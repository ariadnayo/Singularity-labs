# Singularity Labs — Data Dictionary

## Purpose

This document defines the meaning of the structured clinical-outcome dataset.

The documentation must describe the actual data rather than assumptions about the data.

---

# Core Outcome Fields

## nct_id

ClinicalTrials.gov study identifier.

Example:

`NCT01101334`

---

## title

The title or description of the clinical outcome measure.

This field may contain important information about the endpoint definition, assessment method, population, and timeframe.

Do not classify an outcome based solely on keyword matching when the full title provides contradictory information.

---

## parameter

The type of reported statistic or measurement.

Examples include:

* MEDIAN
* MEAN
* NUMBER
* COUNT_OF_PARTICIPANTS
* COUNT_OF_UNITS

The parameter describes how the value should be interpreted.

It does not by itself determine the clinical endpoint.

---

## unit

The unit or semantic representation of the reported value.

Examples include:

* months
* percentage of participants
* Participants
* Probability
* Number
* Score on a scale

Do not assume that `NUMBER` means a raw participant count. The title and unit must be considered together.

---

## timeframe

The period over which the outcome was assessed.

Examples include:

* 6 months
* 12 months
* baseline to disease progression
* baseline to death
* study completion

Fixed-time survival outcomes must not automatically be interpreted as median survival.

---

## group

The treatment arm, cohort, population, or analysis group associated with the outcome.

---

## value

The reported numerical value.

The value must be interpreted in conjunction with:

* endpoint
* parameter
* unit
* timeframe
* title
* group

Never interpret the value independently.

---

# Canonical Endpoint Categories

The canonical endpoint field is:

`outcomes_df["endpoint"]`

Current canonical categories:

* PFS
* OS
* ORR
* DOR
* DFS

---

# PFS

Progression-Free Survival.

Generally describes time from a defined starting point until disease progression or death, depending on the study definition.

Examples may include:

* median PFS
* progression-free survival time
* progression-free survival rate
* PFS at a fixed timepoint

Fixed-time PFS outcomes such as PFS6 and PFS12 may require subtype handling and should not automatically be treated as equivalent to median PFS.

---

# OS

Overall Survival.

Generally describes time from a defined starting point until death from any cause.

Examples may include:

* median OS
* overall survival rate
* OS at 6 months
* OS at 12 months
* OS at 24 months

A fixed-time OS rate is not the same statistical quantity as median OS.

---

# ORR

Overall Response Rate / Objective Response Rate depending on the source terminology.

Usually represents the proportion or percentage of participants achieving a defined tumor response.

The exact response definition must be interpreted from the source.

Do not classify Duration of Response as ORR merely because the title contains the word "response."

---

# DOR

Duration of Response.

Generally describes the duration from documented response until disease progression or death, according to the study definition.

Examples include:

* median DOR
* duration of objective response

DOR is distinct from ORR.

---

# DFS

Disease-Free Survival.

Generally describes the time from a defined starting point until disease recurrence or death, depending on the study definition.

Fixed-time DFS rates and median DFS are different statistical quantities.

---

# Related Measures That Require Careful Handling

The following should not automatically be mapped to canonical endpoints without contextual review:

* PFS6
* PFS12
* OS6
* OS12
* survival rate
* disease control rate
* clinical benefit rate
* time to progression
* time to local progression
* quality-of-life outcomes
* adverse-event outcomes
* tumor response subcategories
* event-free survival (EFS) -- related to DFS but not equivalent; the
  "event" definition is protocol-specific and typically broader than
  DFS's disease-recurrence-specific framing. Explicitly excluded from
  the classifier since 2026-08-14 (session 8) -- see
  `docs/endpoint_taxonomy_analysis.md`.
* pathological complete response (pCR, incl. tpCR/bpCR) -- related to
  ORR but not equivalent; assessed via post-surgical pathology, not
  RECIST imaging-based tumor-shrinkage criteria. Explicitly excluded
  from the classifier since 2026-08-14 (session 8).
* best overall response (BOR) -- related to ORR but not equivalent; a
  categorical per-subject classification (CR/PR/SD/PD/NE), not itself
  a numeric response rate. Explicitly excluded from the classifier
  since 2026-08-14 (session 8).

---

# Data Integrity Rule

When uncertain, preserve the original source information and flag the record.

Do not manufacture certainty.

---

# Provenance

Every `OutcomeRecord` ingested from a real external source (as opposed
to a test/mock fixture) should carry a `Provenance` record
(`src/singularity/schema.py`) with:

* `source` — the name of the external source, e.g. `"clinicaltrials.gov"`.
* `source_record_id` — the source's own identifier for the underlying
  record (e.g. an NCT ID).
* `retrieved_at` — ISO 8601 UTC timestamp of the actual retrieval.
* `request_url` — the exact URL requested.
* `query_params` — the exact query parameters used, so the request can
  be reproduced.
* `raw` — the raw source record, or the relevant slice of it, so the
  mapping into `OutcomeRecord` fields can be audited or re-derived.

This is intentionally generic and carries nothing specific to any one
source, so it applies unchanged to future sources (PubMed/NCBI,
OpenAlex, FDA, PubChem, ChEMBL, UniProt, Open Targets).

---

# ClinicalTrials.gov API v2 → OutcomeRecord Mapping

Implemented in `src/singularity/sources/clinicaltrials.py`. Verified
live 2026-08-13: public API, no authentication required, JSON
responses, base URL `https://clinicaltrials.gov/api/v2/studies`.

Only studies with `hasResults: true` contribute records — most
registered trials have not posted results, and that is expected, not
an error. For each entry in
`resultsSection.outcomeMeasuresModule.outcomeMeasures[]`, one
`OutcomeRecord` is produced per (measurement × group):

| OutcomeRecord field | ClinicalTrials.gov v2 field |
|---|---|
| `nct_id` | `protocolSection.identificationModule.nctId` |
| `title` | `outcomeMeasures[].title` |
| `parameter` | `outcomeMeasures[].paramType` |
| `unit` | `outcomeMeasures[].unitOfMeasure` |
| `timeframe` | `outcomeMeasures[].timeFrame` |
| `group` | `outcomeMeasures[].groups[].title`, matched via `classes[].categories[].measurements[].groupId` |
| `value` | `classes[].categories[].measurements[].value` (parsed as float; non-numeric values such as `"NA"` become `None`, never guessed) |

Note: this maps *reported results* (`resultsSection`), not the
*planned* outcome measures in `protocolSection.outcomesModule`
(`primaryOutcomes`/`secondaryOutcomes`), which have no reported values
and are out of scope for `OutcomeRecord` until a study posts results.
