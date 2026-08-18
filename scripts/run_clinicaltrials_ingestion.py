#!/usr/bin/env python3
"""
Real end-to-end ingestion script: ClinicalTrials.gov -> normalize ->
classify -> PostgreSQL, using REAL network access and a REAL database.

WHY THIS SCRIPT EXISTS
-----------------------
This repo's development sandbox cannot reach clinicaltrials.gov over
the network (confirmed repeatedly across sessions -- see
docs/autonomous_state.md). All of tests/test_pipeline.py therefore
uses a mocked HTTP transport against a real local PostgreSQL instance
-- real database, mocked network. This script is the other half: real
network, and a real database you point it at. Run it yourself from an
environment with actual internet access to clinicaltrials.gov.

This script makes REAL network requests and REAL database writes. It
will fail with a clear network or database error if either isn't
reachable -- it must NOT be modified to fall back to mock/synthetic
data on failure. That would defeat its entire purpose.

USAGE
-----
    export SINGULARITY_DATABASE_URL="postgresql://user:pass@host:5432/singularity_labs"
    # First, create the database and run migrations if you haven't:
    #   createdb singularity_labs
    #   for f in db/migrations/*.sql; do psql -d singularity_labs -f "$f"; done

    python3 scripts/run_clinicaltrials_ingestion.py \
        --condition "non-small cell lung cancer" \
        --status COMPLETED \
        --has-results \
        --page-size 10 \
        --max-pages 1

Only the standard library plus psycopg2 (install the 'db' extra:
`pip install -e ".[db]"`) are required.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from singularity.db import get_connection  # noqa: E402
from singularity.pipeline import run_clinicaltrials_ingestion  # noqa: E402
from singularity.sources.clinicaltrials import ClinicalTrialsAdapter  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--condition", default="cancer", help="query.cond value. Default: 'cancer'.")
    parser.add_argument("--status", action="append", default=None, help="filter.overallStatus. May repeat. Default: COMPLETED.")
    parser.add_argument(
        "--has-results", action="store_true",
        help="Restrict to studies with posted results (AREA[HasResults]true). Recommended -- "
        "without it, most fetched studies will have no outcome data at all.",
    )
    parser.add_argument("--page-size", type=int, default=10)
    parser.add_argument("--max-pages", type=int, default=1, help="Keep this small for a first real run.")
    parser.add_argument(
        "--database-url", default=None,
        help="Postgres DSN. Defaults to the SINGULARITY_DATABASE_URL environment variable.",
    )
    args = parser.parse_args()

    statuses = args.status or ["COMPLETED"]
    filter_advanced = "AREA[HasResults]true" if args.has_results else None

    print("Connecting to database...")
    conn = get_connection(args.database_url)  # raises loudly if unreachable/misconfigured -- no fallback

    print(
        f"Running REAL ingestion (condition={args.condition!r}, status={statuses}, "
        f"has_results_filter={args.has_results}, page_size={args.page_size}, max_pages={args.max_pages})...\n"
        f"This makes real HTTPS requests to clinicaltrials.gov and real writes to your database."
    )
    adapter = ClinicalTrialsAdapter()  # real HTTP transport, default
    report = run_clinicaltrials_ingestion(
        conn,
        adapter,
        query_cond=args.condition,
        filter_overall_status=statuses,
        filter_advanced=filter_advanced,
        page_size=args.page_size,
        max_pages=args.max_pages,
    )
    conn.close()

    print("\n" + report.to_markdown())
    print(
        "\nNEXT STEP (not automated -- do this yourself): manually spot-check a handful of "
        "the ingested trials/outcome_records against their real ClinicalTrials.gov pages, "
        "the same way session 4/6's real-title validation did. Report findings back or "
        "update docs/autonomous_state.md directly."
    )
    return 1 if report.failed_studies else 0


if __name__ == "__main__":
    raise SystemExit(main())
