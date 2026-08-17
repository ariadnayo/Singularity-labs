# Singularity Labs — Autonomous State

## Last Updated

2026-08-14 (session 9)

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
