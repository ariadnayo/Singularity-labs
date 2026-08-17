-- Migration 0002: outcome_records
--
-- Raw, OBSERVED outcome measurements only -- mirrors
-- singularity.schema.OutcomeRecord exactly. Deliberately contains NO
-- classifier output (no endpoint/subtype/confidence columns here) --
-- see 0003_create_endpoint_classifications.sql and db/README.md for
-- why that's a separate, versioned table.

CREATE TABLE outcome_records (
    -- Surrogate key: (nct_id, title, group, timeframe, ...) is NOT a
    -- reliable natural key. Real ClinicalTrials.gov data contains
    -- genuine duplicate rows (see src/singularity/ingest.py's
    -- ValidationReport.duplicate_rows, and ingest.py's own comment:
    -- duplicates are detected and reported, never silently removed).
    -- A surrogate key preserves that duplication faithfully instead of
    -- forcing artificial uniqueness.
    id                  BIGSERIAL PRIMARY KEY,

    nct_id              TEXT NOT NULL REFERENCES trials (nct_id),
    title               TEXT NOT NULL,
    parameter           TEXT,
    unit                TEXT,
    timeframe           TEXT,
    -- "group" is a reserved word in SQL; named group_name to match
    -- singularity.schema.OutcomeRecord.group without needing quoting
    -- everywhere.
    group_name          TEXT,
    value               DOUBLE PRECISION,

    -- Provenance (mirrors singularity.schema.Provenance exactly).
    provenance_source             TEXT NOT NULL,
    provenance_source_record_id   TEXT NOT NULL,
    provenance_retrieved_at       TIMESTAMPTZ NOT NULL,
    provenance_request_url        TEXT NOT NULL,
    provenance_query_params       JSONB NOT NULL DEFAULT '{}'::jsonb,
    provenance_raw                JSONB,

    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_outcome_records_nct_id ON outcome_records (nct_id);
CREATE INDEX idx_outcome_records_title ON outcome_records (title);

COMMENT ON TABLE outcome_records IS
  'Raw, observed outcome measurements only -- mirrors '
  'singularity.schema.OutcomeRecord. Never mixes in derived classifier '
  'output; see endpoint_classifications for that.';
COMMENT ON COLUMN outcome_records.value IS
  'The value as extracted from the source, unmodified. Must always be '
  'interpreted together with parameter/unit/timeframe/title/group, per '
  'docs/data_dictionary.md -- never independently.';
