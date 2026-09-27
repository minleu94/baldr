"""Canonical 與舊版推薦結果的唯讀 query/read-view seam。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
from types import MappingProxyType
from typing import IO, Literal, Mapping, Protocol, cast

from app_module.recommendation.legacy_dtos import RecommendationResultDTO
from app_module.recommendation.codec import (
    ExecutionCodecError,
    ExecutionReadEnvelope,
    decode_artifact,
)
from app_module.recommendation.contracts import (
    MLAvailabilityStatus,
    RecommendationExecution,
    ReferenceKind,
)
from app_module.recommendation.persistence import (
    ExecutionArtifactIntegrityError,
    ExecutionIndexReadError,
    RecommendationExecutionPersistence,
)
from data_module.result_artifact_store import ArtifactIndexRecord


_SHA256_PATTERN = re.compile(r"sha256:[0-9a-f]{64}\Z")
_FILE_ATTRIBUTE_REPARSE_POINT = 0x400
_FILE_ATTRIBUTE_DEVICE = 0x40
_SQLITE_DATABASE_HEADER = b"SQLite format 3\x00"
_SQLITE_SIDECAR_SUFFIXES = ("-wal", "-shm", "-journal")


def _require_safe_legacy_result_id(result_id: str) -> None:
    """拒絕會被當作路徑、ADS 或 Win32 裝置別名的 legacy ID。"""

    invalid = (
        type(result_id) is not str
        or not result_id.strip()
        or result_id in {".", ".."}
        or "/" in result_id
        or "\\" in result_id
        or "\x00" in result_id
    )
    if os.name == "nt" and not invalid:
        invalid = (
            result_id[-1] in {" ", "."}
            or any(
                ord(character) < 32 or character in '<>:"|?*'
                for character in result_id
            )
        )
        device_stem = result_id.split(".", 1)[0].rstrip(" .").upper()
        reserved_devices = {
            "CON",
            "PRN",
            "AUX",
            "NUL",
            "CONIN$",
            "CONOUT$",
            *(f"COM{number}" for number in range(1, 10)),
            *(f"LPT{number}" for number in range(1, 10)),
            "COM¹",
            "COM²",
            "COM³",
            "LPT¹",
            "LPT²",
            "LPT³",
        }
        invalid = invalid or device_stem in reserved_devices
    if invalid:
        raise ValueError("legacy result_id 必須是安全的單一檔名")


def _is_symlink_or_reparse(path: Path) -> bool:
    """涵蓋 POSIX symlink 與 Windows junction/reparse point。"""

    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return False
    attributes = getattr(metadata, "st_file_attributes", 0)
    return stat.S_ISLNK(metadata.st_mode) or bool(
        attributes & _FILE_ATTRIBUTE_REPARSE_POINT
    )


def _windows_open_nofollow_handle(path: Path, *, directory: bool) -> int:
    """以同一 no-follow handle 驗證 disk type、attribute 與目錄／檔案型別。"""

    win_dll = getattr(ctypes, "WinDLL", None)
    if not callable(win_dll):
        raise ExecutionArtifactIntegrityError(
            "Windows no-follow handle API 不可用；拒絕 legacy read"
        )
    import msvcrt
    from ctypes import wintypes

    kernel32 = win_dll("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = (
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    )
    create_file.restype = wintypes.HANDLE
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = (wintypes.HANDLE,)
    close_handle.restype = wintypes.BOOL
    get_info = kernel32.GetFileInformationByHandleEx
    get_info.argtypes = (
        wintypes.HANDLE,
        wintypes.INT,
        wintypes.LPVOID,
        wintypes.DWORD,
    )
    get_info.restype = wintypes.BOOL
    try:
        get_file_type = kernel32.GetFileType
    except AttributeError as exc:
        raise ExecutionArtifactIntegrityError(
            "Windows GetFileType API 不可用；拒絕 legacy read"
        ) from exc
    get_file_type.argtypes = (wintypes.HANDLE,)
    get_file_type.restype = wintypes.DWORD

    class _FileAttributeTagInfo(ctypes.Structure):
        _fields_ = (("attributes", wintypes.DWORD), ("reparse_tag", wintypes.DWORD))

    generic_read = 0x80000000
    file_read_attributes = 0x00000080
    share_read_write = 0x00000001 | 0x00000002
    open_existing = 3
    open_reparse_point = 0x00200000
    backup_semantics = 0x02000000
    sequential_scan = 0x08000000
    info_class_file_attribute_tag = 9
    file_attribute_directory = 0x00000010
    file_type_disk = 0x0001
    invalid_handle = ctypes.c_void_p(-1).value

    desired_access = file_read_attributes if directory else generic_read
    flags = open_reparse_point | (backup_semantics if directory else sequential_scan)
    handle = create_file(
        str(path),
        desired_access,
        share_read_write,
        None,
        open_existing,
        flags,
        None,
    )
    handle_value = handle if isinstance(handle, int) else getattr(handle, "value", None)
    is_invalid_handle = handle_value is None or handle_value == invalid_handle
    if isinstance(handle_value, int) and handle_value == -1:
        is_invalid_handle = True
    if is_invalid_handle:
        error = ctypes.get_last_error()
        if error in (2, 3):
            raise FileNotFoundError(error, os.strerror(error), str(path))
        raise OSError(error, f"CreateFileW failed for {path}")
    native_handle_value = cast(int, handle_value)

    try:
        if get_file_type(handle) != file_type_disk:
            raise ExecutionArtifactIntegrityError(
                "Windows legacy handle 必須是一般 disk file 或 directory"
            )
        info = _FileAttributeTagInfo()
        if not get_info(
            handle,
            info_class_file_attribute_tag,
            ctypes.byref(info),
            ctypes.sizeof(info),
        ):
            error = ctypes.get_last_error()
            raise OSError(error, f"GetFileInformationByHandleEx failed for {path}")
        if info.attributes & _FILE_ATTRIBUTE_REPARSE_POINT:
            raise ExecutionArtifactIntegrityError(
                "Windows opened path is a reparse point"
            )
        if info.attributes & _FILE_ATTRIBUTE_DEVICE:
            raise ExecutionArtifactIntegrityError(
                "Windows legacy handle 不可是 device"
            )
        is_directory = bool(info.attributes & file_attribute_directory)
        if is_directory != directory:
            raise ExecutionArtifactIntegrityError(
                "legacy root component must be a directory and payload a regular file"
            )
        if directory:
            result = native_handle_value
            handle_value = None
            return result
        descriptor = msvcrt.open_osfhandle(
            native_handle_value, os.O_RDONLY | getattr(os, "O_BINARY", 0)
        )
        handle_value = None
        return descriptor
    finally:
        if handle_value is not None:
            close_handle(handle)


def _windows_close_handle(handle: int) -> None:
    win_dll = getattr(ctypes, "WinDLL", None)
    if not callable(win_dll):
        raise ExecutionArtifactIntegrityError(
            "Windows no-follow handle API 不可用；無法安全關閉 legacy root handle"
        )
    from ctypes import wintypes

    close_handle = win_dll("kernel32", use_last_error=True).CloseHandle
    close_handle.argtypes = (wintypes.HANDLE,)
    close_handle.restype = wintypes.BOOL
    if not close_handle(handle):
        error = ctypes.get_last_error()
        raise OSError(error, "CloseHandle failed for legacy read root")


def _windows_read_regular_file_no_follow(
    path: Path,
    root: Path,
    *,
    max_bytes: int | None = None,
) -> bytes:
    """以固定且持有的 runs root/parents/file handles 讀取一般檔案。"""

    absolute_root = Path(os.path.abspath(root))
    if not absolute_root.is_absolute() or not absolute_root.anchor:
        raise ExecutionArtifactIntegrityError("Windows legacy root 必須是絕對路徑")
    try:
        relative = path.relative_to(absolute_root)
    except ValueError as exc:
        raise ExecutionArtifactIntegrityError(
            "Windows legacy file 超出已錨定的 runs root"
        ) from exc
    if not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
        raise ExecutionArtifactIntegrityError("Windows legacy file path 非 exact child path")

    held_directories: list[int] = []
    descriptor: int | None = None
    try:
        current = Path(absolute_root.anchor)
        held_directories.append(
            _windows_open_nofollow_handle(current, directory=True)
        )
        for component in absolute_root.parts[1:]:
            current = current / component
            held_directories.append(
                _windows_open_nofollow_handle(current, directory=True)
            )
        for component in relative.parts[:-1]:
            current = current / component
            held_directories.append(
                _windows_open_nofollow_handle(current, directory=True)
            )
        target = current / relative.parts[-1]
        if target != path:
            raise ExecutionArtifactIntegrityError(
                "Windows legacy target path 在讀取前解析結果不一致"
            )
        descriptor = _windows_open_nofollow_handle(target, directory=False)
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = None
            payload, _read_key = _read_stable_regular_file(
                handle,
                "legacy file",
                max_bytes=max_bytes,
            )
            return payload
    except ExecutionArtifactIntegrityError:
        raise
    except Exception as exc:
        raise ExecutionArtifactIntegrityError(
            "無法透過 Windows no-follow handles 讀取 legacy bytes"
        ) from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        for directory_handle in reversed(held_directories):
            _windows_close_handle(directory_handle)


def _posix_open_directory_chain_no_follow(root: Path) -> list[int]:
    """從 `/` 起以 held dir_fd 錨定 root 的每一層祖先。"""

    open_supports_dir_fd = getattr(os, "open", None) in getattr(
        os, "supports_dir_fd", set()
    )
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    directory_flag = getattr(os, "O_DIRECTORY", 0)
    if not open_supports_dir_fd or not nofollow or not directory_flag:
        raise ExecutionArtifactIntegrityError(
            "此平台缺少 dir_fd/O_NOFOLLOW；拒絕 legacy file read"
        )
    if not root.is_absolute() or root.anchor != "/":
        raise ExecutionArtifactIntegrityError(
            "POSIX legacy root 必須使用絕對檔案系統路徑"
        )
    if any(component in {"", ".", ".."} for component in root.parts[1:]):
        raise ExecutionArtifactIntegrityError("POSIX legacy root component 非 canonical")
    held_directories: list[int] = []
    try:
        directory_flags = (
            os.O_RDONLY
            | directory_flag
            | nofollow
            | getattr(os, "O_CLOEXEC", 0)
        )
        directory_fd = os.open(
            root.anchor,
            directory_flags,
        )
        held_directories.append(directory_fd)
        if not stat.S_ISDIR(os.fstat(directory_fd).st_mode):
            raise ExecutionArtifactIntegrityError(
                "POSIX filesystem root 必須是一般目錄"
            )
        for component in root.parts[1:]:
            directory_fd = os.open(
                component,
                directory_flags,
                dir_fd=held_directories[-1],
            )
            held_directories.append(directory_fd)
            if not stat.S_ISDIR(os.fstat(directory_fd).st_mode):
                raise ExecutionArtifactIntegrityError(
                    "POSIX legacy runs root ancestor 必須是一般目錄"
                )
        return held_directories
    except Exception:
        for directory_fd in reversed(held_directories):
            os.close(directory_fd)
        raise


def _posix_read_regular_file_no_follow(
    path: Path,
    root: Path,
    *,
    max_bytes: int | None = None,
) -> bytes:
    """從檔案系統根目錄逐層錨定 runs root 與其目標。"""

    if not path.is_absolute() or path.anchor != root.anchor:
        raise ExecutionArtifactIntegrityError(
            "POSIX legacy file 必須使用與 runs root 相同的絕對路徑"
        )
    try:
        relative = path.relative_to(root)
    except ValueError as exc:
        raise ExecutionArtifactIntegrityError(
            "legacy file 超出已錨定的 runs root"
        ) from exc
    if not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
        raise ExecutionArtifactIntegrityError("legacy file path 非 exact child path")

    held_directories = _posix_open_directory_chain_no_follow(root)
    descriptor: int | None = None
    try:
        nofollow = getattr(os, "O_NOFOLLOW", 0)
        directory_flag = getattr(os, "O_DIRECTORY", 0)
        for component in relative.parts[:-1]:
            directory_fd = os.open(
                component,
                os.O_RDONLY
                | directory_flag
                | nofollow
                | getattr(os, "O_CLOEXEC", 0),
                dir_fd=held_directories[-1],
            )
            held_directories.append(directory_fd)
            if not stat.S_ISDIR(os.fstat(directory_fd).st_mode):
                raise ExecutionArtifactIntegrityError(
                    "legacy path component 必須是一般目錄"
                )
        descriptor = os.open(
            relative.parts[-1],
            os.O_RDONLY | nofollow | getattr(os, "O_CLOEXEC", 0),
            dir_fd=held_directories[-1],
        )
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ExecutionArtifactIntegrityError("legacy payload 必須是一般檔案")
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = None
            payload, _read_key = _read_stable_regular_file(
                handle,
                "legacy file",
                max_bytes=max_bytes,
            )
            return payload
    except ExecutionArtifactIntegrityError:
        raise
    except Exception as exc:
        raise ExecutionArtifactIntegrityError(
            "無法透過 filesystem-root dir_fd/O_NOFOLLOW 讀取 legacy bytes"
        ) from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        for directory_fd in reversed(held_directories):
            os.close(directory_fd)


def _read_regular_file_no_follow(
    path: Path,
    root: Path,
    *,
    max_bytes: int | None = None,
) -> bytes:
    if os.name == "nt":
        return _windows_read_regular_file_no_follow(path, root, max_bytes=max_bytes)
    return _posix_read_regular_file_no_follow(path, root, max_bytes=max_bytes)


def _stat_stability_key(info: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        int(info.st_dev),
        int(info.st_ino),
        int(info.st_mode),
        int(info.st_size),
        int(info.st_mtime_ns),
        int(info.st_ctime_ns),
    )


def _read_stable_regular_file(
    handle: IO[bytes],
    label: str,
    *,
    max_bytes: int | None = None,
) -> tuple[bytes, tuple[int, int, int, int, int, int]]:
    before = os.fstat(handle.fileno())
    if not stat.S_ISREG(before.st_mode):
        raise ExecutionArtifactIntegrityError(f"{label} 必須是一般檔案")
    if max_bytes is not None:
        if type(max_bytes) is not int or max_bytes < 0:
            raise ValueError("max_bytes 必須是非負整數或 None")
        if before.st_size > max_bytes:
            raise ExecutionArtifactIntegrityError(f"{label} 超過讀取大小上限")
        payload = handle.read(max_bytes + 1)
    else:
        payload = handle.read()
    after = os.fstat(handle.fileno())
    before_key = _stat_stability_key(before)
    after_key = _stat_stability_key(after)
    if (
        before_key != after_key
        or len(payload) != before.st_size
        or (max_bytes is not None and len(payload) > max_bytes)
    ):
        raise ExecutionArtifactIntegrityError(f"{label} 在單次讀取期間 bytes/stat 改變")
    return payload, after_key


def _posix_assert_no_sqlite_sidecars(database_name: str, runs_directory_fd: int) -> None:
    stat_function = getattr(os, "stat", None)
    supports_dir_fd = stat_function in getattr(os, "supports_dir_fd", set())
    supports_nofollow = stat_function in getattr(
        os, "supports_follow_symlinks", set()
    )
    if not supports_dir_fd or not supports_nofollow:
        raise ExecutionArtifactIntegrityError(
            "此平台缺少 dir_fd no-follow SQLite sidecar 檢查；拒絕開啟 legacy SQLite"
        )
    for suffix in _SQLITE_SIDECAR_SUFFIXES:
        sidecar_name = database_name + suffix
        try:
            os.stat(sidecar_name, dir_fd=runs_directory_fd, follow_symlinks=False)
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise ExecutionArtifactIntegrityError(
                "無法安全檢查 legacy SQLite sidecar"
            ) from exc
        raise ExecutionArtifactIntegrityError(
            f"legacy SQLite sidecar 存在，拒絕唯讀 snapshot：{sidecar_name}"
        )


def _posix_read_sqlite_database_no_follow(
    database_path: Path,
    runs_root: Path,
) -> bytes | None:
    if database_path.parent != runs_root or database_path.name != "recommendation_runs.db":
        raise ExecutionArtifactIntegrityError(
            "legacy SQLite database 必須是 runs root 的 exact child"
        )
    try:
        held_directories = _posix_open_directory_chain_no_follow(runs_root)
    except ExecutionArtifactIntegrityError:
        raise
    except Exception as exc:
        raise ExecutionArtifactIntegrityError(
            "無法 no-follow 錨定 legacy SQLite runs root/ancestors"
        ) from exc
    descriptor: int | None = None
    try:
        runs_directory_fd = held_directories[-1]
        _posix_assert_no_sqlite_sidecars(database_path.name, runs_directory_fd)
        try:
            database_entry = os.stat(
                database_path.name,
                dir_fd=runs_directory_fd,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise ExecutionArtifactIntegrityError(
                "無法安全檢查 legacy SQLite database directory entry"
            ) from exc
        if not stat.S_ISREG(database_entry.st_mode):
            raise ExecutionArtifactIntegrityError(
                "legacy SQLite database directory entry 必須是一般檔案"
            )
        descriptor = os.open(
            database_path.name,
            os.O_RDONLY
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
            dir_fd=runs_directory_fd,
        )
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = None
            payload, read_key = _read_stable_regular_file(
                handle,
                "legacy SQLite database",
            )
        try:
            path_info = os.stat(
                database_path.name,
                dir_fd=runs_directory_fd,
                follow_symlinks=False,
            )
        except OSError as exc:
            raise ExecutionArtifactIntegrityError(
                "legacy SQLite database directory entry 在讀取期間改變"
            ) from exc
        if (
            not stat.S_ISREG(path_info.st_mode)
            or _stat_stability_key(path_info) != read_key
        ):
            raise ExecutionArtifactIntegrityError(
                "legacy SQLite database path/bytes 在單次讀取期間改變"
            )
        _posix_assert_no_sqlite_sidecars(database_path.name, runs_directory_fd)
        return payload
    except ExecutionArtifactIntegrityError:
        raise
    except Exception as exc:
        raise ExecutionArtifactIntegrityError(
            "無法透過 filesystem-root dir_fd/O_NOFOLLOW 讀取 legacy SQLite bytes"
        ) from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        for directory_fd in reversed(held_directories):
            os.close(directory_fd)


def _windows_open_legacy_runs_root(runs_root: Path) -> tuple[Path, list[int]]:
    absolute_root = Path(os.path.abspath(runs_root))
    if not absolute_root.is_absolute() or not absolute_root.anchor:
        raise ExecutionArtifactIntegrityError("Windows legacy root 必須是絕對路徑")
    held_directories: list[int] = []
    try:
        current = Path(absolute_root.anchor)
        held_directories.append(
            _windows_open_nofollow_handle(current, directory=True)
        )
        for component in absolute_root.parts[1:]:
            current = current / component
            held_directories.append(
                _windows_open_nofollow_handle(current, directory=True)
            )
        return absolute_root, held_directories
    except Exception:
        for directory_handle in reversed(held_directories):
            _windows_close_handle(directory_handle)
        raise


def _windows_assert_no_sqlite_sidecars(database_name: str, runs_root: Path) -> None:
    for suffix in _SQLITE_SIDECAR_SUFFIXES:
        sidecar = runs_root / f"{database_name}{suffix}"
        try:
            metadata = sidecar.lstat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise ExecutionArtifactIntegrityError(
                "無法安全檢查 legacy SQLite sidecar 路徑"
            ) from exc
        attributes = getattr(metadata, "st_file_attributes", 0)
        if stat.S_ISLNK(metadata.st_mode) or attributes & _FILE_ATTRIBUTE_REPARSE_POINT:
            raise ExecutionArtifactIntegrityError(
                f"legacy SQLite sidecar 是 symlink/reparse，拒絕唯讀 snapshot：{sidecar.name}"
            )
        try:
            descriptor = _windows_open_nofollow_handle(sidecar, directory=False)
        except FileNotFoundError as exc:
            raise ExecutionArtifactIntegrityError(
                f"legacy SQLite sidecar 在 no-follow open 前後改變：{sidecar.name}"
            ) from exc
        except Exception as exc:
            raise ExecutionArtifactIntegrityError(
                "無法安全檢查 legacy SQLite sidecar"
            ) from exc
        os.close(descriptor)
        raise ExecutionArtifactIntegrityError(
            f"legacy SQLite sidecar 存在，拒絕唯讀 snapshot：{sidecar.name}"
        )


def _windows_read_sqlite_database_no_follow(
    database_path: Path,
    runs_root: Path,
) -> bytes | None:
    absolute_root = Path(os.path.abspath(runs_root))
    absolute_database = Path(os.path.abspath(database_path))
    if (
        absolute_database.parent != absolute_root
        or absolute_database.name != "recommendation_runs.db"
    ):
        raise ExecutionArtifactIntegrityError(
            "legacy SQLite database 必須是 runs root 的 exact child"
        )
    try:
        _absolute_root, held_directories = _windows_open_legacy_runs_root(absolute_root)
    except ExecutionArtifactIntegrityError:
        raise
    except Exception as exc:
        raise ExecutionArtifactIntegrityError(
            "無法以 no-follow handles 錨定 legacy SQLite runs root/ancestors"
        ) from exc
    descriptor: int | None = None
    try:
        _windows_assert_no_sqlite_sidecars(absolute_database.name, absolute_root)
        try:
            database_entry = absolute_database.lstat()
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise ExecutionArtifactIntegrityError(
                "無法安全檢查 legacy SQLite database directory entry"
            ) from exc
        if not stat.S_ISREG(database_entry.st_mode):
            raise ExecutionArtifactIntegrityError(
                "legacy SQLite database directory entry 必須是一般檔案"
            )
        descriptor = _windows_open_nofollow_handle(
            absolute_database,
            directory=False,
        )
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = None
            payload, _read_key = _read_stable_regular_file(
                handle,
                "legacy SQLite database",
            )
        _windows_assert_no_sqlite_sidecars(absolute_database.name, absolute_root)
        return payload
    except ExecutionArtifactIntegrityError:
        raise
    except Exception as exc:
        raise ExecutionArtifactIntegrityError(
            "無法透過 Windows no-follow handles 讀取 legacy SQLite bytes"
        ) from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        for directory_handle in reversed(held_directories):
            _windows_close_handle(directory_handle)


def _read_sqlite_database_no_follow(
    database_path: Path,
    runs_root: Path,
) -> bytes | None:
    if os.name == "nt":
        return _windows_read_sqlite_database_no_follow(database_path, runs_root)
    return _posix_read_sqlite_database_no_follow(database_path, runs_root)


def _validate_legacy_sqlite_header(payload: bytes) -> None:
    if len(payload) < 100 or payload[:16] != _SQLITE_DATABASE_HEADER:
        raise ExecutionArtifactIntegrityError(
            "legacy SQLite main database header 無效或不完整"
        )
    if payload[18] != 1 or payload[19] != 1:
        raise ExecutionArtifactIntegrityError(
            "legacy SQLite WAL/非 rollback-journal mode 不支援；拒絕降級讀取"
        )


def _validate_legacy_sqlite_schema(connection: sqlite3.Connection) -> None:
    """驗證存在的 legacy runs 表可由唯讀投影查詢。"""

    runs_table = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'runs'"
    ).fetchone()
    if runs_table is None:
        # Canonical-only databases may share this index file and have no legacy
        # table; they are a valid empty legacy namespace.
        return
    columns = {
        row[1]
        for row in connection.execute("PRAGMA table_info('runs')").fetchall()
    }
    required = {"result_id", "result_name", "notes", "created_at", "data_path"}
    if not required.issubset(columns):
        raise ExecutionArtifactIntegrityError(
            "legacy SQLite runs schema 缺少唯讀查詢所需欄位"
        )


@dataclass(frozen=True, slots=True)
class LegacyRecommendationBytes:
    """從既有 runs row 及其原始 JSON 檔取得的唯讀值。"""

    result_id: str
    data_path: str
    raw_payload: bytes
    label: str | None
    notes: str | None
    created_at: str | None
    trusted_expected_sha256: str | None


@dataclass(frozen=True, slots=True)
class LegacyRecommendationOriginalPayload:
    """legacy 唯讀原始 payload 投影；不屬於 canonical execution 型別。"""

    result_id: str
    data_path: str
    payload: Mapping[str, object]
    raw_artifact_sha256: str
    integrity_basis: Literal[
        "legacy_trusted_hash_verified", "legacy_read_time_hash_only"
    ]
    source: Literal["registered_legacy_run", "unindexed_legacy_file"]


class LegacyRecommendationRawByteReader(Protocol):
    """可注入的 legacy SQLite/raw-byte port；不得建立 schema 或寫檔。"""

    def get(self, result_id: str) -> LegacyRecommendationBytes | None: ...

    def list_result_ids(self) -> tuple[str, ...]: ...


class SQLiteLegacyRecommendationRawByteReader:
    """以唯讀 SQLite 與原始 bytes 連接既有 RecommendationRepository runs。"""

    def __init__(
        self,
        runs_dir: Path,
        database_path: Path,
        *,
        trusted_expected_hashes: Mapping[str, str] | None = None,
    ) -> None:
        self._runs_dir = Path(runs_dir)
        self._database_path = Path(database_path)
        self._trusted_expected_hashes = dict(trusted_expected_hashes or {})
        if self._database_path.name != "recommendation_runs.db":
            raise ValueError("legacy reader database_path 必須是 recommendation_runs.db")
        if Path(os.path.abspath(self._database_path.parent)) != Path(
            os.path.abspath(self._runs_dir)
        ):
            raise ValueError("legacy reader 的 database 與 runs_dir 必須是同一目錄")
        for result_id, expected_hash in self._trusted_expected_hashes.items():
            if type(result_id) is not str or not result_id.strip():
                raise ValueError("trusted expected hash map 含無效 result_id")
            if type(expected_hash) is not str or _SHA256_PATTERN.fullmatch(expected_hash) is None:
                raise ValueError("trusted expected hash 必須是 sha256:<64 小寫 hex>")

    def _connect_read_only(self) -> sqlite3.Connection | None:
        runs_root = Path(os.path.abspath(self._runs_dir))
        database_path = Path(os.path.abspath(self._database_path))
        if (
            database_path.parent != runs_root
            or database_path.name != "recommendation_runs.db"
        ):
            raise ExecutionArtifactIntegrityError(
                "legacy database 路徑必須是 configured runs root 的 exact child"
            )
        if not self._preflight_runs_root_exists(runs_root):
            # No legacy namespace has been created yet. This is distinct from
            # an ancestor disappearing after the preflight, which the held
            # no-follow walk below reports as an integrity error.
            return None
        if _is_symlink_or_reparse(database_path):
            raise ExecutionArtifactIntegrityError(
                "legacy SQLite database 不可為 symlink/reparse"
            )
        raw_database = _read_sqlite_database_no_follow(database_path, runs_root)
        if raw_database is None:
            return None
        if self._verified_runs_root() != runs_root:
            raise ExecutionArtifactIntegrityError(
                "legacy runs root 在 SQLite bytes 讀取期間改變"
            )
        _validate_legacy_sqlite_header(raw_database)

        try:
            connection = sqlite3.connect(":memory:", timeout=5.0)
        except sqlite3.Error as exc:
            raise ExecutionIndexReadError(
                "無法建立唯讀 legacy SQLite memory snapshot"
            ) from exc
        deserialize = getattr(connection, "deserialize", None)
        if not callable(deserialize):
            connection.close()
            raise ExecutionIndexReadError(
                "此 Python SQLite 不支援 deserialize；拒絕 pathname fallback"
            )
        try:
            deserialize(raw_database)
            connection.execute("PRAGMA query_only = ON")
            integrity_rows = connection.execute("PRAGMA integrity_check").fetchall()
            if integrity_rows != [("ok",)]:
                raise ExecutionArtifactIntegrityError(
                    "legacy SQLite main database integrity_check 未通過"
                )
            _validate_legacy_sqlite_schema(connection)
            return connection
        except ExecutionArtifactIntegrityError:
            connection.close()
            raise
        except sqlite3.Error as exc:
            connection.close()
            raise ExecutionArtifactIntegrityError(
                "legacy SQLite main database bytes 無法安全 deserialize/query"
            ) from exc

    @staticmethod
    def _preflight_runs_root_exists(configured_root: Path) -> bool:
        """Distinguish an initially absent output tree from a read-time race."""

        if not configured_root.is_absolute() or not configured_root.anchor:
            raise ExecutionArtifactIntegrityError(
                "legacy runs root 必須是絕對路徑"
            )
        current = Path(configured_root.anchor)
        for component in configured_root.parts[1:]:
            if component not in {"", ".", ".."}:
                current = current / component
            try:
                metadata = current.lstat()
            except FileNotFoundError:
                return False
            except OSError as exc:
                raise ExecutionArtifactIntegrityError(
                    "無法安全檢查 legacy runs root/ancestors"
                ) from exc
            attributes = getattr(metadata, "st_file_attributes", 0)
            if stat.S_ISLNK(metadata.st_mode) or attributes & _FILE_ATTRIBUTE_REPARSE_POINT:
                raise ExecutionArtifactIntegrityError(
                    "legacy runs 目錄不可為 symlink/reparse"
                )
            if not stat.S_ISDIR(metadata.st_mode):
                raise ExecutionArtifactIntegrityError(
                    "legacy runs root ancestor 必須是一般目錄"
                )
        return True

    @staticmethod
    def _has_runs_table(connection: sqlite3.Connection) -> bool:
        row = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'runs'"
        ).fetchone()
        return row is not None

    def list_result_ids(self) -> tuple[str, ...]:
        connection = self._connect_read_only()
        if connection is None:
            return ()
        try:
            if not self._has_runs_table(connection):
                return ()
            rows = connection.execute(
                "SELECT result_id FROM runs ORDER BY created_at DESC, result_id COLLATE BINARY"
            ).fetchall()
        except sqlite3.Error as exc:
            raise ExecutionIndexReadError("無法唯讀列出 legacy runs") from exc
        finally:
            connection.close()
        result_ids: list[str] = []
        for row in rows:
            result_id = row[0]
            try:
                _require_safe_legacy_result_id(result_id)
            except ValueError as exc:
                raise ExecutionArtifactIntegrityError(
                    "legacy runs 含 Win32 不安全 result_id"
                ) from exc
            result_ids.append(result_id)
        if len(result_ids) != len(set(result_ids)):
            raise ExecutionArtifactIntegrityError("legacy runs 含重複 result_id")
        return tuple(result_ids)

    def has_identity(self, result_id: str) -> bool:
        """只查 legacy SQLite identity，不依 ID 開啟任何檔案路徑。"""

        if type(result_id) is not str:
            raise ExecutionArtifactIntegrityError(
                "legacy identity query result_id 型別錯誤"
            )
        connection = self._connect_read_only()
        if connection is None:
            return False
        try:
            if not self._has_runs_table(connection):
                return False
            rows = connection.execute(
                "SELECT 1 FROM runs WHERE result_id = ? LIMIT 2", (result_id,)
            ).fetchall()
        except sqlite3.Error as exc:
            raise ExecutionIndexReadError(
                "無法唯讀查詢 legacy result identity"
            ) from exc
        finally:
            connection.close()
        if len(rows) > 1:
            raise ExecutionArtifactIntegrityError("legacy runs 含重複 result_id")
        return bool(rows)

    def _verified_runs_root(self) -> Path:
        """回傳與設定路徑一致且不是 symlink/reparse 的 runs root。"""

        configured_root = Path(os.path.abspath(self._runs_dir))
        if _is_symlink_or_reparse(configured_root):
            raise ExecutionArtifactIntegrityError(
                "legacy runs 目錄不可為 symlink/reparse"
            )
        try:
            resolved_root = configured_root.resolve(strict=True)
        except OSError as exc:
            raise ExecutionArtifactIntegrityError("legacy runs 目錄不存在") from exc
        if resolved_root != configured_root:
            raise ExecutionArtifactIntegrityError(
                "legacy runs root resolve 與 configured absolute path 不一致"
            )
        if _is_symlink_or_reparse(resolved_root):
            raise ExecutionArtifactIntegrityError(
                "legacy runs 目錄不可為 symlink/reparse"
            )
        return configured_root

    def _read_scoped_path(self, result_id: str, stored_path: object) -> tuple[Path, bytes]:
        _require_safe_legacy_result_id(result_id)
        if type(stored_path) is not str or not stored_path.strip():
            raise ExecutionArtifactIntegrityError("legacy runs.data_path 缺失或型別錯誤")
        root = self._verified_runs_root()
        supplied_path = Path(stored_path).expanduser()
        if not supplied_path.is_absolute():
            supplied_path = root / supplied_path
        supplied_absolute = Path(os.path.abspath(supplied_path))
        expected_absolute = Path(os.path.abspath(root / f"{result_id}.json"))
        try:
            relative = supplied_absolute.relative_to(root)
            expected_absolute.relative_to(root)
        except ValueError as exc:
            raise ExecutionArtifactIntegrityError(
                "legacy data_path 超出 runs 目錄範圍"
            ) from exc
        if supplied_absolute != expected_absolute or not relative.parts:
            raise ExecutionArtifactIntegrityError(
                "legacy data_path 與 result_id 的舊檔名規則不符"
            )

        cursor = root
        for component in relative.parts:
            cursor = cursor / component
            if _is_symlink_or_reparse(cursor):
                raise ExecutionArtifactIntegrityError("legacy data_path 不可經過 symlink")
        try:
            resolved = supplied_absolute.resolve(strict=True)
        except OSError as exc:
            raise ExecutionArtifactIntegrityError("legacy result bytes 不存在") from exc
        if resolved != supplied_absolute or not resolved.is_relative_to(root):
            raise ExecutionArtifactIntegrityError("legacy data_path 解析後超出 runs scope")
        try:
            payload = _read_regular_file_no_follow(resolved, root)
        except ExecutionArtifactIntegrityError:
            raise
        except Exception as exc:
            raise ExecutionArtifactIntegrityError(
                "無法安全唯讀 legacy result bytes"
            ) from exc
        if self._verified_runs_root() != root:
            raise ExecutionArtifactIntegrityError(
                "legacy runs root 在 raw bytes 讀取期間改變"
            )
        return resolved, payload

    def get(self, result_id: str) -> LegacyRecommendationBytes | None:
        _require_safe_legacy_result_id(result_id)
        connection = self._connect_read_only()
        if connection is None:
            return None
        try:
            if not self._has_runs_table(connection):
                return None
            rows = connection.execute(
                """
                SELECT result_id, result_name, notes, created_at, data_path
                  FROM runs
                 WHERE result_id = ?
                 LIMIT 2
                """,
                (result_id,),
            ).fetchall()
        except sqlite3.Error as exc:
            raise ExecutionIndexReadError("無法唯讀查詢 legacy result identity") from exc
        finally:
            connection.close()
        if not rows:
            return None
        if len(rows) > 1:
            raise ExecutionArtifactIntegrityError("legacy runs 含重複 result_id")
        row = rows[0]
        stored_result_id, label, notes, created_at, stored_path = row
        if stored_result_id != result_id:
            raise ExecutionArtifactIntegrityError("legacy SQLite result_id identity mismatch")
        path, payload = self._read_scoped_path(result_id, stored_path)
        for value, field_name in ((label, "result_name"), (notes, "notes"), (created_at, "created_at")):
            if value is not None and type(value) is not str:
                raise ExecutionArtifactIntegrityError(f"legacy runs.{field_name} 型別錯誤")
        return LegacyRecommendationBytes(
            result_id=result_id,
            data_path=str(path),
            raw_payload=payload,
            label=cast(str | None, label),
            notes=cast(str | None, notes),
            created_at=cast(str | None, created_at),
            trusted_expected_sha256=self._trusted_expected_hashes.get(result_id),
        )


@dataclass(frozen=True, slots=True)
class RecommendationExecutionReadModel:
    """由已驗證 canonical execution 或唯讀 legacy DTO 組成的單一 read view。"""

    execution: RecommendationExecution | None
    label: str | None
    notes: str | None
    persisted_at: datetime | None
    payload_hash: str | None
    artifact_location: str
    legacy_result: RecommendationResultDTO | None = None
    schema_version: str | None = None
    schema_revision: int | None = None
    raw_artifact_sha256: str = ""
    integrity_basis: Literal[
        "canonical_payload_and_index_verified",
        "legacy_trusted_hash_verified",
        "legacy_read_time_hash_only",
    ] = "canonical_payload_and_index_verified"
    ml_read_status: Literal[
        "not_requested", "unknown", "verified", "unavailable", "legacy_saved_fields"
    ] = "not_requested"
    ml_projection_rows: tuple[Mapping[str, object], ...] = ()
    diagnostics: tuple[str, ...] = ()

    @property
    def result_id(self) -> str:
        if self.execution is not None:
            return self.execution.result_id
        if self.legacy_result is not None:
            return self.legacy_result.result_id
        raise ExecutionArtifactIntegrityError("read view 缺少結果身分")

    @property
    def result(self) -> RecommendationExecution | RecommendationResultDTO:
        """提供同一 query seam 的保存結果；legacy 型別維持唯讀 decoder ABI。"""

        if self.execution is not None:
            return self.execution
        if self.legacy_result is not None:
            return self.legacy_result
        raise ExecutionArtifactIntegrityError("read view 缺少保存結果")


def _metadata_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ExecutionArtifactIntegrityError("SQLite persisted_at 不是 ISO datetime") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ExecutionArtifactIntegrityError("SQLite persisted_at 缺少 timezone offset")
    return parsed


def _legacy_datetime(value: str | None) -> datetime | None:
    """舊 created_at 若無時區或格式未知就保留為 unknown。"""

    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed


def _freeze_json(value: object) -> object:
    if type(value) is dict:
        return MappingProxyType(
            {str(key): _freeze_json(item) for key, item in cast(dict[str, object], value).items()}
        )
    if type(value) is list:
        return tuple(_freeze_json(item) for item in cast(list[object], value))
    return value


def _read_ml_projections(
    execution: RecommendationExecution,
) -> tuple[
    Literal["not_requested", "unknown", "verified", "unavailable"],
    tuple[Mapping[str, object], ...],
    tuple[str, ...],
]:
    bindings = execution.ml_receipt_refs
    projection_hashes = tuple(
        reference.reference_id
        for reference in execution.ml_projection_refs
        if reference.kind is ReferenceKind.ML_PROJECTION
    )
    if not bindings:
        if projection_hashes:
            return "unavailable", (), ("ml_projection_ref_missing_receipt_binding",)
        if execution.ml_availability.status is MLAvailabilityStatus.NOT_REQUESTED:
            return "not_requested", (), ()
        if execution.ml_availability.status is MLAvailabilityStatus.UNKNOWN:
            return "unknown", (), ()
        return "unavailable", (), ("ml_receipt_binding_missing",)

    try:
        from ml_module.recommendation_inference_provenance import (
            read_inference_projection_receipt,
        )

        verified_hashes: list[str] = []
        verified_rows: list[Mapping[str, object]] = []
        for binding in bindings:
            receipt_reference = binding.receipt_ref
            if receipt_reference.kind is not ReferenceKind.ML_RECEIPT:
                raise ExecutionArtifactIntegrityError("ML receipt reference kind mismatch")
            receipt_path = Path(receipt_reference.reference_id).expanduser()
            resolved_reference = str(receipt_path.resolve())
            receipt = read_inference_projection_receipt(
                receipt_path,
                expected_receipt_hash=binding.receipt_hash,
                expected_decision_date=binding.decision_date.isoformat(),
                expected_candidate_id=binding.model_candidate_id,
                expected_result_id=execution.result_id,
                expected_cost_scenario_hash=binding.cost_scenario_hash,
            )
            if receipt.receipt_path != resolved_reference:
                raise ExecutionArtifactIntegrityError("ML receipt path reference mismatch")
            body = receipt.payload
            if body.get("result_id") != binding.result_id:
                raise ExecutionArtifactIntegrityError("ML receipt result_id binding mismatch")
            if body.get("decision_date") != binding.decision_date.isoformat():
                raise ExecutionArtifactIntegrityError("ML receipt decision date binding mismatch")
            candidate = body.get("candidate_identity")
            if not isinstance(candidate, Mapping) or candidate.get("candidate_id") != binding.model_candidate_id:
                raise ExecutionArtifactIntegrityError("ML receipt candidate binding mismatch")
            if body.get("cost_scenario_hash") != binding.cost_scenario_hash:
                raise ExecutionArtifactIntegrityError("ML receipt cost binding mismatch")
            rows = body.get("projections")
            rows_hash = body.get("projection_rows_sha256")
            if type(rows) is not list or not rows or type(rows_hash) is not str:
                raise ExecutionArtifactIntegrityError("ML receipt projection rows/hash 缺失")
            row_codes = tuple(
                str(row.get("stock_code") or "")
                for row in rows
                if isinstance(row, Mapping)
            )
            if len(row_codes) != len(rows) or row_codes != binding.projected_stock_codes:
                raise ExecutionArtifactIntegrityError(
                    "ML receipt projected stock code order/set 與 execution binding 不符"
                )
            if rows_hash not in projection_hashes:
                raise ExecutionArtifactIntegrityError(
                    "ML receipt row hash 未由 execution projection reference 綁定"
                )
            verified_hashes.append(rows_hash)
            verified_rows.extend(
                cast(Mapping[str, object], _freeze_json(dict(row))) for row in rows
            )
        if len(verified_hashes) != len(bindings):
            raise ExecutionArtifactIntegrityError(
                "ML receipt 與 execution projection references 未一對一綁定"
            )
        if len(verified_hashes) != len(set(verified_hashes)):
            raise ExecutionArtifactIntegrityError("不同 ML receipt 重複綁定 projection row hash")
        if len(projection_hashes) != len(set(projection_hashes)):
            raise ExecutionArtifactIntegrityError("execution ML projection references 重複")
        if (
            len(projection_hashes) != len(verified_hashes)
            or set(projection_hashes) != set(verified_hashes)
        ):
            raise ExecutionArtifactIntegrityError(
                "execution projection references 與已驗證 receipt row hashes 未一對一相符"
            )
        return "verified", tuple(verified_rows), ()
    except Exception as exc:  # receipt integrity failure remains visible in read view
        return (
            "unavailable",
            (),
            (f"ml_receipt_validation_failed:{type(exc).__name__}",),
        )


class RecommendationExecutionQueries:
    """單一唯讀 seam；不查詢 live regime、score、資料來源或模型。"""

    def __init__(
        self,
        persistence: RecommendationExecutionPersistence,
        legacy_reader: LegacyRecommendationRawByteReader | None = None,
    ) -> None:
        self._persistence = persistence
        self._legacy_reader = legacy_reader or self._legacy_reader_from_store(persistence)

    @staticmethod
    def _legacy_reader_from_store(
        persistence: RecommendationExecutionPersistence,
    ) -> LegacyRecommendationRawByteReader | None:
        """沿用 canonical store 的 recommendation_runs.db 接舊 runs，不建舊 repository。"""

        store = getattr(persistence, "_store", None)
        database_path = getattr(store, "database_path", None)
        artifact_root = getattr(store, "artifact_root", None)
        if not isinstance(database_path, (str, Path)) or not isinstance(
            artifact_root, (str, Path)
        ):
            return None
        database = Path(database_path)
        runs_dir = Path(artifact_root).parent
        if database.parent != runs_dir:
            raise ValueError("canonical store 與 legacy runs 必須共用 recommendation_runs.db")
        return SQLiteLegacyRecommendationRawByteReader(runs_dir, database)

    def _canonical_read_model(
        self,
        record: ArtifactIndexRecord,
        envelope: ExecutionReadEnvelope,
    ) -> RecommendationExecutionReadModel:
        metadata = record.metadata
        ml_status, projections, diagnostics = _read_ml_projections(envelope.execution)
        return RecommendationExecutionReadModel(
            execution=envelope.execution,
            label=metadata.label,
            notes=metadata.notes,
            persisted_at=_metadata_datetime(metadata.persisted_at),
            payload_hash=envelope.payload_hash,
            artifact_location=record.artifact_name,
            schema_version=envelope.schema_version,
            schema_revision=envelope.schema_revision,
            raw_artifact_sha256=envelope.raw_payload_sha256,
            integrity_basis="canonical_payload_and_index_verified",
            ml_read_status=ml_status,
            ml_projection_rows=projections,
            diagnostics=diagnostics,
        )

    def _legacy_read_model(
        self, result_id: str, before: LegacyRecommendationBytes
    ) -> RecommendationExecutionReadModel:
        (
            legacy_result,
            _original_payload,
            payload_hash,
            integrity_basis,
        ) = self._decode_legacy_original_payload(result_id, before)
        self._assert_registered_legacy_unchanged(result_id, before)
        return RecommendationExecutionReadModel(
            execution=None,
            label=before.label or legacy_result.result_name,
            notes=before.notes if before.notes is not None else legacy_result.notes,
            persisted_at=_legacy_datetime(before.created_at),
            payload_hash=None,
            artifact_location=before.data_path,
            legacy_result=legacy_result,
            raw_artifact_sha256=payload_hash,
            integrity_basis=integrity_basis,
            ml_read_status="legacy_saved_fields",
        )

    @staticmethod
    def _decode_legacy_original_payload(
        result_id: str,
        source: LegacyRecommendationBytes,
        *,
        include_original_payload: bool = False,
    ) -> tuple[
        RecommendationResultDTO,
        Mapping[str, object] | None,
        str,
        Literal["legacy_trusted_hash_verified", "legacy_read_time_hash_only"],
    ]:
        """用既有 codec 驗證同一 raw bytes，再唯讀保留其完整 JSON mapping。"""

        if type(source.raw_payload) is not bytes:
            raise ExecutionArtifactIntegrityError("legacy raw artifact 必須是 bytes")
        payload_hash = "sha256:" + hashlib.sha256(source.raw_payload).hexdigest()
        trusted_hash = source.trusted_expected_sha256
        if trusted_hash is not None and trusted_hash != payload_hash:
            raise ExecutionArtifactIntegrityError(
                "legacy raw bytes 與獨立可信 expected hash 不符"
            )
        try:
            decoded = decode_artifact(
                source.raw_payload,
                expected_sha256=trusted_hash or payload_hash,
            )
            if not isinstance(decoded, RecommendationResultDTO):
                raise ExecutionArtifactIntegrityError(
                    "legacy read seam 遇到非 legacy DTO artifact"
                )
            original_payload: Mapping[str, object] | None = None
            if include_original_payload:
                # decode_artifact 已先用 codec 的 strict JSON parser 驗證這些相同
                # bytes（含重複 key 與非有限數值）；此處只取得完整 opaque mapping。
                document = json.loads(source.raw_payload.decode("utf-8"))
                if type(document) is not dict:
                    raise ExecutionArtifactIntegrityError(
                        "legacy original payload 頂層必須是 object"
                    )
                frozen_payload = _freeze_json(cast(dict[str, object], document))
                if not isinstance(frozen_payload, Mapping):
                    raise ExecutionArtifactIntegrityError(
                        "legacy original payload 無法建立唯讀 mapping"
                    )
                original_payload = cast(Mapping[str, object], frozen_payload)
        except ExecutionArtifactIntegrityError:
            raise
        except (
            ExecutionCodecError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
            KeyError,
        ) as exc:
            raise ExecutionArtifactIntegrityError("legacy artifact decoder 驗證失敗") from exc
        if decoded.result_id != result_id or source.result_id != result_id:
            raise ExecutionArtifactIntegrityError(
                "legacy artifact result_id 與 query identity 不符"
            )
        basis: Literal[
            "legacy_trusted_hash_verified", "legacy_read_time_hash_only"
        ] = (
            "legacy_trusted_hash_verified"
            if trusted_hash is not None
            else "legacy_read_time_hash_only"
        )
        return decoded, original_payload, payload_hash, basis

    def _assert_registered_legacy_unchanged(
        self,
        result_id: str,
        before: LegacyRecommendationBytes,
    ) -> None:
        after = self._legacy_reader.get(result_id) if self._legacy_reader is not None else None
        if after is None:
            raise ExecutionArtifactIntegrityError("legacy result 在讀取期間消失")
        if after.result_id != before.result_id:
            raise ExecutionArtifactIntegrityError("legacy result identity 在讀取期間改變")
        if after.data_path != before.data_path or after.raw_payload != before.raw_payload:
            raise ExecutionArtifactIntegrityError("legacy raw bytes/path 在單次讀取前後改變")
        if after.trusted_expected_sha256 != before.trusted_expected_sha256:
            raise ExecutionArtifactIntegrityError("legacy trusted hash authority 在讀取期間改變")

    def _legacy_identity_exists(
        self,
        result_id: str,
        *,
        require_metadata_only: bool = False,
    ) -> bool:
        reader = self._legacy_reader
        if reader is None:
            return False
        identity_reader = getattr(reader, "has_identity", None)
        if callable(identity_reader):
            try:
                exists = identity_reader(result_id)
            except ExecutionArtifactIntegrityError:
                raise
            except Exception as exc:
                raise ExecutionArtifactIntegrityError(
                    "無法唯讀查詢 legacy SQLite identity"
                ) from exc
            if type(exists) is not bool:
                raise ExecutionArtifactIntegrityError(
                    "legacy SQLite identity lookup 必須回傳 bool"
                )
            return exists
        if require_metadata_only:
            raise ExecutionArtifactIntegrityError(
                "legacy reader 缺少 metadata-only identity lookup；拒絕 canonical read"
            )
        try:
            return reader.get(result_id) is not None
        except ValueError as exc:
            raise ExecutionArtifactIntegrityError(
                "legacy result_id 不是安全的單一檔名"
            ) from exc

    def _legacy_runs_dir(self) -> Path | None:
        store = getattr(self._persistence, "_store", None)
        database_path = getattr(store, "database_path", None)
        artifact_root = getattr(store, "artifact_root", None)
        if not isinstance(database_path, (str, Path)) or not isinstance(
            artifact_root, (str, Path)
        ):
            return None
        runs_dir = Path(artifact_root).parent
        if Path(os.path.abspath(Path(database_path).parent)) != Path(
            os.path.abspath(runs_dir)
        ):
            raise ExecutionArtifactIntegrityError(
                "unindexed legacy root 與 canonical store database 不同"
            )
        return runs_dir

    def _read_unindexed_legacy_file(
        self, result_id: str
    ) -> LegacyRecommendationBytes | None:
        """從 store 所屬 runs 根唯讀取 exact ``<result_id>.json``，不信任 index。"""

        _require_safe_legacy_result_id(result_id)
        runs_dir = self._legacy_runs_dir()
        if runs_dir is None:
            raise ExecutionArtifactIntegrityError(
                "unindexed legacy read 缺少可驗證的 canonical store root"
            )
        if _is_symlink_or_reparse(runs_dir):
            raise ExecutionArtifactIntegrityError(
                "unindexed legacy runs root 不可為 symlink/reparse"
            )
        try:
            root = runs_dir.resolve(strict=True)
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise ExecutionArtifactIntegrityError(
                "unindexed legacy runs root 無法解析"
            ) from exc
        supplied_root = Path(os.path.abspath(runs_dir))
        if root != supplied_root:
            raise ExecutionArtifactIntegrityError(
                "unindexed legacy runs root 解析後路徑不一致"
            )

        expected_path = root / f"{result_id}.json"
        if _is_symlink_or_reparse(expected_path):
            raise ExecutionArtifactIntegrityError(
                "unindexed legacy result 不可為 symlink/reparse"
            )
        if not expected_path.exists():
            return None
        try:
            resolved = expected_path.resolve(strict=True)
        except OSError as exc:
            raise ExecutionArtifactIntegrityError(
                "unindexed legacy result path 無法解析"
            ) from exc
        if (
            resolved != expected_path
            or resolved.parent != root
            or not resolved.is_relative_to(root)
        ):
            raise ExecutionArtifactIntegrityError(
                "unindexed legacy result path 超出精確 runs scope"
            )
        try:
            raw_payload = _read_regular_file_no_follow(resolved, root)
        except ExecutionArtifactIntegrityError:
            raise
        except Exception as exc:
            raise ExecutionArtifactIntegrityError(
                "無法安全唯讀 unindexed legacy bytes"
            ) from exc
        if raw_payload is None:
            raise ExecutionArtifactIntegrityError(
                "unindexed legacy result 在讀取期間消失"
            )
        return LegacyRecommendationBytes(
            result_id=result_id,
            data_path=str(resolved),
            raw_payload=raw_payload,
            label=None,
            notes=None,
            created_at=None,
            trusted_expected_sha256=None,
        )

    def _assert_no_canonical_claim(self, result_id: str) -> None:
        try:
            record, envelope = self._persistence.read_verified_envelope(result_id)
        except KeyError:
            record = None
            envelope = None
        if record is not None or envelope is not None:
            raise ExecutionArtifactIntegrityError(
                "canonical result claim exists during legacy-only projection"
            )
        self._assert_no_unindexed_canonical_artifact(result_id)

    def get_legacy_original_payload(
        self,
        result_id: str,
        *,
        allow_unindexed_legacy: bool = False,
    ) -> LegacyRecommendationOriginalPayload | None:
        """唯讀取得已驗證 legacy 完整 payload；canonical execution 一律不投影。"""

        _require_safe_legacy_result_id(result_id)
        try:
            record, envelope = self._persistence.read_verified_envelope(result_id)
        except KeyError:
            record = None
            envelope = None
        if record is not None or envelope is not None:
            if self._legacy_identity_exists(
                result_id,
                require_metadata_only=True,
            ):
                raise ExecutionArtifactIntegrityError(
                    "同一 result_id 同時出現在 canonical index 與 legacy runs"
                )
            raise ExecutionArtifactIntegrityError(
                "canonical result 不可經 legacy-only original-payload query 讀取"
            )
        self._assert_no_unindexed_canonical_artifact(result_id)

        registered = (
            self._legacy_reader.get(result_id)
            if self._legacy_reader is not None
            else None
        )
        if registered is not None:
            if registered.result_id != result_id:
                raise ExecutionArtifactIntegrityError(
                    "legacy SQLite result_id 與 query identity 不符"
                )
            _decoded, payload, raw_hash, integrity_basis = (
                self._decode_legacy_original_payload(
                    result_id,
                    registered,
                    include_original_payload=True,
                )
            )
            if payload is None:
                raise ExecutionArtifactIntegrityError(
                    "legacy original payload projection 缺少 mapping"
                )
            self._assert_registered_legacy_unchanged(result_id, registered)
            self._assert_no_canonical_claim(result_id)
            return LegacyRecommendationOriginalPayload(
                result_id=result_id,
                data_path=registered.data_path,
                payload=payload,
                raw_artifact_sha256=raw_hash,
                integrity_basis=integrity_basis,
                source="registered_legacy_run",
            )

        if not allow_unindexed_legacy:
            return None

        unindexed = self._read_unindexed_legacy_file(result_id)
        if unindexed is None:
            return None
        _decoded, payload, raw_hash, integrity_basis = (
            self._decode_legacy_original_payload(
                result_id,
                unindexed,
                include_original_payload=True,
            )
        )
        if payload is None:
            raise ExecutionArtifactIntegrityError(
                "legacy original payload projection 缺少 mapping"
            )
        after = self._read_unindexed_legacy_file(result_id)
        if after is None:
            raise ExecutionArtifactIntegrityError(
                "unindexed legacy result 在讀取期間消失"
            )
        if after.data_path != unindexed.data_path or after.raw_payload != unindexed.raw_payload:
            raise ExecutionArtifactIntegrityError(
                "unindexed legacy raw bytes/path 在單次讀取前後改變"
            )
        if self._legacy_identity_exists(result_id):
            raise ExecutionArtifactIntegrityError(
                "unindexed legacy result 在讀取期間新增 SQLite registration"
            )
        self._assert_no_canonical_claim(result_id)
        return LegacyRecommendationOriginalPayload(
            result_id=result_id,
            data_path=unindexed.data_path,
            payload=payload,
            raw_artifact_sha256=raw_hash,
            integrity_basis=integrity_basis,
            source="unindexed_legacy_file",
        )

    def _assert_no_unindexed_canonical_artifact(self, result_id: str) -> None:
        """Prevent any canonical identity claim from falling back to legacy."""

        store = getattr(self._persistence, "_store", None)
        get_identity_payload_hash = getattr(store, "get_identity_payload_hash", None)
        read_artifact = getattr(store, "read_artifact", None)
        if not callable(get_identity_payload_hash) or not callable(read_artifact):
            raise ExecutionArtifactIntegrityError(
                "canonical identity metadata/artifact reader 不可用；拒絕 legacy fallback"
            )
        try:
            identity_payload_hash = get_identity_payload_hash(result_id)
        except Exception as exc:
            raise ExecutionArtifactIntegrityError(
                "無法讀取 canonical identity metadata；拒絕 legacy fallback"
            ) from exc
        if identity_payload_hash is not None:
            raise ExecutionArtifactIntegrityError(
                "canonical identity metadata claim 存在但 index 缺失；拒絕 fallback 到 legacy"
            )
        try:
            raw_payload = read_artifact(result_id)
        except Exception as exc:
            raise ExecutionArtifactIntegrityError(
                "無法判定 legacy identity 是否已有 canonical artifact；拒絕 fallback"
            ) from exc
        if raw_payload is not None:
            raise ExecutionArtifactIntegrityError(
                "canonical artifact 存在但 index 缺失；拒絕 fallback 到 legacy"
            )

    def get(self, result_id: str) -> RecommendationExecutionReadModel | None:
        try:
            record, envelope = self._persistence.read_verified_envelope(result_id)
        except KeyError:
            record = None
            envelope = None
        if record is not None and envelope is not None:
            if self._legacy_identity_exists(
                result_id,
                require_metadata_only=True,
            ):
                raise ExecutionArtifactIntegrityError(
                    "同一 result_id 同時出現在 canonical index 與 legacy runs"
                )
            return self._canonical_read_model(record, envelope)
        self._assert_no_unindexed_canonical_artifact(result_id)
        if self._legacy_reader is None:
            return None
        try:
            _require_safe_legacy_result_id(result_id)
            legacy = self._legacy_reader.get(result_id)
        except ValueError as exc:
            raise ExecutionArtifactIntegrityError(
                "legacy result_id 不是安全的單一檔名"
            ) from exc
        if legacy is None:
            return None
        return self._legacy_read_model(result_id, legacy)

    def list(self) -> tuple[RecommendationExecutionReadModel, ...]:
        canonical = self._persistence.list_verified_envelopes()
        canonical_ids = {record.metadata.result_id for record, _ in canonical}
        legacy_ids = (
            self._legacy_reader.list_result_ids()
            if self._legacy_reader is not None
            else ()
        )
        for result_id in legacy_ids:
            try:
                _require_safe_legacy_result_id(result_id)
            except ValueError as exc:
                raise ExecutionArtifactIntegrityError(
                    "legacy runs 含 Win32 不安全 result_id"
                ) from exc
        duplicate_ids = canonical_ids.intersection(legacy_ids)
        if duplicate_ids:
            raise ExecutionArtifactIntegrityError(
                "canonical index 與 legacy runs 重複 result_id，拒絕回傳部分結果"
            )
        result = [
            self._canonical_read_model(record, envelope)
            for record, envelope in canonical
        ]
        for result_id in legacy_ids:
            self._assert_no_unindexed_canonical_artifact(result_id)
            legacy = self._legacy_reader.get(result_id) if self._legacy_reader is not None else None
            if legacy is None:
                raise ExecutionArtifactIntegrityError(
                    "legacy result 在 list 讀取期間消失"
                )
            result.append(self._legacy_read_model(result_id, legacy))
        return tuple(result)


__all__ = (
    "LegacyRecommendationBytes",
    "LegacyRecommendationOriginalPayload",
    "LegacyRecommendationRawByteReader",
    "RecommendationExecutionQueries",
    "RecommendationExecutionReadModel",
    "SQLiteLegacyRecommendationRawByteReader",
)
