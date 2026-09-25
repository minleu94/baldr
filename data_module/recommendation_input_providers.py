"""Read-only source providers used while preparing recommendation inputs.

The providers in this module return source facts and preserve the legacy
recommendation read boundaries.  They do not apply recommendation rules.
"""

from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
import sqlite3
from threading import RLock
from typing import Any, Callable, Mapping

import pandas as pd

from data_module.fundamental_data import MonthlyRevenueRecord
from data_module.fundamental_sqlite_provider import FundamentalSQLiteProvider
from data_module.pit_sector_membership_reader import (
    PITMembershipReadResult,
    PITSectorMembershipReader,
)


@dataclass(frozen=True, slots=True)
class ValuationPEObservation:
    """One observed PE row with its source lineage intact."""

    value: object
    as_of_date: object
    available_date: object
    source: object
    source_version: object
    quality: object

    def as_context(self) -> dict[str, object]:
        return {
            "value": self.value,
            "as_of_date": self.as_of_date,
            "available_date": self.available_date,
            "source": self.source,
            "source_version": self.source_version,
            "quality": self.quality,
        }


class HistoricalRecommendationMarketFrameProvider:
    """讀取既有 SQLite／CSV 歷史行情，不建立 SQLite 檔案。"""

    def __init__(self, config: Any) -> None:
        self.config = config

    def __call__(self, cutoff: str | None) -> pd.DataFrame:
        if getattr(self.config, "use_sqlite", False):
            db_path = Path(self.config.db_file).resolve()
            uri = f"{db_path.as_uri()}?mode=ro"
            with closing(sqlite3.connect(uri, uri=True)) as connection:
                connection.execute("PRAGMA query_only=ON")
                tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                }
                if cutoff is None:
                    latest = connection.execute(
                        "SELECT MAX(日期) FROM daily_prices"
                    ).fetchone()[0]
                    if latest is None:
                        return pd.DataFrame(columns=["日期", "證券代號"])
                    cutoff = _normalize_source_date(latest)
                start = (pd.Timestamp(cutoff) - pd.Timedelta(days=60)).strftime(
                    "%Y%m%d"
                )
                end = cutoff.replace("-", "")
                if "technical_indicators" in tables:
                    query = (
                        "SELECT p.*, t.* FROM daily_prices p LEFT JOIN "
                        "technical_indicators t ON p.證券代號=t.證券代號 "
                        "AND p.日期=t.日期 "
                    )
                else:
                    query = "SELECT p.* FROM daily_prices p "
                query += (
                    "WHERE replace(CAST(p.日期 AS TEXT), '-', '') BETWEEN ? AND ? "
                    "ORDER BY p.日期, p.證券代號"
                )
                frame = pd.read_sql_query(query, connection, params=(start, end))
                return frame.loc[:, ~frame.columns.duplicated()].copy()

        paths = (
            getattr(self.config, "all_stocks_data_file", None),
            getattr(self.config, "stock_data_file", None),
        )
        for candidate in paths:
            if candidate is not None and candidate.is_file():
                return pd.read_csv(
                    candidate,
                    encoding="utf-8-sig",
                    dtype={"證券代號": str, "股票代號": str},
                )
        raise FileNotFoundError("歷史推薦缺少唯讀行情來源")


class PITRecommendationMembershipProvider:
    """以推薦既有 PIT 日期／scope 規則讀取產業 membership。"""

    def __init__(
        self,
        reader: PITSectorMembershipReader | None,
        *,
        configured_market_scope: str | None = None,
    ) -> None:
        self.reader = reader
        self.configured_market_scope = configured_market_scope

    def read(
        self,
        cutoff: str,
        config: Mapping[str, Any],
    ) -> PITMembershipReadResult | None:
        reader = self.reader
        if reader is None:
            return None
        decision_date = date.fromisoformat(cutoff)
        configured_cutoff = config.get("pit_decision_at") or config.get("decision_at")
        decision_at = configured_cutoff or reader.default_decision_at(decision_date)
        market_scope = config.get("pit_market_scope") or self.configured_market_scope
        try:
            return reader.read(
                as_of_date=decision_date,
                decision_at=decision_at,
                market_scope=market_scope,
            )
        except Exception as exc:  # noqa: BLE001 - recommendation fails closed
            return PITMembershipReadResult(
                as_of_date=decision_date,
                decision_at=reader.default_decision_at(decision_date),
                status="unavailable",
                quality="missing",
                rows=(),
                warnings=(f"pit_membership_reader_error:{type(exc).__name__}",),
                lineage={
                    "reader_schema_version": "pit-sector-membership-reader.v1",
                    "status": "unavailable",
                    "market_scope_requested": None,
                    "error": str(exc),
                },
            )


class RecommendationFundamentalInputProvider:
    """逐候選讀取推薦使用的 PE 與受治理月營收 source facts。

    月營收 provider 必須由 composition/application 傳入或以 factory 注入；
    明示 provider 視為已初始化的舊 cache。Factory 路徑保留首次 DB missing
    後不重試的行為。PE 查詢使用 SQLite read-only URI，並保留原推薦查詢
    排序及 lineage 欄位。
    """

    def __init__(
        self,
        db_file: Path,
        monthly_revenue_provider: FundamentalSQLiteProvider | None = None,
        *,
        monthly_revenue_provider_factory: Callable[
            [], FundamentalSQLiteProvider | None
        ]
        | None = None,
    ) -> None:
        self.db_file = Path(db_file)
        self.monthly_revenue_provider = monthly_revenue_provider
        self._monthly_revenue_provider_factory = monthly_revenue_provider_factory
        self._monthly_provider_initialization_attempted = monthly_revenue_provider is not None
        self._monthly_provider_lock = RLock()

    def load_pe(
        self,
        *,
        stock_code: str,
        decision_date: str,
    ) -> ValuationPEObservation | None:
        db_path = self.db_file.resolve()
        with closing(
            sqlite3.connect(f"{db_path.as_uri()}?mode=ro", uri=True)
        ) as connection:
            connection.execute("PRAGMA query_only=ON")
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                "SELECT value, as_of_date, available_date, source, source_version, quality "
                "FROM fundamental_valuation_metrics "
                "WHERE stock_code = ? AND metric_name = 'pe' "
                "AND available_date <= ? AND as_of_date <= ? AND quality = 'observed' "
                "ORDER BY as_of_date DESC, available_date DESC, source_version DESC LIMIT 1",
                (stock_code, decision_date, decision_date),
            ).fetchone()
        if row is None or row["value"] is None:
            return None
        return ValuationPEObservation(
            value=row["value"],
            as_of_date=row["as_of_date"],
            available_date=row["available_date"],
            source=row["source"],
            source_version=row["source_version"],
            quality=row["quality"],
        )

    def load_monthly_revenues(
        self,
        *,
        stock_code: str,
        decision_date: date,
    ) -> tuple[MonthlyRevenueRecord, ...]:
        provider = self.get_monthly_revenue_provider()
        if provider is None:
            return ()
        return provider.load_monthly_revenues(
            stock_code=stock_code,
            decision_date=decision_date,
        )

    def get_monthly_revenue_provider(self) -> FundamentalSQLiteProvider | None:
        """保留 service 舊有 lazy/cache 行為，但把建構責任移到 data adapter。"""

        if self.monthly_revenue_provider is not None:
            return self.monthly_revenue_provider
        if self._monthly_provider_initialization_attempted:
            return None
        with self._monthly_provider_lock:
            if self.monthly_revenue_provider is not None:
                return self.monthly_revenue_provider
            if self._monthly_provider_initialization_attempted:
                return None
            self._monthly_provider_initialization_attempted = True
            if not self.db_file.is_file():
                return None
            factory = self._monthly_revenue_provider_factory
            if factory is None:
                return None
            self.monthly_revenue_provider = factory()
            return self.monthly_revenue_provider


def _normalize_source_date(value: object) -> str:
    if isinstance(value, (pd.Timestamp, datetime, date)):
        if pd.isna(value):
            raise ValueError("decision date is missing")
        return value.strftime("%Y-%m-%d")
    text = str(value).strip()
    normalized = text.replace("-", "").replace("/", "")
    if len(normalized) != 8 or not normalized.isdigit():
        raise ValueError(f"unsupported decision date: {text}")
    return datetime.strptime(normalized, "%Y%m%d").date().isoformat()


__all__ = (
    "HistoricalRecommendationMarketFrameProvider",
    "PITRecommendationMembershipProvider",
    "RecommendationFundamentalInputProvider",
    "ValuationPEObservation",
)
