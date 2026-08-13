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
  empty-title validation and batch-summary consistency. All passing.
* `data/README.md`: documents the expected schema; explicitly does not
  include or fabricate a dataset, since none exists in this repo yet.

## Current Known Data

Current endpoint counts:

* PFS: 303
* ORR: 188
* OS: 180
* DOR: 90
* DFS: 40
* Unclassified: 4,364

Total rows:

* 5,165

Canonical endpoint column:

`outcomes_df["endpoint"]`

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

No real dataset exists in this repository yet (`data/` is empty besides
a README). The classifier logic and its test suite are ready, but they
have not been run against real trial data because none has been
provided. Next real work requires that data to be added.

## Tests

`pytest tests/` — 13/13 passing (all against mock fixtures, not real
clinical data).

## Blockers

* No real dataset is present in `data/`. The counts referenced above
  this section (5,165 rows, 801 classified, etc.) come from a prior
  session's context and could not be independently verified against
  data in this repo. They should not be treated as currently
  reproducible until a real dataset file is added and run through
  `singularity.endpoints.classify_batch` + `summarize`.

## Next Recommended Task

Add the real outcomes dataset to `data/` (format documented in
`data/README.md`), then run `classify_batch` + `summarize` against it
to produce an actual, reproducible classification audit report
(replacing the unverified counts above), per `Claude.md` section 9.

## Human Decisions Required

None currently.
