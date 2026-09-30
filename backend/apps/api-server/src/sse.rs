use crate::state::AppState;
use axum::{
    extract::{Path, State},
    http::HeaderMap,
    response::Sse,
};
use futures_util::stream::Stream;
use serde_json::{Value, json};
use sqlx::Row;
use std::{convert::Infallible, time::Duration};
use uuid::Uuid;

/// Replay and stream the same persisted events, using an SSE cursor without duplicates.
pub async fn sse_handler(
    State(state): State<AppState>,
    Path(run_id): Path<Uuid>,
    headers: HeaderMap,
) -> Sse<impl Stream<Item = Result<axum::response::sse::Event, Infallible>>> {
    let mut last_id = headers
        .get("last-event-id")
        .and_then(|s| s.to_str().ok())
        .and_then(|s| s.parse::<i64>().ok())
        .unwrap_or(0);
    let stream = async_stream::stream! {
        loop {
            let rows=sqlx::query("SELECT id,event_type,payload,created_at FROM run_events WHERE run_id=$1 AND id>$2 ORDER BY id LIMIT 100")
                .bind(run_id).bind(last_id).fetch_all(&state.db.pool).await;
            if let Ok(events)=rows {
                for event in events {
                    last_id=event.get("id");
                    let kind: String=event.get("event_type");
                    let payload: Value=event.get("payload");
                    let data=json!({"type":kind,"payload":payload,"created_at":event.get::<chrono::DateTime<chrono::Utc>,_>("created_at")});
                    yield Ok(axum::response::sse::Event::default().id(last_id.to_string()).event("run_event").data(data.to_string()));
                    if matches!(kind.as_str(),"run.completed"|"run.partial"|"run.exhausted"|"run.failed"|"run.cancelled") { return; }
                }
            }
            tokio::time::sleep(Duration::from_secs(1)).await;
        }
    };
    Sse::new(stream)
        .keep_alive(axum::response::sse::KeepAlive::new().interval(Duration::from_secs(15)))
}
