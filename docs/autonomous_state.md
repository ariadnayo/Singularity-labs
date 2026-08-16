# Singularity Labs — Autonomous State

## Last Updated

2026-08-14 (session 6)

## Current Phase

Phase 1 / Phase 1a — Data Foundation / ClinicalTrials.gov Integration — Real-Data Validation

## Session 4 Summary: Real-Data Validation Run (2026-08-13)

**This session ran the real-data validation the roadmap required before
any further ingestion work, and it found and fixed a real bug.**
Everything below is grounded in an actual live fetch; nothing here is
fabricated or extrapolated from the earlier "unverified" 5,165-row notes.

### What was actually fetched

A live, unauthenticated request to
`https://clinicaltrials.gov/api/v2/studies?filter.overallStatus=RECRUITING&format=json&pageSize=10&query.cond=lung+cancer`
returned 7 real, currently-live oncology-related trials (full NCT IDs,
sponsors, and titles in `data/clinicaltrials_raw/2026-08-13_lung_cancer_recruiting_provenance.txt`).

**Real tooling constraint hit and disclosed, not worked around
silently:** attempts to fetch different query parameters (different
condition, `filter.overallStatus=COMPLETED`) against the same endpoint
were silently served the same cached response — confirmed by
byte-identical study content across three differently-parameterized
requests. A request to the single-study endpoint
(`/studies/{NCT_ID}`) was rejected outright as not previously seen.
**In practice, only one real query result was reachable this session**,
not an arbitrary controlled sample as originally intended.

All 7 studies in that sample have `hasResults: false` (none have
posted results yet — normal for active trials). This means **no
`resultsSection.outcomeMeasuresModule` data (measured values, arms/
groups) was reachable anywhere in this session** — the value/group
extraction path in `extract_outcome_records()` remains validated only
against mock data (see `tests/test_clinicaltrials_adapter.py`), not
real posted results.

### What was validated instead, and why this is still a legitimate real-data run

Rather than fabricate value-bearing records to hit the "spot-check 20+
records" target, this session used the one real, reachable thing
available: the **planned outcome measure titles**
(`protocolSection.outcomesModule.primaryOutcomes` /
`.secondaryOutcomes`) from those 7 real trials — actual PFS/OS/ORR/
DOR/DCR/CBR/AE/PK title text as written by real trial sponsors, with
no posted numeric values (none exist yet for these trials).

- Raw data saved: `data/clinicaltrials_raw/studies_outcomes_raw.json`
  (verbatim `outcomesModule` slices from the real response) +
  `..._provenance.txt` (exact request URL, retrieval context, the
  tooling constraint above, and per-study sponsor/title attribution).
- Normalized data saved separately:
  `data/clinicaltrials_normalized/planned_outcome_titles.csv` (33
  rows, one per real outcome title, each with `nct_id`, `source`,
  `retrieved_at`, `request_url` provenance) and
  `classification_results.csv` (the classifier's output on each row).
- Pipeline run: `singularity.endpoints.classify_batch` +
  `summarize()` against these 33 real titles (via
  `OutcomeRecord`/`Provenance`, not through the CSV/`ingest.py` path,
  since these rows have no `value`/`group` — that path is exercised by
  `tests/test_ingest_and_audit.py` on mock data, not by this run).

**Explicit scope limit:** this validates the classifier's title-
matching logic against real trial language. It does NOT validate
`extract_outcome_records()`'s value/group parsing (no real measured
values were reachable), and it does NOT include a real DFS example or
a real title with genuine fixed-timepoint phrasing (e.g. "PFS at 6
Months") — none appeared in this specific sample. Both remain
validated only against mock fixtures until a real study with posted
results (or a real DFS/fixed-timepoint title) is reachable.

### Manual spot-check: all 33 real rows checked (target was ≥20)

Every row in `classification_results.csv` was manually compared
against the raw source title. Results:

| # | NCT ID | Title (real) | Classified | Correct? |
|---|--------|---------------|------------|----------|
| 4 | NCT07227597 | Objective Response Rate (ORR) | ORR, confident | ✅ |
| 5 | NCT07227597 | Disease Control Rate (DCR) | unclassified | ✅ (DCR must not become ORR/PFS) |
| 6 | NCT07227597 | Duration of Response (DOR) | DOR, confident | ✅ (not ORR) |
| 7 | NCT07227597 | Progression-Free Survival (PFS) | **initially PFS58 (WRONG)** → fixed → PFS median, confident | ❌→✅ (see bug below) |
| 8 | NCT07227597 | Overall Survival (OS) | **initially OS58 (WRONG)** → fixed → OS median, confident | ❌→✅ (see bug below) |
| 10 | NCT06917079 | Objective response rate (ORR) per RECIST v1.1 and CNS RECIST | ORR, confident | ✅ |
| 11 | NCT06917079 | Clinical benefit rate (CBR) per RECIST v1.1 | unclassified | ✅ (CBR must not become ORR) |
| 12 | NCT06917079 | Duration of Response (DOR) per RECIST v1.1 | DOR, confident | ✅ |
| 13 | NCT06917079 | Progression-Free Survival (PFS) per RECIST v1.1 | PFS median, confident | ✅ |
| 14 | NCT06917079 | Overall Survival (OS) | OS median, confident | ✅ |
| 1,2,3,9,18,19,27 | various | AE / DLT / TEAE / SAE titles | unclassified | ✅ |
| 21,22 | NCT04787042 | PK, ADA | unclassified | ✅ |
| 15,16,17 | NCT05977803 | imaging/diagnostic-performance titles | unclassified | ✅ |
| 20 | NCT04787042 | "Initial assessment of efficacy in phase 2" (ORR description buried in `description`, not `title`) | unclassified | ✅ (title alone genuinely doesn't say ORR — correctly conservative) |
| 23,24,25 | NCT06005246 | ME/CFS phenotyping/risk factors/biomarkers | unclassified | ✅ (not an oncology endpoint at all) |
| 26,28,29 | NCT05632913 | feasibility / "Efficacy - Alpha DaRT seeds" | unclassified | ✅ (too generic to safely map to PFS/ORR) |
| 30,31,32,33 | NCT07159659 | LOS / chest drain / QoL / GI symptoms | unclassified | ✅ (surgical/nutrition trial, correctly all unclassified) |

**1 real bug found, fixed, and regression-tested** (rows 7–8 above).

### Bug found: follow-up-ceiling timeframe mistaken for fixed timepoint

`NCT07227597`'s "Progression-Free Survival (PFS)" and "Overall
Survival (OS)" outcomes — plain median endpoints, no fixed-timepoint
wording in the title — were misclassified as `PFS58`/`OS58` subtypes
with `confident=False`. Root cause: `timeframe="Up to approximately 58
months"` (the study's overall follow-up ceiling — boilerplate that
applies to nearly every outcome in the trial) was being matched by the
fixed-timepoint regex, which read "58 months" as if the endpoint were
specifically measured *at* 58 months, the same pattern real PFS6/PFS12
measures use. Comparing against `NCT06917079`'s identically-worded
titles (timeframe: "approximately 5 years", no month-boilerplate
match) is what isolated the cause.

**Fix** (`src/singularity/endpoints.py`,
`_fixed_timepoint_months`): fixed-timepoint detection now trusts the
title first; the `timeframe` field is only used as a fallback, and
only when it is *not* phrased as a ceiling ("up to ...",
"approximately ..."). **Regression tests added**
(`tests/test_endpoints.py`):
`test_followup_ceiling_timeframe_not_mistaken_for_fixed_timepoint`
(using the exact real title/timeframe pair that exposed the bug) and
`test_genuine_fixed_timepoint_in_title_still_detected` (confirming the
fix didn't remove real fixed-timepoint detection). Full suite: 33/33
passing after the fix.

This bug would very likely have affected real data broadly — "Up to
approximately N months/years" is standard ClinicalTrials.gov
boilerplate, not specific to this one trial — so finding it via a real
7-study sample rather than only mock fixtures was the point of doing
this validation before scaling up.

## Session 5 Summary: Real-Results Extraction — Blocked, Reproducible Script Delivered (2026-08-13)

**Goal this session:** validate `extract_outcome_records()`'s value/
group parsing against a real study with posted results
(`hasResults: true`), closing the last Phase 1 gate. **Outcome: this
specific validation could not be completed in this environment.**
Three independent access paths were tried and exhausted; none used
mock, synthetic, or planned-outcome data as a substitute for real
posted results, per instruction.

### Three access paths tried, in order, all confirmed blocked

1. **Direct API queries with different parameters.** Requests to
   `https://clinicaltrials.gov/api/v2/studies` with different
   `query.cond`/`filter.overallStatus` values were silently served the
   same cached response from an earlier, unrelated query (session 4's
   lung-cancer/RECRUITING query) — confirmed by byte-identical study
   content returned across three differently-parameterized requests.
2. **Direct single-study API endpoint**
   (`/api/v2/studies/{NCT_ID}`) — rejected outright by the available
   fetch tool as an unseen/unreachable URL, even for a real NCT ID
   (`NCT01078090`) sourced from a technical article specifically about
   real posted-results data.
3. **Human-readable study page** (`clinicaltrials.gov/study/{NCT_ID}`)
   — returned an empty JavaScript application shell with no data; the
   real content is fetched client-side after page load, which the
   available fetch tool cannot execute.

This is a tooling/environment constraint, not a data-availability
problem — ClinicalTrials.gov itself has hundreds of thousands of
studies with posted results; this session's specific fetch tooling
could not reach any of them.

### What was built instead: a reproducible script for an unrestricted environment

`scripts/validate_real_clinicaltrials_data.py` — run from any machine
with real network access to `clinicaltrials.gov` (a developer's
laptop, CI, etc.). It:

1. Fetches a small, controlled sample of real studies with
   `hasResults=true` (using the real `AREA[HasResults]true` advanced
   filter, newly added to the adapter this session — see below), via
   the actual `ClinicalTrialsAdapter`, not a re-implementation.
2. Saves raw JSON per study, verbatim, to
   `data/clinicaltrials_raw/real_results_run_<timestamp>/`.
3. Extracts real `OutcomeRecord`s (title, parameter, unit, timeframe,
   group, value) with full `Provenance`, via the same
   `extract_outcome_records()` already covered by mock tests.
4. Saves normalized records separately to
   `data/clinicaltrials_normalized/real_results_run_<timestamp>/records.csv`.
5. Runs the existing classifier and writes `audit_summary.json` +
   `audit_report.md`, explicitly listing every unclassified or
   low-confidence row as **requiring manual spot-check** — the script
   does not claim classification correctness on its own.
6. Fails loudly (a real `HTTPError`/`URLError`) if network access
   isn't available, rather than falling back to any mock or synthetic
   data. **Verified this session**: running it from this sandbox
   produces `urllib.error.HTTPError: HTTP Error 403: Forbidden` from
   the sandbox's own egress proxy — the correct, honest failure mode,
   not a silent success with fake data.

### Adapter change this session

`src/singularity/sources/clinicaltrials.py`: added `filter_advanced`
support to `build_request_url`, `fetch_studies_page`, `iter_all_studies`,
and `ClinicalTrialsAdapter.fetch_outcome_records`, so a real run can
pass `filter_advanced="AREA[HasResults]true"` — the correct, real
ClinicalTrials.gov mechanism for restricting to studies with posted
results (sourced from a technical article documenting real API usage,
cross-referenced against the official field reference). New mock test:
`test_build_request_url_supports_filter_advanced_for_has_results`.
Full suite: 34/34 passing.

### Explicit scope boundary (unchanged from session 4, still true)

The classifier's title-matching logic HAS real-data validation
(session 4: 33 real titles, 1 bug found/fixed). The value/group
extraction path (`extract_outcome_records()`'s measurement parsing)
STILL has only mock-data validation
(`tests/test_clinicaltrials_adapter.py`). This gate remains open until
someone runs `scripts/validate_real_clinicaltrials_data.py` from an
environment with real network access and manually spot-checks the
output, the same way session 4's title validation was done.

## Session 6 Summary: Two Approved Fixes Implemented and Re-Validated Against Real Data (2026-08-14)

**Scope: exactly the two Category A fixes approved in session 5's
analysis, nothing else.** No new endpoint categories (EFS, pCR, BOR,
TTR, CRi, OR-by-modality) were added, and no existing exclusion logic
(DCR/CBR/TTP/QoL/AE/PK/dose-finding/dermatology) was touched.

**Data-integrity note carried over from the analysis step:** the real
dataset actually has 3,552 OutcomeRecords / 3,497 flagged rows (not
the 1,135/926 figures mentioned earlier in that conversation) — this
was verified directly from the attached `records.csv`/`audit_report.md`
and all numbers below use the verified figures.

### Fix 1: ORR/CR+PR/RECIST synonyms

Added `_ORR_SYNONYM_PATTERNS` (`src/singularity/endpoints.py`) —
context-anchored patterns requiring CR and PR to appear together as an
explicit response-rate phrase, deliberately NOT matching a bare "CR"
or "PR". 7 new tests (4 positive using the exact real phrasings from
session 5's analysis, 3 negative near-misses: hematologic "CR or CRi",
isolated "Complete Response" alone, isolated "Partial Response" alone
— none of these trigger ORR).

### Fix 2: Year-based fixed-timepoint survival phrasing

Extended fixed-timepoint detection to years (`_FIXED_TIMEPOINT_YEAR_RE`)
and added a narrowly-anchored "participants surviving" OS synonym,
**deliberately gated on an actual detected timepoint number** — a bare
"Number of Participants Surviving" with no timepoint must not become a
confident median-OS classification (a raw survivor count is not a
median survival time). This gating was added after the first
implementation attempt produced exactly that wrong result in manual
testing before it ever reached the test suite. 4 new tests.

### Two additional bugs found and fixed during this session's own re-validation (not part of the original 2-fix request, but directly caused by/exposed while implementing them)

1. **Decimal-number mis-parse (years):** `"3.5 years"` was matched by
   a naive year regex as if it said `"5 years"` (the digit after the
   decimal point), found on real trial `NCT01488487` while re-running
   against the real dataset. Fixed with a `(?<![\d.])` negative
   lookbehind.
2. **Decimal-number mis-parse (months) — a PRE-EXISTING bug, not
   introduced this session:** the same flaw existed in the *original*
   month regex from session 4 (`"4.8 months"` → matched as `"8
   months"`, `"34.9 months"` → matched as `"9 months"`), found on real
   trial `NCT03602586` in this session's before/after diff. Applying
   the same lookbehind guard to the month regex (done "for
   consistency" while fixing the year version) fixed it as a side
   effect. **This means session 4's real-data validation had an
   undetected false-positive that this session's re-validation caught.**

2 new regression tests, one per case, using the exact real
title/timeframe text that exposed each.

**Full suite: 47/47 passing** (34 baseline + 13 new: 7 ORR + 4 OS-year
+ 2 decimal-number).

### Re-validation against the exact real dataset (verified `records.csv`, 3,552 rows / 20 studies)

| | Before | After |
|---|---:|---:|
| Confidently classified | 55 | 55 |
| Flagged (unclassified OR low-confidence) | 3,497 | 3,497 |
| ORR | 8 | 26 |
| OS | 17 | 26 |
| PFS | 39 | 39 |
| DOR | 1 | 1 |
| DFS | 0 | 0 |

**The flagged-row total did not move (3,497 → 3,497) — this is not a
failure, it's the honest result of two independent effects exactly
offsetting each other**, verified via a complete row-by-row diff (49
rows changed in total, every one individually accounted for below; the
other 3,503 rows are byte-identical before/after):

**Genuinely newly and correctly classified (gains, 20 rows total):**
- 18 rows: real ORR-synonym titles (4 unique titles, e.g. `"Complete
  and Partial Response Rate Using... RECIST... Criteria"`, 12 rows
  from one trial alone) → now confidently ORR. **This is the intended
  effect of Fix 1.**
- 2 rows: `NCT03602586`'s "Progression-free Survival (PFS)" and
  "Overall Survival (OS)" — previously wrongly low-confidence PFS8/OS9
  due to the pre-existing decimal-month bug — now correctly confident
  median PFS/OS. **Bonus correction, not part of the original 2-fix
  request.**

**Newly and correctly identified as fixed-timepoint (still
appropriately low-confidence, NOT a gain in the "confident" count but
a real improvement in identification, 9 rows):**
- `"Percentage of Participants Surviving at 1/2/3 Year(s)"` (3 rows
  each) → now `OS`, subtype `OS1yr`/`OS2yr`/`OS3yr`, `confident=False`.
  Previously fully unclassified (endpoint=None). **This is the
  intended effect of Fix 2** — correctly conservative, not
  over-confident.

**Newly and correctly flagged as low-confidence (were WRONGLY
confident before this session — real pre-existing errors this
session's re-validation caught and fixed, 20 rows):**
- `"2-year Progression-free Survival"` (2 rows, `NCT00390611`) — title
  literally says "2-year," meaning this is a fixed-timepoint PFS rate,
  not median PFS. Previously silently misclassified as confident
  median PFS because no year-based detection existed at all before
  this session. Now correctly `PFS2yr`, `confident=False`.
- `"Progression Free Survival"` with timeframe `"5, 10, 15 years"` (18
  rows, `NCT02947984`) — a landmark multi-timepoint PFS reporting
  schedule, not a single median value. Previously silently
  misclassified as confident median PFS for the same reason. Now
  flagged `PFS15yr`, `confident=False`. **Known imprecision, disclosed
  not hidden:** the subtype label `PFS15yr` only reflects the last of
  three listed timepoints (5, 10, and 15 years) — the regex finds the
  one number immediately adjacent to the word "years" and has no
  concept of a multi-timepoint list. This is not scientifically wrong
  (the record is correctly flagged as non-median and routed to manual
  review, which is the safe direction), but the subtype string itself
  should not be read as "this specifically measures the 15-year
  timepoint only." Left as-is rather than over-engineered for a
  1-title, 18-row edge case — noted as a residual limitation, not
  silently claimed as fully solved.

**No new false positives were found.** The complete diff (49 rows) is
fully accounted for above; nothing in the other 3,503 rows changed at
all, confirming no unintended side effects on unrelated titles.

### Explicit disclaimers, per instruction

**This classifier is NOT being claimed as "validated" or "production-
ready."** What changed this session: 2 approved narrow fixes were
implemented, tested (47/47 unit tests, all with real-title-derived
fixtures where applicable), and re-validated against the same real
20-study dataset with a full row-level diff. What remains open: all of
session 5's Category B/D/F findings (EFS, pCR, BOR, TTR, CRi,
OR-by-modality, and the 67-row miscellaneous long tail — 119 rows
total) are **unchanged and still require a scoping decision** before
any further code changes. The value/group extraction path
(`extract_outcome_records()`) still has no fresh real-data validation
beyond what this session's dataset already exercised implicitly (i.e.,
this session re-validated using already-extracted real records from
your Colab run, not a fresh live extraction).

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
* `tests/test_endpoints.py`: tests against clearly-labeled mock
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
  needed to run the pipeline on real data.
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
* `tests/test_clinicaltrials_adapter.py`: 10 tests against hand-written
  mock JSON shaped like real ClinicalTrials.gov v2 responses (NCT IDs
  in the 99999900s range, invented drug/sponsor names, to keep mock
  and real data unambiguous). No real network call in any test.
* `docs/architecture.md`: added a "Data Sources" section naming
  ClinicalTrials.gov as the initial authoritative source, documenting
  the no-auth finding, and describing the adapter pattern for future
  sources.
* `docs/data_dictionary.md`: added the `Provenance` field spec and the
  full ClinicalTrials.gov API v2 → `OutcomeRecord` field mapping table.
* Session 4: real-title classifier validation (33 real titles, 1 bug
  found/fixed). Session 5: real-results extraction confirmed blocked by
  environment; reproducible script delivered. Session 6: two approved
  Category A fixes implemented (ORR/CR+PR synonyms, year-based
  fixed-timepoint OS), plus two decimal-number mis-parse bugs found and
  fixed (one pre-existing from session 4, undetected until this
  session's re-validation) -- see "Session 6 Summary" above for the
  complete before/after real-data diff. Full suite: 47/47 passing.

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

Session 5's data-integrity/tooling blocker was resolved externally: you
ran the real-results extraction yourself (Google Colab, real network
access), producing a real 20-study/3,552-record/3,497-flagged dataset.
Session 6 analyzed it, implemented the 2 approved Category A fixes,
and re-validated. **This does NOT mean the classifier is validated or
production-ready** — session 5's Category B/D/F findings (EFS, pCR,
BOR, TTR, CRi, OR-by-modality, 67-row long tail — 119 rows) are
unresolved and require a scoping decision before further code changes.
Per instruction, this cycle stops here for your review.

## Tests

`pytest tests/` — 47/47 passing:
* `tests/test_endpoints.py` (28, +13 this session) — classification
  rules incl. the session-4 follow-up-ceiling regression test, plus
  session-6's ORR-synonym (7), year-based-OS (4), and decimal-number
  mis-parse (2) regression tests.
* `tests/test_ingest_and_audit.py` (9) — CSV ingestion validation
  failure modes and end-to-end audit, mock fixtures.
* `tests/test_clinicaltrials_adapter.py` (10) — ClinicalTrials.gov
  adapter incl. `filter_advanced` support.

Session 4 ran the classifier against 33 real titles. Session 6
re-ran it against your real 3,552-record/20-study dataset with a full
row-level before/after diff (see "Session 6 Summary" above) — the most
thorough real-data validation to date, though still scoped to what the
provided `records.csv` contains, not a fresh live extraction.

## Blockers

* **Value/group extraction (`extract_outcome_records()`) still has no
  FRESH real-data validation from this specific codebase** — session
  6's re-validation reused your already-extracted `records.csv`
  (produced by your Colab run), which is real data, but doesn't
  independently re-verify the extraction code path itself running
  end-to-end from raw JSON in this environment. This sandbox's network
  egress still does not include `clinicaltrials.gov` for that.
* **119 rows (Category B/D/F from session 5) remain unresolved**: EFS
  taxonomy (6 rows), pCR taxonomy (12 rows), BOR handling (15 rows),
  OR-by-modality/biomarker-subgroup fragmentation (18 rows),
  hematologic CRi/TTR (2 rows), and a 67-row miscellaneous long tail.
  None of these were touched this session, per explicit instruction to
  implement ONLY the 2 approved fixes.
* The 5,165-row / 801-classified counts recorded elsewhere in this
  file remain unverified legacy notes and must not be cited as current.

## Next Recommended Task

1. **You (human) decide** on each of the 119 Category B/D/F rows from
   session 5's analysis: which (if any) warrant taxonomy expansion
   (EFS, pCR as named exclusions were recommended) vs. remain
   deliberately unclassified vs. need individual review (the 67-row
   long tail).
2. Once scoped, implement only the approved subset, the same
   incremental, tested, re-validated way session 6 did.
3. Independently, consider running
   `scripts/validate_real_clinicaltrials_data.py` fresh (or re-running
   your Colab extraction) to validate the extraction code path itself
   end-to-end, not just re-use the already-extracted CSV.
4. Only once the classifier is explicitly approved as sufficient for
   the current phase: proceed to large-scale ingestion, additional
   sources (PubMed/NCBI, OpenAlex, FDA, PubChem, ChEMBL, UniProt, Open
   Targets), ML modeling, or UI work.

## Human Decisions Required

* Scoping decision on the 119 Category B/D/F rows (see above) — this
  is the primary open decision blocking further classifier work.
* Whether to re-run extraction fresh in an environment with real
  network access, to validate `extract_outcome_records()` end-to-end
  rather than via an already-extracted CSV.
