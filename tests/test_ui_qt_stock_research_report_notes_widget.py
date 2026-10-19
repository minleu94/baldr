"""個股研究報告判斷筆記的 Qt 背景讀寫與來源綁定。"""

from __future__ import annotations

import os
import sys
import time
from dataclasses import replace
from threading import Event, get_ident
from typing import Callable

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app_module.stock_research_report_dtos import StockResearchReportDTO
from app_module.stock_research_report_notes import StockResearchReportNote
from app_module.stock_research_report_snapshot_codec import (
    StockResearchReportProjectionSnapshot,
    create_stock_research_report_projection_snapshot,
)
from ui_qt.widgets.stock_research_report_notes_widget import (
    StockResearchReportNotesWidget,
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
) -> None:
    deadline = time.monotonic() + timeout_ms / 1000
    while True:
        application.processEvents()
        if predicate():
            application.processEvents()
            return
        if time.monotonic() >= deadline:
            raise AssertionError("Qt 背景筆記狀態未在固定期限內完成")
        QTest.qWait(10)
        time.sleep(0.001)


def _snapshot(
    *,
    stock_code: str = "2330",
    as_of: str = "2026-10-16T13:30:00+08:00",
    generated_at: str = "2026-10-16T13:31:12+08:00",
) -> StockResearchReportProjectionSnapshot:
    report = StockResearchReportDTO(
        stock_code=stock_code,
        stock_name=f"測試股票 {stock_code}",
        as_of=as_of,
        generated_at=generated_at,
        read_only=True,
    )
    return create_stock_research_report_projection_snapshot(report)


def _note(
    revision_id: str,
    snapshot: StockResearchReportProjectionSnapshot,
    text: str,
    *,
    revision_of: str | None = None,
    recorded_at: str = "2026-10-18T09:15:00+08:00",
) -> StockResearchReportNote:
    return StockResearchReportNote(
        revision_id=revision_id,
        snapshot=snapshot,
        text=text,
        revision_of=revision_of,
        recorded_at=recorded_at,
    )


class _FakeReportNoteService:
    def __init__(
        self,
        notes: tuple[StockResearchReportNote, ...] = (),
        *,
        get_started: Event | None = None,
        get_release: Event | None = None,
        save_started: Event | None = None,
        save_release: Event | None = None,
    ) -> None:
        self.notes = {note.revision_id: note for note in notes}
        self.get_started = get_started
        self.get_release = get_release
        self.save_started = save_started
        self.save_release = save_release
        self.list_calls: list[tuple[str, int]] = []
        self.get_calls: list[tuple[str, int]] = []
        self.save_calls: list[
            tuple[
                StockResearchReportProjectionSnapshot,
                str,
                str,
                str | None,
                int,
            ]
        ] = []

    def list_notes(self, *, stock_code: str = "") -> tuple[StockResearchReportNote, ...]:
        self.list_calls.append((stock_code, get_ident()))
        return tuple(
            note
            for note in self.notes.values()
            if not stock_code or note.snapshot.stock_code == stock_code
        )

    def get_note(self, revision_id: str) -> StockResearchReportNote:
        self.get_calls.append((revision_id, get_ident()))
        if self.get_started is not None:
            self.get_started.set()
        if self.get_release is not None:
            self.get_release.wait(5)
        return self.notes[revision_id]

    def save(
        self,
        snapshot: StockResearchReportProjectionSnapshot,
        text: str,
        *,
        revision_id: str,
        revision_of: str | None = None,
    ) -> StockResearchReportNote:
        self.save_calls.append(
            (snapshot, text, revision_id, revision_of, get_ident())
        )
        if self.save_started is not None:
            self.save_started.set()
        if self.save_release is not None:
            self.save_release.wait(5)
        note = _note(
            revision_id,
            snapshot,
            text,
            revision_of=revision_of,
        )
        self.notes[revision_id] = note
        return note


def _wait_idle(application: QApplication, widget: StockResearchReportNotesWidget) -> None:
    _wait_until(application, lambda: not widget.is_busy())


def test_background_list_save_explicit_read_and_fresh_open_preserve_original_report():
    application = app()
    service = _FakeReportNoteService()
    widget = StockResearchReportNotesWidget(service)  # type: ignore[arg-type]
    _wait_idle(application, widget)
    assert service.list_calls == [], "建立元件不得自動開啟私人 Journal"
    assert widget.revisions.currentIndex() == -1

    snapshot = _snapshot()
    widget.set_snapshot(snapshot, stock_code="2330")
    _wait_idle(application, widget)
    original = "  第一行原文\n\n第二行保留空白  "
    widget.editor.setPlainText(original)
    assert widget.save_button.text() == "保存此份報告與判斷"
    assert widget.save_button.isEnabled()
    widget.save_button.click()
    _wait_until(
        application,
        lambda: not widget.is_busy()
        and widget.revisions.count() == 1
        and "清單已刷新" in widget.status_label.text(),
    )

    saved_snapshot, saved_text, revision_id, revision_of, worker_thread = service.save_calls[0]
    assert saved_snapshot is not snapshot
    assert saved_snapshot.identity_sha256 == snapshot.identity_sha256
    assert saved_snapshot.canonical_json == snapshot.canonical_json
    assert saved_snapshot.report == snapshot.report
    assert saved_text == original
    assert revision_of is None
    assert worker_thread != get_ident()
    assert widget.revisions.currentIndex() == -1
    assert not widget.saved_text.toPlainText()
    assert service.list_calls
    assert all(thread_id != get_ident() for _, thread_id in service.list_calls)

    selected_index = widget.revisions.findData(revision_id, Qt.ItemDataRole.UserRole)
    assert selected_index >= 0
    widget.revisions.setCurrentIndex(selected_index)
    widget.read_button.click()
    _wait_until(
        application,
        lambda: widget.saved_text.toPlainText() == original
        and "已讀取判斷" in widget.status_label.text(),
    )
    assert "查詢截至：2026-10-16T13:30:00+08:00" in widget.status_label.text()
    assert "原報告產生時間：2026-10-16T13:31:12+08:00" in widget.status_label.text()
    assert "實際保存時間：2026-10-18T09:15:00+08:00" in widget.status_label.text()
    assert service.get_calls[-1][1] != get_ident()
    assert widget.revise_button.isEnabled()
    widget.revise_button.click()
    assert widget.editor.toPlainText() == original
    widget.editor.appendPlainText("追加一項觀察")
    revised_text = widget.editor.toPlainText()
    widget.save_button.click()
    _wait_until(
        application,
        lambda: not widget.is_busy()
        and widget.revisions.count() == 2
        and "清單已刷新" in widget.status_label.text(),
    )
    assert service.save_calls[1][0].canonical_json == snapshot.canonical_json
    assert service.save_calls[1][0].identity_sha256 == snapshot.identity_sha256
    assert service.save_calls[1][1] == revised_text
    assert service.save_calls[1][3] == revision_id
    assert widget.revisions.currentData(Qt.ItemDataRole.UserRole) == revision_id

    fresh_snapshot = _snapshot()
    service.notes[revision_id] = _note(
        revision_id,
        fresh_snapshot,
        original,
        recorded_at="2026-10-18T09:15:00+08:00",
    )
    opened: list[StockResearchReportProjectionSnapshot] = []
    widget.openSnapshotRequested.connect(opened.append)
    prior_get_count = len(service.get_calls)
    widget.open_report_button.click()
    _wait_until(application, lambda: len(opened) == 1 and not widget.is_busy())
    assert opened[0] is fresh_snapshot
    assert opened[0] is not snapshot
    assert len(service.get_calls) == prior_get_count + 1
    assert service.get_calls[-1][0] == revision_id
    assert service.get_calls[-1][1] != get_ident()
    assert "重新讀取保存時報告副本" in widget.status_label.text()

    widget.set_snapshot(None, stock_code="2330")
    assert not widget.save_button.isEnabled()
    assert widget.revisions.count() == 2
    assert widget.revisions.currentData(Qt.ItemDataRole.UserRole) == revision_id
    assert widget.open_report_button.isEnabled()
    widget.open_report_button.click()
    _wait_until(application, lambda: len(opened) == 2 and not widget.is_busy())
    assert opened[1] is fresh_snapshot

    widget.read_button.click()
    _wait_until(
        application,
        lambda: widget.saved_text.toPlainText() == original
        and "已讀取判斷" in widget.status_label.text(),
    )
    assert widget.revise_button.isEnabled()
    widget.revise_button.click()
    assert widget.editor.toPlainText() == original
    assert widget._draft_snapshot is not None
    assert widget._draft_snapshot.canonical_json == fresh_snapshot.canonical_json
    widget.editor.appendPlainText("重開後另存一項補充")
    reopened_revision_text = widget.editor.toPlainText()
    widget.save_button.click()
    _wait_until(
        application,
        lambda: not widget.is_busy()
        and widget.revisions.count() == 3
        and "清單已刷新" in widget.status_label.text(),
    )
    assert service.save_calls[2][1] == reopened_revision_text
    assert service.save_calls[2][3] == revision_id
    assert service.save_calls[2][0].identity_sha256 == fresh_snapshot.identity_sha256
    assert service.save_calls[2][0].canonical_json == fresh_snapshot.canonical_json
    widget.close()
    application.processEvents()


def test_snapshot_entry_uses_canonical_report_and_rejects_mismatched_sha():
    application = app()
    service = _FakeReportNoteService()
    widget = StockResearchReportNotesWidget(service)  # type: ignore[arg-type]
    _wait_idle(application, widget)

    canonical = _snapshot(
        as_of="2026-10-15T13:30:00+08:00",
        generated_at="2026-10-15T13:31:00+08:00",
    )
    altered_report = replace(
        canonical.report,
        stock_name="偽造名稱",
        as_of="2099-12-31T23:59:59+08:00",
        generated_at="2099-12-31T23:59:59+08:00",
    )
    altered_projection = replace(
        canonical,
        stock_code="2382",
        report=altered_report,
    )
    widget.set_snapshot(altered_projection, stock_code="2330")
    _wait_idle(application, widget)

    assert "測試股票 2330" in widget.source_label.text()
    assert "查詢截至：2026-10-15T13:30:00+08:00" in widget.source_label.text()
    assert "原報告產生時間：2026-10-15T13:31:00+08:00" in widget.source_label.text()
    assert "偽造名稱" not in widget.source_label.text()
    assert "2099-12-31" not in widget.source_label.text()
    assert widget._snapshot is not altered_projection
    assert widget._snapshot is not None
    assert widget._snapshot.stock_code == canonical.stock_code
    assert widget._snapshot.canonical_json == canonical.canonical_json
    assert widget._snapshot.report == canonical.report

    widget.editor.setPlainText("依 canonical 報告保存的判斷")
    assert widget._draft_snapshot is not None
    assert widget._draft_snapshot.stock_code == canonical.stock_code
    widget.save_button.click()
    _wait_until(
        application,
        lambda: not widget.is_busy()
        and widget.revisions.count() == 1
        and "清單已刷新" in widget.status_label.text(),
    )
    saved_snapshot = service.save_calls[0][0]
    assert saved_snapshot.canonical_json == canonical.canonical_json
    assert saved_snapshot.identity_sha256 == canonical.identity_sha256
    assert saved_snapshot.report.stock_name == canonical.report.stock_name
    assert saved_snapshot.report.as_of == canonical.report.as_of
    assert saved_snapshot.report.generated_at == canonical.report.generated_at

    wrong_sha = "0" * 64
    if wrong_sha == canonical.identity_sha256:
        wrong_sha = "1" * 64
    wrong_sha_projection = replace(canonical, identity_sha256=wrong_sha)
    with pytest.raises(ValueError, match="canonical_json 與 SHA-256"):
        widget.set_snapshot(wrong_sha_projection, stock_code="2330")
    with pytest.raises(TypeError, match="StockResearchReportProjectionSnapshot"):
        widget.set_snapshot(object())  # type: ignore[arg-type]
    assert widget._snapshot is not None
    assert widget._snapshot.identity_sha256 == canonical.identity_sha256
    assert widget._snapshot.report.as_of == canonical.report.as_of
    widget.close()
    application.processEvents()


def test_stale_read_is_discarded_and_draft_remains_bound_to_original_snapshot():
    application = app()
    snapshot_a = _snapshot()
    snapshot_b = _snapshot(
        as_of="2026-10-17T13:30:00+08:00",
        generated_at="2026-10-17T13:32:00+08:00",
    )
    existing = _note("existing", snapshot_a, "保存原文")
    get_started = Event()
    get_release = Event()
    service = _FakeReportNoteService(
        (existing,), get_started=get_started, get_release=get_release
    )
    widget = StockResearchReportNotesWidget(service)  # type: ignore[arg-type]
    _wait_idle(application, widget)
    widget.set_snapshot(snapshot_a, stock_code="2330")
    _wait_idle(application, widget)
    selected_index = widget.revisions.findData(existing.revision_id, Qt.ItemDataRole.UserRole)
    widget.revisions.setCurrentIndex(selected_index)
    widget.editor.setPlainText("仍綁 A 的草稿")
    widget.read_button.click()
    try:
        _wait_until(application, get_started.is_set)
        widget.set_snapshot(snapshot_b, stock_code="2330")
        assert widget.editor.toPlainText() == "仍綁 A 的草稿"
        assert widget._draft_snapshot is not snapshot_a
        assert widget._draft_snapshot is not None
        assert widget._draft_snapshot.canonical_json == snapshot_a.canonical_json
        assert widget._draft_snapshot.identity_sha256 == snapshot_a.identity_sha256
        assert not widget.saved_text.toPlainText()
    finally:
        get_release.set()

    _wait_idle(application, widget)
    assert not widget.saved_text.toPlainText()
    assert "已丟棄" in widget.status_label.text()
    assert widget.save_button.isEnabled()
    widget.save_button.click()
    _wait_until(
        application,
        lambda: not widget.is_busy()
        and any(note.text == "仍綁 A 的草稿" for note in service.notes.values()),
    )
    saved = next(note for note in service.notes.values() if note.text == "仍綁 A 的草稿")
    assert saved.snapshot is not snapshot_a
    assert saved.snapshot.canonical_json == snapshot_a.canonical_json
    assert saved.snapshot.identity_sha256 == snapshot_a.identity_sha256
    assert widget.editor.toPlainText() == ""
    widget.close()
    application.processEvents()


def test_direct_parent_comparison_shows_exact_report_times_and_original_text():
    application = app()
    snapshot = _snapshot()
    parent = _note(
        "parent-revision",
        snapshot,
        "前版原文\n" + "前" * 5000,
        recorded_at="2026-10-18T08:00:00+08:00",
    )
    child = _note(
        "child-revision",
        snapshot,
        "修訂原文\n" + "後" * 5000,
        revision_of=parent.revision_id,
        recorded_at="2026-10-18T09:00:00+08:00",
    )
    service = _FakeReportNoteService((parent, child))
    widget = StockResearchReportNotesWidget(service)  # type: ignore[arg-type]
    widget.refresh_button.click()
    _wait_idle(application, widget)
    assert widget.revisions.currentIndex() == -1
    child_index = widget.revisions.findData(child.revision_id, Qt.ItemDataRole.UserRole)
    widget.revisions.setCurrentIndex(child_index)
    widget.editor.setPlainText("未保存草稿仍保留")

    before_io = (len(service.get_calls), len(service.list_calls), len(service.save_calls))
    assert widget.compare_previous_button.isEnabled()
    widget.compare_previous_button.click()
    application.processEvents()

    assert widget.compare_dialog.isVisible()
    widget.compare_dialog.resize(800, 520)
    application.processEvents()
    assert widget.compare_dialog.width() == 800
    assert widget.comparison_previous_text.toPlainText() == parent.text
    assert widget.comparison_selected_text.toPlainText() == child.text
    assert widget.comparison_previous_text.verticalScrollBar().maximum() > 0
    assert widget.comparison_selected_text.verticalScrollBar().maximum() > 0
    for label, note in (
        (widget.comparison_previous_identity, parent),
        (widget.comparison_selected_identity, child),
    ):
        assert note.revision_id in label.text()
        assert "查詢截至：2026-10-16T13:30:00+08:00" in label.text()
        assert "原報告產生時間：2026-10-16T13:31:12+08:00" in label.text()
        assert note.recorded_at in label.text()
        assert note.snapshot.identity_sha256[:16] in label.text()
        assert note.snapshot.identity_sha256 not in label.text()
        assert note.snapshot.identity_sha256 in label.toolTip()
    assert widget.editor.toPlainText() == "未保存草稿仍保留"
    assert before_io == (len(service.get_calls), len(service.list_calls), len(service.save_calls))

    parent_index = widget.revisions.findData(parent.revision_id, Qt.ItemDataRole.UserRole)
    widget.revisions.setCurrentIndex(parent_index)
    application.processEvents()
    assert not widget.compare_previous_button.isEnabled()
    assert not widget.compare_dialog.isVisible()
    widget.close()
    application.processEvents()


def test_close_during_save_does_not_cancel_or_drop_append_result():
    application = app()
    save_started = Event()
    save_release = Event()
    service = _FakeReportNoteService(
        save_started=save_started,
        save_release=save_release,
    )
    widget = StockResearchReportNotesWidget(service)  # type: ignore[arg-type]
    _wait_idle(application, widget)
    snapshot = _snapshot(
        as_of="2026-10-18T13:30:00+08:00",
        generated_at="2026-10-18T13:31:12+08:00",
    )
    widget.set_snapshot(snapshot, stock_code="2330")
    _wait_idle(application, widget)
    widget.editor.setPlainText("關閉期間仍需完成的判斷")
    widget.save_button.click()
    try:
        _wait_until(application, save_started.is_set)
        worker = widget._active_worker
        assert worker is not None
        widget.shutdown()
        assert widget.is_busy()
        assert "不會強制中止" in widget.status_label.text()
        remaining_workers = request_cooperative_task_worker_shutdown()
        assert worker in remaining_workers
        assert not worker.is_cancel_requested()
    finally:
        save_release.set()

    _wait_idle(application, widget)
    assert service.save_calls
    assert service.save_calls[0][0] is not snapshot
    assert service.save_calls[0][0].canonical_json == snapshot.canonical_json
    assert any(note.text == "關閉期間仍需完成的判斷" for note in service.notes.values())
    assert "保存結果已確認" in widget.status_label.text()
    widget.close()
    application.processEvents()
