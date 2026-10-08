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
from PySide6.QtWidgets import QApplication, QTableView

from app_module.daily_market_technical_universe_price_bookmark_v1 import (
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


def _entry_index(view: DailyMarketTechnicalUniversePriceV1View, status: str) -> int:
    for index in range(view.sources.count()):
        entry = view.sources.itemData(index)
        if getattr(entry, "source_status", None) == status:
            return index
    return -1


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
    view.add_selected_to_comparison()
    assert view.select_stock_code("S0003")
    view.add_selected_to_comparison()
    view.run_comparison()
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
    assert calls == 0
    assert view.current_query == query
    assert view.current_page is bookmark_state.selected.page
    current_row = view._selected_row()
    assert current_row is not None and current_row.technical_row.stock_code == "S0001"
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
