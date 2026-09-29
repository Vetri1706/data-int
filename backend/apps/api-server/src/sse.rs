use axum::{
    extract::{Path, State},
    response::Sse,
};
use futures_util::stream::Stream;
use serde_json::json;
use std::{convert::Infallible, time::Duration};
use uuid::Uuid;

use crate::state::AppState;

/// GET /v1/runs/:id/events — SSE endpoint for live workflow progress
///
/// Streams:
///   - Buffered historical events from run_events table (catch-up)
///   - Live events via Redis pub/sub subscription
pub async fn sse_handler(
    State(state): State<AppState>,
    Path(run_id): Path<Uuid>,
) -> Sse<impl Stream<Item = Result<axum::response::sse::Event, Infallible>>> {
    let db = state.db.clone();

    let stream = async_stream::stream! {
        // ── 1. Send catch-up events from Postgres ─────────────────────────
        if let Ok(history) = sqlx::query!(
            "SELECT event_type, payload, created_at
             FROM run_events
             WHERE run_id = $1
             ORDER BY created_at ASC
             LIMIT 200",
            run_id
        )
        .fetch_all(&db.pool)
        .await
        {
            for ev in history {
                let data = json!({
                    "type":       ev.event_type,
                    "payload":    ev.payload,
                    "created_at": ev.created_at,
                });
                yield Ok::<_, Infallible>(
                    axum::response::sse::Event::default()
                        .event("run_event")
                        .data(data.to_string())
                );
            }
        }

        // ── 2. Subscribe to Redis pub/sub for live events ─────────────────
        // We poll the latest event from the DB every 2 seconds as a
        // simple polling bridge. For production, upgrade to a real
        // Redis pub/sub subscriber via the `redis` async client.
        let mut last_id: i64 = 0;
        loop {
            tokio::time::sleep(Duration::from_secs(2)).await;

            let rows = sqlx::query!(
                "SELECT id, event_type, payload, created_at
                 FROM run_events
                 WHERE run_id = $1 AND id > $2
                 ORDER BY id ASC
                 LIMIT 50",
                run_id,
                last_id,
            )
            .fetch_all(&db.pool)
            .await;

            match rows {
                Ok(evs) if !evs.is_empty() => {
                    for ev in &evs {
                        last_id = ev.id;
                        let data = json!({
                            "type":    ev.event_type,
                            "payload": ev.payload,
                        });
                        yield Ok::<_, Infallible>(
                            axum::response::sse::Event::default()
                                .event("run_event")
                                .data(data.to_string())
                        );

                        // Stop streaming if run terminal
                        if ev.event_type == "run.completed" || ev.event_type == "run.failed" {
                            return;
                        }
                    }
                }
                _ => {
                    // Heartbeat keep-alive
                    yield Ok::<_, Infallible>(
                        axum::response::sse::Event::default()
                            .comment("heartbeat")
                    );
                }
            }
        }
    };

    Sse::new(stream).keep_alive(
        axum::response::sse::KeepAlive::new()
            .interval(Duration::from_secs(30))
            .text("ping"),
    )
}
