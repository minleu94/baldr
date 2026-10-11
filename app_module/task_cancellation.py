"""工作階段內部取消能力。

這個模組只提供受限讀取操作使用的一次性、唯讀取消 probe；不依賴 Qt，
也不執行呼叫端提供的 callback。
"""

from __future__ import annotations

from threading import Event, Lock, get_ident
from typing import Callable


_READ_OPERATION_CANCELLATION_SEAL = object()
_ORIGINAL_EVENT_IS_SET = Event.is_set
_ORIGINAL_EVENT_SET = Event.set


def _event_methods_are_original(event: Event) -> bool:
    """確認 Event 沒有替換查詢／設定方法，也未 shadow 類別方法。"""

    if type(event) is not Event:
        return False
    try:
        namespace = object.__getattribute__(event, "__dict__")
    except (AttributeError, TypeError):
        return False
    if type(namespace) is not dict or "is_set" in namespace or "set" in namespace:
        return False

    # 比對模組載入時保存的原方法；不能拿已被 monkeypatch 的現行 class
    # attribute 當作可信基準。
    event_namespace = Event.__dict__
    if (
        event_namespace.get("is_set") is not _ORIGINAL_EVENT_IS_SET
        or event_namespace.get("set") is not _ORIGINAL_EVENT_SET
    ):
        return False
    try:
        bound_is_set = object.__getattribute__(event, "is_set")
        bound_set = object.__getattribute__(event, "set")
    except (AttributeError, TypeError):
        return False
    return (
        getattr(bound_is_set, "__func__", None) is _ORIGINAL_EVENT_IS_SET
        and getattr(bound_set, "__func__", None) is _ORIGINAL_EVENT_SET
    )


class _EventCancellationProbe:
    """只讀取 Event 狀態的 callable，不公開 Event 本身。"""

    __slots__ = ("__event",)

    def __init__(self, event: Event) -> None:
        self.__event = event

    def __call__(self) -> bool:
        # 直接呼叫載入時捕捉的原始 unbound method，避免 probe 動態查找
        # Event instance 上後續被 shadow 的 is_set callback。
        return _ORIGINAL_EVENT_IS_SET(self.__event)


class _ReadOperationCancellationCapability:
    """綁定單一 callback 與發行執行緒的一次性內部能力。"""

    __slots__ = (
        "__seal",
        "__event",
        "__callback",
        "__owner_thread_id",
        "__claimed",
        "__claim_lock",
    )

    def __init__(
        self,
        *,
        event: Event,
        callback: Callable[[], bool],
        owner_thread_id: int,
        seal: object,
    ) -> None:
        if seal is not _READ_OPERATION_CANCELLATION_SEAL:
            raise TypeError("read_operation_cancellation_capability_invalid")
        self.__seal = seal
        self.__event = event
        self.__callback = callback
        self.__owner_thread_id = owner_thread_id
        self.__claimed = False
        self.__claim_lock = Lock()

    def _claim_probe(self, callback: Callable[[], bool] | None) -> Callable[[], bool] | None:
        with self.__claim_lock:
            if self.__claimed:
                return None
            # 原設計要求任何一次 claim 嘗試都消耗能力；callback 或執行緒
            # 綁定不符時只可退回序列路徑，不能再把 token 轉交其他操作。
            self.__claimed = True
            if (
                self.__seal is not _READ_OPERATION_CANCELLATION_SEAL
                or callback is not self.__callback
                or get_ident() != self.__owner_thread_id
            ):
                return None
            return _EventCancellationProbe(self.__event)


def _issue_read_operation_cancellation_capability(
    *,
    event: Event,
    callback: Callable[[], bool],
) -> object:
    """在操作執行緒建立不透明能力；呼叫端須先確認明確 opt-in。"""

    if not _event_methods_are_original(event) or not callable(callback):
        raise TypeError("read_operation_cancellation_capability_invalid")
    return _ReadOperationCancellationCapability(
        event=event,
        callback=callback,
        owner_thread_id=get_ident(),
        seal=_READ_OPERATION_CANCELLATION_SEAL,
    )


def _claim_read_operation_cancellation_probe(
    capability: object,
    callback: Callable[[], bool] | None,
) -> Callable[[], bool] | None:
    """以 exact callback identity 與 owner thread claim 一次唯讀 probe。"""

    if type(capability) is not _ReadOperationCancellationCapability:
        return None
    return capability._claim_probe(callback)
