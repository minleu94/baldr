from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from scripts import qa_validate_update_tab as qa_module


class _SharingViolation(PermissionError):
    @property
    def winerror(self) -> int:
        return 32


def test_sandbox_cleanup_retries_winerror32_then_succeeds(monkeypatch):
    temporary_directory = tempfile.TemporaryDirectory(
        prefix="r022-cleanup-retry-",
        dir=tempfile.gettempdir(),
    )
    original_cleanup = temporary_directory.cleanup
    attempts = 0
    delays: list[float] = []

    def cleanup_with_one_transient_failure():
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise _SharingViolation("synthetic transient lock")
        original_cleanup()

    temporary_directory.cleanup = cleanup_with_one_transient_failure
    monkeypatch.setattr(qa_module.time, "sleep", delays.append)
    monkeypatch.setattr(qa_module.time, "monotonic", lambda: 0.0)

    qa_module._cleanup_isolated_temporary_directory(
        temporary_directory,
        Path(temporary_directory.name),
    )

    assert attempts == 2
    assert delays == [0.1]
    assert not Path(temporary_directory.name).exists()


def test_sandbox_cleanup_stops_at_deadline_and_preserves_winerror32(monkeypatch):
    temporary_directory = tempfile.TemporaryDirectory(
        prefix="r022-cleanup-exhausted-",
        dir=tempfile.gettempdir(),
    )
    original_cleanup = temporary_directory.cleanup
    attempts = 0
    delays: list[float] = []

    def cleanup_always_locked():
        nonlocal attempts
        attempts += 1
        raise _SharingViolation("synthetic persistent lock")

    temporary_directory.cleanup = cleanup_always_locked
    clock = {"now": 0.0}

    def advance_clock(delay: float) -> None:
        delays.append(delay)
        clock["now"] += delay

    monkeypatch.setattr(qa_module.time, "sleep", advance_clock)
    monkeypatch.setattr(qa_module.time, "monotonic", lambda: clock["now"])

    try:
        with pytest.raises(_SharingViolation, match="synthetic persistent lock"):
            qa_module._cleanup_isolated_temporary_directory(
                temporary_directory,
                Path(temporary_directory.name),
                deadline_seconds=0.5,
            )
        assert attempts == 4
        assert delays == pytest.approx([0.1, 0.2, 0.2])
    finally:
        original_cleanup()


def test_sandbox_cleanup_rejects_path_outside_system_temp():
    temporary_directory = tempfile.TemporaryDirectory(
        prefix="r022-cleanup-scope-",
        dir=tempfile.gettempdir(),
    )
    original_cleanup = temporary_directory.cleanup

    try:
        with pytest.raises(ValueError, match="system TEMP"):
            qa_module._cleanup_isolated_temporary_directory(
                temporary_directory,
                Path(tempfile.gettempdir()),
            )
    finally:
        original_cleanup()
