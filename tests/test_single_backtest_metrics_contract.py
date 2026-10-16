from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from decimal import Decimal

import pandas as pd
import pytest

from app_module.single_backtest_metrics_contract import (
    SINGLE_BACKTEST_METRICS_KEY,
    capture_single_backtest_metrics_contract,
    decode_single_backtest_metrics_contract,
)
from backtest_module.performance_metrics import PerformanceAnalyzer, PerformanceMetrics


_METRIC_NAMES = (
    "total_return", "annual_return", "sharpe_ratio", "max_drawdown", "win_rate", "total_trades", "expectancy",
)


def _flat_case():
    equity = pd.DataFrame(
        {"equity": [100000.0, 100000.0]},
        index=pd.DatetimeIndex(["2026-01-01", "2026-01-02"]),
    )
    trades = pd.DataFrame(columns=["進場日期", "出場日期", "報酬率%"])
    metrics = PerformanceAnalyzer().summarize([], equity, 100000.0)
    node = capture_single_backtest_metrics_contract(metrics, equity=equity, trades=trades, stock_code="2330")
    return metrics, equity, trades, node


def _metric_values(metrics: PerformanceMetrics) -> dict[str, object]:
    return {name: getattr(metrics, name) for name in _METRIC_NAMES}


def _decode(node, metrics: dict[str, object], *, run_type: str = "single_backtest", universe=None):
    return decode_single_backtest_metrics_contract(
        {SINGLE_BACKTEST_METRICS_KEY: node},
        metrics,
        run_type=run_type,
        universe=["2330"] if universe is None else universe,
    )


def test_analyzer_zero_trade_metrics_keep_observation_status_and_saved_numeric_boundary():
    metrics, equity, trades, node = _flat_case()
    saved_original = _metric_values(metrics)

    assert type(metrics) is PerformanceMetrics
    assert len(equity) == node["equity_rows"] == 2
    assert len(trades) == node["closed_pairs"] == metrics.total_trades == 0
    assert metrics.metric_status["total_trades"] == "observed"
    assert metrics.metric_status["win_rate"] == "unavailable"
    assert metrics.metric_status["expectancy"] == "unavailable"
    assert metrics.metric_status["sharpe_ratio"] == "unavailable"
    assert metrics.win_rate == 0.0
    assert metrics.expectancy == 0.0
    assert metrics.sharpe_ratio == 0.0
    decoded = _decode(node, saved_original)
    assert decoded is not None
    assert decoded["completed_trades"] == 0
    assert decoded["win_rate"] is None
    assert decoded["expectancy"] is None
    assert decoded["average_trade_return"] is None
    assert decoded["sharpe_ratio"] is None
    assert decoded["total_return"] == Decimal(str(saved_original["total_return"]))


@pytest.mark.parametrize("curve_kind", ["missing", "one_day"], ids=["missing-curve", "no-period"])
def test_fallback_zero_from_missing_curve_or_period_stays_unavailable(curve_kind):
    if curve_kind == "missing":
        equity = pd.DataFrame({"equity": pd.Series(dtype="float64")}, index=pd.DatetimeIndex([]))
    else:
        equity = pd.DataFrame({"equity": [100000.0]}, index=pd.DatetimeIndex(["2026-01-01"]))
    trades = pd.DataFrame(columns=["進場日期", "出場日期", "報酬率%"])
    metrics = PerformanceAnalyzer().summarize([], equity, 100000.0)
    node = capture_single_backtest_metrics_contract(metrics, equity=equity, trades=trades, stock_code="2330")
    decoded = _decode(node, _metric_values(metrics))

    assert decoded is not None
    assert node["equity_rows"] == len(equity)
    assert node["closed_pairs"] == 0
    assert decoded["completed_trades"] == 0
    if curve_kind == "missing":
        assert node["period_start"] == node["period_end"] == ""
        for key in ("total_return", "annual_return", "sharpe_ratio", "max_drawdown"):
            assert node["metric_status"][key] == "unavailable"
            assert decoded[key] is None
    else:
        assert node["period_start"] == node["period_end"] == "2026-01-01"
        assert node["metric_status"]["annual_return"] == "unavailable"
        assert decoded["annual_return"] is None


def test_capture_rejects_completed_pair_count_that_does_not_match_the_trade_table():
    metrics, equity, trades, _ = _flat_case()

    with pytest.raises(ValueError, match="筆數與原表不符"):
        capture_single_backtest_metrics_contract(
            replace(metrics, total_trades=1), equity=equity, trades=trades, stock_code="2330"
        )


def test_decoder_rejects_saved_pair_count_that_does_not_match_numeric_metrics():
    metrics, _, _, node = _flat_case()
    changed = deepcopy(node)
    changed["closed_pairs"] = 1

    with pytest.raises(ValueError, match="版本／原值／單股身份不符"):
        _decode(changed, _metric_values(metrics))


@pytest.mark.parametrize(("bad_value", "reason"), [(float("nan"), "保存指標含非有限數值"), (True, "保存指標不是有限數值")], ids=["nonfinite", "boolean"])
def test_capture_rejects_nonfinite_and_boolean_metric_values(bad_value, reason):
    metrics, equity, trades, _ = _flat_case()

    with pytest.raises(ValueError, match=reason):
        capture_single_backtest_metrics_contract(
            replace(metrics, total_return=bad_value), equity=equity, trades=trades, stock_code="2330"
        )


@pytest.mark.parametrize(("bad_value", "reason"), [(float("inf"), "保存指標含非有限數值"), (False, "保存指標不是有限數值")], ids=["nonfinite", "boolean"])
def test_decoder_rejects_nonfinite_and_boolean_metric_values(bad_value, reason):
    metrics, _, _, node = _flat_case()
    values = _metric_values(metrics)
    values["total_return"] = bad_value

    with pytest.raises(ValueError, match=reason):
        _decode(node, values)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("producer", "other.producer"),
        ("schema_version", "single-backtest-performance.v2"),
        ("metrics_sha256", "0" * 64),
        ("contract_sha256", "0" * 64),
    ],
    ids=["wrong-source", "wrong-schema", "wrong-metrics-hash", "wrong-contract-hash"],
)
def test_decoder_rejects_wrong_source_schema_or_metrics_hash(field, value):
    metrics, _, _, node = _flat_case()
    changed = deepcopy(node)
    changed[field] = value

    with pytest.raises(ValueError):
        _decode(changed, _metric_values(metrics))


@pytest.mark.parametrize(
    ("run_type", "universe"),
    [("portfolio_backtest", ["2330"]), ("single_backtest", ["2317"])],
    ids=["cross-run-kind", "wrong-universe"],
)
def test_decoder_rejects_cross_run_kind_or_stock_universe(run_type, universe):
    metrics, _, _, node = _flat_case()

    with pytest.raises(ValueError):
        _decode(node, _metric_values(metrics), run_type=run_type, universe=universe)


@pytest.mark.parametrize("run_type", ["batch_backtest_stock", "fixed_basket_stock"])
def test_per_stock_batch_run_preserves_exact_source_metrics_with_separate_profit_factor_projection(run_type):
    metrics, _, _, node = _flat_case()
    saved = {
        **_metric_values(metrics),
        "profit_factor": None,
        "profit_factor_status": "no_closed_pairs",
        "profit_factor_semantics": "closed-pair-net-pnl-ratio.v1",
    }

    decoded = _decode(node, saved, run_type=run_type)

    assert decoded is not None
    assert decoded["completed_trades"] == 0
    assert decoded["profit_factor"] is None
    changed = dict(saved, total_return=Decimal("999"))
    with pytest.raises(ValueError, match="版本／原值／單股身份不符"):
        _decode(node, changed, run_type=run_type)


def test_per_stock_batch_run_rejects_unknown_metric_projection_field():
    metrics, _, _, node = _flat_case()
    saved = {**_metric_values(metrics), "unsupported_metric": 123}
    with pytest.raises(ValueError, match="保存指標欄位不符"):
        _decode(node, saved, run_type="batch_backtest_stock")


def test_decoder_rejects_status_tampering_that_promotes_a_fallback_zero():
    empty_curve = pd.DataFrame({"equity": pd.Series(dtype="float64")}, index=pd.DatetimeIndex([]))
    trades = pd.DataFrame(columns=["進場日期", "出場日期", "報酬率%"])
    metrics = PerformanceAnalyzer().summarize([], empty_curve, 100000.0)
    node = capture_single_backtest_metrics_contract(metrics, equity=empty_curve, trades=trades, stock_code="2330")
    changed = deepcopy(node)
    changed["metric_status"]["total_return"] = "observed"

    with pytest.raises(ValueError):
        _decode(changed, _metric_values(metrics))


def test_legacy_manifest_without_contract_schema_stays_unavailable():
    metrics, _, _, _ = _flat_case()

    assert decode_single_backtest_metrics_contract(
        {}, _metric_values(metrics), run_type="single_backtest", universe=["2330"]
    ) is None
