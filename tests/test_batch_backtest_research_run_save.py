from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

import pandas as pd

from app_module.batch_backtest_service import BatchBacktestService, BatchBacktestResultDTO, StockBacktestResult
from app_module.dtos import BacktestReportDTO, ValidationStatus
from decision_module.strategies.contracts import StrategySpec
from decision_module.factors.factor_adapters import build_technical_total_score_factor


class _FakeBacktestService:
    def __init__(self, report: BacktestReportDTO):
        self.report = report

    def run_backtest(self, **kwargs):
        del kwargs
        return self.report


class _FakeRunRepository:
    def save_run(self, **kwargs):
        del kwargs
        return "legacy-run-2330"


def _strategy_spec() -> StrategySpec:
    return StrategySpec(
        strategy_id="baseline_score",
        strategy_version="1.0",
        default_params={"buy_score": 60, "sell_score": 40},
        config={"params": {"threshold_mode": "fixed", "buy_score": 60, "sell_score": 40}},
    )


def _report_with_factor_records(factor_record) -> BacktestReportDTO:
    return BacktestReportDTO(
        total_return=0.12,
        annual_return=0.10,
        sharpe_ratio=1.1,
        max_drawdown=-0.05,
        win_rate=0.5,
        total_trades=1,
        expectancy=1200.0,
        validation_status=ValidationStatus.PASS,
        details={
            "profit_factor": 1.5,
            "equity_curve": pd.DataFrame(
                {"date": ["2026-01-05", "2026-01-07"], "portfolio_value": [1000, 1120]}
            ),
            "trade_list": pd.DataFrame(
                {"stock_code": ["2330"], "action": ["buy"], "price": [100]}
            ),
            "factor_records": [factor_record],
            "factor_decision_date": date(2026, 1, 7),
            "strategy_version": "1.0",
            "parameter_contract_version": "score.v1",
            "data_as_of_date": "2026-01-07",
            "data_version": "sha256:test",
        },
    )


def test_batch_save_forwards_factor_records_to_research_run_service():
    factor_record = build_technical_total_score_factor(
        stock_code="2330",
        as_of_date=date(2026, 1, 7),
        available_date=date(2026, 1, 7),
        total_score=Decimal("82.35"),
    )
    report = _report_with_factor_records(factor_record)
    research_run_service = MagicMock()
    batch_service = BatchBacktestService(
        _FakeBacktestService(report),
        _FakeRunRepository(),
        research_run_service=research_run_service,
    )

    result = batch_service.run_batch_backtest(
        stock_codes=["2330"],
        start_date="2026-01-05",
        end_date="2026-01-07",
        strategy_spec=_strategy_spec(),
        save_runs=True,
        parallel_threshold=5,
        batch_name="Batch Factor Test",
    )

    assert result.stock_results[0].run_id == "legacy-run-2330"
    metadata, equity, trades = research_run_service.save_run.call_args.args
    kwargs = research_run_service.save_run.call_args.kwargs
    assert metadata.run_id == "batch-backtest:legacy-run-2330"
    assert metadata.run_type == "batch_backtest_stock"
    assert metadata.original_input["legacy_run_id"] == "legacy-run-2330"
    assert metadata.original_input["batch_id"] == result.batch_id
    assert metadata.universe == ["2330"]
    assert list(equity["portfolio_value"]) == [1000, 1120]
    assert list(trades["stock_code"]) == ["2330"]
    assert kwargs["factor_records"] == [factor_record]
    assert kwargs["factor_decision_date"] == date(2026, 1, 7)


def test_fixed_basket_save_marks_run_type_and_forwards_factor_records():
    factor_record = build_technical_total_score_factor(
        stock_code="2330",
        as_of_date=date(2026, 1, 7),
        available_date=date(2026, 1, 7),
        total_score=Decimal("82.35"),
    )
    report = _report_with_factor_records(factor_record)
    research_run_service = MagicMock()
    batch_service = BatchBacktestService(
        _FakeBacktestService(report),
        _FakeRunRepository(),
        research_run_service=research_run_service,
    )

    batch_service.run_batch_backtest(
        stock_codes=["2330"],
        start_date="2026-01-05",
        end_date="2026-01-07",
        strategy_spec=_strategy_spec(),
        save_runs=True,
        parallel_threshold=5,
        batch_name="Fixed Basket Factor Test",
        research_mode="fixed_basket",
    )

    metadata, equity, trades = research_run_service.save_run.call_args.args
    kwargs = research_run_service.save_run.call_args.kwargs
    assert metadata.run_type == "fixed_basket_stock"
    assert metadata.original_input["research_mode"] == "fixed_basket"
    assert metadata.original_input["batch_name"] == "Fixed Basket Factor Test"
    assert metadata.universe == ["2330"]
    assert list(equity["portfolio_value"]) == [1000, 1120]
    assert list(trades["stock_code"]) == ["2330"]
    assert kwargs["factor_records"] == [factor_record]
    assert kwargs["factor_decision_date"] == date(2026, 1, 7)


def test_batch_leaderboard_mdd_sort_prefers_smaller_absolute_drawdown():
    service = BatchBacktestService(_FakeBacktestService(_report_with_factor_records(None)))
    result = BatchBacktestResultDTO(
        batch_id="batch-test",
        batch_name="MDD sort",
        stock_results=[
            StockBacktestResult(
                stock_code="2330",
                run_id=None,
                success=True,
                cagr=0.10,
                sharpe=1.0,
                mdd=-0.50,
                total_trades=20,
            ),
            StockBacktestResult(
                stock_code="2317",
                run_id=None,
                success=True,
                cagr=0.08,
                sharpe=1.0,
                mdd=-0.10,
                total_trades=20,
            ),
        ],
        overall_stats={},
        created_at="2026-06-14T12:00:00",
    )

    frame = service.create_leaderboard_dataframe(result, sort_by="mdd")

    assert list(frame["股票代號"]) == ["2317", "2330"]


def test_batch_overall_stats_expose_valid_coverage_and_explicit_no_trade_count():
    service = BatchBacktestService(_FakeBacktestService(_report_with_factor_records(None)))
    stats = service._calculate_overall_stats(
        [
            StockBacktestResult(
                stock_code="2330",
                run_id=None,
                success=True,
                cagr=0.10,
                mdd=-0.20,
                total_trades=12,
            ),
            StockBacktestResult(
                stock_code="2317",
                run_id=None,
                success=False,
                error_reason="無交易信號",
                total_trades=0,
            ),
            StockBacktestResult(
                stock_code="2454",
                run_id=None,
                success=False,
                error_reason="資料不足",
                total_trades=0,
            ),
        ]
    )

    assert stats["total_stocks"] == 3
    assert stats["successful_stocks"] == 1
    assert stats["failed_stocks"] == 2
    assert stats["no_trade_stocks"] == 1
    assert stats["coverage_bp"] == 3333
    assert stats["cagr_sample_count"] == 1
    assert stats["mdd_sample_count"] == 1
