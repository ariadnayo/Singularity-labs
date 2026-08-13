# Singularity Labs — Autonomous State

## Last Updated

2026-08-13 (session 3)

## Current Phase

Phase 1 / Phase 1a — Data Foundation / ClinicalTrials.gov Integration

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
* `src/singularity/sources/base.py`: generic `DataSourceAdapter`
  interface, so future sources plug in without changing the schema.
* `src/singularity/sources/clinicaltrials.py`: ClinicalTrials.gov API
  v2 adapter -- pagination, rate-limit-respecting delay between pages,
  provenance capture, and mapping from
  `resultsSection.outcomeMeasuresModule` onto `OutcomeRecord`
  (one record per measurement × group). Uses only the standard library
  (`urllib`), no auth, since none is required (verified live).
* `src/singularity/schema.py`: added `Provenance` (source, source
  record id, retrieval timestamp, request URL, query params, raw
  record) and an optional `provenance` field on `OutcomeRecord`.
  Deliberately source-agnostic.
* `tests/test_clinicaltrials_adapter.py`: 9 tests against hand-written
  mock JSON shaped like real ClinicalTrials.gov v2 responses (NCT IDs
  in the 99999900s range, invented drug/sponsor names, to keep mock
  and real data unambiguous). No real network call in any test.
* `docs/architecture.md`: added a "Data Sources" section naming
  ClinicalTrials.gov as the initial authoritative source, documenting
  the no-auth finding, and describing the adapter pattern for future
  sources.
* `docs/data_dictionary.md`: added the `Provenance` field spec and the
  full ClinicalTrials.gov API v2 → `OutcomeRecord` field mapping table.
* Full test suite: 31/31 passing (`pytest tests/`).

## ClinicalTrials.gov API — What Was Actually Verified This Session

Verified live, via a direct HTTPS request made through a tool with
broader network access than the code-execution sandbox (not through
the sandbox's own `bash`/Python, which cannot reach
`clinicaltrials.gov` -- see "Environment Constraint" below):

* The endpoint `https://clinicaltrials.gov/api/v2/studies` is real,
  public, and returns JSON right now.
* **No authentication or API key is required.** This was determined by
  actually making an unauthenticated request and receiving a normal
  200 response with real study data, not by assuming it from
  documentation alone (docs were also checked and agree: public,
  U.S.-government-work, no-auth, ~50 requests/minute rate limit).
* The response shape matches what's implemented in
  `src/singularity/sources/clinicaltrials.py` and documented in
  `docs/data_dictionary.md` (`protocolSection.identificationModule.nctId`,
  `hasResults`, etc.). The specific batch fetched during verification
  happened to all have `hasResults: false`, so the exact
  `resultsSection.outcomeMeasuresModule` shape for a study with posted
  results was confirmed from official/third-party API field
  documentation (cited in code comments and `docs/data_dictionary.md`),
  not from a live example with real posted results.

## Environment Constraint (real, not hypothetical)

The sandboxed code-execution environment used for this autonomous
session has a restricted network egress allowlist that does **not**
include `clinicaltrials.gov` (confirmed by the allowlist itself, not
by a failed guess). This means:

* `src/singularity/sources/clinicaltrials.py`'s real HTTP path
  (`_default_http_get`, built on stdlib `urllib`) has not been and
  currently cannot be executed against the live API from within this
  sandbox.
* All 9 tests in `tests/test_clinicaltrials_adapter.py` inject a mock
  `http_get` and never touch the network.
* Actually running ClinicalTrials.gov ingestion end-to-end requires
  either (a) running this code in an environment with network access
  to `clinicaltrials.gov` (e.g. a human's machine, CI, or a
  differently configured agent environment), or (b) this sandbox's
  network policy being changed to allow that host.

This is a environment/infrastructure limitation, not a missing-data
problem -- the data source itself is real, public, and already
integrated in code.

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

ClinicalTrials.gov is now the designated initial authoritative data
source, and a fully tested (against mocks) ingestion adapter exists.
The remaining gap is purely environmental: actually running that
adapter against the live API requires network access this sandbox
doesn't have. This is no longer blocked on "no data source exists" --
it's blocked on "this specific execution environment can't reach the
host." That distinction matters and should not be collapsed back into
"waiting for a human to supply a CSV."

## Tests

`pytest tests/` — 31/31 passing:
* `tests/test_endpoints.py` (13) — classification rules, mock fixtures.
* `tests/test_ingest_and_audit.py` (9) — CSV ingestion validation
  failure modes and end-to-end audit, mock fixtures.
* `tests/test_clinicaltrials_adapter.py` (9) — ClinicalTrials.gov
  adapter (URL building, pagination, provenance capture, outcome
  extraction, malformed-value handling), mock HTTP transport.

No test in this suite uses or claims real clinical-trial data.

## Blockers

* **This sandbox's network egress does not include `clinicaltrials.gov`.**
  The adapter code is complete and correct against the verified live
  API shape, but cannot be executed end-to-end here. Running it for
  real requires either network access to be granted to this host, or
  running the code in an environment that already has it (a
  developer's machine, CI, etc.).
* The 5,165-row / 801-classified counts recorded elsewhere in this
  file remain unverified legacy notes and must not be cited as current.

## Next Recommended Task

1. Run `ClinicalTrialsAdapter().fetch_outcome_records(...)` for real,
   in an environment with network access to `clinicaltrials.gov` (e.g.
   `query_cond="<some condition>", filter_overall_status=["COMPLETED"], max_pages=1`
   as a small first real run).
2. Manually spot-check a handful of the resulting `OutcomeRecord`s
   against the actual ClinicalTrials.gov study pages for the same NCT
   IDs, to confirm the field mapping holds on real data (not just mock
   data) -- per `Claude.md` section 9, an audit report alone is not
   sufficient validation.
3. Run `singularity.endpoints.classify_batch` + `summarize` on the real
   records and record the actual, reproducible counts here, replacing
   the "UNVERIFIED" section above.
4. Only then proceed to the next roadmap phase (Clinical Trial
   Intelligence) or to additional sources (PubMed/NCBI, OpenAlex, FDA,
   PubChem, ChEMBL, UniProt, Open Targets).

## Human Decisions Required

* Can this sandbox's network egress allowlist be updated to include
  `clinicaltrials.gov`, so the adapter can be run end-to-end
  autonomously in future sessions? If not, real ingestion runs will
  need to happen outside this specific environment.
