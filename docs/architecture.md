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
