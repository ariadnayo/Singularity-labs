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

from ..schema import OutcomeRecord, Provenance

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
    """
    protocol = study.get("protocolSection", {})
    nct_id = protocol.get("identificationModule", {}).get("nctId")
    if not nct_id:
        # A study record without an NCT ID is not usable -- do not
        # guess one.
        return []

    provenance_meta = study.get("_page_provenance", {})
    results = study.get("resultsSection", {})
    outcome_module = results.get("outcomeMeasuresModule", {})
    outcome_measures = outcome_module.get("outcomeMeasures", [])

    records: list[OutcomeRecord] = []
    for om in outcome_measures:
        title = om.get("title")
        if not title:
            # Cannot build a valid OutcomeRecord without a title; skip
            # and do not fabricate one.
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
    return records


class ClinicalTrialsAdapter:
    """Concrete adapter implementing the `DataSourceAdapter` shape
    from `singularity.sources.base`.
    """

    source_name = SOURCE_NAME

    def __init__(self, http_get: HttpGet = _default_http_get, sleep: Callable[[float], None] = time.sleep):
        self._http_get = http_get
        self._sleep = sleep

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
