use axum::{Extension, Json, extract::State, http::StatusCode};
use datavault_domain::{SearchRequest, SearchResult};
use serde::Deserialize;
use serde_json::{Value, json};
use std::collections::{BTreeMap, HashSet};

use crate::{
    handlers::{ApiResult, err},
    middleware::WorkspaceAccess,
    state::AppState,
};

#[derive(Deserialize)]
pub struct DiscoverSourcesRequest {
    pub prompt: String,
    #[serde(default)]
    pub domain_filters: Vec<String>,
}

fn normalized_filters(domains: &[String]) -> Result<Vec<String>, &'static str> {
    if domains.len() > 25 {
        return Err("Use at most 25 domain restrictions.");
    }
    let mut output = Vec::new();
    for domain in domains {
        let domain = domain
            .trim()
            .to_ascii_lowercase()
            .trim_end_matches('.')
            .to_owned();
        if domain.len() > 253
            || !domain.contains('.')
            || domain.split('.').any(|label| {
                label.is_empty()
                    || label.len() > 63
                    || label.starts_with('-')
                    || label.ends_with('-')
                    || !label
                        .bytes()
                        .all(|c| c.is_ascii_alphanumeric() || c == b'-')
            })
            || domain
                .rsplit('.')
                .next()
                .is_none_or(|tld| tld.len() < 2 || !tld.bytes().all(|c| c.is_ascii_alphabetic()))
        {
            return Err(
                "Enter domains such as example.com, without a URL, path, port or wildcard.",
            );
        }
        if !output.contains(&domain) {
            output.push(domain);
        }
    }
    Ok(output)
}

fn search_terms(text: &str) -> Vec<String> {
    let mut terms = Vec::new();
    for word in text.split(|c: char| !c.is_alphanumeric()) {
        let word = word.to_lowercase();
        if word.len() < 2
            || matches!(
                word.as_str(),
                "find"
                    | "list"
                    | "show"
                    | "get"
                    | "search"
                    | "please"
                    | "me"
                    | "all"
                    | "potential"
                    | "the"
                    | "an"
                    | "for"
                    | "in"
                    | "with"
                    | "and"
                    | "or"
                    | "of"
                    | "that"
                    | "have"
                    | "has"
                    | "which"
                    | "are"
                    | "is"
                    | "to"
                    | "from"
                    | "at"
                    | "as"
                    | "information"
                    | "about"
            )
        {
            continue;
        }
        if !terms.contains(&word) {
            terms.push(word);
        }
    }
    terms
}

fn candidate_matches(result: &SearchResult, terms: &[String]) -> bool {
    // This is a coarse discovery filter, never evidence verification or a confidence score.
    // In particular, an engine result matching only "Find" must not seed a collection.
    let text = format!(
        "{} {} {}",
        result.title,
        result.snippet.as_deref().unwrap_or(""),
        result.url
    )
    .to_lowercase();
    let words: HashSet<_> = text
        .split(|c: char| !c.is_alphanumeric())
        .map(|word| word.trim_end_matches('s'))
        .collect();
    let matches = terms
        .iter()
        .filter(|term| words.contains(term.trim_end_matches('s')))
        .count();
    // Supplier discovery needs a supply-side signal. EV + India alone also
    // matches consumer car listings. This is metadata screening, not verification.
    let supplier_request = terms.iter().any(|t| matches!(t.trim_end_matches('s'), "supplier" | "manufacturer" | "vendor"));
    if supplier_request && !["supplier", "supply", "supplies", "manufacturer", "manufacturing", "vendor", "exhibitor", "producer", "component"]
        .iter().any(|word| words.contains(word)) {
        return false;
    }
    !terms.is_empty() && matches >= terms.len().min(2)
}

fn grouped_candidates(
    results: Vec<SearchResult>,
    blocked: &[String],
    terms: &[String],
) -> Vec<Value> {
    let mut groups = BTreeMap::<String, Vec<Value>>::new();
    let mut seen = HashSet::new();
    for result in results {
        if !candidate_matches(&result, terms) {
            continue;
        }
        let Ok(url) = url::Url::parse(&result.url) else {
            continue;
        };
        let Some(host) = url.host_str() else { continue };
        let domain = host.trim_end_matches('.').to_ascii_lowercase();
        if blocked
            .iter()
            .any(|d| domain == *d || domain.ends_with(&format!(".{d}")))
            || !seen.insert(result.url.clone())
        {
            continue;
        }
        groups.entry(domain).or_default().push(json!({
            "url": result.url, "title": result.title, "provider": result.provider, "snippet": result.snippet,
        }));
    }
    groups
        .into_iter()
        .map(|(domain, pages)| json!({"domain": domain, "pages": pages}))
        .collect()
}

/// Authenticated discovery happens before collection permission is requested.
/// Only search-provider metadata is returned. No collection or run is created.
pub async fn discover(
    State(state): State<AppState>,
    Extension(WorkspaceAccess(workspace_id)): Extension<WorkspaceAccess>,
    Json(body): Json<DiscoverSourcesRequest>,
) -> ApiResult<Json<Value>> {
    let prompt = body.prompt.trim();
    if !(5..=500).contains(&prompt.chars().count()) {
        return Err(err(
            StatusCode::UNPROCESSABLE_ENTITY,
            "Enter a requirement between 5 and 500 characters.",
        ));
    }
    let filters = normalized_filters(&body.domain_filters)
        .map_err(|message| err(StatusCode::UNPROCESSABLE_ENTITY, message))?;
    let terms = search_terms(prompt);
    // Discover entities first; requested output columns can otherwise overwhelm
    // the search (e.g. "with catalog links, locations and certifications").
    let lower = prompt.to_lowercase();
    let discovery_terms = search_terms(lower.split(" with ").next().unwrap_or(&lower));
    if terms.is_empty() {
        return Err(err(
            StatusCode::UNPROCESSABLE_ENTITY,
            "Describe the entities or topic you want to find.",
        ));
    }
    let blocked: Vec<String> =
        sqlx::query_scalar("SELECT domain FROM sources WHERE workspace_id=$1 AND enabled=false")
            .bind(workspace_id)
            .fetch_all(&state.db.pool)
            .await
            .map_err(|_| {
                err(
                    StatusCode::SERVICE_UNAVAILABLE,
                    "Cannot check disabled sources. Please retry.",
                )
            })?;
    let blocked: Vec<_> = blocked
        .into_iter()
        .map(|d| {
            d.trim()
                .to_ascii_lowercase()
                .trim_end_matches('.')
                .to_owned()
        })
        .collect();
    let results = tokio::time::timeout(
        std::time::Duration::from_secs(20),
        state.search.discover_sources(SearchRequest {
            query: discovery_terms.join(" "),
            max_results: 20,
            domain_filters: filters,
            freshness_days: None,
            model_config: None,
        }),
    )
    .await
    .map_err(|_| {
        err(
            StatusCode::GATEWAY_TIMEOUT,
            "Source discovery timed out. Retry or enter a domain you already know.",
        )
    })?
    .map_err(|_| {
        err(
            StatusCode::BAD_GATEWAY,
            "Search is unavailable. Retry or enter a domain you already know.",
        )
    })?;
    let domains = grouped_candidates(results, &blocked, &terms);
    Ok(Json(json!({ "domains": domains, "total": domains.len() })))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn restrictions_are_optional_but_invalid_values_never_become_unrestricted() {
        assert!(normalized_filters(&[]).unwrap().is_empty());
        assert_eq!(
            normalized_filters(&["EXAMPLE.COM".into(), "example.com".into()]).unwrap(),
            vec!["example.com"]
        );
        for input in [
            "https://example.com",
            "*.example.com",
            "example.com/path",
            "example.com:80",
            "bad..com",
            "127.0.0.1",
        ] {
            assert!(normalized_filters(&[input.into()]).is_err(), "{input}");
        }
    }

    #[test]
    fn review_groups_candidates_and_excludes_disabled_domains() {
        let result = |url: &str| SearchResult {
            url: url.into(),
            title: "Candidate".into(),
            snippet: None,
            provider: "fixture".into(),
            rank: 1,
            original_url: None,
            redirected: false,
            root_fallback: false,
        };
        let domains = grouped_candidates(
            vec![
                result("https://news.blocked.example/a"),
                result("https://allowed.example/a"),
                result("https://allowed.example/a"),
                result("https://allowed.example/b"),
            ],
            &["blocked.example".into()],
            &["candidate".into()],
        );
        assert_eq!(domains.len(), 1);
        assert_eq!(domains[0]["domain"], "allowed.example");
        assert_eq!(domains[0]["pages"].as_array().unwrap().len(), 2);
        assert!(domains[0].get("approved").is_none());
    }

    #[test]
    fn generic_find_results_do_not_become_robotics_source_suggestions() {
        let terms = search_terms("Find potential sponsors for a robotics hackathon in Tamil Nadu.");
        assert_eq!(terms.join(" "), "sponsors robotics hackathon tamil nadu");
        let mut result = SearchResult {
            url: "https://example.com/find-phone".into(),
            title: "Find your phone".into(),
            snippet: None,
            provider: "fixture".into(),
            rank: 1,
            original_url: None,
            redirected: false,
            root_fallback: false,
        };
        assert!(!candidate_matches(&result, &terms));
        result.title = "Robotics hackathon sponsors in Tamil Nadu".into();
        assert!(candidate_matches(&result, &terms));
    }

    #[test]
    fn consumer_car_listings_are_not_supplier_candidates() {
        let terms = search_terms("List EV battery and component suppliers in India with catalog links");
        let mut result = SearchResult { url: "https://example.com/electric-cars-india".into(), title: "EV Cars in India - Prices, Range and Reviews".into(), snippet: None, provider: "fixture".into(), rank: 1, original_url: None, redirected: false, root_fallback: false };
        assert!(!candidate_matches(&result, &terms));
        result.title = "EV Component Manufacturers in India".into();
        assert!(candidate_matches(&result, &terms));
    }
}
