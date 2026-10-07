"""完整母體收藏控制項沿真實觀察清單 COW 背景重開固定來源。"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
import sqlite3
import threading
import time
from types import SimpleNamespace
from typing import Any, cast

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from app_module.daily_market_technical_universe_v4_bookmark import (
    DAILY_MARKET_TECHNICAL_UNIVERSE_V4_BOOKMARK_SOURCE,
    DailyMarketTechnicalUniverseV4Bookmark,
    DailyMarketTechnicalUniverseV4BookmarkState,
    create_daily_market_technical_universe_v4_bookmark,
)
from app_module.daily_market_technical_universe_v4_producer import (
    DailyMarketTechnicalUniverseV4ProductionRequest,
    produce_daily_market_technical_universe_v4,
)
from app_module.daily_market_technical_universe_v4_query import (
    DailyMarketTechnicalUniverseV4Query,
)
from app_module.daily_market_technical_universe_v4_store import (
    DailyMarketTechnicalUniverseV4Cohort,
)
from app_module.rule_research_sample_capture import ResearchCaptureWriteScope
from app_module.watchlist_service import WatchlistService
from ui_qt.widgets.technical_universe_bookmark_controls import (
    DailyMarketTechnicalUniverseV4BookmarkControls,
)


@pytest.fixture(scope="module")
def app() -> QApplication:
    instance = cast(QApplication | None, QApplication.instance())
    if instance is None:
        instance = QApplication([])
    return instance


def _wait_for(app: QApplication, predicate: Any, *, timeout_seconds: float = 30.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while not predicate():
        app.processEvents()
        if time.monotonic() >= deadline:
            raise AssertionError("完整母體收藏背景工作逾時")
        time.sleep(0.005)
    app.processEvents()


def _create_saved_cow_bookmark(tmp_path: Path) -> tuple[
    WatchlistService,
    str,
    str,
    str,
]:
    """以短期 SQLite producer 與隔離 Watchlist COW 建立真實收藏。"""

    from zoneinfo import ZoneInfo

    database = tmp_path / "synthetic-daily-prices.sqlite"
    decision = date(2026, 10, 6)
    stock_codes = ("2382", "9999")
    connection = sqlite3.connect(database)
    with connection:
        connection.execute(
            "CREATE TABLE daily_prices "
            "(日期 TEXT, 證券代號 TEXT, 開盤價 TEXT, 最高價 TEXT, 最低價 TEXT, 收盤價 TEXT, 成交股數 INTEGER)"
        )
        connection.executemany(
            "INSERT INTO daily_prices VALUES (?,?,?,?,?,?,?)",
            [
                (
                    (decision - timedelta(days=39 - offset)).isoformat(),
                    code,
                    str(100 + offset),
                    str(101 + offset),
                    str(99 + offset),
                    str(100 + offset),
                    1000 + offset,
                )
                for code in stock_codes
                for offset in range(40)
            ],
        )
    connection.close()

    capture_scope = ResearchCaptureWriteScope(tmp_path / "research-output", database)
    cohort = DailyMarketTechnicalUniverseV4Cohort.create(
        universe_id="synthetic-bookmark-controls",
        population_version="fixture-v1",
        decision_date=decision,
        raw_stock_codes=stock_codes,
    )
    store_root = capture_scope.root / "technical-universe"
    produced = produce_daily_market_technical_universe_v4(
        DailyMarketTechnicalUniverseV4ProductionRequest(
            source_database=database,
            cohort=cohort,
            decision_cutoff=datetime(
                2026, 10, 6, 16, 0, tzinfo=ZoneInfo("Asia/Taipei")
            ),
            store_output_root=store_root,
            research_scope=capture_scope,
        )
    )
    assert produced.status == "complete", produced.to_dict()
    assert produced.plan is not None and produced.receipt is not None
    assert produced.plan_sha256 is not None
    query = DailyMarketTechnicalUniverseV4Query.create(
        store_output_root=store_root,
        generation_identity_sha256=produced.plan.generation_identity_sha256,
        plan_identity_sha256=produced.plan.identity_sha256,
        plan_sha256=produced.plan_sha256,
        receipt_identity_sha256=produced.receipt.identity_sha256,
        receipt_sha256=produced.receipt.content_sha256,
        page_size=10,
    )
    bookmark = create_daily_market_technical_universe_v4_bookmark(
        query,
        "2382",
        scroll_position=11,
    )

    watchlist_root = tmp_path / "watchlist-output"
    config = SimpleNamespace(
        output_root=watchlist_root,
        resolve_output_path=lambda relative: watchlist_root / relative,
    )
    initial_service = WatchlistService(config)
    assert initial_service.add_research_bookmark(bookmark).status == "added"
    # 這筆列刻意宣告 full-N source，卻沒有 typed bookmark，UI 必須明示拒絕。
    assert initial_service.add_stocks(
        [{"stock_code": "7777", "stock_name": "錯誤收藏列"}],
        source=DAILY_MARKET_TECHNICAL_UNIVERSE_V4_BOOKMARK_SOURCE,
    ) == 1
    # 一般觀察清單列不應混進 full-N 收藏列表。
    assert initial_service.add_stocks(
        [{"stock_code": "8888", "stock_name": "一般列"}],
        source="manual",
    ) == 1
    assert initial_service.upgrade_to_repository().is_repository

    repository, storage_status = WatchlistService.discover_repository(config)
    assert repository is not None
    service = WatchlistService(
        config,
        repository=repository,
        storage_status=storage_status,
    )
    # 後續 UI 只重開保存的 child／manifest；刪除本測試自己建立的行情 DB。
    database.unlink()
    return service, bookmark.bookmark_id, str(store_root), str(watchlist_root)


def test_real_cow_bookmark_is_listed_and_background_reopen_emits_typed_state(
    app: QApplication,
    tmp_path: Path,
) -> None:
    service, bookmark_id, _store_root, _watchlist_root = _create_saved_cow_bookmark(tmp_path)
    watchlist_before = service.get_watchlist()
    assert watchlist_before is not None
    revision_before = watchlist_before.revision
    widget = DailyMarketTechnicalUniverseV4BookmarkControls(service)
    emitted: list[object] = []
    widget.stateReady.connect(emitted.append)
    widget.show()

    try:
        widget.refresh_bookmarks()
        _wait_for(app, lambda: widget._worker is None)
        assert widget.bookmarks.count() == 2
        assert "2026-10-06｜2382｜synthetic-bookmark-controls" in widget.bookmarks.item(0).text()
        assert "收藏格式錯誤" in widget.bookmarks.item(1).text()

        widget.bookmarks.setCurrentRow(1)
        assert widget.open_button.isEnabled() is False
        assert "拒絕讀回" in widget.status_label.text()

        widget.bookmarks.setCurrentRow(0)
        assert widget.open_button.isEnabled() is True
        widget.open_button.click()
        _wait_for(app, lambda: widget._worker is None)

        assert len(emitted) == 1
        state = emitted[0]
        assert isinstance(state, DailyMarketTechnicalUniverseV4BookmarkState)
        assert state.bookmark.bookmark_id == bookmark_id
        assert state.bookmark.source == DAILY_MARKET_TECHNICAL_UNIVERSE_V4_BOOKMARK_SOURCE
        assert state.selected_stock.snapshot.stock_code == "2382"
        assert state.bookmark.origin_query.query_identity_sha256 == state.origin_page.query.query_identity_sha256
        watchlist_after = service.get_watchlist()
        assert watchlist_after is not None
        assert watchlist_after.revision == revision_before
        assert "已核驗並重開" in widget.status_label.text()
    finally:
        widget.close()
        app.processEvents()


class _BlockingWatchlistService:
    """只在真 COW typed reader 前設 barrier，資料讀取仍走正式實作。"""

    def __init__(
        self,
        service: WatchlistService,
        entered: threading.Event,
        release: threading.Event,
    ) -> None:
        self.service = service
        self.entered = entered
        self.release = release
        self.list_calls = 0
        self.events: list[str] = []

    def get_stocks(self, watchlist_id: str = "default") -> list[dict[str, Any]]:
        self.list_calls += 1
        self.events.append("list")
        return self.service.get_stocks(watchlist_id)

    def get_technical_universe_research_bookmark_state(
        self,
        bookmark_id: str,
        watchlist_id: str = "default",
        *,
        cancel_callback=None,
    ) -> DailyMarketTechnicalUniverseV4BookmarkState:
        self.events.append("open")
        self.entered.set()
        if not self.release.wait(timeout=15):
            raise AssertionError("測試 barrier 未釋放")
        return self.service.get_technical_universe_research_bookmark_state(
            bookmark_id,
            watchlist_id,
            cancel_callback=cancel_callback,
        )


class _CoalescingListWatchlistService:
    """在兩次真實 COW 列表讀取前以 event 控制更新時序。"""

    def __init__(
        self,
        service: WatchlistService,
        first_entered: threading.Event,
        first_release: threading.Event,
        second_entered: threading.Event,
        second_release: threading.Event,
    ) -> None:
        self.service = service
        self.first_entered = first_entered
        self.first_release = first_release
        self.second_entered = second_entered
        self.second_release = second_release
        self._calls = 0
        self._lock = threading.Lock()

    @property
    def list_calls(self) -> int:
        with self._lock:
            return self._calls

    def get_stocks(self, watchlist_id: str = "default") -> list[dict[str, Any]]:
        with self._lock:
            self._calls += 1
            call_number = self._calls
        barrier = {
            1: (self.first_entered, self.first_release),
            2: (self.second_entered, self.second_release),
        }.get(call_number)
        if barrier is not None:
            entered, release = barrier
            entered.set()
            if not release.wait(timeout=15):
                raise AssertionError("列表 barrier 未釋放")
        return self.service.get_stocks(watchlist_id)

    def get_technical_universe_research_bookmark_state(
        self,
        bookmark_id: str,
        watchlist_id: str = "default",
        *,
        cancel_callback=None,
    ) -> DailyMarketTechnicalUniverseV4BookmarkState:
        return self.service.get_technical_universe_research_bookmark_state(
            bookmark_id,
            watchlist_id,
            cancel_callback=cancel_callback,
        )


def _select_bookmark(widget: DailyMarketTechnicalUniverseV4BookmarkControls, bookmark_id: str) -> int:
    for row_number in range(widget.bookmarks.count()):
        item = widget.bookmarks.item(row_number)
        entry = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        if getattr(entry, "bookmark_id", "") == bookmark_id:
            widget.bookmarks.setCurrentRow(row_number)
            return row_number
    raise AssertionError(f"找不到指定收藏：{bookmark_id}")


def _selected_bookmark_id(widget: DailyMarketTechnicalUniverseV4BookmarkControls) -> str:
    item = widget.bookmarks.currentItem()
    entry = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
    return str(getattr(entry, "bookmark_id", "") or "")


def _save_second_bookmark(service: WatchlistService, bookmark_id: str) -> str:
    original = service.get_research_bookmark(bookmark_id)
    assert isinstance(original, DailyMarketTechnicalUniverseV4Bookmark)
    added = create_daily_market_technical_universe_v4_bookmark(
        original.origin_query,
        "9999",
        scroll_position=23,
    )
    result = service.add_research_bookmark(added)
    assert result.status == "added", result
    return added.bookmark_id


def test_repeated_busy_refreshes_coalesce_and_keep_exact_selection(
    app: QApplication,
    tmp_path: Path,
) -> None:
    service, bookmark_id, _store_root, _watchlist_root = _create_saved_cow_bookmark(tmp_path)
    first_entered = threading.Event()
    first_release = threading.Event()
    second_entered = threading.Event()
    second_release = threading.Event()
    wrapper = _CoalescingListWatchlistService(
        service,
        first_entered,
        first_release,
        second_entered,
        second_release,
    )
    widget = DailyMarketTechnicalUniverseV4BookmarkControls(wrapper)  # type: ignore[arg-type]  # barrier 僅包裝真 COW 列表讀取。
    widget.show()

    try:
        widget.refresh_bookmarks()
        assert first_entered.wait(timeout=10)
        widget.refresh_bookmarks()
        widget.refresh_bookmarks()
        widget.refresh_bookmarks()
        assert widget._refresh_pending is True
        assert wrapper.list_calls == 1

        first_release.set()
        _wait_for(app, second_entered.is_set)
        _wait_for(app, lambda: widget.bookmarks.count() == 2)
        _select_bookmark(widget, bookmark_id)

        new_bookmark_id = _save_second_bookmark(service, bookmark_id)
        second_release.set()
        _wait_for(
            app,
            lambda: widget._worker is None
            and widget.bookmarks.count() == 3
            and wrapper.list_calls == 2,
        )

        assert widget._refresh_pending is False
        assert _selected_bookmark_id(widget) == bookmark_id
        visible_ids = {
            getattr(
                widget.bookmarks.item(row).data(Qt.ItemDataRole.UserRole),
                "bookmark_id",
                "",
            )
            for row in range(widget.bookmarks.count())
        }
        assert new_bookmark_id in visible_ids

        removed = service.remove_research_bookmark(bookmark_id)
        assert removed.status == "removed", removed
        widget.refresh_bookmarks()
        _wait_for(
            app,
            lambda: widget._worker is None
            and widget.bookmarks.count() == 2
            and wrapper.list_calls == 3,
        )
        assert widget.bookmarks.currentRow() == -1
        assert widget.open_button.isEnabled() is False
    finally:
        first_release.set()
        second_release.set()
        widget.close()
        _wait_for(app, lambda: widget._worker is None)
        app.processEvents()


def test_pending_refresh_waits_for_open_result_then_shows_new_bookmark(
    app: QApplication,
    tmp_path: Path,
) -> None:
    service, bookmark_id, _store_root, _watchlist_root = _create_saved_cow_bookmark(tmp_path)
    entered = threading.Event()
    release = threading.Event()
    wrapper = _BlockingWatchlistService(service, entered, release)
    widget = DailyMarketTechnicalUniverseV4BookmarkControls(wrapper)  # type: ignore[arg-type]  # barrier 僅包裝真 reader 以控制完成時序。
    emitted: list[object] = []

    def collect_state(value: object) -> None:
        emitted.append(value)
        wrapper.events.append("state_ready")

    widget.stateReady.connect(collect_state)
    widget.show()

    try:
        widget.refresh_bookmarks()
        _wait_for(app, lambda: widget._worker is None)
        assert wrapper.list_calls == 1
        wrapper.events.clear()
        _select_bookmark(widget, bookmark_id)
        widget.open_selected()
        assert entered.wait(timeout=10)

        widget.refresh_bookmarks()
        widget.refresh_bookmarks()
        widget.refresh_bookmarks()
        assert widget._refresh_pending is True
        assert wrapper.list_calls == 1
        new_bookmark_id = _save_second_bookmark(service, bookmark_id)

        release.set()
        _wait_for(
            app,
            lambda: widget._worker is None and widget.bookmarks.count() == 3,
        )

        assert len(emitted) == 1
        state = emitted[0]
        assert isinstance(state, DailyMarketTechnicalUniverseV4BookmarkState)
        assert state.bookmark.bookmark_id == bookmark_id
        assert wrapper.events.index("state_ready") < wrapper.events.index("list")
        assert wrapper.list_calls == 2
        assert _selected_bookmark_id(widget) == bookmark_id
        visible_ids = {
            getattr(
                widget.bookmarks.item(row).data(Qt.ItemDataRole.UserRole),
                "bookmark_id",
                "",
            )
            for row in range(widget.bookmarks.count())
        }
        assert new_bookmark_id in visible_ids
    finally:
        release.set()
        if not widget._closing:
            widget.close()
        _wait_for(app, lambda: widget._worker is None)
        app.processEvents()


@pytest.mark.parametrize("action", ("cancel", "close"))
def test_cancel_or_close_clears_pending_refresh_without_restart(
    app: QApplication,
    tmp_path: Path,
    action: str,
) -> None:
    service, bookmark_id, _store_root, _watchlist_root = _create_saved_cow_bookmark(tmp_path)
    entered = threading.Event()
    release = threading.Event()
    wrapper = _BlockingWatchlistService(service, entered, release)
    widget = DailyMarketTechnicalUniverseV4BookmarkControls(wrapper)  # type: ignore[arg-type]  # barrier 僅包裝真 reader 以控制完成時序。
    emitted: list[object] = []
    widget.stateReady.connect(emitted.append)
    widget.show()

    try:
        widget.refresh_bookmarks()
        _wait_for(app, lambda: widget._worker is None)
        assert wrapper.list_calls == 1
        _select_bookmark(widget, bookmark_id)
        widget.open_selected()
        assert entered.wait(timeout=10)

        widget.refresh_bookmarks()
        widget.refresh_bookmarks()
        assert widget._refresh_pending is True
        if action == "cancel":
            widget.cancel()
        else:
            widget.begin_shutdown()
            widget.close()
        assert widget._refresh_pending is False

        release.set()
        _wait_for(app, lambda: widget._worker is None)
        assert emitted == []
        assert wrapper.list_calls == 1
        if action == "cancel":
            assert _selected_bookmark_id(widget) == bookmark_id
        else:
            assert widget._closing is True
    finally:
        release.set()
        if not widget._closing:
            widget.close()
        _wait_for(app, lambda: widget._worker is None)
        app.processEvents()


@pytest.mark.parametrize("interrupt", ("selection_change", "cancel", "close"))
def test_stale_cancelled_or_closed_reopen_never_emits_old_state(
    app: QApplication,
    tmp_path: Path,
    interrupt: str,
) -> None:
    service, _bookmark_id, _store_root, _watchlist_root = _create_saved_cow_bookmark(tmp_path)
    entered = threading.Event()
    release = threading.Event()
    widget = DailyMarketTechnicalUniverseV4BookmarkControls(
        _BlockingWatchlistService(service, entered, release)  # type: ignore[arg-type]  # barrier 僅包裝真 reader 以控制完成時序。
    )
    emitted: list[object] = []
    widget.stateReady.connect(emitted.append)
    widget.show()

    try:
        widget.refresh_bookmarks()
        _wait_for(app, lambda: widget._worker is None)
        assert widget.bookmarks.count() == 2
        widget.bookmarks.setCurrentRow(0)
        widget.open_selected()
        assert entered.wait(timeout=10)

        if interrupt == "selection_change":
            widget.bookmarks.setCurrentRow(1)
        elif interrupt == "cancel":
            widget.cancel()
        else:
            widget.close()
            assert widget.begin_shutdown() is False
        release.set()
        _wait_for(app, lambda: widget._worker is None)

        assert emitted == []
        if interrupt == "selection_change":
            assert "選取的收藏已變更" in widget.status_label.text()
        elif interrupt == "cancel":
            assert "已取消讀取" in widget.status_label.text()
        else:
            assert widget._closing is True
    finally:
        release.set()
        if not widget._closing:
            widget.close()
        _wait_for(app, lambda: widget._worker is None)
        app.processEvents()
