# Singularity Labs — Autonomous State

## Last Updated

2026-08-14 (session 15)

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

## Session 8 Summary: EFS/pCR/BOR Named Exclusions Implemented and Verified (2026-08-14)

**Scope: exactly item #1 of your session-7 decision, nothing else.**
TTR left unclassified with no special handling (item #2, unchanged).
Hematologic CRi/leukemia-style response left as a documented future
scope decision (item #3, unchanged). OR-by-modality left unclassified,
no schema/classifier change (item #4, unchanged).

### What changed

Added EFS, pCR (incl. tpCR/bpCR/"Total pCR" phrasings), and BOR to
`_NON_CANONICAL_PATTERNS` in `src/singularity/endpoints.py` — the same
mechanism already used for DCR/CBR/TTP/QoL/AE. Deliberately did NOT
add a bare `\bpcr\b` or `\bbor\b` pattern: bare "PCR" collides with the
unrelated molecular-biology assay (polymerase chain reaction), and
matching it would produce a misleading `reason` string even though the
classification outcome (unclassified) would be unchanged either way.
Only the specific real-world oncology phrasings found in the actual
dataset (tpCR, bpCR, "pathological complete response," "best overall
response") are matched.

Also updated `docs/data_dictionary.md`'s "Related Measures That
Require Careful Handling" list with the same three additions and their
rationale, and the module docstring in `endpoints.py`.

4 new regression tests: EFS-not-DFS (4 real titles), pCR-not-ORR (3
real titles), BOR-not-ORR (1 real title), and a conservatism guard
confirming a bare "PCR" (molecular assay context) does not trigger the
pCR-specific reason text. **Full suite: 51/51 passing.**

### Re-validation against the real dataset — exact row-level accounting

Re-ran against the same real 3,552-record/20-study dataset
(`data/clinicaltrials_normalized/real_results_run_20260814_colab/records.csv`)
and did a complete row-by-row diff against the session-6 baseline:

- **`endpoint`, `subtype`, and `confident` are byte-identical for all
  3,552 rows.** Confirmed zero rows changed classification outcome —
  exactly as expected, since this change only adds new *named*
  exclusions for rows that were already correctly unclassified.
- Top-line counts unchanged: 55 confidently classified, 3,497 flagged,
  same endpoint distribution (`PFS: 39, OS: 26, ORR: 26, DOR: 1`).
- **`reason` text changed for 307 rows total** — reported precisely,
  not rounded down:
  - **33 rows**: the intended EFS/pCR/BOR rows, which now carry a
    specific, documented reason instead of the generic "no canonical
    endpoint pattern matched."
  - **274 rows**: pre-existing DCR/CBR/TTP/QoL/AE rows whose `reason`
    text also changed, but *only cosmetically* — they matched the same
    patterns as before and still return the same
    endpoint/subtype/confident; their reason string changed only
    because it shares a single generic example-list template
    (`"e.g. DCR, CBR, TTP, QoL, AE"` → `"...EFS, pCR, BOR"`) with the
    newly-added patterns. Disclosed rather than hidden or rounded into
    the "33 rows affected" headline number.

### Explicit non-scope, confirmed unchanged this session

- TTR: still fully unclassified, no pattern added, no special-case
  logic. 1 row of evidence remains insufficient per your decision.
- Hematologic CRi / leukemia-style "Complete or Partial Remission":
  untouched. Still an open, documented scope question (does
  Singularity Labs cover hematologic malignancies?) — not resolved by
  this session.
- OR-by-modality (18 rows, fragmented ORR-family data by assessment
  modality × biomarker subgroup): untouched. Still unclassified,
  pending a future aggregation/data-model decision, not a classifier
  change.
- No new canonical endpoints. No ML, additional data sources, or UI
  work started.

## Session 9 Summary: Phase 2A — Trial/Data Architecture Implemented (2026-08-14)

**Human-approved architecture decisions carried into this session:**
PostgreSQL for persistent storage, Python/FastAPI for the backend/API
(NOT started this session), Next.js + TypeScript for the frontend (NOT
started this session), existing Python data/classification layer kept
intact rather than rewritten, ClinicalTrials.gov remains the first
data source. Explicitly out of scope and untouched: ML, new endpoint
taxonomy, hematologic CRi, TTR, OR-by-modality aggregation, additional
data sources.

### What was built

1. **`Trial` entity** (`src/singularity/schema.py`) — protocol-level
   metadata, distinct from `OutcomeRecord`, linked by `nct_id`.
2. **`extract_trial` + `ClinicalTrialsAdapter.fetch_trials`**
   (`src/singularity/sources/clinicaltrials.py`) — maps `protocolSection`
   onto `Trial`, same `.get()`-with-`None`-default pattern as the
   existing outcome extraction, never fabricates a missing field.
3. **PostgreSQL schema** (`db/migrations/0001-0003.sql`) — three
   tables: `trials`, `outcome_records` (observed data only),
   `endpoint_classifications` (derived, versioned classifier output).
   Deliberately separated per the project's existing observed-vs-
   derived principle (`architecture.md`, `Claude.md` §7) rather than
   mixing classifier output into the same row as raw data.
4. **`CLASSIFIER_VERSION` constant** (`src/singularity/endpoints.py`)
   — one-line, purely additive metadata so DB-persisted classifications
   are tied to which version of the classifier produced them. **Not a
   rewrite**: confirmed via full test suite passing unchanged before
   and after this addition.
5. **`db/README.md`** — full design rationale, including the six
   deliberate design principles (observed/derived separation,
   versioned classifications, provenance on every table, dates as TEXT
   not DATE, no artificial uniqueness on `outcome_records`, CHECK
   constraint on `endpoint`).

### Real verification performed, not just syntax-checked

This sandbox had `apt`/`pypi` access (unlike `clinicaltrials.gov`), so
PostgreSQL 16 was actually installed and run locally this session, and
the schema was genuinely verified against it, not just eyeballed:

- All three migrations ran cleanly against a real local instance.
- Real `Trial`, `OutcomeRecord`, and `ClassificationResult` Python
  objects (via the actual dataclasses, not hand-typed SQL) were
  inserted and read back correctly — field-for-field round-trip
  confirmed, including array columns (`phases`, `conditions`,
  `interventions`) and the `latest_endpoint_classifications` view.
- The `outcome_records.nct_id` foreign key was confirmed to actually
  reject an outcome record referencing an unknown trial
  (`ForeignKeyViolation`, not silently accepted).
- The `endpoint_classifications` CHECK constraint was confirmed to
  actually reject an invalid endpoint value (`CheckViolation`).
- This manual verification was then captured as an automated,
  reproducible test file (`tests/test_db_schema.py`, 6 tests) that
  creates a uniquely-named scratch database per test run and drops it
  afterward — never touches a persistent application database.
- Confirmed the DB tests **skip cleanly (not fail)** when no
  PostgreSQL instance is reachable (stopped the service and re-ran to
  verify) — this matters because most environments running this test
  suite (including this project's own sandbox in other sessions) won't
  have a persistent database available.

### Field-verification gap, disclosed honestly

This session's web-fetch tooling was unavailable (unlike sessions
4/5/6, which used it to verify ClinicalTrials.gov API behavior live).
Only `protocolSection.identificationModule.nctId` and
`protocolSection.outcomesModule` remain independently verified against
a real live API response in this project. `extract_trial`'s other
field mappings (`statusModule.overallStatus`, `designModule.phases`,
`sponsorCollaboratorsModule.leadSponsor.name`, etc.) are implemented
using the publicly documented, long-stable ClinicalTrials.gov API v2
schema, but were NOT re-verified against a fresh live response this
session. This is disclosed in three places (schema.py docstring,
clinicaltrials.py docstring, db/README.md) rather than presented as
equally-verified. **Recommend a live spot-check of these fields before
Phase 2B trusts `Trial` data at scale.**

### Test suite

**64/64 passing** (51 pre-session-9 + 7 new Trial-extraction tests + 6
new DB schema tests).

### What remains before Phase 2B

- No ingestion-to-database orchestration function exists yet (tests
  insert directly; there's no single `ingest_trial_and_outcomes(study)`
  pipeline call).
- No FastAPI service, no ORM/migration-tool decision (deferred — the
  right choice depends on the API framework, a Phase 2B decision).
- The `protocolSection` field-verification gap above.
- Everything explicitly out of scope this session remains out of
  scope: ML, new endpoint taxonomy, hematologic CRi, TTR, OR-by-
  modality aggregation, additional data sources, API, frontend.

### Decisions that would need your approval before Phase 2B proceeds

- ORM choice (or continued raw SQL) for the FastAPI layer.
- Whether/how to resolve the field-verification gap (e.g., prioritize
  a live spot-check run before building on top of untrusted fields).
- Ingestion orchestration design (one function per study? batch job?
  where does it run, given this sandbox still can't reach
  `clinicaltrials.gov` directly?).

None of these were decided or guessed at in this session — flagged for
you, per instruction to stop rather than guess on genuine architecture
decisions.

## Session 10 Summary: Ingestion Orchestration Pipeline Implemented and Verified (2026-08-14)

**Scope: the full fetch → normalize → classify → PostgreSQL pipeline,
per explicit instruction.** ML, new endpoint taxonomy, hematologic
CRi, TTR, OR-by-modality aggregation, additional data sources, and
frontend/UI remain completely untouched, per instruction.

### What was built

1. **`extract_outcome_records_verbose`** (`sources/clinicaltrials.py`)
   — backward-compatible addition alongside the unchanged
   `extract_outcome_records` (both now call a shared internal
   implementation; confirmed zero behavior change via full suite
   passing before and after the refactor). Reports every skipped
   outcome measure (currently: missing title) with a reason, instead
   of silently dropping it with no trace.
2. **`ClinicalTrialsAdapter.iter_studies`** — small additive method so
   the pipeline can fetch raw studies once and extract both `Trial`
   and `OutcomeRecord` data from the same fetch, instead of the
   pipeline calling `fetch_trials()` and `fetch_outcome_records()`
   separately and paging through the API twice for no reason.
3. **`singularity.db`** — low-level PostgreSQL write helpers
   (`upsert_trial`, `replace_outcome_records_for_trial`,
   `insert_classifications`, `get_connection`). Raw SQL via psycopg2,
   no ORM (none has been chosen — Phase 2B decision).
4. **`singularity.pipeline`** — `run_clinicaltrials_ingestion(conn,
   adapter, ...)` orchestrates the full pipeline and returns an
   `IngestionReport` (mirrors the existing `AuditReport`/
   `ValidationReport` pattern).
5. **`scripts/run_clinicaltrials_ingestion.py`** — reproducible script
   for a human to run real end-to-end (real network + real database)
   ingestion, following the exact pattern established in session 5's
   `scripts/validate_real_clinicaltrials_data.py`.

### Design decision flagged for your review (not unilaterally settled)

The existing schema (session 9) deliberately has no natural-key
uniqueness on `outcome_records`, to preserve genuine duplicate rows in
real ClinicalTrials.gov data. That means idempotent re-ingestion for a
trial can't use a simple "insert if not present" check — there's no
reliable way to distinguish "this is the same row as last time" from
"this is a second, genuinely distinct duplicate." I resolved this with
a **delete-then-insert-per-trial** strategy: each ingestion run
replaces a trial's `outcome_records` wholesale (old
`endpoint_classifications` cascade-delete automatically via the
existing FK). This makes re-runs idempotent in the sense that matters
(same input → same final state) and correctly reflects genuinely
changed source data on re-run (verified by a test that changes a
trial's status between two ingestion runs and confirms the DB reflects
the new value). **The cost**: row-level classification history is not
preserved across re-ingestion runs of the same trial — a re-run with
identical source data produces new `outcome_records.id` values and
therefore a fresh classification row, not literally the same row
re-classified. This is a standard, defensible ETL pattern given the
schema's own constraints, but it IS a design choice. If you intended
append-only/content-hash-based row stability instead, this should be
revisited before Phase 2B builds further on top of it.

### Real verification performed, and its exact boundary

**Real PostgreSQL, mocked network** (same pattern as session 9):
`tests/test_pipeline.py`'s 7 tests all run against a real, disposable
local PostgreSQL 16 instance (uniquely-named scratch database per
test, dropped after), with a mocked HTTP transport. This genuinely
verifies: end-to-end DB writes, idempotent re-run (both unchanged and
changed source data), partial-failure handling (a real test injects a
realistic malformed-JSON shape — `"classes": null` where a list was
expected — into the middle of a 3-study batch and confirms the other 2
studies still ingest correctly while the failure is reported by NCT ID
and exception type), provenance survival through the full pipeline,
and the structural separation of observed data (`outcome_records`, no
classifier columns) from derived data (`endpoint_classifications`).

**Real network was NOT available and NOT used.** This sandbox still
cannot reach `clinicaltrials.gov` — confirmed again this session by
actually running `scripts/run_clinicaltrials_ingestion.py` here: it
correctly connected to a real local database, then correctly failed
loudly with a real `HTTPError: 403 Forbidden` when it tried to reach
the live API, rather than silently succeeding with fabricated data.
**No claim of real end-to-end ingestion is made.** That requires a
human running the script above from an environment with real network
access.

### Test suite

**71/71 passing** (64 pre-session-10 + 7 new `test_pipeline.py` tests).

### What remains before Phase 2B (API layer)

- Real end-to-end ingestion (real network + real DB) has not been run
  by anyone yet — the script is ready, waiting on you.
- The `protocolSection` field-verification gap from session 9 (only
  `nct_id` independently verified live) is unchanged.
- No ORM/migration-tool decision made.
- The idempotency design choice above should be explicitly confirmed
  or revised before more is built on top of it.
- Everything explicitly out of scope this session remains out of
  scope: ML, new endpoint taxonomy, hematologic CRi, TTR, OR-by-
  modality aggregation, additional data sources, frontend/UI, and the
  FastAPI service itself.

## Session 11 Summary: Real Ingested-Data Validation — Bugs Found, NOT Yet Fixed (2026-08-14)

**First genuinely real end-to-end validation of this project**: a
human ran `scripts/run_clinicaltrials_ingestion.py` from Google Colab
(real network access) against a real PostgreSQL database. Result: 10
real ClinicalTrials.gov studies fetched, 10 trials / 109 outcome
records / 109 classifications written, 0 failures, 0 malformed
records. Data exported via a join across `trials` /
`outcome_records` / `latest_endpoint_classifications` and analyzed
directly — no synthetic data, no reliance on memory.

**This is analysis only. No classifier code has been changed.**

### What was reviewed

All 13 confidently-or-low-confidence-classified rows (100% of
classified output), plus representative samples spanning every one of
8 distinct unclassified title families (96 rows) — well past the
≥20-row requirement, every finding backed by the actual
`provenance_raw` JSON for that row, not assumption.

### Findings

1. **Confirmed bug (Category A, high severity):** the fixed-timepoint
   "ceiling guard" (added session 6 to prevent follow-up-window text
   from being mistaken for a fixed assessment timepoint) only
   recognizes the phrases "up to" and "approximately". Real data
   (`NCT02360579`, outcome_record_ids 153–155) uses **"for a maximum
   of"** for the identical concept — this trial's `OS` timeframe
   ("until death or **up to** 60 months") was correctly guarded, but
   its `PFS` timeframe ("...for a **maximum of** 60 months") was not,
   causing 3 real median-PFS values (2.6/3.9/4.1 months) to be wrongly
   downgraded to low-confidence `PFS6`. This is a new variant of the
   exact bug class fixed in sessions 4 and 6 — same mechanism,
   different unguarded phrase. `ORR`/`DOR` in the same trial share the
   identical timeframe but weren't affected, only because those
   branches don't consult the fixed-timepoint detector at all — not
   because of any actual protection.
2. **Confirmed bug (Category A, cosmetic only):** `_NON_CANONICAL_PATTERNS`'s
   AE pattern (`\badverse event\b`) is singular-only. In this real
   109-row sample, **every actual occurrence of adverse-event language
   used the plural** ("Adverse Events", "TEAEs") — a 0% real-world hit
   rate for the existing pattern. Final classification is unaffected
   (falls through to the same "unclassified" outcome via the generic
   catch-all either way), but the session-8 goal of explicit, audited
   exclusion reasons is silently failing for the most common real
   phrasing.
3. **Extraction/schema gap (Category E, not a classifier bug):** ORR
   rows with `parameter=COUNT_OF_PARTICIPANTS` (`NCT02360579`,
   outcome_record_ids 143–146) store a raw responder **count** (e.g.
   23) as `value`, with no capture anywhere of the source's `denoms`
   field (the group-size denominator, e.g. 66) needed to compute an
   actual rate. Classification (`ORR`) is conceptually correct; the
   stored `value` is not itself a percentage for this measurement
   type. A downstream consumer must not assume `value` is always
   already a rate.
4. **Confirmed correct, positive finding:** DOR rows with `value=NaN`
   (`NCT02360579`, ids 147, 149) were checked against raw provenance:
   the source literally reports `"NA"` with an explanatory comment
   ("insufficient events, median not reached") — a genuine censored
   result, not malformed data. `_parse_measurement_value`'s
   None-not-guessed design handled this correctly.
5. **Observation, not a bug:** 8 PK-related titles and 2
   generic-"safety" titles (72 rows total) are correctly unclassified,
   but only by accident of matching no canonical pattern — unlike
   DCR/CBR/TTP/QoL/AE/EFS/pCR/BOR, there's no dedicated, documented
   exclusion pattern for PK or generic safety language.
6. **No false negatives found**: no case where a genuine PFS/OS/ORR/
   DOR/DFS measure was wrongly left fully unclassified in this sample
   — positive evidence for the existing exclusion logic.
7. **Open question, not resolved:** `NCT02044380` has only 4 outcome
   records, all "Safety Assesment" — unusual for its trial type. Could
   not confirm from the available per-row provenance (scoped to
   individual measures, not the full study JSON) whether this is
   genuinely all that trial has posted or a possible gap. Not asserted
   either way.

### Proposed fixes (awaiting approval, NOT implemented)

1. Extend the ceiling-guard regex to also catch "for a maximum of"
   (Finding 1) — regression test using the real title/timeframe above.
2. Add plural variants to the AE pattern (Finding 2) — regression test
   using the real title above.
3. Finding 3 requires a human decision: capture `denoms` into the
   schema now (bigger, schema-affecting change) vs. defer and document
   the limitation. No recommendation implemented either way yet.
4. Finding 5 (named PK/safety exclusions): optional, low priority,
   cosmetic-only — deferred pending human interest.

### Explicit non-claim

**Production readiness is NOT claimed.** This session confirms the
pipeline works end-to-end on real data (10 real studies → 109 real,
correctly-provenanced records → classified → persisted, 0 crashes),
and surfaces two new real classifier bugs plus one real extraction gap
that would not have been found without this real-data pass — exactly
the point of doing it. The classifier remains explicitly unvalidated
for production use until Findings 1–3 are resolved and re-validated
the same way sessions 4/6/8 did.

## Session 12 Summary: Approved Fixes #1/#2/#4 Implemented and Re-Validated Against Real Data (2026-08-14)

**Scope: exactly the 3 approved fixes from session 11's validation
report, nothing else.** Fix #3 (denominator capture) explicitly
deferred per instruction — documented below, no schema change made.
No UI, ML, additional data sources, or new taxonomy expansion.

### What changed

1. **Ceiling-guard extended** (`_fixed_timepoint_suffix`): added
   `"maximum of"` to the follow-up-ceiling phrase list (alongside the
   existing `"up to"`/`"approximately"`). Note: `"for up to ..."` and
   `"for a period of up to ..."` (other phrasings considered) already
   contain the substring `"up to"` and were already covered — no
   separate pattern needed for those.
2. **AE pattern fixed** (`_NON_CANONICAL_PATTERNS`): `\badverse event\b`
   (singular-only) → `\badverse events?\b` + new `\bteaes?\b`.
3. **New `_NON_EFFICACY_PATTERNS` list** (PK + generic safety),
   deliberately kept separate from `_NON_CANONICAL_PATTERNS` with its
   own reason string — PK/safety titles were never at risk of being
   confused with a canonical endpoint the way DCR/CBR are, so
   conflating them would blur the existing list's meaning. 9 patterns,
   every one copied from an actual real title in the validation
   dataset (`plasma concentration`, `half-life`, `plasma clearance`,
   `volume of distribution`, `auc`, `cmax`, `tmax`, `safety
   assess?ment` [matches the source's own real typo, "Assesment"],
   `safety profile`). Deliberately no bare `\bsafety\b` pattern, per
   explicit instruction.

**9 new regression tests** (2 for the ceiling fix incl. a title-level
non-suppression guard, 2 for AE, 5 for PK/safety incl. a
bare-"safety"-doesn't-suppress-efficacy guard and a
PK-patterns-never-fire-on-canonical-titles guard). **Full suite:
80/80 passing** (71 baseline + 9 new).

### Re-validation against the exact real 109-row dataset — full row-level diff

Re-ran the classifier against every one of the 109 real rows from the
Colab-exported dataset (`nct_id`, `title`, `timeframe`, etc. — the
exact CSV analyzed in session 11) and diffed every field:

- **Endpoint value: 0 rows changed, for any row, anywhere.** No
  canonical classification changed unexpectedly — confirmed by direct
  comparison, not assumption.
- **3 rows changed subtype/confidence** — exactly the predicted
  `NCT02360579` PFS rows (outcome_record_ids 153/154/155):
  `PFS6/confident=False` → `median_or_time_to_event/confident=True`.
  This was the intended effect of Fix #1, confirmed exactly.
- **96 rows changed `reason` text only** (endpoint/subtype/confident
  unchanged) — fully accounted for: the 3 PFS rows above (reason text
  changed alongside their subtype fix) + 16 PK rows (8 real titles) +
  64 safety rows (2 real titles, "Safety Assesment" ×4 and "Safety
  Profile" ×60) + 13 AE/TEAE rows (1 real title) = 96 exactly. No row
  outside these grounded, intended categories was touched.
- **No false positives**: every reason-text change maps to a specific,
  real, previously-identified title; nothing unexpected shifted.

### Fix #3 (denominators) — explicitly deferred, documented not implemented

Per instruction, no schema change was made. **Documented limitation**:
`OutcomeRecord`/`outcome_records` rows with `parameter=COUNT_OF_PARTICIPANTS`
may store a raw responder *count* rather than a rate — the source's
`denoms` field (group-size denominator) is not currently captured
anywhere. A downstream consumer must not assume `value` is always
already a percentage/rate for ORR-classified rows. See
`docs/data_dictionary.md` for where this is now documented. Tracked as
a Phase 2/data-model enhancement, not resolved this session.

### Explicit non-claim

**Production readiness is still NOT claimed.** This session fixed the
2 real bugs and added the 1 approved documentation improvement found
in session 11's real-data validation, and re-verified against the
exact same real dataset with a complete field-level diff — but this is
incremental progress on a classifier that continues to require
real-data validation on every change, not a one-time "done" state.

## Session 13 Summary: Phase 2B — API Vertical Slice Built and Verified (2026-08-14)

**Scope: exactly the approved Phase 2B plan, nothing else.** No ML,
additional data sources, taxonomy expansion, authentication,
background jobs, GraphQL, or ingestion automation. No frontend/UI —
this is the backend data layer the eventual website will call.

### What was built

1. **`singularity.value_types.infer_value_type`** — pure function,
   computes `"count"`/`"rate"`/`"time"`/`"other"` from `parameter`/`unit`
   at read time. Directly resolves the session-11 finding (a real ORR
   row with `parameter=COUNT_OF_PARTICIPANTS, value=23` is a raw
   count, not a rate — the source's `denoms` denominator, 66, isn't
   captured anywhere) **without a schema change**, per your explicit
   decision. 11 tests, every rule grounded in an actual real
   `(parameter, unit)` pair from the session-11 validation dataset —
   including a specific negative case (`"L/hr"`, `"ng*hr/mL"` — real PK
   units using the "hr" *abbreviation*, not the word "hour" — must
   stay `"other"`, not `"time"`).
2. **Read functions added to `singularity.db`**: `get_trial`,
   `list_trials` (condition/phase/status filters, capped `LIMIT`),
   `get_outcomes_for_trial` (LEFT JOIN to
   `latest_endpoint_classifications`, so a record with no
   classification yet still appears rather than vanishing). Return
   plain dicts, not dataclasses — deliberately decouples the DB read
   layer from the API response shape.
3. **Pydantic response models** (`singularity.api.models`) — written
   and tested (via direct construction, no HTTP) before any route
   existed, per the approved plan's ordering. `provenance_raw`
   deliberately excluded from every response.
4. **FastAPI app** (`singularity.api.main`) — exactly the 3 approved
   endpoints. `GET /trials/{nct_id}`, `GET /trials`,
   `GET /trials/{nct_id}/outcomes`.

### Real verification performed, and its exact boundary

**Real PostgreSQL, via the existing tested write path** (same
methodology as sessions 9/10): all 9 API tests
(`tests/test_api.py`) run against a real, disposable local PostgreSQL
16 instance, with data seeded through the actual `singularity.db`
write functions (`upsert_trial`, `replace_outcome_records_for_trial`,
`insert_classifications`) — not hand-written SQL fixtures — using real
ClinicalTrials.gov titles from the session-11 dataset (e.g. "Disease
Assessment for Objective Response Rate" with
`parameter=COUNT_OF_PARTICIPANTS`) with synthetic NCT IDs. This
directly confirms the exact real scenario that motivated `value_type`:
the seeded ORR row's API response correctly shows `"value_type":
"count"`, not `"rate"`.

**Not run against the actual Colab-ingested database** — only against
disposable local scratch databases. **Task 7 (closing the remaining
`Trial` field-verification gap) was not completed** — the session-11
Colab export lacked the columns needed
(`official_title`/`interventions`/`start_date`/`completion_date`/
`enrollment_count`); per instruction this explicitly did not block
Phase 2B, and remains open for a future session with a broader export.

### Test suite

**100/100 passing** (80 pre-session-13 + 11 `value_type` + 9 API).

### Example real API output (captured by actually running the app against seeded data, not written by hand)

`GET /trials/{nct_id}/outcomes` for a trial with a real
`COUNT_OF_PARTICIPANTS`-typed ORR row and a real median-OS row:

```json
{
  "nct_id": "NCT88800001",
  "outcomes": [
    {
      "title": "Disease Assessment for Objective Response Rate",
      "parameter": "COUNT_OF_PARTICIPANTS", "unit": "Participants",
      "value": 23.0, "value_type": "count",
      "endpoint": "ORR", "confident": true
    },
    {
      "title": "Overall Survival",
      "parameter": "MEDIAN", "unit": "months",
      "value": 24.5, "value_type": "time",
      "endpoint": "OS", "subtype": "median_or_time_to_event", "confident": true
    }
  ],
  "count": 2
}
```

### What's blocking the frontend, precisely

Nothing structural — the API is a real, tested, running FastAPI app
with a defined JSON contract. What's still missing before a website
can meaningfully use it: (1) the API hasn't been pointed at the real
Colab-ingested database yet (only tested against disposable local
databases seeded with realistic data); (2) only 3 endpoints exist —
no single-outcome-record detail endpoint, no search-across-conditions
beyond substring match, no aggregate/summary endpoints; (3) no CORS
configuration yet (a browser-based frontend calling this API from a
different origin will be blocked by the browser until that's added);
(4) no deployment target — this only runs locally right now.

### Explicit non-claim

**Production readiness is still NOT claimed.** The classifier was not
modified this session (no bug was found or approved for a classifier
change). This is backend infrastructure progress, verified the same
rigorous way as every prior session, not a "done" milestone.

## Session 14 Summary: Real-Data API Verification (2026-08-14)

**Important methodology note, stated upfront**: this sandbox has no
network path to the actual live Colab-hosted database — there is no
way to open a direct connection to wherever that instance runs. What
was done instead, and is fully honest about the distinction: the
**exact real dataset** you exported (109 real rows, real NCT IDs, real
titles/values/classifications from the real Colab ingestion) was
loaded into a genuine local disposable PostgreSQL 16 instance, using
the same tested `singularity.db` write functions the real ingestion
pipeline itself uses — not hand-written SQL, not synthetic data. The
actual FastAPI app object was then run against that database via
`TestClient` (the standard, correct way to exercise a FastAPI app;
functionally identical request/response handling to a live `uvicorn`
process — confirmed separately that `uvicorn` itself starts correctly
and serves the real OpenAPI schema over an actual socket before the
sandbox's per-tool-call shell isolation ended that process). **This
verifies the real data content and the real API code path completely.
It is not a live connection to your Colab instance** — flagged clearly
so this isn't overclaimed.

### Task 1 — configurability: no change needed

`get_db_connection()` already delegated to `db.get_connection()`,
which already reads `SINGULARITY_DATABASE_URL`. Confirmed by
inspection before writing any code.

### Tasks 2–5 — real verification results, all three real trials

| Trial | Category | Rows | Result |
|---|---|---:|---|
| `NCT02360579` | Canonical + mixed | 76 | 13 confidently classified (ORR×4, DOR×3, PFS×3, OS×3, all `confident=true`); 63 correctly excluded (DCR×3, Safety Profile×60) |
| `NCT01324323` | Mostly excluded (PK) | 29 | 0 classified — all 29 real PK/AE titles correctly `endpoint=null`, none dropped |
| `NCT02044380` | Fully excluded (safety) | 4 | 0 classified — all 4 real "Safety Assesment" rows (the source's own real typo) correctly excluded |

**All 6 verification criteria confirmed directly against real data:**
- **Trial metadata correct**: titles, sponsors ("Celgene", "Boehringer
  Ingelheim", "Iovance Biotherapeutics, Inc."), conditions, phases,
  status all matched the source export exactly.
- **Outcome records correctly returned**: all 109 real rows present
  across the three trials (76+29+4), matching the export exactly.
- **Endpoint/subtype/confidence match the database**: every classified
  row's `endpoint`/`subtype`/`confident` matched what session 12's
  re-validation established, with no drift.
- **`value_type` correctly distinguishes real cases** — every rule
  confirmed against real data, not just synthetic unit tests: the
  exact real risk case (ORR, `COUNT_OF_PARTICIPANTS`, value=23) →
  `"count"`; the real rate case (`Safety Assesment`, `Percentage of
  participants`, value=92.9) → `"rate"`; real PK units with the "hr"
  *abbreviation* (`ng*hr/mL`, `L/hr`) correctly stayed `"other"`, not
  misclassified as `"time"`; real PK units with the spelled-out word
  ("hours", Tmax/half-life) correctly showed `"time"`.
- **Unclassified/excluded records not silently dropped**: all 29 PK
  rows and all 4 safety rows returned in full — confirmed by exact
  count match, not sampling.
- **Provenance available where intended by the contract**: the
  contract (session 13) deliberately excludes `provenance_raw`/
  `provenance_*` from every response — confirmed none leaked into any
  real response. No detail endpoint exists yet that would expose it
  (that's the "where intended" case, not yet built).

**One honest negative finding, not hidden**: this specific 109-row
real dataset has **zero remaining low-confidence classified rows**
(all 13 classified rows are `confident=true`) — a direct, positive
consequence of session 12's ceiling-guard fix (which corrected the
one low-confidence case that existed in this data). This means the
"low-confidence classification" verification category couldn't be
satisfied from a literal row in this dataset. Closed instead with a
test using a real, previously-validated ClinicalTrials.gov phrasing
pattern (session 6's "Percentage of Participants Surviving at N
Year(s)") on a synthetic NCT ID, clearly labeled as such — not
presented as if it came from this specific 109-row export.

### Task 6 — new integration tests (4 added, closing real gaps)

`tests/test_api.py` grew from 9 to 13 tests: CORS header presence,
real PK title → `"other"` value_type via the live API, real rate title
→ `"rate"` via the live API, real DOR title → confident classification
via the live API, the low-confidence case above, and a 40-row
all-unclassified batch confirmed not silently dropped (grounded in the
real fact that `NCT02360579`'s "Safety Profile" alone contributed 60
unclassified rows).

### Task 7 — CORS added

`CORSMiddleware` added to `singularity.api.main`, `GET`-only, no
credentials (no auth exists yet), default origins covering common
local frontend dev servers (`localhost:3000`/`5173`), overridable via
`SINGULARITY_CORS_ORIGINS`. **Frontend itself not started** — this
only removes a browser-side blocker for when it is.

### Task 8 — no classifier/schema/ingestion changes

Real verification found zero failures requiring a fix. Nothing in the
classifier, taxonomy, database schema, or ingestion logic was touched
this session.

### Test suite

**104/104 passing** (100 pre-session-14 + 4 new).

### Explicit non-claim

**Production readiness still NOT claimed.** This session closes the
real-data API verification gap using the exact real dataset (loaded
into a genuine local replica, not a live connection to Colab) — a
meaningfully different and stronger form of verification than the
purely-synthetic tests from session 13, but still not equivalent to
running this API continuously against a live, network-connected
production database. No frontend/UI work was started.

## Session 15 Summary: MVP Progress — Field-Verification Gap, Deployment Prep (2026-08-14)

### Step 1 — Trial field-verification gap: inspected, one real bug found and fixed, live verification still open

**Found by code inspection** (no live web-fetch tooling was available
this session either — same constraint as sessions 9/10): `Trial.provenance.raw`
was missing `armsInterventionsModule`, even though the `interventions`
field is extracted from it — meaning that field could never be
audited against its own source. **Fixed additively** (one more key in
the `raw` dict; no schema change, no `Trial` dataclass change). 1
regression test added.

**What still can't be verified without your help**: no real
`protocolSection` JSON is available anywhere in this repo or my
current session — the CSV export from session 11 only has 6
trial-level columns (`brief_title`/`overall_status`/`phases`/
`conditions`/`lead_sponsor`, no `provenance_raw` at the trial level).
**Exact query needed** (documented in `docs/deployment.md` too):

```python
import psycopg2, csv
conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()
cur.execute("""
    SELECT nct_id, official_title, interventions, start_date, completion_date,
           enrollment_count, provenance_raw
    FROM trials
""")
with open("/content/trials_field_check.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow([d[0] for d in cur.description])
    w.writerows(cur.fetchall())
```

**Important caveat already known**: even this query, run against your
*existing* real database, won't show `armsInterventionsModule` in
`provenance_raw` — that data was ingested *before* this session's fix.
Confirming `interventions` extraction specifically requires re-running
ingestion with the updated code. The other four fields
(`official_title`, `start_date`, `completion_date`, `enrollment_count`)
can be checked against your existing database right now, no
re-ingestion needed.

### Step 2 — deployment architecture: Render (one concrete recommendation)

Managed PostgreSQL + one FastAPI web service, both defined in a single
committed `render.yaml` blueprint. No ORM, no GraphQL, no background-
job system, no auth — matches the codebase exactly as it exists.
Ingestion stays a human-run script against the deployed DB's
connection string (Render's optional Cron Jobs could automate this
later, not enabled now). Full rationale in `docs/deployment.md`.

### Step 3 — deployment readiness implemented

1. **`DATABASE_URL` fallback** (`singularity.db.get_connection`) —
   `SINGULARITY_DATABASE_URL` still wins if both are set; falls back
   to the plain `DATABASE_URL` most hosting platforms auto-inject.
2. **Clean 503 on missing/failed DB config** — `get_db_connection`
   (the FastAPI dependency) now converts a missing-config `ValueError`
   or a connection failure into `HTTPException(503, ...)` with an
   actionable message, instead of an unhandled 500/traceback.
3. **`GET /health`** — never raises, reports `{"status": "ok",
   "database": "connected"|"unreachable"|"not_configured"}`. Attempts
   a real `SELECT 1` when configured; falls back to `"not_configured"`
   cleanly when no DSN is set at all. Verified against both states
   directly (real local Postgres → `"connected"`; env vars unset →
   `"not_configured"`, still HTTP 200).
4. **`GET /`** — basic liveness/info endpoint, never touches the
   database (many platforms ping `/` by default; must stay up even if
   the DB is completely down).
5. **`render.yaml`** — committed blueprint, database connection wired
   via Render's `fromDatabase` binding (never a literal credential in
   the file).
6. **`docs/deployment.md`** — full walkthrough: apply blueprint, run
   migrations against the deployed DB, verify `/health`, run
   ingestion, set CORS for the real frontend origin once one exists.
7. **No secrets committed** — verified directly:
   `git grep -i "postgresql://" -- ':!tests' ':!*.md'` returns only
   two placeholder examples (`user:pass@host`, `....`), no real
   credentials anywhere.
8. **API/OpenAPI docs** — `/docs` and `/redoc` auto-generated by
   FastAPI from the existing Pydantic models; confirmed both new
   endpoints appear correctly in the OpenAPI schema.

### Real verification performed, and its exact boundary

**Real local PostgreSQL** (same methodology as every prior session):
all new tests run against a real, disposable local instance. Directly
confirmed (not assumed): `/` and `/health` both return `200` with zero
database environment variables set; a data endpoint (`/trials`)
returns a clean `503` with an actionable message in the same
zero-config state; `/health` correctly reports `"connected"` against a
real database via an actual `SELECT 1`.

**Not verified**: an actual Render deployment. `render.yaml` has not
been applied to a real Render account — this is infrastructure-as-
config that has not itself been deployed and tested end-to-end.
**Per instruction, production readiness is explicitly not claimed
until the deployed API has been tested against the real database.**

### Test suite

**109/109 passing** (104 pre-session-15 + 1 provenance-completeness
regression + 4 new health/root/503 tests).

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

## Session 7 Summary: Taxonomy/Scoping Analysis Complete, Awaiting Human Decision (2026-08-14)

**Analysis only — no code changed.** Full document:
`docs/endpoint_taxonomy_analysis.md`.

Re-clustered the real 3,552-record dataset's fully-unclassified rows
against the current (post-session-6) classifier, excluding everything
already confirmed correctly-excluded in session 5/6. Result: **115
rows / 40 unique titles / 11 trials** (close to session 5's 119
estimate; the small difference is disclosed and explained in the
document itself — a couple of titles moved into "already has a
canonical endpoint, just low-confidence" after session 6's fixes, plus
a plural-regex miss in the analysis script itself, both accounted for
rather than hidden).

15 distinct endpoint/measure families identified and quantified: BOR,
pCR, EFS, OR-by-modality, biomarker/exploratory, local failure,
biopsy-completion feasibility, tumor-size continuous change,
operational/cost/hematologic-support, leukemia-style remission,
hematologic CRi, generic unanchored "objective response," transfusion
independence, TTR, and Duration of Disease Control.

**Recommendation, pending your approval:**
- Add EFS, pCR, and BOR as explicitly-named excluded subtypes (same
  mechanism already used for DCR/CBR/TTP) — no new canonical endpoints,
  just making already-correct behavior intentional and documented.
- Everything else in the 115 rows: leave as-is (correctly excluded, or
  insufficient volume to justify taxonomy action).
- Three items explicitly flagged as needing YOUR decision, not
  resolved by data alone: (1) whether hematologic CRi/leukemia-style
  "remission" terminology warrants its own family — depends on whether
  hematologic malignancies are in scope for Singularity Labs; (2)
  whether/how OR-by-modality fragmentation should ever aggregate into
  ORR — a schema design question, not a taxonomy question; (3) TTR —
  only 1 row of evidence, revisit if it recurs at scale.

No canonical endpoints (PFS/OS/ORR/DOR/DFS) were proposed for addition
or change. No classification-rate change resulted from this document
by design — it's a scoping analysis, not an implementation.

**Status: awaiting your review and scoping decision before any further
classifier implementation proceeds**, per instruction.

## Current Priority

Session 7 delivered a taxonomy/scoping analysis of the 115 remaining
uncategorized rows (`docs/endpoint_taxonomy_analysis.md`). You reviewed
it and made 4 explicit decisions; session 8 implemented exactly item
#1 (EFS/pCR/BOR named exclusions) and stopped, per instruction. Items
#2–#4 (TTR, hematologic CRi, OR-by-modality) remain deliberately
untouched. **The classifier is still NOT validated or production-
ready** — this was a narrow, approved documentation/exclusion change,
not a completeness milestone.

## Tests

`pytest tests/` — 51/51 passing:
* `tests/test_endpoints.py` (32, +4 this session) — classification
  rules incl. session-6's ORR-synonym/year-based-OS/decimal-number
  tests, plus session-8's EFS/pCR/BOR named-exclusion tests (using
  real titles from the validation dataset) and the bare-"PCR"
  conservatism guard.
* `tests/test_ingest_and_audit.py` (9) — CSV ingestion validation
  failure modes and end-to-end audit, mock fixtures.
* `tests/test_clinicaltrials_adapter.py` (10) — ClinicalTrials.gov
  adapter incl. `filter_advanced` support.

Session 6 re-ran the classifier against your real 3,552-record/
20-study dataset with a full row-level before/after diff. Session 8
did the same again for this narrower change — see "Session 8 Summary"
above for the exact row-level accounting (0 classification changes,
307 reason-text changes, 33 of them the intended new exclusions).

## Blockers

* **Value/group extraction (`extract_outcome_records()`) still has no
  FRESH real-data validation from this specific codebase** — sessions
  6 and 8 both reused your already-extracted `records.csv`, not a
  fresh live extraction run in an environment with real network
  access. This sandbox's network egress still does not include
  `clinicaltrials.gov`.
* **94 rows remain from the original 115/119-row taxonomy analysis,
  deliberately unresolved per your explicit decision**: TTR (1 row,
  leave unclassified, no special handling), hematologic CRi /
  leukemia-style remission (3 rows, documented future scope question),
  OR-by-modality (18 rows, pending a future aggregation/data-model
  decision), and the remaining ~72 rows across biomarker/exploratory,
  local failure, biopsy-completion feasibility, tumor-size continuous
  change, and operational/cost measures (all already confirmed
  correctly excluded in the session-7 analysis, no action needed).
* The 5,165-row / 801-classified counts recorded elsewhere in this
  file remain unverified legacy notes and must not be cited as current.

## Next Recommended Task

1. No further classifier changes are approved or pending — session 8
   closes out the current approved scope. Any future classifier work
   requires a new explicit decision from you (e.g. on hematologic
   malignancy scope, or an OR-by-modality aggregation design).
2. Independently, consider running
   `scripts/validate_real_clinicaltrials_data.py` fresh (or re-running
   your Colab extraction) to validate the extraction code path itself
   end-to-end, not just re-use the already-extracted CSV.
3. Per explicit instruction: no large-scale ingestion, additional
   sources (PubMed/NCBI, OpenAlex, FDA, PubChem, ChEMBL, UniProt, Open
   Targets), ML modeling, or UI work has started, and none should start
   without your explicit go-ahead.

## Human Decisions Required

* None pending on the classifier itself right now — session 8 fully
  implemented the one approved item and stopped. Future decisions
  needed only if/when you want to revisit hematologic-malignancy scope
  or OR-by-modality aggregation design.
* Whether to re-run extraction fresh in an environment with real
  network access, to validate `extract_outcome_records()` end-to-end
  rather than via an already-extracted CSV.
