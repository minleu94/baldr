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
from typing import Any, Mapping
from uuid import uuid4

from app_module.dtos.decision_continuity_dtos import (
    IDENTITY_STATUS_CONFLICT,
    IDENTITY_STATUS_LINKED,
    IDENTITY_STATUS_UNKNOWN,
    DecisionIdentity,
)


class WatchlistRepository:
    """以 optimistic revision 與 append-only history 保存候選池。"""

    SCHEMA_VERSION = 2

    def __init__(self, db_path: Path, *, initialize: bool = False):
        self.db_path = Path(db_path).resolve()
        if initialize:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._initialize_schema()

    def _initialize_schema(self) -> None:
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS watchlists (
                    watchlist_id TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    source_hash TEXT NOT NULL DEFAULT '',
                    is_deleted INTEGER NOT NULL DEFAULT 0,
                    last_revision_id TEXT NOT NULL DEFAULT ''
                )
                """
            )
            columns = self._table_columns(conn, "watchlists")
            if "source_hash" not in columns:
                conn.execute(
                    "ALTER TABLE watchlists ADD COLUMN source_hash TEXT NOT NULL DEFAULT ''"
                )
            if "is_deleted" not in columns:
                conn.execute(
                    "ALTER TABLE watchlists ADD COLUMN is_deleted INTEGER NOT NULL DEFAULT 0"
                )
            if "last_revision_id" not in columns:
                conn.execute(
                    "ALTER TABLE watchlists ADD COLUMN last_revision_id TEXT NOT NULL DEFAULT ''"
                )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS watchlist_revisions (
                    revision_id TEXT PRIMARY KEY,
                    watchlist_id TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    operation TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_hash TEXT NOT NULL,
                    source_hash TEXT NOT NULL DEFAULT '',
                    identity_status TEXT NOT NULL DEFAULT 'unknown',
                    continuity_event_id TEXT NOT NULL DEFAULT '',
                    revision_of TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    UNIQUE(watchlist_id, revision)
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_watchlist_revisions_watchlist "
                "ON watchlist_revisions(watchlist_id, revision)"
            )
            # 舊版 current row 沒有 history。升級當下先建立 immutable
            # baseline，created_at 僅代表觀測／升級時間，不冒充原始決策時間。
            legacy_rows = conn.execute(
                "SELECT watchlist_id,payload_json,revision,source_hash,"
                "is_deleted,last_revision_id FROM watchlists"
            ).fetchall()
            for row in legacy_rows:
                watchlist_id = str(row[0])
                revision = int(row[2])
                existing = conn.execute(
                    "SELECT revision_id FROM watchlist_revisions "
                    "WHERE watchlist_id=? AND revision=?",
                    (watchlist_id, revision),
                ).fetchone()
                last_revision_id = str(row[5] or "")
                if existing is None:
                    payload_json = str(row[1])
                    payload = self._decode_payload(payload_json)
                    baseline_id = f"legacy-baseline:{watchlist_id}:{revision}"
                    conn.execute(
                        "INSERT INTO watchlist_revisions("
                        "revision_id,watchlist_id,revision,operation,payload_json,"
                        "payload_hash,source_hash,identity_status,continuity_event_id,"
                        "revision_of,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            baseline_id,
                            watchlist_id,
                            revision,
                            "legacy_baseline",
                            payload_json,
                            hashlib.sha256(payload_json.encode("utf-8")).hexdigest(),
                            str(row[3] or ""),
                            self._payload_identity_status(payload),
                            "",
                            "",
                            self._now(),
                        ),
                    )
                    last_revision_id = baseline_id
                elif not last_revision_id:
                    last_revision_id = str(existing[0])
                if last_revision_id != str(row[5] or ""):
                    conn.execute(
                        "UPDATE watchlists SET last_revision_id=? WHERE watchlist_id=?",
                        (last_revision_id, watchlist_id),
                    )

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
        return sqlite3.connect(f"{self.db_path.as_uri()}?mode=ro", uri=True)

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
                row = conn.execute(
                    "SELECT payload_json, revision, source_hash FROM watchlists "
                    "WHERE watchlist_id=?",
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
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return True

    def list_ids(self) -> list[str]:
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
