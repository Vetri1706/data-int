use anyhow::Result;
use datavault_domain::{Collection, CollectionStatus, DatasetRecord, Entity, User, Workspace};
use sqlx::PgPool;
use uuid::Uuid;

/// Central Postgres repository — thin wrappers over sqlx queries.
/// All business logic lives in workflow / service crates; this stays I/O only.
#[derive(Clone)]
pub struct Db {
    pub pool: PgPool,
}

impl Db {
    pub fn new(pool: PgPool) -> Self {
        Self { pool }
    }

    // ─── Users ──────────────────────────────────────────────────────────────

    pub async fn get_user_by_id(&self, id: Uuid) -> Result<Option<User>> {
        let row = sqlx::query!(
            "SELECT id, email, name, password_hash, provider, provider_id, avatar_url,
                    is_active, created_at, updated_at
             FROM users WHERE id = $1",
            id
        )
        .fetch_optional(&self.pool)
        .await?;
        Ok(row.map(|r| User {
            id:            r.id,
            email:         r.email,
            name:          r.name,
            password_hash: r.password_hash,
            provider:      r.provider.unwrap_or_else(|| "local".to_string()),
            provider_id:   r.provider_id,
            avatar_url:    r.avatar_url,
            is_active:     r.is_active,
            created_at:    r.created_at,
            updated_at:    r.updated_at,
        }))
    }

    pub async fn get_user_by_email(&self, email: &str) -> Result<Option<User>> {
        let row = sqlx::query!(
            "SELECT id, email, name, password_hash, provider, provider_id, avatar_url,
                    is_active, created_at, updated_at
             FROM users WHERE email = $1",
            email
        )
        .fetch_optional(&self.pool)
        .await?;
        Ok(row.map(|r| User {
            id:            r.id,
            email:         r.email,
            name:          r.name,
            password_hash: r.password_hash,
            provider:      r.provider.unwrap_or_else(|| "local".to_string()),
            provider_id:   r.provider_id,
            avatar_url:    r.avatar_url,
            is_active:     r.is_active,
            created_at:    r.created_at,
            updated_at:    r.updated_at,
        }))
    }

    pub async fn create_user(
        &self,
        email: &str,
        name: Option<&str>,
        password_hash: Option<&str>,
    ) -> Result<User> {
        let row = sqlx::query!(
            "INSERT INTO users (email, name, password_hash)
             VALUES ($1, $2, $3)
             RETURNING id, email, name, password_hash, provider, provider_id, avatar_url,
                       is_active, created_at, updated_at",
            email,
            name as _,
            password_hash as _,
        )
        .fetch_one(&self.pool)
        .await?;
        Ok(User {
            id:            row.id,
            email:         row.email,
            name:          row.name,
            password_hash: row.password_hash,
            provider:      row.provider.unwrap_or_else(|| "local".to_string()),
            provider_id:   row.provider_id,
            avatar_url:    row.avatar_url,
            is_active:     row.is_active,
            created_at:    row.created_at,
            updated_at:    row.updated_at,
        })
    }

    // ─── Workspaces ─────────────────────────────────────────────────────────

    pub async fn create_workspace(
        &self,
        owner_id: Uuid,
        name: &str,
        slug: &str,
    ) -> Result<Workspace> {
        let ws = sqlx::query_as!(
            Workspace,
            "INSERT INTO workspaces (owner_id, name, slug)
             VALUES ($1, $2, $3)
             RETURNING id, owner_id, name, slug, plan, created_at, updated_at",
            owner_id,
            name,
            slug,
        )
        .fetch_one(&self.pool)
        .await?;

        // Add owner as member
        sqlx::query!(
            "INSERT INTO workspace_members (workspace_id, user_id, role)
             VALUES ($1, $2, 'owner')",
            ws.id,
            owner_id,
        )
        .execute(&self.pool)
        .await?;

        Ok(ws)
    }

    pub async fn get_workspace_by_owner(&self, owner_id: Uuid) -> Result<Option<Workspace>> {
        let ws = sqlx::query_as!(
            Workspace,
            "SELECT id, owner_id, name, slug, plan, created_at, updated_at
             FROM workspaces WHERE owner_id = $1 LIMIT 1",
            owner_id
        )
        .fetch_optional(&self.pool)
        .await?;
        Ok(ws)
    }

    // ─── Collections ────────────────────────────────────────────────────────

    pub async fn list_collections(&self, workspace_id: Uuid) -> Result<Vec<Collection>> {
        let cols = sqlx::query_as!(
            Collection,
            "SELECT id, workspace_id, created_by, title, prompt, status,
                    data_contract, tags, created_at, updated_at
             FROM collections
             WHERE workspace_id = $1
             ORDER BY created_at DESC
             LIMIT 50",
            workspace_id
        )
        .fetch_all(&self.pool)
        .await?;
        Ok(cols)
    }

    pub async fn get_collection(&self, id: Uuid) -> Result<Option<Collection>> {
        let col = sqlx::query_as!(
            Collection,
            "SELECT id, workspace_id, created_by, title, prompt, status,
                    data_contract, tags, created_at, updated_at
             FROM collections WHERE id = $1",
            id
        )
        .fetch_optional(&self.pool)
        .await?;
        Ok(col)
    }

    pub async fn create_collection(
        &self,
        workspace_id: Uuid,
        created_by: Uuid,
        title: &str,
        prompt: &str,
        data_contract: &serde_json::Value,
    ) -> Result<Collection> {
        let col = sqlx::query_as!(
            Collection,
            "INSERT INTO collections (workspace_id, created_by, title, prompt, data_contract)
             VALUES ($1, $2, $3, $4, $5)
             RETURNING id, workspace_id, created_by, title, prompt, status,
                       data_contract, tags, created_at, updated_at",
            workspace_id,
            created_by,
            title,
            prompt,
            data_contract,
        )
        .fetch_one(&self.pool)
        .await?;
        Ok(col)
    }

    pub async fn update_collection_status(
        &self,
        id: Uuid,
        status: &CollectionStatus,
    ) -> Result<()> {
        sqlx::query!(
            "UPDATE collections SET status = $1, updated_at = NOW() WHERE id = $2",
            status.to_string(),
            id
        )
        .execute(&self.pool)
        .await?;
        Ok(())
    }

    // ─── Dataset Records ────────────────────────────────────────────────────

    pub async fn list_dataset_records(&self, dataset_id: Uuid) -> Result<Vec<DatasetRecord>> {
        let records = sqlx::query_as!(
            DatasetRecord,
            "SELECT id, dataset_id, entity_id, canonical_name, status,
                    confidence_score, confidence_breakdown, primary_attributes,
                    created_at, updated_at
             FROM dataset_records
             WHERE dataset_id = $1
             ORDER BY confidence_score DESC
             LIMIT 500",
            dataset_id
        )
        .fetch_all(&self.pool)
        .await?;
        Ok(records)
    }

    // ─── Entities ───────────────────────────────────────────────────────────

    pub async fn find_entity_by_key(
        &self,
        workspace_id: Uuid,
        entity_type: &str,
        canonical_key: &str,
    ) -> Result<Option<Entity>> {
        let entity = sqlx::query_as!(
            Entity,
            "SELECT id, workspace_id, entity_type, canonical_name, canonical_key,
                    metadata, created_at, updated_at
             FROM entities
             WHERE workspace_id = $1
               AND entity_type  = $2
               AND canonical_key = $3",
            workspace_id,
            entity_type,
            canonical_key,
        )
        .fetch_optional(&self.pool)
        .await?;
        Ok(entity)
    }

    pub async fn insert_run_event(
        &self,
        run_id: Uuid,
        event_type: &str,
        payload: &serde_json::Value,
    ) -> Result<()> {
        sqlx::query!(
            "INSERT INTO run_events (run_id, event_type, payload)
             VALUES ($1, $2, $3)",
            run_id,
            event_type,
            payload,
        )
        .execute(&self.pool)
        .await?;
        Ok(())
    }
}

// ─── Redis Cache ──────────────────────────────────────────────────────────────

use deadpool_redis::{redis::AsyncCommands, Pool as RedisPool};
use std::time::Duration;

#[derive(Clone)]
pub struct Cache {
    pub pool: RedisPool,
}

impl Cache {
    pub fn new(pool: RedisPool) -> Self {
        Self { pool }
    }

    pub async fn get(&self, key: &str) -> Result<Option<String>> {
        let mut conn = self.pool.get().await?;
        let val: Option<String> = conn.get(key).await?;
        Ok(val)
    }

    pub async fn set(&self, key: &str, value: &str, ttl: Duration) -> Result<()> {
        let mut conn = self.pool.get().await?;
        let _: () = conn.set_ex(key, value, ttl.as_secs()).await?;
        Ok(())
    }

    pub async fn del(&self, key: &str) -> Result<()> {
        let mut conn = self.pool.get().await?;
        let _: () = conn.del(key).await?;
        Ok(())
    }

    /// Publish a run event to Redis pub/sub for SSE fan-out
    pub async fn publish_run_event(
        &self,
        run_id: uuid::Uuid,
        event_json: &str,
    ) -> Result<()> {
        let mut conn = self.pool.get().await?;
        let channel = format!("run:{}", run_id);
        let _: () = conn.publish(channel, event_json).await?;
        Ok(())
    }
}
