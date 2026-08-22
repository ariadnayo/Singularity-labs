"""
FastAPI application: the read-only data layer for the eventual
Singularity Labs website.

Scope, deliberately minimal (see docs/architecture.md "API Layer" and
docs/roadmap.md "Phase 2B"):
  - GET /trials/{nct_id}
  - GET /trials  (list, with condition/phase/status filters)
  - GET /trials/{nct_id}/outcomes

No auth, no write/ingestion endpoints, no background jobs, no
GraphQL, no pagination beyond LIMIT/OFFSET. Ingestion stays a
human-run script. This is a backend milestone, not a public launch.

Run locally:
    export SINGULARITY_DATABASE_URL="postgresql://...."
    uvicorn singularity.api.main:app --reload
"""

from __future__ import annotations

import os
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .. import db as _db
from ..value_types import infer_value_type
from .models import OutcomeRecordResponse, RootResponse, TrialListResponse, TrialOutcomesResponse, TrialResponse, HealthResponse

app = FastAPI(
    title="Singularity Labs API",
    description="Read-only clinical trial / endpoint classification data layer.",
    version="0.1.0",
)

# CORS: added session 14 (2026-08-14) so a browser-based frontend on a
# different origin can call this API -- the frontend itself is NOT
# built yet (see docs/roadmap.md "Phase 2B"), this only unblocks it.
# `allow_origins` defaults to common local dev origins (Next.js's
# default port 3000, plus 5173 for Vite-based tooling if ever used);
# override via the SINGULARITY_CORS_ORIGINS env var (comma-separated)
# for any other deployment target. No credentials/cookies are used by
# this API (no auth exists yet), so allow_credentials stays False.
_default_origins = ["http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:5173", "http://127.0.0.1:5173"]
_cors_origins_env = os.environ.get("SINGULARITY_CORS_ORIGINS")
_cors_origins = [o.strip() for o in _cors_origins_env.split(",")] if _cors_origins_env else _default_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)


def get_db_connection():
    """FastAPI dependency: one connection per request, always closed
    afterward (even on error) via the try/finally. Uses
    SINGULARITY_DATABASE_URL (or DATABASE_URL as a fallback) -- see
    singularity.db.get_connection.

    Deliberately converts missing-config/connection-failure into a
    clean HTTP 503 with a clear message, rather than letting a raw
    ValueError/psycopg2 exception surface as an unhandled 500 with a
    traceback -- added session 15 (2026-08-14) for deployment: "clear
    handling of missing database configuration" per the Phase 2B-3
    scope. /health and / do NOT use this dependency (see below) --
    they must stay reachable even when the database is completely
    unreachable or unconfigured, so a deployment platform's liveness
    probe doesn't fail just because the DB isn't ready yet.
    """
    try:
        conn = _db.get_connection()
    except ValueError as e:
        raise HTTPException(status_code=503, detail=f"Database not configured: {e}") from e
    except Exception as e:  # noqa: BLE001 -- any connection failure, not just missing config
        raise HTTPException(status_code=503, detail=f"Database unreachable: {e}") from e
    try:
        yield conn
    finally:
        conn.close()


@app.get("/", response_model=RootResponse)
def root() -> RootResponse:
    """Basic liveness/info endpoint. Does NOT touch the database --
    many deployment platforms ping '/' by default for a basic health
    check, and this must always respond regardless of DB state."""
    return RootResponse(name="Singularity Labs API", version=app.version, docs_url="/docs")


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Deployment health check. Always returns 200 -- this reports
    status IN the response body rather than failing the HTTP request,
    so a platform's liveness probe can distinguish "app process is up
    but DB isn't ready" from "app process itself is down" (the latter
    is the only case that should actually fail a liveness check).

    Never raises: a completely unreachable/misconfigured database is a
    normal, expected, reportable state for this endpoint, not a crash.
    """
    database_configured = bool(os.environ.get("SINGULARITY_DATABASE_URL") or os.environ.get("DATABASE_URL"))
    database_status = "not_configured"
    if database_configured:
        try:
            conn = _db.get_connection()
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                database_status = "connected"
            finally:
                conn.close()
        except Exception:  # noqa: BLE001 -- deliberately broad: this endpoint must never raise
            database_status = "unreachable"
    return HealthResponse(status="ok", database=database_status)


@app.get("/trials/{nct_id}", response_model=TrialResponse)
def read_trial(nct_id: str, conn=Depends(get_db_connection)) -> TrialResponse:
    row = _db.get_trial(conn, nct_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"No trial found for nct_id={nct_id!r}")
    return TrialResponse.from_db_row(row)


@app.get("/trials", response_model=TrialListResponse)
def list_trials(
    condition: Optional[str] = Query(None, description="Case-insensitive substring match against studied conditions."),
    phase: Optional[str] = Query(None, description="Exact match, e.g. 'PHASE2'."),
    status: Optional[str] = Query(None, description="Exact match, e.g. 'COMPLETED'."),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    conn=Depends(get_db_connection),
) -> TrialListResponse:
    rows = _db.list_trials(conn, condition=condition, phase=phase, status=status, limit=limit, offset=offset)
    trials = [TrialResponse.from_db_row(r) for r in rows]
    return TrialListResponse(trials=trials, limit=limit, offset=offset, count=len(trials))


@app.get("/trials/{nct_id}/outcomes", response_model=TrialOutcomesResponse)
def read_trial_outcomes(nct_id: str, conn=Depends(get_db_connection)) -> TrialOutcomesResponse:
    trial_row = _db.get_trial(conn, nct_id)
    if trial_row is None:
        raise HTTPException(status_code=404, detail=f"No trial found for nct_id={nct_id!r}")

    rows = _db.get_outcomes_for_trial(conn, nct_id)
    outcomes = [
        OutcomeRecordResponse.from_db_row(r, infer_value_type(r.get("parameter"), r.get("unit"))) for r in rows
    ]
    return TrialOutcomesResponse(nct_id=nct_id, outcomes=outcomes, count=len(outcomes))
