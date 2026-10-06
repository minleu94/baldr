"""Bounded waiting for the shared scheduled ML heavy-chain reservation.

This adapter owns no lock implementation. It waits on the canonical OS lock
provided by :mod:`data_module.ml_storage_capacity`, preserving that module's
cross-process custody and fail-closed behavior.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import math
from pathlib import Path
import time

from data_module.ml_storage_capacity import (
    MLStorageChainReservation,
    StorageCapacityError,
    acquire_heavy_chain_reservation,
    heavy_chain_lock_path,
    release_heavy_chain_reservation,
)


SCHEDULED_WRITER_RESERVATION_SCHEMA = "scheduled-writer-reservation-wait.v1"
MAX_SCHEDULED_WRITER_WAIT_SECONDS = 24 * 60 * 60
MIN_SCHEDULED_WRITER_POLL_SECONDS = 0.01
MAX_SCHEDULED_WRITER_POLL_SECONDS = 60.0
MIN_SCHEDULED_WRITER_HEARTBEAT_SECONDS = 0.01
MAX_SCHEDULED_WRITER_HEARTBEAT_SECONDS = 60 * 60

ProgressCallback = Callable[[Mapping[str, object]], None]


@dataclass(frozen=True, slots=True)
class ScheduledWriterReservationWait:
    """Result of a bounded wait; the caller owns release after acquisition."""

    reservation: MLStorageChainReservation | None
    receipt: Mapping[str, object]


class ScheduledWriterReservationError(RuntimeError):
    """A lock wait failed for a reason other than ordinary lock contention."""

    def __init__(
        self,
        *,
        receipt: Mapping[str, object],
        cause: BaseException,
    ) -> None:
        self.receipt = dict(receipt)
        self.cause = cause
        status = self.receipt.get("status", "failed")
        error_type = self.receipt.get("error_type", type(cause).__name__)
        super().__init__(f"scheduled writer reservation {status}: {error_type}: {cause}")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _monotonic() -> float:
    return time.monotonic()


def _sleep(seconds: float) -> None:
    time.sleep(seconds)


def _bounded_seconds(
    name: str,
    value: float,
    *,
    minimum: float,
    maximum: float,
    minimum_inclusive: bool,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number of seconds")
    try:
        normalized = float(value)
    except (OverflowError, TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite number of seconds") from exc
    if not math.isfinite(normalized):
        raise ValueError(f"{name} must be finite")
    below_minimum = normalized < minimum if minimum_inclusive else normalized <= minimum
    if below_minimum or normalized > maximum:
        comparator = "at least" if minimum_inclusive else "greater than"
        raise ValueError(
            f"{name} must be {comparator} {minimum} and at most {maximum}"
        )
    return normalized


def _aware_utc(value: datetime, *, name: str) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError(f"{name} must be an aware datetime")
    try:
        offset = value.utcoffset()
    except (OverflowError, TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an aware datetime") from exc
    if value.tzinfo is None or offset is None:
        raise ValueError(f"{name} must be an aware datetime")
    try:
        return value.astimezone(timezone.utc)
    except (OverflowError, ValueError) as exc:
        raise ValueError(f"{name} cannot be represented in UTC") from exc


def _iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def _error_fields(cause: BaseException) -> dict[str, object]:
    fields: dict[str, object] = {
        "error_type": type(cause).__name__,
        "error_message": str(cause),
    }
    if isinstance(cause, StorageCapacityError):
        fields["capacity_error_type"] = type(cause).__name__
        underlying_type = cause.preflight.get("error_type")
        if isinstance(underlying_type, str) and underlying_type:
            fields["capacity_cause_error_type"] = underlying_type
    return fields


def wait_for_scheduled_writer_reservation(
    *,
    release_root: Path,
    timeout_seconds: float,
    latest_acquire_at: datetime,
    poll_interval_seconds: float = 1.0,
    heartbeat_interval_seconds: float = 30.0,
    on_progress: ProgressCallback | None = None,
) -> ScheduledWriterReservationWait:
    """Wait boundedly for the canonical ML chain lock.

    A busy OS lock is represented only by ``acquire_heavy_chain_reservation``
    returning ``None``. Capacity/OS errors fail immediately. The relative
    timeout and absolute latest-acquire time are frozen against one aware UTC
    clock sample, then enforced with monotonic time so wall-clock adjustments
    cannot extend the wait.
    """

    timeout = _bounded_seconds(
        "timeout_seconds",
        timeout_seconds,
        minimum=0.0,
        maximum=float(MAX_SCHEDULED_WRITER_WAIT_SECONDS),
        minimum_inclusive=True,
    )
    poll_interval = _bounded_seconds(
        "poll_interval_seconds",
        poll_interval_seconds,
        minimum=MIN_SCHEDULED_WRITER_POLL_SECONDS,
        maximum=MAX_SCHEDULED_WRITER_POLL_SECONDS,
        minimum_inclusive=True,
    )
    heartbeat_interval = _bounded_seconds(
        "heartbeat_interval_seconds",
        heartbeat_interval_seconds,
        minimum=MIN_SCHEDULED_WRITER_HEARTBEAT_SECONDS,
        maximum=float(MAX_SCHEDULED_WRITER_HEARTBEAT_SECONDS),
        minimum_inclusive=True,
    )
    latest_utc = _aware_utc(latest_acquire_at, name="latest_acquire_at")
    if not isinstance(release_root, (Path, str)):
        raise ValueError("release_root must be a path")

    lock_path = heavy_chain_lock_path(Path(release_root))
    monotonic_started = _monotonic()
    wait_started = _aware_utc(_utc_now(), name="current time")
    timeout_deadline = wait_started + timedelta(seconds=timeout)
    effective_deadline = min(timeout_deadline, latest_utc)
    allowed_duration = max(
        0.0,
        min(timeout, (effective_deadline - wait_started).total_seconds()),
    )
    monotonic_deadline = monotonic_started + allowed_duration
    next_heartbeat = monotonic_started + heartbeat_interval
    attempt_count = 0

    def make_receipt(
        *,
        status: str,
        error: BaseException | None = None,
        ended_at: datetime | None = None,
        ended_monotonic: float | None = None,
        extras: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        wall_end = _aware_utc(ended_at or _utc_now(), name="current time")
        mono_end = _monotonic() if ended_monotonic is None else ended_monotonic
        receipt: dict[str, object] = {
            "schema_version": SCHEDULED_WRITER_RESERVATION_SCHEMA,
            "status": status,
            "lock_path": str(lock_path),
            "wait_started_at_utc": _iso_utc(wait_started),
            "wait_ended_at_utc": _iso_utc(wall_end),
            "effective_deadline_at_utc": _iso_utc(effective_deadline),
            "configured_timeout_seconds": timeout,
            "elapsed_seconds": max(0.0, mono_end - monotonic_started),
            "attempt_count": attempt_count,
            "error_type": None,
            "error_message": None,
        }
        if error is not None:
            receipt.update(_error_fields(error))
        if extras:
            receipt.update(extras)
        return receipt

    def notify(receipt: Mapping[str, object], *, phase: str) -> BaseException | None:
        if on_progress is None:
            return None
        payload = dict(receipt)
        payload["progress_phase"] = phase
        try:
            on_progress(payload)
        except Exception as exc:
            return exc
        return None

    def raise_failed(
        cause: BaseException,
        *,
        report_terminal: bool = True,
        extras: Mapping[str, object] | None = None,
    ) -> None:
        receipt = make_receipt(
            status="failed",
            error=cause,
            extras=extras,
        )
        if report_terminal:
            terminal_error = notify(receipt, phase="terminal")
            if terminal_error is not None:
                try:
                    cause.add_note(
                        "terminal progress callback also failed: "
                        f"{type(terminal_error).__name__}: {terminal_error}"
                    )
                except AttributeError:  # pragma: no cover - Python < 3.11 fallback
                    pass
        raise ScheduledWriterReservationError(
            receipt=receipt,
            cause=cause,
        ) from cause

    initial_receipt = make_receipt(status="waiting")
    callback_error = notify(initial_receipt, phase="initial")
    if callback_error is not None:
        raise_failed(callback_error)

    while True:
        now_monotonic = _monotonic()
        if now_monotonic >= monotonic_deadline:
            receipt = make_receipt(
                status="timed_out",
                ended_monotonic=now_monotonic,
            )
            callback_error = notify(receipt, phase="terminal")
            if callback_error is not None:
                raise_failed(callback_error, report_terminal=False)
            return ScheduledWriterReservationWait(
                reservation=None,
                receipt=receipt,
            )

        attempt_count += 1
        try:
            reservation = acquire_heavy_chain_reservation(lock_path)
        except StorageCapacityError as exc:
            raise_failed(exc)
        except Exception as exc:
            raise_failed(exc)

        after_attempt = _monotonic()
        if reservation is not None:
            if after_attempt >= monotonic_deadline:
                try:
                    release_heavy_chain_reservation(reservation)
                except Exception as exc:  # pragma: no cover - defensive OS failure
                    raise_failed(
                        exc,
                        extras={"cleanup_after_late_acquire": True},
                    )
                receipt = make_receipt(
                    status="timed_out",
                    ended_monotonic=after_attempt,
                )
                callback_error = notify(receipt, phase="terminal")
                if callback_error is not None:
                    raise_failed(callback_error, report_terminal=False)
                return ScheduledWriterReservationWait(
                    reservation=None,
                    receipt=receipt,
                )

            receipt = make_receipt(
                status="acquired",
                ended_monotonic=after_attempt,
            )
            try:
                callback_error = notify(receipt, phase="terminal")
            except BaseException as exc:
                try:
                    release_heavy_chain_reservation(reservation)
                except BaseException as interrupt_cleanup_error:  # pragma: no cover
                    try:
                        exc.add_note(
                            "reservation cleanup also failed: "
                            f"{type(interrupt_cleanup_error).__name__}: "
                            f"{interrupt_cleanup_error}"
                        )
                    except AttributeError:
                        pass
                raise
            if callback_error is not None:
                cleanup_error: BaseException | None = None
                try:
                    release_heavy_chain_reservation(reservation)
                except Exception as exc:  # pragma: no cover - defensive OS failure
                    cleanup_error = exc
                extras: dict[str, object] = {}
                if cleanup_error is not None:
                    extras["cleanup_error_type"] = type(cleanup_error).__name__
                    extras["cleanup_error_message"] = str(cleanup_error)
                raise_failed(
                    callback_error,
                    report_terminal=False,
                    extras=extras,
                )
            return ScheduledWriterReservationWait(
                reservation=reservation,
                receipt=receipt,
            )

        if after_attempt >= monotonic_deadline:
            receipt = make_receipt(
                status="timed_out",
                ended_monotonic=after_attempt,
            )
            callback_error = notify(receipt, phase="terminal")
            if callback_error is not None:
                raise_failed(callback_error, report_terminal=False)
            return ScheduledWriterReservationWait(
                reservation=None,
                receipt=receipt,
            )

        if after_attempt >= next_heartbeat:
            heartbeat_receipt = make_receipt(
                status="waiting",
                ended_monotonic=after_attempt,
            )
            callback_error = notify(heartbeat_receipt, phase="heartbeat")
            if callback_error is not None:
                raise_failed(callback_error)
            next_heartbeat = after_attempt + heartbeat_interval

        remaining = monotonic_deadline - after_attempt
        until_heartbeat = max(0.0, next_heartbeat - after_attempt)
        sleep_seconds = min(poll_interval, remaining)
        if until_heartbeat > 0:
            sleep_seconds = min(sleep_seconds, until_heartbeat)
        if sleep_seconds <= 0:
            continue
        try:
            _sleep(sleep_seconds)
        except Exception as exc:
            raise_failed(exc)
