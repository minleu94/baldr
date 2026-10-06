"""保存結果→規則卡的實際worker及offscreenreadback，僅合成Temp來源。"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import time
from threading import Event
from pathlib import Path
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
import pytest
from tests.test_saved_strategy_rule_card import saved_case, inventory
from app_module.saved_strategy_rule_card import load_saved_strategy_rule_card
from ui_qt.views.research_lab.run_registry_compare_widget import RunRegistryCompareWidget
from ui_qt.widgets.strategy_rule_card_dialog import StrategyRuleCardDialog


def app():
    return QApplication.instance() or QApplication([])


def wait(predicate):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        QApplication.processEvents()
        if predicate():
            return
        QTest.qWait(10)
    assert predicate()


def widget_for(service):
    widget = RunRegistryCompareWidget(service)
    widget.refresh_runs()
    widget.run_list.item(0).setSelected(True)
    return widget


def test_actual_saved_result_to_rule_dialog_and_source_unchanged(tmp_path, monkeypatch):
    qapp = app()
    service, meta = saved_case(tmp_path)
    before = inventory(tmp_path)
    widget = widget_for(service)
    cards = []
    monkeypatch.setattr(StrategyRuleCardDialog, "exec", lambda self: cards.append((self.summary.text(), self.result_source.text(), self.audit.toPlainText())))
    widget.rule_result_button.click()
    assert not widget.rule_result_button.isEnabled()
    wait(lambda: widget._rule_worker is None)
    assert len(cards) == 1
    assert "歷史回測" in cards[0][0] and "規則版本 1.0" in cards[0][0]
    assert "費率 14.25 bp" in cards[0][1]
    assert "基準：未知" in cards[0][1]
    assert "source_ref_only" in cards[0][2] and "not_evaluable" in cards[0][2]
    assert widget.rule_result_button.isEnabled()
    assert inventory(tmp_path) == before
    widget.close()


def test_cost_missing_result_shows_unknown_and_no_source_link(tmp_path):
    qapp = app()
    from dataclasses import replace
    service, meta = saved_case(tmp_path, mutate=lambda m: replace(m, original_input={}))
    result = load_saved_strategy_rule_card(service, meta)
    dialog = StrategyRuleCardDialog(result.rule_card, result=result)
    dialog.show()
    qapp.processEvents()
    assert "保存費率：未知" in dialog.result_source.text()
    assert "尚不能連結保存規則" in dialog.result_source.text()
    assert "尚未核對保存時" in dialog.qualification.text()
    assert not dialog.audit.isVisible()
    dialog.close()


@pytest.mark.parametrize("action", ["selection", "close"])
def test_cancel_or_new_selection_does_not_apply_old_callback(tmp_path, monkeypatch, action):
    qapp = app()
    service, meta = saved_case(tmp_path)
    entered, release = Event(), Event()
    original = service.load_run_data
    calls = []
    def blocked(run_id):
        calls.append(run_id)
        entered.set()
        assert release.wait(5)
        return original(run_id)
    monkeypatch.setattr(service, "load_run_data", blocked)
    cards = []
    monkeypatch.setattr(StrategyRuleCardDialog, "exec", lambda self: cards.append(self))
    widget = widget_for(service)
    widget.rule_result_button.click()
    wait(entered.is_set)
    widget.open_selected_rule_result()
    assert len(calls) == 1
    if action == "selection":
        widget.clear_selection()
    else:
        widget.close()
    release.set()
    wait(lambda: widget._rule_worker is None)
    assert cards == []
    assert "核對保存來源中" not in widget.rule_result_status.text()
    widget.close()


def test_integrity_error_is_visible_and_not_infinite_loading(tmp_path, monkeypatch):
    qapp = app()
    service, meta = saved_case(tmp_path)
    path = Path(meta.equity_path)
    path.write_bytes(path.read_bytes() + b"fixture tamper")
    widget = widget_for(service)
    monkeypatch.setattr(StrategyRuleCardDialog, "exec", lambda self: pytest.fail("corrupt source opened"))
    widget.rule_result_button.click()
    wait(lambda: widget._rule_worker is None)
    assert "核對失敗" in widget.rule_result_status.text()
    assert widget.rule_result_button.isEnabled()
    assert "核對失敗" in widget.rule_result_button.toolTip()
    widget.close()
