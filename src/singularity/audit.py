"""
End-to-end endpoint-classification audit.

Ties together `ingest.load_records_from_csv` and
`endpoints.classify_batch` / `endpoints.summarize` into a single
reproducible report.

This module does not know or assume any specific file path. The caller
must supply a real path to a real data file. If that file does not
exist, `run_audit` raises FileNotFoundError rather than silently
falling back to any built-in or fabricated data -- there is no
fallback dataset anywhere in this codebase.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .endpoints import classify_batch, summarize
from .ingest import ValidationReport, load_records_from_csv


@dataclass
class AuditReport:
    source: str
    validation: ValidationReport
    classification_summary: dict

    def to_markdown(self) -> str:
        v = self.validation
        s = self.classification_summary
        lines = [
            f"# Endpoint Classification Audit — {self.source}",
            "",
            "## Ingestion / Validation",
            f"- Total rows read: {v.total_rows}",
            f"- Valid rows ingested: {v.valid_rows}",
            f"- Rows excluded (missing nct_id/title): {v.missing_required_field_rows}",
            f"- Rows with malformed `value`: {v.malformed_value_rows}",
            f"- Duplicate rows detected (not removed): {v.duplicate_rows}",
            f"- Unknown columns in source: {v.unknown_columns or 'none'}",
            f"- Missing expected columns: {v.missing_expected_columns or 'none'}",
            "",
            "## Endpoint Classification (of ingested rows)",
            f"- Total classified rows: {s['total_rows']}",
            f"- Classified: {s['classified_rows']}",
            f"- Unclassified: {s['unclassified_rows']}",
            f"- Counts by endpoint: {s['counts_by_endpoint']}",
            f"- Low-confidence (subtype-flagged) classifications: {s['low_confidence_classifications']}",
        ]
        if v.warnings:
            lines.append("")
            lines.append("## Warnings")
            lines.extend(f"- {w}" for w in v.warnings[:50])
            if len(v.warnings) > 50:
                lines.append(f"- ... and {len(v.warnings) - 50} more warnings")
        return "\n".join(lines)


def run_audit(csv_path: str | Path) -> AuditReport:
    """Run ingestion + classification against a real CSV file at
    `csv_path`. Raises FileNotFoundError if the file does not exist.
    There is no built-in fallback dataset.
    """
    records, validation = load_records_from_csv(csv_path)
    results = classify_batch(records)
    summary = summarize(results)
    return AuditReport(source=str(csv_path), validation=validation, classification_summary=summary)
