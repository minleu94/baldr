from __future__ import annotations

import json
import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

from scripts.scheduled.register_paper_portfolio_task import (
    TASK_DONT_ADD_PRINCIPAL_ACE,
    TASK_IGNORE_REGISTRATION_TRIGGERS,
    TASK_UPDATE,
    RegistrationError,
    _save_before_backup,
    _scheduler_host_local_wall_time,
    _verify_trigger_readback,
    register_existing_task,
)


ROOT = Path(__file__).resolve().parents[1]
SCHEDULED = ROOT / "scripts" / "scheduled"
REGISTRATION = SCHEDULED / "register_paper_portfolio_task.cmd"
PLAN = SCHEDULED / "paper_portfolio_task_registration_plan.json"
PAPER_TASK = "baldr-paper-portfolio-daily"


def _run_registration(*args: str) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["cmd.exe", "/d", "/c", str(REGISTRATION), *args],
        cwd=ROOT,
        env=os.environ.copy(),
        capture_output=True,
        check=False,
        text=False,
    )
    return subprocess.CompletedProcess(
        result.args,
        result.returncode,
        stdout=(result.stdout or b"").decode("utf-8", errors="replace"),
        stderr=(result.stderr or b"").decode("utf-8", errors="replace"),
    )


def test_dedicated_paper_registration_defaults_to_timezone_aware_dryrun() -> None:
    result = _run_registration("dryrun")

    assert result.returncode == 0, result.stdout + result.stderr
    assert PAPER_TASK in result.stdout
    assert "Schedule: DAILY Asia/Taipei 08:25 (+08:00)" in result.stdout
    boundary_line = next(
        line for line in result.stdout.splitlines() if line.startswith("Next start boundary: ")
    )
    boundary = datetime.fromisoformat(boundary_line.split(": ", 1)[1])
    assert boundary.strftime("%H:%M%z") == "08:25+0800"
    assert "00:25 UTC; 17:25 PDT / 16:25 PST" in result.stdout
    assert "waits five minutes for real Asia/Taipei 08:30" in result.stdout
    assert "IgnoreNew, RandomDelay=PT0S, StartWhenAvailable=false" in result.stdout
    assert "ExecutionTimeLimit: preserve existing Scheduler value" in result.stdout
    assert "preserve existing InteractiveToken / LeastPrivilege principal" in result.stdout
    assert "preserve existing battery restrictions" in result.stdout
    assert "WorkingDirectory: " + str(ROOT) in result.stdout
    assert "Dryrun only. No scheduled task was changed." in result.stdout
    for other_task in (
        "baldr-formal-input-producer-daily",
        "baldr-paper-execution-eod-replay-daily",
        "baldr-ml-allocation-copilot-daily",
    ):
        assert other_task not in result.stdout


def test_custom_user_local_time_is_an_explicit_optional_override() -> None:
    result = _run_registration("dryrun", "16:15")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Schedule: DAILY custom user-local 16:15" in result.stdout
    assert "Host-local override explicitly requested" in result.stdout


def test_optional_execution_time_limit_override_is_validated_and_explicit() -> None:
    result = _run_registration("dryrun", "", "PT30M")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "ExecutionTimeLimit: PT30M" in result.stdout

    invalid = _run_registration("dryrun", "", "P0D")
    assert invalid.returncode == 2
    assert "positive" in invalid.stdout


def test_registration_plan_keeps_backup_rollback_and_timeout_as_proposed() -> None:
    plan = json.loads(PLAN.read_text(encoding="utf-8"))

    assert plan["status"] == "prepared_not_applied"
    assert plan["schedule"]["start_boundary"] == "2026-10-03T08:25:00+08:00"
    assert plan["settings"]["multiple_instances"] == "IgnoreNew"
    assert plan["settings"]["random_delay"] == "PT0S"
    assert plan["settings"]["start_when_available"] is False
    assert plan["settings"]["execution_time_limit"] == "preserve existing Scheduler value"
    assert plan["settings"]["recommended_execution_time_limit"] == "PT30M"
    assert "not adopted" in plan["settings"]["recommended_execution_time_limit_status"]
    assert plan["registration"]["applied_by_this_plan"] is False
    assert "deployment owner" in plan["registration"]["task_state_owner"]
    assert "pywin32 Task Scheduler COM" in plan["registration"]["method"]
    assert "Create-only XML backup" in plan["registration"]["before_backup"]
    assert "Re-register the saved before XML" in plan["rollback"]["method"]
    assert plan["rollback"]["do_not_delete_task"] is True


def test_backup_bytes_match_xml_declaration_and_parse_with_non_ascii_content(tmp_path: Path) -> None:
    xml_text = (
        '<?xml version="1.0" encoding="UTF-16"?>'
        '<Task><Description>盤前排程</Description></Task>'
    )

    backup = _save_before_backup(
        xml_text=xml_text,
        enabled=False,
        execution_time_limit="PT72H",
        backup_root=tmp_path,
    )

    path = Path(backup["xml_path"])
    data = path.read_bytes()
    assert data.startswith((b"\xff\xfe", b"\xfe\xff"))
    assert hashlib.sha256(data).hexdigest() == backup["xml_sha256"]
    root = ET.parse(path).getroot()
    assert root.findtext("Description") == "盤前排程"


def test_normalized_com_boundary_is_verified_against_aware_xml_recurrence() -> None:
    expected = "2026-10-03T08:25:00+08:00"

    def xml(boundary: str, *, delay: str = "", days_interval: int = 1) -> str:
        delay_xml = f"<RandomDelay>{delay}</RandomDelay>" if delay else ""
        return (
            "<Task><Triggers><CalendarTrigger>"
            f"<StartBoundary>{boundary}</StartBoundary>"
            f"{delay_xml}<ScheduleByDay><DaysInterval>{days_interval}</DaysInterval>"
            "</ScheduleByDay></CalendarTrigger></Triggers></Task>"
        )

    normalized_xml_values = (
        ("2026-10-02T17:25:00-07:00", "2026-10-02T17:25:00-07:00"),
        ("2026-10-03T00:25:00Z", "2026-10-02T17:25:00-07:00"),
    )
    for xml_boundary, com_boundary in normalized_xml_values:
        normalized = _verify_trigger_readback(
            expected_boundary=expected,
            com_boundary=com_boundary,
            com_random_delay="",
            task_xml='<?xml version="1.0" encoding="UTF-16"?>' + xml(xml_boundary),
            custom_user_local_time=False,
        )
        assert normalized["verified"] is True, normalized
        assert normalized["com_start_boundary"] == com_boundary
        assert normalized["xml_start_boundary"] == xml_boundary
        assert normalized["com_boundary_utc"] == "2026-10-03T00:25:00+00:00"
        assert normalized["xml_boundary_utc"] == "2026-10-03T00:25:00+00:00"
        assert normalized["xml_boundary_taipei"] == "2026-10-03T08:25:00+08:00"

    invalid_cases = (
        # Naive boundaries do not identify a stable instant.
        (xml("2026-10-02T17:25:00"), "2026-10-02T17:25:00-07:00", ""),
        (xml("2026-10-03T08:25:00+08:00"), "2026-10-03T08:25:00", ""),
        # Wrong UTC time, nonzero delay from either source, or wrong recurrence.
        (xml("2026-10-02T17:26:00-07:00"), "2026-10-02T17:25:00-07:00", ""),
        (xml("2026-10-03T08:25:00+08:00"), "2026-10-02T16:25:00-07:00", ""),
        (xml("2026-10-03T08:25:00+08:00", delay="PT1M"), "2026-10-02T17:25:00-07:00", ""),
        (xml("2026-10-03T08:25:00+08:00"), "2026-10-02T17:25:00-07:00", "PT1M"),
        (xml("2026-10-03T08:25:00+08:00", days_interval=2), "2026-10-02T17:25:00-07:00", ""),
    )
    for task_xml, com_boundary, com_delay in invalid_cases:
        result = _verify_trigger_readback(
            expected_boundary=expected,
            com_boundary=com_boundary,
            com_random_delay=com_delay,
            task_xml=task_xml,
            custom_user_local_time=False,
        )
        assert result["verified"] is False


def test_scheduler_com_run_time_is_reported_as_host_local_without_fake_offset() -> None:
    value = datetime(2026, 10, 2, 16, 34, tzinfo=timezone.utc)

    assert _scheduler_host_local_wall_time(value) == "2026-10-02T16:34:00"


def test_registration_cli_keeps_modes_and_uses_task_scheduler_com() -> None:
    cmd_text = REGISTRATION.read_text(encoding="utf-8")
    python_text = (SCHEDULED / "register_paper_portfolio_task.py").read_text(encoding="utf-8")

    assert '"dryrun"' in cmd_text and '"register"' in cmd_text
    assert "register_paper_portfolio_task.py" in cmd_text
    assert "BALDR_PYTHON" in cmd_text
    assert "ExecutionTimeLimitOverride" not in cmd_text
    assert "RegisterTaskDefinition" in python_text
    assert 'GetTask(TASK_NAME)' in python_text
    assert "_save_before_backup" in python_text
    assert "settings.StartWhenAvailable = False" in python_text
    assert "trigger.RandomDelay = \"PT0S\"" in python_text
    assert "execution_time_limit_override" in python_text
    assert "if execution_time_limit_override:" in python_text
    assert "schtasks.exe /Create" not in python_text
    assert "ExecutionPolicy" not in cmd_text
    assert "TASK_CREATE_OR_UPDATE" not in python_text
    assert TASK_UPDATE == 0x4
    assert TASK_DONT_ADD_PRINCIPAL_ACE == 0x10
    assert TASK_IGNORE_REGISTRATION_TRIGGERS == 0x20


def test_missing_existing_paper_task_fails_closed_without_registering_or_creating(tmp_path: Path) -> None:
    calls = {"register": 0}

    class MissingFolder:
        def GetTask(self, _name: str) -> object:
            raise FileNotFoundError("task missing")

        def RegisterTaskDefinition(self, *_args: object) -> None:
            calls["register"] += 1

    service = type(
        "Service",
        (),
        {"Connect": lambda _self: None, "GetFolder": lambda _self, _path: MissingFolder()},
    )()

    try:
        register_existing_task(
            repo_root=ROOT,
            backup_root=tmp_path / "backups",
            service_factory=lambda: service,
        )
    except RegistrationError as error:
        assert "no task created" in str(error)
    else:
        raise AssertionError("a missing task must fail closed")

    assert calls["register"] == 0
    assert not (tmp_path / "backups").exists()


def test_registration_releases_com_proxies_before_uninitializing_apartment(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from scripts.scheduled import register_paper_portfolio_task as registration

    tracker = {"active": 0, "initialized": False, "active_at_uninitialize": None}

    class ComProxy:
        def __init__(self, target: object) -> None:
            object.__setattr__(self, "_target", target)
            tracker["active"] += 1

        def __getattr__(self, name: str):
            value = getattr(object.__getattribute__(self, "_target"), name)
            if callable(value):
                def invoke(*args, **kwargs):
                    result = value(*(unwrap(item) for item in args), **kwargs)
                    return wrap(result)

                return invoke
            return wrap(value)

        def __setattr__(self, name: str, value: object) -> None:
            setattr(
                object.__getattribute__(self, "_target"),
                name,
                unwrap(value),
            )

        def __str__(self) -> str:
            return str(object.__getattribute__(self, "_target"))

        def __del__(self) -> None:
            tracker["active"] -= 1

    def unwrap(value: object) -> object:
        return object.__getattribute__(value, "_target") if isinstance(value, ComProxy) else value

    def wrap(value: object) -> object:
        if value is None or isinstance(value, (str, int, float, bool, bytes)):
            return value
        return ComProxy(value)

    class Collection:
        def __init__(self, *items: object) -> None:
            self.items = items

        @property
        def Count(self) -> int:
            return len(self.items)

        def Item(self, index: int) -> object:
            return self.items[index - 1]

    class Trigger:
        Type = 2
        StartBoundary = "2026-10-02T16:15:00"
        DaysInterval = 1
        RandomDelay = ""

    class Action:
        Type = 0
        Path = "cmd.exe"
        Arguments = ""
        WorkingDirectory = ""

    class Principal:
        LogonType = 3
        RunLevel = 0
        UserId = "BALDR\\worker"

    class Settings:
        DisallowStartIfOnBatteries = True
        StopIfGoingOnBatteries = True
        ExecutionTimeLimit = "PT72H"
        RestartCount = 0
        RestartInterval = "PT0S"
        MultipleInstances = 1
        StartWhenAvailable = True

    class Definition:
        def __init__(self) -> None:
            self.Principal = Principal()
            self.Settings = Settings()
            self.Triggers = Collection(Trigger())
            self.Actions = Collection(Action())

    class Task:
        def __init__(self) -> None:
            self.Path = "\\baldr-paper-portfolio-daily"
            self.Definition = Definition()
            self.Enabled = False
            self.State = 1
            self.LastRunTime = None
            self.LastTaskResult = 0
            self.NextRunTime = None
            self.NumberOfMissedRuns = 0

        @property
        def Xml(self) -> str:
            boundary = self.Definition.Triggers.Item(1).StartBoundary
            return (
                "<Task><Triggers><CalendarTrigger>"
                f"<StartBoundary>{boundary}</StartBoundary>"
                "<ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay>"
                "</CalendarTrigger></Triggers></Task>"
            )

    task_model = Task()

    class Folder:
        def GetTask(self, _name: str) -> Task:
            return task_model

        def RegisterTaskDefinition(self, *_args: object) -> None:
            return None

    folder_model = Folder()

    class Service:
        def Connect(self) -> None:
            return None

        def GetFolder(self, _path: str) -> Folder:
            return folder_model

    class PythonCom:
        def CoInitialize(self) -> None:
            tracker["initialized"] = True

        def CoUninitialize(self) -> None:
            tracker["active_at_uninitialize"] = tracker["active"]
            tracker["initialized"] = False

    pythoncom = PythonCom()
    monkeypatch.setitem(sys.modules, "pythoncom", pythoncom)

    def fake_service() -> object:
        pythoncom.CoInitialize()
        return ComProxy(Service())

    monkeypatch.setattr(registration, "_make_service", fake_service)

    result = register_existing_task(
        repo_root=ROOT,
        backup_root=tmp_path / "backups",
    )

    assert result["status"] == "registered_and_readback_verified"
    assert tracker["initialized"] is False
    assert tracker["active_at_uninitialize"] == 0
    assert tracker["active"] == 0
