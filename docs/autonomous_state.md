# Singularity Labs — Autonomous State

## Last Updated

2026-08-13

## Current Phase

Phase 1 — Data Foundation

## Current Objective

Establish a reliable and scientifically correct clinical-outcome data foundation.

## Completed

* Initial autonomous development instructions created.
* Initial development roadmap created.
* `src/singularity/schema.py`: `OutcomeRecord` and `ClassificationResult`
  dataclasses matching `docs/data_dictionary.md`.
* `src/singularity/endpoints.py`: rule-based endpoint classifier.
  Distinguishes median/time-to-event PFS, OS, DFS from their
  fixed-timepoint/rate subtypes (PFS6, OS12, etc.) rather than
  collapsing them. Explicitly excludes DOR from ORR matching. Leaves
  DCR, CBR, TTP, QoL, and AE measures unclassified rather than guessing.
* `tests/test_endpoints.py`: 13 tests against clearly-labeled mock
  fixtures (not real trial data), covering the edge cases above plus
  empty-title validation and batch-summary consistency.
* `src/singularity/ingest.py`: CSV ingestion + `ValidationReport`
  (missing required fields, malformed values, duplicates, unknown/
  missing columns, empty dataset). Never silently drops or transforms
  rows -- every exclusion is counted and explained.
* `src/singularity/audit.py`: `run_audit(csv_path)` end-to-end pipeline
  (ingest → classify → summarize → markdown report). Raises
  `FileNotFoundError` if the path doesn't exist -- there is no
  built-in fallback dataset anywhere in this codebase.
* `tests/test_ingest_and_audit.py`: 9 tests against mock CSV fixtures,
  covering every ingestion failure mode above plus an end-to-end mock
  audit run.
* `data/README.md`: documents the expected schema and exactly what is
  needed to run the pipeline on real data (a real CSV file, or a
  documented API source with credentials -- neither currently exists
  in or is reachable from this repo).
* Full test suite: 22/22 passing (`pytest tests/`).

## Data Source Status (searched this session)

Searched: entire repo tree, `Claude.md`, all files in `docs/`, and the
uploads/session environment. Result: **no real dataset file, API
endpoint, or credentials for one are present or documented anywhere.**
`docs/architecture.md` names "Data Sources" only as a generic box in
the pipeline diagram, with no specifics. The 5,165-row dataset
referenced elsewhere in this file has never been located.

## Current Known Data — UNVERIFIED, DO NOT TREAT AS CURRENT

The counts below were recorded in an earlier version of this document.
No dataset producing these numbers has ever been found in this
repository, and no ingestion or classification run against real data
has been performed in any session to date (see "Data Source Status"
below). They are preserved here only as historical context, not as a
current or reproducible result:

* PFS: 303
* ORR: 188
* OS: 180
* DOR: 90
* DFS: 40
* Unclassified: 4,364
* Total rows: 5,165
* Referenced canonical endpoint column: `outcomes_df["endpoint"]`

Do not cite these numbers as current state. If asked for current
classification counts, the honest answer is: no real dataset is
present, so there are none yet.

## Known Issues

The majority of rows are currently unclassified.

Some apparently PFS-related outcomes are not necessarily canonical PFS measurements.

Examples include:

* PFS6
* PFS12
* progression-free survival rates
* probability of PFS
* disease control rate
* quality-of-life measurements
* adverse-event measurements

Some OS rows represent survival rates at fixed timepoints rather than median overall survival.

Some ORR-related rows represent duration of objective response and therefore may belong to DOR rather than ORR.

These distinctions must be preserved rather than guessed.

## Current Priority

The ingestion and classification pipeline is now fully implemented and
tested against mock data, but it has **not been run against real
clinical-trial data**, because none is present or reachable. This is a
hard blocker on the roadmap item "integrate classification pipeline
with real data" -- the code side of that task is done; the data side
is not, and cannot be completed autonomously without a real data
source being supplied.

## Tests

`pytest tests/` — 22/22 passing:
* `tests/test_endpoints.py` (13) — classification rules, mock fixtures.
* `tests/test_ingest_and_audit.py` (9) — ingestion validation failure
  modes and end-to-end audit, mock fixtures.

No test in this suite uses or claims real clinical-trial data.

## Blockers

* **No real dataset is present in `data/` or anywhere in this repo.**
  Confirmed by an explicit search of the full repo tree and the
  session environment this session.
* The 5,165-row / 801-classified counts recorded elsewhere in this
  file are unverified legacy notes from before this codebase existed
  in its current form. They cannot be reproduced and must not be
  cited as current results.
* Running the pipeline for real requires a human to supply one of:
  1. A real CSV file at `data/outcomes.csv` (or similar), with its
     provenance documented (source, export date, query).
  2. Or a documented API/source plus credentials, if the data is meant
     to come from a live system rather than a static export.

## Next Recommended Task

Once a real data source is supplied per the two options above:
1. Run `singularity.audit.run_audit(path)` against it.
2. Manually spot-check a sample of the classification output against
   the source titles for correctness (per `Claude.md` section 9 --
   an audit report alone is not sufficient validation).
3. Record the real, reproducible counts here, replacing the "UNVERIFIED"
   section above.
4. Only then proceed to the next roadmap phase (Clinical Trial
   Intelligence).

Until real data is supplied, autonomous progress on this specific task
is blocked; further roadmap phases that assume classified real data as
input should not be started, since they would have nothing real to
build on.

## Human Decisions Required

* Where does the real outcomes dataset referenced in earlier sessions
  actually come from, and can it be provided (as a file or an
  accessible API)? This is required to continue Phase 1 with real
  data rather than mock fixtures.
