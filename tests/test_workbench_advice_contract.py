from __future__ import annotations

import os
import sys
from dataclasses import replace
from datetime import date, datetime

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import (
    QApplication,
    QBoxLayout,
    QDateTimeEdit,
    QDialog,
    QFrame,
    QLabel,
    QSizePolicy,
)
from PySide6.QtCore import QDateTime, Qt
from PySide6.QtTest import QTest

from app_module.advice_dtos import (
    AdviceAction,
    AdviceClassification,
    AdviceDashboardDTO,
    AdviceMode,
    AdvicePolicyConfig,
    PortfolioAdviceDTO,
    RecommendationAdviceDTO,
)
from app_module.advice_composer import AdviceComposer
from app_module.advice_policy import AdvicePolicy
from app_module.recommendation.legacy_dtos import RecommendationDTO, RecommendationResultDTO
from app_module.workbench_dtos import (
    WorkbenchAccessBoundary,
    WorkbenchDashboardDTO,
    WorkbenchDailyEvidence,
)
from ui_qt.views.workbench_view import (
    UnifiedDecisionWorkbenchView,
    _advice_presentation_sections_html,
    _daily_trace_sections_html,
    _advice_warning_text,
)


def _app() -> QApplication:
    instance = QApplication.instance()
    if isinstance(instance, QApplication):
        return instance
    return QApplication(sys.argv)


def _wait_for_qt(predicate, timeout: float = 2.0) -> bool:
    from time import monotonic, sleep

    deadline = monotonic() + timeout
    while monotonic() < deadline:
        QApplication.processEvents()
        if predicate():
            return True
        sleep(0.01)
    QApplication.processEvents()
    return bool(predicate())


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


def test_advice_detail_sections_have_visual_hierarchy_and_escape_source_text():
    rendered = _advice_presentation_sections_html(
        [
            "本筆資料身份（唯讀）\n股票：1569",
            "Advice 判讀與限制｜唯讀\n動作適合度：研究\n限制：<script>alert(1)</script>",
            "逐股來源證據｜本筆保存結果\n來源：原始證據",
            "策略版本作者說明｜選填；缺漏不阻擋 Advice\n進場論點：未提供",
        ]
    )

    assert rendered.count("border-left:3px solid") == 4
    assert "Advice 判讀與限制" in rendered
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in rendered
    assert "<script>" not in rendered


def test_daily_source_trace_uses_guided_sections_and_escapes_source_text():
    rendered = _daily_trace_sections_html(
        "本次每日來源（唯讀）\n"
        "本次結果\n結果 ID：saved-1\n"
        "候選來源與範圍\n來源 ID：<script>candidate</script>\n"
        "篩選與排除\n來源未提供可顯示的排除摘要；不能據此判定沒有排除。\n"
        "證據成熟度觀察\n• 20 日：總數 4｜已就緒 1｜待成熟 2｜缺漏 1"
    )

    assert rendered.count("border-left:3px solid") == 5
    assert "候選來源與範圍" in rendered
    assert "篩選與排除" in rendered
    assert "&lt;script&gt;candidate&lt;/script&gt;" in rendered
    assert "<script>candidate</script>" not in rendered


def test_candidate_scope_details_remain_reachable_without_source_trace_text():
    _app()
    daily = WorkbenchDailyEvidence(
        status="candidate",
        decision_date="2026-10-28",
        data_as_of_date="2026-10-27",
        headline="有研究候選",
        next_action="核對來源",
        market_summary="",
        industry_summary="",
        stock_summary="1 檔候選",
        watchlist_summary="",
        portfolio_summary="",
        candidate_count=1,
        candidate_symbols=("1569",),
        candidate_source_id="candidate-source-1",
        candidate_data_date="2026-10-27",
        candidate_quality="degraded",
        candidate_requested_count=4,
        candidate_degraded_count=1,
        candidate_missing_count=2,
    )
    dashboard = replace(_dashboard_with_advice(), daily_evidence=daily)
    view = UnifiedDecisionWorkbenchView(dashboard=dashboard, auto_refresh=False)

    assert "來源 ID=candidate-source-1" in view.daily_candidate_detail_label.text()
    assert "候選資料日=2026-10-27" in view.daily_candidate_detail_label.text()
    assert "要求檔數" not in view.daily_candidate_detail_label.text()
    assert "1 檔" in view.daily_candidate_card.value_label.text()
    assert "1 檔" not in view.daily_state_label.text()
    assert view.daily_detail_button.isEnabled()
    view.daily_detail_button.click()
    details = view.daily_trace_label.text()
    assert "候選來源與範圍" in details
    assert "要求檔數：4｜降級檔數：1｜缺漏檔數：2" in details
    assert "全市場分母：未提供" in details
    view.close()


def test_workbench_renders_advice_dto_without_policy_execution() -> None:
    _app()

    view = UnifiedDecisionWorkbenchView(dashboard=_dashboard_with_advice(), auto_refresh=False)

    assert "模式：引導模式" in view.advice_summary.text()
    assert "決策日：2026-07-12｜資料日：2026-07-11" in view.advice_summary.text()
    assert view.advice_metric_cards["formal"].value_label.text() == "1"
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
    assert _advice_warning_text(
        "guided_mode_strategy_advice_contract_missing_or_unverified"
    ) == (
        "此策略版本的作者說明缺少或未核驗；仍提供 Advice，請將此限制納入判斷。"
    )
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
    assert view.advice_metric_cards["formal"].value_label.text() == "1"
    assert view.advice_metric_cards["research"].value_label.text() == "1"
    assert view.advice_metric_cards["allocation"].value_label.text() == "0"
    assert not view.advice_candidate_hint.isHidden()
    assert "每筆 Advice 是一張獨立小卡" in view.advice_candidate_hint.text()
    assert "依序核對來源、閱讀理由與限制" in view.advice_candidate_hint.text()
    assert "不會自動下單" in view.advice_candidate_hint.text()
    assert not view.advice_candidate_cards.isHidden()
    assert len(view._advice_candidate_card_buttons) == 1
    view._show_advice_row_presentation(view.advice_candidate_model, 0)
    assert "策略 Advice｜研究" in view.advice_selection_card.text()
    assert "動作適合度：研究" in view.advice_presentation_detail.toPlainText()
    assert view.advice_presentation_detail.isHidden()
    view.advice_presentation_toggle.click()
    detail = view.advice_presentation_detail.toPlainText()
    assert "本筆資料身份（唯讀）" in detail
    assert "股票：2330" in detail
    assert "Advice 判讀與限制｜唯讀" in detail
    assert detail.index("Advice 判讀與限制｜唯讀") < detail.index(
        "來源理由／論點"
    )
    assert detail.index("來源理由／論點") < detail.index(
        "逐股來源證據｜本筆保存結果"
    )
    assert detail.index("逐股來源證據｜本筆保存結果") < detail.index(
        "策略版本作者說明｜選填"
    )
    assert "適用期間：未提供" in detail
    assert "風險：未提供" in detail
    assert "失效條件：未提供" in detail
    assert "Advice 判讀與限制｜唯讀" in detail


def test_advice_cards_show_saved_comparison_fields_and_centralize_shared_notices() -> None:
    _app()
    dashboard = _dashboard_with_advice()
    candidates = (
        RecommendationAdviceDTO(
            stock_code="2330",
            stock_name="台積電",
            advice_action=AdviceAction.RESEARCH,
            classification=AdviceClassification.PROFESSIONAL_CANDIDATE,
            why_reasons=("成交量高於均值",),
            why_not_reasons=("strategy_advice_contract_missing_or_unverified",),
            risk_reasons=("low_liquidity_review",),
            source_evidence=("Why Not：階段=final_selection；結果=未通過",),
            data_as_of_date="2026-07-11",
            total_score="92.50",
            score_percentile_bp=8_200,
            eligible_universe_size=125,
            eligible_universe_date="2026-07-11",
            industry="半導體",
            close_price="1000.00",
            price_change="1.2",
        ),
        RecommendationAdviceDTO(
            stock_code="2603",
            stock_name="長榮",
            advice_action=AdviceAction.RESEARCH,
            classification=AdviceClassification.PROFESSIONAL_CANDIDATE,
            why_reasons=("突破保存條件",),
            why_not_reasons=("strategy_advice_contract_missing_or_unverified",),
        ),
    )
    advice = AdviceDashboardDTO(
        decision_date="2026-07-12",
        data_as_of_date="2026-07-11",
        mode=AdviceMode.PROFESSIONAL,
        policy=AdvicePolicyConfig(mode=AdviceMode.PROFESSIONAL),
        recommendations=candidates,
        warnings=("market_snapshot_degraded",),
    )
    view = UnifiedDecisionWorkbenchView(
        dashboard=replace(dashboard, advice_dashboard=advice), auto_refresh=False
    )

    assert "market_snapshot_degraded" in view.advice_warning_status.text()
    assert "共用策略／資格限制" in view.advice_warning_status.text()
    first_labels = view._advice_candidate_card_frames[0].findChildren(QLabel)
    first_card_text = "\n".join(label.text() for label in first_labels)
    second_card_text = "\n".join(
        label.text() for label in view._advice_candidate_card_frames[1].findChildren(QLabel)
    )
    assert "規則分數" in first_card_text
    assert "92.50" in first_card_text
    assert "排序參考・非勝率" in first_card_text
    assert "規則分數百分位" in first_card_text
    assert "82.00%" in first_card_text
    assert "排名母體 eligible universe · 資料日 2026-07-11 · N=125" in first_card_text
    assert "產業" in first_card_text and "半導體" in first_card_text
    assert "收盤價" in first_card_text and "1000.00" in first_card_text
    assert "漲跌幅" in first_card_text and "1.2%" in first_card_text
    comparison_panel = view._advice_candidate_card_frames[0].findChild(
        QFrame, "adviceCandidateMetrics"
    )
    assert comparison_panel is not None
    assert "規則分數百分位：82.00%（eligible universe；日期=2026-07-11；N=125）" in (
        comparison_panel.accessibleDescription()
    )
    assert "不代表信心或勝率" in comparison_panel.toolTip()
    assert "信心 92.50" not in first_card_text
    assert "前 82%" not in first_card_text
    assert "Why Not：階段=final_selection；結果=未通過" in first_card_text
    assert "需覆核流動性" in first_card_text
    assert "資料日 2026-07-11" in first_card_text
    assert "market_snapshot_degraded" not in first_card_text
    assert "未提供額外逐股風險資料" in second_card_text
    assert "strategy_advice_contract_missing_or_unverified" not in first_card_text
    assert view.advice_candidate_model.row_at(0).why_not_reasons == (
        "strategy_advice_contract_missing_or_unverified",
    )


def test_professional_candidate_cards_expand_inline_and_keep_selection_bound_to_card() -> None:
    _app()
    dashboard = _dashboard_with_advice()
    candidates = (
        RecommendationAdviceDTO(
            stock_code="2330",
            stock_name="台積電",
            advice_action=AdviceAction.RESEARCH,
            classification=AdviceClassification.PROFESSIONAL_CANDIDATE,
            why_reasons=("research_gate_passed", "volume_confirmation"),
            why_not_reasons=("price_current_session_missing",),
            risk_reasons=("low_liquidity_review",),
            source_evidence=("同筆來源證據 Alpha",),
        ),
        RecommendationAdviceDTO(
            stock_code="2603",
            stock_name="長榮",
            advice_action=AdviceAction.RESEARCH,
            classification=AdviceClassification.PROFESSIONAL_CANDIDATE,
            why_reasons=("retest_observed",),
        ),
        RecommendationAdviceDTO(
            stock_code="2454",
            stock_name="聯發科",
            advice_action=AdviceAction.RESEARCH,
            classification=AdviceClassification.PROFESSIONAL_CANDIDATE,
            why_reasons=("volume_confirmation",),
        ),
    )
    advice = AdviceDashboardDTO(
        decision_date="2026-07-12",
        data_as_of_date="2026-07-11",
        mode=AdviceMode.PROFESSIONAL,
        policy=AdvicePolicyConfig(mode=AdviceMode.PROFESSIONAL),
        recommendations=candidates,
    )
    view = UnifiedDecisionWorkbenchView(
        dashboard=replace(dashboard, advice_dashboard=advice),
        auto_refresh=False,
    )

    assert view.advice_candidate_table.isHidden()
    assert len(view._advice_candidate_card_buttons) == 3
    for width, expected_columns in (
        (1120, 2),
        (1540, 2),
        (1700, 3),
        (700, 1),
    ):
        view.resize(width, 900)
        view._apply_responsive_layout(force=True)
        assert view._advice_candidate_card_columns == expected_columns
    view._layout_advice_candidate_cards(3)
    assert view.advice_candidate_cards_layout.itemAtPosition(0, 0).widget() == (
        view._advice_candidate_card_frames[0]
    )
    assert view.advice_candidate_cards_layout.itemAtPosition(0, 1).widget() == (
        view._advice_candidate_card_frames[1]
    )
    assert view.advice_candidate_cards_layout.itemAtPosition(0, 2).widget() == (
        view._advice_candidate_card_frames[2]
    )
    view._layout_advice_candidate_cards(2)
    assert view.advice_candidate_cards_layout.itemAtPosition(1, 0).widget() == (
        view._advice_candidate_card_frames[2]
    )
    view._layout_advice_candidate_cards(1)
    assert view.advice_candidate_cards_layout.itemAtPosition(1, 0).widget() == (
        view._advice_candidate_card_frames[1]
    )
    assert view.advice_candidate_cards_layout.itemAtPosition(2, 0).widget() == (
        view._advice_candidate_card_frames[2]
    )
    view._layout_advice_candidate_cards(3)
    first = view._advice_candidate_card_buttons[0]
    first.click()

    assert view.advice_candidate_table.selectionModel().currentIndex().row() == 0
    assert not view._advice_candidate_detail_hosts[0].isHidden()
    assert view._advice_candidate_detail_hosts[1].isHidden()
    expanded_position = view.advice_candidate_cards_layout.getItemPosition(
        view.advice_candidate_cards_layout.indexOf(view._advice_candidate_card_frames[0])
    )
    assert expanded_position == (0, 0, 1, 3)
    assert view.advice_candidate_cards_layout.itemAtPosition(1, 0).widget() == (
        view._advice_candidate_card_frames[1]
    )
    assert view.advice_candidate_cards_layout.itemAtPosition(1, 1).widget() == (
        view._advice_candidate_card_frames[2]
    )
    assert view._advice_candidate_detail_hosts[0].isAncestorOf(
        view.advice_selection_detail_panel
    )
    assert "策略 Advice｜研究" in view.advice_selection_card.text()
    candidate_card = view._advice_candidate_card_frames[0]
    summary_texts = tuple(
        label.text() for label in candidate_card.findChildren(QLabel)
    )
    assert "符合研究條件" in summary_texts
    assert "缺少當日價格" in summary_texts
    assert "01" in summary_texts
    assert "研究" in summary_texts
    assert "信心 未提供" in summary_texts
    assert not any(text.startswith("支持理由：") for text in summary_texts)
    assert "同筆來源證據 Alpha" in view.advice_selection_card.toolTip()
    assert "策略 Advice" in view.advice_selection_card.accessibleDescription()
    assert view.advice_selection_card.isHidden()
    assert view.advice_presentation_toggle.parentWidget() is view.advice_selection_detail_panel
    assert view.advice_lineage_button.parentWidget() is view.advice_selection_detail_panel
    assert view.advice_lineage_button.text() == "查看機率依據"
    assert not view.advice_source_heading.isHidden()
    assert not view.advice_source_unavailable_label.isHidden()
    assert "today-source-details" not in view.advice_source_unavailable_label.text()
    detail_layout = view.advice_selection_detail_layout
    assert view.advice_source_heading.text() == "1｜核對每日來源與原始結果"
    assert view.advice_evidence_heading.text() == "2｜閱讀判讀理由與限制"
    assert detail_layout.indexOf(view.advice_source_heading) < detail_layout.indexOf(
        view.advice_evidence_heading
    )
    assert detail_layout.indexOf(view.advice_evidence_heading) < detail_layout.indexOf(
        view.advice_presentation_detail
    )
    assert detail_layout.indexOf(view.advice_presentation_detail) < detail_layout.indexOf(
        view.advice_author_heading
    )
    assert detail_layout.indexOf(view.advice_author_heading) < detail_layout.indexOf(
        view.advice_decision_heading
    )
    assert view.advice_decision_heading.text() == "4｜記錄人工研究決定"
    assert view.advice_follow_up_heading.text() == "後續追蹤（不改變納入／略過決定）"
    assert "重新讀取只刷新狀態" in view.advice_follow_up_hint.text()
    assert "result ID 找回" in view.advice_follow_up_hint.text()
    assert view.advice_contract_backtest_button.text() == "前往策略回測建立新版本"
    assert view.advice_presentation_toggle.sizePolicy().horizontalPolicy() == (
        QSizePolicy.Policy.Fixed
    )
    assert view.advice_lineage_button.sizePolicy().horizontalPolicy() == (
        QSizePolicy.Policy.Fixed
    )
    assert view.advice_presentation_detail.isHidden()
    view.resize(1700, 900)
    view.show()
    _app().processEvents()
    view.advice_presentation_toggle.click()
    view.advice_presentation_detail.setPlainText(
        "長篇判讀欄位：" + ("同筆來源與理由；" * 400)
    )
    _app().processEvents()
    QTest.qWait(20)
    _app().processEvents()
    assert not view.advice_presentation_detail.isHidden()
    assert view.advice_presentation_detail.verticalScrollBar().maximum() == 0
    assert view.advice_selection_detail_panel.minimumHeight() >= (
        view.advice_selection_detail_layout.sizeHint().height()
    )
    assert view._advice_candidate_detail_hosts[0].height() >= (
        view.advice_selection_detail_panel.minimumHeight()
    )
    assert view._advice_candidate_detail_hosts[0].isAncestorOf(
        view.advice_accept_decision_button
    )

    first_reason_label = view._advice_candidate_card_frames[0].findChild(
        QLabel, "adviceCandidateReasonText"
    )
    assert first_reason_label is not None
    QTest.mouseClick(first_reason_label, Qt.LeftButton)
    assert view._advice_candidate_detail_hosts[0].isHidden()
    assert view.advice_selection_detail_panel.isHidden()
    assert view.advice_candidate_cards_layout.itemAtPosition(0, 2).widget() == (
        view._advice_candidate_card_frames[2]
    )

    QTest.mouseClick(view._advice_candidate_card_frames[1], Qt.LeftButton)
    assert view.advice_candidate_table.selectionModel().currentIndex().row() == 1
    assert view._advice_candidate_detail_hosts[0].isHidden()
    assert not view._advice_candidate_detail_hosts[1].isHidden()

    view._advice_candidate_card_buttons[1].click()
    assert view.advice_candidate_table.selectionModel().currentIndex().row() == -1
    assert view._advice_candidate_detail_hosts[0].isHidden()
    assert view._advice_candidate_detail_hosts[1].isHidden()
    assert view.advice_selection_detail_panel.isHidden()
    assert not view._advice_candidate_detail_hosts[1].isAncestorOf(
        view.advice_selection_detail_panel
    )
    assert not view.advice_accept_decision_button.isEnabled()

    view.resize(390, 844)
    view._apply_responsive_layout(force=True)
    assert view.advice_evidence_actions_layout.direction() == QBoxLayout.TopToBottom
    assert view.advice_source_actions_layout.direction() == QBoxLayout.TopToBottom
    narrow_follow_up = view.advice_follow_up_actions_layout
    assert narrow_follow_up.getItemPosition(
        narrow_follow_up.indexOf(view.advice_note_decision_button)
    )[:2] == (0, 0)
    assert narrow_follow_up.getItemPosition(
        narrow_follow_up.indexOf(view.advice_schedule_review_button)
    )[:2] == (0, 1)
    assert narrow_follow_up.getItemPosition(
        narrow_follow_up.indexOf(view.advice_readback_decision_button)
    )[:2] == (1, 0)

    view.resize(1280, 844)
    view._apply_responsive_layout(force=True)
    assert view.advice_evidence_actions_layout.direction() == QBoxLayout.LeftToRight
    assert view.advice_source_actions_layout.direction() == QBoxLayout.LeftToRight
    wide_follow_up = view.advice_follow_up_actions_layout
    assert wide_follow_up.getItemPosition(
        wide_follow_up.indexOf(view.advice_readback_decision_button)
    )[:2] == (0, 2)


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

    assert "本次沒有可顯示的建議" in view.advice_empty_label.text()
    assert "first_warning" in view.advice_empty_label.text()
    assert "second_warning" in view.advice_empty_label.text()
    assert "不會自動補齊缺失資料" in view.advice_empty_label.text()
    assert "原警告：" in view.advice_warning_status.text()
    assert "first_warning\n• second_warning" in view.advice_warning_status.text()
    assert "無合格標的" not in view.advice_warning_status.text()

    no_warning_advice = replace(empty_advice, warnings=())
    no_warning_view = UnifiedDecisionWorkbenchView(
        dashboard=replace(dashboard, advice_dashboard=no_warning_advice),
        auto_refresh=False,
    )
    assert "無原警告回報；這不代表沒有風險" in no_warning_view.advice_warning_status.text()
    assert "沒有說明原因" in no_warning_view.advice_empty_label.text()
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

    assert view.advice_selection_card.maximumHeight() > 160
    assert view.advice_selection_card.wordWrap()
    assert "完整判讀" in view.advice_selection_card.text()
    assert long_reason in view.advice_selection_card.toolTip()
    view.advice_presentation_toggle.click()
    assert "風險：" in view.advice_presentation_detail.toPlainText()
    assert long_risk not in view.advice_selection_card.text()
    assert long_reason in view.advice_selection_card.accessibleDescription()
    assert long_reason in view.advice_presentation_detail.toPlainText()
    assert long_risk in view.advice_selection_card.toolTip()
    assert long_invalidation in view.advice_selection_card.accessibleDescription()
    assert long_risk in view.advice_presentation_detail.toPlainText()
    view.resize(1200, 900)
    view.show()
    _app().processEvents()
    view.advice_presentation_detail.setPlainText(
        "\n".join(f"完整判讀欄位：{long_reason}" for _ in range(40))
    )
    _app().processEvents()
    assert view.advice_presentation_detail.isReadOnly()
    assert view.advice_presentation_detail.minimumHeight() > 480
    assert view.advice_presentation_detail.verticalScrollBar().maximum() == 0
    wide_detail_height = view.advice_presentation_detail.minimumHeight()
    view.resize(390, 844)
    _app().processEvents()
    assert view.advice_presentation_detail.minimumHeight() >= wide_detail_height
    assert view.advice_presentation_detail.verticalScrollBar().maximum() == 0
    assert view.overview_scroll_area.verticalScrollBar().maximum() > 0
    view.close()


def test_advice_exact_saved_source_button_requires_current_row_identity() -> None:
    _app()
    base = _dashboard_with_advice()
    result_id = "saved-result-20260711"
    recommendation = replace(
        base.advice_dashboard.recommendations[0],
        decision_date="2026-07-12",
        data_as_of_date="2026-07-11",
        source_result_id=result_id,
        source_payload_sha256="sha256:" + "a" * 64,
    )
    daily = WorkbenchDailyEvidence(
        status="candidate",
        decision_date="2026-07-12",
        data_as_of_date="2026-07-11",
        headline="候選已保存",
        next_action="回查保存結果",
        market_summary="",
        industry_summary="",
        stock_summary="",
        watchlist_summary="",
        portfolio_summary="",
        candidate_symbols=("2330",),
        candidate_count=1,
        candidate_status="candidate",
        candidate_result_id=result_id,
        candidate_data_date="2026-07-11",
    )
    advice = replace(base.advice_dashboard, recommendations=(recommendation,))
    dashboard = replace(base, advice_dashboard=advice, daily_evidence=daily)
    opened: list[str] = []
    view = UnifiedDecisionWorkbenchView(
        dashboard=dashboard,
        navigate_to_saved_recommendation_callback=lambda selected: opened.append(selected) or True,
        auto_refresh=False,
    )

    view._show_advice_row_presentation(view.advice_recommendation_model, 0)
    assert not view.advice_source_result_button.isHidden()
    assert "result_id=" + result_id in view.advice_source_result_button.toolTip()
    assert "payload SHA-256=sha256:" + "a" * 64 in view.advice_source_result_button.toolTip()
    view.advice_source_result_button.click()
    assert opened == [result_id]


def test_composed_advice_restores_exact_saved_source_and_manual_research_entry() -> None:
    _app()
    result_id = "saved-result-composed-e2e"
    source = RecommendationResultDTO(
        result_id=result_id,
        result_name="每日研究結果",
        config={},
        recommendations=[
            RecommendationDTO(
                stock_code="2330",
                stock_name="台積電",
                close_price=1000,
                price_change=1,
                total_score=90,
                indicator_score=30,
                pattern_score=30,
                volume_score=30,
                recommendation_reasons="策略條件吻合",
                industry="半導體",
                regime_match=True,
            )
        ],
    )
    composed = AdviceComposer(AdvicePolicy()).compose(
        recommendations=source,
        portfolio_result=None,
        evidence_quality="OBSERVED",
        decision_date="2026-07-12",
        data_as_of_date="2026-07-11",
        mode=AdviceMode.GUIDED,
    )
    row = composed.recommendations[0]
    assert row.source_result_id == result_id
    assert row.source_payload_sha256 is None

    base = _dashboard_with_advice()
    daily = WorkbenchDailyEvidence(
        status="candidate",
        decision_date="2026-07-12",
        data_as_of_date="2026-07-11",
        headline="候選已保存",
        next_action="回查保存結果並記錄研究決定",
        market_summary="",
        industry_summary="",
        stock_summary="",
        watchlist_summary="",
        portfolio_summary="",
        candidate_symbols=("2330",),
        candidate_status="candidate",
        candidate_result_id=result_id,
        candidate_source_id="daily-source-composed-e2e",
        candidate_source_snapshot_id="snapshot-composed-e2e",
        candidate_data_date="2026-07-11",
        candidate_quality="degraded",
        candidate_requested_count=5,
        candidate_degraded_count=1,
        candidate_missing_count=2,
        evidence_event_ids=("daily-event-for-ui-test",),
        source_trace=("industry source contract pending",),
    )
    opened: list[str] = []
    history_searches: list[str] = []
    dashboard = replace(base, advice_dashboard=composed, daily_evidence=daily)
    view = UnifiedDecisionWorkbenchView(
        dashboard=dashboard,
        navigate_to_saved_recommendation_callback=lambda selected: opened.append(selected) or True,
        navigate_to_research_history_callback=lambda selected: history_searches.append(selected) or True,
        save_advice_research_decision_callback=lambda action, identity, note: None,
        auto_refresh=False,
    )

    view._show_advice_row_presentation(view.advice_recommendation_model, 0)
    assert not view.advice_source_result_button.isHidden()
    assert not view.advice_daily_source_button.isHidden()
    assert not view.advice_source_heading.isHidden()
    assert view.advice_source_unavailable_label.isHidden()
    assert view.advice_daily_source_button.text() == "今日總覽｜每日來源與排除"
    assert view.advice_source_result_button.text() == "綜合選股｜保存推薦結果"
    assert "result_id=" + result_id in view.advice_daily_source_button.toolTip()
    assert "來源 ID=daily-source-composed-e2e" in view.daily_candidate_detail_label.text()
    assert "候選資料日=2026-07-11" in view.daily_candidate_detail_label.text()
    assert "要求檔數" not in view.daily_candidate_detail_label.text()
    assert not view.advice_research_history_link.isHidden()
    assert "研究紀錄與覆盤" in view.advice_research_history_link.text()
    assert "查找這筆" in view.advice_research_history_link.text()
    assert view.advice_research_history_link.width() <= (
        view.advice_research_history_link.sizeHint().width() + 2
    )
    view.advice_research_history_link.click()
    assert history_searches == [result_id]
    view.advice_daily_source_button.click()
    assert view.daily_detail_button.isChecked()
    assert not view.daily_trace_label.isHidden()
    daily_trace_text = view.daily_trace_label.text()
    assert "本次每日來源（唯讀）" in daily_trace_text
    assert daily_trace_text.index("本次結果") < daily_trace_text.index("篩選與排除")
    assert daily_trace_text.index(result_id) < daily_trace_text.index("篩選與排除")
    assert daily_trace_text.index("候選來源與範圍") < daily_trace_text.index("篩選與排除")
    assert "要求檔數：5｜降級檔數：1｜缺漏檔數：2" in daily_trace_text
    assert "全市場分母：未提供" in daily_trace_text
    assert "研究候選" in daily_trace_text
    assert "來源未提供可顯示的排除摘要；不能據此判定沒有排除。" in daily_trace_text
    assert "daily-event-for-ui-test" not in daily_trace_text
    assert view.daily_trace_advanced_panel.is_collapsed()
    assert "daily-event-for-ui-test" in view.daily_trace_advanced_text.text()
    assert "industry source contract pending" in view.daily_trace_advanced_text.text()
    assert _wait_for_qt(view.advice_accept_decision_button.isEnabled)
    assert view.advice_accept_decision_button.isEnabled()
    assert view._selected_advice_decision_identity == {
        "result_id": result_id,
        "stock_code": "2330",
        "decision_date": "2026-07-12",
        "source_snapshot_id": "snapshot-composed-e2e",
        "source_snapshot_hash": "",
        "identity_status": "linked",
    }
    view.advice_source_result_button.click()
    assert opened == [result_id]
    view._display_exception_dashboard("source read failed")
    assert view.advice_source_result_button.isHidden()
    assert view.advice_daily_source_button.isHidden()
    assert "today-source-details" not in view.advice_source_unavailable_label.text()

    mismatched_daily = replace(daily, candidate_result_id="another-result")
    mismatch_view = UnifiedDecisionWorkbenchView(
        dashboard=replace(dashboard, daily_evidence=mismatched_daily),
        navigate_to_saved_recommendation_callback=lambda selected: opened.append(selected) or True,
        auto_refresh=False,
    )
    mismatch_view._show_advice_row_presentation(
        mismatch_view.advice_recommendation_model, 0
    )
    assert mismatch_view.advice_source_result_button.isHidden()
    assert mismatch_view.advice_daily_source_button.isHidden()
    assert not mismatch_view.advice_source_heading.isHidden()
    assert not mismatch_view.advice_source_unavailable_label.isHidden()
    assert 'href="today-source-details"' in mismatch_view.advice_source_unavailable_label.text()
    assert "不代表來源已與本筆相同" in mismatch_view.advice_source_unavailable_label.text()
    mismatch_view.advice_source_unavailable_label.linkActivated.emit(
        "today-source-details"
    )
    assert mismatch_view.daily_detail_button.isChecked()
    assert not mismatch_view.daily_trace_label.isHidden()
    assert not mismatch_view._open_selected_advice_source_result()
    assert opened == [result_id]


def test_advice_manual_research_decision_requires_exact_current_identity() -> None:
    from types import SimpleNamespace

    _app()
    base = _dashboard_with_advice()
    result_id = "saved-result-manual-decision"
    recommendation = replace(
        base.advice_dashboard.recommendations[0],
        decision_date="2026-07-12",
        data_as_of_date="2026-07-11",
        source_result_id=result_id,
        source_payload_sha256="sha256:" + "c" * 64,
    )
    daily = WorkbenchDailyEvidence(
        status="candidate",
        decision_date="2026-07-12",
        data_as_of_date="2026-07-11",
        headline="候選已保存",
        next_action="記錄研究決定",
        market_summary="",
        industry_summary="",
        stock_summary="",
        watchlist_summary="",
        portfolio_summary="",
        candidate_symbols=("2330",),
        candidate_status="candidate",
        candidate_result_id=result_id,
        candidate_source_snapshot_id="source-snapshot-1",
        candidate_data_date="2026-07-11",
    )
    dashboard = replace(
        base,
        advice_dashboard=replace(base.advice_dashboard, recommendations=(recommendation,)),
        daily_evidence=daily,
    )
    saved: list[tuple[str, dict[str, str], str]] = []
    callback_status: list[tuple[str, str]] = []
    readback_result: list[object] = []
    view_holder: dict[str, UnifiedDecisionWorkbenchView] = {}

    def save(action: str, identity: dict[str, str], note: str) -> object:
        saved.append((action, identity, note))
        view = view_holder.get("view")
        if view is not None:
            callback_status.append((action, view.advice_research_decision_status.text()))
        if action == "readback":
            return readback_result[0]
        return SimpleNamespace(success=True, readback_verified=True, message="測試讀回成功")

    def state(
        identity: dict[str, str],
        *,
        status: str = "linked",
        conflict: str = "",
        decision_status: str = "skipped",
        active_note_count: int = 0,
        next_review_at: str = "",
    ) -> object:
        return SimpleNamespace(
            identity=SimpleNamespace(**{**identity, "identity_status": status}),
            read_error="",
            identity_conflict_reason=conflict,
            decision_status=decision_status,
            active_note_count=active_note_count,
            next_review_at=next_review_at,
        )

    readback_result.append(state(expected_identity := {
        "result_id": result_id,
        "stock_code": "2330",
        "decision_date": "2026-07-12",
        "source_snapshot_id": "source-snapshot-1",
        "source_snapshot_hash": "",
        "identity_status": "linked",
    }))
    view = UnifiedDecisionWorkbenchView(
        dashboard=dashboard,
        save_advice_research_decision_callback=save,
        auto_refresh=False,
    )
    view_holder["view"] = view
    view._show_advice_row_presentation(view.advice_recommendation_model, 0)
    assert "背景讀取" in view.advice_research_decision_status.text()
    assert _wait_for_qt(view.advice_skip_decision_button.isEnabled)
    assert [item[0] for item in saved] == ["readback"]
    assert view.advice_skip_decision_button.isEnabled()
    assert "讀取" in view.advice_readback_decision_button.text()
    assert "hash 未提供" in view.advice_research_decision_status.text()
    view.advice_skip_decision_button.click()
    assert [item[0] for item in saved] == ["readback", "skipped"]
    assert saved[1][1] == expected_identity
    assert saved[1][2] == ""
    assert callback_status[-1] == (
        "skipped",
        "正在保存研究動作並核對同一筆；目前尚未確認結果。",
    )
    assert "已保存並讀回核對" in view.advice_research_decision_status.text()
    assert "不建立交易或 fill" in view.advice_research_decision_status.text()
    assert "回查位置：研究紀錄與覆盤｜查找這筆" in view.advice_research_decision_status.text()
    readback_result[0] = state(expected_identity, active_note_count=0)
    assert _wait_for_qt(view.advice_readback_decision_button.isEnabled)
    view.advice_readback_decision_button.click()
    assert _wait_for_qt(
        lambda: "研究註記=0 筆（不含研究決定）"
        in view.advice_research_decision_status.text()
    )
    readback_result[0] = state(
        expected_identity,
        active_note_count=2,
        next_review_at="2026-07-20T09:30:00+08:00",
    )
    assert _wait_for_qt(view.advice_readback_decision_button.isEnabled)
    view.advice_readback_decision_button.click()
    assert _wait_for_qt(lambda: saved[-1][0] == "readback")
    assert saved[-1][0] == "readback"
    assert _wait_for_qt(
        lambda: "同筆狀態已讀回" in view.advice_research_decision_status.text()
    )
    assert "同筆狀態已讀回" in view.advice_research_decision_status.text()
    assert "回查位置：研究紀錄與覆盤｜查找這筆" in view.advice_research_decision_status.text()
    assert "目前人工決定=已略過" in view.advice_research_decision_status.text()
    assert "研究註記=2 筆（不含研究決定）" in view.advice_research_decision_status.text()
    assert "下次檢視=2026-07-20T09:30:00+08:00" in view.advice_research_decision_status.text()

    readback_result[0] = state(
        expected_identity,
        status="conflict",
        conflict="來源 snapshot 與歷史紀錄衝突",
    )
    assert not view._save_selected_advice_research_decision("readback")
    assert "讀回身分衝突" in view.advice_research_decision_status.text()
    assert "來源 snapshot 與歷史紀錄衝突" in view.advice_research_decision_status.text()

    mismatched_identity = {**expected_identity, "result_id": "other-result"}
    readback_result[0] = state(mismatched_identity)
    assert not view._save_selected_advice_research_decision("readback")
    assert "欄位不符=result_id" in view.advice_research_decision_status.text()
    view._display_exception_dashboard("stale source")
    assert not view.advice_skip_decision_button.isEnabled()
    assert "已 stale" in view.advice_research_decision_status.text()

    mismatched = replace(recommendation, decision_date="2026-07-13")
    blocked_view = UnifiedDecisionWorkbenchView(
        dashboard=replace(
            dashboard,
            advice_dashboard=replace(base.advice_dashboard, recommendations=(mismatched,)),
        ),
        save_advice_research_decision_callback=save,
        auto_refresh=False,
    )
    blocked_view._show_advice_row_presentation(blocked_view.advice_recommendation_model, 0)
    assert not blocked_view.advice_skip_decision_button.isEnabled()
    assert saved[-1][0] == "readback"


def test_advice_schedule_review_uses_taipei_time_and_exact_readback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace

    _app()
    base = _dashboard_with_advice()
    recommendation = replace(
        base.advice_dashboard.recommendations[0],
        decision_date="2026-07-12",
        data_as_of_date="2026-07-11",
        source_result_id="saved-result-review",
    )
    daily = WorkbenchDailyEvidence(
        status="candidate",
        decision_date="2026-07-12",
        data_as_of_date="2026-07-11",
        headline="候選已保存",
        next_action="設定研究檢視時間",
        market_summary="",
        industry_summary="",
        stock_summary="",
        watchlist_summary="",
        portfolio_summary="",
        candidate_symbols=(recommendation.stock_code,),
        candidate_status="candidate",
        candidate_result_id="saved-result-review",
        candidate_source_snapshot_id="source-snapshot-review",
        candidate_data_date="2026-07-11",
    )
    dashboard = replace(
        base,
        advice_dashboard=replace(
            base.advice_dashboard,
            recommendations=(recommendation,),
        ),
        daily_evidence=daily,
    )
    calls: list[tuple[str, dict[str, str], str]] = []

    def save(
        action: str,
        identity: dict[str, str],
        note: str,
        *,
        next_review_at: str = "",
    ) -> object:
        calls.append((action, dict(identity), next_review_at))
        linked_identity = SimpleNamespace(**{**identity, "identity_status": "linked"})
        if action == "readback":
            return SimpleNamespace(
                identity=linked_identity,
                read_error="",
                identity_conflict_reason="",
                decision_status="unrecorded",
                active_note_count=0,
                next_review_at="",
            )
        return SimpleNamespace(
            success=True,
            readback_verified=True,
            message="下次檢視已保存。",
            state=SimpleNamespace(
                identity=linked_identity,
                read_error="",
                next_review_at=next_review_at,
            ),
        )

    monkeypatch.setattr(QDialog, "exec", lambda _dialog: QDialog.Accepted)
    monkeypatch.setattr(
        QDateTimeEdit,
        "dateTime",
        lambda _editor: QDateTime.fromString(
            "2026-10-30 09:00:00", "yyyy-MM-dd HH:mm:ss"
        ),
    )
    view = UnifiedDecisionWorkbenchView(
        dashboard=dashboard,
        save_advice_research_decision_callback=save,
        auto_refresh=False,
    )
    view._show_advice_row_presentation(view.advice_recommendation_model, 0)
    assert _wait_for_qt(view.advice_schedule_review_button.isEnabled)

    assert view.advice_schedule_review_button.isEnabled()
    view.advice_schedule_review_button.click()

    assert calls[-1][0] == "review_scheduled"
    assert calls[-1][2] == "2026-10-30T09:00:00+08:00"
    assert "已保存並讀回核對" in view.advice_research_decision_status.text()
    assert "不建立交易或 fill" in view.advice_research_decision_status.text()

    view._dashboard_stale = True
    call_count = len(calls)
    assert not view._schedule_selected_advice_review()
    assert len(calls) == call_count
    assert "未設定下次檢視" in view.advice_research_decision_status.text()
    view.close()


def test_advice_reason_capsules_show_longer_summary_and_announce_full_detail() -> None:
    _app()
    dashboard = _dashboard_with_advice()
    long_reason = "成交量放大、MACD金叉及均線多頭排列；" * 5
    candidate = replace(
        dashboard.advice_dashboard.recommendations[0],
        classification=AdviceClassification.PROFESSIONAL_CANDIDATE,
        why_reasons=(long_reason,),
    )
    advice = replace(
        dashboard.advice_dashboard,
        mode=AdviceMode.PROFESSIONAL,
        recommendations=(candidate,),
    )
    view = UnifiedDecisionWorkbenchView(
        dashboard=replace(dashboard, advice_dashboard=advice), auto_refresh=False
    )

    reason_label = view._advice_candidate_card_frames[0].findChild(
        QLabel, "adviceCandidateReasonText"
    )
    assert reason_label is not None
    assert len(reason_label.text()) > 42
    assert reason_label.text().endswith("…")
    assert "精簡理由" in reason_label.accessibleDescription()
    assert "點擊卡片" in reason_label.toolTip()

    view.close()


def test_advice_manual_decision_persists_and_reads_back_from_fresh_journal(
    tmp_path,
) -> None:
    """Workbench Advice 的明確人工決定須沿 exact identity 保存並可冷讀回。"""
    from types import SimpleNamespace

    from app_module.decision_continuity_controller import DecisionContinuityController
    from app_module.dtos.decision_continuity_dtos import DecisionIdentity
    from app_module.journal_service import JournalService
    from ui_qt.main import MainWindow

    _app()
    result_id = "saved-result-advice-journal-roundtrip"
    source_snapshot_id = "saved-snapshot-advice-journal-roundtrip"
    base = _dashboard_with_advice()
    recommendation = replace(
        base.advice_dashboard.recommendations[0],
        decision_date="2026-07-12",
        data_as_of_date="2026-07-11",
        source_result_id=result_id,
        source_payload_sha256="sha256:" + "c" * 64,
    )
    daily = WorkbenchDailyEvidence(
        status="candidate",
        decision_date="2026-07-12",
        data_as_of_date="2026-07-11",
        headline="候選已保存",
        next_action="記錄研究決定",
        market_summary="",
        industry_summary="",
        stock_summary="",
        watchlist_summary="",
        portfolio_summary="",
        candidate_symbols=("2330",),
        candidate_status="candidate",
        candidate_result_id=result_id,
        candidate_source_snapshot_id=source_snapshot_id,
        candidate_data_date="2026-07-11",
    )
    dashboard = replace(
        base,
        advice_dashboard=replace(
            base.advice_dashboard,
            recommendations=(recommendation,),
        ),
        daily_evidence=daily,
    )
    output_root = tmp_path / "isolated-output"
    config = SimpleNamespace(
        output_root=output_root,
        resolve_output_path=lambda name: output_root / name,
    )
    controller = DecisionContinuityController(JournalService(config))
    host = SimpleNamespace(decision_continuity_controller=controller)

    def save(action, identity, note, *, next_review_at=""):
        return MainWindow._save_workbench_advice_research_decision(
            host,
            action,
            identity,
            note,
            next_review_at=next_review_at,
        )

    view = UnifiedDecisionWorkbenchView(
        dashboard=dashboard,
        save_advice_research_decision_callback=save,
        auto_refresh=False,
    )
    view._show_advice_row_presentation(view.advice_recommendation_model, 0)
    assert _wait_for_qt(view.advice_skip_decision_button.isEnabled)
    assert view.advice_skip_decision_button.isEnabled()
    view.advice_skip_decision_button.click()
    assert "已保存並讀回核對" in view.advice_research_decision_status.text()

    journal_path = output_root / "portfolio" / "journal_entries.jsonl"
    assert journal_path.is_file()
    journal_bytes_after_save = journal_path.read_bytes()
    assert b"workbench_advice" in journal_bytes_after_save
    assert result_id.encode() in journal_bytes_after_save
    assert b"2330" in journal_bytes_after_save
    assert not (output_root / "portfolio" / "trades.jsonl").exists()

    identity = DecisionIdentity(
        result_id=result_id,
        stock_code="2330",
        decision_date="2026-07-12",
        source_snapshot_id=source_snapshot_id,
        source_snapshot_hash="",
        identity_status="linked",
    )
    reopened = DecisionContinuityController(JournalService(config)).read_state(
        identity
    )
    assert reopened.identity.result_id == result_id
    assert reopened.identity.stock_code == "2330"
    assert reopened.identity.decision_date == "2026-07-12"
    assert reopened.identity.source_snapshot_id == source_snapshot_id
    assert reopened.identity.source_snapshot_hash == ""
    assert reopened.decision_status == "skipped"
    assert len(reopened.history) == 1
    assert reopened.history[0].decision_identity == identity
    assert reopened.history[0].payload.get("source_id") == "workbench_advice"
    other_identity = replace(identity, result_id="another-saved-result")
    assert (
        DecisionContinuityController(JournalService(config))
        .read_state(other_identity)
        .decision_status
        == "unrecorded"
    )
    view.close()


def test_advice_source_identity_round_trips_and_rejects_invalid_hash() -> None:
    row = RecommendationAdviceDTO(
        stock_code="2330",
        advice_action=AdviceAction.RESEARCH,
        source_result_id="saved-result-1",
        source_payload_sha256="sha256:" + "b" * 64,
    )
    assert RecommendationAdviceDTO.from_dict(row.to_dict()) == row
    with pytest.raises(ValueError, match="canonical SHA-256"):
        replace(row, source_payload_sha256="not-a-hash")


def test_formal_advice_uses_cards_and_optional_portfolio_stays_in_table() -> None:
    _app()
    dashboard = _dashboard_with_advice()
    one_row_view = UnifiedDecisionWorkbenchView(dashboard=dashboard, auto_refresh=False)
    assert one_row_view.advice_recommendation_model.rowCount() == 1
    assert one_row_view.advice_candidate_model.rowCount() == 1
    assert one_row_view.advice_recommendation_table.isHidden()
    assert not one_row_view.advice_candidate_cards.isHidden()
    assert len(one_row_view._advice_candidate_card_buttons) == 1
    assert one_row_view.advice_candidate_table.isHidden()
    assert not one_row_view.advice_portfolio_table.isHidden()

    card_texts = tuple(
        label.text()
        for label in one_row_view._advice_candidate_card_frames[0].findChildren(QLabel)
    )
    assert "暫不新增部位" in card_texts
    assert not any(text.startswith("支持理由：") for text in card_texts)
    one_row_view._advice_candidate_card_buttons[0].click()
    assert one_row_view._expanded_advice_candidate_row == 0
    assert not one_row_view._advice_candidate_detail_hosts[0].isHidden()
    assert one_row_view._advice_candidate_detail_hosts[0].isAncestorOf(
        one_row_view.advice_selection_detail_panel
    )
    one_row_view.close()

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
    assert many_row_view.advice_recommendation_model.rowCount() == 5
    assert many_row_view.advice_candidate_model.rowCount() == 5
    assert many_row_view.advice_recommendation_table.isHidden()
    assert not many_row_view.advice_candidate_cards.isHidden()
    assert len(many_row_view._advice_candidate_card_buttons) == 5
    assert many_row_view.advice_candidate_table.isHidden()
    assert many_row_view.advice_portfolio_table.isHidden()
    many_row_view.close()
