"""封存並排除已由官方證明的整日休市價量及錯日逐列資料。"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
from typing import Any, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data_module import excluded_daily_price_revision as exclusions
from data_module.ml_storage_capacity import acquire_heavy_chain_reservation, release_heavy_chain_reservation


SCHEMA = exclusions.SCHEMA
CONFIRM = "repair-excluded-daily-prices"
TABLES = ("daily_prices", "technical_indicators")
TARGET_DATES = (*exclusions.CLOSED_DATES, "20260520")
ORIGIN_MATCH_COLUMNS = ("成交股數", "開盤價", "最高價", "最低價", "收盤價")


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def encoded(value: object) -> bytes:
    return exclusions._encoded(value)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_hash(path: Path) -> str:
    return exclusions._hash_file(path)


def atomic(path: Path, body: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix="." + path.name, dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(body)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def read_json(path: Path) -> dict[str, Any]:
    return exclusions._read_json(path)


def readonly(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(
        path.resolve(strict=True).as_uri() + "?mode=ro", uri=True, timeout=30
    )
    connection.execute("PRAGMA query_only=ON")
    return connection


def root_for(database_path: Path) -> Path:
    return exclusions._root(database_path)


def relative_to_root(root: Path, path: Path, *, strict: bool = True) -> str:
    resolved = path.resolve(strict=strict)
    try:
        relative = resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError("來源或 receipt 必須位於正式資料根目錄") from exc
    return relative.as_posix()


def _sqlite_value(value: object) -> object:
    return str(value) if isinstance(value, float) else value


def _schema_snapshot(connection: sqlite3.Connection, table: str) -> dict[str, Any]:
    columns = [row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')]
    if not columns:
        raise ValueError(f"正式資料缺少資料表：{table}")
    objects = [
        list(row)
        for row in connection.execute(
            "SELECT type,name,sql FROM sqlite_master WHERE tbl_name=? ORDER BY type,name",
            (table,),
        )
    ]
    return {
        "columns": columns,
        "objects_sha256": digest(encoded(objects)),
        "schema_sha256": digest(encoded({"columns": columns, "objects": objects})),
    }


def _read_day_rows(
    connection: sqlite3.Connection, table: str, days: Sequence[str],
) -> dict[str, list[dict[str, object]]]:
    schema = _schema_snapshot(connection, table)
    columns = schema["columns"]
    marks = ",".join("?" for _ in days)
    quoted_columns = ",".join('"' + column.replace('"', '""') + '"' for column in columns)
    query = (
        f'SELECT {quoted_columns} '
        f'FROM "{table}" WHERE "日期" IN ({marks}) '
        'ORDER BY "日期", "證券代號"'
    )
    result: dict[str, list[dict[str, object]]] = {day: [] for day in days}
    for values in connection.execute(query, tuple(days)):
        row = {column: _sqlite_value(value) for column, value in zip(columns, values, strict=True)}
        day = exclusions._normal_date(row["日期"])
        result.setdefault(day, []).append(row)
    for rows in result.values():
        rows.sort(key=lambda row: (exclusions._normal_date(row["日期"]), exclusions._normal_symbol(row["證券代號"])))
    return result


def _key_set(rows: Sequence[dict[str, object]]) -> set[tuple[str, str]]:
    return {
        (exclusions._normal_date(row["日期"]), exclusions._normal_symbol(row["證券代號"]))
        for row in rows
    }


def _source_payloads(source_dir: Path) -> tuple[dict[tuple[str, str], dict[str, Any]], set[str]]:
    payloads: dict[tuple[str, str], dict[str, Any]] = {}
    for day in exclusions.OFFICIAL_DATES:
        for venue in ("twse", "tpex"):
            payloads[(venue, day)] = read_json(source_dir / f"{venue}-{day}.json")
    exclusions._validate_official_payloads(payloads)
    twse_table = next(
        table for table in payloads[("twse", "20260520")]["tables"]
        if isinstance(table, dict) and str(table.get("title", "")).endswith("每日收盤行情(全部)")
    )
    tpex_table = payloads[("tpex", "20260520")]["tables"][0]
    twse_codes = exclusions._unique_codes(
        twse_table["data"], expected_width=len(twse_table["fields"]), label="TWSE 20260520",
    )
    tpex_codes = exclusions._unique_codes(
        tpex_table["data"], expected_width=len(tpex_table["fields"]), label="TPEx 20260520",
    )
    if twse_codes & tpex_codes:
        raise ValueError("TWSE 與 TPEx 完整市場代號清單重疊")
    return payloads, twse_codes | tpex_codes


def _source_file_manifest(source_dir: Path) -> list[dict[str, Any]]:
    archive = read_json(source_dir / "archive.json")
    by_name = {Path(str(item.get("archived", ""))).name: item for item in archive.get("files", [])}
    result: list[dict[str, Any]] = []
    for name in exclusions._EVIDENCE_FILES:
        entry = by_name[name]
        item: dict[str, Any] = {
            "name": name,
            "sha256": str(entry["sha256"]),
            "bytes": int(entry["bytes"]),
        }
        if name.endswith(".receipt.json"):
            receipt = read_json(source_dir / name)
            item["captured_at"] = receipt["captured_at"]
        result.append(item)
    return result


def _target_rows(
    all_rows: dict[str, list[dict[str, object]]], keys: set[tuple[str, str]],
    closed_dates: set[str],
) -> list[dict[str, object]]:
    return [
        row for row in all_rows.get("20260520", [])
        if ("20260520", exclusions._normal_symbol(row["證券代號"])) in keys
    ] + [
        row for day in sorted(closed_dates) for row in all_rows.get(day, [])
    ]


def build_plan(
    database_path: Path,
    evidence_dir: Path,
    market_receipt_dir: Path,
    receipt_dir: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """建立唯讀 dry-run：包含全體目標列 before snapshot 與驗證來源鏈。"""
    database_path = database_path.resolve(strict=True)
    root = root_for(database_path).resolve(strict=True)
    evidence_dir = evidence_dir.resolve(strict=True)
    market_receipt_dir = market_receipt_dir.resolve(strict=True)
    receipt_dir = receipt_dir.resolve()
    run_id = receipt_dir.name
    receipt_relative = relative_to_root(root, receipt_dir.parent, strict=False) + "/" + run_id
    expected_receipts = (root / exclusions.RECEIPT_DIR).resolve()
    if receipt_dir.parent.resolve() != expected_receipts or not run_id or run_id in {".", ".."}:
        raise ValueError("receipt 目錄必須位於正式資料根目錄排除修訂目錄")
    evidence_relative = relative_to_root(root, evidence_dir)
    market_relative = relative_to_root(root, market_receipt_dir)
    archive, acquired_at, official_codes = exclusions._verify_archive(
        root,
        evidence_relative,
        file_hash(evidence_dir / "archive.json"),
        _source_file_manifest(evidence_dir),
    )
    market_validation = exclusions._validate_market_chain(
        database_path, root, market_relative, full_source_validation=True,
    )
    payloads, official_codes = _source_payloads(evidence_dir)

    with readonly(database_path) as connection:
        table_schemas = {table: _schema_snapshot(connection, table) for table in TABLES}
        all_rows = {
            table: _read_day_rows(connection, table, (*TARGET_DATES, "20171218"))
            for table in TABLES
        }
    closed_dates = set(exclusions.CLOSED_DATES)
    keys: set[tuple[str, str]] = set()
    closure_counts: dict[str, dict[str, int]] = {}
    for day in exclusions.CLOSED_DATES:
        closure_counts[day] = {}
        for table in TABLES:
            date_rows = all_rows[table].get(day, [])
            closure_counts[day][table] = len(date_rows)
            keys.update(_key_set(date_rows))
    may20_all = set().union(*(_key_set(all_rows[table].get("20260520", [])) for table in TABLES))
    may20_missing = {key for key in may20_all if key[1] not in official_codes}
    if len(may20_missing) != 54:
        raise ValueError(f"20260520 官方雙市場完整報表應精確排除54個未列代號，實際為{len(may20_missing)}")
    keys.update(may20_missing)

    daily_by_day = {
        day: {exclusions._normal_symbol(row["證券代號"]): row for row in all_rows["daily_prices"].get(day, [])}
        for day in ("20241002", "20171218", "20260520")
    }
    matches_20241002 = 0
    matches_20171218 = 0
    for _day, symbol in may20_missing:
        current = daily_by_day["20260520"].get(symbol)
        origin = daily_by_day["20241002"].get(symbol)
        older = daily_by_day["20171218"].get(symbol)
        if current is None or origin is None:
            raise ValueError(f"20260520 錯日來源缺少原始價量列：{symbol}")
        if any(current.get(column) != origin.get(column) for column in ORIGIN_MATCH_COLUMNS):
            raise ValueError(f"20260520 未列代號無法由錯誤休市日逐欄追溯：{symbol}")
        matches_20241002 += 1
        if older is not None and all(current.get(column) == older.get(column) for column in ORIGIN_MATCH_COLUMNS):
            matches_20171218 += 1

    before_tables: dict[str, list[dict[str, object]]] = {}
    for table in TABLES:
        before_tables[table] = _target_rows(all_rows[table], keys, closed_dates)
        identities = _key_set(before_tables[table])
        if len(identities) != len(before_tables[table]):
            raise ValueError(f"{table} 受影響列有重複 key")
    before_rows = {
        "schema_version": SCHEMA,
        "keys": [list(key) for key in sorted(keys)],
        "tables": before_tables,
    }
    before_rows_bytes = encoded(before_rows)
    scope = {"closed_dates": sorted(closed_dates), "keys": [list(key) for key in sorted(keys)]}
    source_files = _source_file_manifest(evidence_dir)
    summary = {
        "closed_date_daily_rows": {day: closure_counts[day]["daily_prices"] for day in exclusions.CLOSED_DATES},
        "closed_date_technical_rows": {day: closure_counts[day]["technical_indicators"] for day in exclusions.CLOSED_DATES},
        "may20_official_twse_rows": 31124,
        "may20_official_tpex_rows": 1007,
        "may20_excluded_exact_keys": len(may20_missing),
        "may20_rows_matching_closed_20241002": matches_20241002,
        "may20_rows_also_matching_20171218": matches_20171218,
        "total_excluded_keys": len(keys),
        "before_rows_by_table": {table: len(before_tables[table]) for table in TABLES},
    }
    plan = {
        "schema_version": SCHEMA,
        "created_at": now(),
        "database_path": str(database_path),
        "run_id": run_id,
        "receipt_relative_dir": receipt_relative,
        "evidence_archive_relative": evidence_relative,
        "evidence_archive_sha256": file_hash(evidence_dir / "archive.json"),
        "source_files": source_files,
        "market_receipt_relative_dir": market_relative,
        "market_plan_sha256": market_validation["plan_sha256"],
        "market_receipt_sha256": market_validation["receipt_sha256"],
        "market_validation": market_validation,
        "closed_dates": sorted(closed_dates),
        "source_start_date": min(closed_dates),
        "source_end_date": "20260520",
        "source_available_at": acquired_at.isoformat(),
        "historical_pit": False,
        "keys": scope["keys"],
        "scope_sha256": digest(encoded(scope)),
        "table_schemas": table_schemas,
        "before_rows_file": "before_rows.json",
        "before_rows_file_sha256": digest(before_rows_bytes),
        "before_rows_count": {table: len(before_tables[table]) for table in TABLES},
        "before_rows_table_sha256": {
            table: digest(encoded(before_tables[table])) for table in TABLES
        },
        "summary": summary,
    }
    return plan, before_rows


def _load_plan_and_rows(directory: Path) -> tuple[dict[str, Any], dict[str, Any], bytes]:
    plan_path = directory / "plan.json"
    before_path = directory / "before_rows.json"
    plan = read_json(plan_path)
    before_bytes = before_path.read_bytes()
    if file_hash(before_path) != plan.get("before_rows_file_sha256"):
        raise ValueError("before rows snapshot hash 不符")
    before_rows = json.loads(before_bytes)
    if before_rows.get("schema_version") != SCHEMA or before_rows.get("keys") != plan.get("keys"):
        raise ValueError("before rows snapshot 與 plan scope 不符")
    for table in TABLES:
        rows = before_rows.get("tables", {}).get(table)
        if (
            not isinstance(rows, list)
            or len(rows) != plan.get("before_rows_count", {}).get(table)
            or digest(encoded(rows)) != plan.get("before_rows_table_sha256", {}).get(table)
        ):
            raise ValueError(f"{table} before rows 數量／hash 不符")
    return plan, before_rows, before_bytes


def _current_target_rows(
    connection: sqlite3.Connection, table: str, plan: dict[str, Any],
) -> tuple[list[dict[str, object]], dict[str, list[dict[str, object]]]]:
    by_day = _read_day_rows(connection, table, TARGET_DATES)
    keys = {tuple(key) for key in plan["keys"]}
    affected = _target_rows(by_day, keys, set(plan["closed_dates"]))
    return affected, by_day


def _expected_table_rows(before_rows: dict[str, Any], table: str) -> list[dict[str, object]]:
    return before_rows["tables"][table]


def _check_before_state(
    connection: sqlite3.Connection, plan: dict[str, Any], before_rows: dict[str, Any],
    official_codes: set[str] | None,
) -> None:
    for table in TABLES:
        if _schema_snapshot(connection, table) != plan["table_schemas"][table]:
            raise ValueError(f"正式資料 schema 已變更：{table}")
        current, by_day = _current_target_rows(connection, table, plan)
        expected = _expected_table_rows(before_rows, table)
        if current != expected:
            raise ValueError(f"正式資料受影響 before rows 已漂移：{table}")
        for day in plan["closed_dates"]:
            expected_day = [row for row in expected if exclusions._normal_date(row["日期"]) == day]
            if by_day.get(day, []) != expected_day:
                raise ValueError(f"休市日完整列集合已漂移：{table}/{day}")
    if official_codes is not None:
        may20_codes = set().union(
            *(
                {exclusions._normal_symbol(row["證券代號"]) for row in _read_day_rows(connection, table, ("20260520",))["20260520"]}
                for table in TABLES
            )
        )
        absent = {symbol for symbol in may20_codes if symbol not in official_codes}
        expected_absent = {symbol for day, symbol in plan["keys"] if day == "20260520"}
        if absent != expected_absent:
            raise ValueError("20260520 官方報表缺漏代號集合已漂移")


def _check_after_state(
    connection: sqlite3.Connection, plan: dict[str, Any], official_codes: set[str] | None,
) -> None:
    for table in TABLES:
        if _schema_snapshot(connection, table) != plan["table_schemas"][table]:
            raise ValueError(f"正式資料 schema 已變更：{table}")
        by_day = _read_day_rows(connection, table, TARGET_DATES)
        for day in plan["closed_dates"]:
            if by_day.get(day):
                raise ValueError(f"修訂後休市日仍有列：{table}/{day}")
        forbidden = {tuple(key) for key in plan["keys"]}
        if any(
            (day, exclusions._normal_symbol(row["證券代號"])) in forbidden
            for day, rows in by_day.items() for row in rows
        ):
            raise ValueError(f"修訂後仍有精確排除 key：{table}")
    if official_codes is not None:
        remaining_codes = set().union(
            *(
                {exclusions._normal_symbol(row["證券代號"]) for row in _read_day_rows(connection, table, ("20260520",))["20260520"]}
                for table in TABLES
            )
        )
        if {symbol for symbol in remaining_codes if symbol not in official_codes}:
            raise ValueError("修訂後 20260520 仍有官方報表未列代號")


def _source_context(plan: dict[str, Any], root: Path) -> tuple[Path, set[str]]:
    source_dir = exclusions._resolve_relative(root, plan["evidence_archive_relative"])
    _archive, acquired_at, official_codes = exclusions._verify_archive(
        root, plan["evidence_archive_relative"], plan["evidence_archive_sha256"], plan["source_files"],
    )
    if acquired_at.isoformat() != plan["source_available_at"]:
        raise ValueError("官方來源取得時間已漂移")
    market = exclusions._validate_market_chain(
        Path(plan["database_path"]), root, plan["market_receipt_relative_dir"],
        full_source_validation=False,
    )
    if (
        market["plan_sha256"] != plan.get("market_plan_sha256")
        or market["receipt_sha256"] != plan.get("market_receipt_sha256")
    ):
        raise ValueError("正式市場來源版本與排除計畫不符")
    for day, symbol in (tuple(key) for key in plan["keys"] if key[0] == "20260520"):
        if symbol in official_codes:
            raise ValueError("May 20 排除 key 已出現在官方完整市場報表")
    return source_dir, official_codes


def _marker(directory: Path, plan: dict[str, Any], state: str, **extra: object) -> None:
    atomic(
        directory / "revision.json",
        encoded(
            {
                "schema_version": exclusions.REVISION_SCHEMA,
                "state": state,
                "database_path": plan["database_path"],
                "plan_sha256": file_hash(directory / "plan.json"),
                "backup_sha256": read_json(directory / "journal.json")["backup_sha256"],
                "source_start_date": plan["source_start_date"],
                "source_end_date": plan["source_end_date"],
                "observed_at": now(),
                "historical_pit": False,
                **extra,
            }
        ),
    )


def _make_receipt(
    directory: Path, plan: dict[str, Any], journal: dict[str, Any], state: str,
    **extra: object,
) -> dict[str, Any]:
    receipt = {
        **journal,
        "schema_version": SCHEMA,
        "state": state,
        "completed_at": now(),
        "summary": plan["summary"],
        "source_available_at": plan["source_available_at"],
        "evidence_archive_sha256": plan["evidence_archive_sha256"],
        "market_plan_sha256": plan["market_plan_sha256"],
        **extra,
    }
    name = "receipt.json" if state == "applied" else "rollback.json"
    atomic(directory / name, encoded(receipt))
    _marker(
        directory,
        plan,
        state,
        **{
            ("receipt_sha256" if state == "applied" else "rollback_sha256"): file_hash(directory / name),
        },
    )
    return receipt


def _backup_database(database_path: Path, backup_path: Path) -> str:
    with readonly(database_path) as source, sqlite3.connect(backup_path) as destination:
        source.backup(destination, pages=8192)
    with readonly(backup_path) as saved:
        if saved.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise ValueError("SQLite 完整備份 quick_check 失敗")
    return file_hash(backup_path)


def prepare(
    database_path: Path, evidence_dir: Path, market_receipt_dir: Path, receipt_dir: Path,
) -> dict[str, Any]:
    root = root_for(database_path).resolve(strict=True)
    expected_parent = (root / exclusions.RECEIPT_DIR).resolve()
    receipt_dir = receipt_dir.resolve()
    if receipt_dir.parent != expected_parent or receipt_dir.exists():
        raise ValueError("dry-run receipt 必須是正式排除修訂目錄下的新目錄")
    plan, before_rows = build_plan(database_path, evidence_dir, market_receipt_dir, receipt_dir)
    receipt_dir.mkdir(parents=True)
    try:
        atomic(receipt_dir / "before_rows.json", encoded(before_rows))
        atomic(receipt_dir / "plan.json", encoded(plan))
    except BaseException:
        shutil.rmtree(receipt_dir)
        raise
    return {
        "receipt_dir": str(receipt_dir),
        "plan_path": str(receipt_dir / "plan.json"),
        "plan_sha256": file_hash(receipt_dir / "plan.json"),
        "summary": plan["summary"],
    }


def apply(plan_path: Path, expected_hash: str, confirm: str) -> dict[str, Any]:
    plan = read_json(plan_path)
    root = root_for(Path(plan["database_path"]))
    reservation = acquire_heavy_chain_reservation(root / "output/release_v4/.ml_heavy_chain.lock")
    if reservation is None:
        raise ValueError("正式維護／重建流程正在使用 heavy-chain lock")
    try:
        return _apply_under_lock(plan_path, expected_hash, confirm)
    finally:
        release_heavy_chain_reservation(reservation)


def _apply_under_lock(plan_path: Path, expected_hash: str, confirm: str) -> dict[str, Any]:
    if confirm != CONFIRM:
        raise ValueError("缺少正式修訂確認字串")
    plan_path = plan_path.resolve(strict=True)
    directory = plan_path.parent
    plan, before_rows, before_bytes = _load_plan_and_rows(directory)
    if file_hash(plan_path) != expected_hash.removeprefix("sha256:"):
        raise ValueError("dry-run plan hash 不符")
    database_path = Path(plan["database_path"]).resolve(strict=True)
    root = root_for(database_path).resolve(strict=True)
    if relative_to_root(root, directory) != plan.get("receipt_relative_dir"):
        raise ValueError("receipt 目錄與 plan 不符")
    if set(path.name for path in directory.iterdir()) != {"plan.json", "before_rows.json"}:
        raise ValueError("apply 只允許 dry-run plan/before rows 所在的新 receipt 目錄")
    source_dir, official_codes = _source_context(plan, root)
    market_dir = exclusions._resolve_relative(root, plan["market_receipt_relative_dir"])
    fresh, fresh_rows = build_plan(database_path, source_dir, market_dir, directory)
    comparable = {key: value for key, value in fresh.items() if key != "created_at"}
    original = {key: value for key, value in plan.items() if key != "created_at"}
    if encoded(comparable) != encoded(original) or encoded(fresh_rows) != before_bytes:
        raise ValueError("dry-run 來源、正式受影響列或計畫內容已漂移")
    if shutil.disk_usage(root).free < database_path.stat().st_size + 128 * 1024 * 1024:
        raise ValueError("備份可用空間不足")

    backup = directory / "sqlite_before.db"
    backup_sha256 = _backup_database(database_path, backup)
    with readonly(backup) as saved:
        _check_before_state(saved, plan, before_rows, official_codes)
    journal = {
        "schema_version": SCHEMA,
        "state": "prepared",
        "database_path": str(database_path),
        "plan_sha256": file_hash(plan_path),
        "backup_sha256": backup_sha256,
        "before_rows_file_sha256": plan["before_rows_file_sha256"],
        "started_at": now(),
    }
    atomic(directory / "journal.json", encoded(journal))
    _marker(directory, plan, "pending")
    connection = sqlite3.connect(database_path, timeout=60)
    try:
        connection.execute("BEGIN IMMEDIATE")
        # Revalidate the target rows and closed-date completeness after obtaining the writer lock.
        _check_before_state(connection, plan, before_rows, official_codes)
        total_deleted: dict[str, int] = {}
        keys = [tuple(key) for key in plan["keys"]]
        for table in TABLES:
            cursor = connection.executemany(
                f'DELETE FROM "{table}" WHERE "日期"=? AND "證券代號"=?', keys,
            )
            total_deleted[table] = cursor.rowcount
        _check_after_state(connection, plan, official_codes)
        expected = {
            table: sum(
                1 for row in before_rows["tables"][table]
                if (exclusions._normal_date(row["日期"]), exclusions._normal_symbol(row["證券代號"])) in set(map(tuple, plan["keys"]))
            )
            for table in TABLES
        }
        if total_deleted != expected:
            raise ValueError(f"刪除筆數與 before snapshot 不符：{total_deleted}")
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()
    return _make_receipt(directory, plan, journal, "applied", deleted_rows=total_deleted)


def _restore_before_rows(
    connection: sqlite3.Connection, plan: dict[str, Any], before_rows: dict[str, Any],
    official_codes: set[str] | None,
) -> dict[str, int]:
    _check_after_state(connection, plan, official_codes)
    restored: dict[str, int] = {}
    for table in TABLES:
        columns = plan["table_schemas"][table]["columns"]
        rows = before_rows["tables"][table]
        if not rows:
            restored[table] = 0
            continue
        quoted = ",".join('"' + column.replace('"', '""') + '"' for column in columns)
        marks = ",".join("?" for _ in columns)
        cursor = connection.executemany(
            f'INSERT INTO "{table}" ({quoted}) VALUES ({marks})',
            [[row[column] for column in columns] for row in rows],
        )
        restored[table] = cursor.rowcount
    for table in TABLES:
        current, _ = _current_target_rows(connection, table, plan)
        if current != before_rows["tables"][table]:
            raise ValueError(f"rollback 列讀回與本輪 before rows 不符：{table}")
    return restored


def recover(directory: Path, *, rollback: bool, confirm: str) -> dict[str, Any]:
    plan = read_json(directory.resolve(strict=True) / "plan.json")
    root = root_for(Path(plan["database_path"]))
    reservation = acquire_heavy_chain_reservation(root / "output/release_v4/.ml_heavy_chain.lock")
    if reservation is None:
        raise ValueError("正式維護／重建流程正在使用 heavy-chain lock")
    try:
        return _recover_under_lock(directory, rollback=rollback, confirm=confirm)
    finally:
        release_heavy_chain_reservation(reservation)


def _recover_under_lock(directory: Path, *, rollback: bool, confirm: str) -> dict[str, Any]:
    if confirm != CONFIRM:
        raise ValueError("缺少回復確認字串")
    directory = directory.resolve(strict=True)
    plan, before_rows, _before_bytes = _load_plan_and_rows(directory)
    database_path = Path(plan["database_path"]).resolve(strict=True)
    root = root_for(database_path).resolve(strict=True)
    if relative_to_root(root, directory) != plan.get("receipt_relative_dir"):
        raise ValueError("回復 receipt 目錄不符")
    journal = read_json(directory / "journal.json")
    backup = directory / "sqlite_before.db"
    if (
        file_hash(directory / "plan.json") != journal.get("plan_sha256")
        or file_hash(backup) != journal.get("backup_sha256")
    ):
        raise ValueError("回復 plan 或 SQLite before backup hash 不符")
    marker = read_json(directory / "revision.json")
    # Recovery is tied to the immutable official archive just like apply. If
    # the archive is unavailable or altered, restore that evidence first.
    _source_dir, official_codes = _source_context(plan, root)
    if rollback:
        if marker.get("state") != "applied":
            raise ValueError("只可 rollback 已套用的排除修訂")
    elif marker.get("state") != "pending":
        raise ValueError("只可 resume pending 排除修訂")
    connection = sqlite3.connect(database_path, timeout=60)
    try:
        connection.execute("BEGIN IMMEDIATE")
        if rollback:
            try:
                _check_after_state(connection, plan, official_codes)
            except ValueError:
                # A prior rollback may have committed its row transaction before its
                # receipt was finalized. Accept only the exact before state then.
                _check_before_state(connection, plan, before_rows, official_codes)
                restored = {table: 0 for table in TABLES}
            else:
                restored = _restore_before_rows(connection, plan, before_rows, official_codes)
            connection.commit()
            return _make_receipt(directory, plan, journal, "rolled_back", restored_rows=restored)
        try:
            _check_after_state(connection, plan, official_codes)
        except ValueError:
            _check_before_state(connection, plan, before_rows, official_codes)
            connection.rollback()
            return _make_receipt(directory, plan, journal, "rolled_back", restored_rows={table: 0 for table in TABLES})
        connection.commit()
        return _make_receipt(directory, plan, journal, "applied", recovered=True)
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prep = commands.add_parser("prepare", help="驗證官方來源並建立唯讀 dry-run plan")
    prep.add_argument("--db", type=Path, required=True)
    prep.add_argument("--evidence-dir", type=Path, required=True)
    prep.add_argument("--market-receipt-dir", type=Path, required=True)
    prep.add_argument("--receipt-dir", type=Path, required=True)
    apply_parser = commands.add_parser("apply", help="備份並交易式排除已核驗列")
    apply_parser.add_argument("--plan", type=Path, required=True)
    apply_parser.add_argument("--expected-plan-hash", required=True)
    apply_parser.add_argument("--confirm", default="")
    resume = commands.add_parser("resume", help="完成 pending 修訂或標記尚未寫入資料庫的準備回復")
    resume.add_argument("--receipt-dir", type=Path, required=True)
    resume.add_argument("--confirm", default="")
    rollback = commands.add_parser("rollback", help="只恢復本輪受影響的 before rows")
    rollback.add_argument("--receipt-dir", type=Path, required=True)
    rollback.add_argument("--confirm", default="")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "prepare":
        result = prepare(args.db, args.evidence_dir, args.market_receipt_dir, args.receipt_dir)
    elif args.command == "apply":
        result = apply(args.plan, args.expected_plan_hash, args.confirm)
    else:
        result = recover(args.receipt_dir, rollback=args.command == "rollback", confirm=args.confirm)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
