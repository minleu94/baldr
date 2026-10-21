from __future__ import annotations

import os
import sys
import time
from dataclasses import replace
from typing import cast

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication

from app_module.dtos.portfolio_dtos import JournalEntryDTO
from app_module.decision_outcome_journey import DecisionOutcomeJourney
from app_module.research_timeline_dtos import ResearchTimelineEntry, ResearchTimelineReadResult
from ui_qt.views.research_timeline_view import ResearchTimelineView

_APPLICATION: QApplication | None = None


def _app() -> QApplication:
    global _APPLICATION
    if _APPLICATION is not None:
        return _APPLICATION
    instance = QApplication.instance()
    _APPLICATION = instance if instance is not None else QApplication(sys.argv)
    return _APPLICATION


@pytest.fixture(autouse=True)
def _keep_qt_application_and_drain_deferred_deletes():
    application = _app()
    existing_windows = set(application.topLevelWidgets())
    yield
    owned_windows = [
        widget for widget in application.topLevelWidgets()
        if widget not in existing_windows
    ]
    for widget in owned_windows:
        shutdown = getattr(widget, "begin_shutdown", None)
        if callable(shutdown):
            shutdown()
        close_request = getattr(widget, "request_close", None)
        if callable(close_request):
            close_request()
        workers = set(getattr(widget, "_workers", ()))
        for name in ("_active_worker", "_refresh_worker"):
            worker = getattr(widget, name, None)
            if worker is not None:
                workers.add(worker)
        journey = getattr(widget, "journey_widget", None)
        if journey is not None:
            workers.update(getattr(journey, "_workers", ()))
            worker = getattr(journey, "_active_worker", None)
            if worker is not None:
                workers.add(worker)
        for worker in workers:
            if worker.isRunning():
                worker.cancel(cooperative=True, wait=False)
                assert worker.wait(5000), "測試結束時 TaskWorker 未能自然停止"
    application.processEvents()
    for widget in owned_windows:
        widget.close()
        widget.deleteLater()
    application.processEvents()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    application.processEvents()


def _entry(kind: str, record_id: str, text: str, *, stock: str = "2330", result_id: str = ""):
    reference = JournalEntryDTO(
        journal_id=record_id,
        portfolio_id="default",
        body=text,
        stock_code=stock,
        created_at="2026-10-19T10:00:00+00:00",
        revision_id=record_id,
    )
    return ResearchTimelineEntry(
        kind=kind,
        record_id=record_id,
        recorded_at="2026-10-19T10:00:00+00:00",
        text=text,
        reference=reference,
        stock_code=stock,
        data_date="2026-10-18",
        source_identity="saved-source-identity",
        result_id=result_id,
        revision_of="prior-note" if kind != "manual" else "",
    )


class _Reader:
    def __init__(self, result: ResearchTimelineReadResult):
        self.result = result
        self.calls = 0

    def read(self, cancel_callback=None):
        self.calls += 1
        if cancel_callback is not None and cancel_callback():
            return ResearchTimelineReadResult((), ("已取消",))
        return self.result


class _JourneyReader:
    def __init__(self) -> None:
        self.requested_result_ids: list[str] = []

    def build(self, result_id: str, *, query_boundary=None):
        self.requested_result_ids.append(result_id)
        return cast(DecisionOutcomeJourney, object())


def _wait(application: QApplication, predicate, timeout_ms: int = 3000) -> None:
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        application.processEvents()
        if predicate():
            application.processEvents()
            return
        time.sleep(0.01)
    raise AssertionError("timeline UI did not reach the expected state")


def _timeline_idle(view: ResearchTimelineView) -> bool:
    journey = view.journey_widget
    return (
        not view.is_busy()
        and view._active_worker is None
        and (journey is None or journey._active_worker is None)
    )


def test_view_preserves_full_original_and_emits_only_selected_saved_entry():
    application = _app()
    original = "原始保存判斷\n完整第二行，必須原樣保留。"
    report = _entry("report", "report-1", original, result_id="explicit-result")
    manual = _entry("manual", "manual-1", "一般筆記")
    view = ResearchTimelineView(
        _Reader(ResearchTimelineReadResult((report, manual))),
    )
    _wait(application, lambda: view._entries == (report, manual) and _timeline_idle(view))

    assert view.original_text.toPlainText() == original
    assert "來源資料日 2026-10-18" in view.detail_label.text()
    assert "前版 prior-note" in view.detail_label.text()
    assert view.open_original_button.isEnabled()
    emitted: list[object] = []
    view.openOriginalRequested.connect(emitted.append)
    view.open_original_button.click()
    assert emitted == [report]

    view.source_filter.setCurrentIndex(view.source_filter.findData("manual"))
    assert view.entries_table.rowCount() == 1
    assert view.original_text.toPlainText() == "一般筆記"
    assert not view.open_original_button.isEnabled()
    view.open_original_button.click()
    assert emitted == [report]

    view.source_filter.setCurrentIndex(view.source_filter.findData("all"))
    view.stock_filter.setText("2454")
    assert view.entries_table.rowCount() == 0
    assert not view.open_original_button.isEnabled()
    view.close()


def test_late_generation_cannot_replace_newer_timeline_result():
    application = _app()
    current = _entry("theme", "current", "目前原文")
    stale = _entry("report", "stale", "較晚抵達的舊原文")
    view = ResearchTimelineView(_Reader(ResearchTimelineReadResult((current,))))
    _wait(application, lambda: view._entries == (current,) and _timeline_idle(view))
    view._generation += 1
    current_generation = view._generation

    view._receive(current_generation - 1, ResearchTimelineReadResult((stale,)))

    assert view._entries == (current,)
    assert view.original_text.toPlainText() == "目前原文"
    view.close()


def test_exact_forward_identity_is_required_and_unlinked_note_stays_unlinked():
    application = _app()
    entry = _entry("price", "price-1", "價格原文", result_id="")
    journey_reader = _JourneyReader()
    view = ResearchTimelineView(
        _Reader(ResearchTimelineReadResult((entry,))),
        journey_service=journey_reader,
    )
    _wait(application, lambda: view._entries == (entry,) and _timeline_idle(view))

    assert "未連結保存的推薦結果" in view.status_label.text()
    assert view.journey_widget is not None
    assert view.journey_widget.context.result_id == ""
    assert view.journey_widget.context.stock_code == "2330"
    assert view.journey_widget.is_busy() is False
    assert view.journey_widget.continuity_controls is None
    assert view.journey_widget.isHidden()
    assert not view.journey_placeholder.isHidden()
    assert journey_reader.requested_result_ids == []
    view.request_close()
    view.close()


def test_forward_reader_receives_only_the_entry_exact_result_id():
    application = _app()
    entry = _entry("report", "report-2", "保存報告原文", result_id="exact-result-42")
    journey_reader = _JourneyReader()
    view = ResearchTimelineView(
        _Reader(ResearchTimelineReadResult((entry,))),
        journey_service=journey_reader,
    )
    _wait(application, lambda: view._entries == (entry,))
    _wait(application, lambda: journey_reader.requested_result_ids == ["exact-result-42"])
    _wait(application, lambda: _timeline_idle(view))

    assert journey_reader.requested_result_ids == ["exact-result-42"]
    assert view.journey_widget is not None
    assert view.journey_widget.context.result_id == "exact-result-42"
    view.request_close()
    view.close()


def test_auto_refresh_can_be_disabled_and_ready_emits_the_same_read_result():
    _app()
    entry = _entry("manual", "manual-no-auto", "既有原文")
    result = ResearchTimelineReadResult((entry,))
    reader = _Reader(result)
    view = ResearchTimelineView(reader, auto_refresh=False)
    emitted: list[object] = []
    view.resultReady.connect(emitted.append)

    assert reader.calls == 0
    assert view.last_result is None

    view._receive(view._generation, result)

    assert reader.calls == 0
    assert emitted == [result]
    assert emitted[0] is result
    assert view.last_result is result
    view.close()


def test_select_entry_requires_exact_current_object_and_clears_filters():
    _app()
    target = _entry("report", "same-record", "本次保存判斷")
    other = _entry("manual", "other-record", "另一筆研究")
    result = ResearchTimelineReadResult((target, other))
    view = ResearchTimelineView(_Reader(result), auto_refresh=False)
    view._receive(view._generation, result)

    equivalent_but_stale_object = replace(target)
    assert equivalent_but_stale_object == target
    assert equivalent_but_stale_object is not target
    assert not view.select_entry(equivalent_but_stale_object)

    view.source_filter.setCurrentIndex(view.source_filter.findData("theme"))
    view.stock_filter.setText("2454")
    assert view.entries_table.rowCount() == 0

    assert view.select_entry(target)
    assert view.source_filter.currentData() == "all"
    assert view.stock_filter.text() == ""
    assert view.entries_table.rowCount() == 2
    assert view._selected is target
    assert view.original_text.toPlainText() == "本次保存判斷"
    view.close()


def test_refresh_result_rejects_entry_from_previous_result_even_with_same_id():
    _app()
    old_entry = _entry("report", "same-record", "舊保存判斷")
    first_result = ResearchTimelineReadResult((old_entry,))
    view = ResearchTimelineView(_Reader(first_result), auto_refresh=False)
    view._receive(view._generation, first_result)

    new_entry = _entry("report", "same-record", "新修訂判斷")
    refreshed_result = ResearchTimelineReadResult((new_entry,))
    view._generation += 1
    view._receive(view._generation, refreshed_result)

    assert view.last_result is refreshed_result
    assert view._entries == (new_entry,)
    assert not view.select_entry(old_entry)
    assert view.select_entry(new_entry)
    assert view._selected is new_entry
    assert view.original_text.toPlainText() == "新修訂判斷"
    view.close()


def test_current_error_and_cancel_notify_home_while_preserving_timeline_selection():
    _app()
    entry = _entry("report", "preserved", "仍可查看的原文")
    view = ResearchTimelineView(
        _Reader(ResearchTimelineReadResult((entry,))), auto_refresh=False
    )
    view._receive(view._generation, ResearchTimelineReadResult((entry,)))
    emitted: list[str] = []
    view.readUnavailable.connect(emitted.append)

    view._receive_error(view._generation, "reader unavailable")
    assert emitted == ["讀取失敗；保留原畫面：reader unavailable"]
    assert view.status_label.text() == emitted[-1]
    assert view._entries == (entry,)
    assert view._selected is entry
    assert view.original_text.toPlainText() == "仍可查看的原文"

    view._receive_cancelled(view._generation)
    assert emitted[-1] == "讀取已安全取消；保留目前可用紀錄。"
    assert len(emitted) == 2
    assert view._entries == (entry,)
    assert view._selected is entry
    assert view.original_text.toPlainText() == "仍可查看的原文"
    view.close()


def test_late_error_and_cancel_do_not_notify_home_or_replace_timeline():
    _app()
    entry = _entry("theme", "newer", "較新的原文")
    view = ResearchTimelineView(
        _Reader(ResearchTimelineReadResult((entry,))), auto_refresh=False
    )
    view._receive(view._generation, ResearchTimelineReadResult((entry,)))
    emitted: list[str] = []
    view.readUnavailable.connect(emitted.append)
    stale_generation = view._generation
    view._generation += 1

    view._receive_error(stale_generation, "late error")
    view._receive_cancelled(stale_generation)

    assert emitted == []
    assert view._entries == (entry,)
    assert view._selected is entry
    assert view.original_text.toPlainText() == "較新的原文"
    view.close()


def test_closing_error_and_cancel_do_not_notify_home():
    _app()
    view = ResearchTimelineView(_Reader(ResearchTimelineReadResult(())), auto_refresh=False)
    emitted: list[str] = []
    view.readUnavailable.connect(emitted.append)
    generation = view._generation
    view.request_close()

    view._receive_error(generation, "shutdown error")
    view._receive_cancelled(generation)

    assert emitted == []
    view.close()
