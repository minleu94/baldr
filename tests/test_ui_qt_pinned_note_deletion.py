from __future__ import annotations

import os
import sys
import uuid
from threading import Event, get_ident
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from app_module.daily_market_technical_universe_price_bookmark_v1 import (
    read_daily_market_technical_universe_price_bookmark_v1,
)
from app_module.pinned_stock_research_notes import (
    PinnedStockResearchNote,
    PinnedStockResearchSource,
)
from tests.test_daily_market_technical_universe_price_query_v1 import exact_price_store
from tests.test_ui_qt_pinned_stock_research_notes_widget import _wait_until
from tests.test_ui_qt_pinned_stock_save_readback import _bookmark_for, _source
import ui_qt.widgets.pinned_stock_research_notes_widget as widget_module
from ui_qt.widgets.pinned_stock_research_notes_widget import (
    PinnedStockResearchNotesWidget,
)


def _app() -> QApplication:
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication(sys.argv)
    return instance


def _note(
    source: PinnedStockResearchSource,
    revision_id: str,
    *,
    revision_of: str | None = None,
) -> PinnedStockResearchNote:
    return PinnedStockResearchNote(
        revision_id=revision_id,
        source=source,
        text=f"原文 {revision_id}",
        revision_of=revision_of,
        recorded_at="2026-10-19T10:30:00+00:00",
    )


class _DeleteService:
    def __init__(
        self,
        notes: tuple[PinnedStockResearchNote, ...],
        *,
        started: Event | None = None,
        release: Event | None = None,
        failure: str = "",
    ) -> None:
        self.notes = {note.revision_id: note for note in notes}
        self.started = started
        self.release = release
        self.failure = failure
        self.list_calls: list[str] = []
        self.delete_calls: list[tuple[PinnedStockResearchNote, str, int]] = []
        self.verify_calls: list[str] = []

    def list_notes(self, *, stock_code: str = "") -> tuple[PinnedStockResearchNote, ...]:
        self.list_calls.append(stock_code)
        return tuple(
            note for note in self.notes.values()
            if note.source.stock_code == stock_code
        )

    def get_note(self, revision_id: str) -> PinnedStockResearchNote:
        return self.notes[revision_id]

    def verify_source(self, note: PinnedStockResearchNote, *, cancel_callback=None):
        self.verify_calls.append(note.revision_id)
        if cancel_callback is not None and cancel_callback():
            raise InterruptedError("筆記來源核對已取消")
        return read_daily_market_technical_universe_price_bookmark_v1(
            note.source.bookmark_json
        )

    def delete_note_family(
        self,
        note: PinnedStockResearchNote,
        *,
        removal_revision_id: str,
    ) -> tuple[str, ...]:
        self.delete_calls.append((note, removal_revision_id, get_ident()))
        if self.started is not None:
            self.started.set()
        if self.release is not None:
            assert self.release.wait(10)
        if self.failure:
            raise ValueError(self.failure)
        if self.notes.get(note.revision_id) != note:
            raise ValueError("明選筆記身份已改變")

        root_id = note.revision_id
        while self.notes.get(root_id) is not None:
            parent_id = self.notes[root_id].revision_of
            if parent_id is None or parent_id not in self.notes:
                break
            root_id = parent_id
        family_ids = {root_id}
        changed = True
        while changed:
            changed = False
            for item in self.notes.values():
                if item.revision_of in family_ids and item.revision_id not in family_ids:
                    family_ids.add(item.revision_id)
                    changed = True
        self.notes = {
            revision_id: item
            for revision_id, item in self.notes.items()
            if revision_id not in family_ids
        }
        return tuple(sorted(family_ids))


def _loaded_widget(
    application: QApplication,
    service: _DeleteService,
    bookmark,
) -> PinnedStockResearchNotesWidget:
    widget = PinnedStockResearchNotesWidget(service)  # type: ignore[arg-type]
    widget.set_source(bookmark)
    _wait_until(
        application,
        lambda: not widget.is_busy() and widget._verified_source is not None,
        timeout_ms=8000,
        diagnostic=lambda: (
            f"job={(widget._active_job or {}).get('kind')}；"
            f"status={widget.status_label.text()}"
        ),
    )
    return widget


def _wait_delete_and_refresh(
    application: QApplication,
    widget: PinnedStockResearchNotesWidget,
    service: _DeleteService,
    *,
    expected_list_calls: int,
) -> None:
    _wait_until(
        application,
        lambda: (
            not widget.is_busy()
            and len(service.list_calls) >= expected_list_calls
            and widget._active_job is None
        ),
        timeout_ms=8000,
        diagnostic=lambda: (
            f"busy={widget.is_busy()}；job={(widget._active_job or {}).get('kind')}；"
            f"lists={service.list_calls}；status={widget.status_label.text()}"
        ),
    )


def _family_notes(source: PinnedStockResearchSource):
    root = _note(source, "family-root")
    child = _note(source, "family-child", revision_of=root.revision_id)
    other = _note(source, "other-root")
    return root, child, other


def test_delete_cancel_defaults_to_no_and_preserves_selection_and_draft(
    exact_price_store: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application = _app()
    bookmark = _bookmark_for(exact_price_store, "S0001")
    source = _source(bookmark)
    root, child, other = _family_notes(source)
    service = _DeleteService((root, child, other))
    widget = _loaded_widget(application, service, bookmark)
    question: list[tuple[Any, ...]] = []

    def decline(*args):
        question.append(args)
        return QMessageBox.StandardButton.No

    monkeypatch.setattr(widget_module.QMessageBox, "question", decline)
    try:
        assert not widget.delete_button.isEnabled()
        widget.revisions.setCurrentIndex(
            widget.revisions.findData(child.revision_id, Qt.ItemDataRole.UserRole)
        )
        assert widget.delete_button.isEnabled()
        widget.editor.setPlainText("未保存草稿")
        selected_before = widget._selected_revision_id()
        status_before = widget.status_label.text()

        widget.delete_button.click()

        assert question
        assert question[0][-1] == QMessageBox.StandardButton.No
        assert "全部修訂" in question[0][2]
        assert "Journal" in question[0][2] and "價格來源" in question[0][2]
        assert widget._selected_revision_id() == selected_before
        assert widget.editor.toPlainText() == "未保存草稿"
        assert widget.status_label.text() == status_before
        assert service.delete_calls == []
        assert set(service.notes) == {root.revision_id, child.revision_id, other.revision_id}
    finally:
        widget.close()
        application.processEvents()


@pytest.mark.parametrize("draft_parent", [None, "family-child"])
def test_confirmed_delete_removes_only_note_family_and_refreshes_journal_without_source_read(
    exact_price_store: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    draft_parent: str | None,
) -> None:
    application = _app()
    bookmark = _bookmark_for(exact_price_store, "S0001")
    source = _source(bookmark)
    root, child, other = _family_notes(source)
    service = _DeleteService((root, child, other))
    source_verifications: list[str] = []
    original_verifier = widget_module.verify_pinned_stock_research_source

    def count_source_reads(selected_bookmark, *, cancel_callback=None):
        source_verifications.append(selected_bookmark.bookmark_identity_sha256)
        return original_verifier(selected_bookmark, cancel_callback=cancel_callback)

    monkeypatch.setattr(
        widget_module,
        "verify_pinned_stock_research_source",
        count_source_reads,
    )
    monkeypatch.setattr(
        widget_module.QMessageBox,
        "question",
        lambda *_args: QMessageBox.StandardButton.Yes,
    )
    widget = _loaded_widget(application, service, bookmark)
    try:
        child_index = widget.revisions.findData(
            child.revision_id,
            Qt.ItemDataRole.UserRole,
        )
        widget.revisions.setCurrentIndex(child_index)
        widget._read_selected()
        _wait_until(
            application,
            lambda: not widget.is_busy() and widget._loaded_note == child,
            timeout_ms=8000,
        )
        if draft_parent is not None:
            widget._prepare_revision()
            assert widget._draft_revision_of == child.revision_id
            widget.editor.setPlainText("保留原文的未保存修訂草稿")
        else:
            widget.editor.setPlainText("獨立的未保存草稿")
        draft_before = widget.editor.toPlainText()
        source_reads_before_delete = len(source_verifications)
        service_verifications_before_delete = len(service.verify_calls)

        widget.delete_button.click()
        _wait_delete_and_refresh(
            application,
            widget,
            service,
            expected_list_calls=2,
        )

        assert len(service.delete_calls) == 1
        submitted_note, removal_id, worker_thread = service.delete_calls[0]
        assert submitted_note == child
        assert str(uuid.UUID(removal_id)) == removal_id
        assert worker_thread != get_ident()
        assert set(service.notes) == {other.revision_id}
        assert widget.revisions.count() == 1
        assert widget.revisions.itemData(0, Qt.ItemDataRole.UserRole) == other.revision_id
        assert widget.revisions.findData(child.revision_id, Qt.ItemDataRole.UserRole) == -1
        assert widget.revisions.findData(root.revision_id, Qt.ItemDataRole.UserRole) == -1
        assert widget._loaded_note is None
        assert widget._loaded_source_state is None
        assert widget.saved_text.toPlainText() == ""
        assert widget._draft_revision_of is None
        assert widget.editor.toPlainText() == draft_before
        assert len(source_verifications) == source_reads_before_delete
        assert len(service.verify_calls) == service_verifications_before_delete
        assert "Journal 原始歷史" in widget.status_label.text()
        assert "價格來源保留" in widget.status_label.text()
    finally:
        widget.close()
        application.processEvents()


def test_delete_error_preserves_original_list_selection_and_draft(
    exact_price_store: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application = _app()
    bookmark = _bookmark_for(exact_price_store, "S0001")
    source = _source(bookmark)
    root, child, other = _family_notes(source)
    service = _DeleteService((root, child, other), failure="Journal revision conflict")
    widget = _loaded_widget(application, service, bookmark)
    monkeypatch.setattr(
        widget_module.QMessageBox,
        "question",
        lambda *_args: QMessageBox.StandardButton.Yes,
    )
    try:
        widget.revisions.setCurrentIndex(
            widget.revisions.findData(child.revision_id, Qt.ItemDataRole.UserRole)
        )
        widget.editor.setPlainText("獨立草稿保持原樣")
        selected_before = widget._selected_revision_id()
        list_before = dict(widget._notes_by_id)
        calls_before = list(service.list_calls)

        widget.delete_button.click()
        _wait_until(
            application,
            lambda: not widget.is_busy(),
            timeout_ms=8000,
            diagnostic=lambda: widget.status_label.text(),
        )

        assert set(widget._notes_by_id) == set(list_before)
        assert widget._notes_by_id == list_before
        assert widget._selected_revision_id() == selected_before
        assert widget.editor.toPlainText() == "獨立草稿保持原樣"
        assert service.list_calls == calls_before
        assert "Journal revision conflict" in widget.status_label.text()
        assert len(service.notes) == 3
    finally:
        widget.close()
        application.processEvents()


def test_delete_write_stays_busy_and_stale_result_does_not_replace_new_stock(
    exact_price_store: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application = _app()
    bookmark_a = _bookmark_for(exact_price_store, "S0001")
    bookmark_b = _bookmark_for(exact_price_store, "S0002")
    source_a = _source(bookmark_a)
    source_b = _source(bookmark_b)
    root, child, other = _family_notes(source_a)
    other_stock = _note(source_b, "other-stock")
    started, release = Event(), Event()
    service = _DeleteService(
        (root, child, other, other_stock),
        started=started,
        release=release,
    )
    widget = _loaded_widget(application, service, bookmark_a)
    monkeypatch.setattr(
        widget_module.QMessageBox,
        "question",
        lambda *_args: QMessageBox.StandardButton.Yes,
    )
    try:
        widget.revisions.setCurrentIndex(
            widget.revisions.findData(child.revision_id, Qt.ItemDataRole.UserRole)
        )
        widget.delete_button.click()
        _wait_until(application, started.is_set, timeout_ms=8000)
        assert widget.has_pending_write()
        assert not widget.delete_button.isEnabled()
        assert not widget.read_button.isEnabled()
        assert not widget.revise_button.isEnabled()
        assert not widget.save_button.isEnabled()
        assert widget.editor.isReadOnly()
        assert not widget.revisions.isEnabled()

        widget.set_source(bookmark_b)
        assert widget.is_busy()
        assert widget.has_pending_write()
        release.set()
        _wait_until(
            application,
            lambda: (
                not widget.is_busy()
                and widget._verified_source is not None
                and widget._verified_source.stock_code == "S0002"
            ),
            timeout_ms=8000,
            diagnostic=lambda: widget.status_label.text(),
        )

        assert set(service.notes) == {other.revision_id, other_stock.revision_id}
        assert set(widget._notes_by_id) == {other_stock.revision_id}
        assert widget._loaded_note is None
    finally:
        release.set()
        widget.close()
        application.processEvents()


def test_close_does_not_cancel_submitted_delete_write(
    exact_price_store: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application = _app()
    bookmark = _bookmark_for(exact_price_store, "S0001")
    source = _source(bookmark)
    root, child, other = _family_notes(source)
    started, release = Event(), Event()
    service = _DeleteService(
        (root, child, other),
        started=started,
        release=release,
    )
    widget = _loaded_widget(application, service, bookmark)
    monkeypatch.setattr(
        widget_module.QMessageBox,
        "question",
        lambda *_args: QMessageBox.StandardButton.Yes,
    )
    try:
        widget.revisions.setCurrentIndex(
            widget.revisions.findData(child.revision_id, Qt.ItemDataRole.UserRole)
        )
        widget.delete_button.click()
        _wait_until(application, started.is_set, timeout_ms=8000)

        widget.close()
        application.processEvents()
        assert widget.has_pending_write()
        release.set()
        _wait_until(
            application,
            lambda: not widget.is_busy(),
            timeout_ms=8000,
            diagnostic=lambda: widget.status_label.text(),
        )

        assert not widget.has_pending_write()
        assert set(service.notes) == {other.revision_id}
        assert child.revision_id in widget._notes_by_id
    finally:
        release.set()
        widget.close()
        application.processEvents()
