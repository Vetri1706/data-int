use axum::{Json, extract::State, http::StatusCode};
use datavault_domain::SearchRequest;
use serde::Deserialize;
use serde_json::{Value, json};
use uuid::Uuid;

use crate::handlers::{ApiResult, api_error};
use crate::state::AppState;

/// POST /v1/internal/search
/// Called by the LangGraph intelligence service when it needs search results.
#[derive(Debug, Deserialize)]
pub struct InternalSearchRequest {
    pub query: String,
    pub max_results: Option<usize>,
    pub domain_filters: Option<Vec<String>>,
    pub freshness_days: Option<u32>,
    pub model_config: Option<Value>,
}

pub async fn search(
    State(state): State<AppState>,
    Json(body): Json<InternalSearchRequest>,
) -> ApiResult<Json<Value>> {
    let req = SearchRequest {
        query: body.query,
        max_results: body.max_results.unwrap_or(10),
        domain_filters: body.domain_filters.unwrap_or_default(),
        freshness_days: body.freshness_days,
        model_config: body.model_config,
    };

    let results = state
        .search
        .search(req)
        .await
        .map_err(|e| api_error(StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?;

    Ok(Json(json!({ "results": results, "total": results.len() })))
}

/// POST /v1/internal/intelligence/run
/// Webhook called by LangGraph to update run progress / write records
#[derive(Debug, Deserialize)]
pub struct RunUpdatePayload {
    pub run_id: Uuid,
    pub event_type: String,
    pub stage: Option<String>,
    pub progress: Option<i32>,
    pub records_found: Option<i32>,
    pub records_verified: Option<i32>,
    pub avg_confidence: Option<f32>,
    pub error: Option<String>,
    pub payload: Option<Value>,
}

pub async fn intelligence_run(
    State(state): State<AppState>,
    Json(body): Json<RunUpdatePayload>,
) -> ApiResult<Json<Value>> {
    use sqlx::Row;
    let db_error =
        |error: sqlx::Error| api_error(StatusCode::INTERNAL_SERVER_ERROR, error.to_string());
    let mut tx = state.db.pool.begin().await.map_err(db_error)?;
    let run = sqlx::query("SELECT r.collection_id, c.workspace_id, c.title, c.data_contract FROM workflow_runs r JOIN collections c ON c.id = r.collection_id WHERE r.id = $1 FOR UPDATE OF r")
        .bind(body.run_id).fetch_optional(&mut *tx).await.map_err(db_error)?
        .ok_or_else(|| api_error(StatusCode::NOT_FOUND, "run not found"))?;
    let collection_id: Uuid = run.try_get("collection_id").map_err(db_error)?;
    let workspace_id: Uuid = run.try_get("workspace_id").map_err(db_error)?;
    let title: String = run.try_get("title").map_err(db_error)?;
    let contract: Value = run.try_get("data_contract").map_err(db_error)?;
    let payload = body.payload.clone().unwrap_or(json!({}));

    // Publish completion only after records and provenance commit successfully.
    // Locking the run also makes repeated completion callbacks idempotent.
    if body.event_type == "run.completed" {
        let records = payload
            .get("records")
            .and_then(Value::as_array)
            .filter(|rows| !rows.is_empty())
            .ok_or_else(|| {
                api_error(
                    StatusCode::UNPROCESSABLE_ENTITY,
                    "completion requires evidence records",
                )
            })?;
        let existing: Option<Uuid> =
            sqlx::query_scalar("SELECT id FROM datasets WHERE run_id = $1 LIMIT 1")
                .bind(body.run_id)
                .fetch_optional(&mut *tx)
                .await
                .map_err(db_error)?;
        if existing.is_none() {
            let entity_type = contract
                .get("entity_type")
                .and_then(Value::as_str)
                .unwrap_or("entity");
            let dataset_id: Uuid = sqlx::query_scalar("INSERT INTO datasets (collection_id, run_id, workspace_id, name, entity_type, record_count, avg_confidence, schema) VALUES ($1,$2,$3,$4,$5,$6,$7,$8) RETURNING id")
                .bind(collection_id).bind(body.run_id).bind(workspace_id)
                .bind(format!("{title} — Dataset")).bind(entity_type).bind(records.len() as i32)
                .bind(body.avg_confidence).bind(&contract)
                .fetch_one(&mut *tx).await.map_err(db_error)?;
            for record in records {
                let name = record
                    .get("canonical_name")
                    .and_then(Value::as_str)
                    .filter(|name| !name.trim().is_empty())
                    .ok_or_else(|| {
                        api_error(
                            StatusCode::UNPROCESSABLE_ENTITY,
                            "record is missing its canonical name",
                        )
                    })?;
                let score = record
                    .get("confidence_score")
                    .and_then(Value::as_f64)
                    .unwrap_or(0.)
                    .clamp(0., 1.) as f32;
                let status = record
                    .get("status")
                    .and_then(Value::as_str)
                    .unwrap_or("draft");
                let breakdown = record
                    .get("confidence_breakdown")
                    .cloned()
                    .unwrap_or(json!({}));
                sqlx::query("INSERT INTO dataset_records (dataset_id, canonical_name, status, confidence_score, confidence_breakdown, primary_attributes) VALUES ($1,$2,$3,$4,$5,$6)")
                    .bind(dataset_id).bind(name).bind(status).bind(score).bind(breakdown).bind(record)
                    .execute(&mut *tx).await.map_err(db_error)?;
            }
            if let Some(sources) = payload.get("sources").and_then(Value::as_array) {
                for source in sources {
                    let Some(url) = source
                        .get("url")
                        .and_then(Value::as_str)
                        .and_then(|u| url::Url::parse(u).ok())
                    else {
                        continue;
                    };
                    let Some(domain) = url.host_str() else {
                        continue;
                    };
                    let status = source
                        .get("http_status")
                        .and_then(Value::as_i64)
                        .map(|s| s as i32);
                    let source_title = source
                        .get("title")
                        .and_then(Value::as_str)
                        .unwrap_or(domain);
                    sqlx::query("INSERT INTO sources (workspace_id, domain, display_name, last_status_code, last_checked_at, last_success_at) VALUES ($1,$2,$3,$4,NOW(),CASE WHEN $4 = 200 THEN NOW() ELSE NULL END) ON CONFLICT (workspace_id, domain) DO UPDATE SET display_name = EXCLUDED.display_name, last_status_code = EXCLUDED.last_status_code, last_checked_at = NOW(), last_success_at = EXCLUDED.last_success_at, updated_at = NOW()")
                        .bind(workspace_id).bind(domain).bind(source_title).bind(status)
                        .execute(&mut *tx).await.map_err(db_error)?;
                }
            }
        }
    }
    sqlx::query("UPDATE workflow_runs SET current_stage = COALESCE($2, current_stage), records_found = COALESCE($3, records_found), records_verified = COALESCE($4, records_verified), avg_confidence = COALESCE($5, avg_confidence), error_message = COALESCE($6, error_message), status = CASE WHEN $7 = 'run.completed' THEN 'completed' WHEN $7 = 'run.failed' THEN 'failed' ELSE status END, completed_at = CASE WHEN $7 IN ('run.completed', 'run.failed') THEN NOW() ELSE completed_at END WHERE id = $1")
        .bind(body.run_id).bind(&body.stage).bind(body.records_found).bind(body.records_verified)
        .bind(body.avg_confidence).bind(&body.error).bind(&body.event_type)
        .execute(&mut *tx).await.map_err(db_error)?;
    if matches!(body.event_type.as_str(), "run.completed" | "run.failed") {
        let status = if body.event_type == "run.completed" {
            "completed"
        } else {
            "failed"
        };
        sqlx::query("UPDATE collections SET status = $1, updated_at = NOW() WHERE id = $2")
            .bind(status)
            .bind(collection_id)
            .execute(&mut *tx)
            .await
            .map_err(db_error)?;
    }
    sqlx::query("INSERT INTO run_events (run_id, event_type, payload) VALUES ($1,$2,$3)")
        .bind(body.run_id)
        .bind(&body.event_type)
        .bind(&payload)
        .execute(&mut *tx)
        .await
        .map_err(db_error)?;
    tx.commit().await.map_err(db_error)?;

    let event_json = json!({
        "type": body.event_type, "stage": body.stage, "progress": body.progress,
        "records_found": body.records_found, "records_verified": body.records_verified,
        "avg_confidence": body.avg_confidence,
    })
    .to_string();
    let _ = state
        .cache
        .publish_run_event(body.run_id, &event_json)
        .await;
    Ok(Json(json!({ "ok": true })))
}
