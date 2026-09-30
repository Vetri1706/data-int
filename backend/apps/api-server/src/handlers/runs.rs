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
                records_found, records_verified, avg_confidence, started_at, completed_at, error_message
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
    .map_err(|e| api_error(StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?;

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
        "error_message": run.error_message,
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

pub async fn list_runs(
    State(state): State<AppState>,
    Path(collection_id): Path<Uuid>,
) -> ApiResult<Json<Value>> {
    use sqlx::Row;
    let rows=sqlx::query("SELECT id,status,current_stage,records_found,records_verified,started_at,completed_at,error_message FROM workflow_runs WHERE collection_id=$1 ORDER BY started_at DESC")
        .bind(collection_id).fetch_all(&state.db.pool).await.map_err(|e|api_error(StatusCode::INTERNAL_SERVER_ERROR,e.to_string()))?;
    Ok(Json(
        json!({"data": rows.iter().map(|r|json!({"id":r.get::<Uuid,_>("id"),"collection_id":collection_id,
        "status":r.get::<String,_>("status"),"current_stage":r.get::<String,_>("current_stage"),
        "records_found":r.get::<i32,_>("records_found"),"records_verified":r.get::<i32,_>("records_verified"),
        "started_at":r.get::<chrono::DateTime<chrono::Utc>,_>("started_at"),"completed_at":r.get::<Option<chrono::DateTime<chrono::Utc>>,_>("completed_at"),
        "error_message":r.get::<Option<String>,_>("error_message")})).collect::<Vec<_>>()}),
    ))
}

pub async fn history(
    State(state): State<AppState>,
    Path(id): Path<Uuid>,
) -> ApiResult<Json<Value>> {
    use sqlx::Row;
    let rows = sqlx::query(
        "SELECT id,event_type,payload,created_at FROM run_events WHERE run_id=$1 ORDER BY id",
    )
    .bind(id)
    .fetch_all(&state.db.pool)
    .await
    .map_err(|e| api_error(StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?;
    let review: Vec<Value> = sqlx::query_scalar(
        "SELECT candidate FROM review_candidates WHERE run_id=$1 ORDER BY created_at",
    )
    .bind(id)
    .fetch_all(&state.db.pool)
    .await
    .map_err(|e| api_error(StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?;
    Ok(Json(
        json!({"data":rows.iter().map(|r|json!({"id":r.get::<i64,_>("id"),"type":r.get::<String,_>("event_type"),"payload":r.get::<Value,_>("payload"),"created_at":r.get::<chrono::DateTime<chrono::Utc>,_>("created_at")})).collect::<Vec<_>>(),"review_candidates":review}),
    ))
}

pub async fn pause() -> ApiResult<StatusCode> {
    Err(api_error(
        StatusCode::NOT_IMPLEMENTED,
        "Pause/resume is not supported. Cancel the run instead.",
    ))
}

pub async fn cancel(State(state): State<AppState>, Path(id): Path<Uuid>) -> ApiResult<Json<Value>> {
    let mut tx = state
        .db
        .pool
        .begin()
        .await
        .map_err(|e| api_error(StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?;
    let result: Option<Uuid> = sqlx::query_scalar("UPDATE workflow_runs SET status='cancelled',completed_at=NOW() WHERE id=$1 AND status NOT IN ('completed','partial','exhausted','failed','cancelled') RETURNING collection_id")
        .bind(id).fetch_optional(&mut *tx).await.map_err(|e|api_error(StatusCode::INTERNAL_SERVER_ERROR,e.to_string()))?;
    if let Some(collection) = result {
        sqlx::query("UPDATE collections SET status='cancelled',updated_at=NOW() WHERE id=$1 AND NOT EXISTS (SELECT 1 FROM workflow_runs WHERE collection_id=$1 AND id<>$2 AND (status IN ('pending','running') OR started_at > (SELECT started_at FROM workflow_runs WHERE id=$2)))")
            .bind(collection).bind(id).execute(&mut *tx).await.map_err(|e|api_error(StatusCode::INTERNAL_SERVER_ERROR,e.to_string()))?;
        sqlx::query("UPDATE workflow_steps SET status='cancelled',completed_at=NOW(),duration_ms=(EXTRACT(EPOCH FROM (NOW()-started_at))*1000)::int WHERE run_id=$1 AND status='running'")
            .bind(id).execute(&mut *tx).await.map_err(|e|api_error(StatusCode::INTERNAL_SERVER_ERROR,e.to_string()))?;
        sqlx::query(
            "INSERT INTO run_events (run_id,event_type,payload) VALUES ($1,'run.cancelled',$2)",
        )
        .bind(id)
        .bind(json!({"reason":"Cancelled by user"}))
        .execute(&mut *tx)
        .await
        .map_err(|e| api_error(StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?;
    } else {
        let status: Option<String> =
            sqlx::query_scalar("SELECT status FROM workflow_runs WHERE id=$1")
                .bind(id)
                .fetch_optional(&mut *tx)
                .await
                .map_err(|e| api_error(StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?;
        return status
            .map(|status| Json(json!({"status":status,"already_terminal":true})))
            .ok_or_else(|| api_error(StatusCode::NOT_FOUND, "run not found"));
    }
    tx.commit()
        .await
        .map_err(|e| api_error(StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?;
    // Persist first, so an in-flight completion cannot beat cancellation.
    let delivered = state
        .intel_client
        .post(format!("{}/runs/{id}/cancel", state.intel_base_url))
        .timeout(std::time::Duration::from_secs(6))
        .send()
        .await
        .is_ok_and(|r| r.status().is_success());
    Ok(Json(
        json!({"status":"cancelled","worker_notified":delivered}),
    ))
}
