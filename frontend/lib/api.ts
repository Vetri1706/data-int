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
  status: "draft" | "planning" | "running" | "paused" | "needs_review" | "completed" | "partial" | "exhausted" | "failed" | "cancelled";
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
  source_policy?: SourcePolicy;
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

export interface SourcePolicy { basis: "user_confirmed_permission"; approved_domains: string[]; blocked_domains?: string[]; domain_filters?: string[]; }

export interface SourceCandidate {
  domain: string;
  pages: { title: string; url: string; provider: string; snippet?: string | null }[];
}

export const sourceDiscovery = {
  discover: (prompt: string, domainFilters: string[], signal: AbortSignal) =>
    apiFetch<{ domains: SourceCandidate[]; total: number }>("/me/source-discovery", {
      method: "POST", body: JSON.stringify({ prompt, domain_filters: domainFilters }),
      signal: AbortSignal.any([signal, AbortSignal.timeout(25000)]),
    }),
};

export interface ModelSelection {
  provider: "local" | "nvidia" | "glm" | "groq" | "gemini" | "openrouter" | "huggingface";
  model: string;
  allow_external: boolean;
}

export interface ModelCatalog {
  default: ModelSelection | null;
  providers: { id: ModelSelection["provider"]; label: string; available: boolean; configured?: boolean; external?: boolean; reason?: string | null; default_model?: string | null;
    models: { id: string; label: string; available: boolean; reason?: string | null;
      context_length?: number | null; catalog_source?: "live" | "documented";
      cost?: { kind: "free" | "free_tier" | "local" | "credits" | "paid" | "unknown"; label: string; note: string; source_url: string };
    }[] }[];
}

export const providerLabels: Record<ModelSelection["provider"], string> = {
  local: "Local Ollama", nvidia: "NVIDIA", glm: "GLM (Z.ai)", groq: "Groq",
  gemini: "Gemini", openrouter: "OpenRouter", huggingface: "Hugging Face",
};

export const models = {
  list: (signal?: AbortSignal) => apiFetch<ModelCatalog>("/me/models", { signal }),
};

export const collections = {
  list: () =>
    apiFetch<{ data: Collection[]; total: number }>("/collections"),

  get: (id: string) =>
    apiFetch<Collection>(`/collections/${id}`),

  create: (title: string, prompt: string, tags?: string[], modelSelection?: ModelSelection, sourcePolicy?: SourcePolicy, templateContract?: Partial<DataContract>, discoverySources?: SourceCandidate["pages"]) =>
    apiFetch<Collection>("/collections", {
      method: "POST",
      body: JSON.stringify({ title, prompt, tags, model_selection: modelSelection, source_policy: sourcePolicy, template_contract: templateContract, discovery_sources: discoverySources }),
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
  error_message?: string | null;
  steps: WorkflowStep[];
}

export interface RunEvent { id: number; type: string; payload: Record<string, unknown>; created_at: string; }
export const runs = {
  list: (collectionId: string) => apiFetch<{ data: WorkflowRun[] }>(`/collections/${collectionId}/runs`),
  history: (id: string) => apiFetch<{ data: RunEvent[]; review_candidates: Record<string, unknown>[] }>(`/runs/${id}/history`),
  get: (id: string) =>
    apiFetch<WorkflowRun>(`/runs/${id}`),

  pause: (id: string) =>
    apiFetch<void>(`/runs/${id}/pause`, { method: "POST" }),

  cancel: (id: string) =>
    apiFetch<{status: string; worker_notified?: boolean; already_terminal?: boolean}>(`/runs/${id}/cancel`, { method: "POST" }),

  /** Returns an EventSource for SSE run events */
  events: (runId: string): EventSource => {
    return new EventSource(`${API_BASE}/runs/${runId}/events`);
  },
};

// ─── Datasets ────────────────────────────────────────────────────────────────

export interface Dataset {
  id: string;
  run_id?: string;
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
  confidence_score: number | null;
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
  extraction_success_rate: number | null;
  freshness_score: number | null;
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
  
  const sourceUrls = explicitProvenance?.source_urls?.length 
    ? explicitProvenance.source_urls 
    : (sourceUrl ? [sourceUrl] : []);
    
  const fieldEvidence = explicitProvenance?.field_evidence ?? [];
  const breakdown = (record.confidence_breakdown ?? raw.confidence_breakdown ?? {}) as unknown as Record<string, number>;
  const provenance: EntityProvenance = {
    ...explicitProvenance,
    source_urls: sourceUrls,
    field_evidence: fieldEvidence,
  };

  const reserved = new Set([
    "claims", "verification", "accepted",
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
        .filter(([key, value]) => !reserved.has(key) && (value === null || Array.isArray(value) || ["string", "number", "boolean"].includes(typeof value)))
        .map(([key, value]) => [key, value === null ? "" : Array.isArray(value) ? JSON.stringify(value) : String(value)])
    ),
    confidence_score: typeof record.confidence_score === "number" && Number.isFinite(record.confidence_score) ? record.confidence_score : null,
    claims: raw.claims as EntityRecord["claims"],
    verification: raw.verification as EntityRecord["verification"],
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
      : collection.status === "partial" ? "Partial"
      : collection.status === "exhausted" ? "Exhausted"
      : collection.status === "cancelled" ? "Cancelled"
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
  const [collection, datasetList, runList] = await Promise.all([collections.get(id), datasets.list(), runs.list(id)]);
  const run = runList.data[0] ? await runs.get(runList.data[0].id) : null;
  const history = run ? await runs.history(run.id) : null;
  const dataset = datasetList.data.filter((item) => item.collection_id === id && (!run || item.run_id === run.id))
    .sort((a, b) => b.created_at.localeCompare(a.created_at))[0];
  const response = dataset ? await datasets.records(dataset.id) : { data: [] };
  const records = response.data.map(toEntityRecord);
  const contract = collection.data_contract;
  const sourceMap = new Map<string, GroundingResponse["sources"][number]>();
  // Retrieved pages remain inspectable even when no record is accepted.
  for (const event of history?.data ?? []) {
    const sources = event.payload.sources;
    if (!Array.isArray(sources)) continue;
    for (const raw of sources) {
      if (!raw || typeof raw !== "object" || typeof raw.url !== "string") continue;
      let url: URL;
      try { url = new URL(raw.url); } catch { continue; }
      if (!["http:", "https:"].includes(url.protocol)) continue;
      sourceMap.set(raw.url, { url: raw.url, domain: url.hostname,
        title: typeof raw.title === "string" ? raw.title : url.hostname,
        live_status_code: typeof raw.http_status === "number" ? raw.http_status : undefined,
        fetched_at: typeof raw.fetched_at === "string" ? raw.fetched_at : undefined });
    }
  }
  for (const record of records) {
    for (const url of record.provenance.source_urls ?? []) {
      if (sourceMap.has(url)) continue;
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
  const terminalEvent = history?.data.filter(event => event.type.startsWith("run.")).at(-1);
  const stopReason = run?.error_message || (typeof terminalEvent?.payload.reason === "string" ? terminalEvent.payload.reason : undefined);
  return {
    task_id: id, dataset_id: dataset?.id, title: collection.title === collection.prompt.slice(0, 100) ? collection.prompt : collection.title,
    status: collection.status, updated_at: collection.updated_at,
    intent: { category: contract?.entity_type ?? "entity", target_entity: contract?.entity_type ?? "entity",
      needs_external_search: true, confidence: null, explanation: collection.prompt },
    contract: { target_entity_type: contract?.entity_type ?? "entity",
      fields: (contract?.fields ?? []).map((field) => ({ ...field, description: field.description ?? "" })),
      constraints: contract?.constraints ?? [], allowed_domains: contract?.allowed_domains ?? [] },
    sub_queries: [], records, sources: [...sourceMap.values()], run_id: run?.id,
    stop_reason: stopReason, extracted_count: run?.records_found,
    review_candidates: history?.review_candidates.map((raw, index) => toEntityRecord({ id: `review-${index}`, canonical_name: String(raw.canonical_name), status: "needs_review", confidence_score: null, confidence_breakdown: {} as ConfidenceBreakdown, primary_attributes: raw } as DatasetRecord)),
    summary_briefing: dataset ? `${records.length} records loaded with their stored source evidence.` : stopReason || "No records have met the evidence requirements yet.",
    workflow: { workflow_id: run?.id ?? id, stages: (run?.steps ?? []).map((s, i) => ({ stage_id: i + 1, stage_name: s.step_type,
      status: s.status as "pending" | "running" | "completed" | "failed" | "cancelled", duration_ms: s.duration_ms ?? null,
      details: s.started_at ? `Started ${new Date(s.started_at).toLocaleString()}` : "" })),
      total_duration_ms: run?.completed_at ? Date.parse(run.completed_at) - Date.parse(run.started_at) : 0 },
    total_records: records.length, verified_count: records.filter((r) => r.status === "verified").length,
    average_confidence: null,
  };
}

export async function executeGroundedSearch(prompt: string, modelSelection?: ModelSelection, onProgress?: (stage: string, run?: WorkflowRun) => void, sourcePolicy?: SourcePolicy, templateContract?: Partial<DataContract>, onStarted?: (runId: string) => void, discoverySources?: SourceCandidate["pages"]): Promise<GroundingResponse> {
  onProgress?.("planning");
  const collection = await collections.create(prompt.slice(0, 100), prompt, undefined, modelSelection, sourcePolicy, templateContract, discoverySources);
  const run = await collections.triggerRun(collection.id);
  onStarted?.(run.run_id);
  const deadline = Date.now() + 360_000;
  while (Date.now() < deadline) {
    const current = await runs.get(run.run_id);
    onProgress?.(current.current_stage, current);
    if (["completed", "partial", "exhausted"].includes(current.status)) {
      const result = await fetchTaskById(collection.id);
      return result;
    }
    if (["failed", "cancelled"].includes(current.status)) {
      throw new Error(current.error_message || `Collection run ${current.status}. Inspect the run for details.`);
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
