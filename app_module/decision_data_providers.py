"""Decision application services 的 SQLite-first 資料 provider。"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable, Iterable

import pandas as pd

from app_module.sqlite_read_only import ReadOnlySQLiteManager
from data_module.industry_mapper_data_provider import IndustryMapperDataProvider

logger = logging.getLogger(__name__)


class _DecisionProviderImmutableFallbackError(RuntimeError):
    """指出 decision 資料只能從可能過期的 immutable SQLite 視圖讀取。"""


class _DecisionProviderSQLiteReader:
    """拒絕將 immutable fallback 快照當成一般 decision 資料。"""

    def __init__(self, db_path: str | Path) -> None:
        self._reader = ReadOnlySQLiteManager(db_path)

    def execute_query(self, query: str) -> pd.DataFrame:
        frame = self._reader.execute_query(query)
        if self._reader.last_read_mode == "immutable_fallback":
            raise _DecisionProviderImmutableFallbackError(
                "SQLite immutable fallback 可能讀到過期快照；改用既有 CSV/空資料降級"
            )
        return frame


def _read_only_sqlite_factory(config: Any) -> _DecisionProviderSQLiteReader:
    """建立短生命週期 reader，並拒絕 immutable fallback 快照。"""

    return _DecisionProviderSQLiteReader(config.db_file)


class SqliteFirstFrameProvider:
    """以唯讀查詢優先、CSV 候選路徑降級提供資料框。"""

    def __init__(
        self,
        config: Any,
        *,
        table: str,
        csv_paths: Callable[[Any], Iterable[Path]],
        db_factory: Callable[[Any], Any] | None = None,
    ) -> None:
        self.config = config
        self.table = table
        self.csv_paths = csv_paths
        self.db_factory = db_factory

    def __call__(self) -> pd.DataFrame:
        if getattr(self.config, "use_sqlite", False):
            try:
                factory = self.db_factory
                if factory is None:
                    factory = _read_only_sqlite_factory
                frame = factory(self.config).execute_query(
                    f"SELECT * FROM {self.table} ORDER BY 日期 ASC;"
                )
                if not frame.empty:
                    return frame.copy()
            except Exception as exc:  # noqa: BLE001 - fallback 是既有契約
                logger.warning("SQLite 載入 %s 失敗，降級 CSV：%s", self.table, exc)

        for path in self.csv_paths(self.config):
            if path.exists():
                return pd.read_csv(path, encoding="utf-8-sig")
        return pd.DataFrame()


def market_index_frame_provider(config: Any) -> SqliteFirstFrameProvider:
    return SqliteFirstFrameProvider(
        config,
        table="market_indices",
        csv_paths=lambda current: (current.market_index_file,),
    )


def industry_index_frame_provider(config: Any) -> Callable[[], pd.DataFrame]:
    """建立 data-owned 產業指數 reader 的 app callable。"""
    return IndustryMapperDataProvider(
        config,
        db_factory=_read_only_sqlite_factory,
    ).load_industry_index_frame


def industry_companies_provider(config: Any) -> Callable[[], pd.DataFrame | None]:
    """建立 data-owned companies.csv reader 的 app callable。"""
    return IndustryMapperDataProvider(config).load_companies


def legacy_industry_index_provider(
    config: Any,
) -> Callable[[], pd.DataFrame | None]:
    """建立保留舊 fallback None／讀取錯誤語意的 data callable。"""
    return IndustryMapperDataProvider(config).load_legacy_industry_index


def recent_stock_screen_provider(config: Any) -> Callable[[str, int], Any]:
    """建立 StockScreener recent stock frame adapter。"""
    from data_module.stock_screener_reader import load_recent_stock_prices

    return lambda period, volume_lookback: load_recent_stock_prices(
        config, period, volume_lookback
    )


def recent_industry_screen_provider(config: Any) -> Callable[[str], Any]:
    """建立 StockScreener recent industry frame adapter。"""
    from data_module.stock_screener_reader import load_recent_industry_indices

    return lambda period: load_recent_industry_indices(config, period)


def stock_screen_fallback_provider(config: Any) -> Callable[..., Any]:
    """建立強弱勢個股的唯讀 legacy fallback adapter。"""
    from data_module.stock_screener_reader import load_stock_fallback_frames

    return lambda period, direction, start_date, days_back: load_stock_fallback_frames(
        config, period, direction, start_date, days_back
    )


def industry_screen_fallback_provider(config: Any) -> Callable[..., Any]:
    """建立強弱勢產業的唯讀 legacy fallback adapter。"""
    from data_module.stock_screener_reader import load_industry_fallback_frame

    return lambda direction: load_industry_fallback_frame(config, direction)
