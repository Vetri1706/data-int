use axum::{Json, extract::State, http::StatusCode};
use datavault_domain::SearchRequest;
use serde::Deserialize;
use serde_json::{Value, json};
use uuid::Uuid;

use crate::handlers::{ApiResult, api_error};
use crate::state::AppState;

/// POST /v1/internal/search
/// Called by the LangGraph intelligence service when it needs search results.
#[derive(Debug, Deserialize)]
pub struct InternalSearchRequest {
    pub query: String,
    pub max_results: Option<usize>,
    pub domain_filters: Option<Vec<String>>,
    pub freshness_days: Option<u32>,
    pub model_config: Option<Value>,
}

pub async fn search(
    State(state): State<AppState>,
    Json(body): Json<InternalSearchRequest>,
) -> ApiResult<Json<Value>> {
    let req = SearchRequest {
        query: body.query,
        max_results: body.max_results.unwrap_or(10),
        domain_filters: body.domain_filters.unwrap_or_default(),
        freshness_days: body.freshness_days,
        model_config: body.model_config,
    };

    let results = state
        .search
        .search(req)
        .await
        .map_err(|e| api_error(StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?;

    Ok(Json(json!({ "results": results, "total": results.len() })))
}

/// POST /v1/internal/intelligence/run
/// Webhook called by LangGraph to update run progress / write records
#[derive(Debug, Deserialize)]
pub struct RunUpdatePayload {
    pub run_id: Uuid,
    pub event_type: String,
    pub stage: Option<String>,
    pub progress: Option<i32>,
    pub records_found: Option<i32>,
    pub records_verified: Option<i32>,
    pub error: Option<String>,
    pub payload: Option<Value>,
}

fn terminal(status: &str) -> bool {
    matches!(
        status,
        "completed" | "partial" | "exhausted" | "failed" | "cancelled"
    )
}

pub fn accepted_record(record: &Value, contract: &Value) -> bool {
    if record["accepted"] != true
        || record["verification"]["accepted"] != true
        || record["verification"]["version"] != "typed-claims-v1"
        || record["status"] != "verified"
        || record["canonical_name"]
            .as_str()
            .is_none_or(|v| v.trim().is_empty())
    {
        return false;
    }
    let Some(fields) = contract["fields"].as_array().filter(|f| !f.is_empty()) else {
        return false;
    };
    let Some(claims) = record["claims"].as_object() else {
        return false;
    };
    if record["verification"]["acceptance_failures"]
        .as_array()
        .is_none_or(|v| !v.is_empty())
    {
        return false;
    }
    let mut supported = 0;
    for field in fields {
        let Some(name) = field["name"].as_str() else {
            return false;
        };
        let Some(claim) = claims.get(name) else {
            return false;
        };
        let is_supported = claim["state"] == "supported";
        let hard = contract["constraints"].as_array().is_some_and(|cs| {
            cs.iter()
                .any(|c| c["is_hard"] == true && c["field"] == name)
        });
        if (field["required"] == true || hard) && !is_supported {
            return false;
        }
        if is_supported {
            supported += 1;
            if record[name] != claim["value"] || record[name].is_null() {
                return false;
            }
            if claim["evidence"].as_array().is_none_or(|es| {
                !es.iter().any(|e| {
                    e["state"] == "supported"
                        && e["verbatim_quote"].as_str().is_some_and(|q| !q.is_empty())
                        && e["chunk_id"].as_str().is_some_and(|q| !q.is_empty())
                        && e["source_url"].as_str().is_some_and(|u| {
                            url::Url::parse(u).is_ok_and(|u| {
                                matches!(u.scheme(), "http" | "https") && u.host_str().is_some()
                            })
                        })
                        && e["content_sha256"].as_str().is_some_and(|h| {
                            h.len() == 64 && h.bytes().all(|c| c.is_ascii_hexdigit())
                        })
                        && e["char_start"]
                            .as_u64()
                            .zip(e["char_end"].as_u64())
                            .is_some_and(|(a, b)| b > a)
                })
            }) {
                return false;
            }
            if claim["evidence"]
                .as_array()
                .is_some_and(|es| es.iter().any(|e| e["state"] == "contradicted"))
            {
                return false;
            }
        } else if !record[name].is_null() {
            return false;
        }
    }
    supported > 0
        && record["verification"]["field_coverage"]
            .as_f64()
            .is_some_and(|coverage| {
                (coverage - supported as f64 / fields.len() as f64).abs() < 0.000001
            })
}

pub async fn intelligence_run(
    State(state): State<AppState>,
    Json(body): Json<RunUpdatePayload>,
) -> ApiResult<Json<Value>> {
    use sqlx::Row;
    let db_error = |e: sqlx::Error| api_error(StatusCode::INTERNAL_SERVER_ERROR, e.to_string());
    let mut tx = state.db.pool.begin().await.map_err(db_error)?;
    let run = sqlx::query("SELECT r.collection_id, r.status, r.data_contract, c.workspace_id, c.title FROM workflow_runs r JOIN collections c ON c.id = r.collection_id WHERE r.id = $1 FOR UPDATE OF r")
        .bind(body.run_id).fetch_optional(&mut *tx).await.map_err(db_error)?
        .ok_or_else(|| api_error(StatusCode::NOT_FOUND, "run not found"))?;
    let status: String = run.try_get("status").map_err(db_error)?;
    if terminal(&status) {
        return Ok(Json(json!({"ok": true, "ignored": "terminal run"})));
    }
    let collection_id: Uuid = run.try_get("collection_id").map_err(db_error)?;
    let workspace_id: Uuid = run.try_get("workspace_id").map_err(db_error)?;
    let title: String = run.try_get("title").map_err(db_error)?;
    let contract: Value = run.try_get("data_contract").map_err(db_error)?;
    let mut payload = body.payload.clone().unwrap_or(json!({}));
    if !payload.is_object() {
        return Err(api_error(
            StatusCode::UNPROCESSABLE_ENTITY,
            "event payload must be an object",
        ));
    }
    for (key, value) in [
        ("stage", json!(body.stage)),
        ("progress", json!(body.progress)),
        ("records_found", json!(body.records_found)),
        ("records_verified", json!(body.records_verified)),
        ("error", json!(body.error)),
    ] {
        if !value.is_null() {
            payload[key] = value;
        }
    }
    let mut verified_count = body.records_verified;
    let end_status = body.event_type.strip_prefix("run.").filter(|s| terminal(s));
    if matches!(end_status, Some("completed" | "partial" | "exhausted")) {
        let records = payload["records"].as_array().ok_or_else(|| {
            api_error(
                StatusCode::UNPROCESSABLE_ENTITY,
                "missing accepted records array",
            )
        })?;
        if records.iter().any(|r| !accepted_record(r, &contract)) {
            return Err(api_error(
                StatusCode::UNPROCESSABLE_ENTITY,
                "dataset contains a record without accepted typed evidence",
            ));
        }
        let coverage = if records.is_empty() {
            0.
        } else {
            records
                .iter()
                .map(|r| r["verification"]["field_coverage"].as_f64().unwrap_or(0.))
                .sum::<f64>()
                / records.len() as f64
        };
        verified_count = Some(records.len() as i32);
        let target = contract["target_count"].as_u64().unwrap_or(100).max(1) as usize;
        let meets_target = records.len() >= target
            && coverage >= contract["min_field_coverage"].as_f64().unwrap_or(1.);
        let expected = if meets_target {
            "completed"
        } else if records.is_empty() {
            "exhausted"
        } else {
            "partial"
        };
        if end_status != Some(expected) {
            return Err(api_error(
                StatusCode::UNPROCESSABLE_ENTITY,
                "terminal state does not match accepted count and coverage",
            ));
        }
        if !records.is_empty() {
            let entity_type = contract["entity_type"].as_str().unwrap_or("entity");
            let dataset_id: Uuid = sqlx::query_scalar("INSERT INTO datasets (collection_id, run_id, workspace_id, name, entity_type, record_count, avg_confidence, schema) VALUES ($1,$2,$3,$4,$5,$6,NULL,$7) RETURNING id")
                .bind(collection_id).bind(body.run_id).bind(workspace_id).bind(format!("{title} - Dataset"))
                .bind(entity_type).bind(records.len() as i32).bind(&contract).fetch_one(&mut *tx).await.map_err(db_error)?;
            for record in records {
                sqlx::query("INSERT INTO dataset_records (dataset_id, canonical_name, status, confidence_score, confidence_breakdown, primary_attributes) VALUES ($1,$2,'verified',NULL,'{}',$3)")
                    .bind(dataset_id).bind(record["canonical_name"].as_str().unwrap()).bind(record).execute(&mut *tx).await.map_err(db_error)?;
            }
        }
    }
    // A provider failure must preserve collected evidence for inspection while
    // keeping every draft outside accepted datasets.
    if end_status.is_some() {
        if let Some(review) = payload["review_candidates"].as_array() {
            for candidate in review {
                sqlx::query("INSERT INTO review_candidates (run_id,candidate) VALUES ($1,$2)")
                    .bind(body.run_id)
                    .bind(candidate)
                    .execute(&mut *tx)
                    .await
                    .map_err(db_error)?;
            }
        }
        if let Some(sources) = payload["sources"].as_array() {
            for source in sources {
                let Some(url) = source["url"].as_str().and_then(|s| url::Url::parse(s).ok()) else {
                    continue;
                };
                let Some(domain) = url.host_str() else {
                    continue;
                };
                let http_status = source["http_status"].as_i64().map(|v| v as i32);
                sqlx::query("INSERT INTO sources (workspace_id,domain,last_status_code,last_checked_at,last_success_at) VALUES ($1,$2,$3,NOW(),CASE WHEN $3=200 THEN NOW() ELSE NULL END) ON CONFLICT (workspace_id,domain) DO UPDATE SET last_status_code=EXCLUDED.last_status_code,last_checked_at=NOW(),last_success_at=EXCLUDED.last_success_at")
                    .bind(workspace_id).bind(domain).bind(http_status).execute(&mut *tx).await.map_err(db_error)?;
            }
        }
    }
    if let Some(count) = verified_count {
        payload["records_verified"] = json!(count);
    }
    if body.event_type == "stage.updated" {
        let stage = body
            .stage
            .as_deref()
            .ok_or_else(|| api_error(StatusCode::UNPROCESSABLE_ENTITY, "missing stage"))?;
        sqlx::query("UPDATE workflow_steps SET status='completed',completed_at=NOW(),duration_ms=(EXTRACT(EPOCH FROM (NOW()-started_at))*1000)::int WHERE run_id=$1 AND status='running' AND step_type<>$2")
            .bind(body.run_id).bind(stage).execute(&mut *tx).await.map_err(db_error)?;
        let id: Option<Uuid> = sqlx::query_scalar("SELECT id FROM workflow_steps WHERE run_id=$1 AND step_type=$2 AND status='running' LIMIT 1")
            .bind(body.run_id).bind(stage).fetch_optional(&mut *tx).await.map_err(db_error)?;
        if let Some(id) = id {
            sqlx::query("UPDATE workflow_steps SET metadata=$2 WHERE id=$1")
                .bind(id)
                .bind(&payload)
                .execute(&mut *tx)
                .await
                .map_err(db_error)?;
        } else {
            sqlx::query("INSERT INTO workflow_steps (run_id,step_type,status,metadata,started_at) VALUES ($1,$2,'running',$3,NOW())")
                .bind(body.run_id).bind(stage).bind(&payload).execute(&mut *tx).await.map_err(db_error)?;
        }
    }
    sqlx::query("UPDATE workflow_runs SET current_stage=COALESCE($2,current_stage), records_found=COALESCE($3,records_found),records_verified=COALESCE($4,records_verified),error_message=COALESCE($5,error_message),iteration=COALESCE($7,iteration),status=COALESCE($6,'running'),completed_at=CASE WHEN $6 IS NOT NULL THEN NOW() ELSE completed_at END WHERE id=$1")
        .bind(body.run_id).bind(&body.stage).bind(body.records_found).bind(verified_count).bind(&body.error).bind(end_status).bind(payload["iteration"].as_i64().map(|v|v as i32)).execute(&mut *tx).await.map_err(db_error)?;
    if let Some(end_status) = end_status {
        sqlx::query("UPDATE collections SET status=$1,updated_at=NOW() WHERE id=$2 AND NOT EXISTS (SELECT 1 FROM workflow_runs WHERE collection_id=$2 AND id<>$3 AND started_at > (SELECT started_at FROM workflow_runs WHERE id=$3))")
            .bind(end_status).bind(collection_id).bind(body.run_id).execute(&mut *tx).await.map_err(db_error)?;
        sqlx::query("UPDATE workflow_steps SET status=$2,completed_at=NOW(),duration_ms=(EXTRACT(EPOCH FROM (NOW()-started_at))*1000)::int WHERE run_id=$1 AND status='running'")
            .bind(body.run_id).bind(if matches!(end_status,"failed"|"cancelled") {end_status} else {"completed"}).execute(&mut *tx).await.map_err(db_error)?;
    }
    sqlx::query("INSERT INTO run_events (run_id,event_type,payload) VALUES ($1,$2,$3)")
        .bind(body.run_id)
        .bind(&body.event_type)
        .bind(&payload)
        .execute(&mut *tx)
        .await
        .map_err(db_error)?;
    tx.commit().await.map_err(db_error)?;
    Ok(Json(json!({"ok":true})))
}

pub async fn run_control(
    State(state): State<AppState>,
    axum::extract::Path(id): axum::extract::Path<Uuid>,
) -> ApiResult<Json<Value>> {
    use sqlx::Row;
    let row = sqlx::query("SELECT r.status,r.data_contract,c.workspace_id FROM workflow_runs r JOIN collections c ON c.id=r.collection_id WHERE r.id=$1")
        .bind(id).fetch_optional(&state.db.pool).await.map_err(|e|api_error(StatusCode::INTERNAL_SERVER_ERROR,e.to_string()))?
        .ok_or_else(||api_error(StatusCode::NOT_FOUND,"run not found"))?;
    let contract: Value = row.get("data_contract");
    let ws: Uuid = row.get("workspace_id");
    let blocked: Vec<String> = sqlx::query_scalar("SELECT domain FROM sources WHERE workspace_id=$1 AND enabled=false UNION SELECT unnest(blocked_domains) FROM user_preferences WHERE user_id=(SELECT triggered_by FROM workflow_runs WHERE id=$2)")
        .bind(ws).bind(id).fetch_all(&state.db.pool).await.map_err(|e|api_error(StatusCode::INTERNAL_SERVER_ERROR,e.to_string()))?;
    let mut policy = contract["source_policy"].clone();
    if !policy.is_object() {
        policy = json!({});
    }
    let mut all = policy["blocked_domains"]
        .as_array()
        .cloned()
        .unwrap_or_default();
    all.extend(blocked.into_iter().map(Value::String));
    policy["blocked_domains"] = json!(all);
    Ok(Json(
        json!({"status":row.get::<String,_>("status"),"source_policy":policy}),
    ))
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::extract::Path;
    use datavault_auth::AuthService;
    use datavault_storage::{Cache, Db};

    fn fixture() -> (Value, Value) {
        let contract = json!({"entity_type":"company","target_count":1,"fields":[{"name":"location","required":true}],"constraints":[]});
        let record = json!({"accepted":true,"status":"verified","canonical_name":"Acme","location":"Chennai",
            "verification":{"version":"typed-claims-v1","accepted":true,"field_coverage":1.0,"acceptance_failures":[]},
            "claims":{"location":{"state":"supported","value":"Chennai","evidence":[{"state":"supported",
                "verbatim_quote":"Acme is based in Chennai.","source_url":"https://example.com/about","chunk_id":"chunk-1",
                "content_sha256":"a".repeat(64),"char_start":0,"char_end":25}]}}});
        (contract, record)
    }

    fn event(id: Uuid, kind: &str, payload: Value) -> RunUpdatePayload {
        RunUpdatePayload {
            run_id: id,
            event_type: kind.into(),
            stage: None,
            progress: None,
            records_found: None,
            records_verified: None,
            error: None,
            payload: Some(payload),
        }
    }

    #[test]
    fn rejects_drafts_unknowns_forged_metrics_and_missing_evidence() {
        let (contract, record) = fixture();
        assert!(accepted_record(&record, &contract));
        for (pointer, value) in [
            ("/accepted", json!(false)),
            ("/status", json!("needs_review")),
            ("/claims/location/state", json!("unknown")),
            ("/claims/location/state", json!("contradicted")),
            ("/location", json!("Mumbai")),
            ("/claims/location/evidence", json!([])),
            ("/verification/field_coverage", json!(0.5)),
            (
                "/verification/acceptance_failures",
                json!(["missing evidence"]),
            ),
        ] {
            let mut bad = record.clone();
            *bad.pointer_mut(pointer).unwrap() = value;
            assert!(
                !accepted_record(&bad, &contract),
                "accepted invalid {pointer}"
            );
        }
    }

    // Run against an isolated migrated PostgreSQL database. No Redis or model required.
    #[tokio::test]
    async fn transactions_preserve_history_separate_review_and_ignore_late_completion() {
        let Ok(url) = std::env::var("TEST_DATABASE_URL") else {
            return;
        };
        let pool = sqlx::PgPool::connect(&url).await.unwrap();
        let db = Db::new(pool.clone());
        let redis = deadpool_redis::Config::from_url("redis://127.0.0.1:1")
            .create_pool(Some(deadpool_redis::Runtime::Tokio1))
            .unwrap();
        let state = AppState::new(
            db.clone(),
            Cache::new(redis),
            AuthService::new(db, "test-only".into()),
            "http://127.0.0.1:1".into(),
            "http://127.0.0.1:1".into(),
        );
        let user = Uuid::new_v4();
        let ws = Uuid::new_v4();
        let col = Uuid::new_v4();
        let run = Uuid::new_v4();
        let (contract, record) = fixture();
        sqlx::query("INSERT INTO users(id,email) VALUES ($1,$2)")
            .bind(user)
            .bind(format!("{user}@test.invalid"))
            .execute(&pool)
            .await
            .unwrap();
        sqlx::query("INSERT INTO workspaces(id,owner_id,name,slug) VALUES ($1,$2,'trust-test',$3)")
            .bind(ws)
            .bind(user)
            .bind(ws.to_string())
            .execute(&pool)
            .await
            .unwrap();
        sqlx::query("INSERT INTO collections(id,workspace_id,created_by,title,prompt,data_contract) VALUES ($1,$2,$3,'test','test',$4)")
            .bind(col).bind(ws).bind(user).bind(&contract).execute(&pool).await.unwrap();
        sqlx::query("INSERT INTO workflow_runs(id,collection_id,data_contract) VALUES ($1,$2,$3)")
            .bind(run)
            .bind(col)
            .bind(&contract)
            .execute(&pool)
            .await
            .unwrap();
        for stage in ["search", "extract", "validate"] {
            let mut e = event(run, "stage.updated", json!({"real_event":stage}));
            e.stage = Some(stage.into());
            let _ = intelligence_run(State(state.clone()), Json(e))
                .await
                .unwrap();
        }
        // A raw draft and a dishonest completion are both rejected atomically.
        let bad = intelligence_run(
            State(state.clone()),
            Json(event(
                run,
                "run.completed",
                json!({"records":[{"canonical_name":"Invented"}]}),
            )),
        )
        .await;
        assert!(bad.is_err());
        let bad = intelligence_run(
            State(state.clone()),
            Json(event(run, "run.completed", json!({"records":[]}))),
        )
        .await;
        assert!(bad.is_err());
        let review = json!({"canonical_name":"Review only","accepted":false});
        let complete = event(
            run,
            "run.completed",
            json!({"records":[record.clone()],"review_candidates":[review]}),
        );
        let _ = intelligence_run(State(state.clone()), Json(complete))
            .await
            .unwrap();
        // Retried callbacks cannot create another dataset.
        let _ = intelligence_run(
            State(state.clone()),
            Json(event(
                run,
                "run.completed",
                json!({"records":[record.clone()]}),
            )),
        )
        .await
        .unwrap();
        let count: i64 = sqlx::query_scalar("SELECT COUNT(*) FROM datasets WHERE run_id=$1")
            .bind(run)
            .fetch_one(&pool)
            .await
            .unwrap();
        assert_eq!(count, 1);
        let rows:i64=sqlx::query_scalar("SELECT COUNT(*) FROM dataset_records r JOIN datasets d ON r.dataset_id=d.id WHERE d.run_id=$1 AND confidence_score IS NULL").bind(run).fetch_one(&pool).await.unwrap();
        assert_eq!(rows, 1);
        let reviews: i64 =
            sqlx::query_scalar("SELECT COUNT(*) FROM review_candidates WHERE run_id=$1")
                .bind(run)
                .fetch_one(&pool)
                .await
                .unwrap();
        assert_eq!(reviews, 1);
        let stages:i64=sqlx::query_scalar("SELECT COUNT(*) FROM workflow_steps WHERE run_id=$1 AND status='completed' AND duration_ms IS NOT NULL").bind(run).fetch_one(&pool).await.unwrap();
        assert_eq!(stages, 3);
        let events: i64 = sqlx::query_scalar("SELECT COUNT(*) FROM run_events WHERE run_id=$1")
            .bind(run)
            .fetch_one(&pool)
            .await
            .unwrap();
        assert_eq!(events, 4);
        let finished = crate::handlers::runs::cancel(State(state.clone()), Path(run))
            .await
            .unwrap();
        assert_eq!(finished.0["status"], "completed");
        let cancelled = Uuid::new_v4();
        sqlx::query("INSERT INTO workflow_runs(id,collection_id,data_contract) VALUES ($1,$2,$3)")
            .bind(cancelled)
            .bind(col)
            .bind(&contract)
            .execute(&pool)
            .await
            .unwrap();
        let _ = crate::handlers::runs::cancel(State(state.clone()), Path(cancelled))
            .await
            .unwrap();
        let late = intelligence_run(
            State(state.clone()),
            Json(event(
                cancelled,
                "run.completed",
                json!({"records":[record.clone()]}),
            )),
        )
        .await
        .unwrap();
        assert_eq!(late.0["ignored"], "terminal run");
        let count: i64 = sqlx::query_scalar("SELECT COUNT(*) FROM datasets WHERE run_id=$1")
            .bind(cancelled)
            .fetch_one(&pool)
            .await
            .unwrap();
        assert_eq!(count, 0);
        for (kind, rows, expected_count) in [
            ("partial", json!([record.clone()]), 1_i64),
            ("exhausted", json!([]), 0_i64),
        ] {
            let next = Uuid::new_v4();
            let mut more = contract.clone();
            more["target_count"] = json!(2);
            sqlx::query(
                "INSERT INTO workflow_runs(id,collection_id,data_contract) VALUES ($1,$2,$3)",
            )
            .bind(next)
            .bind(col)
            .bind(&more)
            .execute(&pool)
            .await
            .unwrap();
            let _ = intelligence_run(
                State(state.clone()),
                Json(event(next, &format!("run.{kind}"), json!({"records":rows}))),
            )
            .await
            .unwrap();
            let saved_status: String =
                sqlx::query_scalar("SELECT status FROM workflow_runs WHERE id=$1")
                    .bind(next)
                    .fetch_one(&pool)
                    .await
                    .unwrap();
            assert_eq!(saved_status, kind);
            let accepted: i32 =
                sqlx::query_scalar("SELECT records_verified FROM workflow_runs WHERE id=$1")
                    .bind(next)
                    .fetch_one(&pool)
                    .await
                    .unwrap();
            assert_eq!(accepted, expected_count as i32);
            let count: i64 = sqlx::query_scalar("SELECT COUNT(*) FROM datasets WHERE run_id=$1")
                .bind(next)
                .fetch_one(&pool)
                .await
                .unwrap();
            assert_eq!(count, expected_count);
        }
        let failed = Uuid::new_v4();
        sqlx::query("INSERT INTO workflow_runs(id,collection_id,data_contract) VALUES ($1,$2,$3)")
            .bind(failed).bind(col).bind(&contract).execute(&pool).await.unwrap();
        let mut failure = event(failed, "run.failed", json!({"review_candidates":[{"canonical_name":"Draft","accepted":false}]}));
        failure.error = Some("Groq: HTTP 429".into());
        let _ = intelligence_run(State(state.clone()), Json(failure)).await.unwrap();
        let reviews: i64 = sqlx::query_scalar("SELECT COUNT(*) FROM review_candidates WHERE run_id=$1").bind(failed).fetch_one(&pool).await.unwrap();
        assert_eq!(reviews, 1);
        let datasets: i64 = sqlx::query_scalar("SELECT COUNT(*) FROM datasets WHERE run_id=$1").bind(failed).fetch_one(&pool).await.unwrap();
        assert_eq!(datasets, 0);
        let result = crate::handlers::runs::get_run(State(state.clone()), Path(failed)).await.unwrap();
        assert_eq!(result.0["error_message"], "Groq: HTTP 429");
        // Only this test's UUID-scoped data is removed.
        sqlx::query("DELETE FROM workspaces WHERE id=$1")
            .bind(ws)
            .execute(&pool)
            .await
            .unwrap();
        sqlx::query("DELETE FROM users WHERE id=$1")
            .bind(user)
            .execute(&pool)
            .await
            .unwrap();
    }
}
