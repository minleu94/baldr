"""回測原結果圖卡的缺值、真零、來源隔離及清除驗證。"""

from decimal import Decimal
from types import SimpleNamespace

from PySide6.QtWidgets import QApplication

from ui_qt.widgets.backtest_outcome_summary import BacktestOutcomeSummary


def test_original_ratio_zero_and_cost_assumptions_are_not_recomputed():
    app = QApplication.instance() or QApplication([])
    widget = BacktestOutcomeSummary()
    report = SimpleNamespace(total_return=Decimal("0.123456789"), max_drawdown=Decimal("-0.08"), total_trades=0,
                             details={"stock_code": "2330", "start_date": "2026-01-01", "end_date": "2026-02-01"})
    params = {"fee_bps": "14.25", "slippage_bps": 0}
    widget.present(report, params, "當次結果原始參數")
    widget.resize(1000, 150)
    widget.show()
    app.processEvents()
    assert widget.values["return"].text() == "12.35 %"
    assert widget.values["return"].toolTip() == "原比率：0.123456789"
    assert widget.values["drawdown"].text() == "-8.00 %"
    assert widget.values["trades"].text() == "0"
    assert "滑價 0 bps" in widget.values["cost"].text()
    assert "不代表實際扣款" in widget.values["cost"].toolTip()
    assert report.total_return == Decimal("0.123456789") and params == {"fee_bps": "14.25", "slippage_bps": 0}
    assert not widget.grab().isNull()
    widget.clear()
    assert widget.isHidden() and not widget.context.text()
    assert all(label.text() == "未提供" and not label.toolTip() for label in widget.values.values())
    widget.close()


def test_history_uses_only_its_original_values_and_keeps_invalid_values_unknown():
    app = QApplication.instance() or QApplication([])
    widget = BacktestOutcomeSummary()
    widget.present({"details": {"total_return": None, "max_drawdown": float("nan"), "total_trades": True,
                                "fee_bps": "bad", "run_id": 17}}, {}, "已保存 run 原始資料")
    assert all(widget.values[key].text() == "未提供" for key in ("return", "drawdown", "trades"))
    assert "滑價 未提供 bps" in widget.values["cost"].text()
    assert "run 17" in widget.context.text()
    widget.present(SimpleNamespace(details={"error": "來源不可讀"}), {}, "新結果")
    assert widget.isHidden() and not widget.context.text()
    widget.close()
    app.processEvents()


def test_versioned_unavailable_zero_is_not_presented_as_observed_return():
    import pandas as pd
    from app_module.single_backtest_metrics_contract import capture_single_backtest_metrics_contract, SINGLE_BACKTEST_METRICS_KEY, SINGLE_BACKTEST_METRIC_NAMES
    from backtest_module.performance_metrics import PerformanceAnalyzer
    app = QApplication.instance() or QApplication([])
    equity = pd.DataFrame({"equity": pd.Series(dtype="float64")}, index=pd.DatetimeIndex([]))
    trades = pd.DataFrame(columns=["進場日期", "出場日期", "報酬率%"])
    metrics = PerformanceAnalyzer().summarize([], equity, 100000.0)
    node = capture_single_backtest_metrics_contract(metrics, equity=equity, trades=trades, stock_code="2330")
    report = SimpleNamespace(**{key: getattr(metrics, key) for key in SINGLE_BACKTEST_METRIC_NAMES},
                             details={"stock_code": "2330", "data_manifest": {SINGLE_BACKTEST_METRICS_KEY: node}})
    widget = BacktestOutcomeSummary()
    widget.present(report, {}, "當次結果")
    assert widget.values["return"].text() == "未提供"
    assert widget.values["drawdown"].text() == "未提供"
    assert widget.values["trades"].text() == "0"
    node["contract_sha256"] = "0" * 64
    widget.present(report, {}, "不可核對")
    assert widget.values["trades"].text() == "未提供"
    assert "契約不可核對" in widget.context.text()
    widget.close()
    app.processEvents()


def test_equity_preview_uses_only_original_tail_and_keeps_gaps():
    import pandas as pd
    app = QApplication.instance() or QApplication([])
    source = pd.DataFrame({"equity": [str(value) for value in range(200)]}, index=pd.date_range("2026-01-01", periods=200))
    source.iloc[-2, 0] = "NaN"
    original = source.copy(deep=True)
    widget = BacktestOutcomeSummary()
    widget.present(SimpleNamespace(details={"equity_curve": source}), {}, "原結果")
    widget.resize(1100, 380)
    widget.show()
    app.processEvents()
    assert len(widget.curve.points) == 120
    assert widget.curve.points[0][1] == Decimal(80)
    assert widget.curve.points[-2][1] is None
    assert widget.curve.points[-1][1] == Decimal(199)
    assert "120／共 200 筆" in widget.curve_caption.text()
    assert not widget.curve.grab().isNull()
    pd.testing.assert_frame_equal(source, original)
    indexed = source.reset_index(names="date")
    widget.present(SimpleNamespace(details={"equity_curve": indexed}), {}, "保存原件")
    assert widget.curve.points[0][0] == str(source.index[80])[:10]
    assert widget.curve.points[-1][0] == str(source.index[-1])[:10]
    widget.clear()
    assert not widget.curve.points and widget.curve.isHidden()
    widget.close()
