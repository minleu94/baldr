#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Validate and apply a bounded technical-indicator repair.

The default command remains plan-only.  ``--apply`` is an explicitly gated
writer: it consumes a reviewed dry-run, the applied price receipt, and a
shared maintenance lock; it writes only listed technical cells and matching
5/20 cache cells.  A plan is rejected when its source file or source-plan
hash changed after the dry-run.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data_module.ml_storage_capacity import (
    acquire_heavy_chain_reservation,
    release_heavy_chain_reservation,
)

from scripts.technical_indicator_repair_dryrun import (
    DEPENDENT_INDICATORS,
    SOURCE_FIELD_KEYS,
    DryRunError,
    _json_value,
    _date_key,
    _normalise_symbol,
    _normalise_overlay_row,
    _sha256_payload,
    _values_equal,
)


class ApplyGuardError(RuntimeError):
    """Raised when a dry-run cannot be promoted to a reviewed patch plan."""


class TechnicalApplyError(ApplyGuardError):
    """Raised when a gated technical/cache write must fail closed."""


CONFIRM_TOKEN = "repair-technical-indicators-20260520"
TARGET_DATE = "20260520"
TECHNICAL_TABLE = "technical_indicators"
# Keep a large free-space reserve because the formal DB is multi-GB and the
# cache writer retains both immutable backups and staged copies.  The check is
# bounded to the source/cache volume and does not inspect or load the files.
CAPACITY_RESERVE_BYTES = 200 * 1024**3
CAPACITY_HEADROOM_BYTES = 64 * 1024**2
TECHNICAL_ALIAS_COLUMNS = ("Date", "Open", "High", "Low", "Close", "Volume")
CACHE_COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "Date": ("Date", "日期"),
    "日期": ("日期", "Date"),
    "Open": ("Open", "開盤價"),
    "開盤價": ("開盤價", "Open"),
    "High": ("High", "最高價"),
    "最高價": ("最高價", "High"),
    "Low": ("Low", "最低價"),
    "最低價": ("最低價", "Low"),
    "Close": ("Close", "收盤價"),
    "收盤價": ("收盤價", "Close"),
    "Volume": ("Volume", "成交股數"),
    "成交股數": ("成交股數", "Volume"),
}
DATE_ALIASES = ("日期", "Date", "date", "trade_date", "trading_date")
SYMBOL_ALIASES = (
    "證券代號",
    "股票代號",
    "stock_code",
    "stock_id",
    "Code",
)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _price_payload_hash(payload: Mapping[str, Any]) -> str:
    """Match the price repair receipt hash (canonical JSON plus newline)."""
    encoded = (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _write_json_atomic(path: Path, payload: Mapping[str, Any], *, replace: bool) -> None:
    path = path.expanduser().resolve(strict=False)
    if path.is_symlink() or (path.exists() and not replace):
        raise TechnicalApplyError(f"拒絕覆寫 receipt 路徑：{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(
                (
                    json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)
                    + "\n"
                ).encode("utf-8")
            )
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass


def _normalise_csv_value(value: Any) -> str:
    value = _json_value(value)
    if value is None:
        return ""
    if isinstance(value, bool):
        return "1" if value else "0"
    return str(value)


def _cache_cell_value(value: Any) -> Any:
    """Normalize CSV's empty representation without inventing a value."""
    if isinstance(value, str) and not value.strip():
        return None
    return _json_value(value)


def _cache_text_format(path: Path) -> tuple[str, str]:
    """Keep BOM and line-ending bytes stable across a row-bound rewrite."""
    with path.open("rb") as stream:
        sample = stream.read(1024 * 1024)
    encoding = "utf-8-sig" if sample.startswith(b"\xef\xbb\xbf") else "utf-8"
    line_ending = "\r\n" if b"\r\n" in sample else "\n"
    return encoding, line_ending


def _daily_hash_numeric(value: Any) -> Any:
    """Mirror pandas ``to_numeric(errors='coerce')`` used by the dry-run."""
    if value is None:
        return None
    try:
        # numeric-boundary: this is only the logical source hash boundary;
        # do not use it for persisted financial calculations.
        parsed = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return _json_value(parsed)


def _csv_date_key(value: Any) -> str:
    return _date_key(value)


def _csv_symbol(value: Any) -> str:
    return _normalise_symbol(value)


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise ApplyGuardError(f"輸入 JSON 不存在或是 symlink：{path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ApplyGuardError(f"無法讀取 JSON：{path} ({exc})") from exc
    if not isinstance(value, dict):
        raise ApplyGuardError(f"JSON 根節點不是 object：{path}")
    return value


def _assert_output_safe(output_path: Path, input_paths: Sequence[Path]) -> None:
    """Keep a generated plan outside every source file/directory and symlink."""
    if output_path.exists() and output_path.is_symlink():
        raise ApplyGuardError(f"輸出檔不可是 symlink：{output_path}")
    parent = output_path.parent
    if parent.exists() and parent.is_symlink():
        raise ApplyGuardError(f"輸出父目錄不可是 symlink：{parent}")
    resolved_output = output_path.expanduser().resolve(strict=False)
    for input_path in input_paths:
        resolved_input = input_path.expanduser().resolve(strict=False)
        if resolved_output == resolved_input or resolved_input in resolved_output.parents:
            raise ApplyGuardError(f"輸出路徑落在來源範圍：{output_path} / {input_path}")


def _canonical_digest(row: Mapping[str, Any]) -> str:
    payload = {
        str(key): _json_value(value)
        for key, value in row.items()
        if not str(key).startswith("_")
    }
    return _sha256_payload(payload)


def _raw_source_digest(row: Mapping[str, Any]) -> str:
    """Hash the exact verified ``rows[].source`` mapping, including NULLs."""
    return _sha256_payload({str(key): _json_value(value) for key, value in row.items()})


def _finite_or_null(value: Any) -> Any:
    """Reject non-finite values in a patch while retaining NULL explicitly."""
    value = _json_value(value)
    if isinstance(value, float) and not math.isfinite(value):
        raise ApplyGuardError("patch 含非有限數值")
    return value


def _price_rows(price_plan: Mapping[str, Any], target_date: str) -> dict[str, Mapping[str, Any]]:
    rows = price_plan.get("rows")
    if not isinstance(rows, list):
        raise ApplyGuardError("price repair plan 缺少 rows")
    result: dict[str, Mapping[str, Any]] = {}
    for item in rows:
        if not isinstance(item, Mapping):
            raise ApplyGuardError("price repair plan rows 含非 object")
        normalized, schema = _normalise_overlay_row(item)
        if schema != "price_repair_plan_rows_source":
            raise ApplyGuardError("price repair plan row 缺少完整 rows[].source")
        if str(normalized.get("date", "")) != target_date:
            raise ApplyGuardError("price repair plan 含非 target date row")
        symbol = str(normalized.get("symbol", "")).strip()
        if not symbol:
            raise ApplyGuardError("price repair plan row 缺少 symbol")
        raw_source = item.get("source")
        if not isinstance(raw_source, Mapping):
            raise ApplyGuardError("price repair plan rows[].source 不是 object")
        normalized = {**normalized, "_raw_source_row": dict(raw_source)}
        if symbol in result and _raw_source_digest(result[symbol]["_raw_source_row"]) != _raw_source_digest(raw_source):
            raise ApplyGuardError(f"price repair plan 同一股票有多個 source：{symbol}")
        result[symbol] = normalized
    return result


def _validate_indicator_update(
    *, symbol: str, update: Mapping[str, Any], target_date: str
) -> dict[str, Any]:
    date = str(update.get("date", ""))
    if not date.isdigit() or len(date) != 8 or date < target_date:
        raise ApplyGuardError(f"{symbol} indicator update 超出 target scope：{date}")
    changed = update.get("changed_columns")
    old = update.get("old")
    new = update.get("new")
    if not isinstance(changed, list) or not isinstance(old, Mapping) or not isinstance(new, Mapping):
        raise ApplyGuardError(f"{symbol} indicator update 結構不完整：{date}")
    if set(changed) != set(old) or set(changed) != set(new):
        raise ApplyGuardError(f"{symbol} indicator update old/new 欄位不一致：{date}")
    operations: list[dict[str, Any]] = []
    for column in changed:
        column = str(column)
        if column not in DEPENDENT_INDICATORS:
            raise ApplyGuardError(f"{symbol} indicator update 含非白名單欄位：{column}")
        operations.append(
            {
                "kind": "technical_indicator_cell",
                "symbol": symbol,
                "date": date,
                "column": column,
                "column_ordinal": 0,
                "old": _finite_or_null(old[column]),
                "new": _finite_or_null(new[column]),
            }
        )
    return operations


def _validate_source_copy_update(
    *,
    symbol: str,
    update: Mapping[str, Any],
    target_date: str,
    allowed_columns: set[str],
) -> dict[str, Any]:
    if str(update.get("row_identity", {}).get("date", "")) != target_date:
        raise ApplyGuardError(f"{symbol} source copy 不是 target date")
    column = str(update.get("column", ""))
    if column not in allowed_columns or column not in SOURCE_FIELD_KEYS:
        raise ApplyGuardError(f"{symbol} source copy 含非 price-plan 欄位：{column}")
    ordinal = update.get("column_ordinal")
    if not isinstance(ordinal, int) or ordinal < 0:
        raise ApplyGuardError(f"{symbol} source copy column ordinal 無效：{column}")
    return {
        "kind": "technical_source_cell",
        "symbol": symbol,
        "date": target_date,
        "column": column,
        "column_ordinal": ordinal,
        "source_key": str(update.get("source_key", "")),
        "old": _finite_or_null(update.get("old")),
        "new": _finite_or_null(update.get("new")),
    }


def _validate_cache_source_desired(
    *,
    symbol: str,
    desired: Mapping[str, Any],
    target_date: str,
    allowed_columns: set[str],
) -> dict[str, Any]:
    """Validate a cache-only source desired cell without a DB old value."""
    row_identity = desired.get("row_identity")
    if not isinstance(row_identity, Mapping) or str(row_identity.get("date", "")) != target_date:
        raise ApplyGuardError(f"{symbol} cache source desired 不是 target date")
    column = str(desired.get("column", ""))
    if column not in allowed_columns or column not in SOURCE_FIELD_KEYS:
        raise ApplyGuardError(f"{symbol} cache source desired 含非 price-plan 欄位：{column}")
    ordinal = desired.get("column_ordinal")
    if not isinstance(ordinal, int) or ordinal < 0:
        raise ApplyGuardError(f"{symbol} cache source desired column ordinal 無效：{column}")
    return {
        "kind": "cache_source_cell",
        "symbol": symbol,
        "date": target_date,
        "column": column,
        "column_ordinal": ordinal,
        "source_key": str(desired.get("source_key", "")),
        "new": _finite_or_null(desired.get("new")),
    }


def build_apply_plan(
    *,
    dryrun_manifest_path: Path,
    price_plan_path: Path,
    output_path: Path | None = None,
    expected_plan_hash: str | None = None,
    expected_price_file_sha256: str | None = None,
) -> dict[str, Any]:
    """Validate and return a plan-only list of exact cell operations."""
    manifest = _read_json(dryrun_manifest_path)
    price_plan = _read_json(price_plan_path)
    target_date = str(manifest.get("scope", {}).get("target_date", ""))
    if target_date != "20260520":
        raise ApplyGuardError(f"只允許 20260520，收到：{target_date}")
    summary = manifest.get("summary")
    read_only = manifest.get("read_only")
    overlay_meta = manifest.get("overlay_source")
    if not isinstance(summary, Mapping) or not isinstance(read_only, Mapping) or not isinstance(overlay_meta, Mapping):
        raise ApplyGuardError("dry-run manifest 缺少 summary/read_only/overlay_source")
    if bool(summary.get("formal_data_written")) or bool(read_only.get("formal_data_written")):
        raise ApplyGuardError("dry-run 已標示 formal data written")
    if int(summary.get("failed_symbols", -1)) != 0:
        raise ApplyGuardError("dry-run 有 failed symbols")
    actual_price_file_sha = _sha256_file(price_plan_path)
    recorded_overlay_sha = str(overlay_meta.get("sha256", ""))
    if recorded_overlay_sha != actual_price_file_sha:
        raise ApplyGuardError(
            "dry-run manifest 的 price plan file hash 已過期："
            f" recorded={recorded_overlay_sha} actual={actual_price_file_sha}"
        )
    price_plan_hash = str(price_plan.get("plan_hash", ""))
    recorded_plan_hash = str(overlay_meta.get("plan_hash", ""))
    if not price_plan_hash or recorded_plan_hash != price_plan_hash:
        raise ApplyGuardError(
            f"price plan hash 不一致：dryrun={recorded_plan_hash} current={price_plan_hash}"
        )
    if expected_plan_hash is not None and price_plan_hash != expected_plan_hash:
        raise ApplyGuardError(f"price plan hash 與 review hash 不同：{price_plan_hash}")
    if expected_price_file_sha256 is not None and actual_price_file_sha != expected_price_file_sha256:
        raise ApplyGuardError(f"price plan file hash 與 review hash 不同：{actual_price_file_sha}")
    if str(price_plan.get("source_date", "")) != target_date:
        raise ApplyGuardError("price plan source_date 不同")
    if price_plan.get("apply_allowed") is not False:
        raise ApplyGuardError("price plan 必須保持 apply_allowed=false")

    source_columns = price_plan.get("source_update_columns")
    if not isinstance(source_columns, list) or not source_columns:
        raise ApplyGuardError("price plan 缺少 source_update_columns")
    allowed_source_columns = {
        str(column) for column in source_columns
    }.union(TECHNICAL_ALIAS_COLUMNS)
    price_rows = _price_rows(price_plan, target_date)
    plans = manifest.get("plans")
    if not isinstance(plans, list):
        raise ApplyGuardError("dry-run manifest 缺少 plans")
    manifest_symbols = {str(plan.get("symbol", "")) for plan in plans if isinstance(plan, Mapping)}
    if manifest_symbols != set(price_rows):
        raise ApplyGuardError("dry-run 與 price plan 股票 allowlist 不一致")
    allowlist_hash = str(price_plan.get("allowlist_hash", ""))
    if allowlist_hash and str(overlay_meta.get("allowlist_hash", "")) != allowlist_hash:
        raise ApplyGuardError("allowlist hash 不一致")

    operations: list[dict[str, Any]] = []
    cache_operations: list[dict[str, Any]] = []
    source_rows = 0
    source_cells = 0
    cache_source_cells = 0
    cache_indicator_cells = 0
    for plan in plans:
        if not isinstance(plan, Mapping):
            raise ApplyGuardError("dry-run plans 含非 object")
        symbol = str(plan.get("symbol", ""))
        source = price_rows[symbol]
        raw_source = source.get("_raw_source_row")
        if not isinstance(raw_source, Mapping):
            raise ApplyGuardError(f"{symbol} 缺少 raw verified source row")
        canonical = plan.get("canonical_source_row")
        canonical_raw = plan.get("canonical_source_row_raw")
        if not isinstance(canonical, Mapping) or not isinstance(canonical_raw, Mapping):
            raise ApplyGuardError(f"{symbol} canonical source row hash 不一致")
        if _raw_source_digest(canonical_raw) != _raw_source_digest(raw_source):
            raise ApplyGuardError(f"{symbol} raw canonical source row hash 不一致")
        if _canonical_digest(canonical) != _canonical_digest({key: value for key, value in source.items() if not str(key).startswith("_")}):
            raise ApplyGuardError(f"{symbol} normalized canonical source row hash 不一致")
        source_copy = plan.get("source_copy_plan")
        if not isinstance(source_copy, Mapping):
            raise ApplyGuardError(f"{symbol} 缺少 source_copy_plan")
        if source_copy.get("source_plan_hash") != price_plan_hash:
            raise ApplyGuardError(f"{symbol} source plan hash 不一致")
        expected_source_digest = str(source_copy.get("source_row_sha256", ""))
        if expected_source_digest != _raw_source_digest(raw_source):
            raise ApplyGuardError(f"{symbol} source row digest 不一致")
        normalized_digest = source_copy.get("normalized_source_row_sha256")
        if normalized_digest is not None and normalized_digest != _canonical_digest(
            {key: value for key, value in source.items() if not str(key).startswith("_")}
        ):
            raise ApplyGuardError(f"{symbol} normalized source row digest 不一致")
        if plan.get("technical_table", {}).get("pre_target_rows_untouched") is not True:
            raise ApplyGuardError(f"{symbol} pre-target guard missing")
        if plan.get("technical_table", {}).get("unknown_columns_untouched") is not True:
            raise ApplyGuardError(f"{symbol} unknown-column guard missing")
        indicator_updates = plan.get("updates")
        if not isinstance(indicator_updates, list):
            raise ApplyGuardError(f"{symbol} updates 不是 list")
        for update in indicator_updates:
            if not isinstance(update, Mapping):
                raise ApplyGuardError(f"{symbol} indicator update 不是 object")
            operations.extend(
                _validate_indicator_update(
                    symbol=symbol, update=update, target_date=target_date
                )
            )
        cache_desired_rows = plan.get("cache_desired_rows")
        if not isinstance(cache_desired_rows, list):
            raise ApplyGuardError(f"{symbol} 缺少 cache_desired_rows")
        for desired_row in cache_desired_rows:
            if not isinstance(desired_row, Mapping):
                raise ApplyGuardError(f"{symbol} cache desired row 不是 object")
            date = str(desired_row.get("date", ""))
            if not date.isdigit() or len(date) != 8 or date < target_date:
                raise ApplyGuardError(f"{symbol} cache desired 超出 target scope：{date}")
            desired_values = desired_row.get("desired")
            if not isinstance(desired_values, Mapping):
                raise ApplyGuardError(f"{symbol} cache desired values 不是 object：{date}")
            for column, value in desired_values.items():
                column = str(column)
                if column not in DEPENDENT_INDICATORS:
                    raise ApplyGuardError(f"{symbol} cache desired 含非白名單欄位：{column}")
                cache_operations.append(
                    {
                        "kind": "cache_indicator_cell",
                        "symbol": symbol,
                        "date": date,
                        "column": column,
                        "column_ordinal": 0,
                        "source_column": column,
                        "new": _finite_or_null(value),
                    }
                )
                cache_indicator_cells += 1
        source_updates = source_copy.get("updates")
        if not isinstance(source_updates, list):
            raise ApplyGuardError(f"{symbol} source updates 不是 list")
        source_desired = source_copy.get("desired")
        if not isinstance(source_desired, list):
            raise ApplyGuardError(f"{symbol} source_copy_plan 缺少 desired")
        if source_updates:
            source_rows += 1
        for update in source_updates:
            if not isinstance(update, Mapping):
                raise ApplyGuardError(f"{symbol} source update 不是 object")
            operations.append(
                _validate_source_copy_update(
                    symbol=symbol,
                    update=update,
                    target_date=target_date,
                    allowed_columns=allowed_source_columns,
                )
            )
            source_cells += 1
        for desired in source_desired:
            if not isinstance(desired, Mapping):
                raise ApplyGuardError(f"{symbol} cache source desired 不是 object")
            cache_operations.append(
                _validate_cache_source_desired(
                    symbol=symbol,
                    desired=desired,
                    target_date=target_date,
                    allowed_columns=allowed_source_columns,
                )
            )
            cache_source_cells += 1

    if output_path is not None:
        _assert_output_safe(output_path, (dryrun_manifest_path, price_plan_path))
    result: dict[str, Any] = {
        "schema_version": "technical-indicator-repair-apply-guard-20260520.v1",
        "mode": "plan_only",
        "apply_allowed": False,
        "formal_data_written": False,
        "scope": {
            "target_date": target_date,
            "symbols": len(manifest_symbols),
            "dependent_indicators": list(DEPENDENT_INDICATORS),
            "source_columns": sorted(allowed_source_columns),
        },
        "daily_calculation_sequences": {
            str(plan["symbol"]): dict(plan.get("daily_input") or {})
            for plan in plans
            if isinstance(plan, Mapping)
        },
        "inputs": {
            "dryrun_manifest": str(dryrun_manifest_path.resolve()),
            "dryrun_manifest_sha256": _sha256_file(dryrun_manifest_path),
            "price_plan": str(price_plan_path.resolve()),
            "price_plan_sha256": actual_price_file_sha,
            "price_plan_hash": price_plan_hash,
            "allowlist_hash": allowlist_hash,
            "canonical_sha256": price_plan.get("canonical_sha256"),
        },
        "summary": {
            "technical_indicator_cells": sum(
                1 for operation in operations if operation["kind"] == "technical_indicator_cell"
            ),
            "technical_source_cells": source_cells,
            "technical_source_rows": source_rows,
            "cache_indicator_cells": cache_indicator_cells,
            "cache_source_cells": cache_source_cells,
            "cache_operations": len(cache_operations),
            "operations": len(operations),
            "formal_db_write": False,
            "csv_cache_write": False,
        },
        "operations": operations,
        "cache_operations": cache_operations,
        "cache_policy": {
            "sqlite_primary": True,
            "csv_cache_status": "deferred_until_separate_backup_and_narrow_writer",
            "csv_cache_write": False,
            "rule": "Never promote stale CSV over SQLite; update only listed target-plus-existing rows after backup and readback.",
        },
        "rollback": {
            "old_values_embedded": True,
            "required_before_write": [
                "Root review and explicit approval",
                "Formal SQLite backup and transaction drift check",
                "Price-plan/source-row hash verification at write time",
                "Post-write readback of every listed cell",
            ],
        },
    }
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        output_path.with_suffix(output_path.suffix + ".sha256").write_text(
            _sha256_file(output_path) + "\n", encoding="ascii"
        )
    return result


def _verify_price_receipt(
    *,
    receipt_path: Path,
    price_plan: Mapping[str, Any],
    db_path: Path,
) -> dict[str, Any]:
    """Verify the already-applied price repair custody before touching tech data."""
    receipt = _read_json(receipt_path)
    supplied = receipt.get("receipt_sha256")
    body = dict(receipt)
    body.pop("receipt_sha256", None)
    if not isinstance(supplied, str) or supplied != _price_payload_hash(body):
        raise TechnicalApplyError("price receipt hash mismatch")
    if receipt.get("receipt_kind") != "historical_price_spike_repair":
        raise TechnicalApplyError("price receipt kind mismatch")
    if receipt.get("status") != "applied":
        raise TechnicalApplyError("price receipt is not applied")
    if str(receipt.get("source_date", "")) != TARGET_DATE:
        raise TechnicalApplyError("price receipt source date mismatch")
    if str(receipt.get("plan_hash", "")) != str(price_plan.get("plan_hash", "")):
        raise TechnicalApplyError("price receipt and price plan hash mismatch")
    if str(receipt.get("allowlist_hash", "")) != str(price_plan.get("allowlist_hash", "")):
        raise TechnicalApplyError("price receipt and allowlist hash mismatch")
    recorded_db = Path(str(receipt.get("db_path", ""))).resolve()
    if recorded_db != db_path.resolve():
        raise TechnicalApplyError("price receipt DB path mismatch")
    backup_path = Path(str(receipt.get("backup_path", ""))).resolve()
    backup_sha = str(receipt.get("backup_sha256", ""))
    if not backup_path.is_file() or backup_path.is_symlink() or _sha256_file(backup_path) != backup_sha:
        raise TechnicalApplyError("price backup custody is missing or changed")
    pending_path = receipt_path.with_name("pending.json")
    if pending_path.is_file():
        pending = _read_json(pending_path)
        if pending.get("status") != "applied_receipt_written":
            raise TechnicalApplyError("price pending receipt is not closed")
    rows = receipt.get("rows")
    if not isinstance(rows, list) or len(rows) != int(price_plan.get("allowlist_count", 0)):
        raise TechnicalApplyError("price receipt row count mismatch")
    return receipt


def _make_online_backup(db_path: Path, backup_path: Path) -> Path:
    if backup_path.exists() or backup_path.is_symlink():
        raise TechnicalApplyError(f"technical backup already exists: {backup_path}")
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    fd, name = tempfile.mkstemp(
        prefix=f".{backup_path.name}.", suffix=".tmp", dir=backup_path.parent
    )
    os.close(fd)
    temporary = Path(name)
    try:
        source = sqlite3.connect(db_path)
        destination = sqlite3.connect(temporary)
        try:
            source.backup(destination)
            destination.commit()
            if str(destination.execute("PRAGMA quick_check").fetchone()[0]).lower() != "ok":
                raise TechnicalApplyError("technical backup quick_check failed")
        finally:
            destination.close()
            source.close()
        temporary.replace(backup_path)
        temporary = None
        return backup_path
    finally:
        if temporary is not None:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass


def _technical_schema(connection: sqlite3.Connection) -> tuple[list[str], str]:
    rows = connection.execute(f'PRAGMA table_info("{TECHNICAL_TABLE}")').fetchall()
    if not rows:
        raise TechnicalApplyError("technical_indicators table missing")
    columns = [str(row[1]) for row in rows]
    if "日期" not in columns or "證券代號" not in columns:
        raise TechnicalApplyError("technical_indicators identity columns missing")
    return columns, _sha256_payload(
        [{"cid": int(row[0]), "name": str(row[1]), "type": str(row[2]), "pk": int(row[5] or 0)} for row in rows]
    )


def _technical_row(
    connection: sqlite3.Connection,
    symbol: str,
    date: str,
    columns: Sequence[str] | None = None,
) -> tuple[list[str], tuple[Any, ...]]:
    resolved_columns = list(columns) if columns is not None else _technical_schema(connection)[0]
    row = connection.execute(
        f'SELECT * FROM "{TECHNICAL_TABLE}" WHERE "證券代號" = ? AND "日期" = ?',
        (symbol, date),
    ).fetchone()
    if row is None:
        raise TechnicalApplyError(f"technical row missing: {(symbol, date)}")
    return resolved_columns, tuple(row)


def _cell_state(
    connection: sqlite3.Connection,
    operations: Sequence[Mapping[str, Any]],
    *,
    expected_key: str | None,
) -> dict[tuple[str, str, str, int], Any]:
    grouped: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    for operation in operations:
        if operation.get("kind") not in {"technical_indicator_cell", "technical_source_cell"}:
            raise TechnicalApplyError(f"unknown technical operation kind: {operation.get('kind')}")
        key = (str(operation.get("symbol", "")), str(operation.get("date", "")))
        grouped.setdefault(key, []).append(operation)
    result: dict[tuple[str, str, str, int], Any] = {}
    columns, _schema_hash = _technical_schema(connection)
    for (symbol, date), row_operations in grouped.items():
        _row_columns, row = _technical_row(connection, symbol, date, columns)
        for operation in row_operations:
            column = str(operation.get("column", ""))
            ordinal = operation.get("column_ordinal")
            if not isinstance(ordinal, int) or ordinal < 0:
                raise TechnicalApplyError(f"invalid technical column ordinal: {column}")
            indexes = [index for index, name in enumerate(columns) if name == column]
            if ordinal >= len(indexes):
                raise TechnicalApplyError(f"technical column occurrence missing: {column}[{ordinal}]")
            key = (symbol, date, column, ordinal)
            if key in result:
                raise TechnicalApplyError(f"duplicate technical operation: {key}")
            result[key] = _json_value(row[indexes[ordinal]])
            expected = _json_value(operation.get(expected_key)) if expected_key else None
            if expected_key is not None and not _values_equal(result[key], expected):
                raise TechnicalApplyError(
                    f"technical {expected_key} drift {symbol}/{date}/{column}[{ordinal}]: "
                    f"actual={result[key]!r} expected={expected!r}"
                )
    return result


def _classify_technical_db_state(
    *,
    db_path: Path,
    operations: Sequence[Mapping[str, Any]],
) -> tuple[str, dict[str, Any]]:
    """Classify a pending writer as all-before, all-after, or unknown."""
    connection = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    try:
        connection.execute("PRAGMA query_only=ON")
        current = _cell_state(connection, operations, expected_key=None)
        quick_check = str(connection.execute("PRAGMA quick_check").fetchone()[0]).lower()
        if quick_check != "ok":
            raise TechnicalApplyError(f"pending DB quick_check failed: {quick_check}")
    finally:
        connection.close()
    before = all(
        _values_equal(current[key], operation.get("old"))
        for operation in operations
        for key in [
            (
                str(operation["symbol"]),
                str(operation["date"]),
                str(operation["column"]),
                int(operation["column_ordinal"]),
            )
        ]
    )
    after = all(
        _values_equal(current[key], operation.get("new"))
        for operation in operations
        for key in [
            (
                str(operation["symbol"]),
                str(operation["date"]),
                str(operation["column"]),
                int(operation["column_ordinal"]),
            )
        ]
    )
    if before and not after:
        state = "all_before"
    elif after and not before:
        state = "all_after"
    elif before and after:
        state = "all_before"
    else:
        state = "unknown"
    return state, {
        "state": state,
        "before_cells_sha256": _operation_cells_hash(operations, "old"),
        "after_cells_sha256": _operation_cells_hash(operations, "new"),
        "quick_check": quick_check,
    }


def _verify_pending_technical_backup(pending: Mapping[str, Any]) -> Path:
    backup_path = Path(str(pending.get("technical_backup_path", ""))).resolve()
    expected = str(pending.get("technical_backup_sha256", ""))
    if not expected or not backup_path.is_file() or backup_path.is_symlink():
        raise TechnicalApplyError("pending technical backup custody is missing")
    actual = _sha256_file(backup_path)
    if actual != expected:
        raise TechnicalApplyError(
            f"pending technical backup hash drift: {actual} != {expected}"
        )
    return backup_path


def _pending_cache_states(
    pending_infos: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """Verify immutable cache journals and classify each file by whole-file hash."""
    normalized: list[dict[str, Any]] = []
    journals: dict[str, dict[str, Any]] = {}
    for raw_info in pending_infos:
        if not isinstance(raw_info, Mapping):
            raise TechnicalApplyError("pending cache file entry is not an object")
        info = dict(raw_info)
        path = Path(str(info.get("path", ""))).resolve()
        if not path.is_file() or path.is_symlink():
            raise TechnicalApplyError(f"pending cache file missing: {path}")
        journal = _read_cache_journal(info)
        journals[str(path)] = journal
        before_sha = str(info.get("before_sha256") or journal.get("before_sha256") or "")
        after_sha = str(info.get("after_sha256") or journal.get("after_sha256") or "")
        if not before_sha or not after_sha:
            raise TechnicalApplyError(f"pending cache hashes missing: {path}")
        actual = _sha256_file(path)
        if actual == before_sha == after_sha:
            state = "unchanged"
        elif actual == before_sha:
            state = "before"
        elif actual == after_sha:
            state = "after"
        else:
            state = "unknown"
        if state == "unknown":
            raise TechnicalApplyError(f"pending cache hash drift: {path}")
        info["before_sha256"] = before_sha
        info["after_sha256"] = after_sha
        info["recovery_state"] = state
        normalized.append(info)
    return normalized, journals


def _restore_pending_caches_before(
    *,
    pending_path: Path,
    pending: dict[str, Any],
    cache_infos: list[dict[str, Any]],
    journals: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Restore only published cache cells to their journaled before values."""
    staging_dir = pending_path.parent / "recovery_staging"
    pending["status"] = "recovery_in_progress"
    pending["formal_data_written"] = False
    pending["recovery"] = {
        "mode": "restore_before_db_commit",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "row_bound": True,
    }
    _write_json_atomic(pending_path, pending, replace=True)
    restored = 0
    for index, info in enumerate(cache_infos):
        if info.get("recovery_state") != "after":
            continue
        path = Path(str(info["path"])).resolve()
        info["status"] = "restoring_before"
        pending["cache_files"] = [_cache_public_info(item) for item in cache_infos]
        _write_json_atomic(pending_path, pending, replace=True)
        journal = journals[str(path)]
        inverse = _inverse_operations(journal.get("operations", []))
        if inverse:
            staged = _stage_cache_file(
                path=path,
                operations=inverse,
                staging_dir=staging_dir,
                label=f"recover_{index:04d}_{path.stem}",
            )
            os.replace(Path(str(staged["staging_path"])), path)
        if _sha256_file(path) != str(info["before_sha256"]):
            raise TechnicalApplyError(f"pending cache restore hash mismatch: {path}")
        info["status"] = "restored_before"
        info["recovery_state"] = "before"
        restored += 1
        pending["cache_files"] = [_cache_public_info(item) for item in cache_infos]
        _write_json_atomic(pending_path, pending, replace=True)
    pending["status"] = "recovered_before_db_commit"
    pending["formal_data_written"] = False
    pending.setdefault("recovery", {})["restored_files"] = restored
    pending["recovery"]["completed_at"] = datetime.now(timezone.utc).isoformat()
    pending["cache_files"] = [_cache_public_info(item) for item in cache_infos]
    _write_json_atomic(pending_path, pending, replace=True)
    return {
        "status": "recovered_before_db_commit",
        "restored_cache_files": restored,
        "pending_path": str(pending_path.resolve()),
    }


def _technical_apply_operations(
    connection: sqlite3.Connection,
    operations: Sequence[Mapping[str, Any]],
    *,
    expected_key: str,
    value_key: str,
) -> tuple[str, str, int]:
    """Check every listed old cell, update it, and verify its new value."""
    columns, _schema_hash = _technical_schema(connection)
    before = _cell_state(connection, operations, expected_key=expected_key)
    before_hash = _sha256_payload(
        [{"key": list(key), "value": value} for key, value in sorted(before.items())]
    )
    changed = 0
    total_changes_before = connection.total_changes
    grouped: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    for operation in operations:
        grouped.setdefault((str(operation["symbol"]), str(operation["date"])), []).append(operation)
    for (symbol, date), row_operations in grouped.items():
        assignments: list[str] = []
        values: list[Any] = []
        seen_columns: set[str] = set()
        for operation in row_operations:
            column = str(operation["column"])
            if column in seen_columns or sum(name == column for name in columns) != 1:
                raise TechnicalApplyError(
                    f"writer requires unique SQL column name; duplicate schema field: {column}"
                )
            seen_columns.add(column)
            assignments.append(f'"{column.replace(chr(34), chr(34) * 2)}" = ?')
            values.append(operation.get(value_key))
        values.extend((symbol, date))
        cursor = connection.execute(
            f'UPDATE "{TECHNICAL_TABLE}" SET {", ".join(assignments)} '
            'WHERE "證券代號" = ? AND "日期" = ?',
            values,
        )
        if cursor.rowcount != 1:
            raise TechnicalApplyError(f"technical row update count != 1: {(symbol, date)}")
        changed += len(row_operations)
    total_changes = connection.total_changes - total_changes_before
    if total_changes != len(grouped):
        raise TechnicalApplyError(
            "technical trigger/extra-change drift: "
            f"{total_changes} != {len(grouped)} row updates"
        )
    after = _cell_state(
        connection,
        [
            {**dict(operation), "old": operation.get(value_key)}
            for operation in operations
        ],
        expected_key="old",
    )
    expected_after = {
        (str(operation["symbol"]), str(operation["date"]), str(operation["column"]), int(operation["column_ordinal"])):
        _json_value(operation.get(value_key))
        for operation in operations
    }
    if any(not _values_equal(after.get(key), value) for key, value in expected_after.items()):
        raise TechnicalApplyError("technical after-cell verification failed")
    after_hash = _sha256_payload(
        [{"key": list(key), "value": value} for key, value in sorted(after.items())]
    )
    return before_hash, after_hash, changed


def _validate_technical_before_cells(
    *,
    db_path: Path,
    operations: Sequence[Mapping[str, Any]],
) -> str:
    """Acquire a write reservation and check listed DB cells before cache publish."""
    connection = sqlite3.connect(db_path, timeout=60)
    try:
        connection.execute("BEGIN IMMEDIATE")
        before = _cell_state(connection, operations, expected_key="old")
        if str(connection.execute("PRAGMA quick_check").fetchone()[0]).lower() != "ok":
            raise TechnicalApplyError("technical preflight quick_check failed")
        connection.rollback()
        return _sha256_payload(
            [{"key": list(key), "value": value} for key, value in sorted(before.items())]
        )
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _verify_daily_calculation_sequences(
    *,
    db_path: Path,
    plans: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Re-read current daily date/OHLC prefixes without applying the overlay."""
    connection = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    try:
        connection.execute("PRAGMA query_only=ON")
        info = connection.execute('PRAGMA table_info("daily_prices")').fetchall()
        columns = [str(row[1]) for row in info]
        def pick(*names: str) -> str:
            for name in names:
                if name in columns:
                    return name
            raise TechnicalApplyError(f"daily_prices 缺少來源欄位：{names}")

        date_column = pick("日期", "Date", "date")
        symbol_column = pick(*SYMBOL_ALIASES)
        field_columns = {
            "open": pick("開盤價", "Open", "open"),
            "high": pick("最高價", "High", "high"),
            "low": pick("最低價", "Low", "low"),
            "close": pick("收盤價", "Close", "close"),
        }
        result: dict[str, Any] = {}
        for plan in plans:
            symbol = str(plan.get("symbol", ""))
            expected = plan.get("daily_input")
            if not isinstance(expected, Mapping):
                raise TechnicalApplyError(f"{symbol} daily_input missing")
            select = ", ".join(
                f'"{name.replace(chr(34), chr(34) * 2)}"'
                for name in (date_column, *field_columns.values())
            )
            rows = connection.execute(
                f'SELECT {select} FROM "daily_prices" WHERE "{symbol_column}" = ? '
                f'ORDER BY "{date_column}" ASC',
                (symbol,),
            ).fetchall()
            sequence: list[dict[str, Any]] = []
            seen_dates: set[str] = set()
            for row in rows:
                date = _date_key(row[0])
                if not date:
                    continue
                if date in seen_dates:
                    raise TechnicalApplyError(f"daily_prices duplicate date: {symbol}/{date}")
                seen_dates.add(date)
                sequence.append(
                    {
                        "date": date,
                        "open": _daily_hash_numeric(row[1]),
                        "high": _daily_hash_numeric(row[2]),
                        "low": _daily_hash_numeric(row[3]),
                        "close": _daily_hash_numeric(row[4]),
                    }
                )
            actual_hash = _sha256_payload(sequence)
            if actual_hash != expected.get("calculation_sequence_sha256"):
                raise TechnicalApplyError(
                    f"daily calculation source drift: {symbol} "
                    f"{actual_hash} != {expected.get('calculation_sequence_sha256')}"
                )
            if len(sequence) != int(expected.get("calculation_sequence_row_count", -1)):
                raise TechnicalApplyError(f"daily calculation row-count drift: {symbol}")
            result[symbol] = {
                "row_count": len(sequence),
                "sha256": actual_hash,
                "first_date": sequence[0]["date"] if sequence else None,
                "last_date": sequence[-1]["date"] if sequence else None,
            }
        return result
    finally:
        connection.close()


def _cache_identity_indices(header: Sequence[str]) -> tuple[int, int]:
    date_index = next((index for index, name in enumerate(header) if name in DATE_ALIASES), None)
    symbol_index = next((index for index, name in enumerate(header) if name in SYMBOL_ALIASES), None)
    if date_index is None or symbol_index is None:
        raise TechnicalApplyError("CSV cache 缺少日期／證券代號欄位")
    return date_index, symbol_index


def _cache_operation_key(operation: Mapping[str, Any]) -> tuple[str, str, str, int]:
    return (
        str(operation.get("symbol", "")),
        str(operation.get("date", "")),
        str(operation.get("column", "")),
        int(operation.get("column_ordinal", 0)),
    )


def _prepare_cache_operations(
    header: Sequence[str], operations: Sequence[Mapping[str, Any]]
) -> tuple[
    int,
    int,
    dict[str, list[int]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    date_index, symbol_index = _cache_identity_indices(header)
    column_indices: dict[str, list[int]] = {}
    for index, name in enumerate(header):
        column_indices.setdefault(str(name), []).append(index)
    prepared_operations: list[dict[str, Any]] = []
    prepared_by_key: dict[tuple[str, str, str, int], dict[str, Any]] = {}
    operation_ids: set[tuple[str, str, str, int]] = set()
    skipped_columns: list[dict[str, Any]] = []
    for operation in operations:
        source_column = str(operation["column"])
        candidate_columns = CACHE_COLUMN_ALIASES.get(source_column, (source_column,))
        requested_ordinal = int(operation["column_ordinal"])
        selected_columns = [candidate for candidate in candidate_columns if candidate in column_indices]
        if not selected_columns:
            skipped_columns.append(
                {
                    "source_column": source_column,
                    "reason": "missing_cache_column_preserved",
                }
            )
            continue
        for selected_column in selected_columns:
            available_ordinals = column_indices[selected_column]
            ordinal = requested_ordinal if requested_ordinal < len(available_ordinals) else 0
            prepared = {
                **dict(operation),
                "source_column": source_column,
                "column": selected_column,
                "column_ordinal": ordinal,
            }
            key = _cache_operation_key(prepared)
            if key in operation_ids:
                previous = prepared_by_key[key]
                if not _values_equal(previous.get("new"), prepared.get("new")):
                    raise TechnicalApplyError(f"cache alias desired values conflict：{key}")
                continue
            operation_ids.add(key)
            prepared_by_key[key] = prepared
            prepared_operations.append(prepared)
    return date_index, symbol_index, column_indices, prepared_operations, skipped_columns


def _stage_cache_file(
    *,
    path: Path,
    operations: Sequence[Mapping[str, Any]],
    staging_dir: Path,
    label: str,
) -> dict[str, Any]:
    """Stream one cache into staging and verify every listed before cell."""
    if not path.is_file() or path.is_symlink():
        raise TechnicalApplyError(f"cache 不存在或是 symlink：{path}")
    if not operations:
        return {
            "path": str(path.resolve()),
            "status": "no_listed_cells",
            "before_sha256": _sha256_file(path),
            "changed_cells": 0,
            "touched_rows": 0,
            "operations": [],
        }
    staging_dir.mkdir(parents=True, exist_ok=True)
    staging_path = staging_dir / f"{label}.staged.csv"
    if staging_path.exists() or staging_path.is_symlink():
        raise TechnicalApplyError(f"cache staging already exists：{staging_path}")
    before_sha = _sha256_file(path)
    cache_encoding, cache_line_ending = _cache_text_format(path)
    operation_map: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    operation_ids: set[tuple[str, str, str, int]] = set()
    seen: set[tuple[str, str, str, int]] = set()
    seen_rows: set[tuple[str, str]] = set()
    effective_operations: list[dict[str, Any]] = []
    changed_cells = 0
    touched_rows = 0
    try:
        with path.open("r", encoding=cache_encoding, newline="") as source, staging_path.open(
            "w", encoding=cache_encoding, newline=""
        ) as destination:
            reader = csv.reader(source)
            writer = csv.writer(destination, lineterminator=cache_line_ending)
            try:
                header = next(reader)
            except StopIteration as exc:
                raise TechnicalApplyError(f"cache 空檔：{path}") from exc
            (
                date_index,
                symbol_index,
                column_indices,
                prepared_operations,
                skipped_columns,
            ) = _prepare_cache_operations(header, operations)
            for operation in prepared_operations:
                key = _cache_operation_key(operation)
                operation_ids.add(key)
                operation_map.setdefault(key[:2], []).append(operation)
            writer.writerow(header)
            for row in reader:
                if len(row) != len(header):
                    raise TechnicalApplyError(f"cache 欄數漂移：{path}")
                identity = (_csv_symbol(row[symbol_index]), _csv_date_key(row[date_index]))
                row_operations = operation_map.get(identity, [])
                if row_operations:
                    if identity in seen_rows:
                        raise TechnicalApplyError(f"cache identity duplicate：{path.name}:{identity}")
                    seen_rows.add(identity)
                    touched_rows += 1
                    for operation in row_operations:
                        column = str(operation["column"])
                        ordinal = int(operation["column_ordinal"])
                        index = column_indices[column][ordinal]
                        actual = _cache_cell_value(row[index])
                        expected_present = "cache_expected_old" in operation
                        expected = operation.get("cache_expected_old")
                        if expected_present and not _values_equal(actual, expected):
                            raise TechnicalApplyError(
                                f"cache before-cell drift {path.name}:{identity}:{column}[{ordinal}] "
                                f"actual={actual!r} expected={expected!r}"
                            )
                        row[index] = _normalise_csv_value(operation.get("new"))
                        seen.add(_cache_operation_key(operation))
                        effective_operations.append(
                            {
                                **dict(operation),
                                "old": actual,
                                "new": _json_value(operation.get("new")),
                                "cache_expected_old": actual,
                            }
                        )
                        changed_cells += 1
                writer.writerow(row)
            destination.flush()
            os.fsync(destination.fileno())
    except Exception:
        try:
            staging_path.unlink()
        except FileNotFoundError:
            pass
        raise
    missing = operation_ids.difference(seen)
    after_sha = _sha256_file(staging_path)
    if missing and effective_operations:
        status = "staged_with_missing_rows"
    elif missing:
        status = "missing_rows"
    elif not prepared_operations:
        status = "no_present_columns"
    else:
        status = "staged"
    return {
        "path": str(path.resolve()),
        "status": status,
        "before_sha256": before_sha,
        "staging_path": str(staging_path.resolve()),
        "after_sha256": after_sha,
        "changed_cells": changed_cells,
        "touched_rows": touched_rows,
        "missing_cell_count": len(missing),
        "missing_cell_samples": [list(item) for item in sorted(missing)[:5]],
        "skipped_columns": skipped_columns,
        "operations": effective_operations,
    }


def _cache_specs(data_root: Path, operations: Sequence[Mapping[str, Any]]) -> list[tuple[Path, list[Mapping[str, Any]], str]]:
    technical_dir = data_root / "technical_analysis"
    by_symbol: dict[str, list[Mapping[str, Any]]] = {}
    for operation in operations:
        by_symbol.setdefault(str(operation["symbol"]), []).append(operation)
    specs: list[tuple[Path, list[Mapping[str, Any]], str]] = [
        (technical_dir / f"{symbol}_indicators.csv", symbol_operations, f"technical_{symbol}")
        for symbol, symbol_operations in sorted(by_symbol.items())
    ]
    specs.append(
        (
            data_root / "meta_data" / "all_stocks_data.csv",
            list(operations),
            "all_stocks_data",
        )
    )
    return specs


def _stage_all_caches(
    *,
    data_root: Path,
    operations: Sequence[Mapping[str, Any]],
    staging_dir: Path,
) -> list[dict[str, Any]]:
    return [
        _stage_cache_file(
            path=path,
            operations=file_operations,
            staging_dir=staging_dir,
            label=label,
        )
        for path, file_operations, label in _cache_specs(data_root, operations)
    ]


def _capacity_preflight(
    *,
    db_path: Path,
    data_root: Path,
    operations: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Check bounded free space before creating any backup or pending state."""
    cache_paths = [path for path, _ops, _label in _cache_specs(data_root, operations)]
    db_size = int(db_path.stat().st_size)
    cache_sizes = {
        str(path.resolve()): int(path.stat().st_size)
        for path in cache_paths
        if path.is_file() and not path.is_symlink()
    }
    cache_bytes = sum(cache_sizes.values())
    required_bytes = (
        CAPACITY_RESERVE_BYTES
        + db_size
        + (cache_bytes * 2)
        + CAPACITY_HEADROOM_BYTES
    )
    usage = shutil.disk_usage(str(data_root))
    if int(usage.free) < required_bytes:
        raise TechnicalApplyError(
            "insufficient free space for bounded technical repair: "
            f"free={usage.free} required={required_bytes}"
        )
    return {
        "volume": str(Path(data_root).anchor or data_root),
        "free_bytes": int(usage.free),
        "required_bytes": int(required_bytes),
        "reserve_bytes": CAPACITY_RESERVE_BYTES,
        "headroom_bytes": CAPACITY_HEADROOM_BYTES,
        "db_bytes": db_size,
        "cache_bytes": cache_bytes,
        "cache_file_count": len(cache_sizes),
        "cache_sizes": cache_sizes,
    }


def _write_cache_journals(
    cache_infos: Sequence[dict[str, Any]],
    journal_dir: Path,
) -> None:
    """Persist immutable per-file old/new cell custody before publishing."""
    journal_dir.mkdir(parents=True, exist_ok=True)
    for index, info in enumerate(cache_infos):
        if info.get("status") not in {
            "staged",
            "staged_with_missing_rows",
            "no_present_columns",
        }:
            continue
        path = Path(str(info["path"]))
        journal_path = journal_dir / f"{index:04d}_{path.name}.cells.json"
        payload = {
            "schema_version": "technical-indicator-cache-cell-journal-20260520.v1",
            "cache_path": str(path.resolve()),
            "before_sha256": info.get("before_sha256"),
            "after_sha256": info.get("after_sha256"),
            "changed_cells": info.get("changed_cells", 0),
            "skipped_columns": info.get("skipped_columns", []),
            "operations": info.get("operations", []),
        }
        payload["journal_sha256"] = _price_payload_hash(payload)
        _write_json_atomic(journal_path, payload, replace=False)
        info["journal_path"] = str(journal_path.resolve())
        info["journal_sha256"] = str(payload["journal_sha256"])


def _read_cache_journal(info: Mapping[str, Any]) -> dict[str, Any]:
    journal_path = Path(str(info.get("journal_path", ""))).resolve()
    journal = _read_json(journal_path)
    body = dict(journal)
    supplied = body.pop("journal_sha256", None)
    if supplied != _price_payload_hash(body):
        raise TechnicalApplyError(f"cache journal hash mismatch：{journal_path}")
    if str(journal.get("cache_path", "")) != str(Path(str(info.get("path", ""))).resolve()):
        raise TechnicalApplyError(f"cache journal path mismatch：{journal_path}")
    if str(info.get("journal_sha256", "")) != str(supplied):
        raise TechnicalApplyError(f"cache journal reference drift：{journal_path}")
    if not isinstance(journal.get("operations"), list):
        raise TechnicalApplyError(f"cache journal operations missing：{journal_path}")
    return journal


def _copy_cache_backup(path: Path, backup_path: Path) -> None:
    if backup_path.exists() or backup_path.is_symlink():
        raise TechnicalApplyError(f"cache backup already exists：{backup_path}")
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, backup_path)
    # Windows rejects fsync on a read-only descriptor; ``r+b`` still keeps
    # the backup bytes untouched while giving the durability call a valid
    # descriptor.
    with backup_path.open("r+b") as stream:
        os.fsync(stream.fileno())


def _replace_staged_caches(
    cache_infos: Sequence[Mapping[str, Any]],
    backup_dir: Path,
    *,
    journal: list[dict[str, Any]] | None = None,
    progress_callback: Any | None = None,
) -> list[dict[str, Any]]:
    applied: list[dict[str, Any]] = journal if journal is not None else []
    for index, info in enumerate(cache_infos):
        if info.get("status") not in {"staged", "staged_with_missing_rows"}:
            continue
        path = Path(str(info["path"]))
        staging_path = Path(str(info["staging_path"]))
        before_sha = _sha256_file(path)
        if before_sha != info.get("before_sha256"):
            raise TechnicalApplyError(f"cache drift before replace：{path}")
        backup_path = backup_dir / f"{index:04d}_{path.name}.before"
        _copy_cache_backup(path, backup_path)
        backup_sha = _sha256_file(backup_path)
        if backup_sha != before_sha:
            raise TechnicalApplyError(f"cache backup hash mismatch：{path}")
        journal_entry = {
            **dict(info),
            "status": "publishing",
            "backup_path": str(backup_path.resolve()),
            "backup_sha256": backup_sha,
        }
        applied.append(journal_entry)
        if progress_callback is not None:
            progress_callback(applied)
        os.replace(staging_path, path)
        journal_entry["status"] = "published"
        if progress_callback is not None:
            progress_callback(applied)
        if _sha256_file(path) != info.get("after_sha256"):
            raise TechnicalApplyError(f"cache after replace hash mismatch：{path}")
    return applied


def _cache_public_info(info: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in info.items()
        if key != "operations"
    }


def _inverse_operations(operations: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            **dict(operation),
            "old": operation.get("new"),
            "new": operation.get("old"),
            **(
                {
                    "cache_expected_old": operation.get("new"),
                }
                if "cache_expected_old" in operation
                else {}
            ),
        }
        for operation in operations
    ]


def _rollback_cache_changes(
    *,
    cache_infos: Sequence[Mapping[str, Any]],
    staging_dir: Path,
) -> None:
    """Restore only listed cache cells after a pre-commit failure."""
    for index, info in enumerate(cache_infos):
        if info.get("status") != "published" or not info.get("operations"):
            continue
        path = Path(str(info["path"]))
        inverse = _inverse_operations(info["operations"])
        rollback_info = _stage_cache_file(
            path=path,
            operations=inverse,
            staging_dir=staging_dir,
            label=f"rollback_{index:04d}_{path.stem}",
        )
        os.replace(Path(str(rollback_info["staging_path"])), path)


def _pending_apply_payload(
    *,
    plan_result: Mapping[str, Any],
    receipt: Mapping[str, Any],
    db_path: Path,
    backup_path: Path,
    status: str,
    cache_infos: Sequence[Mapping[str, Any]] = (),
    cache_backups: Sequence[Mapping[str, Any]] = (),
    technical_backup_sha256: str | None = None,
) -> dict[str, Any]:
    journal = list(cache_backups) if cache_backups else list(cache_infos)
    return {
        "schema_version": "technical-indicator-repair-apply-20260520.v1",
        "receipt_kind": "technical_indicator_repair_pending",
        "status": status,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_date": TARGET_DATE,
        "plan_hash": plan_result["inputs"]["price_plan_hash"],
        "price_plan_sha256": plan_result["inputs"]["price_plan_sha256"],
        "dryrun_manifest_sha256": plan_result["inputs"]["dryrun_manifest_sha256"],
        "price_receipt": str(receipt.get("receipt_sha256", "")),
        "price_receipt_path": str(receipt.get("_receipt_path", "")),
        "price_plan_path": plan_result["inputs"]["price_plan"],
        "dryrun_manifest_path": plan_result["inputs"]["dryrun_manifest"],
        "db_path": str(db_path.resolve()),
        "technical_backup_path": str(backup_path.resolve()),
        "technical_backup_sha256": technical_backup_sha256
        if technical_backup_sha256 is not None
        else (_sha256_file(backup_path) if backup_path.is_file() else None),
        "capacity_preflight": plan_result.get("capacity_preflight"),
        "cache_files": [_cache_public_info(info) for info in journal],
        "formal_data_written": status
        in {"db_committed", "db_committed_receipt_pending", "receipt_written"},
    }


def apply_technical_plan(
    *,
    dryrun_manifest_path: Path,
    price_plan_path: Path,
    price_receipt_path: Path,
    data_root: Path,
    receipt_dir: Path,
    lock_path: Path,
    backup_path: Path | None = None,
    expected_plan_hash: str | None = None,
    expected_price_file_sha256: str | None = None,
    confirm: str | None = None,
) -> dict[str, Any]:
    """Apply listed DB/cache cells after all custody and before-cell checks."""
    if confirm != CONFIRM_TOKEN:
        raise TechnicalApplyError(f"--apply requires --confirm {CONFIRM_TOKEN}")
    plan_result = build_apply_plan(
        dryrun_manifest_path=dryrun_manifest_path,
        price_plan_path=price_plan_path,
        expected_plan_hash=expected_plan_hash,
        expected_price_file_sha256=expected_price_file_sha256,
    )
    price_plan = _read_json(price_plan_path)
    db_path = Path(str(price_plan.get("db_path", ""))).resolve()
    if not db_path.is_file() or db_path.is_symlink():
        raise TechnicalApplyError(f"technical DB 不存在或是 symlink：{db_path}")
    receipt = _verify_price_receipt(
        receipt_path=price_receipt_path,
        price_plan=price_plan,
        db_path=db_path,
    )
    receipt = {**receipt, "_receipt_path": str(price_receipt_path.resolve())}
    if receipt.get("plan_hash") != plan_result["inputs"]["price_plan_hash"]:
        raise TechnicalApplyError("price receipt / technical plan hash mismatch")
    receipt_dir = receipt_dir.expanduser().resolve(strict=False)
    receipt_dir.mkdir(parents=True, exist_ok=True)
    final_path = receipt_dir / "receipt.json"
    pending_path = receipt_dir / "pending.json"
    if final_path.exists() or final_path.is_symlink():
        raise TechnicalApplyError(f"technical final receipt already exists：{final_path}")
    if pending_path.exists() or pending_path.is_symlink():
        raise TechnicalApplyError(f"technical pending receipt already exists：{pending_path}")
    backup_path = (backup_path or receipt_dir / "technical_sqlite_before_repair.db").resolve()
    if backup_path == db_path or backup_path.exists() or backup_path.is_symlink():
        raise TechnicalApplyError(f"technical backup path invalid：{backup_path}")

    operations = list(plan_result["operations"])
    cache_operations = list(plan_result.get("cache_operations", []))
    if not operations:
        raise TechnicalApplyError("technical repair has no listed operations")
    data_root = data_root.expanduser().resolve()
    staging_dir = receipt_dir / "staging"
    cache_backup_dir = receipt_dir / "cache_backups"
    reservation = acquire_heavy_chain_reservation(lock_path.expanduser().resolve())
    if reservation is None:
        raise TechnicalApplyError(f"maintenance lock unavailable：{lock_path}")
    cache_infos: list[dict[str, Any]] = []
    cache_applied: list[dict[str, Any]] = []
    db_committed = False
    preflight_before_hash: str | None = None
    daily_sequence_state: dict[str, Any] = {}
    technical_backup_sha256: str | None = None
    try:
        # Run this before creating pending state or the formal backup.  Store
        # the immutable measurement in the in-memory plan so every pending
        # update carries the same bounded preflight evidence without
        # rescanning sources.
        plan_result["capacity_preflight"] = _capacity_preflight(
            db_path=db_path,
            data_root=data_root,
            operations=cache_operations or operations,
        )
        _write_json_atomic(
            pending_path,
            _pending_apply_payload(
                plan_result=plan_result,
                receipt=receipt,
                db_path=db_path,
                backup_path=backup_path,
                status="preparing",
            ),
            replace=False,
        )
        _make_online_backup(db_path, backup_path)
        technical_backup_sha256 = _sha256_file(backup_path)
        _write_json_atomic(
            pending_path,
            _pending_apply_payload(
                plan_result=plan_result,
                receipt=receipt,
                db_path=db_path,
                backup_path=backup_path,
                status="backup_ready",
                technical_backup_sha256=technical_backup_sha256,
            ),
            replace=True,
        )
        preflight_before_hash = _validate_technical_before_cells(
            db_path=db_path,
            operations=operations,
        )
        daily_sequence_state = _verify_daily_calculation_sequences(
            db_path=db_path,
            plans=[
                {"symbol": symbol, "daily_input": daily_input}
                for symbol, daily_input in plan_result["daily_calculation_sequences"].items()
            ],
        )
        cache_infos = _stage_all_caches(
            data_root=data_root,
            operations=cache_operations or operations,
            staging_dir=staging_dir,
        )
        # Cache rows are an optional, bounded mirror.  A shorter cache is
        # recorded as missing_rows and its existing intersection is staged;
        # no new row is ever inserted and the formal DB remains authoritative.
        _write_cache_journals(cache_infos, receipt_dir / "cache_journals")
        _write_json_atomic(
            pending_path,
            _pending_apply_payload(
                plan_result=plan_result,
                receipt=receipt,
                db_path=db_path,
                backup_path=backup_path,
                status="cache_staged",
                cache_infos=cache_infos,
                technical_backup_sha256=technical_backup_sha256,
            ),
            replace=True,
        )
        def _cache_progress(journal: list[dict[str, Any]]) -> None:
            status = (
                "cache_replaced"
                if len(journal) == len(cache_infos)
                and journal
                and all(item.get("status") == "published" for item in journal)
                else "cache_publishing"
            )
            _write_json_atomic(
                pending_path,
                _pending_apply_payload(
                    plan_result=plan_result,
                    receipt=receipt,
                    db_path=db_path,
                    backup_path=backup_path,
                    status=status,
                    cache_backups=journal,
                    technical_backup_sha256=technical_backup_sha256,
                ),
                replace=True,
            )

        cache_applied = _replace_staged_caches(
            cache_infos,
            cache_backup_dir,
            journal=cache_applied,
            progress_callback=_cache_progress,
        )
        _write_json_atomic(
            pending_path,
            _pending_apply_payload(
                plan_result=plan_result,
                receipt=receipt,
                db_path=db_path,
                backup_path=backup_path,
                status="cache_replaced",
                cache_infos=cache_infos,
                cache_backups=cache_applied,
                technical_backup_sha256=technical_backup_sha256,
            ),
            replace=True,
        )

        connection = sqlite3.connect(db_path, timeout=60)
        try:
            connection.execute("BEGIN IMMEDIATE")
            before_cells_hash, after_cells_hash, changed_cells = _technical_apply_operations(
                connection,
                operations,
                expected_key="old",
                value_key="new",
            )
            if str(connection.execute("PRAGMA quick_check").fetchone()[0]).lower() != "ok":
                raise TechnicalApplyError("technical transaction quick_check failed")
            connection.commit()
            db_committed = True
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        _write_json_atomic(
            pending_path,
            _pending_apply_payload(
                plan_result=plan_result,
                receipt=receipt,
                db_path=db_path,
                backup_path=backup_path,
                status="db_committed",
                cache_infos=cache_infos,
                cache_backups=cache_applied,
                technical_backup_sha256=technical_backup_sha256,
            ),
            replace=True,
        )
        verification = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
        try:
            verification.execute("PRAGMA query_only=ON")
            _cell_state(
                verification,
                [
                    {**dict(operation), "old": operation.get("new")}
                    for operation in operations
                ],
                expected_key="old",
            )
            if str(verification.execute("PRAGMA quick_check").fetchone()[0]).lower() != "ok":
                raise TechnicalApplyError("post-commit technical quick_check failed")
        finally:
            verification.close()
        body: dict[str, Any] = {
            "schema_version": "technical-indicator-repair-apply-20260520.v1",
            "receipt_kind": "technical_indicator_repair",
            "status": "applied",
            "source_date": TARGET_DATE,
            "corrected_at": datetime.now(timezone.utc).isoformat(),
            "db_path": str(db_path),
            "technical_backup_path": str(backup_path),
            "technical_backup_sha256": _sha256_file(backup_path),
            "capacity_preflight": plan_result.get("capacity_preflight"),
            "price_receipt_path": str(price_receipt_path.resolve()),
            "price_receipt_sha256": str(receipt["receipt_sha256"]),
            "price_plan_path": str(price_plan_path.resolve()),
            "price_plan_sha256": plan_result["inputs"]["price_plan_sha256"],
            "price_plan_hash": plan_result["inputs"]["price_plan_hash"],
            "allowlist_hash": plan_result["inputs"]["allowlist_hash"],
            "dryrun_manifest_path": str(dryrun_manifest_path.resolve()),
            "dryrun_manifest_sha256": plan_result["inputs"]["dryrun_manifest_sha256"],
            "before_cells_sha256": before_cells_hash,
            "preflight_before_cells_sha256": preflight_before_hash,
            "daily_calculation_sequences": daily_sequence_state,
            "after_cells_sha256": after_cells_hash,
            "changed_cells": changed_cells,
            "cache_files": [_cache_public_info(info) for info in cache_applied],
            "operations_summary": plan_result["summary"],
            "formal_training_allowed": False,
            "promotion_eligible": False,
            "row_bound_rollback": True,
        }
        final = dict(body)
        final["receipt_sha256"] = _price_payload_hash(body)
        _write_json_atomic(final_path, final, replace=False)
        _write_json_atomic(
            pending_path,
            _pending_apply_payload(
                plan_result=plan_result,
                receipt=receipt,
                db_path=db_path,
                backup_path=backup_path,
                status="receipt_written",
                cache_infos=cache_infos,
                cache_backups=cache_applied,
                technical_backup_sha256=technical_backup_sha256,
            ),
            replace=True,
        )
        return final
    except Exception as exc:
        status = "db_committed_receipt_pending" if db_committed else "failed_before_commit"
        if not db_committed and cache_applied:
            try:
                _rollback_cache_changes(cache_infos=cache_applied, staging_dir=staging_dir)
                status = "cache_rolled_back_before_db_commit"
            except Exception as rollback_exc:
                status = f"cache_rollback_failed:{type(rollback_exc).__name__}"
        try:
            if backup_path.is_file():
                _write_json_atomic(
                    pending_path,
                    _pending_apply_payload(
                        plan_result=plan_result,
                        receipt=receipt,
                        db_path=db_path,
                        backup_path=backup_path,
                        status=status,
                        cache_infos=cache_infos,
                        cache_backups=cache_applied,
                        technical_backup_sha256=technical_backup_sha256,
                    ),
                    replace=True,
                )
        except Exception:
            pass
        raise
    finally:
        release_heavy_chain_reservation(reservation)


def _operation_cells_hash(operations: Sequence[Mapping[str, Any]], value_key: str) -> str:
    values = [
        {
            "key": [
                str(operation["symbol"]),
                str(operation["date"]),
                str(operation["column"]),
                int(operation["column_ordinal"]),
            ],
            "value": _json_value(operation.get(value_key)),
        }
        for operation in operations
    ]
    return _sha256_payload(sorted(values, key=lambda item: item["key"]))


def _resume_technical_receipt_unlocked(
    *,
    pending_path: Path,
    lock_path: Path,
    confirm: str | None = None,
) -> dict[str, Any]:
    """Recover a crash-safe pending apply or finalize its receipt.

    The recovery path never retries a write.  It classifies the formal DB and
    each cache by immutable before/after custody first; an all-before DB gets
    row-bound cache restoration, an all-after DB can only be finalized when
    every owned cache is also after, and any mixed state fails closed.
    """
    if confirm != CONFIRM_TOKEN:
        raise TechnicalApplyError(f"--resume requires --confirm {CONFIRM_TOKEN}")
    pending = _read_json(pending_path)
    resumable_statuses = {
        "cache_publishing",
        "cache_replaced",
        "db_committed",
        "db_committed_receipt_pending",
        "recovery_in_progress",
    }
    if pending.get("status") not in resumable_statuses:
        raise TechnicalApplyError(
            f"pending status cannot be finalized safely: {pending.get('status')}"
        )
    price_plan_path = Path(str(pending.get("price_plan_path", ""))).resolve()
    dryrun_path = Path(str(pending.get("dryrun_manifest_path", ""))).resolve()
    price_receipt_path = Path(str(pending.get("price_receipt_path", ""))).resolve()
    plan_result = build_apply_plan(
        dryrun_manifest_path=dryrun_path,
        price_plan_path=price_plan_path,
        expected_plan_hash=str(pending.get("plan_hash", "")),
        expected_price_file_sha256=str(pending.get("price_plan_sha256", "")),
    )
    if plan_result["inputs"]["dryrun_manifest_sha256"] != str(
        pending.get("dryrun_manifest_sha256", "")
    ):
        raise TechnicalApplyError("pending dry-run manifest hash drift")
    price_plan = _read_json(price_plan_path)
    db_path = Path(str(pending.get("db_path", ""))).resolve()
    receipt = _verify_price_receipt(
        receipt_path=price_receipt_path,
        price_plan=price_plan,
        db_path=db_path,
    )
    _verify_pending_technical_backup(pending)
    operations = list(plan_result["operations"])
    db_state, db_state_evidence = _classify_technical_db_state(
        db_path=db_path,
        operations=operations,
    )
    if db_state == "unknown":
        raise TechnicalApplyError("pending formal DB state is mixed/unknown")
    daily_sequence_state = _verify_daily_calculation_sequences(
        db_path=db_path,
        plans=[
            {"symbol": symbol, "daily_input": daily_input}
            for symbol, daily_input in plan_result["daily_calculation_sequences"].items()
        ],
    )
    pending_infos = pending.get("cache_files", [])
    if not isinstance(pending_infos, list):
        raise TechnicalApplyError("pending cache_files is not a list")
    cache_infos, journals = _pending_cache_states(pending_infos)
    if db_state == "all_before":
        return _restore_pending_caches_before(
            pending_path=pending_path,
            pending=pending,
            cache_infos=cache_infos,
            journals=journals,
        )
    if any(info.get("recovery_state") not in {"after", "unchanged"} for info in cache_infos):
        raise TechnicalApplyError(
            "formal DB is all-after but an owned cache is not all-after"
        )
    for info in cache_infos:
        if info.get("recovery_state") == "after":
            info["status"] = "published"
    final_cache_infos = [_cache_public_info(info) for info in cache_infos]
    final_path = pending_path.with_name("receipt.json")
    if final_path.exists() or final_path.is_symlink():
        raise TechnicalApplyError(f"final receipt already exists: {final_path}")
    body: dict[str, Any] = {
        "schema_version": "technical-indicator-repair-apply-20260520.v1",
        "receipt_kind": "technical_indicator_repair",
        "status": "applied",
        "source_date": TARGET_DATE,
        "corrected_at": datetime.now(timezone.utc).isoformat(),
        "db_path": str(db_path),
        "technical_backup_path": str(pending.get("technical_backup_path", "")),
        "technical_backup_sha256": pending.get("technical_backup_sha256"),
        "capacity_preflight": pending.get("capacity_preflight"),
        "price_receipt_path": str(price_receipt_path),
        "price_receipt_sha256": str(receipt["receipt_sha256"]),
        "price_plan_path": str(price_plan_path),
        "price_plan_sha256": plan_result["inputs"]["price_plan_sha256"],
        "price_plan_hash": plan_result["inputs"]["price_plan_hash"],
        "allowlist_hash": plan_result["inputs"]["allowlist_hash"],
        "dryrun_manifest_path": str(dryrun_path),
        "dryrun_manifest_sha256": plan_result["inputs"]["dryrun_manifest_sha256"],
        "before_cells_sha256": _operation_cells_hash(operations, "old"),
        "after_cells_sha256": _operation_cells_hash(operations, "new"),
        "daily_calculation_sequences": daily_sequence_state,
        "pending_db_state": db_state_evidence,
        "changed_cells": len(operations),
        "cache_files": final_cache_infos,
        "operations_summary": plan_result["summary"],
        "formal_training_allowed": False,
        "promotion_eligible": False,
        "row_bound_rollback": True,
        "resumed_from_pending": str(pending_path.resolve()),
    }
    final = dict(body)
    final["receipt_sha256"] = _price_payload_hash(body)
    _write_json_atomic(final_path, final, replace=False)
    pending["status"] = "receipt_written"
    pending["formal_data_written"] = True
    pending["cache_files"] = final_cache_infos
    pending["pending_db_state"] = db_state_evidence
    pending["resumed_at"] = datetime.now(timezone.utc).isoformat()
    _write_json_atomic(pending_path, pending, replace=True)
    return final


def resume_technical_receipt(
    *,
    pending_path: Path,
    lock_path: Path,
    confirm: str | None = None,
) -> dict[str, Any]:
    """Resume a pending post-commit receipt while holding the shared lock."""
    if confirm != CONFIRM_TOKEN:
        raise TechnicalApplyError(f"--resume requires --confirm {CONFIRM_TOKEN}")
    reservation = acquire_heavy_chain_reservation(lock_path.expanduser().resolve())
    if reservation is None:
        raise TechnicalApplyError(f"maintenance lock unavailable: {lock_path}")
    try:
        return _resume_technical_receipt_unlocked(
            pending_path=pending_path,
            lock_path=lock_path,
            confirm=confirm,
        )
    finally:
        release_heavy_chain_reservation(reservation)


def rollback_technical_receipt(
    *,
    receipt_path: Path,
    lock_path: Path,
    confirm: str | None = None,
) -> dict[str, Any]:
    """Restore only the cells listed in an applied technical receipt."""
    if confirm != CONFIRM_TOKEN:
        raise TechnicalApplyError(f"--rollback requires --confirm {CONFIRM_TOKEN}")
    receipt = _read_json(receipt_path)
    body = dict(receipt)
    supplied = body.pop("receipt_sha256", None)
    if receipt.get("receipt_kind") != "technical_indicator_repair" or receipt.get("status") != "applied":
        raise TechnicalApplyError("rollback requires an applied technical receipt")
    if supplied != _price_payload_hash(body):
        raise TechnicalApplyError("technical receipt hash mismatch")
    db_path = Path(str(receipt.get("db_path", ""))).resolve()
    backup_path = Path(str(receipt.get("technical_backup_path", ""))).resolve()
    if not backup_path.is_file() or _sha256_file(backup_path) != receipt.get("technical_backup_sha256"):
        raise TechnicalApplyError("technical backup custody is missing or changed")
    price_plan_path = Path(str(receipt.get("price_plan_path", ""))).resolve()
    dryrun_path = Path(str(receipt.get("dryrun_manifest_path", ""))).resolve()
    plan_result = build_apply_plan(
        dryrun_manifest_path=dryrun_path,
        price_plan_path=price_plan_path,
        expected_plan_hash=str(receipt.get("price_plan_hash", "")),
    )
    if plan_result["inputs"]["dryrun_manifest_sha256"] != receipt.get("dryrun_manifest_sha256"):
        raise TechnicalApplyError("dry-run manifest changed since apply")
    operations = _inverse_operations(plan_result["operations"])
    rollback_path = receipt_path.with_name("rollback_receipt.json")
    if rollback_path.exists() or rollback_path.is_symlink():
        raise TechnicalApplyError(f"rollback receipt already exists：{rollback_path}")
    reservation = acquire_heavy_chain_reservation(lock_path.expanduser().resolve())
    if reservation is None:
        raise TechnicalApplyError(f"maintenance lock unavailable：{lock_path}")
    cache_inverse_applied: list[tuple[Path, list[dict[str, Any]]]] = []
    cache_staging_dir = receipt_path.parent / "rollback_staging"

    def _apply_cache_cells(
        *,
        label: str,
        inverse: bool,
    ) -> None:
        by_path: dict[Path, list[Mapping[str, Any]]] = {}
        for info in receipt.get("cache_files", []):
            if not isinstance(info, Mapping) or info.get("status") != "published":
                continue
            path = Path(str(info.get("path", ""))).resolve()
            journal = _read_cache_journal(info)
            selected = [dict(operation) for operation in journal["operations"]]
            if inverse:
                selected = _inverse_operations(selected)
            else:
                selected = [
                    {
                        **operation,
                        "cache_expected_old": operation.get("new"),
                    }
                    for operation in selected
                ]
            if selected:
                by_path[path] = selected
        for index, (path, selected) in enumerate(by_path.items()):
            staged = _stage_cache_file(
                path=path,
                operations=selected,
                staging_dir=cache_staging_dir,
                label=f"{label}_{index:04d}_{path.stem}",
            )
            os.replace(Path(str(staged["staging_path"])), path)
            cache_inverse_applied.append((path, [dict(operation) for operation in selected]))

    try:
        _apply_cache_cells(label="inverse", inverse=True)
        connection = sqlite3.connect(db_path, timeout=60)
        try:
            connection.execute("BEGIN IMMEDIATE")
            before_hash, after_hash, changed = _technical_apply_operations(
                connection,
                operations,
                expected_key="old",
                value_key="new",
            )
            connection.commit()
        except Exception:
            connection.rollback()
            # Restore cache cells to the post-apply values if DB rollback
            # failed after the cache inverse had already been published.
            try:
                _apply_cache_cells(label="restore", inverse=False)
            except Exception as restore_exc:
                raise TechnicalApplyError(
                    f"DB rollback failed after cache inverse; cache restore failed: {restore_exc}"
                ) from restore_exc
            raise
        finally:
            connection.close()
        result: dict[str, Any] = {
            "schema_version": "technical-indicator-repair-rollback-20260520.v1",
            "receipt_kind": "technical_indicator_repair_rollback",
            "status": "rolled_back",
            "source_receipt": str(receipt_path.resolve()),
            "source_receipt_sha256": _sha256_file(receipt_path),
            "db_path": str(db_path),
            "before_cells_sha256": before_hash,
            "after_cells_sha256": after_hash,
            "changed_cells": changed,
            "row_bound": True,
            "cache_changed_files": len(cache_inverse_applied),
            "cache_rollback_required": False,
            "cache_policy": "Inverse old/new values were applied to listed cells only; no full-file restore was used.",
        }
        result["receipt_sha256"] = _price_payload_hash(result)
        _write_json_atomic(rollback_path, result, replace=False)
        return result
    finally:
        release_heavy_chain_reservation(reservation)


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dryrun-manifest", type=Path)
    parser.add_argument("--price-plan", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--expected-plan-hash", default=None)
    parser.add_argument("--expected-price-file-sha256", default=None)
    parser.add_argument("--price-receipt", type=Path)
    parser.add_argument("--data-root", type=Path, default=None)
    parser.add_argument("--receipt-dir", type=Path, default=None)
    parser.add_argument("--lock-path", type=Path, default=None)
    parser.add_argument("--backup-path", type=Path, default=None)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--resume", type=Path, default=None)
    parser.add_argument("--rollback", type=Path, default=None)
    parser.add_argument("--confirm", default=None)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        selected_modes = sum(
            bool(value)
            for value in (args.apply, args.resume is not None, args.rollback is not None)
        )
        if selected_modes > 1:
            raise ApplyGuardError("--apply、--resume、--rollback 只能擇一")
        data_root = (args.data_root or Path("F:/Min/Python/Project/FA_Data")).expanduser().resolve()
        lock_path = (
            args.lock_path
            or data_root / "output" / "release_v4" / ".ml_heavy_chain.lock"
        ).resolve()
        if args.rollback is not None:
            result = rollback_technical_receipt(
                receipt_path=args.rollback.resolve(),
                lock_path=lock_path,
                confirm=args.confirm,
            )
            print(json.dumps({"mode": "rollback", "result": result}, ensure_ascii=False))
            return 0
        if args.resume is not None:
            result = resume_technical_receipt(
                pending_path=args.resume.resolve(),
                lock_path=lock_path,
                confirm=args.confirm,
            )
            print(json.dumps({"mode": "resume", "result": result}, ensure_ascii=False))
            return 0
        if args.apply:
            if args.dryrun_manifest is None or args.price_plan is None or args.price_receipt is None:
                raise TechnicalApplyError(
                    "--apply requires --dryrun-manifest, --price-plan and --price-receipt"
                )
            receipt_dir = (
                args.receipt_dir
                or data_root
                / "output"
                / "scheduled"
                / "technical_indicator_repair_receipts"
                / TARGET_DATE
                / "historical_price_spike_20260921"
            ).resolve()
            result = apply_technical_plan(
                dryrun_manifest_path=args.dryrun_manifest.resolve(),
                price_plan_path=args.price_plan.resolve(),
                price_receipt_path=args.price_receipt.resolve(),
                data_root=data_root,
                receipt_dir=receipt_dir,
                lock_path=lock_path,
                backup_path=args.backup_path,
                expected_plan_hash=args.expected_plan_hash,
                expected_price_file_sha256=args.expected_price_file_sha256,
                confirm=args.confirm,
            )
            print(json.dumps({"mode": "applied", "result": result}, ensure_ascii=False))
            return 0
        if args.dryrun_manifest is None or args.price_plan is None or args.output is None:
            raise ApplyGuardError(
                "plan-only requires --dryrun-manifest, --price-plan and --output"
            )
        result = build_apply_plan(
            dryrun_manifest_path=args.dryrun_manifest.resolve(),
            price_plan_path=args.price_plan.resolve(),
            output_path=args.output.resolve(),
            expected_plan_hash=args.expected_plan_hash,
            expected_price_file_sha256=args.expected_price_file_sha256,
        )
    except (ApplyGuardError, DryRunError, OSError, sqlite3.Error, ValueError, KeyError, TypeError) as exc:
        print(f"apply guard failed: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {"output": str(args.output.resolve()), "summary": result["summary"]},
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
