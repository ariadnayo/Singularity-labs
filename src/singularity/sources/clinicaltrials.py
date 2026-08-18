"""
ClinicalTrials.gov API v2 adapter.

Verified this session (2026-08-13) via a live, unauthenticated HTTPS
request: the API is public, requires no API key or credential, returns
JSON by default, and is rate-limited to roughly 50 requests/minute per
IP. Base URL: https://clinicaltrials.gov/api/v2/studies. Source:
https://clinicaltrials.gov/data-api/api (official documentation).

IMPORTANT ENVIRONMENT NOTE: the sandbox this adapter was written and
tested in cannot reach clinicaltrials.gov over the network (it is not
on the allowed egress list for the code-execution environment), so
this module's HTTP calls could not be exercised against the live API
from Python in that session. The adapter was verified correct against
a real, live sample of the API's JSON response fetched through a
separate tool with broader network access (see docs/autonomous_state.md
for the exact verification method and what was and wasn't tested).
Every test in tests/test_clinicaltrials_adapter.py therefore injects a
mock HTTP transport and is clearly labeled as using mock data.

No authentication is implemented here because none is required. If
ClinicalTrials.gov later requires an API key, that would need to be
added as an explicit credential requirement at that time -- it must
not be silently assumed now.
"""

from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Callable, Iterable, Optional

from ..schema import OutcomeRecord, Provenance, Trial

BASE_URL = "https://clinicaltrials.gov/api/v2/studies"
SOURCE_NAME = "clinicaltrials.gov"
API_VERSION = "v2"

# Documented rate limit is ~50 requests/minute per IP. Default to a
# conservative interval between paginated requests.
DEFAULT_MIN_INTERVAL_SECONDS = 1.5

HttpGet = Callable[[str], bytes]


def _default_http_get(url: str) -> bytes:
    """Real HTTP GET using only the standard library (no extra
    dependency). Not exercised in this sandbox session -- see module
    docstring -- but this is the actual implementation that will run
    in an environment with network access to clinicaltrials.gov.
    """
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:  # nosec - fixed public gov API host
        return resp.read()


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_request_url(
    *,
    query_cond: Optional[str] = None,
    query_term: Optional[str] = None,
    filter_overall_status: Optional[list[str]] = None,
    filter_ids: Optional[list[str]] = None,
    filter_advanced: Optional[str] = None,
    page_size: int = 50,
    page_token: Optional[str] = None,
) -> tuple[str, dict]:
    """Build the exact request URL and the query params dict used to
    build it, so both can be stored as provenance.

    `filter_advanced` accepts ClinicalTrials.gov's advanced filter
    syntax, e.g. `"AREA[HasResults]true"` to restrict to studies that
    have posted results (necessary for any real validation of
    `extract_outcome_records`, since studies without posted results
    have no `resultsSection` at all).
    """
    params: dict[str, str] = {"pageSize": str(page_size), "format": "json"}
    if query_cond:
        params["query.cond"] = query_cond
    if query_term:
        params["query.term"] = query_term
    if filter_overall_status:
        params["filter.overallStatus"] = ",".join(filter_overall_status)
    if filter_ids:
        params["filter.ids"] = ",".join(filter_ids)
    if filter_advanced:
        params["filter.advanced"] = filter_advanced
    if page_token:
        params["pageToken"] = page_token

    url = f"{BASE_URL}?{urllib.parse.urlencode(params)}"
    return url, params


def fetch_studies_page(
    *,
    query_cond: Optional[str] = None,
    query_term: Optional[str] = None,
    filter_overall_status: Optional[list[str]] = None,
    filter_ids: Optional[list[str]] = None,
    filter_advanced: Optional[str] = None,
    page_size: int = 50,
    page_token: Optional[str] = None,
    http_get: HttpGet = _default_http_get,
) -> dict:
    """Fetch a single page of studies. Returns the parsed JSON response
    plus provenance metadata under the `_provenance` key.

    Raises whatever the underlying `http_get` raises on network or
    HTTP errors -- this function does not swallow or silently retry
    errors, per Claude.md section 13 (fail loudly on infrastructure
    problems, don't guess).
    """
    url, params = build_request_url(
        query_cond=query_cond,
        query_term=query_term,
        filter_overall_status=filter_overall_status,
        filter_ids=filter_ids,
        filter_advanced=filter_advanced,
        page_size=page_size,
        page_token=page_token,
    )
    retrieved_at = _now_iso()
    raw_bytes = http_get(url)
    payload = json.loads(raw_bytes)
    payload["_provenance"] = {
        "source": SOURCE_NAME,
        "api_version": API_VERSION,
        "retrieved_at": retrieved_at,
        "request_url": url,
        "query_params": params,
    }
    return payload


def iter_all_studies(
    *,
    query_cond: Optional[str] = None,
    query_term: Optional[str] = None,
    filter_overall_status: Optional[list[str]] = None,
    filter_ids: Optional[list[str]] = None,
    filter_advanced: Optional[str] = None,
    page_size: int = 50,
    max_pages: Optional[int] = None,
    min_interval_seconds: float = DEFAULT_MIN_INTERVAL_SECONDS,
    http_get: HttpGet = _default_http_get,
    sleep: Callable[[float], None] = time.sleep,
) -> Iterable[dict]:
    """Page through all matching studies, yielding each raw study dict
    (with `_page_provenance` attached to every study for traceability).
    Respects the documented rate limit by sleeping between requests.
    """
    page_token: Optional[str] = None
    pages_fetched = 0
    while True:
        page = fetch_studies_page(
            query_cond=query_cond,
            query_term=query_term,
            filter_overall_status=filter_overall_status,
            filter_ids=filter_ids,
            filter_advanced=filter_advanced,
            page_size=page_size,
            page_token=page_token,
            http_get=http_get,
        )
        page_provenance = page["_provenance"]
        for study in page.get("studies", []):
            study["_page_provenance"] = page_provenance
            yield study

        pages_fetched += 1
        page_token = page.get("nextPageToken")
        if not page_token:
            break
        if max_pages is not None and pages_fetched >= max_pages:
            break
        if min_interval_seconds > 0:
            sleep(min_interval_seconds)


def _parse_measurement_value(raw: Optional[str]) -> Optional[float]:
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def extract_outcome_records(study: dict) -> list[OutcomeRecord]:
    """Map one raw ClinicalTrials.gov study record onto OutcomeRecord
    instances, one per (outcome measure, arm/group, category)
    combination actually reported in resultsSection.outcomeMeasuresModule.

    Studies with hasResults=False, or with no outcomeMeasuresModule,
    contribute no records -- this is expected and correct, not an
    error: most registered trials have not posted results.

    Every returned record carries `provenance.raw` set to the raw
    outcome-measure dict it came from, so the mapping can be audited
    or re-derived.

    This function's return type (list[OutcomeRecord], no skip
    information) is unchanged since it was first written -- existing
    callers/tests are unaffected. For a variant that also reports which
    outcome measures were skipped and why (needed by the Phase 2B
    ingestion pipeline's "do not silently discard malformed records"
    requirement), see `extract_outcome_records_verbose`, added
    2026-08-14 (session 10). Both call the same internal
    implementation, so behavior is guaranteed identical -- verified by
    the full test suite passing unchanged after this refactor.
    """
    records, _skipped = _extract_outcome_records_impl(study)
    return records


def extract_outcome_records_verbose(study: dict) -> "tuple[list[OutcomeRecord], list[dict]]":
    """Same mapping as `extract_outcome_records`, but also returns a
    list of skip records (each a dict with `nct_id`, `reason`, and the
    raw outcome-measure dict that was skipped) for outcome measures
    that could not become a valid OutcomeRecord (currently: missing
    title). Added for the ingestion pipeline's reporting requirement --
    see `singularity.pipeline`.
    """
    return _extract_outcome_records_impl(study)


def _extract_outcome_records_impl(study: dict) -> "tuple[list[OutcomeRecord], list[dict]]":
    protocol = study.get("protocolSection", {})
    nct_id = protocol.get("identificationModule", {}).get("nctId")
    if not nct_id:
        # A study record without an NCT ID is not usable -- do not
        # guess one.
        return [], []

    provenance_meta = study.get("_page_provenance", {})
    results = study.get("resultsSection", {})
    outcome_module = results.get("outcomeMeasuresModule", {})
    outcome_measures = outcome_module.get("outcomeMeasures", [])

    records: list[OutcomeRecord] = []
    skipped: list[dict] = []
    for om in outcome_measures:
        title = om.get("title")
        if not title:
            # Cannot build a valid OutcomeRecord without a title; skip
            # and do not fabricate one. Reported, not silently dropped.
            skipped.append({"nct_id": nct_id, "reason": "missing title", "raw_outcome_measure": om})
            continue
        parameter = om.get("paramType")
        unit = om.get("unitOfMeasure")
        timeframe = om.get("timeFrame")

        group_titles = {g.get("id"): g.get("title") for g in om.get("groups", [])}

        for cls in om.get("classes", []):
            for category in cls.get("categories", []):
                for measurement in category.get("measurements", []):
                    group_id = measurement.get("groupId")
                    group_title = group_titles.get(group_id, group_id)
                    value = _parse_measurement_value(measurement.get("value"))

                    provenance = Provenance(
                        source=SOURCE_NAME,
                        source_record_id=nct_id,
                        retrieved_at=provenance_meta.get("retrieved_at", ""),
                        request_url=provenance_meta.get("request_url", ""),
                        query_params=provenance_meta.get("query_params", {}),
                        raw={"outcome_measure": om, "measurement": measurement},
                    )

                    records.append(
                        OutcomeRecord(
                            nct_id=nct_id,
                            title=title,
                            parameter=parameter,
                            unit=unit,
                            timeframe=timeframe,
                            group=group_title,
                            value=value,
                            provenance=provenance,
                        )
                    )
    return records, skipped



def extract_trial(study: dict) -> Optional[Trial]:
    """Map one raw ClinicalTrials.gov study record onto a `Trial`
    (protocol-level metadata), distinct from its outcome measurements.

    FIELD-VERIFICATION STATUS (see also the `Trial` docstring in
    schema.py): only `protocolSection.identificationModule.nctId` has
    been independently verified against a live API response in this
    project. The other fields mapped below
    (`statusModule.overallStatus`, `statusModule.startDateStruct.date`,
    `statusModule.completionDateStruct.date`,
    `designModule.studyType`, `designModule.phases`,
    `sponsorCollaboratorsModule.leadSponsor.name`,
    `conditionsModule.conditions`,
    `armsInterventionsModule.interventions[].name`,
    `designModule.enrollmentInfo.count`) use the publicly documented
    ClinicalTrials.gov API v2 schema, but were not re-verified against
    a fresh live response in the session that wrote this function
    (web-fetch tooling was unavailable). Spot-check against a real
    response before trusting these fields at scale. Every access below
    uses `.get()` with a `None` default rather than assuming presence,
    so a schema mismatch produces a missing field, not a crash or a
    fabricated value.

    Returns None (does not fabricate a Trial) if the study has no
    NCT ID -- the one field this project has actually verified live.
    """
    protocol = study.get("protocolSection", {})
    identification = protocol.get("identificationModule", {})
    nct_id = identification.get("nctId")
    if not nct_id:
        return None

    status = protocol.get("statusModule", {})
    design = protocol.get("designModule", {})
    sponsor_module = protocol.get("sponsorCollaboratorsModule", {})
    conditions_module = protocol.get("conditionsModule", {})
    arms_module = protocol.get("armsInterventionsModule", {})

    lead_sponsor = sponsor_module.get("leadSponsor", {})
    interventions_raw = arms_module.get("interventions", [])
    interventions = [i.get("name") for i in interventions_raw if i.get("name")] or None

    conditions = conditions_module.get("conditions") or None

    phases = design.get("phases") or None

    enrollment_info = design.get("enrollmentInfo", {})
    enrollment_count = enrollment_info.get("count")

    provenance_meta = study.get("_page_provenance", {})
    provenance = Provenance(
        source=SOURCE_NAME,
        source_record_id=nct_id,
        retrieved_at=provenance_meta.get("retrieved_at", ""),
        request_url=provenance_meta.get("request_url", ""),
        query_params=provenance_meta.get("query_params", {}),
        raw={
            "identificationModule": identification,
            "statusModule": status,
            "designModule": design,
            "sponsorCollaboratorsModule": sponsor_module,
            "conditionsModule": conditions_module,
        },
    )

    return Trial(
        nct_id=nct_id,
        brief_title=identification.get("briefTitle"),
        official_title=identification.get("officialTitle"),
        overall_status=status.get("overallStatus"),
        phases=phases,
        study_type=design.get("studyType"),
        conditions=conditions,
        lead_sponsor=lead_sponsor.get("name"),
        interventions=interventions,
        start_date=(status.get("startDateStruct") or {}).get("date"),
        completion_date=(status.get("completionDateStruct") or {}).get("date"),
        enrollment_count=enrollment_count,
        provenance=provenance,
    )


class ClinicalTrialsAdapter:
    """Concrete adapter implementing the `DataSourceAdapter` shape
    from `singularity.sources.base`.
    """

    source_name = SOURCE_NAME

    def __init__(self, http_get: HttpGet = _default_http_get, sleep: Callable[[float], None] = time.sleep):
        self._http_get = http_get
        self._sleep = sleep

    def iter_studies(
        self,
        *,
        query_cond: Optional[str] = None,
        query_term: Optional[str] = None,
        filter_overall_status: Optional[list[str]] = None,
        filter_ids: Optional[list[str]] = None,
        filter_advanced: Optional[str] = None,
        page_size: int = 50,
        max_pages: Optional[int] = None,
    ) -> Iterable[dict]:
        """Yield raw study dicts (with `_page_provenance` attached),
        using this adapter's configured transport/rate-limit settings.

        Added for `singularity.pipeline`, which needs both `Trial` and
        `OutcomeRecord` data from the SAME fetch -- calling
        `fetch_trials()` and `fetch_outcome_records()` separately would
        page through the API twice for no reason. Both of those methods
        remain available independently for callers who only want one or
        the other.
        """
        yield from iter_all_studies(
            query_cond=query_cond,
            query_term=query_term,
            filter_overall_status=filter_overall_status,
            filter_ids=filter_ids,
            filter_advanced=filter_advanced,
            page_size=page_size,
            max_pages=max_pages,
            http_get=self._http_get,
            sleep=self._sleep,
        )

    def fetch_outcome_records(
        self,
        *,
        query_cond: Optional[str] = None,
        query_term: Optional[str] = None,
        filter_overall_status: Optional[list[str]] = None,
        filter_ids: Optional[list[str]] = None,
        filter_advanced: Optional[str] = None,
        page_size: int = 50,
        max_pages: Optional[int] = None,
    ) -> list[OutcomeRecord]:
        records: list[OutcomeRecord] = []
        for study in iter_all_studies(
            query_cond=query_cond,
            query_term=query_term,
            filter_overall_status=filter_overall_status,
            filter_ids=filter_ids,
            filter_advanced=filter_advanced,
            page_size=page_size,
            max_pages=max_pages,
            http_get=self._http_get,
            sleep=self._sleep,
        ):
            records.extend(extract_outcome_records(study))
        return records

    def fetch_trials(
        self,
        *,
        query_cond: Optional[str] = None,
        query_term: Optional[str] = None,
        filter_overall_status: Optional[list[str]] = None,
        filter_ids: Optional[list[str]] = None,
        filter_advanced: Optional[str] = None,
        page_size: int = 50,
        max_pages: Optional[int] = None,
    ) -> list[Trial]:
        """Fetch protocol-level Trial records (not outcome measurements
        -- see `fetch_outcome_records` for those). A study missing an
        NCT ID is skipped (`extract_trial` returns None for it), not
        fabricated.
        """
        trials: list[Trial] = []
        for study in iter_all_studies(
            query_cond=query_cond,
            query_term=query_term,
            filter_overall_status=filter_overall_status,
            filter_ids=filter_ids,
            filter_advanced=filter_advanced,
            page_size=page_size,
            max_pages=max_pages,
            http_get=self._http_get,
            sleep=self._sleep,
        ):
            trial = extract_trial(study)
            if trial is not None:
                trials.append(trial)
        return trials
