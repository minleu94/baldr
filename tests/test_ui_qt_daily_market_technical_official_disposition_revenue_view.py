"""F12 月營收研究頁的真來源、跨頁與保存重開旅程。"""

from __future__ import annotations

import os
from pathlib import Path
from threading import get_ident
import time
from types import SimpleNamespace
from typing import Any, cast

import pytest
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QPlainTextEdit, QTabWidget, QWidget

pytest_plugins = ("test_daily_market_technical_official_disposition_revenue_source_v1",)

from app_module.daily_market_technical_official_disposition_bundle_v1 import (
    DailyMarketTechnicalOfficialDispositionBundleReaderV1,
)
from app_module.daily_market_technical_official_disposition_revenue_bookmark_v1 import (
    DailyMarketTechnicalOfficialDispositionRevenueBookmarkV1,
    DailyMarketTechnicalOfficialDispositionRevenueBookmarkV1Error,
)
from app_module.daily_market_research_bookmark import DailyMarketResearchBookmarkError
from app_module.daily_market_technical_official_disposition_revenue_query_v1 import (
    DailyMarketTechnicalOfficialDispositionRevenuePageRequestV1,
    DailyMarketTechnicalOfficialDispositionRevenueQueryPageV1,
    DailyMarketTechnicalOfficialDispositionRevenueResultRowV1,
    DailyMarketTechnicalOfficialDispositionRevenueVerifiedQueryResultV1,
)
from app_module import daily_market_technical_official_disposition_revenue_source_v1 as revenue_source_module
from data_module.daily_market_monthly_revenue_read_session_v1 import (
    DailyMarketMonthlyRevenueSourceReferenceV2,
)
from app_module.watchlist_service import WatchlistService
from ui_qt.main import MainWindow, apply_app_theme
from ui_qt.models.saved_research_page_table_model import (
    SavedResearchPageTableModel,
    SavedResearchTableRow,
)
from ui_qt.views.daily_market_technical_official_disposition_revenue_view import (
    DailyMarketTechnicalOfficialDispositionRevenueView,
    _OpenedQuery,
    _SourceChoice,
    _project_revenue_page_table_rows,
    _parse_stock_codes,
)
from ui_qt.views import daily_market_technical_official_disposition_revenue_view as revenue_view_module


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def app() -> QApplication:
    instance = cast(QApplication | None, QApplication.instance())
    if instance is None:
        instance = QApplication([])
    apply_app_theme(instance)
    return instance


def _wait_for_operation(
    app: QApplication,
    results: list[tuple[str, bool]],
    previous_count: int,
    *,
    expected_kind: str,
    status_label: QLabel | None = None,
    worker_errors: list[str] | None = None,
    timeout_seconds: float = 420.0,
) -> tuple[str, bool]:
    deadline = time.monotonic() + timeout_seconds
    while len(results) <= previous_count and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert len(results) > previous_count, f"operation timed out: {expected_kind}"
    outcome = results[previous_count]
    assert outcome[0] == expected_kind
    if outcome[1] is not True:
        detail = status_label.text() if status_label is not None else ""
        errors = "\n".join(worker_errors or ())
        raise AssertionError(
            f"operation failed: {expected_kind}; status={detail}; worker_errors={errors}"
        )
    return outcome


def _click_stock(
    app: QApplication,
    view: DailyMarketTechnicalOfficialDispositionRevenueView,
    stock_code: str,
) -> None:
    index = view.table_model.index_for_stock(stock_code)
    assert index.isValid()
    rectangle = view.results_table.visualRect(index)
    assert rectangle.isValid() and rectangle.width() > 0 and rectangle.height() > 0
    QTest.mouseClick(
        view.results_table.viewport(),
        Qt.MouseButton.LeftButton,
        pos=rectangle.center(),
    )
    app.processEvents()


@pytest.mark.parametrize("width", (460, 800))
def test_revenue_view_fits_narrow_and_wide_windows(
    app: QApplication,
    width: int,
) -> None:
    view = DailyMarketTechnicalOfficialDispositionRevenueView()
    view.resize(width, 700)
    view.show()
    app.processEvents()

    assert view.width() == width
    assert view.height() == 700
    assert view.page_scroll.widgetResizable()
    assert view.page_scroll.horizontalScrollBar().maximum() == 0
    assert view.results_table.minimumHeight() >= 220
    assert view.detail_text.minimumHeight() >= 220
    assert view.audit_text.minimumHeight() >= 220
    for button in (
        view.choose_root_button,
        view.choose_reference_button,
        view.choose_operation_root_button,
        view.refresh_catalog_button,
        view.open_candidate_button,
        view.apply_query_button,
        view.clear_filters_button,
        view.cancel_button,
        view.detail_button,
        view.compare_button,
        view.bookmark_button,
    ):
        assert button.width() >= button.sizeHint().width()

    # 明細與稽核欄都以實際可捲動文字編輯器呈現；確認最後一行能被
    # Ctrl+End 帶入外層頁面 viewport，而非只檢查控件高度或按鈕尺寸。
    view.results_stack.setCurrentIndex(1)
    app.processEvents()
    detail_tail = "DETAIL-END-SENTINEL"
    view.detail_text.setPlainText("\n".join(
        [f"保存明細第 {index:03d} 行" for index in range(80)] + [detail_tail]
    ))
    view.activateWindow()
    view.detail_text.setFocus()
    app.processEvents()
    assert view.detail_text.hasFocus()
    _scroll_editor_tail_into_page_viewport(app, view, view.detail_text, detail_tail)

    audit_tail = "AUDIT-END-SENTINEL"
    view.audit_text.setPlainText("\n".join(
        [f'  "source_field_{index:03d}": "保存欄位"'
         for index in range(80)] + [audit_tail]
    ))
    view.audit_toggle.setChecked(True)
    app.processEvents()
    view.activateWindow()
    view.audit_text.setFocus()
    app.processEvents()
    assert view.audit_text.hasFocus()
    _scroll_editor_tail_into_page_viewport(app, view, view.audit_text, audit_tail)

    assert view.begin_shutdown()
    view.close()
    app.processEvents()


def _scroll_editor_tail_into_page_viewport(
    app: QApplication,
    view: DailyMarketTechnicalOfficialDispositionRevenueView,
    editor: QPlainTextEdit,
    expected_tail: str,
) -> None:
    page_down_count = 0
    while (
        editor.verticalScrollBar().value() < editor.verticalScrollBar().maximum()
        and page_down_count < 128
    ):
        QTest.keyClick(editor, Qt.Key.Key_PageDown)
        app.processEvents()
        page_down_count += 1
    assert editor.verticalScrollBar().value() == editor.verticalScrollBar().maximum()
    last_block = editor.document().lastBlock()
    assert last_block.text() == expected_tail
    cursor_rect = editor.cursorRect(QTextCursor(last_block))
    view.page_scroll.ensureWidgetVisible(editor, 0, 0)
    app.processEvents()
    view.page_scroll.setFocus()
    app.processEvents()
    page_down_count = 0
    while (
        view.page_scroll.verticalScrollBar().value()
        < view.page_scroll.verticalScrollBar().maximum()
        and page_down_count < 128
    ):
        QTest.keyClick(view.page_scroll, Qt.Key.Key_PageDown)
        app.processEvents()
        page_down_count += 1
    assert (
        view.page_scroll.verticalScrollBar().value()
        == view.page_scroll.verticalScrollBar().maximum()
    )
    cursor_top_global = editor.viewport().mapToGlobal(cursor_rect.topLeft())
    cursor_bottom_global = editor.viewport().mapToGlobal(cursor_rect.bottomRight())
    cursor_top_in_page = view.page_scroll.viewport().mapFromGlobal(cursor_top_global)
    cursor_bottom_in_page = view.page_scroll.viewport().mapFromGlobal(cursor_bottom_global)
    visible_rect = view.page_scroll.viewport().rect()
    assert cursor_rect.height() > 0
    assert visible_rect.contains(cursor_top_in_page)
    assert visible_rect.contains(cursor_bottom_in_page)


def test_stock_filter_parser_rejects_partial_or_ambiguous_input() -> None:
    assert _parse_stock_codes("2382 2330，2317", was_truncated=False) == (
        "2317", "2330", "2382",
    )
    for value in ("2382,,2330", "2382,", ",2382", "2382 2382", "2382,2330x"):
        with pytest.raises(ValueError):
            _parse_stock_codes(value, was_truncated=False)
    with pytest.raises(ValueError, match="too_long"):
        _parse_stock_codes("2382", was_truncated=True)


def test_revenue_page_projection_matches_six_column_model_contract(
    app: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_row = SimpleNamespace(stock_code="2330")
    monkeypatch.setattr(
        revenue_view_module,
        "revenue_row_cells_v1",
        lambda _row: ("2330", "符合", "未知", "已保存", "22.0%", "符合"),
    )
    monkeypatch.setattr(
        revenue_view_module,
        "format_technical_official_revenue_research_row_v1",
        lambda _row: "完整保存事實末行",
    )

    projected = _project_revenue_page_table_rows(cast(Any, (source_row,)))
    model: SavedResearchPageTableModel[object] = SavedResearchPageTableModel(
        ("股票代碼", "技術條件", "四均線", "YoY 資料", "YoY 百分比", "複合結果"),
        maximum_page_size=256,
    )
    model.replace_page(cast(Any, projected))

    assert len(projected) == 1
    assert len(projected[0].cells) == 6
    assert len(projected[0].tooltips) == 6
    assert projected[0].source_row is source_row
    assert all("完整保存事實末行" in tooltip for tooltip in projected[0].tooltips)
    assert model.rowCount() == 1
    assert model.columnCount() == 6
    assert model.data(model.index(0, 5), Qt.ItemDataRole.ToolTipRole) == projected[0].tooltips[5]


def test_failed_open_page_projection_preserves_current_view_state(app: QApplication) -> None:
    view = DailyMarketTechnicalOfficialDispositionRevenueView()
    sentinel_source = object()
    sentinel_recipe = object()
    sentinel_query = object()
    sentinel_result = object()
    sentinel_request = object()
    sentinel_page = object()
    view._source = cast(_SourceChoice, sentinel_source)
    view._recipe = cast(Any, sentinel_recipe)
    view._query = cast(Any, sentinel_query)
    view._result = cast(Any, sentinel_result)
    view._page_request = cast(Any, sentinel_request)
    view._page = cast(Any, sentinel_page)
    prior_row = SavedResearchTableRow(
        "2330",
        cast(DailyMarketTechnicalOfficialDispositionRevenueResultRowV1, object()),
        ("2330", "符合", "未知", "已保存", "22.0%", "符合"),
        ("提示",) * 6,
    )
    view.table_model.replace_page((prior_row,))
    invalid_source_row = SimpleNamespace(stock_code="2317")
    invalid_page = cast(
        DailyMarketTechnicalOfficialDispositionRevenueQueryPageV1,
        SimpleNamespace(rows=(invalid_source_row,)),
    )
    opened = _OpenedQuery(
        cast(_SourceChoice, object()),
        cast(Any, object()),
        cast(Any, object()),
        cast(Any, object()),
        cast(Any, object()),
        invalid_page,
    )

    with pytest.raises(ValueError, match="technical_official_revenue_presenter_row_invalid"):
        view._apply_opened_query(opened)

    assert view._source is sentinel_source
    assert view._recipe is sentinel_recipe
    assert view._query is sentinel_query
    assert view._result is sentinel_result
    assert view._page_request is sentinel_request
    assert view._page is sentinel_page
    assert view.table_model.rowCount() == 1
    assert view.table_model.row_at(0) is prior_row.source_row
    assert view.begin_shutdown()
    view.close()
    app.processEvents()


def test_real_reader_worker_page_basket_detail_bookmark_and_fresh_restore(
    app: QApplication,
    bundle_fixture: Any,
    monthly_source_reference: DailyMarketMonthlyRevenueSourceReferenceV2,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reference_path = tmp_path / "monthly-source-reference.json"
    reference_path.write_text(monthly_source_reference.to_json(), encoding="utf-8")
    operation_parent = tmp_path / "revenue-reader-operations"
    operation_parent.mkdir()
    view = DailyMarketTechnicalOfficialDispositionRevenueView(
        bundle_output_root=bundle_fixture.bundle_root,
        monthly_reference_path=reference_path,
        operation_root_parent=operation_parent,
    )
    view.page_size_box.setValue(128)
    view.show()
    app.processEvents()

    outcomes: list[tuple[str, bool]] = []
    view.operationSettled.connect(lambda kind, success: outcomes.append((kind, success)))
    original_read_exact = DailyMarketTechnicalOfficialDispositionBundleReaderV1.read_exact
    exact_read_count = 0
    opener_thread_ids: list[int] = []
    exact_reads: list[Any] = []
    result_exact_reads: dict[int, Any] = {}
    page_read_observations: list[tuple[int, int, int, bool]] = []

    def counted_read_exact(reader: Any, *args: Any, **kwargs: Any) -> Any:
        nonlocal exact_read_count
        exact_read_count += 1
        return cast(Any, original_read_exact)(reader, *args, **kwargs)

    monkeypatch.setattr(
        DailyMarketTechnicalOfficialDispositionBundleReaderV1,
        "read_exact",
        counted_read_exact,
    )
    original_bundle_open = (
        revenue_source_module.open_daily_market_technical_official_disposition_revenue_bundle_source_v1
    )

    def counted_bundle_open(*args: Any, **kwargs: Any) -> Any:
        exact = cast(Any, original_bundle_open)(*args, **kwargs)
        opener_thread_ids.append(get_ident())
        exact_reads.append(exact)
        result_exact_reads[id(exact.result)] = exact
        return exact

    monkeypatch.setattr(
        revenue_source_module,
        "open_daily_market_technical_official_disposition_revenue_bundle_source_v1",
        counted_bundle_open,
    )
    original_result_read_page_request = (
        DailyMarketTechnicalOfficialDispositionRevenueVerifiedQueryResultV1.read_page_request
    )

    def observe_result_page_read(
        result: DailyMarketTechnicalOfficialDispositionRevenueVerifiedQueryResultV1,
        request: DailyMarketTechnicalOfficialDispositionRevenuePageRequestV1 | str | bytes,
        **kwargs: Any,
    ) -> Any:
        page_index = (
            request.page_index
            if type(request) is DailyMarketTechnicalOfficialDispositionRevenuePageRequestV1
            else -1
        )
        exact = result_exact_reads.get(id(result))
        page_read_observations.append((
            id(result), get_ident(), page_index,
            exact is not None and exact.closed and exact.monthly_sqlite_connection_closed,
        ))
        return cast(Any, original_result_read_page_request)(result, request, **kwargs)

    monkeypatch.setattr(
        DailyMarketTechnicalOfficialDispositionRevenueVerifiedQueryResultV1,
        "read_page_request",
        observe_result_page_read,
    )
    emitted_bookmarks: list[DailyMarketTechnicalOfficialDispositionRevenueBookmarkV1] = []
    view.bookmarkPrepared.connect(emitted_bookmarks.append)

    try:
        assert view.set_bundle_output_root(bundle_fixture.bundle_root)
        assert view.set_monthly_reference_path(reference_path)
        assert view.set_operation_root_parent(operation_parent)

        before = len(outcomes)
        view.refresh_catalog()
        _wait_for_operation(
            app, outcomes, before,
            expected_kind="盤點保存來源 metadata",
            status_label=view.status_label,
        )
        assert view.catalog_list.count() == 1
        assert "尚未核驗" in view.catalog_list.item(0).text()
        view.catalog_list.setCurrentRow(0)
        view.open_selected_candidate()
        open_worker_errors: list[str] = []
        open_worker = view.active_worker
        assert open_worker is not None
        open_worker.error.connect(open_worker_errors.append)
        _wait_for_operation(
            app, outcomes, before + 1,
            expected_kind="核驗雙來源並執行全母體查詢",
            status_label=view.status_label,
            worker_errors=open_worker_errors,
        )

        original_result = view.current_result
        original_page_zero = view.current_page
        assert original_result is not None and original_page_zero is not None
        assert original_result.counts.declared_count == 258
        assert original_result.counts.visible_count == 258
        assert original_result.scope == "current_only"
        assert original_result.availability_status == "unknown"
        assert original_result.historical_pit_eligible is False
        assert original_page_zero.page_index == 0
        assert exact_read_count == 1
        assert len(exact_reads) == 1
        assert exact_reads[0].closed is True
        assert exact_reads[0].monthly_sqlite_connection_closed is True
        assert len(opener_thread_ids) == 1
        assert opener_thread_ids[0] != get_ident()
        initial_page_reads = [
            item for item in page_read_observations
            if item[0] == id(original_result) and item[2] == 0
        ]
        assert initial_page_reads
        assert initial_page_reads[0][1] == opener_thread_ids[0]
        assert initial_page_reads[0][3] is False
        assert view.active_worker is None
        assert not view._has_running_worker()

        first_code = original_page_zero.rows[0].stock_code
        _click_stock(app, view, first_code)
        view.detail_button.click()
        app.processEvents()
        assert view.results_stack.currentIndex() == 1
        assert first_code in view.detail_text.toPlainText()
        assert "current-only" in view.detail_text.toPlainText()
        assert "不具歷史 PIT 資格" in view.detail_text.toPlainText()
        view.return_button.click()
        app.processEvents()
        assert view.current_page is original_page_zero
        assert view.current_result is original_result

        view.add_comparison_button.click()
        assert view.comparison_basket == ((first_code, 0),)
        before = len(outcomes)
        view.navigate_page(1)
        _wait_for_operation(
            app, outcomes, before,
            expected_kind="讀取已核驗全域排序結果的指定頁",
            status_label=view.status_label,
        )
        page_one = view.current_page
        assert page_one is not None and page_one.page_index == 1
        assert view.current_result is original_result
        assert view.comparison_basket == ((first_code, 0),)
        assert exact_read_count == 1, "warm page read must not reopen F17 or rebuild full-N query"
        warm_page_reads = [
            item for item in page_read_observations
            if item[0] == id(original_result) and item[2] == 1 and item[3]
        ]
        assert warm_page_reads
        assert warm_page_reads[-1][1] != opener_thread_ids[0]

        second_code = page_one.rows[0].stock_code
        _click_stock(app, view, second_code)
        view.add_comparison_button.click()
        assert view.comparison_basket == ((first_code, 0), (second_code, 1))

        comparison_rows: list[tuple[object, ...]] = []

        def close_comparison(rows: object) -> None:
            assert isinstance(rows, tuple)
            comparison_rows.append(rows)
            QTimer.singleShot(0, lambda: _accept_comparison_dialog(app))

        view.comparisonReady.connect(close_comparison)
        before = len(outcomes)
        view.compare_button.click()
        _wait_for_operation(
            app, outcomes, before,
            expected_kind="比較同一已核驗全域結果中的選取列",
            status_label=view.status_label,
        )
        assert len(comparison_rows) == 1
        actual_compared = cast(tuple[Any, ...], comparison_rows[0])
        assert tuple(row.stock_code for row in actual_compared) == (first_code, second_code)
        original_rows = {
            row.stock_code: row.to_dict()
            for row in (*original_page_zero.rows, *page_one.rows)
            if row.stock_code in {first_code, second_code}
        }
        assert {row.stock_code: row.to_dict() for row in actual_compared} == original_rows
        assert exact_read_count == 1, "comparison must page the same issued full-N result"
        assert any(
            result_id == id(original_result) and connection_closed
            and worker_thread_id != opener_thread_ids[0]
            for result_id, worker_thread_id, _page_index, connection_closed
            in page_read_observations
        )

        _click_stock(app, view, second_code)
        view.prepare_bookmark()
        assert len(emitted_bookmarks) == 1
        bookmark = emitted_bookmarks[0]
        decoded = DailyMarketTechnicalOfficialDispositionRevenueBookmarkV1.from_json(
            bookmark.to_json()
        )
        assert decoded.bookmark_id == bookmark.bookmark_id
        assert decoded.stock_code == second_code
        assert decoded.source == "technical_official_disposition_revenue_research_bookmark"

        watchlist_output = tmp_path / "isolated-watchlist-output"

        def resolve_watchlist_path(name: str) -> Path:
            return watchlist_output / name

        watchlist_config = SimpleNamespace(
            output_root=watchlist_output,
            resolve_output_path=resolve_watchlist_path,
        )
        writer_service = WatchlistService(watchlist_config)
        assert writer_service.add_research_bookmark(bookmark).status == "added"
        watchlist_primary = watchlist_output / "watchlist" / "default.json"
        saved_watchlist_bytes = watchlist_primary.read_bytes()

        reader_service = WatchlistService(watchlist_config)
        loaded_bookmark = reader_service.get_research_bookmark(bookmark.bookmark_id)
        assert isinstance(loaded_bookmark, DailyMarketTechnicalOfficialDispositionRevenueBookmarkV1)
        assert loaded_bookmark.to_dict() == bookmark.to_dict()
        with pytest.raises(DailyMarketResearchBookmarkError) as generic_context:
            reader_service.get_research_bookmark_context(bookmark.bookmark_id)
        assert generic_context.value.code == "technical_official_revenue_bookmark_typed_reopen_required"
        assert watchlist_primary.read_bytes() == saved_watchlist_bytes

        assert view.current_recipe is not None and view._page_request is not None
        with pytest.raises(DailyMarketTechnicalOfficialDispositionRevenueBookmarkV1Error) as unissued:
            DailyMarketTechnicalOfficialDispositionRevenueBookmarkV1.from_issued_result_page(
                recipe=view.current_recipe,
                page_request=view._page_request,
                page=object(),
                stock_code=second_code,
            )
        assert unissued.value.code.endswith("page_invalid")
        assert view.active_worker is None
        assert not view._has_running_worker()

        main_tabs = QTabWidget()
        main_tabs.addTab(view, "月營收研究")
        other_tab = QWidget()
        main_tabs.addTab(other_tab, "其他")
        main_tabs.setCurrentWidget(other_tab)
        main_tabs.show()
        app.processEvents()
        selected_workspaces: list[str] = []
        main_host = SimpleNamespace(
            _shutdown_close_requested=False,
            technical_official_revenue_research_view=view,
            recommendation_view=SimpleNamespace(result_source_tabs=main_tabs),
            _select_main_workspace=selected_workspaces.append,
            statusBar=lambda: SimpleNamespace(showMessage=lambda *_args: None),
        )
        before = len(outcomes)
        MainWindow._open_technical_official_revenue_bookmark(
            cast(MainWindow, main_host), loaded_bookmark,
        )
        _wait_for_operation(
            app, outcomes, before,
            expected_kind="依收藏固定雙來源重新核驗",
            status_label=view.status_label,
        )
        assert selected_workspaces == ["recommendation"]
        assert main_tabs.currentWidget() is view
        assert exact_read_count == 2
        assert view.current_page is not None and view.current_page.page_index == 1
        assert view.current_query is not None
        assert view.current_recipe is not None
        assert view.current_recipe.to_json() == decoded.saved_recipe.to_json()
        assert view.current_query.ma_query.f17_query.to_json() == decoded.saved_recipe.f17_query_json
        assert view._selected_row is not None and view._selected_row.stock_code == second_code
        assert view.current_result is not original_result
        assert view.current_result is not None
        assert view.current_result.counts.declared_count == 258
        assert view.current_result.availability_status == "unknown"
        assert view.current_result.historical_pit_eligible is False

        restore_calls: list[object] = []
        original_restore = view.restore_bookmark

        def track_restore(value: object) -> bool:
            restore_calls.append(value)
            return original_restore(cast(DailyMarketTechnicalOfficialDispositionRevenueBookmarkV1, value))

        monkeypatch.setattr(view, "restore_bookmark", track_restore)
        main_tabs.setCurrentWidget(other_tab)
        main_host._shutdown_close_requested = True
        MainWindow._open_technical_official_revenue_bookmark(
            cast(MainWindow, main_host), loaded_bookmark,
        )
        assert restore_calls == []
        assert main_tabs.currentWidget() is other_tab
        assert selected_workspaces == ["recommendation"]
    finally:
        shutdown_deadline = time.monotonic() + 20.0
        while not view.begin_shutdown() and time.monotonic() < shutdown_deadline:
            app.processEvents()
            time.sleep(0.01)
        assert view.begin_shutdown()
        view.close()
        app.processEvents()
        assert not view._has_running_worker()


def _accept_comparison_dialog(app: QApplication) -> None:
    for widget in app.topLevelWidgets():
        if isinstance(widget, QDialog) and widget.windowTitle() == "月營收研究跨頁比較":
            widget.accept()
            return

