"""以實際 Workbench Qt widget 驗證 Research fallback 多種呈現狀態。"""

from __future__ import annotations

import argparse
from datetime import date, datetime
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

project_root = Path(__file__).resolve().parents[1]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

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
from ui_qt.main import apply_app_theme
from ui_qt.views.workbench_view import UnifiedDecisionWorkbenchView


class _UnknownCalendar:
    def is_official_trading_day(self, target_date, *, allow_online_probe: bool = False):
        return None, "isolated_fixture_has_no_official_calendar"


def _projection(status: str) -> RecommendationLearningEvidenceProjection:
    horizon_status = "matured" if status == "verified" else "pending"
    reason = "candidate capture identity mismatch" if status == "blocked_provenance" else "fixture"
    horizon = LearningHorizonProjection(
        horizon_days=5,
        status=horizon_status,
        reason=reason,
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
        decision_reason=reason,
        candidate_id="candidate-a",
        candidate_model_version="candidate-a",
        candidate_training_as_of=None,
        data_recorded_status="recorded" if status != "missing" else "not_recorded",
        data_recorded_reason=reason,
        next_gap="fixture",
        adoption_reason=reason,
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


def _dashboard(packet: ResearchFallbackPacket | None) -> WorkbenchDashboardDTO:
    packet_status = packet.status if packet is not None else "not_needed"
    missing = packet_status == "missing_data"
    pending = packet_status == "pending_natural_evidence"
    daily = WorkbenchDailyEvidence(
        status="ready" if packet is None else "degraded",
        decision_date="2026-09-14",
        data_as_of_date="2026-09-14",
        headline=(
            "隔離 DTO fixture（非實際資料 lane；僅驗證 UI 呈現）。已有自然成熟樣本。"
            if packet is None
            else "隔離 DTO fixture（非實際資料 lane；僅驗證 UI 呈現）。研究判讀依 packet 限制。"
        ),
        next_action=(
            "依既有證據成熟度閱讀。"
            if packet is None
            else "依 packet 完成下一個唯讀檢查。"
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
        source_trace=("qa:research_fallback_fixture",),
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


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Research fallback Qt screenshot QA")
    parser.add_argument(
        "--output-dir",
        default=str(Path("output") / "qa" / "research_fallback_qt"),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication(sys.argv)
    apply_app_theme(app)
    results: list[dict[str, object]] = []
    try:
        for name, status, expected in (
            ("normal", "not_needed", "已有自然成熟樣本"),
            ("missing", "missing_data", "研究 fallback：缺少這次推薦的後續證據。"),
            ("conflict", "blocked_identity_or_cost", "研究 fallback：推薦、來源或成本版本不一致。"),
            ("pending_natural", "pending_natural_evidence", "研究 fallback：這次推薦的後續價格觀測尚未成熟。"),
        ):
            view = UnifiedDecisionWorkbenchView(
                dashboard=_dashboard(_packet(status)),
                auto_refresh=False,
            )
            view.resize(1440, 900)
            view.show()
            app.processEvents()
            summary = view.daily_journey_label.text()
            if name == "normal":
                expected_present = expected in summary and "研究 fallback" not in summary
            else:
                expected_present = expected in summary
            if not expected_present:
                raise AssertionError(f"{name} summary 缺少預期文字：{expected}")
            if not view.daily_trace_label.isHidden():
                raise AssertionError(f"{name} 詳情預設應收合")
            collapsed_screenshot = output_dir / f"workbench_research_fallback_{name}_collapsed.png"
            collapsed_pixmap = view.grab()
            if collapsed_pixmap.isNull() or not collapsed_pixmap.save(str(collapsed_screenshot)):
                raise AssertionError(f"{name} collapsed screenshot 保存失敗")
            view.daily_detail_button.click()
            app.processEvents()
            detail = view.daily_trace_label.text()
            if name == "normal":
                if "Research fallback packet（唯讀）" in detail:
                    raise AssertionError("normal 狀態不應塞入 fallback packet 詳情")
            elif "source_owner=未知（既有來源未提供 owner）" not in detail:
                raise AssertionError(f"{name} detail 未明示 owner unknown")
            expanded_screenshot = output_dir / f"workbench_research_fallback_{name}_expanded.png"
            pixmap = view.grab()
            if pixmap.isNull() or not pixmap.save(str(expanded_screenshot)):
                raise AssertionError(f"{name} screenshot 保存失敗")
            results.append(
                {
                    "name": name,
                    "status": status,
                    "summary": summary,
                    "detail_default": "collapsed",
                    "collapsed_screenshot": str(collapsed_screenshot),
                    "expanded_screenshot": str(expanded_screenshot),
                    "font_family": app.font().family(),
                    "font_point_size": app.font().pointSize(),
                }
            )
            view.close()
            view.deleteLater()
            app.processEvents()
    finally:
        app.quit()
    summary_path = output_dir / "summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "status": "passed",
                "evidence_kind": "actual_qt_production_theme_offscreen_screenshot",
                "read_only_fixture": True,
                "results": results,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Research fallback Qt screenshot QA passed: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
