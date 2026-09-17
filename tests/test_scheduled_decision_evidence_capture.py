from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path

import pytest

from app_module.evidence_event_importer_dtos import EvidenceCaptureRequest
from scripts.scheduled import run_scheduled_decision_evidence_capture as runner


ALL_SECTIONS = sorted(runner.REQUIRED_SNAPSHOT_SECTIONS)


class _OpenCalendar:
    def is_official_trading_day(self, _target_date):
        return True, "test_official_schedule_open"


class _ClosedCalendar:
    def is_official_trading_day(self, _target_date):
        return False, "twse_holiday_schedule_closed"


class _UnknownCalendar:
    def is_official_trading_day(self, _target_date):
        return None, "twse_holiday_schedule_unavailable"


def _snapshot_result(*, saved: bool, duplicate: bool) -> runner.CliRunResult:
    return runner.CliRunResult(
        returncode=0,
        payload={
            "dry_run": False,
            "saved": saved,
            "skipped_duplicate": duplicate,
            "snapshot_id": "snapshot-001",
            "snapshot_hash": "sha256:snapshot",
            "quality": "observed",
            "sections_seen": ALL_SECTIONS,
            "sections_missing": [],
            "warnings_count": 0,
        },
        stderr="",
    )


def _evidence_result(
    *,
    inserted: int,
    duplicates: int,
    failed: int = 0,
) -> runner.CliRunResult:
    return runner.CliRunResult(
        returncode=0,
        payload={
            "dry_run": False,
            "events_seen": inserted + duplicates + failed,
            "events_inserted": inserted,
            "events_skipped_duplicate": duplicates,
            "events_failed": failed,
            "warnings_count": 0,
            "diagnostics_by_code": {},
            "event_type_counts": {},
            "quality_counts": {},
            "diagnostics": [],
        },
        stderr="",
    )


def _with_command_temporal(result: runner.CliRunResult, command: list[str]) -> runner.CliRunResult:
    def value(flag: str) -> str:
        return command[command.index(flag) + 1]

    request = EvidenceCaptureRequest(
        source="test",
        decision_date=value("--as-of"),
        as_of=value("--as-of"),
        decision_at=value("--decision-at"),
        captured_at=value("--captured-at"),
        capture_mode=value("--capture-mode"),
    )
    payload = {**dict(result.payload or {}), **request.temporal_summary}
    payload["persisted_capture_context"] = request.capture_context
    return runner.CliRunResult(
        returncode=result.returncode,
        payload=payload,
        stderr=result.stderr,
        timed_out=result.timed_out,
        timeout_seconds=result.timeout_seconds,
    )


@pytest.mark.parametrize(
    ("now_text", "expected"),
    (
        ("2026-07-30T08:29:59+08:00", "2026-07-30T08:30:00+08:00"),
        ("2026-07-30T08:30:00+08:00", "2026-07-31T08:30:00+08:00"),
        ("2026-07-30T20:00:00+08:00", "2026-07-31T08:30:00+08:00"),
        ("2026-07-29T17:30:00-07:00", "2026-07-31T08:30:00+08:00"),
    ),
)
def test_next_unreached_taipei_decision_at(
    now_text: str,
    expected: str,
) -> None:
    result = runner.next_unreached_taipei_decision_at(
        datetime.fromisoformat(now_text)
    )

    assert result.isoformat() == expected


def test_next_unreached_taipei_decision_at_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError, match="時區"):
        runner.next_unreached_taipei_decision_at(
            datetime.fromisoformat("2026-07-30T08:00:00")
        )


@pytest.mark.parametrize(
    ("now_text", "expected"),
    (
        ("2026-07-30T08:29:59+08:00", "2026-07-29T08:30:00+08:00"),
        ("2026-07-30T08:30:00+08:00", "2026-07-30T08:30:00+08:00"),
        ("2026-07-30T20:00:00+08:00", "2026-07-30T08:30:00+08:00"),
        ("2026-07-29T17:30:00-07:00", "2026-07-30T08:30:00+08:00"),
    ),
)
def test_latest_reached_taipei_decision_at(
    now_text: str,
    expected: str,
) -> None:
    result = runner.latest_reached_taipei_decision_at(
        datetime.fromisoformat(now_text)
    )

    assert result.isoformat() == expected


def test_latest_reached_taipei_decision_at_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError, match="時區"):
        runner.latest_reached_taipei_decision_at(
            datetime.fromisoformat("2026-07-30T08:00:00")
        )


def test_successful_run_writes_atomic_status_and_uses_confirmed_existing_clis(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []
    results = iter(
        (
            _snapshot_result(saved=True, duplicate=False),
            _evidence_result(inserted=3, duplicates=2),
        )
    )

    def fake_run(command, **_kwargs):
        calls.append(list(command))
        return _with_command_temporal(next(results), list(command))

    monkeypatch.setattr(runner, "_run_json_cli", fake_run)
    payload = runner.run(
        data_root=tmp_path / "data",
        output_root=tmp_path / "output",
        db_path=tmp_path / "twstock.db",
        now=datetime.fromisoformat("2026-07-30T09:00:00+08:00"),
        python_executable="python-test",
        calendar=_OpenCalendar(),
    )

    status_path = (
        tmp_path
        / "output"
        / "scheduled"
        / "decision_evidence_capture"
        / "latest_status.json"
    )
    persisted = json.loads(status_path.read_text(encoding="utf-8"))
    assert persisted == payload
    assert payload["status"] == "passed"
    assert payload["calendar_decision_at"] == "2026-07-30T08:30:00+08:00"
    assert payload["decision_at"] == "2026-07-30T09:00:00+08:00"
    assert payload["as_of"] == "2026-07-30"
    assert payload["captured_at"] == "2026-07-30T09:00:00+08:00"
    assert payload["capture_mode"] == "research_only"
    assert payload["research_only"] is True
    assert payload["preopen_authority"] is False
    assert payload["natural_authority"] is False
    assert payload["snapshot_saved"] is True
    assert payload["snapshot_duplicate"] is False
    assert payload["events_inserted"] == 3
    assert payload["events_duplicates"] == 2
    assert payload["events_failures"] == 0
    assert payload["trading_calendar_validated"] is True
    assert payload["trading_calendar_is_open"] is True
    assert payload["maturity_date_inferred"] is False
    assert payload["safety_boundary"]["changes_portfolio_state"] is False
    assert payload["safety_boundary"]["broker_execution"] is False
    assert calls[0][-1] == "--confirm"
    assert "capture_decision_desk_snapshot.py" in calls[0][1]
    assert calls[1][-1] == "--confirm"
    assert "capture_evidence_events.py" in calls[1][1]
    assert calls[1][2:4] == ["--source", "all"]
    assert not list(status_path.parent.glob("*.tmp"))


def test_after_close_capture_passes_real_clock_and_marks_eod_research(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []
    results = iter(
        (
            _snapshot_result(saved=True, duplicate=False),
            _evidence_result(inserted=1, duplicates=0),
        )
    )

    def fake_run(command, **_kwargs):
        calls.append(list(command))
        return _with_command_temporal(next(results), list(command))

    monkeypatch.setattr(runner, "_run_json_cli", fake_run)
    payload = runner.run(
        data_root=tmp_path / "data",
        output_root=tmp_path / "output",
        now=datetime.fromisoformat("2026-09-16T20:25:00+08:00"),
        calendar=_OpenCalendar(),
    )

    assert payload["status"] == "passed"
    assert payload["calendar_decision_at"] == "2026-09-16T08:30:00+08:00"
    assert payload["decision_at"] == "2026-09-16T20:25:00+08:00"
    assert payload["captured_at"] == "2026-09-16T20:25:00+08:00"
    assert payload["capture_mode"] == "eod_research"
    assert payload["preopen_authority"] is False
    assert calls[0][calls[0].index("--decision-at") + 1] == "2026-09-16T20:25:00+08:00"
    assert calls[0][calls[0].index("--as-of") + 1] == "2026-09-16"
    assert calls[0][calls[0].index("--capture-mode") + 1] == "eod_research"


def test_runner_fails_closed_when_child_does_not_echo_temporal_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    results = iter(
        (
            _snapshot_result(saved=True, duplicate=False),
            _evidence_result(inserted=1, duplicates=0),
        )
    )

    def fake_run(command, **_kwargs):
        result = _with_command_temporal(next(results), list(command))
        if "capture_decision_desk_snapshot.py" in command[1]:
            payload = dict(result.payload or {})
            payload["decision_at"] = "2026-09-16T08:30:00+08:00"
            result = runner.CliRunResult(result.returncode, payload, result.stderr)
        return result

    monkeypatch.setattr(runner, "_run_json_cli", fake_run)
    payload = runner.run(
        data_root=tmp_path / "data",
        output_root=tmp_path / "output",
        now=datetime.fromisoformat("2026-09-16T20:25:00+08:00"),
        calendar=_OpenCalendar(),
    )

    assert payload["status"] == "failed"
    assert "temporal_receipt_mismatch:decision_at" in payload["failure_reasons"]
    assert payload["evidence"]["status"] == "not_run"


def test_runner_fails_closed_when_child_persisted_context_is_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    results = iter((_snapshot_result(saved=True, duplicate=False),))

    def fake_run(command, **_kwargs):
        result = _with_command_temporal(next(results), list(command))
        payload = dict(result.payload or {})
        payload.pop("persisted_capture_context", None)
        return runner.CliRunResult(result.returncode, payload, result.stderr)

    monkeypatch.setattr(runner, "_run_json_cli", fake_run)
    payload = runner.run(
        data_root=tmp_path / "data",
        output_root=tmp_path / "output",
        now=datetime.fromisoformat("2026-09-16T20:25:00+08:00"),
        calendar=_OpenCalendar(),
    )

    assert payload["status"] == "failed"
    assert "snapshot_persisted_capture_context_missing" in payload["failure_reasons"]
    assert payload["evidence"]["status"] == "not_run"


def test_snapshot_failure_stops_before_evidence_and_remains_retryable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def fake_run(command, **_kwargs):
        calls.append(list(command))
        return runner.CliRunResult(
            returncode=1,
            payload=None,
            stderr="snapshot failed",
        )

    monkeypatch.setattr(runner, "_run_json_cli", fake_run)
    payload = runner.run(
        data_root=tmp_path / "data",
        output_root=tmp_path / "output",
        now=datetime.fromisoformat("2026-07-30T07:00:00+08:00"),
        calendar=_OpenCalendar(),
    )

    assert payload["status"] == "failed"
    assert payload["evidence"]["status"] == "not_run"
    assert payload["events_inserted"] == 0
    assert payload["events_failures"] == 0
    assert len(calls) == 1


def test_unexpected_snapshot_runner_error_is_persisted_as_failed_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        runner,
        "_run_json_cli",
        lambda _command, **_kwargs: (_ for _ in ()).throw(
            OSError("runner unavailable")
        ),
    )

    payload = runner.run(
        data_root=tmp_path / "data",
        output_root=tmp_path / "output",
        now=datetime.fromisoformat("2026-07-30T07:00:00+08:00"),
        calendar=_OpenCalendar(),
    )

    status_path = (
        tmp_path
        / "output"
        / "scheduled"
        / "decision_evidence_capture"
        / "latest_status.json"
    )
    assert payload["status"] == "failed"
    assert payload["snapshot"]["error_type"] == "OSError"
    assert payload["evidence"]["status"] == "not_run"
    assert json.loads(status_path.read_text(encoding="utf-8"))["status"] == (
        "failed"
    )


def test_evidence_event_failure_marks_whole_run_failed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    results = iter(
        (
            _snapshot_result(saved=False, duplicate=True),
            _evidence_result(inserted=1, duplicates=1, failed=2),
        )
    )
    monkeypatch.setattr(
        runner,
        "_run_json_cli",
        lambda command, **_kwargs: _with_command_temporal(next(results), list(command)),
    )

    payload = runner.run(
        data_root=tmp_path / "data",
        output_root=tmp_path / "output",
        now=datetime.fromisoformat("2026-07-30T20:00:00+08:00"),
        calendar=_OpenCalendar(),
    )

    assert payload["status"] == "failed"
    assert payload["snapshot_duplicate"] is True
    assert payload["events_inserted"] == 1
    assert payload["events_duplicates"] == 1
    assert payload["events_failures"] == 2
    assert "evidence_events_failed:2" in payload["failure_reasons"]


def test_closed_day_persists_skip_without_running_subprocess(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[object] = []
    monkeypatch.setattr(
        runner,
        "_run_json_cli",
        lambda command, **_kwargs: calls.append(command),
    )

    payload = runner.run(
        data_root=tmp_path / "data",
        output_root=tmp_path / "output",
        now=datetime.fromisoformat("2026-08-01T07:00:00+08:00"),
        calendar=_ClosedCalendar(),
    )

    assert payload["status"] == "skipped_non_trading_day"
    assert payload["snapshot"]["status"] == "not_run"
    assert payload["evidence"]["events_seen"] == 0
    assert payload["safety_boundary"]["writes_decision_desk_snapshot"] is False
    assert payload["safety_boundary"]["writes_evidence_events"] is False
    assert calls == []


def test_explicit_closed_decision_at_fails_closed_without_capture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        runner,
        "_run_json_cli",
        lambda *_args, **_kwargs: pytest.fail("不應呼叫 capture CLI"),
    )

    payload = runner.run(
        data_root=tmp_path / "data",
        output_root=tmp_path / "output",
        now=datetime.fromisoformat("2026-07-30T07:00:00+08:00"),
        decision_at=datetime.fromisoformat("2026-08-01T08:30:00+08:00"),
        as_of="2026-08-01",
        captured_at=datetime.fromisoformat("2026-08-01T08:30:00+08:00"),
        calendar_decision_at=datetime.fromisoformat("2026-08-01T08:30:00+08:00"),
        calendar=_ClosedCalendar(),
    )

    assert payload["status"] == "skipped_non_trading_day"
    assert payload["decision_date_basis"] == "explicit_calendar_decision_at"
    assert payload["snapshot_saved"] is False


def test_unknown_calendar_persists_degraded_without_capture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        runner,
        "_run_json_cli",
        lambda *_args, **_kwargs: pytest.fail("不應呼叫 capture CLI"),
    )

    payload = runner.run(
        data_root=tmp_path / "data",
        output_root=tmp_path / "output",
        now=datetime.fromisoformat("2026-07-30T07:00:00+08:00"),
        calendar=_UnknownCalendar(),
    )

    assert payload["status"] == "degraded_calendar_unknown"
    assert payload["trading_calendar_validated"] is False
    assert payload["events_inserted"] == 0


def test_snapshot_requires_all_seven_sections() -> None:
    result = _snapshot_result(saved=True, duplicate=False)
    payload = dict(result.payload or {})
    payload["sections_seen"] = ["market_regime"]
    step, failures = runner._snapshot_step(
        runner.CliRunResult(0, payload, "")
    )

    assert step["status"] == "failed"
    assert any(
        reason.startswith("snapshot_required_sections_missing:")
        for reason in failures
    )


@pytest.mark.parametrize(
    ("inserted", "duplicates"),
    ((0, 0),),
)
def test_zero_event_evidence_cannot_pass(
    inserted: int,
    duplicates: int,
) -> None:
    step, failures = runner._evidence_step(
        _evidence_result(inserted=inserted, duplicates=duplicates)
    )

    assert step["status"] == "failed"
    assert "evidence_events_empty" in failures
    assert "evidence_no_insert_or_duplicate" in failures


def test_duplicate_evidence_is_idempotent_success() -> None:
    step, failures = runner._evidence_step(
        _evidence_result(inserted=0, duplicates=2)
    )

    assert step["status"] == "passed"
    assert failures == []


def test_subprocess_timeout_is_bounded_and_persisted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def timeout_run(*_args, **_kwargs):
        raise runner.subprocess.TimeoutExpired(
            cmd=["python-test"],
            timeout=7,
            stderr="timed out",
        )

    monkeypatch.setattr(runner.subprocess, "run", timeout_run)
    cli_result = runner._run_json_cli(
        ["python-test", "capture.py"],
        timeout_seconds=7,
    )
    assert cli_result.timed_out is True
    assert cli_result.timeout_seconds == 7

    monkeypatch.setattr(
        runner,
        "_run_json_cli",
        lambda *_args, **_kwargs: cli_result,
    )
    payload = runner.run(
        data_root=tmp_path / "data",
        output_root=tmp_path / "output",
        now=datetime.fromisoformat("2026-07-30T07:00:00+08:00"),
        calendar=_OpenCalendar(),
        subprocess_timeout_seconds=7,
    )

    assert payload["status"] == "degraded"
    assert payload["snapshot"]["status"] == "timeout"
    assert payload["snapshot"]["timeout_seconds"] == 7
    assert "snapshot_cli_timeout" in payload["failure_reasons"]
