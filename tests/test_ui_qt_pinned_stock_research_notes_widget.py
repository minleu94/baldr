"""F07 個股筆記 UI 生命週期測試；來源資格沿用真實 exact reader。"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from threading import Event, get_ident
from typing import Any, Callable

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from app_module.daily_market_technical_universe_price_bookmark_v1 import (
    DailyMarketTechnicalUniversePriceBookmarkStateV1,
    DailyMarketTechnicalUniversePriceBookmarkV1,
    create_daily_market_technical_universe_price_bookmark_v1,
    read_daily_market_technical_universe_price_bookmark_v1,
)
from app_module.daily_market_technical_universe_v4_store import (
    DAILY_MARKET_TECHNICAL_UNIVERSE_V4_STORE_DIRECTORY,
)
from app_module.pinned_stock_research_notes import (
    PinnedStockResearchNote,
    PinnedStockResearchSource,
    verify_pinned_stock_research_source,
)
from app_module.personal_data_paths import to_internal_io_path
from tests.test_daily_market_technical_universe_price_query_v1 import (
    _open_session,
    exact_price_store,
)
import ui_qt.widgets.pinned_stock_research_notes_widget as pinned_notes_widget_module
from ui_qt.widgets.pinned_stock_research_notes_widget import (
    PinnedStockResearchNotesWidget,
)
from ui_qt.workers.task_worker import request_cooperative_task_worker_shutdown


def app() -> QApplication:
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication(sys.argv)
    return instance


def _wait_until(
    application: QApplication,
    predicate: Callable[[], bool],
    *,
    timeout_ms: int = 5000,
    diagnostic: Callable[[], str] | None = None,
) -> None:
    deadline = time.monotonic() + timeout_ms / 1000
    while True:
        application.processEvents()
        if predicate():
            application.processEvents()
            return
        if time.monotonic() >= deadline:
            detail = f"；狀態：{diagnostic()}" if diagnostic else ""
            raise AssertionError(f"Qt 工作未在固定期限內完成{detail}")
        # 讓背景來源核對取得 Python 執行緒時間，原固定五秒界線不變。
        time.sleep(0.005)


def _diagnostic(widget: PinnedStockResearchNotesWidget) -> str:
    job = widget._active_job or {}
    outcome = widget._active_outcome
    return (
        f"busy={widget.is_busy()}；job={job.get('kind', '無')}；"
        f"outcome={outcome[0] if outcome else '無'}；"
        f"native_finished={widget._active_native_finished}；"
        f"status={widget.status_label.text()}"
    )


def _bookmark_for(exact_price_store: dict[str, Any], stock_code: str):
    session = _open_session(exact_price_store)
    query = session.create_query(unknown_price_policy="include")
    result = session.execute(query)
    page = result.read_page(result.create_page_request(0, page_size=4))
    return create_daily_market_technical_universe_price_bookmark_v1(
        query,
        page,
        stock_code,
        scroll_position=13,
    )


def _source(bookmark: DailyMarketTechnicalUniversePriceBookmarkV1):
    return PinnedStockResearchSource(bookmark_json=bookmark.to_json())


class _FakePinnedNoteService:
    def __init__(
        self,
        *,
        get_started: Event | None = None,
        get_release: Event | None = None,
        verify_started: Event | None = None,
        verify_release: Event | None = None,
        verify_cancel_observed: Event | None = None,
        save_started: Event | None = None,
        save_release: Event | None = None,
    ):
        self.notes: dict[str, PinnedStockResearchNote] = {}
        self.get_started = get_started
        self.get_release = get_release
        self.verify_started = verify_started
        self.verify_release = verify_release
        self.verify_cancel_observed = verify_cancel_observed
        self.save_started = save_started
        self.save_release = save_release
        self.list_calls: list[tuple[str, int]] = []
        self.get_calls: list[tuple[str, int]] = []
        self.verify_calls: list[tuple[str, int]] = []
        self.verify_callbacks: list[Callable[[], bool] | None] = []
        self.save_calls: list[tuple[PinnedStockResearchSource, str, str, str | None, int]] = []

    def list_notes(self, *, stock_code: str = "") -> tuple[PinnedStockResearchNote, ...]:
        self.list_calls.append((stock_code, get_ident()))
        return tuple(
            note for note in self.notes.values() if note.source.stock_code == stock_code
        )

    def get_note(self, revision_id: str) -> PinnedStockResearchNote:
        self.get_calls.append((revision_id, get_ident()))
        if self.get_started is not None:
            self.get_started.set()
        if self.get_release is not None:
            self.get_release.wait(5)
        return self.notes[revision_id]

    def verify_source(
        self,
        note: PinnedStockResearchNote,
        *,
        cancel_callback: Callable[[], bool] | None = None,
    ) -> DailyMarketTechnicalUniversePriceBookmarkStateV1:
        self.verify_calls.append((note.revision_id, get_ident()))
        self.verify_callbacks.append(cancel_callback)
        if self.verify_started is not None:
            self.verify_started.set()
        while self.verify_release is not None and not self.verify_release.wait(0.01):
            if cancel_callback is not None and cancel_callback():
                if self.verify_cancel_observed is not None:
                    self.verify_cancel_observed.set()
                raise InterruptedError("原價格版本核對已取消")
        if cancel_callback is not None and cancel_callback():
            if self.verify_cancel_observed is not None:
                self.verify_cancel_observed.set()
            raise InterruptedError("原價格版本核對已取消")
        return read_daily_market_technical_universe_price_bookmark_v1(
            note.source.bookmark_json
        )

    def save(
        self,
        source: PinnedStockResearchSource,
        text: str,
        *,
        revision_id: str,
        revision_of: str | None = None,
    ) -> PinnedStockResearchNote:
        self.save_calls.append((source, text, revision_id, revision_of, get_ident()))
        verify_pinned_stock_research_source(source.bookmark_json)
        if self.save_started is not None:
            self.save_started.set()
        if self.save_release is not None:
            self.save_release.wait(5)
        note = PinnedStockResearchNote(
            revision_id=revision_id,
            source=source,
            text=text,
            revision_of=revision_of,
            recorded_at="2026-10-18T10:30:00+00:00",
        )
        self.notes[revision_id] = note
        return note


def _wait_for_source(
    application: QApplication,
    widget: PinnedStockResearchNotesWidget,
) -> None:
    _wait_until(
        application,
        lambda: not widget.is_busy() and widget._verified_source is not None,
        diagnostic=lambda: _diagnostic(widget),
    )


def test_widget_saves_reads_opens_exact_source_and_appends_direct_revision(
    exact_price_store: dict[str, Any],
) -> None:
    application = app()
    bookmark = _bookmark_for(exact_price_store, "S0001")
    service = _FakePinnedNoteService()
    widget = PinnedStockResearchNotesWidget(service)  # type: ignore[arg-type]
    widget.set_source(bookmark)
    _wait_for_source(application, widget)

    assert "股票：S0001" in widget.source_label.text()
    expected_data_date = bookmark.selected.observation_date or "未知"
    expected_research_date = bookmark.selected.query.source.decision_date.isoformat()
    assert f"行情觀測日：{expected_data_date}" in widget.source_label.text()
    assert f"原研究日：{expected_research_date}" in widget.source_label.text()
    assert bookmark.bookmark_identity_sha256 in widget.source_label.toolTip()
    assert widget.saved_text.isReadOnly()

    widget.editor.setPlainText("保存時保留原字與精確價格版本")
    assert widget.save_button.isEnabled()
    widget.save_button.click()
    _wait_until(
        application,
        lambda: not widget.is_busy() and widget.revisions.count() == 1,
        diagnostic=lambda: _diagnostic(widget),
    )
    first = next(iter(service.notes.values()))
    assert service.save_calls[0][0] == _source(bookmark)
    assert service.save_calls[0][1] == "保存時保留原字與精確價格版本"
    assert service.save_calls[0][3] is None
    assert service.save_calls[0][4] != get_ident()
    assert widget.revisions.currentIndex() == -1
    assert not widget.read_button.isEnabled()

    widget.revisions.setCurrentIndex(
        widget.revisions.findData(first.revision_id, Qt.ItemDataRole.UserRole)
    )
    widget.read_button.click()
    _wait_until(
        application,
        lambda: not widget.is_busy() and widget.saved_text.toPlainText() == first.text,
        diagnostic=lambda: _diagnostic(widget),
    )
    assert widget.open_source_button.isEnabled()
    assert widget.revise_button.isEnabled()
    assert f"實際保存時間 {first.recorded_at}" in widget.status_label.text()

    opened: list[DailyMarketTechnicalUniversePriceBookmarkStateV1] = []
    widget.open_source_requested.connect(opened.append)
    widget.open_source_button.click()
    _wait_until(
        application,
        lambda: not widget.is_busy() and len(opened) == 1,
        diagnostic=lambda: _diagnostic(widget),
    )
    assert isinstance(opened[0], DailyMarketTechnicalUniversePriceBookmarkStateV1)
    assert opened[0].bookmark.to_json() == first.source.bookmark_json
    assert opened[0].bookmark.bookmark_identity_sha256 == bookmark.bookmark_identity_sha256

    widget.revise_button.click()
    assert widget.editor.toPlainText() == first.text
    widget.editor.appendPlainText("追加一項待下次核對的觀察")
    widget.save_button.click()
    _wait_until(
        application,
        lambda: not widget.is_busy() and widget.revisions.count() == 2,
        diagnostic=lambda: _diagnostic(widget),
    )
    second = next(note for note in service.notes.values() if note.revision_id != first.revision_id)
    assert second.revision_of == first.revision_id
    assert second.source.bookmark_json == first.source.bookmark_json
    assert second.text == first.text + "\n追加一項待下次核對的觀察"
    assert all(thread_id != get_ident() for _, thread_id in service.list_calls)
    assert all(thread_id != get_ident() for _, thread_id in service.get_calls)
    assert all(thread_id != get_ident() for _, thread_id in service.verify_calls)
    assert service.verify_callbacks
    assert all(callback is not None for callback in service.verify_callbacks)
    widget.close()
    application.processEvents()


def test_stock_switch_discards_late_read_and_never_carries_revision_parent(
    exact_price_store: dict[str, Any],
) -> None:
    application = app()
    bookmark_a = _bookmark_for(exact_price_store, "S0001")
    bookmark_b = _bookmark_for(exact_price_store, "S0002")
    get_started, get_release = Event(), Event()
    service = _FakePinnedNoteService(get_started=get_started, get_release=get_release)
    note_a = PinnedStockResearchNote(
        revision_id="note-a",
        source=_source(bookmark_a),
        text="甲股原文",
        recorded_at="2026-10-18T10:30:00+00:00",
    )
    note_b = PinnedStockResearchNote(
        revision_id="note-b",
        source=_source(bookmark_b),
        text="乙股原文",
        recorded_at="2026-10-18T10:31:00+00:00",
    )
    service.notes = {note_a.revision_id: note_a, note_b.revision_id: note_b}
    widget = PinnedStockResearchNotesWidget(service)  # type: ignore[arg-type]
    widget.set_source(bookmark_a)
    _wait_for_source(application, widget)
    widget.revisions.setCurrentIndex(
        widget.revisions.findData(note_a.revision_id, Qt.ItemDataRole.UserRole)
    )
    widget.read_button.click()
    _wait_until(application, get_started.is_set, timeout_ms=5000)

    old_worker = widget._active_worker
    assert old_worker is not None
    get_release.set()
    assert old_worker.wait(5000)
    widget.set_source(bookmark_b)
    assert not widget.saved_text.toPlainText()
    assert widget.revisions.currentIndex() == -1
    assert not widget.open_source_button.isEnabled()
    _wait_until(
        application,
        lambda: not widget.is_busy()
        and widget._verified_source is not None
        and widget._verified_source.identity_sha256 == bookmark_b.bookmark_identity_sha256,
        diagnostic=lambda: _diagnostic(widget),
    )
    assert widget.revisions.count() == 1
    assert widget.revisions.itemData(0, Qt.ItemDataRole.UserRole) == note_b.revision_id
    assert widget.revisions.currentIndex() == -1
    assert not widget.saved_text.toPlainText()
    assert not widget.revise_button.isEnabled()
    assert all(stock_code == "S0002" for stock_code, _ in service.list_calls[-1:])

    widget.close()
    application.processEvents()


def test_cancel_during_source_listing_reaches_verifier_and_discards_result(
    exact_price_store: dict[str, Any],
    monkeypatch: Any,
) -> None:
    application = app()
    bookmark = _bookmark_for(exact_price_store, "S0001")
    verify_started, verify_release, cancel_observed = Event(), Event(), Event()

    def slow_verifier(
        selected_bookmark: DailyMarketTechnicalUniversePriceBookmarkV1,
        *,
        cancel_callback: Callable[[], bool] | None = None,
    ) -> PinnedStockResearchSource:
        assert cancel_callback is not None
        verify_started.set()
        while not verify_release.wait(0.01):
            if cancel_callback():
                cancel_observed.set()
                raise InterruptedError("原價格版本核對已取消")
        if cancel_callback():
            cancel_observed.set()
            raise InterruptedError("原價格版本核對已取消")
        return _source(selected_bookmark)

    monkeypatch.setattr(
        pinned_notes_widget_module,
        "verify_pinned_stock_research_source",
        slow_verifier,
    )
    service = _FakePinnedNoteService()
    widget = PinnedStockResearchNotesWidget(service)  # type: ignore[arg-type]
    results: list[Any] = []
    errors: list[str] = []
    native_finished: list[bool] = []
    worker = None
    widget.set_source(bookmark)
    try:
        _wait_until(application, verify_started.is_set, diagnostic=lambda: _diagnostic(widget))
        worker = widget._active_worker
        assert worker is not None
        worker.finished.connect(results.append)
        worker.native_thread_finished.connect(lambda: native_finished.append(True))
        worker.error.connect(errors.append)
        widget.request_cancel()
        _wait_until(
            application,
            lambda: not widget.is_busy(),
            diagnostic=lambda: _diagnostic(widget),
        )
        assert native_finished == [True]
        assert cancel_observed.is_set()
        assert results == []
        assert errors
        assert "原價格版本核對已取消" in errors[0]
        assert widget._verified_source is None
        assert widget._source_error == ""
        assert widget.revisions.count() == 0
        assert service.list_calls == []
    finally:
        verify_release.set()
        widget.shutdown()
        if widget.is_busy():
            _wait_until(
                application,
                lambda: not widget.is_busy(),
                diagnostic=lambda: _diagnostic(widget),
            )
        widget.close()
        application.processEvents()


def test_cancel_during_explicit_note_source_read_reaches_verifier_without_emitting_state(
    exact_price_store: dict[str, Any],
) -> None:
    application = app()
    bookmark = _bookmark_for(exact_price_store, "S0001")
    verify_started, verify_release, cancel_observed = Event(), Event(), Event()
    note = PinnedStockResearchNote(
        revision_id="slow-source-note",
        source=_source(bookmark),
        text="原筆記需在來源核對完成後才能回用",
        recorded_at="2026-10-18T10:30:00+00:00",
    )
    service = _FakePinnedNoteService(
        verify_started=verify_started,
        verify_release=verify_release,
        verify_cancel_observed=cancel_observed,
    )
    service.notes[note.revision_id] = note
    widget = PinnedStockResearchNotesWidget(service)  # type: ignore[arg-type]
    results: list[Any] = []
    errors: list[str] = []
    native_finished: list[bool] = []
    opened: list[DailyMarketTechnicalUniversePriceBookmarkStateV1] = []
    widget.open_source_requested.connect(opened.append)
    worker = None
    widget.set_source(bookmark)
    try:
        _wait_for_source(application, widget)
        widget.revisions.setCurrentIndex(
            widget.revisions.findData(note.revision_id, Qt.ItemDataRole.UserRole)
        )
        widget.read_button.click()
        _wait_until(application, verify_started.is_set, diagnostic=lambda: _diagnostic(widget))
        worker = widget._active_worker
        assert worker is not None
        worker.finished.connect(results.append)
        worker.native_thread_finished.connect(lambda: native_finished.append(True))
        worker.error.connect(errors.append)
        widget.clear_source()
        _wait_until(
            application,
            lambda: not widget.is_busy(),
            diagnostic=lambda: _diagnostic(widget),
        )

        assert native_finished == [True]
        assert cancel_observed.is_set()
        assert service.verify_callbacks[-1] is not None
        assert results == []
        assert errors
        assert "原價格版本核對已取消" in errors[0]
        assert opened == []
        assert widget._verified_source is None
        assert widget._loaded_note is None
        assert widget._loaded_source_state is None
        assert not widget.saved_text.toPlainText()
        assert widget.revisions.count() == 0
    finally:
        verify_release.set()
        widget.shutdown()
        if widget.is_busy():
            _wait_until(
                application,
                lambda: not widget.is_busy(),
                diagnostic=lambda: _diagnostic(widget),
            )
        widget.close()
        application.processEvents()


def test_missing_original_keeps_saved_text_but_blocks_source_open_and_revision(
    exact_price_store: dict[str, Any],
) -> None:
    application = app()
    bookmark = _bookmark_for(exact_price_store, "S0001")
    service = _FakePinnedNoteService()
    note = PinnedStockResearchNote(
        revision_id="missing-original",
        source=_source(bookmark),
        text="原件移除後仍保留的使用者筆記",
        recorded_at="2026-10-18T10:30:00+00:00",
    )
    service.notes[note.revision_id] = note
    widget = PinnedStockResearchNotesWidget(service)  # type: ignore[arg-type]
    plan = exact_price_store["plan"]
    plan_path = (
        Path(to_internal_io_path(exact_price_store["store_root"]))
        / DAILY_MARKET_TECHNICAL_UNIVERSE_V4_STORE_DIRECTORY
        / "generations"
        / plan.generation_identity_sha256
        / "plan.json"
    )
    original_plan_bytes = plan_path.read_bytes()
    try:
        widget.set_source(bookmark)
        _wait_for_source(application, widget)
        assert widget._verified_source is not None
        widget.revisions.setCurrentIndex(
            widget.revisions.findData(note.revision_id, Qt.ItemDataRole.UserRole)
        )
        plan_path.unlink()
        widget.read_button.click()
        _wait_until(
            application,
            lambda: not widget.is_busy()
            and widget.saved_text.toPlainText() == note.text
            and "原件核對失敗" in widget.status_label.text(),
            diagnostic=lambda: _diagnostic(widget),
        )
        assert widget._loaded_source_error
        assert widget._loaded_source_error in widget.status_label.text()
        assert widget._loaded_source_error == "technical_snapshot_v4_file_type_rejected"
        assert not widget.open_source_button.isEnabled()
        assert not widget.revise_button.isEnabled()
    finally:
        plan_path.write_bytes(original_plan_bytes)
        widget.close()
        application.processEvents()
    assert plan_path.read_bytes() == original_plan_bytes


def test_open_freshly_rechecks_original_and_keeps_text_when_it_disappears(
    exact_price_store: dict[str, Any],
) -> None:
    application = app()
    bookmark = _bookmark_for(exact_price_store, "S0001")
    service = _FakePinnedNoteService()
    note = PinnedStockResearchNote(
        revision_id="open-missing-original",
        source=_source(bookmark),
        text="重新核對失敗時仍保留的原文",
        recorded_at="2026-10-18T10:30:00+00:00",
    )
    service.notes[note.revision_id] = note
    widget = PinnedStockResearchNotesWidget(service)  # type: ignore[arg-type]
    plan = exact_price_store["plan"]
    plan_path = (
        Path(to_internal_io_path(exact_price_store["store_root"]))
        / DAILY_MARKET_TECHNICAL_UNIVERSE_V4_STORE_DIRECTORY
        / "generations"
        / plan.generation_identity_sha256
        / "plan.json"
    )
    original_plan_bytes = plan_path.read_bytes()
    opened: list[DailyMarketTechnicalUniversePriceBookmarkStateV1] = []
    widget.open_source_requested.connect(opened.append)
    try:
        widget.set_source(bookmark)
        _wait_for_source(application, widget)
        widget.revisions.setCurrentIndex(
            widget.revisions.findData(note.revision_id, Qt.ItemDataRole.UserRole)
        )
        widget.read_button.click()
        _wait_until(
            application,
            lambda: not widget.is_busy()
            and widget.saved_text.toPlainText() == note.text
            and widget.open_source_button.isEnabled(),
            diagnostic=lambda: _diagnostic(widget),
        )
        assert widget.revise_button.isEnabled()

        plan_path.unlink()
        widget.open_source_button.click()
        _wait_until(
            application,
            lambda: not widget.is_busy() and bool(widget._loaded_source_error),
            diagnostic=lambda: _diagnostic(widget),
        )

        assert opened == []
        assert widget._loaded_note == note
        assert widget.saved_text.toPlainText() == note.text
        assert widget._loaded_source_error == "technical_snapshot_v4_file_type_rejected"
        assert widget._loaded_source_error in widget.status_label.text()
        assert "原價格版本重新核對失敗" in widget.status_label.text()
        assert not widget.open_source_button.isEnabled()
        assert not widget.revise_button.isEnabled()
    finally:
        plan_path.write_bytes(original_plan_bytes)
        widget.close()
        application.processEvents()
    assert plan_path.read_bytes() == original_plan_bytes


def test_without_source_same_stock_notes_remain_readable_but_new_write_is_disabled(
    exact_price_store: dict[str, Any],
) -> None:
    application = app()
    bookmark = _bookmark_for(exact_price_store, "S0001")
    service = _FakePinnedNoteService()
    note = PinnedStockResearchNote(
        revision_id="old-note",
        source=_source(bookmark),
        text="可回訪原文",
        recorded_at="2026-10-18T10:30:00+00:00",
    )
    service.notes[note.revision_id] = note
    widget = PinnedStockResearchNotesWidget(service)  # type: ignore[arg-type]

    widget.set_source(None, stock_code="S0001")
    _wait_until(application, lambda: not widget.is_busy(), diagnostic=lambda: _diagnostic(widget))
    assert widget.revisions.count() == 1
    widget.editor.setPlainText("沒有明選來源的新草稿")
    assert not widget.save_button.isEnabled()
    widget.revisions.setCurrentIndex(
        widget.revisions.findData(note.revision_id, Qt.ItemDataRole.UserRole)
    )
    widget.read_button.click()
    _wait_until(
        application,
        lambda: not widget.is_busy() and widget.saved_text.toPlainText() == note.text,
        diagnostic=lambda: _diagnostic(widget),
    )
    assert widget.open_source_button.isEnabled()
    assert not widget.revise_button.isEnabled()
    assert not widget.save_button.isEnabled()

    previous_list_call_count = len(service.list_calls)
    widget.clear_source()
    assert widget.revisions.count() == 0
    assert not widget.is_busy()
    assert len(service.list_calls) == previous_list_call_count
    assert not widget.save_button.isEnabled()

    widget.close()
    application.processEvents()


def test_shutdown_does_not_cancel_an_already_submitted_journal_write(
    exact_price_store: dict[str, Any],
) -> None:
    application = app()
    bookmark = _bookmark_for(exact_price_store, "S0001")
    save_started, save_release = Event(), Event()
    service = _FakePinnedNoteService(
        save_started=save_started,
        save_release=save_release,
    )
    widget = PinnedStockResearchNotesWidget(service)  # type: ignore[arg-type]
    widget.set_source(bookmark)
    _wait_for_source(application, widget)
    widget.editor.setPlainText("關閉期間已送出的保存")
    worker = None
    try:
        widget.save_button.click()
        _wait_until(application, save_started.is_set, timeout_ms=5000)
        worker = widget._active_worker
        assert worker is not None
        assert widget.has_pending_write()
        widget.close()
        widget.shutdown()
        assert widget.has_pending_write()
        assert not worker.is_cancel_requested()
        remaining = request_cooperative_task_worker_shutdown()
        assert worker in remaining
        assert not worker.is_cancel_requested()
    finally:
        save_release.set()

    _wait_until(application, lambda: not widget.is_busy(), diagnostic=lambda: _diagnostic(widget))
    assert not widget.has_pending_write()
    assert len(service.notes) == 1
    assert "已確認保存筆記" in widget.status_label.text()
    assert service.save_calls[0][4] != get_ident()
    widget.close()
    application.processEvents()
