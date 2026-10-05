"""唯讀 legacy watchlist SQLite 到獨立 v3 副本的 bounded COW converter。"""
from __future__ import annotations

from contextlib import closing, contextmanager
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import uuid
from typing import Any, Callable, Iterator, Mapping

from data_module import watchlist_item_storage as item_storage
from data_module.watchlist_item_storage import (
    WatchlistStorageCapacityError,
    WatchlistStorageIntegrityError,
    WatchlistWriteCapacityRequest,
)


_RECEIPT_SCHEMA = "watchlist-cow-conversion.v1"
_SIDECARS = ("-journal", "-wal", "-shm")
_V1_BASE = {"watchlist_id", "payload_json", "revision"}
_V2_WATCHLIST_COLUMNS = {
    "watchlist_id", "payload_json", "revision", "source_hash", "is_deleted", "last_revision_id",
}
_V2_REVISION_COLUMNS = {
    "revision_id", "watchlist_id", "revision", "operation", "payload_json", "payload_hash",
    "source_hash", "identity_status", "continuity_event_id", "revision_of", "created_at",
}


class _Blocked(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class _Revision:
    revision_id: str
    watchlist_id: str
    revision: int
    operation: str
    payload_raw: str
    payload: dict[str, Any]
    payload_hash: str
    source_hash: str
    identity_status: str
    continuity_event_id: str
    revision_of: str
    created_at: str
    is_deleted: bool
    synthetic_baseline: bool = False
    source_revision_id: str = ""


@dataclass(frozen=True)
class _Current:
    watchlist_id: str
    payload_raw: str
    payload: dict[str, Any]
    revision: int
    source_hash: str
    is_deleted: bool
    last_revision_id: str


@dataclass(frozen=True)
class _Snapshot:
    source_path: Path
    source_schema_version: int
    source_sha256: str
    source_size_bytes: int
    source_stat: dict[str, int]
    currents: tuple[_Current, ...]
    revisions: tuple[_Revision, ...]
    source_row_count: int
    source_payload_bytes: int
    source_scan_bytes: int
    source_database_bytes: int


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    total = 0
    with path.open("rb") as stream:
        while True:
            block = stream.read(1024 * 1024)
            if not block:
                break
            total += len(block)
            if total > item_storage.MAX_DATABASE_BYTES:
                raise _Blocked("database_limit_exceeded")
            digest.update(block)
    return digest.hexdigest()


def _stat_record(path: Path) -> dict[str, int]:
    value = path.stat(follow_symlinks=False)
    return {
        "size": int(value.st_size), "mtime_ns": int(value.st_mtime_ns),
        "inode": int(value.st_ino), "device": int(value.st_dev),
    }


def _sidecars(path: Path) -> list[Path]:
    return [Path(f"{path}{suffix}") for suffix in _SIDECARS]


def _assert_no_sidecars(path: Path, code: str) -> None:
    if any(candidate.exists() for candidate in _sidecars(path)):
        raise _Blocked(code)


def _normalize_paths(source: Path | str, destination: Path | str) -> tuple[Path, Path, Path]:
    src_input = Path(source).expanduser()
    dst_input = Path(destination).expanduser()
    try:
        if src_input.is_symlink() or not src_input.is_file():
            raise _Blocked("source_not_regular_file")
        src = src_input.resolve(strict=True)
        dst_parent = dst_input.parent.resolve(strict=True)
        dst = dst_parent / dst_input.name
        if not dst.name or dst.exists() or dst.is_symlink():
            raise _Blocked("target_already_exists")
        receipt = dst.with_name(dst.name + ".cow-conversion.v1.json")
        if receipt.exists() or receipt.is_symlink():
            raise _Blocked("receipt_already_exists")
        if os.path.normcase(str(src)) == os.path.normcase(str(dst)):
            raise _Blocked("source_target_same_path")
        if src.stat(follow_symlinks=False).st_nlink != 1:
            raise _Blocked("source_hardlink_unsupported")
        if any(parent.is_symlink() for parent in (dst_parent,)):
            raise _Blocked("target_parent_symlink_unsupported")
        _assert_no_sidecars(src, "source_sidecar_present")
        _assert_no_sidecars(dst, "target_sidecar_present")
        _assert_no_sidecars(receipt, "receipt_sidecar_present")
    except _Blocked:
        raise
    except OSError as exc:
        raise _Blocked("path_preflight_failed") from exc
    return src, dst, receipt


def _skip_ws(raw: str, position: int) -> int:
    while position < len(raw) and raw[position] in " \t\r\n":
        position += 1
    return position


def _payload_layout(raw: str, payload: Mapping[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """保留 root `items` array 的每個 lexical span 與前後分隔符。"""
    decoder = json.JSONDecoder()
    position = _skip_ws(raw, 0)
    if position >= len(raw) or raw[position] != "{":
        raise _Blocked("invalid_payload_root")
    position += 1
    array_start = array_end = -1
    while True:
        position = _skip_ws(raw, position)
        if position >= len(raw):
            raise _Blocked("invalid_payload_root")
        if raw[position] == "}":
            position += 1
            break
        try:
            key, key_end = decoder.raw_decode(raw, position)
        except (json.JSONDecodeError, ValueError) as exc:
            raise _Blocked("invalid_payload_root") from exc
        if not isinstance(key, str):
            raise _Blocked("invalid_payload_root")
        position = _skip_ws(raw, key_end)
        if position >= len(raw) or raw[position] != ":":
            raise _Blocked("invalid_payload_root")
        value_start = _skip_ws(raw, position + 1)
        try:
            _, value_end = decoder.raw_decode(raw, value_start)
        except (json.JSONDecodeError, ValueError) as exc:
            raise _Blocked("invalid_payload_value") from exc
        if key == "items":
            if array_start >= 0 or value_start >= len(raw) or raw[value_start] != "[":
                raise _Blocked("invalid_items_array")
            array_start, array_end = value_start, value_end
        position = _skip_ws(raw, value_end)
        if position < len(raw) and raw[position] == ",":
            position += 1
            continue
        if position < len(raw) and raw[position] == "}":
            position += 1
            break
        raise _Blocked("invalid_payload_root")
    if _skip_ws(raw, position) != len(raw) or array_start < 0 or not isinstance(payload.get("items"), list):
        raise _Blocked("invalid_items_array")
    contents = _skip_ws(raw, array_start + 1)
    if contents < array_end and raw[contents] == "]":
        layout = {"codec": item_storage.PAYLOAD_LAYOUT_CODEC, "item_json": [], "empty_raw": raw}
        return layout, []
    starts: list[int] = []
    ends: list[int] = []
    index = contents
    while True:
        index = _skip_ws(raw, index)
        if index >= array_end or raw[index] == "]":
            break
        start = index
        try:
            item, end = decoder.raw_decode(raw, start)
        except (json.JSONDecodeError, ValueError) as exc:
            raise _Blocked("invalid_item_json") from exc
        if not isinstance(item, dict):
            raise _Blocked("invalid_item_object")
        starts.append(start)
        ends.append(end)
        index = _skip_ws(raw, end)
        if index < array_end and raw[index] == ",":
            index += 1
            continue
        if index < array_end and raw[index] == "]":
            break
        raise _Blocked("invalid_items_array")
    if len(starts) != len(payload["items"]):
        raise _Blocked("invalid_items_array")
    item_json = [raw[start:end] for start, end in zip(starts, ends)]
    separators = [raw[ends[i]:starts[i + 1]] for i in range(len(starts) - 1)]
    layout = {
        "codec": item_storage.PAYLOAD_LAYOUT_CODEC,
        "prefix": raw[:starts[0]], "suffix": raw[ends[-1]:],
        "separators": separators, "item_json": item_json,
    }
    for source_item, raw_item in zip(payload["items"], item_json):
        try:
            decoded = item_storage.strict_json_loads(raw_item)
        except WatchlistStorageIntegrityError as exc:
            raise _Blocked(exc.code) from exc
        if not isinstance(decoded, dict) or decoded != source_item:
            raise _Blocked("item_lexical_decode_mismatch")
    return layout, item_json


def _decode_source_payload(raw: Any) -> tuple[str, dict[str, Any], dict[str, Any], list[str]]:
    if not isinstance(raw, str):
        raise _Blocked("payload_not_text")
    try:
        payload = item_storage.strict_json_loads(raw)
    except WatchlistStorageIntegrityError as exc:
        raise _Blocked(exc.code) from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
        raise _Blocked("invalid_payload_shape")
    if any(not isinstance(item, dict) for item in payload["items"]):
        raise _Blocked("invalid_item_object")
    raw_bytes = raw.encode("utf-8")
    if len(raw_bytes) > item_storage.MAX_PAYLOAD_BYTES:
        raise _Blocked("payload_limit_exceeded")
    layout, item_json = _payload_layout(raw, payload)
    return raw, payload, layout, item_json


def _text(value: Any, code: str) -> str:
    if not isinstance(value, str):
        raise _Blocked(code)
    return value


def _revision_number(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise _Blocked("invalid_legacy_revision_number")
    return value


def _current_row(row: tuple[Any, ...], schema: int) -> _Current:
    if schema == 1:
        wid, raw, revision, *tail = row
        source_hash = "" if not tail else _text(tail[0], "invalid_source_hash")
        deleted, last_id = False, ""
    else:
        wid, raw, revision, source_hash, deleted_raw, last_id = row
        source_hash = _text(source_hash, "invalid_source_hash")
        if isinstance(deleted_raw, bool) or deleted_raw not in (0, 1):
            raise _Blocked("invalid_current_deletion_flag")
        deleted = bool(deleted_raw)
        last_id = _text(last_id, "invalid_current_revision_id")
    watchlist_id = _text(wid, "invalid_watchlist_id")
    payload_raw, payload, _, _ = _decode_source_payload(raw)
    return _Current(watchlist_id, payload_raw, payload, _revision_number(revision),
                    source_hash, deleted, last_id)


def _source_open(path: Path) -> sqlite3.Connection:
    conn: sqlite3.Connection | None = None
    try:
        conn = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True, timeout=5.0)
        conn.execute("PRAGMA query_only=ON")
        conn.execute("BEGIN")
        conn.execute("SELECT name FROM sqlite_master LIMIT 1").fetchall()
        mode = str(conn.execute("PRAGMA journal_mode").fetchone()[0]).lower()
        if mode == "wal":
            conn.close()
            raise _Blocked("source_wal_mode_unsupported")
        return conn
    except _Blocked:
        if conn is not None:
            conn.close()
        raise
    except sqlite3.Error as exc:
        if conn is not None:
            conn.close()
        raise _Blocked("source_sqlite_open_failed") from exc


def _read_snapshot(source: Path) -> tuple[_Snapshot, sqlite3.Connection]:
    before_stat = _stat_record(source)
    if before_stat["size"] > item_storage.MAX_DATABASE_BYTES:
        raise _Blocked("database_limit_exceeded")
    before_hash = _file_sha256(source)
    if _stat_record(source) != before_stat:
        raise _Blocked("source_changed_during_hash")
    _assert_no_sidecars(source, "source_sidecar_present")
    conn = _source_open(source)
    try:
        tables = item_storage.table_names(conn)
        table_count = 0
        payload_bytes = 0
        scanned_bytes = 0
        if tables == {"watchlists"}:
            source_rows = int(conn.execute("SELECT COUNT(*) FROM watchlists").fetchone()[0])
            source_payload_bytes = int(conn.execute(
                "SELECT COALESCE(SUM(length(CAST(payload_json AS BLOB))),0) FROM watchlists"
            ).fetchone()[0])
            if source_rows > item_storage.MAX_ROWS:
                raise _Blocked("row_limit_exceeded")
            if source_payload_bytes > item_storage.MAX_PAYLOAD_BYTES:
                raise _Blocked("payload_limit_exceeded")
            cols = tuple(str(row[1]) for row in conn.execute("PRAGMA table_info(watchlists)"))
            if cols == ("watchlist_id", "payload_json", "revision"):
                schema = 1
                select_current = "SELECT watchlist_id,payload_json,revision FROM watchlists ORDER BY watchlist_id LIMIT ?"
            elif set(cols) == _V1_BASE | {"source_hash"} and len(cols) == 4:
                schema = 1
                select_current = "SELECT watchlist_id,payload_json,revision,source_hash FROM watchlists ORDER BY watchlist_id LIMIT ?"
            else:
                raise _Blocked("unknown_source_schema")
            current_rows = conn.execute(select_current, (item_storage.MAX_ROWS + 1,)).fetchall()
            revision_rows: list[tuple[Any, ...]] = []
            metadata_bytes = sum(sum(len(str(value or "").encode("utf-8")) for value in (row[0], *row[3:]))
                                 for row in current_rows)
            current_payload_col = 1
        elif tables == {"watchlists", "watchlist_revisions"}:
            current_count = int(conn.execute("SELECT COUNT(*) FROM watchlists").fetchone()[0])
            revision_count = int(conn.execute("SELECT COUNT(*) FROM watchlist_revisions").fetchone()[0])
            if current_count + revision_count > item_storage.MAX_ROWS:
                raise _Blocked("row_limit_exceeded")
            source_payload_bytes = int(conn.execute(
                "SELECT (SELECT COALESCE(SUM(length(CAST(payload_json AS BLOB))),0) FROM watchlists) + "
                "(SELECT COALESCE(SUM(length(CAST(payload_json AS BLOB))),0) FROM watchlist_revisions)"
            ).fetchone()[0])
            if source_payload_bytes > item_storage.MAX_PAYLOAD_BYTES:
                raise _Blocked("payload_limit_exceeded")
            current_cols = {str(row[1]) for row in conn.execute("PRAGMA table_info(watchlists)")}
            revision_cols = {str(row[1]) for row in conn.execute("PRAGMA table_info(watchlist_revisions)")}
            if current_cols != _V2_WATCHLIST_COLUMNS or revision_cols != _V2_REVISION_COLUMNS:
                raise _Blocked("unknown_source_schema")
            schema = 2
            current_rows = conn.execute(
                "SELECT watchlist_id,payload_json,revision,source_hash,is_deleted,last_revision_id "
                "FROM watchlists ORDER BY watchlist_id LIMIT ?", (item_storage.MAX_ROWS + 1,)
            ).fetchall()
            revision_rows = conn.execute(
                "SELECT revision_id,watchlist_id,revision,operation,payload_json,payload_hash,source_hash,"
                "identity_status,continuity_event_id,revision_of,created_at "
                "FROM watchlist_revisions ORDER BY watchlist_id,revision LIMIT ?", (item_storage.MAX_ROWS + 1,)
            ).fetchall()
            metadata_bytes = sum(
                len(str(value or "").encode("utf-8"))
                for row in current_rows for value in (row[0], row[3], row[5])
            )
            metadata_bytes += sum(
                len(str(value or "").encode("utf-8"))
                for row in revision_rows for value in (row[0], row[1], *row[3:4], *row[5:])
            )
            current_payload_col = 1
        else:
            raise _Blocked("unknown_source_schema")
        table_count = len(current_rows) + len(revision_rows)
        if table_count > item_storage.MAX_ROWS:
            raise _Blocked("row_limit_exceeded")
        currents = tuple(_current_row(row, schema) for row in current_rows)
        if len({row.watchlist_id for row in currents}) != len(currents):
            raise _Blocked("duplicate_watchlist_id")
        current_by_id = {row.watchlist_id: row for row in currents}
        source_revisions: list[_Revision] = []
        previous_by_id: dict[str, int] = {}
        seen_ids: set[str] = set()
        if schema == 2:
            for row in revision_rows:
                (rid_raw, wid_raw, rev_raw, operation_raw, payload_raw_value, payload_hash_raw,
                 source_hash_raw, identity_raw, event_raw, parent_raw, created_raw) = row
                rid = _text(rid_raw, "invalid_revision_id")
                wid = _text(wid_raw, "invalid_watchlist_id")
                legacy_number = _revision_number(rev_raw)
                if rid in seen_ids or wid not in current_by_id:
                    raise _Blocked("orphan_or_duplicate_revision")
                if legacy_number <= previous_by_id.get(wid, 0):
                    raise _Blocked("duplicate_legacy_revision_number")
                seen_ids.add(rid)
                previous_by_id[wid] = legacy_number
                payload_raw, payload, _, _ = _decode_source_payload(payload_raw_value)
                payload_hash = _text(payload_hash_raw, "invalid_payload_hash")
                if _sha256_bytes(payload_raw.encode("utf-8")) != payload_hash:
                    raise _Blocked("revision_payload_hash_mismatch")
                source_revisions.append(_Revision(
                    rid, wid, legacy_number, _text(operation_raw, "invalid_revision_operation"),
                    payload_raw, payload, payload_hash,
                    _text(source_hash_raw, "invalid_source_hash"),
                    _text(identity_raw, "invalid_identity_status"),
                    _text(event_raw, "invalid_continuity_event_id"),
                    _text(parent_raw, "invalid_revision_of"),
                    _text(created_raw, "invalid_created_at"), False,
                ))
        by_watchlist: dict[str, list[_Revision]] = {}
        for revision in source_revisions:
            by_watchlist.setdefault(revision.watchlist_id, []).append(revision)
        if schema == 2:
            if set(by_watchlist) != set(current_by_id):
                if by_watchlist or current_by_id:
                    raise _Blocked("legacy_history_missing_or_orphaned")
            bound_revisions: list[_Revision] = []
            for current in currents:
                history = by_watchlist.get(current.watchlist_id, [])
                if not history:
                    continue
                final = history[-1]
                if (final.revision != current.revision or final.revision_id != current.last_revision_id
                        or final.payload_raw != current.payload_raw
                        or final.payload != current.payload
                        or final.source_hash != current.source_hash):
                    raise _Blocked("current_revision_binding_mismatch")
                for index, revision in enumerate(history):
                    bound_revisions.append(_Revision(
                        revision.revision_id, revision.watchlist_id, revision.revision,
                        revision.operation, revision.payload_raw, revision.payload,
                        revision.payload_hash, revision.source_hash, revision.identity_status,
                        revision.continuity_event_id, revision.revision_of, revision.created_at,
                        current.is_deleted if index == len(history) - 1 else False,
                    ))
            source_revisions = bound_revisions
        payload_bytes = sum(len(row.payload_raw.encode("utf-8")) for row in currents)
        payload_bytes += sum(len(row.payload_raw.encode("utf-8")) for row in source_revisions)
        scanned_bytes = payload_bytes + metadata_bytes
        database_bytes = int(conn.execute("PRAGMA page_count").fetchone()[0]) * int(
            conn.execute("PRAGMA page_size").fetchone()[0]
        )
        if payload_bytes > item_storage.MAX_PAYLOAD_BYTES:
            raise _Blocked("payload_limit_exceeded")
        if scanned_bytes > item_storage.MAX_SCAN_BYTES:
            raise _Blocked("scan_limit_exceeded")
        if database_bytes > item_storage.MAX_DATABASE_BYTES:
            raise _Blocked("database_limit_exceeded")
        after_stat = _stat_record(source)
        after_hash = _file_sha256(source)
        _assert_no_sidecars(source, "source_sidecar_present")
        if before_stat != after_stat or before_hash != after_hash:
            raise _Blocked("source_changed_during_read")
        snapshot = _Snapshot(
            source, schema, before_hash, before_stat["size"], before_stat,
            currents, tuple(source_revisions), table_count, payload_bytes,
            scanned_bytes, database_bytes,
        )
        return snapshot, conn
    except Exception:
        conn.close()
        raise


def _baseline_revision(snapshot: _Snapshot, current: _Current) -> _Revision:
    return _Revision(
        revision_id=f"cow-v1-baseline:{snapshot.source_sha256}:{current.watchlist_id}",
        watchlist_id=current.watchlist_id, revision=current.revision,
        operation="migration_baseline", payload_raw=current.payload_raw,
        payload=current.payload, payload_hash=_sha256_bytes(current.payload_raw.encode("utf-8")),
        source_hash=current.source_hash, identity_status="", continuity_event_id="",
        revision_of="", created_at="", is_deleted=current.is_deleted,
        synthetic_baseline=True, source_revision_id="",
    )


def _rows_for_import(snapshot: _Snapshot) -> list[_Revision]:
    if snapshot.source_schema_version == 1:
        return [_baseline_revision(snapshot, current) for current in snapshot.currents]
    return list(snapshot.revisions)


def _provenance(snapshot: _Snapshot, revision: _Revision) -> dict[str, Any]:
    return {
        "schema": item_storage.IMPORT_PROVENANCE_SCHEMA,
        "source_schema_version": snapshot.source_schema_version,
        "source_sha256": snapshot.source_sha256,
        "source_revision_id": ("" if revision.synthetic_baseline else (revision.source_revision_id or revision.revision_id)),
        "source_revision_number": revision.revision,
        "synthetic_baseline": revision.synthetic_baseline,
        "current_is_deleted": revision.is_deleted,
        "source_current_revision_id": next(
            (current.last_revision_id for current in snapshot.currents
             if current.watchlist_id == revision.watchlist_id), ""),
    }


def _build_database(snapshot: _Snapshot) -> tuple[sqlite3.Connection, dict[str, Any]]:
    conn = sqlite3.connect(":memory:")
    try:
        item_storage.initialize_schema(conn)
        expected_rows = _rows_for_import(snapshot)
        count_by_watchlist: dict[str, int] = {}
        previous_by_watchlist: dict[str, int] = {}
        for source_revision in expected_rows:
            if source_revision.revision_id in {row[0] for row in conn.execute(
                "SELECT revision_id FROM watchlist_revisions_v3") }:
                raise _Blocked("duplicate_source_revision_id")
            source_raw, payload, layout, item_json = _decode_source_payload(source_revision.payload_raw)
            if _sha256_bytes(source_raw.encode("utf-8")) != source_revision.payload_hash:
                raise _Blocked("source_payload_hash_mismatch")
            prior_number = previous_by_watchlist.get(source_revision.watchlist_id)
            provenance = _provenance(snapshot, source_revision)
            item_storage.save_v3(
                conn,
                watchlist_id=source_revision.watchlist_id,
                payload=payload,
                revision_id=source_revision.revision_id,
                operation=source_revision.operation,
                source_hash=source_revision.source_hash,
                identity_status=source_revision.identity_status,
                continuity_event_id=source_revision.continuity_event_id,
                revision_of=source_revision.revision_of,
                created_at=source_revision.created_at,
                expected_revision=prior_number,
                payload_raw_override=source_raw,
                item_json_overrides=item_json,
                payload_layout=layout,
                import_provenance=provenance,
                revision_number=source_revision.revision,
                imported_is_deleted=source_revision.is_deleted,
            )
            previous_by_watchlist[source_revision.watchlist_id] = source_revision.revision
            count_by_watchlist[source_revision.watchlist_id] = count_by_watchlist.get(source_revision.watchlist_id, 0) + 1
        for current in snapshot.currents:
            actual = conn.execute(
                "SELECT payload_json,revision,source_hash,is_deleted FROM watchlists WHERE watchlist_id=?",
                (current.watchlist_id,),
            ).fetchone()
            if actual is None:
                if snapshot.source_schema_version == 2:
                    raise _Blocked("legacy_history_missing")
                continue
            if (str(actual[0]) != current.payload_raw or int(actual[1]) != current.revision
                    or str(actual[2]) != current.source_hash or bool(actual[3]) != current.is_deleted):
                raise _Blocked("target_current_projection_mismatch")
        inventory = item_storage.inventory(conn)
        if not inventory.get("complete") or not inventory.get("historical_payload_hashes_verified"):
            raise _Blocked("target_inventory_incomplete")
        target_revisions = [
            item for current in snapshot.currents
            for item in item_storage.iter_revisions(conn, current.watchlist_id, include_payload=True)
        ]
        comparison = _compare(snapshot, expected_rows, target_revisions, inventory)
        stats = item_storage.storage_stats(conn)
        conn.commit()
        return conn, {
            "comparison": comparison,
            "revision_count": len(expected_rows),
            "revision_counts": count_by_watchlist,
            "item_count": sum(len(current.payload["items"]) for current in snapshot.currents),
            "payload_bytes": stats["payload_bytes"],
            "scan_bytes": stats["scanned_bytes"],
            "row_count": sum(stats["row_counts"].values()),
            "database_bytes": stats["database_bytes"],
        }
    except Exception:
        conn.close()
        raise


def _compare(
    snapshot: _Snapshot, expected: list[_Revision], actual: list[dict[str, Any]],
    inventory: Mapping[str, Any],
) -> dict[str, Any]:
    expected_by_watchlist: dict[str, list[_Revision]] = {}
    actual_by_watchlist: dict[str, list[dict[str, Any]]] = {}
    for entry in expected:
        expected_by_watchlist.setdefault(entry.watchlist_id, []).append(entry)
    for actual_entry in actual:
        actual_by_watchlist.setdefault(str(actual_entry["watchlist_id"]), []).append(actual_entry)
    revisions_compared = 0
    payload_hashes_matched = 0
    metadata_compared = 0
    for watchlist_id, expected_rows in expected_by_watchlist.items():
        actual_rows = actual_by_watchlist.get(watchlist_id, [])
        if len(expected_rows) != len(actual_rows):
            raise _Blocked("comparison_revision_count_mismatch")
        for left, right in zip(expected_rows, actual_rows):
            expected_source_id = left.source_revision_id or left.revision_id
            if left.synthetic_baseline:
                expected_source_id = ""
            expected_values = (
                left.revision, left.operation, left.payload_hash, left.source_hash,
                left.identity_status, left.continuity_event_id, left.revision_of,
                left.created_at, left.is_deleted,
            )
            actual_values = (
                int(right["revision"]), str(right["operation"]), str(right["payload_hash"]),
                str(right["source_hash"]), str(right["identity_status"]),
                str(right["continuity_event_id"]), str(right["revision_of"]),
                str(right["created_at"]), bool(right["is_deleted"]),
            )
            if expected_values != actual_values or right.get("payload") != left.payload:
                raise _Blocked("comparison_revision_metadata_mismatch")
            provenance = right.get("header", {}).get("import_provenance", {})
            if (right.get("revision_id") != left.revision_id
                    or provenance.get("source_revision_id", "") != expected_source_id
                    or bool(provenance.get("synthetic_baseline")) != left.synthetic_baseline):
                raise _Blocked("comparison_revision_identity_mismatch")
            revisions_compared += 1
            payload_hashes_matched += 1
            metadata_compared += 1
    if len(actual) != len(expected):
        raise _Blocked("comparison_revision_count_mismatch")
    current_by_id = {row.watchlist_id: row for row in snapshot.currents}
    target_by_id = {str(row["watchlist_id"]): row for row in inventory["watchlists"]}
    if set(current_by_id) != set(target_by_id):
        raise _Blocked("comparison_current_ids_mismatch")
    for watchlist_id, current_source in current_by_id.items():
        right = target_by_id[watchlist_id]
        if (right.get("payload") != current_source.payload or right.get("payload_json") != current_source.payload_raw
                or int(right.get("revision", -1)) != current_source.revision
                or str(right.get("source_hash", "")) != current_source.source_hash
                or bool(right.get("is_deleted")) != current_source.is_deleted):
            raise _Blocked("comparison_current_mismatch")
        final_source_revision_id = current_source.last_revision_id
        if snapshot.source_schema_version == 1:
            provenance = inventory["revisions"]
            last = next((entry for entry in provenance if entry["watchlist_id"] == watchlist_id), None)
            if last is None or not last["header"]["import_provenance"]["synthetic_baseline"]:
                raise _Blocked("comparison_baseline_marker_missing")
        elif str(right.get("last_revision_id", "")) != final_source_revision_id:
            raise _Blocked("comparison_current_revision_identity_mismatch")
    return {
        "complete": True,
        "source_current_rows": len(snapshot.currents),
        "target_current_rows": len(target_by_id),
        "source_revision_rows": len(expected),
        "target_revision_rows": len(actual),
        "revision_rows_compared": revisions_compared,
        "payload_hashes_matched": payload_hashes_matched,
        "revision_metadata_rows_compared": metadata_compared,
        "current_payloads_compared": len(snapshot.currents),
        "source_current_bytes_preserved": True,
        "unknown_payload_fields_preserved": True,
        "source_history_gaps_preserved": True,
        "synthetic_baselines_marked": sum(row.synthetic_baseline for row in expected),
        "checks": [
            "schema", "duplicate_json_keys", "current_payload_raw_bytes", "revision_payload_raw_hashes",
            "revision_ids_numbers_metadata", "revision_of_values", "item_order_and_unknown_fields",
            "source_hash", "deletion_state_when_source_known", "history_gap_provenance", "v3_inventory",
        ],
    }


def _capacity_preflight(
    destination: Path, snapshot: _Snapshot, details: Mapping[str, Any],
    capacity_preflight: Callable[[WatchlistWriteCapacityRequest], bool | None] | None,
) -> None:
    target_bytes = int(details["database_bytes"])
    receipt_template = _base_result(
        snapshot, destination, destination.with_name(destination.name + ".cow-conversion.v1.json"),
        "ready", details, target_hash="0" * 64,
        target_size=item_storage.MAX_DATABASE_BYTES,
    )
    receipt_bytes = len(json.dumps(
        receipt_template, ensure_ascii=False, sort_keys=True, allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8"))
    request = WatchlistWriteCapacityRequest(
        db_path=destination, operation="watchlist-cow-convert",
        payload_bytes_after=int(details["payload_bytes"]), rows_after=int(details["row_count"]),
        database_bytes_before=0, sidecar_bytes_before=0,
        estimated_database_growth_bytes=target_bytes + receipt_bytes,
        required_peak_bytes=snapshot.source_size_bytes + 2 * target_bytes + 2 * receipt_bytes,
    )
    if target_bytes > item_storage.MAX_DATABASE_BYTES:
        raise _Blocked("database_limit_exceeded")
    if capacity_preflight is not None:
        try:
            approved = capacity_preflight(request)
        except Exception as exc:
            raise _Blocked("capacity_unknown") from exc
        if approved is not True:
            raise _Blocked("capacity_unknown" if approved is None else "capacity_insufficient")
        return
    try:
        from data_module.ml_storage_capacity import (
            evaluate_capacity, filesystem_usage, heavy_chain_capacity_budget,
        )
        decision = evaluate_capacity(
            budget=heavy_chain_capacity_budget(), usage=filesystem_usage(destination),
            stage="watchlist-cow-conversion",
            persistent_existing_bytes=snapshot.source_size_bytes,
            persistent_new_bytes_estimate=target_bytes + receipt_bytes,
            temporary_peak_bytes_observed=2 * target_bytes + 2 * receipt_bytes,
        )
    except Exception as exc:
        raise _Blocked("capacity_unknown") from exc
    if getattr(decision, "within_budget", None) is not True:
        raise _Blocked("capacity_insufficient")


def _base_result(snapshot: _Snapshot, target: Path, receipt: Path, status: str,
                 details: Mapping[str, Any], *, target_hash: str | None,
                 target_size: int | None) -> dict[str, Any]:
    return {
        "schema_version": _RECEIPT_SCHEMA,
        "status": status,
        "source_path": str(snapshot.source_path),
        "target_path": str(target),
        "receipt_path": str(receipt),
        "source_schema_version": snapshot.source_schema_version,
        "target_schema_version": item_storage.SCHEMA_VERSION,
        "source_sha256": snapshot.source_sha256,
        "target_sha256": target_hash,
        "source_size_bytes": snapshot.source_size_bytes,
        "target_size_bytes": target_size,
        "source_stat": dict(snapshot.source_stat),
        "revision_count": int(details["revision_count"]),
        "revision_counts": dict(details["revision_counts"]),
        "item_count": int(details["item_count"]),
        "migration_notes": [
            "v1 only supplies current state; one explicitly marked synthetic baseline is stored per current row."
            if snapshot.source_schema_version == 1 else
            "v2 has no historical deletion flag; historical revisions retain reader-visible false and the current revision retains its current-row flag."
        ],
        "comparison": dict(details["comparison"]),
    }


def _verify_source_still_held(snapshot: _Snapshot, conn: sqlite3.Connection) -> None:
    if not conn.in_transaction:
        raise _Blocked("source_snapshot_lost")
    _assert_no_sidecars(snapshot.source_path, "source_sidecar_present")
    current_stat = _stat_record(snapshot.source_path)
    current_hash = _file_sha256(snapshot.source_path)
    _assert_no_sidecars(snapshot.source_path, "source_sidecar_present")
    if current_stat != snapshot.source_stat or current_hash != snapshot.source_sha256:
        raise _Blocked("source_changed_before_publish")
    try:
        conn.execute("SELECT name FROM sqlite_master LIMIT 1").fetchall()
    except sqlite3.Error as exc:
        raise _Blocked("source_snapshot_lost") from exc


def _reserve_source_for_conversion(source: Path) -> sqlite3.Connection:
    """只取 SQLite reserved writer lock，query_only 下直到發布都不執行資料寫入。"""
    try:
        conn = sqlite3.connect(f"{source.as_uri()}?mode=rw", uri=True, timeout=0.1)
        conn.execute("PRAGMA busy_timeout=100")
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("PRAGMA query_only=ON")
        return conn
    except sqlite3.Error as exc:
        try:
            conn.close()  # type: ignore[possibly-undefined]
        except Exception:
            pass
        raise _Blocked("source_writer_lock_unavailable") from exc


def _busy_probe_source(source: Path) -> None:
    conn: sqlite3.Connection | None = None
    try:
        conn = sqlite3.connect(f"{source.as_uri()}?mode=rw", uri=True, timeout=0.1)
        conn.execute("PRAGMA busy_timeout=100")
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("PRAGMA query_only=ON")
        conn.rollback()
    except sqlite3.Error as exc:
        raise _Blocked("source_writer_busy") from exc
    finally:
        if conn is not None:
            conn.close()


def _create_stage(destination: Path, memory_conn: sqlite3.Connection) -> Path:
    stage = destination.with_name(f"{destination.name}.cow-stage-{uuid.uuid4().hex}.sqlite")
    try:
        descriptor = os.open(stage, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
        os.close(descriptor)
        disk_conn = sqlite3.connect(stage)
        try:
            memory_conn.backup(disk_conn)
            disk_conn.execute("PRAGMA journal_mode=DELETE")
            disk_conn.commit()
        finally:
            disk_conn.close()
        with stage.open("r+b") as stream:
            os.fsync(stream.fileno())
        return stage
    except Exception:
        # 已建立的 failed stage 刻意保留，供診斷；呼叫端會回傳 stage path。
        raise


def _validate_stage(stage: Path, expected: Mapping[str, Any]) -> tuple[str, int]:
    _assert_no_sidecars(stage, "stage_sidecar_present")
    size = stage.stat().st_size
    if size > item_storage.MAX_DATABASE_BYTES:
        raise _Blocked("database_limit_exceeded")
    digest = _file_sha256(stage)
    try:
        conn = sqlite3.connect(f"{stage.as_uri()}?mode=ro", uri=True)
        conn.execute("PRAGMA query_only=ON")
        conn.execute("BEGIN")
        inventory = item_storage.inventory(conn)
        if not inventory.get("complete") or len(inventory["revisions"]) != expected["revision_count"]:
            raise _Blocked("stage_oracle_mismatch")
        conn.close()
    except _Blocked:
        raise
    except Exception as exc:
        raise _Blocked("stage_validation_failed") from exc
    return digest, size


def _publish_noreplace(stage: Path, target: Path) -> os.stat_result:
    _assert_no_sidecars(target, "target_sidecar_present")
    try:
        os.link(stage, target)
    except FileExistsError as exc:
        raise _Blocked("target_already_exists") from exc
    except OSError as exc:
        raise _Blocked("target_publish_failed") from exc
    return target.stat(follow_symlinks=False)


def _write_receipt_stage(receipt_path: Path, payload: Mapping[str, Any]) -> Path:
    stage = receipt_path.with_name(f"{receipt_path.name}.stage-{uuid.uuid4().hex}")
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, allow_nan=False,
                         separators=(",", ":")).encode("utf-8")
    descriptor = os.open(stage, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    return stage


def _convert(source: Path | str, destination: Path | str, *, dry_run: bool,
             capacity_preflight: Callable[[WatchlistWriteCapacityRequest], bool | None] | None,
             cancel_check: Callable[[], bool] | None) -> dict[str, Any]:
    stage: Path | None = None
    receipt_stage: Path | None = None
    writer_lock: sqlite3.Connection | None = None
    try:
        src, target, receipt_path = _normalize_paths(source, destination)
        snapshot, source_conn = _read_snapshot(src)
        try:
            if dry_run:
                _busy_probe_source(src)
            else:
                writer_lock = _reserve_source_for_conversion(src)
                _verify_source_still_held(snapshot, source_conn)
        except Exception:
            source_conn.close()
            raise
        memory_conn: sqlite3.Connection | None = None
        with closing(source_conn):
            if cancel_check is not None and cancel_check():
                raise _Blocked("cancelled")
            memory_conn, details = _build_database(snapshot)
            try:
                _capacity_preflight(target, snapshot, details, capacity_preflight)
                if cancel_check is not None and cancel_check():
                    raise _Blocked("cancelled")
                if dry_run:
                    _verify_source_still_held(snapshot, source_conn)
                    return _base_result(snapshot, target, receipt_path, "dry_run", details,
                                        target_hash=None, target_size=int(details["database_bytes"]))
                stage = _create_stage(target, memory_conn)
                target_hash, target_size = _validate_stage(stage, details)
                if target_size > item_storage.MAX_DATABASE_BYTES:
                    raise _Blocked("database_limit_exceeded")
                _verify_source_still_held(snapshot, source_conn)
                receipt_payload = _base_result(snapshot, target, receipt_path, "ready", details,
                                               target_hash=target_hash, target_size=target_size)
                receipt_stage = _write_receipt_stage(receipt_path, receipt_payload)
                _verify_source_still_held(snapshot, source_conn)
                _publish_noreplace(stage, target)
                try:
                    os.link(receipt_stage, receipt_path)
                    os.unlink(receipt_stage)
                    receipt_stage = None
                    os.unlink(stage)
                    stage = None
                except Exception:
                    raise _Blocked("receipt_publish_failed")
                return receipt_payload
            finally:
                if memory_conn is not None:
                    memory_conn.close()
    except _Blocked as exc:
        result: dict[str, Any] = {"schema_version": _RECEIPT_SCHEMA, "status": "blocked", "error_code": exc.code}
        if stage is not None and stage.exists():
            result["failed_stage_path"] = str(stage)
        if receipt_stage is not None and receipt_stage.exists():
            result["failed_receipt_stage_path"] = str(receipt_stage)
        return result
    except (sqlite3.Error, OSError, ValueError, TypeError, WatchlistStorageIntegrityError,
            WatchlistStorageCapacityError) as exc:
        result = {"schema_version": _RECEIPT_SCHEMA, "status": "blocked",
                  "error_code": str(getattr(exc, "code", type(exc).__name__))}
        if stage is not None and stage.exists():
            result["failed_stage_path"] = str(stage)
        if receipt_stage is not None and receipt_stage.exists():
            result["failed_receipt_stage_path"] = str(receipt_stage)
        return result
    except Exception as exc:
        result = {"schema_version": _RECEIPT_SCHEMA, "status": "blocked",
                  "error_code": str(getattr(exc, "code", type(exc).__name__))}
        if stage is not None and stage.exists():
            result["failed_stage_path"] = str(stage)
        if receipt_stage is not None and receipt_stage.exists():
            result["failed_receipt_stage_path"] = str(receipt_stage)
        return result
    finally:
        if writer_lock is not None:
            writer_lock.close()


def dry_run_watchlist_sqlite(
    source: Path | str,
    destination: Path | str,
    *,
    capacity_preflight: Callable[[WatchlistWriteCapacityRequest], bool | None] | None = None,
) -> dict[str, Any]:
    """唯讀掃描 legacy DB 並於記憶體驗證 v3 副本，不建立目標或收據檔。"""
    return _convert(source, destination, dry_run=True,
                    capacity_preflight=capacity_preflight, cancel_check=None)


def convert_watchlist_sqlite(
    source: Path | str,
    destination: Path | str,
    *,
    capacity_preflight: Callable[[WatchlistWriteCapacityRequest], bool | None] | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """建置新 SQLite v3 副本並在驗證與 capacity preflight 通過後以 no-replace 發布。"""
    return _convert(source, destination, dry_run=False,
                    capacity_preflight=capacity_preflight, cancel_check=cancel_check)
