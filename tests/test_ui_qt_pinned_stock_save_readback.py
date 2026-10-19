"""F07 個股筆記同次保存回讀的 UI 邊界測試。"""

from __future__ import annotations

import os
import sys
import time
from threading import Event, get_ident
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from app_module.daily_market_technical_universe_price_bookmark_v1 import (
    DailyMarketTechnicalUniversePriceBookmarkStateV1,
    DailyMarketTechnicalUniversePriceBookmarkV1,
    create_daily_market_technical_universe_price_bookmark_v1,
    read_daily_market_technical_universe_price_bookmark_v1,
)
from app_module.pinned_stock_research_notes import (
    PinnedStockResearchNote,
    PinnedStockResearchNoteSaveReadback,
    PinnedStockResearchSource,
)
from tests.test_daily_market_technical_universe_price_query_v1 import (
    _open_session,
    exact_price_store,
)
import ui_qt.widgets.pinned_stock_research_notes_widget as widget_module
from ui_qt.widgets.pinned_stock_research_notes_widget import (
    PinnedStockResearchNotesWidget,
)
from tests.test_ui_qt_pinned_stock_research_notes_widget import _wait_until


def _app() -> QApplication:
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication(sys.argv)
    return instance


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


def _wait_source(application: QApplication, widget: PinnedStockResearchNotesWidget) -> None:
    _wait_until(
        application,
        lambda: not widget.is_busy() and widget._verified_source is not None,
        timeout_ms=8000,
    )


def _wait_idle(application: QApplication, widget: PinnedStockResearchNotesWidget) -> None:
    _wait_until(application, lambda: not widget.is_busy(), timeout_ms=8000)


class _ReadbackService:
    """以真 typed bookmark state 模擬服務已完成的保存後 Journal 回讀。"""

    def __init__(
        self,
        *,
        fault: str = "",
        wrong_state: DailyMarketTechnicalUniversePriceBookmarkStateV1 | None = None,
        save_started: Event | None = None,
        save_release: Event | None = None,
    ) -> None:
        self.notes: dict[str, PinnedStockResearchNote] = {}
        self.fault = fault
        self.wrong_state = wrong_state
        self.save_started = save_started
        self.save_release = save_release
        self.list_calls: list[tuple[str, int]] = []
        self.save_calls: list[
            tuple[PinnedStockResearchSource, str, str, str | None, int]
        ] = []

    def list_notes(self, *, stock_code: str = "") -> tuple[PinnedStockResearchNote, ...]:
        self.list_calls.append((stock_code, get_ident()))
        return tuple(
            note for note in self.notes.values()
            if note.source.stock_code == stock_code
        )

    def save_with_readback(
        self,
        source: PinnedStockResearchSource,
        text: str,
        *,
        revision_id: str,
        revision_of: str | None = None,
    ) -> PinnedStockResearchNoteSaveReadback | PinnedStockResearchNote:
        self.save_calls.append((source, text, revision_id, revision_of, get_ident()))
        if self.save_started is not None:
            self.save_started.set()
        if self.save_release is not None:
            self.save_release.wait(10)

        note = PinnedStockResearchNote(
            revision_id=revision_id,
            source=source,
            text=text,
            revision_of=revision_of,
            recorded_at="" if self.fault == "missing_recorded_at" else "2026-10-19T10:30:00+00:00",
        )
        self.notes[revision_id] = note
        notes = self.list_notes(stock_code=source.stock_code)
        state = read_daily_market_technical_universe_price_bookmark_v1(
            source.bookmark_json
        )
        if self.fault == "wrong_receipt":
            return note
        if self.fault == "wrong_state":
            assert self.wrong_state is not None
            state = self.wrong_state
        elif self.fault == "wrong_notes":
            notes = tuple(item for item in notes if item.revision_id != revision_id)
        return PinnedStockResearchNoteSaveReadback(
            note=note,
            source_state=state,
            notes=notes,
        )


def _count_verifications(
    monkeypatch: pytest.MonkeyPatch,
    *,
    second_started: Event | None = None,
    second_release: Event | None = None,
) -> list[str]:
    original = widget_module.verify_pinned_stock_research_source
    identities: list[str] = []

    def counted(bookmark, *, cancel_callback=None):
        identities.append(bookmark.bookmark_identity_sha256)
        if len(identities) == 2 and second_started is not None:
            second_started.set()
            if second_release is not None:
                second_release.wait(10)
        return original(bookmark, cancel_callback=cancel_callback)

    monkeypatch.setattr(widget_module, "verify_pinned_stock_research_source", counted)
    return identities


def test_valid_save_readback_applies_once_without_second_source_list_load(
    exact_price_store: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application = _app()
    bookmark = _bookmark_for(exact_price_store, "S0001")
    verifications = _count_verifications(monkeypatch)
    service = _ReadbackService()
    widget = PinnedStockResearchNotesWidget(service)  # type: ignore[arg-type]
    try:
        widget.set_source(bookmark)
        _wait_source(application, widget)
        assert len(verifications) == 1
        assert len(service.list_calls) == 1

        widget.editor.setPlainText("同次保存完成後直接顯示回讀原文")
        widget.save_button.click()
        _wait_until(
            application,
            lambda: not widget.is_busy() and widget.revisions.count() == 1,
            timeout_ms=8000,
        )

        revision_id = service.save_calls[0][2]
        saved = service.notes[revision_id]
        assert service.save_calls[0][0] == _source(bookmark)
        assert service.save_calls[0][1] == "同次保存完成後直接顯示回讀原文"
        assert service.save_calls[0][4] != get_ident()
        assert widget._notes_by_id[revision_id] == saved
        assert widget.revisions.currentIndex() == -1
        assert len(verifications) == 1
        assert len(service.list_calls) == 2
    finally:
        widget.close()
        application.processEvents()


@pytest.mark.parametrize("fault", ["wrong_receipt", "wrong_state", "wrong_notes", "missing_recorded_at"])
def test_invalid_save_readback_falls_back_to_fresh_list_load(
    exact_price_store: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    fault: str,
) -> None:
    application = _app()
    bookmark = _bookmark_for(exact_price_store, "S0001")
    wrong_state = None
    if fault == "wrong_state":
        other_bookmark = _bookmark_for(exact_price_store, "S0002")
        wrong_state = read_daily_market_technical_universe_price_bookmark_v1(
            other_bookmark
        )
    second_started, second_release = Event(), Event()
    verifications = _count_verifications(
        monkeypatch,
        second_started=second_started,
        second_release=second_release,
    )
    service = _ReadbackService(fault=fault, wrong_state=wrong_state)
    widget = PinnedStockResearchNotesWidget(service)  # type: ignore[arg-type]
    not_applied_before_fallback = False
    try:
        widget.set_source(bookmark)
        _wait_source(application, widget)
        widget.editor.setPlainText("回讀收據不符時保留舊路徑")
        widget.save_button.click()
        _wait_until(application, second_started.is_set, timeout_ms=8000)

        revision_id = service.save_calls[0][2]
        not_applied_before_fallback = (
            revision_id not in widget._notes_by_id
            and widget.revisions.findData(
                revision_id,
                Qt.ItemDataRole.UserRole,
            ) == -1
        )
        second_release.set()
        _wait_until(
            application,
            lambda: not widget.is_busy()
            and widget._verified_source is not None
            and len(service.list_calls) == 3,
            timeout_ms=8000,
        )
        revision_id = service.save_calls[0][2]
        assert not_applied_before_fallback
        assert len(verifications) == 2
        assert service.list_calls[-1][0] == "S0001"
        assert widget._notes_by_id[revision_id] == service.notes[revision_id]
        assert widget.revisions.currentIndex() == -1
    finally:
        second_release.set()
        widget.close()
        application.processEvents()


def test_context_change_preserves_pending_load_after_save_readback(
    exact_price_store: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application = _app()
    bookmark_a = _bookmark_for(exact_price_store, "S0001")
    bookmark_b = _bookmark_for(exact_price_store, "S0002")
    verifications = _count_verifications(monkeypatch)
    save_started, save_release = Event(), Event()
    service = _ReadbackService(save_started=save_started, save_release=save_release)
    widget = PinnedStockResearchNotesWidget(service)  # type: ignore[arg-type]
    try:
        widget.set_source(bookmark_a)
        _wait_source(application, widget)
        widget.editor.setPlainText("保存時切換股票不沿用舊收據")
        widget.save_button.click()
        _wait_until(application, save_started.is_set, timeout_ms=8000)
        saving_worker = widget._active_worker
        assert saving_worker is not None

        widget.set_source(bookmark_b)
        assert widget._pending_load
        assert not saving_worker.is_cancel_requested()
        save_release.set()
        _wait_until(
            application,
            lambda: not widget.is_busy()
            and widget._verified_source is not None
            and widget._verified_source.stock_code == "S0002",
            timeout_ms=8000,
        )
        assert not widget._pending_load
        assert widget._notes_by_id == {}
        assert widget.revisions.count() == 0
        assert len(verifications) == 2
        assert [code for code, _thread_id in service.list_calls] == [
            "S0001", "S0001", "S0002"
        ]
    finally:
        save_release.set()
        widget.close()
        application.processEvents()


def test_close_keeps_save_non_cancellable_and_confirms_readback_without_reload(
    exact_price_store: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application = _app()
    bookmark = _bookmark_for(exact_price_store, "S0001")
    verifications = _count_verifications(monkeypatch)
    save_started, save_release = Event(), Event()
    service = _ReadbackService(save_started=save_started, save_release=save_release)
    widget = PinnedStockResearchNotesWidget(service)  # type: ignore[arg-type]
    try:
        widget.set_source(bookmark)
        _wait_source(application, widget)
        widget.editor.setPlainText("關閉時仍完成已送出的保存")
        widget.save_button.click()
        _wait_until(application, save_started.is_set, timeout_ms=8000)
        saving_worker = widget._active_worker
        assert saving_worker is not None
        widget.close()
        assert not saving_worker.is_cancel_requested()
        save_release.set()
        _wait_idle(application, widget)
        assert widget._shutdown
        assert len(service.save_calls) == 1
        assert len(service.notes) == 1
        assert "已確認保存筆記" in widget.status_label.text()
        assert len(verifications) == 1
        assert [code for code, _thread_id in service.list_calls] == ["S0001", "S0001"]
    finally:
        save_release.set()
        widget.close()
        application.processEvents()
