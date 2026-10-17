"""原規則卡與未開放模式在Qt正常控制項上的拒絕接線。"""
import json

from PySide6.QtWidgets import QApplication, QComboBox, QLabel, QWidget
import pytest

from decision_module.strategies.baldr_vcp_contract import STRATEGY_ID
from tests.test_ui_qt_strategy_rule_card import Harness
from ui_qt.views.backtest_view import BacktestView
from ui_qt.widgets.strategy_rule_card_dialog import StrategyRuleCardDialog


def test_selected_rule_dialog_uses_fixed_registered_vcp_identity(monkeypatch):
    app = QApplication.instance() or QApplication([])
    view = Harness()
    view.strategy_combo.clear()
    view.strategy_combo.addItem("三段轉折收縮突破（研究）", STRATEGY_ID)
    view.params = {}
    cards = []
    monkeypatch.setattr(StrategyRuleCardDialog, "exec", lambda self: cards.append(json.loads(self.audit.toPlainText())))
    monkeypatch.setattr("decision_module.strategies.registry.StrategyRegistry.get_executor",
                        lambda *_: pytest.fail("規則卡不得執行策略"))
    BacktestView._show_strategy_rule_card(view)
    card = cards[0]
    assert card["identity"]["rule_id"] == STRATEGY_ID
    assert card["identity"]["rule_version"] == "1.0.0"
    assert card["fields"]["entry"]["value"]["base"]["last_depth_max_bp"] == 800
    assert card["fields"]["data_insufficiency"]["value"]["warmup"] == 80
    assert card["rule_status"] == "specified_research_hypothesis"
    view.close()
    app.processEvents()


@pytest.mark.parametrize("mode", ["batch_stock", "optimization", "walkforward", "recommendation_replay"])
def test_unsupported_mode_has_actionable_warning_without_worker(monkeypatch, mode):
    app = QApplication.instance() or QApplication([])
    view = QWidget()
    view.strategy_combo = QComboBox()
    view.strategy_combo.addItem("三段收縮研究", STRATEGY_ID)
    warnings = []
    monkeypatch.setattr("ui_qt.views.backtest_view.QMessageBox.warning", lambda *_a: warnings.append(_a[-1]))
    assert BacktestView._reject_squeeze_other_mode(view, mode)
    assert len(warnings) == 1 and "正常單股" in warnings[0]
    assert not BacktestView._reject_squeeze_other_mode(view, "single_stock")
    view.close()
    app.processEvents()


def test_independent_recommendation_replay_does_not_depend_on_single_strategy(monkeypatch):
    app = QApplication.instance() or QApplication([])
    view = QWidget()
    view.strategy_combo = QComboBox()
    view.strategy_combo.addItem("三段收縮研究", STRATEGY_ID)
    view.research_lab_mode_combo = QComboBox()
    view.research_lab_mode_combo.addItem("推薦回放", "recommendation_replay")
    called = []
    view._execute_recommendation_portfolio_backtest = lambda: called.append("original_profile")
    monkeypatch.setattr("ui_qt.views.backtest_view.QMessageBox.warning", lambda *_: pytest.fail("獨立推薦profile不可受單股策略限制"))
    BacktestView._execute_backtest(view)
    assert called == ["original_profile"]
    view.close()
    app.processEvents()
