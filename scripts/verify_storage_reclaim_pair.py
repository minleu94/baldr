"""唯讀驗證兩份 runtime 樹；只產生還原證據，不授予刪除或 SAFE_RECLAIM。"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import time

ROOT = Path(__file__).absolute().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.audit_storage_lifecycle import allocated_bytes, is_reparse, native_path


def fingerprint(info: os.stat_result) -> tuple[int, int, int, int, int]:
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_nlink


def exclusive_probe(path: Path) -> int | None:
    """不寫入、不刪除；share=0 的短暫 read handle 失敗時保留 Win32 錯誤。"""
    if os.name != "nt":
        return -1
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.CreateFileW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32,
        ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p]
    api.CreateFileW.restype = ctypes.c_void_p
    api.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = api.CreateFileW(native_path(path), 1, 0, None, 3, 0x00200000, None)
    if handle == ctypes.c_void_p(-1).value:
        return ctypes.get_last_error()
    api.CloseHandle(handle)
    return None


def alternate_streams(path: Path) -> list[str] | None:
    """只查 stream 名稱；未能查核時不能宣稱完整還原。"""
    if os.name != "nt":
        return []
    class StreamData(ctypes.Structure):
        _fields_ = [("size", ctypes.c_int64), ("name", ctypes.c_wchar * 296)]
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.FindFirstStreamW.argtypes = [ctypes.c_wchar_p, ctypes.c_int,
        ctypes.POINTER(StreamData), ctypes.c_uint32]
    api.FindFirstStreamW.restype = ctypes.c_void_p
    api.FindNextStreamW.argtypes = [ctypes.c_void_p, ctypes.POINTER(StreamData)]
    api.FindNextStreamW.restype = ctypes.c_int
    api.FindClose.argtypes = [ctypes.c_void_p]
    data = StreamData()
    handle = api.FindFirstStreamW(native_path(path), 0, ctypes.byref(data), 0)
    if handle == ctypes.c_void_p(-1).value:
        return [] if ctypes.get_last_error() == 38 else None
    streams = []
    try:
        while True:
            if data.name != "::$DATA":
                streams.append(data.name)
            if not api.FindNextStreamW(handle, ctypes.byref(data)):
                return streams if ctypes.get_last_error() == 38 else None
    finally:
        api.FindClose(handle)


def resource_users(paths: list[Path]) -> dict:
    """以一批具名檔查 Restart Manager；只建暫時session，不關閉或重啟程式。"""
    if os.name != "nt" or not paths or len(paths) > 15000:
        return {"complete": False, "reason": "unsupported_or_invalid_budget"}
    class FileTime(ctypes.Structure):
        _fields_ = [("low", ctypes.c_uint32), ("high", ctypes.c_uint32)]
    class UniqueProcess(ctypes.Structure):
        _fields_ = [("pid", ctypes.c_uint32), ("started", FileTime)]
    class ProcessInfo(ctypes.Structure):
        _fields_ = [("process", UniqueProcess), ("app", ctypes.c_wchar * 256),
                    ("service", ctypes.c_wchar * 64), ("kind", ctypes.c_int),
                    ("status", ctypes.c_uint32), ("session", ctypes.c_uint32),
                    ("restartable", ctypes.c_int)]
    api = ctypes.WinDLL("Rstrtmgr", use_last_error=True)
    uint = ctypes.c_uint32
    api.RmStartSession.argtypes = [ctypes.POINTER(uint), uint, ctypes.c_wchar_p]
    api.RmRegisterResources.argtypes = [uint, uint, ctypes.POINTER(ctypes.c_wchar_p),
                                      uint, ctypes.c_void_p, uint, ctypes.c_void_p]
    api.RmGetList.argtypes = [uint, ctypes.POINTER(uint), ctypes.POINTER(uint),
                            ctypes.POINTER(ProcessInfo), ctypes.POINTER(uint)]
    api.RmEndSession.argtypes = [uint]
    for name in ("RmStartSession", "RmRegisterResources", "RmGetList", "RmEndSession"):
        getattr(api, name).restype = uint
    session = uint()
    key = ctypes.create_unicode_buffer(33)
    result = {"complete": False, "registered_file_count": len(paths), "users": []}
    status = api.RmStartSession(ctypes.byref(session), 0, key)
    if status:
        return {**result, "start_error": int(status)}
    try:
        names = (ctypes.c_wchar_p * len(paths))(*(str(p) for p in paths))
        status = api.RmRegisterResources(session, len(paths), names, 0, None, 0, None)
        if status:
            return {**result, "register_error": int(status)}
        needed, count, reboot = uint(), uint(256), uint()
        values = (ProcessInfo * 256)()
        status = api.RmGetList(session, ctypes.byref(needed), ctypes.byref(count),
                               values, ctypes.byref(reboot))
        result.update(query_error=int(status), needed=int(needed.value),
                      reboot_reasons=int(reboot.value))
        if status == 0:
            result["complete"] = True
            result["users"] = [{"pid": int(v.process.pid),
                "started_filetime": (v.process.started.high << 32) | v.process.started.low,
                "app": v.app, "service": v.service} for v in values[:count.value]]
        return result
    finally:
        status = api.RmEndSession(session)
        result["session_closed"] = status == 0
        if status:
            result["complete"] = False


def verify_pair(candidate: Path, retained: Path, *, max_files: int = 12000,
                max_hash_bytes: int = 3 * 1024**3,
                max_seconds: int = 180, max_depth: int = 32) -> dict:
    if min(max_files, max_hash_bytes, max_seconds) < 1 or max_depth < 0:
        raise ValueError("驗證預算必須為正")
    roots = [Path(os.path.abspath(candidate)), Path(os.path.abspath(retained))]
    started = time.monotonic()
    errors = []
    files: list[dict[str, tuple[Path, os.stat_result]]] = []
    directories: list[set[str]] = []
    records = []
    bytes_hashed = 0
    allocation = 0

    def budget() -> None:
        if time.monotonic() - started > max_seconds:
            raise ValueError("time_budget")

    def tree(root: Path) -> tuple[dict, set]:
        index = {}
        folders = set()
        def descend(path: Path, depth: int = 0) -> None:
            budget()
            if depth > max_depth:
                raise ValueError("depth_budget:" + str(path))
            if is_reparse(os.lstat(native_path(path))):
                raise ValueError("reparse:" + str(path))
            streams = alternate_streams(path)
            if streams is None or streams:
                raise ValueError("directory_streams_unknown_or_present:" + str(path))
            with os.scandir(native_path(path)) as entries:
                for entry in entries:
                    budget()
                    item = path / entry.name
                    info = os.stat(native_path(item), follow_symlinks=False)
                    if is_reparse(info):
                        raise ValueError("reparse:" + str(item))
                    relative = item.relative_to(root).as_posix()
                    if stat.S_ISDIR(info.st_mode):
                        folders.add(relative)
                        if len(folders) > max_files:
                            raise ValueError("directory_budget")
                        descend(item, depth + 1)
                    elif stat.S_ISREG(info.st_mode):
                        if getattr(info, "st_file_attributes", 0) & 0x4000:
                            raise ValueError("encrypted_file:" + str(item))
                        index[relative] = (item, info)
                        if len(index) > max_files:
                            raise ValueError("file_budget")
                    else:
                        raise ValueError("not_regular:" + str(item))
        for part in [*reversed(root.parents), root]:
            if is_reparse(os.lstat(native_path(part))):
                raise ValueError("root_reparse:" + str(part))
        descend(root)
        return index, folders

    def digest(path: Path, before: os.stat_result) -> str:
        nonlocal bytes_hashed
        if before.st_size > max_hash_bytes - bytes_hashed:
            raise ValueError("hash_budget")
        value = hashlib.sha256()
        with open(native_path(path), "rb") as stream:
            if fingerprint(os.fstat(stream.fileno())) != fingerprint(before):
                raise ValueError("identity_changed_before_read:" + str(path))
            while block := stream.read(1024**2):
                budget()
                bytes_hashed += len(block)
                if bytes_hashed > max_hash_bytes:
                    raise ValueError("hash_budget")
                value.update(block)
            if fingerprint(os.fstat(stream.fileno())) != fingerprint(before):
                raise ValueError("identity_changed_during_read:" + str(path))
        return value.hexdigest()

    try:
        if roots[0] == roots[1] or any(a.is_relative_to(b) for a, b in
                [(roots[0], roots[1]), (roots[1], roots[0])]):
            raise ValueError("overlapping_roots")
        for root in roots:
            index, folders = tree(root)
            files.append(index)
            directories.append(folders)
        if files[0].keys() != files[1].keys() or directories[0] != directories[1]:
            raise ValueError("tree_members_differ")
        for relative in sorted(files[0]):
            left, li = files[0][relative]
            right, ri = files[1][relative]
            if li.st_size != ri.st_size:
                raise ValueError("size_differs:" + relative)
            if not li.st_ino or not ri.st_ino or li.st_nlink != 1 or ri.st_nlink != 1:
                raise ValueError("unknown_identity_or_hardlink:" + relative)
            if (li.st_dev, li.st_ino) == (ri.st_dev, ri.st_ino):
                raise ValueError("same_physical_file:" + relative)
            ls, rs = alternate_streams(left), alternate_streams(right)
            if ls is None or rs is None or ls or rs:
                raise ValueError("alternate_streams_unknown_or_present:" + relative)
            a, b = digest(left, li), digest(right, ri)
            if a != b:
                raise ValueError("hash_differs:" + relative)
            size = allocated_bytes(left, li)
            if size is None:
                raise ValueError("allocation_unknown:" + relative)
            error = exclusive_probe(left)
            if error is not None:
                raise ValueError("exclusive_probe_failed:" + relative + ":" + str(error))
            allocation += size
            records.append({"relative_path": relative, "sha256": a, "bytes": li.st_size,
                "candidate_identity": list(fingerprint(li)),
                "retained_identity": list(fingerprint(ri)), "allocated_bytes": size})
        # 再列一次，不能以部分樹或掃描期間變動的樹交付可還原證據。
        for root, original, folders in zip(roots, files, directories):
            latest, dirs = tree(root)
            if latest.keys() != original.keys() or dirs != folders or any(
                    fingerprint(latest[k][1]) != fingerprint(original[k][1]) for k in original):
                raise ValueError("tree_changed_before_closeout:" + str(root))
    except (OSError, ValueError) as exc:
        errors.append(str(exc))
    return {"schema_version": "storage-reclaim-pair.v1", "candidate": str(roots[0]),
        "retained": str(roots[1]), "equivalent_stable_trees": not errors,
        "errors": errors, "files": records,
        "directories": sorted(directories[0]) if directories else [],
        "verified_file_count": len(records), "bytes_hashed": bytes_hashed,
        "estimated_candidate_allocation_bytes": allocation if not errors else None,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "reference_audit_required": True, "process_audit_required": True,
        "owner_approval_required": True, "deletion_performed": False,
        "restore_recreates_file_ids": True, "atomic_snapshot": False,
        "restoration_scope": "relative_paths_and_default_stream_bytes_only",
        "metadata_restore_verified": False, "external_restore_plan_required": True,
        "exclusive_probe_is_instantaneous": True, "mapped_images_require_separate_audit": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--retained", required=True, type=Path)
    args = parser.parse_args()
    result = verify_pair(args.candidate, args.retained)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["equivalent_stable_trees"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
