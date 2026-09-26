"""R011 execute、invocation capture 與 legacy façade parity。"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from threading import Barrier, local
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

from app_module.recommendation import execute as execute_module
from app_module.recommendation.execute import (
    _safe_contract_value,
    execute_recommendation,
)
from app_module.recommendation.contracts import ExecutionStatus
from app_module.recommendation_service import RecommendationService
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
        thread_name = self.invocation.run_id
        self.barrier.wait(timeout=5)
        return self.frames[thread_name].copy(deep=True)


def _market_frame(code: str, *, start: date = date(2026, 5, 1)) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for offset in range(20):
        current = start + timedelta(days=offset)
        rows.append(
            {
                "日期": current,
                "available_date": current,
                "證券代號": code,
                "證券名稱": f"{code}_NAME",
                "收盤價": Decimal("100.00"),
                "成交股數": 1_000,
            }
        )
    return pd.DataFrame(rows)


def _service(
    tmp_path: Path,
    codes: tuple[str, ...],
    scores: dict[str, object],
    *,
    errors: dict[str, Exception] | None = None,
    provider: object | None = None,
) -> RecommendationService:
    frame = (
        pd.concat([_market_frame(code) for code in codes], ignore_index=True)
        if codes
        else pd.DataFrame(
            columns=["日期", "available_date", "證券代號", "證券名稱", "收盤價", "成交股數"]
        )
    )
    config = SimpleNamespace(
        db_file=tmp_path / "missing-fundamentals.db",
        use_sqlite=False,
        pit_market_scope="twse_listed",
    )
    market_data_provider = provider or _FrameProvider(frame)
    service = RecommendationService(
        config,
        industry_mapper=MagicMock(),
        market_data_provider=market_data_provider,
        regime_detector=MagicMock(),
        calibration_consumer=None,
        input_preparer=build_recommendation_test_preparer(
            config, market_data_provider=market_data_provider
        ),
    )
    service.reason_engine = MagicMock()
    service.reason_engine.generate_reasons.return_value = []
    service.reason_engine.format_reason_text.return_value = ""
    error_by_code = errors or {}

    def generate(stock_frame: pd.DataFrame, _config: dict[str, Any]) -> pd.DataFrame:
        code = str(stock_frame.iloc[-1]["證券代號"])
        if code in error_by_code:
            raise error_by_code[code]
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


def _config(as_of: str = "2026-05-20") -> dict[str, Any]:
    return {
        "profile_id": "r011-profile",
        "profile_version": "1",
        "recommendation_ranking": {"threshold_mode": "fixed"},
        "as_of_date": as_of,
    }


class _UnsupportedEvidence:
    pass


def test_public_facade_delegates_once_and_preserves_exact_legacy_numeric_boundary(
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
    body_calls = 0
    invocation_services: list[RecommendationService] = []
    original_body = RecommendationService._run_recommendation_body_result

    def counted_body(invocation_service: RecommendationService, **kwargs: Any):
        nonlocal body_calls
        body_calls += 1
        invocation_services.append(invocation_service)
        return original_body(invocation_service, **kwargs)

    monkeypatch.setattr(
        RecommendationService, "_run_recommendation_body_result", counted_body
    )
    execute_calls = 0
    original_execute = execute_module.execute_recommendation
    invocation_capture: dict[str, Any] = {}

    def counted_execute(*args: Any, **kwargs: Any):
        nonlocal execute_calls
        execute_calls += 1
        execution = original_execute(*args, **kwargs)
        invocation_capture.update(kwargs["capture_sink"])
        return execution

    monkeypatch.setattr(execute_module, "execute_recommendation", counted_execute)
    recommendations = service.run_recommendation(
        _config(), top_n=3, result_id="r011-list-parity"
    )

    assert execute_calls == 1
    assert body_calls == 1
    assert invocation_services and invocation_services[0] is not service
    assert invocation_capture["compatibility_snapshot"].materialize()["last_run_context"]["result_id"] == (
        "r011-list-parity"
    )
    assert [item.stock_code for item in recommendations] == ["HIGH", "TIE_B", "TIE_A"]
    assert type(recommendations[0].total_score) is np.float64
    assert recommendations[0].total_score == 91.5
    assert type(recommendations[1].total_score) is Decimal
    assert str(recommendations[1].total_score) == "70.0100"
    assert recommendations[0].close_price == Decimal("100.00")
    assert service.last_run_context["result_id"] == "r011-list-parity"


def test_execute_never_calls_public_facade_and_freezes_nested_capture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service(
        tmp_path,
        ("GOOD", "BROKEN"),
        {"GOOD": Decimal("88.500"), "BROKEN": Decimal("1.000")},
        errors={"BROKEN": RuntimeError("fixture failure")},
    )

    def forbidden_facade(*_args: Any, **_kwargs: Any):
        raise AssertionError("execute must not recurse through the legacy façade")

    monkeypatch.setattr(service, "run_recommendation", forbidden_facade)
    capture: dict[str, Any] = {}
    execution = execute_recommendation(
        service,
        _config(),
        top_n=1,
        result_id="r011-freeze",
        capture_sink=capture,
    )

    assert execution.status is ExecutionStatus.COMPLETED
    assert [item.stock_code for item in execution.items] == ["GOOD"]
    assert [row.stock_code for row in execution.assessments] == ["GOOD", "BROKEN"]
    broken = execution.assessments[1]
    assert broken.negative_evidence
    old_reason = broken.negative_evidence[0].reason
    old_matrix_reason = execution.events[1].details["screening_matrix"][1][
        "reason_codes"
    ][0]

    captured_matrix = capture["compatibility_snapshot"].materialize()["last_screening_matrix"]
    captured_matrix[1]["reason_codes"].append("sidecar-only-mutation")
    captured_matrix[1]["warnings"].append("sidecar-only-warning")
    assert broken.negative_evidence[0].reason == old_reason
    assert execution.events[1].details["screening_matrix"][1]["reason_codes"][0] == old_matrix_reason
    with pytest.raises(TypeError):
        execution.events[1].details["screening_matrix"][1]["status"] = "changed"


def test_contract_evidence_fails_closed_for_unknowns_keys_and_nonfinite_numbers() -> None:
    unsupported_values = (
        pd.DataFrame({"private": [42]}),
        lambda: "callback",
        _UnsupportedEvidence(),
    )
    for value in unsupported_values:
        with pytest.raises(TypeError, match="不在 execution evidence allowlist"):
            _safe_contract_value({"evidence": value})

    with pytest.raises(TypeError, match="mapping key 必須是 str"):
        _safe_contract_value({1: "integer-key", "1": "string-key"})

    for nonfinite in (Decimal("NaN"), float("inf"), np.float64("nan")):
        with pytest.raises(ValueError, match="必須是有限值"):
            _safe_contract_value(nonfinite)
    assert _safe_contract_value("nan") == "nan"

    assert _safe_contract_value(
        {"integer": np.int64(7), "float": np.float64(1.25), "text": np.str_("ok")}
    ) == {"integer": 7, "float": Decimal("1.25"), "text": "ok"}


def test_legacy_list_abi_and_execution_abi_match_with_isolated_side_effects(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app_module.recommendation_service as service_module

    class _FrozenRecommendationDatetime(datetime):
        @classmethod
        def now(cls, tz=None):  # type: ignore[no-untyped-def]
            current = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
            return current.astimezone(tz) if tz is not None else current.replace(tzinfo=None)

    monkeypatch.setattr(service_module, "datetime", _FrozenRecommendationDatetime)
    legacy_list_root = tmp_path / "legacy-list-abi"
    execution_root = tmp_path / "execution-abi"
    legacy_list_root.mkdir()
    execution_root.mkdir()
    codes = ("TIE_B", "HIGH", "TIE_A", "BROKEN")
    scores = {
        "TIE_B": Decimal("70.0100"),
        "HIGH": 91.5,
        "TIE_A": Decimal("70.0100"),
        "BROKEN": Decimal("10.000"),
    }
    errors = {"BROKEN": RuntimeError("paired-compatibility rejection")}

    # 相容 list 入口與 typed execution 入口使用隔離的 service 與輸出路徑。
    # 兩者共用同一計算流程；本測試只比較公開相容 ABI 的結果與狀態。
    legacy_service = _service(legacy_list_root, codes, scores, errors=errors)
    execution_service = _service(execution_root, codes, scores, errors=errors)
    fixed_config = _config()
    expected = legacy_service._run_recommendation_body(
        fixed_config,
        top_n=3,
        result_id="r029-rec06-abi-parity",
        input_session=legacy_service.recommendation_input_preparer.begin(
            legacy_service.config
        ),
    )
    actual = execution_service.run_recommendation(
        fixed_config, top_n=3, result_id="r029-rec06-abi-parity"
    )

    assert legacy_service.config.db_file != execution_service.config.db_file
    assert [item.stock_code for item in expected] == [
        item.stock_code for item in actual
    ] == ["HIGH", "TIE_B", "TIE_A"]
    assert [vars(item) for item in actual] == [vars(item) for item in expected]
    for expected_item, actual_item in zip(expected, actual, strict=True):
        assert type(actual_item.total_score) is type(expected_item.total_score)
        if type(expected_item.total_score) is Decimal:
            assert str(actual_item.total_score) == str(expected_item.total_score)

    state_fields = (
        "last_calibration_projections",
        "last_screening_matrix",
        "last_excluded_candidates_json",
        "last_why_not_payload_json",
        "last_liquidity_gate_payload_json",
        "last_exclusion_quality",
        "last_exclusion_warnings_json",
        "last_run_context",
    )
    legacy_state = {name: getattr(legacy_service, name) for name in state_fields}
    execution_state = {
        name: getattr(execution_service, name) for name in state_fields
    }
    assert execution_state == legacy_state
    assert execution_state["last_run_context"]["result_id"] == "r029-rec06-abi-parity"
    assert execution_state["last_screening_matrix"] == legacy_state[
        "last_screening_matrix"
    ]
    assert execution_state["last_why_not_payload_json"] == legacy_state[
        "last_why_not_payload_json"
    ]
    assert execution_state["last_excluded_candidates_json"] == legacy_state[
        "last_excluded_candidates_json"
    ]
    assert execution_state["last_liquidity_gate_payload_json"] == legacy_state[
        "last_liquidity_gate_payload_json"
    ]


def test_empty_completion_and_prestart_cancel_have_explicit_statuses(
    tmp_path: Path,
) -> None:
    empty_service = _service(tmp_path, (), {})
    completed = execute_recommendation(
        empty_service,
        _config(),
        result_id="r011-empty",
    )
    assert completed.status is ExecutionStatus.COMPLETED
    assert completed.result_id == "r011-empty"
    assert completed.decision is not None
    assert completed.decision.items == ()

    calls = 0
    original = empty_service._run_recommendation_body_result

    def counted(**kwargs: Any):
        nonlocal calls
        calls += 1
        return original(**kwargs)

    empty_service._run_recommendation_body_result = counted
    cancelled = execute_recommendation(
        empty_service,
        _config(),
        cancel=lambda: True,
    )
    assert cancelled.status is ExecutionStatus.CANCELLED
    assert cancelled.decision is None
    assert calls == 0


def test_public_validation_error_preserves_previous_last_state_and_body_error_resets(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path, ("GOOD",), {"GOOD": Decimal("88.500")})
    service.run_recommendation(_config(), result_id="r011-first")
    previous_context = service.last_run_context
    previous_matrix = service.last_screening_matrix

    with pytest.raises(ValueError, match="不得為負數"):
        service.run_recommendation(_config(), top_n=-1)
    assert service.last_run_context is previous_context
    assert service.last_screening_matrix is previous_matrix

    service.market_data_provider = lambda: (_ for _ in ()).throw(OSError("source down"))
    with pytest.raises(OSError, match="source down"):
        service.run_recommendation(_config(), result_id="r011-source-error")
    assert service.last_run_context == {}
    assert service.last_screening_matrix == []


def test_post_body_cancel_discards_decision_but_keeps_invocation_capture(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path, ("GOOD",), {"GOOD": Decimal("88.500")})
    checks = 0
    progress_events: list[tuple[str, int]] = []

    def cancel_after_body() -> bool:
        nonlocal checks
        checks += 1
        return checks > 1

    capture: dict[str, Any] = {}
    execution = execute_recommendation(
        service,
        _config(),
        result_id="r011-cancel-after-body",
        cancel=cancel_after_body,
        progress=lambda stage, percent: progress_events.append((stage, percent)),
        capture_sink=capture,
    )
    assert execution.status is ExecutionStatus.CANCELLED
    assert execution.decision is None
    assert len(capture["legacy_recommendations"]) == 1
    assert capture["compatibility_snapshot"].materialize()["last_run_context"]["result_id"] == (
        "r011-cancel-after-body"
    )
    assert [percent for _, percent in progress_events] == [10, 35, 90, 100]


def test_interleaved_a_b_keep_execution_and_published_legacy_state_per_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frames = {
        "r011-A": _market_frame("AAA", start=date(2026, 5, 1)),
        "r011-B": _market_frame("BBB", start=date(2026, 6, 1)),
    }
    provider = _InterleavedFrameProvider(frames)
    service = _service(
        tmp_path,
        ("AAA", "BBB"),
        {"AAA": Decimal("80.00"), "BBB": Decimal("90.00")},
        provider=provider,
    )
    observed: dict[str, tuple[Any, dict[str, Any]]] = {}
    original_execute = execute_module.execute_recommendation

    def capture_execute(service_arg: Any, config: Mapping[str, Any], **kwargs: Any):
        execution = original_execute(service_arg, config, **kwargs)
        captured = kwargs["capture_sink"]
        observed[str(config["run_id"])] = (
            execution,
            {
                "legacy_state": deepcopy(captured["compatibility_snapshot"].materialize()),
                "legacy_recommendations": deepcopy(
                    captured["legacy_recommendations"]
                ),
            },
        )
        return execution

    monkeypatch.setattr(execute_module, "execute_recommendation", capture_execute)

    def invoke(run_id: str, code: str, day: str):
        provider.invocation.run_id = run_id
        return service.run_recommendation(
            {
                **_config(day),
                "run_id": run_id,
                "recommendation_ranking": {"threshold_mode": "fixed"},
            },
            result_id=run_id,
        )

    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="r011") as pool:
        future_a = pool.submit(invoke, "r011-A", "AAA", "2026-05-20")
        future_b = pool.submit(invoke, "r011-B", "BBB", "2026-06-20")
        result_a = future_a.result(timeout=10)
        result_b = future_b.result(timeout=10)

    execution_a, capture_a = observed["r011-A"]
    execution_b, capture_b = observed["r011-B"]
    assert [item.stock_code for item in result_a] == ["AAA"]
    assert [item.stock_code for item in result_b] == ["BBB"]
    assert execution_a.result_id == "r011-A"
    assert execution_b.result_id == "r011-B"
    assert execution_a.context.as_of_date == date(2026, 5, 20)
    assert execution_b.context.as_of_date == date(2026, 6, 20)
    assert [item.stock_code for item in execution_a.items] == ["AAA"]
    assert [item.stock_code for item in execution_b.items] == ["BBB"]
    assert [row["stock_code"] for row in capture_a["legacy_state"]["last_screening_matrix"]] == ["AAA"]
    assert [row["stock_code"] for row in capture_b["legacy_state"]["last_screening_matrix"]] == ["BBB"]
    live_context_id = service.last_run_context["result_id"]
    live_code = service.last_screening_matrix[0]["stock_code"]
    assert (live_context_id, live_code) in {("r011-A", "AAA"), ("r011-B", "BBB")}
    assert not execution_a.ml_receipt_refs
    assert not execution_b.ml_receipt_refs


def test_verified_receipt_binding_survives_post_write_identity_race_without_a_b_cross_link(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app_module.recommendation_calibration_consumer import (
        RecommendationCalibrationConsumer,
    )
    from ml_module.feature_registry import CORE_LONG_HISTORY_FEATURE_REGISTRY
    from ml_module.recommendation_calibration_authority import (
        RecommendationCalibrationPromotionAuthority,
    )
    from ml_module.recommendation_inference_provenance import (
        read_inference_projection_receipt,
    )
    from test_daily_recommendation_learning_loop import _natural_receipt
    from test_recommendation_service_calibration_integration import (
        _core_feature_samples,
        _make_database,
        _verified_candidate,
    )
    import app_module.recommendation_service as service_module

    registry = CORE_LONG_HISTORY_FEATURE_REGISTRY
    candidate_day = "2026-06-01"
    decision_day = "2026-08-03"
    trained, candidate_root, candidate_metadata = _verified_candidate(
        tmp_path,
        candidate_day=candidate_day,
        training_as_of="2026-05-31",
        samples=_core_feature_samples(),
        feature_names=registry.canonical_ids,
        feature_schema=registry.canonical_schema,
        feature_registry_hash=registry.registry_hash,
        dataset_id="dataset-r011-receipt-race",
    )
    natural_evidence = _natural_receipt(
        tmp_path,
        root=candidate_root,
        candidate_day=candidate_day,
        evaluation_day=decision_day,
        feature_schema=registry.canonical_schema,
        feature_registry_hash=registry.registry_hash,
    )
    authority = RecommendationCalibrationPromotionAuthority(tmp_path / "authority")
    decision = authority.evaluate_and_apply(
        decision_date=decision_day,
        candidate_id=trained.candidate_id,
        candidate_root=candidate_root,
        candidate_metadata=candidate_metadata,
        natural_evidence=natural_evidence,
        data_status="ready",
        drift_status="clean",
    )
    assert decision.decision == "adopt"

    database = tmp_path / "source.db"
    _make_database(database, start=date(2026, 1, 1))
    consumer = RecommendationCalibrationConsumer(
        pointer_path=authority.pointer_path,
        feature_schema=registry.canonical_schema,
        feature_registry_hash=registry.registry_hash,
        data_root=tmp_path / "formal-data",
    )
    assert consumer.reload(decision_date=decision_day) == "active"
    config = SimpleNamespace(
        db_file=database,
        default_start_date="2026-01-01",
        output_root=tmp_path / "output",
        data_root=tmp_path / "formal-data",
        use_sqlite=False,
    )
    market_frame = pd.DataFrame(
        [
            {
                "日期": date(2026, 1, 1) + timedelta(days=offset),
                "證券代號": "AAA",
                "證券名稱": "測試股票",
                "收盤價": 100 + offset,
                "成交股數": 1_000 + offset,
            }
            for offset in range(215)
        ]
    )
    market_data_provider = lambda: market_frame.copy(deep=True)
    service = RecommendationService(
        config,
        industry_mapper=MagicMock(),
        market_data_provider=market_data_provider,
        regime_detector=MagicMock(),
        calibration_consumer=consumer,
        input_preparer=build_recommendation_test_preparer(
            config, market_data_provider=market_data_provider
        ),
    )
    service.strategy_configurator.generate_recommendations = lambda _df, _config: pd.DataFrame(
        {"TotalScore": [80], "FinalScore": [80], "收盤價": [Decimal("100")], "成交股數": [1_000]}
    )

    class _FrozenRecommendationDatetime(datetime):
        @classmethod
        def now(cls, tz=None):  # type: ignore[no-untyped-def]
            current = datetime(2026, 8, 3, 16, 50, tzinfo=timezone.utc)
            return current.astimezone(tz) if tz is not None else current.replace(tzinfo=None)

    monkeypatch.setattr(service_module, "datetime", _FrozenRecommendationDatetime)
    original_writer = service_module.persist_inference_projection_receipt
    write_complete = False

    def persist_then_change_identity(learning_root, receipt):
        nonlocal write_complete
        path = original_writer(learning_root, receipt)
        write_complete = True
        return path

    monkeypatch.setattr(
        service_module,
        "persist_inference_projection_receipt",
        persist_then_change_identity,
    )
    original_identity = consumer.active_identity
    race_enabled = True

    def identity_with_post_write_race(*, decision_date: str):
        identity = original_identity(decision_date=decision_date)
        if identity is not None and write_complete and race_enabled:
            identity = dict(identity)
            identity["pointer_version"] = f"{identity.get('pointer_version')}:raced"
        return identity

    consumer.active_identity = identity_with_post_write_race

    def invoke(run_id: str):
        capture: dict[str, Any] = {}
        execution = execute_recommendation(
            service,
            {
                "recommendation_ranking": {"threshold_mode": "fixed"},
                "as_of_date": None,
            },
            max_stocks=1,
            top_n=1,
            universe=["AAA"],
            result_id=run_id,
            select_latest_available_cutoff=True,
            capture_sink=capture,
        )
        return execution, capture

    execution_a, capture_a = invoke("r011-receipt-A")
    receipt_capture_a = capture_a["receipt"]
    assert execution_a.status is ExecutionStatus.COMPLETED
    assert receipt_capture_a["persisted"] is True
    assert receipt_capture_a["readback_verified"] is True
    assert receipt_capture_a.get("identity_verified") is not True
    assert "candidate/model race" in receipt_capture_a["error"]
    assert execution_a.ml_availability.status.value == "unavailable"
    assert len(execution_a.ml_receipt_refs) == 1
    binding_a = execution_a.ml_receipt_refs[0]
    assert binding_a.result_id == "r011-receipt-A"
    assert binding_a.model_candidate_id == trained.candidate_id
    assert binding_a.projected_stock_codes == ("AAA",)
    read_a = read_inference_projection_receipt(
        receipt_capture_a["path"],
        expected_receipt_hash=receipt_capture_a["receipt_hash"],
        expected_decision_date=decision_day,
        expected_candidate_id=trained.candidate_id,
        expected_result_id="r011-receipt-A",
        expected_stock_code="AAA",
    )
    assert read_a.receipt_hash == binding_a.receipt_hash

    write_complete = False
    race_enabled = False
    execution_b, capture_b = invoke("r011-receipt-B")
    receipt_capture_b = capture_b["receipt"]
    assert execution_b.ml_availability.status.value == "available"
    assert len(execution_b.ml_receipt_refs) == 1
    binding_b = execution_b.ml_receipt_refs[0]
    assert binding_b.result_id == "r011-receipt-B"
    assert binding_b.model_candidate_id == trained.candidate_id
    assert binding_b.projected_stock_codes == ("AAA",)
    assert binding_a.receipt_ref.reference_id != binding_b.receipt_ref.reference_id
    assert binding_a.receipt_hash != binding_b.receipt_hash
    event_a = next(
        event for event in execution_a.events
        if event.event_type == "ml_projection_receipt_capture"
    )
    assert event_a.details["path"] == receipt_capture_a["path"]
    assert event_a.details["receipt_hash"] == receipt_capture_a["receipt_hash"]
    assert event_a.details["result_id"] == "r011-receipt-A"
    assert event_a.details["receipt_body_hash_verified"] is True

    checks = 0

    def cancel_after_verified_receipt() -> bool:
        nonlocal checks
        checks += 1
        return checks > 1

    # Capture again through an explicit sink; cancellation keeps receipt evidence
    # but never publishes a DecisionBatch.
    capture_c = {}
    execution_c = execute_recommendation(
        service,
        {"recommendation_ranking": {"threshold_mode": "fixed"}},
        max_stocks=1,
        top_n=1,
        universe=["AAA"],
        result_id="r011-receipt-C",
        select_latest_available_cutoff=True,
        cancel=cancel_after_verified_receipt,
        capture_sink=capture_c,
    )
    assert execution_c.status is ExecutionStatus.CANCELLED
    assert execution_c.decision is None
    assert execution_c.ml_receipt_refs[0].result_id == "r011-receipt-C"
    assert capture_c["receipt"]["readback_verified"] is True
