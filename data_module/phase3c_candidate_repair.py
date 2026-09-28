"""受控修復 2026-09-11 Phase3C 三大法人 candidate rows。

這個模組是一次性的 candidate-only repair contract，不是一般資料 writer。
它只接受已保存的官方 capture manifest，固定驗證 manifest/raw/candidate hash、
37 個預期操作與目前 candidate DB preimage。plan 只讀 target DB；apply 先用
SQLite online backup，再在同一 transaction 內驗證 row、非目標 scope 與 checkpoint，
最後才把 checkpoint 標成 SUCCESS。formal DB、交易、帳務與正式資料路徑一律拒絕。

原始交易日是 2026-09-11，但來源沒有官方 publication timestamp。repair row 的
``first_observed_at``／``available_at`` 必須使用 capture 實際完成時間；不可填成
2026-09-11，也不可把 candidate repair 宣稱成 historical PIT。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
from typing import Any, Iterable, Mapping, Sequence

from data_module.p0_candidate_repository import validate_candidate_working_copy_path


REPAIR_SCHEMA = "phase3c-candidate-institutional-repair-20260911.v1"
TABLE_NAME = "institutional_flows"
HISTORY_TABLE_NAME = "phase3c_candidate_institutional_history"
TARGET_DATE = "2026-09-11"
APPLY_CONFIRM_TOKEN = "apply-phase3c-candidate-repair-20260911"
ROLLBACK_CONFIRM_TOKEN = "rollback-phase3c-candidate-repair-20260911"
CANONICAL_OBSERVATION_SCHEMA_VERSION = "phase3c-canonical-observation.v1"
HISTORY_COLUMNS = (
    "repair_id",
    "version",
    "stock_code",
    "decision_date",
    "source",
    "valid_from",
    "valid_to",
    "row_json",
    "row_sha256",
    "capture_manifest_sha256",
    "recorded_at",
)

EXPECTED_CAPTURE_MANIFEST_SHA256 = (
    "sha256:9637f746618fc259f5d960971c276bac180e2fd356436ea126fadc3c79ec6faa"
)
EXPECTED_CAPTURE_CANDIDATE_ROWS_SHA256 = (
    "sha256:5d0033784322e6a7dcc4dcd457d7b95af8fd14b2d8cdf171cec5b790c8e592e9"
)
EXPECTED_TWSE_RAW_SHA256 = (
    "sha256:a39eb941db5762a0421e281b909c24db59d0262d5e869feb7b82a41045364c2a"
)
EXPECTED_TPEX_RAW_SHA256 = (
    "sha256:c5987fe920ab981ff7f77fc3355c7a38725662187dfc3e11f5e77bb54e7aa759"
)
EXPECTED_SEMANTIC_HASH = (
    "sha256:a26a38a527be3cbac5695ec12c7a6a29b372a77ee22e06f6cc43b3a37ead1f31"
)
EXPECTED_SOURCE_ROW_COUNT = 21_479
EXPECTED_UPDATE_COUNT = 32
EXPECTED_INSERT_COUNT = 5
EXPECTED_OPERATION_COUNT = 37

TABLE_COLUMNS = (
    "stock_code",
    "decision_date",
    "source_version",
    "publication_at",
    "first_observed_at",
    "available_at",
    "available_date",
    "quality",
    "foreign_investor_buy",
    "foreign_investor_sell",
    "foreign_investor_net",
    "investment_trust_buy",
    "investment_trust_sell",
    "investment_trust_net",
    "dealer_buy",
    "dealer_sell",
    "dealer_net",
)
NUMERIC_COLUMNS = (
    "foreign_investor_buy",
    "foreign_investor_sell",
    "foreign_investor_net",
    "investment_trust_buy",
    "investment_trust_sell",
    "investment_trust_net",
    "dealer_buy",
    "dealer_sell",
    "dealer_net",
)
CUSTODY_COLUMNS = frozenset({"first_observed_at", "available_at"})
SOURCE_VERSION_BY_ENDPOINT = {
    "twse:T86": "twse-official-T86",
    "tpex:3itrade": "tpex-official-3itrade",
}

EXPECTED_UPDATE_KEYS = (
    "2049",
    "2201",
    "2308",
    "2327",
    "2330",
    "2345",
    "2368",
    "2382",
    "2383",
    "2395",
    "2454",
    "2884",
    "2890",
    "3008",
    "3045",
    "3231",
    "3376",
    "3406",
    "3491",
    "3529",
    "3665",
    "3711",
    "5347",
    "6409",
    "6515",
    "6531",
    "6669",
    "6727",
    "7734",
    "7769",
    "7828",
    "8996",
)
EXPECTED_INSERT_KEYS = ("00625K", "00636K", "00643K", "00657K", "00668K")


class CandidateRepairError(RuntimeError):
    """任何 repair plan/apply/rollback 的 fail-closed 錯誤。"""


@dataclass(frozen=True)
class RepairContract:
    """可測試的固定 repair contract；CLI 永遠使用 production contract。"""

    manifest_sha256: str
    candidate_rows_sha256: str
    raw_hashes: Mapping[str, str]
    semantic_hash: str
    expected_source_rows: int
    update_keys: tuple[str, ...]
    insert_keys: tuple[str, ...]

    @property
    def operation_count(self) -> int:
        return len(self.update_keys) + len(self.insert_keys)


PRODUCTION_CONTRACT = RepairContract(
    manifest_sha256=EXPECTED_CAPTURE_MANIFEST_SHA256,
    candidate_rows_sha256=EXPECTED_CAPTURE_CANDIDATE_ROWS_SHA256,
    raw_hashes={
        "twse:T86": EXPECTED_TWSE_RAW_SHA256,
        "tpex:3itrade": EXPECTED_TPEX_RAW_SHA256,
    },
    semantic_hash=EXPECTED_SEMANTIC_HASH,
    expected_source_rows=EXPECTED_SOURCE_ROW_COUNT,
    update_keys=EXPECTED_UPDATE_KEYS,
    insert_keys=EXPECTED_INSERT_KEYS,
)


def _contract_payload(contract: RepairContract) -> dict[str, Any]:
    """把固定 contract 寫進 plan，讓 apply 重新驗證同一份 contract。"""

    return {
        "manifest_sha256": contract.manifest_sha256,
        "candidate_rows_sha256": contract.candidate_rows_sha256,
        "raw_hashes": dict(sorted(contract.raw_hashes.items())),
        "semantic_hash": contract.semantic_hash,
        "expected_source_rows": contract.expected_source_rows,
        "update_keys": list(contract.update_keys),
        "insert_keys": list(contract.insert_keys),
        "operation_count": contract.operation_count,
    }


def _contract_from_plan(plan: Mapping[str, Any]) -> RepairContract:
    payload = plan.get("contract")
    if not isinstance(payload, Mapping):
        raise CandidateRepairError("plan 缺少固定 repair contract")
    try:
        raw_hashes = payload["raw_hashes"]
        update_keys = payload["update_keys"]
        insert_keys = payload["insert_keys"]
        if not isinstance(raw_hashes, Mapping) or not isinstance(update_keys, list) or not isinstance(insert_keys, list):
            raise TypeError
        contract = RepairContract(
            manifest_sha256=str(payload["manifest_sha256"]),
            candidate_rows_sha256=str(payload["candidate_rows_sha256"]),
            raw_hashes={str(key): str(value) for key, value in raw_hashes.items()},
            semantic_hash=str(payload["semantic_hash"]),
            expected_source_rows=int(payload["expected_source_rows"]),
            update_keys=tuple(str(value) for value in update_keys),
            insert_keys=tuple(str(value) for value in insert_keys),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise CandidateRepairError("plan contract 欄位不合法") from exc
    if payload.get("operation_count") != contract.operation_count:
        raise CandidateRepairError("plan contract operation_count 不符")
    return contract


def _require_plan_contract(plan: Mapping[str, Any], contract: RepairContract) -> None:
    if _contract_from_plan(plan) != contract:
        raise CandidateRepairError("plan contract 與 apply 使用的固定 contract 不一致")


def _sha256_bytes(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1 << 20):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _digest_text(value: object) -> str:
    text = str(value or "").strip().lower()
    return text if text.startswith("sha256:") else "sha256:" + text


def _json_bytes(payload: object) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _write_json_create_only(path: Path, payload: Mapping[str, Any]) -> None:
    data = _json_bytes(payload)
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.is_symlink() or path.read_bytes() != data:
            raise CandidateRepairError(f"拒絕覆寫既有 receipt/plan: {path}")
        return
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=f".{path.name}.", suffix=".tmp", dir=path.parent, delete=False
        ) as stream:
            temporary = Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
        temporary = None
    finally:
        if temporary is not None:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise CandidateRepairError(f"JSON 不存在或是 symlink: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CandidateRepairError(f"JSON 無法讀取: {path}") from exc
    if not isinstance(payload, dict):
        raise CandidateRepairError(f"JSON root 必須是 object: {path}")
    return payload


def _resolve_child(root: Path, relative: object, *, label: str) -> Path:
    raw = str(relative or "").strip()
    if not raw:
        raise CandidateRepairError(f"{label} path 不可為空")
    root = root.resolve(strict=True)
    candidate = Path(raw)
    if candidate.is_absolute():
        raise CandidateRepairError(f"{label} 必須是 manifest 相對路徑")
    resolved = (root / candidate).resolve(strict=False)
    if not resolved.is_relative_to(root) or resolved.is_symlink():
        raise CandidateRepairError(f"{label} path escape 或 symlink: {raw}")
    return resolved


def _copy_create_only(source: Path, destination: Path) -> None:
    if not source.is_file() or source.is_symlink():
        raise CandidateRepairError(f"capture evidence 不是一般檔案: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if destination.is_symlink() or _sha256_file(destination) != _sha256_file(source):
            raise CandidateRepairError(f"capture evidence 已存在但 bytes 不同: {destination}")
        return
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent, delete=False
        ) as stream:
            temporary = Path(stream.name)
        shutil.copyfile(source, temporary)
        temporary.replace(destination)
        temporary = None
    finally:
        if temporary is not None:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass


def _copy_capture_tree(capture_root: Path, destination: Path) -> None:
    capture_root = capture_root.resolve(strict=True)
    if destination.resolve() == capture_root:
        raise CandidateRepairError("capture evidence destination 不可等於 source")
    for source in sorted(capture_root.rglob("*")):
        relative = source.relative_to(capture_root)
        target = destination / relative
        if source.is_symlink():
            raise CandidateRepairError(f"capture tree 含 symlink: {source}")
        if source.is_file():
            _copy_create_only(source, target)


def _aware_timestamp(value: object, *, label: str) -> str:
    text = str(value or "").strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CandidateRepairError(f"{label} 不是合法 ISO timestamp: {value!r}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CandidateRepairError(f"{label} 必須含 timezone: {value!r}")
    return parsed.astimezone(timezone.utc).isoformat()


def _natural_key(row: Mapping[str, Any]) -> tuple[str, str]:
    return str(row.get("stock_code", "")), str(row.get("decision_date", ""))


def _key_text(row: Mapping[str, Any]) -> str:
    return "|".join(_natural_key(row))


def _canonical_row_from_capture(item: Mapping[str, Any]) -> dict[str, Any]:
    if item.get("table") != TABLE_NAME:
        raise CandidateRepairError("capture candidate row table 不是 institutional_flows")
    values = item.get("values")
    provenance = item.get("provenance")
    if not isinstance(values, Mapping) or not isinstance(provenance, Mapping):
        raise CandidateRepairError("capture candidate row 缺少 values/provenance")
    endpoint_id = str(provenance.get("endpoint_id", ""))
    source_version = SOURCE_VERSION_BY_ENDPOINT.get(endpoint_id)
    if source_version is None:
        raise CandidateRepairError(f"不支援的 institutional endpoint: {endpoint_id}")
    if str(values.get("decision_date")) != TARGET_DATE:
        raise CandidateRepairError("capture candidate row decision_date 不符")
    if item.get("availability_evidence") != "first_observed_only":
        raise CandidateRepairError("9/11 repair 不接受非 first_observed_only custody")
    if values.get("publication_at") not in (None, "") or values.get("available_date") not in (None, ""):
        raise CandidateRepairError("9/11 repair 不得填 publication_at/available_date")
    if values.get("quality") != "degraded":
        raise CandidateRepairError("9/11 repair 的來源 quality 必須是 degraded")
    custody = _aware_timestamp(item.get("available_at") or values.get("observed_at"), label="capture available_at")
    if _aware_timestamp(values.get("observed_at"), label="capture observed_at") != custody:
        raise CandidateRepairError("capture observed_at/available_at 不一致")
    result: dict[str, Any] = {
        "stock_code": str(values.get("stock_code", "")).strip(),
        "decision_date": TARGET_DATE,
        "source_version": source_version,
        "publication_at": None,
        "first_observed_at": custody,
        "available_at": custody,
        "available_date": None,
        "quality": "degraded",
    }
    if not result["stock_code"]:
        raise CandidateRepairError("capture candidate row stock_code 不可為空")
    for column in NUMERIC_COLUMNS:
        value = values.get(column)
        if isinstance(value, bool) or not isinstance(value, int):
            raise CandidateRepairError(f"{_key_text(result)} 的 {column} 不是整數")
        result[column] = value
    for prefix in ("foreign_investor", "investment_trust", "dealer"):
        if result[f"{prefix}_net"] != result[f"{prefix}_buy"] - result[f"{prefix}_sell"]:
            raise CandidateRepairError(f"{_key_text(result)} 的 {prefix} net identity 不成立")
    return result


def _canonical_row_from_db(row: Mapping[str, Any]) -> dict[str, Any]:
    return {column: row[column] for column in TABLE_COLUMNS}


def _row_payload_hash(rows: Iterable[Mapping[str, Any]]) -> str:
    ordered = [
        {column: row.get(column) for column in TABLE_COLUMNS}
        for row in sorted(rows, key=_natural_key)
    ]
    return _sha256_bytes(_json_bytes(ordered))


def _semantic_hash(rows: Iterable[Mapping[str, Any]]) -> str:
    ordered = []
    for row in sorted(rows, key=_natural_key):
        ordered.append(
            {
                column: row.get(column)
                for column in TABLE_COLUMNS
                if column not in CUSTODY_COLUMNS
            }
        )
    payload = {
        "schema_version": CANONICAL_OBSERVATION_SCHEMA_VERSION,
        "rows": ordered,
    }
    # source observation ledger 的 semantic hash 使用 canonical JSON bytes，
    # 不附加 newline；row/file receipt hash 仍使用 _json_bytes 的 newline 形式。
    canonical = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return _sha256_bytes(canonical)


def _scope_hash(conn: sqlite3.Connection, *, exclude_date: str | None = None) -> str:
    digest = hashlib.sha256()
    quoted = ",".join('"' + column.replace('"', '""') + '"' for column in TABLE_COLUMNS)
    query = f'SELECT {quoted} FROM "{TABLE_NAME}"'
    parameters: tuple[str, ...] = ()
    if exclude_date is not None:
        query += ' WHERE "decision_date" <> ?'
        parameters = (exclude_date,)
    query += ' ORDER BY "decision_date", "stock_code"'
    for row in conn.execute(query, parameters):
        digest.update(_json_bytes(list(row)))
    return "sha256:" + digest.hexdigest()


def _quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _source_observation_scope_hash(conn: sqlite3.Connection) -> str:
    """hash 9/11 institutional ledger；用來偵測 apply 期間的 ledger 漂移。"""

    rows = conn.execute(
        "SELECT source, decision_date, observation_hash, observed_at, row_count, "
        "observation_mode, source_versions, first_observed_at_min, available_at_max, "
        "canonical_payload_json, diagnostic_json "
        "FROM phase3c_source_observations WHERE source=? AND decision_date=? "
        "ORDER BY observation_hash",
        ("institutional", TARGET_DATE),
    ).fetchall()
    return _sha256_bytes(_json_bytes([list(row) for row in rows]))


def _checkpoint_non_target_scope_hash(conn: sqlite3.Connection) -> str:
    rows = conn.execute(
        "SELECT decision_date, source, status, row_count, fetched_at, error_message "
        "FROM phase3c_backfill_checkpoints WHERE decision_date<>? "
        "ORDER BY decision_date, source",
        (TARGET_DATE,),
    ).fetchall()
    return _sha256_bytes(_json_bytes([list(row) for row in rows]))


def _non_target_tables_hash(conn: sqlite3.Connection) -> str:
    """hash candidate DB 的其他資料表，排除目標表、checkpoint 與本 repair history。"""

    table_rows = conn.execute(
        "SELECT name, sql FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    digest = hashlib.sha256()
    excluded = {TABLE_NAME, "phase3c_backfill_checkpoints", HISTORY_TABLE_NAME}
    for table_name, sql in table_rows:
        table_name = str(table_name)
        if table_name in excluded:
            continue
        digest.update(_json_bytes({"table": table_name, "sql": sql}))
        columns = [str(row[1]) for row in conn.execute(f"PRAGMA table_info({_quote_identifier(table_name)})")]
        digest.update(_json_bytes(columns))
        rows = conn.execute(f"SELECT * FROM {_quote_identifier(table_name)}").fetchall()
        encoded_rows = sorted(_json_bytes(list(row)) for row in rows)
        for encoded in encoded_rows:
            digest.update(encoded)
    return "sha256:" + digest.hexdigest()


def _history_table_columns(conn: sqlite3.Connection) -> tuple[str, ...]:
    return tuple(
        str(row[1])
        for row in conn.execute(f"PRAGMA table_info({_quote_identifier(HISTORY_TABLE_NAME)})")
    )


def _ensure_history_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {_quote_identifier(HISTORY_TABLE_NAME)} (
            repair_id TEXT NOT NULL,
            version TEXT NOT NULL CHECK (version IN ('before', 'after')),
            stock_code TEXT NOT NULL,
            decision_date TEXT NOT NULL,
            source TEXT NOT NULL,
            valid_from TEXT,
            valid_to TEXT,
            row_json TEXT NOT NULL,
            row_sha256 TEXT NOT NULL,
            capture_manifest_sha256 TEXT NOT NULL,
            recorded_at TEXT NOT NULL,
            PRIMARY KEY (repair_id, version, stock_code, decision_date)
        )
        """
    )
    if _history_table_columns(conn) != HISTORY_COLUMNS:
        raise CandidateRepairError("candidate repair history schema 不符")


def _history_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {column: row.get(column) for column in TABLE_COLUMNS}


def _history_row_hash(row: Mapping[str, Any]) -> str:
    return _row_payload_hash([_history_row(row)])


def _archive_repair_history(
    conn: sqlite3.Connection,
    *,
    repair_id: str,
    operations: Sequence[Mapping[str, Any]],
    capture_manifest_sha256: str,
    recorded_at: str,
) -> int:
    """在同一 transaction 封存 before/after，讓舊值可按 custody 時間查回。"""

    _ensure_history_table(conn)
    existing = conn.execute(
        f"SELECT COUNT(*) FROM {_quote_identifier(HISTORY_TABLE_NAME)} WHERE repair_id=?",
        (repair_id,),
    ).fetchone()
    if existing and int(existing[0]) != 0:
        raise CandidateRepairError(f"repair history 已存在: {repair_id}")
    insert_sql = (
        f"INSERT INTO {_quote_identifier(HISTORY_TABLE_NAME)} "
        f"({','.join(_quote_identifier(column) for column in HISTORY_COLUMNS)}) "
        f"VALUES ({','.join('?' for _ in HISTORY_COLUMNS)})"
    )
    inserted = 0
    for operation in operations:
        key = str(operation.get("key", ""))
        stock_code, decision_date = key.split("|", 1)
        after = operation.get("after")
        if not isinstance(after, Mapping):
            raise CandidateRepairError(f"history after 不合法: {key}")
        if operation.get("operation") == "UPDATE":
            before = operation.get("before")
            if not isinstance(before, Mapping):
                raise CandidateRepairError(f"history before 不合法: {key}")
            before_values = _history_row(before)
            conn.execute(
                insert_sql,
                (
                    repair_id,
                    "before",
                    stock_code,
                    decision_date,
                    "institutional",
                    before_values["first_observed_at"],
                    after.get("available_at"),
                    _json_bytes(before_values).decode("utf-8"),
                    _history_row_hash(before_values),
                    capture_manifest_sha256,
                    recorded_at,
                ),
            )
            inserted += 1
        after_values = _history_row(after)
        conn.execute(
            insert_sql,
            (
                repair_id,
                "after",
                stock_code,
                decision_date,
                "institutional",
                after_values["available_at"],
                None,
                _json_bytes(after_values).decode("utf-8"),
                _history_row_hash(after_values),
                capture_manifest_sha256,
                recorded_at,
            ),
        )
        inserted += 1
    return inserted


def read_history_as_of(
    *,
    candidate_db: Path,
    as_of: str,
    stock_code: str | None = None,
) -> list[dict[str, Any]]:
    """唯讀查回 repair history；as-of 以來源實際 custody timestamp 判定。"""

    as_of = _aware_timestamp(as_of, label="as_of")
    conn = _open_candidate_readonly(candidate_db.resolve())
    try:
        if _history_table_columns(conn) != HISTORY_COLUMNS:
            raise CandidateRepairError("candidate repair history 尚未建立或 schema 不符")
        parameters: list[str] = [as_of, as_of]
        query = (
            f"SELECT row_json FROM {_quote_identifier(HISTORY_TABLE_NAME)} "
            "WHERE valid_from IS NOT NULL AND valid_from <= ? "
            "AND (valid_to IS NULL OR valid_to > ?)"
        )
        if stock_code is not None:
            query += " AND stock_code=?"
            parameters.append(str(stock_code))
        query += " ORDER BY stock_code, decision_date, version"
        result: list[dict[str, Any]] = []
        for (row_json,) in conn.execute(query, parameters):
            payload = json.loads(row_json)
            if not isinstance(payload, dict):
                raise CandidateRepairError("history row_json 不是 object")
            result.append(payload)
        return result
    finally:
        conn.close()


def _candidate_db_uri(path: Path) -> str:
    return f"file:{path.as_posix()}?mode=ro"


def _validate_candidate_target(
    candidate_db: Path,
    *,
    production_data_root: Path,
    formal_db: Path,
) -> Path:
    try:
        resolved = validate_candidate_working_copy_path(
            candidate_db,
            production_data_root=production_data_root,
            production_db_path=formal_db,
        )
    except (OSError, ValueError) as exc:
        raise CandidateRepairError(str(exc)) from exc
    if resolved.name.lower() == "twstock.db":
        raise CandidateRepairError("拒絕以 twstock.db 作為 candidate repair target")
    return resolved


def _table_columns(conn: sqlite3.Connection) -> tuple[str, ...]:
    columns = tuple(str(row[1]) for row in conn.execute(f'PRAGMA table_info("{TABLE_NAME}")'))
    if columns != TABLE_COLUMNS:
        raise CandidateRepairError(
            f"{TABLE_NAME} schema 不符: expected={TABLE_COLUMNS}, actual={columns}"
        )
    return columns


def _read_target_rows(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    _table_columns(conn)
    quoted = ",".join('"' + column + '"' for column in TABLE_COLUMNS)
    rows = conn.execute(
        f'SELECT {quoted} FROM "{TABLE_NAME}" WHERE "decision_date" = ? ORDER BY "stock_code"',
        (TARGET_DATE,),
    ).fetchall()
    return [dict(zip(TABLE_COLUMNS, row)) for row in rows]


def _read_checkpoint(conn: sqlite3.Connection) -> dict[str, Any]:
    columns = tuple(str(row[1]) for row in conn.execute("PRAGMA table_info(phase3c_backfill_checkpoints)"))
    expected = ("decision_date", "source", "status", "row_count", "fetched_at", "error_message")
    if columns != expected:
        raise CandidateRepairError("phase3c_backfill_checkpoints schema 不符")
    row = conn.execute(
        "SELECT decision_date, source, status, row_count, fetched_at, error_message "
        "FROM phase3c_backfill_checkpoints WHERE decision_date=? AND source=?",
        (TARGET_DATE, "institutional"),
    ).fetchone()
    if row is None:
        raise CandidateRepairError("9/11 institutional checkpoint 不存在")
    return dict(zip(expected, row))


def _integrity_check(conn: sqlite3.Connection) -> None:
    result = conn.execute("PRAGMA quick_check").fetchone()
    if not result or str(result[0]).lower() != "ok":
        raise CandidateRepairError(f"SQLite quick_check 失敗: {result!r}")


def _verify_manifest_contract(
    manifest_path: Path,
    *,
    contract: RepairContract,
) -> tuple[dict[str, Any], Path, list[dict[str, Any]], dict[str, str]]:
    manifest_path = manifest_path.resolve(strict=True)
    manifest_hash = _sha256_file(manifest_path)
    if manifest_hash != contract.manifest_sha256:
        raise CandidateRepairError(
            f"capture manifest hash 不符: expected={contract.manifest_sha256}, actual={manifest_hash}"
        )
    manifest = _read_json(manifest_path)
    if manifest.get("candidate_only") is not True or manifest.get("formal_apply_allowed") is not False:
        raise CandidateRepairError("capture manifest candidate-only boundary 不符")
    if manifest.get("production_scheduler_allowed") is not False:
        raise CandidateRepairError("capture manifest 不得允許 production scheduler")
    if manifest.get("downstream_eligibility") != "none":
        raise CandidateRepairError("capture manifest downstream eligibility 不符")
    if manifest.get("as_of_date") != TARGET_DATE or manifest.get("discovered_sessions") != [TARGET_DATE]:
        raise CandidateRepairError("capture manifest 不是 bounded 2026-09-11 session")
    root = manifest_path.parent
    entries = [
        entry for entry in manifest.get("sources", [])
        if isinstance(entry, Mapping) and entry.get("source_id") == TABLE_NAME
    ]
    if len(entries) != 1:
        raise CandidateRepairError("capture manifest 必須剛好有一個 institutional source entry")
    entry = dict(entries[0])
    if entry.get("decision_date") != TARGET_DATE:
        raise CandidateRepairError("capture institutional source custody contract 不符")
    if int(entry.get("accepted_row_count", -1)) != contract.expected_source_rows:
        raise CandidateRepairError("capture institutional accepted row count 不符")
    candidate_path = _resolve_child(root, entry.get("candidate_rows_path"), label="candidate rows")
    candidate_hash = _sha256_file(candidate_path)
    expected_candidate_hash = _digest_text(entry.get("candidate_rows_sha256"))
    if candidate_hash != expected_candidate_hash or candidate_hash != contract.candidate_rows_sha256:
        raise CandidateRepairError("capture candidate rows hash 不符")
    raw_hashes: dict[str, str] = {}
    raw_artifacts = entry.get("raw_artifacts")
    if not isinstance(raw_artifacts, list) or len(raw_artifacts) != 2:
        raise CandidateRepairError("institutional raw artifacts 必須剛好有 TWSE/TPEx 兩份")
    for raw_entry in raw_artifacts:
        if not isinstance(raw_entry, Mapping):
            raise CandidateRepairError("raw artifact entry 不是 object")
        raw_path = _resolve_child(root, raw_entry.get("path"), label="raw artifact")
        metadata_path = _resolve_child(root, raw_entry.get("metadata_path"), label="raw metadata")
        raw_hash = _sha256_file(raw_path)
        expected_hash = _digest_text(raw_entry.get("sha256"))
        if raw_hash != expected_hash:
            raise CandidateRepairError(f"raw artifact hash 不符: {raw_path}")
        metadata = _read_json(metadata_path)
        if (
            _digest_text(metadata.get("payload_sha256")) != raw_hash
            or metadata.get("requested_date") != TARGET_DATE
            or metadata.get("source_id") != TABLE_NAME
        ):
            raise CandidateRepairError(f"raw metadata 不符: {metadata_path}")
        endpoint = str(metadata.get("endpoint_id", ""))
        if endpoint not in SOURCE_VERSION_BY_ENDPOINT:
            raise CandidateRepairError(f"institutional endpoint 不支援: {endpoint}")
        if contract.raw_hashes.get(endpoint) != raw_hash:
            raise CandidateRepairError(f"raw hash 不符 expected contract: {endpoint}")
        if metadata.get("http_status") != 200:
            raise CandidateRepairError(f"raw HTTP status 非 200: {endpoint}")
        raw_hashes[endpoint] = raw_hash
    if set(raw_hashes) != set(contract.raw_hashes):
        raise CandidateRepairError("institutional raw artifacts endpoint set 不符")
    try:
        rows_payload = json.loads(candidate_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CandidateRepairError("capture candidate rows 無法解析") from exc
    if not isinstance(rows_payload, list) or len(rows_payload) != contract.expected_source_rows:
        raise CandidateRepairError("capture candidate rows count 不符")
    rows = [_canonical_row_from_capture(item) for item in rows_payload if isinstance(item, Mapping)]
    if len(rows) != contract.expected_source_rows:
        raise CandidateRepairError("capture candidate rows 含非 object")
    keys = [_key_text(row) for row in rows]
    if len(set(keys)) != len(keys):
        raise CandidateRepairError("capture candidate rows 含重複 natural key")
    if _semantic_hash(rows) != contract.semantic_hash:
        raise CandidateRepairError("capture canonical semantic hash 不符")
    return manifest, root, rows, raw_hashes


def _open_candidate_readonly(path: Path) -> sqlite3.Connection:
    if not path.is_file() or path.is_symlink():
        raise CandidateRepairError(f"candidate DB 不存在或是 symlink: {path}")
    conn = sqlite3.connect(_candidate_db_uri(path), uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    if conn.execute("PRAGMA query_only").fetchone()[0] != 1:
        conn.close()
        raise CandidateRepairError("candidate DB 無法啟用 query_only")
    return conn


def _logical_snapshot(conn: sqlite3.Connection) -> dict[str, Any]:
    """從 SQLite snapshot 讀出 apply guard 所需的 logical state。"""

    rows = _read_target_rows(conn)
    return {
        "target_rows_sha256": _row_payload_hash(rows),
        "target_row_count": len(rows),
        "target_table_non_target_rows_sha256": _scope_hash(conn, exclude_date=TARGET_DATE),
        "non_target_tables_sha256": _non_target_tables_hash(conn),
        "observation_scope_sha256": _source_observation_scope_hash(conn),
        "checkpoint_non_target_scope_sha256": _checkpoint_non_target_scope_hash(conn),
        "checkpoint": _read_checkpoint(conn),
    }


def _capture_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    by_source: dict[str, list[str]] = {}
    for row in rows:
        by_source.setdefault(str(row["source_version"]), []).append(str(row["available_at"]))
    return {
        source: {
            "row_count": len(values),
            "first_observed_at_min": min(values),
            "available_at_max": max(values),
            "available_at_values": sorted(set(values)),
        }
        for source, values in sorted(by_source.items())
    }


def _operation_diff(before: Mapping[str, Any], after: Mapping[str, Any]) -> dict[str, list[Any]]:
    return {
        column: [before.get(column), after.get(column)]
        for column in TABLE_COLUMNS
        if before.get(column) != after.get(column)
    }


def _copy_evidence(manifest_root: Path, destination: Path) -> None:
    _copy_capture_tree(manifest_root, destination)


def build_plan(
    *,
    capture_manifest: Path,
    candidate_db: Path,
    production_data_root: Path,
    formal_db: Path,
    receipt_dir: Path,
    contract: RepairContract = PRODUCTION_CONTRACT,
) -> dict[str, Any]:
    """只讀 target DB，建立 hash-bound plan 與 capture evidence copy。"""

    target = _validate_candidate_target(candidate_db.resolve(), production_data_root=production_data_root.resolve(), formal_db=formal_db.resolve())
    manifest, capture_root, incoming_rows, raw_hashes = _verify_manifest_contract(
        capture_manifest, contract=contract
    )
    receipt_dir = receipt_dir.resolve()
    evidence_dir = receipt_dir / "capture"
    _copy_evidence(capture_root, evidence_dir)
    evidence_manifest = evidence_dir / "manifest.json"
    if _sha256_file(evidence_manifest) != contract.manifest_sha256:
        raise CandidateRepairError("capture evidence copy manifest hash 不符")

    conn = _open_candidate_readonly(target)
    try:
        _integrity_check(conn)
        before_rows = _read_target_rows(conn)
        before_checkpoint = _read_checkpoint(conn)
        latest_observations = conn.execute(
            "SELECT observation_hash, observed_at, canonical_payload_json "
            "FROM phase3c_source_observations WHERE source=? AND decision_date=? ORDER BY observed_at",
            ("institutional", TARGET_DATE),
        ).fetchall()
        if not latest_observations:
            raise CandidateRepairError("9/11 institutional source observation ledger 不存在")
        ledger_semantic_hashes: list[str] = []
        for observation in latest_observations:
            payload = json.loads(observation[2])
            ledger_rows = payload.get("rows")
            if not isinstance(ledger_rows, list):
                raise CandidateRepairError("source observation canonical payload rows 不符")
            ledger_semantic_hashes.append(_semantic_hash(ledger_rows))
        if set(ledger_semantic_hashes) != {contract.semantic_hash}:
            raise CandidateRepairError("ledger semantic hash 不一致")
        before_snapshot = _logical_snapshot(conn)
    finally:
        conn.close()

    before_by_key = {_key_text(row): row for row in before_rows}
    incoming_by_key = {_key_text(row): row for row in incoming_rows}
    expected_keys = set(incoming_by_key)
    existing_keys = set(before_by_key)
    missing_keys = sorted(expected_keys - existing_keys)
    unexpected_keys = sorted(existing_keys - expected_keys)
    update_keys: list[str] = []
    unchanged_keys: list[str] = []
    operations: list[dict[str, Any]] = []
    for key in sorted(expected_keys & existing_keys):
        before = before_by_key[key]
        after = incoming_by_key[key]
        diff = _operation_diff(before, after)
        material = set(diff) - CUSTODY_COLUMNS
        if material:
            update_keys.append(key)
            if set(diff) - (CUSTODY_COLUMNS | set(NUMERIC_COLUMNS)):
                raise CandidateRepairError(f"{key} 含非允許修訂欄位: {sorted(diff)}")
            operations.append({
                "operation": "UPDATE",
                "key": key,
                "before": before,
                "after": after,
                "changed_columns": sorted(diff),
            })
        else:
            unchanged_keys.append(key)
    for key in missing_keys:
        operations.append({
            "operation": "INSERT",
            "key": key,
            "before": None,
            "after": incoming_by_key[key],
            "changed_columns": list(TABLE_COLUMNS),
        })
    if unexpected_keys:
        raise CandidateRepairError(f"candidate 有 unexpected 9/11 keys: {unexpected_keys[:10]}")
    if tuple(sorted(update_keys)) != tuple(sorted(f"{key}|{TARGET_DATE}" for key in contract.update_keys)):
        raise CandidateRepairError("實際 update key set 不符固定 repair contract")
    if tuple(sorted(missing_keys)) != tuple(sorted(f"{key}|{TARGET_DATE}" for key in contract.insert_keys)):
        raise CandidateRepairError("實際 insert key set 不符固定 repair contract")
    if len(operations) != contract.operation_count:
        raise CandidateRepairError(f"repair operation count 不符: {len(operations)}")
    if len(update_keys) != len(contract.update_keys) or len(missing_keys) != len(contract.insert_keys):
        raise CandidateRepairError("repair update/insert count 不符")

    after_by_key = dict(before_by_key)
    for operation in operations:
        after_by_key[operation["key"]] = operation["after"]
    after_rows = [after_by_key[key] for key in sorted(after_by_key)]
    if len(after_rows) != contract.expected_source_rows:
        raise CandidateRepairError("repair after row count 不符")
    after_target_hash = _row_payload_hash(after_rows)
    repair_id = "phase3c-20260911-" + contract.manifest_sha256.split(":", 1)[1][:16]
    plan = {
        "schema_version": REPAIR_SCHEMA,
        "status": "planned",
        "repair_id": repair_id,
        "contract": _contract_payload(contract),
        "repair_scope": {
            "source": "institutional",
            "table": TABLE_NAME,
            "decision_date": TARGET_DATE,
            "candidate_only": True,
            "formal_db_written": False,
            "downstream_eligibility": "none",
            "historical_pit_claim": False,
        },
        "target": {
            "candidate_db": str(target),
            "production_data_root": str(production_data_root.resolve()),
            "formal_db": str(formal_db.resolve()),
            "before_target_rows_sha256": before_snapshot["target_rows_sha256"],
            "before_target_table_non_target_rows_sha256": before_snapshot["target_table_non_target_rows_sha256"],
            "before_non_target_tables_sha256": before_snapshot["non_target_tables_sha256"],
            "before_observation_scope_sha256": before_snapshot["observation_scope_sha256"],
            "before_checkpoint_non_target_scope_sha256": before_snapshot["checkpoint_non_target_scope_sha256"],
            "before_checkpoint": before_snapshot["checkpoint"],
            "before_row_count": len(before_rows),
            "after_row_count": len(after_rows),
            "after_target_rows_sha256": after_target_hash,
        },
        "capture": {
            "manifest_sha256": contract.manifest_sha256,
            "manifest_run_id": manifest.get("run_id"),
            "manifest_created_at": manifest.get("created_at"),
            "manifest_path_copy": "capture/manifest.json",
            "candidate_rows_sha256": contract.candidate_rows_sha256,
            "raw_hashes": raw_hashes,
            "semantic_hash": contract.semantic_hash,
            "custody": _capture_summary(incoming_rows),
            "raw_payload_copied": True,
            "metadata_copied": True,
        },
        "expected_operations": {
            "update_count": len(contract.update_keys),
            "insert_count": len(contract.insert_keys),
            "total_count": contract.operation_count,
            "unchanged_count": len(unchanged_keys),
            "update_keys": [f"{key}|{TARGET_DATE}" for key in contract.update_keys],
            "insert_keys": [f"{key}|{TARGET_DATE}" for key in contract.insert_keys],
        },
        "checkpoint_before": before_checkpoint,
        "checkpoint_after_policy": {
            "status": "SUCCESS",
            "row_count": contract.expected_source_rows,
            "error_message": None,
            "fetched_at": "apply_completion_utc_after_post_write_verification",
        },
        "operations": operations,
        "rollback": {
            "backup_required": True,
            "backup_kind": "sqlite_online_backup",
            "rollback_requires_current_after_target_rows_and_checkpoint": True,
            "rollback_preserves_other_tables_and_dates": True,
            "rollback_receipt": "rollback_receipt.json",
        },
    }
    plan_path = receipt_dir / "plan.json"
    _write_json_create_only(plan_path, plan)
    return {**plan, "plan_path": str(plan_path), "plan_sha256": _sha256_file(plan_path)}


def _load_plan(plan_path: Path) -> tuple[dict[str, Any], str]:
    plan_path = plan_path.resolve(strict=True)
    plan = _read_json(plan_path)
    if plan.get("schema_version") != REPAIR_SCHEMA or plan.get("status") != "planned":
        raise CandidateRepairError("plan schema/status 不符")
    plan_hash = _sha256_file(plan_path)
    target_text = str(plan.get("target", {}).get("candidate_db", "")).strip()
    if not target_text:
        raise CandidateRepairError("plan 缺少 candidate target")
    return plan, plan_hash


def _validate_operations_against_capture(
    operations: object,
    incoming_rows: Sequence[Mapping[str, Any]],
    *,
    contract: RepairContract,
) -> list[dict[str, Any]]:
    if not isinstance(operations, list) or len(operations) != contract.operation_count:
        raise CandidateRepairError("plan operations count 不符固定 contract")
    incoming_by_key = {_key_text(row): dict(row) for row in incoming_rows}
    expected_updates = {f"{key}|{TARGET_DATE}" for key in contract.update_keys}
    expected_inserts = {f"{key}|{TARGET_DATE}" for key in contract.insert_keys}
    seen: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for operation in operations:
        if not isinstance(operation, Mapping):
            raise CandidateRepairError("plan operation 不是 object")
        key = str(operation.get("key", ""))
        if key in seen or key not in incoming_by_key:
            raise CandidateRepairError(f"plan operation key 不合法或重複: {key}")
        seen.add(key)
        after = operation.get("after")
        if not isinstance(after, Mapping) or dict(after) != incoming_by_key[key]:
            raise CandidateRepairError(f"plan operation after 與 capture 不一致: {key}")
        kind = str(operation.get("operation", ""))
        if kind == "UPDATE":
            if key not in expected_updates or not isinstance(operation.get("before"), Mapping):
                raise CandidateRepairError(f"plan UPDATE key 不符: {key}")
            before = dict(operation["before"])
            diff = _operation_diff(before, after)
            if not (set(diff) - CUSTODY_COLUMNS):
                raise CandidateRepairError(f"plan UPDATE 沒有 material change: {key}")
            if set(diff) - (CUSTODY_COLUMNS | set(NUMERIC_COLUMNS)):
                raise CandidateRepairError(f"plan UPDATE 含非允許欄位: {key}")
        elif kind == "INSERT":
            if key not in expected_inserts or operation.get("before") is not None:
                raise CandidateRepairError(f"plan INSERT key 不符: {key}")
        else:
            raise CandidateRepairError(f"plan operation type 不支援: {kind}")
        normalized.append(dict(operation))
    if seen != expected_updates | expected_inserts:
        raise CandidateRepairError("plan operation key set 不符固定 contract")
    return normalized


def _verified_sqlite_backup(source: Path, destination: Path) -> None:
    if destination.exists():
        raise CandidateRepairError(f"backup 已存在，拒絕覆寫: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    source_conn = sqlite3.connect(source)
    destination_conn = sqlite3.connect(destination)
    try:
        source_conn.backup(destination_conn)
        _integrity_check(destination_conn)
        destination_conn.commit()
    finally:
        destination_conn.close()
        source_conn.close()


def _verify_plan_capture(
    plan: Mapping[str, Any],
    plan_path: Path,
    *,
    contract: RepairContract,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    _require_plan_contract(plan, contract)
    capture_manifest_rel = str(plan.get("capture", {}).get("manifest_path_copy", ""))
    evidence_root = plan_path.parent / "capture"
    manifest_path = (plan_path.parent / capture_manifest_rel).resolve()
    if not manifest_path.is_relative_to(evidence_root.resolve()):
        raise CandidateRepairError("plan capture manifest path escape")
    _manifest, _root, rows, raw_hashes = _verify_manifest_contract(manifest_path, contract=contract)
    expected_raw = plan.get("capture", {}).get("raw_hashes")
    if expected_raw != raw_hashes:
        raise CandidateRepairError("plan capture raw hash 與 evidence 不一致")
    if _semantic_hash(rows) != plan.get("capture", {}).get("semantic_hash"):
        raise CandidateRepairError("plan capture semantic hash drift")
    return {"manifest_path": str(manifest_path), "raw_hashes": raw_hashes}, rows


def _snapshot_matches_plan(snapshot: Mapping[str, Any], plan: Mapping[str, Any]) -> None:
    target = plan.get("target")
    if not isinstance(target, Mapping):
        raise CandidateRepairError("plan target 不合法")
    if snapshot.get("target_rows_sha256") != target.get("before_target_rows_sha256"):
        raise CandidateRepairError("candidate logical target rows 已漂移")
    if snapshot.get("target_row_count") != target.get("before_row_count"):
        raise CandidateRepairError("candidate logical target row count 已漂移")
    if snapshot.get("target_table_non_target_rows_sha256") != target.get("before_target_table_non_target_rows_sha256"):
        raise CandidateRepairError("institutional_flows 非 9/11 rows 已漂移")
    if snapshot.get("non_target_tables_sha256") != target.get("before_non_target_tables_sha256"):
        raise CandidateRepairError("candidate 非目標 table scope 已漂移")
    if snapshot.get("observation_scope_sha256") != target.get("before_observation_scope_sha256"):
        raise CandidateRepairError("candidate institutional observation ledger 已漂移")
    if snapshot.get("checkpoint_non_target_scope_sha256") != target.get("before_checkpoint_non_target_scope_sha256"):
        raise CandidateRepairError("非目標 checkpoint rows 已漂移")
    if snapshot.get("checkpoint") != plan.get("checkpoint_before"):
        raise CandidateRepairError("candidate checkpoint preimage 已漂移")


def _apply_operations_and_verify(
    conn: sqlite3.Connection,
    *,
    plan: Mapping[str, Any],
    operations: Sequence[Mapping[str, Any]],
    contract: RepairContract,
    repair_id: str,
    applied_at: str,
) -> tuple[dict[str, Any], int]:
    """在已開啟的 transaction 中套用並驗證一組固定 operations。"""

    before_snapshot = _logical_snapshot(conn)
    _snapshot_matches_plan(before_snapshot, plan)
    for operation in operations:
        key = str(operation["key"])
        stock_code, decision_date = key.split("|", 1)
        before = operation.get("before")
        after = operation.get("after")
        if not isinstance(after, Mapping):
            raise CandidateRepairError(f"operation after 不合法: {key}")
        existing = conn.execute(
            f"SELECT {','.join(_quote_identifier(column) for column in TABLE_COLUMNS)} "
            f"FROM {_quote_identifier(TABLE_NAME)} WHERE stock_code=? AND decision_date=?",
            (stock_code, decision_date),
        ).fetchone()
        if operation["operation"] == "UPDATE":
            if not isinstance(before, Mapping):
                raise CandidateRepairError(f"UPDATE preimage 不符: {key}")
            if existing is None or dict(zip(TABLE_COLUMNS, existing)) != dict(before):
                raise CandidateRepairError(f"UPDATE preimage 不符: {key}")
            assignments = ",".join(
                f"{_quote_identifier(column)}=?"
                for column in TABLE_COLUMNS
                if column not in {"stock_code", "decision_date"}
            )
            values = [
                after[column]
                for column in TABLE_COLUMNS
                if column not in {"stock_code", "decision_date"}
            ]
            values.extend([stock_code, decision_date])
            cursor = conn.execute(
                f"UPDATE {_quote_identifier(TABLE_NAME)} SET {assignments} "
                "WHERE stock_code=? AND decision_date=?",
                values,
            )
            if cursor.rowcount != 1:
                raise CandidateRepairError(f"UPDATE row count 不符: {key}")
        elif operation["operation"] == "INSERT":
            if existing is not None:
                raise CandidateRepairError(f"INSERT key 已存在: {key}")
            conn.execute(
                f"INSERT INTO {_quote_identifier(TABLE_NAME)} "
                f"({','.join(_quote_identifier(column) for column in TABLE_COLUMNS)}) "
                f"VALUES ({','.join('?' for _ in TABLE_COLUMNS)})",
                [after[column] for column in TABLE_COLUMNS],
            )
        else:
            raise CandidateRepairError(f"未知 operation: {operation.get('operation')}")

    after_rows = _read_target_rows(conn)
    target = plan["target"]
    if len(after_rows) != contract.expected_source_rows:
        raise CandidateRepairError("transaction 後 target row count 不符")
    if _row_payload_hash(after_rows) != target["after_target_rows_sha256"]:
        raise CandidateRepairError("transaction 後 target rows hash 不符")
    if _scope_hash(conn, exclude_date=TARGET_DATE) != target["before_target_table_non_target_rows_sha256"]:
        raise CandidateRepairError("transaction 改動了 institutional_flows 非 9/11 rows")
    if _non_target_tables_hash(conn) != target["before_non_target_tables_sha256"]:
        raise CandidateRepairError("transaction 改動了非目標 table scope")
    if _source_observation_scope_hash(conn) != target["before_observation_scope_sha256"]:
        raise CandidateRepairError("transaction 改動了 institutional observation ledger")
    if _checkpoint_non_target_scope_hash(conn) != target["before_checkpoint_non_target_scope_sha256"]:
        raise CandidateRepairError("transaction 改動了非目標 checkpoint rows")
    if _read_checkpoint(conn) != plan["checkpoint_before"]:
        raise CandidateRepairError("transaction 內 checkpoint preimage 不符")

    history_count = _archive_repair_history(
        conn,
        repair_id=repair_id,
        operations=operations,
        capture_manifest_sha256=str(plan["capture"]["manifest_sha256"]),
        recorded_at=applied_at,
    )
    checkpoint_cursor = conn.execute(
        "UPDATE phase3c_backfill_checkpoints SET status='SUCCESS', row_count=?, fetched_at=?, error_message=NULL "
        "WHERE decision_date=? AND source=?",
        (contract.expected_source_rows, applied_at, TARGET_DATE, "institutional"),
    )
    if checkpoint_cursor.rowcount != 1:
        raise CandidateRepairError("checkpoint SUCCESS update 未影響 row")
    _integrity_check(conn)
    checkpoint_after = _read_checkpoint(conn)
    if (
        checkpoint_after["status"] != "SUCCESS"
        or checkpoint_after["row_count"] != contract.expected_source_rows
        or checkpoint_after["error_message"] is not None
    ):
        raise CandidateRepairError("transaction 後 checkpoint SUCCESS 不符")
    return checkpoint_after, history_count


def _history_rows_for_repair(conn: sqlite3.Connection, repair_id: str) -> list[sqlite3.Row]:
    if _history_table_columns(conn) != HISTORY_COLUMNS:
        raise CandidateRepairError("candidate repair history 尚未建立或 schema 不符")
    return conn.execute(
        f"SELECT {','.join(_quote_identifier(column) for column in HISTORY_COLUMNS)} "
        f"FROM {_quote_identifier(HISTORY_TABLE_NAME)} WHERE repair_id=? "
        "ORDER BY version, stock_code, decision_date",
        (repair_id,),
    ).fetchall()


def _verify_after_readback(
    target: Path,
    *,
    plan: Mapping[str, Any],
    contract: RepairContract,
    repair_id: str,
    expected_history_count: int,
) -> tuple[dict[str, Any], list[sqlite3.Row]]:
    conn = _open_candidate_readonly(target)
    try:
        _integrity_check(conn)
        rows = _read_target_rows(conn)
        if len(rows) != contract.expected_source_rows:
            raise CandidateRepairError("commit 後 target row count 不符")
        if _row_payload_hash(rows) != plan["target"]["after_target_rows_sha256"]:
            raise CandidateRepairError("commit 後 target rows hash 不符")
        if _scope_hash(conn, exclude_date=TARGET_DATE) != plan["target"]["before_target_table_non_target_rows_sha256"]:
            raise CandidateRepairError("commit 後 institutional 非目標 rows 不符")
        if _non_target_tables_hash(conn) != plan["target"]["before_non_target_tables_sha256"]:
            raise CandidateRepairError("commit 後非目標 table scope 不符")
        if _source_observation_scope_hash(conn) != plan["target"]["before_observation_scope_sha256"]:
            raise CandidateRepairError("commit 後 observation scope 不符")
        if _checkpoint_non_target_scope_hash(conn) != plan["target"]["before_checkpoint_non_target_scope_sha256"]:
            raise CandidateRepairError("commit 後非目標 checkpoint scope 不符")
        checkpoint = _read_checkpoint(conn)
        if (
            checkpoint["status"] != "SUCCESS"
            or checkpoint["row_count"] != contract.expected_source_rows
            or checkpoint["error_message"] is not None
        ):
            raise CandidateRepairError("commit 後 checkpoint readback 不符")
        history_rows = _history_rows_for_repair(conn, repair_id)
        if len(history_rows) != expected_history_count:
            raise CandidateRepairError("commit 後 repair history row count 不符")
        snapshot = _logical_snapshot(conn)
        snapshot["checkpoint"] = checkpoint
        return snapshot, history_rows
    finally:
        conn.close()


def apply_plan(
    *,
    plan_path: Path,
    confirm: str,
    production_data_root: Path,
    formal_db: Path,
    contract: RepairContract = PRODUCTION_CONTRACT,
) -> dict[str, Any]:
    """先在 SQLite online-backup staging 驗證，再套用 candidate-only repair。"""

    if confirm != APPLY_CONFIRM_TOKEN:
        raise CandidateRepairError(f"apply 必須使用 --confirm {APPLY_CONFIRM_TOKEN}")
    plan, plan_hash = _load_plan(plan_path)
    _require_plan_contract(plan, contract)
    target = _validate_candidate_target(
        Path(str(plan["target"]["candidate_db"])),
        production_data_root=production_data_root.resolve(),
        formal_db=formal_db.resolve(),
    )
    if str(target) != str(Path(str(plan["target"]["candidate_db"])).resolve()):
        raise CandidateRepairError("plan candidate target identity 不符")
    _capture_info, incoming_rows = _verify_plan_capture(
        plan, plan_path.resolve(), contract=contract
    )
    operations = _validate_operations_against_capture(
        plan.get("operations"), incoming_rows, contract=contract
    )
    receipt_dir = plan_path.resolve().parent
    receipt_path = receipt_dir / "receipt.json"
    pending_path = receipt_dir / "pending.json"
    if receipt_path.exists() or pending_path.exists():
        raise CandidateRepairError("repair receipt/pending 已存在，拒絕重播 apply")
    repair_id = str(plan.get("repair_id", "")).strip()
    if not repair_id:
        raise CandidateRepairError("plan 缺少 repair_id")
    backup_path = receipt_dir / "backup" / "phase3c_candidate_before.sqlite"
    _verified_sqlite_backup(target, backup_path)
    backup_conn = _open_candidate_readonly(backup_path)
    try:
        backup_snapshot = _logical_snapshot(backup_conn)
        _snapshot_matches_plan(backup_snapshot, plan)
    finally:
        backup_conn.close()

    staging_path = receipt_dir / "backup" / "phase3c_candidate_staging.sqlite"
    _verified_sqlite_backup(backup_path, staging_path)
    applied_at = datetime.now(timezone.utc).isoformat()
    pending = {
        "schema_version": REPAIR_SCHEMA,
        "status": "pending",
        "plan_sha256": plan_hash,
        "target_db": str(target),
        "repair_id": repair_id,
        "before_logical_snapshot": backup_snapshot,
        "backup_path": str(backup_path),
        "backup_sha256": _sha256_file(backup_path),
        "staging_path": str(staging_path),
        "staging_sha256_before": _sha256_file(staging_path),
        "created_at": applied_at,
    }
    _write_json_create_only(pending_path, pending)

    staging_conn = sqlite3.connect(staging_path)
    staging_conn.row_factory = sqlite3.Row
    try:
        _table_columns(staging_conn)
        _integrity_check(staging_conn)
        staging_conn.execute("BEGIN IMMEDIATE")
        staging_checkpoint_after, history_count = _apply_operations_and_verify(
            staging_conn,
            plan=plan,
            operations=operations,
            contract=contract,
            repair_id=repair_id,
            applied_at=applied_at,
        )
        staging_conn.commit()
    except Exception:
        staging_conn.rollback()
        raise
    finally:
        staging_conn.close()

    staging_snapshot, _staging_history = _verify_after_readback(
        staging_path,
        plan=plan,
        contract=contract,
        repair_id=repair_id,
        expected_history_count=history_count,
    )

    live_conn = sqlite3.connect(target)
    live_conn.row_factory = sqlite3.Row
    try:
        _table_columns(live_conn)
        _integrity_check(live_conn)
        live_conn.execute("BEGIN IMMEDIATE")
        live_before = _logical_snapshot(live_conn)
        _snapshot_matches_plan(live_before, plan)
        checkpoint_after, live_history_count = _apply_operations_and_verify(
            live_conn,
            plan=plan,
            operations=operations,
            contract=contract,
            repair_id=repair_id,
            applied_at=applied_at,
        )
        if live_history_count != history_count:
            raise CandidateRepairError("live/staging history row count 不一致")
        live_conn.commit()
    except Exception:
        live_conn.rollback()
        raise
    finally:
        live_conn.close()

    after_snapshot, history_rows = _verify_after_readback(
        target,
        plan=plan,
        contract=contract,
        repair_id=repair_id,
        expected_history_count=history_count,
    )
    if after_snapshot != staging_snapshot:
        raise CandidateRepairError("live commit 與 staging logical snapshot 不一致")
    if checkpoint_after != staging_checkpoint_after:
        raise CandidateRepairError("live/staging checkpoint 不一致")

    receipt = {
        "schema_version": REPAIR_SCHEMA,
        "status": "applied",
        "plan_path": str(plan_path.resolve()),
        "plan_sha256": plan_hash,
        "target_db": str(target),
        "formal_db_written": False,
        "candidate_db_written": True,
        "applied_at": applied_at,
        "repair_id": repair_id,
        "before_logical_snapshot": backup_snapshot,
        "after_logical_snapshot": after_snapshot,
        "backup_path": str(backup_path),
        "backup_sha256": _sha256_file(backup_path),
        "staging_path": str(staging_path),
        "staging_sha256_after": _sha256_file(staging_path),
        "capture": plan["capture"],
        "operations": operations,
        "checkpoint_before": plan["checkpoint_before"],
        "checkpoint_after": checkpoint_after,
        "history_rows_count": len(history_rows),
        "rollback": {
            "confirm_token": ROLLBACK_CONFIRM_TOKEN,
            "requires_current_after_target_rows_sha256": plan["target"]["after_target_rows_sha256"],
            "requires_current_checkpoint": checkpoint_after,
            "restores_only_target_operations_and_checkpoint": True,
            "backup_is_sqlite_online_backup": True,
        },
    }
    _write_json_create_only(receipt_path, receipt)
    return {**receipt, "receipt_path": str(receipt_path)}


def rollback_receipt(
    *,
    receipt_path: Path,
    confirm: str,
    production_data_root: Path,
    formal_db: Path,
) -> dict[str, Any]:
    """只回復本輪 operations/checkpoint/history，保留其他後續 candidate 寫入。"""

    if confirm != ROLLBACK_CONFIRM_TOKEN:
        raise CandidateRepairError(f"rollback 必須使用 --confirm {ROLLBACK_CONFIRM_TOKEN}")
    receipt_path = receipt_path.resolve(strict=True)
    receipt = _read_json(receipt_path)
    if receipt.get("schema_version") != REPAIR_SCHEMA or receipt.get("status") != "applied":
        raise CandidateRepairError("rollback receipt schema/status 不符")
    target = _validate_candidate_target(
        Path(str(receipt.get("target_db", ""))),
        production_data_root=production_data_root.resolve(),
        formal_db=formal_db.resolve(),
    )
    rollback_path = receipt_path.parent / "rollback_receipt.json"
    if rollback_path.exists():
        raise CandidateRepairError("rollback receipt 已存在，拒絕重播")
    backup = Path(str(receipt.get("backup_path", ""))).resolve()
    if not backup.is_file() or _sha256_file(backup) != receipt.get("backup_sha256"):
        raise CandidateRepairError("rollback backup 不存在或 hash 不符")
    repair_id = str(receipt.get("repair_id", "")).strip()
    operations = receipt.get("operations")
    if not repair_id or not isinstance(operations, list):
        raise CandidateRepairError("rollback receipt 缺少 repair_id/operations")

    conn = sqlite3.connect(target)
    conn.row_factory = sqlite3.Row
    rolled_back_at = datetime.now(timezone.utc).isoformat()
    try:
        _table_columns(conn)
        _integrity_check(conn)
        conn.execute("BEGIN IMMEDIATE")
        current_checkpoint = _read_checkpoint(conn)
        if current_checkpoint != receipt.get("checkpoint_after"):
            raise CandidateRepairError("rollback 拒絕：checkpoint 已被其他流程改寫")
        history_rows = _history_rows_for_repair(conn, repair_id)
        expected_history_count = int(receipt.get("history_rows_count", -1))
        if len(history_rows) != expected_history_count:
            raise CandidateRepairError("rollback 拒絕：本輪 history 已漂移")

        for operation in operations:
            key = str(operation.get("key", ""))
            stock_code, decision_date = key.split("|", 1)
            after = operation.get("after")
            before = operation.get("before")
            if not isinstance(after, Mapping):
                raise CandidateRepairError(f"rollback after 不合法: {key}")
            current = conn.execute(
                f"SELECT {','.join(_quote_identifier(column) for column in TABLE_COLUMNS)} "
                f"FROM {_quote_identifier(TABLE_NAME)} WHERE stock_code=? AND decision_date=?",
                (stock_code, decision_date),
            ).fetchone()
            if operation.get("operation") == "UPDATE":
                if current is None or dict(zip(TABLE_COLUMNS, current)) != dict(after):
                    raise CandidateRepairError(f"rollback UPDATE after preimage 不符: {key}")
                if not isinstance(before, Mapping):
                    raise CandidateRepairError(f"rollback UPDATE before 不合法: {key}")
                assignments = ",".join(
                    f"{_quote_identifier(column)}=?"
                    for column in TABLE_COLUMNS
                    if column not in {"stock_code", "decision_date"}
                )
                values = [
                    before[column]
                    for column in TABLE_COLUMNS
                    if column not in {"stock_code", "decision_date"}
                ]
                values.extend([stock_code, decision_date])
                cursor = conn.execute(
                    f"UPDATE {_quote_identifier(TABLE_NAME)} SET {assignments} "
                    "WHERE stock_code=? AND decision_date=?",
                    values,
                )
                if cursor.rowcount != 1:
                    raise CandidateRepairError(f"rollback UPDATE row count 不符: {key}")
            elif operation.get("operation") == "INSERT":
                if current is None or dict(zip(TABLE_COLUMNS, current)) != dict(after):
                    raise CandidateRepairError(f"rollback INSERT after preimage 不符: {key}")
                cursor = conn.execute(
                    f"DELETE FROM {_quote_identifier(TABLE_NAME)} WHERE stock_code=? AND decision_date=?",
                    (stock_code, decision_date),
                )
                if cursor.rowcount != 1:
                    raise CandidateRepairError(f"rollback INSERT delete row count 不符: {key}")
            else:
                raise CandidateRepairError(f"rollback operation type 不支援: {operation.get('operation')}")

        cursor = conn.execute(
            "UPDATE phase3c_backfill_checkpoints SET status=?, row_count=?, fetched_at=?, error_message=? "
            "WHERE decision_date=? AND source=?",
            (
                receipt["checkpoint_before"]["status"],
                receipt["checkpoint_before"]["row_count"],
                receipt["checkpoint_before"]["fetched_at"],
                receipt["checkpoint_before"]["error_message"],
                TARGET_DATE,
                "institutional",
            ),
        )
        if cursor.rowcount != 1:
            raise CandidateRepairError("rollback checkpoint update 未影響 row")
        deleted = conn.execute(
            f"DELETE FROM {_quote_identifier(HISTORY_TABLE_NAME)} WHERE repair_id=?",
            (repair_id,),
        )
        if deleted.rowcount != expected_history_count:
            raise CandidateRepairError("rollback history delete row count 不符")
        _integrity_check(conn)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    restored = _open_candidate_readonly(target)
    try:
        _integrity_check(restored)
        rows = _read_target_rows(restored)
        if _row_payload_hash(rows) != receipt["before_logical_snapshot"]["target_rows_sha256"]:
            raise CandidateRepairError("rollback 後 target rows 不等於 before")
        checkpoint = _read_checkpoint(restored)
        if checkpoint != receipt["checkpoint_before"]:
            raise CandidateRepairError("rollback 後 checkpoint 不等於 before")
        if _history_table_columns(restored) != HISTORY_COLUMNS:
            raise CandidateRepairError("rollback 後 history schema 不符")
        remaining = restored.execute(
            f"SELECT COUNT(*) FROM {_quote_identifier(HISTORY_TABLE_NAME)} WHERE repair_id=?",
            (repair_id,),
        ).fetchone()
        if remaining is None or int(remaining[0]) != 0:
            raise CandidateRepairError("rollback 後仍有本輪 history rows")
    finally:
        restored.close()
    rollback = {
        "schema_version": REPAIR_SCHEMA,
        "status": "rolled_back",
        "receipt_path": str(receipt_path),
        "target_db": str(target),
        "repair_id": repair_id,
        "rolled_back_at": rolled_back_at,
        "restored_target_rows_sha256": receipt["before_logical_snapshot"]["target_rows_sha256"],
        "restored_checkpoint": receipt["checkpoint_before"],
        "formal_db_written": False,
        "restored_only_target_operations_checkpoint_history": True,
    }
    _write_json_create_only(rollback_path, rollback)
    return {**rollback, "rollback_receipt_path": str(rollback_path)}
