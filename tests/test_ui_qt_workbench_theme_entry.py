"""Workbench 首屏題材研究入口的本機 Qt 契約。"""
from __future__ import annotations

import os
import sys
from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app_module.research_session import ResearchStockContextDTO
from app_module.theme_daily_service import (
    ThemeDailyReport,
    ThemeDailyRow,
    ThemeMetricCoverage,
)
from app_module.theme_research_snapshot import ThemeResearchSnapshot
from decision_module.industry_theme_map import ThemeMappingRow
from ui_qt.views.workbench_view import UnifiedDecisionWorkbenchView


def app() -> QApplication:
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication(sys.argv)
    return instance


def _snapshot(identity: str = "f" * 64) -> ThemeResearchSnapshot:
    coverage = ThemeMetricCoverage(1, 0, 0, 0, 0, 0)
    rows = (
        ThemeDailyRow(
            chain_name="科技鏈",
            theme_name="AI",
            stock_ids=("2330",),
            mean_return_pct=None,
            turnover_twd=None,
            volume_multiple_5d=None,
            institutional_net_shares=None,
            institutional_net_turnover_twd=None,
            up_count=0,
            down_count=0,
            flat_count=0,
            institutional_buy_count=0,
            institutional_sell_count=0,
            institutional_flat_count=0,
            advancing_ratio=None,
            institutional_buy_ratio=None,
            coverage=coverage,
            source_ids=(),
        ),
        ThemeDailyRow(
            chain_name="金融鏈",
            theme_name="保險",
            stock_ids=("2881",),
            mean_return_pct=None,
            turnover_twd=None,
            volume_multiple_5d=None,
            institutional_net_shares=None,
            institutional_net_turnover_twd=None,
            up_count=0,
            down_count=0,
            flat_count=0,
            institutional_buy_count=0,
            institutional_sell_count=0,
            institutional_flat_count=0,
            advancing_ratio=None,
            institutional_buy_ratio=None,
            coverage=coverage,
            source_ids=(),
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
        ThemeMappingRow(
            snapshot_date="2026-10-15",
            available_date="2026-10-15",
            stock_id=stock_id,
            stock_name=stock_name,
            market_type="上市",
            l1_industry_category="",
            chain_name=chain_name,
            chain_tier="核心鏈",
            theme_name=theme_name,
            is_primary=True,
            assignment_method="公司主業",
            source_name="本機分類來源",
            source_tier="來源一級",
            pit_mode="pit_snapshot_aligned",
            evidence_note="保存映射列",
        )
        for stock_id, stock_name, chain_name, theme_name in (
            ("2330", "台積電", "科技鏈", "AI"),
            ("2881", "富邦金", "金融鏈", "保險"),
        )
    )
    return ThemeResearchSnapshot(identity, report, mapping)


def test_home_theme_entry_shows_unloaded_state_and_only_navigates() -> None:
    application = app()
    theme_navigation: list[str] = []
    stock_contexts: list[object] = []

    def capture_stock_context(context: object) -> None:
        stock_contexts.append(context)

    view = UnifiedDecisionWorkbenchView(
        auto_refresh=False,
        navigate_to_industry_themes_callback=lambda: theme_navigation.append("open"),
        navigate_to_stock_research_callback=capture_stock_context,
    )
    view.show()
    application.processEvents()

    assert "尚未載入題材研究版本" in view.home_theme_summary_label.text()
    assert view.home_theme_button.isEnabled()
    QTest.mouseClick(view.home_theme_button, Qt.MouseButton.LeftButton)
    assert theme_navigation == ["open"]
    assert "尚未載入題材研究版本" in view.home_theme_summary_label.text()

    assert view.home_more_actions.is_collapsed()
    view.home_more_actions.toggle_button.click()
    application.processEvents()
    view.home_stock_input.setText("2330")
    QTest.mouseClick(view.home_stock_search_button, Qt.MouseButton.LeftButton)
    assert len(stock_contexts) == 1
    stock_context = stock_contexts[0]
    assert isinstance(stock_context, ResearchStockContextDTO)
    assert stock_context.stock_code == "2330"
    assert stock_context.source_kind == "explicit_latest_stock_research"
    assert theme_navigation == ["open"]


def test_home_theme_summary_uses_snapshot_scope_and_clears() -> None:
    application = app()
    theme_navigation: list[str] = []
    view = UnifiedDecisionWorkbenchView(
        auto_refresh=False,
        navigate_to_industry_themes_callback=lambda: theme_navigation.append("open"),
    )
    view.show()
    application.processEvents()
    snapshot = _snapshot()

    view.set_theme_research_snapshot(snapshot)

    summary = view.home_theme_summary_label.text()
    assert "資料日 2026-10-16" in summary
    assert "涵蓋 2 條產業鏈／2 個題材" in summary
    assert snapshot.identity_sha256 in view.home_theme_summary_label.toolTip()
    assert "0／2" in view.home_theme_observation_label.text()
    assert "Unknown" in view.home_theme_observation_label.text()
    QTest.mouseClick(view.home_theme_button, Qt.MouseButton.LeftButton)
    assert theme_navigation == ["open"]
    assert view.home_theme_summary_label.text() == summary

    view.set_theme_research_snapshot(None)
    assert "尚未載入題材研究版本" in view.home_theme_summary_label.text()
    assert view.home_theme_summary_label.toolTip() == ""
    assert "相對高端" not in view.home_theme_observation_label.text()


def test_home_theme_extremes_keep_negative_values_and_exclude_partial_coverage() -> None:
    app()
    original = _snapshot()
    first, second = original.report.rows
    covered = replace(first.coverage, returns=1)
    rows = (
        replace(first, mean_return_pct=Decimal("-1.25"), coverage=covered),
        replace(second, mean_return_pct=Decimal("-5.50"), coverage=covered),
        replace(first, theme_name="部分覆蓋", mean_return_pct=Decimal("99.00")),
    )
    snapshot = replace(original, report=replace(original.report, rows=rows))
    opened = []
    view = UnifiedDecisionWorkbenchView(
        auto_refresh=False, navigate_to_industry_themes_callback=lambda: opened.append("same"),
    )
    try:
        view.set_theme_research_snapshot(snapshot)
        text = view.home_theme_observation_label.text()
        assert "2／3" in text and "Unknown" in text
        assert "相對高端：科技鏈／AI -1.25%" in text
        assert "相對低端：金融鏈／保險 -5.50%" in text
        assert "99.00" not in text and "上漲" not in text
        view.home_theme_button.click()
        assert opened == ["same"]
        assert view._theme_research_snapshot is snapshot
        view.set_theme_research_snapshot(None)
        assert "-1.25" not in view.home_theme_observation_label.text()
    finally:
        view.begin_shutdown()
        view.close()


def test_home_theme_summary_rejects_untyped_snapshot() -> None:
    app()
    view = UnifiedDecisionWorkbenchView(auto_refresh=False)

    assert not view.home_theme_button.isEnabled()
    with pytest.raises(TypeError):
        getattr(view, "set_theme_research_snapshot")(object())


def test_candidate_source_date_is_distinct_from_market_date_on_home() -> None:
    from tests.test_ui_qt_workbench_candidate_selection import _daily, _view

    app()
    daily = _daily(("2330", "2603"), data_date="2026-10-15")
    view, _ = _view(daily)
    try:
        reason = view.guided_priority_reason_labels["candidates"].text()
        assert "候選資料日：2026-10-15" in reason
        assert "來源品質：缺漏" in reason
        dashboard = replace(view._dashboard, daily_evidence=replace(daily, candidate_data_date=None))
        view.render_dashboard(dashboard)
        assert "候選資料日：未知" in view.guided_priority_reason_labels["candidates"].text()
    finally:
        view.begin_shutdown()
        view.close()
