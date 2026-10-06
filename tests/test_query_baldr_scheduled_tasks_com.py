from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from scripts.scheduled.query_baldr_scheduled_tasks_com import (
    TASK_ENUM_HIDDEN,
    _time_text,
    query_tasks,
)


PAPER_PATH = "\\baldr-paper-portfolio-daily"
ML_PATH = "\\baldr-ml-allocation-forward-daily"


def _task(path: str = PAPER_PATH):
    xml = f"""<Task xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
      <RegistrationInfo><Author>private account must not be emitted</Author></RegistrationInfo>
      <Triggers><CalendarTrigger><StartBoundary>2026-10-03T08:25:00+08:00</StartBoundary>
        <Enabled>true</Enabled><RandomDelay>PT0S</RandomDelay>
        <ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay>
      </CalendarTrigger></Triggers>
      <Actions Context="Author"><Exec><Command>cmd.exe</Command>
        <Arguments>/c run.cmd /password &quot;secret value with spaces&quot; /account &quot;DOMAIN\\other account&quot;</Arguments>
        <WorkingDirectory>C:\\Projects\\PythonProjects\\technical_analysis</WorkingDirectory>
      </Exec></Actions>
      <Principals><Principal id="Author"><UserId>DOMAIN\\unrelated-user</UserId></Principal></Principals>
    </Task>"""
    settings = SimpleNamespace(
        DisallowStartIfOnBatteries=True,
        StopIfGoingOnBatteries=True,
        ExecutionTimeLimit="PT2H",
        RestartCount=2,
        RestartInterval="PT5M",
        MultipleInstances=2,
        StartWhenAvailable=False,
    )
    trigger = SimpleNamespace(
        StartBoundary="2026-10-02T17:25:00-07:00",
        RandomDelay="",
    )
    triggers = SimpleNamespace(Count=1, Item=lambda index: trigger)
    definition = SimpleNamespace(Settings=settings, Triggers=triggers)
    return SimpleNamespace(
        Path=path,
        Xml=xml,
        Definition=definition,
        State=3,
        LastTaskResult=267011,
        Enabled=True,
        LastRunTime=datetime(2026, 10, 2, 11, 0, tzinfo=timezone.utc),
        NextRunTime=datetime(2026, 10, 3, 15, 0, tzinfo=timezone.utc),
        NumberOfMissedRuns=0,
    )


def _service_for(tasks):
    calls: list[int] = []
    collection = SimpleNamespace(
        Count=len(tasks),
        Item=lambda index: tasks[index - 1],
    )

    def get_tasks(flags: int):
        calls.append(flags)
        return collection

    folder = SimpleNamespace(GetTasks=get_tasks)
    service = SimpleNamespace(
        Connect=lambda: None,
        GetFolder=lambda path: folder,
    )
    return lambda: service, calls


def test_readonly_com_query_returns_full_root_task_fields_and_redacts_identity_data() -> None:
    service_factory, calls = _service_for([_task()])
    result = query_tasks([PAPER_PATH], service_factory=service_factory)

    assert result["status"] == "available"
    task = result["tasks"][0]
    assert task["task_path"] == PAPER_PATH
    assert task["state"] == "ready"
    assert task["state_code"] == 3
    assert task["last_task_result"] == 267011
    assert task["last_task_result_hex"] == "0x00041303"
    assert task["missed_run_count"] == 0
    assert task["start_boundary"] == "2026-10-03T08:25:00+08:00"
    assert task["com_start_boundary"] == "2026-10-02T17:25:00-07:00"
    assert task["com_random_delay"] == ""
    assert task["com_trigger_count"] == 1
    assert task["trigger_count"] == 1
    assert task["action_count"] == 1
    assert task["actions"][0]["working_directory"] == "C:\\Projects\\PythonProjects\\technical_analysis"
    assert task["execution_time_limit"] == "PT2H"
    assert task["restart_count"] == 2
    assert task["restart_interval"] == "PT5M"
    assert task["multiple_instances_policy"] == "IgnoreNew"
    assert task["start_when_available"] is False
    assert calls == [TASK_ENUM_HIDDEN]
    rendered = str(result)
    for private_value in ("unrelated-user", "other account", "secret value", "private account"):
        assert private_value not in rendered
    assert task["actions"][0]["working_directory"].endswith("technical_analysis")


def test_successful_com_enumeration_marks_only_unreturned_exact_root_paths_missing() -> None:
    service_factory, calls = _service_for([_task()])
    result = query_tasks([PAPER_PATH, ML_PATH], service_factory=service_factory)

    assert result["status"] == "available"
    assert [row["status"] for row in result["tasks"]] == ["available", "missing"]
    assert [row["task_path"] for row in result["tasks"]] == [PAPER_PATH, ML_PATH]
    assert calls == [TASK_ENUM_HIDDEN]


def test_hidden_existing_allowlisted_task_is_not_confirmed_missing() -> None:
    hidden_task = _task()
    service_factory, calls = _service_for([hidden_task])

    result = query_tasks([PAPER_PATH], service_factory=service_factory)

    assert calls == [1]
    assert result["tasks"][0]["status"] == "available"
    assert result["tasks"][0]["task_path"] == PAPER_PATH


def test_com_scheduler_run_times_do_not_claim_false_utc_offset() -> None:
    # COM DATE wall-clock components can arrive with tzinfo=UTC from pywin32.
    # Keep the host-local reading and expose no invented offset.
    value = datetime(2026, 10, 2, 16, 34, tzinfo=timezone.utc)

    assert _time_text(value) == "2026-10-02T16:34:00"
    assert _time_text("2026-10-02T16:34:00+00:00") == "2026-10-02T16:34:00"


def test_invalid_or_nested_task_paths_are_rejected_before_com_access() -> None:
    result = query_tasks(["\\Folder\\baldr-paper-portfolio-daily"], service_factory=lambda: None)

    assert result["status"] == "query_error"
    assert result["error"] == "invalid_task_paths_parameter"


def test_com_enumeration_error_remains_query_error() -> None:
    result = query_tasks(
        [PAPER_PATH],
        service_factory=lambda: SimpleNamespace(
            Connect=lambda: (_ for _ in ()).throw(PermissionError("account text must not leak"))
        ),
    )

    assert result["status"] == "query_error"
    assert result["error"] == "PermissionError"
    assert "account text" not in str(result)
