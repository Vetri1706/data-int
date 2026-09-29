use axum::{
    Json,
    extract::{Path, State},
    http::StatusCode,
};
use serde_json::{Value, json};
use uuid::Uuid;

use crate::handlers::{ApiResult, api_error};
use crate::state::AppState;

pub async fn get_run(
    State(state): State<AppState>,
    Path(id): Path<Uuid>,
) -> ApiResult<Json<Value>> {
    let run = sqlx::query!(
        "SELECT id, collection_id, status, current_stage, iteration,
                records_found, records_verified, avg_confidence, started_at, completed_at
         FROM workflow_runs WHERE id = $1",
        id
    )
    .fetch_optional(&state.db.pool)
    .await
    .map_err(|e| api_error(StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?
    .ok_or_else(|| api_error(StatusCode::NOT_FOUND, "run not found"))?;

    // Fetch recent steps
    let steps = sqlx::query!(
        "SELECT id, step_type, status, duration_ms, metadata, started_at, completed_at
         FROM workflow_steps WHERE run_id = $1 ORDER BY started_at ASC LIMIT 100",
        id
    )
    .fetch_all(&state.db.pool)
    .await
    .unwrap_or_default();

    Ok(Json(json!({
        "id": run.id,
        "collection_id": run.collection_id,
        "status": run.status,
        "current_stage": run.current_stage,
        "iteration": run.iteration,
        "records_found": run.records_found,
        "records_verified": run.records_verified,
        "avg_confidence": run.avg_confidence,
        "started_at": run.started_at,
        "completed_at": run.completed_at,
        "steps": steps.iter().map(|s| json!({
            "id": s.id,
            "step_type": s.step_type,
            "status": s.status,
            "duration_ms": s.duration_ms,
            "metadata": s.metadata,
            "started_at": s.started_at,
            "completed_at": s.completed_at,
        })).collect::<Vec<_>>()
    })))
}

pub async fn pause(State(state): State<AppState>, Path(id): Path<Uuid>) -> StatusCode {
    let _ = sqlx::query!(
        "UPDATE workflow_runs SET status = 'paused' WHERE id = $1",
        id
    )
    .execute(&state.db.pool)
    .await;
    StatusCode::NO_CONTENT
}

pub async fn cancel(State(state): State<AppState>, Path(id): Path<Uuid>) -> StatusCode {
    let _ = sqlx::query!(
        "UPDATE workflow_runs SET status = 'cancelled', completed_at = NOW() WHERE id = $1",
        id
    )
    .execute(&state.db.pool)
    .await;
    StatusCode::NO_CONTENT
}
