"""F07 收藏控制項沿 exact bookmark pins fresh 重開。"""

from __future__ import annotations

import time
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from typing import Any, Callable, cast

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel

from app_module.daily_market_research_bookmark import DailyMarketResearchBookmarkError
from app_module.daily_market_technical_universe_price_bookmark_v1 import (
    DailyMarketTechnicalUniversePriceBookmarkStateV1,
    DailyMarketTechnicalUniversePriceBookmarkV1,
    create_daily_market_technical_universe_price_bookmark_v1,
)
from app_module.daily_market_technical_universe_price_comparison_v1 import (
    DailyMarketTechnicalUniversePriceSelectionV1,
)
from app_module.daily_market_technical_universe_price_query_v1 import (
    DailyMarketTechnicalUniversePriceReadSessionV1,
)
from app_module.watchlist_service import (
    TECHNICAL_UNIVERSE_PRICE_BOOKMARK_SOURCE,
    WatchlistService,
)
from tests.test_daily_market_technical_universe_price_query_v1 import (
    _open_session,
    exact_price_store,
)
from ui_qt.views.daily_market_technical_universe_price_view_v1 import (
    DailyMarketTechnicalUniversePriceV1View,
)
from ui_qt.widgets.daily_market_technical_price_bookmark_controls_v1 import (
    DailyMarketTechnicalPriceBookmarkControlsV1,
)
from ui_qt.workers.task_worker import TaskWorker
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
            raise AssertionError("F07 收藏控制項背景工作逾時")
        time.sleep(0.01)
    app.processEvents()


def _service(tmp_path: Path) -> WatchlistService:
    output = tmp_path / "watchlist_output"
    config = SimpleNamespace(
        output_root=output,
        resolve_output_path=lambda name: output / name,
    )
    return WatchlistService(config)


def _bookmark_for(
    session: DailyMarketTechnicalUniversePriceReadSessionV1,
    stock_code: str,
    *,
    scroll_position: int,
) -> DailyMarketTechnicalUniversePriceBookmarkV1:
    query = session.create_query(unknown_price_policy="include")
    result = session.execute(query)
    page = result.read_page(result.create_page_request(0, page_size=4))
    DailyMarketTechnicalUniversePriceSelectionV1.from_page(query, page, stock_code)
    return create_daily_market_technical_universe_price_bookmark_v1(
        query,
        page,
        stock_code,
        scroll_position=scroll_position,
        comparison_selections=(),
    )


def _add(service: WatchlistService, bookmark: DailyMarketTechnicalUniversePriceBookmarkV1) -> None:
    result = service.add_research_bookmark(bookmark)
    assert result.status == "added"


def test_controls_fresh_reopen_hands_same_operation_state_to_price_view_once(
    app: QApplication,
    exact_price_store: dict[str, Any],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service(tmp_path)
    session = _open_session(exact_price_store)
    bookmark = _bookmark_for(session, "S0001", scroll_position=1)
    _add(service, bookmark)

    reader_calls = 0
    original_reader = controls_module.read_daily_market_technical_universe_price_bookmark_v1

    def counted_reader(
        value: DailyMarketTechnicalUniversePriceBookmarkV1,
        *,
        cancel_callback: Callable[[], object] | None = None,
    ) -> DailyMarketTechnicalUniversePriceBookmarkStateV1:
        nonlocal reader_calls
        reader_calls += 1
        return original_reader(value, cancel_callback=cancel_callback)

    monkeypatch.setattr(controls_module, "read_daily_market_technical_universe_price_bookmark_v1", counted_reader)
    controls = DailyMarketTechnicalPriceBookmarkControlsV1(service)
    view = DailyMarketTechnicalUniversePriceV1View(exact_price_store["store_root"])
    view.resize(520, 170)
    view.show()
    app.processEvents()
    states: list[object] = []
    applied: list[bool] = []

    def apply_state(state: object) -> None:
        states.append(state)
        if not isinstance(state, DailyMarketTechnicalUniversePriceBookmarkStateV1):
            applied.append(False)
            return
        applied.append(view.restore_bookmark_state(state))

    controls.stateReady.connect(apply_state)
    assert controls.restore_selection(bookmark.bookmark_id) == "queued"
    _wait(app, lambda: not controls.busy and controls.workers_remaining == 0)
    assert controls.bookmarks.count() == 1
    current_entry = controls._current_entry()
    assert current_entry is not None
    assert current_entry.bookmark_id == bookmark.bookmark_id
    controls.open_selected()
    _wait(app, lambda: not controls.busy and controls.workers_remaining == 0)

    assert reader_calls == 1
    assert len(states) == 1 and isinstance(states[0], DailyMarketTechnicalUniversePriceBookmarkStateV1)
    assert applied == [True]
    assert view.current_query is not None
    assert view.current_query.to_json() == bookmark.selected.query_json
    row = view._selected_row()
    assert row is not None and row.technical_row.stock_code == "S0001"
    assert view.table.verticalScrollBar().value() == bookmark.scroll_position
    assert "沒有重新開來源" in view.status.text()
    assert controls.begin_shutdown() is True
    assert view.begin_shutdown() is True
    controls.close()
    view.close()


def test_invalid_price_bookmark_candidate_stays_visible_and_disabled(
    app: QApplication,
) -> None:
    class InvalidService:
        def get_stocks(self, _watchlist_id: str) -> list[dict[str, object]]:
            return [{
                "stock_code": "S0001",
                "stock_name": "S0001",
                "source": TECHNICAL_UNIVERSE_PRICE_BOOKMARK_SOURCE,
                "source_id": "b" * 64,
                "research_bookmark": {
                    "schema_version": "daily-market-technical-universe-price-bookmark.v1",
                },
            }]

        def get_research_bookmark(self, _bookmark_id: str, _watchlist_id: str) -> None:
            raise DailyMarketResearchBookmarkError(
                "synthetic_price_bookmark_corrupt",
                "synthetic corrupt F07 payload",
            )

    controls = DailyMarketTechnicalPriceBookmarkControlsV1(cast(WatchlistService, InvalidService()))
    title = controls.findChild(QLabel, "dailyMarketTechnicalPriceBookmarkTitleV1")
    assert title is not None and title.text() == "原價格條件研究收藏"
    assert controls.bookmarks.accessibleName() == "原價格條件研究收藏列表"
    controls.refresh_bookmarks()
    _wait(app, lambda: not controls.busy and controls.workers_remaining == 0)
    assert controls.bookmarks.count() == 1
    item = controls.bookmarks.item(0)
    entry = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
    assert entry is not None and entry.error_code == "synthetic_price_bookmark_corrupt"
    assert controls.open_button.isEnabled() is False
    assert "無法核驗" in controls.bookmarks.item(0).text()
    assert controls.begin_shutdown() is True
    controls.close()


def test_open_bookmark_before_initial_list_automatically_opens_after_fresh_list(
    app: QApplication,
    exact_price_store: dict[str, Any],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service(tmp_path)
    bookmark = _bookmark_for(_open_session(exact_price_store), "S0001", scroll_position=0)
    _add(service, bookmark)
    reader_calls = 0
    original_reader = controls_module.read_daily_market_technical_universe_price_bookmark_v1

    def counted_reader(
        value: DailyMarketTechnicalUniversePriceBookmarkV1,
        *,
        cancel_callback: Callable[[], object] | None = None,
    ) -> DailyMarketTechnicalUniversePriceBookmarkStateV1:
        nonlocal reader_calls
        reader_calls += 1
        return original_reader(value, cancel_callback=cancel_callback)

    monkeypatch.setattr(controls_module, "read_daily_market_technical_universe_price_bookmark_v1", counted_reader)
    controls = DailyMarketTechnicalPriceBookmarkControlsV1(service)
    states: list[object] = []
    controls.stateReady.connect(states.append)

    assert controls.open_bookmark(bookmark.bookmark_id) == "queued"
    _wait(app, lambda: not controls.busy and controls.workers_remaining == 0)

    assert controls.bookmarks.count() == 1
    entry = controls._current_entry()
    assert entry is not None and entry.bookmark_id == bookmark.bookmark_id
    assert reader_calls == 1
    assert len(states) == 1 and isinstance(states[0], DailyMarketTechnicalUniversePriceBookmarkStateV1)
    assert controls.begin_shutdown() is True
    controls.close()


def test_open_bookmark_queued_during_refresh_uses_one_fresh_reader(
    app: QApplication,
    exact_price_store: dict[str, Any],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service(tmp_path)
    bookmark = _bookmark_for(_open_session(exact_price_store), "S0001", scroll_position=0)
    _add(service, bookmark)
    original_list = controls_module._list_price_bookmarks
    original_reader = controls_module.read_daily_market_technical_universe_price_bookmark_v1
    list_started = Event()
    release_list = Event()
    list_calls = 0
    reader_calls = 0

    def delayed_list(
        watchlist_service: WatchlistService,
        watchlist_id: str,
        cancel_callback: Callable[[], object] | None = None,
    ) -> tuple[object, ...]:
        nonlocal list_calls
        list_calls += 1
        list_started.set()
        if not release_list.wait(5.0):
            raise TimeoutError("synthetic refresh barrier timeout")
        if cancel_callback is not None and cancel_callback():
            raise InterruptedError("synthetic list cancelled")
        return original_list(watchlist_service, watchlist_id, cancel_callback)

    def counted_reader(
        value: DailyMarketTechnicalUniversePriceBookmarkV1,
        *,
        cancel_callback: Callable[[], object] | None = None,
    ) -> DailyMarketTechnicalUniversePriceBookmarkStateV1:
        nonlocal reader_calls
        reader_calls += 1
        return original_reader(value, cancel_callback=cancel_callback)

    monkeypatch.setattr(controls_module, "_list_price_bookmarks", delayed_list)
    monkeypatch.setattr(controls_module, "read_daily_market_technical_universe_price_bookmark_v1", counted_reader)
    controls = DailyMarketTechnicalPriceBookmarkControlsV1(service)
    states: list[object] = []
    controls.stateReady.connect(states.append)
    controls.refresh_bookmarks()
    assert list_started.wait(5.0)
    assert controls.open_bookmark(bookmark.bookmark_id) == "queued"
    release_list.set()
    _wait(app, lambda: not controls.busy and controls.workers_remaining == 0)

    assert list_calls == 1
    assert reader_calls == 1
    assert len(states) == 1 and isinstance(states[0], DailyMarketTechnicalUniversePriceBookmarkStateV1)
    assert states[0].bookmark.to_dict() == bookmark.to_dict()
    assert controls.begin_shutdown() is True
    controls.close()


def test_cancel_clears_queued_open_before_list_finishes(
    app: QApplication,
    exact_price_store: dict[str, Any],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service(tmp_path)
    bookmark = _bookmark_for(_open_session(exact_price_store), "S0001", scroll_position=0)
    _add(service, bookmark)
    original_list = controls_module._list_price_bookmarks
    list_started = Event()
    release_list = Event()
    reader_calls = 0

    def delayed_list(
        watchlist_service: WatchlistService,
        watchlist_id: str,
        cancel_callback: Callable[[], object] | None = None,
    ) -> tuple[object, ...]:
        list_started.set()
        if not release_list.wait(5.0):
            raise TimeoutError("synthetic cancellation barrier timeout")
        if cancel_callback is not None and cancel_callback():
            raise InterruptedError("synthetic list cancelled")
        return original_list(watchlist_service, watchlist_id, cancel_callback)

    def forbidden_reader(*_args: object, **_kwargs: object) -> object:
        nonlocal reader_calls
        reader_calls += 1
        raise AssertionError("取消後不得重開收藏來源")

    monkeypatch.setattr(controls_module, "_list_price_bookmarks", delayed_list)
    monkeypatch.setattr(controls_module, "read_daily_market_technical_universe_price_bookmark_v1", forbidden_reader)
    controls = DailyMarketTechnicalPriceBookmarkControlsV1(service)
    states: list[object] = []
    controls.stateReady.connect(states.append)

    assert controls.open_bookmark(bookmark.bookmark_id) == "queued"
    assert list_started.wait(5.0)
    controls.cancel()
    release_list.set()
    _wait(app, lambda: not controls.busy and controls.workers_remaining == 0)

    assert reader_calls == 0
    assert states == []
    assert controls._pending_open_bookmark_id == ""
    assert controls.begin_shutdown() is True
    controls.close()


def test_queued_open_keeps_latest_explicit_id_and_emits_that_fresh_state(
    app: QApplication,
    exact_price_store: dict[str, Any],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service(tmp_path)
    session = _open_session(exact_price_store)
    first = _bookmark_for(session, "S0001", scroll_position=0)
    second = _bookmark_for(session, "S0002", scroll_position=0)
    _add(service, first)
    _add(service, second)
    original_list = controls_module._list_price_bookmarks
    original_reader = controls_module.read_daily_market_technical_universe_price_bookmark_v1
    list_started = Event()
    release_list = Event()
    reader_calls = 0

    def delayed_list(
        watchlist_service: WatchlistService,
        watchlist_id: str,
        cancel_callback: Callable[[], object] | None = None,
    ) -> tuple[object, ...]:
        list_started.set()
        if not release_list.wait(5.0):
            raise TimeoutError("synthetic queued-open barrier timeout")
        if cancel_callback is not None and cancel_callback():
            raise InterruptedError("synthetic list cancelled")
        return original_list(watchlist_service, watchlist_id, cancel_callback)

    def counted_reader(
        value: DailyMarketTechnicalUniversePriceBookmarkV1,
        *,
        cancel_callback: Callable[[], object] | None = None,
    ) -> DailyMarketTechnicalUniversePriceBookmarkStateV1:
        nonlocal reader_calls
        reader_calls += 1
        return original_reader(value, cancel_callback=cancel_callback)

    monkeypatch.setattr(controls_module, "_list_price_bookmarks", delayed_list)
    monkeypatch.setattr(controls_module, "read_daily_market_technical_universe_price_bookmark_v1", counted_reader)
    controls = DailyMarketTechnicalPriceBookmarkControlsV1(service)
    states: list[object] = []
    controls.stateReady.connect(states.append)
    controls.refresh_bookmarks()
    assert list_started.wait(5.0)

    assert controls.open_bookmark(first.bookmark_id) == "queued"
    assert controls.open_bookmark(second.bookmark_id) == "queued"
    release_list.set()
    _wait(app, lambda: not controls.busy and controls.workers_remaining == 0)

    assert reader_calls == 1
    assert len(states) == 1 and isinstance(states[0], DailyMarketTechnicalUniversePriceBookmarkStateV1)
    assert states[0].bookmark.to_dict() == second.to_dict()
    current_entry = controls._current_entry()
    assert current_entry is not None and current_entry.bookmark_id == second.bookmark_id
    assert controls.begin_shutdown() is True
    controls.close()


@pytest.mark.parametrize("use_shutdown", [False, True], ids=["cancel", "shutdown"])
def test_cancel_or_shutdown_clears_queued_open_and_waits_for_worker(
    app: QApplication,
    exact_price_store: dict[str, Any],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    use_shutdown: bool,
) -> None:
    service = _service(tmp_path)
    bookmark = _bookmark_for(_open_session(exact_price_store), "S0001", scroll_position=0)
    _add(service, bookmark)
    original_list = controls_module._list_price_bookmarks
    list_started = Event()
    release_list = Event()
    reader_calls = 0

    def delayed_list(
        watchlist_service: WatchlistService,
        watchlist_id: str,
        cancel_callback: Callable[[], object] | None = None,
    ) -> tuple[object, ...]:
        list_started.set()
        if not release_list.wait(5.0):
            raise TimeoutError("synthetic shutdown barrier timeout")
        if cancel_callback is not None and cancel_callback():
            raise InterruptedError("synthetic list cancelled")
        return original_list(watchlist_service, watchlist_id, cancel_callback)

    def forbidden_reader(*_args: object, **_kwargs: object) -> object:
        nonlocal reader_calls
        reader_calls += 1
        raise AssertionError("取消或關閉後不得重開收藏來源")

    monkeypatch.setattr(controls_module, "_list_price_bookmarks", delayed_list)
    monkeypatch.setattr(controls_module, "read_daily_market_technical_universe_price_bookmark_v1", forbidden_reader)
    controls = DailyMarketTechnicalPriceBookmarkControlsV1(service)
    states: list[object] = []
    controls.stateReady.connect(states.append)
    assert controls.open_bookmark(bookmark.bookmark_id) == "queued"
    assert list_started.wait(5.0)

    if use_shutdown:
        assert controls.begin_shutdown() is False
    else:
        controls.cancel()
    assert controls._pending_open_bookmark_id == ""
    release_list.set()
    _wait(app, lambda: not controls.busy and controls.workers_remaining == 0)

    assert reader_calls == 0
    assert states == []
    assert controls.begin_shutdown() is True
    controls.close()


def test_stale_native_finished_callback_cannot_consume_current_open_request(app: QApplication) -> None:
    controls = DailyMarketTechnicalPriceBookmarkControlsV1(cast(WatchlistService, object()))
    current = TaskWorker(lambda: None)
    stale = TaskWorker(lambda: None)
    target = "a" * 64
    controls._worker = current
    controls._operation = "list"
    controls._pending_open_bookmark_id = target
    stale.native_thread_finished.connect(controls._on_worker_thread_finished)
    stale.native_thread_finished.emit()

    assert controls._worker is current
    assert controls._pending_open_bookmark_id == target
    assert controls._operation == "list"
    controls._worker = None
    current.deleteLater()
    stale.deleteLater()
    assert controls.begin_shutdown() is True
    controls.close()


def test_selection_change_cancel_and_shutdown_wait_for_native_worker(
    app: QApplication,
    exact_price_store: dict[str, Any],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service(tmp_path)
    session = _open_session(exact_price_store)
    first = _bookmark_for(session, "S0001", scroll_position=0)
    second = _bookmark_for(session, "S0002", scroll_position=1)
    _add(service, first)
    _add(service, second)

    original_reader = controls_module.read_daily_market_technical_universe_price_bookmark_v1
    started = Event()
    release = Event()
    calls = 0

    def delayed_reader(
        value: DailyMarketTechnicalUniversePriceBookmarkV1,
        *,
        cancel_callback: Callable[[], object] | None = None,
    ) -> DailyMarketTechnicalUniversePriceBookmarkStateV1:
        nonlocal calls
        calls += 1
        started.set()
        release.wait(10.0)
        if cancel_callback is not None and cancel_callback():
            raise InterruptedError("synthetic_price_bookmark_cancelled")
        return original_reader(value, cancel_callback=cancel_callback)

    monkeypatch.setattr(controls_module, "read_daily_market_technical_universe_price_bookmark_v1", delayed_reader)
    controls = DailyMarketTechnicalPriceBookmarkControlsV1(service)
    published: list[object] = []
    controls.stateReady.connect(published.append)
    controls.refresh_bookmarks()
    _wait(app, lambda: not controls.busy and controls.workers_remaining == 0)
    assert controls.bookmarks.count() == 2
    controls.restore_selection(first.bookmark_id)
    controls.open_selected()
    assert started.wait(5.0)
    controls.refresh_bookmarks()
    assert controls._refresh_pending is True
    def row_bookmark_id(row: int) -> str:
        item = controls.bookmarks.item(row)
        entry = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        return str(getattr(entry, "bookmark_id", ""))

    second_row = next(row for row in range(controls.bookmarks.count()) if row_bookmark_id(row) == second.bookmark_id)
    controls.bookmarks.setCurrentRow(second_row)
    release.set()
    _wait(app, lambda: not controls.busy and controls.workers_remaining == 0)
    assert calls == 1
    assert published == []
    current_entry = controls._current_entry()
    assert current_entry is not None
    assert current_entry.bookmark_id == second.bookmark_id

    started.clear()
    release.clear()
    controls.open_selected()
    assert started.wait(5.0)
    assert controls.begin_shutdown() is False
    release.set()
    _wait(app, lambda: controls.workers_remaining == 0)
    _wait(app, lambda: not controls.busy)
    assert controls.begin_shutdown() is True
    assert calls == 2
    assert published == []
    controls.close()
