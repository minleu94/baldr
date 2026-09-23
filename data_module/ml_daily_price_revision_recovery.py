"""隔離快照的修訂指標復原工具。

本模組只把已驗證的 repair before rows 與 dry-run after cells 套到隔離
SQLite 複本；不開啟正式資料庫，也不會放寬正式 PIT／training gate。
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sqlite3
from typing import Any, Iterator, Mapping

from data_module.ml_daily_price_revision_technical_snapshot import (
    EXPECTED_COVERAGE,
    EXPECTED_UNTOUCHED_CELLS,
    PRICE_RECEIPT_SCHEMA,
    TECHNICAL_RECEIPT_SCHEMA,
    TARGET_DATE,
    SnapshotEvidenceError,
    _canonical_hash,
    _date_key,
    _fetch_rows,
    _json_object,
    _json_value,
    _open_read_only,
    _quote,
    _schema,
    _sha256_file,
    _symbol_key,
    _values_equal,
    collect_expected_cells,
    verify_technical_rows,
)


RECOVERY_SCHEMA = "ml-daily-price-revision-isolated-recovery.v1"
RECOVERY_CONFIRMATION = "recover-2026-05-20-revision-to-isolated-run02"
FORMAL_DATABASE = Path(r"D:\Min\Python\Project\FA_Data\sqlite\twstock.db")
DIFF_FILENAME = "recovery_cell_diff.jsonl"
ROW_HASH_FILENAME = "affected_row_hashes.jsonl"
RECEIPT_FILENAME = "recovery_receipt.json"


class RecoveryError(SnapshotEvidenceError):
    """隔離復原遇到來源、範圍或 readback 不一致時使用。"""


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _row_hash(row: tuple[Any, ...] | list[Any]) -> str:
    return "sha256:" + hashlib.sha256(_canonical_bytes(_row_values(row))).hexdigest()


def _row_values(row: tuple[Any, ...] | list[Any]) -> list[Any]:
    return [_json_value(value) for value in row]


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _assert_isolated_target(
    *,
    database_path: Path,
    allowed_output_root: Path,
    evidence_directory: Path,
    before_backup_path: Path,
    dryrun_manifest_path: Path,
) -> tuple[Path, Path, Path]:
    """要求寫入目標位於明確隔離根，且與所有來源分離。"""
    target = database_path.expanduser().resolve(strict=False)
    root = allowed_output_root.expanduser().resolve(strict=False)
    evidence = evidence_directory.expanduser().resolve(strict=False)
    backup = before_backup_path.expanduser().resolve(strict=False)
    manifest = dryrun_manifest_path.expanduser().resolve(strict=False)
    if root.is_symlink() or evidence.is_symlink():
        raise RecoveryError("隔離輸出根與證據目錄不可使用 symlink")
    if target.is_symlink() or not target.is_file():
        raise RecoveryError("復原目標不是已存在的一般 SQLite 檔案")
    if not _is_within(target, root) or not _is_within(evidence, root):
        raise RecoveryError("資料庫與證據輸出必須位於指定隔離根內")
    if target in {backup, manifest, FORMAL_DATABASE.resolve(strict=False)}:
        raise RecoveryError("拒絕把來源檔或正式資料庫當作復原目標")
    if _is_within(backup, root):
        raise RecoveryError("隔離輸出根不可與 before backup 重疊")
    if _is_within(manifest, root):
        raise RecoveryError("隔離輸出根不可與 dry-run manifest 重疊")
    if target.drive.casefold() != root.drive.casefold():
        raise RecoveryError("隔離資料庫與輸出根必須位於同一磁碟")
    if database_path.is_symlink() or evidence_directory.is_symlink():
        raise RecoveryError("復原路徑不可使用 symlink")
    return target, root, evidence


def _verify_sealed_receipt(path: Path, *, schema: str, kind: str, label: str) -> dict[str, Any]:
    payload = _json_object(path, label)
    supplied = payload.get("receipt_sha256")
    body = dict(payload)
    body.pop("receipt_sha256", None)
    if payload.get("schema_version") != schema or payload.get("receipt_kind") != kind:
        raise RecoveryError(f"{label} schema 或 kind 不符")
    if supplied != _canonical_hash(body):
        raise RecoveryError(f"{label} body hash 不符")
    return payload


def _verify_recovery_inputs(
    *,
    database_path: Path,
    expected_database_sha256: str,
    before_backup_path: Path,
    dryrun_manifest_path: Path,
    technical_receipt_path: Path,
    price_receipt_path: Path,
    technical_pending_path: Path,
    price_pending_path: Path,
    allowed_output_root: Path,
    evidence_directory: Path,
    confirmation: str,
    require_official_coverage: bool,
) -> tuple[
    Path,
    Path,
    Path,
    Path,
    dict[str, dict[str, dict[tuple[str, int], Any]]],
    dict[str, int],
    dict[str, Any],
]:
    if confirmation != RECOVERY_CONFIRMATION:
        raise RecoveryError("缺少隔離復原確認字串")
    target, root, evidence = _assert_isolated_target(
        database_path=database_path,
        allowed_output_root=allowed_output_root,
        evidence_directory=evidence_directory,
        before_backup_path=before_backup_path,
        dryrun_manifest_path=dryrun_manifest_path,
    )
    before = before_backup_path.expanduser().resolve()
    manifest = dryrun_manifest_path.expanduser().resolve()
    technical_receipt_file = technical_receipt_path.expanduser().resolve()
    price_receipt_file = price_receipt_path.expanduser().resolve()
    technical_pending_file = technical_pending_path.expanduser().resolve()
    price_pending_file = price_pending_path.expanduser().resolve()
    for path, label in (
        (before, "technical before backup"),
        (manifest, "dry-run manifest"),
        (technical_receipt_file, "technical repair receipt"),
        (price_receipt_file, "price repair receipt"),
        (technical_pending_file, "technical pending"),
        (price_pending_file, "price pending"),
    ):
        if path.is_symlink() or not path.is_file():
            raise RecoveryError(f"{label} 不存在或不是一般檔案")
    target_hash = _sha256_file(target)
    if target_hash != expected_database_sha256:
        raise RecoveryError("run02 起始 SQLite hash 與核准來源不符")

    hashes = {
        "run02_before": target_hash,
        "technical_before_backup": _sha256_file(before),
        "dryrun_manifest": _sha256_file(manifest),
        "technical_receipt_file": _sha256_file(technical_receipt_file),
        "price_receipt_file": _sha256_file(price_receipt_file),
        "technical_pending_file": _sha256_file(technical_pending_file),
        "price_pending_file": _sha256_file(price_pending_file),
    }
    technical = _verify_sealed_receipt(
        technical_receipt_file,
        schema=TECHNICAL_RECEIPT_SCHEMA,
        kind="technical_indicator_repair",
        label="technical repair receipt",
    )
    price = _verify_sealed_receipt(
        price_receipt_file,
        schema=PRICE_RECEIPT_SCHEMA,
        kind="historical_price_spike_repair",
        label="price repair receipt",
    )
    if technical.get("status") != "applied" or price.get("status") != "applied":
        raise RecoveryError("來源修復 receipts 必須記錄 applied")
    if technical.get("source_date") != TARGET_DATE or price.get("source_date") != TARGET_DATE:
        raise RecoveryError("來源修復 receipt target date 不符")
    if technical.get("formal_training_allowed") is not False or technical.get("promotion_eligible") is not False:
        raise RecoveryError("technical repair receipt 不再是 formal/PIT 關閉狀態")
    if price.get("formal_training_allowed") is not False or price.get("promotion_eligible") is not False:
        raise RecoveryError("price repair receipt 不再是 formal/PIT 關閉狀態")
    if technical.get("technical_backup_sha256") != hashes["technical_before_backup"]:
        raise RecoveryError("technical before backup hash 與 receipt 不符")
    if technical.get("dryrun_manifest_sha256") != hashes["dryrun_manifest"]:
        raise RecoveryError("dry-run manifest hash 與 receipt 不符")
    if technical.get("price_receipt_sha256") != price.get("receipt_sha256"):
        raise RecoveryError("price receipt body hash 與 technical receipt 不符")
    technical_pending = _json_object(technical_pending_file, "technical pending")
    price_pending = _json_object(price_pending_file, "price pending")
    if (
        technical_pending.get("schema_version") != TECHNICAL_RECEIPT_SCHEMA
        or technical_pending.get("receipt_kind") != "technical_indicator_repair_pending"
        or technical_pending.get("status") != "receipt_written"
        or technical_pending.get("source_date") != TARGET_DATE
    ):
        raise RecoveryError("technical pending schema/kind/status/source_date 不符")
    if (
        technical_pending.get("technical_backup_sha256") != hashes["technical_before_backup"]
        or technical_pending.get("dryrun_manifest_sha256") != hashes["dryrun_manifest"]
        or technical_pending.get("price_receipt") != price.get("receipt_sha256")
    ):
        raise RecoveryError("technical pending 與已封存 receipts/輸入 hash 不一致")
    if (
        price_pending.get("schema_version") != PRICE_RECEIPT_SCHEMA
        or price_pending.get("receipt_kind") != "historical_price_spike_repair_pending"
        or price_pending.get("status") != "applied_receipt_written"
        or price_pending.get("source_date") != TARGET_DATE
        or price_pending.get("plan_hash") != price.get("plan_hash")
        or price_pending.get("allowlist_hash") != price.get("allowlist_hash")
    ):
        raise RecoveryError("price pending schema/kind/status/source_date 不符")
    pending_state = {
        "technical_status": technical_pending.get("status"),
        "price_status": price_pending.get("status"),
        "technical_pending_file_sha256": hashes["technical_pending_file"],
        "price_pending_file_sha256": hashes["price_pending_file"],
        "changed": False,
    }
    expected, coverage = collect_expected_cells(manifest)
    if require_official_coverage and coverage != EXPECTED_COVERAGE:
        raise RecoveryError("dry-run manifest coverage 與正式修復範圍不符")
    if not expected:
        raise RecoveryError("dry-run manifest 沒有修訂列")
    operations_summary = technical.get("operations_summary")
    expected_operations = {
        "operations": coverage["after_cells"],
        "technical_indicator_cells": coverage["indicator_after_cells"],
        "technical_source_cells": coverage["source_after_cells"],
        "technical_source_rows": coverage["symbols"],
    }
    if not isinstance(operations_summary, Mapping) or any(
        operations_summary.get(key) != value for key, value in expected_operations.items()
    ):
        raise RecoveryError("technical receipt operations_summary 與 manifest coverage 不符")
    for output in (evidence / DIFF_FILENAME, evidence / ROW_HASH_FILENAME, evidence / RECEIPT_FILENAME):
        if output.exists() or output.is_symlink():
            raise RecoveryError(f"拒絕覆寫既有復原證據：{output.name}")
    return target, before, manifest, root, expected, coverage, {
        "hashes": hashes,
        "technical_receipt_body_sha256": technical["receipt_sha256"],
        "price_receipt_body_sha256": price["receipt_sha256"],
        "pending_state": pending_state,
        "evidence_directory": evidence,
    }


def _schema_for_recovery(connection: sqlite3.Connection) -> dict[str, Any]:
    schema = _schema(connection)
    columns = list(schema["columns"])
    if len(columns) != len(set(columns)):
        raise RecoveryError("technical_indicators schema 有重複欄名，拒絕按欄位復原")
    primary = [
        str(row[1])
        for row in connection.execute('PRAGMA table_info("technical_indicators")')
        if int(row[5]) > 0
    ]
    if set(primary) != {str(schema["symbol_column"]), str(schema["date_column"])}:
        raise RecoveryError("technical_indicators 主鍵不是預期的證券代號／日期")
    return schema


def _table_digest(
    connection: sqlite3.Connection,
    schema: Mapping[str, Any],
    *,
    excluded_keys: set[tuple[str, str]],
) -> dict[str, Any]:
    """串流計算完整資料表或 plan 外列 hash，避免將全表載入記憶體。"""
    columns = list(schema["columns"])
    symbol_column, date_column = str(schema["symbol_column"]), str(schema["date_column"])
    plan = connection.execute(
        "EXPLAIN QUERY PLAN SELECT * FROM technical_indicators ORDER BY "
        f"{_quote(symbol_column)}, {_quote(date_column)}"
    ).fetchall()
    query_plan = [str(row[3]) for row in plan]
    if not any("INDEX" in line.upper() for line in query_plan):
        raise RecoveryError("plan 外 row hash 未使用 SQLite index，拒絕無界排序掃描")
    symbol_index, date_index = columns.index(symbol_column), columns.index(date_column)
    digest = hashlib.sha256()
    total_rows = 0
    included_rows = 0
    cursor = connection.execute(
        "SELECT * FROM technical_indicators ORDER BY "
        f"{_quote(symbol_column)}, {_quote(date_column)}"
    )
    while batch := cursor.fetchmany(5000):
        for row in batch:
            total_rows += 1
            key = (_symbol_key(row[symbol_index]), _date_key(row[date_index]))
            if key in excluded_keys:
                continue
            digest.update(_canonical_bytes([_json_value(value) for value in row]))
            digest.update(b"\n")
            included_rows += 1
    return {
        "sha256": "sha256:" + digest.hexdigest(),
        "row_count": included_rows,
        "total_table_rows": total_rows,
        "query_plan": query_plan,
    }


def _iter_expected_rows(
    target: sqlite3.Connection,
    before: sqlite3.Connection,
    target_schema: Mapping[str, Any],
    before_schema: Mapping[str, Any],
    expected: Mapping[str, Mapping[str, Mapping[tuple[str, int], Any]]],
) -> Iterator[tuple[str, str, tuple[Any, ...], tuple[Any, ...], Mapping[tuple[str, int], Any]]]:
    """按股票索引讀取受影響列，逐列回傳 target／before rows。"""
    for symbol in sorted(expected):
        current_rows = _fetch_rows(target, target_schema, symbol)
        before_rows = _fetch_rows(before, before_schema, symbol)
        for date in sorted(expected[symbol]):
            current_row = current_rows.get(date)
            before_row = before_rows.get(date)
            if current_row is None or before_row is None:
                raise RecoveryError(f"修訂列缺少 current/before identity：{symbol}/{date}")
            for schema, row in ((target_schema, current_row), (before_schema, before_row)):
                columns = list(schema["columns"])
                symbol_index = columns.index(str(schema["symbol_column"]))
                date_index = columns.index(str(schema["date_column"]))
                if _symbol_key(row[symbol_index]) != _symbol_key(symbol) or _date_key(row[date_index]) != date:
                    raise RecoveryError(f"修訂列 identity 不一致：{symbol}/{date}")
            current_key = tuple(
                current_row[list(target_schema["columns"]).index(column)]
                for column in (str(target_schema["symbol_column"]), str(target_schema["date_column"]))
            )
            before_key = tuple(
                before_row[list(before_schema["columns"]).index(column)]
                for column in (str(before_schema["symbol_column"]), str(before_schema["date_column"]))
            )
            if current_key != before_key:
                raise RecoveryError(f"before/current raw key 不相同：{symbol}/{date}")
            yield symbol, date, current_row, before_row, expected[symbol][date]


def _desired_row(
    *,
    before_row: tuple[Any, ...],
    cells: Mapping[tuple[str, int], Any],
    schema: Mapping[str, Any],
) -> tuple[Any, ...]:
    desired = list(before_row)
    positions = schema["positions"]
    for (column, ordinal), value in cells.items():
        indexes = positions.get(column, [])
        if ordinal >= len(indexes):
            raise RecoveryError(f"dry-run 欄位不存在：{column}[{ordinal}]")
        desired[indexes[ordinal]] = value
    return tuple(desired)


def preview_isolated_recovery(
    *,
    database_path: Path,
    expected_database_sha256: str,
    before_backup_path: Path,
    dryrun_manifest_path: Path,
    technical_receipt_path: Path,
    price_receipt_path: Path,
    technical_pending_path: Path,
    price_pending_path: Path,
    allowed_output_root: Path,
    evidence_directory: Path,
    confirmation: str,
    require_official_coverage: bool = True,
) -> dict[str, Any]:
    """唯讀比較 run02 與 before-plus-after 的預期列，不建立或修改資料。"""
    (
        target_path,
        before_path,
        _manifest,
        _root,
        expected,
        coverage,
        provenance,
    ) = _verify_recovery_inputs(
        database_path=database_path,
        expected_database_sha256=expected_database_sha256,
        before_backup_path=before_backup_path,
        dryrun_manifest_path=dryrun_manifest_path,
        technical_receipt_path=technical_receipt_path,
        price_receipt_path=price_receipt_path,
        technical_pending_path=technical_pending_path,
        price_pending_path=price_pending_path,
        allowed_output_root=allowed_output_root,
        evidence_directory=evidence_directory,
        confirmation=confirmation,
        require_official_coverage=require_official_coverage,
    )
    target, before = _open_read_only(target_path), _open_read_only(before_path)
    try:
        target_schema, before_schema = _schema_for_recovery(target), _schema_for_recovery(before)
        if target_schema["columns"] != before_schema["columns"]:
            raise RecoveryError("run02 與 before backup 的技術資料表 schema 不同")
        affected_keys = {
            (_symbol_key(symbol), date)
            for symbol, dates in expected.items()
            for date in dates
        }
        outside = _table_digest(target, target_schema, excluded_keys=affected_keys)
        digest_target = hashlib.sha256()
        digest_before = hashlib.sha256()
        digest_desired = hashlib.sha256()
        digest_keys = hashlib.sha256()
        changed_cells = 0
        after_cell_mismatches = 0
        restored_untouched_cells = 0
        untouched_cells = 0
        for symbol, date, current_row, before_row, cells in _iter_expected_rows(
            target, before, target_schema, before_schema, expected
        ):
            desired = _desired_row(before_row=before_row, cells=cells, schema=target_schema)
            digest_target.update(_canonical_bytes([symbol, date, _row_values(current_row)]) + b"\n")
            digest_before.update(_canonical_bytes([symbol, date, _row_values(before_row)]) + b"\n")
            digest_desired.update(_canonical_bytes([symbol, date, _row_values(desired)]) + b"\n")
            digest_keys.update(_canonical_bytes([symbol, date]) + b"\n")
            positions = target_schema["positions"]
            modified = set(cells)
            for index, column in enumerate(target_schema["columns"]):
                ordinal = positions[column].index(index)
                key = (column, ordinal)
                if not _values_equal(current_row[index], desired[index]):
                    changed_cells += 1
                if key in modified:
                    if not _values_equal(current_row[index], cells[key]):
                        after_cell_mismatches += 1
                else:
                    untouched_cells += 1
                    if not _values_equal(current_row[index], before_row[index]):
                        restored_untouched_cells += 1
        return {
            "schema_version": RECOVERY_SCHEMA,
            "status": "ready_for_review",
            "mode": "isolated_read_only_preview",
            "formal_data_written": False,
            "formal_training_allowed": False,
            "historical_pit_eligible": False,
            "pending_state": provenance["pending_state"],
            "input_hashes": provenance["hashes"],
            "coverage": coverage,
            "row_hashes": {
                "affected_keys_sha256": "sha256:" + digest_keys.hexdigest(),
                "run02_before_sha256": "sha256:" + digest_target.hexdigest(),
                "technical_before_backup_sha256": "sha256:" + digest_before.hexdigest(),
                "expected_recovery_sha256": "sha256:" + digest_desired.hexdigest(),
                "plan_external_sha256": outside["sha256"],
                "plan_external_rows": outside["row_count"],
                "total_table_rows": outside["total_table_rows"],
            },
            "planned_cell_diff": {
                "changed_cells": changed_cells,
                "after_cell_mismatches_before_recovery": after_cell_mismatches,
                "restored_untouched_cells": restored_untouched_cells,
                "untouched_cells": untouched_cells,
                "expected_untouched_cells": EXPECTED_UNTOUCHED_CELLS,
            },
            "query_plan": outside["query_plan"],
        }
    finally:
        target.close()
        before.close()


def _write_jsonl_line(stream: Any, payload: Mapping[str, Any]) -> None:
    stream.write(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False))
    stream.write("\n")


def _publish_file(temp_path: Path, final_path: Path) -> None:
    if final_path.exists() or final_path.is_symlink():
        raise RecoveryError(f"拒絕覆寫復原證據：{final_path.name}")
    temp_path.rename(final_path)


def _evidence_file(path: Path) -> dict[str, Any]:
    return {"path": str(path.resolve()), "size_bytes": path.stat().st_size, "sha256": _sha256_file(path)}


def apply_isolated_recovery(
    *,
    database_path: Path,
    expected_database_sha256: str,
    before_backup_path: Path,
    dryrun_manifest_path: Path,
    technical_receipt_path: Path,
    price_receipt_path: Path,
    technical_pending_path: Path,
    price_pending_path: Path,
    allowed_output_root: Path,
    evidence_directory: Path,
    confirmation: str,
    require_official_coverage: bool = True,
) -> dict[str, Any]:
    """交易式復原 run02；每個 affected row 以 before 全欄覆蓋，再套用 after cells。"""
    (
        target_path,
        before_path,
        manifest_path,
        root,
        expected,
        coverage,
        provenance,
    ) = _verify_recovery_inputs(
        database_path=database_path,
        expected_database_sha256=expected_database_sha256,
        before_backup_path=before_backup_path,
        dryrun_manifest_path=dryrun_manifest_path,
        technical_receipt_path=technical_receipt_path,
        price_receipt_path=price_receipt_path,
        technical_pending_path=technical_pending_path,
        price_pending_path=price_pending_path,
        allowed_output_root=allowed_output_root,
        evidence_directory=evidence_directory,
        confirmation=confirmation,
        require_official_coverage=require_official_coverage,
    )
    evidence = Path(provenance["evidence_directory"])
    evidence.mkdir(parents=True, exist_ok=True)
    final_diff = evidence / DIFF_FILENAME
    final_rows = evidence / ROW_HASH_FILENAME
    final_receipt = evidence / RECEIPT_FILENAME
    if any(path.exists() or path.is_symlink() for path in (final_diff, final_rows, final_receipt)):
        raise RecoveryError("復原證據檔已存在，拒絕覆寫")
    temp_diff = evidence / f".{DIFF_FILENAME}.{os.getpid()}.tmp"
    temp_rows = evidence / f".{ROW_HASH_FILENAME}.{os.getpid()}.tmp"
    temp_receipt = evidence / f".{RECEIPT_FILENAME}.{os.getpid()}.tmp"
    if any(path.exists() or path.is_symlink() for path in (temp_diff, temp_rows, temp_receipt)):
        raise RecoveryError("復原暫存證據路徑已存在")

    input_hashes = dict(provenance["hashes"])
    target_sidecar_wal = Path(str(target_path) + "-wal")
    if target_sidecar_wal.exists() and target_sidecar_wal.stat().st_size:
        raise RecoveryError("run02 復原前 WAL 非空，拒絕猜測 SQLite 狀態")
    target_connection = sqlite3.connect(target_path, timeout=30, isolation_level=None)
    before_connection = _open_read_only(before_path)
    cleanup_target_connection: sqlite3.Connection | None = target_connection
    cleanup_before_connection: sqlite3.Connection | None = before_connection
    target_connection.execute("PRAGMA busy_timeout=30000")
    target_connection.execute("PRAGMA foreign_keys=ON")
    transaction_started = False
    changed_cell_count = 0
    changed_after_cell_count = 0
    restored_untouched_cell_count = 0
    after_cell_count = 0
    untouched_cell_count = 0
    rows_written = 0
    affected_rows = 0
    digest_keys = hashlib.sha256()
    digest_target_before = hashlib.sha256()
    digest_backup = hashlib.sha256()
    digest_recovered = hashlib.sha256()
    outside_before: dict[str, Any] = {}
    outside_after: dict[str, Any] = {}
    checkpoint: tuple[Any, ...] | None = None
    commit_completed = False
    temp_files = [temp_diff, temp_rows, temp_receipt]
    try:
        target_schema = _schema_for_recovery(target_connection)
        before_schema = _schema_for_recovery(before_connection)
        if target_schema["columns"] != before_schema["columns"]:
            raise RecoveryError("run02 與 before backup 的技術資料表 schema 不同")
        positions = target_schema["positions"]
        symbol_column = str(target_schema["symbol_column"])
        date_column = str(target_schema["date_column"])
        symbol_index = target_schema["columns"].index(symbol_column)
        date_index = target_schema["columns"].index(date_column)
        column_sql = ", ".join(_quote(name) for name in target_schema["columns"])
        update_sql = (
            "UPDATE technical_indicators SET "
            + ", ".join(f"{_quote(name)} = ?" for name in target_schema["columns"])
            + f" WHERE {_quote(symbol_column)} = ? AND {_quote(date_column)} = ?"
        )
        select_sql = (
            f"SELECT {column_sql} FROM technical_indicators "
            f"WHERE {_quote(symbol_column)} = ? AND {_quote(date_column)} = ?"
        )
        target_connection.execute("BEGIN IMMEDIATE")
        transaction_started = True
        affected_keys = {
            (_symbol_key(symbol), date)
            for symbol, dates in expected.items()
            for date in dates
        }
        outside_before = _table_digest(
            target_connection, target_schema, excluded_keys=affected_keys
        )
        if outside_before["total_table_rows"] < len(affected_keys):
            raise RecoveryError("technical_indicators 總列數小於受影響鍵數")
        with temp_diff.open("x", encoding="utf-8", newline="\n") as diff_stream, temp_rows.open(
            "x", encoding="utf-8", newline="\n"
        ) as row_stream:
            for symbol, date, current_row, before_row, cells in _iter_expected_rows(
                target_connection, before_connection, target_schema, before_schema, expected
            ):
                affected_rows += 1
                digest_keys.update(_canonical_bytes([symbol, date]) + b"\n")
                digest_target_before.update(
                    _canonical_bytes([symbol, date, _row_values(current_row)]) + b"\n"
                )
                digest_backup.update(_canonical_bytes([symbol, date, _row_values(before_row)]) + b"\n")
                desired = _desired_row(before_row=before_row, cells=cells, schema=target_schema)
                modified = set(cells)
                row_changes = 0
                for index, column in enumerate(target_schema["columns"]):
                    ordinal = positions[column].index(index)
                    key = (column, ordinal)
                    if key in modified:
                        after_cell_count += 1
                    else:
                        untouched_cell_count += 1
                    if _values_equal(current_row[index], desired[index]):
                        continue
                    row_changes += 1
                    changed_cell_count += 1
                    reason = "repair_after_cell" if key in modified else "restore_before_untouched"
                    if key in modified:
                        changed_after_cell_count += 1
                    else:
                        restored_untouched_cell_count += 1
                    _write_jsonl_line(
                        diff_stream,
                        {
                            "symbol": symbol,
                            "date": date,
                            "column": column,
                            "ordinal": ordinal,
                            "reason": reason,
                            "current_before": _json_value(current_row[index]),
                            "before_backup": _json_value(before_row[index]),
                            "recovered_after": _json_value(desired[index]),
                        },
                    )
                raw_symbol, raw_date = current_row[symbol_index], current_row[date_index]
                if row_changes:
                    cursor = target_connection.execute(
                        update_sql, (*desired, raw_symbol, raw_date)
                    )
                    if cursor.rowcount != 1:
                        raise RecoveryError(f"affected row update 數不為 1：{symbol}/{date}")
                    rows_written += 1
                post = target_connection.execute(select_sql, (raw_symbol, raw_date)).fetchone()
                if post is None or len(post) != len(desired):
                    raise RecoveryError(f"復原後列讀取失敗：{symbol}/{date}")
                if any(not _values_equal(a, b) for a, b in zip(post, desired)):
                    raise RecoveryError(f"復原後 full-row readback 不符：{symbol}/{date}")
                post_tuple = tuple(post)
                for (column, ordinal), expected_value in cells.items():
                    index = positions[column][ordinal]
                    if not _values_equal(post_tuple[index], expected_value):
                        raise RecoveryError(f"after cell readback 不符：{symbol}/{date}/{column}")
                for index, column in enumerate(target_schema["columns"]):
                    ordinal = positions[column].index(index)
                    if (column, ordinal) not in modified and not _values_equal(
                        post_tuple[index], before_row[index]
                    ):
                        raise RecoveryError(f"untouched cell readback 不符：{symbol}/{date}/{column}")
                digest_recovered.update(
                    _canonical_bytes([symbol, date, _row_values(post_tuple)]) + b"\n"
                )
                _write_jsonl_line(
                    row_stream,
                    {
                        "symbol": symbol,
                        "date": date,
                        "run02_before_row_sha256": _row_hash(current_row),
                        "technical_before_backup_row_sha256": _row_hash(before_row),
                        "recovered_row_sha256": _row_hash(post_tuple),
                        "after_cell_count": len(cells),
                        "changed_cell_count": row_changes,
                    },
                )
            diff_stream.flush()
            os.fsync(diff_stream.fileno())
            row_stream.flush()
            os.fsync(row_stream.fileno())
        if affected_rows != coverage["affected_rows"] or after_cell_count != coverage["after_cells"]:
            raise RecoveryError("復原列數或 after cell 數與 manifest 不符")
        if require_official_coverage and untouched_cell_count != EXPECTED_UNTOUCHED_CELLS:
            raise RecoveryError("復原 untouched cell 數與正式 QA 範圍不符")
        outside_after = _table_digest(
            target_connection, target_schema, excluded_keys=affected_keys
        )
        if outside_before["sha256"] != outside_after["sha256"]:
            raise RecoveryError("plan 外 technical rows hash 改變，整筆復原 rollback")
        if outside_before["row_count"] != outside_after["row_count"] or outside_before["total_table_rows"] != outside_after["total_table_rows"]:
            raise RecoveryError("plan 外 row count 改變，整筆復原 rollback")
        check = str(target_connection.execute("PRAGMA quick_check(1)").fetchone()[0]).lower()
        if check != "ok":
            raise RecoveryError("run02 transaction 內 quick_check 失敗")
        target_connection.execute("COMMIT")
        transaction_started = False
        commit_completed = True
        before_connection.close()
        cleanup_before_connection = None
        checkpoint_row = target_connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        checkpoint = tuple(checkpoint_row) if checkpoint_row is not None else None
        if checkpoint is not None and int(checkpoint[0]) != 0:
            raise RecoveryError("run02 WAL checkpoint 未完成")
        check_after = str(target_connection.execute("PRAGMA quick_check(1)").fetchone()[0]).lower()
        if check_after != "ok":
            raise RecoveryError("run02 commit 後 quick_check 失敗")
        target_connection.close()
        cleanup_target_connection = None
    except BaseException as exc:
        if transaction_started:
            try:
                target_connection.execute("ROLLBACK")
            except sqlite3.Error:
                pass
        for connection in (cleanup_target_connection, cleanup_before_connection):
            if connection is not None:
                try:
                    connection.close()
                except sqlite3.Error:
                    pass
        for path in temp_files:
            try:
                if path.is_file() and not path.is_symlink():
                    path.unlink()
            except OSError:
                pass
        if commit_completed:
            raise RecoveryError(
                "RUN02_INVALID_AFTER_COMMIT：commit 後 checkpoint/驗證失敗；"
                "不可重用此 run02，須由 immutable run01 online backup 建新 run 重試"
            ) from exc
        raise

    verification: dict[str, Any]
    try:
        verification = verify_technical_rows(target_path, before_path, expected)
    except Exception as exc:  # noqa: BLE001
        verification = {"status": "error", "reason": type(exc).__name__}
    expected_untouched_cells = (
        EXPECTED_UNTOUCHED_CELLS if require_official_coverage else untouched_cell_count
    )
    verification_passed = (
        verification.get("after_cells") == coverage["after_cells"]
        and verification.get("after_matches") == coverage["after_cells"]
        and verification.get("after_mismatches") == 0
        and verification.get("missing_current_rows") == 0
        and verification.get("untouched_cells") == expected_untouched_cells
        and verification.get("untouched_mismatches") == 0
    )
    report: dict[str, Any] = {
        "schema_version": RECOVERY_SCHEMA,
        "status": "passed" if verification_passed else "failed",
        "mode": "isolated_research_snapshot_recovery",
        "database_path": str(target_path),
        "allowed_output_root": str(root),
        "formal_data_written": False,
        "formal_training_allowed": False,
        "historical_pit_eligible": False,
        "promotion_eligible": False,
        "research_candidate_only": True,
        "pending_state": provenance["pending_state"],
        "input_hashes": input_hashes,
        "database_sha256_after": _sha256_file(target_path),
        "database_size_after": target_path.stat().st_size,
        "database_wal_after": {
            "exists": target_sidecar_wal.exists(),
            "size_bytes": target_sidecar_wal.stat().st_size if target_sidecar_wal.exists() else 0,
        },
        "coverage": coverage,
        "rows": {
            "affected_rows": affected_rows,
            "rows_written": rows_written,
            "rows_already_converged": affected_rows - rows_written,
            "affected_keys_sha256": "sha256:" + digest_keys.hexdigest(),
            "run02_before_rows_sha256": "sha256:" + digest_target_before.hexdigest(),
            "technical_before_backup_rows_sha256": "sha256:" + digest_backup.hexdigest(),
            "recovered_rows_sha256": "sha256:" + digest_recovered.hexdigest(),
            "plan_external_before_sha256": outside_before.get("sha256"),
            "plan_external_after_sha256": outside_after.get("sha256"),
            "plan_external_rows": outside_after.get("row_count"),
            "total_table_rows": outside_after.get("total_table_rows"),
        },
        "cell_diff": {
            "after_cells": after_cell_count,
            "changed_cells": changed_cell_count,
            "changed_after_cells": changed_after_cell_count,
            "restored_untouched_cells": restored_untouched_cell_count,
            "untouched_cells": untouched_cell_count,
            "untouched_mismatches_in_transaction": 0,
        },
        "checkpoint": checkpoint,
        "post_commit_verification": verification,
        "evidence_files": {
            "cell_diff": None,
            "affected_row_hashes": None,
        },
    }
    try:
        for path, final_path, evidence_key in (
            (temp_diff, final_diff, "cell_diff"),
            (temp_rows, final_rows, "affected_row_hashes"),
        ):
            _publish_file(path, final_path)
            report["evidence_files"][evidence_key] = _evidence_file(final_path)
        receipt_body = dict(report)
        report["receipt_sha256"] = _canonical_hash(receipt_body)
        with temp_receipt.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(
                json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
                + "\n"
            )
            stream.flush()
            os.fsync(stream.fileno())
        _publish_file(temp_receipt, final_receipt)
    except Exception as exc:  # noqa: BLE001
        raise RecoveryError(
            "RUN02_INVALID_AFTER_COMMIT：證據封存失敗；不可重用此 run02，"
            "須從 immutable run01 online backup 建立新 run 重試"
        ) from exc
    return report
