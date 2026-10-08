"""F17 全母體瀏覽介面以真實保存 bundle 驗證來源、跨頁與收藏重開。"""

from __future__ import annotations

import json
import os
import threading
import time
from typing import Any, cast

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app_module.daily_market_technical_official_disposition_bookmark_v1 import (
    DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_RESEARCH_BOOKMARK_SOURCE,
)
from app_module.daily_market_technical_official_disposition_query_reader_v1 import (
    DailyMarketTechnicalOfficialDispositionPageRequestV1,
)
from app_module.daily_market_technical_official_disposition_query_v1 import (
    DailyMarketTechnicalOfficialDispositionQueryV1,
)
from app_module.daily_market_technical_parent_v4_query import (
    DailyMarketTechnicalRuleStateFilterV4,
)
from app_module.daily_market_technical_universe_v4_query import (
    DailyMarketTechnicalUniverseV4Query,
)
from app_module.daily_market_technical_official_disposition_bundle_catalog_v1 import (
    DailyMarketTechnicalOfficialDispositionBundleCatalogEntryV1,
)
from ui_qt.views import daily_market_technical_official_disposition_view as view_module
from ui_qt.views.daily_market_technical_official_disposition_view import (
    DailyMarketTechnicalOfficialDispositionBookmarkV1,
    DailyMarketTechnicalOfficialDispositionComparisonV1,
    DailyMarketTechnicalOfficialDispositionStockSelectionV1,
    DailyMarketTechnicalOfficialDispositionView,
    format_technical_official_research_row_v1,
)
from test_daily_market_technical_official_disposition_bundle_v1 import bundle_fixture  # type: ignore[import-not-found]


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def app() -> QApplication:
    instance = cast(QApplication | None, QApplication.instance())
    if instance is None:
        instance = QApplication([])
    return instance


def _wait_for_idle(
    app: QApplication,
    view: DailyMarketTechnicalOfficialDispositionView,
    *,
    timeout_seconds: float = 180.0,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    while view.active_worker is not None:
        app.processEvents()
        if time.monotonic() >= deadline:
            raise AssertionError("F17 背景工作逾時")
        time.sleep(0.01)
    app.processEvents()


def _load_real_bundle(
    app: QApplication,
    fixture: Any,
) -> tuple[DailyMarketTechnicalOfficialDispositionView, DailyMarketTechnicalOfficialDispositionBundleCatalogEntryV1]:
    view = DailyMarketTechnicalOfficialDispositionView(fixture.bundle_root)
    view.refresh_catalog()
    _wait_for_idle(app, view)
    selectable = tuple(entry for entry in view._catalog_entries if entry.can_attempt_exact_read)
    assert len(selectable) == 1
    view.catalog_list.setCurrentRow(view._catalog_entries.index(selectable[0]))
    _wait_for_idle(app, view)
    assert view.current_result is not None
    assert view.current_page is not None
    assert view.current_page.counts.population.declared_count == 258
    assert view.current_result.counts.matching_count == 258
    return view, selectable[0]


def _bookmark_with_unrepresentable_query(
    view: DailyMarketTechnicalOfficialDispositionView,
    *,
    multiple_rule_states: bool,
    multiple_stock_codes: bool,
) -> DailyMarketTechnicalOfficialDispositionBookmarkV1:
    assert view.current_result is not None
    assert view.current_request is not None
    assert view._selected_row is not None
    base = view.current_result.query
    technical = base.technical_query
    rule_filters = technical.rule_state_filters
    if multiple_rule_states:
        rule_filters = (
            DailyMarketTechnicalRuleStateFilterV4.create(
                technical.method_rule_keys[0], ("match", "unknown")
            ),
        )
    rebuilt_technical = DailyMarketTechnicalUniverseV4Query.create(
        store_output_root=technical.store_output_root,
        generation_identity_sha256=technical.generation_identity_sha256,
        plan_identity_sha256=technical.plan_identity_sha256,
        plan_sha256=technical.plan_sha256,
        receipt_identity_sha256=technical.receipt_identity_sha256,
        receipt_sha256=technical.receipt_sha256,
        rule_state_filters=rule_filters,
        combine_mode=technical.combine_mode,
        stock_filter=technical.stock_filter,
        sort_key=technical.sort_key,
        descending=technical.descending,
        page_index=technical.page_index,
        page_size=technical.page_size,
    )
    if multiple_stock_codes:
        stock_codes = tuple(sorted({view._selected_row.stock_code, "1001"}))
        stock_mode = "explicit_codes"
    else:
        stock_codes = base.outer_stock_codes
        stock_mode = base.outer_stock_filter_mode
    query = DailyMarketTechnicalOfficialDispositionQueryV1.create(
        technical_query=rebuilt_technical,
        decision_cutoff=base.decision_cutoff,
        bundle_output_root=base.bundle_output_root,
        bundle_identity_sha256=base.bundle_identity_sha256,
        expected_manifest_sha256=base.expected_manifest_sha256,
        market_assignment_pin_identity_sha256=base.market_assignment_pin_identity_sha256,
        official_disposal_pin_identity_sha256=base.official_disposal_pin_identity_sha256,
        row_scope_filter=base.row_scope_filter,
        market_assignment_states=base.market_assignment_states,
        official_disposal_states=base.official_disposal_states,
        outer_stock_filter_mode=cast(Any, stock_mode),
        outer_stock_codes=stock_codes,
        sort_clauses=base.sort_clauses,
    )
    request = DailyMarketTechnicalOfficialDispositionPageRequestV1.create(
        query,
        page_index=view.current_request.page_index,
        page_size=view.current_request.page_size,
    )
    return DailyMarketTechnicalOfficialDispositionBookmarkV1.create(
        origin_page_request=request,
        selected_row=view._selected_row,
    )


def _controls_snapshot(view: DailyMarketTechnicalOfficialDispositionView) -> tuple[object, ...]:
    return (
        view.rule_filter_enabled.isChecked(),
        tuple((key, box.currentData()) for key, box in sorted(view.rule_state_boxes.items())),
        view.combine_box.currentData(),
        tuple((key, box.isChecked()) for key, box in sorted(view.scope_checks.items())),
        view.market_filter_enabled.isChecked(),
        tuple((key, box.isChecked()) for key, box in sorted(view.market_checks.items())),
        view.disposal_filter_enabled.isChecked(),
        tuple((key, box.isChecked()) for key, box in sorted(view.disposal_checks.items())),
        view.stock_filter_enabled.isChecked(),
        view.stock_code_input.text(),
        tuple((field.currentData(), direction.currentData()) for field, direction, _remove, _row in view.sort_rows),
        view.page_size_box.value(),
    )


def _wait_for_native_shutdown(
    app: QApplication,
    view: DailyMarketTechnicalOfficialDispositionView,
    *,
    timeout_seconds: float = 30.0,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    while not view.begin_shutdown():
        app.processEvents()
        if time.monotonic() >= deadline:
            raise AssertionError("F17 native QThread 未在期限內停止")
        time.sleep(0.01)
    app.processEvents()


def test_real_258_bundle_cross_page_detail_compare_bookmark_and_same_process_fresh_restore(
    app: QApplication,
    bundle_fixture: Any,
) -> None:
    view, _entry = _load_real_bundle(app, bundle_fixture)
    view.add_sort_clause()
    view.sort_rows[0][0].setCurrentIndex(view.sort_rows[0][0].findData("stock_code"))
    view.sort_rows[0][1].setCurrentIndex(view.sort_rows[0][1].findData("asc"))
    view.sort_rows[1][0].setCurrentIndex(view.sort_rows[1][0].findData("raw_row_count"))
    view.sort_rows[1][1].setCurrentIndex(view.sort_rows[1][1].findData("desc"))
    view.apply_filters()
    _wait_for_idle(app, view)
    assert view.current_result is not None
    assert tuple(
        (clause.field, clause.direction)
        for clause in view.current_result.query.sort_clauses
    ) == (("stock_code", "asc"), ("raw_row_count", "desc"))
    assert view.current_page is not None
    assert view.current_page.page_index == 0
    assert view.current_page.counts.population.included_count == 257
    assert view.current_page.counts.population.excluded_count == 1
    assert view.current_page.result_status in {"complete", "partial"}
    assert view.current_page.scope == "current_only"
    assert view.current_page.official_available_at is None
    assert view.current_page.historical_pit_eligible is False
    assert view.current_page.full_market_claim is False

    selected_events: list[object] = []
    prepared_events: list[object] = []
    comparisons: list[object] = []
    view.stockSelected.connect(selected_events.append)
    view.bookmarkPrepared.connect(prepared_events.append)
    view.comparisonReady.connect(comparisons.append)

    assert view.select_stock_code("1000")
    view.show_selected_detail()
    assert view.results_stack.currentIndex() == 1
    assert len(selected_events) == 1
    assert isinstance(selected_events[0], DailyMarketTechnicalOfficialDispositionStockSelectionV1)
    selected_row = view._selected_row
    assert selected_row is not None
    detail = format_technical_official_research_row_v1(selected_row)
    assert f"股票代碼：{selected_row.stock_code}" in detail
    assert "決策日期：" in detail
    assert "技術來源最新交易日：" in detail
    assert "市場對照：" in detail
    assert "處置狀態：" in detail
    assert "MA5／MA20 金叉：" in detail
    assert "K／D 金叉：" in detail
    assert "MACD 金叉：" in detail
    assert "量能比 20（含當日）：" in detail
    assert "量能比 5（含當日）：" in detail
    assert "來源不持續監測" in detail
    assert "官方 available_at 未知" in detail
    assert "snapshot_identity_sha256" not in detail
    assert "row_identity_sha256" not in detail
    assert not view.audit_toggle.isChecked()
    assert not view.audit_json_text.isVisible()
    assert "row_identity_sha256" in view.audit_json_text.toPlainText()
    view.resize(460, 700)
    view.show()
    app.processEvents()
    detail_scrollbar = view.detail_scroll.verticalScrollBar()
    assert detail_scrollbar.maximum() > 0
    detail_scrollbar.setValue(detail_scrollbar.maximum())
    app.processEvents()
    assert detail_scrollbar.value() == detail_scrollbar.maximum()
    first_request = view.current_request
    assert first_request is not None and first_request.page_index == 0
    view.return_to_results()
    assert view.results_stack.currentIndex() == 0
    assert view.current_request == first_request
    view.add_selected_to_comparison()
    assert tuple(item.stock_code for item in view.comparison_basket) == ("1000",)

    view.navigate_page(5)
    _wait_for_idle(app, view)
    assert view.current_page is not None
    assert view.current_page.page_index == 5
    assert view.current_page.rows[-2].stock_code == bundle_fixture.included_codes[-1]
    assert view.current_page.rows[-1].stock_code == bundle_fixture.excluded_code
    assert view.select_stock_code(bundle_fixture.included_codes[-1])
    view.add_selected_to_comparison()
    assert tuple(item.page_request.page_index for item in view.comparison_basket) == (0, 5)
    view.compare_basket()
    _wait_for_idle(app, view)
    assert len(comparisons) == 1
    comparison = comparisons[0]
    assert isinstance(comparison, DailyMarketTechnicalOfficialDispositionComparisonV1)
    assert tuple(item.stock_code for item in comparison.items) == ("1000", bundle_fixture.included_codes[-1])
    assert tuple(item.page_request.page_index for item in comparison.items) == (0, 5)

    view.prepare_bookmark()
    assert len(prepared_events) == 1
    bookmark = prepared_events[0]
    assert isinstance(bookmark, DailyMarketTechnicalOfficialDispositionBookmarkV1)
    assert bookmark.bookmark_id == bookmark.bookmark_identity_sha256
    assert bookmark.stock_code == bookmark.selected_stock_code
    assert bookmark.stock_name == f"{bookmark.selected_stock_code}／研究收藏"
    assert bookmark.source == DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_RESEARCH_BOOKMARK_SOURCE
    assert type(bookmark).__module__ == (
        "app_module.daily_market_technical_official_disposition_bookmark_v1"
    )
    assert tuple(
        item.page_request_json
        for item in bookmark.comparison_items
    ) == tuple(item.page_request.to_json() for item in comparison.items)
    bookmark_json = bookmark.to_json()
    assert DailyMarketTechnicalOfficialDispositionBookmarkV1.from_json(bookmark_json) == bookmark

    restored = DailyMarketTechnicalOfficialDispositionView(bundle_fixture.bundle_root)
    restored.restore_bookmark(bookmark_json)
    _wait_for_idle(app, restored)
    assert restored.current_result is not None
    assert restored.current_result.query.query_identity_sha256 == bookmark.query_identity_sha256
    assert len(restored.sort_rows) == 2
    assert tuple(
        (clause.field, clause.direction)
        for clause in cast(tuple[Any, ...], restored._read_conditions()["sort_clauses"])
    ) == (("stock_code", "asc"), ("raw_row_count", "desc"))
    assert restored.current_request is not None and restored.current_request.page_index == 5
    assert restored.current_page is not None and restored.current_page.page_index == 5
    assert restored._selected_row is not None
    assert restored._selected_row.stock_code == bundle_fixture.included_codes[-1]
    assert tuple(item.stock_code for item in restored.comparison_basket) == (
        "1000", bundle_fixture.included_codes[-1]
    )
    assert tuple(item.page_request.page_index for item in restored.comparison_basket) == (0, 5)
    assert restored.status_label.text().startswith("已從原保存來源")
    restored.close()
    view.close()


def test_same_table_position_selects_new_page_row_after_navigation(
    app: QApplication,
    bundle_fixture: Any,
) -> None:
    view, _entry = _load_real_bundle(app, bundle_fixture)
    try:
        view.resize(1000, 900)
        view.show()
        app.processEvents()
        assert view.current_page is not None
        technical_index = next(
            index
            for index, row in enumerate(view.current_page.rows)
            if row.technical_row is not None
        )
        technical_row = view.current_page.rows[technical_index]
        table_rule_text = view._technical_state_text(technical_row)
        assert all(
            label in table_rule_text
            for label in (
                "MA5／MA20 金叉",
                "K／D 金叉",
                "MACD 金叉",
                "量能比 20（含當日）",
                "量能比 5（含當日）",
            )
        )
        assert all(
            key not in table_rule_text
            for key in (
                "ma5_20_golden_cross",
                "kd_golden_cross",
                "macd_golden_cross",
                "volume_ratio_20_including_current",
                "volume_ratio_5_including_current",
            )
        )
        assert "公式" not in table_rule_text
        technical_cell = view.results_table.item(technical_index, 2)
        assert technical_cell is not None and technical_cell.text() == table_rule_text
        first_page_row = view.current_page.rows[0]
        first_item = view.results_table.item(0, 0)
        assert first_item is not None
        QTest.mouseClick(
            view.results_table.viewport(),
            Qt.MouseButton.LeftButton,
            pos=view.results_table.visualItemRect(first_item).center(),
        )
        app.processEvents()
        assert view._selected_row is first_page_row

        view.navigate_page(5)
        _wait_for_idle(app, view)
        assert view.current_page is not None
        assert view.current_page.page_index == 5
        target_row = view.current_page.rows[0]
        assert target_row.stock_code != first_page_row.stock_code
        assert view.results_table.currentRow() == -1
        excluded_row = view.current_page.rows[-1]
        assert excluded_row.technical_row is None
        assert view._technical_state_text(excluded_row) == "明示排除"

        # 跨頁後點同一個表格位置，必須綁到新頁列，不得沿用舊列或落成無選取。
        target_item = view.results_table.item(0, 0)
        assert target_item is not None
        QTest.mouseClick(
            view.results_table.viewport(),
            Qt.MouseButton.LeftButton,
            pos=view.results_table.visualItemRect(target_item).center(),
        )
        app.processEvents()
        assert view._selected_row is target_row

        # 公開選取器即使遇到同一個 currentCell，也要同步自己的已選列 DTO。
        assert view.select_stock_code(target_row.stock_code)
        assert view._selected_row is target_row
        view.add_selected_to_comparison()
        assert tuple(item.stock_code for item in view.comparison_basket) == (
            target_row.stock_code,
        )
    finally:
        view.close()


def test_missing_root_does_not_scan_and_empty_or_invalid_filters_are_rejected(
    app: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden_catalog(*_args: object, **_kwargs: object) -> Any:
        raise AssertionError("未指定 root 時不得掃描 catalog")

    monkeypatch.setattr(view_module, "DailyMarketTechnicalOfficialDispositionBundleCatalogV1", forbidden_catalog)
    view = DailyMarketTechnicalOfficialDispositionView(None)
    view.refresh_catalog()
    assert view.active_worker is None
    assert "未掃描磁碟" in view.status_label.text()

    view.rule_filter_enabled.setChecked(True)
    with pytest.raises(ValueError, match="rule_state_required"):
        view._read_conditions()
    view.rule_filter_enabled.setChecked(False)
    view.stock_filter_enabled.setChecked(True)
    with pytest.raises(ValueError, match="stock_code_required"):
        view._read_conditions()
    view.stock_filter_enabled.setChecked(False)
    view.scope_checks["excluded"].setChecked(False)
    view.scope_checks["included_pending"].setChecked(False)
    view.scope_checks["included_processed"].setChecked(False)
    with pytest.raises(ValueError, match="row_scope_empty"):
        view._read_conditions()
    view.scope_checks["included_processed"].setChecked(True)
    view.add_sort_clause()
    first_field = view.sort_rows[0][0]
    second_field = view.sort_rows[1][0]
    first_field.setCurrentIndex(first_field.findData("stock_code"))
    second_field.setCurrentIndex(second_field.findData("stock_code"))
    with pytest.raises(ValueError, match="sort_duplicate"):
        view._read_conditions()
    view.close()


def test_explicit_existing_source_folder_picker_and_busy_guard(
    app: QApplication,
    tmp_path: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    view = DailyMarketTechnicalOfficialDispositionView(None)
    assert not view.set_bundle_output_root("relative-folder")
    assert view.bundle_output_root is None

    view._busy_worker = cast(Any, object())
    assert not view.set_bundle_output_root(tmp_path)
    view._busy_worker = None
    assert view.bundle_output_root is None

    monkeypatch.setattr(
        view_module.QFileDialog,
        "getExistingDirectory",
        lambda *_args, **_kwargs: str(tmp_path),
    )
    view.choose_bundle_output_root()
    _wait_for_idle(app, view)
    assert view.bundle_output_root is not None
    assert str(view.bundle_output_root) == str(tmp_path)
    assert view.current_result is None
    assert view.current_page is None
    assert view.comparison_basket == ()
    view.close()


def test_narrow_window_and_detail_remain_scrollable_at_current_dpi(
    app: QApplication,
) -> None:
    view = DailyMarketTechnicalOfficialDispositionView(None)
    view.resize(460, 700)
    view.detail_text.setText("保存列完整內容與來源說明。\n" * 180)
    view.results_stack.setCurrentIndex(1)
    view.show()
    app.processEvents()

    assert view.width() == 460
    assert view.devicePixelRatioF() > 0
    assert view.page_scroll.viewport().width() < view.width()
    assert view.page_scroll.verticalScrollBar().maximum() > 0
    assert view.detail_scroll.verticalScrollBar().maximum() > 0
    view.close()


def test_zero_match_clears_rows_and_failed_source_switch_preserves_current_page(
    app: QApplication,
    bundle_fixture: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    view, entry = _load_real_bundle(app, bundle_fixture)
    previous_result = view.current_result
    previous_query = previous_result.query.query_identity_sha256 if previous_result else None

    view.stock_filter_enabled.setChecked(True)
    view.stock_code_input.setText("999999")
    view.apply_filters()
    _wait_for_idle(app, view)
    assert view.current_page is not None
    assert view.current_page.counts.declared_count == 258
    assert view.current_page.counts.matching_count == 0
    assert view.current_page.rows == ()
    assert view.results_table.rowCount() == 0
    assert "0 筆符合" in view.page_label.text()
    zero_result = view.current_result
    assert zero_result is not None and zero_result.query.query_identity_sha256 != previous_query

    view.stock_filter_enabled.setChecked(False)
    view.stock_code_input.clear()
    view.clear_filters()
    _wait_for_idle(app, view)
    assert view.current_page is not None and len(view.current_page.rows) == 50
    preserved_page = view.current_page
    preserved_result = view.current_result

    def fail_exact(*_args: object, **_kwargs: object) -> Any:
        raise ValueError("synthetic_exact_source_drift")

    monkeypatch.setattr(view_module, "open_daily_market_technical_official_disposition_bundle_session_v1", fail_exact)
    view.select_catalog_candidate(entry)
    _wait_for_idle(app, view)
    assert view.current_page is preserved_page
    assert view.current_result is preserved_result
    assert "synthetic_exact_source_drift" in view.status_label.text()
    view.close()


def test_cancelled_late_exact_open_keeps_current_query_and_page(
    app: QApplication,
    bundle_fixture: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    view, entry = _load_real_bundle(app, bundle_fixture)
    original_result = view.current_result
    original_page = view.current_page
    entered = threading.Event()
    release = threading.Event()
    original_open = cast(Any, view_module.open_daily_market_technical_official_disposition_bundle_session_v1)

    def blocked_open(*args: Any, **kwargs: Any) -> Any:
        entered.set()
        if not release.wait(30):
            raise AssertionError("測試閘門逾時")
        return original_open(*args, **kwargs)

    monkeypatch.setattr(view_module, "open_daily_market_technical_official_disposition_bundle_session_v1", blocked_open)
    view.select_catalog_candidate(entry)
    assert entered.wait(30)
    view.cancel_current_operation()
    release.set()
    _wait_for_idle(app, view)
    assert view.current_result is original_result
    assert view.current_page is original_page
    assert "已送出合作式取消" in view.status_label.text()
    assert "目前結果維持不變" in view.status_label.text()
    view.close()


def test_invalid_bookmark_restore_is_atomic_and_close_cancels_late_worker(
    app: QApplication,
    bundle_fixture: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    view, entry = _load_real_bundle(app, bundle_fixture)
    assert view.select_stock_code("1000")
    # 從目前頁選取建立 exact bookmark，確保失敗案例使用真來源列。
    captured: list[object] = []
    view.bookmarkPrepared.connect(captured.append)
    view.prepare_bookmark()
    bookmark = cast(DailyMarketTechnicalOfficialDispositionBookmarkV1, captured[-1])
    old_result = view.current_result
    old_page = view.current_page
    payload = json.loads(bookmark.to_json())
    payload["selected_stock_code"] = "9999"
    view.restore_bookmark(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
    assert view.active_worker is None
    assert view.current_result is old_result
    assert view.current_page is old_page
    assert "收藏無效" in view.status_label.text()

    assert view.select_stock_code("1000")
    view.add_selected_to_comparison()
    view.rule_filter_enabled.setChecked(True)
    view.rule_state_boxes[next(iter(view.rule_state_boxes))].setCurrentIndex(1)
    view.market_filter_enabled.setChecked(True)
    view.market_checks["assigned_twse"].setChecked(True)
    view.stock_filter_enabled.setChecked(True)
    view.stock_code_input.setText("1000")
    view.add_sort_clause()
    view.sort_rows[0][0].setCurrentIndex(view.sort_rows[0][0].findData("stock_code"))
    view.sort_rows[1][0].setCurrentIndex(view.sort_rows[1][0].findData("raw_row_count"))
    controls_before = _controls_snapshot(view)
    basket_before = view.comparison_basket

    for multiple_rule_states, multiple_stock_codes, error_code in (
        (True, False, "rule_filter_not_representable"),
        (False, True, "stock_filter_not_representable"),
    ):
        unsupported = _bookmark_with_unrepresentable_query(
            view,
            multiple_rule_states=multiple_rule_states,
            multiple_stock_codes=multiple_stock_codes,
        )
        view.restore_bookmark(unsupported)
        assert view.active_worker is None
        assert view.current_result is old_result
        assert view.current_page is old_page
        assert view.comparison_basket == basket_before
        assert _controls_snapshot(view) == controls_before
        assert error_code in view.status_label.text()

    entered = threading.Event()
    release = threading.Event()
    original_open = cast(Any, view_module.open_daily_market_technical_official_disposition_bundle_session_v1)

    def blocked_open(*args: Any, **kwargs: Any) -> Any:
        entered.set()
        if not release.wait(30):
            raise AssertionError("測試閘門逾時")
        return original_open(*args, **kwargs)

    monkeypatch.setattr(view_module, "open_daily_market_technical_official_disposition_bundle_session_v1", blocked_open)
    view.select_catalog_candidate(entry)
    assert entered.wait(30)
    worker = view.active_worker
    assert worker is not None and worker.isRunning()
    assert view.begin_shutdown() is False
    assert view.close() is False
    release.set()
    _wait_for_idle(app, view)
    _wait_for_native_shutdown(app, view)
    assert view.current_result is old_result
    assert view.current_page is old_page
    assert view.close() is True
