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
  adverse events, survival rate without a clear canonical anchor) are
  left unclassified (endpoint=None) rather than guessed into a category.

This module does not fabricate or assume data. It only classifies
records that are passed to it.
"""

from __future__ import annotations

import re

from .schema import ClassificationResult, OutcomeRecord

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
    r"\badverse event\b",
]

_FIXED_TIMEPOINT_RE = re.compile(r"\b(\d{1,3})[\s-]?month", re.IGNORECASE)


def _matches_any(patterns: list[str], text: str) -> bool:
    return any(re.search(p, text, re.IGNORECASE) for p in patterns)


def _fixed_timepoint_months(record: OutcomeRecord) -> "str | None":
    """Return e.g. '6' if the title or timeframe indicates a fixed
    timepoint measurement (e.g. 'at 6 months'), else None."""
    for field in (record.title, record.timeframe or ""):
        m = _FIXED_TIMEPOINT_RE.search(field)
        if m:
            return m.group(1)
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
                "(e.g. DCR, CBR, TTP, QoL, AE) that must not be folded "
                "into a canonical endpoint per data_dictionary.md."
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

    fixed_month = _fixed_timepoint_months(record)

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

    # 4. OS family.
    if re.search(r"\boverall survival\b|\bos\b", title, re.IGNORECASE) and "response" not in title.lower():
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

    # 6. ORR (checked after DOR/DCR/CBR/TTP exclusions above).
    if re.search(r"\bobjective response rate\b|\boverall response rate\b|\borr\b", title, re.IGNORECASE):
        return ClassificationResult(
            endpoint="ORR",
            subtype=None,
            confident=True,
            reason="Title explicitly refers to objective/overall response rate.",
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
