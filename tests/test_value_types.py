"""
Tests for singularity.value_types.infer_value_type.

Every case here is grounded in an actual (parameter, unit) pair from
the session-11 real ClinicalTrials.gov validation dataset (109 rows,
10 real studies) -- see value_types.py's module docstring for the
full rationale and exact provenance of each rule.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from singularity.value_types import infer_value_type


def test_percentage_of_participants_is_rate():
    """Real: NCT02360579 'Safety Assesment', parameter=NUMBER,
    unit='Percentage of participants', value=92.9 -- a genuine rate."""
    assert infer_value_type("NUMBER", "Percentage of participants") == "rate"


def test_percentage_case_insensitive_and_symbol_variants():
    assert infer_value_type("NUMBER", "percentage of participants") == "rate"
    assert infer_value_type("NUMBER", "Percent") == "rate"
    assert infer_value_type("NUMBER", "%") == "rate"


def test_count_of_participants_parameter_with_bare_unit_is_count():
    """Real: NCT02360579 ORR-classified row, parameter=COUNT_OF_PARTICIPANTS,
    unit='Participants', value=23 -- the exact count-vs-rate risk this
    module exists to prevent. This is a raw responder count, not a
    rate; the source's denominator (66) is not captured (see
    docs/data_dictionary.md)."""
    assert infer_value_type("COUNT_OF_PARTICIPANTS", "Participants") == "count"


def test_bare_participants_unit_is_count_even_with_number_parameter():
    """Real: NCT01324323 TEAE row, parameter=NUMBER, unit='participants'
    (bare, lowercase, no percentage qualifier), value=13 -- confirms a
    bare people-counting unit means count regardless of parameter."""
    assert infer_value_type("NUMBER", "participants") == "count"


def test_subjects_and_patients_also_count_as_people_units():
    assert infer_value_type("NUMBER", "subjects") == "count"
    assert infer_value_type("NUMBER", "patients") == "count"


def test_median_months_is_time():
    """Real: median OS/PFS rows throughout the dataset, parameter=MEDIAN,
    unit='months'."""
    assert infer_value_type("MEDIAN", "months") == "time"


def test_years_weeks_days_hours_minutes_are_time():
    for unit in ["years", "weeks", "days", "hours", "minutes"]:
        assert infer_value_type("MEDIAN", unit) == "time", unit


def test_pk_concentration_and_clearance_units_are_other_not_time():
    """Real: NCT01324323 PK rows. Critically, 'L/hr' and 'ng*hr/mL' use
    the 'hr' ABBREVIATION, not the word 'hour' -- must NOT be
    classified as time (they're concentration/clearance units)."""
    assert infer_value_type("GEOMETRIC_MEAN", "ng/mL") == "other"
    assert infer_value_type("GEOMETRIC_MEAN", "ng*hr/mL") == "other"
    assert infer_value_type("GEOMETRIC_MEAN", "L/hr") == "other"
    assert infer_value_type("GEOMETRIC_MEAN", "Liters") == "other"


def test_spelled_out_hours_is_still_time_even_in_pk_context():
    """Real: NCT01324323 Tmax row, parameter=MEDIAN, unit='hours'
    (spelled out, not abbreviated) -- genuinely a time duration, even
    though it's a PK measure conceptually. value_type is about
    presentation safety (don't show a duration as a percentage), not
    clinical endpoint categorization."""
    assert infer_value_type("MEDIAN", "hours") == "time"


def test_missing_parameter_or_unit_falls_back_to_other_not_error():
    assert infer_value_type(None, None) == "other"
    assert infer_value_type("MEDIAN", None) == "other"
    assert infer_value_type(None, "months") == "time"


def test_rate_check_wins_over_count_check_for_overlapping_unit_text():
    """'Percentage of participants' contains the word 'participants',
    which would also match the count-unit pattern -- rate must win
    this overlap, checked first deliberately."""
    assert infer_value_type("NUMBER", "Percentage of participants") == "rate"
