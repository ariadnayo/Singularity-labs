# Endpoint Taxonomy / Scoping Analysis

**Date:** 2026-08-14 (session 7)
**Status:** Analysis only. No classifier code has been changed as part of this document.
**Data source:** `data/clinicaltrials_normalized/real_results_run_20260814_colab/records.csv`
(the real 20-study / 3,552-record dataset, verified in session 6 — see
`docs/autonomous_state.md` "Session 6 Summary" for its provenance).
Nothing in this analysis uses synthetic data or memory-based
extrapolation; every count and example below was computed directly
from that file using the current (post-session-6) classifier.

## 0. Reconciling the row count

Session 5's original analysis estimated the Category B/D/F remainder
at 119 rows. Re-running that clustering fresh against the current
classifier state (post-session-6 fixes) gives **115 rows across 40
unique titles, from 11 distinct trials** — close to the original
estimate but not identical, for two disclosed reasons:

1. Session 6's fixes reclassified a few titles (e.g. "Evaluate the
   Progression-free Survival Rate") from fully-unclassified into
   `endpoint=PFS, subtype=PFS_rate` — they now carry a canonical
   endpoint (just low-confidence), so they no longer belong in "outside
   the taxonomy entirely" and were correctly excluded from this
   analysis.
2. A regex bug in the *analysis clustering script itself* (not the
   classifier) failed to match plural "TEAEs" against a singular
   `\bteae\b` pattern, initially miscounting 12 real adverse-event rows
   as "remainder" when they are actually a correctly-excluded AE/safety
   measure. Fixed before producing the table below.

All numbers below are the freshly verified 115-row/40-title figure,
not a reproduction of the earlier estimate.

## 1. Category table

| Category | Rows | Titles | NCT IDs | Typical unit(s) | Typical timeframe(s) |
|---|---:|---:|---|---|---|
| BOR (Best Overall Response) | 15 | 1 | NCT01014936 | subjects | Baseline up to 153.3 weeks |
| pCR (pathological complete response) | 12 | 5 | NCT01998906, NCT02273973 | percentage of participants | Pre-surgery cycle timepoints; Baseline→16 weeks |
| EFS (event-free survival) | 15 | 5 | NCT01998906 | percentage of participants; months | Long multi-year post-surgical follow-up schedules |
| OR-by-modality (fragmented ORR by assessment method × biomarker subgroup) | 18 | 9 | NCT02273973 | percentage of participants | Baseline→16 weeks |
| Biomarker/exploratory (H-Score, Ki67, PPV/NPV, genomic testing reach) | 24 | 5 | NCT01014936, NCT01979003, NCT02273973, NCT03130569 | units on a scale; fold change; percentage; participants | 1 day; Baseline/Day1 Cycle2; 3 months |
| Local control / local failure (radiotherapy-specific) | 6 | 1 | NCT02947984 | participants | 15 years |
| Molecular-treatment-assignment feasibility (biopsy completion) | 6 | 3 | NCT02213289 | biopsies; participants | Up to 1 / 60 months |
| Tumor-size/imaging change (continuous, not a RECIST response-rate category) | 5 | 2 | NCT01014936, NCT02273973 | percent change | Baseline→Weeks 17-18; on-treatment up to 153.3 weeks |
| Operational/cost/hematologic-support (LOS, hospital cost, RBC transfusion) | 6 | 4 | NCT02666950, NCT03476707 | Dollars; Days; Participants | Admission→discharge; up to 17 months |
| Complete or Partial Remission (leukemia-style, non-RECIST) | 2 | 1 | NCT00526292 | participants | 3 months post-treatment |
| Hematologic CRi (CR or CRi, NCCN criteria) | 1 | 1 | NCT02666950 | percentage of patients | Up to 17 months |
| Objective response, generic phrasing (no RECIST/CR+PR anchor) | 2 | 1 | NCT02213289 | Participants | Up to 6 months |
| Hematologic clinical benefit (transfusion independence) | 1 | 1 | NCT02666950 | Participants | Up to 17 months |
| TTR (time to response) | 1 | 1 | NCT01022996 | Days | Every 3 months until PD/toxicity/death |
| Duration of Disease Control (broader than DOR) | 1 | 1 | NCT01022996 | Days | Every 3 months until PD/toxicity/death |
| **Total** | **115** | **40** | **11 trials** | | |

## 2. Representative real titles, per category

**BOR** — `"Number of Subjects With Best Overall Response (BOR)"` (15 rows, all one trial, presumably one row per response-category bucket [CR/PR/SD/PD/NE] × arm, though `group`/`value` breakdown wasn't separately inspected in this pass).

**pCR** — `"Percentage of Participants With Breast Pathological Complete Response (bpCR)"`, `"Percentage of Participants With Total Pathological Complete Response (tpCR)"`, `"Percentage of Participants With Total pCR, Defined as Having pCR in Both Breast and Axilla, Using AJCC Staging System"` (± biomarker-subgroup variants: PIK3CA MT/WT).

**EFS** — `"Event-Free Survival (EFS) - Percentage of Participants With an Event"`, `"Event-Free Survival"`, `"Percentage of Participants Event Free at 1/2/3 Years"`.

**OR-by-modality** — `"Percentage of Participants With OR by Centrally Assessed Breast MRI Via mRECIST Version 1.1 in PIK3CA Wildtype (WT) Participants"`, and 8 close variants differing only by assessment modality (MRI / ultrasound / mammography / clinical breast exam) crossed with PIK3CA mutant/wildtype subgroup.

**Biomarker/exploratory** — `"Absolute Change From Baseline in Cytoplasm and Membrane H-Score at Day 1 Cycle 2"`, `"Central Assessments of Changes in Ki67 Levels"`, `"Percentage of Participants With Positive Predictive Value and Negative Predictive Value From Fluorescein Visualization"`, `"Reach of Personalized Genomic Testing for Melanoma."`

**Local failure** — `"Local Failure Rate"` (radiotherapy-specific local-control endpoint, distinct from PFS).

**Biopsy-completion feasibility** — `"Completion of [Serial] Biopsy for [Second/Third] Line Therapy and Successful, Molecularly-based Treatment Assignment"`.

**Tumor-size continuous change** — `"Relative Percentage Change In Sum of Longest Diameter (SOLD) of Target Lesions to Post-Baseline Nadir"`, `"Percent Change From Baseline to Surgery in Enhancing Tumor Volume as Measured by Breast MRI"`.

**Operational/cost** — `"Total Hospital Costs"`, `"Length of Stay"`, `"Red Blood Cell Transfusion"`.

**Complete or Partial Remission (leukemia-style)** — `"Treatment Efficacy as Defined by Complete or Partial Remission"`.

**Hematologic CRi** — `"Complete Response Rate (CR or CRi) Per the National Comprehensive Cancer Network (NCCN) Guidelines or According to Specific Criteria From Expert Panels"`.

**Generic "objective response"** — `"Objective Response to First Line Therapy"` (no RECIST or CR+PR anchor — too vague to safely treat as ORR).

**Transfusion independence** — `"Clinical Benefit as Measured by the Number of Patients Who Were Not RBC Transfusion-dependent Post-Baseline"`.

**TTR** — `"Time to Overall Response (TTR) Per Kaplan-Meier Estimate"`.

**Duration of Disease Control** — `"Duration of Disease Control"` (same trial as TTR above, NCT01022996).

## 3. Category assignment (per your A–D scheme) and rationale

| Endpoint family | Conceptually equivalent to a canonical endpoint? | Decision | Rationale |
|---|---|---|---|
| **EFS** | Related to DFS, but NOT equivalent | **C — retain as distinct named subtype (excluded from DFS)** | EFS's "event" definition is protocol-specific and typically broader than DFS (may include any progression, second malignancy, or death, not only disease recurrence). Silently merging into DFS would blur genuinely different statistical populations, which `Claude.md`'s data-integrity rule explicitly prohibits. 6 rows here (15 total incl. year-rate variants) is not enough evidence for a full canonical endpoint (own analytics/modeling downstream), but is enough to warrant an explicitly *named* exclusion rather than an anonymous "no pattern matched." |
| **pCR** | NOT equivalent to ORR | **C — retain as distinct named subtype (excluded from ORR)** | pCR is assessed via post-surgical pathology after neoadjuvant therapy; ORR is assessed via RECIST imaging-based tumor shrinkage. Different methodology, different population (only neoadjuvant/surgical trials), different clinical meaning. Forcing into ORR would be scientifically wrong per your explicit instruction. 12 rows, one clear recurring phrasing family (tpCR/bpCR/"Total pCR ... AJCC Staging"). Worth a named exclusion. |
| **BOR** | Related to ORR, NOT equivalent | **C — retain as distinct named subtype (excluded from ORR)**, with a caveat | BOR is fundamentally a *categorical* per-subject classification (CR/PR/SD/PD/NE), not itself a numeric rate — 15 rows here all come from a single title/trial and (based on `parameter`/`unit`) likely represent a count-of-subjects-per-category breakdown, not a single "BOR rate." ORR is technically derivable as `(CR+PR)/(total)` from BOR data, but that requires cross-referencing `value`/`group` fields across multiple rows of the *same* outcome measure, which is a data-transformation task, not a title-classification task. Recommend: name BOR as an explicit exclusion now (Category C); a future *aggregation* feature (not a classifier change) could derive ORR from BOR data later if that's ever prioritized — out of scope here. |
| **TTR** | Distinct from both PFS (time to progression) and ORR (a rate) | **D — leave unclassified, do not add to taxonomy yet** | Only 1 row, 1 trial. Real and legitimate concept, but far too little evidence in this sample to justify taxonomy expansion. Revisit if it recurs in a larger dataset. |
| **Hematologic CRi (CR or CRi, NCCN)** | Related to ORR but NOT equivalent | **D — leave unclassified, do not merge into ORR** | Hematologic response criteria (used in leukemia/MDS trials) differ substantially from solid-tumor RECIST criteria; "CRi" (CR with incomplete count recovery) has no RECIST analog. Only 1 row in this sample — real, but not enough volume here to justify a dedicated hematologic-oncology endpoint family right now. This is a genuine scope question: **if Singularity Labs intends to cover hematologic malignancies as a first-class domain, this deserves its own endpoint family (D→B) later; if solid-tumor-focused for now, D is correct.** This is a scope decision for you, not something the data alone resolves. |
| **OR-by-modality (fragmented ORR)** | Conceptually IS "OR" (objective response), same family as ORR | **A/E hybrid — see discussion below, not a clean single answer** | These 18 rows are genuinely response-rate data (the word "OR" = Objective Response), but reported once per assessment-modality × biomarker-subgroup combination rather than once per trial arm. Two sub-questions: (1) should the *concept* map to ORR? Probably yes, eventually. (2) should the *classifier* auto-map it now? **Recommend: not yet.** The bare token "OR" is far too generic/risky to regex-match directly (an ordinary English word); a safe fix would need to anchor on the specific `"OR by <modality> Via mRECIST"` phrasing pattern, which is very study-specific wording, not a general ClinicalTrials.gov idiom the way "objective response rate" is. This is an **E (extraction/mapping design question)** more than a simple classifier bug: even if title-matched, whether 9 per-modality/subgroup rows should collapse into one ORR value or remain distinct fragments is a modeling decision outside `classify_outcome`'s scope. |
| **Local failure rate** | Distinct from PFS (local control vs. any-site progression) | **D — leave unclassified** | Radiotherapy-specific local-control endpoint. 6 rows, 1 trial. Not equivalent to PFS (a local recurrence trial can have local failure without meeting PFS's broader progression definition). Not enough volume to justify a new category. |
| **Biomarker/exploratory (H-Score, Ki67, PPV/NPV, genomic-testing reach)** | Not an efficacy/survival endpoint at all | **D — leave unclassified (correctly outside scope)** | These are correlative/exploratory biomarker measures, methodologically closer to the already-excluded PK/PD family than to PFS/OS/ORR/DOR/DFS. No taxonomy action needed — this is the classifier already working as intended, just not yet given an explicit named-exclusion pattern the way DCR/CBR/AE are. Could be added to the non-canonical exclusion list for clarity, but is low priority since it's already correctly unclassified. |
| **Tumor-size/imaging continuous change (SOLD, tumor volume)** | Related to, but distinct from, ORR | **D — leave unclassified** | A continuous measurement (percent change in lesion size/volume), not a categorical response-rate outcome. Different statistical type entirely from ORR's binary responder/non-responder rate. Correctly excluded already. |
| **Biopsy-completion feasibility** | Not an efficacy endpoint | **D — leave unclassified (correctly outside scope)** | Operational/feasibility measure for a biomarker-driven trial design, same family as the already-excluded dose-finding/feasibility category. |
| **Operational/cost/hematologic-support (LOS, cost, transfusion)** | Not an efficacy endpoint | **D — leave unclassified (correctly outside scope)** | Health-economics and supportive-care measures, unrelated to the PFS/OS/ORR/DOR/DFS taxonomy by definition. |
| **Complete or Partial Remission (leukemia-style)** | Related to ORR but NOT equivalent | **D — leave unclassified** | "Remission" terminology and criteria in leukemia trials differ from RECIST "response" terminology; only 2 rows, 1 trial. Same domain-scope question as hematologic CRi above — not enough volume to act on now. |
| **Generic "objective response" (no RECIST/CR+PR anchor)** | Ambiguous — could be ORR, could be something else | **D — leave unclassified** | `"Objective Response to First Line Therapy"` alone doesn't specify assessment criteria; too vague to safely classify given only 2 rows. Correctly conservative. |
| **Duration of Disease Control** | Related to DOR but broader (includes SD, not just CR/PR) | **D — leave unclassified** | DOR specifically requires a confirmed response (CR/PR); "disease control" also includes stable disease. Genuinely different population/definition. 1 row — not enough to act on. |

## 4. Direct answer to your question 4: should EFS, pCR, BOR, TTR, CRi become part of the core taxonomy?

**EFS and pCR: yes, as explicitly-named excluded/distinct subtypes (Category C), not as new canonical endpoints classifiers report on.** Both are real, recurring, well-defined oncology concepts that appear in real ClinicalTrials.gov data, and both are currently only "accidentally" correct (unclassified because no pattern matches, not because the system knows what they are and has decided to exclude them). Making them explicit:
- Improves auditability (a documented decision beats a silent non-match)
- Costs nothing in terms of new complexity — no new canonical endpoint category needs to exist, no new column, no new modeling assumptions
- Directly matches the existing pattern already used for DCR/CBR/TTP in `_NON_CANONICAL_PATTERNS`

**BOR: name it as an excluded subtype (Category C) for the same reason, but do NOT attempt to derive ORR from it yet.** That would require row-aggregation logic beyond `classify_outcome`'s per-row design.

**TTR and hematologic CRi: leave unclassified (Category D) for now.** Both are real concepts, but with only 1 row of evidence each in this dataset, adding them to the taxonomy would be optimizing for a sample size of one, which conflicts with your explicit instruction not to expand taxonomy without sufficient evidence. **CRi in particular raises a genuine scope question** (hematologic vs. solid-tumor oncology) that isn't a data question — it's a decision about what Singularity Labs is trying to cover, and belongs to you, not to pattern-counting.

**OR-by-modality: neither a clean addition nor a clean exclusion — flagged as needing a design decision (Category E), not a taxonomy decision per se.** The underlying concept (objective response) already exists (ORR); the question is whether/how to handle per-modality/subgroup fragmentation, which is an aggregation/schema question, not a "should this be canonical" question.

## 5. Recommended taxonomy architecture

**Current canonical endpoints (unchanged):** PFS, OS, ORR, DOR, DFS.

**Proposed additions to canonical endpoints:** **None.** No pattern in this 115-row remainder has enough volume or sufficiently unambiguous mapping to justify a new canonical endpoint category. This directly follows your instruction not to add categories merely to increase coverage.

**Proposed additions to the existing non-canonical/excluded-subtype list** (the same mechanism already used for DCR/CBR/TTP in `src/singularity/endpoints.py`'s `_NON_CANONICAL_PATTERNS`, and in `docs/data_dictionary.md`'s "Related Measures That Require Careful Handling" section):
- **EFS** (event-free survival, and its fixed-timepoint "event free at N years" variant)
- **pCR** (pathological complete response, incl. tpCR/bpCR variants)
- **BOR** (Best Overall Response — categorical, not a rate)

**Proposed exclusions (stay exactly as-is, no taxonomy action needed, just confirmed correct):** biomarker/exploratory measures, tumor-size continuous-change measures, biopsy-completion feasibility, operational/cost/hematologic-support measures, local failure rate, generic unanchored "objective response" phrasing, "complete or partial remission" (leukemia-style). All already correctly unclassified; no code change needed, just confirmation these should stay that way.

**Proposed subtype structure:** No change to the existing subtype mechanism (`ClassificationResult.subtype`) is needed. EFS/pCR/BOR would use the *same* mechanism DCR/CBR/TTP already use — matched by `_NON_CANONICAL_PATTERNS`, returned with `endpoint=None` and a `reason` explaining which related-but-distinct concept was detected. This is a documentation/pattern-list change, not an architectural change.

**Explicitly deferred, not decided here (need your input):**
- Hematologic CRi and "Complete or Partial Remission" — depends on whether hematologic malignancies are an intended scope for Singularity Labs.
- TTR — insufficient volume; revisit if it recurs in a larger dataset.
- OR-by-modality fragmentation — an aggregation/schema design question, not a taxonomy question; needs a decision on whether per-modality/subgroup response rates should ever collapse into a single ORR record, and if so, how.

## 6. What this analysis explicitly does NOT do

- Does not change `src/singularity/endpoints.py` or any other code.
- Does not claim the classifier is more "complete" — confidently-classified row count is unchanged by this document.
- Does not resolve the hematologic-oncology scope question, the OR-by-modality aggregation question, or the TTR/CRi volume question — these are flagged as needing your decision, not resolved by assumption.
