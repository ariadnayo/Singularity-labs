"""
Tests for Trial extraction: singularity.sources.clinicaltrials.extract_trial
and ClinicalTrialsAdapter.fetch_trials.

CRITICAL: every fixture in this file is SYNTHETIC / MOCK data written
by hand to match the publicly documented ClinicalTrials.gov API v2
protocolSection shape. No fixture here is copied from, or claims to
be, a real trial. NCT IDs (e.g. "NCT99999910") are intentionally in a
range not used by real studies, and sponsor/drug/condition names are
invented, to keep mock and real data unambiguous.

FIELD-VERIFICATION CAVEAT (2026-08-14, session 9): only
`protocolSection.identificationModule.nctId` and
`protocolSection.outcomesModule` have been independently verified
against a live ClinicalTrials.gov API v2 response in this project (see
docs/autonomous_state.md). The other protocolSection fields exercised
here (statusModule, designModule, sponsorCollaboratorsModule,
conditionsModule, armsInterventionsModule) are mocked according to the
publicly documented API v2 schema, but were not re-verified against a
fresh live response in the session that wrote extract_trial (web-fetch
tooling was unavailable that session). These mocks encode the SAME
assumption the implementation makes, so passing tests confirm internal
consistency, not independent verification against the live API. A
real live spot-check remains an open item -- see
docs/autonomous_state.md "Session 9 Summary".

No test in this file makes a real network call.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from singularity.sources.clinicaltrials import ClinicalTrialsAdapter, extract_trial


def _mock_full_protocol_study(nct_id="NCT99999910") -> dict:
    """A hand-written MOCK study record with a fully-populated
    protocolSection, shaped per the documented API v2 schema. Not real
    data -- see module docstring caveat above."""
    return {
        "protocolSection": {
            "identificationModule": {
                "nctId": nct_id,
                "briefTitle": "A Mock Study of Fictidrug in Mock Advanced Solid Tumors",
                "officialTitle": "A Phase 2 Mock Study Evaluating Fictidrug in Participants With Mock Advanced Solid Tumors",
            },
            "statusModule": {
                "overallStatus": "RECRUITING",
                "startDateStruct": {"date": "2025-01-15"},
                "completionDateStruct": {"date": "2028-06-30"},
            },
            "designModule": {
                "studyType": "INTERVENTIONAL",
                "phases": ["PHASE2"],
                "enrollmentInfo": {"count": 240},
            },
            "sponsorCollaboratorsModule": {"leadSponsor": {"name": "Mock Therapeutics, Inc."}},
            "conditionsModule": {"conditions": ["Mock Advanced Solid Tumors", "Mock Non-Small Cell Lung Cancer"]},
            "armsInterventionsModule": {
                "interventions": [
                    {"type": "DRUG", "name": "Fictidrug"},
                    {"type": "DRUG", "name": "Mock Placebo"},
                ]
            },
        },
        "hasResults": False,
    }


def _mock_minimal_protocol_study(nct_id="NCT99999911") -> dict:
    """A hand-written MOCK study record with ONLY an NCT ID -- exercises
    that missing fields become None, not fabricated defaults."""
    return {"protocolSection": {"identificationModule": {"nctId": nct_id}}, "hasResults": False}


def test_extract_trial_maps_all_fields_from_full_mock_protocol():
    study = _mock_full_protocol_study()
    study["_page_provenance"] = {
        "retrieved_at": "2026-08-14T00:00:00Z",
        "request_url": "https://clinicaltrials.gov/api/v2/studies?mock=1",
        "query_params": {"query.cond": "Mock Condition"},
    }
    trial = extract_trial(study)
    assert trial is not None
    assert trial.nct_id == "NCT99999910"
    assert trial.brief_title == "A Mock Study of Fictidrug in Mock Advanced Solid Tumors"
    assert trial.official_title.startswith("A Phase 2 Mock Study")
    assert trial.overall_status == "RECRUITING"
    assert trial.phases == ["PHASE2"]
    assert trial.study_type == "INTERVENTIONAL"
    assert trial.conditions == ["Mock Advanced Solid Tumors", "Mock Non-Small Cell Lung Cancer"]
    assert trial.lead_sponsor == "Mock Therapeutics, Inc."
    assert trial.interventions == ["Fictidrug", "Mock Placebo"]
    assert trial.start_date == "2025-01-15"
    assert trial.completion_date == "2028-06-30"
    assert trial.enrollment_count == 240
    assert trial.provenance is not None
    assert trial.provenance.source == "clinicaltrials.gov"
    assert trial.provenance.source_record_id == "NCT99999910"


def test_extract_trial_missing_fields_become_none_not_fabricated():
    """A study with only an NCT ID must produce a Trial with every
    other field explicitly None -- never a guessed/default value."""
    study = _mock_minimal_protocol_study()
    study["_page_provenance"] = {}
    trial = extract_trial(study)
    assert trial is not None
    assert trial.nct_id == "NCT99999911"
    assert trial.brief_title is None
    assert trial.official_title is None
    assert trial.overall_status is None
    assert trial.phases is None
    assert trial.study_type is None
    assert trial.conditions is None
    assert trial.lead_sponsor is None
    assert trial.interventions is None
    assert trial.start_date is None
    assert trial.completion_date is None
    assert trial.enrollment_count is None


def test_extract_trial_returns_none_when_no_nct_id():
    """A study record with no NCT ID cannot become a valid Trial --
    must not fabricate one."""
    study = {"protocolSection": {"identificationModule": {}}}
    assert extract_trial(study) is None


def test_extract_trial_handles_missing_protocol_section_entirely():
    """A malformed/unexpected study shape (no protocolSection at all)
    must not crash -- it has no NCT ID, so returns None."""
    assert extract_trial({}) is None


def test_extract_trial_provenance_raw_preserves_relevant_modules():
    study = _mock_full_protocol_study()
    study["_page_provenance"] = {}
    trial = extract_trial(study)
    assert "identificationModule" in trial.provenance.raw
    assert "statusModule" in trial.provenance.raw
    assert "designModule" in trial.provenance.raw
    assert trial.provenance.raw["statusModule"]["overallStatus"] == "RECRUITING"


def test_provenance_raw_includes_arms_interventions_module():
    """Regression test for the session-15 gap: armsInterventionsModule
    was previously missing from provenance.raw even though
    `interventions` is extracted from it, making that field
    unauditable against its own source. Found by code inspection."""
    study = _mock_full_protocol_study()
    study["_page_provenance"] = {}
    trial = extract_trial(study)
    assert "armsInterventionsModule" in trial.provenance.raw
    assert trial.provenance.raw["armsInterventionsModule"]["interventions"][0]["name"] == "Fictidrug"


def test_fetch_trials_end_to_end_with_mock_transport():
    def fake_http_get(url: str) -> bytes:
        return json.dumps(
            {"studies": [_mock_full_protocol_study(), _mock_minimal_protocol_study()], "nextPageToken": None}
        ).encode()

    adapter = ClinicalTrialsAdapter(http_get=fake_http_get, sleep=lambda s: None)
    trials = adapter.fetch_trials(query_cond="Mock Condition")
    assert len(trials) == 2
    nct_ids = {t.nct_id for t in trials}
    assert nct_ids == {"NCT99999910", "NCT99999911"}


def test_fetch_trials_skips_studies_with_no_nct_id_rather_than_fabricating():
    def fake_http_get(url: str) -> bytes:
        return json.dumps(
            {"studies": [{"protocolSection": {"identificationModule": {}}}], "nextPageToken": None}
        ).encode()

    adapter = ClinicalTrialsAdapter(http_get=fake_http_get, sleep=lambda s: None)
    trials = adapter.fetch_trials(query_cond="Mock Condition")
    assert trials == []
