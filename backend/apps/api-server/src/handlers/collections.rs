use axum::{
    Json,
    extract::{Path, State},
    http::StatusCode,
};
use serde::Deserialize;
use serde_json::json;
use uuid::Uuid;

use crate::handlers::{ApiError, err};
use crate::state::AppState;

type ApiResult<T> = Result<T, ApiError>;

// ─── List collections ─────────────────────────────────────────────────────────

pub async fn list(
    State(state): State<AppState>,
    axum_extra::extract::TypedHeader(auth): axum_extra::extract::TypedHeader<
        axum_extra::headers::Authorization<axum_extra::headers::authorization::Bearer>,
    >,
) -> ApiResult<Json<serde_json::Value>> {
    let user = state
        .auth
        .authenticate(auth.token())
        .await
        .map_err(|_| err(StatusCode::UNAUTHORIZED, "invalid token"))?;

    let ws = state
        .db
        .get_workspace_by_owner(user.id)
        .await
        .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?
        .ok_or_else(|| err(StatusCode::NOT_FOUND, "workspace not found"))?;

    let cols = state
        .db
        .list_collections(ws.id)
        .await
        .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?;

    let total = cols.len();
    Ok(Json(json!({ "data": cols, "total": total })))
}

// ─── Get collection ───────────────────────────────────────────────────────────

pub async fn get(
    State(state): State<AppState>,
    Path(id): Path<Uuid>,
    axum_extra::extract::TypedHeader(auth): axum_extra::extract::TypedHeader<
        axum_extra::headers::Authorization<axum_extra::headers::authorization::Bearer>,
    >,
) -> ApiResult<Json<serde_json::Value>> {
    let _user = state
        .auth
        .authenticate(auth.token())
        .await
        .map_err(|_| err(StatusCode::UNAUTHORIZED, "invalid token"))?;

    let col = state
        .db
        .get_collection(id)
        .await
        .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?
        .ok_or_else(|| err(StatusCode::NOT_FOUND, "not found"))?;

    Ok(Json(json!(col)))
}

// ─── Create collection ────────────────────────────────────────────────────────

#[derive(Debug, Deserialize)]
pub struct CreateCollectionRequest {
    pub title: String,
    pub prompt: String,
    pub tags: Option<Vec<String>>,
    pub model_selection: Option<serde_json::Value>,
}

pub async fn create(
    State(state): State<AppState>,
    axum_extra::extract::TypedHeader(auth): axum_extra::extract::TypedHeader<
        axum_extra::headers::Authorization<axum_extra::headers::authorization::Bearer>,
    >,
    Json(body): Json<CreateCollectionRequest>,
) -> ApiResult<(StatusCode, Json<serde_json::Value>)> {
    let user = state
        .auth
        .authenticate(auth.token())
        .await
        .map_err(|_| err(StatusCode::UNAUTHORIZED, "invalid token"))?;

    let ws = state
        .db
        .get_workspace_by_owner(user.id)
        .await
        .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?
        .ok_or_else(|| err(StatusCode::NOT_FOUND, "workspace not found"))?;

    // Ask LangGraph to parse the requirement into a DataContract
    let contract = call_intelligence_parse(&state, &body.prompt, body.model_selection.as_ref())
        .await
        .map_err(|e| err(StatusCode::UNPROCESSABLE_ENTITY, e.to_string()))?;

    let col = state
        .db
        .create_collection(ws.id, user.id, &body.title, &body.prompt, &contract)
        .await
        .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?;

    Ok((StatusCode::CREATED, Json(json!(col))))
}

// ─── Update collection ────────────────────────────────────────────────────────

#[derive(Debug, Deserialize)]
pub struct UpdateCollectionRequest {
    pub title: Option<String>,
    pub tags: Option<Vec<String>>,
    pub status: Option<String>,
}

pub async fn update(
    State(state): State<AppState>,
    Path(id): Path<Uuid>,
    axum::Extension(crate::middleware::WorkspaceAccess(workspace_id)): axum::Extension<
        crate::middleware::WorkspaceAccess,
    >,
    Json(body): Json<UpdateCollectionRequest>,
) -> ApiResult<Json<serde_json::Value>> {
    let col = state
        .db
        .get_collection(id)
        .await
        .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?
        .ok_or_else(|| err(StatusCode::NOT_FOUND, "collection not found"))?;

    if col.workspace_id != workspace_id {
        return Err(err(StatusCode::FORBIDDEN, "forbidden"));
    }

    let updated_title = body.title.unwrap_or(col.title);
    let updated_tags = body.tags.unwrap_or(col.tags);
    let updated_status = body.status.unwrap_or_else(|| col.status.to_string());

    let updated = sqlx::query_as!(
        datavault_domain::Collection,
        "UPDATE collections
         SET title = $1, tags = $2, status = $3, updated_at = NOW()
         WHERE id = $4 AND workspace_id = $5
         RETURNING id, workspace_id, created_by, title, prompt, status,
                   data_contract, tags, created_at, updated_at",
        updated_title,
        &updated_tags,
        updated_status,
        id,
        workspace_id,
    )
    .fetch_one(&state.db.pool)
    .await
    .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?;

    Ok(Json(json!(updated)))
}

// ─── Delete collection ────────────────────────────────────────────────────────

pub async fn delete(
    State(state): State<AppState>,
    Path(id): Path<Uuid>,
    axum::Extension(crate::middleware::WorkspaceAccess(workspace_id)): axum::Extension<
        crate::middleware::WorkspaceAccess,
    >,
) -> ApiResult<StatusCode> {
    let result = sqlx::query!(
        "DELETE FROM collections WHERE id = $1 AND workspace_id = $2",
        id,
        workspace_id,
    )
    .execute(&state.db.pool)
    .await
    .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?;

    if result.rows_affected() == 0 {
        return Err(err(StatusCode::NOT_FOUND, "collection not found"));
    }

    Ok(StatusCode::NO_CONTENT)
}

// ─── Trigger run ──────────────────────────────────────────────────────────────

pub async fn trigger_run(
    State(state): State<AppState>,
    Path(id): Path<Uuid>,
    axum_extra::extract::TypedHeader(auth): axum_extra::extract::TypedHeader<
        axum_extra::headers::Authorization<axum_extra::headers::authorization::Bearer>,
    >,
) -> ApiResult<(StatusCode, Json<serde_json::Value>)> {
    let user = state
        .auth
        .authenticate(auth.token())
        .await
        .map_err(|_| err(StatusCode::UNAUTHORIZED, "invalid token"))?;

    let col = state
        .db
        .get_collection(id)
        .await
        .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?
        .ok_or_else(|| err(StatusCode::NOT_FOUND, "collection not found"))?;

    // Create workflow run record
    let run = sqlx::query!(
        "INSERT INTO workflow_runs (collection_id, triggered_by, status, current_stage)
         VALUES ($1, $2, 'pending', 'planning')
         RETURNING id, status, started_at",
        col.id,
        user.id,
    )
    .fetch_one(&state.db.pool)
    .await
    .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?;

    // Update collection status
    let _ = state
        .db
        .update_collection_status(id, &datavault_domain::CollectionStatus::Running)
        .await;

    // Fire-and-forget: delegate to LangGraph
    let intel_url = state.intel_base_url.clone();
    let client = state.intel_client.clone();
    let run_id = run.id;
    let prompt = col.prompt.clone();
    let contract = col.data_contract.clone();
    let pool = state.db.pool.clone();

    tokio::spawn(async move {
        let accepted = client
            .post(format!("{intel_url}/run"))
            .json(&json!({
                "run_id":        run_id,
                "prompt":        prompt,
                "data_contract": contract,
            }))
            .send()
            .await
            .is_ok_and(|response| response.status().is_success());
        if !accepted {
            let _ = sqlx::query(
                "UPDATE workflow_runs SET status = 'failed', completed_at = NOW() WHERE id = $1",
            )
            .bind(run_id)
            .execute(&pool)
            .await;
            let _ = sqlx::query(
                "UPDATE collections SET status = 'failed', updated_at = NOW() WHERE id = $1",
            )
            .bind(id)
            .execute(&pool)
            .await;
        }
    });

    Ok((
        StatusCode::ACCEPTED,
        Json(json!({ "run_id": run.id, "status": "pending" })),
    ))
}

// ─── Internal: parse prompt via LangGraph ─────────────────────────────────────

async fn call_intelligence_parse(
    state: &AppState,
    prompt: &str,
    model_selection: Option<&serde_json::Value>,
) -> anyhow::Result<serde_json::Value> {
    let resp = state
        .intel_client
        .post(format!("{}/parse", state.intel_base_url))
        .json(&json!({ "prompt": prompt, "model_selection": model_selection }))
        .timeout(std::time::Duration::from_secs(58))
        .send()
        .await?;

    if resp.status().is_success() {
        Ok(resp.json().await?)
    } else {
        let error: serde_json::Value = resp.json().await.unwrap_or_default();
        anyhow::bail!(
            "{}",
            error["detail"]
                .as_str()
                .unwrap_or("Model service unavailable. Check the selected provider and retry.")
        )
    }
}
