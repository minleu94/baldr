"""保存結果→規則卡的實際worker及offscreenreadback，僅合成Temp來源。"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import time
from threading import Event
from pathlib import Path
from PySide6.QtTest import QTest
from PySide6.QtCore import Qt
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


def history_widget(tmp_path):
    from tests.test_baldr_b07_research_history import fixed_sources
    from ui_qt.views.backtest.result_panel import ResearchHistoryLookupWidget
    _, lookup, *_ = fixed_sources(tmp_path)
    opened = []
    widget = ResearchHistoryLookupWidget(lookup, opened.append)
    widget.refresh_entries()
    wait(lambda: widget._worker is None)
    return widget, opened


def test_b07_single_lookup_filter_metadata_and_exact_original_result(tmp_path):
    qapp = app()
    widget, opened = history_widget(tmp_path)
    before = inventory(tmp_path)
    assert widget.entries.count() == 8
    widget.search.setText("legacy_backtest")
    assert widget.entries.count() == 1
    widget.entries.setCurrentRow(0)
    widget.open_result.click()
    wait(lambda: widget._worker is None)
    assert len(opened) == 1 and opened[0].entry.run_type == "legacy_backtest"
    assert opened[0].result["stock_code"] == "2330"
    widget.search.setText("research_forward")
    widget.entries.setCurrentRow(0)
    assert not widget.open_result.isEnabled() and not widget.open_rule.isEnabled()
    assert "research_forward_metadata_only" in widget.status.text()
    assert '"run_type":"research_forward"' in widget.status.toolTip()
    assert widget.metadata_button.isEnabled()
    assert inventory(tmp_path) == before
    widget.close()


@pytest.mark.parametrize("action", ["selection", "cancel", "close"])
def test_b07_lookup_stale_cancel_close_refuses_callback(tmp_path, monkeypatch, action):
    qapp = app()
    widget, opened = history_widget(tmp_path)
    widget.search.setText("legacy_backtest")
    widget.entries.setCurrentRow(0)
    entered, release = Event(), Event()
    original = widget.lookup.resolve
    def blocked(selected):
        entered.set()
        assert release.wait(5)
        return original(selected)
    monkeypatch.setattr(widget.lookup, "resolve", blocked)
    before = inventory(tmp_path)
    widget.open_result.click()
    wait(entered.is_set)
    if action == "selection":
        widget.search.setText("research_forward")
    elif action == "cancel":
        widget.cancel.click()
    else:
        widget.close()
    release.set()
    wait(lambda: widget._worker is None)
    assert opened == []
    assert inventory(tmp_path) == before
    widget.close()


def test_b07_lookup_revision_failure_never_opens_partial_result(tmp_path):
    qapp = app()
    widget, opened = history_widget(tmp_path)
    widget.search.setText("legacy_backtest")
    widget.entries.setCurrentRow(0)
    (tmp_path / "legacy.parquet").write_bytes(b"revision")
    before = inventory(tmp_path)
    widget.open_result.click()
    wait(lambda: widget._worker is None)
    assert opened == []
    assert "selected_source_changed" in widget.status.text()
    assert inventory(tmp_path) == before
    widget.close()


@pytest.mark.parametrize("kind", ["legacy_backtest", "single_backtest", "batch_backtest_stock", "fixed_basket_stock"])
def test_b07_exact_result_returns_to_original_backtest_summary(tmp_path, kind):
    qapp = app()
    from tests.test_baldr_b07_research_history import fixed_sources
    from ui_qt.views.backtest_view import BacktestView
    from ui_qt.views.backtest.result_panel import ResearchHistoryLookupWidget
    _, lookup, *_ = fixed_sources(tmp_path)
    view = BacktestView(backtest_service=None, config=None)
    widget = ResearchHistoryLookupWidget(lookup, view._open_research_history_result, view)
    widget.refresh_entries()
    wait(lambda: widget._worker is None)
    # registry type 字串也是其他名稱的子字串；直接依 exact kind 選取。
    row = next(index for index in range(widget.entries.count())
               if widget.entries.item(index).data(Qt.ItemDataRole.UserRole).run_type == kind)
    widget.entries.setCurrentRow(row)
    before = inventory(tmp_path)
    widget.open_result.click()
    wait(lambda: widget._worker is None)
    assert f"／{kind}" in view.summary_text.toPlainText(), widget.status.text()
    assert "股票代號: 2330" in view.summary_text.toPlainText()
    assert "總報酬率: 未知" in view.summary_text.toPlainText()
    assert all(button is None or not button.isEnabled() for button in (view.save_result_btn, view.promote_btn))
    assert view.current_report is None
    assert inventory(tmp_path) == before
    widget.close()
    view.close()


def test_b07_execution_generation_change_does_not_open_old_history(tmp_path, monkeypatch):
    qapp = app()
    from types import SimpleNamespace
    widget, opened = history_widget(tmp_path)
    widget._owner = SimpleNamespace(_execution_generation=1)
    widget.search.setText("legacy_backtest")
    widget.entries.setCurrentRow(0)
    entered, release = Event(), Event()
    original = widget.lookup.resolve
    def blocked(selected):
        entered.set()
        assert release.wait(5)
        return original(selected)
    monkeypatch.setattr(widget.lookup, "resolve", blocked)
    widget.open_result.click()
    wait(entered.is_set)
    widget._owner._execution_generation = 2
    release.set()
    wait(lambda: widget._worker is None)
    assert opened == [] and "新執行" in widget.status.text()
    widget.close()
