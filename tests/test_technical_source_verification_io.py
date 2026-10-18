"""唯讀四件核對有界；錯誤及取消返回前所有自有工作必須結束。"""
import threading
import time

import pytest

from app_module.technical_source_copy import _run_io, TechnicalSourceCopyError


@pytest.mark.parametrize("workers", [2, 4])
def test_parallelism_bound_and_join(workers):
    lock = threading.Lock()
    barrier = threading.Barrier(workers)
    active = peak = completed = 0
    def work():
        nonlocal active, peak, completed
        with lock:
            active += 1
            peak = max(peak, active)
        barrier.wait(timeout=5)
        with lock:
            active -= 1
            completed += 1
    _run_io((work for _ in range(workers * 2)), None, workers=workers)
    assert peak == workers and active == 0 and completed == workers * 2


@pytest.mark.parametrize("workers", [2, 4])
def test_completed_later_work_refills_slot_while_first_is_still_running(workers):
    first_started = threading.Event()
    slot_refilled = threading.Event()

    def first():
        first_started.set()
        assert slot_refilled.wait(timeout=5), "completed slots must not wait for the first work"

    def quick():
        assert first_started.wait(timeout=5)

    _run_io([first, *[quick] * (workers - 1), slot_refilled.set], None, workers=workers)
    assert slot_refilled.is_set()


def test_failure_waits_for_other_dispatched_verifications():
    barrier = threading.Barrier(4)
    finished = []
    def work(index):
        def run():
            barrier.wait(timeout=5)
            if index == 0:
                raise ValueError("bad hash")
            time.sleep(.02)
            finished.append(index)
        return run
    with pytest.raises(ValueError, match="bad hash"):
        _run_io((work(index) for index in range(8)), None, workers=4)
    assert sorted(finished) == [1, 2, 3]


def test_cancel_waits_for_in_flight_verifications():
    cancel = threading.Event()
    lock = threading.Lock()
    active = 0
    def work():
        nonlocal active
        with lock:
            active += 1
        cancel.set()
        time.sleep(.02)
        with lock:
            active -= 1
    with pytest.raises(TechnicalSourceCopyError, match="cancelled"):
        _run_io((work for _ in range(20)), cancel.is_set, workers=4)
    assert active == 0


@pytest.mark.parametrize("workers", [True, 0, 3, 8])
def test_unapproved_parallelism_refused_before_dispatch(workers):
    called = []
    with pytest.raises(TechnicalSourceCopyError, match="workers_invalid"):
        _run_io([lambda: called.append(True)], None, workers=workers)
    assert called == []


def test_metadata_budget_registration_is_serial_and_writes_are_bounded(tmp_path, monkeypatch):
    from hashlib import sha256
    import app_module.technical_source_copy as module
    from app_module.research_output_copy import ResearchOutputCopyBudget
    files = module._Files(ResearchOutputCopyBudget(16, 128, 16, 8), None)
    producer = threading.get_ident()
    original_prepare = files._prepare_write
    registrations = []
    def prepare(path, raw):
        registrations.append(threading.get_ident())
        return original_prepare(path, raw)
    monkeypatch.setattr(files, "_prepare_write", prepare)
    barrier = threading.Barrier(2)
    lock = threading.Lock()
    active = peak = 0
    def write(path, raw, *, maximum):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        barrier.wait(timeout=5)
        path.write_bytes(raw)
        with lock:
            active -= 1
    monkeypatch.setattr(module, "_write_immutable", write)
    members = [(tmp_path / str(index), bytes([index])) for index in range(4)]
    files.write_many(iter(members))
    assert registrations == [producer] * 4 and peak == 2 and active == 0
    assert files.destination == {path: (len(raw), sha256(raw).hexdigest()) for path, raw in members}
    assert all(path.read_bytes() == raw for path, raw in members)
