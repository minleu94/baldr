"""Broker Flow dashboard 專用的 SQLite 唯讀範圍查詢 repository。"""

from __future__ import annotations

import hashlib
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from app_module.broker_flow_dashboard_dtos import (
    BrokerFlowDashboardQuery,
    BrokerFlowLotQuantity,
)
from decision_module.flow_contracts import BrokerFlowEvent


_REQUIRED_COLUMNS = {
    "日期",
    "分點名稱",
    "證券代號",
    "證券名稱",
    "買進股數",
    "賣出股數",
    "買賣超股數",
    "買進金額千元",
    "賣出金額千元",
    "買賣超金額千元",
    "lots_observed",
    "amount_observed",
    "lots_rank",
    "amount_rank",
}


def _parse_date_key(raw: object) -> date:
    text = str(raw).strip()
    if len(text) != 8 or not text.isdigit():
        raise ValueError(f"invalid broker-flow date key: {text}")
    return date(int(text[:4]), int(text[4:6]), int(text[6:8]))


def _date_key_iso_map(selected_dates: tuple[date, ...]) -> dict[str, str]:
    return {
        trading_day.strftime("%Y%m%d"): trading_day.isoformat()
        for trading_day in selected_dates
    }


@dataclass(frozen=True)
class BrokerFlowReadSnapshot:
    selected_trading_dates: tuple[date, ...]
    events: tuple[BrokerFlowEvent, ...]
    tracked_branches: tuple[tuple[str, str], ...]
    quality: str
    warnings: tuple[str, ...]
    source_fingerprint: str
    query_count: int
    materialized_row_count: int


class BrokerFlowSQLiteReadRepository:
    """只允許對既有 SQLite 檔執行 query-specific read。"""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)

    def source_cache_key(self) -> str | None:
        try:
            identity = self._source_file_identity()
        except OSError:
            return None
        if identity is None:
            return None
        return hashlib.sha256(repr(identity).encode("utf-8")).hexdigest()

    def dashboard_source_cache_key(
        self, query: BrokerFlowDashboardQuery
    ) -> tuple[str, date, str] | None:
        """回傳範圍無關 dashboard 來源的安全快取鍵。"""
        source_version = self.source_cache_key()
        if source_version is None:
            return None
        return (source_version, query.requested_as_of_date, query.period)

    def load_dashboard_source(
        self, query: BrokerFlowDashboardQuery
    ) -> BrokerFlowReadSnapshot:
        return self._load_source(query)

    def load_stock_source(
        self, stock_code: str, query: BrokerFlowDashboardQuery
    ) -> BrokerFlowReadSnapshot:
        return self._load_source(query, stock_code=str(stock_code))

    def load_stock_batch_source(
        self,
        stock_codes: tuple[str, ...],
        as_of_date: date,
        *,
        trading_day_limit: int = 60,
    ) -> BrokerFlowReadSnapshot:
        codes = tuple(dict.fromkeys(str(code) for code in stock_codes if str(code)))
        if not codes:
            return self._missing("broker_flow_stock_codes_empty", query_count=0)
        if trading_day_limit < 1:
            raise ValueError("trading_day_limit must be at least 1")
        query = BrokerFlowDashboardQuery(
            period="month", scope="all", requested_as_of_date=as_of_date
        )
        return self._load_source(
            query, stock_codes=codes, trading_day_limit=trading_day_limit
        )

    def load_stock_semantic_batch(
        self,
        stock_codes: tuple[str, ...],
        as_of_date: date,
        *,
        trading_day_limit: int = 60,
        dashboard_source: BrokerFlowReadSnapshot | None = None,
        expected_source_version: str | None = None,
    ) -> BrokerFlowReadSnapshot:
        """只物件化 semantics 所需欄位，避免建立未使用的金額／rank DTO。"""
        codes = tuple(dict.fromkeys(str(code) for code in stock_codes if str(code)))
        if not codes:
            return self._missing("broker_flow_stock_codes_empty", query_count=0)
        if trading_day_limit < 1:
            raise ValueError("trading_day_limit must be at least 1")
        if dashboard_source is not None:
            reused = self._load_stock_semantic_batch_with_dashboard(
                codes,
                as_of_date,
                trading_day_limit=trading_day_limit,
                dashboard_source=dashboard_source,
                expected_source_version=expected_source_version,
            )
            if reused is not None:
                return reused
        query = BrokerFlowDashboardQuery(
            period="month", scope="all", requested_as_of_date=as_of_date
        )
        if not self.db_path.is_file():
            return self._missing("broker_flow_sqlite_missing", query_count=0)
        try:
            with closing(self._connect()) as connection:
                columns = {
                    str(row[1])
                    for row in connection.execute("PRAGMA table_info(broker_flows)")
                }
                missing_columns = sorted(_REQUIRED_COLUMNS - columns)
                if missing_columns:
                    return self._missing(
                        "broker_flows_columns_missing:" + ",".join(missing_columns),
                        query_count=1,
                    )
                selected_dates = self._load_recent_dates(
                    connection, query, limit=trading_day_limit
                )
                if not selected_dates:
                    return self._missing(
                        "broker_flow_dates_missing_for_as_of", query_count=2
                    )
                date_key_to_iso = _date_key_iso_map(selected_dates)
                rows = self._load_semantic_rows(connection, selected_dates, codes)
        except sqlite3.Error as exc:
            return self._missing(
                f"broker_flow_sqlite_read_failed:{type(exc).__name__}", query_count=0
            )

        events = self._semantic_events_from_rows(rows, date_key_to_iso)
        return BrokerFlowReadSnapshot(
            selected_trading_dates=selected_dates,
            events=tuple(events),
            tracked_branches=(),
            quality="observed",
            warnings=(),
            source_fingerprint=self._source_fingerprint(columns),
            query_count=2,
            materialized_row_count=len(events),
        )

    def _load_stock_semantic_batch_with_dashboard(
        self,
        stock_codes: tuple[str, ...],
        as_of_date: date,
        *,
        trading_day_limit: int,
        dashboard_source: BrokerFlowReadSnapshot,
        expected_source_version: str | None,
    ) -> BrokerFlowReadSnapshot | None:
        """只在來源版本與日期身份吻合時重用 dashboard 的近期事件。"""
        if (
            not expected_source_version
            or self.source_cache_key() != expected_source_version
            or dashboard_source.quality != "observed"
            or dashboard_source.warnings
            or not dashboard_source.selected_trading_dates
            or dashboard_source.selected_trading_dates[-1] != as_of_date
        ):
            return None

        try:
            with closing(self._connect()) as connection:
                columns = {
                    str(row[1])
                    for row in connection.execute("PRAGMA table_info(broker_flows)")
                }
                if sorted(_REQUIRED_COLUMNS - columns):
                    return None
                source_fingerprint = self._source_fingerprint(columns)
                if source_fingerprint != dashboard_source.source_fingerprint:
                    return None

                query = BrokerFlowDashboardQuery(
                    period="month",
                    scope="all",
                    requested_as_of_date=as_of_date,
                )
                selected_dates = self._load_recent_dates(
                    connection, query, limit=trading_day_limit
                )
                dashboard_dates = dashboard_source.selected_trading_dates
                if (
                    len(selected_dates) < trading_day_limit
                    or tuple(selected_dates[-len(dashboard_dates) :])
                    != dashboard_dates
                ):
                    return None

                dashboard_date_set = set(dashboard_dates)
                tail_dates = tuple(
                    trading_day
                    for trading_day in selected_dates
                    if trading_day not in dashboard_date_set
                )
                if not tail_dates:
                    return None
                rows = self._load_semantic_rows(
                    connection, tail_dates, stock_codes
                )
        except sqlite3.Error:
            return None

        if self.source_cache_key() != expected_source_version:
            return None

        date_key_to_iso = _date_key_iso_map(tail_dates)
        events_by_code: dict[str, list[BrokerFlowEvent]] = {
            code: [] for code in stock_codes
        }
        code_set = frozenset(stock_codes)
        dashboard_keys: set[tuple[date, str, str]] = set()
        for event in dashboard_source.events:
            if event.stock_code not in code_set:
                continue
            try:
                event_date = date.fromisoformat(str(event.date))
            except ValueError:
                return None
            if event_date not in dashboard_date_set:
                return None
            identity = (
                event_date,
                str(event.branch_system_key),
                str(event.stock_code),
            )
            if identity in dashboard_keys:
                return None
            dashboard_keys.add(identity)
            events_by_code[event.stock_code].append(event)

        tail_events = self._semantic_events_from_rows(rows, date_key_to_iso)
        for event in tail_events:
            if event.stock_code not in code_set:
                return None
            events_by_code[event.stock_code].append(event)

        names_by_code = {
            code: {
                event.stock_name
                for event in events
                if event.stock_name
            }
            for code, events in events_by_code.items()
        }
        conflicting_codes = tuple(
            code for code in stock_codes if len(names_by_code[code]) > 1
        )
        fallback_row_count = 0
        query_count = 2
        if conflicting_codes:
            fallback_source = self.load_stock_semantic_batch(
                conflicting_codes,
                as_of_date,
                trading_day_limit=trading_day_limit,
            )
            if (
                fallback_source.selected_trading_dates != selected_dates
                or fallback_source.source_fingerprint != source_fingerprint
                or self.source_cache_key() != expected_source_version
            ):
                return None
            for code in conflicting_codes:
                events_by_code[code] = []
            for event in fallback_source.events:
                events_by_code[event.stock_code].append(event)
            fallback_row_count = fallback_source.materialized_row_count
            query_count += fallback_source.query_count

        events = [event for code in stock_codes for event in events_by_code[code]]
        return BrokerFlowReadSnapshot(
            selected_trading_dates=selected_dates,
            events=tuple(events),
            tracked_branches=(),
            quality="observed",
            warnings=(),
            source_fingerprint=source_fingerprint,
            query_count=query_count,
            materialized_row_count=len(rows) + fallback_row_count,
        )

    @staticmethod
    def _semantic_events_from_rows(
        rows: list[sqlite3.Row], date_key_to_iso: dict[str, str]
    ) -> list[BrokerFlowEvent]:
        events: list[BrokerFlowEvent] = []
        for row in rows:
            buy = BrokerFlowLotQuantity.from_sqlite_shares(row["買進股數"])
            sell = BrokerFlowLotQuantity.from_sqlite_shares(row["賣出股數"])
            net = BrokerFlowLotQuantity.from_sqlite_shares(row["買賣超股數"])
            lots_observed = bool(row["lots_observed"])
            if not lots_observed:
                lots_quality = "unavailable"
                net_qty = None
            elif any(item.warnings for item in (buy, sell, net)):
                lots_quality = "degraded"
                net_qty = net.lots
            else:
                lots_quality = "observed"
                net_qty = net.lots
            branch = str(row["分點名稱"] or "").strip()
            date_key = str(row["date_key"]).strip()
            date_value = date_key_to_iso.get(date_key)
            if date_value is None:
                date_value = _parse_date_key(row["date_key"]).isoformat()
            events.append(
                BrokerFlowEvent(
                    date=date_value,
                    branch_system_key=branch,
                    branch_display_name=branch,
                    stock_code=str(row["證券代號"] or "").strip(),
                    stock_name=str(row["證券名稱"] or "").strip(),
                    net_qty=net_qty,
                    lots_available=lots_quality == "observed",
                    lots_observed=lots_observed,
                    lots_quality=lots_quality,
                )
            )
        return events

    def load_branch_source(
        self,
        branch_system_key: str,
        query: BrokerFlowDashboardQuery,
        *,
        limit: int,
    ) -> BrokerFlowReadSnapshot:
        if limit < 1:
            raise ValueError("limit must be at least 1")
        return self._load_source(
            query,
            branch_system_key=str(branch_system_key),
            row_limit=limit,
        )

    def _load_source(
        self,
        query: BrokerFlowDashboardQuery,
        *,
        stock_code: str | None = None,
        stock_codes: tuple[str, ...] | None = None,
        branch_system_key: str | None = None,
        row_limit: int | None = None,
        trading_day_limit: int | None = None,
    ) -> BrokerFlowReadSnapshot:
        if not self.db_path.is_file():
            return self._missing("broker_flow_sqlite_missing", query_count=0)

        try:
            with closing(self._connect()) as connection:
                columns = {
                    str(row[1])
                    for row in connection.execute("PRAGMA table_info(broker_flows)")
                }
                if not columns:
                    return self._missing("broker_flows_table_missing", query_count=1)
                missing_columns = sorted(_REQUIRED_COLUMNS - columns)
                if missing_columns:
                    return self._missing(
                        "broker_flows_columns_missing:" + ",".join(missing_columns),
                        query_count=1,
                    )

                selected_dates = self._load_recent_dates(
                    connection, query, limit=trading_day_limit
                )
                if not selected_dates:
                    return BrokerFlowReadSnapshot(
                        selected_trading_dates=(),
                        events=(),
                        tracked_branches=(),
                        quality="missing",
                        warnings=("broker_flow_dates_missing_for_as_of",),
                        source_fingerprint=self._source_fingerprint(columns),
                        query_count=2,
                        materialized_row_count=0,
                    )
                date_key_to_iso = _date_key_iso_map(selected_dates)
                rows = self._load_aggregated_rows(
                    connection,
                    selected_dates,
                    stock_code=stock_code,
                    stock_codes=stock_codes,
                    branch_system_key=branch_system_key,
                    row_limit=row_limit,
                )
        except sqlite3.Error as exc:
            return self._missing(
                f"broker_flow_sqlite_read_failed:{type(exc).__name__}",
                query_count=0,
            )

        events: list[BrokerFlowEvent] = []
        warnings: list[str] = []
        for row in rows:
            event, row_warnings = self._row_to_event(row, date_key_to_iso)
            events.append(event)
            warnings.extend(row_warnings)
        unique_warnings = tuple(dict.fromkeys(warnings))
        branches = tuple(
            sorted(
                {
                    (event.branch_system_key, event.branch_display_name)
                    for event in events
                }
            )
        )
        return BrokerFlowReadSnapshot(
            selected_trading_dates=selected_dates,
            events=tuple(events),
            tracked_branches=branches,
            quality="degraded" if unique_warnings else "observed",
            warnings=unique_warnings,
            source_fingerprint=self._source_fingerprint(columns),
            query_count=2,
            materialized_row_count=len(events),
        )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            f"{self.db_path.resolve().as_uri()}?mode=ro",
            uri=True,
        )
        connection.execute("PRAGMA query_only=ON")
        connection.row_factory = sqlite3.Row
        return connection

    def _load_recent_dates(
        self,
        connection: sqlite3.Connection,
        query: BrokerFlowDashboardQuery,
        *,
        limit: int | None = None,
    ) -> tuple[date, ...]:
        rows = connection.execute(
            """
            SELECT DISTINCT 日期 AS date_key
            FROM broker_flows
            WHERE 日期 <= ?
            ORDER BY date_key DESC
            LIMIT ?
            """,
            (
                query.requested_as_of_date.strftime("%Y%m%d"),
                limit or query.period_trading_days,
            ),
        ).fetchall()
        return tuple(
            sorted(_parse_date_key(row[0]) for row in rows)
        )

    def _load_aggregated_rows(
        self,
        connection: sqlite3.Connection,
        selected_dates: tuple[date, ...],
        *,
        stock_code: str | None,
        stock_codes: tuple[str, ...] | None,
        branch_system_key: str | None,
        row_limit: int | None,
    ) -> list[sqlite3.Row]:
        date_keys = tuple(item.strftime("%Y%m%d") for item in selected_dates)
        predicates = [
            "日期 IN ("
            + ",".join("?" for _ in date_keys)
            + ")"
        ]
        parameters: list[object] = list(date_keys)
        if stock_code is not None:
            predicates.append("證券代號 = ?")
            parameters.append(stock_code)
        if stock_codes is not None:
            predicates.append("證券代號 IN (" + ",".join("?" for _ in stock_codes) + ")")
            parameters.extend(stock_codes)
        if branch_system_key is not None:
            predicates.append("分點名稱 = ?")
            parameters.append(branch_system_key)

        sql = f"""
            SELECT
                日期 AS date_key,
                分點名稱,
                證券代號,
                MAX(證券名稱) AS 證券名稱,
                SUM(買進股數) AS 買進股數,
                SUM(賣出股數) AS 賣出股數,
                SUM(買賣超股數) AS 買賣超股數,
                SUM(買進金額千元) AS 買進金額千元,
                SUM(賣出金額千元) AS 賣出金額千元,
                SUM(買賣超金額千元) AS 買賣超金額千元,
                MIN(COALESCE(lots_observed, 0)) AS lots_observed,
                MIN(COALESCE(amount_observed, 0)) AS amount_observed,
                MIN(lots_rank) AS lots_rank,
                MIN(amount_rank) AS amount_rank
            FROM broker_flows
            WHERE {' AND '.join(predicates)}
            GROUP BY date_key, 分點名稱, 證券代號
            ORDER BY date_key DESC, ABS(SUM(買賣超股數)) DESC, 證券代號
        """
        if row_limit is not None:
            sql += " LIMIT ?"
            parameters.append(row_limit)
        return connection.execute(sql, tuple(parameters)).fetchall()

    def _load_semantic_rows(
        self,
        connection: sqlite3.Connection,
        selected_dates: tuple[date, ...],
        stock_codes: tuple[str, ...],
    ) -> list[sqlite3.Row]:
        date_keys = tuple(item.strftime("%Y%m%d") for item in selected_dates)
        date_placeholders = ",".join("?" for _ in date_keys)
        stock_placeholders = ",".join("?" for _ in stock_codes)
        return connection.execute(
            f"""
            SELECT 日期 AS date_key, 分點名稱, 證券代號,
                   MAX(證券名稱) AS 證券名稱,
                   SUM(買進股數) AS 買進股數,
                   SUM(賣出股數) AS 賣出股數,
                   SUM(買賣超股數) AS 買賣超股數,
                   MIN(COALESCE(lots_observed, 0)) AS lots_observed
            FROM broker_flows
            WHERE 日期 IN ({date_placeholders})
              AND 證券代號 IN ({stock_placeholders})
            GROUP BY date_key, 分點名稱, 證券代號
            ORDER BY date_key DESC, 證券代號
            """,
            (*date_keys, *stock_codes),
        ).fetchall()

    def _row_to_event(
        self,
        row: sqlite3.Row,
        date_key_to_iso: dict[str, str] | None = None,
    ) -> tuple[BrokerFlowEvent, tuple[str, ...]]:
        # These positions match the SELECT order in _load_aggregated_rows.
        buy = BrokerFlowLotQuantity.from_sqlite_shares(row[4])
        sell = BrokerFlowLotQuantity.from_sqlite_shares(row[5])
        net = BrokerFlowLotQuantity.from_sqlite_shares(row[6])
        lot_warnings = buy.warnings + sell.warnings + net.warnings
        warnings = tuple(dict.fromkeys(lot_warnings)) if lot_warnings else ()
        lots_observed = bool(row[10])
        if not lots_observed:
            lots_quality = "unavailable"
            buy_qty = sell_qty = net_qty = None
        elif warnings:
            lots_quality = "degraded"
            buy_qty, sell_qty, net_qty = buy.lots, sell.lots, net.lots
        else:
            lots_quality = "observed"
            buy_qty, sell_qty, net_qty = buy.lots, sell.lots, net.lots

        date_key = str(row[0]).strip()
        date_value = (
            date_key_to_iso.get(date_key)
            if date_key_to_iso is not None
            else None
        )
        if date_value is None:
            date_value = _parse_date_key(row["date_key"]).isoformat()
        branch = str(row[1] or "").strip()
        event = BrokerFlowEvent(
            date=date_value,
            branch_system_key=branch,
            branch_display_name=branch,
            stock_code=str(row[2] or "").strip(),
            stock_name=str(row[3] or "").strip(),
            buy_qty=buy_qty,
            sell_qty=sell_qty,
            net_qty=net_qty,
            buy_amount_k_twd=self._optional_int(row[7]),
            sell_amount_k_twd=self._optional_int(row[8]),
            net_amount_k_twd=self._optional_int(row[9]),
            lots_available=lots_quality in {"observed", "degraded"},
            has_estimated_lots=False,
            lots_observed=lots_observed,
            amount_observed=bool(row[11]),
            lots_rank=self._optional_int(row[12]),
            amount_rank=self._optional_int(row[13]),
            lots_quality=lots_quality,
            amount_quality="observed" if bool(row[11]) else "unavailable",
        )
        return event, warnings

    @staticmethod
    def _optional_int(value: object) -> int | None:
        if value is None:
            return None
        if isinstance(value, (int, str, bytes, bytearray)):
            return int(value)
        raise ValueError(f"unsupported SQLite integer value: {type(value).__name__}")

    def _source_fingerprint(self, columns: set[str]) -> str:
        try:
            identity = self._source_file_identity()
        except OSError:
            identity = None
        payload = f"{identity!r}:{','.join(sorted(columns))}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _source_file_identity(self) -> tuple[object, ...] | None:
        main = self._file_identity(self.db_path)
        if main is None:
            return None

        # A rollback journal can represent an in-progress or recovery-sensitive
        # write. Do not cache while one is present.
        if self._file_identity(self.db_path.with_name(self.db_path.name + "-journal")) is not None:
            return None

        wal = self._file_identity(self.db_path.with_name(self.db_path.name + "-wal"))
        return (main, wal)

    @staticmethod
    def _file_identity(path: Path) -> tuple[int, int, int, int, int] | None:
        try:
            stat = path.stat()
        except FileNotFoundError:
            return None
        return (
            int(stat.st_dev),
            int(stat.st_ino),
            int(stat.st_size),
            int(stat.st_mtime_ns),
            int(stat.st_ctime_ns),
        )

    def _missing(self, warning: str, *, query_count: int) -> BrokerFlowReadSnapshot:
        return BrokerFlowReadSnapshot(
            selected_trading_dates=(),
            events=(),
            tracked_branches=(),
            quality="missing",
            warnings=(warning,),
            source_fingerprint="",
            query_count=query_count,
            materialized_row_count=0,
        )


__all__ = ["BrokerFlowReadSnapshot", "BrokerFlowSQLiteReadRepository"]
