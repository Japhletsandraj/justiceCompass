from ai.retrieval.assessment import assess_question, classify_domain
from ai.retrieval.prediction import estimate_bail_outcome
from ai.retrieval.caselaw_loader import CaselawIndex, load_cases
import json


def test_assessment_identifies_domain_and_missing_dates():
    result = assess_question("My landlord is threatening eviction without notice", "Delhi")
    assert result.legal_domain == "tenancy_property"
    assert result.immediate_steps
    assert any("dates" in item.lower() for item in result.missing_information)


def test_unknown_question_does_not_claim_valid_case():
    result = assess_question("Can you help me?", "Delhi", "2026-01-01")
    assert result.legal_domain == "unknown"
    assert "may involve" in result.concern_assessment


def test_bail_estimator_abstains_for_small_sample():
    records = [{"outcome": "Granted"}, {"outcome": "Rejected"}]
    estimate = estimate_bail_outcome(records, min_cases=3)
    assert estimate.estimate is None
    assert estimate.outcome == "insufficient_data"


def test_bail_estimator_reports_historical_rate():
    records = [{"outcome": "Granted", "outcome_verified": True}] * 3 + [
        {"outcome": "Rejected", "outcome_verified": True}
    ]
    estimate = estimate_bail_outcome(records, min_cases=4)
    assert estimate.estimate == 0.75
    assert estimate.comparable_cases == 4


def test_bail_estimator_normalizes_ecourts_dispositions():
    records = [{"outcome": "Allowed", "outcome_verified": True}] * 3 + [
        {"outcome": "Dismissed", "outcome_verified": True}
    ]
    estimate = estimate_bail_outcome(records, min_cases=4)
    assert estimate.estimate == 0.75
    assert estimate.comparable_cases == 4


def test_bail_estimator_ignores_unverified_outcomes():
    records = [{"outcome": "Granted"}] * 5
    estimate = estimate_bail_outcome(records, min_cases=1)
    assert estimate.estimate is None
    assert estimate.comparable_cases == 0


def test_load_cases_includes_optional_ecourts_dataset(tmp_path):
    record = {
        "case_id": "EC-1",
        "title": "Example v State",
        "court": "Delhi High Court",
        "court_level": "High Court",
        "region": "Delhi",
        "year": 2025,
        "outcome": "Allowed",
        "domain_tags": ["criminal_law"],
        "case_details": {"case_type": "bail_regular"},
    }
    (tmp_path / "ecourts_cases.json").write_text(
        json.dumps([record]), encoding="utf-8"
    )

    index = CaselawIndex(load_cases(tmp_path))
    cases = index.filter(case_type="bail_regular", region="Delhi")

    assert len(cases) == 1
    assert cases[0]["outcome"] == "allowed"
    assert cases[0]["source_dataset"] == "eCourts"
