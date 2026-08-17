"""
Tests for the PostgreSQL schema in db/migrations/.

These tests are SKIPPED (not failed) if either:
  - psycopg2 is not installed (install the optional 'db' extra:
    pip install -e ".[db]"), or
  - a real PostgreSQL instance is not reachable at the connection
    settings below (override via SINGULARITY_TEST_DATABASE_URL, e.g.
    "postgresql://user:pass@host:5432/postgres").

This is deliberate: the rest of this project's test suite must keep
passing in any environment (including this sandbox, which has no
persistent database), so DB tests degrade to "skipped" rather than
"failed" when no real database is reachable -- this is not the same
as being untested. The schema in db/migrations/ WAS verified against a
real local PostgreSQL 16 instance during development (2026-08-14,
session 9): all three migrations ran cleanly, real Trial/OutcomeRecord/
ClassificationResult objects round-tripped correctly, and the foreign-
key and CHECK constraints were confirmed to actually reject bad data.
See docs/autonomous_state.md "Session 9 Summary" for that verification
run. This test file makes that verification reproducible and automated
rather than a one-off manual check.

A fresh, uniquely-named database is created for each test run and
dropped afterward -- this never touches a real application database.
"""

import json
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

psycopg2 = pytest.importorskip("psycopg2", reason="psycopg2 not installed; install the 'db' extra to run DB schema tests")

from singularity.endpoints import CLASSIFIER_VERSION, classify_outcome
from singularity.schema import OutcomeRecord, Provenance, Trial

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "db" / "migrations"

ADMIN_DSN = os.environ.get(
    "SINGULARITY_TEST_ADMIN_DSN", "postgresql://postgres:testpass@localhost:5432/postgres"
)


def _admin_connection():
    try:
        return psycopg2.connect(ADMIN_DSN)
    except Exception as e:  # pragma: no cover - environment-dependent
        pytest.skip(f"No reachable PostgreSQL instance at {ADMIN_DSN!r} ({e}); skipping DB schema tests.")


@pytest.fixture()
def test_db_connection():
    """Create a uniquely-named scratch database, run all migrations
    against it, yield a connection, then drop the database."""
    admin_conn = _admin_connection()
    admin_conn.autocommit = True
    db_name = f"singularity_test_{uuid.uuid4().hex[:12]}"
    with admin_conn.cursor() as cur:
        cur.execute(f"CREATE DATABASE {db_name}")

    dsn = ADMIN_DSN.rsplit("/", 1)[0] + f"/{db_name}"
    conn = psycopg2.connect(dsn)
    migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    assert migration_files, "no migration files found in db/migrations/"
    with conn.cursor() as cur:
        for path in migration_files:
            cur.execute(path.read_text())
    conn.commit()

    yield conn

    conn.close()
    with admin_conn.cursor() as cur:
        cur.execute(f"DROP DATABASE {db_name}")
    admin_conn.close()


def test_migrations_run_cleanly(test_db_connection):
    """All three migrations applied without error (the fixture itself
    would have raised if not) -- this test exists to give that a
    dedicated, readable pass/fail entry in test output."""
    with test_db_connection.cursor() as cur:
        cur.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name"
        )
        tables = {row[0] for row in cur.fetchall()}
    assert {"trials", "outcome_records", "endpoint_classifications"} <= tables


def test_trial_round_trips_through_real_schema(test_db_connection):
    prov = Provenance(
        source="clinicaltrials.gov",
        source_record_id="NCT99999920",
        retrieved_at="2026-08-14T00:00:00Z",
        request_url="https://clinicaltrials.gov/api/v2/studies?mock=1",
        query_params={"query.cond": "Mock Condition"},
        raw={"mock": True},
    )
    trial = Trial(
        nct_id="NCT99999920",
        brief_title="Mock Roundtrip Trial",
        overall_status="RECRUITING",
        phases=["PHASE2"],
        study_type="INTERVENTIONAL",
        conditions=["Mock Condition"],
        lead_sponsor="Mock Sponsor",
        interventions=["Mock Drug"],
        start_date="2025-01-01",
        enrollment_count=100,
        provenance=prov,
    )
    with test_db_connection.cursor() as cur:
        cur.execute(
            """
            INSERT INTO trials (nct_id, brief_title, official_title, overall_status, phases,
                study_type, conditions, lead_sponsor, interventions, start_date, completion_date,
                enrollment_count, provenance_source, provenance_source_record_id,
                provenance_retrieved_at, provenance_request_url, provenance_query_params, provenance_raw)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                trial.nct_id, trial.brief_title, trial.official_title, trial.overall_status, trial.phases,
                trial.study_type, trial.conditions, trial.lead_sponsor, trial.interventions, trial.start_date,
                trial.completion_date, trial.enrollment_count, prov.source, prov.source_record_id,
                prov.retrieved_at, prov.request_url, json.dumps(prov.query_params), json.dumps(prov.raw),
            ),
        )
        test_db_connection.commit()
        cur.execute(
            "SELECT nct_id, brief_title, phases, conditions, enrollment_count FROM trials WHERE nct_id = %s",
            (trial.nct_id,),
        )
        row = cur.fetchone()
    assert row == (trial.nct_id, trial.brief_title, trial.phases, trial.conditions, trial.enrollment_count)


def test_outcome_record_and_classification_round_trip_via_latest_view(test_db_connection):
    prov = Provenance(
        source="clinicaltrials.gov", source_record_id="NCT99999921",
        retrieved_at="2026-08-14T00:00:00Z",
        request_url="https://clinicaltrials.gov/api/v2/studies?mock=1",
        query_params={}, raw=None,
    )
    with test_db_connection.cursor() as cur:
        cur.execute(
            """
            INSERT INTO trials (nct_id, provenance_source, provenance_source_record_id,
                provenance_retrieved_at, provenance_request_url)
            VALUES (%s,%s,%s,%s,%s)
            """,
            ("NCT99999921", prov.source, prov.source_record_id, prov.retrieved_at, prov.request_url),
        )

        rec = OutcomeRecord(
            nct_id="NCT99999921", title="Median Overall Survival", parameter="MEDIAN",
            unit="months", timeframe="Up to 36 months", group="Mock Drug Arm", value=24.5, provenance=prov,
        )
        cur.execute(
            """
            INSERT INTO outcome_records (nct_id, title, parameter, unit, timeframe, group_name, value,
                provenance_source, provenance_source_record_id, provenance_retrieved_at,
                provenance_request_url, provenance_query_params, provenance_raw)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id
            """,
            (
                rec.nct_id, rec.title, rec.parameter, rec.unit, rec.timeframe, rec.group, rec.value,
                prov.source, prov.source_record_id, prov.retrieved_at, prov.request_url,
                json.dumps(prov.query_params), json.dumps(prov.raw),
            ),
        )
        outcome_id = cur.fetchone()[0]

        result = classify_outcome(rec)
        cur.execute(
            """
            INSERT INTO endpoint_classifications
                (outcome_record_id, endpoint, subtype, confident, reason, classifier_version)
            VALUES (%s,%s,%s,%s,%s,%s)
            """,
            (outcome_id, result.endpoint, result.subtype, result.confident, result.reason, CLASSIFIER_VERSION),
        )
        test_db_connection.commit()

        cur.execute("SELECT title, value, group_name FROM outcome_records WHERE id = %s", (outcome_id,))
        outcome_row = cur.fetchone()
        cur.execute(
            "SELECT endpoint, subtype, confident, classifier_version FROM latest_endpoint_classifications "
            "WHERE outcome_record_id = %s",
            (outcome_id,),
        )
        class_row = cur.fetchone()

    assert outcome_row == (rec.title, rec.value, rec.group)
    assert class_row == (result.endpoint, result.subtype, result.confident, CLASSIFIER_VERSION)
    # This specific real title should classify as confident median OS.
    assert result.endpoint == "OS"
    assert result.confident is True


def test_foreign_key_rejects_outcome_record_for_unknown_trial(test_db_connection):
    with test_db_connection.cursor() as cur:
        with pytest.raises(psycopg2.errors.ForeignKeyViolation):
            cur.execute(
                """
                INSERT INTO outcome_records (nct_id, title, provenance_source,
                    provenance_source_record_id, provenance_retrieved_at, provenance_request_url)
                VALUES ('NCT00000000', 'x', 'clinicaltrials.gov', 'x', '2026-01-01T00:00:00Z', 'http://x')
                """
            )
    test_db_connection.rollback()


def test_check_constraint_rejects_non_canonical_endpoint_value(test_db_connection):
    with test_db_connection.cursor() as cur:
        cur.execute(
            """
            INSERT INTO trials (nct_id, provenance_source, provenance_source_record_id,
                provenance_retrieved_at, provenance_request_url)
            VALUES ('NCT99999922','clinicaltrials.gov','x','2026-01-01T00:00:00Z','http://x')
            """
        )
        cur.execute(
            """
            INSERT INTO outcome_records (nct_id, title, provenance_source,
                provenance_source_record_id, provenance_retrieved_at, provenance_request_url)
            VALUES ('NCT99999922','x','clinicaltrials.gov','x','2026-01-01T00:00:00Z','http://x')
            RETURNING id
            """
        )
        outcome_id = cur.fetchone()[0]
        test_db_connection.commit()

        with pytest.raises(psycopg2.errors.CheckViolation):
            cur.execute(
                """
                INSERT INTO endpoint_classifications (outcome_record_id, endpoint, confident, reason, classifier_version)
                VALUES (%s, 'NOT_A_REAL_ENDPOINT', true, 'test', 'x')
                """,
                (outcome_id,),
            )
    test_db_connection.rollback()


def test_duplicate_outcome_records_are_not_rejected():
    """Real ClinicalTrials.gov data contains genuine duplicate rows
    (confirmed in earlier sessions' real-data validation). The schema
    must not enforce artificial uniqueness that would silently drop
    them -- see the surrogate-key comment in
    db/migrations/0002_create_outcome_records.sql."""
    # This is a design assertion, not a DB round-trip -- verified by
    # inspecting the migration: outcome_records has no UNIQUE
    # constraint over (nct_id, title, group_name, timeframe, ...).
    sql_lines = (Path(__file__).resolve().parents[1] / "db" / "migrations" / "0002_create_outcome_records.sql").read_text().splitlines()
    sql_no_comments = "\n".join(line for line in sql_lines if not line.strip().startswith("--"))
    assert "UNIQUE" not in sql_no_comments.upper()
