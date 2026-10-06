"""Read exact root BALDR task details through Windows Task Scheduler COM.

The command is read-only. It enumerates the root folder once, returns only the
allowlisted task paths passed on its command line, and never emits principal
UserId or a security descriptor.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import re
import sys
from typing import Any, Sequence
import xml.etree.ElementTree as ET


SCHEMA_VERSION = "scheduler-com-query.v1"
TASK_PATH_RE = re.compile(r"^\\baldr-[a-z0-9-]+$", re.IGNORECASE)
TASK_ENUM_HIDDEN = 0x1
SENSITIVE_ARGUMENT_RE = re.compile(
    r"(?i)((?:--?|/)(?:password|passwd|token|secret|api[-_]?key|client[-_]?secret)"
    r"(?:\s+|\s*=\s*|=)|(?:password|passwd|token|secret|api[_-]?key)\s*=\s*)"
    r"(\"[^\"]*\"|'[^']*'|[^\s]+)"
)
ACCOUNT_ARGUMENT_RE = re.compile(
    r"(?i)((?:--?|/)(?:user(?:name)?|account|run-as)(?:\s+|\s*=\s*|=)"
    r"|(?:user(?:name)?|account)\s*=\s*)(\"[^\"]*\"|'[^']*'|[^\s]+)"
)
SID_RE = re.compile(r"\bS-1-(?:\d+-){2,}\d+\b", re.IGNORECASE)


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _child_text(element: ET.Element, name: str) -> str | None:
    for child in element.iter():
        if _local_name(child.tag) == name and child.text:
            return child.text.strip()
    return None


def _safe_arguments(value: str | None) -> str | None:
    if value is None:
        return None
    redacted = SENSITIVE_ARGUMENT_RE.sub(r"\1<redacted>", value)
    redacted = ACCOUNT_ARGUMENT_RE.sub(r"\1<account-redacted>", redacted)
    return SID_RE.sub("<sid-redacted>", redacted)


def _state_name(value: int) -> str:
    return {
        0: "unknown",
        1: "disabled",
        2: "queued",
        3: "ready",
        4: "running",
    }.get(value, "unknown")


def _multiple_instances_name(value: int) -> str:
    return {
        0: "Parallel",
        1: "Queue",
        2: "IgnoreNew",
        3: "StopExisting",
    }.get(value, "unknown")


def _time_text(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.year < 1900:
            return None
        # Task Scheduler's COM DATE values represent host-local wall time.
        # pywin32 may attach a UTC tzinfo even when the components are local;
        # dropping that marker avoids presenting a false UTC instant.
        return value.replace(tzinfo=None).isoformat(timespec="seconds")
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return text
    if parsed.year < 1900:
        return None
    return parsed.replace(tzinfo=None).isoformat(timespec="seconds")


def _trigger_details(root: ET.Element) -> list[dict[str, object]]:
    triggers_root = next(
        (node for node in root.iter() if _local_name(node.tag) == "Triggers"),
        None,
    )
    if triggers_root is None:
        return []
    output: list[dict[str, object]] = []
    for trigger in list(triggers_root):
        trigger_type = _local_name(trigger.tag)
        schedule_type = trigger_type
        if trigger_type == "CalendarTrigger":
            child_names = {_local_name(node.tag) for node in trigger.iter()}
            if "ScheduleByDay" in child_names:
                schedule_type = "Daily"
            elif "ScheduleByWeek" in child_names:
                schedule_type = "Weekly"
            elif "ScheduleByMonth" in child_names:
                schedule_type = "Monthly"
        days_of_week: list[str] = []
        for node in trigger.iter():
            if _local_name(node.tag) == "DaysOfWeek":
                days_of_week = [
                    _local_name(child.tag)
                    for child in list(node)
                    if _local_name(child.tag)
                ]
                break
        output.append(
            {
                "type": trigger_type,
                "schedule_type": schedule_type,
                "start_boundary": _child_text(trigger, "StartBoundary"),
                "enabled": _child_text(trigger, "Enabled"),
                "random_delay": _child_text(trigger, "RandomDelay") or "PT0S",
                "days_interval": _child_text(trigger, "DaysInterval"),
                "weeks_interval": _child_text(trigger, "WeeksInterval"),
                "days": ",".join(days_of_week),
            }
        )
    return output


def _action_details(root: ET.Element) -> list[dict[str, str | None]]:
    actions_root = next(
        (node for node in root.iter() if _local_name(node.tag) == "Actions"),
        None,
    )
    if actions_root is None:
        return []
    output: list[dict[str, str | None]] = []
    for action in list(actions_root):
        output.append(
            {
                "type": _local_name(action.tag),
                "command": _child_text(action, "Command"),
                "arguments": _safe_arguments(_child_text(action, "Arguments")),
                "working_directory": _child_text(action, "WorkingDirectory"),
            }
        )
    return output


def _task_details(task: Any) -> dict[str, object]:
    xml_text = str(task.Xml)
    xml_root = ET.fromstring(xml_text)
    definition = task.Definition
    settings = definition.Settings
    triggers = _trigger_details(xml_root)
    actions = _action_details(xml_root)
    trigger_collection = definition.Triggers
    com_trigger_count = int(trigger_collection.Count)
    com_start_boundary: str | None = None
    com_random_delay: str | None = None
    if com_trigger_count == 1:
        com_trigger = trigger_collection.Item(1)
        raw_boundary = com_trigger.StartBoundary
        raw_random_delay = com_trigger.RandomDelay
        com_start_boundary = str(raw_boundary) if raw_boundary is not None else None
        com_random_delay = (
            "" if raw_random_delay is None else str(raw_random_delay)
        )
    first_trigger = triggers[0] if triggers else {}
    try:
        state_code = int(task.State)
    except (TypeError, ValueError):
        state_code = 0
    try:
        result: int | None = int(task.LastTaskResult)
    except (TypeError, ValueError):
        result = None
    unsigned_result = result & 0xFFFF_FFFF if result is not None else None
    power_policy = {
        "disallow_start_if_on_batteries": bool(settings.DisallowStartIfOnBatteries),
        "stop_if_going_on_batteries": bool(settings.StopIfGoingOnBatteries),
    }
    return {
        "task_path": str(task.Path),
        "status": "available",
        "state": _state_name(state_code),
        "state_code": state_code,
        "enabled": bool(task.Enabled),
        "last_run_time": _time_text(task.LastRunTime),
        "last_task_result": result,
        "last_task_result_hex": f"0x{unsigned_result:08X}" if unsigned_result is not None else None,
        "next_run_time": _time_text(task.NextRunTime),
        "missed_run_count": int(task.NumberOfMissedRuns),
        "actions": actions,
        "action_count": len(actions),
        "triggers": triggers,
        "trigger_count": len(triggers),
        "com_trigger_count": com_trigger_count,
        "com_start_boundary": com_start_boundary,
        "com_random_delay": com_random_delay,
        "start_boundary": first_trigger.get("start_boundary"),
        "schedule_type": first_trigger.get("schedule_type", "unknown"),
        "days_interval": first_trigger.get("days_interval"),
        "weeks_interval": first_trigger.get("weeks_interval"),
        "days": first_trigger.get("days", ""),
        "random_delay": first_trigger.get("random_delay", "PT0S"),
        "execution_time_limit": str(settings.ExecutionTimeLimit),
        "restart_count": int(settings.RestartCount),
        "restart_interval": str(settings.RestartInterval),
        "multiple_instances_policy": _multiple_instances_name(
            int(settings.MultipleInstances)
        ),
        "start_when_available": bool(settings.StartWhenAvailable),
        "power_policy": power_policy,
        "scheduler_time_basis": "last_run_time and next_run_time are host-local wall-clock ISO values without offset; COM StartBoundary is retained separately from the XML boundary",
    }


def query_tasks(
    task_paths: Sequence[str],
    *,
    service_factory: Any | None = None,
) -> dict[str, object]:
    """Read only the allowlisted root tasks from one successful enumeration."""

    paths = list(task_paths)
    if not paths or any(not isinstance(path, str) or not TASK_PATH_RE.fullmatch(path) for path in paths):
        return {
            "schema_version": SCHEMA_VERSION,
            "status": "query_error",
            "error": "invalid_task_paths_parameter",
        }
    pythoncom_module: Any | None = None
    try:
        if service_factory is None:
            import pythoncom
            import win32com.client

            pythoncom.CoInitialize()
            pythoncom_module = pythoncom
            service = win32com.client.Dispatch("Schedule.Service")
        else:
            service = service_factory()
        service.Connect()
        root_folder = service.GetFolder("\\")
        registered_tasks = root_folder.GetTasks(TASK_ENUM_HIDDEN)
        by_path: dict[str, Any] = {}
        for index in range(1, int(registered_tasks.Count) + 1):
            task = registered_tasks.Item(index)
            path = str(task.Path)
            if path in paths:
                by_path[path] = task
        rows: list[dict[str, object]] = []
        for path in paths:
            task = by_path.get(path)
            if task is None:
                rows.append({"task_path": path, "status": "missing"})
                continue
            try:
                rows.append(_task_details(task))
            except Exception as error:  # COM per-task failure must not imply missing
                rows.append(
                    {
                        "task_path": path,
                        "status": "detail_error",
                        "error": type(error).__name__,
                    }
                )
        return {"schema_version": SCHEMA_VERSION, "status": "available", "tasks": rows}
    except Exception as error:  # noqa: BLE001 - do not expose raw COM exception text
        hresult = getattr(error, "hresult", None)
        if hresult is None:
            hresult = getattr(error, "winerror", None)
        payload: dict[str, object] = {
            "schema_version": SCHEMA_VERSION,
            "status": "query_error",
            "error": type(error).__name__,
        }
        if isinstance(hresult, int):
            payload["hresult"] = f"0x{(hresult & 0xFFFF_FFFF):08X}"
        return payload
    finally:
        if pythoncom_module is not None:
            # Release apartment-owned interfaces before CoUninitialize. Keeping
            # task wrappers alive here made IUnknown cleanup pollute JSON stdout.
            import gc
            task = None
            if "by_path" in locals():
                by_path.clear()
            registered_tasks = None
            root_folder = None
            service = None
            gc.collect()
            pythoncom_module.CoUninitialize()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-paths-json", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        task_paths = json.loads(args.task_paths_json)
    except json.JSONDecodeError:
        report: dict[str, object] = {
            "schema_version": SCHEMA_VERSION,
            "status": "query_error",
            "error": "invalid_task_paths_parameter",
        }
    else:
        if isinstance(task_paths, list):
            report = query_tasks(task_paths)
        else:
            report = {
                "schema_version": SCHEMA_VERSION,
                "status": "query_error",
                "error": "invalid_task_paths_parameter",
            }
    sys.stdout.write(json.dumps(report, ensure_ascii=False, separators=(",", ":")) + "\n")
    return 0 if report.get("status") == "available" else 2


if __name__ == "__main__":
    raise SystemExit(main())
