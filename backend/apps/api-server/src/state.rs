use datavault_auth::AuthService;
use datavault_search::{
    DuckDuckGoProvider, FederatedSearch, LlmSearchProvider, SearxProvider, WikipediaProvider,
};
use datavault_storage::{Cache, Db};
use std::sync::Arc;

/// Shared application state injected into every Axum handler.
#[derive(Clone)]
pub struct AppState {
    pub db: Db,
    pub cache: Cache,
    pub auth: AuthService,
    pub intel_client: reqwest::Client,
    pub intel_base_url: String,
    pub search: Arc<FederatedSearch>,
}

impl AppState {
    pub fn new(
        db: Db,
        cache: Cache,
        auth: AuthService,
        intelligence_url: String,
        searxng_url: String,
    ) -> Self {
        let intel_client = reqwest::Client::builder()
            .timeout(std::time::Duration::from_secs(60))
            .build()
            .expect("intel http client");

        let searx = SearxProvider::new(searxng_url);
        let llm_search = LlmSearchProvider::new(&intelligence_url);
        let wiki = WikipediaProvider::new();

        let search = Arc::new(FederatedSearch::new(vec![
            Box::new(searx),
            Box::new(DuckDuckGoProvider::default()),
            Box::new(wiki),
            Box::new(llm_search),
        ]));

        Self {
            db,
            cache,
            auth,
            intel_client,
            intel_base_url: intelligence_url,
            search,
        }
    }
}
