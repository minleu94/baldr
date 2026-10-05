"""Phase 3C 候選資料歷史回補執行器 (三大法人、信用交易與 TDCC 治理邊界)

本模組為受控、可中斷、可續跑、可審計的 Candidate Working-Copy 回補執行器。
嚴禁寫入正式資料庫 D:/Min/Python/Project/FA_Data/sqlite/twstock.db。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
import hashlib
import json
import logging
import os
from pathlib import Path
import sqlite3
import time
from typing import Any, Callable, Iterable, Optional, Sequence

import pandas as pd

from data_module.official_phase3c_fetcher import (
    fetch_credit_transactions,
    fetch_institutional_flows,
    fetch_latest_tdcc_shareholding,
)
from data_module.official_trading_calendar import OfficialTradingCalendar
from data_module.institutional_revision_read_model import (
    SUPPORTED_SOURCE_VERSIONS as INSTITUTIONAL_REVISION_SOURCE_VERSIONS,
    project_observation as project_institutional_observation,
)
from data_module.p0_candidate_repository import (
    validate_candidate_working_copy_path,
)

logger = logging.getLogger(__name__)

APPLY_CONFIRM_TOKEN = "apply-phase3c-candidate-ingestion"
SUPPORTED_SOURCES = frozenset({"institutional", "credit", "tdcc"})
CANDIDATE_DB_PATH_ENV = "PHASE3C_CANDIDATE_DB_PATH"
OBSERVATION_CUSTODY_COLUMNS = frozenset({"first_observed_at", "available_at"})
RECONCILIATION_SAMPLE_LIMIT = 10
CANONICAL_OBSERVATION_SCHEMA_VERSION = "phase3c-canonical-observation.v1"


def _cancel_requested(callback: Optional[Callable[[], bool]]) -> bool:
    if callback is None:
        return False
    try:
        return bool(callback())
    except Exception:
        # 取消觀測是控制訊號；callback 故障不可冒充取消或資料錯誤。
        return False


class _CancellationRequestedBeforeFetch(Exception):
    """停止尚未開始的單一官方請求，不代表來源錯誤。"""


def configured_candidate_db_path() -> Optional[Path]:
    """回傳使用者明確設定的 candidate DB；不猜測或建立路徑。

    Windows 已執行中的父程序不會自動吸收後來寫入 HKCU 的使用者環境
    變數。process environment 缺值時，只讀取同名的持久使用者環境設定，
    讓下一個 App 子程序不必依賴登出／重啟；兩者都沒有值時仍 fail closed。
    """

    raw_path = os.environ.get(CANDIDATE_DB_PATH_ENV, "").strip()
    if not raw_path:
        raw_path = _persisted_user_environment_value(CANDIDATE_DB_PATH_ENV)
    return Path(raw_path).expanduser() if raw_path else None


def _persisted_user_environment_value(name: str) -> str:
    if os.name != "nt":
        return ""
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            value, _value_type = winreg.QueryValueEx(key, name)
    except (ImportError, OSError):
        return ""
    return value.strip() if isinstance(value, str) else ""


@dataclass
class DailyFetchResult:
    decision_date: str
    source: str
    is_trading_day: Optional[bool]
    trading_day_reason: str
    status: str  # SUCCESS, SKIPPED_NOT_TRADING_DAY, SKIPPED_ALREADY_EXISTS, BLOCKED_NO_HISTORICAL_ENDPOINT, FAILED_RETRYABLE
    http_status: Optional[int]
    row_count: int
    error_message: Optional[str]
    fetched_at: str
    reconciliation: Optional[dict[str, Any]] = None


@dataclass
class BackfillSummary:
    start_date: str
    end_date: str
    candidate_db_path: str
    dry_run: bool
    sources: list[str]
    total_days: int
    trading_days_count: int
    non_trading_days_count: int
    unknown_days_count: int
    succeeded_days_count: int
    skipped_days_count: int
    failed_days_count: int
    total_rows_inserted: int
    tdcc_historical_status: str
    started_at: str
    finished_at: str
    daily_results: list[dict]
    cancelled: bool = False


@dataclass
class SourceReconciliationReport:
    """單一來源／資料日的 candidate natural-key reconciliation 結果。"""

    source: str
    table_name: str
    decision_date: str
    status: str
    expected_row_count: int
    existing_row_count: int
    matched_row_count: int
    missing_key_count: int
    conflict_key_count: int
    unexpected_existing_key_count: int
    inserted_row_count: int = 0
    exact_match_row_count: int = 0
    new_observation_match_row_count: int = 0
    observation_hash: Optional[str] = None
    observation_at: Optional[str] = None
    observation_timing_error: Optional[str] = None
    observation_mode: str = "unclassified"
    source_versions: list[str] = field(default_factory=list)
    first_observed_at_min: Optional[str] = None
    available_at_max: Optional[str] = None
    compared_columns: list[str] = field(default_factory=list)
    provenance_columns: list[str] = field(default_factory=list)
    missing_keys: list[str] = field(default_factory=list)
    conflict_keys: list[str] = field(default_factory=list)
    unexpected_existing_keys: list[str] = field(default_factory=list)
    conflict_fields: dict[str, list[str]] = field(default_factory=dict)


@dataclass
class SourceReconciliationOutcome:
    """reconciliation 報告與可重算的完整 canonical custody payload。"""

    report: dict[str, Any]
    canonical_payload_json: str


class SourceReconciliationError(RuntimeError):
    """reconciliation 或 atomic write/verify 失敗時保留結構化診斷。"""

    def __init__(
        self,
        report: SourceReconciliationReport,
        kind: str,
        canonical_payload_json: str,
        detail: Optional[str] = None,
    ) -> None:
        self.report = report
        self.kind = kind
        self.canonical_payload_json = canonical_payload_json
        diagnostic = json.dumps(
            asdict(report), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        detail_text = f":{detail}" if detail else ""
        super().__init__(f"{kind}{detail_text}:{diagnostic}")


class Phase3CBackfillRunner:
    """Phase 3C 候選資料受控回補執行器。"""

    def __init__(
        self,
        candidate_db_path: str | Path,
        *,
        sources: Sequence[str] = ("institutional", "credit"),
        production_data_root: Optional[str | Path] = None,
        production_db_path: Optional[str | Path] = None,
        rate_limit_seconds: float = 3.0,
        allow_online_calendar_probe: bool = False,
        include_latest_tdcc_snapshot: bool = False,
        calendar: Optional[OfficialTradingCalendar] = None,
    ) -> None:
        root = production_data_root or os.environ.get("DATA_ROOT", "D:/Min/Python/Project/FA_Data")
        prod_db = production_db_path or Path(root) / "sqlite" / "twstock.db"
        self.candidate_db_path = validate_candidate_working_copy_path(
            candidate_db_path,
            production_data_root=root,
            production_db_path=prod_db,
        )
        self.sources = [s.strip().lower() for s in sources if s.strip()]
        invalid_sources = sorted(set(self.sources) - SUPPORTED_SOURCES)
        if not self.sources or invalid_sources:
            raise ValueError(
                "sources 必須為 institutional、credit、tdcc；"
                f"收到: {', '.join(invalid_sources) or '空集合'}"
            )
        self.rate_limit_seconds = max(0.0, rate_limit_seconds)
        self.allow_online_calendar_probe = allow_online_calendar_probe
        self.include_latest_tdcc_snapshot = include_latest_tdcc_snapshot
        self.calendar = calendar or OfficialTradingCalendar(db_path=prod_db)

    def _ensure_candidate_tables(self, conn: sqlite3.Connection) -> None:
        """建立 candidate working-copy 中的 Phase 3C 候選資料表與 checkpoint 表。"""
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS institutional_flows (
                stock_code TEXT NOT NULL,
                decision_date TEXT NOT NULL,
                source_version TEXT NOT NULL,
                publication_at TEXT,
                first_observed_at TEXT NOT NULL,
                available_at TEXT NOT NULL,
                available_date TEXT,
                quality TEXT NOT NULL,
                foreign_investor_buy INTEGER NOT NULL,
                foreign_investor_sell INTEGER NOT NULL,
                foreign_investor_net INTEGER NOT NULL,
                investment_trust_buy INTEGER NOT NULL,
                investment_trust_sell INTEGER NOT NULL,
                investment_trust_net INTEGER NOT NULL,
                dealer_buy INTEGER NOT NULL,
                dealer_sell INTEGER NOT NULL,
                dealer_net INTEGER NOT NULL,
                PRIMARY KEY (stock_code, decision_date)
            );

            CREATE TABLE IF NOT EXISTS credit_transactions (
                stock_code TEXT NOT NULL,
                decision_date TEXT NOT NULL,
                source_version TEXT NOT NULL,
                publication_at TEXT,
                first_observed_at TEXT NOT NULL,
                available_at TEXT NOT NULL,
                available_date TEXT,
                quality TEXT NOT NULL,
                margin_purchase INTEGER NOT NULL,
                margin_balance INTEGER NOT NULL,
                short_sale INTEGER NOT NULL,
                short_balance INTEGER NOT NULL,
                financing INTEGER,
                securities_lending INTEGER,
                PRIMARY KEY (stock_code, decision_date)
            );

            CREATE TABLE IF NOT EXISTS tdcc_shareholding (
                stock_code TEXT NOT NULL,
                decision_date TEXT NOT NULL,
                source_version TEXT NOT NULL,
                publication_at TEXT,
                first_observed_at TEXT NOT NULL,
                available_at TEXT NOT NULL,
                available_date TEXT,
                quality TEXT NOT NULL,
                shareholding_tiers TEXT NOT NULL,
                large_holder_ratio_bp INTEGER NOT NULL,
                retail_holder_ratio_bp INTEGER NOT NULL,
                dispersion_index_bp INTEGER NOT NULL,
                PRIMARY KEY (stock_code, decision_date)
            );

            CREATE TABLE IF NOT EXISTS phase3c_backfill_checkpoints (
                decision_date TEXT NOT NULL,
                source TEXT NOT NULL,
                status TEXT NOT NULL,
                row_count INTEGER NOT NULL,
                fetched_at TEXT NOT NULL,
                error_message TEXT,
                PRIMARY KEY (decision_date, source)
            );

            CREATE TABLE IF NOT EXISTS phase3c_source_observations (
                source TEXT NOT NULL,
                decision_date TEXT NOT NULL,
                observation_hash TEXT NOT NULL,
                observed_at TEXT NOT NULL,
                row_count INTEGER NOT NULL,
                observation_mode TEXT NOT NULL,
                source_versions TEXT NOT NULL,
                first_observed_at_min TEXT,
                available_at_max TEXT,
                canonical_payload_json TEXT NOT NULL,
                diagnostic_json TEXT,
                PRIMARY KEY (source, decision_date, observation_hash)
            );
            """
        )
        observation_columns = {
            str(row[1])
            for row in conn.execute(
                "PRAGMA table_info(phase3c_source_observations)"
            ).fetchall()
        }
        if observation_columns and "canonical_payload_json" not in observation_columns:
            # 僅升級 candidate-only ledger；舊 observation 若無 payload 會保留
            # 為 legacy，不冒造內容，新的 observation 一律保存完整 payload。
            conn.execute(
                "ALTER TABLE phase3c_source_observations "
                "ADD COLUMN canonical_payload_json TEXT"
            )

    def is_date_already_completed(
        self, conn: sqlite3.Connection, decision_date_str: str, source: str
    ) -> bool:
        """只以成功 checkpoint 判定完成；無 checkpoint 也必須先 reconciliation。"""
        checkpoint = conn.execute(
            """
            SELECT status FROM phase3c_backfill_checkpoints
            WHERE decision_date = ? AND source = ?
            """,
            (decision_date_str, source),
        ).fetchone()
        if checkpoint is not None:
            return str(checkpoint[0]) == "SUCCESS"

        # 早期 candidate DB 可能只有資料列沒有 checkpoint；不能再用
        # 「該日有任何 row」當成完整來源覆蓋，必須抓取後做逐欄 reconciliation。
        return False

    @staticmethod
    def _record_checkpoint(
        conn: sqlite3.Connection,
        result: DailyFetchResult,
    ) -> None:
        """寫入可審計 checkpoint；FAILED_RETRYABLE 不會被視為完成。"""
        if result.status == "SKIPPED_ALREADY_EXISTS":
            # 不得將原本的 SUCCESS checkpoint 覆蓋成 skip 狀態。
            return
        conn.execute(
            """
            INSERT INTO phase3c_backfill_checkpoints (
                decision_date, source, status, row_count, fetched_at, error_message
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(decision_date, source) DO UPDATE SET
                status = excluded.status,
                row_count = excluded.row_count,
                fetched_at = excluded.fetched_at,
                error_message = excluded.error_message
            """,
            (
                result.decision_date,
                result.source,
                result.status,
                result.row_count,
                result.fetched_at,
                result.error_message,
            ),
        )

    @staticmethod
    def _record_source_observation(
        conn: sqlite3.Connection,
        result: DailyFetchResult,
        canonical_payload_json: Optional[str] = None,
    ) -> None:
        """保存每次有 payload 的 observation custody，不覆寫既有資料列。"""
        report = result.reconciliation
        if not isinstance(report, dict) or not report.get("observation_hash"):
            return
        if not isinstance(canonical_payload_json, str) or not canonical_payload_json:
            raise ValueError("observation custody 缺少 canonical payload")
        conn.execute(
            """
            INSERT INTO phase3c_source_observations (
                source, decision_date, observation_hash, observed_at, row_count,
                observation_mode, source_versions, first_observed_at_min,
                available_at_max, canonical_payload_json, diagnostic_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source, decision_date, observation_hash) DO NOTHING
            """,
            (
                result.source,
                result.decision_date,
                report["observation_hash"],
                report.get("observation_at") or result.fetched_at,
                int(report.get("expected_row_count") or result.row_count),
                str(report.get("observation_mode") or "unclassified"),
                json.dumps(
                    report.get("source_versions", []),
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                report.get("first_observed_at_min"),
                report.get("available_at_max"),
                canonical_payload_json,
                json.dumps(report, ensure_ascii=False, sort_keys=True),
            ),
        )

    @staticmethod
    def _project_current_institutional_observation(
        conn: sqlite3.Connection,
        result: DailyFetchResult,
        canonical_payload_json: Optional[str],
    ) -> None:
        """Project only a verified official institutional observation into the current read model."""
        report = result.reconciliation
        if result.source != "institutional" or not isinstance(report, dict):
            return
        if report.get("observation_timing_error") is not None:
            return
        versions = report.get("source_versions")
        if not isinstance(versions, list) or not versions:
            return
        if any(version not in INSTITUTIONAL_REVISION_SOURCE_VERSIONS for version in versions):
            return
        observation_hash = report.get("observation_hash")
        observation_at = report.get("observation_at")
        if not isinstance(observation_hash, str) or not isinstance(observation_at, str):
            return
        stored = conn.execute(
            "SELECT observed_at,row_count,canonical_payload_json "
            "FROM phase3c_source_observations "
            "WHERE source='institutional' AND decision_date=? AND observation_hash=?",
            (result.decision_date, observation_hash),
        ).fetchone()
        if stored is None:
            raise ValueError("verified institutional source observation was not persisted")
        stored_clock, stored_count, stored_payload = tuple(stored)
        if stored_clock != observation_at or stored_payload != canonical_payload_json:
            raise ValueError("persisted institutional source observation identity mismatch")
        project_institutional_observation(
            conn,
            {
                "canonical_payload_json": stored_payload,
                "observation_hash": observation_hash,
                "observed_at": stored_clock,
                "decision_date": result.decision_date,
                "row_count": int(stored_count),
            },
        )

    @staticmethod
    def _source_table_name(source: str) -> str:
        table_map = {
            "institutional": "institutional_flows",
            "credit": "credit_transactions",
            "tdcc": "tdcc_shareholding",
        }
        try:
            return table_map[source]
        except KeyError as exc:
            raise ValueError(f"不支援的 reconciliation source: {source}") from exc

    @staticmethod
    def _quote_identifier(identifier: str) -> str:
        return '"' + identifier.replace('"', '""') + '"'

    @staticmethod
    def _canonical_cell(value: Any) -> Any:
        """把 pandas/SQLite 的缺值與 scalar 正規化為可比較值。"""
        if value is None:
            return None
        try:
            if bool(pd.isna(value)):
                return None
        except (TypeError, ValueError):
            pass
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        item_method = getattr(value, "item", None)
        if callable(item_method) and not isinstance(value, (str, bytes)):
            try:
                value = item_method()
            except (TypeError, ValueError):
                pass
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        return value

    @classmethod
    def _sqlite_value(cls, value: Any) -> Any:
        normalized = cls._canonical_cell(value)
        if normalized is None or isinstance(normalized, (str, bytes, int, float)):
            return normalized
        return str(normalized)

    @classmethod
    def _natural_key(cls, row: dict[str, Any]) -> tuple[str, str]:
        stock_code = cls._canonical_cell(row.get("stock_code"))
        decision_date = cls._canonical_cell(row.get("decision_date"))
        return str(stock_code), str(decision_date)

    @classmethod
    def _key_text(cls, key: tuple[str, str]) -> str:
        return f"{key[0]}|{key[1]}"

    @classmethod
    def _parse_aware_observation_timestamp(
        cls, value: Any
    ) -> Optional[datetime]:
        timestamp = cls._canonical_cell(value)
        if not isinstance(timestamp, str):
            return None
        try:
            parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.utcoffset() is None:
            return None
        return parsed

    @staticmethod
    def _observation_timestamp_is_monotonic(
        existing_value: Any,
        incoming_value: Any,
    ) -> bool:
        existing_dt = Phase3CBackfillRunner._parse_aware_observation_timestamp(
            existing_value
        )
        incoming_dt = Phase3CBackfillRunner._parse_aware_observation_timestamp(
            incoming_value
        )
        # custody clock 必須是 timezone-aware；date-only 或 naive datetime
        # 沒有可驗證的絕對時間基準，不得被當成 newer observation。
        if existing_dt is None or incoming_dt is None:
            return False
        try:
            return incoming_dt >= existing_dt
        except TypeError:
            return False

    @classmethod
    def _observation_timing_error(
        cls,
        expected_records: Sequence[dict[str, Any]],
        observation_at: str,
    ) -> Optional[str]:
        observation_dt = cls._parse_aware_observation_timestamp(observation_at)
        if observation_dt is None:
            return "observation_at 必須是 timezone-aware ISO timestamp"

        for record in expected_records:
            key_text = cls._key_text(cls._natural_key(record))
            for column in sorted(OBSERVATION_CUSTODY_COLUMNS):
                raw_value = record.get(column)
                incoming_dt = cls._parse_aware_observation_timestamp(raw_value)
                incoming_text = cls._canonical_cell(raw_value)
                if incoming_dt is None:
                    return (
                        f"{column} 必須是 timezone-aware ISO timestamp："
                        f"{key_text}={incoming_text}"
                    )
                if incoming_dt > observation_dt:
                    return (
                        f"observation_at {observation_at} 早於 {column} "
                        f"{incoming_text}：{key_text}"
                    )
        return None

    @classmethod
    def _canonical_observation_payload(
        cls,
        frame: pd.DataFrame,
        table_columns: Sequence[str],
        observation_at: str,
    ) -> str:
        records = []
        for record in frame.to_dict(orient="records"):
            canonical = {
                column: cls._canonical_cell(record.get(column))
                for column in table_columns
            }
            records.append(canonical)
        records.sort(key=lambda row: cls._natural_key(row))
        return json.dumps(
            {
                "schema_version": CANONICAL_OBSERVATION_SCHEMA_VERSION,
                "observation_at": observation_at,
                "rows": records,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )

    @classmethod
    def _observation_hash(
        cls,
        frame: pd.DataFrame,
        table_columns: Sequence[str],
        observation_at: str,
    ) -> str:
        payload = cls._canonical_observation_payload(
            frame, table_columns, observation_at
        )
        return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @classmethod
    def _read_candidate_rows(
        cls,
        conn: sqlite3.Connection,
        table_name: str,
        table_columns: Sequence[str],
        decision_date_str: str,
    ) -> list[dict[str, Any]]:
        selected_columns = ", ".join(
            cls._quote_identifier(column) for column in table_columns
        )
        quoted_table = cls._quote_identifier(table_name)
        rows = conn.execute(
            f"SELECT {selected_columns} FROM {quoted_table} "
            f"WHERE {cls._quote_identifier('decision_date')} = ?",
            (decision_date_str,),
        ).fetchall()
        return [dict(zip(table_columns, tuple(row))) for row in rows]

    @classmethod
    def _inspect_source_reconciliation(
        cls,
        conn: sqlite3.Connection,
        source: str,
        decision_date_str: str,
        frame: pd.DataFrame,
        table_name: str,
        table_columns: Sequence[str],
        observation_at: str,
    ) -> tuple[
        SourceReconciliationReport,
        list[dict[str, Any]],
        str,
    ]:
        frame_columns = [str(column) for column in frame.columns]
        unsupported_columns = sorted(set(frame_columns) - set(table_columns))
        if unsupported_columns:
            raise ValueError(
                f"來源資料含候選表未支援欄位: {', '.join(unsupported_columns)}"
            )

        expected_records = [
            {column: record.get(column) for column in frame_columns}
            for record in frame.to_dict(orient="records")
        ]
        expected_by_key: dict[tuple[str, str], dict[str, Any]] = {}
        for record in expected_records:
            key = cls._natural_key(record)
            if key in expected_by_key:
                raise ValueError(
                    "來源資料含重複 stock_code + decision_date："
                    f"{cls._key_text(key)}"
                )
            expected_by_key[key] = record

        existing_rows = cls._read_candidate_rows(
            conn, table_name, table_columns, decision_date_str
        )
        existing_by_key: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for record in existing_rows:
            existing_by_key.setdefault(cls._natural_key(record), []).append(record)

        expected_keys = set(expected_by_key)
        existing_keys = set(existing_by_key)
        missing_keys = sorted(expected_keys - existing_keys)
        unexpected_keys = sorted(existing_keys - expected_keys)
        conflict_keys: list[tuple[str, str]] = []
        conflict_fields: dict[str, list[str]] = {}
        observation_timing_error = cls._observation_timing_error(
            expected_records, observation_at
        )
        if observation_timing_error:
            conflict_fields["<observation_clock>"] = [observation_timing_error]
        matched_count = 0
        exact_match_count = 0
        new_observation_match_count = 0

        for key in sorted(expected_keys & existing_keys):
            key_text = cls._key_text(key)
            rows_for_key = existing_by_key[key]
            if len(rows_for_key) != 1:
                conflict_keys.append(key)
                conflict_fields[key_text] = ["<duplicate_natural_key>"]
                continue
            expected = expected_by_key[key]
            existing = rows_for_key[0]
            mismatches = [
                column
                for column in table_columns
                if cls._canonical_cell(existing.get(column))
                != cls._canonical_cell(expected.get(column))
            ]
            if not mismatches:
                exact_match_count += 1
                matched_count += 1
                continue

            # 官方 fetcher 在沒有 publication timestamp 時，會以每次實際
            # 觀測時間填入 first_observed_at/available_at。這兩個欄位若只
            # 向前推進，視為新的 observation custody；原始資料列仍不可更新。
            custody_only = set(mismatches).issubset(OBSERVATION_CUSTODY_COLUMNS)
            custody_is_newer = custody_only and all(
                cls._observation_timestamp_is_monotonic(
                    existing.get(column), expected.get(column)
                )
                for column in mismatches
            )
            if custody_is_newer:
                new_observation_match_count += 1
                matched_count += 1
            else:
                conflict_keys.append(key)
                conflict_fields[key_text] = mismatches

        provenance_columns = [
            column
            for column in (
                "source_version",
                "publication_at",
                "first_observed_at",
                "available_at",
                "available_date",
                "quality",
            )
            if column in table_columns
        ]
        source_versions = sorted(
            {
                str(cls._canonical_cell(record.get("source_version")))
                for record in expected_records
                if cls._canonical_cell(record.get("source_version")) is not None
            }
        )
        first_observed_values = sorted(
            str(cls._canonical_cell(record.get("first_observed_at")))
            for record in expected_records
            if cls._canonical_cell(record.get("first_observed_at")) is not None
        )
        available_at_values = sorted(
            str(cls._canonical_cell(record.get("available_at")))
            for record in expected_records
            if cls._canonical_cell(record.get("available_at")) is not None
        )
        has_conflict = bool(
            conflict_keys or unexpected_keys or observation_timing_error
        )
        if has_conflict:
            observation_mode = "conflict"
        elif new_observation_match_count or missing_keys:
            observation_mode = (
                "new_observation_reconciled" if existing_rows else "new_observation_insert"
            )
        else:
            observation_mode = "exact_replay"
        canonical_payload_json = cls._canonical_observation_payload(
            frame, table_columns, observation_at
        )
        report = SourceReconciliationReport(
            source=source,
            table_name=table_name,
            decision_date=decision_date_str,
            status=("CONFLICT" if has_conflict else "READY"),
            expected_row_count=len(expected_records),
            existing_row_count=len(existing_rows),
            matched_row_count=matched_count,
            missing_key_count=len(missing_keys),
            conflict_key_count=len(conflict_keys),
            unexpected_existing_key_count=len(unexpected_keys),
            exact_match_row_count=exact_match_count,
            new_observation_match_row_count=new_observation_match_count,
            observation_hash=(
                cls._observation_hash(frame, table_columns, observation_at)
            ),
            observation_at=observation_at,
            observation_timing_error=observation_timing_error,
            observation_mode=observation_mode,
            source_versions=source_versions,
            first_observed_at_min=(first_observed_values[0] if first_observed_values else None),
            available_at_max=(available_at_values[-1] if available_at_values else None),
            compared_columns=list(table_columns),
            provenance_columns=provenance_columns,
            missing_keys=[
                cls._key_text(key) for key in missing_keys[:RECONCILIATION_SAMPLE_LIMIT]
            ],
            conflict_keys=[
                cls._key_text(key) for key in conflict_keys[:RECONCILIATION_SAMPLE_LIMIT]
            ],
            unexpected_existing_keys=[
                cls._key_text(key)
                for key in unexpected_keys[:RECONCILIATION_SAMPLE_LIMIT]
            ],
            conflict_fields={
                key: fields
                for key, fields in list(conflict_fields.items())[
                    :RECONCILIATION_SAMPLE_LIMIT
                ]
            },
        )
        missing_records = [expected_by_key[key] for key in missing_keys]
        return report, missing_records, canonical_payload_json

    @staticmethod
    def _reconciliation_error(
        report: SourceReconciliationReport,
        kind: str,
        canonical_payload_json: str,
    ) -> SourceReconciliationError:
        report.status = kind.upper()
        return SourceReconciliationError(
            report,
            f"reconciliation_{kind.lower()}",
            canonical_payload_json,
        )

    def _reconcile_source_frame(
        self,
        conn: sqlite3.Connection,
        source: str,
        decision_date_str: str,
        frame: pd.DataFrame,
        observation_at: str,
    ) -> SourceReconciliationOutcome:
        """在既有 transaction 內做完整比對、補齊與 post-write verify。"""
        table_name = self._source_table_name(source)
        table_info = conn.execute(
            f"PRAGMA table_info({self._quote_identifier(table_name)})"
        ).fetchall()
        table_columns = [str(row[1]) for row in table_info]
        if not table_columns:
            raise ValueError(f"candidate table 不存在或無欄位: {table_name}")

        report, missing_records, canonical_payload_json = self._inspect_source_reconciliation(
            conn,
            source,
            decision_date_str,
            frame,
            table_name,
            table_columns,
            observation_at,
        )
        if report.status == "CONFLICT":
            raise self._reconciliation_error(
                report, "conflict", canonical_payload_json
            )

        insert_columns = [str(column) for column in frame.columns]
        if missing_records:
            quoted_columns = ", ".join(
                self._quote_identifier(column) for column in insert_columns
            )
            placeholders = ", ".join("?" for _ in insert_columns)
            insert_sql = (
                f"INSERT INTO {self._quote_identifier(table_name)} "
                f"({quoted_columns}) VALUES ({placeholders})"
            )
            values = [
                tuple(self._sqlite_value(record.get(column)) for column in insert_columns)
                for record in missing_records
            ]
            try:
                conn.executemany(insert_sql, values)
            except Exception as exc:
                report.status = "WRITE_FAILED"
                raise SourceReconciliationError(
                    report,
                    "reconciliation_write_failed",
                    canonical_payload_json,
                    detail=f"{type(exc).__name__}:{exc}",
                ) from exc

        verified, _, verified_payload_json = self._inspect_source_reconciliation(
            conn,
            source,
            decision_date_str,
            frame,
            table_name,
            table_columns,
            observation_at,
        )
        verified.inserted_row_count = len(missing_records)
        if (
            verified.status == "CONFLICT"
            or verified.missing_key_count > 0
            or verified.unexpected_existing_key_count > 0
        ):
            verified.status = "VERIFY_FAILED"
            raise SourceReconciliationError(
                verified,
                "reconciliation_verify_failed",
                verified_payload_json,
            )
        verified.status = "RECONCILED"
        # post-write verify 看到剛插入的列必然會是 exact match；保留寫入前
        # 的 observation mode，讓報告仍能區分 exact replay、re-observation
        # reconciliation 與真正的 new observation insert。
        verified.observation_mode = report.observation_mode
        return SourceReconciliationOutcome(
            report=asdict(verified),
            canonical_payload_json=verified_payload_json,
        )

    @staticmethod
    def _validate_source_frame(
        frame: pd.DataFrame, source: str, decision_date_str: str
    ) -> None:
        required_columns = {
            "institutional": {
                "stock_code", "decision_date", "source_version", "first_observed_at",
                "available_at", "quality", "foreign_investor_buy", "foreign_investor_sell",
                "foreign_investor_net", "investment_trust_buy", "investment_trust_sell",
                "investment_trust_net", "dealer_buy", "dealer_sell", "dealer_net",
            },
            "credit": {
                "stock_code", "decision_date", "source_version", "first_observed_at",
                "available_at", "quality", "margin_purchase", "margin_balance",
                "short_sale", "short_balance",
            },
            "tdcc": {
                "stock_code", "decision_date", "source_version", "first_observed_at",
                "available_at", "quality", "shareholding_tiers",
                "large_holder_ratio_bp", "retail_holder_ratio_bp",
                "dispersion_index_bp",
            },
        }[source]
        missing = sorted(required_columns - set(frame.columns))
        if missing:
            raise ValueError(f"來源資料缺少必要欄位: {', '.join(missing)}")
        if frame["stock_code"].isna().any() or (frame["stock_code"].astype(str).str.strip() == "").any():
            raise ValueError("來源資料含空白 stock_code")
        normalized_dates = frame["decision_date"].astype(str)
        if not normalized_dates.eq(decision_date_str).all():
            raise ValueError("來源資料 decision_date 與請求日期不一致")
        if frame.duplicated(subset=["stock_code", "decision_date"]).any():
            raise ValueError("來源資料含重複 stock_code + decision_date")

    def run_backfill(
        self,
        start_date: date,
        end_date: date,
        *,
        dry_run: bool = True,
        confirm_token: Optional[str] = None,
        progress_callback: Optional[Callable[[str, int], None]] = None,
        cancel_callback: Optional[Callable[[], bool]] = None,
    ) -> BackfillSummary:
        """執行 Phase 3C 受控區間回補。"""
        started_at = datetime.now(timezone.utc).isoformat()

        if not dry_run:
            if confirm_token != APPLY_CONFIRM_TOKEN:
                raise ValueError(
                    f"apply 模式必須提供正確 confirm token: {APPLY_CONFIRM_TOKEN}"
                )
            self.candidate_db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(self.candidate_db_path)
            self._ensure_candidate_tables(conn)
            conn.commit()
        else:
            conn = None

        try:
            days_range = self.calendar.get_trading_days_in_range(
                start_date,
                end_date,
                allow_online_probe=self.allow_online_calendar_probe,
            )
            total_days = len(days_range)

            results: list[DailyFetchResult] = []
            total_rows_inserted = 0

            def append_result(
                result: DailyFetchResult,
                *,
                canonical_payload_json: Optional[str] = None,
                project_institutional_revision: bool = False,
            ) -> None:
                if conn is not None:
                    with conn:
                        conn.execute("BEGIN IMMEDIATE")
                        self._record_source_observation(
                            conn, result, canonical_payload_json
                        )
                        if project_institutional_revision:
                            self._project_current_institutional_observation(
                                conn, result, canonical_payload_json
                            )
                        self._record_checkpoint(conn, result)
                results.append(result)

            succeeded_count = 0
            skipped_count = 0
            failed_count = 0
            was_cancelled = False
            tdcc_result_recorded = False
            tdcc_historical_status = (
                "LATEST_SNAPSHOT_ENABLED；歷史日期仍 BLOCKED_NO_HISTORICAL_ENDPOINT"
                if self.include_latest_tdcc_snapshot and "tdcc" in self.sources
                else "BLOCKED_NO_HISTORICAL_ENDPOINT (僅提供最新單週公開資料)"
            )

            if self.include_latest_tdcc_snapshot and "tdcc" in self.sources:
                fetched_at = datetime.now(timezone.utc).isoformat()
                tdcc_failure_date = end_date.isoformat()
                if _cancel_requested(cancel_callback):
                    was_cancelled = True
                    tdcc_result_recorded = True
                else:
                    try:
                        time.sleep(self.rate_limit_seconds)
                        if _cancel_requested(cancel_callback):
                            was_cancelled = True
                            tdcc_result_recorded = True
                            raise _CancellationRequestedBeforeFetch()
                        tdcc_frame = fetch_latest_tdcc_shareholding()
                        if tdcc_frame.empty:
                            raise ValueError("TDCC 最新單週官方端點未回傳候選資料")
                        unique_dates = sorted(
                            str(value)
                            for value in tdcc_frame["decision_date"].dropna().unique()
                        )
                        if len(unique_dates) != 1:
                            raise ValueError("TDCC 最新 snapshot 必須只有一個資料日")
                        snapshot_date = date.fromisoformat(unique_dates[0])
                        tdcc_failure_date = snapshot_date.isoformat()
                        if snapshot_date > date.today() or snapshot_date > end_date:
                            raise ValueError("TDCC 最新 snapshot 日期晚於本次可接受日期")
                        snapshot_date_str = snapshot_date.isoformat()
                        self._validate_source_frame(tdcc_frame, "tdcc", snapshot_date_str)
                        if conn is not None and self.is_date_already_completed(
                            conn, snapshot_date_str, "tdcc"
                        ):
                            result = DailyFetchResult(
                                decision_date=snapshot_date_str,
                                source="tdcc",
                                is_trading_day=None,
                                trading_day_reason="latest_weekly_snapshot",
                                status="SKIPPED_ALREADY_EXISTS",
                                http_status=None,
                                row_count=0,
                                error_message=None,
                                fetched_at=fetched_at,
                            )
                            skipped_count += 1
                            append_result(result)
                        elif not dry_run and conn is not None:
                            tdcc_observation_at = datetime.now(timezone.utc).isoformat()
                            # TDCC 資料列、來源 observation 與 SUCCESS checkpoint
                            # 共用同一交易；失敗即全部回滾，重試可補缺列。
                            with conn:
                                conn.execute("BEGIN IMMEDIATE")
                                outcome = self._reconcile_source_frame(
                                    conn, "tdcc", snapshot_date_str, tdcc_frame, tdcc_observation_at
                                )
                                tdcc_reconciliation = outcome.report
                                result = DailyFetchResult(
                                    decision_date=snapshot_date_str,
                                    source="tdcc",
                                    is_trading_day=None,
                                    trading_day_reason="latest_weekly_snapshot",
                                    status="SUCCESS",
                                    http_status=None,
                                    row_count=len(tdcc_frame),
                                    error_message=None,
                                    fetched_at=fetched_at,
                                    reconciliation=tdcc_reconciliation,
                                )
                                self._record_source_observation(
                                    conn, result, outcome.canonical_payload_json
                                )
                                self._record_checkpoint(conn, result)
                            results.append(result)
                            total_rows_inserted += int(tdcc_reconciliation["inserted_row_count"])
                            succeeded_count += 1
                        else:
                            result = DailyFetchResult(
                                decision_date=snapshot_date_str,
                                source="tdcc",
                                is_trading_day=None,
                                trading_day_reason="latest_weekly_snapshot",
                                status="SUCCESS",
                                http_status=None,
                                row_count=len(tdcc_frame),
                                error_message=None,
                                fetched_at=fetched_at,
                            )
                            append_result(result)
                            succeeded_count += 1
                    except _CancellationRequestedBeforeFetch:
                        pass
                    except Exception as exc:
                        logger.error(f"抓取 TDCC 最新 snapshot 失敗: {exc}")
                        failed_result = DailyFetchResult(
                            decision_date=tdcc_failure_date,
                            source="tdcc",
                            is_trading_day=None,
                            trading_day_reason="latest_weekly_snapshot",
                            status="FAILED_RETRYABLE",
                            http_status=None,
                            row_count=0,
                            error_message=str(exc),
                            fetched_at=fetched_at,
                        )
                        append_result(failed_result)
                        failed_count += 1
                    tdcc_result_recorded = True
                    if _cancel_requested(cancel_callback):
                        was_cancelled = True

            trading_days_count = sum(1 for d in days_range if d["is_trading_day"] is True)
            non_trading_days_count = sum(1 for d in days_range if d["is_trading_day"] is False)
            unknown_days_count = sum(1 for d in days_range if d["is_trading_day"] is None)

            for idx, day_info in enumerate(days_range):
                if _cancel_requested(cancel_callback):
                    was_cancelled = True
                    break
                d_obj = day_info["date"]
                assert isinstance(d_obj, date)
                d_str = str(day_info["date_str"])
                is_td_raw = day_info["is_trading_day"]
                is_td: Optional[bool] = bool(is_td_raw) if is_td_raw is not None else None
                td_reason = str(day_info["reason_code"])

                pct = int(((idx + 1) / total_days) * 100) if total_days > 0 else 100
                if progress_callback:
                    progress_callback(f"處理 {d_str} ({idx + 1}/{total_days})...", pct)

                for src in self.sources:
                    if _cancel_requested(cancel_callback):
                        was_cancelled = True
                        break
                    fetch_started_at = datetime.now(timezone.utc).isoformat()
                    # 保留既有 fetched_at 的 fetch-start 語意；完整 payload
                    # 的 observation_at 會在 fetcher 返回後另行建立。
                    fetched_at = fetch_started_at
                    reconciliation: Optional[dict[str, Any]] = None
                    canonical_payload_json: Optional[str] = None
                    observation_at: Optional[str] = None

                    # TDCC 歷史邊界處理 (歷史日期不論交易日與否，均明確標示不支援歷史端點)
                    if src == "tdcc":
                        if tdcc_result_recorded:
                            continue
                        append_result(
                            DailyFetchResult(
                                decision_date=d_str,
                                source=src,
                                is_trading_day=is_td,
                                trading_day_reason=td_reason,
                                status="BLOCKED_NO_HISTORICAL_ENDPOINT",
                                http_status=None,
                                row_count=0,
                                error_message="TDCC 僅提供最新單週公開資料，不對歷史日期輪詢抓取",
                                fetched_at=fetched_at,
                            )
                        )
                        skipped_count += 1
                        continue

                    # 只有有證據的休市日可以合法跳過；日曆未知必須可重試，不能當作休市。
                    if is_td is False:
                        append_result(
                            DailyFetchResult(
                                decision_date=d_str,
                                source=src,
                                is_trading_day=is_td,
                                trading_day_reason=td_reason,
                                status="SKIPPED_NOT_TRADING_DAY",
                                http_status=None,
                                row_count=0,
                                error_message=None,
                                fetched_at=fetched_at,
                            )
                        )
                        skipped_count += 1
                        continue

                    if is_td is None:
                        append_result(
                            DailyFetchResult(
                                decision_date=d_str,
                                source=src,
                                is_trading_day=None,
                                trading_day_reason=td_reason,
                                status="BLOCKED_CALENDAR_UNKNOWN",
                                http_status=None,
                                row_count=0,
                                error_message=(
                                    f"官方交易日狀態未知：{d_str} ({td_reason})；"
                                    "未抓取資料，需在日曆可驗證後重試"
                                ),
                                fetched_at=fetched_at,
                            )
                        )
                        failed_count += 1
                        continue

                    # 斷點續跑檢查
                    if conn is not None and self.is_date_already_completed(conn, d_str, src):
                        append_result(
                            DailyFetchResult(
                                decision_date=d_str,
                                source=src,
                                is_trading_day=True,
                                trading_day_reason=td_reason,
                                status="SKIPPED_ALREADY_EXISTS",
                                http_status=None,
                                row_count=0,
                                error_message=None,
                                fetched_at=fetched_at,
                            )
                        )
                        skipped_count += 1
                        continue

                    # 實際連線抓取
                    try:
                        time.sleep(self.rate_limit_seconds)
                        if _cancel_requested(cancel_callback):
                            was_cancelled = True
                            break
                        df: Optional[pd.DataFrame] = None
                        if src == "institutional":
                            df = fetch_institutional_flows(d_obj)
                        elif src == "credit":
                            df = fetch_credit_transactions(d_obj)

                        # 官方 fetcher 內部建立的 first_observed_at／available_at
                        # 發生在 HTTP 觀測期間；不可沿用 fetch 開始前的 fetched_at
                        # 作為整份新 payload 的 observation_at。
                        observation_at = datetime.now(timezone.utc).isoformat()
                        if df is None or df.empty:
                            append_result(
                                DailyFetchResult(
                                    decision_date=d_str,
                                    source=src,
                                    is_trading_day=True,
                                    trading_day_reason=td_reason,
                                    status="FAILED_RETRYABLE",
                                    http_status=None,
                                    row_count=0,
                                    error_message="官方 API 無資料或連線失敗",
                                    fetched_at=fetched_at,
                                )
                            )
                            failed_count += 1
                        else:
                            self._validate_source_frame(df, src, d_str)
                            row_cnt = len(df)
                            if not dry_run and conn is not None:
                                try:
                                    # Candidate rows and SUCCESS checkpoint must share
                                    # one transaction; any conflict/write/verify error
                                    # therefore rolls back all newly inserted rows.
                                    with conn:
                                        # Acquire the write lock before the first
                                        # reconciliation SELECT so two retries cannot
                                        # both observe the same missing natural keys.
                                        conn.execute("BEGIN IMMEDIATE")
                                        assert observation_at is not None
                                        reconciliation_outcome = self._reconcile_source_frame(
                                            conn, src, d_str, df, observation_at
                                        )
                                        reconciliation = reconciliation_outcome.report
                                        canonical_payload_json = (
                                            reconciliation_outcome.canonical_payload_json
                                        )
                                        result = DailyFetchResult(
                                            decision_date=d_str,
                                            source=src,
                                            is_trading_day=True,
                                            trading_day_reason=td_reason,
                                            status="SUCCESS",
                                            http_status=None,
                                            row_count=row_cnt,
                                            error_message=None,
                                            fetched_at=fetched_at,
                                            reconciliation=reconciliation,
                                        )
                                        self._record_source_observation(
                                            conn, result, canonical_payload_json
                                        )
                                        if src == "institutional":
                                            self._project_current_institutional_observation(
                                                conn, result, canonical_payload_json
                                            )
                                        self._record_checkpoint(conn, result)
                                except SourceReconciliationError as exc:
                                    reconciliation = asdict(exc.report)
                                    canonical_payload_json = exc.canonical_payload_json
                                    logger.error(
                                        f"候選資料 reconciliation {src} ({d_str}) 失敗: {exc}"
                                    )
                                    failed_result = DailyFetchResult(
                                        decision_date=d_str,
                                        source=src,
                                        is_trading_day=True,
                                        trading_day_reason=td_reason,
                                        status="FAILED_RETRYABLE",
                                        http_status=None,
                                        row_count=0,
                                        error_message=str(exc),
                                        fetched_at=fetched_at,
                                        reconciliation=reconciliation,
                                    )
                                    append_result(
                                        failed_result,
                                        canonical_payload_json=canonical_payload_json,
                                        project_institutional_revision=(
                                            src == "institutional"
                                            and exc.kind == "reconciliation_conflict"
                                        ),
                                    )
                                    failed_count += 1
                                    continue
                                total_rows_inserted += int(
                                    reconciliation["inserted_row_count"]
                                )
                                # The context manager committed both candidate rows
                                # and the SUCCESS checkpoint atomically.
                                results.append(result)
                            else:
                                append_result(
                                    DailyFetchResult(
                                        decision_date=d_str,
                                        source=src,
                                        is_trading_day=True,
                                        trading_day_reason=td_reason,
                                        status="SUCCESS",
                                        http_status=None,
                                        row_count=row_cnt,
                                        error_message=None,
                                        fetched_at=fetched_at,
                                    )
                                )
                            succeeded_count += 1

                    except Exception as exc:
                        logger.error(f"抓取 {src} ({d_str}) 失敗: {exc}")
                        append_result(
                            DailyFetchResult(
                                decision_date=d_str,
                                source=src,
                                is_trading_day=True,
                                trading_day_reason=td_reason,
                                status="FAILED_RETRYABLE",
                                http_status=None,
                                row_count=0,
                                error_message=str(exc),
                                fetched_at=fetched_at,
                                reconciliation=reconciliation,
                            ),
                            canonical_payload_json=canonical_payload_json,
                        )
                        failed_count += 1

            was_cancelled = was_cancelled or _cancel_requested(cancel_callback)
            finished_at = datetime.now(timezone.utc).isoformat()
            summary = BackfillSummary(
                start_date=start_date.isoformat(),
                end_date=end_date.isoformat(),
                candidate_db_path=str(self.candidate_db_path),
                dry_run=dry_run,
                sources=self.sources,
                total_days=total_days,
                trading_days_count=trading_days_count,
                non_trading_days_count=non_trading_days_count,
                unknown_days_count=unknown_days_count,
                succeeded_days_count=succeeded_count,
                skipped_days_count=skipped_count,
                failed_days_count=failed_count,
                total_rows_inserted=total_rows_inserted,
                tdcc_historical_status=tdcc_historical_status,
                started_at=started_at,
                finished_at=finished_at,
                daily_results=[asdict(r) for r in results],
                cancelled=was_cancelled,
            )

            # 寫入 summary 報告檔至非 tracked 輸出位置
            self._write_summary_report(summary)
            return summary

        finally:
            if conn is not None:
                conn.close()

    def _write_summary_report(self, summary: BackfillSummary) -> None:
        """產出結構化摘要報告 (JSON & Markdown) 至 Candidate DB 的同層 output 目錄。"""
        out_dir = self.candidate_db_path.parent / "backfill_reports"
        out_dir.mkdir(parents=True, exist_ok=True)

        dt_tag = datetime.now().strftime("%Y%m%d_%H%M%S")
        json_path = out_dir / f"phase3c_backfill_summary_{dt_tag}.json"
        md_path = out_dir / f"phase3c_backfill_summary_{dt_tag}.md"

        summary_dict = asdict(summary)
        json_path.write_text(
            json.dumps(summary_dict, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        md_content = f"""# Phase 3C 候選資料回補執行摘要

- **執行時間**: `{summary.started_at}` ~ `{summary.finished_at}`
- **模式**: `{'DRY-RUN (唯讀測試)' if summary.dry_run else 'APPLY (寫入 Candidate DB)'}`
- **目標 Candidate DB**: `{summary.candidate_db_path}`
- **回補區間**: `{summary.start_date}` 至 `{summary.end_date}`
- **選擇來源**: `{', '.join(summary.sources)}`

## 交易日統計
- **總天數**: {summary.total_days}
- **官方交易日數**: {summary.trading_days_count}
- **休市日數**: {summary.non_trading_days_count}
- **未知／無證據日數**: {summary.unknown_days_count}

## 回補執行結果
- **是否安全取消**: {summary.cancelled}
- **成功完成日數**: {summary.succeeded_days_count}
- **跳過日數 (非交易日/已存在/TDCC邊界)**: {summary.skipped_days_count}
- **失敗待重試日數**: {summary.failed_days_count}
- **總寫入資料列數**: {summary.total_rows_inserted}
- **TDCC 歷史狀態**: `{summary.tdcc_historical_status}`

> [!IMPORTANT]
> **資料治理免責宣告**：本資料庫及寫入數據為 Phase 3C 候選研究資料 (Candidate Data)，絕不直接參與 ScoringEngine、Recommendation、Advice、Portfolio 或任何投資交易邏輯。
"""
        md_path.write_text(md_content, encoding="utf-8")
        logger.info(f"回補摘要報告已產出: {json_path}")
