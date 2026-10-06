from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from collections.abc import Mapping
from dataclasses import FrozenInstanceError, replace
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from threading import Barrier
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock

import pandas as pd
import pytest

from app_module.recommendation.contracts import (
    MLAvailabilityReason,
    MLAvailabilityStatus,
    ReferenceKind,
)
from app_module.recommendation.execute import _safe_contract_value
from app_module.recommendation.ml_postcalibration_handoff import (
    CalibrationProjectionStatusV1,
    CalibrationReceiptEventFactsV1,
    CalibrationReceiptStatusV1,
    RecommendationPostCalibrationHandoffSinkV1,
    RecommendationPostCalibrationHandoffV1,
    encode_candidate_identity_event_json_v1,
    ml_availability_from_handoff_v1,
    verified_receipt_references_v1,
)
from app_module.recommendation.execute import execute_recommendation
from app_module.recommendation_service import RecommendationService
from recommendation_test_support import build_recommendation_test_preparer


_HASH_A = "sha256:" + "a" * 64
_HASH_B = "sha256:" + "b" * 64


def _receipt_event(
    *,
    identity_verified: bool = True,
    readback_verified: bool = True,
    persisted: bool = True,
    **overrides: object,
) -> CalibrationReceiptEventFactsV1:
    values: dict[str, object] = {
        "payload_present": True,
        "attempted": True,
        "persisted": persisted,
        "readback_verified": readback_verified,
        "identity_verified": identity_verified,
        "path": "C:/learning/inference_projection/2026-09-24/candidate-A/receipt.json",
        "receipt_hash": _HASH_A,
        "receipt_created_at": "2026-09-25T12:00:00+00:00",
        "result_id": "result-A",
        "decision_date": "2026-09-24",
        "candidate_id": "candidate-A",
        "candidate_identity_json": encode_candidate_identity_event_json_v1(
            {
                "candidate_id": "candidate-A",
                "candidate_manifest_hash": _HASH_B,
                "pointer_version": "pointer-7",
                "nested": {
                    "lane": "legacy-shadow",
                    "ratio": 0.1,
                    "samples": [1.25, {"score": 0.3}],
                },
            }
        ),
        "cost_scenario_hash": _HASH_B,
        "cost_scenario_id": "cost-A",
        "projected_stock_codes": ("2330", "2317"),
        "projection_rows_sha256": _HASH_B,
        "inference_source_hash": "source-hash",
        "inference_pit_hash": "pit-hash",
        "feature_rows_sha256": "feature-rows-hash",
    }
    values.update(overrides)
    return CalibrationReceiptEventFactsV1(**values)  # type: ignore[arg-type]


def _successful_handoff(
    *,
    identity_verified: bool = True,
    receipt: CalibrationReceiptEventFactsV1 | None = None,
) -> RecommendationPostCalibrationHandoffV1:
    return RecommendationPostCalibrationHandoffV1(
        consumer_configured=True,
        attempted=True,
        projection_status=CalibrationProjectionStatusV1.ACTIVE_CANDIDATE,
        receipt_status=CalibrationReceiptStatusV1.PERSISTED,
        receipt_event=receipt
        or _receipt_event(identity_verified=identity_verified),
    )


def _execution_service(
    tmp_path: Path,
    *,
    consumer: object | None,
    include_rows: bool = True,
) -> RecommendationService:
    rows = [
        {
            "日期": date(2026, 5, 1) + timedelta(days=offset),
            "available_date": date(2026, 5, 1) + timedelta(days=offset),
            "證券代號": "AAA",
            "證券名稱": "AAA_NAME",
            "收盤價": Decimal("100.00"),
            "成交股數": 1_000,
        }
        for offset in range(20)
    ] if include_rows else []
    frame = pd.DataFrame(
        rows,
        columns=(
            "日期",
            "available_date",
            "證券代號",
            "證券名稱",
            "收盤價",
            "成交股數",
        ),
    )
    market_data_provider = lambda: frame.copy(deep=True)
    config = SimpleNamespace(
        db_file=tmp_path / "missing-fundamentals.db",
        use_sqlite=False,
        pit_market_scope="twse_listed",
    )
    service = RecommendationService(
        config,
        industry_mapper=MagicMock(),
        market_data_provider=market_data_provider,
        regime_detector=MagicMock(),
        calibration_consumer=cast(Any, consumer),
        input_preparer=build_recommendation_test_preparer(
            config,
            market_data_provider=market_data_provider,
        ),
    )
    service.reason_engine = MagicMock()
    service.reason_engine.generate_reasons.return_value = []
    service.reason_engine.format_reason_text.return_value = ""
    setattr(
        service.strategy_configurator,
        "generate_recommendations",
        lambda _frame, _config: pd.DataFrame(
            {
                "TotalScore": [Decimal("88.50")],
                "FinalScore": [Decimal("88.50")],
                "收盤價": [Decimal("100.00")],
                "成交股數": [1_000],
            }
        ),
    )
    return service


def _invocation_sink(
    service: RecommendationService,
) -> RecommendationPostCalibrationHandoffSinkV1:
    sink = getattr(service, "_r026_post_calibration_handoff_sink", None)
    assert type(sink) is RecommendationPostCalibrationHandoffSinkV1
    return cast(RecommendationPostCalibrationHandoffSinkV1, sink)


def _mock_receipt_handoff(
    service: RecommendationService,
    recommendations: list[Any],
    *,
    decision_date: str,
    identity_verified: bool = True,
    event_error: str = "",
) -> RecommendationPostCalibrationHandoffV1:
    result_id = str(service.last_run_context.get("result_id") or "")
    candidate_id = f"candidate-{result_id}"
    codes = tuple(str(item.stock_code) for item in recommendations)
    event = CalibrationReceiptEventFactsV1(
        payload_present=True,
        attempted=True,
        persisted=True,
        readback_verified=True,
        identity_verified=identity_verified,
        path=f"C:/synthetic-receipts/{result_id}.json",
        receipt_hash=_HASH_A,
        error=event_error,
        result_id=result_id,
        decision_date=decision_date,
        candidate_id=candidate_id,
        candidate_identity_json=encode_candidate_identity_event_json_v1(
            {"candidate_id": candidate_id, "pointer_version": result_id}
        ),
        projected_stock_codes=codes,
        projection_rows_sha256=_HASH_B,
    )
    return RecommendationPostCalibrationHandoffV1(
        consumer_configured=service.calibration_consumer is not None,
        attempted=True,
        projection_status=CalibrationProjectionStatusV1.ACTIVE_CANDIDATE,
        receipt_status=CalibrationReceiptStatusV1.PERSISTED,
        receipt_event=event,
    )


def _execute_one(
    service: RecommendationService,
    result_id: str,
    *,
    cancel: Any = None,
    capture_sink: dict[str, Any] | None = None,
) -> Any:
    return execute_recommendation(
        service,
        {
            "recommendation_ranking": {"threshold_mode": "fixed"},
            "as_of_date": "2026-05-20",
        },
        max_stocks=1,
        top_n=1,
        universe=["AAA"],
        result_id=result_id,
        cancel=cancel,
        capture_sink=capture_sink,
    )


def _plain_contract_value(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _plain_contract_value(item) for key, item in value.items()}
    if type(value) in (list, tuple):
        return tuple(_plain_contract_value(item) for item in value)
    return value


def test_postcalibration_sink_is_single_publish_and_invocation_local() -> None:
    sink_a = RecommendationPostCalibrationHandoffSinkV1()
    sink_b = RecommendationPostCalibrationHandoffSinkV1()
    facts_a = _successful_handoff()
    facts_b = _successful_handoff(
        receipt=_receipt_event(
            identity_verified=False,
            path="C:/learning/receipt-B.json",
            result_id="result-B",
            candidate_id="candidate-B",
            candidate_identity_json=encode_candidate_identity_event_json_v1(
                {"candidate_id": "candidate-B"}
            ),
        )
    )

    sink_a.publish(facts_a)
    sink_b.publish(facts_b)

    assert sink_a.snapshot() is facts_a
    assert sink_b.snapshot() is facts_b
    assert sink_a.snapshot().receipt_event.path.endswith("receipt.json")  # type: ignore[union-attr]
    assert sink_b.snapshot().receipt_event.path.endswith("receipt-B.json")  # type: ignore[union-attr]
    with pytest.raises(RuntimeError, match="已發布"):
        sink_a.publish(facts_b)
    with pytest.raises(FrozenInstanceError):
        facts_a.attempted = False  # type: ignore[misc]


def test_unpublished_sink_preserves_initial_consumer_configuration() -> None:
    sink = RecommendationPostCalibrationHandoffSinkV1(consumer_configured=True)
    baseline = sink.snapshot()

    assert baseline.consumer_configured is True
    assert baseline.attempted is False
    assert ml_availability_from_handoff_v1(
        handoff=baseline,
        bindings=(),
        recommendation_count=1,
    ).status is MLAvailabilityStatus.UNKNOWN


def test_receipt_event_details_preserve_existing_summary_fields() -> None:
    details = _receipt_event().event_details()

    assert details == {
        "attempted": True,
        "persisted": True,
        "readback_verified": True,
        "identity_verified": True,
        "path": "C:/learning/inference_projection/2026-09-24/candidate-A/receipt.json",
        "receipt_hash": _HASH_A,
        "receipt_created_at": "2026-09-25T12:00:00+00:00",
        "error": "",
        "result_id": "result-A",
        "decision_date": "2026-09-24",
        "candidate_id": "candidate-A",
        "candidate_identity": {
            "candidate_id": "candidate-A",
            "candidate_manifest_hash": _HASH_B,
            "pointer_version": "pointer-7",
            "nested": {
                "lane": "legacy-shadow",
                "ratio": Decimal("0.1"),
                "samples": (
                    Decimal("1.25"),
                    {"score": Decimal("0.3")},
                ),
            },
        },
        "cost_scenario_hash": _HASH_B,
        "cost_scenario_id": "cost-A",
        "projected_stock_codes": ("2330", "2317"),
        "projection_rows_sha256": _HASH_B,
        "inference_source_hash": "source-hash",
        "inference_pit_hash": "pit-hash",
        "feature_rows_sha256": "feature-rows-hash",
        "receipt_body_hash_verified": True,
    }


def test_receipt_build_error_event_has_only_base_details() -> None:
    event = CalibrationReceiptEventFactsV1(error="ValueError: receipt build failed")

    assert event.event_details() == {
        "attempted": False,
        "persisted": False,
        "readback_verified": False,
        "identity_verified": False,
        "path": "",
        "receipt_hash": "",
        "receipt_created_at": "",
        "error": "ValueError: receipt build failed",
    }


def test_verified_readback_keeps_refs_when_active_identity_check_failed() -> None:
    handoff = _successful_handoff(identity_verified=False)
    bindings, projection_refs = verified_receipt_references_v1(
        handoff=handoff,
        result_id="result-A",
        context_date=date(2026, 9, 24),
    )

    assert len(bindings) == 1
    assert bindings[0].model_candidate_id == "candidate-A"
    assert bindings[0].projected_stock_codes == ("2330", "2317")
    assert bindings[0].receipt_ref.kind is ReferenceKind.ML_RECEIPT
    assert bindings[0].receipt_ref.reference_id.endswith("receipt.json")
    assert len(projection_refs) == 1
    assert projection_refs[0].kind is ReferenceKind.ML_PROJECTION
    assert projection_refs[0].reference_id == _HASH_B
    availability = ml_availability_from_handoff_v1(
        handoff=handoff,
        bindings=bindings,
        recommendation_count=2,
    )
    assert availability.status is MLAvailabilityStatus.UNAVAILABLE
    assert availability.reason is MLAvailabilityReason.SOURCE_VERSION_UNAVAILABLE
    assert availability.reason_detail == "active_candidate_identity_not_verified"


def test_available_requires_identity_even_when_receipt_refs_are_valid() -> None:
    handoff = _successful_handoff(identity_verified=False)
    bindings, _ = verified_receipt_references_v1(
        handoff=handoff,
        result_id="result-A",
        context_date=date(2026, 9, 24),
    )

    assert bindings
    assert ml_availability_from_handoff_v1(
        handoff=handoff,
        bindings=bindings,
        recommendation_count=2,
    ).status is MLAvailabilityStatus.UNAVAILABLE


@pytest.mark.parametrize(
    ("receipt_changes", "result_id", "context_date"),
    [
        ({"readback_verified": False}, "result-A", date(2026, 9, 24)),
        ({"payload_present": False}, "result-A", date(2026, 9, 24)),
        ({"path": ""}, "result-A", date(2026, 9, 24)),
        ({"receipt_hash": ""}, "result-A", date(2026, 9, 24)),
        (
            {
                "candidate_id": "",
                "candidate_identity_json": encode_candidate_identity_event_json_v1(
                    {"candidate_id": ""}
                ),
            },
            "result-A",
            date(2026, 9, 24),
        ),
        ({"result_id": "other-result"}, "result-A", date(2026, 9, 24)),
        ({"decision_date": "not-a-date"}, "result-A", date(2026, 9, 24)),
        ({"projected_stock_codes": ()}, "result-A", date(2026, 9, 24)),
        ({"projected_stock_codes": ("",)}, "result-A", date(2026, 9, 24)),
        ({}, "result-A", date(2026, 9, 23)),
        ({"receipt_hash": "not-a-sha256"}, "result-A", date(2026, 9, 24)),
        ({"cost_scenario_hash": "not-a-sha256"}, "result-A", date(2026, 9, 24)),
    ],
)
def test_receipt_refs_fail_closed_when_required_binding_fact_is_invalid(
    receipt_changes: dict[str, object],
    result_id: str,
    context_date: date,
) -> None:
    handoff = _successful_handoff(
        receipt=replace(_receipt_event(), **receipt_changes)  # type: ignore[arg-type]
    )

    assert verified_receipt_references_v1(
        handoff=handoff,
        result_id=result_id,
        context_date=context_date,
    ) == ((), ())


def test_projection_reference_is_optional_when_receipt_binding_is_valid() -> None:
    handoff = _successful_handoff(
        receipt=replace(_receipt_event(), projection_rows_sha256="")
    )

    bindings, projection_refs = verified_receipt_references_v1(
        handoff=handoff,
        result_id="result-A",
        context_date=date(2026, 9, 24),
    )

    assert len(bindings) == 1
    assert projection_refs == ()


def test_empty_stock_codes_remain_in_event_and_candidate_cost_is_not_fallback() -> None:
    event = replace(
        _receipt_event(),
        candidate_identity_json=encode_candidate_identity_event_json_v1(
            {
                "candidate_id": "candidate-A",
                "cost_scenario_hash": _HASH_B,
            }
        ),
        projected_stock_codes=("", "2330"),
        cost_scenario_hash="",
    )
    handoff = _successful_handoff(receipt=event)

    assert event.event_details()["projected_stock_codes"] == ("", "2330")
    bindings, _ = verified_receipt_references_v1(
        handoff=handoff,
        result_id="result-A",
        context_date=date(2026, 9, 24),
    )
    assert bindings == ()

    without_empty = replace(event, projected_stock_codes=("2330",))
    handoff_without_empty = _successful_handoff(receipt=without_empty)
    bindings, _ = verified_receipt_references_v1(
        handoff=handoff_without_empty,
        result_id="result-A",
        context_date=date(2026, 9, 24),
    )
    assert len(bindings) == 1
    assert bindings[0].cost_scenario_hash is None


@pytest.mark.parametrize(
    ("handoff", "recommendation_count", "expected_status", "expected_reason"),
    [
        (
            None,
            2,
            MLAvailabilityStatus.NOT_REQUESTED,
            None,
        ),
        (
            RecommendationPostCalibrationHandoffV1(
                consumer_configured=True,
                attempted=False,
            ),
            0,
            MLAvailabilityStatus.NOT_REQUESTED,
            None,
        ),
        (
            RecommendationPostCalibrationHandoffV1(
                consumer_configured=True,
                attempted=False,
            ),
            2,
            MLAvailabilityStatus.UNKNOWN,
            None,
        ),
        (
            RecommendationPostCalibrationHandoffV1(
                consumer_configured=True,
                attempted=True,
                projection_status=CalibrationProjectionStatusV1.UNAVAILABLE,
                receipt_status=CalibrationReceiptStatusV1.UNAVAILABLE,
            ),
            2,
            MLAvailabilityStatus.UNAVAILABLE,
            MLAvailabilityReason.MISSING,
        ),
        (
            _successful_handoff(identity_verified=False),
            2,
            MLAvailabilityStatus.UNAVAILABLE,
            MLAvailabilityReason.SOURCE_VERSION_UNAVAILABLE,
        ),
        (
            _successful_handoff(identity_verified=True),
            2,
            MLAvailabilityStatus.AVAILABLE,
            None,
        ),
    ],
)
def test_availability_states_cover_absence_failure_and_identity(
    handoff: RecommendationPostCalibrationHandoffV1 | None,
    recommendation_count: int,
    expected_status: MLAvailabilityStatus,
    expected_reason: MLAvailabilityReason | None,
) -> None:
    bindings, _ = verified_receipt_references_v1(
        handoff=handoff,
        result_id="result-A",
        context_date=date(2026, 9, 24),
    )

    availability = ml_availability_from_handoff_v1(
        handoff=handoff,
        bindings=bindings,
        recommendation_count=recommendation_count,
    )

    assert availability.status is expected_status
    assert availability.reason is expected_reason


def test_unavailable_reason_detail_preserves_receipt_then_projection_fallback() -> None:
    handoff = RecommendationPostCalibrationHandoffV1(
        consumer_configured=True,
        attempted=True,
        projection_status=CalibrationProjectionStatusV1.UNAVAILABLE,
        receipt_status=CalibrationReceiptStatusV1.UNAVAILABLE,
        receipt_error_detail="OSError: readback failed",
    )
    availability = ml_availability_from_handoff_v1(
        handoff=handoff,
        bindings=(),
        recommendation_count=1,
    )
    assert availability.reason_detail == "OSError: readback failed"

    fallback = replace(handoff, receipt_error_detail=None)
    availability = ml_availability_from_handoff_v1(
        handoff=fallback,
        bindings=(),
        recommendation_count=1,
    )
    assert availability.reason_detail == "unavailable"


@pytest.mark.parametrize(
    (
        "receipt_event",
        "receipt_error_detail",
        "expected_reason",
        "expected_detail",
    ),
    [
        (
            CalibrationReceiptEventFactsV1(
                error="ValueError: receipt build failed"
            ),
            "receipt build failed",
            MLAvailabilityReason.MISSING,
            "receipt build failed",
        ),
        (
            CalibrationReceiptEventFactsV1(
                payload_present=True,
                attempted=True,
                error="OSError: receipt write failed",
                result_id="result-A",
                decision_date="2026-09-24",
                candidate_id="candidate-A",
                candidate_identity_json=encode_candidate_identity_event_json_v1(
                    {"candidate_id": "candidate-A"}
                ),
            ),
            "receipt write failed",
            MLAvailabilityReason.MISSING,
            "receipt write failed",
        ),
        (
            _receipt_event(
                persisted=True,
                readback_verified=False,
                identity_verified=False,
                error="RecommendationProvenanceError: readback failed",
            ),
            "readback failed",
            MLAvailabilityReason.SOURCE_VERSION_UNAVAILABLE,
            "RecommendationProvenanceError: readback failed",
        ),
    ],
)
def test_receipt_stage_failures_keep_stage_specific_availability(
    receipt_event: CalibrationReceiptEventFactsV1,
    receipt_error_detail: str,
    expected_reason: MLAvailabilityReason,
    expected_detail: str,
) -> None:
    handoff = RecommendationPostCalibrationHandoffV1(
        consumer_configured=True,
        attempted=True,
        projection_status=CalibrationProjectionStatusV1.UNAVAILABLE,
        receipt_status=CalibrationReceiptStatusV1.UNAVAILABLE,
        receipt_error_detail=receipt_error_detail,
        receipt_event=receipt_event,
    )
    bindings, projection_refs = verified_receipt_references_v1(
        handoff=handoff,
        result_id="result-A",
        context_date=date(2026, 9, 24),
    )

    assert bindings == ()
    assert projection_refs == ()
    availability = ml_availability_from_handoff_v1(
        handoff=handoff,
        bindings=bindings,
        recommendation_count=1,
    )
    assert availability.status is MLAvailabilityStatus.UNAVAILABLE
    assert availability.reason is expected_reason
    assert availability.reason_detail == expected_detail


def test_rule_only_projection_remains_unknown_without_receipt_failure() -> None:
    handoff = RecommendationPostCalibrationHandoffV1(
        consumer_configured=True,
        attempted=True,
        projection_status=CalibrationProjectionStatusV1.RULE_ONLY,
    )

    assert ml_availability_from_handoff_v1(
        handoff=handoff,
        bindings=(),
        recommendation_count=1,
    ).status is MLAvailabilityStatus.UNKNOWN


def test_receipt_event_candidate_identity_bytes_are_canonical_and_typed() -> None:
    payload = {
        "candidate_id": "candidate-A",
        "pointer_version": "v1",
        "nested": [0.1, {"ratio": 1.25}],
    }
    encoded = encode_candidate_identity_event_json_v1(payload)
    event = CalibrationReceiptEventFactsV1(
        payload_present=True,
        candidate_id="candidate-A",
        candidate_identity_json=encoded,
    )

    projected_candidate = event.event_details()["candidate_identity"]
    assert projected_candidate == _safe_contract_value(payload)
    assert projected_candidate == {
        "candidate_id": "candidate-A",
        "pointer_version": "v1",
        "nested": (Decimal("0.1"), {"ratio": Decimal("1.25")}),
    }
    with pytest.raises(ValueError, match="canonical"):
        CalibrationReceiptEventFactsV1(
            payload_present=True,
            candidate_id="candidate-A",
            candidate_identity_json=b'{ "candidate_id" : "candidate-A" }',
        )
    with pytest.raises(ValueError, match="與 candidate_id 不一致"):
        CalibrationReceiptEventFactsV1(
            payload_present=True,
            candidate_id="candidate-B",
            candidate_identity_json=encoded,
        )


def test_execute_uses_typed_facts_when_legacy_context_claims_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _execution_service(tmp_path, consumer=object())

    def typed_success(
        invocation: RecommendationService,
        recommendations: list[Any],
        **kwargs: Any,
    ) -> None:
        sink = _invocation_sink(invocation)
        sink.publish(
            _mock_receipt_handoff(
                invocation,
                recommendations,
                decision_date=str(kwargs["decision_date"]),
            )
        )
        invocation.last_run_context["calibration_projection_status"] = "unavailable"
        invocation.last_run_context[
            "calibration_projection_receipt_status"
        ] = "unavailable"
        invocation.last_run_context[
            "calibration_projection_receipt_error_detail"
        ] = "poisoned legacy context"

    monkeypatch.setattr(
        RecommendationService,
        "_apply_recommendation_calibration",
        typed_success,
    )

    execution = _execute_one(service, "typed-success")

    assert execution.status.value == "completed"
    assert execution.ml_availability.status is MLAvailabilityStatus.AVAILABLE
    assert len(execution.ml_receipt_refs) == 1
    assert execution.ml_receipt_refs[0].model_candidate_id == "candidate-typed-success"
    assert len(execution.ml_projection_refs) == 1
    event = next(
        event
        for event in execution.events
        if event.event_type == "ml_projection_receipt_capture"
    )
    assert event.details["result_id"] == "typed-success"
    assert event.details["identity_verified"] is True
    assert event.details["path"].endswith("typed-success.json")


def test_failed_body_keeps_typed_receipt_before_error_event(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _execution_service(tmp_path, consumer=object())

    def typed_identity_failure(
        invocation: RecommendationService,
        recommendations: list[Any],
        **kwargs: Any,
    ) -> None:
        _invocation_sink(invocation).publish(
            _mock_receipt_handoff(
                invocation,
                recommendations,
                decision_date=str(kwargs["decision_date"]),
                identity_verified=False,
                event_error="active candidate changed",
            )
        )

    monkeypatch.setattr(
        RecommendationService,
        "_apply_recommendation_calibration",
        typed_identity_failure,
    )
    original_body = RecommendationService._run_recommendation_body_result

    def fail_after_body(
        invocation: RecommendationService,
        **kwargs: Any,
    ) -> Any:
        original_body(invocation, **kwargs)
        raise RuntimeError("failure after calibration body")

    monkeypatch.setattr(
        RecommendationService,
        "_run_recommendation_body_result",
        fail_after_body,
    )

    execution = _execute_one(service, "typed-failed-body")

    assert execution.status.value == "failed"
    assert execution.decision is None
    assert len(execution.ml_receipt_refs) == 1
    assert execution.ml_availability.status is MLAvailabilityStatus.UNAVAILABLE
    event_types = [event.event_type for event in execution.events]
    assert event_types.index("ml_projection_receipt_capture") < event_types.index(
        "recommendation_execution_error"
    )
    receipt_event = next(
        event
        for event in execution.events
        if event.event_type == "ml_projection_receipt_capture"
    )
    assert receipt_event.details["identity_verified"] is False
    assert receipt_event.details["error"] == "active candidate changed"


def test_cancel_after_body_keeps_typed_receipt_before_cancel_event(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _execution_service(tmp_path, consumer=object())

    def typed_success(
        invocation: RecommendationService,
        recommendations: list[Any],
        **kwargs: Any,
    ) -> None:
        _invocation_sink(invocation).publish(
            _mock_receipt_handoff(
                invocation,
                recommendations,
                decision_date=str(kwargs["decision_date"]),
            )
        )

    monkeypatch.setattr(
        RecommendationService,
        "_apply_recommendation_calibration",
        typed_success,
    )
    cancel_checks = 0

    def cancel_after_body() -> bool:
        nonlocal cancel_checks
        cancel_checks += 1
        return cancel_checks > 1

    capture: dict[str, Any] = {}
    execution = _execute_one(
        service,
        "typed-cancelled",
        cancel=cancel_after_body,
        capture_sink=capture,
    )

    assert execution.status.value == "cancelled"
    assert execution.decision is None
    assert len(execution.ml_receipt_refs) == 1
    event_types = [event.event_type for event in execution.events]
    assert event_types.index("ml_projection_receipt_capture") < event_types.index(
        "recommendation_execution_cancelled"
    )
    negative_evidence_event = next(
        event
        for event in execution.events
        if event.event_type == "legacy_negative_evidence_capture"
    )
    assert negative_evidence_event.message == (
        "Negative-evidence typed assessments 以外的原始 matrix 欄位保存在同次 invocation capture。"
    )
    compatibility_snapshot = capture["compatibility_snapshot"]
    assert compatibility_snapshot is not None
    legacy_state = compatibility_snapshot.materialize()
    for event_field, state_field in (
        ("screening_matrix", "last_screening_matrix"),
        ("excluded_candidates", "last_excluded_candidates_json"),
        ("why_not_payload", "last_why_not_payload_json"),
        ("liquidity_gate_payload", "last_liquidity_gate_payload_json"),
        ("exclusion_quality", "last_exclusion_quality"),
        ("exclusion_warnings", "last_exclusion_warnings_json"),
    ):
        assert _plain_contract_value(negative_evidence_event.details[event_field]) == (
            _plain_contract_value(_safe_contract_value(legacy_state[state_field]))
        )


def test_ab_interleaved_invocations_keep_separate_typed_receipts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _execution_service(tmp_path, consumer=object())
    publish_barrier = Barrier(2)

    def interleaved_producer(
        invocation: RecommendationService,
        recommendations: list[Any],
        **kwargs: Any,
    ) -> None:
        result_id = str(invocation.last_run_context.get("result_id") or "")
        publish_barrier.wait(timeout=10)
        _invocation_sink(invocation).publish(
            _mock_receipt_handoff(
                invocation,
                recommendations,
                decision_date=str(kwargs["decision_date"]),
                identity_verified=result_id == "typed-A",
            )
        )

    monkeypatch.setattr(
        RecommendationService,
        "_apply_recommendation_calibration",
        interleaved_producer,
    )

    with ThreadPoolExecutor(max_workers=2) as executor:
        future_a = executor.submit(_execute_one, service, "typed-A")
        future_b = executor.submit(_execute_one, service, "typed-B")
        execution_a = future_a.result(timeout=20)
        execution_b = future_b.result(timeout=20)

    assert execution_a.ml_receipt_refs[0].result_id == "typed-A"
    assert execution_b.ml_receipt_refs[0].result_id == "typed-B"
    assert execution_a.ml_receipt_refs[0].model_candidate_id == "candidate-typed-A"
    assert execution_b.ml_receipt_refs[0].model_candidate_id == "candidate-typed-B"
    event_a = next(
        event
        for event in execution_a.events
        if event.event_type == "ml_projection_receipt_capture"
    )
    event_b = next(
        event
        for event in execution_b.events
        if event.event_type == "ml_projection_receipt_capture"
    )
    assert event_a.details["result_id"] == "typed-A"
    assert event_b.details["result_id"] == "typed-B"
    assert event_a.details["path"] != event_b.details["path"]
    assert execution_a.ml_availability.status is MLAvailabilityStatus.AVAILABLE
    assert execution_b.ml_availability.status is MLAvailabilityStatus.UNAVAILABLE


def test_execute_uses_seeded_configuration_when_no_calibration_handoff_is_published(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _execution_service(tmp_path, consumer=object())

    def no_handoff(
        _invocation: RecommendationService,
        _recommendations: list[Any],
        **_kwargs: Any,
    ) -> None:
        return None

    monkeypatch.setattr(
        RecommendationService,
        "_apply_recommendation_calibration",
        no_handoff,
    )

    execution = _execute_one(service, "typed-no-stage")

    assert execution.ml_availability.status is MLAvailabilityStatus.UNKNOWN


def test_empty_body_and_unconfigured_consumer_remain_not_requested(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    empty_service = _execution_service(
        tmp_path / "empty",
        consumer=object(),
        include_rows=False,
    )
    unconfigured_service = _execution_service(
        tmp_path / "unconfigured",
        consumer=None,
    )

    def no_handoff(
        _invocation: RecommendationService,
        _recommendations: list[Any],
        **_kwargs: Any,
    ) -> None:
        return None

    monkeypatch.setattr(
        RecommendationService,
        "_apply_recommendation_calibration",
        no_handoff,
    )

    empty_execution = _execute_one(empty_service, "typed-empty")
    unconfigured_execution = _execute_one(unconfigured_service, "typed-no-consumer")

    assert empty_execution.status.value == "completed"
    assert empty_execution.items == ()
    assert empty_execution.ml_availability.status is MLAvailabilityStatus.NOT_REQUESTED
    assert unconfigured_execution.ml_availability.status is MLAvailabilityStatus.NOT_REQUESTED
