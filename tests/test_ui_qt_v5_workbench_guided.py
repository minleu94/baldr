import os
import sys
from dataclasses import replace
from datetime import date

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app_module.workbench_dtos import (
    WorkbenchActionItem,
    WorkbenchDailyEvidence,
    WorkbenchReviewItem,
)
from ui_qt.theme import MIDNIGHT_ANALYST
from ui_qt.views.workbench_view import UnifiedDecisionWorkbenchView

from test_ui_qt_workbench_view import _dashboard_with_replay
from test_ui_qt_decision_desk_view import FakeBuilder, _snapshot, rendered_view


def app() -> QApplication:
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication(sys.argv)
    return instance


def _mixed_dashboard():
    base = _dashboard_with_replay()
    daily = WorkbenchDailyEvidence(
        status="observed",
        decision_date="2026-07-06",
        data_as_of_date="2026-07-05",
        headline="先確認持倉風險，再逐檔查看候選。",
        next_action="先查看資料與候選來源，再決定是否進一步研究。",
        market_summary="市場資料可檢視，但仍有來源警示。",
        industry_summary="半導體是主要研究方向。",
        stock_summary="候選由既有來源提供。",
        watchlist_summary="觀察清單有觸發待覆盤。",
        portfolio_summary="持倉有一筆風險事項。",
        candidate_symbols=("2330", "2603"),
        candidate_count=2,
        candidate_status="candidate",
        candidate_data_date="2026-07-05",
        candidate_quality="observed",
        candidate_reasons=("2330 強勢但需確認量價。", "2603 觸發觀察條件。"),
    )
    reviews = (
        WorkbenchReviewItem(
            item_id="candidate_trigger_2330",
            title="候選觸發 2330",
            severity="warning",
            source="watchlist_trigger",
            summary="2330：強勢但需確認量價；決策日 2026-07-06。",
            drilldown_target="watchlist",
            code="2330",
        ),
        WorkbenchReviewItem(
            item_id="data_review",
            title="資料完整性待確認",
            severity="warning",
            source="data_quality_review",
            summary="來源日期需要人工核對。",
            drilldown_target="evidence_review",
        ),
    )
    actions = (
        WorkbenchActionItem(
            item_id="holding_risk",
            title="持倉風險待覆盤",
            source_type="portfolio_alert",
            severity="warning",
            summary="2330 的持倉條件需要人工確認。",
            source_trace="DecisionDeskSnapshot.portfolio_alerts",
            degraded_reason="human_review_required",
            drilldown_target="portfolio_review",
            code="2330",
        ),
        WorkbenchActionItem(
            item_id="generic_data_review",
            title="資料核對待處理",
            source_type="data_quality_review",
            severity="warning",
            summary="資料日期需要人工核對。",
            source_trace="WorkbenchDashboardDTO.status_strip",
            degraded_reason="human_review_required",
            drilldown_target="evidence_review",
        ),
    )
    return replace(
        base,
        daily_evidence=daily,
        review_items=reviews,
        action_items=actions,
        warnings=(
            "warning:來源日期需要確認",
            "source_missing:market_breadth",
            "waiting_for_time:evidence_window",
        ),
        market_context={"source_status": "ready", "overall_quality": "observed"},
    )


def test_guided_home_keeps_mixed_sources_separate_and_advanced_collapsed() -> None:
    app()
    view = UnifiedDecisionWorkbenchView(
        dashboard=_mixed_dashboard(),
        auto_refresh=False,
        navigate_to_daily_decision_callback=lambda: None,
        navigate_to_market_explore_callback=lambda: None,
        navigate_to_evidence_review_callback=lambda: None,
        navigate_to_portfolio_callback=lambda: None,
        navigate_to_watchlist_callback=lambda: None,
        navigate_to_stock_research_callback=lambda _context: None,
        navigate_to_update_callback=lambda: None,
        navigate_to_recommendation_callback=lambda: None,
    )

    assert view.advanced_workbench_panel.is_collapsed()
    assert view.guided_date_label.text() == "判讀日期：2026-07-06｜資料日期：2026-07-05"
    assert "先確認持倉風險" in view.guided_conclusion_label.text()
    assert view.guided_summary_model.rowCount() == 5
    rows = {
        view.guided_summary_model.raw_value(index, "key"): view.guided_summary_model.row_at(index)
        for index in range(view.guided_summary_model.rowCount())
    }
    assert "候選或研究事項待處理" in rows["candidates"].conclusion
    assert rows["candidates"].target == "advanced"
    assert rows["other"].title == "其他待處理"
    assert "持倉或風險事項" in rows["portfolio"].conclusion
    assert "市場判讀待處理" not in rows["market"].conclusion

    view.guided_priority_action_buttons["candidates"].click()
    assert not view.advanced_workbench_panel.is_collapsed()
    assert view._selected_detail_item.item_id == "candidate_trigger_2330"
    assert "強勢但需確認量價" in view.detail_summary_box.text()
    assert "2330" in view.daily_candidate_detail_label.text()
    assert "2603" in view.daily_candidate_detail_label.text()
    assert "強勢但需確認量價" in view.daily_candidate_detail_label.text()
    assert "下一步：先查看資料與候選來源" in view.daily_candidate_detail_label.text()

    view.guided_priority_action_buttons["data"].click()
    assert not view.warnings_collapsible.is_collapsed()
    warning_text = view.warning_list.toPlainText()
    assert "來源日期需要確認" in warning_text
    assert "market_breadth" in warning_text
    assert "等待真實時間累積" in warning_text

    view.guided_priority_action_buttons["other"].click()
    assert view._selected_detail_item.item_id == "data_review"
    assert "來源日期需要人工核對" in view.detail_summary_box.text()


def test_guided_candidates_selects_action_item_when_review_row_is_absent() -> None:
    app()
    dashboard = _mixed_dashboard()
    dashboard = replace(
        dashboard,
        review_items=(),
        action_items=(
            WorkbenchActionItem(
                item_id="candidate_action_2603",
                title="候選觸發 2603",
                source_type="watchlist_trigger",
                severity="warning",
                summary="2603：觸發觀察條件。",
                source_trace="DecisionDeskSnapshot.watchlist_triggers",
                degraded_reason="human_review_required",
                drilldown_target="watchlist",
                code="2603",
            ),
        ),
    )
    view = UnifiedDecisionWorkbenchView(
        dashboard=dashboard,
        auto_refresh=False,
        navigate_to_watchlist_callback=lambda: None,
    )

    view.guided_priority_action_buttons["candidates"].click()
    assert view._selected_detail_item.item_id == "candidate_action_2603"
    assert "2603" in view.detail_summary_box.text()


def test_decision_desk_keeps_full_market_details_progressive_and_data_impact_visible() -> None:
    app()
    view = rendered_view(
        FakeBuilder(
            _snapshot(
                overall_warnings=("market_data_visibility_missing",),
            )
        )
    )

    assert view.advanced_market_panel.is_collapsed()
    assert view.overall_status_label.text() == "摘要已載入"
    assert MIDNIGHT_ANALYST.success not in view.overall_status_label.styleSheet()
    assert view.overall_quality_badge.isHidden()
    assert view.decision_date_card.isHidden()
    assert view.generated_at_card.isHidden()
    assert "判讀日：2026-06-15" in view.generated_at_label.text()
    assert "資料影響" in view.market_data_impact_label.text()
    assert "缺件" in view.market_data_impact_label.text()
    assert "資料缺漏" in view.warning_list.toPlainText()

    view.market_details_button.click()
    assert not view.advanced_market_panel.is_collapsed()
    assert not view.advanced_market_panel.content_widget.isHidden()


def test_guided_home_unknown_state_does_not_use_success_tone() -> None:
    app()
    view = UnifiedDecisionWorkbenchView(auto_refresh=False)

    assert view.advanced_workbench_panel.is_collapsed()
    assert "尚未確認" in view.guided_priority_status_badges["market"].text()
    assert "#22c55e" not in view.guided_priority_status_badges["market"].styleSheet()
    assert view.guided_summary_model.raw_value(2, "status") == "unknown"
