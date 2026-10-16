"""真 typed v2 single-backtest 的保存規則卡 UI 讀回；不重跑或授績效。"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import copy
import json
import time
from dataclasses import replace
from pathlib import Path
from threading import Event

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
import pytest

from tests.test_single_backtest_rule_execution_v2 import executed_v2_case
from app_module.saved_strategy_rule_card import metadata_sha256
from decision_module.strategies.registry import StrategyRegistry
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


def inventory(root):
    return {
        str(path.relative_to(root)): (path.read_bytes(), path.stat().st_mtime_ns)
        for path in Path(root).rglob("*")
        if path.is_file()
    }


def selected_widget(registry):
    widget = RunRegistryCompareWidget(registry)
    widget.refresh_runs()
    assert widget.run_list.count() == 1
    widget.run_list.item(0).setSelected(True)
    return widget


def capture_dialog(dialog):
    return {
        "summary": dialog.summary.text(),
        "result_source": dialog.result_source.text(),
        "qualification": dialog.qualification.text(),
        "rules": dialog.rules.toPlainText(),
        "audit": json.loads(dialog.audit.toPlainText()),
    }


@pytest.mark.parametrize(
    "strategy_id",
    ["stable_conservative_v1", "momentum_aggressive_v1"],
)
def test_v2_saved_rule_card_uses_original_execution_and_returns_to_registry(
    tmp_path, monkeypatch, strategy_id
):
    qapp = app()
    config, registry, metadata, request, report, backtest_service = executed_v2_case(
        tmp_path, monkeypatch, strategy_id
    )
    execution = metadata.data_manifest["single_backtest_rule_execution"]
    assert execution["schema"] == "single-backtest-rule-execution.v2"
    assert execution["strategy_spec"]["strategy_id"] == strategy_id
    before = inventory(tmp_path)

    def forbidden(*_args, **_kwargs):
        pytest.fail("saved UI reader must not consult current executor or reload market data")

    monkeypatch.setattr(StrategyRegistry, "get_executor", forbidden)
    monkeypatch.setattr(StrategyRegistry, "get_strategy_meta", forbidden)
    monkeypatch.setattr(backtest_service, "_load_stock_data", forbidden)

    widget = selected_widget(registry)
    opened = []

    def close_after_capture(dialog):
        opened.append(capture_dialog(dialog))
        dialog.reject()

    monkeypatch.setattr(StrategyRuleCardDialog, "exec", close_after_capture)
    widget.rule_result_button.click()
    wait(lambda: widget._rule_worker is None)

    assert len(opened) == 1
    card = opened[0]
    audit = card["audit"]
    saved_rule = audit["rule_card"]
    assert saved_rule["identity"]["rule_id"] == strategy_id
    assert saved_rule["identity"]["rule_version"] == "1.0.0"
    assert saved_rule["rule_status"] == "execution_contract_bound"
    assert audit["source_status"] == "source_ref_only"
    assert audit["result_ref"] == f"research-run:{metadata.run_id}"
    assert audit["performance_status"] == "not_evaluable"

    fields = saved_rule["fields"]
    executor = execution["executor"]
    assert fields["entry"]["value"]["threshold"] == executor["buy_score"]
    assert fields["exit"]["value"]["threshold"] == executor["sell_score"]
    assert fields["entry"]["value"]["confirm_sessions"] == executor["buy_confirm_days"]
    assert fields["exit"]["value"]["confirm_sessions"] == executor["sell_confirm_days"]
    assert fields["entry"]["value"]["cooldown_calendar_days"] == executor["cooldown_days"]
    assert fields["parameters"]["value"] == execution["strategy_spec"]["config"]
    broker = execution["broker_config"]
    assert fields["cost"]["value"]["fee_bps"] == broker["fee_bps"]
    assert fields["cost"]["value"]["slippage_bps"] == broker["slippage_bps"]
    assert fields["execution_mode"]["value"] == execution["execution_contract"]
    assert fields["source_trace"]["value"]["source_hashes"] == execution["source_hashes"]
    assert fields["qualification"]["value"]["historical_pit_eligible"] is False
    assert "正式資格未授予" in card["result_source"]
    assert "尚不可評估" in card["qualification"]

    # 關閉規則卡後回到同一筆 Registry 選取；操作只讀且不改保存件。
    assert widget.selected_run_ids() == [metadata.run_id]
    assert widget.rule_result_button.isEnabled()
    assert metadata_sha256(registry.load_run_data(metadata.run_id).metadata) == metadata_sha256(metadata)
    assert inventory(tmp_path) == before
    widget.close()


@pytest.mark.parametrize(
    "action",
    ["selection", "close"],
)
def test_v2_saved_rule_card_ignores_late_callback_after_selection_or_close(
    tmp_path, monkeypatch, action
):
    qapp = app()
    _, registry, metadata, _, _, _ = executed_v2_case(
        tmp_path, monkeypatch, "stable_conservative_v1"
    )
    before = inventory(tmp_path)
    widget = selected_widget(registry)
    entered, release = Event(), Event()
    original = registry.load_run_data

    def blocked(run_id):
        entered.set()
        assert release.wait(5)
        return original(run_id)

    monkeypatch.setattr(registry, "load_run_data", blocked)
    monkeypatch.setattr(
        StrategyRuleCardDialog,
        "exec",
        lambda *_: pytest.fail("late v2 result must not open a rule card"),
    )
    widget.rule_result_button.click()
    wait(entered.is_set)

    if action == "selection":
        widget.clear_selection()
    else:
        widget.close()
    release.set()
    wait(lambda: widget._rule_worker is None)

    if action == "selection":
        assert widget.selected_run_ids() == []
    else:
        assert widget._rule_closed is True
    assert "保存來源已讀回" not in widget.rule_result_status.text()
    assert inventory(tmp_path) == before
    widget.close()


def test_v2_changed_saved_execution_does_not_reuse_previous_successful_card(
    tmp_path, monkeypatch
):
    qapp = app()
    _, registry, metadata, _, _, _ = executed_v2_case(
        tmp_path, monkeypatch, "momentum_aggressive_v1"
    )
    before = inventory(tmp_path)
    widget = selected_widget(registry)
    cards = []

    def close_after_capture(dialog):
        cards.append(capture_dialog(dialog))
        dialog.reject()

    monkeypatch.setattr(StrategyRuleCardDialog, "exec", close_after_capture)
    widget.rule_result_button.click()
    wait(lambda: widget._rule_worker is None)
    assert cards[0]["audit"]["source_status"] == "source_ref_only"

    original = registry.load_run_data
    loaded = original(metadata.run_id)
    changed = copy.deepcopy(metadata)
    execution = changed.data_manifest["single_backtest_rule_execution"]
    execution["executor"]["buy_score"] += 1

    def changed_read(run_id):
        assert run_id == metadata.run_id
        return replace(loaded, metadata=changed)

    monkeypatch.setattr(registry, "load_run_data", changed_read)
    widget.rule_result_button.click()
    wait(lambda: widget._rule_worker is None)

    assert len(cards) == 2
    failed = cards[1]
    assert failed["audit"]["source_status"] == "not_evaluable"
    assert failed["audit"]["result_ref"] is None
    assert failed["audit"]["rule_card"]["rule_status"] == "not_evaluable"
    assert "selected_source_changed" in failed["audit"]["reasons"]
    assert "saved_rule_pin_mismatch" in failed["audit"]["reasons"]
    assert "尚不能連結保存規則" in failed["result_source"]
    assert failed["audit"]["performance_status"] == "not_evaluable"
    assert widget.selected_run_ids() == [metadata.run_id]
    assert inventory(tmp_path) == before
    widget.close()
