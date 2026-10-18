"""題材研究筆記 widget：來源固定、追加修訂與背景讀回。"""

import os
import sys
import time
from datetime import date
from threading import Event, get_ident
from types import SimpleNamespace
from typing import Callable

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app_module.journal_service import JournalService
from app_module.theme_research_notes import ThemeResearchNote, ThemeResearchNoteService
from app_module.theme_research_snapshot import ThemeResearchSnapshot
from tests.test_theme_research_notes import _journal_service, _snapshot
from ui_qt.widgets.theme_research_notes_widget import ThemeResearchNotesWidget
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
    timeout_ms: int,
    diagnostic: Callable[[], str] | None = None,
) -> None:
    deadline = time.monotonic() + timeout_ms / 1000
    while True:
        application.processEvents()
        if predicate():
            application.processEvents()
            return
        if time.monotonic() >= deadline:
            details = f"；狀態診斷：{diagnostic()}" if diagnostic is not None else ""
            raise AssertionError(f"Qt 狀態未在固定期限內完成{details}")
        QTest.qWait(10)
        time.sleep(0.001)


def _widget_diagnostic(widget: ThemeResearchNotesWidget) -> str:
    job = widget._active_job or {}
    outcome = widget._active_outcome
    outcome_kind = outcome[0] if outcome is not None else "無"
    return (
        f"busy={widget.is_busy()}；job={job.get('kind', '無')}；"
        f"outcome={outcome_kind}；native_finished={widget._active_native_finished}；"
        f"worker_refs={len(widget._workers)}；status={widget.status_label.text()}"
    )


class _FakeNoteService:
    def __init__(
        self,
        *,
        started: Event | None = None,
        release: Event | None = None,
        get_started: Event | None = None,
        get_release: Event | None = None,
    ):
        self.notes: dict[str, ThemeResearchNote] = {}
        self.started = started
        self.release = release
        self.get_started = get_started
        self.get_release = get_release
        self.saved_calls: list[tuple[ThemeResearchSnapshot, str, str, str | None, int]] = []
        self.thread_ids: list[int] = []
        self.fail_save: str | None = None
        self.fail_list: str | None = None

    def list_notes(self) -> tuple[ThemeResearchNote, ...]:
        self.thread_ids.append(get_ident())
        if self.fail_list is not None:
            raise ValueError(self.fail_list)
        return tuple(self.notes.values())

    def get_note(self, revision_id: str) -> ThemeResearchNote:
        self.thread_ids.append(get_ident())
        if self.get_started is not None:
            self.get_started.set()
        if self.get_release is not None:
            self.get_release.wait(5)
        return self.notes[revision_id]

    def save(
        self,
        snapshot: ThemeResearchSnapshot,
        text: str,
        *,
        revision_id: str,
        revision_of: str | None = None,
    ) -> ThemeResearchNote:
        self.thread_ids.append(get_ident())
        self.saved_calls.append((snapshot, text, revision_id, revision_of, get_ident()))
        if self.started is not None:
            self.started.set()
        if self.release is not None:
            self.release.wait(5)
        if self.fail_save is not None:
            raise ValueError(self.fail_save)
        data_date = snapshot.report.data_date.isoformat()
        note = ThemeResearchNote(
            revision_id=revision_id,
            snapshot_identity_sha256=snapshot.identity_sha256,
            text=text,
            data_date=data_date,
            revision_of=revision_of,
            recorded_at="2026-10-18T10:30:00+00:00",
        )
        self.notes[revision_id] = note
        return note


def _theme_note(
    revision_id: str,
    text: str,
    *,
    revision_of: str | None = None,
    identity: str = "f" * 64,
    data_date: str = "2026-10-17",
) -> ThemeResearchNote:
    return ThemeResearchNote(
        revision_id=revision_id,
        snapshot_identity_sha256=identity,
        text=text,
        data_date=data_date,
        revision_of=revision_of,
        recorded_at="2026-10-18T10:30:00+00:00",
    )


def test_widget_pins_unbound_draft_and_inflight_save_to_original_snapshot():
    application = app()
    started = Event()
    release = Event()
    service = _FakeNoteService(started=started, release=release)
    widget = ThemeResearchNotesWidget(service)  # type: ignore[arg-type]
    _wait_until(
        application,
        lambda: not widget.is_busy(),
        timeout_ms=5000,
        diagnostic=lambda: _widget_diagnostic(widget),
    )

    widget.editor.setPlainText("尚未綁來源的草稿")
    assert not widget.save_button.isEnabled()

    snapshot_a = _snapshot("a" * 64)
    snapshot_b = _snapshot("b" * 64)
    widget.set_snapshot(snapshot_a)
    assert not widget.save_button.isEnabled()

    widget.editor.clear()
    widget.editor.setPlainText("只綁定明選來源 A 的研究判斷")
    assert widget.save_button.isEnabled()
    widget.save_button.click()
    try:
        _wait_until(application, started.is_set, timeout_ms=5000)
        widget.set_snapshot(snapshot_b)
        assert snapshot_a.identity_sha256 in widget.status_label.text()
    finally:
        release.set()

    _wait_until(
        application,
        lambda: widget.revisions.findData(
            service.saved_calls[0][2], Qt.ItemDataRole.UserRole
        ) >= 0,
        timeout_ms=5000,
    )
    assert service.saved_calls[0][0] is snapshot_a
    assert service.saved_calls[0][4] != get_ident()
    assert widget.saved_text.isReadOnly()

    opened: list[str] = []
    widget.openSnapshotRequested.connect(opened.append)
    widget.open_source_button.click()
    assert opened == [snapshot_a.identity_sha256]
    assert "保存時間 2026-10-18T10:30:00+00:00" in widget.status_label.text()
    widget.read_button.click()
    _wait_until(
        application,
        lambda: "已讀取唯讀修訂" in widget.status_label.text(),
        timeout_ms=5000,
    )
    assert all(thread_id != get_ident() for thread_id in service.thread_ids)

    widget.close()
    application.processEvents()


def test_widget_appends_revision_and_reopens_exact_note_from_journal(tmp_path):
    application = app()
    journal, paths = _journal_service(tmp_path)
    service = ThemeResearchNoteService(journal)
    snapshot = _snapshot("c" * 64)
    widget = ThemeResearchNotesWidget(service)
    _wait_until(
        application,
        lambda: not widget.is_busy(),
        timeout_ms=5000,
        diagnostic=lambda: _widget_diagnostic(widget),
    )

    widget.set_snapshot(snapshot)
    widget.editor.setPlainText("原始題材觀察")
    widget.save_button.click()
    _wait_until(application, lambda: widget.revisions.count() == 1, timeout_ms=5000)
    first_id = widget.revisions.currentData(Qt.ItemDataRole.UserRole)
    first = service.get_note(first_id)
    assert first.data_date == snapshot.report.data_date.isoformat()
    assert first.snapshot_identity_sha256 == snapshot.identity_sha256
    assert first.recorded_at
    assert widget.saved_text.isReadOnly()

    widget.read_button.click()
    _wait_until(
        application,
        lambda: widget.saved_text.toPlainText() == first.text
        and "已讀取唯讀修訂" in widget.status_label.text(),
        timeout_ms=5000,
    )
    assert f"資料日 {first.data_date}" in widget.status_label.text()
    assert f"保存時間 {first.recorded_at}" in widget.status_label.text()

    assert widget.revise_button.isEnabled()
    widget.revise_button.click()
    assert widget.editor.toPlainText() == first.text
    widget.editor.appendPlainText("追加一項待下次核對的觀察")
    widget.save_button.click()
    _wait_until(application, lambda: widget.revisions.count() == 2, timeout_ms=5000)
    revisions = service.list_notes()
    assert revisions[0] == first
    second = next(note for note in revisions if note.revision_id != first_id)
    assert second.revision_of == first.revision_id
    assert second.snapshot_identity_sha256 == first.snapshot_identity_sha256

    reopened_journal = JournalService(
        SimpleNamespace(output_root=paths.personal_paths.legacy_output_root),
        journal_paths=paths,
    )
    reopened = ThemeResearchNotesWidget(ThemeResearchNoteService(reopened_journal))
    _wait_until(application, lambda: not reopened.is_busy(), timeout_ms=5000)
    first_index = reopened.revisions.findData(first.revision_id, Qt.ItemDataRole.UserRole)
    assert first_index >= 0
    reopened.revisions.setCurrentIndex(first_index)
    reopened.read_button.click()
    _wait_until(
        application,
        lambda: reopened.saved_text.toPlainText() == first.text
        and "已讀取唯讀修訂" in reopened.status_label.text(),
        timeout_ms=5000,
    )
    opened: list[str] = []
    reopened.openSnapshotRequested.connect(opened.append)
    reopened.open_source_button.click()
    assert opened == [snapshot.identity_sha256]
    assert f"資料日 {date.fromisoformat(first.data_date).isoformat()}" in reopened.status_label.text()

    reopened.close()
    widget.close()
    application.processEvents()


def test_widget_translates_write_error_and_keeps_failure_visible_after_refresh():
    application = app()
    service = _FakeNoteService()
    service.fail_save = "revision_id already names different saved content"
    widget = ThemeResearchNotesWidget(service)  # type: ignore[arg-type]
    _wait_until(application, lambda: not widget.is_busy(), timeout_ms=5000)
    widget.set_snapshot(_snapshot("d" * 64))
    widget.editor.setPlainText("一筆新判斷")
    widget.save_button.click()
    _wait_until(
        application,
        lambda: not widget.is_busy() and "未覆寫原文" in widget.status_label.text(),
        timeout_ms=5000,
    )
    assert "修訂身份已存在且內容不同" in widget.status_label.text()
    assert "revision_id" not in widget.status_label.text()
    assert "已保存修訂" not in widget.status_label.text()

    widget.close()
    application.processEvents()


def test_shutdown_marks_inflight_save_unknown_without_terminating_it():
    application = app()
    started = Event()
    release = Event()
    service = _FakeNoteService(started=started, release=release)
    widget = ThemeResearchNotesWidget(service)  # type: ignore[arg-type]
    _wait_until(application, lambda: not widget.is_busy(), timeout_ms=5000)
    widget.set_snapshot(_snapshot("e" * 64))
    widget.editor.setPlainText("關閉前明確顯示保存狀態")
    widget.save_button.click()
    try:
        _wait_until(application, started.is_set, timeout_ms=5000)
        widget.shutdown()
        assert "結果未知" in widget.status_label.text()
        assert widget.is_busy()
        save_worker = widget._active_worker
        assert save_worker is not None
        remaining_workers = request_cooperative_task_worker_shutdown()
        assert save_worker in remaining_workers
        assert not save_worker.is_cancel_requested()
    finally:
        release.set()

    _wait_until(application, lambda: not widget.is_busy(), timeout_ms=5000)
    assert "已保存修訂" in widget.status_label.text()
    assert service.saved_calls
    widget.close()
    application.processEvents()


def test_compare_previous_shows_exact_notes_without_io_or_changing_draft():
    application = app()
    previous = _theme_note("compare-root", "前" * 8000)
    selected = _theme_note(
        "compare-child",
        "後" * 8000,
        revision_of=previous.revision_id,
    )
    service = _FakeNoteService()
    service.notes = {previous.revision_id: previous, selected.revision_id: selected}
    widget = ThemeResearchNotesWidget(service)  # type: ignore[arg-type]
    _wait_until(application, lambda: not widget.is_busy(), timeout_ms=5000)

    selected_index = widget.revisions.findData(selected.revision_id, Qt.ItemDataRole.UserRole)
    widget.revisions.setCurrentIndex(selected_index)
    widget.editor.setPlainText("未保存草稿保持原樣")
    widget.saved_text.setPlainText("先前唯讀區內容")
    thread_count = len(service.thread_ids)
    saved_notes = dict(service.notes)

    assert widget.compare_previous_button.isEnabled()
    widget.compare_previous_button.click()
    application.processEvents()

    assert widget.compare_dialog.isVisible()
    assert not widget.compare_dialog.isModal()
    widget.compare_dialog.resize(800, 520)
    application.processEvents()
    assert widget.compare_dialog.width() == 800
    assert widget.comparison_previous_text.isVisible()
    assert widget.comparison_selected_text.isVisible()
    assert widget.comparison_previous_text.verticalScrollBar().maximum() > 0
    assert widget.comparison_selected_text.verticalScrollBar().maximum() > 0
    assert widget.comparison_previous_text.toPlainText() == previous.text
    assert widget.comparison_selected_text.toPlainText() == selected.text
    for identity_label, note in (
        (widget.comparison_previous_identity, previous),
        (widget.comparison_selected_identity, selected),
    ):
        assert note.revision_id in identity_label.text()
        assert note.data_date in identity_label.text()
        assert note.recorded_at in identity_label.text()
        assert f"{note.snapshot_identity_sha256[:16]}…" in identity_label.text()
        assert note.snapshot_identity_sha256 not in identity_label.text()
        assert note.snapshot_identity_sha256 in identity_label.toolTip()
        assert note.revision_id in identity_label.toolTip()
    assert len(service.thread_ids) == thread_count
    assert service.notes == saved_notes
    assert widget.editor.toPlainText() == "未保存草稿保持原樣"
    assert widget.saved_text.toPlainText() == "先前唯讀區內容"

    root_index = widget.revisions.findData(previous.revision_id, Qt.ItemDataRole.UserRole)
    widget.revisions.setCurrentIndex(root_index)
    application.processEvents()
    assert not widget.compare_previous_button.isEnabled()
    assert not widget.compare_dialog.isVisible()
    assert not widget.comparison_previous_text.toPlainText()
    assert not widget.comparison_selected_text.toPlainText()
    assert widget.comparison_previous_identity.text() == "前一版：尚未載入"
    assert widget.comparison_selected_identity.text() == "目前所選修訂：尚未載入"

    widget.revisions.setCurrentIndex(selected_index)
    widget.compare_previous_button.click()
    application.processEvents()
    assert widget.compare_dialog.isVisible()
    service.fail_list = "合成刷新失敗"
    widget.refresh_notes()
    assert not widget.compare_dialog.isVisible()
    assert not widget.comparison_previous_text.toPlainText()
    assert widget.comparison_previous_identity.text() == "前一版：尚未載入"
    assert not widget.comparison_selected_text.toPlainText()
    _wait_until(application, lambda: not widget.is_busy(), timeout_ms=5000)
    assert "未完成" in widget.status_label.text()

    widget.shutdown()
    assert not widget.compare_previous_button.isEnabled()
    assert not widget.compare_dialog.isVisible()
    assert not widget.comparison_previous_text.toPlainText()
    widget.close()
    application.processEvents()


def test_compare_previous_fails_closed_for_invalid_direct_parent_links():
    application = app()
    valid_parent = _theme_note("valid-parent", "前一版")
    cases = (
        ("root", (_theme_note("root", "原始判斷"),), "root"),
        (
            "missing-parent",
            (_theme_note("orphan", "找不到父版", revision_of="absent"),),
            "orphan",
        ),
        (
            "self-parent",
            (_theme_note("self", "不能指向自己", revision_of="self"),),
            "self",
        ),
        (
            "wrong-sha",
            (
                valid_parent,
                _theme_note(
                    "wrong-sha-child",
                    "來源不同",
                    revision_of=valid_parent.revision_id,
                    identity="e" * 64,
                ),
            ),
            "wrong-sha-child",
        ),
        (
            "wrong-date",
            (
                valid_parent,
                _theme_note(
                    "wrong-date-child",
                    "資料日不同",
                    revision_of=valid_parent.revision_id,
                    data_date="2026-10-18",
                ),
            ),
            "wrong-date-child",
        ),
    )

    for _case_name, notes, selected_id in cases:
        service = _FakeNoteService()
        service.notes = {note.revision_id: note for note in notes}
        widget = ThemeResearchNotesWidget(service)  # type: ignore[arg-type]
        _wait_until(application, lambda: not widget.is_busy(), timeout_ms=5000)
        selected_index = widget.revisions.findData(selected_id, Qt.ItemDataRole.UserRole)
        widget.revisions.setCurrentIndex(selected_index)
        application.processEvents()

        assert not widget.compare_previous_button.isEnabled()
        assert not widget.compare_dialog.isVisible()
        assert not widget.comparison_previous_text.toPlainText()
        assert not widget.comparison_selected_text.toPlainText()
        assert widget.comparison_previous_identity.text() == "前一版：尚未載入"
        assert widget.comparison_selected_identity.text() == "目前所選修訂：尚未載入"
        widget.close()
        application.processEvents()


def test_compare_previous_closes_and_clears_while_selected_note_is_loading():
    application = app()
    get_started = Event()
    get_release = Event()
    previous = _theme_note("busy-root", "先前原文")
    selected = _theme_note(
        "busy-child",
        "目前修訂",
        revision_of=previous.revision_id,
    )
    service = _FakeNoteService(get_started=get_started, get_release=get_release)
    service.notes = {previous.revision_id: previous, selected.revision_id: selected}
    widget = ThemeResearchNotesWidget(service)  # type: ignore[arg-type]
    _wait_until(application, lambda: not widget.is_busy(), timeout_ms=5000)
    widget.revisions.setCurrentIndex(
        widget.revisions.findData(selected.revision_id, Qt.ItemDataRole.UserRole)
    )
    widget.compare_previous_button.click()
    application.processEvents()
    assert widget.compare_dialog.isVisible()

    widget.read_button.click()
    try:
        _wait_until(application, get_started.is_set, timeout_ms=5000)
        assert widget.is_busy()
        assert not widget.compare_previous_button.isEnabled()
        assert not widget.compare_dialog.isVisible()
        assert not widget.comparison_previous_text.toPlainText()
        assert widget.comparison_previous_identity.text() == "前一版：尚未載入"
    finally:
        get_release.set()
    _wait_until(application, lambda: not widget.is_busy(), timeout_ms=5000)
    assert widget.compare_previous_button.isEnabled()

    widget.close()
    application.processEvents()
