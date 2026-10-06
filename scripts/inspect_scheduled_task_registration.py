"""唯讀檢查 baldr Windows Task Scheduler 註冊狀態。

本工具先保留既有 ``schtasks /Query`` 路徑，再以 Task Scheduler COM 讀回
精確觸發器、執行狀態與設定。COM 查詢失敗一律保留 unknown，不推定 task 不存在。
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = "scheduled-task-registration.v1"
DEFAULT_EXECUTABLE = "schtasks.exe"
DEFAULT_TIMEOUT_SECONDS = 15
PROJECT_ROOT = Path(__file__).resolve().parents[1]

EXPECTED_TASKS: tuple[dict[str, str], ...] = (
    {"name": "baldr-data-update-quick-daily", "schedule": "DAILY 04:20", "required": "true"},
    {"name": "baldr-official-market-events-daily", "schedule": "DAILY 04:50", "required": "true"},
    {"name": "baldr-data-freshness-check-daily", "schedule": "DAILY 05:00", "required": "true"},
    {"name": "baldr-ml-raw-pit-refresh-daily", "schedule": "DAILY 05:05", "required": "true"},
    {"name": "baldr-recommendation-snapshot-daily", "schedule": "DAILY 05:10", "required": "true"},
    {"name": "baldr-evidence-pipeline-dry-run-daily", "schedule": "DAILY 05:15", "required": "true"},
    {"name": "baldr-ml-promotion-evidence-daily", "schedule": "DAILY 05:17", "required": "true"},
    {"name": "baldr-ml-promotion-authority-daily", "schedule": "DAILY 05:18", "required": "true"},
    {"name": "baldr-ml-allocation-copilot-daily", "schedule": "DAILY 05:20", "required": "true"},
    {"name": "baldr-decision-evidence-capture-daily", "schedule": "DAILY 05:25", "required": "true"},
    {"name": "baldr-ml-direct-chain-maintainer", "schedule": "DAILY 05:30", "required": "true"},
    {"name": "baldr-forward-outcomes-daily", "schedule": "DAILY 05:40", "required": "true"},
    {"name": "baldr-recommendation-calibration-learning-daily", "schedule": "DAILY 05:45", "required": "true"},
    {"name": "baldr-recommendation-calibration-learning-banktaiwan-shadow-daily", "schedule": "DAILY 05:50", "required": "true"},
    {"name": "baldr-paper-execution-eod-replay-daily", "schedule": "DAILY 06:00", "required": "true"},
    {"name": "baldr-pit-sector-membership-preopen-capture-daily", "schedule": "DAILY 16:00", "required": "true"},
    {"name": "baldr-paper-portfolio-daily", "schedule": "DAILY 08:25 +08:00", "required": "true"},
    {"name": "baldr-ml-allocation-forward-daily", "schedule": "DAILY 08:25 +08:00", "required": "true"},
    {"name": "baldr-formal-pit-sidecar-postcutoff-daily", "schedule": "DAILY 18:00", "required": "true"},
    {"name": "baldr-formal-input-producer-daily", "schedule": "DAILY 21:25", "required": "true"},
    {"name": "baldr-v2-2-weekly-collection", "schedule": "WEEKLY SUN 18:00", "required": "true"},
)

TASK_WRAPPER_PATHS: dict[str, str] = {
    "baldr-paper-execution-eod-replay-daily": "scripts/scheduled/run_paper_execution_daily_isolated.cmd",
    "baldr-data-update-quick-daily": "scripts/scheduled/run_daily_data_update_quick.cmd",
    "baldr-official-market-events-daily": "scripts/scheduled/run_official_market_event_backfill.cmd",
    "baldr-data-freshness-check-daily": "scripts/scheduled/run_daily_data_freshness_check.cmd",
    "baldr-ml-raw-pit-refresh-daily": "scripts/scheduled/run_ml_raw_pit_refresh.cmd",
    "baldr-recommendation-snapshot-daily": "scripts/scheduled/run_recommendation_snapshot.cmd",
    "baldr-evidence-pipeline-dry-run-daily": "scripts/scheduled/run_evidence_pipeline_dry_run.cmd",
    "baldr-ml-promotion-evidence-daily": "scripts/scheduled/run_ml_promotion_evidence.cmd",
    "baldr-ml-promotion-authority-daily": "scripts/scheduled/run_ml_promotion_authority.cmd",
    "baldr-ml-allocation-copilot-daily": "scripts/scheduled/run_ml_allocation_copilot.cmd",
    "baldr-decision-evidence-capture-daily": "scripts/scheduled/run_decision_evidence_capture.cmd",
    "baldr-forward-outcomes-daily": "scripts/scheduled/run_forward_outcomes_daily.cmd",
    "baldr-recommendation-calibration-learning-daily": "scripts/scheduled/run_recommendation_calibration_learning.cmd",
    "baldr-recommendation-calibration-learning-banktaiwan-shadow-daily": "scripts/scheduled/run_banktaiwan_recommendation_learning_daily.cmd",
    "baldr-paper-portfolio-daily": "scripts/scheduled/run_paper_portfolio_daily.cmd",
    "baldr-ml-allocation-forward-daily": "scripts/scheduled/run_ml_allocation_forward_daily.cmd",
    "baldr-pit-sector-membership-preopen-capture-daily": "scripts/scheduled/run_pit_sector_membership_preopen_capture.cmd",
    "baldr-formal-pit-sidecar-postcutoff-daily": "scripts/scheduled/run_formal_pit_sidecar_postcutoff.cmd",
    "baldr-formal-input-producer-daily": "scripts/scheduled/run_formal_input_producer_daily.cmd",
    "baldr-ml-direct-chain-maintainer": "scripts/scheduled/run_ml_direct_chain_maintenance.cmd",
    "baldr-v2-2-weekly-collection": "scripts/scheduled/run_v2_2_weekly_collection.cmd",
}

_SAFE_SUMMARY_KEYS = (
    "status",
    "task_to_run",
    "next_run_time",
    "last_run_time",
    "last_result",
    "logon_mode",
    "run_only_if_user_is_logged_on",
    "stop_if_the_computer_switches_to_battery_power",
    "start_the_task_only_if_the_computer_is_on_ac_power",
    "power_management",
    "scheduled_task_state",
    "execution_time_limit",
    "multiple_instances_policy",
    "schedule_type",
    "start_time",
    "days",
    "start_in",
    "execution_time_limit",
    "multiple_instances_policy",
    "restart_count",
    "restart_interval",
    "missed_runs",
    "start_when_available",
)
COM_QUERY_SCRIPT = PROJECT_ROOT / "scripts" / "scheduled" / "query_baldr_scheduled_tasks_com.py"
DEFAULT_COM_TIMEOUT_SECONDS = 20
_SENSITIVE_ARGUMENT_RE = re.compile(
    r"(?i)((?:--?|/)(?:password|passwd|token|secret|api[-_]?key|client[-_]?secret)"
    r"(?:\s+|\s*=\s*|=)|(?:password|passwd|token|secret|api[_-]?key)\s*=\s*)"
    r"(\"[^\"]*\"|'[^']*'|[^\s]+)"
)
_ACCOUNT_ARGUMENT_RE = re.compile(
    r"(?i)((?:--?|/)(?:user(?:name)?|account|run-as)(?:\s+|\s*=\s*|=)"
    r"|(?:user(?:name)?|account)\s*=\s*)(\"[^\"]*\"|'[^']*'|[^\s]+)"
)
_SID_RE = re.compile(r"\bS-1-(?:\d+-){2,}\d+\b", re.IGNORECASE)


def inspect_scheduled_task_registration(
    *,
    executable: str | None = None,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    runner=None,
    com_runner=None,
    com_python_executable: str | None = None,
    repo_root: str | Path | None = None,
) -> dict[str, Any]:
    """Query every expected task and return a redacted, deterministic summary.

    ``runner`` remains the existing schtasks test/API seam. When callers inject
    it, COM is opt-in via ``com_runner``; normal CLI runs query COM once to add
    scheduler-native fields or to recover from a schtasks query error.
    """

    if timeout_seconds < 1 or timeout_seconds > 120:
        raise ValueError("timeout_seconds must be between 1 and 120")
    command = executable or os.environ.get("BALDR_SCHTASKS_EXE", DEFAULT_EXECUTABLE)
    resolved_repo_root = _resolve_repo_root(repo_root)
    run = runner or subprocess.run
    task_results: list[dict[str, Any]] = []
    for spec in EXPECTED_TASKS:
        name = spec["name"]
        task_path = f"\\{name}"
        query = [command, "/Query", "/TN", task_path, "/V", "/FO", "LIST"]
        try:
            completed = run(
                query,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_seconds,
                check=False,
            )
        except FileNotFoundError as error:
            task_results.append(_task_result(
                spec,
                repo_root=resolved_repo_root,
                status="unknown",
                task_path=task_path,
                error=type(error).__name__,
            ))
            continue
        except subprocess.TimeoutExpired as error:
            task_results.append(_task_result(
                spec,
                repo_root=resolved_repo_root,
                status="unknown",
                task_path=task_path,
                error=type(error).__name__,
            ))
            continue
        except OSError as error:
            task_results.append(_task_result(
                spec,
                repo_root=resolved_repo_root,
                status="unknown",
                task_path=task_path,
                error=type(error).__name__,
            ))
            continue

        stdout = str(getattr(completed, "stdout", "") or "")
        stderr = str(getattr(completed, "stderr", "") or "")
        returncode = int(getattr(completed, "returncode", 1))
        summary = _parse_list_summary(stdout)
        status = "available" if returncode == 0 else "unknown"
        explicit_missing = _is_explicit_not_found(returncode, stderr or stdout)
        task_results.append(_task_result(
            spec,
            repo_root=resolved_repo_root,
            status=status,
            task_path=task_path,
            returncode=returncode,
            command_output_sha256=_sha256_text(stdout + "\n" + stderr),
            summary=summary,
            error=None if returncode == 0 else _safe_query_error(stderr or stdout),
            schtasks_explicit_missing=explicit_missing,
        ))

    injected_runner = runner is not None
    if com_runner is not None or not injected_runner:
        com_report = _query_com(
            runner=com_runner or subprocess.run,
            executable=com_python_executable,
            task_paths=[f"\\{item['name']}" for item in EXPECTED_TASKS],
            timeout_seconds=min(max(timeout_seconds, 1), DEFAULT_COM_TIMEOUT_SECONDS),
        )
        _merge_com_details(task_results, com_report, resolved_repo_root)

    available_count = sum(item["status"] == "available" for item in task_results)
    confirmed_missing_count = sum(item["status"] == "missing" for item in task_results)
    unknown_count = sum(item["status"] == "unknown" for item in task_results)
    missing_count = confirmed_missing_count + unknown_count
    wrapper_missing_count = sum(
        item.get("wrapper_status") != "present" for item in task_results
    )
    action_mismatch_count = sum(
        item.get("action_matches_wrapper") is False for item in task_results
    )
    action_unobserved_count = sum(
        item.get("action_matches_wrapper") is None for item in task_results
    )
    schedule_mismatch_count = sum(
        item.get("schedule_matches") is False for item in task_results
    )
    schedule_unobserved_count = sum(
        item.get("schedule_matches") is None for item in task_results
    )
    working_directory_mismatch_count = sum(
        item.get("working_directory_matches_repo_root") is False
        for item in task_results
    )
    working_directory_unobserved_count = sum(
        item.get("working_directory_matches_repo_root") is None
        for item in task_results
    )
    all_wrappers_present = wrapper_missing_count == 0
    all_actions_match = action_mismatch_count == 0
    all_actions_observed = action_unobserved_count == 0
    all_schedules_match = schedule_mismatch_count == 0
    all_schedules_observed = schedule_unobserved_count == 0
    return {
        "schema_version": SCHEMA_VERSION,
        "captured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "executable": command,
        "repo_root": str(resolved_repo_root),
        "query_only": True,
        "side_effect_free": True,
        "task_count": len(task_results),
        "available_count": available_count,
        "missing_or_unavailable_count": missing_count,
        "confirmed_missing_count": confirmed_missing_count,
        "unknown_count": unknown_count,
        "all_available": missing_count == 0,
        "wrapper_count": len(task_results),
        "wrapper_missing_count": wrapper_missing_count,
        "all_wrappers_present": all_wrappers_present,
        "action_mismatch_count": action_mismatch_count,
        "action_unobserved_count": action_unobserved_count,
        "all_actions_observed": all_actions_observed,
        "all_actions_match": all_actions_match,
        "schedule_mismatch_count": schedule_mismatch_count,
        "schedule_unobserved_count": schedule_unobserved_count,
        "all_schedules_observed": all_schedules_observed,
        "all_schedules_match": all_schedules_match,
        "working_directory_mismatch_count": working_directory_mismatch_count,
        "working_directory_unobserved_count": working_directory_unobserved_count,
        "all_working_directories_match": (
            working_directory_mismatch_count == 0
            and working_directory_unobserved_count == 0
        ),
        "configuration_ready": (
            missing_count == 0
            and all_wrappers_present
            and all_actions_observed
            and all_actions_match
            and all_schedules_observed
            and all_schedules_match
            and working_directory_mismatch_count == 0
            and working_directory_unobserved_count == 0
        ),
        "tasks": task_results,
    }


def _task_result(
    spec: Mapping[str, str],
    *,
    repo_root: Path,
    status: str,
    returncode: int | None = None,
    command_output_sha256: str | None = None,
    summary: Mapping[str, Any] | None = None,
    error: str | None = None,
    task_path: str | None = None,
    schtasks_explicit_missing: bool = False,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": spec["name"],
        "task_path": task_path or f"\\{spec['name']}",
        "schedule": spec["schedule"],
        "required": spec["required"] == "true",
        "status": status,
    }
    wrapper = _wrapper_info(spec["name"], repo_root)
    payload.update(wrapper)
    payload["action_matches_wrapper"] = _action_matches_wrapper(
        summary if summary else None,
        repo_root=repo_root,
        wrapper_path=wrapper.get("wrapper_path"),
    )
    payload["schedule_matches"] = _schedule_matches(
        summary,
        expected_schedule=spec.get("schedule"),
    )
    if returncode is not None:
        payload["returncode"] = returncode
    if command_output_sha256:
        payload["command_output_sha256"] = command_output_sha256
    if summary:
        payload["summary"] = dict(summary)
    if error:
        payload["error"] = error[:500]
    if schtasks_explicit_missing:
        payload["schtasks_reported_missing"] = True
    return payload


def _wrapper_info(task_name: str, repo_root: Path) -> dict[str, Any]:
    relative_path = TASK_WRAPPER_PATHS.get(task_name)
    if relative_path is None:
        return {
            "wrapper_path": None,
            "wrapper_status": "unconfigured",
            "wrapper_exists": False,
        }
    target = repo_root / Path(relative_path)
    try:
        if not target.is_file():
            return {
                "wrapper_path": relative_path,
                "wrapper_status": "missing",
                "wrapper_exists": False,
            }
        return {
            "wrapper_path": relative_path,
            "wrapper_status": "present",
            "wrapper_exists": True,
            "wrapper_sha256": _sha256_file(target),
        }
    except OSError as error:
        return {
            "wrapper_path": relative_path,
            "wrapper_status": "unreadable",
            "wrapper_exists": False,
            "wrapper_error": type(error).__name__,
        }


def _action_matches_wrapper(
    summary: Mapping[str, Any] | None,
    *,
    repo_root: Path,
    wrapper_path: object,
) -> bool | None:
    action = summary.get("task_to_run") if summary else None
    actions = summary.get("actions") if summary else None
    action_values: list[str] = []
    if isinstance(action, str) and action.strip():
        action_values.append(_redact_sensitive_text(action))
    if isinstance(actions, list):
        if len(actions) != 1:
            return False
        for item in actions:
            if not isinstance(item, Mapping):
                continue
            parts = [item.get("command"), item.get("arguments"), item.get("working_directory")]
            action_values.append(" ".join(
                _redact_sensitive_text(value)
                for value in parts
                if isinstance(value, str) and value.strip()
            ))
    if not action_values:
        return None
    if not isinstance(wrapper_path, str) or not wrapper_path.strip():
        return False
    normalized_absolute = str((repo_root / Path(wrapper_path)).resolve()).replace("/", "\\").lower()
    normalized_relative = wrapper_path.replace("/", "\\").lower()
    return any(
        normalized_absolute in candidate.replace("/", "\\").replace('"', "").lower()
        or normalized_relative in candidate.replace("/", "\\").replace('"', "").lower()
        for candidate in action_values
    )


def _parse_list_summary(output: str) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for raw_line in output.splitlines():
        if ":" not in raw_line:
            continue
        key, value = raw_line.split(":", 1)
        normalized_key = key.strip().lower().replace(" ", "_")
        if normalized_key not in _SAFE_SUMMARY_KEYS:
            continue
        text = value.strip()
        if text:
            values[normalized_key] = _redact_sensitive_text(text)[:240]
    return values


def _schedule_matches(
    summary: Mapping[str, Any] | None,
    *,
    expected_schedule: object,
) -> bool | None:
    """比較 schtasks 實際 trigger；欄位缺失時回傳 None 而非猜測。"""

    if not summary or not isinstance(expected_schedule, str):
        return None
    trigger_count = summary.get("trigger_count")
    if trigger_count is not None:
        try:
            if int(trigger_count) != 1:
                return False
        except (TypeError, ValueError):
            return None
    com_trigger_count = summary.get("com_trigger_count")
    if com_trigger_count is not None:
        try:
            if int(com_trigger_count) != 1:
                return False
        except (TypeError, ValueError):
            return None
    if "random_delay" in summary and not _is_zero_duration(summary.get("random_delay")):
        return False
    if "com_random_delay" in summary and not _is_zero_duration(summary.get("com_random_delay")):
        return False
    parts = expected_schedule.split()
    if len(parts) != 2 and len(parts) != 3:
        return None
    expected_type = parts[0].lower()
    expected_offset = parts[-1] if len(parts) == 3 and parts[-1].startswith(("+", "-")) else None
    expected_time = parts[-2] if expected_offset else parts[-1]
    start_boundary = summary.get("start_boundary") if summary else None
    if isinstance(start_boundary, str):
        try:
            observed_boundary = datetime.fromisoformat(start_boundary.replace("Z", "+00:00"))
        except ValueError:
            return False
        offset = observed_boundary.strftime("%z")
        offset = f"{offset[:3]}:{offset[3:]}" if offset else ""
        schedule_type = str(summary.get("schedule_type", "")).lower()
        interval_matches = (
            str(summary.get("days_interval", "")) == "1"
            if expected_type == "daily"
            else str(summary.get("weeks_interval", "")) == "1"
            if expected_type == "weekly"
            else True
        )
        boundary_time_matches = (
            True if expected_offset else observed_boundary.strftime("%H:%M") == expected_time
        )
        matches = (
            expected_type in schedule_type
            and boundary_time_matches
            and interval_matches
        )
        if expected_type == "weekly":
            expected_day = parts[1].upper()
            observed_days = str(summary.get("days", "")).upper()
            matches = matches and expected_day in observed_days
        if expected_offset:
            if (
                not matches
                or observed_boundary.tzinfo is None
                or observed_boundary.utcoffset() is None
            ):
                return False
            com_boundary_text = summary.get("com_start_boundary")
            if not isinstance(com_boundary_text, str):
                return False
            try:
                com_boundary = datetime.fromisoformat(
                    com_boundary_text.replace("Z", "+00:00")
                )
            except ValueError:
                return False
            if (
                com_boundary.tzinfo is None
                or com_boundary.utcoffset() is None
                or com_boundary.astimezone(timezone.utc)
                != observed_boundary.astimezone(timezone.utc)
            ):
                return False
            try:
                expected_timezone = datetime.fromisoformat(
                    f"2000-01-01T00:00:00{expected_offset}"
                ).tzinfo
                if expected_timezone is None:
                    return False
                local_boundary = observed_boundary.astimezone(expected_timezone)
                expected_local_boundary = local_boundary.replace(
                    hour=int(expected_time[:2]),
                    minute=int(expected_time[3:]),
                    second=0,
                    microsecond=0,
                )
            except (ValueError, IndexError):
                return False
            return (
                local_boundary.strftime("%H:%M") == expected_time
                and local_boundary.second == 0
                and local_boundary.microsecond == 0
                and observed_boundary.astimezone(timezone.utc)
                == expected_local_boundary.astimezone(timezone.utc)
            )
        return matches and not offset
    if expected_offset:
        # schtasks LIST does not expose a trigger's explicit UTC offset.
        return None
    legacy_schedule_type = summary.get("schedule_type")
    start_time = summary.get("start_time")
    if not isinstance(legacy_schedule_type, str) or not legacy_schedule_type or not start_time:
        return None
    observed_type = legacy_schedule_type.strip().lower()
    if expected_type not in observed_type:
        return False
    observed_time = _normalise_start_time(str(start_time))
    if observed_time is None or observed_time != expected_time:
        return False
    if expected_type == "weekly":
        expected_day = parts[1].upper()
        observed_days = (summary.get("days") or "").upper()
        if expected_day not in observed_days:
            return False
    return True


def _query_com(
    *,
    runner,
    executable: str | None,
    task_paths: Sequence[str],
    timeout_seconds: int,
) -> dict[str, Any]:
    """使用受限的 Python helper 透過 Scheduler COM 查詢指定 root tasks。"""

    command = executable or os.environ.get("BALDR_COM_QUERY_PYTHON") or sys.executable
    arguments = [
        command,
        str(COM_QUERY_SCRIPT),
        "--task-paths-json",
        json.dumps(list(task_paths), separators=(",", ":")),
    ]
    try:
        completed = runner(
            arguments,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            check=False,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired) as error:
        return {
            "status": "query_error",
            "error": type(error).__name__,
        }
    stdout = str(getattr(completed, "stdout", "") or "")
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        return {
            "status": "query_error",
            "error": "invalid_com_json",
            "returncode": int(getattr(completed, "returncode", 1)),
        }
    if not isinstance(payload, Mapping) or payload.get("schema_version") != "scheduler-com-query.v1":
        return {"status": "query_error", "error": "invalid_com_payload"}
    if payload.get("status") != "available" or not isinstance(payload.get("tasks"), list):
        return {
            "status": "query_error",
            "error": _safe_error_label(payload.get("error") or "com_query_unavailable"),
        }
    return {"status": "available", "tasks": payload["tasks"]}


def _merge_com_details(
    task_results: list[dict[str, Any]],
    com_report: Mapping[str, Any],
    repo_root: Path,
) -> None:
    """以 COM 精確欄位補強 schtasks；無法查詢時維持 unknown 語意。"""

    if com_report.get("status") != "available":
        for item in task_results:
            item["com_query_status"] = "unknown"
            item["com_query_error"] = _safe_error_label(
                com_report.get("error") or "com_query_failed"
            )
            if item.get("status") == "unknown" and item.get("schtasks_reported_missing"):
                item["status"] = "unknown"
        return
    com_tasks = {
        value.get("task_path"): value
        for value in com_report.get("tasks", [])
        if isinstance(value, Mapping) and isinstance(value.get("task_path"), str)
    }
    for item in task_results:
        detail = com_tasks.get(item["task_path"])
        item["com_query_status"] = (
            str(detail.get("status")) if detail is not None else "unknown"
        )
        if detail is None:
            continue
        detail_status = detail.get("status")
        if detail_status == "missing":
            if item.get("status") != "available":
                item["status"] = "missing"
            item["com_confirmed_missing"] = True
            continue
        if detail_status != "available":
            item["com_query_error"] = _safe_error_label(
                detail.get("error") or "com_task_detail_unavailable"
            )
            continue
        item["status"] = "available"
        item["scheduler_state"] = detail.get("state")
        item["scheduler_state_code"] = detail.get("state_code")
        item["last_run_time"] = detail.get("last_run_time")
        item["last_task_result"] = detail.get("last_task_result")
        item["last_task_result_hex"] = detail.get("last_task_result_hex")
        item["next_run_time"] = detail.get("next_run_time")
        item["missed_run_count"] = detail.get("missed_run_count")
        item["actions"] = _sanitize_actions(detail.get("actions", []))
        item["action_count"] = detail.get("action_count", len(item["actions"]))
        item["trigger_count"] = detail.get("trigger_count")
        item["working_directories"] = [
            action.get("working_directory")
            for action in item["actions"]
            if isinstance(action, Mapping) and action.get("working_directory")
        ]
        item["execution_time_limit"] = detail.get("execution_time_limit")
        item["restart_count"] = detail.get("restart_count")
        item["restart_interval"] = detail.get("restart_interval")
        item["multiple_instances_policy"] = detail.get("multiple_instances_policy")
        item["start_when_available"] = detail.get("start_when_available")
        item["random_delay"] = detail.get("random_delay")
        item["enabled"] = detail.get("enabled")
        item["power_policy"] = detail.get("power_policy")
        item["start_boundary"] = detail.get("start_boundary")
        item["com_start_boundary"] = detail.get("com_start_boundary")
        item["com_random_delay"] = detail.get("com_random_delay")
        item["com_trigger_count"] = detail.get("com_trigger_count")
        item["schedule_type"] = detail.get("schedule_type")
        item["days_interval"] = detail.get("days_interval")
        item["days"] = detail.get("days")
        item["schedule_matches"] = _schedule_matches(
            detail,
            expected_schedule=item.get("schedule"),
        )
        item["action_matches_wrapper"] = _action_matches_wrapper(
            {"actions": item["actions"]},
            repo_root=repo_root,
            wrapper_path=item.get("wrapper_path"),
        )
        item["working_directory_matches_repo_root"] = (
            all(
                str(path).replace("/", "\\").lower()
                == str(repo_root).replace("/", "\\").lower()
                for path in item["working_directories"]
            )
            if item["working_directories"]
            else None
        )


def _is_explicit_not_found(returncode: int, output: str) -> bool:
    if returncode == 0:
        return False
    lowered = output.lower()
    explicit_messages = (
        "the system cannot find the file specified",
        "cannot find the task",
        "task not found",
        "task does not exist",
    )
    return any(message in lowered for message in explicit_messages)


def _safe_query_error(value: str) -> str | None:
    """Save a stable error category without echoing localized account/path text."""

    text = _compact_error(value)
    if not text:
        return None
    lowered = text.lower()
    if "access is denied" in lowered or "access denied" in lowered:
        return "access_denied"
    if _is_explicit_not_found(1, text):
        return "task_not_found_reported_by_schtasks"
    if "task scheduler service" in lowered and "not available" in lowered:
        return "scheduler_service_unavailable"
    return "query_failed"


def _safe_error_label(value: object) -> str:
    """Allow only a short type/code label from an external query response."""

    text = str(value)
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]{0,79}", text):
        return text
    if re.fullmatch(r"0x[0-9A-Fa-f]{8}", text):
        return text
    return "query_failed"


def _sanitize_actions(value: object) -> list[dict[str, str | None]]:
    if not isinstance(value, list):
        return []
    sanitized: list[dict[str, str | None]] = []
    for action in value[:16]:
        if not isinstance(action, Mapping):
            continue
        row: dict[str, str | None] = {}
        for key in ("type", "command", "arguments", "working_directory"):
            raw = action.get(key)
            row[key] = (
                _redact_sensitive_text(raw)[:2_048]
                if isinstance(raw, str)
                else None
            )
        sanitized.append(row)
    return sanitized


_DURATION_RE = re.compile(
    r"^P(?:(?P<days>\d+(?:\.\d+)?)D)?(?:T(?:(?P<hours>\d+(?:\.\d+)?)H)?"
    r"(?:(?P<minutes>\d+(?:\.\d+)?)M)?(?:(?P<seconds>\d+(?:\.\d+)?)S)?)?$",
    re.IGNORECASE,
)


def _is_zero_duration(value: object) -> bool:
    """Treat omitted/default or any valid all-zero ISO duration as zero."""

    if value is None or (isinstance(value, str) and not value.strip()):
        return True
    match = _DURATION_RE.fullmatch(str(value).strip())
    if match is None:
        return False
    components = match.groupdict()
    if not any(components.values()):
        return False
    try:
        return all(
            Decimal(amount) == 0
            for amount in components.values()
            if amount is not None
        )
    except InvalidOperation:
        return False


def _redact_sensitive_text(value: str) -> str:
    redacted = _SENSITIVE_ARGUMENT_RE.sub(r"\1<redacted>", value)
    redacted = _ACCOUNT_ARGUMENT_RE.sub(r"\1<account-redacted>", redacted)
    return _SID_RE.sub("<sid-redacted>", redacted)


def _normalise_start_time(value: str) -> str | None:
    """將中英文 Windows locale 的 Start Time 轉成 24 小時 HH:MM。"""

    import re

    match = re.search(r"(?<!\d)(\d{1,2}):(\d{2})(?::\d{2})?", value)
    if match is None:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2))
    lower = value.lower()
    if any(marker in value for marker in ("下午", "午後")) or "pm" in lower:
        if hour < 12:
            hour += 12
    elif any(marker in value for marker in ("上午", "午前")) or "am" in lower:
        if hour == 12:
            hour = 0
    if hour > 23 or minute > 59:
        return None
    return f"{hour:02d}:{minute:02d}"


def _compact_error(value: str) -> str | None:
    text = " ".join(value.split())
    return text[:500] if text else None


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve_repo_root(value: str | Path | None) -> Path:
    candidate = value or os.environ.get("BALDR_SCHEDULED_REPO_ROOT") or PROJECT_ROOT
    try:
        return Path(candidate).expanduser().resolve()
    except (OSError, RuntimeError, TypeError, ValueError):
        return Path(candidate).expanduser().absolute()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", default=None, help="schtasks executable; defaults to BALDR_SCHTASKS_EXE")
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument(
        "--com-python-executable",
        default=None,
        help="Python executable used by the read-only Task Scheduler COM fallback",
    )
    parser.add_argument("--repo-root", type=Path, help="repository root used to verify scheduled wrapper files")
    parser.add_argument("--output", type=Path, help="optional JSON output path")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    _configure_utf8_stdio()
    args = build_parser().parse_args(argv)
    report = inspect_scheduled_task_registration(
        executable=args.executable,
        timeout_seconds=args.timeout_seconds,
        com_python_executable=args.com_python_executable,
        repo_root=args.repo_root,
    )
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0 if report["all_available"] else 1


def _configure_utf8_stdio() -> None:
    """讓 Windows CP1252 主控台也能安全輸出繁中說明與診斷。"""

    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if not callable(reconfigure):
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            continue


if __name__ == "__main__":
    raise SystemExit(main())
