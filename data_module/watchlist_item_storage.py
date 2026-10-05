"""Watchlist v3 的 immutable item object 與稀疏 revision event 儲存。"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any, Callable, Iterator, Mapping, Sequence


STORAGE_FORMAT = "watchlist-item-events.v1"
SCHEMA_VERSION = 3
MAX_PAYLOAD_BYTES = 4 * 1024 * 1024
MAX_DATABASE_BYTES = 32 * 1024 * 1024
MAX_SCAN_BYTES = 64 * 1024 * 1024
MAX_ROWS = 4096


class WatchlistStorageIntegrityError(ValueError):
    """儲存格式或其內容無法安全驗證。"""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(detail or code)
        self.code = code


class WatchlistStorageCapacityError(RuntimeError):
    """儲存寫入無法通過明確容量檢查。"""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(detail or code)
        self.code = code


@dataclass(frozen=True)
class WatchlistWriteCapacityRequest:
    db_path: Path
    operation: str
    payload_bytes_after: int
    rows_after: int
    database_bytes_before: int
    sidecar_bytes_before: int
    estimated_database_growth_bytes: int
    required_peak_bytes: int
    max_payload_bytes: int = MAX_PAYLOAD_BYTES
    max_database_bytes: int = MAX_DATABASE_BYTES
    max_scan_bytes: int = MAX_SCAN_BYTES


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False,
                      separators=(",", ":"))


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


_TABLE_COLUMNS: dict[str, tuple[str, ...]] = {
    "watchlists": ("watchlist_id", "payload_json", "revision", "source_hash",
                   "is_deleted", "last_revision_id"),
    "watchlist_storage_meta": ("storage_format", "schema_version"),
    "watchlist_item_objects": ("object_hash", "item_json", "payload_bytes"),
    "watchlist_revisions_v3": (
        "revision_id", "watchlist_id", "revision", "operation", "payload_hash",
        "source_hash", "identity_status", "continuity_event_id", "revision_of",
        "created_at", "is_deleted", "header_json", "delta_hash", "chain_hash",
    ),
    "watchlist_revision_events": (
        "event_id", "watchlist_id", "revision", "revision_id", "event_json",
        "event_hash",
    ),
    "watchlist_current_items": ("watchlist_id", "position", "object_hash"),
}


def table_names(conn: sqlite3.Connection) -> set[str]:
    return {str(row[0]) for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    )}


def validate_schema(conn: sqlite3.Connection) -> None:
    names = table_names(conn)
    if names != set(_TABLE_COLUMNS):
        raise WatchlistStorageIntegrityError("unknown_schema_tables")
    for name, expected in _TABLE_COLUMNS.items():
        actual = tuple(str(row[1]) for row in conn.execute(f"PRAGMA table_info({name})"))
        if actual != expected:
            raise WatchlistStorageIntegrityError("unknown_schema_columns", name)
    marker = conn.execute(
        "SELECT storage_format,schema_version FROM watchlist_storage_meta"
    ).fetchall()
    if marker != [(STORAGE_FORMAT, SCHEMA_VERSION)]:
        raise WatchlistStorageIntegrityError("unknown_schema_marker")


def initialize_schema(conn: sqlite3.Connection) -> None:
    """只建立新 v3 schema；呼叫端須先確認 DB 不含任何資料表。"""
    conn.execute("""CREATE TABLE watchlists (
        watchlist_id TEXT PRIMARY KEY, payload_json TEXT NOT NULL, revision INTEGER NOT NULL,
        source_hash TEXT NOT NULL DEFAULT '', is_deleted INTEGER NOT NULL DEFAULT 0,
        last_revision_id TEXT NOT NULL DEFAULT '')""")
    conn.execute("CREATE TABLE watchlist_storage_meta (storage_format TEXT NOT NULL, schema_version INTEGER NOT NULL)")
    conn.execute("INSERT INTO watchlist_storage_meta VALUES (?,?)", (STORAGE_FORMAT, SCHEMA_VERSION))
    conn.execute("""CREATE TABLE watchlist_item_objects (
        object_hash TEXT PRIMARY KEY, item_json TEXT NOT NULL, payload_bytes INTEGER NOT NULL)""")
    conn.execute("""CREATE TABLE watchlist_revisions_v3 (
        revision_id TEXT PRIMARY KEY, watchlist_id TEXT NOT NULL, revision INTEGER NOT NULL,
        operation TEXT NOT NULL, payload_hash TEXT NOT NULL, source_hash TEXT NOT NULL,
        identity_status TEXT NOT NULL, continuity_event_id TEXT NOT NULL, revision_of TEXT NOT NULL,
        created_at TEXT NOT NULL, is_deleted INTEGER NOT NULL, header_json TEXT NOT NULL,
        delta_hash TEXT NOT NULL, chain_hash TEXT NOT NULL, UNIQUE(watchlist_id,revision))""")
    conn.execute("CREATE INDEX idx_watchlist_revisions_v3_watchlist ON watchlist_revisions_v3(watchlist_id,revision)")
    conn.execute("""CREATE TABLE watchlist_revision_events (
        event_id TEXT PRIMARY KEY, watchlist_id TEXT NOT NULL, revision INTEGER NOT NULL,
        revision_id TEXT NOT NULL, event_json TEXT NOT NULL, event_hash TEXT NOT NULL)""")
    conn.execute("CREATE INDEX idx_watchlist_revision_events_revision ON watchlist_revision_events(watchlist_id,revision)")
    conn.execute("""CREATE TABLE watchlist_current_items (
        watchlist_id TEXT NOT NULL, position INTEGER NOT NULL, object_hash TEXT NOT NULL,
        PRIMARY KEY(watchlist_id,position))""")
    validate_schema(conn)


def _item_key_tokens(items: Sequence[Mapping[str, Any]]) -> list[str]:
    occurrences: dict[tuple[str, str, str], int] = {}
    result: list[str] = []
    for item in items:
        identity = (str(item.get("stock_code", "") or ""),
                    str(item.get("source", "") or ""),
                    str(item.get("source_id", "") or ""))
        occurrence = occurrences.get(identity, 0)
        occurrences[identity] = occurrence + 1
        result.append(canonical_json([*identity, occurrence]))
    return result


def _decode_item(raw: str, expected_hash: str) -> dict[str, Any]:
    if sha256_text(raw) != expected_hash:
        raise WatchlistStorageIntegrityError("object_hash_mismatch")
    value = json.loads(raw)
    if not isinstance(value, dict) or canonical_json(value) != raw:
        raise WatchlistStorageIntegrityError("invalid_item_object")
    return value


def _event_hash(event_json: str) -> str:
    return sha256_text(event_json)


def storage_stats(conn: sqlite3.Connection, *, max_scan_bytes: int = MAX_SCAN_BYTES) -> dict[str, Any]:
    """先以 SQL length/count 做有界檢查，再回傳目前帳面大小。"""
    validate_schema(conn)
    row_counts = {name: int(conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0])
                  for name in _TABLE_COLUMNS}
    if sum(row_counts.values()) > MAX_ROWS:
        raise WatchlistStorageCapacityError("row_limit_exceeded")
    lengths = {
        "current": int(conn.execute("SELECT COALESCE(SUM(length(CAST(payload_json AS BLOB))),0) FROM watchlists").fetchone()[0]),
        "objects": int(conn.execute("SELECT COALESCE(SUM(length(CAST(item_json AS BLOB))),0) FROM watchlist_item_objects").fetchone()[0]),
        "headers": int(conn.execute("SELECT COALESCE(SUM(length(CAST(header_json AS BLOB))),0) FROM watchlist_revisions_v3").fetchone()[0]),
        "events": int(conn.execute("SELECT COALESCE(SUM(length(CAST(event_json AS BLOB))),0) FROM watchlist_revision_events").fetchone()[0]),
    }
    payload_bytes = sum(lengths.values())
    scanned_bytes = payload_bytes
    for table, columns in {
        "watchlists": ("watchlist_id", "source_hash", "last_revision_id"),
        "watchlist_storage_meta": ("storage_format",),
        "watchlist_item_objects": ("object_hash",),
        "watchlist_revisions_v3": (
            "revision_id", "watchlist_id", "operation", "payload_hash", "source_hash",
            "identity_status", "continuity_event_id", "revision_of", "created_at",
            "header_json", "delta_hash", "chain_hash",
        ),
        "watchlist_revision_events": ("event_id", "watchlist_id", "revision_id", "event_json", "event_hash"),
        "watchlist_current_items": ("watchlist_id", "object_hash"),
    }.items():
        expression = "+".join(f"length(CAST({column} AS BLOB))" for column in columns)
        scanned_bytes += int(conn.execute(f"SELECT COALESCE(SUM({expression}),0) FROM {table}").fetchone()[0])
    if scanned_bytes > max_scan_bytes:
        raise WatchlistStorageCapacityError("scan_limit_exceeded")
    page_count = int(conn.execute("PRAGMA page_count").fetchone()[0])
    page_size = int(conn.execute("PRAGMA page_size").fetchone()[0])
    database_bytes = page_count * page_size
    if database_bytes > MAX_DATABASE_BYTES:
        raise WatchlistStorageCapacityError("database_limit_exceeded")
    return {"payload_bytes": payload_bytes, "scanned_bytes": scanned_bytes,
            "row_counts": row_counts, "database_bytes": database_bytes,
            "lengths": lengths}


def save_v3(
    conn: sqlite3.Connection,
    *, watchlist_id: str, payload: Mapping[str, Any], revision_id: str,
    operation: str, source_hash: str, identity_status: str,
    continuity_event_id: str, revision_of: str, created_at: str,
    expected_revision: int | None, before_commit: Callable[[str, str], None] | None = None,
    plan_only: bool = False,
) -> tuple[int, int, int]:
    """在呼叫端交易內寫入一個稀疏 revision；回傳 revision、payload bytes、row 數。"""
    validate_schema(conn)
    stats = storage_stats(conn)
    raw = canonical_json(dict(payload))
    if "items" not in payload:
        raise WatchlistStorageIntegrityError("missing_items_payload")
    items_value = payload.get("items")
    if not isinstance(items_value, list) or any(not isinstance(x, Mapping) for x in items_value):
        raise WatchlistStorageIntegrityError("invalid_items_payload")
    items = [dict(item) for item in items_value]
    keys = _item_key_tokens(items)
    item_raws = [canonical_json(item) for item in items]
    hashes = [sha256_text(item_raw) for item_raw in item_raws]
    new_hash_set = set(hashes)
    stored = conn.execute(
        "SELECT revision_id,watchlist_id,revision,operation,payload_hash,source_hash,"
        "identity_status,continuity_event_id,revision_of,created_at,is_deleted,header_json "
        "FROM watchlist_revisions_v3 WHERE revision_id=?", (revision_id,)
    ).fetchone()
    payload_hash = sha256_text(raw)
    is_deleted = False
    if stored is not None:
        if (str(stored[1]) != watchlist_id or str(stored[3]) != operation
                or str(stored[4]) != payload_hash or str(stored[5]) != source_hash
                or str(stored[6]) != identity_status or str(stored[7]) != continuity_event_id
                or (revision_of and str(stored[8]) != revision_of)):
            raise RuntimeError("watchlist_revision_event_conflict")
        return int(stored[2]), stats["payload_bytes"], sum(stats["row_counts"].values())

    current_row = conn.execute(
        "SELECT payload_json,revision,source_hash,is_deleted,last_revision_id FROM watchlists WHERE watchlist_id=?",
        (watchlist_id,),
    ).fetchone()
    actual = None if current_row is None else int(current_row[1])
    if actual != expected_revision:
        raise RuntimeError("watchlist_revision_conflict")
    prior_revision_id = "" if current_row is None else str(current_row[4] or "")
    if revision_of and revision_of != prior_revision_id:
        raise RuntimeError("watchlist_revision_conflict")
    current_refs = conn.execute(
        "SELECT ci.position,ci.object_hash,io.item_json FROM watchlist_current_items ci "
        "JOIN watchlist_item_objects io USING(object_hash) WHERE ci.watchlist_id=? ORDER BY ci.position",
        (watchlist_id,),
    ).fetchall()
    old_hashes = [str(row[1]) for row in current_refs]
    old_items = [_decode_item(str(row[2]), str(row[1])) for row in current_refs]
    old_keys = _item_key_tokens(old_items)
    old_by_key = dict(zip(old_keys, old_hashes))
    new_by_key = dict(zip(keys, hashes))
    events: list[dict[str, Any]] = []
    for key in old_keys:
        if key not in new_by_key:
            events.append({"kind": "remove", "key": json.loads(key)})
    for key, object_hash in new_by_key.items():
        old_hash = old_by_key.get(key)
        if old_hash is None:
            events.append({"kind": "add", "key": json.loads(key), "object_hash": object_hash})
        elif old_hash != object_hash:
            events.append({"kind": "replace", "key": json.loads(key), "object_hash": object_hash})
    replay_order = [key for key in old_keys if key in new_by_key]
    replay_order.extend(key for key in keys if key not in old_by_key)
    if replay_order != keys:
        events.append({"kind": "order", "items": [[json.loads(key), new_by_key[key]] for key in keys]})
    event_pairs = [(event, canonical_json(event)) for event in events]
    event_hashes = [_event_hash(encoded) for _, encoded in event_pairs]
    delta_hash = sha256_text(canonical_json(event_hashes))
    revision = (actual or 0) + 1
    revision_of_value = revision_of or prior_revision_id
    header = {
        "operation": operation, "source_hash": source_hash,
        "identity_status": identity_status, "continuity_event_id": continuity_event_id,
        "revision_of": revision_of_value, "created_at": created_at,
        "is_deleted": is_deleted,
        "payload_envelope": {key: value for key, value in payload.items() if key != "items"},
        "watchlist_id": watchlist_id, "revision_id": revision_id,
        "revision_number": revision, "payload_hash": payload_hash,
    }
    header_json = canonical_json(header)
    previous_chain = ""
    if actual is not None:
        previous_chain = str(conn.execute(
            "SELECT chain_hash FROM watchlist_revisions_v3 WHERE watchlist_id=? AND revision=?",
            (watchlist_id, actual),
        ).fetchone()[0])
    chain_hash = sha256_text(previous_chain + header_json + delta_hash)
    added_object_bytes = 0
    counted_new_hashes: set[str] = set()
    for item_raw, object_hash in zip(item_raws, hashes):
        if object_hash in counted_new_hashes:
            continue
        counted_new_hashes.add(object_hash)
        if object_hash in new_hash_set:
            existing_object = conn.execute(
                "SELECT item_json FROM watchlist_item_objects WHERE object_hash=?", (object_hash,)
            ).fetchone()
            if existing_object is None:
                added_object_bytes += len(item_raw.encode("utf-8"))
    event_bytes = sum(len(encoded.encode("utf-8")) for _, encoded in event_pairs)
    header_bytes = len(header_json.encode("utf-8"))
    new_payload_total = (stats["payload_bytes"] - (0 if current_row is None else len(str(current_row[0]).encode("utf-8")))
                         + len(raw.encode("utf-8")) + added_object_bytes + event_bytes + header_bytes)
    if new_payload_total > MAX_PAYLOAD_BYTES:
        raise WatchlistStorageCapacityError("payload_limit_exceeded")
    new_row_count = sum(stats["row_counts"].values())
    new_row_count += (1 if current_row is None else 0) + 1 + len(event_pairs) + len(items) - len(current_refs)
    new_row_count += sum(1 for h in set(hashes) if conn.execute(
        "SELECT 1 FROM watchlist_item_objects WHERE object_hash=?", (h,)
    ).fetchone() is None)
    if new_row_count > MAX_ROWS:
        raise WatchlistStorageCapacityError("row_limit_exceeded")

    if plan_only:
        return revision, new_payload_total, new_row_count

    for item_raw, object_hash in zip(item_raws, hashes):
        existing_object = conn.execute(
            "SELECT item_json FROM watchlist_item_objects WHERE object_hash=?", (object_hash,)
        ).fetchone()
        if existing_object is not None:
            _decode_item(str(existing_object[0]), object_hash)
        conn.execute(
            "INSERT OR IGNORE INTO watchlist_item_objects(object_hash,item_json,payload_bytes) VALUES(?,?,?)",
            (object_hash, item_raw, len(item_raw.encode("utf-8"))),
        )
    for index, (event, event_json) in enumerate(event_pairs):
        conn.execute(
            "INSERT INTO watchlist_revision_events VALUES(?,?,?,?,?,?)",
            (f"{revision_id}:{index}", watchlist_id, revision, revision_id, event_json, event_hashes[index]),
        )
    conn.execute(
        "INSERT INTO watchlist_revisions_v3 VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (revision_id, watchlist_id, revision, operation, payload_hash, source_hash,
         identity_status, continuity_event_id, revision_of_value, created_at, 0,
         header_json, delta_hash, chain_hash),
    )
    conn.execute(
        "INSERT INTO watchlists VALUES(?,?,?,?,0,?) ON CONFLICT(watchlist_id) DO UPDATE SET "
        "payload_json=excluded.payload_json,revision=excluded.revision,source_hash=excluded.source_hash,"
        "is_deleted=0,last_revision_id=excluded.last_revision_id",
        (watchlist_id, raw, revision, source_hash, revision_id),
    )
    conn.execute("DELETE FROM watchlist_current_items WHERE watchlist_id=?", (watchlist_id,))
    conn.executemany(
        "INSERT INTO watchlist_current_items VALUES(?,?,?)",
        [(watchlist_id, position, object_hash) for position, object_hash in enumerate(hashes)],
    )
    if before_commit is not None:
        before_commit(operation, revision_id)
    return revision, new_payload_total, new_row_count


def delete_v3(
    conn: sqlite3.Connection, *, watchlist_id: str, expected_revision: int,
    revision_id: str, operation: str, continuity_event_id: str, identity_status: str,
    revision_of: str, created_at: str,
    before_commit: Callable[[str, str], None] | None = None,
) -> bool:
    validate_schema(conn)
    stats = storage_stats(conn)
    duplicate = conn.execute(
        "SELECT watchlist_id,operation,payload_hash,source_hash,identity_status,"
        "continuity_event_id,revision_of,is_deleted FROM watchlist_revisions_v3 WHERE revision_id=?",
        (revision_id,),
    ).fetchone()
    if duplicate is not None:
        current_row = conn.execute("SELECT payload_json,source_hash FROM watchlists WHERE watchlist_id=?", (watchlist_id,)).fetchone()
        if current_row is None:
            raise RuntimeError("watchlist_revision_event_conflict")
        same = (str(duplicate[0]) == watchlist_id and str(duplicate[1]) == operation
                and str(duplicate[2]) == sha256_text(str(current_row[0]))
                and str(duplicate[3] or "") == str(current_row[1] or "")
                and str(duplicate[4]) == identity_status
                and str(duplicate[5] or "") == continuity_event_id
                and (not revision_of or str(duplicate[6] or "") == revision_of)
                and bool(duplicate[7]))
        if not same:
            raise RuntimeError("watchlist_revision_event_conflict")
        return True
    current = conn.execute(
        "SELECT payload_json,revision,source_hash,last_revision_id,is_deleted FROM watchlists WHERE watchlist_id=?",
        (watchlist_id,),
    ).fetchone()
    if current is None:
        return False
    if int(current[1]) != expected_revision:
        raise RuntimeError("watchlist_revision_conflict")
    prior_revision = str(current[3] or "")
    if revision_of and revision_of != prior_revision:
        raise RuntimeError("watchlist_revision_conflict")
    payload_raw = str(current[0])
    payload = json.loads(payload_raw)
    payload_hash = sha256_text(payload_raw)
    revision = expected_revision + 1
    header = {"operation": operation, "source_hash": str(current[2] or ""),
              "identity_status": identity_status, "continuity_event_id": continuity_event_id,
              "revision_of": revision_of or prior_revision, "created_at": created_at,
              "is_deleted": True, "payload_envelope": {key: value for key, value in payload.items() if key != "items"},
              "watchlist_id": watchlist_id, "revision_id": revision_id,
              "revision_number": revision, "payload_hash": payload_hash}
    header_json = canonical_json(header)
    delta_hash = sha256_text(canonical_json([]))
    prior_chain_row = conn.execute(
        "SELECT chain_hash FROM watchlist_revisions_v3 WHERE watchlist_id=? AND revision=?",
        (watchlist_id, expected_revision),
    ).fetchone()
    prior_chain = "" if prior_chain_row is None else str(prior_chain_row[0])
    chain_hash = sha256_text(prior_chain + header_json + delta_hash)
    new_total = stats["payload_bytes"] + len(header_json.encode("utf-8"))
    new_rows = sum(stats["row_counts"].values()) + 1
    if new_total > MAX_PAYLOAD_BYTES:
        raise WatchlistStorageCapacityError("payload_limit_exceeded")
    if new_rows > MAX_ROWS:
        raise WatchlistStorageCapacityError("row_limit_exceeded")
    conn.execute(
        "INSERT INTO watchlist_revisions_v3 VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (revision_id, watchlist_id, revision, operation, payload_hash, str(current[2] or ""),
         identity_status, continuity_event_id, revision_of or prior_revision, created_at,
         1, header_json, delta_hash, chain_hash),
    )
    conn.execute(
        "UPDATE watchlists SET revision=?,is_deleted=1,last_revision_id=? WHERE watchlist_id=? AND revision=?",
        (revision, revision_id, watchlist_id, expected_revision),
    )
    if before_commit is not None:
        before_commit(operation, revision_id)
    return True


def _validate_header(
    header: Mapping[str, Any], watchlist_id: str, revision_id: str, revision: int,
    operation: str, payload_hash: str, source_hash: str, identity_status: str,
    continuity_event_id: str, revision_of: str, created_at: str, is_deleted: bool,
) -> None:
    expected = {
        "watchlist_id": watchlist_id, "revision_id": revision_id,
        "revision_number": revision, "operation": operation,
        "payload_hash": payload_hash, "source_hash": source_hash,
        "identity_status": identity_status,
        "continuity_event_id": continuity_event_id, "revision_of": revision_of,
        "created_at": created_at, "is_deleted": is_deleted,
    }
    for key, value in expected.items():
        if header.get(key) != value:
            raise WatchlistStorageIntegrityError("revision_header_mismatch", key)
    if not isinstance(header.get("payload_envelope"), dict):
        raise WatchlistStorageIntegrityError("invalid_payload_envelope")


def iter_revisions(conn: sqlite3.Connection, watchlist_id: str, *, include_payload: bool = True) -> Iterator[dict[str, Any]]:
    """單次增量 replay；每次最多保留一份完整 payload。"""
    storage_stats(conn)
    validate_schema(conn)
    object_cache: dict[str, dict[str, Any]] = {}
    for object_hash, item_json in conn.execute(
        "SELECT object_hash,item_json FROM watchlist_item_objects"
    ):
        object_cache[str(object_hash)] = _decode_item(str(item_json), str(object_hash))
    event_cache: dict[int, list[tuple[str, str, str, str]]] = {}
    for event_id, revision, revision_id, event_json, event_hash in conn.execute(
        "SELECT event_id,revision,revision_id,event_json,event_hash FROM watchlist_revision_events "
        "WHERE watchlist_id=? ORDER BY rowid", (watchlist_id,)
    ):
        event_cache.setdefault(int(revision), []).append((str(event_id), str(revision_id), str(event_json), str(event_hash)))
    rows = conn.execute(
        "SELECT revision_id,watchlist_id,revision,operation,payload_hash,source_hash,"
        "identity_status,continuity_event_id,revision_of,created_at,is_deleted,header_json,delta_hash,chain_hash "
        "FROM watchlist_revisions_v3 WHERE watchlist_id=? ORDER BY revision", (watchlist_id,)
    )
    current: dict[str, str] = {}
    order: list[str] = []
    previous_chain = ""
    expected_revision = 1
    for row in rows:
        (revision_id, wid, revision, operation, payload_hash, source_hash, identity_status,
         event_id, revision_of, created_at, deleted, header_json, delta_hash, chain_hash) = row
        if int(revision) != expected_revision:
            raise WatchlistStorageIntegrityError("revision_sequence_mismatch")
        header = json.loads(str(header_json))
        if not isinstance(header, dict) or canonical_json(header) != str(header_json):
            raise WatchlistStorageIntegrityError("invalid_revision_header")
        _validate_header(header, str(wid), str(revision_id), int(revision), str(operation),
                         str(payload_hash), str(source_hash or ""), str(identity_status or "unknown"),
                         str(event_id or ""), str(revision_of or ""), str(created_at), bool(deleted))
        event_rows = event_cache.pop(int(revision), [])
        events: list[dict[str, Any]] = []
        hashes: list[str] = []
        for event_index, (event_id, event_revision_id, event_raw, event_hash) in enumerate(event_rows):
            if event_revision_id != str(revision_id):
                raise WatchlistStorageIntegrityError("event_revision_ref_mismatch")
            if event_id != f"{revision_id}:{event_index}":
                raise WatchlistStorageIntegrityError("invalid_event_order")
            if _event_hash(event_raw) != str(event_hash):
                raise WatchlistStorageIntegrityError("event_hash_mismatch")
            event = json.loads(event_raw)
            if not isinstance(event, dict) or canonical_json(event) != event_raw:
                raise WatchlistStorageIntegrityError("invalid_event")
            events.append(event)
            hashes.append(str(event_hash))
        if sha256_text(canonical_json(hashes)) != str(delta_hash):
            raise WatchlistStorageIntegrityError("delta_hash_mismatch")
        calculated_chain = sha256_text(previous_chain + str(header_json) + str(delta_hash))
        if calculated_chain != str(chain_hash):
            raise WatchlistStorageIntegrityError("revision_chain_hash_mismatch")
        for event in events:
            kind = event.get("kind")
            key = canonical_json(event.get("key")) if "key" in event else ""
            if kind == "remove":
                if set(event) != {"kind", "key"}:
                    raise WatchlistStorageIntegrityError("unknown_delta_fields")
                if key not in current:
                    raise WatchlistStorageIntegrityError("delta_remove_ref_missing")
                del current[key]
                order.remove(key)
            elif kind in {"add", "replace"}:
                if set(event) != {"kind", "key", "object_hash"}:
                    raise WatchlistStorageIntegrityError("unknown_delta_fields")
                object_hash = str(event.get("object_hash", ""))
                item = object_cache.get(object_hash)
                if item is None:
                    raise WatchlistStorageIntegrityError("delta_object_ref_missing")
                _validate_key_identity(event.get("key"), item)
                if kind == "add":
                    if key in current:
                        raise WatchlistStorageIntegrityError("delta_add_duplicate")
                    order.append(key)
                elif key not in current:
                    raise WatchlistStorageIntegrityError("delta_replace_ref_missing")
                current[key] = object_hash
            elif kind == "order":
                if set(event) != {"kind", "items"}:
                    raise WatchlistStorageIntegrityError("unknown_delta_fields")
                raw_items = event.get("items")
                if not isinstance(raw_items, list):
                    raise WatchlistStorageIntegrityError("invalid_order_event")
                order = []
                ordered: dict[str, str] = {}
                for pair in raw_items:
                    if not isinstance(pair, list) or len(pair) != 2:
                        raise WatchlistStorageIntegrityError("invalid_order_event")
                    token, object_hash = canonical_json(pair[0]), str(pair[1])
                    ordered_item = object_cache.get(object_hash)
                    if ordered_item is None:
                        raise WatchlistStorageIntegrityError("delta_object_ref_missing")
                    _validate_key_identity(pair[0], ordered_item)
                    if token not in current:
                        raise WatchlistStorageIntegrityError("order_ref_missing")
                    if object_hash not in object_cache:
                        raise WatchlistStorageIntegrityError("delta_object_ref_missing")
                    ordered[token] = object_hash
                    order.append(token)
                if set(ordered) != set(current) or len(ordered) != len(raw_items):
                    raise WatchlistStorageIntegrityError("invalid_order_event")
                current = ordered
            else:
                raise WatchlistStorageIntegrityError("unknown_delta_event")
        envelope = header.get("payload_envelope", {})
        if not isinstance(envelope, dict):
            raise WatchlistStorageIntegrityError("invalid_payload_envelope")
        current_payload_raw = _payload_from_refs(conn, current, order, envelope, object_cache)
        if sha256_text(current_payload_raw) != str(payload_hash):
            raise WatchlistStorageIntegrityError("revision_payload_hash_mismatch")
        result: dict[str, Any] = {
            "revision_id": str(revision_id), "watchlist_id": str(wid), "revision": int(revision),
            "operation": str(operation), "payload_hash": str(payload_hash),
            "source_hash": str(source_hash or ""), "identity_status": str(identity_status or "unknown"),
            "continuity_event_id": str(event_id or ""), "revision_of": str(revision_of or ""),
            "created_at": str(created_at), "is_deleted": bool(deleted), "header": header,
        }
        if include_payload:
            result["payload"] = json.loads(current_payload_raw)
        yield result
        previous_chain = str(chain_hash)
        expected_revision += 1
    if event_cache:
        raise WatchlistStorageIntegrityError("orphan_event")


def _payload_from_refs(
    conn: sqlite3.Connection, objects: Mapping[str, str], order: list[str],
    envelope: Mapping[str, Any] | None = None,
    object_cache: Mapping[str, dict[str, Any]] | None = None,
) -> str:
    items: list[dict[str, Any]] = []
    for token in order:
        object_hash = objects[token]
        item = None if object_cache is None else object_cache.get(object_hash)
        if item is None and object_cache is None:
            row = conn.execute("SELECT item_json FROM watchlist_item_objects WHERE object_hash=?", (object_hash,)).fetchone()
            item = None if row is None else _decode_item(str(row[0]), object_hash)
        if item is None:
            raise WatchlistStorageIntegrityError("delta_object_ref_missing")
        items.append(item)
    # 未知的頂層 payload 欄位逐 revision 保存在小型 header，不複製 item references。
    payload = dict(envelope or {})
    payload["items"] = items
    return canonical_json(payload)


def inventory(conn: sqlite3.Connection, *, max_scan_bytes: int = MAX_SCAN_BYTES) -> dict[str, Any]:
    """有界驗證 v3 物件、增量 refs、chain 與 current projection。"""
    stats = storage_stats(conn, max_scan_bytes=max_scan_bytes)
    result: dict[str, Any] = {
        "complete": False, "schema_valid": True, "object_hashes_valid": False,
        "delta_refs_valid": False, "revision_chain_valid": False,
        "current_projection_valid": False, "historical_payload_hashes_verified": False,
        "schema_version": SCHEMA_VERSION, "storage_format": STORAGE_FORMAT,
        "payload_bytes": stats["payload_bytes"], "scanned_bytes": stats["scanned_bytes"],
        "row_counts": stats["row_counts"], "objects": [], "events": [],
        "revisions": [], "watchlists": [], "errors": [],
    }

    object_cache: dict[str, dict[str, Any]] = {}
    objects: list[dict[str, Any]] = []
    for object_hash, item_json, byte_count in conn.execute(
        "SELECT object_hash,item_json,payload_bytes FROM watchlist_item_objects ORDER BY object_hash"
    ):
        object_hash, item_json = str(object_hash), str(item_json)
        item = _decode_item(item_json, object_hash)
        if int(byte_count) != len(item_json.encode("utf-8")):
            raise WatchlistStorageIntegrityError("object_size_mismatch")
        object_cache[object_hash] = item
        objects.append({"object_hash": object_hash, "item": item,
                        "payload_bytes": int(byte_count), "reference_count": 0})
    result["object_hashes_valid"] = True
    object_rows = {item["object_hash"]: item for item in objects}

    event_groups: dict[tuple[str, int], list[dict[str, Any]]] = {}
    event_output: list[dict[str, Any]] = []
    for event_id, watchlist_id, revision, revision_id, event_json, event_hash in conn.execute(
        "SELECT event_id,watchlist_id,revision,revision_id,event_json,event_hash "
        "FROM watchlist_revision_events ORDER BY watchlist_id,revision,rowid"
    ):
        raw = str(event_json)
        if sha256_text(raw) != str(event_hash):
            raise WatchlistStorageIntegrityError("event_hash_mismatch")
        event = json.loads(raw)
        if not isinstance(event, dict) or canonical_json(event) != raw:
            raise WatchlistStorageIntegrityError("invalid_event")
        record = {"event_id": str(event_id), "watchlist_id": str(watchlist_id),
                  "revision": int(revision), "revision_id": str(revision_id),
                  "event": event, "event_hash": str(event_hash)}
        event_groups.setdefault((str(watchlist_id), int(revision)), []).append(record)
        event_output.append(record)
    result["events"] = event_output

    revision_rows = conn.execute(
        "SELECT revision_id,watchlist_id,revision,operation,payload_hash,source_hash,identity_status,"
        "continuity_event_id,revision_of,created_at,is_deleted,header_json,delta_hash,chain_hash "
        "FROM watchlist_revisions_v3 ORDER BY watchlist_id,revision"
    ).fetchall()
    state_by_watchlist: dict[str, tuple[dict[str, str], list[str]]] = {}
    previous_by_watchlist: dict[str, tuple[int, str, str]] = {}
    revisions: list[dict[str, Any]] = []
    for row in revision_rows:
        (rid, wid_raw, rev_raw, operation, payload_hash, source_hash, identity_status,
         continuity, revision_of, created, deleted, header_raw, delta_hash, chain_hash) = row
        rid, wid, rev = str(rid), str(wid_raw), int(rev_raw)
        prior_rev, prior_id, prior_chain = previous_by_watchlist.get(wid, (0, "", ""))
        if rev != prior_rev + 1 or (rev == 1 and str(revision_of or "")) or (rev > 1 and str(revision_of or "") != prior_id):
            raise WatchlistStorageIntegrityError("revision_chain_link_mismatch")
        header = json.loads(str(header_raw))
        if not isinstance(header, dict) or canonical_json(header) != str(header_raw):
            raise WatchlistStorageIntegrityError("invalid_revision_header")
        _validate_header(header, wid, rid, rev, str(operation), str(payload_hash),
                         str(source_hash or ""), str(identity_status or "unknown"),
                         str(continuity or ""), str(revision_of or ""), str(created), bool(deleted))
        refs, order = state_by_watchlist.get(wid, ({}, []))
        refs, order = dict(refs), list(order)
        group = event_groups.pop((wid, rev), [])
        event_hashes: list[str] = []
        for event_index, event_row in enumerate(group):
            if event_row["revision_id"] != rid:
                raise WatchlistStorageIntegrityError("event_revision_ref_mismatch")
            if event_row["event_id"] != f"{rid}:{event_index}":
                raise WatchlistStorageIntegrityError("invalid_event_order")
            event = event_row["event"]
            kind = event.get("kind")
            key_value = event.get("key")
            key = canonical_json(key_value) if "key" in event else ""
            event_hashes.append(event_row["event_hash"])
            if kind == "remove":
                if set(event) != {"kind", "key"} or key not in refs:
                    raise WatchlistStorageIntegrityError("delta_remove_ref_missing")
                del refs[key]
                order.remove(key)
            elif kind in {"add", "replace"}:
                if set(event) != {"kind", "key", "object_hash"}:
                    raise WatchlistStorageIntegrityError("unknown_delta_fields")
                object_hash = str(event.get("object_hash", ""))
                found_item = object_cache.get(object_hash)
                if found_item is None:
                    raise WatchlistStorageIntegrityError("delta_object_ref_missing")
                _validate_key_identity(key_value, found_item)
                if kind == "add":
                    if key in refs:
                        raise WatchlistStorageIntegrityError("delta_add_duplicate")
                    order.append(key)
                elif key not in refs:
                    raise WatchlistStorageIntegrityError("delta_replace_ref_missing")
                refs[key] = object_hash
            elif kind == "order":
                if set(event) != {"kind", "items"} or not isinstance(event.get("items"), list):
                    raise WatchlistStorageIntegrityError("invalid_order_event")
                new_order: list[str] = []
                new_refs: dict[str, str] = {}
                for pair in event["items"]:
                    if not isinstance(pair, list) or len(pair) != 2:
                        raise WatchlistStorageIntegrityError("invalid_order_event")
                    key_value, object_hash = pair[0], str(pair[1])
                    key = canonical_json(key_value)
                    found_item = object_cache.get(object_hash)
                    if found_item is None:
                        raise WatchlistStorageIntegrityError("delta_object_ref_missing")
                    _validate_key_identity(key_value, found_item)
                    if key not in refs or key in new_refs:
                        raise WatchlistStorageIntegrityError("order_ref_missing")
                    new_order.append(key)
                    new_refs[key] = object_hash
                if set(new_refs) != set(refs):
                    raise WatchlistStorageIntegrityError("invalid_order_event")
                refs, order = new_refs, new_order
            else:
                raise WatchlistStorageIntegrityError("unknown_delta_event")
        calculated_delta = sha256_text(canonical_json(event_hashes))
        if calculated_delta != str(delta_hash):
            raise WatchlistStorageIntegrityError("delta_hash_mismatch")
        if sha256_text(prior_chain + str(header_raw) + str(delta_hash)) != str(chain_hash):
            raise WatchlistStorageIntegrityError("revision_chain_hash_mismatch")
        state_by_watchlist[wid] = (refs, order)
        previous_by_watchlist[wid] = (rev, rid, str(chain_hash))
        revisions.append({"revision_id": rid, "watchlist_id": wid, "revision": rev,
                          "operation": str(operation), "payload_hash": str(payload_hash),
                          "source_hash": str(source_hash or ""), "identity_status": str(identity_status),
                          "continuity_event_id": str(continuity or ""), "revision_of": str(revision_of or ""),
                          "created_at": str(created), "is_deleted": bool(deleted),
                          "header": header, "delta_hash": str(delta_hash), "chain_hash": str(chain_hash),
                          "event_count": len(group)})
    if event_groups:
        raise WatchlistStorageIntegrityError("orphan_event")
    result["delta_refs_valid"] = True
    result["revision_chain_valid"] = True
    result["revisions"] = revisions

    current_rows: dict[str, list[tuple[int, str]]] = {}
    for wid, position, object_hash in conn.execute(
        "SELECT watchlist_id,position,object_hash FROM watchlist_current_items ORDER BY watchlist_id,position"
    ):
        wid, position, object_hash = str(wid), int(position), str(object_hash)
        if object_hash not in object_cache:
            raise WatchlistStorageIntegrityError("current_object_ref_missing")
        current_rows.setdefault(wid, []).append((position, object_hash))
        object_rows[object_hash]["reference_count"] += 1

    watchlists: list[dict[str, Any]] = []
    known_watchlists: set[str] = set()
    for wid_raw, payload_raw, revision_raw, source_hash, deleted, last_id in conn.execute(
        "SELECT watchlist_id,payload_json,revision,source_hash,is_deleted,last_revision_id "
        "FROM watchlists ORDER BY watchlist_id"
    ):
        wid, raw, revision = str(wid_raw), str(payload_raw), int(revision_raw)
        payload = json.loads(raw)
        if not isinstance(payload, dict) or "items" not in payload or not isinstance(payload["items"], list):
            raise WatchlistStorageIntegrityError("invalid_current_payload")
        if canonical_json(payload) != raw:
            raise WatchlistStorageIntegrityError("noncanonical_current_payload")
        rows = current_rows.pop(wid, [])
        if [position for position, _ in rows] != list(range(len(rows))):
            raise WatchlistStorageIntegrityError("current_ref_positions_invalid")
        current_hashes = [object_hash for _, object_hash in rows]
        current_items = [object_cache[object_hash] for object_hash in current_hashes]
        refs, order = state_by_watchlist.get(wid, ({}, []))
        if payload["items"] != current_items or _item_key_tokens(current_items) != order:
            raise WatchlistStorageIntegrityError("current_projection_mismatch")
        if [refs[key] for key in order] != current_hashes:
            raise WatchlistStorageIntegrityError("current_revision_refs_mismatch")
        final = previous_by_watchlist.get(wid)
        if final is None or final[0] != revision or final[1] != str(last_id):
            raise WatchlistStorageIntegrityError("current_revision_mismatch")
        final_revision = revisions[-1] if revisions and revisions[-1]["watchlist_id"] == wid else next(
            (entry for entry in revisions if entry["watchlist_id"] == wid and entry["revision"] == revision), None)
        if (final_revision is None or final_revision["is_deleted"] != bool(deleted)
                or final_revision["payload_hash"] != sha256_text(raw)):
            raise WatchlistStorageIntegrityError("current_revision_payload_mismatch")
        if final_revision["source_hash"] != str(source_hash or ""):
            raise WatchlistStorageIntegrityError("current_revision_source_hash_mismatch")
        if final_revision["header"].get("payload_envelope") != {key: value for key, value in payload.items() if key != "items"}:
            raise WatchlistStorageIntegrityError("current_revision_envelope_mismatch")
        known_watchlists.add(wid)
        watchlists.append({"watchlist_id": wid, "payload": payload, "revision": revision,
                           "source_hash": str(source_hash or ""), "is_deleted": bool(deleted),
                           "last_revision_id": str(last_id or "")})
    if current_rows or set(previous_by_watchlist) != known_watchlists:
        raise WatchlistStorageIntegrityError("history_current_watchlist_mismatch")
    result["current_projection_valid"] = True
    result["watchlists"] = watchlists
    result["objects"] = objects
    result["complete"] = True
    return result


def _validate_key_identity(key_value: Any, item: Mapping[str, Any]) -> None:
    if not isinstance(key_value, list) or len(key_value) != 4:
        raise WatchlistStorageIntegrityError("invalid_item_identity_key")
    expected = [str(item.get("stock_code", "") or ""),
                str(item.get("source", "") or ""),
                str(item.get("source_id", "") or "")]
    if key_value[:3] != expected or isinstance(key_value[3], bool) or not isinstance(key_value[3], int) or key_value[3] < 0:
        raise WatchlistStorageIntegrityError("item_identity_key_mismatch")
