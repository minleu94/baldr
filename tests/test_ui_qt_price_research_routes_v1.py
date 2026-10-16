"""F07 價格研究在每日研究與觀察清單間保留原來源路由。"""

from __future__ import annotations

import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, cast

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QMainWindow, QTabWidget, QWidget

pytest_plugins = ("tests.test_daily_market_technical_universe_price_query_v1",)

from app_module.daily_market_technical_universe_price_bookmark_v1 import (
    DailyMarketTechnicalUniversePriceBookmarkStateV1,
    DailyMarketTechnicalUniversePriceBookmarkV1,
)
from app_module.daily_market_technical_universe_price_comparison_v1 import (
    DailyMarketTechnicalUniversePriceComparisonV1,
    DailyMarketTechnicalUniversePriceSelectionV1,
)
from app_module.daily_market_technical_universe_price_query_v1 import (
    DailyMarketTechnicalUniversePriceQueryV1,
    DailyMarketTechnicalUniversePriceReadSessionV1,
    DailyMarketTechnicalUniversePriceStockV1,
)
from app_module.watchlist_service import (
    TECHNICAL_UNIVERSE_PRICE_BOOKMARK_SOURCE,
    WatchlistService,
)
from ui_qt.main import MainWindow
from ui_qt.views.daily_market_research_view import DailyMarketResearchView
from ui_qt.views.daily_market_technical_price_comparison_v1_view import (
    DailyMarketTechnicalPriceComparisonV1View,
)
from ui_qt.views.daily_market_technical_price_stock_v1_view import (
    DailyMarketTechnicalPriceStockV1View,
)
from ui_qt.views.daily_market_technical_universe_price_view_v1 import (
    DailyMarketTechnicalUniversePriceV1View,
)
from ui_qt.views.watchlist_view import WatchlistView
import app_module.daily_market_technical_universe_price_comparison_v1 as comparison_module
import ui_qt.views.daily_market_technical_universe_price_view_v1 as price_view_module


@pytest.fixture(scope="module")
def app() -> QApplication:
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication([])
    return cast(QApplication, instance)


class _PriceBookmarkRouteHost(QMainWindow):
    """只提供 MainWindow route 使用的真 Qt 導航容器。"""

    def __init__(self, daily: DailyMarketResearchView) -> None:
        super().__init__()
        self._shutdown_close_requested = False
        self.workspace_selections: list[str] = []
        tabs = QTabWidget(self)
        tabs.addTab(QLabel("其他研究工作區", tabs), "其他")
        tabs.addTab(daily, "每日研究")
        tabs.setCurrentIndex(0)
        self.setCentralWidget(tabs)
        self.recommendation_view = SimpleNamespace(
            daily_market_research_view=daily,
            result_source_tabs=tabs,
        )

    def _select_main_workspace(self, workspace: str) -> None:
        self.workspace_selections.append(workspace)


def _wait(app: QApplication, predicate: Callable[[], bool], *, timeout_seconds: float = 120.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while not predicate():
        app.processEvents()
        if time.monotonic() >= deadline:
            raise AssertionError("F07 正常 UI 路由背景工作逾時")
        time.sleep(0.01)
    app.processEvents()


def _complete_source_index(view: DailyMarketTechnicalUniversePriceV1View) -> int:
    for index in range(view.sources.count()):
        entry = view.sources.itemData(index)
        if getattr(entry, "source_status", None) == "complete":
            return index
    return -1


def _selected_price_code(view: DailyMarketTechnicalUniversePriceV1View) -> str | None:
    index = view.table.currentIndex()
    if not index.isValid():
        return None
    row = view.results_model.row_at(index.row())
    code = getattr(getattr(row, "technical_row", None), "stock_code", None)
    return code if isinstance(code, str) else None


def _activate_price_stock(
    app: QApplication,
    view: DailyMarketTechnicalUniversePriceV1View,
    stock_code: str,
) -> None:
    assert view.select_stock_code(stock_code)
    index = view.results_model.index_for_stock(stock_code)
    view.table.scrollTo(index)
    app.processEvents()
    rect = view.table.visualRect(index)
    assert rect.isValid() and view.table.viewport().rect().intersects(rect)
    QTest.mouseClick(view.table.viewport(), Qt.MouseButton.LeftButton, pos=rect.center())
    QTest.mouseDClick(view.table.viewport(), Qt.MouseButton.LeftButton, pos=rect.center())
    app.processEvents()


def _private_watchlist_service(tmp_path: Path) -> tuple[WatchlistService, SimpleNamespace]:
    output_root = tmp_path / "private-output"
    output_root.mkdir(parents=True)
    config = SimpleNamespace(
        output_root=output_root,
        resolve_output_path=lambda name: output_root / name,
    )
    return WatchlistService(config), config


def test_daily_research_parent_opens_returns_compares_and_guards_bookmark_confirmation(
    app: QApplication,
    exact_price_store: dict[str, Any],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
) -> None:
    assert not Path(exact_price_store["database"]).exists()
    service, watchlist_config = _private_watchlist_service(tmp_path)
    watchlist = WatchlistView(service, config=None)
    watchlist.resize(1500, 1100)
    watchlist.show()
    app.processEvents()
    _wait(app, lambda: not watchlist.price_bookmark_controls.busy)

    config = SimpleNamespace(
        output_root=watchlist_config.output_root,
        resolve_output_path=watchlist_config.resolve_output_path,
        technical_universe_read_root=exact_price_store["store_root"],
    )
    confirmation_values: list[object] = []
    mode = {"change_query": False}
    price_views: list[DailyMarketTechnicalUniversePriceV1View] = []

    def confirm_bookmark(value: object) -> bool:
        confirmation_values.append(value)
        if mode["change_query"]:
            assert price_views
            price = price_views[0]
            previous_query = price.current_query
            previous_page = price.current_page
            assert previous_query is not None and previous_page is not None
            price.minimum.setText("150")
            price.apply_query()
            _wait(app, lambda: not price.busy)
            assert price.current_query is not None
            assert price.current_page is not None
            assert price.current_query.to_json() != previous_query.to_json()
            assert price.current_page.page_identity_sha256 != previous_page.page_identity_sha256
        return True

    daily = DailyMarketResearchView(
        service=SimpleNamespace(config=config),
        watchlist_service=service,
        bookmark_confirmation_callback=confirm_bookmark,
    )
    daily.resize(1800, 1800)
    daily.show()
    app.processEvents()
    price = daily.technical_price_view
    assert price is not None
    price_views.append(price)
    assert daily.isVisible() and price.isVisible()
    assert daily.research_sections.currentWidget() is price
    assert daily.research_sections.tabText(0).startswith("價格選股")
    daily.research_sections.setCurrentWidget(daily.snapshot_page)
    app.processEvents()
    assert daily.source_selector is not None and daily.source_selector.isVisible()
    daily.research_sections.setCurrentWidget(price)
    app.processEvents()
    assert price.isVisible()

    hosts: list[_PriceBookmarkRouteHost] = []

    def cleanup() -> None:
        daily.begin_shutdown()
        watchlist.begin_shutdown()
        deadline = time.monotonic() + 30.0
        while not (daily.begin_shutdown() and watchlist.begin_shutdown()):
            app.processEvents()
            if time.monotonic() >= deadline:
                raise AssertionError("F07 測試視窗的背景工作未在關閉期限內停止")
            time.sleep(0.01)
        if hosts:
            hosts[0].close()
        watchlist.close()
        daily.close()
        app.processEvents()

    request.addfinalizer(cleanup)

    stock_events: list[tuple[object, object]] = []
    comparison_events: list[object] = []
    saved_events: list[object] = []
    generic_stock_events: list[str] = []

    price.stockSelected.connect(lambda stock, origin: stock_events.append((stock, origin)))
    price.comparisonReady.connect(comparison_events.append)
    watchlist.stockAnalysisRequested.connect(generic_stock_events.append)

    def refresh_watchlist(_value: object) -> None:
        saved_events.append(_value)
        watchlist._load_watchlist()

    daily.bookmarkSaved.connect(refresh_watchlist)

    price.refresh_sources()
    _wait(app, lambda: not price.busy)
    catalog_index = _complete_source_index(price)
    assert catalog_index >= 0, price.status.text()
    price.sources.setCurrentIndex(catalog_index)
    source_entry = price.selected_source
    assert source_entry is not None and source_entry.is_selectable
    price.load_selected_source()
    _wait(app, lambda: not price.busy)
    assert price.current_query is not None and price.current_page is not None
    original_query = price.current_query
    assert price.current_page.source_counts.declared_count == 5
    assert price.current_page.source_counts.included_count == 4
    assert price.current_page.source_counts.excluded_count == 1
    assert price.current_page.price_counts.unknown_count == 1
    original_page = price.current_page

    opened_queries: list[str] = []
    original_restore_open = price_view_module.open_daily_market_technical_universe_price_session_for_query_v1

    def tracked_restore_open(
        query: DailyMarketTechnicalUniversePriceQueryV1,
        *,
        cancel_callback: Callable[[], object] | None = None,
    ) -> tuple[object, DailyMarketTechnicalUniversePriceQueryV1]:
        opened_queries.append(query.to_json())
        return original_restore_open(query, cancel_callback=cancel_callback)

    monkeypatch.setattr(
        price_view_module,
        "open_daily_market_technical_universe_price_session_for_query_v1",
        tracked_restore_open,
    )
    restored_origins: list[DailyMarketTechnicalUniversePriceSelectionV1] = []
    original_restore_origin = price.restore_origin

    def tracked_restore_origin(selection: DailyMarketTechnicalUniversePriceSelectionV1) -> bool:
        restored_origins.append(selection)
        return original_restore_origin(selection)

    monkeypatch.setattr(price, "restore_origin", tracked_restore_origin)

    _activate_price_stock(app, price, "S0001")
    _wait(app, lambda: not price.busy and daily._price_stock_dialog is not None)
    assert len(stock_events) == 1
    stock, origin = stock_events[0]
    assert isinstance(stock, DailyMarketTechnicalUniversePriceStockV1)
    assert isinstance(origin, DailyMarketTechnicalUniversePriceSelectionV1)
    assert stock.stock_code == origin.stock_code == "S0001"
    assert origin.query.to_json() == original_query.to_json()
    assert origin.page_identity_sha256 == original_page.page_identity_sha256
    assert daily._price_stock_dialog is not None and daily._price_stock_dialog.isVisible()
    details = daily._price_stock_dialog.findChild(DailyMarketTechnicalPriceStockV1View)
    assert details is not None and details.isVisible()
    assert "S0001" in details.summary.text()
    assert origin.selection_identity_sha256 in details.audit.toPlainText()
    assert details.return_button.isEnabled()
    QTest.mouseClick(details.return_button, Qt.MouseButton.LeftButton)
    _wait(app, lambda: not price.busy)
    assert restored_origins[-1].to_dict() == origin.to_dict()
    assert opened_queries[-1] == origin.query_json
    assert price.current_query is not None and price.current_page is not None
    assert price.current_query.to_json() == origin.query_json
    assert price.current_page.page_identity_sha256 == origin.page_identity_sha256
    assert _selected_price_code(price) == origin.stock_code

    assert price.select_stock_code("S0002")
    price.add_selected_to_comparison()
    assert price.select_stock_code("S0003")
    price.add_selected_to_comparison()
    price.run_comparison()
    _wait(app, lambda: not price.busy and daily._price_comparison_dialog is not None)
    assert len(comparison_events) == 1
    comparison = comparison_events[0]
    assert isinstance(comparison, DailyMarketTechnicalUniversePriceComparisonV1)
    assert tuple(column.selection.stock_code for column in comparison.columns) == ("S0002", "S0003")
    comparison_dialog = daily._price_comparison_dialog
    assert comparison_dialog is not None and comparison_dialog.isVisible()
    comparison_details = comparison_dialog.findChild(DailyMarketTechnicalPriceComparisonV1View)
    assert comparison_details is not None and comparison_details.isVisible()
    assert comparison_details.table.columnCount() == 2
    expected_return = comparison.columns[1].selection
    comparison_details.table.setCurrentCell(0, 1)
    QTest.mouseClick(comparison_details.return_button, Qt.MouseButton.LeftButton)
    _wait(app, lambda: not price.busy)
    assert restored_origins[-1].to_dict() == expected_return.to_dict()
    assert opened_queries[-1] == expected_return.query_json
    assert opened_queries == [origin.query_json, expected_return.query_json]
    assert price.current_query is not None and price.current_page is not None
    assert price.current_query.to_json() == expected_return.query_json
    assert price.current_page.page_identity_sha256 == expected_return.page_identity_sha256
    assert _selected_price_code(price) == "S0003"

    assert price.select_stock_code("S0001")
    mode["change_query"] = True
    price.prepare_bookmark()
    _wait(app, lambda: not price.busy)
    assert confirmation_values
    rejected_bookmark = confirmation_values[-1]
    assert isinstance(rejected_bookmark, DailyMarketTechnicalUniversePriceBookmarkV1)
    assert rejected_bookmark.stock_code == "S0001"
    assert price.current_query is not None
    assert price.current_query.to_json() != rejected_bookmark.selected.query_json
    assert service.get_stocks() == []
    assert saved_events == []
    mode["change_query"] = False

    price.minimum.clear()
    price.apply_query()
    _wait(app, lambda: not price.busy)
    assert price.current_query is not None and price.current_query.to_json() == original_query.to_json()
    assert price.select_stock_code("S0001")
    price.prepare_bookmark()
    _wait(app, lambda: not price.busy)
    assert len(confirmation_values) == 2
    accepted_bookmark = confirmation_values[-1]
    assert isinstance(accepted_bookmark, DailyMarketTechnicalUniversePriceBookmarkV1)
    assert accepted_bookmark.stock_code == "S0001"
    assert tuple(item.stock_code for item in accepted_bookmark.comparison_selections) == (
        "S0002", "S0003",
    )
    _wait(
        app,
        lambda: (
            bool(saved_events)
            and not watchlist.price_bookmark_controls.busy
            and watchlist.price_bookmark_controls.bookmarks.count() == 1
        ),
    )

    records = service.get_stocks()
    assert len(records) == 1
    record = records[0]
    assert record["source"] == TECHNICAL_UNIVERSE_PRICE_BOOKMARK_SOURCE
    assert record["source_id"] == accepted_bookmark.bookmark_id
    payload = record["research_bookmark"]
    assert isinstance(payload, dict)
    assert payload["schema_version"] == "daily-market-technical-universe-price-bookmark.v1"
    typed_label = WatchlistView._research_bookmark_label(payload)
    assert typed_label.startswith("已收藏原價格條件研究")
    assert watchlist.stocks_model is not None
    frame = watchlist.stocks_model.getDataFrame()
    assert frame.iloc[0]["每日研究收藏"].startswith("已收藏原價格條件研究")
    controls = watchlist.price_bookmark_controls
    assert controls.bookmarks.count() == 1
    listed_entry = controls.bookmarks.item(0).data(Qt.ItemDataRole.UserRole)
    assert isinstance(getattr(listed_entry, "bookmark", None), DailyMarketTechnicalUniversePriceBookmarkV1)
    assert getattr(listed_entry, "bookmark_id", None) == accepted_bookmark.bookmark_id

    counted_open, exact_bookmark_opens = _count_exact_bookmark_opens()
    monkeypatch.setattr(
        comparison_module,
        "open_daily_market_technical_universe_price_session_for_query_v1",
        counted_open,
    )
    state_events: list[object] = []
    watchlist.technicalPriceBookmarkStateReady.connect(state_events.append)
    generic_events_before = tuple(generic_stock_events)
    _double_click_watchlist_row(app, watchlist)
    _wait(app, lambda: bool(state_events) and not controls.busy)
    assert generic_stock_events == list(generic_events_before)
    assert len(state_events) == 1
    fresh_state = state_events[0]
    assert isinstance(fresh_state, DailyMarketTechnicalUniversePriceBookmarkStateV1)
    assert fresh_state.bookmark.to_dict() == accepted_bookmark.to_dict()
    assert fresh_state.selected.selection.to_dict() == accepted_bookmark.selected.to_dict()
    assert fresh_state.comparison is not None
    assert tuple(column.selection.stock_code for column in fresh_state.comparison.columns) == (
        "S0002", "S0003",
    )
    assert exact_bookmark_opens == [accepted_bookmark.selected.query_json]

    host = _PriceBookmarkRouteHost(daily)
    hosts.append(host)
    host.resize(1500, 1000)
    host.show()
    app.processEvents()
    tabs = host.recommendation_view.result_source_tabs
    placeholder = tabs.widget(0)
    busy_query = price.current_query
    busy_page = price.current_page
    assert busy_query is not None and busy_page is not None
    busy_code = _selected_price_code(price)
    busy_basket = tuple(item.to_dict() for item in price._basket)
    restore_calls: list[DailyMarketTechnicalUniversePriceBookmarkStateV1] = []
    original_restore_bookmark_state = price.restore_bookmark_state

    def tracked_restore_bookmark_state(
        value: DailyMarketTechnicalUniversePriceBookmarkStateV1,
    ) -> bool:
        restore_calls.append(value)
        return original_restore_bookmark_state(value)

    monkeypatch.setattr(price, "restore_bookmark_state", tracked_restore_bookmark_state)

    price.refresh_sources()
    assert price.busy
    MainWindow._open_price_bookmark_state(cast(MainWindow, host), fresh_state)
    assert tabs.currentWidget() is placeholder
    assert host.workspace_selections == []
    assert restore_calls == [fresh_state]
    assert price.current_query is not None and price.current_page is not None
    assert price.current_query.to_json() == busy_query.to_json()
    assert price.current_page.page_identity_sha256 == busy_page.page_identity_sha256
    assert _selected_price_code(price) == busy_code
    assert tuple(item.to_dict() for item in price._basket) == busy_basket
    _wait(app, lambda: not price.busy)

    assert controls.open_bookmark(accepted_bookmark.bookmark_id) == "started"
    _wait(app, lambda: len(state_events) == 2 and not controls.busy)
    reopened_state = state_events[1]
    assert isinstance(reopened_state, DailyMarketTechnicalUniversePriceBookmarkStateV1)
    assert reopened_state is not fresh_state
    assert reopened_state.bookmark.to_dict() == accepted_bookmark.to_dict()
    assert reopened_state.selected.selection.to_dict() == accepted_bookmark.selected.to_dict()
    assert reopened_state.comparison is not None
    assert tuple(column.selection.stock_code for column in reopened_state.comparison.columns) == (
        "S0002", "S0003",
    )
    assert exact_bookmark_opens == [
        accepted_bookmark.selected.query_json,
        accepted_bookmark.selected.query_json,
    ]

    MainWindow._open_price_bookmark_state(cast(MainWindow, host), reopened_state)
    assert tabs.currentWidget() is daily
    assert host.workspace_selections == ["recommendation"]
    assert restore_calls == [fresh_state, reopened_state]
    assert exact_bookmark_opens == [
        accepted_bookmark.selected.query_json,
        accepted_bookmark.selected.query_json,
    ]
    assert price.current_query is not None and price.current_page is not None
    assert price.current_query.to_json() == accepted_bookmark.selected.query_json
    assert price.current_page.page_identity_sha256 == accepted_bookmark.selected.page_identity_sha256
    assert _selected_price_code(price) == accepted_bookmark.stock_code
    assert tuple(item.stock_code for item in price._basket) == ("S0002", "S0003")

    current_query = price.current_query.to_json()
    current_page_identity = price.current_page.page_identity_sha256
    current_code = _selected_price_code(price)
    current_basket = tuple(item.to_dict() for item in price._basket)
    assert daily.begin_shutdown()
    MainWindow._open_price_bookmark_state(cast(MainWindow, host), reopened_state)
    assert host.workspace_selections == ["recommendation"]
    assert len(restore_calls) == 2
    assert price.current_query is not None and price.current_page is not None
    assert price.current_query.to_json() == current_query
    assert price.current_page.page_identity_sha256 == current_page_identity
    assert _selected_price_code(price) == current_code
    assert tuple(item.to_dict() for item in price._basket) == current_basket

def _count_exact_bookmark_opens() -> tuple[Callable[..., object], list[str]]:
    original = comparison_module.open_daily_market_technical_universe_price_session_for_query_v1
    opened: list[str] = []

    def counted(
        query: DailyMarketTechnicalUniversePriceQueryV1,
        *,
        cancel_callback: Callable[[], object] | None = None,
    ) -> tuple[DailyMarketTechnicalUniversePriceReadSessionV1, DailyMarketTechnicalUniversePriceQueryV1]:
        opened.append(query.to_json())
        return original(query, cancel_callback=cancel_callback)

    return counted, opened


def _double_click_watchlist_row(app: QApplication, watchlist: WatchlistView) -> None:
    assert watchlist.stocks_model is not None
    watchlist.show()
    watchlist.resize(1500, 1100)
    watchlist.page_scroll.ensureWidgetVisible(watchlist.stocks_table)
    app.processEvents()
    index = watchlist.stocks_model.index(0, 0)
    assert index.isValid()
    watchlist.stocks_table.scrollTo(index)
    rect = watchlist.stocks_table.visualRect(index)
    assert rect.isValid() and watchlist.stocks_table.viewport().rect().intersects(rect)
    QTest.mouseClick(watchlist.stocks_table.viewport(), Qt.MouseButton.LeftButton, pos=rect.center())
    QTest.mouseDClick(watchlist.stocks_table.viewport(), Qt.MouseButton.LeftButton, pos=rect.center())
    app.processEvents()
