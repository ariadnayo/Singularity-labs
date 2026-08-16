# Real ClinicalTrials.gov results run — provided by human, 2026-08-14

## Provenance

This dataset was produced by the human running the real-results
extraction themselves, externally, in Google Colab (an environment
with real network access to clinicaltrials.gov, unlike the
code-execution sandbox used in this repo's autonomous sessions -- see
docs/autonomous_state.md "Session 5 Summary" for why that sandbox
could not do this itself).

The human attached `records.csv` and `audit_report.md` directly to the
conversation on 2026-08-14. Both files are copied here verbatim (no
edits) as the authoritative real dataset used for session 6's
classifier fix analysis and re-validation.

## Verified contents (do not trust summary claims without checking the files)

A data-integrity discrepancy was found and disclosed before analysis
began: the counts initially described in conversation (1,135 records /
926 flagged) did NOT match the attached files. Verified directly from
the files themselves:

- 20 completed studies, 20/20 with `hasResults=true`
- **3,552** real OutcomeRecords (not 1,135)
- **3,497** rows flagged for manual review (not 926)
- `audit_report.md` confirms: `Total: 3552`, `Classified: 65`,
  `Unclassified: 3487`, `Low-confidence: 10` (3487+10=3497, matching
  the 3497 individually-listed flagged rows in the file).

All analysis and fix validation in `docs/autonomous_state.md` "Session
6 Summary" uses these verified numbers, not the originally-stated ones.

## What extraction path this validates

This dataset was produced by running real extraction end-to-end in an
environment with real network access (the human's Colab session), so
it DOES validate `extract_outcome_records()`'s real-world behavior on
posted results. It does NOT independently re-verify that code running
inside this specific sandboxed repo environment, since this sandbox
still cannot reach clinicaltrials.gov itself (see
`scripts/validate_real_clinicaltrials_data.py` and session 5's notes).
