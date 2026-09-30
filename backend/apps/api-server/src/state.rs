use datavault_auth::AuthService;
use datavault_search::{
    DdgsProvider, FederatedSearch, SearxProvider, WikipediaProvider,
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
        let wiki = WikipediaProvider::new();

        let search = Arc::new(FederatedSearch::new(vec![
            Box::new(DdgsProvider::new(std::env::var("SCRAPLING_URL").unwrap_or_else(|_| "http://127.0.0.1:8001".into()))),
            Box::new(searx),
            Box::new(wiki),
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
