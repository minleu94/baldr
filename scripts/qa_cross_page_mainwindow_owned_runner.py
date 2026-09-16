"""以既有 Win32 owned process-tree runner 執行 bounded cross-page QA。

此 runner 只負責啟動既有的 writer/readback pytest 與 busy-close script，
重用 ``qa_run_research_journey_qt_subprocess`` 的 suspended CreateProcess →
Job Object 綁定。每個 case 都保存實際 child return code、timeout、root PID、
tree binding／close 狀態與 child stdout log；不使用全域 taskkill，也不碰正式資料。
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any
from uuid import uuid4

# Executing ``python scripts/<file>.py`` puts ``scripts`` (rather than the
# repository root) first on sys.path; make the existing package import explicit.
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts import qa_run_research_journey_qt_subprocess as owned_runner


DEFAULT_TIMEOUT_SECONDS = 90.0
DEFAULT_TERMINATE_GRACE_SECONDS = 5.0


def _now() -> str:
    return datetime.now().astimezone().isoformat()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _run_case(
    *,
    repo_root: Path,
    run_dir: Path,
    name: str,
    command: list[str],
    environment: dict[str, str],
    timeout_seconds: float,
    terminate_grace_seconds: float,
) -> dict[str, Any]:
    case_dir = run_dir / name
    case_dir.mkdir(parents=False, exist_ok=False)
    process_path = case_dir / "process.json"
    stdout_path = case_dir / "stdout.log"
    tree = owned_runner._OwnedProcessTree()
    child: Any = None
    root_pid: int | None = None
    return_code: int | None = None
    timed_out = False
    termination_action: str | None = None
    error: str | None = None
    tree_close_error: str | None = None
    child_close_error: str | None = None
    root_running_after_tree_close: bool | None = None
    started_at = _now()
    metadata: dict[str, Any] = {
        "schema_version": "cross-page-owned-runner.v1",
        "status": "starting",
        "case": name,
        "runner_pid": os.getpid(),
        "cwd": str(repo_root),
        "command": command,
        "started_at": started_at,
        "ended_at": None,
        "return_code": None,
        "timeout_seconds": timeout_seconds,
        "terminate_grace_seconds": terminate_grace_seconds,
        "timed_out": False,
        "termination_scope": (
            "owned_windows_job_object_process_tree"
            if os.name == "nt"
            else "owned_posix_process_group_rooted_at_runner_pid"
        ),
        "process_tree_binding": (
            "create_suspended_assign_before_resume"
            if os.name == "nt"
            else "process_group_created_before_child_execution"
        ),
        "process_tree_management": tree.management_mode,
        "owned_process_tree_attached": False,
        "owned_process_tree_closed": False,
        "root_pid": None,
        "root_running_after_tree_close": None,
        "stdout_path": str(stdout_path),
        "process_json_path": str(process_path),
    }
    _write_json(process_path, metadata)

    try:
        with stdout_path.open("wb") as log_handle:
            child = owned_runner._spawn_owned_child(
                command,
                cwd=repo_root,
                env=environment,
                log_handle=log_handle,
                owned_process_tree=tree,
            )
            root_pid = int(child.pid)
            metadata.update(
                {
                    "status": "running",
                    "root_pid": root_pid,
                    "process_tree_management": tree.management_mode,
                    "owned_process_tree_attached": tree.attached,
                }
            )
            _write_json(process_path, metadata)
            try:
                return_code = child.wait(timeout=timeout_seconds)
            except subprocess.TimeoutExpired:
                timed_out = True
                metadata.update(
                    {
                        "status": "timeout_terminating_owned_tree",
                        "timed_out": True,
                        "termination_requested_at": _now(),
                    }
                )
                _write_json(process_path, metadata)
                return_code, termination_action = owned_runner._terminate_owned_child(
                    child,
                    terminate_grace_seconds,
                )
    except BaseException as exc:  # noqa: BLE001 - preserve process evidence
        error = f"{type(exc).__name__}: {exc}"
    finally:
        if child is not None and return_code is None:
            return_code = child.poll()
        if child is not None and return_code is None:
            try:
                return_code, termination_action = owned_runner._terminate_owned_child(
                    child,
                    terminate_grace_seconds,
                )
            except BaseException as exc:  # noqa: BLE001 - preserve cleanup evidence
                if error is None:
                    error = f"cleanup {type(exc).__name__}: {exc}"

        try:
            tree.close()
        except BaseException as exc:  # noqa: BLE001 - preserve cleanup evidence
            tree_close_error = f"{type(exc).__name__}: {exc}"
            if error is None:
                error = f"owned tree close {tree_close_error}"

        if child is not None:
            close_child = getattr(child, "close", None)
            if callable(close_child):
                try:
                    close_child()
                except BaseException as exc:  # noqa: BLE001 - preserve evidence
                    child_close_error = f"{type(exc).__name__}: {exc}"
                    if error is None:
                        error = f"child handle close {child_close_error}"

        if root_pid is not None:
            root_running_after_tree_close = owned_runner._is_process_pid_running(root_pid)

        ended_at = _now()
        passed = (
            error is None
            and return_code == 0
            and not timed_out
            and tree_close_error is None
            and child_close_error is None
            and root_running_after_tree_close is not True
        )
        metadata.update(
            {
                "status": "passed" if passed else "failed",
                "ended_at": ended_at,
                "return_code": return_code,
                "timed_out": timed_out,
                "termination_action": termination_action,
                "error": error,
                "owned_process_tree_closed": tree_close_error is None,
                "owned_process_tree_close_error": tree_close_error,
                "owned_child_handles_closed": child_close_error is None,
                "owned_child_handle_close_error": child_close_error,
                "root_running_after_tree_close": root_running_after_tree_close,
            }
        )
        _write_json(process_path, metadata)

    return metadata


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="bounded cross-page MainWindow owned process-tree QA"
    )
    parser.add_argument(
        "--output-root",
        required=True,
        help="isolated root for process.json and stdout logs",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
    )
    parser.add_argument(
        "--terminate-grace-seconds",
        type=float,
        default=DEFAULT_TERMINATE_GRACE_SECONDS,
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if os.name != "nt":
        print("bounded owned process-tree QA requires Windows", file=sys.stderr)
        return 2
    if args.timeout_seconds <= 0 or args.terminate_grace_seconds < 0:
        raise ValueError("timeout must be positive and grace must be non-negative")

    repo_root = Path(__file__).resolve().parents[1]
    output_root = Path(args.output_root).expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    run_dir = output_root / (
        f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}"
    )
    run_dir.mkdir(parents=False, exist_ok=False)

    base_environment = os.environ.copy()
    base_environment.update(
        {
            "QT_QPA_PLATFORM": "offscreen",
            "PYTHONIOENCODING": "utf-8",
        }
    )
    readback_environment = dict(base_environment)
    readback_environment["CROSS_PAGE_READBACK_RECEIPT_PATH"] = str(
        run_dir / "readback_receipt.json"
    )
    readback_command = [
        sys.executable,
        "-u",
        "-m",
        "pytest",
        "tests\\test_cross_page_decision_journey_mainwindow.py::test_actual_mainwindow_cross_page_decision_journey_round_trip",
        "-q",
        "-o",
        "addopts=",
        "--tb=short",
    ]
    busy_command = [
        sys.executable,
        "-u",
        "scripts\\qa_cross_page_mainwindow_busy_close.py",
        "--data-root",
        str(run_dir / "busy_data"),
        "--output-root",
        str(run_dir / "busy_output"),
        "--receipt",
        str(run_dir / "busy_receipt.json"),
    ]

    summary_path = run_dir / "processes.json"
    summary: dict[str, Any] = {
        "schema_version": "cross-page-owned-runner-summary.v1",
        "status": "running",
        "runner_pid": os.getpid(),
        "cwd": str(repo_root),
        "run_dir": str(run_dir),
        "started_at": _now(),
        "cases": {},
    }
    _write_json(summary_path, summary)

    for name, command, environment in (
        ("readback_writer_reader", readback_command, readback_environment),
        ("busy_close", busy_command, base_environment),
    ):
        case = _run_case(
            repo_root=repo_root,
            run_dir=run_dir,
            name=name,
            command=command,
            environment=environment,
            timeout_seconds=args.timeout_seconds,
            terminate_grace_seconds=args.terminate_grace_seconds,
        )
        summary["cases"][name] = case
        _write_json(summary_path, summary)

    all_passed = all(case.get("status") == "passed" for case in summary["cases"].values())
    summary.update(
        {
            "status": "passed" if all_passed else "failed",
            "ended_at": _now(),
            "processes_json": str(summary_path),
        }
    )
    _write_json(summary_path, summary)
    print(f"bounded owned runner status={summary['status']} processes.json={summary_path}")
    for name, case in summary["cases"].items():
        print(
            f"case={name} status={case.get('status')} "
            f"return_code={case.get('return_code')} timed_out={case.get('timed_out')} "
            f"root_pid={case.get('root_pid')} "
            f"root_running_after_tree_close={case.get('root_running_after_tree_close')} "
            f"stdout={case.get('stdout_path')} process_json={case.get('process_json_path')}"
        )
    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
