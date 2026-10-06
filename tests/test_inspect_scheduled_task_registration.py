from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from scripts.inspect_scheduled_task_registration import (
    EXPECTED_TASKS,
    TASK_WRAPPER_PATHS,
    _is_zero_duration,
    _parse_list_summary,
    _redact_sensitive_text,
    _sanitize_actions,
    _schedule_matches,
    inspect_scheduled_task_registration,
)


ROOT = Path(__file__).resolve().parents[1]
COM_SCHEMA = "scheduler-com-query.v1"


def _com_task_rows(repo_root: Path, *, missing: set[str] | None = None) -> list[dict[str, object]]:
    missing_names = missing or set()
    rows: list[dict[str, object]] = []
    for spec in EXPECTED_TASKS:
        name = spec["name"]
        task_path = f"\\{name}"
        if name in missing_names:
            rows.append({"task_path": task_path, "status": "missing"})
            continue
        schedule_parts = spec["schedule"].split()
        expected_offset = schedule_parts[-1] if schedule_parts[-1].startswith(("+", "-")) else None
        expected_time = schedule_parts[-2] if expected_offset else schedule_parts[-1]
        boundary = f"2026-10-03T{expected_time}:00{expected_offset or ''}"
        com_boundary = boundary
        if expected_offset:
            com_boundary = datetime.fromisoformat(boundary).astimezone(
                ZoneInfo("America/Los_Angeles")
            ).isoformat(timespec="seconds")
        wrapper = repo_root / TASK_WRAPPER_PATHS[name]
        rows.append(
            {
                "task_path": task_path,
                "status": "available",
                "state": "ready",
                "state_code": 3,
                "enabled": True,
                "last_run_time": "2026-10-02T04:00:00-07:00",
                "last_task_result": 0,
                "last_task_result_hex": "0x00000000",
                "next_run_time": "2026-10-03T04:00:00-07:00",
                "missed_run_count": 0,
                "actions": [
                    {
                        "type": "Exec",
                        "command": "cmd.exe",
                        "arguments": f'/c "{wrapper}"',
                        "working_directory": str(repo_root),
                    }
                ],
                "start_boundary": boundary,
                "com_start_boundary": com_boundary,
                "com_random_delay": "PT0S",
                "com_trigger_count": 1,
                "random_delay": "PT0S",
                "schedule_type": schedule_parts[0].title(),
                "days_interval": "1" if schedule_parts[0].lower() == "daily" else None,
                "weeks_interval": "1" if schedule_parts[0].lower() == "weekly" else None,
                "days": schedule_parts[1].title() if schedule_parts[0].lower() == "weekly" else "",
                "random_delay": "PT0S",
                "execution_time_limit": "PT2H",
                "restart_count": 0,
                "restart_interval": "PT0S",
                "multiple_instances_policy": "IgnoreNew",
                "start_when_available": False,
                "power_policy": {
                    "disallow_start_if_on_batteries": True,
                    "stop_if_going_on_batteries": True,
                },
            }
        )
    return rows


def _com_runner(*, rows: list[dict[str, object]] | None = None, status: str = "available"):
    def run(command, **kwargs):
        paths = json.loads(command[command.index("--task-paths-json") + 1])
        assert len(paths) == len(EXPECTED_TASKS)
        assert all(path.startswith("\\baldr-") for path in paths)
        payload = {"schema_version": COM_SCHEMA, "status": status, "tasks": rows or []}
        if status != "available":
            payload["error"] = "access_denied"
        return SimpleNamespace(returncode=0 if status == "available" else 2, stdout=json.dumps(payload), stderr="")

    return run


def test_inspector_uses_exact_root_paths_and_com_fields_for_configuration_readback() -> None:
    calls = []
    repo_root = ROOT

    def fake_schtasks(command, **kwargs):
        calls.append((command, kwargs))
        task_path = command[3]
        task_name = task_path.lstrip("\\")
        wrapper = repo_root / TASK_WRAPPER_PATHS[task_name]
        return SimpleNamespace(
            returncode=0,
            stdout=f'Task To Run: cmd.exe /c "{wrapper}"\nLast Result: 0\n',
            stderr="",
        )

    report = inspect_scheduled_task_registration(
        runner=fake_schtasks,
        com_runner=_com_runner(rows=_com_task_rows(repo_root)),
        repo_root=repo_root,
    )

    assert report["query_only"] is True
    assert report["side_effect_free"] is True
    assert report["all_available"] is True
    assert report["all_wrappers_present"] is True
    assert report["all_actions_observed"] is True
    assert report["all_actions_match"] is True
    assert report["all_schedules_observed"] is True
    assert report["all_schedules_match"] is True
    assert report["all_working_directories_match"] is True
    assert report["configuration_ready"] is True
    assert report["available_count"] == len(EXPECTED_TASKS)
    assert len(calls) == len(EXPECTED_TASKS)
    assert all(call[0][1:3] == ["/Query", "/TN"] for call in calls)
    assert all(call[0][3].startswith("\\baldr-") for call in calls)
    first = report["tasks"][0]
    assert first["scheduler_state"] == "ready"
    assert first["last_task_result_hex"] == "0x00000000"
    assert first["missed_run_count"] == 0
    assert first["execution_time_limit"] == "PT2H"
    assert first["restart_count"] == 0
    assert first["multiple_instances_policy"] == "IgnoreNew"
    assert first["working_directories"] == [str(repo_root)]
    assert all("output" not in item for item in report["tasks"])
    taipei_task = next(
        item for item in report["tasks"] if item["name"] == "baldr-paper-portfolio-daily"
    )
    assert taipei_task["schedule_matches"] is True
    assert taipei_task["start_boundary"] == "2026-10-03T08:25:00+08:00"
    assert taipei_task["com_start_boundary"] == "2026-10-02T17:25:00-07:00"


def test_query_cmd_delegates_to_inspector_without_a_duplicate_task_list() -> None:
    text = (ROOT / "scripts/scheduled/query_baldr_scheduled_tasks.cmd").read_text(encoding="utf-8")
    names = [spec["name"] for spec in EXPECTED_TASKS]

    assert len(names) == len(set(names)) == 21
    assert set(names) == set(TASK_WRAPPER_PATHS)
    assert "inspect_scheduled_task_registration.py" in text
    assert "--repo-root" in text
    assert "set TASKS=" not in text
    assert next(spec["schedule"] for spec in EXPECTED_TASKS if spec["name"].endswith("banktaiwan-shadow-daily")) == "DAILY 05:50"
    assert next(spec["schedule"] for spec in EXPECTED_TASKS if spec["name"] == "baldr-paper-portfolio-daily") == "DAILY 08:25 +08:00"


def test_schtasks_query_error_remains_unknown_until_com_confirms_presence_or_absence() -> None:
    def fake_schtasks(command, **kwargs):
        return SimpleNamespace(returncode=1, stdout="ERROR: Access is denied.\n", stderr="ERROR: Access is denied.\n")

    report = inspect_scheduled_task_registration(runner=fake_schtasks)

    assert report["all_available"] is False
    assert report["available_count"] == 0
    assert report["confirmed_missing_count"] == 0
    assert report["unknown_count"] == len(EXPECTED_TASKS)
    assert report["tasks"][0]["status"] == "unknown"
    assert report["tasks"][0]["error"] == "access_denied"
    assert report["tasks"][0].get("schtasks_reported_missing") is not True


def test_com_query_error_never_turns_schtasks_not_found_text_into_confirmed_missing() -> None:
    def fake_schtasks(command, **kwargs):
        return SimpleNamespace(returncode=1, stdout="ERROR: The system cannot find the file specified.\n", stderr="")

    report = inspect_scheduled_task_registration(
        runner=fake_schtasks,
        com_runner=_com_runner(status="query_error"),
    )

    assert report["confirmed_missing_count"] == 0
    assert report["unknown_count"] == len(EXPECTED_TASKS)
    assert report["tasks"][0]["status"] == "unknown"
    assert report["tasks"][0]["schtasks_reported_missing"] is True
    assert report["tasks"][0]["com_query_status"] == "unknown"


def test_successful_com_enumeration_is_required_to_confirm_a_missing_task() -> None:
    missing_name = EXPECTED_TASKS[1]["name"]

    def fake_schtasks(command, **kwargs):
        name = command[3].lstrip("\\")
        return SimpleNamespace(
            returncode=1 if name == missing_name else 0,
            stdout="ERROR: task not found\n" if name == missing_name else "Last Result: 0\n",
            stderr="",
        )

    report = inspect_scheduled_task_registration(
        runner=fake_schtasks,
        com_runner=_com_runner(rows=_com_task_rows(ROOT, missing={missing_name})),
    )

    assert report["confirmed_missing_count"] == 1
    assert report["unknown_count"] == 0
    assert report["tasks"][1]["status"] == "missing"
    assert report["tasks"][1]["com_confirmed_missing"] is True


def test_inspector_redacts_secret_and_account_arguments_without_corrupting_paths() -> None:
    rendered = _redact_sensitive_text(
        'cmd.exe /c "C:\\Projects\\PythonProjects\\technical_analysis\\scripts\\scheduled\\run.cmd" '
        '/token "secret value with spaces" /user "DOMAIN\\unrelated account"'
    )

    assert "C:\\Projects\\PythonProjects\\technical_analysis\\scripts\\scheduled\\run.cmd" in rendered
    assert "secret value with spaces" not in rendered
    assert '"DOMAIN\\unrelated account"' not in rendered
    assert "unrelated" not in rendered
    assert "<redacted>" in rendered
    assert "<account-redacted>" in rendered


def test_inspector_redacts_summary_accounts_and_keeps_only_safe_runtime_fields() -> None:
    repo_root = ROOT

    def fake_schtasks(command, **kwargs):
        task_name = command[3].lstrip("\\")
        wrapper = repo_root / TASK_WRAPPER_PATHS[task_name]
        return SimpleNamespace(
            returncode=0,
            stdout=(
                f'Task To Run: cmd.exe /c "{wrapper}"\n'
                "Logon Mode: Interactive only\n"
                "Power Management: Stop On Battery Mode, No Start On Batteries\n"
                "Scheduled Task State: Enabled\n"
                "Last Run Time: 1999/11/30 上午 12:00:00\n"
                "Next Run Time: 2026/10/3 上午 04:20:00\n"
                "Last Result: 267011\n"
                "Run As User: DOMAIN\\private-user\n"
            ),
            stderr="",
        )

    report = inspect_scheduled_task_registration(runner=fake_schtasks, repo_root=repo_root)
    summary = report["tasks"][0]["summary"]
    assert summary["logon_mode"] == "Interactive only"
    assert summary["power_management"] == "Stop On Battery Mode, No Start On Batteries"
    assert summary["scheduled_task_state"] == "Enabled"
    assert summary["last_result"] == "267011"
    assert "private-user" not in str(report)


def test_long_quoted_secret_is_redacted_before_summary_or_action_truncation() -> None:
    secret = "PRIVATE_SECRET_PART " * 220
    account = "PRIVATE_ACCOUNT_PART " * 180
    wrapper = str(ROOT / "scripts/scheduled/run_paper_portfolio_daily.cmd")
    summary = _parse_list_summary(
        f'Task To Run: cmd.exe /c "{wrapper}" /token "{secret}" /user "{account}"\n'
    )
    action = _sanitize_actions(
        [
            {
                "type": "Exec",
                "command": "cmd.exe",
                "arguments": f'/c "{wrapper}" /token "{secret}" /account "{account}"',
                "working_directory": str(ROOT),
            }
        ]
    )[0]

    for rendered in (str(summary), str(action)):
        assert "PRIVATE_SECRET_PART" not in rendered
        assert "PRIVATE_ACCOUNT_PART" not in rendered
        assert "run_paper_portfolio_daily.cmd" in rendered


def test_timezone_aware_daily_schedule_requires_taipei_recurrence_and_zero_delay() -> None:
    expected = "DAILY 08:25 +08:00"

    def summary(
        boundary: str,
        *,
        com_boundary: str = "2026-10-02T17:25:00-07:00",
        random_delay: str = "PT0S",
        com_random_delay: str = "",
        days_interval: str = "1",
    ) -> dict[str, object]:
        return {
            "trigger_count": 1,
            "com_trigger_count": 1,
            "schedule_type": "Daily",
            "days_interval": days_interval,
            "start_boundary": boundary,
            "random_delay": random_delay,
            "com_start_boundary": com_boundary,
            "com_random_delay": com_random_delay,
        }

    assert _schedule_matches(
        summary("2026-10-03T08:25:00+08:00"), expected_schedule=expected
    ) is True
    # Task Scheduler may normalize XML and COM to host-local -07:00 or UTC Z;
    # both are accepted only when the aware instant resolves to Taipei 08:25.
    assert _schedule_matches(
        summary("2026-10-02T17:25:00-07:00"), expected_schedule=expected
    ) is True
    assert _schedule_matches(
        summary("2026-10-03T00:25:00Z"), expected_schedule=expected
    ) is True
    assert _schedule_matches(
        summary("2026-10-03T08:25:00"), expected_schedule=expected
    ) is False
    assert _schedule_matches(
        summary("2026-10-02T17:26:00-07:00"), expected_schedule=expected
    ) is False
    assert _schedule_matches(
        summary("2026-10-03T08:26:00+08:00"), expected_schedule=expected
    ) is False
    assert _schedule_matches(
        summary("2026-10-03T08:25:00+08:00", random_delay="PT1M"),
        expected_schedule=expected,
    ) is False
    assert _schedule_matches(
        summary("2026-10-03T08:25:00+08:00", days_interval="2"),
        expected_schedule=expected,
    ) is False
    wrong_com_instant = summary("2026-10-03T08:25:00+08:00")
    wrong_com_instant["com_start_boundary"] = "2026-10-02T16:25:00-07:00"
    assert _schedule_matches(wrong_com_instant, expected_schedule=expected) is False
    nonzero_com_delay = summary("2026-10-03T08:25:00+08:00")
    nonzero_com_delay["com_random_delay"] = "PT5S"
    assert _schedule_matches(nonzero_com_delay, expected_schedule=expected) is False
    naive_com_instant = summary(
        "2026-10-03T08:25:00+08:00", com_boundary="2026-10-02T17:25:00"
    )
    assert _schedule_matches(naive_com_instant, expected_schedule=expected) is False
    assert _schedule_matches(
        {**summary("2026-10-03T08:25:00+08:00"), "trigger_count": 2},
        expected_schedule=expected,
    ) is False
    assert _is_zero_duration("") is True
    assert _is_zero_duration(None) is True
    assert _is_zero_duration("PT0S") is True
    assert _is_zero_duration("P0DT0S") is True
    assert _is_zero_duration("PT1M") is False


def test_scheduler_registration_probe_detects_missing_local_wrappers(tmp_path: Path) -> None:
    def fake_run(command, **kwargs):
        return SimpleNamespace(returncode=0, stdout="Last Result: 0\n", stderr="")

    report = inspect_scheduled_task_registration(runner=fake_run, repo_root=tmp_path)

    assert report["all_available"] is True
    assert report["all_wrappers_present"] is False
    assert report["wrapper_missing_count"] == len(EXPECTED_TASKS)
    assert report["configuration_ready"] is False
    assert report["tasks"][0]["wrapper_status"] == "missing"


def test_scheduler_registration_probe_detects_task_action_mismatch() -> None:
    def fake_run(command, **kwargs):
        return SimpleNamespace(
            returncode=0,
            stdout='Task To Run: cmd.exe /c "C:\\wrong\\wrapper.cmd"\n',
            stderr="",
        )

    report = inspect_scheduled_task_registration(runner=fake_run)

    assert report["all_available"] is True
    assert report["all_wrappers_present"] is True
    assert report["all_actions_observed"] is True
    assert report["action_mismatch_count"] == len(EXPECTED_TASKS)
    assert report["all_actions_match"] is False
    assert report["configuration_ready"] is False


def test_scheduler_registration_probe_requires_observed_task_actions() -> None:
    def fake_run(command, **kwargs):
        return SimpleNamespace(returncode=0, stdout="Last Result: 0\n", stderr="")

    report = inspect_scheduled_task_registration(runner=fake_run)

    assert report["all_available"] is True
    assert report["action_mismatch_count"] == 0
    assert report["action_unobserved_count"] == len(EXPECTED_TASKS)
    assert report["all_actions_observed"] is False
    assert report["all_actions_match"] is True
    assert report["configuration_ready"] is False


def test_scheduler_registration_help_is_utf8_safe_with_cp1252() -> None:
    script = ROOT / "scripts" / "inspect_scheduled_task_registration.py"
    environment = os.environ.copy()
    environment["PYTHONIOENCODING"] = "cp1252"
    completed = subprocess.run(
        [sys.executable, str(script), "--help"],
        capture_output=True,
        env=environment,
        check=False,
    )

    assert completed.returncode == 0
    assert "唯讀檢查" in completed.stdout.decode("utf-8")
