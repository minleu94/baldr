import os
import sys
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app_module.recommendation_profile_service import RecommendationProfileService
from ui_qt.main_window_coordinator import resolve_workspace_key
from ui_qt.views.backtest.config_panel import BacktestConfigPanel
from ui_qt.views.recommendation_view import RecommendationView
from ui_qt.widgets.left_navigation import LeftNavigationWidget, NavigationItem


def _app():
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication(sys.argv)
    return instance


class _FakeRecommendationService:
    last_run_context = {}


class _FakeRegimeService:
    def detect_regime(self):
        return SimpleNamespace(
            regime="Trend",
            confidence=0.75,
            regime_name_cn="趨勢追蹤",
            details={"source": "fixture", "as_of_date": "2026-09-20", "score": 70},
        )

    def get_strategy_config(self, regime):
        return {"regime": regime}


def test_recommendation_profile_details_expand_without_switching_mode_or_reapplying():
    _app()
    view = RecommendationView(
        recommendation_service=_FakeRecommendationService(),
        regime_service=_FakeRegimeService(),
        config=None,
        profile_service=RecommendationProfileService(None),
    )
    view.show()
    profile_index = next(
        index for index in range(view.profile_combo.count())
        if view.profile_combo.itemData(index)
    )
    view.profile_combo.setCurrentIndex(profile_index)
    mode_before = view.is_beginner_mode
    profile_before = view.current_profile
    config_before = deepcopy(view.strategy_config)

    view.profile_details_toggle.click()

    assert view.is_beginner_mode is mode_before is True
    assert view.current_profile == profile_before
    assert view.strategy_config == config_before
    assert view.profile_advanced_group.isVisible()
    assert "權重" in view.profile_advanced_label.text()
    assert "風險" in view.profile_advanced_label.text()

    view.profile_details_toggle.click()
    assert not view.profile_advanced_group.isVisible()


def test_backtest_guided_toggle_only_changes_visibility_and_preserves_values():
    _app()
    parent = MagicMock()
    parent.preset_service = None
    parent.optimizer_service = SimpleNamespace(max_workers=1)
    parent.walkforward_service = MagicMock()
    parent.portfolio_run_repository = None
    parent.run_repository = None
    parent.promotion_service = None
    parent._populate_watchlist_combo = MagicMock()
    parent._populate_strategy_combo = MagicMock()
    parent._on_strategy_changed = MagicMock()
    parent._update_optimization_params_form = MagicMock()
    parent._execute_optimization = MagicMock()
    parent._execute_walkforward = MagicMock()
    parent._execute_recommendation_portfolio_backtest = MagicMock()
    parent._on_research_lab_mode_changed = MagicMock()
    parent._execute_backtest = MagicMock()
    parent._on_cancel_clicked = MagicMock()

    panel = BacktestConfigPanel(parent)
    panel.show()
    panel.stock_code_input.setText("2330")
    panel.capital_input.setValue(123456)
    panel.fee_bps_input.setValue(12.5)
    panel.stop_loss_input.setValue(5.0)
    panel.take_profit_input.setValue(12.0)
    assert "5.00%" in panel.risk_assumption_summary.text()
    assert "12.00%" in panel.risk_assumption_summary.text()
    panel.optimization_group.setChecked(True)
    before = {
        "stock": panel.stock_code_input.text(),
        "start": panel.start_date.date(),
        "end": panel.end_date.date(),
        "capital": panel.capital_input.value(),
        "fee": panel.fee_bps_input.value(),
        "stop_loss": panel.stop_loss_input.value(),
        "take_profit": panel.take_profit_input.value(),
        "strategy": panel.strategy_combo.currentData(),
        "optimization": panel.optimization_group.isChecked(),
        "walkforward": panel.wf_group.isChecked(),
    }

    panel.guided_readability_toggle.click()
    assert panel.optimization_group.isVisible()
    assert panel.wf_group.isVisible()
    panel.risk_details_toggle.click()
    assert panel.risk_advanced_widget.isVisible()
    panel.risk_details_toggle.click()
    assert not panel.risk_advanced_widget.isVisible()
    panel.guided_readability_toggle.click()
    assert not panel.optimization_group.isVisible()
    assert not panel.wf_group.isVisible()

    after = {
        "stock": panel.stock_code_input.text(),
        "start": panel.start_date.date(),
        "end": panel.end_date.date(),
        "capital": panel.capital_input.value(),
        "fee": panel.fee_bps_input.value(),
        "stop_loss": panel.stop_loss_input.value(),
        "take_profit": panel.take_profit_input.value(),
        "strategy": panel.strategy_combo.currentData(),
        "optimization": panel.optimization_group.isChecked(),
        "walkforward": panel.wf_group.isChecked(),
    }
    assert after == before


def test_navigation_groups_keep_keys_and_reveal_deep_linked_workspace():
    _app()
    nav = LeftNavigationWidget(
        (
            NavigationItem("workbench", "決策工作台"),
            NavigationItem("recommendation", "推薦分析"),
            NavigationItem("backtest", "策略回測"),
            NavigationItem("update", "數據更新"),
            NavigationItem("runtime", "系統狀態"),
        )
    )
    nav.show()
    assert nav.item_keys() == ["workbench", "recommendation", "backtest", "update", "runtime"]
    assert nav.group_button_for_id("daily") is not None
    assert nav.group_button_for_id("research") is not None
    assert nav.group_button_for_id("maintenance") is not None

    nav.set_current_key("backtest")
    nav.group_button_for_id("research").click()
    assert nav.current_key() == "backtest"
    nav.set_current_key("backtest")
    assert nav.group_button_for_id("research").isChecked()
    assert nav.button_for_key("backtest").isVisible()
    assert resolve_workspace_key("Runtime") == "runtime"
    assert resolve_workspace_key("系統狀態") == "runtime"
