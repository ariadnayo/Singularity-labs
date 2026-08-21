"""
Low-level PostgreSQL read/write helpers for singularity.pipeline and
the API layer (singularity.api).

Deliberately raw SQL via psycopg2, not an ORM -- no ORM/migration-tool
decision has been made yet (see docs/autonomous_state.md "Session 9
Summary"; that's a Phase 2B decision depending on the API framework).
This module is the minimum needed to read/write Trial/OutcomeRecord/
ClassificationResult data against the schema in db/migrations/, safely
and idempotently, without introducing a new dependency/framework
decision that hasn't been made.

Every function here takes an already-open connection (dependency
injection) rather than opening its own -- this is what makes
singularity.pipeline and the API layer testable against a real scratch
database, the same pattern already established in
tests/test_db_schema.py.

Transaction handling is the CALLER's responsibility for the write
functions (see singularity.pipeline for the per-trial commit/rollback
boundary this project uses) -- these functions execute statements but
do not commit or rollback themselves, so they compose safely inside a
larger transaction. Read functions never need a transaction boundary
beyond the implicit one PostgreSQL gives every statement.

Read functions return plain dicts (column name -> value), not the
Trial/OutcomeRecord dataclasses -- deliberately: the API response
shape (singularity.api.models) is a separate concern from what this
module fetches, and dicts avoid needing to reconstruct a full
Provenance object (which isn't wanted in most API responses) just to
read a few columns.
"""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING

from .schema import ClassificationResult, OutcomeRecord, Provenance, Trial

if TYPE_CHECKING:
    import psycopg2


def get_connection(dsn: "str | None" = None):
    """Open a real PostgreSQL connection. Raises immediately (does not
    retry, does not fall back to anything) if psycopg2 is not
    installed or the connection fails -- per the "fail loudly on
    infrastructure problems" principle already established in this
    project (Claude.md section 13, singularity.ingest,
    singularity.sources.clinicaltrials).

    `dsn` defaults to the SINGULARITY_DATABASE_URL environment
    variable if not passed explicitly. Never hardcodes a real
    application database DSN anywhere in this codebase.
    """
    try:
        import psycopg2  # noqa: F401 (import used below via module attribute)
    except ImportError as e:
        raise ImportError(
            "psycopg2 is required to connect to PostgreSQL. Install the optional "
            "'db' extra: pip install -e \".[db]\""
        ) from e

    resolved_dsn = dsn or os.environ.get("SINGULARITY_DATABASE_URL")
    if not resolved_dsn:
        raise ValueError(
            "No database DSN provided and SINGULARITY_DATABASE_URL is not set. "
            "Refusing to guess a connection target."
        )
    return __import__("psycopg2").connect(resolved_dsn)


def _rows_as_dicts(cur) -> "list[dict]":
    """Zip cursor.description column names with each fetched row.
    Deliberately not psycopg2.extras.RealDictCursor -- avoids adding a
    second cursor-factory convention alongside the plain cursors
    already used throughout this module's write functions.
    """
    columns = [d[0] for d in cur.description]
    return [dict(zip(columns, row)) for row in cur.fetchall()]


def get_trial(conn, nct_id: str) -> "dict | None":
    """Fetch a single trial by nct_id. Returns None if not found (does
    not raise) -- a missing trial is a normal, expected outcome for a
    lookup, not an error.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT nct_id, brief_title, official_title, overall_status, phases, study_type,
                   conditions, lead_sponsor, interventions, start_date, completion_date,
                   enrollment_count, ingested_at, updated_at
            FROM trials
            WHERE nct_id = %s
            """,
            (nct_id,),
        )
        rows = _rows_as_dicts(cur)
    return rows[0] if rows else None


def list_trials(
    conn,
    *,
    condition: "str | None" = None,
    phase: "str | None" = None,
    status: "str | None" = None,
    limit: int = 50,
    offset: int = 0,
) -> "list[dict]":
    """List trials with optional filters. All filters are AND-combined
    when more than one is given. `condition` is a case-insensitive
    substring match against any element of the trial's `conditions`
    array; `phase` and `status` are exact matches (phase against any
    element of `phases`).

    `limit` is capped at 200 regardless of what's requested, to avoid
    an unbounded query -- this is a read-only, list-style endpoint, not
    a bulk-export mechanism.
    """
    limit = max(1, min(limit, 200))
    offset = max(0, offset)

    where_clauses = []
    params: list = []
    if condition:
        where_clauses.append("EXISTS (SELECT 1 FROM unnest(conditions) AS c WHERE c ILIKE %s)")
        params.append(f"%{condition}%")
    if phase:
        where_clauses.append("%s = ANY(phases)")
        params.append(phase)
    if status:
        where_clauses.append("overall_status = %s")
        params.append(status)

    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
    params.extend([limit, offset])

    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT nct_id, brief_title, official_title, overall_status, phases, study_type,
                   conditions, lead_sponsor, interventions, start_date, completion_date,
                   enrollment_count, ingested_at, updated_at
            FROM trials
            {where_sql}
            ORDER BY nct_id
            LIMIT %s OFFSET %s
            """,
            params,
        )
        return _rows_as_dicts(cur)


def get_outcomes_for_trial(conn, nct_id: str) -> "list[dict]":
    """Fetch every outcome record for a trial, joined with its latest
    classification (via the `latest_endpoint_classifications` view --
    see db/migrations/0003). Uses a LEFT JOIN so an outcome record with
    no classification row yet (should not happen via the normal
    ingestion pipeline, but must not silently vanish if it did) still
    appears, with classification fields as None.

    Deliberately does NOT select outcome_records.provenance_raw --
    that's a large JSONB blob not needed for a list view; a future
    single-outcome-record endpoint can fetch it explicitly if needed.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                o.id, o.nct_id, o.title, o.parameter, o.unit, o.timeframe, o.group_name, o.value,
                lec.endpoint, lec.subtype, lec.confident, lec.reason, lec.classifier_version, lec.classified_at
            FROM outcome_records o
            LEFT JOIN latest_endpoint_classifications lec ON lec.outcome_record_id = o.id
            WHERE o.nct_id = %s
            ORDER BY o.id
            """,
            (nct_id,),
        )
        return _rows_as_dicts(cur)


def upsert_trial(conn, trial: Trial) -> None:
    """Insert a Trial, or update it in place if its nct_id already
    exists (safe to re-run). Does not commit -- caller controls the
    transaction boundary.
    """
    prov = trial.provenance
    if prov is None:
        raise ValueError(f"Trial {trial.nct_id!r} has no provenance; refusing to persist an unprovenanced record.")

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO trials (
                nct_id, brief_title, official_title, overall_status, phases, study_type,
                conditions, lead_sponsor, interventions, start_date, completion_date,
                enrollment_count, provenance_source, provenance_source_record_id,
                provenance_retrieved_at, provenance_request_url, provenance_query_params,
                provenance_raw, updated_at
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, now())
            ON CONFLICT (nct_id) DO UPDATE SET
                brief_title = EXCLUDED.brief_title,
                official_title = EXCLUDED.official_title,
                overall_status = EXCLUDED.overall_status,
                phases = EXCLUDED.phases,
                study_type = EXCLUDED.study_type,
                conditions = EXCLUDED.conditions,
                lead_sponsor = EXCLUDED.lead_sponsor,
                interventions = EXCLUDED.interventions,
                start_date = EXCLUDED.start_date,
                completion_date = EXCLUDED.completion_date,
                enrollment_count = EXCLUDED.enrollment_count,
                provenance_source = EXCLUDED.provenance_source,
                provenance_source_record_id = EXCLUDED.provenance_source_record_id,
                provenance_retrieved_at = EXCLUDED.provenance_retrieved_at,
                provenance_request_url = EXCLUDED.provenance_request_url,
                provenance_query_params = EXCLUDED.provenance_query_params,
                provenance_raw = EXCLUDED.provenance_raw,
                updated_at = now()
            """,
            (
                trial.nct_id, trial.brief_title, trial.official_title, trial.overall_status,
                trial.phases, trial.study_type, trial.conditions, trial.lead_sponsor,
                trial.interventions, trial.start_date, trial.completion_date, trial.enrollment_count,
                prov.source, prov.source_record_id, prov.retrieved_at, prov.request_url,
                json.dumps(prov.query_params), json.dumps(prov.raw),
            ),
        )


def replace_outcome_records_for_trial(conn, nct_id: str, records: "list[OutcomeRecord]") -> "list[int]":
    """Idempotent re-run strategy for outcome_records (see
    singularity.pipeline's module docstring for the full rationale):
    DELETE all existing outcome_records for this nct_id, then INSERT
    the freshly extracted ones. Old endpoint_classifications for the
    deleted rows are removed automatically via ON DELETE CASCADE (see
    db/migrations/0003), so nothing is orphaned.

    Returns the new outcome_records.id values, in the same order as
    `records`, for the caller to attach classifications to.

    Does NOT commit -- caller controls the transaction boundary, so a
    failure partway through this trial's processing can be rolled back
    without affecting other trials already committed in the same run.
    """
    with conn.cursor() as cur:
        cur.execute("DELETE FROM outcome_records WHERE nct_id = %s", (nct_id,))

        ids: list[int] = []
        for rec in records:
            prov = rec.provenance
            if prov is None:
                raise ValueError(
                    f"OutcomeRecord {rec.nct_id!r}/{rec.title!r} has no provenance; "
                    "refusing to persist an unprovenanced record."
                )
            cur.execute(
                """
                INSERT INTO outcome_records (
                    nct_id, title, parameter, unit, timeframe, group_name, value,
                    provenance_source, provenance_source_record_id, provenance_retrieved_at,
                    provenance_request_url, provenance_query_params, provenance_raw
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING id
                """,
                (
                    rec.nct_id, rec.title, rec.parameter, rec.unit, rec.timeframe, rec.group, rec.value,
                    prov.source, prov.source_record_id, prov.retrieved_at, prov.request_url,
                    json.dumps(prov.query_params), json.dumps(prov.raw),
                ),
            )
            ids.append(cur.fetchone()[0])
    return ids


def insert_classifications(
    conn, outcome_record_ids: "list[int]", results: "list[ClassificationResult]", classifier_version: str
) -> None:
    """Insert one endpoint_classifications row per (outcome_record_id,
    result) pair. Never updates/overwrites an existing classification
    row -- classifications are append-only/versioned by design (see
    db/README.md); this is only called for freshly-inserted
    outcome_records (see replace_outcome_records_for_trial), so there
    is nothing to conflict with.
    """
    if len(outcome_record_ids) != len(results):
        raise ValueError(
            f"outcome_record_ids ({len(outcome_record_ids)}) and results ({len(results)}) length mismatch"
        )
    with conn.cursor() as cur:
        for oid, result in zip(outcome_record_ids, results):
            cur.execute(
                """
                INSERT INTO endpoint_classifications
                    (outcome_record_id, endpoint, subtype, confident, reason, classifier_version)
                VALUES (%s,%s,%s,%s,%s,%s)
                """,
                (oid, result.endpoint, result.subtype, result.confident, result.reason, classifier_version),
            )
