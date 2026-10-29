"""產業與題材頁的本機版本呈現與使用者操作測試。"""

import os
import sys
import threading
import time
from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QGroupBox, QProgressBar, QPushButton

from app_module.theme_daily_service import (
    ThemeDailyReport,
    ThemeDailyRow,
    ThemeMetricCoverage,
)
from app_module.theme_research_snapshot import ThemeResearchSnapshot
from decision_module.industry_theme_map import ThemeMappingRow
from ui_qt.views import industry_theme_map_view as view_module
from ui_qt.views.industry_theme_map_view import IndustryThemeMapView
from ui_qt.widgets.observation_bar_delegate import OBSERVATION_DIRECTIONAL_ROLE


def app():
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication(sys.argv)
    return instance


def test_selected_theme_details_share_width_and_explicit_member_action():
    application = app()
    view = IndustryThemeMapView()
    view.resize(1280, 760)
    view.show()
    snapshot = _snapshot()
    view.set_snapshot(snapshot)
    view.chain_filter.setCurrentIndex(view.chain_filter.findData("科技鏈"))
    view.theme_filter.setCurrentIndex(view.theme_filter.findText("AI"))
    application.processEvents()
    assert view.theme_detail_splitter.orientation() == Qt.Orientation.Horizontal
    assert view._metric_card_columns == 2
    assert [row.count() for row in view.metrics_card_rows] == [2, 2, 2, 2, 1]
    assert "科技鏈／AI" in view.selected_theme_summary.text()
    assert "1 / 2 位成員" in view.selected_theme_summary.text()
    assert "2026-10-16" in view.selected_theme_summary.text()
    assert not view.open_member_button.isEnabled()
    view.member_table.setCurrentCell(1, 1)
    assert view.member_table.item(1, 3).toolTip() == view.member_table.item(1, 3).text()
    received = []
    view.stockSelected.connect(received.append)
    navigation = view.capture_selected_member_navigation("2317")
    view.open_member_button.click()
    assert received == ["2317"]
    assert view.capture_selected_member_navigation("2317") == navigation
    assert view.snapshot is snapshot
    view._busy = True
    view._update_controls()
    assert not view.open_member_button.isEnabled()
    view._busy = False
    view._update_controls()
    view.resize(1920, 1080)
    application.processEvents()
    assert view._metric_card_columns == 3
    assert [row.count() for row in view.metrics_card_rows] == [3, 3, 3, 0, 0]
    view.resize(800, 760)
    application.processEvents()
    assert view.theme_detail_splitter.orientation() == Qt.Orientation.Vertical
    view.clear_research()
    assert not view.open_member_button.isEnabled()
    assert "選擇題材" in view.selected_theme_summary.text()
    view.shutdown()
    view.close()


def test_classification_explorer_is_collapsed_and_focuses_exact_member_row():
    application = app()
    view = IndustryThemeMapView()
    view.show()
    view.resize(1280, 760)
    snapshot = _classification_snapshot()
    view.set_snapshot(snapshot)
    _select_theme(view, "科技鏈", "AI")
    application.processEvents()

    assert not view.classification_explorer_group.isVisible()
    assert not view.classification_explorer_toggle.isChecked()
    received = []
    view.stockSelected.connect(received.append)
    view.classification_explorer_toggle.click()
    application.processEvents()

    assert view.classification_explorer_group.isVisible()
    assert "產業鏈：科技鏈" in view.classification_hierarchy_label.text()
    assert "題材：AI" in view.classification_hierarchy_label.text()
    assert any("上游" in title for title in [
        group.title()
        for group in view.classification_explorer_group.findChildren(QGroupBox)
    ])
    assert any("下游" in title for title in [
        group.title()
        for group in view.classification_explorer_group.findChildren(QGroupBox)
    ])
    buttons = view.classification_explorer_group.findChildren(
        QPushButton, "industryThemeClassificationMemberButton"
    )
    assert len(buttons) == 2
    member_button = next(
        button for button in buttons
        if button.property("classificationStockId") == "2317"
    )
    assert "分配方法：未提供" in member_button.toolTip()
    assert "證據：未提供" in member_button.toolTip()
    assert "可得日期：2026-10-15" in member_button.toolTip()
    assert snapshot.identity_sha256 in member_button.toolTip()
    sourced_member_button = next(
        button for button in buttons
        if button.property("classificationStockId") == "2330"
    )
    assert "分配方法：公司主業" in sourced_member_button.toolTip()
    assert "來源：本機映射原列" in sourced_member_button.toolTip()
    assert "證據：保存分類證據" in sourced_member_button.toolTip()

    member_button.click()
    assert view.member_table.currentRow() == 1
    assert view.member_table.item(1, 0).text() == "2317"
    assert received == []
    assert view.snapshot is snapshot
    view.shutdown()
    view.close()


def test_classification_explorer_caps_display_and_clears_on_selection_or_snapshot_change():
    application = app()
    view = IndustryThemeMapView()
    view.show()
    snapshot = _classification_snapshot(member_count=35)
    view.set_snapshot(snapshot)
    _select_theme(view, "科技鏈", "AI")
    view.classification_explorer_toggle.click()
    application.processEvents()
    assert view.classification_members_layout.count() > 0

    buttons = view.classification_explorer_group.findChildren(
        QPushButton, "industryThemeClassificationMemberButton"
    )
    assert len(buttons) == 30
    assert "顯示 30 / 35 位" in view.classification_members_status.text()
    assert "其餘 5 位請在下方既有題材成員表查閱" in view.classification_members_status.text()
    assert view.member_table.rowCount() == 35
    assert view.member_page_status_label.text() == "顯示 1–35 / 35 位成員；第 1 / 1 頁"

    _select_theme(view, "金融鏈", "保險")
    application.processEvents()
    assert not view.classification_explorer_group.isVisible()
    assert not view.classification_explorer_toggle.isChecked()
    assert view.classification_members_layout.count() == 0

    view.set_snapshot(_classification_snapshot(identity="b" * 64))
    application.processEvents()
    assert not view.classification_explorer_group.isVisible()
    assert not view.classification_explorer_toggle.isChecked()
    assert view.classification_members_layout.count() == 0
    view.shutdown()
    view.close()


def test_classification_l1_summary_counts_missing_and_bounded_overflow_then_clears():
    application = app()
    view = IndustryThemeMapView()
    view.show()
    categories = (
        "電子業", "電子業", " 電子業", " 電子業",
        "電子業 ", "電子業 ", "金融保險業", "金融保險業",
        "未提供", "未提供", "未提供（來源原值）", "未提供（來源原值）",
        "來源：「測試分類」", "來源：「測試分類」",
        *(f"測試分類{index:02d}" for index in range(20)), "", " ", "\t",
    )
    view.set_snapshot(_classification_snapshot(
        member_count=len(categories), l1_categories=categories,
    ))
    _select_theme(view, "科技鏈", "AI")
    view.classification_explorer_toggle.click()
    application.processEvents()

    card = view.classification_explorer_group.findChild(
        QGroupBox, "industryThemeClassificationL1Summary"
    )
    assert card is not None
    assert "分類列數／本題材分類列總數" in card.title()
    dates = card.findChild(view_module.QLabel, "industryThemeClassificationL1Dates")
    assert "資料日 2026-10-16" in dates.text()
    assert "Mapping 日期 2026-10-15／2026-10-15" in dates.text()
    note = card.findChild(view_module.QLabel, "industryThemeClassificationL1Note")
    assert "不代表權重、供應關係或歷史 PIT" in note.text()
    bars = card.findChildren(QProgressBar, "industryThemeClassificationL1Bar")
    labels = card.findChildren(QPushButton, "industryThemeClassificationL1Category")
    assert len(bars) == 10  # 8 類、合併列、未提供
    assert len(labels) == 10
    labels_by_text = {label.text(): label for label in labels}
    labels_by_accessible_name = {
        label.accessibleName(): label for label in labels
    }
    assert "「電子業」" in labels_by_text
    assert "「來源：「測試分類」」" in labels_by_accessible_name
    assert "未提供（欄位空白）" in labels_by_text
    assert "「未提供」" in labels_by_accessible_name
    assert "「未提供（來源原值）」" in labels_by_accessible_name
    assert "其他（合併 19 個 L1 類別）" in labels_by_accessible_name
    assert labels_by_accessible_name["「電子業」"].maximumWidth() == 190
    assert labels_by_accessible_name["「電子業」"].toolTip().startswith(
        "來源原值：'電子業'"
    )
    assert labels_by_accessible_name["「來源：「測試分類」」"].toolTip().startswith(
        "來源原值：'來源：「測試分類」'"
    )
    total_rows = len(categories)
    assert f"來源原值：'電子業'；2 / {total_rows}" in next(
        bar.toolTip() for bar in bars if "來源原值：'電子業'" in bar.toolTip()
    )
    electronic_bar = next(
        bar for bar in bars if bar.accessibleName() == "「電子業」分類列數"
    )
    assert electronic_bar.value() == 2
    assert electronic_bar.maximum() == total_rows
    assert f"來源原值：' 電子業'；2 / {total_rows}" in next(
        bar.toolTip() for bar in bars if "來源原值：' 電子業'" in bar.toolTip()
    )
    assert f"來源原值：'電子業 '；2 / {total_rows}" in next(
        bar.toolTip() for bar in bars if "來源原值：'電子業 '" in bar.toolTip()
    )
    assert f"來源原值：'未提供'；2 / {total_rows}" in next(
        bar.toolTip() for bar in bars if "來源原值：'未提供'" in bar.toolTip()
    )
    assert f"來源原值：'未提供（來源原值）'；2 / {total_rows}" in next(
        bar.toolTip() for bar in bars
        if "來源原值：'未提供（來源原值）'" in bar.toolTip()
    )
    overflow_bar = next(
        bar for bar in bars if "合併其餘" in bar.toolTip()
    )
    assert overflow_bar.value() == 19
    assert overflow_bar.maximum() == total_rows
    overflow_tooltip = overflow_bar.toolTip()
    assert "逐類計數：" in overflow_tooltip
    assert "另有 7 個 L1 類別，請至下方完整成員表查看" in overflow_tooltip
    assert len(overflow_tooltip) < 650
    missing_tooltip = next(
        bar.toolTip() for bar in bars
        if bar.accessibleName() == "未提供（欄位空白）分類列數"
    )
    assert f"L1 產業欄位原值為空白：3 / {total_rows}" in missing_tooltip
    assert "'' 1 列" in missing_tooltip
    assert "'\\t' 1 列" in missing_tooltip
    assert "' ' 1 列" in missing_tooltip
    assert view.member_table.rowCount() == len(categories)

    category_counts = {}
    for category in categories:
        if category.strip():
            category_counts[category] = category_counts.get(category, 0) + 1
    omitted_categories = {
        category for category, _count in sorted(
            category_counts.items(), key=lambda item: (-item[1], item[0])
        )[8:]
    }
    overflow_selector = next(
        button for button in labels
        if button.accessibleName() == "其他（合併 19 個 L1 類別）"
    )
    overflow_selector.click()
    expected_overflow_ids = tuple(
        f"{1000 + index:04d}"
        for index, category in enumerate(categories)
        if category in omitted_categories
    )
    assert view._visible_member_stock_ids() == expected_overflow_ids
    assert view.member_table.rowCount() == len(expected_overflow_ids)
    assert "1–19 / 19 位符合成員（本題材 37 位）" in view.member_page_status_label.text()
    assert "目前篩選：其他（合併 19 個 L1 類別）；符合 19 / 本題材 37 位" in view.classification_members_status.text()

    missing_selector = next(
        button for button in labels
        if button.accessibleName() == "未提供（欄位空白）"
    )
    missing_selector.click()
    assert view._visible_member_stock_ids() == ("1034", "1035", "1036")
    assert view.member_table.rowCount() == 3
    view.classification_explorer_group.findChild(
        QPushButton, "industryThemeClassificationL1Reset"
    ).click()
    assert view._member_l1_filter_stock_ids is None
    assert view._visible_member_stock_ids() == tuple(
        f"{1000 + index:04d}" for index in range(len(categories))
    )
    assert view.member_table.rowCount() == len(categories)
    assert view.member_table.currentRow() == -1
    assert "顯示 30 / 37 位分類成員" in view.classification_members_status.text()

    view.classification_explorer_toggle.click()
    application.processEvents()
    assert view.classification_members_layout.count() == 0

    view.set_snapshot(_classification_snapshot(
        identity="a" * 64, member_count=2,
    ))
    _select_theme(view, "科技鏈", "AI")
    view.classification_explorer_toggle.click()
    application.processEvents()
    assert view.classification_members_layout.count() > 0
    current_snapshot = view.snapshot
    assert current_snapshot is not None
    selected_mapping = next(
        row for row in current_snapshot.mapping
        if row.chain_name == "科技鏈" and row.theme_name == "AI"
    )
    failed_snapshot = replace(
        current_snapshot, mapping=current_snapshot.mapping + (selected_mapping,)
    )
    view.set_snapshot(failed_snapshot)
    _select_theme(view, "科技鏈", "AI")
    assert view.theme_filter.currentIndex() > 0
    view.classification_explorer_toggle.click()
    application.processEvents()
    assert view.classification_members_layout.count() == 0
    assert "缺少可展開" in view.classification_members_status.text()
    view.shutdown()
    view.close()


def test_classification_l1_selectors_filter_exact_rows_reset_and_preserve_navigation(
    monkeypatch,
):
    application = app()
    view = IndustryThemeMapView()
    view.resize(1280, 760)
    view.show()
    categories = (
        "電子業", "電子業", " 電子業", "電子業 ", "電子業",
        "金融保險業", "金融保險業", "", " ",
    )
    snapshot = _classification_snapshot(
        member_count=len(categories), l1_categories=categories,
    )
    view.set_snapshot(snapshot)
    _select_theme(view, "科技鏈", "AI")
    view.classification_explorer_toggle.click()
    application.processEvents()
    card = view.classification_explorer_group.findChild(
        QGroupBox, "industryThemeClassificationL1Summary"
    )
    selectors = card.findChildren(
        QPushButton, "industryThemeClassificationL1Category"
    )
    by_accessible_name = {
        selector.accessibleName(): selector for selector in selectors
    }

    by_accessible_name["「電子業」"].click()
    assert view._visible_member_stock_ids() == ("1000", "1001", "1004")
    assert tuple(
        view.member_table.item(row, 0).text()
        for row in range(view.member_table.rowCount())
    ) == ("1000", "1001", "1004")
    assert "1–3 / 3 位符合成員（本題材 9 位）" in view.member_page_status_label.text()
    assert "目前篩選：「電子業」" in view.classification_members_status.text()
    assert snapshot.identity_sha256 in view.classification_members_status.text()
    view.member_table.setCurrentCell(1, 0)
    navigation = view.capture_selected_member_navigation("1001")
    assert navigation is not None
    assert navigation.origin_stock_code == "1001"
    assert navigation.origin_row_index == 1

    outside_filter_button = next(
        button for button in view.classification_explorer_group.findChildren(
            QPushButton, "industryThemeClassificationMemberButton"
        )
        if button.property("classificationStockId") == "1002"
    )
    outside_filter_button.click()
    assert view._member_l1_filter_stock_ids is None
    assert view.member_table.rowCount() == len(categories)
    assert view.member_table.item(view.member_table.currentRow(), 0).text() == "1002"
    navigation = view.capture_selected_member_navigation("1002")
    assert navigation is not None
    assert navigation.origin_row_index == 2

    by_accessible_name["「 電子業」"].click()
    assert view._visible_member_stock_ids() == ("1002",)
    assert view.member_table.item(0, 0).text() == "1002"
    by_accessible_name["「電子業 」"].click()
    assert view._visible_member_stock_ids() == ("1003",)
    assert view.member_table.item(0, 0).text() == "1003"

    by_accessible_name["未提供（欄位空白）"].click()
    assert view._visible_member_stock_ids() == ("1007", "1008")
    assert "未提供（欄位空白）" in view.member_page_status_label.text()
    reset = card.findChild(QPushButton, "industryThemeClassificationL1Reset")
    reset.click()
    assert view._member_l1_filter_stock_ids is None
    assert view.member_table.currentRow() == -1
    assert view.member_table.rowCount() == len(categories)
    assert "顯示 1–9 / 9 位成員" in view.member_page_status_label.text()
    assert not view.open_member_button.isEnabled()

    by_accessible_name["「電子業」"].click()
    _select_theme(view, "金融鏈", "保險")
    application.processEvents()
    assert view._member_l1_filter_stock_ids is None
    assert view._visible_member_stock_ids() == ("2881",)
    assert view.member_table.rowCount() == 1
    assert view.member_table.item(0, 0).text() == "2881"

    _select_theme(view, "科技鏈", "AI")
    view.classification_explorer_toggle.click()
    application.processEvents()
    current_card = view.classification_members_layout.itemAt(0).widget()
    assert current_card.objectName() == "industryThemeClassificationL1Summary"
    current_card.findChildren(
        QPushButton, "industryThemeClassificationL1Category"
    )[0].click()
    assert view._member_l1_filter_stock_ids is not None
    replacement = _classification_snapshot(identity="f" * 64, member_count=2)
    view.set_snapshot(replacement)
    application.processEvents()
    assert view._member_l1_filter_stock_ids is None
    assert view.member_table.rowCount() == 0

    _select_theme(view, "科技鏈", "AI")
    view.classification_explorer_toggle.click()
    application.processEvents()
    replacement_card = view.classification_members_layout.itemAt(0).widget()
    assert replacement_card.objectName() == "industryThemeClassificationL1Summary"
    replacement_button = replacement_card.findChildren(
        QPushButton, "industryThemeClassificationL1Category"
    )[0]
    assert replacement_button.isEnabled()
    replacement_button.click()
    assert view._member_l1_filter_stock_ids is not None

    def reject_presentation(*_args, **_kwargs):
        raise ValueError("合成來源版本拒絕呈現")

    monkeypatch.setattr(
        view_module, "build_theme_research_presentation", reject_presentation
    )
    view.set_snapshot(_classification_snapshot(identity="a" * 64, member_count=2))
    assert view.snapshot is None
    assert view._member_l1_filter_stock_ids is None
    assert view.member_table.rowCount() == 0
    assert view.classification_members_layout.count() == 0
    view.shutdown()
    view.close()


def test_member_table_pages_are_bounded_and_clear_selection_and_tooltip():
    application = app()
    view = IndustryThemeMapView()
    view.show()
    view.set_snapshot(_classification_snapshot(member_count=123))
    _select_theme(view, "科技鏈", "AI")
    application.processEvents()

    assert view.member_table.rowCount() == 50
    assert view.member_table.item(0, 0).text() == "1000"
    assert view.member_page_status_label.text() == "顯示 1–50 / 123 位成員；第 1 / 3 頁"
    assert not view.member_page_previous_button.isEnabled()
    assert view.member_page_next_button.isEnabled()
    view._change_member_page(-1)
    assert view._member_page_index == 0

    view.member_table.setCurrentCell(0, 0)
    assert view.open_member_button.isEnabled()
    view.member_table.setToolTip("舊頁提示")
    view.member_page_next_button.click()
    application.processEvents()

    assert view._member_page_index == 1
    assert view.member_table.rowCount() == 50
    assert view.member_table.item(0, 0).text() == "1050"
    assert view.member_page_status_label.text() == "顯示 51–100 / 123 位成員；第 2 / 3 頁"
    assert view.member_table.currentRow() == -1
    assert not view.open_member_button.isEnabled()
    assert view.member_selection_label.text() == "先選取一檔成員股票。"
    assert view.member_table.toolTip() == ""

    view.member_page_next_button.click()
    application.processEvents()
    assert view._member_page_index == 2
    assert view.member_table.rowCount() == 23
    assert view.member_table.item(0, 0).text() == "1100"
    assert view.member_table.item(22, 0).text() == "1122"
    assert view.member_page_status_label.text() == "顯示 101–123 / 123 位成員；第 3 / 3 頁"
    assert not view.member_page_next_button.isEnabled()
    view.member_page_next_button.click()
    assert view._member_page_index == 2
    view.member_page_previous_button.click()
    assert view._member_page_index == 1
    assert view.member_table.item(0, 0).text() == "1050"

    view.set_snapshot(_classification_snapshot(identity="f" * 64, member_count=123))
    _select_theme(view, "科技鏈", "AI")
    assert view._member_page_index == 0
    assert view.member_table.rowCount() == 50
    assert view.member_table.item(0, 0).text() == "1000"
    assert view.member_table.currentRow() == -1
    assert not view.open_member_button.isEnabled()
    view.shutdown()
    view.close()


def test_classification_member_button_pages_to_exact_same_snapshot_member():
    application = app()
    view = IndustryThemeMapView()
    view.show()
    base = _classification_snapshot(member_count=123)
    daily_row = replace(base.report.rows[0], stock_ids=tuple(reversed(base.report.rows[0].stock_ids)))
    report = replace(base.report, rows=(daily_row, *base.report.rows[1:]))
    snapshot = ThemeResearchSnapshot(base.identity_sha256, report, base.mapping)
    view.set_snapshot(snapshot)
    _select_theme(view, "科技鏈", "AI")
    view.classification_explorer_toggle.click()
    application.processEvents()

    button = next(
        candidate for candidate in view.classification_explorer_group.findChildren(
            QPushButton, "industryThemeClassificationMemberButton"
        )
        if candidate.property("classificationStockId") == "1000"
    )
    button.click()
    application.processEvents()

    assert view._member_page_index == 2
    assert view.member_page_status_label.text() == "顯示 101–123 / 123 位成員；第 3 / 3 頁"
    assert view.member_table.currentRow() == 22
    assert view.member_table.item(22, 0).text() == "1000"
    navigation = view.capture_selected_member_navigation("1000")
    assert navigation is not None
    assert navigation.snapshot_identity == snapshot.identity_sha256
    assert navigation.theme_key == ("科技鏈", "AI")
    assert navigation.origin_stock_code == "1000"
    assert navigation.origin_row_index == 122
    view.shutdown()
    view.close()


def test_theme_overlap_neighborhood_is_collapsed_bounded_and_opens_exact_theme(monkeypatch):
    application = app()
    real_builder = view_module.build_theme_overlap_presentation
    calls = []

    def build_spy(*args):
        calls.append(args)
        return real_builder(*args)

    monkeypatch.setattr(view_module, "build_theme_overlap_presentation", build_spy)
    view = IndustryThemeMapView()
    view.resize(1280, 760)
    view.show()
    snapshot = _overlap_snapshot(neighbor_count=10)
    view.set_snapshot(snapshot)
    _select_theme(view, "科技鏈", "AI")
    assert calls == []
    application.processEvents()

    assert not view.theme_overlap_group.isVisible()
    assert not view.theme_overlap_toggle.isChecked()
    view.theme_overlap_toggle.click()
    assert len(calls) == 1
    application.processEvents()
    buttons = view.theme_overlap_group.findChildren(
        QPushButton, "industryThemeOverlapNeighborButton"
    )
    assert len(buttons) == 8
    assert "鄰居共 10 個，省略 2 個" in view.theme_overlap_context.text()
    assert "資料日 2026-10-16" in view.theme_overlap_context.text()
    assert "映射快照日 2026-10-15" in view.theme_overlap_context.text()
    assert snapshot.identity_sha256 in view.theme_overlap_context.text()
    assert "僅靜態分類重疊，非供應鏈、因果、歷史 PIT" in view.theme_overlap_context.text()
    assert "2330 台積電" in buttons[0].toolTip()
    bar = buttons[0].parentWidget().findChild(
        QProgressBar, "industryThemeOverlapProgressBar"
    )
    assert bar is not None
    assert bar.value() == 2
    assert bar.maximum() == 2
    assert bar.format() == "共用 %v / %m 檔"
    assert "所選題材 科技鏈／AI 原分類列" in buttons[0].toolTip()
    assert "股票名稱：台積電" in buttons[0].toolTip()
    assert "來源：本機映射原列" in buttons[0].toolTip()
    assert "鄰居題材 鄰域鏈 00／共用題材 00 原分類列" in buttons[0].toolTip()
    assert "股票名稱：鄰居映射名稱 00 2330" in buttons[0].toolTip()
    assert "共用股票 2317" in buttons[0].toolTip()
    assert "股票名稱：鄰居映射名稱 00 2317" in buttons[0].toolTip()
    assert "來源：鄰居來源 00" in buttons[0].toolTip()
    assert "分配方法：鄰居補充分類" in buttons[0].toolTip()
    assert "PIT 模式：鄰居靜態模式" in buttons[0].toolTip()
    assert "證據註記：鄰居原始證據 00" in buttons[0].toolTip()
    assert "快照日：2026-10-15" in buttons[0].toolTip()
    assert "可得日：2026-10-15" in buttons[0].toolTip()

    buttons[0].setProperty("themeSnapshotIdentity", "d" * 64)
    buttons[0].click()
    assert view.chain_filter.currentData() == "科技鏈"
    buttons[0].setProperty("themeSnapshotIdentity", snapshot.identity_sha256)
    buttons[0].setProperty("themeSelectedKey", ("金融鏈", "保險"))
    buttons[0].click()
    assert view.theme_filter.currentText() == "AI"
    buttons[0].setProperty("themeSelectedKey", ("科技鏈", "AI"))
    buttons[0].click()
    application.processEvents()
    assert view.chain_filter.currentData() == "鄰域鏈 00"
    assert view.theme_filter.currentText() == "共用題材 00"
    assert "鄰域鏈 00／共用題材 00" in view.selected_theme_summary.text()
    assert view.selected_theme_summary.visibleRegion().boundingRect().height() > 0
    assert view.snapshot is snapshot
    view.shutdown()
    view.close()


def test_theme_overlap_empty_state_and_stale_button_guards_and_clear():
    application = app()
    view = IndustryThemeMapView()
    view.show()
    view.set_snapshot(_classification_snapshot())
    _select_theme(view, "科技鏈", "AI")
    view.theme_overlap_toggle.click()
    assert "沒有同版本共用成員題材" in view.theme_overlap_summary.text()

    view.set_snapshot(_overlap_snapshot(neighbor_count=2))
    _select_theme(view, "科技鏈", "AI")
    view.theme_overlap_toggle.click()
    stale = view._theme_overlap_buttons[0]
    _select_theme(view, "金融鏈", "保險")
    assert not view.theme_overlap_group.isVisible()
    assert not view.theme_overlap_toggle.isChecked()
    assert view._theme_overlap_buttons == []
    stale.setEnabled(True)
    stale.click()
    assert view.chain_filter.currentData() == "金融鏈"
    assert view.theme_filter.currentText() == "保險"

    _select_theme(view, "科技鏈", "AI")
    view.theme_overlap_toggle.click()
    stale = view._theme_overlap_buttons[0]
    view._busy = True
    stale.setEnabled(True)
    stale.click()
    assert view.chain_filter.currentData() == "科技鏈"
    view._busy = False
    view.clear_research()
    assert not view.theme_overlap_group.isVisible()
    assert not view.theme_overlap_toggle.isChecked()
    assert view._theme_overlap_buttons == []
    stale.setEnabled(True)
    stale.click()
    assert view.snapshot is None
    view.shutdown()
    view.close()


def _wait_until(application, predicate, *, timeout_ms: int) -> None:
    deadline = time.monotonic() + timeout_ms / 1000
    while True:
        application.processEvents()
        if predicate():
            application.processEvents()
            return
        if time.monotonic() >= deadline:
            raise AssertionError("Qt 狀態未在固定期限內完成")
        QTest.qWait(10)


def _daily_row(
    chain: str,
    theme: str,
    stock_ids: tuple[str, ...],
    *,
    returns: Decimal | None,
    turnover: Decimal | None,
    volume: Decimal | None,
    flow_shares: int | None,
    flow_amount: Decimal | None,
    coverage: ThemeMetricCoverage,
) -> ThemeDailyRow:
    return ThemeDailyRow(
        chain_name=chain,
        theme_name=theme,
        stock_ids=stock_ids,
        mean_return_pct=returns,
        turnover_twd=turnover,
        volume_multiple_5d=volume,
        institutional_net_shares=flow_shares,
        institutional_net_turnover_twd=flow_amount,
        up_count=1 if returns is not None and returns > 0 else 0,
        down_count=1 if returns is not None and returns < 0 else 0,
        flat_count=0,
        institutional_buy_count=1 if flow_shares is not None and flow_shares > 0 else 0,
        institutional_sell_count=1 if flow_shares is not None and flow_shares < 0 else 0,
        institutional_flat_count=0,
        advancing_ratio=Decimal("0.5") if returns is not None and returns > 0 else None,
        institutional_buy_ratio=(
            Decimal("1") if flow_shares is not None and flow_shares > 0 else None
        ),
        coverage=coverage,
        source_ids=("local-test-source",),
    )


def _snapshot(identity: str = "a" * 64) -> ThemeResearchSnapshot:
    rows = (
        _daily_row(
            "科技鏈",
            "AI",
            ("2330", "2317"),
            returns=Decimal("1.2300"),
            turnover=Decimal("125.00"),
            volume=None,
            flow_shares=8,
            flow_amount=None,
            coverage=ThemeMetricCoverage(2, 1, 2, 0, 1, 0),
        ),
        _daily_row(
            "金融鏈",
            "保險",
            ("2881",),
            returns=None,
            turnover=None,
            volume=None,
            flow_shares=None,
            flow_amount=None,
            coverage=ThemeMetricCoverage(1, 0, 0, 0, 0, 0),
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
    mapping = tuple(
        SimpleNamespace(
            stock_id=stock_id,
            stock_name={
                "2330": "台積電",
                "2317": "",
                "2881": "富邦金",
            }[stock_id],
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


def _classification_snapshot(
    identity: str = "e" * 64,
    *,
    member_count: int = 2,
    l1_categories: tuple[str, ...] | None = None,
) -> ThemeResearchSnapshot:
    """使用實際 ThemeMappingRow 驗證展開時的來源分類契約。"""
    if l1_categories is not None and len(l1_categories) != member_count:
        raise ValueError("l1_categories 必須與 member_count 相同")
    base = _snapshot(identity)
    stock_ids = (
        ("2330", "2317") if member_count == 2
        else tuple(f"{index:04d}" for index in range(1000, 1000 + member_count))
    )
    coverage = ThemeMetricCoverage(member_count, member_count, member_count, 0, 0, 0)
    mapping = tuple(
        ThemeMappingRow(
            snapshot_date="2026-10-15",
            available_date="2026-10-15",
            stock_id=stock_id,
            stock_name=(
                {"2330": "台積電", "2317": "鴻海"}.get(stock_id, f"測試公司{stock_id}")
            ),
            market_type="上市",
            l1_industry_category=(
                l1_categories[member_index] if l1_categories is not None else "電子業"
            ),
            chain_name="科技鏈",
            chain_tier="上游" if member_index % 2 == 0 else "下游",
            theme_name="AI",
            is_primary=member_index == 0,
            assignment_method="" if stock_id == "2317" else "公司主業",
            source_name="" if stock_id == "2317" else "本機映射原列",
            source_tier="" if stock_id == "2317" else "來源一級",
            pit_mode="" if stock_id == "2317" else "as_of_snapshot",
            evidence_note="" if stock_id == "2317" else "保存分類證據",
        )
        for member_index, stock_id in enumerate(stock_ids)
    ) + (
        ThemeMappingRow(
            snapshot_date="2026-10-15",
            available_date="2026-10-15",
            stock_id="2881",
            stock_name="富邦金",
            market_type="上市",
            l1_industry_category="金融保險業",
            chain_name="金融鏈",
            chain_tier="整合",
            theme_name="保險",
            is_primary=True,
            assignment_method="公司主業",
            source_name="本機映射原列",
            source_tier="來源一級",
            pit_mode="as_of_snapshot",
            evidence_note="保存分類證據",
        ),
    )
    selected_row = _daily_row(
        "科技鏈",
        "AI",
        stock_ids,
        returns=Decimal("1.2300"),
        turnover=Decimal("125.00"),
        volume=None,
        flow_shares=8,
        flow_amount=None,
        coverage=coverage,
    )
    report = replace(base.report, rows=(selected_row, base.report.rows[1]))
    return ThemeResearchSnapshot(identity, report, mapping)


def _overlap_snapshot(
    identity: str = "c" * 64,
    *,
    neighbor_count: int,
) -> ThemeResearchSnapshot:
    """在現有 typed 分類 fixture 增加多條共享 2330 的獨立題材。"""
    base = _classification_snapshot(identity)
    neighbor_rows = tuple(
        _daily_row(
            f"鄰域鏈 {index:02d}",
            f"共用題材 {index:02d}",
            ("2330", "2317") if index == 0 else ("2330",),
            returns=None,
            turnover=None,
            volume=None,
            flow_shares=None,
            flow_amount=None,
            coverage=ThemeMetricCoverage(2 if index == 0 else 1, 0, 0, 0, 0, 0),
        )
        for index in range(neighbor_count)
    )
    neighbor_mappings = tuple(
        replace(
            next(row for row in base.mapping if row.stock_id == stock_id),
            chain_name=f"鄰域鏈 {index:02d}",
            theme_name=f"共用題材 {index:02d}",
            stock_name=f"鄰居映射名稱 {index:02d} {stock_id}",
            source_name=f"鄰居來源 {index:02d}",
            source_tier=f"鄰居來源層級 {index:02d}",
            assignment_method="鄰居補充分類",
            pit_mode="鄰居靜態模式",
            evidence_note=f"鄰居原始證據 {index:02d}",
        )
        for index in range(neighbor_count)
        for stock_id in (("2330", "2317") if index == 0 else ("2330",))
    )
    return ThemeResearchSnapshot(
        identity,
        replace(base.report, rows=(*base.report.rows, *neighbor_rows)),
        (*base.mapping, *neighbor_mappings),
    )


def _snapshot_with_zero_and_negative_values() -> ThemeResearchSnapshot:
    complete = ThemeMetricCoverage(1, 1, 1, 1, 1, 1)
    rows = (
        _daily_row(
            "科技鏈",
            "零值題材",
            ("0001",),
            returns=Decimal("0.00"),
            turnover=Decimal("0.00"),
            volume=Decimal("0.00"),
            flow_shares=0,
            flow_amount=Decimal("0.00"),
            coverage=complete,
        ),
        _daily_row(
            "能源鏈",
            "負值題材",
            ("0002",),
            returns=Decimal("-1.50"),
            turnover=Decimal("0.00"),
            volume=Decimal("0.00"),
            flow_shares=-4,
            flow_amount=Decimal("-500.00"),
            coverage=complete,
        ),
    )
    report = ThemeDailyReport(
        data_date=date(2026, 10, 16),
        known_at=datetime(2026, 10, 17, 2, 0, tzinfo=timezone.utc),
        mapping_snapshot_date="2026-10-15",
        mapping_available_date="2026-10-15",
        status="current_research",
        rows=rows,
        warnings=(),
    )
    mapping = tuple(
        SimpleNamespace(
            stock_id=stock_id,
            stock_name=f"測試公司{stock_id}",
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
    return ThemeResearchSnapshot("c" * 64, report, mapping)


def _snapshot_with_directional_rankings(
    identity: str = "d" * 64,
    *,
    theme_prefix: str = "題材",
) -> ThemeResearchSnapshot:
    complete = ThemeMetricCoverage(1, 1, 1, 1, 1, 1)
    specifications = (
        ("A", Decimal("-3.00"), Decimal("70.00"), Decimal("0.00"), -7),
        ("B", Decimal("-2.00"), Decimal("10.00"), Decimal("6.00"), -2),
        ("C", Decimal("-1.00"), Decimal("60.00"), Decimal("5.00"), -1),
        ("D", Decimal("0.00"), Decimal("20.00"), Decimal("4.00"), 0),
        ("E", Decimal("1.00"), Decimal("50.00"), Decimal("3.00"), 1),
        ("F", Decimal("2.00"), Decimal("30.00"), Decimal("2.00"), 2),
        ("G", Decimal("3.00"), Decimal("40.00"), Decimal("1.00"), 7),
    )
    rows = []
    mapping = []
    for index, (suffix, returns, turnover, volume, flow_shares) in enumerate(
        specifications,
        start=1,
    ):
        chain_name = f"鏈{suffix}"
        theme_name = f"{theme_prefix}{suffix}"
        stock_id = f"8{index:03d}"
        rows.append(
            _daily_row(
                chain_name,
                theme_name,
                (stock_id,),
                returns=returns,
                turnover=turnover,
                volume=volume,
                flow_shares=flow_shares,
                flow_amount=Decimal(f"{flow_shares * 100}.00"),
                coverage=complete,
            )
        )
        mapping.append(
            SimpleNamespace(
                stock_id=stock_id,
                stock_name=f"測試公司{stock_id}",
                chain_name=chain_name,
                theme_name=theme_name,
                chain_tier="核心鏈",
                assignment_method="公司主業",
                source_name="本機分類來源",
                source_tier="來源一級",
                evidence_note="測試快照映射列",
            )
        )

    rows.extend((
        _daily_row(
            "部分鏈",
            "部分覆蓋極端值",
            ("8991", "8992"),
            returns=Decimal("-999.00"),
            turnover=Decimal("999999.00"),
            volume=Decimal("999.00"),
            flow_shares=999,
            flow_amount=Decimal("999999.00"),
            coverage=ThemeMetricCoverage(2, 1, 1, 1, 1, 1),
        ),
        _daily_row(
            "缺值鏈",
            "未提供題材",
            ("8993", "8994"),
            returns=None,
            turnover=None,
            volume=None,
            flow_shares=None,
            flow_amount=None,
            coverage=ThemeMetricCoverage(2, 0, 0, 0, 0, 0),
        ),
    ))
    for chain_name, theme_name, stock_ids in (
        ("部分鏈", "部分覆蓋極端值", ("8991", "8992")),
        ("缺值鏈", "未提供題材", ("8993", "8994")),
    ):
        mapping.extend(
            SimpleNamespace(
                stock_id=stock_id,
                stock_name=f"測試公司{stock_id}",
                chain_name=chain_name,
                theme_name=theme_name,
                chain_tier="核心鏈",
                assignment_method="公司主業",
                source_name="本機分類來源",
                source_tier="來源一級",
                evidence_note="測試快照映射列",
            )
            for stock_id in stock_ids
        )

    report = ThemeDailyReport(
        data_date=date(2026, 10, 16),
        known_at=datetime(2026, 10, 17, 2, 0, tzinfo=timezone.utc),
        mapping_snapshot_date="2026-10-15",
        mapping_available_date="2026-10-15",
        status="current_research",
        rows=tuple(rows),
        warnings=(),
    )
    return ThemeResearchSnapshot(identity, report, tuple(mapping))


def _snapshot_with_duplicate_theme_names() -> ThemeResearchSnapshot:
    """兩鏈使用同名題材，但保留各自原值與映射身份。"""
    baseline = _snapshot_with_directional_rankings(identity="9" * 64)
    duplicated_theme = "同名觀察題材"
    duplicated_keys = {("鏈A", "題材A"), ("鏈B", "題材B")}
    rows = tuple(
        replace(row, theme_name=duplicated_theme)
        if (row.chain_name, row.theme_name) in duplicated_keys else row
        for row in baseline.report.rows
    )
    mapping = tuple(
        SimpleNamespace(**{
            **vars(row),
            "theme_name": duplicated_theme,
        }) if (row.chain_name, row.theme_name) in duplicated_keys else row
        for row in baseline.mapping
    )
    return ThemeResearchSnapshot(
        baseline.identity_sha256,
        replace(baseline.report, rows=rows),
        mapping,
    )


def _snapshot_with_large_theme_search_catalog() -> ThemeResearchSnapshot:
    base = _snapshot_with_duplicate_theme_names()
    rows = list(base.report.rows)
    mapping = list(base.mapping)
    complete = ThemeMetricCoverage(1, 1, 1, 1, 1, 1)
    for index in range(81):
        chain_name = f"大量鏈{index:02d}"
        theme_name = f"大量題材{index:02d}"
        stock_id = f"9{index:03d}"
        rows.append(_daily_row(
            chain_name,
            theme_name,
            (stock_id,),
            returns=Decimal(index),
            turnover=Decimal(index + 1),
            volume=Decimal(index + 1),
            flow_shares=index,
            flow_amount=Decimal(index + 1),
            coverage=complete,
        ))
        mapping.append(SimpleNamespace(
            stock_id=stock_id,
            stock_name=f"測試公司{stock_id}",
            chain_name=chain_name,
            theme_name=theme_name,
            chain_tier="核心鏈",
            assignment_method="公司主業",
            source_name="本機分類來源",
            source_tier="來源一級",
            evidence_note="搜尋目錄合成列",
        ))
    return ThemeResearchSnapshot(
        base.identity_sha256,
        replace(base.report, rows=tuple(rows)),
        tuple(mapping),
    )


def _select_theme(view: IndustryThemeMapView, chain: str, theme: str) -> None:
    view.chain_filter.setCurrentIndex(view.chain_filter.findData(chain))
    view.theme_filter.setCurrentIndex(view.theme_filter.findText(theme))


def _metric_row(view: IndustryThemeMapView, label: str) -> int:
    for row_index in range(view.metrics_table.rowCount()):
        item = view.metrics_table.item(row_index, 0)
        if item is not None and item.text() == label:
            return row_index
    raise AssertionError(f"找不到指標列：{label}")


def _ranked_theme_names(view: IndustryThemeMapView) -> list[str]:
    return [
        view.ranking_table.item(row, 2).text()
        for row in range(view.ranking_table.rowCount())
    ]


def test_snapshot_render_keeps_decimal_and_separate_missing_coverage():
    app()
    view = IndustryThemeMapView()
    view.set_snapshot(_snapshot())

    assert "資料日：2026-10-16" in view.summary_label.text()
    assert "產業鏈：2　｜　題材：2　｜　不重複成員：3" in view.summary_label.text()
    assert "不代表官方來源接受或歷史 PIT" in view.summary_label.text()

    _select_theme(view, "科技鏈", "AI")
    returns_row = _metric_row(view, "平均日漲跌幅")
    turnover_row = _metric_row(view, "價格成交金額（TWD）")
    volume_row = _metric_row(view, "成交量五日倍數")
    flow_row = _metric_row(view, "法人淨股數（已覆蓋成員合計）")
    flow_amount_row = _metric_row(view, "法人流向淨金額（TWD）")
    advancing_row = _metric_row(view, "上漲比例")
    institutional_ratio_row = _metric_row(view, "法人買超比例（已覆蓋成員）")

    assert view.metrics_table.item(returns_row, 1).text() == "1.23 %"
    assert view.metrics_table.item(returns_row, 1).toolTip() == "1.2300 %"
    assert view.metrics_table.item(returns_row, 2).text() == "1 / 2 位成員"
    assert view.metrics_table.item(turnover_row, 1).text() == "125.00"
    assert view.metrics_table.item(turnover_row, 1).toolTip() == "125.00"
    assert view.metrics_table.item(turnover_row, 2).text() == "2 / 2 位成員"
    assert view.metrics_table.item(volume_row, 1).text() == "未提供"
    assert view.metrics_table.item(volume_row, 2).text() == "0 / 2 位成員"
    assert view.metrics_table.item(flow_row, 1).text() == "8"
    assert view.metrics_table.item(flow_row, 2).text() == "1 / 2 位成員"
    assert view.metrics_table.item(flow_amount_row, 1).text() == "未提供"
    assert view.metrics_table.item(flow_amount_row, 2).text() == "0 / 2 位成員"
    assert view.metrics_table.item(advancing_row, 1).text() == "50.00%"
    assert view.metrics_table.item(advancing_row, 1).toolTip() == "0.5"
    assert view.metrics_table.item(institutional_ratio_row, 1).text() == "100.00%"
    assert view.metrics_table.item(institutional_ratio_row, 1).toolTip() == "1"
    assert view.metrics_table.rowCount() == 9
    assert view.metrics_table.columnCount() == 3
    assert not view.metrics_cards_group.isHidden()
    assert len(view.metrics_card_labels) == 9
    for row_index, (label, card_value, card_coverage) in enumerate(view.metrics_card_labels):
        assert label.text() == view.metrics_table.item(row_index, 0).text()
        assert card_value.text() == view.metrics_table.item(row_index, 1).text()
        assert card_coverage.text() == f"覆蓋：{view.metrics_table.item(row_index, 2).text()}"
        assert card_value.toolTip() == view.metrics_table.item(row_index, 1).toolTip()
    assert view.metrics_card_labels[2][1].text() == "未提供"
    assert view.metrics_card_labels[2][2].text() == "覆蓋：0 / 2 位成員"
    assert [
        view.member_table.item(row, 0).text()
        for row in range(view.member_table.rowCount())
    ] == ["2330", "2317"]
    assert view.member_table.item(0, 1).text() == "台積電"
    assert view.member_table.item(0, 2).text() == "核心鏈"
    assert view.member_table.item(0, 3).text() == (
        "公司主業；本機分類來源；來源一級；依保存映射列"
    )
    assert view.member_table.item(1, 1).text() == "未提供"


def test_chain_theme_filters_and_member_double_click_emit_stock_id():
    application = app()
    view = IndustryThemeMapView()
    view.resize(1100, 760)
    view.set_snapshot(_snapshot())

    _select_theme(view, "金融鏈", "保險")
    assert view.member_table.rowCount() == 1
    assert view.member_table.item(0, 0).text() == "2881"

    _select_theme(view, "科技鏈", "AI")
    assert view.member_table.rowCount() == 2
    assert view.metrics_table.item(_metric_row(view, "平均日漲跌幅"), 1).text() == "1.23 %"

    assert view.member_view_combo.currentData() == "cards"
    assert not view.member_cards_widget.isHidden()
    assert view.member_table.isHidden()
    assert set(view._member_card_buttons) == {"2330", "2317"}
    view.show()
    application.processEvents()
    view.member_view_combo.setCurrentIndex(view.member_view_combo.findData("table"))
    application.processEvents()
    selected_stock_ids = []
    view.stockSelected.connect(selected_stock_ids.append)
    item = view.member_table.item(0, 1)
    # 指標卡展開後，分割區可能高於外層 viewport；把實際目標列捲到可視範圍。
    view.scroll_area.ensureWidgetVisible(view.member_table, 0, 0)
    view.member_table.scrollToItem(item)
    application.processEvents()
    item_position = view.member_table.visualItemRect(item).center()
    member_viewport = view.member_table.viewport()
    outer_position = view.scroll_area.viewport().mapFromGlobal(
        member_viewport.mapToGlobal(item_position)
    )
    outer_scroll = view.scroll_area.verticalScrollBar()
    outer_scroll.setValue(outer_scroll.value() + outer_position.y() - 60)
    application.processEvents()
    item_position = view.member_table.visualItemRect(item).center()
    assert member_viewport.rect().contains(item_position)
    assert member_viewport.visibleRegion().contains(item_position)
    outer_position = view.scroll_area.viewport().mapFromGlobal(
        member_viewport.mapToGlobal(item_position)
    )
    assert view.scroll_area.viewport().rect().contains(outer_position)
    # 外層viewport被content子widget覆蓋，visibleRegion會排除子widget；
    # 以實際裁切範圍及目標viewport可見性核對滑鼠位置。
    assert view.scroll_area.viewport().isVisible()
    QTest.mouseClick(
        member_viewport,
        Qt.MouseButton.LeftButton,
        pos=item_position,
    )
    QTest.qWait(50)
    QTest.mouseDClick(
        member_viewport,
        Qt.MouseButton.LeftButton,
        pos=item_position,
    )
    application.processEvents()
    assert selected_stock_ids == ["2330"]


def test_failed_reload_clears_old_snapshot_and_disables_member_actions(monkeypatch):
    application = app()
    view = IndustryThemeMapView()
    initial_snapshot = _snapshot()
    events = []
    view.snapshotChanged.connect(events.append)
    view.set_snapshot(initial_snapshot)
    _select_theme(view, "科技鏈", "AI")
    assert view.member_table.rowCount() == 2
    view.ranking_type_combo.setCurrentIndex(
        view.ranking_type_combo.findData("turnover")
    )
    view.sorting_direction_combo.setCurrentIndex(
        view.sorting_direction_combo.findData(True)
    )
    assert view.ranking_table.rowCount() == 1
    assert view.ranking_table.item(0, 2).text() == "AI"

    def fail_read(_path: Path):
        raise ValueError("無法讀取測試版本")

    monkeypatch.setattr(view_module, "read_theme_research_snapshot", fail_read)
    view.load_snapshot(Path("missing-manifest.json"))

    assert view.snapshot is None
    assert view.member_table.rowCount() == 0
    assert view.ranking_table.rowCount() == 0
    assert not view.sorting_direction_combo.isEnabled()
    assert not view.member_table.isEnabled()
    assert events == [initial_snapshot, None]
    _wait_until(application, lambda: not view.is_busy(), timeout_ms=3000)
    assert view.snapshot is None
    assert view.member_table.rowCount() == 0
    assert view.ranking_table.rowCount() == 0
    assert "讀取失敗" in view.status_label.text()
    assert "2026-10-16" not in view.overview_label.text()
    assert events == [initial_snapshot, None, None]


def test_two_version_comparison_reads_explicit_files_and_shows_zero_missing_and_partial(monkeypatch):
    application = app()
    view = IndustryThemeMapView()
    view.set_snapshot(_snapshot("f" * 64))
    assert view.comparison_group.isHidden()
    assert all(bar.isHidden() for bar in view.comparison_coverage_bars)
    view.comparison_toggle.click()
    assert not view.comparison_group.isHidden()
    first = _snapshot_with_zero_and_negative_values()
    missing = _snapshot("d" * 64)
    partial_base = _snapshot()
    partial = ThemeResearchSnapshot(
        "e" * 64,
        replace(partial_base.report, data_date=date(2026, 10, 20)),
        partial_base.mapping,
    )
    paths = (Path("first.json"), Path("second.json"))
    selected = iter(((str(paths[0]), ""), (str(paths[1]), "")))
    monkeypatch.setattr(
        view_module.QFileDialog, "getOpenFileName", lambda *_args, **_kwargs: next(selected),
    )
    read_paths = []
    snapshots = {paths[0]: first, paths[1]: missing}

    def read_snapshot(path: Path):
        read_paths.append(path)
        return snapshots[path]

    monkeypatch.setattr(view_module, "read_theme_research_snapshot", read_snapshot)
    view._choose_comparison_snapshots()
    _wait_until(application, lambda: view._comparison_snapshots is not None, timeout_ms=3000)
    assert read_paths == list(paths)
    assert view.comparison_chain_filter.isEnabled()
    view.comparison_chain_filter.setCurrentIndex(
        view.comparison_chain_filter.findData("科技鏈")
    )
    view.comparison_theme_filter.setCurrentIndex(
        view.comparison_theme_filter.findData("零值題材")
    )
    assert "平均日漲跌幅（%）：0.00" in view.comparison_version_labels[0].text()
    assert "資料日：2026-10-16" in view.comparison_version_labels[0].text()
    assert "映射版本／可得日：2026-10-15／2026-10-15" in view.comparison_version_labels[0].text()
    assert "manifest SHA-256：" + "c" * 64 in view.comparison_version_labels[0].text()
    assert "題材列來源 ID：local-test-source" in view.comparison_version_labels[0].text()
    assert not view.comparison_coverage_bars[0].isHidden()
    assert (view.comparison_coverage_bars[0].value(),
            view.comparison_coverage_bars[0].maximum()) == (1, 1)
    assert view.comparison_coverage_bars[0].format() == "報酬覆蓋 1 / 1 位成員"
    assert view.comparison_coverage_bars[0].accessibleDescription() == "報酬覆蓋 1 / 1 位成員"
    assert "平均日漲跌幅（%）：未知" in view.comparison_version_labels[1].text()
    assert "報表列：無（覆蓋未知）" in view.comparison_version_labels[1].text()
    assert "報酬覆蓋：未知" in view.comparison_version_labels[1].text()
    assert view.comparison_coverage_bars[1].isHidden()
    assert view.comparison_coverage_status_labels[1].text() == "報酬覆蓋：未知（無報表列或覆蓋不可用）"

    cancelled = iter(((str(paths[0]), ""), ("", "")))
    monkeypatch.setattr(
        view_module.QFileDialog, "getOpenFileName", lambda *_args, **_kwargs: next(cancelled),
    )
    view._choose_comparison_snapshots()
    assert view._comparison_snapshots is None
    assert view._comparison_paths is None
    assert "已取消雙版本明選；比較已清除" in view.comparison_status.text()
    assert view.comparison_version_labels[0].text() == "尚未讀取版本。"
    assert all(bar.isHidden() and bar.format() == "" for bar in view.comparison_coverage_bars)
    assert all(status.isHidden() for status in view.comparison_coverage_status_labels)

    snapshots[paths[0]] = partial
    snapshots[paths[1]] = _snapshot("b" * 64)
    view._comparison_paths = paths
    view._load_comparison_snapshots()
    _wait_until(application, lambda: view._comparison_snapshots is not None, timeout_ms=3000)
    view.comparison_chain_filter.setCurrentIndex(
        view.comparison_chain_filter.findData("科技鏈")
    )
    view.comparison_theme_filter.setCurrentIndex(
        view.comparison_theme_filter.findData("AI")
    )
    for label in view.comparison_version_labels:
        assert "平均日漲跌幅（%）：未知" in label.text()
        assert "報酬覆蓋：1 / 2 位成員" in label.text()
    assert all((bar.value(), bar.maximum()) == (1, 2) for bar in view.comparison_coverage_bars)
    view.shutdown()
    view.close()


@pytest.mark.parametrize(
    ("observation", "expected_bar", "expected_value", "expected_maximum", "expected_status"),
    (
        (SimpleNamespace(row_present=True, returns_coverage=3, member_count=3), True, 3, 3, ""),
        (SimpleNamespace(row_present=True, returns_coverage=1, member_count=3), True, 1, 3, ""),
        (SimpleNamespace(row_present=True, returns_coverage=0, member_count=3), True, 0, 3, ""),
        (SimpleNamespace(row_present=False, returns_coverage=None, member_count=3), False, 0, 1,
         "報酬覆蓋：未知（無報表列或覆蓋不可用）"),
        (SimpleNamespace(row_present=True, returns_coverage=0, member_count=0), False, 0, 1,
         "報酬覆蓋：不適用（0 位成員；比例未知）"),
    ),
)
def test_two_version_coverage_bar_preserves_zero_partial_and_unknown_states(
    observation, expected_bar, expected_value, expected_maximum, expected_status,
):
    view = IndustryThemeMapView()
    view._render_comparison_coverage(0, observation)
    bar = view.comparison_coverage_bars[0]
    status = view.comparison_coverage_status_labels[0]
    assert (not bar.isHidden()) is expected_bar
    assert (bar.value(), bar.maximum()) == (expected_value, expected_maximum)
    assert status.text() == expected_status
    assert (not status.isHidden()) is (not expected_bar)
    if expected_bar:
        assert bar.format() == f"報酬覆蓋 {expected_value} / {expected_maximum} 位成員"
        assert bar.accessibleDescription() == bar.format()
    else:
        assert bar.format() == ""
    view._clear_comparison_coverage()
    assert bar.isHidden()
    assert bar.format() == ""
    assert status.isHidden()


@pytest.mark.parametrize("width", (900, 1280))
def test_theme_name_search_filters_large_catalog_and_explicitly_locates_cross_chain_duplicate(width):
    application = app()
    view = IndustryThemeMapView()
    view.resize(width, 760)
    snapshot = _snapshot_with_large_theme_search_catalog()
    view.set_snapshot(snapshot)
    view.show()
    application.processEvents()

    assert len(view._theme_options) == 91
    for control in (
        view.chain_filter,
        view.theme_filter,
        view.theme_search_input,
        view.theme_search_results,
        view.theme_search_locate_button,
        view.stock_lookup_input,
        view.stock_lookup_results,
    ):
        assert control.width() > 0
    assert view.chain_filter.currentIndex() == 0
    assert view.theme_filter.currentIndex() == 0

    view.theme_search_input.setText("觀察")
    assert view.theme_search_results.count() == 3
    assert view.theme_search_results.itemText(1) == "鏈A／同名觀察題材"
    assert view.theme_search_results.itemText(2) == "鏈B／同名觀察題材"
    assert view.theme_search_results.currentIndex() == 0
    assert view.theme_search_results.currentData() is None
    assert not view.theme_search_locate_button.isEnabled()
    assert view.chain_filter.currentIndex() == 0
    assert view.theme_filter.currentIndex() == 0
    assert "找到 2 個題材" in view.theme_search_status_label.text()

    view.theme_search_results.setCurrentIndex(2)
    assert tuple(view.theme_search_results.currentData()) == (
        snapshot.identity_sha256, "鏈B", "同名觀察題材",
    )
    assert view.chain_filter.currentIndex() == 0
    assert view.theme_filter.currentIndex() == 0
    assert view.theme_search_locate_button.isEnabled()
    view.theme_search_locate_button.click()
    application.processEvents()
    assert view.chain_filter.currentData() == "鏈B"
    assert view.theme_filter.currentText() == "同名觀察題材"
    assert view.metrics_table.item(_metric_row(view, "平均日漲跌幅"), 1).text() == "-2.00 %"
    assert view.snapshot is snapshot

    view.theme_search_results.setItemData(
        2, ("0" * 64, "鏈B", "同名觀察題材")
    )
    view._locate_selected_theme_search_result()
    assert view.theme_search_input.text() == ""
    assert view.theme_search_results.count() == 1
    assert "搜尋結果已失效" in view.theme_search_status_label.text()
    assert view.chain_filter.currentData() == "鏈B"
    assert view.theme_filter.currentText() == "同名觀察題材"

    # 搜尋依整份載入目錄，不受定位後的鏈篩選限制。
    view.theme_search_input.setText("觀察題材")
    assert view.theme_search_results.count() == 3
    assert view.theme_search_results.itemText(1) == "鏈A／同名觀察題材"
    assert view.theme_search_results.itemText(2) == "鏈B／同名觀察題材"

    view.theme_search_input.setText("不存在的名稱片段")
    assert view.theme_search_results.count() == 1
    assert view.theme_search_results.currentData() is None
    assert not view.theme_search_locate_button.isEnabled()
    assert "沒有符合" in view.theme_search_status_label.text()
    assert view.chain_filter.currentData() == "鏈B"
    assert view.theme_filter.currentText() == "同名觀察題材"

    view.theme_search_input.clear()
    assert view.theme_search_input.text() == ""
    assert view.theme_search_results.count() == 1
    assert view.theme_search_results.currentData() is None
    assert "輸入題材名稱片段" in view.theme_search_status_label.text()
    assert len(view._theme_options) == 2  # 目前鏈篩選仍保留；搜尋目錄不受限

    view.theme_search_input.setText("觀察題材")
    replacement = ThemeResearchSnapshot(
        "8" * 64, snapshot.report, snapshot.mapping,
    )
    view.set_snapshot(replacement)
    assert view.snapshot is replacement
    assert view.theme_search_input.text() == ""
    assert view.theme_search_results.count() == 1
    assert view.theme_search_results.currentData() is None
    assert view.chain_filter.currentIndex() == 0
    assert view.theme_filter.currentIndex() == 0
    assert len(view._theme_options) == 91

    view.theme_search_input.setText("觀察題材")
    view.theme_search_results.setCurrentIndex(1)
    view._snapshot = None
    view._busy = True
    view._clear_snapshot_view()
    view._update_controls()
    assert view.theme_search_input.text() == ""
    assert view.theme_search_results.count() == 1
    assert view.theme_search_results.currentData() is None
    assert not view.theme_search_input.isEnabled()
    assert not view.theme_search_locate_button.isEnabled()
    assert "讀取中" in view.theme_search_status_label.text()

    view._busy = False
    view.shutdown()
    assert view.theme_search_input.text() == ""
    assert view.theme_search_results.count() == 1
    assert not view.theme_search_locate_button.isEnabled()
    assert "已關閉" in view.theme_search_status_label.text()
    view.close()


def test_two_version_comparison_failure_and_stale_callback_clear_on_main_snapshot_change(monkeypatch):
    application = app()
    view = IndustryThemeMapView()
    view.set_snapshot(_snapshot("f" * 64))
    paths = (Path("first.json"), Path("second.json"))
    view._comparison_paths = paths

    def fail_read(_first: Path, _second: Path):
        raise ValueError("第二份版本無法讀取")

    monkeypatch.setattr(view_module, "_read_theme_comparison_pair", fail_read)
    view._load_comparison_snapshots()
    _wait_until(application, lambda: view._comparison_worker is None, timeout_ms=3000)
    assert view._comparison_snapshots is None
    assert view.comparison_version_labels[0].text() == "尚未讀取版本。"
    assert "讀取失敗；比較已清除" in view.comparison_status.text()
    assert not view.comparison_chain_filter.isEnabled()

    started = threading.Event()
    release = threading.Event()
    pair = (_snapshot("a" * 64), _snapshot("b" * 64))

    def slow_read(_first: Path, _second: Path):
        started.set()
        release.wait(2)
        return pair

    monkeypatch.setattr(view_module, "_read_theme_comparison_pair", slow_read)
    view._comparison_paths = paths
    view._load_comparison_snapshots()
    assert started.wait(1)
    view.set_snapshot(_snapshot("e" * 64))
    assert view._comparison_snapshots is None
    assert view.comparison_version_labels[0].text() == "尚未讀取版本。"
    release.set()
    _wait_until(application, lambda: view._comparison_worker is None, timeout_ms=3000)
    assert view._comparison_snapshots is None
    assert "尚未明選雙版本。" == view.comparison_status.text()
    assert view.comparison_choose_button.isEnabled()
    view.shutdown()
    view.close()


def test_two_version_long_decimal_is_compact_but_exact_value_remains_available():
    view = IndustryThemeMapView()
    view.set_snapshot(_snapshot("f" * 64))
    first = _snapshot_with_zero_and_negative_values()
    exact = Decimal("-0.99009900990099009900990099009900990099")
    rows = tuple(
        replace(row, mean_return_pct=exact) if row.theme_name == "負值題材" else row
        for row in first.report.rows
    )
    first = replace(first, report=replace(first.report, rows=rows))
    view._comparison_snapshots = (first, _snapshot("d" * 64))
    view.comparison_chain_filter.addItem("能源鏈", "能源鏈")
    view.comparison_chain_filter.setCurrentIndex(view.comparison_chain_filter.findData("能源鏈"))
    view._populate_comparison_theme_filter()
    assert view.comparison_theme_filter.findData("負值題材") >= 0
    view.comparison_theme_filter.setCurrentIndex(
        view.comparison_theme_filter.findData("負值題材")
    )
    displayed = view.comparison_version_labels[0]
    assert "平均日漲跌幅（%）：約-0.9901（完整原值見提示）" in displayed.text()
    assert str(exact) in displayed.toolTip()
    assert "平均日漲跌幅（%）：未知" in view.comparison_version_labels[1].text()
    assert view._comparison_display_value(Decimal("0.00000000000001234567890123456789")) == (
        "約1.2346E-14（完整原值見提示）"
    )
    assert view._comparison_display_value(Decimal("0.00000000000000")) == (
        "0（完整原值見提示）"
    )
    view.shutdown()
    view.close()


def test_new_snapshot_clears_old_filter_while_hiding_keeps_current_selection():
    application = app()
    view = IndustryThemeMapView()
    view.resize(1100, 760)
    view.set_snapshot(_snapshot())
    _select_theme(view, "科技鏈", "AI")
    view.show()
    application.processEvents()

    view.hide()
    view.show()
    assert view.chain_filter.currentData() == "科技鏈"
    assert view.theme_filter.currentText() == "AI"
    assert view.member_table.rowCount() == 2

    view.set_snapshot(_snapshot("b" * 64))
    assert "版本 identity SHA-256：" + "b" * 64 in view.summary_label.text()
    assert view.chain_filter.currentIndex() == 0
    assert view.theme_filter.currentIndex() == 0
    assert view.member_table.rowCount() == 0


def test_narrow_layout_keeps_primary_controls_visible():
    application = app()
    view = IndustryThemeMapView()
    view.resize(1000, 700)
    view.set_snapshot(_snapshot())
    view.show()
    _wait_until(
        application,
        lambda: view.open_snapshot_button.isVisible(),
        timeout_ms=1000,
    )

    assert view.chain_filter.width() > 0
    assert view.theme_filter.width() > 0
    assert view.open_snapshot_button.geometry().right() <= view.width()
    assert view.open_snapshot_button.geometry().bottom() <= view.height()


def test_short_overview_precedes_collapsed_source_details():
    application = app()
    view = IndustryThemeMapView()
    view.resize(1200, 800)
    view.set_snapshot(_snapshot())
    view.show()
    application.processEvents()

    assert "資料日：2026-10-16" in view.overview_label.text()
    assert "2 條產業鏈／2 個題材" in view.overview_label.text()
    assert "本機目前研究" in view.overview_label.text()
    assert view.summary_group.isHidden()
    assert view.source_details_button.text() == "顯示來源與限制"

    view.scroll_area.ensureWidgetVisible(view.source_details_button)
    application.processEvents()
    QTest.mouseClick(view.source_details_button, Qt.MouseButton.LeftButton)
    application.processEvents()

    assert view.summary_group.isVisible()
    assert view.source_details_button.text() == "收合來源與限制"
    assert "版本 identity SHA-256：" + "a" * 64 in view.summary_label.text()


def test_partial_coverage_is_excluded_and_missing_rank_explained():
    app()
    view = IndustryThemeMapView()
    assert all(card.isHidden() for card in view.observation_cards.values())
    assert "尚未載入" in view.observation_missing_label.text()
    view.set_snapshot(_snapshot())

    assert "完整覆蓋：0 / 2 個報表題材列" in view.return_tiles_summary.text()
    assert view._return_tile_buttons == {}
    assert not view.return_tiles_toggle.isEnabled()
    assert view.leader_card_values["return"].text() == "資料不足"
    assert "沒有成員覆蓋完整" in view.leader_card_coverages["return"].text()
    assert view.leader_card_values["institutional"].text() == "資料不足"
    assert view.leader_card_values["volume"].text() == "資料不足"
    assert view.observation_cards["volume"].isHidden()
    assert view.observation_cards["institutional"].isHidden()
    assert "法人淨流向" in view.observation_missing_label.text()
    assert "不能推定為零" in view.observation_missing_label.text()
    assert view.leader_card_topics["turnover"].text() == "科技鏈／AI"
    assert view.leader_card_values["turnover"].text() == "125.00 TWD"
    assert view.leader_card_coverages["turnover"].text() == "2 / 2 位成員"
    assert view.ranking_table.rowCount() == 0
    assert "此欄資料不足" in view.ranking_empty_label.text()
    assert "覆蓋完整" in view.ranking_empty_label.text()

    view.ranking_type_combo.setCurrentIndex(
        view.ranking_type_combo.findData("turnover")
    )
    assert view.ranking_table.rowCount() == 1
    assert view.ranking_table.item(0, 2).text() == "AI"
    assert view.ranking_table.item(0, 3).text() == "125.00 TWD"
    assert view.ranking_table.item(0, 4).text() == "2 / 2 位成員"


def test_zero_and_negative_observations_remain_visible_in_presenter_order():
    app()
    view = IndustryThemeMapView()
    view.set_snapshot(_snapshot_with_zero_and_negative_values())

    assert view.leader_card_values["return"].text() == "0.00 %"
    assert view.leader_card_values["turnover"].text() == "0.00 TWD"
    assert view.leader_card_values["institutional"].text() == "0 股"
    assert view.leader_card_values["volume"].text() == "0.00 倍"
    assert view.ranking_table.rowCount() == 2
    assert view.ranking_table.item(0, 2).text() == "零值題材"
    assert view.ranking_table.item(0, 3).text() == "0.00 %"
    assert view.ranking_table.item(1, 2).text() == "負值題材"
    assert view.ranking_table.item(1, 3).text() == "-1.50 %"
    assert view.ranking_table.item(0, 3).data(OBSERVATION_DIRECTIONAL_ROLE) is True
    assert view.ranking_table.item(1, 3).data(OBSERVATION_DIRECTIONAL_ROLE) is True

    view.ranking_type_combo.setCurrentIndex(view.ranking_type_combo.findData("turnover"))
    assert view.ranking_table.item(0, 3).data(OBSERVATION_DIRECTIONAL_ROLE) is False

    view.ranking_type_combo.setCurrentIndex(
        view.ranking_type_combo.findData("institutional")
    )
    assert view.ranking_table.item(0, 3).data(OBSERVATION_DIRECTIONAL_ROLE) is True
    assert view.ranking_table.item(0, 3).text() == "0 股"
    assert view.ranking_table.item(1, 3).text() == "-4 股"


def test_first_screen_return_cards_show_leading_and_lagging_themes_with_member_breadth():
    app()
    view = IndustryThemeMapView()
    view.resize(1200, 850)
    view.set_snapshot(_snapshot_with_directional_rankings())
    view.show()
    app().processEvents()

    assert view.observation_cards["return"].title() == "領先題材｜平均日漲幅"
    assert view.observation_cards["return_laggard"].title() == "落後題材｜平均日漲幅"
    assert view.leader_card_topics["return"].text() == "鏈G／題材G"
    assert view.leader_card_values["return"].text() == "3.00 %"
    assert view.leader_card_topics["return_laggard"].text() == "鏈A／題材A"
    assert view.leader_card_values["return_laggard"].text() == "-3.00 %"
    assert "題材成員：漲 0／跌 1／平 0（1 位有漲跌資料；非全市場廣度）" in view.leader_card_breadth_labels["return_laggard"].text()
    assert "題材內上漲率未知" in view.leader_card_breadth_labels["return_laggard"].text()
    assert view.leader_card_breadth_bars["return_laggard"].accessibleDescription() == view.leader_card_breadth_labels["return_laggard"].text()
    assert view.leader_card_breadth_segments["return_laggard"][1].isVisible()
    assert not view.leader_card_breadth_segments["return_laggard"][0].isVisible()
    institutional_text = view.leader_card_institutional_labels["return_laggard"].text()
    assert (
        "買超 0／賣超 1／持平 0（有淨股數 1／1 位成員"
        in institutional_text
    )
    assert "非全市場廣度" in institutional_text
    assert "非多家法人共同買進同股統計" in institutional_text
    assert (
        view.leader_card_institutional_bars["return_laggard"].accessibleDescription()
        == institutional_text
    )
    assert view.leader_card_institutional_segments["return_laggard"][1].isVisible()
    assert view.leader_card_institutional_segments["return"][0].isVisible()
    assert view.observation_cards_layout.getItemPosition(
        view.observation_cards_layout.indexOf(view.observation_cards["return"])
    ) == (0, 0, 1, 2)
    assert view.observation_cards_layout.getItemPosition(
        view.observation_cards_layout.indexOf(view.observation_cards["return_laggard"])
    ) == (0, 2, 1, 2)
    view.resize(900, 850)
    app().processEvents()
    assert view.observation_cards_layout.getItemPosition(
        view.observation_cards_layout.indexOf(view.observation_cards["return"])
    ) == (0, 0, 1, 1)
    assert view.observation_cards_layout.getItemPosition(
        view.observation_cards_layout.indexOf(view.observation_cards["return_laggard"])
    ) == (0, 1, 1, 1)
    view.resize(540, 850)
    app().processEvents()
    assert view.observation_cards_layout.getItemPosition(
        view.observation_cards_layout.indexOf(view.observation_cards["return"])
    ) == (0, 0, 1, 1)
    assert view.observation_cards_layout.getItemPosition(
        view.observation_cards_layout.indexOf(view.observation_cards["return_laggard"])
    ) == (1, 0, 1, 1)
    assert view.content.layout().itemAt(1).widget() is view.observations_group
    view.close()


def test_theme_explorer_and_selected_details_precede_secondary_visualizations():
    app()
    view = IndustryThemeMapView()
    layout = view.content.layout()

    assert layout.itemAt(1).widget() is view.observations_group
    assert layout.indexOf(view.filter_group) == 2
    assert layout.indexOf(view.selected_theme_summary) == 3
    assert layout.indexOf(view.theme_detail_splitter) < layout.indexOf(
        view.return_tiles_toggle
    )
    assert layout.indexOf(view.theme_detail_splitter) < layout.indexOf(
        view.turnover_treemap_toggle
    )
    assert layout.indexOf(view.theme_detail_splitter) < layout.indexOf(
        view.ranking_group
    )
    assert layout.indexOf(view.theme_detail_splitter) < layout.indexOf(
        view.chain_directory_button
    )
    view.shutdown()
    view.close()


def test_topic_details_default_to_cards_and_card_actions_select_records():
    application = app()
    view = IndustryThemeMapView()
    view.resize(1100, 760)
    view.set_snapshot(_snapshot())
    view.ranking_type_combo.setCurrentIndex(
        view.ranking_type_combo.findData("turnover")
    )
    _select_theme(view, "科技鏈", "AI")
    view.show()
    application.processEvents()

    assert view.ranking_view_combo.currentData() == "cards"
    assert not view.ranking_cards_widget.isHidden()
    assert view.ranking_table.isHidden()
    assert view.metrics_detail_toggle.isChecked() is False
    assert view.metrics_table.isHidden()
    assert view.member_view_combo.currentData() == "cards"
    assert not view.member_cards_widget.isHidden()
    assert view.member_table.isHidden()
    assert set(view._member_card_buttons) == {"2330", "2317"}

    view.metrics_detail_toggle.click()
    application.processEvents()
    assert not view.metrics_table.isHidden()
    assert view.metrics_detail_toggle.text() == "收合九項指標原表"
    view.metrics_detail_toggle.click()
    view.member_view_combo.setCurrentIndex(view.member_view_combo.findData("table"))
    application.processEvents()
    assert view.member_cards_widget.isHidden()
    assert not view.member_table.isHidden()
    view.member_view_combo.setCurrentIndex(view.member_view_combo.findData("cards"))
    application.processEvents()

    view._member_card_buttons["2317"].click()
    application.processEvents()
    assert view.member_table.currentRow() == 1
    assert view.open_member_button.isEnabled()
    assert view._member_card_buttons["2317"].isChecked()

    ai_rank_card = next((
        button for button in view._ranking_card_buttons
        if button.property("rankedChainName") == "科技鏈"
        and button.property("rankedThemeName") == "AI"
    ), None)
    assert ai_rank_card is not None, [
        (button.accessibleName(), button.property("rankedChainName"), button.property("rankedThemeName"))
        for button in view._ranking_card_buttons
    ]
    ai_rank_card.click()
    application.processEvents()
    assert view.chain_filter.currentData() == "科技鏈"
    assert view.theme_filter.currentText() == "AI"
    view.close()


def test_member_cards_reflow_by_available_width_and_keep_page_members():
    application = app()
    view = IndustryThemeMapView()
    view.resize(1280, 900)
    view.set_snapshot(_classification_snapshot(member_count=50))
    _select_theme(view, "科技鏈", "AI")
    view.show()
    application.processEvents()

    assert view.member_table.rowCount() == 50
    assert view.member_cards_layout.count() == 50

    view.member_cards_widget.resize(550, 500)
    view._arrange_member_cards()
    positions = [view.member_cards_layout.getItemPosition(index) for index in range(50)]
    assert max(column for _row, column, _row_span, _column_span in positions) == 0
    assert max(row for row, _column, _row_span, _column_span in positions) == 49

    view.member_cards_widget.resize(760, 500)
    view._arrange_member_cards()
    positions = [view.member_cards_layout.getItemPosition(index) for index in range(50)]
    assert max(column for _row, column, _row_span, _column_span in positions) == 1
    assert max(row for row, _column, _row_span, _column_span in positions) == 24

    view.member_cards_widget.resize(1100, 500)
    view._arrange_member_cards()
    positions = [view.member_cards_layout.getItemPosition(index) for index in range(50)]
    assert max(column for _row, column, _row_span, _column_span in positions) == 2
    assert max(row for row, _column, _row_span, _column_span in positions) == 16
    assert len(view._member_card_buttons) == 50
    assert view.member_page_status_label.text().startswith("顯示 1–50 / 50 位成員")
    view.shutdown()
    view.close()


def _render_after_invalid_row_injection(
    view: IndustryThemeMapView,
    snapshot: ThemeResearchSnapshot,
    theme_name: str,
    *,
    row_updates: dict[str, object] | None = None,
    coverage_updates: dict[str, object] | None = None,
) -> None:
    """先建立有效呈現，再只於測試中繞過 frozen DTO 注入壞值。"""
    view.set_snapshot(snapshot)
    row = next(item for item in snapshot.report.rows if item.theme_name == theme_name)
    if coverage_updates:
        object.__setattr__(row, "coverage", replace(row.coverage, **coverage_updates))
    for field, value in (row_updates or {}).items():
        object.__setattr__(row, field, value)
    # 保留前一步建立的 presentation，讓同一筆候選列抵達 UI 資料品質守衛。
    view._render_presentation()


def test_first_screen_institutional_distribution_is_unknown_without_coverage():
    application = app()
    view = IndustryThemeMapView()
    snapshot = _snapshot_with_directional_rankings()
    _render_after_invalid_row_injection(
        view,
        snapshot,
        "題材G",
        row_updates={
            "institutional_buy_count": 0,
            "institutional_sell_count": 0,
            "institutional_flat_count": 0,
        },
        coverage_updates={"institutional_shares": 0},
    )
    application.processEvents()

    label = view.leader_card_institutional_labels["return"]
    assert "未知" in label.text()
    assert "尚未載入" not in label.text()
    assert "非全市場廣度" in label.text()
    assert "多家法人共同買進同股統計" in label.text()
    assert "未知" in view.leader_card_institutional_bars["return"].accessibleDescription()
    assert all(
        segment.isHidden()
        for segment in view.leader_card_institutional_segments["return"]
    )
    view.close()


@pytest.mark.parametrize(
    ("row_updates", "coverage_updates"),
    (
        ({"up_count": 0}, {}),
        ({"up_count": -1, "down_count": 2}, {}),
        ({"up_count": True}, {}),
        ({}, {"returns": True}),
        ({}, {"returns": -1}),
        ({}, {"members": 0}),
    ),
)
def test_first_screen_return_distribution_rejects_invalid_counts_and_coverage(
    row_updates, coverage_updates,
):
    application = app()
    view = IndustryThemeMapView()
    snapshot = _snapshot_with_directional_rankings()
    _render_after_invalid_row_injection(
        view,
        snapshot,
        "題材G",
        row_updates=row_updates,
        coverage_updates=coverage_updates,
    )
    application.processEvents()

    assert "未知" in view.leader_card_breadth_labels["return"].text()
    assert "尚未載入" not in view.leader_card_breadth_labels["return"].text()
    assert view.leader_card_topics["return"].text() == "鏈G／題材G"
    assert "未知" in view.leader_card_breadth_bars["return"].accessibleDescription()
    assert all(
        segment.isHidden()
        for segment in view.leader_card_breadth_segments["return"]
    )
    view.close()


@pytest.mark.parametrize(
    ("row_updates", "coverage_updates"),
    (
        ({"institutional_buy_count": 0}, {}),
        ({"institutional_buy_count": -1, "institutional_sell_count": 2}, {}),
        ({"institutional_buy_count": True}, {}),
        ({}, {"institutional_shares": True}),
        ({}, {"institutional_shares": -1}),
        ({}, {"members": 0}),
    ),
)
def test_first_screen_institutional_distribution_rejects_invalid_counts_and_coverage(
    row_updates, coverage_updates,
):
    application = app()
    view = IndustryThemeMapView()
    snapshot = _snapshot_with_directional_rankings()
    _render_after_invalid_row_injection(
        view,
        snapshot,
        "題材G",
        row_updates=row_updates,
        coverage_updates=coverage_updates,
    )
    application.processEvents()

    assert "未知" in view.leader_card_institutional_labels["return"].text()
    assert "尚未載入" not in view.leader_card_institutional_labels["return"].text()
    assert view.leader_card_topics["return"].text() == "鏈G／題材G"
    assert "未知" in view.leader_card_institutional_bars["return"].accessibleDescription()
    assert all(
        segment.isHidden()
        for segment in view.leader_card_institutional_segments["return"]
    )
    view.close()


@pytest.mark.parametrize(
    "ratio",
    (
        Decimal("NaN"),
        Decimal("-0.01"),
        Decimal("1.01"),
        0.5,
        Decimal("0.00"),
    ),
)
def test_first_screen_advancing_ratio_requires_finite_decimal_matching_counts(ratio):
    application = app()
    view = IndustryThemeMapView()
    snapshot = _snapshot_with_directional_rankings()
    _render_after_invalid_row_injection(
        view,
        snapshot,
        "題材G",
        row_updates={"advancing_ratio": ratio},
    )
    application.processEvents()

    label = view.leader_card_breadth_labels["return"].text()
    assert "題材內上漲率未知" in label
    assert "題材內上漲率 50" not in label
    view.close()


def test_return_tiles_show_eligible_source_context_and_drill_down_by_mouse_and_keyboard():
    application = app()
    view = IndustryThemeMapView()
    view.resize(1200, 850)
    snapshot = _snapshot_with_zero_and_negative_values()
    view.set_snapshot(snapshot)
    view.show()
    application.processEvents()

    assert view.return_tiles_summary.text() == (
        "資料日：2026-10-16　｜　完整覆蓋：2 / 2 個報表題材列"
    )
    assert set(view._return_tile_buttons) == {
        ("科技鏈", "零值題材"), ("能源鏈", "負值題材"),
    }
    zero = view._return_tile_buttons[("科技鏈", "零值題材")]
    negative = view._return_tile_buttons[("能源鏈", "負值題材")]
    assert "科技鏈｜" not in zero.text()
    assert "能源鏈｜" not in negative.text()
    assert zero.isCheckable() and zero.focusPolicy() == Qt.FocusPolicy.StrongFocus
    assert "2026-10-16" in negative.toolTip()
    assert "c" * 64 in negative.toolTip()
    assert "完整覆蓋 1 / 1 位成員" in negative.accessibleName()
    assert "紅色為正、綠色為負、灰色為零" in view.return_tiles_note.text()
    assert "background-color: #555B63" in zero.styleSheet()
    assert "background-color: #25634A" in negative.styleSheet()

    view.return_tiles_toggle.click()
    application.processEvents()
    assert view.return_tiles_group.isVisible()

    zero.setProperty("themeSnapshotIdentity", "stale-identity")
    QTest.mouseClick(zero, Qt.MouseButton.LeftButton)
    assert view.chain_filter.currentIndex() == 0
    assert view.theme_filter.currentIndex() == 0

    zero.setProperty("themeSnapshotIdentity", snapshot.identity_sha256)
    QTest.mouseClick(zero, Qt.MouseButton.LeftButton)
    application.processEvents()
    assert view.chain_filter.currentData() == "科技鏈"
    assert view.theme_filter.currentText() == "零值題材"
    assert view.metrics_table.item(_metric_row(view, "平均日漲跌幅"), 1).text() == "0.00 %"
    assert view.member_table.rowCount() == 1

    negative.setFocus()
    QTest.keyClick(negative, Qt.Key.Key_Space)
    application.processEvents()
    assert view.chain_filter.currentData() == "能源鏈"
    assert view.theme_filter.currentText() == "負值題材"
    assert view.metrics_table.item(_metric_row(view, "平均日漲跌幅"), 1).text() == "-1.50 %"
    assert view.member_table.item(0, 0).text() == "0002"

    mapping_without_negative = tuple(
        mapping_row for mapping_row in snapshot.mapping
        if mapping_row.theme_name != "負值題材"
    )
    unmapped_snapshot = ThemeResearchSnapshot(
        "f" * 64, snapshot.report, mapping_without_negative,
    )
    view.set_snapshot(unmapped_snapshot)
    assert set(view._return_tile_buttons) == {("科技鏈", "零值題材")}
    assert set(view._return_tile_buttons) <= set(view._theme_options[1:])
    assert "可由既有篩選定位：1 格" in view.return_tiles_summary.text()
    view.shutdown()
    view.close()


def test_return_tiles_disambiguate_cross_chain_duplicate_names_and_keep_exact_navigation():
    application = app()
    view = IndustryThemeMapView()
    view.resize(1200, 850)
    snapshot = _snapshot_with_duplicate_theme_names()
    view.set_snapshot(snapshot)
    view.show()
    application.processEvents()

    first = view._return_tile_buttons[("鏈A", "同名觀察題材")]
    second = view._return_tile_buttons[("鏈B", "同名觀察題材")]
    assert "鏈A｜同名觀察題材" in first.text()
    assert "鏈B｜同名觀察題材" in second.text()
    assert first.text().endswith("-3.00 %")
    assert second.text().endswith("-2.00 %")
    assert "鏈A／同名觀察題材" in first.toolTip()
    assert "鏈B／同名觀察題材" in second.accessibleName()
    assert "background-color: #25634A" in first.styleSheet()
    assert "background-color: #25634A" in second.styleSheet()

    QTest.mouseClick(first, Qt.MouseButton.LeftButton)
    application.processEvents()
    assert view.chain_filter.currentData() == "鏈A"
    assert view.theme_filter.currentText() == "同名觀察題材"
    assert view.metrics_table.item(_metric_row(view, "平均日漲跌幅"), 1).text() == "-3.00 %"

    QTest.mouseClick(second, Qt.MouseButton.LeftButton)
    application.processEvents()
    assert view.chain_filter.currentData() == "鏈B"
    assert view.theme_filter.currentText() == "同名觀察題材"
    assert view.metrics_table.item(_metric_row(view, "平均日漲跌幅"), 1).text() == "-2.00 %"
    view.shutdown()
    view.close()


def test_return_tiles_reset_identity_on_reload_clear_and_failed_load(monkeypatch):
    application = app()
    view = IndustryThemeMapView()
    original = _snapshot_with_zero_and_negative_values()
    view.set_snapshot(original)
    old_button = view._return_tile_buttons[("科技鏈", "零值題材")]

    replacement = ThemeResearchSnapshot(
        "e" * 64, original.report, original.mapping,
    )
    view.set_snapshot(replacement)
    assert old_button.isEnabled() is False
    assert view._return_tile_identity == replacement.identity_sha256
    assert all(
        button.property("themeSnapshotIdentity") == replacement.identity_sha256
        for button in view._return_tile_buttons.values()
    )

    assert view.clear_research()
    assert view._return_tile_identity is None
    assert view._return_tile_buttons == {}
    assert view.return_tiles_group.isHidden()
    assert "尚未載入" in view.return_tiles_summary.text()

    view.set_snapshot(original)
    assert view._return_tile_buttons

    def fail_read(_path: Path):
        raise ValueError("無法讀取題材版本")

    monkeypatch.setattr(view_module, "read_theme_research_snapshot", fail_read)
    view.load_snapshot(Path("missing-theme-manifest.json"))
    assert view.snapshot is None
    assert view._return_tile_buttons == {}
    assert view._return_tile_identity is None
    assert "版本讀取中" in view.return_tiles_summary.text()
    _wait_until(application, lambda: not view.is_busy(), timeout_ms=3000)
    assert view._return_tile_buttons == {}
    assert view._return_tile_identity is None
    assert "尚未載入" in view.return_tiles_summary.text()
    view.shutdown()
    view.close()


def test_turnover_treemap_uses_full_coverage_area_and_exact_snapshot_navigation():
    def with_zero(identity: str) -> ThemeResearchSnapshot:
        baseline = _snapshot_with_directional_rankings(identity=identity)
        rows = tuple(
            replace(row, turnover_twd=Decimal("0.00")) if row.theme_name == "題材D"
            else replace(row, turnover_twd=Decimal("50.00")) if row.theme_name == "題材F"
            else row
            for row in baseline.report.rows
        )
        return ThemeResearchSnapshot(
            baseline.identity_sha256, replace(baseline.report, rows=rows), baseline.mapping,
        )

    application = app()
    view = IndustryThemeMapView()
    view.resize(1200, 900)
    snapshot = with_zero("d" * 64)
    view.set_snapshot(snapshot)
    view.show()
    application.processEvents()

    assert "完整覆蓋有效值：7 / 9 個報表題材列" in view.turnover_treemap_summary.text()
    assert "正值面積：6 格" in view.turnover_treemap_summary.text()
    assert "零值：1 筆" in view.turnover_treemap_summary.text()
    assert "覆蓋不全、缺值或非有限值：2 筆未畫面積" in view.turnover_treemap_summary.text()
    assert set(view._turnover_treemap_buttons) == {
        (f"鏈{suffix}", f"題材{suffix}") for suffix in "ABCEFG"
    }
    assert set(view._turnover_zero_buttons) == {("鏈D", "題材D")}
    assert "題材成員可能重疊" in view.turnover_treemap_note.text()
    assert "不可相加作市場占比" in view.turnover_treemap_note.text()
    assert "不代表歷史 PIT 資格" in view.turnover_treemap_note.text()

    view.turnover_treemap_toggle.click()
    application.processEvents()
    assert view.turnover_treemap_group.isVisible()
    large = view._turnover_treemap_buttons[("鏈A", "題材A")]
    assert "鏈A ·" not in large.text()
    assert large.focusPolicy() == Qt.FocusPolicy.StrongFocus
    assert "完整覆蓋 1 / 1 位成員" in large.accessibleName()
    assert snapshot.identity_sha256 in large.toolTip()
    assert "原題材列相關來源識別" in large.toolTip()
    assert view._turnover_area_label(Decimal("90000000")) == "約9,000萬"
    area_ratio = (large.width() * large.height()) / (
        view.turnover_treemap_canvas.width() * view.turnover_treemap_canvas.height()
    )
    assert area_ratio == pytest.approx(0.25, abs=0.04)

    large.setProperty("themeSnapshotIdentity", "stale-identity")
    QTest.mouseClick(large, Qt.MouseButton.LeftButton)
    assert view.chain_filter.currentIndex() == 0
    assert view.theme_filter.currentIndex() == 0
    large.setProperty("themeSnapshotIdentity", snapshot.identity_sha256)
    QTest.mouseClick(large, Qt.MouseButton.LeftButton)
    application.processEvents()
    assert view.chain_filter.currentData() == "鏈A"
    assert view.theme_filter.currentText() == "題材A"
    assert view.metrics_table.item(_metric_row(view, "價格成交金額（TWD）"), 1).text() == "70.00"

    zero = view._turnover_zero_buttons[("鏈D", "題材D")]
    assert "成交金額為零，沒有面積" in zero.accessibleName()
    assert "零成交金額（不占面積）" in view.turnover_zero_summary.text()
    zero.setFocus()
    QTest.keyClick(zero, Qt.Key.Key_Space)
    application.processEvents()
    assert view.chain_filter.currentData() == "鏈D"
    assert view.theme_filter.currentText() == "題材D"
    assert view.metrics_table.item(_metric_row(view, "價格成交金額（TWD）"), 1).text() == "0.00"

    replacement = with_zero("e" * 64)
    view.set_snapshot(replacement)
    assert view._turnover_treemap_identity == replacement.identity_sha256
    assert all(
        button.property("themeSnapshotIdentity") == replacement.identity_sha256
        for button in (*view._turnover_treemap_buttons.values(), *view._turnover_zero_buttons.values())
    )
    view.shutdown()
    view.close()


def test_turnover_treemap_disambiguates_duplicate_names_without_hiding_value():
    application = app()
    view = IndustryThemeMapView()
    view.resize(1200, 900)
    snapshot = _snapshot_with_duplicate_theme_names()
    view.set_snapshot(snapshot)
    view.show()
    view.turnover_treemap_toggle.click()
    application.processEvents()

    first = view._turnover_treemap_buttons[("鏈A", "同名觀察題材")]
    second = view._turnover_treemap_buttons[("鏈B", "同名觀察題材")]
    assert "同名觀察題材" in first.text() and "鏈A" in first.text()
    assert "同名觀察題材" in second.text() and "鏈B" in second.text()
    assert first.text().count("\n") == 1
    assert second.text().count("\n") == 1
    assert first.text().endswith("70.00 TWD")
    assert second.text().endswith("10.00 TWD")
    assert "鏈A／同名觀察題材" in first.toolTip()
    assert "鏈B／同名觀察題材" in second.accessibleName()

    QTest.mouseClick(first, Qt.MouseButton.LeftButton)
    application.processEvents()
    assert view.chain_filter.currentData() == "鏈A"
    assert view.theme_filter.currentText() == "同名觀察題材"
    assert view.metrics_table.item(_metric_row(view, "價格成交金額（TWD）"), 1).text() == "70.00"

    QTest.mouseClick(second, Qt.MouseButton.LeftButton)
    application.processEvents()
    assert view.chain_filter.currentData() == "鏈B"
    assert view.theme_filter.currentText() == "同名觀察題材"
    assert view.metrics_table.item(_metric_row(view, "價格成交金額（TWD）"), 1).text() == "10.00"
    view.shutdown()
    view.close()


def test_large_turnover_uses_readable_units_and_preserves_exact_original():
    from dataclasses import replace

    app()
    view = IndustryThemeMapView()
    row = replace(_snapshot().report.rows[0], turnover_twd=Decimal("12345678901.23456789"))
    before = row.turnover_twd
    display, available, members = view._leader_value_and_coverage("turnover", row)
    assert display == "123.46 億元 TWD"
    assert "12345678901.23456789" in view._leader_original_value("turnover", row)
    assert row.turnover_twd == before
    assert (available, members) == (2, 2)


def test_sorting_direction_projects_global_high_and_low_five_for_all_metrics():
    app()
    snapshot = _snapshot_with_directional_rankings()
    original_rows = snapshot.report.rows
    view = IndustryThemeMapView()
    view.set_snapshot(snapshot)

    assert view.sorting_direction_combo.currentData() == "both"
    assert _ranked_theme_names(view) == ["題材G", "題材F", "題材A", "題材B"]
    cards_before = {
        key: (
            view.leader_card_topics[key].text(),
            view.leader_card_values[key].text(),
            view.leader_card_coverages[key].text(),
        )
        for key in view.leader_card_topics
    }
    expected_orders = {
        "return": (
            ["題材G", "題材F", "題材E", "題材D", "題材C"],
            ["題材A", "題材B", "題材C", "題材D", "題材E"],
        ),
        "turnover": (
            ["題材A", "題材C", "題材E", "題材G", "題材F"],
            ["題材B", "題材D", "題材F", "題材G", "題材E"],
        ),
        "institutional": (
            ["題材G", "題材F", "題材E", "題材D", "題材C"],
            ["題材A", "題材B", "題材C", "題材D", "題材E"],
        ),
        "volume": (
            ["題材B", "題材C", "題材D", "題材E", "題材F"],
            ["題材A", "題材G", "題材F", "題材E", "題材D"],
        ),
    }
    for metric, (high_order, low_order) in expected_orders.items():
        view.ranking_type_combo.setCurrentIndex(
            view.ranking_type_combo.findData(metric)
        )
        view.sorting_direction_combo.setCurrentIndex(
            view.sorting_direction_combo.findData(False)
        )
        assert _ranked_theme_names(view) == high_order
        view.sorting_direction_combo.setCurrentIndex(
            view.sorting_direction_combo.findData(True)
        )
        assert _ranked_theme_names(view) == low_order
        assert "部分覆蓋極端值" not in _ranked_theme_names(view)
        assert "未提供題材" not in _ranked_theme_names(view)
        view.sorting_direction_combo.setCurrentIndex(view.sorting_direction_combo.findData("both"))
        expected = list(dict.fromkeys(high_order[:2] + low_order[:2]))
        assert _ranked_theme_names(view) == expected
        assert view.ranking_table.rowCount() <= 4

    view.ranking_type_combo.setCurrentIndex(
        view.ranking_type_combo.findData("institutional")
    )
    view.sorting_direction_combo.setCurrentIndex(
        view.sorting_direction_combo.findData(True)
    )
    assert view.ranking_table.item(3, 3).text() == "0 股"
    assert "法人賣超" in view.ranking_note.text()
    assert cards_before == {
        key: (
            view.leader_card_topics[key].text(),
            view.leader_card_values[key].text(),
            view.leader_card_coverages[key].text(),
        )
        for key in view.leader_card_topics
    }
    assert snapshot.report.rows == original_rows
    view.close()


def test_selected_theme_member_navigation_capture_is_bound_to_visible_row():
    application = app()
    view = IndustryThemeMapView()
    snapshot = _snapshot()
    view.set_snapshot(snapshot)
    _select_theme(view, "科技鏈", "AI")
    view.member_table.setCurrentCell(0, 0)
    navigation = view.capture_selected_member_navigation("2330")
    assert navigation is not None
    assert navigation.snapshot_ref is snapshot
    assert navigation.snapshot_identity == snapshot.identity_sha256
    assert navigation.theme_key == ("科技鏈", "AI")
    assert navigation.member_stock_codes == ("2330", "2317")
    assert navigation.origin_stock_code == "2330"
    assert navigation.member_names == (("2330", "台積電"), ("2317", ""))

    assert view.capture_selected_member_navigation("2317") is None
    _select_theme(view, "金融鏈", "保險")
    _select_theme(view, "科技鏈", "AI")
    view.member_table.setCurrentCell(0, 0)
    changed_selection = view.capture_selected_member_navigation("2330")
    assert changed_selection is not None
    assert not navigation.matches(changed_selection)
    view.close()
    application.processEvents()


def test_directional_projection_rebuilds_after_snapshot_replacement():
    app()
    view = IndustryThemeMapView()
    view.set_snapshot(_snapshot_with_directional_rankings())
    view.ranking_type_combo.setCurrentIndex(
        view.ranking_type_combo.findData("return")
    )
    view.sorting_direction_combo.setCurrentIndex(
        view.sorting_direction_combo.findData(True)
    )
    assert view.ranking_table.item(0, 2).text() == "題材A"

    replacement = _snapshot_with_directional_rankings(
        "e" * 64,
        theme_prefix="新版",
    )
    view.set_snapshot(replacement)

    assert view.snapshot is replacement
    assert view.sorting_direction_combo.currentData() is True
    assert view.ranking_table.item(0, 2).text() == "新版A"
    assert "題材A" not in _ranked_theme_names(view)
    view.shutdown()
    view.close()
    assert view.snapshot is None
    assert view.ranking_table.rowCount() == 0


def test_clicking_ranked_theme_selects_original_chain_theme_and_members():
    application = app()
    view = IndustryThemeMapView()
    view.resize(1100, 760)
    view.set_snapshot(_snapshot())
    view.ranking_type_combo.setCurrentIndex(
        view.ranking_type_combo.findData("turnover")
    )
    view.ranking_view_combo.setCurrentIndex(view.ranking_view_combo.findData("table"))
    view.show()
    application.processEvents()

    view.scroll_area.ensureWidgetVisible(view.ranking_table, 0, 0)
    item = view.ranking_table.item(0, 2)
    assert item.text() == "AI"
    view.ranking_table.scrollToItem(item)
    application.processEvents()
    position = view.ranking_table.visualItemRect(item).center()
    table_viewport = view.ranking_table.viewport()
    assert table_viewport.rect().contains(position)
    page_position = view.scroll_area.viewport().mapFromGlobal(
        table_viewport.mapToGlobal(position)
    )
    assert view.scroll_area.viewport().rect().contains(page_position)

    QTest.mouseClick(
        table_viewport,
        Qt.MouseButton.LeftButton,
        pos=position,
    )
    application.processEvents()

    assert view.chain_filter.currentData() == "科技鏈"
    assert view.theme_filter.currentText() == "AI"
    assert [
        view.member_table.item(row, 0).text()
        for row in range(view.member_table.rowCount())
    ] == ["2330", "2317"]


def test_low_direction_rank_click_selects_original_theme_and_member():
    application = app()
    view = IndustryThemeMapView()
    view.resize(1100, 760)
    view.set_snapshot(_snapshot_with_directional_rankings())
    view.ranking_type_combo.setCurrentIndex(
        view.ranking_type_combo.findData("return")
    )
    view.sorting_direction_combo.setCurrentIndex(
        view.sorting_direction_combo.findData(True)
    )
    view.ranking_view_combo.setCurrentIndex(view.ranking_view_combo.findData("table"))
    view.show()
    application.processEvents()

    assert view.ranking_table.item(0, 2).text() == "題材A"
    view.scroll_area.ensureWidgetVisible(view.ranking_table, 0, 0)
    item = view.ranking_table.item(0, 2)
    view.ranking_table.scrollToItem(item)
    application.processEvents()
    position = view.ranking_table.visualItemRect(item).center()
    table_viewport = view.ranking_table.viewport()
    assert table_viewport.rect().contains(position)
    assert table_viewport.visibleRegion().contains(position)
    outer_position = view.scroll_area.viewport().mapFromGlobal(
        table_viewport.mapToGlobal(position)
    )
    assert view.scroll_area.viewport().rect().contains(outer_position)

    QTest.mouseClick(
        table_viewport,
        Qt.MouseButton.LeftButton,
        pos=position,
    )
    application.processEvents()

    assert view.chain_filter.currentData() == "鏈A"
    assert view.theme_filter.currentText() == "題材A"
    assert view.member_table.rowCount() == 1
    assert view.member_table.item(0, 0).text() == "8001"
    view.close()


def test_snapshot_changed_clears_on_load_and_emits_loaded_snapshot(monkeypatch):
    application = app()
    loaded_snapshot = _snapshot("e" * 64)
    captured = {}

    def read_snapshot(path: Path, *, expected_identity_sha256: str):
        captured["path"] = path
        captured["expected_identity_sha256"] = expected_identity_sha256
        return loaded_snapshot

    monkeypatch.setattr(view_module, "read_theme_research_snapshot", read_snapshot)
    view = IndustryThemeMapView()
    events = []
    view.snapshotChanged.connect(events.append)
    initial_snapshot = _snapshot("d" * 64)
    view.set_snapshot(initial_snapshot)
    assert events == [initial_snapshot]

    manifest_path = Path("selected-manifest.json")
    view.load_snapshot(
        manifest_path,
        expected_identity_sha256="e" * 64,
    )
    assert events[-1] is None
    _wait_until(application, lambda: not view.is_busy(), timeout_ms=3000)

    assert captured == {
        "path": manifest_path,
        "expected_identity_sha256": "e" * 64,
    }
    assert view.snapshot is loaded_snapshot
    assert events == [initial_snapshot, None, loaded_snapshot]
    view.ranking_type_combo.setCurrentIndex(
        view.ranking_type_combo.findData("turnover")
    )
    view.sorting_direction_combo.setCurrentIndex(
        view.sorting_direction_combo.findData(True)
    )
    assert view.ranking_table.rowCount() == 1

    view.shutdown()
    assert events[-1] is None
    assert view.ranking_table.rowCount() == 0
    assert not view.sorting_direction_combo.isEnabled()
    view.close()


def test_tpex_diagnostics_explains_market_scope_and_partial_flow_denominator():
    from dataclasses import replace

    application = app()
    snapshot = _snapshot()
    snapshot = replace(snapshot, report=replace(
        snapshot.report,
        warnings=("institutional_tpex_diagnostics_only", "non_tpex_members_excluded"),
    ))
    view = IndustryThemeMapView()
    try:
        view.set_snapshot(snapshot)
        assert "僅上櫃三大法人股數診斷" in view.overview_label.text()
        assert "上市、興櫃與未知市場未納入法人數值" in view.overview_label.text()
        assert "另有" not in view.overview_label.text()
        _select_theme(view, "科技鏈", "AI")
        net = _metric_row(view, "法人淨股數（已覆蓋成員合計）")
        counts = _metric_row(view, "法人買超／賣超／持平家數（已覆蓋成員）")
        ratio = _metric_row(view, "法人買超比例（已覆蓋成員）")
        assert view.metrics_table.item(net, 1).text() == "8"
        assert view.metrics_table.item(net, 2).text() == "1 / 2 位成員"
        assert view.metrics_table.item(counts, 2).text() == "1 / 2 位成員"
        assert view.metrics_table.item(ratio, 1).text() == "100.00%"
        assert view.metrics_table.item(ratio, 2).text() == "1 / 2 位成員"
        view.ranking_type_combo.setCurrentIndex(view.ranking_type_combo.findData("institutional"))
        assert _ranked_theme_names(view) == []
        _select_theme(view, "金融鏈", "保險")
        missing_returns = _metric_row(view, "上漲／下跌／平盤家數")
        missing_flows = _metric_row(view, "法人買超／賣超／持平家數")
        assert view.metrics_table.item(missing_returns, 1).text() == "未提供"
        assert view.metrics_table.item(missing_flows, 1).text() == "未提供"
        assert view.metrics_table.item(missing_returns, 2).text() == "0 / 1 位成員"
        assert view.metrics_table.item(missing_flows, 2).text() == "0 / 1 位成員"
    finally:
        view.close()
        application.processEvents()
