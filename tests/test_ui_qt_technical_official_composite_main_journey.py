"""以真正 MainWindow 和動態 257 母體驗證複合收藏的儲存與 Watchlist 路由。"""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import time
from typing import cast

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

_REPO = next(
    path for path in Path(__file__).resolve().parents
    if (path / "tests").is_dir() and (path / "app_module").is_dir()
)
for _import_path in (str(_REPO), str(_REPO / "tests")):
    if _import_path not in sys.path:
        sys.path.insert(0, _import_path)

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QAbstractScrollArea,
    QApplication,
    QListWidget,
    QScrollArea,
    QTabBar,
    QTableView,
    QToolButton,
    QWidget,
)

from app_module.daily_market_technical_official_disposition_composite_bookmark_storage_v1 import (
    DailyMarketTechnicalOfficialDispositionCompositeViewBookmarkEnvelopeV1,
)
from test_daily_market_technical_official_disposition_bundle_v1 import _BundleFixture
from ui_qt.main import MainWindow, _drain_qt_deferred_deletes
from ui_qt.views.daily_market_technical_official_disposition_composite_view import (
    DailyMarketTechnicalOfficialDispositionCompositeView,
)
from ui_qt.views.watchlist_view import WatchlistView
from ui_qt.workers.task_worker import running_task_workers


pytest_plugins = ("test_daily_market_technical_official_disposition_composite_reader_v1",)


_ISOLATED_ENVIRONMENT_KEYS = (
    "APPDATA",
    "BALDR_CONFIG",
    "BALDR_ML_RESEARCH_STORAGE_CONFIG",
    "BANKTAIWAN_RECOMMENDATION_LEARNING_OUTPUT_ROOT",
    "DATA_ROOT",
    "FUNDAMENTAL_READ_SNAPSHOT_ROOT",
    "LOCALAPPDATA",
    "MPLCONFIGDIR",
    "OFFICIAL_CALENDAR_CACHE_PATH",
    "OUTPUT_ROOT",
    "PERSONAL_DATA_ROOT",
    "PERSONAL_H20_ACTIVATION_CONFIG",
    "PERSONAL_H20_SQLITE_READ_ROOT",
    "PERSONAL_JOURNAL_MODE",
    "PERSONAL_JOURNAL_ROOT",
    "PERSONAL_MODEL_POLICY_PATH",
    "PERSONAL_STORE_MODE",
    "PERSONAL_STORE_ROOT",
    "PERSONAL_WATCHLIST_SOURCE",
    "PROFILE",
    "RECOMMENDATION_LEARNING_OUTPUT_ROOT",
    "RESEARCH_STATE_ROOT",
    "TECHNICAL_OFFICIAL_DISPOSITION_READ_ROOT",
    "TECHNICAL_UNIVERSE_READ_ROOT",
    "TEMP",
    "TMP",
    "USERPROFILE",
)


@pytest.fixture(scope="module")
def app() -> QApplication:
    instance = cast(QApplication | None, QApplication.instance())
    if instance is None:
        instance = QApplication([])
    return instance


def _wait_until(
    app: QApplication,
    predicate: object,
    *,
    timeout_seconds: float = 90.0,
    label: str,
) -> None:
    if not callable(predicate):
        raise AssertionError("等待條件不是 callable")
    deadline = time.monotonic() + timeout_seconds
    while not predicate():
        app.processEvents()
        if time.monotonic() >= deadline:
            raise AssertionError(f"複合 Main 測試逾時：{label}")
        time.sleep(0.005)
    app.processEvents()


def _fit_main_window_to_available_screen(
    app: QApplication,
    window: MainWindow,
    *,
    requested_width: int,
) -> QRect:
    """讓 MainWindow 完整位於目前可用螢幕，再做真實座標命中。"""

    screen = app.primaryScreen()
    assert screen is not None
    available = screen.availableGeometry()
    margin = 24
    assert available.width() - margin * 2 >= requested_width, (
        f"可用螢幕寬度不足以展示 {requested_width}px 視窗：{available}"
    )
    target_height = min(700, available.height() - margin * 2)
    assert target_height >= window.minimumHeight(), (
        f"可用螢幕高度不足以展示 MainWindow：{available}"
    )
    window.resize(requested_width, target_height)
    window.move(available.left() + margin, available.top() + margin)
    window.show()
    window.activateWindow()
    window.raise_()
    for _ in range(20):
        app.processEvents()
        if available.contains(window.frameGeometry()):
            break
        QTest.qWait(10)
    assert window.isVisible() and window.isActiveWindow()
    assert window.width() == requested_width
    assert available.contains(window.frameGeometry()), (
        f"MainWindow 外框超出螢幕：available={available}, frame={window.frameGeometry()}"
    )
    return available


def _click_visible_research_tab(
    app: QApplication,
    tab_bar: QTabBar,
    tab_index: int,
    *,
    window: MainWindow,
) -> None:
    """真實操作頁籤列捲動按鈕，再點選可見目標頁籤。"""

    assert tab_bar.usesScrollButtons()
    for _ in range(32):
        app.processEvents()
        tab_rect = tab_bar.tabRect(tab_index)
        clipped = tab_rect.intersected(tab_bar.rect())
        if not clipped.isEmpty():
            y = clipped.center().y()
            points = [QPoint(x, y) for x in range(clipped.left(), clipped.right() + 1)]
            points.sort(key=lambda point: abs(point.x() - clipped.center().x()))
            for point in points:
                global_point = tab_bar.mapToGlobal(point)
                if (
                    tab_bar.tabAt(point) == tab_index
                    and QApplication.widgetAt(global_point) is tab_bar
                ):
                    ancestor = tab_bar.parentWidget()
                    while ancestor is not None:
                        mapped = ancestor.mapFromGlobal(global_point)
                        assert ancestor.rect().contains(mapped), (
                            "目標頁籤被祖先裁切："
                            f"ancestor={type(ancestor).__name__}/{ancestor.objectName()}"
                        )
                        if isinstance(ancestor, QAbstractScrollArea):
                            viewport_point = ancestor.viewport().mapFromGlobal(global_point)
                            assert ancestor.viewport().rect().contains(viewport_point), (
                                "目標頁籤位於捲動 viewport 外"
                            )
                        ancestor = ancestor.parentWidget()
                    assert window.isVisible() and window.isActiveWindow()
                    assert window.rect().contains(window.mapFromGlobal(global_point))
                    assert QApplication.widgetAt(global_point) is tab_bar
                    assert tab_bar.tabAt(point) == tab_index
                    QTest.mouseClick(tab_bar, Qt.MouseButton.LeftButton, pos=point)
                    app.processEvents()
                    return

        right_button = next(
            (
                button
                for button in tab_bar.findChildren(QToolButton)
                if button.isVisible()
                and button.isEnabled()
                and button.arrowType() == Qt.ArrowType.RightArrow
            ),
            None,
        )
        assert right_button is not None, (
            "研究頁籤未顯示，且頁籤列沒有可用的向右捲動按鈕："
            f"tab_index={tab_index}, tab_rect={tab_rect}, bar={tab_bar.geometry()}"
        )
        before = tab_bar.tabRect(tab_index)
        _click_visible(right_button)
        app.processEvents()
        assert tab_bar.tabRect(tab_index) != before, "頁籤捲動按鈕未移動目標頁籤"
    raise AssertionError("32 次真實頁籤捲動後仍無法點選複合研究頁籤")


def _configure_private_empty_main_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    bundle_fixture: _BundleFixture,
) -> tuple[Path, Path]:
    """沿 MainWindow 真實初始化路徑指定隔離資料根與空 Watchlist。"""

    for name in _ISOLATED_ENVIRONMENT_KEYS:
        monkeypatch.delenv(name, raising=False)

    root = tmp_path / "composite-main-private-empty"
    data_root = root / "data"
    output_root = root / "output"
    research_state_root = root / "research-state"
    temporary_root = root / "temporary"
    appdata_root = root / "appdata"
    localappdata_root = root / "localappdata"
    ml_storage_root = root / "ml-research"
    technical_read_root = root / "technical-read"
    fundamental_read_root = root / "fundamental-read"
    h20_read_root = root / "h20-read"
    for path in (
        data_root,
        output_root,
        research_state_root,
        temporary_root,
        appdata_root,
        localappdata_root,
        ml_storage_root,
        technical_read_root,
        fundamental_read_root,
        h20_read_root,
    ):
        path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(tempfile, "tempdir", str(temporary_root))

    ml_config = root / "ml-research-storage.json"
    ml_config.write_text(
        json.dumps(
            {"schema_version": "ml-research-storage.v1", "active_root": str(ml_storage_root)},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    environment = {
        "APPDATA": str(appdata_root),
        "BALDR_CONFIG": str(root / "baldr-config.json"),
        "BALDR_ML_RESEARCH_STORAGE_CONFIG": str(ml_config),
        "BANKTAIWAN_RECOMMENDATION_LEARNING_OUTPUT_ROOT": str(
            research_state_root / "bank-taiwan-recommendation-learning"
        ),
        "DATA_ROOT": str(data_root),
        "FUNDAMENTAL_READ_SNAPSHOT_ROOT": str(fundamental_read_root),
        "LOCALAPPDATA": str(localappdata_root),
        "MPLCONFIGDIR": str(output_root / "application-state" / "matplotlib"),
        "OFFICIAL_CALENDAR_CACHE_PATH": str(data_root / "official-calendar-cache.json"),
        "OUTPUT_ROOT": str(output_root),
        "PERSONAL_H20_ACTIVATION_CONFIG": str(
            data_root / "personal" / "recommendation_h20" / "activation.json"
        ),
        "PERSONAL_H20_SQLITE_READ_ROOT": str(h20_read_root),
        "PERSONAL_MODEL_POLICY_PATH": str(research_state_root / "personal-use-policy.json"),
        "PROFILE": "prod",
        "QT_QPA_PLATFORM": "offscreen",
        "RECOMMENDATION_LEARNING_OUTPUT_ROOT": str(
            research_state_root / "recommendation-learning"
        ),
        "RESEARCH_STATE_ROOT": str(research_state_root),
        "TECHNICAL_OFFICIAL_DISPOSITION_READ_ROOT": str(bundle_fixture.bundle_root),
        "TECHNICAL_UNIVERSE_READ_ROOT": str(technical_read_root),
        "TEMP": str(temporary_root),
        "TMP": str(temporary_root),
        "USERPROFILE": str(root / "user-profile"),
    }
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    return root, output_root


def _click_visible(widget: QWidget) -> None:
    ancestor = widget.parentWidget()
    while ancestor is not None:
        if isinstance(ancestor, QScrollArea):
            ancestor.ensureWidgetVisible(widget, 0, 12)
        ancestor = ancestor.parentWidget()
    QApplication.processEvents()

    if not widget.isVisible():
        raise AssertionError("要操作的 Qt 控制項不可見")
    if not widget.isEnabled():
        raise AssertionError("要操作的 Qt 控制項未啟用")
    rect = widget.rect()
    if rect.isEmpty() or not rect.contains(rect.center()):
        raise AssertionError("Qt 控制項中心不在自身可見區域")

    center_global = widget.mapToGlobal(rect.center())
    ancestor = widget.parentWidget()
    while ancestor is not None:
        center_in_ancestor = ancestor.mapFromGlobal(center_global)
        if not ancestor.rect().contains(center_in_ancestor):
            raise AssertionError("Qt 控制項中心被祖先視窗裁切")
        if isinstance(ancestor, QAbstractScrollArea):
            viewport = ancestor.viewport()
            center_in_viewport = viewport.mapFromGlobal(center_global)
            if not viewport.rect().contains(center_in_viewport):
                raise AssertionError("Qt 控制項中心在捲動 viewport 可見範圍外")
        ancestor = ancestor.parentWidget()

    top_level = widget.window()
    if not top_level.rect().contains(top_level.mapFromGlobal(center_global)):
        raise AssertionError("Qt 控制項中心在頂層視窗可見範圍外")
    hit_widget = QApplication.widgetAt(center_global)
    if hit_widget is None or (
        hit_widget is not widget and not widget.isAncestorOf(hit_widget)
    ):
        hit_name = repr(hit_widget.objectName()) if hit_widget is not None else None
        raise AssertionError(
            "Qt 控制項中心目前命中其他 widget："
            f"target={type(widget).__name__}/{widget.objectName()!r}, "
            f"hit={type(hit_widget).__name__ if hit_widget is not None else None}/"
            f"{hit_name}"
        )
    QTest.mouseClick(widget, Qt.MouseButton.LeftButton, pos=rect.center())


def _select_result_code(
    app: QApplication,
    view: DailyMarketTechnicalOfficialDispositionCompositeView,
    stock_code: str,
) -> None:
    page = view.current_page
    assert page is not None
    row_number = next(
        index for index, row in enumerate(page.rows) if row.stock_code == stock_code
    )
    model = view.results_table.model()
    assert model is not None
    index = model.index(row_number, 0)
    view.results_table.scrollTo(index)
    app.processEvents()
    rect = view.results_table.visualRect(index)
    assert rect.isValid() and view.results_table.viewport().rect().contains(rect.center())
    QTest.mouseClick(
        view.results_table.viewport(),
        Qt.MouseButton.LeftButton,
        pos=rect.center(),
    )
    app.processEvents()
    assert view._selected_row is not None
    assert view._selected_row.stock_code == stock_code


def _composite_watchlist_rows(watchlist: WatchlistView, identity: str) -> list[int]:
    model = watchlist.stocks_model
    if model is None:
        return []
    frame = model.getDataFrame()
    return [
        row_number
        for row_number, (_, row) in enumerate(frame.iterrows())
        if row.get("source") == "technical_official_disposition_composite_research_bookmark"
        and row.get("source_id") == identity
    ]


def _has_unique_composite_watchlist_row(watchlist: WatchlistView, identity: str) -> bool:
    return len(_composite_watchlist_rows(watchlist, identity)) == 1


def _find_composite_watchlist_row(watchlist: WatchlistView, identity: str) -> int:
    matches = _composite_watchlist_rows(watchlist, identity)
    assert len(matches) == 1
    return matches[0]


def _click_list_row(app: QApplication, widget: QListWidget, row_number: int) -> None:
    item = widget.item(row_number)
    assert item is not None
    widget.scrollToItem(item)
    app.processEvents()
    rect = widget.visualItemRect(item)
    assert rect.isValid() and widget.viewport().rect().contains(rect.center())
    QTest.mouseClick(
        widget.viewport(),
        Qt.MouseButton.LeftButton,
        pos=rect.center(),
    )
    app.processEvents()
    assert widget.currentRow() == row_number


def _click_table_row(app: QApplication, widget: QTableView, row_number: int) -> None:
    model = widget.model()
    assert model is not None
    index = model.index(row_number, 0)
    widget.scrollTo(index)
    app.processEvents()
    rect = widget.visualRect(index)
    assert rect.isValid() and widget.viewport().rect().contains(rect.center())
    QTest.mouseClick(
        widget.viewport(),
        Qt.MouseButton.LeftButton,
        pos=rect.center(),
    )
    app.processEvents()
    assert widget.currentIndex().row() == row_number


def test_real_main_saves_and_reopens_composite_bookmark_through_visible_watchlist_route(
    app: QApplication,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    bundle_fixture: _BundleFixture,
) -> None:
    """由真 MainWindow 保存 typed envelope，並以可見 Watchlist 控制項精確重開。"""

    _, private_output_root = _configure_private_empty_main_environment(
        monkeypatch,
        tmp_path,
        bundle_fixture,
    )
    window: MainWindow | None = None
    saver_was_requested = False
    try:
        window = MainWindow()
        assert window.config.output_root.resolve() == private_output_root.resolve()
        assert window.config.technical_official_disposition_read_root.resolve() == (
            bundle_fixture.bundle_root.resolve()
        )
        assert window.watchlist_service is not None
        assert window.watchlist_service.canonical_repository_path.resolve().is_relative_to(
            private_output_root.resolve()
        )
        _fit_main_window_to_available_screen(app, window, requested_width=640)

        _click_visible(window.left_navigation.button_for_key("recommendation"))
        view = window.technical_official_composite_research_view
        assert isinstance(view, DailyMarketTechnicalOfficialDispositionCompositeView)
        tabs = window.recommendation_view.result_source_tabs
        tab_index = tabs.indexOf(view)
        assert tab_index >= 0
        _click_visible_research_tab(
            app,
            tabs.tabBar(),
            tab_index,
            window=window,
        )
        assert tabs.currentWidget() is view

        events: list[tuple[str, bool]] = []
        prepared: list[object] = []
        route_payloads: list[object] = []
        generic_research: list[object] = []
        latest_research: list[object] = []
        view.operationSettled.connect(
            lambda kind, succeeded: events.append((str(kind), bool(succeeded)))
        )
        view.bookmarkPrepared.connect(prepared.append)
        window.watchlist_view.technicalCompositeBookmarkReady.connect(route_payloads.append)
        window.watchlist_view.stockResearchRequested.connect(generic_research.append)
        window.watchlist_view.latestResearchRequested.connect(latest_research.append)

        event_count = len(events)
        _click_visible(view.refresh_catalog_button)
        _wait_until(
            app,
            lambda: len(events) > event_count,
            label="盤點固定來源",
        )
        assert events[-1] == ("盤點已保存來源清單", True)
        assert view.catalog_list.count() == 1
        _click_list_row(app, view.catalog_list, 0)
        view.page_size_box.setValue(256)
        for scope, check in view.scope_checks.items():
            check.setChecked(scope == "included_processed")

        event_count = len(events)
        _click_visible(view.open_candidate_button)
        _wait_until(
            app,
            lambda: len(events) > event_count,
            label="全母體複合查詢",
        )
        assert events[-1] == ("精確核驗並執行全母體複合查詢", True)
        result = view.current_result
        first_page = view.current_page
        assert result is not None and first_page is not None
        population = result.counts.base_f17_counts.population
        assert (
            population.declared_count,
            population.included_count,
            population.processed_count,
            population.excluded_count,
            population.pending_count,
        ) == (258, 257, 257, 1, 0)
        assert result.visible_count == 257
        assert first_page.page_size == 256 and first_page.page_count == 2
        assert len(first_page.rows) == 256
        assert tuple(row.stock_code for row in first_page.rows) == bundle_fixture.included_codes[:256]

        first_code = first_page.rows[0].stock_code
        _select_result_code(app, view, first_code)
        _click_visible(view.add_comparison_button)
        event_count = len(events)
        _click_visible(view.next_page_button)
        _wait_until(
            app,
            lambda: len(events) > event_count,
            label="讀取第二頁",
        )
        assert events[-1] == ("讀取全域排序結果的指定頁", True)
        second_page = view.current_page
        assert second_page is not None and second_page.page_index == 1
        assert len(second_page.rows) == 1
        selected_code = second_page.rows[0].stock_code
        assert selected_code == bundle_fixture.included_codes[-1]
        _select_result_code(app, view, selected_code)
        _click_visible(view.add_comparison_button)
        assert tuple(item.selection.stock_code for item in view._basket) == (
            first_code,
            selected_code,
        )

        original_result = view.current_result
        original_page = view.current_page
        original_query_json = result.query.to_json()
        original_page_request_identity = view._page_request.request_identity_sha256
        original_row = view._selected_row
        assert original_result is not None and original_page is not None and original_row is not None
        view.page_scroll.ensureWidgetVisible(view.bookmark_button, 0, 24)
        app.processEvents()
        scroll_bar = view.page_scroll.verticalScrollBar()
        assert scroll_bar.maximum() > 0
        original_scroll = scroll_bar.value()
        assert original_scroll > 0
        bookmark_center = view.bookmark_button.mapTo(
            view.page_scroll.viewport(),
            view.bookmark_button.rect().center(),
        )
        assert view.page_scroll.viewport().rect().contains(bookmark_center)
        _click_visible(view.bookmark_button)
        assert hasattr(window, "_technical_official_bookmark_workers")
        saver_was_requested = True
        _wait_until(
            app,
            lambda: len(prepared) == 1
            and not window._technical_official_bookmark_workers,
            label="Main typed saver native worker",
        )
        envelope = prepared[0]
        assert type(envelope) is DailyMarketTechnicalOfficialDispositionCompositeViewBookmarkEnvelopeV1
        assert envelope.selected_was_in_comparison_basket is True
        service = window.watchlist_service
        saved = service.read_composite_research_bookmark(
            envelope.envelope_identity_sha256
        )
        assert type(saved) is DailyMarketTechnicalOfficialDispositionCompositeViewBookmarkEnvelopeV1
        assert saved.to_json() == envelope.to_json()

        watchlist_button = window.left_navigation.button_for_key("watchlist")
        _click_visible(watchlist_button)
        watchlist = window.watchlist_view
        assert isinstance(watchlist, WatchlistView)
        _wait_until(
            app,
            lambda: _has_unique_composite_watchlist_row(
                watchlist,
                envelope.envelope_identity_sha256,
            ),
            label="Watchlist 讀回剛保存的複合收藏",
        )
        row_number = _find_composite_watchlist_row(
            watchlist,
            envelope.envelope_identity_sha256,
        )
        _click_table_row(app, watchlist.stocks_table, row_number)
        assert watchlist.stock_analysis_btn.text() == "查看選中個股研究報告"
        assert watchlist.stock_analysis_btn.isVisible()
        assert watchlist.stock_analysis_btn.isEnabled()
        _click_visible(watchlist.stock_analysis_btn)
        _wait_until(
            app,
            lambda: len(route_payloads) == 1
            and view.active_worker is None
            and view.current_page is not None
            and view.current_page.request_identity_sha256
            == original_page_request_identity,
            label="可見 Watchlist 按鈕的 typed fresh reopen",
        )
        assert type(route_payloads[0]) is DailyMarketTechnicalOfficialDispositionCompositeViewBookmarkEnvelopeV1
        assert route_payloads[0].to_json() == envelope.to_json()
        assert generic_research == [] and latest_research == []
        assert window.recommendation_view.result_source_tabs.currentWidget() is view
        assert view.current_result is not None
        assert view.current_result.query.to_json() == original_query_json
        assert view.current_result.query.query_identity_sha256 == original_result.query.query_identity_sha256
        assert view.current_result.operation_identity_sha256 == original_result.operation_identity_sha256
        assert view.current_page is not None
        assert view.current_page.page_identity_sha256 == original_page.page_identity_sha256
        assert view.current_page.request_identity_sha256 == original_page_request_identity
        assert view._selected_row is not None
        assert view._selected_row.row_identity_sha256 == original_row.row_identity_sha256
        assert tuple(item.selection.stock_code for item in view._basket) == (
            first_code,
            selected_code,
        )
        assert view.page_scroll.verticalScrollBar().value() == original_scroll

        watchlist_button = window.left_navigation.button_for_key("watchlist")
        _click_visible(watchlist_button)
        row_number = _find_composite_watchlist_row(
            watchlist,
            envelope.envelope_identity_sha256,
        )
        _click_table_row(app, watchlist.stocks_table, row_number)
        model = watchlist.stocks_table.model()
        assert model is not None
        index = model.index(row_number, 0)
        watchlist.stocks_table.scrollTo(index)
        app.processEvents()
        rect = watchlist.stocks_table.visualRect(index)
        assert rect.isValid() and watchlist.stocks_table.viewport().rect().contains(rect.center())
        QTest.mouseDClick(
            watchlist.stocks_table.viewport(),
            Qt.MouseButton.LeftButton,
            pos=rect.center(),
        )
        _wait_until(
            app,
            lambda: len(route_payloads) == 2
            and view.active_worker is None
            and view.current_page is not None
            and view.current_page.request_identity_sha256
            == original_page_request_identity,
            label="Watchlist 列雙擊的 typed fresh reopen",
        )
        assert route_payloads[1].to_json() == envelope.to_json()
        assert generic_research == [] and latest_research == []
    finally:
        if window is not None:
            window.close()
            _wait_until(
                app,
                lambda: not window.isVisible(),
                timeout_seconds=30.0,
                label="MainWindow 正常關閉",
            )
            view = window.technical_official_composite_research_view
            if isinstance(view, DailyMarketTechnicalOfficialDispositionCompositeView):
                assert view.active_worker is None
                assert not view._has_running_worker()
            if saver_was_requested:
                assert hasattr(window, "_technical_official_bookmark_workers")
            if hasattr(window, "_technical_official_bookmark_workers"):
                assert not window._technical_official_bookmark_workers
            _drain_qt_deferred_deletes(app, (window,))
            assert running_task_workers() == ()
