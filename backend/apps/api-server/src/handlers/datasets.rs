use axum::{
    Json,
    extract::{Path, State},
    http::StatusCode,
};
use serde_json::{Value, json};
use uuid::Uuid;

use crate::handlers::{ApiResult, api_error};
use crate::state::AppState;

pub async fn list(
    State(state): State<AppState>,
    axum::Extension(crate::middleware::WorkspaceAccess(workspace_id)): axum::Extension<
        crate::middleware::WorkspaceAccess,
    >,
) -> ApiResult<Json<Value>> {
    let datasets = sqlx::query!(
        "SELECT id, run_id, collection_id, name, entity_type, record_count, avg_confidence, created_at
         FROM datasets WHERE workspace_id = $1 ORDER BY created_at DESC LIMIT 50",
        workspace_id
    )
    .fetch_all(&state.db.pool)
    .await
    .map_err(|e| api_error(StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?;

    let data: Vec<Value> = datasets
        .iter()
        .map(|d| {
            json!({
                "id": d.id,
                "run_id": d.run_id,
                "collection_id": d.collection_id,
                "name": d.name,
                "entity_type": d.entity_type,
                "record_count": d.record_count,
                "avg_confidence": d.avg_confidence,
                "created_at": d.created_at,
            })
        })
        .collect();

    Ok(Json(json!({ "data": data, "total": data.len() })))
}

pub async fn get(State(state): State<AppState>, Path(id): Path<Uuid>) -> ApiResult<Json<Value>> {
    let ds = sqlx::query!(
        "SELECT id, run_id, collection_id, name, entity_type, record_count, avg_confidence,
                schema, created_at, updated_at
         FROM datasets WHERE id = $1",
        id
    )
    .fetch_optional(&state.db.pool)
    .await
    .map_err(|e| api_error(StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?
    .ok_or_else(|| api_error(StatusCode::NOT_FOUND, "dataset not found"))?;

    Ok(Json(json!({
        "id": ds.id,
        "run_id": ds.run_id,
        "collection_id": ds.collection_id,
        "name": ds.name,
        "entity_type": ds.entity_type,
        "record_count": ds.record_count,
        "avg_confidence": ds.avg_confidence,
        "schema": ds.schema,
        "created_at": ds.created_at,
        "updated_at": ds.updated_at,
    })))
}

pub async fn list_records(
    State(state): State<AppState>,
    Path(id): Path<Uuid>,
) -> ApiResult<Json<Value>> {
    let records = state
        .db
        .list_dataset_records(id)
        .await
        .map_err(|e| api_error(StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?;

    Ok(Json(json!({ "data": records, "total": records.len() })))
}

pub async fn export(
    State(state): State<AppState>,
    Path(id): Path<Uuid>,
) -> ApiResult<(StatusCode, Json<Value>)> {
    let export = sqlx::query!(
        "INSERT INTO exports (dataset_id, format, status)
         VALUES ($1, 'csv', 'pending')
         RETURNING id",
        id
    )
    .fetch_one(&state.db.pool)
    .await
    .map_err(|e| api_error(StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?;

    Ok((
        StatusCode::ACCEPTED,
        Json(json!({ "export_id": export.id, "status": "pending" })),
    ))
}

#[derive(serde::Deserialize)]
pub struct ExportQuery {
    #[serde(default = "csv_format")]
    format: String,
}

fn csv_format() -> String {
    "csv".into()
}

pub async fn download(
    State(state): State<AppState>,
    Path(id): Path<Uuid>,
    axum::extract::Query(query): axum::extract::Query<ExportQuery>,
) -> ApiResult<axum::response::Response> {
    use axum::response::IntoResponse;
    if !matches!(query.format.as_str(), "csv" | "json") {
        return Err(api_error(
            StatusCode::BAD_REQUEST,
            "format must be csv or json",
        ));
    }
    let records = state
        .db
        .list_dataset_records(id)
        .await
        .map_err(|e| api_error(StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?;
    let (content_type, body) = if query.format == "json" {
        (
            "application/json",
            serde_json::to_string_pretty(&records).unwrap_or_default(),
        )
    } else {
        fn cell(value: &str) -> String {
            format!("\"{}\"", value.replace('"', "\"\""))
        }
        let mut body = String::from(
            "canonical_name,status,confidence_score,attributes,confidence_breakdown\r\n",
        );
        for record in records {
            let value = serde_json::to_value(record).unwrap_or(Value::Null);
            let row = [
                value["canonical_name"].as_str().unwrap_or("").to_string(),
                value["status"].as_str().unwrap_or("").to_string(),
                value["confidence_score"].to_string(),
                value["primary_attributes"].to_string(),
                value["confidence_breakdown"].to_string(),
            ];
            body.push_str(&row.iter().map(|v| cell(v)).collect::<Vec<_>>().join(","));
            body.push_str("\r\n");
        }
        ("text/csv; charset=utf-8", body)
    };
    Ok((
        [
            (axum::http::header::CONTENT_TYPE, content_type.to_string()),
            (
                axum::http::header::CONTENT_DISPOSITION,
                format!("attachment; filename=\"dataset-{id}.{}\"", query.format),
            ),
        ],
        body,
    )
        .into_response())
}
