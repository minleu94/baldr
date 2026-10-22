"""以外部 SHA-256 固定觀察輸入，唯讀分類每日排程狀態。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
from typing import Any, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app_module.daily_operations_status import (
    ObservationError,
    classify_manifest,
    validate_manifest,
)


MAX_BYTES = 2 * 1024 * 1024
MAX_RECEIPT_BYTES = 512 * 1024
MAX_READS = 128


class AuditInputError(ValueError):
    pass


def _pairs_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise AuditInputError("json_duplicate_key")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise AuditInputError(f"json_non_finite:{value}")


def _strict_json(raw: bytes) -> Any:
    try:
        text = raw.decode("utf-8-sig")
        return json.loads(
            text,
            object_pairs_hook=_pairs_no_duplicates,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AuditInputError("json_invalid") from exc


def _read_bounded_regular(path: Path, limit: int) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or _is_reparse(before):
        raise AuditInputError("path_not_regular_nofollow")
    if before.st_size < 0 or before.st_size > limit:
        raise AuditInputError("file_size_limit")
    fd = os.open(str(path), flags)
    try:
        opened = os.fstat(fd)
        if not stat.S_ISREG(opened.st_mode) or _file_identity(before) != _file_identity(opened):
            raise AuditInputError("file_identity_changed_before_read")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(fd, min(65536, limit + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > limit:
                raise AuditInputError("file_size_limit")
        after = os.fstat(fd)
        current = path.lstat()
        if (
            _file_identity(opened) != _file_identity(after)
            or _file_identity(after) != _file_identity(current)
            or total != after.st_size
        ):
            raise AuditInputError("file_identity_changed_during_read")
        return b"".join(chunks)
    finally:
        os.close(fd)


def _file_identity(info: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        info.st_dev,
        info.st_ino,
        info.st_size,
        getattr(info, "st_mtime_ns", int(info.st_mtime * 1_000_000_000)),
        getattr(info, "st_ctime_ns", int(info.st_ctime * 1_000_000_000)),
    )


def _is_reparse(info: os.stat_result) -> bool:
    attrs = getattr(info, "st_file_attributes", 0)
    return bool(attrs & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def _resolve_receipt(root: Path, relative: str) -> Path:
    candidate = Path(relative)
    if not candidate.parts or candidate.is_absolute() or any(part in {"..", ""} for part in candidate.parts):
        raise AuditInputError("receipt_path_must_be_relative_and_contained")
    root_resolved = root.resolve(strict=True)
    current = root_resolved
    for part in candidate.parts[:-1]:
        current = current / part
        info = current.lstat()
        if not stat.S_ISDIR(info.st_mode) or _is_reparse(info):
            raise AuditInputError("receipt_parent_not_plain_directory")
    target = current / candidate.parts[-1]
    if not target.parent.is_relative_to(root_resolved):
        raise AuditInputError("receipt_path_escape")
    return target


def _read_receipt(root: Path, ref: dict[str, str]) -> dict[str, Any]:
    if not re.fullmatch(r"[0-9a-fA-F]{64}", ref["sha256"]):
        raise AuditInputError("receipt_sha256_invalid")
    path = _resolve_receipt(root, ref["path"])
    raw = _read_bounded_regular(path, MAX_RECEIPT_BYTES)
    if hashlib.sha256(raw).hexdigest().lower() != ref["sha256"].lower():
        raise AuditInputError("receipt_sha256_mismatch")
    value = _strict_json(raw)
    # 僅支援刻意收斂的收據格式；舊版格式一律保留為 UNKNOWN。
    if not isinstance(value, dict):
        raise AuditInputError("receipt_not_object")
    status = value.get("producer_status") or value.get("status")
    if (
        not isinstance(value.get("run_id"), str)
        or not isinstance(value.get("started_at"), str)
        or not isinstance(status, str)
        or not isinstance(value.get("blockers", []), list)
        or any(not isinstance(item, str) or not item.strip() or len(item) > 2048
               for item in value.get("blockers", []))
        or len(value.get("blockers", [])) > 128
    ):
        raise AuditInputError("receipt_schema_unsupported")
    # 只回傳獨立讀取的收據欄位，不沿用 manifest 的宣稱。
    return {
        "run_id": value["run_id"],
        "started_at": value["started_at"],
        "producer_status": value.get("producer_status") or value.get("status"),
        "status": value.get("status"),
        "blockers": value.get("blockers", []),
        "completed_at": value.get("completed_at", value.get("completed_at_utc")),
    }


def audit(manifest_path: Path, expected_sha256: str, receipt_root: Path) -> dict[str, Any]:
    if not re.fullmatch(r"[0-9a-fA-F]{64}", expected_sha256):
        raise AuditInputError("snapshot_sha256_invalid")
    raw = _read_bounded_regular(manifest_path, MAX_BYTES)
    if hashlib.sha256(raw).hexdigest().lower() != expected_sha256.lower():
        raise AuditInputError("snapshot_sha256_mismatch")
    manifest = validate_manifest(_strict_json(raw))
    if len(manifest["components"]) > MAX_READS:
        raise AuditInputError("receipt_read_limit")
    receipts: dict[str, dict[str, Any] | None] = {}
    errors: dict[str, str] = {}
    for row in manifest["components"]:
        ref = row["receipt_ref"]
        if ref is None:
            receipts[row["id"]] = None
            errors[row["id"]] = "receipt_ref_missing"
            continue
        try:
            receipts[row["id"]] = _read_receipt(receipt_root, ref)
        except (OSError, ValueError, AuditInputError) as exc:
            receipts[row["id"]] = None
            errors[row["id"]] = str(exc)[:256] or type(exc).__name__
    return classify_manifest(manifest, receipts, errors)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="唯讀分類 SHA-256 固定的每日排程 observation manifest。")
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--snapshot-sha256", required=True)
    parser.add_argument("--receipt-root", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = audit(args.manifest, args.snapshot_sha256, args.receipt_root)
    except (OSError, ValueError, ObservationError) as exc:
        print(json.dumps({"error": str(exc)[:256]}, ensure_ascii=False, sort_keys=True))
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
