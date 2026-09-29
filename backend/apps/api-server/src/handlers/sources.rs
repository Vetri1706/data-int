use axum::{Json, extract::State, http::StatusCode};
use serde_json::{Value, json};

use crate::handlers::{ApiResult, api_error};
use crate::state::AppState;

pub async fn list(
    State(state): State<AppState>,
    axum::Extension(crate::middleware::WorkspaceAccess(workspace_id)): axum::Extension<
        crate::middleware::WorkspaceAccess,
    >,
) -> ApiResult<Json<Value>> {
    let sources = sqlx::query!(
        "SELECT id, domain, display_name, source_type, trust_tier,
                extraction_success_rate, freshness_score, enabled, last_success_at, last_checked_at, last_status_code
         FROM sources WHERE workspace_id = $1 ORDER BY trust_tier, domain LIMIT 200", workspace_id
    )
    .fetch_all(&state.db.pool)
    .await
    .map_err(|e| api_error(StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?;

    let data: Vec<Value> = sources
        .iter()
        .map(|s| {
            json!({
                "id": s.id,
                "domain": s.domain,
                "display_name": s.display_name,
                "source_type": s.source_type,
                "trust_tier": s.trust_tier,
                "extraction_success_rate": s.extraction_success_rate,
                "freshness_score": s.freshness_score,
                "enabled": s.enabled,
                "last_success_at": s.last_success_at,
                "last_checked_at": s.last_checked_at,
                "last_status_code": s.last_status_code,
            })
        })
        .collect();

    Ok(Json(json!({ "data": data })))
}

#[derive(Debug, serde::Deserialize)]
pub struct CreateSourceRequest {
    pub domain: String,
    pub source_type: Option<String>,
    pub trust_tier: Option<String>,
}

pub async fn create(
    State(state): State<AppState>,
    axum::Extension(crate::middleware::WorkspaceAccess(workspace_id)): axum::Extension<
        crate::middleware::WorkspaceAccess,
    >,
    Json(body): Json<CreateSourceRequest>,
) -> ApiResult<(StatusCode, Json<Value>)> {
    let source = sqlx::query!(
        "INSERT INTO sources (domain, source_type, trust_tier, workspace_id)
         VALUES ($1, COALESCE($2, 'general'), COALESCE($3, 'tier2'), $4)
         RETURNING id, domain, source_type, trust_tier, enabled, created_at",
        body.domain,
        body.source_type,
        body.trust_tier,
        workspace_id,
    )
    .fetch_one(&state.db.pool)
    .await
    .map_err(|e| api_error(StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?;

    Ok((
        StatusCode::CREATED,
        Json(json!({
            "id": source.id,
            "domain": source.domain,
            "source_type": source.source_type,
            "trust_tier": source.trust_tier,
            "enabled": source.enabled,
        })),
    ))
}

pub async fn update(
    State(state): State<AppState>,
    axum::extract::Path(id): axum::extract::Path<uuid::Uuid>,
    Json(body): Json<serde_json::Value>,
) -> StatusCode {
    if let Some(enabled) = body.get("enabled").and_then(|v| v.as_bool()) {
        let _ = sqlx::query!(
            "UPDATE sources SET enabled = $1, updated_at = NOW() WHERE id = $2",
            enabled,
            id
        )
        .execute(&state.db.pool)
        .await;
    }
    StatusCode::NO_CONTENT
}
