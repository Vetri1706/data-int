use anyhow::Result;
use async_trait::async_trait;
use datavault_domain::{SearchRequest, SearchResult};
#[cfg(test)]
use futures_util::{StreamExt, stream};
use serde::Deserialize;
use serde_json::json;
use std::net::IpAddr;
#[cfg(test)]
use std::{collections::HashSet, time::Duration};
use tracing::{debug, warn};
use url::Url;
mod duckduckgo;
pub use duckduckgo::DuckDuckGoProvider;

pub fn sanitize_query(query: &str) -> String {
    let operators = regex::Regex::new(r"(?i)\b(site|filetype|intitle|inurl):\S+").unwrap();
    operators
        .replace_all(query, " ")
        .replace(['\"', '(', ')', '[', ']', '|', '“', '”'], " ")
        .split_whitespace()
        .filter(|token| !matches!(*token, "AND" | "OR" | "NOT"))
        .collect::<Vec<_>>()
        .join(" ")
}

fn public_web_url(url: &Url) -> bool {
    if !matches!(url.scheme(), "http" | "https")
        || !url.username().is_empty()
        || url.password().is_some()
    {
        return false;
    }
    let Some(host) = url.host_str() else {
        return false;
    };
    if host == "localhost"
        || host.ends_with(".localhost")
        || host.ends_with(".local")
        || !host.contains('.') && !host.contains(':')
    {
        return false;
    }
    if let Ok(ip) = host.trim_matches(['[', ']']).parse::<IpAddr>() {
        return match ip {
            IpAddr::V4(ip) => {
                !(ip.is_loopback()
                    || ip.is_private()
                    || ip.is_link_local()
                    || ip.is_unspecified()
                    || ip.is_multicast()
                    || ip.is_broadcast())
            }
            IpAddr::V6(ip) => {
                !(ip.is_loopback()
                    || ip.is_unspecified()
                    || ip.is_unique_local()
                    || ip.is_unicast_link_local()
                    || ip.is_multicast()
                    || ip.to_ipv4_mapped().is_some())
            }
        };
    }
    true
}

#[cfg(test)]
async fn check_url(
    client: &reqwest::Client,
    url: &str,
    allow_root: bool,
) -> Option<(String, bool, bool)> {
    let mut parsed = Url::parse(url).ok()?;
    if !public_web_url(&parsed) {
        return None;
    }
    for attempt in 0..=usize::from(allow_root) {
        let mut response = client.head(parsed.clone()).send().await.ok()?;
        if matches!(response.status().as_u16(), 403 | 405 | 501) {
            response = client.get(parsed.clone()).send().await.ok()?;
        }
        if response.status() == reqwest::StatusCode::OK {
            return Some((
                response.url().to_string(),
                attempt > 0,
                response.url() != &parsed,
            ));
        }
        if attempt == 0
            && allow_root
            && matches!(response.status().as_u16(), 403 | 404)
            && parsed.path() != "/"
        {
            parsed.set_path("/");
            parsed.set_query(None);
            parsed.set_fragment(None);
        } else {
            return None;
        }
    }
    None
}

#[cfg(test)]
async fn verified_results(
    client: &reqwest::Client,
    results: Vec<SearchResult>,
    allow_root: bool,
) -> Vec<SearchResult> {
    let mut verified: Vec<_> =
        stream::iter(results.into_iter().take(30).map(|mut result| async move {
            let (url, root_fallback, redirected) =
                check_url(client, &result.url, allow_root).await?;
            result.original_url = Some(result.url.clone());
            result.url = url;
            result.root_fallback = root_fallback;
            result.redirected = redirected;
            if root_fallback || result.provider == "llm_grounded" {
                // A reachable root does not substantiate a generated deep-page claim.
                result.snippet = None;
                if root_fallback {
                    result.title = Url::parse(&result.url).ok()?.host_str()?.to_string();
                }
            }
            Some(result)
        }))
        .buffer_unordered(8)
        .filter_map(|r| async move { r })
        .collect()
        .await;
    verified.sort_by_key(|r| r.rank);
    let mut seen = HashSet::new();
    verified.retain(|r| seen.insert(r.url.clone()));
    verified
}

// ─── Trait ────────────────────────────────────────────────────────────────────

/// Abstract search provider — swap implementations without touching callers.
#[async_trait]
pub trait SearchProvider: Send + Sync {
    async fn search(&self, req: SearchRequest) -> Result<Vec<SearchResult>>;
    fn name(&self) -> &'static str;
}

/// Maintained DDGS search adapters, hosted beside Scrapling.
pub struct DdgsProvider { client: reqwest::Client, base_url: String }
impl DdgsProvider {
    pub fn new(base_url: impl Into<String>) -> Self {
        Self { client: reqwest::Client::builder().timeout(std::time::Duration::from_secs(17)).build().unwrap_or_default(),
            base_url: base_url.into().trim_end_matches('/').to_owned() }
    }
}
#[async_trait]
impl SearchProvider for DdgsProvider {
    fn name(&self) -> &'static str { "ddgs" }
    async fn search(&self, req: SearchRequest) -> Result<Vec<SearchResult>> {
        #[derive(Deserialize)]
        struct Response { results: Vec<SearchResult> }
        Ok(self.client.post(format!("{}/search", self.base_url))
            .json(&json!({"query": req.query, "domain_filters": req.domain_filters, "max_results": req.max_results.min(20)}))
            .send().await?.error_for_status()?.json::<Response>().await?.results)
    }
}

// ─── SearXNG ─────────────────────────────────────────────────────────────────

pub struct SearxProvider {
    client: reqwest::Client,
    base_url: String,
}

impl SearxProvider {
    pub fn new(base_url: impl Into<String>) -> Self {
        let client = reqwest::Client::builder()
            .timeout(std::time::Duration::from_secs(5))
            .user_agent("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")
            .build()
            .expect("http client");
        Self {
            client,
            base_url: base_url.into().trim_end_matches('/').to_string(),
        }
    }
}

#[derive(Debug, Deserialize)]
struct SearxResponse {
    #[serde(default)]
    results: Vec<SearxResult>,
}

#[derive(Debug, Deserialize)]
struct SearxResult {
    #[serde(default)]
    url: String,
    title: Option<String>,
    content: Option<String>,
}

#[async_trait]
impl SearchProvider for SearxProvider {
    fn name(&self) -> &'static str {
        "searxng"
    }

    async fn search(&self, req: SearchRequest) -> Result<Vec<SearchResult>> {
        let mut params = vec![
            ("q", req.query.clone()),
            ("format", "json".into()),
            ("pageno", "1".into()),
        ];

        if !req.domain_filters.is_empty() {
            let site_filter = req
                .domain_filters
                .iter()
                .map(|d| format!("site:{d}"))
                .collect::<Vec<_>>()
                .join(" OR ");
            params[0].1 = format!("{} ({})", req.query, site_filter);
        }

        if let Some(days) = req.freshness_days {
            params.push((
                "time_range",
                match days {
                    ..=1 => "day",
                    ..=7 => "week",
                    ..=30 => "month",
                    _ => "year",
                }
                .into(),
            ));
        }

        debug!(query = %req.query, provider = "searxng", "executing search");

        let resp = self
            .client
            .get(format!("{}/search", self.base_url))
            .query(&params)
            .send()
            .await?;

        if !resp.status().is_success() {
            warn!(status = %resp.status(), "SearXNG returned non-200");
            return Ok(vec![]);
        }

        let body: SearxResponse = resp.json().await?;

        let results: Vec<SearchResult> = body
            .results
            .into_iter()
            .enumerate()
            .take(req.max_results)
            .map(|(i, r)| SearchResult {
                url: r.url,
                title: r.title.unwrap_or_default(),
                snippet: r.content,
                provider: "searxng".into(),
                rank: i + 1,
                original_url: None,
                root_fallback: false,
                redirected: false,
            })
            .collect();

        Ok(results)
    }
}

// ─── Wikipedia OpenSearch (instant, zero-auth, high-trust) ───────────────────

pub struct WikipediaProvider {
    client: reqwest::Client,
}

impl WikipediaProvider {
    pub fn new() -> Self {
        let client = reqwest::Client::builder()
            .timeout(std::time::Duration::from_secs(5))
            .user_agent("Datavault/1.0 (research data platform)")
            .build()
            .unwrap_or_default();
        Self { client }
    }
}

impl Default for WikipediaProvider {
    fn default() -> Self {
        Self::new()
    }
}

#[async_trait]
impl SearchProvider for WikipediaProvider {
    fn name(&self) -> &'static str {
        "wikipedia"
    }

    async fn search(&self, req: SearchRequest) -> Result<Vec<SearchResult>> {
        let clean_q: String = req
            .query
            .split("site:")
            .next()
            .unwrap_or(&req.query)
            .trim()
            .to_string();

        let url = format!(
            "https://en.wikipedia.org/w/api.php?action=opensearch&search={}&limit={}&format=json",
            urlencoding(&clean_q),
            req.max_results.min(10)
        );

        let mut results = Vec::new();
        if let Ok(res) = self.client.get(&url).send().await {
            if let Ok(arr) = res.json::<serde_json::Value>().await {
                if let (Some(titles), Some(snippets), Some(urls)) = (
                    arr.get(1).and_then(|v| v.as_array()),
                    arr.get(2).and_then(|v| v.as_array()),
                    arr.get(3).and_then(|v| v.as_array()),
                ) {
                    for (i, t_val) in titles.iter().enumerate() {
                        let title = t_val.as_str().unwrap_or("").to_string();
                        let url = urls
                            .get(i)
                            .and_then(|u| u.as_str())
                            .unwrap_or("")
                            .to_string();
                        let snippet = snippets
                            .get(i)
                            .and_then(|s| s.as_str())
                            .map(|s| s.to_string());
                        if !title.is_empty() && !url.is_empty() {
                            results.push(SearchResult {
                                url,
                                title,
                                snippet,
                                provider: "wikipedia".into(),
                                rank: i + 1,
                                original_url: None,
                                root_fallback: false,
                                redirected: false,
                            });
                        }
                    }
                }
            }
        }
        Ok(results)
    }
}

// ─── LLM URL suggestions (verified by FederatedSearch before use) ──────────

pub struct LlmSearchProvider {
    client: reqwest::Client,
    intelligence_url: String,
}

impl LlmSearchProvider {
    pub fn new(intelligence_url: impl Into<String>) -> Self {
        let client = reqwest::Client::builder()
            .timeout(std::time::Duration::from_secs(22))
            .build()
            .unwrap_or_default();
        Self {
            client,
            intelligence_url: intelligence_url.into().trim_end_matches('/').into(),
        }
    }
}

#[async_trait]
impl SearchProvider for LlmSearchProvider {
    fn name(&self) -> &'static str {
        "llm_grounded"
    }

    async fn search(&self, req: SearchRequest) -> Result<Vec<SearchResult>> {
        // Keep every model call behind one provider selection and rate limiter.
        // Rust never holds a model API key or silently falls back to Groq.
        let resp = self
            .client
            .post(format!("{}/discover", self.intelligence_url))
            .json(&json!({"query": sanitize_query(&req.query), "max_results": req.max_results.min(5), "model_selection": req.model_config}))
            .send()
            .await?;

        if !resp.status().is_success() {
            return Ok(vec![]);
        }

        let val: serde_json::Value = resp.json().await?;
        let mut results = Vec::new();
        if let Some(arr) = val.get("results").and_then(|v| v.as_array()) {
            for (i, item) in arr.iter().take(req.max_results).enumerate() {
                let title = item
                    .get("title")
                    .and_then(|t| t.as_str())
                    .unwrap_or("")
                    .to_string();
                let url = item
                    .get("url")
                    .and_then(|u| u.as_str())
                    .unwrap_or("")
                    .to_string();
                let snippet = item
                    .get("snippet")
                    .and_then(|s| s.as_str())
                    .map(|s| s.to_string());
                if !url.is_empty() && !title.is_empty() {
                    results.push(SearchResult {
                        url,
                        title,
                        snippet,
                        provider: "llm_grounded".into(),
                        rank: i + 1,
                        original_url: None,
                        root_fallback: false,
                        redirected: false,
                    });
                }
            }
        }

        Ok(results)
    }
}

// ─── Federated Search (multi-provider cascade with live verification) ────────

pub struct FederatedSearch {
    providers: Vec<Box<dyn SearchProvider>>,
}

impl FederatedSearch {
    pub fn new(providers: Vec<Box<dyn SearchProvider>>) -> Self {
        Self { providers }
    }

    pub async fn search(&self, mut req: SearchRequest) -> Result<Vec<SearchResult>> {
        self.search_candidates(&mut req, true).await
    }

    /// Search-engine candidates only: no result-page fetches and no model calls.
    /// Used before the user has selected/approved sources for collection.
    pub async fn discover_sources(&self, mut req: SearchRequest) -> Result<Vec<SearchResult>> {
        req.model_config = None;
        self.search_candidates(&mut req, false).await
    }

    async fn search_candidates(
        &self,
        req: &mut SearchRequest,
        allow_llm: bool,
    ) -> Result<Vec<SearchResult>> {
        req.query = sanitize_query(&req.query);
        req.max_results = req.max_results.min(30);
        if req.query.is_empty() || req.max_results == 0 {
            return Ok(vec![]);
        }
        for provider in &self.providers {
            if !allow_llm && provider.name() == "llm_grounded" {
                continue;
            }
            match provider.search(req.clone()).await {
                Ok(results) if !results.is_empty() => {
                    // Discovery never fetches result destinations. Retrieval owns permission,
                    // robots checks, redirect enforcement and observed HTTP evidence.
                    let mut results = results;
                    results.retain(|r| Url::parse(&r.url).ok().is_some_and(|u| public_web_url(&u)));
                    if !req.domain_filters.is_empty() {
                        let domain_matched: Vec<_> = results
                            .iter()
                            .filter(|r| {
                                Url::parse(&r.url).ok().is_some_and(|url| {
                                    let host = url.host_str().unwrap_or("").to_lowercase();
                                    req.domain_filters.iter().any(|d| {
                                        host == d.to_lowercase()
                                            || host.ends_with(&format!(".{}", d.to_lowercase()))
                                    })
                                })
                            })
                            .cloned()
                            .collect();
                        results = domain_matched;
                    }
                    if !results.is_empty() {
                        results.truncate(req.max_results);
                        debug!(
                            provider = provider.name(),
                            count = results.len(),
                            "candidate discovery succeeded"
                        );
                        return Ok(results);
                    }
                    warn!(
                        provider = provider.name(),
                        "no candidates within required domains; continuing cascade"
                    );
                }
                Ok(_) => {
                    warn!(
                        provider = provider.name(),
                        "returned 0 results, trying next"
                    );
                }
                Err(e) => {
                    warn!(provider = provider.name(), error = %e, "search failed, trying next");
                }
            }
        }
        Ok(vec![])
    }
}

fn urlencoding(s: &str) -> String {
    url::form_urlencoded::byte_serialize(s.as_bytes()).collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    use tokio::io::{AsyncReadExt, AsyncWriteExt};

    #[tokio::test]
    async fn discovery_forwards_collection_model_without_provider_credentials() {
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let address = listener.local_addr().unwrap();
        let server = tokio::spawn(async move {
            let (mut socket, _) = listener.accept().await.unwrap();
            let mut request = Vec::new();
            loop {
                let mut chunk = [0; 4096];
                let n = socket.read(&mut chunk).await.unwrap();
                if n == 0 {
                    break;
                }
                request.extend_from_slice(&chunk[..n]);
                let text = String::from_utf8_lossy(&request);
                if let Some((headers, body)) = text.split_once("\r\n\r\n") {
                    let length: usize = headers
                        .lines()
                        .find_map(|line| {
                            line.to_lowercase()
                                .strip_prefix("content-length: ")
                                .and_then(|v| v.parse().ok())
                        })
                        .unwrap_or(0);
                    if body.len() >= length {
                        break;
                    }
                }
            }
            let request = String::from_utf8(request).unwrap();
            assert!(request.starts_with("POST /discover "));
            assert!(!request.to_lowercase().contains("authorization:"));
            let body: serde_json::Value =
                serde_json::from_str(request.split_once("\r\n\r\n").unwrap().1).unwrap();
            assert_eq!(
                body["model_selection"]["model"],
                "qwen2.5-coder:1.5b-instruct"
            );
            assert_eq!(body["model_selection"]["allow_external"], false);
            let response = r#"{"results":[{"title":"Fixture","url":"https://example.com"}]}"#;
            socket.write_all(format!("HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{response}", response.len()).as_bytes()).await.unwrap();
        });
        let provider = LlmSearchProvider::new(format!("http://{address}"));
        let results = provider.search(SearchRequest { query: "robotics".into(), domain_filters: vec![], max_results: 5, freshness_days: None,
            model_config: Some(json!({"provider":"local", "model":"qwen2.5-coder:1.5b-instruct", "allow_external":false})) }).await.unwrap();
        assert_eq!(results.len(), 1);
        server.await.unwrap();
    }

    #[test]
    fn strips_operators_without_losing_following_keywords() {
        assert_eq!(
            sanitize_query("\"AI startups\" site:example.com AND (Bangalore OR Chennai) funding"),
            "AI startups Bangalore Chennai funding"
        );
    }

    #[test]
    fn unsafe_urls_are_not_fetched() {
        for url in [
            "file:///etc/passwd",
            "http://127.0.0.1/",
            "http://10.0.0.1/",
            "http://localhost/",
            "http://[::1]/",
            "https://user:pass@example.com/",
        ] {
            assert!(!public_web_url(&Url::parse(url).unwrap()), "{url}");
        }
        assert!(public_web_url(
            &Url::parse("https://example.com/about").unwrap()
        ));
    }

    #[test]
    fn parses_real_index_links_and_decodes_redirects() {
        let html = r#"<div class="result"><a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fabout">Acme &amp; Sons</a><div class="result__snippet">Robotics company</div></div>"#;
        let rows = duckduckgo::parse_results(html, 5);
        assert_eq!(rows.len(), 1);
        assert_eq!(rows[0].url, "https://example.com/about");
        assert_eq!(rows[0].title, "Acme & Sons");
        assert!(duckduckgo::parse_results("<p>captcha</p>", 5).is_empty());
    }

    async fn server() -> (String, reqwest::Client, tokio::task::JoinHandle<()>) {
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let address = listener.local_addr().unwrap();
        let task = tokio::spawn(async move {
            loop {
                let Ok((mut socket, _)) = listener.accept().await else {
                    break;
                };
                let mut buffer = [0; 4096];
                let length = socket.read(&mut buffer).await.unwrap_or(0);
                let request = String::from_utf8_lossy(&buffer[..length]);
                let first = request.lines().next().unwrap_or("");
                let status = if first.contains("/dead ") {
                    "404 Not Found"
                } else if first.starts_with("HEAD /head-blocked ") {
                    "405 Method Not Allowed"
                } else if first.contains("/denied ") {
                    "403 Forbidden"
                } else {
                    "200 OK"
                };
                let response =
                    format!("HTTP/1.1 {status}\r\nContent-Length: 0\r\nConnection: close\r\n\r\n");
                let _ = socket.write_all(response.as_bytes()).await;
            }
        });
        let client = reqwest::Client::builder()
            .no_proxy()
            .resolve("source.example", address)
            .timeout(Duration::from_millis(1500))
            .build()
            .unwrap();
        (
            format!("http://source.example:{}", address.port()),
            client,
            task,
        )
    }

    #[tokio::test]
    async fn live_root_fallback_clears_unverified_deep_claims() {
        let (base, client, task) = server().await;
        let rows = verified_results(
            &client,
            vec![SearchResult {
                url: format!("{base}/dead"),
                title: "Invented page".into(),
                snippet: Some("Invented evidence".into()),
                provider: "llm_grounded".into(),
                rank: 1,
                original_url: None,
                root_fallback: false,
                redirected: false,
            }],
            true,
        )
        .await;
        task.abort();
        assert_eq!(rows.len(), 1);
        assert_eq!(rows[0].url, format!("{base}/"));
        assert_eq!(rows[0].snippet, None);
    }

    #[tokio::test]
    async fn head_unsupported_uses_get_and_dead_without_fallback_dropped() {
        let (base, client, task) = server().await;
        assert!(
            check_url(&client, &format!("{base}/head-blocked"), false)
                .await
                .is_some()
        );
        assert!(
            check_url(&client, &format!("{base}/dead"), false)
                .await
                .is_none()
        );
        assert!(
            check_url(&client, &format!("{base}/denied"), false)
                .await
                .is_none()
        );
        task.abort();
    }

    struct FixtureProvider {
        url: String,
    }

    struct ModelMustNotRun;
    #[async_trait]
    impl SearchProvider for ModelMustNotRun {
        fn name(&self) -> &'static str {
            "llm_grounded"
        }
        async fn search(&self, _: SearchRequest) -> Result<Vec<SearchResult>> {
            panic!("Source review must never invoke a model or invent candidate URLs")
        }
    }

    #[tokio::test]
    async fn source_review_accepts_no_domains_and_never_calls_model_fallback() {
        let request = SearchRequest {
            query: "robotics companies".into(),
            max_results: 5,
            domain_filters: vec![],
            freshness_days: None,
            model_config: None,
        };
        let search = FederatedSearch::new(vec![Box::new(ModelMustNotRun)]);
        assert!(
            search
                .discover_sources(request.clone())
                .await
                .unwrap()
                .is_empty()
        );
        let search = FederatedSearch::new(vec![
            Box::new(FixtureProvider {
                url: "https://unreachable-source.example/candidate".into(),
            }),
            Box::new(ModelMustNotRun),
        ]);
        // Search metadata is returned without fetching the source page.
        let results = search.discover_sources(request.clone()).await.unwrap();
        assert_eq!(results.len(), 1);
        let mut restricted = request;
        restricted.domain_filters = vec!["another.example".into()];
        assert!(
            search
                .discover_sources(restricted)
                .await
                .unwrap()
                .is_empty()
        );
    }
    #[async_trait]
    impl SearchProvider for FixtureProvider {
        fn name(&self) -> &'static str {
            "fixture"
        }
        async fn search(&self, _: SearchRequest) -> Result<Vec<SearchResult>> {
            Ok(vec![SearchResult {
                url: self.url.clone(),
                title: "Acme".into(),
                snippet: None,
                provider: "fixture".into(),
                rank: 1,
                original_url: None,
                root_fallback: false,
                redirected: false,
            }])
        }
    }

    #[tokio::test]
    async fn hard_domains_never_relax_for_fallback_or_suffix_spoofs() {
        let request = SearchRequest {
            query: "test".into(),
            max_results: 5,
            domain_filters: vec!["allowed.example".into()],
            freshness_days: None,
            model_config: None,
        };
        for url in [
            "https://outside.example/page",
            "https://allowed.example.attacker.test/page",
        ] {
            let search = FederatedSearch::new(vec![Box::new(FixtureProvider { url: url.into() })]);
            assert!(search.search(request.clone()).await.unwrap().is_empty());
        }
        let search = FederatedSearch::new(vec![
            Box::new(FixtureProvider {
                url: "https://outside.example/page".into(),
            }),
            Box::new(FixtureProvider {
                url: "https://news.allowed.example/page".into(),
            }),
        ]);
        let results = search.search(request).await.unwrap();
        assert_eq!(results.len(), 1);
        assert_eq!(results[0].url, "https://news.allowed.example/page");
    }

    #[tokio::test]
    async fn cascade_skips_unreachable_candidate_and_retains_domain_filters() {
        let (base, _client, task) = server().await;
        let search = FederatedSearch {
            providers: vec![
                Box::new(FixtureProvider {
                    url: "http://127.0.0.1/private".into(),
                }),
                Box::new(FixtureProvider {
                    url: format!("{base}/live"),
                }),
            ],
        };
        let mut req = SearchRequest {
            query: "Acme robotics".into(),
            max_results: 5,
            domain_filters: vec![],
            freshness_days: None,
            model_config: None,
        };
        assert_eq!(search.search(req.clone()).await.unwrap().len(), 1);
        req.domain_filters = vec!["allowed.example".into()];
        assert!(search.search(req).await.unwrap().is_empty());
        task.abort();
    }
}
