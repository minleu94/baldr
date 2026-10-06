"""B03 兩頁的唯讀呈現、未知與刷新回歸；不啟動正式更新。"""

import os
from datetime import datetime, timezone
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from app_module.dtos.runtime_dtos import (
    EnvironmentReadinessSnapshotDTO, EnvironmentPathReadinessDTO,
    RuntimeHealthSnapshotDTO, RuntimeState, RuntimeStateSnapshotDTO,
    ScheduledOperationStatusDTO, ScheduledOperationsSnapshotDTO,
)
from ui_qt.views.runtime_view import RuntimeView
from ui_qt.views.update_view import UpdateView


@pytest.fixture
def qt_app():
    return QApplication.instance() or QApplication([])


class RenderOnlyUpdateView(UpdateView):
    def _check_data_status(self):
        pass

    def _check_source_detail(self, source, force=False):
        pass


@pytest.fixture
def update_view(qt_app, tmp_path):
    service = SimpleNamespace(config=SimpleNamespace(
        use_sqlite=False, data_root=tmp_path, output_root=tmp_path,
        meta_data_dir=tmp_path, log_dir=tmp_path, profile="test", db_file=tmp_path / "test.db",
    ), scripts_dir=tmp_path)
    view = RenderOnlyUpdateView(service)
    yield view
    view.close()
    view.deleteLater()
    qt_app.processEvents()


@pytest.fixture
def runtime_view(qt_app):
    view = RuntimeView()
    yield view
    view.close()
    view.deleteLater()
    qt_app.processEvents()


def overview(status="current"):
    return {
        "daily_data": {"status": "ok", "latest_date": "2026-10-02", "total_records": 2},
        "technical_indicators": {"status": "ok", "latest_date": "2026-10-01", "total_records": 2},
        "data_update_timeline": {
            "status": status, "last_success_at": "2026-10-03T08:00:00Z",
            "target_date": "2026-10-05", "run_id": "run-b03",
            "steps": [{"name": "下載", "status": "passed", "message": "完整原始明細"}],
            "history": {"records": [{"run_id": "run-b03", "status": "passed"}]},
        },
    }


def test_update_distinguishes_success_data_and_target_dates(update_view):
    update_view._on_status_checked(overview())
    text = update_view.update_impact_label.text()
    assert "最後成功完成：2026-10-03T08:00:00Z" in text
    assert "股價資料日：2026-10-02" in text
    assert "技術指標資料日：2026-10-01" in text
    assert "2026-10-05" not in text
    assert "下一步：" in text
    assert "run-b03" in update_view.data_update_timeline_summary_label.text()


@pytest.mark.parametrize("state", ["unknown", "failed", "invalid", "stale", "degraded", "running", "partial", "new_token"])
def test_update_adverse_states_do_not_claim_data_ready(update_view, state):
    update_view._on_status_checked(overview(state))
    text = update_view.update_impact_label.text()
    assert "已讀取更新收據" not in text
    assert "下一步：" in text
    assert "不能" in text or "尚不能" in text


def test_update_partial_payload_and_error_clear_previous_dates(update_view, monkeypatch):
    update_view._on_status_checked(overview())
    update_view._on_status_checked({})
    assert "最後成功完成：未知｜股價資料日：未知｜技術指標資料日：未知" in update_view.update_impact_label.text()
    monkeypatch.setattr(QMessageBox, "critical", lambda *args: None)
    update_view._on_status_checked(overview())
    update_view._on_status_error("隔離測試錯誤")
    assert "2026-10-03" not in update_view.update_impact_label.text()
    assert "異常" in update_view.update_impact_label.text()
    assert "隔離測試錯誤" in update_view.daily_status_text.toPlainText()


def test_update_refresh_keeps_page_collapse_and_run_selection(update_view):
    update_view._on_status_checked(overview())
    update_view.timeline_details_button.setChecked(True)
    update_view.data_update_timeline_table.setCurrentCell(0, 0)
    update_view.data_update_timeline_history_table.setCurrentCell(0, 2)
    update_view.nav_list.setCurrentRow(2)
    update_view._on_status_checked(overview())
    assert update_view.timeline_details_button.isChecked()
    assert not update_view.p0_details_button.isChecked()
    assert update_view.nav_list.currentRow() == 2
    assert update_view.data_update_timeline_table.currentRow() == 0
    assert update_view.data_update_timeline_history_table.currentRow() == 0
    assert update_view.data_update_timeline_table.item(0, 2).text() == "完整原始明細"


def operations(state="operational", read_state="observed", reverse=False):
    jobs = tuple(ScheduledOperationStatusDTO(
        job_id=key, label=key, state=state, raw_status="raw-b03", read_state=read_state,
        updated_at=datetime(2026, 10, 6, tzinfo=timezone.utc), diagnostic="完整阻擋原因",
    ) for key in ("job-a", "job-b"))
    return ScheduledOperationsSnapshotDTO(
        overall_state=state, core_ready_count=1, core_job_count=2,
        operations=tuple(reversed(jobs)) if reverse else jobs,
        observed_at=datetime(2026, 10, 6, tzinfo=timezone.utc),
    )


def test_runtime_timestamp_does_not_supply_success_or_data_date(runtime_view):
    runtime_view.on_scheduled_operations_updated(operations())
    assert "最後成功完成：未知" in runtime_view.impact_label.text()
    assert "行情資料日：未知" in runtime_view.impact_label.text()
    assert "2026-10-06" not in runtime_view.impact_label.text()
    assert "觀測時間：" in runtime_view.operations_list.item(0).text()
    assert "raw-b03" not in runtime_view.operations_list.item(0).text()
    assert "raw-b03" in runtime_view.operations_raw_text.toPlainText()
    assert "完整阻擋原因" in runtime_view.operations_raw_text.toPlainText()


@pytest.mark.parametrize("state", ["unavailable", "unknown", "future_state"])
def test_runtime_unknown_operations_never_render_normal(runtime_view, state):
    runtime_view.on_scheduled_operations_updated(operations(state))
    assert "正常" not in runtime_view.operations_summary_label.text()


def test_runtime_unreadable_source_never_render_normal(runtime_view):
    runtime_view.on_scheduled_operations_updated(operations(read_state="unavailable"))
    assert "來源未確認" in runtime_view.operations_summary_label.text()
    assert "正常" not in runtime_view.operations_list.item(0).text()
    runtime_view.on_state_updated(RuntimeStateSnapshotDTO(
        task_objective="test", task_status="IDLE", active_context_files=[], task_read_state="unavailable",
    ))
    assert "任務流程：未知" in runtime_view.impact_label.text()
    assert "未知" in runtime_view.status_label.text()


def test_runtime_current_scope_with_unreadable_log_cannot_render_green(runtime_view):
    runtime_view.on_health_updated(RuntimeHealthSnapshotDTO(
        is_healthy=True, current_state=RuntimeState.IDLE, rejection_rate=0,
        rejection_rate_trend="STABLE", consecutive_failures=0,
        event_log_read_state="unavailable", event_log_diagnostic="完整錯誤",
    ))
    assert "green" not in runtime_view.health_state_label.text()
    assert "目前狀態未知" in runtime_view.impact_label.text()
    assert "完整錯誤" in runtime_view.health_scope_note_label.text()


@pytest.mark.parametrize("scope", ["historical_only", "event_log_unreadable", "timestamp_invalid", "timestamp_future", "event_log_degraded"])
def test_runtime_noncurrent_health_keeps_current_unknown(runtime_view, scope):
    runtime_view.on_health_updated(RuntimeHealthSnapshotDTO(
        is_healthy=True, current_state=RuntimeState.IDLE, rejection_rate=0,
        rejection_rate_trend="STABLE", consecutive_failures=0, observation_scope=scope,
    ))
    assert "目前狀態未知" in runtime_view.impact_label.text()
    assert "不" in runtime_view.health_scope_note_label.text() or "未知" in runtime_view.health_state_label.text()


def test_runtime_refresh_retains_identity_selection_and_details(runtime_view):
    runtime_view.on_scheduled_operations_updated(operations())
    runtime_view.operations_list.setCurrentRow(1)
    runtime_view.operations_details_button.setChecked(True)
    runtime_view.governance_details_button.setChecked(True)
    runtime_view.on_scheduled_operations_updated(operations(reverse=True))
    assert runtime_view.operations_list.currentItem().text().startswith("job-b")
    assert runtime_view.operations_details_button.isChecked()
    assert runtime_view.governance_details_button.isChecked()
    assert not runtime_view.environment_details_button.isChecked()


def test_runtime_environment_unknown_and_selection_are_preserved(runtime_view):
    paths = tuple(EnvironmentPathReadinessDTO(
        key=key, label=key, path=f"test/{key}", kind="directory", exists=True,
        parent_exists=True, readable=True, writable=None, requires_write=True, status="attention",
    ) for key in ("data", "output"))
    dto = EnvironmentReadinessSnapshotDTO(
        overall_state="unknown", observed_at=datetime(2026, 10, 6, tzinfo=timezone.utc),
        data_root="test", output_root="test", log_root="test", research_registry="test", paths=paths,
    )
    runtime_view.on_environment_readiness_updated(dto)
    runtime_view.environment_list.setCurrentRow(1)
    runtime_view.on_environment_readiness_updated(dto)
    assert runtime_view.environment_list.currentRow() == 1
    assert "資料與保存位置：未知" in runtime_view.impact_label.text()
