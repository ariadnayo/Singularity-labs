"""
Pydantic response models for the API layer.

Defined and tested BEFORE any HTTP routing exists, per the Phase 2B
plan -- these are pure data shapes, independently testable without a
running server or a database.

Deliberately does NOT include `provenance_raw` in any response model
-- large JSONB blob, not needed by a UI, per the Phase 2B scope
decision. A future single-record detail endpoint can expose it
explicitly if ever needed.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from ..value_types import ValueType


class HealthResponse(BaseModel):
    status: str = Field(description="Always 'ok' if the app process itself is responding.")
    database: str = Field(description="'connected', 'unreachable', or 'not_configured'. Never raises.")


class RootResponse(BaseModel):
    name: str
    version: str
    docs_url: str


class TrialResponse(BaseModel):
    nct_id: str
    brief_title: Optional[str] = None
    official_title: Optional[str] = None
    overall_status: Optional[str] = None
    phases: Optional[list[str]] = None
    study_type: Optional[str] = None
    conditions: Optional[list[str]] = None
    lead_sponsor: Optional[str] = None
    interventions: Optional[list[str]] = None
    start_date: Optional[str] = None
    completion_date: Optional[str] = None
    enrollment_count: Optional[int] = None

    @classmethod
    def from_db_row(cls, row: dict) -> "TrialResponse":
        return cls(
            nct_id=row["nct_id"],
            brief_title=row.get("brief_title"),
            official_title=row.get("official_title"),
            overall_status=row.get("overall_status"),
            phases=row.get("phases"),
            study_type=row.get("study_type"),
            conditions=row.get("conditions"),
            lead_sponsor=row.get("lead_sponsor"),
            interventions=row.get("interventions"),
            start_date=row.get("start_date"),
            completion_date=row.get("completion_date"),
            enrollment_count=row.get("enrollment_count"),
        )


class TrialListResponse(BaseModel):
    trials: list[TrialResponse]
    limit: int
    offset: int
    count: int = Field(description="Number of trials in THIS response, not a total across all pages.")


class OutcomeRecordResponse(BaseModel):
    """One outcome measurement, with its latest classification joined
    in. `value_type` is COMPUTED (see singularity.value_types), not
    stored -- see that module's docstring for why it exists: a real,
    demonstrated risk (session 11) that a raw responder count could be
    silently presented as a rate without this label. `value_type` does
    NOT mean the underlying data-completeness gap (no denominator
    captured for count-typed rows) is solved -- see
    docs/data_dictionary.md "Known limitation" for that.
    """

    id: int
    nct_id: str
    title: str
    parameter: Optional[str] = None
    unit: Optional[str] = None
    timeframe: Optional[str] = None
    group: Optional[str] = None
    value: Optional[float] = None
    value_type: ValueType

    endpoint: Optional[str] = None
    subtype: Optional[str] = None
    confident: Optional[bool] = None
    reason: Optional[str] = None
    classifier_version: Optional[str] = None

    @classmethod
    def from_db_row(cls, row: dict, value_type: ValueType) -> "OutcomeRecordResponse":
        return cls(
            id=row["id"],
            nct_id=row["nct_id"],
            title=row["title"],
            parameter=row.get("parameter"),
            unit=row.get("unit"),
            timeframe=row.get("timeframe"),
            group=row.get("group_name"),
            value=row.get("value"),
            value_type=value_type,
            endpoint=row.get("endpoint"),
            subtype=row.get("subtype"),
            confident=row.get("confident"),
            reason=row.get("reason"),
            classifier_version=row.get("classifier_version"),
        )


class TrialOutcomesResponse(BaseModel):
    nct_id: str
    outcomes: list[OutcomeRecordResponse]
    count: int
