from __future__ import annotations

from datetime import datetime, timedelta, timezone
import multiprocessing
from multiprocessing.queues import Queue
import os
from pathlib import Path
from queue import Empty
import time
from typing import Any

import pytest

from app_module import scheduled_writer_reservation as reservation_module
from app_module.scheduled_writer_reservation import (
    ScheduledWriterReservationError,
    ScheduledWriterReservationWait,
    wait_for_scheduled_writer_reservation,
)
from data_module.ml_storage_capacity import (
    HEAVY_CHAIN_LOCK_FILENAME,
    StorageCapacityError,
    acquire_heavy_chain_reservation,
    heavy_chain_lock_path,
    release_heavy_chain_reservation,
)


@pytest.fixture
def fake_clock(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    clock: dict[str, Any] = {
        "wall": datetime(2026, 10, 4, 23, 59, 59, tzinfo=timezone.utc),
        "monotonic": 100.0,
        "rollback_wall": False,
    }

    def wall_now() -> datetime:
        return clock["wall"]

    def monotonic_now() -> float:
        return clock["monotonic"]

    def sleep(seconds: float) -> None:
        clock["monotonic"] += seconds
        if clock["rollback_wall"]:
            clock["wall"] -= timedelta(seconds=seconds)
        else:
            clock["wall"] += timedelta(seconds=seconds)

    monkeypatch.setattr(reservation_module, "_utc_now", wall_now)
    monkeypatch.setattr(reservation_module, "_monotonic", monotonic_now)
    monkeypatch.setattr(reservation_module, "_sleep", sleep)
    return clock


def _cross_process_reservation_wait_worker(
    release_root: str,
    progress_queue: Queue[dict[str, object]],
) -> None:
    latest = datetime.now(timezone.utc) + timedelta(seconds=15)

    def report_progress(payload: Any) -> None:
        progress_queue.put(dict(payload))

    waited = wait_for_scheduled_writer_reservation(
        release_root=Path(release_root),
        timeout_seconds=15.0,
        latest_acquire_at=latest,
        poll_interval_seconds=0.02,
        heartbeat_interval_seconds=0.1,
        on_progress=report_progress,
    )
    progress_queue.put(
        {
            "worker_result": True,
            "status": waited.receipt["status"],
            "attempt_count": waited.receipt["attempt_count"],
        }
    )
    try:
        if waited.reservation is None:
            raise AssertionError("cross-process waiter did not acquire after release")
    finally:
        release_heavy_chain_reservation(waited.reservation)


@pytest.mark.parametrize("timeout", [-1.0, float("nan"), float("inf"), 86401.0, True])
def test_rejects_invalid_or_unbounded_timeout_before_lock_attempt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    timeout: float,
) -> None:
    called = False

    def acquire(_path: Path) -> None:
        nonlocal called
        called = True
        return None

    monkeypatch.setattr(reservation_module, "acquire_heavy_chain_reservation", acquire)
    with pytest.raises(ValueError, match="timeout_seconds"):
        wait_for_scheduled_writer_reservation(
            release_root=tmp_path,
            timeout_seconds=timeout,
            latest_acquire_at=datetime.now(timezone.utc) + timedelta(seconds=10),
        )
    assert called is False


@pytest.mark.parametrize(
    ("parameter", "value"),
    [
        ("poll_interval_seconds", 0.0),
        ("poll_interval_seconds", float("nan")),
        ("poll_interval_seconds", 61.0),
        ("heartbeat_interval_seconds", 0.0),
        ("heartbeat_interval_seconds", float("inf")),
        ("heartbeat_interval_seconds", 3601.0),
    ],
)
def test_rejects_invalid_wait_intervals_before_lock_attempt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    parameter: str,
    value: float,
) -> None:
    called = False

    def acquire(_path: Path) -> None:
        nonlocal called
        called = True
        return None

    monkeypatch.setattr(reservation_module, "acquire_heavy_chain_reservation", acquire)
    kwargs: dict[str, object] = {
        "release_root": tmp_path,
        "timeout_seconds": 1.0,
        "latest_acquire_at": datetime.now(timezone.utc) + timedelta(seconds=10),
        parameter: value,
    }
    with pytest.raises(ValueError, match=parameter):
        wait_for_scheduled_writer_reservation(**kwargs)  # type: ignore[arg-type]
    assert called is False


def test_latest_acquire_at_must_be_aware(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def acquire(_path: Path) -> None:
        nonlocal called
        called = True
        return None

    monkeypatch.setattr(reservation_module, "acquire_heavy_chain_reservation", acquire)
    with pytest.raises(ValueError, match="latest_acquire_at must be an aware datetime"):
        wait_for_scheduled_writer_reservation(
            release_root=tmp_path,
            timeout_seconds=1.0,
            latest_acquire_at=datetime(2026, 10, 5),
        )
    assert called is False


def test_busy_lock_times_out_at_absolute_deadline_across_midnight(
    tmp_path: Path,
    fake_clock: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    latest = datetime(
        2026,
        10,
        5,
        8,
        0,
        0,
        tzinfo=timezone(timedelta(hours=8)),
    )
    monkeypatch.setattr(
        reservation_module,
        "acquire_heavy_chain_reservation",
        lambda _path: None,
    )
    progress: list[dict[str, object]] = []

    result = wait_for_scheduled_writer_reservation(
        release_root=tmp_path,
        timeout_seconds=20.0,
        latest_acquire_at=latest,
        poll_interval_seconds=0.2,
        heartbeat_interval_seconds=0.25,
        on_progress=lambda item: progress.append(dict(item)),
    )

    assert result.reservation is None
    assert result.receipt["status"] == "timed_out"
    assert result.receipt["effective_deadline_at_utc"] == (
        "2026-10-05T00:00:00.000000Z"
    )
    attempt_count = result.receipt["attempt_count"]
    elapsed_seconds = result.receipt["elapsed_seconds"]
    assert isinstance(attempt_count, int) and attempt_count > 0
    assert isinstance(elapsed_seconds, (int, float))
    assert elapsed_seconds == pytest.approx(1.0)
    phases = [item["progress_phase"] for item in progress]
    assert phases[0] == "initial"
    assert phases[-1] == "terminal"
    assert len(phases) > 2
    assert set(phases[1:-1]) == {"heartbeat"}
    assert progress[-1]["status"] == "timed_out"


def test_relative_timeout_uses_monotonic_time_when_wall_clock_moves_back(
    tmp_path: Path,
    fake_clock: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_clock["rollback_wall"] = True
    latest = fake_clock["wall"] + timedelta(seconds=10)
    monkeypatch.setattr(
        reservation_module,
        "acquire_heavy_chain_reservation",
        lambda _path: None,
    )

    result = wait_for_scheduled_writer_reservation(
        release_root=tmp_path,
        timeout_seconds=1.0,
        latest_acquire_at=latest,
        poll_interval_seconds=0.25,
        heartbeat_interval_seconds=0.5,
    )

    assert result.receipt["status"] == "timed_out"
    assert result.receipt["elapsed_seconds"] == pytest.approx(1.0)
    assert result.receipt["effective_deadline_at_utc"] == (
        "2026-10-05T00:00:00.000000Z"
    )
    assert result.receipt["attempt_count"] == 4


def test_immediate_expired_deadline_does_not_attempt_acquisition(
    tmp_path: Path,
    fake_clock: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def acquire(_path: Path) -> None:
        nonlocal called
        called = True
        return None

    monkeypatch.setattr(reservation_module, "acquire_heavy_chain_reservation", acquire)
    result = wait_for_scheduled_writer_reservation(
        release_root=tmp_path,
        timeout_seconds=10.0,
        latest_acquire_at=fake_clock["wall"] - timedelta(microseconds=1),
    )
    assert result.receipt["status"] == "timed_out"
    assert result.receipt["attempt_count"] == 0
    assert called is False


def test_zero_timeout_is_an_immediate_bounded_timeout(
    tmp_path: Path,
    fake_clock: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def acquire(_path: Path) -> None:
        nonlocal called
        called = True
        return None

    monkeypatch.setattr(reservation_module, "acquire_heavy_chain_reservation", acquire)
    result = wait_for_scheduled_writer_reservation(
        release_root=tmp_path,
        timeout_seconds=0.0,
        latest_acquire_at=fake_clock["wall"] + timedelta(seconds=10),
    )
    assert result.receipt["status"] == "timed_out"
    assert result.receipt["attempt_count"] == 0
    assert called is False


def test_busy_then_acquired_emits_initial_heartbeat_and_terminal_progress(
    tmp_path: Path,
    fake_clock: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_reservation = object()
    acquired: list[Path] = []
    released: list[object] = []
    attempts = iter((None, None, fake_reservation))

    def acquire(path: Path) -> object | None:
        acquired.append(path)
        fake_clock["monotonic"] += 0.0
        return next(attempts)

    monkeypatch.setattr(reservation_module, "acquire_heavy_chain_reservation", acquire)
    monkeypatch.setattr(
        reservation_module,
        "release_heavy_chain_reservation",
        lambda reservation: released.append(reservation),
    )
    events: list[dict[str, object]] = []

    result = wait_for_scheduled_writer_reservation(
        release_root=tmp_path,
        timeout_seconds=1.0,
        latest_acquire_at=fake_clock["wall"] + timedelta(seconds=10),
        poll_interval_seconds=0.01,
        heartbeat_interval_seconds=0.01,
        on_progress=lambda item: events.append(dict(item)),
    )

    assert isinstance(result, ScheduledWriterReservationWait)
    assert result.reservation is fake_reservation
    assert result.receipt["status"] == "acquired"
    assert result.receipt["attempt_count"] == 3
    assert [event["progress_phase"] for event in events] == [
        "initial",
        "heartbeat",
        "terminal",
    ]
    assert [event["status"] for event in events] == [
        "waiting",
        "waiting",
        "acquired",
    ]
    assert acquired == [heavy_chain_lock_path(tmp_path)] * 3
    assert released == []


def test_capacity_os_error_fails_immediately_instead_of_timing_out(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capacity_error = StorageCapacityError(
        "cannot open lock file",
        preflight={
            "lock_path": str(tmp_path / HEAVY_CHAIN_LOCK_FILENAME),
            "error_type": "PermissionError",
        },
    )
    calls = 0

    def fail_acquire(_path: Path) -> None:
        nonlocal calls
        calls += 1
        raise capacity_error

    monkeypatch.setattr(reservation_module, "acquire_heavy_chain_reservation", fail_acquire)
    with pytest.raises(ScheduledWriterReservationError) as raised:
        wait_for_scheduled_writer_reservation(
            release_root=tmp_path,
            timeout_seconds=60.0,
            latest_acquire_at=datetime.now(timezone.utc) + timedelta(minutes=2),
        )
    assert calls == 1
    assert raised.value.cause is capacity_error
    assert raised.value.receipt["status"] == "failed"
    assert raised.value.receipt["error_type"] == "StorageCapacityError"
    assert raised.value.receipt["capacity_cause_error_type"] == "PermissionError"
    assert raised.value.receipt["attempt_count"] == 1


def test_initial_progress_failure_is_terminal_without_lock_attempt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    acquire_calls = 0
    phases: list[object] = []

    def acquire(_path: Path) -> None:
        nonlocal acquire_calls
        acquire_calls += 1
        return None

    def fail_initial(payload: Any) -> None:
        phases.append(payload["progress_phase"])
        if payload["progress_phase"] == "initial":
            raise OSError("cannot write progress receipt")

    monkeypatch.setattr(reservation_module, "acquire_heavy_chain_reservation", acquire)
    with pytest.raises(ScheduledWriterReservationError) as raised:
        wait_for_scheduled_writer_reservation(
            release_root=tmp_path,
            timeout_seconds=5.0,
            latest_acquire_at=datetime.now(timezone.utc) + timedelta(seconds=10),
            on_progress=fail_initial,
        )

    assert acquire_calls == 0
    assert phases == ["initial", "terminal"]
    assert raised.value.receipt["status"] == "failed"
    assert raised.value.receipt["error_type"] == "OSError"
    assert raised.value.receipt["attempt_count"] == 0


def test_late_acquire_result_is_released_and_reported_as_timed_out(
    tmp_path: Path,
    fake_clock: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_reservation = object()
    released: list[object] = []

    def acquire(_path: Path) -> object:
        fake_clock["monotonic"] += 1.1
        return fake_reservation

    monkeypatch.setattr(reservation_module, "acquire_heavy_chain_reservation", acquire)
    monkeypatch.setattr(
        reservation_module,
        "release_heavy_chain_reservation",
        lambda reservation: released.append(reservation),
    )
    result = wait_for_scheduled_writer_reservation(
        release_root=tmp_path,
        timeout_seconds=1.0,
        latest_acquire_at=fake_clock["wall"] + timedelta(seconds=3),
    )
    assert result.reservation is None
    assert result.receipt["status"] == "timed_out"
    assert result.receipt["attempt_count"] == 1
    assert released == [fake_reservation]


def test_terminal_callback_failure_releases_an_acquired_lock(
    tmp_path: Path,
) -> None:
    phases: list[object] = []

    def fail_terminal(payload: Any) -> None:
        phases.append(payload["progress_phase"])
        if payload["progress_phase"] == "terminal":
            raise RuntimeError("cannot persist terminal status")

    with pytest.raises(ScheduledWriterReservationError) as raised:
        wait_for_scheduled_writer_reservation(
            release_root=tmp_path,
            timeout_seconds=5.0,
            latest_acquire_at=datetime.now(timezone.utc) + timedelta(seconds=10),
            on_progress=fail_terminal,
        )

    assert phases == ["initial", "terminal"]
    assert raised.value.receipt["status"] == "failed"
    assert raised.value.receipt["error_type"] == "RuntimeError"
    assert "cannot persist terminal status" in str(raised.value)
    recovered = acquire_heavy_chain_reservation(heavy_chain_lock_path(tmp_path))
    assert recovered is not None
    release_heavy_chain_reservation(recovered)


@pytest.mark.skipif(
    os.name != "nt",
    reason="requires Windows msvcrt process-level advisory locking",
)
def test_windows_process_contention_then_release_allows_waiter_to_acquire(
    tmp_path: Path,
) -> None:
    held = acquire_heavy_chain_reservation(heavy_chain_lock_path(tmp_path))
    assert held is not None
    context = multiprocessing.get_context("spawn")
    progress_queue: Queue[dict[str, object]] = context.Queue()
    process = context.Process(
        target=_cross_process_reservation_wait_worker,
        args=(str(tmp_path), progress_queue),
    )
    process.start()
    observed_busy_heartbeat = False
    terminal: dict[str, object] | None = None
    worker_result: dict[str, object] | None = None
    deadline = time.monotonic() + 10.0
    try:
        while time.monotonic() < deadline and not observed_busy_heartbeat:
            try:
                event = progress_queue.get(timeout=0.1)
            except Empty:
                continue
            event_attempt_count = event.get("attempt_count")
            if (
                event.get("progress_phase") == "heartbeat"
                and isinstance(event_attempt_count, int)
                and event_attempt_count >= 1
                and event.get("status") == "waiting"
            ):
                observed_busy_heartbeat = True
        assert observed_busy_heartbeat, "child never reported an actual busy-lock wait"
        release_heavy_chain_reservation(held)
        held = None

        while time.monotonic() < deadline and (terminal is None or worker_result is None):
            try:
                event = progress_queue.get(timeout=0.1)
            except Empty:
                continue
            if event.get("progress_phase") == "terminal":
                terminal = event
            if event.get("worker_result") is True:
                worker_result = event

        assert terminal is not None
        assert terminal["status"] == "acquired"
        assert worker_result is not None
        assert worker_result["status"] == "acquired"
        worker_attempt_count = worker_result["attempt_count"]
        assert isinstance(worker_attempt_count, int)
        assert worker_attempt_count >= 2
        process.join(timeout=10)
        assert process.exitcode == 0
    finally:
        if held is not None:
            release_heavy_chain_reservation(held)
        if process.is_alive():
            process.terminate()
            process.join(timeout=10)
        progress_queue.close()
        progress_queue.join_thread()
