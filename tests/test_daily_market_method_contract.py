from __future__ import annotations

from datetime import date, timedelta

from app_module.daily_market_method_contract import method_contracts_payload
from app_module.daily_market_research_screener import evaluate_daily_market_conditions


def test_screener_projects_verified_method_binding_and_rejects_wrong_decision_date():
    contracts = method_contracts_payload()
    contract = contracts["close_above_ma20"]
    decision_date = date(2026, 10, 2)
    raw_condition = {
        "state": "match",
        "relation": "above",
        "reason": "",
        "method_id": contract["method_id"],
        "family": contract["family"],
        "version": contract["version"],
        "parameters": contract["parameters"],
        "decision_date": decision_date.isoformat(),
        "eligibility": "eligible",
        "unknown_reason": "",
    }

    projected = evaluate_daily_market_conditions(
        {"close_above_ma20": raw_condition},
        ("close_above_ma20",),
        "AND",
        expected_decision_date=decision_date,
    ).conditions[0]
    assert projected.state == "match"
    assert projected.to_dict() == {
        "key": "close_above_ma20",
        "state": "match",
        "relation": "above",
        "reason": "",
        "method_id": contract["method_id"],
        "family": contract["family"],
        "version": contract["version"],
        "parameters": {"window": 20, "direction": "above"},
        "decision_date": decision_date.isoformat(),
        "eligibility": "eligible",
        "unknown_reason": "",
    }

    mismatched = evaluate_daily_market_conditions(
        {"close_above_ma20": raw_condition},
        ("close_above_ma20",),
        "AND",
        expected_decision_date=decision_date + timedelta(days=1),
    ).conditions[0]
    assert mismatched.state == "unknown"
    assert mismatched.relation == "unknown"
    assert mismatched.eligibility == "unknown"
    assert mismatched.unknown_reason == "decision_date_mismatch"


def test_minimal_legacy_condition_projection_stays_minimal():
    legacy = evaluate_daily_market_conditions(
        {
            "close_above_ma20": {
                "state": "match",
                "relation": "above",
                "reason": "",
            }
        },
        ("close_above_ma20",),
        "AND",
    ).conditions[0]
    assert legacy.to_dict() == {
        "key": "close_above_ma20",
        "state": "match",
        "relation": "above",
        "reason": "",
    }
