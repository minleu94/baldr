"""以全新 Python／MainWindow 從 Watchlist 重開真 F17 收藏。"""

from __future__ import annotations

import hashlib
import json
import os
import socket
import stat
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Mapping, cast
from uuid import uuid4

import pytest

if TYPE_CHECKING:
    from PySide6.QtWidgets import QApplication

from app_module.daily_market_technical_official_disposition_bookmark_v1 import (
    DailyMarketTechnicalOfficialDispositionBookmarkV1,
)
from app_module.personal_data_paths import to_internal_io_path
from test_daily_market_technical_official_disposition_bundle_v1 import bundle_fixture


_TOTAL_DEADLINE_SECONDS = 300.0
_CHILD_DEADLINE_SECONDS = 240.0
_QA_ROOT_RELATIVE = Path("output/qa/f17_full_browser_newpid_20261008_a")
_WATCHLIST_SIDECAR_SUFFIXES = ("-wal", "-shm", "-journal")
_CHILD_RUNTIME_ENVIRONMENT_KEYS = ("PATH", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT")

_ISOLATED_ENVIRONMENT_KEYS = (
    "ALL_PROXY",
    "APPDATA",
    "BALDR_CONFIG",
    "BALDR_ML_RESEARCH_STORAGE_CONFIG",
    "BANKTAIWAN_RECOMMENDATION_LEARNING_OUTPUT_ROOT",
    "DATA_FRESHNESS_STATUS_ARTIFACT",
    "DATA_ROOT",
    "DATA_UPDATE_HISTORY_ARTIFACT",
    "DATA_UPDATE_STATUS_ARTIFACT",
    "EVIDENCE_REHEARSAL_REPORT",
    "FINMIND_TOKEN",
    "FORMAL_DAILY_PORTFOLIO_CLOCK_MANIFEST",
    "FORMAL_DAILY_ROLLING_CALENDAR_BUNDLE",
    "FORMAL_DAILY_RUNTIME_CONFIG",
    "FORMAL_DAILY_RUNTIME_CONFIG_ROOT",
    "FORMAL_DAILY_RUNTIME_ENVIRONMENT_FILE",
    "FUNDAMENTAL_READ_SNAPSHOT_ROOT",
    "HOME",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "LOCALAPPDATA",
    "MONTHLY_REVENUE_AVAILABILITY_CANDIDATE",
    "MONTHLY_REVENUE_SNAPSHOT_CANDIDATE",
    "MPLCONFIGDIR",
    "OFFICIAL_CALENDAR_CACHE_PATH",
    "OUTPUT_ROOT",
    "PERSONAL_DATA_ROOT",
    "PERSONAL_H20_ACTIVATION_CONFIG",
    "PERSONAL_H20_SQLITE_READ_ROOT",
    "PERSONAL_JOURNAL_MODE",
    "PERSONAL_JOURNAL_ROOT",
    "PERSONAL_MODEL_POLICY_PATH",
    "PERSONAL_STORE_MODE",
    "PERSONAL_STORE_ROOT",
    "PERSONAL_WATCHLIST_SOURCE",
    "PIT_MARKET_SCOPE",
    "PIT_SECTOR_MEMBERSHIP_EXPECTED_CLASSIFICATION_VERSION",
    "PIT_SECTOR_MEMBERSHIP_PATH",
    "PIT_SECTOR_MEMBERSHIP_RAW_ROOT",
    "PIT_SECTOR_MEMBERSHIP_TAXONOMY_IDENTITY_PATH",
    "PIT_SECTOR_MEMBERSHIP_UNIVERSE_IDENTITY_PATH",
    "PIT_SECTOR_MEMBERSHIP_UNIVERSE_SYMBOLS_PATH",
    "PIT_SECTOR_MEMBERSHIP_CLOCK_MANIFEST_PATH",
    "P0_SOURCE_CONTROL_CENTER_AUDIT",
    "P0_SOURCE_CONTROL_CENTER_DECISIONS",
    "P0_SOURCE_CONTROL_CENTER_LICENSE_EVIDENCE",
    "PAPER_EQUAL_WEIGHT_BENCHMARK_PATH",
    "PAPER_TRADE_LEDGER_PATH",
    "PROFILE",
    "PROGRAM_READINESS_ARTIFACT",
    "PYTHONHOME",
    "PYTHONIOENCODING",
    "PYTHONPATH",
    "PYTHONUTF8",
    "PYTHONUSERBASE",
    "QT_PLUGIN_PATH",
    "QT_QPA_PLATFORM_PLUGIN_PATH",
    "QT_QPA_PLATFORM",
    "RECOMMENDATION_LEARNING_OUTPUT_ROOT",
    "RESEARCH_CONSOLE_PROJECTION",
    "RESEARCH_STATE_ROOT",
    "TECHNICAL_OFFICIAL_DISPOSITION_READ_ROOT",
    "TECHNICAL_UNIVERSE_READ_ROOT",
    "TEMP",
    "TMP",
    "TPEX_REFRESH_STATUS_ARTIFACT",
    "USERPROFILE",
    "WEEKLY_EVIDENCE_HISTORY_PROJECTION_PATH",
    "http_proxy",
    "https_proxy",
    "all_proxy",
)

_UNSET_CHILD_ENVIRONMENT_KEYS = (
    "ALL_PROXY",
    "FINMIND_TOKEN",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "PERSONAL_DATA_ROOT",
    "PERSONAL_JOURNAL_MODE",
    "PERSONAL_JOURNAL_ROOT",
    "PERSONAL_STORE_MODE",
    "PERSONAL_STORE_ROOT",
    "PERSONAL_WATCHLIST_SOURCE",
    "PYTHONHOME",
    "PYTHONPATH",
    "PYTHONUSERBASE",
    "all_proxy",
    "http_proxy",
    "https_proxy",
)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(to_internal_io_path(path), "rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _lstat_internal(path: Path) -> os.stat_result:
    return os.lstat(to_internal_io_path(path))


def _directory_child_paths(path: Path) -> list[Path]:
    try:
        with os.scandir(to_internal_io_path(path)) as entries:
            names = [entry.name for entry in entries]
    except OSError as exc:
        raise AssertionError(f"來源 inventory 無法列舉已存在目錄：{path}") from exc
    return [path / name for name in sorted(names, key=str.casefold)]


def _tree_inventory(root: Path) -> tuple[tuple[object, ...], ...]:
    """列出合成來源樹中的每個節點，檔案包含 SHA 與完整 stat。"""

    root = Path(root)
    try:
        _lstat_internal(root)
    except FileNotFoundError as exc:
        raise AssertionError(f"來源 inventory 根目錄缺失：{root}") from exc
    except OSError as exc:
        raise AssertionError(f"來源 inventory 根目錄無法 stat：{root}") from exc
    pending = [root]
    entries: list[tuple[object, ...]] = []
    while pending:
        current = pending.pop()
        try:
            info = _lstat_internal(current)
        except FileNotFoundError as exc:
            raise AssertionError(f"來源 inventory 掃描期間節點消失：{current}") from exc
        except OSError as exc:
            raise AssertionError(f"來源 inventory 節點無法 stat：{current}") from exc
        reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
        if stat.S_ISLNK(info.st_mode) or (
            reparse_flag and getattr(info, "st_file_attributes", 0) & reparse_flag
        ):
            raise AssertionError(f"來源 inventory 不接受 reparse/symlink：{current}")
        relative = "." if current == root else str(current.relative_to(root))
        common: tuple[object, ...] = (
            relative,
            "directory" if stat.S_ISDIR(info.st_mode) else "file",
            info.st_dev,
            info.st_ino,
            info.st_nlink,
            info.st_size,
            info.st_mtime_ns,
        )
        if stat.S_ISDIR(info.st_mode):
            entries.append((*common, ""))
            children = _directory_child_paths(current)
            pending.extend(reversed(children))
        elif stat.S_ISREG(info.st_mode):
            entries.append((*common, _sha256_file(current)))
        else:
            raise AssertionError(f"來源 inventory 遇到非一般檔案：{current}")
    return tuple(sorted(entries, key=lambda item: str(item[0]).casefold()))


def _source_roots(fixture: Any) -> tuple[Path, ...]:
    roots = (
        Path(fixture.database),
        Path(fixture.store_root),
        *(Path(root) for root in fixture.parent_roots),
        *(Path(root) for root in fixture.source_roots),
        Path(fixture.bundle_root),
    )
    unique: dict[str, Path] = {}
    for root in roots:
        resolved = root.resolve(strict=False)
        unique[str(resolved).casefold()] = resolved
    return tuple(unique[key] for key in sorted(unique))


def _source_inventory(roots: tuple[Path, ...]) -> tuple[tuple[str, tuple[tuple[object, ...], ...]], ...]:
    return tuple((str(root), _tree_inventory(root)) for root in roots)


def _watchlist_inventory(watchlist_root: Path) -> dict[str, object]:
    """主資料檔精確比 bytes；SQLite sidecar 僅保存生命週期觀測值。"""

    try:
        root_info = _lstat_internal(watchlist_root)
    except FileNotFoundError:
        return {"primary": [], "sidecars": []}
    except OSError as exc:
        raise AssertionError(f"Watchlist root 無法 stat：{watchlist_root}") from exc
    if not stat.S_ISDIR(root_info.st_mode):
        raise AssertionError(f"Watchlist root 必須是目錄：{watchlist_root}")
    primary: list[dict[str, object]] = []
    sidecars: list[dict[str, object]] = []
    pending = [watchlist_root]
    while pending:
        current = pending.pop()
        try:
            info = _lstat_internal(current)
        except FileNotFoundError as exc:
            raise AssertionError(f"Watchlist inventory 掃描期間節點消失：{current}") from exc
        except OSError as exc:
            raise AssertionError(f"Watchlist 節點無法 stat：{current}") from exc
        reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
        if stat.S_ISLNK(info.st_mode) or (
            reparse_flag and getattr(info, "st_file_attributes", 0) & reparse_flag
        ):
            raise AssertionError(f"Watchlist 隔離樹不接受 reparse/symlink：{current}")
        if stat.S_ISDIR(info.st_mode):
            pending.extend(reversed(_directory_child_paths(current)))
            continue
        if not stat.S_ISREG(info.st_mode):
            raise AssertionError(f"Watchlist 隔離樹出現非一般檔案：{current}")
        entry: dict[str, object] = {
            "relative_path": str(current.relative_to(watchlist_root)),
            "size": info.st_size,
            "mtime_ns": info.st_mtime_ns,
            "sha256": _sha256_file(current),
        }
        if current.name.endswith(_WATCHLIST_SIDECAR_SUFFIXES):
            sidecars.append(entry)
        else:
            primary.append(entry)
    return {"primary": primary, "sidecars": sidecars}


def _primary_watchlist_bytes(inventory: Mapping[str, object]) -> tuple[tuple[str, int, str], ...]:
    raw = inventory.get("primary")
    if not isinstance(raw, list):
        raise AssertionError("Watchlist persistent inventory 格式錯誤")
    normalized: list[tuple[str, int, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            raise AssertionError("Watchlist primary inventory 列格式錯誤")
        normalized.append(
            (
                str(item.get("relative_path", "")),
                int(item.get("size", -1)),
                str(item.get("sha256", "")),
            )
        )
    return tuple(normalized)


def _wait_for(
    app: QApplication,
    predicate: Callable[[], bool],
    *,
    deadline: float,
    stage: str,
    cancel_marker: Path | None = None,
) -> None:
    while not predicate():
        app.processEvents()
        if cancel_marker is not None and cancel_marker.exists():
            raise AssertionError(f"父程序要求 child 合作取消：{stage}")
        if time.monotonic() >= deadline:
            raise AssertionError(f"F17 全新程序旅程超過共同 deadline：{stage}")
        time.sleep(0.005)
    app.processEvents()
    if cancel_marker is not None and cancel_marker.exists():
        raise AssertionError(f"父程序要求 child 合作取消：{stage}")
    if time.monotonic() > deadline:
        raise AssertionError(f"F17 全新程序旅程在 deadline 後完成：{stage}")


def _check_cancel_marker(cancel_marker: Path) -> None:
    if cancel_marker.exists():
        raise AssertionError("父程序要求 child 合作取消；此旅程不算成功")


def _remaining_seconds(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise AssertionError("F17 全新程序 MainWindow 旅程已超過 300 秒總 deadline")
    return remaining


def _view_idle(view: Any) -> bool:
    active = getattr(view, "active_worker", None)
    if active is not None:
        return False
    has_running = getattr(view, "_has_running_worker", None)
    return not bool(has_running()) if callable(has_running) else True


def _click_table_row(
    app: QApplication,
    table: Any,
    row_index: int,
    *,
    deadline: float,
) -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    model = table.model()
    assert model is not None and 0 <= row_index < model.rowCount()
    index = model.index(row_index, 0)
    table.scrollTo(index)
    app.processEvents()
    rect = table.visualRect(index)
    assert rect.isValid() and rect.width() > 0 and rect.height() > 0
    assert time.monotonic() < deadline
    QTest.mouseClick(
        table.viewport(),
        Qt.MouseButton.LeftButton,
        pos=rect.center(),
    )
    app.processEvents()


def _watchlist_row_for_bookmark(watchlist: Any, stock_code: str) -> int:
    from PySide6.QtCore import Qt

    model = watchlist.stocks_table.model()
    assert model is not None
    matches: list[int] = []
    for row_index in range(model.rowCount()):
        row_text = " ".join(
            str(model.index(row_index, column).data(Qt.ItemDataRole.DisplayRole) or "")
            for column in range(model.columnCount())
        )
        if "已收藏官方市場／處置研究" in row_text and stock_code in row_text:
            matches.append(row_index)
    assert len(matches) == 1, "可見 Watchlist 表格必須只有一筆目標 F17 收藏列"
    return matches[0]


def _isolated_environment(
    *,
    root: Path,
    bundle_root: Path,
) -> tuple[dict[str, str], tuple[str, ...]]:
    data_root = root / "data"
    output_root = root / "output"
    research_state_root = root / "research-state"
    temporary_root = root / "temporary"
    appdata_root = root / "appdata"
    localappdata_root = root / "localappdata"
    ml_storage_root = root / "ml-research"
    technical_read_root = output_root / "research_snapshots" / "technical_universe"
    fundamental_copy_root = root / "fundamental-read-copy"
    h20_copy_root = root / "personal-h20-read-copy"
    for path in (
        data_root,
        output_root,
        research_state_root,
        temporary_root,
        appdata_root,
        localappdata_root,
        ml_storage_root,
        technical_read_root,
        fundamental_copy_root,
        h20_copy_root,
    ):
        path.mkdir(parents=True, exist_ok=True)
    ml_config = root / "ml-research-storage.json"
    ml_config.write_text(
        json.dumps(
            {"schema_version": "ml-research-storage.v1", "active_root": str(ml_storage_root)},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    env = {
        "APPDATA": str(appdata_root),
        "BALDR_CONFIG": str(root / "baldr-config.json"),
        "BALDR_ML_RESEARCH_STORAGE_CONFIG": str(ml_config),
        "BANKTAIWAN_RECOMMENDATION_LEARNING_OUTPUT_ROOT": str(
            research_state_root / "bank-taiwan-recommendation-learning"
        ),
        "DATA_ROOT": str(data_root),
        "FUNDAMENTAL_READ_SNAPSHOT_ROOT": str(fundamental_copy_root),
        "LOCALAPPDATA": str(localappdata_root),
        "MPLCONFIGDIR": str(output_root / "application_state" / "matplotlib"),
        "OFFICIAL_CALENDAR_CACHE_PATH": str(data_root / "official-calendar-cache.json"),
        "OUTPUT_ROOT": str(output_root),
        "PERSONAL_H20_ACTIVATION_CONFIG": str(
            data_root / "personal" / "recommendation_h20" / "activation.json"
        ),
        "PERSONAL_H20_SQLITE_READ_ROOT": str(h20_copy_root),
        "PERSONAL_MODEL_POLICY_PATH": str(research_state_root / "personal-use-policy.json"),
        "PROFILE": "prod",
        "QT_QPA_PLATFORM": "offscreen",
        "RECOMMENDATION_LEARNING_OUTPUT_ROOT": str(
            research_state_root / "recommendation-learning"
        ),
        "RESEARCH_STATE_ROOT": str(research_state_root),
        "TECHNICAL_OFFICIAL_DISPOSITION_READ_ROOT": str(bundle_root),
        "TECHNICAL_UNIVERSE_READ_ROOT": str(technical_read_root),
        "TEMP": str(temporary_root),
        "TMP": str(temporary_root),
        "USERPROFILE": str(root / "user-profile"),
        "HOME": str(root / "home"),
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
    }
    return env, _UNSET_CHILD_ENVIRONMENT_KEYS


def _minimal_child_environment(
    *,
    expected_env: Mapping[str, str],
) -> dict[str, str]:
    child_env = {
        name: value
        for name in _CHILD_RUNTIME_ENVIRONMENT_KEYS
        if (value := os.environ.get(name)) is not None
    }
    child_env.update(expected_env)
    child_env.pop("PYTHONHOME", None)
    child_env.pop("PYTHONPATH", None)
    child_env.pop("PYTHONUSERBASE", None)
    return child_env


def _validate_child_environment(
    actual_environment: Mapping[str, str],
    *,
    expected_environment: object,
    unset_environment_keys: object,
) -> dict[str, str]:
    if not isinstance(expected_environment, dict):
        raise AssertionError("child payload 缺少 expected_environment")
    validated_environment: dict[str, str] = {}
    for key, value in expected_environment.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise AssertionError("child expected_environment 只接受字串鍵值")
        if actual_environment.get(key) != value:
            raise AssertionError(f"child environment 不符：{key}")
        validated_environment[key] = value
    if not isinstance(unset_environment_keys, list) or not all(
        isinstance(key, str) for key in unset_environment_keys
    ):
        raise AssertionError("child payload 缺少明示 unset environment key 清單")
    for key in unset_environment_keys:
        if key in actual_environment:
            raise AssertionError(f"child environment 不應含敏感或來源變數：{key}")
    permitted_keys = set(validated_environment) | set(_CHILD_RUNTIME_ENVIRONMENT_KEYS)
    unexpected_keys = set(actual_environment) - permitted_keys
    if unexpected_keys:
        raise AssertionError(
            f"child environment 出現白名單外鍵值：{sorted(unexpected_keys)}"
        )
    return validated_environment


def _normalize_executable_path(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 4096:
        raise AssertionError(f"{label} 必須是有界執行檔路徑")
    if not os.path.isabs(value):
        raise AssertionError(f"{label} 必須是絕對路徑")
    return os.path.normcase(os.path.abspath(os.path.normpath(value)))


def _validate_child_pid_chain(
    *,
    reporter_pid: object,
    reporter_parent_pid: object,
    reporter_executable: object,
    launcher_pid: object,
    parent_pid: object,
    expected_executables: object,
) -> str:
    """只接受真直接子程序或單層 Windows venv launcher 關係。"""

    pid_fields = {
        "reporter_pid": reporter_pid,
        "reporter_parent_pid": reporter_parent_pid,
        "launcher_pid": launcher_pid,
        "parent_pid": parent_pid,
    }
    for name, value in pid_fields.items():
        if type(value) is not int or value <= 0:
            raise AssertionError(f"{name} 必須是正整數 PID")
    typed_reporter_pid = cast(int, reporter_pid)
    typed_reporter_parent_pid = cast(int, reporter_parent_pid)
    typed_launcher_pid = cast(int, launcher_pid)
    typed_parent_pid = cast(int, parent_pid)
    if typed_launcher_pid == typed_parent_pid:
        raise AssertionError("Popen launcher PID 不可等於測試父程序 PID")
    if typed_reporter_pid == typed_parent_pid:
        raise AssertionError("child reporter 必須是全新 PID")

    if typed_reporter_pid == typed_launcher_pid:
        if typed_reporter_parent_pid != typed_parent_pid:
            raise AssertionError("直接 child 的 OS parent PID 不符")
        relation = "direct"
    else:
        if typed_reporter_parent_pid != typed_launcher_pid:
            raise AssertionError("child reporter 不是 Popen launcher 的直接子程序")
        relation = "venv_redirector_child"

    if not isinstance(expected_executables, (tuple, list)) or not expected_executables:
        raise AssertionError("expected_executables 必須是非空路徑清單")
    allowed = {
        _normalize_executable_path(item, label="expected executable")
        for item in expected_executables
    }
    actual = _normalize_executable_path(
        reporter_executable,
        label="reporter executable",
    )
    if actual not in allowed:
        raise AssertionError("child reporter executable 不在明示 Python 執行檔清單")
    return relation


def _windows_kernel32() -> Any:
    import ctypes

    loader = getattr(ctypes, "WinDLL", None)
    if loader is None:
        raise AssertionError("Windows process containment 只支援 Windows")
    return loader("kernel32", use_last_error=True)


def _assign_suspended_process_to_kill_job(process: subprocess.Popen[str]) -> int:
    """把尚未執行的 Windows process 放進關閉即清理整棵子樹的 Job。"""

    if os.name != "nt":
        raise AssertionError("Windows Job Object 僅能在 Windows 使用")
    import ctypes
    from ctypes import wintypes

    kernel32 = _windows_kernel32()
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
    kernel32.SetInformationJobObject.restype = wintypes.BOOL
    kernel32.SetInformationJobObject.argtypes = [
        wintypes.HANDLE,
        wintypes.INT,
        wintypes.LPVOID,
        wintypes.DWORD,
    ]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel32.Thread32First.restype = wintypes.BOOL
    kernel32.Thread32Next.restype = wintypes.BOOL
    kernel32.OpenThread.restype = wintypes.HANDLE
    kernel32.OpenThread.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.ResumeThread.restype = wintypes.DWORD
    kernel32.ResumeThread.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.TerminateJobObject.restype = wintypes.BOOL
    kernel32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]

    class _BasicLimitInformation(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_longlong),
            ("PerJobUserTimeLimit", ctypes.c_longlong),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class _IoCounters(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_ulonglong),
            ("WriteOperationCount", ctypes.c_ulonglong),
            ("OtherOperationCount", ctypes.c_ulonglong),
            ("ReadTransferCount", ctypes.c_ulonglong),
            ("WriteTransferCount", ctypes.c_ulonglong),
            ("OtherTransferCount", ctypes.c_ulonglong),
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

    class _ThreadEntry32(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ThreadID", wintypes.DWORD),
            ("th32OwnerProcessID", wintypes.DWORD),
            ("tpBasePri", wintypes.LONG),
            ("tpDeltaPri", wintypes.LONG),
            ("dwFlags", wintypes.DWORD),
        ]

    kernel32.Thread32First.argtypes = [wintypes.HANDLE, ctypes.POINTER(_ThreadEntry32)]
    kernel32.Thread32Next.argtypes = [wintypes.HANDLE, ctypes.POINTER(_ThreadEntry32)]

    job_handle = kernel32.CreateJobObjectW(None, None)
    if not job_handle:
        raise OSError(ctypes.get_last_error(), "CreateJobObjectW 失敗")
    job_value = int(job_handle)
    process_handle: Any | None = None
    snapshot_handle: Any | None = None
    thread_handle: Any | None = None
    assigned = False
    try:
        limit = _ExtendedLimitInformation()
        limit.BasicLimitInformation.LimitFlags = 0x00002000  # 關閉 Job handle 時終止其內程序。
        if not kernel32.SetInformationJobObject(
            job_handle,
            9,  # JobObjectExtendedLimitInformation 擴充限制資訊類別。
            ctypes.byref(limit),
            ctypes.sizeof(limit),
        ):
            raise OSError(ctypes.get_last_error(), "SetInformationJobObject 失敗")

        process_handle = kernel32.OpenProcess(
            0x0001 | 0x0100 | 0x0400,  # TERMINATE、SET_QUOTA、QUERY_INFORMATION 權限。
            False,
            process.pid,
        )
        if not process_handle:
            raise OSError(ctypes.get_last_error(), "OpenProcess 失敗")
        if not kernel32.AssignProcessToJobObject(job_handle, process_handle):
            raise OSError(ctypes.get_last_error(), "AssignProcessToJobObject 失敗")
        assigned = True

        snapshot_handle = kernel32.CreateToolhelp32Snapshot(0x00000004, 0)
        invalid_handle = ctypes.c_void_p(-1).value
        if not snapshot_handle or int(snapshot_handle) == invalid_handle:
            raise OSError(ctypes.get_last_error(), "CreateToolhelp32Snapshot 失敗")
        entry = _ThreadEntry32()
        entry.dwSize = ctypes.sizeof(entry)
        thread_ids: list[int] = []
        has_entry = bool(kernel32.Thread32First(snapshot_handle, ctypes.byref(entry)))
        while has_entry:
            if int(entry.th32OwnerProcessID) == process.pid:
                thread_ids.append(int(entry.th32ThreadID))
            has_entry = bool(kernel32.Thread32Next(snapshot_handle, ctypes.byref(entry)))
        if len(thread_ids) != 1:
            raise AssertionError("suspended launcher 必須且只能有一條尚未啟動的主執行緒")

        thread_handle = kernel32.OpenThread(0x0002, False, thread_ids[0])  # THREAD_SUSPEND_RESUME 權限。
        if not thread_handle:
            raise OSError(ctypes.get_last_error(), "OpenThread 失敗")
        previous_suspend_count = int(kernel32.ResumeThread(thread_handle))
        if previous_suspend_count != 1:
            raise AssertionError("launcher 主執行緒的 suspend count 不符")
        return job_value
    except BaseException:
        if assigned:
            kernel32.TerminateJobObject(job_handle, 1)
        else:
            try:
                process.kill()
            except OSError:
                pass
        try:
            process.communicate(timeout=3.0)
        except subprocess.TimeoutExpired:
            pass
        kernel32.CloseHandle(job_handle)
        raise
    finally:
        for handle in (thread_handle, snapshot_handle, process_handle):
            if handle:
                kernel32.CloseHandle(handle)


def _close_process_job(job_handle: int | None) -> None:
    if job_handle is None:
        return
    kernel32 = _windows_kernel32()
    from ctypes import wintypes

    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    if not kernel32.CloseHandle(wintypes.HANDLE(job_handle)):
        import ctypes

        raise OSError(ctypes.get_last_error(), "CloseHandle(Job Object) 失敗")


def _terminate_process_tree(
    process: subprocess.Popen[str],
    *,
    job_handle: int | None,
) -> None:
    if os.name == "nt":
        if job_handle is None:
            raise AssertionError("Windows child 缺少 process Job Object，拒絕只殺 launcher")
        kernel32 = _windows_kernel32()
        from ctypes import wintypes
        import ctypes

        kernel32.TerminateJobObject.restype = wintypes.BOOL
        kernel32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
        if not kernel32.TerminateJobObject(wintypes.HANDLE(job_handle), 1):
            raise OSError(ctypes.get_last_error(), "TerminateJobObject 失敗")
        return
    kill_group = getattr(os, "killpg", None)
    terminate_signal = getattr(signal, "SIGTERM", None)
    if not callable(kill_group) or type(terminate_signal) is not int:
        raise AssertionError("目前平台不支援受控 process group 終止")
    try:
        kill_group(process.pid, terminate_signal)
    except ProcessLookupError:
        return


def _process_is_active(pid: int) -> bool:
    if type(pid) is not int or pid <= 0:
        raise AssertionError("PID 存活檢查只接受正整數")
    if os.name != "nt":
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True
    import ctypes
    from ctypes import wintypes

    kernel32 = _windows_kernel32()
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.GetExitCodeProcess.restype = wintypes.BOOL
    kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION 權限。
    if not handle:
        error_code = ctypes.get_last_error()
        if error_code == 87:  # ERROR_INVALID_PARAMETER: PID 已不在 process table
            return False
        raise OSError(error_code, "OpenProcess 存活檢查失敗")
    try:
        exit_code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            raise OSError(ctypes.get_last_error(), "GetExitCodeProcess 失敗")
        return int(exit_code.value) == 259  # STILL_ACTIVE 表示程序仍在執行。
    finally:
        kernel32.CloseHandle(handle)


def _spawn_child_process(
    command: list[str],
    *,
    cwd: str,
    env: Mapping[str, str],
) -> tuple[subprocess.Popen[str], int | None]:
    if os.name == "nt":
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=dict(env),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            creationflags=0x00000004 | 0x00000200,  # CREATE_SUSPENDED 與 NEW_PROCESS_GROUP。
        )
        try:
            job_handle = _assign_suspended_process_to_kill_job(process)
        except BaseException:
            if process.poll() is None:
                try:
                    process.kill()
                except OSError:
                    pass
            try:
                process.communicate(timeout=3.0)
            except subprocess.TimeoutExpired:
                pass
            raise
        return process, job_handle
    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=dict(env),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        start_new_session=True,
    )
    return process, None


def _stop_child_bounded(
    process: subprocess.Popen[str],
    *,
    job_handle: int | None,
    cancel_marker: Path,
    stdout_path: Path,
    stderr_path: Path,
    cooperative_wait_seconds: float = 5.0,
    terminate_wait_seconds: float = 2.0,
    final_wait_seconds: float = 3.0,
) -> tuple[str, str]:
    """先送合作取消，逾時時只收束本次 Job／process group。"""

    cancel_marker.write_text("cancel requested\n", encoding="utf-8")
    try:
        stdout, stderr = process.communicate(timeout=cooperative_wait_seconds)
    except subprocess.TimeoutExpired:
        _terminate_process_tree(process, job_handle=job_handle)
        try:
            stdout, stderr = process.communicate(timeout=terminate_wait_seconds)
        except subprocess.TimeoutExpired:
            if os.name == "nt":
                _terminate_process_tree(process, job_handle=job_handle)
            else:
                kill_group = getattr(os, "killpg", None)
                kill_signal = getattr(signal, "SIGKILL", None)
                if not callable(kill_group) or type(kill_signal) is not int:
                    raise AssertionError("目前平台不支援 process group 強制終止")
                try:
                    kill_group(process.pid, kill_signal)
                except ProcessLookupError:
                    pass
            try:
                stdout, stderr = process.communicate(timeout=final_wait_seconds)
            except subprocess.TimeoutExpired as exc:
                raise AssertionError(
                    "child process tree 在合作取消與有界 terminate 後仍未退出"
                ) from exc
    stdout_text = stdout or ""
    stderr_text = stderr or ""
    stdout_path.write_text(stdout_text, encoding="utf-8")
    stderr_path.write_text(stderr_text, encoding="utf-8")
    return stdout_text, stderr_text


def _install_network_deny(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    attempts: list[str] = []

    def deny(*args: object, **kwargs: object) -> int:
        target = str(args[1]) if len(args) > 1 else "unknown"
        attempts.append(target)
        raise AssertionError(f"F17 synthetic MainWindow 禁止 provider/network 連線：{target}")

    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket.socket, "connect_ex", deny)
    monkeypatch.setattr(socket, "create_connection", deny)
    return attempts


def _helper_source() -> str:
    """輸出只轉入測試模組 child 入口的 ignored launcher。"""

    return "\n".join(
        (
            "from __future__ import annotations",
            "import sys",
            "from pathlib import Path",
            "repo_root = Path(sys.argv[1]).resolve()",
            "payload_path = Path(sys.argv[2]).resolve()",
            "sys.path.insert(0, str(repo_root))",
            "sys.path.insert(0, str(repo_root / 'tests'))",
            "from test_ui_qt_technical_official_main_new_process import _child_main",
            "raise SystemExit(_child_main(payload_path))",
            "",
        )
    )


def _child_main(payload_path: Path) -> int:
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise AssertionError("child payload 必須是 JSON object")
    expected_environment = payload.get("expected_environment")
    unset_environment_keys = payload.get("unset_environment_keys")
    expected_env = _validate_child_environment(
        os.environ,
        expected_environment=expected_environment,
        unset_environment_keys=unset_environment_keys,
    )
    cancel_marker_path = Path(str(payload["cancel_marker_path"]))
    _check_cancel_marker(cancel_marker_path)

    network_attempts: list[str] = []

    def deny_network(*args: object, **kwargs: object) -> int:
        target = str(args[1]) if len(args) > 1 else "unknown"
        network_attempts.append(target)
        raise AssertionError(f"child synthetic MainWindow 禁止網路連線：{target}")

    setattr(socket.socket, "connect", deny_network)
    setattr(socket.socket, "connect_ex", deny_network)
    setattr(socket, "create_connection", deny_network)

    repo_root = Path(str(payload["repo_root"])).resolve()
    source_roots = tuple(Path(str(value)).resolve() for value in payload["source_roots"])
    source_before = _source_inventory(source_roots)
    output_root = Path(str(expected_env["OUTPUT_ROOT"])).resolve()
    watchlist_root = output_root / "watchlist"
    watchlist_before = _watchlist_inventory(watchlist_root)
    expected_primary = tuple(
        tuple(cast(tuple[str, int, str], item))
        for item in payload["watchlist_primary_bytes"]
    )
    if _primary_watchlist_bytes(watchlist_before) != expected_primary:
        raise AssertionError("child 啟動前 Watchlist 持久檔 bytes 已漂移")

    receipt_path = Path(str(payload["receipt_path"])).resolve()
    receipt: dict[str, object] = {
        "status": "in_progress",
        "pid": os.getpid(),
        "parent_pid": os.getppid(),
        "executable": _normalize_executable_path(sys.executable, label="child sys.executable"),
        "network_attempts": network_attempts,
        "source_inventory_before_sha256": hashlib.sha256(
            json.dumps(source_before, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest(),
    }
    window: Any | None = None
    app: Any | None = None
    deadline = time.monotonic() + min(
        _CHILD_DEADLINE_SECONDS,
        float(payload["remaining_total_seconds"]),
    )
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication, QDialog, QGroupBox, QPushButton

        from app_module.daily_market_technical_official_disposition_bookmark_v1 import (
            DailyMarketTechnicalOfficialDispositionBookmarkV1,
        )
        from ui_qt.main import MainWindow

        app = cast(QApplication, QApplication.instance() or QApplication([]))
        window = MainWindow()
        config = window.config
        assert Path(config.data_root).resolve() == Path(expected_env["DATA_ROOT"]).resolve()
        assert Path(config.output_root).resolve() == output_root
        assert Path(cast(str, config.technical_official_disposition_read_root)).resolve() == Path(
            expected_env["TECHNICAL_OFFICIAL_DISPOSITION_READ_ROOT"]
        ).resolve()
        assert config.personal_data_root is None
        assert config.personal_watchlist_source is None
        assert config.personal_journal_root is None
        assert config.personal_journal_mode is None
        assert config.personal_store_root is None
        assert config.personal_store_mode is None
        service = window.watchlist_service
        assert service is not None
        assert Path(service.default_watchlist_file).resolve().is_relative_to(output_root)
        assert Path(service.canonical_repository_path).resolve().is_relative_to(output_root)
        assert Path(service.watchlist_dir).resolve() == watchlist_root.resolve()
        watchlist = window.watchlist_view
        window.show()
        app.processEvents()

        routed_bookmarks: list[object] = []
        watchlist.technicalOfficialBookmarkReady.connect(routed_bookmarks.append)
        nav_button = window.left_navigation.button_for_key("watchlist")
        assert nav_button is not None and nav_button.isVisible()
        QTest.mouseClick(nav_button, Qt.MouseButton.LeftButton)
        assert window.left_navigation.current_key() == "watchlist"

        bookmark_id = str(payload["bookmark_id"])
        expected_bookmark_json = str(payload["bookmark_json"])
        persisted = service.get_research_bookmark(bookmark_id)
        assert type(persisted) is DailyMarketTechnicalOfficialDispositionBookmarkV1
        assert persisted.to_json() == expected_bookmark_json
        receipt["bookmark_identity_sha256"] = persisted.bookmark_identity_sha256

        model = watchlist.stocks_table.model()
        assert model is not None
        row_index = _watchlist_row_for_bookmark(
            watchlist,
            str(payload["selected_stock_code"]),
        )
        _click_table_row(app, watchlist.stocks_table, row_index, deadline=deadline)
        selection = watchlist.stocks_table.selectionModel()
        assert selection is not None and len(selection.selectedRows()) == 1
        assert watchlist.stock_analysis_btn.isEnabled()
        QTest.mouseClick(watchlist.stock_analysis_btn, Qt.MouseButton.LeftButton)
        _wait_for(
            app,
            lambda: len(routed_bookmarks) == 1,
            deadline=deadline,
            stage="Watchlist F17 typed bookmark signal",
            cancel_marker=cancel_marker_path,
        )
        assert type(routed_bookmarks[0]) is DailyMarketTechnicalOfficialDispositionBookmarkV1
        assert routed_bookmarks[0].bookmark_id == bookmark_id

        view = window.technical_official_research_view
        expected_query = str(payload["query_identity_sha256"])
        expected_selected = str(payload["selected_stock_code"])
        expected_codes = tuple(str(value) for value in payload["comparison_stock_codes"])
        expected_pages = tuple(int(value) for value in payload["comparison_page_indices"])

        def restored_exactly() -> bool:
            result = view.current_result
            request = view.current_request
            page = view.current_page
            return bool(
                result is not None
                and result.query.query_identity_sha256 == expected_query
                and request is not None
                and request.page_index == int(payload["selected_page_index"])
                and page is not None
                and page.page_index == int(payload["selected_page_index"])
                and _view_idle(view)
            )

        _wait_for(
            app,
            restored_exactly,
            deadline=deadline,
            stage="Watchlist 原收藏 fresh exact 重開",
            cancel_marker=cancel_marker_path,
        )
        assert window.left_navigation.current_key() == "recommendation"
        assert window.recommendation_view.result_source_tabs.currentWidget() is view
        result = view.current_result
        request = view.current_request
        page = view.current_page
        assert result is not None and request is not None and page is not None
        assert result.query.bundle_identity_sha256 == payload["bundle_identity_sha256"]
        assert result.query.expected_manifest_sha256 == payload["manifest_sha256"]
        assert request.query.query_identity_sha256 == expected_query
        assert view.results_table.currentIndex().row() >= 0
        selected_row = page.rows[view.results_table.currentIndex().row()]
        assert selected_row.stock_code == expected_selected
        assert tuple(item.stock_code for item in view.comparison_basket) == expected_codes
        assert tuple(item.page_request.page_index for item in view.comparison_basket) == expected_pages
        assert tuple(item.page_request.query.query_identity_sha256 for item in view.comparison_basket) == (
            expected_query,
        ) * len(expected_codes)
        receipt["query_identity_sha256"] = result.query.query_identity_sha256
        receipt["page_index"] = request.page_index
        receipt["selected_stock_code"] = selected_row.stock_code
        receipt["comparison_stock_codes"] = [item.stock_code for item in view.comparison_basket]
        receipt["comparison_page_indices"] = [item.page_request.page_index for item in view.comparison_basket]
        receipt["watchlist_route_source"] = type(routed_bookmarks[0]).__name__

        QTest.mouseClick(view.compare_button, Qt.MouseButton.LeftButton)
        _wait_for(
            app,
            lambda: getattr(window, "_technical_official_comparison_dialog", None) is not None
            and bool(window._technical_official_comparison_dialog.isVisible())
            and _view_idle(view),
            deadline=deadline,
            stage="Main 真比較對話框",
            cancel_marker=cancel_marker_path,
        )
        dialog = window._technical_official_comparison_dialog
        group_codes = tuple(
            group.title()
            for group in dialog.findChildren(QGroupBox)
            if group.title() in expected_codes
        )
        assert group_codes == expected_codes
        close_button = next(
            button
            for button in dialog.findChildren(QPushButton)
            if button.text() == "關閉比較，返回原研究"
        )
        receipt["comparison_dialog_visible"] = dialog.isVisible()
        receipt["comparison_dialog_stock_codes"] = list(group_codes)
        QTest.mouseClick(close_button, Qt.MouseButton.LeftButton)
        _wait_for(
            app,
            lambda: not dialog.isVisible(),
            deadline=deadline,
            stage="關閉比較對話框",
            cancel_marker=cancel_marker_path,
        )

        QTest.mouseClick(view.detail_button, Qt.MouseButton.LeftButton)
        _wait_for(
            app,
            lambda: view.results_stack.currentIndex() == 1,
            deadline=deadline,
            stage="個股詳情畫面",
            cancel_marker=cancel_marker_path,
        )
        detail_text = view.detail_text.text()
        assert f"股票代碼：{expected_selected}" in detail_text
        assert "來源不持續監測" in detail_text
        assert "官方 available_at 未知" in detail_text
        receipt["detail_visible"] = True
        QTest.mouseClick(view.back_button, Qt.MouseButton.LeftButton)
        _wait_for(
            app,
            lambda: view.results_stack.currentIndex() == 0,
            deadline=deadline,
            stage="返回原結果頁",
            cancel_marker=cancel_marker_path,
        )
        assert view.current_result is not None
        assert view.current_result.query.query_identity_sha256 == expected_query
        assert view.current_request is not None
        assert view.current_request.page_index == int(payload["selected_page_index"])
        assert view.results_table.currentIndex().row() >= 0
        assert (
            view.current_page.rows[view.results_table.currentIndex().row()].stock_code
            == expected_selected
        )
        assert tuple(item.stock_code for item in view.comparison_basket) == expected_codes
        receipt["returned_to_original_page"] = True

        reopened = service.get_research_bookmark(bookmark_id)
        assert type(reopened) is DailyMarketTechnicalOfficialDispositionBookmarkV1
        assert reopened.to_json() == expected_bookmark_json
        window.close()
        _wait_for(
            app,
            lambda: not window.isVisible(),
            deadline=deadline,
            stage="child MainWindow 合作關閉",
            cancel_marker=cancel_marker_path,
        )
        receipt["main_closed"] = True
        receipt["watchlist_bookmark_json"] = reopened.to_json()
        receipt["source_inventory_after_sha256"] = hashlib.sha256(
            json.dumps(_source_inventory(source_roots), ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        if _source_inventory(source_roots) != source_before:
            raise AssertionError("child MainWindow 改動了合成來源/store/bundle inventory")
        watchlist_after = _watchlist_inventory(watchlist_root)
        receipt["watchlist_primary_after"] = watchlist_after["primary"]
        receipt["watchlist_primary_before"] = watchlist_before["primary"]
        receipt["watchlist_sidecars_before"] = watchlist_before["sidecars"]
        receipt["watchlist_sidecars_after"] = watchlist_after["sidecars"]
        if _primary_watchlist_bytes(watchlist_after) != expected_primary:
            raise AssertionError("child MainWindow 改動 Watchlist 持久化內容")
        if network_attempts:
            raise AssertionError(f"child MainWindow 出現網路嘗試：{network_attempts}")
        _check_cancel_marker(cancel_marker_path)
        receipt["status"] = "passed"
        return 0
    except Exception as exc:
        receipt["status"] = "failed"
        receipt["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        if window is not None:
            try:
                if window.isVisible():
                    window.close()
                    if app is not None:
                        final_deadline = time.monotonic() + 20.0
                        while window.isVisible() and time.monotonic() < final_deadline:
                            app.processEvents()
                            time.sleep(0.005)
            except RuntimeError:
                pass
        receipt["network_attempts"] = list(network_attempts)
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(
            json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2),
            encoding="utf-8",
        )


def test_watchlist_inventory_recurses_and_detects_primary_byte_changes(tmp_path: Path) -> None:
    root = tmp_path / "watchlist"
    nested = root / "repository"
    nested.mkdir(parents=True)
    default_path = root / "default.json"
    database_path = nested / "watchlists.db"
    sidecar_path = nested / "watchlists.db-wal"
    default_path.write_text('{"items":[]}', encoding="utf-8")
    database_path.write_bytes(b"synthetic-db-before")
    sidecar_path.write_bytes(b"synthetic-wal-observation")

    before = _watchlist_inventory(root)
    before_primary = _primary_watchlist_bytes(before)
    assert {item[0] for item in before_primary} == {
        "default.json",
        "repository\\watchlists.db",
    }
    before_sidecars = before["sidecars"]
    assert isinstance(before_sidecars, list)
    assert [item["relative_path"] for item in before_sidecars] == [
        "repository\\watchlists.db-wal"
    ]

    database_path.write_bytes(b"synthetic-db-after-change")
    after = _watchlist_inventory(root)
    assert _primary_watchlist_bytes(after) != before_primary


def test_minimal_child_environment_excludes_qt_added_parent_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PYSIDE6_OPTION_PYTHON_ENUM", "True")
    monkeypatch.setenv("PYTHONHOME", "parent-python-home")
    monkeypatch.setenv("PYTHONPATH", "parent-python-path")
    monkeypatch.setenv("PYTHONUSERBASE", "parent-python-userbase")
    expected_environment = {"DATA_ROOT": "C:/synthetic/data", "QT_QPA_PLATFORM": "offscreen"}

    child_environment = _minimal_child_environment(expected_env=expected_environment)

    expected_keys = set(expected_environment) | {
        name for name in _CHILD_RUNTIME_ENVIRONMENT_KEYS if os.environ.get(name) is not None
    }
    assert set(child_environment) == expected_keys
    assert child_environment["DATA_ROOT"] == expected_environment["DATA_ROOT"]
    assert child_environment["QT_QPA_PLATFORM"] == "offscreen"
    assert "PYSIDE6_OPTION_PYTHON_ENUM" not in child_environment
    assert "PYTHONHOME" not in child_environment
    assert "PYTHONPATH" not in child_environment
    assert "PYTHONUSERBASE" not in child_environment


def test_child_environment_validator_rejects_qt_added_unlisted_key() -> None:
    expected_environment = {"DATA_ROOT": "C:/synthetic/data"}
    allowed_environment = {"DATA_ROOT": "C:/synthetic/data", "PATH": "C:/Windows"}
    _validate_child_environment(
        allowed_environment,
        expected_environment=expected_environment,
        unset_environment_keys=[],
    )

    with pytest.raises(AssertionError, match="白名單外鍵值"):
        _validate_child_environment(
            {
                **allowed_environment,
                "PYSIDE6_OPTION_PYTHON_ENUM": "True",
            },
            expected_environment=expected_environment,
            unset_environment_keys=[],
        )


def test_pid_chain_accepts_only_direct_or_exact_venv_redirector_relation() -> None:
    executable = sys.executable
    direct = _validate_child_pid_chain(
        reporter_pid=12002,
        reporter_parent_pid=12001,
        reporter_executable=executable,
        launcher_pid=12002,
        parent_pid=12001,
        expected_executables=[executable],
    )
    redirected = _validate_child_pid_chain(
        reporter_pid=12003,
        reporter_parent_pid=12002,
        reporter_executable=executable,
        launcher_pid=12002,
        parent_pid=12001,
        expected_executables=[executable],
    )
    assert direct == "direct"
    assert redirected == "venv_redirector_child"


def test_pid_chain_rejects_fake_pid_wrong_parent_and_invalid_types() -> None:
    base: dict[str, object] = {
        "reporter_pid": 12003,
        "reporter_parent_pid": 12002,
        "reporter_executable": sys.executable,
        "launcher_pid": 12002,
        "parent_pid": 12001,
        "expected_executables": [sys.executable],
    }
    invalid_cases: tuple[tuple[str, object], ...] = (
        ("reporter_pid", 12001),
        ("reporter_parent_pid", 12004),
        ("reporter_pid", True),
        ("launcher_pid", "12002"),
        ("reporter_executable", "C:/untrusted/python.exe"),
    )
    for key, invalid_value in invalid_cases:
        candidate = dict(base)
        candidate[key] = invalid_value
        with pytest.raises(AssertionError):
            _validate_child_pid_chain(
                reporter_pid=candidate["reporter_pid"],
                reporter_parent_pid=candidate["reporter_parent_pid"],
                reporter_executable=candidate["reporter_executable"],
                launcher_pid=candidate["launcher_pid"],
                parent_pid=candidate["parent_pid"],
                expected_executables=candidate["expected_executables"],
            )


def test_minimal_venv_python_process_reports_exact_os_pid_chain(tmp_path: Path) -> None:
    attempt = Path("output/qa/f17_main_new_process_pidchain_20261008_a") / (
        f"venv_probe_{uuid4().hex[:10]}"
    )
    attempt_root = Path(__file__).resolve().parents[1] / attempt
    attempt_root.mkdir(parents=True, exist_ok=False)
    output_path = attempt_root / "process_identity.json"
    code = (
        "import json, os, sys; "
        "print(json.dumps({'pid': os.getpid(), 'parent_pid': os.getppid(), "
        "'executable': sys.executable}, sort_keys=True))"
    )
    parent_pid = os.getpid()
    process, job_handle = _spawn_child_process(
        [sys.executable, "-c", code],
        cwd=str(tmp_path),
        env=_minimal_child_environment(expected_env={}),
    )
    try:
        stdout, stderr = process.communicate(timeout=15.0)
        assert process.returncode == 0, stderr
        identity = json.loads(stdout)
        relation = _validate_child_pid_chain(
            reporter_pid=identity.get("pid"),
            reporter_parent_pid=identity.get("parent_pid"),
            reporter_executable=identity.get("executable"),
            launcher_pid=process.pid,
            parent_pid=parent_pid,
            expected_executables=[
                sys.executable,
                getattr(sys, "_base_executable", sys.executable),
            ],
        )
        output_path.write_text(
            json.dumps(
                {
                    "status": "passed",
                    "relation": relation,
                    "parent_pid": parent_pid,
                    "popen_pid": process.pid,
                    "reporter": identity,
                    "returncode": process.returncode,
                },
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
            ),
            encoding="utf-8",
        )
    finally:
        if process.poll() is None:
            _stop_child_bounded(
                process,
                job_handle=job_handle,
                cancel_marker=attempt_root / "cancel.requested",
                stdout_path=attempt_root / "stdout.log",
                stderr_path=attempt_root / "stderr.log",
                cooperative_wait_seconds=1.0,
                terminate_wait_seconds=1.0,
                final_wait_seconds=2.0,
            )
        _close_process_job(job_handle)


def test_bounded_timeout_cleans_launcher_reporter_and_grandchild(tmp_path: Path) -> None:
    attempt = Path("output/qa/f17_main_new_process_pidchain_20261008_a") / (
        f"tree_cleanup_{uuid4().hex[:10]}"
    )
    attempt_root = Path(__file__).resolve().parents[1] / attempt
    attempt_root.mkdir(parents=True, exist_ok=False)
    parent_script = attempt_root / "parent_script.py"
    grandchild_script = attempt_root / "grandchild_script.py"
    parent_identity_path = attempt_root / "parent_identity.json"
    grandchild_identity_path = attempt_root / "grandchild_identity.json"
    cancel_marker = attempt_root / "cancel.requested"
    stdout_path = attempt_root / "stdout.log"
    stderr_path = attempt_root / "stderr.log"
    grandchild_script.write_text(
        "\n".join(
            (
                "import json, os, sys, time",
                "from pathlib import Path",
                "Path(sys.argv[1]).write_text(json.dumps({'pid': os.getpid(), 'parent_pid': os.getppid()}), encoding='utf-8')",
                "while True: time.sleep(0.05)",
                "",
            )
        ),
        encoding="utf-8",
    )
    parent_script.write_text(
        "\n".join(
            (
                "import json, os, subprocess, sys, time",
                "from pathlib import Path",
                "child_launcher = subprocess.Popen([sys.executable, sys.argv[3], sys.argv[4]], stdout=sys.stdout, stderr=sys.stderr)",
                "identity = {'pid': os.getpid(), 'parent_pid': os.getppid(), 'executable': sys.executable, 'grandchild_launcher_pid': child_launcher.pid}",
                "Path(sys.argv[1]).write_text(json.dumps(identity), encoding='utf-8')",
                "marker = Path(sys.argv[2])",
                "while not marker.exists(): time.sleep(0.01)",
                "",
            )
        ),
        encoding="utf-8",
    )
    process, job_handle = _spawn_child_process(
        [
            sys.executable,
            str(parent_script),
            str(parent_identity_path),
            str(cancel_marker),
            str(grandchild_script),
            str(grandchild_identity_path),
        ],
        cwd=str(attempt_root),
        env=_minimal_child_environment(expected_env={}),
    )
    try:
        startup_deadline = time.monotonic() + 10.0
        while time.monotonic() < startup_deadline:
            if parent_identity_path.is_file() and grandchild_identity_path.is_file():
                break
            if process.poll() is not None:
                raise AssertionError("PID cleanup fixture 在建立 process tree 前提前結束")
            time.sleep(0.01)
        assert parent_identity_path.is_file()
        assert grandchild_identity_path.is_file()
        parent_identity = json.loads(parent_identity_path.read_text(encoding="utf-8"))
        grandchild_identity = json.loads(grandchild_identity_path.read_text(encoding="utf-8"))
        relation = _validate_child_pid_chain(
            reporter_pid=parent_identity.get("pid"),
            reporter_parent_pid=parent_identity.get("parent_pid"),
            reporter_executable=parent_identity.get("executable"),
            launcher_pid=process.pid,
            parent_pid=os.getpid(),
            expected_executables=[sys.executable, getattr(sys, "_base_executable", sys.executable)],
        )
        grandchild_pid = grandchild_identity.get("pid")
        if type(grandchild_pid) is not int or grandchild_pid <= 0:
            raise AssertionError("grandchild fixture 未回報有效 PID")
        grandchild_launcher_pid = parent_identity.get("grandchild_launcher_pid")
        if type(grandchild_launcher_pid) is not int or grandchild_launcher_pid <= 0:
            raise AssertionError("reporter 未記錄其 grandchild launcher PID")
        if grandchild_identity.get("parent_pid") != grandchild_launcher_pid:
            raise AssertionError("grandchild reporter 的 OS parent 不符合精確 launcher PID")
        cancel_marker.write_text("cancel requested\n", encoding="utf-8")
        _stop_child_bounded(
            process,
            job_handle=job_handle,
            cancel_marker=cancel_marker,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            cooperative_wait_seconds=0.25,
            terminate_wait_seconds=1.0,
            final_wait_seconds=1.0,
        )
        assert process.returncode is not None
        exit_deadline = time.monotonic() + 3.0
        tracked_pids = (
            int(parent_identity["pid"]),
            grandchild_launcher_pid,
            grandchild_pid,
        )
        while time.monotonic() < exit_deadline and any(
            _process_is_active(pid) for pid in tracked_pids
        ):
            time.sleep(0.01)
        assert not any(_process_is_active(pid) for pid in tracked_pids)
        (attempt_root / "result.json").write_text(
            json.dumps(
                {
                    "status": "passed",
                    "relation": relation,
                    "popen_pid": process.pid,
                    "parent_identity": parent_identity,
                    "grandchild_identity": grandchild_identity,
                    "tracked_processes_inactive": True,
                },
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
            ),
            encoding="utf-8",
        )
    finally:
        if process.poll() is None:
            _stop_child_bounded(
                process,
                job_handle=job_handle,
                cancel_marker=cancel_marker,
                stdout_path=stdout_path,
                stderr_path=stderr_path,
                cooperative_wait_seconds=0.25,
                terminate_wait_seconds=1.0,
                final_wait_seconds=1.0,
            )
        _close_process_job(job_handle)


def _check_persisted_bookmark_store(
    inventory: Mapping[str, object],
    *,
    watchlist_dir: Path,
    default_watchlist_file: Path,
    canonical_repository_path: Path,
) -> tuple[tuple[str, int, str], ...]:
    primary = _primary_watchlist_bytes(inventory)
    if not primary:
        raise AssertionError("Watchlist bookmark 保存後，持久檔 inventory 不可為空")
    saved_paths = {relative_path for relative_path, _, _ in primary}
    expected_paths = {
        str(default_watchlist_file.resolve().relative_to(watchlist_dir.resolve())),
        str(canonical_repository_path.resolve().relative_to(watchlist_dir.resolve())),
    }
    if not saved_paths.intersection(expected_paths):
        raise AssertionError(
            "Watchlist inventory 未包含 default.json 或 canonical SQLite repository"
        )
    return primary


def test_f17_watchlist_bookmark_reopens_in_new_mainwindow_process(
    monkeypatch: pytest.MonkeyPatch,
    bundle_fixture: Any,
    tmp_path: Path,
) -> None:
    """真 258 bundle 跨 Main／Python PID 收藏重開，並核對原來源 bytes。"""

    started = time.monotonic()
    deadline = started + _TOTAL_DEADLINE_SECONDS
    repo_root = Path(__file__).resolve().parents[1]
    qa_root = repo_root / _QA_ROOT_RELATIVE
    qa_root.mkdir(parents=True, exist_ok=True)
    attempt_root = qa_root / f"attempt_{uuid4().hex[:10]}"
    attempt_root.mkdir(parents=True, exist_ok=False)
    helper_path = attempt_root / "child_main_runner.py"
    input_path = attempt_root / "child_input.json"
    environment_manifest_path = attempt_root / "environment_whitelist.json"
    receipt_path = attempt_root / "child_receipt.json"
    cancel_marker_path = attempt_root / "child_cancel.requested"
    stdout_path = attempt_root / "child_stdout.log"
    stderr_path = attempt_root / "child_stderr.log"
    checkpoint_path = attempt_root / "parent_checkpoint.json"

    source_roots = _source_roots(bundle_fixture)
    fixture_root = Path(bundle_fixture.qa_root).resolve()
    assert Path(bundle_fixture.database).resolve().is_relative_to(fixture_root)
    assert Path(bundle_fixture.bundle_root).resolve().is_relative_to(fixture_root)
    assert all(root.is_relative_to(fixture_root) for root in source_roots)
    source_before = _source_inventory(source_roots)
    assert source_before

    isolated_root = tmp_path / "f17-main-parent-child"
    env, unset_values = _isolated_environment(
        root=isolated_root,
        bundle_root=Path(bundle_fixture.bundle_root).resolve(),
    )
    for name in _ISOLATED_ENVIRONMENT_KEYS:
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    for name in unset_values:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    assert Path(os.environ["DATA_ROOT"]).resolve().is_relative_to(isolated_root.resolve())
    assert Path(os.environ["OUTPUT_ROOT"]).resolve().is_relative_to(isolated_root.resolve())
    assert Path(os.environ["TECHNICAL_OFFICIAL_DISPOSITION_READ_ROOT"]).resolve() == Path(
        bundle_fixture.bundle_root
    ).resolve()
    assert os.environ.get("PERSONAL_DATA_ROOT") is None
    assert os.environ.get("PERSONAL_WATCHLIST_SOURCE") is None

    temporary_root = Path(env["TEMP"])
    temporary_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("tempfile.tempdir", str(temporary_root))
    network_attempts = _install_network_deny(monkeypatch)

    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from ui_qt.main import MainWindow

    app = cast(QApplication, QApplication.instance() or QApplication([]))
    window: Any | None = None
    persisted_bookmark: DailyMarketTechnicalOfficialDispositionBookmarkV1 | None = None
    child_return_code: int | None = None
    child_stdout = ""
    child_stderr = ""
    process: subprocess.Popen[str] | None = None
    process_job_handle: int | None = None
    child_output_collected = False
    pid_chain_kind: str | None = None
    source_after: tuple[tuple[str, tuple[tuple[object, ...], ...]], ...] = ()
    child_env = _minimal_child_environment(expected_env=env)
    expected_child_env = dict(env)
    unset_child_env = sorted(
        (set(_ISOLATED_ENVIRONMENT_KEYS) | set(_UNSET_CHILD_ENVIRONMENT_KEYS))
        - set(expected_child_env)
    )
    environment_manifest_path.write_text(
        json.dumps(
            {
                "runtime_allowlist": [
                    key
                    for key in _CHILD_RUNTIME_ENVIRONMENT_KEYS
                    if key in child_env
                ],
                "synthetic_environment": env,
                "unset_environment_keys": unset_child_env,
            },
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        ),
        encoding="utf-8",
    )

    try:
        window = MainWindow()
        assert Path(window.config.data_root).resolve() == Path(env["DATA_ROOT"]).resolve()
        assert Path(window.config.output_root).resolve() == Path(env["OUTPUT_ROOT"]).resolve()
        assert Path(cast(str, window.config.technical_official_disposition_read_root)).resolve() == Path(
            cast(Path, bundle_fixture.bundle_root)
        ).resolve()
        assert window.config.personal_data_root is None
        assert window.config.personal_watchlist_source is None
        assert window.config.personal_journal_root is None
        assert window.config.personal_journal_mode is None
        assert window.config.personal_store_root is None
        assert window.config.personal_store_mode is None
        service = window.watchlist_service
        assert service is not None
        output_root = Path(env["OUTPUT_ROOT"]).resolve()
        assert Path(service.default_watchlist_file).resolve().is_relative_to(output_root)
        assert Path(service.canonical_repository_path).resolve().is_relative_to(output_root)
        window.resize(1440, 980)
        window.show()
        app.processEvents()

        recommendation_button = window.left_navigation.button_for_key("recommendation")
        assert recommendation_button is not None and recommendation_button.isVisible()
        QTest.mouseClick(recommendation_button, Qt.MouseButton.LeftButton)
        assert window.left_navigation.current_key() == "recommendation"
        view = window.technical_official_research_view
        tabs = window.recommendation_view.result_source_tabs
        tab_index = tabs.indexOf(view)
        assert tab_index >= 0
        QTest.mouseClick(
            tabs.tabBar(),
            Qt.MouseButton.LeftButton,
            pos=tabs.tabBar().tabRect(tab_index).center(),
        )
        assert tabs.currentWidget() is view
        assert Path(view.bundle_output_root).resolve() == Path(bundle_fixture.bundle_root).resolve()

        QTest.mouseClick(view.refresh_catalog_button, Qt.MouseButton.LeftButton)
        _wait_for(
            app,
            lambda: _view_idle(view) and view.catalog_list.count() == 1,
            deadline=deadline,
            stage="父 Main 清單盤點",
        )
        catalog_item = view.catalog_list.item(0)
        assert catalog_item is not None and catalog_item.flags() & Qt.ItemFlag.ItemIsSelectable
        QTest.mouseClick(
            view.catalog_list.viewport(),
            Qt.MouseButton.LeftButton,
            pos=view.catalog_list.visualItemRect(catalog_item).center(),
        )
        _wait_for(
            app,
            lambda: _view_idle(view) and view.current_page is not None and view.current_result is not None,
            deadline=deadline,
            stage="父 Main 明確選取 bundle 並 exact-open",
        )
        result = view.current_result
        page = view.current_page
        assert result is not None and page is not None
        assert result.query.bundle_identity_sha256 == bundle_fixture.reference.bundle_identity_sha256
        assert result.query.expected_manifest_sha256 == bundle_fixture.reference.manifest_sha256
        assert page.counts.population.declared_count == 258
        assert page.counts.population.included_count == 257
        assert page.counts.population.excluded_count == 1
        assert page.scope == "current_only"
        assert page.official_available_at is None
        assert page.historical_pit_eligible is False
        assert page.full_market_claim is False

        selected_events: list[object] = []
        bookmark_events: list[object] = []
        view.stockSelected.connect(selected_events.append)
        view.bookmarkPrepared.connect(bookmark_events.append)
        assert view.current_request is not None and view.current_request.page_index == 0
        first_row = page.rows[0]
        assert first_row.stock_code == bundle_fixture.included_codes[0]
        view.page_scroll.ensureWidgetVisible(view.results_table)
        _click_table_row(app, view.results_table, 0, deadline=deadline)
        assert (
            view.current_page.rows[view.results_table.currentIndex().row()].stock_code
            == first_row.stock_code
        )
        QTest.mouseClick(view.add_comparison_button, Qt.MouseButton.LeftButton)
        assert tuple(item.stock_code for item in view.comparison_basket) == (first_row.stock_code,)

        for target_page in range(1, 6):
            assert view.next_page_button.isEnabled()
            QTest.mouseClick(view.next_page_button, Qt.MouseButton.LeftButton)

            def page_loaded(expected_page: int = target_page) -> bool:
                return (
                    _view_idle(view)
                    and view.current_page is not None
                    and view.current_page.page_index == expected_page
                )

            _wait_for(
                app,
                page_loaded,
                deadline=deadline,
                stage=f"父 Main 翻到第 {target_page} 頁",
            )
        last_page = view.current_page
        assert last_page is not None and last_page.page_index == 5
        second_code = last_page.rows[0].stock_code
        assert second_code in bundle_fixture.included_codes
        view.page_scroll.ensureWidgetVisible(view.results_table)
        _click_table_row(app, view.results_table, 0, deadline=deadline)
        assert (
            view.current_page.rows[view.results_table.currentIndex().row()].stock_code
            == second_code
        )
        QTest.mouseClick(view.add_comparison_button, Qt.MouseButton.LeftButton)
        assert tuple(item.stock_code for item in view.comparison_basket) == (
            first_row.stock_code,
            second_code,
        )
        assert tuple(item.page_request.page_index for item in view.comparison_basket) == (0, 5)
        assert view.current_request is not None and view.current_request.page_index == 5
        selected_code = view.current_page.rows[view.results_table.currentIndex().row()].stock_code
        assert selected_code == second_code
        assert view.bookmark_button.text() == "收藏原研究"
        QTest.mouseClick(view.bookmark_button, Qt.MouseButton.LeftButton)
        _wait_for(
            app,
            lambda: bool(bookmark_events)
            and not getattr(window, "_technical_official_bookmark_workers", set())
            and view.bookmark_button.isEnabled(),
            deadline=deadline,
            stage="父 Main 保存原研究收藏",
        )
        assert len(bookmark_events) == 1
        raw_bookmark = bookmark_events[0]
        assert type(raw_bookmark) is DailyMarketTechnicalOfficialDispositionBookmarkV1
        persisted_bookmark = cast(DailyMarketTechnicalOfficialDispositionBookmarkV1, raw_bookmark)
        assert persisted_bookmark.query_identity_sha256 == result.query.query_identity_sha256
        assert persisted_bookmark.selected_stock_code == selected_code
        assert tuple(item.stock_code for item in persisted_bookmark.comparison_items) == (
            first_row.stock_code,
            second_code,
        )
        assert tuple(
            item.page_request_json for item in persisted_bookmark.comparison_items
        ) == tuple(item.page_request.to_json() for item in view.comparison_basket)
        assert service.get_research_bookmark(persisted_bookmark.bookmark_id) == persisted_bookmark
        assert view.current_result.query.query_identity_sha256 == persisted_bookmark.query_identity_sha256
        assert selected_events == []

        watchlist_view = window.watchlist_view
        assert watchlist_view.stocks_model is not None
        row_index = _watchlist_row_for_bookmark(
            watchlist_view,
            persisted_bookmark.stock_code,
        )
        assert watchlist_view.stocks_table.model().rowCount() > row_index
        assert window._technical_official_bookmark_workers == set()
        window.close()
        _wait_for(
            app,
            lambda: not window.isVisible(),
            deadline=deadline,
            stage="父 Main 正常關閉與 worker 終態",
        )

        watchlist_before_child = _watchlist_inventory(Path(service.watchlist_dir))
        persisted_after_parent = service.get_research_bookmark(persisted_bookmark.bookmark_id)
        assert type(persisted_after_parent) is DailyMarketTechnicalOfficialDispositionBookmarkV1
        bookmark_json = persisted_after_parent.to_json()
        assert bookmark_json == persisted_bookmark.to_json()
        primary_before_child = _check_persisted_bookmark_store(
            watchlist_before_child,
            watchlist_dir=Path(service.watchlist_dir),
            default_watchlist_file=Path(service.default_watchlist_file),
            canonical_repository_path=Path(service.canonical_repository_path),
        )
        source_after_parent = _source_inventory(source_roots)
        assert source_after_parent == source_before

        helper_path.write_text(_helper_source(), encoding="utf-8")
        payload = {
            "repo_root": str(repo_root),
            "source_roots": [str(path) for path in source_roots],
            "receipt_path": str(receipt_path),
            "cancel_marker_path": str(cancel_marker_path),
            "bookmark_id": persisted_bookmark.bookmark_id,
            "bookmark_json": bookmark_json,
            "bundle_identity_sha256": bundle_fixture.reference.bundle_identity_sha256,
            "manifest_sha256": bundle_fixture.reference.manifest_sha256,
            "query_identity_sha256": persisted_bookmark.query_identity_sha256,
            "selected_stock_code": persisted_bookmark.selected_stock_code,
            "selected_page_index": 5,
            "comparison_stock_codes": [first_row.stock_code, second_code],
            "comparison_page_indices": [0, 5],
            "watchlist_primary_bytes": [list(item) for item in primary_before_child],
            "expected_environment": expected_child_env,
            "unset_environment_keys": unset_child_env,
            "remaining_total_seconds": _remaining_seconds(deadline),
        }
        input_path.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2),
            encoding="utf-8",
        )
        checkpoint_path.write_text(
            json.dumps(
                {
                    "status": "parent_closed_child_starting",
                    "parent_pid": os.getpid(),
                    "fixture_root": str(fixture_root),
                    "synthetic_data_root": env["DATA_ROOT"],
                    "synthetic_output_root": env["OUTPUT_ROOT"],
                    "bundle_root": str(bundle_fixture.bundle_root),
                    "bundle_identity_sha256": bundle_fixture.reference.bundle_identity_sha256,
                    "manifest_sha256": bundle_fixture.reference.manifest_sha256,
                    "query_identity_sha256": persisted_bookmark.query_identity_sha256,
                    "bookmark_identity_sha256": persisted_bookmark.bookmark_identity_sha256,
                    "source_inventory_sha256": hashlib.sha256(
                        json.dumps(source_after_parent, ensure_ascii=False, sort_keys=True).encode("utf-8")
                    ).hexdigest(),
                    "watchlist_primary_bytes": [list(item) for item in primary_before_child],
                    "watchlist_sidecars": watchlist_before_child["sidecars"],
                    "child_deadline_seconds": min(
                        _CHILD_DEADLINE_SECONDS,
                        _remaining_seconds(deadline),
                    ),
                },
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
            ),
            encoding="utf-8",
        )

        command = [sys.executable, str(helper_path), str(repo_root), str(input_path)]
        child_deadline = min(time.monotonic() + _CHILD_DEADLINE_SECONDS, deadline)
        process, process_job_handle = _spawn_child_process(
            command,
            cwd=str(repo_root),
            env=child_env,
        )
        assert process.pid != os.getpid()
        try:
            child_timeout = child_deadline - time.monotonic()
            if child_timeout <= 0:
                raise subprocess.TimeoutExpired(command, timeout=0)
            child_stdout, child_stderr = process.communicate(timeout=child_timeout)
            child_output_collected = True
        except subprocess.TimeoutExpired as timeout_error:
            child_stdout, child_stderr = _stop_child_bounded(
                process,
                job_handle=process_job_handle,
                cancel_marker=cancel_marker_path,
                stdout_path=stdout_path,
                stderr_path=stderr_path,
            )
            child_output_collected = True
            child_return_code = process.returncode
            raise AssertionError(
                "child MainWindow 超過 min(240 秒, 父旅程共同 deadline)；已先送合作取消，"
                "再以有限 terminate／kill 收束，測試判定失敗"
            ) from timeout_error
        child_return_code = process.returncode
        stdout_path.write_text(child_stdout, encoding="utf-8")
        stderr_path.write_text(child_stderr, encoding="utf-8")
        assert child_return_code == 0, (
            f"全新 PID F17 journey 失敗，exit={child_return_code}; "
            f"stdout={stdout_path}; stderr={stderr_path}; receipt={receipt_path}"
        )
        assert receipt_path.is_file()
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        assert receipt["status"] == "passed"
        pid_chain_kind = _validate_child_pid_chain(
            reporter_pid=receipt.get("pid"),
            reporter_parent_pid=receipt.get("parent_pid"),
            reporter_executable=receipt.get("executable"),
            launcher_pid=process.pid,
            parent_pid=os.getpid(),
            expected_executables=[
                sys.executable,
                getattr(sys, "_base_executable", sys.executable),
            ],
        )
        assert receipt["query_identity_sha256"] == persisted_bookmark.query_identity_sha256
        assert receipt["page_index"] == 5
        assert receipt["selected_stock_code"] == selected_code
        assert tuple(receipt["comparison_stock_codes"]) == (first_row.stock_code, second_code)
        assert tuple(receipt["comparison_page_indices"]) == (0, 5)
        assert receipt["comparison_dialog_visible"] is True
        assert receipt["detail_visible"] is True
        assert receipt["returned_to_original_page"] is True
        assert receipt["main_closed"] is True
        assert receipt["network_attempts"] == []
        assert receipt["watchlist_bookmark_json"] == bookmark_json
        assert _primary_watchlist_bytes({"primary": receipt["watchlist_primary_before"]}) == primary_before_child
        assert _primary_watchlist_bytes({"primary": receipt["watchlist_primary_after"]}) == primary_before_child

        source_after = _source_inventory(source_roots)
        assert source_after == source_before
        watchlist_after_child = _watchlist_inventory(Path(service.watchlist_dir))
        assert _primary_watchlist_bytes(watchlist_after_child) == primary_before_child
        assert not network_attempts
        if time.monotonic() > deadline:
            raise AssertionError("F17 全新程序旅程完成時間超過共同 300 秒 deadline")

        checkpoint_path.write_text(
            json.dumps(
                {
                    "status": "passed",
                    "parent_pid": os.getpid(),
                    "child_pid": process.pid,
                    "child_reporter_pid": receipt["pid"],
                    "child_reporter_parent_pid": receipt["parent_pid"],
                    "child_pid_chain_kind": pid_chain_kind,
                    "elapsed_seconds": round(time.monotonic() - started, 3),
                    "deadline_seconds": _TOTAL_DEADLINE_SECONDS,
                    "child_timeout_cap_seconds": _CHILD_DEADLINE_SECONDS,
                    "child_return_code": child_return_code,
                    "source_inventory_sha256": hashlib.sha256(
                        json.dumps(source_after, ensure_ascii=False, sort_keys=True).encode("utf-8")
                    ).hexdigest(),
                    "watchlist_primary_before": watchlist_before_child["primary"],
                    "watchlist_primary_after": watchlist_after_child["primary"],
                    "watchlist_sidecars_before": watchlist_before_child["sidecars"],
                    "watchlist_sidecars_after": watchlist_after_child["sidecars"],
                    "environment_manifest_path": str(environment_manifest_path),
                    "child_receipt": receipt,
                    "network_attempts": network_attempts,
                },
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
            ),
            encoding="utf-8",
        )
    except Exception as exc:
        checkpoint_path.write_text(
            json.dumps(
                {
                    "status": "failed",
                    "phase_elapsed_seconds": round(time.monotonic() - started, 3),
                    "error": f"{type(exc).__name__}: {exc}",
                    "child_return_code": child_return_code,
                    "child_stdout_path": str(stdout_path) if stdout_path.exists() else None,
                    "child_stderr_path": str(stderr_path) if stderr_path.exists() else None,
                    "child_receipt_path": str(receipt_path) if receipt_path.exists() else None,
                    "source_inventory_before_sha256": hashlib.sha256(
                        json.dumps(source_before, ensure_ascii=False, sort_keys=True).encode("utf-8")
                    ).hexdigest(),
                    "source_inventory_after_sha256": hashlib.sha256(
                        json.dumps(_source_inventory(source_roots), ensure_ascii=False, sort_keys=True).encode("utf-8")
                    ).hexdigest(),
                    "network_attempts": network_attempts,
                },
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
            ),
            encoding="utf-8",
        )
        raise
    finally:
        try:
            if process is not None and (process.poll() is None or not child_output_collected):
                try:
                    child_stdout, child_stderr = _stop_child_bounded(
                        process,
                        job_handle=process_job_handle,
                        cancel_marker=cancel_marker_path,
                        stdout_path=stdout_path,
                        stderr_path=stderr_path,
                    )
                    child_output_collected = True
                    child_return_code = process.returncode
                except Exception as cleanup_error:
                    checkpoint_path.write_text(
                        json.dumps(
                            {
                                "status": "failed_child_cleanup",
                                "phase_elapsed_seconds": round(time.monotonic() - started, 3),
                                "error": f"{type(cleanup_error).__name__}: {cleanup_error}",
                                "child_return_code": process.returncode,
                                "child_stdout_path": str(stdout_path),
                                "child_stderr_path": str(stderr_path),
                                "cancel_marker_path": str(cancel_marker_path),
                            },
                            ensure_ascii=False,
                            sort_keys=True,
                            indent=2,
                        ),
                        encoding="utf-8",
                    )
                    raise AssertionError(
                        "child process tree cleanup 未能在有限等待內確認終止；保留來源與子程序輸出"
                    ) from cleanup_error
        finally:
            _close_process_job(process_job_handle)
            process_job_handle = None
        if window is not None and window.isVisible():
            window.close()
            cleanup_deadline = time.monotonic() + 20.0
            while window.isVisible() and time.monotonic() < cleanup_deadline:
                app.processEvents()
                time.sleep(0.005)
        if window is not None and window.isVisible():
            raise AssertionError("parent MainWindow 關閉未完成；保留 fixture 與診斷")
