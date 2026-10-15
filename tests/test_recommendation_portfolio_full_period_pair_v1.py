"""以真 Registry capture 驗證明示雙 run 的期間覆蓋配對。"""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any, Callable, Literal, cast

import pandas as pd
import pytest

from app_module.recommendation.composition import build_recommendation_composition
from app_module.recommendation.portfolio_result_reader import (
    RecommendationPortfolioResultReadCancelledError,
    RecommendationPortfolioResultReadbackError,
    RecommendationPortfolioResultReader,
)
from app_module.recommendation_portfolio_backtest_service import RecommendationPortfolioBacktestService
from app_module.recommendation_portfolio_calendar_artifact_v1 import (
    write_portfolio_period_calendar_evidence_create_only_v1,
)
from app_module.recommendation_portfolio_calendar_evidence_v1 import (
    PortfolioPeriodCalendarEvidenceV1,
)
from app_module.recommendation_portfolio_full_period_pair_v1 import (
    FullPeriodPairReadCancelledV1,
    FullPeriodPairReadErrorV1,
    FullPeriodPairReadV1,
    RecommendationPortfolioFullPeriodPairReadServiceV1,
)
from app_module.recommendation_portfolio_period_calendar_read_pin_v1 import (
    PortfolioPeriodCalendarReadPinV1,
)
from app_module.recommendation_portfolio_dtos import RecommendationPortfolioBacktestResultDTO
from app_module.research_run_dtos import ResearchRunMetadataDTO
from app_module.research_run_service import (
    ResearchRunIntegrityError,
    ResearchRunReadCancelledError,
    ResearchRunService,
)
from app_module.saved_strategy_rule_card import metadata_sha256
from data_module.config import TWStockConfig
from data_module.official_calendar_bundle import (
    CapturedCalendarResponse,
    TPEX_MARKET_CALENDAR_URL,
    TWSE_HOLIDAY_SCHEDULE_URL,
    hash_response_bytes,
)


_CAPITAL_LEFT = Decimal("9007199254740993.01")
_CAPITAL_RIGHT = Decimal("9007199254740994.01")
_DATES = ("2026-01-02", "2026-01-05", "2026-01-06")
_START = "2026-01-02"
_END = "2026-01-06"


def _config(tmp_path: Path) -> TWStockConfig:
    return TWStockConfig(data_root=tmp_path / "data", output_root=tmp_path / "output", profile="test")


def _produce(
    *,
    parent_result_id: str,
    stock_code: str = "2330",
    stock_name: str = "合成股",
    start_date: str = _START,
    end_date: str = _END,
    observed_dates: tuple[str, ...] = _DATES,
    initial_capital: Decimal = _CAPITAL_LEFT,
    cancelled: bool = False,
) -> RecommendationPortfolioBacktestResultDTO:
    """呼叫實際單股 producer；資料只包含本 fixture 明示的日期。"""

    def provider(*_args):
        return [{"stock_code": stock_code, "stock_name": stock_name, "total_score": 90,
                 "factor_scores": {"technical": 90}}]

    cancel_checks = 0

    def check_cancel() -> bool:
        nonlocal cancel_checks
        cancel_checks += 1
        return cancelled and cancel_checks >= 2

    history = pd.DataFrame([
        {"日期": day, "證券代號": stock_code, "證券名稱": stock_name,
         "開盤價": Decimal("100.01"), "收盤價": Decimal("100.00")}
        for day in observed_dates
    ])
    return RecommendationPortfolioBacktestService(provider=provider)._run_next_open_portfolio(
        start_date=start_date, end_date=end_date, profile_id="full-period-pair-fixture",
        config={"regime": "Trend"}, history=history, initial_capital=initial_capital,
        rebalance_frequency="once", top_n=1, allocation_method="equal_weight", holding_days=10,
        stop_loss_pct=None, take_profit_pct=None, max_participation_rate=None,
        fee_bps=Decimal("0"), slippage_bps=Decimal("0"), tax_bps=Decimal("0"),
        lot_size=1, check_cancel=check_cancel, include_benchmark=False,
        cost_policy_id=None, cost_policy_instrument_type=None, cost_policy_lot_type=None,
        parent_result_id=parent_result_id,
    )


def _metadata(
    *,
    run_id: str,
    result: RecommendationPortfolioBacktestResultDTO,
    strategy_id: str,
    strategy_version: str = "fixture-v1",
    start_date: str = _START,
    end_date: str = _END,
    initial_capital: Decimal = _CAPITAL_LEFT,
) -> ResearchRunMetadataDTO:
    parent_id = result.replay_parent_id
    return ResearchRunMetadataDTO(
        run_id=run_id,
        run_name=f"期間配對 {run_id}",
        run_type="recommendation_portfolio",
        strategy_id=strategy_id,
        strategy_version=strategy_version,
        original_input={"config": {"profile_id": "full-period-pair-fixture"}},
        normalized_params={"start_date": start_date, "end_date": end_date},
        start_date=start_date,
        end_date=end_date,
        capital_cents=int(initial_capital * 100),
        data_manifest={
            "execution_contract": "next-session-open.v2",
            "replay_lineage_status": {
                "schema_version": 1,
                "status": "unavailable",
                "parent_result_id": parent_id,
                "reason": "canonical_child_unavailable",
            },
        },
        payload_hash="sha256:caller-placeholder",
    )


def _save(
    service: ResearchRunService,
    *,
    run_id: str,
    result: RecommendationPortfolioBacktestResultDTO,
    strategy_id: str,
    strategy_version: str = "fixture-v1",
    start_date: str = _START,
    end_date: str = _END,
    initial_capital: Decimal = _CAPITAL_LEFT,
    legacy_v1: bool = False,
):
    if legacy_v1:
        # 走 Registry 既有 V1 encoder；不製作或推導任何 V1 精確 capture。
        result = replace(
            result,
            period_precision_capture=None,
            period_precision_observations=(),
            period_precision_capture_status="not_applicable",
            period_precision_capture_reason=None,
        )
    metadata = _metadata(
        run_id=run_id,
        result=result,
        strategy_id=strategy_id,
        strategy_version=strategy_version,
        start_date=start_date,
        end_date=end_date,
        initial_capital=initial_capital,
    )
    return service.save_run(
        metadata,
        result.equity_curve,
        result.trades,
        portfolio_result=result,
    )


def _calendar_candidate(
    tmp_path: Path,
    config: TWStockConfig,
) -> tuple[Path, str, tuple[Path, ...]]:
    """保存僅供測試的原始日曆候選，不自稱官方認證日曆。"""

    artifact_parent = tmp_path / "calendar_candidate"
    artifact_parent.mkdir(parents=True)
    protected_roots = (
        Path(config.data_root).resolve(),
        Path(config.output_root).resolve(),
        (tmp_path / "formal_data").resolve(),
        (tmp_path / "formal_output").resolve(),
        (tmp_path / "operation_root").resolve(),
    )
    for protected_root in protected_roots:
        protected_root.mkdir(parents=True, exist_ok=True)

    twse_payload = [
        {"Name": "元旦", "Date": "1150101", "Description": "放假一日。"},
    ]
    twse_raw = json.dumps(twse_payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    twse_response = CapturedCalendarResponse(
        kind="twse",
        key="2026",
        source=f"{TWSE_HOLIDAY_SCHEDULE_URL}?queryYear=115",
        source_hash=hash_response_bytes(twse_raw),
        payload=twse_payload,
        raw_bytes=twse_raw,
        metadata={"capture_mode": "fixture_only", "request_params": {"queryYear": "115"}},
    )
    tpex_payload: dict[str, object] = {
        "calendar": {
            "total": len(_DATES),
            "data": {
                "20260102": {"holiday": False, "holidayList": []},
                "20260105": {"holiday": False, "holidayList": []},
                "20260106": {"holiday": False, "holidayList": []},
            },
            "status": "success",
        },
    }
    tpex_raw = json.dumps(tpex_payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    tpex_response = CapturedCalendarResponse(
        kind="tpex",
        key="202601",
        source=f"{TPEX_MARKET_CALENDAR_URL}?ym=202601&lang=zh-tw",
        source_hash=hash_response_bytes(tpex_raw),
        payload=tpex_payload,
        raw_bytes=tpex_raw,
        metadata={"capture_mode": "fixture_only", "request_params": {"ym": "202601", "lang": "zh-tw"}},
    )
    evidence = PortfolioPeriodCalendarEvidenceV1.build(
        start_date=date.fromisoformat(_START),
        end_date=date.fromisoformat(_END),
        twse_responses={2026: twse_response},
        tpex_responses={"202601": tpex_response},
        captured_at=datetime(2026, 1, 1, 16, 0, tzinfo=timezone.utc),
    )
    calendar_path = artifact_parent / "fixture-only-calendar.json"
    calendar_sha256 = write_portfolio_period_calendar_evidence_create_only_v1(
        calendar_path,
        evidence,
        protected_roots=protected_roots,
    )
    return calendar_path, calendar_sha256, protected_roots


def _read_service(config: TWStockConfig) -> tuple[ResearchRunService, RecommendationPortfolioResultReader]:
    reopened = ResearchRunService(config)
    reader = RecommendationPortfolioResultReader(
        reopened,
        build_recommendation_composition(config).persistence,
    )
    return reopened, reader


def _pair_read(
    service: ResearchRunService,
    reader: RecommendationPortfolioResultReader,
    left_run_id: str,
    right_run_id: str,
    calendar: tuple[Path, str, tuple[Path, ...]],
    *,
    market: Literal["twse", "tpex"] = "twse",
    expected_left_metadata_sha256: str | None = None,
    expected_right_metadata_sha256: str | None = None,
    check_cancel: Callable[[], bool] | None = None,
) -> FullPeriodPairReadV1:
    calendar_path, calendar_sha256, protected_roots = calendar
    return RecommendationPortfolioFullPeriodPairReadServiceV1(
        service,
        reader,
    ).read(
        left_run_id,
        right_run_id,
        calendar_path=calendar_path,
        expected_calendar_sha256=calendar_sha256,
        market=market,
        protected_roots=protected_roots,
        expected_left_metadata_sha256=expected_left_metadata_sha256,
        expected_right_metadata_sha256=expected_right_metadata_sha256,
        check_cancel=check_cancel,
    )


def _saved_pair(
    tmp_path: Path,
    *,
    left_dates: tuple[str, ...] = _DATES,
    right_dates: tuple[str, ...] = _DATES,
    left_stock_code: str = "2330",
    right_stock_code: str = "2330",
    left_start_date: str = _START,
    left_end_date: str = _END,
    right_start_date: str = _START,
    right_end_date: str = _END,
    left_parent_id: str = "pair-parent-left",
    right_parent_id: str = "pair-parent-right",
    left_strategy_id: str = "strategy-left",
    right_strategy_id: str = "strategy-right",
    left_strategy_version: str = "fixture-v1",
    right_strategy_version: str = "fixture-v2",
    left_cancelled: bool = False,
    left_legacy_v1: bool = False,
):
    config = _config(tmp_path)
    writer = ResearchRunService(config)
    left_result = _produce(
        parent_result_id=left_parent_id,
        stock_code=left_stock_code,
        start_date=left_start_date,
        end_date=left_end_date,
        observed_dates=left_dates,
        initial_capital=_CAPITAL_LEFT,
        cancelled=left_cancelled,
    )
    right_result = _produce(
        parent_result_id=right_parent_id,
        stock_code=right_stock_code,
        start_date=right_start_date,
        end_date=right_end_date,
        observed_dates=right_dates,
        initial_capital=_CAPITAL_RIGHT,
    )
    left_saved = _save(
        writer,
        run_id="pair-left-run",
        result=left_result,
        strategy_id=left_strategy_id,
        strategy_version=left_strategy_version,
        start_date=left_start_date,
        end_date=left_end_date,
        initial_capital=_CAPITAL_LEFT,
        legacy_v1=left_legacy_v1,
    )
    right_saved = _save(
        writer,
        run_id="pair-right-run",
        result=right_result,
        strategy_id=right_strategy_id,
        strategy_version=right_strategy_version,
        start_date=right_start_date,
        end_date=right_end_date,
        initial_capital=_CAPITAL_RIGHT,
    )
    reopened, reader = _read_service(config)
    calendar = _calendar_candidate(tmp_path, config)
    return config, reopened, reader, calendar, left_saved, right_saved, left_result, right_result


def _persisted_bytes(
    service: ResearchRunService,
    run_ids: tuple[str, str],
    calendar_path: Path,
) -> dict[str, bytes]:
    values = {"registry": service.repository.db_path.read_bytes(), "calendar": calendar_path.read_bytes()}
    for run_id in run_ids:
        paths = service._paths_for(run_id)
        values[f"{run_id}:portfolio"] = Path(paths["portfolio_result_final"]).read_bytes()
    return values


def test_actual_registry_full_period_pair_preserves_capture_bytes_and_decimal_values(tmp_path: Path) -> None:
    config, service, reader, calendar, left_saved, right_saved, left_source, right_source = _saved_pair(tmp_path)
    calendar_path = calendar[0]
    before = _persisted_bytes(service, (left_saved.run_id, right_saved.run_id), calendar_path)

    result = _pair_read(service, reader, left_saved.run_id, right_saved.run_id, calendar)

    assert type(result) is FullPeriodPairReadV1
    assert (result.left.registry_run_id, result.right.registry_run_id) == (left_saved.run_id, right_saved.run_id)
    assert result.left.parent_id == "pair-parent-left"
    assert result.right.parent_id == "pair-parent-right"
    assert (result.left.strategy_id, result.right.strategy_id) == ("strategy-left", "strategy-right")
    assert (result.left.strategy_version, result.right.strategy_version) == ("fixture-v1", "fixture-v2")
    left_metadata = service.repository.get_metadata(left_saved.run_id)
    right_metadata = service.repository.get_metadata(right_saved.run_id)
    assert left_metadata is not None and right_metadata is not None
    assert result.left.metadata_identity_sha256 == metadata_sha256(left_metadata)
    assert result.right.metadata_identity_sha256 == metadata_sha256(right_metadata)
    assert result.expected_session_dates == _DATES
    assert result.left_actual_session_dates == _DATES
    assert result.right_actual_session_dates == _DATES
    assert result.left_missing_session_dates == result.right_missing_session_dates == ()
    assert result.left_unexpected_session_dates == result.right_unexpected_session_dates == ()
    assert result.coverage_complete is True
    # 完整列日只說明結構覆蓋；fixture日曆與來源權威未知仍阻止績效資格。
    assert result.status == "blocked"
    assert "calendar_candidate_only" in result.reasons
    assert "left_source_evidence_unknown" in result.reasons
    assert "right_source_evidence_unknown" in result.reasons
    assert result.performance_eligible is False
    assert result.historical_pit_eligible is False
    assert result.broker_eligible is False
    assert result.metrics is None
    left_capture = left_source.period_precision_capture
    right_capture = right_source.period_precision_capture
    assert left_capture is not None and right_capture is not None
    assert result.left.capture == left_capture
    assert result.right.capture == right_capture
    assert result.left.capture is not None and result.right.capture is not None
    assert result.left.capture.initial_capital_decimal == str(_CAPITAL_LEFT)
    assert result.right.capture.initial_capital_decimal == str(_CAPITAL_RIGHT)
    assert result.left.capture.observations[0].equity_decimal == left_capture.observations[0].equity_decimal
    assert result.right.capture.observations[0].equity_decimal == right_capture.observations[0].equity_decimal
    assert result.left.capture is not result.right.capture
    assert result.left.precision is None
    assert result.right.precision is None
    assert _persisted_bytes(service, (left_saved.run_id, right_saved.run_id), calendar_path) == before


def test_portfolio_reader_accepts_expected_metadata_sha_and_forwards_budgets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, service, reader, _, left_saved, _, _, _ = _saved_pair(tmp_path)
    metadata = service.repository.get_metadata(left_saved.run_id)
    assert metadata is not None
    expected_sha256 = metadata_sha256(metadata)
    max_artifact_bytes = 16 * 1024**2
    max_total_bytes = 32 * 1024**2
    original_load_run_data = service.load_run_data
    load_calls: list[tuple[str, dict[str, int]]] = []

    def record_load_run_data(run_id: str, **kwargs: int) -> Any:
        load_calls.append((run_id, dict(kwargs)))
        return original_load_run_data(run_id, **kwargs)

    monkeypatch.setattr(service, "load_run_data", record_load_run_data)

    result = reader.read(
        left_saved.run_id,
        expected_metadata_sha256=expected_sha256,
        max_artifact_bytes=max_artifact_bytes,
        max_total_bytes=max_total_bytes,
    )

    assert type(result) is RecommendationPortfolioBacktestResultDTO
    assert load_calls == [(
        left_saved.run_id,
        {"max_artifact_bytes": max_artifact_bytes, "max_total_bytes": max_total_bytes},
    )]


def test_portfolio_reader_rejects_wrong_metadata_sha_before_dto_decode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, service, reader, _, left_saved, _, _, _ = _saved_pair(tmp_path)
    metadata = service.repository.get_metadata(left_saved.run_id)
    assert metadata is not None
    expected_sha256 = metadata_sha256(metadata)
    wrong_sha256 = ("0" if expected_sha256[0] != "0" else "1") + expected_sha256[1:]
    decode_calls = 0
    original_read_verified_data = reader._read_verified_data

    def record_decode(registry_run_id: str, loaded: Any) -> Any:
        nonlocal decode_calls
        decode_calls += 1
        return original_read_verified_data(registry_run_id, loaded)

    monkeypatch.setattr(reader, "_read_verified_data", record_decode)

    with pytest.raises(
        RecommendationPortfolioResultReadbackError,
        match="所選 metadata 與 exact reader 來源不符",
    ):
        reader.read(left_saved.run_id, expected_metadata_sha256=wrong_sha256)

    assert decode_calls == 0


def test_portfolio_reader_rejects_metadata_changed_after_verified_decode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, service, reader, _, left_saved, _, _, _ = _saved_pair(tmp_path)
    metadata = service.repository.get_metadata(left_saved.run_id)
    assert metadata is not None
    expected_sha256 = metadata_sha256(metadata)
    original_read_verified_data = reader._read_verified_data
    decode_completed = False

    def decode_then_change_metadata(registry_run_id: str, loaded: Any) -> Any:
        nonlocal decode_completed
        result = original_read_verified_data(registry_run_id, loaded)
        decode_completed = True
        with sqlite3.connect(service.repository.db_path) as connection:
            connection.execute(
                "UPDATE research_runs SET strategy_version = ? WHERE run_id = ?",
                ("post-decode-mutated-version", left_saved.run_id),
            )
        return result

    monkeypatch.setattr(reader, "_read_verified_data", decode_then_change_metadata)

    with pytest.raises(
        RecommendationPortfolioResultReadbackError,
        match="exact 讀取期間 metadata 已變更",
    ):
        reader.read(left_saved.run_id, expected_metadata_sha256=expected_sha256)

    assert decode_completed is True


def test_portfolio_reader_fails_closed_when_sidecar_exceeds_artifact_budget(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, service, reader, _, left_saved, _, _, _ = _saved_pair(tmp_path)
    paths = service._paths_for(left_saved.run_id)
    parquet_budget = max(
        paths["equity_final"].stat().st_size,
        paths["trades_final"].stat().st_size,
    )
    sidecar_path = paths["portfolio_result_final"]
    assert sidecar_path.stat().st_size > parquet_budget
    decode_calls = 0
    original_read_verified_data = reader._read_verified_data

    def record_decode(registry_run_id: str, loaded: Any) -> Any:
        nonlocal decode_calls
        decode_calls += 1
        return original_read_verified_data(registry_run_id, loaded)

    monkeypatch.setattr(reader, "_read_verified_data", record_decode)

    with pytest.raises(RecommendationPortfolioResultReadbackError) as exc_info:
        reader.read(
            left_saved.run_id,
            max_artifact_bytes=parquet_budget,
            max_total_bytes=128 * 1024**2,
        )

    assert "artifact_byte_budget_exceeded" in str(exc_info.value.__cause__)
    assert str(sidecar_path) in str(exc_info.value.__cause__)
    assert decode_calls == 0


def test_full_pair_reads_with_both_selection_metadata_pins(tmp_path: Path) -> None:
    _, service, reader, calendar, left_saved, right_saved, _, _ = _saved_pair(tmp_path)
    left_metadata = service.repository.get_metadata(left_saved.run_id)
    right_metadata = service.repository.get_metadata(right_saved.run_id)
    assert left_metadata is not None and right_metadata is not None
    left_pin = metadata_sha256(left_metadata)
    right_pin = metadata_sha256(right_metadata)

    result = _pair_read(
        service,
        reader,
        left_saved.run_id,
        right_saved.run_id,
        calendar,
        expected_left_metadata_sha256=left_pin,
        expected_right_metadata_sha256=right_pin,
    )

    assert result.left.metadata_identity_sha256 == left_pin
    assert result.right.metadata_identity_sha256 == right_pin
    assert result.left.registry_run_id == left_saved.run_id
    assert result.right.registry_run_id == right_saved.run_id


@pytest.mark.parametrize(
    ("side", "pin_kind"),
    [("left", "stale"), ("right", "stale"), ("left", "invalid"), ("right", "invalid")],
)
def test_full_pair_rejects_stale_or_invalid_selection_pin_before_artifact_load(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    side: Literal["left", "right"],
    pin_kind: Literal["stale", "invalid"],
) -> None:
    _, service, reader, calendar, left_saved, right_saved, _, _ = _saved_pair(tmp_path)
    left_metadata = service.repository.get_metadata(left_saved.run_id)
    right_metadata = service.repository.get_metadata(right_saved.run_id)
    assert left_metadata is not None and right_metadata is not None
    left_pin = metadata_sha256(left_metadata)
    right_pin = metadata_sha256(right_metadata)
    if pin_kind == "stale":
        current_pin = left_pin if side == "left" else right_pin
        bad_pin = ("0" if current_pin[0] != "0" else "1") + current_pin[1:]
    else:
        bad_pin = "not-a-canonical-sha"
    if side == "left":
        left_pin = bad_pin
    else:
        right_pin = bad_pin

    load_calls: list[str] = []
    original_load_run_data = service.load_run_data

    def record_load_run_data(run_id: str, **kwargs: Any) -> Any:
        load_calls.append(run_id)
        return original_load_run_data(run_id, **kwargs)

    monkeypatch.setattr(service, "load_run_data", record_load_run_data)

    with pytest.raises(FullPeriodPairReadErrorV1, match=side):
        _pair_read(
            service,
            reader,
            left_saved.run_id,
            right_saved.run_id,
            calendar,
            expected_left_metadata_sha256=left_pin,
            expected_right_metadata_sha256=right_pin,
        )

    assert load_calls == []


def test_full_pair_immediate_cancellation_does_not_load_either_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, service, reader, calendar, left_saved, right_saved, _, _ = _saved_pair(tmp_path)
    load_calls: list[str] = []
    original_load_run_data = service.load_run_data

    def record_load_run_data(run_id: str, **kwargs: Any) -> Any:
        load_calls.append(run_id)
        return original_load_run_data(run_id, **kwargs)

    monkeypatch.setattr(service, "load_run_data", record_load_run_data)

    with pytest.raises(FullPeriodPairReadCancelledV1):
        _pair_read(
            service,
            reader,
            left_saved.run_id,
            right_saved.run_id,
            calendar,
            check_cancel=lambda: True,
        )

    assert load_calls == []


def test_full_pair_cancellation_after_left_read_does_not_read_right_or_return_pair(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, service, reader, calendar, left_saved, right_saved, _, _ = _saved_pair(tmp_path)
    cancelled = False
    load_calls: list[str] = []
    reader_calls: list[str] = []
    original_load_run_data = service.load_run_data
    original_reader_read = reader.read

    def record_load_run_data(run_id: str, **kwargs: Any) -> Any:
        load_calls.append(run_id)
        return original_load_run_data(run_id, **kwargs)

    def read_then_cancel_after_left(registry_run_id: str, *args: Any, **kwargs: Any) -> Any:
        nonlocal cancelled
        reader_calls.append(registry_run_id)
        result = original_reader_read(registry_run_id, *args, **kwargs)
        if registry_run_id == left_saved.run_id:
            cancelled = True
        return result

    monkeypatch.setattr(service, "load_run_data", record_load_run_data)
    monkeypatch.setattr(reader, "read", read_then_cancel_after_left)

    with pytest.raises(FullPeriodPairReadCancelledV1):
        _pair_read(
            service,
            reader,
            left_saved.run_id,
            right_saved.run_id,
            calendar,
            check_cancel=lambda: cancelled,
        )

    assert reader_calls == [left_saved.run_id]
    assert load_calls == [left_saved.run_id, left_saved.run_id]


def test_portfolio_reader_integrity_failure_remains_error_when_cancel_flag_is_set(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, service, reader, _, left_saved, _, _, _ = _saved_pair(tmp_path)
    sidecar = service._paths_for(left_saved.run_id)["portfolio_result_final"]
    sidecar.write_bytes(sidecar.read_bytes() + b"tamper")
    cancelled = False
    original_load_run_data = service.load_run_data

    def load_and_set_cancel_after_integrity_error(run_id: str, **kwargs: Any) -> Any:
        nonlocal cancelled
        try:
            return original_load_run_data(run_id, **kwargs)
        except ResearchRunIntegrityError:
            cancelled = True
            raise

    monkeypatch.setattr(service, "load_run_data", load_and_set_cancel_after_integrity_error)

    with pytest.raises(RecommendationPortfolioResultReadbackError) as exc_info:
        reader.read(left_saved.run_id, check_cancel=lambda: cancelled)

    assert type(exc_info.value) is RecommendationPortfolioResultReadbackError
    assert isinstance(exc_info.value.__cause__, ResearchRunIntegrityError)
    assert cancelled is True


def test_full_pair_integrity_failure_remains_error_when_cancel_flag_is_set(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, service, reader, calendar, left_saved, right_saved, _, _ = _saved_pair(tmp_path)
    sidecar = service._paths_for(left_saved.run_id)["portfolio_result_final"]
    sidecar.write_bytes(sidecar.read_bytes() + b"tamper")
    cancelled = False
    original_load_run_data = service.load_run_data

    def load_and_set_cancel_after_integrity_error(run_id: str, **kwargs: Any) -> Any:
        nonlocal cancelled
        try:
            return original_load_run_data(run_id, **kwargs)
        except ResearchRunIntegrityError:
            cancelled = True
            raise

    monkeypatch.setattr(service, "load_run_data", load_and_set_cancel_after_integrity_error)

    with pytest.raises(FullPeriodPairReadErrorV1) as exc_info:
        _pair_read(
            service,
            reader,
            left_saved.run_id,
            right_saved.run_id,
            calendar,
            check_cancel=lambda: cancelled,
        )

    assert type(exc_info.value) is FullPeriodPairReadErrorV1
    assert isinstance(exc_info.value.__cause__, ResearchRunIntegrityError)
    assert cancelled is True


def test_registry_read_cancellation_remains_compatible_with_integrity_error(
    tmp_path: Path,
) -> None:
    _, service, _, _, left_saved, _, _, _ = _saved_pair(tmp_path)

    with pytest.raises(ResearchRunIntegrityError) as exc_info:
        service.load_run_data(left_saved.run_id, check_cancel=lambda: True)

    assert type(exc_info.value) is ResearchRunReadCancelledError
    assert str(exc_info.value) == "read_cancelled"


def test_calendar_read_pin_is_immutable_and_uses_explicit_sha_without_io(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected_io(*_args: Any, **_kwargs: Any) -> Any:
        pytest.fail("calendar read pin construction must not access the filesystem or hash bytes")

    monkeypatch.setattr(Path, "open", unexpected_io)
    monkeypatch.setattr(Path, "read_bytes", unexpected_io)
    monkeypatch.setattr(Path, "stat", unexpected_io)
    monkeypatch.setattr(Path, "resolve", unexpected_io)
    monkeypatch.setattr(hashlib, "sha256", unexpected_io)

    pin = PortfolioPeriodCalendarReadPinV1(
        artifact_path=tmp_path / "not-created-calendar.json",
        expected_sha256="a" * 64,
        market="twse",
        protected_roots=(tmp_path,),
    )

    assert pin.expected_sha256 == "a" * 64
    assert pin.market == "twse"
    assert pin.protected_roots == (tmp_path,)
    with pytest.raises(FrozenInstanceError):
        setattr(pin, "market", "tpex")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("expected_sha256", "A" * 64),
        ("market", None),
        ("protected_roots", ()),
        ("artifact_path", Path("relative-calendar.json")),
        ("protected_roots", (Path("relative-root"),)),
    ],
)
def test_calendar_read_pin_rejects_invalid_sha_market_roots_or_relative_path(
    tmp_path: Path,
    field: str,
    value: Any,
) -> None:
    pin_values: dict[str, Any] = {
        "artifact_path": tmp_path / "not-created-calendar.json",
        "expected_sha256": "a" * 64,
        "market": "twse",
        "protected_roots": (tmp_path,),
    }
    pin_values[field] = value

    with pytest.raises(ValueError):
        PortfolioPeriodCalendarReadPinV1(
            artifact_path=pin_values["artifact_path"],
            expected_sha256=pin_values["expected_sha256"],
            market=pin_values["market"],
            protected_roots=pin_values["protected_roots"],
        )


def test_full_pair_reports_missing_session_for_completed_partial_input(tmp_path: Path) -> None:
    _, service, reader, calendar, left_saved, right_saved, left_source, _ = _saved_pair(
        tmp_path,
        left_dates=("2026-01-02", "2026-01-05"),
    )

    result = _pair_read(service, reader, left_saved.run_id, right_saved.run_id, calendar)

    assert left_source.period_precision_capture is not None
    assert left_source.period_precision_capture.capture_status == "complete"
    assert left_source.period_precision_capture.completion_status == "completed"
    assert result.expected_session_dates == _DATES
    assert result.coverage_complete is False
    assert result.left_actual_session_dates == ("2026-01-02", "2026-01-05")
    assert result.left_missing_session_dates == ("2026-01-06",)
    assert result.left_unexpected_session_dates == ()
    assert result.right_missing_session_dates == ()
    assert result.status == "blocked"


def test_full_pair_rejects_same_or_missing_registry_run_id(tmp_path: Path) -> None:
    _, service, reader, calendar, left_saved, right_saved, _, _ = _saved_pair(tmp_path)

    with pytest.raises(FullPeriodPairReadErrorV1):
        _pair_read(service, reader, left_saved.run_id, left_saved.run_id, calendar)
    with pytest.raises(FullPeriodPairReadErrorV1):
        _pair_read(service, reader, "", right_saved.run_id, calendar)
    with pytest.raises(FullPeriodPairReadErrorV1):
        _pair_read(service, reader, cast(str, None), right_saved.run_id, calendar)
    with pytest.raises(FullPeriodPairReadErrorV1):
        _pair_read(service, reader, left_saved.run_id, "missing-registry-run", calendar)


def test_pair_rejects_reader_from_another_registry_root_with_same_run_id(tmp_path: Path) -> None:
    _, service, _reader, calendar, left_saved, right_saved, _, _ = _saved_pair(tmp_path)
    foreign_config = _config(tmp_path / "foreign-root")
    foreign_service = ResearchRunService(foreign_config)
    foreign_result = _produce(parent_result_id="foreign-root-parent", initial_capital=_CAPITAL_RIGHT)
    _save(
        foreign_service,
        run_id=left_saved.run_id,
        result=foreign_result,
        strategy_id="foreign-root-strategy",
        strategy_version="foreign-root-version",
        initial_capital=_CAPITAL_RIGHT,
    )
    _, foreign_reader = _read_service(foreign_config)

    pair_reader = RecommendationPortfolioFullPeriodPairReadServiceV1(service, foreign_reader)
    calendar_path, calendar_sha256, protected_roots = calendar
    with pytest.raises(FullPeriodPairReadErrorV1):
        pair_reader.read(
            left_saved.run_id,
            right_saved.run_id,
            calendar_path=calendar_path,
            expected_calendar_sha256=calendar_sha256,
        market="twse",
            protected_roots=protected_roots,
        )


@pytest.mark.parametrize(
    ("right_parent_id", "right_strategy_id", "right_strategy_version", "reason"),
    [
        ("pair-parent-left", "strategy-right", "fixture-v2", "same_portfolio_parent"),
        ("pair-parent-right", "strategy-left", "fixture-v1", "same_strategy_version"),
    ],
)
def test_full_pair_blocks_same_parent_or_strategy_version(
    tmp_path: Path,
    right_parent_id: str,
    right_strategy_id: str,
    right_strategy_version: str,
    reason: str,
) -> None:
    _, service, reader, calendar, left_saved, right_saved, _, _ = _saved_pair(
        tmp_path,
        right_parent_id=right_parent_id,
        right_strategy_id=right_strategy_id,
        right_strategy_version=right_strategy_version,
    )

    result = _pair_read(service, reader, left_saved.run_id, right_saved.run_id, calendar)

    assert result.coverage_complete is True
    assert result.status == "blocked"
    assert reason in result.reasons
    assert result.performance_eligible is False


def test_full_pair_preserves_legacy_v1_parent_and_blocks_same_parent(tmp_path: Path) -> None:
    _, service, reader, calendar, left_saved, right_saved, _, _ = _saved_pair(
        tmp_path,
        left_legacy_v1=True,
        right_parent_id="pair-parent-left",
    )

    result = _pair_read(service, reader, left_saved.run_id, right_saved.run_id, calendar)

    assert result.left.parent_id == "pair-parent-left"
    assert result.right.parent_id == "pair-parent-left"
    assert result.left.capture is None
    assert result.left.precision is None
    assert result.status == "blocked"
    assert "same_portfolio_parent" in result.reasons
    assert "left_precision_capture_missing" in result.reasons
    assert result.performance_eligible is False


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"right_stock_code": "6488"}, "stock_code_mismatch"),
        (
            {
                "right_start_date": "2026-01-05",
                "right_end_date": "2026-01-06",
                "right_dates": ("2026-01-05", "2026-01-06"),
            },
            "requested_period_mismatch",
        ),
    ],
)
def test_full_pair_blocks_different_stock_or_requested_period(
    tmp_path: Path,
    overrides: dict[str, object],
    reason: str,
) -> None:
    _, service, reader, calendar, left_saved, right_saved, _, _ = _saved_pair(tmp_path, **overrides)

    result = _pair_read(service, reader, left_saved.run_id, right_saved.run_id, calendar)

    assert result.status == "blocked"
    assert reason in result.reasons
    assert result.performance_eligible is False


@pytest.mark.parametrize(
    ("left_cancelled", "left_legacy_v1", "reason"),
    [
        (True, False, "left_capture_cancelled"),
        (False, True, "left_precision_capture_missing"),
    ],
)
def test_full_pair_blocks_cancelled_or_legacy_run_without_precision_capture(
    tmp_path: Path,
    left_cancelled: bool,
    left_legacy_v1: bool,
    reason: str,
) -> None:
    _, service, reader, calendar, left_saved, right_saved, _, _ = _saved_pair(
        tmp_path,
        left_cancelled=left_cancelled,
        left_legacy_v1=left_legacy_v1,
    )

    result = _pair_read(service, reader, left_saved.run_id, right_saved.run_id, calendar)

    assert result.status == "blocked"
    assert reason in result.reasons
    assert result.performance_eligible is False


@pytest.mark.parametrize("change_during_read", [False, True])
def test_full_pair_rejects_registry_metadata_changed_after_save(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    change_during_read: bool,
) -> None:
    _, service, reader, calendar, left_saved, right_saved, _, _ = _saved_pair(tmp_path)
    def change_registry_version() -> None:
        with sqlite3.connect(service.repository.db_path) as connection:
            connection.execute(
                "UPDATE research_runs SET strategy_version = ? WHERE run_id = ?",
                ("tampered-version", right_saved.run_id),
            )

    if change_during_read:
        original_read = reader.read

        def mutate_after_exact_read(registry_run_id: str, *args, **kwargs):
            result = original_read(registry_run_id, *args, **kwargs)
            if registry_run_id == right_saved.run_id:
                change_registry_version()
            return result

        monkeypatch.setattr(reader, "read", mutate_after_exact_read)
    else:
        change_registry_version()

    with pytest.raises(FullPeriodPairReadErrorV1):
        _pair_read(service, reader, left_saved.run_id, right_saved.run_id, calendar)
