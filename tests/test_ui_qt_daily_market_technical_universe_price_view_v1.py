"""F07 價格範圍視圖以真實合成保存來源完成瀏覽與重開。"""

from __future__ import annotations

import time
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from threading import Event
from typing import Any, cast

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QTabWidget, QTableView, QVBoxLayout, QWidget

from app_module.daily_market_technical_universe_price_bookmark_v1 import (
    DailyMarketTechnicalUniversePriceBookmarkStateV1,
    DailyMarketTechnicalUniversePriceBookmarkV1,
    create_daily_market_technical_universe_price_bookmark_v1,
    read_daily_market_technical_universe_price_bookmark_v1,
)
from app_module.daily_market_technical_universe_price_comparison_v1 import (
    DailyMarketTechnicalUniversePriceComparisonV1,
    DailyMarketTechnicalUniversePriceSelectionV1,
)
from app_module.daily_market_technical_universe_price_query_v1 import (
    DailyMarketTechnicalUniversePriceStockV1,
)
from tests.test_daily_market_technical_universe_price_query_v1 import _open_session, exact_price_store
from ui_qt.views.daily_market_technical_universe_price_view_v1 import (
    DailyMarketTechnicalUniversePriceV1View,
    _parse_stock_filter,
)
from ui_qt.views.recommendation_view import _CurrentPageSizeTabWidget
from ui_qt.widgets.layout_helpers import create_scroll_area
import ui_qt.views.daily_market_technical_universe_price_view_v1 as price_view_module


@pytest.fixture(scope="module")
def app() -> QApplication:
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication([])
    return cast(QApplication, instance)


def _wait(app: QApplication, predicate: Any, *, timeout_seconds: float = 90.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while not predicate():
        app.processEvents()
        if time.monotonic() >= deadline:
            raise AssertionError("F07 價格視圖背景工作逾時")
        time.sleep(0.01)
    app.processEvents()


def _scroll_bookmark_state(
    store: dict[str, Any], *, stock_code: str, scroll_position: int
) -> tuple[
    DailyMarketTechnicalUniversePriceBookmarkV1,
    DailyMarketTechnicalUniversePriceBookmarkStateV1,
]:
    session = _open_session(store)
    query = session.create_query(unknown_price_policy="include")
    result = session.execute(query)
    page = result.read_page(result.create_page_request(0, page_size=4))
    bookmark = create_daily_market_technical_universe_price_bookmark_v1(
        query,
        page,
        stock_code,
        scroll_position=scroll_position,
    )
    return bookmark, read_daily_market_technical_universe_price_bookmark_v1(bookmark)


def _scroll_metrics(view: DailyMarketTechnicalUniversePriceV1View) -> dict[str, object]:
    bar = view.table.verticalScrollBar()
    viewport = view.table.viewport()
    model = view.table.model()
    page = view.current_page
    return {
        "value": int(bar.value()),
        "minimum": int(bar.minimum()),
        "maximum": int(bar.maximum()),
        "viewport_width": int(viewport.width()),
        "viewport_height": int(viewport.height()),
        "table_width": int(view.table.width()),
        "table_height": int(view.table.height()),
        "table_visible": bool(view.table.isVisible()),
        "view_visible": bool(view.isVisible()),
        "row_count": int(model.rowCount()) if model is not None else 0,
        "page_row_count": len(page.rows) if page is not None else 0,
        "page_index": page.request.page_index if page is not None else None,
    }


def _entry_index(view: DailyMarketTechnicalUniversePriceV1View, status: str) -> int:
    for index in range(view.sources.count()):
        entry = view.sources.itemData(index)
        if getattr(entry, "source_status", None) == status:
            return index
    return -1


@pytest.mark.parametrize("width", (520, 760))
def test_narrow_result_area_keeps_price_apply_reachable_and_inputs_on_resize(
    app: QApplication, exact_price_store: dict[str, Any], width: int,
) -> None:
    """小結果區不得靠不可見的水平捲動才能套用，重排也不可重設原查詢。"""
    view = DailyMarketTechnicalUniversePriceV1View(exact_price_store["store_root"])
    tabs = _CurrentPageSizeTabWidget()
    tabs.addTab(view, "價格研究")
    host = create_scroll_area(tabs)
    host.resize(width, 650)
    host.show()
    try:
        app.processEvents()
        view.refresh_sources()
        _wait(app, lambda: not view.busy, timeout_seconds=15)
        view.sources.setCurrentIndex(_entry_index(view, "complete"))
        view.load_selected_source()
        _wait(app, lambda: not view.busy, timeout_seconds=15)
        assert view.current_query is not None
        original_source = view.current_query.source
        view.minimum.setText("101")
        view.combine_mode.setCurrentIndex(view.combine_mode.findData("OR"))
        for target_width in (1100, width):
            host.resize(target_width, 650)
            app.processEvents()
            assert view.minimum.text() == "101" and view.combine_mode.currentData() == "OR"
        viewport = host.viewport()
        button = view.apply_query_button
        def reachable() -> bool:
            host.ensureWidgetVisible(button, 0, 12)
            app.processEvents()
            return (
                viewport.rect().contains(button.mapTo(viewport, button.rect().topLeft()))
                and viewport.rect().contains(button.mapTo(viewport, button.rect().bottomRight()))
            )
        _wait(app, reachable, timeout_seconds=15)
        assert viewport.rect().contains(button.mapTo(viewport, button.rect().topLeft()))
        assert viewport.rect().contains(button.mapTo(viewport, button.rect().bottomRight()))
        assert host.horizontalScrollBar().value() == 0
        assert button.isEnabled()
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        _wait(app, lambda: not view.busy, timeout_seconds=15)
        assert view.current_query is not None and view.current_query.min_close_price == Decimal("101")
        assert view.current_query.combine_mode == "OR"
        assert view.current_query.source == original_source
    finally:
        view.begin_shutdown()
        _wait(app, lambda: view.workers_remaining == 0, timeout_seconds=15)
        host.close()
        app.processEvents()


def test_price_table_remains_selectable_beside_a_wide_sibling(
    app: QApplication, exact_price_store: dict[str, Any],
) -> None:
    """同頁其他研究有大最小寬度，不能使價格股票列躲在隱藏水平捲軸外。"""
    page = QWidget()
    layout = QVBoxLayout(page)
    sibling = QWidget()
    sibling.setMinimumSize(1200, 20)
    layout.addWidget(sibling)
    view = DailyMarketTechnicalUniversePriceV1View(exact_price_store["store_root"])
    layout.addWidget(view)
    tabs = _CurrentPageSizeTabWidget()
    tabs.addTab(page, "每日研究")
    host = create_scroll_area(tabs)
    host.resize(760, 650)
    host.show()
    try:
        app.processEvents()
        view.refresh_sources()
        _wait(app, lambda: not view.busy, timeout_seconds=15)
        view.sources.setCurrentIndex(_entry_index(view, "complete"))
        view.load_selected_source()
        _wait(app, lambda: not view.busy, timeout_seconds=15)
        index = view.results_model.index_for_stock("S0001")
        assert index.isValid()
        def reachable() -> bool:
            view.table.scrollTo(index)
            host.ensureWidgetVisible(view.table)
            app.processEvents()
            rect = view.table.visualRect(index)
            return rect.isValid() and host.viewport().rect().contains(
                view.table.viewport().mapTo(host.viewport(), rect.center())
            )
        _wait(app, reachable, timeout_seconds=15)
        assert host.horizontalScrollBar().value() == 0
        rect = view.table.visualRect(index)
        QTest.mouseClick(view.table.viewport(), Qt.MouseButton.LeftButton, pos=rect.center())
        selected = view._selected_row()
        assert selected is not None and selected.technical_row.stock_code == "S0001"
    finally:
        view.begin_shutdown()
        _wait(app, lambda: view.workers_remaining == 0, timeout_seconds=15)
        host.close()
        app.processEvents()


def test_true_saved_source_catalog_query_comparison_bookmark_and_stock_signal(
    app: QApplication,
    exact_price_store: dict[str, Any],
) -> None:
    view = DailyMarketTechnicalUniversePriceV1View(exact_price_store["store_root"])
    view.resize(900, 720)
    view.show()
    app.processEvents()
    stock_events: list[tuple[object, object]] = []
    comparison_events: list[object] = []
    bookmark_events: list[object] = []
    view.stockSelected.connect(lambda stock, selection: stock_events.append((stock, selection)))
    view.comparisonReady.connect(comparison_events.append)
    view.bookmarkPrepared.connect(bookmark_events.append)

    view.refresh_sources()
    _wait(app, lambda: not view.busy)
    catalog_index = _entry_index(view, "complete")
    assert catalog_index >= 0, view.status.text()
    view.sources.setCurrentIndex(catalog_index)
    entry = view.selected_source
    assert entry is not None and entry.is_selectable
    assert "尚未 strict 核驗" in view.source_pins.text()

    view.load_selected_source()
    _wait(app, lambda: not view.busy)
    assert view.current_page is not None, view.status.text()
    assert isinstance(view.table, QTableView)
    assert view.table.isSortingEnabled() is False
    assert view.results_model.rowCount() == len(view.current_page.rows)
    assert view.current_page.full_population_complete is True
    assert view.current_page.source_counts.declared_count == 5
    assert view.current_page.source_counts.included_count == 4
    assert view.current_page.source_counts.excluded_count == 1
    assert view.current_page.price_counts.unknown_count == 1
    assert "可得時間未知" in view.summary.text()

    original_query = view.current_query
    assert original_query is not None
    view.minimum.setText("201")
    view.maximum.setText("100")
    view.apply_query()
    assert view.current_query == original_query
    assert "下限不可高於上限" in view.status.text()
    view._restore_controls_from_state()

    assert view.select_stock_code("S0001")
    row_index = view.results_model.index_for_stock("S0001")
    rect = view.table.visualRect(row_index)
    assert rect.isValid() and view.table.viewport().rect().intersects(rect)
    table_double_clicks: list[object] = []
    view.table.doubleClicked.connect(table_double_clicks.append)
    QTest.mouseClick(view.table.viewport(), Qt.MouseButton.LeftButton, pos=rect.center())
    QTest.mouseDClick(view.table.viewport(), Qt.MouseButton.LeftButton, pos=rect.center())
    app.processEvents()
    assert len(table_double_clicks) == 1
    _wait(app, lambda: not view.busy)
    assert len(stock_events) == 1
    assert isinstance(stock_events[0][0], DailyMarketTechnicalUniversePriceStockV1)
    assert isinstance(stock_events[0][1], DailyMarketTechnicalUniversePriceSelectionV1)
    assert stock_events[0][0].stock_code == "S0001"
    assert stock_events[0][1].stock_code == "S0001"
    assert view.current_page is not None
    assert stock_events[0][1].page_identity_sha256 == view.current_page.page_identity_sha256

    assert view.select_stock_code("S0002")
    QTest.mouseClick(view.add_comparison_button, Qt.MouseButton.LeftButton)
    assert not view.run_comparison_button.isEnabled()
    assert view.clear_comparison_button.isEnabled()
    assert not view.bookmark_button.isEnabled()
    assert view.select_stock_code("S0003")
    QTest.mouseClick(view.add_comparison_button, Qt.MouseButton.LeftButton)
    assert view.run_comparison_button.isEnabled()
    assert view.bookmark_button.isEnabled()
    QTest.mouseClick(view.run_comparison_button, Qt.MouseButton.LeftButton)
    _wait(app, lambda: not view.busy)
    assert len(comparison_events) == 1
    comparison = comparison_events[0]
    assert isinstance(comparison, DailyMarketTechnicalUniversePriceComparisonV1)
    assert tuple(column.selection.stock_code for column in comparison.columns) == ("S0002", "S0003")
    assert comparison.columns[-1].row.price_state == "unknown"

    assert view.select_stock_code("S0001")
    view.table.verticalScrollBar().setValue(7)
    view.prepare_bookmark()
    _wait(app, lambda: not view.busy)
    assert len(bookmark_events) == 1
    bookmark = bookmark_events[0]
    assert isinstance(bookmark, DailyMarketTechnicalUniversePriceBookmarkV1)
    assert bookmark.stock_code == "S0001"
    assert len(bookmark.comparison_selections) == 2

    assert view.restore_bookmark(bookmark) is True
    _wait(app, lambda: not view.busy)
    assert view.current_query is not None
    assert view.current_page is not None
    assert view.select_stock_code("S0001")
    assert tuple(item.stock_code for item in view._basket) == ("S0002", "S0003")
    QTest.mouseClick(view.clear_comparison_button, Qt.MouseButton.LeftButton)
    assert view._basket == []
    assert not view.run_comparison_button.isEnabled()
    assert not view.clear_comparison_button.isEnabled()
    assert view.bookmark_button.isEnabled()

    selection = DailyMarketTechnicalUniversePriceSelectionV1.from_page(
        view.current_query,
        view.current_page,
        "S0001",
    )
    assert view.restore_origin(selection) is True
    _wait(app, lambda: not view.busy)
    assert view.current_page is not None
    assert view.select_stock_code("S0001")
    assert view.begin_shutdown() is True
    view.close()


def test_parent_save_status_is_not_overwritten_after_bookmark_prepared_signal(
    app: QApplication,
    exact_price_store: dict[str, Any],
) -> None:
    session = _open_session(exact_price_store)
    query = session.create_query(unknown_price_policy="include")
    result = session.execute(query)
    page = result.read_page(result.create_page_request(0, page_size=4))
    bookmark = create_daily_market_technical_universe_price_bookmark_v1(
        query,
        page,
        "S0001",
        scroll_position=0,
    )
    view = DailyMarketTechnicalUniversePriceV1View(exact_price_store["store_root"])

    saved: list[DailyMarketTechnicalUniversePriceBookmarkV1] = []

    def successful_writer(value: object) -> None:
        assert isinstance(value, DailyMarketTechnicalUniversePriceBookmarkV1)
        saved.append(value)
        view.status.setText("原價格條件收藏已保存。")

    view.bookmarkPrepared.connect(successful_writer)
    view._apply_bookmark(bookmark)

    assert saved == [bookmark]
    assert view.status.text() == "原價格條件收藏已保存。"
    view.close()


def test_stock_code_filter_accepts_full_limit_and_rejects_overflow_atomically(
    app: QApplication,
    tmp_path: Path,
) -> None:
    codes = tuple(f"S{index:05d}" for index in range(100_000))
    raw = ",".join(codes)
    assert _parse_stock_filter(raw) == codes
    view = DailyMarketTechnicalUniversePriceV1View(tmp_path / "unused-stock-filter-store")
    view.stock_filter.setText(raw)
    assert view.stock_filter.text() == raw
    assert view._query_inputs().stock_filter == codes

    overflow = ",".join((*codes, "S100000"))
    with pytest.raises(ValueError, match="100,000"):
        _parse_stock_filter(overflow)
    view.stock_filter.setText(overflow)
    with pytest.raises(ValueError, match="100,000"):
        view._query_inputs()
    for malformed in ("S00001,,S00002", "S00001,S00001", "S00001,"):
        with pytest.raises(ValueError):
            _parse_stock_filter(malformed)
    view.begin_shutdown()


def test_eligible_stock_filter_preserves_none_empty_and_explicit_subset(
    app: QApplication,
    tmp_path: Path,
) -> None:
    view = DailyMarketTechnicalUniversePriceV1View(tmp_path / "unused-store")
    view.eligible_stock_filter.setText("S00001, S00002")
    view.eligible_stock_filter_enabled.setChecked(False)
    assert view._query_inputs().eligible_stock_codes is None

    view.eligible_stock_filter_enabled.setChecked(True)
    assert view._query_inputs().eligible_stock_codes == ("S00001", "S00002")

    view.eligible_stock_filter.clear()
    assert view._query_inputs().eligible_stock_codes == ()
    view.begin_shutdown()


def test_shutdown_waits_for_native_worker_and_discards_late_result(app: QApplication, tmp_path: Path) -> None:
    view = DailyMarketTechnicalUniversePriceV1View(tmp_path / "not-created-price-store")
    started = Event()
    release = Event()
    applied: list[object] = []

    def delayed_operation(cancel_callback: Any = None) -> str:
        started.set()
        release.wait(10.0)
        return "late" if cancel_callback is None or not cancel_callback() else "cancelled-late"

    assert view._start("合成延遲工作", delayed_operation, applied.append, kind="synthetic")
    assert started.wait(5.0)
    assert view.begin_shutdown() is False
    release.set()
    _wait(app, lambda: view.workers_remaining == 0)
    _wait(app, lambda: view._worker is None)
    assert applied == []
    assert view.begin_shutdown() is True


def test_restore_fresh_bookmark_state_reuses_issued_page_and_rejects_wrong_source(
    app: QApplication,
    exact_price_store: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _open_session(exact_price_store)
    query = session.create_query(unknown_price_policy="include")
    result = session.execute(query)
    request = result.create_page_request(0, page_size=4)
    page = result.read_page(request)
    bookmark = create_daily_market_technical_universe_price_bookmark_v1(
        query, page, "S0001", scroll_position=1,
    )
    bookmark_state = read_daily_market_technical_universe_price_bookmark_v1(bookmark)

    alternate_query = session.create_query(
        min_close_price=Decimal("150"),
        unknown_price_policy="include",
    )
    alternate_result = session.execute(alternate_query)
    alternate_page = alternate_result.read_page(
        alternate_result.create_page_request(0, page_size=4)
    )
    alternate_bookmark = create_daily_market_technical_universe_price_bookmark_v1(
        alternate_query, alternate_page, "S0002", scroll_position=0,
    )
    calls = 0

    def forbidden_reopen(*_args: object, **_kwargs: object) -> object:
        nonlocal calls
        calls += 1
        raise AssertionError("同次 fresh state 不應再次開啟來源")

    monkeypatch.setattr(
        price_view_module,
        "read_daily_market_technical_universe_price_bookmark_v1",
        forbidden_reopen,
    )
    view = DailyMarketTechnicalUniversePriceV1View(exact_price_store["store_root"])
    view.resize(520, 170)
    view.show()
    app.processEvents()

    assert view.restore_bookmark_state(bookmark_state)
    _wait(
        app,
        lambda: (
            view._pending_bookmark_scroll_restore is None
            and view.table.isVisible()
            and view.table.viewport().width() > 0
            and view.table.viewport().height() > 0
            and view.table.verticalScrollBar().maximum() >= bookmark.scroll_position
            and view.table.verticalScrollBar().value() == bookmark.scroll_position
        ),
        timeout_seconds=3.0,
    )
    assert calls == 0
    assert view.current_query == query
    assert view.current_page is bookmark_state.selected.page
    current_row = view._selected_row()
    assert current_row is not None and current_row.technical_row.stock_code == "S0001"
    assert bookmark.scroll_position > 0
    assert view.table.verticalScrollBar().maximum() >= bookmark.scroll_position
    assert view.table.verticalScrollBar().value() == bookmark.scroll_position
    assert view._basket == list(bookmark.comparison_selections)

    with pytest.raises(ValueError):
        replace(bookmark_state, bookmark=alternate_bookmark)

    forged_state = object.__new__(type(bookmark_state))
    object.__setattr__(forged_state, "bookmark", alternate_bookmark)
    object.__setattr__(forged_state, "selected", bookmark_state.selected)
    object.__setattr__(forged_state, "comparison", bookmark_state.comparison)
    preserved_page = view.current_page
    preserved_query = view.current_query
    assert not view.restore_bookmark_state(forged_state)
    assert view.current_page is preserved_page
    assert view.current_query == preserved_query
    assert "anchors 無效" in view.status.text()
    assert calls == 0
    assert view.begin_shutdown() is True
    view.close()


def test_async_bookmark_restore_keeps_scroll_until_native_worker_release(
    app: QApplication,
    exact_price_store: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bookmark, bookmark_state = _scroll_bookmark_state(
        exact_price_store,
        stock_code="S0001",
        scroll_position=2,
    )
    host = QTabWidget()
    view = DailyMarketTechnicalUniversePriceV1View(
        exact_price_store["store_root"], parent=host
    )
    view.table.setFixedHeight(110)
    host.addTab(QWidget(), "Watchlist")
    host.addTab(view, "Price")
    host.resize(800, 600)
    host.show()
    app.processEvents()
    assert not view.table.isVisible()

    held_releases: list[object] = []
    native_release = view._release

    def delay_ui_release(worker: object) -> None:
        held_releases.append(worker)

    monkeypatch.setattr(view, "_release", delay_ui_release)
    assert view._start(
        "測試非同步重開收藏",
        lambda cancel_callback=None: bookmark_state,
        view._apply_bookmark_state,
        kind="bookmark_restore",
    )

    _wait(
        app,
        lambda: (
            len(held_releases) == 1
            and view.current_page is bookmark_state.selected.page
            and view._pending_bookmark_scroll_restore is not None
        ),
        timeout_seconds=3.0,
    )
    assert view.busy
    assert view.table.verticalScrollBar().value() == 0

    # 先讓隱藏頁完成顯示與版面事件；worker release callback 仍被測試攔住。
    host.setCurrentWidget(view)
    _wait(
        app,
        lambda: (
            view.table.isVisible()
            and view.table.viewport().height() > 0
            and view.table.verticalScrollBar().maximum() >= bookmark.scroll_position
        ),
        timeout_seconds=3.0,
    )
    QTest.qWait(30)
    assert view.busy
    assert view._pending_bookmark_scroll_restore is not None
    assert view.table.verticalScrollBar().value() != bookmark.scroll_position

    native_release(cast(Any, held_releases[0]))
    _wait(
        app,
        lambda: (
            not view.busy
            and view._pending_bookmark_scroll_restore is None
            and view.table.verticalScrollBar().value() == bookmark.scroll_position
        ),
        timeout_seconds=3.0,
    )
    assert view.table.verticalScrollBar().maximum() >= bookmark.scroll_position
    assert view.table.verticalScrollBar().value() == bookmark.scroll_position
    assert view.begin_shutdown() is True
    host.close()


def test_hidden_bookmark_restore_applies_scroll_after_tab_layout(
    app: QApplication,
    exact_price_store: dict[str, Any],
) -> None:
    bookmark, bookmark_state = _scroll_bookmark_state(
        exact_price_store,
        stock_code="S0001",
        scroll_position=2,
    )
    host = QTabWidget()
    view = DailyMarketTechnicalUniversePriceV1View(
        exact_price_store["store_root"], parent=host
    )
    view.table.setFixedHeight(110)
    placeholder = QWidget()
    host.addTab(placeholder, "Watchlist")
    host.addTab(view, "Price")
    host.resize(800, 600)
    host.show()
    app.processEvents()
    assert not view.table.isVisible()

    assert view.restore_bookmark_state(bookmark_state)
    hidden_bar = view.table.verticalScrollBar()
    assert hidden_bar.maximum() == 0
    assert hidden_bar.value() == 0
    assert view._pending_bookmark_scroll_restore is not None

    scroll_events: list[int] = []
    hidden_bar.valueChanged.connect(scroll_events.append)
    host.setCurrentWidget(view)
    try:
        _wait(
            app,
            lambda: (
                view.table.isVisible()
                and view._pending_bookmark_scroll_restore is None
                and hidden_bar.value() == bookmark.scroll_position
            ),
            timeout_seconds=3.0,
        )
    except AssertionError as exc:
        raise AssertionError(
            "隱藏頁收藏捲動未在顯示後還原："
            f"metrics={_scroll_metrics(view)}; "
            f"pending={view._pending_bookmark_scroll_restore!r}; "
            f"busy={view.busy}; generation={view._generation}; "
            f"scroll_events={scroll_events}"
        ) from exc
    assert view.results_model.rowCount() == 4
    assert hidden_bar.maximum() >= bookmark.scroll_position
    assert hidden_bar.value() == bookmark.scroll_position
    assert bookmark.scroll_position in scroll_events
    assert view.table.viewport().width() > 0
    assert view.table.viewport().height() > 0
    assert view.begin_shutdown() is True
    host.close()


def test_zero_size_bookmark_restore_waits_for_resize_without_repeating(
    app: QApplication,
    exact_price_store: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bookmark, bookmark_state = _scroll_bookmark_state(
        exact_price_store,
        stock_code="S0001",
        scroll_position=2,
    )
    host = QTabWidget()
    view = DailyMarketTechnicalUniversePriceV1View(
        exact_price_store["store_root"], parent=host
    )
    scheduled_runs = 0
    original_scheduled_run = view._run_scheduled_bookmark_scroll_restore

    def count_scheduled_run(expected: object) -> None:
        nonlocal scheduled_runs
        scheduled_runs += 1
        original_scheduled_run(cast(Any, expected))

    monkeypatch.setattr(
        view,
        "_run_scheduled_bookmark_scroll_restore",
        count_scheduled_run,
    )
    placeholder = QWidget()
    host.addTab(placeholder, "Watchlist")
    host.addTab(view, "Price")
    host.resize(520, 170)
    host.show()
    app.processEvents()

    assert view.restore_bookmark_state(bookmark_state)
    host.setCurrentWidget(view)
    app.processEvents()
    first_metrics = _scroll_metrics(view)
    assert view.table.isVisible()
    assert cast(int, first_metrics["viewport_height"]) <= 0
    assert view._pending_bookmark_scroll_restore is not None

    # 零尺寸狀態只等待下一個實際版面事件，不建立無限的零毫秒重試。
    QTest.qWait(50)
    assert view._pending_bookmark_scroll_restore is not None
    assert scheduled_runs <= 16
    assert int(view.table.verticalScrollBar().value()) != bookmark.scroll_position

    view.table.setFixedHeight(110)
    host.resize(800, 600)
    _wait(
        app,
        lambda: (
            view._pending_bookmark_scroll_restore is None
            and view.table.viewport().height() > 0
            and view.table.verticalScrollBar().value() == bookmark.scroll_position
        ),
        timeout_seconds=3.0,
    )
    metrics = _scroll_metrics(view)
    assert cast(int, metrics["maximum"]) >= bookmark.scroll_position
    assert cast(int, metrics["viewport_width"]) > 0
    assert cast(int, metrics["viewport_height"]) > 0
    assert view.begin_shutdown() is True
    host.close()


def test_pending_bookmark_scroll_is_cleared_by_selection_and_shutdown(
    app: QApplication,
    exact_price_store: dict[str, Any],
) -> None:
    bookmark, bookmark_state = _scroll_bookmark_state(
        exact_price_store,
        stock_code="S0001",
        scroll_position=2,
    )
    host = QTabWidget()
    view = DailyMarketTechnicalUniversePriceV1View(
        exact_price_store["store_root"], parent=host
    )
    view.table.setFixedHeight(110)
    placeholder = QWidget()
    host.addTab(placeholder, "Watchlist")
    host.addTab(view, "Price")
    host.resize(800, 600)
    host.show()
    app.processEvents()

    assert not view.table.isVisible()
    assert view.restore_bookmark_state(bookmark_state)
    assert view._pending_bookmark_scroll_restore is not None
    assert view.select_stock_code("S0002")
    assert view._pending_bookmark_scroll_restore is None
    host.setCurrentWidget(view)
    _wait(app, lambda: view.table.viewport().height() > 0, timeout_seconds=3.0)
    selected = view._selected_row()
    assert selected is not None and selected.technical_row.stock_code == "S0002"
    assert view._pending_bookmark_scroll_restore is None
    app.processEvents()
    selected_scroll_after_layout = view.table.verticalScrollBar().value()
    app.processEvents()
    assert view.table.verticalScrollBar().value() == selected_scroll_after_layout

    host.setCurrentWidget(placeholder)
    app.processEvents()
    assert view.restore_bookmark_state(bookmark_state)
    assert view._pending_bookmark_scroll_restore is not None
    assert view.begin_shutdown() is True
    assert view._pending_bookmark_scroll_restore is None
    host.setCurrentWidget(view)
    _wait(app, lambda: view.table.viewport().height() > 0, timeout_seconds=3.0)
    shutdown_scroll_after_layout = view.table.verticalScrollBar().value()
    app.processEvents()
    assert view.table.verticalScrollBar().value() == shutdown_scroll_after_layout
    assert view._pending_bookmark_scroll_restore is None
    host.close()
