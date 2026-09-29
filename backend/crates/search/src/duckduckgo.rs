//! Public search fallback requested in the implementation handoff.
use crate::{SearchProvider, public_web_url, sanitize_query};
use anyhow::Result;
use async_trait::async_trait;
use datavault_domain::{SearchRequest, SearchResult};
use std::time::Duration;
use url::Url;

pub struct DuckDuckGoProvider {
    client: reqwest::Client,
}

impl Default for DuckDuckGoProvider {
    fn default() -> Self {
        Self {
            client: reqwest::Client::builder()
                .timeout(Duration::from_secs(5))
                .user_agent("Mozilla/5.0 (compatible; Datavault/1.0)")
                .build()
                .unwrap_or_default(),
        }
    }
}

pub(crate) fn parse_results(html: &str, limit: usize) -> Vec<SearchResult> {
    let document = scraper::Html::parse_document(html);
    let rows = scraper::Selector::parse(".result").unwrap();
    let links = scraper::Selector::parse("a.result__a").unwrap();
    let snippets = scraper::Selector::parse(".result__snippet").unwrap();
    let base = Url::parse("https://html.duckduckgo.com/").unwrap();
    document
        .select(&rows)
        .filter_map(|row| {
            let link = row.select(&links).next()?;
            let target = base.join(link.value().attr("href")?).ok()?;
            let url = target
                .query_pairs()
                .find(|(key, _)| key == "uddg")
                .map(|(_, value)| value.into_owned())
                .unwrap_or_else(|| target.to_string());
            let parsed = Url::parse(&url).ok()?;
            if !public_web_url(&parsed) || parsed.host_str()?.ends_with("duckduckgo.com") {
                return None;
            }
            Some(SearchResult {
                url,
                title: link.text().collect::<Vec<_>>().join(" "),
                snippet: row
                    .select(&snippets)
                    .next()
                    .map(|s| s.text().collect::<Vec<_>>().join(" ")),
                provider: "duckduckgo".into(),
                rank: 0,
                original_url: None,
                root_fallback: false,
                redirected: false,
            })
        })
        .take(limit)
        .enumerate()
        .map(|(i, mut result)| {
            result.rank = i + 1;
            result
        })
        .collect()
}

#[async_trait]
impl SearchProvider for DuckDuckGoProvider {
    fn name(&self) -> &'static str {
        "duckduckgo"
    }
    async fn search(&self, req: SearchRequest) -> Result<Vec<SearchResult>> {
        let response = self
            .client
            .get("https://html.duckduckgo.com/html/")
            .query(&[("q", sanitize_query(&req.query))])
            .send()
            .await?
            .error_for_status()?;
        Ok(parse_results(&response.text().await?, req.max_results))
    }
}
