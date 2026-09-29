use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

#[derive(Debug, Clone, Deserialize)]
#[allow(dead_code)]
pub struct GroundingRequest {
    pub prompt: String,
    pub grounding_threshold: Option<f32>,
    pub max_sources: Option<usize>,
    pub category_hint: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct IntentClassification {
    pub needs_search: bool,
    pub confidence_score: f32,
    pub reasoning: String,
    pub category: String,
    pub trigger_type: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DataContract {
    pub entity: String,
    pub fields: HashMap<String, String>, // field_name -> data_type ("string", "currency", "date", "url", "number")
    pub constraints: Vec<String>,
    pub freshness: String,
    pub target_count: usize,
    pub preferred_sources: Vec<String>,
    pub critical_fields: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct QueryExpansion {
    pub original_prompt: String,
    pub rewritten_queries: Vec<String>,
    pub target_intent: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SearchResultItem {
    pub url: String,
    pub title: String,
    pub snippet: String,
    pub domain: String,
    pub source_engine: String,
    pub relevance_score: f32,
    pub rank: usize,
    pub is_live: bool,
    pub scraped_content: Option<String>,
    pub jsonld_data: Option<serde_json::Value>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Citation {
    pub index: usize,
    pub url: String,
    pub title: String,
    pub domain: String,
    pub snippet: String,
    pub is_live: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GroundingMetadata {
    pub search_queries: Vec<String>,
    pub sources: Vec<Citation>,
    pub grounding_threshold: f32,
    pub intent_score: f32,
    pub triggered_grounding: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FieldEvidence {
    pub field: String,
    pub value: String,
    pub quote: String,
    pub source_url: String,
    pub page_title: String,
    pub source_type: String, // "official_company_page", "primary_job_board", "verified_directory", "secondary_aggregator"
    pub retrieved_at: DateTime<Utc>,
    pub confidence: f32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ConfidenceBreakdown {
    pub source_authority: f32,
    pub extraction_certainty: f32,
    pub cross_source_agreement: f32,
    pub freshness: f32,
    pub completeness: f32,
    pub composite_score: f32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StructuredRecord {
    pub id: String,
    pub canonical_name: String,
    pub title: String,
    pub category: String,
    pub key_attributes: HashMap<String, String>,
    pub field_evidence: HashMap<String, FieldEvidence>,
    pub confidence: ConfidenceBreakdown,
    pub validation_status: String, // "PASSED", "WARNING", "REJECTED"
    pub validation_notes: Vec<String>,
    pub source_url: String,
    pub source_type: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum WorkflowState {
    Draft,
    Planning,
    Discovering,
    Collecting,
    Extracting,
    Validating,
    Deduplicating,
    Finalizing,
    Completed,
    Failed,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WorkflowStats {
    pub workflow_id: String,
    pub state: WorkflowState,
    pub domains_discovered: usize,
    pub domains_accepted: usize,
    pub pages_collected: usize,
    pub records_extracted: usize,
    pub records_validated: usize,
    pub records_final: usize,
    pub dag_summary: String,
    pub loop_iterations: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StageMetric {
    pub stage_number: usize,
    pub stage_name: String,
    pub duration_ms: u64,
    pub status: String,
    pub description: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GroundingResponse {
    pub id: String,
    pub timestamp: DateTime<Utc>,
    pub prompt: String,
    pub intent: IntentClassification,
    pub data_contract: Option<DataContract>,
    pub workflow_stats: Option<WorkflowStats>,
    pub answer_markdown: String,
    pub grounding_metadata: GroundingMetadata,
    pub dataset: Vec<StructuredRecord>,
    pub pipeline_stages: Vec<StageMetric>,
    pub total_latency_ms: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TaskHistorySummary {
    pub id: String,
    pub timestamp: DateTime<Utc>,
    pub prompt: String,
    pub category: String,
    pub records_count: usize,
    pub sources_count: usize,
    pub total_latency_ms: u64,
    pub triggered_grounding: bool,
    pub workflow_summary: Option<String>,
}
