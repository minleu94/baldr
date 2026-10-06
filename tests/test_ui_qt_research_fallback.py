from __future__ import annotations

import os
import sys
from datetime import date, datetime
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app_module.daily_investment_journey import (
    DailyInvestmentJourneyService,
    _CandidateRead,
    _EvidenceRead,
    _PendingHorizonAnchor,
)
from app_module.recommendation_learning_evidence_projection_service import (
    LearningHorizonProjection,
    LearningLaneProjection,
    RecommendationLearningEvidenceProjection,
)
from app_module.workbench_dtos import (
    ResearchFallbackPacket,
    WorkbenchAccessBoundary,
    WorkbenchDashboardDTO,
    WorkbenchDailyEvidence,
    WorkbenchLearningReceipt,
)
from app_module.v4_evidence_identity import DEFAULT_RETURN_BASIS
from ui_qt.views.workbench_view import UnifiedDecisionWorkbenchView


def _app() -> QApplication:
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication(sys.argv)
    return instance


def _dashboard(packet: ResearchFallbackPacket | None) -> WorkbenchDashboardDTO:
    missing = packet is not None and packet.status == "missing_data"
    pending = packet is not None and packet.status == "pending_natural_evidence"
    daily = WorkbenchDailyEvidence(
        status="degraded" if packet is not None else "ready",
        decision_date="2026-09-14",
        data_as_of_date="2026-09-14",
        headline=(
            "今日 evidence 狀態可讀，已有自然成熟樣本。"
            if packet is None
            else "今日 evidence 狀態可讀，但研究判讀依 packet 限制。"
        ),
        next_action=(
            "依既有證據成熟度閱讀。"
            if packet is None
            else "依研究 fallback packet 完成下一個唯讀檢查。"
        ),
        market_summary="市場：可讀",
        industry_summary="產業：可讀",
        stock_summary="個股研究候選：2330",
        watchlist_summary="觀察清單：觸發 0 檔",
        portfolio_summary="持倉：警示未知",
        candidate_symbols=("2330",),
        candidate_count=1,
        candidate_status="candidate",
        candidate_result_id="result-a",
        candidate_source_id="source-a",
        candidate_source_snapshot_id="snapshot-a",
        candidate_data_date="2026-09-14",
        evidence_event_count=0 if missing else 1,
        outcome_total=0 if missing else 1,
        outcome_ready=0 if missing or pending else 1,
        outcome_pending=1 if pending else 0,
        learning=(
            WorkbenchLearningReceipt(
                schema_version="fixture.v1",
                status="completed",
                decision_date="2026-09-14",
                checked_at="2026-09-14T12:00:00+08:00",
                decision="retain_current",
                decision_reason="fixture",
                active_pointer_status="active" if packet is None else "rule_only",
                active_natural_matured_sample_count=3 if packet is None else 0,
            )
            if packet is None or pending or (
                packet is not None and packet.status == "blocked_identity_or_cost"
            )
            else None
        ),
        research_fallback=packet,
        source_trace=("fixture:research_fallback",),
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


class _UnknownCalendar:
    def is_official_trading_day(self, target_date, *, allow_online_probe: bool = False):
        return None, "isolated_fixture_has_no_official_calendar"


def _projection(status: str) -> RecommendationLearningEvidenceProjection:
    horizon_status = "matured" if status == "verified" else "pending"
    reason = "candidate capture identity mismatch" if status == "blocked_provenance" else "fixture"
    horizon = LearningHorizonProjection(
        horizon_days=5,
        status=horizon_status,
        reason="fixture",
    )
    candidate_lane = LearningLaneProjection(
        lane_id="candidate_natural",
        label="候選 natural evidence",
        status=status,
        reason=reason,
        candidate_id="candidate-a",
        cost_scenario_id="cost-1",
        capture_status="recorded" if status != "missing" else "not_recorded",
        horizons=(horizon,),
    )
    active_lane = LearningLaneProjection(
        lane_id="active_model_natural",
        label="active model natural evidence",
        status="not_applicable",
        reason="active_pointer_not_active",
    )
    return RecommendationLearningEvidenceProjection(
        schema_version="fixture.v1",
        status=status,
        requested_date="2026-09-14",
        learning_decision_date="2026-09-14",
        checked_at="2026-09-14T12:00:00+08:00",
        decision="retain_current",
        decision_reason="fixture",
        candidate_id="candidate-a",
        candidate_model_version="candidate-a",
        candidate_training_as_of=None,
        data_recorded_status="recorded" if status != "missing" else "not_recorded",
        data_recorded_reason=reason,
        next_gap="fixture",
        adoption_reason="fixture",
        candidate_lane=candidate_lane,
        active_lane=active_lane,
        horizons=(horizon,),
        horizon_scope_lane_id="candidate_natural",
        horizon_scope_label="候選 natural evidence",
        horizon_scope_cost_scenario_id="cost-1",
        cost_lane="banktaiwan_estimated_research",
    )


def _packet(status: str) -> ResearchFallbackPacket | None:
    service = DailyInvestmentJourneyService(
        SimpleNamespace(output_root=".", db_file="evidence.sqlite"),
        trading_calendar=_UnknownCalendar(),
    )
    candidate = _CandidateRead(
        status="candidate",
        result_id="result-a",
        source_id="source-a",
        source_snapshot_id="snapshot-a",
        symbols=("2330",),
        identity=(
            "strategy_version_id=strategy-1",
            "cost_model_id=cost-1",
            "cost_scenario_id=cost-1",
            "benchmark_id=TAIEX",
            "horizon_days=20",
            "learning_candidate_id=candidate-a",
        ),
        source_trace=("fixture:candidate",),
    )
    anchor = _PendingHorizonAnchor(
        horizon_days=5,
        decision_date="2026-09-14",
        symbol="2330",
        source_id="source-a",
        source_snapshot_id="snapshot-a",
        identity=(
            ("result_id", "result-a"),
            ("strategy_version_id", "strategy-1"),
            ("cost_model_id", "cost-1"),
            ("cost_scenario_id", "cost-1"),
            ("benchmark_id", "TAIEX"),
            ("horizon_days", "20"),
            ("learning_candidate_id", "candidate-a"),
        ),
        window_type="trading_days",
        return_basis=DEFAULT_RETURN_BASIS,
    )
    evidence = _EvidenceRead(
        status="waiting_for_time" if status == "pending_natural_evidence" else "missing" if status == "missing_data" else "ready",
        event_count=0 if status == "missing_data" else 1,
        outcome_total=0 if status == "missing_data" else 1,
        outcome_ready=1 if status not in {"missing_data", "pending_natural_evidence"} else 0,
        outcome_pending=1 if status == "pending_natural_evidence" else 0,
        pending_horizon_anchors=(anchor,) if status == "pending_natural_evidence" else (),
        source_trace=("fixture:evidence",),
    )
    projection_status = {
        "not_needed": "verified",
        "missing_data": "missing",
        "blocked_identity_or_cost": "blocked_provenance",
        "pending_natural_evidence": "pending",
    }[status]
    return service._build_research_fallback_packet(
        decision_date="2026-09-14",
        candidate=candidate,
        evidence=evidence,
        recommendation_learning_projection=_projection(projection_status),
    )


def test_workbench_surfaces_fallback_summary_and_detail_without_approve_action() -> None:
    _app()
    view = UnifiedDecisionWorkbenchView(
        dashboard=_dashboard(_packet("blocked_identity_or_cost")),
        auto_refresh=False,
    )

    summary = view.daily_journey_label.text()
    assert "研究 fallback：推薦、來源或成本版本不一致。" in summary
    assert "下一步：查看來源詳情定位衝突，再重新整理。" in summary
    assert "下一步：" in summary
    assert "再看時間：尚無法判定" in summary
    assert "目前不能下有效機率、權重或買賣結論" in summary
    assert "批准" not in summary

    view.daily_detail_button.click()
    detail = view.daily_trace_label.text()
    assert "Research fallback packet（唯讀）" in detail
    assert "source_owner=未知（既有來源未提供 owner）" in detail
    assert "owner_known=False" in detail
    assert "prohibited_actions：" in detail
    assert "不可下單" in detail


def test_workbench_surfaces_normal_and_missing_fallback_states() -> None:
    _app()
    normal = UnifiedDecisionWorkbenchView(
        dashboard=_dashboard(None),
        auto_refresh=False,
    )
    assert "研究 fallback" not in normal.daily_journey_label.text()
    assert "已有自然成熟樣本" in normal.daily_journey_label.text()

    missing_packet = _packet("missing_data")
    missing = UnifiedDecisionWorkbenchView(
        dashboard=_dashboard(missing_packet),
        auto_refresh=False,
    )
    assert "研究 fallback：缺少這次推薦的後續證據。" in missing.daily_journey_label.text()
    assert "目前不能下有效機率、權重或買賣結論" in missing.daily_journey_label.text()

    pending = UnifiedDecisionWorkbenchView(
        dashboard=_dashboard(_packet("pending_natural_evidence")),
        auto_refresh=False,
    )
    assert "研究 fallback：這次推薦的後續價格觀測尚未成熟。" in pending.daily_journey_label.text()
    assert "再看時間：尚無法判定" in pending.daily_journey_label.text()
