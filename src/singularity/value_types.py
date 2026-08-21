"""
Infers a presentation-safe `value_type` ("count", "rate", "time", or
"other") from an OutcomeRecord's `parameter`/`unit` fields, WITHOUT any
database schema change.

WHY THIS EXISTS (read before changing)
----------------------------------------
Session 11's real-data validation found a genuine, demonstrated risk:
`outcome_records.value` is stored as a single DOUBLE PRECISION column
regardless of what kind of quantity it represents. Two real rows from
the same ingested dataset illustrate the danger directly:

  - NCT02360579, "Disease Assessment for Objective Response Rate":
    parameter=COUNT_OF_PARTICIPANTS, unit="Participants", value=23
    -> a RAW RESPONDER COUNT (the source's `denoms` field shows this
    group has 66 participants total; that denominator is not captured
    anywhere in this schema -- see docs/data_dictionary.md "Known
    limitation").
  - NCT02360579, "Safety Assesment":
    parameter=NUMBER, unit="Percentage of participants", value=92.9
    -> a genuine RATE.

Both rows live in the identical `outcome_records.value` column with
nothing structurally distinguishing them. A naive API/UI that renders
`value` directly (e.g. "23%") would silently misrepresent a count as a
rate. This module is the API-layer fix for that: a pure, testable
function computed at READ time from the existing `parameter`/`unit`
fields, with no schema or ingestion change. It does not create or
store new data -- it labels what's already there.

This does NOT solve the underlying data-completeness gap (the
denominator is still not captured, so a "count" value_type cannot be
turned into an actual rate by the API either) -- it only prevents a
count from being SILENTLY mislabeled as a rate. See
docs/data_dictionary.md for the full, still-open limitation.

RULES (in priority order, each grounded in a real example from the
session-11 validation dataset -- see the docstring of
`infer_value_type` for the exact evidence per rule)
"""

from __future__ import annotations

import re
from typing import Literal, Optional

ValueType = Literal["count", "rate", "time", "other"]

_RATE_UNIT_RE = re.compile(r"percentage|percent\b|\bpct\b|%", re.IGNORECASE)
_COUNT_UNIT_RE = re.compile(r"\b(participants?|subjects?|patients?)\b", re.IGNORECASE)
_TIME_UNIT_RE = re.compile(r"\b(months?|years?|weeks?|days?|hours?|minutes?)\b", re.IGNORECASE)
_COUNT_PARAMETER_RE = re.compile(r"count_of_participants", re.IGNORECASE)


def infer_value_type(parameter: Optional[str], unit: Optional[str]) -> ValueType:
    """Return "count", "rate", "time", or "other" for a given
    (parameter, unit) pair, computed from real ClinicalTrials.gov
    vocabulary observed in the session-11 validation dataset. Never
    raises -- unrecognized or missing input falls through to "other"
    rather than guessing.

    Rule 1 -- RATE: unit mentions "percentage"/"percent"/"%". Real
    example: parameter=NUMBER, unit="Percentage of participants",
    value=92.9 (NCT02360579, "Safety Assesment") -> genuine rate.
    Checked FIRST because "Percentage of participants" would otherwise
    also match the count-unit check below (it contains the word
    "participants") -- percentage must win that overlap.

    Rule 2 -- COUNT: parameter is COUNT_OF_PARTICIPANTS, OR unit is a
    bare people-counting word with no percentage qualifier. Real
    examples: parameter=COUNT_OF_PARTICIPANTS, unit="Participants",
    value=23 (NCT02360579, ORR-classified row -- the count-vs-rate risk
    this module exists to prevent); AND, independently, parameter=NUMBER,
    unit="participants" (bare, lowercase), value=13 (NCT01324323, TEAE
    row) -- confirms a bare people-counting unit means "count" even
    when parameter says NUMBER, not just when it says
    COUNT_OF_PARTICIPANTS.

    Rule 3 -- TIME: unit is a calendar/duration unit (months, years,
    weeks, days, hours, minutes) as a whole word. Real example:
    parameter=MEDIAN, unit="months", value=24.5 (median OS/PFS values
    throughout the validation dataset). Deliberately whole-word only --
    "L/hr" and "ng*hr/mL" (real PK units in this dataset) use the "hr"
    abbreviation, not the word "hour", and must NOT be classified as
    "time" (they're concentration/clearance units, correctly "other").

    Rule 4 -- OTHER (default): anything not matched above. Real
    examples: unit="ng/mL", "ng*hr/mL", "L/hr", "Liters" (PK
    concentration/clearance/volume units, NCT01324323).
    """
    unit_text = unit or ""
    parameter_text = parameter or ""

    if _RATE_UNIT_RE.search(unit_text):
        return "rate"
    if _COUNT_PARAMETER_RE.search(parameter_text) or (
        _COUNT_UNIT_RE.search(unit_text) and not _RATE_UNIT_RE.search(unit_text)
    ):
        return "count"
    if _TIME_UNIT_RE.search(unit_text):
        return "time"
    return "other"
