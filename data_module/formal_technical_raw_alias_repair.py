"""以正式日價重建技術快取中的六個原始數值欄，並保留可驗證回復資料。"""

from __future__ import annotations

import csv
from contextlib import contextmanager
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
from numbers import Real
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sqlite3
import tempfile
from typing import Any, Callable, Iterable, Iterator, Mapping, Sequence

from data_module.ml_storage_capacity import (
    acquire_heavy_chain_reservation,
    release_heavy_chain_reservation,
)


SCHEMA_VERSION = "formal-technical-raw-alias-repair.v1"
TECHNICAL_STAGE_SCHEMA = "technical-cache-rebuild-stage.v1"
SOURCE_RECEIPT_ROOT = Path("output/scheduled/formal_technical_repair_receipts")
RECEIPT_ROOT = Path("output/scheduled/formal_technical_raw_alias_repair_receipts")
CONFIRM = "repair-formal-technical-raw-aliases"
ALIASES = (
    "最後揭示買價",
    "最後揭示買量",
    "最後揭示賣價",
    "最後揭示賣量",
    "本益比",
    "漲跌價差",
)
INTEGER_ALIASES = frozenset(("最後揭示買量", "最後揭示賣量"))
PRICE_ALIASES = frozenset(("最後揭示買價", "最後揭示賣價"))
KEYS = ("日期", "證券代號")
CSV_ENCODING = "utf-8-sig"
_CHUNK_ROWS = 10_000
_TABLE_HASH_CHUNK_ROWS = 5_000
_HASH_RE = re.compile(r"^(?:sha256:)?[0-9a-f]{64}$")
_NUMERIC_LITERAL_RE = re.compile(
    r"[+-]?(?:(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?\Z",
    re.ASCII,
)


class RawAliasRepairError(ValueError):
    """來源證據、完整性或回復狀態不符時停止修復。"""


def _quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
        + "\n"
    ).encode("utf-8")


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _file_identity(path: Path) -> dict[str, int]:
    stat = path.stat()
    return {"size_bytes": stat.st_size, "mtime_ns": stat.st_mtime_ns}


def _atomic_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _seal(payload: Mapping[str, Any]) -> dict[str, Any]:
    body = dict(payload)
    body.pop("payload_sha256", None)
    return {**body, "payload_sha256": hashlib.sha256(_json_bytes(body)).hexdigest()}


def _write_sealed(path: Path, payload: Mapping[str, Any]) -> str:
    sealed = _seal(payload)
    data = _json_bytes(sealed)
    _atomic_bytes(path, data)
    return hashlib.sha256(data).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RawAliasRepairError(f"修復證據無法讀取：{path}") from exc
    if not isinstance(payload, dict):
        raise RawAliasRepairError(f"修復證據格式不符：{path}")
    return payload


def _read_sealed(path: Path) -> dict[str, Any]:
    payload = _read_json(path)
    actual = payload.pop("payload_sha256", None)
    expected = hashlib.sha256(_json_bytes(payload)).hexdigest()
    if actual != expected:
        raise RawAliasRepairError(f"修復紀錄自我雜湊不符：{path}")
    payload["payload_sha256"] = actual
    return payload


@contextmanager
def _readonly(path: Path) -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(path.resolve(strict=True).as_uri() + "?mode=ro", uri=True, timeout=30)
    try:
        connection.execute("PRAGMA query_only=ON")
        yield connection
    finally:
        connection.close()


@contextmanager
def _readonly_immutable(path: Path) -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(
        path.resolve(strict=True).as_uri() + "?mode=ro&immutable=1",
        uri=True,
        timeout=30,
    )
    try:
        connection.execute("PRAGMA query_only=ON")
        yield connection
    finally:
        connection.close()


@contextmanager
def _sqlite_connection(path: Path, *, timeout: int = 30) -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(path, timeout=timeout)
    try:
        yield connection
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()


def _database_path(root: Path) -> Path:
    return root / "sqlite" / "twstock.db"


def _normalize_date(value: object) -> str:
    text = str(value).strip().split(" ", 1)[0]
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    text = text.replace("-", "").replace("/", "")
    if not re.fullmatch(r"\d{8}", text):
        raise RawAliasRepairError(f"日期鍵格式不符：{value!r}")
    try:
        date(int(text[:4]), int(text[4:6]), int(text[6:8]))
    except ValueError as exc:
        raise RawAliasRepairError(f"日期鍵格式不符：{value!r}") from exc
    return text


def _normalize_symbol(value: object) -> str:
    if value is None:
        raise RawAliasRepairError("證券代號鍵為空")
    text = str(value).strip()
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    if text.isdigit() and len(text) < 4:
        text = text.zfill(4)
    if not text or text.lower() in {"nan", "none", "<na>"}:
        raise RawAliasRepairError("證券代號鍵為空")
    return text.upper()


def _decimal_value(value: object, column: str) -> Decimal | None:
    """解析六個原始數值欄；缺值採明確規則，其他非數字一律拒絕。"""
    if column not in ALIASES:
        raise RawAliasRepairError(f"不是受保護的 raw alias 欄位：{column}")
    if value is None or _is_numeric_nan(value):
        return None
    text = str(value).strip()
    if not text:
        return None
    if text == "--" and column in PRICE_ALIASES:
        return None
    if len(text) > 256 or _NUMERIC_LITERAL_RE.fullmatch(text) is None:
        raise RawAliasRepairError(f"正式日價的 {column} 不是有效數值：{value!r}")
    try:
        number = Decimal(text.replace(",", ""))
    except (InvalidOperation, ValueError) as exc:
        raise RawAliasRepairError(f"正式日價的 {column} 不是有效數值：{value!r}") from exc
    if not number.is_finite():
        raise RawAliasRepairError(f"正式日價的 {column} 不可為非有限數值：{value!r}")
    if number and abs(number.adjusted()) > 308:
        raise RawAliasRepairError(f"正式日價的 {column} 超出 SQLite REAL 可用範圍：{value!r}")
    if column in INTEGER_ALIASES and number != number.to_integral_value():
        raise RawAliasRepairError(f"正式日價的 {column} 不是整數：{value!r}")
    return number


def _is_numeric_nan(value: object) -> bool:
    """pandas 將 SQLite REAL NULL 讀成數值 NaN；文字 'nan' 不視為缺值。"""
    if not isinstance(value, Real):
        return False
    try:
        return math.isnan(float(value))
    except (OverflowError, TypeError, ValueError):
        return False


def _decimal_text(number: Decimal) -> str:
    if number == 0:
        return "0"
    sign, digits_tuple, exponent = number.as_tuple()
    if not isinstance(exponent, int):
        raise RawAliasRepairError("正式日價的數值指數不正確")
    is_negative = sign == 1
    digits = list(digits_tuple)
    while len(digits) > 1 and digits[-1] == 0:
        digits.pop()
        exponent += 1
    digits_text = "".join(str(digit) for digit in digits)
    if exponent >= 0:
        body = digits_text + ("0" * exponent)
    else:
        point = len(digits_text) + exponent
        if point > 0:
            body = digits_text[:point] + "." + digits_text[point:]
        else:
            body = "0." + ("0" * (-point)) + digits_text
    return ("-" if is_negative else "") + body


def _numeric_text(value: object, column: str) -> str:
    number = _decimal_value(value, column)
    if number is None:
        return ""
    if column in INTEGER_ALIASES:
        return str(int(number))
    return _decimal_text(number)


def _numeric_storage_value(value: object, column: str) -> int | float | None:
    """將來源值轉為與正式欄位 affinity 相符的 canonical SQLite 值。"""
    text = _numeric_text(value, column)
    if not text:
        return None
    if column in INTEGER_ALIASES:
        return int(text)
    number = Decimal(text)
    converted = float(number)
    if not math.isfinite(converted) or Decimal(str(converted)) != number:
        raise RawAliasRepairError(
            f"正式日價的 {column} 無法在 SQLite REAL 中精確往返：{value!r}"
        )
    return converted


def _is_csv_null(value: object, column: str | None = None) -> bool:
    if value is None or _is_numeric_nan(value):
        return True
    if isinstance(value, str) and not value.strip():
        return True
    return column in PRICE_ALIASES and isinstance(value, str) and value.strip() == "--"


def _same_numeric(left: object, right: object, column: str | None = None) -> bool:
    if column is None:
        return False
    try:
        left_text = _numeric_text(left, column)
        right_text = _numeric_text(right, column)
    except RawAliasRepairError:
        return False
    if not left_text or not right_text:
        return not left_text and not right_text
    return Decimal(left_text) == Decimal(right_text)


def _value_delta(existing: object, canonical: object, column: str) -> dict[str, int]:
    old_null = _is_csv_null(existing, column)
    new_null = _is_csv_null(canonical, column)
    same = _same_numeric(existing, canonical, column)
    return {
        "changed_values": 0 if same else 1,
        "canonical_null_existing_filled": int(new_null and not old_null),
        "canonical_value_existing_null": int(not new_null and old_null),
        "both_filled_different": int(not new_null and not old_null and not same),
    }


def _date_symbol_key(day: object, symbol: object) -> tuple[str, str]:
    return _normalize_date(day), _normalize_symbol(symbol)


def _read_table_columns(connection: sqlite3.Connection, table: str) -> list[str]:
    if table not in {str(row[0]) for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}:
        raise RawAliasRepairError(f"資料表不存在：{table}")
    return [str(row[1]) for row in connection.execute(f"PRAGMA table_info({_quote(table)})")]


def _table_fingerprint(connection: sqlite3.Connection, table: str) -> dict[str, Any]:
    """與 formal technical publisher 相同算法算全表 hash，並同掃 schema/key/欄位指紋。"""
    columns = _read_table_columns(connection, table)
    missing = sorted(set((*KEYS, *ALIASES)) - set(columns))
    if missing:
        raise RawAliasRepairError(f"{table} 缺少受保護欄位：{missing}")
    column_indexes = {name: columns.index(name) for name in columns}
    full_hash = hashlib.sha256(_json_bytes(columns))
    key_hash = hashlib.sha256(_json_bytes(list(KEYS)))
    alias_hash = hashlib.sha256(_json_bytes(list(KEYS) + list(ALIASES)))
    non_target_columns = [name for name in columns if name not in ALIASES]
    non_target_hash = hashlib.sha256(_json_bytes(non_target_columns))
    schema_rows = list(connection.execute(
        f"SELECT type,name,tbl_name,sql FROM sqlite_master WHERE tbl_name=? ORDER BY type,name",
        (table,),
    ))
    schema_hash = hashlib.sha256(_json_bytes({
        "table_info": list(connection.execute(f"PRAGMA table_info({_quote(table)})")),
        "objects": schema_rows,
    })).hexdigest()
    cursor = connection.execute(
        f"SELECT * FROM {_quote(table)} ORDER BY {_quote('證券代號')}, {_quote('日期')}"
    )
    rows_seen = 0
    while rows := cursor.fetchmany(_TABLE_HASH_CHUNK_ROWS):
        full_hash.update(_json_bytes(rows))
        keys = []
        aliases = []
        non_targets = []
        for row in rows:
            day, symbol = _date_symbol_key(
                row[column_indexes["日期"]], row[column_indexes["證券代號"]]
            )
            keys.append([day, symbol])
            aliases.append([day, symbol, *(row[column_indexes[name]] for name in ALIASES)])
            non_targets.append([row[column_indexes[name]] for name in non_target_columns])
        key_hash.update(_json_bytes(keys))
        alias_hash.update(_json_bytes(aliases))
        non_target_hash.update(_json_bytes(non_targets))
        rows_seen += len(rows)
    return {
        "table": table,
        "columns": columns,
        "schema_sha256": schema_hash,
        "rows": rows_seen,
        "table_sha256": full_hash.hexdigest(),
        "keys_sha256": key_hash.hexdigest(),
        "aliases_sha256": alias_hash.hexdigest(),
        "non_target_values_sha256": non_target_hash.hexdigest(),
        "non_target_columns": non_target_columns,
    }


def _table_hash(connection: sqlite3.Connection, table: str) -> str:
    columns = _read_table_columns(connection, table)
    digest = hashlib.sha256(_json_bytes(columns))
    cursor = connection.execute(
        f"SELECT * FROM {_quote(table)} ORDER BY {_quote('證券代號')}, {_quote('日期')}"
    )
    while rows := cursor.fetchmany(_TABLE_HASH_CHUNK_ROWS):
        digest.update(_json_bytes(rows))
    return digest.hexdigest()


def _current_fingerprints(root: Path) -> dict[str, Any]:
    db_path = _database_path(root)
    with _readonly(db_path) as connection:
        return {
            "daily_prices": {"table_sha256": _table_hash(connection, "daily_prices")},
            "technical_indicators": _table_fingerprint(connection, "technical_indicators"),
        }


def _resolve_within(root: Path, value: object, *, must_exist: bool = True) -> Path:
    if not isinstance(value, str) or not value:
        raise RawAliasRepairError("修復證據缺少路徑")
    candidate = Path(value)
    try:
        resolved = candidate.resolve(strict=must_exist)
        resolved.relative_to(root.resolve(strict=True))
    except (OSError, ValueError) as exc:
        raise RawAliasRepairError(f"修復路徑越界或不存在：{value}") from exc
    if candidate.is_symlink():
        raise RawAliasRepairError(f"修復路徑不可為符號連結：{candidate}")
    return resolved


def _safe_target(root: Path, value: object) -> Path:
    target = _resolve_within(root, value)
    technical_dir = (root / "technical_analysis").resolve(strict=True)
    aggregate = (root / "meta_data" / "all_stocks_data.csv").resolve(strict=False)
    if target == aggregate:
        return target
    if target.parent == technical_dir and target.name.endswith("_indicators.csv"):
        symbol = target.name[: -len("_indicators.csv")]
        if re.fullmatch(r"[A-Za-z0-9]{4,8}", symbol):
            return target
    raise RawAliasRepairError(f"技術衍生檔目標不在允許範圍：{target}")


def _exclusion_identities(root: Path) -> list[dict[str, str]]:
    from data_module.excluded_daily_price_revision import load_exclusion_evidence

    evidence = load_exclusion_evidence(_database_path(root))
    fields = ("plan_sha256", "receipt_sha256", "receipt_path")
    result = [{name: str(item[name]) for name in fields} for item in evidence]
    return sorted(result, key=lambda item: (item["receipt_path"], item["plan_sha256"], item["receipt_sha256"]))


def _load_technical_publication(
    root: Path,
    technical_receipt_dir: Path,
    *,
    check_live: bool,
) -> dict[str, Any]:
    root = root.resolve(strict=True)
    source_root = (root / SOURCE_RECEIPT_ROOT).resolve(strict=True)
    run_dir = technical_receipt_dir.resolve(strict=True)
    if run_dir.parent != source_root or run_dir.is_symlink():
        raise RawAliasRepairError("run02 technical receipt 不在正式 receipt 目錄")
    source_path = run_dir / "source.json"
    manifest_path = run_dir / "stage" / "manifest.json"
    receipt_path = run_dir / "receipt.json"
    journal_path = run_dir / "journal.json"
    if not all(path.is_file() and not path.is_symlink() for path in (source_path, manifest_path, receipt_path, journal_path)):
        raise RawAliasRepairError("正式技術重算缺少 applied receipt、manifest 或 journal")
    source = _read_json(source_path)
    manifest = _read_json(manifest_path)
    receipt = _read_json(receipt_path)
    journal = _read_json(journal_path)
    if receipt != journal or receipt.get("state") != "applied":
        raise RawAliasRepairError("正式技術重算尚未 applied，或 receipt/journal 不一致")
    if manifest.get("schema_version") != TECHNICAL_STAGE_SCHEMA:
        raise RawAliasRepairError("正式技術重算 manifest 版型不符")
    if Path(str(source.get("root", ""))).resolve() != root:
        raise RawAliasRepairError("正式技術重算 root 與目前資料根目錄不符")
    source_db = _resolve_within(root, source.get("source_db"))
    if source_db.parent != run_dir or manifest.get("source_db") != str(source_db):
        raise RawAliasRepairError("正式技術重算 immutable source 路徑不符")
    source_sha = _file_hash(source_db)
    source_file_identity = _file_identity(source_db)
    manifest_sha = _file_hash(manifest_path)
    receipt_sha = _file_hash(receipt_path)
    if source_sha != source.get("source_sha256") or manifest.get("source_sha256") != source_sha:
        raise RawAliasRepairError("正式技術重算 source hash 不符")
    if receipt.get("manifest_sha256") != manifest_sha:
        raise RawAliasRepairError("正式技術重算 manifest hash 未綁定 applied receipt")
    if receipt.get("source_sha256") != source_sha or Path(str(receipt.get("source_db", ""))).resolve() != source_db:
        raise RawAliasRepairError("正式技術 applied receipt 的來源身分不符")
    if not _HASH_RE.fullmatch(str(receipt.get("technical_after_hash", ""))):
        raise RawAliasRepairError("正式技術 applied receipt 缺少完整 technical after hash")
    identities = _exclusion_identities(root)
    if manifest.get("exclusion_evidence_identities") != identities:
        raise RawAliasRepairError("正式技術重算所綁定的錯日排除證據已變更")

    manifest_files = manifest.get("files")
    receipt_files = receipt.get("files")
    if not isinstance(manifest_files, list) or not isinstance(receipt_files, list) or not manifest_files:
        raise RawAliasRepairError("正式技術重算沒有衍生 CSV 清冊")
    receipt_by_target: dict[Path, Mapping[str, Any]] = {}
    for item in receipt_files:
        if not isinstance(item, dict):
            raise RawAliasRepairError("正式技術 applied CSV 清冊格式不符")
        target = _safe_target(root, item.get("target_path"))
        if target in receipt_by_target:
            raise RawAliasRepairError("正式技術 applied CSV 目標重複")
        receipt_by_target[target] = item
    files: list[dict[str, Any]] = []
    seen: set[Path] = set()
    for item in manifest_files:
        if not isinstance(item, dict):
            raise RawAliasRepairError("正式技術 manifest CSV 清冊格式不符")
        target = _safe_target(root, item.get("target_path"))
        staged = _resolve_within(run_dir, item.get("staged_path"))
        applied = receipt_by_target.get(target)
        if target in seen or applied is None:
            raise RawAliasRepairError("正式技術 CSV 目標有重複或缺少 applied 身分")
        seen.add(target)
        if (
            applied.get("after_sha256") != item.get("after_sha256")
            or not _HASH_RE.fullmatch(str(item.get("after_sha256", "")))
            or _file_hash(staged) != item.get("after_sha256")
        ):
            raise RawAliasRepairError(f"正式技術 CSV staging/applied hash 不符：{target}")
        files.append({
            "target_path": str(target),
            "technical_after_sha256": str(item["after_sha256"]),
            "technical_row_count": int(item.get("row_count_after", -1)),
            "staged_path": str(staged),
        })
    if seen != set(receipt_by_target) or sum(item["target_path"].endswith("all_stocks_data.csv") for item in files) != 1:
        raise RawAliasRepairError("正式技術 applied CSV 目標集合不完整")

    with _readonly(source_db) as source_conn:
        if source_conn.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise RawAliasRepairError("正式技術 immutable source SQLite quick_check 失敗")
        source_daily_hash = _table_hash(source_conn, "daily_prices")
    if source_daily_hash != source.get("daily_before_hash"):
        raise RawAliasRepairError("immutable source daily_prices 與 technical source receipt 不符")

    result = {
        "root": str(root),
        "technical_receipt_dir": str(run_dir),
        "technical_source_json": str(source_path),
        "technical_source_json_sha256": _file_hash(source_path),
        "technical_receipt_path": str(receipt_path),
        "technical_receipt_sha256": receipt_sha,
        "technical_manifest_path": str(manifest_path),
        "technical_manifest_sha256": manifest_sha,
        "source_db": str(source_db),
        "source_sha256": source_sha,
        "source_db_file_identity": source_file_identity,
        "daily_before_hash": source_daily_hash,
        "technical_after_hash": str(receipt["technical_after_hash"]),
        "exclusion_evidence_identities": identities,
        "files": sorted(files, key=lambda item: item["target_path"]),
        "technical_rows": int(manifest.get("rows", -1)),
        "technical_manifest_schema": manifest.get("schema_version"),
    }
    if check_live:
        current = _current_fingerprints(root)
        if current["daily_prices"]["table_sha256"] != source_daily_hash:
            raise RawAliasRepairError("正式 daily_prices 已漂移，拒絕 raw alias staging")
        if current["technical_indicators"]["table_sha256"] != result["technical_after_hash"]:
            raise RawAliasRepairError("正式 technical_indicators 未等於已發布 run02 after hash")
        for item in files:
            target = Path(item["target_path"])
            if not target.is_file() or _file_hash(target) != item["technical_after_sha256"]:
                raise RawAliasRepairError(f"正式技術 CSV 尚未完整發布或 hash 已漂移：{target}")
        result["daily_fingerprint"] = current["daily_prices"]
        result["technical_fingerprint"] = current["technical_indicators"]
    return result


def prepare(root: Path, technical_receipt_dir: Path, receipt_dir: Path) -> dict[str, Any]:
    """驗證已發布 run02 並建立新修復 receipt；只讀正式 DB/CSV。"""
    root = Path(root).resolve(strict=True)
    technical_receipt_dir = Path(technical_receipt_dir)
    receipt_dir = Path(receipt_dir)
    expected_parent = (root / RECEIPT_ROOT).resolve(strict=False)
    if receipt_dir.resolve(strict=False).parent != expected_parent:
        raise RawAliasRepairError("新修復紀錄必須是正式 raw alias receipt 根目錄的直接子目錄")
    if receipt_dir.exists() or receipt_dir.is_symlink():
        raise RawAliasRepairError("拒絕覆寫既有 raw alias 修復紀錄")
    evidence = _load_technical_publication(root, technical_receipt_dir, check_live=True)
    receipt_dir.mkdir(parents=True, exist_ok=False)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "state": "prepared",
        "root": str(root),
        "receipt_dir": str(receipt_dir.resolve()),
        "prepared_at": datetime.now(timezone.utc).isoformat(),
        **evidence,
        "target_count": len(evidence["files"]),
    }
    _write_sealed(receipt_dir / "source.json", payload)
    return {"state": "prepared", "receipt_dir": str(receipt_dir), "targets": len(evidence["files"])}


def _load_evidence(receipt_dir: Path, *, check_technical_publication: bool = True) -> dict[str, Any]:
    receipt_dir = Path(receipt_dir).resolve(strict=True)
    evidence = _read_sealed(receipt_dir / "source.json")
    if evidence.get("schema_version") != SCHEMA_VERSION or evidence.get("receipt_dir") != str(receipt_dir):
        raise RawAliasRepairError("raw alias 修復 source receipt 身分不符")
    root = Path(str(evidence.get("root", ""))).resolve(strict=True)
    if receipt_dir.parent != (root / RECEIPT_ROOT).resolve(strict=True):
        raise RawAliasRepairError("raw alias 修復 receipt 路徑不符")
    current = _load_technical_publication(
        root,
        Path(str(evidence["technical_receipt_dir"])),
        check_live=check_technical_publication,
    )
    for name in (
        "technical_source_json_sha256",
        "technical_receipt_sha256",
        "technical_manifest_sha256",
        "source_db",
        "source_sha256",
        "source_db_file_identity",
        "daily_before_hash",
        "technical_after_hash",
        "exclusion_evidence_identities",
        "files",
    ):
        if evidence.get(name) != current.get(name):
            raise RawAliasRepairError(f"raw alias 修復綁定的 run02 證據已變更：{name}")
    return evidence


def _delta_counter() -> dict[str, int]:
    return {
        "rows_checked": 0,
        "changed_values": 0,
        "canonical_null_existing_filled": 0,
        "canonical_value_existing_null": 0,
        "both_filled_different": 0,
    }


def _merge_delta(counter: dict[str, int], delta: Mapping[str, int]) -> None:
    for name, value in delta.items():
        counter[name] += int(value)


def _spool_schema(connection: sqlite3.Connection) -> None:
    canonical_columns = ",\n            ".join(
        f"{_quote(name)} {'INTEGER' if name in INTEGER_ALIASES else 'REAL'}"
        for name in ALIASES
    )
    connection.executescript(
        f"""
        PRAGMA journal_mode=DELETE;
        PRAGMA synchronous=FULL;
        PRAGMA cache_size=-65536;
        PRAGMA temp_store=FILE;
        CREATE TABLE canonical_aliases (
            date_key TEXT NOT NULL,
            symbol_key TEXT NOT NULL,
            source_date,
            source_symbol,
            {canonical_columns},
            PRIMARY KEY(symbol_key, date_key)
        ) WITHOUT ROWID;
        CREATE INDEX canonical_aliases_by_date ON canonical_aliases(date_key, symbol_key);
        CREATE TABLE before_aliases (
            date_key TEXT NOT NULL,
            symbol_key TEXT NOT NULL,
            db_date,
            db_symbol,
            "最後揭示買價",
            "最後揭示買量",
            "最後揭示賣價",
            "最後揭示賣量",
            "本益比",
            "漲跌價差",
            PRIMARY KEY(symbol_key, date_key)
        ) WITHOUT ROWID;
        """
    )


def _source_alias_rows(connection: sqlite3.Connection) -> Iterator[tuple[Any, ...]]:
    columns = _read_table_columns(connection, "daily_prices")
    missing = sorted(set((*KEYS, *ALIASES)) - set(columns))
    if missing:
        raise RawAliasRepairError(f"immutable daily_prices 缺少 raw alias 欄位：{missing}")
    selected = ["證券代號", "日期", *ALIASES]
    return iter(connection.execute(
        "SELECT " + ",".join(_quote(name) for name in selected)
        + " FROM daily_prices ORDER BY CAST(證券代號 AS TEXT), CAST(日期 AS TEXT)"
    ))


def _build_spool(evidence: Mapping[str, Any], spool_path: Path) -> dict[str, Any]:
    root = Path(str(evidence["root"]))
    exclusions = _exclusion_identities(root)
    if exclusions != evidence.get("exclusion_evidence_identities"):
        raise RawAliasRepairError("錯日排除證據在 staging 前已變更")
    from data_module.excluded_daily_price_revision import load_exclusion_evidence

    exclusion_items = load_exclusion_evidence(_database_path(root))
    excluded_keys = {
        (_normalize_date(day), _normalize_symbol(symbol))
        for item in exclusion_items
        for day, symbol in item["keys"]
    }
    closed_dates = {
        _normalize_date(day)
        for item in exclusion_items
        for day in item["closed_dates"]
    }
    with _readonly(Path(str(evidence["source_db"]))) as source:
        if _table_hash(source, "daily_prices") != evidence["daily_before_hash"]:
            raise RawAliasRepairError("immutable source daily_prices hash 不符")
        spool = sqlite3.connect(spool_path)
        try:
            _spool_schema(spool)
            buffer: list[tuple[Any, ...]] = []
            previous: tuple[str, str] | None = None
            canonical_count = 0
            insert = "INSERT INTO canonical_aliases VALUES (?,?,?,?,?,?,?,?,?,?)"
            for raw in _source_alias_rows(source):
                source_symbol, source_date = raw[0], raw[1]
                day, symbol = _date_symbol_key(source_date, source_symbol)
                key = (symbol, day)
                if previous is not None and key <= previous:
                    raise RawAliasRepairError("immutable daily_prices 有重複或排序異常 key")
                previous = key
                if day in closed_dates or (day, symbol) in excluded_keys:
                    raise RawAliasRepairError(f"immutable daily_prices 仍含已排除錯日 key：{day}/{symbol}")
                values = tuple(
                    _numeric_storage_value(value, column)
                    for column, value in zip(ALIASES, raw[2:], strict=True)
                )
                buffer.append((day, symbol, source_date, source_symbol, *values))
                canonical_count += 1
                if len(buffer) >= _CHUNK_ROWS:
                    spool.executemany(insert, buffer)
                    buffer.clear()
            if buffer:
                spool.executemany(insert, buffer)
            spool.commit()
        finally:
            spool.close()
    return {
        "canonical_rows": canonical_count,
        "excluded_exact_keys_checked": len(excluded_keys),
        "excluded_closed_dates_checked": len(closed_dates),
    }


def _source_cursor(connection: sqlite3.Connection, *, order: str) -> sqlite3.Cursor:
    if order == "symbol_date":
        ordering = "symbol_key, date_key"
    elif order == "date_symbol":
        ordering = "date_key, symbol_key"
    else:
        raise ValueError(order)
    columns = ",".join(_quote(name) for name in ALIASES)
    return connection.execute(
        f"SELECT date_key,symbol_key,{columns} FROM canonical_aliases ORDER BY {ordering}"
    )


def _source_record(row: Sequence[Any]) -> tuple[str, str, tuple[Any, ...]]:
    return str(row[0]), str(row[1]), tuple(row[2:])


def _target_summary_from_db(root: Path, spool_path: Path) -> dict[str, Any]:
    fingerprint = _current_fingerprints(root)["technical_indicators"]
    db_columns = fingerprint["columns"]
    alias_indexes = [db_columns.index(name) for name in ALIASES]
    with _readonly(_database_path(root)) as live, _sqlite_connection(spool_path) as spool:
        spool.row_factory = None
        source_cursor = _source_cursor(spool, order="symbol_date")
        source_row = source_cursor.fetchone()
        cursor = live.execute(
            "SELECT 證券代號,日期," + ",".join(_quote(name) for name in ALIASES)
            + " FROM technical_indicators ORDER BY CAST(證券代號 AS TEXT), CAST(日期 AS TEXT)"
        )
        field_deltas = {name: _delta_counter() for name in ALIASES}
        key_hash = hashlib.sha256(_json_bytes(list(KEYS)))
        before_hash = hashlib.sha256(_json_bytes(list(KEYS) + list(ALIASES)))
        before_buffer: list[tuple[Any, ...]] = []
        previous: tuple[str, str] | None = None
        rows_seen = 0
        insert = "INSERT INTO before_aliases VALUES (?,?,?,?,?,?,?,?,?,?)"
        while rows := cursor.fetchmany(_CHUNK_ROWS):
            for raw in rows:
                day, symbol = _date_symbol_key(raw[1], raw[0])
                key = (symbol, day)
                if previous is not None and key <= previous:
                    raise RawAliasRepairError("technical_indicators 有重複或排序異常 key")
                previous = key
                if source_row is None:
                    raise RawAliasRepairError(f"technical_indicators 有 daily source 缺漏 key：{day}/{symbol}")
                canonical_day, canonical_symbol, canonical_values = _source_record(source_row)
                if (canonical_symbol, canonical_day) != key:
                    raise RawAliasRepairError(
                        f"technical_indicators 與 immutable daily source key 集合不同：{day}/{symbol}"
                    )
                current_values = tuple(raw[2:])
                key_hash.update(_json_bytes([[day, symbol]]))
                before_hash.update(_json_bytes([[day, symbol, *current_values]]))
                before_buffer.append((day, symbol, raw[1], raw[0], *current_values))
                for name, current_value, canonical_value in zip(ALIASES, current_values, canonical_values, strict=True):
                    metric = field_deltas[name]
                    metric["rows_checked"] += 1
                    _merge_delta(metric, _value_delta(current_value, canonical_value, name))
                rows_seen += 1
                source_row = source_cursor.fetchone()
                if len(before_buffer) >= _CHUNK_ROWS:
                    spool.executemany(insert, before_buffer)
                    before_buffer.clear()
        if before_buffer:
            spool.executemany(insert, before_buffer)
        if source_row is not None:
            raise RawAliasRepairError("immutable daily source 有 technical_indicators 缺漏 key")
        spool.commit()
    if rows_seen != fingerprint["rows"]:
        raise RawAliasRepairError("technical_indicators row denominator 漂移")
    return {
        "technical_fingerprint": fingerprint,
        "rows_checked": rows_seen,
        "key_sequence_sha256": key_hash.hexdigest(),
        "before_alias_sequence_sha256": before_hash.hexdigest(),
        "field_deltas": field_deltas,
    }


def _csv_numeric_deltas(existing: object, canonical: object, column: str) -> dict[str, int]:
    return _value_delta(existing, canonical, column)


def _csv_value_digests() -> tuple[hashlib._Hash, hashlib._Hash]:
    return hashlib.sha256(), hashlib.sha256()


def _flush_csv_hashes(
    key_hash: Any,
    non_target_hash: Any,
    keys: list[list[str]],
    non_targets: list[list[str]],
) -> None:
    if keys:
        key_hash.update(_json_bytes(keys))
        non_target_hash.update(_json_bytes(non_targets))
        keys.clear()
        non_targets.clear()


def _require_csv_record_width(row: Mapping[Any, Any], target: Path, phase: str) -> None:
    if None in row or any(value is None for value in row.values()):
        raise RawAliasRepairError(f"{phase} CSV 資料列短於標頭：{target}")


def _stage_csv_target(
    *,
    root: Path,
    target: Path,
    staged: Path,
    expected_before_sha: str,
    spool: sqlite3.Connection,
    order: str,
    symbol: str | None,
) -> dict[str, Any]:
    if not target.is_file() or target.is_symlink() or _file_hash(target) != expected_before_sha:
        raise RawAliasRepairError(f"CSV 在 staging 前已變更：{target}")
    staged.parent.mkdir(parents=True, exist_ok=True)
    with target.open("r", encoding=CSV_ENCODING, newline="") as source_stream, staged.open(
        "w", encoding=CSV_ENCODING, newline=""
    ) as output_stream:
        reader = csv.DictReader(source_stream)
        fields = list(reader.fieldnames or [])
        if not fields or len(fields) != len(set(fields)) or any(not item for item in fields):
            raise RawAliasRepairError(f"CSV header 空白或重複：{target}")
        required = set((*KEYS, *ALIASES))
        if not required <= set(fields):
            raise RawAliasRepairError(f"CSV 缺少 raw alias/key 欄位：{target}")
        writer = csv.DictWriter(
            output_stream,
            fieldnames=fields,
            extrasaction="raise",
            lineterminator="\n",
        )
        writer.writeheader()
        if order == "symbol_date":
            query = (
                "SELECT date_key,symbol_key," + ",".join(_quote(name) for name in ALIASES)
                + " FROM canonical_aliases WHERE symbol_key=? ORDER BY date_key"
            )
            source_cursor = spool.execute(query, (symbol,))
        else:
            source_cursor = _source_cursor(spool, order="date_symbol")
        source_row = source_cursor.fetchone()
        prior_key: tuple[str, str] | None = None
        row_count = 0
        field_deltas = {name: _delta_counter() for name in ALIASES}
        non_target_columns = [name for name in fields if name not in ALIASES]
        key_hash = hashlib.sha256(_json_bytes(list(KEYS)))
        non_target_hash = hashlib.sha256(_json_bytes(non_target_columns))
        key_buffer: list[list[str]] = []
        non_target_buffer: list[list[str]] = []
        for raw in reader:
            _require_csv_record_width(raw, target, "stage")
            original: dict[str, str] = {}
            for name in fields:
                value = raw.get(name)
                original[name] = "" if value is None else str(value)
            day, row_symbol = _date_symbol_key(original["日期"], original["證券代號"])
            if symbol is not None and row_symbol != symbol:
                raise RawAliasRepairError(f"個股 CSV 代碼與檔名不符：{target}/{row_symbol}")
            key = (day, row_symbol) if order == "date_symbol" else (row_symbol, day)
            if prior_key is not None and key <= prior_key:
                raise RawAliasRepairError(f"CSV keys 有重複或排序異常：{target}")
            prior_key = key
            if source_row is None:
                raise RawAliasRepairError(f"CSV 有 daily source 缺漏 key：{target}/{day}/{row_symbol}")
            source_day, source_symbol, source_values = _source_record(source_row)
            expected_key = (source_day, source_symbol) if order == "date_symbol" else (source_symbol, source_day)
            if expected_key != key:
                raise RawAliasRepairError(f"CSV 與 immutable daily source key 集合不同：{target}/{day}/{row_symbol}")
            changed = dict(original)
            for name, canonical_value in zip(ALIASES, source_values, strict=True):
                canonical_text = _numeric_text(canonical_value, name)
                _merge_delta(field_deltas[name], _csv_numeric_deltas(original[name], canonical_value, name))
                field_deltas[name]["rows_checked"] += 1
                changed[name] = canonical_text
            if any(original[name] != changed[name] for name in non_target_columns):
                raise RawAliasRepairError(f"CSV stage 改動了非目標欄：{target}")
            key_buffer.append([day, row_symbol])
            non_target_buffer.append([original[name] for name in non_target_columns])
            row_count += 1
            writer.writerow(changed)
            source_row = source_cursor.fetchone()
            if len(key_buffer) >= _CHUNK_ROWS:
                _flush_csv_hashes(key_hash, non_target_hash, key_buffer, non_target_buffer)
        if key_buffer:
            _flush_csv_hashes(key_hash, non_target_hash, key_buffer, non_target_buffer)
        if source_row is not None:
            raise RawAliasRepairError(f"CSV 遺漏 immutable daily source keys：{target}")
        output_stream.flush()
        os.fsync(output_stream.fileno())
    if _file_hash(target) != expected_before_sha:
        raise RawAliasRepairError(f"CSV 在 staging 過程被其他 writer 修改：{target}")
    after_sha = _file_hash(staged)
    if row_count <= 0:
        raise RawAliasRepairError(f"正式技術 CSV 不可為空：{target}")
    per_field = {name: {**field_deltas[name], "rows_checked": row_count} for name in ALIASES}
    return {
        "target_path": str(target),
        "staged_relative_path": staged.relative_to(staged.parents[2]).as_posix(),
        "before_sha256": expected_before_sha,
        "after_sha256": after_sha,
        "rows_checked": row_count,
        "columns": fields,
        "key_sequence_sha256": key_hash.hexdigest(),
        "non_target_columns": non_target_columns,
        "non_target_values_sha256": non_target_hash.hexdigest(),
        "field_deltas": per_field,
        "source_join": "exact_one_to_one",
    }


def stage(receipt_dir: Path) -> dict[str, Any]:
    """由已驗證 run02 日價來源串流產生六欄 staging 與資料庫回復 spool。"""
    evidence = _load_evidence(receipt_dir, check_technical_publication=True)
    receipt_dir = Path(str(evidence["receipt_dir"]))
    output = receipt_dir / "stage"
    if output.exists() or output.is_symlink():
        raise RawAliasRepairError("拒絕覆寫既有 raw alias staging")
    temporary = Path(tempfile.mkdtemp(prefix=".stage-", dir=receipt_dir))
    spool_path = temporary / "alias_spool.sqlite"
    try:
        spool_stats = _build_spool(evidence, spool_path)
        db_comparison = _target_summary_from_db(Path(evidence["root"]), spool_path)
        manifest_files: list[dict[str, Any]] = []
        targets = list(evidence["files"])
        per_stock = [item for item in targets if not str(item["target_path"]).endswith("all_stocks_data.csv")]
        aggregate = [item for item in targets if str(item["target_path"]).endswith("all_stocks_data.csv")]
        if len(aggregate) != 1:
            raise RawAliasRepairError("正式技術 manifest 必須剛好有一個 all_stocks_data.csv")
        symbols = [Path(item["target_path"]).name[: -len("_indicators.csv")] for item in per_stock]
        normalized_symbols = [_normalize_symbol(item) for item in symbols]
        if len(set(normalized_symbols)) != len(normalized_symbols):
            raise RawAliasRepairError("正式技術 manifest 有重複個股 CSV target")
        with _sqlite_connection(spool_path) as spool:
            source_symbols = [str(row[0]) for row in spool.execute(
                "SELECT DISTINCT symbol_key FROM canonical_aliases ORDER BY symbol_key"
            )]
        if sorted(normalized_symbols) != source_symbols:
            raise RawAliasRepairError("正式個股 CSV symbol 範圍與 authoritative daily source 不同")
        for item in sorted(per_stock, key=lambda value: _normalize_symbol(Path(value["target_path"]).name[: -len("_indicators.csv")])):
            target = Path(item["target_path"])
            symbol = _normalize_symbol(target.name[: -len("_indicators.csv")])
            staged = temporary / "staged" / "technical_analysis" / target.name
            with _sqlite_connection(spool_path) as spool:
                record = _stage_csv_target(
                    root=Path(evidence["root"]), target=target, staged=staged,
                    expected_before_sha=str(item["technical_after_sha256"]), spool=spool,
                    order="symbol_date", symbol=symbol,
                )
            manifest_files.append(record)
        aggregate_item = aggregate[0]
        aggregate_target = Path(aggregate_item["target_path"])
        aggregate_staged = temporary / "staged" / "meta_data" / "all_stocks_data.csv"
        with _sqlite_connection(spool_path) as spool:
            aggregate_record = _stage_csv_target(
                root=Path(evidence["root"]), target=aggregate_target, staged=aggregate_staged,
                expected_before_sha=str(aggregate_item["technical_after_sha256"]), spool=spool,
                order="date_symbol", symbol=None,
            )
        manifest_files.append(aggregate_record)
        # 在 manifest 發布前確認兩份 DB spool 均完整且閉合。
        with _sqlite_connection(spool_path) as spool:
            canonical_count = int(spool.execute("SELECT COUNT(*) FROM canonical_aliases").fetchone()[0])
            before_count = int(spool.execute("SELECT COUNT(*) FROM before_aliases").fetchone()[0])
        if canonical_count != db_comparison["rows_checked"] or before_count != canonical_count:
            raise RawAliasRepairError("DB preimage/canonical spool 分母不相等")
        spool_hash = _file_hash(spool_path)
        final_files = []
        for item in manifest_files:
            final_files.append({
                **item,
                "staged_path": str(output / item["staged_relative_path"]),
            })
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "stage_schema_version": "formal-technical-raw-alias-stage.v1",
            "state": "staged",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "root": evidence["root"],
            "technical_receipt_sha256": evidence["technical_receipt_sha256"],
            "technical_manifest_sha256": evidence["technical_manifest_sha256"],
            "source_db": evidence["source_db"],
            "source_sha256": evidence["source_sha256"],
            "source_db_file_identity": evidence["source_db_file_identity"],
            "technical_receipt_dir": evidence["technical_receipt_dir"],
            "source_daily_prices_sha256": evidence["daily_before_hash"],
            "source_exclusion_evidence_identities": evidence["exclusion_evidence_identities"],
            "raw_alias_columns": list(ALIASES),
            "canonical_spool_path": str(output / "alias_spool.sqlite"),
            "canonical_spool_sha256": spool_hash,
            "canonical_rows": canonical_count,
            "database_before": db_comparison["technical_fingerprint"],
            "database_rows_checked": db_comparison["rows_checked"],
            "database_key_sequence_sha256": db_comparison["key_sequence_sha256"],
            "database_before_alias_sequence_sha256": db_comparison["before_alias_sequence_sha256"],
            "database_field_deltas": db_comparison["field_deltas"],
            "csv_rows_checked": sum(int(item["rows_checked"]) for item in final_files),
            "per_stock_target_count": len(per_stock),
            "aggregate_target_count": 1,
            "target_file_count": len(final_files),
            "csv_targets": final_files,
            "source_spool_checks": spool_stats,
            "preservation_contract": {
                "key_set_and_order": "exact_one_to_one_and_monotonic",
                "non_target_columns": "all source CSV values preserved row-by-row",
                "database_schema": "unchanged",
                "database_keys": "unchanged",
                "database_non_target_values": "unchanged",
                "nulls": "SQLite NULL is emitted as an empty CSV cell; no forward/back fill or zero fill",
            },
            "historical_pit": False,
            "formal_data_written": False,
        }
        _write_sealed(temporary / "manifest.json", manifest)
        if output.exists():
            raise RawAliasRepairError("raw alias stage 目錄已存在")
        os.replace(temporary, output)
        return _read_sealed(output / "manifest.json")
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def _stream_spool_vs_source(evidence: Mapping[str, Any], spool_path: Path) -> dict[str, Any]:
    with _readonly(Path(str(evidence["source_db"]))) as source, _sqlite_connection(spool_path) as spool:
        if _table_hash(source, "daily_prices") != evidence["daily_before_hash"]:
            raise RawAliasRepairError("audit 時 immutable daily source hash 漂移")
        source_rows = _source_alias_rows(source)
        spool_rows = _source_cursor(spool, order="symbol_date")
        checked = 0
        previous: tuple[str, str] | None = None
        for raw in source_rows:
            symbol, raw_day, *values = raw
            day, normalized_symbol = _date_symbol_key(raw_day, symbol)
            key = (normalized_symbol, day)
            if previous is not None and key <= previous:
                raise RawAliasRepairError("audit source daily key 重複或排序異常")
            previous = key
            staged = spool_rows.fetchone()
            if staged is None or (staged[1], staged[0]) != key:
                raise RawAliasRepairError(f"audit spool/source key 不同：{day}/{normalized_symbol}")
            if any(
                not _same_numeric(source_value, staged_value, name)
                for name, source_value, staged_value in zip(ALIASES, values, staged[2:], strict=True)
            ):
                raise RawAliasRepairError(f"audit spool/source alias values 不同：{day}/{normalized_symbol}")
            checked += 1
        if spool_rows.fetchone() is not None:
            raise RawAliasRepairError("audit spool 多出 immutable source key")
        return {"rows_checked": checked, "source_alias_values_exact": True}


def _audit_csv_target(
    *,
    target: Path,
    staged: Path,
    expected_before_sha: str,
    expected_after_sha: str,
    spool_path: Path,
    order: str,
    symbol: str | None,
) -> dict[str, Any]:
    if _file_hash(target) != expected_before_sha or _file_hash(staged) != expected_after_sha:
        raise RawAliasRepairError(f"audit CSV before/after hash 不符：{target}")
    with target.open("r", encoding=CSV_ENCODING, newline="") as old_stream, staged.open(
        "r", encoding=CSV_ENCODING, newline=""
    ) as new_stream, _sqlite_connection(spool_path) as spool:
        old_reader = csv.DictReader(old_stream)
        new_reader = csv.DictReader(new_stream)
        old_fields = list(old_reader.fieldnames or [])
        new_fields = list(new_reader.fieldnames or [])
        if old_fields != new_fields or not set((*KEYS, *ALIASES)) <= set(old_fields):
            raise RawAliasRepairError(f"audit CSV schema/header 改變：{target}")
        if order == "symbol_date":
            if symbol is None:
                raise RawAliasRepairError("個股 CSV audit 缺少 symbol")
            source_cursor = spool.execute(
                "SELECT date_key,symbol_key," + ",".join(_quote(name) for name in ALIASES)
                + " FROM canonical_aliases WHERE symbol_key=? ORDER BY date_key", (symbol,)
            )
        else:
            source_cursor = _source_cursor(spool, order="date_symbol")
        source_row = source_cursor.fetchone()
        non_target_columns = [name for name in old_fields if name not in ALIASES]
        field_deltas = {name: _delta_counter() for name in ALIASES}
        key_digest = hashlib.sha256(_json_bytes(old_fields[:0] + list(KEYS)))
        non_target_digest = hashlib.sha256(_json_bytes(non_target_columns))
        batch_keys: list[list[str]] = []
        batch_non_targets: list[list[str]] = []
        rows_checked = 0
        previous: tuple[str, str] | None = None
        while True:
            old = next(old_reader, None)
            new = next(new_reader, None)
            if old is None or new is None:
                if old is not None or new is not None:
                    raise RawAliasRepairError(f"audit CSV row count changed：{target}")
                break
            if None in old or None in new:
                raise RawAliasRepairError(f"audit CSV has a row/header width mismatch：{target}")
            _require_csv_record_width(old, target, "audit")
            _require_csv_record_width(new, target, "audit")
            old_values: dict[str, str] = {}
            new_values: dict[str, str] = {}
            for name in old_fields:
                value = old.get(name)
                old_values[name] = "" if value is None else str(value)
            for name in new_fields:
                value = new.get(name)
                new_values[name] = "" if value is None else str(value)
            day, row_symbol = _date_symbol_key(old_values["日期"], old_values["證券代號"])
            new_key = _date_symbol_key(new_values["日期"], new_values["證券代號"])
            key = (day, row_symbol) if order == "date_symbol" else (row_symbol, day)
            if key != ((new_key[0], new_key[1]) if order == "date_symbol" else (new_key[1], new_key[0])):
                raise RawAliasRepairError(f"audit CSV key/order changed：{target}")
            if previous is not None and key <= previous:
                raise RawAliasRepairError(f"audit CSV keys duplicate or unsorted：{target}")
            previous = key
            if symbol is not None and row_symbol != symbol:
                raise RawAliasRepairError(f"audit stock CSV symbol mismatch：{target}")
            if source_row is None:
                raise RawAliasRepairError(f"audit CSV has key absent from source：{target}/{day}/{row_symbol}")
            source_day, source_symbol, source_values = _source_record(source_row)
            expected_key = (source_day, source_symbol) if order == "date_symbol" else (source_symbol, source_day)
            if expected_key != key:
                raise RawAliasRepairError(f"audit CSV/source key mismatch：{target}/{day}/{row_symbol}")
            if any(old_values[name] != new_values[name] for name in non_target_columns):
                raise RawAliasRepairError(f"audit detected non-target CSV value change：{target}")
            for name, old_value, new_value, canonical in zip(ALIASES, (old_values[item] for item in ALIASES), (new_values[item] for item in ALIASES), source_values, strict=True):
                if not _same_numeric(new_value, canonical, name):
                    raise RawAliasRepairError(f"audit staged alias differs from canonical daily source：{target}/{day}/{row_symbol}/{name}")
                if _numeric_text(canonical, name) != new_value:
                    raise RawAliasRepairError(f"audit staged alias representation is not canonical：{target}/{day}/{row_symbol}/{name}")
                field_deltas[name]["rows_checked"] += 1
                _merge_delta(field_deltas[name], _csv_numeric_deltas(old_value, canonical, name))
            batch_keys.append([day, row_symbol])
            batch_non_targets.append([old_values[name] for name in non_target_columns])
            rows_checked += 1
            source_row = source_cursor.fetchone()
            if len(batch_keys) >= _CHUNK_ROWS:
                _flush_csv_hashes(key_digest, non_target_digest, batch_keys, batch_non_targets)
        if batch_keys:
            _flush_csv_hashes(key_digest, non_target_digest, batch_keys, batch_non_targets)
        if source_row is not None:
            raise RawAliasRepairError(f"audit CSV omitted canonical daily source keys：{target}")
    if rows_checked <= 0:
        raise RawAliasRepairError(f"audit CSV has no rows：{target}")
    return {
        "target_path": str(target),
        "before_sha256": expected_before_sha,
        "after_sha256": expected_after_sha,
        "rows_checked": rows_checked,
        "key_sequence_sha256": key_digest.hexdigest(),
        "non_target_columns": non_target_columns,
        "non_target_values_sha256": non_target_digest.hexdigest(),
        "non_target_values_equal": True,
        "field_deltas": field_deltas,
        "canonical_alias_mismatches": 0,
    }


def audit(receipt_dir: Path, expected_manifest_hash: str | None = None) -> dict[str, Any]:
    """全量重讀 spool/CSV，記錄每列、每欄與未修改內容的完整驗證分母。"""
    evidence = _load_evidence(receipt_dir, check_technical_publication=True)
    receipt_dir = Path(str(evidence["receipt_dir"]))
    stage_dir = receipt_dir / "stage"
    manifest_path = stage_dir / "manifest.json"
    manifest_hash = _file_hash(manifest_path)
    if expected_manifest_hash and expected_manifest_hash.removeprefix("sha256:") != manifest_hash:
        raise RawAliasRepairError("raw alias stage manifest hash 不符")
    manifest = _read_sealed(manifest_path)
    if manifest.get("schema_version") != SCHEMA_VERSION or manifest.get("state") != "staged":
        raise RawAliasRepairError("raw alias stage manifest 狀態/版型不符")
    if manifest.get("technical_receipt_sha256") != evidence["technical_receipt_sha256"]:
        raise RawAliasRepairError("raw alias stage 與正式技術 receipt 不同")
    _validate_stage_inventory(evidence, manifest, stage_dir)
    spool_path = stage_dir / "alias_spool.sqlite"
    if _file_hash(spool_path) != manifest.get("canonical_spool_sha256"):
        raise RawAliasRepairError("raw alias canonical/preimage spool hash 不符")
    source_audit = _stream_spool_vs_source(evidence, spool_path)
    canonical_rows = int(manifest.get("canonical_rows", -1))
    database_rows = int(manifest.get("database_rows_checked", -1))
    if source_audit["rows_checked"] != canonical_rows or database_rows != canonical_rows:
        raise RawAliasRepairError("source/DB canonical row 分母與 stage manifest 不符")
    current = _current_fingerprints(Path(evidence["root"]))
    before = manifest.get("database_before")
    if current["daily_prices"]["table_sha256"] != evidence["daily_before_hash"]:
        raise RawAliasRepairError("audit 時正式 daily_prices 已變更")
    if current["technical_indicators"] != before:
        raise RawAliasRepairError("audit 時 technical_indicators schema/key/non-target/alias 尚未維持 staging before 狀態")
    csv_results = []
    for item in manifest.get("csv_targets", []):
        if not isinstance(item, dict):
            raise RawAliasRepairError("raw alias manifest CSV entry 格式不符")
        target = Path(str(item["target_path"]))
        staged = stage_dir / str(item["staged_relative_path"])
        symbol = None if target.name == "all_stocks_data.csv" else _normalize_symbol(target.name[: -len("_indicators.csv")])
        result = _audit_csv_target(
            target=target,
            staged=staged,
            expected_before_sha=str(item["before_sha256"]),
            expected_after_sha=str(item["after_sha256"]),
            spool_path=spool_path,
            order="date_symbol" if symbol is None else "symbol_date",
            symbol=symbol,
        )
        for field in ("rows_checked", "key_sequence_sha256", "non_target_values_sha256", "field_deltas"):
            if result[field] != item[field]:
                raise RawAliasRepairError(f"audit 與 stage manifest 的全量證據不同：{target}/{field}")
        csv_results.append(result)
    target_rows = sum(int(item["rows_checked"]) for item in csv_results)
    if len(csv_results) != manifest.get("target_file_count") or target_rows != manifest.get("csv_rows_checked"):
        raise RawAliasRepairError("audit target file/row denominator 與 stage manifest 不符")
    audit_payload = {
        "schema_version": "formal-technical-raw-alias-audit.v1",
        "state": "passed",
        "audited_at": datetime.now(timezone.utc).isoformat(),
        "manifest_sha256": manifest_hash,
        "canonical_spool_sha256": manifest["canonical_spool_sha256"],
        "source_daily_rows_checked": source_audit["rows_checked"],
        "source_alias_values_exact": source_audit["source_alias_values_exact"],
        "database_rows_checked": manifest["database_rows_checked"],
        "database_before_fingerprint_sha256": hashlib.sha256(_json_bytes(before)).hexdigest(),
        "csv_rows_checked": target_rows,
        "target_file_count": len(csv_results),
        "csv_targets": csv_results,
        "all_target_keys_and_order_preserved": all(
            item["key_sequence_sha256"] for item in csv_results
        ) and all(
            result["key_sequence_sha256"] == planned["key_sequence_sha256"]
            for result, planned in zip(csv_results, manifest["csv_targets"], strict=True)
        ),
        "all_non_target_csv_values_preserved": all(item["non_target_values_equal"] for item in csv_results),
        "all_staged_aliases_equal_authoritative_daily": all(item["canonical_alias_mismatches"] == 0 for item in csv_results),
        "all_database_schema_keys_and_non_target_values_preserved": True,
        "formal_data_written": False,
    }
    if not all(audit_payload[name] for name in (
        "source_alias_values_exact",
        "all_target_keys_and_order_preserved",
        "all_non_target_csv_values_preserved",
        "all_staged_aliases_equal_authoritative_daily",
        "all_database_schema_keys_and_non_target_values_preserved",
    )):
        raise RawAliasRepairError("全量 raw alias audit 未通過")
    _write_sealed(receipt_dir / "audit.json", audit_payload)
    return audit_payload


def _load_stage(receipt_dir: Path, expected_manifest_hash: str | None = None) -> tuple[dict[str, Any], dict[str, Any], Path, str]:
    evidence = _load_evidence(receipt_dir, check_technical_publication=False)
    receipt_dir = Path(str(evidence["receipt_dir"]))
    stage_dir = receipt_dir / "stage"
    manifest_path = stage_dir / "manifest.json"
    manifest_hash = _file_hash(manifest_path)
    if expected_manifest_hash and expected_manifest_hash.removeprefix("sha256:") != manifest_hash:
        raise RawAliasRepairError("raw alias manifest hash 不符")
    manifest = _read_sealed(manifest_path)
    if (
        manifest.get("schema_version") != SCHEMA_VERSION
        or manifest.get("stage_schema_version") != "formal-technical-raw-alias-stage.v1"
        or manifest.get("state") != "staged"
    ):
        raise RawAliasRepairError("raw alias stage manifest 狀態/版型不符")
    spool_path = stage_dir / "alias_spool.sqlite"
    if _file_hash(spool_path) != manifest.get("canonical_spool_sha256"):
        raise RawAliasRepairError("raw alias spool hash 不符")
    if manifest.get("source_sha256") != evidence.get("source_sha256"):
        raise RawAliasRepairError("raw alias staging source 身分不符")
    expected_source_identity = {
        "source_db_file_identity": evidence.get("source_db_file_identity"),
        "technical_receipt_sha256": evidence.get("technical_receipt_sha256"),
        "technical_manifest_sha256": evidence.get("technical_manifest_sha256"),
        "source_daily_prices_sha256": evidence.get("daily_before_hash"),
    }
    if any(manifest.get(name) != value for name, value in expected_source_identity.items()):
        raise RawAliasRepairError("raw alias staging source 身分與 prepared receipt 不符")
    _validate_stage_inventory(evidence, manifest, stage_dir)
    return evidence, manifest, spool_path, manifest_hash


def _validate_stage_inventory(
    evidence: Mapping[str, Any], manifest: Mapping[str, Any], stage_dir: Path,
) -> None:
    """Bind every staged CSV to the exact run02 publication target inventory."""
    root = Path(str(evidence["root"])).resolve(strict=True)
    evidence_files = evidence.get("files")
    planned_files = manifest.get("csv_targets")
    if (
        not isinstance(evidence_files, list)
        or not isinstance(planned_files, list)
        or not evidence_files
        or len(planned_files) != len(evidence_files)
    ):
        raise RawAliasRepairError("raw alias target inventory 與正式技術 receipt 筆數不同")
    if manifest.get("raw_alias_columns") != list(ALIASES):
        raise RawAliasRepairError("raw alias stage 目標欄位集合／順序不符")

    expected_by_target: dict[Path, Mapping[str, Any]] = {}
    for item in evidence_files:
        if not isinstance(item, Mapping):
            raise RawAliasRepairError("正式技術 applied target inventory 格式不符")
        target = _safe_target(root, item.get("target_path"))
        if target in expected_by_target:
            raise RawAliasRepairError("正式技術 applied target inventory 有重複路徑")
        if not _HASH_RE.fullmatch(str(item.get("technical_after_sha256", ""))):
            raise RawAliasRepairError(f"正式技術 applied target 缺少 after hash：{target}")
        if type(item.get("technical_row_count")) is not int or int(item["technical_row_count"]) <= 0:
            raise RawAliasRepairError(f"正式技術 applied target 列數無效：{target}")
        expected_by_target[target] = item

    actual_targets: set[Path] = set()
    actual_staged: set[Path] = set()
    aggregate = (root / "meta_data" / "all_stocks_data.csv").resolve(strict=True)
    per_stock_count = 0
    aggregate_count = 0
    checked_csv_rows = 0
    for item in planned_files:
        if not isinstance(item, Mapping):
            raise RawAliasRepairError("raw alias manifest target entry 格式不符")
        target = _safe_target(root, item.get("target_path"))
        if str(item.get("target_path")) != str(target):
            raise RawAliasRepairError(f"raw alias manifest target path 非 canonical：{item.get('target_path')}")
        if target in actual_targets:
            raise RawAliasRepairError(f"raw alias manifest target 重複：{target}")
        actual_targets.add(target)
        authority = expected_by_target.get(target)
        if authority is None:
            raise RawAliasRepairError(f"raw alias manifest target 不在 run02 applied inventory：{target}")
        if item.get("before_sha256") != authority.get("technical_after_sha256"):
            raise RawAliasRepairError(f"raw alias target preimage hash 不等於 run02 applied CSV：{target}")
        if type(item.get("rows_checked")) is not int or int(item["rows_checked"]) != int(authority["technical_row_count"]):
            raise RawAliasRepairError(f"raw alias target row count 不等於 run02 applied CSV：{target}")
        after_sha = str(item.get("after_sha256", ""))
        if not _HASH_RE.fullmatch(after_sha):
            raise RawAliasRepairError(f"raw alias manifest target 缺少 after hash：{target}")

        if target == aggregate:
            expected_relative = PurePosixPath("staged/meta_data/all_stocks_data.csv")
            aggregate_count += 1
        else:
            expected_relative = PurePosixPath("staged/technical_analysis") / target.name
            per_stock_count += 1
        relative_value = item.get("staged_relative_path")
        if not isinstance(relative_value, str) or relative_value != expected_relative.as_posix():
            raise RawAliasRepairError(f"raw alias staged path 不符合受控目錄：{relative_value!r}")
        staged = _resolve_within(stage_dir, str(stage_dir / Path(*expected_relative.parts)))
        if staged in actual_staged:
            raise RawAliasRepairError(f"raw alias manifest staged path 重複：{staged}")
        actual_staged.add(staged)
        if not staged.is_file() or _file_hash(staged) != after_sha:
            raise RawAliasRepairError(f"raw alias staged CSV hash 不符：{staged}")
        checked_csv_rows += int(item["rows_checked"])

    if actual_targets != set(expected_by_target):
        raise RawAliasRepairError("raw alias manifest 漏列或新增 run02 target")
    if aggregate_count != 1 or per_stock_count != len(expected_by_target) - 1:
        raise RawAliasRepairError("raw alias manifest aggregate／個股 target 數不符")
    if (
        manifest.get("target_file_count") != len(expected_by_target)
        or manifest.get("per_stock_target_count") != per_stock_count
        or manifest.get("aggregate_target_count") != 1
        or manifest.get("csv_rows_checked") != checked_csv_rows
        or type(manifest.get("canonical_rows")) is not int
        or int(manifest["canonical_rows"]) != int(evidence.get("technical_rows", -1))
        or manifest.get("database_rows_checked") != manifest.get("canonical_rows")
    ):
        raise RawAliasRepairError("raw alias manifest 的 target／row denominator 不符正式技術 receipt")


def _copy_atomic(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "wb") as output, source.open("rb") as input_stream:
            shutil.copyfileobj(input_stream, output, length=1024 * 1024)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def _ensure_backups(receipt_dir: Path, manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    backup_dir = receipt_dir / "csv_before"
    result = []
    for index, item in enumerate(manifest["csv_targets"]):
        target = Path(str(item["target_path"]))
        backup = backup_dir / f"{index:05d}.csv"
        expected = str(item["before_sha256"])
        if backup.exists():
            if _file_hash(backup) != expected:
                raise RawAliasRepairError(f"CSV 備份 hash 不符：{backup}")
        else:
            if not target.is_file() or _file_hash(target) != expected:
                raise RawAliasRepairError(f"apply 前 CSV 已漂移：{target}")
            _copy_atomic(target, backup)
            if _file_hash(backup) != expected:
                raise RawAliasRepairError(f"CSV 備份讀回 hash 不符：{backup}")
        result.append({
            "target_path": str(target),
            "before_sha256": expected,
            "after_sha256": str(item["after_sha256"]),
            "backup_relative_path": backup.relative_to(receipt_dir).as_posix(),
            "staged_relative_path": str(item["staged_relative_path"]),
        })
    return result


def _write_db_values(connection: sqlite3.Connection, spool_path: Path, *, after: bool) -> int:
    source_table = "canonical_aliases" if after else "before_aliases"
    if after:
        select = (
            "SELECT c.date_key,c.symbol_key,b.db_date,b.db_symbol," + ",".join(f"c.{_quote(name)}" for name in ALIASES)
            + " FROM canonical_aliases c JOIN before_aliases b USING(date_key,symbol_key) ORDER BY c.symbol_key,c.date_key"
        )
    else:
        select = (
            "SELECT date_key,symbol_key,db_date,db_symbol," + ",".join(_quote(name) for name in ALIASES)
            + " FROM before_aliases ORDER BY symbol_key,date_key"
        )
    update = (
        "UPDATE technical_indicators SET "
        + ",".join(f"{_quote(name)}=?" for name in ALIASES)
        + " WHERE 證券代號=? AND 日期=?"
    )
    count = 0
    with _sqlite_connection(spool_path) as spool:
        cursor = spool.execute(select)
        while rows := cursor.fetchmany(_CHUNK_ROWS):
            parameters = [(*row[4:], row[3], row[2]) for row in rows]
            connection.executemany(update, parameters)
            count += len(rows)
    return count


def _publish_csvs(receipt_dir: Path, manifest: Mapping[str, Any], journal: Mapping[str, Any], *, after: bool) -> None:
    entries = journal.get("files")
    if not isinstance(entries, list) or len(entries) != len(manifest["csv_targets"]):
        raise RawAliasRepairError("journal CSV target 清冊不完整")
    for index, (entry, planned) in enumerate(zip(entries, manifest["csv_targets"], strict=True)):
        if entry.get("target_path") != planned.get("target_path") or entry.get("before_sha256") != planned.get("before_sha256") or entry.get("after_sha256") != planned.get("after_sha256"):
            raise RawAliasRepairError("journal/manifest CSV target 身分不同")
        target = Path(str(entry["target_path"]))
        before_sha, after_sha = str(entry["before_sha256"]), str(entry["after_sha256"])
        current_sha = _file_hash(target) if target.is_file() else None
        desired = after_sha if after else before_sha
        if current_sha not in (before_sha, after_sha):
            raise RawAliasRepairError(f"CSV 在發布/回復中被其他 writer 改動：{target}")
        if current_sha == desired:
            continue
        if after:
            source = receipt_dir / "stage" / str(entry["staged_relative_path"])
        else:
            source = receipt_dir / str(entry["backup_relative_path"])
        if not source.is_file() or _file_hash(source) != desired:
            raise RawAliasRepairError(f"CSV 發布/回復來源 hash 不符：{source}")
        _copy_atomic(source, target)


def _preflight_csv_publication(
    receipt_dir: Path,
    manifest: Mapping[str, Any],
    journal: Mapping[str, Any],
    *,
    after: bool,
) -> None:
    """在 DB 或 CSV 寫入前，完整確認每個目標及來源檔都可安全發布。"""

    entries = journal.get("files")
    targets = manifest.get("csv_targets")
    if not isinstance(entries, list) or not isinstance(targets, list) or len(entries) != len(targets):
        raise RawAliasRepairError("journal CSV target 清冊不完整")
    for entry, planned in zip(entries, targets, strict=True):
        if (
            entry.get("target_path") != planned.get("target_path")
            or entry.get("before_sha256") != planned.get("before_sha256")
            or entry.get("after_sha256") != planned.get("after_sha256")
        ):
            raise RawAliasRepairError("journal/manifest CSV target 身分不同")
        target = Path(str(entry["target_path"]))
        if target.is_symlink() or not target.is_file():
            raise RawAliasRepairError(f"CSV 在 recovery 前不存在或為符號連結：{target}")
        current_sha = _file_hash(target)
        if current_sha not in (entry["before_sha256"], entry["after_sha256"]):
            raise RawAliasRepairError(f"CSV 在 recovery 前已漂移：{target}")
        backup_path = receipt_dir / str(entry.get("backup_relative_path", ""))
        backup = _resolve_within(receipt_dir, str(backup_path))
        if not backup.is_file() or _file_hash(backup) != entry["before_sha256"]:
            raise RawAliasRepairError(f"CSV rollback backup hash 不符：{backup}")
        if after:
            source_path = receipt_dir / "stage" / str(entry.get("staged_relative_path", ""))
            source = _resolve_within(receipt_dir / "stage", str(source_path))
            expected = str(entry["after_sha256"])
        else:
            source_path = receipt_dir / str(entry.get("backup_relative_path", ""))
            source = _resolve_within(receipt_dir, str(source_path))
            expected = str(entry["before_sha256"])
        if not source.is_file() or _file_hash(source) != expected:
            raise RawAliasRepairError(f"CSV 發布/回復來源 hash 不符：{source}")


def _acquire_lock(root: Path):
    lock_path = root / "output" / "release_v4" / ".ml_heavy_chain.lock"
    lock = acquire_heavy_chain_reservation(lock_path)
    if lock is None:
        raise RawAliasRepairError("正式資料維護鎖忙碌")
    return lock


def _check_current_before(evidence: Mapping[str, Any], manifest: Mapping[str, Any]) -> None:
    root = Path(str(evidence["root"]))
    current = _current_fingerprints(root)
    if current["daily_prices"]["table_sha256"] != evidence["daily_before_hash"]:
        raise RawAliasRepairError("正式 daily_prices 在 raw alias stage 後已變更")
    if current["technical_indicators"] != manifest["database_before"]:
        raise RawAliasRepairError("正式 technical_indicators 在 raw alias stage 後已變更")
    for item in manifest["csv_targets"]:
        target = Path(str(item["target_path"]))
        if not target.is_file() or _file_hash(target) != item["before_sha256"]:
            raise RawAliasRepairError(f"正式 CSV 在 raw alias stage 後已變更：{target}")


def _apply_database(
    evidence: Mapping[str, Any],
    manifest: Mapping[str, Any],
    spool_path: Path,
    *,
    before_commit: Callable[[dict[str, Any], int], None] | None = None,
) -> dict[str, Any]:
    root = Path(str(evidence["root"]))
    db_path = _database_path(root)
    with _sqlite_connection(db_path, timeout=60) as connection:
        connection.execute("PRAGMA busy_timeout=60000")
        connection.execute("BEGIN IMMEDIATE")
        daily_hash = _table_hash(connection, "daily_prices")
        current = _table_fingerprint(connection, "technical_indicators")
        if daily_hash != evidence["daily_before_hash"] or current != manifest["database_before"]:
            raise RawAliasRepairError("正式 DB 在 BEGIN IMMEDIATE 後與 audit before fingerprint 不同")
        columns = _read_table_columns(connection, "technical_indicators")
        if not set((*KEYS, *ALIASES)) <= set(columns):
            raise RawAliasRepairError("正式 technical schema 缺少受保護欄位；拒絕 ALTER/DROP")
        updated = _write_db_values(connection, spool_path, after=True)
        if updated != manifest["canonical_rows"]:
            raise RawAliasRepairError("DB batch update row count 不符 canonical source")
        after = _table_fingerprint(connection, "technical_indicators")
        if (
            after["schema_sha256"] != current["schema_sha256"]
            or after["rows"] != current["rows"]
            or after["keys_sha256"] != current["keys_sha256"]
            or after["non_target_values_sha256"] != current["non_target_values_sha256"]
        ):
            raise RawAliasRepairError("DB apply 改變 schema/key/非目標值")
        expected_alias_digest = _spool_alias_digest(spool_path)
        if after["aliases_sha256"] != expected_alias_digest:
            raise RawAliasRepairError("DB 六欄讀回不等於 authoritative daily source")
        if before_commit is not None:
            before_commit(after, updated)
        connection.commit()
    return {"updated_rows": updated, "technical_after": after}


def _spool_alias_digest(spool_path: Path) -> str:
    digest = hashlib.sha256(_json_bytes(list(KEYS) + list(ALIASES)))
    with _sqlite_connection(spool_path) as spool:
        cursor = spool.execute(
            "SELECT date_key,symbol_key," + ",".join(_quote(name) for name in ALIASES)
            + " FROM canonical_aliases ORDER BY symbol_key,date_key"
        )
        while rows := cursor.fetchmany(_TABLE_HASH_CHUNK_ROWS):
            digest.update(_json_bytes(rows))
    return digest.hexdigest()


def _apply(
    receipt_dir: Path,
    *,
    expected_manifest_hash: str,
    recovering: bool = False,
) -> dict[str, Any]:
    evidence, manifest, spool_path, manifest_hash = _load_stage(receipt_dir, expected_manifest_hash)
    receipt_dir = Path(str(evidence["receipt_dir"]))
    audit_path = receipt_dir / "audit.json"
    audit_record = _read_sealed(audit_path)
    audit_hash = _file_hash(audit_path)
    if audit_record.get("state") != "passed" or audit_record.get("manifest_sha256") != manifest_hash:
        raise RawAliasRepairError("apply 必須使用同一 manifest 的完整全量 audit")
    journal_path = receipt_dir / "journal.json"
    if journal_path.exists() and not recovering:
        raise RawAliasRepairError("已有 journal，請使用 resume／rollback")
    root = Path(str(evidence["root"]))
    lock = _acquire_lock(root)
    try:
        _check_current_before(evidence, manifest)
        if not recovering:
            files = _ensure_backups(receipt_dir, manifest)
            journal = {
                "schema_version": "formal-technical-raw-alias-journal.v1",
                "state": "pending",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "root": str(root),
                "manifest_sha256": manifest_hash,
                "audit_sha256": audit_hash,
                "source_sha256": evidence["source_sha256"],
                "source_db": evidence["source_db"],
                "source_db_file_identity": evidence["source_db_file_identity"],
                "technical_receipt_dir": evidence["technical_receipt_dir"],
                "source_technical_receipt_sha256": evidence["technical_receipt_sha256"],
                "source_technical_manifest_sha256": evidence["technical_manifest_sha256"],
                "source_daily_prices_sha256": evidence["daily_before_hash"],
                "daily_before_hash": evidence["daily_before_hash"],
                "technical_before_hash": manifest["database_before"]["table_sha256"],
                "database_before": manifest["database_before"],
                "files": files,
            }
            _write_sealed(journal_path, journal)
            _preflight_csv_publication(receipt_dir, manifest, journal, after=True)
        else:
            journal = _read_sealed(journal_path)
            if journal.get("state") != "pending" or journal.get("manifest_sha256") != manifest_hash or journal.get("audit_sha256") != audit_hash:
                raise RawAliasRepairError("resume journal identity/state 不符")
            _ensure_backups(receipt_dir, manifest)
        def record_before_commit(after: dict[str, Any], updated: int) -> None:
            journal.update({
                "database_after": after,
                "technical_after_alias_repair_hash": after["table_sha256"],
                "database_updated_rows": updated,
                "database_verified_schema_keys_non_target": True,
                "database_verified_alias_values": True,
                "db_commit_pending_at": datetime.now(timezone.utc).isoformat(),
            })
            _write_sealed(journal_path, journal)

        database_result = _apply_database(
            evidence, manifest, spool_path, before_commit=record_before_commit
        )
        journal["db_committed_at"] = datetime.now(timezone.utc).isoformat()
        _write_sealed(journal_path, journal)
        _publish_csvs(receipt_dir, manifest, journal, after=True)
        for item in journal["files"]:
            if _file_hash(Path(item["target_path"])) != item["after_sha256"]:
                raise RawAliasRepairError(f"CSV after publish hash 不符：{item['target_path']}")
        applied = {
            **journal,
            "state": "applied",
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "source_technical_receipt_sha256": evidence["technical_receipt_sha256"],
            "source_technical_manifest_sha256": evidence["technical_manifest_sha256"],
            "canonical_spool_sha256": manifest["canonical_spool_sha256"],
            "canonical_rows": manifest["canonical_rows"],
            "database_field_deltas": manifest["database_field_deltas"],
            "csv_field_deltas": {item["target_path"]: item["field_deltas"] for item in manifest["csv_targets"]},
            "preservation_verified": {
                "database_schema": True,
                "database_keys": True,
                "database_non_target_values": True,
                "csv_keys_and_order": True,
                "csv_non_target_values": True,
            },
            "rollback_preimage_sha256": _file_hash(spool_path),
            "rollback_preimage_rows": int(manifest["canonical_rows"]),
            "rollback_csv_backups_verified": all(
                _file_hash(receipt_dir / str(entry["backup_relative_path"])) == entry["before_sha256"]
                for entry in journal["files"]
            ),
            "formal_data_written": True,
            "historical_pit": False,
        }
        receipt_sha = _write_sealed(receipt_dir / "receipt.json", applied)
        _write_sealed(journal_path, {**applied, "receipt_sha256": receipt_sha})
        return {
            "state": "applied",
            "receipt_dir": str(receipt_dir),
            "receipt_sha256": receipt_sha,
            "database_rows": database_result["updated_rows"],
            "csv_targets": len(journal["files"]),
            "technical_after_hash": database_result["technical_after"]["table_sha256"],
        }
    finally:
        release_heavy_chain_reservation(lock)


def apply(receipt_dir: Path, expected_manifest_hash: str) -> dict[str, Any]:
    """在完整 audit、hash 重驗與 writer lock 下發布 SQLite 六欄及 CSV。"""
    return _apply(receipt_dir, expected_manifest_hash=expected_manifest_hash)


def _restore_database(evidence: Mapping[str, Any], journal: Mapping[str, Any], spool_path: Path) -> dict[str, Any]:
    root = Path(str(evidence["root"]))
    with _sqlite_connection(_database_path(root), timeout=60) as connection:
        connection.execute("PRAGMA busy_timeout=60000")
        connection.execute("BEGIN IMMEDIATE")
        current = _table_fingerprint(connection, "technical_indicators")
        expected_after = journal.get("database_after")
        expected_before = journal.get("database_before")
        if current != expected_after:
            raise RawAliasRepairError("rollback 前正式技指不是 journal after fingerprint")
        restored = _write_db_values(connection, spool_path, after=False)
        if restored != journal.get("database_updated_rows"):
            raise RawAliasRepairError("rollback DB preimage row count 不符")
        after = _table_fingerprint(connection, "technical_indicators")
        if after != expected_before:
            raise RawAliasRepairError("rollback DB 讀回與完整 before fingerprint 不同")
        connection.commit()
    return {"restored_rows": restored, "technical_after_rollback": after}


def recover(
    receipt_dir: Path,
    *,
    rollback: bool,
    expected_manifest_hash: str | None = None,
) -> dict[str, Any]:
    """由 journal 狀態恢復未完成發布，或對完整 applied 修復精確回復。"""
    evidence, manifest, spool_path, manifest_hash = _load_stage(receipt_dir, expected_manifest_hash)
    receipt_dir = Path(str(evidence["receipt_dir"]))
    journal_path = receipt_dir / "journal.json"
    journal_sha_before_lock = _file_hash(journal_path)
    journal = _read_sealed(journal_path)
    if journal.get("manifest_sha256") != manifest_hash:
        raise RawAliasRepairError("recover journal manifest hash 不符")
    if _file_hash(spool_path) != journal.get("rollback_preimage_sha256", manifest.get("canonical_spool_sha256")):
        # The stage spool is both the authoritative after-image and exact DB preimage.
        # The applied receipt may name its hash as rollback_preimage_sha256.
        raise RawAliasRepairError("recover canonical/preimage spool hash 不符")
    audit_path = receipt_dir / "audit.json"
    audit_sha_before_lock = _file_hash(audit_path)
    audit_record = _read_sealed(audit_path)
    if audit_record.get("manifest_sha256") != manifest_hash or journal.get("audit_sha256") != audit_sha_before_lock:
        raise RawAliasRepairError("recover audit identity/hash 不符")
    lock = _acquire_lock(Path(str(evidence["root"])))
    try:
        if _file_hash(journal_path) != journal_sha_before_lock:
            raise RawAliasRepairError("recover journal 在等待維護鎖期間已變更；請重讀狀態後重試")
        journal = _read_sealed(journal_path)
        if journal.get("manifest_sha256") != manifest_hash or journal.get("audit_sha256") != audit_sha_before_lock:
            raise RawAliasRepairError("recover 鎖內 journal identity/hash 不符")
        if _file_hash(audit_path) != audit_sha_before_lock:
            raise RawAliasRepairError("recover audit 在等待維護鎖期間已變更")
        root = Path(str(evidence["root"]))
        current = _current_fingerprints(root)["technical_indicators"]
        before = manifest["database_before"]
        after = journal.get("database_after")
        if rollback:
            if journal.get("state") not in {"applied", "pending"}:
                raise RawAliasRepairError("只能回復 state=applied 或 pending 的 raw alias 修復")
            live_daily_hash = _current_fingerprints(root)["daily_prices"]["table_sha256"]
            if live_daily_hash != evidence["daily_before_hash"]:
                raise RawAliasRepairError("正式 daily_prices 已漂移，拒絕 raw alias rollback")
            _preflight_csv_publication(receipt_dir, manifest, journal, after=False)
            if after is not None and current == after:
                result = _restore_database(evidence, journal, spool_path)
            elif current == before:
                result = {"restored_rows": 0, "technical_after_rollback": before}
            else:
                raise RawAliasRepairError("rollback 偵測到正式技指漂移，拒絕覆蓋")
            _publish_csvs(receipt_dir, manifest, journal, after=False)
            for item in journal["files"]:
                target = Path(str(item["target_path"]))
                if not target.is_file() or _file_hash(target) != item["before_sha256"]:
                    raise RawAliasRepairError(f"rollback CSV 讀回 hash 不符：{target}")
                backup = receipt_dir / str(item["backup_relative_path"])
                if not backup.is_file() or _file_hash(backup) != item["before_sha256"]:
                    raise RawAliasRepairError(f"rollback CSV backup hash 不符：{backup}")
            rolled = {**journal, "state": "rolled_back", "rolled_back_at": datetime.now(timezone.utc).isoformat(), "rollback_result": result}
            _write_sealed(receipt_dir / "rollback_receipt.json", rolled)
            _write_sealed(journal_path, rolled)
            return {"state": "rolled_back", "database_rows": result["restored_rows"], "csv_targets": len(journal["files"])}
        if journal.get("state") != "pending":
            raise RawAliasRepairError("resume 只接受 state=pending journal")
        live_daily_hash = _current_fingerprints(root)["daily_prices"]["table_sha256"]
        if live_daily_hash != evidence["daily_before_hash"]:
            raise RawAliasRepairError("正式 daily_prices 已漂移，拒絕 raw alias resume")
        _preflight_csv_publication(receipt_dir, manifest, journal, after=True)
        if current == before:
            _check_current_before(evidence, manifest)
            def record_before_commit(after_fingerprint: dict[str, Any], updated: int) -> None:
                journal.update({
                    "database_after": after_fingerprint,
                    "technical_after_alias_repair_hash": after_fingerprint["table_sha256"],
                    "database_updated_rows": updated,
                    "database_verified_schema_keys_non_target": True,
                    "database_verified_alias_values": True,
                })
                _write_sealed(journal_path, journal)

            database_result = _apply_database(
                evidence, manifest, spool_path, before_commit=record_before_commit
            )
        elif after and current == after:
            database_result = {"updated_rows": int(journal.get("database_updated_rows", 0)), "technical_after": after}
        else:
            raise RawAliasRepairError("resume 偵測到正式技指漂移，拒絕覆蓋")
        _publish_csvs(receipt_dir, manifest, journal, after=True)
        for item in journal["files"]:
            target = Path(str(item["target_path"]))
            if not target.is_file() or _file_hash(target) != item["after_sha256"]:
                raise RawAliasRepairError(f"resume CSV 讀回 hash 不符：{target}")
        applied = {
            **journal,
            "state": "applied",
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "source_technical_receipt_sha256": evidence["technical_receipt_sha256"],
            "source_technical_manifest_sha256": evidence["technical_manifest_sha256"],
            "canonical_spool_sha256": manifest["canonical_spool_sha256"],
            "canonical_rows": manifest["canonical_rows"],
            "database_field_deltas": manifest["database_field_deltas"],
            "csv_field_deltas": {item["target_path"]: item["field_deltas"] for item in manifest["csv_targets"]},
            "preservation_verified": {
                "database_schema": True,
                "database_keys": True,
                "database_non_target_values": True,
                "csv_keys_and_order": True,
                "csv_non_target_values": True,
            },
            "rollback_preimage_sha256": _file_hash(spool_path),
            "formal_data_written": True,
            "historical_pit": False,
        }
        receipt_sha = _write_sealed(receipt_dir / "receipt.json", applied)
        _write_sealed(journal_path, {**applied, "receipt_sha256": receipt_sha})
        return {"state": "applied", "receipt_dir": str(receipt_dir), "receipt_sha256": receipt_sha, "database_rows": database_result["updated_rows"], "csv_targets": len(journal["files"])}
    finally:
        release_heavy_chain_reservation(lock)


def load_applied_raw_alias_receipt(database_path: Path | str) -> dict[str, Any] | None:
    """載入唯一已套用的六欄 marker；後續 writer guard 可共用此驗證入口。"""
    database_path = Path(database_path).resolve(strict=True)
    root = database_path.parent.parent if database_path.parent.name.casefold() == "sqlite" else database_path.parent
    receipt_root = root / RECEIPT_ROOT
    if not receipt_root.exists():
        return None
    if receipt_root.is_symlink() or not receipt_root.is_dir():
        raise RawAliasRepairError("raw alias receipt 根目錄不是可信目錄")
    applied: list[dict[str, Any]] = []
    for run_dir in sorted(receipt_root.iterdir()):
        if run_dir.is_symlink() or not run_dir.is_dir():
            raise RawAliasRepairError("raw alias receipt 根目錄含未知項目")
        journal_path = run_dir / "journal.json"
        receipt_path = run_dir / "receipt.json"
        if not journal_path.exists() and not receipt_path.exists():
            raise RawAliasRepairError("raw alias receipt run 缺少 journal/receipt")
        journal = _read_sealed(journal_path)
        if journal.get("state") == "pending":
            raise RawAliasRepairError("raw alias 修復仍 pending；writer 必須 fail closed")
        if journal.get("state") == "rolled_back":
            continue
        receipt = _read_sealed(receipt_path)
        if receipt.get("state") != "applied" or journal.get("state") != "applied":
            raise RawAliasRepairError("raw alias 修復 receipt 狀態不明")
        if journal.get("receipt_sha256") != _file_hash(receipt_path):
            raise RawAliasRepairError("raw alias applied receipt hash 與 journal 不符")
        applied.append(receipt)
    if len(applied) > 1:
        raise RawAliasRepairError("raw alias 有多個已套用版本，writer 必須 fail closed")
    if not applied:
        return None
    return applied[0]


def assert_legacy_technical_writer_allowed(
    database_path: Path | str,
    data_root: Path | str,
    *,
    check_only: bool,
) -> None:
    """舊版逐股計算器有 applied marker 時不可先改寫 CSV。"""

    if check_only:
        return
    database_path = Path(database_path)
    receipt_root = Path(data_root) / RECEIPT_ROOT
    if not database_path.is_file():
        if receipt_root.exists():
            raise RawAliasRepairError("raw alias 修訂 marker 存在但正式 SQLite 不可讀；停止舊版技術指標寫入")
        return
    marker = load_applied_raw_alias_receipt(database_path)
    if marker is not None:
        raise RawAliasRepairError(
            "正式六欄 raw alias 已修復；舊版計算器會先覆寫個股與 aggregate CSV，"
            "請改用 Data Update 正式入口重新產生技術資料"
        )


def _raw_alias_authority_source(database_path: Path, marker: Mapping[str, Any]) -> Path:
    """核對 marker 指向的 immutable source 與原 technical publication 身分。"""

    database_path = database_path.resolve(strict=True)
    root = database_path.parent.parent if database_path.parent.name.casefold() == "sqlite" else database_path.parent
    if marker.get("root") != str(root):
        raise RawAliasRepairError("raw alias receipt 與要求寫入的 DATA_ROOT 不同")
    expected_database = _database_path(root).resolve(strict=True)
    if database_path != expected_database:
        raise RawAliasRepairError("raw alias receipt 不屬於要求寫入的 SQLite 資料庫")

    technical_receipt_dir = _resolve_within(root, marker.get("technical_receipt_dir"))
    source_db = _resolve_within(root, marker.get("source_db"))
    source_root = (root / SOURCE_RECEIPT_ROOT).resolve(strict=True)
    if technical_receipt_dir.parent != source_root or source_db.parent != technical_receipt_dir or source_db.name != "source.sqlite":
        raise RawAliasRepairError("raw alias receipt 的 immutable source/技術 receipt 路徑不符")
    if marker.get("source_db_file_identity") != _file_identity(source_db):
        raise RawAliasRepairError("raw alias immutable source 檔案身分已變更")

    source_json_path = technical_receipt_dir / "source.json"
    manifest_path = technical_receipt_dir / "stage" / "manifest.json"
    receipt_path = technical_receipt_dir / "receipt.json"
    journal_path = technical_receipt_dir / "journal.json"
    if not all(path.is_file() and not path.is_symlink() for path in (
        source_json_path, manifest_path, receipt_path, journal_path,
    )):
        raise RawAliasRepairError("raw alias immutable source 缺少正式技術 receipt")
    if (
        _file_hash(manifest_path) != marker.get("source_technical_manifest_sha256")
        or _file_hash(receipt_path) != marker.get("source_technical_receipt_sha256")
    ):
        raise RawAliasRepairError("raw alias immutable source 的技術 manifest/receipt 身分已變更")
    source = _read_json(source_json_path)
    manifest = _read_json(manifest_path)
    receipt = _read_json(receipt_path)
    journal = _read_json(journal_path)
    if (
        receipt != journal
        or receipt.get("state") != "applied"
        or Path(str(source.get("root", ""))).resolve() != root
        or Path(str(source.get("source_db", ""))).resolve() != source_db
        or manifest.get("schema_version") != TECHNICAL_STAGE_SCHEMA
        or manifest.get("source_db") != str(source_db)
        or source.get("source_sha256") != marker.get("source_sha256")
        or manifest.get("source_sha256") != marker.get("source_sha256")
        or receipt.get("source_sha256") != marker.get("source_sha256")
        or receipt.get("manifest_sha256") != marker.get("source_technical_manifest_sha256")
    ):
        raise RawAliasRepairError("raw alias immutable source 與 applied 技術 receipt 內容不一致")
    return source_db


def validate_raw_alias_replacement(
    database_path: Path | str,
    records: Iterable[Mapping[str, object]],
    *,
    replace_all: bool = False,
    replace_dates: bool = False,
    allow_missing_aliases: bool = False,
) -> None:
    """以有界 SQLite spool 驗證 incoming 技術列，不允許舊 cache 覆寫六欄。"""

    if replace_all and replace_dates:
        raise RawAliasRepairError("raw alias 替換模式不可同時指定整表與日期範圍")

    database_path = Path(database_path)
    marker = _load_writer_marker(database_path)
    if marker is None:
        return
    database_path = database_path.resolve(strict=True)
    source_db = _raw_alias_authority_source(database_path, marker)

    with tempfile.TemporaryDirectory(prefix="raw-alias-writer-guard-") as temp_dir:
        spool_path = Path(temp_dir) / "incoming.sqlite"
        with _sqlite_connection(spool_path) as spool:
            alias_columns = ",".join(f"{_quote(name)} TEXT" for name in ALIASES)
            spool.execute(
                "CREATE TABLE incoming (date_key TEXT NOT NULL,symbol_key TEXT NOT NULL,presence_mask INTEGER NOT NULL,"
                + alias_columns
                + ",PRIMARY KEY(symbol_key,date_key)) WITHOUT ROWID"
            )
            placeholders = ",".join("?" for _ in range(3 + len(ALIASES)))
            insert = f"INSERT INTO incoming VALUES ({placeholders})"
            pending: list[tuple[object, ...]] = []
            incoming_rows = 0
            for record in records:
                if not isinstance(record, Mapping):
                    raise RawAliasRepairError("technical alias incoming row 格式不符")
                if not all(name in record for name in KEYS):
                    raise RawAliasRepairError("technical alias incoming 缺少日期或證券代號")
                day, symbol = _date_symbol_key(record["日期"], record["證券代號"])
                presence = sum(1 << index for index, name in enumerate(ALIASES) if name in record)
                values: list[str | None] = []
                for name in ALIASES:
                    value = record.get(name)
                    normalized = _numeric_text(value, name)
                    values.append(normalized if normalized else None)
                pending.append((day, symbol, presence, *values))
                incoming_rows += 1
                if len(pending) >= _CHUNK_ROWS:
                    try:
                        spool.executemany(insert, pending)
                    except sqlite3.IntegrityError as exc:
                        raise RawAliasRepairError("technical alias incoming 含重複日期／證券鍵") from exc
                    pending.clear()
            if pending:
                try:
                    spool.executemany(insert, pending)
                except sqlite3.IntegrityError as exc:
                    raise RawAliasRepairError("technical alias incoming 含重複日期／證券鍵") from exc
            if replace_all and incoming_rows == 0 and int(marker.get("canonical_rows", 0)) > 0:
                raise RawAliasRepairError("technical alias 整表替換來源為空")
            spool.commit()

        if incoming_rows == 0:
            return
        with _readonly_immutable(source_db) as source:
            columns = _read_table_columns(source, "daily_prices")
            if not set((*KEYS, *ALIASES)) <= set(columns):
                raise RawAliasRepairError("immutable daily source 缺少六欄技術 alias")
            source.execute(
                "ATTACH DATABASE ? AS alias_incoming",
                (spool_path.resolve(strict=True).as_uri() + "?mode=ro&immutable=1",),
            )
            source_columns = ",".join(f"d.{_quote(name)}" for name in ALIASES)
            incoming_columns = ",".join(f"i.{_quote(name)}" for name in ALIASES)
            query = (
                "SELECT i.date_key,i.symbol_key,i.presence_mask,"
                + incoming_columns
                + ","
                + source_columns
                + " FROM alias_incoming.incoming i JOIN main.daily_prices d"
                + " ON d.\"證券代號\"=i.symbol_key AND d.\"日期\"=i.date_key"
                + " ORDER BY i.symbol_key,i.date_key"
            )
            full_mask = (1 << len(ALIASES)) - 1
            checked = 0
            cursor = source.execute(query)
            while rows := cursor.fetchmany(_CHUNK_ROWS):
                for row in rows:
                    day, symbol, presence = str(row[0]), str(row[1]), int(row[2])
                    if presence != full_mask and not allow_missing_aliases:
                        raise RawAliasRepairError(
                            f"technical alias incoming 缺少六欄：{day}/{symbol}"
                        )
                    incoming_values = row[3 : 3 + len(ALIASES)]
                    canonical_values = row[3 + len(ALIASES) :]
                    for index, (name, incoming, canonical) in enumerate(
                        zip(ALIASES, incoming_values, canonical_values, strict=True)
                    ):
                        if not (presence & (1 << index)):
                            continue
                        if not _same_numeric(incoming, canonical, name):
                            raise RawAliasRepairError(
                                f"technical alias 舊來源會覆寫已核准日價：{day}/{symbol}/{name}"
                            )
                    checked += 1

            if replace_all:
                source_rows = int(source.execute("SELECT COUNT(*) FROM main.daily_prices").fetchone()[0])
                if source_rows != int(marker.get("canonical_rows", -1)):
                    raise RawAliasRepairError("raw alias marker canonical row 數與 immutable daily source 不同")
                missing = int(source.execute(
                    "SELECT COUNT(*) FROM main.daily_prices d WHERE NOT EXISTS ("
                    "SELECT 1 FROM alias_incoming.incoming i "
                    "WHERE i.date_key=d.\"日期\" "
                    "AND i.symbol_key=d.\"證券代號\")"
                ).fetchone()[0])
                if missing:
                    raise RawAliasRepairError(f"technical alias 整表替換缺少 {missing} 個受保護 key")
            elif replace_dates:
                missing = int(source.execute(
                    "SELECT COUNT(*) FROM main.daily_prices d "
                    "JOIN (SELECT DISTINCT date_key FROM alias_incoming.incoming) scope "
                    "ON scope.date_key=d.\"日期\" "
                    "WHERE NOT EXISTS ("
                    "SELECT 1 FROM alias_incoming.incoming i "
                    "WHERE i.date_key=d.\"日期\" "
                    "AND i.symbol_key=d.\"證券代號\")"
                ).fetchone()[0])
                if missing:
                    raise RawAliasRepairError(
                        f"technical alias 日期替換缺少 {missing} 個受保護 key"
                    )


def prepare_raw_alias_upsert_frame(
    database_path: Path | str,
    frame,
):
    """驗證受保護技術 upsert，並為省略欄位補 immutable 日價或既有值。"""

    import pandas as pd

    if frame is None or frame.empty:
        return frame
    if frame.columns.has_duplicates:
        raise RawAliasRepairError("technical alias incoming 欄名不可重複")

    database_path = Path(database_path)
    marker = _load_writer_marker(database_path)
    if marker is None:
        return frame
    database_path = database_path.resolve(strict=True)
    missing_aliases = [name for name in ALIASES if name not in frame.columns]
    present_aliases = set(ALIASES).intersection(frame.columns)
    if not missing_aliases:
        validate_raw_alias_replacement(
            database_path,
            _frame_records(frame),
        )
        return frame
    if not set(KEYS) <= set(frame.columns):
        raise RawAliasRepairError("technical alias incoming 缺少日期或證券代號")

    source_db = _raw_alias_authority_source(database_path, marker)
    result = frame.copy()
    for name in missing_aliases:
        result[name] = None

    live_uri = database_path.as_uri() + "?mode=ro"
    with tempfile.TemporaryDirectory(prefix="raw-alias-upsert-guard-") as temp_dir:
        spool_path = Path(temp_dir) / "incoming.sqlite"
        with _sqlite_connection(spool_path) as spool:
            alias_columns = ",".join(f"{_quote(name)} TEXT" for name in ALIASES)
            spool.execute(
                "CREATE TABLE incoming (row_number INTEGER NOT NULL UNIQUE,"
                "date_key TEXT NOT NULL,symbol_key TEXT NOT NULL,presence_mask INTEGER NOT NULL,"
                + alias_columns
                + ",PRIMARY KEY(symbol_key,date_key)) WITHOUT ROWID"
            )
            placeholders = ",".join("?" for _ in range(4 + len(ALIASES)))
            insert = f"INSERT INTO incoming VALUES ({placeholders})"
            columns = list(result.columns)
            date_index = columns.index("日期")
            symbol_index = columns.index("證券代號")
            alias_indexes = {name: columns.index(name) for name in ALIASES if name in columns}
            pending: list[tuple[object, ...]] = []
            for row_number, values in enumerate(result.itertuples(index=False, name=None)):
                day, symbol = _date_symbol_key(values[date_index], values[symbol_index])
                presence = sum(
                    1 << index for index, name in enumerate(ALIASES) if name in present_aliases
                )
                normalized_values: list[str | None] = []
                for name in ALIASES:
                    if name not in alias_indexes:
                        normalized_values.append(None)
                        continue
                    value = values[alias_indexes[name]]
                    normalized_values.append(_numeric_text(value, name) or None)
                pending.append((row_number, day, symbol, presence, *normalized_values))
                if len(pending) >= _CHUNK_ROWS:
                    try:
                        spool.executemany(insert, pending)
                    except sqlite3.IntegrityError as exc:
                        raise RawAliasRepairError(
                            "technical alias incoming 含重複日期／證券鍵"
                        ) from exc
                    pending.clear()
            if pending:
                try:
                    spool.executemany(insert, pending)
                except sqlite3.IntegrityError as exc:
                    raise RawAliasRepairError(
                        "technical alias incoming 含重複日期／證券鍵"
                    ) from exc

        with _readonly_immutable(source_db) as source:
            source_columns = _read_table_columns(source, "daily_prices")
            if not set((*KEYS, *ALIASES)) <= set(source_columns):
                raise RawAliasRepairError("immutable daily source 缺少六欄技術 alias")
            live_exists = database_path.exists()
            if not live_exists:
                raise RawAliasRepairError("raw alias writer SQLite 不存在")
            source.execute(
                "ATTACH DATABASE ? AS alias_incoming",
                (spool_path.resolve(strict=True).as_uri() + "?mode=ro&immutable=1",),
            )
            source.execute("ATTACH DATABASE ? AS live", (live_uri,))
            live_tables = {
                str(row[0])
                for row in source.execute(
                    "SELECT name FROM live.sqlite_master WHERE type='table'"
                )
            }
            live_daily_columns: set[str] = set()
            if "daily_prices" in live_tables:
                live_daily_columns = {
                    str(row[1])
                    for row in source.execute('PRAGMA live.table_info("daily_prices")')
                }
            live_columns: set[str] = set()
            if "technical_indicators" in live_tables:
                live_columns = {
                    str(row[1])
                    for row in source.execute(
                        'PRAGMA live.table_info("technical_indicators")'
                    )
                }
            canonical_select = ",".join(
                f'd.{_quote(name)}' for name in ALIASES
            )
            live_select = ",".join(
                f't.{_quote(name)}' if name in live_columns else f'NULL AS {_quote(name)}'
                for name in ALIASES
            )
            live_daily_select = ",".join(
                f'ld.{_quote(name)}' if name in live_daily_columns else f'NULL AS {_quote(name)}'
                for name in ALIASES
            )
            live_daily_join = (
                ' LEFT JOIN live.daily_prices ld '
                'ON ld."證券代號"=i.symbol_key AND ld."日期"=i.date_key'
                if "daily_prices" in live_tables
                and {"證券代號", "日期"} <= live_daily_columns
                else ""
            )
            live_daily_key = 'ld."證券代號"' if live_daily_join else "NULL"
            live_join = (
                ' LEFT JOIN live.technical_indicators t '
                'ON t."證券代號"=i.symbol_key AND t."日期"=i.date_key'
                if "technical_indicators" in live_tables
                and {"證券代號", "日期"} <= live_columns
                else ""
            )
            live_key = 't."證券代號"' if live_join else "NULL"
            query = (
                "SELECT i.row_number,i.presence_mask,d.\"日期\","
                + ",".join(f'i.{_quote(name)}' for name in ALIASES)
                + ","
                + canonical_select
                + ","
                + live_daily_key
                + ","
                + live_daily_select
                + ","
                + live_key
                + ","
                + live_select
                + " FROM alias_incoming.incoming i "
                + "LEFT JOIN main.daily_prices d "
                + 'ON d."證券代號"=i.symbol_key AND d."日期"=i.date_key'
                + live_daily_join
                + live_join
                + " ORDER BY i.row_number"
            )
            plan = [str(row[3]).upper() for row in source.execute("EXPLAIN QUERY PLAN " + query)]
            if not any("SEARCH D" in detail for detail in plan):
                raise RawAliasRepairError(
                    "immutable daily source 未使用日期／證券鍵索引；停止 raw alias writer"
                )
            missing_values: dict[str, list[object]] = {
                name: [] for name in missing_aliases
            }
            checked_rows = 0
            cursor = source.execute(query)
            while rows := cursor.fetchmany(_CHUNK_ROWS):
                for row in rows:
                    presence = int(row[1])
                    source_exists = row[2] is not None
                    incoming_values = row[3 : 3 + len(ALIASES)]
                    canonical_values = row[3 + len(ALIASES) : 3 + 2 * len(ALIASES)]
                    live_daily_key_position = 3 + 2 * len(ALIASES)
                    live_daily_exists_for_key = row[live_daily_key_position] is not None
                    live_daily_values = row[
                        live_daily_key_position + 1 : live_daily_key_position + 1 + len(ALIASES)
                    ]
                    live_key_position = live_daily_key_position + 1 + len(ALIASES)
                    live_exists_for_key = row[live_key_position] is not None
                    live_values = row[live_key_position + 1 :]
                    for index, name in enumerate(ALIASES):
                        if presence & (1 << index):
                            if source_exists and not _same_numeric(
                                incoming_values[index], canonical_values[index], name
                            ):
                                raise RawAliasRepairError(
                                    f"technical alias 舊來源會覆寫已核准日價："
                                    f"{row[0]}/{name}"
                                )
                            continue
                        if name not in missing_values:
                            continue
                        if source_exists:
                            value = canonical_values[index]
                        elif live_daily_exists_for_key:
                            value = live_daily_values[index]
                        elif live_exists_for_key:
                            value = live_values[index]
                        else:
                            value = None
                        missing_values[name].append(value)
                    checked_rows += 1
            if checked_rows != len(result):
                raise RawAliasRepairError("technical alias incoming 列數與 key spool 不符")

    for name, values in missing_values.items():
        result[name] = pd.Series(values, index=result.index, dtype="object")
    return result


def _frame_records(frame) -> Iterator[dict[str, object]]:
    columns = [str(column) for column in frame.columns]
    for values in frame.itertuples(index=False, name=None):
        yield dict(zip(columns, values, strict=True))


def normalize_raw_alias_values_for_storage(frame):
    """將核准 alias 表示轉成 SQLite 可儲存的數字或 NULL。"""

    import pandas as pd
    from pandas.api.types import is_numeric_dtype

    if frame is None or frame.empty:
        return frame
    result = frame.copy()
    for name in ALIASES:
        if name not in result.columns or is_numeric_dtype(result[name].dtype):
            continue
        if not any(isinstance(value, str) for value in result[name].array):
            continue
        result[name] = result[name].map(
            lambda value: _numeric_storage_value(value, name)
        )
    return result


def _load_writer_marker(database_path: Path) -> dict[str, Any] | None:
    if database_path.is_file():
        return load_applied_raw_alias_receipt(database_path)
    root = database_path.parent.parent if database_path.parent.name.casefold() == "sqlite" else database_path.parent
    receipt_root = root / RECEIPT_ROOT
    if receipt_root.exists():
        raise RawAliasRepairError(
            "raw alias 修訂 marker 存在但 writer SQLite 不可讀；停止技術指標寫入"
        )
    return None


def raw_alias_guard_enabled(database_path: Path | str) -> bool:
    """回報 writer 是否位於有效 applied raw-alias 修訂根目錄。"""

    return _load_writer_marker(Path(database_path)) is not None
