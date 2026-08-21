# Singularity Labs — Architecture

## Current Status

The architecture is under active development.

Claude must inspect the existing repository before proposing major architectural changes.

---

# High-Level Architecture

Singularity Labs should eventually consist of:

```text
Data Sources
     ↓
Data Ingestion
     ↓
Data Cleaning / Normalization
     ↓
Structured Clinical Data
     ↓
Endpoint Classification
     ↓
Validation
     ↓
Analytics Layer
     ↓
Modeling Layer
     ↓
API / Application Layer
     ↓
Singularity Terminal
```

---

# Data Layer

Responsible for:

* ingestion
* normalization
* validation
* deduplication
* provenance
* structured representation

Raw data should remain distinguishable from transformed data.

## Data Sources

The initial authoritative external data source is **ClinicalTrials.gov**,
via its public REST API v2 (`https://clinicaltrials.gov/api/v2/studies`).
Verified 2026-08-13 via a live request: the API is public domain (U.S.
government work, operated by NLM/NIH), requires **no authentication or
API key**, returns JSON by default, and is rate-limited to roughly 50
requests/minute per IP. Source: https://clinicaltrials.gov/data-api/api.

Do not introduce a credential/auth requirement for this source unless
ClinicalTrials.gov's own documentation changes to require one -- verify
before assuming, the way this decision was verified rather than assumed.

### Source adapter pattern

Every external source is implemented as an adapter under
`src/singularity/sources/` that maps its own API/format onto
`singularity.schema.OutcomeRecord`, attaching a `singularity.schema.Provenance`
(source name, source record id, retrieval timestamp, exact request URL,
exact query parameters, and the raw source record or relevant slice of
it) to every record it produces. The adapter interface is defined in
`src/singularity/sources/base.py`.

This is deliberate: `OutcomeRecord` and `Provenance` are generic and
carry no ClinicalTrials.gov-specific fields, so adding a new source
later -- PubMed/NCBI, OpenAlex, FDA, PubChem, ChEMBL, UniProt, Open
Targets -- means writing a new adapter module that produces the same
two dataclasses, without changing the core schema, the classifier
(`singularity.endpoints`), the ingestion/validation layer
(`singularity.ingest`), or the audit pipeline (`singularity.audit`).
Only the ClinicalTrials.gov adapter is implemented so far; the others
are intentionally not started yet (see docs/roadmap.md) -- get the
first one right and reproducible before adding more.

### Trial entity (added Phase 2A, session 9)

`singularity.schema.Trial` is a first-class, protocol-level entity
distinct from `OutcomeRecord` (which represents a single outcome
*measurement*). A `Trial` and its `OutcomeRecord`s are linked by
`nct_id` -- a normal relational join (see the `trials`/`outcome_records`
foreign key in the Persistence Layer section below), not embedding.

`singularity.sources.clinicaltrials.extract_trial` maps
`protocolSection` fields onto `Trial`, using the same
`.get()`-with-`None`-default, never-fabricate approach as
`extract_outcome_records`. **Field-verification caveat**: only
`protocolSection.identificationModule.nctId` has been independently
verified against a live API response in this project; the other
`protocolSection` fields `extract_trial` reads
(`statusModule`, `designModule`, `sponsorCollaboratorsModule`,
`conditionsModule`, `armsInterventionsModule`) are based on the
publicly documented API v2 schema but were not re-verified against a
fresh live response in the session that wrote this code (web-fetch
tooling was unavailable that session). Spot-check against a real
response before trusting these fields at scale -- see
`docs/autonomous_state.md` "Session 9 Summary".

### Environment constraint (important, not hypothetical)

The sandboxed code-execution environment used in autonomous development
sessions has a restricted network egress list that does **not** include
`clinicaltrials.gov`. This means the adapter's HTTP calls cannot
currently be exercised end-to-end against the live API from within that
environment -- only via mocked transports in tests, or by a human /
differently-configured environment actually running it. This is a real,
verified constraint (confirmed by attempting the call and observing the
network policy), not an assumption. See `docs/autonomous_state.md` for
what was and wasn't actually run.

---

# Persistence Layer

**Added in Phase 2A (2026-08-14, session 9).** Chosen: **PostgreSQL**,
Python/FastAPI for the eventual API layer, Next.js/TypeScript for the
eventual frontend — these are the human-approved Phase 2 architecture
decisions. Only the persistence layer (this section) is built so far;
the API and frontend layers are explicitly NOT started yet.

Schema and migrations: `db/migrations/`. Full design rationale: `db/README.md`.

Three tables, deliberately separated by the observed-vs-derived
principle stated below:

* `trials` — protocol-level metadata, mirrors `singularity.schema.Trial`.
* `outcome_records` — raw, observed outcome measurements only, mirrors
  `singularity.schema.OutcomeRecord`. Contains no classifier output.
* `endpoint_classifications` — derived, versioned classifier output,
  mirrors `singularity.schema.ClassificationResult`, tagged with
  `singularity.endpoints.CLASSIFIER_VERSION` so re-classification runs
  add history rather than silently overwriting it.

Verified against a real local PostgreSQL 16 instance during
development, not just checked for SQL syntax — see
`docs/autonomous_state.md` "Session 9 Summary" and
`tests/test_db_schema.py` for the reproducible, automated version of
that verification. No ORM or migration-management tool has been
chosen yet — that's a Phase 2B (API layer) decision.

## Ingestion Pipeline (added Phase 2B-precursor, 2026-08-14, session 10)

`singularity.pipeline.run_clinicaltrials_ingestion` ties the adapter,
classifier, and persistence layer together end-to-end:

```
ClinicalTrialsAdapter.iter_studies()
       v
extract_trial() / extract_outcome_records_verbose()
       v
classify_outcome()
       v
db.upsert_trial() / db.replace_outcome_records_for_trial() / db.insert_classifications()
       v
PostgreSQL
```

**Idempotency design (important, read before changing):** the schema
deliberately has no natural key on `outcome_records` (real
ClinicalTrials.gov data contains genuine duplicate rows that must be
preserved — see `db/README.md`). Re-running ingestion for a trial uses
a **delete-then-insert-per-trial** strategy: existing
`outcome_records` for that `nct_id` are deleted and replaced, with old
`endpoint_classifications` cascading away automatically. This makes
re-runs idempotent (same input → same final state) at the cost of not
preserving row-level classification history across re-ingestion runs.
This is a defensible ETL pattern given the schema's own constraints,
but it's a design choice, not a mechanically forced one — see
`docs/autonomous_state.md` "Session 10 Summary" for the full reasoning
and an explicit flag for human review.

**Failure handling:** network/HTTP failures while fetching propagate
immediately and abort the run (fail loudly, no fallback). Per-study
data problems (malformed JSON, a DB constraint violation for one
trial) are caught, rolled back for that trial only, and reported in
the returned `IngestionReport` — the rest of the batch still ingests.
Verified with a real test injecting a realistic malformed-JSON shape
(a null where a list was expected) into one study out of three, and
confirming the other two still ingest correctly.

**What was verified vs. what requires a human to run:** all pipeline
tests (`tests/test_pipeline.py`) use a mocked HTTP transport against a
**real** local PostgreSQL 16 instance — the database-write path,
idempotency, partial-failure handling, provenance survival, and
observed/derived separation are all genuinely verified. **Real network
access to clinicaltrials.gov was never available in this sandbox** —
`scripts/run_clinicaltrials_ingestion.py` is the reproducible script
for a human to run true end-to-end (real network + real database)
ingestion and report back, following the same pattern as
`scripts/validate_real_clinicaltrials_data.py` from session 5.

---

## API Layer (Phase 2B, 2026-08-14, session 13)

**FastAPI, raw SQL via `psycopg2`, no ORM** — matches the session-9
approved stack, builds directly on `singularity.db`'s existing
write-function conventions rather than introducing a second data-
access pattern. `singularity.db` gained read functions (`get_trial`,
`list_trials`, `get_outcomes_for_trial`) alongside its existing write
functions; both return/accept plain dicts or the existing dataclasses,
never a new parallel data model.

**Read-only, deliberately minimal**: three endpoints
(`GET /trials/{nct_id}`, `GET /trials`, `GET /trials/{nct_id}/outcomes`).
No write/ingestion endpoints — ingestion stays a human-run script
(`scripts/run_clinicaltrials_ingestion.py`). No auth, no background
jobs, no GraphQL, no pagination beyond `LIMIT`/`OFFSET` (capped at
200). This is a backend milestone, not a public launch — see
`docs/roadmap.md` "Phase 2B" for the explicit list of what was
deliberately not built yet.

### The `value_type` field — presentation-safety fix, not a schema change

Session 11's real-data validation found a genuine, demonstrated risk:
`outcome_records.value` is a single column regardless of whether it
represents a rate, a raw count, a time duration, or something else
(e.g. a PK concentration). Two real rows from the same ingested
dataset: an ORR-classified row with `parameter=COUNT_OF_PARTICIPANTS,
value=23` is a raw responder **count** (the source's `denoms` field —
group size 66 — isn't captured anywhere); a safety-assessment row with
`parameter=NUMBER, unit="Percentage of participants", value=92.9` is a
genuine **rate**. Nothing in the schema itself distinguishes them.

`singularity.value_types.infer_value_type(parameter, unit)` is a pure,
independently-tested function (11 tests, every rule grounded in a real
`(parameter, unit)` pair from the session-11 dataset) that computes
`"count"`/`"rate"`/`"time"`/`"other"` at API-read time. Every
`OutcomeRecordResponse` includes this field. **This does not solve the
underlying data-completeness gap** — a "count" value still can't
become an actual rate without the denominator, which remains
uncaptured (deferred, per session-11/13 decisions) — it only prevents
a count from being *silently mislabeled* as a rate. See
`docs/data_dictionary.md` "Known limitation" for the full, still-open
gap.

### Response contract

`provenance_raw` (and all other provenance columns) are deliberately
**excluded** from every API response — large JSONB blobs, not needed
by a UI. `OutcomeRecordResponse` includes `endpoint`, `subtype`,
`confident`, `reason`, `classifier_version` alongside `value`/`unit`/
`parameter`/`value_type`, so a consumer always has the context needed
to interpret a value correctly, including low-confidence/unclassified
rows shown transparently (never filtered out silently).

### What was verified

All 9 API tests (`tests/test_api.py`) run against a real, disposable
local PostgreSQL 16 instance (same pattern as `test_db_schema.py`/
`test_pipeline.py`), seeding data via the actual, already-tested
`singularity.db` write functions — not hand-written SQL — so these
tests exercise the real read-after-write path. One test (OpenAPI
schema well-formedness) needs no database. Full suite: 100/100.

**Not yet verified**: the API has not been run against the real
Colab-ingested database (only against disposable local scratch
databases seeded with realistic-but-synthetic data). The remaining
`Trial` field-verification gap from session 9 (`official_title`,
`interventions`, `start_date`, `completion_date`, `enrollment_count`
not yet confirmed against a live response) is unchanged — the
session-11 Colab export didn't include those columns, and closing this
gap explicitly did not block Phase 2B per instruction.

---

# Endpoint Layer

Responsible for:

* endpoint extraction
* endpoint classification
* endpoint normalization
* subtype identification
* ambiguity detection

Canonical endpoint categories currently include:

* PFS
* OS
* ORR
* DOR
* DFS

---

# Analytics Layer

Responsible for:

* descriptive statistics
* trial comparisons
* treatment comparisons
* endpoint distributions
* subgroup analysis
* visualization-ready datasets

Analytics must preserve the distinction between observed and derived values.

---

# Modeling Layer

Responsible for:

* feature generation
* model training
* validation
* evaluation
* calibration
* explainability

Models must not bypass the validated data layer.

---

# Application Layer

Responsible for:

* search
* filtering
* trial exploration
* drug exploration
* company exploration
* analytics
* visualization
* AI-assisted research workflows

---

# UI Layer

The UI should present information clearly and efficiently.

The intended visual direction is:

* scientific
* quantitative
* minimal
* sophisticated
* information-dense
* terminal-inspired

The visual design must support analytical workflows rather than distract from them.

---

# Architectural Principle

Prefer a reliable, understandable architecture over unnecessary complexity.

Do not introduce microservices, databases, queues, model-serving infrastructure, or other complex infrastructure unless there is a demonstrated need.
