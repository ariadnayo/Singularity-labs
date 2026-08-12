# Singularity Labs — Development Roadmap

## Current Objective

Build a scientifically rigorous clinical and biomedical intelligence platform.

The current priority is to establish a reliable clinical-outcome data foundation before expanding into advanced modeling and intelligence features.

---

# Phase 1 — Data Foundation

* [ ] Audit the current data pipeline
* [ ] Document the complete outcome schema
* [ ] Validate `outcomes_df["endpoint"]`
* [ ] Build endpoint classification validation
* [ ] Investigate unclassified outcomes
* [ ] Investigate suspicious PFS classifications
* [ ] Investigate suspicious OS classifications
* [ ] Investigate suspicious ORR classifications
* [ ] Investigate suspicious DOR classifications
* [ ] Investigate suspicious DFS classifications
* [ ] Normalize endpoint terminology
* [ ] Normalize units
* [ ] Handle missing values consistently
* [ ] Detect duplicate outcome records
* [ ] Preserve source provenance
* [ ] Build automated data-quality reporting
* [ ] Create a manually verified endpoint test set

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
