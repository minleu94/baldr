"""TaskWorker 取消契約的精準單元測試。"""

import pytest

from ui_qt.workers.task_worker import (
    ProgressTaskWorker,
    TaskWorker,
    request_cooperative_task_worker_shutdown,
)


class _InspectableTaskWorker(TaskWorker):
    """記錄取消期間的 QThread 方法呼叫，不啟動實際執行緒。"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.terminate_calls = 0
        self.wait_calls = []

    def terminate(self):
        self.terminate_calls += 1

    def wait(self, *args):
        self.wait_calls.append(args)
        return True


class _InspectableProgressTaskWorker(ProgressTaskWorker):
    """記錄取消期間的 QThread 方法呼叫，不啟動實際執行緒。"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.terminate_calls = 0
        self.wait_calls = []

    def terminate(self):
        self.terminate_calls += 1

    def wait(self, *args):
        self.wait_calls.append(args)
        return True


@pytest.mark.parametrize(
    "worker_class",
    [_InspectableTaskWorker, _InspectableProgressTaskWorker],
)
def test_cancel_defaults_to_nonblocking_cooperative_without_terminating(worker_class):
    worker = worker_class(lambda **_kwargs: None)

    worker.cancel()

    assert worker._is_cancelled is True
    assert worker.terminate_calls == 0
    assert worker.wait_calls == []


@pytest.mark.parametrize(
    "worker_class",
    [_InspectableTaskWorker, _InspectableProgressTaskWorker],
)
def test_cancel_can_explicitly_wait_without_terminating(worker_class):
    worker = worker_class(lambda **_kwargs: None)

    worker.cancel(wait=True)

    assert worker._is_cancelled is True
    assert worker.terminate_calls == 0
    assert worker.wait_calls == [()]


@pytest.mark.parametrize(
    "worker_class",
    [_InspectableTaskWorker, _InspectableProgressTaskWorker],
)
def test_cancel_keeps_legacy_parameter_but_never_terminates(worker_class):
    worker = worker_class(lambda **_kwargs: None)

    worker.cancel(cooperative=False, wait=False)

    assert worker._is_cancelled is True
    assert worker.terminate_calls == 0
    assert worker.wait_calls == []


@pytest.mark.parametrize("worker_class", [TaskWorker, ProgressTaskWorker])
def test_pre_cancelled_worker_emits_cancelled_without_running_task(worker_class):
    task_calls = []
    cancelled_calls = []
    worker = worker_class(lambda **_kwargs: task_calls.append("ran"))
    worker.cancelled.connect(lambda: cancelled_calls.append("cancelled"))

    worker.cancel(wait=False)
    worker.run()

    assert task_calls == []
    assert cancelled_calls == ["cancelled"]


def test_progress_worker_injects_thread_safe_cancel_callback_only_when_supported():
    observed: list[bool] = []
    finished_calls: list[object] = []

    def task(progress_callback=None, cancel_callback=None):
        assert progress_callback is not None
        assert cancel_callback is not None
        observed.append(cancel_callback())
        return "done"

    worker = ProgressTaskWorker(task)
    worker.finished.connect(finished_calls.append)
    worker.run()

    assert observed == [False]
    assert finished_calls == ["done"]

    worker.cancel()
    assert worker.is_cancel_requested() is True


def test_task_worker_does_not_inject_cancel_callback_into_legacy_callable():
    calls: list[str] = []
    worker = TaskWorker(lambda: calls.append("ran"))

    worker.run()

    assert calls == ["ran"]


@pytest.mark.parametrize("worker_class", [TaskWorker, ProgressTaskWorker])
def test_worker_preserves_explicit_partial_cancel_result(worker_class):
    finished = []
    cancelled = []
    holder = {}

    def task(progress_callback=None, cancel_callback=None):
        holder["worker"].cancel()
        return {"cancelled": True, "completed_units": 2}

    worker = worker_class(task)
    holder["worker"] = worker
    worker.finished.connect(finished.append)
    worker.cancelled.connect(lambda: cancelled.append(True))

    worker.run()

    assert finished == [{"cancelled": True, "completed_units": 2}]
    assert cancelled == []


@pytest.mark.parametrize("worker_class", [TaskWorker, ProgressTaskWorker])
def test_worker_does_not_mask_real_error_when_cancel_is_requested(worker_class):
    errors = []
    cancelled = []
    holder = {}

    def task(progress_callback=None, cancel_callback=None):
        holder["worker"].cancel()
        raise RuntimeError("writer failure after cancel request")

    worker = worker_class(task)
    holder["worker"] = worker
    worker.error.connect(errors.append)
    worker.cancelled.connect(lambda: cancelled.append(True))

    worker.run()

    assert len(errors) == 1
    assert "writer failure after cancel request" in errors[0]
    assert cancelled == []


def test_worker_keeps_legacy_cancellation_signal_without_explicit_outcome():
    cancelled = []
    holder = {}

    def task():
        holder["worker"].cancel()
        return "legacy result has no cancel outcome field"

    worker = TaskWorker(task)
    holder["worker"] = worker
    worker.cancelled.connect(lambda: cancelled.append(True))

    worker.run()

    assert cancelled == [True]


def test_shutdown_request_is_nonblocking_and_never_terminates():
    class _RunningWorker(_InspectableTaskWorker):
        def isRunning(self):
            return True

    worker = _RunningWorker(lambda **_kwargs: None)

    remaining = request_cooperative_task_worker_shutdown()

    assert worker in remaining
    assert worker._is_cancelled is True
    assert worker.terminate_calls == 0
    assert worker.wait_calls == []


def test_native_thread_cleanup_is_deferred_while_worker_is_running():
    class _RunningWorker(TaskWorker):
        running = True

        def isRunning(self):
            return self.running

    worker = _RunningWorker(lambda **_kwargs: None)

    worker.deleteLater()

    assert worker._delete_later_requested is True

    worker.running = False
    worker._on_native_thread_finished()

    assert worker._delete_later_requested is False


def test_native_finished_worker_is_removed_from_shutdown_registry():
    import ui_qt.workers.task_worker as task_worker_module

    class _FinishedWorker(TaskWorker):
        def isRunning(self):
            return False

    worker = _FinishedWorker(lambda **_kwargs: None)
    assert worker in task_worker_module._MANAGED_TASK_WORKERS

    worker._on_native_thread_finished()

    assert worker not in task_worker_module._MANAGED_TASK_WORKERS


def test_unstarted_delete_later_worker_is_removed_from_shutdown_registry():
    from PySide6.QtWidgets import QApplication
    import ui_qt.workers.task_worker as task_worker_module

    app = QApplication.instance() or QApplication([])
    worker = TaskWorker(lambda **_kwargs: None)
    assert worker in task_worker_module._MANAGED_TASK_WORKERS

    worker.deleteLater()

    try:
        assert worker not in task_worker_module._MANAGED_TASK_WORKERS
    finally:
        app.processEvents()


def test_start_failure_cleans_both_worker_registries(monkeypatch):
    from PySide6.QtCore import QThread
    import ui_qt.workers.task_worker as task_worker_module

    worker = TaskWorker(lambda **_kwargs: None)

    def fail_start(_worker, _priority):
        raise RuntimeError("synthetic QThread.start failure")

    monkeypatch.setattr(QThread, "start", fail_start)

    with pytest.raises(RuntimeError, match="synthetic QThread.start failure"):
        worker.start()

    assert worker not in task_worker_module._MANAGED_TASK_WORKERS
    assert worker not in task_worker_module._LIVE_TASK_WORKERS


def test_deleted_cpp_worker_is_discarded_by_shutdown_probe():
    from PySide6.QtWidgets import QApplication
    import shiboken6
    import ui_qt.workers.task_worker as task_worker_module

    app = QApplication.instance() or QApplication([])
    worker = TaskWorker(lambda **_kwargs: None)
    assert worker in task_worker_module._MANAGED_TASK_WORKERS

    shiboken6.delete(worker)

    assert task_worker_module.running_task_workers() == ()
    assert worker not in task_worker_module._MANAGED_TASK_WORKERS
    app.processEvents()


def test_restarting_finished_worker_restores_shutdown_registry():
    from PySide6.QtWidgets import QApplication
    import threading
    import ui_qt.workers.task_worker as task_worker_module

    app = QApplication.instance() or QApplication([])
    first_finished = []
    second_started = threading.Event()
    release_second = threading.Event()

    def task():
        if not first_finished:
            first_finished.append(True)
            return "first"
        second_started.set()
        release_second.wait(5)
        return "second"

    worker = TaskWorker(task)
    worker.start()
    assert worker.wait(5_000) is True
    app.processEvents()
    assert worker not in task_worker_module._MANAGED_TASK_WORKERS

    started = False
    waited = False
    try:
        worker.start()
        started = True
        assert second_started.wait(5) is True
        assert worker in task_worker_module._MANAGED_TASK_WORKERS
        assert worker in task_worker_module._LIVE_TASK_WORKERS
    finally:
        if started:
            release_second.set()
            waited = worker.wait(5_000)
        app.processEvents()

    assert waited is True
    assert worker not in task_worker_module._MANAGED_TASK_WORKERS
    worker.deleteLater()
    app.processEvents()


def test_native_finished_signal_is_available_separately_from_task_result():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    task_results = []
    native_finished = []
    worker = TaskWorker(lambda: "ok")
    worker.finished.connect(task_results.append)
    worker.native_thread_finished.connect(lambda: native_finished.append(True))

    worker.start()
    assert worker.wait(5_000) is True
    app.processEvents()

    assert task_results == ["ok"]
    assert native_finished == [True]
    worker.deleteLater()
    app.processEvents()
