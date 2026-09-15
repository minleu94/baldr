"""受控 Qt QA launcher 的純 Python process contract 測試。"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess

from scripts import qa_run_research_journey_qt_subprocess as runner


class _CompletedChild:
    def __init__(self, return_code: int) -> None:
        self.pid = 42_424
        self.returncode = return_code
        self.wait_calls: list[float | None] = []
        self.terminate_calls = 0
        self.kill_calls = 0

    def wait(self, timeout: float | None = None) -> int:
        self.wait_calls.append(timeout)
        return self.returncode

    def poll(self) -> int | None:
        return self.returncode

    def terminate(self) -> None:
        self.terminate_calls += 1

    def kill(self) -> None:
        self.kill_calls += 1


class _TimeoutChild(_CompletedChild):
    def __init__(self, return_code: int) -> None:
        super().__init__(return_code)
        self._wait_count = 0
        self._terminated = False

    def poll(self) -> int | None:
        return self.returncode if self._terminated else None

    def wait(self, timeout: float | None = None) -> int:
        self._wait_count += 1
        self.wait_calls.append(timeout)
        if self._wait_count == 1:
            assert timeout is not None
            raise subprocess.TimeoutExpired("research-journey-child", timeout)
        return self.returncode

    def terminate(self) -> None:
        self._terminated = True
        super().terminate()


class _FakeOwnedProcessTree:
    management_mode = "test_owned_process_tree"

    def __init__(self) -> None:
        self.attached = False
        self.closed = False

    def mark_attached(self) -> None:
        self.attached = True

    def close(self) -> None:
        self.closed = True


def _read_metadata(output_dir: Path) -> dict[str, object]:
    metadata_paths = sorted(output_dir.glob("controlled_run_*/process.json"))
    assert len(metadata_paths) == 1
    return json.loads(metadata_paths[0].read_text(encoding="utf-8"))


def test_launcher_finds_nested_child_pid_receipt(tmp_path):
    run_dir = tmp_path / "controlled_run"
    nested = run_dir / "run_20260915_000000_abcd1234"
    nested.mkdir(parents=True)
    receipt = nested / "child_process.json"
    receipt.write_text("{\"pid\": 1234}", encoding="utf-8")

    assert runner._find_child_process_metadata_path(run_dir) == receipt


def _fake_spawn(child):
    def spawn(command, **kwargs):
        output_dir = Path(command[command.index("--output-dir") + 1])
        (output_dir / "child_process.json").write_text(
            json.dumps(
                {
                    "pid": child.pid,
                    "ppid": 1,
                    "status": "running",
                }
            ),
            encoding="utf-8",
        )
        kwargs["owned_process_tree"].mark_attached()
        return child

    return spawn


def test_launcher_preserves_nonzero_child_exit_without_retry(tmp_path, monkeypatch):
    output_dir = tmp_path / "evidence"
    child = _CompletedChild(3221225477)
    popen_calls: list[tuple[object, dict[str, object]]] = []

    def fake_spawn(command, **kwargs):
        popen_calls.append((command, kwargs))
        output_dir = Path(command[command.index("--output-dir") + 1])
        (output_dir / "child_process.json").write_text(
            json.dumps({"pid": child.pid, "ppid": 1, "status": "passed"}),
            encoding="utf-8",
        )
        kwargs["owned_process_tree"].mark_attached()
        return child

    monkeypatch.setattr(runner, "_spawn_owned_child", fake_spawn)
    monkeypatch.setattr(runner, "_OwnedProcessTree", _FakeOwnedProcessTree)

    exit_code = runner.run(["--output-dir", str(output_dir)])

    metadata = _read_metadata(output_dir)
    assert exit_code == 3221225477
    assert metadata["status"] == "child_failed"
    assert metadata["exit_code"] == 3221225477
    assert metadata["automatic_retries"] == 0
    assert metadata["runner_pid"] == 42424
    assert metadata["owned_process_tree_attached"] is True
    assert metadata["owned_process_tree_closed"] is True
    assert len(popen_calls) == 1
    assert child.terminate_calls == 0
    assert child.kill_calls == 0


def test_launcher_timeout_only_terminates_owned_child_and_records_exit_code(
    tmp_path,
    monkeypatch,
):
    output_dir = tmp_path / "evidence"
    child = _TimeoutChild(3221225477)

    monkeypatch.setattr(runner, "_spawn_owned_child", _fake_spawn(child))
    monkeypatch.setattr(runner, "_OwnedProcessTree", _FakeOwnedProcessTree)
    monkeypatch.setattr(runner, "_is_process_pid_running", lambda _pid: False)

    exit_code = runner.run(
        [
            "--output-dir",
            str(output_dir),
            "--timeout-seconds",
            "0.01",
            "--terminate-grace-seconds",
            "0.01",
        ]
    )

    metadata = _read_metadata(output_dir)
    assert exit_code == runner.DEFAULT_TIMEOUT_EXIT_CODE
    assert metadata["status"] == "timed_out"
    assert metadata["timed_out"] is True
    assert metadata["exit_code"] == 3221225477
    assert metadata["termination_scope"] == "owned_windows_job_object_process_tree"
    assert metadata["owned_process_tree_attached"] is True
    assert metadata["owned_process_tree_closed"] is True
    assert metadata["reported_child_pid_exit_proof"] == "pid_not_running_after_tree_close"
    assert child.terminate_calls == 1
    assert child.kill_calls == 0


class _FailingCloseProcessTree(_FakeOwnedProcessTree):
    def close(self) -> None:
        raise OSError("simulated Job Object close failure")


def test_launcher_treats_owned_process_tree_close_failure_as_launcher_error(
    tmp_path,
    monkeypatch,
):
    output_dir = tmp_path / "evidence"
    child = _CompletedChild(0)

    monkeypatch.setattr(runner, "_spawn_owned_child", _fake_spawn(child))
    monkeypatch.setattr(runner, "_OwnedProcessTree", _FailingCloseProcessTree)

    exit_code = runner.run(["--output-dir", str(output_dir)])

    metadata = _read_metadata(output_dir)
    assert exit_code == 1
    assert metadata["status"] == "launcher_error"
    assert metadata["owned_process_tree_closed"] is False
    assert "owned process tree close failed" in str(metadata["error"])
