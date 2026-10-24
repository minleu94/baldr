import logging
from concurrent.futures import Future
from unittest.mock import MagicMock

import pandas as pd
import pytest

from app_module.exceptions import BacktestCancelledError
from app_module.optimizer_service import OptimizerService, ParamRange
from app_module.dtos import BacktestReportDTO
from app_module.single_backtest_metrics_contract import (
    SINGLE_BACKTEST_METRICS_KEY,
    capture_single_backtest_metrics_contract,
)
from backtest_module.performance_metrics import PerformanceMetrics
from decision_module.strategies.contracts import StrategySpec
from decimal import Decimal



def test_estimate_param_grid_size_counts_int_float_and_list_ranges():
    service = OptimizerService(MagicMock(), max_workers=2)
    param_ranges = {
        "short_window": ParamRange(
            name="short_window",
            type="int",
            values=[],
            min=5,
            max=15,
            step=5,
        ),
        "threshold": ParamRange(
            name="threshold",
            type="float",
            values=[],
            min=0.1,
            max=0.3,
            step=0.1,
        ),
        "mode": ParamRange(
            name="mode",
            type="list",
            values=["a", "b"],
        ),
    }

    assert service.estimate_param_grid_size(param_ranges) == 18


def test_estimate_param_grid_size_handles_empty_ranges_as_one_fixed_value():
    service = OptimizerService(MagicMock(), max_workers=2)

    assert service.estimate_param_grid_size({}) == 1


def test_generate_param_grid_matches_estimated_size():
    service = OptimizerService(MagicMock(), max_workers=2)
    param_ranges = {
        "fast": ParamRange("fast", "int", [], min=5, max=7, step=1),
        "slow": ParamRange("slow", "int", [], min=20, max=24, step=2),
    }

    grid = service.generate_param_grid(param_ranges)

    assert len(grid) == service.estimate_param_grid_size(param_ranges)


def test_grid_search_cancellation_does_not_submit_entire_grid_or_log_empty_errors(
    monkeypatch,
    caplog,
):
    backtest_service = MagicMock()
    backtest_service._load_stock_data.return_value = (
        pd.DataFrame({"日期": ["2026-01-02"], "收盤價": [100]}),
        "2026-01-02",
        "2026-01-02",
    )
    service = OptimizerService(backtest_service, max_workers=2)

    class RecordingExecutor:
        instances = []

        def __init__(self, max_workers):
            self.max_workers = max_workers
            self.submitted = 0
            self.futures = []
            self.shutdown_calls = []
            RecordingExecutor.instances.append(self)

        def submit(self, _fn, *_args, **_kwargs):
            self.submitted += 1
            future = Future()
            self.futures.append(future)
            return future

        def shutdown(self, wait=True, cancel_futures=False):
            self.shutdown_calls.append(
                {"wait": wait, "cancel_futures": cancel_futures}
            )

    monkeypatch.setattr(
        "app_module.optimizer_service.ThreadPoolExecutor",
        RecordingExecutor,
    )
    monkeypatch.setattr(
        "app_module.optimizer_service.wait",
        lambda pending, timeout, return_when: (set(pending), set()),
    )
    caplog.set_level(logging.ERROR)

    with pytest.raises(BacktestCancelledError):
        service.grid_search(
            stock_code="2330",
            start_date="2026-01-02",
            end_date="2026-01-02",
            strategy_id="baseline_score_threshold",
            base_params={},
            param_ranges={
                "param": ParamRange("param", "int", [], min=1, max=20, step=1),
            },
            check_cancel=lambda: True,
        )

    assert RecordingExecutor.instances
    assert RecordingExecutor.instances[0].submitted <= service.max_workers * 2
    assert "最佳化子任務" not in caplog.text
    assert "異常:" not in caplog.text


def _contract_report(*, sharpe_status="observed", annual_status="observed", mdd_status="observed", tamper=False):
    metrics = PerformanceMetrics(
        total_return=0,
        annual_return=0,
        sharpe_ratio=0,
        max_drawdown=0,
        win_rate=0,
        total_trades=1,
        expectancy=0,
        profit_factor=None,
        avg_win=0,
        avg_loss=0,
        largest_win=0,
        largest_loss=0,
        metric_status={
            "total_return": "observed",
            "annual_return": annual_status,
            "sharpe_ratio": sharpe_status,
            "max_drawdown": mdd_status,
            "win_rate": "observed",
            "total_trades": "observed",
            "expectancy": "observed",
        },
    )
    contract = capture_single_backtest_metrics_contract(
        metrics,
        equity=pd.DataFrame({"equity": [100, 100]}, index=pd.to_datetime(["2026-01-01", "2026-01-02"])),
        trades=pd.DataFrame([{"進場日期": "2026-01-01", "出場日期": "2026-01-02", "報酬": 0, "報酬率%": 0, "股數": 1}]),
        stock_code="2330",
    )
    if tamper:
        contract["metric_status"]["sharpe_ratio"] = "unavailable"
    return BacktestReportDTO(
        total_return=0,
        annual_return=0,
        sharpe_ratio=0,
        max_drawdown=0,
        win_rate=0,
        total_trades=1,
        expectancy=0,
        details={"stock_code": "2330", "data_manifest": {SINGLE_BACKTEST_METRICS_KEY: contract}},
    )


def _run_one_report(monkeypatch, report, *, objective="sharpe_ratio"):
    backtest_service = MagicMock()
    backtest_service._load_stock_data.return_value = (pd.DataFrame({"x": [1]}), "2026-01-01", "2026-01-02")
    backtest_service.run_backtest.return_value = report
    monkeypatch.setattr(
        "app_module.optimizer_service.registered_strategy_spec",
        lambda *_args, **_kwargs: StrategySpec("baseline_score_threshold", "1.0"),
    )
    return OptimizerService(backtest_service, max_workers=1).grid_search(
        stock_code="2330",
        start_date="2026-01-01",
        end_date="2026-01-02",
        strategy_id="baseline_score_threshold",
        base_params={},
        param_ranges={},
        objective=objective,
    )


def test_grid_search_contract_observed_zero_remains_ranked_and_visible(monkeypatch):
    results = _run_one_report(monkeypatch, _contract_report())

    assert len(results) == 1
    assert results[0].metrics["score"] == Decimal("0")
    assert results[0].metric_status["sharpe_ratio"] == "observed"
    summary = OptimizerService(MagicMock()).create_optimization_summary(results)
    assert summary.loc[0, "夏普比率"] == Decimal("0")
    assert summary.loc[0, "夏普比率狀態"] == "observed"


def test_grid_search_skips_explicitly_unavailable_objective(monkeypatch, caplog):
    results = _run_one_report(monkeypatch, _contract_report(sharpe_status="unavailable"))

    assert results == []
    assert "明示不可用" in caplog.text


def test_cagr_mdd_requires_both_saved_objective_metrics(monkeypatch, caplog):
    report = _contract_report(annual_status="observed", mdd_status="unavailable")

    assert _run_one_report(monkeypatch, report, objective="cagr_mdd") == []
    assert "明示不可用" in caplog.text


def test_grid_search_skips_tampered_metrics_contract(monkeypatch, caplog):
    results = _run_one_report(monkeypatch, _contract_report(tamper=True))

    assert results == []
    assert "契約SHA不符" in caplog.text


def test_grid_search_legacy_report_keeps_compatibility_but_marks_unknown(monkeypatch):
    report = _contract_report()
    report.details = {"stock_code": "2330"}
    results = _run_one_report(monkeypatch, report)

    assert len(results) == 1
    assert results[0].metric_status["objective"] == "legacy_unverified"
    summary = OptimizerService(MagicMock()).create_optimization_summary(results)
    assert pd.isna(summary.loc[0, "夏普比率"])
    assert summary.loc[0, "夏普比率狀態"] == "legacy_unverified"


def test_grid_search_does_not_rank_failed_report_fallback_zero(monkeypatch, caplog):
    report = _contract_report()
    report.details = {"error": "合成資料不足"}

    assert _run_one_report(monkeypatch, report) == []
    assert "原回測未完成" in caplog.text


def test_summary_keeps_missing_values_as_none_instead_of_zero():
    from app_module.optimizer_service import OptimizationResult

    result = OptimizationResult(
        params={},
        metrics={"total_return": None, "score": Decimal("0")},
        metric_status={"total_return": "unavailable", "objective": "observed"},
    )
    summary = OptimizerService(MagicMock()).create_optimization_summary([result])

    assert pd.isna(summary.loc[0, "總報酬率%"])
    assert summary.loc[0, "總報酬率狀態"] == "unavailable"
