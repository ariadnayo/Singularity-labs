"""
Tests for singularity.pipeline (the ClinicalTrials.gov -> normalize ->
classify -> PostgreSQL ingestion orchestration layer).

Like tests/test_db_schema.py, these tests SKIP (not fail) if psycopg2
is not installed or no PostgreSQL instance is reachable -- see that
file's docstring for the rationale. A fresh, uniquely-named scratch
database is created per test and dropped afterward.

Network access is always mocked (a fake `http_get` injected into
ClinicalTrialsAdapter) -- these tests do NOT make real calls to
clinicaltrials.gov, and do NOT claim to. Real end-to-end verification
(real network + real DB) requires a human to run
scripts/run_clinicaltrials_ingestion.py from an environment with real
network access -- see that script and docs/autonomous_state.md
"Session 10 Summary" for exactly what is and isn't verified here.

All fixture study data is SYNTHETIC (NCT IDs in the 99999900s+ range,
invented sponsor/drug/condition names), matching this project's
established convention for keeping mock and real data unambiguous.
"""

import json
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

psycopg2 = pytest.importorskip("psycopg2", reason="psycopg2 not installed; install the 'db' extra to run pipeline tests")

from singularity.pipeline import run_clinicaltrials_ingestion
from singularity.sources.clinicaltrials import ClinicalTrialsAdapter

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "db" / "migrations"
ADMIN_DSN = os.environ.get("SINGULARITY_TEST_ADMIN_DSN", "postgresql://postgres:testpass@localhost:5432/postgres")


def _admin_connection():
    try:
        return psycopg2.connect(ADMIN_DSN)
    except Exception as e:  # pragma: no cover - environment-dependent
        pytest.skip(f"No reachable PostgreSQL instance at {ADMIN_DSN!r} ({e}); skipping pipeline tests.")


@pytest.fixture()
def test_db_connection():
    admin_conn = _admin_connection()
    admin_conn.autocommit = True
    db_name = f"singularity_pipeline_test_{uuid.uuid4().hex[:12]}"
    with admin_conn.cursor() as cur:
        cur.execute(f"CREATE DATABASE {db_name}")

    dsn = ADMIN_DSN.rsplit("/", 1)[0] + f"/{db_name}"
    conn = psycopg2.connect(dsn)
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        with conn.cursor() as cur:
            cur.execute(path.read_text())
    conn.commit()

    yield conn

    conn.close()
    with admin_conn.cursor() as cur:
        cur.execute(f"DROP DATABASE {db_name}")
    admin_conn.close()


def _mock_study(nct_id="NCT99999930", with_results=True) -> dict:
    """A hand-written MOCK study with both protocolSection and (if
    with_results) a resultsSection -- exercises the full Trial +
    OutcomeRecord extraction path in one fetch. Not real data."""
    study = {
        "protocolSection": {
            "identificationModule": {"nctId": nct_id, "briefTitle": "A Mock Pipeline Test Trial"},
            "statusModule": {"overallStatus": "COMPLETED"},
            "designModule": {"studyType": "INTERVENTIONAL", "phases": ["PHASE2"]},
            "sponsorCollaboratorsModule": {"leadSponsor": {"name": "Mock Pipeline Sponsor"}},
            "conditionsModule": {"conditions": ["Mock Pipeline Condition"]},
            "armsInterventionsModule": {"interventions": [{"type": "DRUG", "name": "Mock Pipeline Drug"}]},
        },
        "hasResults": with_results,
    }
    if with_results:
        study["resultsSection"] = {
            "outcomeMeasuresModule": {
                "outcomeMeasures": [
                    {
                        "title": "Median Overall Survival",
                        "paramType": "MEDIAN",
                        "unitOfMeasure": "months",
                        "timeFrame": "Up to 36 months",
                        "groups": [{"id": "OG000", "title": "Mock Drug Arm"}],
                        "classes": [{"categories": [{"measurements": [{"groupId": "OG000", "value": "24.5"}]}]}],
                    },
                    {
                        # No title -- exercises the "malformed record, reported not silently dropped" path.
                        "paramType": "NUMBER",
                        "unitOfMeasure": "percentage of participants",
                        "classes": [{"categories": [{"measurements": [{"groupId": "OG000", "value": "42"}]}]}],
                    },
                ]
            }
        }
    return study


def _mock_http_get_for_studies(studies):
    def fake_http_get(url: str) -> bytes:
        return json.dumps({"studies": studies, "nextPageToken": None}).encode()

    return fake_http_get


def test_end_to_end_ingestion_with_mock_transport_real_db(test_db_connection):
    adapter = ClinicalTrialsAdapter(http_get=_mock_http_get_for_studies([_mock_study()]), sleep=lambda s: None)
    report = run_clinicaltrials_ingestion(test_db_connection, adapter, query_cond="Mock Condition", max_pages=1)

    assert report.studies_fetched == 1
    assert report.trials_upserted == 1
    assert report.outcome_records_inserted == 1  # the titled measure only
    assert report.outcome_records_skipped_malformed == 1  # the titleless one
    assert report.classifications_inserted == 1
    assert report.failed_studies == []
    assert report.finished_at is not None

    with test_db_connection.cursor() as cur:
        cur.execute("SELECT brief_title, overall_status FROM trials WHERE nct_id = 'NCT99999930'")
        assert cur.fetchone() == ("A Mock Pipeline Test Trial", "COMPLETED")

        cur.execute("SELECT title, value FROM outcome_records WHERE nct_id = 'NCT99999930'")
        rows = cur.fetchall()
        assert rows == [("Median Overall Survival", 24.5)]

        cur.execute(
            "SELECT endpoint, subtype, confident FROM latest_endpoint_classifications lec "
            "JOIN outcome_records o ON o.id = lec.outcome_record_id WHERE o.nct_id = 'NCT99999930'"
        )
        assert cur.fetchone() == ("OS", "median_or_time_to_event", True)


def test_idempotent_rerun_does_not_duplicate_rows(test_db_connection):
    """Running the exact same ingestion twice must not double the row
    counts in trials or outcome_records -- see pipeline.py's module
    docstring for the delete-then-insert-per-trial design this relies
    on."""
    adapter = ClinicalTrialsAdapter(http_get=_mock_http_get_for_studies([_mock_study()]), sleep=lambda s: None)

    run_clinicaltrials_ingestion(test_db_connection, adapter, query_cond="Mock Condition", max_pages=1)
    run_clinicaltrials_ingestion(test_db_connection, adapter, query_cond="Mock Condition", max_pages=1)

    with test_db_connection.cursor() as cur:
        cur.execute("SELECT count(*) FROM trials WHERE nct_id = 'NCT99999930'")
        assert cur.fetchone()[0] == 1

        cur.execute("SELECT count(*) FROM outcome_records WHERE nct_id = 'NCT99999930'")
        assert cur.fetchone()[0] == 1  # not 2

        cur.execute(
            "SELECT count(*) FROM endpoint_classifications ec "
            "JOIN outcome_records o ON o.id = ec.outcome_record_id WHERE o.nct_id = 'NCT99999930'"
        )
        assert cur.fetchone()[0] == 1  # old classification cascade-deleted with its outcome_record, not accumulated


def test_idempotent_rerun_with_changed_data(test_db_connection):
    """A genuine re-run scenario: the source data changes between runs
    (e.g. a trial's status updates). The idempotent design must
    reflect the NEW data, not just avoid duplicating the old data."""
    adapter1 = ClinicalTrialsAdapter(http_get=_mock_http_get_for_studies([_mock_study()]), sleep=lambda s: None)
    run_clinicaltrials_ingestion(test_db_connection, adapter1, query_cond="Mock Condition", max_pages=1)

    updated_study = _mock_study()
    updated_study["protocolSection"]["statusModule"]["overallStatus"] = "TERMINATED"
    adapter2 = ClinicalTrialsAdapter(http_get=_mock_http_get_for_studies([updated_study]), sleep=lambda s: None)
    run_clinicaltrials_ingestion(test_db_connection, adapter2, query_cond="Mock Condition", max_pages=1)

    with test_db_connection.cursor() as cur:
        cur.execute("SELECT overall_status FROM trials WHERE nct_id = 'NCT99999930'")
        assert cur.fetchone()[0] == "TERMINATED"


def test_partial_failure_one_malformed_study_does_not_abort_batch(test_db_connection):
    """A batch of 3 studies where the middle one has a realistic
    malformed shape (a null where a list was expected in the raw JSON
    -- causes a TypeError during extraction) must still successfully
    ingest the other 2, and report the failure clearly rather than
    crashing the whole run."""
    good_study_1 = _mock_study(nct_id="NCT99999931")
    good_study_2 = _mock_study(nct_id="NCT99999933")

    malformed_study = _mock_study(nct_id="NCT99999932")
    # Realistic malformed-upstream-data scenario: "classes" is null
    # instead of a list. `.get("classes", [])` returns None here (the
    # key IS present, just null), so `for cls in None` raises
    # TypeError during extraction -- exactly the kind of real-world
    # malformed API response this pipeline must survive.
    malformed_study["resultsSection"]["outcomeMeasuresModule"]["outcomeMeasures"][0]["classes"] = None

    studies = [good_study_1, malformed_study, good_study_2]
    adapter = ClinicalTrialsAdapter(http_get=_mock_http_get_for_studies(studies), sleep=lambda s: None)
    report = run_clinicaltrials_ingestion(test_db_connection, adapter, query_cond="Mock Condition", max_pages=1)

    assert report.studies_fetched == 3
    assert report.trials_upserted == 2  # the malformed one failed, not counted
    assert len(report.failed_studies) == 1
    assert report.failed_studies[0]["nct_id"] == "NCT99999932"
    assert "TypeError" in report.failed_studies[0]["error"]

    with test_db_connection.cursor() as cur:
        cur.execute("SELECT nct_id FROM trials ORDER BY nct_id")
        assert [r[0] for r in cur.fetchall()] == ["NCT99999931", "NCT99999933"]
        # The malformed study's trial must NOT have been partially
        # committed either (rollback confirmed, not just "outcome
        # records missing").
        cur.execute("SELECT count(*) FROM trials WHERE nct_id = 'NCT99999932'")
        assert cur.fetchone()[0] == 0


def test_provenance_survives_the_full_pipeline(test_db_connection):
    adapter = ClinicalTrialsAdapter(http_get=_mock_http_get_for_studies([_mock_study()]), sleep=lambda s: None)
    run_clinicaltrials_ingestion(
        test_db_connection, adapter, query_cond="Mock Provenance Condition",
        filter_advanced="AREA[HasResults]true", max_pages=1,
    )

    with test_db_connection.cursor() as cur:
        cur.execute(
            "SELECT provenance_source, provenance_query_params FROM trials WHERE nct_id = 'NCT99999930'"
        )
        source, params = cur.fetchone()
        assert source == "clinicaltrials.gov"
        assert params["query.cond"] == "Mock Provenance Condition"
        assert params["filter.advanced"] == "AREA[HasResults]true"

        cur.execute(
            "SELECT provenance_source, provenance_raw FROM outcome_records WHERE nct_id = 'NCT99999930'"
        )
        source, raw = cur.fetchone()
        assert source == "clinicaltrials.gov"
        assert "outcome_measure" in raw


def test_observed_and_derived_data_remain_in_separate_tables(test_db_connection):
    """outcome_records must contain no classifier output columns at
    all -- the separation is structural, not just a convention."""
    with test_db_connection.cursor() as cur:
        cur.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'outcome_records'"
        )
        outcome_columns = {row[0] for row in cur.fetchall()}
    assert "endpoint" not in outcome_columns
    assert "subtype" not in outcome_columns
    assert "confident" not in outcome_columns
    assert "classifier_version" not in outcome_columns

    adapter = ClinicalTrialsAdapter(http_get=_mock_http_get_for_studies([_mock_study()]), sleep=lambda s: None)
    run_clinicaltrials_ingestion(test_db_connection, adapter, query_cond="Mock Condition", max_pages=1)

    with test_db_connection.cursor() as cur:
        cur.execute(
            "SELECT classifier_version FROM endpoint_classifications ec "
            "JOIN outcome_records o ON o.id = ec.outcome_record_id WHERE o.nct_id = 'NCT99999930'"
        )
        version = cur.fetchone()[0]
    from singularity.endpoints import CLASSIFIER_VERSION

    assert version == CLASSIFIER_VERSION


def test_report_to_markdown_includes_failed_study():
    from singularity.pipeline import IngestionReport

    report = IngestionReport(query_params={"query_cond": "Mock"}, started_at="2026-01-01T00:00:00Z")
    report.finished_at = "2026-01-01T00:01:00Z"
    report.studies_fetched = 2
    report.trials_upserted = 1
    report.failed_studies.append({"nct_id": "NCT00000001", "error": "TypeError: boom"})
    md = report.to_markdown()
    assert "NCT00000001" in md
    assert "TypeError: boom" in md
