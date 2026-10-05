"""R011 execute、invocation capture 與 legacy façade parity。"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
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
    _current_fundamental_lineage_event,
    _safe_contract_value,
    execute_recommendation,
)
from app_module.recommendation.codec import decode_execution, encode_execution
from app_module.recommendation.contracts import ExecutionStatus
from app_module.recommendation_service import RecommendationService
from app_module.recommendation.input_preparation import RecommendationInputSession
from data_module.recommendation_current_fundamental_provider import (
    CurrentMonthlyRevenueReadResult,
    CurrentObservedMonthlyRevenueInput,
    CurrentObservedPEInput,
)
from recommendation_test_support import build_recommendation_test_preparer
from decision_module.recommendation.evaluate import RecommendationEvaluator


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
    output_root: Path | None = None,
) -> RecommendationService:
    frame = (
        pd.concat([_market_frame(code) for code in codes], ignore_index=True)
        if codes
        else pd.DataFrame(
            columns=["日期", "available_date", "證券代號", "證券名稱", "收盤價", "成交股數"]
        )
    )
    config_values: dict[str, object] = dict(
        db_file=tmp_path / "missing-fundamentals.db",
        use_sqlite=False,
        pit_market_scope="twse_listed",
    )
    if output_root is not None:
        config_values["output_root"] = output_root
    config = SimpleNamespace(**config_values)
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


def test_explicit_config_cutoff_does_not_enter_natural_current_fundamental_scope(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path, ("AAA",), {"AAA": Decimal("88.5")})
    capture: dict[str, Any] = {}

    execution = execute_recommendation(
        service,
        _config("2026-05-20"),
        top_n=1,
        result_id="r011-explicit-config-pit",
        capture_sink=capture,
    )

    assert execution.status is ExecutionStatus.COMPLETED
    context = capture["compatibility_snapshot"].materialize()["last_run_context"]
    assert context["fundamental_input_scope"] == "formal_pit"
    assert context["current_observation_cutoff_at"] is None
    assert context["fundamental_input_requests"] == []
    assert not any(
        event.event_type == "current_fundamental_lineage"
        for event in execution.events
    )


def test_verified_current_delisting_excludes_before_history_preflight(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.test_recommendation_current_market_status_preflight import (
        write_4130_pointer_fixture,
    )

    source_root = tmp_path / "official-status"
    now = datetime.now(timezone.utc)
    write_4130_pointer_fixture(
        source_root,
        captured_at=now - timedelta(seconds=3),
        snapshot_observed_at=now - timedelta(seconds=1),
    )
    service = _service(
        tmp_path,
        ("4130",),
        {"4130": Decimal("88.5")},
        output_root=source_root,
    )
    config = _config()
    config["as_of_date"] = None
    history_preflight_calls: list[str] = []
    original_preflight = RecommendationEvaluator.preflight_history

    def observe_preflight(facts: Any) -> Any:
        history_preflight_calls.append(facts.stock_code)
        return original_preflight(facts)

    monkeypatch.setattr(
        RecommendationEvaluator,
        "preflight_history",
        staticmethod(observe_preflight),
    )
    capture: dict[str, Any] = {}

    execution = execute_recommendation(
        service,
        config,
        top_n=1,
        result_id="current-status-4130-before-history",
        capture_sink=capture,
    )

    assert execution.status is ExecutionStatus.COMPLETED
    assert history_preflight_calls == []
    assert execution.decision.items == ()
    assert len(execution.decision.assessments) == 1
    assessment = execution.decision.assessments[0]
    assert assessment.stock_code == "4130"
    assert assessment.eligible is False
    gate = assessment.filter_outcomes["current_market_status_gate"]
    assert gate.passed is False
    assert gate.reason == "official_delisted"
    assert gate.evidence["scope"] == "current_only"
    assert gate.evidence["pit_eligible"] is False
    assert gate.evidence["symbol"] == "4130"
    legacy = capture["compatibility_snapshot"].materialize()
    matrix_row = legacy["last_screening_matrix"][0]
    assert matrix_row["status"] == "fail"
    assert matrix_row["quality"] == "observed"
    assert matrix_row["stage"] == "current_market_status_gate"
    assert matrix_row["reason_codes"] == ["official_delisted"]
    assert matrix_row["warnings"] == []


def test_unknown_current_market_status_is_diagnostic_only_and_historical_skips_reader(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    natural_service = _service(
        tmp_path / "natural",
        ("AAA",),
        {"AAA": Decimal("88.5")},
    )
    natural_config = _config()
    natural_config["as_of_date"] = None
    natural_capture: dict[str, Any] = {}
    natural_execution = execute_recommendation(
        natural_service,
        natural_config,
        top_n=1,
        result_id="current-status-unavailable-natural",
        capture_sink=natural_capture,
    )
    assert natural_execution.status is ExecutionStatus.COMPLETED
    assert natural_execution.quality.status.value == "unknown"
    assert [item.stock_code for item in natural_execution.decision.items] == ["AAA"]
    natural_context = natural_capture["compatibility_snapshot"].materialize()[
        "last_run_context"
    ]
    diagnostics = natural_context["current_market_status_preflight_diagnostics"]
    assert len(diagnostics) == 1
    assert diagnostics[0].startswith(
        "current_market_status_preflight_unavailable:AAA:"
    )
    assert not any(
        "current_market_status_preflight_unavailable" in warning
        for warning in natural_execution.quality.warnings
    )
    diagnostic_event = next(
        event
        for event in natural_execution.events
        if event.event_type == "legacy_invocation_context"
    )
    assert tuple(
        diagnostic_event.details["current_market_status_preflight_diagnostics"]
    ) == tuple(diagnostics)
    reopened_natural = decode_execution(encode_execution(natural_execution))
    reopened_diagnostic_event = next(
        event
        for event in reopened_natural.events
        if event.event_type == "legacy_invocation_context"
    )
    assert reopened_diagnostic_event.details[
        "current_market_status_preflight_diagnostics"
    ] == diagnostic_event.details["current_market_status_preflight_diagnostics"]

    calls: list[str] = []

    def forbidden_historical_reader(
        _self: RecommendationInputSession,
        stock_code: str,
        *,
        cutoff_at: datetime,
        decision_date: date,
    ) -> Any:
        calls.append(stock_code)
        raise AssertionError("historical recommendation called current-only status")

    monkeypatch.setattr(
        RecommendationInputSession,
        "get_current_market_status",
        forbidden_historical_reader,
    )
    historical_service = _service(
        tmp_path / "historical",
        ("AAA",),
        {"AAA": Decimal("88.5")},
    )
    historical_capture: dict[str, Any] = {}
    historical_execution = execute_recommendation(
        historical_service,
        _config("2026-05-20"),
        top_n=1,
        result_id="current-status-not-called-historically",
        capture_sink=historical_capture,
    )
    assert historical_execution.status is ExecutionStatus.COMPLETED
    assert calls == []
    historical_context = historical_capture["compatibility_snapshot"].materialize()[
        "last_run_context"
    ]
    assert historical_context["current_market_status_preflight_diagnostics"] == []

    latest_service = _service(
        tmp_path / "select-latest",
        ("AAA",),
        {"AAA": Decimal("88.5")},
    )
    latest_config = _config()
    latest_config["as_of_date"] = None
    latest_execution = execute_recommendation(
        latest_service,
        latest_config,
        top_n=1,
        result_id="current-status-not-called-select-latest",
        select_latest_available_cutoff=True,
        capture_sink={},
    )
    assert latest_execution.status is ExecutionStatus.COMPLETED
    assert calls == []


def test_failed_natural_body_keeps_original_error_without_lineage_event(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service(tmp_path, ("AAA",), {"AAA": Decimal("88.5")})

    def fail_before_publishing_body(_self: RecommendationService) -> None:
        raise RuntimeError("body failed before typed result publication")

    monkeypatch.setattr(
        RecommendationService,
        "_record_current_industry_mapping_use",
        lambda _self, _usage: None,
    )
    monkeypatch.setattr(
        RecommendationService,
        "_finalize_current_industry_mapping_snapshot",
        fail_before_publishing_body,
    )
    config = _config()
    config["as_of_date"] = None
    capture: dict[str, Any] = {}

    execution = execute_recommendation(
        service,
        config,
        top_n=1,
        result_id="r011-natural-body-failure",
        capture_sink=capture,
    )

    assert execution.status is ExecutionStatus.FAILED
    assert execution.failure_reason == (
        "RuntimeError: body failed before typed result publication"
    )
    context = capture["compatibility_snapshot"].materialize()["last_run_context"]
    assert context["fundamental_input_scope"] == "natural_current_observation"
    assert any(
        event.event_type == "legacy_invocation_context"
        for event in execution.events
    )
    error_event = next(
        event
        for event in execution.events
        if event.event_type == "recommendation_execution_error"
    )
    assert error_event.details["exception_type"] == "RuntimeError"
    assert "body failed before typed result publication" in error_event.message
    assert not any(
        event.event_type == "current_fundamental_lineage"
        for event in execution.events
    )


def test_blocked_current_yoy_baseline_cannot_fall_back_to_formal_pit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service(tmp_path, ("2330",), {"2330": Decimal("88.5")})

    class _BlockedBaselineProvider:
        def load_monthly_revenues(
            self,
            *,
            stock_code: str,
            cutoff_at: datetime,
        ) -> CurrentMonthlyRevenueReadResult:
            observed_at = cutoff_at - timedelta(seconds=1)
            current = CurrentObservedMonthlyRevenueInput(
                stock_code=stock_code,
                period="2026-04",
                revenue=Decimal("150000"),
                observed_at=observed_at,
                source_available_at=None,
                available_at=observed_at,
                source="mops.monthly_revenue_static_snapshot",
                source_version=(
                    "mops-current-revenue-normalizer.v2:twse:2026-04:raw:"
                    "mops-static-twse-2026-04-sha256-" + "a" * 64
                    + ":derived:sha256:" + "b" * 64
                ),
                market="twse",
                raw_source_version="mops-static-twse-2026-04-sha256-" + "a" * 64,
                raw_source_sha256="a" * 64,
            )
            return CurrentMonthlyRevenueReadResult(
                status="ready",
                stock_code=stock_code,
                cutoff_at=cutoff_at,
                latest_period="2026-04",
                observations=(current,),
                diagnostics=(
                    "current_monthly_revenue_unverified_revision_blocks_period:2025-04",
                ),
                blocked_periods=("2025-04",),
            )

    service.recommendation_input_preparer.current_fundamental_provider = (
        _BlockedBaselineProvider()
    )

    def reject_formal_fallback(*_args: Any, **_kwargs: Any):
        raise AssertionError("a blocked current baseline must not use a formal PIT fallback")

    monkeypatch.setattr(
        RecommendationService,
        "_load_governed_monthly_revenues",
        reject_formal_fallback,
    )
    config = _config()
    config["as_of_date"] = None
    config["filters"] = {"monthly_revenue_yoy_min": "10"}
    capture: dict[str, Any] = {}

    execution = execute_recommendation(
        service,
        config,
        top_n=1,
        result_id="r011-blocked-yoy-baseline",
        capture_sink=capture,
    )

    assert execution.status is ExecutionStatus.COMPLETED
    context = capture["compatibility_snapshot"].materialize()["last_run_context"]
    assert context["fundamental_input_scope"] == "natural_current_observation"
    assert "current_monthly_revenue_exact_prior_year_baseline_blocked:2330:2025-04" in (
        context["fundamental_input_diagnostics"]
    )
    assert any(
        "fundamental_revenue_yoy_missing" in row.reasons
        for row in execution.assessments
    )
    assert [
        item["period"]
        for item in context["current_fundamental_observations"]
        if item.get("metric") == "monthly_revenue"
    ] == ["2026-04"]
    lineage_event = next(
        event
        for event in execution.events
        if event.event_type == "current_fundamental_lineage"
    )
    assert lineage_event.details["schema_version"] == (
        "recommendation-current-fundamental-lineage.v1"
    )
    assert lineage_event.details["result_id"] == execution.result_id
    assert lineage_event.details["scope"] == "natural_current_observation"
    assert lineage_event.details["current_observation_cutoff_at"]
    assert len(lineage_event.details["requests"]) == 1
    assert lineage_event.details["facts"][0]["period"] == "2026-04"
    assert any(
        "current_monthly_revenue_exact_prior_year_baseline_blocked" in item
        for item in lineage_event.details["diagnostics"]
    )
    reopened = decode_execution(encode_execution(execution))
    assert reopened == execution
    reopened_event = next(
        event
        for event in reopened.events
        if event.event_type == "current_fundamental_lineage"
    )
    assert reopened_event.details == lineage_event.details


def test_current_fundamental_lineage_event_is_same_run_and_codec_persistent(
    tmp_path: Path,
) -> None:
    service = _service(
        tmp_path,
        ("AAA", "BBB"),
        {"AAA": Decimal("88.5"), "BBB": Decimal("77.5")},
    )

    class _CurrentProvider:
        future_stock_code: str | None = None
        diagnostics: tuple[str, ...] = ()
        source_row_count = 0
        comparator_row_count = 0

        def load_pe(
            self,
            *,
            stock_code: str,
            cutoff_at: datetime,
            expected_market_date: date | str,
        ) -> tuple[CurrentObservedPEInput, tuple[str, ...]]:
            quote_date = (
                expected_market_date
                if isinstance(expected_market_date, date)
                else date.fromisoformat(expected_market_date)
            )
            return (
                CurrentObservedPEInput(
                    stock_code=stock_code,
                    value=Decimal("10") if stock_code == "AAA" else Decimal("20"),
                    as_of_date=quote_date,
                    available_at=cutoff_at - timedelta(milliseconds=100),
                    source="official.valuation.capture",
                    source_version=f"official-pe-v1:{stock_code}",
                    market="twse",
                    raw_response_sha256=("a" if stock_code == "AAA" else "b") * 64,
                    market_calendar_session_date=quote_date,
                    market_calendar_reason_code="last_completed_official_session",
                ),
                (),
            )

        def load_monthly_revenues(
            self, *, stock_code: str, cutoff_at: datetime
        ) -> CurrentMonthlyRevenueReadResult:
            raw_hash = ("c" if stock_code == "AAA" else "d") * 64
            raw_source_version = (
                "mops-static-twse-2026-04-sha256-" + raw_hash
            )
            source = "mops.monthly_revenue_static_snapshot"
            current_value = Decimal("100000") if stock_code == "AAA" else Decimal("400000")
            baseline_value = Decimal("90000") if stock_code == "AAA" else Decimal("200000")
            current_clock = (
                cutoff_at + timedelta(seconds=1)
                if stock_code == self.future_stock_code
                else cutoff_at - timedelta(seconds=2)
            )
            comparator_clock = cutoff_at - timedelta(seconds=5)
            current = CurrentObservedMonthlyRevenueInput(
                stock_code=stock_code,
                period="2026-04",
                revenue=current_value,
                observed_at=current_clock,
                source_available_at=None,
                available_at=current_clock,
                source=source,
                source_version=(
                    "mops-current-revenue-normalizer.v2:twse:2026-04:raw:"
                    + raw_source_version
                    + ":derived:sha256:"
                    + "e" * 64
                ),
                market="twse",
                raw_source_version=raw_source_version,
                raw_source_sha256=raw_hash,
            )
            comparator = CurrentObservedMonthlyRevenueInput(
                stock_code=stock_code,
                period="2025-04",
                revenue=baseline_value,
                observed_at=comparator_clock,
                source_available_at=None,
                available_at=comparator_clock,
                source=source,
                source_version=(
                    "mops-current-revenue-yoy-comparator.v1:twse:2025-04:from:2026-04:raw:"
                    + raw_source_version
                    + ":derived:sha256:"
                    + "f" * 64
                ),
                market="twse",
                raw_source_version=raw_source_version,
                raw_source_sha256=raw_hash,
                input_role="same_report_prior_year_comparison_baseline",
                parent_report_period="2026-04",
            )
            return CurrentMonthlyRevenueReadResult(
                status="ready",
                stock_code=stock_code,
                cutoff_at=cutoff_at,
                latest_period="2026-04",
                observations=(current,),
                diagnostics=self.diagnostics,
                comparison_baseline=comparator,
                diagnostic_source_row_count=self.source_row_count,
                diagnostic_comparator_row_count=self.comparator_row_count,
            )

    current_provider = _CurrentProvider()
    service.recommendation_input_preparer.current_fundamental_provider = current_provider
    config = _config()
    config["as_of_date"] = None
    config["filters"] = {
        "pe_ratio_max": "30",
        "monthly_revenue_yoy_min": "10",
    }

    def run(code: str):
        capture: dict[str, Any] = {}
        execution = execute_recommendation(
            service,
            config,
            max_stocks=1,
            top_n=1,
            universe=[code],
            result_id=f"current-lineage-{code}",
            capture_sink=capture,
        )
        assert execution.status is ExecutionStatus.COMPLETED
        event = next(
            item
            for item in execution.events
            if item.event_type == "current_fundamental_lineage"
        )
        return execution, capture, event

    execution_a, capture_a, event_a = run("AAA")
    encoded_a = encode_execution(execution_a)
    reopened_a = decode_execution(encoded_a)
    reopened_event_a = next(
        item
        for item in reopened_a.events
        if item.event_type == "current_fundamental_lineage"
    )
    assert reopened_event_a.details == event_a.details
    assert event_a.details["result_id"] == "current-lineage-AAA"
    assert event_a.details["invocation_id"]
    assert event_a.details["source_id"]
    assert len(event_a.details["market_data_fingerprint"]) == 64
    assert len(event_a.details["data_fingerprint"]) == 64
    assert {fact["stock_code"] for fact in event_a.details["facts"]} == {"AAA"}
    assert {fact["metric"] for fact in event_a.details["facts"]} == {
        "pe",
        "monthly_revenue",
    }
    monthly_facts_a = [
        fact
        for fact in event_a.details["facts"]
        if fact["metric"] == "monthly_revenue"
    ]
    assert {fact["input_role"] for fact in monthly_facts_a} == {
        "reported_period_value",
        "same_report_prior_year_comparison_baseline",
    }
    assert all(fact["unit"] == "TWD" for fact in monthly_facts_a)
    assert all(
        fact["source_version_content_sha256"]
        == fact["raw_source_version"].rsplit("-sha256-", 1)[-1]
        for fact in monthly_facts_a
    )
    assert all(
        fact["verified_response_body_bytes_sha256"] is None
        and fact["response_body_bytes_hash_status"]
        == "not_persisted_on_current_observation_row"
        and "raw_source_sha256" not in fact
        for fact in monthly_facts_a
    )
    assert all(fact["formal_pit_eligible"] is False for fact in event_a.details["facts"])
    assert event_a.details["facts"]
    assert event_a.details["requests"]

    _, capture_b, event_b = run("BBB")
    assert capture_a["compatibility_snapshot"].materialize()["last_run_context"][
        "result_id"
    ] == "current-lineage-AAA"
    assert capture_b["compatibility_snapshot"].materialize()["last_run_context"][
        "result_id"
    ] == "current-lineage-BBB"
    assert encode_execution(reopened_a) == encoded_a
    assert {fact["stock_code"] for fact in event_b.details["facts"]} == {"BBB"}
    assert all(fact["stock_code"] == "AAA" for fact in event_a.details["facts"])

    current_provider.future_stock_code = "AAA"
    with pytest.raises(ValueError, match="after freeze"):
        run("AAA")

    current_provider.future_stock_code = None
    current_provider.diagnostics = tuple(f"source_warning:{index}" for index in range(9))
    current_provider.source_row_count = 5
    current_provider.comparator_row_count = 1
    diagnostic_execution, _diagnostic_capture, diagnostic_event = run("AAA")
    assert diagnostic_execution.status is ExecutionStatus.COMPLETED
    assert diagnostic_event.details["diagnostics"] == current_provider.diagnostics
    assert diagnostic_event.details["diagnostic_source_row_count"] == 5
    assert diagnostic_event.details["diagnostic_comparator_row_count"] == 1

    current_provider.diagnostics = tuple(f"source_warning:{index}" for index in range(21))
    failed_capture: dict[str, Any] = {}
    with pytest.raises(ValueError, match="fundamental_input_diagnostics is malformed or unbounded"):
        execute_recommendation(
            service,
            config,
            max_stocks=1,
            top_n=1,
            universe=["AAA"],
            result_id="current-lineage-diagnostics-rejected",
            capture_sink=failed_capture,
        )
    failed_context = failed_capture["compatibility_snapshot"].materialize()[
        "last_run_context"
    ]
    assert failed_context["fundamental_input_diagnostics"] == list(
        current_provider.diagnostics
    )
    assert "execution" not in failed_capture


def test_current_pe_requires_each_stock_quote_on_expected_market_session(
    tmp_path: Path,
) -> None:
    frame = pd.concat(
        [
            _market_frame("FRESH"),
            _market_frame("STALE", start=date(2026, 4, 30)),
        ],
        ignore_index=True,
    )
    provider = _FrameProvider(frame)
    service = _service(
        tmp_path,
        ("FRESH", "STALE"),
        {"FRESH": Decimal("88.5"), "STALE": Decimal("77.5")},
        provider=provider,
    )

    class _CurrentPEProvider:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def load_pe(
            self,
            *,
            stock_code: str,
            cutoff_at: datetime,
            expected_market_date: date | str,
        ) -> tuple[CurrentObservedPEInput, tuple[str, ...]]:
            self.calls.append(stock_code)
            quote_date = (
                expected_market_date
                if isinstance(expected_market_date, date)
                else date.fromisoformat(expected_market_date)
            )
            return (
                CurrentObservedPEInput(
                    stock_code=stock_code,
                    value=Decimal("12.5"),
                    as_of_date=quote_date,
                    available_at=cutoff_at - timedelta(seconds=1),
                    source="official.valuation.capture",
                    source_version=f"official-pe-v1:{stock_code}",
                    market="twse",
                    raw_response_sha256="a" * 64,
                    market_calendar_session_date=quote_date,
                    market_calendar_reason_code="last_completed_official_session",
                ),
                (),
            )

    current_provider = _CurrentPEProvider()
    service.recommendation_input_preparer.current_fundamental_provider = (
        current_provider
    )
    config = _config()
    config["as_of_date"] = None
    config["filters"] = {"pe_ratio_max": "30"}
    capture: dict[str, Any] = {}

    execution = execute_recommendation(
        service,
        config,
        max_stocks=2,
        top_n=2,
        universe=["FRESH", "STALE"],
        result_id="current-pe-per-stock-session-gate",
        capture_sink=capture,
    )

    assert execution.status is ExecutionStatus.COMPLETED
    assert current_provider.calls == ["FRESH"]
    context = capture["compatibility_snapshot"].materialize()["last_run_context"]
    assert context["expected_market_date"] == "2026-05-20"
    assert context["fundamental_inputs"]
    assert {
        item["stock_code"]
        for item in context["fundamental_inputs"]
        if item["metric"] == "pe"
    } == {"FRESH"}
    assert (
        "current_pe_stock_quote_date_not_expected_session:STALE:"
        "expected=2026-05-20:observed=2026-05-19"
    ) in context["fundamental_input_diagnostics"]


def test_current_fundamental_lineage_bounds_follow_large_universe_and_roundtrip(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path, ("AAA",), {"AAA": Decimal("88.5")})
    capture: dict[str, Any] = {}
    config = _config()
    config["as_of_date"] = None
    execution = execute_recommendation(
        service,
        config,
        max_stocks=1,
        top_n=1,
        universe=["AAA"],
        result_id="lineage-large-shape-seed",
        capture_sink=capture,
    )
    legacy_context = deepcopy(
        capture["compatibility_snapshot"].materialize()["last_run_context"]
    )
    cutoff = datetime.fromisoformat(
        legacy_context["current_observation_cutoff_at"]
    )
    observation_at = cutoff - timedelta(seconds=1)
    requests: list[dict[str, object]] = []
    projected_facts: list[dict[str, object]] = []
    captured_observations: list[dict[str, object]] = []
    diagnostics: list[str] = []
    universe_size = 501
    for index in range(universe_size):
        code = f"{index:04d}"
        raw_hash = f"{index + 1:064x}"
        raw_source_version = (
            f"mops-static-twse-2026-04-sha256-{raw_hash}"
        )
        requests.extend(
            (
                {
                    "request_id": f"pe:{code}",
                    "stock_code": code,
                    "metric": "pe",
                    "scope": "natural_current_observation",
                    "decision_date": "2026-04-30",
                    "current_observation_cutoff_at": cutoff.isoformat(),
                },
                {
                    "request_id": f"monthly:{code}",
                    "stock_code": code,
                    "metric": "monthly_revenue",
                    "scope": "natural_current_observation",
                    "decision_date": "2026-04-30",
                    "current_observation_cutoff_at": cutoff.isoformat(),
                },
            )
        )
        projected_facts.append(
            {
                "stock_code": code,
                "metric": "pe",
                "scope": "natural_current_observation",
                "value": "12.5",
                "as_of_date": "2026-04-30",
                "expected_market_date": "2026-04-30",
                "available_at": observation_at.isoformat(),
                "observed_at": observation_at.isoformat(),
                "source_available_at": None,
                "source": "official.valuation.capture",
                "source_version": f"valuation:{code}:v1",
                "raw_response_sha256": "a" * 64,
                "market": "twse",
                "formal_pit_eligible": False,
            }
        )
        current_version = (
            "mops-current-revenue-normalizer.v2:twse:2026-04:raw:"
            + raw_source_version
            + ":derived:sha256:"
            + "b" * 64
        )
        comparator_version = (
            "mops-current-revenue-yoy-comparator.v1:twse:2025-04:from:2026-04:raw:"
            + raw_source_version
            + ":derived:sha256:"
            + "c" * 64
        )
        common_monthly = {
            "stock_code": code,
            "metric": "monthly_revenue",
            "scope": "natural_current_observation",
            "unit": "TWD",
            "period_basis": "monthly_flow",
            "basis_verified": True,
            "aggregate_feature_eligible": False,
            "observed_at": observation_at.isoformat(),
            "source_available_at": None,
            "available_at": observation_at.isoformat(),
            "availability_basis": "local_verified_observation",
            "source": "mops.monthly_revenue_static_snapshot",
            "raw_source_sha256": raw_hash,
            "market": "twse",
            "formal_pit_eligible": False,
        }
        captured_observations.extend(
            (
                {
                    **common_monthly,
                    "input_role": "reported_period_value",
                    "parent_report_period": "2026-04",
                    "period": "2026-04",
                    "source_version": current_version,
                    "value": "1000000",
                },
                {
                    **common_monthly,
                    "input_role": "same_report_prior_year_comparison_baseline",
                    "parent_report_period": "2026-04",
                    "period": "2025-04",
                    "source_version": comparator_version,
                    "value": "900000",
                },
            )
        )
        diagnostics.append(f"{code}:current_source_observed")

    legacy_context["fundamental_input_requests"] = requests
    legacy_context["fundamental_inputs"] = projected_facts
    legacy_context["current_fundamental_observations"] = captured_observations
    legacy_context["fundamental_input_diagnostics"] = diagnostics
    event = _current_fundamental_lineage_event(
        legacy_context,
        result_id=execution.result_id,
        invocation_id="large-universe-lineage-invocation",
        decision_at=execution.context.decision_at,
        max_stocks=universe_size,
    )

    assert event is not None
    assert len(event.details["requests"]) == 2 * universe_size
    assert len(event.details["facts"]) == 3 * universe_size
    assert len(event.details["diagnostics"]) == universe_size
    large_execution = replace(execution, events=(event,))
    reopened = decode_execution(encode_execution(large_execution))
    assert reopened == large_execution


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
    import app_module.recommendation.execute as execute_module

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
            current = datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc)
            return current.astimezone(tz) if tz is not None else current.replace(tzinfo=None)

    monkeypatch.setattr(service_module, "datetime", _FrozenRecommendationDatetime)
    monkeypatch.setattr(
        execute_module,
        "_utc_now",
        lambda: datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc),
    )
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
