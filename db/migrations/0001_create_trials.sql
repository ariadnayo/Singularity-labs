-- Migration 0001: trials
--
-- Protocol-level trial metadata, mirroring singularity.schema.Trial.
-- See db/README.md for the design rationale (observed-vs-derived
-- separation, why dates are TEXT not DATE, provenance columns).

CREATE TABLE trials (
    nct_id              TEXT PRIMARY KEY,
    brief_title         TEXT,
    official_title      TEXT,
    overall_status      TEXT,
    -- Stored as TEXT[] rather than a normalized lookup table for now --
    -- Phase 2A scope is the core schema, not a controlled-vocabulary
    -- layer. Revisit if/when phase/condition normalization is needed.
    phases              TEXT[],
    study_type          TEXT,
    conditions          TEXT[],
    lead_sponsor        TEXT,
    interventions       TEXT[],
    -- Dates are stored EXACTLY as reported by the source (e.g. may be
    -- "2025-01" with no day, or "2025-01-15"). Deliberately TEXT, not
    -- DATE: parsing/normalizing a partial date is a data transformation,
    -- and per Claude.md section 5 ("never silently transform clinical
    -- measurements... every transformation must be explicit and
    -- reproducible"), that must be an explicit, separate, documented
    -- step -- not baked into the column type where it would silently
    -- fail or truncate information for partial dates.
    start_date          TEXT,
    completion_date     TEXT,
    enrollment_count    INTEGER,

    -- Provenance (mirrors singularity.schema.Provenance exactly).
    provenance_source             TEXT NOT NULL,
    provenance_source_record_id   TEXT NOT NULL,
    provenance_retrieved_at       TIMESTAMPTZ NOT NULL,
    provenance_request_url        TEXT NOT NULL,
    provenance_query_params       JSONB NOT NULL DEFAULT '{}'::jsonb,
    provenance_raw                JSONB,

    -- Row-management metadata (distinct from provenance_retrieved_at,
    -- which is when the SOURCE data was fetched -- this is when this
    -- row was written into OUR database, which may be later).
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_trials_overall_status ON trials (overall_status);
CREATE INDEX idx_trials_conditions ON trials USING GIN (conditions);
CREATE INDEX idx_trials_phases ON trials USING GIN (phases);
CREATE INDEX idx_trials_lead_sponsor ON trials (lead_sponsor);

COMMENT ON TABLE trials IS
  'Protocol-level trial metadata. See src/singularity/schema.py::Trial '
  'and src/singularity/sources/clinicaltrials.py::extract_trial. '
  'FIELD-VERIFICATION CAVEAT: only nct_id has been independently '
  'verified against a live ClinicalTrials.gov API v2 response as of '
  '2026-08-14 (session 9) -- see docs/autonomous_state.md.';
