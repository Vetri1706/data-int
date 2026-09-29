use std::env;

#[derive(Clone, Debug)]
pub struct AppConfig {
    pub host: String,
    pub port: u16,
    pub groq_api_key: Option<String>,
    pub gemini_api_key: Option<String>,
    pub openai_api_key: Option<String>,
    pub nvidia_api_key: Option<String>,
    pub searxng_url: Option<String>,
    pub default_grounding_threshold: f32,
    pub default_model: String,
}

impl AppConfig {
    pub fn from_env() -> Self {
        dotenvy::dotenv().ok();

        let host = env::var("HOST").unwrap_or_else(|_| "127.0.0.1".to_string());
        let port = env::var("PORT")
            .ok()
            .and_then(|p| p.parse().ok())
            .unwrap_or(3000);

        let groq_api_key = env::var("GROQ_API_KEY").ok().filter(|s| !s.is_empty());
        let gemini_api_key = env::var("GEMINI_API_KEY").ok().filter(|s| !s.is_empty());
        let openai_api_key = env::var("OPENAI_API_KEY").ok().filter(|s| !s.is_empty());
        let nvidia_api_key = env::var("NVIDIA_API_KEY").ok().filter(|s| !s.is_empty());
        let searxng_url = env::var("SEARXNG_URL")
            .or_else(|_| env::var("SEARXNG_ENDPOINT"))
            .ok()
            .filter(|s| !s.is_empty())
            .or_else(|| Some("http://127.0.0.1:8888".to_string()));

        let default_grounding_threshold = env::var("GROUNDING_THRESHOLD")
            .ok()
            .and_then(|t| t.parse().ok())
            .unwrap_or(0.65);

        let default_model = env::var("MODEL_NAME")
            .unwrap_or_else(|_| "llama-3.3-70b-versatile".to_string());

        Self {
            host,
            port,
            groq_api_key,
            gemini_api_key,
            openai_api_key,
            nvidia_api_key,
            searxng_url,
            default_grounding_threshold,
            default_model,
        }
    }
}
