"""Declared metrics 的唯讀 UI 對照；不呼叫 Registry 或回測 reader。"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import replace
from decimal import Decimal
from typing import cast

import pandas as pd
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel

from app_module.single_backtest_metrics_contract import (
    SINGLE_BACKTEST_METRICS_KEY,
    capture_single_backtest_metrics_contract,
)
from app_module.strategy_historical_performance_read_service import (
    HistoricalComparabilityState,
    HistoricalMetricsState,
    HistoricalPerformanceSummary,
)
from backtest_module.performance_metrics import PerformanceMetrics
from test_historical_performance_widget import _card, _entry
from ui_qt.widgets.historical_performance_widget import HistoricalPerformanceWidget


_DECLARED_REASON = "saved_original_analytics_not_performance_qualification"
_METRIC_NAMES = (
    "total_return",
    "annual_return",
    "sharpe_ratio",
    "max_drawdown",
    "win_rate",
    "total_trades",
    "expectancy",
)


@pytest.fixture(scope="module")
def app() -> QApplication:
    instance = cast(QApplication | None, QApplication.instance())
    if instance is None:
        instance = QApplication([])
    return instance


def _metrics(*, completed_pairs: int) -> PerformanceMetrics:
    """建立與原 producer 同型的有限 fixture，不執行指標計算。"""
    status = {name: "observed" for name in _METRIC_NAMES}
    if completed_pairs == 0:
        status["win_rate"] = "unavailable"
        status["expectancy"] = "unavailable"
    return PerformanceMetrics(
        total_return=0.125,
        annual_return=0.2,
        sharpe_ratio=1.5,
        max_drawdown=-0.1,
        win_rate=0.5 if completed_pairs else 0.0,
        total_trades=completed_pairs,
        expectancy=0.025 if completed_pairs else 0.0,
        profit_factor=1.2,
        avg_win=1.0,
        avg_loss=-1.0,
        largest_win=1.0,
        largest_loss=-1.0,
        metric_status=status,
    )


def _declared_fixture(completed_pairs: int):
    entry = _entry()
    metrics = _metrics(completed_pairs=completed_pairs)
    equity = pd.DataFrame(
        {"equity": [100.0, 112.5]},
        index=pd.to_datetime(["2026-01-02", "2026-01-05"]),
    )
    trade_columns = ("進場日期", "出場日期", "報酬", "報酬率%", "股數")
    trades = pd.DataFrame(
        [
            {
                "進場日期": "2026-01-02",
                "出場日期": "2026-01-05",
                "報酬": 12.5,
                "報酬率%": 0.125,
                "股數": 1,
            }
        ][:completed_pairs],
        columns=trade_columns,
    )
    contract = capture_single_backtest_metrics_contract(
        metrics,
        equity=equity,
        trades=trades,
        stock_code=entry.stock_code,
    )
    raw_metrics = {name: getattr(metrics, name) for name in _METRIC_NAMES}
    metadata = json.loads(entry.metadata_json)
    metadata["metrics"] = raw_metrics
    metadata["data_manifest"][SINGLE_BACKTEST_METRICS_KEY] = contract
    metadata_json = json.dumps(metadata, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    entry = replace(
        entry,
        metadata_json=metadata_json,
        metadata_sha256=hashlib.sha256(metadata_json.encode("utf-8")).hexdigest(),
    )
    if completed_pairs:
        average = Decimal("0.025")
        win_rate = Decimal("0.5")
    else:
        average = None
        win_rate = None
    summary = HistoricalPerformanceSummary(
        stock_count=1,
        signal_count=None,
        completed_trades=completed_pairs,
        average_trade_return=average,
        total_return=Decimal("0.125"),
        annual_return=Decimal("0.2"),
        cagr=Decimal("0.2"),
        max_drawdown=Decimal("-0.1"),
        win_rate=win_rate,
        sharpe_ratio=Decimal("1.5"),
        expectancy=average,
        profit_factor=None,
    )
    base_card = _card(entry)
    assert base_card.details is not None
    trade_preview = (
        ("2026-01-02", "2026-01-05", "12.5", "0.125", "1"),
    )[:completed_pairs]
    trades_table = replace(
        base_card.details.trades,
        row_count=completed_pairs,
        column_count=len(trade_columns),
        columns=trade_columns,
        preview_rows=trade_preview,
        rows_truncated=False,
    )
    card = replace(
        base_card,
        metrics_state=HistoricalMetricsState.DECLARED,
        metrics_reason=_DECLARED_REASON,
        comparability_state=HistoricalComparabilityState.NOT_ASSESSED,
        summary=summary,
        details=replace(base_card.details, trades=trades_table),
    )
    return entry, card


def _rendered_text(widget: HistoricalPerformanceWidget) -> str:
    return "\n".join(label.text() for label in widget.findChildren(QLabel))


def test_declared_summary_is_rechecked_and_shown_with_saved_units(app: QApplication):
    entry, card = _declared_fixture(completed_pairs=1)
    widget = HistoricalPerformanceWidget()
    generation = widget.begin_selection(entry)

    assert widget.present_card(generation, entry, card) is True
    rendered = _rendered_text(widget)
    assert "股票數（stocks）：1 檔" in rendered
    assert "訊號數（signals）：未提供" in rendered
    assert "已完成交易配對（completed pairs）：1 對" in rendered
    assert "總報酬：0.125 ratio（轉為 % 數值需乘 100）" in rendered
    assert "原指標計算期間（manifest，不同於回測請求期間）：2026-01-02 至 2026-01-05" in rendered
    assert "回測請求開始日期：2026-01-01" in rendered
    assert "Sharpe：1.5（Sharpe ratio；非百分比）" in rendered
    assert "不是 Decimal 精度核心、合格績效或排名，不重算" in rendered
    assert "資格：unknown" in rendered
    assert "可比較性：not_assessed" in rendered
    assert all(label.textFormat() == Qt.TextFormat.PlainText for label in widget.findChildren(QLabel))


def test_zero_completed_pairs_does_not_show_win_or_average_as_zero(app: QApplication):
    entry, card = _declared_fixture(completed_pairs=0)
    widget = HistoricalPerformanceWidget()
    generation = widget.begin_selection(entry)

    assert widget.present_card(generation, entry, card) is True
    rendered = _rendered_text(widget)
    assert "已完成交易配對（completed pairs）：0 對" in rendered
    assert "平均單筆報酬：未提供（尚無已完成交易）" in rendered
    assert "勝率：未提供（尚無已完成交易）" in rendered
    assert "期望值：未提供（尚無已完成交易）" in rendered
    assert "平均單筆報酬：0" not in rendered
    assert "勝率：0" not in rendered


def test_declared_card_cannot_supply_a_summary_different_from_saved_metrics(app: QApplication):
    entry, card = _declared_fixture(completed_pairs=1)
    changed_summary = replace(card.summary, total_return=Decimal("0.126"))
    widget = HistoricalPerformanceWidget()
    generation = widget.begin_selection(entry)

    assert widget.present_card(generation, entry, replace(card, summary=changed_summary)) is False
    assert widget._identity_label.text() == ""
    assert widget._metrics_label.text() == ""
    assert "historical_summary_not_bound_to_saved_metrics" in widget._status_label.text()


def test_legacy_entry_without_schema_keeps_unversioned_unknown_display(app: QApplication):
    entry = _entry()
    widget = HistoricalPerformanceWidget()
    generation = widget.begin_selection(entry)

    assert widget.present_card(generation, entry, _card(entry)) is True
    rendered = _rendered_text(widget)
    assert "指標狀態：metrics_unversioned" in rendered
    assert "績效指標未提供：原保存 metrics 沒有可驗證的共同 schema。" in rendered
    assert "總報酬：未提供" in rendered
    assert "指標原因：historical_metrics_schema_unversioned" in rendered
