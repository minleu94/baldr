"""F07 來源語義證明 scope 的背景工作邊界測試。"""

from __future__ import annotations

import os
from contextlib import contextmanager
from threading import Event, get_ident
from typing import Any, Callable, Iterator

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from app_module.daily_market_technical_universe_price_bookmark_v1 import (
    DailyMarketTechnicalUniversePriceBookmarkV1,
)
from app_module.pinned_stock_research_notes import PinnedStockResearchSource
from tests.test_daily_market_technical_universe_price_query_v1 import exact_price_store
from tests.test_ui_qt_pinned_stock_research_notes_widget import (
    _FakePinnedNoteService,
    _bookmark_for,
    _diagnostic,
    _wait_until,
    app,
)
import ui_qt.widgets.pinned_stock_research_notes_widget as pinned_notes_widget_module
from ui_qt.widgets.pinned_stock_research_notes_widget import (
    PinnedStockResearchNotesWidget,
)


class _ScopedPinnedNoteService(_FakePinnedNoteService):
    def __init__(self) -> None:
        super().__init__()
        self.scope_active = False
        self.scope_entries = 0
        self.scope_exits = 0
        self.scope_thread_id: int | None = None

    @contextmanager
    def source_read_scope(self) -> Iterator[None]:
        assert not self.scope_active
        self.scope_active = True
        self.scope_entries += 1
        self.scope_thread_id = get_ident()
        try:
            yield
        finally:
            self.scope_active = False
            self.scope_exits += 1


@pytest.mark.parametrize("fail_verifier", [False, True])
def test_source_scope_is_worker_local_and_exits_after_verifier(
    exact_price_store: dict[str, Any],
    monkeypatch: Any,
    fail_verifier: bool,
) -> None:
    application = app()
    bookmark = _bookmark_for(exact_price_store, "S0001")
    service = _ScopedPinnedNoteService()
    verifier_started, verifier_release = Event(), Event()
    verifier_threads: list[int] = []

    def verifier(
        selected_bookmark: DailyMarketTechnicalUniversePriceBookmarkV1,
        *,
        cancel_callback: Callable[[], bool] | None = None,
    ) -> PinnedStockResearchSource:
        assert selected_bookmark is bookmark
        assert cancel_callback is not None
        assert service.scope_active
        verifier_threads.append(get_ident())
        verifier_started.set()
        assert verifier_release.wait(5)
        if fail_verifier:
            raise ValueError("測試來源拒絕")
        return PinnedStockResearchSource(bookmark_json=selected_bookmark.to_json())

    monkeypatch.setattr(
        pinned_notes_widget_module,
        "verify_pinned_stock_research_source",
        verifier,
    )
    widget = PinnedStockResearchNotesWidget(service)  # type: ignore[arg-type]
    results: list[Any] = []
    errors: list[str] = []
    native_finished: list[bool] = []
    main_thread_id = get_ident()
    widget.set_source(bookmark)
    try:
        _wait_until(
            application,
            verifier_started.is_set,
            diagnostic=lambda: _diagnostic(widget),
        )
        worker = widget._active_worker
        assert worker is not None
        worker.finished.connect(results.append)
        worker.error.connect(errors.append)
        worker.native_thread_finished.connect(lambda: native_finished.append(True))
        verifier_release.set()
        _wait_until(
            application,
            lambda: not widget.is_busy() and native_finished == [True],
            diagnostic=lambda: _diagnostic(widget),
        )

        assert verifier_threads and verifier_threads[0] != main_thread_id
        assert service.scope_thread_id == verifier_threads[0]
        assert service.scope_entries == service.scope_exits == 1
        assert not service.scope_active
        assert len(results) == 1
        assert errors == []
        if fail_verifier:
            assert results[0]["source"] is None
            assert "測試來源拒絕" in results[0]["source_error"]
        else:
            assert results[0]["source"].identity_sha256 == bookmark.bookmark_identity_sha256
            assert results[0]["source_error"] == ""
    finally:
        verifier_release.set()
        widget.shutdown()
        if widget.is_busy():
            _wait_until(
                application,
                lambda: not widget.is_busy(),
                diagnostic=lambda: _diagnostic(widget),
            )
        widget.close()
        application.processEvents()


def test_source_scope_exits_after_cooperative_verifier_cancellation(
    exact_price_store: dict[str, Any],
    monkeypatch: Any,
) -> None:
    application = app()
    bookmark = _bookmark_for(exact_price_store, "S0001")
    service = _ScopedPinnedNoteService()
    verifier_started, verifier_release, cancel_seen = Event(), Event(), Event()

    def verifier(
        selected_bookmark: DailyMarketTechnicalUniversePriceBookmarkV1,
        *,
        cancel_callback: Callable[[], bool] | None = None,
    ) -> PinnedStockResearchSource:
        assert selected_bookmark is bookmark
        assert cancel_callback is not None
        assert service.scope_active
        verifier_started.set()
        while not verifier_release.wait(0.01):
            if cancel_callback():
                cancel_seen.set()
                raise InterruptedError("原價格版本核對已取消")
        if cancel_callback():
            cancel_seen.set()
            raise InterruptedError("原價格版本核對已取消")
        return PinnedStockResearchSource(bookmark_json=selected_bookmark.to_json())

    monkeypatch.setattr(
        pinned_notes_widget_module,
        "verify_pinned_stock_research_source",
        verifier,
    )
    widget = PinnedStockResearchNotesWidget(service)  # type: ignore[arg-type]
    results: list[Any] = []
    errors: list[str] = []
    native_finished: list[bool] = []
    widget.set_source(bookmark)
    try:
        _wait_until(
            application,
            verifier_started.is_set,
            diagnostic=lambda: _diagnostic(widget),
        )
        worker = widget._active_worker
        assert worker is not None
        worker.finished.connect(results.append)
        worker.error.connect(errors.append)
        worker.native_thread_finished.connect(lambda: native_finished.append(True))
        widget.request_cancel()
        verifier_release.set()
        _wait_until(
            application,
            lambda: not widget.is_busy() and native_finished == [True],
            diagnostic=lambda: _diagnostic(widget),
        )

        assert cancel_seen.is_set()
        assert results == []
        assert errors and "原價格版本核對已取消" in errors[0]
        assert service.scope_entries == service.scope_exits == 1
        assert not service.scope_active
        assert service.list_calls == []
    finally:
        verifier_release.set()
        widget.shutdown()
        if widget.is_busy():
            _wait_until(
                application,
                lambda: not widget.is_busy(),
                diagnostic=lambda: _diagnostic(widget),
            )
        widget.close()
        application.processEvents()


def test_legacy_fake_service_without_scope_keeps_verifier_compatibility(
    exact_price_store: dict[str, Any],
    monkeypatch: Any,
) -> None:
    application = app()
    bookmark = _bookmark_for(exact_price_store, "S0001")
    service = _FakePinnedNoteService()
    verifier_called = Event()

    def verifier(
        selected_bookmark: DailyMarketTechnicalUniversePriceBookmarkV1,
        *,
        cancel_callback: Callable[[], bool] | None = None,
    ) -> PinnedStockResearchSource:
        assert cancel_callback is not None
        verifier_called.set()
        return PinnedStockResearchSource(bookmark_json=selected_bookmark.to_json())

    monkeypatch.setattr(
        pinned_notes_widget_module,
        "verify_pinned_stock_research_source",
        verifier,
    )
    widget = PinnedStockResearchNotesWidget(service)  # type: ignore[arg-type]
    widget.set_source(bookmark)
    try:
        _wait_until(
            application,
            lambda: verifier_called.is_set()
            and not widget.is_busy()
            and widget._verified_source is not None,
            diagnostic=lambda: _diagnostic(widget),
        )
        assert not hasattr(service, "source_read_scope")
        assert widget._verified_source.identity_sha256 == bookmark.bookmark_identity_sha256
    finally:
        widget.shutdown()
        if widget.is_busy():
            _wait_until(
                application,
                lambda: not widget.is_busy(),
                diagnostic=lambda: _diagnostic(widget),
            )
        widget.close()
        application.processEvents()
