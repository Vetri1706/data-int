/**
 * Datavault API Client
 * Typed wrapper over the Rust Axum backend REST API.
 * API failures remain visible; sample data is never substituted for live results.
 */

import type {
  EntityProvenance,
  EntityRecord,
  GroundingResponse,
  TaskSummary,
} from "@/lib/types";

const API_BASE = "/api/v1";

export class ApiError extends Error {
  constructor(message: string, public status: number) { super(message); }
}

// ─── Core fetch helper ────────────────────────────────────────────────────────

async function apiFetch<T>(
  path: string,
  opts: RequestInit = {}
): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(opts.headers as Record<string, string>),
  };
  const res = await fetch(`${API_BASE}${path}`, { signal: AbortSignal.timeout(65000), ...opts, credentials: "same-origin", cache: "no-store", headers });

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    if (res.status === 401 && !path.startsWith("/auth/") && typeof window !== "undefined") {
      window.dispatchEvent(new Event("datavault:session-expired"));
    }
    throw new ApiError(body.error || `API error ${res.status}`, res.status);
  }

  if (res.status === 204) return {} as T;
  return res.json() as Promise<T>;
}

// ─── Auth ─────────────────────────────────────────────────────────────────────

export interface AuthUser {
  id: string;
  email: string;
  name?: string;
  avatar_url?: string;
}

export interface AuthResponse {
  user: AuthUser;
}

export const auth = {
  register: (email: string, password: string, name?: string) =>
    apiFetch<AuthResponse>("/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password, name }),
    }),

  login: (email: string, password: string) =>
    apiFetch<AuthResponse>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),

  me: () => apiFetch<AuthUser>("/auth/me"),

  logout: () => apiFetch<void>("/auth/logout", { method: "POST" }),
};

// ─── Collections ─────────────────────────────────────────────────────────────

export interface Collection {
  id: string;
  workspace_id: string;
  created_by: string;
  title: string;
  prompt: string;
  status: "draft" | "planning" | "running" | "paused" | "needs_review" | "completed" | "failed" | "cancelled";
  data_contract: DataContract;
  tags: string[];
  created_at: string;
  updated_at: string;
}

export interface DataContract {
  _model_config?: ModelSelection;
  entity_type: string;
  fields: FieldDefinition[];
  constraints: Constraint[];
  target_count?: number;
  freshness_days?: number;
  evidence_policy: EvidencePolicy;
  allowed_domains: string[];
}

export interface FieldDefinition {
  name: string;
  field_type: string;
  description?: string;
  required: boolean;
}

export interface Constraint {
  field: string;
  operator: "eq" | "contains" | "gte" | "lte" | "in";
  target_value: unknown;
  is_hard: boolean;
}

export interface EvidencePolicy {
  min_sources: number;
  prefer_official: boolean;
  require_date: boolean;
}

export interface ModelSelection {
  provider: "local" | "nvidia";
  model: string;
  allow_external: boolean;
}

export interface ModelCatalog {
  default: ModelSelection;
  providers: { id: ModelSelection["provider"]; label: string; available: boolean; reason?: string | null;
    models: { id: string; label: string; available: boolean; reason?: string | null }[] }[];
}

export const models = {
  list: (signal?: AbortSignal) => apiFetch<ModelCatalog>("/me/models", { signal }),
};

export const collections = {
  list: () =>
    apiFetch<{ data: Collection[]; total: number }>("/collections"),

  get: (id: string) =>
    apiFetch<Collection>(`/collections/${id}`),

  create: (title: string, prompt: string, tags?: string[], modelSelection?: ModelSelection) =>
    apiFetch<Collection>("/collections", {
      method: "POST",
      body: JSON.stringify({ title, prompt, tags, model_selection: modelSelection }),
    }),

  triggerRun: (id: string) =>
    apiFetch<{ run_id: string; status: string }>(`/collections/${id}/run`, {
      method: "POST",
    }),

  update: (id: string, updates: { title?: string; tags?: string[]; status?: string }) =>
    apiFetch<Collection>(`/collections/${id}`, {
      method: "PATCH",
      body: JSON.stringify(updates),
    }),

  delete: (id: string) =>
    apiFetch<void>(`/collections/${id}`, { method: "DELETE" }),

  bulkDelete: async (ids: string[]) => {
    await Promise.all(ids.map((id) => apiFetch<void>(`/collections/${id}`, { method: "DELETE" })));
  },
};

// ─── Workflow Runs ────────────────────────────────────────────────────────────

export interface WorkflowStep {
  id: string;
  step_type: string;
  status: string;
  duration_ms?: number;
  metadata: Record<string, unknown>;
  started_at?: string;
  completed_at?: string;
}

export interface WorkflowRun {
  id: string;
  collection_id: string;
  status: string;
  current_stage: string;
  iteration: number;
  records_found: number;
  records_verified: number;
  avg_confidence?: number;
  started_at: string;
  completed_at?: string;
  steps: WorkflowStep[];
}

export const runs = {
  get: (id: string) =>
    apiFetch<WorkflowRun>(`/runs/${id}`),

  pause: (id: string) =>
    apiFetch<void>(`/runs/${id}/pause`, { method: "POST" }),

  cancel: (id: string) =>
    apiFetch<void>(`/runs/${id}/cancel`, { method: "POST" }),

  /** Returns an EventSource for SSE run events */
  events: (runId: string): EventSource => {
    return new EventSource(`${API_BASE}/runs/${runId}/events`);
  },
};

// ─── Datasets ────────────────────────────────────────────────────────────────

export interface Dataset {
  id: string;
  collection_id: string;
  name: string;
  entity_type: string;
  record_count: number;
  avg_confidence?: number;
  schema: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface ConfidenceBreakdown {
  source_authority: number;
  extraction_certainty: number;
  agreement: number;
  freshness: number;
  completeness: number;
  reachability?: number;
  grounding_score?: number;
  ml_validation_score?: number;
}

export interface DatasetRecord {
  id: string;
  dataset_id: string;
  entity_id?: string;
  canonical_name: string;
  status: "verified" | "needs_review" | "draft" | "rejected" | "conflicting";
  confidence_score: number;
  confidence_breakdown: ConfidenceBreakdown;
  primary_attributes: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export const datasets = {
  list: () =>
    apiFetch<{ data: Dataset[]; total: number }>("/datasets"),

  get: (id: string) =>
    apiFetch<Dataset>(`/datasets/${id}`),

  records: (id: string) =>
    apiFetch<{ data: DatasetRecord[]; total: number }>(`/datasets/${id}/records`),

  export: (id: string, format = "csv") =>
    apiFetch<{ export_id: string; status: string }>(`/datasets/${id}/export`, {
      method: "POST",
      body: JSON.stringify({ format }),
    }),
};

// ─── Sources ─────────────────────────────────────────────────────────────────

export interface Source {
  id: string;
  domain: string;
  display_name?: string;
  source_type: string;
  trust_tier: "tier1" | "tier2" | "tier3";
  extraction_success_rate: number;
  freshness_score: number;
  enabled: boolean;
  last_success_at?: string;
  last_checked_at?: string;
  last_status_code?: number;
}

export const sources = {
  list: () =>
    apiFetch<{ data: Source[] }>("/sources"),

  create: (domain: string, source_type?: string, trust_tier?: string) =>
    apiFetch<Source>("/sources", {
      method: "POST",
      body: JSON.stringify({ domain, source_type, trust_tier }),
    }),

  toggle: (id: string, enabled: boolean) =>
    apiFetch<void>(`/sources/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ enabled }),
    }),
};

// ─── User Preferences ─────────────────────────────────────────────────────────

export interface UserPreferences {
  default_target_count: number;
  default_freshness_days?: number;
  preferred_regions: string[];
  preferred_source_types: string[];
  default_export_format: "csv" | "json" | "xlsx";
  saved_categories: string[];
  blocked_domains: string[];
}

export const preferences = {
  get: () =>
    apiFetch<UserPreferences>("/me/preferences"),

  update: (prefs: Partial<UserPreferences>) =>
    apiFetch<void>("/me/preferences", {
      method: "PATCH",
      body: JSON.stringify(prefs),
    }),
};

// ─── Health ───────────────────────────────────────────────────────────────────

export const health = {
  check: () =>
    apiFetch<{ status: string; services: { postgres: string; redis: string } }>("/health"),
};


/** Preserve the evidence written by the intelligence service in primary_attributes. */
export function toEntityRecord(record: DatasetRecord): EntityRecord {
  const raw = record.primary_attributes ?? {};
  const explicitProvenance = raw.provenance as EntityRecord["provenance"] | undefined;
  
  const sourceUrl = (raw.source_url || raw.website || raw.url || raw.link) as string | undefined;
  const evidenceExcerpt = raw.evidence_excerpt as string | undefined;
  
  const sourceUrls = explicitProvenance?.source_urls?.length 
    ? explicitProvenance.source_urls 
    : (sourceUrl ? [sourceUrl] : []);
    
  const fieldEvidence = explicitProvenance?.field_evidence?.length
    ? explicitProvenance.field_evidence
    : (evidenceExcerpt && sourceUrl
        ? [{
            field_name: "Source evidence",
            verbatim_quote: evidenceExcerpt,
            source_url: sourceUrl,
            extracted_value: record.canonical_name,
          }]
        : []);

  const breakdown = ((record.confidence_breakdown ?? raw.confidence_breakdown ?? {}) as unknown) as Record<string, number>;
  const reachability = breakdown.reachability ?? (raw.reachability !== undefined ? Number(raw.reachability) : 1.0);
  const authority = breakdown.source_authority ?? 0.8;
  const agreement = breakdown.agreement ?? 0.0;

  const provenance: EntityProvenance = {
    source_urls: sourceUrls,
    field_evidence: fieldEvidence,
    authority_score: explicitProvenance?.authority_score ?? authority,
    agreement_rate: explicitProvenance?.agreement_rate ?? agreement,
    reachability: explicitProvenance?.reachability ?? reachability,
    http_status: explicitProvenance?.http_status ?? (reachability >= 0.5 ? 200 : undefined),
    freshness_basis: explicitProvenance?.freshness_basis ?? "crawl",
  };

  const reserved = new Set([
    "provenance",
    "confidence_breakdown",
    "canonical_name",
    "source_url",
    "evidence_excerpt",
    "chunk_id",
    "confidence_score",
    "grounding_score",
    "extraction_confidence",
    "status",
    "reachability",
  ]);

  return {
    entity_id: record.entity_id ?? record.id,
    canonical_name: record.canonical_name,
    primary_attributes: Object.fromEntries(
      Object.entries(raw)
        .filter(([key, value]) => !reserved.has(key) && value !== null && ["string", "number", "boolean"].includes(typeof value))
        .map(([key, value]) => [key, String(value)])
    ),
    confidence_score: Number.isFinite(record.confidence_score) ? record.confidence_score : 0,
    confidence_breakdown: breakdown,
    status: record.status === "verified" || record.status === "draft" ? record.status : "needs_review",
    provenance,
  };
}

export async function fetchTasks(): Promise<TaskSummary[]> {
  const [collectionList, datasetList] = await Promise.all([collections.list(), datasets.list()]);
  return collectionList.data.map((collection) => {
    const dataset = datasetList.data.find((item) => item.collection_id === collection.id);
    const status: TaskSummary["status"] = collection.status === "completed" ? "Completed"
      : collection.status === "failed" ? "Failed"
      : ["running", "planning"].includes(collection.status) ? "Running" : "Draft";
    return {
      id: collection.id, timestamp: collection.updated_at, prompt: collection.title,
      category: collection.data_contract?.entity_type ?? "entity",
      records_count: dataset?.record_count ?? 0, sources_count: 0,
      total_latency_ms: 0, triggered_grounding: Boolean(dataset),
      workflow_summary: collection.status, status,
    };
  });
}

export async function fetchTaskById(id: string): Promise<GroundingResponse> {
  const [collection, datasetList] = await Promise.all([collections.get(id), datasets.list()]);
  const dataset = datasetList.data.filter((item) => item.collection_id === id)
    .sort((a, b) => b.created_at.localeCompare(a.created_at))[0];
  const response = dataset ? await datasets.records(dataset.id) : { data: [] };
  const records = response.data.map(toEntityRecord);
  const contract = collection.data_contract;
  const sourceMap = new Map<string, GroundingResponse["sources"][number]>();
  for (const record of records) {
    for (const url of record.provenance.source_urls ?? []) {
      let domain: string;
      try { domain = new URL(url).hostname; } catch { continue; }
      const isPrimary = record.provenance.field_evidence.some((field) => field.source_url === url);
      sourceMap.set(url, {
        url, domain, title: domain,
        authority_score: isPrimary ? record.provenance.authority_score : undefined,
        live_status_code: isPrimary ? record.provenance.http_status : undefined,
      });
    }
  }
  return {
    task_id: id, dataset_id: dataset?.id, title: collection.title,
    status: collection.status, updated_at: collection.updated_at,
    intent: { category: contract?.entity_type ?? "entity", target_entity: contract?.entity_type ?? "entity",
      needs_external_search: true, confidence: 0, explanation: collection.prompt },
    contract: { target_entity_type: contract?.entity_type ?? "entity",
      fields: (contract?.fields ?? []).map((field) => ({ ...field, description: field.description ?? "" })),
      constraints: contract?.constraints ?? [], allowed_domains: contract?.allowed_domains ?? [] },
    sub_queries: [], records, sources: [...sourceMap.values()],
    summary_briefing: dataset ? `${records.length} records loaded with their stored source evidence.` : "This collection has no completed dataset yet.",
    workflow: { workflow_id: id, stages: [], total_duration_ms: 0 },
    total_records: records.length, verified_count: records.filter((r) => r.status === "verified").length,
    average_confidence: records.length ? records.reduce((sum, record) => sum + record.confidence_score, 0) / records.length : 0,
  };
}

export async function executeGroundedSearch(prompt: string, modelSelection?: ModelSelection, onProgress?: (stage: string) => void): Promise<GroundingResponse> {
  onProgress?.("planning");
  const collection = await collections.create(prompt.slice(0, 100), prompt, undefined, modelSelection);
  const run = await collections.triggerRun(collection.id);
  const deadline = Date.now() + 195_000;
  while (Date.now() < deadline) {
    const current = await runs.get(run.run_id);
    onProgress?.(current.current_stage);
    if (current.status === "completed") {
      const result = await fetchTaskById(collection.id);
      if (result.dataset_id) return result;
    }
    if (["failed", "cancelled"].includes(current.status)) {
      throw new Error(`Collection run ${current.status}. Open Collections to inspect the run.`);
    }
    await new Promise((resolve) => setTimeout(resolve, 1500));
  }
  throw new Error("The collection is still running. Open Collections to check its progress.");
}

export function getExportCsvUrl(id: string): string {
  return `${API_BASE}/datasets/${id}/export?format=csv`;
}

export function getExportJsonUrl(id: string): string {
  return `${API_BASE}/datasets/${id}/export?format=json`;
}
