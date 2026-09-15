"""Owner 關閉桌面程式時的合作式背景工作安全契約。"""

from __future__ import annotations

import os
import time
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import ui_qt.main as main_module
from ui_qt.views.update_view import UpdateView
from ui_qt.workers.task_worker import TaskWorker


class _CloseEvent:
    def __init__(self) -> None:
        self.accepted = False
        self.ignored = False

    def accept(self) -> None:
        self.accepted = True

    def ignore(self) -> None:
        self.ignored = True


class _StatusBar:
    def __init__(self) -> None:
        self.messages: list[tuple[str, int]] = []

    def showMessage(self, message: str, timeout: int) -> None:
        self.messages.append((message, timeout))


class _Window:
    def __init__(self, update_view: object | None = None) -> None:
        self.update_view = update_view
        self._status_bar = _StatusBar()

    def statusBar(self) -> _StatusBar:
        return self._status_bar


def test_main_close_pauses_until_managed_worker_is_safely_finished(
    monkeypatch,
) -> None:
    worker = object()
    monkeypatch.setattr(
        main_module,
        "request_cooperative_task_worker_shutdown",
        lambda: (worker,),
    )
    window = _Window()
    event = _CloseEvent()

    main_module.MainWindow.closeEvent(window, event)

    assert event.ignored is True
    assert event.accepted is False
    assert "1 個合作式取消中的背景工作" in window._status_bar.messages[0][0]


def test_main_close_pauses_for_detached_update_process(monkeypatch) -> None:
    monkeypatch.setattr(
        main_module,
        "request_cooperative_task_worker_shutdown",
        lambda: (),
    )
    update_view = SimpleNamespace(
        has_running_background_process=lambda: True,
    )
    window = _Window(update_view=update_view)
    event = _CloseEvent()

    main_module.MainWindow.closeEvent(window, event)

    assert event.ignored is True
    assert event.accepted is False
    assert "TPEX 背景更新程序" in window._status_bar.messages[0][0]


def test_main_close_accepts_when_no_managed_work_remains(monkeypatch) -> None:
    monkeypatch.setattr(
        main_module,
        "request_cooperative_task_worker_shutdown",
        lambda: (),
    )
    window = _Window()
    event = _CloseEvent()

    main_module.MainWindow.closeEvent(window, event)

    assert event.accepted is True
    assert event.ignored is False
    assert window._status_bar.messages == []


def test_pending_close_sends_cancel_once_then_only_polls(monkeypatch) -> None:
    worker = object()
    calls = {"begin": 0, "request": 0, "poll": 0}

    def begin_shutdown() -> None:
        calls["begin"] += 1

    def request_shutdown():
        calls["request"] += 1
        return (worker,)

    def poll_workers():
        calls["poll"] += 1
        return (worker,)

    monkeypatch.setattr(main_module, "request_cooperative_task_worker_shutdown", request_shutdown)
    monkeypatch.setattr(main_module, "running_task_workers", poll_workers)
    window = _Window(
        update_view=SimpleNamespace(
            begin_shutdown=begin_shutdown,
            has_running_background_process=lambda: False,
        )
    )

    first_event = _CloseEvent()
    second_event = _CloseEvent()
    main_module.MainWindow.closeEvent(window, first_event)
    main_module.MainWindow.closeEvent(window, second_event)

    assert first_event.ignored is True
    assert second_event.ignored is True
    assert calls == {"begin": 1, "request": 1, "poll": 1}


def test_update_view_close_never_uses_terminate_fallback() -> None:
    calls: list[str] = []
    view = SimpleNamespace(
        request_cooperative_shutdown=lambda: False,
        _log=lambda message: calls.append(message),
    )
    event = _CloseEvent()

    UpdateView.closeEvent(view, event)

    assert event.ignored is True
    assert event.accepted is False
    assert calls == ["已送出合作式取消；背景工作結束後才可關閉資料更新頁。"]


def test_real_qapplication_worker_finishes_and_first_close_auto_completes() -> None:
    """真 QThread 完成後，第一次 X 的 pending close 會自動完成。"""

    from PySide6.QtWidgets import QApplication, QMainWindow, QWidget
    from PySide6.QtCore import QTimer

    app = QApplication.instance() or QApplication([])

    class _RealMainWindow(main_module.MainWindow):
        def __init__(self) -> None:
            QMainWindow.__init__(self)
            self.setCentralWidget(QWidget())
            self.update_view = SimpleNamespace(
                begin_shutdown=lambda: None,
                has_running_background_process=lambda: False,
            )
            self.portfolio_view = None
            self.decision_desk_view = None
            self._shutdown_close_requested = False
            self._shutdown_close_finalizing = False
            self._shutdown_close_started_monotonic = None
            self._shutdown_close_last_blockers = ()
            self._shutdown_close_timer = QTimer(self)
            self._shutdown_close_timer.setInterval(10)
            self._shutdown_close_timer.timeout.connect(self._poll_shutdown_close)

    started = False

    def task(cancel_callback=None):
        nonlocal started
        started = True
        while not cancel_callback or not cancel_callback():
            time.sleep(0.005)
        return "cancelled-at-safe-boundary"

    worker = TaskWorker(task)
    window = _RealMainWindow()
    try:
        worker.start()
        deadline = time.monotonic() + 2.0
        while not started and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.005)
        assert started is True

        window.show()
        app.processEvents()
        first_event = _CloseEvent()
        main_module.MainWindow.closeEvent(window, first_event)

        assert first_event.ignored is True
        assert first_event.accepted is False

        deadline = time.monotonic() + 3.0
        while window.isVisible() and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.005)

        assert window.isVisible() is False
        assert worker.isRunning() is False
    finally:
        worker.cancel(cooperative=True, wait=False)
        assert worker.wait(5_000) is True
        window._shutdown_close_timer.stop()
        window.close()
        app.processEvents()


def test_deferred_mainwindow_teardown_releases_cpp_wrapper() -> None:
    """關閉後在 QApplication 有效期間排空 deferred delete。"""

    from PySide6.QtWidgets import QApplication, QMainWindow

    import shiboken6

    app = QApplication.instance() or QApplication([])
    window = QMainWindow()
    window.show()
    app.processEvents()
    window.close()

    main_module._drain_qt_deferred_deletes(app, (window,))

    assert shiboken6.isValid(window) is False
