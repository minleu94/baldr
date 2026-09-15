"""以單一受控子程序執行跨頁研究旅程 Qt QA。

此 launcher 本身不載入 Qt。它只負責：

* 以 process-local 環境啟動一個 QA child；
* 將 stdout/stderr 與 faulthandler 輸出寫入同一份 log；
* 保存 launcher root（Windows venv redirector）、child 回報的 payload PID、
  開始／結束時間、timeout、真正退出碼；
* 以檔案鎖保證同一時間只有一個此類 Qt child；
* Windows 以 process-local Job Object 持有自己的 process tree；timeout 時只
  停止該 tree，不碰其他 Python、WER 或 registry。

遇到 native crash 時不重試；child 的非零退出碼會原樣回傳，讓 crash 不會
被「抑制錯誤對話框」掩蓋。
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import math
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, IO
from uuid import uuid4


DEFAULT_TIMEOUT_SECONDS = 120.0
DEFAULT_TERMINATE_GRACE_SECONDS = 5.0
DEFAULT_TIMEOUT_EXIT_CODE = 124


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="單一受控子程序的隔離 offscreen MainWindow 研究旅程 QA"
    )
    parser.add_argument(
        "--output-dir",
        default=str(Path("output") / "qa" / "research_journey_qt_controlled"),
        help="隔離 evidence 根目錄；child 會在其中建立 summary.json 與 run 子目錄",
    )
    parser.add_argument(
        "--mode",
        choices=(
            "task_worker_lifecycle",
            "journey",
            "mainwindow_shutdown",
            "continuity_readback",
        ),
        default="task_worker_lifecycle",
        help=(
            "QA 模式；預設先執行最小 worker lifecycle，完整旅程需明確指定 journey；"
            "另有 MainWindow 關閉與跨 child continuity readback"
        ),
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help="child 最長執行秒數；超時只終止此 launcher 建立的 child",
    )
    parser.add_argument(
        "--terminate-grace-seconds",
        type=float,
        default=DEFAULT_TERMINATE_GRACE_SECONDS,
        help="timeout 後等待 child 結束的寬限秒數",
    )
    parser.add_argument(
        "--lock-path",
        default=None,
        help="跨 launcher 共用的 process lock；預設位於 output-dir 上層",
    )
    parser.add_argument(
        "--shared-root",
        default=None,
        help="傳給 child 的共用隔離 DATA_ROOT／OUTPUT_ROOT（跨 child continuity QA）",
    )
    return parser.parse_args(argv)


def _configure_console_streams() -> None:
    """讓 launcher 的中文 help／錯誤訊息不受 Windows code page 影響。"""

    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if not callable(reconfigure):
            continue
        try:
            reconfigure(encoding="utf-8", errors="backslashreplace")
        except (OSError, ValueError):
            continue


def _now() -> str:
    return datetime.now().astimezone().isoformat()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _find_child_process_metadata_path(run_dir: Path) -> Path | None:
    """Find the child PID receipt whether it is root-level or nested.

    The child creates its own evidence ``run_*`` directory so that a single
    launcher run can keep a stable outer summary.  Older child revisions wrote
    ``child_process.json`` only in that nested directory; accepting both
    locations keeps the launcher contract backward-compatible while still
    making the payload PID available for cleanup proof.
    """

    root_candidate = run_dir / "child_process.json"
    if root_candidate.is_file():
        return root_candidate
    nested_candidates = sorted(
        run_dir.glob("run_*/child_process.json"),
        key=lambda path: path.stat().st_mtime_ns,
        reverse=True,
    )
    return nested_candidates[0] if nested_candidates else None


class _SingleQtProcessLock:
    """以 process-held file lock 防止同類 Qt runner 並行。"""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._handle: IO[str] | None = None

    def __enter__(self) -> "_SingleQtProcessLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("a+", encoding="ascii")
        handle.seek(0)
        if not handle.read(1):
            handle.seek(0)
            handle.write("0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(  # type: ignore[attr-defined]
                    handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB  # type: ignore[attr-defined]
                )
        except (OSError, BlockingIOError) as exc:
            handle.close()
            raise RuntimeError(f"已有另一個研究旅程 Qt runner：{self.path}") from exc
        self._handle = handle
        return self

    def __exit__(self, _exc_type: Any, _exc: Any, _tb: Any) -> None:
        handle = self._handle
        self._handle = None
        if handle is None:
            return
        try:
            if os.name == "nt":
                import msvcrt

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)  # type: ignore[attr-defined]
        finally:
            handle.close()


class _OwnedProcessTree:
    """只管理 launcher 建立的 process tree。

    Windows venv 的 ``python.exe`` 可能是 redirector，Popen PID 不一定等於
    實際 Python payload PID。這個 Job Object 必須由
    :class:`_WindowsOwnedProcess` 在 ``CREATE_SUSPENDED`` 建立後、
    ``ResumeThread`` 前完成 process assignment；如此 redirector 後續啟動的
    payload 才會在同一棵受控 tree 內。``KILL_ON_JOB_CLOSE`` 只作用於這個
    runner 自己建立的 Job Object，不改 WER 或 registry。
    """

    def __init__(self) -> None:
        self.attached = False
        self.management_mode = "owned_popen_pid"
        self._job_handle: Any = None
        self._kernel32: Any = None
        if os.name != "nt":
            return

        import ctypes

        class _BasicLimitInformation(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_longlong),
                ("PerJobUserTimeLimit", ctypes.c_longlong),
                ("LimitFlags", ctypes.c_uint32),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", ctypes.c_uint32),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", ctypes.c_uint32),
                ("SchedulingClass", ctypes.c_uint32),
            ]

        class _IoCounters(ctypes.Structure):
            _fields_ = [
                ("ReadOperationCount", ctypes.c_uint64),
                ("WriteOperationCount", ctypes.c_uint64),
                ("OtherOperationCount", ctypes.c_uint64),
                ("ReadTransferCount", ctypes.c_uint64),
                ("WriteTransferCount", ctypes.c_uint64),
                ("OtherTransferCount", ctypes.c_uint64),
            ]

        class _ExtendedLimitInformation(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", _BasicLimitInformation),
                ("IoInfo", _IoCounters),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]
        kernel32.CreateJobObjectW.restype = ctypes.c_void_p
        kernel32.SetInformationJobObject.argtypes = [
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_void_p,
            ctypes.c_uint32,
        ]
        kernel32.SetInformationJobObject.restype = ctypes.c_int
        kernel32.AssignProcessToJobObject.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
        ]
        kernel32.AssignProcessToJobObject.restype = ctypes.c_int
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel32.CloseHandle.restype = ctypes.c_int

        job_handle = kernel32.CreateJobObjectW(None, None)
        if not job_handle:
            error_code = ctypes.get_last_error()
            raise OSError(error_code, "CreateJobObjectW failed")
        self._kernel32 = kernel32
        self._job_handle = job_handle
        information = _ExtendedLimitInformation()
        information.BasicLimitInformation.LimitFlags = 0x2000  # KILL_ON_JOB_CLOSE
        configured = kernel32.SetInformationJobObject(
            job_handle,
            9,  # JobObjectExtendedLimitInformation
            ctypes.byref(information),
            ctypes.sizeof(information),
        )
        if not configured:
            error_code = ctypes.get_last_error()
            kernel32.CloseHandle(job_handle)
            self._job_handle = None
            raise OSError(error_code, "SetInformationJobObject failed")
        self.management_mode = "windows_job_object_kill_on_close"

    def attach_suspended(self, process_handle: Any) -> None:
        """在 child 尚未執行第一個 user instruction 前加入 Job Object。"""

        if os.name != "nt":
            self.attached = True
            return
        if self._job_handle is None or self._kernel32 is None:
            raise RuntimeError("Windows job object 尚未建立")
        assigned = self._kernel32.AssignProcessToJobObject(
            self._job_handle,
            process_handle,
        )
        if not assigned:
            import ctypes

            error_code = ctypes.get_last_error()
            raise OSError(error_code, "AssignProcessToJobObject failed")
        self.attached = True

    def mark_attached(self) -> None:
        """標記非 Windows fallback 已交給 launcher 的 child。"""

        self.attached = True

    def close(self) -> None:
        if self._job_handle is None or self._kernel32 is None:
            return
        handle = self._job_handle
        if not self._kernel32.CloseHandle(handle):
            import ctypes

            error_code = ctypes.get_last_error()
            raise OSError(error_code, "CloseHandle(job) failed")
        self._job_handle = None


class _WindowsOwnedProcess:
    """以 suspended Win32 process + Job Object 啟動受控 child。

    ``subprocess.Popen`` 會在內部立即關閉 primary thread handle，因此無法
    讓呼叫端可靠地在 ``ResumeThread`` 前完成 Job assignment。本 wrapper
    直接使用同一個 stdlib Win32 API，保留真正的 process/thread handle，並
    明確執行：CreateProcess(CREATE_SUSPENDED) → AssignProcessToJobObject →
    ResumeThread。
    """

    def __init__(
        self,
        *,
        process_handle: Any,
        thread_handle: Any,
        pid: int,
        command: list[str],
    ) -> None:
        self._handle = process_handle
        self._thread_handle = thread_handle
        self.pid = pid
        self.args = command
        self.returncode: int | None = None
        self._closed = False

    @classmethod
    def create(
        cls,
        command: list[str],
        *,
        cwd: Path,
        env: dict[str, str],
        log_handle: IO[bytes],
        owned_process_tree: _OwnedProcessTree,
    ) -> "_WindowsOwnedProcess":
        if os.name != "nt":
            raise RuntimeError("_WindowsOwnedProcess 只能在 Windows 使用")

        import _winapi
        import msvcrt

        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= _winapi.STARTF_USESTDHANDLES

        # Use a dedicated inheritable NUL stdin and a duplicated log handle.
        # The handle list prevents unrelated inheritable handles from leaking
        # into this process tree.
        with open(os.devnull, "rb") as null_handle:
            source_handles = (
                msvcrt.get_osfhandle(null_handle.fileno()),
                msvcrt.get_osfhandle(log_handle.fileno()),
            )
            inherited_handles: list[int] = []
            process_handle: Any = None
            thread_handle: Any = None
            try:
                current_process = _winapi.GetCurrentProcess()
                for source_handle in source_handles:
                    inherited_handles.append(
                        int(
                            _winapi.DuplicateHandle(
                                current_process,
                                source_handle,
                                current_process,
                                0,
                                True,
                                _winapi.DUPLICATE_SAME_ACCESS,
                            )
                        )
                    )
                startupinfo.hStdInput = inherited_handles[0]
                startupinfo.hStdOutput = inherited_handles[1]
                startupinfo.hStdError = inherited_handles[1]
                startupinfo.lpAttributeList = {
                    "handle_list": list(dict.fromkeys(inherited_handles))
                }
                if hasattr(_winapi, "STARTF_USESHOWWINDOW"):
                    startupinfo.dwFlags |= _winapi.STARTF_USESHOWWINDOW
                    startupinfo.wShowWindow = getattr(_winapi, "SW_HIDE", 0)

                executable = os.fsdecode(command[0])
                command_line = subprocess.list2cmdline(
                    [os.fsdecode(argument) for argument in command]
                )
                creation_flags = (
                    getattr(_winapi, "CREATE_SUSPENDED", 0x00000004)
                    | getattr(
                        subprocess,
                        "CREATE_NEW_PROCESS_GROUP",
                        getattr(_winapi, "CREATE_NEW_PROCESS_GROUP", 0),
                    )
                    | getattr(
                        subprocess,
                        "CREATE_NO_WINDOW",
                        getattr(_winapi, "CREATE_NO_WINDOW", 0),
                    )
                )
                process_handle, thread_handle, pid, _tid = _winapi.CreateProcess(
                    executable,
                    command_line,
                    None,
                    None,
                    True,
                    creation_flags,
                    env,
                    os.fsdecode(cwd),
                    startupinfo,
                )

                # This is the critical ordering guarantee. The redirector has
                # not been resumed, so it cannot have spawned payload yet.
                owned_process_tree.attach_suspended(process_handle)
                _resume_windows_thread(thread_handle)
                return cls(
                    process_handle=process_handle,
                    thread_handle=thread_handle,
                    pid=int(pid),
                    command=command,
                )
            except BaseException:
                if process_handle is not None:
                    try:
                        _winapi.TerminateProcess(process_handle, 1)
                    except (OSError, PermissionError):
                        pass
                if thread_handle is not None:
                    try:
                        _winapi.CloseHandle(thread_handle)
                    except OSError:
                        pass
                if process_handle is not None:
                    try:
                        _winapi.CloseHandle(process_handle)
                    except OSError:
                        pass
                raise
            finally:
                for handle in inherited_handles:
                    try:
                        _winapi.CloseHandle(handle)
                    except OSError:
                        pass

    def poll(self) -> int | None:
        if self.returncode is not None:
            return self.returncode
        import _winapi

        if _winapi.WaitForSingleObject(self._handle, 0) == _winapi.WAIT_OBJECT_0:
            self.returncode = _winapi.GetExitCodeProcess(self._handle)
        return self.returncode

    def wait(self, timeout: float | None = None) -> int:
        if self.returncode is not None:
            return self.returncode
        import _winapi

        if timeout is None:
            timeout_milliseconds = _winapi.INFINITE
        elif timeout <= 0:
            timeout_milliseconds = 0
        else:
            timeout_milliseconds = int(timeout * 1000)
        result = _winapi.WaitForSingleObject(
            self._handle,
            timeout_milliseconds,
        )
        if result == _winapi.WAIT_TIMEOUT:
            assert timeout is not None
            raise subprocess.TimeoutExpired(self.args, timeout)
        if result != _winapi.WAIT_OBJECT_0:
            raise OSError(f"WaitForSingleObject failed: result={result}")
        self.returncode = _winapi.GetExitCodeProcess(self._handle)
        return self.returncode

    def terminate(self) -> None:
        if self.returncode is not None:
            return
        import _winapi

        try:
            _winapi.TerminateProcess(self._handle, 1)
        except PermissionError:
            result = _winapi.GetExitCodeProcess(self._handle)
            if result == _winapi.STILL_ACTIVE:
                raise
            self.returncode = result

    kill = terminate

    def close(self) -> None:
        if self._closed:
            return
        import _winapi

        errors: list[BaseException] = []
        for attribute in ("_thread_handle", "_handle"):
            handle = getattr(self, attribute)
            if handle is None:
                continue
            try:
                _winapi.CloseHandle(handle)
            except BaseException as exc:  # pragma: no cover - OS failure path
                errors.append(exc)
            else:
                setattr(self, attribute, None)
        if errors:
            raise RuntimeError(
                "無法關閉 Windows child handle："
                + "; ".join(f"{type(error).__name__}: {error}" for error in errors)
            ) from errors[0]
        self._closed = True


def _resume_windows_thread(thread_handle: Any) -> None:
    """呼叫 Python 3.11 未公開於 ``_winapi`` 的 ResumeThread API。"""

    if os.name != "nt":
        raise RuntimeError("ResumeThread 只能在 Windows 使用")
    import ctypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.ResumeThread.argtypes = [ctypes.c_void_p]
    kernel32.ResumeThread.restype = ctypes.c_uint32
    result = kernel32.ResumeThread(thread_handle)
    if result == 0xFFFFFFFF:
        error_code = ctypes.get_last_error()
        raise OSError(error_code, "ResumeThread failed")


def _spawn_owned_child(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    log_handle: IO[bytes],
    owned_process_tree: _OwnedProcessTree,
) -> Any:
    """啟動 child，Windows 綁定 tree 的時間點早於任何 payload 執行。"""

    if os.name == "nt":
        return _WindowsOwnedProcess.create(
            command,
            cwd=cwd,
            env=env,
            log_handle=log_handle,
            owned_process_tree=owned_process_tree,
        )

    child = subprocess.Popen(
        command,
        cwd=cwd,
        env=env,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    owned_process_tree.mark_attached()
    return child


def _is_process_pid_running(pid: int) -> bool | None:
    """查詢 PID 是否仍活著；``None`` 表示 OS 無法可靠判定。"""

    if pid <= 0:
        return None
    if os.name != "nt":
        return None

    import ctypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]
    kernel32.GetExitCodeProcess.restype = ctypes.c_int
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel32.CloseHandle.restype = ctypes.c_int
    handle = kernel32.OpenProcess(0x1000, 0, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        error_code = ctypes.get_last_error()
        if error_code == 87:  # ERROR_INVALID_PARAMETER: process no longer exists
            return False
        return None
    try:
        exit_code = ctypes.c_uint32()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            return None
        return int(exit_code.value) == 259  # STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)


def _build_command(
    repo_root: Path,
    output_dir: Path,
    mode: str,
    shared_root: Path | None = None,
) -> list[str]:
    child = repo_root / "scripts" / "qa_validate_research_journey_qt.py"
    command = [
        sys.executable,
        "-u",
        str(child),
        "--output-dir",
        str(output_dir),
        "--mode",
        mode,
    ]
    if shared_root is not None:
        command.extend(["--shared-root", str(shared_root)])
    return command


def _new_run_dir(output_root: Path) -> Path:
    for _ in range(5):
        candidate = output_root / (
            f"controlled_run_{datetime.now().strftime('%Y%m%d_%H%M%S')}_"
            f"{uuid4().hex[:8]}"
        )
        try:
            candidate.mkdir(parents=False, exist_ok=False)
        except FileExistsError:
            continue
        return candidate
    raise RuntimeError("無法建立唯一的受控 Qt runner run directory")


def _terminate_owned_child(
    child: Any,
    grace_seconds: float,
) -> tuple[int | None, str]:
    """有限地終止 launcher 自己建立的 child root，絕不觸碰其他 PID。

    呼叫端隨後會關閉 ``_OwnedProcessTree``；Windows Job Object 的 close
    會一併處理 venv redirector 之下仍可能存在的實際 payload。
    """

    existing = child.poll()
    if existing is not None:
        return existing, "already_exited"

    action = "terminate"
    child.terminate()
    try:
        return child.wait(timeout=grace_seconds), action
    except subprocess.TimeoutExpired:
        action = "kill"
        child.kill()
        try:
            return child.wait(timeout=max(grace_seconds, 1.0)), action
        except subprocess.TimeoutExpired:
            # TerminateProcess／kill normally makes this impossible on Windows;
            # keep the uncertain result explicit instead of blocking forever.
            return child.poll(), "kill_timeout"


def run(argv: list[str] | None = None) -> int:
    _configure_console_streams()
    args = parse_args(argv)
    if (
        not math.isfinite(args.timeout_seconds)
        or not math.isfinite(args.terminate_grace_seconds)
        or args.timeout_seconds <= 0
        or args.terminate_grace_seconds < 0
    ):
        raise ValueError("timeout 與 terminate grace 必須為有效秒數")

    repo_root = Path(__file__).resolve().parents[1]
    output_root = Path(args.output_dir).expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    lock_path = (
        Path(args.lock_path).expanduser().resolve()
        if args.lock_path
        else repo_root / "output" / "qa" / ".research_journey_qt.lock"
    )
    environment = os.environ.copy()
    environment.update(
        {
            "QT_QPA_PLATFORM": "offscreen",
            "PYTHONIOENCODING": "utf-8",
            "TECHNICAL_ANALYSIS_QA_CHILD": "1",
        }
    )
    # Let the existing crash_diagnostics session install faulthandler against
    # its persistent diagnostic file.  The child stderr still receives the
    # runner's bounded hang breadcrumb and is captured in runner.log.
    environment.pop("PYTHONFAULTHANDLER", None)

    with _SingleQtProcessLock(lock_path):
        run_dir = _new_run_dir(output_root)
        log_path = run_dir / "runner.log"
        metadata_path = run_dir / "process.json"
        shared_root = (
            Path(args.shared_root).expanduser().resolve()
            if args.shared_root
            else None
        )
        command = _build_command(repo_root, run_dir, args.mode, shared_root)
        started_at = _now()
        metadata: dict[str, Any] = {
            "status": "starting",
            "launcher_pid": os.getpid(),
            "runner_pid": None,
            "popen_pid": None,
            "redirector_pid": None,
            "reported_child_pid": None,
            "reported_child_ppid": None,
            "started_at": started_at,
            "ended_at": None,
            "exit_code": None,
            "timeout_seconds": args.timeout_seconds,
            "terminate_grace_seconds": args.terminate_grace_seconds,
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
            "process_tree_management": None,
            "owned_process_tree_attached": False,
            "owned_process_tree_closed": False,
            "automatic_retries": 0,
            "qt_process_concurrency": "one_child_per_lock",
            "lock_scope": "fixed_repo_qa_lock_or_explicit_lock_path",
            "mode": args.mode,
            "command": command,
            "output_root": str(output_root),
            "shared_root": str(shared_root) if shared_root is not None else None,
            "run_dir": str(run_dir),
            "child_process_metadata_path": str(run_dir / "child_process.json"),
            "log_path": str(log_path),
            "lock_path": str(lock_path),
            "error_dialog_suppression": {
                "requested_in_child": True,
                "scope": "child_process_only",
                "wer_registry_modified": False,
            },
        }
        _write_json(metadata_path, metadata)

        child: Any = None
        owned_process_tree: _OwnedProcessTree | None = None
        return_code: int | None = None
        launcher_error: str | None = None
        interrupted = False
        try:
            owned_process_tree = _OwnedProcessTree()
            metadata["process_tree_management"] = (
                owned_process_tree.management_mode
            )
            with log_path.open("wb") as log_handle:
                child = _spawn_owned_child(
                    command,
                    cwd=repo_root,
                    env=environment,
                    log_handle=log_handle,
                    owned_process_tree=owned_process_tree,
                )
                metadata["runner_pid"] = child.pid
                metadata["popen_pid"] = child.pid
                metadata["redirector_pid"] = child.pid
                metadata["termination_root_pid"] = child.pid
                metadata["owned_process_tree_attached"] = (
                    owned_process_tree.attached
                )
                metadata["status"] = "running"
                _write_json(metadata_path, metadata)
                try:
                    return_code = child.wait(timeout=args.timeout_seconds)
                except subprocess.TimeoutExpired:
                    metadata["timed_out"] = True
                    metadata["status"] = "timeout_terminating_child"
                    metadata["termination_requested_at"] = _now()
                    _write_json(metadata_path, metadata)
                    return_code, action = _terminate_owned_child(
                        child,
                        args.terminate_grace_seconds,
                    )
                    metadata["termination_action"] = action
        except KeyboardInterrupt:
            interrupted = True
            launcher_error = "KeyboardInterrupt"
        except Exception as exc:  # noqa: BLE001 - launcher must write evidence
            launcher_error = f"{type(exc).__name__}: {exc}"
        finally:
            # Covers metadata/logging failures after Popen, as well as an
            # interrupt.  The lock is not released until this bounded cleanup
            # has run, and cleanup is scoped to this exact Popen child.
            if child is not None and child.poll() is None:
                metadata["status"] = "launcher_error_terminating_child"
                metadata["termination_requested_at"] = _now()
                try:
                    cleanup_code, cleanup_action = _terminate_owned_child(
                        child,
                        args.terminate_grace_seconds,
                    )
                    metadata["cleanup_termination_action"] = cleanup_action
                    if return_code is None:
                        return_code = cleanup_code
                except Exception as cleanup_exc:  # noqa: BLE001 - preserve evidence
                    metadata["cleanup_error"] = (
                        f"{type(cleanup_exc).__name__}: {cleanup_exc}"
                    )
            if return_code is None and child is not None:
                return_code = child.poll()
            child_metadata_path = _find_child_process_metadata_path(run_dir)
            child_metadata = (
                _read_json(child_metadata_path)
                if child_metadata_path is not None
                else None
            )
            if child_metadata_path is not None:
                metadata["child_process_metadata_path"] = str(child_metadata_path)
            if child_metadata is not None:
                metadata["reported_child_pid"] = child_metadata.get("pid")
                metadata["reported_child_ppid"] = child_metadata.get("ppid")
                metadata["child_process_status"] = child_metadata.get("status")
            if owned_process_tree is not None:
                try:
                    owned_process_tree.close()
                    metadata["owned_process_tree_closed"] = True
                except Exception as tree_exc:  # noqa: BLE001 - preserve evidence
                    metadata["owned_process_tree_closed"] = False
                    metadata["owned_process_tree_close_error"] = (
                        f"{type(tree_exc).__name__}: {tree_exc}"
                    )
                    if launcher_error is None:
                        launcher_error = (
                            "owned process tree close failed: "
                            f"{type(tree_exc).__name__}: {tree_exc}"
                        )
            # The custom Windows process wrapper owns the actual process and
            # primary-thread handles. Close them after the Job Object so the
            # post-cleanup PID probe still has an independent query path.
            if child is not None:
                child_close = getattr(child, "close", None)
                if callable(child_close):
                    try:
                        child_close()
                        metadata["owned_child_handles_closed"] = True
                    except Exception as child_close_exc:  # noqa: BLE001
                        metadata["owned_child_handles_closed"] = False
                        metadata["owned_child_handle_close_error"] = (
                            f"{type(child_close_exc).__name__}: {child_close_exc}"
                        )
                        if launcher_error is None:
                            launcher_error = (
                                "owned child handle close failed: "
                                f"{type(child_close_exc).__name__}: {child_close_exc}"
                            )
            # Re-read after Job close: a normal child has already flushed its
            # startup metadata, while a timeout must provide an explicit PID
            # exit proof instead of only proving that the redirector exited.
            child_metadata_path = _find_child_process_metadata_path(run_dir)
            child_metadata = (
                _read_json(child_metadata_path)
                if child_metadata_path is not None
                else None
            )
            if child_metadata_path is not None:
                metadata["child_process_metadata_path"] = str(child_metadata_path)
            if child_metadata is not None:
                metadata["reported_child_pid"] = child_metadata.get("pid")
                metadata["reported_child_ppid"] = child_metadata.get("ppid")
                metadata["child_process_status"] = child_metadata.get("status")
            reported_child_pid = metadata.get("reported_child_pid")
            if isinstance(reported_child_pid, int):
                payload_running = _is_process_pid_running(reported_child_pid)
                metadata["reported_child_pid_running_after_tree_close"] = (
                    payload_running
                )
                metadata["reported_child_pid_exit_proof"] = (
                    "pid_not_running_after_tree_close"
                    if payload_running is False
                    else "pid_still_running_or_probe_unavailable"
                )
                if metadata["timed_out"] and payload_running is not False:
                    if launcher_error is None:
                        launcher_error = (
                            "timeout cleanup could not prove reported payload PID "
                            f"{reported_child_pid} exited"
                        )
            elif metadata["timed_out"] and launcher_error is None:
                launcher_error = (
                    "timeout cleanup could not read reported payload PID"
                )
            ended_at = _now()
            metadata["ended_at"] = ended_at
            metadata["exit_code"] = return_code
            if launcher_error is not None:
                metadata["status"] = "launcher_error"
                metadata["error"] = launcher_error
            elif metadata["timed_out"]:
                metadata["status"] = "timed_out"
            elif return_code == 0:
                metadata["status"] = "passed"
            else:
                metadata["status"] = "child_failed"
            try:
                _write_json(metadata_path, metadata)
            except Exception as metadata_exc:  # noqa: BLE001 - report to stderr
                if launcher_error is None:
                    launcher_error = (
                        f"{type(metadata_exc).__name__}: {metadata_exc}"
                    )

    if launcher_error is not None:
        print(f"受控 Qt runner 啟動失敗：{launcher_error}", file=sys.stderr)
        return 130 if interrupted else 1
    if metadata["timed_out"]:
        print(
            "受控 Qt runner timeout；只停止 runner child，詳見 "
            f"{metadata_path}",
            file=sys.stderr,
        )
        return DEFAULT_TIMEOUT_EXIT_CODE
    assert return_code is not None
    print(
        f"受控 Qt runner 結束：exit_code={return_code}，"
        f"process.json={metadata_path}，log={log_path}"
    )
    return return_code


if __name__ == "__main__":
    raise SystemExit(run())
