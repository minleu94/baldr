from __future__ import annotations

import os
import sys
from dataclasses import replace
from datetime import date, datetime

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from app_module.workbench_dtos import (
    WorkbenchAccessBoundary,
    WorkbenchDashboardDTO,
    WorkbenchDailyEvidence,
    WorkbenchEvidenceWindow,
    WorkbenchLearningReceipt,
)
from app_module.research_session import ResearchStockContextDTO
from ui_qt.views.workbench_view import UnifiedDecisionWorkbenchView


def _app() -> QApplication:
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication(sys.argv)
    return instance


def _dashboard() -> WorkbenchDashboardDTO:
    daily = WorkbenchDailyEvidence(
        status="waiting_for_time",
        decision_date="2026-09-14",
        data_as_of_date="2026-09-14",
        headline="2026-09-14：市場可讀；今日 1 檔研究候選。",
        next_action="等待下一個官方交易日的可見價格觀測。",
        market_summary="市場：趨勢追蹤｜資料日 2026-09-14｜品質 degraded",
        industry_summary="產業：領先 金融｜落後 電子｜品質 observed",
        stock_summary="個股研究候選：1528 恩德",
        watchlist_summary="觀察清單：觸發 0 檔｜品質 observed",
        portfolio_summary="持倉：警示 1 檔（2330）｜品質 estimated",
        candidate_symbols=("1528",),
        candidate_count=1,
        candidate_status="candidate_degraded",
        candidate_result_id="scheduled-rec-1",
        candidate_source_id="scheduled-rec-1",
        candidate_source_snapshot_id="snapshot-1",
        candidate_data_date="2026-09-14",
        candidate_quality="degraded",
        candidate_requested_count=120,
        candidate_degraded_count=2,
        candidate_missing_count=1,
        candidate_reasons=("1528 恩德｜產業 電機機械｜理由 圖形模式分數+",),
        candidate_exclusion_summaries=(
            "篩選缺資料：197 筆／197 檔；品質 missing 197；理由碼 source_data_missing 197。",
        ),
        candidate_identity=("cohort_hash=sha256:cohort-1",),
        evidence_event_type="recommendation_included",
        evidence_scope_start="2026-09-10",
        evidence_scope_end="2026-09-14",
        evidence_event_count=1,
        evidence_daily_event_count=1,
        evidence_skipped_incomplete_identity=2,
        evidence_event_ids=("evt-complete",),
        evidence_source_snapshot_ids=("scheduled-rec-1",),
        outcome_total=4,
        outcome_pending=4,
        outcome_windows=(5, 10, 20, 60),
        evidence_windows=(
            WorkbenchEvidenceWindow(window_days=5, total=1, pending=1),
            WorkbenchEvidenceWindow(window_days=10, total=1, pending=1),
            WorkbenchEvidenceWindow(window_days=20, total=1, pending=1),
            WorkbenchEvidenceWindow(window_days=60, total=1, pending=1),
        ),
        learning=WorkbenchLearningReceipt(
            schema_version="daily-recommendation-learning-cli-result.v3",
            status="completed",
            decision_date="2026-09-14",
            checked_at="2026-09-14T20:47:26+08:00",
            decision="retain_current",
            decision_reason="natural_forward_evidence_receipt_missing",
            candidate_id="candidate-1",
            candidate_status="challenger_candidate",
            active_pointer_status="rule_only",
            natural_matured_sample_count=0,
            candidate_natural_matured_sample_count=0,
            active_natural_matured_sample_count=0,
            decision_receipt_id="decision-1",
            decision_receipt_hash="sha256:receipt-1",
        ),
        source_trace=(
            "recommendation_snapshot.result_id=scheduled-rec-1",
            "evidence_event[evt-complete].event_hash=sha256:event-1",
        ),
    )
    return WorkbenchDashboardDTO(
        as_of_date=date(2026, 9, 14),
        generated_at=datetime(2026, 9, 14, 12, 0, 0),
        source_mode="read_only_sources",
        access_boundary=WorkbenchAccessBoundary(),
        status_strip=(),
        review_items=(),
        evidence_summary=(),
        market_context={"source_status": "ready"},
        portfolio_watchlist_summary={},
        daily_checklist=(),
        daily_evidence=daily,
    )


def test_daily_candidate_opens_direct_stock_research_context_without_watchlist_membership() -> None:
    _app()
    contexts: list[ResearchStockContextDTO] = []
    watchlist_calls: list[str] = []
    view = UnifiedDecisionWorkbenchView(
        dashboard=_dashboard(),
        auto_refresh=False,
        navigate_to_stock_research_callback=lambda context: contexts.append(context),
        navigate_to_watchlist_callback=lambda: watchlist_calls.append("watchlist"),
    )

    assert view.daily_candidate_button.isEnabled() is True
    assert view.daily_candidate_button.text() == "開啟 1528 個股研究報告"
    view.daily_candidate_button.click()

    assert len(contexts) == 1
    context = contexts[0]
    assert context.stock_code == "1528"
    assert context.decision_date == "2026-09-14"
    assert context.data_date == "2026-09-14"
    assert context.result_id == "scheduled-rec-1"
    assert context.source_id == "scheduled-rec-1"
    assert context.source_workspace == "workbench"

    assert view.workflow_collapsible.is_collapsed() is True
    assert "直接開啟" in view.workflow_path_note.text()

    view.daily_watchlist_button.click()
    assert watchlist_calls == ["watchlist"]


def test_daily_journey_details_are_collapsed_until_requested_and_evidence_tab_is_reachable() -> None:
    _app()
    view = UnifiedDecisionWorkbenchView(dashboard=_dashboard(), auto_refresh=False)

    assert view.daily_trace_label.isHidden() is True
    assert "sha256:event-1" not in view.daily_candidate_detail_label.text()
    assert "來源 ID=scheduled-rec-1" in view.daily_candidate_detail_label.text()
    assert "candidate_degraded" not in view.daily_candidate_detail_label.text()
    assert "候選資料日=2026-09-14" in view.daily_candidate_detail_label.text()
    assert "要求檔數" not in view.daily_candidate_detail_label.text()
    assert "全市場分母" not in view.daily_candidate_detail_label.text()
    assert "合格事件 1 件" in view.daily_evidence_card.value_label.text()
    assert "recommendation_included" not in view.daily_journey_label.text()
    assert "active pointer" not in view.daily_journey_label.text()
    view.daily_detail_button.click()
    assert view.daily_trace_label.isHidden() is False
    assert view.daily_detail_button.isChecked()
    assert view.daily_detail_button.text() == "收合來源／範圍／排除"
    assert "sha256:event-1" not in view.daily_trace_label.text()
    assert "border-left" in view.daily_trace_label.text()
    assert "候選來源與範圍" in view.daily_trace_label.text()
    assert "要求檔數：120｜降級檔數：2｜缺漏檔數：1" in view.daily_trace_label.text()
    assert "全市場分母：未提供" in view.daily_trace_label.text()
    assert "篩選缺資料：197 筆／197 檔" in view.daily_trace_label.text()
    assert "品質 missing 197" in view.daily_trace_label.text()
    advanced_trace = view.daily_trace_advanced_text.text()
    assert "sha256:event-1" in advanced_trace
    assert "自然成熟樣本：回執 0；候選 0；啟用版本 0" in advanced_trace
    view.daily_detail_button.click()
    assert view.daily_trace_label.isHidden() is True
    assert not view.daily_detail_button.isChecked()
    assert view.daily_detail_button.text() == "展開來源／範圍／排除"
    assert view.daily_detail_button.arrowType() == Qt.ArrowType.RightArrow

    view.daily_detail_button.click()
    view._render_daily_investment_journey(_dashboard().daily_evidence)
    assert not view.daily_detail_button.isChecked()
    assert view.daily_detail_button.text() == "展開來源／範圍／排除"
    assert view.daily_trace_label.isHidden() is True

    view.daily_evidence_button.click()
    assert view.subtabs.currentWidget() is view.research_console_view
    assert view.subtabs.tabText(view.subtabs.currentIndex()) == "研究證據"


def test_daily_candidate_disclosure_remains_visible_for_empty_candidate_result() -> None:
    _app()
    daily = _dashboard().daily_evidence
    assert daily is not None
    empty_daily = WorkbenchDailyEvidence(
        status=daily.status,
        decision_date=daily.decision_date,
        data_as_of_date=daily.data_as_of_date,
        headline="沒有候選列",
        next_action=daily.next_action,
        market_summary=daily.market_summary,
        industry_summary=daily.industry_summary,
        stock_summary="",
        watchlist_summary=daily.watchlist_summary,
        portfolio_summary=daily.portfolio_summary,
        candidate_count=0,
        candidate_status="missing",
        candidate_quality="missing",
    )
    view = UnifiedDecisionWorkbenchView(
        dashboard=replace(_dashboard(), daily_evidence=empty_daily),
        auto_refresh=False,
    )

    disclosure = view.daily_candidate_detail_label.text()
    assert "目前無候選列或來源理由可供檢視" in disclosure
    assert "來源 ID=未提供" in disclosure
    assert "要求檔數" not in disclosure
    assert "全市場分母" not in disclosure
