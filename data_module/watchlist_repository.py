"""候選池 SQLite 副本儲存與 append-only revision 歷史。

這個 repository 是候選池的 current projection；每次變更同時寫入
``watchlist_revisions`` 與 current row，同一個 SQLite transaction 內完成。
刪除不會物理移除原 row，而是留下 payload 與 tombstone revision。
"""

from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any, Callable, Iterator, Mapping
from uuid import uuid4

from app_module.dtos.decision_continuity_dtos import (
    IDENTITY_STATUS_CONFLICT,
    IDENTITY_STATUS_LINKED,
    IDENTITY_STATUS_UNKNOWN,
    DecisionIdentity,
)
from data_module import watchlist_item_storage as item_storage
from data_module.watchlist_item_storage import (
    WatchlistStorageCapacityError,
    WatchlistStorageIntegrityError,
    WatchlistWriteCapacityRequest,
)


class WatchlistRepository:
    """以 optimistic revision 與 append-only history 保存候選池。"""

    SCHEMA_VERSION = 3

    def __init__(
        self,
        db_path: Path,
        *,
        initialize: bool = False,
        capacity_preflight: Callable[[WatchlistWriteCapacityRequest], bool | None] | None = None,
    ):
        self.db_path = Path(db_path).resolve()
        self._capacity_preflight = capacity_preflight
        if initialize:
            self._initialize_schema()

    def _initialize_schema(self) -> None:
        detected = self.detect_storage_format()
        if detected["schema_version"] in {1, 2}:
            raise RuntimeError("watchlist_schema_requires_copy_on_write")
        if detected["schema_version"] == 3:
            with closing(self._open_read_only()) as conn:
                item_storage.inventory(conn)
            return
        if detected["storage_format"] != "uninitialized":
            raise WatchlistStorageIntegrityError("unknown_schema")
        request = WatchlistWriteCapacityRequest(
            db_path=self.db_path, operation="initialize-v3", payload_bytes_after=0,
            rows_after=1, database_bytes_before=0, sidecar_bytes_before=0,
            estimated_database_growth_bytes=16384, required_peak_bytes=32768,
        )
        self._assert_capacity(request)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                if item_storage.table_names(conn):
                    raise RuntimeError("watchlist_schema_changed_during_initialize")
                item_storage.initialize_schema(conn)
                self._before_commit("initialize-v3", "")
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def _before_commit(self, operation: str, revision_id: str) -> None:
        """測試可覆寫此點，在提交前注入取消或崩潰。"""

    def _request_capacity(self, operation: str, payload_bytes: int, rows: int,
                          database_bytes: int, growth_bytes: int) -> None:
        sidecar_bytes = 0
        for suffix in ("-journal", "-wal", "-shm"):
            try:
                sidecar_bytes += Path(f"{self.db_path}{suffix}").stat().st_size
            except FileNotFoundError:
                pass
        growth = max(growth_bytes, 4096)
        # DELETE journal 可能暫存被改寫的資料頁，預留整個舊 DB 與成長量。
        required_peak = database_bytes + sidecar_bytes + database_bytes + growth
        self._assert_capacity(WatchlistWriteCapacityRequest(
            db_path=self.db_path, operation=operation, payload_bytes_after=payload_bytes,
            rows_after=rows, database_bytes_before=database_bytes,
            sidecar_bytes_before=sidecar_bytes,
            estimated_database_growth_bytes=growth,
            required_peak_bytes=required_peak,
        ))

    def _preflight_v3_save(self, **kwargs: Any) -> tuple[int, int, int]:
        with closing(self._open_read_only()) as conn:
            item_storage.inventory(conn)
            plan = item_storage.save_v3(conn, **kwargs, plan_only=True)
            stats = item_storage.storage_stats(conn)
        self._request_capacity(kwargs["operation"], plan[1], plan[2],
                               stats["database_bytes"], max(0, plan[1] - stats["payload_bytes"]))
        return plan

    def _preflight_v3_delete(self, operation: str) -> None:
        with closing(self._open_read_only()) as conn:
            item_storage.inventory(conn)
            stats = item_storage.storage_stats(conn)
        self._request_capacity(operation, stats["payload_bytes"] + 2048,
                               sum(stats["row_counts"].values()) + 1,
                               stats["database_bytes"], 8192)

    def _preflight_legacy_save(
        self, raw: str, operation: str, watchlist_id: str, *, replace_current: bool,
    ) -> None:
        with closing(self._open_read_only()) as conn:
            tables = item_storage.table_names(conn)
            if tables != {"watchlists", "watchlist_revisions"}:
                raise RuntimeError("watchlist_schema_requires_copy_on_write")
            rows = int(conn.execute("SELECT COUNT(*) FROM watchlists").fetchone()[0])
            rows += int(conn.execute("SELECT COUNT(*) FROM watchlist_revisions").fetchone()[0])
            old_current = conn.execute(
                "SELECT length(CAST(payload_json AS BLOB)) FROM watchlists WHERE watchlist_id=?",
                (watchlist_id,),
            ).fetchone()
            old_current_bytes = 0 if old_current is None else int(old_current[0])
            size = int(conn.execute(
                "SELECT COALESCE(SUM(length(CAST(payload_json AS BLOB))),0) FROM watchlists"
            ).fetchone()[0]) + int(conn.execute(
                "SELECT COALESCE(SUM(length(CAST(payload_json AS BLOB))),0) FROM watchlist_revisions"
            ).fetchone()[0])
            metadata = int(conn.execute(
                "SELECT COALESCE(SUM(length(CAST(revision_id AS BLOB))+length(CAST(watchlist_id AS BLOB))+"
                "length(CAST(operation AS BLOB))+length(CAST(payload_hash AS BLOB))+"
                "length(CAST(source_hash AS BLOB))+length(CAST(identity_status AS BLOB))+"
                "length(CAST(continuity_event_id AS BLOB))+length(CAST(revision_of AS BLOB))+"
                "length(CAST(created_at AS BLOB))),0) FROM watchlist_revisions"
            ).fetchone()[0]) + int(conn.execute(
                "SELECT COALESCE(SUM(length(CAST(watchlist_id AS BLOB))+length(CAST(source_hash AS BLOB))+"
                "length(CAST(last_revision_id AS BLOB))),0) FROM watchlists"
            ).fetchone()[0])
            database_bytes = int(conn.execute("PRAGMA page_count").fetchone()[0]) * int(conn.execute("PRAGMA page_size").fetchone()[0])
        new_bytes = len(raw.encode("utf-8"))
        removed_current = old_current_bytes if replace_current else 0
        projected_payload = size - removed_current + new_bytes
        projected_scan = size + metadata - removed_current + new_bytes
        if replace_current:
            projected_payload += new_bytes
            projected_scan += new_bytes
        if projected_scan > item_storage.MAX_SCAN_BYTES:
            raise WatchlistStorageCapacityError("scan_limit_exceeded")
        projected_rows = rows + 1 + int(replace_current and old_current is None)
        self._request_capacity(operation, projected_payload, projected_rows,
                               database_bytes, new_bytes + 8192)

    @staticmethod
    def _assert_legacy_limits(conn: sqlite3.Connection) -> None:
        rows = int(conn.execute("SELECT COUNT(*) FROM watchlists").fetchone()[0])
        rows += int(conn.execute("SELECT COUNT(*) FROM watchlist_revisions").fetchone()[0])
        payload_bytes = int(conn.execute(
            "SELECT COALESCE(SUM(length(CAST(payload_json AS BLOB))),0) FROM watchlists"
        ).fetchone()[0]) + int(conn.execute(
            "SELECT COALESCE(SUM(length(CAST(payload_json AS BLOB))),0) FROM watchlist_revisions"
        ).fetchone()[0])
        if rows > item_storage.MAX_ROWS:
            raise WatchlistStorageCapacityError("row_limit_exceeded")
        if payload_bytes > item_storage.MAX_PAYLOAD_BYTES:
            raise WatchlistStorageCapacityError("payload_limit_exceeded")
        database_bytes = int(conn.execute("PRAGMA page_count").fetchone()[0]) * int(
            conn.execute("PRAGMA page_size").fetchone()[0]
        )
        if database_bytes > item_storage.MAX_DATABASE_BYTES:
            raise WatchlistStorageCapacityError("database_limit_exceeded")

    def _assert_capacity(self, request: WatchlistWriteCapacityRequest) -> None:
        if request.payload_bytes_after > item_storage.MAX_PAYLOAD_BYTES:
            raise WatchlistStorageCapacityError("payload_limit_exceeded")
        if request.rows_after > item_storage.MAX_ROWS:
            raise WatchlistStorageCapacityError("row_limit_exceeded")
        if request.database_bytes_before + request.estimated_database_growth_bytes > item_storage.MAX_DATABASE_BYTES:
            raise WatchlistStorageCapacityError("database_limit_exceeded")
        if self._capacity_preflight is not None:
            try:
                approved = self._capacity_preflight(request)
            except Exception as exc:
                raise WatchlistStorageCapacityError("capacity_unknown", str(exc)) from exc
            if approved is not True:
                raise WatchlistStorageCapacityError("capacity_unknown" if approved is None else "capacity_insufficient")
            return
        try:
            from data_module.ml_storage_capacity import (
                evaluate_capacity, filesystem_usage, heavy_chain_capacity_budget,
            )
            decision = evaluate_capacity(
                budget=heavy_chain_capacity_budget(), usage=filesystem_usage(self.db_path),
                stage="watchlist-storage-write",
                persistent_existing_bytes=request.database_bytes_before,
                persistent_new_bytes_estimate=request.estimated_database_growth_bytes,
                temporary_peak_bytes_observed=request.required_peak_bytes,
            )
        except Exception as exc:
            raise WatchlistStorageCapacityError("capacity_unknown", str(exc)) from exc
        if getattr(decision, "within_budget", None) is not True:
            raise WatchlistStorageCapacityError("capacity_insufficient")

    def detect_storage_format(self) -> dict[str, Any]:
        """唯讀辨識資料格式，不初始化、不升級，也不修改任何位元組。"""
        if not self.db_path.is_file():
            return {"schema_version": None, "storage_format": "uninitialized",
                    "requires_copy_on_write": False, "ready": False}
        try:
            with closing(self._open_read_only()) as conn:
                tables = item_storage.table_names(conn)
                if not tables:
                    return {"schema_version": None, "storage_format": "uninitialized",
                            "requires_copy_on_write": False, "ready": False}
                if "watchlist_storage_meta" in tables:
                    item_storage.validate_schema(conn)
                    return {"schema_version": 3, "storage_format": item_storage.STORAGE_FORMAT,
                            "requires_copy_on_write": False, "ready": True}
                columns = self._table_columns(conn, "watchlists") if "watchlists" in tables else set()
                base = {"watchlist_id", "payload_json", "revision"}
                v2_columns = base | {"source_hash", "is_deleted", "last_revision_id"}
                if tables == {"watchlists"} and columns in (base, base | {"source_hash"}):
                    return {"schema_version": 1, "storage_format": "watchlist-full-payload.v1",
                            "requires_copy_on_write": True, "ready": True}
                if tables == {"watchlists", "watchlist_revisions"} and columns == v2_columns:
                    revisions = self._table_columns(conn, "watchlist_revisions")
                    expected = {"revision_id", "watchlist_id", "revision", "operation", "payload_json",
                                "payload_hash", "source_hash", "identity_status", "continuity_event_id",
                                "revision_of", "created_at"}
                    if revisions == expected:
                        return {"schema_version": 2, "storage_format": "watchlist-full-payload.v2",
                                "requires_copy_on_write": True, "ready": True}
        except (sqlite3.Error, WatchlistStorageIntegrityError, ValueError):
            pass
        return {"schema_version": None, "storage_format": "unknown",
                "requires_copy_on_write": True, "ready": False}

    def get_item_storage_inventory(
        self, *, connection: sqlite3.Connection | None = None,
        max_scan_bytes: int = item_storage.MAX_SCAN_BYTES,
    ) -> dict[str, Any]:
        """回傳 unique item inventory，不逐 revision 重建完整 snapshot。"""
        if connection is not None:
            return item_storage.inventory(connection, max_scan_bytes=max_scan_bytes)
        with closing(self._open_read_only()) as conn:
            return item_storage.inventory(conn, max_scan_bytes=max_scan_bytes)

    def iter_revisions(
        self, watchlist_id: str, *, include_payload: bool = True,
    ) -> Iterator[dict[str, Any]]:
        """依事件增量重播歷史，每次只交付一份完整 payload。"""
        with closing(self._open_read_only()) as conn:
            storage = self.detect_storage_format()
            if storage["schema_version"] == 3:
                yield from item_storage.iter_revisions(conn, watchlist_id, include_payload=include_payload)
                return
            if storage["schema_version"] not in {1, 2}:
                item_storage.validate_schema(conn)
                raise WatchlistStorageIntegrityError("unknown_schema")
            try:
                cursor = conn.execute(
                    "SELECT revision_id,watchlist_id,revision,operation,payload_json,payload_hash,"
                    "source_hash,identity_status,continuity_event_id,revision_of,created_at "
                    "FROM watchlist_revisions WHERE watchlist_id=? ORDER BY revision", (watchlist_id,)
                )
            except sqlite3.OperationalError:
                return
            for row in cursor:
                result = {"revision_id": str(row[0]), "watchlist_id": str(row[1]),
                          "revision": int(row[2]), "operation": str(row[3]),
                          "payload_hash": str(row[5]), "source_hash": str(row[6] or ""),
                          "identity_status": str(row[7] or IDENTITY_STATUS_UNKNOWN),
                          "continuity_event_id": str(row[8] or ""),
                          "revision_of": str(row[9] or ""), "created_at": str(row[10]),
                          "is_deleted": False}
                if include_payload:
                    result["payload"] = self._decode_payload(str(row[4]))
                    if hashlib.sha256(str(row[4]).encode("utf-8")).hexdigest() != str(row[5]):
                        raise WatchlistStorageIntegrityError("revision_payload_hash_mismatch")
                yield result

    @staticmethod
    def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
        return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})")}

    @staticmethod
    def _canonical_payload(payload: Mapping[str, Any]) -> tuple[str, str]:
        if not isinstance(payload, Mapping):
            raise ValueError("候選池 payload 必須是 object")
        raw = json.dumps(
            dict(payload), ensure_ascii=False, sort_keys=True, allow_nan=False
        )
        return raw, hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _normalize_identity_status(status: str, payload: Mapping[str, Any]) -> str:
        value = str(status or "").strip()
        if value and value not in {
            IDENTITY_STATUS_CONFLICT,
            IDENTITY_STATUS_LINKED,
            IDENTITY_STATUS_UNKNOWN,
            "unlinked",
        }:
            raise ValueError(f"unsupported decision identity status: {value}")
        payload_status = WatchlistRepository._payload_identity_status(payload)
        if value == IDENTITY_STATUS_LINKED:
            if payload_status != IDENTITY_STATUS_LINKED:
                raise ValueError("linked decision identity requires complete payload identity")
            return IDENTITY_STATUS_LINKED
        if value in {IDENTITY_STATUS_CONFLICT, "unlinked", IDENTITY_STATUS_UNKNOWN}:
            return value
        return payload_status

    @staticmethod
    def _payload_identity_status(payload: Mapping[str, Any]) -> str:
        items = payload.get("items")
        if not isinstance(items, list) or not items:
            return IDENTITY_STATUS_UNKNOWN
        identities: list[DecisionIdentity] = []
        for item in items:
            if not isinstance(item, Mapping):
                return IDENTITY_STATUS_CONFLICT
            try:
                identities.append(
                    DecisionIdentity.from_mapping(
                        item,
                        default_stock_code=str(item.get("stock_code", "")),
                    )
                )
            except (TypeError, ValueError):
                return IDENTITY_STATUS_CONFLICT
        if any(identity.identity_status == IDENTITY_STATUS_CONFLICT for identity in identities):
            return IDENTITY_STATUS_CONFLICT
        if any(identity.identity_status == "unlinked" for identity in identities):
            return "unlinked"
        if all(identity.is_linked for identity in identities):
            return IDENTITY_STATUS_LINKED
        return IDENTITY_STATUS_UNKNOWN

    def _open_read_only(self) -> sqlite3.Connection:
        conn = sqlite3.connect(f"{self.db_path.as_uri()}?mode=ro", uri=True)
        try:
            conn.execute("PRAGMA query_only=ON")
            # Inventory spans several queries; one read transaction prevents mixed revisions.
            conn.execute("BEGIN")
            return conn
        except Exception:
            conn.close()
            raise

    @staticmethod
    def _decode_payload(raw: str) -> dict[str, Any]:
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("候選池 payload 必須是 object")
        return payload

    @staticmethod
    def _current_row(
        conn: sqlite3.Connection, watchlist_id: str
    ) -> dict[str, Any] | None:
        try:
            row = conn.execute(
                "SELECT payload_json, revision, source_hash, is_deleted, last_revision_id "
                "FROM watchlists WHERE watchlist_id=?",
                (watchlist_id,),
            ).fetchone()
        except sqlite3.OperationalError as exc:
            if "no such column" in str(exc).lower():
                columns = WatchlistRepository._table_columns(conn, "watchlists")
                source_expr = "source_hash" if "source_hash" in columns else "''"
                row = conn.execute(
                    f"SELECT payload_json,revision,{source_expr} FROM watchlists WHERE watchlist_id=?",
                    (watchlist_id,),
                ).fetchone()
                if row is None:
                    return None
                return {
                    "payload_json": row[0],
                    "revision": int(row[1]),
                    "source_hash": str(row[2] or ""),
                    "is_deleted": False,
                    "last_revision_id": "",
                    "legacy_schema": True,
                }
            raise
        if row is None:
            return None
        return {
            "payload_json": row[0],
            "revision": int(row[1]),
            "source_hash": str(row[2] or ""),
            "is_deleted": bool(row[3]),
            "last_revision_id": str(row[4] or ""),
            "legacy_schema": False,
        }

    def get_current(self, watchlist_id: str) -> dict[str, Any] | None:
        """讀取 current row，供 migration／審計辨識 tombstone。"""

        storage = self.detect_storage_format()
        if storage["schema_version"] == 3:
            inventory = self.get_item_storage_inventory()
            row = next((item for item in inventory["watchlists"]
                        if item["watchlist_id"] == watchlist_id), None)
            if row is None:
                return None
            payload_json = str(row["payload_json"])
            return {"payload_json": payload_json, "revision": row["revision"],
                    "source_hash": row["source_hash"], "is_deleted": row["is_deleted"],
                    "last_revision_id": row["last_revision_id"], "legacy_schema": False,
                    "payload": row["payload"]}
        if storage["schema_version"] not in {1, 2}:
            try:
                with closing(self._open_read_only()) as conn:
                    item_storage.validate_schema(conn)
            except WatchlistStorageIntegrityError:
                raise
            except sqlite3.Error:
                pass
            raise WatchlistStorageIntegrityError("unknown_schema")


        with closing(self._open_read_only()) as conn:
            row = self._current_row(conn, watchlist_id)
        if row is None:
            return None
        result = dict(row)
        result["payload"] = self._decode_payload(str(row["payload_json"]))
        return result

    def load(
        self, watchlist_id: str, *, include_deleted: bool = False
    ) -> tuple[dict[str, Any], int] | None:
        current = self.get_current(watchlist_id)
        if current is None or (current["is_deleted"] and not include_deleted):
            return None
        return current["payload"], int(current["revision"])

    def _existing_revision(
        self, conn: sqlite3.Connection, revision_id: str
    ) -> dict[str, Any] | None:
        row = conn.execute(
            "SELECT revision_id, watchlist_id, revision, operation, payload_json, "
            "payload_hash, source_hash, identity_status, continuity_event_id, "
            "revision_of FROM watchlist_revisions WHERE revision_id=?",
            (revision_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "revision_id": str(row[0]),
            "watchlist_id": str(row[1]),
            "revision": int(row[2]),
            "operation": str(row[3]),
            "payload_json": str(row[4]),
            "payload_hash": str(row[5]),
            "source_hash": str(row[6] or ""),
            "identity_status": str(row[7] or IDENTITY_STATUS_UNKNOWN),
            "continuity_event_id": str(row[8] or ""),
            "revision_of": str(row[9] or ""),
        }

    @staticmethod
    def _assert_same_revision(
        stored: Mapping[str, Any],
        *,
        watchlist_id: str,
        operation: str,
        payload_json: str,
        payload_hash: str,
        source_hash: str,
        identity_status: str,
        continuity_event_id: str,
        revision_of: str,
    ) -> int:
        same = (
            stored["watchlist_id"] == watchlist_id
            and stored["operation"] == operation
            and stored["payload_json"] == payload_json
            and stored["payload_hash"] == payload_hash
            and stored["source_hash"] == source_hash
            and stored["identity_status"] == identity_status
            and stored["continuity_event_id"] == continuity_event_id
            and stored["revision_of"] == revision_of
        )
        if not same:
            raise RuntimeError("watchlist_revision_event_conflict")
        return int(stored["revision"])

    def _insert_revision(
        self,
        conn: sqlite3.Connection,
        *,
        revision_id: str,
        watchlist_id: str,
        revision: int,
        operation: str,
        payload_json: str,
        payload_hash: str,
        source_hash: str,
        identity_status: str,
        continuity_event_id: str,
        revision_of: str,
        created_at: str,
    ) -> None:
        conn.execute(
            "INSERT INTO watchlist_revisions("
            "revision_id,watchlist_id,revision,operation,payload_json,payload_hash,"
            "source_hash,identity_status,continuity_event_id,revision_of,created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (
                revision_id,
                watchlist_id,
                revision,
                operation,
                payload_json,
                payload_hash,
                source_hash,
                identity_status,
                continuity_event_id,
                revision_of,
                created_at,
            ),
        )

    def save(
        self,
        watchlist_id: str,
        payload: dict[str, Any],
        *,
        expected_revision: int | None,
        source_hash: str = "",
        revision_id: str | None = None,
        continuity_event_id: str | None = None,
        operation: str = "updated",
        identity_status: str = "",
        revision_of: str | None = None,
        created_at: str | None = None,
    ) -> int:
        raw, payload_hash = self._canonical_payload(payload)
        operation = str(operation or "updated").strip()
        if not operation:
            raise ValueError("watchlist operation is required")
        source_hash = str(source_hash or "")
        identity_status = self._normalize_identity_status(identity_status, payload)
        revision_id = str(revision_id or uuid4().hex).strip()
        continuity_event_id = str(continuity_event_id or "").strip()
        revision_of = str(revision_of or "").strip()
        created_at = str(created_at or self._now()).strip()
        if not revision_id:
            raise ValueError("watchlist revision_id is required")

        storage = self.detect_storage_format()
        if storage["schema_version"] == 3:
            payload_hash = item_storage.sha256_text(item_storage.canonical_json(dict(payload)))
            kwargs: dict[str, Any] = {
                "watchlist_id": watchlist_id, "payload": payload,
                "revision_id": revision_id, "operation": operation,
                "source_hash": source_hash, "identity_status": identity_status,
                "continuity_event_id": continuity_event_id,
                "revision_of": revision_of, "created_at": created_at,
                "expected_revision": expected_revision,
            }
            with closing(self._open_read_only()) as read_conn:
                duplicate = read_conn.execute(
                    "SELECT watchlist_id,operation,payload_hash,source_hash,identity_status,"
                    "continuity_event_id,revision_of,revision FROM watchlist_revisions_v3 WHERE revision_id=?",
                    (revision_id,),
                ).fetchone()
            if duplicate is not None:
                same = (str(duplicate[0]) == watchlist_id and str(duplicate[1]) == operation
                        and str(duplicate[2]) == payload_hash and str(duplicate[3] or "") == source_hash
                        and str(duplicate[4]) == identity_status
                        and str(duplicate[5] or "") == continuity_event_id
                        and (not revision_of or str(duplicate[6] or "") == revision_of))
                if not same:
                    raise RuntimeError("watchlist_revision_event_conflict")
                return int(duplicate[7])
            self._preflight_v3_save(**kwargs)
            with closing(sqlite3.connect(f"{self.db_path.as_uri()}?mode=rw", uri=True)) as conn:
                conn.execute("BEGIN IMMEDIATE")
                try:
                    revision, _, _ = item_storage.save_v3(
                        conn, **kwargs, before_commit=self._before_commit,
                    )
                    database_bytes = int(conn.execute("PRAGMA page_count").fetchone()[0]) * int(
                        conn.execute("PRAGMA page_size").fetchone()[0]
                    )
                    if database_bytes > item_storage.MAX_DATABASE_BYTES:
                        raise WatchlistStorageCapacityError("database_limit_exceeded")
                    conn.commit()
                except Exception:
                    conn.rollback()
                    raise
            return revision
        if storage["schema_version"] == 1:
            raise RuntimeError("watchlist_schema_requires_copy_on_write")
        if storage["schema_version"] == 2:
            self._preflight_legacy_save(raw, operation, watchlist_id, replace_current=True)
        elif storage["schema_version"] is None:
            raise RuntimeError("watchlist_schema_requires_copy_on_write")

        with closing(sqlite3.connect(f"{self.db_path.as_uri()}?mode=rw", uri=True)) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                stored = self._existing_revision(conn, revision_id)
                if stored is not None:
                    return self._assert_same_revision(
                        stored,
                        watchlist_id=watchlist_id,
                        operation=operation,
                        payload_json=raw,
                        payload_hash=payload_hash,
                        source_hash=source_hash,
                        identity_status=identity_status,
                        continuity_event_id=continuity_event_id,
                        revision_of=revision_of or str(stored["revision_of"]),
                    )
                current = self._current_row(conn, watchlist_id)
                if current is not None and current.get("legacy_schema"):
                    raise RuntimeError("watchlist_schema_requires_initialize")
                if current is not None:
                    # Validate the current payload before advancing the
                    # projection; a corrupt row must remain untouched.
                    self._decode_payload(str(current["payload_json"]))
                actual = None if current is None else int(current["revision"])
                if actual != expected_revision:
                    raise RuntimeError("watchlist_revision_conflict")
                current_last_revision = "" if current is None else str(
                    current["last_revision_id"]
                )
                if revision_of and revision_of != current_last_revision:
                    raise RuntimeError("watchlist_revision_conflict")
                revision = (actual or 0) + 1
                self._insert_revision(
                    conn,
                    revision_id=revision_id,
                    watchlist_id=watchlist_id,
                    revision=revision,
                    operation=operation,
                    payload_json=raw,
                    payload_hash=payload_hash,
                    source_hash=source_hash,
                    identity_status=identity_status,
                    continuity_event_id=continuity_event_id,
                    revision_of=revision_of or current_last_revision,
                    created_at=created_at,
                )
                conn.execute(
                    "INSERT INTO watchlists("
                    "watchlist_id,payload_json,revision,source_hash,is_deleted,last_revision_id) "
                    "VALUES(?,?,?,?,0,?) "
                    "ON CONFLICT(watchlist_id) DO UPDATE SET "
                    "payload_json=excluded.payload_json, revision=excluded.revision, "
                    "source_hash=excluded.source_hash, is_deleted=0, "
                    "last_revision_id=excluded.last_revision_id",
                    (
                        watchlist_id,
                        raw,
                        revision,
                        source_hash,
                        revision_id,
                    ),
                )
                self._assert_legacy_limits(conn)
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return revision

    def delete(
        self,
        watchlist_id: str,
        *,
        expected_revision: int,
        revision_id: str | None = None,
        continuity_event_id: str | None = None,
        operation: str = "removed",
        identity_status: str = "",
        revision_of: str | None = None,
        created_at: str | None = None,
    ) -> bool:
        """追加候選池 tombstone；保留 current row 與過往 payload。"""

        revision_id = str(revision_id or uuid4().hex).strip()
        continuity_event_id = str(continuity_event_id or "").strip()
        operation = str(operation or "removed").strip()
        created_at = str(created_at or self._now()).strip()
        if not revision_id:
            raise ValueError("watchlist revision_id is required")
        storage = self.detect_storage_format()
        if storage["schema_version"] == 3:
            current = self.get_current(watchlist_id)
            if current is None:
                return False
            status = self._normalize_identity_status(identity_status, current["payload"])
            requested_revision_of = str(revision_of or current["last_revision_id"] or "")
            with closing(self._open_read_only()) as read_conn:
                duplicate = read_conn.execute(
                    "SELECT watchlist_id,revision,operation,payload_hash,source_hash,identity_status,"
                    "continuity_event_id,revision_of,is_deleted FROM watchlist_revisions_v3 WHERE revision_id=?",
                    (revision_id,),
                ).fetchone()
                if duplicate is not None:
                    same = (str(duplicate[0]) == watchlist_id and str(duplicate[2]) == operation
                            and str(duplicate[4] or "") == str(current["source_hash"] or "")
                            and str(duplicate[5]) == status
                            and str(duplicate[6] or "") == continuity_event_id
                            and (not revision_of or str(duplicate[7] or "") == requested_revision_of)
                            and bool(duplicate[8]))
                    if not same:
                        raise RuntimeError("watchlist_revision_event_conflict")
                    return True
            self._preflight_v3_delete(operation)
            with closing(sqlite3.connect(f"{self.db_path.as_uri()}?mode=rw", uri=True)) as conn:
                conn.execute("BEGIN IMMEDIATE")
                try:
                    result = item_storage.delete_v3(
                        conn, watchlist_id=watchlist_id, expected_revision=expected_revision,
                        revision_id=revision_id, operation=operation,
                        continuity_event_id=continuity_event_id, identity_status=status,
                        revision_of=requested_revision_of, created_at=created_at,
                        before_commit=self._before_commit,
                    )
                    database_bytes = int(conn.execute("PRAGMA page_count").fetchone()[0]) * int(
                        conn.execute("PRAGMA page_size").fetchone()[0]
                    )
                    if database_bytes > item_storage.MAX_DATABASE_BYTES:
                        raise WatchlistStorageCapacityError("database_limit_exceeded")
                    conn.commit()
                except Exception:
                    conn.rollback()
                    raise
            return result
        if storage["schema_version"] == 1:
            raise RuntimeError("watchlist_schema_requires_copy_on_write")
        if storage["schema_version"] == 2:
            legacy_current = self.get_current(watchlist_id)
            if legacy_current is None:
                return False
            legacy_raw, _ = self._canonical_payload(legacy_current["payload"])
            self._preflight_legacy_save(legacy_raw, operation, watchlist_id, replace_current=False)
        elif storage["schema_version"] is None:
            raise RuntimeError("watchlist_schema_requires_copy_on_write")
        with closing(sqlite3.connect(f"{self.db_path.as_uri()}?mode=rw", uri=True)) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                stored = self._existing_revision(conn, revision_id)
                if stored is not None:
                    self._assert_same_revision(
                        stored,
                        watchlist_id=watchlist_id,
                        operation=operation,
                        payload_json=stored["payload_json"],
                        payload_hash=stored["payload_hash"],
                        source_hash=stored["source_hash"],
                        identity_status=stored["identity_status"],
                        continuity_event_id=continuity_event_id,
                        revision_of=revision_of or stored["revision_of"],
                    )
                    conn.commit()
                    return True
                current = self._current_row(conn, watchlist_id)
                if current is None:
                    conn.rollback()
                    return False
                if current.get("legacy_schema"):
                    raise RuntimeError("watchlist_schema_requires_initialize")
                actual = int(current["revision"])
                if actual != expected_revision:
                    raise RuntimeError("watchlist_revision_conflict")
                raw = str(current["payload_json"])
                payload = self._decode_payload(raw)
                payload_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
                identity_status = self._normalize_identity_status(identity_status, payload)
                current_last_revision = str(current["last_revision_id"] or "")
                requested_revision_of = str(revision_of or current_last_revision)
                if requested_revision_of != current_last_revision:
                    raise RuntimeError("watchlist_revision_conflict")
                revision = actual + 1
                self._insert_revision(
                    conn,
                    revision_id=revision_id,
                    watchlist_id=watchlist_id,
                    revision=revision,
                    operation=operation,
                    payload_json=raw,
                    payload_hash=payload_hash,
                    source_hash=str(current["source_hash"] or ""),
                    identity_status=identity_status,
                    continuity_event_id=continuity_event_id,
                    revision_of=requested_revision_of,
                    created_at=created_at,
                )
                conn.execute(
                    "UPDATE watchlists SET revision=?, is_deleted=1, last_revision_id=? "
                    "WHERE watchlist_id=? AND revision=?",
                    (revision, revision_id, watchlist_id, expected_revision),
                )
                self._assert_legacy_limits(conn)
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return True

    def list_ids(self) -> list[str]:
        storage = self.detect_storage_format()
        if storage["schema_version"] == 3:
            inventory = self.get_item_storage_inventory()
            return sorted(item["watchlist_id"] for item in inventory["watchlists"]
                          if not item["is_deleted"])
        if storage["schema_version"] not in {1, 2}:
            raise WatchlistStorageIntegrityError("unknown_schema")
        with closing(self._open_read_only()) as conn:
            try:
                rows = conn.execute(
                    "SELECT watchlist_id FROM watchlists WHERE is_deleted=0 "
                    "ORDER BY watchlist_id"
                ).fetchall()
            except sqlite3.OperationalError as exc:
                if "no such column" not in str(exc).lower():
                    raise
                rows = conn.execute(
                    "SELECT watchlist_id FROM watchlists ORDER BY watchlist_id"
                ).fetchall()
        return [str(row[0]) for row in rows]

    def list_revisions(
        self, watchlist_id: str, *, include_payload: bool = True
    ) -> list[dict[str, Any]]:
        storage = self.detect_storage_format()
        if storage["schema_version"] == 3:
            self.get_item_storage_inventory()
            return list(self.iter_revisions(watchlist_id, include_payload=include_payload))
        if storage["schema_version"] not in {1, 2}:
            raise WatchlistStorageIntegrityError("unknown_schema")
        with closing(self._open_read_only()) as conn:
            try:
                rows = conn.execute(
                    "SELECT revision_id,watchlist_id,revision,operation,payload_json,"
                    "payload_hash,source_hash,identity_status,continuity_event_id,"
                    "revision_of,created_at FROM watchlist_revisions "
                    "WHERE watchlist_id=? ORDER BY revision",
                    (watchlist_id,),
                ).fetchall()
            except sqlite3.OperationalError as exc:
                if "no such table" in str(exc).lower():
                    return []
                raise
        result: list[dict[str, Any]] = []
        for row in rows:
            item: dict[str, Any] = {
                "revision_id": str(row[0]),
                "watchlist_id": str(row[1]),
                "revision": int(row[2]),
                "operation": str(row[3]),
                "payload_hash": str(row[5]),
                "source_hash": str(row[6] or ""),
                "identity_status": str(row[7] or IDENTITY_STATUS_UNKNOWN),
                "continuity_event_id": str(row[8] or ""),
                "revision_of": str(row[9] or ""),
                "created_at": str(row[10]),
            }
            if include_payload:
                item["payload"] = self._decode_payload(str(row[4]))
            result.append(item)
        return result

    def import_legacy_payload(
        self,
        watchlist_id: str,
        payload: dict[str, Any],
        *,
        source_hash: str,
        import_id: str | None = None,
    ) -> int:
        """以內容雜湊作為 stable event id 的 bounded legacy import。

        這個 API 只寫指定 repository，不讀取或修改來源 JSON；相同來源重跑
        會回傳既有 revision，不會建立重複 history。
        """

        current = self.get_current(watchlist_id)
        if current is not None:
            if not current["is_deleted"] and current["payload"] == payload:
                return int(current["revision"])
            if current["is_deleted"]:
                raise RuntimeError("目標候選池已刪除；禁止自動復活")
            raise RuntimeError("目標候選池已存在不同內容；禁止覆寫")
        source_hash = str(source_hash or "").strip()
        if not source_hash:
            raise ValueError("legacy import source_hash is required")
        return self.save(
            watchlist_id,
            payload,
            expected_revision=None,
            source_hash=source_hash,
            revision_id=import_id or f"legacy-import:{source_hash}",
            continuity_event_id=import_id or f"legacy-import:{source_hash}",
            operation="legacy_import",
        )
