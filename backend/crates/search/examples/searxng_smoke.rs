//! Live discovery check using the application's actual search adapter. No LLM,
//! database, result-page retrieval or fallback provider is involved.
use anyhow::{Result, ensure};
use datavault_domain::SearchRequest;
use datavault_search::{FederatedSearch, SearxProvider};
use std::time::Instant;

#[tokio::main]
async fn main() -> Result<()> {
    let base = std::env::var("SEARXNG_URL").unwrap_or_else(|_| "http://127.0.0.1:8888".to_string());
    let query = std::env::args()
        .nth(1)
        .unwrap_or_else(|| "Python documentation".into());
    let domain = std::env::args()
        .nth(2)
        .unwrap_or_else(|| "python.org".into());
    let search = FederatedSearch::new(vec![Box::new(SearxProvider::new(base))]);
    let start = Instant::now();
    let results = search
        .search(SearchRequest {
            query,
            domain_filters: vec![domain.clone()],
            max_results: 5,
            freshness_days: None,
            model_config: None,
        })
        .await?;
    ensure!(
        !results.is_empty(),
        "No results within the required domain; inspect SearXNG engine status"
    );
    ensure!(
        results.iter().all(|r| r.provider == "searxng"),
        "Unexpected fallback provider"
    );
    println!(
        "PASS: {} SearXNG candidates within {} in {:.2}s",
        results.len(),
        domain,
        start.elapsed().as_secs_f64()
    );
    for result in results {
        println!("{}", result.url);
    }
    Ok(())
}
