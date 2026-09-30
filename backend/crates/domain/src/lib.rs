use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use sqlx::FromRow;
use uuid::Uuid;

// ─── User ────────────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize, FromRow)]
pub struct User {
    pub id: Uuid,
    pub email: String,
    pub name: Option<String>,
    #[serde(skip_serializing)]
    pub password_hash: Option<String>,
    pub provider: String,
    pub provider_id: Option<String>,
    pub avatar_url: Option<String>,
    pub is_active: bool,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

// ─── Workspace ───────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize, FromRow)]
pub struct Workspace {
    pub id: Uuid,
    pub owner_id: Uuid,
    pub name: String,
    pub slug: String,
    pub plan: String,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize, sqlx::Type, PartialEq)]
#[sqlx(type_name = "text", rename_all = "snake_case")]
pub enum MemberRole {
    Owner,
    Admin,
    Editor,
    Viewer,
}

// ─── Collection ──────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize, FromRow)]
pub struct Collection {
    pub id: Uuid,
    pub workspace_id: Uuid,
    pub created_by: Uuid,
    pub title: String,
    pub prompt: String,
    pub status: String,
    pub data_contract: serde_json::Value,
    pub tags: Vec<String>,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum CollectionStatus {
    Draft,
    Planning,
    Running,
    Paused,
    NeedsReview,
    Completed,
    Partial,
    Exhausted,
    Failed,
    Cancelled,
}

impl std::fmt::Display for CollectionStatus {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Draft => write!(f, "draft"),
            Self::Planning => write!(f, "planning"),
            Self::Running => write!(f, "running"),
            Self::Paused => write!(f, "paused"),
            Self::NeedsReview => write!(f, "needs_review"),
            Self::Completed => write!(f, "completed"),
            Self::Partial => write!(f, "partial"),
            Self::Exhausted => write!(f, "exhausted"),
            Self::Failed => write!(f, "failed"),
            Self::Cancelled => write!(f, "cancelled"),
        }
    }
}

// ─── Data Contract ───────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DataContract {
    pub entity_type: String,
    pub fields: Vec<FieldDefinition>,
    pub constraints: Vec<Constraint>,
    pub target_count: Option<u32>,
    pub freshness_days: Option<u32>,
    pub evidence_policy: EvidencePolicy,
    pub allowed_domains: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FieldDefinition {
    pub name: String,
    pub field_type: String,
    pub description: Option<String>,
    pub required: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Constraint {
    pub field: String,
    pub operator: String, // "eq" | "contains" | "gte" | "lte" | "in"
    pub target_value: serde_json::Value,
    pub is_hard: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EvidencePolicy {
    pub min_sources: u32,
    pub prefer_official: bool,
    pub require_date: bool,
}

impl Default for EvidencePolicy {
    fn default() -> Self {
        Self {
            min_sources: 1,
            prefer_official: true,
            require_date: false,
        }
    }
}

// ─── Workflow Run ─────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize, FromRow)]
pub struct WorkflowRun {
    pub id: Uuid,
    pub collection_id: Uuid,
    pub triggered_by: Option<Uuid>,
    pub status: String,
    pub current_stage: String,
    pub iteration: i32,
    pub records_found: i32,
    pub records_verified: i32,
    pub avg_confidence: Option<f32>,
    pub error_message: Option<String>,
    pub started_at: DateTime<Utc>,
    pub completed_at: Option<DateTime<Utc>>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum WorkflowStage {
    Planning,
    Discovering,
    Collecting,
    Extracting,
    Normalizing,
    Validating,
    Deduplicating,
    Finalizing,
}

// ─── Source ───────────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize, FromRow)]
pub struct Source {
    pub id: Uuid,
    pub workspace_id: Option<Uuid>,
    pub domain: String,
    pub display_name: Option<String>,
    pub source_type: String,
    pub trust_tier: String,
    pub extraction_success_rate: Option<f32>,
    pub freshness_score: Option<f32>,
    pub last_success_at: Option<DateTime<Utc>>,
    pub last_checked_at: Option<DateTime<Utc>>,
    pub last_status_code: Option<i32>,
    pub enabled: bool,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

// ─── Document ────────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize, FromRow)]
pub struct Document {
    pub id: Uuid,
    pub run_id: Option<Uuid>,
    pub source_id: Option<Uuid>,
    pub url: String,
    pub final_url: Option<String>,
    pub content_hash: Option<String>,
    pub content_type: Option<String>,
    pub status_code: Option<i32>,
    pub object_path: Option<String>,
    pub metadata: serde_json::Value,
    pub fetched_at: DateTime<Utc>,
}

// ─── Entity ───────────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize, FromRow)]
pub struct Entity {
    pub id: Uuid,
    pub workspace_id: Uuid,
    pub entity_type: String,
    pub canonical_name: String,
    pub canonical_key: Option<String>,
    pub metadata: serde_json::Value,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

// ─── Claim ────────────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize, FromRow)]
pub struct Claim {
    pub id: Uuid,
    pub run_id: Uuid,
    pub document_id: Option<Uuid>,
    pub entity_id: Option<Uuid>,
    pub field_name: String,
    pub field_value: serde_json::Value,
    pub extraction_method: String,
    pub confidence: Option<f32>,
    pub created_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum ExtractionMethod {
    Api,
    JsonLd,
    HtmlSelector,
    Table,
    Regex,
    Llm,
}

impl std::fmt::Display for ExtractionMethod {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Api => write!(f, "api"),
            Self::JsonLd => write!(f, "json_ld"),
            Self::HtmlSelector => write!(f, "html_selector"),
            Self::Table => write!(f, "table"),
            Self::Regex => write!(f, "regex"),
            Self::Llm => write!(f, "llm"),
        }
    }
}

// ─── Evidence ─────────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize, FromRow)]
pub struct Evidence {
    pub id: Uuid,
    pub claim_id: Uuid,
    pub document_id: Option<Uuid>,
    pub url: String,
    pub text_excerpt: Option<String>,
    pub selector: Option<String>,
    pub content_hash: Option<String>,
    pub retrieved_at: DateTime<Utc>,
}

// ─── Dataset Record ───────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize, FromRow)]
pub struct DatasetRecord {
    pub id: Uuid,
    pub dataset_id: Uuid,
    pub entity_id: Option<Uuid>,
    pub canonical_name: String,
    pub status: String,
    pub confidence_score: Option<f32>,
    pub confidence_breakdown: serde_json::Value,
    pub primary_attributes: serde_json::Value,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SearchRequest {
    pub query: String,
    pub domain_filters: Vec<String>,
    pub max_results: usize,
    pub freshness_days: Option<u32>,
    #[serde(default)]
    pub model_config: Option<serde_json::Value>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SearchResult {
    pub url: String,
    pub title: String,
    pub snippet: Option<String>,
    pub provider: String,
    pub rank: usize,
    #[serde(default)]
    pub original_url: Option<String>,
    #[serde(default)]
    pub root_fallback: bool,
    #[serde(default)]
    pub redirected: bool,
}

// ─── Run Events (SSE) ─────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RunEvent {
    pub run_id: Uuid,
    pub event_type: String,
    pub payload: serde_json::Value,
}

// ─── User Preferences ─────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize, FromRow)]
pub struct UserPreferences {
    pub id: Uuid,
    pub user_id: Uuid,
    pub workspace_id: Option<Uuid>,
    pub default_target_count: i32,
    pub default_freshness_days: Option<i32>,
    pub preferred_regions: Vec<String>,
    pub preferred_source_types: Vec<String>,
    pub default_export_format: String,
    pub saved_categories: Vec<String>,
    pub blocked_domains: Vec<String>,
}

// ─── Error ────────────────────────────────────────────────────────────────────

#[derive(Debug, thiserror::Error)]
pub enum DomainError {
    #[error("not found: {0}")]
    NotFound(String),

    #[error("unauthorized")]
    Unauthorized,

    #[error("forbidden: {0}")]
    Forbidden(String),

    #[error("validation error: {0}")]
    Validation(String),

    #[error("conflict: {0}")]
    Conflict(String),

    #[error("database error: {0}")]
    Database(#[from] sqlx::Error),

    #[error("internal error: {0}")]
    Internal(String),
}
