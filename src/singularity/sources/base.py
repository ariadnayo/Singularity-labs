"""
Generic interface that any external data-source adapter implements.

The goal is that adding PubMed/NCBI, OpenAlex, FDA, PubChem, ChEMBL,
UniProt, Open Targets, etc. later means writing a new module in this
package that implements `DataSourceAdapter` and returns
`singularity.schema.OutcomeRecord` objects with `Provenance` attached
-- without touching `singularity.schema`, `singularity.endpoints`,
`singularity.ingest`, or `singularity.audit`.

Only one adapter (`clinicaltrials.py`) is implemented right now, per
instructions: get this one right and reproducible before adding others.
"""

from __future__ import annotations

from typing import Iterable, Protocol

from ..schema import OutcomeRecord


class DataSourceAdapter(Protocol):
    """Structural interface for a source adapter.

    Implementations are not required to subclass this -- it exists as
    documentation of the expected shape and for static type checking.
    """

    source_name: str

    def fetch_outcome_records(self, **query) -> Iterable[OutcomeRecord]:
        """Fetch and return OutcomeRecord objects for the given query.

        Each returned record's `provenance` field must be populated
        (source, source_record_id, retrieved_at, request_url,
        query_params, raw) so results are reproducible and auditable.

        Implementations must not fabricate data: if the underlying
        source has no data for a field, that field is left None, not
        guessed or interpolated.
        """
        ...
