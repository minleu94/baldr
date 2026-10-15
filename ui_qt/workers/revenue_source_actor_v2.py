"""提供雙來源研究 View 使用的長駐、單一 owner-thread actor。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from threading import Condition, Event, Lock, get_ident
from typing import Literal, Protocol, TypeAlias

from PySide6.QtCore import QThread, Signal


class ClosableHandle(Protocol):
    """由 actor 建立、使用及關閉的來源 handle。"""

    def close(self) -> None:
        """釋放 handle 持有的資源。"""


CancelCheck: TypeAlias = Callable[[], bool]
OpenCallable: TypeAlias = Callable[[CancelCheck], ClosableHandle]
ProjectCallable: TypeAlias = Callable[[ClosableHandle, CancelCheck], object]
TaskCallable: TypeAlias = Callable[[ClosableHandle, CancelCheck], object]


@dataclass(frozen=True, slots=True)
class _OpenRequest:
    token: int
    opener: OpenCallable
    project: ProjectCallable
    cancel_event: Event


@dataclass(frozen=True, slots=True)
class _TaskRequest:
    token: int
    task: TaskCallable
    cancel_event: Event


_Request: TypeAlias = _OpenRequest | _TaskRequest
_Outcome: TypeAlias = Literal["succeeded", "failed", "cancelled"]


class _ActorCancelled(Exception):
    """表示合作式取消已在不可變更的提交點前被觀測到。"""


class RevenueSourceActorV2(QThread):
    """在專屬 QThread 內序列化來源開啟、分頁工作及 handle 關閉。

    Actor 建立後即進入等待迴圈。每次只接受一筆請求；來源替換在候選
    source 完成 projection 並通過最後取消檢查後才提交。取消與失敗會
    關閉候選 source，保留先前已提交的 source。
    """

    succeeded = Signal(int, object)
    failed = Signal(int, str)
    cancelled = Signal(int)
    settled = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        self._state_lock = Lock()
        self._condition = Condition(self._state_lock)
        self._pending_request: _Request | None = None
        self._current_cancel_event: Event | None = None
        self._request_committed = False
        self._busy = False
        self._has_source = False
        self._shutdown_requested = False
        self._source: ClosableHandle | None = None
        self._retired_handles: list[ClosableHandle] = []
        self._owner_thread_id: int | None = None
        self.start()

    @property
    def busy(self) -> bool:
        """回報 actor 是否正在處理唯一請求。"""

        with self._state_lock:
            return self._busy

    @property
    def has_source(self) -> bool:
        """回報是否有已提交且可供下一個 task 使用的來源。"""

        with self._state_lock:
            return self._has_source

    @property
    def shutdown_requested(self) -> bool:
        """回報 actor 是否已收到合作式停止要求。"""

        with self._state_lock:
            return self._shutdown_requested

    def submit_open(
        self,
        token: int,
        opener: OpenCallable,
        project: ProjectCallable,
    ) -> bool:
        """排入來源替換；忙碌或停止中的 actor 會明確拒絕新請求。"""

        if type(token) is not int or not callable(opener) or not callable(project):
            return False
        request = _OpenRequest(token, opener, project, Event())
        return self._reserve_request(request)

    def submit_task(self, token: int, task: TaskCallable) -> bool:
        """排入目前來源上的一次 owner-thread 操作。"""

        if type(token) is not int or not callable(task):
            return False
        request = _TaskRequest(token, task, Event())
        return self._reserve_request(request)

    def cancel_current(self) -> None:
        """要求目前請求合作式取消，不阻塞呼叫端。"""

        with self._condition:
            event = self._current_cancel_event
            if self._busy and event is not None and not self._request_committed:
                event.set()
            self._condition.notify_all()

    def request_shutdown(self) -> None:
        """要求停止並在 owner thread 關閉來源；不呼叫 terminate 或 wait。"""

        with self._condition:
            self._shutdown_requested = True
            event = self._current_cancel_event
            if self._busy and event is not None and not self._request_committed:
                event.set()
            self._condition.notify_all()

    def _reserve_request(self, request: _Request) -> bool:
        with self._condition:
            if self._shutdown_requested or self._busy or self._pending_request is not None:
                return False
            self._pending_request = request
            self._current_cancel_event = request.cancel_event
            self._request_committed = False
            self._busy = True
            self._condition.notify_all()
            return True

    def _cancel_check(self) -> bool:
        """以穩定 bound method 動態讀取目前 request 的取消狀態。"""

        with self._state_lock:
            event = self._current_cancel_event
            return self._shutdown_requested or (event is not None and event.is_set())

    def run(self) -> None:
        """在 QThread owner thread 消化請求，然後安全關閉來源並自然退出。"""

        self._owner_thread_id = get_ident()
        while True:
            with self._condition:
                while self._pending_request is None and not self._shutdown_requested:
                    self._condition.wait()
                if self._pending_request is None and self._shutdown_requested:
                    break
                request = self._pending_request
                self._pending_request = None
            if request is None:
                continue
            outcome, payload, error_message = self._execute_request(request)
            self._settle_request(request, outcome, payload, error_message)
        self._close_owned_handles()

    def _execute_request(
        self,
        request: _Request,
    ) -> tuple[_Outcome, object | None, str | None]:
        if self._cancel_check():
            return "cancelled", None, None
        try:
            if isinstance(request, _OpenRequest):
                payload = self._execute_open(request)
            else:
                payload = self._execute_task(request)
        except BaseException as exc:
            if self._request_was_cancelled(request):
                return "cancelled", None, None
            return "failed", None, self._error_text(exc)
        return "succeeded", payload, None

    def _execute_open(self, request: _OpenRequest) -> object:
        candidate: ClosableHandle | None = None
        committed = False
        try:
            candidate = request.opener(self._cancel_check)
            if not callable(getattr(candidate, "close", None)):
                raise TypeError("revenue_source_actor_handle_not_closable")
            if self._cancel_check():
                raise _ActorCancelled()
            payload = request.project(candidate, self._cancel_check)
            old_source = self._commit_candidate(request, candidate)
            committed = True
            candidate = None
            if old_source is not None:
                self._close_handle(old_source)
            return payload
        except BaseException:
            if candidate is not None and not committed:
                self._close_handle(candidate)
            raise

    def _execute_task(self, request: _TaskRequest) -> object:
        with self._state_lock:
            source = self._source
        if source is None:
            raise RuntimeError("revenue_source_actor_source_unavailable")
        if not callable(getattr(source, "close", None)):
            raise RuntimeError("revenue_source_actor_committed_handle_invalid")
        payload = request.task(source, self._cancel_check)
        with self._state_lock:
            if request.cancel_event.is_set() or self._shutdown_requested:
                raise _ActorCancelled()
            self._request_committed = True
        return payload

    def _commit_candidate(
        self,
        request: _OpenRequest,
        candidate: ClosableHandle,
    ) -> ClosableHandle | None:
        with self._state_lock:
            if request.cancel_event.is_set() or self._shutdown_requested:
                raise _ActorCancelled()
            old_source = self._source
            self._source = candidate
            self._has_source = True
            self._request_committed = True
            return old_source

    def _request_was_cancelled(self, request: _Request) -> bool:
        with self._state_lock:
            return not self._request_committed and (
                request.cancel_event.is_set() or self._shutdown_requested
            )

    def _settle_request(
        self,
        request: _Request,
        outcome: _Outcome,
        payload: object | None,
        error_message: str | None,
    ) -> None:
        with self._condition:
            self._busy = False
            self._pending_request = None
            self._current_cancel_event = None
            self._request_committed = False
            self._condition.notify_all()
        if outcome == "succeeded":
            self.succeeded.emit(request.token, payload)
        elif outcome == "cancelled":
            self.cancelled.emit(request.token)
        else:
            self.failed.emit(request.token, error_message or "revenue_source_actor_failed")
        self.settled.emit(request.token)

    def _close_handle(self, handle: ClosableHandle) -> None:
        try:
            handle.close()
        except BaseException:
            self._retired_handles.append(handle)

    def _close_owned_handles(self) -> None:
        with self._state_lock:
            source = self._source
            self._source = None
            self._has_source = False
            retired = tuple(self._retired_handles)
            self._retired_handles.clear()
        handles = (() if source is None else (source,)) + retired
        for handle in handles:
            try:
                handle.close()
            except BaseException:
                # 停機時只重試一次；不以強制終止中斷來源自己的 close。 
                pass

    @staticmethod
    def _error_text(exc: BaseException) -> str:
        message = str(exc).strip()
        return message or type(exc).__name__


__all__ = ["ClosableHandle", "RevenueSourceActorV2"]
