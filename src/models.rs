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
pub struct StructuredRecord {
    pub id: String,
    pub title: String,
    pub category: String,
    pub key_attributes: HashMap<String, String>,
    pub source_url: String,
    pub confidence: f32,
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
}
