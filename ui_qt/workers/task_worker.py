"""
統一背景任務 Worker
用於執行長時間運行的任務（推薦、回測、更新資料等）
"""

from PySide6.QtCore import QThread, Signal
from typing import Callable, Any, Dict, Optional
import inspect
import threading
import traceback
from weakref import WeakSet
from app_module.exceptions import BacktestCancelledError


_MANAGED_TASK_WORKERS: WeakSet[QThread] = WeakSet()
# A QThread wrapper must stay strongly referenced until Qt has emitted the
# native ``QThread.finished()`` signal.  The task result signal below is
# emitted from ``run()`` before the native thread has necessarily returned;
# views must not be able to drop the last Python reference in that window.
_LIVE_TASK_WORKERS: set[QThread] = set()


def _supports_cancel_callback(task_function: Callable[..., Any]) -> str | None:
    """回傳任務支援的取消 callback 參數名；舊任務不會被強塞新參數。"""
    try:
        parameters = inspect.signature(task_function).parameters.values()
    except (TypeError, ValueError):
        return None
    names = {parameter.name for parameter in parameters}
    if "cancel_callback" in names:
        return "cancel_callback"
    if "cancellation_callback" in names:
        return "cancellation_callback"
    if any(parameter.kind is inspect.Parameter.VAR_KEYWORD for parameter in parameters):
        return "cancel_callback"
    return None


def _invoke_task_with_optional_cancel(
    task_function: Callable[..., Any],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    callback: Callable[[], bool],
) -> Any:
    """只對明確支援的任務注入合作式取消 callback。"""
    call_kwargs = dict(kwargs)
    callback_name = _supports_cancel_callback(task_function)
    if callback_name is not None and callback_name not in call_kwargs:
        call_kwargs[callback_name] = callback
    return task_function(*args, **call_kwargs)


def _has_explicit_cancel_outcome(result: Any) -> bool:
    """確認任務結果是否明確交代取消與已完成工作量。"""
    if isinstance(result, dict):
        return isinstance(result.get("cancelled"), bool)
    value = getattr(result, "cancelled", None)
    return isinstance(value, bool)


class _ManagedTaskThread(QThread):
    """Keep QThread lifetime separate from the task-result signal lifecycle.

    ``TaskWorker`` historically exposes ``finished(object)`` for task results,
    which shadows QThread's native ``finished()`` signal.  The alias is
    declared on this intermediate class so it still binds to the base Qt
    signal.  Cleanup requested while the task-result callback is running is
    deferred until native thread completion; this prevents deleting a running
    QThread wrapper during queued UI cleanup.
    """

    native_thread_finished = QThread.finished

    def __init__(self) -> None:
        super().__init__()
        self._delete_later_requested = False
        _MANAGED_TASK_WORKERS.add(self)
        self.native_thread_finished.connect(self._on_native_thread_finished)

    def start(self, priority: Any = QThread.InheritPriority) -> None:
        # QThread 在 native run 完成後可以再次 start；finished cleanup 會
        # 將 wrapper 從 managed registry 移除，因此每次真正啟動前都要恢復
        # 登記，讓 shutdown probe 不會漏掉重用中的 worker。
        _MANAGED_TASK_WORKERS.add(self)
        _LIVE_TASK_WORKERS.add(self)
        try:
            super().start(priority)
        except BaseException:
            _LIVE_TASK_WORKERS.discard(self)
            _MANAGED_TASK_WORKERS.discard(self)
            raise

    def deleteLater(self) -> None:
        """Defer QObject deletion until the native QThread has stopped."""

        try:
            is_running = self.isRunning()
        except RuntimeError:
            # QObject 已由 Qt teardown 刪除時，Python wrapper 仍可能被
            # queued cleanup 暫時持有；從兩個 registry 移除即可，不能再
            # 呼叫任何 Qt method。
            _LIVE_TASK_WORKERS.discard(self)
            _MANAGED_TASK_WORKERS.discard(self)
            return
        if is_running:
            self._delete_later_requested = True
            return
        _LIVE_TASK_WORKERS.discard(self)
        _MANAGED_TASK_WORKERS.discard(self)
        super().deleteLater()

    def _on_native_thread_finished(self) -> None:
        # Native finished 代表 wrapper 不應再被全域 shutdown probe 查詢；
        # 留在 weak set 會讓稍後的 closeEvent 對已結束的 PySide QThread
        # 再次呼叫 isRunning()，部分 offscreen teardown 會因此卡住。
        _MANAGED_TASK_WORKERS.discard(self)
        if self._delete_later_requested:
            self._delete_later_requested = False
            super().deleteLater()
        _LIVE_TASK_WORKERS.discard(self)


def running_task_workers() -> tuple[QThread, ...]:
    """傳回仍在執行的受管背景工作，供根視窗安全關閉協調。"""

    running: list[QThread] = []
    for worker in tuple(_MANAGED_TASK_WORKERS):
        try:
            is_running = worker.isRunning()
        except RuntimeError:
            # PySide wrapper 可能在 native QObject 已刪除後仍短暫存於
            # WeakSet；shutdown probe 必須丟棄它，而不是讓 closeEvent
            # 因 ``Internal C++ object ... already deleted`` 中止。
            _MANAGED_TASK_WORKERS.discard(worker)
            _LIVE_TASK_WORKERS.discard(worker)
            continue
        if is_running:
            running.append(worker)
    return tuple(running)


def request_cooperative_task_worker_shutdown() -> tuple[QThread, ...]:
    """送出非阻塞合作式取消，回傳仍未安全結束的工作。

    此函式刻意不呼叫 ``terminate()`` 或 ``wait()``。呼叫端若仍有回傳
    worker，必須保留視窗並等待工作自然結束，不能在持有 SQLite／檔案資源時
    強制關閉程序。
    """

    for worker in running_task_workers():
        try:
            cancel = getattr(worker, "cancel", None)
        except RuntimeError:
            _MANAGED_TASK_WORKERS.discard(worker)
            _LIVE_TASK_WORKERS.discard(worker)
            continue
        if callable(cancel):
            try:
                cancel(cooperative=True, wait=False)
            except RuntimeError:
                # Native QObject 可能剛在 queued callback 中被刪除；不要讓
                # 關閉協調器因 stale wrapper 中止，也不要再把它留在 registry。
                _MANAGED_TASK_WORKERS.discard(worker)
                _LIVE_TASK_WORKERS.discard(worker)
    return running_task_workers()


class TaskWorker(_ManagedTaskThread):
    """通用背景任務 Worker

    使用方式：
        worker = TaskWorker(task_function, arg1, arg2, kwarg1=value1)
        worker.finished.connect(on_finished)
        worker.error.connect(on_error)
        worker.progress.connect(on_progress)
        worker.cancelled.connect(on_cancelled)
        worker.start()
    """

    # 信號定義
    started = Signal()  # 任務開始
    finished = Signal(object)  # 任務完成，傳遞結果
    error = Signal(str)  # 任務出錯，傳遞錯誤信息
    progress = Signal(str, int)  # 進度更新 (message, percentage)
    cancelled = Signal()  # 任務被取消

    def __init__(
        self,
        task_function: Callable,
        *args,
        **kwargs
    ):
        """初始化 Worker

        Args:
            task_function: 要執行的函數
            *args: 位置參數
            **kwargs: 關鍵字參數
        """
        super().__init__()
        self.task_function = task_function
        self.args = args
        self.kwargs = kwargs
        self._is_cancelled = False
        self._cancel_event = threading.Event()

    def is_cancel_requested(self) -> bool:
        """以 thread-safe event 查詢合作式取消請求。"""
        return self._cancel_event.is_set() or self._is_cancelled

    def run(self):
        """執行任務（在背景線程中運行）"""
        try:
            self.started.emit()

            # ✅ 檢查是否已取消
            if self.is_cancel_requested():
                self.cancelled.emit()
                return

            # 執行任務函數
            result = _invoke_task_with_optional_cancel(
                self.task_function,
                self.args,
                self.kwargs,
                self.is_cancel_requested,
            )

            # ✅ 再次檢查是否已取消（任務執行期間可能被取消）
            if self.is_cancel_requested() and not _has_explicit_cancel_outcome(result):
                self.cancelled.emit()
            else:
                self.finished.emit(result)

        except BacktestCancelledError:
            self.cancelled.emit()
        except Exception as e:
            # 取消旗標不能掩蓋真實例外；只有任務明確回報安全取消或
            # BacktestCancelledError 才送出 cancelled signal。
            error_msg = f"{str(e)}\n{traceback.format_exc()}"
            self.error.emit(error_msg)

    def cancel(self, cooperative: bool = True, wait: bool = False):
        """取消任務

        Args:
            cooperative: 保留給既有呼叫端的相容參數。取消一律採合作式，
                僅設置取消標記，不會呼叫 QThread.terminate()。
            wait: 是否在呼叫取消後同步等待執行緒結束。預設為 false，避免
                關閉 UI 時在主執行緒無期限阻塞。
        """
        self._cancel_event.set()
        self._is_cancelled = True
        if wait:
            self.wait()


class ProgressTaskWorker(_ManagedTaskThread):
    """支持進度報告的任務 Worker

    任務函數需要接受一個 progress_callback 參數：
        def my_task(arg1, arg2, progress_callback=None):
            progress_callback("開始處理...", 0)
            # ... 處理邏輯
            progress_callback("處理中...", 50)
            # ... 更多處理
            progress_callback("完成", 100)
            return result
    """

    # 信號定義
    started = Signal()
    finished = Signal(object)
    error = Signal(str)
    progress = Signal(str, int)  # (message, percentage)
    cancelled = Signal()  # 任務被取消

    def __init__(
        self,
        task_function: Callable,
        *args,
        **kwargs
    ):
        """初始化 Worker

        Args:
            task_function: 要執行的函數（需要接受 progress_callback 參數）
            *args: 位置參數
            **kwargs: 關鍵字參數
        """
        super().__init__()
        self.task_function = task_function
        self.args = args
        self.kwargs = kwargs
        self._is_cancelled = False
        self._cancel_event = threading.Event()

    def is_cancel_requested(self) -> bool:
        """以 thread-safe event 查詢合作式取消請求。"""
        return self._cancel_event.is_set() or self._is_cancelled

    def _progress_callback(self, message: str, percentage: int):
        """進度回調函數"""
        if not self.is_cancel_requested():
            self.progress.emit(message, percentage)

    def run(self):
        """執行任務"""
        try:
            self.started.emit()

            # ✅ 檢查是否已取消
            if self.is_cancel_requested():
                self.cancelled.emit()
                return

            # 將 progress_callback 添加到 kwargs
            kwargs_with_progress = {**self.kwargs, 'progress_callback': self._progress_callback}

            # 執行任務函數
            result = _invoke_task_with_optional_cancel(
                self.task_function,
                self.args,
                kwargs_with_progress,
                self.is_cancel_requested,
            )

            if self.is_cancel_requested() and not _has_explicit_cancel_outcome(result):
                self.cancelled.emit()
            else:
                self.finished.emit(result)

        except BacktestCancelledError:
            self.cancelled.emit()
        except Exception as e:
            error_msg = f"{str(e)}\n{traceback.format_exc()}"
            self.error.emit(error_msg)

    def cancel(self, cooperative: bool = True, wait: bool = False):
        """取消任務

        Args:
            cooperative: 保留給既有呼叫端的相容參數。取消一律採合作式，
                僅設置取消標記，不會呼叫 QThread.terminate()。
            wait: 是否在呼叫取消後同步等待執行緒結束。預設為 false，避免
                關閉 UI 時在主執行緒無期限阻塞。
        """
        self._cancel_event.set()
        self._is_cancelled = True
        if wait:
            self.wait()


