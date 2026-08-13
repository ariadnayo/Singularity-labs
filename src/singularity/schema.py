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
