"""每日臺銀成本研究 lane 的受控排程接線。

此入口只重用已由既有 05:10 recommendation snapshot 與 05:45 source
custody 建立的唯讀輸入，並把 calibration learning child 寫入獨立的
BankTaiwan shadow root。它不重跑 technical／official／snapshot producer，
不寫正式 SQLite、Recommendation、Portfolio、Formal 或 broker state。
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import stat
import subprocess
import sys
import time
from typing import Any, Callable, Literal, Mapping
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_module.recommendation_learning_paths import (
    DEFAULT_DATA_ROOT,
    resolve_recommendation_learning_output_root,
)
from data_module.official_trading_calendar import OfficialTradingCalendar
from ml_module.recommendation_cost_scenario import (
    RecommendationCostScenario,
    build_banktaiwan_cost_scenario,
)
from ml_module.current_restated_research_bridge import (
    CurrentRestatedResearchError,
    CurrentRestatedResearchInvocation,
    add_current_restated_research_arguments,
    parse_current_restated_research_invocation,
    run_current_restated_research_sidecar,
)


TAIPEI = ZoneInfo("Asia/Taipei")
TASK_NAME = "baldr-recommendation-calibration-learning-banktaiwan-shadow-daily"
SCHEDULER_LOCAL_TIME = "05:50"
SCHEDULER_TIMEZONE = "Pacific Standard Time"
DEFAULT_LANE_DIRNAME = "FA_Data_Shadow_BankTaiwan"
DEFAULT_SOURCE_DIRNAME = "FA_Data_Shadow"
DEFAULT_RESEARCH_ORDER_QUANTITY_SHARES = 1000
DEFAULT_POLICY_ESTIMATE_DATE = "2026-01-01"
DEFAULT_CALENDAR_CACHE_ROOT = (
    ROOT / "output" / "paper_execution_eod_replay" / "calendar_cache"
)
OPERATION_SCHEMA_VERSION = "banktaiwan-recommendation-learning-operational.v1"
_MAX_SNAPSHOT_STATUS_BYTES = 8 * 1024 * 1024
_MAX_OPERATIONAL_STATUS_BYTES = 8 * 1024 * 1024
_MAX_CHILD_RUN_RECEIPT_BYTES = 16 * 1024 * 1024
_MAX_CHILD_CLI_STDOUT_ARTIFACT_BYTES = 16 * 1024 * 1024
_MAX_PIPELINE_TERMINAL_RECEIPT_BYTES = 64 * 1024
_BANK_TASK_EXECUTION_BUDGET_SECONDS = 2 * 60 * 60
_BANK_TERMINAL_FLUSH_RESERVE_SECONDS = 5 * 60
_DEFAULT_UPSTREAM_PROJECTION_WAIT_SECONDS = 0
_MAX_UPSTREAM_PROJECTION_WAIT_SECONDS = 1800
_UPSTREAM_TASK_STATE_POLL_SECONDS = 5
_UPSTREAM_WAIT_HEARTBEAT_SECONDS = 30
_UPSTREAM_TASK_START_EARLY_TOLERANCE_SECONDS = 2
_UPSTREAM_TASK_START_LATE_TOLERANCE_SECONDS = 30
_UPSTREAM_STATUS_MTIME_EARLY_TOLERANCE_SECONDS = 1
_UPSTREAM_FUTURE_CLOCK_TOLERANCE_SECONDS = 2
_CHILD_CLI_SCHEMA_VERSION = "daily-recommendation-learning-cli-result.v3"
_CHILD_RECEIPT_SCHEMA_VERSION = "daily-recommendation-learning-receipt.v1"
_CHILD_RUN_FAILURE_STATUSES = frozenset(
    {"failed_dependency", "failed_training", "failed_candidate", "failed_lineage"}
)
_CHILD_RUN_SKIP_STATUSES = frozenset(
    {"skipped_insufficient_evidence", "skipped_no_data"}
)

_REUSABLE_TERMINAL_STATUSES = frozenset(
    {
        "completed_shadow",
        "completed_waiting_natural_maturity",
        "completed_with_advisories",
        "skipped_non_trading_day",
    }
)


class OperationalLaneError(ValueError):
    """操作 lane 的 path／輸入契約錯誤。"""


class OperationalOverlapError(RuntimeError):
    """另一個相同 lane 的 process 已持有執行鎖。"""


@dataclass(frozen=True)
class ScheduledTaskObservation:
    """固定上游 Windows Task 的唯讀執行狀態。"""

    task_name: str
    task_path: str
    state: str
    last_run_time_utc: datetime


@dataclass(frozen=True)
class UpstreamRunProof:
    """由 TaskScheduler 與 bounded producer status 共同驗證的當次執行。"""

    run_id: str
    last_run_time_utc: datetime
    status_mtime_utc: datetime


@dataclass(frozen=True)
class OperationalPaths:
    """每日 task 的所有輸出與唯讀輸入路徑。"""

    data_root: Path
    lane_output_root: Path
    lane_learning_root: Path
    operational_root: Path
    latest_status_path: Path
    runs_root: Path
    logs_root: Path
    lock_path: Path
    snapshot_output_root: Path
    source_artifact_root: Path
    source_db: Path


@dataclass(frozen=True)
class SnapshotSummary:
    """已驗證同次 canonical snapshot 與 pipeline invocation 的唯讀摘要。"""

    path: Path
    payload: Mapping[str, Any]
    symbols: tuple[str, ...]
    cohort: Mapping[str, Any]
    file_sha256: str
    status_path: Path
    status_payload: Mapping[str, Any]
    pipeline_run_id: str
    pipeline_status_path: Path
    pipeline_status_payload: Mapping[str, Any]
    result_id: str
    payload_hash: str
    canonical_artifact_sha256: str
    schema_version: str
    schema_revision: int
    integrity_basis: str
    decision_date: str
    data_as_of_date: str
    decision_at: str
    available_at: str | None
    cohort_hash: str
    invocation_output_path: Path
    invocation_output_sha256: str
    invocation_output_size: int


def _official_calendar(source_db: Path) -> OfficialTradingCalendar:
    configured = os.environ.get("FORMAL_DAILY_CALENDAR_CACHE_ROOT")
    cache_root = (
        Path(configured).expanduser().resolve()
        if isinstance(configured, str) and configured.strip()
        else DEFAULT_CALENDAR_CACHE_ROOT.resolve()
    )
    return OfficialTradingCalendar(
        db_path=source_db,
        calendar_cache_path=cache_root,
        temporary_closure_path=cache_root,
    )


ChildRunner = Callable[
    [OperationalPaths, date, RecommendationCostScenario, argparse.Namespace],
    Mapping[str, Any],
]


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _read_bounded_snapshot_status(
    path: Path,
    *,
    root: Path,
) -> tuple[dict[str, Any] | None, str | None]:
    """只從錨定輸出根讀取小型、穩定且非連結的狀態 JSON。"""

    from app_module.recommendation.queries import (
        ExecutionArtifactIntegrityError,
        _read_regular_file_no_follow,
    )

    try:
        path.lstat()
    except FileNotFoundError:
        return None, "missing_or_invalid"
    except OSError:
        return None, "unreadable_or_unsafe"
    try:
        raw = _read_regular_file_no_follow(
            path,
            root,
            max_bytes=_MAX_SNAPSHOT_STATUS_BYTES,
        )
    except (ExecutionArtifactIntegrityError, OSError):
        return None, "unreadable_or_unsafe"
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        return None, "missing_or_invalid"
    if not isinstance(payload, dict):
        return None, "missing_or_invalid"
    return payload, None


def _read_bounded_snapshot_status_with_mtime(
    path: Path,
    *,
    root: Path,
) -> tuple[dict[str, Any] | None, datetime | None, str | None]:
    """以既有 no-follow reader 讀取 bounded 狀態並確認讀取期間檔案未換代。"""

    try:
        before = path.lstat()
    except FileNotFoundError:
        return None, None, "missing_or_invalid"
    except OSError:
        return None, None, "unreadable_or_unsafe"
    if not stat.S_ISREG(before.st_mode):
        return None, None, "unreadable_or_unsafe"

    payload, error = _read_bounded_snapshot_status(path, root=root)
    if payload is None:
        return None, None, error or "missing_or_invalid"

    try:
        after = path.lstat()
    except OSError:
        return None, None, "unreadable_or_unsafe"
    if not stat.S_ISREG(after.st_mode):
        return None, None, "unreadable_or_unsafe"
    stability_before = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    )
    stability_after = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    )
    if stability_before != stability_after:
        return None, None, "unreadable_or_unsafe"
    return payload, datetime.fromtimestamp(after.st_mtime, timezone.utc), None


def _parse_aware_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif type(value) is str:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    try:
        return parsed.astimezone(timezone.utc)
    except (OverflowError, ValueError):
        return None


def _parse_pipeline_run_id_start(run_id: object) -> datetime | None:
    if type(run_id) is not str or len(run_id) > 96:
        return None
    parts = run_id.split("-")
    if (
        len(parts) != 3
        or re.fullmatch(r"\d{8}", parts[0]) is None
        or re.fullmatch(r"[0-9a-f]{12}", parts[2]) is None
    ):
        return None
    try:
        return datetime.strptime(parts[1], "%Y%m%dT%H%M%S%fZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        return None


def _query_upstream_task_observation() -> ScheduledTaskObservation | None:
    """查詢固定 Recommendation learning Task；不接受 caller 傳入 task 或命令。"""

    if os.name != "nt":
        return None
    system_root = os.environ.get("SystemRoot")
    if not isinstance(system_root, str) or not system_root.strip():
        return None
    powershell = (
        Path(system_root)
        / "System32"
        / "WindowsPowerShell"
        / "v1.0"
        / "powershell.exe"
    )
    if not powershell.is_file():
        return None
    query = (
        "$ErrorActionPreference='Stop'; "
        "$task=Get-ScheduledTask -TaskName "
        "'baldr-recommendation-calibration-learning-daily' -TaskPath '\\' "
        "-ErrorAction Stop; "
        "$info=Get-ScheduledTaskInfo -TaskName "
        "'baldr-recommendation-calibration-learning-daily' -TaskPath '\\' "
        "-ErrorAction Stop; "
        "$value=[ordered]@{task_name=[string]$task.TaskName; "
        "task_path=[string]$task.TaskPath; state=[string]$task.State; "
        "last_run_time_utc=$info.LastRunTime.ToUniversalTime().ToString('o')}; "
        "[Console]::WriteLine((ConvertTo-Json -InputObject $value -Compress))"
    )
    try:
        completed = subprocess.run(
            [
                str(powershell),
                "-NoLogo",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                query,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=5,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0 or len(completed.stdout) > 4096:
        return None
    try:
        value = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return None
    if not isinstance(value, Mapping):
        return None
    last_run_time = _parse_aware_datetime(value.get("last_run_time_utc"))
    task_name = value.get("task_name")
    task_path = value.get("task_path")
    state = value.get("state")
    if (
        type(task_name) is not str
        or type(task_path) is not str
        or type(state) is not str
        or last_run_time is None
    ):
        return None
    return ScheduledTaskObservation(
        task_name=task_name,
        task_path=task_path,
        state=state,
        last_run_time_utc=last_run_time,
    )


def _pipeline_paths(output_root: Path) -> tuple[Path, Path, Path]:
    pipeline_root = (
        output_root
        / "scheduled"
        / "recommendation_calibration_learning"
    )
    return (
        pipeline_root,
        pipeline_root / "latest_status.json",
        pipeline_root / "latest_snapshot_source_status.json",
    )


def _current_upstream_run_proof(
    *,
    output_root: Path,
    decision_date: date,
    task_state_reader: Callable[[], ScheduledTaskObservation | None],
    now: datetime,
    recheck_task_state: bool = True,
) -> tuple[UpstreamRunProof | None, str | None]:
    """確認固定 Task 與同日 running payload 指向同一個新 producer run。"""

    expected_date = decision_date.isoformat()
    current_day = now.astimezone(TAIPEI).date()
    if decision_date != current_day:
        return None, "upstream_wait_not_current_taipei_day"

    observation = task_state_reader()
    if observation is None:
        return None, "upstream_task_state_unavailable"
    if (
        observation.task_name != "baldr-recommendation-calibration-learning-daily"
        or observation.task_path != "\\"
    ):
        return None, "upstream_task_identity_mismatch"
    if observation.state != "Running":
        return None, "upstream_task_not_running"
    last_run_time = _parse_aware_datetime(observation.last_run_time_utc)
    if last_run_time is None:
        return None, "upstream_task_last_run_time_invalid"
    now_utc = now.astimezone(timezone.utc)
    future_clock_tolerance = timedelta(
        seconds=_UPSTREAM_FUTURE_CLOCK_TOLERANCE_SECONDS
    )
    if last_run_time > now_utc + future_clock_tolerance:
        return None, "upstream_task_last_run_time_in_future"

    _pipeline_root, status_path, _projection_path = _pipeline_paths(output_root)
    payload, status_mtime, error = _read_bounded_snapshot_status_with_mtime(
        status_path,
        root=output_root,
    )
    if payload is None or status_mtime is None:
        return None, f"upstream_running_status_{error or 'missing_or_invalid'}"
    if (
        payload.get("schema_version") != "daily-recommendation-learning-pipeline.v1"
        or payload.get("task") != observation.task_name
        or payload.get("status") != "running"
        or payload.get("decision_date") != expected_date
        or payload.get("decision_timezone") != "Asia/Taipei"
        or not _same_resolved_path(payload.get("output_root"), output_root)
        or not _same_resolved_path(payload.get("status_path"), status_path)
    ):
        return None, "upstream_running_status_identity_mismatch"

    run_id = payload.get("run_id")
    run_start = _parse_pipeline_run_id_start(run_id)
    if (
        type(run_id) is not str
        or run_start is None
        or not run_id.startswith(decision_date.strftime("%Y%m%d") + "-")
    ):
        return None, "upstream_running_status_run_id_invalid"
    if run_start > now_utc + future_clock_tolerance:
        return None, "upstream_running_status_run_start_in_future"
    if status_mtime > now_utc + future_clock_tolerance:
        return None, "upstream_running_status_mtime_in_future"
    early_tolerance = timedelta(seconds=_UPSTREAM_TASK_START_EARLY_TOLERANCE_SECONDS)
    late_tolerance = timedelta(seconds=_UPSTREAM_TASK_START_LATE_TOLERANCE_SECONDS)
    if run_start < last_run_time - early_tolerance:
        return None, "upstream_running_status_run_precedes_task_last_run"
    if run_start > last_run_time + late_tolerance:
        return None, "upstream_running_status_run_start_too_late"
    if status_mtime < last_run_time - timedelta(
        seconds=_UPSTREAM_STATUS_MTIME_EARLY_TOLERANCE_SECONDS
    ):
        return None, "upstream_running_status_mtime_precedes_task_last_run"
    if status_mtime > last_run_time + late_tolerance:
        return None, "upstream_running_status_mtime_too_late_for_task_start"

    if recheck_task_state:
        latest_observation = task_state_reader()
        if latest_observation != observation:
            return None, "upstream_task_observation_changed_during_proof"

    return (
        UpstreamRunProof(
            run_id=run_id,
            last_run_time_utc=last_run_time,
            status_mtime_utc=status_mtime,
        ),
        None,
    )


def _read_pipeline_projection(
    *,
    output_root: Path,
) -> tuple[dict[str, Any] | None, str | None]:
    _pipeline_root, _status_path, projection_path = _pipeline_paths(output_root)
    return _read_bounded_snapshot_status(projection_path, root=output_root)


def _validate_stale_pipeline_projection(
    payload: Mapping[str, Any],
    *,
    output_root: Path,
    decision_date: date,
    current_run_proof: UpstreamRunProof,
) -> str | None:
    """只把格式正確、明確早於目前 Task instance 的 projection 當 transient。"""

    if (
        payload.get("schema_version") != "daily-recommendation-snapshot-source.v1"
        or payload.get("task") != "baldr-recommendation-calibration-learning-daily"
        or not _same_resolved_path(payload.get("output_root"), output_root)
    ):
        return "recommendation_pipeline_projection_identity_mismatch"
    prior_date_value = payload.get("decision_date")
    if type(prior_date_value) is not str:
        return "recommendation_pipeline_projection_date_invalid"
    try:
        prior_date = date.fromisoformat(prior_date_value)
    except ValueError:
        return "recommendation_pipeline_projection_date_invalid"
    if prior_date > decision_date:
        return "recommendation_pipeline_projection_date_in_future"
    prior_run_id = payload.get("run_id")
    prior_start = _parse_pipeline_run_id_start(prior_run_id)
    if (
        type(prior_run_id) is not str
        or prior_start is None
        or not prior_run_id.startswith(prior_date.strftime("%Y%m%d") + "-")
    ):
        return "recommendation_pipeline_projection_run_id_invalid"
    if prior_start >= current_run_proof.last_run_time_utc - timedelta(
        seconds=_UPSTREAM_TASK_START_EARLY_TOLERANCE_SECONDS
    ):
        return "recommendation_pipeline_projection_run_id_not_stale"
    completed_at = _parse_aware_datetime(payload.get("completed_at"))
    if completed_at is None or completed_at > current_run_proof.last_run_time_utc:
        return "recommendation_pipeline_projection_terminal_clock_invalid"
    status = payload.get("status")
    if (
        type(status) is not str
        or status not in {"passed", "passed_with_warnings", "failed"}
    ):
        return "recommendation_pipeline_projection_status_invalid"

    steps = payload.get("steps")
    if isinstance(steps, Mapping):
        snapshot = steps.get("recommendation_snapshot")
        if isinstance(snapshot, Mapping):
            output_hash = snapshot.get("child_stdout_sha256")
            if output_hash is not None and not _is_sha256_text(output_hash):
                return "recommendation_pipeline_projection_child_hash_invalid"
            output_size = snapshot.get("child_stdout_artifact_size")
            if output_size is not None and (type(output_size) is not int or output_size <= 0):
                return "recommendation_pipeline_projection_child_size_invalid"
    return None


def _verify_current_pipeline_terminal_receipt(
    *,
    output_root: Path,
    projection: Mapping[str, Any],
    run_id: str,
) -> str | None:
    pipeline_root, status_path, _projection_path = _pipeline_paths(output_root)
    receipt_path = pipeline_root / "runs" / run_id / "receipt.json"
    try:
        from app_module.recommendation.queries import (
            ExecutionArtifactIntegrityError,
            _read_regular_file_no_follow,
        )

        raw = _read_regular_file_no_follow(
            receipt_path,
            output_root,
            max_bytes=_MAX_PIPELINE_TERMINAL_RECEIPT_BYTES,
        )
    except (ExecutionArtifactIntegrityError, OSError):
        return "recommendation_pipeline_terminal_receipt_unreadable"
    try:
        receipt = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        return "recommendation_pipeline_terminal_receipt_invalid"
    if not isinstance(receipt, Mapping):
        return "recommendation_pipeline_terminal_receipt_invalid"
    if (
        receipt.get("schema_version")
        != "daily-recommendation-learning-terminal-receipt.v1"
        or receipt.get("task") != "baldr-recommendation-calibration-learning-daily"
        or receipt.get("run_id") != run_id
        or receipt.get("decision_date") != projection.get("decision_date")
        or receipt.get("decision_timezone") != "Asia/Taipei"
        or receipt.get("status") != projection.get("status")
        or receipt.get("completed_at") != projection.get("completed_at")
        or receipt.get("terminal") is not True
        or not _same_resolved_path(receipt.get("status_path"), status_path)
        or not _same_resolved_path(
            receipt.get("log_path"),
            pipeline_root
            / f"{str(projection.get('decision_date', '')).replace('-', '')}_pipeline.log",
        )
    ):
        return "recommendation_pipeline_terminal_receipt_identity_mismatch"
    projection_steps = projection.get("steps")
    receipt_steps = receipt.get("steps")
    projection_step = (
        projection_steps.get("recommendation_snapshot")
        if isinstance(projection_steps, Mapping)
        else None
    )
    receipt_step = (
        receipt_steps.get("recommendation_snapshot")
        if isinstance(receipt_steps, Mapping)
        else None
    )
    if not isinstance(projection_step, Mapping) or not isinstance(receipt_step, Mapping):
        return "recommendation_pipeline_terminal_receipt_snapshot_step_missing"
    for key in (
        "status",
        "returncode",
        "child_stdout_artifact_path",
        "child_stdout_artifact_size",
        "child_stdout_sha256",
    ):
        if projection_step.get(key) != receipt_step.get(key):
            return "recommendation_pipeline_terminal_receipt_snapshot_binding_mismatch"
    return None


def _validate_current_pipeline_projection(
    payload: Mapping[str, Any],
    *,
    output_root: Path,
    decision_date: date,
    run_id: str,
) -> str | None:
    if (
        payload.get("schema_version") != "daily-recommendation-snapshot-source.v1"
        or payload.get("task") != "baldr-recommendation-calibration-learning-daily"
        or payload.get("run_id") != run_id
        or payload.get("decision_date") != decision_date.isoformat()
        or not _same_resolved_path(payload.get("output_root"), output_root)
        or type(payload.get("status")) is not str
        or payload.get("status") not in {"passed", "passed_with_warnings", "failed"}
        or _parse_aware_datetime(payload.get("completed_at")) is None
    ):
        return "recommendation_pipeline_current_projection_identity_or_terminal_mismatch"
    return None


def _try_accept_published_current_projection(
    *,
    paths: OperationalPaths,
    decision_date: date,
    initial_snapshot: SnapshotSummary | None,
    initial_observation: ScheduledTaskObservation,
    task_state_reader: Callable[[], ScheduledTaskObservation | None],
    now_provider: Callable[[], datetime],
) -> tuple[bool, SnapshotSummary | None, str | None, dict[str, Any]]:
    """以固定 Task instance 時鐘驗證並接納已發布的 terminal projection。

    這條完成競態路徑只讀 bounded projection、immutable receipt 與既有
    same-day canonical 驗證，不碰可能已換成大型 terminal payload 的 parent
    latest_status.json。回傳第一個 bool 表示 projection 是否已綁定目前 Task；
    舊同日 projection 回傳 False，交給既有 running proof pin 目前 run。
    """

    audit: dict[str, Any] = {"status": "not_applicable", "waited_seconds": 0.0}
    if (
        initial_observation.task_name
        != "baldr-recommendation-calibration-learning-daily"
        or initial_observation.task_path != "\\"
        or initial_observation.state not in {"Running", "Ready"}
    ):
        return False, None, None, audit

    now = now_provider()
    if decision_date != now.astimezone(TAIPEI).date():
        return False, None, None, audit
    now_utc = now.astimezone(timezone.utc)
    future_tolerance = timedelta(seconds=_UPSTREAM_FUTURE_CLOCK_TOLERANCE_SECONDS)
    last_run_time = _parse_aware_datetime(initial_observation.last_run_time_utc)
    if last_run_time is None:
        return True, None, "upstream_task_last_run_time_invalid", {
            "status": "current_terminal_proof_invalid",
            "reason": "upstream_task_last_run_time_invalid",
        }
    if last_run_time > now_utc + future_tolerance:
        return True, None, "upstream_task_last_run_time_in_future", {
            "status": "current_terminal_proof_invalid",
            "reason": "upstream_task_last_run_time_in_future",
        }

    _pipeline_root, _status_path, projection_path = _pipeline_paths(
        paths.snapshot_output_root
    )
    projection, projection_mtime, projection_error = (
        _read_bounded_snapshot_status_with_mtime(
            projection_path,
            root=paths.snapshot_output_root,
        )
    )
    if projection is None or projection_mtime is None:
        # producer 尚未發布 projection 時，running status 仍可由後續 live
        # proof 驗證並等待；其他讀取錯誤則不會被當成有效終態來源。
        audit["status"] = "projection_unavailable"
        audit["reason"] = projection_error or "missing_or_invalid"
        return False, None, None, audit

    run_id = projection.get("run_id")
    run_start = _parse_pipeline_run_id_start(run_id)
    projection_date_value = projection.get("decision_date")
    try:
        projection_date = (
            date.fromisoformat(projection_date_value)
            if type(projection_date_value) is str
            else None
        )
    except ValueError:
        projection_date = None
    if (
        type(run_id) is not str
        or run_start is None
        or projection_date is None
        or not run_id.startswith(projection_date.strftime("%Y%m%d") + "-")
    ):
        reason = "recommendation_pipeline_terminal_run_identity_invalid"
        return True, None, reason, {
            "status": "current_terminal_proof_invalid",
            "reason": reason,
        }
    if projection_date > decision_date:
        reason = "recommendation_pipeline_projection_date_in_future"
        return True, None, reason, {
            "status": "current_terminal_proof_invalid",
            "upstream_run_id": run_id,
            "reason": reason,
        }
    if run_start < last_run_time - timedelta(
        seconds=_UPSTREAM_TASK_START_EARLY_TOLERANCE_SECONDS
    ):
        # 舊日期或舊同日 terminal source 不能證明新 Task instance；交回既有
        # bounded live-proof/wait 路徑。
        audit.update(
            {
                "status": "stale_projection_for_task",
                "upstream_run_id": run_id,
                "upstream_last_run_time_utc": last_run_time.isoformat(),
            }
        )
        return False, None, None, audit
    if projection_date != decision_date:
        reason = "recommendation_pipeline_current_projection_date_mismatch"
        return True, None, reason, {
            "status": "current_terminal_proof_invalid",
            "upstream_run_id": run_id,
            "reason": reason,
        }

    identity_error = _validate_current_pipeline_projection(
        projection,
        output_root=paths.snapshot_output_root,
        decision_date=decision_date,
        run_id=run_id,
    )
    if identity_error is not None:
        return True, None, identity_error, {
            "status": "current_terminal_proof_invalid",
            "upstream_run_id": run_id,
            "reason": identity_error,
        }

    completed_at = _parse_aware_datetime(projection.get("completed_at"))
    late_tolerance = timedelta(seconds=_UPSTREAM_TASK_START_LATE_TOLERANCE_SECONDS)
    early_tolerance = timedelta(
        seconds=_UPSTREAM_TASK_START_EARLY_TOLERANCE_SECONDS
    )
    clock_error: str | None = None
    if run_start > now_utc + future_tolerance:
        clock_error = "recommendation_pipeline_terminal_run_start_in_future"
    elif run_start > last_run_time + late_tolerance:
        clock_error = "recommendation_pipeline_terminal_run_start_too_late"
    elif completed_at is None or completed_at < run_start:
        clock_error = "recommendation_pipeline_terminal_completed_at_precedes_run_start"
    elif completed_at < last_run_time - early_tolerance:
        clock_error = "recommendation_pipeline_terminal_completed_at_precedes_task_last_run"
    elif completed_at > now_utc + future_tolerance:
        clock_error = "recommendation_pipeline_terminal_completed_at_in_future"
    elif projection_mtime < run_start:
        clock_error = "recommendation_pipeline_projection_mtime_precedes_run_start"
    elif projection_mtime > now_utc + future_tolerance:
        clock_error = "recommendation_pipeline_projection_mtime_in_future"
    elif projection_mtime < completed_at - timedelta(
        seconds=_UPSTREAM_STATUS_MTIME_EARLY_TOLERANCE_SECONDS
    ):
        clock_error = "recommendation_pipeline_projection_mtime_precedes_terminal_completion"
    if clock_error is not None:
        return True, None, clock_error, {
            "status": "current_terminal_proof_invalid",
            "upstream_run_id": run_id,
            "reason": clock_error,
        }
    assert run_start is not None and completed_at is not None

    receipt_error = _verify_current_pipeline_terminal_receipt(
        output_root=paths.snapshot_output_root,
        projection=projection,
        run_id=run_id,
    )
    if receipt_error is not None:
        return True, None, receipt_error, {
            "status": "current_terminal_proof_invalid",
            "upstream_run_id": run_id,
            "reason": receipt_error,
        }

    latest_snapshot, snapshot_error = load_same_day_snapshot(
        output_root=paths.snapshot_output_root,
        decision_date=decision_date,
    )
    if latest_snapshot is None:
        reason = (
            "recommendation_pipeline_current_snapshot_unverified:"
            f"{snapshot_error or 'missing'}"
        )
        return True, None, reason, {
            "status": "current_terminal_proof_invalid",
            "upstream_run_id": run_id,
            "reason": reason,
        }

    latest_binding = (
        latest_snapshot.pipeline_run_id,
        latest_snapshot.result_id,
        latest_snapshot.payload_hash,
        latest_snapshot.canonical_artifact_sha256,
        latest_snapshot.cohort_hash,
        latest_snapshot.invocation_output_path,
        latest_snapshot.invocation_output_sha256,
        latest_snapshot.invocation_output_size,
        latest_snapshot.decision_at,
        latest_snapshot.available_at,
        latest_snapshot.data_as_of_date,
    )
    same_initial_run = (
        initial_snapshot is not None
        and initial_snapshot.pipeline_run_id == run_id
    )
    initial_binding = (
        (
            initial_snapshot.pipeline_run_id,
            initial_snapshot.result_id,
            initial_snapshot.payload_hash,
            initial_snapshot.canonical_artifact_sha256,
            initial_snapshot.cohort_hash,
            initial_snapshot.invocation_output_path,
            initial_snapshot.invocation_output_sha256,
            initial_snapshot.invocation_output_size,
            initial_snapshot.decision_at,
            initial_snapshot.available_at,
            initial_snapshot.data_as_of_date,
        )
        if same_initial_run and initial_snapshot is not None
        else None
    )
    if (
        latest_snapshot.pipeline_run_id != run_id
        or (same_initial_run and latest_binding != initial_binding)
        or dict(latest_snapshot.pipeline_status_payload) != projection
        or (
            same_initial_run
            and initial_snapshot is not None
            and dict(initial_snapshot.pipeline_status_payload) != projection
        )
    ):
        reason = "recommendation_pipeline_current_snapshot_binding_changed"
        return True, None, reason, {
            "status": "current_terminal_proof_invalid",
            "upstream_run_id": run_id,
            "reason": reason,
        }

    # 讀回 canonical 與 invocation 後再次確認 projection 同一份 bytes 狀態，
    # 並確認 Windows Task 的 instance 沒有在驗證期間被新觸發取代。
    projection_after, projection_mtime_after, projection_after_error = (
        _read_bounded_snapshot_status_with_mtime(
            projection_path,
            root=paths.snapshot_output_root,
        )
    )
    if (
        projection_after is None
        or projection_mtime_after is None
        or projection_after_error is not None
        or projection_after != projection
        or projection_mtime_after != projection_mtime
    ):
        reason = "recommendation_pipeline_current_projection_changed_during_readback"
        return True, None, reason, {
            "status": "current_terminal_proof_invalid",
            "upstream_run_id": run_id,
            "reason": reason,
        }

    latest_observation = task_state_reader()
    latest_last_run = (
        _parse_aware_datetime(latest_observation.last_run_time_utc)
        if latest_observation is not None
        else None
    )
    if (
        latest_observation is None
        or latest_observation.task_name
        != "baldr-recommendation-calibration-learning-daily"
        or latest_observation.task_path != "\\"
        or latest_last_run != last_run_time
        or latest_observation.state not in {"Running", "Ready"}
    ):
        reason = "upstream_task_observation_changed_during_terminal_readback"
        return True, None, reason, {
            "status": "current_terminal_proof_invalid",
            "upstream_run_id": run_id,
            "reason": reason,
        }

    final_now = now_provider().astimezone(timezone.utc)
    if (
        last_run_time > final_now + future_tolerance
        or run_start > final_now + future_tolerance
        or projection_mtime > final_now + future_tolerance
        or completed_at > final_now + future_tolerance
    ):
        reason = "recommendation_pipeline_terminal_clock_in_future"
        return True, None, reason, {
            "status": "current_terminal_proof_invalid",
            "upstream_run_id": run_id,
            "reason": reason,
        }

    return True, latest_snapshot, None, {
        "status": "current_terminal_projection_available",
        "upstream_run_id": run_id,
        "upstream_last_run_time_utc": last_run_time.isoformat(),
        "run_start_utc": run_start.isoformat(),
        "projection_mtime_utc": projection_mtime.isoformat(),
        "completed_at": completed_at.isoformat(),
        "terminal_receipt_verified": True,
        "task_state_before": initial_observation.state,
        "task_state_after": latest_observation.state,
        "waited_seconds": 0.0,
        "poll_count": 0,
    }


class _WaitHeartbeatLog:
    """每次 wait 建立唯一 JSONL 紀錄，保留 bounded liveness 更新。"""

    def __init__(self, paths: OperationalPaths, decision_date: date) -> None:
        paths.logs_root.mkdir(parents=True, exist_ok=True)
        self.path = paths.logs_root / (
            f"{decision_date.strftime('%Y%m%d')}_upstream_wait_"
            f"{secrets.token_hex(8)}.jsonl"
        )
        self._stream = self.path.open("xb")

    def write(self, payload: Mapping[str, Any]) -> None:
        encoded = (
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            + "\n"
        ).encode("utf-8")
        if len(encoded) > 4096:
            raise ValueError("upstream wait heartbeat exceeds the 4 KiB bound")
        self._stream.write(encoded)
        self._stream.flush()
        os.fsync(self._stream.fileno())

    def close(self) -> None:
        self._stream.close()


def _write_wait_heartbeat_safely(
    writer: Callable[[Mapping[str, Any]], None] | None,
    payload: Mapping[str, Any],
) -> str | None:
    if writer is None:
        return None
    try:
        writer(payload)
    except (OSError, ValueError, TypeError) as exc:
        return f"{type(exc).__name__}:{exc}"
    return None


def _wait_for_exact_upstream_projection(
    *,
    paths: OperationalPaths,
    decision_date: date,
    proof: UpstreamRunProof,
    wait_seconds: int,
    attempt_deadline: float,
    task_state_reader: Callable[[], ScheduledTaskObservation | None],
    monotonic: Callable[[], float],
    sleep: Callable[[float], None],
    now_provider: Callable[[], datetime],
    heartbeat_writer: Callable[[Mapping[str, Any]], None],
    heartbeat_path: Path,
) -> tuple[SnapshotSummary | None, str | None, dict[str, Any]]:
    started_monotonic = monotonic()
    deadline = min(
        started_monotonic + max(0, wait_seconds),
        attempt_deadline,
    )
    last_heartbeat = started_monotonic
    poll_count = 0
    last_projection_run_id: str | None = None
    last_projection_date: str | None = None

    def finish(
        *,
        status: str,
        reason: str | None,
        snapshot: SnapshotSummary | None = None,
    ) -> tuple[SnapshotSummary | None, str | None, dict[str, Any]]:
        nonlocal last_heartbeat
        elapsed = max(0.0, monotonic() - started_monotonic)
        audit = {
            "enabled": True,
            "status": status,
            "upstream_task": "baldr-recommendation-calibration-learning-daily",
            "upstream_run_id": proof.run_id,
            "upstream_last_run_time_utc": proof.last_run_time_utc.isoformat(),
            "status_mtime_utc": proof.status_mtime_utc.isoformat(),
            "wait_limit_seconds": wait_seconds,
            "waited_seconds": round(elapsed, 3),
            "poll_count": poll_count,
            "last_projection_run_id": last_projection_run_id,
            "last_projection_decision_date": last_projection_date,
            "heartbeat_path": str(heartbeat_path),
            "reason": reason,
        }
        heartbeat_error = _write_wait_heartbeat_safely(
            heartbeat_writer,
            {
                "schema_version": "banktaiwan-upstream-projection-wait.v1",
                "task": TASK_NAME,
                "decision_date": decision_date.isoformat(),
                "heartbeat_at": now_provider().isoformat(timespec="seconds"),
                **audit,
            },
        )
        last_heartbeat = monotonic()
        if heartbeat_error is not None:
            audit["status"] = "blocked"
            audit["reason"] = "upstream_wait_heartbeat_write_failed"
            audit["heartbeat_error"] = heartbeat_error
            return None, "recommendation_pipeline_wait_heartbeat_write_failed", audit
        return snapshot, reason, audit

    initial_heartbeat_error = _write_wait_heartbeat_safely(
        heartbeat_writer,
        {
            "schema_version": "banktaiwan-upstream-projection-wait.v1",
            "task": TASK_NAME,
            "decision_date": decision_date.isoformat(),
            "heartbeat_at": now_provider().isoformat(timespec="seconds"),
            "enabled": True,
            "status": "waiting",
            "upstream_task": "baldr-recommendation-calibration-learning-daily",
            "upstream_run_id": proof.run_id,
            "upstream_last_run_time_utc": proof.last_run_time_utc.isoformat(),
            "status_mtime_utc": proof.status_mtime_utc.isoformat(),
            "wait_limit_seconds": wait_seconds,
            "waited_seconds": 0.0,
            "poll_count": 0,
            "heartbeat_path": str(heartbeat_path),
        },
    )
    if initial_heartbeat_error is not None:
        return finish(
            status="blocked",
            reason="recommendation_pipeline_wait_heartbeat_write_failed",
        )
    last_heartbeat = monotonic()

    while True:
        poll_count += 1
        projection_path = _pipeline_paths(paths.snapshot_output_root)[2]
        try:
            projection_exists = os.path.lexists(projection_path)
        except OSError:
            projection_exists = True
        if projection_exists:
            projection, projection_error = _read_pipeline_projection(
                output_root=paths.snapshot_output_root
            )
            if projection is None:
                return finish(
                    status="blocked",
                    reason=(
                        "recommendation_pipeline_projection_unreadable:"
                        f"{projection_error or 'unknown'}"
                    ),
                )
            last_projection_run_id = (
                projection.get("run_id")
                if type(projection.get("run_id")) is str
                else None
            )
            last_projection_date = (
                projection.get("decision_date")
                if type(projection.get("decision_date")) is str
                else None
            )
            if last_projection_run_id == proof.run_id:
                terminal_observation = task_state_reader()
                if (
                    terminal_observation is None
                    or terminal_observation.task_name
                    != "baldr-recommendation-calibration-learning-daily"
                    or terminal_observation.task_path != "\\"
                    or terminal_observation.state not in {"Running", "Ready"}
                    or _parse_aware_datetime(
                        terminal_observation.last_run_time_utc
                    )
                    != proof.last_run_time_utc
                ):
                    return finish(
                        status="blocked",
                        reason="recommendation_pipeline_task_last_run_changed",
                    )
                (
                    terminal_candidate,
                    snapshot,
                    terminal_error,
                    terminal_audit,
                ) = _try_accept_published_current_projection(
                    paths=paths,
                    decision_date=decision_date,
                    initial_snapshot=None,
                    initial_observation=terminal_observation,
                    task_state_reader=task_state_reader,
                    now_provider=now_provider,
                )
                if (
                    not terminal_candidate
                    or snapshot is None
                    or snapshot.pipeline_run_id != proof.run_id
                ):
                    return finish(
                        status="blocked",
                        reason=(
                            "recommendation_pipeline_current_snapshot_unverified:"
                            f"{terminal_error or terminal_audit.get('reason') or 'run_id_mismatch'}"
                        ),
                    )
                return finish(status="ready", reason=None, snapshot=snapshot)

            stale_error = _validate_stale_pipeline_projection(
                projection,
                output_root=paths.snapshot_output_root,
                decision_date=decision_date,
                current_run_proof=proof,
            )
            if stale_error is not None:
                return finish(status="blocked", reason=stale_error)

        observation = task_state_reader()
        if (
            observation is None
            or observation.task_name != "baldr-recommendation-calibration-learning-daily"
            or observation.task_path != "\\"
            or observation.state != "Running"
        ):
            return finish(
                status="upstream_stopped",
                reason="recommendation_pipeline_stopped_without_current_projection",
            )
        observation_last_run = _parse_aware_datetime(observation.last_run_time_utc)
        if observation_last_run != proof.last_run_time_utc:
            return finish(
                status="blocked",
                reason="recommendation_pipeline_task_last_run_changed",
            )
        current_proof, proof_error = _current_upstream_run_proof(
            output_root=paths.snapshot_output_root,
            decision_date=decision_date,
            task_state_reader=lambda: observation,
            now=now_provider(),
            recheck_task_state=False,
        )
        if current_proof is None or current_proof.run_id != proof.run_id:
            return finish(
                status="blocked",
                reason=(
                    "recommendation_pipeline_running_proof_changed:"
                    f"{proof_error or 'run_id_mismatch'}"
                ),
            )

        current_monotonic = monotonic()
        if current_monotonic >= deadline:
            return finish(
                status="timed_out",
                reason="recommendation_pipeline_wait_timeout",
            )

        if current_monotonic - last_heartbeat >= _UPSTREAM_WAIT_HEARTBEAT_SECONDS:
            heartbeat_error = _write_wait_heartbeat_safely(
                heartbeat_writer,
                {
                    "schema_version": "banktaiwan-upstream-projection-wait.v1",
                    "task": TASK_NAME,
                    "decision_date": decision_date.isoformat(),
                    "heartbeat_at": now_provider().isoformat(timespec="seconds"),
                    "enabled": True,
                    "status": "waiting",
                    "upstream_task": "baldr-recommendation-calibration-learning-daily",
                    "upstream_run_id": proof.run_id,
                    "upstream_last_run_time_utc": proof.last_run_time_utc.isoformat(),
                    "status_mtime_utc": current_proof.status_mtime_utc.isoformat(),
                    "wait_limit_seconds": wait_seconds,
                    "waited_seconds": round(current_monotonic - started_monotonic, 3),
                    "poll_count": poll_count,
                    "last_projection_run_id": last_projection_run_id,
                    "last_projection_decision_date": last_projection_date,
                    "heartbeat_path": str(heartbeat_path),
                },
            )
            if heartbeat_error is not None:
                return finish(
                    status="blocked",
                    reason="recommendation_pipeline_wait_heartbeat_write_failed",
                )
            last_heartbeat = monotonic()

        sleep(min(_UPSTREAM_TASK_STATE_POLL_SECONDS, max(0.0, deadline - monotonic())))


def _maybe_wait_for_current_upstream_projection(
    *,
    paths: OperationalPaths,
    decision_date: date,
    initial_snapshot: SnapshotSummary | None,
    initial_reason: str | None,
    wait_seconds: int,
    attempt_deadline: float | None,
    task_state_reader: Callable[[], ScheduledTaskObservation | None],
    monotonic: Callable[[], float],
    sleep: Callable[[float], None],
    now_provider: Callable[[], datetime],
) -> tuple[SnapshotSummary | None, str | None, dict[str, Any]]:
    audit: dict[str, Any] = {
        "enabled": wait_seconds > 0,
        "status": "not_requested" if wait_seconds > 0 else "disabled",
        "wait_limit_seconds": wait_seconds,
        "waited_seconds": 0.0,
        "poll_count": 0,
    }
    if wait_seconds <= 0:
        return initial_snapshot, initial_reason, audit
    if decision_date != now_provider().astimezone(TAIPEI).date():
        audit["status"] = "not_current_taipei_day"
        return initial_snapshot, initial_reason, audit

    first_observation = task_state_reader()
    if first_observation is None:
        audit["status"] = "upstream_not_running"
        return initial_snapshot, initial_reason, audit
    terminal_candidate, terminal_snapshot, terminal_error, terminal_audit = (
        _try_accept_published_current_projection(
            paths=paths,
            decision_date=decision_date,
            initial_snapshot=initial_snapshot,
            initial_observation=first_observation,
            task_state_reader=task_state_reader,
            now_provider=now_provider,
        )
    )
    if terminal_candidate:
        audit.update(terminal_audit)
        if terminal_snapshot is not None:
            return terminal_snapshot, None, audit
        audit["status"] = "current_terminal_proof_invalid"
        audit["reason"] = terminal_error
        return (
            None,
            f"recommendation_pipeline_current_terminal_proof_invalid:{terminal_error}",
            audit,
        )
    if first_observation.state != "Running":
        if terminal_audit.get("status") == "stale_projection_for_task":
            reason = "recommendation_pipeline_stale_projection_after_task_completion"
            audit.update(
                {
                    "status": "current_terminal_proof_invalid",
                    "reason": reason,
                }
            )
            return None, reason, audit
        if (
            initial_snapshot is not None
            and terminal_audit.get("status") == "projection_unavailable"
            and initial_snapshot.pipeline_status_path
            == _pipeline_paths(paths.snapshot_output_root)[2]
        ):
            reason = (
                "recommendation_pipeline_current_projection_unreadable:"
                f"{terminal_audit.get('reason', 'missing_or_invalid')}"
            )
            audit.update(
                {
                    "status": "current_terminal_proof_invalid",
                    "reason": reason,
                }
            )
            return None, reason, audit
        audit["status"] = "upstream_not_running"
        return initial_snapshot, initial_reason, audit
    proof, proof_error = _current_upstream_run_proof(
        output_root=paths.snapshot_output_root,
        decision_date=decision_date,
        task_state_reader=task_state_reader,
        now=now_provider(),
    )
    if proof is None:
        audit.update(
            {
                "status": "running_identity_unverified",
                "reason": proof_error,
            }
        )
        return None, f"recommendation_pipeline_running_proof_invalid:{proof_error}", audit
    if (
        initial_snapshot is not None
        and initial_snapshot.pipeline_run_id == proof.run_id
    ):
        projection, projection_error = _read_pipeline_projection(
            output_root=paths.snapshot_output_root
        )
        if projection is None:
            audit.update(
                {
                    "status": "current_run_projection_unreadable",
                    "upstream_run_id": proof.run_id,
                    "reason": projection_error,
                }
            )
            return None, "recommendation_pipeline_current_projection_unreadable", audit
        identity_error = _validate_current_pipeline_projection(
            projection,
            output_root=paths.snapshot_output_root,
            decision_date=decision_date,
            run_id=proof.run_id,
        )
        receipt_error = (
            _verify_current_pipeline_terminal_receipt(
                output_root=paths.snapshot_output_root,
                projection=projection,
                run_id=proof.run_id,
            )
            if identity_error is None
            else None
        )
        if identity_error is not None or receipt_error is not None:
            if identity_error is not None:
                current_run_error = identity_error
            else:
                assert receipt_error is not None
                current_run_error = receipt_error
            audit.update(
                {
                    "status": "current_run_terminal_proof_invalid",
                    "upstream_run_id": proof.run_id,
                    "reason": current_run_error,
                }
            )
            return None, f"recommendation_pipeline_current_terminal_proof_invalid:{current_run_error}", audit
        audit.update(
            {
                "status": "current_run_already_available",
                "upstream_run_id": proof.run_id,
            }
        )
        return initial_snapshot, None, audit
    if attempt_deadline is None:
        audit.update(
            {
                "status": "blocked",
                "upstream_run_id": proof.run_id,
                "reason": "bank_attempt_deadline_unavailable",
            }
        )
        return None, "recommendation_pipeline_wait_attempt_deadline_unavailable", audit

    heartbeat: _WaitHeartbeatLog | None = None
    try:
        heartbeat = _WaitHeartbeatLog(paths, decision_date)
        snapshot, wait_reason, wait_audit = _wait_for_exact_upstream_projection(
            paths=paths,
            decision_date=decision_date,
            proof=proof,
            wait_seconds=wait_seconds,
            attempt_deadline=attempt_deadline,
            task_state_reader=task_state_reader,
            monotonic=monotonic,
            sleep=sleep,
            now_provider=now_provider,
            heartbeat_writer=heartbeat.write,
            heartbeat_path=heartbeat.path,
        )
        return snapshot, wait_reason, wait_audit
    except OSError as exc:
        audit.update(
            {
                "status": "blocked",
                "upstream_run_id": proof.run_id,
                "reason": f"wait_heartbeat_open_failed:{type(exc).__name__}",
            }
        )
        return None, "recommendation_pipeline_wait_heartbeat_open_failed", audit
    finally:
        if heartbeat is not None:
            heartbeat.close()


def _write_json(
    path: Path,
    payload: Mapping[str, Any],
    *,
    max_bytes: int | None = None,
) -> str:
    encoded = _encode_json_payload(payload)
    if max_bytes is not None and len(encoded) > max_bytes:
        raise OperationalLaneError("JSON payload exceeds its configured write bound")
    return _write_json_bytes(path, encoded)


def _encode_json_payload(payload: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")


def _write_json_bytes(path: Path, encoded: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(encoded)
    os.replace(temporary, path)
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _has_reparse_attribute(info: os.stat_result) -> bool:
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    file_attributes = getattr(info, "st_file_attributes", 0)
    return stat.S_ISLNK(info.st_mode) or bool(file_attributes & reparse_flag)


def _prepare_child_stdout_artifact_target(
    *,
    paths: OperationalPaths,
    run_id: str,
) -> tuple[Path | None, str | None]:
    """確認 child stdout create-only 目的路徑在 operation root 內且無碰撞。"""

    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}-attempt-\d{3}-[0-9a-f]{12}", run_id):
        return None, "child_stdout_artifact_run_id_invalid"
    try:
        root = paths.operational_root.resolve(strict=True)
        artifact_root = root / "child_cli_artifacts"
        artifact_root.mkdir(exist_ok=True)
        root_info = artifact_root.lstat()
        if not stat.S_ISDIR(root_info.st_mode) or _has_reparse_attribute(root_info):
            return None, "child_stdout_artifact_root_unsafe"
        resolved_root = artifact_root.resolve(strict=True)
        resolved_root.relative_to(root)
        target = artifact_root / f"{run_id}.stdout.bin"
        try:
            target.lstat()
        except FileNotFoundError:
            return target, None
        return None, "child_stdout_artifact_path_already_exists"
    except (OSError, RuntimeError, ValueError):
        return None, "child_stdout_artifact_root_unavailable"


def _read_child_stdout_artifact(path: Path, *, root: Path) -> bytes:
    from app_module.recommendation.queries import _read_regular_file_no_follow

    return _read_regular_file_no_follow(
        path,
        root,
        max_bytes=_MAX_CHILD_CLI_STDOUT_ARTIFACT_BYTES,
    )


def _publish_child_stdout_artifact(
    *,
    paths: OperationalPaths,
    target: Path,
    stdout_bytes: bytes,
) -> dict[str, Any]:
    """原樣 create-only 發布 child stdout，並以 no-follow bytes 回讀驗證。"""

    if len(stdout_bytes) > _MAX_CHILD_CLI_STDOUT_ARTIFACT_BYTES:
        return {
            "status": "blocked",
            "reason": "child_stdout_artifact_size_limit_exceeded",
            "path": str(target),
            "observed_size_bytes": len(stdout_bytes),
            "size_limit_bytes": _MAX_CHILD_CLI_STDOUT_ARTIFACT_BYTES,
        }
    temp_path = target.with_name(f".{target.name}.{secrets.token_hex(16)}.tmp")
    temp_created = False
    try:
        root = paths.operational_root.resolve(strict=True)
        target.parent.resolve(strict=True).relative_to(root)
        descriptor = os.open(
            str(temp_path),
            os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0),
            0o600,
        )
        temp_created = True
        try:
            view = memoryview(stdout_bytes)
            while view:
                written = os.write(descriptor, view[:1024 * 1024])
                if written <= 0:
                    raise OSError("child stdout artifact write made no progress")
                view = view[written:]
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.link(temp_path, target)
        temp_path.unlink()
        temp_created = False

        before = target.lstat()
        if not stat.S_ISREG(before.st_mode) or _has_reparse_attribute(before):
            raise OSError("child stdout artifact is not a regular file")
        raw = _read_child_stdout_artifact(target, root=root)
        after = target.lstat()
        if (
            not stat.S_ISREG(after.st_mode)
            or _has_reparse_attribute(after)
            or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
            or raw != stdout_bytes
        ):
            raise OSError("child stdout artifact changed during readback")
        digest = "sha256:" + hashlib.sha256(raw).hexdigest()
        return {
            "status": "verified",
            "publication": "created",
            "path": str(target),
            "size_bytes": len(raw),
            "sha256": digest,
        }
    except FileExistsError:
        try:
            root = paths.operational_root.resolve(strict=True)
            raw = _read_child_stdout_artifact(target, root=root)
            if raw != stdout_bytes:
                return {
                    "status": "blocked",
                    "reason": "child_stdout_artifact_collision_bytes_mismatch",
                    "path": str(target),
                    "observed_size_bytes": len(raw),
                }
            return {
                "status": "verified",
                "publication": "reused_exact_bytes",
                "path": str(target),
                "size_bytes": len(raw),
                "sha256": "sha256:" + hashlib.sha256(raw).hexdigest(),
            }
        except (OSError, RuntimeError, ValueError):
            return {
                "status": "blocked",
                "reason": "child_stdout_artifact_collision_unreadable",
                "path": str(target),
                "observed_size_bytes": len(stdout_bytes),
            }
    except (OSError, RuntimeError, ValueError):
        return {
            "status": "blocked",
            "reason": "child_stdout_artifact_publish_or_readback_failed",
            "path": str(target),
            "observed_size_bytes": len(stdout_bytes),
        }
    finally:
        if temp_created:
            try:
                temp_path.unlink()
            except OSError:
                pass


def _hash_payload(payload: Any) -> str:
    return "sha256:" + hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _hash_file(path: Path) -> str | None:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        return None
    return "sha256:" + digest.hexdigest()


def _tail(value: object, limit: int = 8000) -> str:
    text = str(value or "")
    return text[-limit:] if len(text) > limit else text


def _subprocess_text(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value or "")


def _default_data_root() -> Path:
    return Path(os.environ.get("DATA_ROOT", str(DEFAULT_DATA_ROOT))).expanduser().resolve()


def resolve_operational_paths(
    *,
    data_root: str | Path | None = None,
    lane_output_root: str | Path | None = None,
    snapshot_output_root: str | Path | None = None,
    source_artifact_root: str | Path | None = None,
    source_db: str | Path | None = None,
) -> OperationalPaths:
    """解析隔離 lane，並拒絕與 formal／legacy root 重疊。"""

    formal_root = Path(data_root or _default_data_root()).expanduser().resolve()
    raw_lane = lane_output_root or os.environ.get(
        "BANKTAIWAN_RECOMMENDATION_LEARNING_OUTPUT_ROOT"
    )
    lane_root = Path(raw_lane).expanduser().resolve() if raw_lane else (
        formal_root.parent / DEFAULT_LANE_DIRNAME
    ).resolve()
    try:
        lane_root = resolve_recommendation_learning_output_root(
            data_root=formal_root,
            explicit_output_root=lane_root,
        )
    except ValueError as exc:
        raise OperationalLaneError(str(exc)) from exc

    raw_source = source_artifact_root or os.environ.get(
        "BANKTAIWAN_SOURCE_ARTIFACT_ROOT"
    )
    if raw_source:
        source_root = Path(raw_source).expanduser().resolve()
    else:
        # This is the resolver's canonical sibling legacy root, not a
        # hard-coded machine path.  The caller still requires it to exist.
        source_root = (
            formal_root.parent / DEFAULT_SOURCE_DIRNAME
        ).resolve()
    if (
        source_root == lane_root
        or source_root in lane_root.parents
        or lane_root in source_root.parents
    ):
        raise OperationalLaneError(
            "BankTaiwan source artifact root and lane output root must be disjoint; "
            f"source={source_root}; lane={lane_root}"
        )

    snapshot_root = Path(
        snapshot_output_root
        or os.environ.get("BANKTAIWAN_SNAPSHOT_OUTPUT_ROOT")
        or source_root
    ).expanduser().resolve()
    database = Path(
        source_db
        or os.environ.get("BANKTAIWAN_SOURCE_DB")
        or os.environ.get("DB_PATH")
        or formal_root / "sqlite" / "twstock.db"
    ).expanduser().resolve()
    learning_root = lane_root / "recommendation_learning"
    operational_root = lane_root / "scheduled" / "recommendation_learning_banktaiwan"
    return OperationalPaths(
        data_root=formal_root,
        lane_output_root=lane_root,
        lane_learning_root=learning_root,
        operational_root=operational_root,
        latest_status_path=operational_root / "latest_status.json",
        runs_root=operational_root / "runs",
        logs_root=operational_root / "logs",
        lock_path=operational_root / "run.lock",
        snapshot_output_root=snapshot_root,
        source_artifact_root=source_root,
        source_db=database,
    )


def load_same_day_snapshot(
    *,
    output_root: str | Path,
    decision_date: date,
) -> tuple[SnapshotSummary | None, str | None]:
    """以兩個 latest-status 指標精確讀取同次 canonical snapshot。"""

    root = Path(output_root).expanduser().resolve()
    status_path = root / "scheduled" / "recommendation_snapshot" / "latest_status.json"
    status_payload, status_read_error = _read_bounded_snapshot_status(
        status_path,
        root=root,
    )
    if status_payload is None:
        suffix = status_read_error or "missing_or_invalid"
        return None, f"recommendation_snapshot_status_{suffix}"
    acceptable_statuses = {"passed", "passed_with_warnings", "warning", "degraded"}
    if status_payload.get("task") != "baldr-recommendation-snapshot-daily":
        return None, "recommendation_snapshot_status_task_mismatch"
    if type(status_payload.get("status")) is not str or status_payload.get(
        "status"
    ) not in acceptable_statuses:
        return None, "recommendation_snapshot_status_not_eligible"
    expected_date = decision_date.isoformat()
    if status_payload.get("decision_date") != expected_date:
        return None, "recommendation_snapshot_status_decision_date_mismatch"
    if not _same_resolved_path(status_payload.get("output_root"), root):
        return None, "recommendation_snapshot_status_output_root_mismatch"
    result_id = status_payload.get("result_id")
    if type(result_id) is not str or not result_id or result_id.strip() != result_id:
        return None, "recommendation_snapshot_status_result_id_missing_or_invalid"
    status_cohort_value = status_payload.get("snapshot_cohort")
    if not isinstance(status_cohort_value, Mapping):
        return None, "recommendation_snapshot_status_cohort_missing_or_invalid"
    status_cohort = dict(status_cohort_value)
    cohort_hash = status_cohort.get("cohort_hash")
    if not isinstance(cohort_hash, str) or not _is_sha256_text(cohort_hash):
        return None, "recommendation_snapshot_status_cohort_hash_missing_or_invalid"

    pipeline_root = (
        root
        / "scheduled"
        / "recommendation_calibration_learning"
    )
    projection_path = pipeline_root / "latest_snapshot_source_status.json"
    # 新版 producer 以 bounded projection 交接；舊版 fixture／歷史輸出
    # 沒有 projection 時仍按原契約讀 full status，且保留 8 MiB 上限。
    use_projection = os.path.lexists(projection_path)
    pipeline_status_path = (
        projection_path if use_projection else pipeline_root / "latest_status.json"
    )
    pipeline_status_payload, pipeline_status_read_error = (
        _read_bounded_snapshot_status(pipeline_status_path, root=root)
    )
    if pipeline_status_payload is None:
        suffix = pipeline_status_read_error or "missing_or_invalid"
        return None, f"recommendation_pipeline_status_{suffix}"
    if use_projection and pipeline_status_payload.get("schema_version") != (
        "daily-recommendation-snapshot-source.v1"
    ):
        return None, "recommendation_pipeline_projection_schema_mismatch"
    if pipeline_status_payload.get("task") != "baldr-recommendation-calibration-learning-daily":
        return None, "recommendation_pipeline_status_task_mismatch"
    if pipeline_status_payload.get("decision_date") != expected_date:
        return None, "recommendation_pipeline_status_decision_date_mismatch"
    if not _same_resolved_path(pipeline_status_payload.get("output_root"), root):
        return None, "recommendation_pipeline_status_output_root_mismatch"
    pipeline_run_id = pipeline_status_payload.get("run_id")
    if (
        type(pipeline_run_id) is not str
        or not pipeline_run_id
        or pipeline_run_id in {".", ".."}
        or Path(pipeline_run_id).name != pipeline_run_id
        or any(separator in pipeline_run_id for separator in ("/", "\\"))
    ):
        return None, "recommendation_pipeline_run_id_missing_or_invalid"
    steps_value = pipeline_status_payload.get("steps")
    steps = steps_value if isinstance(steps_value, Mapping) else {}
    snapshot_step_value = steps.get("recommendation_snapshot")
    if not isinstance(snapshot_step_value, Mapping):
        return None, "recommendation_pipeline_snapshot_step_missing_or_invalid"
    snapshot_step = snapshot_step_value
    if (
        type(snapshot_step.get("status")) is not str
        or snapshot_step.get("status") not in acceptable_statuses
        or type(snapshot_step.get("returncode")) is not int
        or snapshot_step.get("returncode") != 0
        or snapshot_step.get("child_receipt_error") is not None
    ):
        return None, "recommendation_pipeline_snapshot_step_not_successful"
    invocation_payload_value = snapshot_step.get("child_status")
    if not isinstance(invocation_payload_value, Mapping):
        return None, "recommendation_pipeline_snapshot_child_status_missing_or_invalid"
    invocation_payload = dict(invocation_payload_value)
    if (
        type(invocation_payload.get("status")) is not str
        or invocation_payload.get("status") not in acceptable_statuses
        or invocation_payload.get("decision_date") != expected_date
        or not _same_resolved_path(invocation_payload.get("output_root"), root)
        or invocation_payload.get("result_id") != result_id
        or invocation_payload.get("snapshot_cohort") != status_cohort
    ):
        return None, "recommendation_pipeline_snapshot_identity_mismatch"

    invocation_output_path_value = snapshot_step.get("child_stdout_artifact_path")
    invocation_output_sha256 = snapshot_step.get("child_stdout_sha256")
    invocation_output_size = snapshot_step.get("child_stdout_artifact_size")
    if (
        type(invocation_output_path_value) is not str
        or not invocation_output_path_value.strip()
        or not isinstance(invocation_output_sha256, str)
        or not _is_sha256_text(invocation_output_sha256)
        or type(invocation_output_size) is not int
        or invocation_output_size <= 0
    ):
        return None, "recommendation_pipeline_snapshot_stdout_binding_missing_or_invalid"
    invocation_output_path = Path(invocation_output_path_value).expanduser()
    expected_invocation_output_path = (
        root
        / "scheduled"
        / "recommendation_calibration_learning"
        / "runs"
        / pipeline_run_id
        / "recommendation_snapshot.stdout.bin"
    )
    if not _same_resolved_path(invocation_output_path_value, expected_invocation_output_path):
        return None, "recommendation_pipeline_snapshot_stdout_path_mismatch"

    try:
        # 重用 learning CLI 的嚴格同次綁定，讓原始 stdout、canonical index、
        # artifact bytes、typed execution、cohort 與日期沿用同一套 fail-closed 契約。
        from scripts.scheduled.run_daily_recommendation_learning import (
            _resolve_same_run_snapshot_input,
        )

        symbols, canonical_cohort, binding = _resolve_same_run_snapshot_input(
            output_root=root,
            decision_date=decision_date,
            result_id=result_id,
            expected_cohort_hash=cohort_hash,
            expected_invocation_output_sha256=invocation_output_sha256,
            invocation_output_path=str(invocation_output_path),
        )
    except (OSError, RuntimeError, TypeError, ValueError, KeyError) as exc:
        return None, f"recommendation_snapshot_canonical_readback_failed:{type(exc).__name__}:{exc}"

    if (
        canonical_cohort != status_cohort
        or binding.get("result_id") != result_id
        or binding.get("cohort_hash") != cohort_hash
        or binding.get("invocation_output_size") != invocation_output_size
        or binding.get("invocation_output_sha256") != invocation_output_sha256
    ):
        return None, "recommendation_snapshot_status_canonical_binding_mismatch"
    raw_artifact_sha256 = binding.get("raw_artifact_sha256")
    payload_hash = binding.get("payload_hash")
    schema_version = binding.get("schema_version")
    schema_revision = binding.get("schema_revision")
    integrity_basis = binding.get("integrity_basis")
    data_as_of_date = binding.get("data_as_of_date")
    decision_at = binding.get("decision_at")
    available_at = binding.get("available_at")
    if (
        not isinstance(raw_artifact_sha256, str)
        or not _is_sha256_text(raw_artifact_sha256)
        or not isinstance(payload_hash, str)
        or not _is_sha256_text(payload_hash)
        or type(schema_version) is not str
        or type(schema_revision) is not int
        or integrity_basis != "canonical_payload_and_index_verified"
        or type(data_as_of_date) is not str
        or type(decision_at) is not str
        or (available_at is not None and type(available_at) is not str)
    ):
        return None, "recommendation_snapshot_canonical_binding_incomplete"
    try:
        actual_size = invocation_output_path.stat().st_size
    except OSError:
        return None, "recommendation_pipeline_snapshot_stdout_unreadable"
    if actual_size != invocation_output_size:
        return None, "recommendation_pipeline_snapshot_stdout_size_mismatch"

    return (
        SnapshotSummary(
            path=invocation_output_path.resolve(),
            payload=invocation_payload,
            symbols=symbols,
            cohort=canonical_cohort,
            file_sha256=invocation_output_sha256,
            status_path=status_path.resolve(),
            status_payload=status_payload,
            pipeline_run_id=pipeline_run_id,
            pipeline_status_path=pipeline_status_path.resolve(),
            pipeline_status_payload=pipeline_status_payload,
            result_id=result_id,
            payload_hash=payload_hash,
            canonical_artifact_sha256=raw_artifact_sha256,
            schema_version=schema_version,
            schema_revision=schema_revision,
            integrity_basis=integrity_basis,
            decision_date=expected_date,
            data_as_of_date=data_as_of_date,
            decision_at=decision_at,
            available_at=available_at,
            cohort_hash=cohort_hash,
            invocation_output_path=invocation_output_path.resolve(),
            invocation_output_sha256=invocation_output_sha256,
            invocation_output_size=invocation_output_size,
        ),
        None,
    )


def _is_sha256_text(value: object) -> bool:
    return (
        type(value) is str
        and len(value) == 71
        and value.startswith("sha256:")
        and all(char in "0123456789abcdef" for char in value[7:])
    )


def _same_resolved_path(value: object, expected: Path) -> bool:
    if type(value) is not str or not value.strip():
        return False
    try:
        return Path(value).expanduser().resolve() == expected.expanduser().resolve()
    except (OSError, RuntimeError, TypeError, ValueError):
        return False


def _file_marker(path: Path, *, hash_small_file: bool = True) -> dict[str, Any]:
    marker: dict[str, Any] = {"path": str(path.resolve()), "exists": path.is_file()}
    if not path.is_file():
        return marker
    try:
        stat = path.stat()
    except OSError:
        marker["stat_readable"] = False
        return marker
    marker.update(
        {
            "stat_readable": True,
            "size": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
        }
    )
    if hash_small_file and stat.st_size <= 10 * 1024 * 1024:
        marker["sha256"] = _hash_file(path)
    return marker


def _source_markers(paths: OperationalPaths) -> list[dict[str, Any]]:
    candidates = [
        paths.source_artifact_root / "scheduled" / "official_market_events" / "latest_status.json",
        paths.source_artifact_root / "release_v4" / "official_market_events" / "prospective_latest_manifest.json",
        paths.source_artifact_root / "release_v4" / "official_market_events" / "latest_manifest.json",
        paths.source_artifact_root / "release_v4" / "corporate_action_adjustments" / "latest_manifest.json",
        paths.data_root / "output" / "scheduled" / "data_update_quick" / "latest_status.json",
    ]
    technical_root = paths.data_root / "output" / "scheduled" / "technical_indicator_publication"
    if technical_root.is_dir():
        candidates.extend(sorted(technical_root.glob("**/receipt.json"))[-2:])
    return [_file_marker(path) for path in candidates]


_VOLATILE_CALENDAR_EVIDENCE_KEYS = frozenset(
    {"validated_at", "validation_at", "observed_at", "checked_at"}
)


def _stable_calendar_evidence_value(value: object) -> object:
    """保留官方日曆證據身份，略過每次重驗才變動的觀測時鐘。"""

    if isinstance(value, Mapping):
        return {
            str(key): _stable_calendar_evidence_value(item)
            for key, item in value.items()
            if str(key) not in _VOLATILE_CALENDAR_EVIDENCE_KEYS
        }
    if isinstance(value, (list, tuple)):
        return [_stable_calendar_evidence_value(item) for item in value]
    if value is None or type(value) in {str, int, bool}:
        return value
    return {"unsupported_evidence_type": type(value).__name__}


def _calendar_input_identity(
    calendar: object,
    *,
    source_db: Path,
    decision_date: date,
    is_trading_day: bool | None,
    reason: str,
) -> dict[str, Any]:
    """擷取本次官方判定使用的穩定來源身份，不觸發新的網路查詢。"""

    identity: dict[str, Any] = {
        "decision_date": decision_date.isoformat(),
        "is_official_trading_day": is_trading_day,
        "reason": reason,
    }
    if reason == "weekend_closed":
        identity["evidence"] = {"mode": "calendar_weekend_convention"}
        return identity

    schedule_evidence = getattr(calendar, "_schedule_evidence", None)
    if isinstance(schedule_evidence, Mapping):
        annual = schedule_evidence.get(decision_date.year)
        if isinstance(annual, Mapping):
            identity["annual_schedule_evidence"] = _stable_calendar_evidence_value(
                annual
            )

    temporary_cache = getattr(calendar, "_temporary_closure_cache", None)
    if isinstance(temporary_cache, Mapping):
        temporary = temporary_cache.get(decision_date)
        temporary_evidence = getattr(temporary, "evidence", None)
        if isinstance(temporary_evidence, Mapping):
            identity["temporary_closure_evidence"] = (
                _stable_calendar_evidence_value(temporary_evidence)
            )
    failure_reasons = getattr(calendar, "_schedule_failure_reason", None)
    if isinstance(failure_reasons, Mapping):
        failure = failure_reasons.get(decision_date.year)
        if isinstance(failure, str):
            identity["annual_schedule_failure"] = failure
    temporary_failures = getattr(calendar, "_temporary_closure_failure_reason", None)
    if isinstance(temporary_failures, Mapping):
        failure = temporary_failures.get(decision_date)
        if isinstance(failure, str):
            identity["temporary_closure_failure"] = failure

    cache_candidates = getattr(calendar, "_cache_candidates", None)
    if callable(cache_candidates):
        try:
            candidates = tuple(cache_candidates(decision_date.year))
        except (OSError, RuntimeError, TypeError, ValueError):
            candidates = ()
            identity["annual_cache_candidate_scan"] = "failed"
        identity["annual_cache_candidate_markers"] = [
            _calendar_path_marker(Path(candidate)) for candidate in candidates
        ]
    temporary_root_value = getattr(calendar, "temporary_closure_path", None)
    if isinstance(temporary_root_value, (str, Path)):
        temporary_root = Path(temporary_root_value)
        try:
            if temporary_root.is_dir():
                temporary_candidates = tuple(
                    sorted(
                        temporary_root.glob(
                            f"twse_temporary_closure_{decision_date:%Y%m%d}_*.json"
                        )
                    )
                )
            elif temporary_root.suffix.casefold() == ".json":
                temporary_candidates = (temporary_root,)
            else:
                temporary_candidates = ()
        except OSError:
            temporary_candidates = ()
            identity["temporary_cache_candidate_scan"] = "failed"
        identity["temporary_cache_candidate_markers"] = [
            _calendar_path_marker(candidate) for candidate in temporary_candidates
        ]

    if reason == "twstock_db_market_indices_evidence":
        identity["market_indices_database_marker"] = _file_marker(
            source_db,
            hash_small_file=False,
        )
    if not any(
        key in identity
        for key in (
            "annual_schedule_evidence",
            "temporary_closure_evidence",
            "annual_schedule_failure",
            "temporary_closure_failure",
            "market_indices_database_marker",
        )
    ):
        identity["evidence"] = {"mode": "reason_only", "reason": reason}
    return identity


def _calendar_path_marker(path: Path) -> dict[str, Any]:
    """記錄日曆候選檔本身身份，不跟隨連結讀取目標內容。"""

    try:
        info = path.lstat()
    except FileNotFoundError:
        return {"path": str(path), "exists": False}
    except OSError:
        return {"path": str(path), "stat_readable": False}
    return {
        "path": str(path),
        "exists": True,
        "is_symlink": path.is_symlink(),
        "is_regular_file": stat.S_ISREG(info.st_mode),
        "size": info.st_size,
        "mtime_ns": info.st_mtime_ns,
        "device": info.st_dev,
        "inode": info.st_ino,
    }


def build_input_fingerprint(
    *,
    paths: OperationalPaths,
    decision_date: date,
    scenario: RecommendationCostScenario,
    snapshot: SnapshotSummary | None,
    history_start_date: str,
    max_decision_dates: int,
    calendar_identity: Mapping[str, Any],
) -> str:
    """以 immutable input identity 判斷同日重跑是否可安全 reuse。"""

    return _hash_payload(
        {
            "schema_version": "banktaiwan-operational-input-fingerprint.v3",
            "decision_date": decision_date.isoformat(),
            "decision_timezone": "Asia/Taipei",
            "replay_scope": {
                "history_start_date": history_start_date,
                "max_decision_dates": max_decision_dates,
                "replay_selection_policy": "latest_eligible_dates",
                "fixed_round_trip_cost_bp": 50,
            },
            "official_calendar": dict(calendar_identity),
            "snapshot": (
                {
                    "result_id": snapshot.result_id,
                    "path": str(snapshot.path),
                    "canonical_artifact_sha256": snapshot.canonical_artifact_sha256,
                    "payload_hash": snapshot.payload_hash,
                    "schema_version": snapshot.schema_version,
                    "schema_revision": snapshot.schema_revision,
                    "integrity_basis": snapshot.integrity_basis,
                    "decision_date": snapshot.decision_date,
                    "data_as_of_date": snapshot.data_as_of_date,
                    "decision_at": snapshot.decision_at,
                    "available_at": snapshot.available_at,
                    "symbols": list(snapshot.symbols),
                    "cohort": dict(snapshot.cohort),
                    "cohort_hash": snapshot.cohort_hash,
                    "pipeline_run_id": snapshot.pipeline_run_id,
                    "pipeline_status_path": str(snapshot.pipeline_status_path),
                    "invocation_output_path": str(snapshot.invocation_output_path),
                    "invocation_output_sha256": snapshot.invocation_output_sha256,
                    "invocation_output_size": snapshot.invocation_output_size,
                }
                if snapshot is not None
                else None
            ),
            "source_artifact_root": str(paths.source_artifact_root),
            "source_markers": _source_markers(paths),
            "source_db": _file_marker(paths.source_db, hash_small_file=False),
            "cost_scenario": scenario.metadata(),
        }
    )


ProcessState = Literal["running", "dead", "unknown"]


def _windows_process_state(pid: int) -> ProcessState:
    """以 Windows query-only API 判斷 PID；不送 signal、不終止 process。"""

    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel32.GetExitCodeProcess.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        process_query_limited_information = 0x1000
        still_active = 259
        handle = kernel32.OpenProcess(
            process_query_limited_information,
            False,
            wintypes.DWORD(pid),
        )
        if not handle:
            error_code = ctypes.get_last_error()
            # OpenProcess uses ERROR_INVALID_PARAMETER for a valid PID that
            # no longer exists on this host.  The explicit not-found codes
            # are safe stale-lock evidence; AccessDenied/protected-process
            # and every other query error remain unknown.
            if error_code in {2, 87, 1168}:
                return "dead"
            return "unknown"
        exit_code = wintypes.DWORD()
        try:
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return "unknown"
        finally:
            kernel32.CloseHandle(handle)
        return "running" if exit_code.value == still_active else "dead"
    except (AttributeError, OSError, TypeError, ValueError):
        return "unknown"


def _process_state(pid: object) -> ProcessState:
    """回傳 running/dead/unknown；不確定時永不回收 lock。"""

    if (
        isinstance(pid, bool)
        or not isinstance(pid, int)
        or pid <= 0
        or pid > 0xFFFFFFFF
    ):
        return "unknown"
    if os.name == "nt":
        return _windows_process_state(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return "dead"
    except PermissionError:
        return "unknown"
    except OSError:
        return "unknown"
    return "running"


def _pid_running(pid: object) -> bool:
    """相容性 helper；只有明確 running 才回傳 True。"""

    return _process_state(pid) == "running"


class OperationalRunLock:
    """跨 process 的 create-only lock；crash 後只回收確認已死亡的 PID。"""

    def __init__(self, path: Path) -> None:
        self.path = path.resolve()
        self.token = secrets.token_hex(16)
        self.acquired = False

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        metadata = {
            "schema_version": "banktaiwan-operational-lock.v1",
            "pid": os.getpid(),
            "token": self.token,
            "started_at": datetime.now(TAIPEI).isoformat(timespec="seconds"),
        }
        for _ in range(2):
            try:
                descriptor = os.open(
                    str(self.path),
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                )
                try:
                    os.write(
                        descriptor,
                        (json.dumps(metadata, ensure_ascii=False) + "\n").encode("utf-8"),
                    )
                finally:
                    os.close(descriptor)
                self.acquired = True
                return
            except FileExistsError as exc:
                existing = _read_json(self.path)
                process_state = (
                    _process_state(existing.get("pid"))
                    if isinstance(existing, Mapping)
                    else "unknown"
                )
                if existing is None or process_state in {"running", "unknown"}:
                    raise OperationalOverlapError(
                        f"operational lock is held: {self.path}"
                    ) from exc
                try:
                    self.path.unlink()
                except OSError as unlink_error:
                    raise OperationalOverlapError(
                        f"stale operational lock cannot be reclaimed: {self.path}"
                    ) from unlink_error
        raise OperationalOverlapError(f"operational lock is held: {self.path}")

    def release(self) -> None:
        if not self.acquired:
            return
        try:
            existing = _read_json(self.path)
            if isinstance(existing, Mapping) and existing.get("token") == self.token:
                self.path.unlink(missing_ok=True)
        finally:
            self.acquired = False

    def __enter__(self) -> "OperationalRunLock":
        self.acquire()
        return self

    def __exit__(self, _exc_type: object, _exc: object, _traceback: object) -> None:
        self.release()


def _scenario_payload(scenario: RecommendationCostScenario) -> dict[str, Any]:
    return {
        **scenario.metadata(),
        "research_sizing_basis": "configured_reference_order_not_user_position",
        "research_sizing_is_not_actual_fill": True,
        "formal_order_allowed": False,
        "shadow_only": True,
    }


def _base_payload(
    *,
    paths: OperationalPaths,
    decision_date: date,
    scenario: RecommendationCostScenario,
    input_fingerprint: str | None,
) -> dict[str, Any]:
    return {
        "schema_version": OPERATION_SCHEMA_VERSION,
        "task": TASK_NAME,
        "scheduler": {
            "task_name": TASK_NAME,
            "local_time": SCHEDULER_LOCAL_TIME,
            "host_timezone": SCHEDULER_TIMEZONE,
            "multiple_instances": "IgnoreNew",
        },
        "decision_date": decision_date.isoformat(),
        "decision_timezone": "Asia/Taipei",
        "paths": {
            "data_root": str(paths.data_root),
            "lane_output_root": str(paths.lane_output_root),
            "lane_learning_root": str(paths.lane_learning_root),
            "operational_root": str(paths.operational_root),
            "latest_status_path": str(paths.latest_status_path),
            "runs_root": str(paths.runs_root),
            "logs_root": str(paths.logs_root),
            "lock_path": str(paths.lock_path),
            "snapshot_output_root": str(paths.snapshot_output_root),
            "source_artifact_root": str(paths.source_artifact_root),
            "source_db": str(paths.source_db),
        },
        "cost_scenario": _scenario_payload(scenario),
        "cost_policy_identity": {
            "policy_id": scenario.policy_id,
            "policy_version": scenario.policy_version,
            "policy_estimate_date": scenario.policy_estimate_date,
        },
        "input_fingerprint": input_fingerprint,
        "source_read_policy": {
            "source_db_mode": "sqlite_mode_ro_query_only",
            "source_artifacts_are_read_only": True,
            "snapshot_reused_from_existing_scheduler": True,
            "technical_refresh_in_this_task": False,
            "official_refresh_in_this_task": False,
        },
        "formal_order_allowed": False,
        "shadow_only": True,
        "broker_action": False,
    }


def _next_attempt_number(runs_root: Path, decision_date: date) -> int:
    prefix = f"{decision_date.isoformat()}-attempt-"
    numbers: list[int] = []
    for path in runs_root.glob(f"{prefix}*.json"):
        match = re.search(r"-attempt-(\d+)(?:-[0-9a-f]+)?\.json$", path.name)
        if match:
            numbers.append(int(match.group(1)))
    return max(numbers, default=0) + 1


def _run_id(decision_date: date, input_fingerprint: str, attempt: int) -> str:
    return f"{decision_date.isoformat()}-attempt-{attempt:03d}-{input_fingerprint.split(':', 1)[-1][:12]}"


def _extract_child_json(stdout: str) -> dict[str, Any] | None:
    for line in reversed(stdout.splitlines()):
        text = line.strip()
        if not text.startswith("{"):
            continue
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    return None


def _verify_child_terminal_readback(
    child_payload: object,
    *,
    paths: OperationalPaths,
    decision_date: date,
    scenario: RecommendationCostScenario,
) -> dict[str, Any]:
    """驗證本次 child stdout 與 lane 內不可變 run/attempt receipt 同一。"""

    if not isinstance(child_payload, Mapping):
        return {"status": "failed", "reason": "child_stdout_json_missing_or_invalid"}
    if child_payload.get("schema_version") != _CHILD_CLI_SCHEMA_VERSION:
        return {"status": "failed", "reason": "child_cli_schema_mismatch"}
    if child_payload.get("decision_date") != decision_date.isoformat():
        return {"status": "failed", "reason": "child_decision_date_mismatch"}
    if child_payload.get("formal_order_allowed") is not False:
        return {"status": "failed", "reason": "child_formal_order_flag_invalid"}
    if child_payload.get("shadow_only") is not True:
        return {"status": "failed", "reason": "child_shadow_flag_invalid"}
    if child_payload.get("cost_scenario_hash") != scenario.scenario_hash:
        return {"status": "failed", "reason": "child_cost_scenario_mismatch"}

    run_value = child_payload.get("run")
    if not isinstance(run_value, Mapping):
        return {"status": "failed", "reason": "child_run_summary_missing"}
    run = run_value
    run_id = run.get("run_id")
    run_status = run.get("status")
    receipt_path_value = run.get("receipt_path")
    if type(run_id) is not str or not run_id.strip():
        return {"status": "failed", "reason": "child_run_id_missing_or_invalid"}
    if type(run_status) is not str or not run_status.strip():
        return {"status": "failed", "reason": "child_run_status_missing_or_invalid"}
    if type(receipt_path_value) is not str or not receipt_path_value.strip():
        return {"status": "failed", "reason": "child_run_receipt_path_missing_or_invalid"}

    receipt_path = Path(receipt_path_value)
    runs_root = paths.lane_learning_root / "runs"
    if (
        not receipt_path.is_absolute()
        or any(part in {".", ".."} for part in receipt_path.parts)
        or not receipt_path.is_relative_to(runs_root)
    ):
        return {"status": "failed", "reason": "child_run_receipt_path_outside_lane"}

    try:
        from app_module.recommendation.queries import (
            ExecutionArtifactIntegrityError,
            _read_regular_file_no_follow,
        )

        raw_receipt = _read_regular_file_no_follow(
            receipt_path,
            paths.lane_learning_root,
            max_bytes=_MAX_CHILD_RUN_RECEIPT_BYTES,
        )
    except (ExecutionArtifactIntegrityError, OSError, ValueError) as exc:
        return {
            "status": "failed",
            "reason": f"child_run_receipt_unreadable_or_unsafe:{type(exc).__name__}",
        }
    try:
        receipt_value = json.loads(raw_receipt.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        return {"status": "failed", "reason": "child_run_receipt_json_invalid"}
    if not isinstance(receipt_value, Mapping):
        return {"status": "failed", "reason": "child_run_receipt_not_object"}
    receipt = receipt_value

    expected_identity = {
        "schema_version": _CHILD_RECEIPT_SCHEMA_VERSION,
        "run_id": run_id,
        "decision_date": decision_date.isoformat(),
        "receipt_path": receipt_path_value,
        "status": run_status,
        "cost_scenario_hash": scenario.scenario_hash,
        "formal_order_allowed": False,
        "shadow_only": True,
    }
    for field, expected in expected_identity.items():
        actual = receipt.get(field)
        if actual != expected:
            return {"status": "failed", "reason": f"child_run_receipt_{field}_mismatch"}

    summary_receipt_fields = (
        "reason",
        "dataset_id",
        "dataset_hash",
        "candidate_id",
        "candidate_root",
        "training_lineage_manifest_hash",
        "training_lineage_manifest_path",
        "training_lineage_status",
        "decision",
        "decision_reason",
    )
    for field in summary_receipt_fields:
        if run.get(field) != receipt.get(field):
            return {"status": "failed", "reason": f"child_run_receipt_{field}_mismatch"}

    if run_status not in ({"completed"} | _CHILD_RUN_FAILURE_STATUSES | _CHILD_RUN_SKIP_STATUSES):
        return {"status": "failed", "reason": "child_run_status_unknown"}
    if run_status == "completed" and (
        receipt.get("finalized") is not True or receipt.get("recoverable") is not False
    ):
        return {"status": "failed", "reason": "child_completed_receipt_not_finalized"}
    if run_status != "completed" and receipt.get("recoverable") is not True:
        return {"status": "failed", "reason": "child_noncompleted_receipt_not_recoverable"}

    return {
        "status": "verified",
        "schema_version": _CHILD_RECEIPT_SCHEMA_VERSION,
        "run_id": run_id,
        "run_status": run_status,
        "decision_date": decision_date.isoformat(),
        "receipt_path": str(receipt_path),
        "receipt_sha256": "sha256:" + hashlib.sha256(raw_receipt).hexdigest(),
        "cost_scenario_hash": scenario.scenario_hash,
    }


def _child_command(
    *,
    paths: OperationalPaths,
    decision_date: date,
    scenario: RecommendationCostScenario,
    args: argparse.Namespace,
    snapshot: SnapshotSummary,
) -> list[str]:
    command = [
        sys.executable,
        str(ROOT / "scripts" / "scheduled" / "run_daily_recommendation_learning.py"),
        "--data-root",
        str(paths.data_root),
        "--output-root",
        str(paths.lane_output_root),
        "--snapshot-output-root",
        str(paths.snapshot_output_root),
        "--source-artifact-root",
        str(paths.source_artifact_root),
        "--source-db",
        str(paths.source_db),
        "--history-start-date",
        str(args.history_start_date),
        "--fixed-round-trip-cost-bp",
        "50",
        "--max-decision-dates",
        str(args.max_decision_dates),
        "--replay-selection-policy",
        "latest_eligible_dates",
        "--decision-date",
        decision_date.isoformat(),
        "--training-as-of",
        decision_date.isoformat(),
        "--cost-scenario",
        "banktaiwan_estimated_research",
        "--cost-policy-estimate-date",
        str(scenario.policy_estimate_date),
        "--research-order-quantity-shares",
        str(scenario.research_order_quantity_shares),
        "--research-order-lot-type",
        str(scenario.lot_type),
        "--research-instrument-type",
        str(scenario.instrument_type),
        "--capture-current",
    ]
    command.extend(
        [
            "--snapshot-result-id",
            snapshot.result_id,
            "--snapshot-cohort-hash",
            snapshot.cohort_hash,
            "--snapshot-invocation-output-sha256",
            snapshot.invocation_output_sha256,
            "--snapshot-invocation-output-path",
            str(snapshot.invocation_output_path),
        ]
    )
    research_invocation = getattr(args, "current_restated_research_invocation", None)
    if research_invocation is not None:
        command.extend(research_invocation.child_arguments())
        upstream_fields = (
            (
                "--research-upstream-terminal-receipt",
                getattr(args, "research_upstream_terminal_receipt", None),
            ),
            (
                "--research-upstream-terminal-receipt-sha256",
                getattr(args, "research_upstream_terminal_receipt_sha256", None),
            ),
            (
                "--research-expected-upstream-binding-sha256",
                getattr(args, "research_expected_upstream_binding_sha256", None),
            ),
        )
        if any(value is None for _flag, value in upstream_fields):
            raise OperationalLaneError("Bank research child requires the complete Legacy terminal barrier")
        for flag, value in upstream_fields:
            command.extend((flag, str(value)))
    return command


def _run_child_subprocess(
    paths: OperationalPaths,
    decision_date: date,
    scenario: RecommendationCostScenario,
    args: argparse.Namespace,
    snapshot: SnapshotSummary,
    *,
    run_id: str,
    stdout_artifact_path: Path,
) -> Mapping[str, Any]:
    command = _child_command(
        paths=paths,
        decision_date=decision_date,
        scenario=scenario,
        args=args,
        snapshot=snapshot,
    )
    environment = os.environ.copy()
    environment.update(
        {
            "OUTPUT_ROOT": str(paths.snapshot_output_root),
            "RECOMMENDATION_LEARNING_OUTPUT_ROOT": str(paths.lane_output_root),
            "DB_PATH": str(paths.source_db),
            "PYTHONUTF8": "1",
            "PYTHONIOENCODING": "utf-8",
        }
    )
    log_path = paths.logs_root / f"{decision_date.strftime('%Y%m%d')}_banktaiwan_learning.log"
    paths.logs_root.mkdir(parents=True, exist_ok=True)
    try:
        completed = subprocess.run(
            command,
            cwd=str(ROOT),
            env=environment,
            capture_output=True,
            text=False,
            check=False,
            timeout=int(args.child_timeout_seconds),
        )
    except subprocess.TimeoutExpired as exc:
        combined = _tail(_subprocess_text(exc.stdout) + _subprocess_text(exc.stderr))
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(f"\n===== CHILD TIMEOUT =====\n{combined}\n")
        return {
            "command": command,
            "returncode": None,
            "status": "timed_out",
            "reason": "child_timeout",
            "stdout_stderr_tail": combined,
        }
    stdout_value = completed.stdout or b""
    stdout_bytes = (
        stdout_value
        if isinstance(stdout_value, bytes)
        else str(stdout_value).encode("utf-8")
    )
    # 先檢查原始 stdout 大小並發布完整 bytes，再做 UTF-8/JSON 解析。
    stdout_artifact = _publish_child_stdout_artifact(
        paths=paths,
        target=stdout_artifact_path,
        stdout_bytes=stdout_bytes,
    )
    stderr_text = _subprocess_text(completed.stderr)
    stdout_text: str | None = None
    child_payload: dict[str, Any] | None = None
    child_payload_source = "missing_or_invalid_stdout_json"
    if stdout_artifact.get("status") == "verified":
        try:
            stdout_text = stdout_bytes.decode("utf-8")
        except UnicodeDecodeError:
            child_payload_source = "invocation_stdout_utf8_invalid"
        else:
            child_payload = _extract_child_json(stdout_text)
            child_payload_source = (
                "invocation_stdout_json"
                if child_payload is not None
                else "missing_or_invalid_stdout_json"
            )
    else:
        child_payload_source = str(stdout_artifact.get("reason") or "stdout_artifact_blocked")
    combined = ((stdout_text or _subprocess_text(stdout_value)) + stderr_text).strip()
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(f"\n===== CHILD =====\n{combined}\n")
    return {
        "command": command,
        "returncode": completed.returncode,
        "status": "completed_process",
        "child_payload": child_payload,
        "child_payload_source": child_payload_source,
        "stdout_artifact": stdout_artifact,
        "stdout_stderr_tail": _tail(combined),
    }


def _child_classification(child_result: Mapping[str, Any]) -> tuple[str, str, bool]:
    returncode = child_result.get("returncode")
    if returncode is None:
        return "failed_dependency", "child_timeout", True
    if isinstance(returncode, bool) or not isinstance(returncode, int):
        return "failed_dependency", "child_exit_code_invalid", True
    if returncode != 0:
        return "failed_dependency", f"child_exit_code:{returncode}", True
    terminal_value = child_result.get("terminal_readback")
    terminal = terminal_value if isinstance(terminal_value, Mapping) else {}
    if terminal.get("status") != "verified":
        reason = str(terminal.get("reason") or "child_terminal_readback_missing")
        return "failed_dependency", f"child_terminal_readback_failed:{reason}", True
    child = child_result.get("child_payload")
    child = child if isinstance(child, Mapping) else {}
    run_value = child.get("run")
    run = run_value if isinstance(run_value, Mapping) else {}
    run_status = run.get("status")
    run_reason = str(run.get("reason") or "").strip()
    if run_status in _CHILD_RUN_FAILURE_STATUSES:
        return (
            "failed_dependency",
            f"child_run_failed:{run_status}:{run_reason or 'no_reason'}",
            True,
        )
    if run_status not in ({"completed"} | _CHILD_RUN_SKIP_STATUSES):
        return "failed_dependency", "child_run_status_unknown", True

    live_capture_value = child.get("live_capture")
    live_capture = live_capture_value if isinstance(live_capture_value, Mapping) else {}
    capture_status = str(live_capture.get("status") or "").strip().lower()
    capture_reason = str(live_capture.get("reason") or "").strip()
    if capture_status in {"blocked", "failed"}:
        return "failed_dependency", f"live_capture_{capture_status}:{capture_reason}", True
    if capture_status == "skipped" and (
        "non_trading_day" in capture_reason
        or "official_calendar" in capture_reason
    ):
        wrapper_calendar = child_result.get("wrapper_calendar_is_trading_day")
        if wrapper_calendar is False:
            return (
                "skipped_non_trading_day",
                capture_reason or "non_trading_day_official_calendar",
                False,
            )
        return (
            "failed_dependency",
            "child_non_trading_skip_conflicts_with_wrapper_calendar",
            True,
        )
    decision_reason = str(
        run.get("decision_reason")
        or child.get("decision_reason")
        or ""
    ).strip()
    if "natural" in decision_reason or "matur" in decision_reason:
        return "completed_waiting_natural_maturity", decision_reason or "natural_maturity_pending", False
    if run_status in _CHILD_RUN_SKIP_STATUSES:
        return (
            "completed_with_advisories",
            f"child_run_skipped:{run_status}:{run_reason or decision_reason or 'no_reason'}",
            False,
        )
    dependencies_value = child.get("dependencies")
    dependencies = dependencies_value if isinstance(dependencies_value, Mapping) else {}
    diagnostics = dependencies.get("diagnostics")
    if isinstance(diagnostics, list) and any(
        "source" in str(item).lower() and "failed" in str(item).lower()
        for item in diagnostics
    ):
        return "completed_with_advisories", decision_reason or "source_advisory_preserved", False
    return "completed_shadow", decision_reason or "shadow_learning_completed", False


def _typed_summary_fields(
    value: object,
    fields: tuple[str, ...],
) -> dict[str, Any]:
    """從固定欄位白名單取有界純量；完整來源留在 stdout artifact。"""

    if not isinstance(value, Mapping):
        return {}
    summary: dict[str, Any] = {}
    for field in fields:
        item = value.get(field)
        if item is None or type(item) in {bool, int}:
            summary[field] = item
        elif type(item) is str and len(item) <= 1024:
            summary[field] = item
    return summary


def _summary_record(value: object, *, kind: str) -> dict[str, Any]:
    fields_by_kind: dict[str, tuple[str, ...]] = {
        "pointer": (
            "status",
            "reason",
            "candidate_id",
            "candidate_root",
            "model_path",
            "artifact_path",
            "artifact_sha256",
            "manifest_path",
            "manifest_sha256",
            "cost_scenario_hash",
            "updated_at",
            "created_at",
        ),
        "evidence": (
            "status",
            "reason",
            "checked_at",
            "decision_date",
            "source_date",
            "candidate_id",
            "model_id",
            "matured_count",
            "pending_count",
            "failed_count",
            "eligible_count",
            "row_count",
            "sample_count",
            "report_path",
            "receipt_path",
            "evidence_path",
            "evidence_sha256",
            "source_contract_sha256",
            "available_at",
        ),
    }
    if kind not in fields_by_kind:
        raise ValueError("unsupported child summary record kind")
    return _typed_summary_fields(value, fields_by_kind[kind])


def _compact_child_payload_summary(
    child_payload: Mapping[str, Any],
    *,
    stdout_artifact: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """產生 operational receipt 白名單摘要，不展開完整來源合約或列資料。"""

    run_value = child_payload.get("run")
    run = _typed_summary_fields(
        run_value,
        (
            "run_id",
            "status",
            "reason",
            "receipt_path",
            "latest_status_path",
            "dataset_id",
            "dataset_hash",
            "candidate_id",
            "candidate_root",
            "training_lineage_manifest_hash",
            "training_lineage_manifest_path",
            "training_lineage_status",
            "decision",
            "decision_reason",
            "idempotent_replay",
        ),
    )
    dependencies_value = child_payload.get("dependencies")
    dependencies = _typed_summary_fields(
        dependencies_value,
        ("data_status", "outcome_status", "drift_status", "recovery_policy"),
    )
    if isinstance(dependencies_value, Mapping):
        diagnostics = dependencies_value.get("diagnostics")
        if isinstance(diagnostics, list):
            dependencies["diagnostic_count"] = len(diagnostics)
        receipt = dependencies_value.get("source_contract_receipt")
        receipt_summary = _typed_summary_fields(
            receipt,
            (
                "status",
                "reason",
                "contract_path",
                "contract_content_sha256",
                "contract_file_sha256",
                "contract_sha256",
                "decision_date",
                "checked_at",
                "availability_cutoff_at",
            ),
        )
        if receipt_summary:
            dependencies["source_contract_receipt"] = receipt_summary
        source_contract = dependencies_value.get("source_contract")
        if isinstance(source_contract, Mapping):
            contract_summary = _typed_summary_fields(
                source_contract,
                (
                    "status",
                    "reason",
                    "decision_date",
                    "contract_sha256",
                    "checked_at",
                    "availability_cutoff_at",
                    "history_start_date",
                    "replay_start_date",
                    "replay_end_date",
                ),
            )
            technical = source_contract.get("technical")
            if isinstance(technical, Mapping):
                technical_summary = _typed_summary_fields(
                    technical,
                    (
                        "status",
                        "reason",
                        "verified",
                        "publication_time_verified",
                        "prospective_available",
                        "latest_receipt_source_date",
                        "technical_input_cutoff_max",
                    ),
                )
                feature_snapshot = technical.get("prospective_feature_snapshot")
                feature_summary = _typed_summary_fields(
                    feature_snapshot,
                    (
                        "status",
                        "verified",
                        "reason",
                        "captured_at",
                        "rows_sha256",
                        "content_sha256",
                        "row_count",
                    ),
                )
                if feature_summary:
                    technical_summary["prospective_feature_snapshot"] = feature_summary
                if technical_summary:
                    contract_summary["technical"] = technical_summary
            corporate = source_contract.get("corporate_actions")
            if isinstance(corporate, Mapping):
                corporate_summary = _typed_summary_fields(
                    corporate,
                    (
                        "status",
                        "reason",
                        "official_event_publication_verified",
                        "formal_source_contract_verified",
                    ),
                )
                adjustment = corporate.get("adjustment_custody")
                adjustment_summary = _typed_summary_fields(
                    adjustment,
                    (
                        "status",
                        "reason",
                        "verified",
                        "manifest_path",
                        "manifest_sha256",
                        "available_at",
                        "row_count",
                    ),
                )
                if adjustment_summary:
                    corporate_summary["adjustment_custody"] = adjustment_summary
                if corporate_summary:
                    contract_summary["corporate_actions"] = corporate_summary
            if contract_summary:
                dependencies["source_contract"] = contract_summary

    lanes = (
        dependencies_value.get("source_contract", {}).get("lanes")
        if isinstance(dependencies_value, Mapping)
        and isinstance(dependencies_value.get("source_contract"), Mapping)
        else None
    )
    if isinstance(lanes, Mapping):
        price_up = lanes.get("price_up_calibration")
        price_up_summary = _typed_summary_fields(
            price_up,
            ("prospective_status", "status", "reason"),
        )
        if isinstance(price_up, Mapping):
            blockers = price_up.get("prospective_blockers") or price_up.get("blockers")
            if isinstance(blockers, list):
                price_up_summary["blocker_count"] = len(blockers)
        if price_up_summary:
            dependencies["price_up_calibration"] = price_up_summary

    live_capture = _typed_summary_fields(
        child_payload.get("live_capture"),
        (
            "status",
            "reason",
            "checked_at",
            "decision_date",
            "source_contract_hash",
            "candidate_id",
            "capture_path",
            "capture_id",
            "capture_hash",
            "active_model_monitor_status",
            "active_model_monitor_reason",
        ),
    )
    source_artifact = (
        dict(stdout_artifact)
        if isinstance(stdout_artifact, Mapping)
        else {"status": "not_captured_by_test_child_runner"}
    )
    summary: dict[str, Any] = {
        "schema_version": "banktaiwan-child-result-summary.v1",
        "source": "verified_child_cli_stdout_artifact",
        "source_stdout_artifact": source_artifact,
        "child_cli": _typed_summary_fields(
            child_payload,
            (
                "schema_version",
                "decision_date",
                "decision_timezone",
                "cost_scenario_hash",
                "symbol_source",
                "run_scope",
                "capture_scope",
                "experiment_scope",
                "recoverable",
                "formal_order_allowed",
                "shadow_only",
                "error",
            ),
        ),
        "run": run,
        "dependencies": dependencies,
        "live_capture": live_capture,
        "active_pointer": _summary_record(
            child_payload.get("active_pointer"), kind="pointer"
        ),
        "challenger": _summary_record(
            child_payload.get("challenger"), kind="pointer"
        ),
        "natural_evidence": _summary_record(
            child_payload.get("natural_evidence"), kind="evidence"
        ),
        "active_model_natural_evidence": _summary_record(
            child_payload.get("active_model_natural_evidence"), kind="evidence"
        ),
    }
    return summary


def _projection_for_idempotent_replay(
    existing: Mapping[str, Any],
) -> dict[str, Any]:
    payload = dict(existing)
    payload["idempotent_replay"] = True
    payload["reused_run_id"] = existing.get("run_id")
    payload["reused_receipt_path"] = existing.get("receipt_path")
    payload["last_observed_at"] = datetime.now(TAIPEI).isoformat(timespec="seconds")
    return payload


_LATEST_STATUS_ONLY_FIELDS = frozenset(
    {
        "latest_status_path",
        "terminal_receipt_sha256",
        "idempotent_replay",
        "reused_run_id",
        "reused_receipt_path",
        "last_observed_at",
    }
)


def _reusable_terminal_receipt_matches(
    *,
    paths: OperationalPaths,
    latest: Mapping[str, Any],
    decision_date: date,
    input_fingerprint: str,
) -> bool:
    """只重用有界、非連結且與不可變 run receipt 完全相符的終態。"""

    run_id = latest.get("run_id")
    receipt_path_value = latest.get("receipt_path")
    if type(run_id) is not str or not re.fullmatch(
        rf"{re.escape(decision_date.isoformat())}-attempt-\d{{3}}-[0-9a-f]{{12}}",
        run_id,
    ):
        return False
    if type(receipt_path_value) is not str:
        return False
    expected_path = paths.runs_root / f"{run_id}.json"
    try:
        receipt_path = Path(receipt_path_value)
        if not receipt_path.is_absolute() or receipt_path != expected_path:
            return False
    except (OSError, RuntimeError, TypeError, ValueError):
        return False

    try:
        from app_module.recommendation.queries import (
            ExecutionArtifactIntegrityError,
            _read_regular_file_no_follow,
        )

        raw_receipt = _read_regular_file_no_follow(
            expected_path,
            paths.runs_root,
            max_bytes=_MAX_CHILD_RUN_RECEIPT_BYTES,
        )
    except (ExecutionArtifactIntegrityError, OSError, ValueError):
        return False
    declared_hash = latest.get("terminal_receipt_sha256")
    actual_hash = "sha256:" + hashlib.sha256(raw_receipt).hexdigest()
    if type(declared_hash) is not str or declared_hash != actual_hash:
        return False
    try:
        receipt_value = json.loads(raw_receipt.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        return False
    if not isinstance(receipt_value, Mapping):
        return False
    if (
        latest.get("schema_version") != OPERATION_SCHEMA_VERSION
        or latest.get("task") != TASK_NAME
        or latest.get("decision_date") != decision_date.isoformat()
        or latest.get("input_fingerprint") != input_fingerprint
        or latest.get("status") not in _REUSABLE_TERMINAL_STATUSES
        or latest.get("finalized") is not True
        or latest.get("recoverable") is not False
    ):
        return False
    child_invocation = latest.get("child_invocation")
    if (
        isinstance(child_invocation, Mapping)
        and child_invocation.get("child_payload_source") == "invocation_stdout_json"
        and not _child_stdout_artifact_matches(
            paths=paths,
            run_id=run_id,
            child_invocation=child_invocation,
        )
    ):
        return False
    latest_core = {
        key: value
        for key, value in latest.items()
        if key not in _LATEST_STATUS_ONLY_FIELDS
    }
    return dict(receipt_value) == latest_core


def _child_stdout_artifact_matches(
    *,
    paths: OperationalPaths,
    run_id: str,
    child_invocation: Mapping[str, Any],
) -> bool:
    """重用終態前驗證其原始 child stdout artifact 仍與宣告 bytes 相同。"""

    artifact = child_invocation.get("stdout_artifact")
    if not isinstance(artifact, Mapping) or artifact.get("status") != "verified":
        return False
    expected_path = (
        paths.operational_root / "child_cli_artifacts" / f"{run_id}.stdout.bin"
    )
    if not _same_resolved_path(artifact.get("path"), expected_path):
        return False
    size_bytes = artifact.get("size_bytes")
    digest = artifact.get("sha256")
    if (
        type(size_bytes) is not int
        or size_bytes <= 0
        or size_bytes > _MAX_CHILD_CLI_STDOUT_ARTIFACT_BYTES
        or not _is_sha256_text(digest)
    ):
        return False
    try:
        before = expected_path.lstat()
        if not stat.S_ISREG(before.st_mode) or _has_reparse_attribute(before):
            return False
        raw = _read_child_stdout_artifact(
            expected_path,
            root=paths.operational_root.resolve(strict=True),
        )
        after = expected_path.lstat()
    except (OSError, RuntimeError, ValueError):
        return False
    return (
        stat.S_ISREG(after.st_mode)
        and not _has_reparse_attribute(after)
        and (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
        and len(raw) == size_bytes
        and "sha256:" + hashlib.sha256(raw).hexdigest() == digest
    )


def _persist_terminal(
    *,
    paths: OperationalPaths,
    payload: Mapping[str, Any],
    run_id: str,
) -> dict[str, Any]:
    run_path = paths.runs_root / f"{run_id}.json"
    completed_at = datetime.now(TAIPEI).isoformat(timespec="seconds")
    run_payload = dict(payload)
    run_payload.update(
        {
            "run_id": run_id,
            "receipt_path": str(run_path),
            "finalized": True,
            "completed_at": completed_at,
        }
    )
    run_bytes = _encode_json_payload(run_payload)
    receipt_sha256 = "sha256:" + hashlib.sha256(run_bytes).hexdigest()
    latest_payload = dict(run_payload)
    latest_payload["latest_status_path"] = str(paths.latest_status_path)
    latest_payload["terminal_receipt_sha256"] = receipt_sha256
    latest_bytes = _encode_json_payload(latest_payload)
    if (
        len(run_bytes) > _MAX_OPERATIONAL_STATUS_BYTES
        or len(latest_bytes) > _MAX_OPERATIONAL_STATUS_BYTES
    ):
        run_payload = _compact_terminal_size_limit_payload(
            payload=payload,
            run_id=run_id,
            run_path=run_path,
            completed_at=completed_at,
            original_size_bytes=max(len(run_bytes), len(latest_bytes)),
        )
        run_bytes = _encode_json_payload(run_payload)
        receipt_sha256 = "sha256:" + hashlib.sha256(run_bytes).hexdigest()
        latest_payload = dict(run_payload)
        latest_payload["latest_status_path"] = str(paths.latest_status_path)
        latest_payload["terminal_receipt_sha256"] = receipt_sha256
        latest_bytes = _encode_json_payload(latest_payload)
        if (
            len(run_bytes) > _MAX_OPERATIONAL_STATUS_BYTES
            or len(latest_bytes) > _MAX_OPERATIONAL_STATUS_BYTES
        ):
            raise OperationalLaneError(
                "compact terminal fallback exceeds operational JSON write bound"
            )
    _write_json_bytes(run_path, run_bytes)
    _write_json_bytes(paths.latest_status_path, latest_bytes)
    return latest_payload


def _compact_terminal_size_limit_payload(
    *,
    payload: Mapping[str, Any],
    run_id: str,
    run_path: Path,
    completed_at: str,
    original_size_bytes: int,
) -> dict[str, Any]:
    """保留操作身分與 child custody，避免超限報告阻止小型 fail-closed receipt。"""

    retained = (
        "schema_version",
        "task",
        "scheduler",
        "decision_date",
        "decision_timezone",
        "paths",
        "cost_scenario",
        "cost_policy_identity",
        "input_fingerprint",
        "source_read_policy",
        "started_at",
        "attempt_number",
        "retry",
        "snapshot",
        "upstream_projection_wait",
        "attempt_budget",
        "formal_order_allowed",
        "shadow_only",
        "broker_action",
    )
    fallback = {key: payload[key] for key in retained if key in payload}
    calendar_value = payload.get("calendar")
    if isinstance(calendar_value, Mapping):
        calendar_summary = _typed_summary_fields(
            calendar_value,
            ("timezone", "is_official_trading_day", "reason"),
        )
        identity_value = calendar_value.get("input_identity")
        identity_summary = _typed_summary_fields(
            identity_value,
            ("decision_date", "is_official_trading_day", "reason"),
        )
        if identity_summary:
            calendar_summary["input_identity"] = identity_summary
        if calendar_summary:
            fallback["calendar"] = calendar_summary
    child_invocation_value = payload.get("child_invocation")
    child_invocation: dict[str, Any] = {}
    if isinstance(child_invocation_value, Mapping):
        child_invocation = _typed_summary_fields(
            child_invocation_value,
            (
                "status",
                "returncode",
                "child_payload_source",
                "status_path",
            ),
        )
        for key in ("command", "stdout_stderr_tail", "terminal_readback", "stdout_artifact"):
            value = child_invocation_value.get(key)
            if key == "command" and isinstance(value, list) and len(value) <= 64 and all(
                type(item) is str and len(item) <= 1024 for item in value
            ):
                child_invocation[key] = list(value)
            elif key == "stdout_stderr_tail" and type(value) is str:
                child_invocation[key] = value[-8000:]
            elif key in {"terminal_readback", "stdout_artifact"} and isinstance(value, Mapping):
                child_invocation[key] = _typed_summary_fields(
                    value,
                    (
                        "status",
                        "reason",
                        "run_id",
                        "run_status",
                        "decision_date",
                        "receipt_path",
                        "receipt_sha256",
                        "cost_scenario_hash",
                        "publication",
                        "path",
                        "size_bytes",
                        "sha256",
                        "observed_size_bytes",
                        "size_limit_bytes",
                    ),
                )
    fallback.update(
        {
            "run_id": run_id,
            "receipt_path": str(run_path),
            "completed_at": completed_at,
            "status": "failed_dependency",
            "reason": "operational_terminal_payload_size_limit_exceeded",
            "recoverable": True,
            "original_operational_classification": {
                "status": payload.get("status"),
                "reason": payload.get("reason"),
                "payload_size_bytes": original_size_bytes,
            },
            "child_invocation": child_invocation or "not_started",
        }
    )
    child_result_value = payload.get("child_result")
    if isinstance(child_result_value, Mapping) and child_result_value.get(
        "schema_version"
    ) == "banktaiwan-child-result-summary.v1":
        fallback["child_result"] = dict(child_result_value)
    outcome_value = payload.get("outcome_evaluation")
    if isinstance(outcome_value, Mapping):
        fallback["outcome_evaluation"] = _typed_summary_fields(
            outcome_value,
            ("decision", "decision_reason", "candidate_id", "candidate_root"),
        )
    fallback.update(
        {
            "formal_order_allowed": False,
            "shadow_only": True,
            "broker_action": False,
        }
    )
    return fallback


def _build_scenario(args: argparse.Namespace) -> RecommendationCostScenario:
    quantity = (
        DEFAULT_RESEARCH_ORDER_QUANTITY_SHARES
        if args.research_order_quantity_shares is None
        else args.research_order_quantity_shares
    )
    return build_banktaiwan_cost_scenario(
        policy_estimate_date=str(args.cost_policy_estimate_date),
        research_order_amount_twd=args.research_order_amount_twd,
        research_order_quantity_shares=quantity,
        lot_type=str(args.research_order_lot_type),
        instrument_type=str(args.research_instrument_type),
    )


def _common_args(args: argparse.Namespace) -> tuple[OperationalPaths, date, RecommendationCostScenario]:
    paths = resolve_operational_paths(
        data_root=args.data_root,
        lane_output_root=args.output_root,
        snapshot_output_root=args.snapshot_output_root,
        source_artifact_root=args.source_artifact_root,
        source_db=args.source_db,
    )
    decision_date = (
        date.fromisoformat(str(args.decision_date)[:10])
        if args.decision_date
        else datetime.now(TAIPEI).date()
    )
    scenario = _build_scenario(args)
    return paths, decision_date, scenario


def _dry_run(args: argparse.Namespace) -> int:
    try:
        paths, decision_date, scenario = _common_args(args)
        official_day, calendar_reason = _official_calendar(
            paths.source_db
        ).is_official_trading_day(decision_date, allow_online_probe=False)
        if official_day is True:
            snapshot, snapshot_reason = load_same_day_snapshot(
                output_root=paths.snapshot_output_root,
                decision_date=decision_date,
            )
        else:
            snapshot = None
            snapshot_reason = (
                "not_applicable_non_trading_day"
                if official_day is False
                else "not_checked_calendar_unresolved"
            )
        planned = {
            "schema_version": OPERATION_SCHEMA_VERSION,
            "status": "dry_run",
            "task": TASK_NAME,
            "decision_date": decision_date.isoformat(),
            "decision_timezone": "Asia/Taipei",
            "scheduler": {
                "task_name": TASK_NAME,
                "local_time": SCHEDULER_LOCAL_TIME,
                "host_timezone": SCHEDULER_TIMEZONE,
                "multiple_instances": "IgnoreNew",
            },
            "paths": {
                "lane_output_root": str(paths.lane_output_root),
                "snapshot_output_root": str(paths.snapshot_output_root),
                "source_artifact_root": str(paths.source_artifact_root),
                "source_db": str(paths.source_db),
                "latest_status_path": str(paths.latest_status_path),
                "lock_path": str(paths.lock_path),
            },
            "cost_scenario": _scenario_payload(scenario),
            "calendar": {
                "timezone": "Asia/Taipei",
                "is_official_trading_day": official_day,
                "reason": calendar_reason,
            },
            "snapshot": {
                "status": (
                    "verified"
                    if snapshot is not None
                    else "not_applicable"
                    if official_day is False
                    else "not_checked"
                    if official_day is None
                    else "blocked"
                ),
                "reason": snapshot_reason,
                "path": str(snapshot.path) if snapshot is not None else None,
                "file_sha256": snapshot.file_sha256 if snapshot is not None else None,
                "canonical_artifact_sha256": (
                    snapshot.canonical_artifact_sha256 if snapshot is not None else None
                ),
                "symbols": list(snapshot.symbols) if snapshot is not None else [],
                "result_id": snapshot.result_id if snapshot is not None else None,
                "payload_hash": snapshot.payload_hash if snapshot is not None else None,
                "schema_version": snapshot.schema_version if snapshot is not None else None,
                "schema_revision": snapshot.schema_revision if snapshot is not None else None,
                "integrity_basis": snapshot.integrity_basis if snapshot is not None else None,
                "cohort_hash": snapshot.cohort_hash if snapshot is not None else None,
                "invocation_output_path": (
                    str(snapshot.invocation_output_path) if snapshot is not None else None
                ),
                "invocation_output_sha256": (
                    snapshot.invocation_output_sha256 if snapshot is not None else None
                ),
            },
            "child_invocation": "not_run",
            "formal_order_allowed": False,
            "shadow_only": True,
            "broker_action": False,
        }
    except (OperationalLaneError, OSError, TypeError, ValueError) as exc:
        planned = {
            "schema_version": OPERATION_SCHEMA_VERSION,
            "status": "dry_run_blocked",
            "task": TASK_NAME,
            "reason": f"{type(exc).__name__}:{exc}",
            "formal_order_allowed": False,
            "shadow_only": True,
        }
        print(json.dumps(planned, ensure_ascii=False, sort_keys=True))
        return 2
    print(json.dumps(planned, ensure_ascii=False, sort_keys=True))
    return 0


def _run_locked(
    *,
    paths: OperationalPaths,
    decision_date: date,
    scenario: RecommendationCostScenario,
    args: argparse.Namespace,
    child_runner: ChildRunner | None,
    task_state_reader: Callable[[], ScheduledTaskObservation | None],
    attempt_deadline: float | None,
    monotonic: Callable[[], float],
    sleep: Callable[[float], None],
    now_provider: Callable[[], datetime],
) -> tuple[int, dict[str, Any]]:
    research_invocation = getattr(args, "current_restated_research_invocation", None)
    if research_invocation is not None and type(research_invocation) is not CurrentRestatedResearchInvocation:
        research_invocation = None
    official_day: bool | None = None
    calendar_reason = "not_checked"
    calendar: object | None = None
    if paths.source_db.is_file():
        try:
            calendar = _official_calendar(paths.source_db)
            official_day, calendar_reason = calendar.is_official_trading_day(
                decision_date,
                allow_online_probe=False,
            )
        except (OSError, RuntimeError, TypeError, ValueError):
            calendar = None
            official_day, calendar_reason = None, "official_calendar_read_failed"
    else:
        calendar_reason = "source_db_missing"
    upstream_wait_audit: dict[str, Any] = {
        "enabled": int(getattr(args, "upstream_projection_wait_seconds", 0)) > 0,
        "status": (
            "disabled"
            if int(getattr(args, "upstream_projection_wait_seconds", 0)) <= 0
            else "not_attempted"
        ),
        "wait_limit_seconds": int(
            getattr(args, "upstream_projection_wait_seconds", 0)
        ),
        "waited_seconds": 0.0,
        "poll_count": 0,
    }
    if official_day is True:
        snapshot, snapshot_reason = load_same_day_snapshot(
            output_root=paths.snapshot_output_root,
            decision_date=decision_date,
        )
        snapshot, snapshot_reason, upstream_wait_audit = (
            _maybe_wait_for_current_upstream_projection(
                paths=paths,
                decision_date=decision_date,
                initial_snapshot=snapshot,
                initial_reason=snapshot_reason,
                wait_seconds=int(
                    getattr(args, "upstream_projection_wait_seconds", 0)
                ),
                attempt_deadline=attempt_deadline,
                task_state_reader=task_state_reader,
                monotonic=monotonic,
                sleep=sleep,
                now_provider=now_provider,
            )
        )
    else:
        snapshot = None
        snapshot_reason = (
            "not_applicable_non_trading_day"
            if official_day is False
            else "not_checked_calendar_unresolved"
        )
        upstream_wait_audit["status"] = (
            "not_applicable_non_trading_day"
            if official_day is False
            else "not_attempted_calendar_unresolved"
        )
    calendar_identity = _calendar_input_identity(
        calendar if calendar is not None else object(),
        source_db=paths.source_db,
        decision_date=decision_date,
        is_trading_day=official_day,
        reason=calendar_reason,
    )
    fingerprint = build_input_fingerprint(
        paths=paths,
        decision_date=decision_date,
        scenario=scenario,
        snapshot=snapshot,
        history_start_date=str(args.history_start_date),
        max_decision_dates=int(args.max_decision_dates),
        calendar_identity=calendar_identity,
    )
    existing, _existing_read_error = _read_bounded_snapshot_status(
        paths.latest_status_path,
        root=paths.operational_root,
    )
    if (
        isinstance(existing, Mapping)
        and existing.get("decision_date") == decision_date.isoformat()
        and existing.get("input_fingerprint") == fingerprint
        and existing.get("status") in _REUSABLE_TERMINAL_STATUSES
        and _reusable_terminal_receipt_matches(
            paths=paths,
            latest=existing,
            decision_date=decision_date,
            input_fingerprint=fingerprint,
        )
    ):
        projection = _projection_for_idempotent_replay(existing)
        _write_json(
            paths.latest_status_path,
            projection,
            max_bytes=_MAX_OPERATIONAL_STATUS_BYTES,
        )
        return 0, projection

    attempt = _next_attempt_number(paths.runs_root, decision_date)
    run_id = _run_id(decision_date, fingerprint, attempt)
    base = _base_payload(
        paths=paths,
        decision_date=decision_date,
        scenario=scenario,
        input_fingerprint=fingerprint,
    )
    base["upstream_projection_wait"] = upstream_wait_audit
    base.update(
        {
            "run_id": run_id,
            "attempt_number": attempt,
            "started_at": datetime.now(TAIPEI).isoformat(timespec="seconds"),
            "retry": {
                "attempt_number": attempt,
                "previous_status": existing.get("status") if isinstance(existing, Mapping) else None,
                "previous_run_id": existing.get("run_id") if isinstance(existing, Mapping) else None,
                "retryable_after_failure": True,
            },
            "snapshot": {
                "status": (
                    "verified"
                    if snapshot is not None
                    else "not_applicable"
                    if official_day is False
                    else "not_checked"
                    if official_day is None
                    else "blocked"
                ),
                "reason": snapshot_reason,
                "path": str(snapshot.path) if snapshot is not None else None,
                "file_sha256": snapshot.file_sha256 if snapshot is not None else None,
                "canonical_artifact_sha256": (
                    snapshot.canonical_artifact_sha256 if snapshot is not None else None
                ),
                "status_path": str(snapshot.status_path) if snapshot is not None else str(paths.snapshot_output_root / "scheduled" / "recommendation_snapshot" / "latest_status.json"),
                "symbols": list(snapshot.symbols) if snapshot is not None else [],
                "cohort": dict(snapshot.cohort) if snapshot is not None else {},
                "result_id": snapshot.result_id if snapshot is not None else None,
                "payload_hash": snapshot.payload_hash if snapshot is not None else None,
                "schema_version": snapshot.schema_version if snapshot is not None else None,
                "schema_revision": snapshot.schema_revision if snapshot is not None else None,
                "integrity_basis": snapshot.integrity_basis if snapshot is not None else None,
                "decision_date": snapshot.decision_date if snapshot is not None else None,
                "data_as_of_date": snapshot.data_as_of_date if snapshot is not None else None,
                "decision_at": snapshot.decision_at if snapshot is not None else None,
                "available_at": snapshot.available_at if snapshot is not None else None,
                "cohort_hash": snapshot.cohort_hash if snapshot is not None else None,
                "pipeline_run_id": snapshot.pipeline_run_id if snapshot is not None else None,
                "pipeline_status_path": (
                    str(snapshot.pipeline_status_path) if snapshot is not None else None
                ),
                "invocation_output_path": (
                    str(snapshot.invocation_output_path) if snapshot is not None else None
                ),
                "invocation_output_sha256": (
                    snapshot.invocation_output_sha256 if snapshot is not None else None
                ),
                "invocation_output_size": (
                    snapshot.invocation_output_size if snapshot is not None else None
                ),
            },
            "replay_scope": {
                "history_start_date": str(args.history_start_date),
                "max_decision_dates": int(args.max_decision_dates),
                "replay_selection_policy": "latest_eligible_dates",
                "fixed_round_trip_cost_bp": 50,
            },
        }
    )
    base["calendar"] = {
        "timezone": "Asia/Taipei",
        "is_official_trading_day": official_day,
        "reason": calendar_reason,
        "input_identity": calendar_identity,
    }

    if official_day is False:
        base.update(
            {
                "status": "skipped_non_trading_day",
                "reason": calendar_reason,
                "recoverable": False,
                "child_invocation": "not_required_non_trading_day",
            }
        )
        result = _persist_terminal(paths=paths, payload=base, run_id=run_id)
        return 0, result

    if official_day is None:
        base.update(
            {
                "status": "failed_dependency",
                "reason": f"official_calendar_unresolved:{calendar_reason}",
                "recoverable": True,
                "child_invocation": "not_started",
            }
        )
        result = _persist_terminal(paths=paths, payload=base, run_id=run_id)
        return 2, result

    if not paths.source_db.is_file():
        base.update(
            {
                "status": "failed_dependency",
                "reason": "source_db_missing",
                "recoverable": True,
                "child_invocation": "not_started",
            }
        )
        result = _persist_terminal(paths=paths, payload=base, run_id=run_id)
        return 2, result
    if not paths.source_artifact_root.is_dir():
        base.update(
            {
                "status": "failed_dependency",
                "reason": "source_artifact_root_missing",
                "recoverable": True,
                "child_invocation": "not_started",
            }
        )
        result = _persist_terminal(paths=paths, payload=base, run_id=run_id)
        return 2, result
    if snapshot is None:
        base.update(
            {
                "status": "failed_dependency",
                "reason": snapshot_reason or "same_day_scheduled_recommendation_snapshot_missing",
                "recoverable": True,
                "child_invocation": "not_started",
            }
        )
        result = _persist_terminal(paths=paths, payload=base, run_id=run_id)
        return 2, result

    child_args = args
    if attempt_deadline is not None:
        remaining_child_seconds = int(attempt_deadline - monotonic())
        configured_child_seconds = int(args.child_timeout_seconds)
        effective_child_seconds = min(
            configured_child_seconds,
            remaining_child_seconds,
        )
        if effective_child_seconds <= 0:
            base.update(
                {
                    "status": "failed_dependency",
                    "reason": "bank_attempt_budget_exhausted_before_child",
                    "recoverable": True,
                    "child_invocation": "not_started",
                    "attempt_budget": {
                        "total_limit_seconds": _BANK_TASK_EXECUTION_BUDGET_SECONDS,
                        "terminal_flush_reserve_seconds": _BANK_TERMINAL_FLUSH_RESERVE_SECONDS,
                        "configured_child_timeout_seconds": configured_child_seconds,
                        "effective_child_timeout_seconds": 0,
                    },
                }
            )
            result = _persist_terminal(paths=paths, payload=base, run_id=run_id)
            return 2, result
        child_args = argparse.Namespace(**vars(args))
        child_args.child_timeout_seconds = effective_child_seconds
        base["attempt_budget"] = {
            "total_limit_seconds": _BANK_TASK_EXECUTION_BUDGET_SECONDS,
            "terminal_flush_reserve_seconds": _BANK_TERMINAL_FLUSH_RESERVE_SECONDS,
            "configured_child_timeout_seconds": configured_child_seconds,
            "effective_child_timeout_seconds": effective_child_seconds,
            "remaining_before_child_seconds": max(0, int(attempt_deadline - monotonic())),
        }

    stdout_artifact_path: Path | None = None
    if child_runner is None:
        stdout_artifact_path, artifact_target_error = (
            _prepare_child_stdout_artifact_target(paths=paths, run_id=run_id)
        )
        if stdout_artifact_path is None:
            base.update(
                {
                    "status": "failed_dependency",
                    "reason": artifact_target_error or "child_stdout_artifact_target_unavailable",
                    "recoverable": True,
                    "child_invocation": {
                        "status": "not_started",
                        "reason": artifact_target_error
                        or "child_stdout_artifact_target_unavailable",
                        "stdout_artifact": {
                            "status": "blocked",
                            "reason": artifact_target_error
                            or "child_stdout_artifact_target_unavailable",
                        },
                    },
                }
            )
            result = _persist_terminal(paths=paths, payload=base, run_id=run_id)
            return 2, result
    if child_runner is not None:
        child_result = dict(child_runner(paths, decision_date, scenario, child_args))
    else:
        assert stdout_artifact_path is not None
        child_result = dict(
            _run_child_subprocess(
                paths,
                decision_date,
                scenario,
                child_args,
                snapshot,
                run_id=run_id,
                stdout_artifact_path=stdout_artifact_path,
            )
        )
    child_result["wrapper_calendar_is_trading_day"] = official_day
    child_result["terminal_readback"] = _verify_child_terminal_readback(
        child_result.get("child_payload"),
        paths=paths,
        decision_date=decision_date,
        scenario=scenario,
    )
    status, reason, recoverable = _child_classification(child_result)
    child_payload = child_result.get("child_payload")
    child_payload = child_payload if isinstance(child_payload, Mapping) else {}
    run_value = child_payload.get("run")
    run = dict(run_value) if isinstance(run_value, Mapping) else {}
    base.update(
        {
            "status": status,
            "reason": reason,
            "recoverable": recoverable,
            "child_invocation": {
                "status": child_result.get("status"),
                "returncode": child_result.get("returncode"),
                "command": list(child_result.get("command") or []),
                "stdout_stderr_tail": child_result.get("stdout_stderr_tail", ""),
                "child_payload_source": child_result.get("child_payload_source"),
                "stdout_artifact": child_result.get("stdout_artifact"),
                "terminal_readback": child_result.get("terminal_readback"),
                "status_path": str(paths.lane_learning_root / "latest_status.json"),
            },
            "child_result": (
                _compact_child_payload_summary(
                    child_payload,
                    stdout_artifact=(
                        child_result.get("stdout_artifact")
                        if isinstance(child_result.get("stdout_artifact"), Mapping)
                        else None
                    ),
                )
                if child_payload
                else {}
            ),
            "outcome_evaluation": {
                **_typed_summary_fields(
                    {
                        "decision": run.get("decision") or child_payload.get("decision"),
                        "decision_reason": run.get("decision_reason") or child_payload.get("decision_reason"),
                        "candidate_id": run.get("candidate_id"),
                        "candidate_root": run.get("candidate_root"),
                    },
                    ("decision", "decision_reason", "candidate_id", "candidate_root"),
                ),
                "active_pointer": _summary_record(
                    child_payload.get("active_pointer"), kind="pointer"
                ),
                "challenger": _summary_record(
                    child_payload.get("challenger"), kind="pointer"
                ),
                "natural_evidence": _summary_record(
                    child_payload.get("natural_evidence"), kind="evidence"
                ),
                "active_model_natural_evidence": _summary_record(
                    child_payload.get("active_model_natural_evidence"), kind="evidence"
                ),
            },
            "formal_order_allowed": False,
            "shadow_only": True,
            "broker_action": False,
        }
    )
    result = _persist_terminal(paths=paths, payload=base, run_id=run_id)
    return (0 if result.get("status") in _REUSABLE_TERMINAL_STATUSES else 2), result


def run_once(
    args: argparse.Namespace,
    *,
    child_runner: ChildRunner | None = None,
    task_state_reader: Callable[[], ScheduledTaskObservation | None] | None = None,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    now_provider: Callable[[], datetime] | None = None,
) -> tuple[int, dict[str, Any]]:
    """執行一次具 lock、retry、receipt 與 non-trading 分類的每日 attempt。"""

    try:
        research_invocation = parse_current_restated_research_invocation(args)
    except (CurrentRestatedResearchError, OSError, TypeError, ValueError) as exc:
        return 2, {
            "schema_version": OPERATION_SCHEMA_VERSION,
            "status": "failed_dependency",
            "task": TASK_NAME,
            "reason": "current_restated_research_input_invalid",
            "error": f"{type(exc).__name__}: {exc}",
            "formal_order_allowed": False,
            "shadow_only": True,
            "broker_action": False,
        }
    setattr(args, "current_restated_research_invocation", research_invocation)

    upstream_values = (
        getattr(args, "research_upstream_terminal_receipt", None),
        getattr(args, "research_upstream_terminal_receipt_sha256", None),
        getattr(args, "research_expected_upstream_binding_sha256", None),
    )
    if research_invocation is None and any(value is not None for value in upstream_values):
        return 2, {
            "schema_version": "banktaiwan-recommendation-learning-research-only.v1",
            "status": "failed_dependency",
            "task": TASK_NAME,
            "reason": "upstream_terminal_pins_require_current_restated_research_opt_in",
            "formal_order_allowed": False,
            "shadow_only": True,
            "broker_action": False,
        }
    if research_invocation is not None:
        if any(value is None for value in upstream_values):
            return 2, {
                "schema_version": "banktaiwan-recommendation-learning-research-only.v1",
                "status": "failed_dependency",
                "task": TASK_NAME,
                "reason": "current_restated_research_requires_complete_legacy_terminal_barrier",
                "model_training_performed": False,
                "verified_model_reused": False,
                "formal_calibration_performed": False,
                "formal_order_allowed": False,
                "shadow_only": True,
                "broker_action": False,
            }
        return _run_current_restated_research_sidecar_entry(
            args,
            invocation=research_invocation,
            actual_invocation=list(sys.argv),
        )

    wait_seconds = int(getattr(args, "upstream_projection_wait_seconds", 0))
    attempt_deadline = (
        monotonic()
        + _BANK_TASK_EXECUTION_BUDGET_SECONDS
        - _BANK_TERMINAL_FLUSH_RESERVE_SECONDS
        if wait_seconds > 0
        else None
    )
    clock = now_provider or (lambda: datetime.now(TAIPEI))
    source_task_reader = task_state_reader or _query_upstream_task_observation
    try:
        paths, decision_date, scenario = _common_args(args)
    except (OperationalLaneError, OSError, TypeError, ValueError) as exc:
        payload = {
            "schema_version": OPERATION_SCHEMA_VERSION,
            "status": "failed_dependency",
            "task": TASK_NAME,
            "reason": f"configuration_invalid:{type(exc).__name__}:{exc}",
            "formal_order_allowed": False,
            "shadow_only": True,
            "broker_action": False,
        }
        return 2, payload
    lock = OperationalRunLock(paths.lock_path)
    try:
        lock.acquire()
    except OperationalOverlapError as exc:
        payload = {
            "schema_version": OPERATION_SCHEMA_VERSION,
            "status": "skipped_overlap",
            "task": TASK_NAME,
            "decision_date": decision_date.isoformat(),
            "decision_timezone": "Asia/Taipei",
            "reason": str(exc),
            "lock_path": str(paths.lock_path),
            "recoverable": True,
            "formal_order_allowed": False,
            "shadow_only": True,
            "broker_action": False,
        }
        return 0, payload
    try:
        return _run_locked(
            paths=paths,
            decision_date=decision_date,
            scenario=scenario,
            args=args,
            child_runner=child_runner,
            task_state_reader=source_task_reader,
            attempt_deadline=attempt_deadline,
            monotonic=monotonic,
            sleep=sleep,
            now_provider=clock,
        )
    finally:
        lock.release()


def _parse_upstream_projection_wait_seconds(value: str) -> int:
    try:
        seconds = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("等待秒數必須是整數") from exc
    if seconds < 0 or seconds > _MAX_UPSTREAM_PROJECTION_WAIT_SECONDS:
        raise argparse.ArgumentTypeError(
            f"等待秒數必須介於 0 與 {_MAX_UPSTREAM_PROJECTION_WAIT_SECONDS}"
        )
    return seconds


def _run_current_restated_research_sidecar_entry(
    args: argparse.Namespace,
    *,
    invocation: CurrentRestatedResearchInvocation,
    actual_invocation: list[str],
) -> tuple[int, dict[str, Any]]:
    """重驗既有 Legacy terminal 並以相同 source-row cohort 寫 Bank sidecar。"""

    try:
        result = run_current_restated_research_sidecar(
            invocation,
            lane="banktaiwan",
            cost_scenario=_build_scenario(args),
            actual_invocation=actual_invocation,
            upstream_terminal_receipt_path=Path(
                args.research_upstream_terminal_receipt
            ),
            expected_upstream_terminal_receipt_sha256=str(
                args.research_upstream_terminal_receipt_sha256
            ),
            expected_upstream_binding_sha256=str(
                args.research_expected_upstream_binding_sha256
            ),
            repository_root=ROOT,
        )
        return 0, {
            "schema_version": "banktaiwan-recommendation-learning-research-only.v1",
            "status": result.status,
            "terminal": True,
            "task": TASK_NAME,
            "lane": "banktaiwan",
            "mode": "source_row_outcome_research",
            "receipt_path": str(result.receipt_path),
            "receipt_sha256": result.receipt_sha256,
            "binding_sha256": result.binding_sha256,
            "sample_cohort_sha256": result.sample_cohort_sha256,
            "core19_numeric_vector_sha256_by_symbol": dict(
                result.core19_numeric_vector_sha256_by_symbol
            ),
            "upstream_legacy_terminal_receipt_path": str(
                args.research_upstream_terminal_receipt
            ),
            "upstream_legacy_terminal_receipt_sha256": str(
                args.research_upstream_terminal_receipt_sha256
            ),
            "upstream_binding_sha256": str(
                args.research_expected_upstream_binding_sha256
            ),
            "model_training_performed": False,
            "verified_model_reused": True,
            "formal_calibration_performed": False,
            "formal_order_allowed": False,
            "shadow_only": True,
            "broker_action": False,
            "historical_pit_eligible": False,
            "decision_time_eligible": False,
            "recommendation_cohort_status": "not_a_daily_recommendation_cohort",
            "full_allocation_status": "blocked_full_allocation_teacher_unavailable",
        }
    except (CurrentRestatedResearchError, OSError, TypeError, ValueError) as exc:
        return 2, {
            "schema_version": "banktaiwan-recommendation-learning-research-only.v1",
            "status": "failed_dependency",
            "task": TASK_NAME,
            "reason": "current_restated_research_sidecar_failed",
            "error": f"{type(exc).__name__}: {exc}",
            "model_training_performed": False,
            "verified_model_reused": False,
            "formal_calibration_performed": False,
            "formal_order_allowed": False,
            "shadow_only": True,
            "broker_action": False,
            "historical_pit_eligible": False,
        }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=None)
    parser.add_argument("--output-root", type=Path, default=None)
    parser.add_argument("--snapshot-output-root", type=Path, default=None)
    parser.add_argument("--source-artifact-root", type=Path, default=None)
    parser.add_argument("--source-db", type=Path, default=None)
    parser.add_argument("--decision-date", default=None)
    parser.add_argument("--history-start-date", default="2014-01-01")
    parser.add_argument("--max-decision-dates", type=int, default=100)
    parser.add_argument("--cost-policy-estimate-date", default=DEFAULT_POLICY_ESTIMATE_DATE)
    sizing = parser.add_mutually_exclusive_group()
    sizing.add_argument("--research-order-amount-twd", default=None)
    sizing.add_argument(
        "--research-order-quantity-shares",
        type=int,
        default=None,
    )
    parser.add_argument(
        "--research-order-lot-type",
        choices=("full_lot", "odd_lot"),
        default="full_lot",
    )
    parser.add_argument(
        "--research-instrument-type",
        choices=("ordinary_stock", "equity_etf"),
        default="ordinary_stock",
    )
    parser.add_argument("--child-timeout-seconds", type=int, default=7200)
    parser.add_argument(
        "--upstream-projection-wait-seconds",
        type=_parse_upstream_projection_wait_seconds,
        default=_DEFAULT_UPSTREAM_PROJECTION_WAIT_SECONDS,
        help=(
            "僅對同日、固定 producer Task 的已驗證 running run 等候其 terminal projection；"
            "預設 0，最高 1800 秒。"
        ),
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--research-upstream-terminal-receipt", type=Path, default=None)
    parser.add_argument("--research-upstream-terminal-receipt-sha256", default=None)
    parser.add_argument("--research-expected-upstream-binding-sha256", default=None)
    add_current_restated_research_arguments(parser)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if args.dry_run:
        if args.current_restated_research_only or any(
            value is not None
            for value in (
                args.research_upstream_terminal_receipt,
                args.research_upstream_terminal_receipt_sha256,
                args.research_expected_upstream_binding_sha256,
            )
        ):
            print(
                json.dumps(
                    {
                        "schema_version": "banktaiwan-recommendation-learning-research-only.v1",
                        "status": "failed_dependency",
                        "reason": "dry_run_cannot_consume_or_publish_research_terminal_receipts",
                        "model_training_performed": False,
                        "formal_calibration_performed": False,
                        "formal_order_allowed": False,
                        "shadow_only": True,
                        "broker_action": False,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
            return 2
        return _dry_run(args)
    code, payload = run_once(args)
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
