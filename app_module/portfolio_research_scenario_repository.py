"""明示私人路由的人選情境封存；唯讀重開不初始化或遷移資料庫。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import sqlite3
from typing import Any

from app_module.personal_data_paths import PersonalDataPaths
from app_module.personal_paper_store_paths import PersonalStoreCustody
from app_module.personal_store_routes import PersonalStoreDomain, PersonalStoreMode, PersonalStoreRoute, PersonalStoreRouteError
from app_module.portfolio_allocation_dtos import _validate_int, _validate_non_empty, _validate_sha256
from app_module.portfolio_research_scenario_artifact import (
    MAX_SCENARIO_BYTES, decode_scenario_artifact, encode_scenario_artifact, scenario_artifact_id,
)
from app_module.portfolio_research_scenario_service import PortfolioResearchScenarioComparison, _aware


_SCHEMA = "portfolio-research-store.v1"
_COLUMNS = (
    "artifact_id", "account_kind", "portfolio_id", "snapshot_id", "decision_at",
    "saved_at", "input_hash", "payload_json",
)


@dataclass(frozen=True)
class SavedPortfolioResearchScenario:
    artifact_id: str
    saved_at: datetime
    comparison: PortfolioResearchScenarioComparison


class PortfolioResearchScenarioRepository:
    def __init__(self, *, route: PersonalStoreRoute, personal_paths: PersonalDataPaths | None = None) -> None:
        if not isinstance(route, PersonalStoreRoute) or route.domain is not PersonalStoreDomain.PORTFOLIO_RESEARCH:
            raise PersonalStoreRouteError("portfolio_research_domain_required")
        self._route = route
        self._custody = PersonalStoreCustody(route, personal_paths)
        self.db_path = route.read_source

    @property
    def writable(self) -> bool:
        return self._route.mode is PersonalStoreMode.PERSONAL and self._route.write_target == self.db_path

    @staticmethod
    def _validate_schema(conn: sqlite3.Connection) -> None:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
        if tables != {"scenario_store_meta", "scenario_archives"}:
            raise ValueError("scenario store schema tables mismatch")
        meta = conn.execute("SELECT schema_version FROM scenario_store_meta").fetchall()
        if len(meta) != 1 or meta[0][0] != _SCHEMA:
            raise ValueError("unsupported scenario store schema")
        for table, expected in (("scenario_store_meta", ("schema_version",)), ("scenario_archives", _COLUMNS)):
            info = conn.execute(f"PRAGMA table_info({table})").fetchall()
            if tuple(row[1] for row in info) != expected:
                raise ValueError("scenario store schema columns mismatch")
            for row in info:
                expected_type = "BLOB" if row[1] == "payload_json" else "TEXT"
                if row[2] != expected_type or row[3] != 1 or row[5] != int(row[1] in {"schema_version", "artifact_id"}):
                    raise ValueError("scenario store column contract mismatch")
        indices = conn.execute("PRAGMA index_list(scenario_archives)").fetchall()
        selected = [row for row in indices if row[1] == "scenario_account_time"]
        if len(selected) != 1 or selected[0][2] != 0 or selected[0][4] != 0:
            raise ValueError("scenario store account index missing or invalid")
        parts = conn.execute("PRAGMA index_xinfo(scenario_account_time)").fetchall()
        keys = tuple((row[2], row[3], row[4]) for row in parts if row[5] == 1)
        if keys != (("account_kind", 0, "BINARY"), ("portfolio_id", 0, "BINARY"),
                    ("saved_at", 1, "BINARY"), ("artifact_id", 0, "BINARY")):
            raise ValueError("scenario store account index contract mismatch")

    @staticmethod
    def _create_schema(conn: sqlite3.Connection) -> None:
        conn.execute("CREATE TABLE scenario_store_meta (schema_version TEXT NOT NULL PRIMARY KEY)")
        conn.execute("INSERT INTO scenario_store_meta VALUES (?)", (_SCHEMA,))
        conn.execute("""CREATE TABLE scenario_archives (
            artifact_id TEXT NOT NULL PRIMARY KEY, account_kind TEXT NOT NULL,
            portfolio_id TEXT NOT NULL, snapshot_id TEXT NOT NULL, decision_at TEXT NOT NULL,
            saved_at TEXT NOT NULL, input_hash TEXT NOT NULL, payload_json BLOB NOT NULL
        )""")
        conn.execute("CREATE INDEX scenario_account_time ON scenario_archives(account_kind, portfolio_id, saved_at DESC, artifact_id ASC)")

    @staticmethod
    def _selected(account_kind: str, portfolio_id: str) -> None:
        if account_kind not in {"manual", "user_declared", "paper"}:
            raise ValueError("unsupported selected scenario account kind")
        if _validate_non_empty("portfolio_id", portfolio_id) != portfolio_id:
            raise ValueError("selected scenario account id must be canonical")

    @staticmethod
    def _decode(row: sqlite3.Row, *, account_kind: str, portfolio_id: str) -> SavedPortfolioResearchScenario:
        if (row["account_kind"], row["portfolio_id"]) != (account_kind, portfolio_id):
            raise ValueError("saved scenario belongs to another selected account")
        payload = row["payload_json"]
        if type(payload) is not bytes or scenario_artifact_id(payload) != row["artifact_id"]:
            raise ValueError("saved scenario artifact hash mismatch")
        comparison = decode_scenario_artifact(payload)
        account = comparison.account
        expected = (account.account_kind, account.portfolio_id, account.snapshot_id,
                    comparison.decision_at.isoformat(), comparison.input_hash)
        actual = tuple(row[name] for name in ("account_kind", "portfolio_id", "snapshot_id", "decision_at", "input_hash"))
        if actual != expected:
            raise ValueError("saved scenario index differs from artifact")
        if type(row["saved_at"]) is not str:
            raise ValueError("saved scenario clock type mismatch")
        saved_at = _aware("saved_at", datetime.fromisoformat(row["saved_at"]))
        if saved_at.isoformat() != row["saved_at"] or saved_at.tzinfo != timezone.utc or saved_at < comparison.decision_at:
            raise ValueError("saved scenario clock precedes decision or is not canonical")
        return SavedPortfolioResearchScenario(row["artifact_id"], saved_at, comparison)

    @staticmethod
    def _load(conn: sqlite3.Connection, artifact_id: str, *, account_kind: str, portfolio_id: str) -> SavedPortfolioResearchScenario | None:
        # 在同一 transaction 先核大小，避免把超大／損壞 payload 拉進 Python。
        meta = conn.execute("SELECT account_kind,portfolio_id,typeof(payload_json),length(payload_json) FROM scenario_archives WHERE artifact_id=?", (artifact_id,)).fetchone()
        if meta is None:
            return None
        if (meta[0], meta[1]) != (account_kind, portfolio_id):
            raise ValueError("saved scenario belongs to another selected account")
        if meta[2] != "blob" or type(meta[3]) is not int or not 0 < meta[3] <= MAX_SCENARIO_BYTES:
            raise ValueError("saved scenario payload type or size rejected")
        row = conn.execute("SELECT * FROM scenario_archives WHERE artifact_id=?", (artifact_id,)).fetchone()
        if row is None:
            raise ValueError("saved scenario vanished within read transaction")
        return PortfolioResearchScenarioRepository._decode(row, account_kind=account_kind, portfolio_id=portfolio_id)

    def append(self, comparison: PortfolioResearchScenarioComparison, *, saved_at: datetime) -> SavedPortfolioResearchScenario:
        if self._route.mode is not PersonalStoreMode.PERSONAL or self._route.write_target != self.db_path:
            raise PersonalStoreRouteError("scenario_store_read_only")
        _aware("saved_at", saved_at)
        if saved_at < comparison.decision_at:
            raise ValueError("saved_at precedes scenario decision")
        saved_at = saved_at.astimezone(timezone.utc)
        payload = encode_scenario_artifact(comparison)
        artifact_id = scenario_artifact_id(payload)
        comparison = decode_scenario_artifact(payload)
        existed = self._custody.exists(self.db_path)
        self._custody.prepare_parent(self.db_path)
        self._custody.sqlite_guard(self.db_path)
        conn = sqlite3.connect(self._custody.io(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("BEGIN IMMEDIATE")
            self._custody.sqlite_guard(self.db_path)
            tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()
            if not tables and not existed:
                self._create_schema(conn)
            self._validate_schema(conn)
            account = comparison.account
            existing = self._load(conn, artifact_id, account_kind=account.account_kind, portfolio_id=account.portfolio_id)
            if existing is not None:
                if encode_scenario_artifact(existing.comparison) != payload:
                    raise ValueError("saved scenario content collision")
                conn.rollback()
                return existing
            values: tuple[Any, ...] = (artifact_id, account.account_kind, account.portfolio_id, account.snapshot_id,
                comparison.decision_at.isoformat(), saved_at.isoformat(), comparison.input_hash, payload)
            conn.execute("INSERT INTO scenario_archives VALUES (?,?,?,?,?,?,?,?)", values)
            self._custody.sqlite_guard(self.db_path)
            conn.commit()
            return SavedPortfolioResearchScenario(artifact_id, saved_at, comparison)
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def get_exact(self, artifact_id: str, *, account_kind: str, portfolio_id: str) -> SavedPortfolioResearchScenario | None:
        _validate_sha256("artifact_id", artifact_id)
        self._selected(account_kind, portfolio_id)
        if not self._custody.exists(self.db_path):
            return None
        with self._custody.read_sqlite(self.db_path) as conn:
            conn.execute("BEGIN")
            try:
                self._validate_schema(conn)
                return self._load(conn, artifact_id, account_kind=account_kind, portfolio_id=portfolio_id)
            finally:
                conn.rollback()

    def list_artifact_ids(self, *, account_kind: str, portfolio_id: str, limit: int = 25) -> tuple[str, ...]:
        """有界索引供選單定位；使用者選取後必須以 get_exact 核原內容。"""
        self._selected(account_kind, portfolio_id)
        _validate_int("limit", limit, minimum=1, maximum=200)
        if not self._custody.exists(self.db_path):
            return ()
        with self._custody.read_sqlite(self.db_path) as conn:
            conn.execute("BEGIN")
            try:
                self._validate_schema(conn)
                rows = conn.execute("SELECT artifact_id FROM scenario_archives WHERE account_kind=? AND portfolio_id=? ORDER BY saved_at DESC,artifact_id ASC LIMIT ?", (account_kind, portfolio_id, limit)).fetchall()
                return tuple(_validate_sha256("artifact_id", row[0]) for row in rows)
            finally:
                conn.rollback()
