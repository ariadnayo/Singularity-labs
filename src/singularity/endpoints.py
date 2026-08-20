"""
Endpoint classification for raw clinical outcome records.

Implements the rules in docs/data_dictionary.md and docs/architecture.md:

- Canonical endpoint categories are PFS, OS, ORR, DOR, DFS.
- Fixed-timepoint rates (PFS6, PFS12, OS6, OS12, OS24, DFS-at-timepoint)
  are RELATED to but NOT equivalent to the canonical median/time-to-event
  endpoint. They are returned with a `subtype` and `confident=False` so
  downstream consumers can decide how to handle them -- they are never
  silently folded into the canonical bucket.
- Duration of Response (DOR) must never be classified as ORR merely
  because a title contains "response".
- Ambiguous or related-but-distinct measures (disease control rate,
  clinical benefit rate, time to progression, quality-of-life outcomes,
  adverse events, event-free survival, pathological complete response,
  best overall response, survival rate without a clear canonical
  anchor) are left unclassified (endpoint=None) rather than guessed
  into a category.

This module does not fabricate or assume data. It only classifies
records that are passed to it.
"""

from __future__ import annotations

import re

from .schema import ClassificationResult, OutcomeRecord

# Identifies which version of the classification logic produced a
# given ClassificationResult, so results persisted to a database (see
# db/migrations/0003_create_endpoint_classifications.sql, Phase 2A) can
# be tied to a specific classifier version rather than silently mixing
# results from different sessions' fixes. Bump this string whenever
# classify_outcome's logic changes in a way that could change output
# (not for comment-only or docstring-only edits). Purely additive
# metadata -- does not change any classification behavior.
CLASSIFIER_VERSION = "2026-08-14-session8"

# Related-but-distinct measures that must never be silently mapped to a
# canonical endpoint, per docs/data_dictionary.md.
_NON_CANONICAL_PATTERNS = [
    r"\bdisease control rate\b",
    r"\bdcr\b",
    r"\bclinical benefit rate\b",
    r"\bcbr\b",
    r"\btime to progression\b",
    r"\btime to local progression\b",
    r"\bttp\b",
    r"\bquality of life\b",
    r"\bqol\b",
    r"\badverse events?\b",
    r"\bteaes?\b",
    # Session 11 fix (2026-08-14, see docs/autonomous_state.md): the
    # original pattern was singular-only (`adverse event`, no `s?`).
    # In a real 109-row validation sample, every actual occurrence of
    # AE language used the plural ("Adverse Events", "TEAEs") -- a 0%
    # real-world hit rate for the old pattern. Classification outcome
    # was unaffected (fell through to the generic unclassified catch-
    # all either way), but the exclusion reason wasn't the intended,
    # documented one. `teaes?` is a standalone abbreviation pattern for
    # titles that use only "TEAE"/"TEAEs" without spelling out "adverse
    # events" nearby.
    # Added 2026-08-14 (session 8), per human-approved taxonomy analysis
    # (docs/endpoint_taxonomy_analysis.md). These were already correctly
    # left unclassified before this change -- no pattern matched them --
    # this makes that exclusion explicit and documented instead of an
    # accidental non-match, per the approved decision. Endpoint output
    # is unchanged; only the classification `reason` becomes specific.
    r"\bevent[\s-]free survival\b",  # EFS -- related to DFS but NOT
    # equivalent: EFS's "event" definition is protocol-specific and
    # typically broader than DFS's disease-recurrence-specific framing
    # (may include any progression, second malignancy, or death).
    r"\befs\b",
    r"\bpathological complete response\b",  # pCR -- related to ORR but
    r"\bpathologic complete response\b",  # NOT equivalent: assessed via
    r"\btpcr\b",  # post-surgical pathology, not RECIST imaging-based
    r"\bbpcr\b",  # tumor-shrinkage criteria. Deliberately not matching a
    r"\btotal pcr\b",  # bare "pcr" -- that abbreviation collides with the
    # unrelated molecular-biology assay "PCR" (polymerase chain
    # reaction) and would produce a misleading `reason` string even
    # though the classification outcome (unclassified) would be the same.
    r"\bbest overall response\b",  # BOR -- related to ORR but NOT
    # equivalent: BOR is a categorical per-subject classification
    # (CR/PR/SD/PD/NE), not itself a numeric response rate. Deliberately
    # not matching a bare "bor" for the same false-positive-labeling
    # reason as bare "pcr" above.
]

# Non-efficacy measures: pharmacokinetic (PK) and generic safety
# assessments. Kept in a SEPARATE list from _NON_CANONICAL_PATTERNS
# above, deliberately: DCR/CBR/TTP/QoL/AE/EFS/pCR/BOR are measures that
# could plausibly be confused with a canonical efficacy endpoint (that
# is precisely why they need an explicit exclusion). PK and safety
# measures were never at risk of that confusion -- a PK or safety
# title never superficially resembles "objective response rate" or
# "progression-free survival". This is a categorically different kind
# of exclusion (out-of-scope-by-definition vs. related-but-distinct),
# so it gets its own list and its own, more accurate reason string
# rather than diluting the meaning of the list above.
#
# Added 2026-08-14 (session 11), grounded in the real 109-row
# validation dataset (docs/autonomous_state.md "Session 11 Summary")
# -- every pattern below is copied from an actual real title, not
# speculative. Deliberately does NOT include a bare `\bsafety\b`
# pattern: a genuine combined title (e.g. "Safety and Efficacy:
# Progression-Free Survival") could contain that word without being a
# safety-only measure, and the two real safety titles found both
# matched a specific, unambiguous whole phrase anyway.
_NON_EFFICACY_PATTERNS = [
    # Pharmacokinetic (PK) measures -- from a real Phase 1 PK study
    # (NCT01324323): AUC/Cmax/Tmax measures all contain "plasma
    # concentration"; half-life, clearance, and volume of distribution
    # are each unambiguous, PK-exclusive terms.
    r"\bplasma concentration\b",
    r"\bhalf-life\b",
    r"\bplasma clearance\b",
    r"\bvolume of distribution\b",
    r"\bauc\b",
    r"\bcmax\b",
    r"\btmax\b",
    # Generic safety assessment titles -- from two real trials
    # (NCT02044380, NCT02360579). "safety assess?ment" matches both the
    # correct spelling and the real source's typo ("Safety Assesment",
    # verified in provenance_raw, not a transcription error on our
    # side) via the optional second "s".
    r"\bsafety assess?ment\b",
    r"\bsafety profile\b",
]

_FIXED_TIMEPOINT_MONTH_RE = re.compile(r"(?<![\d.])(\d{1,3})[\s-]?month", re.IGNORECASE)
_FIXED_TIMEPOINT_YEAR_RE = re.compile(r"(?<![\d.])(\d{1,3})[\s-]?year", re.IGNORECASE)

# Explicit, context-anchored synonyms for ORR (CR+PR rate under RECIST or
# equivalent criteria is the clinical definition of ORR). Deliberately
# NOT a bare "CR" or "PR" match -- each pattern requires both concepts
# to appear together, joined as a response-rate phrase, so an isolated
# mention of "CR" (e.g. hematologic "CR or CRi") elsewhere in a title
# does not trigger this. Found via real-data validation 2026-08-14 (see
# docs/autonomous_state.md): 22 real ClinicalTrials.gov rows used one of
# these phrasings instead of the literal words "objective response rate".
_ORR_SYNONYM_PATTERNS = [
    r"\bcomplete and partial response rate\b",
    r"\bobjective tumor response rate\b",
    r"\bcomplete or partial (objective )?(tumor )?response\b",
    r"\bcomplete response\s*[\[\(]?cr[\]\)]?\s*(or|and)\s*partial response\s*[\[\(]?pr[\]\)]?\b",
]


def _matches_any(patterns: list[str], text: str) -> bool:
    return any(re.search(p, text, re.IGNORECASE) for p in patterns)


def _fixed_timepoint_suffix(record: OutcomeRecord) -> "str | None":
    """Return a subtype suffix (e.g. '6' for 6 months, '1yr' for 1 year)
    if the title, or an unambiguous timeframe, indicates a fixed-
    timepoint measurement (e.g. 'at 6 months', 'at 1 Year'), else None.

    Month and year suffixes are deliberately formatted differently
    ('6' vs '1yr') so a downstream consumer can never confuse OS6
    (6 months) with a hypothetical OS6 meaning 6 years -- the year
    variant is always explicit.

    BUG FOUND during real-data validation (2026-08-13, see
    docs/autonomous_state.md): a real ClinicalTrials.gov trial
    (NCT07227597) had a plain "Progression-Free Survival (PFS)" title
    with timeframe "Up to approximately 58 months" -- boilerplate
    describing the study's overall follow-up ceiling, which applies to
    nearly every outcome in the trial, not a per-outcome fixed
    timepoint. Fix: only trust the title for this signal; the
    timeframe field is only used as a fallback, and only when it is
    NOT phrased as a maximum/ceiling ("up to ...", "approximately
    ..."). This guard applies equally to the year-based pattern added
    2026-08-14, to avoid reintroducing the same bug in years instead
    of months.

    SECOND VARIANT FOUND (2026-08-14, session 11, see
    docs/autonomous_state.md): a real trial (NCT02360579) used the
    phrase "...for a maximum of 60 months" for the identical ceiling
    concept -- not caught by the original "up to"/"approximately"
    guard, causing 3 real median-PFS values to be wrongly downgraded
    to a low-confidence PFS6 subtype. Fixed by adding "maximum of" to
    the guard. Note "for up to ..." and "for a period of up to ..."
    (other phrasings considered) already contain the literal substring
    "up to" and were already covered by the existing guard -- no
    separate pattern was needed for those.
    """
    m = _FIXED_TIMEPOINT_MONTH_RE.search(record.title)
    if m:
        return m.group(1)
    y = _FIXED_TIMEPOINT_YEAR_RE.search(record.title)
    if y:
        return f"{y.group(1)}yr"

    timeframe = record.timeframe or ""
    if re.search(r"\bup to\b|\bapproximately\b|\bmaximum of\b", timeframe, re.IGNORECASE):
        return None
    m = _FIXED_TIMEPOINT_MONTH_RE.search(timeframe)
    if m:
        return m.group(1)
    y = _FIXED_TIMEPOINT_YEAR_RE.search(timeframe)
    if y:
        return f"{y.group(1)}yr"
    return None


def classify_outcome(record: OutcomeRecord) -> ClassificationResult:
    """Classify a single raw outcome record.

    Returns a ClassificationResult. `endpoint` is None whenever the
    record cannot be safely assigned to a canonical category -- callers
    must not treat a None result as an error, it is an expected and
    important outcome of conservative classification.
    """
    title = record.title or ""
    unit = (record.unit or "").lower()

    # 1. Explicitly non-canonical / related measures -> never classify.
    if _matches_any(_NON_CANONICAL_PATTERNS, title):
        return ClassificationResult(
            endpoint=None,
            subtype=None,
            confident=False,
            reason=(
                "Title matches a related-but-distinct measure "
                "(e.g. DCR, CBR, TTP, QoL, AE, EFS, pCR, BOR) that must "
                "not be folded into a canonical endpoint per "
                "data_dictionary.md."
            ),
        )

    # 1b. Non-efficacy measures (PK, generic safety) -> never classify.
    # Separate from the check above: these were never at risk of being
    # confused with a canonical efficacy endpoint, they're simply
    # outside the PFS/OS/ORR/DOR/DFS taxonomy by definition. See
    # _NON_EFFICACY_PATTERNS above for why this is a distinct list.
    if _matches_any(_NON_EFFICACY_PATTERNS, title):
        return ClassificationResult(
            endpoint=None,
            subtype=None,
            confident=False,
            reason=(
                "Title matches a pharmacokinetic or generic safety "
                "measure, which is outside the PFS/OS/ORR/DOR/DFS "
                "efficacy-endpoint taxonomy by definition."
            ),
        )

    # 2. Duration of Response must not be caught by generic "response"
    #    matching for ORR.
    if re.search(r"\bduration of (objective )?response\b", title, re.IGNORECASE) or re.search(
        r"\bdor\b", title, re.IGNORECASE
    ):
        return ClassificationResult(
            endpoint="DOR",
            subtype=None,
            confident=True,
            reason="Title explicitly refers to duration of response.",
        )

    fixed_month = _fixed_timepoint_suffix(record)

    # 3. PFS family.
    if re.search(r"\bprogression[\s-]free survival\b|\bpfs\b", title, re.IGNORECASE):
        if fixed_month or "probability" in title.lower() or "probability" in unit or "rate" in title.lower():
            return ClassificationResult(
                endpoint="PFS",
                subtype=f"PFS{fixed_month}" if fixed_month else "PFS_rate",
                confident=False,
                reason=(
                    "Fixed-timepoint or probability/rate PFS measure "
                    "(e.g. PFS6/PFS12) is not equivalent to median PFS "
                    "and is flagged as a subtype rather than treated as "
                    "the canonical median PFS endpoint."
                ),
            )
        return ClassificationResult(
            endpoint="PFS",
            subtype="median_or_time_to_event",
            confident=True,
            reason="Title refers to progression-free survival without a fixed-timepoint/rate qualifier.",
        )

    # 4. OS family. In addition to explicit "overall survival"/"OS"
    # wording, "Percentage of Participants Surviving at N Year(s)" is a
    # real, recurring ClinicalTrials.gov phrasing for a fixed-timepoint
    # OS rate that never uses the words "overall survival" or "OS" at
    # all (found via real-data validation 2026-08-14). This synonym is
    # deliberately gated on an actual detected fixed timepoint --
    # "Number of Participants Surviving" with no timepoint number must
    # NOT fall through to a confident median-OS classification, since a
    # bare survivor count is not a median survival time. Anchored to
    # the specific idiom "participants surviving" rather than a bare
    # "surviving" to avoid over-matching unrelated titles.
    mentions_participants_surviving = bool(re.search(r"\bparticipants surviving\b", title, re.IGNORECASE))
    has_title_timepoint = bool(_FIXED_TIMEPOINT_MONTH_RE.search(title) or _FIXED_TIMEPOINT_YEAR_RE.search(title))
    is_surviving_at_timepoint = mentions_participants_surviving and has_title_timepoint

    if (
        re.search(r"\boverall survival\b|\bos\b", title, re.IGNORECASE) or is_surviving_at_timepoint
    ) and "response" not in title.lower():
        if fixed_month or "rate" in title.lower() or "probability" in unit:
            return ClassificationResult(
                endpoint="OS",
                subtype=f"OS{fixed_month}" if fixed_month else "OS_rate",
                confident=False,
                reason=(
                    "Fixed-timepoint or rate-based OS measure is not "
                    "equivalent to median OS and is flagged as a subtype."
                ),
            )
        return ClassificationResult(
            endpoint="OS",
            subtype="median_or_time_to_event",
            confident=True,
            reason="Title refers to overall survival without a fixed-timepoint/rate qualifier.",
        )

    # 5. DFS family.
    if re.search(r"\bdisease[\s-]free survival\b|\bdfs\b", title, re.IGNORECASE):
        if fixed_month or "rate" in title.lower():
            return ClassificationResult(
                endpoint="DFS",
                subtype=f"DFS{fixed_month}" if fixed_month else "DFS_rate",
                confident=False,
                reason="Fixed-timepoint/rate DFS measure flagged as a subtype, not median DFS.",
            )
        return ClassificationResult(
            endpoint="DFS",
            subtype="median_or_time_to_event",
            confident=True,
            reason="Title refers to disease-free survival without a fixed-timepoint/rate qualifier.",
        )

    # 6. ORR: literal mentions, or an explicit CR+PR/RECIST synonym
    #    (checked after DOR/DCR/CBR/TTP exclusions above, so a hematologic
    #    "CR or CRi" title etc. never reaches this branch).
    if re.search(r"\bobjective response rate\b|\boverall response rate\b|\borr\b", title, re.IGNORECASE):
        return ClassificationResult(
            endpoint="ORR",
            subtype=None,
            confident=True,
            reason="Title explicitly refers to objective/overall response rate.",
        )
    if _matches_any(_ORR_SYNONYM_PATTERNS, title):
        return ClassificationResult(
            endpoint="ORR",
            subtype=None,
            confident=True,
            reason=(
                "Title uses an explicit CR+PR/RECIST-defined response-rate "
                "synonym for ORR (e.g. 'Complete and Partial Response Rate "
                "... RECIST ...'), not the literal words 'objective/overall "
                "response rate' -- recognized as an equivalent phrasing, "
                "not inferred."
            ),
        )

    # 7. Nothing matched -> unclassified. Do not guess.
    return ClassificationResult(
        endpoint=None,
        subtype=None,
        confident=False,
        reason="No canonical endpoint pattern matched; left unclassified rather than guessed.",
    )


def classify_batch(records: list[OutcomeRecord]) -> list[ClassificationResult]:
    """Classify many records and return results in the same order."""
    return [classify_outcome(r) for r in records]


def summarize(results: list[ClassificationResult]) -> dict:
    """Produce the audit summary required by Claude.md section 9:
    total rows, classified rows, unclassified rows, counts by endpoint,
    and count of low-confidence (subtype-flagged) classifications.
    """
    total = len(results)
    unclassified = sum(1 for r in results if r.endpoint is None)
    by_endpoint: dict[str, int] = {}
    low_confidence = 0
    for r in results:
        if r.endpoint:
            by_endpoint[r.endpoint] = by_endpoint.get(r.endpoint, 0) + 1
            if not r.confident:
                low_confidence += 1
    return {
        "total_rows": total,
        "classified_rows": total - unclassified,
        "unclassified_rows": unclassified,
        "counts_by_endpoint": by_endpoint,
        "low_confidence_classifications": low_confidence,
    }
