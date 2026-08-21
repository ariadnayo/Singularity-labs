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

from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query

from .. import db as _db
from ..value_types import infer_value_type
from .models import OutcomeRecordResponse, TrialListResponse, TrialOutcomesResponse, TrialResponse

app = FastAPI(
    title="Singularity Labs API",
    description="Read-only clinical trial / endpoint classification data layer.",
    version="0.1.0",
)


def get_db_connection():
    """FastAPI dependency: one connection per request, always closed
    afterward (even on error) via the try/finally. Uses
    SINGULARITY_DATABASE_URL -- see singularity.db.get_connection.
    """
    conn = _db.get_connection()
    try:
        yield conn
    finally:
        conn.close()


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
