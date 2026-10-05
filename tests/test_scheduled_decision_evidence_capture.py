from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sys

import pytest

from app_module.evidence_event_importer_dtos import (
    EvidenceCaptureRequest,
    capture_context_identity,
)
from app_module.scheduled_writer_reservation import ScheduledWriterReservationWait
from data_module.ml_storage_capacity import (
    acquire_heavy_chain_reservation,
    heavy_chain_lock_path,
    release_heavy_chain_reservation,
)
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
        stdout=result.stdout,
        stdout_truncated=result.stdout_truncated,
        stderr_truncated=result.stderr_truncated,
        stdout_byte_count=result.stdout_byte_count,
        stderr_byte_count=result.stderr_byte_count,
        stdout_sha256=result.stdout_sha256,
        stderr_sha256=result.stderr_sha256,
        stdout_artifact=result.stdout_artifact,
        stderr_artifact=result.stderr_artifact,
        execution_status=result.execution_status,
        execution_error_type=result.execution_error_type,
        execution_error=result.execution_error,
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
    child_timeouts: list[float] = []
    results = iter(
        (
            _snapshot_result(saved=True, duplicate=False),
            _evidence_result(inserted=1, duplicates=0),
        )
    )

    def fake_run(command, **kwargs):
        competing = acquire_heavy_chain_reservation(
            heavy_chain_lock_path(tmp_path / "output" / "release_v4")
        )
        assert competing is None
        calls.append(list(command))
        child_timeouts.append(kwargs["timeout_seconds"])
        return _with_command_temporal(next(results), list(command))

    wait_arguments: dict[str, object] = {}
    original_wait = runner.wait_for_scheduled_writer_reservation

    def track_wait(**kwargs):
        wait_arguments.update(kwargs)
        return original_wait(**kwargs)

    monkeypatch.setattr(runner, "wait_for_scheduled_writer_reservation", track_wait)
    monkeypatch.setattr(runner, "_run_json_cli", fake_run)
    payload = runner.run(
        data_root=tmp_path / "data",
        output_root=tmp_path / "output",
        now=datetime.fromisoformat("2026-09-16T20:25:00.123456+08:00"),
        calendar=_OpenCalendar(),
    )

    assert payload["status"] == "passed"
    assert payload["calendar_decision_at"] == "2026-09-16T08:30:00+08:00"
    assert payload["decision_at"] == "2026-09-16T20:25:00.123456+08:00"
    assert payload["captured_at"] == "2026-09-16T20:25:00.123456+08:00"
    assert payload["capture_mode"] == "eod_research"
    assert payload["reservation_wait"]["status"] == "acquired"
    assert payload["reservation_acquire_guard"]["passed"] is True
    assert wait_arguments["timeout_seconds"] == runner.SCHEDULED_WRITER_RESERVATION_TIMEOUT_SECONDS
    assert wait_arguments["latest_acquire_at"] == datetime.fromisoformat(
        payload["reservation_acquire_guard"]["latest_acquire_at"]
    )
    assert child_timeouts == [120, 120]
    assert payload["preopen_authority"] is False
    assert (
        payload["capture_context_hash"]
        == payload["snapshot"]["capture_context_hash"]
    )
    assert (
        payload["capture_context_identity_hash"]
        == payload["snapshot"]["capture_context_identity_hash"]
    )
    assert (
        calls[0][calls[0].index("--decision-at") + 1]
        == "2026-09-16T20:25:00.123456+08:00"
    )
    assert calls[0][calls[0].index("--as-of") + 1] == "2026-09-16"
    assert calls[0][calls[0].index("--capture-mode") + 1] == "eod_research"
    after_release = acquire_heavy_chain_reservation(
        heavy_chain_lock_path(tmp_path / "output" / "release_v4")
    )
    assert after_release is not None
    release_heavy_chain_reservation(after_release)


def test_natural_capture_clock_is_sampled_after_reservation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    results = iter(
        (
            _snapshot_result(saved=True, duplicate=False),
            _evidence_result(inserted=1, duplicates=0),
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
        calendar=_OpenCalendar(),
    )

    assert payload["status"] == "passed"
    assert payload["reservation_wait"]["status"] == "acquired"
    checked_at = datetime.fromisoformat(payload["captured_at"]).astimezone(timezone.utc)
    wait_ended_at = datetime.fromisoformat(
        str(payload["reservation_wait"]["wait_ended_at_utc"]).replace("Z", "+00:00")
    )
    assert checked_at >= wait_ended_at


def test_canonical_db_uses_configured_lock_when_receipts_go_to_shadow_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    canonical_data = tmp_path / "canonical-data"
    canonical_output = tmp_path / "canonical-output"
    shadow_output = tmp_path / "shadow-output"
    monkeypatch.setenv("DATA_ROOT", str(canonical_data))
    monkeypatch.setenv("OUTPUT_ROOT", str(canonical_output))
    results = iter(
        (
            _snapshot_result(saved=True, duplicate=False),
            _evidence_result(inserted=1, duplicates=0),
        )
    )

    def fake_run(command, **_kwargs):
        competing = acquire_heavy_chain_reservation(
            heavy_chain_lock_path(canonical_output / "release_v4")
        )
        assert competing is None
        return _with_command_temporal(next(results), list(command))

    monkeypatch.setattr(runner, "_run_json_cli", fake_run)
    payload = runner.run(
        data_root=canonical_data,
        output_root=shadow_output,
        db_path=canonical_data / "sqlite" / "twstock.db",
        now=datetime.fromisoformat("2026-07-30T09:00:00+08:00"),
        calendar=_OpenCalendar(),
    )

    assert payload["status"] == "passed"
    assert payload["canonical_reservation_root"] == str(canonical_output.resolve())
    assert payload["artifact_output_root"] == str(shadow_output.resolve())
    assert str(payload["status_path"]).startswith(str(shadow_output.resolve()))
    after_release = acquire_heavy_chain_reservation(
        heavy_chain_lock_path(canonical_output / "release_v4")
    )
    assert after_release is not None
    release_heavy_chain_reservation(after_release)


def test_subsecond_decision_identity_and_captured_retry_contract() -> None:
    first = EvidenceCaptureRequest(
        source="test",
        decision_date="2026-09-16",
        as_of="2026-09-16",
        decision_at="2026-09-16T20:25:00.123456+08:00",
        captured_at="2026-09-16T20:25:00.223456+08:00",
        capture_mode="research_only",
    )
    different_decision = EvidenceCaptureRequest(
        source="test",
        decision_date="2026-09-16",
        as_of="2026-09-16",
        decision_at="2026-09-16T20:25:00.123457+08:00",
        captured_at="2026-09-16T20:25:00.223456+08:00",
        capture_mode="research_only",
    )
    retry = EvidenceCaptureRequest(
        source="test",
        decision_date="2026-09-16",
        as_of="2026-09-16",
        decision_at="2026-09-16T20:25:00.123456+08:00",
        captured_at="2026-09-16T20:25:01.223456+08:00",
        capture_mode="research_only",
    )

    first_context = first.capture_context
    different_decision_context = different_decision.capture_context
    retry_context = retry.capture_context
    assert first_context is not None
    assert different_decision_context is not None
    assert retry_context is not None
    assert capture_context_identity(first_context) != capture_context_identity(
        different_decision_context
    )
    assert (
        first.temporal_summary["capture_context_identity_hash"]
        != different_decision.temporal_summary["capture_context_identity_hash"]
    )
    assert capture_context_identity(first_context) == capture_context_identity(
        retry_context
    )
    assert (
        first.temporal_summary["capture_context_hash"]
        != retry.temporal_summary["capture_context_hash"]
    )


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
            FileNotFoundError("runner unavailable")
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
    assert payload["snapshot"]["error_type"] == "FileNotFoundError"
    assert payload["snapshot"]["status"] == "unknown"
    assert payload["subprocesses"]["snapshot"]["launch_status"] == "failed"
    assert payload["subprocesses"]["snapshot"]["returncode"] is None
    assert Path(payload["receipt_path"]).exists()
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
    monkeypatch.setattr(
        runner,
        "wait_for_scheduled_writer_reservation",
        lambda **_kwargs: pytest.fail("closed days must not wait for the writer lock"),
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
    monkeypatch.setattr(
        runner,
        "wait_for_scheduled_writer_reservation",
        lambda **_kwargs: pytest.fail("unknown calendar must not wait for the writer lock"),
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
    monkeypatch.setattr(
        runner,
        "wait_for_scheduled_writer_reservation",
        lambda **_kwargs: pytest.fail("unknown calendar must not wait for the writer lock"),
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


def test_writer_reservation_timeout_blocks_without_launching_children(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    timeout_receipt = {
        "schema_version": "scheduled-writer-reservation-wait.v1",
        "status": "timed_out",
        "attempt_count": 2,
        "lock_path": str(heavy_chain_lock_path(tmp_path / "output" / "release_v4")),
    }
    monkeypatch.setattr(
        runner,
        "wait_for_scheduled_writer_reservation",
        lambda **_kwargs: ScheduledWriterReservationWait(None, timeout_receipt),
    )
    monkeypatch.setattr(
        runner,
        "_run_json_cli",
        lambda *_args, **_kwargs: pytest.fail("capture child ran after lock timeout"),
    )

    payload = runner.run(
        data_root=tmp_path / "data",
        output_root=tmp_path / "output",
        now=datetime.fromisoformat("2026-07-30T09:00:00+08:00"),
        calendar=_OpenCalendar(),
    )

    assert payload["status"] == "blocked_reservation_timeout"
    assert payload["reservation_wait"] == timeout_receipt
    assert payload["snapshot"]["status"] == "not_run"
    assert payload["evidence"]["status"] == "not_run"
    assert payload["safety_boundary"]["writes_decision_desk_snapshot"] is False
    assert payload["safety_boundary"]["writes_evidence_events"] is False


def test_acquire_guard_rejects_wall_clock_jump_past_completion_reserve(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_datetime = runner.datetime
    before = original_datetime.fromisoformat("2026-10-04T10:00:00+08:00")
    after_cutoff = original_datetime.fromisoformat("2026-10-04T23:58:00+08:00")
    calls = 0

    class JumpClock(original_datetime):
        @classmethod
        def now(cls, tz=None):
            nonlocal calls
            if tz == runner.TAIPEI:
                calls += 1
                return before if calls == 1 else after_cutoff
            return original_datetime.now(tz)

    def acquire_immediately(**kwargs):
        lease = acquire_heavy_chain_reservation(
            heavy_chain_lock_path(Path(kwargs["release_root"]))
        )
        assert lease is not None
        return ScheduledWriterReservationWait(
            lease,
            {"schema_version": "scheduled-writer-reservation-wait.v1", "status": "acquired"},
        )

    monkeypatch.setattr(runner, "datetime", JumpClock)
    monkeypatch.setattr(runner, "wait_for_scheduled_writer_reservation", acquire_immediately)
    monkeypatch.setattr(
        runner,
        "_run_json_cli",
        lambda *_args, **_kwargs: pytest.fail("capture child ran past completion cutoff"),
    )

    payload = runner.run(
        data_root=tmp_path / "data",
        output_root=tmp_path / "output",
        calendar=_OpenCalendar(),
    )

    assert payload["status"] == "blocked_reservation_acquire_guard"
    assert payload["failure_reasons"] == ["heavy_chain_reservation_after_completion_cutoff"]
    assert payload["reservation_acquire_guard"]["passed"] is False
    after_release = acquire_heavy_chain_reservation(
        heavy_chain_lock_path(tmp_path / "output" / "release_v4")
    )
    assert after_release is not None
    release_heavy_chain_reservation(after_release)


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


def test_real_child_nonzero_after_isolated_write_keeps_write_state_unknown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    marker = tmp_path / "snapshot-side-effect.txt"
    original_run_json_cli = runner._run_json_cli

    def fake_run(_command, **kwargs):
        child_code = (
            "from pathlib import Path; "
            f"Path({str(marker)!r}).write_text('committed-before-exit', encoding='utf-8'); "
            "import sys; sys.stderr.write('child failed\\n'); sys.exit(7)"
        )
        return original_run_json_cli(
            [sys.executable, "-c", child_code],
            timeout_seconds=kwargs["timeout_seconds"],
        )

    monkeypatch.setattr(runner, "_run_json_cli", fake_run)
    payload = runner.run(
        data_root=tmp_path / "data",
        output_root=tmp_path / "output",
        now=datetime.fromisoformat("2026-07-30T09:00:00+08:00"),
        calendar=_OpenCalendar(),
    )

    assert marker.read_text(encoding="utf-8") == "committed-before-exit"
    assert payload["status"] == "failed"
    assert payload["snapshot"]["saved"] is None
    assert payload["snapshot"]["duplicate"] is None
    assert payload["snapshot_saved"] is None
    assert payload["safety_boundary"]["writes_decision_desk_snapshot"] is None
    assert payload["subprocesses"]["snapshot"]["returncode"] == 7
    assert payload["subprocesses"]["snapshot"]["artifact_status"] == "complete"
    assert payload["evidence"]["status"] == "not_run"


def test_invalid_utf8_child_output_keeps_returncode_and_raw_hash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_run_json_cli = runner._run_json_cli

    def fake_run(_command, **kwargs):
        child_code = (
            "import sys; "
            "sys.stdout.buffer.write(b'\\xff\\xfe'); "
            "sys.stderr.buffer.write(b'bad utf8\\n'); "
            "sys.exit(11)"
        )
        return original_run_json_cli(
            [sys.executable, "-c", child_code],
            timeout_seconds=kwargs["timeout_seconds"],
        )

    monkeypatch.setattr(runner, "_run_json_cli", fake_run)
    payload = runner.run(
        data_root=tmp_path / "data",
        output_root=tmp_path / "output",
        now=datetime.fromisoformat("2026-07-30T09:00:00+08:00"),
        calendar=_OpenCalendar(),
    )

    execution = payload["subprocesses"]["snapshot"]
    assert payload["status"] == "failed"
    assert payload["snapshot"]["saved"] is None
    assert payload["safety_boundary"]["writes_decision_desk_snapshot"] is None
    assert execution["returncode"] == 11
    assert execution["stdout_byte_count"] == 2
    raw_stdout = bytes((0xFF, 0xFE))
    assert execution["stdout_sha256"] == hashlib.sha256(raw_stdout).hexdigest()
    assert Path(execution["stdout_path"]).read_bytes() == raw_stdout
    assert payload["evidence"]["status"] == "not_run"


def test_real_child_timeout_after_isolated_write_keeps_write_state_unknown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    marker = tmp_path / "snapshot-timeout-side-effect.txt"
    original_run_json_cli = runner._run_json_cli

    def fake_run(_command, **kwargs):
        child_code = (
            "from pathlib import Path; "
            f"Path({str(marker)!r}).write_text('committed-before-timeout', encoding='utf-8'); "
            "import time; time.sleep(2)"
        )
        return original_run_json_cli(
            [sys.executable, "-c", child_code],
            timeout_seconds=kwargs["timeout_seconds"],
        )

    monkeypatch.setattr(runner, "_run_json_cli", fake_run)
    payload = runner.run(
        data_root=tmp_path / "data",
        output_root=tmp_path / "output",
        now=datetime.fromisoformat("2026-07-30T09:00:00+08:00"),
        calendar=_OpenCalendar(),
        subprocess_timeout_seconds=0.1,
    )

    assert marker.read_text(encoding="utf-8") == "committed-before-timeout"
    assert payload["status"] == "degraded"
    assert payload["snapshot"]["status"] == "timeout"
    assert payload["snapshot"]["saved"] is None
    assert payload["snapshot_saved"] is None
    assert payload["safety_boundary"]["writes_decision_desk_snapshot"] is None
    assert payload["subprocesses"]["snapshot"]["returncode"] is None
    assert payload["subprocesses"]["snapshot"]["timed_out"] is True
    assert payload["evidence"]["status"] == "not_run"


def test_real_evidence_child_nonzero_after_isolated_write_keeps_counts_unknown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    marker = tmp_path / "evidence-side-effect.txt"
    original_run_json_cli = runner._run_json_cli
    calls = 0

    def fake_run(command, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return _with_command_temporal(
                _snapshot_result(saved=True, duplicate=False),
                list(command),
            )
        child_code = (
            "from pathlib import Path; "
            f"Path({str(marker)!r}).write_text('event-committed-before-exit', encoding='utf-8'); "
            "import sys; sys.exit(9)"
        )
        return original_run_json_cli(
            [sys.executable, "-c", child_code],
            timeout_seconds=kwargs["timeout_seconds"],
        )

    monkeypatch.setattr(runner, "_run_json_cli", fake_run)
    payload = runner.run(
        data_root=tmp_path / "data",
        output_root=tmp_path / "output",
        now=datetime.fromisoformat("2026-07-30T09:00:00+08:00"),
        calendar=_OpenCalendar(),
    )

    assert marker.read_text(encoding="utf-8") == "event-committed-before-exit"
    assert payload["status"] == "failed"
    assert payload["snapshot"]["status"] == "passed"
    assert payload["evidence"]["status"] == "failed"
    assert payload["evidence"]["events_seen"] is None
    assert payload["evidence"]["events_inserted"] is None
    assert payload["evidence"]["duplicates"] is None
    assert payload["evidence"]["failures"] is None
    assert payload["events_inserted"] is None
    assert payload["safety_boundary"]["writes_evidence_events"] is None
    assert payload["subprocesses"]["evidence"]["returncode"] == 9


def test_post_start_exception_preserves_available_streams_as_unknown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _PostStartError(RuntimeError):
        stdout = b"partial stdout\\n"
        stderr = b"partial stderr\\n"

    def raise_after_start(*_args, **_kwargs):
        raise _PostStartError("communicate failed after child start")

    monkeypatch.setattr(runner.subprocess, "run", raise_after_start)
    payload = runner.run(
        data_root=tmp_path / "data",
        output_root=tmp_path / "output",
        now=datetime.fromisoformat("2026-07-30T09:00:00+08:00"),
        calendar=_OpenCalendar(),
    )

    execution = payload["subprocesses"]["snapshot"]
    assert payload["status"] == "failed"
    assert payload["snapshot"]["status"] == "unknown"
    assert payload["snapshot"]["saved"] is None
    assert payload["safety_boundary"]["writes_decision_desk_snapshot"] is None
    assert execution["launch_status"] == "unknown"
    assert execution["execution_status"] == "unknown"
    assert execution["execution_error_type"] == "_PostStartError"
    assert execution["artifact_status"] == "complete"
    assert Path(execution["stdout_path"]).read_bytes() == b"partial stdout\\n"
    assert Path(execution["stderr_path"]).read_bytes() == b"partial stderr\\n"


def test_real_child_success_preserves_json_and_output_metadata() -> None:
    result = runner._run_json_cli(
        [
            sys.executable,
            "-c",
            "import sys; sys.stdout.buffer.write(b'{\"ok\": true}\\n'); sys.stderr.buffer.write(b'diagnostic\\n')",
        ]
    )

    assert result.returncode == 0
    assert result.payload == {"ok": True}
    assert result.stdout == '{"ok": true}\n'
    assert result.stderr == "diagnostic\n"
    assert result.stdout_artifact == result.stdout.encode("utf-8")
    assert result.stdout_byte_count == len(result.stdout_artifact)
    assert result.stderr_byte_count == len(result.stderr.encode("utf-8"))
    assert result.stdout_sha256 == hashlib.sha256(result.stdout_artifact).hexdigest()


def test_real_child_nonzero_preserves_returncode_and_stderr() -> None:
    result = runner._run_json_cli(
        [
            sys.executable,
            "-c",
            "import sys; sys.stdout.write('partial'); sys.stderr.write('boom'); sys.exit(7)",
        ]
    )

    assert result.returncode == 7
    assert result.payload is None
    assert result.stdout == "partial"
    assert result.stderr == "boom"
    assert result.timed_out is False


def test_real_child_timeout_has_no_synthetic_returncode() -> None:
    result = runner._run_json_cli(
        [sys.executable, "-c", "import time; time.sleep(2)"],
        timeout_seconds=0.1,
    )

    assert result.timed_out is True
    assert result.returncode is None
    assert result.timeout_seconds == 0.1


def test_terminal_receipt_is_immutable_and_latest_points_to_new_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    results = iter(
        (
            _snapshot_result(saved=True, duplicate=False),
            _evidence_result(inserted=1, duplicates=0),
            _snapshot_result(saved=True, duplicate=False),
            _evidence_result(inserted=1, duplicates=0),
        )
    )
    large_stdout = "x" * (runner.MAX_CHILD_OUTPUT_BYTES + 101)

    def fake_run(command, **_kwargs):
        result = _with_command_temporal(next(results), list(command))
        return runner.CliRunResult(
            returncode=result.returncode,
            payload=result.payload,
            stderr="child-stderr",
            stdout=large_stdout,
        )

    monkeypatch.setattr(runner, "_run_json_cli", fake_run)
    common = {
        "data_root": tmp_path / "data",
        "output_root": tmp_path / "output",
        "now": datetime.fromisoformat("2026-07-30T09:00:00+08:00"),
        "calendar": _OpenCalendar(),
    }
    first = runner.run(**common)
    first_receipt_path = Path(first["receipt_path"])
    first_receipt_bytes = first_receipt_path.read_bytes()
    first_receipt = json.loads(first_receipt_bytes.decode("utf-8"))
    first_execution = first["subprocesses"]["snapshot"]
    first_artifact = Path(first_execution["stdout_path"]).read_bytes()

    second = runner.run(**common)
    second_receipt_path = Path(second["receipt_path"])
    latest = json.loads(
        (
            tmp_path
            / "output"
            / "scheduled"
            / "decision_evidence_capture"
            / "latest_status.json"
        ).read_text(encoding="utf-8")
    )

    assert first["status"] == "passed"
    assert first["receipt_status"] == "complete"
    assert first_receipt["receipt_status"] == "complete"
    assert first["receipt_sha256"] == hashlib.sha256(first_receipt_bytes).hexdigest()
    assert first_execution["stdout_truncated"] is True
    assert first_execution["stdout_byte_count"] == len(large_stdout.encode("utf-8"))
    assert first_execution["stdout_sha256"] == hashlib.sha256(
        large_stdout.encode("utf-8")
    ).hexdigest()
    assert len(first_artifact) <= runner.MAX_CHILD_OUTPUT_BYTES
    assert first_execution["stdout_artifact_byte_count"] == len(first_artifact)
    assert first_execution["stdout_artifact_sha256"] == hashlib.sha256(
        first_artifact
    ).hexdigest()
    assert second["run_id"] != first["run_id"]
    assert second_receipt_path != first_receipt_path
    assert first_receipt_path.read_bytes() == first_receipt_bytes
    assert latest["run_id"] == second["run_id"]
    assert latest["receipt_path"] == str(second_receipt_path.resolve())


def test_receipt_write_error_cannot_report_passed(
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
        return _with_command_temporal(next(results), list(command))

    monkeypatch.setattr(runner, "_run_json_cli", fake_run)
    monkeypatch.setattr(
        runner,
        "_write_immutable_json",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("receipt disk full")),
    )

    payload = runner.run(
        data_root=tmp_path / "data",
        output_root=tmp_path / "output",
        now=datetime.fromisoformat("2026-07-30T09:00:00+08:00"),
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
    assert payload["receipt_status"] == "write_failed"
    assert any(
        reason.startswith("receipt_write_failed:OSError")
        for reason in payload["failure_reasons"]
    )
    assert json.loads(status_path.read_text(encoding="utf-8"))["status"] == "failed"


def test_immutable_receipt_publish_never_overwrites_existing_file(
    tmp_path: Path,
) -> None:
    receipt_path = tmp_path / "receipt.json"
    runner._write_immutable_json(receipt_path, {"run_id": "first"})
    original = receipt_path.read_bytes()

    with pytest.raises(FileExistsError):
        runner._write_immutable_json(receipt_path, {"run_id": "second"})

    assert receipt_path.read_bytes() == original


def test_exception_after_successful_children_preserves_known_step_state(
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
        return _with_command_temporal(next(results), list(command))

    original_context_reader = runner._persisted_capture_context
    read_count = 0

    def fail_after_child_steps(payload):
        nonlocal read_count
        read_count += 1
        if read_count == 5:
            raise RuntimeError("post-child receipt assembly failed")
        return original_context_reader(payload)

    monkeypatch.setattr(runner, "_run_json_cli", fake_run)
    monkeypatch.setattr(
        runner,
        "_persisted_capture_context",
        fail_after_child_steps,
    )

    payload = runner.run(
        data_root=tmp_path / "data",
        output_root=tmp_path / "output",
        now=datetime.fromisoformat("2026-07-30T09:00:00+08:00"),
        calendar=_OpenCalendar(),
    )

    assert payload["status"] == "failed"
    assert payload["snapshot"]["status"] == "passed"
    assert payload["snapshot"]["saved"] is True
    assert payload["evidence"]["status"] == "passed"
    assert payload["evidence"]["events_inserted"] == 1
    assert payload["safety_boundary"]["writes_decision_desk_snapshot"] is True
    assert payload["safety_boundary"]["writes_evidence_events"] is True
    assert any(
        reason.startswith("orchestrator_exception:RuntimeError")
        for reason in payload["failure_reasons"]
    )


def test_child_return_then_artifact_io_error_is_unknown_write_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(command, **_kwargs):
        result = _with_command_temporal(
            _snapshot_result(saved=True, duplicate=False),
            list(command),
        )
        return result

    original_publisher = runner._publish_create_only_bytes

    def fail_stdout_artifact(path: Path, content: bytes) -> None:
        if path.name == "snapshot.stdout.txt":
            raise OSError("artifact disk full")
        original_publisher(path, content)

    monkeypatch.setattr(runner, "_run_json_cli", fake_run)
    monkeypatch.setattr(
        runner,
        "_publish_create_only_bytes",
        fail_stdout_artifact,
    )

    payload = runner.run(
        data_root=tmp_path / "data",
        output_root=tmp_path / "output",
        now=datetime.fromisoformat("2026-07-30T09:00:00+08:00"),
        calendar=_OpenCalendar(),
    )

    assert payload["status"] == "failed"
    assert payload["snapshot"]["status"] == "unknown"
    assert payload["snapshot"]["saved"] is None
    assert payload["safety_boundary"]["writes_decision_desk_snapshot"] is None
    assert payload["subprocesses"]["snapshot"]["returncode"] == 0
    assert payload["subprocesses"]["snapshot"]["artifact_status"] == "pending"
    assert payload["evidence"]["status"] == "not_run"
