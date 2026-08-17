-- Migration 0003: endpoint_classifications
--
-- DERIVED data: the output of running singularity.endpoints.classify_outcome
-- against an outcome_records row. Kept in its own table, separate from
-- outcome_records, so:
--   1. Observed vs. derived data stays structurally distinct (per
--      docs/architecture.md: "Analytics must preserve the distinction
--      between observed and derived values", and Claude.md section 7).
--   2. Re-running the classifier after a future fix (this project has
--      changed classification logic in 4 of its first 9 sessions) adds
--      a NEW row rather than silently overwriting history -- the full
--      classification history for a given outcome_record is queryable.
--   3. classifier_version makes it possible to ask "what did version X
--      of the classifier say about this row" reproducibly.

CREATE TABLE endpoint_classifications (
    id                  BIGSERIAL PRIMARY KEY,
    outcome_record_id   BIGINT NOT NULL REFERENCES outcome_records (id) ON DELETE CASCADE,

    -- Mirrors singularity.schema.ClassificationResult exactly.
    endpoint            TEXT,       -- one of PFS/OS/ORR/DOR/DFS, or NULL
    subtype             TEXT,       -- e.g. 'PFS6', 'median_or_time_to_event', or NULL
    confident           BOOLEAN NOT NULL,
    reason              TEXT NOT NULL,

    -- singularity.endpoints.CLASSIFIER_VERSION at the time this
    -- classification was produced. Never NULL -- every classification
    -- must be traceable to the exact logic version that produced it.
    classifier_version  TEXT NOT NULL,

    classified_at        TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- A canonical endpoint value must be one of the five documented
    -- categories -- this constraint exists to catch a future bug
    -- (e.g. a typo'd endpoint string) at write time rather than
    -- silently persisting an invalid category.
    CONSTRAINT chk_endpoint_is_canonical_or_null
        CHECK (endpoint IS NULL OR endpoint IN ('PFS', 'OS', 'ORR', 'DOR', 'DFS'))
);

CREATE INDEX idx_endpoint_classifications_outcome_record_id
    ON endpoint_classifications (outcome_record_id);
CREATE INDEX idx_endpoint_classifications_endpoint
    ON endpoint_classifications (endpoint);
CREATE INDEX idx_endpoint_classifications_classifier_version
    ON endpoint_classifications (classifier_version);

-- Convenience view: the LATEST classification per outcome_record, by
-- classified_at. Application code should query this view rather than
-- endpoint_classifications directly for "current" classification state,
-- so historical rows are preserved without every consumer needing to
-- re-implement "most recent" logic.
CREATE VIEW latest_endpoint_classifications AS
SELECT DISTINCT ON (outcome_record_id)
    outcome_record_id, endpoint, subtype, confident, reason,
    classifier_version, classified_at
FROM endpoint_classifications
ORDER BY outcome_record_id, classified_at DESC;

COMMENT ON TABLE endpoint_classifications IS
  'Derived classifier output, versioned and kept separate from '
  'observed data in outcome_records. See '
  'src/singularity/endpoints.py::classify_outcome and '
  'docs/endpoint_taxonomy_analysis.md for what the current classifier '
  'does and does not cover -- it is explicitly NOT validated or '
  'production-ready as of 2026-08-14 (see docs/autonomous_state.md).';
