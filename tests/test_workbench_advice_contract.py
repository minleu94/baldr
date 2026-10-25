from __future__ import annotations

import os
import sys
from dataclasses import replace
from datetime import date, datetime

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from app_module.advice_dtos import (
    AdviceAction,
    AdviceClassification,
    AdviceDashboardDTO,
    AdviceMode,
    AdvicePolicyConfig,
    PortfolioAdviceDTO,
    RecommendationAdviceDTO,
)
from app_module.workbench_dtos import WorkbenchAccessBoundary, WorkbenchDashboardDTO
from ui_qt.views.workbench_view import UnifiedDecisionWorkbenchView


def _app() -> QApplication:
    instance = QApplication.instance()
    if isinstance(instance, QApplication):
        return instance
    return QApplication(sys.argv)


def _dashboard_with_advice() -> WorkbenchDashboardDTO:
    advice = AdviceDashboardDTO(
        decision_date="2026-07-12",
        data_as_of_date="2026-07-11",
        mode=AdviceMode.GUIDED,
        policy=AdvicePolicyConfig(),
        recommendations=(
            RecommendationAdviceDTO(
                stock_code="2330",
                advice_action=AdviceAction.NO_NEW_POSITION,
                why_not_reasons=("guided_mode_strategy_not_promoted",),
                data_quality="DEGRADED",
                execution_feasibility="NOT_FEASIBLE",
            ),
        ),
        portfolio_rows=(
            PortfolioAdviceDTO(
                stock_code="2330",
                advice_action=AdviceAction.NO_NEW_POSITION,
                target_weight_bp=0,
                current_weight_bp=1200,
                weight_gap_bp=-1200,
                reasons=("risk_budget_unavailable",),
                data_quality="DEGRADED",
                execution_feasibility="NOT_FEASIBLE",
            ),
        ),
        warnings=("evidence_degraded",),
    )
    return WorkbenchDashboardDTO(
        as_of_date=date(2026, 7, 12),
        generated_at=datetime(2026, 7, 12, 12, 0, 0),
        source_mode="read_only",
        access_boundary=WorkbenchAccessBoundary(),
        status_strip=(),
        review_items=(),
        evidence_summary=(),
        market_context={},
        portfolio_watchlist_summary={},
        daily_checklist=(),
        advice_dashboard=advice,
    )


def test_workbench_renders_advice_dto_without_policy_execution() -> None:
    _app()

    view = UnifiedDecisionWorkbenchView(dashboard=_dashboard_with_advice(), auto_refresh=False)

    assert "模式：引導模式" in view.advice_summary.text()
    assert "決策日：2026-07-12｜資料日：2026-07-11" in view.advice_summary.text()
    assert "正式 Advice：1 列" in view.advice_summary.text()
    assert "evidence_degraded" in view.advice_warning_status.text()
    action_index = view.advice_recommendation_model.index(
        0, view.advice_recommendation_model.column_index("advice_action")
    )
    quality_index = view.advice_recommendation_model.index(
        0, view.advice_recommendation_model.column_index("data_quality")
    )
    feasibility_index = view.advice_recommendation_model.index(
        0, view.advice_recommendation_model.column_index("execution_feasibility")
    )
    assert view.advice_recommendation_model.data(action_index) == "暫不新增部位"
    assert view.advice_recommendation_model.data(action_index, Qt.ToolTipRole) == "原始值：NO_NEW_POSITION"
    assert view.advice_recommendation_model.data(quality_index) == "降級"
    assert view.advice_recommendation_model.data(quality_index, Qt.ToolTipRole) == "原始值：DEGRADED"
    assert view.advice_recommendation_model.data(feasibility_index) == "原狀態：不可成交"
    assert view.advice_recommendation_model.data(feasibility_index, Qt.ToolTipRole) == "原始值：NOT_FEASIBLE"
    assert "Advice 僅呈現已注入 DTO、不執行 Policy" in view.boundary_banner.text()
    assert view.advice_portfolio_model.rowCount() == 1
    assert view.advice_portfolio_model.data(
        view.advice_portfolio_model.index(0, view.advice_portfolio_model.column_index("target_weight_bp"))
    ) == "0"
    assert tuple(
        view.advice_portfolio_model.headerData(column, Qt.Orientation.Horizontal)
        for column in range(view.advice_portfolio_model.columnCount())
    ) == ("標的", "動作", "目標配置（bp）", "目前配置（bp）", "配置差距（bp）", "資料品質", "可成交性")
    for field, expected_label, expected_raw in (
        ("advice_action", "暫不新增部位", "NO_NEW_POSITION"),
        ("data_quality", "降級", "DEGRADED"),
        ("execution_feasibility", "原狀態：不可成交", "NOT_FEASIBLE"),
    ):
        index = view.advice_portfolio_model.index(
            0, view.advice_portfolio_model.column_index(field)
        )
        assert view.advice_portfolio_model.data(index) == expected_label
        assert view.advice_portfolio_model.data(index, Qt.ToolTipRole) == f"原始值：{expected_raw}"
        assert expected_raw in view.advice_portfolio_model.data(index, Qt.AccessibleTextRole)
    bp_index = view.advice_portfolio_model.index(
        0, view.advice_portfolio_model.column_index("current_weight_bp")
    )
    assert view.advice_portfolio_model.data(bp_index) == "1200"
    assert view.advice_portfolio_model.data(bp_index, Qt.ToolTipRole) == "原始值：1200 bp"
    assert "1200" in view.advice_portfolio_model.data(bp_index, Qt.AccessibleTextRole)
    view.advice_recommendation_model.set_rows((
        RecommendationAdviceDTO(
            stock_code="9999",
            advice_action="FUTURE_ACTION",
            data_quality="FUTURE_QUALITY",
            execution_feasibility="FUTURE_FEASIBILITY",
        ),
    ))
    for field, expected in (
        ("advice_action", "FUTURE_ACTION"),
        ("data_quality", "FUTURE_QUALITY"),
        ("execution_feasibility", "FUTURE_FEASIBILITY"),
    ):
        index = view.advice_recommendation_model.index(
            0, view.advice_recommendation_model.column_index(field)
        )
        assert view.advice_recommendation_model.data(index) == expected
        assert view.advice_recommendation_model.data(index, Qt.ToolTipRole) == f"原始值：{expected}"
    view.advice_recommendation_model.set_rows((
        RecommendationAdviceDTO(stock_code="0000", advice_action=AdviceAction.RESEARCH),
    ))
    unknown_index = view.advice_recommendation_model.index(
        0, view.advice_recommendation_model.column_index("data_quality")
    )
    assert view.advice_recommendation_model.data(unknown_index) == "未知"
    assert view.advice_recommendation_model.data(unknown_index, Qt.ToolTipRole) == "原始值：未知"


def test_workbench_separates_professional_candidates_from_formal_advice() -> None:
    _app()
    dashboard = _dashboard_with_advice()
    professional_advice = AdviceDashboardDTO(
        decision_date=dashboard.advice_dashboard.decision_date,
        data_as_of_date=dashboard.advice_dashboard.data_as_of_date,
        mode=AdviceMode.PROFESSIONAL,
        policy=AdvicePolicyConfig(mode=AdviceMode.PROFESSIONAL),
        recommendations=(
            RecommendationAdviceDTO(
                stock_code="2330",
                advice_action=AdviceAction.RESEARCH,
                classification=AdviceClassification.PROFESSIONAL_CANDIDATE,
            ),
        ),
    )
    candidate_dashboard = WorkbenchDashboardDTO(
        as_of_date=dashboard.as_of_date,
        generated_at=dashboard.generated_at,
        source_mode=dashboard.source_mode,
        access_boundary=dashboard.access_boundary,
        status_strip=dashboard.status_strip,
        review_items=dashboard.review_items,
        evidence_summary=dashboard.evidence_summary,
        market_context=dashboard.market_context,
        portfolio_watchlist_summary=dashboard.portfolio_watchlist_summary,
        daily_checklist=dashboard.daily_checklist,
        advice_dashboard=professional_advice,
    )

    view = UnifiedDecisionWorkbenchView(dashboard=candidate_dashboard, auto_refresh=False)

    assert view.advice_recommendation_model.rowCount() == 0
    assert view.advice_candidate_model.rowCount() == 1
    assert "正式 Advice：0 列" in view.advice_summary.text()
    assert "Professional 研究候選：1 列" in view.advice_summary.text()
    view._show_advice_row_presentation(view.advice_candidate_model, 0)
    assert "Professional 研究候選（不屬於正式 Advice）" in view.advice_selection_card.text()
    assert "動作：研究（原碼：RESEARCH）" in view.advice_selection_card.text()
    assert "適用期間：未提供" in view.advice_selection_card.text()
    assert "風險：未提供" in view.advice_selection_card.text()
    assert "失效條件：未提供" in view.advice_selection_card.text()
    assert "共用證據詳情（唯讀）" in view.advice_presentation_detail.text()


def test_advice_selection_and_warnings_clear_when_state_changes() -> None:
    _app()
    view = UnifiedDecisionWorkbenchView(dashboard=_dashboard_with_advice(), auto_refresh=False)
    view.advice_recommendation_table.setCurrentIndex(
        view.advice_recommendation_model.index(0, 0)
    )
    assert "暫不新增部位" in view.advice_selection_card.text()
    assert view.advice_lineage_button.isEnabled()

    view._set_advice_state("ADVICE_DTO_ERROR", "synthetic failure")

    assert view.advice_recommendation_model.rowCount() == 0
    assert view.advice_candidate_model.rowCount() == 0
    assert view.advice_portfolio_model.rowCount() == 0
    assert "尚未選取" in view.advice_selection_card.text()
    assert not view.advice_lineage_button.isEnabled()
    assert "舊警告已清除" in view.advice_warning_status.text()


def test_no_eligible_advice_keeps_empty_reason_separate_from_source_warnings() -> None:
    _app()
    dashboard = _dashboard_with_advice()
    empty_advice = replace(
        dashboard.advice_dashboard,
        recommendations=(),
        portfolio_rows=(),
        warnings=("first_warning", "second_warning"),
    )
    view = UnifiedDecisionWorkbenchView(
        dashboard=replace(dashboard, advice_dashboard=empty_advice),
        auto_refresh=False,
    )

    assert "本次沒有可呈現的 Advice" in view.advice_empty_label.text()
    assert "first_warning" in view.advice_empty_label.text()
    assert "second_warning" in view.advice_empty_label.text()
    assert "不會自動補齊資料或取得正式資格" in view.advice_empty_label.text()
    assert "原警告：" in view.advice_warning_status.text()
    assert "first_warning\n• second_warning" in view.advice_warning_status.text()
    assert "無合格標的" not in view.advice_warning_status.text()

    no_warning_advice = replace(empty_advice, warnings=())
    no_warning_view = UnifiedDecisionWorkbenchView(
        dashboard=replace(dashboard, advice_dashboard=no_warning_advice),
        auto_refresh=False,
    )
    assert "無原警告回報；這不代表沒有風險" in no_warning_view.advice_warning_status.text()
    assert "沒有提供空結果原因" in no_warning_view.advice_empty_label.text()
    assert "不能僅由空結果推斷資料完整或風險已解除" in no_warning_view.advice_empty_label.text()
    assert view.advice_recommendation_table.isHidden()
    assert view.advice_candidate_table.isHidden()
    assert view.advice_portfolio_table.isHidden()


def test_no_eligible_advice_explains_known_warnings_and_escapes_source_text() -> None:
    _app()
    dashboard = _dashboard_with_advice()
    blocked_advice = replace(
        dashboard.advice_dashboard,
        recommendations=(),
        portfolio_rows=(),
        warnings=(
            "evidence_quality_missing",
            "risk_budget_unavailable",
            "raw <script>alert(1)</script>",
            "fourth_warning",
        ),
    )
    view = UnifiedDecisionWorkbenchView(
        dashboard=replace(dashboard, advice_dashboard=blocked_advice),
        auto_refresh=False,
    )

    rendered = view.advice_empty_label.text()
    assert "缺少合格證據，不能產生 Advice。" in rendered
    assert "缺少已核驗的風險預算，不能提供配置。" in rendered
    assert "raw &lt;script&gt;alert(1)&lt;/script&gt;" in rendered
    assert "<script>" not in rendered
    assert "另有 1 則，請見下方完整原警告。" in rendered
    assert "raw <script>alert(1)</script>" in view.advice_warning_status.text()


def test_advice_selection_card_bounds_height_and_keeps_full_text_reachable() -> None:
    _app()
    view = UnifiedDecisionWorkbenchView(dashboard=_dashboard_with_advice(), auto_refresh=False)
    long_reason = "原始研究理由" * 40
    long_risk = "原始風險" * 30
    long_invalidation = "原始失效條件" * 30
    long_advice = RecommendationAdviceDTO(
        stock_code="2330",
        advice_action=AdviceAction.RESEARCH,
        why_reasons=(long_reason,),
        risk_reasons=(long_risk,),
        invalidation_conditions=(long_invalidation,),
    )
    view.advice_recommendation_model.set_rows((long_advice,))
    view._show_advice_row_presentation(view.advice_recommendation_model, 0)

    assert view.advice_selection_card.maximumHeight() == 160
    assert "完整理由見下方共用證據詳情" in view.advice_selection_card.text()
    assert long_reason in view.advice_selection_card.toolTip()
    assert "風險：" in view.advice_selection_card.text()
    assert long_risk not in view.advice_selection_card.text()
    assert long_reason in view.advice_selection_card.accessibleDescription()
    assert long_reason in view.advice_presentation_detail.text()
    assert long_risk in view.advice_selection_card.toolTip()
    assert long_invalidation in view.advice_selection_card.accessibleDescription()
    assert long_risk in view.advice_presentation_detail.text()


def test_advice_tables_hide_empty_models_and_bound_nonempty_rows() -> None:
    _app()
    dashboard = _dashboard_with_advice()
    one_row_view = UnifiedDecisionWorkbenchView(dashboard=dashboard, auto_refresh=False)
    assert not one_row_view.advice_recommendation_table.isHidden()
    assert one_row_view.advice_candidate_table.isHidden()
    assert not one_row_view.advice_portfolio_table.isHidden()
    assert one_row_view.advice_recommendation_table.maximumHeight() < 160

    many_recommendations = tuple(
        RecommendationAdviceDTO(
            stock_code=f"{2330 + index}",
            advice_action=AdviceAction.RESEARCH,
        )
        for index in range(5)
    )
    many_advice = replace(
        dashboard.advice_dashboard,
        recommendations=many_recommendations,
        portfolio_rows=(),
    )
    many_row_view = UnifiedDecisionWorkbenchView(
        dashboard=replace(dashboard, advice_dashboard=many_advice),
        auto_refresh=False,
    )
    table = many_row_view.advice_recommendation_table
    assert table.model().rowCount() == 5
    assert not table.isHidden()
    assert table.maximumHeight() < 200
    assert table.verticalScrollBarPolicy() == Qt.ScrollBarAsNeeded
    assert table.horizontalScrollBarPolicy() == Qt.ScrollBarAsNeeded
    assert many_row_view.advice_candidate_table.isHidden()
    assert many_row_view.advice_portfolio_table.isHidden()
