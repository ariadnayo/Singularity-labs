"""
Structured representation of a raw clinical outcome record.

This mirrors the fields defined in docs/data_dictionary.md. It does not
invent fields that aren't documented there, and it does not assume a
canonical endpoint has been assigned -- that is the job of
`endpoints.classify_outcome`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Provenance:
    """Generic record of where a raw data point came from and how it
    can be reproduced. Deliberately source-agnostic (no field here is
    specific to ClinicalTrials.gov) so any future adapter -- PubMed/
    NCBI, OpenAlex, FDA, PubChem, ChEMBL, UniProt, Open Targets, etc.
    -- can populate the same shape without changing this schema.
    """

    source: str  # e.g. "clinicaltrials.gov"
    source_record_id: str  # e.g. an NCT ID, PMID, ChEMBL ID, etc.
    retrieved_at: str  # ISO 8601 UTC timestamp of the actual retrieval
    request_url: str  # the exact URL/endpoint requested
    query_params: dict  # the exact query parameters used, for reproducibility
    raw: Optional[dict] = None  # the raw source record (or the relevant slice of it)


@dataclass(frozen=True)
class OutcomeRecord:
    """One row of raw, unclassified clinical outcome data.

    Fields correspond exactly to docs/data_dictionary.md:
    nct_id, title, parameter, unit, timeframe, group, value.

    `provenance` is optional (mock/test fixtures need not set it) but
    should always be populated for records ingested from a real
    external source, so downstream analyses can be traced back to
    exactly what was requested, when, and from where.
    """

    nct_id: str
    title: str
    parameter: Optional[str] = None
    unit: Optional[str] = None
    timeframe: Optional[str] = None
    group: Optional[str] = None
    value: Optional[float] = None
    provenance: Optional[Provenance] = None

    def __post_init__(self) -> None:
        if not self.nct_id:
            raise ValueError("OutcomeRecord requires a non-empty nct_id")
        if not self.title:
            raise ValueError("OutcomeRecord requires a non-empty title")


@dataclass(frozen=True)
class Trial:
    """Protocol-level representation of a single clinical trial,
    distinct from its outcome measurements (`OutcomeRecord`).

    A `Trial` and its `OutcomeRecord`s are linked by `nct_id` (a normal
    relational join, not embedding) -- a trial has zero, one, or many
    outcome records, and this deliberately doesn't duplicate that
    one-to-many relationship inside the dataclass itself.

    FIELD-VERIFICATION STATUS (2026-08-14, session 9): only
    `nct_id` has been independently verified against a live
    ClinicalTrials.gov API v2 response in this project (see
    docs/autonomous_state.md, sessions 4/5/9).  This session's
    other fields (`brief_title`, `official_title`, `overall_status`,
    `phases`, `study_type`, `conditions`, `lead_sponsor`,
    `interventions`, `start_date`, `completion_date`,
    `enrollment_count`) are mapped using the publicly documented,
    long-stable ClinicalTrials.gov API v2 schema, but this specific
    session did NOT have web-fetch tooling available to re-verify them
    against a fresh live response the way `identificationModule` and
    `outcomesModule` were verified in earlier sessions. This is
    disclosed, not hidden -- see
    `src/singularity/sources/clinicaltrials.py::extract_trial` and
    `docs/architecture.md` for the same caveat. Spot-check against a
    real response before trusting these fields at scale in Phase 2B.

    All fields except `nct_id` are optional: a real ClinicalTrials.gov
    record may genuinely omit any of them (e.g. an ongoing trial has
    no `completion_date` yet), and a missing field must be represented
    as `None`, never guessed or defaulted to something plausible.
    """

    nct_id: str
    brief_title: Optional[str] = None
    official_title: Optional[str] = None
    overall_status: Optional[str] = None  # e.g. RECRUITING, COMPLETED, TERMINATED
    phases: Optional[list] = None  # e.g. ["PHASE2", "PHASE3"]
    study_type: Optional[str] = None  # e.g. INTERVENTIONAL, OBSERVATIONAL
    conditions: Optional[list] = None  # list[str]
    lead_sponsor: Optional[str] = None
    interventions: Optional[list] = None  # list[str] (intervention names)
    start_date: Optional[str] = None  # as reported by the source; not parsed/normalized here
    completion_date: Optional[str] = None
    enrollment_count: Optional[int] = None
    provenance: Optional[Provenance] = None

    def __post_init__(self) -> None:
        if not self.nct_id:
            raise ValueError("Trial requires a non-empty nct_id")


@dataclass(frozen=True)
class ClassificationResult:
    """Result of attempting to classify a raw outcome into a canonical
    endpoint category.

    `endpoint` is one of the five canonical categories (PFS, OS, ORR, DOR,
    DFS) or None if the record could not be safely classified.

    `subtype` captures distinctions that must NOT be collapsed into the
    canonical category (e.g. "PFS6" is related to PFS but is not the same
    statistical quantity as median PFS, per docs/data_dictionary.md).

    `reason` documents why the classification (or non-classification)
    was made, so classification decisions are auditable rather than
    opaque.
    """

    endpoint: Optional[str]
    subtype: Optional[str]
    confident: bool
    reason: str
