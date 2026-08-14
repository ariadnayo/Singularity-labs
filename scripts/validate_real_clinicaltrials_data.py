#!/usr/bin/env python3
"""
Real-results validation script for the ClinicalTrials.gov adapter.

WHY THIS SCRIPT EXISTS
-----------------------
This repo's development sandbox cannot reach clinicaltrials.gov over
the network -- confirmed this session by three independent, exhausted
attempts (see docs/autonomous_state.md, "Session 5"):
  1. Direct API queries with different parameters were silently served
     a cached response from an earlier, unrelated query, regardless of
     what parameters were actually sent.
  2. The single-study API endpoint was rejected outright as an
     unreachable/unseen URL.
  3. The human-readable study page returned an empty JS-application
     shell with no data (it fetches data client-side after load, which
     the available fetch tool cannot execute).

None of that is a substitute for real validation, so none of it was
used to fabricate or approximate real resultsSection data. This script
is the reproducible alternative: run it yourself, from an environment
with real network access to clinicaltrials.gov, and it will do exactly
what direct interactive validation would have done.

WHAT THIS SCRIPT DOES
----------------------
1. Fetches a SMALL, CONTROLLED sample of real studies that have
   POSTED RESULTS (hasResults=true), using the real
   ClinicalTrialsAdapter (src/singularity/sources/clinicaltrials.py)
   -- no mocking, no synthetic data, no fallback dataset.
2. Saves the raw JSON for every fetched study, verbatim, to
   data/clinicaltrials_raw/real_results_run_<timestamp>/ -- separately
   from the normalized/classified output.
3. Extracts OutcomeRecords (title, parameter, unit, timeframe, group,
   value) via the adapter's real resultsSection-parsing logic, with
   full Provenance attached to every record.
4. Saves the normalized records to
   data/clinicaltrials_normalized/real_results_run_<timestamp>/records.csv
5. Runs the existing classifier (singularity.endpoints.classify_batch)
   against the real records.
6. Generates an audit report (counts, unclassified rows, low-
   confidence/ambiguous classifications) as both a .json summary and a
   human-readable .md report.
7. Prints a clear "SPOT-CHECK THESE" list of every unclassified or
   low-confidence row, with its source NCT ID, so a human can manually
   verify them against the real study page -- this script does NOT
   claim classification correctness on its own; per Claude.md section
   9, that requires the human spot-check step this script sets up but
   does not itself perform.

USAGE
-----
    python3 scripts/validate_real_clinicaltrials_data.py \\
        --condition "non-small cell lung cancer" \\
        --status COMPLETED \\
        --page-size 10 \\
        --max-pages 1

Only the standard library is required (this reuses
src/singularity/sources/clinicaltrials.py, which uses urllib, not
requests). Run from the repo root so the `src` import below resolves.

This script makes REAL network requests to clinicaltrials.gov. Do not
run it somewhere without real internet access -- it will simply fail
with a clear network error, which is correct and expected; it must
NOT be modified to fall back to mock or synthetic data on failure.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from singularity.endpoints import classify_batch, summarize  # noqa: E402
from singularity.sources.clinicaltrials import (  # noqa: E402
    ClinicalTrialsAdapter,
    iter_all_studies,
)


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--condition",
        default="cancer",
        help="query.cond value, e.g. 'non-small cell lung cancer'. Default: 'cancer' (broad oncology sample).",
    )
    parser.add_argument(
        "--status",
        action="append",
        default=None,
        help="filter.overallStatus value(s), e.g. COMPLETED. May be repeated. Default: COMPLETED only "
        "(completed trials are far more likely to have posted results).",
    )
    parser.add_argument("--page-size", type=int, default=10, help="Studies per page. Default: 10 (small, controlled).")
    parser.add_argument(
        "--max-pages", type=int, default=2, help="Max pages to fetch. Default: 2 (keeps the sample small and controlled)."
    )
    parser.add_argument(
        "--no-has-results-filter",
        action="store_true",
        help="Skip the AREA[HasResults]true advanced filter (not recommended -- most studies without it "
        "will have no resultsSection at all, producing zero OutcomeRecords).",
    )
    args = parser.parse_args()

    statuses = args.status or ["COMPLETED"]
    filter_advanced = None if args.no_has_results_filter else "AREA[HasResults]true"

    run_id = _timestamp()
    raw_dir = REPO_ROOT / "data" / "clinicaltrials_raw" / f"real_results_run_{run_id}"
    norm_dir = REPO_ROOT / "data" / "clinicaltrials_normalized" / f"real_results_run_{run_id}"
    raw_dir.mkdir(parents=True, exist_ok=True)
    norm_dir.mkdir(parents=True, exist_ok=True)

    print(f"[1/6] Fetching real studies (condition={args.condition!r}, status={statuses}, "
          f"filter_advanced={filter_advanced!r}, page_size={args.page_size}, max_pages={args.max_pages})...")

    studies = list(
        iter_all_studies(
            query_cond=args.condition,
            filter_overall_status=statuses,
            filter_advanced=filter_advanced,
            page_size=args.page_size,
            max_pages=args.max_pages,
        )
    )
    print(f"      Fetched {len(studies)} real studies.")

    if not studies:
        print("      No studies returned. This is a REAL result, not an error -- do not substitute mock "
              "data. Try a broader --condition or drop --no-has-results-filter's opposite (i.e. make sure "
              "it's not set) and re-run.")
        return 0

    # [2/6] Save raw JSON, verbatim, one file per study, separate from normalized output.
    print(f"[2/6] Saving raw JSON to {raw_dir}...")
    has_results_count = 0
    for study in studies:
        nct_id = study.get("protocolSection", {}).get("identificationModule", {}).get("nctId", "UNKNOWN")
        if study.get("hasResults"):
            has_results_count += 1
        with (raw_dir / f"{nct_id}.json").open("w") as f:
            json.dump(study, f, indent=2)
    print(f"      {has_results_count}/{len(studies)} fetched studies have hasResults=true.")

    # [3/6] Extract OutcomeRecords via the real adapter logic (not reimplemented here).
    print("[3/6] Extracting OutcomeRecords from resultsSection...")
    from singularity.sources.clinicaltrials import extract_outcome_records

    records = []
    for study in studies:
        records.extend(extract_outcome_records(study))
    print(f"      Extracted {len(records)} real OutcomeRecords "
          f"(0 is expected and correct if none of the fetched studies had posted results).")

    # [4/6] Save normalized records, separately from raw.
    print(f"[4/6] Saving normalized records to {norm_dir / 'records.csv'}...")
    with (norm_dir / "records.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["nct_id", "title", "parameter", "unit", "timeframe", "group", "value",
                    "provenance_source", "provenance_retrieved_at", "provenance_request_url"])
        for r in records:
            w.writerow([
                r.nct_id, r.title, r.parameter or "", r.unit or "", r.timeframe or "", r.group or "",
                r.value if r.value is not None else "",
                r.provenance.source if r.provenance else "",
                r.provenance.retrieved_at if r.provenance else "",
                r.provenance.request_url if r.provenance else "",
            ])

    if not records:
        print("      No OutcomeRecords to classify. Stopping here -- this is an honest empty result, "
              "not a failure. Re-run with a broader --condition, more --max-pages, or without "
              "--no-has-results-filter's inverse to find studies with resultsSection data.")
        return 0

    # [5/6] Classify.
    print("[5/6] Running classifier...")
    results = classify_batch(records)
    summary = summarize(results)

    # [6/6] Audit report + ambiguous/failed classification list.
    print("[6/6] Writing audit report...")
    ambiguous = [
        (r, res) for r, res in zip(records, results)
        if res.endpoint is None or not res.confident
    ]

    with (norm_dir / "audit_summary.json").open("w") as f:
        json.dump(summary, f, indent=2)

    md_lines = [
        f"# Real ClinicalTrials.gov Results Audit — run {run_id}",
        "",
        f"Condition: `{args.condition}` | Status filter: `{statuses}` | "
        f"HasResults filter: `{filter_advanced}`",
        f"Studies fetched: {len(studies)} ({has_results_count} with hasResults=true)",
        f"OutcomeRecords extracted: {len(records)}",
        "",
        "## Classification Summary",
        f"- Total: {summary['total_rows']}",
        f"- Classified: {summary['classified_rows']}",
        f"- Unclassified: {summary['unclassified_rows']}",
        f"- By endpoint: {summary['counts_by_endpoint']}",
        f"- Low-confidence (subtype-flagged): {summary['low_confidence_classifications']}",
        "",
        "## Rows Requiring Manual Spot-Check (unclassified OR low-confidence)",
        "**This script does not itself validate correctness.** Per Claude.md",
        "section 9, a human must check each row below against the real",
        "ClinicalTrials.gov study page for that NCT ID before these",
        "classifications are trusted.",
        "",
    ]
    for r, res in ambiguous:
        md_lines.append(
            f"- `{r.nct_id}` — \"{r.title}\" — endpoint={res.endpoint!r} "
            f"subtype={res.subtype!r} confident={res.confident} — reason: {res.reason}"
        )
    (norm_dir / "audit_report.md").write_text("\n".join(md_lines))

    print(f"\nDone. {len(ambiguous)} rows flagged for manual spot-check -- see {norm_dir / 'audit_report.md'}")
    print(f"Raw JSON: {raw_dir}")
    print(f"Normalized data + audit: {norm_dir}")
    print("\nNEXT STEP (not automated -- do this yourself):")
    print("  Manually check each flagged row against clinicaltrials.gov/study/<NCT_ID>,")
    print("  update docs/autonomous_state.md with what you find (correct classifications,")
    print("  errors found, any new failure modes), and add regression tests for anything")
    print("  wrong, the same way session 4's real-title validation did.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
