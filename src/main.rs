mod config;
mod export;
mod models;
mod pipeline;
mod storage;

use axum::{
    extract::{Path, State},
    http::{header, HeaderMap, StatusCode},
    response::{Html, IntoResponse, Response},
    routing::{get, post},
    Json, Router,
};
use tower_http::cors::CorsLayer;
use tower_http::services::ServeDir;
use tracing::info;

use config::AppConfig;
use export::DatasetExporter;
use models::GroundingRequest;
use pipeline::GroundingPipeline;
use storage::TaskStore;

#[derive(Clone)]
pub struct AppState {
    pub config: AppConfig,
    pub store: TaskStore,
}

#[tokio::main]
async fn main() {
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| "info,tower_http=info".into()),
        )
        .init();

    let config = AppConfig::from_env();
    let store = TaskStore::new(100);

    let state = AppState {
        config: config.clone(),
        store,
    };

    let api_routes = Router::new()
        .route("/grounded-search", post(handle_grounded_search))
        .route("/ground", post(handle_grounded_search))
        .route("/ai-search", post(handle_grounded_search))
        .route("/internal/search", post(handle_internal_search))
        .route("/tasks", get(handle_get_tasks))
        .route("/tasks/{id}", get(handle_get_task_by_id))
        .route("/tasks/{id}/export/csv", get(handle_export_csv))
        .route("/tasks/{id}/export/json", get(handle_export_json));

    let app = Router::new()
        .route("/health", get(handle_health))
        .nest("/v1", api_routes)
        .nest_service("/static", ServeDir::new("static"))
        .fallback(handle_index_fallback)
        .layer(CorsLayer::permissive())
        .with_state(state);

    let addr = format!("{}:{}", config.host, config.port);
    info!("🚀 AI Data Intelligence Platform listening on http://{}", addr);

    let listener = tokio::net::TcpListener::bind(&addr).await.unwrap();
    axum::serve(listener, app).await.unwrap();
}

async fn handle_health() -> Json<serde_json::Value> {
    Json(serde_json::json!({
        "status": "healthy",
        "service": "AI Data Intelligence & Search Grounding Platform",
        "engine": "Rust (Axum + Tokio)",
        "version": "1.0.0"
    }))
}

async fn handle_grounded_search(
    State(state): State<AppState>,
    Json(payload): Json<GroundingRequest>,
) -> Response {
    if payload.prompt.trim().is_empty() {
        return (
            StatusCode::BAD_REQUEST,
            Json(serde_json::json!({ "error": "Prompt cannot be empty" })),
        )
            .into_response();
    }

    let response = GroundingPipeline::execute(payload, &state.config).await;

    // Persist to Task & Workflow History
    state.store.add_task(response.clone()).await;

    (StatusCode::OK, Json(response)).into_response()
}

async fn handle_get_tasks(State(state): State<AppState>) -> Response {
    let history = state.store.get_history().await;
    (StatusCode::OK, Json(history)).into_response()
}

async fn handle_get_task_by_id(
    State(state): State<AppState>,
    Path(id): Path<String>,
) -> Response {
    if let Some(task) = state.store.get_task_by_id(&id).await {
        (StatusCode::OK, Json(task)).into_response()
    } else {
        (
            StatusCode::NOT_FOUND,
            Json(serde_json::json!({ "error": "Task not found" })),
        )
            .into_response()
    }
}

async fn handle_export_csv(
    State(state): State<AppState>,
    Path(id): Path<String>,
) -> Response {
    if let Some(task) = state.store.get_task_by_id(&id).await {
        let csv = DatasetExporter::to_csv(&task.dataset);
        let mut headers = HeaderMap::new();
        headers.insert(header::CONTENT_TYPE, "text/csv; charset=utf-8".parse().unwrap());
        headers.insert(
            header::CONTENT_DISPOSITION,
            format!("attachment; filename=\"dataset-{}.csv\"", id).parse().unwrap(),
        );
        (StatusCode::OK, headers, csv).into_response()
    } else {
        (StatusCode::NOT_FOUND, "Task not found").into_response()
    }
}

async fn handle_export_json(
    State(state): State<AppState>,
    Path(id): Path<String>,
) -> Response {
    if let Some(task) = state.store.get_task_by_id(&id).await {
        let json_str = DatasetExporter::to_json(&task.dataset);
        let mut headers = HeaderMap::new();
        headers.insert(header::CONTENT_TYPE, "application/json".parse().unwrap());
        headers.insert(
            header::CONTENT_DISPOSITION,
            format!("attachment; filename=\"dataset-{}.json\"", id).parse().unwrap(),
        );
        (StatusCode::OK, headers, json_str).into_response()
    } else {
        (StatusCode::NOT_FOUND, "Task not found").into_response()
    }
}

#[derive(serde::Deserialize)]
pub struct InternalSearchQuery {
    pub query: String,
    pub limit: Option<usize>,
}

async fn handle_internal_search(
    State(state): State<AppState>,
    Json(payload): Json<InternalSearchQuery>,
) -> Response {
    let limit = payload.limit.unwrap_or(8);
    let results = pipeline::stage3_retriever::RetrieverStage::retrieve(&[payload.query], &state.config, limit).await;
    (StatusCode::OK, Json(results)).into_response()
}

async fn handle_index_fallback() -> Html<String> {
    match tokio::fs::read_to_string("static/index.html").await {
        Ok(content) => Html(content),
        Err(_) => Html("<h1>AI Data Intelligence Platform</h1><p>UI loading error. Check static directory.</p>".to_string()),
    }
}
