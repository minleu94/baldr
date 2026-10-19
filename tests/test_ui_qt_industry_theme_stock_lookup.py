from __future__ import annotations

import os
import threading
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from app_module.theme_daily_service import ThemeDailyReport, ThemeMetricCoverage
from app_module.theme_research_snapshot import ThemeResearchSnapshot
from tests.test_ui_qt_industry_theme_map_view import _daily_row, _wait_until, app
from ui_qt.views import industry_theme_map_view as view_module
from ui_qt.views.industry_theme_map_view import IndustryThemeMapView


def _lookup_snapshot(
    identity: str = "a" * 64,
    *,
    revised: bool = False,
) -> ThemeResearchSnapshot:
    chain = "新版鏈" if revised else "科技鏈"
    ai_theme = "新版 AI" if revised else "AI"
    foundry_theme = "新版晶圓代工" if revised else "晶圓代工"
    peer_chain = "新版電子鏈" if revised else "電子鏈"
    peer_theme = "新版晶片" if revised else "晶片"
    rows = (
        _daily_row(
            chain,
            ai_theme,
            ("2330", "2317"),
            returns=Decimal("1.25"),
            turnover=Decimal("1000"),
            volume=None,
            flow_shares=None,
            flow_amount=None,
            coverage=ThemeMetricCoverage(2, 2, 2, 0, 0, 0),
        ),
        _daily_row(
            chain,
            foundry_theme,
            ("2330",),
            returns=Decimal("0.75"),
            turnover=Decimal("500"),
            volume=None,
            flow_shares=None,
            flow_amount=None,
            coverage=ThemeMetricCoverage(1, 1, 1, 0, 0, 0),
        ),
        _daily_row(
            peer_chain,
            peer_theme,
            ("1111",),
            returns=Decimal("-0.25"),
            turnover=Decimal("200"),
            volume=None,
            flow_shares=None,
            flow_amount=None,
            coverage=ThemeMetricCoverage(1, 1, 1, 0, 0, 0),
        ),
    )
    report = ThemeDailyReport(
        data_date=date(2026, 10, 16),
        known_at=datetime(2026, 10, 17, 2, 0, tzinfo=timezone.utc),
        mapping_snapshot_date="2026-10-15",
        mapping_available_date="2026-10-15",
        status="current_research",
        rows=rows,
        warnings=("five_session_calendar_unavailable",),
    )
    names = {"2330": "台積電", "2317": "鴻海", "1111": "台積電"}
    mapping = tuple(
        SimpleNamespace(
            stock_id=stock_id,
            stock_name=names[stock_id],
            chain_name=row.chain_name,
            theme_name=row.theme_name,
            chain_tier="核心鏈",
            assignment_method="公司主業",
            source_name="本機分類來源",
            source_tier="來源一級",
            evidence_note="依保存映射列",
        )
        for row in rows
        for stock_id in row.stock_ids
    )
    return ThemeResearchSnapshot(identity, report, mapping)


def _result_index(
    view: IndustryThemeMapView,
    stock_id: str,
    chain_name: str,
    theme_name: str,
) -> int:
    for index in range(1, view.stock_lookup_results.count()):
        value = view.stock_lookup_results.itemData(
            index, Qt.ItemDataRole.UserRole
        )
        if isinstance(value, (tuple, list)) and tuple(value[1:]) == (
            stock_id,
            chain_name,
            theme_name,
        ):
            return index
    raise AssertionError("找不到明選股票反查項目")


def _double_click_member(
    view: IndustryThemeMapView,
    application,
    stock_id: str,
) -> None:
    row = next(
        row_index
        for row_index in range(view.member_table.rowCount())
        if view.member_table.item(row_index, 0).text() == stock_id
    )
    item = view.member_table.item(row, 1)
    member_viewport = view.member_table.viewport()
    view.scroll_area.ensureWidgetVisible(view.member_table, 0, 0)
    view.member_table.scrollToItem(item)
    application.processEvents()
    position = view.member_table.visualItemRect(item).center()
    assert member_viewport.rect().contains(position)
    assert member_viewport.visibleRegion().contains(position)
    QTest.mouseClick(member_viewport, Qt.MouseButton.LeftButton, pos=position)
    QTest.qWait(50)
    QTest.mouseDClick(member_viewport, Qt.MouseButton.LeftButton, pos=position)
    application.processEvents()


def test_exact_code_lists_multitheme_and_locates_before_original_double_click():
    application = app()
    view = IndustryThemeMapView()
    view.resize(1050, 760)
    view.set_snapshot(_lookup_snapshot())
    view.show()
    application.processEvents()
    selected_stock_ids: list[str] = []
    view.stockSelected.connect(selected_stock_ids.append)

    view.stock_lookup_input.setText("2330")
    assert view.stock_lookup_results.count() == 3
    assert "科技鏈／AI" in view.stock_lookup_results.itemText(1)
    assert "科技鏈／晶圓代工" in view.stock_lookup_results.itemText(2)
    assert view.stock_lookup_results.currentIndex() == 0
    assert not view.stock_lookup_locate_button.isEnabled()

    selected_index = _result_index(view, "2330", "科技鏈", "晶圓代工")
    view.stock_lookup_results.setCurrentIndex(selected_index)
    assert view.stock_lookup_locate_button.isEnabled()
    view.scroll_area.ensureWidgetVisible(view.stock_lookup_locate_button)
    QTest.mouseClick(view.stock_lookup_locate_button, Qt.MouseButton.LeftButton)
    application.processEvents()

    assert view.chain_filter.currentData() == "科技鏈"
    assert view.theme_filter.currentText() == "晶圓代工"
    assert view.member_table.rowCount() == 1
    assert view.member_table.item(0, 0).text() == "2330"
    assert [index.row() for index in view.member_table.selectionModel().selectedRows()] == [0]
    assert selected_stock_ids == []

    _double_click_member(view, application, "2330")
    assert selected_stock_ids == ["2330"]
    view.shutdown()


def test_partial_unicode_name_keeps_same_name_and_multitheme_results_explicit():
    app()
    view = IndustryThemeMapView()
    view.set_snapshot(_lookup_snapshot())

    view.stock_lookup_input.setText("台積")

    assert view.stock_lookup_results.count() == 4
    assert view.stock_lookup_results.currentIndex() == 0
    assert not view.stock_lookup_locate_button.isEnabled()
    labels = [
        view.stock_lookup_results.itemText(index)
        for index in range(1, view.stock_lookup_results.count())
    ]
    assert sum("2330｜台積電" in label for label in labels) == 2
    assert sum("1111｜台積電" in label for label in labels) == 1
    assert any("晶圓代工" in label for label in labels)

    view.shutdown()


def test_empty_and_unmatched_searches_are_non_actionable_and_codes_are_exact():
    app()
    view = IndustryThemeMapView()
    assert not view.stock_lookup_input.isEnabled()
    assert not view.stock_lookup_locate_button.isEnabled()
    assert "尚未載入" in view.stock_lookup_status_label.text()

    view.set_snapshot(_lookup_snapshot())
    assert view.stock_lookup_input.isEnabled()
    assert "完整四碼" in view.stock_lookup_status_label.text()

    view.stock_lookup_input.setText("233")
    assert view.stock_lookup_results.count() == 1
    assert "完整四碼" in view.stock_lookup_status_label.text()
    assert not view.stock_lookup_locate_button.isEnabled()

    view.stock_lookup_input.setText("9999")
    assert view.stock_lookup_results.count() == 1
    assert "沒有符合" in view.stock_lookup_status_label.text()
    assert not view.stock_lookup_locate_button.isEnabled()

    view.stock_lookup_input.clear()
    assert "請輸入" in view.stock_lookup_status_label.text()
    assert not view.stock_lookup_locate_button.isEnabled()
    view.shutdown()


def test_failed_snapshot_reload_clears_prior_lookup_and_selection(monkeypatch):
    application = app()
    view = IndustryThemeMapView()
    view.set_snapshot(_lookup_snapshot())
    view.stock_lookup_input.setText("2330")
    view.stock_lookup_results.setCurrentIndex(
        _result_index(view, "2330", "科技鏈", "AI")
    )

    def fail_read(_path: Path):
        raise ValueError("測試版本不可讀")

    monkeypatch.setattr(view_module, "read_theme_research_snapshot", fail_read)
    view.load_snapshot(Path("missing-theme-manifest.json"))
    assert view.snapshot is None
    assert view.stock_lookup_input.text() == ""
    assert view.stock_lookup_results.count() == 1
    assert not view.stock_lookup_locate_button.isEnabled()

    _wait_until(application, lambda: not view.is_busy(), timeout_ms=3000)
    assert view.snapshot is None
    assert "讀取失敗" in view.status_label.text()
    assert view.stock_lookup_results.currentData(Qt.ItemDataRole.UserRole) is None
    view.shutdown()


def test_replacement_cancels_old_lookup_and_shutdown_invalidates_results(monkeypatch):
    application = app()
    view = IndustryThemeMapView()
    original = _lookup_snapshot("a" * 64)
    replacement = _lookup_snapshot("b" * 64, revised=True)
    view.set_snapshot(original)
    view.stock_lookup_input.setText("2330")
    entered = threading.Event()
    release = threading.Event()

    def delayed_read(_path: Path):
        entered.set()
        assert release.wait(5)
        return original

    monkeypatch.setattr(view_module, "read_theme_research_snapshot", delayed_read)
    view.load_snapshot(Path("slow-theme-manifest.json"))
    assert entered.wait(2)
    assert view.is_busy()
    assert view.stock_lookup_input.text() == ""
    assert not view.stock_lookup_input.isEnabled()
    assert view.stock_lookup_results.count() == 1

    view.set_snapshot(replacement)
    assert view.snapshot is replacement
    assert view.is_busy()
    assert not view.stock_lookup_locate_button.isEnabled()
    release.set()
    _wait_until(application, lambda: not view.is_busy(), timeout_ms=3000)
    assert view.snapshot is replacement
    assert view.stock_lookup_input.isEnabled()
    assert view.stock_lookup_input.text() == ""
    assert "已載入本機版本" in view.stock_lookup_status_label.text()

    view.stock_lookup_input.setText("2330")
    current_index = _result_index(view, "2330", "新版鏈", "新版晶圓代工")
    view.stock_lookup_results.setItemData(
        current_index,
        (original.identity_sha256, "2330", "新版鏈", "新版晶圓代工"),
        Qt.ItemDataRole.UserRole,
    )
    view.stock_lookup_results.setCurrentIndex(current_index)
    view.scroll_area.ensureWidgetVisible(view.stock_lookup_locate_button)
    QTest.mouseClick(view.stock_lookup_locate_button, Qt.MouseButton.LeftButton)
    assert view.chain_filter.currentIndex() == 0
    assert view.theme_filter.currentIndex() == 0
    assert "其他版本" in view.stock_lookup_status_label.text()

    view.shutdown()
    assert view.snapshot is None
    assert not view.stock_lookup_input.isEnabled()
    assert not view.stock_lookup_results.isEnabled()
    assert not view.stock_lookup_locate_button.isEnabled()
    assert view.stock_lookup_input.text() == ""
    assert view.stock_lookup_results.count() == 1


def test_lookup_fields_shrink_and_remain_in_narrow_scrolling_page():
    application = app()
    view = IndustryThemeMapView()
    view.resize(420, 700)
    view.set_snapshot(_lookup_snapshot())
    view.show()
    _wait_until(
        application,
        lambda: view.stock_lookup_input.isVisible(),
        timeout_ms=1000,
    )

    assert view.stock_lookup_input.minimumWidth() == 0
    assert view.stock_lookup_results.minimumWidth() == 0
    assert view.stock_lookup_input.width() > 0
    assert view.stock_lookup_results.width() > 0
    assert view.stock_lookup_locate_button.width() > 0
    view.shutdown()
