from ai.retrieval.assessment import assess_question, classify_domain
from ai.retrieval.prediction import estimate_bail_outcome


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
    records = [{"outcome": "Granted"}] * 3 + [{"outcome": "Rejected"}]
    estimate = estimate_bail_outcome(records, min_cases=4)
    assert estimate.estimate == 0.75
    assert estimate.comparable_cases == 4
