"""v4 技術母體視圖以真實 257 檔保存來源完成瀏覽與原來源 drill-down。"""

from __future__ import annotations

import time
import os
from dataclasses import replace
from functools import wraps
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from threading import Event, get_ident
from types import SimpleNamespace
from typing import Any, cast

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QTableView

from app_module.daily_market_technical_parent_v4_query import (
    DailyMarketTechnicalParentV4Row,
    DailyMarketTechnicalRuleStateFilterV4,
    RuleState,
)
from app_module.daily_market_technical_universe_v4_query import (
    DailyMarketTechnicalUniverseV4Query,
    DailyMarketTechnicalUniverseV4ReadSession,
)
from app_module.daily_market_technical_universe_v4_comparison import (
    DailyMarketTechnicalUniverseV4Comparison,
)
from app_module.daily_market_technical_universe_v4_bookmark import (
    DailyMarketTechnicalUniverseV4Bookmark,
    read_daily_market_technical_universe_v4_bookmark,
)
from app_module.daily_market_technical_universe_v4_producer import (
    DailyMarketTechnicalUniverseV4ProductionRequest,
    DailyMarketTechnicalUniverseV4ProductionResult,
)
from app_module.daily_market_technical_universe_v4_store import (
    DAILY_MARKET_TECHNICAL_UNIVERSE_V4_STORE_DIRECTORY,
    DailyMarketTechnicalUniverseV4Cohort,
    DailyMarketTechnicalUniverseV4Counts,
)
from app_module.daily_market_technical_universe_v4_stock import (
    DailyMarketTechnicalUniverseV4Stock,
)
from tests.test_daily_market_technical_universe_v4_query import synthetic_full_store
from tests.test_daily_market_technical_universe_v4_bookmark import pinned_bookmark
from ui_qt.widgets.daily_market_technical_v4_production_setup import (
    DailyMarketTechnicalV4DeferredProductionSetup,
    ProductionSetupSummary,
)
import ui_qt.views.daily_market_technical_universe_v4_view as universe_view_module
from ui_qt.views.daily_market_technical_universe_v4_view import (
    DailyMarketTechnicalUniverseV4View,
)


@pytest.fixture(scope="module")
def app() -> QApplication:
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication([])
    return cast(QApplication, instance)


def _wait(app: QApplication, predicate: Any, *, timeout_seconds: float = 120.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while not predicate():
        app.processEvents()
        if time.monotonic() >= deadline:
            raise AssertionError("v4 view background operation timed out")
        time.sleep(0.01)
    app.processEvents()


def _entry_index(view: DailyMarketTechnicalUniverseV4View, status: str) -> int:
    for index in range(view.sources.count()):
        entry = view.sources.itemData(index)
        if getattr(entry, "source_status", None) == status:
            return index
    return -1


def _native_file_path(path: Path) -> str:
    """以 Windows extended-length 路徑讀寫測試中的長路徑保存檔。"""
    absolute = os.path.abspath(os.fspath(path))
    if os.name != "nt" or absolute.startswith("\\\\?\\"):
        return absolute
    if absolute.startswith("\\\\"):
        return "\\\\?\\UNC\\" + absolute[2:]
    return "\\\\?\\" + absolute


def test_real_257_full_store_catalog_query_filters_pages_and_exact_stock_drilldown(
    app: QApplication,
    synthetic_full_store: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = synthetic_full_store
    calls = {"strict_open": 0, "selection": 0, "selection_page": 0, "selected_stock": 0}
    original_open = universe_view_module.open_daily_market_technical_universe_v4_read_session
    original_select = DailyMarketTechnicalUniverseV4ReadSession.select_stock_codes
    original_page = DailyMarketTechnicalUniverseV4ReadSession.read_selection_page
    original_stock = DailyMarketTechnicalUniverseV4ReadSession.read_selection_stock_snapshot

    @wraps(original_open)
    def count_strict_open(**kwargs: Any) -> Any:
        calls["strict_open"] += 1
        return original_open(**kwargs)

    @wraps(original_select)
    def count_selection(
        session: DailyMarketTechnicalUniverseV4ReadSession,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        calls["selection"] += 1
        return original_select(session, *args, **kwargs)

    @wraps(original_page)
    def count_selection_page(
        session: DailyMarketTechnicalUniverseV4ReadSession,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        calls["selection_page"] += 1
        return original_page(session, *args, **kwargs)

    @wraps(original_stock)
    def count_selected_stock(
        session: DailyMarketTechnicalUniverseV4ReadSession,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        calls["selected_stock"] += 1
        return original_stock(session, *args, **kwargs)

    monkeypatch.setattr(
        universe_view_module,
        "open_daily_market_technical_universe_v4_read_session",
        count_strict_open,
    )
    monkeypatch.setattr(DailyMarketTechnicalUniverseV4ReadSession, "select_stock_codes", count_selection)
    monkeypatch.setattr(DailyMarketTechnicalUniverseV4ReadSession, "read_selection_page", count_selection_page)
    monkeypatch.setattr(
        DailyMarketTechnicalUniverseV4ReadSession,
        "read_selection_stock_snapshot",
        count_selected_stock,
    )

    view = DailyMarketTechnicalUniverseV4View(fixture["store_output_root"])
    view.show()
    selected_events: list[object] = []
    view.stockSelected.connect(selected_events.append)

    # 產製測試資料會建立兩份 parent 保存（256+1）與完整 full-N 收據，
    # 並在測試前移除來源資料庫；來源清冊與查詢必須只重開固定保存版本。
    view.refresh_sources()
    _wait(app, lambda: view._worker is None)
    complete_index = _entry_index(view, "complete")
    assert complete_index >= 0, view.status.text()
    view.sources.setCurrentIndex(complete_index)
    entry = view.selected_source
    assert entry is not None and entry.is_selectable
    assert "metadata 尚未完成 strict 核驗" in view.source_pins.text()
    assert entry.population_state == "included"

    view.load_selected()
    _wait(
        app,
        lambda: view._worker is None
        and (view.current_page is not None or "失敗：" in view.status.text()),
    )
    assert view.current_page is not None, view.status.text()
    assert calls["strict_open"] == 1
    assert calls["selection"] == 1
    assert calls["selection_page"] == 1
    page = view.current_page
    query = view.current_query
    assert page is not None and query is not None
    assert page.is_complete is True
    assert query.receipt_status == "complete"
    assert page.counts.declared_count == 258
    assert page.counts.included_count == 257
    assert page.counts.excluded_count == 1
    assert page.counts.processed_count == 257
    assert page.counts.pending_count == 0
    assert page.counts.missing_data_count == 1
    assert page.counts.missing_data_pending_count == 0
    assert page.unknown_rule_count == 2
    assert page.matching_count == 257
    assert len(page.rows) == 50
    assert isinstance(view.table, QTableView)
    assert view.table.model() is view.results_model
    assert view.table.isSortingEnabled() is False
    assert view.results_model.rowCount() == len(page.rows)
    assert view.results_model.columnCount() == 9
    first_row = page.rows[0]
    assert tuple(rule.key for rule in first_row.rules) == (
        "ma5_20_golden_cross",
        "kd_golden_cross",
        "macd_golden_cross",
        "volume_ratio_20_including_current",
        "volume_ratio_5_including_current",
    )
    first_index = view.results_model.index(0, 0)
    first_label = first_row.stock_code
    if first_row.raw_row_count == 0:
        first_label += "（缺資料）"
    assert view.results_model.data(first_index, Qt.ItemDataRole.DisplayRole) == first_label
    assert view.results_model.data(first_index, Qt.ItemDataRole.UserRole) is first_row
    full_tooltip = view.results_model.data(first_index, Qt.ItemDataRole.ToolTipRole)
    assert isinstance(full_tooltip, str)
    assert f"來源 identity：{first_row.source_identity}" in full_tooltip
    assert "資料可得時間未知；只供當下重述研究；不授歷史 PIT／可交易資格。" in full_tooltip
    assert all(
        view.table.indexWidget(view.results_model.index(row_index, column)) is None
        for row_index in range(view.results_model.rowCount())
        for column in range(view.results_model.columnCount())
    )
    assert view._select_stock_code(first_row.stock_code) is True
    assert view._selected_row() is first_row
    view._render_rows(page.rows[1:], selected_code=first_row.stock_code)
    assert view._selected_row() is None
    view._render_rows(page.rows, selected_code=first_row.stock_code)
    assert view._selected_row() is first_row
    assert "此固定版本於 read-session 建立時通過 strict 核驗" in view.verified_pins.text()
    assert "不宣稱來源檔在核驗後未變" in view.verified_pins.text()
    assert query.generation_identity_sha256 in view.verified_pins.text()
    assert query.plan_sha256 in view.verified_pins.text()
    assert query.receipt_sha256 in view.verified_pins.text()
    assert query.source_clock_identity_sha256 in view.verified_pins.text()
    assert query.method_contracts_sha256 in view.verified_pins.text()
    assert "資料可得時間未知" in view.disclaimer.text()
    assert "只供當下重述研究" in view.verified_pins.text()
    assert "不授歷史 PIT／可交易資格" in view.verified_pins.text()
    assert "全市場宣稱：否" in view.summary.text()

    # 每條規則可選任一非空三態組合；query 的 state tuple 以公開 canonical 順序往返。
    first_rule_key = query.method_rule_keys[0]
    first_rule_combo = view._rule_filters[first_rule_key]
    state_sets: tuple[tuple[RuleState, ...], ...] = (
        (),
        ("match",),
        ("no_match",),
        ("unknown",),
        ("match", "no_match"),
        ("match", "unknown"),
        ("no_match", "unknown"),
        ("match", "no_match", "unknown"),
    )
    for states in state_sets:
        filter_id = (
            universe_view_module._RULE_STATE_FILTER_STATES_TO_ID.get(states)
            if states
            else universe_view_module._NO_STATE_FILTER
        )
        assert filter_id is not None
        option_index = first_rule_combo.findData(filter_id)
        assert option_index >= 0
        first_rule_combo.setCurrentIndex(option_index)
        selected_filters = view._selected_rule_state_filters()
        expected_filters = (
            (DailyMarketTechnicalRuleStateFilterV4.create(first_rule_key, states),)
            if states
            else ()
        )
        assert selected_filters == expected_filters

    multi_state_filter = DailyMarketTechnicalRuleStateFilterV4.create(
        first_rule_key, ("unknown", "match")
    )
    multi_state_query = DailyMarketTechnicalUniverseV4Query.create(
        store_output_root=query.store_output_root,
        generation_identity_sha256=query.generation_identity_sha256,
        plan_identity_sha256=query.plan_identity_sha256,
        plan_sha256=query.plan_sha256,
        receipt_identity_sha256=query.receipt_identity_sha256,
        receipt_sha256=query.receipt_sha256,
        rule_state_filters=(multi_state_filter,),
        combine_mode="OR",
        stock_filter=("S0001", "S0002"),
        sort_key=query.sort_key,
        descending=True,
        page_index=1,
        page_size=25,
    )
    reopened_multi_state_query = DailyMarketTechnicalUniverseV4Query.from_json(
        multi_state_query.to_json()
    )
    assert reopened_multi_state_query == multi_state_query
    view._set_filter_controls(reopened_multi_state_query)
    assert first_rule_combo.currentData() == "match|unknown"
    assert view._selected_rule_state_filters() == reopened_multi_state_query.rule_state_filters
    assert view.mode.currentData() == "OR"
    assert view.stock_filter.text() == "S0001, S0002"
    assert view.sort.currentData() == query.sort_key
    assert view.descending.currentData() is True
    assert view.page_size.currentData() == 25
    view._set_filter_controls(query)

    retained_page = view.current_page
    retained_query = view.current_query
    view.stock_filter.setText("S0001,,S0002")
    view.apply_query()
    assert "空欄位" in view.status.text()
    assert view.current_page is retained_page
    assert view.current_query is retained_query
    assert view._worker is None
    view.stock_filter.clear()

    read_session = view._read_session
    assert read_session is not None
    assert universe_view_module._query_matches_entry(query, read_session, entry)
    altered_receipt_sha256 = "0" * 64
    if altered_receipt_sha256 == entry.receipt_bytes_sha256:
        altered_receipt_sha256 = "1" * 64
    altered_entry = replace(entry, receipt_bytes_sha256=altered_receipt_sha256)
    assert not universe_view_module._query_matches_entry(query, read_session, altered_entry)

    # 透過介面套用 OR 狀態篩選及全域排序。測試資料當日量能有一檔量能比 20
    # 符合；一般股票的量能比 5 不符合；零資料股票仍保留未知。
    view._rule_filters["volume_ratio_20_including_current"].setCurrentIndex(
        view._rule_filters["volume_ratio_20_including_current"].findData("match")
    )
    view._rule_filters["volume_ratio_5_including_current"].setCurrentIndex(
        view._rule_filters["volume_ratio_5_including_current"].findData("no_match")
    )
    view.mode.setCurrentIndex(view.mode.findData("OR"))
    view.sort.setCurrentIndex(view.sort.findData("volume_ratio_20_including_current.ratio"))
    view.descending.setCurrentIndex(view.descending.findData(False))
    view.apply_query()
    # 第二個立即套用的同條件查詢改成降冪；第一個晚到結果不得覆蓋後者。
    view.descending.setCurrentIndex(view.descending.findData(True))
    view.apply_query()
    _wait(app, lambda: view._worker is None and view.current_page is not None)
    assert view.current_query is not None and view.current_query.combine_mode == "OR"
    assert view.current_page is not None
    assert view.current_page.matching_count == 255
    assert view.current_page.page_count == 6
    assert len(view.current_page.rows) == 50
    assert view.current_page.rows[0].stock_code == "S0001"
    assert view.current_query.descending is True
    final_page = view.current_page
    final_query = view.current_query
    selection_calls_before_page_turn = calls["selection"]
    strict_opens_before_page_turn = calls["strict_open"]

    view.next_button.click()
    _wait(app, lambda: view._worker is None and view.current_query is not None
          and view.current_query.page_index == 1)
    assert view.current_page is not None
    assert view.current_page.counts.processed_count == 257
    assert view.current_page.matching_count == 255
    assert calls["strict_open"] == strict_opens_before_page_turn
    assert calls["selection"] == selection_calls_before_page_turn
    second_page = view.current_page
    final_page = second_page
    final_query = view.current_query

    # 個股讀取必須依原查詢精確讀回，並一起送出查詢、列與嚴格核驗快照，
    # 不得改查最新來源。
    view.table.selectRow(0)
    selected_row = view._selected_row()
    assert isinstance(selected_row, DailyMarketTechnicalParentV4Row)
    view.open_selected_stock()
    _wait(app, lambda: view._worker is None and bool(selected_events))
    assert len(selected_events) == 1
    emitted = selected_events[0]
    assert isinstance(emitted, tuple) and len(emitted) == 3
    emitted_query, emitted_row, emitted_stock = emitted
    assert isinstance(emitted_query, DailyMarketTechnicalUniverseV4Query)
    assert isinstance(emitted_row, DailyMarketTechnicalParentV4Row)
    assert isinstance(emitted_stock, DailyMarketTechnicalUniverseV4Stock)
    assert emitted_query == final_query
    assert emitted_row == selected_row
    assert emitted_stock.origin_query == final_query
    assert emitted_stock.snapshot.stock_code == selected_row.stock_code
    assert emitted_stock.snapshot.snapshot_identity_sha256 == selected_row.snapshot_identity_sha256
    assert calls["strict_open"] == strict_opens_before_page_turn
    assert calls["selection"] == selection_calls_before_page_turn
    assert calls["selected_stock"] == 1

    # 翻到第三頁後立即取消；第二頁的已核驗內容不得被晚到結果取代。
    view.next_button.click()
    view.cancel()
    _wait(app, lambda: view._worker is None)
    assert view.current_page is second_page

    # 明示不存在的股票代碼會得到真實零符合結果，必須清空舊頁並保留已核母體計數。
    view.stock_filter.setText("ZZZZ")
    view.apply_query()
    _wait(
        app,
        lambda: view._worker is None
        and view.current_query is not None
        and view.current_query.stock_filter == ("ZZZZ",),
    )
    assert view.current_page is None
    assert view.results_model.rowCount() == 0
    assert view.next_button.isEnabled() is False
    assert view.open_button.isEnabled() is False
    assert view.add_comparison_button.isEnabled() is False
    assert view.bookmark_button.isEnabled() is False
    assert "符合目前篩選 0 筆" in view.summary.text()
    assert "已核驗母體計數：宣告 258、納入 257、排除 1" in view.summary.text()
    assert "全市場宣稱：否" in view.summary.text()

    view.stock_filter.clear()
    view.apply_query()
    _wait(app, lambda: view._worker is None and view.current_page is not None)
    restored_page = view.current_page
    restored_session = view._read_session
    restored_selection = view._selection
    assert restored_page is not None
    assert restored_page.matching_count == 255
    assert calls["strict_open"] == strict_opens_before_page_turn

    # explicit reload 必須重新核驗整個保存版本；篡改非目前頁面依賴的 receipt
    # 後應拒絕發布，原頁面與 session/selection 保留。
    plan = fixture["plan"]
    complete = fixture["complete"]
    receipt_path = (
        Path(fixture["store_output_root"])
        / DAILY_MARKET_TECHNICAL_UNIVERSE_V4_STORE_DIRECTORY
        / "generations"
        / plan.generation_identity_sha256
        / "receipts"
        / f"{complete.identity_sha256}.json"
    )
    native_receipt_path = _native_file_path(receipt_path)
    with open(native_receipt_path, "rb") as receipt_file:
        receipt_bytes = receipt_file.read()
    try:
        with open(native_receipt_path, "wb") as receipt_file:
            receipt_file.write(receipt_bytes + b" ")
        view.load_selected()
        _wait(app, lambda: view._worker is None)
        assert "目前已核驗結果保留" in view.status.text()
        assert view.current_page is restored_page
        assert view._read_session is restored_session
        assert view._selection is restored_selection
        assert view.current_query is not None and view.current_query.stock_filter == ()
        assert calls["strict_open"] == strict_opens_before_page_turn + 1
    finally:
        with open(native_receipt_path, "wb") as receipt_file:
            receipt_file.write(receipt_bytes)

    view.close()
    assert view.begin_shutdown()


def test_diagnostic_catalog_rows_cannot_be_loaded_or_resumed(app: QApplication, tmp_path: Any) -> None:
    view = DailyMarketTechnicalUniverseV4View(tmp_path)
    view.show()
    view.sources.addItem("診斷列", None)
    view.sources.setCurrentIndex(0)
    view.load_selected()
    assert view.current_query is None
    assert "請選擇一筆可讀取" in view.status.text()
    view.resume_selected()
    assert "續跑前請選擇" in view.status.text()
    view.close()
    assert view.begin_shutdown()


def test_real_pinned_comparison_basket_cross_page_and_origin_restore(
    app: QApplication,
    synthetic_full_store: dict[str, Any],
) -> None:
    fixture = synthetic_full_store
    view = DailyMarketTechnicalUniverseV4View(fixture["store_output_root"])
    view.show()
    comparisons: list[object] = []
    view.comparisonReady.connect(comparisons.append)

    view.refresh_sources()
    _wait(app, lambda: view._worker is None)
    complete_index = _entry_index(view, "complete")
    assert complete_index >= 0
    view.sources.setCurrentIndex(complete_index)
    view.load_selected()
    _wait(app, lambda: view._worker is None and view.current_page is not None)

    first_query = view.current_query
    assert first_query is not None
    view.table.selectRow(0)
    first_row = view._selected_row()
    assert isinstance(first_row, DailyMarketTechnicalParentV4Row)
    view.add_selected_to_comparison()
    assert "比較籃 1／256" in view.comparison_basket_label.text()
    assert view.compare_button.isEnabled() is False
    view.add_selected_to_comparison()
    assert len(view._comparison_basket) == 1
    assert "已在比較籃中" in view.status.text()

    view.next_button.click()
    _wait(app, lambda: view._worker is None and view.current_query is not None
          and view.current_query.page_index == 1)
    second_query = view.current_query
    assert second_query is not None
    view.table.selectRow(0)
    second_row = view._selected_row()
    assert isinstance(second_row, DailyMarketTechnicalParentV4Row)
    view.add_selected_to_comparison()
    assert "比較籃 2／256" in view.comparison_basket_label.text()
    assert view.compare_button.isEnabled() is True
    assert first_query != second_query

    table_before_compare = view.current_page
    view.compare_basket()
    _wait(app, lambda: view._worker is None and bool(comparisons))
    assert len(comparisons) == 1
    comparison = comparisons[0]
    assert isinstance(comparison, DailyMarketTechnicalUniverseV4Comparison)
    assert len(comparison.columns) == 2
    assert tuple(column.row.stock_code for column in comparison.columns) == (
        first_row.stock_code,
        second_row.stock_code,
    )
    assert tuple(column.origin_query for column in comparison.columns) == (
        first_query,
        second_query,
    )
    assert view.current_page is table_before_compare

    # 比較欄返回時，視圖須依欄位保存的 query pins 重開原頁並選回原股票。
    returned_column = comparison.columns[0]
    view.restore_origin(returned_column.origin_query, returned_column.row.stock_code)
    _wait(app, lambda: view._worker is None and view.current_query == first_query)
    restored_row = view._selected_row()
    assert restored_row is not None
    assert restored_row.stock_code == returned_column.row.stock_code
    assert view.current_page is not None
    assert view.current_page.query == returned_column.origin_query

    # 立即取消比較，原查詢頁面與選取內容仍保留，也不再發出比較結果。
    table_before_cancel = view.current_page
    selected_before_cancel = view._selected_row()
    view.compare_basket()
    view.cancel()
    _wait(app, lambda: view._worker is None)
    assert view.current_page is table_before_cancel
    assert view._selected_row() == selected_before_cancel
    assert len(comparisons) == 1

    view.clear_comparison_basket()
    assert view._comparison_basket == []
    assert "比較籃 0／256" in view.comparison_basket_label.text()
    assert view.clear_comparison_button.isEnabled() is False
    assert view.compare_button.isEnabled() is False

    view.close()
    assert view.begin_shutdown()


def test_source_clock_display_cache_is_cleared_when_source_pins_change(
    app: QApplication,
    tmp_path: Any,
) -> None:
    view = DailyMarketTechnicalUniverseV4View(tmp_path)
    counts = DailyMarketTechnicalUniverseV4Counts(
        declared_count=0,
        included_count=0,
        excluded_count=0,
        processed_count=0,
        pending_count=0,
        missing_data_count=0,
        missing_data_pending_count=0,
    )
    rule_keys = (
        "ma5_20_golden_cross",
        "kd_golden_cross",
        "macd_golden_cross",
        "volume_ratio_20_including_current",
        "volume_ratio_5_including_current",
    )

    def synthetic_query(generation: str, clock: str, *, page_index: int = 0) -> Any:
        return SimpleNamespace(
            store_output_root=str(tmp_path),
            generation_identity_sha256=generation * 64,
            plan_identity_sha256="b" * 64,
            plan_sha256="c" * 64,
            receipt_identity_sha256="d" * 64,
            receipt_sha256="e" * 64,
            receipt_status="complete",
            cohort_identity_sha256="f" * 64,
            source_clock_identity_sha256=clock * 64,
            method_contracts_sha256="a" * 64,
            universe_id="synthetic-clock-cache",
            population_version="fixture-v1",
            decision_date=date(2026, 10, 6),
            declared_count=0,
            included_count=0,
            excluded_count=0,
            segment_count=0,
            counts=counts,
            method_rule_keys=rule_keys,
            rule_state_filters=(),
            combine_mode="AND",
            stock_filter=(),
            sort_key="stock_code",
            descending=False,
            page_index=page_index,
            page_size=50,
        )

    def synthetic_page(query: Any) -> Any:
        return SimpleNamespace(
            query=query,
            rows=(),
            counts=counts,
            is_complete=True,
            matching_count=0,
            page_count=1,
            processed_segment_count=0,
            unknown_rule_count=0,
            exclusion_reasons=(),
            coverage_scope="declared_full_universe_v4",
            aggregation_scope="global_full_universe",
        )

    first_query = synthetic_query("1", "1")
    view._show_page(synthetic_page(first_query), source_clock={"payload_marker": "clock-one"})
    assert "clock-one" in view.verified_pins.text()

    same_source_next_page = synthetic_query("1", "1", page_index=1)
    view._show_page(synthetic_page(same_source_next_page))
    assert "clock-one" in view.verified_pins.text()

    second_source = synthetic_query("2", "2")
    view._show_page(synthetic_page(second_source))
    assert view._source_clock is None
    assert "clock-one" not in view.verified_pins.text()
    assert second_source.source_clock_identity_sha256 in view.verified_pins.text()

    view.close()
    assert view.begin_shutdown()


def test_deferred_setup_runs_in_worker_and_cancel_never_calls_producer(
    app: QApplication,
    tmp_path: Any,
    monkeypatch: Any,
) -> None:
    configured_root = Path(tmp_path) / "configured-output"
    store_root = configured_root / "research_snapshots" / "technical_universe"
    source_database = Path(tmp_path) / "synthetic-source.sqlite"
    decision_cutoff = datetime(
        2026,
        10,
        6,
        16,
        0,
        tzinfo=timezone(timedelta(hours=8)),
    )
    cohort = DailyMarketTechnicalUniverseV4Cohort.create(
        universe_id="synthetic-deferred-worker",
        population_version="fixture-v1",
        decision_date=date(2026, 10, 6),
        raw_stock_codes=("S0001",),
    )
    summary = ProductionSetupSummary(
        mode="new",
        cohort=cohort,
        source_database=source_database,
        configured_output_root=configured_root,
        store_output_root=store_root,
        decision_cutoff=decision_cutoff,
    )
    setup = DailyMarketTechnicalV4DeferredProductionSetup(
        mode="new",
        source_database=source_database,
        configured_output_root=configured_root,
        store_output_root=store_root,
        summary=summary,
        cohort=cohort,
        decision_cutoff=decision_cutoff,
    )
    request = DailyMarketTechnicalUniverseV4ProductionRequest(
        source_database=source_database,
        cohort=cohort,
        decision_cutoff=decision_cutoff,
        store_output_root=store_root,
    )
    setup_entered = Event()
    release_setup = Event()
    setup_thread_ids: list[int] = []
    producer_calls: list[object] = []

    def delayed_prepare(
        self: DailyMarketTechnicalV4DeferredProductionSetup,
        *,
        cancel_callback: Any = None,
    ) -> DailyMarketTechnicalUniverseV4ProductionRequest:
        del self, cancel_callback
        setup_thread_ids.append(get_ident())
        setup_entered.set()
        if not release_setup.wait(timeout=10):
            raise AssertionError("deferred setup test was not released")
        return request

    def forbidden_producer(_request: DailyMarketTechnicalUniverseV4ProductionRequest) -> Any:
        producer_calls.append(_request)
        raise AssertionError("cancelled deferred setup must not call producer")

    monkeypatch.setattr(
        DailyMarketTechnicalV4DeferredProductionSetup,
        "prepare_request",
        delayed_prepare,
    )
    monkeypatch.setattr(
        universe_view_module,
        "produce_daily_market_technical_universe_v4",
        forbidden_producer,
    )
    view = DailyMarketTechnicalUniverseV4View(
        store_root,
        production_request_factory=lambda _entry: setup,
    )
    view.produce_new()
    _wait(app, setup_entered.is_set)
    assert setup_thread_ids
    assert setup_thread_ids[0] != get_ident()

    view.cancel()
    release_setup.set()
    _wait(app, lambda: view._worker is None)
    assert producer_calls == []

    view.close()
    assert view.begin_shutdown()


def test_legacy_request_factory_remains_supported(
    app: QApplication,
    tmp_path: Any,
    monkeypatch: Any,
) -> None:
    configured_root = Path(tmp_path) / "legacy-configured-output"
    store_root = configured_root / "research_snapshots" / "technical_universe"
    source_database = Path(tmp_path) / "legacy-source.sqlite"
    decision_cutoff = datetime(
        2026,
        10,
        6,
        16,
        0,
        tzinfo=timezone(timedelta(hours=8)),
    )
    cohort = DailyMarketTechnicalUniverseV4Cohort.create(
        universe_id="synthetic-legacy-factory",
        population_version="fixture-v1",
        decision_date=date(2026, 10, 6),
        raw_stock_codes=("S0001",),
    )
    request = DailyMarketTechnicalUniverseV4ProductionRequest(
        source_database=source_database,
        cohort=cohort,
        decision_cutoff=decision_cutoff,
        store_output_root=store_root,
    )
    result = DailyMarketTechnicalUniverseV4ProductionResult(
        status="cancelled",
        step="synthetic-cancel-before-write",
        plan=None,
        receipt=None,
        error_code="synthetic_cancelled",
        cause_code=None,
        resumed=False,
        calculation_identity_sha256=None,
        completed_segment_indices=(),
        missing_data_stock_codes=(),
    )
    producer_requests: list[DailyMarketTechnicalUniverseV4ProductionRequest] = []
    finished: list[object] = []

    def synthetic_producer(
        value: DailyMarketTechnicalUniverseV4ProductionRequest,
    ) -> DailyMarketTechnicalUniverseV4ProductionResult:
        producer_requests.append(value)
        return result

    monkeypatch.setattr(
        universe_view_module,
        "produce_daily_market_technical_universe_v4",
        synthetic_producer,
    )
    view = DailyMarketTechnicalUniverseV4View(
        store_root,
        production_request_factory=lambda _entry: request,
    )
    view.productionFinished.connect(finished.append)
    view.produce_new()
    _wait(app, lambda: view._worker is None and bool(finished))
    assert producer_requests
    assert producer_requests[0].store_output_root == store_root
    assert finished == [result]

    view.close()
    assert view.begin_shutdown()


def test_bookmark_button_prepares_and_restores_real_small_saved_state(
    app: QApplication,
    pinned_bookmark: dict[str, Any],
) -> None:
    saved = pinned_bookmark["bookmark"]
    assert isinstance(saved, DailyMarketTechnicalUniverseV4Bookmark)
    state = read_daily_market_technical_universe_v4_bookmark(saved)
    view = DailyMarketTechnicalUniverseV4View(saved.origin_query.store_output_root)
    view.table.setFixedHeight(70)
    view.show()
    prepared: list[object] = []
    view.bookmarkPrepared.connect(prepared.append)

    view.restore_bookmark_state(state)
    _wait(app, lambda: view._worker is None and view.current_query == saved.origin_query)
    assert view.current_page is state.origin_page
    selected_row = view._selected_row()
    assert selected_row is not None
    assert selected_row.stock_code == saved.selected_stock_code
    assert len(view._comparison_basket) == len(saved.comparison_selections) == 2
    assert view.table.verticalScrollBar().value() == min(
        saved.scroll_position,
        view.table.verticalScrollBar().maximum(),
    )

    selected = view._selected_row()
    assert selected is not None
    view.table.verticalScrollBar().setValue(
        min(12, view.table.verticalScrollBar().maximum())
    )
    expected_scroll = view.table.verticalScrollBar().value()
    view.prepare_bookmark()
    _wait(app, lambda: view._worker is None and bool(prepared))
    assert len(prepared) == 1
    prepared_bookmark = prepared[0]
    assert isinstance(prepared_bookmark, DailyMarketTechnicalUniverseV4Bookmark)
    assert prepared_bookmark.origin_query == saved.origin_query
    assert prepared_bookmark.selected_stock_code == selected.stock_code
    assert prepared_bookmark.scroll_position == expected_scroll
    assert prepared_bookmark.comparison_selections == saved.comparison_selections
    assert "尚未寫入觀察清單" in view.status.text()

    # 單筆比較項目不可在收藏時被靜默省略。
    view.clear_comparison_basket()
    assert view._select_stock_code(saved.selected_stock_code)
    view.add_selected_to_comparison()
    view.prepare_bookmark()
    assert len(view._comparison_basket) == 1
    assert "比較籃只有 1 檔" in view.status.text()
    assert len(prepared) == 1

    # 空比較籃合法，且收藏不會寫入或呼叫觀察清單服務。
    view.clear_comparison_basket()
    view.prepare_bookmark()
    _wait(app, lambda: view._worker is None and len(prepared) == 2)
    empty_basket_bookmark = prepared[1]
    assert isinstance(empty_basket_bookmark, DailyMarketTechnicalUniverseV4Bookmark)
    assert empty_basket_bookmark.comparison_selections == ()

    page_before_invalid_restore = view.current_page
    view.restore_bookmark_state(cast(Any, object()))
    _wait(app, lambda: view._worker is None)
    assert view.current_page is page_before_invalid_restore

    view.close()
    assert view.begin_shutdown()


def test_stock_filter_parser_covers_full_public_limit_without_silent_dropping() -> None:
    codes = tuple(f"S{index:015d}" for index in range(100_000))
    text = ", ".join(codes)
    assert len(text) == universe_view_module._MAX_STOCK_FILTER_TEXT_LENGTH
    assert DailyMarketTechnicalUniverseV4View._parse_stock_filter(text) == codes

    for invalid in (
        "2382,,9999",
        ",2382",
        "2382,",
        "2382, 2382",
        "2382, bad-code",
    ):
        with pytest.raises(ValueError):
            DailyMarketTechnicalUniverseV4View._parse_stock_filter(invalid)
    too_many_codes = ",".join((*codes, "T000000000000000"))
    assert len(too_many_codes) < universe_view_module._MAX_STOCK_FILTER_TEXT_LENGTH
    with pytest.raises(ValueError, match="100,000"):
        DailyMarketTechnicalUniverseV4View._parse_stock_filter(
            too_many_codes
        )
    assert DailyMarketTechnicalUniverseV4View._parse_stock_filter("  ") == ()


def test_qlineedit_overflow_rejects_truncated_prefix_until_user_edits(
    app: QApplication,
    tmp_path: Path,
    pinned_bookmark: dict[str, Any],
) -> None:
    saved = pinned_bookmark["bookmark"]
    assert isinstance(saved, DailyMarketTechnicalUniverseV4Bookmark)
    view = DailyMarketTechnicalUniverseV4View(saved.origin_query.store_output_root)
    view.stock_filter.setMaxLength(5)
    view.show()
    app.processEvents()
    view.stock_filter.setFocus()
    QGuiApplication.clipboard().setText("238200")
    QTest.keyClick(view.stock_filter, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
    app.processEvents()

    assert view.stock_filter.text() == "23820"
    assert view._stock_filter_rejected_text == view.stock_filter.text()
    view.apply_query()
    assert "輸入超過欄位上限" in view.status.text()
    assert view._worker is None

    view.stock_filter.selectAll()
    QTest.keyClick(view.stock_filter, Qt.Key.Key_Backspace)
    app.processEvents()
    assert view._stock_filter_rejected_text is None
    view.stock_filter.setMaxLength(universe_view_module._MAX_STOCK_FILTER_TEXT_LENGTH)
    view._set_filter_controls(saved.origin_query)
    assert view._stock_filter_rejected_text is None
    assert view.stock_filter.text() == ", ".join(saved.origin_query.stock_filter)

    view.stock_filter.selectAll()
    QTest.keyClicks(view.stock_filter, "2382")
    app.processEvents()
    assert view._stock_filter_rejected_text is None
    view.apply_query()
    assert "請先嚴格核驗" in view.status.text()
    view.close()


def test_each_rule_filter_roundtrips_all_canonical_state_combinations(
    app: QApplication,
    pinned_bookmark: dict[str, Any],
) -> None:
    saved = pinned_bookmark["bookmark"]
    assert isinstance(saved, DailyMarketTechnicalUniverseV4Bookmark)
    query = saved.origin_query
    view = DailyMarketTechnicalUniverseV4View(query.store_output_root)
    view._ensure_rule_filters(query.method_rule_keys)
    state_sets: tuple[tuple[RuleState, ...], ...] = (
        (),
        ("match",),
        ("no_match",),
        ("unknown",),
        ("match", "no_match"),
        ("match", "unknown"),
        ("no_match", "unknown"),
        ("match", "no_match", "unknown"),
    )

    for rule_key, combo in view._rule_filters.items():
        for states in state_sets:
            filter_id = (
                universe_view_module._RULE_STATE_FILTER_STATES_TO_ID.get(states)
                if states
                else universe_view_module._NO_STATE_FILTER
            )
            assert filter_id is not None
            option_index = combo.findData(filter_id)
            assert option_index >= 0
            combo.setCurrentIndex(option_index)
            expected = (
                (DailyMarketTechnicalRuleStateFilterV4.create(rule_key, states),)
                if states
                else ()
            )
            assert view._selected_rule_state_filters() == expected
            all_index = combo.findData(universe_view_module._NO_STATE_FILTER)
            assert all_index >= 0
            combo.setCurrentIndex(all_index)

    view._set_filter_controls(query)
    assert view._selected_rule_state_filters() == query.rule_state_filters
    view.close()
