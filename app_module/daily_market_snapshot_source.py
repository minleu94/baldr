"""共用研究快照的有界唯讀來源；沿用個股報告既有價格／指標查詢。"""

from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Callable, Sequence
from datetime import date
from pathlib import Path
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from app_module.daily_market_snapshot_producer import DailyMarketSnapshotInput

from app_module.research_run_dtos import canonical_json
from app_module.stock_research_report_dtos import StockPricePointDTO, StockTechnicalSnapshotDTO
from app_module.sqlite_read_only import connect_read_only_sqlite, configure_read_only_connection, cooperative_read_cancellation


def daily_snapshot_schema_identity(price_columns: Sequence[str], technical_columns: Sequence[str]) -> str:
    return hashlib.sha256(canonical_json({
        "daily_prices": sorted(price_columns),
        "technical_indicators": sorted(technical_columns),
    }).encode("utf-8")).hexdigest()


def daily_snapshot_scope_identity(db_path: Path, stock_code: str, schema_identity: str) -> str:
    source_hash = hashlib.sha256(canonical_json({
        "database": str(db_path.resolve()), "schema_identity": schema_identity,
    }).encode("utf-8")).hexdigest()
    return f"daily-market-source:{source_hash}:stock:{stock_code}"


def _source_pin(path: Path) -> tuple[tuple[str, int, int, int, int] | tuple[str], ...]:
    pins: list[tuple[str, int, int, int, int] | tuple[str]] = []
    # SHM是共享索引metadata；SQLite read transaction承擔內容一致性，WAL／main變動另拒絕。
    for candidate in (path, Path(str(path) + "-wal")):
        try:
            stat = candidate.stat()
        except FileNotFoundError:
            pins.append((str(candidate),))
        else:
            pins.append((str(candidate), stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns))
    return tuple(pins)


class SQLiteDailyMarketSnapshotSource:
    """同一query-only SQLite snapshot讀取明示股票，每股最多120筆既有DTO。"""

    def __init__(self, db_path: Path | str, decision_date: date, *, cancel_callback: Callable[[], bool] | None = None):
        self.db_path = Path(db_path).resolve()
        self.decision_date = decision_date
        self.cancel_callback = cancel_callback
        self._connection: Any = None
        self._reader: Any = None
        self._pin: Any = None
        self.schema_identity = ""

    def __enter__(self) -> SQLiteDailyMarketSnapshotSource:
        from types import SimpleNamespace
        from app_module.stock_research_report_service import StockResearchReportReadService

        connection = connect_read_only_sqlite(self.db_path)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("BEGIN")
            # 首次schema SELECT建立SQLite snapshot，再固定main／WAL身份；不把觀測時間補成available-at。
            columns = {
                table: tuple(str(row[1]) for row in connection.execute(f'PRAGMA table_info("{table}")'))
                for table in ("daily_prices", "technical_indicators")
            }
            required = (
                ("daily_prices", (("日期", "Date"), ("證券代號", "stock_code", "Code"), ("開盤價", "Open"), ("最高價", "High"), ("最低價", "Low"), ("收盤價", "Close"))),
                ("technical_indicators", (("日期", "Date"), ("證券代號", "stock_code", "Code"), ("MA20",), ("MA60",))),
            )
            for table, groups in required:
                for alternatives in groups:
                    if not any(name in columns[table] for name in alternatives):
                        raise ValueError(f"daily_market_source_schema_incompatible:{table}:{'/'.join(alternatives)}")

            class TransactionReader(StockResearchReportReadService):
                def _columns(self, table: str) -> tuple[str, ...]:
                    return columns.get(table, ())

                def _query(self, sql: str, params: tuple[Any, ...]) -> list[Any]:
                    return list(connection.execute(sql, params).fetchall())

            self._reader = TransactionReader(SimpleNamespace(db_file=self.db_path, output_root=None))
            self.schema_identity = daily_snapshot_schema_identity(columns["daily_prices"], columns["technical_indicators"])
            self._connection = connection
            self._pin = _source_pin(self.db_path)
            return self
        except BaseException:
            connection.close()
            raise

    def __exit__(self, *_args: object) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None
            self._reader = None

    def validate_source_stable(self) -> None:
        if self._connection is None:
            raise RuntimeError("daily_market_source_not_open")
        if _source_pin(self.db_path) != self._pin:
            raise ValueError("daily_market_source_changed_during_read")

    def load(
        self, stock_code: str, *, include_bbands30_upper: bool = False
    ) -> tuple[tuple[StockPricePointDTO, ...], StockTechnicalSnapshotDTO | None, str, dict[str, str]]:
        if self._reader is None:
            raise RuntimeError("daily_market_source_not_open")
        if not isinstance(include_bbands30_upper, bool):
            raise TypeError("include_bbands30_upper 必須是 bool")
        if not stock_code or not stock_code.isalnum() or len(stock_code) > 16:
            raise ValueError("daily_market_source_invalid_stock")
        self.validate_source_stable()
        with cooperative_read_cancellation(self.cancel_callback):
            configure_read_only_connection(self._connection)
            points, _price_source, _name = self._reader._read_prices(stock_code, self.decision_date)
            if include_bbands30_upper:
                technical, _technical_source = self._reader._read_technical(
                    stock_code,
                    self.decision_date,
                    include_bbands30_upper=True,
                )
            else:
                technical, _technical_source = self._reader._read_technical(
                    stock_code, self.decision_date
                )
        self.validate_source_stable()
        # Producer輸入型別由同包契約提供；此入口不觸發完整report／ML或其他providers。
        return points, technical, daily_snapshot_scope_identity(self.db_path, stock_code, self.schema_identity), {
            "database": str(self.db_path),
            "schema_identity_sha256": self.schema_identity,
            "price": f"{self.db_path}#daily_prices",
            "technical": f"{self.db_path}#technical_indicators",
        }

    def load_input(
        self, stock_code: str, *, include_bbands30_upper: bool = False
    ) -> DailyMarketSnapshotInput:
        """新producer保存同一transaction的價格與MA歷史，舊load四欄介面保留。"""
        from app_module.daily_market_snapshot_producer import DailyMarketSnapshotInput

        if not isinstance(include_bbands30_upper, bool):
            raise TypeError("include_bbands30_upper 必須是 bool")
        if include_bbands30_upper:
            points, technical, scope, refs = self.load(
                stock_code, include_bbands30_upper=True
            )
        else:
            points, technical, scope, refs = self.load(stock_code)
        with cooperative_read_cancellation(self.cancel_callback):
            configure_read_only_connection(self._connection)
            history = self._reader._read_technical_history(stock_code, self.decision_date, points)
        self.validate_source_stable()
        return DailyMarketSnapshotInput(stock_code, scope, points, technical, refs, history)
