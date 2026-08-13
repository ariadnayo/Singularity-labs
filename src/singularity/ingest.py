"""
Data ingestion and validation for raw clinical outcome data.

This module turns a CSV file matching the schema in
docs/data_dictionary.md into a list of `OutcomeRecord` objects, and
produces a `ValidationReport` describing data-quality issues.

Design principles (per Claude.md section 5 and section 9):

- Never silently drop or transform ambiguous/invalid rows. Every row
  that is excluded or flagged is counted and the reason is recorded in
  the ValidationReport, not swallowed.
- Duplicate rows are detected and counted but NOT silently removed --
  the caller decides what to do with them. Silent deduplication would
  be a silent transformation of the data.
- A malformed `value` field (non-numeric) does not crash ingestion; the
  row is still ingested with `value=None` and is flagged as malformed
  so it can be audited, rather than guessing a numeric value.
- Rows missing a required field (`nct_id` or `title`) cannot become an
  `OutcomeRecord` (see schema.py) and are excluded from the returned
  records, but are counted and reported.
"""

from __future__ import annotations

import csv
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from .schema import OutcomeRecord

REQUIRED_COLUMNS = {"nct_id", "title"}
KNOWN_COLUMNS = {"nct_id", "title", "parameter", "unit", "timeframe", "group", "value"}


@dataclass
class ValidationReport:
    """Data-quality audit produced while ingesting a raw outcomes file."""

    source: str
    total_rows: int = 0
    valid_rows: int = 0
    missing_required_field_rows: int = 0
    malformed_value_rows: int = 0
    duplicate_rows: int = 0
    unknown_columns: list[str] = field(default_factory=list)
    missing_expected_columns: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def is_empty_dataset(self) -> bool:
        return self.total_rows == 0

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "total_rows": self.total_rows,
            "valid_rows": self.valid_rows,
            "missing_required_field_rows": self.missing_required_field_rows,
            "malformed_value_rows": self.malformed_value_rows,
            "duplicate_rows": self.duplicate_rows,
            "unknown_columns": self.unknown_columns,
            "missing_expected_columns": self.missing_expected_columns,
            "warnings": self.warnings,
        }


def _parse_value(raw: str | None) -> tuple[float | None, bool]:
    """Return (parsed_value, was_malformed)."""
    if raw is None or raw.strip() == "":
        return None, False
    try:
        return float(raw), False
    except ValueError:
        return None, True


def load_records_from_csv(path: str | Path) -> tuple[list[OutcomeRecord], ValidationReport]:
    """Load and validate raw outcome records from a CSV file.

    Does not raise on data-quality problems (missing fields, malformed
    values, duplicates) -- those are recorded in the returned
    ValidationReport. Raises FileNotFoundError if the path does not
    exist, since that is an environment problem, not a data-quality
    one, and must not be silently handled per Claude.md section 13.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"No such data file: {path}")

    report = ValidationReport(source=str(path))
    records: list[OutcomeRecord] = []
    seen: Counter[tuple] = Counter()

    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = set(reader.fieldnames or [])

        report.missing_expected_columns = sorted(REQUIRED_COLUMNS - fieldnames)
        report.unknown_columns = sorted(fieldnames - KNOWN_COLUMNS)

        if REQUIRED_COLUMNS - fieldnames:
            report.warnings.append(
                f"Required column(s) missing from header: {sorted(REQUIRED_COLUMNS - fieldnames)}. "
                "No rows can be validly ingested without them."
            )

        for row in reader:
            report.total_rows += 1

            nct_id = (row.get("nct_id") or "").strip()
            title = (row.get("title") or "").strip()

            if not nct_id or not title:
                report.missing_required_field_rows += 1
                report.warnings.append(
                    f"Row {report.total_rows}: missing required field "
                    f"(nct_id={'present' if nct_id else 'MISSING'}, "
                    f"title={'present' if title else 'MISSING'}); row excluded."
                )
                continue

            value, malformed = _parse_value(row.get("value"))
            if malformed:
                report.malformed_value_rows += 1
                report.warnings.append(
                    f"Row {report.total_rows}: non-numeric value "
                    f"{row.get('value')!r} for nct_id={nct_id}; ingested with value=None."
                )

            dedup_key = (
                nct_id,
                title,
                row.get("parameter"),
                row.get("unit"),
                row.get("timeframe"),
                row.get("group"),
            )
            seen[dedup_key] += 1
            if seen[dedup_key] > 1:
                report.duplicate_rows += 1
                report.warnings.append(
                    f"Row {report.total_rows}: duplicate of an earlier row "
                    f"(nct_id={nct_id}, title={title!r}); both rows retained, not silently merged."
                )

            records.append(
                OutcomeRecord(
                    nct_id=nct_id,
                    title=title,
                    parameter=(row.get("parameter") or None),
                    unit=(row.get("unit") or None),
                    timeframe=(row.get("timeframe") or None),
                    group=(row.get("group") or None),
                    value=value,
                )
            )
            report.valid_rows += 1

    if report.is_empty_dataset():
        report.warnings.append("Dataset is empty: 0 rows found in source file.")

    return records, report
