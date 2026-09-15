from __future__ import annotations

import os
import sys
from datetime import date, datetime

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

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
        candidate_reasons=("1528 恩德｜產業 電機機械｜理由 圖形模式分數+",),
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
    assert context.source_workspace == "recommendation"

    assert view.workflow_collapsible.is_collapsed() is True
    assert "直接開啟" in view.workflow_path_note.text()

    view.daily_watchlist_button.click()
    assert watchlist_calls == ["watchlist"]


def test_daily_journey_details_are_collapsed_until_requested_and_evidence_tab_is_reachable() -> None:
    _app()
    view = UnifiedDecisionWorkbenchView(dashboard=_dashboard(), auto_refresh=False)

    assert view.daily_trace_label.isHidden() is True
    assert "sha256:event-1" not in view.daily_candidate_detail_label.text()
    assert "scheduled-rec-1" not in view.daily_candidate_detail_label.text()
    assert "candidate_degraded" not in view.daily_candidate_detail_label.text()
    assert "合格事件 1 件" in view.daily_evidence_card.value_label.text()
    assert "recommendation_included" not in view.daily_journey_label.text()
    assert "active pointer" not in view.daily_journey_label.text()
    view.daily_detail_button.click()
    assert view.daily_trace_label.isHidden() is False
    assert "sha256:event-1" in view.daily_trace_label.text()
    assert "candidate natural=0" in view.daily_trace_label.text()
    assert "active natural=0" in view.daily_trace_label.text()
    view.daily_detail_button.click()
    assert view.daily_trace_label.isHidden() is True

    view.daily_evidence_button.click()
    assert view.subtabs.tabText(view.subtabs.currentIndex()) == "Evidence"
