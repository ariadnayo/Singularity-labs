"""
Tests for singularity.endpoints.

All records used here are MOCK / SYNTHETIC test fixtures, not real
clinical-trial data. They exist only to exercise classification logic
edge cases described in docs/data_dictionary.md.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from singularity.endpoints import classify_outcome, classify_batch, summarize
from singularity.schema import OutcomeRecord


def _mock_record(**kwargs) -> OutcomeRecord:
    defaults = dict(nct_id="NCT00000000", title="", parameter=None, unit=None, timeframe=None)
    defaults.update(kwargs)
    return OutcomeRecord(**defaults)


def test_median_pfs_classified_confidently():
    r = _mock_record(title="Median Progression-Free Survival", parameter="MEDIAN", unit="months")
    result = classify_outcome(r)
    assert result.endpoint == "PFS"
    assert result.confident is True
    assert result.subtype == "median_or_time_to_event"


def test_pfs6_not_treated_as_equivalent_to_median_pfs():
    r = _mock_record(
        title="Progression-Free Survival at 6 months",
        parameter="NUMBER",
        unit="Probability",
        timeframe="6 months",
    )
    result = classify_outcome(r)
    assert result.endpoint == "PFS"
    assert result.subtype == "PFS6"
    # Fixed-timepoint PFS must be flagged as lower confidence / distinct subtype
    assert result.confident is False


def test_median_os_classified_confidently():
    r = _mock_record(title="Median Overall Survival", parameter="MEDIAN", unit="months")
    result = classify_outcome(r)
    assert result.endpoint == "OS"
    assert result.confident is True


def test_os_rate_at_fixed_timepoint_flagged_as_subtype():
    r = _mock_record(
        title="Overall Survival Rate at 12 months",
        parameter="NUMBER",
        unit="Probability",
        timeframe="12 months",
    )
    result = classify_outcome(r)
    assert result.endpoint == "OS"
    assert result.subtype == "OS12"
    assert result.confident is False


def test_orr_classified_confidently():
    r = _mock_record(title="Objective Response Rate (ORR)", parameter="NUMBER", unit="percentage of participants")
    result = classify_outcome(r)
    assert result.endpoint == "ORR"
    assert result.confident is True


def test_duration_of_response_not_classified_as_orr():
    r = _mock_record(title="Duration of Objective Response", parameter="MEDIAN", unit="months")
    result = classify_outcome(r)
    assert result.endpoint == "DOR"
    assert result.endpoint != "ORR"


def test_disease_control_rate_left_unclassified():
    r = _mock_record(title="Disease Control Rate (DCR)", parameter="NUMBER", unit="percentage of participants")
    result = classify_outcome(r)
    assert result.endpoint is None
    assert "DCR" in result.reason or "related-but-distinct" in result.reason


def test_time_to_progression_left_unclassified_not_mapped_to_pfs():
    r = _mock_record(title="Time to Progression", parameter="MEDIAN", unit="months")
    result = classify_outcome(r)
    assert result.endpoint is None


def test_quality_of_life_left_unclassified():
    r = _mock_record(title="Change in Quality of Life Score", parameter="MEAN", unit="Score on a scale")
    result = classify_outcome(r)
    assert result.endpoint is None


def test_disease_free_survival_median():
    r = _mock_record(title="Median Disease-Free Survival", parameter="MEDIAN", unit="months")
    result = classify_outcome(r)
    assert result.endpoint == "DFS"
    assert result.confident is True


def test_unrecognized_title_left_unclassified_not_guessed():
    r = _mock_record(title="Number of Participants with Serious Adverse Events", parameter="COUNT_OF_PARTICIPANTS")
    result = classify_outcome(r)
    assert result.endpoint is None


def test_empty_title_raises_on_construction():
    try:
        _mock_record(title="")
        assert False, "expected ValueError for empty title"
    except ValueError:
        pass


def test_summarize_counts_are_consistent():
    records = [
        _mock_record(title="Median Overall Survival", parameter="MEDIAN", unit="months"),
        _mock_record(title="Objective Response Rate", parameter="NUMBER", unit="percentage of participants"),
        _mock_record(title="Disease Control Rate", parameter="NUMBER", unit="percentage of participants"),
    ]
    results = classify_batch(records)
    summary = summarize(results)
    assert summary["total_rows"] == 3
    assert summary["classified_rows"] == 2
    assert summary["unclassified_rows"] == 1
    assert summary["counts_by_endpoint"]["OS"] == 1
    assert summary["counts_by_endpoint"]["ORR"] == 1
