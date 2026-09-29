use axum::{Json, extract::State};
use serde_json::{Value, json};

use crate::state::AppState;

pub async fn health(State(state): State<AppState>) -> Json<Value> {
    let pg_ok = sqlx::query("SELECT 1")
        .fetch_one(&state.db.pool)
        .await
        .is_ok();
    let redis_ok = state.cache.get("__ping__").await.is_ok();

    Json(json!({
        "status": if pg_ok && redis_ok { "ok" } else { "degraded" },
        "services": {
            "postgres": if pg_ok { "up" } else { "down" },
            "redis":    if redis_ok { "up" } else { "down" }
        }
    }))
}
