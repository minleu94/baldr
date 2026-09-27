"""Research Run Registry SQLite metadata repository."""

from __future__ import annotations

from dataclasses import fields
from contextlib import closing, contextmanager
import re
import sqlite3
from pathlib import Path
from typing import Any, Iterator

from app_module.research_run_dtos import (
    ResearchRunMetadataDTO,
    canonical_json,
    normalize_research_run_json_value,
    parse_json_list,
    parse_json_object,
)


class ResearchRunRepositoryError(Exception):
    """Research Run Repository 基底例外。"""


class ResearchRunConflictError(ResearchRunRepositoryError):
    """同一 run_id 對應到不同 payload hash。"""


class ResearchRunRepository:
    """統一研究 run metadata 的 SQLite repository。

    schema 僅由明確寫入入口遷移，查詢使用 query_only connection。
    Parquet 寫入、crash recovery 與 integrity verification 由 service 擁有。
    """

    SCHEMA_NAME = "research_runs"
    SCHEMA_VERSION = 2

    PORTFOLIO_RESULT_REQUIRED_MARKER = "portfolio_result_required"
    PORTFOLIO_RESULT_DESCRIPTOR_KEY = "portfolio_result_sidecar"
    PORTFOLIO_RESULT_SCHEMA_VERSION = "recommendation-portfolio-result.v1"
    PORTFOLIO_RESULT_SCHEMA_REVISION = 1
    PORTFOLIO_RESULT_DESCRIPTOR_KEYS = frozenset(
        {
            "schema_version",
            "schema_revision",
            "registry_run_id",
            "portfolio_parent_id",
            "relative_path",
            "raw_payload_sha256",
            "payload_hash",
            "equity_parquet_sha256",
            "trades_parquet_sha256",
        }
    )

    JSON_FIELD_MAP = {
        "original_input": "original_input_json",
        "normalized_params": "normalized_params_json",
        "fallback_reason": "fallback_reason_json",
        "universe": "universe_json",
        "data_manifest": "data_manifest_json",
        "metrics": "metrics_json",
        "regime_breakdown": "regime_breakdown_json",
        "benchmark_results": "benchmark_results_json",
    }

    def __init__(self, config: Any):
        self.config = config
        self.db_path = Path(config.research_run_db_file)

    @contextmanager
    def _read_connection(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path.resolve().as_uri() + "?mode=ro", uri=True)
        conn.execute("PRAGMA query_only = ON")
        try:
            row = conn.execute(
                "SELECT version FROM schema_version WHERE name = ?", (self.SCHEMA_NAME,)
            ).fetchone()
            if row is None or int(row[0]) != self.SCHEMA_VERSION:
                raise ResearchRunRepositoryError("Registry schema version 不相容；需由寫入 owner 明確遷移")
            yield conn
        except sqlite3.Error as exc:
            raise ResearchRunRepositoryError(f"Registry schema 無法唯讀載入: {exc}") from exc
        finally:
            conn.close()

    @contextmanager
    def _write_connection(self) -> Iterator[sqlite3.Connection]:
        with closing(sqlite3.connect(self.db_path)) as conn:
            with conn:
                yield conn

    def ensure_schema(self) -> None:
        """執行可重入 schema migration。"""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._write_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_version (
                    name TEXT PRIMARY KEY,
                    version INTEGER NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            current = conn.execute(
                "SELECT version FROM schema_version WHERE name = ?",
                (self.SCHEMA_NAME,),
            ).fetchone()
            current_version = int(current[0]) if current else 0
            if current_version > self.SCHEMA_VERSION:
                raise ResearchRunRepositoryError("拒絕降版未知 Registry schema")
            if current_version == self.SCHEMA_VERSION:
                return

            if current_version < 1:
                self._migrate_v1(conn)
                current_version = 1
            if current_version < 2:
                self._migrate_v2(conn)

            conn.execute(
                """
                INSERT INTO schema_version(name, version, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(name) DO UPDATE SET
                    version = excluded.version,
                    updated_at = excluded.updated_at
                """,
                (self.SCHEMA_NAME, self.SCHEMA_VERSION),
            )

    def _migrate_v1(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS research_runs (
                run_id TEXT PRIMARY KEY,
                run_name TEXT NOT NULL,
                run_type TEXT NOT NULL,
                strategy_id TEXT NOT NULL DEFAULT '',
                strategy_version TEXT NOT NULL DEFAULT '',
                parameter_contract_version TEXT NOT NULL DEFAULT '',
                original_input_json TEXT NOT NULL DEFAULT '{}',
                normalized_params_json TEXT NOT NULL DEFAULT '{}',
                fallback_reason_json TEXT NOT NULL DEFAULT '{}',
                universe_json TEXT NOT NULL DEFAULT '[]',
                start_date TEXT NOT NULL DEFAULT '',
                end_date TEXT NOT NULL DEFAULT '',
                data_cutoff_date TEXT NOT NULL DEFAULT '',
                data_fingerprint TEXT NOT NULL DEFAULT '',
                fingerprint_algorithm TEXT NOT NULL DEFAULT '',
                data_manifest_json TEXT NOT NULL DEFAULT '{}',
                capital_cents INTEGER NOT NULL DEFAULT 0,
                fee_bp_x100 INTEGER NOT NULL DEFAULT 0,
                slippage_bp_x100 INTEGER NOT NULL DEFAULT 0,
                stop_loss_bp INTEGER,
                take_profit_bp INTEGER,
                execution_price TEXT NOT NULL DEFAULT '',
                sizing_mode TEXT NOT NULL DEFAULT '',
                metrics_json TEXT NOT NULL DEFAULT '{}',
                regime_breakdown_json TEXT NOT NULL DEFAULT '{}',
                benchmark_results_json TEXT NOT NULL DEFAULT '{}',
                payload_hash TEXT NOT NULL,
                equity_path TEXT NOT NULL DEFAULT '',
                equity_parquet_hash TEXT NOT NULL DEFAULT '',
                trades_path TEXT NOT NULL DEFAULT '',
                trades_parquet_hash TEXT NOT NULL DEFAULT '',
                is_archived INTEGER NOT NULL DEFAULT 0,
                promoted_version_id TEXT,
                promotion_reconciliation_status TEXT NOT NULL DEFAULT 'none',
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_research_runs_created_at "
            "ON research_runs(created_at)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_research_runs_type_strategy "
            "ON research_runs(run_type, strategy_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_research_runs_archived "
            "ON research_runs(is_archived)"
        )

    def _migrate_v2(self, conn: sqlite3.Connection) -> None:
        self._add_column_if_missing(
            conn,
            "research_runs",
            "storage_state",
            "TEXT NOT NULL DEFAULT 'committed'",
        )
        self._add_column_if_missing(
            conn,
            "research_runs",
            "integrity_status",
            "TEXT NOT NULL DEFAULT 'valid'",
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_research_runs_storage_state "
            "ON research_runs(storage_state)"
        )

    def _add_column_if_missing(
        self,
        conn: sqlite3.Connection,
        table_name: str,
        column_name: str,
        definition: str,
    ) -> None:
        columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table_name})")}
        if column_name not in columns:
            conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")

    def insert_metadata(
        self, metadata: ResearchRunMetadataDTO, *, staging: bool = False
    ) -> ResearchRunMetadataDTO:
        self.ensure_schema()
        existing = self.get_metadata(metadata.run_id)
        if existing:
            if staging:
                raise ResearchRunConflictError("另一個保存 owner 已保留此 run_id")
            if existing.payload_hash != metadata.payload_hash:
                raise ResearchRunConflictError(
                    f"run_id 已存在但 payload_hash 不一致: {metadata.run_id}"
                )
            return existing

        row = self._dto_to_row(metadata)
        if staging:
            row.update(storage_state="staging", integrity_status="pending")
        columns = list(row.keys())
        placeholders = ", ".join("?" for _ in columns)
        column_sql = ", ".join(columns)

        with self._write_connection() as conn:
            conn.execute(
                f"INSERT INTO research_runs ({column_sql}) VALUES ({placeholders})",
                tuple(row[column] for column in columns),
            )
        return metadata

    def get_metadata(self, run_id: str) -> ResearchRunMetadataDTO | None:
        row = self.get_raw_metadata_row(run_id)
        if row is None:
            return None
        return self._row_to_dto(row)

    def get_raw_metadata_row(self, run_id: str) -> dict[str, Any] | None:
        if not self.db_path.exists():
            return None
        with self._read_connection() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM research_runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        if row is None:
            return None
        return dict(row)

    def update_storage_fields(
        self,
        run_id: str,
        *,
        equity_path: str | None = None,
        equity_parquet_hash: str | None = None,
        trades_path: str | None = None,
        trades_parquet_hash: str | None = None,
        storage_state: str | None = None,
        integrity_status: str | None = None,
    ) -> None:
        self.ensure_schema()
        updates: dict[str, Any] = {}
        if equity_path is not None:
            updates["equity_path"] = equity_path
        if equity_parquet_hash is not None:
            updates["equity_parquet_hash"] = equity_parquet_hash
        if trades_path is not None:
            updates["trades_path"] = trades_path
        if trades_parquet_hash is not None:
            updates["trades_parquet_hash"] = trades_parquet_hash
        if storage_state is not None:
            updates["storage_state"] = storage_state
        if integrity_status is not None:
            updates["integrity_status"] = integrity_status
        if not updates:
            return

        set_sql = ", ".join(f"{column} = ?" for column in updates)
        params = [*updates.values(), run_id]
        with self._write_connection() as conn:
            conn.execute(
                f"UPDATE research_runs SET {set_sql} WHERE run_id = ?",
                params,
            )

    @staticmethod
    def _is_sha256(value: object) -> bool:
        return (
            type(value) is str
            and re.fullmatch(r"sha256:[0-9a-f]{64}", value) is not None
        )

    @staticmethod
    def _is_safe_relative_artifact_path(value: object) -> bool:
        if (
            type(value) is not str
            or not value
            or value != value.strip()
            or "\\" in value
            or ":" in value
            or "\x00" in value
        ):
            return False
        parts = value.split("/")
        return all(part not in {"", ".", ".."} for part in parts)

    def _resolved_parquet_path(self, value: object) -> Path | None:
        if type(value) is not str or not Path(value).is_absolute():
            return None
        try:
            parquet_root = Path(self.config.research_run_parquet_dir).resolve()
            candidate = Path(value).resolve()
            candidate.relative_to(parquet_root)
        except (OSError, RuntimeError, ValueError):
            return None
        if candidate == parquet_root:
            return None
        return candidate

    def _validate_portfolio_result_finalization(
        self,
        run_id: str,
        expected_payload_hash: str,
        finalized_metadata: ResearchRunMetadataDTO,
    ) -> None:
        if not isinstance(finalized_metadata, ResearchRunMetadataDTO):
            raise ResearchRunRepositoryError("finalized_metadata DTO 型別無效")
        if type(run_id) is not str or not run_id or run_id != run_id.strip():
            raise ResearchRunRepositoryError("portfolio finalize run_id 無效")
        if type(expected_payload_hash) is not str or not expected_payload_hash:
            raise ResearchRunRepositoryError("expected_payload_hash 不可為空")
        if finalized_metadata.run_id != run_id:
            raise ResearchRunRepositoryError("finalized metadata run_id 不相符")
        if finalized_metadata.run_type != "recommendation_portfolio":
            raise ResearchRunRepositoryError(
                "portfolio finalize metadata run_type 必須是 recommendation_portfolio"
            )
        if not self._is_sha256(finalized_metadata.payload_hash):
            raise ResearchRunRepositoryError("finalized payload_hash 格式無效")
        if finalized_metadata.payload_hash == expected_payload_hash:
            raise ResearchRunRepositoryError(
                "finalized payload_hash 必須反映 manifest 更新"
            )
        for label, value in (
            ("equity_path", finalized_metadata.equity_path),
            ("trades_path", finalized_metadata.trades_path),
        ):
            if self._resolved_parquet_path(value) is None:
                raise ResearchRunRepositoryError(
                    f"{label} 必須是位於 research_run_parquet_dir 下的 absolute path"
                )
        equity_path = self._resolved_parquet_path(finalized_metadata.equity_path)
        trades_path = self._resolved_parquet_path(finalized_metadata.trades_path)
        if equity_path is None or trades_path is None:
            raise ResearchRunRepositoryError("Parquet absolute path 無法解析")
        if equity_path == trades_path:
            raise ResearchRunRepositoryError("equity 與 trades 路徑必須分離")
        if not self._is_sha256(finalized_metadata.equity_parquet_hash):
            raise ResearchRunRepositoryError("equity Parquet hash 格式無效")
        if not self._is_sha256(finalized_metadata.trades_parquet_hash):
            raise ResearchRunRepositoryError("trades Parquet hash 格式無效")

        manifest = finalized_metadata.data_manifest
        if type(manifest) is not dict:
            raise ResearchRunRepositoryError("data_manifest 必須是 object")
        if manifest.get(self.PORTFOLIO_RESULT_REQUIRED_MARKER) is not True:
            raise ResearchRunRepositoryError("portfolio result required marker 缺失")
        descriptor = manifest.get(self.PORTFOLIO_RESULT_DESCRIPTOR_KEY)
        if type(descriptor) is not dict:
            raise ResearchRunRepositoryError("portfolio result descriptor 缺失")
        if set(descriptor) != self.PORTFOLIO_RESULT_DESCRIPTOR_KEYS:
            raise ResearchRunRepositoryError(
                "portfolio result descriptor 欄位不完整或含未知欄位"
            )
        if descriptor.get("schema_version") != self.PORTFOLIO_RESULT_SCHEMA_VERSION:
            raise ResearchRunRepositoryError("portfolio result schema_version 不支援")
        revision = descriptor.get("schema_revision")
        if type(revision) is not int or revision != self.PORTFOLIO_RESULT_SCHEMA_REVISION:
            raise ResearchRunRepositoryError("portfolio result schema_revision 不支援")
        if descriptor.get("registry_run_id") != run_id:
            raise ResearchRunRepositoryError("portfolio result Registry identity 不相符")
        parent_id = descriptor.get("portfolio_parent_id")
        if (
            type(parent_id) is not str
            or not parent_id
            or parent_id != parent_id.strip()
            or parent_id == run_id
        ):
            raise ResearchRunRepositoryError("portfolio parent identity 無效")
        if not self._is_safe_relative_artifact_path(descriptor.get("relative_path")):
            raise ResearchRunRepositoryError("portfolio sidecar path 必須是安全相對路徑")
        parquet_root = Path(self.config.research_run_parquet_dir).resolve()
        if descriptor["relative_path"] in {
            equity_path.relative_to(parquet_root).as_posix(),
            trades_path.relative_to(parquet_root).as_posix(),
        }:
            raise ResearchRunRepositoryError("portfolio sidecar path 必須與 Parquet 路徑分離")
        for key in (
            "raw_payload_sha256",
            "payload_hash",
            "equity_parquet_sha256",
            "trades_parquet_sha256",
        ):
            if not self._is_sha256(descriptor.get(key)):
                raise ResearchRunRepositoryError(f"portfolio descriptor {key} 格式無效")
        if descriptor["equity_parquet_sha256"] != finalized_metadata.equity_parquet_hash:
            raise ResearchRunRepositoryError("portfolio descriptor equity hash 不相符")
        if descriptor["trades_parquet_sha256"] != finalized_metadata.trades_parquet_hash:
            raise ResearchRunRepositoryError("portfolio descriptor trades hash 不相符")

    def finalize_portfolio_result_staging(
        self,
        run_id: str,
        *,
        expected_payload_hash: str,
        finalized_metadata: ResearchRunMetadataDTO,
    ) -> ResearchRunMetadataDTO:
        """以 CAS 將 staging portfolio row 的 manifest 與檔案綁定一次定稿。

        此窄 command 僅供 portfolio-result publisher 使用；通用
        ``update_storage_fields`` 的既有語意不變。B2 service 呼叫前必須完成
        sidecar/Parquet 原始 bytes 與 canonical hash 驗證，並重算 Registry
        payload_hash；本 command 負責核對 staging CAS、metadata identity 與
        manifest 只新增 marker/descriptor。
        """

        self._validate_portfolio_result_finalization(
            run_id, expected_payload_hash, finalized_metadata
        )
        self.ensure_schema()
        unchanged_fields = {
            "data_manifest",
            "payload_hash",
            "equity_path",
            "equity_parquet_hash",
            "trades_path",
            "trades_parquet_hash",
        }

        with self._write_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM research_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            if row is None:
                raise ResearchRunConflictError("portfolio finalize run_id 不存在")
            current_row = dict(row)
            if current_row["run_type"] != "recommendation_portfolio":
                raise ResearchRunConflictError("Registry row 不是 recommendation_portfolio")
            if (
                current_row["storage_state"] != "staging"
                or current_row["integrity_status"] != "pending"
            ):
                raise ResearchRunConflictError(
                    "portfolio finalize 僅允許 staging/pending Registry row"
                )
            if current_row["payload_hash"] != expected_payload_hash:
                raise ResearchRunConflictError("portfolio finalize base payload_hash 已變更")

            current_metadata = self._row_to_dto(current_row)
            current_manifest = current_metadata.data_manifest
            finalized_manifest = finalized_metadata.data_manifest
            if self.PORTFOLIO_RESULT_DESCRIPTOR_KEY in current_manifest:
                raise ResearchRunRepositoryError(
                    "staging manifest 已有 portfolio result descriptor，不可覆寫"
                )
            expected_manifest_keys = set(current_manifest) | {
                self.PORTFOLIO_RESULT_REQUIRED_MARKER,
                self.PORTFOLIO_RESULT_DESCRIPTOR_KEY,
            }
            if set(finalized_manifest) != expected_manifest_keys:
                raise ResearchRunRepositoryError(
                    "finalize manifest 只能新增 portfolio result marker 與 descriptor"
                )
            for key, value in current_manifest.items():
                finalized_value = normalize_research_run_json_value(
                    finalized_manifest.get(key)
                )
                if finalized_value != value:
                    raise ResearchRunRepositoryError(
                        f"portfolio finalize 不得變更既有 manifest 欄位: {key}"
                    )
            for field_info in fields(ResearchRunMetadataDTO):
                name = field_info.name
                if (
                    name not in unchanged_fields
                    and getattr(current_metadata, name) != getattr(finalized_metadata, name)
                ):
                    raise ResearchRunRepositoryError(
                        f"portfolio finalize 不得變更既有 metadata 欄位: {name}"
                    )

            finalized_row = self._dto_to_row(finalized_metadata)
            cursor = conn.execute(
                """
                UPDATE research_runs
                SET data_manifest_json = ?,
                    payload_hash = ?,
                    equity_path = ?,
                    equity_parquet_hash = ?,
                    trades_path = ?,
                    trades_parquet_hash = ?
                WHERE run_id = ?
                  AND run_type = 'recommendation_portfolio'
                  AND storage_state = 'staging'
                  AND integrity_status = 'pending'
                  AND payload_hash = ?
                """,
                (
                    finalized_row["data_manifest_json"],
                    finalized_row["payload_hash"],
                    finalized_row["equity_path"],
                    finalized_row["equity_parquet_hash"],
                    finalized_row["trades_path"],
                    finalized_row["trades_parquet_hash"],
                    run_id,
                    expected_payload_hash,
                ),
            )
            if cursor.rowcount != 1:
                raise ResearchRunConflictError(
                    "portfolio finalize CAS 未命中唯一 staging row"
                )

        return finalized_metadata

    def _transition_portfolio_result_state(
        self,
        run_id: str,
        *,
        expected_payload_hash: str,
        expected_data_manifest: dict[str, Any],
        from_storage_state: str,
        from_integrity_status: str,
        to_storage_state: str,
        to_integrity_status: str,
    ) -> None:
        descriptor = expected_data_manifest.get(self.PORTFOLIO_RESULT_DESCRIPTOR_KEY)
        if (
            expected_data_manifest.get(self.PORTFOLIO_RESULT_REQUIRED_MARKER) is not True
            or type(descriptor) is not dict
            or set(descriptor) != self.PORTFOLIO_RESULT_DESCRIPTOR_KEYS
            or descriptor.get("registry_run_id") != run_id
        ):
            raise ResearchRunRepositoryError(
                "portfolio result state transition 缺少 identity-bound descriptor"
            )
        manifest_json = canonical_json(
            normalize_research_run_json_value(expected_data_manifest)
        )
        self.ensure_schema()
        with self._write_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            cursor = conn.execute(
                """
                UPDATE research_runs
                SET storage_state = ?, integrity_status = ?
                WHERE run_id = ?
                  AND run_type = 'recommendation_portfolio'
                  AND storage_state = ?
                  AND integrity_status = ?
                  AND payload_hash = ?
                  AND data_manifest_json = ?
                """,
                (
                    to_storage_state,
                    to_integrity_status,
                    run_id,
                    from_storage_state,
                    from_integrity_status,
                    expected_payload_hash,
                    manifest_json,
                ),
            )
            if cursor.rowcount != 1:
                raise ResearchRunConflictError(
                    "portfolio result storage state CAS 未命中唯一預期 row"
                )

    def mark_portfolio_result_files_ready(
        self,
        run_id: str,
        *,
        expected_payload_hash: str,
        expected_data_manifest: dict[str, Any],
    ) -> None:
        """僅將已 finalize 的 portfolio staging row CAS 至 files_ready。"""

        self._transition_portfolio_result_state(
            run_id,
            expected_payload_hash=expected_payload_hash,
            expected_data_manifest=expected_data_manifest,
            from_storage_state="staging",
            from_integrity_status="pending",
            to_storage_state="files_ready",
            to_integrity_status="pending",
        )

    def mark_portfolio_result_committed(
        self,
        run_id: str,
        *,
        expected_payload_hash: str,
        expected_data_manifest: dict[str, Any],
    ) -> None:
        """僅將已驗證完整 artifacts 的 portfolio files_ready row CAS commit。"""

        self._transition_portfolio_result_state(
            run_id,
            expected_payload_hash=expected_payload_hash,
            expected_data_manifest=expected_data_manifest,
            from_storage_state="files_ready",
            from_integrity_status="pending",
            to_storage_state="committed",
            to_integrity_status="valid",
        )

    def mark_portfolio_result_failed(
        self,
        run_id: str,
        *,
        expected_payload_hash: str,
        expected_data_manifest: dict[str, Any],
        expected_storage_state: str,
        expected_integrity_status: str,
    ) -> None:
        """以 CAS 標記失敗的 opt-in portfolio publisher row。

        staging row 可尚未完成 sidecar descriptor；files_ready row 則必須已綁定
        descriptor。兩者都必須保留明確 marker，避免這個窄轉移影響舊 publisher。
        """

        descriptor_key = self.PORTFOLIO_RESULT_DESCRIPTOR_KEY
        if (
            self.PORTFOLIO_RESULT_REQUIRED_MARKER not in expected_data_manifest
            and descriptor_key not in expected_data_manifest
        ):
            raise ResearchRunRepositoryError(
                "portfolio result failure transition 缺少 reserved marker/descriptor"
            )
        # Failure-only transition may quarantine a malformed marker/descriptor.
        # The exact manifest JSON remains part of the CAS predicate, so it cannot
        # overwrite a corrected, committed, or otherwise changed row.
        allowed_from = {
            ("staging", "pending"),
            ("files_ready", "pending"),
        }
        if (expected_storage_state, expected_integrity_status) not in allowed_from:
            raise ResearchRunRepositoryError(
                "portfolio result failure transition source state 無效"
            )
        manifest_json = canonical_json(
            normalize_research_run_json_value(expected_data_manifest)
        )
        self.ensure_schema()
        with self._write_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            cursor = conn.execute(
                """
                UPDATE research_runs
                SET storage_state = 'failed', integrity_status = 'failed'
                WHERE run_id = ?
                  AND run_type = 'recommendation_portfolio'
                  AND storage_state = ?
                  AND integrity_status = ?
                  AND payload_hash = ?
                  AND data_manifest_json = ?
                """,
                (
                    run_id,
                    expected_storage_state,
                    expected_integrity_status,
                    expected_payload_hash,
                    manifest_json,
                ),
            )
            if cursor.rowcount != 1:
                raise ResearchRunConflictError(
                    "portfolio result failed CAS 未命中唯一預期 row"
                )

    def list_uncommitted_rows(self) -> list[dict[str, Any]]:
        if not self.db_path.exists():
            return []
        with self._read_connection() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT * FROM research_runs
                WHERE storage_state IN ('staging', 'files_ready')
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def list_metadata(self, *, include_archived: bool = False) -> list[ResearchRunMetadataDTO]:
        if not self.db_path.exists():
            return []
        where = "" if include_archived else "WHERE is_archived = 0"
        with self._read_connection() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                f"""
                SELECT * FROM research_runs
                {where}
                ORDER BY created_at DESC, run_id ASC
                """
            ).fetchall()
        return [self._row_to_dto(dict(row)) for row in rows]

    def archive_run(self, run_id: str) -> None:
        with self._write_connection() as conn:
            conn.execute(
                "UPDATE research_runs SET is_archived = 1 WHERE run_id = ?",
                (run_id,),
            )

    def mark_promoted(self, run_id: str, version_id: str) -> bool:
        with self._write_connection() as conn:
            cursor = conn.execute(
                """
                UPDATE research_runs
                SET promoted_version_id = ?,
                    promotion_reconciliation_status = 'synced'
                WHERE run_id = ?
                """,
                (version_id, run_id),
            )
            return cursor.rowcount > 0

    def mark_promotion_reconciliation_required(self, run_id: str, version_id: str) -> bool:
        with self._write_connection() as conn:
            cursor = conn.execute(
                """
                UPDATE research_runs
                SET promoted_version_id = ?,
                    promotion_reconciliation_status = 'reconciliation_required'
                WHERE run_id = ?
                """,
                (version_id, run_id),
            )
            return cursor.rowcount > 0

    def _dto_to_row(self, metadata: ResearchRunMetadataDTO) -> dict[str, Any]:
        row: dict[str, Any] = {}
        for field_info in fields(metadata):
            name = field_info.name
            value = getattr(metadata, name)
            if name in self.JSON_FIELD_MAP:
                row[self.JSON_FIELD_MAP[name]] = canonical_json(
                    normalize_research_run_json_value(value)
                )
            elif name == "is_archived":
                row[name] = 1 if value else 0
            else:
                row[name] = value
        return row

    def _row_to_dto(self, row: dict[str, Any]) -> ResearchRunMetadataDTO:
        kwargs: dict[str, Any] = {}
        reverse_json_map = {value: key for key, value in self.JSON_FIELD_MAP.items()}
        dto_field_names = {field_info.name for field_info in fields(ResearchRunMetadataDTO)}

        for column, value in row.items():
            if column in reverse_json_map:
                dto_name = reverse_json_map[column]
                if dto_name == "universe":
                    kwargs[dto_name] = parse_json_list(value)
                else:
                    kwargs[dto_name] = parse_json_object(value)
            elif column in dto_field_names:
                kwargs[column] = bool(value) if column == "is_archived" else value

        return ResearchRunMetadataDTO(**kwargs)
