"""合成設定規則卡，不啟動回測、producer或正式來源。"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QWidget, QComboBox, QLabel
from app_module.strategy_rule_card_readmodel import read_strategy_rule_card
from decision_module.strategies.contracts import StrategySpec
from ui_qt.widgets.strategy_rule_card_dialog import StrategyRuleCardDialog
from ui_qt.views.backtest_view import BacktestView
import pytest


def app():
    return QApplication.instance() or QApplication([])


class Harness(QWidget):
    def __init__(self):
        super().__init__()
        self.strategy_combo = QComboBox()
        self.strategy_combo.addItem("baseline", "baseline_score_threshold")
        self.strategy_desc = QLabel("description")
        self.params = {"buy_score": 65}
    def _get_default_strategy_config(self):
        return {"fixture": "config"}
    def _get_strategy_params(self):
        return dict(self.params)


def test_consumer_reads_current_config_without_executor_or_old_result(monkeypatch):
    qapp = app()
    view = Harness()
    cards = []
    monkeypatch.setattr(StrategyRuleCardDialog, "exec", lambda self: cards.append(self.audit.toPlainText()))
    monkeypatch.setattr("decision_module.strategies.registry.StrategyRegistry.get_executor",
                        lambda *_: pytest.fail("must not execute"))
    BacktestView._show_strategy_rule_card(view)
    view.params["buy_score"] = 66
    BacktestView._show_strategy_rule_card(view)
    import json
    first, second = map(json.loads, cards)
    assert first["fields"]["parameters"]["value"] == {"buy_score": 65}
    assert second["fields"]["parameters"]["value"] == {"buy_score": 66}
    assert first["identity"]["rule_sha256"] != second["identity"]["rule_sha256"]
    assert first["identity"]["result_kind"] == "historical_backtest"
    assert first["fields"]["source_trace"]["value"]["source_run_id"] is None
    assert first["performance_status"] == "not_evaluable"
    view.close()


def test_unknown_trade_contract_is_visible_and_audit_starts_collapsed():
    qapp = app()
    card = read_strategy_rule_card(StrategySpec("baseline_score_threshold", "1.0", config={"params": {"buy_score": 65}}))
    dialog = StrategyRuleCardDialog(card)
    dialog.show()
    qapp.processEvents()
    assert not dialog.audit.isVisible()
    assert "出場條件：未知" in dialog.rules.toPlainText()
    assert "比較基準：未知" in dialog.rules.toPlainText()
    assert "尚未連結執行結果" in dialog.summary.text()
    assert "尚不可評估" in dialog.qualification.text()
    assert dialog.rules.isReadOnly() and dialog.audit.isReadOnly()
    dialog.close()


def test_registry_revision_mismatch_remains_not_evaluable():
    qapp = app()
    card = read_strategy_rule_card(StrategySpec("baseline_score_threshold", "2.0"))
    dialog = StrategyRuleCardDialog(card)
    assert "registry_version_mismatch" in dialog.qualification.toolTip()
    assert "版本 2.0" in dialog.summary.text()
    assert "not_evaluable" in dialog.audit.toPlainText()
    dialog.close()


def test_no_selection_does_not_open_card(monkeypatch):
    qapp = app()
    view = Harness()
    view.strategy_combo.clear()
    warnings = []
    monkeypatch.setattr("ui_qt.views.backtest_view.QMessageBox.warning", lambda *args: warnings.append(args))
    monkeypatch.setattr(StrategyRuleCardDialog, "exec", lambda *_: pytest.fail("empty selection"))
    BacktestView._show_strategy_rule_card(view)
    assert len(warnings) == 1
    view.close()
