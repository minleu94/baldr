"""唯讀驗收 2026-05-20 修訂後的技術指標 SQLite 快照。

此模組將既有獨立 QA 的 bounded readback 方法納入可追蹤程式碼，逐股讀取
dry-run manifest 列出的修訂欄位，並與修復前 online backup 比對未修改欄位。
它不寫入資料庫、不解除正式 PIT gate，也不提供模型訓練輸入。
"""
from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
import hashlib
import json
import math
from pathlib import Path
import sqlite3
from typing import Any

EVIDENCE_SCHEMA = "ml-daily-price-revision-technical-snapshot-evidence.v1"
TECHNICAL_RECEIPT_SCHEMA = "technical-indicator-repair-apply-20260520.v1"
PRICE_RECEIPT_SCHEMA = "historical-price-spike-repair-20260921.v1"
TARGET_DATE = "20260520"
EXPECTED_COVERAGE = {
    "symbols": 868,
    "affected_rows": 75_442,
    "indicator_after_cells": 1_257_696,
    "source_after_cells": 19_439,
    "after_cells": 1_277_135,
}
EXPECTED_UNTOUCHED_CELLS = 2_117_755
# 歷史 ignored QA verifier 的來源 hash 僅供溯源；重跑只依賴下方 tracked verifier。
ORIGINAL_QA_VERIFIER_REFERENCE_SHA256 = (
    "sha256:19543576338c2ccda9b61b7c06bf047dd21e15f4a978cd525354d5bdce359bc9"
)
DATE_COLUMNS = ("日期", "Date", "date")
SYMBOL_COLUMNS = ("證券代號", "股票代號", "stock_code", "stock_id", "Code", "code")


class SnapshotEvidenceError(ValueError):
    """修訂快照證據缺漏或不一致時使用。"""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _canonical_hash(payload: Mapping[str, Any]) -> str:
    encoded = (json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _json_object(path: Path, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise SnapshotEvidenceError(f"{label} 不是一般檔案：{path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SnapshotEvidenceError(f"{label} 無法讀取：{path}") from exc
    if not isinstance(payload, dict):
        raise SnapshotEvidenceError(f"{label} 根節點不是物件")
    return payload


def _date_key(value: Any) -> str:
    text = "" if value is None else str(value).strip()
    digits = "".join(character for character in text if character.isdigit())
    return digits[:8] if len(digits) >= 8 else ""


def _symbol_key(value: Any) -> str:
    text = "" if value is None else str(value).strip()
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    if text.isdigit():
        return str(int(text))
    return text


def _json_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (int, str, bool)):
        return value
    return str(value)


def _values_equal(left: Any, right: Any) -> bool:
    left, right = _json_value(left), _json_value(right)
    if left is None or right is None:
        return left is None and right is None
    try:
        from decimal import Decimal, InvalidOperation

        return Decimal(str(left).replace(",", "")) == Decimal(str(right).replace(",", ""))
    except (InvalidOperation, ValueError):
        return str(left).strip() == str(right).strip()


def _iter_array_objects(path: Path, key: str) -> Iterator[dict[str, Any]]:
    """以串流方式讀取大型 JSON 文件中的單一頂層陣列。"""
    marker = f'"{key}"'
    decoder = json.JSONDecoder()
    buffer = ""
    found = False
    with path.open("r", encoding="utf-8") as stream:
        while not found:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                raise SnapshotEvidenceError(f"manifest 找不到陣列：{key}")
            buffer += chunk
            marker_index = buffer.find(marker)
            if marker_index >= 0:
                array_index = buffer.find("[", marker_index + len(marker))
                if array_index >= 0:
                    buffer = buffer[array_index + 1 :]
                    found = True
        while True:
            while True:
                buffer = buffer.lstrip()
                if buffer.startswith(","):
                    buffer = buffer[1:]
                    continue
                if buffer:
                    break
                chunk = stream.read(1024 * 1024)
                if not chunk:
                    raise SnapshotEvidenceError(f"manifest 陣列未結束：{key}")
                buffer += chunk
            if buffer.startswith("]"):
                return
            while True:
                try:
                    value, end = decoder.raw_decode(buffer)
                    break
                except json.JSONDecodeError:
                    chunk = stream.read(1024 * 1024)
                    if not chunk:
                        raise SnapshotEvidenceError(f"manifest 陣列格式錯誤：{key}")
                    buffer += chunk
            if not isinstance(value, dict):
                raise SnapshotEvidenceError(f"manifest 陣列 {key} 包含非物件")
            yield value
            buffer = buffer[end:]


def collect_expected_cells(path: Path) -> tuple[dict[str, dict[str, dict[tuple[str, int], Any]]], dict[str, int]]:
    """整理 manifest 指定的 after cells，並保留逐股／逐日／逐欄身份。"""
    expected: dict[str, dict[str, dict[tuple[str, int], Any]]] = {}
    symbols: set[str] = set()
    indicator_cells = 0
    source_cells = 0
    for plan in _iter_array_objects(path, "plans"):
        symbol = str(plan.get("symbol", "")).strip()
        if not symbol or symbol in symbols:
            raise SnapshotEvidenceError(f"manifest 股票代碼缺漏或重複：{symbol!r}")
        symbols.add(symbol)
        symbol_rows = expected.setdefault(symbol, {})

        def add_cell(date: str, column: str, ordinal: int, value: Any) -> None:
            cells = symbol_rows.setdefault(date, {})
            key = (column, ordinal)
            normalized = _json_value(value)
            if key in cells and not _values_equal(cells[key], normalized):
                raise SnapshotEvidenceError(f"manifest after cell 衝突：{symbol}/{date}/{key}")
            cells[key] = normalized

        updates = plan.get("updates")
        if not isinstance(updates, list):
            raise SnapshotEvidenceError(f"manifest 缺少指標更新：{symbol}")
        for update in updates:
            if not isinstance(update, Mapping):
                raise SnapshotEvidenceError(f"manifest 指標更新格式錯誤：{symbol}")
            date = _date_key(update.get("date"))
            changed, values = update.get("changed_columns"), update.get("new")
            if not date or not isinstance(changed, list) or not isinstance(values, Mapping):
                raise SnapshotEvidenceError(f"manifest 指標更新欄位不完整：{symbol}/{date}")
            for column in changed:
                name = str(column)
                if name not in values:
                    raise SnapshotEvidenceError(f"manifest after value 缺漏：{symbol}/{date}/{name}")
                add_cell(date, name, 0, values[name])
                indicator_cells += 1

        source_plan = plan.get("source_copy_plan")
        source_updates = source_plan.get("updates") if isinstance(source_plan, Mapping) else None
        if not isinstance(source_updates, list):
            raise SnapshotEvidenceError(f"manifest 缺少來源欄更新：{symbol}")
        for update in source_updates:
            if not isinstance(update, Mapping):
                raise SnapshotEvidenceError(f"manifest 來源欄更新格式錯誤：{symbol}")
            identity = update.get("row_identity")
            date = _date_key(identity.get("date") if isinstance(identity, Mapping) else None)
            column = str(update.get("column", ""))
            ordinal = update.get("column_ordinal", 0)
            if not date or not column or not isinstance(ordinal, int) or ordinal < 0:
                raise SnapshotEvidenceError(f"manifest 來源欄身份錯誤：{symbol}/{date}/{column}")
            add_cell(date, column, ordinal, update.get("new"))
            source_cells += 1
    return expected, {
        "symbols": len(symbols),
        "affected_rows": sum(len(rows) for rows in expected.values()),
        "indicator_after_cells": indicator_cells,
        "source_after_cells": source_cells,
        "after_cells": indicator_cells + source_cells,
    }


def _quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _schema(connection: sqlite3.Connection) -> dict[str, Any]:
    rows = connection.execute('PRAGMA table_info("technical_indicators")').fetchall()
    columns = [str(row[1]) for row in rows]
    date_column = next((name for name in DATE_COLUMNS if name in columns), None)
    symbol_column = next((name for name in SYMBOL_COLUMNS if name in columns), None)
    if not columns or date_column is None or symbol_column is None:
        raise SnapshotEvidenceError("technical_indicators 缺少資料表或日期／代碼欄")
    positions: dict[str, list[int]] = {}
    for index, name in enumerate(columns):
        positions.setdefault(name, []).append(index)
    return {"columns": columns, "positions": positions,
            "date_column": date_column, "symbol_column": symbol_column}


def _open_read_only(path: Path) -> sqlite3.Connection:
    if path.is_symlink() or not path.is_file():
        raise SnapshotEvidenceError(f"SQLite 不存在或不是一般檔案：{path}")
    connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)
    connection.execute("PRAGMA query_only=ON")
    connection.execute("PRAGMA busy_timeout=5000")
    if int(connection.execute("PRAGMA query_only").fetchone()[0]) != 1:
        connection.close()
        raise SnapshotEvidenceError("SQLite query_only 無法開啟")
    return connection


def _sqlite_sidecar_state(path: Path) -> dict[str, dict[str, object]]:
    """記錄 SQLite WAL／SHM 檔案狀態；SHM 僅為鎖定索引，不是資料內容。"""
    state: dict[str, dict[str, object]] = {}
    for suffix in ("-wal", "-shm"):
        sidecar = Path(str(path) + suffix)
        exists = sidecar.exists()
        state[suffix] = {"exists": exists, "size_bytes": sidecar.stat().st_size if exists else 0}
    return state


def _symbol_candidates(symbol: str) -> list[str]:
    candidates = [symbol]
    if symbol.isdigit():
        number = str(int(symbol))
        candidates.extend([number, f"{number}.0", f"{int(number):04d}", f"{int(number):04d}.0"])
    return list(dict.fromkeys(candidates))


def _query_plan(connection: sqlite3.Connection, schema: Mapping[str, Any], symbol: str) -> list[str]:
    candidates = _symbol_candidates(symbol)
    marks = ",".join("?" for _ in candidates)
    sql = (f"SELECT * FROM technical_indicators WHERE {_quote(str(schema['symbol_column']))} "
           f"IN ({marks}) AND {_quote(str(schema['date_column']))} >= ?")
    rows = connection.execute("EXPLAIN QUERY PLAN " + sql, (*candidates, TARGET_DATE)).fetchall()
    return [str(row[3]) for row in rows]


def _fetch_rows(connection: sqlite3.Connection, schema: Mapping[str, Any], symbol: str) -> dict[str, tuple[Any, ...]]:
    columns = list(schema["columns"])
    candidates = _symbol_candidates(symbol)
    marks = ",".join("?" for _ in candidates)
    date_column, symbol_column = str(schema["date_column"]), str(schema["symbol_column"])
    sql = (f"SELECT {', '.join(_quote(column) for column in columns)} FROM technical_indicators "
           f"WHERE {_quote(symbol_column)} IN ({marks}) AND {_quote(date_column)} >= ?")
    result: dict[str, tuple[Any, ...]] = {}
    symbol_index, date_index = columns.index(symbol_column), columns.index(date_column)
    for row in connection.execute(sql, (*candidates, TARGET_DATE)):
        if _symbol_key(row[symbol_index]) != _symbol_key(symbol):
            continue
        date = _date_key(row[date_index])
        if not date:
            continue
        if date in result:
            raise SnapshotEvidenceError(f"SQLite 有重複技術列：{symbol}/{date}")
        result[date] = tuple(row)
    return result


def verify_technical_rows(
    database_path: Path,
    backup_path: Path,
    expected: Mapping[str, Mapping[str, Mapping[tuple[str, int], Any]]],
) -> dict[str, Any]:
    """逐股核對 after cells，並確認同一修訂列其餘欄位與 before backup 相同。"""
    current, backup = _open_read_only(database_path), _open_read_only(backup_path)
    result: dict[str, Any] = {
        "symbols": len(expected), "affected_rows": sum(len(rows) for rows in expected.values()),
        "after_cells": 0, "after_matches": 0, "after_mismatches": 0,
        "missing_current_rows": 0, "untouched_cells": 0, "untouched_mismatches": 0,
        "samples": [], "query_plan": [],
    }
    try:
        current_schema, backup_schema = _schema(current), _schema(backup)
        if current_schema["columns"] != backup_schema["columns"]:
            raise SnapshotEvidenceError("修復前後 technical_indicators schema 不同")
        if expected:
            result["query_plan"] = _query_plan(current, current_schema, next(iter(expected)))
        for symbol, dates in expected.items():
            current_rows = _fetch_rows(current, current_schema, symbol)
            backup_rows = _fetch_rows(backup, backup_schema, symbol)
            for date, cells in dates.items():
                current_row, backup_row = current_rows.get(date), backup_rows.get(date)
                if current_row is None:
                    result["missing_current_rows"] += 1
                    result["after_mismatches"] += len(cells)
                    if len(result["samples"]) < 20:
                        result["samples"].append({"kind": "missing_current_row", "symbol": symbol, "date": date})
                    continue
                if backup_row is None:
                    raise SnapshotEvidenceError(f"修復前備份缺少技術列：{symbol}/{date}")
                modified = set(cells)
                positions = current_schema["positions"]
                for (column, ordinal), expected_value in cells.items():
                    result["after_cells"] += 1
                    indexes = positions.get(column, [])
                    if ordinal >= len(indexes):
                        result["after_mismatches"] += 1
                        continue
                    if _values_equal(current_row[indexes[ordinal]], expected_value):
                        result["after_matches"] += 1
                    else:
                        result["after_mismatches"] += 1
                        if len(result["samples"]) < 20:
                            result["samples"].append({"kind": "after_mismatch", "symbol": symbol,
                                "date": date, "column": column, "expected": _json_value(expected_value),
                                "actual": _json_value(current_row[indexes[ordinal]])})
                for column, indexes in positions.items():
                    for ordinal, index in enumerate(indexes):
                        if (column, ordinal) in modified:
                            continue
                        result["untouched_cells"] += 1
                        if not _values_equal(current_row[index], backup_row[index]):
                            result["untouched_mismatches"] += 1
                            if len(result["samples"]) < 20:
                                result["samples"].append({"kind": "untouched_mismatch", "symbol": symbol,
                                    "date": date, "column": column,
                                    "before": _json_value(backup_row[index]),
                                    "after": _json_value(current_row[index])})
    finally:
        current.close()
        backup.close()
    return result


def _verify_receipt(path: Path, label: str, expected_schema: str, expected_kind: str) -> tuple[dict[str, Any], str, str]:
    payload = _json_object(path, label)
    supplied = payload.get("receipt_sha256")
    body = dict(payload)
    body.pop("receipt_sha256", None)
    computed = _canonical_hash(body)
    if supplied != computed:
        raise SnapshotEvidenceError(f"{label} body hash 不符")
    if payload.get("schema_version") != expected_schema or payload.get("receipt_kind") != expected_kind:
        raise SnapshotEvidenceError(f"{label} schema/kind 不符")
    return payload, _sha256_file(path), str(supplied)


def verify_revision_snapshot(
    *,
    database_path: Path,
    technical_pending_path: Path,
    technical_receipt_path: Path,
    price_pending_path: Path,
    price_receipt_path: Path,
    technical_backup_path: Path,
    dryrun_manifest_path: Path,
) -> dict[str, Any]:
    """產生完整修訂窗 readback evidence；來源快照在查核前後必須 byte-stable。"""
    paths = {
        "database_snapshot": database_path.resolve(),
        "technical_pending": technical_pending_path.resolve(),
        "technical_receipt": technical_receipt_path.resolve(),
        "price_pending": price_pending_path.resolve(),
        "price_receipt": price_receipt_path.resolve(),
        "technical_backup": technical_backup_path.resolve(),
        "dryrun_manifest": dryrun_manifest_path.resolve(),
    }
    for name, path in paths.items():
        if path.is_symlink() or not path.is_file():
            raise SnapshotEvidenceError(f"輸入檔不存在或不是一般檔案：{name}={path}")
    input_stats = {name: path.stat() for name, path in paths.items()}
    input_hashes = {name: _sha256_file(path) for name, path in paths.items()}
    snapshot_sidecars_before = _sqlite_sidecar_state(paths["database_snapshot"])
    backup_sidecars_before = _sqlite_sidecar_state(paths["technical_backup"])
    if snapshot_sidecars_before["-wal"]["size_bytes"] or backup_sidecars_before["-wal"]["size_bytes"]:
        raise SnapshotEvidenceError("SQLite snapshot/backup 有非空 WAL；不得只用主檔 SHA 綁定資料")

    technical_pending = _json_object(paths["technical_pending"], "technical pending")
    if (technical_pending.get("schema_version"), technical_pending.get("status"), technical_pending.get("source_date")) != (
        TECHNICAL_RECEIPT_SCHEMA, "receipt_written", TARGET_DATE
    ):
        raise SnapshotEvidenceError("technical pending 狀態或日期不符，維持 fail-closed")
    price_pending = _json_object(paths["price_pending"], "price pending")
    if (price_pending.get("schema_version"), price_pending.get("receipt_kind"),
        price_pending.get("status"), price_pending.get("source_date")) != (
        PRICE_RECEIPT_SCHEMA, "historical_price_spike_repair_pending", "applied_receipt_written", TARGET_DATE
    ):
        raise SnapshotEvidenceError("price pending 狀態或日期不符，維持 fail-closed")
    technical, technical_file_hash, technical_body_hash = _verify_receipt(
        paths["technical_receipt"], "technical receipt", TECHNICAL_RECEIPT_SCHEMA, "technical_indicator_repair"
    )
    price, price_file_hash, price_body_hash = _verify_receipt(
        paths["price_receipt"], "price receipt", PRICE_RECEIPT_SCHEMA, "historical_price_spike_repair"
    )
    if (technical_file_hash != input_hashes["technical_receipt"]
        or price_file_hash != input_hashes["price_receipt"]):
        raise SnapshotEvidenceError("receipt bytes 在 body 驗證前後改變")
    if technical.get("status") != "applied" or technical.get("source_date") != TARGET_DATE:
        raise SnapshotEvidenceError("technical receipt 未套用或日期不符")
    if technical.get("price_receipt_sha256") != price_body_hash:
        raise SnapshotEvidenceError("technical receipt 所記 price body identity 不符")
    if price.get("status") != "applied" or price.get("available_at") is not None:
        raise SnapshotEvidenceError("price receipt 狀態不符或錯誤宣稱歷史 available_at")
    for field in ("historical_decision_time_available", "formal_training_allowed", "promotion_eligible"):
        if price.get(field) is not False:
            raise SnapshotEvidenceError(f"price receipt 必須維持 {field}=false")
    if technical.get("available_at") is not None or technical.get("formal_training_allowed") is not False:
        raise SnapshotEvidenceError("technical receipt 不可宣稱正式可得或正式訓練核准")
    backup_hash = input_hashes["technical_backup"]
    if backup_hash != technical.get("technical_backup_sha256"):
        raise SnapshotEvidenceError("technical online backup hash 不符 receipt")
    manifest_hash = input_hashes["dryrun_manifest"]
    if manifest_hash != technical.get("dryrun_manifest_sha256"):
        raise SnapshotEvidenceError("dry-run manifest hash 不符 receipt")

    database = paths["database_snapshot"]
    before_stat = input_stats["database_snapshot"]
    before_hash = input_hashes["database_snapshot"]
    expected, manifest_coverage = collect_expected_cells(paths["dryrun_manifest"])
    receipt_operations = technical.get("operations_summary")
    if not isinstance(receipt_operations, Mapping):
        raise SnapshotEvidenceError("technical receipt 缺少 operations_summary")
    expected_operations = {
        "operations": manifest_coverage["after_cells"],
        "technical_indicator_cells": manifest_coverage["indicator_after_cells"],
        "technical_source_cells": manifest_coverage["source_after_cells"],
        "technical_source_rows": manifest_coverage["symbols"],
    }
    if any(receipt_operations.get(key) != value for key, value in expected_operations.items()):
        raise SnapshotEvidenceError("technical receipt operations_summary 與 dry-run manifest 不符")
    verified = verify_technical_rows(database, paths["technical_backup"], expected)
    after_stat = database.stat()
    after_hash = _sha256_file(database)
    snapshot_sidecars_after = _sqlite_sidecar_state(database)
    backup_sidecars_after = _sqlite_sidecar_state(paths["technical_backup"])
    if (before_hash != after_hash or before_stat.st_size != after_stat.st_size
        or before_stat.st_mtime_ns != after_stat.st_mtime_ns):
        raise SnapshotEvidenceError("查核期間 SQLite snapshot bytes/stat 改變")
    for name, path in paths.items():
        current = path.stat()
        original = input_stats[name]
        if current.st_size != original.st_size or current.st_mtime_ns != original.st_mtime_ns:
            raise SnapshotEvidenceError(f"查核期間輸入檔案大小或修改時間改變：{name}")
    if (snapshot_sidecars_after["-wal"] != snapshot_sidecars_before["-wal"]
        or backup_sidecars_after["-wal"] != backup_sidecars_before["-wal"]):
        raise SnapshotEvidenceError("查核期間 SQLite WAL 狀態改變")
    if manifest_coverage != EXPECTED_COVERAGE:
        raise SnapshotEvidenceError(f"dry-run manifest coverage 不符正式 repair 範圍：{manifest_coverage}")
    for field in ("symbols", "affected_rows", "after_cells"):
        if verified.get(field) != manifest_coverage[field]:
            raise SnapshotEvidenceError(f"SQLite readback {field} 數量不符 manifest")
    if (verified["after_matches"] != EXPECTED_COVERAGE["after_cells"]
        or verified["after_mismatches"] != 0
        or verified["missing_current_rows"] != 0
        or verified["untouched_cells"] != EXPECTED_UNTOUCHED_CELLS
        or verified["untouched_mismatches"] != 0):
        raise SnapshotEvidenceError(f"SQLite 技術修訂 readback 未通過：{verified}")
    if not verified["query_plan"] or not all("SEARCH" in plan.upper() and "SCAN" not in plan.upper()
                                             for plan in verified["query_plan"]):
        raise SnapshotEvidenceError("SQLite 查核不是索引 bounded SEARCH")

    inputs = {
        name: {"path": str(path), "sha256": input_hashes[name], "size_bytes": input_stats[name].st_size}
        for name, path in paths.items()
    }
    evidence: dict[str, Any] = {
        "schema_version": EVIDENCE_SCHEMA,
        "status": "passed",
        "purpose": "late_obtained_research_source_evidence_only",
        "formal_pit_gate_changed": False,
        "historical_available_at": None,
        "availability_status": "late_obtained",
        "snapshot": {"path": str(database), "sha256_before": before_hash,
                     "sha256_after": after_hash, "size_bytes": before_stat.st_size,
                     "sidecars_before": snapshot_sidecars_before,
                     "sidecars_after": snapshot_sidecars_after,
                     "nonempty_wal_rejected": True},
        "technical_backup_sidecars": {"before": backup_sidecars_before,
                                      "after": backup_sidecars_after,
                                      "nonempty_wal_rejected": True},
        "inputs": inputs,
        "receipt_identity": {"technical_receipt_file_sha256": technical_file_hash,
            "technical_receipt_body_sha256": technical_body_hash,
            "price_receipt_file_sha256": price_file_hash,
            "price_receipt_body_sha256": price_body_hash,
            "technical_price_receipt_identity_match": True},
        "coverage": {**manifest_coverage, **{key: verified[key] for key in (
            "after_matches", "after_mismatches", "missing_current_rows", "untouched_cells",
            "untouched_mismatches", "query_plan")}},
        "provenance": {"tracked_verifier_module_sha256": _sha256_file(Path(__file__).resolve()),
            "original_qa_verifier_reference_sha256": ORIGINAL_QA_VERIFIER_REFERENCE_SHA256,
            "original_qa_verifier_imported": False,
            "rerun_uses_tracked_verifier_module": True},
    }
    evidence["evidence_sha256"] = _canonical_hash(evidence)
    return evidence
