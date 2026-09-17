from __future__ import annotations

from copy import deepcopy

import pytest

from app_module.personalization_contract import (
    PersonalizationDeliveryScope,
)
from app_module.personalization_projection import (
    PersonalizationDeliveryCaptureService,
    PersonalizationProjectionError,
    PersonalizationProjectionService,
)
from app_module.personalization_contract import canonical_payload_hash


RECEIPT_HASH_SEED = "sha256:" + ("b" * 64)
DATASET_HASH = "sha256:" + ("d" * 64)
UNIVERSE_HASH = "sha256:" + ("e" * 64)
LABEL_CONTRACT_ID = "label_projection_v1"
RETURN_BASIS = "close_to_close_event_date"
RESULT_ID = "rec_projection_001"
STOCK_CODE = "2330"
SCOPE_ID = "scope_projection_user_001"
PREDICTION_ID = "00000000-0000-0000-0000-000000000010"


def _receipt() -> dict:
    body = {
        "schema_version": "recommendation-calibration-projection-receipt.v1",
        "result_id": RESULT_ID,
        "decision_date": "2025-02-10",
        "candidate_identity": {"candidate_id": "model_001"},
        "model_id": "model_001",
        "dataset_id": "dataset_001",
        "dataset_hash": DATASET_HASH,
        "label_contract_id": LABEL_CONTRACT_ID,
        "return_basis": RETURN_BASIS,
        "universe_policy_hash": UNIVERSE_HASH,
        "source_id": "recommendation_service",
        "selection_contract": {
            "authority": "rule_top_n",
            "score_kind": "rule_total_score",
            "percentile_kind": "rule_percentile",
            "model_ranking_kind": "model_return_bp",
            "top_n_changed_by_model": False,
        },
        "projections": [
            {
                "stock_code": STOCK_CODE,
                "model_version": "model_001",
                "dataset_version": "dataset_001",
                "dataset_hash": DATASET_HASH,
                "cost_scenario_hash": RECEIPT_HASH_SEED,
                "horizon": "20 trading days",
                "prediction_id": PREDICTION_ID,
                "label_contract_id": LABEL_CONTRACT_ID,
                "return_basis": RETURN_BASIS,
                "universe_policy_hash": UNIVERSE_HASH,
                "calibrated_probability_bp": 5200,
                "status": "active_candidate",
            }
        ],
        "formal_order_allowed": False,
        "production_action_allowed": False,
        "shadow_only": True,
    }
    return {**body, "receipt_hash": canonical_payload_hash(body)}


def _scope() -> PersonalizationDeliveryScope:
    return PersonalizationDeliveryScope.create(
        scope_id=SCOPE_ID,
        scope_type="user",
        delivery_id="delivery_projection_001",
        declared_at="2025-02-10T08:50:00+00:00",
        decision_at="2025-02-10T09:00:00+00:00",
        available_at="2025-02-10T08:55:00+00:00",
        captured_at="2025-02-10T08:55:00+00:00",
        receipt_created_at="2025-02-10T09:01:00+00:00",
    )


def _capture(status: str = "delivered"):
    service = PersonalizationDeliveryCaptureService()
    capture = service.capture(
        scope=_scope(),
        request_id="request_projection_001",
        result_id=RESULT_ID,
        stock_code=STOCK_CODE,
        projection_receipt_hash=_receipt()["receipt_hash"],
        generated_at="2025-02-10T08:50:00+00:00",
        prediction_id=PREDICTION_ID,
        model_id="model_001",
        dataset_id="dataset_001",
        dataset_hash=DATASET_HASH,
        cost_scenario_hash=RECEIPT_HASH_SEED,
        horizon_days=20,
    )
    if status == "generated":
        return capture
    persisted = service.mark_persisted(capture, persisted_at="2025-02-10T08:56:00+00:00")
    if status == "persisted":
        return persisted
    return service.mark_delivered(persisted, delivered_at="2025-02-10T08:59:00+00:00")


def _result(capture=None, recommendations=None) -> dict:
    receipt = _receipt()
    capture = capture or _capture()
    row = {
        "stock_code": STOCK_CODE,
        "calibration_provenance": {
            "projection_receipt_hash": receipt["receipt_hash"],
            "model_version": "model_001",
            "dataset_version": "dataset_001",
            "cost_scenario_hash": RECEIPT_HASH_SEED,
        },
    }
    return {
        "result_id": RESULT_ID,
        "run_context": {
            "as_of_date": "2025-02-10",
            "data_date": "2025-02-10",
            "run_started_at": "2025-02-10T08:49:00+00:00",
            "personalization_scope_declared_at": _scope().declared_at,
            "available_at": _scope().available_at,
            "captured_at": _scope().captured_at,
            "decision_at": _scope().decision_at,
            "calibration_projection_receipt_created_at": _scope().receipt_created_at,
            "temporal_contract": "recommendation-producer-clock.v1",
            "temporal_mode": "natural_producer_clock",
            "cutoff_selection": "producer_selected_latest_available_cutoff",
            "cutoff_policy": "source_latest_available_exact",
            "decision_clock_timezone": "UTC",
            "market_calendar_timezone": "Asia/Taipei",
            "prediction_decision_anchor": "actual_producer_decision_at",
            "horizon_anchor": "immutable_projection_receipt",
            "calibration_projection_receipt": receipt,
            "calibration_projection_receipt_metadata": {
                "result_id": RESULT_ID,
                "receipt_hash": receipt["receipt_hash"],
                "receipt_created_at": _scope().receipt_created_at,
            },
            "personalization_delivery_captures": [capture.to_dict()],
            "calibration_projection_rows": {STOCK_CODE: dict(receipt["projections"][0])},
        },
        "recommendations": recommendations if recommendations is not None else [row],
    }


def _service(outcomes=None, actions=None) -> PersonalizationProjectionService:
    return PersonalizationProjectionService(
        action_reader={(RESULT_ID, STOCK_CODE): actions or []},
        outcome_reader={(RESULT_ID, STOCK_CODE): outcomes or []},
    )


def test_projection_links_only_exact_delivered_candidate_and_keeps_missing_action_unrecorded() -> None:
    result = _result()
    outcome = {
        "result_id": RESULT_ID,
        "stock_code": STOCK_CODE,
        "prediction_id": PREDICTION_ID,
        "personalization_scope_id": SCOPE_ID,
        "prediction_receipt_hash": _receipt()["receipt_hash"],
        "event_id": "event_001",
        "outcome_id": "outcome_001",
        "event_price_date": "2025-02-10",
        "outcome_price_date": "2025-03-02",
        "label_available_date": "2025-03-02",
        "window_days": 20,
        "return_basis": RETURN_BASIS,
        "label_contract_id": LABEL_CONTRACT_ID,
        "label_available_at": "2025-03-02T00:00:00+00:00",
        "outcome_recorded_at": "2025-03-02T00:00:00+00:00",
        "cost_scenario_hash": RECEIPT_HASH_SEED,
        "outcome_status": "ready",
        "outcome_tier": "natural_forward",
    }
    projection = _service([outcome]).build_for_candidate(
        result_id=RESULT_ID,
        stock_code=STOCK_CODE,
        personalization_scope_id=SCOPE_ID,
        result=result,
        projection_receipt=_receipt(),
        evaluated_as_of="2025-03-05",
        evaluation_cutoff_at="2025-03-05T00:00:00+00:00",
    )

    assert projection.status == "linked_prediction"
    assert projection.evidence is not None
    assert projection.evidence.action == "not_recorded"
    assert projection.outcome_status == "ready"
    assert projection.evidence.formal_order_allowed is False


def test_projection_rejects_known_before_outcome_clock_even_with_exact_identity() -> None:
    outcome = {
        "result_id": RESULT_ID,
        "stock_code": STOCK_CODE,
        "prediction_id": PREDICTION_ID,
        "personalization_scope_id": SCOPE_ID,
        "prediction_receipt_hash": _receipt()["receipt_hash"],
        "event_id": "event_known_before",
        "outcome_id": "outcome_known_before",
        "window_days": 20,
        "return_basis": RETURN_BASIS,
        "label_contract_id": LABEL_CONTRACT_ID,
        "cost_scenario_hash": RECEIPT_HASH_SEED,
        "event_price_date": "2025-02-10",
        "outcome_price_date": "2025-03-02",
        "label_available_date": "2025-01-01",
        "label_available_at": "2025-01-01T00:00:00+00:00",
        "outcome_recorded_at": "2025-01-01T00:00:00+00:00",
        "label": 1,
        "outcome_status": "ready",
        "outcome_tier": "natural_forward",
    }
    projection = _service([outcome]).build_for_candidate(
        result_id=RESULT_ID,
        stock_code=STOCK_CODE,
        personalization_scope_id=SCOPE_ID,
        result=_result(),
        projection_receipt=_receipt(),
        evaluated_as_of="2025-03-05",
        evaluation_cutoff_at="2025-03-05T00:00:00+00:00",
    )

    assert projection.status == "linked_prediction"
    assert projection.outcome_status == "invalid"
    assert "label_available_at_before_or_at_decision" in projection.warnings
    assert "outcome_recorded_at_before_decision" in projection.warnings


def test_projection_cutoff_uses_taipei_market_date_at_utc_midnight_boundary() -> None:
    projection = _service().build_for_candidate(
        result_id=RESULT_ID,
        stock_code=STOCK_CODE,
        personalization_scope_id=SCOPE_ID,
        result=_result(),
        projection_receipt=_receipt(),
        evaluated_as_of="2025-02-10",
        evaluation_cutoff_at="2025-02-09T16:30:00+00:00",
    )

    assert projection.status == "linked_prediction"
    assert "evaluation_cutoff_after_evaluated_as_of" not in projection.warnings


def test_projection_does_not_link_unbound_scope_source_id_or_undelivered_capture() -> None:
    base = _result()
    no_scope = deepcopy(base)
    no_scope["run_context"].pop("personalization_delivery_captures")
    no_scope["recommendations"][0]["calibration_provenance"] = {
        "source_id": "2330",
        "projection_receipt_hash": _receipt()["receipt_hash"],
    }
    population_only = _service().build_for_candidate(
        result_id=RESULT_ID,
        stock_code=STOCK_CODE,
        personalization_scope_id=SCOPE_ID,
        result=no_scope,
        projection_receipt=_receipt(),
    )
    assert population_only.status == "population_only"
    assert population_only.evidence is None

    not_delivered = _service().build_for_candidate(
        result_id=RESULT_ID,
        stock_code=STOCK_CODE,
        personalization_scope_id=SCOPE_ID,
        result=_result(_capture("persisted")),
        projection_receipt=_receipt(),
    )
    assert not_delivered.status == "not_delivered"
    assert not_delivered.evidence is None


def test_projection_fails_closed_for_receipt_identity_and_duplicate_candidates() -> None:
    result = _result()
    bad_receipt = deepcopy(_receipt())
    bad_receipt["receipt_hash"] = "sha256:" + ("c" * 64)
    invalid_receipt = _service().build_for_candidate(
        result_id=RESULT_ID,
        stock_code=STOCK_CODE,
        personalization_scope_id=SCOPE_ID,
        result=result,
        projection_receipt=bad_receipt,
    )
    assert invalid_receipt.status == "unavailable"
    assert "receipt" in " ".join(invalid_receipt.warnings)

    exact_duplicate = _service().build_for_candidate(
        result_id=RESULT_ID,
        stock_code=STOCK_CODE,
        personalization_scope_id=SCOPE_ID,
        result=_result(recommendations=[result["recommendations"][0], result["recommendations"][0]]),
        projection_receipt=_receipt(),
    )
    assert exact_duplicate.status == "duplicate_exact"
    assert exact_duplicate.duplicate_exact_count == 1

    conflict = deepcopy(result["recommendations"][0])
    conflict["calibration_provenance"]["model_version"] = "model_conflict"
    duplicate_conflict = _service().build_for_candidate(
        result_id=RESULT_ID,
        stock_code=STOCK_CODE,
        personalization_scope_id=SCOPE_ID,
        result=_result(recommendations=[result["recommendations"][0], conflict]),
        projection_receipt=_receipt(),
    )
    assert duplicate_conflict.status == "duplicate_conflict"
    assert duplicate_conflict.duplicate_conflict_count == 2


def test_projection_rejects_requested_scope_mismatch_and_future_scope_mapping() -> None:
    result = _result()
    mismatch = _service().build_for_candidate(
        result_id=RESULT_ID,
        stock_code=STOCK_CODE,
        personalization_scope_id="scope_other",
        result=result,
        projection_receipt=_receipt(),
    )
    assert mismatch.status == "unavailable"
    assert "scope" in " ".join(mismatch.warnings)

    future = deepcopy(result)
    future["run_context"]["personalization_scope"] = {
        **_scope().to_dict(),
        "available_at": "2025-02-10T09:00:01+00:00",
    }
    future["run_context"].pop("personalization_delivery_captures")
    future_projection = _service().build_for_candidate(
        result_id=RESULT_ID,
        stock_code=STOCK_CODE,
        personalization_scope_id=SCOPE_ID,
        result=future,
        projection_receipt=_receipt(),
    )
    assert future_projection.status == "population_only"


def test_projection_never_allows_context_probability_or_horizon_to_override_receipt() -> None:
    result = _result()
    tampered = deepcopy(result)
    tampered["run_context"]["calibration_projection_rows"][STOCK_CODE][
        "calibrated_probability_bp"
    ] = 9999
    tampered["run_context"]["calibration_projection_rows"][STOCK_CODE]["horizon"] = (
        "5 trading days"
    )
    projection = _service().build_for_candidate(
        result_id=RESULT_ID,
        stock_code=STOCK_CODE,
        personalization_scope_id=SCOPE_ID,
        result=tampered,
        projection_receipt=_receipt(),
        evaluated_as_of="2025-02-11",
        evaluation_cutoff_at="2025-02-11T00:00:00+00:00",
    )
    assert projection.status == "unavailable"
    assert any("receipt" in warning for warning in projection.warnings)


def test_projection_requires_scope_prediction_horizon_cost_and_exact_outcome_clock() -> None:
    result = _result()
    wrong_prediction = {
        "result_id": RESULT_ID,
        "stock_code": STOCK_CODE,
        "personalization_scope_id": SCOPE_ID,
        "prediction_id": "wrong_prediction",
        "prediction_receipt_hash": _receipt()["receipt_hash"],
        "window_days": 5,
        "return_basis": RETURN_BASIS,
        "label_contract_id": LABEL_CONTRACT_ID,
        "cost_scenario_hash": RECEIPT_HASH_SEED,
        "label_available_at": "2025-02-11T00:00:00+00:00",
        "outcome_recorded_at": "2025-02-11T00:00:00+00:00",
        "outcome_status": "ready",
        "outcome_tier": "natural_forward",
    }
    projection = _service([wrong_prediction]).build_for_candidate(
        result_id=RESULT_ID,
        stock_code=STOCK_CODE,
        personalization_scope_id=SCOPE_ID,
        result=result,
        projection_receipt=_receipt(),
        evaluated_as_of="2025-02-11",
        evaluation_cutoff_at="2025-02-11T00:00:00+00:00",
    )
    assert projection.status == "linked_prediction"
    assert projection.outcome_status == "conflict"
    assert any("outcome" in warning for warning in projection.warnings)

    actions = [
        {
            "result_id": RESULT_ID,
            "stock_code": STOCK_CODE,
            "personalization_scope_id": SCOPE_ID,
            "prediction_id": PREDICTION_ID,
            "prediction_receipt_hash": _receipt()["receipt_hash"],
            "horizon_days": 20,
            "cost_scenario_hash": RECEIPT_HASH_SEED,
            "label_contract_id": LABEL_CONTRACT_ID,
            "return_basis": RETURN_BASIS,
            "action": "accepted",
            "action_state": "recorded",
            "action_at": "2025-02-10T08:59:00+00:00",
            "recorded_at": "2025-02-10T09:00:00+00:00",
            "created_at": "2025-02-10T09:00:00+00:00",
            "revision_id": "revision_early",
        },
        {
            "result_id": RESULT_ID,
            "stock_code": STOCK_CODE,
            "personalization_scope_id": SCOPE_ID,
            "prediction_id": PREDICTION_ID,
            "prediction_receipt_hash": _receipt()["receipt_hash"],
            "horizon_days": 20,
            "cost_scenario_hash": RECEIPT_HASH_SEED,
            "label_contract_id": LABEL_CONTRACT_ID,
            "return_basis": RETURN_BASIS,
            "action": "sell",
            "action_state": "recorded",
            "action_at": "2025-02-10T09:10:00+00:00",
            "recorded_at": "2025-02-10T09:11:00+00:00",
            "created_at": "2025-02-10T09:11:00+00:00",
            "revision_id": "revision_late",
        },
    ]
    action_projection = _service(actions=actions).build_for_candidate(
        result_id=RESULT_ID,
        stock_code=STOCK_CODE,
        personalization_scope_id=SCOPE_ID,
        result=result,
        projection_receipt=_receipt(),
        evaluated_as_of="2025-02-10",
        evaluation_cutoff_at="2025-02-10T09:05:00+00:00",
    )
    assert action_projection.action == "accepted"
    assert action_projection.action_state == "recorded"


@pytest.mark.parametrize(
    "mutation, warning",
    [
        (
            lambda row: row.update(
                {"decision_identity": {"result_id": "other-result", "stock_code": STOCK_CODE}}
            ),
            "action_identity_alias_conflict",
        ),
        (
            lambda row: row.update({"source_result_id": "other-result"}),
            "action_identity_alias_conflict",
        ),
        (
            lambda row: row.update({"scope_id": "other-scope"}),
            "action_contract_alias_conflict",
        ),
        (
            lambda row: row.update(
                {"projection_receipt_hash": "sha256:" + ("f" * 64)}
            ),
            "action_contract_alias_conflict",
        ),
    ],
)
def test_projection_rejects_conflicting_action_aliases(
    mutation, warning: str
) -> None:
    result = _result()
    action = {
        "result_id": RESULT_ID,
        "stock_code": STOCK_CODE,
        "personalization_scope_id": SCOPE_ID,
        "prediction_id": PREDICTION_ID,
        "prediction_receipt_hash": _receipt()["receipt_hash"],
        "horizon_days": 20,
        "cost_scenario_hash": RECEIPT_HASH_SEED,
        "label_contract_id": LABEL_CONTRACT_ID,
        "return_basis": RETURN_BASIS,
        "action": "accepted",
        "action_state": "recorded",
        "action_at": "2025-02-10T08:59:00+00:00",
        "recorded_at": "2025-02-10T09:00:00+00:00",
        "created_at": "2025-02-10T09:00:00+00:00",
        "revision_id": "revision_alias_conflict",
    }
    mutation(action)
    projection = _service(actions=[action]).build_for_candidate(
        result_id=RESULT_ID,
        stock_code=STOCK_CODE,
        personalization_scope_id=SCOPE_ID,
        result=result,
        projection_receipt=_receipt(),
        evaluated_as_of="2025-02-11",
        evaluation_cutoff_at="2025-02-11T00:00:00+00:00",
    )
    assert projection.status == "linked_prediction"
    assert projection.action == "not_recorded"
    assert projection.action_state == "conflict"
    assert warning in projection.warnings


def test_projection_accepts_matching_action_aliases_and_does_not_promote_source_id() -> None:
    result = _result()
    action = {
        "result_id": RESULT_ID,
        "source_result_id": RESULT_ID,
        "stock_code": STOCK_CODE,
        "symbol": STOCK_CODE,
        "personalization_scope_id": SCOPE_ID,
        "scope_id": SCOPE_ID,
        "prediction_id": PREDICTION_ID,
        "prediction_receipt_hash": _receipt()["receipt_hash"],
        "projection_receipt_hash": _receipt()["receipt_hash"],
        "horizon_days": 20,
        "horizon": "20 trading days",
        "cost_scenario_hash": RECEIPT_HASH_SEED,
        "label_contract_id": LABEL_CONTRACT_ID,
        "return_basis": RETURN_BASIS,
        "source_id": "provider-source-is-not-result-id",
        "action": "accepted",
        "action_state": "recorded",
        "action_at": "2025-02-10T08:59:00+00:00",
        "recorded_at": "2025-02-10T09:00:00+00:00",
        "created_at": "2025-02-10T09:00:00+00:00",
        "revision_id": "revision_alias_exact",
    }
    projection = _service(actions=[action]).build_for_candidate(
        result_id=RESULT_ID,
        stock_code=STOCK_CODE,
        personalization_scope_id=SCOPE_ID,
        result=result,
        projection_receipt=_receipt(),
        evaluated_as_of="2025-02-11",
        evaluation_cutoff_at="2025-02-11T00:00:00+00:00",
    )
    assert projection.action == "accepted"
    assert projection.action_state == "recorded"
    assert not any("alias_conflict" in warning for warning in projection.warnings)


@pytest.mark.parametrize(
    "mutation, warning",
    [
        (
            lambda row: row.update(
                {"decision_identity": {"result_id": "other-result", "stock_code": STOCK_CODE}}
            ),
            "outcome_identity_alias_conflict",
        ),
        (
            lambda row: row.update({"scope_id": "other-scope"}),
            "outcome_contract_alias_conflict",
        ),
        (
            lambda row: row.update(
                {"projection_receipt_hash": "sha256:" + ("f" * 64)}
            ),
            "outcome_contract_alias_conflict",
        ),
    ],
)
def test_projection_rejects_conflicting_outcome_aliases(
    mutation, warning: str
) -> None:
    result = _result()
    outcome = {
        "result_id": RESULT_ID,
        "stock_code": STOCK_CODE,
        "personalization_scope_id": SCOPE_ID,
        "prediction_id": PREDICTION_ID,
        "prediction_receipt_hash": _receipt()["receipt_hash"],
        "event_id": "event_alias_conflict",
        "outcome_id": "outcome_alias_conflict",
        "event_price_date": "2025-02-10",
        "outcome_price_date": "2025-03-02",
        "label_available_date": "2025-03-02",
        "window_days": 20,
        "return_basis": RETURN_BASIS,
        "label_contract_id": LABEL_CONTRACT_ID,
        "label_available_at": "2025-03-02T00:00:00+00:00",
        "outcome_recorded_at": "2025-03-02T00:00:00+00:00",
        "cost_scenario_hash": RECEIPT_HASH_SEED,
        "outcome_status": "ready",
        "outcome_tier": "natural_forward",
        "label": 1,
    }
    mutation(outcome)
    projection = _service([outcome]).build_for_candidate(
        result_id=RESULT_ID,
        stock_code=STOCK_CODE,
        personalization_scope_id=SCOPE_ID,
        result=result,
        projection_receipt=_receipt(),
        evaluated_as_of="2025-03-05",
        evaluation_cutoff_at="2025-03-05T00:00:00+00:00",
    )
    assert projection.status == "linked_prediction"
    assert projection.outcome_status == "conflict"
    assert warning in projection.warnings


@pytest.mark.parametrize("nested_key", ["outcomes", "outcome"])
def test_projection_rejects_evidence_parent_child_conflict_before_flatten(
    nested_key: str,
) -> None:
    result = _result()
    child = {
        "result_id": RESULT_ID,
        "stock_code": STOCK_CODE,
        "personalization_scope_id": SCOPE_ID,
        "prediction_id": PREDICTION_ID,
        "prediction_receipt_hash": _receipt()["receipt_hash"],
        "event_id": "event_preflatten_conflict",
        "outcome_id": "outcome_preflatten_conflict",
        "event_price_date": "2025-02-10",
        "outcome_price_date": "2025-03-02",
        "label_available_date": "2025-03-02",
        "window_days": 20,
        "return_basis": RETURN_BASIS,
        "label_contract_id": LABEL_CONTRACT_ID,
        "cost_scenario_hash": RECEIPT_HASH_SEED,
        "label_available_at": "2025-03-02T00:00:00+00:00",
        "outcome_recorded_at": "2025-03-02T00:00:00+00:00",
        "outcome_status": "ready",
        "outcome_tier": "natural_forward",
        "label": 1,
    }
    event = {
        "result_id": "wrong-parent-result",
        "stock_code": "9999",
        nested_key: [child] if nested_key == "outcomes" else child,
    }
    projection = PersonalizationProjectionService(
        evidence_reader={(RESULT_ID, STOCK_CODE): [event]},
    ).build_for_candidate(
        result_id=RESULT_ID,
        stock_code=STOCK_CODE,
        personalization_scope_id=SCOPE_ID,
        result=result,
        projection_receipt=_receipt(),
        evaluated_as_of="2025-03-05",
        evaluation_cutoff_at="2025-03-05T00:00:00+00:00",
    )
    assert projection.status == "linked_prediction"
    assert projection.outcome_status == "conflict"
    assert "outcome_preflatten_contract_conflict" in projection.warnings


@pytest.mark.parametrize("nested_key", ["outcomes", "outcome"])
def test_projection_accepts_consistent_or_child_only_evidence_identity(
    nested_key: str,
) -> None:
    result = _result()
    child = {
        "result_id": RESULT_ID,
        "stock_code": STOCK_CODE,
        "personalization_scope_id": SCOPE_ID,
        "prediction_id": PREDICTION_ID,
        "prediction_receipt_hash": _receipt()["receipt_hash"],
        "event_id": "event_preflatten_exact",
        "outcome_id": "outcome_preflatten_exact",
        "event_price_date": "2025-02-10",
        "outcome_price_date": "2025-03-02",
        "label_available_date": "2025-03-02",
        "window_days": 20,
        "return_basis": RETURN_BASIS,
        "label_contract_id": LABEL_CONTRACT_ID,
        "cost_scenario_hash": RECEIPT_HASH_SEED,
        "label_available_at": "2025-03-02T00:00:00+00:00",
        "outcome_recorded_at": "2025-03-02T00:00:00+00:00",
        "outcome_status": "ready",
        "outcome_tier": "natural_forward",
        "label": 1,
    }
    event = {
        "result_id": RESULT_ID,
        "symbol": STOCK_CODE,
        "personalization_scope_id": SCOPE_ID,
        "prediction_id": PREDICTION_ID,
        "prediction_receipt_hash": _receipt()["receipt_hash"],
        "event_id": "event_preflatten_exact",
        "horizon_days": 20,
        "cost_scenario_hash": RECEIPT_HASH_SEED,
        "label_contract_id": LABEL_CONTRACT_ID,
        "return_basis": RETURN_BASIS,
        nested_key: [child] if nested_key == "outcomes" else child,
    }
    projection = PersonalizationProjectionService(
        evidence_reader={(RESULT_ID, STOCK_CODE): [event]},
    ).build_for_candidate(
        result_id=RESULT_ID,
        stock_code=STOCK_CODE,
        personalization_scope_id=SCOPE_ID,
        result=result,
        projection_receipt=_receipt(),
        evaluated_as_of="2025-03-05",
        evaluation_cutoff_at="2025-03-05T00:00:00+00:00",
    )
    assert projection.outcome_status == "ready"
    assert not any("preflatten" in warning for warning in projection.warnings)


def test_projection_keeps_parallel_evidence_windows_independent() -> None:
    result = _result()
    common = {
        "result_id": RESULT_ID,
        "stock_code": STOCK_CODE,
        "personalization_scope_id": SCOPE_ID,
        "prediction_id": PREDICTION_ID,
        "prediction_receipt_hash": _receipt()["receipt_hash"],
        "event_id": "event_parallel_windows",
        "return_basis": RETURN_BASIS,
        "label_contract_id": LABEL_CONTRACT_ID,
        "cost_scenario_hash": RECEIPT_HASH_SEED,
        "outcome_status": "ready",
        "outcome_tier": "natural_forward",
        "event_price_date": "2025-02-10",
        "outcome_price_date": "2025-03-02",
        "label_available_date": "2025-03-02",
        "label_available_at": "2025-03-02T00:00:00+00:00",
        "outcome_recorded_at": "2025-03-02T00:00:00+00:00",
        "label": 1,
    }
    expected = {**common, "outcome_id": "outcome_parallel_20", "window_days": 20}
    sibling = {
        **common,
        "outcome_id": "outcome_parallel_5",
        "window_days": 5,
        "label": 0,
    }
    event = {
        "result_id": RESULT_ID,
        "symbol": STOCK_CODE,
        "horizon_days": 20,
        "outcomes": [expected, sibling],
    }
    projection = PersonalizationProjectionService(
        evidence_reader={(RESULT_ID, STOCK_CODE): [event]},
    ).build_for_candidate(
        result_id=RESULT_ID,
        stock_code=STOCK_CODE,
        personalization_scope_id=SCOPE_ID,
        result=result,
        projection_receipt=_receipt(),
        evaluated_as_of="2025-03-05",
        evaluation_cutoff_at="2025-03-05T00:00:00+00:00",
    )
    assert projection.outcome_status == "ready"
    assert [row["outcome_id"] for row in projection.outcomes] == ["outcome_parallel_20"]
    assert "outcome_parallel_horizon_ignored" in projection.warnings
    assert "outcome_alias_conflict" not in projection.warnings


def test_scope_without_captured_at_is_unverified_and_cannot_create_capture() -> None:
    scope = PersonalizationDeliveryScope.create(
        scope_id=SCOPE_ID,
        scope_type="user",
        delivery_id="delivery_without_capture_clock",
        declared_at="2025-02-10T08:50:00+00:00",
        decision_at="2025-02-10T09:00:00+00:00",
        available_at="2025-02-10T08:55:00+00:00",
        receipt_created_at="2025-02-10T09:01:00+00:00",
    )
    assert scope.captured_at is None
    assert scope.temporal_status == "temporal_precision_unproven"
    with pytest.raises(PersonalizationProjectionError, match="captured_at"):
        PersonalizationDeliveryCaptureService().capture(
            scope=scope,
            request_id="request_without_capture_clock",
            result_id=RESULT_ID,
            stock_code=STOCK_CODE,
            projection_receipt_hash=_receipt()["receipt_hash"],
            generated_at="2025-02-10T08:50:00+00:00",
            prediction_id=PREDICTION_ID,
        )
