from __future__ import annotations

from decimal import Decimal
from typing import Callable

import pandas as pd
import pytest

from app_module.recommendation_portfolio_backtest_service import (
    RecommendationPortfolioBacktestService,
)
from app_module.recommendation_portfolio_dtos import (
    RecommendationPortfolioBacktestResultDTO,
)
from backtest_module.broker_simulator import LEGACY_CLOSE_CONTRACT


_INITIAL_CAPITAL = Decimal("9007199254740993.01")
_DATES = ("2026-01-02", "2026-01-05", "2026-01-06")


def _history(
    stock_codes: tuple[str, ...] = ("2330",),
    dates: tuple[str, ...] = _DATES,
) -> pd.DataFrame:
    rows = []
    for date_index, session_date in enumerate(dates):
        for stock_index, stock_code in enumerate(stock_codes):
            close = Decimal("100.00") + Decimal(date_index + stock_index)
            rows.append(
                {
                    "日期": session_date,
                    "證券代號": stock_code,
                    "證券名稱": f"stock-{stock_code}",
                    "開盤價": close + Decimal("0.01"),
                    "收盤價": close,
                }
            )
    return pd.DataFrame(rows)


def _provider_for(stock_code: str) -> Callable[..., list[dict[str, object]]]:
    def provider(*_args: object) -> list[dict[str, object]]:
        return [
            {
                "stock_code": stock_code,
                "stock_name": f"stock-{stock_code}",
                "total_score": 90.0,
                "factor_scores": {"technical": 90.0},
            }
        ]

    return provider


def _run_next_open(
    history: pd.DataFrame,
    *,
    provider_stock_code: str = "2330",
    check_cancel: Callable[[], bool] | None = None,
) -> RecommendationPortfolioBacktestResultDTO:
    service = RecommendationPortfolioBacktestService(
        provider=_provider_for(provider_stock_code)
    )
    return service._run_next_open_portfolio(
        start_date=_DATES[0],
        end_date=_DATES[-1],
        profile_id="precision-capture-test",
        config={"regime": "Trend"},
        history=history,
        initial_capital=_INITIAL_CAPITAL,
        rebalance_frequency="once",
        top_n=1,
        allocation_method="equal_weight",
        holding_days=10,
        stop_loss_pct=None,
        take_profit_pct=None,
        max_participation_rate=None,
        fee_bps=Decimal("0"),
        slippage_bps=Decimal("0"),
        tax_bps=Decimal("0"),
        lot_size=1,
        check_cancel=check_cancel,
        include_benchmark=False,
    )


def test_next_open_captures_producer_decimals_before_float_and_keeps_v1_wire_shape() -> None:
    result = _run_next_open(_history(dates=_DATES[:2]))

    assert result.period_precision_capture_status == "captured_unqualified"
    assert result.period_precision_capture_reason is not None
    observations = result.period_precision_observations
    assert tuple(row.session_date for row in observations) == _DATES[:2]
    first = observations[0]
    assert first.cash_decimal == format(_INITIAL_CAPITAL, "f")
    assert first.position_value_decimal == "0.00"
    assert first.equity_decimal == format(_INITIAL_CAPITAL, "f")
    assert Decimal(first.cash_decimal) + Decimal(first.position_value_decimal) == Decimal(
        first.equity_decimal
    )
    assert all(
        Decimal(row.cash_decimal) + Decimal(row.position_value_decimal)
        == Decimal(row.equity_decimal)
        for row in observations
    )

    capture = result.period_precision_capture
    assert capture is not None
    assert capture.stock_code == "2330"
    assert capture.stock_scope_status == "exact_single_stock"
    assert capture.capture_status == "complete"
    assert capture.completion_status == "completed"
    assert capture.initial_capital_decimal == format(_INITIAL_CAPITAL, "f")
    assert capture.requested_start_date == _DATES[0]
    assert capture.requested_end_date == _DATES[-1]
    assert capture.observed_session_dates == _DATES[:2]
    assert capture.observations == observations
    assert capture.execution_contract_id == "next-session-open"
    assert capture.execution_contract_version == "v2"
    assert capture.cost_model_status == "unknown"
    assert capture.cost_model_id is None
    assert capture.cost_model_version is None
    assert not hasattr(capture, "expected_session_dates")
    assert not hasattr(capture, "currency_code")
    assert not hasattr(capture, "source_fingerprint_sha256")

    # 這個金額超過 float 可精確表示範圍；觀察列保留 producer Decimal，
    # 舊展示曲線仍維持原 numeric boundary。
    first_float_equity = Decimal(str(result.equity_curve.iloc[0]["equity"]))
    assert first_float_equity != Decimal(first.equity_decimal)
    assert list(result.equity_curve.columns) == [
        "date",
        "equity",
        "cash",
        "position_value",
    ]

    legacy_wire = result.to_dict()
    assert "period_precision_observations" not in legacy_wire
    assert "period_precision_capture_status" not in legacy_wire
    assert "period_precision_capture_reason" not in legacy_wire
    assert "period_precision_capture" not in legacy_wire
    restored = RecommendationPortfolioBacktestResultDTO.from_dict(legacy_wire)
    assert restored.period_precision_observations == ()
    assert restored.period_precision_capture is None


@pytest.mark.parametrize(
    ("stock_codes", "provider_stock_code", "expected_reason"),
    [
        (("2330", "2317"), "2330", "history_contains_multiple_stock_codes"),
        (("2330",), "2317", "producer_source_order_or_holding_stock_mismatch"),
    ],
)
def test_next_open_rejects_non_single_stock_capture(
    stock_codes: tuple[str, ...],
    provider_stock_code: str,
    expected_reason: str,
) -> None:
    result = _run_next_open(
        _history(stock_codes=stock_codes, dates=_DATES[:2]),
        provider_stock_code=provider_stock_code,
    )

    assert result.period_precision_capture_status == "not_single_stock"
    assert result.period_precision_capture_reason == expected_reason
    assert result.period_precision_observations == ()
    assert result.period_precision_capture is None


@pytest.mark.parametrize("source_stock_code", [2330, " 2330"])
def test_next_open_rejects_stock_codes_that_need_normalization(
    source_stock_code: object,
) -> None:
    history = _history(dates=_DATES[:2])
    history["證券代號"] = source_stock_code

    result = _run_next_open(history)

    assert result.period_precision_capture_status == "rejected"
    assert result.period_precision_capture_reason == "history_stock_code_not_exact_text"
    assert result.period_precision_observations == ()
    assert result.period_precision_capture is None


def test_next_open_rejects_unique_stock_code_outside_v2_identity_contract() -> None:
    history = _history(dates=_DATES[:2])
    history["證券代號"] = "bad code"

    result = _run_next_open(history, provider_stock_code="bad code")

    assert result.period_precision_capture_status == "rejected"
    assert (
        result.period_precision_capture_reason
        == "producer_decimal_row_rejected_by_v2_observation_contract"
    )
    assert result.period_precision_observations == ()
    assert result.period_precision_capture is None


def test_cancelled_next_open_keeps_only_actual_partial_observations() -> None:
    checks = 0

    def cancel_before_second_session() -> bool:
        nonlocal checks
        checks += 1
        return checks >= 2

    result = _run_next_open(
        _history(),
        check_cancel=cancel_before_second_session,
    )

    assert result.summary["status"] == "cancelled"
    assert result.period_precision_capture_status == "partial"
    assert result.period_precision_capture_reason == "cancelled_before_all_sessions"
    assert tuple(row.session_date for row in result.period_precision_observations) == (
        _DATES[0],
    )
    capture = result.period_precision_capture
    assert capture is not None
    assert capture.capture_status == "partial"
    assert capture.completion_status == "cancelled"
    assert capture.observed_session_dates == (_DATES[0],)
    assert capture.requested_start_date == _DATES[0]
    assert capture.requested_end_date == _DATES[-1]
    assert len(result.equity_curve) == 1


def test_unentered_loop_fallback_is_not_a_precision_observation() -> None:
    result = _run_next_open(
        _history(dates=_DATES[:2]),
        check_cancel=lambda: True,
    )

    assert result.summary["status"] == "cancelled"
    assert len(result.equity_curve) == 1
    assert result.period_precision_capture_status == "rejected"
    assert result.period_precision_capture_reason == "no_actual_observations"
    assert result.period_precision_observations == ()
    assert result.period_precision_capture is None


def test_legacy_close_marks_precision_capture_not_applicable() -> None:
    service = RecommendationPortfolioBacktestService(provider=_provider_for("2330"))
    result = service.run_portfolio_backtest(
        start_date=_DATES[0],
        end_date=_DATES[1],
        profile_id="precision-capture-test",
        recommendation_config={"regime": "Trend"},
        history=_history(dates=_DATES[:2]),
        initial_capital=1000000.0,
        rebalance_frequency="once",
        top_n=1,
        allocation_method="equal_weight",
        holding_days=2,
        execution_contract=LEGACY_CLOSE_CONTRACT,
    )

    assert result.period_precision_capture_status == "not_applicable"
    assert result.period_precision_capture_reason is None
    assert result.period_precision_observations == ()
    assert result.period_precision_capture is None
