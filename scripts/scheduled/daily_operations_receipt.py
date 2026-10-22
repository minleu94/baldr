"""建立每日營運終態收據的有界、不可覆寫寫入器。"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
from typing import Any, Mapping

from runtime.repository_output import is_repository_output_path, resolve_repository_output_path


MAX_TERMINAL_RECEIPT_BYTES = 512 * 1024


def code_version(path: Path) -> str:
    """以 producer 原始碼位元組的 SHA-256 標示實際版本。"""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(64 * 1024):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _checked_receipt_path(path: Path) -> Path:
    """只接受普通父目錄，repo/output 沿既有核准 mount-point 邊界解析。"""
    if ".." in path.parts:
        raise ValueError("terminal_receipt_parent_traversal")
    candidate = Path(os.path.abspath(path))
    repository = Path(__file__).resolve().parents[2]
    if is_repository_output_path(candidate, repository_root=repository):
        candidate = resolve_repository_output_path(candidate, repository_root=repository)
    for component in reversed((candidate, *candidate.parents)):
        try:
            info = component.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x0400:
            raise ValueError("terminal_receipt_path_contains_link")
        if component != candidate and not stat.S_ISDIR(info.st_mode):
            raise ValueError("terminal_receipt_parent_not_directory")
    return candidate


def write_terminal_receipt(
    path: Path, payload: Mapping[str, Any], *, receipt_root: Path | None = None,
) -> dict[str, str]:
    """以單份序列化位元組 create-only 寫入收據並回傳其路徑與雜湊。"""
    raw = (json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ) + "\n").encode("utf-8")
    if len(raw) > MAX_TERMINAL_RECEIPT_BYTES:
        raise ValueError("terminal_receipt_too_large")
    logical_path = path
    path = _checked_receipt_path(path)
    root = _checked_receipt_path(receipt_root if receipt_root is not None else logical_path.parent)
    if not path.is_relative_to(root) or path == root:
        raise ValueError("terminal_receipt_outside_root")
    path.parent.mkdir(parents=True, exist_ok=True)
    _checked_receipt_path(root)
    _checked_receipt_path(path)
    descriptor: int | None = None
    created = False
    created_identity: tuple[int, int] | None = None
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_RDWR | getattr(os, "O_BINARY", 0), 0o600)
        created = True
        opened_stat = os.fstat(descriptor)
        created_identity = (int(opened_stat.st_dev), int(opened_stat.st_ino))
        _checked_receipt_path(path)
        if not stat.S_ISREG(opened_stat.st_mode):
            raise OSError("terminal_receipt_not_regular_file")
        view = memoryview(raw)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("terminal_receipt_short_write")
            view = view[written:]
        os.fsync(descriptor)
        os.lseek(descriptor, 0, os.SEEK_SET)
        readback = bytearray()
        while len(readback) <= MAX_TERMINAL_RECEIPT_BYTES:
            chunk = os.read(descriptor, min(64 * 1024, MAX_TERMINAL_RECEIPT_BYTES + 1 - len(readback)))
            if not chunk:
                break
            readback.extend(chunk)
        if bytes(readback) != raw:
            raise OSError("terminal_receipt_readback_mismatch")
        os.close(descriptor)
        descriptor = None
        return {"path": str(logical_path), "sha256": "sha256:" + hashlib.sha256(raw).hexdigest()}
    except BaseException:
        descriptor_closed = descriptor is None
        if descriptor is not None:
            try:
                os.close(descriptor)
                descriptor = None
                descriptor_closed = True
            except OSError:
                descriptor = None
        if (
            created
            and descriptor_closed
            and created_identity is not None
            and created_identity[1] > 0
        ):
            try:
                current_stat = path.lstat()
                current_identity = (int(current_stat.st_dev), int(current_stat.st_ino))
                if (
                    stat.S_ISREG(current_stat.st_mode)
                    and not stat.S_ISLNK(current_stat.st_mode)
                    and current_identity == created_identity
                ):
                    path.unlink()
            except OSError:
                pass
        raise
    finally:
        if descriptor is not None:
            os.close(descriptor)
