"""External data source adapters.

Each adapter maps a specific external API/source onto
`singularity.schema.OutcomeRecord`, attaching `Provenance` so every
record is traceable back to exactly what was requested and when.

Currently implemented:
- `clinicaltrials`: ClinicalTrials.gov API v2 (the initial authoritative
  source, per docs/architecture.md).

Planned, not yet implemented (see docs/roadmap.md and
docs/architecture.md): PubMed/NCBI, OpenAlex, FDA, PubChem, ChEMBL,
UniProt, Open Targets.
"""

__all__ = ["base", "clinicaltrials"]
