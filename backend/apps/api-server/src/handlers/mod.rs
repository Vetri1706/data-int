pub mod auth;
pub mod collections;
pub mod datasets;
pub mod health;
pub mod internal;
pub mod runs;
pub mod source_discovery;
pub mod sources;
pub mod users;
pub mod workspace;

use axum::{
    Json,
    http::StatusCode,
    response::{IntoResponse, Response},
};
use serde_json::json;

/// Concrete API error type so Rust can always infer the `E` in `Result<T, E>`.
#[derive(Debug)]
pub struct ApiError(pub StatusCode, pub String);

impl IntoResponse for ApiError {
    fn into_response(self) -> Response {
        (self.0, Json(json!({ "error": self.1 }))).into_response()
    }
}

pub fn api_error(status: StatusCode, msg: impl Into<String>) -> ApiError {
    ApiError(status, msg.into())
}

pub fn err(status: StatusCode, msg: impl Into<String>) -> ApiError {
    ApiError(status, msg.into())
}

pub type ApiResult<T> = Result<T, ApiError>;
