"""V2 正常 Qt view 對真實 257 列 bundle、F07 gate 與收藏回復的覆蓋。"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
import sys
import time
from typing import cast

import pytest

_REPO = next(
    path for path in Path(__file__).resolve().parents
    if (path / "tests").is_dir() and (path / "app_module").is_dir()
)
for _import_path in (str(_REPO), str(_REPO / "tests")):
    if _import_path not in sys.path:
        sys.path.insert(0, _import_path)

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel
import app_module.daily_market_technical_official_disposition_composite_bookmark_v2 as bookmark_v2
import app_module.daily_market_technical_official_disposition_query_reader_v1 as query_reader
from app_module.daily_market_technical_official_disposition_composite_bookmark_storage_v2 import (
    DailyMarketTechnicalOfficialDispositionCompositeViewBookmarkEnvelopeV2,
)
from app_module.daily_market_technical_official_disposition_composite_query_v2 import (
    DailyMarketTechnicalOfficialDispositionCompositeQueryV2,
    DailyMarketTechnicalOfficialDispositionCompositeQueryPageV2,
    DailyMarketTechnicalOfficialDispositionCompositeSortClauseV2,
    DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV2,
    execute_composite_query_v2,
)
from app_module.daily_market_technical_official_disposition_composite_query_v1 import (
    DailyMarketTechnicalOfficialDispositionCompositeQueryV1,
)
from app_module.daily_market_technical_universe_projection_group_session_v3 import (
    DailyMarketTechnicalUniverseProjectionGroupSessionV3,
)
from test_daily_market_technical_official_disposition_bundle_v1 import (
    _BundleFixture,
    _tree_signature,
)
from ui_qt.views.daily_market_technical_official_disposition_composite_view_v2 import (
    DailyMarketTechnicalOfficialDispositionCompositeViewV2,
    _ConditionsV2,
    _SourceChoiceV2,
    _execute_fresh_query_v2,
)
from ui_qt.main import _drain_qt_deferred_deletes


pytest_plugins = (
    "test_daily_market_technical_official_disposition_composite_reader_v1",
    "test_daily_market_technical_official_disposition_composite_query_v2",
)


@pytest.fixture(scope="module")
def app() -> QApplication:
    instance = cast(QApplication | None, QApplication.instance())
    if instance is None:
        instance = QApplication([])
    return instance


def _wait_for_settled(
    app: QApplication,
    events: list[tuple[str, bool]],
    previous_count: int,
    *,
    timeout_seconds: float = 600.0,
) -> tuple[str, bool]:
    deadline = time.monotonic() + timeout_seconds
    while len(events) <= previous_count:
        app.processEvents()
        if time.monotonic() >= deadline:
            raise AssertionError("複合研究 V2 View 背景工作逾時")
        time.sleep(0.005)
    app.processEvents()
    return events[previous_count]


def _close_view_and_wait_for_native_workers(
    app: QApplication,
    view: DailyMarketTechnicalOfficialDispositionCompositeViewV2,
) -> None:
    view.begin_shutdown()
    deadline = time.monotonic() + 600.0
    while view.active_worker is not None or view._has_running_worker():
        app.processEvents()
        if time.monotonic() >= deadline:
            raise AssertionError("複合研究 V2 View worker 未在期限內到達原生終態")
        time.sleep(0.005)
    app.processEvents()
    assert view.active_worker is None
    assert not view._has_running_worker()
    assert not view._live_workers
    view.close()
    app.processEvents()
    assert not view.isVisible()
    _drain_qt_deferred_deletes(app, (view,))


def _assert_source_trees_unchanged(bundle_fixture: _BundleFixture) -> None:
    assert bundle_fixture.original_signatures == tuple(
        (path, _tree_signature(Path(path)))
        for path, _signature in bundle_fixture.original_signatures
    )


def _open_selected_bundle(
    app: QApplication,
    view: DailyMarketTechnicalOfficialDispositionCompositeViewV2,
    events: list[tuple[str, bool]],
) -> None:
    previous = len(events)
    view.refresh_catalog()
    kind, succeeded = _wait_for_settled(app, events, previous)
    assert kind == "盤點已保存來源清單" and succeeded
    assert view.catalog_list.count() == 1
    view.catalog_list.setCurrentRow(0)
    app.processEvents()
    previous = len(events)
    view.open_selected_candidate()
    kind, succeeded = _wait_for_settled(app, events, previous)
    assert kind == "精確核驗並執行 V2 全域複合查詢" and succeeded


def test_v2_unsupported_saved_multisort_is_rejected_before_any_view_state_changes(
    app: QApplication,
    exact_query,
    projection_group_session_v3,
) -> None:
    group = projection_group_session_v3
    base = DailyMarketTechnicalOfficialDispositionCompositeQueryV1.create(
        exact_query, projection_group_session_identity_sha256=group.identity_sha256,
    )
    query = DailyMarketTechnicalOfficialDispositionCompositeQueryV2.create(
        base,
        sort_clauses=(
            DailyMarketTechnicalOfficialDispositionCompositeSortClauseV2("price.close_price", "asc"),
            DailyMarketTechnicalOfficialDispositionCompositeSortClauseV2("decision_date", "asc"),
        ),
    )
    result = execute_composite_query_v2(query, group)
    page = result.read_page(0, 1)
    bookmark = bookmark_v2.DailyMarketTechnicalOfficialDispositionCompositeBookmarkV2.create_from_real_row_context(
        result, page, page.rows[0].stock_code,
    )
    envelope = DailyMarketTechnicalOfficialDispositionCompositeViewBookmarkEnvelopeV2.create(bookmark)
    view = DailyMarketTechnicalOfficialDispositionCompositeViewV2()
    try:
        before = (view.current_result, view.current_page, view._source)
        assert view.restore_bookmark(envelope) is False
        assert "sort_not_supported" in view.status_label.text()
        assert (view.current_result, view.current_page, view._source) == before
        assert view.active_worker is None and not view._has_running_worker()
    finally:
        _close_view_and_wait_for_native_workers(app, view)


def test_v2_price_controls_are_decimal_and_separate_from_four_group_unknown_policy(
    app: QApplication,
) -> None:
    view = DailyMarketTechnicalOfficialDispositionCompositeViewV2()
    try:
        view.price_min_input.setText("10.125")
        view.price_max_input.setText("20.250")
        view.price_min_inclusive.setChecked(False)
        view.price_max_inclusive.setChecked(True)
        view.unknown_price_box.setCurrentIndex(view.unknown_price_box.findData("exclude"))
        view.ma_state_checks["match"].setChecked(True)
        view.kdj_state_checks["match"].setChecked(True)
        view.combine_box.setCurrentIndex(view.combine_box.findData("OR"))
        view.unknown_box.setCurrentIndex(view.unknown_box.findData("only"))

        conditions = view._read_conditions()
        assert type(conditions) is _ConditionsV2
        assert conditions.min_close_price == Decimal("10.125")
        assert conditions.max_close_price == Decimal("20.250")
        assert conditions.min_inclusive is False
        assert conditions.max_inclusive is True
        assert conditions.unknown_price_policy == "exclude"
        assert conditions.condition_combine_mode == "OR"
        assert conditions.unknown_policy == "only"

        view.price_min_input.setText("20")
        view.price_max_input.setText("10")
        with pytest.raises(ValueError, match="price_range_invalid"):
            _execute_fresh_query_v2(
                _SourceChoiceV2("C:/unused", "0" * 64, "0" * 64),
                view._read_conditions(),
                page_size=1,
                cancel_callback=lambda: False,
            )
    finally:
        _close_view_and_wait_for_native_workers(app, view)


def test_v2_view_runs_real_two_parent_257_cohort_f07_sort_pages_and_restores_bookmark(
    app: QApplication,
    bundle_fixture: _BundleFixture,
) -> None:
    view = DailyMarketTechnicalOfficialDispositionCompositeViewV2(bundle_fixture.bundle_root)
    view.resize(900, 900)
    view.show()
    app.processEvents()
    events: list[tuple[str, bool]] = []
    view.operationSettled.connect(lambda kind, success: events.append((kind, success)))
    captured: list[object] = []
    view.bookmarkPrepared.connect(captured.append)
    try:
        assert view.bundle_output_root == bundle_fixture.bundle_root
        disclosure_text = " ".join(label.text() for label in view.findChildren(QLabel))
        assert "官方資料可得時間未知" in disclosure_text
        assert "研究用途" in disclosure_text
        view.page_size_box.setValue(256)
        for scope, check in view.scope_checks.items():
            check.setChecked(scope == "included_processed")
        _open_selected_bundle(app, view, events)

        baseline = view.current_result
        baseline_page = view.current_page
        group = view._projection_group_session
        assert type(baseline) is DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV2
        assert type(baseline_page) is DailyMarketTechnicalOfficialDispositionCompositeQueryPageV2
        assert type(group) is DailyMarketTechnicalUniverseProjectionGroupSessionV3
        assert group.parent_segment_indexes == (0, 1)
        assert len(group.price_facts) == len(bundle_fixture.included_codes) == 257
        population = baseline.counts.base_f17_counts.population
        assert (
            population.declared_count,
            population.included_count,
            population.processed_count,
            population.excluded_count,
            population.pending_count,
        ) == (258, 257, 257, 1, 0)
        assert baseline.visible_count == 257
        assert baseline_page.page_size == 256 and baseline_page.page_count == 2
        assert tuple(row.stock_code for row in baseline_page.rows) == bundle_fixture.included_codes[:256]

        known_prices = tuple(
            (fact.close_price, fact.stock_code)
            for fact in group.price_facts
            if fact.status == "known" and fact.close_price is not None
        )
        assert len(known_prices) >= 2
        expected_order = tuple(
            stock_code
            for _price, stock_code in sorted(known_prices, key=lambda item: (item[0], item[1]))
        )
        view.price_min_input.setText(str(min(price for price, _code in known_prices)))
        view.price_max_input.setText(str(max(price for price, _code in known_prices)))
        view.price_min_inclusive.setChecked(True)
        view.price_max_inclusive.setChecked(True)
        view.unknown_price_box.setCurrentIndex(view.unknown_price_box.findData("exclude"))
        view.sort_field_box.setCurrentIndex(view.sort_field_box.findData("price.close_price"))
        view.sort_direction_box.setCurrentIndex(view.sort_direction_box.findData("asc"))
        view.page_size_box.setValue(max(1, min(256, len(expected_order) // 2)))

        previous = len(events)
        view.apply_filters()
        kind, succeeded = _wait_for_settled(app, events, previous)
        assert kind == "精確核驗並執行 V2 全域複合查詢" and succeeded
        result = view.current_result
        page0 = view.current_page
        assert result is not None and page0 is not None
        assert result.query.min_close_price == min(price for price, _code in known_prices)
        assert result.query.max_close_price == max(price for price, _code in known_prices)
        assert result.query.min_inclusive is True and result.query.max_inclusive is True
        assert result.query.unknown_price_policy == "exclude"
        assert result.query.sort_clauses[0].field == "price.close_price"
        assert result.ordered_stock_codes == expected_order
        assert result.visible_count == len(expected_order)
        assert page0.page_index == 0 and page0.page_count >= 2
        assert tuple(row.stock_code for row in page0.rows) == expected_order[:page0.page_size]
        assert "四群原複合結果" in view.counts_label.text()
        assert "F07 價格列" in view.counts_label.text()
        assert "最終複合結果" in view.counts_label.text()
        assert "F07 gate 後全域可見" in view.page_label.text()

        first_code = page0.rows[0].stock_code
        assert view.select_stock_code(first_code)
        view.add_comparison_button.click()
        assert tuple(item.selection.stock_code for item in view._basket) == (first_code,)

        page_size = page0.page_size
        second_index = 1
        second_expected_code = expected_order[second_index * page_size]
        previous = len(events)
        view.navigate_page(second_index)
        kind, succeeded = _wait_for_settled(app, events, previous)
        assert kind == "讀取 V2 全域排序結果的指定頁" and succeeded
        page1 = view.current_page
        assert page1 is not None and page1.page_index == second_index
        assert page1._result is result
        assert page1.rows[0].stock_code == second_expected_code
        assert view.select_stock_code(second_expected_code)
        view.add_comparison_button.click()
        assert tuple(item.selection.stock_code for item in view._basket) == (
            first_code,
            second_expected_code,
        )
        assert view.compare_button.isEnabled()

        view.detail_button.click()
        app.processEvents()
        assert view.results_stack.currentIndex() == 1
        assert "四群結果 AND 價格閘門" in view.detail_text.toPlainText()
        view.back_button.click()
        app.processEvents()
        assert view.results_stack.currentIndex() == 0
        assert view.current_result is result
        assert view.current_page is page1
        assert view._selected_row is not None
        assert view._selected_row.stock_code == second_expected_code

        view.page_scroll.verticalScrollBar().setValue(
            min(41, view.page_scroll.verticalScrollBar().maximum())
        )
        saved_scroll = view.page_scroll.verticalScrollBar().value()
        saved_query_json = result.query.to_json()
        saved_pins = result.source_pins
        saved_basket = tuple(item.selection.stock_code for item in view._basket)
        view.prepare_bookmark()
        assert len(captured) == 1
        envelope = captured[0]
        assert type(envelope) is DailyMarketTechnicalOfficialDispositionCompositeViewBookmarkEnvelopeV2
        bookmark = bookmark_v2.DailyMarketTechnicalOfficialDispositionCompositeBookmarkV2.from_json(
            envelope.bookmark_json
        )
        assert bookmark.query_json == saved_query_json
        assert bookmark.source_pins == saved_pins
        assert bookmark.basket_stock_codes == saved_basket
        assert bookmark.scroll_position == saved_scroll

        previous = len(events)
        assert view.restore_bookmark(envelope)
        kind, succeeded = _wait_for_settled(app, events, previous)
        assert kind == "saved pins fresh exact 重開 V2 複合收藏" and succeeded
        restored = view.current_result
        restored_page = view.current_page
        assert restored is not None and restored_page is not None
        assert restored.query.to_json() == saved_query_json
        assert restored.source_pins == saved_pins
        assert restored_page.page_index == second_index
        assert view._selected_row is not None
        assert view._selected_row.stock_code == second_expected_code
        assert tuple(item.selection.stock_code for item in view._basket) == saved_basket
        assert view.page_scroll.verticalScrollBar().value() == saved_scroll
        assert view.price_min_input.text() == str(bookmark.query.min_close_price)
        assert view.price_max_input.text() == str(bookmark.query.max_close_price)
        _assert_source_trees_unchanged(bundle_fixture)
    finally:
        _close_view_and_wait_for_native_workers(app, view)


def test_v2_execution_honors_early_cancel_and_rejects_poisoned_real_group(
    app: QApplication,
    bundle_fixture: _BundleFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    view = DailyMarketTechnicalOfficialDispositionCompositeViewV2(bundle_fixture.bundle_root)
    try:
        source = _SourceChoiceV2(
            str(bundle_fixture.bundle_root),
            bundle_fixture.reference.bundle_identity_sha256,
            bundle_fixture.reference.manifest_sha256,
        )
        conditions = view._read_conditions()
        with pytest.raises(ValueError, match="cancelled"):
            _execute_fresh_query_v2(
                source,
                conditions,
                page_size=1,
                cancel_callback=lambda: True,
            )

        group = query_reader.open_daily_market_technical_official_disposition_bundle_projection_group_session_v3(
            bundle_output_root=source.output_root,
            bundle_identity_sha256=source.bundle_identity_sha256,
            expected_manifest_sha256=source.manifest_sha256,
            row_scope_filter=conditions.row_scope_filter,
            rule_state_filters=conditions.rule_state_filters,
            combine_mode=conditions.technical_combine_mode,
            market_assignment_states=conditions.market_assignment_states,
            official_disposal_states=conditions.official_disposal_states,
            outer_stock_filter_mode=conditions.outer_stock_filter_mode,
            outer_stock_codes=conditions.outer_stock_codes,
            sort_clauses=(),
        )
        group._require_active().group._failed = True
        monkeypatch.setattr(
            "ui_qt.views.daily_market_technical_official_disposition_composite_view_v2.open_daily_market_technical_official_disposition_bundle_projection_group_session_v3",
            lambda **_kwargs: group,
        )
        with pytest.raises(ValueError, match="poisoned|not_reader_issued"):
            _execute_fresh_query_v2(
                source,
                conditions,
                page_size=1,
                cancel_callback=None,
            )
    finally:
        _close_view_and_wait_for_native_workers(app, view)


def test_v2_brand_new_view_waits_for_scroll_range_before_settling_restore(
    app: QApplication,
    bundle_fixture: _BundleFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_view = DailyMarketTechnicalOfficialDispositionCompositeViewV2(bundle_fixture.bundle_root)
    source_view.resize(720, 360)
    source_view.show()
    app.processEvents()
    source_events: list[tuple[str, bool]] = []
    source_view.operationSettled.connect(
        lambda kind, success: source_events.append((kind, success))
    )
    captured: list[object] = []
    source_view.bookmarkPrepared.connect(captured.append)
    try:
        _open_selected_bundle(app, source_view, source_events)
        page = source_view.current_page
        assert page is not None and page.rows
        assert source_view.select_stock_code(page.rows[0].stock_code)
        scrollbar = source_view.page_scroll.verticalScrollBar()
        assert scrollbar.maximum() > 0
        saved_scroll = min(41, scrollbar.maximum())
        assert saved_scroll > 0
        scrollbar.setValue(saved_scroll)
        source_view.prepare_bookmark()
        assert len(captured) == 1
        envelope = captured[0]
        assert type(envelope) is DailyMarketTechnicalOfficialDispositionCompositeViewBookmarkEnvelopeV2
        bookmark = bookmark_v2.DailyMarketTechnicalOfficialDispositionCompositeBookmarkV2.from_json(
            envelope.bookmark_json
        )
        assert bookmark.scroll_position == saved_scroll
    finally:
        _close_view_and_wait_for_native_workers(app, source_view)

    restored_view = DailyMarketTechnicalOfficialDispositionCompositeViewV2(bundle_fixture.bundle_root)
    restored_view.resize(720, 360)
    restored_view.show()
    app.processEvents()
    restored_events: list[tuple[str, bool]] = []
    restored_view.operationSettled.connect(
        lambda kind, success: restored_events.append((kind, success))
    )
    original_metrics = restored_view._restore_scroll_layout_metrics_v2
    metric_reads = 0

    def delayed_initial_range() -> tuple[int, int, int]:
        nonlocal metric_reads
        metric_reads += 1
        minimum, maximum, current = original_metrics()
        if metric_reads <= 2:
            return minimum, min(maximum, saved_scroll - 1), current
        return minimum, maximum, current

    monkeypatch.setattr(restored_view, "_restore_scroll_layout_metrics_v2", delayed_initial_range)
    try:
        previous = len(restored_events)
        assert restored_view.restore_bookmark(envelope)
        kind, succeeded = _wait_for_settled(app, restored_events, previous)
        assert kind == "saved pins fresh exact 重開 V2 複合收藏"
        assert succeeded
        assert metric_reads >= 4
        assert restored_view.page_scroll.verticalScrollBar().value() == saved_scroll
        assert not restored_view._has_running_worker()
    finally:
        _close_view_and_wait_for_native_workers(app, restored_view)
