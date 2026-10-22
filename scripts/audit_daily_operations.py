"""以外部 SHA-256 固定觀察輸入，唯讀分類每日排程狀態。"""

from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
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
from app_module.daily_operations_receipts import adapt_receipt


MAX_BYTES = 2 * 1024 * 1024
MAX_RECEIPT_BYTES = 512 * 1024
MAX_READS = 128
_TAIPEI_TIMEZONE = timezone(timedelta(hours=8), name="Asia/Taipei")


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
    # schema明列時只接受adapter認得的契約，不以generic legacy補接未知schema。
    if not isinstance(value, dict):
        raise AuditInputError("receipt_not_object")
    adapted = adapt_receipt(value)
    if "schema_version" not in value and adapted.get("supported") is True:
        legacy_task = value.get("task")
        adapted["schema"] = f"legacy:{legacy_task}" if isinstance(legacy_task, str) and legacy_task else "legacy:generic.v1"
    if "schema_version" not in value and adapted.get("supported") is not True:
        # 僅兼容具備完整基本身份欄位的無schema舊收據。
        if all(isinstance(value.get(key), str) and value[key].strip() for key in ("run_id", "started_at", "status")):
            adapted.update({
                "supported": True,
                "kind": "producer",
                "schema": "legacy:generic.v1",
                "run_id": value["run_id"],
                "started_at": value["started_at"],
                "completed_at": value.get("completed_at", value.get("completed_at_utc")),
                "producer_status": value["status"],
            })

    # Paper EOD gate有時會列出大量逐檔缺件。原收據仍受512KiB與外部SHA
    # 保護；超過一般128項列表界限時，只建立明確標記的有限來源阻擋投影。
    if (
        value.get("schema_version") == "paper-execution-dependency-gate.v1"
        and isinstance(value.get("blockers"), list)
        and len(value["blockers"]) > 128
    ):
        projection = _paper_eod_blocked_projection(
            value,
            verified_sha256=hashlib.sha256(raw).hexdigest(),
            verified_relative_path=ref["path"],
        )
        if projection is None:
            raise AuditInputError("receipt_blockers_invalid")
        return {
            "supported": True,
            "kind": "producer",
            "schema": "paper-execution-dependency-gate.v1",
            "run_id": None,
            "started_at": None,
            "completed_at": None,
            "producer_status": "blocked",
            "producer_status_semantic": "blocked",
            # 不把超限的原始清單帶入分類器，也不聲稱逐條驗證。
            "blockers": [],
            "errors": [],
            "warnings": [],
            "blocker": [],
            "_bounded_paper_eod_projection": projection,
        }

    def bounded_text_list(raw_value: object, field: str, *, allow_scalar: bool = False) -> list[str]:
        if raw_value is None:
            return []
        items = [raw_value] if allow_scalar and isinstance(raw_value, str) else raw_value
        if not isinstance(items, list) or len(items) > 128:
            raise AuditInputError(f"receipt_{field}_invalid")
        if any(not isinstance(item, str) or not item.strip() or len(item) > 2048 for item in items):
            raise AuditInputError(f"receipt_{field}_invalid")
        return list(items)

    blockers = bounded_text_list(value.get("blockers", []), "blockers")
    blocker_values = bounded_text_list(value.get("blocker"), "blocker", allow_scalar=True)
    errors = bounded_text_list(value.get("errors"), "errors", allow_scalar=True)
    warnings = bounded_text_list(value.get("warnings"), "warnings", allow_scalar=True)
    status = adapted.get("producer_status")
    if not isinstance(status, str):
        status = value.get("producer_status") if isinstance(value.get("producer_status"), str) else value.get("status")
    adapted.update({
        "producer_status": status if isinstance(status, str) else None,
        "blockers": blockers + [item for item in blocker_values if item not in blockers],
        "errors": errors,
        "warnings": warnings,
        "blocker": blocker_values,
    })
    return adapted


def _paper_eod_blocked_projection(
    value: dict[str, Any], *, verified_sha256: str, verified_relative_path: str
) -> dict[str, Any] | None:
    """從已驗SHA與有界JSON建立不含run-id主張的Paper EOD阻擋摘要。"""
    if (
        value.get("status") != "blocked"
        or value.get("ready") is not False
        or value.get("source_db_written") is not False
        or value.get("source_files_written") is not False
    ):
        return None
    target_date = value.get("target_date")
    observed_at = value.get("observed_at")
    blockers = value.get("blockers")
    if (
        not isinstance(target_date, str)
        or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", target_date)
        or not isinstance(observed_at, str)
        or not isinstance(blockers, list)
        or len(blockers) <= 128
        or type(value.get("attempt")) is not int
        or value["attempt"] < 1
    ):
        return None
    try:
        target = datetime.fromisoformat(target_date)
        observed = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    if (
        target.date().isoformat() != target_date
        or observed.tzinfo is None
        or observed.utcoffset() is None
        or observed.astimezone(_TAIPEI_TIMEZONE).date().isoformat() != target_date
    ):
        return None

    lane = value.get("freshness_lane")
    if not isinstance(lane, dict):
        return None
    required = lane.get("required_sources")
    daily_prices = required.get("sqlite.daily_prices") if isinstance(required, dict) else None
    market = value.get("market_observation")
    actual_period = daily_prices.get("actual_period") if isinstance(daily_prices, dict) else None
    try:
        actual_date = date.fromisoformat(actual_period) if isinstance(actual_period, str) else None
    except ValueError:
        actual_date = None
    if (
        lane.get("schema_version") != "paper-eod-freshness-lane.v1"
        or lane.get("status") != "blocked"
        or lane.get("target_date") != target_date
        or not isinstance(daily_prices, dict)
        or daily_prices.get("freshness_status") != "stale"
        or daily_prices.get("expected_period") != target_date
        or actual_date is None
        or actual_date.isoformat() != actual_period
        or actual_date >= target.date()
        or not isinstance(market, dict)
        or market.get("mode") != "ro/query_only"
        or market.get("ready") is not False
        or market.get("target_date") != target_date
        or market.get("target_key") != target_date.replace("-", "")
    ):
        return None
    return {
        "schema": "paper-eod-blocked-reader-projection.v1",
        "source_schema": "paper-execution-dependency-gate.v1",
        "raw_sha256_verified": True,
        "evidence_kind": "scheduler_time_correlated_not_producer_run_id",
        "target_date": target_date,
        "observed_at": observed_at,
        "receipt_path": verified_relative_path,
        "raw_sha256": verified_sha256,
        "blocker_count": len(blockers),
        "blockers_validation": "not_performed_above_128",
        "source_basis": "sqlite.daily_prices_stale_and_target_mismatch",
        "source_db_written": False,
        "source_files_written": False,
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
