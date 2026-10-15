from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
import sqlite3

import pytest

from app_module.backtest_contracts import (
    PROFIT_FACTOR_SEMANTICS,
    profit_factor_projection,
)
from app_module.batch_backtest_service import BatchBacktestService
from app_module.dtos import BacktestReportDTO, ValidationStatus
from app_module.backtest_repository import BacktestRunRepository
from app_module.optimizer_service import OptimizationResult, OptimizerService


_EXPECTED_KEYS = {"profit_factor", "profit_factor_status", "profit_factor_semantics"}
_KNOWN_UNDEFINED = (
    "no_closed_pairs",
    "unbounded_no_gross_loss",
    "undefined_zero_over_zero",
    "unavailable_nonfinite",
)


class _FakeBacktestService:
    def __init__(self, report: BacktestReportDTO):
        self.report = report

    def run_backtest(self, **kwargs):
        del kwargs
        return self.report


def _project_without_mutation(details: dict[str, object]) -> dict[str, object]:
    before = deepcopy(details)
    projection = profit_factor_projection(details)
    assert details == before
    assert set(projection) == _EXPECTED_KEYS
    return projection


def _report(details: dict[str, object]) -> BacktestReportDTO:
    return BacktestReportDTO(
        total_return=0.0,
        annual_return=0.0,
        sharpe_ratio=0.0,
        max_drawdown=0.0,
        win_rate=0.0,
        total_trades=0,
        expectancy=0.0,
        validation_status=ValidationStatus.PASS,
        details=details,
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    [(Decimal("0"), 0.0), (Decimal("1.25"), 1.25)],
    ids=["observed-zero-is-valid", "observed-ratio"],
)
def test_projection_accepts_only_versioned_observed_nonnegative_finite_values(value, expected):
    details = {
        "profit_factor": value,
        "profit_factor_status": "observed",
        "profit_factor_semantics": PROFIT_FACTOR_SEMANTICS,
    }

    projection = _project_without_mutation(details)

    assert PROFIT_FACTOR_SEMANTICS == "closed-pair-net-pnl-ratio.v1"
    assert projection == {
        "profit_factor": expected,
        "profit_factor_status": "observed",
        "profit_factor_semantics": PROFIT_FACTOR_SEMANTICS,
    }


@pytest.mark.parametrize("status", _KNOWN_UNDEFINED)
def test_projection_preserves_each_known_undefined_status_with_none(status):
    details = {
        "profit_factor": None,
        "profit_factor_status": status,
        "profit_factor_semantics": PROFIT_FACTOR_SEMANTICS,
    }

    projection = _project_without_mutation(details)

    assert projection == {
        "profit_factor": None,
        "profit_factor_status": status,
        "profit_factor_semantics": PROFIT_FACTOR_SEMANTICS,
    }


def test_projection_does_not_promote_an_unversioned_legacy_amount():
    details = {"profit_factor": 125000.0}

    projection = _project_without_mutation(details)

    assert projection == {
        "profit_factor": None,
        "profit_factor_status": "legacy_unversioned",
        "profit_factor_semantics": None,
    }


@pytest.mark.parametrize(
    "value",
    [None, float("nan"), -0.1, True],
    ids=["none-observed", "nan", "negative", "boolean"],
)
def test_projection_rejects_invalid_values_marked_observed(value):
    details = {
        "profit_factor": value,
        "profit_factor_status": "observed",
        "profit_factor_semantics": PROFIT_FACTOR_SEMANTICS,
    }

    projection = _project_without_mutation(details)

    assert projection == {
        "profit_factor": None,
        "profit_factor_status": "unavailable_nonfinite",
        "profit_factor_semantics": PROFIT_FACTOR_SEMANTICS,
    }


@pytest.mark.parametrize(
    "details",
    [
        {"profit_factor": 99.0, "profit_factor_status": "observed", "profit_factor_semantics": "old-dollar-value.v0"},
        {"profit_factor": 1.5, "profit_factor_semantics": PROFIT_FACTOR_SEMANTICS},
        {"profit_factor": 1.5, "profit_factor_status": "unknown-status", "profit_factor_semantics": PROFIT_FACTOR_SEMANTICS},
        {"profit_factor": 0.0, "profit_factor_status": "no_closed_pairs", "profit_factor_semantics": PROFIT_FACTOR_SEMANTICS},
    ],
    ids=["unknown-semantics", "missing-status", "unknown-status", "undefined-status-with-value"],
)
def test_projection_quarantines_unknown_or_contradictory_details(details):
    projection = _project_without_mutation(details)

    assert projection["profit_factor"] is None
    assert projection["profit_factor_status"] in {"legacy_unversioned", "unavailable_nonfinite"}


def test_batch_report_metrics_preserve_nullable_profit_factor_status_and_semantics():
    details = {
        "profit_factor": None,
        "profit_factor_status": "unbounded_no_gross_loss",
        "profit_factor_semantics": PROFIT_FACTOR_SEMANTICS,
    }
    before = deepcopy(details)
    report = _report(details)
    batch = BatchBacktestService(_FakeBacktestService(report))

    metrics = batch._report_metrics(report)

    assert metrics["profit_factor"] is None
    assert metrics["profit_factor_status"] == "unbounded_no_gross_loss"
    assert metrics["profit_factor_semantics"] == PROFIT_FACTOR_SEMANTICS
    assert details == before


def test_new_repository_save_uses_null_without_rewriting_unversioned_old_rows(tmp_path):
    class IsolatedConfig:
        def resolve_output_path(self, relative):
            return tmp_path / relative

    repository = BacktestRunRepository(IsolatedConfig())
    with sqlite3.connect(repository.db_path) as connection:
        connection.execute("INSERT INTO runs (run_id, run_name, profit_factor) VALUES ('old', 'old amount', 125000)")
        columns_before = connection.execute("PRAGMA table_info(runs)").fetchall()
        old_before = connection.execute("SELECT * FROM runs WHERE run_id='old'").fetchone()
    report = _report({"profit_factor": None, "profit_factor_status": "unbounded_no_gross_loss",
                      "profit_factor_semantics": PROFIT_FACTOR_SEMANTICS})
    repository.save_run(run_name="new", stock_code="2330", start_date="2026-01-02", end_date="2026-01-05",
                        strategy_id="baseline", strategy_params={}, capital=10000, fee_bps=0, slippage_bps=0,
                        stop_loss_pct=None, take_profit_pct=None, report=report, run_id="new")
    with sqlite3.connect(repository.db_path) as connection:
        assert connection.execute("SELECT profit_factor FROM runs WHERE run_id='new'").fetchone() == (None,)
        assert connection.execute("SELECT * FROM runs WHERE run_id='old'").fetchone() == old_before
        assert connection.execute("PRAGMA table_info(runs)").fetchall() == columns_before
    assert repository.load_run("new").profit_factor is None


def test_optimizer_summary_does_not_upgrade_legacy_amount_or_fill_undefined_zero():
    service = OptimizerService(object(), max_workers=1)
    result = service.create_optimization_summary([
        OptimizationResult(params={}, metrics={"profit_factor": 125000}),
        OptimizationResult(params={}, metrics={"profit_factor": None,
            "profit_factor_status": "unbounded_no_gross_loss", "profit_factor_semantics": PROFIT_FACTOR_SEMANTICS}),
        OptimizationResult(params={}, metrics={"profit_factor": 0,
            "profit_factor_status": "observed", "profit_factor_semantics": PROFIT_FACTOR_SEMANTICS}),
    ])
    assert result["獲利因子"].isna().tolist() == [True, True, False]
    assert result["獲利因子狀態"].tolist() == ["legacy_unversioned", "unbounded_no_gross_loss", "observed"]
    assert result.iloc[2]["獲利因子"] == 0
