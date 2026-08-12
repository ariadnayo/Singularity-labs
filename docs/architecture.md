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
