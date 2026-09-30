export interface FieldEvidence {
  field_name: string;
  verbatim_quote: string;
  source_url: string;
  extracted_value: string;
  chunk_id?: string;
  char_start?: number;
  char_end?: number;
}

export interface MetricFactorScore {
  factor_name: string;
  score: number;
  weight: number;
  contribution: number;
}

export interface EntityProvenance {
  authority_score?: number;
  agreement_rate?: number;
  source_urls: string[];
  field_evidence: FieldEvidence[];
  factors?: MetricFactorScore[];
  http_status?: number;
  reachability?: number;
  freshness_basis?: string;
  fetched_at?: string;
  published_at?: string;
  content_sha256?: string;
  validation_method?: string;
  chunk_id?: string;
  char_start?: number;
  char_end?: number;
  retrieval_score?: number;
}

export interface EntityRecord {
  entity_id: string;
  canonical_name: string;
  primary_attributes: Record<string, string>;
  status: "verified" | "needs_review" | "draft" | "running";
  confidence_score: number | null;
  claims?: Record<string, { field_name: string; value: unknown; state: "supported" | "contradicted" | "unknown"; reason: string; evidence: FieldEvidence[] }>;
  verification?: { field_coverage: number; accepted: boolean; acceptance_failures: { field: string; state: string; reason: string }[] };
  provenance: EntityProvenance;
  confidence_breakdown?: Record<string, number>;
}

export interface SourceInfo {
  url: string;
  domain: string;
  title: string;
  authority_score?: number;
  live_status_code?: number;
  fetched_at?: string;
}

export interface WorkflowStage {
  stage_id: number;
  stage_name: string;
  status: "pending" | "running" | "completed" | "failed" | "cancelled";
  duration_ms: number | null;
  details: string;
}

export interface WorkflowExecution {
  workflow_id: string;
  stages: WorkflowStage[];
  total_duration_ms: number;
}

export interface FieldDefinition {
  name: string;
  field_type: string;
  description: string;
  required: boolean;
}

export interface ConstraintDefinition {
  field: string;
  operator: string;
  target_value: unknown;
  is_hard: boolean;
}

export interface DataContract {
  target_entity_type: string;
  fields: FieldDefinition[];
  constraints: ConstraintDefinition[];
  allowed_domains: string[];
}

export interface GroundingResponse {
  task_id: string;
  dataset_id?: string;
  title?: string;
  status?: string;
  updated_at?: string;
  intent: {
    category: string;
    target_entity: string;
    needs_external_search: boolean;
    confidence: number | null;
    explanation: string;
  };
  contract: DataContract;
  sub_queries: string[];
  records: EntityRecord[];
  sources: SourceInfo[];
  summary_briefing: string;
  workflow: WorkflowExecution;
  total_records: number;
  verified_count: number;
  average_confidence: number | null;
  run_id?: string;
  review_candidates?: EntityRecord[];
  stop_reason?: string;
  extracted_count?: number;
}

export interface TaskSummary {
  id: string;
  timestamp: string;
  prompt: string;
  category: string;
  records_count: number;
  sources_count: number;
  total_latency_ms: number;
  triggered_grounding: boolean;
  workflow_summary: string;
  status: "Completed" | "Running" | "Draft" | "Failed" | "Partial" | "Exhausted" | "Cancelled";
  collection_id?: string;
}
