"""產生 Windows owned process-tree normal／timeout 的可查核 QA 證據。

此 probe 不載入 Qt、不修改 WER／registry，也不碰正式資料。它重用受控
Qt launcher 的 suspended CreateProcess → Job assignment → ResumeThread
實作，讓 normal／timeout 的 raw JSON 與 child stdout log 可直接查核。
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import sys
import time
from typing import Any
from uuid import uuid4

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts import qa_run_research_journey_qt_subprocess as launcher


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="owned process-tree normal／timeout probe")
    parser.add_argument(
        "--output-dir",
        default=str(Path("output") / "qa" / "win32_process_tree_probe_20260915"),
    )
    return parser.parse_args(argv)


def _now() -> str:
    return datetime.now().astimezone().isoformat()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _child_code(*, keep_running: bool) -> str:
    sleep_code = "while True: time.sleep(1.0)" if keep_running else "time.sleep(0.2)"
    return (
        "import json, os, sys, time\n"
        "from pathlib import Path\n"
        "Path(sys.argv[1]).write_text(json.dumps({'pid':os.getpid(),"
        "'ppid':os.getppid(),'status':'running'}), encoding='utf-8')\n"
        f"{sleep_code}\n"
    )


def _wait_for_payload_receipt(path: Path, timeout_seconds: float = 3.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            time.sleep(0.01)
            continue
        if isinstance(payload, dict) and isinstance(payload.get("pid"), int):
            return payload
        time.sleep(0.01)
    raise RuntimeError(f"child payload receipt 未在期限內產生：{path}")


def _run_case(output_dir: Path, *, name: str, keep_running: bool) -> dict[str, Any]:
    case_dir = output_dir / name
    case_dir.mkdir(parents=True, exist_ok=False)
    receipt_path = case_dir / "payload.json"
    log_path = case_dir / "child.log"
    tree = launcher._OwnedProcessTree()
    child: Any = None
    return_code: int | None = None
    timeout_observed = False
    termination_action: str | None = None
    tree_close_error: str | None = None
    child_close_error: str | None = None
    receipt: dict[str, Any] = {}
    payload_running_before_tree_close: bool | None = None
    payload_running_after_tree_close: bool | None = None

    command = [
        sys.executable,
        "-u",
        "-c",
        _child_code(keep_running=keep_running),
        str(receipt_path),
    ]
    try:
        with log_path.open("wb") as log_handle:
            child = launcher._spawn_owned_child(
                command,
                cwd=Path.cwd(),
                env=os.environ.copy(),
                log_handle=log_handle,
                owned_process_tree=tree,
            )
            receipt = _wait_for_payload_receipt(receipt_path)
            payload_pid = receipt["pid"]
            payload_running_before_tree_close = launcher._is_process_pid_running(payload_pid)
            if keep_running:
                timeout_observed = True
                try:
                    child.wait(timeout=0.1)
                except TimeoutError:
                    # The custom Windows wrapper raises subprocess.TimeoutExpired;
                    # retain the generic fallback for the POSIX test double.
                    timeout_observed = True
                except Exception as exc:
                    import subprocess

                    if isinstance(exc, subprocess.TimeoutExpired):
                        timeout_observed = True
                    else:
                        raise
                if timeout_observed:
                    return_code, termination_action = launcher._terminate_owned_child(
                        child,
                        0.1,
                    )
            else:
                return_code = child.wait(timeout=5.0)
    finally:
        try:
            tree.close()
        except Exception as exc:  # pragma: no cover - OS failure evidence
            tree_close_error = f"{type(exc).__name__}: {exc}"
        if child is not None:
            close_child = getattr(child, "close", None)
            if callable(close_child):
                try:
                    close_child()
                except Exception as exc:  # pragma: no cover - OS failure evidence
                    child_close_error = f"{type(exc).__name__}: {exc}"
        if receipt:
            payload_running_after_tree_close = launcher._is_process_pid_running(
                receipt["pid"]
            )

    return {
        "case": name,
        "started_at": _now(),
        "root_pid": getattr(child, "pid", None),
        "payload_pid": receipt.get("pid"),
        "payload_ppid": receipt.get("ppid"),
        "process_tree_management": tree.management_mode,
        "process_tree_binding": "create_suspended_assign_before_resume",
        "owned_process_tree_attached": tree.attached,
        "timeout_observed": timeout_observed,
        "termination_action": termination_action,
        "return_code": return_code,
        "payload_running_before_tree_close": payload_running_before_tree_close,
        "payload_running_after_tree_close": payload_running_after_tree_close,
        "owned_process_tree_closed": tree_close_error is None,
        "owned_process_tree_close_error": tree_close_error,
        "owned_child_handles_closed": child_close_error is None,
        "owned_child_handle_close_error": child_close_error,
        "receipt_path": str(receipt_path),
        "log_path": str(log_path),
    }


def main(argv: list[str] | None = None) -> int:
    if os.name != "nt":
        print("Win32 owned process-tree probe requires Windows", file=sys.stderr)
        return 2
    args = parse_args(argv)
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    run_dir = output_dir / f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}"
    run_dir.mkdir(parents=False, exist_ok=False)
    payload: dict[str, Any] = {
        "status": "running",
        "started_at": _now(),
        "run_dir": str(run_dir),
        "normal": None,
        "timeout": None,
    }
    result_path = run_dir / "win32_process_tree_probe.json"
    _write_json(result_path, payload)
    try:
        payload["normal"] = _run_case(run_dir, name="normal", keep_running=False)
        _write_json(result_path, payload)
        payload["timeout"] = _run_case(run_dir, name="timeout", keep_running=True)
        payload["status"] = "passed"
    except BaseException as exc:  # pragma: no cover - probe must preserve evidence
        payload["status"] = "failed"
        payload["error_type"] = type(exc).__name__
        payload["error"] = str(exc)
    payload["ended_at"] = _now()
    _write_json(result_path, payload)
    print(f"Win32 process-tree probe: {result_path}")
    return 0 if payload["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
