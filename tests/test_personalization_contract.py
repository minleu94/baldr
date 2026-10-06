from __future__ import annotations

import pytest

from app_module.personalization_contract import (
    PersonalizationActionEnvelope,
    PersonalizationDeliveryCapture,
    PersonalizationDeliveryScope,
    PersonalizationEvaluationRow,
    inspect_personalization_temporal_context,
    validate_forward_outcome_chronology,
)
from app_module.personalization_projection import PersonalizationDeliveryCaptureService


RECEIPT_HASH = "sha256:" + ("a" * 64)
PREDICTION_ID = "00000000-0000-0000-0000-000000000001"


def _scope() -> PersonalizationDeliveryScope:
    return PersonalizationDeliveryScope.create(
        scope_id="scope_user_001",
        scope_type="user",
        delivery_id="delivery_001",
        declared_at="2025-01-02T08:50:00+00:00",
        decision_at="2025-01-02T09:00:00+00:00",
        available_at="2025-01-02T08:55:00+00:00",
        captured_at="2025-01-02T08:55:00+00:00",
        receipt_created_at="2025-01-02T09:01:00+00:00",
    )


def test_scope_separates_pit_capture_clock_from_receipt_publication_clock() -> None:
    scope = _scope()

    assert scope.captured_at == "2025-01-02T08:55:00.000000+00:00"
    assert scope.receipt_created_at == "2025-01-02T09:01:00.000000+00:00"
    assert scope.envelope_hash.startswith("sha256:")
    assert PersonalizationDeliveryScope.from_mapping(scope.to_dict()) == scope

    with pytest.raises(ValueError, match="captured_at"):
        PersonalizationDeliveryScope.create(
            scope_id="scope_user_001",
            scope_type="user",
            delivery_id="delivery_future_capture",
            declared_at="2025-01-02T08:50:00+00:00",
            decision_at="2025-01-02T09:00:00+00:00",
            available_at="2025-01-02T08:55:00+00:00",
            captured_at="2025-01-02T09:00:01+00:00",
            receipt_created_at="2025-01-02T09:01:00+00:00",
        )

    unverified = PersonalizationDeliveryScope.create(
        scope_id="scope_user_001",
        scope_type="user",
        delivery_id="delivery_missing_capture_clock",
        declared_at="2025-01-02T08:50:00+00:00",
        decision_at="2025-01-02T09:00:00+00:00",
        available_at="2025-01-02T08:55:00+00:00",
        receipt_created_at="2025-01-02T09:01:00+00:00",
    )
    assert unverified.captured_at is None
    assert unverified.temporal_status == "temporal_precision_unproven"

    with pytest.raises(ValueError, match="available_at"):
        PersonalizationDeliveryScope.create(
            scope_id="scope_user_001",
            scope_type="user",
            delivery_id="delivery_future_available",
            declared_at="2025-01-02T08:50:00+00:00",
            decision_at="2025-01-02T09:00:00+00:00",
            available_at="2025-01-02T09:00:01+00:00",
            captured_at="2025-01-02T08:55:00+00:00",
            receipt_created_at="2025-01-02T09:01:00+00:00",
        )


def test_scope_and_evaluation_dates_use_taipei_market_calendar() -> None:
    scope = PersonalizationDeliveryScope.create(
        scope_id="scope_user_midnight",
        scope_type="user",
        delivery_id="delivery_midnight",
        declared_at="2025-02-09T16:20:00+00:00",
        available_at="2025-02-09T16:25:00+00:00",
        captured_at="2025-02-09T16:25:00+00:00",
        decision_at="2025-02-09T16:30:00+00:00",
        receipt_created_at="2025-02-09T16:31:00+00:00",
    )

    assert scope.decision_date == "2025-02-10"
    assert scope.available_date == "2025-02-10"

    row = PersonalizationEvaluationRow(
        prediction_id=PREDICTION_ID,
        scope_id=scope.scope_id,
        symbol="2330",
        decision_date="2025-02-10",
        label_available_date="2025-03-02",
        horizon_days=20,
        cost_scenario_hash=RECEIPT_HASH,
        population_probability_bp=5000,
        label=1,
        decision_at="2025-02-09T16:30:00+00:00",
        available_at="2025-02-09T16:25:00+00:00",
        captured_at="2025-02-09T16:25:00+00:00",
        receipt_created_at="2025-02-09T16:31:00+00:00",
        label_available_at="2025-03-01T16:10:00+00:00",
        outcome_recorded_at="2025-03-01T16:10:00+00:00",
        outcome_status="ready",
        delivery_status="delivered",
        outcome_tier="natural_forward",
    )

    assert row.to_dict()["decision_date"] == "2025-02-10"
    assert row.to_dict()["label_available_date"] == "2025-03-02"


def test_temporal_markers_without_clocks_scope_or_receipt_never_verify() -> None:
    state, warnings = inspect_personalization_temporal_context(
        {
            "temporal_contract": "recommendation-producer-clock.v1",
            "temporal_mode": "natural_producer_clock",
            "cutoff_selection": "producer_selected_latest_available_cutoff",
            "cutoff_policy": "source_latest_available_exact",
            "decision_clock_timezone": "UTC",
            "market_calendar_timezone": "Asia/Taipei",
            "prediction_decision_anchor": "actual_producer_decision_at",
            "horizon_anchor": "immutable_projection_receipt",
            "as_of_date": "2025-02-10",
            "data_date": "2025-02-10",
        },
        actual_decision_date="2025-02-10",
    )

    assert state == "invalid"
    assert "run_started_at_missing" in warnings
    assert "temporal_scope_missing" in warnings
    assert "temporal_receipt_hash_missing" in warnings


def test_forward_outcome_requires_explicit_price_and_label_anchors() -> None:
    warnings = validate_forward_outcome_chronology(
        {
            "label_available_at": "2025-03-02T00:00:00+00:00",
            "outcome_recorded_at": "2025-03-02T00:00:00+00:00",
        },
        decision_at="2025-02-10T09:00:00+00:00",
        decision_date="2025-02-10",
    )

    assert "outcome_event_price_date_missing" in warnings
    assert "outcome_price_date_missing" in warnings
    assert "label_available_date_missing" in warnings


def test_delivery_capture_is_immutable_and_retry_keeps_prediction_identity() -> None:
    service = PersonalizationDeliveryCaptureService()
    generated = service.capture(
        scope=_scope(),
        request_id="request_001",
        result_id="rec_001",
        stock_code="2330",
        projection_receipt_hash=RECEIPT_HASH,
        generated_at="2025-01-02T08:50:00+00:00",
        prediction_id=PREDICTION_ID,
        model_id="model_001",
        dataset_id="dataset_001",
        cost_scenario_hash=RECEIPT_HASH,
        horizon_days=20,
    )
    persisted = service.mark_persisted(
        generated,
        persisted_at="2025-01-02T08:56:00+00:00",
    )
    delivered = service.mark_delivered(
        persisted,
        delivered_at="2025-01-02T08:59:00+00:00",
    )

    assert generated.status == "generated"
    assert persisted.status == "persisted"
    assert delivered.status == "delivered"
    assert generated.capture_hash != persisted.capture_hash != delivered.capture_hash
    assert service.retry_is_same_identity(delivered, delivered)
    assert not service.retry_is_same_identity(
        delivered,
        service.capture(
            scope=_scope(),
            request_id="request_002",
            result_id="rec_001",
            stock_code="2330",
            projection_receipt_hash=RECEIPT_HASH,
            generated_at="2025-01-02T08:50:00+00:00",
            prediction_id="00000000-0000-0000-0000-000000000002",
        ),
    )

    with pytest.raises(ValueError, match="delivered capture"):
        service.mark_persisted(delivered, persisted_at="2025-01-02T09:00:00+00:00")

    retryable = generated.mark_not_delivered()
    retried_persisted = service.mark_persisted(
        retryable,
        persisted_at="2025-01-02T08:57:00+00:00",
    )
    assert retried_persisted.prediction_id == generated.prediction_id
    assert retried_persisted.request_id == generated.request_id


def test_action_envelope_and_evaluation_row_require_explicit_contract_fields() -> None:
    action = PersonalizationActionEnvelope(
        personalization_scope_id="scope_user_001",
        result_id="rec_001",
        stock_code="2330",
        prediction_id=PREDICTION_ID,
        prediction_receipt_hash=RECEIPT_HASH,
        decision_kind="research_review",
        action="accepted",
        action_state="recorded",
        action_at="2025-01-02T09:02:00+00:00",
        recorded_at="2025-01-02T09:03:00+00:00",
        request_id="request_action_001",
    )
    action_payload = action.to_dict()
    action_payload.pop("envelope_hash")
    assert PersonalizationActionEnvelope(**action_payload).envelope_hash == action.envelope_hash

    row = PersonalizationEvaluationRow(
        prediction_id=PREDICTION_ID,
        scope_id="scope_user_001",
        symbol="2330",
        decision_date="2025-01-02",
        label_available_date="2025-01-22",
        horizon_days=20,
        cost_scenario_hash=RECEIPT_HASH,
        population_probability_bp=5000,
        label=1,
        decision_at="2025-01-02T09:00:00+00:00",
        available_at="2025-01-02T08:55:00+00:00",
        captured_at="2025-01-02T08:55:00+00:00",
        receipt_created_at="2025-01-02T09:01:00+00:00",
        outcome_status="ready",
        delivery_status="delivered",
        outcome_tier="natural_forward",
    )
    assert row.to_dict()["delivery_status"] == "delivered"
    assert row.to_dict()["late_delivery"] is False
