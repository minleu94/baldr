from __future__ import annotations

import ast
from dataclasses import replace
import os
import sys
from pathlib import Path
from threading import Event, current_thread
import time
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent, QThread, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton
import shiboken6

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
import ui_qt.views.research_console_view as research_console_view_module


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


class _AsyncResearchConsoleSourceService:
    def __init__(self, console: ResearchConsoleDTO) -> None:
        self.console = console
        self.calls = 0
        self.thread_names: list[str] = []
        self.block_next = False
        self.started = Event()
        self.release = Event()
        self.fail_calls: set[int] = set()

    def missing_projection(self) -> ResearchConsoleDTO:
        return self.console

    def inspect(self, **kwargs) -> ResearchConsoleDTO:
        self.calls += 1
        self.thread_names.append(current_thread().name)
        if self.block_next:
            self.block_next = False
            self.started.set()
            if not self.release.wait(timeout=2.0):
                raise TimeoutError("Research Console source fixture was not released")
        if self.calls in self.fail_calls:
            raise RuntimeError("fixture Research Console source failure")
        return self.console


class _RecordingLearningProjectionService:
    def __init__(
        self,
        projection: RecommendationLearningEvidenceProjection,
        *,
        block_call: int | None = None,
    ) -> None:
        self.cost_lane = projection.cost_lane
        self.projection = projection
        self.block_call = block_call
        self.calls = 0
        self.requested_dates: list[str | None] = []
        self.started = Event()
        self.release = Event()

    def inspect(self, *, requested_date: str | None = None, **kwargs):
        self.calls += 1
        self.requested_dates.append(requested_date)
        if self.calls == self.block_call:
            self.started.set()
            if not self.release.wait(timeout=2.0):
                raise TimeoutError("learning projection fixture was not released")
        return self.projection


def _learning_projection_for_lane(cost_lane: str) -> RecommendationLearningEvidenceProjection:
    candidate = LearningLaneProjection(
        lane_id=cost_lane,
        label=f"fixture candidate {cost_lane}",
        status="pending",
        reason="fixture_pending",
    )
    active = LearningLaneProjection(
        lane_id=f"{cost_lane}:active",
        label=f"fixture active {cost_lane}",
        status="pending",
        reason="fixture_active_pending",
    )
    return RecommendationLearningEvidenceProjection(
        schema_version="recommendation-learning-evidence-projection.v1",
        status="pending",
        requested_date="2026-09-14",
        learning_decision_date="2026-09-14",
        checked_at="2026-09-14T12:00:00+08:00",
        decision="retain_current",
        decision_reason=f"fixture_{cost_lane}",
        candidate_id=f"candidate-{cost_lane}",
        candidate_model_version="fixture-model",
        candidate_training_as_of="2026-09-01",
        data_recorded_status="not_recorded",
        data_recorded_reason="fixture_no_capture",
        next_gap="fixture gap",
        adoption_reason=f"fixture_{cost_lane}",
        candidate_lane=candidate,
        active_lane=active,
        cost_lane=cost_lane,
    )


def _wait_for_console_refresh(
    view: ResearchConsoleView,
    source: _AsyncResearchConsoleSourceService,
    expected_calls: int,
    timeout_ms: int = 2_000,
) -> None:
    deadline = time.monotonic() + timeout_ms / 1_000
    while time.monotonic() < deadline:
        app().processEvents()
        if (
            view._refresh_worker is None
            and not view._refresh_pending
            and source.calls >= expected_calls
        ):
            app().processEvents()
            return
        QTest.qWait(10)
    pytest.fail(
        "Research Console async refresh did not settle: "
        f"calls={source.calls}, pending={view._refresh_pending}, "
        f"worker={view._refresh_worker}, generation={view._refresh_generation}"
    )


def _drain_deferred_deletes() -> None:
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app().processEvents()


def _dispose_console_view(view: ResearchConsoleView) -> None:
    view.begin_shutdown()
    deadline = time.monotonic() + 3.0
    while view._refresh_worker is not None and time.monotonic() < deadline:
        app().processEvents()
        QTest.qWait(10)
    view.close()
    view.deleteLater()
    _drain_deferred_deletes()


def _observe_console_callbacks_on_gui_thread(
    view: ResearchConsoleView,
    names: tuple[str, ...],
    observations: dict[str, list[bool]],
) -> None:
    for name in names:
        original = getattr(view, name)

        def record(*args, _original=original, _name=name, **kwargs):
            observations[_name].append(QThread.currentThread() == view.thread())
            return _original(*args, **kwargs)

        setattr(view, name, record)


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


def test_async_research_console_load_is_lazy_background_and_renders_on_gui_thread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app()
    source = _AsyncResearchConsoleSourceService(_console())
    original_worker_factory = research_console_view_module.TaskWorker
    workers = []

    def worker_factory(*args, **kwargs):
        worker = original_worker_factory(*args, **kwargs)
        workers.append(worker)
        return worker

    monkeypatch.setattr(research_console_view_module, "TaskWorker", worker_factory)
    view = ResearchConsoleView(
        source_service=source,  # type: ignore[arg-type]
        auto_refresh=False,
        async_refresh=True,
    )
    callback_threads: dict[str, list[bool]] = {
        "_on_async_refresh_finished": [],
        "_on_async_refresh_thread_finished": [],
    }
    _observe_console_callbacks_on_gui_thread(
        view,
        tuple(callback_threads),
        callback_threads,
    )
    rendered_on_gui_thread: list[bool] = []
    original_render = view.render_console

    def record_render(console: ResearchConsoleDTO) -> None:
        rendered_on_gui_thread.append(QThread.currentThread() == view.thread())
        original_render(console)

    view.render_console = record_render
    try:
        assert source.calls == 0
        view.ensure_loaded()
        view.ensure_loaded()
        _wait_for_console_refresh(view, source, expected_calls=1)
        _drain_deferred_deletes()

        assert source.calls == 1
        assert source.thread_names and all(
            name != "MainThread" for name in source.thread_names
        )
        assert callback_threads["_on_async_refresh_finished"] == [True]
        assert callback_threads["_on_async_refresh_thread_finished"] == [True]
        assert rendered_on_gui_thread == [True]
        assert view._console_loaded is True
        assert workers and not shiboken6.isValid(workers[0])
    finally:
        _dispose_console_view(view)


def test_async_research_console_ignores_queued_result_after_shutdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app()
    source = _AsyncResearchConsoleSourceService(_console())
    source.block_next = True
    original_worker_factory = research_console_view_module.TaskWorker
    workers = []

    def worker_factory(*args, **kwargs):
        worker = original_worker_factory(*args, **kwargs)
        workers.append(worker)
        return worker

    monkeypatch.setattr(research_console_view_module, "TaskWorker", worker_factory)
    view = ResearchConsoleView(
        source_service=source,  # type: ignore[arg-type]
        auto_refresh=False,
        async_refresh=True,
    )
    rendered: list[ResearchConsoleDTO] = []
    original_render = view.render_console

    def record_render(console: ResearchConsoleDTO) -> None:
        rendered.append(console)
        original_render(console)

    view.render_console = record_render
    try:
        view.ensure_loaded()
        assert source.started.wait(timeout=1.0)
        worker = view._refresh_worker
        assert worker is not None
        source.release.set()
        deadline = time.monotonic() + 1.0
        while worker.isRunning() and time.monotonic() < deadline:
            time.sleep(0.001)
        assert not worker.isRunning()

        view.begin_shutdown()
        _wait_for_console_refresh(view, source, expected_calls=1)
        _drain_deferred_deletes()

        assert rendered == []
        assert view._console_loaded is False
        assert view._refresh_worker is None
        assert not shiboken6.isValid(worker)
    finally:
        source.release.set()
        _dispose_console_view(view)


@pytest.mark.parametrize("recover_from_initial_failure", [False, True])
def test_research_console_lane_switch_drops_queued_result_during_lazy_load_or_retry(
    monkeypatch: pytest.MonkeyPatch,
    recover_from_initial_failure: bool,
) -> None:
    app()
    console = _console()
    source = _AsyncResearchConsoleSourceService(console)
    if recover_from_initial_failure:
        source.fail_calls.add(1)
    banktaiwan = _RecordingLearningProjectionService(
        _learning_projection_for_lane("banktaiwan_estimated_research"),
        block_call=1,
    )
    legacy = _RecordingLearningProjectionService(
        _learning_projection_for_lane("legacy_fixed_bp")
    )
    original_worker_factory = research_console_view_module.TaskWorker
    workers = []

    def worker_factory(*args, **kwargs):
        worker = original_worker_factory(*args, **kwargs)
        workers.append(worker)
        return worker

    monkeypatch.setattr(research_console_view_module, "TaskWorker", worker_factory)
    view = ResearchConsoleView(
        source_service=source,  # type: ignore[arg-type]
        learning_projection_service=banktaiwan,  # type: ignore[arg-type]
        legacy_learning_projection_service=legacy,  # type: ignore[arg-type]
        decision_date="2026-09-14",
        auto_refresh=False,
        async_refresh=True,
    )
    callback_threads: dict[str, list[bool]] = {
        "_on_async_refresh_finished": [],
        "_on_async_refresh_error": [],
        "_on_async_refresh_thread_finished": [],
    }
    _observe_console_callbacks_on_gui_thread(
        view,
        tuple(callback_threads),
        callback_threads,
    )
    try:
        view.ensure_loaded()
        if recover_from_initial_failure:
            _wait_for_console_refresh(view, source, expected_calls=1)
            _drain_deferred_deletes()
            assert view._console_loaded is False
            assert view._load_requested is False
            assert callback_threads["_on_async_refresh_error"] == [True]
            source.fail_calls.clear()

        banktaiwan.block_call = banktaiwan.calls + 1
        if recover_from_initial_failure:
            view.refresh_console()
        old_worker = view._refresh_worker
        assert old_worker is not None
        assert banktaiwan.started.wait(timeout=1.0)

        rendered_lanes: list[str] = []
        original_render_learning = view.render_learning_projection

        def record_learning_render(projection, *, error=None) -> None:
            if projection is not None:
                rendered_lanes.append(projection.cost_lane)
            original_render_learning(projection, error=error)

        view.render_learning_projection = record_learning_render

        result_emitted = Event()
        allow_native_exit = Event()

        def pause_after_result(_bundle: object) -> None:
            result_emitted.set()
            if not allow_native_exit.wait(timeout=2.0):
                raise TimeoutError("queued-result lane fixture was not released")

        old_worker.finished.connect(
            pause_after_result,
            Qt.ConnectionType.DirectConnection,
        )
        banktaiwan.release.set()
        assert result_emitted.wait(timeout=1.0)
        assert old_worker.isRunning()

        view.learning_lane_selector.setCurrentIndex(1)
        assert view._refresh_pending is True
        allow_native_exit.set()
        _wait_for_console_refresh(
            view,
            source,
            expected_calls=2 + int(recover_from_initial_failure),
        )
        _drain_deferred_deletes()

        assert source.calls == 2 + int(recover_from_initial_failure)
        assert banktaiwan.calls == 1
        assert legacy.calls == 1
        assert rendered_lanes == ["legacy_fixed_bp"]
        assert view._learning_projection is not None
        assert view._learning_projection.cost_lane == "legacy_fixed_bp"
        assert callback_threads["_on_async_refresh_finished"] == [True, True]
        assert all(callback_threads["_on_async_refresh_thread_finished"])
        assert all(not shiboken6.isValid(worker) for worker in workers)
    finally:
        banktaiwan.release.set()
        _dispose_console_view(view)


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
