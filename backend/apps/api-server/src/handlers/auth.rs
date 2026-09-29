use axum::{Json, extract::State, http::StatusCode};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

use crate::handlers::{ApiResult, api_error};
use crate::state::AppState;

// ─── /auth/register ───────────────────────────────────────────────────────────

#[derive(Debug, Deserialize)]
pub struct RegisterRequest {
    pub email: String,
    pub password: String,
    pub name: Option<String>,
}

#[derive(Debug, Serialize)]
pub struct AuthResponse {
    pub token: String,
    pub user: Value,
}

pub async fn register(
    State(state): State<AppState>,
    Json(body): Json<RegisterRequest>,
) -> ApiResult<(StatusCode, Json<AuthResponse>)> {
    let email = body.email.trim().to_lowercase();
    match state
        .auth
        .register(&email, body.name.as_deref().map(str::trim), &body.password)
        .await
    {
        Ok((user, token)) => {
            let resp = AuthResponse {
                token,
                user: json!({
                    "id": user.id,
                    "email": user.email,
                    "name": user.name,
                }),
            };
            // Ensure workspace exists
            if state
                .db
                .get_workspace_by_owner(user.id)
                .await
                .ok()
                .flatten()
                .is_none()
            {
                let slug = format!("workspace-{}", user.id);
                state
                    .db
                    .create_workspace(user.id, "My Workspace", &slug)
                    .await
                    .map_err(|_| {
                        api_error(
                            StatusCode::INTERNAL_SERVER_ERROR,
                            "Could not prepare your workspace. Please sign in again.",
                        )
                    })?;
            }
            Ok((StatusCode::CREATED, Json(resp)))
        }
        Err(e) => Err(api_error(StatusCode::BAD_REQUEST, e.to_string())),
    }
}

// ─── /auth/login ──────────────────────────────────────────────────────────────

#[derive(Debug, Deserialize)]
pub struct LoginRequest {
    pub email: String,
    pub password: String,
}

pub async fn login(
    State(state): State<AppState>,
    Json(body): Json<LoginRequest>,
) -> ApiResult<Json<AuthResponse>> {
    match state
        .auth
        .login(&body.email.trim().to_lowercase(), &body.password)
        .await
    {
        Ok((user, token)) => {
            if state
                .db
                .get_workspace_by_owner(user.id)
                .await
                .ok()
                .flatten()
                .is_none()
            {
                state
                    .db
                    .create_workspace(user.id, "My Workspace", &format!("workspace-{}", user.id))
                    .await
                    .map_err(|_| {
                        api_error(
                            StatusCode::INTERNAL_SERVER_ERROR,
                            "Could not prepare your workspace. Please try again.",
                        )
                    })?;
            }
            Ok(Json(AuthResponse {
                token,
                user: json!({ "id": user.id, "email": user.email, "name": user.name }),
            }))
        }
        Err(_) => Err(api_error(
            StatusCode::UNAUTHORIZED,
            "Email or password is incorrect.",
        )),
    }
}

// ─── /auth/me ─────────────────────────────────────────────────────────────────

pub async fn me(
    State(state): State<AppState>,
    axum_extra::extract::TypedHeader(auth): axum_extra::extract::TypedHeader<
        axum_extra::headers::Authorization<axum_extra::headers::authorization::Bearer>,
    >,
) -> ApiResult<Json<Value>> {
    match state.auth.authenticate(auth.token()).await {
        Ok(user) => Ok(Json(json!({
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "avatar_url": user.avatar_url,
        }))),
        Err(_) => Err(api_error(StatusCode::UNAUTHORIZED, "invalid token")),
    }
}

// ─── /auth/logout ─────────────────────────────────────────────────────────────

pub async fn logout(
    State(state): State<AppState>,
    axum_extra::extract::TypedHeader(auth): axum_extra::extract::TypedHeader<
        axum_extra::headers::Authorization<axum_extra::headers::authorization::Bearer>,
    >,
) -> ApiResult<StatusCode> {
    state.auth.logout(auth.token()).await.map_err(|_| {
        api_error(
            StatusCode::SERVICE_UNAVAILABLE,
            "Could not sign out. Please try again.",
        )
    })?;
    Ok(StatusCode::NO_CONTENT)
}
