"""BacktestView 中歷史績效卡的唯讀接線測試。"""

from __future__ import annotations

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from dataclasses import replace
from pathlib import Path
from threading import Event
import time

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app_module.research_history_lookup import (
    ResearchHistoryLookup,
    ResearchHistoryReadBudget,
)
from app_module.strategy_historical_performance_read_service import (
    StrategyHistoricalPerformanceReadService,
)
from ui_qt.widgets.historical_performance_widget import HistoricalPerformanceWidget
from tests.test_baldr_b07_research_history import (
    executed_case,
    fixed_sources,
    inventory,
)
from ui_qt.views.backtest_view import BacktestView


def app():
    return QApplication.instance() or QApplication([])


def wait_until(predicate):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        app().processEvents()
        if predicate():
            return
        time.sleep(0.01)
    pytest.fail("歷史卡 worker 未在既有 10 秒界線內結束")


def lookup_for(registry):
    return ResearchHistoryLookup(
        registry=registry,
        read_budget=ResearchHistoryReadBudget(
            max_artifact_bytes=64 * 1024 * 1024,
            max_total_bytes=256 * 1024 * 1024,
        ),
    )


def view_for(lookup, reader=None):
    view = BacktestView(backtest_service=None, config=None)
    panel = view.result_panel
    history = panel.research_history_lookup
    history.lookup = lookup
    history.performance_reader = reader or StrategyHistoricalPerformanceReadService(lookup)
    panel.research_history_group.setChecked(True)
    view.resize(1440, 1000)
    view.show()
    view.ensurePolished()
    app().processEvents()
    for widget in (view, view.backtest_splitter, panel, panel.research_history_group, history):
        layout = widget.layout()
        if layout is not None:
            layout.activate()
    app().processEvents()
    history.refresh_entries()
    wait_until(lambda: history._worker is None)
    app().processEvents()

    button = history.show_history_card_button
    splitter = view.backtest_splitter
    ancestors = []
    current = button
    while current is not None:
        ancestors.append(current)
        if current is view:
            break
        current = current.parentWidget()

    mouse_point = button.rect().center()
    geometry_rows = []
    geometry_ready = button.isVisible() and button.width() > 0 and button.height() > 0
    for ancestor in ancestors:
        local_point = button.mapTo(ancestor, mouse_point)
        bounds = ancestor.rect() if ancestor is button else ancestor.contentsRect()
        inside = bounds.contains(local_point)
        geometry_rows.append(
            f"{type(ancestor).__name__}"
            f"(visible={ancestor.isVisible()},enabled={ancestor.isEnabled()},"
            f"rect={ancestor.rect().getRect()},contents={ancestor.contentsRect().getRect()},"
            f"mouse_point={local_point.x()},{local_point.y()},inside={inside})"
        )
        geometry_ready = geometry_ready and ancestor.isVisible() and inside
    geometry_ready = geometry_ready and ancestors[-1] is view
    print(
        "HISTORY_CARD_GEOMETRY "
        f"splitter_orientation={splitter.orientation()} sizes={splitter.sizes()} "
        f"group_checked={panel.research_history_group.isChecked()} "
        f"button_visible={button.isVisible()} button_enabled={button.isEnabled()} "
        f"button_rect={button.rect().getRect()} "
        f"ancestor_chain={' > '.join(geometry_rows)}"
    )
    assert geometry_ready, "歷史卡按鈕中心必須位於已顯示祖先的內容範圍內，且 layout 幾何非空。"
    return view, history, panel.history_performance_card


def select_run(history, run_id):
    for row in range(history.entries.count()):
        entry = history.entries.item(row).data(Qt.ItemDataRole.UserRole)
        if entry.run_id == run_id:
            history.entries.setCurrentRow(row)
            return entry
    raise AssertionError(f"Registry entry not found: {run_id}")


def card_payload_is_empty(card):
    return (
        card._identity_label.text() == ""
        and card._metrics_label.text() == ""
        and card._details_label.text() == ""
        and not card._details_button.isVisible()
    )


def test_selected_registry_card_uses_real_writer_taskworker_and_keeps_sources_unchanged(tmp_path, monkeypatch):
    app()
    _, registry, metadata, _, _, _ = executed_case(tmp_path, monkeypatch)
    lookup = lookup_for(registry)
    view, history, card = view_for(lookup)
    assert isinstance(card, HistoricalPerformanceWidget)
    selected = select_run(history, metadata.run_id)
    before = inventory(tmp_path)

    assert selected.source_kind == "registry"
    assert selected.result_supported is True
    assert history.show_history_card_button.isEnabled()
    assert history.open_result.isEnabled()  # 原開啟原結果入口仍保留。
    QTest.mouseClick(history.show_history_card_button, Qt.MouseButton.LeftButton)
    wait_until(lambda: history._worker is None)

    # 此 fixture 每次執行原新版 producer；舊無 schema 的隔離 fixture 另有不升級斷言。
    assert "single_backtest_metrics_contract" in metadata.data_manifest
    assert card._status_label.text() == "已讀回此筆保存結果；原始 analytics schema 已核對，績效資格仍未知。"
    assert f"已完成交易配對（completed pairs）：{metadata.metrics['total_trades']} 對" in card._metrics_label.text()
    assert "資格：unknown" in card._metrics_label.text()
    assert "可比較性：not_assessed" in card._metrics_label.text()
    assert card._details_button.isVisible()
    assert inventory(tmp_path) == before
    view.close()


def test_legacy_selection_never_enables_registry_history_card(tmp_path):
    app()
    _, lookup, *_ = fixed_sources(tmp_path)
    class CountingReader:
        calls = 0
        def read_selected(self, *_args, **_kwargs):
            self.calls += 1
            raise AssertionError("legacy entry must not reach the Registry card reader")

    reader = CountingReader()
    view, history, card = view_for(lookup, reader)
    legacy_row = next(
        row for row in range(history.entries.count())
        if history.entries.item(row).data(Qt.ItemDataRole.UserRole).source_kind != "registry"
    )
    history.entries.setCurrentRow(legacy_row)
    assert not history.show_history_card_button.isEnabled()
    QTest.mouseClick(history.show_history_card_button, Qt.MouseButton.LeftButton)
    assert reader.calls == 0
    assert card_payload_is_empty(card)
    view.close()


def test_blocked_registry_reply_clears_previous_card_identity_and_details(tmp_path, monkeypatch):
    app()
    _, registry, metadata, _, _, _ = executed_case(tmp_path, monkeypatch)
    lookup = lookup_for(registry)
    real_reader = StrategyHistoricalPerformanceReadService(lookup)
    view, history, card = view_for(lookup, real_reader)
    selected = select_run(history, metadata.run_id)
    generation = card.begin_selection(selected)
    assert card.present_card(generation, selected, real_reader.read_selected(selected))
    assert card._identity_label.text()

    class BlockedReader:
        def read_selected(self, _selected, *, check_cancel=None):
            return real_reader.read_selected(
                replace(selected, source_kind="legacy_backtest"),
                check_cancel=check_cancel,
            )

    history.performance_reader = BlockedReader()
    QTest.mouseClick(history.show_history_card_button, Qt.MouseButton.LeftButton)
    wait_until(lambda: history._worker is None)

    assert card._identity_label.text() == ""
    assert card._details_label.text() == ""
    assert "source_kind_unsupported" in card._status_label.text()
    view.close()


def test_reader_exception_clears_all_card_payload(tmp_path, monkeypatch):
    app()
    _, registry, metadata, _, _, _ = executed_case(tmp_path, monkeypatch)
    lookup = lookup_for(registry)
    view, history, card = view_for(lookup)
    select_run(history, metadata.run_id)

    class BrokenReader:
        def read_selected(self, *_args, **_kwargs):
            raise OSError("fixture source refusal")

    history.performance_reader = BrokenReader()
    QTest.mouseClick(history.show_history_card_button, Qt.MouseButton.LeftButton)
    wait_until(lambda: history._worker is None)

    assert card_payload_is_empty(card)
    assert history.status.text() == "歷史卡讀取失敗；沒有套用部分結果。"
    view.close()


def test_apply_exception_clears_all_card_payload(tmp_path, monkeypatch):
    app()
    _, registry, metadata, _, _, _ = executed_case(tmp_path, monkeypatch)
    lookup = lookup_for(registry)
    view, history, card = view_for(lookup)
    select_run(history, metadata.run_id)

    def fail_render(*_args):
        raise RuntimeError("fixture presentation failure")

    monkeypatch.setattr(card, "_render", fail_render)
    QTest.mouseClick(history.show_history_card_button, Qt.MouseButton.LeftButton)
    wait_until(lambda: history._worker is None)

    assert card_payload_is_empty(card)
    assert history.status.text() == "歷史卡讀取失敗；沒有套用部分結果。"
    view.close()


def test_registry_source_drift_returns_no_partial_card(tmp_path, monkeypatch):
    app()
    _, registry, metadata, _, _, _ = executed_case(tmp_path, monkeypatch)
    lookup = lookup_for(registry)
    view, history, card = view_for(lookup)
    select_run(history, metadata.run_id)
    Path(metadata.equity_path).write_bytes(b"tampered source")
    before = inventory(tmp_path)

    QTest.mouseClick(history.show_history_card_button, Qt.MouseButton.LeftButton)
    wait_until(lambda: history._worker is None)

    assert card._identity_label.text() == ""
    assert card._details_label.text() == ""
    assert "registry_integrity_rejected" in card._status_label.text()
    assert inventory(tmp_path) == before
    view.close()


@pytest.mark.parametrize(
    "action",
    ("selection", "cancel", "widget_close", "new_execution", "parent_close"),
)
def test_late_card_reply_is_not_applied_after_invalidation(tmp_path, monkeypatch, action):
    app()
    _, registry, metadata, _, _, _ = executed_case(tmp_path, monkeypatch)
    lookup = lookup_for(registry)
    real_reader = StrategyHistoricalPerformanceReadService(lookup)
    entered, release = Event(), Event()

    class GatedReader:
        def read_selected(self, selected, *, check_cancel=None):
            entered.set()
            if not release.wait(5):
                raise TimeoutError("既有五秒測試閘門逾時")
            # 模擬取消後仍回傳的晚到值；UI token、generation 與 TaskWorker 仍須拒絕套用。
            return real_reader.read_selected(selected)

    view, history, card = view_for(lookup, GatedReader())
    select_run(history, metadata.run_id)
    QTest.mouseClick(history.show_history_card_button, Qt.MouseButton.LeftButton)
    assert entered.wait(5), "worker 未進入既有五秒閘門"

    if action == "selection":
        history.search.setText("no matching saved run")
    elif action == "cancel":
        QTest.mouseClick(history.cancel, Qt.MouseButton.LeftButton)
    elif action == "widget_close":
        history.close()
    elif action == "new_execution":
        view._mark_research_execution_started()
    else:
        assert not view.close()  # 正在工作的 parent 必須保留至 child 自然結束。

    release.set()
    wait_until(lambda: history._worker is None)
    if action == "parent_close":
        assert view.close()

    assert card_payload_is_empty(card)
    view.close()


def test_history_card_is_inside_collapsible_group_and_parent_shutdown_clears_it(tmp_path, monkeypatch):
    app()
    _, registry, metadata, _, _, _ = executed_case(tmp_path, monkeypatch)
    lookup = lookup_for(registry)
    view, history, card = view_for(lookup)
    select_run(history, metadata.run_id)
    QTest.mouseClick(history.show_history_card_button, Qt.MouseButton.LeftButton)
    wait_until(lambda: history._worker is None)
    group = view.result_panel.research_history_group

    assert card.parentWidget() is group
    assert card.isVisible()
    group.setChecked(False)
    app().processEvents()
    assert not card.isVisible()
    group.setChecked(True)
    app().processEvents()
    assert card.isVisible()

    assert view.request_cooperative_shutdown()
    assert card_payload_is_empty(card)
    view.close()

def test_busy_refresh_preserves_card_and_unknown_registry_kind_is_denied(tmp_path, monkeypatch):
    app()
    _, registry, metadata, _, _, _ = executed_case(tmp_path, monkeypatch)
    lookup = lookup_for(registry)
    real_reader = StrategyHistoricalPerformanceReadService(lookup)
    view, history, card = view_for(lookup, real_reader)
    selected = select_run(history, metadata.run_id)
    QTest.mouseClick(history.show_history_card_button, Qt.MouseButton.LeftButton)
    wait_until(lambda: history._worker is None)
    assert card._identity_label.text()

    card_before = (
        card._identity_label.text(),
        card._metrics_label.text(),
        card._details_label.text(),
        card._status_label.text(),
        card._details_button.isVisible(),
        card.generation,
    )
    history.status.setText("既有卡片與待處理讀取保持不變")
    status_before = history.status.text()
    entered, release = Event(), Event()
    cancel_observed = []

    def pending_task(cancel_callback):
        entered.set()
        if not release.wait(5):
            raise TimeoutError("既有五秒測試閘門逾時")
        cancel_observed.append(cancel_callback())
        return None

    history._start(pending_task, lambda _value: None)
    assert entered.wait(5), "受控讀取未進入既有五秒閘門"
    active_worker = history._worker
    request_id = history._request_id
    try:
        history.refresh_entries()
        assert history._worker is active_worker
        assert history._request_id == request_id
        assert history.status.text() == status_before
        assert (
            card._identity_label.text(),
            card._metrics_label.text(),
            card._details_label.text(),
            card._status_label.text(),
            card._details_button.isVisible(),
            card.generation,
        ) == card_before
    finally:
        release.set()
        wait_until(lambda: history._worker is None)

    assert cancel_observed == [False]
    assert history.status.text() == status_before
    assert (
        card._identity_label.text(),
        card._metrics_label.text(),
        card._details_label.text(),
        card._status_label.text(),
        card._details_button.isVisible(),
        card.generation,
    ) == card_before

    class CountingReader:
        calls = 0

        def read_selected(self, *_args, **_kwargs):
            self.calls += 1
            raise AssertionError("未列入 Registry result types 的項目不得進入卡片 reader")

    counting_reader = CountingReader()
    history.performance_reader = counting_reader
    item = history.entries.currentItem()
    assert item is not None
    item.setData(Qt.ItemDataRole.UserRole, replace(selected, run_type="unlisted_registry_result_type"))
    history._selection_changed()
    assert not history.show_history_card_button.isEnabled()
    history.show_history_card()
    assert counting_reader.calls == 0
    assert card_payload_is_empty(card)
    view.close()
