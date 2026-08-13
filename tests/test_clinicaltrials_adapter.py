"""
Tests for singularity.sources.clinicaltrials.

CRITICAL: every fixture in this file is SYNTHETIC / MOCK data written
by hand to match the real ClinicalTrials.gov API v2 JSON shape (which
was verified live and separately -- see docs/autonomous_state.md). No
fixture here is copied from, or claims to be, a real trial. NCT IDs
below (e.g. "NCT99999901") are intentionally in a range not used by
real studies, and sponsor/drug names are invented, to keep mock and
real data unambiguous.

No test in this file makes a real network call. `http_get` is always
a hand-written fake.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from singularity.sources.clinicaltrials import (
    build_request_url,
    extract_outcome_records,
    fetch_studies_page,
    iter_all_studies,
    ClinicalTrialsAdapter,
)


def _mock_study_with_results(nct_id="NCT99999901") -> dict:
    """A hand-written MOCK study record shaped like a real
    ClinicalTrials.gov v2 study with posted results. Not real data."""
    return {
        "protocolSection": {"identificationModule": {"nctId": nct_id}},
        "hasResults": True,
        "resultsSection": {
            "outcomeMeasuresModule": {
                "outcomeMeasures": [
                    {
                        "title": "Median Overall Survival",
                        "paramType": "MEDIAN",
                        "unitOfMeasure": "months",
                        "timeFrame": "Up to 36 months",
                        "groups": [
                            {"id": "OG000", "title": "Mock Drug Arm"},
                            {"id": "OG001", "title": "Mock Placebo Arm"},
                        ],
                        "classes": [
                            {
                                "categories": [
                                    {
                                        "measurements": [
                                            {"groupId": "OG000", "value": "24.5"},
                                            {"groupId": "OG001", "value": "18.2"},
                                        ]
                                    }
                                ]
                            }
                        ],
                    },
                    {
                        "title": "Objective Response Rate",
                        "paramType": "NUMBER",
                        "unitOfMeasure": "percentage of participants",
                        "timeFrame": "Up to 36 months",
                        "groups": [
                            {"id": "OG000", "title": "Mock Drug Arm"},
                            {"id": "OG001", "title": "Mock Placebo Arm"},
                        ],
                        "classes": [
                            {
                                "categories": [
                                    {
                                        "measurements": [
                                            {"groupId": "OG000", "value": "42"},
                                            {"groupId": "OG001", "value": "NA"},
                                        ]
                                    }
                                ]
                            }
                        ],
                    },
                ]
            }
        },
    }


def _mock_study_without_results(nct_id="NCT99999902") -> dict:
    return {
        "protocolSection": {"identificationModule": {"nctId": nct_id}},
        "hasResults": False,
    }


def test_build_request_url_includes_expected_params():
    url, params = build_request_url(query_cond="Mock Condition", page_size=25)
    assert "clinicaltrials.gov/api/v2/studies" in url
    assert params["pageSize"] == "25"
    assert params["query.cond"] == "Mock Condition"
    assert "format=json" in url


def test_fetch_studies_page_records_provenance_with_mock_transport():
    def fake_http_get(url: str) -> bytes:
        return json.dumps({"studies": [_mock_study_with_results()], "nextPageToken": None}).encode()

    page = fetch_studies_page(query_cond="Mock Condition", http_get=fake_http_get)
    assert page["_provenance"]["source"] == "clinicaltrials.gov"
    assert "request_url" in page["_provenance"]
    assert "retrieved_at" in page["_provenance"]
    assert len(page["studies"]) == 1


def test_iter_all_studies_paginates_with_mock_transport():
    call_count = {"n": 0}

    def fake_http_get(url: str) -> bytes:
        call_count["n"] += 1
        if "pageToken" not in url:
            return json.dumps(
                {"studies": [_mock_study_with_results("NCT99999901")], "nextPageToken": "PAGE2"}
            ).encode()
        return json.dumps({"studies": [_mock_study_without_results("NCT99999902")], "nextPageToken": None}).encode()

    studies = list(iter_all_studies(query_cond="Mock Condition", http_get=fake_http_get, min_interval_seconds=0, sleep=lambda s: None))
    assert call_count["n"] == 2
    assert len(studies) == 2
    assert {s["protocolSection"]["identificationModule"]["nctId"] for s in studies} == {
        "NCT99999901",
        "NCT99999902",
    }


def test_extract_outcome_records_from_mock_study_with_results():
    study = _mock_study_with_results()
    study["_page_provenance"] = {
        "source": "clinicaltrials.gov",
        "retrieved_at": "2026-08-13T00:00:00Z",
        "request_url": "https://clinicaltrials.gov/api/v2/studies?mock=1",
        "query_params": {"query.cond": "Mock Condition"},
    }
    records = extract_outcome_records(study)
    assert len(records) == 4  # 2 outcome measures x 2 groups each

    os_records = [r for r in records if r.title == "Median Overall Survival"]
    assert len(os_records) == 2
    assert {r.group for r in os_records} == {"Mock Drug Arm", "Mock Placebo Arm"}
    assert all(r.nct_id == "NCT99999901" for r in os_records)
    assert all(r.provenance is not None for r in os_records)
    assert all(r.provenance.source == "clinicaltrials.gov" for r in os_records)


def test_extract_outcome_records_handles_malformed_value_as_none():
    study = _mock_study_with_results()
    study["_page_provenance"] = {}
    records = extract_outcome_records(study)
    orr_placebo = [r for r in records if r.title == "Objective Response Rate" and r.group == "Mock Placebo Arm"]
    assert len(orr_placebo) == 1
    assert orr_placebo[0].value is None  # "NA" could not be parsed as a number


def test_extract_outcome_records_returns_empty_for_study_without_results():
    study = _mock_study_without_results()
    study["_page_provenance"] = {}
    records = extract_outcome_records(study)
    assert records == []


def test_extract_outcome_records_returns_empty_when_no_nct_id():
    study = {"protocolSection": {"identificationModule": {}}, "hasResults": True}
    records = extract_outcome_records(study)
    assert records == []


def test_provenance_raw_field_preserves_original_outcome_measure():
    study = _mock_study_with_results()
    study["_page_provenance"] = {}
    records = extract_outcome_records(study)
    r = records[0]
    assert "outcome_measure" in r.provenance.raw
    assert r.provenance.raw["outcome_measure"]["title"] == r.title


def test_clinicaltrials_adapter_end_to_end_with_mock_transport():
    def fake_http_get(url: str) -> bytes:
        return json.dumps({"studies": [_mock_study_with_results()], "nextPageToken": None}).encode()

    adapter = ClinicalTrialsAdapter(http_get=fake_http_get, sleep=lambda s: None)
    assert adapter.source_name == "clinicaltrials.gov"
    records = adapter.fetch_outcome_records(query_cond="Mock Condition")
    assert len(records) == 4
    assert all(r.provenance.query_params.get("query.cond") == "Mock Condition" for r in records)
