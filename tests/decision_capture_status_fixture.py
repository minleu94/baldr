"""以既有 capture producer helpers 建立唯讀 status-reader 測試原件。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from app_module import decision_snapshot_diagnostics as snapshot_diagnostics
from app_module import scheduled_writer_reservation as writer_reservation
from scripts.scheduled import run_scheduled_decision_evidence_capture as runner


_TAIPEI = ZoneInfo("Asia/Taipei")


@dataclass(frozen=True)
class DecisionCaptureFixture:
    status_path: Path
    receipt_path: Path
    run_dir: Path
    run_id: str
    decision_date: str
    completed_at: datetime


def _stage_line(sequence: int, stage: str, state: str, elapsed_ms: int) -> str:
    payload: dict[str, Any] = {
        "schema": snapshot_diagnostics.SCHEMA,
        "sequence": sequence,
        "stage": stage,
        "state": state,
        "elapsed_ms": elapsed_ms,
    }
    return snapshot_diagnostics.PREFIX + json.dumps(payload, separators=(",", ":"))


def stage_diagnostic_stderr(*, unfinished_snapshot: bool = False, private_text: str = "") -> str:
    lines = [
        _stage_line(1, "config", "started", 0),
        _stage_line(2, "config", "completed", 2),
        _stage_line(3, "snapshot", "started", 0),
    ]
    if not unfinished_snapshot:
        lines.append(_stage_line(4, "snapshot", "completed", 5))
    if private_text:
        lines.append(private_text)
    return "\n".join(lines) + "\n"


def _fixed_producer_clock(value: datetime | None):
    if value is None:
        return None
    original_datetime = runner.datetime

    class FixedDateTime(original_datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return value.replace(tzinfo=None)
            return value.astimezone(tz)

    runner.datetime = FixedDateTime
    return original_datetime


def create_decision_capture_fixture(
    output_root: Path,
    *,
    producer_now: datetime | None = None,
    decision_date: str | None = None,
    timeout: bool = False,
    private_text: str = "",
) -> DecisionCaptureFixture:
    """呼叫 producer 的 context/artifact/finalizer，避免複製其寫入契約。"""
    if producer_now is not None and (
        producer_now.tzinfo is None or producer_now.utcoffset() is None
    ):
        raise ValueError("producer_now must be timezone-aware")
    fixed_now = (
        producer_now.astimezone(timezone.utc)
        if producer_now is not None
        else datetime.now(timezone.utc)
    )
    original_datetime = _fixed_producer_clock(
        fixed_now if producer_now is not None else None
    )
    try:
        context = runner._create_run_context(Path(output_root))
        stderr = stage_diagnostic_stderr(
            unfinished_snapshot=timeout,
            private_text=private_text,
        )
        if timeout:
            snapshot_result = runner.CliRunResult(
                returncode=None,
                payload=None,
                stderr=stderr,
                timed_out=True,
                timeout_seconds=runner.DEFAULT_SUBPROCESS_TIMEOUT_SECONDS,
                execution_status="timed_out",
            )
            snapshot, failures = runner._snapshot_step(snapshot_result)
            snapshot_execution = runner._persist_cli_result(
                context,
                "snapshot",
                snapshot_result,
            )
            snapshot["execution"] = snapshot_execution
            context.steps["snapshot"] = dict(snapshot)
            payload: dict[str, Any] = {
                "schema_version": runner.SCHEMA_VERSION,
                "task": runner.TASK_NAME,
                "status": "degraded",
                "checked_at": fixed_now.isoformat(timespec="seconds"),
                "decision_date": decision_date
                or fixed_now.astimezone(_TAIPEI).date().isoformat(),
                "snapshot": snapshot,
                "evidence": {
                    "status": "not_run",
                    "events_seen": 0,
                    "events_inserted": 0,
                    "duplicates": 0,
                    "failures": 0,
                },
                "snapshot_saved": snapshot["saved"],
                "snapshot_duplicate": snapshot["duplicate"],
                "failure_reasons": failures,
                "subprocesses": dict(context.subprocesses),
            }
        else:
            snapshot_payload = {
                "dry_run": False,
                "saved": True,
                "skipped_duplicate": False,
                "snapshot_id": "fixture-snapshot",
                "snapshot_hash": "sha256:fixture-snapshot",
                "quality": "observed",
                "sections_seen": sorted(runner.REQUIRED_SNAPSHOT_SECTIONS),
                "sections_missing": [],
                "warnings_count": 0,
            }
            snapshot_result = runner.CliRunResult(
                returncode=0,
                payload=snapshot_payload,
                stderr=stderr,
                stdout=json.dumps(snapshot_payload, sort_keys=True),
            )
            snapshot, snapshot_failures = runner._snapshot_step(snapshot_result)
            snapshot_execution = runner._persist_cli_result(
                context,
                "snapshot",
                snapshot_result,
            )
            snapshot["execution"] = snapshot_execution
            context.steps["snapshot"] = dict(snapshot)

            evidence_payload = {
                "dry_run": False,
                "events_seen": 1,
                "events_inserted": 1,
                "events_skipped_duplicate": 0,
                "events_failed": 0,
                "warnings_count": 0,
                "diagnostics_by_code": {},
                "event_type_counts": {},
                "quality_counts": {},
                "diagnostics": [],
            }
            evidence_result = runner.CliRunResult(
                returncode=0,
                payload=evidence_payload,
                stderr="",
                stdout=json.dumps(evidence_payload, sort_keys=True),
            )
            evidence, evidence_failures = runner._evidence_step(evidence_result)
            evidence_execution = runner._persist_cli_result(
                context,
                "evidence",
                evidence_result,
            )
            evidence["execution"] = evidence_execution
            context.steps["evidence"] = dict(evidence)
            payload = {
                "schema_version": runner.SCHEMA_VERSION,
                "task": runner.TASK_NAME,
                "status": "passed",
                "checked_at": fixed_now.isoformat(timespec="seconds"),
                "decision_date": decision_date
                or fixed_now.astimezone(_TAIPEI).date().isoformat(),
                "snapshot": snapshot,
                "evidence": evidence,
                "snapshot_saved": snapshot["saved"],
                "snapshot_duplicate": snapshot["duplicate"],
                "failure_reasons": snapshot_failures + evidence_failures,
                "subprocesses": dict(context.subprocesses),
            }
        terminal = runner._finalize_run(context, payload)
    finally:
        if original_datetime is not None:
            runner.datetime = original_datetime

    return DecisionCaptureFixture(
        status_path=context.status_path.resolve(),
        receipt_path=context.receipt_path.resolve(),
        run_dir=context.run_dir.resolve(),
        run_id=context.run_id,
        decision_date=str(terminal["decision_date"]),
        completed_at=datetime.fromisoformat(str(terminal["completed_at"])),
    )


def _capture_from_terminal(payload: dict[str, Any]) -> DecisionCaptureFixture:
    return DecisionCaptureFixture(
        status_path=Path(str(payload["status_path"])),
        receipt_path=Path(str(payload["receipt_path"])),
        run_dir=Path(str(payload["run_dir"])),
        run_id=str(payload["run_id"]),
        decision_date=str(payload.get("decision_date", "")),
        completed_at=datetime.fromisoformat(str(payload["completed_at"])),
    )


class _OpenCalendar:
    def is_official_trading_day(self, _target_date):
        return True, "synthetic_test_open"


class _ClosedCalendar:
    def is_official_trading_day(self, _target_date):
        return False, "synthetic_test_closed"


def _run_with_fake_cli(
    output_root: Path,
    *,
    producer_now: datetime,
    monkeypatch,
    calendar,
) -> dict[str, Any]:
    original_datetime = _fixed_producer_clock(producer_now.astimezone(timezone.utc))
    # 單元案例的producer與reservation時鐘須一致，才會抵達指定的失敗階段。
    monkeypatch.setattr(writer_reservation, "_utc_now", lambda: producer_now.astimezone(timezone.utc))
    try:
        return runner.run(
            data_root=Path(output_root).parent / "data",
            output_root=Path(output_root),
            now=producer_now.astimezone(_TAIPEI),
            calendar=calendar,
        )
    finally:
        if original_datetime is not None:
            runner.datetime = original_datetime


def create_prelaunch_failure_fixture(
    output_root: Path,
    *,
    producer_now: datetime,
    monkeypatch,
    error_type: str,
) -> DecisionCaptureFixture:
    error_types = {
        "FileNotFoundError": FileNotFoundError,
        "PermissionError": PermissionError,
        "NotADirectoryError": NotADirectoryError,
        "ValueError": ValueError,
        "TypeError": TypeError,
    }
    error_class = error_types[error_type]

    def fail_before_child(*_args, **_kwargs):
        raise error_class("synthetic child launch failure")

    monkeypatch.setattr(runner, "_run_json_cli", fail_before_child)
    payload = _run_with_fake_cli(
        output_root,
        producer_now=producer_now,
        monkeypatch=monkeypatch,
        calendar=_OpenCalendar(),
    )
    return _capture_from_terminal(payload)


def create_no_child_skipped_fixture(
    output_root: Path,
    *,
    producer_now: datetime,
    monkeypatch,
) -> DecisionCaptureFixture:
    def unexpected_child(*_args, **_kwargs):
        raise AssertionError("closed calendar must not launch a child")

    monkeypatch.setattr(runner, "_run_json_cli", unexpected_child)
    payload = _run_with_fake_cli(
        output_root,
        producer_now=producer_now,
        monkeypatch=monkeypatch,
        calendar=_ClosedCalendar(),
    )
    return _capture_from_terminal(payload)


def create_pending_artifact_fixture(
    output_root: Path,
    *,
    producer_now: datetime,
    monkeypatch,
) -> DecisionCaptureFixture:
    snapshot_payload = {
        "dry_run": False,
        "saved": True,
        "skipped_duplicate": False,
        "snapshot_id": "pending-artifact-snapshot",
        "snapshot_hash": "sha256:pending-artifact-snapshot",
        "quality": "observed",
        "sections_seen": sorted(runner.REQUIRED_SNAPSHOT_SECTIONS),
        "sections_missing": [],
        "warnings_count": 0,
    }

    def return_child(*_args, **_kwargs):
        return runner.CliRunResult(
            returncode=0,
            payload=snapshot_payload,
            stderr="",
            stdout=json.dumps(snapshot_payload, sort_keys=True),
        )

    original_publish = runner._publish_create_only_bytes

    def fail_artifact_write(path, content):
        if Path(path).name.endswith((".stdout.txt", ".stderr.txt")):
            raise OSError("synthetic child artifact write failure")
        return original_publish(path, content)

    monkeypatch.setattr(runner, "_run_json_cli", return_child)
    monkeypatch.setattr(runner, "_publish_create_only_bytes", fail_artifact_write)
    payload = _run_with_fake_cli(
        output_root,
        producer_now=producer_now,
        monkeypatch=monkeypatch,
        calendar=_OpenCalendar(),
    )
    return _capture_from_terminal(payload)
