"""驗證雙來源 QThread actor 的 owner-thread 與取消生命週期。"""

from __future__ import annotations

import os
from threading import Event, get_ident
import time
from typing import Callable, cast

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from ui_qt.workers.revenue_source_actor_v2 import RevenueSourceActorV2


def _pump_until(app: QApplication, predicate: Callable[[], bool], timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)
    app.processEvents()
    assert predicate()


def _stop_actor(app: QApplication, actor: RevenueSourceActorV2) -> None:
    actor.request_shutdown()
    _pump_until(app, lambda: not actor.isRunning())
    assert actor.wait(5_000)


@pytest.fixture
def qapp() -> QApplication:
    return cast(QApplication, QApplication.instance() or QApplication([]))


class _Handle:
    def __init__(self, name: str) -> None:
        self.name = name
        self.created_thread_id = get_ident()
        self.close_thread_id: int | None = None
        self.close_count = 0

    def close(self) -> None:
        self.close_thread_id = get_ident()
        self.close_count += 1


def _signals(actor: RevenueSourceActorV2) -> tuple[list[tuple[int, object]], list[tuple[int, str]], list[int], list[int]]:
    succeeded: list[tuple[int, object]] = []
    failed: list[tuple[int, str]] = []
    cancelled: list[int] = []
    settled: list[int] = []
    actor.succeeded.connect(lambda token, payload: succeeded.append((token, payload)))
    actor.failed.connect(lambda token, message: failed.append((token, message)))
    actor.cancelled.connect(cancelled.append)
    actor.settled.connect(settled.append)
    return succeeded, failed, cancelled, settled


def _open_handle(
    name: str,
    callbacks: list[Callable[[], bool]] | None = None,
    owner_threads: list[int] | None = None,
) -> Callable[[Callable[[], bool]], _Handle]:
    def opener(cancel_check: Callable[[], bool]) -> _Handle:
        if callbacks is not None:
            callbacks.append(cancel_check)
        if owner_threads is not None:
            owner_threads.append(get_ident())
        if cancel_check():
            raise RuntimeError("open_cancelled_before_create")
        return _Handle(name)

    return opener


def test_open_task_and_replacement_share_owner_thread_and_shutdown_closes_source(qapp: QApplication) -> None:
    actor = RevenueSourceActorV2()
    succeeded, failed, cancelled, settled = _signals(actor)
    owner_threads: list[int] = []
    first: list[_Handle] = []
    second: list[_Handle] = []

    def first_opener(cancel_check: Callable[[], bool]) -> _Handle:
        owner_threads.append(get_ident())
        handle = _open_handle("first")(cancel_check)
        first.append(handle)
        return handle

    try:
        assert actor.submit_open(
            1,
            first_opener,
            lambda handle, cancel_check: (owner_threads.append(get_ident()), handle.name)[1],
        )
        _pump_until(qapp, lambda: 1 in settled)
        assert succeeded == [(1, "first")]
        assert failed == [] and cancelled == []
        assert actor.has_source and not actor.busy

        def page_task(handle: _Handle, cancel_check: Callable[[], bool]) -> object:
            owner_threads.append(get_ident())
            assert not cancel_check()
            return ("page", handle.name)

        assert actor.submit_task(2, page_task)
        _pump_until(qapp, lambda: 2 in settled)
        assert succeeded[-1] == (2, ("page", "first"))

        def second_opener(cancel_check: Callable[[], bool]) -> _Handle:
            owner_threads.append(get_ident())
            handle = _open_handle("second")(cancel_check)
            second.append(handle)
            return handle

        assert actor.submit_open(
            3,
            second_opener,
            lambda handle, cancel_check: (owner_threads.append(get_ident()), handle.name)[1],
        )
        _pump_until(qapp, lambda: 3 in settled)
        assert succeeded[-1] == (3, "second")
        assert first[0].close_count == 1
        assert first[0].close_thread_id == first[0].created_thread_id
        assert second[0].close_count == 0
        assert len(set(owner_threads)) == 1

        _stop_actor(qapp, actor)
        assert second[0].close_count == 1
        assert second[0].close_thread_id == second[0].created_thread_id
        assert not actor.has_source
    finally:
        if actor.isRunning():
            _stop_actor(qapp, actor)


def test_failed_projection_closes_candidate_and_keeps_previous_source(qapp: QApplication) -> None:
    actor = RevenueSourceActorV2()
    succeeded, failed, cancelled, settled = _signals(actor)
    original: list[_Handle] = []
    candidate: list[_Handle] = []

    def remember(target: list[_Handle], name: str) -> Callable[[Callable[[], bool]], _Handle]:
        def opener(cancel_check: Callable[[], bool]) -> _Handle:
            handle = _open_handle(name)(cancel_check)
            target.append(handle)
            return handle

        return opener

    try:
        assert actor.submit_open(10, remember(original, "original"), lambda handle, check: handle.name)
        _pump_until(qapp, lambda: 10 in settled)

        def fail_projection(handle: _Handle, cancel_check: Callable[[], bool]) -> object:
            raise ValueError("projection_rejected")

        assert actor.submit_open(11, remember(candidate, "candidate"), fail_projection)
        _pump_until(qapp, lambda: 11 in settled)
        assert failed == [(11, "projection_rejected")]
        assert succeeded == [(10, "original")]
        assert cancelled == []
        assert candidate[0].close_count == 1
        assert candidate[0].close_thread_id == candidate[0].created_thread_id
        assert original[0].close_count == 0
        assert actor.has_source

        assert actor.submit_task(12, lambda handle, check: handle.name)
        _pump_until(qapp, lambda: 12 in settled)
        assert succeeded[-1] == (12, "original")
    finally:
        _stop_actor(qapp, actor)


def test_cancelled_replacement_keeps_source_and_cancel_callback_tracks_current_request(qapp: QApplication) -> None:
    actor = RevenueSourceActorV2()
    succeeded, failed, cancelled, settled = _signals(actor)
    original: list[_Handle] = []
    candidate: list[_Handle] = []
    saved_callbacks: list[Callable[[], bool]] = []
    entered = Event()
    release = Event()

    def remembered_original(cancel_check: Callable[[], bool]) -> _Handle:
        handle = _open_handle("original", saved_callbacks)(cancel_check)
        original.append(handle)
        return handle

    try:
        assert actor.submit_open(20, remembered_original, lambda handle, check: handle.name)
        _pump_until(qapp, lambda: 20 in settled)
        stale_callback = saved_callbacks[0]
        assert stale_callback() is False

        def candidate_opener(cancel_check: Callable[[], bool]) -> _Handle:
            handle = _open_handle("candidate")(cancel_check)
            candidate.append(handle)
            return handle

        def wait_for_cancel(handle: _Handle, cancel_check: Callable[[], bool]) -> object:
            entered.set()
            while not release.is_set():
                if cancel_check():
                    return "discarded-candidate"
                release.wait(0.005)
            return handle.name

        assert actor.submit_open(21, candidate_opener, wait_for_cancel)
        _pump_until(qapp, entered.is_set)
        actor.cancel_current()
        release.set()
        _pump_until(qapp, lambda: 21 in settled)

        assert cancelled == [21]
        assert candidate[0].close_count == 1
        assert candidate[0].close_thread_id == candidate[0].created_thread_id
        assert original[0].close_count == 0
        assert actor.has_source
        assert stale_callback() is False

        task_entered = Event()
        observed: list[bool] = []

        def cancellable_task(handle: _Handle, cancel_check: Callable[[], bool]) -> object:
            task_entered.set()
            observed.append(stale_callback())
            while not cancel_check():
                release.wait(0.005)
            observed.append(stale_callback())
            return handle.name

        release.clear()
        assert actor.submit_task(22, cancellable_task)
        _pump_until(qapp, task_entered.is_set)
        actor.cancel_current()
        _pump_until(qapp, lambda: 22 in settled)
        assert cancelled == [21, 22]
        assert observed == [False, True]
        assert stale_callback() is False
        assert original[0].close_count == 0
        assert actor.has_source
    finally:
        release.set()
        _stop_actor(qapp, actor)


def test_actor_rejects_a_second_request_while_its_single_slot_is_busy(qapp: QApplication) -> None:
    actor = RevenueSourceActorV2()
    succeeded, failed, cancelled, settled = _signals(actor)
    entered = Event()
    release = Event()
    executed: list[int] = []

    def blocked_open(cancel_check: Callable[[], bool]) -> _Handle:
        entered.set()
        while not release.is_set() and not cancel_check():
            release.wait(0.005)
        return _Handle("blocked")

    try:
        assert actor.submit_open(30, blocked_open, lambda handle, check: handle.name)
        _pump_until(qapp, entered.is_set)
        assert actor.busy
        assert not actor.submit_task(31, lambda handle, check: executed.append(31))
        actor.cancel_current()
        release.set()
        _pump_until(qapp, lambda: 30 in settled)
        assert cancelled == [30]
        assert succeeded == [] and failed == []
        assert settled == [30]
        assert executed == []
        assert not actor.busy and not actor.has_source
    finally:
        release.set()
        _stop_actor(qapp, actor)


def test_shutdown_cooperatively_cancels_task_closes_source_and_uses_native_finished(qapp: QApplication) -> None:
    actor = RevenueSourceActorV2()
    succeeded, failed, cancelled, settled = _signals(actor)
    native_finished = Event()
    actor.finished.connect(native_finished.set)
    source: list[_Handle] = []
    task_entered = Event()
    release = Event()

    def opener(cancel_check: Callable[[], bool]) -> _Handle:
        handle = _open_handle("shutdown-source")(cancel_check)
        source.append(handle)
        return handle

    try:
        assert actor.submit_open(40, opener, lambda handle, check: handle.name)
        _pump_until(qapp, lambda: 40 in settled)

        def blocking_task(handle: _Handle, cancel_check: Callable[[], bool]) -> object:
            task_entered.set()
            while not release.is_set() and not cancel_check():
                release.wait(0.005)
            return handle.name

        assert actor.submit_task(41, blocking_task)
        _pump_until(qapp, task_entered.is_set)
        actor.request_shutdown()
        _pump_until(qapp, lambda: not actor.isRunning())
        assert actor.wait(5_000)
        qapp.processEvents()

        assert actor.shutdown_requested
        assert cancelled == [41]
        assert succeeded == [(40, "shutdown-source")]
        assert failed == []
        assert settled == [40, 41]
        assert source[0].close_count == 1
        assert source[0].close_thread_id == source[0].created_thread_id
        assert not actor.has_source
        assert native_finished.is_set()
    finally:
        release.set()
        if actor.isRunning():
            _stop_actor(qapp, actor)

