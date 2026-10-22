"""有界唯讀盤點；觀測到 reparse 即略過，非原子快照，不授予刪除資格。"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import ctypes
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import stat
import time


def native_path(path: Path) -> str:
    """保留輸出的普通路徑；Windows metadata API 使用 extended-length 路徑。"""
    value = os.path.abspath(path)
    if os.name != "nt" or value.startswith("\\\\?\\"):
        return value
    return "\\\\?\\UNC\\" + value[2:] if value.startswith("\\\\") else "\\\\?\\" + value


def allocated_bytes(path: Path, info: os.stat_result) -> int | None:
    """普通檔 AllocationSize；壓縮／sparse 未量測，不推導可回收量。"""
    if os.name != "nt":
        blocks = getattr(info, "st_blocks", None)
        return None if blocks is None else int(blocks) * 512
    if getattr(info, "st_file_attributes", 0) & (0x800 | 0x200):
        return None
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    class StandardInfo(ctypes.Structure):
        _fields_ = [("allocation", ctypes.c_int64), ("end_of_file", ctypes.c_int64),
                    ("links", ctypes.c_uint32), ("delete_pending", ctypes.c_ubyte),
                    ("directory", ctypes.c_ubyte)]
    create = kernel.CreateFileW
    create.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32,
                       ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p]
    create.restype = ctypes.c_void_p
    query = kernel.GetFileInformationByHandleEx
    query.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]
    query.restype = ctypes.c_int
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel.CloseHandle.restype = ctypes.c_int
    handle = create(native_path(path), 0, 7, None, 3, 0x00200000, None)
    if handle == ctypes.c_void_p(-1).value:
        return None
    try:
        result = StandardInfo()
        if not query(handle, 1, ctypes.byref(result), ctypes.sizeof(result)):
            return None
        return int(result.allocation)
    finally:
        kernel.CloseHandle(handle)


def is_reparse(info: os.stat_result) -> bool:
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & 0x400
    )


def inventory(roots: list[Path], *, max_files: int = 350_000,
              max_depth: int = 32, max_seconds: int = 240,
              top_n: int = 80, max_entries: int = 1_000_000) -> dict:
    if min(max_files, max_seconds, top_n, max_entries) < 1 or max_depth < 0:
        raise ValueError("盤點預算必須有效")
    started = time.monotonic()
    seen: set[tuple[int, int]] = set()
    seen_roots: set[str] = set()
    groups: dict[str, Counter] = defaultdict(Counter)
    extensions: dict[str, Counter] = defaultdict(Counter)
    large: list[dict] = []
    links: list[dict] = []
    errors: list[dict] = []
    omissions: list[dict] = []
    file_count = 0
    entry_count = 0

    def omitted(path: Path, reason: str) -> None:
        omissions.append({"path": str(path), "reason": reason})

    def scan(directory: Path, root: Path, depth: int) -> None:
        nonlocal file_count, entry_count
        if time.monotonic() - started >= max_seconds:
            omitted(directory, "time_budget")
            return
        if file_count >= max_files or entry_count >= max_entries:
            omitted(directory, "file_or_entry_budget")
            return
        if depth > max_depth:
            omitted(directory, "depth_budget")
            return
        try:
            if is_reparse(os.lstat(native_path(directory))):
                links.append({"path": str(directory), "kind": "directory_changed_to_reparse"})
                return
            with os.scandir(native_path(directory)) as entries:
                for entry in entries:
                    if (file_count >= max_files or entry_count >= max_entries
                            or time.monotonic() - started >= max_seconds):
                        omitted(directory, "file_entry_or_time_budget_remaining_entries")
                        break
                    entry_count += 1
                    path = directory / entry.name
                    try:
                        # Windows DirEntry.stat 的身分欄位可能為零，須向檔案系統另查。
                        info = os.stat(native_path(path), follow_symlinks=False)
                        if is_reparse(info):
                            links.append({"path": str(path), "kind": "reparse_skipped"})
                            continue
                        if stat.S_ISDIR(info.st_mode):
                            scan(path, root, depth + 1)
                            continue
                        if not stat.S_ISREG(info.st_mode):
                            continue
                        file_count += 1
                        identity = (info.st_dev, info.st_ino)
                        known_identity = bool(info.st_ino)
                        duplicate = known_identity and identity in seen
                        if known_identity:
                            seen.add(identity)
                        allocated = None if duplicate else allocated_bytes(path, info)
                        parts = path.relative_to(root).parts
                        group = str(root / parts[0]) if len(parts) > 1 else str(root)
                        values = Counter(files=1, logical_bytes=info.st_size,
                                         unique_files=int(known_identity and not duplicate),
                                         duplicate_identity_paths=int(duplicate),
                                         unknown_identity_files=int(not known_identity),
                                         hardlinked_paths=int(info.st_nlink > 1),
                                         unique_logical_bytes=info.st_size if known_identity and not duplicate else 0,
                                         allocated_bytes=(allocated or 0) if known_identity else 0,
                                         unknown_allocation_files=int(allocated is None and not duplicate))
                        groups[group].update(values)
                        extensions[path.suffix.lower() or "<none>"].update(values)
                        record = {"path": str(path), "logical_bytes": info.st_size,
                                  "allocated_bytes": allocated,
                                  "identity": [info.st_dev, info.st_ino],
                                  "nlink": info.st_nlink, "mtime_ns": info.st_mtime_ns,
                                  "duplicate_identity": duplicate,
                                  "classification": "REVIEW_REQUIRED",
                                  "reclaimable_bytes": None,
                                  "reference_check": "NOT_RUN", "open_handle_check": "UNKNOWN"}
                        large.append(record)
                        if len(large) > top_n * 2:
                            large.sort(key=lambda item: item["logical_bytes"], reverse=True)
                            del large[top_n:]
                    except OSError as exc:
                        errors.append({"path": str(path), "error": type(exc).__name__})
        except OSError as exc:
            errors.append({"path": str(directory), "error": type(exc).__name__})

    root_reports = []
    for value in roots:
        root = Path(os.path.abspath(value))
        key = os.path.normcase(str(root))
        if key in seen_roots:
            omitted(root, "duplicate_root")
            continue
        seen_roots.add(key)
        try:
            blocked = next((parent for parent in reversed(root.parents)
                            if is_reparse(os.lstat(native_path(parent)))), None)
            if blocked is not None:
                links.append({"path": str(root), "ancestor": str(blocked),
                              "kind": "root_reparse_ancestor_rejected"})
                continue
            info = os.lstat(native_path(root))
            if is_reparse(info):
                links.append({"path": str(root), "kind": "root_reparse_rejected"})
                continue
            if not stat.S_ISDIR(info.st_mode):
                omitted(root, "not_directory")
                continue
            root_reports.append(str(root))
            scan(root, root, 0)
        except OSError as exc:
            errors.append({"path": str(root), "error": type(exc).__name__})
    large.sort(key=lambda item: item["logical_bytes"], reverse=True)
    totals = Counter()
    for values in groups.values():
        totals.update(values)
    return {"schema_version": "baldr-storage-lifecycle.v1",
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "duration_seconds": round(time.monotonic() - started, 3),
            "roots": root_reports, "budgets": {"max_files": max_files, "max_entries": max_entries,
                "max_depth": max_depth, "max_seconds": max_seconds},
            "entries_observed": entry_count,
            "complete_identity": not totals["unknown_identity_files"],
            "complete_allocation": not totals["unknown_allocation_files"] and not totals["unknown_identity_files"],
            "complete": not errors and not omissions and not links
                and not totals["unknown_identity_files"] and not totals["unknown_allocation_files"],
            "totals": dict(totals),
            "groups": [{"path": path, **dict(values)} for path, values in
                       sorted(groups.items(), key=lambda pair: pair[1]["allocated_bytes"], reverse=True)],
            "extensions": {name: dict(values) for name, values in extensions.items()},
            "largest_files": large[:top_n], "reparse_points": links,
            "errors": errors, "omissions": omissions,
            "safety": {"read_only": True, "hash_content_read": False,
                       "deletion_allowed": False, "verified_reclaimable_bytes": 0,
                       "allocation_is_not_reclaimable": True,
                       "allocation_method": "ordinary_FILE_STANDARD_INFO.AllocationSize_compressed_sparse_unknown",
                       "concurrent_path_replacement_not_atomic": True,
                       "traversal_race_protected": False,
                       "point_in_time_snapshot": False}}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, action="append", required=True)
    parser.add_argument("--max-files", type=int, default=350_000)
    parser.add_argument("--max-entries", type=int, default=1_000_000)
    parser.add_argument("--max-depth", type=int, default=32)
    parser.add_argument("--max-seconds", type=int, default=240)
    parser.add_argument("--top-n", type=int, default=80)
    args = parser.parse_args()
    print(json.dumps(inventory(args.root, max_files=args.max_files, max_entries=args.max_entries, max_depth=args.max_depth,
                               max_seconds=args.max_seconds, top_n=args.top_n),
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
