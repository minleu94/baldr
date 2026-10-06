"""Fail-closed boundary for isolated ML research artifacts.

The configured root is the only write target. Existing repository-local research
artifacts remain readable by their exact pinned paths for backward compatibility.
This module validates paths only and never creates directories or files.
"""

from __future__ import annotations

import ctypes
import json
import os
from pathlib import Path
import stat
from typing import Any, Literal, Sequence

from data_module.config import TWStockConfig


REPO_ROOT = Path(__file__).resolve().parents[1]
LEGACY_ML_RESEARCH_ROOT = REPO_ROOT / "output" / "ml_research"
# Kept as a compatibility name for callers that construct legacy pinned paths.
APPROVED_ML_RESEARCH_ROOT = LEGACY_ML_RESEARCH_ROOT
ML_RESEARCH_STORAGE_CONFIG_NAME = "ml_research_storage.json"
ML_RESEARCH_STORAGE_SCHEMA_VERSION = "ml-research-storage.v1"
_MAX_STORAGE_CONFIG_BYTES = 16 * 1024


class MLResearchOutputBoundaryError(ValueError):
    """A research path or storage-root configuration violates the boundary."""


def get_ml_research_root(*, repository_root: Path | None = None) -> Path:
    """Return the active root for new research writes.

    If ``<repository>/output/ml_research_storage.json`` is absent, the legacy
    repository-local root remains active. If that configuration exists but is
    malformed or unsafe, resolution fails closed instead of silently falling
    back to a different root.

    The function only validates and resolves paths; it never creates them.
    """

    repository = _repository_root(repository_root)
    legacy_root = _legacy_root(repository)
    configured = _read_active_root_config(repository)
    active_root = legacy_root if configured is None else configured
    _validate_root_safety(
        active_root,
        repository_root=repository,
        legacy_root=legacy_root,
        extra_forbidden_roots=(),
        reject_legacy_overlap=configured is not None,
    )
    return active_root


def resolve_ml_research_output_path(
    path: os.PathLike[str] | str,
    *,
    repository_root: Path | None = None,
    extra_forbidden_roots: Sequence[Path] = (),
    access: Literal["read", "write"] = "read",
) -> Path:
    """Resolve a path under an approved research root.

    ``access="read"`` accepts the legacy C/repository root and the configured
    active root. ``access="write"`` accepts only the active root. The default
    is deliberately read-only so old absolute C pins remain readable; every
    producer must request write access explicitly.

    Relative paths are rooted at ``repository_root``. No directory is created.
    """

    if access not in ("read", "write"):
        raise MLResearchOutputBoundaryError("access must be 'read' or 'write'")
    repository = _repository_root(repository_root)
    legacy_root = _legacy_root(repository)
    configured = _read_active_root_config(repository)
    active_root = legacy_root if configured is None else configured
    _validate_root_safety(
        active_root,
        repository_root=repository,
        legacy_root=legacy_root,
        extra_forbidden_roots=extra_forbidden_roots,
        reject_legacy_overlap=configured is not None,
    )

    candidate = _absolute_candidate(path, base=repository, label="research output path")
    candidate_resolved = candidate.resolve(strict=False)
    allowed_roots = (active_root,) if access == "write" else (legacy_root, active_root)
    if not any(_is_same_or_child(candidate_resolved, root) for root in allowed_roots):
        if access == "write":
            raise MLResearchOutputBoundaryError(
                "research writes must be inside the configured active ML research root"
            )
        raise MLResearchOutputBoundaryError(
            "research reads must be inside the legacy or configured active ML research root"
        )

    for forbidden in _configured_forbidden_roots(repository, extra_forbidden_roots):
        forbidden_path = _absolute_candidate(
            forbidden, base=repository, label="protected root"
        ).resolve(strict=False)
        if _paths_overlap(candidate_resolved, forbidden_path):
            raise MLResearchOutputBoundaryError(
                f"ML research path overlaps a protected root: {forbidden_path}"
            )
    return candidate_resolved


def _repository_root(repository_root: Path | None) -> Path:
    root = Path(REPO_ROOT if repository_root is None else repository_root).expanduser()
    if not root.is_absolute():
        raise MLResearchOutputBoundaryError("repository_root must be absolute")
    raw_root = Path(os.path.abspath(root))
    _assert_no_reparse_aliases(raw_root)
    return raw_root.resolve(strict=False)


def _legacy_root(repository_root: Path) -> Path:
    candidate = repository_root / "output" / "ml_research"
    _assert_no_reparse_aliases(candidate)
    return candidate.resolve(strict=False)


def _read_active_root_config(repository_root: Path) -> Path | None:
    config_path = repository_root / "output" / ML_RESEARCH_STORAGE_CONFIG_NAME
    _assert_no_reparse_aliases(config_path)
    try:
        info = config_path.lstat()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise MLResearchOutputBoundaryError(
            "ML research storage configuration cannot be inspected"
        ) from exc

    if _is_reparse_or_link(config_path, info) or not stat.S_ISREG(info.st_mode):
        raise MLResearchOutputBoundaryError(
            "ML research storage configuration must be a regular non-reparse file"
        )
    if info.st_size < 0 or info.st_size > _MAX_STORAGE_CONFIG_BYTES:
        raise MLResearchOutputBoundaryError(
            "ML research storage configuration exceeds its bounded size"
        )

    raw = _read_bounded_regular_file_no_follow(
        config_path, maximum_bytes=_MAX_STORAGE_CONFIG_BYTES
    )
    try:
        payload = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise MLResearchOutputBoundaryError(
            "ML research storage configuration is not valid UTF-8 JSON"
        ) from exc
    if not isinstance(payload, dict) or set(payload) != {"schema_version", "active_root"}:
        raise MLResearchOutputBoundaryError(
            "ML research storage configuration has an unexpected schema"
        )
    if payload.get("schema_version") != ML_RESEARCH_STORAGE_SCHEMA_VERSION:
        raise MLResearchOutputBoundaryError(
            "ML research storage configuration schema version is unsupported"
        )
    active_value = payload.get("active_root")
    if (
        not isinstance(active_value, str)
        or not active_value
        or active_value != active_value.strip()
    ):
        raise MLResearchOutputBoundaryError(
            "ML research storage active_root must be a non-empty absolute path"
        )
    if not Path(active_value).is_absolute():
        raise MLResearchOutputBoundaryError(
            "ML research storage active_root must be an absolute path"
        )
    active_path = _absolute_candidate(
        active_value, base=repository_root, label="active_root"
    )
    return active_path.resolve(strict=False)


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON constant: {value}")


def _read_bounded_regular_file_no_follow(path: Path, *, maximum_bytes: int) -> bytes:
    if os.name == "nt":
        return _read_windows_regular_file_no_follow(path, maximum_bytes=maximum_bytes)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise MLResearchOutputBoundaryError(
            "ML research storage configuration could not be opened without following links"
        ) from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_size > maximum_bytes:
            raise MLResearchOutputBoundaryError(
                "ML research storage configuration is not a bounded regular file"
            )
        chunks: list[bytes] = []
        remaining = maximum_bytes + 1
        while remaining > 0:
            chunk = os.read(descriptor, min(remaining, 4096))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        after = os.fstat(descriptor)
        raw = b"".join(chunks)
        if (
            len(raw) > maximum_bytes
            or before.st_size != after.st_size
            or before.st_mtime_ns != after.st_mtime_ns
            or len(raw) != after.st_size
        ):
            raise MLResearchOutputBoundaryError(
                "ML research storage configuration changed or exceeded its read bound"
            )
        return raw
    finally:
        os.close(descriptor)


def _read_windows_regular_file_no_follow(path: Path, *, maximum_bytes: int) -> bytes:
    """Read the final path component through a handle opened as the reparse point."""

    import msvcrt
    from ctypes import wintypes

    class _FileTime(ctypes.Structure):
        _fields_ = [("low", wintypes.DWORD), ("high", wintypes.DWORD)]

    class _ByHandleFileInformation(ctypes.Structure):
        _fields_ = [
            ("attributes", wintypes.DWORD),
            ("creation_time", _FileTime),
            ("last_access_time", _FileTime),
            ("last_write_time", _FileTime),
            ("volume_serial_number", wintypes.DWORD),
            ("file_size_high", wintypes.DWORD),
            ("file_size_low", wintypes.DWORD),
            ("number_of_links", wintypes.DWORD),
            ("file_index_high", wintypes.DWORD),
            ("file_index_low", wintypes.DWORD),
        ]

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
    get_info = kernel32.GetFileInformationByHandle
    get_info.argtypes = [wintypes.HANDLE, ctypes.POINTER(_ByHandleFileInformation)]
    get_info.restype = wintypes.BOOL
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = [wintypes.HANDLE]
    close_handle.restype = wintypes.BOOL

    generic_read = 0x80000000
    share_read = 0x00000001
    open_existing = 3
    file_flag_open_reparse_point = 0x00200000
    file_flag_sequential_scan = 0x08000000
    handle = create_file(
        str(path),
        generic_read,
        share_read,
        None,
        open_existing,
        file_flag_open_reparse_point | file_flag_sequential_scan,
        None,
    )
    invalid_handle = ctypes.c_void_p(-1).value
    if handle in (None, invalid_handle):
        raise MLResearchOutputBoundaryError(
            "ML research storage configuration could not be opened without following links"
        )

    owned_handle = True
    try:
        information = _ByHandleFileInformation()
        if not get_info(handle, ctypes.byref(information)):
            raise MLResearchOutputBoundaryError(
                "ML research storage configuration handle could not be inspected"
            )
        reparse_attribute = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        directory_attribute = getattr(stat, "FILE_ATTRIBUTE_DIRECTORY", 0x10)
        file_size = (information.file_size_high << 32) | information.file_size_low
        if information.attributes & reparse_attribute:
            raise MLResearchOutputBoundaryError(
                "ML research storage configuration cannot be a reparse point"
            )
        if information.attributes & directory_attribute or file_size > maximum_bytes:
            raise MLResearchOutputBoundaryError(
                "ML research storage configuration is not a bounded regular file"
            )

        descriptor = msvcrt.open_osfhandle(
            int(handle), os.O_RDONLY | getattr(os, "O_BINARY", 0)
        )
        owned_handle = False
        try:
            with os.fdopen(descriptor, "rb", closefd=True) as stream:
                raw = stream.read(maximum_bytes + 1)
                after = os.fstat(stream.fileno())
            if len(raw) > maximum_bytes or after.st_size != file_size or len(raw) != file_size:
                raise MLResearchOutputBoundaryError(
                    "ML research storage configuration changed or exceeded its read bound"
                )
            return raw
        except OSError as exc:
            raise MLResearchOutputBoundaryError(
                "ML research storage configuration could not be read safely"
            ) from exc
    finally:
        if owned_handle:
            close_handle(handle)


def _absolute_candidate(
    path: os.PathLike[str] | str,
    *,
    base: Path,
    label: str,
) -> Path:
    try:
        candidate = Path(path).expanduser()
    except (TypeError, ValueError, OSError) as exc:
        raise MLResearchOutputBoundaryError(f"{label} is not a valid path") from exc
    if any(part == ".." for part in candidate.parts):
        raise MLResearchOutputBoundaryError(f"{label} cannot contain '..'")
    raw_text = str(candidate)
    if os.name == "nt" and raw_text.startswith(("\\\\?\\", "\\\\.\\")):
        raise MLResearchOutputBoundaryError(f"{label} cannot use a Windows device namespace")
    if not candidate.is_absolute():
        candidate = base / candidate
    candidate = Path(os.path.abspath(candidate))
    _assert_no_reparse_aliases(candidate)
    return candidate


def _validate_root_safety(
    active_root: Path,
    *,
    repository_root: Path,
    legacy_root: Path,
    extra_forbidden_roots: Sequence[Path],
    reject_legacy_overlap: bool,
) -> None:
    _assert_no_reparse_aliases(active_root)
    if reject_legacy_overlap and _paths_overlap(active_root, legacy_root):
        raise MLResearchOutputBoundaryError(
            "configured active_root must be separate from the legacy ML research root"
        )
    if reject_legacy_overlap and _paths_overlap(active_root, repository_root):
        raise MLResearchOutputBoundaryError(
            "configured active_root must be outside the repository tree"
        )
    for forbidden in _configured_forbidden_roots(
        repository_root, extra_forbidden_roots
    ):
        forbidden_resolved = _absolute_candidate(
            forbidden, base=repository_root, label="protected root"
        ).resolve(strict=False)
        if _paths_overlap(active_root, forbidden_resolved):
            raise MLResearchOutputBoundaryError(
                f"configured ML research root overlaps a protected root: {forbidden_resolved}"
            )


def _configured_forbidden_roots(
    repository_root: Path,
    extra_forbidden_roots: Sequence[Path],
) -> tuple[Path, ...]:
    data_field = TWStockConfig.__dataclass_fields__.get("data_root")
    output_field = TWStockConfig.__dataclass_fields__.get("output_root")
    if (
        data_field is None
        or output_field is None
        or not callable(data_field.default_factory)
        or not callable(output_field.default_factory)
    ):
        raise MLResearchOutputBoundaryError(
            "TWStockConfig data/output roots cannot be resolved without side effects"
        )
    data_root_value = data_field.default_factory()
    output_root_value = output_field.default_factory()
    if not isinstance(data_root_value, (str, os.PathLike)) or not isinstance(
        output_root_value, (str, os.PathLike)
    ):
        raise MLResearchOutputBoundaryError("TWStockConfig roots have invalid types")

    data_root = Path(data_root_value)
    output_root = Path(output_root_value)
    roots = [
        data_root,
        output_root / "release_v4",
        data_root.parent / "FA_Data_Shadow",
        data_root.parent / "FA_Data_Shadow_BankTaiwan",
        repository_root / "output" / "release_v4",
        repository_root / "output" / "v4_ml_derived_h5_20260907_real_v2",
    ]
    for env_name in (
        "RECOMMENDATION_LEARNING_OUTPUT_ROOT",
        "BANKTAIWAN_RECOMMENDATION_LEARNING_OUTPUT_ROOT",
    ):
        configured_learning_root = os.environ.get(env_name)
        if configured_learning_root:
            roots.append(Path(configured_learning_root))
    roots.extend(Path(item) for item in extra_forbidden_roots)
    return tuple(roots)


def _is_same_or_child(candidate: Path, parent: Path) -> bool:
    candidate_key = _path_key(candidate)
    parent_key = _path_key(parent)
    return candidate_key == parent_key or candidate_key.startswith(
        parent_key.rstrip("\\/") + os.sep.casefold()
    )


def _paths_overlap(left: Path, right: Path) -> bool:
    return _is_same_or_child(left, right) or _is_same_or_child(right, left)


def _path_key(path: Path) -> str:
    resolved = os.path.normpath(str(path.resolve(strict=False)))
    return os.path.normcase(resolved).casefold()


def _is_reparse_or_link(path: Path, info: os.stat_result) -> bool:
    attributes = getattr(info, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    is_junction = getattr(path, "is_junction", None)
    return (
        stat.S_ISLNK(info.st_mode)
        or bool(attributes & reparse_flag)
        or (callable(is_junction) and is_junction())
    )


def _assert_no_reparse_aliases(path: Path) -> None:
    parts = path.parts
    if not parts:
        raise MLResearchOutputBoundaryError("research output path is empty")
    current = Path(parts[0])
    for part in parts[1:]:
        current = current / part
        try:
            info = current.lstat()
        except FileNotFoundError:
            break
        except OSError as exc:
            raise MLResearchOutputBoundaryError(
                f"research output path component cannot be inspected: {current}"
            ) from exc
        if _is_reparse_or_link(current, info):
            raise MLResearchOutputBoundaryError(
                f"research output path cannot traverse a symlink or junction: {current}"
            )
