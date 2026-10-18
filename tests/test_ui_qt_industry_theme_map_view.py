"""產業與題材頁的本機版本呈現與使用者操作測試。"""

import os
import sys
import time
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app_module.theme_daily_service import (
    ThemeDailyReport,
    ThemeDailyRow,
    ThemeMetricCoverage,
)
from app_module.theme_research_snapshot import ThemeResearchSnapshot
from ui_qt.views import industry_theme_map_view as view_module
from ui_qt.views.industry_theme_map_view import IndustryThemeMapView


def app():
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication(sys.argv)
    return instance


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


def _select_theme(view: IndustryThemeMapView, chain: str, theme: str) -> None:
    view.chain_filter.setCurrentIndex(view.chain_filter.findData(chain))
    view.theme_filter.setCurrentIndex(view.theme_filter.findText(theme))


def _metric_row(view: IndustryThemeMapView, label: str) -> int:
    for row_index in range(view.metrics_table.rowCount()):
        item = view.metrics_table.item(row_index, 0)
        if item is not None and item.text() == label:
            return row_index
    raise AssertionError(f"找不到指標列：{label}")


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
    flow_row = _metric_row(view, "法人流向淨股數")
    flow_amount_row = _metric_row(view, "法人流向淨金額（TWD）")
    advancing_row = _metric_row(view, "上漲比例")
    institutional_ratio_row = _metric_row(view, "法人買超比例")

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

    view.show()
    application.processEvents()
    selected_stock_ids = []
    view.stockSelected.connect(selected_stock_ids.append)
    item = view.member_table.item(0, 1)
    view.scroll_area.ensureWidgetVisible(view.member_table, 0, 0)
    view.member_table.scrollToItem(item)
    application.processEvents()
    item_position = view.member_table.visualItemRect(item).center()
    member_viewport = view.member_table.viewport()
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

    def fail_read(_path: Path):
        raise ValueError("無法讀取測試版本")

    monkeypatch.setattr(view_module, "read_theme_research_snapshot", fail_read)
    view.load_snapshot(Path("missing-manifest.json"))

    assert view.snapshot is None
    assert view.member_table.rowCount() == 0
    assert not view.member_table.isEnabled()
    assert events == [initial_snapshot, None]
    _wait_until(application, lambda: not view.is_busy(), timeout_ms=3000)
    assert view.snapshot is None
    assert view.member_table.rowCount() == 0
    assert "讀取失敗" in view.status_label.text()
    assert "2026-10-16" not in view.overview_label.text()
    assert events == [initial_snapshot, None, None]


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
    view.set_snapshot(_snapshot())

    assert view.leader_card_values["return"].text() == "資料不足"
    assert "沒有成員覆蓋完整" in view.leader_card_coverages["return"].text()
    assert view.leader_card_values["institutional"].text() == "資料不足"
    assert view.leader_card_values["volume"].text() == "資料不足"
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

    view.ranking_type_combo.setCurrentIndex(
        view.ranking_type_combo.findData("institutional")
    )
    assert view.ranking_table.item(0, 3).text() == "0 股"
    assert view.ranking_table.item(1, 3).text() == "-4 股"


def test_clicking_ranked_theme_selects_original_chain_theme_and_members():
    application = app()
    view = IndustryThemeMapView()
    view.resize(1100, 760)
    view.set_snapshot(_snapshot())
    view.ranking_type_combo.setCurrentIndex(
        view.ranking_type_combo.findData("turnover")
    )
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

    view.shutdown()
    assert events[-1] is None
