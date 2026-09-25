"""回測 UI 的策略列表順序與 registry metadata contract。"""

import os
from unittest.mock import MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from ui_qt.views.backtest_view import BacktestView


def test_backtest_strategy_combo_preserves_registered_ids_and_order():
    app = QApplication.instance() or QApplication([])
    view = BacktestView(backtest_service=MagicMock(), config=None)

    strategies = [
        view.strategy_combo.itemData(index)
        for index in range(view.strategy_combo.count())
    ]

    assert strategies == [
        "baseline_score_threshold",
        "momentum_aggressive_v1",
        "stable_conservative_v1",
    ]
    assert [view.strategy_combo.itemText(index) for index in range(view.strategy_combo.count())] == [
        "基準分數門檻策略",
        "暴衝策略",
        "穩健策略",
    ]
    assert QApplication.instance() is app
