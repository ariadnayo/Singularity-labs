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
* [ ] **The classifier is explicitly NOT validated or production-ready.**
      119 rows from session 6's analysis (Category B/D/F: EFS, pCR,
      BOR, TTR, CRi, OR-by-modality fragmentation, and a 67-row
      miscellaneous long tail) remain unresolved and require a human
      scoping decision before any further classifier changes.
* [ ] Only after that scoping decision (and any resulting fixes are
      implemented, tested, and re-validated the same way): proceed to
      large-scale ingestion, additional sources (PubMed/NCBI, OpenAlex,
      FDA, PubChem, ChEMBL, UniProt, Open Targets), ML modeling, or UI
      work — explicitly not started yet, per instruction.

## Phase 2 — Clinical Trial Intelligence

* [ ] Build structured trial representation
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
