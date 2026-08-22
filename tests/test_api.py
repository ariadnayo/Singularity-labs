"""
Integration tests for singularity.api.main (the FastAPI read layer).

Like tests/test_db_schema.py and tests/test_pipeline.py, the DB-backed
tests here SKIP (not fail) if psycopg2/fastapi/httpx aren't installed
or no PostgreSQL instance is reachable. A fresh, uniquely-named scratch
database is created per test and dropped afterward.

Data is seeded via the EXISTING, already-tested singularity.db write
functions (upsert_trial, replace_outcome_records_for_trial,
insert_classifications) -- not hand-written SQL -- so these tests
exercise the real read-after-write path end-to-end, using real
Trial/OutcomeRecord/ClassificationResult dataclass instances built from
real ClinicalTrials.gov titles/values from the session-11 validation
dataset (synthetic NCT IDs, to keep mock and real data unambiguous per
this project's convention).

The OpenAPI smoke test does not require a database.
"""

import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

fastapi_testclient = pytest.importorskip("fastapi.testclient", reason="fastapi not installed; install the 'api' extra")
psycopg2 = pytest.importorskip("psycopg2", reason="psycopg2 not installed; install the 'db' extra")

from singularity import db as _db
from singularity.api.main import app, get_db_connection
from singularity.endpoints import CLASSIFIER_VERSION, classify_outcome
from singularity.schema import OutcomeRecord, Provenance, Trial

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "db" / "migrations"
ADMIN_DSN = os.environ.get("SINGULARITY_TEST_ADMIN_DSN", "postgresql://postgres:testpass@localhost:5432/postgres")


def _admin_connection():
    try:
        return psycopg2.connect(ADMIN_DSN)
    except Exception as e:  # pragma: no cover - environment-dependent
        pytest.skip(f"No reachable PostgreSQL instance at {ADMIN_DSN!r} ({e}); skipping API tests.")


@pytest.fixture()
def test_db_connection():
    admin_conn = _admin_connection()
    admin_conn.autocommit = True
    db_name = f"singularity_api_test_{uuid.uuid4().hex[:12]}"
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


@pytest.fixture()
def client(test_db_connection):
    """A TestClient with the DB dependency overridden to use the real
    scratch database from test_db_connection, instead of reading
    SINGULARITY_DATABASE_URL."""
    app.dependency_overrides[get_db_connection] = lambda: (yield test_db_connection)
    with fastapi_testclient.TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _seed_real_shaped_trial(conn, nct_id="NCT88888801"):
    """Seed one trial with two outcome records: a real ORR title with
    parameter=COUNT_OF_PARTICIPANTS (the exact count-vs-rate case from
    session 11's NCT02360579), and a real median-OS title. Uses the
    actual dataclasses and db write functions -- not raw SQL."""
    prov = Provenance(
        source="clinicaltrials.gov", source_record_id=nct_id,
        retrieved_at="2026-08-14T00:00:00Z",
        request_url="https://clinicaltrials.gov/api/v2/studies?mock=1",
        query_params={"query.cond": "Mock Melanoma"}, raw=None,
    )
    trial = Trial(
        nct_id=nct_id, brief_title="Mock Study of a Fictitious Drug in Metastatic Melanoma",
        overall_status="COMPLETED", phases=["PHASE2"], study_type="INTERVENTIONAL",
        conditions=["Metastatic Melanoma"], lead_sponsor="Mock Biotherapeutics, Inc.",
        interventions=["Mock Drug"], provenance=prov,
    )
    _db.upsert_trial(conn, trial)

    records = [
        OutcomeRecord(
            nct_id=nct_id, title="Disease Assessment for Objective Response Rate",
            parameter="COUNT_OF_PARTICIPANTS", unit="Participants", group="Cohort 2",
            value=23.0, provenance=prov,
        ),
        OutcomeRecord(
            nct_id=nct_id, title="Overall Survival", parameter="MEDIAN", unit="months",
            timeframe="Until death or up to 60 months", group="Cohort 2", value=24.5, provenance=prov,
        ),
    ]
    ids = _db.replace_outcome_records_for_trial(conn, nct_id, records)
    results = [classify_outcome(r) for r in records]
    _db.insert_classifications(conn, ids, results, CLASSIFIER_VERSION)
    conn.commit()
    return trial, records


def test_root_endpoint_never_touches_database():
    """'/' must respond even with no database configured at all --
    common platform default health-check target."""
    import os as _os
    saved = {k: _os.environ.pop(k, None) for k in ("SINGULARITY_DATABASE_URL", "DATABASE_URL")}
    try:
        with fastapi_testclient.TestClient(app) as c:
            resp = c.get("/")
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "Singularity Labs API"
        assert body["docs_url"] == "/docs"
    finally:
        for k, v in saved.items():
            if v is not None:
                _os.environ[k] = v


def test_health_endpoint_reports_not_configured_without_crashing():
    import os as _os
    saved = {k: _os.environ.pop(k, None) for k in ("SINGULARITY_DATABASE_URL", "DATABASE_URL")}
    try:
        with fastapi_testclient.TestClient(app) as c:
            resp = c.get("/health")
        assert resp.status_code == 200  # never fails the HTTP request itself
        body = resp.json()
        assert body["status"] == "ok"
        assert body["database"] == "not_configured"
    finally:
        for k, v in saved.items():
            if v is not None:
                _os.environ[k] = v


def test_health_endpoint_reports_connected_against_real_db(test_db_connection):
    """Confirms /health's real DB check (SELECT 1) actually works
    against a real database, not just the not-configured path."""
    import os as _os
    with test_db_connection.cursor() as cur:
        cur.execute("SELECT current_database()")
        db_name = cur.fetchone()[0]
    real_dsn = ADMIN_DSN.rsplit("/", 1)[0] + f"/{db_name}"
    saved = _os.environ.get("SINGULARITY_DATABASE_URL")
    _os.environ["SINGULARITY_DATABASE_URL"] = real_dsn
    try:
        with fastapi_testclient.TestClient(app) as c:
            resp = c.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok", "database": "connected"}
    finally:
        if saved is not None:
            _os.environ["SINGULARITY_DATABASE_URL"] = saved
        else:
            _os.environ.pop("SINGULARITY_DATABASE_URL", None)


def test_data_endpoint_returns_503_with_clear_message_when_db_not_configured():
    """'Clear handling of missing database configuration' -- a data
    endpoint must return a clean 503 with an actionable message, not a
    raw traceback/500, when SINGULARITY_DATABASE_URL/DATABASE_URL
    aren't set."""
    import os as _os
    saved = {k: _os.environ.pop(k, None) for k in ("SINGULARITY_DATABASE_URL", "DATABASE_URL")}
    try:
        with fastapi_testclient.TestClient(app) as c:
            resp = c.get("/trials")
        assert resp.status_code == 503
        assert "not configured" in resp.json()["detail"].lower()
    finally:
        for k, v in saved.items():
            if v is not None:
                _os.environ[k] = v


def test_openapi_schema_is_well_formed_no_db_needed():
    with fastapi_testclient.TestClient(app) as c:
        resp = c.get("/openapi.json")
    assert resp.status_code == 200
    schema = resp.json()
    assert set(schema["paths"].keys()) == {
        "/", "/health", "/trials/{nct_id}", "/trials", "/trials/{nct_id}/outcomes"
    }


def test_get_trial_by_nct_id(client, test_db_connection):
    _seed_real_shaped_trial(test_db_connection)
    resp = client.get("/trials/NCT88888801")
    assert resp.status_code == 200
    body = resp.json()
    assert body["nct_id"] == "NCT88888801"
    assert body["brief_title"] == "Mock Study of a Fictitious Drug in Metastatic Melanoma"
    assert body["overall_status"] == "COMPLETED"
    assert body["phases"] == ["PHASE2"]
    assert body["conditions"] == ["Metastatic Melanoma"]
    assert "provenance_raw" not in body
    assert "provenance_source" not in body


def test_get_trial_404_for_unknown_nct_id(client):
    resp = client.get("/trials/NCT00000000")
    assert resp.status_code == 404


def test_list_trials_returns_seeded_trial(client, test_db_connection):
    _seed_real_shaped_trial(test_db_connection)
    resp = client.get("/trials")
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 1
    assert body["trials"][0]["nct_id"] == "NCT88888801"


def test_list_trials_filters_by_condition(client, test_db_connection):
    _seed_real_shaped_trial(test_db_connection, nct_id="NCT88888802")
    resp_match = client.get("/trials", params={"condition": "melanoma"})
    assert resp_match.json()["count"] == 1
    resp_no_match = client.get("/trials", params={"condition": "lung cancer"})
    assert resp_no_match.json()["count"] == 0


def test_list_trials_filters_by_status_and_phase(client, test_db_connection):
    _seed_real_shaped_trial(test_db_connection, nct_id="NCT88888803")
    assert client.get("/trials", params={"status": "COMPLETED"}).json()["count"] == 1
    assert client.get("/trials", params={"status": "RECRUITING"}).json()["count"] == 0
    assert client.get("/trials", params={"phase": "PHASE2"}).json()["count"] == 1
    assert client.get("/trials", params={"phase": "PHASE3"}).json()["count"] == 0


def test_get_trial_outcomes_includes_classification_and_value_type(client, test_db_connection):
    _seed_real_shaped_trial(test_db_connection, nct_id="NCT88888804")
    resp = client.get("/trials/NCT88888804/outcomes")
    assert resp.status_code == 200
    body = resp.json()
    assert body["nct_id"] == "NCT88888804"
    assert body["count"] == 2

    by_title = {o["title"]: o for o in body["outcomes"]}

    orr_row = by_title["Disease Assessment for Objective Response Rate"]
    assert orr_row["endpoint"] == "ORR"
    assert orr_row["confident"] is True
    assert orr_row["value"] == 23.0
    # The exact real risk from session 11: this is a raw responder
    # count, not a rate -- value_type must say "count", not "rate".
    assert orr_row["value_type"] == "count"

    os_row = by_title["Overall Survival"]
    assert os_row["endpoint"] == "OS"
    assert os_row["subtype"] == "median_or_time_to_event"
    assert os_row["confident"] is True
    assert os_row["value"] == 24.5
    assert os_row["value_type"] == "time"

    assert "provenance_raw" not in orr_row


def test_get_trial_outcomes_404_for_unknown_trial(client):
    resp = client.get("/trials/NCT00000000/outcomes")
    assert resp.status_code == 404


def test_cors_headers_present_for_allowed_origin(client):
    """Real-data-verification gap closed (session 14): confirms the
    CORS middleware actually adds the header a browser-based frontend
    needs, for one of the default allowed dev origins."""
    resp = client.get("/trials", headers={"Origin": "http://localhost:3000"})
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:3000"


def _seed_real_shaped_pk_and_dor_and_rate_trial(conn, nct_id="NCT88888820"):
    """Seed real title/parameter/unit shapes (copied exactly from the
    session-11 validation dataset -- NCT01324323's PK measures and
    NCT02044380's percentage-based safety measure, and NCT02360579's
    DOR measure) not currently exercised via the live API in
    test_api.py's other seed helper. Synthetic NCT ID per this
    project's convention."""
    prov = Provenance(
        source="clinicaltrials.gov", source_record_id=nct_id, retrieved_at="2026-08-14T00:00:00Z",
        request_url="https://clinicaltrials.gov/api/v2/studies?mock=1", query_params={}, raw=None,
    )
    trial = Trial(nct_id=nct_id, brief_title="Mock PK/DOR/Rate Coverage Trial", overall_status="COMPLETED", provenance=prov)
    _db.upsert_trial(conn, trial)

    records = [
        # Real title/parameter/unit from NCT01324323 -- PK, must be "other".
        OutcomeRecord(nct_id=nct_id, title="Maximum Observed Plasma Concentration (Cmax)of Romidepsin",
                      parameter="GEOMETRIC_MEAN", unit="ng/mL", value=571.2, provenance=prov),
        # Real title/parameter/unit from NCT02044380 -- must be "rate".
        OutcomeRecord(nct_id=nct_id, title="Safety Assesment", parameter="NUMBER",
                      unit="Percentage of participants", value=92.9, provenance=prov),
        # Real title from NCT02360579 -- DOR, must classify confidently.
        OutcomeRecord(nct_id=nct_id, title="Disease Assessment for Duration of Response",
                      parameter="MEDIAN", unit="months", value=10.4, provenance=prov),
    ]
    ids = _db.replace_outcome_records_for_trial(conn, nct_id, records)
    results = [classify_outcome(r) for r in records]
    _db.insert_classifications(conn, ids, results, CLASSIFIER_VERSION)
    conn.commit()


def test_pk_rate_and_dor_value_types_correct_via_live_api(client, test_db_connection):
    """Closes a real-data-shape gap: the original test_api.py seed only
    covered 'count' and 'time' value_type via the live API. This
    covers 'other' (PK) and 'rate', plus a DOR classification, all
    using real title/parameter/unit text."""
    _seed_real_shaped_pk_and_dor_and_rate_trial(test_db_connection)
    resp = client.get("/trials/NCT88888820/outcomes")
    body = resp.json()
    by_title = {o["title"]: o for o in body["outcomes"]}

    assert by_title["Maximum Observed Plasma Concentration (Cmax)of Romidepsin"]["value_type"] == "other"
    assert by_title["Maximum Observed Plasma Concentration (Cmax)of Romidepsin"]["endpoint"] is None

    rate_row = by_title["Safety Assesment"]
    assert rate_row["value_type"] == "rate"
    assert rate_row["value"] == 92.9

    dor_row = by_title["Disease Assessment for Duration of Response"]
    assert dor_row["endpoint"] == "DOR"
    assert dor_row["confident"] is True
    assert dor_row["value_type"] == "time"


def test_low_confidence_classified_row_surfaced_correctly_via_api(client, test_db_connection):
    """The literal 109-row session-11 dataset happens to have ZERO
    low-confidence CLASSIFIED rows remaining after the session-12 fix
    (confirmed by direct inspection: all 13 classified rows are now
    confident=True) -- a positive side effect of that fix, not a gap.
    This test uses a real, previously-validated ClinicalTrials.gov
    phrasing pattern (session 6's fixed-timepoint OS finding,
    'Percentage of Participants Surviving at N Year(s)') to confirm the
    API still correctly surfaces a low-confidence classification when
    one exists, rather than hiding or erroring on it."""
    prov = Provenance(
        source="clinicaltrials.gov", source_record_id="NCT88888821", retrieved_at="2026-08-14T00:00:00Z",
        request_url="https://clinicaltrials.gov/api/v2/studies?mock=1", query_params={}, raw=None,
    )
    trial = Trial(nct_id="NCT88888821", brief_title="Mock Low-Confidence Coverage Trial", overall_status="COMPLETED", provenance=prov)
    _db.upsert_trial(test_db_connection, trial)
    records = [
        OutcomeRecord(nct_id="NCT88888821", title="Percentage of Participants Surviving at 1 Year",
                      parameter="NUMBER", unit="percentage of participants", value=68.0, provenance=prov),
    ]
    ids = _db.replace_outcome_records_for_trial(test_db_connection, "NCT88888821", records)
    results = [classify_outcome(r) for r in records]
    _db.insert_classifications(test_db_connection, ids, results, CLASSIFIER_VERSION)
    test_db_connection.commit()

    resp = client.get("/trials/NCT88888821/outcomes")
    row = resp.json()["outcomes"][0]
    assert row["endpoint"] == "OS"
    assert row["subtype"] == "OS1yr"
    assert row["confident"] is False
    assert row["reason"] is not None and len(row["reason"]) > 0


def test_large_unclassified_batch_not_silently_dropped(client, test_db_connection):
    """Real-data-shape check: NCT02360579's real 'Safety Profile'
    measure alone contributed 60 unclassified rows in the actual
    session-11 dataset. Confirms the API returns every row in a large
    all-unclassified batch, none silently dropped."""
    prov = Provenance(
        source="clinicaltrials.gov", source_record_id="NCT88888822", retrieved_at="2026-08-14T00:00:00Z",
        request_url="https://clinicaltrials.gov/api/v2/studies?mock=1", query_params={}, raw=None,
    )
    trial = Trial(nct_id="NCT88888822", brief_title="Mock Large-Batch Coverage Trial", overall_status="COMPLETED", provenance=prov)
    _db.upsert_trial(test_db_connection, trial)
    records = [
        OutcomeRecord(nct_id="NCT88888822", title="Safety Profile", parameter="COUNT_OF_PARTICIPANTS",
                      unit="Participants", group=f"Group {i}", value=float(i), provenance=prov)
        for i in range(40)
    ]
    ids = _db.replace_outcome_records_for_trial(test_db_connection, "NCT88888822", records)
    results = [classify_outcome(r) for r in records]
    _db.insert_classifications(test_db_connection, ids, results, CLASSIFIER_VERSION)
    test_db_connection.commit()

    resp = client.get("/trials/NCT88888822/outcomes")
    body = resp.json()
    assert body["count"] == 40
    assert len(body["outcomes"]) == 40
    assert all(o["endpoint"] is None for o in body["outcomes"])
    assert all(o["value_type"] == "count" for o in body["outcomes"])


def test_list_trials_respects_limit(client, test_db_connection):
    for i in range(3):
        _seed_real_shaped_trial(test_db_connection, nct_id=f"NCT8888880{5 + i}")
    resp = client.get("/trials", params={"limit": 2})
    body = resp.json()
    assert body["limit"] == 2
    assert body["count"] == 2
