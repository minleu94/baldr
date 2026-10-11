"""工作階段內部取消能力的純 Python 定向測試。"""

from threading import Barrier, Event, Lock, Thread

import pytest

from app_module.task_cancellation import (
    _claim_read_operation_cancellation_probe,
    _issue_read_operation_cancellation_capability,
)


def test_read_operation_probe_is_read_only_and_tracks_the_issued_event() -> None:
    event = Event()
    callback = lambda: event.is_set()
    capability = _issue_read_operation_cancellation_capability(
        event=event,
        callback=callback,
    )

    probe = _claim_read_operation_cancellation_probe(capability, callback)

    assert callable(probe)
    assert probe is not None
    assert probe() is False
    assert not hasattr(capability, "event")
    assert not hasattr(capability, "set")
    assert not hasattr(probe, "event")
    assert not hasattr(probe, "set")

    event.set()

    assert probe() is True


def test_callback_identity_mismatch_consumes_capability_and_falls_back() -> None:
    event = Event()
    callback = lambda: event.is_set()
    equivalent_callback = lambda: event.is_set()
    capability = _issue_read_operation_cancellation_capability(
        event=event,
        callback=callback,
    )

    assert _claim_read_operation_cancellation_probe(
        capability, equivalent_callback
    ) is None
    assert _claim_read_operation_cancellation_probe(capability, callback) is None


def test_successful_claim_is_one_use() -> None:
    event = Event()
    callback = lambda: event.is_set()
    capability = _issue_read_operation_cancellation_capability(
        event=event,
        callback=callback,
    )

    assert _claim_read_operation_cancellation_probe(capability, callback) is not None
    assert _claim_read_operation_cancellation_probe(capability, callback) is None


def test_wrong_thread_claim_consumes_capability_and_falls_back() -> None:
    event = Event()
    callback = lambda: event.is_set()
    capability = _issue_read_operation_cancellation_capability(
        event=event,
        callback=callback,
    )
    wrong_thread_results: list[object] = []

    thread = Thread(
        target=lambda: wrong_thread_results.append(
            _claim_read_operation_cancellation_probe(capability, callback)
        )
    )
    thread.start()
    thread.join(timeout=5)

    assert not thread.is_alive()
    assert wrong_thread_results == [None]
    assert _claim_read_operation_cancellation_probe(capability, callback) is None


def test_probe_never_calls_the_raising_or_reentrant_external_callback() -> None:
    event = Event()
    callback_calls: list[str] = []
    capability_holder: dict[str, object] = {}

    def external_callback() -> bool:
        callback_calls.append("called")
        _claim_read_operation_cancellation_probe(
            capability_holder["capability"], external_callback
        )
        raise RuntimeError("the external callback must not run in the probe")

    capability = _issue_read_operation_cancellation_capability(
        event=event,
        callback=external_callback,
    )
    capability_holder["capability"] = capability
    probe = _claim_read_operation_cancellation_probe(capability, external_callback)

    assert probe is not None
    assert probe() is False
    event.set()
    assert probe() is True
    assert callback_calls == []


def test_capability_rejects_event_subclasses() -> None:
    class DerivedEvent(Event):
        pass

    with pytest.raises(TypeError, match="read_operation_cancellation_capability_invalid"):
        _issue_read_operation_cancellation_capability(
            event=DerivedEvent(),
            callback=lambda: False,
        )


@pytest.mark.parametrize("method_name", ["is_set", "set"])
def test_capability_rejects_shadowed_event_methods_without_calling_them(method_name: str) -> None:
    event = Event()
    calls: list[str] = []

    def caller_method(*_args: object, **_kwargs: object) -> bool:
        calls.append(method_name)
        return False

    setattr(event, method_name, caller_method)
    with pytest.raises(TypeError, match="read_operation_cancellation_capability_invalid"):
        _issue_read_operation_cancellation_capability(
            event=event,
            callback=lambda: False,
        )

    assert calls == []


def test_unmodified_exact_event_methods_issue_a_live_read_only_probe() -> None:
    event = Event()
    callback = event.is_set
    capability = _issue_read_operation_cancellation_capability(
        event=event,
        callback=callback,
    )

    probe = _claim_read_operation_cancellation_probe(capability, callback)
    assert probe is not None
    assert probe() is False
    event.set()
    assert probe() is True


def test_probe_does_not_call_an_is_set_shadow_added_after_claim() -> None:
    event = Event()
    callback = lambda: event.is_set()
    capability = _issue_read_operation_cancellation_capability(
        event=event,
        callback=callback,
    )
    probe = _claim_read_operation_cancellation_probe(capability, callback)
    assert probe is not None

    calls: list[str] = []
    event.is_set = lambda: calls.append("is_set") or True  # type: ignore[method-assign]

    assert probe() is False
    assert calls == []


@pytest.mark.parametrize("method_name", ["is_set", "set"])
def test_capability_rejects_replaced_event_class_method(method_name: str, monkeypatch) -> None:
    event = Event()
    monkeypatch.setattr(Event, method_name, lambda *_args: False)

    with pytest.raises(TypeError, match="read_operation_cancellation_capability_invalid"):
        _issue_read_operation_cancellation_capability(
            event=event,
            callback=lambda: False,
        )


def test_simultaneous_cross_thread_claims_have_at_most_one_success() -> None:
    event = Event()
    callback = lambda: event.is_set()
    capability = _issue_read_operation_cancellation_capability(
        event=event,
        callback=callback,
    )
    contender_count = 8
    start = Barrier(contender_count + 1)
    result_lock = Lock()
    results: list[object] = []

    def contend() -> None:
        start.wait(timeout=5)
        result = _claim_read_operation_cancellation_probe(capability, callback)
        with result_lock:
            results.append(result)

    threads = [Thread(target=contend) for _ in range(contender_count)]
    for thread in threads:
        thread.start()
    start.wait(timeout=5)
    owner_result = _claim_read_operation_cancellation_probe(capability, callback)
    with result_lock:
        results.append(owner_result)
    for thread in threads:
        thread.join(timeout=5)

    assert all(not thread.is_alive() for thread in threads)
    successful_claims = [result for result in results if result is not None]
    assert len(successful_claims) <= 1


@pytest.mark.parametrize("capability", [None, object(), "not-a-capability"])
def test_invalid_capability_falls_back_without_claiming_a_probe(capability: object) -> None:
    assert _claim_read_operation_cancellation_probe(capability, lambda: False) is None


def test_capability_issuer_rejects_non_event_or_non_callable_inputs() -> None:
    with pytest.raises(TypeError, match="read_operation_cancellation_capability_invalid"):
        _issue_read_operation_cancellation_capability(
            event=object(),  # type: ignore[arg-type]
            callback=lambda: False,
        )

    with pytest.raises(TypeError, match="read_operation_cancellation_capability_invalid"):
        _issue_read_operation_cancellation_capability(
            event=Event(),
            callback=None,  # type: ignore[arg-type]
        )
