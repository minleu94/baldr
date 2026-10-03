from __future__ import annotations

from types import SimpleNamespace

import pytest

from scripts import qa_cross_page_mainwindow_readback as readback


class _FakeDialog:
    def __init__(self, *, busy: bool = False) -> None:
        self.busy = busy

    def is_busy(self) -> bool:
        return self.busy


class _FakeUpdateView:
    def __init__(self, *, process_running: bool = False) -> None:
        self.process_running = process_running
        self._tpex_background_process = (
            SimpleNamespace(pid=4132) if process_running else None
        )

    def has_running_background_process(self) -> bool:
        return self.process_running


class _FakeWindow:
    def __init__(self, update_view: _FakeUpdateView) -> None:
        self.update_view = update_view
        self.close_calls = 0

    def close(self) -> None:
        self.close_calls += 1


def test_loaded_views_wait_for_worker_research_and_process_idle_then_close_once(
    monkeypatch,
) -> None:
    live_worker = object()
    worker_state = {"workers": (live_worker,)}
    monkeypatch.setattr(
        readback,
        "running_task_workers",
        lambda: worker_state["workers"],
    )
    dialog = _FakeDialog(busy=True)
    update_view = _FakeUpdateView(process_running=True)
    window = _FakeWindow(update_view)
    receipt: dict[str, object] = {"idle_close_requests": 0}
    coordinator = readback._ReadbackIdleCloseCoordinator(window, dialog, receipt)

    assert coordinator.request_close_if_idle() is False
    assert window.close_calls == 0
    assert receipt["idle_close_requests"] == 0
    worker_state["workers"] = ()

    assert coordinator.request_close_if_idle() is False
    assert window.close_calls == 0
    dialog.busy = False

    assert coordinator.request_close_if_idle() is False
    assert window.close_calls == 0
    update_view.process_running = False
    update_view._tpex_background_process = None

    assert coordinator.request_close_if_idle() is True
    assert coordinator.request_close_if_idle() is True
    assert window.close_calls == 1
    assert receipt["idle_close_requests"] == 1
    assert receipt["idle_close_poll_count"] == 4
    before_close = receipt["idle_close_before_state"]
    assert isinstance(before_close, dict)
    assert before_close["task_worker_count"] == 0
    assert before_close["research_dialog_busy"] is False
    assert before_close["update_background_process_running"] is False
    assert before_close["idle"] is True


def test_unavailable_update_process_probe_fails_closed(monkeypatch) -> None:
    class _UnavailableUpdateView:
        def has_running_background_process(self) -> bool:
            raise OSError("process handle unavailable")

    monkeypatch.setattr(readback, "running_task_workers", lambda: ())
    window = _FakeWindow(_FakeUpdateView())
    window.update_view = _UnavailableUpdateView()
    dialog = _FakeDialog()
    receipt: dict[str, object] = {"idle_close_requests": 0}
    coordinator = readback._ReadbackIdleCloseCoordinator(window, dialog, receipt)

    assert coordinator.request_close_if_idle() is False
    assert window.close_calls == 0
    state = receipt["idle_close_last_state"]
    assert isinstance(state, dict)
    assert state["update_background_process_running"] is None
    assert state["idle"] is False
    assert "update_process_probe_error:OSError" in state["probe_errors"]


@pytest.mark.parametrize(("value", "type_name"), [(None, "NoneType"), (0, "int")])
def test_non_boolean_update_process_probe_fails_closed(
    monkeypatch,
    value: object,
    type_name: str,
) -> None:
    class _UnknownUpdateView:
        def has_running_background_process(self) -> object:
            return value

    monkeypatch.setattr(readback, "running_task_workers", lambda: ())
    window = _FakeWindow(_FakeUpdateView())
    window.update_view = _UnknownUpdateView()
    dialog = _FakeDialog()
    receipt: dict[str, object] = {"idle_close_requests": 0}
    coordinator = readback._ReadbackIdleCloseCoordinator(window, dialog, receipt)

    assert coordinator.request_close_if_idle() is False
    assert window.close_calls == 0
    state = receipt["idle_close_last_state"]
    assert isinstance(state, dict)
    assert state["update_background_process_running"] is None
    assert state["idle"] is False
    assert f"update_process_probe_invalid_type:{type_name}" in state["probe_errors"]


@pytest.mark.parametrize(("value", "type_name"), [(None, "NoneType"), (0, "int")])
def test_non_boolean_research_busy_probe_fails_closed(
    monkeypatch,
    value: object,
    type_name: str,
) -> None:
    class _UnknownDialog:
        def is_busy(self) -> object:
            return value

    monkeypatch.setattr(readback, "running_task_workers", lambda: ())
    window = _FakeWindow(_FakeUpdateView())
    receipt: dict[str, object] = {"idle_close_requests": 0}
    coordinator = readback._ReadbackIdleCloseCoordinator(
        window,
        _UnknownDialog(),
        receipt,
    )

    assert coordinator.request_close_if_idle() is False
    assert window.close_calls == 0
    state = receipt["idle_close_last_state"]
    assert isinstance(state, dict)
    assert state["research_dialog_busy"] is None
    assert state["idle"] is False
    assert f"research_busy_probe_invalid_type:{type_name}" in state["probe_errors"]
