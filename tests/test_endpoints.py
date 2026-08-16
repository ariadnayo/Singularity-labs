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


def test_followup_ceiling_timeframe_not_mistaken_for_fixed_timepoint():
    """Regression test for a real classification bug found during
    ClinicalTrials.gov real-data validation on 2026-08-13
    (docs/autonomous_state.md): a plain median PFS/OS title with a
    study-wide follow-up ceiling in `timeframe` (e.g. "Up to
    approximately 58 months") was incorrectly flagged as a fixed-
    timepoint PFS58/OS58 subtype. The exact title/timeframe pair below
    is copied from the real trial (NCT07227597) that exposed the bug.
    """
    r = _mock_record(
        title="Progression-Free Survival (PFS)",
        parameter=None,
        unit=None,
        timeframe="Up to approximately 58 months",
    )
    result = classify_outcome(r)
    assert result.endpoint == "PFS"
    assert result.subtype == "median_or_time_to_event"
    assert result.confident is True

    r2 = _mock_record(
        title="Overall Survival (OS)",
        parameter=None,
        unit=None,
        timeframe="Up to approximately 58 months",
    )
    result2 = classify_outcome(r2)
    assert result2.endpoint == "OS"
    assert result2.subtype == "median_or_time_to_event"
    assert result2.confident is True


def test_genuine_fixed_timepoint_in_title_still_detected():
    """Make sure the fix above didn't remove real fixed-timepoint
    detection -- only the false-positive source (ceiling timeframes).
    """
    r = _mock_record(
        title="Progression-Free Survival at 6 Months",
        parameter="NUMBER",
        unit="Probability",
        timeframe="Up to approximately 58 months",
    )
    result = classify_outcome(r)
    assert result.endpoint == "PFS"
    assert result.subtype == "PFS6"
    assert result.confident is False


def test_orr_synonym_complete_and_partial_response_rate():
    """Real example (NCT-level, 2026-08-14 validation): 'Complete and
    Partial Response Rate Using the Response Evaluation Criteria in
    Solid Tumors (RECIST) Criteria'."""
    r = _mock_record(
        title="Complete and Partial Response Rate Using the Response Evaluation Criteria in Solid Tumors (RECIST) Criteria",
        parameter="NUMBER",
        unit="percentage of participants",
    )
    result = classify_outcome(r)
    assert result.endpoint == "ORR"
    assert result.confident is True


def test_orr_synonym_objective_tumor_response_rate_with_cr_pr():
    """Real example: 'Proportion of Patients With Objective Tumor
    Response Rate (Complete Response [CR] or Partial Response [PR])
    Using RECIST Version 1.1'."""
    r = _mock_record(
        title="Proportion of Patients With Objective Tumor Response Rate (Complete Response [CR] or Partial Response [PR]) Using RECIST Version 1.1",
        parameter="NUMBER",
        unit="percentage of participants",
    )
    result = classify_outcome(r)
    assert result.endpoint == "ORR"
    assert result.confident is True


def test_orr_synonym_complete_or_partial_objective_tumor_response():
    """Real example: 'Complete or Partial Objective Tumor Response'."""
    r = _mock_record(title="Complete or Partial Objective Tumor Response", parameter="NUMBER", unit="percentage of participants")
    result = classify_outcome(r)
    assert result.endpoint == "ORR"
    assert result.confident is True


def test_orr_synonym_achieving_either_cr_or_pr():
    """Real example: 'Percentage of Participants Achieving Either
    Complete Response (CR) or Partial Response (PR) According to
    RECIST'."""
    r = _mock_record(
        title="Percentage of Participants Achieving Either Complete Response (CR) or Partial Response (PR) According to RECIST",
        parameter="NUMBER",
        unit="percentage of participants",
    )
    result = classify_outcome(r)
    assert result.endpoint == "ORR"
    assert result.confident is True


def test_orr_synonym_does_not_match_isolated_cr_hematologic():
    """Negative near-miss: hematologic 'CR or CRi' (complete remission
    with incomplete count recovery) is NOT the same concept as RECIST
    ORR and must stay unclassified. This is a real ClinicalTrials.gov
    phrasing distinct from the ORR synonym pattern -- 'CRi' must not be
    matched by a pattern anchored on 'partial response'."""
    r = _mock_record(
        title="Complete Response Rate (CR or CRi) Per the National Comprehensive Cancer Network (NCCN) Guidelines",
        parameter="NUMBER",
        unit="percentage of participants",
    )
    result = classify_outcome(r)
    assert result.endpoint is None


def test_orr_synonym_does_not_match_isolated_complete_response_alone():
    """Negative near-miss: a title mentioning only 'Complete Response'
    with no partial-response counterpart must not be swept into ORR --
    isolated CR is a different (and narrower) measure than ORR."""
    r = _mock_record(title="Pathological Complete Response Rate", parameter="NUMBER", unit="percentage of participants")
    result = classify_outcome(r)
    assert result.endpoint is None


def test_orr_synonym_does_not_match_isolated_partial_response_alone():
    """Negative near-miss: isolated 'Partial Response' with no complete-
    response counterpart must not be swept into ORR."""
    r = _mock_record(title="Rate of Partial Response by Investigator Assessment", parameter="NUMBER", unit="percentage of participants")
    result = classify_outcome(r)
    assert result.endpoint is None


def test_os_year_based_fixed_timepoint_surviving_phrasing():
    """Real example: 'Percentage of Participants Surviving at 1 Year' /
    '2 Years' / '3 Years' -- never uses the words 'overall survival' or
    'OS', found via real-data validation 2026-08-14."""
    for years, expected_subtype in [("1 Year", "OS1yr"), ("2 Years", "OS2yr"), ("3 Years", "OS3yr")]:
        r = _mock_record(
            title=f"Percentage of Participants Surviving at {years}",
            parameter="NUMBER",
            unit="percentage of participants",
        )
        result = classify_outcome(r)
        assert result.endpoint == "OS", years
        assert result.subtype == expected_subtype, years
        assert result.confident is False, years


def test_os_year_based_timepoint_still_respects_followup_ceiling_guard():
    """Regression guard: the year-based extension must not reintroduce
    the session-4 follow-up-ceiling bug in years instead of months. A
    plain median OS title with a ceiling-phrased timeframe in YEARS
    must still classify as confident median OS, not a fixed-timepoint
    subtype."""
    r = _mock_record(
        title="Overall Survival (OS)",
        parameter="MEDIAN",
        unit="months",
        timeframe="Up to approximately 5 years",
    )
    result = classify_outcome(r)
    assert result.endpoint == "OS"
    assert result.subtype == "median_or_time_to_event"
    assert result.confident is True


def test_participants_surviving_without_timepoint_does_not_trigger_os():
    """Conservatism guard: the new 'participants surviving' synonym is
    gated on an actual detected timepoint. Without one, a bare survivor
    count must NOT be swept into OS at all (and certainly not into a
    confident median-OS classification, which would be scientifically
    wrong for a raw count)."""
    r = _mock_record(title="Number of Participants Surviving", parameter="NUMBER", unit="participants")
    result = classify_outcome(r)
    assert result.endpoint is None


def test_surviving_phrasing_requires_exact_anchor_not_bare_word():
    """Conservatism guard: a title using 'surviving' without the exact
    'participants surviving' idiom must not trigger OS via this
    synonym."""
    r = _mock_record(title="Number of Patients Surviving Surgery at 1 Year", parameter="NUMBER", unit="participants")
    result = classify_outcome(r)
    assert result.endpoint is None


def test_decimal_month_value_not_misparsed_as_smaller_integer_month():
    """Real bug found via this session's re-validation (NCT03602586):
    a decimal month value in a long descriptive timeframe ('The median
    follow-up time was 4.8 months.') was matched by the pre-existing
    month regex as if it said '8 months', producing a wrong PFS8
    subtype for what is actually a plain median PFS with no fixed
    timepoint at all. Fixed by the same decimal-guard lookbehind added
    for the year regex."""
    r = _mock_record(
        title="Progression-free Survival (PFS)",
        parameter="MEDIAN",
        unit="months",
        timeframe=(
            "Radiographic tumor assessments were completed 12 weeks after the start of "
            "treatment, then every 6 weeks for 49 weeks, followed by every 12 weeks until "
            "disease progression or treatment discontinuation. The median follow-up time "
            "was 4.8 months."
        ),
    )
    result = classify_outcome(r)
    assert result.endpoint == "PFS"
    assert result.subtype == "median_or_time_to_event"
    assert result.confident is True


def test_decimal_year_value_not_misparsed_as_smaller_integer_year():
    """Bug found while validating the year-based fix against real data
    (NCT01488487, 2026-08-14): timeframe '3.5 years' was being matched
    by a naive year regex as if it said '5 years' (the digit after the
    decimal point), producing a wrong OS5yr subtype for what is
    actually a 3.5-year follow-up duration, not a clean single-year
    fixed timepoint. A decimal timeframe with no other signal should
    not produce a fixed-timepoint subtype at all."""
    r = _mock_record(title="Overall Survival (OS)", parameter="MEDIAN", unit="months", timeframe="3.5 years")
    result = classify_outcome(r)
    assert result.endpoint == "OS"
    assert result.subtype == "median_or_time_to_event"
    assert result.confident is True


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
