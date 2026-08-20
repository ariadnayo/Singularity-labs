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

## Known limitation: `value` is not always a rate (added session 11/12, 2026-08-14)

`outcomeMeasures[].denoms` (the group-size denominator, e.g. "66
participants") is present in the raw ClinicalTrials.gov response but
is **not currently captured** by `OutcomeRecord` or the `outcome_records`
table. Confirmed via real-data validation: a real ORR-classified row
(`NCT02360579`) had `parameter=COUNT_OF_PARTICIPANTS` and `value=23` —
this is a raw **responder count**, not a percentage, and the group's
actual size (66) is only in the discarded `denoms` field.

**Consequence: a downstream consumer must not assume `outcome_records.value`
is always already a rate/percentage for ORR (or any) classified rows.**
Rows with `unit` like `"percentage of participants"` genuinely are
rates; rows with `parameter=COUNT_OF_PARTICIPANTS` (or similar
count-typed parameters) are raw counts and require the denominator to
become a rate.

This is explicitly **not fixed** — capturing `denoms` would require a
schema change (new field(s) on `OutcomeRecord` and the `outcome_records`
table) and is deferred as a Phase 2/data-model enhancement, not
resolved in session 11 or 12. Classification (e.g. `endpoint=ORR`) is
unaffected and correct regardless of this gap — the gap is about the
raw *value*, not the *endpoint* it's classified as.

---

# Trial Entity (added Phase 2A, session 9)

`singularity.schema.Trial` — protocol-level trial metadata, distinct
from `OutcomeRecord`. Linked to its outcome records by `nct_id`.

| Field | Meaning | Verified live? |
|---|---|---|
| `nct_id` | ClinicalTrials.gov study identifier | **Yes** |
| `brief_title` | Short trial title | No -- documented schema, not re-verified this session |
| `official_title` | Full formal trial title | No |
| `overall_status` | e.g. RECRUITING, COMPLETED, TERMINATED | No |
| `phases` | e.g. `["PHASE2", "PHASE3"]` | No |
| `study_type` | e.g. INTERVENTIONAL, OBSERVATIONAL | No |
| `conditions` | List of studied conditions | No |
| `lead_sponsor` | Sponsoring organization name | No |
| `interventions` | List of intervention names | No |
| `start_date` | As reported by the source; NOT parsed/normalized (may be partial, e.g. `"2025-01"`) | No |
| `completion_date` | Same caveat as `start_date` | No |
| `enrollment_count` | Reported enrollment target/actual | No |

**"Verified live" means**: independently confirmed against a real
ClinicalTrials.gov API v2 response fetched during this project (as
opposed to relying on general/training knowledge of the public schema).
Only `nct_id` (via `identificationModule`) meets that bar as of
2026-08-14. All other fields should be spot-checked against a real
response before being trusted at scale -- see
`docs/autonomous_state.md` "Session 9 Summary" for exactly why (the
web-fetch tooling needed to re-verify was unavailable in that session).

See `db/README.md` for how `Trial` maps onto the `trials` PostgreSQL
table, and why dates are stored as `TEXT` rather than `DATE`.
