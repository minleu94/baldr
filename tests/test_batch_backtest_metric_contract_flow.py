from __future__ import annotations

from concurrent.futures import Future
from types import SimpleNamespace

import pandas as pd
import pytest

from app_module.batch_backtest_service import BatchBacktestService
from app_module.dtos import BacktestReportDTO, ValidationStatus
from app_module.single_backtest_metrics_contract import (
    SINGLE_BACKTEST_METRICS_KEY,
    capture_single_backtest_metrics_contract,
)
from backtest_module.performance_metrics import PerformanceMetrics
from decision_module.strategies.contracts import StrategySpec


_METRIC_NAMES = (
    "total_return",
    "annual_return",
    "sharpe_ratio",
    "max_drawdown",
    "win_rate",
    "total_trades",
    "expectancy",
)


class _FakeBacktestService:
    def __init__(self, reports: dict[str, BacktestReportDTO]) -> None:
        self.reports = reports
        self.config = SimpleNamespace(reports=reports)

    def run_backtest(self, *, stock_code: str, **kwargs) -> BacktestReportDTO:
        del kwargs
        return self.reports[stock_code]


class _ImmediateExecutor:
    """在目前程序內完成 worker，讓測試經過並行 adapter 分支但不建子程序。"""

    def __init__(self, *args, **kwargs) -> None:
        del args, kwargs

    def submit(self, worker, config, stock_code, *args, **kwargs) -> Future:
        del args, kwargs
        future = Future()
        try:
            future.set_result(worker(config, stock_code))
        except BaseException as error:
            future.set_exception(error)
        return future

    def shutdown(self, *args, **kwargs) -> None:
        del args, kwargs


def _parallel_report_worker(config, stock_code: str) -> BacktestReportDTO:
    return config.reports[stock_code]


def _report(stock_code: str, *, metric_status: str) -> BacktestReportDTO:
    """建立固定合成數值，隔離驗 DTO adapter，不執行策略或績效公式。"""
    values = {
        "total_return": 0.0,
        "annual_return": 0.0,
        "sharpe_ratio": 0.0,
        "max_drawdown": 0.0,
        "win_rate": 0.0,
        "total_trades": 1,
        "expectancy": 0.0,
    }
    statuses = {name: "observed" for name in _METRIC_NAMES}
    for name in ("annual_return", "sharpe_ratio", "max_drawdown", "win_rate"):
        statuses[name] = metric_status
    metrics = PerformanceMetrics(
        **values,
        profit_factor=None,
        avg_win=0.0,
        avg_loss=0.0,
        largest_win=0.0,
        largest_loss=0.0,
        metric_status=statuses,
    )
    equity = pd.DataFrame(
        {"equity": [100_000.0, 100_000.0]},
        index=pd.to_datetime(["2026-01-05", "2026-01-06"]),
    )
    trades = pd.DataFrame(
        [{"進場日期": "2026-01-05", "出場日期": "2026-01-06", "報酬": 0, "報酬率%": 0, "股數": 1}]
    )
    contract = capture_single_backtest_metrics_contract(
        metrics, equity=equity, trades=trades, stock_code=stock_code
    )
    return BacktestReportDTO(
        **values,
        details={
            "stock_code": stock_code,
            "data_manifest": {SINGLE_BACKTEST_METRICS_KEY: contract},
        },
        validation_status=ValidationStatus.PASS,
    )


@pytest.mark.parametrize("parallel", [False, True], ids=["sequential", "parallel-adapter"])
def test_batch_metric_contract_flows_through_service_aggregates_and_leaderboard(
    monkeypatch: pytest.MonkeyPatch,
    parallel: bool,
) -> None:
    reports = {
        "2330": _report("2330", metric_status="unavailable"),
        "2317": _report("2317", metric_status="observed"),
    }
    backtest_service = _FakeBacktestService(reports)
    service = BatchBacktestService(
        backtest_service,
        worker_callable=_parallel_report_worker,
    )
    if parallel:
        import app_module.batch_backtest_service as batch_module

        monkeypatch.setattr(batch_module, "ProcessPoolExecutor", _ImmediateExecutor)

    result = service.run_batch_backtest(
        stock_codes=["2330", "2317"],
        start_date="2026-01-05",
        end_date="2026-01-06",
        strategy_spec=StrategySpec(
            strategy_id="baseline_score",
            strategy_version="1.0",
            default_params={},
            config={"params": {}},
        ),
        save_runs=False,
        parallel_threshold=1 if parallel else None,
    )

    by_code = {row.stock_code: row for row in result.stock_results}
    assert by_code["2330"].cagr is None
    assert by_code["2330"].sharpe is None
    assert by_code["2330"].mdd is None
    assert by_code["2330"].win_rate is None
    assert by_code["2317"].cagr == 0.0
    assert by_code["2317"].sharpe == 0.0
    assert by_code["2317"].mdd == 0.0
    assert by_code["2317"].win_rate == 0.0

    stats = result.overall_stats
    assert stats["cagr_sample_count"] == 1
    assert stats["cagr_median"] == 0.0
    assert stats["mdd_sample_count"] == 1
    assert stats["mdd_median"] == 0.0

    leaderboard = service.create_leaderboard_dataframe(result, sort_by="cagr_mdd")
    assert "Score" not in leaderboard.columns
    assert list(leaderboard["股票代號"]) == ["2317", "2330"]
    unavailable_row = leaderboard.set_index("股票代號").loc["2330"]
    assert pd.isna(unavailable_row["CAGR%"])
    assert pd.isna(unavailable_row["Sharpe"])
    assert pd.isna(unavailable_row["MDD%"])
    assert pd.isna(unavailable_row["WinRate%"])
