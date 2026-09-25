"""R019 Stage 3B canonical DecisionBatch handoff regression coverage."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from threading import Barrier, Lock, local
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

from app_module.recommendation.codec import decode_execution, encode_execution
from app_module.recommendation import execute as execute_module
from app_module.recommendation.contracts import (
    ExecutionStatus,
    MLAvailabilityStatus,
    QualityStatus,
)
from app_module.recommendation.execute import execute_recommendation
from app_module.recommendation.body_result import RecommendationBodyResult
from app_module.recommendation_service import RecommendationService
from decision_module.recommendation.contracts import DecisionBatch
from recommendation_test_support import build_recommendation_test_preparer


class _FrameProvider:
    def __init__(self, frame: pd.DataFrame) -> None:
        self.frame = frame

    def __call__(self) -> pd.DataFrame:
        return self.frame.copy(deep=True)


class _InterleavedFrameProvider:
    def __init__(self, frames: dict[str, pd.DataFrame]) -> None:
        self.frames = frames
        self.barrier = Barrier(2)
        self.invocation = local()

    def __call__(self) -> pd.DataFrame:
        run_id = self.invocation.run_id
        self.barrier.wait(timeout=5)
        return self.frames[run_id].copy(deep=True)


def _market_frame(
    code: str,
    *,
    start: date = date(2026, 5, 1),
    days: int = 20,
) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "日期": current,
                "available_date": current,
                "證券代號": code,
                "證券名稱": f"{code}_NAME",
                "收盤價": Decimal("100.00"),
                "成交股數": 1_000,
            }
            for current in (start + timedelta(days=offset) for offset in range(days))
        ]
    )


def _service(
    tmp_path: Path,
    codes: tuple[str, ...],
    scores: dict[str, object],
    *,
    provider: object | None = None,
) -> RecommendationService:
    frame = (
        pd.concat([_market_frame(code) for code in codes], ignore_index=True)
        if codes
        else pd.DataFrame(
            columns=[
                "日期",
                "available_date",
                "證券代號",
                "證券名稱",
                "收盤價",
                "成交股數",
            ]
        )
    )
    config = SimpleNamespace(
        db_file=tmp_path / "missing-fundamentals.db",
        use_sqlite=False,
        pit_market_scope="twse_listed",
    )
    market_provider = provider or _FrameProvider(frame)
    service = RecommendationService(
        config,
        industry_mapper=MagicMock(),
        market_data_provider=market_provider,
        regime_detector=MagicMock(),
        calibration_consumer=None,
        input_preparer=build_recommendation_test_preparer(
            config, market_data_provider=market_provider
        ),
    )
    service.reason_engine = MagicMock()
    service.reason_engine.generate_reasons.return_value = []
    service.reason_engine.format_reason_text.return_value = ""

    def generate(stock_frame: pd.DataFrame, _config: dict[str, Any]) -> pd.DataFrame:
        code = str(stock_frame.iloc[-1]["證券代號"])
        score = scores[code]
        return pd.DataFrame(
            {
                "FinalScore": [score],
                "TotalScore": [score],
                "收盤價": [Decimal("100.00")],
            }
        )

    service.strategy_configurator.generate_recommendations = generate
    return service


def _config(as_of: str, run_id: str = "r019-execute") -> dict[str, Any]:
    return {
        "profile_id": "r019-execute-profile",
        "profile_version": "1",
        "recommendation_ranking": {"threshold_mode": "fixed"},
        "as_of_date": as_of,
        "run_id": run_id,
    }


def _track_body_results(monkeypatch: pytest.MonkeyPatch):
    observed: dict[str, tuple[RecommendationService, RecommendationBodyResult]] = {}
    lock = Lock()
    original = RecommendationService._run_recommendation_body_result

    def tracked(invocation: RecommendationService, **kwargs: Any):
        body_result = original(invocation, **kwargs)
        result_id = str(kwargs.get("result_id") or "")
        with lock:
            observed[result_id] = (invocation, body_result)
        return body_result

    monkeypatch.setattr(
        RecommendationService, "_run_recommendation_body_result", tracked
    )
    return observed


def test_completed_execution_hands_off_same_body_decision_not_legacy_matrix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service(
        tmp_path,
        ("GOOD", "BROKEN"),
        {"GOOD": Decimal("88.500"), "BROKEN": Decimal("1.000")},
    )
    observed = _track_body_results(monkeypatch)
    original = RecommendationService._run_recommendation_body_result

    def mutate_legacy_after_body(invocation: RecommendationService, **kwargs: Any):
        body_result = original(invocation, **kwargs)
        invocation.last_screening_matrix[0]["reason_codes"].append(
            "matrix-only-negative-control"
        )
        observed[str(kwargs.get("result_id") or "")] = (
            invocation,
            body_result,
        )
        return body_result

    monkeypatch.setattr(
        RecommendationService,
        "_run_recommendation_body_result",
        mutate_legacy_after_body,
    )
    capture: dict[str, Any] = {}
    execution = execute_recommendation(
        service,
        _config("2026-05-20"),
        top_n=2,
        result_id="r019-canonical-handoff",
        capture_sink=capture,
    )

    invocation, body_result = observed["r019-canonical-handoff"]
    assert invocation is not service
    assert type(body_result) is RecommendationBodyResult
    assert type(body_result.decision) is DecisionBatch
    assert execution.status is ExecutionStatus.COMPLETED
    assert "matrix-only-negative-control" not in tuple(
        reason
        for assessment in body_result.decision.assessments
        for reason in assessment.reasons
    )
    assert "matrix-only-negative-control" in capture["compatibility_snapshot"].materialize()[
        "last_screening_matrix"
    ][0]["reason_codes"]
    matrix_event = next(
        event
        for event in execution.events
        if event.event_type == "legacy_negative_evidence_capture"
    )
    assert "matrix-only-negative-control" in matrix_event.details[
        "screening_matrix"
    ][0]["reason_codes"]
    # This is the negative control: the old matrix-derived assessment changes,
    # while the canonical body result remains the sole execution decision source.
    assert execution.decision == body_result.decision
    assert execution.decision is body_result.decision
    assert "matrix-only-negative-control" not in tuple(
        reason
        for assessment in execution.decision.assessments
        for reason in assessment.reasons
    )


def test_empty_success_hands_off_empty_batch_and_codec_roundtrips(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service(tmp_path, (), {})
    observed = _track_body_results(monkeypatch)
    execution = execute_recommendation(
        service,
        _config("2026-05-20"),
        result_id="r019-empty-handoff",
    )

    _invocation, body_result = observed["r019-empty-handoff"]
    assert type(body_result) is RecommendationBodyResult
    assert execution.status is ExecutionStatus.COMPLETED
    assert body_result.decision.items == ()
    assert body_result.decision.assessments == ()
    assert body_result.dispositions == ()
    assert body_result.legacy_recommendations == ()

    encoded = encode_execution(execution)
    decoded = decode_execution(encoded)
    assert decoded == execution
    assert encode_execution(decoded) == encoded
    assert execution.decision == body_result.decision
    assert execution.decision is body_result.decision
    assert execution.decision.items == ()
    assert execution.decision.assessments == ()


def test_body_exception_and_pre_or_post_body_cancellation_never_publish_decision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service(tmp_path, ("GOOD",), {"GOOD": Decimal("88.500")})
    body_calls = 0

    def fail_body(_invocation: RecommendationService, **_kwargs: Any):
        nonlocal body_calls
        body_calls += 1
        raise RuntimeError("synthetic body failure")

    monkeypatch.setattr(
        RecommendationService, "_run_recommendation_body_result", fail_body
    )
    failed = execute_recommendation(
        service,
        _config("2026-05-20"),
        result_id="r019-body-failed",
    )
    assert failed.status is ExecutionStatus.FAILED
    assert failed.decision is None
    assert "synthetic body failure" in str(failed.failure_reason)
    assert body_calls == 1

    monkeypatch.undo()
    service = _service(tmp_path / "cancel", ("GOOD",), {"GOOD": Decimal("88.500")})
    observed = _track_body_results(monkeypatch)
    before_start = execute_recommendation(
        service,
        _config("2026-05-20"),
        result_id="r019-pre-cancel",
        cancel=lambda: True,
    )
    assert before_start.status is ExecutionStatus.CANCELLED
    assert before_start.decision is None
    assert "r019-pre-cancel" not in observed

    checks = 0

    def cancel_after_body() -> bool:
        nonlocal checks
        checks += 1
        return checks > 1

    after_body = execute_recommendation(
        service,
        _config("2026-05-20"),
        result_id="r019-post-cancel",
        cancel=cancel_after_body,
    )
    assert after_body.status is ExecutionStatus.CANCELLED
    assert after_body.decision is None
    assert observed["r019-post-cancel"][1] is not None


def test_interleaved_same_code_runs_keep_body_identity_date_score_and_fingerprint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frames = {
        "r019-A": _market_frame("SAME", start=date(2026, 5, 1)),
        "r019-B": _market_frame("SAME", start=date(2026, 6, 1)),
    }
    provider = _InterleavedFrameProvider(frames)
    service = _service(
        tmp_path,
        ("SAME",),
        {"SAME": Decimal("80.00")},
        provider=provider,
    )

    def generate(stock_frame: pd.DataFrame, _config: dict[str, Any]) -> pd.DataFrame:
        final_day = stock_frame.iloc[-1]["日期"]
        score = Decimal("80.00") if final_day.month == 5 else Decimal("91.00")
        return pd.DataFrame(
            {
                "FinalScore": [score],
                "TotalScore": [score],
                "收盤價": [Decimal("100.00")],
            }
        )

    service.strategy_configurator.generate_recommendations = generate
    observed = _track_body_results(monkeypatch)

    def invoke(run_id: str, day: str):
        provider.invocation.run_id = run_id
        capture: dict[str, Any] = {}
        execution = execute_recommendation(
            service,
            _config(day, run_id),
            top_n=1,
            result_id=run_id,
            capture_sink=capture,
        )
        return execution, capture

    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="r019-handoff") as pool:
        future_a = pool.submit(invoke, "r019-A", "2026-05-20")
        future_b = pool.submit(invoke, "r019-B", "2026-06-20")
        execution_a, capture_a = future_a.result(timeout=10)
        execution_b, capture_b = future_b.result(timeout=10)

    invocation_a, body_a = observed["r019-A"]
    invocation_b, body_b = observed["r019-B"]
    assert invocation_a is not invocation_b
    assert type(body_a) is RecommendationBodyResult
    assert type(body_b) is RecommendationBodyResult
    assert execution_a.result_id == body_a.result_id == "r019-A"
    assert execution_b.result_id == body_b.result_id == "r019-B"
    assert body_a.invocation_id != body_b.invocation_id
    assert body_a.context.as_of_date == "2026-05-20"
    assert body_b.context.as_of_date == "2026-06-20"
    assert body_a.context.data_fingerprint != body_b.context.data_fingerprint
    assert (
        body_a.context.market_data_fingerprint
        != body_b.context.market_data_fingerprint
    )
    assert execution_a.context.as_of_date == date(2026, 5, 20)
    assert execution_b.context.as_of_date == date(2026, 6, 20)
    assert [item.stock_code for item in body_a.decision.items] == ["SAME"]
    assert [item.stock_code for item in body_b.decision.items] == ["SAME"]
    assert body_a.decision.items[0].rule_score == Decimal("80.00")
    assert body_b.decision.items[0].rule_score == Decimal("91.00")
    assert capture_a["compatibility_snapshot"].materialize()["last_run_context"]["as_of_date"] == "2026-05-20"
    assert capture_b["compatibility_snapshot"].materialize()["last_run_context"]["as_of_date"] == "2026-06-20"
    assert execution_a.decision == body_a.decision
    assert execution_b.decision == body_b.decision
    assert execution_a.decision is body_a.decision
    assert execution_b.decision is body_b.decision


def test_body_sidecar_and_captured_legacy_list_preserve_order_and_numeric_types(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service(
        tmp_path,
        ("TIE_B", "HIGH", "TIE_A"),
        {
            "TIE_B": Decimal("70.0100"),
            "HIGH": 91.5,
            "TIE_A": Decimal("70.0100"),
        },
    )
    observed = _track_body_results(monkeypatch)
    capture: dict[str, Any] = {}
    execution = execute_recommendation(
        service,
        _config("2026-05-20"),
        top_n=3,
        result_id="r019-sidecar-parity",
        capture_sink=capture,
    )

    _invocation, body_result = observed["r019-sidecar-parity"]
    assert type(body_result) is RecommendationBodyResult
    expected_order = ["HIGH", "TIE_B", "TIE_A"]
    assert [item.stock_code for item in execution.decision.items] == expected_order
    assert [
        item.field_value("stock_code") for item in body_result.legacy_recommendations
    ] == expected_order
    assert [item.stock_code for item in capture["legacy_recommendations"]] == expected_order
    assert type(body_result.legacy_recommendations[0].field_value("total_score")) is np.float64
    assert body_result.legacy_recommendations[0].field_value("total_score") == 91.5
    for sidecar in body_result.legacy_recommendations[1:]:
        assert type(sidecar.field_value("total_score")) is Decimal
        assert str(sidecar.field_value("total_score")) == "70.0100"
    assert type(capture["legacy_recommendations"][0].total_score) is np.float64
    assert [type(item.total_score) for item in capture["legacy_recommendations"][1:]] == [
        Decimal,
        Decimal,
    ]


def test_completed_context_quality_and_ml_fields_ignore_conflicting_legacy_capture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service(
        tmp_path,
        ("GOOD", "BROKEN"),
        {"GOOD": Decimal("88.500"), "BROKEN": Decimal("1.000")},
    )

    def generate(stock_frame: pd.DataFrame, _config: dict[str, Any]) -> pd.DataFrame:
        code = str(stock_frame.iloc[-1]["證券代號"])
        if code == "BROKEN":
            raise RuntimeError("synthetic candidate failure")
        return pd.DataFrame(
            {
                "FinalScore": [Decimal("88.500")],
                "TotalScore": [Decimal("88.500")],
                "收盤價": [Decimal("100.00")],
            }
        )

    service.strategy_configurator.generate_recommendations = generate
    observed = _track_body_results(monkeypatch)

    original_request_builder = execute_module._build_request

    def poison_request_legacy_context(**kwargs: Any):
        legacy_context = kwargs["legacy_context"]
        legacy_context.update(
            {
                "strategy_config_id": "legacy-poison-strategy",
                "strategy_config_schema": "legacy-poison-schema",
                "universe_policy_id": "legacy-poison-universe",
            }
        )
        return original_request_builder(**kwargs)

    monkeypatch.setattr(
        execute_module, "_build_request", poison_request_legacy_context
    )

    original_execution_builder = execute_module._build_execution

    def poison_execution_legacy_capture(**kwargs: Any):
        capture = kwargs["capture"]
        snapshot = capture["compatibility_snapshot"]
        frozen_before = snapshot.materialize()
        legacy_state = snapshot.materialize()
        legacy_context = legacy_state["last_run_context"]
        legacy_context.update(
            {
                "as_of_date": "2099-12-31",
                "decision_at": "2099-12-31T23:59:00+00:00",
                "warnings": ["legacy-only-warning"],
                "data_fingerprint": "legacy-only-data-fingerprint",
                "market_data_fingerprint": "legacy-only-market-fingerprint",
                "source_id": "legacy-only-source",
                "temporal_mode": "legacy-only-temporal-mode",
                "eligible_universe_size": 999,
                "strategy_config_id": "legacy-poison-strategy",
                "strategy_config_schema": "legacy-poison-schema",
                "universe_policy_id": "legacy-poison-universe",
                "universe_policy_hash": "legacy-poison-universe-hash",
                "calibration_projection_status": "unavailable",
                "calibration_projection_receipt_status": "unavailable",
                "calibration_projection_receipt_error_detail": "legacy-only-ml-error",
            }
        )
        legacy_state["last_screening_matrix"] = [
            {
                "stock_code": "LEGACY_ONLY",
                "status": "degraded",
                "reason_codes": ["legacy-only-matrix-row"],
                "quality": "degraded",
            }
        ]
        legacy_state["last_exclusion_quality"] = "degraded"
        legacy_state["last_exclusion_warnings_json"] = ["legacy-only-quality-warning"]
        assert snapshot.materialize() == frozen_before
        # Exercise the configured/attempted branch without a real consumer or source.
        capture["calibration_consumer_configured"] = True
        capture["calibration_attempted"] = True
        return original_execution_builder(**kwargs)

    monkeypatch.setattr(
        execute_module, "_build_execution", poison_execution_legacy_capture
    )
    execution = execute_recommendation(
        service,
        _config("2026-05-20"),
        top_n=2,
        result_id="r019-typed-context-precedence",
    )

    invocation, body_result = observed["r019-typed-context-precedence"]
    assert type(body_result) is RecommendationBodyResult
    typed = body_result.context
    assert execution.status is ExecutionStatus.COMPLETED
    assert execution.decision is body_result.decision
    assert typed.strategy_identity is not None
    assert typed.universe_identity is not None
    assert execution.request.as_of_date == date(2026, 5, 20)
    assert execution.request.config_ref is not None
    assert execution.request.config_ref.reference_id == (
        typed.strategy_identity.strategy_config_id
    )
    assert execution.request.config_ref.reference_id != "legacy-poison-strategy"
    assert execution.request.universe_policy_ref is not None
    assert execution.request.universe_policy_ref.reference_id == (
        typed.universe_identity.policy.universe_policy_id
    )
    assert execution.context.as_of_date == date.fromisoformat(typed.as_of_date)
    assert execution.context.decision_at == datetime.fromisoformat(typed.decision_at)
    assert execution.context.strategy_identity is typed.strategy_identity
    assert execution.context.universe_identity is typed.universe_identity
    assert execution.context.universe_policy_ref is not None
    assert execution.context.universe_policy_ref.reference_id == (
        typed.universe_identity.policy.universe_policy_id
    )
    assert typed.universe_identity.snapshot is not None
    assert execution.context.universe_snapshot_ref is not None
    assert execution.context.universe_snapshot_ref.reference_id == (
        typed.universe_identity.snapshot.universe_snapshot_id
    )
    expected_warnings = typed.warnings
    if "legacy_source_identity_unbound" not in expected_warnings:
        expected_warnings = (*expected_warnings, "legacy_source_identity_unbound")
    assert execution.context.warnings == expected_warnings
    assert "legacy-only-warning" not in execution.context.warnings

    degraded = any(
        disposition.quality in {"missing", "degraded"}
        for disposition in body_result.dispositions
    )
    assert degraded
    assert execution.quality.status is QualityStatus.DEGRADED
    assert execution.quality == execution.context.input_quality
    assert execution.quality.metrics["screening_row_count"] == len(
        body_result.dispositions
    )
    assert execution.quality.metrics["screening_row_count"] != 1
    assert execution.quality.metrics["recommendation_count"] == len(
        body_result.decision.items
    )
    assert "legacy-only-quality-warning" not in execution.quality.warnings
    assert execution.ml_availability.status is MLAvailabilityStatus.UNKNOWN
    assert execution.ml_availability.reason is None

    legacy_context_event = next(
        event
        for event in execution.events
        if event.event_type == "legacy_invocation_context"
    )
    # The compatibility event is projected from the finally-frozen snapshot.
    # Mutating a separately materialized copy must not rewrite the snapshot,
    # event, or typed execution.
    assert legacy_context_event.details["warnings"] == tuple(
        invocation.last_run_context["warnings"]
    )
    assert legacy_context_event.details["data_fingerprint"] == (
        invocation.last_run_context["data_fingerprint"]
    )
    assert "legacy-only-warning" not in legacy_context_event.details["warnings"]
    assert legacy_context_event.details["data_fingerprint"] != (
        "legacy-only-data-fingerprint"
    )
    legacy_matrix_event = next(
        event
        for event in execution.events
        if event.event_type == "legacy_negative_evidence_capture"
    )
    assert legacy_matrix_event.details["screening_matrix"][0]["stock_code"] == (
        invocation.last_screening_matrix[0]["stock_code"]
    )
    assert all(
        row["stock_code"] != "LEGACY_ONLY"
        for row in legacy_matrix_event.details["screening_matrix"]
    )


def test_empty_early_return_request_does_not_fallback_to_legacy_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service(tmp_path, (), {})
    observed = _track_body_results(monkeypatch)
    original_request_builder = execute_module._build_request
    poisoned: dict[str, object] = {}

    def poison_missing_typed_identity(**kwargs: Any):
        body_context = kwargs["body_context"]
        assert body_context is not None
        assert body_context.universe_identity is None
        legacy_context = kwargs["legacy_context"]
        legacy_context.update(
            {
                "strategy_config_id": "legacy-only-strategy-id",
                "strategy_config_schema": "legacy-only-strategy-schema",
                "universe_policy_id": "legacy-only-universe-policy",
            }
        )
        poisoned["strategy_config_id"] = legacy_context["strategy_config_id"]
        poisoned["universe_policy_id"] = legacy_context["universe_policy_id"]
        return original_request_builder(**kwargs)

    monkeypatch.setattr(
        execute_module, "_build_request", poison_missing_typed_identity
    )
    execution = execute_recommendation(
        service,
        _config("2026-05-20"),
        result_id="r019-empty-typed-identity-none",
    )

    _invocation, body_result = observed["r019-empty-typed-identity-none"]
    assert type(body_result) is RecommendationBodyResult
    assert body_result.decision.items == ()
    assert body_result.context.universe_identity is None
    assert poisoned == {
        "strategy_config_id": "legacy-only-strategy-id",
        "universe_policy_id": "legacy-only-universe-policy",
    }
    assert execution.status is ExecutionStatus.COMPLETED
    assert execution.decision is body_result.decision
    assert execution.request.as_of_date == date(2026, 5, 20)
    assert execution.request.config_ref is not None
    assert execution.request.config_ref.reference_id == (
        body_result.context.strategy_identity.strategy_config_id
    )
    assert execution.request.config_ref.reference_id != poisoned["strategy_config_id"]
    assert execution.request.universe_policy_ref is None
