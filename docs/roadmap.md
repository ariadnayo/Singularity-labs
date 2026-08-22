# Singularity Labs — Development Roadmap

## Current Objective

Build a scientifically rigorous clinical and biomedical intelligence platform.

The current priority is to establish a reliable clinical-outcome data foundation before expanding into advanced modeling and intelligence features.

---

# Phase 1 — Data Foundation

* [x] Audit the current data pipeline — searched full repo; no real
      pipeline or dataset exists yet (see `docs/autonomous_state.md`,
      "Data Source Status"). Ingestion/validation/classification code
      is implemented and tested but has never run on real data.
* [x] Document the complete outcome schema — `docs/data_dictionary.md`
      + `src/singularity/schema.py`.
* [ ] Validate `outcomes_df["endpoint"]` — blocked, no real data.
* [x] Build endpoint classification validation —
      `src/singularity/endpoints.py`, `tests/test_endpoints.py`.
* [ ] Investigate unclassified outcomes — blocked, no real data.
* [ ] Investigate suspicious PFS classifications — blocked, no real data.
* [ ] Investigate suspicious OS classifications — blocked, no real data.
* [ ] Investigate suspicious ORR classifications — blocked, no real data.
* [ ] Investigate suspicious DOR classifications — blocked, no real data.
* [ ] Investigate suspicious DFS classifications — blocked, no real data.
* [ ] Normalize endpoint terminology — subtype distinction exists in
      the classifier, but full terminology normalization is not built.
* [ ] Normalize units — not built.
* [x] Handle missing values consistently —
      `src/singularity/ingest.py` (`ValidationReport`).
* [x] Detect duplicate outcome records — `src/singularity/ingest.py`
      (detected and reported, never silently removed).
* [ ] Preserve source provenance — not built; ingestion records the
      source file path in `ValidationReport` but not per-row provenance.
* [x] Build automated data-quality reporting —
      `src/singularity/audit.py` (`AuditReport`, markdown output).
* [ ] Create a manually verified endpoint test set — the mock fixtures
      in `tests/` exercise classifier logic but are not a manually
      verified sample of real trial data.

---

# Phase 1a — ClinicalTrials.gov Integration (initial authoritative source)

* [x] Determine whether ClinicalTrials.gov API requires authentication
      — verified live: it does not (public, no key, JSON, ~50 req/min
      rate limit). See `docs/architecture.md` § Data Sources.
* [x] Design a source-adapter interface that lets future sources
      (PubMed/NCBI, OpenAlex, FDA, PubChem, ChEMBL, UniProt, Open
      Targets) be added without changing `OutcomeRecord` —
      `src/singularity/sources/base.py`.
* [x] Implement the ClinicalTrials.gov API v2 adapter —
      `src/singularity/sources/clinicaltrials.py` (pagination, rate-
      limit-respecting delay, provenance capture, results-section →
      OutcomeRecord mapping).
* [x] Add `Provenance` to the core schema (source, source record id,
      retrieval timestamp, request URL, query params, raw record) —
      `src/singularity/schema.py`.
* [x] Add mocked adapter/integration tests, clearly separated from any
      real data — `tests/test_clinicaltrials_adapter.py` (9 tests).
* [x] Fetch a real, controlled sample of oncology studies and run the
      classifier against real (not mock) ClinicalTrials.gov data —
      done 2026-08-13: 7 real trials, 33 real outcome titles, full
      pipeline run, raw/normalized data saved separately with
      provenance (`data/clinicaltrials_raw/`,
      `data/clinicaltrials_normalized/`). See `docs/autonomous_state.md`
      "Session 4 Summary" for the complete real-data validation run.
* [x] Manually spot-check ≥20 real records against source — done: all
      33 real rows spot-checked (target was ≥20), documented in a table
      in `docs/autonomous_state.md` with per-row correctness.
* [x] Document every classification error/ambiguity found — done: 1
      real bug found (follow-up-ceiling timeframe mistaken for a fixed
      PFS/OS timepoint), root-caused, fixed, and regression-tested
      (`tests/test_endpoints.py`, 2 new tests using the real title/
      timeframe pair that exposed it).
* [x] Validate the value/group extraction path
      (`extract_outcome_records()`'s measurement parsing) against a
      real study with `hasResults: true` — the human ran real
      extraction externally (Google Colab, 2026-08-14): 20 real
      completed studies, 20/20 hasResults=true, 3,552 real
      OutcomeRecords, 3,497 flagged for review. `records.csv` and
      `audit_report.md` were provided and used directly for the
      analysis and fix cycle below — this environment's own network
      constraint (documented in session 5) no longer blocks progress,
      since the human's environment supplied the real data instead.
* [x] Analyze the flagged rows, cluster into failure-mode patterns,
      and get human approval before touching the classifier — done
      2026-08-14: 15 distinct patterns identified and quantified from
      the real 3,497 flagged rows, categorized (A: bug / B: genuine
      ambiguity / C: correctly excluded / D: missing taxonomy / E:
      extraction issue / F: long tail), with a FIX NOW / KEEP AS IS /
      INVESTIGATE / EXCLUDE recommendation. See
      `docs/autonomous_state.md` "Session 6 Summary" (the analysis
      itself, prior to any code change, isn't separately filed — its
      conclusions are what session 6 implemented).
* [x] Implement ONLY the approved Category A fixes (ORR/CR+PR/RECIST
      synonyms; year-based fixed-timepoint OS phrasing) — done
      2026-08-14. 13 new regression tests (7 + 4 + 2 for two decimal-
      number bugs found along the way, one of which was a pre-existing,
      previously-undetected bug from session 4). Full suite: 47/47
      passing. Re-validated against the real 3,552-record dataset with
      a complete row-level before/after diff — see
      `docs/autonomous_state.md` "Session 6 Summary" for the exact
      numbers (27 rows gained correct classification, 2 more fixed by
      the decimal-month bug fix, 20 rows corrected from wrongly-
      confident to correctly-flagged; net flagged count unchanged at
      3,497 by coincidence of these effects offsetting).
* [x] Produce a taxonomy/scoping analysis of the remaining
      uncategorized rows before touching the classifier further — done
      2026-08-14 (session 7), `docs/endpoint_taxonomy_analysis.md`. 115
      rows / 40 titles / 11 trials reclustered from real data, 15
      distinct endpoint/measure families identified and quantified,
      each assigned a category (map to existing endpoint / new
      canonical endpoint / distinct subtype / leave unclassified) with
      rationale. No canonical-endpoint additions recommended.
* [x] Implement human-approved taxonomy decision, item #1 only (EFS,
      pCR, BOR as named exclusions) — done 2026-08-14 (session 8).
      Added to `_NON_CANONICAL_PATTERNS`, same mechanism as DCR/CBR/TTP.
      4 new regression tests. Full suite: 51/51 passing. Re-validated:
      `endpoint`/`subtype`/`confident` byte-identical for all 3,552
      real rows (0 classification changes); 33 rows gained a specific,
      documented reason string; 274 pre-existing rows got a cosmetic-
      only reason-text update from a shared template string.
* [ ] Items #2–#4 of the session-7 decision deliberately NOT
      implemented, per explicit instruction: TTR stays unclassified,
      no special handling (1 row). Hematologic CRi / leukemia-style
      "Complete or Partial Remission" stays a documented open scope
      question, not resolved (3 rows). OR-by-modality fragmentation
      (18 rows) stays unclassified pending a future aggregation/
      data-model decision, not a classifier change.
* [ ] **The classifier is explicitly NOT validated or production-
      ready.** No further classifier changes are approved or pending.
      Any future work requires a new explicit decision from the human
      (e.g. hematologic-malignancy scope, OR-by-modality aggregation
      design).
* [ ] Only after any such future decision (and resulting fixes are
      implemented, tested, and re-validated the same way): proceed to
      large-scale ingestion, additional sources (PubMed/NCBI, OpenAlex,
      FDA, PubChem, ChEMBL, UniProt, Open Targets), ML modeling, or UI
      work — explicitly not started yet, per instruction.

## Phase 2 — Clinical Trial Intelligence

### Phase 2A — Trial/Data Architecture (2026-08-14, session 9)

Human-approved architecture decisions: PostgreSQL for persistent
storage, Python/FastAPI for the backend/API (not started yet), Next.js
+ TypeScript for the frontend (not started yet). Existing Python data/
classification layer kept intact, built around rather than rewritten.

* [x] Design a first-class `Trial` entity connecting protocol-level
      ClinicalTrials.gov data to `OutcomeRecord` — `singularity.schema.Trial`,
      linked to outcome records by `nct_id` (relational join, not
      embedding).
* [x] Extend the ClinicalTrials.gov adapter to extract `protocolSection`
      fields — `singularity.sources.clinicaltrials.extract_trial` +
      `ClinicalTrialsAdapter.fetch_trials`. Field-verification caveat
      disclosed: only `nct_id` independently verified live this
      project; other `protocolSection` fields based on documented
      schema, not re-verified this session (web-fetch tooling
      unavailable) — see `docs/autonomous_state.md` "Session 9 Summary".
* [x] Design the PostgreSQL schema/migrations — `db/migrations/0001-0003`.
      Observed data (`outcome_records`) and derived classifier output
      (`endpoint_classifications`, versioned via `CLASSIFIER_VERSION`)
      deliberately kept in separate tables. Verified against a real
      local PostgreSQL 16 instance (migrations run cleanly, real
      dataclass round-trip confirmed, FK/CHECK constraints confirmed
      to actually reject bad data) — not just checked for SQL syntax.
* [x] Mock fixtures and tests before relying on real network access —
      `tests/test_trial_extraction.py` (7 tests, synthetic protocol
      data). DB tests (`tests/test_db_schema.py`, 6 tests) skip
      gracefully (not fail) when no PostgreSQL instance is reachable.
* [x] Existing validated classifier preserved, not rewritten — only an
      additive `CLASSIFIER_VERSION` constant was added (metadata only,
      zero behavior change, confirmed by full suite passing unchanged).
* [x] Full test suite passing: 64/64 (58 pre-existing + 6 new DB tests;
      Trial-extraction tests bring the adapter/schema total to 65 lines
      of new test coverage across two files).

**What remains before Phase 2B (API layer)**: no ingestion-to-database
orchestration code exists yet (the round-trip tests insert directly;
there's no `ingest_trial_and_outcomes(study) -> None` pipeline
function yet). No FastAPI service exists. No decision has been made on
an ORM/migration-management tool (deferred to Phase 2B, since the
choice depends on the API framework's own conventions). The
`protocolSection` field-verification caveat above should be resolved
(a live spot-check) before Phase 2B trusts `Trial` data at scale.

### Phase 2A-2 — Ingestion Orchestration Pipeline (2026-08-14, session 10)

Closes the "no orchestration code exists yet" gap noted above.

* [x] Build the orchestration layer: fetch → extract → classify →
      persist — `singularity.pipeline.run_clinicaltrials_ingestion`.
      Full diagram and design rationale in `docs/architecture.md`
      "Ingestion Pipeline".
* [x] Handles duplicates/idempotent re-runs safely — delete-then-
      insert-per-trial strategy, verified with a real test that runs
      the same ingestion twice and confirms row counts don't double,
      and a second test confirming a re-run with genuinely changed
      source data (e.g. updated trial status) is correctly reflected.
      **Flagged for human review**: this is a design choice given the
      schema's no-natural-key decision, not a mechanically forced one
      — see `docs/autonomous_state.md` "Session 10 Summary".
* [x] Does not silently discard malformed records —
      `extract_outcome_records_verbose` (new, backward-compatible
      addition alongside the unchanged `extract_outcome_records`)
      reports every skipped outcome measure with a reason, surfaced in
      `IngestionReport.skipped_outcome_details`.
* [x] Fails loudly on network/API problems; catches and reports
      per-study data problems without aborting the batch — verified
      with a real test injecting a realistic malformed-JSON shape (a
      null where a list was expected) into one study out of three, and
      confirming the other two still ingest correctly while the
      failure is reported by NCT ID and error type.
* [x] Produces a clear ingestion/validation report — `IngestionReport`
      dataclass with `to_markdown()`, mirroring the existing
      `AuditReport`/`ValidationReport` pattern from `singularity.audit`
      / `singularity.ingest`.
* [x] Mock HTTP/database fixtures for deterministic tests —
      `tests/test_pipeline.py` (7 tests): end-to-end ingestion,
      idempotent re-run (unchanged and changed data), partial failure,
      provenance survival, observed/derived separation. All use a
      mocked HTTP transport against a **real** local PostgreSQL 16
      instance (same skip-if-unreachable pattern as
      `tests/test_db_schema.py`).
* [x] Reproducible script for real end-to-end (real network + real DB)
      validation — `scripts/run_clinicaltrials_ingestion.py`. Verified
      this session that it correctly fails loudly (real `HTTPError`)
      when run from this sandbox, rather than succeeding with fake
      data.
* [x] Full test suite: 71/71 passing (64 pre-existing + 7 new).

**Explicitly NOT claimed**: real end-to-end ingestion (real network +
real ClinicalTrials.gov data) has NOT been performed or verified this
session — this sandbox still cannot reach `clinicaltrials.gov`. A
human must run `scripts/run_clinicaltrials_ingestion.py` to get that.

### Phase 2A-3 — Real-Data Validation and Approved Fixes (2026-08-14, sessions 11-12)

First genuinely real end-to-end validation: a human ran
`scripts/run_clinicaltrials_ingestion.py` from Colab (real network) →
10 real trials / 109 real outcome records / 109 classifications, 0
failures, 0 malformed records, written to a real PostgreSQL database.

* [x] Analyzed all 13 classified rows + representative samples across
      8 unclassified title families (96 rows) against real provenance
      — session 11, no code changed. Found: 1 real classifier bug
      (ceiling-guard phrase gap), 1 cosmetic bug (AE plural pattern), 1
      extraction/schema gap (ORR count vs. rate, no denominator
      captured), 1 positive-confirmation finding (NA/censored value
      handling working correctly), 0 false negatives.
* [x] Implemented 3 of 4 proposed fixes, human-approved — session 12:
      ceiling-guard extended ("maximum of"), AE pattern fixed
      (plural + TEAE), new `_NON_EFFICACY_PATTERNS` for PK/safety (9
      patterns, all grounded in real titles). 9 new regression tests.
      Full suite: 80/80.
* [x] Re-validated against the exact real 109-row dataset with a
      complete field-level diff: 0 unexpected endpoint changes, the 3
      predicted `NCT02360579` PFS rows corrected exactly as intended,
      96 reason-text improvements fully accounted for (no row outside
      the grounded AE/PK/safety/PFS-ceiling categories touched).
* [ ] Fix #3 (denominator capture) explicitly deferred per instruction
      — documented as a known limitation in `docs/data_dictionary.md`,
      not implemented. Tracked as a future Phase 2/data-model item.
* [ ] **Classifier still explicitly NOT validated or production-ready.**
      Real-data validation is incremental, not a one-time gate — every
      future change should be re-validated against real data the same
      way.

### Phase 2B-2 — Real-Data API Verification (2026-08-14, session 14)

* [x] Verified all 3 real endpoints against the exact real 109-row/
      10-trial/3-with-results dataset from the Colab ingestion, loaded
      into a real local PostgreSQL replica (no network path to the
      live Colab instance exists from this sandbox — see
      `docs/autonomous_state.md` "Session 14 Summary" for the explicit
      methodology and its honest boundary).
* [x] All 6 verification criteria confirmed against real data: trial
      metadata, outcome records, endpoint/subtype/confidence, `value_type`
      (including the exact real count-vs-rate risk case), no silent
      drops, provenance correctly excluded per contract.
* [x] CORS added (`GET`-only, no credentials, configurable origins) —
      unblocks a future browser frontend; frontend itself not started.
* [x] 4 new integration tests closing real-data-shape gaps (PK/rate/
      DOR via live API, low-confidence case, large unclassified batch).
      Full suite: 104/104.
* [x] No classifier/schema/ingestion changes — real verification found
      zero failures requiring one.
* [ ] Honest gap: zero low-confidence classified rows exist in this
      specific real dataset (a positive side-effect of session 12's
      fix) — the low-confidence test case uses a real phrasing pattern
      from session 6 on a synthetic NCT ID, not a literal row from this
      109-row export.

### Phase 2B — API Vertical Slice (2026-08-14, session 13)

Approved architecture: FastAPI + raw SQL/psycopg2, no ORM. Read-only.

* [x] Read layer: `singularity.db.get_trial`, `list_trials`,
      `get_outcomes_for_trial` (joined with latest classification via
      the existing `latest_endpoint_classifications` view).
* [x] `value_type` computed field (`singularity.value_types`) —
      "count"/"rate"/"time"/"other", derived from `parameter`/`unit`
      at read time. Closes the session-11 count-vs-rate risk without a
      schema change, per approved decision. 11 tests, every rule
      grounded in a real `(parameter, unit)` pair.
* [x] Pydantic response models (`singularity.api.models`) defined and
      tested before any HTTP routing existed.
* [x] Vertical slice: `GET /trials/{nct_id}`, `GET /trials` (with
      condition/phase/status filters), `GET /trials/{nct_id}/outcomes`
      (endpoint/subtype/confident/reason/value/unit/parameter/
      value_type included; `provenance_raw` excluded by default).
* [x] Integration tests against a real local PostgreSQL instance (9
      tests, seeded via the existing tested `db.py` write functions)
      plus an OpenAPI schema smoke test. Full suite: 100/100.
* [ ] Task 7 (close the remaining `Trial` field-verification gap using
      existing Colab data): **not closed** — the session-11 Colab
      export didn't include `official_title`/`interventions`/
      `start_date`/`completion_date`/`enrollment_count` columns.
      Explicitly did not block Phase 2B, per instruction. Would need a
      fresh export with those columns to close.
* [ ] Explicitly NOT started, per instruction: ML, additional data
      sources, taxonomy expansion, authentication, background jobs,
      GraphQL, ingestion automation, frontend/UI.

### Phase 2 — remaining (not started)

* [ ] Build trial search
* [ ] Build trial filtering
* [ ] Filter by disease
* [ ] Filter by intervention
* [ ] Filter by phase
* [ ] Filter by endpoint
* [ ] Filter by trial status
* [ ] Build trial detail page
* [ ] Build endpoint detail page
* [ ] Build treatment comparison
* [ ] Build trial-level analytics
* [ ] Build endpoint distributions
* [ ] Build outcome visualization
* [ ] Add source/provenance display

## Phase 3 — Biomedical Intelligence

* [ ] Build drug representation
* [ ] Connect drugs to trials
* [ ] Connect drugs to endpoints
* [ ] Connect drugs to diseases
* [ ] Build drug detail pages
* [ ] Build treatment/program timelines
* [ ] Build therapeutic-area intelligence
* [ ] Build company representation
* [ ] Connect companies to drugs
* [ ] Connect companies to trials
* [ ] Connect companies to therapeutic programs
* [ ] Build company intelligence pages
* [ ] Add AI/biology company intelligence

## Phase 4 — Modeling

* [ ] Define prediction tasks
* [ ] Define model inputs
* [ ] Establish train/validation/test methodology
* [ ] Build feature pipeline
* [ ] Build baseline models
* [ ] Evaluate baseline models
* [ ] Build improved models where justified
* [ ] Evaluate model calibration
* [ ] Analyze failure cases
* [ ] Add explainability
* [ ] Document model limitations
* [ ] Create model card
* [ ] Prevent data leakage

## Phase 5 — Singularity Terminal

* [ ] Establish information architecture
* [ ] Build global search
* [ ] Build navigation
* [ ] Build trial explorer
* [ ] Build drug explorer
* [ ] Build company explorer
* [ ] Build endpoint analytics
* [ ] Build comparison interfaces
* [ ] Build quantitative charts
* [ ] Add source references
* [ ] Add loading/error states
* [ ] Improve performance
* [ ] Improve accessibility
* [ ] Establish visual design system

## Phase 6 — AI Layer

* [ ] Define AI-assisted workflows
* [ ] Build evidence retrieval
* [ ] Build structured research summaries
* [ ] Add model-assisted analysis
* [ ] Add uncertainty reporting
* [ ] Prevent unsupported claims
* [ ] Add provenance to AI-generated analysis

## Phase 7 — Production Readiness

* [ ] Full test suite
* [ ] Data validation pipeline
* [ ] Error handling
* [ ] Security review
* [ ] Performance review
* [ ] Documentation review
* [ ] Model card review
* [ ] Data dictionary review
* [ ] Deployment preparation
* [ ] Final product QA

---

# Explicitly Out of Scope for Current Phase

The following must NOT be implemented unless explicitly authorized:

* Prediction markets
* Kalshi-style trading
* Real-money markets
* Betting mechanisms
* Financial-market infrastructure

These ideas may be documented in `docs/future_ideas.md` but should not affect current development.
