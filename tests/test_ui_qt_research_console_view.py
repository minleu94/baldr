from __future__ import annotations

import ast
from dataclasses import replace
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QPushButton

from app_module.research_console_dtos import (
    ResearchArtifactRowDTO,
    ResearchConsoleBoundaryDTO,
    ResearchConsoleDTO,
    ResearchGateCardDTO,
    ResearchPipelineRowDTO,
    ResearchSourceRowDTO,
)
from app_module.recommendation_learning_evidence_projection_service import (
    LearningHorizonProjection,
    LearningLaneProjection,
    LearningReliabilityBin,
    RecommendationLearningEvidenceProjection,
)
from ui_qt.views.research_console_view import (
    ResearchConsoleView,
    _learning_next_step,
    _learning_record_summary,
)


def app() -> QApplication:
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication(sys.argv)
    return instance


def _console() -> ResearchConsoleDTO:
    return ResearchConsoleDTO(
        overall_status="degraded",
        source_reference="fixture:ResearchConsoleProjection.v1",
        boundary=ResearchConsoleBoundaryDTO(),
        pipeline=(
            ResearchPipelineRowDTO(
                component_id="dataset",
                label="Development Dataset V0",
                identity="dataset:g-1",
                status="research_only_degraded",
                cutoff="2025-12-31",
                feature_interval="2025-01-01..2025-12-31",
                label_maturity="2025-12-31",
                row_count=48,
                eligible_count=40,
                feature_count=20,
            ),
            ResearchPipelineRowDTO(
                component_id="rule",
                label="Rule Development Baseline",
                identity="sha256:rule",
                status="research_baseline",
            ),
            ResearchPipelineRowDTO(
                component_id="ml",
                label="ML Development Challenger",
                identity="sha256:run",
                status="development_challenger",
            ),
            ResearchPipelineRowDTO(
                component_id="e2e",
                label="Development E2E Run",
                identity="sha256:run",
                status="degraded",
                artifact_path="fixture/projection.json",
                artifact_hash="sha256:projection",
                generated_at="2026-07-13T12:00:00Z",
                blockers=("research_only_degraded",),
            ),
        ),
        gates=tuple(
            ResearchGateCardDTO(
                gate_id=f"EV{index}",
                label=f"EV{index}",
                status="missing" if index != 2 else "provisional",
                detail="Development projection only",
            )
            for index in range(1, 6)
        ),
        sources=(
            ResearchSourceRowDTO(
                source_id="institutional_flows",
                label="Institutional Flows",
                lane="p0",
                status="candidate",
                allowed_use="Development Only",
                observed_rows=12,
            ),
            ResearchSourceRowDTO(
                source_id="broker_dataset",
                label="Broker Dataset",
                lane="broker",
                status="degraded",
                allowed_use="Research Only",
            ),
        ),
        artifacts=(
            ResearchArtifactRowDTO(
                artifact_type="dataset_manifest",
                artifact_id="sha256:manifest",
                status="development_only",
                citation="projection.lineage.dataset_manifest_hash",
            ),
        ),
        frozen_metrics={"sample_count": 48, "coverage_bp": 10000},
        blockers=("research_only_degraded",),
    )


def test_missing_console_opens_and_shows_fail_closed_boundary() -> None:
    app()
    view = ResearchConsoleView(auto_refresh=False)

    text = view.visible_text()
    assert "Safety Boundary" in text
    assert "formal_oos_allowed = False" in text
    assert "production_blend_alpha_bp = 0" in text
    assert "Production ML: Disabled" in text
    assert "Missing" in text
    assert "EV1" in text and "EV5" in text
    assert "P0 Data Source Control Center" in text
    assert "Downstream eligible：0" in text
    assert view.control_center_table.rowCount() == 13
    assert view.control_center_table.horizontalHeaderItem(5).text() == "PIT / 解析通過率"


def test_fixture_renders_pipeline_gates_sources_and_separate_broker_lane() -> None:
    app()
    view = ResearchConsoleView(console=_console(), auto_refresh=False)

    text = view.visible_text()
    assert "Development Pipeline" in text
    assert "dataset:g-1" in text
    assert "Rule Development Baseline" in text
    assert "ML Development Challenger" in text
    assert "Evidence / Source Gates" in text
    assert "Institutional Flows" in text
    assert "Broker Dataset（獨立 lane）" in text
    assert "sha256:manifest" in text
    assert view.pipeline_table.rowCount() == 4
    assert view.gate_table.rowCount() == 5


def test_view_has_no_apply_promote_retrain_blend_accept_or_trade_controls() -> None:
    app()
    view = ResearchConsoleView(console=_console(), auto_refresh=False)

    forbidden = ("apply", "promote", "retrain", "blend", "accept source", "trade", "套用", "升級", "交易")
    button_texts = [button.text().lower() for button in view.findChildren(QPushButton)]
    assert button_texts == ["重新載入唯讀 projection"]
    assert not any(token in text for text in button_texts for token in forbidden)


def test_view_source_has_no_domain_or_database_imports() -> None:
    source_path = Path("ui_qt/views/research_console_view.py")
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module or ""
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }

    forbidden_prefixes = (
        "sqlite3",
        "data_module",
        "ml_module",
        "development_module",
        "decision_module.scoring",
        "portfolio_module",
    )
    assert not any(name.startswith(forbidden_prefixes) for name in imported)


def test_learning_projection_receives_selected_decision_date() -> None:
    app()

    class RecordingLearningService:
        cost_lane = "banktaiwan_estimated_research"

        def __init__(self) -> None:
            self.requested_dates: list[str | None] = []

        def inspect(self, *, requested_date: str | None = None):
            self.requested_dates.append(requested_date)
            return None

    service = RecordingLearningService()
    view = ResearchConsoleView(
        console=_console(),
        learning_projection_service=service,  # type: ignore[arg-type]
        decision_date="2026-09-14",
        auto_refresh=False,
    )
    view.set_decision_date("2026-09-01")

    assert service.requested_dates == ["2026-09-14", "2026-09-01"]


def test_learning_panel_leads_with_short_chinese_summary_and_collapses_identity_details() -> None:
    app()
    candidate = LearningLaneProjection(
        lane_id="banktaiwan_estimated_research",
        label="臺銀公開成本研究",
        status="pending",
        reason="natural_forward_evidence_receipt_missing",
        candidate_id="candidate-long-identity",
        model_version="model-long-identity",
        dataset_version="dataset-long-identity",
        training_as_of="2026-09-13",
        cost_basis="estimated_research_only",
        cost_scenario_id="banktaiwan-electronic-estimate",
        cost_scenario_version="banktaiwan-electronic-estimate-v1",
        cost_scenario_hash="sha256:" + "a" * 64,
        capture_status="not_recorded",
        diagnostics=("natural_forward_evidence_receipt_missing",),
        source_trace=("learning.latest_status=fixture",),
    )
    active = LearningLaneProjection(
        lane_id="banktaiwan_estimated_research:active",
        label="目前規則路徑",
        status="pending",
        reason="active_pointer_not_available",
    )
    projection = RecommendationLearningEvidenceProjection(
        schema_version="recommendation-learning-evidence-projection.v1",
        status="pending",
        requested_date="2026-09-14",
        learning_decision_date="2026-09-14",
        checked_at="2026-09-14T12:00:00+08:00",
        decision="retain_current",
        decision_reason="natural_forward_evidence_receipt_missing",
        candidate_id="candidate-long-identity",
        candidate_model_version="model-long-identity",
        candidate_training_as_of="2026-09-13",
        data_recorded_status="not_recorded",
        data_recorded_reason="no_matching_frozen_challenger_captures",
        next_gap="先取得同一 candidate、同一決策日的 scheduled live prediction capture。",
        adoption_reason="natural_forward_evidence_receipt_missing",
        candidate_lane=candidate,
        active_lane=active,
        cost_lane="banktaiwan_estimated_research",
    )

    view = ResearchConsoleView(console=_console(), auto_refresh=False)
    view.render_learning_projection(projection)

    summary = view.learning_summary_label.text()
    assert "目標決策日：2026-09-14" in summary
    assert "學習資料決策日：2026-09-14" in summary
    assert "臺銀費稅估算" in summary
    assert "尚未建立該日預測紀錄" in summary
    assert "已驗證自然樣本：0 筆／0 個決策日（可靠度未知）" in summary
    assert "保留目前模型／規則路徑" in summary
    assert "candidate-long-identity" not in summary
    assert "model-long-identity" not in summary
    assert "banktaiwan-electronic-estimate" not in summary
    assert view.learning_detail_label.isHidden()
    assert "candidate-long-identity" in view.learning_detail_label.text()
    assert "banktaiwan-electronic-estimate" in view.learning_detail_label.text()

    view.learning_detail_toggle.click()
    assert not view.learning_detail_label.isHidden()


def test_learning_summary_distinguishes_verified_recorded_from_blocked_recorded() -> None:
    app()
    verified_candidate = LearningLaneProjection(
        lane_id="banktaiwan_estimated_research",
        label="臺銀公開成本研究",
        status="verified",
        reason="calibration_not_improved",
        candidate_id="candidate-verified",
        model_version="model-verified",
        cost_basis="estimated_research_only",
        cost_scenario_id="banktaiwan-electronic-estimate",
        capture_status="recorded",
        capture_count=1,
        recorded_row_count=2,
        matured_sample_count=2,
        matured_decision_date_count=1,
        horizons=(
            LearningHorizonProjection(
                horizon_days=20,
                capture_count=1,
                recorded_row_count=2,
                matured_sample_count=2,
                matured_decision_date_count=1,
                status="verified",
            ),
        ),
        reliability_bins=(
            LearningReliabilityBin(
                target="upside_probability",
                lower_probability_bp=8_000,
                upper_probability_bp_exclusive=10_001,
                predicted_probability_bp=8_500,
                matured_actual_up_ratio_bp=5_000,
                sample_count=2,
                decision_date_count=1,
                period_start="2026-09-01",
                period_end="2026-09-14",
                lane_id="banktaiwan_estimated_research",
            ),
        ),
    )
    pending_active = LearningLaneProjection(
        lane_id="banktaiwan_estimated_research:active",
        label="目前規則路徑",
        status="pending",
        reason="active_pointer_not_available",
    )
    verified_projection = RecommendationLearningEvidenceProjection(
        schema_version="recommendation-learning-evidence-projection.v1",
        status="verified",
        requested_date="2026-09-14",
        learning_decision_date="2026-09-14",
        checked_at="2026-09-14T12:00:00+08:00",
        decision="retain_current",
        decision_reason="calibration_not_improved",
        candidate_id="candidate-verified",
        candidate_model_version="model-verified",
        candidate_training_as_of="2026-08-31",
        data_recorded_status="recorded",
        data_recorded_reason="capture_recorded",
        next_gap="已驗證 natural evidence；距 promotion policy 尚差 8 筆、2 個決策日。",
        adoption_reason="calibration_not_improved",
        candidate_lane=verified_candidate,
        active_lane=pending_active,
        cost_lane="banktaiwan_estimated_research",
    )
    view = ResearchConsoleView(console=_console(), auto_refresh=False)
    view.render_learning_projection(verified_projection)
    verified_summary = view.learning_summary_label.text()
    assert "已建立該日預測紀錄；自然證據已完成驗證" in verified_summary
    assert "等待自然成熟" not in verified_summary
    assert "保留目前模型／規則路徑：校準未改善" in verified_summary
    assert "已驗證自然樣本：2 筆／1 個決策日" in verified_summary
    assert view.learning_table.horizontalHeaderItem(2).text() == "實際事件發生比例"
    assert view.learning_table.item(0, 0).text() == "上漲機率"

    blocked_candidate = LearningLaneProjection(
        lane_id="banktaiwan_estimated_research",
        label="臺銀公開成本研究",
        status="blocked_provenance",
        reason="cross-capture feature/source conflict: 1528",
        candidate_id="candidate-blocked",
        capture_status="recorded",
        capture_count=1,
        recorded_row_count=2,
    )
    blocked_projection = replace(
        verified_projection,
        status="blocked_provenance",
        decision_reason="cross-capture feature/source conflict: 1528",
        adoption_reason="cross-capture feature/source conflict: 1528",
        candidate_id="candidate-blocked",
        data_recorded_status="recorded",
        data_recorded_reason="capture_recorded",
        next_gap="先修復 provenance：cross-capture feature/source conflict: 1528；修復前不顯示 reliability。",
        candidate_lane=blocked_candidate,
        horizons=(),
    )
    view.render_learning_projection(blocked_projection)
    blocked_summary = view.learning_summary_label.text()
    assert "已建立該日預測紀錄；自然證據來源追溯受阻，未採用" in blocked_summary
    assert "等待自然成熟" not in blocked_summary
    assert "保留目前模型／規則路徑：來源追溯受阻" in blocked_summary


@pytest.mark.parametrize("projection_status", ("verified", "blocked_provenance", "pending"))
@pytest.mark.parametrize("record_status", ("recorded", "not_recorded", "unknown"))
def test_learning_summary_state_matrix_keeps_record_and_verification_independent(
    projection_status: str,
    record_status: str,
) -> None:
    projection = SimpleNamespace(
        status=projection_status,
        data_recorded_status=record_status,
        next_gap="依既有 gate 覆核。",
    )

    record_summary = _learning_record_summary(projection)  # type: ignore[arg-type]
    next_step = _learning_next_step(projection)  # type: ignore[arg-type]
    has_record = record_status == "recorded"
    assert ("已建立該日預測紀錄" in record_summary) is has_record
    if projection_status == "verified":
        assert "自然證據已完成驗證" in record_summary
    elif projection_status == "blocked_provenance":
        assert "自然證據來源追溯受阻" in record_summary
        assert "等待自然成熟" not in next_step
    elif record_status == "recorded":
        assert "等待自然成熟" in next_step
    else:
        assert "等待自然成熟" not in next_step
