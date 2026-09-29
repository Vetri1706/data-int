use crate::handlers::{ApiResult, api_error};
use crate::middleware::extract_user;
use crate::state::AppState;
use axum::{Json, extract::State, http::StatusCode};
use serde_json::{Value, json};

/// Authenticated, read-only model availability. Never returns credentials.
pub async fn get_models(State(state): State<AppState>) -> ApiResult<Json<Value>> {
    let response = state
        .intel_client
        .get(format!("{}/models", state.intel_base_url))
        .timeout(std::time::Duration::from_secs(12))
        .send()
        .await
        .map_err(|_| {
            api_error(
                StatusCode::SERVICE_UNAVAILABLE,
                "Model service is unavailable. Retry shortly.",
            )
        })?
        .error_for_status()
        .map_err(|_| {
            api_error(
                StatusCode::SERVICE_UNAVAILABLE,
                "Cannot load available models.",
            )
        })?;
    Ok(Json(response.json().await.map_err(|_| {
        api_error(StatusCode::BAD_GATEWAY, "Invalid model catalog")
    })?))
}

pub async fn get_preferences(
    State(state): State<AppState>,
    axum_extra::extract::TypedHeader(auth): axum_extra::extract::TypedHeader<
        axum_extra::headers::Authorization<axum_extra::headers::authorization::Bearer>,
    >,
) -> ApiResult<Json<Value>> {
    let user = extract_user(&state, auth.token())
        .await
        .map_err(|_| api_error(StatusCode::UNAUTHORIZED, "invalid token"))?;

    let prefs = sqlx::query!(
        "SELECT default_target_count, default_freshness_days, preferred_regions,
                preferred_source_types, default_export_format, saved_categories, blocked_domains
         FROM user_preferences WHERE user_id = $1",
        user.id
    )
    .fetch_optional(&state.db.pool)
    .await
    .map_err(|e| api_error(StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?;

    if let Some(p) = prefs {
        Ok(Json(json!({
            "default_target_count": p.default_target_count,
            "default_freshness_days": p.default_freshness_days,
            "preferred_regions": p.preferred_regions,
            "preferred_source_types": p.preferred_source_types,
            "default_export_format": p.default_export_format,
            "saved_categories": p.saved_categories,
            "blocked_domains": p.blocked_domains,
        })))
    } else {
        // Return defaults
        Ok(Json(json!({
            "default_target_count": 100,
            "default_freshness_days": null,
            "preferred_regions": [],
            "preferred_source_types": [],
            "default_export_format": "csv",
            "saved_categories": [],
            "blocked_domains": [],
        })))
    }
}

pub async fn update_preferences(
    State(state): State<AppState>,
    axum_extra::extract::TypedHeader(auth): axum_extra::extract::TypedHeader<
        axum_extra::headers::Authorization<axum_extra::headers::authorization::Bearer>,
    >,
    Json(_body): Json<Value>,
) -> ApiResult<StatusCode> {
    let user = extract_user(&state, auth.token())
        .await
        .map_err(|_| api_error(StatusCode::UNAUTHORIZED, "invalid token"))?;

    sqlx::query!(
        "INSERT INTO user_preferences (user_id)
         VALUES ($1)
         ON CONFLICT (user_id) DO NOTHING",
        user.id
    )
    .execute(&state.db.pool)
    .await
    .map_err(|e| api_error(StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?;

    Ok(StatusCode::NO_CONTENT)
}
