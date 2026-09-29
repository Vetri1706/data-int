use crate::handlers::{ApiResult, api_error};
use crate::state::AppState;
use axum::{
    extract::{Request, State},
    http::StatusCode,
    middleware::Next,
    response::Response,
};
use datavault_domain::User;
use uuid::Uuid;

#[derive(Clone, Copy)]
pub struct WorkspaceAccess(pub Uuid);

/// All product endpoints require a live session and the owner's workspace.
/// Resource checks happen before handlers, including downloads and SSE.
pub async fn require_workspace(
    State(state): State<AppState>,
    mut request: Request,
    next: Next,
) -> ApiResult<Response> {
    let token = request
        .headers()
        .get("authorization")
        .and_then(|h| h.to_str().ok())
        .and_then(|h| h.strip_prefix("Bearer "))
        .ok_or_else(|| api_error(StatusCode::UNAUTHORIZED, "Sign in to continue."))?;
    let user = state.auth.authenticate(token).await.map_err(|_| {
        api_error(
            StatusCode::UNAUTHORIZED,
            "Your session has expired. Please sign in again.",
        )
    })?;
    let ws = state
        .db
        .get_workspace_by_owner(user.id)
        .await
        .map_err(|_| {
            api_error(
                StatusCode::SERVICE_UNAVAILABLE,
                "Workspace is temporarily unavailable.",
            )
        })?
        .ok_or_else(|| api_error(StatusCode::NOT_FOUND, "Workspace not found."))?;
    let path = request.uri().path().trim_start_matches('/');
    let path = path.strip_prefix("v1/").unwrap_or(path);
    let mut segments = path.split('/');
    let resource = segments.next().unwrap_or_default();
    if let Some(id) = segments
        .next()
        .filter(|_| matches!(resource, "collections" | "datasets" | "runs" | "sources"))
    {
        let id = Uuid::parse_str(id)
            .map_err(|_| api_error(StatusCode::NOT_FOUND, "Resource not found."))?;
        let query = match resource {
            "collections" => {
                "SELECT EXISTS(SELECT 1 FROM collections WHERE id = $1 AND workspace_id = $2)"
            }
            "datasets" => {
                "SELECT EXISTS(SELECT 1 FROM datasets WHERE id = $1 AND workspace_id = $2)"
            }
            "sources" => "SELECT EXISTS(SELECT 1 FROM sources WHERE id = $1 AND workspace_id = $2)",
            _ => {
                "SELECT EXISTS(SELECT 1 FROM workflow_runs r JOIN collections c ON c.id = r.collection_id WHERE r.id = $1 AND c.workspace_id = $2)"
            }
        };
        let allowed: bool = sqlx::query_scalar(query)
            .bind(id)
            .bind(ws.id)
            .fetch_one(&state.db.pool)
            .await
            .map_err(|_| {
                api_error(
                    StatusCode::SERVICE_UNAVAILABLE,
                    "Could not check access. Please retry.",
                )
            })?;
        if !allowed {
            return Err(api_error(StatusCode::NOT_FOUND, "Resource not found."));
        }
    }
    request.extensions_mut().insert(WorkspaceAccess(ws.id));
    Ok(next.run(request).await)
}

/// Helper: extract authenticated user from Bearer token
pub async fn extract_user(state: &AppState, token: &str) -> anyhow::Result<User> {
    state.auth.authenticate(token).await
}
