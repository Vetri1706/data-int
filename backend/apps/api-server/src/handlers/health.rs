use axum::{Json, extract::State, http::StatusCode};
use serde_json::{Value, json};

use crate::state::AppState;

pub async fn health(State(state): State<AppState>) -> (StatusCode, Json<Value>) {
    let pg_ok = sqlx::query("SELECT 1")
        .fetch_one(&state.db.pool)
        .await
        .is_ok();
    let redis_ok = state.cache.get("__ping__").await.is_ok();

    let status = if pg_ok && redis_ok { StatusCode::OK } else { StatusCode::SERVICE_UNAVAILABLE };
    (status, Json(json!({
        "status": if pg_ok && redis_ok { "ok" } else { "degraded" },
        "services": {
            "postgres": if pg_ok { "up" } else { "down" },
            "redis":    if redis_ok { "up" } else { "down" }
        }
    })))
}
