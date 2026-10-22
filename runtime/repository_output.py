"""驗證由 Baldr owner 配置的 repository ``output`` 邊界。"""

from __future__ import annotations

import ctypes
import os
from pathlib import Path
import stat
from ctypes import wintypes


IO_REPARSE_TAG_MOUNT_POINT = 0xA0000003
_FILE_ATTRIBUTE_REPARSE_POINT = 0x0400
_FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
_FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
_OPEN_EXISTING = 3
_FSCTL_GET_REPARSE_POINT = 0x000900A8


class RepositoryOutputBoundaryError(ValueError):
    """Repository output 路徑穿越未核准的別名或邊界。"""


def validate_repository_root(repository_root: os.PathLike[str] | str) -> Path:
    """拒絕 reparse 別名後，回傳已存在的 repository 目錄。"""

    root = _absolute_path(repository_root, "repository root")
    _assert_no_reparse_aliases(root)
    try:
        info = root.lstat()
    except OSError as error:
        raise RepositoryOutputBoundaryError(
            f"repository root cannot be inspected: {root}"
        ) from error
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise RepositoryOutputBoundaryError("repository root must be a regular directory")
    return root.resolve(strict=True)


def resolve_repository_output_root(
    repository_root: os.PathLike[str] | str,
) -> Path:
    """解析 ``<repository>/output``，只允許該路徑本身的 mount-point junction。"""

    repository = validate_repository_root(repository_root)
    logical_output = repository / "output"
    try:
        info = logical_output.lstat()
    except FileNotFoundError:
        return logical_output
    except OSError as error:
        raise RepositoryOutputBoundaryError(
            f"repository output cannot be inspected: {logical_output}"
        ) from error

    if _is_reparse_or_link(logical_output, info):
        _validate_output_junction(logical_output, info)
        return _junction_target(logical_output).resolve(strict=True)
    if not stat.S_ISDIR(info.st_mode):
        raise RepositoryOutputBoundaryError("repository output must be a directory")
    return logical_output.resolve(strict=True)


def resolve_repository_output_path(
    path: os.PathLike[str] | str,
    *,
    repository_root: os.PathLike[str] | str,
) -> Path:
    """解析 owner 配置的 output 根目錄下路徑，並拒絕內層別名。"""

    repository = validate_repository_root(repository_root)
    logical_output = repository / "output"
    output_root = resolve_repository_output_root(repository)
    candidate = _absolute_path(path, "repository output path")
    try:
        relative = candidate.relative_to(logical_output)
    except ValueError as error:
        raise RepositoryOutputBoundaryError(
            "path must be lexically inside the repository output root"
        ) from error
    if any(part in (".", "..") for part in relative.parts):
        raise RepositoryOutputBoundaryError("repository output path cannot traverse parents")

    _assert_no_reparse_aliases(candidate, allowed_junction=logical_output)
    resolved = candidate.resolve(strict=False)
    if not _is_same_or_child(resolved, output_root):
        raise RepositoryOutputBoundaryError(
            "repository output path escaped its resolved storage boundary"
        )
    return resolved


def is_repository_output_path(
    path: os.PathLike[str] | str,
    *,
    repository_root: os.PathLike[str] | str,
) -> bool:
    """判斷絕對詞法路徑是否位於 repository/output 之下或等於該路徑。"""

    candidate = _absolute_path(path, "repository path")
    repository = _absolute_path(repository_root, "repository root")
    try:
        candidate.relative_to(repository / "output")
    except ValueError:
        return False
    return True


def _absolute_path(path: os.PathLike[str] | str, label: str) -> Path:
    try:
        candidate = Path(path).expanduser()
    except (TypeError, ValueError, OSError) as error:
        raise RepositoryOutputBoundaryError(f"{label} is invalid") from error
    if not candidate.is_absolute():
        raise RepositoryOutputBoundaryError(f"{label} must be absolute")
    if any(part == ".." for part in candidate.parts):
        raise RepositoryOutputBoundaryError(f"{label} cannot contain '..'")
    return Path(os.path.abspath(candidate))


def _assert_no_reparse_aliases(
    path: Path,
    *,
    allowed_junction: Path | None = None,
) -> None:
    parts = path.parts
    if not parts:
        raise RepositoryOutputBoundaryError("path is empty")
    current = Path(parts[0])
    for part in parts[1:]:
        current = current / part
        try:
            info = current.lstat()
        except FileNotFoundError:
            break
        except (OSError, ValueError) as error:
            raise RepositoryOutputBoundaryError(
                f"path component cannot be inspected: {current}"
            ) from error
        if _is_reparse_or_link(current, info):
            if allowed_junction is None or not _same_path(current, allowed_junction):
                raise RepositoryOutputBoundaryError(
                    f"path cannot traverse a symlink or junction: {current}"
                )
            _validate_output_junction(current, info)


def _validate_output_junction(path: Path, info: os.stat_result) -> None:
    if os.name != "nt" or not (
        getattr(info, "st_file_attributes", 0) & _FILE_ATTRIBUTE_REPARSE_POINT
    ):
        raise RepositoryOutputBoundaryError(
            "repository output alias must be a Windows mount-point junction"
        )
    if _read_windows_reparse_tag(path) != IO_REPARSE_TAG_MOUNT_POINT:
        raise RepositoryOutputBoundaryError(
            "repository output reparse tag must be IO_REPARSE_TAG_MOUNT_POINT"
        )
    target = _junction_target(path)
    _assert_no_reparse_aliases(target)
    try:
        target_info = target.lstat()
    except OSError as error:
        raise RepositoryOutputBoundaryError(
            "repository output junction target must exist"
        ) from error
    if _is_reparse_or_link(target, target_info) or not stat.S_ISDIR(target_info.st_mode):
        raise RepositoryOutputBoundaryError(
            "repository output junction target must be a regular directory"
        )


def _junction_target(path: Path) -> Path:
    try:
        raw_target = os.readlink(path)
    except (OSError, ValueError) as error:
        raise RepositoryOutputBoundaryError(
            "repository output junction target cannot be read"
        ) from error
    if raw_target.startswith("\\??\\UNC\\"):
        raw_target = "\\\\" + raw_target[8:]
    elif raw_target.startswith("\\??\\"):
        raw_target = raw_target[4:]
    elif raw_target.startswith("\\\\?\\UNC\\"):
        raw_target = "\\\\" + raw_target[8:]
    elif raw_target.startswith("\\\\?\\"):
        raw_target = raw_target[4:]
    target = Path(raw_target)
    if not target.is_absolute() or any(part == ".." for part in target.parts):
        raise RepositoryOutputBoundaryError(
            "repository output junction target must be an absolute canonical path"
        )
    return Path(os.path.abspath(target))


def _read_windows_reparse_tag(path: Path) -> int:
    if os.name != "nt":
        raise RepositoryOutputBoundaryError("Windows reparse tags are unavailable")
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    create_file.restype = wintypes.HANDLE
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = [wintypes.HANDLE]
    close_handle.restype = wintypes.BOOL
    device_io = kernel32.DeviceIoControl
    device_io.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
        wintypes.LPVOID,
    ]
    device_io.restype = wintypes.BOOL
    handle = create_file(
        str(path),
        0x0080,
        0x1 | 0x2 | 0x4,
        None,
        _OPEN_EXISTING,
        _FILE_FLAG_BACKUP_SEMANTICS | _FILE_FLAG_OPEN_REPARSE_POINT,
        None,
    )
    invalid_handle = ctypes.c_void_p(-1).value
    if handle == invalid_handle:
        raise RepositoryOutputBoundaryError(
            "repository output junction cannot be opened for reparse inspection"
        )
    try:
        buffer = ctypes.create_string_buffer(16 * 1024)
        returned = wintypes.DWORD()
        if not device_io(
            handle,
            _FSCTL_GET_REPARSE_POINT,
            None,
            0,
            buffer,
            len(buffer),
            ctypes.byref(returned),
            None,
        ) or returned.value < 4:
            raise RepositoryOutputBoundaryError(
                "repository output junction reparse tag cannot be read"
            )
        return int.from_bytes(buffer.raw[:4], "little")
    finally:
        close_handle(handle)


def _is_reparse_or_link(path: Path, info: os.stat_result) -> bool:
    attributes = getattr(info, "st_file_attributes", 0)
    is_junction = getattr(path, "is_junction", None)
    return (
        stat.S_ISLNK(info.st_mode)
        or bool(attributes & _FILE_ATTRIBUTE_REPARSE_POINT)
        or (callable(is_junction) and is_junction())
    )


def _is_same_or_child(candidate: Path, parent: Path) -> bool:
    try:
        candidate.relative_to(parent)
    except ValueError:
        return False
    return True


def _same_path(left: Path, right: Path) -> bool:
    return os.path.normcase(os.path.normpath(str(left))) == os.path.normcase(
        os.path.normpath(str(right))
    )
