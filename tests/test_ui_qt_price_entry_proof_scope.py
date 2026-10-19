"""F07 原價格入口只在 worker 的 full reader 期間啟用共用 proof 範圍。"""

from __future__ import annotations

from contextlib import AbstractContextManager, contextmanager
from pathlib import Path
from threading import Event, Lock, get_ident
import time
from typing import Any, Callable, Iterator, cast

import pytest
from PySide6.QtWidgets import QApplication

from app_module.daily_market_technical_universe_price_bookmark_v1 import (
    DailyMarketTechnicalUniversePriceBookmarkStateV1,
    DailyMarketTechnicalUniversePriceBookmarkV1,
    read_daily_market_technical_universe_price_bookmark_v1,
)
from app_module.daily_market_technical_universe_price_query_v1 import (
    DailyMarketTechnicalUniversePriceReadSessionV1,
)
from tests.test_daily_market_technical_universe_price_query_v1 import (
    _open_session,
    exact_price_store,
)
from tests.test_ui_qt_daily_market_technical_price_bookmark_controls_v1 import (
    _add,
    _bookmark_for,
    _service,
)
from ui_qt.views.daily_market_technical_universe_price_view_v1 import (
    DailyMarketTechnicalUniversePriceV1View,
)
from ui_qt.widgets.daily_market_technical_price_bookmark_controls_v1 import (
    DailyMarketTechnicalPriceBookmarkControlsV1,
)
import ui_qt.views.daily_market_technical_universe_price_view_v1 as price_view_module
import ui_qt.widgets.daily_market_technical_price_bookmark_controls_v1 as controls_module


@pytest.fixture(scope="module")
def app() -> QApplication:
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication([])
    return cast(QApplication, instance)


def _wait(app: QApplication, predicate: Callable[[], bool], *, timeout_seconds: float = 30.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while not predicate():
        app.processEvents()
        if time.monotonic() >= deadline:
            raise AssertionError("F07 proof 範圍 worker 逾時")
        time.sleep(0.01)
    app.processEvents()


class _ScopeProbe:
    def __init__(self) -> None:
        self.main_thread_id = get_ident()
        self.entered = Event()
        self.exited = Event()
        self._active_threads: set[int] = set()
        self._lock = Lock()
        self.factory_thread_ids: list[int] = []

    def factory(self) -> AbstractContextManager[None]:
        self.factory_thread_ids.append(get_ident())
        return self._scope()

    @contextmanager
    def _scope(self) -> Iterator[None]:
        thread_id = get_ident()
        with self._lock:
            self._active_threads.add(thread_id)
        self.entered.set()
        try:
            yield
        finally:
            with self._lock:
                self._active_threads.discard(thread_id)
            self.exited.set()

    def active_on_current_thread(self) -> bool:
        with self._lock:
            return get_ident() in self._active_threads

    def has_active_threads(self) -> bool:
        with self._lock:
            return bool(self._active_threads)


def _make_bookmark(
    exact_price_store: dict[str, Any],
    stock_code: str = "S0001",
) -> DailyMarketTechnicalUniversePriceBookmarkV1:
    session = cast(
        DailyMarketTechnicalUniversePriceReadSessionV1,
        _open_session(exact_price_store),
    )
    return _bookmark_for(session, stock_code, scroll_position=0)


def _prepare_controls(
    app: QApplication,
    exact_price_store: dict[str, Any],
    tmp_path: Path,
) -> tuple[DailyMarketTechnicalPriceBookmarkControlsV1, DailyMarketTechnicalUniversePriceBookmarkV1]:
    service = _service(tmp_path)
    bookmark = _make_bookmark(exact_price_store)
    _add(service, bookmark)
    controls = DailyMarketTechnicalPriceBookmarkControlsV1(service)
    controls.restore_selection(bookmark.bookmark_id)
    _wait(app, lambda: not controls.busy and controls.workers_remaining == 0)
    assert controls._current_entry() is not None
    return controls, bookmark


@pytest.mark.parametrize("outcome", ["success", "error", "cancel"])
def test_controls_reader_scope_runs_on_worker_and_exits_for_every_outcome(
    app: QApplication,
    exact_price_store: dict[str, Any],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    outcome: str,
) -> None:
    controls, bookmark = _prepare_controls(app, exact_price_store, tmp_path)
    probe = _ScopeProbe()
    controls.set_source_read_scope_factory(probe.factory)
    reader_started = Event()
    release_reader = Event()
    emitted: list[object] = []
    reader_threads: list[int] = []
    original_reader = controls_module.read_daily_market_technical_universe_price_bookmark_v1

    def checked_reader(
        value: DailyMarketTechnicalUniversePriceBookmarkV1,
        *,
        cancel_callback: Callable[[], object] | None = None,
    ) -> DailyMarketTechnicalUniversePriceBookmarkStateV1:
        reader_threads.append(get_ident())
        assert probe.active_on_current_thread()
        reader_started.set()
        if outcome == "error":
            raise ValueError("synthetic reader failure")
        if outcome == "cancel":
            assert release_reader.wait(5.0)
            if cancel_callback is not None and cancel_callback():
                raise InterruptedError("synthetic reader cancellation")
        return original_reader(value, cancel_callback=cancel_callback)

    monkeypatch.setattr(
        controls_module,
        "read_daily_market_technical_universe_price_bookmark_v1",
        checked_reader,
    )
    controls.stateReady.connect(emitted.append)
    controls.open_selected()
    assert reader_started.wait(5.0)
    if outcome == "cancel":
        controls.cancel()
        release_reader.set()
    _wait(app, lambda: not controls.busy and controls.workers_remaining == 0)

    assert probe.entered.is_set() and probe.exited.is_set()
    assert probe.factory_thread_ids == reader_threads
    assert reader_threads[0] != probe.main_thread_id
    assert not probe.has_active_threads()
    if outcome == "success":
        assert len(emitted) == 1
        assert isinstance(emitted[0], DailyMarketTechnicalUniversePriceBookmarkStateV1)
        assert emitted[0].bookmark.to_dict() == bookmark.to_dict()
    else:
        assert emitted == []
    assert controls.begin_shutdown() is True
    controls.close()


def test_controls_without_scope_factory_keeps_legacy_reader_path(
    app: QApplication,
    exact_price_store: dict[str, Any],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controls, bookmark = _prepare_controls(app, exact_price_store, tmp_path)
    controls.set_source_read_scope_factory(None)
    reader_threads: list[int] = []
    original_reader = controls_module.read_daily_market_technical_universe_price_bookmark_v1

    def counted_reader(
        value: DailyMarketTechnicalUniversePriceBookmarkV1,
        *,
        cancel_callback: Callable[[], object] | None = None,
    ) -> DailyMarketTechnicalUniversePriceBookmarkStateV1:
        reader_threads.append(get_ident())
        return original_reader(value, cancel_callback=cancel_callback)

    monkeypatch.setattr(
        controls_module,
        "read_daily_market_technical_universe_price_bookmark_v1",
        counted_reader,
    )
    emitted: list[object] = []
    controls.stateReady.connect(emitted.append)
    controls.open_selected()
    _wait(app, lambda: not controls.busy and controls.workers_remaining == 0)

    assert len(reader_threads) == 1 and reader_threads[0] != get_ident()
    assert len(emitted) == 1
    assert isinstance(emitted[0], DailyMarketTechnicalUniversePriceBookmarkStateV1)
    assert emitted[0].bookmark.to_dict() == bookmark.to_dict()
    assert controls.begin_shutdown() is True
    controls.close()


def test_price_view_source_read_uses_factory_captured_when_scheduled(
    app: QApplication,
    exact_price_store: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    view = DailyMarketTechnicalUniversePriceV1View(exact_price_store["store_root"])
    first = _ScopeProbe()
    replacement = _ScopeProbe()
    reader_started = Event()
    release_reader = Event()
    opener_threads: list[int] = []
    original_opener = price_view_module.open_daily_market_technical_universe_price_read_session_v1
    worker_queued, release_worker = Event(), Event()
    original_worker_type = price_view_module.TaskWorker

    class DelayedStartWorker(original_worker_type):
        def run(self) -> None:
            # 在執行 operation 前暫停，才可真正核對排程後替換 factory 的邊界。
            worker_queued.set()
            assert release_worker.wait(5.0)
            super().run()

    def checked_opener(
        *args: Any,
        **kwargs: Any,
    ) -> DailyMarketTechnicalUniversePriceReadSessionV1:
        opener_threads.append(get_ident())
        assert first.active_on_current_thread()
        reader_started.set()
        assert release_reader.wait(5.0)
        return original_opener(*args, **kwargs)
    try:
        view.refresh_sources()
        _wait(app, lambda: not view.busy and view.workers_remaining == 0, timeout_seconds=15.0)
        view.sources.setCurrentIndex(next(
            index
            for index in range(view.sources.count())
            if getattr(view.sources.itemData(index), "source_status", None) == "complete"
        ))
        assert view._source_read_scope_factory is None
        view.load_selected_source()
        _wait(app, lambda: not view.busy and view.workers_remaining == 0, timeout_seconds=15.0)
        assert view.current_page is not None

        monkeypatch.setattr(
            price_view_module,
            "open_daily_market_technical_universe_price_read_session_v1",
            checked_opener,
        )
        view.refresh_sources()
        _wait(app, lambda: not view.busy and view.workers_remaining == 0, timeout_seconds=15.0)
        view.sources.setCurrentIndex(next(
            index
            for index in range(view.sources.count())
            if getattr(view.sources.itemData(index), "source_status", None) == "complete"
        ))
        monkeypatch.setattr(price_view_module, "TaskWorker", DelayedStartWorker)
        view.set_source_read_scope_factory(first.factory)
        view.load_selected_source()
        assert worker_queued.wait(5.0)

        view.set_source_read_scope_factory(replacement.factory)
        release_worker.set()
        assert reader_started.wait(5.0)
        release_reader.set()
        _wait(app, lambda: not view.busy and view.workers_remaining == 0, timeout_seconds=15.0)

        assert first.entered.is_set() and first.exited.is_set()
        assert first.factory_thread_ids == opener_threads
        assert opener_threads[0] != first.main_thread_id
        assert replacement.factory_thread_ids == []
        assert view.current_query is not None
        assert view.current_page is not None
        assert not first.has_active_threads()
    finally:
        release_worker.set()
        release_reader.set()
        assert view.begin_shutdown() is True
        view.close()


def test_price_view_bookmark_restore_scope_runs_on_worker_and_exits_on_success(
    app: QApplication,
    exact_price_store: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bookmark = _make_bookmark(exact_price_store)
    probe = _ScopeProbe()
    view = DailyMarketTechnicalUniversePriceV1View(exact_price_store["store_root"])
    view.set_source_read_scope_factory(probe.factory)
    reader_started = Event()
    reader_threads: list[int] = []
    original_reader = price_view_module.read_daily_market_technical_universe_price_bookmark_v1

    def checked_reader(
        value: DailyMarketTechnicalUniversePriceBookmarkV1,
        *,
        cancel_callback: Callable[[], object] | None = None,
    ) -> DailyMarketTechnicalUniversePriceBookmarkStateV1:
        reader_threads.append(get_ident())
        assert probe.active_on_current_thread()
        reader_started.set()
        return original_reader(value, cancel_callback=cancel_callback)

    monkeypatch.setattr(
        price_view_module,
        "read_daily_market_technical_universe_price_bookmark_v1",
        checked_reader,
    )
    try:
        assert view.restore_bookmark(bookmark)
        assert reader_started.wait(5.0)
        _wait(app, lambda: not view.busy and view.workers_remaining == 0, timeout_seconds=15.0)

        assert probe.entered.is_set() and probe.exited.is_set()
        assert probe.factory_thread_ids == reader_threads
        assert reader_threads[0] != probe.main_thread_id
        assert view.current_page is not None
        assert view.current_page.page_identity_sha256 == bookmark.selected.page_identity_sha256
        assert not probe.has_active_threads()
    finally:
        assert view.begin_shutdown() is True
        view.close()


@pytest.mark.parametrize("outcome", ["error", "cancel"])
def test_price_view_bookmark_restore_scope_resets_after_error_or_cancel(
    app: QApplication,
    exact_price_store: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    outcome: str,
) -> None:
    bookmark = _make_bookmark(exact_price_store)
    probe = _ScopeProbe()
    view = DailyMarketTechnicalUniversePriceV1View(exact_price_store["store_root"])
    view.set_source_read_scope_factory(probe.factory)
    reader_started = Event()
    release_reader = Event()

    def failing_reader(
        _value: DailyMarketTechnicalUniversePriceBookmarkV1,
        *,
        cancel_callback: Callable[[], object] | None = None,
    ) -> DailyMarketTechnicalUniversePriceBookmarkStateV1:
        assert probe.active_on_current_thread()
        reader_started.set()
        if outcome == "cancel":
            assert release_reader.wait(5.0)
            if cancel_callback is not None and cancel_callback():
                raise InterruptedError("synthetic bookmark cancellation")
        raise ValueError("synthetic bookmark reader failure")

    monkeypatch.setattr(
        price_view_module,
        "read_daily_market_technical_universe_price_bookmark_v1",
        failing_reader,
    )
    try:
        assert view.restore_bookmark(bookmark)
        assert reader_started.wait(5.0)
        if outcome == "cancel":
            view.cancel()
            release_reader.set()
        _wait(app, lambda: not view.busy and view.workers_remaining == 0, timeout_seconds=15.0)

        assert probe.entered.is_set() and probe.exited.is_set()
        assert not probe.has_active_threads()
        assert reader_started.is_set()
        assert view.current_page is None
    finally:
        release_reader.set()
        assert view.begin_shutdown() is True
        view.close()


def test_price_view_bookmark_restore_without_factory_keeps_legacy_reader_path(
    app: QApplication,
    exact_price_store: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bookmark = _make_bookmark(exact_price_store)
    view = DailyMarketTechnicalUniversePriceV1View(exact_price_store["store_root"])
    view.set_source_read_scope_factory(None)
    reader_threads: list[int] = []
    original_reader = price_view_module.read_daily_market_technical_universe_price_bookmark_v1

    def counted_reader(
        value: DailyMarketTechnicalUniversePriceBookmarkV1,
        *,
        cancel_callback: Callable[[], object] | None = None,
    ) -> DailyMarketTechnicalUniversePriceBookmarkStateV1:
        reader_threads.append(get_ident())
        return original_reader(value, cancel_callback=cancel_callback)

    monkeypatch.setattr(
        price_view_module,
        "read_daily_market_technical_universe_price_bookmark_v1",
        counted_reader,
    )
    try:
        assert view.restore_bookmark(bookmark)
        _wait(app, lambda: not view.busy and view.workers_remaining == 0, timeout_seconds=15.0)
        assert len(reader_threads) == 1 and reader_threads[0] != get_ident()
        assert view.current_page is not None
    finally:
        assert view.begin_shutdown() is True
        view.close()
