"""建立 late-obtained 研究來源快照，不開啟正式 PIT gate。

正式 source-revision guard 保持 fail-closed。此獨立入口要求保留價格／技術
pending 與 final receipt、隔離 recovery receipt、tracked 全窗口 verifier
證據，以及唯讀 SQLite snapshot。它不回填歷史可得時間，也不產生訓練輸入。
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from typing import Any, Mapping, Sequence

from data_module.ml_daily_price_revision_recovery import RECOVERY_SCHEMA
from data_module.ml_daily_price_revision_technical_snapshot import (
    EVIDENCE_SCHEMA as TECHNICAL_SNAPSHOT_EVIDENCE_SCHEMA,
    EXPECTED_COVERAGE,
    EXPECTED_UNTOUCHED_CELLS,
    PRICE_RECEIPT_SCHEMA,
    TECHNICAL_RECEIPT_SCHEMA,
    _canonical_hash as _sealed_body_hash,
)

SCHEMA = "ml-daily-price-revision-research-dataset.v1"
REPAIR_SCHEMA = "historical-price-spike-repair-20260921.v1"
TECHNICAL_SCHEMA = TECHNICAL_RECEIPT_SCHEMA
DATASET_ID = "research_shadow_daily_price_revision_recovered_source_20260922"
MAX_ROWS = 5_000
BATCH_SIZE = 400
PRICE_COLUMNS = {
    "開盤價": "open", "最高價": "high", "最低價": "low",
    "收盤價": "close", "成交股數": "volume_shares",
}


class ResearchDatasetError(ValueError):
    def __init__(self, message: str, *, evidence: Mapping[str, object] | None = None):
        super().__init__(message)
        self.evidence = dict(evidence or {})


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def _hash_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1 << 20):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _json_object(path: Path, label: str) -> dict[str, Any]:
    path = path.resolve()
    if not path.is_file() or path.is_symlink():
        raise ResearchDatasetError(f"{label} is not a regular file: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ResearchDatasetError(f"{label} is unreadable: {path}") from exc
    if not isinstance(payload, dict):
        raise ResearchDatasetError(f"{label} must be a JSON object")
    return payload


def _verify_sealed_hash(payload: Mapping[str, Any], field: str, label: str) -> str:
    supplied = payload.get(field)
    body = dict(payload)
    body.pop(field, None)
    if not isinstance(supplied, str) or supplied != _sealed_body_hash(body):
        raise ResearchDatasetError(f"{label} body hash does not match")
    return supplied


def _is_beneath(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _sidecar_state(database: Path) -> dict[str, int]:
    state: dict[str, int] = {}
    for suffix in ("-wal", "-shm"):
        sidecar = Path(str(database) + suffix)
        state[suffix] = sidecar.stat().st_size if sidecar.exists() else 0
    return state


def _verify_evidence_artifact(
    recovery: Mapping[str, Any], key: str, output_root: Path
) -> tuple[Path, str]:
    artifacts = recovery.get("evidence_files")
    record = artifacts.get(key) if isinstance(artifacts, Mapping) else None
    if not isinstance(record, Mapping):
        raise ResearchDatasetError(f"recovery evidence is missing {key} artifact")
    path = Path(str(record.get("path", "")))
    if path.is_symlink() or not path.is_file() or not _is_beneath(path, output_root):
        raise ResearchDatasetError(f"recovery {key} artifact is not a file under its isolated run")
    actual_hash = _hash_file(path)
    if actual_hash != record.get("sha256") or path.stat().st_size != record.get("size_bytes"):
        raise ResearchDatasetError(f"recovery {key} artifact hash/size does not match receipt")
    return path.resolve(), actual_hash


def _instant(value: object, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ResearchDatasetError(f"{field} must be a timezone-aware ISO timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ResearchDatasetError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _date(value: object, field: str) -> str:
    text = str(value).strip()
    if len(text) == 8 and text.isdigit():
        return text
    if len(text) == 10 and text[4] == "-" and text[7] == "-":
        return text.replace("-", "")
    raise ResearchDatasetError(f"{field} must be YYYYMMDD or YYYY-MM-DD")


def _number(value: object, field: str, *, integer: bool = False) -> str:
    if value is None or isinstance(value, bool):
        raise ResearchDatasetError(f"{field} is missing")
    try:
        parsed = Decimal(str(value).strip().replace(",", ""))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ResearchDatasetError(f"{field} is not numeric") from exc
    if not parsed.is_finite() or (integer and parsed != parsed.to_integral_value()):
        raise ResearchDatasetError(f"{field} is not a finite {'integer' if integer else 'number'}")
    return str(int(parsed)) if integer else format(parsed.normalize(), "f")


def _receipt_rows(receipt: Mapping[str, Any]) -> tuple[dict[str, object], ...]:
    raw_rows = receipt.get("rows")
    if not isinstance(raw_rows, list) or not 0 < len(raw_rows) <= MAX_ROWS:
        raise ResearchDatasetError("final receipt rows are missing or exceed bounded limit")
    source_date = _date(receipt.get("source_date"), "final.source_date")
    declared_missing_ohlc = {
        str(symbol).strip().zfill(4)
        for symbol in receipt.get("missing_ohlc_symbols", [])
        if str(symbol).strip()
    }
    rows: list[dict[str, object]] = []
    keys: set[tuple[str, str]] = set()
    observed_missing_ohlc: set[str] = set()
    for index, raw in enumerate(raw_rows):
        if not isinstance(raw, Mapping) or not isinstance(raw.get("after"), Mapping):
            raise ResearchDatasetError(f"final receipt row {index} is invalid")
        symbol = str(raw.get("symbol") or "").strip()
        day = _date(raw.get("date", source_date), f"rows[{index}].date")
        after = raw["after"]
        if not symbol or day != source_date:
            raise ResearchDatasetError(f"final receipt row {index} is outside source scope")
        if str(after.get("證券代號") or symbol).strip() != symbol:
            raise ResearchDatasetError(f"final receipt row {index} symbol mismatch")
        if _date(after.get("日期", day), f"rows[{index}].after.date") != day:
            raise ResearchDatasetError(f"final receipt row {index} date mismatch")
        key = (day, symbol)
        if key in keys:
            raise ResearchDatasetError(f"duplicate repaired row: {day}/{symbol}")
        keys.add(key)
        row: dict[str, object] = {"date": day, "symbol": symbol}
        missing_fields: list[str] = []
        for column, name in PRICE_COLUMNS.items():
            value = after.get(column)
            if value is None or not str(value).strip():
                row[name] = None
                missing_fields.append(name)
            else:
                row[name] = _number(value, f"rows[{index}].after.{column}",
                                    integer=name == "volume_shares")
        missing_ohlc = any(row[name] is None for name in ("open", "high", "low", "close"))
        if missing_ohlc:
            observed_missing_ohlc.add(symbol.zfill(4))
        row["missing_source_fields"] = missing_fields
        row["price_row_status"] = "missing_ohlc_excluded_from_fit" if missing_ohlc else "complete_ohlc"
        rows.append(row)
    rows.sort(key=lambda row: (str(row["date"]), str(row["symbol"])))
    if receipt.get("allowlist_count") != len(rows):
        raise ResearchDatasetError("final allowlist_count does not match receipt rows")
    if declared_missing_ohlc != observed_missing_ohlc:
        raise ResearchDatasetError("missing_ohlc_symbols does not match the receipt after values")
    return tuple(rows)


def _sqlite_rows(database: Path, expected: Sequence[Mapping[str, object]]):
    symbols = tuple(sorted(str(row["symbol"]) for row in expected))
    day = str(expected[0]["date"])
    wanted = {(str(row["date"]), str(row["symbol"])) for row in expected}
    price: dict[tuple[str, str], dict[str, object]] = {}
    technical: dict[tuple[str, str], dict[str, object]] = {}
    connection = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA query_only=ON")
        connection.execute("PRAGMA busy_timeout=5000")
        if connection.execute("PRAGMA query_only").fetchone()[0] != 1:
            raise ResearchDatasetError("SQLite connection is not query-only")
        required = {"daily_prices": {"日期", "證券代號", *PRICE_COLUMNS}}
        for table in ("daily_prices", "technical_indicators"):
            columns = {str(row["name"]) for row in connection.execute(f'PRAGMA table_info("{table}")')}
            need = required.get(table, {"日期", "證券代號"})
            if not need.issubset(columns):
                raise ResearchDatasetError(f"{table} is missing required columns")
        tech_columns = tuple(str(row["name"]) for row in connection.execute('PRAGMA table_info("technical_indicators")'))
        for table, sink, projection in (
            ("daily_prices", price,
             '"日期", "證券代號", "開盤價", "最高價", "最低價", "收盤價", "成交股數"'),
            ("technical_indicators", technical,
             ", ".join('"' + column.replace('"', '""') + '"' for column in tech_columns)),
        ):
            for start in range(0, len(symbols), BATCH_SIZE):
                batch = symbols[start:start + BATCH_SIZE]
                marks = ",".join("?" for _ in batch)
                query = f'SELECT {projection} FROM "{table}" WHERE "日期"=? AND "證券代號" IN ({marks})'
                plan = connection.execute("EXPLAIN QUERY PLAN " + query, (day, *batch)).fetchall()
                detail = " ".join(str(row["detail"]).upper() for row in plan)
                if "SEARCH" not in detail or "SCAN" in detail:
                    raise ResearchDatasetError(f"{table} bounded read is not index-backed",
                                               evidence={"query_plan": detail})
                for raw in connection.execute(query, (day, *batch)):
                    item = {key: raw[key] for key in raw.keys()}
                    key = (_date(item["日期"], f"{table}.date"), str(item["證券代號"]).strip())
                    if key not in wanted or key in sink:
                        raise ResearchDatasetError(f"{table} has out-of-scope/duplicate key {key}")
                    sink[key] = item
    except sqlite3.Error as exc:
        raise ResearchDatasetError("bounded read-only SQLite query failed") from exc
    finally:
        connection.close()
    missing_price = sorted(wanted - set(price))
    missing_technical = sorted(wanted - set(technical))
    if missing_price:
        raise ResearchDatasetError("snapshot is missing repaired daily-price rows",
                                   evidence={"expected": len(wanted), "matched": len(price),
                                             "missing_symbols": [key[1] for key in missing_price[:20]]})
    if missing_technical:
        raise ResearchDatasetError("technical snapshot misses affected rows",
                                   evidence={"expected": len(wanted), "matched": len(technical),
                                             "missing_symbols": [key[1] for key in missing_technical[:20]]})
    expected_by_key = {(str(row["date"]), str(row["symbol"])): row for row in expected}
    matched: list[dict[str, object]] = []
    for key in sorted(wanted):
        actual = price[key]
        expected_row = expected_by_key[key]
        for column, name in PRICE_COLUMNS.items():
            raw_value = actual[column]
            a = (
                None
                if raw_value is None or not str(raw_value).strip()
                else _number(raw_value, f"daily_prices.{key}.{column}", integer=name == "volume_shares")
            )
            if a != expected_row[name]:
                raise ResearchDatasetError(f"snapshot daily_prices differs from receipt: {key}/{column}",
                                           evidence={"matched_price_rows": len(price),
                                                     "matched_technical_rows": len(technical)})
        matched.append(dict(expected_row))
    tech_rows = []
    for key in sorted(technical):
        tech_rows.append({name: _normalise_value(value) for name, value in sorted(technical[key].items())})
    return tuple(matched), tuple(tech_rows)


def _normalise_value(value: object) -> object:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        return format(Decimal(str(value)).normalize(), "f")
    if isinstance(value, bytes):
        return {"bytes_hex": value.hex()}
    return str(value)


def _rows_hash(rows: Sequence[Mapping[str, object]]) -> str:
    return _hash_bytes(_canonical([dict(row) for row in rows]))


def build_revision_aware_research_dataset(
    *,
    database_path: Path,
    pending_receipt_path: Path,
    final_receipt_path: Path,
    technical_pending_path: Path,
    technical_receipt_path: Path,
    technical_backup_path: Path,
    dryrun_manifest_path: Path,
    recovery_receipt_path: Path,
    technical_verification_path: Path,
    output_root: Path,
    observed_at: str | None = None,
) -> dict[str, object]:
    db, pending_path, final_path, tech_pending_path, tech_path, backup_path, manifest_path, recovery_path, verification_path = (
        path.expanduser().resolve()
        for path in (
            database_path,
            pending_receipt_path,
            final_receipt_path,
            technical_pending_path,
            technical_receipt_path,
            technical_backup_path,
            dryrun_manifest_path,
            recovery_receipt_path,
            technical_verification_path,
        )
    )
    root = output_root.expanduser().resolve(strict=False)
    if root.drive.casefold() != db.drive.casefold():
        raise ResearchDatasetError("output root must be on the isolated snapshot drive")
    sources = (
        db, pending_path, final_path, tech_pending_path, tech_path,
        backup_path, manifest_path, recovery_path, verification_path,
    )
    for source in sources:
        if source.is_symlink() or not source.is_file():
            raise ResearchDatasetError(f"research input is not a regular file: {source}")
        if root == source.parent or root in source.parents or source.parent in root.parents:
            raise ResearchDatasetError("output root overlaps a read-only source")
    pending = _json_object(pending_path, "pending receipt")
    final = _json_object(final_path, "final receipt")
    technical_pending = _json_object(tech_pending_path, "technical pending")
    technical = _json_object(tech_path, "technical receipt")
    recovery = _json_object(recovery_path, "isolated recovery receipt")
    verification = _json_object(verification_path, "tracked technical snapshot verification")
    if pending.get("schema_version") != REPAIR_SCHEMA or final.get("schema_version") != REPAIR_SCHEMA:
        raise ResearchDatasetError("repair receipt schema is unsupported")
    final_body_hash = _verify_sealed_hash(final, "receipt_sha256", "price repair receipt")
    if (pending.get("receipt_kind"), pending.get("status")) != (
        "historical_price_spike_repair_pending", "applied_receipt_written"):
        raise ResearchDatasetError("pending receipt must remain the applied all-symbol marker")
    if (final.get("receipt_kind"), final.get("status")) != (
        "historical_price_spike_repair", "applied"):
        raise ResearchDatasetError("final repair receipt is not applied")
    day = _date(final.get("source_date"), "final.source_date")
    if _date(pending.get("source_date"), "pending.source_date") != day:
        raise ResearchDatasetError("pending/final source dates differ")
    if pending.get("allowlist_count") != final.get("allowlist_count"):
        raise ResearchDatasetError("pending/final allowlist counts differ")
    if pending.get("plan_hash") != final.get("plan_hash") or pending.get("allowlist_hash") != final.get("allowlist_hash"):
        raise ResearchDatasetError("pending/final repair identities differ")
    if pending.get("rows") not in (None, []):
        raise ResearchDatasetError("pending marker must not be rewritten with row scope")
    if final.get("available_at") is not None or pending.get("available_at") is not None:
        raise ResearchDatasetError("repair receipt cannot claim historical available_at")
    for flag in ("historical_decision_time_available", "formal_training_allowed", "promotion_eligible"):
        if final.get(flag) is not False:
            raise ResearchDatasetError(f"repair receipt must keep {flag}=false")
    corrected = _instant(final.get("corrected_at"), "final.corrected_at")
    if _instant(pending.get("created_at"), "pending.created_at") < corrected:
        raise ResearchDatasetError("pending/final repair chronology is inconsistent")
    if technical_pending.get("schema_version") != TECHNICAL_RECEIPT_SCHEMA or (
        technical_pending.get("receipt_kind"), technical_pending.get("status"),
        technical_pending.get("source_date"),
    ) != ("technical_indicator_repair_pending", "receipt_written", day):
        raise ResearchDatasetError("technical pending must remain receipt_written for the repair date")
    if (
        technical_pending.get("technical_backup_sha256") != _hash_file(backup_path)
        or technical_pending.get("dryrun_manifest_sha256") != _hash_file(manifest_path)
        or technical_pending.get("price_receipt") != final_body_hash
    ):
        raise ResearchDatasetError("technical pending does not bind the preserved repair inputs")
    technical_body_hash = _verify_sealed_hash(technical, "receipt_sha256", "technical repair receipt")
    if technical.get("schema_version") != TECHNICAL_SCHEMA or (
        technical.get("receipt_kind"), technical.get("status"), technical.get("source_date"),
    ) != ("technical_indicator_repair", "applied", day):
        raise ResearchDatasetError("technical repair receipt is absent or unsuccessful")
    for flag in ("formal_training_allowed", "promotion_eligible"):
        if technical.get(flag) is not False:
            raise ResearchDatasetError(f"technical receipt must keep {flag}=false")
    if technical.get("available_at") is not None:
        raise ResearchDatasetError("technical repair receipt cannot claim historical available_at")
    if technical.get("price_receipt_sha256") != final_body_hash:
        raise ResearchDatasetError("technical repair receipt price body identity differs")
    operations_summary = technical.get("operations_summary")
    if not isinstance(operations_summary, Mapping) or any(
        operations_summary.get(key) != value for key, value in {
            "operations": EXPECTED_COVERAGE["after_cells"],
            "technical_indicator_cells": EXPECTED_COVERAGE["indicator_after_cells"],
            "technical_source_cells": EXPECTED_COVERAGE["source_after_cells"],
            "technical_source_rows": EXPECTED_COVERAGE["symbols"],
        }.items()
    ):
        raise ResearchDatasetError("technical receipt operations do not match the verified repair window")

    expected = _receipt_rows(final)
    if len(expected) != EXPECTED_COVERAGE["symbols"]:
        raise ResearchDatasetError("price repair allowlist does not cover the verified revision window")
    db_stat_before = db.stat()
    snapshot_sidecars_before = _sidecar_state(db)
    if snapshot_sidecars_before["-wal"] != 0:
        raise ResearchDatasetError("research source snapshot has a nonempty WAL")
    db_hash = _hash_file(db)
    final_hash, pending_hash, technical_hash, technical_pending_hash = (
        _hash_file(path) for path in (final_path, pending_path, tech_path, tech_pending_path)
    )
    manifest_hash, backup_hash = _hash_file(manifest_path), _hash_file(backup_path)
    recovery_hash, verification_hash = _hash_file(recovery_path), _hash_file(verification_path)

    recovery_body_hash = _verify_sealed_hash(recovery, "receipt_sha256", "isolated recovery receipt")
    if recovery.get("schema_version") != RECOVERY_SCHEMA or (
        recovery.get("status"), recovery.get("mode"), recovery.get("research_candidate_only"),
    ) != ("passed", "isolated_research_snapshot_recovery", True):
        raise ResearchDatasetError("isolated recovery receipt is not a passed research-only recovery")
    for flag in ("formal_data_written", "formal_training_allowed", "historical_pit_eligible", "promotion_eligible"):
        if recovery.get(flag) is not False:
            raise ResearchDatasetError(f"recovery receipt must keep {flag}=false")
    run_root = Path(str(recovery.get("allowed_output_root", ""))).resolve()
    if recovery.get("database_path") != str(db) or not _is_beneath(db, run_root):
        raise ResearchDatasetError("recovery receipt is not bound to this isolated database")
    if recovery.get("database_sha256_after") != db_hash or recovery.get("database_size_after") != db_stat_before.st_size:
        raise ResearchDatasetError("recovered database hash/size differs from recovery receipt")
    if recovery.get("coverage") != EXPECTED_COVERAGE:
        raise ResearchDatasetError("recovery coverage differs from the accepted repair window")
    recovery_inputs = recovery.get("input_hashes")
    expected_recovery_inputs = {
        "price_pending_file": pending_hash,
        "price_receipt_file": final_hash,
        "technical_pending_file": technical_pending_hash,
        "technical_receipt_file": technical_hash,
        "dryrun_manifest": manifest_hash,
        "technical_before_backup": backup_hash,
    }
    if not isinstance(recovery_inputs, Mapping) or any(
        recovery_inputs.get(key) != value for key, value in expected_recovery_inputs.items()
    ):
        raise ResearchDatasetError("recovery receipt input hashes do not match the preserved source files")
    pending_state = recovery.get("pending_state")
    if not isinstance(pending_state, Mapping) or (
        pending_state.get("changed") is not False
        or pending_state.get("technical_status") != "receipt_written"
        or pending_state.get("price_status") != "applied_receipt_written"
        or pending_state.get("technical_pending_file_sha256") != technical_pending_hash
        or pending_state.get("price_pending_file_sha256") != pending_hash
    ):
        raise ResearchDatasetError("recovery receipt does not prove preserved pending markers")
    recovery_rows = recovery.get("rows")
    if not isinstance(recovery_rows, Mapping) or (
        recovery_rows.get("affected_rows") != EXPECTED_COVERAGE["affected_rows"]
        or recovery_rows.get("plan_external_before_sha256") != recovery_rows.get("plan_external_after_sha256")
        or recovery_rows.get("plan_external_rows") != recovery_rows.get("total_table_rows", 0) - EXPECTED_COVERAGE["affected_rows"]
    ):
        raise ResearchDatasetError("recovery receipt lacks matching affected/outside row evidence")
    recovery_artifacts = {
        name: _verify_evidence_artifact(recovery, name, run_root)
        for name in ("cell_diff", "affected_row_hashes")
    }

    verification_body_hash = _verify_sealed_hash(
        verification, "evidence_sha256", "tracked technical snapshot verification"
    )
    if verification.get("schema_version") != TECHNICAL_SNAPSHOT_EVIDENCE_SCHEMA or (
        verification.get("status"), verification.get("purpose"),
        verification.get("formal_pit_gate_changed"), verification.get("availability_status"),
        verification.get("historical_available_at"),
    ) != ("passed", "late_obtained_research_source_evidence_only", False, "late_obtained", None):
        raise ResearchDatasetError("tracked technical snapshot verification is not research-only passed evidence")
    snapshot = verification.get("snapshot")
    if not isinstance(snapshot, Mapping) or (
        snapshot.get("path") != str(db)
        or snapshot.get("sha256_before") != db_hash
        or snapshot.get("sha256_after") != db_hash
        or snapshot.get("size_bytes") != db_stat_before.st_size
    ):
        raise ResearchDatasetError("tracked verifier evidence is not bound to this database snapshot")
    before_sidecars, after_sidecars = snapshot.get("sidecars_before"), snapshot.get("sidecars_after")
    if not isinstance(before_sidecars, Mapping) or not isinstance(after_sidecars, Mapping) or (
        before_sidecars != after_sidecars
        or not isinstance(before_sidecars.get("-wal"), Mapping)
        or before_sidecars["-wal"].get("size_bytes") != 0
        or before_sidecars != {
            suffix: {"exists": Path(str(db) + suffix).exists(), "size_bytes": snapshot_sidecars_before[suffix]}
            for suffix in ("-wal", "-shm")
        }
    ):
        raise ResearchDatasetError("tracked verifier did not prove stable empty-WAL snapshot")
    verifier_coverage = verification.get("coverage")
    if not isinstance(verifier_coverage, Mapping) or any(
        verifier_coverage.get(key) != value for key, value in EXPECTED_COVERAGE.items()
    ) or any(verifier_coverage.get(key) != value for key, value in {
        "after_matches": EXPECTED_COVERAGE["after_cells"],
        "after_mismatches": 0,
        "missing_current_rows": 0,
        "untouched_cells": EXPECTED_UNTOUCHED_CELLS,
        "untouched_mismatches": 0,
    }.items()):
        raise ResearchDatasetError("tracked verifier coverage/readback is incomplete")
    verifier_inputs = verification.get("inputs")
    expected_verifier_inputs = {
        "database_snapshot": (db, db_hash),
        "technical_pending": (tech_pending_path, technical_pending_hash),
        "technical_receipt": (tech_path, technical_hash),
        "price_pending": (pending_path, pending_hash),
        "price_receipt": (final_path, final_hash),
        "technical_backup": (backup_path, backup_hash),
        "dryrun_manifest": (manifest_path, manifest_hash),
    }
    if not isinstance(verifier_inputs, Mapping) or any(
        not isinstance(verifier_inputs.get(name), Mapping)
        or verifier_inputs[name].get("path") != str(path)
        or verifier_inputs[name].get("sha256") != file_hash
        for name, (path, file_hash) in expected_verifier_inputs.items()
    ):
        raise ResearchDatasetError("tracked verifier evidence input identities differ")
    receipt_identity = verification.get("receipt_identity")
    if not isinstance(receipt_identity, Mapping) or any(
        receipt_identity.get(key) != value for key, value in {
            "technical_receipt_file_sha256": technical_hash,
            "technical_receipt_body_sha256": technical_body_hash,
            "price_receipt_file_sha256": final_hash,
            "price_receipt_body_sha256": final_body_hash,
            "technical_price_receipt_identity_match": True,
        }.items()
    ):
        raise ResearchDatasetError("tracked verifier receipt identities differ from current receipts")
    verifier_module = Path(__file__).resolve().with_name("ml_daily_price_revision_technical_snapshot.py")
    provenance = verification.get("provenance")
    if not isinstance(provenance, Mapping) or provenance.get("tracked_verifier_module_sha256") != _hash_file(verifier_module):
        raise ResearchDatasetError("tracked verifier module identity differs from its evidence")
    actual_prices, actual_technical = _sqlite_rows(db, expected)
    db_stat_after = db.stat()
    snapshot_sidecars_after = _sidecar_state(db)
    db_hash_after = _hash_file(db)
    if (db_hash_after != db_hash or db_stat_after.st_size != db_stat_before.st_size
        or db_stat_after.st_mtime_ns != db_stat_before.st_mtime_ns
        or snapshot_sidecars_after != snapshot_sidecars_before):
        raise ResearchDatasetError("SQLite snapshot changed while source rows were being read")
    prices_hash, technical_rows_hash = _rows_hash(actual_prices), _rows_hash(actual_technical)
    if len(actual_prices) != EXPECTED_COVERAGE["symbols"] or len(actual_technical) != EXPECTED_COVERAGE["symbols"]:
        raise ResearchDatasetError("source rows do not cover the verified repair symbols")
    technical_by_key: dict[tuple[str, str], dict[str, object]] = {}
    for row in actual_technical:
        key = (_date(row.get("日期"), "technical.date"), str(row.get("證券代號", "")).strip())
        if key in technical_by_key:
            raise ResearchDatasetError(f"duplicate technical feature row: {key}")
        technical_by_key[key] = {
            name: value for name, value in row.items() if name not in {"日期", "證券代號"}
        }
    for row in actual_prices:
        key = (str(row["date"]), str(row["symbol"]))
        if key not in technical_by_key:
            raise ResearchDatasetError(f"technical source row is missing: {key}")
    incomplete_price_rows = [
        row for row in actual_prices if row.get("price_row_status") != "complete_ohlc"
    ]
    price_quality = {
        "total_rows": len(actual_prices),
        "complete_ohlc_rows": len(actual_prices) - len(incomplete_price_rows),
        "missing_ohlc_rows": len(incomplete_price_rows),
        "missing_ohlc_symbols": sorted(str(row["symbol"]) for row in incomplete_price_rows),
        "excluded_from_fit_reason_counts": {
            "missing_ohlc_source": len(incomplete_price_rows),
        },
    }

    observed = _instant(observed_at or datetime.now(timezone.utc).isoformat(), "observed_at")
    if observed < corrected:
        raise ResearchDatasetError("research observation predates corrected source data")

    research_rows = [
        {**row, "technical_indicators": technical_by_key[(str(row["date"]), str(row["symbol"]))]}
        for row in actual_prices
    ]
    rows_bytes = b"".join(_canonical({
        "schema_version": "ml-daily-price-revision-research-row.v1",
        "dataset_id": DATASET_ID, **row,
        "source_revision": {
            "repair_receipt_sha256": final_hash, "source_db_snapshot_sha256": db_hash,
            "technical_repair_receipt_sha256": technical_hash,
            "isolated_recovery_receipt_sha256": recovery_hash,
            "technical_snapshot_verification_sha256": verification_hash,
            "technical_snapshot_verification_evidence_sha256": verification_body_hash,
            "observed_at": observed.isoformat(), "availability_status": "late_obtained",
            "historical_available_at": None, "historical_decision_time_available": False,
        },
        "training_eligibility": "research_source_evidence_only",
        "label_status": "not_materialized",
        "feature_contract_status": "not_assessed",
    }) + b"\n" for row in research_rows)
    rows_hash = _hash_bytes(rows_bytes)
    run_hash = _hash_bytes(_canonical({
        "dataset_id": DATASET_ID,
        "db": db_hash,
        "price_pending": pending_hash,
        "price_final": final_hash,
        "technical_pending": technical_pending_hash,
        "technical_receipt": technical_hash,
        "technical_before_backup": backup_hash,
        "dryrun_manifest": manifest_hash,
        "recovery_receipt": recovery_hash,
        "technical_verification": verification_hash,
        "recovery_cell_diff": recovery_artifacts["cell_diff"][1],
        "recovery_row_hashes": recovery_artifacts["affected_row_hashes"][1],
        "rows": rows_hash,
        "price_row_quality": price_quality,
        "observed_at": observed.isoformat(),
    }))
    run_id = run_hash.removeprefix("sha256:")[:24]
    directory = root / "runs" / run_id
    rows_path, manifest_path = directory / "recovered_source_rows.jsonl", directory / "manifest.json"
    manifest: dict[str, object] = {
        "schema_version": SCHEMA, "dataset_id": DATASET_ID, "run_id": run_id,
        "status": "accepted_research_source_snapshot", "created_at": observed.isoformat(),
        "authoritative_identity": {"dataset_id": DATASET_ID, "run_id": run_id,
                                   "content_sha256": run_hash},
        "source_revision": {
            "source_date": day, "corrected_at": corrected.isoformat(),
            "historical_available_at": None, "historical_decision_time_available": False,
            "availability_status": "late_obtained", "pending_marker_preserved": True,
            "pending_marker_still_blocks_formal_pit": True,
            "pending_receipt_sha256": pending_hash, "final_receipt_sha256": final_hash,
            "technical_pending_marker_sha256": technical_pending_hash,
            "technical_pending_status": technical_pending.get("status"),
            "allowlist_count": len(expected),
        },
        "snapshot": {"path": str(db), "sha256": db_hash, "size_bytes": db.stat().st_size,
                     "sidecars": snapshot_sidecars_after,
                     "sqlite_mode": "read_only_query_only"},
        "technical_repair_evidence": {
            "receipt_file_sha256": technical_hash,
            "receipt_body_sha256": technical_body_hash,
            "after_cells_sha256": technical.get("after_cells_sha256"),
            "operations_summary": technical.get("operations_summary"),
            "recovery_receipt_sha256": recovery_hash,
            "recovery_receipt_body_sha256": recovery_body_hash,
            "recovery_cell_diff_sha256": recovery_artifacts["cell_diff"][1],
            "recovery_row_hashes_sha256": recovery_artifacts["affected_row_hashes"][1],
            "tracked_verification_file_sha256": verification_hash,
            "tracked_verification_evidence_sha256": verification_body_hash,
            "daily_price_rows_sha256": prices_hash,
            "technical_rows_sha256": technical_rows_hash,
            "technical_rows_verified": len(actual_technical),
            "recovered_from_sealed_plan": True,
            "indicator_recomputed_by_this_builder": False,
        },
        "coverage": {"affected_rows_expected": len(expected), "daily_price_rows_matched": len(actual_prices),
                     "technical_rows_matched": len(actual_technical),
                     "full_repair_window_after_cells_verified": EXPECTED_COVERAGE["after_cells"],
                     "full_repair_window_untouched_cells_verified": EXPECTED_UNTOUCHED_CELLS},
        "price_row_quality": price_quality,
        "artifact": {"path": rows_path.name, "sha256": rows_hash, "row_count": len(actual_prices),
                     "contains_price_rows": True, "contains_technical_rows": True,
                     "model_training_input_compatible": False,
                     "feature_contract_status": "not_assessed",
                     "labels_materialized": False, "label_maturity_status": "not_materialized"},
        "eligibility": {"research_only": True, "formal_training_allowed": False,
            "formal_oos_allowed": False, "historical_pit_allowed": False,
            "promotion_eligible": False, "production_alpha_bp": 0,
            "labels_available_for_fit": False},
    }
    manifest_bytes = _canonical(manifest) + b"\n"
    for path, payload in ((rows_path, rows_bytes), (manifest_path, manifest_bytes)):
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            if path.read_bytes() != payload:
                raise FileExistsError(f"immutable research output differs: {path}")
            continue
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        try:
            with temporary.open("xb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            temporary.rename(path)
        finally:
            temporary.unlink(missing_ok=True)
    return {"dataset_id": DATASET_ID, "run_id": run_id, "run_sha256": run_hash,
            "dataset_directory": directory,
            "manifest_path": manifest_path, "rows_path": rows_path,
            "manifest_sha256": _hash_bytes(manifest_bytes), "rows_sha256": rows_hash,
            "row_count": len(actual_prices)}
