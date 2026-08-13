"""
Tests for singularity.ingest and singularity.audit.

All CSV content here is written to temporary files as MOCK / SYNTHETIC
fixtures for testing ingestion and validation logic. None of it is real
clinical-trial data, and none of it is treated as such anywhere in
this test suite.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

from singularity.ingest import load_records_from_csv
from singularity.audit import run_audit


def _write_csv(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


def test_missing_file_raises_not_silently_handled(tmp_path):
    missing = tmp_path / "does_not_exist.csv"
    with pytest.raises(FileNotFoundError):
        load_records_from_csv(missing)


def test_empty_dataset_reported_not_crashed(tmp_path):
    p = _write_csv(tmp_path, "empty.csv", "nct_id,title,parameter,unit,timeframe,group,value\n")
    records, report = load_records_from_csv(p)
    assert records == []
    assert report.total_rows == 0
    assert report.is_empty_dataset() is True
    assert any("empty" in w.lower() for w in report.warnings)


def test_missing_required_columns_flagged(tmp_path):
    p = _write_csv(tmp_path, "bad_header.csv", "identifier,name\nNCT001,Some title\n")
    records, report = load_records_from_csv(p)
    assert "nct_id" in report.missing_expected_columns
    assert "title" in report.missing_expected_columns
    # Rows can't be validly built without required columns present.
    assert records == []


def test_row_missing_required_field_excluded_and_counted(tmp_path):
    content = (
        "nct_id,title,parameter,unit,timeframe,group,value\n"
        "NCT001,Median Overall Survival,MEDIAN,months,,Arm A,24.5\n"
        ",Missing NCT ID Title,MEDIAN,months,,Arm A,10\n"
        "NCT003,,MEDIAN,months,,Arm A,10\n"
    )
    p = _write_csv(tmp_path, "missing_fields.csv", content)
    records, report = load_records_from_csv(p)
    assert report.total_rows == 3
    assert report.valid_rows == 1
    assert report.missing_required_field_rows == 2
    assert len(records) == 1
    assert records[0].nct_id == "NCT001"


def test_malformed_value_ingested_as_none_and_flagged(tmp_path):
    content = (
        "nct_id,title,parameter,unit,timeframe,group,value\n"
        "NCT001,Median Overall Survival,MEDIAN,months,,Arm A,not_a_number\n"
    )
    p = _write_csv(tmp_path, "malformed.csv", content)
    records, report = load_records_from_csv(p)
    assert report.malformed_value_rows == 1
    assert records[0].value is None


def test_duplicate_rows_detected_but_not_removed(tmp_path):
    content = (
        "nct_id,title,parameter,unit,timeframe,group,value\n"
        "NCT001,Median Overall Survival,MEDIAN,months,,Arm A,24.5\n"
        "NCT001,Median Overall Survival,MEDIAN,months,,Arm A,24.5\n"
    )
    p = _write_csv(tmp_path, "dupes.csv", content)
    records, report = load_records_from_csv(p)
    assert report.duplicate_rows == 1
    # Both rows retained -- duplication is reported, not silently merged.
    assert len(records) == 2


def test_unknown_columns_reported(tmp_path):
    content = (
        "nct_id,title,parameter,unit,timeframe,group,value,extra_col\n"
        "NCT001,Median Overall Survival,MEDIAN,months,,Arm A,24.5,mystery\n"
    )
    p = _write_csv(tmp_path, "extra_col.csv", content)
    records, report = load_records_from_csv(p)
    assert "extra_col" in report.unknown_columns
    assert len(records) == 1


def test_run_audit_raises_for_missing_file_not_fabricated(tmp_path):
    missing = tmp_path / "nonexistent_dataset.csv"
    with pytest.raises(FileNotFoundError):
        run_audit(missing)


def test_run_audit_end_to_end_on_mock_csv(tmp_path):
    content = (
        "nct_id,title,parameter,unit,timeframe,group,value\n"
        "NCT001,Median Overall Survival,MEDIAN,months,,Arm A,24.5\n"
        "NCT002,Objective Response Rate,NUMBER,percentage of participants,,Arm A,42\n"
        "NCT003,Disease Control Rate,NUMBER,percentage of participants,,Arm A,60\n"
        "NCT004,Progression-Free Survival at 6 months,NUMBER,Probability,6 months,Arm A,0.55\n"
    )
    p = _write_csv(tmp_path, "mock_outcomes.csv", content)
    audit = run_audit(p)
    assert audit.validation.total_rows == 4
    assert audit.validation.valid_rows == 4
    assert audit.classification_summary["total_rows"] == 4
    assert audit.classification_summary["unclassified_rows"] == 1  # DCR
    assert audit.classification_summary["counts_by_endpoint"]["OS"] == 1
    assert audit.classification_summary["counts_by_endpoint"]["ORR"] == 1
    assert audit.classification_summary["counts_by_endpoint"]["PFS"] == 1
    assert audit.classification_summary["low_confidence_classifications"] == 1  # PFS6
    md = audit.to_markdown()
    assert "Endpoint Classification Audit" in md
