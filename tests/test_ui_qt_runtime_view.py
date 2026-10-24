import os
import sys
from datetime import datetime, timezone
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QSizePolicy, QProgressBar, QLabel

from app_module.dtos.runtime_dtos import (
    GovernanceSeverity,
    RuntimeEventDTO,
    RuntimeHealthSnapshotDTO,
    RuntimeState,
    RuntimeStateSnapshotDTO,
    ScheduledOperationStatusDTO,
    ScheduledOperationsSnapshotDTO,
    EnvironmentPathReadinessDTO,
    EnvironmentReadinessSnapshotDTO,
)
from app_module.decision_capture_status_reader import (
    DecisionCaptureRunStatus,
    DecisionCaptureStage,
)
from ui_qt.views.runtime_view import MAX_RENDERED_RUNTIME_EVENTS, RuntimeView
from ui_qt.theme import MIDNIGHT_ANALYST


def app():
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication(sys.argv)
    return instance


def make_runtime_health_dto(
    state: str = "HALTED",
    rejection_rate: float = 0.8,
    consecutive_failures: int = 4,
) -> RuntimeHealthSnapshotDTO:
    return RuntimeHealthSnapshotDTO(
        is_healthy=False,
        current_state=RuntimeState(state),
        rejection_rate=rejection_rate,
        rejection_rate_trend="UP",
        consecutive_failures=consecutive_failures,
        last_critical_violation=RuntimeEventDTO(
            event_id="evt-1",
            timestamp=datetime(2026, 6, 23, 9, 0, 0),
            actor="runtime",
            event_type="governance_violation",
            severity=GovernanceSeverity.CRITICAL,
            human_readable_message="GovernanceViolation",
            payload_preview={"raw": "value"},
        ),
    )


def make_runtime_event_dto(
    event_type: str = "validation_rejected",
    message: str = "JSONDecodeError",
) -> RuntimeEventDTO:
    return RuntimeEventDTO(
        event_id="evt-2",
        timestamp=datetime(2026, 6, 23, 9, 1, 0),
        actor="agent",
        event_type=event_type,
        severity=GovernanceSeverity.WARNING,
        human_readable_message=message,
        payload_preview={"exception": message},
    )


def test_runtime_view_static_labels_are_chinese_and_scope_is_explicit():
    app()
    view = RuntimeView()

    assert "任務狀態機" in view.state_group.title()
    assert "未知（尚未讀取）" in view.last_violation_label.text()
    assert MIDNIGHT_ANALYST.text_muted in view.last_violation_label.styleSheet()
    assert "OUTPUT_ROOT/scheduled" in view.scope_label.text()
    assert "Windows Task Scheduler" in view.scope_label.text()
    assert "營運排程" in view.operations_group.title()
    assert "本次開啟後" in view.events_group.title()


def test_runtime_scope_note_is_compact_and_content_starts_near_top():
    app()
    view = RuntimeView()
    try:
        view.operations_details_button.setChecked(True)
        view.scope_label.setText("窄版長範圍說明；" * 16)
        view.resize(390, 420)
        view.show()
        app().processEvents()

        assert view.scope_label.wordWrap()
        assert view.scope_label.maximumHeight() > view.scope_label.height()
        assert view.scope_label.height() >= view.scope_label.heightForWidth(
            view.scope_label.width()
        )
        assert hasattr(view, "main_splitter")
        assert view.content_scroll.verticalScrollBar().maximum() > 0
        assert view.content_scroll.verticalScrollBar().value() == 0
        assert view.scope_label.isVisible()
    finally:
        view.close()
        view.deleteLater()
        app().processEvents()


def test_runtime_view_yields_horizontal_size_hints_for_narrow_workspaces():
    app()
    view = RuntimeView()

    assert view.minimumWidth() == 0
    assert view.sizePolicy().horizontalPolicy() == QSizePolicy.Ignored
    assert view.environment_group.sizePolicy().horizontalPolicy() == QSizePolicy.Ignored
    assert view.operations_group.sizePolicy().horizontalPolicy() == QSizePolicy.Ignored
    assert view.main_splitter.minimumWidth() == 0
    assert view.main_splitter.sizePolicy().horizontalPolicy() == QSizePolicy.Ignored
    assert view.main_splitter.widget(0).sizePolicy().horizontalPolicy() == QSizePolicy.Ignored
    assert view.main_splitter.widget(1).sizePolicy().horizontalPolicy() == QSizePolicy.Ignored


def test_runtime_view_switches_governance_panels_to_vertical_narrow_layout():
    app()
    view = RuntimeView()
    view.show()
    view.resize(390, 844)
    app().processEvents()

    assert view.main_splitter.orientation().name == "Vertical"
    assert view.content_scroll.verticalScrollBarPolicy().name == "ScrollBarAsNeeded"
    assert view.content_scroll.horizontalScrollBarPolicy().name == "ScrollBarAlwaysOff"

    view.resize(900, 844)
    app().processEvents()

    assert view.main_splitter.orientation().name == "Horizontal"


def test_runtime_state_snapshot_renders_chinese_idle_text():
    app()
    view = RuntimeView()
    dto = RuntimeStateSnapshotDTO(
        task_objective="No task assigned",
        task_status="IDLE",
        active_context_files=[],
    )

    view.on_state_updated(dto)

    assert "目前治理目標：尚未指派治理任務" in view.objective_label.text()
    assert "任務流程狀態：閒置" in view.status_label.text()


def test_runtime_health_halted_uses_error_status_and_chinese_labels():
    app()
    view = RuntimeView()
    dto = make_runtime_health_dto()

    view.on_health_updated(dto)

    assert "治理暫停" in view.health_state_label.text()
    assert MIDNIGHT_ANALYST.status_error in view.health_state_label.text()
    assert "驗證拒絕率：80.0%" in view.rejection_rate_label.text()
    assert "連續失敗次數：4" in view.rejection_rate_label.text()
    assert "治理規則違反" in view.last_violation_label.text()
    assert MIDNIGHT_ANALYST.status_error in view.last_violation_label.styleSheet()
    assert "不代表日常營運排程或主 App 一般功能失敗" in view.health_scope_note_label.text()


def test_last_violation_status_color_clears_from_current_to_none_and_noncurrent():
    app()
    view = RuntimeView()
    violation = make_runtime_health_dto()

    view.on_health_updated(violation)
    assert MIDNIGHT_ANALYST.status_error in view.last_violation_label.styleSheet()

    no_violation = replace(
        violation,
        is_healthy=True,
        current_state=RuntimeState.IDLE,
        rejection_rate=0.0,
        consecutive_failures=0,
        last_critical_violation=None,
    )
    view.on_health_updated(no_violation)
    assert view.last_violation_label.text() == "最近重大違規：無"
    assert MIDNIGHT_ANALYST.status_success in view.health_state_label.text()
    assert MIDNIGHT_ANALYST.text_secondary in view.last_violation_label.styleSheet()
    assert MIDNIGHT_ANALYST.status_error not in view.last_violation_label.styleSheet()

    historical = replace(
        violation,
        current_state=RuntimeState.IDLE,
        observation_scope="historical_only",
        historical_event_count=1,
    )
    view.on_health_updated(historical)
    assert "最近歷史重大違規" in view.last_violation_label.text()
    assert MIDNIGHT_ANALYST.status_info in view.last_violation_label.styleSheet()
    assert MIDNIGHT_ANALYST.status_error not in view.last_violation_label.styleSheet()

    unreadable = replace(
        historical,
        observation_scope="event_log_unreadable",
        event_log_read_state="unavailable",
    )
    view.on_health_updated(unreadable)
    assert MIDNIGHT_ANALYST.status_error not in view.last_violation_label.styleSheet()
    assert MIDNIGHT_ANALYST.text_secondary in view.last_violation_label.styleSheet()


def test_runtime_event_stream_shows_chinese_summary_and_raw_tooltip():
    app()
    view = RuntimeView()
    dto = make_runtime_event_dto()

    view.on_event_received(dto)

    item = view.event_list.item(0)
    assert "驗證拒絕" in item.text()
    assert "JSON 格式錯誤" in item.text()
    assert "validation_rejected" in item.toolTip()


def test_runtime_view_renders_operation_status_without_claiming_scheduler_state():
    app()
    view = RuntimeView()
    dto = ScheduledOperationsSnapshotDTO(
        overall_state="operational",
        core_ready_count=6,
        core_job_count=6,
        operations=(
            ScheduledOperationStatusDTO(
                job_id="data_update_quick",
                label="每日資料更新",
                raw_status="passed",
                state="operational",
                updated_at=datetime(2026, 8, 6, 5, 0, tzinfo=timezone.utc),
                lane="core",
                observed_at_source="checked_at",
                source_path="C:/output/scheduled/data_update_quick/latest_status.json",
            ),
            ScheduledOperationStatusDTO(
                job_id="ml_allocation_copilot",
                label="ML Shadow Co-pilot",
                raw_status="passed_rule_only",
                state="guarded",
                updated_at=datetime(2026, 8, 6, 5, 0, tzinfo=timezone.utc),
                lane="safety",
                diagnostic="ml_shadow_rule_only",
            ),
        ),
        observed_at=datetime(2026, 8, 6, 5, 0, tzinfo=timezone.utc),
    )

    view.on_scheduled_operations_updated(dto)

    assert "核心工作已就緒 6/6" in view.operations_summary_label.text()
    assert "每日資料更新｜正常｜觀測時間：" in view.operations_list.item(0).text()
    assert "ML Shadow Co-pilot｜安全邊界中｜觀測時間：" in view.operations_list.item(1).text()
    assert "raw_status: passed" in view.operations_list.item(0).toolTip()
    assert "raw_status: passed_rule_only" in view.operations_list.item(1).toolTip()
    assert "timestamp_source: checked_at" in view.operations_list.item(0).toolTip()


def test_runtime_operations_distribution_counts_only_observed_states_and_keeps_unknowns():
    app()
    view = RuntimeView()
    operations = (
        ScheduledOperationStatusDTO(
            job_id="normal_a", label="正常 A", raw_status="passed",
            state="operational", updated_at=None,
        ),
        ScheduledOperationStatusDTO(
            job_id="normal_b", label="正常 B", raw_status="passed",
            state="operational", updated_at=None,
        ),
        ScheduledOperationStatusDTO(
            job_id="guarded", label="安全邊界", raw_status="blocked",
            state="guarded", updated_at=None,
        ),
        ScheduledOperationStatusDTO(
            job_id="attention", label="注意", raw_status="failed",
            state="attention", updated_at=None,
        ),
        ScheduledOperationStatusDTO(
            job_id="unavailable", label="無法判定", raw_status="missing",
            state="unavailable", updated_at=None,
        ),
        ScheduledOperationStatusDTO(
            job_id="unconfirmed", label="來源未確認", raw_status="passed",
            state="operational", updated_at=None, read_state="unreadable",
        ),
        ScheduledOperationStatusDTO(
            job_id="unknown", label="未知狀態", raw_status="strange",
            state="future_state_code", updated_at=None,
        ),
    )
    dto = ScheduledOperationsSnapshotDTO(
        overall_state="attention", core_ready_count=2, core_job_count=4,
        operations=operations, observed_at=datetime(2026, 10, 23, tzinfo=timezone.utc),
    )

    view.on_scheduled_operations_updated(dto)

    summary = view.operations_distribution_label.text()
    assert "本次已保存狀態快照（非排程器執行紀錄）" in summary
    assert "正常 2｜安全邊界中 1｜需要注意 1｜無法判定 1｜來源未確認 1｜未知狀態 1" in summary
    expected_read_time = dto.observed_at.astimezone().strftime("%Y-%m-%d %H:%M:%S")
    assert f"本頁讀取時間：{expected_read_time}" in summary
    segments = {
        widget.objectName().removeprefix("operationsDistributionSegment_"): widget
        for widget in view._operations_distribution_segment_widgets
    }
    assert {key: widget.property("count") for key, widget in segments.items()} == {
        "operational": 2,
        "guarded": 1,
        "attention": 1,
        "unavailable": 1,
        "source_unconfirmed": 1,
        "unknown": 1,
    }
    assert "state: future_state_code" in view.operations_list.item(6).toolTip()


def test_runtime_operations_distribution_is_independent_of_list_filter():
    app()
    view = RuntimeView()
    operations = (
        ScheduledOperationStatusDTO(
            job_id="normal", label="正常", raw_status="passed",
            state="operational", updated_at=None,
        ),
        ScheduledOperationStatusDTO(
            job_id="attention", label="注意", raw_status="failed",
            state="attention", updated_at=None,
        ),
        ScheduledOperationStatusDTO(
            job_id="unconfirmed", label="來源未確認", raw_status="passed",
            state="operational", updated_at=None, read_state="unreadable",
        ),
    )
    view.on_scheduled_operations_updated(ScheduledOperationsSnapshotDTO(
        overall_state="attention", core_ready_count=1, core_job_count=2,
        operations=operations, observed_at=datetime(2026, 10, 23, tzinfo=timezone.utc),
    ))
    original_distribution = view.operations_distribution_label.text()

    view.operations_state_filter.setCurrentIndex(1)

    assert view.operations_distribution_label.text() == original_distribution
    assert "正常 1｜安全邊界中 0｜需要注意 1｜無法判定 0｜來源未確認 1｜未知狀態 0" in original_distribution
    assert "目前顯示 2/3 項" in view.operations_summary_label.text()


def test_runtime_operations_distribution_replacement_and_empty_snapshot_clear_old_segments():
    app()
    view = RuntimeView()
    first_operations = (
        ScheduledOperationStatusDTO(
            job_id="normal", label="正常", raw_status="passed",
            state="operational", updated_at=None,
        ),
        ScheduledOperationStatusDTO(
            job_id="attention", label="注意", raw_status="failed",
            state="attention", updated_at=None,
        ),
    )
    observed_at = datetime(2026, 10, 23, tzinfo=timezone.utc)
    view.on_scheduled_operations_updated(ScheduledOperationsSnapshotDTO(
        overall_state="attention", core_ready_count=1, core_job_count=2,
        operations=first_operations, observed_at=observed_at,
    ))
    first_segments = tuple(view._operations_distribution_segment_widgets)
    assert len(first_segments) == 2

    replacement = ScheduledOperationStatusDTO(
        job_id="new_attention", label="新注意", raw_status="failed",
        state="attention", updated_at=None,
    )
    replacement_observed_at = datetime(2026, 10, 24, 12, 30, tzinfo=timezone.utc)
    view.on_scheduled_operations_updated(ScheduledOperationsSnapshotDTO(
        overall_state="attention", core_ready_count=0, core_job_count=1,
        operations=(replacement,), observed_at=replacement_observed_at,
    ))
    assert all(widget.isHidden() and widget.parent() is None for widget in first_segments)
    assert len(view._operations_distribution_segment_widgets) == 1
    assert "正常 0｜安全邊界中 0｜需要注意 1｜無法判定 0｜來源未確認 0｜未知狀態 0" in view.operations_distribution_label.text()
    replacement_read_time = replacement_observed_at.astimezone().strftime("%Y-%m-%d %H:%M:%S")
    assert f"本頁讀取時間：{replacement_read_time}" in view.operations_distribution_label.text()

    empty_observed_at = datetime(2026, 10, 25, 12, 30, tzinfo=timezone.utc)
    view.on_scheduled_operations_updated(ScheduledOperationsSnapshotDTO(
        overall_state="attention", core_ready_count=0, core_job_count=0,
        operations=(), observed_at=empty_observed_at,
    ))
    empty_summary = view.operations_distribution_label.text()
    assert "正常 0｜安全邊界中 0｜需要注意 0｜無法判定 0｜來源未確認 0｜未知狀態 0" in empty_summary
    assert "共 0 項" in empty_summary
    empty_read_time = empty_observed_at.astimezone().strftime("%Y-%m-%d %H:%M:%S")
    assert f"本頁讀取時間：{empty_read_time}" in empty_summary
    assert view._operations_distribution_segment_widgets == []
    assert view.operations_distribution_bar.isHidden()


def test_runtime_unreadable_operations_snapshot_shows_read_time_without_claiming_normal() -> None:
    app()
    view = RuntimeView()
    previous_observed_at = datetime(2026, 10, 25, 12, 30, tzinfo=timezone.utc)
    previous_operation = ScheduledOperationStatusDTO(
        job_id="previous", label="前次正常", raw_status="passed",
        state="operational", updated_at=None,
    )
    view.on_scheduled_operations_updated(ScheduledOperationsSnapshotDTO(
        overall_state="operational", core_ready_count=1, core_job_count=1,
        operations=(previous_operation,), observed_at=previous_observed_at,
    ))

    observed_at = datetime(2026, 10, 26, 12, 30, tzinfo=timezone.utc)
    operation = ScheduledOperationStatusDTO(
        job_id="unreadable", label="來源不可讀", raw_status="unreadable",
        state="unavailable", updated_at=None, read_state="unreadable",
    )
    view.on_scheduled_operations_updated(ScheduledOperationsSnapshotDTO(
        overall_state="attention", core_ready_count=0, core_job_count=1,
        operations=(operation,), observed_at=observed_at,
    ))

    summary = view.operations_distribution_label.text()
    expected_read_time = observed_at.astimezone().strftime("%Y-%m-%d %H:%M:%S")
    assert "來源未確認 1" in summary
    assert "正常 0" in summary
    assert "正常 1" not in summary
    assert f"本頁讀取時間：{expected_read_time}" in summary
    assert "非排程器執行紀錄" in summary

    timezone_less = datetime(2026, 10, 27, 12, 30)
    view.on_scheduled_operations_updated(ScheduledOperationsSnapshotDTO(
        overall_state="attention", core_ready_count=0, core_job_count=1,
        operations=(operation,), observed_at=timezone_less,
    ))
    assert "本頁讀取時間：未知（時間未含時區）" in view.operations_distribution_label.text()


def test_runtime_operations_state_filter_renders_all_normalized_states_and_preserves_dto():
    app()
    view = RuntimeView()
    operations = tuple(
        ScheduledOperationStatusDTO(
            job_id=f"job_{state}",
            label=f"工作 {state}",
            raw_status=f"raw_{state}",
            state=state,
            updated_at=None,
            lane="core",
            read_state="observed" if state != "observed" else "missing",
            diagnostic=f"diagnostic_{state}",
        )
        for state in ("operational", "guarded", "attention", "unavailable", "observed")
    )
    dto = ScheduledOperationsSnapshotDTO(
        overall_state="attention",
        core_ready_count=1,
        core_job_count=5,
        operations=operations,
        observed_at=datetime(2026, 10, 23, tzinfo=timezone.utc),
    )

    view.on_scheduled_operations_updated(dto)

    assert view.operations_list.count() == 5
    assert "目前顯示 5/5 項" in view.operations_summary_label.text()
    assert tuple(view._scheduled_operations) == operations
    assert "raw_status: raw_observed" in view.operations_list.item(4).toolTip()
    assert "read_state: missing" in view.operations_list.item(4).toolTip()
    assert "diagnostic: diagnostic_observed" in view.operations_list.item(4).toolTip()
    for index, state in enumerate(("operational", "guarded", "attention", "unavailable", "observed"), start=1):
        view.operations_state_filter.setCurrentIndex(index)
        assert view.operations_list.count() == 1
        assert view.operations_list.item(0).data(Qt.UserRole) == f"job_{state}"
        assert f"目前顯示 1/5 項" in view.operations_summary_label.text()


def test_runtime_operations_filter_handles_selection_transitions_and_empty_states():
    app()
    view = RuntimeView()
    operations = (
        ScheduledOperationStatusDTO(
            job_id="operational_job",
            label="正常工作",
            raw_status="passed",
            state="operational",
            updated_at=None,
            lane="core",
        ),
        ScheduledOperationStatusDTO(
            job_id="decision_evidence_capture",
            label="注意工作",
            raw_status="attention_raw",
            state="attention",
            updated_at=None,
            lane="core",
            capture=_decision_capture_status(run_id="selected-run"),
        ),
    )
    dto = ScheduledOperationsSnapshotDTO(
        overall_state="attention",
        core_ready_count=1,
        core_job_count=2,
        operations=operations,
        observed_at=datetime(2026, 10, 23, tzinfo=timezone.utc),
    )
    view.on_scheduled_operations_updated(dto)
    view.operations_list.setCurrentRow(1)
    assert "selected-run" in view.operations_capture_detail_label.text()

    view.operations_state_filter.setCurrentIndex(1)
    assert view.operations_list.currentItem() is None
    assert "selected-run" not in view.operations_capture_detail_label.text()
    assert "目前顯示 1/2 項" in view.operations_summary_label.text()

    view.operations_state_filter.setCurrentIndex(0)
    assert view.operations_list.count() == 2
    view.operations_list.setCurrentRow(0)
    view.operations_state_filter.setCurrentIndex(1)
    assert view.operations_list.currentItem().data(Qt.UserRole) == "operational_job"

    view.operations_state_filter.setCurrentIndex(4)
    assert view.operations_list.count() == 1
    assert "沒有符合的營運工作" in view.operations_list.item(0).text()
    assert "目前顯示 0/2 項" in view.operations_summary_label.text()
    assert view.operations_list.currentItem() is None


def _decision_capture_status(
    *,
    read_state="verified",
    run_id="capture-run-001",
    snapshot_saved=True,
    failure_reasons=(),
    elapsed_ms=125,
    completed_at="2026-10-14T08:30:00+08:00",
    snapshot_execution_status="completed",
):
    return DecisionCaptureRunStatus(
        status_path=Path("C:/output/scheduled/decision_evidence_capture/latest_status.json"),
        read_state=read_state,
        diagnostic="PRIVATE_EXCEPTION_TEXT_MUST_NOT_RENDER",
        raw_status="passed",
        run_id=run_id,
        decision_date="2026-10-14",
        completed_at=completed_at,
        receipt_path="C:/output/decision_evidence_capture/receipt.json",
        receipt_sha256="a" * 64,
        snapshot_status="saved" if snapshot_saved is True else "unknown",
        snapshot_saved=snapshot_saved,
        snapshot_duplicate=False,
        snapshot_execution_status=snapshot_execution_status,
        failure_reasons=failure_reasons,
        last_stage="receipt_published",
        unfinished_stages=(),
        stages=(DecisionCaptureStage("snapshot", "completed", elapsed_ms),),
    )


def _decision_capture_snapshot(operation):
    return ScheduledOperationsSnapshotDTO(
        overall_state="operational",
        core_ready_count=1,
        core_job_count=1,
        operations=(operation,),
        observed_at=datetime(2026, 10, 14, 0, 30, tzinfo=timezone.utc),
    )


def test_runtime_view_renders_typed_capture_and_updates_the_preserved_selection():
    app()
    view = RuntimeView()
    first = ScheduledOperationStatusDTO(
        job_id="decision_evidence_capture",
        label="決策證據擷取",
        raw_status="passed",
        state="operational",
        updated_at=datetime(2026, 10, 14, 0, 30, tzinfo=timezone.utc),
        lane="core",
        capture=_decision_capture_status(),
    )

    view.on_scheduled_operations_updated(_decision_capture_snapshot(first))
    view.operations_list.setCurrentRow(0)

    detail = view.operations_capture_detail_label.text()
    assert "已驗證（verified）" in detail
    assert "capture-run-001" in detail
    assert "2026-10-14" in detail
    assert "receipt SHA-256：" + "a" * 64 in detail
    assert "snapshot 狀態：saved｜已保存：是" in detail
    assert "snapshot 執行狀態：completed" in detail
    assert "125 ms" in detail
    assert "PRIVATE_EXCEPTION_TEXT_MUST_NOT_RENDER" not in detail
    assert "PRIVATE_EXCEPTION_TEXT_MUST_NOT_RENDER" not in view.operations_raw_text.toPlainText()
    failed_chain = replace(first.capture, read_state="unverified", diagnostic="decision_capture_receipt_hash_mismatch")
    assert "decision_capture_receipt_hash_mismatch" in view._render_decision_capture_status(
        replace(first, state="attention", capture=failed_chain)
    )

    next_operation = ScheduledOperationStatusDTO(
        job_id="decision_evidence_capture",
        label="決策證據擷取",
        raw_status="timeout",
        state="unavailable",
        updated_at=None,
        lane="core",
        capture=_decision_capture_status(
            read_state="not_finalized",
            run_id="capture-run-002",
            snapshot_saved=None,
            failure_reasons=("capture_timeout", "OSError: private stderr"),
            elapsed_ms=90_000_000,
            completed_at="",
            snapshot_execution_status="timeout",
        ),
    )
    view.on_scheduled_operations_updated(_decision_capture_snapshot(next_operation))

    assert view.operations_list.currentItem().data(Qt.UserRole) == "decision_evidence_capture"
    detail = view.operations_capture_detail_label.text()
    assert "尚未終結（not_finalized）" in detail
    assert "capture-run-002" in detail
    assert "完成時間：未知" in detail
    assert "已保存：未知" in detail
    assert "已保存：否" not in detail
    assert "snapshot 執行狀態：timeout" in detail
    assert "capture_timeout" in detail
    assert "private stderr" not in detail
    assert "≥86400000 ms（已截限）" in detail
    assert "capture-run-001" not in detail


def test_runtime_capture_separates_saved_result_from_research_use():
    app()
    view = RuntimeView()
    capture = replace(
        _decision_capture_status(),
        capture_mode="eod_research",
        temporal_status="verified",
        research_only=True,
        preopen_authority=False,
        natural_authority=False,
        reservation_wait_seconds=Decimal("4203.062"),
    )
    operation = ScheduledOperationStatusDTO(
        job_id="decision_evidence_capture",
        label="決策證據擷取",
        raw_status="passed",
        state="operational",
        updated_at=datetime(2026, 10, 14, 0, 30, tzinfo=timezone.utc),
        lane="core",
        capture=capture,
    )

    detail = view._render_decision_capture_status(operation)
    assert "已保存：是" in detail
    assert "收盤後研究；不具開盤前或自然證據資格" in detail
    assert "共用資源等待：70 分 03 秒" in detail
    unverified = view._render_decision_capture_status(
        replace(operation, capture=replace(capture, read_state="unverified"))
    )
    assert "時間用途：未證明" in unverified
    assert "共用資源等待：未知" in unverified
    unproven_clock = view._render_decision_capture_status(
        replace(operation, capture=replace(capture, temporal_status="temporal_precision_unproven"))
    )
    assert "時間用途：未證明" in unproven_clock


def test_runtime_view_keeps_legacy_or_untyped_capture_unknown():
    app()
    view = RuntimeView()
    legacy_operation = ScheduledOperationStatusDTO(
        job_id="decision_evidence_capture",
        label="決策證據擷取",
        raw_status="passed",
        state="operational",
        updated_at=None,
        lane="core",
    )
    view.on_scheduled_operations_updated(_decision_capture_snapshot(legacy_operation))
    view.operations_list.setCurrentRow(0)
    assert "終態：未知" in view.operations_capture_detail_label.text()

    untyped_operation = ScheduledOperationStatusDTO(
        job_id="decision_evidence_capture",
        label="決策證據擷取",
        raw_status="passed",
        state="operational",
        updated_at=None,
        lane="core",
        capture=SimpleNamespace(read_state="verified", run_id="forged-run"),
    )
    view.on_scheduled_operations_updated(_decision_capture_snapshot(untyped_operation))
    detail = view.operations_capture_detail_label.text()
    assert "終態：未知" in detail
    assert "forged-run" not in detail


def test_runtime_capture_stage_chart_preserves_order_duplicates_and_bounded_elapsed():
    app()
    view = RuntimeView()
    capture = replace(
        _decision_capture_status(),
        stages=(
            DecisionCaptureStage("same", "completed", 0),
            DecisionCaptureStage("same", "failed", 500, "OSError"),
            DecisionCaptureStage("long", "started", 90_000_000),
            DecisionCaptureStage("bad", "completed", -1),
            DecisionCaptureStage("invalid", "completed", True),
        ),
        unfinished_stages=("long",),
    )
    operation = ScheduledOperationStatusDTO(
        job_id="decision_evidence_capture", label="擷取", raw_status="failed",
        state="attention", updated_at=None, lane="core", capture=capture,
    )
    view.on_scheduled_operations_updated(_decision_capture_snapshot(operation))
    view.operations_list.setCurrentRow(0)

    chart = view.operations_stage_chart
    text = "\n".join(label.text() for label in chart.findChildren(QLabel))
    assert "相對於本次顯示最長階段" in text
    assert "不代表總耗時或成功" in text
    assert "same｜completed｜0 ms" in text
    assert "same｜failed｜500 ms｜錯誤類型：OSError" in text
    assert "long｜started｜≥86400000 ms（已截限）" in text
    assert "未完成階段：long" in view.operations_capture_detail_label.text()
    assert "same｜failed｜500 ms｜未完成" not in text
    assert "bad｜completed｜未知" in text
    assert "invalid｜completed｜未知" in text
    bars = chart.findChildren(QProgressBar)
    assert len(bars) == 5
    stage_text = [bar.parentWidget().findChild(QLabel).text() for bar in bars]
    assert [text.split("｜", 1)[0] for text in stage_text] == [
        "same", "same", "long", "bad", "invalid",
    ]
    assert bars[0].value() == 0
    assert bars[1].value() == 0  # 相對於截限後的最長階段，極短條寬為零。
    assert bars[2].value() == 1000
    assert bars[3].isHidden() and bars[4].isHidden()


def test_runtime_capture_stage_chart_caps_rows_and_clears_on_selection_and_filter():
    app()
    view = RuntimeView()
    stages = tuple(DecisionCaptureStage(f"stage_{i}", "completed", i) for i in range(35))
    capture_operation = ScheduledOperationStatusDTO(
        job_id="decision_evidence_capture", label="擷取", raw_status="passed",
        state="operational", updated_at=None, lane="core",
        capture=replace(_decision_capture_status(), stages=stages),
    )
    other_operation = ScheduledOperationStatusDTO(
        job_id="other", label="其他", raw_status="passed", state="operational",
        updated_at=None, lane="core",
    )
    view.on_scheduled_operations_updated(
        replace(_decision_capture_snapshot(capture_operation), operations=(capture_operation, other_operation), core_job_count=2)
    )
    view.operations_list.setCurrentRow(0)
    chart = view.operations_stage_chart
    assert len(chart.findChildren(QProgressBar)) == 32
    assert any("另有 3 個階段未顯示" in label.text() for label in chart.findChildren(QLabel))

    view.operations_list.setCurrentRow(1)
    assert chart.isHidden()
    view.operations_list.setCurrentRow(0)
    view.operations_state_filter.setCurrentIndex(2)  # guarded, hides the selected operational job
    assert view.operations_list.currentItem() is None
    assert chart.isHidden()

    view.operations_state_filter.setCurrentIndex(0)
    untyped = replace(capture_operation, capture=SimpleNamespace(stages=stages))
    view.on_scheduled_operations_updated(_decision_capture_snapshot(untyped))
    view.operations_list.setCurrentRow(0)
    assert chart.isHidden()

    missing_stages = replace(
        capture_operation,
        capture=replace(_decision_capture_status(), stages=()),
    )
    view.on_scheduled_operations_updated(_decision_capture_snapshot(missing_stages))
    view.operations_list.setCurrentRow(0)
    assert chart.isHidden()


def test_runtime_view_renders_environment_write_boundary_without_claiming_probe_success():
    app()
    view = RuntimeView()
    dto = EnvironmentReadinessSnapshotDTO(
        overall_state="attention",
        observed_at=datetime(2026, 8, 27, 1, 0, tzinfo=timezone.utc),
        data_root="C:/formal/data",
        output_root="C:/formal/output",
        log_root="C:/formal/data/logs",
        research_registry="C:/formal/output/research_runs/research_runs.db",
        paths=(
            EnvironmentPathReadinessDTO(
                key="data_root",
                label="DATA_ROOT",
                path="C:/formal/data",
                kind="directory",
                exists=True,
                parent_exists=True,
                readable=True,
                writable=False,
                requires_write=False,
                status="ready",
            ),
            EnvironmentPathReadinessDTO(
                key="output_root",
                label="OUTPUT_ROOT",
                path="C:/formal/output",
                kind="directory",
                exists=True,
                parent_exists=True,
                readable=True,
                writable=False,
                requires_write=True,
                status="attention",
                diagnostic="output_root_not_writable",
            ),
        ),
        diagnostics=("output_root_not_writable",),
    )

    view.on_environment_readiness_updated(dto)

    assert "需要處理" in view.environment_summary_label.text()
    assert "os.access hint" in view.environment_detail_label.text()
    assert "OUTPUT_ROOT｜需要處理｜讀 是｜寫 否" in view.environment_list.item(1).text()
    assert "output_root_not_writable" in view.environment_list.item(1).toolTip()


def test_runtime_view_does_not_render_historical_governance_event_as_current_halt():
    app()
    view = RuntimeView()
    dto = make_runtime_health_dto()
    dto.observation_scope = "historical_only"
    dto.current_state = RuntimeState.IDLE
    dto.historical_event_count = 1

    view.on_health_updated(dto)

    assert "僅有歷史治理事件" in view.health_state_label.text()
    assert "歷史事件：1" in view.rejection_rate_label.text()
    assert "最近歷史重大違規" in view.last_violation_label.text()


def test_runtime_event_list_keeps_bounded_recent_window():
    app()
    view = RuntimeView()

    for index in range(MAX_RENDERED_RUNTIME_EVENTS + 1):
        view.on_event_received(
            RuntimeEventDTO(
                event_id=str(index),
                timestamp=None,
                actor="runtime",
                event_type="test_start",
                severity=GovernanceSeverity.INFO,
                human_readable_message=str(index),
            )
        )

    assert view.event_list.count() == MAX_RENDERED_RUNTIME_EVENTS
    assert "：1" in view.event_list.item(0).text()


def test_runtime_view_shows_unreadable_event_log_as_not_current_health():
    app()
    view = RuntimeView()
    dto = RuntimeHealthSnapshotDTO(
        is_healthy=False,
        current_state=RuntimeState.IDLE,
        rejection_rate=0,
        rejection_rate_trend="STABLE",
        consecutive_failures=0,
        observation_scope="event_log_unreadable",
        event_log_read_state="unavailable",
        event_log_diagnostic="runtime_event_read_failed:PermissionError",
    )

    view.on_health_updated(dto)

    assert "治理事件檔無法讀取" in view.health_state_label.text()
    assert "事件檔：無法讀取" in view.rejection_rate_label.text()
    assert "PermissionError" in view.health_scope_note_label.text()
