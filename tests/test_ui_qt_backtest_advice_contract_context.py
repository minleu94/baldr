"""BacktestView 對 Workbench Advice 缺欄上下文的唯讀呈現測試。"""

from __future__ import annotations

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from unittest.mock import MagicMock

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDoubleSpinBox,
    QLineEdit,
    QSpinBox,
)

from ui_qt.views.advice_contract_backtest_context import (
    AdviceContractBacktestNavigation,
)
from ui_qt.views.backtest_view import BacktestView


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _config_values(view: BacktestView) -> tuple[tuple[str, object], ...]:
    values: list[tuple[str, object]] = []
    for widget_type in (QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit, QCheckBox):
        for widget in view.findChildren(widget_type):
            if isinstance(widget, QLineEdit):
                value: object = widget.text()
            elif isinstance(widget, QComboBox):
                value = (widget.currentIndex(), widget.currentData())
            elif isinstance(widget, QDateEdit):
                value = widget.date().toString("yyyy-MM-dd")
            elif isinstance(widget, QCheckBox):
                value = widget.isChecked()
            else:
                value = widget.value()
            values.append((widget.objectName(), value))
    return tuple(values)


def test_advice_navigation_context_only_renders_read_only_banner() -> None:
    _app()
    backtest_service = MagicMock()
    view = BacktestView(backtest_service=backtest_service, config=None)
    backtest_service.reset_mock()
    context = AdviceContractBacktestNavigation(
        candidate_result_id="daily-result-001",
        source_snapshot_id="snapshot-001",
        stock_code="2330",
        decision_date="2026-10-26",
        data_as_of_date="2026-10-23",
        strategy_version="strategy-v7",
        missing_author_fields=("entry_thesis", "review_cadence"),
    )
    original_config = _config_values(view)
    original_config_panel = view.config_panel
    original_result_panel = view.result_panel
    original_report = view.current_report

    view.set_advice_contract_navigation_context(context)

    banner = view.advice_contract_navigation_context_label
    assert not banner.isHidden()
    assert banner.textFormat() == Qt.TextFormat.PlainText
    assert "每日候選：2330｜策略版本：strategy-v7" in banner.text()
    assert "決策日：2026-10-26｜資料日：2026-10-23" in banner.text()
    assert "result_id：daily-result-001｜snapshot_id：snapshot-001" in banner.text()
    assert "待作者填寫：entry_thesis、review_cadence" in banner.text()
    assert "不會載入回測設定、執行回測或升版" in banner.text()
    assert view.config_panel is original_config_panel
    assert view.result_panel is original_result_panel
    assert view.current_report is original_report
    assert _config_values(view) == original_config
    assert view.worker is None
    assert backtest_service.mock_calls == []


def test_clearing_advice_navigation_context_hides_and_clears_banner() -> None:
    _app()
    view = BacktestView(backtest_service=MagicMock(), config=None)
    context = AdviceContractBacktestNavigation(
        candidate_result_id="daily-result-002",
        source_snapshot_id="snapshot-002",
        stock_code="2317",
        decision_date="2026-10-26",
        data_as_of_date="2026-10-26",
        strategy_version="strategy-v3",
        missing_author_fields=("holding_horizon",),
    )
    view.set_advice_contract_navigation_context(context)
    assert not view.advice_contract_navigation_context_label.isHidden()

    view.set_advice_contract_navigation_context(None)

    assert view.advice_contract_navigation_context_label.isHidden()
    assert view.advice_contract_navigation_context_label.text() == ""
