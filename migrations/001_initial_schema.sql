-- =============================================================================
-- Datavault Platform — Full PostgreSQL Schema
-- Implements: HLD from Architecture Design Document
-- =============================================================================

-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- =============================================================================
-- USERS & AUTH
-- =============================================================================

CREATE TABLE users (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email         TEXT NOT NULL UNIQUE,
    name          TEXT,
    password_hash TEXT,                    -- NULL for OAuth users
    provider      TEXT DEFAULT 'local',    -- 'local' | 'google' | 'github'
    provider_id   TEXT,
    avatar_url    TEXT,
    is_active     BOOLEAN NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE sessions (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id       UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash    TEXT NOT NULL UNIQUE,   -- SHA-256 of bearer token
    expires_at    TIMESTAMPTZ NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_sessions_token_hash ON sessions(token_hash);
CREATE INDEX idx_sessions_user_id    ON sessions(user_id);

-- =============================================================================
-- WORKSPACES & MEMBERSHIP
-- =============================================================================

CREATE TABLE workspaces (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    owner_id    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    slug        TEXT NOT NULL UNIQUE,
    plan        TEXT NOT NULL DEFAULT 'free',  -- 'free' | 'pro' | 'enterprise'
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE workspace_members (
    id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    user_id      UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role         TEXT NOT NULL DEFAULT 'viewer',  -- 'owner' | 'admin' | 'editor' | 'viewer'
    joined_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(workspace_id, user_id)
);

CREATE INDEX idx_workspace_members_workspace ON workspace_members(workspace_id);
CREATE INDEX idx_workspace_members_user      ON workspace_members(user_id);

-- =============================================================================
-- USER PREFERENCES
-- =============================================================================

CREATE TABLE user_preferences (
    id                    UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id               UUID NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    workspace_id          UUID REFERENCES workspaces(id) ON DELETE SET NULL,
    default_target_count  INTEGER NOT NULL DEFAULT 100,
    default_freshness_days INTEGER,
    preferred_regions     TEXT[] NOT NULL DEFAULT '{}',
    preferred_source_types TEXT[] NOT NULL DEFAULT '{}',
    default_export_format TEXT NOT NULL DEFAULT 'csv',   -- 'csv' | 'json' | 'xlsx'
    saved_categories      TEXT[] NOT NULL DEFAULT '{}',
    blocked_domains       TEXT[] NOT NULL DEFAULT '{}',
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =============================================================================
-- COLLECTIONS (User's saved intelligence requirements)
-- =============================================================================

CREATE TABLE collections (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    workspace_id  UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    created_by    UUID NOT NULL REFERENCES users(id),
    title         TEXT NOT NULL,
    prompt        TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'draft',
    -- 'draft' | 'planning' | 'running' | 'paused' | 'needs_review'
    -- | 'completed' | 'failed' | 'cancelled'
    data_contract JSONB NOT NULL DEFAULT '{}',
    tags          TEXT[] NOT NULL DEFAULT '{}',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_collections_workspace  ON collections(workspace_id);
CREATE INDEX idx_collections_status     ON collections(status);
CREATE INDEX idx_collections_created_by ON collections(created_by);

-- =============================================================================
-- WORKFLOW RUNS (Each execution of a collection)
-- =============================================================================

CREATE TABLE workflow_runs (
    id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    collection_id    UUID NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
    triggered_by     UUID REFERENCES users(id),
    status           TEXT NOT NULL DEFAULT 'pending',
    -- 'pending' | 'planning' | 'discovering' | 'collecting'
    -- | 'extracting' | 'normalizing' | 'validating'
    -- | 'deduplicating' | 'finalizing' | 'completed' | 'failed' | 'cancelled'
    current_stage    TEXT NOT NULL DEFAULT 'planning',
    iteration        INTEGER NOT NULL DEFAULT 0,
    records_found    INTEGER NOT NULL DEFAULT 0,
    records_verified INTEGER NOT NULL DEFAULT 0,
    avg_confidence   REAL,
    error_message    TEXT,
    started_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at     TIMESTAMPTZ
);

CREATE INDEX idx_workflow_runs_collection ON workflow_runs(collection_id);
CREATE INDEX idx_workflow_runs_status     ON workflow_runs(status);

-- =============================================================================
-- WORKFLOW STEPS (Granular step log inside each run)
-- =============================================================================

CREATE TABLE workflow_steps (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    run_id        UUID NOT NULL REFERENCES workflow_runs(id) ON DELETE CASCADE,
    step_type     TEXT NOT NULL,
    -- 'search' | 'crawl' | 'extract' | 'normalize'
    -- | 'resolve_entity' | 'validate' | 'verify_evidence' | 'export'
    status        TEXT NOT NULL DEFAULT 'pending',
    -- 'pending' | 'running' | 'completed' | 'failed' | 'skipped'
    input_ref     TEXT,                 -- object storage key or JSON snapshot
    output_ref    TEXT,
    duration_ms   INTEGER,
    metadata      JSONB NOT NULL DEFAULT '{}',
    started_at    TIMESTAMPTZ,
    completed_at  TIMESTAMPTZ
);

CREATE INDEX idx_workflow_steps_run ON workflow_steps(run_id);

-- =============================================================================
-- SOURCE REGISTRY
-- =============================================================================

CREATE TABLE sources (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    workspace_id            UUID REFERENCES workspaces(id) ON DELETE CASCADE,
    domain                  TEXT NOT NULL,
    display_name            TEXT,
    source_type             TEXT NOT NULL DEFAULT 'general',
    -- 'official_company' | 'news' | 'academic' | 'regulatory'
    -- | 'social' | 'api' | 'general'
    trust_tier              TEXT NOT NULL DEFAULT 'tier2',  -- 'tier1' | 'tier2' | 'tier3'
    extraction_success_rate REAL,
    freshness_score         REAL,
    last_success_at         TIMESTAMPTZ,
    last_checked_at         TIMESTAMPTZ,
    last_status_code        INTEGER,
    enabled                 BOOLEAN NOT NULL DEFAULT TRUE,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(workspace_id, domain)
);

CREATE INDEX idx_sources_domain  ON sources(domain);
CREATE INDEX idx_sources_enabled ON sources(enabled);

-- =============================================================================
-- SEARCH QUERIES & RESULTS
-- =============================================================================

CREATE TABLE search_queries (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    run_id        UUID NOT NULL REFERENCES workflow_runs(id) ON DELETE CASCADE,
    query_text    TEXT NOT NULL,
    provider      TEXT NOT NULL DEFAULT 'searxng',
    filters       JSONB NOT NULL DEFAULT '{}',
    result_count  INTEGER NOT NULL DEFAULT 0,
    duration_ms   INTEGER,
    executed_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE search_results (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    query_id      UUID NOT NULL REFERENCES search_queries(id) ON DELETE CASCADE,
    url           TEXT NOT NULL,
    title         TEXT,
    snippet       TEXT,
    rank_position INTEGER NOT NULL DEFAULT 0,
    collected     BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX idx_search_results_query   ON search_results(query_id);
CREATE INDEX idx_search_results_url     ON search_results(url);

-- =============================================================================
-- DOCUMENTS (Fetched pages / crawled content)
-- =============================================================================

CREATE TABLE documents (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    run_id        UUID REFERENCES workflow_runs(id) ON DELETE CASCADE,
    source_id     UUID REFERENCES sources(id) ON DELETE SET NULL,
    url           TEXT NOT NULL,
    final_url     TEXT,            -- after redirects
    content_hash  TEXT,            -- SHA-256 of body
    content_type  TEXT,
    status_code   INTEGER,
    object_path   TEXT,            -- S3/object storage key for raw HTML
    metadata      JSONB NOT NULL DEFAULT '{}',
    fetched_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_documents_run         ON documents(run_id);
CREATE INDEX idx_documents_url         ON documents(url);
CREATE INDEX idx_documents_content_hash ON documents(content_hash);

-- =============================================================================
-- ENTITIES & ALIASES (Resolved canonical records)
-- =============================================================================

CREATE TABLE entities (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    workspace_id    UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    entity_type     TEXT NOT NULL,      -- 'company' | 'job' | 'person' | 'product' | ...
    canonical_name  TEXT NOT NULL,
    canonical_key   TEXT,               -- normalized lookup key (domain / phone / ein)
    metadata        JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_entities_workspace    ON entities(workspace_id);
CREATE INDEX idx_entities_canonical_key ON entities(canonical_key);
CREATE INDEX idx_entities_type         ON entities(entity_type);

CREATE TABLE entity_aliases (
    id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    entity_id         UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    value             TEXT NOT NULL,
    normalized_value  TEXT NOT NULL
);

CREATE INDEX idx_entity_aliases_entity    ON entity_aliases(entity_id);
CREATE INDEX idx_entity_aliases_normalized ON entity_aliases(normalized_value);

-- =============================================================================
-- CLAIMS (Intermediate extraction layer)
-- =============================================================================

CREATE TABLE claims (
    id                    UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    run_id                UUID NOT NULL REFERENCES workflow_runs(id) ON DELETE CASCADE,
    document_id           UUID REFERENCES documents(id) ON DELETE SET NULL,
    entity_id             UUID REFERENCES entities(id) ON DELETE CASCADE,
    field_name            TEXT NOT NULL,
    field_value           JSONB NOT NULL,
    extraction_method     TEXT NOT NULL DEFAULT 'rule_based',
    -- 'api' | 'json_ld' | 'html_selector' | 'table' | 'regex' | 'llm'
    confidence            REAL,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_claims_run        ON claims(run_id);
CREATE INDEX idx_claims_entity     ON claims(entity_id);
CREATE INDEX idx_claims_field_name ON claims(field_name);

-- =============================================================================
-- EVIDENCE (Field-level provenance chain)
-- =============================================================================

CREATE TABLE evidence (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    claim_id        UUID NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
    document_id     UUID REFERENCES documents(id) ON DELETE SET NULL,
    url             TEXT NOT NULL,
    text_excerpt    TEXT,               -- verbatim quote
    selector        TEXT,               -- CSS/XPath selector used
    content_hash    TEXT,
    retrieved_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_evidence_claim    ON evidence(claim_id);
CREATE INDEX idx_evidence_document ON evidence(document_id);

-- =============================================================================
-- DATASETS & RECORDS (Finalized, validated output)
-- =============================================================================

CREATE TABLE datasets (
    id             UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    collection_id  UUID NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
    run_id         UUID REFERENCES workflow_runs(id) ON DELETE SET NULL,
    workspace_id   UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    name           TEXT NOT NULL,
    entity_type    TEXT NOT NULL,
    record_count   INTEGER NOT NULL DEFAULT 0,
    avg_confidence REAL,
    schema         JSONB NOT NULL DEFAULT '{}',
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_datasets_collection ON datasets(collection_id);
CREATE INDEX idx_datasets_workspace  ON datasets(workspace_id);

CREATE TABLE dataset_records (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    dataset_id      UUID NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    entity_id       UUID REFERENCES entities(id) ON DELETE SET NULL,
    canonical_name  TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'needs_review',
    -- 'verified' | 'needs_review' | 'draft' | 'rejected' | 'conflicting'
    confidence_score REAL,
    confidence_breakdown JSONB NOT NULL DEFAULT '{}',
    -- { source_authority, extraction_certainty, agreement, freshness, completeness }
    primary_attributes JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_dataset_records_dataset    ON dataset_records(dataset_id);
CREATE INDEX idx_dataset_records_entity     ON dataset_records(entity_id);
CREATE INDEX idx_dataset_records_status     ON dataset_records(status);
CREATE INDEX idx_dataset_records_confidence ON dataset_records(confidence_score DESC);

-- =============================================================================
-- VALIDATION RESULTS
-- =============================================================================

CREATE TABLE validation_results (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    record_id       UUID NOT NULL REFERENCES dataset_records(id) ON DELETE CASCADE,
    validator_type  TEXT NOT NULL,
    -- 'schema' | 'constraint' | 'evidence' | 'semantic' | 'cross_source'
    passed          BOOLEAN NOT NULL,
    score           REAL,
    details         TEXT,
    validated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_validation_results_record ON validation_results(record_id);

-- =============================================================================
-- EXPORTS
-- =============================================================================

CREATE TABLE exports (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    dataset_id    UUID NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    requested_by  UUID REFERENCES users(id) ON DELETE SET NULL,
    format        TEXT NOT NULL DEFAULT 'csv',  -- 'csv' | 'json' | 'xlsx'
    status        TEXT NOT NULL DEFAULT 'pending',
    -- 'pending' | 'processing' | 'completed' | 'failed'
    object_path   TEXT,                          -- object storage key
    file_size     BIGINT,
    error_message TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at  TIMESTAMPTZ
);

CREATE INDEX idx_exports_dataset ON exports(dataset_id);

-- =============================================================================
-- SSE / REAL-TIME EVENT LOG
-- =============================================================================

CREATE TABLE run_events (
    id          BIGSERIAL PRIMARY KEY,
    run_id      UUID NOT NULL REFERENCES workflow_runs(id) ON DELETE CASCADE,
    event_type  TEXT NOT NULL,
    payload     JSONB NOT NULL DEFAULT '{}',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_run_events_run ON run_events(run_id);
CREATE INDEX idx_run_events_created ON run_events(created_at DESC);

-- =============================================================================
-- HELPER: auto-update updated_at on mutation
-- =============================================================================

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_users_updated            BEFORE UPDATE ON users            FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_workspaces_updated       BEFORE UPDATE ON workspaces       FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_collections_updated      BEFORE UPDATE ON collections      FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_sources_updated          BEFORE UPDATE ON sources          FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_entities_updated         BEFORE UPDATE ON entities         FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_datasets_updated         BEFORE UPDATE ON datasets         FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_dataset_records_updated  BEFORE UPDATE ON dataset_records  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_user_preferences_updated BEFORE UPDATE ON user_preferences FOR EACH ROW EXECUTE FUNCTION set_updated_at();
