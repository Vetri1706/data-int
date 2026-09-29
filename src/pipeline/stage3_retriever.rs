use crate::config::AppConfig;
use crate::models::SearchResultItem;
use crate::pipeline::scrapler::LiveScraper;
use crate::pipeline::search_provider::{
    LlmFallbackSearchProvider, SearchProvider, SearxngSearchProvider, WikipediaSearchProvider,
};
use tracing::info;

pub struct RetrieverStage;

impl RetrieverStage {
    pub async fn retrieve(
        queries: &[String],
        config: &AppConfig,
        max_results: usize,
    ) -> Vec<SearchResultItem> {
        let mut raw_candidates = Vec::new();
        let searxng_endpoint = config
            .searxng_url
            .clone()
            .unwrap_or_else(|| "http://127.0.0.1:8888".to_string());

        // Instantiate pluggable SearchProviders
        let searx_provider = SearxngSearchProvider::new(searxng_endpoint);
        let wiki_provider = WikipediaSearchProvider::new();

        // 1. Primary: Query SearXNG meta-search provider across query angles
        for q in queries.iter().take(2) {
            info!("Querying SearXNG provider for: {}", q);
            let searx_items = searx_provider.search(q, max_results).await;
            if !searx_items.is_empty() {
                info!("SearXNG returned {} results for '{}'", searx_items.len(), q);
                raw_candidates.extend(searx_items);
            }
        }

        // 2. Secondary: Query Wikipedia OpenSearch for verified documentation
        if let Some(primary_q) = queries.first() {
            let wiki_items = wiki_provider.search(primary_q, 3).await;
            raw_candidates.extend(wiki_items);
        }

        // 3. Fallback Grounded Discovery if candidates < 3
        if raw_candidates.len() < 3 {
            if let Some(ref key) = config.groq_api_key {
                let primary_query = queries.first().cloned().unwrap_or_default();
                let llm_provider = LlmFallbackSearchProvider::new(key.clone());
                let fallback_items = llm_provider.search(&primary_query, max_results).await;
                raw_candidates.extend(fallback_items);
            }
        }

        // 4. Live Adaptive Scraping, JSON-LD Extraction & 404 Purge:
        // Concurrently fetches live web pages, extracts real paragraph text & schema, and drops dead links
        LiveScraper::scrape_and_verify(raw_candidates, 8).await
    }
}
