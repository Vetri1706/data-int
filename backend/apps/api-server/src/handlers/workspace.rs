use crate::handlers::{ApiResult, api_error};
use crate::middleware::extract_user;
use crate::state::AppState;
use axum::{Json, extract::State, http::StatusCode};
use serde_json::{Value, json};

pub async fn get_workspace(
    State(state): State<AppState>,
    axum_extra::extract::TypedHeader(auth): axum_extra::extract::TypedHeader<
        axum_extra::headers::Authorization<axum_extra::headers::authorization::Bearer>,
    >,
) -> ApiResult<Json<Value>> {
    let user = extract_user(&state, auth.token())
        .await
        .map_err(|_| api_error(StatusCode::UNAUTHORIZED, "invalid token"))?;

    let ws = state
        .db
        .get_workspace_by_owner(user.id)
        .await
        .map_err(|e| api_error(StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?
        .ok_or_else(|| api_error(StatusCode::NOT_FOUND, "workspace not found"))?;

    Ok(Json(json!({
        "id": ws.id,
        "name": ws.name,
        "slug": ws.slug,
        "plan": ws.plan,
        "created_at": ws.created_at,
    })))
}
