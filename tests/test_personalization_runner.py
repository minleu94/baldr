from __future__ import annotations

from scripts.inspect_personalization_contract import run_fixture


def test_bounded_fixture_runner_emits_hashed_shadow_receipt() -> None:
    receipt = run_fixture()

    assert receipt["schema_version"] == "personalization-contract-runner-receipt.v1"
    assert receipt["bounded"] is True
    assert receipt["shadow_only"] is True
    assert receipt["formal_order_allowed"] is False
    assert receipt["auto_action_allowed"] is False
    assert receipt["natural_forward_credit"] is False
    assert receipt["adoption_confidence_status"] == "adoption_not_evaluable"
    assert receipt["projection"]["status"] == "linked_prediction"
    assert receipt["calibration"]["status"] == "evaluated"
    assert receipt["counts"]["calibration_valid_rows"] == 2
    assert receipt["negative_cases"] == {
        "missing_scope": "population_only",
        "persisted_not_delivered": "not_delivered",
        "invalid_receipt": "unavailable",
    }
    assert receipt["runner_receipt_hash"].startswith("sha256:")
