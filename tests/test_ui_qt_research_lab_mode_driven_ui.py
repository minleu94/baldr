import os
import sys
from unittest.mock import MagicMock

# 設定為 offscreen 以免開啟實際 GUI 視窗
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel, QMainWindow
from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtTest import QTest
import pytest

from ui_qt.views.backtest_view import BacktestView, RESEARCH_LAB_MODES
from app_module.backtest_analyst_diagnostics import AnalystDiagnosticsDTO


def app():
    """獲取或建立 QApplication 實例"""
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication(sys.argv)
    return instance


@pytest.fixture
def qt_app():
    return app()


def test_research_lab_mode_driven_ui_visibility(qt_app):
    """驗證選中不同實驗模式時，左側配置面板是否會動態顯示/隱藏/摺疊對應的 GroupBox"""
    mock_backtest_service = MagicMock()
    mock_preset_service = MagicMock()
    
    # 建立 view
    view = BacktestView(backtest_service=mock_backtest_service, config=None)
    
    # 手動模擬 preset_service、walkforward_service 等以啟用所有 GroupBox
    view.preset_service = mock_preset_service
    view.walkforward_service = MagicMock()
    view.optimizer_service = MagicMock()
    
    # 重新觸發一次 UI 初始化以反映 preset/wf 服務的啟用
    # 這裡我們手動重建或直接 Mock 屬性。在實際 `_setup_ui` 中，
    # 這些屬性如 strategy_preset_group, optimization_group, wf_group
    # 都已經在 setup_ui 時建立（因為 mock_preset_service 與 optimizer_service 是在 init 後才 assign，
    # 但在 test 環境下，如果 config=None，那 preset_service 就會是 None，
    # 所以在 view 實例化時 strategy_preset_group 會是 None。
    # 為了測試，我們可以直接手動將 Mock QGroupBox 塞入 view 以測試 _update_ui_state_by_mode）
    
    view.strategy_preset_group = MagicMock()
    view.input_source_group = MagicMock()
    view.stock_selection_container = MagicMock()
    view.risk_cost_group = MagicMock()
    view.sizing_group = MagicMock()
    view.position_mgmt_group = MagicMock()
    view.market_constraints_group = MagicMock()
    view.strategy_config_group = MagicMock()
    view.optimization_group = MagicMock()
    view.wf_group = MagicMock()
    view.recommendation_portfolio_group = MagicMock()
    view.stock_mode_combo = MagicMock()

    # 1. 測試單股回測 (single_stock)
    view._update_ui_state_by_mode("single_stock")
    view.strategy_preset_group.setVisible.assert_called_with(True)
    view.input_source_group.setVisible.assert_called_with(True)
    view.stock_selection_container.setVisible.assert_called_with(True)
    view.stock_mode_combo.setCurrentText.assert_called_with("單一股票")
    view.risk_cost_group.setVisible.assert_called_with(True)
    view.recommendation_portfolio_group.setVisible.assert_called_with(False)
    view.optimization_group.setVisible.assert_called_with(True)
    view.optimization_group.setChecked.assert_called_with(False)

    # 2. 測試批次股票回測 (batch_stock)
    view.stock_mode_combo.reset_mock()
    view.stock_selection_container.reset_mock()
    view._update_ui_state_by_mode("batch_stock")
    view.input_source_group.setVisible.assert_called_with(True)
    view.stock_selection_container.setVisible.assert_called_with(True)
    view.stock_mode_combo.setCurrentText.assert_called_with("選股清單")
    view.recommendation_portfolio_group.setVisible.assert_called_with(False)
    view.optimization_group.setVisible.assert_called_with(False)

    # 3. 測試推薦系統回放 (recommendation_replay)
    view.stock_selection_container.reset_mock()
    view._update_ui_state_by_mode("recommendation_replay")
    view.input_source_group.setVisible.assert_called_with(True)
    view.stock_selection_container.setVisible.assert_called_with(False)
    view.strategy_preset_group.setVisible.assert_called_with(False)
    view.risk_cost_group.setVisible.assert_called_with(True)
    view.recommendation_portfolio_group.setVisible.assert_called_with(True)
    view.recommendation_portfolio_group.setChecked.assert_called_with(True)
    view.optimization_group.setVisible.assert_called_with(False)

    # 4. 測試策略研究 (strategy_research)
    view._update_ui_state_by_mode("strategy_research")
    view.strategy_preset_group.setVisible.assert_called_with(True)
    view.input_source_group.setVisible.assert_called_with(True)
    view.stock_selection_container.setVisible.assert_called_with(True)
    view.optimization_group.setVisible.assert_called_with(True)
    view.optimization_group.setChecked.assert_called_with(False)
    view.wf_group.setVisible.assert_called_with(True)
    view.wf_group.setChecked.assert_called_with(False)


def test_strategy_research_advanced_validation_groups_are_mutually_exclusive(qt_app):
    view = BacktestView(backtest_service=MagicMock(), config=None)

    view.research_lab_mode_combo.setCurrentIndex(
        view.research_lab_mode_combo.findData("strategy_research")
    )
    view.optimization_group.setChecked(True)
    assert view.optimization_group.isChecked() is True
    assert view.wf_group.isChecked() is False
    assert view.params_widget.isHidden() is True

    view.wf_group.setChecked(True)
    assert view.wf_group.isChecked() is True
    assert view.optimization_group.isChecked() is False
    assert view.params_widget.isHidden() is False
    assert view.optimization_params_layout.count() == 0


def test_recommendation_replay_exposes_and_locks_execution_contract(qt_app):
    view = BacktestView(backtest_service=MagicMock(), config=None)
    panel = view.config_panel
    panel.execution_price_combo.setCurrentIndex(1)
    panel.stop_profit_mode_combo.setCurrentIndex(1)
    panel.execution_price_combo.setToolTip("原本的執行價格詳細說明")
    panel.stop_profit_mode_combo.setToolTip("原本的停損停利詳細說明")

    panel._update_ui_state_by_mode("recommendation_replay")

    # BacktestView 在測試中尚未 show；檢查群組沒有被明確隱藏，
    # 而非 QWidget.isVisible() 的父層可見性。
    assert panel.risk_cost_group.isHidden() is False
    assert panel.execution_price_combo.currentIndex() == 0
    assert panel.execution_price_combo.isEnabled() is False
    assert panel.stop_profit_mode_combo.currentIndex() == 0
    assert panel.stop_profit_mode_combo.isEnabled() is False
    assert "next-session-open.v2" in panel.risk_cost_group.title()
    assert "next-session-open.v2" in panel.execution_price_combo.toolTip()
    assert "固定使用百分比" in panel.stop_profit_mode_combo.toolTip()

    panel._update_ui_state_by_mode("single_stock")

    assert panel.execution_price_combo.currentIndex() == 1
    assert panel.execution_price_combo.isEnabled() is True
    assert panel.stop_profit_mode_combo.currentIndex() == 1
    assert panel.stop_profit_mode_combo.isEnabled() is True
    assert panel.execution_price_combo.toolTip() == "原本的執行價格詳細說明"
    assert panel.stop_profit_mode_combo.toolTip() == "原本的停損停利詳細說明"


def test_research_lab_config_panel_default_width_prevents_horizontal_squeeze(qt_app):
    """策略回測左側控制面板預設寬度應足以容納長下拉欄位。"""
    view = BacktestView(backtest_service=MagicMock(), config=None)

    assert view.config_panel.minimumWidth() >= 520
    assert view.execution_price_combo.minimumWidth() >= 320


def test_research_lab_responsive_layout_keeps_1024px_controls_usable(qt_app):
    """桌面與窄桌面切換時，1024px 不應把設定欄壓成水平窄欄。"""
    host = QMainWindow()
    view = BacktestView(backtest_service=MagicMock(), config=None)
    host.setCentralWidget(view)
    host.setFixedSize(1366, 768)
    host.show()
    qt_app.processEvents()
    assert host.size().width() == 1366
    assert host.size().height() == 768
    assert view.size().width() == 1366
    assert view.backtest_splitter.orientation() == Qt.Orientation.Horizontal

    host.setFixedSize(1024, 768)
    qt_app.processEvents()
    assert host.size().width() == 1024
    assert host.size().height() == 768
    assert view.size().width() == 1024
    assert view.size().height() == 768
    assert view.backtest_splitter.orientation() == Qt.Orientation.Vertical
    assert view.config_scroll.width() >= 900
    assert view.result_panel.width() >= 900
    assert view.config_scroll.height() >= 220
    assert view.result_panel.height() >= 350

    view._set_config_panel_collapsed(True)
    qt_app.processEvents()
    assert view.result_panel.width() >= 900
    assert view.result_panel.height() >= 350
    view._set_config_panel_collapsed(False)
    qt_app.processEvents()
    assert view.config_scroll.width() >= 900
    assert view.config_scroll.height() >= 220
    assert view.result_panel.height() >= 350
    host.close()


def test_result_workspace_uses_semantic_tabs_and_single_primary_cta(qt_app):
    view = BacktestView(backtest_service=MagicMock(), config=None)
    panel = view.result_panel

    assert {"summary", "diagnostics", "optimization", "recommendation"}.issubset(
        panel._result_tab_widgets
    )
    assert panel.result_tab_key(view.result_tabs.currentIndex()) == "summary"
    assert view.execute_btn.text() == "執行單股回測"
    assert view.execution_intent_label.text().startswith("本次將執行單股回測")
    assert view.optimize_btn.isHidden()
    assert view.wf_execute_btn.isHidden()
    assert view.execute_recommendation_portfolio_btn.isHidden()

    view.research_lab_mode_combo.setCurrentIndex(
        view.research_lab_mode_combo.findData("recommendation_replay")
    )
    assert panel.result_tabs.isTabVisible(panel.result_tabs.indexOf(panel._result_tab_widgets["recommendation"]))
    assert not panel.result_tabs.isTabVisible(panel.result_tabs.indexOf(panel._result_tab_widgets["summary"]))
    assert view.execute_btn.text() == "執行推薦回放"
    assert "推薦回放" in view.execution_intent_label.text()


def test_recommendation_mode_dispatches_without_stock_code(qt_app, monkeypatch):
    view = BacktestView(backtest_service=MagicMock(), config=None)
    view.research_lab_mode_combo.setCurrentIndex(
        view.research_lab_mode_combo.findData("recommendation_replay")
    )
    view.current_recommendation_portfolio_config = {"profile_id": "demo"}
    dispatch = MagicMock()
    monkeypatch.setattr(view, "_execute_recommendation_portfolio_backtest", dispatch)

    view._execute_backtest()

    dispatch.assert_called_once_with()


def test_analyst_diagnostics_widget_has_numeric_tables_and_theme_boundary(qt_app):
    view = BacktestView(backtest_service=MagicMock(), config=None)
    widget = view.result_panel.analyst_diagnostics_widget
    widget.set_diagnostics(
        AnalystDiagnosticsDTO(
            status="available",
            reason=None,
            kpis={
                "average_exposure_bp": 1200,
                "transaction_costs": {"fee_bp": 4, "slippage_bp": 2, "total_bp": 6},
            },
            rolling=({
                "window": 20,
                "return_bp": 100,
                "annualized_vol_bp": 800,
                "observation_count": 20,
                "status": "available",
            },),
            monthly=({"year": 2026, "month": 1, "return_text": "+100 bp"},),
            benchmark={"status": "unknown", "reason": "legacy missing"},
            definitions=("月報酬以相鄰月末計算。",),
        )
    )

    assert widget.rolling_table.item(0, 1).text() == "100 bp"
    assert widget.monthly_table.item(0, 1).text() == "+100 bp"
    assert widget.benchmark_table.item(0, 3).text() == "legacy missing"
    assert widget.status_label.accessibleName() == "分析診斷狀態"
    assert "#" in widget.status_label.styleSheet()


def test_research_lab_optimization_param_labels_are_compact(qt_app):
    """參數最佳化列的 label 不應把控制項往右推太遠。"""
    view = BacktestView(backtest_service=MagicMock(), config=None)
    view.optimization_group.setChecked(True)
    view._update_optimization_params_form()

    compact_labels = {
        "門檻模式:",
        "買入分數門檻:",
        "賣出分數門檻:",
        "買入確認天數:",
        "賣出確認天數:",
        "交易冷卻天數:",
    }
    labels = [
        label
        for label in view.optimization_params_widget.findChildren(QLabel)
        if label.text() in compact_labels
    ]

    assert labels
    assert all(label.minimumWidth() == 104 for label in labels)
    assert all(label.maximumWidth() == 104 for label in labels)


def test_optimization_timer_runs_once_while_backtest_view_is_alive(qt_app):
    view = BacktestView(backtest_service=MagicMock(), config=None)
    calls = []
    original_update = view._update_optimization_params_form

    def observe_update():
        calls.append("updated")
        original_update()

    view._update_optimization_params_form = observe_update
    QTest.qWait(140)

    assert calls == ["updated"]

    view.setAttribute(Qt.WA_DeleteOnClose, True)
    assert view.close()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


def test_optimization_timer_is_discarded_when_backtest_view_is_deleted(qt_app, monkeypatch):
    qt_exceptions = []
    monkeypatch.setattr(
        sys,
        "excepthook",
        lambda exception_type, exception, traceback: qt_exceptions.append(
            (exception_type, exception, traceback)
        ),
    )
    view = BacktestView(backtest_service=MagicMock(), config=None)
    calls = []
    original_update = view._update_optimization_params_form

    def observe_update():
        calls.append("updated")
        original_update()

    view._update_optimization_params_form = observe_update
    view.setAttribute(Qt.WA_DeleteOnClose, True)
    assert view.close()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    QTest.qWait(140)

    assert qt_exceptions == []
    assert calls == []
