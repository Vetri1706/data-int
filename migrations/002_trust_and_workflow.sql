-- Preserve historical values; new observations may be genuinely unknown.
ALTER TABLE dataset_records ALTER COLUMN confidence_score DROP NOT NULL;
ALTER TABLE dataset_records ALTER COLUMN confidence_score DROP DEFAULT;
ALTER TABLE claims ALTER COLUMN confidence DROP NOT NULL;
ALTER TABLE claims ALTER COLUMN confidence DROP DEFAULT;
ALTER TABLE sources ALTER COLUMN extraction_success_rate DROP NOT NULL;
ALTER TABLE sources ALTER COLUMN extraction_success_rate DROP DEFAULT;
ALTER TABLE sources ALTER COLUMN freshness_score DROP NOT NULL;
ALTER TABLE sources ALTER COLUMN freshness_score DROP DEFAULT;
ALTER TABLE workflow_runs ADD COLUMN IF NOT EXISTS data_contract JSONB NOT NULL DEFAULT '{}';
CREATE TABLE IF NOT EXISTS review_candidates (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    run_id UUID NOT NULL REFERENCES workflow_runs(id) ON DELETE CASCADE,
    candidate JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_review_candidates_run ON review_candidates(run_id);
