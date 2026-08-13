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
* [ ] Run the adapter against the live API and ingest a real batch of
      studies — **blocked in the current sandboxed environment**,
      which cannot reach `clinicaltrials.gov` over the network (see
      `docs/autonomous_state.md`). Not blocked by any missing data
      source, license, or credential.
* [ ] Manually spot-check a real ingested sample against source study
      pages for mapping correctness, once real ingestion has run.
* [ ] Run `singularity.audit.run_audit`-equivalent against real
      ClinicalTrials.gov data and record actual, reproducible
      classification counts (replacing the "UNVERIFIED" legacy numbers
      in `docs/autonomous_state.md`).
* [ ] Only after the above: proceed to additional sources
      (PubMed/NCBI, OpenAlex, FDA, PubChem, ChEMBL, UniProt, Open
      Targets), per `docs/architecture.md`.

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
