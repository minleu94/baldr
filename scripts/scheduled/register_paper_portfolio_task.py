"""Safely update only the existing Paper Portfolio task through Scheduler COM.

The CLI keeps ``dryrun|register`` compatibility with the CMD wrapper. The
default daily boundary is timezone-aware Asia/Taipei 08:25 (+08:00); callers
can explicitly request a host-local time or execution-time-limit override.
"""

from __future__ import annotations

import argparse
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from typing import Any, Sequence
from uuid import uuid4
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[2]
TASK_NAME = "baldr-paper-portfolio-daily"
TASK_PATH = f"\\{TASK_NAME}"
TASK_UPDATE = 0x4
TASK_DONT_ADD_PRINCIPAL_ACE = 0x10
TASK_IGNORE_REGISTRATION_TRIGGERS = 0x20
WRAPPER_RELATIVE_PATH = Path("scripts/scheduled/run_paper_portfolio_daily.cmd")
TAIPEI_OFFSET = timezone(timedelta(hours=8), name="Asia/Taipei")
CUSTOM_TIME_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")
XML_DECLARATION_RE = re.compile(r"^\s*<\?xml\s+.*?\?>", re.IGNORECASE | re.DOTALL)
DURATION_RE = re.compile(
    r"^P(?:(?P<days>\d+(?:\.\d+)?)D)?(?:T(?:(?P<hours>\d+(?:\.\d+)?)H)?"
    r"(?:(?P<minutes>\d+(?:\.\d+)?)M)?(?:(?P<seconds>\d+(?:\.\d+)?)S)?)?$",
    re.IGNORECASE,
)


class RegistrationError(RuntimeError):
    """The exact existing task does not satisfy the registration contract."""


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _duration_seconds_decimal(value: str) -> Decimal:
    # Accept a bounded ISO-8601 day/time duration subset supported by Task
    # Scheduler. The value is written only after exact syntax validation.
    match = DURATION_RE.fullmatch(value)
    if match is None or not any(match.groupdict().values()):
        raise ValueError("duration must be an ISO 8601 duration")
    try:
        seconds = (
            Decimal(match.group("days") or 0) * 86_400
            + Decimal(match.group("hours") or 0) * 3_600
            + Decimal(match.group("minutes") or 0) * 60
            + Decimal(match.group("seconds") or 0)
        )
    except InvalidOperation as error:
        raise ValueError("duration must be an ISO 8601 duration") from error
    return seconds


def _duration_seconds(value: str) -> Decimal:
    seconds = _duration_seconds_decimal(value)
    if seconds <= 0:
        raise ValueError("duration must be positive")
    return seconds


def _is_zero_duration(value: object) -> bool:
    if value is None or (isinstance(value, str) and not value.strip()):
        return True
    try:
        return _duration_seconds_decimal(str(value).strip()) == 0
    except ValueError:
        return False


def _xml_backup_bytes(xml_text: str) -> bytes:
    """Normalize the declaration and bytes together for a parseable UTF-16 backup."""

    text = xml_text.lstrip("\ufeff")
    declaration_match = XML_DECLARATION_RE.match(text)
    if declaration_match is None:
        text = '<?xml version="1.0" encoding="UTF-16"?>\n' + text
    else:
        declaration = declaration_match.group(0)
        if re.search(r"\bencoding\s*=", declaration, re.IGNORECASE):
            declaration = re.sub(
                r"(\bencoding\s*=\s*)(['\"])[^'\"]*\2",
                r'\1"UTF-16"',
                declaration,
                count=1,
                flags=re.IGNORECASE,
            )
        else:
            declaration = declaration[:-2] + ' encoding="UTF-16"?>'
        text = declaration + text[declaration_match.end():]
    return text.encode("utf-16")


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _xml_child_text(element: ET.Element, name: str) -> str | None:
    for child in element.iter():
        if _local_name(child.tag) == name and child.text is not None:
            return child.text.strip()
    return None


def _parse_task_timing_xml(xml_text: str) -> dict[str, object] | None:
    try:
        xml_body = XML_DECLARATION_RE.sub("", xml_text.lstrip("\ufeff"), count=1)
        root = ET.fromstring(xml_body)
    except (ET.ParseError, ValueError):
        return None
    triggers_root = next(
        (node for node in root.iter() if _local_name(node.tag) == "Triggers"),
        None,
    )
    if triggers_root is None or len(list(triggers_root)) != 1:
        return None
    trigger = list(triggers_root)[0]
    if _local_name(trigger.tag) != "CalendarTrigger":
        return None
    schedule_by_day = next(
        (node for node in trigger.iter() if _local_name(node.tag) == "ScheduleByDay"),
        None,
    )
    if schedule_by_day is None:
        return None
    days_interval = _xml_child_text(schedule_by_day, "DaysInterval")
    return {
        "start_boundary": _xml_child_text(trigger, "StartBoundary"),
        "days_interval": days_interval,
        "random_delay": _xml_child_text(trigger, "RandomDelay") or "",
    }


def _parse_boundary(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None


def _scheduler_host_local_wall_time(value: object) -> str | None:
    """Format COM DATE values as host-local wall time without a false offset."""

    if value is None:
        return None
    if isinstance(value, datetime):
        if value.year < 1900:
            return None
        return value.replace(tzinfo=None).isoformat(timespec="seconds")
    text = str(value).strip()
    if not text:
        return None
    parsed = _parse_boundary(text)
    if parsed is not None:
        return parsed.replace(tzinfo=None).isoformat(timespec="seconds")
    return text


def _verify_trigger_readback(
    *,
    expected_boundary: str,
    com_boundary: object,
    com_random_delay: object,
    task_xml: str,
    custom_user_local_time: bool,
) -> dict[str, object]:
    """Verify both COM's instant and the XML recurrence/time-basis contract."""

    xml_details = _parse_task_timing_xml(task_xml)
    xml_boundary_text = xml_details.get("start_boundary") if xml_details else None
    xml_boundary = _parse_boundary(xml_boundary_text)
    expected = _parse_boundary(expected_boundary)
    com_value = str(com_boundary) if com_boundary is not None else None
    com_parsed = _parse_boundary(com_value)
    xml_delay = xml_details.get("random_delay") if xml_details else None

    if custom_user_local_time:
        instant_matches = (
            expected is not None
            and expected.tzinfo is None
            and com_parsed is not None
            and com_parsed.replace(tzinfo=None) == expected
            and xml_boundary is not None
            and xml_boundary.tzinfo is None
            and xml_boundary == expected
        )
        recurrence_matches = (
            xml_details is not None
            and xml_details.get("days_interval") == "1"
        )
    else:
        expected_offset = expected.utcoffset() if expected is not None else None
        com_offset = com_parsed.utcoffset() if com_parsed is not None else None
        xml_offset = xml_boundary.utcoffset() if xml_boundary is not None else None
        expected_taipei = (
            expected.astimezone(TAIPEI_OFFSET) if expected is not None else None
        )
        xml_taipei = (
            xml_boundary.astimezone(TAIPEI_OFFSET)
            if xml_boundary is not None and xml_offset is not None
            else None
        )
        instant_matches = (
            expected is not None
            and expected_offset == timedelta(hours=8)
            and expected_taipei is not None
            and expected_taipei.strftime("%H:%M") == "08:25"
            and expected_taipei.second == 0
            and expected_taipei.microsecond == 0
            and com_parsed is not None
            and com_offset is not None
            and com_parsed.astimezone(timezone.utc) == expected.astimezone(timezone.utc)
            and xml_boundary is not None
            and xml_offset is not None
            and xml_boundary.astimezone(timezone.utc) == expected.astimezone(timezone.utc)
        )
        recurrence_matches = (
            xml_details is not None
            and xml_details.get("days_interval") == "1"
            and xml_taipei is not None
            and xml_taipei.strftime("%H:%M") == "08:25"
            and xml_taipei.second == 0
            and xml_taipei.microsecond == 0
        )

    delay_matches = _is_zero_duration(com_random_delay) and _is_zero_duration(xml_delay)
    return {
        "verified": bool(instant_matches and recurrence_matches and delay_matches),
        "expected_start_boundary": expected_boundary,
        "com_start_boundary": com_value,
        "xml_start_boundary": xml_boundary_text,
        "com_boundary_utc": (
            com_parsed.astimezone(timezone.utc).isoformat(timespec="seconds")
            if com_parsed is not None and com_parsed.utcoffset() is not None
            else None
        ),
        "xml_boundary_utc": (
            xml_boundary.astimezone(timezone.utc).isoformat(timespec="seconds")
            if xml_boundary is not None and xml_boundary.utcoffset() is not None
            else None
        ),
        "xml_boundary_taipei": (
            xml_boundary.astimezone(TAIPEI_OFFSET).isoformat(timespec="seconds")
            if xml_boundary is not None and xml_boundary.utcoffset() is not None
            else None
        ),
        "expected_boundary_utc": (
            expected.astimezone(timezone.utc).isoformat(timespec="seconds")
            if expected is not None and expected.utcoffset() is not None
            else None
        ),
        "com_random_delay": None if com_random_delay is None else str(com_random_delay),
        "xml_random_delay": xml_delay,
        "daily_interval": xml_details.get("days_interval") if xml_details else None,
        "recurrence_timezone": (
            "host-local explicit override"
            if custom_user_local_time
            else "Asia/Taipei 08:25 validated through aware UTC instant"
        ),
    }


def _next_start_boundary(
    *,
    custom_user_local_time: str | None = None,
    now_utc: datetime | None = None,
) -> tuple[str, str, str]:
    """Return boundary text, display schedule, and timezone mapping."""

    if custom_user_local_time:
        if CUSTOM_TIME_RE.fullmatch(custom_user_local_time) is None:
            raise ValueError("custom user-local time must use HH:mm")
        hour, minute = (int(part) for part in custom_user_local_time.split(":"))
        now_local = (now_utc or datetime.now(timezone.utc)).astimezone()
        target = now_local.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= now_local:
            target = (target + timedelta(days=1)).replace(hour=hour, minute=minute)
        return (
            target.replace(tzinfo=None).isoformat(timespec="seconds"),
            f"DAILY custom user-local {custom_user_local_time}",
            "Host-local override explicitly requested",
        )

    now_taipei = (now_utc or datetime.now(timezone.utc)).astimezone(TAIPEI_OFFSET)
    target = datetime.combine(now_taipei.date(), time(8, 25), tzinfo=TAIPEI_OFFSET)
    if now_taipei >= target:
        target += timedelta(days=1)
    return (
        target.isoformat(timespec="seconds"),
        "DAILY Asia/Taipei 08:25 (+08:00)",
        "00:25 UTC; 17:25 PDT / 16:25 PST on previous Pacific calendar date",
    )


def _windows_timezone_name() -> str | None:
    try:
        completed = subprocess.run(
            ["tzutil.exe", "/g"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return completed.stdout.strip() if completed.returncode == 0 else None


def _make_service() -> Any:
    try:
        import pythoncom
        import win32com.client
    except ImportError as error:
        raise RegistrationError("pywin32_not_available") from error
    pythoncom.CoInitialize()
    service: Any | None = None
    try:
        service = win32com.client.Dispatch("Schedule.Service")
        service.Connect()
        return service
    except Exception:
        service = None
        pythoncom.CoUninitialize()
        raise


def _save_before_backup(
    *,
    xml_text: str,
    enabled: bool,
    execution_time_limit: str,
    backup_root: Path,
) -> dict[str, str]:
    backup_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    stem = f"{TASK_NAME}_{stamp}_{uuid4().hex[:12]}"
    xml_path = backup_root / f"{stem}.xml"
    metadata_path = backup_root / f"{stem}.json"
    xml_bytes = _xml_backup_bytes(xml_text)
    with xml_path.open("xb") as stream:
        stream.write(xml_bytes)
        stream.flush()
        os.fsync(stream.fileno())
    xml_sha256 = _sha256(xml_bytes)
    metadata: dict[str, str | bool] = {
        "schema_version": "paper-task-before-backup.v1",
        "task_path": TASK_PATH,
        "enabled": enabled,
        "execution_time_limit": execution_time_limit,
        "xml_sha256": xml_sha256,
    }
    with metadata_path.open("xb") as stream:
        stream.write((json.dumps(metadata, sort_keys=True, indent=2) + "\n").encode("utf-8"))
        stream.flush()
        os.fsync(stream.fileno())
    return {
        "xml_path": str(xml_path),
        "metadata_path": str(metadata_path),
        "xml_sha256": xml_sha256,
    }


def dryrun(
    *,
    repo_root: Path,
    custom_user_local_time: str | None = None,
    execution_time_limit_override: str | None = None,
) -> dict[str, object]:
    if execution_time_limit_override:
        _duration_seconds(execution_time_limit_override)
    root = repo_root.expanduser().resolve()
    wrapper = root / WRAPPER_RELATIVE_PATH
    if not wrapper.is_file():
        raise RegistrationError("paper_wrapper_missing")
    boundary, schedule, mapping = _next_start_boundary(
        custom_user_local_time=custom_user_local_time
    )
    return {
        "mode": "dryrun",
        "task_path": TASK_PATH,
        "schedule": schedule,
        "start_boundary": boundary,
        "mapping": mapping,
        "cutoff": "on-time scheduled invocation waits five minutes for real Asia/Taipei 08:30",
        "multiple_instances": "IgnoreNew",
        "random_delay": "PT0S",
        "start_when_available": False,
        "execution_time_limit": (
            execution_time_limit_override or "preserve existing Scheduler value"
        ),
        "working_directory": str(root),
        "action": f'cmd.exe /c "{wrapper}"',
        "principal_policy": "preserve existing InteractiveToken / LeastPrivilege principal",
        "battery_policy": "preserve existing battery restrictions",
        "task_modified": False,
    }


def register_existing_task(
    *,
    repo_root: Path,
    backup_root: Path,
    custom_user_local_time: str | None = None,
    execution_time_limit_override: str | None = None,
    service_factory: Any | None = None,
) -> dict[str, object]:
    if execution_time_limit_override:
        _duration_seconds(execution_time_limit_override)
    if custom_user_local_time and _windows_timezone_name() != "Pacific Standard Time":
        raise RegistrationError("custom_user_local_time_requires_Pacific_Standard_Time")

    root = repo_root.expanduser().resolve()
    wrapper = root / WRAPPER_RELATIVE_PATH
    if not wrapper.is_file():
        raise RegistrationError("paper_wrapper_missing")
    boundary, schedule, mapping = _next_start_boundary(
        custom_user_local_time=custom_user_local_time
    )
    # COM proxy references are initialized up front so every exit path can
    # release them before CoUninitialize tears down this thread's apartment.
    service: Any | None = None
    folder: Any | None = None
    task: Any | None = None
    definition: Any | None = None
    principal: Any | None = None
    settings: Any | None = None
    trigger_collection: Any | None = None
    action_collection: Any | None = None
    trigger: Any | None = None
    action: Any | None = None
    after_task: Any | None = None
    after_definition: Any | None = None
    after_trigger: Any | None = None
    after_action: Any | None = None
    after_settings: Any | None = None
    service = service_factory() if service_factory is not None else _make_service()
    try:
        if service_factory is not None:
            service.Connect()
        folder = service.GetFolder("\\")
        try:
            task = folder.GetTask(TASK_NAME)
        except Exception as error:
            raise RegistrationError("existing_root_task_unavailable; no task created") from error
        if str(task.Path) != TASK_PATH:
            raise RegistrationError("scheduler_returned_different_task_path")

        definition = task.Definition
        principal = definition.Principal
        settings = definition.Settings
        trigger_collection = definition.Triggers
        action_collection = definition.Actions
        if int(principal.LogonType) != 3 or int(principal.RunLevel) != 0:
            raise RegistrationError("existing_principal_must_be_InteractiveToken_LeastPrivilege")
        if not bool(settings.DisallowStartIfOnBatteries) or not bool(settings.StopIfGoingOnBatteries):
            raise RegistrationError("existing_battery_restrictions_do_not_match_required_policy")
        if int(trigger_collection.Count) != 1 or int(trigger_collection.Item(1).Type) != 2:
            raise RegistrationError("expected_exactly_one_daily_trigger")
        if int(action_collection.Count) != 1 or int(action_collection.Item(1).Type) != 0:
            raise RegistrationError("expected_exactly_one_exec_action")

        before_xml = str(task.Xml)
        before_enabled = bool(task.Enabled)
        before_timeout = str(settings.ExecutionTimeLimit)
        before_retry_count = int(settings.RestartCount)
        before_retry_interval = str(settings.RestartInterval)
        backup = _save_before_backup(
            xml_text=before_xml,
            enabled=before_enabled,
            execution_time_limit=before_timeout,
            backup_root=backup_root,
        )

        trigger = trigger_collection.Item(1)
        trigger.StartBoundary = boundary
        trigger.DaysInterval = 1
        trigger.RandomDelay = "PT0S"
        action = action_collection.Item(1)
        action.Path = "cmd.exe"
        action.Arguments = f'/c "{wrapper}"'
        action.WorkingDirectory = str(root)
        settings.MultipleInstances = 2
        settings.StartWhenAvailable = False
        if execution_time_limit_override:
            settings.ExecutionTimeLimit = execution_time_limit_override

        folder.RegisterTaskDefinition(
            TASK_NAME,
            definition,
            TASK_UPDATE
            | TASK_DONT_ADD_PRINCIPAL_ACE
            | TASK_IGNORE_REGISTRATION_TRIGGERS,
            str(principal.UserId),
            None,
            3,
            None,
        )
        after_task = folder.GetTask(TASK_NAME)
        if bool(after_task.Enabled) != before_enabled:
            after_task.Enabled = before_enabled
            after_task = folder.GetTask(TASK_NAME)
        after_definition = after_task.Definition
        after_trigger = after_definition.Triggers.Item(1)
        after_action = after_definition.Actions.Item(1)
        after_settings = after_definition.Settings
        expected_timeout = execution_time_limit_override or before_timeout
        after_xml_text = str(after_task.Xml)
        after_com_boundary = str(after_trigger.StartBoundary)
        after_com_random_delay = after_trigger.RandomDelay
        trigger_readback = _verify_trigger_readback(
            expected_boundary=boundary,
            com_boundary=after_com_boundary,
            com_random_delay=after_com_random_delay,
            task_xml=after_xml_text,
            custom_user_local_time=bool(custom_user_local_time),
        )
        verified = (
            trigger_readback["verified"] is True
            and int(after_trigger.DaysInterval) == 1
            and str(after_action.Path).casefold() == "cmd.exe"
            and Path(str(after_action.WorkingDirectory)).resolve() == root
            and str(after_action.Arguments) == f'/c "{wrapper}"'
            and int(after_settings.MultipleInstances) == 2
            and not bool(after_settings.StartWhenAvailable)
            and str(after_settings.ExecutionTimeLimit) == expected_timeout
            and int(after_settings.RestartCount) == before_retry_count
            and str(after_settings.RestartInterval) == before_retry_interval
            and int(after_definition.Principal.LogonType) == 3
            and int(after_definition.Principal.RunLevel) == 0
            and str(after_definition.Principal.UserId) == str(principal.UserId)
            and bool(after_settings.DisallowStartIfOnBatteries)
            and bool(after_settings.StopIfGoingOnBatteries)
            and bool(after_task.Enabled) == before_enabled
        )
        if not verified:
            return {
                "status": "readback_mismatch",
                "task_path": TASK_PATH,
                "before_xml_backup": backup["xml_path"],
                "before_xml_sha256": backup["xml_sha256"],
                "execution_time_limit_before": before_timeout,
                "trigger_readback": trigger_readback,
            }
        after_xml = _xml_backup_bytes(after_xml_text)
        return {
            "status": "registered_and_readback_verified",
            "task_path": TASK_PATH,
            "schedule": schedule,
            "start_boundary": after_com_boundary,
            "start_boundary_readback": trigger_readback,
            "random_delay": (
                None if after_com_random_delay is None else str(after_com_random_delay)
            ),
            "mapping": mapping,
            "state": int(after_task.State),
            "enabled": bool(after_task.Enabled),
            "last_run_time": _scheduler_host_local_wall_time(after_task.LastRunTime),
            "last_task_result": int(after_task.LastTaskResult),
            "next_run_time": _scheduler_host_local_wall_time(after_task.NextRunTime),
            "missed_run_count": int(after_task.NumberOfMissedRuns),
            "multiple_instances": int(after_settings.MultipleInstances),
            "execution_time_limit": str(after_settings.ExecutionTimeLimit),
            "execution_time_limit_before": before_timeout,
            "execution_time_limit_override_applied": bool(execution_time_limit_override),
            "start_when_available": bool(after_settings.StartWhenAvailable),
            "retry_count": int(after_settings.RestartCount),
            "retry_interval": str(after_settings.RestartInterval),
            "before_xml_backup": backup["xml_path"],
            "before_xml_backup_metadata": backup["metadata_path"],
            "before_xml_sha256": backup["xml_sha256"],
            "after_xml_sha256": _sha256(after_xml),
            "principal_preserved": True,
            "battery_restrictions_preserved": True,
            "retry_policy_preserved": True,
            "enabled_state_preserved": True,
            "readback_verified": True,
        }
    finally:
        # 先釋放所有區域 COM proxy，讓 IUnknown.Release 在 apartment 尚存時完成。
        after_settings = None
        after_action = None
        after_trigger = None
        after_definition = None
        after_task = None
        action = None
        trigger = None
        action_collection = None
        trigger_collection = None
        settings = None
        principal = None
        definition = None
        task = None
        folder = None
        service = None
        if service_factory is None:
            try:
                import pythoncom

                pythoncom.CoUninitialize()
            except ImportError:
                pass


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", nargs="?", choices=("dryrun", "register"), default="dryrun")
    parser.add_argument("custom_user_local_time", nargs="?", default="")
    parser.add_argument("execution_time_limit_override", nargs="?", default="")
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--backup-root", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    custom_time = args.custom_user_local_time or None
    time_limit = args.execution_time_limit_override or None
    try:
        if args.mode == "dryrun":
            payload = dryrun(
                repo_root=args.repo_root,
                custom_user_local_time=custom_time,
                execution_time_limit_override=time_limit,
            )
            print(f"Mode: {payload['mode']}")
            print(f"Task: {payload['task_path']}")
            print(f"Schedule: {payload['schedule']}")
            print(f"Next start boundary: {payload['start_boundary']}")
            print(f"Mapping: {payload['mapping']}")
            print(f"Cutoff: {payload['cutoff']}")
            print("Execution settings: IgnoreNew, RandomDelay=PT0S, StartWhenAvailable=false")
            print(f"ExecutionTimeLimit: {payload['execution_time_limit']}")
            print(f"Principal policy: {payload['principal_policy']}")
            print(f"Battery policy: {payload['battery_policy']}")
            print(f"Action: {payload['action']}")
            print(f"WorkingDirectory: {payload['working_directory']}")
            print("Dryrun only. No scheduled task was changed.")
            return 0
        if custom_time and _windows_timezone_name() != "Pacific Standard Time":
            raise RegistrationError("custom_user_local_time_requires_Pacific_Standard_Time")
        report = register_existing_task(
            repo_root=args.repo_root,
            backup_root=args.backup_root
            or args.repo_root / "output/qa/scheduled_registration_backups",
            custom_user_local_time=custom_time,
            execution_time_limit_override=time_limit,
        )
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if report.get("status") == "registered_and_readback_verified" else 3
    except (OSError, RegistrationError, ValueError) as error:
        print(json.dumps({"status": "blocked", "error": str(error)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
