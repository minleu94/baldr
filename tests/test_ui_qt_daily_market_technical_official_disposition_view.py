"""F17 全母體瀏覽介面以真實保存 bundle 驗證來源、跨頁與收藏重開。"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
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
    *,
    expected_population: int = 258,
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
    assert view.current_page.counts.population.declared_count == expected_population
    assert view.current_result.counts.matching_count == expected_population
    return view, selectable[0]


def _create_varied_technical_bundle(
    bundle_fixture: Any,
    *,
    decision_cutoff: datetime,
) -> Path:
    """以正式 producer 和同一核驗 official pins 建立可區分技術狀態的合成來源。"""

    from app_module.daily_market_technical_official_disposition_bundle_v1 import (
        DailyMarketTechnicalOfficialDispositionBundleWriterV1,
    )
    from app_module.daily_market_technical_universe_v4_producer import (
        DailyMarketTechnicalUniverseV4ProductionRequest,
        produce_daily_market_technical_universe_v4,
    )
    from app_module.daily_market_technical_universe_v4_store import (
        DailyMarketTechnicalUniverseV4Cohort,
    )
    from app_module.rule_research_sample_capture import ResearchCaptureWriteScope
    from app_module.personal_data_paths import to_internal_io_path

    attempt_root = bundle_fixture.qa_root / f"and-or-varied-{time.time_ns()}"
    attempt_root.mkdir()
    database = attempt_root / "daily_prices.sqlite"
    stock_codes = bundle_fixture.included_codes[:4]
    connection = sqlite3.connect(to_internal_io_path(database))
    try:
        with connection:
            connection.execute(
                "CREATE TABLE daily_prices ("
                "日期 TEXT, 證券代號 TEXT, 開盤價 TEXT, 最高價 TEXT, 最低價 TEXT, "
                "收盤價 TEXT, 成交股數 INTEGER)"
            )
            start_date = bundle_fixture.cohort.decision_date - timedelta(days=39)
            rows: list[tuple[str, str, str, str, str, str, int]] = []
            final_volumes = {
                stock_codes[0]: 1_000,
                stock_codes[1]: 1_000,
                stock_codes[2]: 1_000_000,
                stock_codes[3]: 1_000_000,
            }
            for stock_index, stock_code in enumerate(stock_codes):
                for offset in range(40):
                    if stock_index in {0, 2}:
                        close = 100 + offset
                    else:
                        close = 139 - offset
                        if offset == 39:
                            close = 300
                    volume = (
                        final_volumes[stock_code]
                        if offset == 39
                        else 1_000
                    )
                    rows.append((
                        (start_date + timedelta(days=offset)).isoformat(),
                        stock_code,
                        str(close),
                        str(close + 1),
                        str(close - 1),
                        str(close),
                        volume,
                    ))
            connection.executemany(
                "INSERT INTO daily_prices VALUES (?,?,?,?,?,?,?)", rows
            )
    finally:
        connection.close()

    cohort = DailyMarketTechnicalUniverseV4Cohort.create(
        universe_id="synthetic-f17-and-or-varied",
        population_version=f"synthetic-{time.time_ns()}",
        decision_date=bundle_fixture.cohort.decision_date,
        raw_stock_codes=stock_codes,
        excluded_stock_codes=(),
        exclusion_reasons={},
    )
    scope = ResearchCaptureWriteScope(attempt_root / "technical-output", database)
    store_root = scope.root / "technical-store"
    produced = produce_daily_market_technical_universe_v4(
        DailyMarketTechnicalUniverseV4ProductionRequest(
            source_database=database,
            cohort=cohort,
            decision_cutoff=decision_cutoff,
            store_output_root=store_root,
            research_scope=scope,
        )
    )
    assert produced.status == "complete", produced.to_dict()
    assert produced.plan is not None and produced.receipt is not None
    writer = DailyMarketTechnicalOfficialDispositionBundleWriterV1(
        scope.root / "official-disposition-bundle-v1",
        research_scope=scope,
    )
    writer.create_from_pins(
        store_output_root=store_root,
        generation_identity_sha256=cast(str, produced.generation_identity_sha256),
        plan_identity_sha256=cast(str, produced.plan_identity_sha256),
        expected_plan_sha256=cast(str, produced.plan_sha256),
        receipt_identity_sha256=cast(str, produced.receipt_identity_sha256),
        expected_receipt_sha256=cast(str, produced.receipt_content_sha256),
        market_assignment_source_pin=bundle_fixture.market_pin,
        official_disposal_source_pin=bundle_fixture.disposal_pin,
    )
    return Path(writer.output_root)


def _query_with_rule_and_stock_filters(
    view: DailyMarketTechnicalOfficialDispositionView,
    *,
    rule_states: tuple[str, ...],
    outer_stock_codes: tuple[str, ...],
    inner_stock_codes: tuple[str, ...] = (),
) -> DailyMarketTechnicalOfficialDispositionQueryV1:
    assert view.current_result is not None
    base = view.current_result.query
    technical = base.technical_query
    rule_filters = (
        DailyMarketTechnicalRuleStateFilterV4.create(
            technical.method_rule_keys[0], cast(Any, rule_states)
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
        stock_filter=inner_stock_codes,
        sort_key=technical.sort_key,
        descending=technical.descending,
        page_index=technical.page_index,
        page_size=technical.page_size,
    )
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
        outer_stock_filter_mode="explicit_codes",
        outer_stock_codes=outer_stock_codes,
        sort_clauses=base.sort_clauses,
    )
    return query


def _bookmark_with_extended_query(
    view: DailyMarketTechnicalOfficialDispositionView,
    *,
    inner_stock_codes: tuple[str, ...] = (),
) -> DailyMarketTechnicalOfficialDispositionBookmarkV1:
    assert view.current_request is not None
    assert view._selected_row is not None
    assert view._selected_row.technical_row is not None
    base = view.current_result.query if view.current_result is not None else None
    assert base is not None
    technical = base.technical_query
    selected_code = view._selected_row.stock_code
    second_code = next(code for code in base.outer_stock_codes if code > selected_code)
    selected_state = view._selected_row.technical_row.rule(
        technical.method_rule_keys[0]
    ).state
    another_state = next(
        state for state in ("match", "no_match", "unknown") if state != selected_state
    )
    selected_states = tuple(
        state
        for state in ("match", "no_match", "unknown")
        if state in {selected_state, another_state}
    )
    query = _query_with_rule_and_stock_filters(
        view,
        rule_states=(selected_state, another_state),
        outer_stock_codes=(selected_code, second_code),
        inner_stock_codes=inner_stock_codes,
    )
    request = DailyMarketTechnicalOfficialDispositionPageRequestV1.create(
        query,
        page_index=0,
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
        technical_cell = view.results_model.index(technical_index, 2)
        assert technical_cell.isValid() and technical_cell.data() == table_rule_text
        first_page_row = view.current_page.rows[0]
        first_item = view.results_model.index(0, 0)
        assert first_item.isValid()
        QTest.mouseClick(
            view.results_table.viewport(),
            Qt.MouseButton.LeftButton,
            pos=view.results_table.visualRect(first_item).center(),
        )
        app.processEvents()
        assert view._selected_row is first_page_row

        view.navigate_page(5)
        _wait_for_idle(app, view)
        assert view.current_page is not None
        assert view.current_page.page_index == 5
        target_row = view.current_page.rows[0]
        assert target_row.stock_code != first_page_row.stock_code
        assert view.results_table.currentIndex().row() == -1
        excluded_row = view.current_page.rows[-1]
        assert excluded_row.technical_row is None
        assert view._technical_state_text(excluded_row) == "明示排除"

        # 跨頁後點同一個表格位置，必須綁到新頁列，不得沿用舊列或落成無選取。
        target_item = view.results_model.index(0, 0)
        assert target_item.isValid()
        QTest.mouseClick(
            view.results_table.viewport(),
            Qt.MouseButton.LeftButton,
            pos=view.results_table.visualRect(target_item).center(),
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


def test_all_rule_state_combinations_and_bounded_multi_stock_parser(
    app: QApplication,
) -> None:
    view = DailyMarketTechnicalOfficialDispositionView(None)
    first_rule_key = next(iter(view.rule_state_boxes))
    state_box = view.rule_state_boxes[first_rule_key]
    view.rule_filter_enabled.setChecked(True)
    assert tuple(
        tuple(cast(Any, state_box.itemData(index)))
        for index in range(1, state_box.count())
    ) == view_module._RULE_STATE_SELECTIONS
    assert state_box.itemData(0) == view_module._NO_RULE_STATE_FILTER
    for selection in view_module._RULE_STATE_SELECTIONS:
        state_box.setCurrentIndex(state_box.findData(selection))
        filters = cast(tuple[DailyMarketTechnicalRuleStateFilterV4, ...],
                       view._read_conditions()["rule_state_filters"])
        assert len(filters) == 1
        assert filters[0].rule_key == first_rule_key
        assert filters[0].states == selection
    view.rule_filter_enabled.setChecked(False)
    state_box.setCurrentIndex(0)
    assert state_box.currentData() == view_module._NO_RULE_STATE_FILTER
    assert view._read_conditions()["rule_state_filters"] == ()

    assert view_module._parse_stock_code_filter(
        "2330  2317，1101,\t0050"
    ) == ("0050", "1101", "2317", "2330")
    for raw, reason in (
        ("", "stock_code_required"),
        (" \t ", "stock_code_required"),
        ("2382,,2330", "stock_code_invalid"),
        ("2382,", "stock_code_invalid"),
        (",2382", "stock_code_invalid"),
        ("2382, ,2330", "stock_code_invalid"),
        ("2382,2382", "stock_code_duplicate"),
        ("2382,23-3", "stock_code_invalid"),
    ):
        with pytest.raises(ValueError, match=reason):
            view_module._parse_stock_code_filter(raw)

    too_many_codes = ",".join(f"{index:06d}" for index in range(100_001))
    with pytest.raises(ValueError, match="stock_code_limit"):
        view_module._parse_stock_code_filter(too_many_codes)

    max_code_count = view_module.DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_DECLARED_STOCKS
    max_input = ", ".join(f"A{index:015d}" for index in range(max_code_count))
    assert len(max_input) == view_module._MAX_STOCK_FILTER_INPUT_CHARACTERS
    parsed_max_input = view_module._parse_stock_code_filter(max_input)
    assert len(parsed_max_input) == max_code_count
    assert parsed_max_input[0] == "A000000000000000"
    assert parsed_max_input[-1] == "A000000000099999"

    assert view.stock_code_input.maxLength() == (
        view_module._MAX_STOCK_FILTER_INPUT_CHARACTERS + 1
    )
    view.stock_filter_enabled.setChecked(True)
    view.stock_code_input.setText(max_input)
    assert view.stock_code_input.text() == max_input
    assert not view.stock_code_input.input_was_truncated
    conditions = view._read_conditions()
    assert len(cast(tuple[str, ...], conditions["outer_stock_codes"])) == max_code_count

    view.stock_code_input.setText(max_input + "  ")
    assert view.stock_code_input.input_was_truncated
    with pytest.raises(ValueError, match="stock_filter_size_limit"):
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
    previous_page = view.current_page

    view.stock_filter_enabled.setChecked(True)
    view.stock_code_input.setText("1000,,1001")
    view.apply_filters()
    assert view.active_worker is None
    assert view.current_result is previous_result
    assert view.current_page is previous_page
    assert "stock_code_invalid" in view.status_label.text()

    view.stock_code_input.setText("999999")
    view.apply_filters()
    _wait_for_idle(app, view)
    assert view.current_page is not None
    assert view.current_page.counts.declared_count == 258
    assert view.current_page.counts.matching_count == 0
    assert view.current_page.rows == ()
    assert view.results_model.rowCount() == 0
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


def test_multistate_multistock_bookmark_roundtrip_and_inner_filter_atomic_reject(
    app: QApplication,
    bundle_fixture: Any,
) -> None:
    view, _entry = _load_real_bundle(app, bundle_fixture)
    assert view.select_stock_code("1000")
    assert view._selected_row is not None and view._selected_row.technical_row is not None
    original_row_identity = view._selected_row.row_identity_sha256
    assert view.current_page is not None
    base_query = view.current_result.query if view.current_result is not None else None
    assert base_query is not None
    rule_key = base_query.technical_query.method_rule_keys[0]
    selected_state = view._selected_row.technical_row.rule(rule_key).state
    another_state = next(
        state for state in ("match", "no_match", "unknown") if state != selected_state
    )
    selected_states = tuple(
        state
        for state in ("match", "no_match", "unknown")
        if state in {selected_state, another_state}
    )
    original_query_identity = base_query.query_identity_sha256
    selected_code = view._selected_row.stock_code
    second_code = next(
        row.stock_code for row in view.current_page.rows if row.stock_code > selected_code
    )
    view.rule_filter_enabled.setChecked(True)
    view.rule_state_boxes[rule_key].setCurrentIndex(
        view.rule_state_boxes[rule_key].findData(selected_states)
    )
    view.stock_filter_enabled.setChecked(True)
    view.stock_code_input.setText(f"{second_code}， {selected_code}")
    view.apply_filters()
    _wait_for_idle(app, view)
    assert view.current_result is not None
    assert view.current_result.query.query_identity_sha256 != original_query_identity
    assert view.current_result.query.technical_query.rule_state_filters[0].states == selected_states
    assert view.select_stock_code(selected_code)
    assert view._selected_row is not None
    assert view.current_page is not None
    assert view._selected_row.row_identity_sha256 != original_row_identity
    view.add_selected_to_comparison()
    current_result = view.current_result
    current_page = view.current_page
    current_selection = view._selected_row
    captured: list[object] = []
    view.bookmarkPrepared.connect(captured.append)
    view.prepare_bookmark()
    assert captured == []
    assert "比較收藏需選 2–5 檔" in view.status_label.text()
    assert view.current_result is current_result
    assert view.current_page is current_page
    assert view._selected_row is current_selection
    assert len(view.comparison_basket) == 1
    assert view.select_stock_code(second_code)
    view.add_selected_to_comparison()
    assert len(view.comparison_basket) == 2
    assert view.select_stock_code(selected_code)
    view.prepare_bookmark()
    assert captured, view.status_label.text()
    bookmark = cast(DailyMarketTechnicalOfficialDispositionBookmarkV1, captured[-1])
    bookmarked_request = DailyMarketTechnicalOfficialDispositionPageRequestV1.from_json(
        bookmark.origin_page_request_json
    )
    bookmarked_query = bookmarked_request.query
    expected_codes = bookmarked_query.outer_stock_codes
    expected_states = bookmarked_query.technical_query.rule_state_filters[0].states
    assert len(expected_codes) == 2
    assert len(expected_states) == 2

    # 重現先前拒絕案例：套用不含此股票實際規則狀態的條件後，該股票不在新結果頁。
    rejected_states: tuple[str, ...] = ("match", "unknown")
    if selected_state in rejected_states:
        rejected_states = (next(
            state for state in ("match", "no_match", "unknown")
            if state != selected_state
        ),)
    view.rule_state_boxes[rule_key].setCurrentIndex(
        view.rule_state_boxes[rule_key].findData(rejected_states)
    )
    view.apply_filters()
    _wait_for_idle(app, view)
    assert view.current_page is not None
    assert all(row.stock_code != selected_code for row in view.current_page.rows)
    with pytest.raises(
        ValueError, match="technical_official_view_saved_row_missing_or_changed"
    ):
        view_module._find_row(
            view.current_page, selected_code, bookmark.selected_row_identity_sha256
        )

    restored = DailyMarketTechnicalOfficialDispositionView(bundle_fixture.bundle_root)
    try:
        restored.restore_bookmark(bookmark)
        _wait_for_idle(app, restored)
        assert restored.current_result is not None, restored.status_label.text()
        assert (
            restored.current_result.query.query_identity_sha256
            == bookmarked_query.query_identity_sha256
        )
        assert restored.current_page is not None and restored.current_page.page_index == 0
        assert restored._selected_row is not None
        assert restored._selected_row.stock_code == "1000"
        assert restored.rule_filter_enabled.isChecked()
        rule_key = bookmarked_query.technical_query.method_rule_keys[0]
        assert tuple(cast(Any, restored.rule_state_boxes[rule_key].currentData())) == expected_states
        assert restored.stock_filter_enabled.isChecked()
        assert restored.stock_code_input.text() == ", ".join(expected_codes)
        restored_conditions = restored._read_conditions()
        restored_filters = cast(
            tuple[DailyMarketTechnicalRuleStateFilterV4, ...],
            restored_conditions["rule_state_filters"],
        )
        assert restored_filters[0].states == expected_states
        assert restored_conditions["outer_stock_codes"] == expected_codes

        # 每一種非空狀態集合都能由同一個已核查來源查詢表示並回填控制項。
        for selection in view_module._RULE_STATE_SELECTIONS:
            query = _query_with_rule_and_stock_filters(
                restored,
                rule_states=selection,
                outer_stock_codes=expected_codes,
            )
            restored._apply_query_controls(query)
            assert tuple(cast(Any, restored.rule_state_boxes[rule_key].currentData())) == selection
            restored_conditions = restored._read_conditions()
            restored_filters = cast(
                tuple[DailyMarketTechnicalRuleStateFilterV4, ...],
                restored_conditions["rule_state_filters"],
            )
            assert restored_filters[0].states == selection
            assert restored_conditions["outer_stock_codes"] == expected_codes
            assert restored.stock_code_input.text() == ", ".join(expected_codes)

        previous_result = restored.current_result
        previous_page = restored.current_page
        previous_controls = _controls_snapshot(restored)
        previous_basket = restored.comparison_basket
        unsupported = _bookmark_with_extended_query(
            restored, inner_stock_codes=("1000",)
        )
        restored.restore_bookmark(unsupported)
        assert restored.active_worker is None
        assert restored.current_result is previous_result
        assert restored.current_page is previous_page
        assert _controls_snapshot(restored) == previous_controls
        assert restored.comparison_basket == previous_basket
        assert "inner_stock_filter_not_representable" in restored.status_label.text()
    finally:
        restored.close()
    view.close()


def test_real_and_or_conditions_sort_globally_before_paging(
    app: QApplication,
    bundle_fixture: Any,
) -> None:
    from app_module.daily_market_technical_universe_v4_store import (
        DailyMarketTechnicalUniverseV4StoreReader,
    )

    verified_store = DailyMarketTechnicalUniverseV4StoreReader(
        bundle_fixture.store_root
    ).read_exact(
        bundle_fixture.generation_identity_sha256,
        bundle_fixture.plan_identity_sha256,
        bundle_fixture.receipt_identity_sha256,
        expected_receipt_sha256=bundle_fixture.expected_receipt_sha256,
        expected_plan_sha256=bundle_fixture.expected_plan_sha256,
    )
    varied_bundle_root = _create_varied_technical_bundle(
        bundle_fixture,
        decision_cutoff=verified_store.plan.source_clock.decision_cutoff,
    )
    view, _entry = _load_real_bundle(
        app,
        SimpleNamespace(bundle_root=varied_bundle_root),
        expected_population=4,
    )
    try:
        result = view.current_result
        first_page = view.current_page
        assert result is not None and first_page is not None
        all_rows: list[Any] = []
        for page_index in range(first_page.page_count):
            request = DailyMarketTechnicalOfficialDispositionPageRequestV1.create(
                result.query,
                page_index=page_index,
                page_size=first_page.page_size,
            )
            page = result.read_page_request(request)
            all_rows.extend(page.rows)
        rule_keys = result.query.technical_query.method_rule_keys
        states_by_code: dict[str, dict[str, str]] = {}
        for row in all_rows:
            if row.filter_evaluation.row_scope != "included_processed":
                continue
            assert row.technical_row is not None
            states_by_code[row.stock_code] = {
                rule_key: row.technical_row.rule(rule_key).state
                for rule_key in rule_keys
            }

        candidate: tuple[
            str, tuple[str, ...], str, tuple[str, ...], list[str], list[str]
        ] | None = None
        state_selections = cast(
            tuple[tuple[str, ...], ...], view_module._RULE_STATE_SELECTIONS
        )
        for left_index, left_key in enumerate(rule_keys):
            for right_key in rule_keys[left_index + 1 :]:
                for left_states in state_selections:
                    left_set = set(left_states)
                    for right_states in state_selections:
                        right_set = set(right_states)
                        and_codes = [
                            code
                            for code, values in states_by_code.items()
                            if values[left_key] in left_set
                            and values[right_key] in right_set
                        ]
                        or_codes = [
                            code
                            for code, values in states_by_code.items()
                            if values[left_key] in left_set
                            or values[right_key] in right_set
                        ]
                        if len(and_codes) >= 2 and len(or_codes) > len(and_codes):
                            candidate = (
                                left_key,
                                left_states,
                                right_key,
                                right_states,
                                and_codes,
                                or_codes,
                            )
                            break
                    if candidate is not None:
                        break
                if candidate is not None:
                    break
            if candidate is not None:
                break
        assert candidate is not None, "合成真來源需有可區分 AND/OR 的已核規則狀態"
        left_key, left_states, right_key, right_states, and_codes, or_codes = candidate
        extra_code = next(code for code in or_codes if code not in and_codes)
        selected_codes = (and_codes[0], and_codes[1], extra_code)

        view.rule_filter_enabled.setChecked(True)
        view.rule_state_boxes[left_key].setCurrentIndex(
            view.rule_state_boxes[left_key].findData(left_states)
        )
        view.rule_state_boxes[right_key].setCurrentIndex(
            view.rule_state_boxes[right_key].findData(right_states)
        )
        for scope, checkbox in view.scope_checks.items():
            checkbox.setChecked(scope in {"included_processed", "excluded"})
        view.stock_filter_enabled.setChecked(True)
        view.stock_code_input.setText(
            f"{selected_codes[2]}， {selected_codes[0]},\t{selected_codes[1]}"
        )
        view.page_size_box.setValue(1)
        view.sort_rows[0][0].setCurrentIndex(
            view.sort_rows[0][0].findData("stock_code")
        )
        view.sort_rows[0][1].setCurrentIndex(
            view.sort_rows[0][1].findData("desc")
        )
        view.apply_filters()
        _wait_for_idle(app, view)
        and_result = view.current_result
        assert and_result is not None
        assert and_result.query.outer_stock_codes == tuple(sorted(selected_codes))
        assert and_result.counts.matching_count == 2
        assert view.current_page is not None and view.current_page.page_index == 0
        and_first_code = view.current_page.rows[0].stock_code
        view.navigate_page(1)
        _wait_for_idle(app, view)
        assert view.current_page is not None
        and_second_code = view.current_page.rows[0].stock_code
        assert (and_first_code, and_second_code) == tuple(sorted(and_codes, reverse=True))

        view.combine_box.setCurrentIndex(view.combine_box.findData("OR"))
        view.apply_filters()
        _wait_for_idle(app, view)
        or_result = view.current_result
        assert or_result is not None
        expected_or_codes = tuple(
            sorted(set(or_codes).intersection(selected_codes), reverse=True)
        )
        assert or_result.counts.matching_count == len(expected_or_codes)
        ordered_or_codes: list[str] = []
        assert view.current_page is not None
        assert view.current_page.page_count == len(expected_or_codes)
        for page_index in range(len(expected_or_codes)):
            if page_index:
                view.navigate_page(page_index)
                _wait_for_idle(app, view)
            assert view.current_page is not None
            ordered_or_codes.append(view.current_page.rows[0].stock_code)
        assert ordered_or_codes == list(expected_or_codes)
    finally:
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
