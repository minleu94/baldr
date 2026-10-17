"""訊號對照presentation、翻頁、原規則及取消／晚到；不授Native或策略資格。"""
from dataclasses import replace
from threading import Event
import time

import pandas as pd
import pytest
from PySide6.QtWidgets import QApplication

from app_module.research_run_dtos import ResearchRunMetadataDTO
from app_module.saved_strategy_signal_comparison import (
    SavedSignalComparison, SavedSignalComparisonDay, SavedSignalStrategy, SavedStrategySignal,
)
from ui_qt.widgets.saved_strategy_signal_compare_widget import SavedStrategySignalCompareWidget


def wait(predicate):
    app = QApplication.instance()
    deadline = time.monotonic() + 10
    while not predicate():
        app.processEvents()
        assert time.monotonic() < deadline, "訊號worker未在期限內自然完成"
        time.sleep(.01)
    app.processEvents()


@pytest.fixture
def widget():
    app = QApplication.instance() or QApplication([])
    widget = SavedStrategySignalCompareWidget(object())
    widget.resize(1100, 500)
    widget.show()
    app.processEvents()
    yield widget
    widget.begin_shutdown()
    wait(lambda: widget._worker is None)
    widget.close()


def selection():
    return tuple(ResearchRunMetadataDTO(run_id="run" + str(i), run_name="策略" + str(i),
        run_type="single_backtest", strategy_id="strategy" + str(i)) for i in range(2))


def model():
    # 合成展示DTO；真來源／規則與價量綁定由domain實際保存測試核對。
    strategies = tuple(SavedSignalStrategy("run" + str(i), "策略" + str(i), "strategy" + str(i),
        "1.0.0", str(i), "家族" + str(i), None) for i in range(2))
    rows = []
    for index, when in enumerate(pd.bdate_range("2025-01-02", periods=251)):
        if index == 0:
            signals, state, count = (SavedStrategySignal("match", 1, "原進場") for _ in range(2)), "match", 2
        elif index == 1:
            signals, state, count = (SavedStrategySignal("unknown", 0, "原資料缺件"), SavedStrategySignal("match", 1, "原進場")), "unknown", 1
        else:
            signals, state, count = (SavedStrategySignal("no_match", 0, "原規則未發進場") for _ in range(2)), "no_match", 0
        rows.append(SavedSignalComparisonDay(when.date().isoformat(), tuple(signals), state, count, count))
    return SavedSignalComparison("available", strategies=strategies, rows=tuple(rows), stock_code="2330",
        requested_start=rows[0].data_date, requested_end=rows[-1].data_date, input_sha256="a" * 64)


def publish(widget, result):
    widget.set_selection(selection())
    widget._loaded({"generation": widget._generation, "result": result})


def test_daily_matrix_unknown_family_count_pagination_and_entry_filter(widget):
    publish(widget, model())
    assert widget.table.isVisible() and widget.table.rowCount() == 100
    assert widget.table.item(0, 1).text() == "進場意圖"
    assert widget.table.item(0, 4).text() == "2／2"
    assert widget.table.item(1, 1).text() == "未知"
    assert widget.table.item(1, 1).toolTip() == "原資料缺件"
    assert "2策略／2家族" in widget.status.text() and "1日未知" in widget.status.text()
    assert "共同判定" in widget.status.text()
    assert "策略0：1次" in widget.detail_status.text() and "策略1：2次" in widget.detail_status.text()
    widget.next_button.click()
    assert widget.table.item(0, 0).text() == model().rows[100].data_date
    widget.next_button.click()
    assert widget.table.rowCount() == 51 and not widget.next_button.isEnabled()
    widget.entry_only.setChecked(True)
    assert widget.table.rowCount() == 2 and not widget.previous_button.isEnabled()
    assert widget.table.item(1, 3).text() == "未知"


def test_exact_selection_preserves_result_but_metadata_change_clears_it_and_late_payload(widget):
    result = model()
    publish(widget, result)
    generation = widget._generation
    widget.set_selection(selection())
    assert widget.result is result
    changed = (replace(selection()[0], run_name="changed"), selection()[1])
    widget.set_selection(changed)
    assert widget.result is None and not widget.table.isVisible()
    widget._loaded({"generation": generation, "result": result})
    assert widget.result is None


def test_failed_source_clears_visible_previous_rows(widget):
    publish(widget, model())
    widget._loaded({"generation": widget._generation, "result": SavedSignalComparison("unavailable", ("原來源缺件",))})
    assert "原來源缺件" in widget.status.text()
    assert not widget.table.isVisible()


def test_rules_button_uses_exact_selected_saved_source(widget, monkeypatch):
    result = model()
    class Rule:
        rule_card = object()
    sources = tuple(Rule() for _ in range(2))
    strategies = tuple(replace(strategy, rule_source=source) for strategy, source in zip(result.strategies, sources))
    result = replace(result, strategies=strategies)
    seen = []
    class Dialog:
        def __init__(self, card, parent, *, result):
            seen.append((card, result))
        def exec(self):
            return 0
    monkeypatch.setattr("ui_qt.widgets.strategy_rule_card_dialog.StrategyRuleCardDialog", Dialog)
    publish(widget, result)
    widget.strategy_combo.setCurrentIndex(1)
    widget.rules_button.click()
    assert seen == [(sources[1].rule_card, sources[1])]


@pytest.mark.parametrize("shutdown", [False, True])
def test_async_selection_or_close_does_not_publish_late_result(widget, monkeypatch, shutdown):
    started, released = Event(), Event()
    def slow(*args, **kwargs):
        started.set()
        assert released.wait(5)
        return model()
    monkeypatch.setattr("ui_qt.widgets.saved_strategy_signal_compare_widget.read_saved_strategy_signal_comparison", slow)
    widget.set_selection(selection())
    widget.compare_button.click()
    try:
        wait(started.is_set)
        if shutdown:
            widget.begin_shutdown()
        else:
            widget.set_selection((replace(selection()[0], run_id="new-selection"), selection()[1]))
    finally:
        released.set()
    wait(lambda: widget._worker is None)
    assert widget.result is None and not widget.table.isVisible()
