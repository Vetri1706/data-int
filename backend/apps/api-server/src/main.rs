mod handlers;
mod middleware;
mod sse;
mod state;

use anyhow::Result;
use axum::{
    Router,
    routing::{delete, get, patch, post},
};
use datavault_auth::AuthService;
use datavault_storage::{Cache, Db};
use dotenvy::dotenv;
use sqlx::PgPool;
use std::env;
use tower_http::{
    compression::CompressionLayer,
    cors::{Any, CorsLayer},
    trace::TraceLayer,
};
use tracing::info;
use tracing_subscriber::{EnvFilter, layer::SubscriberExt, util::SubscriberInitExt};

#[tokio::main]
async fn main() -> Result<()> {
    dotenv().ok();

    // ── Tracing ───────────────────────────────────────────────────────────────
    tracing_subscriber::registry()
        .with(EnvFilter::try_from_default_env().unwrap_or_else(|_| "info,sqlx=warn".into()))
        .with(tracing_subscriber::fmt::layer().with_target(false))
        .init();

    // ── PostgreSQL ────────────────────────────────────────────────────────────
    let database_url = env::var("DATABASE_URL").expect("DATABASE_URL must be set");
    let pool = PgPool::connect(&database_url).await?;
    sqlx::raw_sql(include_str!(
        "../../../../migrations/002_trust_and_workflow.sql"
    ))
    .execute(&pool)
    .await?;
    info!("PostgreSQL connected");

    // ── Redis ─────────────────────────────────────────────────────────────────
    let redis_url = env::var("REDIS_URL").unwrap_or_else(|_| "redis://127.0.0.1:6379".into());
    let redis_cfg = deadpool_redis::Config::from_url(redis_url);
    let redis_pool = redis_cfg.create_pool(Some(deadpool_redis::Runtime::Tokio1))?;
    info!("Redis pool created");

    // ── App State ─────────────────────────────────────────────────────────────
    let db = Db::new(pool);
    let cache = Cache::new(redis_pool);
    let jwt_secret = env::var("JWT_SECRET").unwrap_or_else(|_| "changeme_dev_secret".into());
    let auth = AuthService::new(db.clone(), jwt_secret);
    let intelligence_url =
        env::var("INTELLIGENCE_URL").unwrap_or_else(|_| "http://127.0.0.1:7000".into());
    let searxng_url = env::var("SEARXNG_URL").unwrap_or_else(|_| "http://127.0.0.1:8888".into());

    let app_state = state::AppState::new(db, cache, auth, intelligence_url, searxng_url);

    // ── CORS ──────────────────────────────────────────────────────────────────
    let cors = CorsLayer::new()
        .allow_origin(Any)
        .allow_methods(Any)
        .allow_headers(Any);

    // ── Router ────────────────────────────────────────────────────────────────
    let protected = Router::new()
        // Workspaces
        .route("/workspaces", get(handlers::workspace::get_workspace))
        // Collections
        .route("/collections", get(handlers::collections::list))
        .route("/collections", post(handlers::collections::create))
        .route("/collections/{id}", get(handlers::collections::get))
        .route("/collections/{id}", patch(handlers::collections::update))
        .route("/collections/{id}", delete(handlers::collections::delete))
        .route(
            "/collections/{id}/run",
            post(handlers::collections::trigger_run),
        )
        // Runs
        .route("/collections/{id}/runs", get(handlers::runs::list_runs))
        .route("/runs/{id}", get(handlers::runs::get_run))
        .route("/runs/{id}/history", get(handlers::runs::history))
        .route("/runs/{id}/events", get(sse::sse_handler))
        .route("/runs/{id}/pause", post(handlers::runs::pause))
        .route("/runs/{id}/cancel", post(handlers::runs::cancel))
        // Datasets
        .route("/datasets", get(handlers::datasets::list))
        .route("/datasets/{id}", get(handlers::datasets::get))
        .route(
            "/datasets/{id}/records",
            get(handlers::datasets::list_records),
        )
        .route("/datasets/{id}/export", post(handlers::datasets::export))
        .route("/datasets/{id}/export", get(handlers::datasets::download))
        // Sources
        .route("/sources", get(handlers::sources::list))
        .route("/sources", post(handlers::sources::create))
        .route("/sources/{id}", patch(handlers::sources::update))
        // Settings
        .route("/me/preferences", get(handlers::users::get_preferences))
        .route("/me/models", get(handlers::users::get_models))
        .route(
            "/me/source-discovery",
            post(handlers::source_discovery::discover),
        )
        .route(
            "/me/preferences",
            patch(handlers::users::update_preferences),
        )
        .route_layer(axum::middleware::from_fn_with_state(
            app_state.clone(),
            middleware::require_workspace,
        ));

    let api = Router::new()
        .merge(protected)
        .route("/health", get(handlers::health::health))
        .route("/auth/register", post(handlers::auth::register))
        .route("/auth/login", post(handlers::auth::login))
        .route("/auth/me", get(handlers::auth::me))
        .route("/auth/logout", post(handlers::auth::logout))
        // Service-only routes are not exposed by the frontend API bridge.
        .route("/internal/search", post(handlers::internal::search))
        .route(
            "/internal/runs/{id}/control",
            get(handlers::internal::run_control),
        )
        .route(
            "/internal/intelligence/run",
            post(handlers::internal::intelligence_run),
        )
        .with_state(app_state);

    let app = Router::new()
        .nest("/v1", api)
        .layer(TraceLayer::new_for_http())
        .layer(cors)
        .layer(CompressionLayer::new());

    let host = env::var("HOST").unwrap_or_else(|_| "127.0.0.1".into());
    let port = env::var("PORT").unwrap_or_else(|_| "3000".into());
    let addr = format!("{host}:{port}").parse::<std::net::SocketAddr>()?;

    info!("Datavault API server listening on http://{addr}");
    let listener = tokio::net::TcpListener::bind(addr).await?;
    axum::serve(listener, app).await?;

    Ok(())
}
