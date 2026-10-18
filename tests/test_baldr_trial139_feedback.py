"""139真人回報：數值可見、巢狀窄頁可捲、名稱只作展示。"""
from dataclasses import replace
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QScrollArea, QTableView, QToolButton, QWidget

from app_module.stock_research_report_dtos import StockFundamentalObservationDTO, StockReportSourceDTO
from app_module.watchlist_service import WatchlistService
from tests.test_daily_market_technical_universe_price_query_v1 import exact_price_store
from tests.test_ui_qt_daily_market_technical_universe_price_view_v1 import _entry_index, _wait, _scroll_bookmark_state
from tests.test_ui_qt_stock_research_report import _report_for
from ui_qt.views.stock_research_report_view import StockResearchReportView
from ui_qt.views.daily_market_technical_universe_price_view_v1 import DailyMarketTechnicalUniversePriceV1View
from ui_qt.widgets.layout_helpers import CurrentPageSizeTabWidget, create_scroll_area


@pytest.fixture(scope="module")
def app() -> QApplication:
    return cast(QApplication, QApplication.instance() or QApplication([]))


def test_monthly_values_precede_collapsed_custody_without_hiding_missing_statement(app: QApplication) -> None:
    source = "official.issuer.quanta.monthly_sales.2382.2026"
    rows = tuple(StockFundamentalObservationDTO(kind="monthly_revenue", label=label,
        metric_name=metric, value=Decimal(value), unit=unit, period="2026-09", source_id=source,
        available_at="2026-10-18T04:00:00+08:00") for metric, label, value, unit in (
            ("revenue", "當月營收", "325300", "百萬元（TWD）"),
            ("previous_month_revenue", "前月營收", "423971", "百萬元（TWD）"),
            ("previous_year_revenue", "去年同月", "184109", "百萬元（TWD）"),
            ("mom_pct", "月增率", "-23.3", "%"), ("yoy_pct", "年增率", "76.7", "%")))
    report = replace(_report_for("2382", "100"), fundamentals=rows, sources=(StockReportSourceDTO(
        source_id="official.twse.operating_summary.2382.2026h1", source_label="2382半年財報",
        status="unavailable", limitations=("下載轉驗證頁；不補值。",)), StockReportSourceDTO(
        source_id=source, source_label="廣達月營收", status="available",
        limitations=("同表百萬元整數，非半年財報。" * 30,))))
    view = StockResearchReportView(cast(Any, object()))
    view.resize(800, 600)
    view._render_fundamental(report)
    view.tabs.setCurrentIndex(next(i for i in range(view.tabs.count()) if "基本面" in view.tabs.tabText(i)))
    view.show()
    try:
        app.processEvents()
        table = view.findChild(QTableView, "fundamentalMonthlyRevenueTable")
        assert table is not None and table.isVisible()
        assert table.model().rowCount() == 5
        assert "325,300" in str(table.model().index(0, 1).data())
        assert "76.7" in str(table.model().index(4, 1).data())
        details = view.findChild(QWidget, "fundamentalSourceDetails")
        assert details is not None and details.isHidden()
        assert any("2382半年財報：缺少" in label.text() and label.isVisible() for label in view.findChildren(QLabel))
        scroll = next(parent for parent in view.findChildren(QScrollArea) if parent.isAncestorOf(table))
        assert table.mapTo(scroll.viewport(), table.rect().topLeft()).y() < scroll.viewport().height()
        toggle = view.findChild(QToolButton, "fundamentalSourceDetailsToggle")
        assert toggle is not None
        toggle.click()
        assert not details.isHidden()
        assert "驗證頁" in "".join(label.text() for label in details.findChildren(QLabel))
    finally:
        view.close()
        app.processEvents()


def test_nested_narrow_price_page_keeps_filters_results_and_code_clear_reachable(
    app: QApplication, exact_price_store: dict[str, Any],
) -> None:
    view = DailyMarketTechnicalUniversePriceV1View(exact_price_store["store_root"])
    inner = CurrentPageSizeTabWidget()
    inner.addTab(view, "價格選股")
    unused = QWidget()
    unused.setMinimumHeight(2000)
    inner.addTab(unused, "未使用頁")
    outer = CurrentPageSizeTabWidget()
    outer.addTab(inner, "每日研究條件")
    host = create_scroll_area(outer)
    host.resize(700, 540)
    host.show()
    try:
        app.processEvents()
        view.refresh_sources()
        _wait(app, lambda: not view.busy, timeout_seconds=15)
        view.sources.setCurrentIndex(_entry_index(view, "complete"))
        view.load_selected_source()
        _wait(app, lambda: not view.busy, timeout_seconds=15)
        original = view.current_query.source
        assert "已嚴格核驗" in view.sources.currentText()
        assert "尚未 strict 核驗" not in view.source_pins.text()
        view.query_controls_toggle.setChecked(True)
        view.stock_filter.setText("S0001")
        view._rule_filters["ma5_20_golden_cross"].setCurrentIndex(1)
        expected_rule = view._rule_filters["ma5_20_golden_cross"].currentData()
        for width in (700, 1100, 700):
            host.resize(width, 540)
            app.processEvents()
            host.ensureWidgetVisible(view.clear_stock_filter_button, 0, 12)
            app.processEvents()
            assert host.viewport().rect().contains(view.clear_stock_filter_button.mapTo(host.viewport(), view.clear_stock_filter_button.rect().center()))
            assert view.apply_query_button.height() >= view.apply_query_button.minimumSizeHint().height()
        QTest.mouseClick(view.clear_stock_filter_button, Qt.MouseButton.LeftButton)
        assert not view.stock_filter.text()
        assert view._rule_filters["ma5_20_golden_cross"].currentData() == expected_rule
        assert view.current_query.source == original
        assert view.table.height() >= 240
        host.ensureWidgetVisible(view.table, 0, 0)
        app.processEvents()
        assert view.table.viewport().height() >= 150
        assert host.verticalScrollBar().maximum() > 0
    finally:
        view.begin_shutdown()
        _wait(app, lambda: view.workers_remaining == 0, timeout_seconds=15)
        host.close()


def test_names_from_registry_are_exact_display_only_and_ambiguous_names_are_omitted(tmp_path: Path) -> None:
    registry = tmp_path / "companies.csv"
    registry.write_text("stock_id,stock_name\n2506,甲公司\n8933,乙公司\n9999,丙公司\n9999,丁公司\n", encoding="utf-8")
    before = sha256(registry.read_bytes()).hexdigest()
    service = WatchlistService.__new__(WatchlistService)
    service.config = cast(Any, SimpleNamespace(use_sqlite=False, stock_data_file=None, meta_data_dir=tmp_path))
    assert service.query_stock_names(["2506", "8933", "9999", "250"]) == {"2506": "甲公司", "8933": "乙公司"}
    assert sha256(registry.read_bytes()).hexdigest() == before


def test_price_bookmark_routes_to_same_source_stock_after_restore(
    app: QApplication, exact_price_store: dict[str, Any],
) -> None:
    from ui_qt.main import MainWindow
    _, state = _scroll_bookmark_state(exact_price_store, stock_code="S0001", scroll_position=0)
    calls: list[str] = []
    view = SimpleNamespace(restore_bookmark_state=lambda value: calls.append("restore") or value is state,
        open_selected_stock=lambda: calls.append("same_source_stock") or True)
    daily = SimpleNamespace(technical_price_view=view, _shutting_down=False)
    recommendation = SimpleNamespace(daily_market_research_view=daily,
        result_source_tabs=SimpleNamespace(setCurrentWidget=lambda value: calls.append("daily")))
    window = SimpleNamespace(recommendation_view=recommendation, _shutdown_close_requested=False,
        _select_main_workspace=lambda key: calls.append(key))
    MainWindow._open_price_bookmark_state(cast(Any, window), state)
    assert calls == ["restore", "recommendation", "daily", "same_source_stock"]
