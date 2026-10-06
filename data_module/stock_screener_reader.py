"""StockScreener 唯讀資料來源與 fallback。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
from pathlib import Path
import sqlite3
from typing import Any, Literal

import pandas as pd


logger = logging.getLogger(__name__)

FallbackSource = Literal["sqlite", "csv", "unavailable"]


@dataclass(frozen=True)
class StockFallbackFrames:
    """股票 legacy fallback 的 frames 與資料品質。"""

    frames: tuple[tuple[str, pd.DataFrame], ...]
    start_date: datetime
    days_back: int
    source_count: int
    source: FallbackSource
    quality: tuple[str, ...] = ()
    missing_source: bool = False


@dataclass(frozen=True)
class IndustryFallbackFrame:
    """產業 legacy fallback 的 frame 與資料品質。"""

    frame: pd.DataFrame | None
    source: FallbackSource
    quality: tuple[str, ...] = ()


def _readonly_connection(config: Any) -> sqlite3.Connection | None:
    db_file = Path(getattr(config, "db_file", ""))
    if not db_file.exists():
        return None

    connection = sqlite3.connect(f"{db_file.resolve().as_uri()}?mode=ro", uri=True)
    connection.execute("PRAGMA query_only=ON")
    return connection


def _recent_date_values(
    connection: sqlite3.Connection,
    table_name: str,
    date_column: str,
    limit: int,
) -> list[Any]:
    sql = f"""
        SELECT DISTINCT {date_column} AS date_value
        FROM {table_name}
        WHERE {date_column} IS NOT NULL
        ORDER BY {date_column} DESC
        LIMIT ?
    """
    rows = connection.execute(sql, (limit,)).fetchall()
    return [row[0] for row in rows if row and row[0]]


def load_recent_stock_prices(
    config: Any,
    period: str,
    volume_lookback: int,
) -> pd.DataFrame | None:
    """讀取 recent stock frame；不可用時回傳 None。"""
    if not getattr(config, "use_sqlite", False):
        return None

    lookback_limit = max(volume_lookback + 8, 32 if period == "day" else 48)
    try:
        connection = _readonly_connection(config)
        if connection is None:
            return None

        with connection:
            date_values = _recent_date_values(
                connection, "daily_prices", "日期", lookback_limit
            )
            if not date_values:
                return None

            placeholders = ",".join("?" for _ in date_values)
            sql = f"""
                SELECT
                    日期,
                    證券代號,
                    證券名稱,
                    收盤價,
                    開盤價,
                    最高價,
                    最低價,
                    成交股數,
                    成交金額
                FROM daily_prices
                WHERE 日期 IN ({placeholders})
                ORDER BY 日期 ASC, 證券代號 ASC
            """
            return pd.read_sql_query(sql, connection, params=date_values)
    except Exception as sql_err:  # noqa: BLE001 - 失敗時由明確 fallback 接手
        logger.warning(
            "SQLite 快速載入強弱勢個股資料失敗: %s，將降級為既有路徑", sql_err
        )
        return None


def load_recent_industry_indices(
    config: Any,
    period: str,
) -> pd.DataFrame | None:
    """讀取 recent industry frame；不可用時回傳 None。"""
    if not getattr(config, "use_sqlite", False):
        return None

    lookback_limit = 45 if period == "day" else 90
    try:
        connection = _readonly_connection(config)
        if connection is None:
            return None

        with connection:
            date_values = _recent_date_values(
                connection, "industry_indices", "日期", lookback_limit
            )
            if not date_values:
                return None

            placeholders = ",".join("?" for _ in date_values)
            sql = f"""
                SELECT 日期, 指數名稱, 收盤指數
                FROM industry_indices
                WHERE 日期 IN ({placeholders})
                ORDER BY 日期 ASC, 指數名稱 ASC
            """
            return pd.read_sql_query(sql, connection, params=date_values)
    except Exception as sql_err:  # noqa: BLE001 - 失敗時由明確 fallback 接手
        logger.warning(
            "SQLite 快速載入強弱勢產業資料失敗: %s，將降級為 CSV", sql_err
        )
        return None


def load_stock_fallback_frames(
    config: Any,
    period: str,
    direction: Literal["strong", "weak"],
    start_date: datetime,
    days_back: int,
) -> StockFallbackFrames:
    """載入原有 SQLite JOIN 或逐檔指標 CSV fallback frames。"""
    quality: list[str] = []
    if getattr(config, "use_sqlite", False):
        try:
            connection = _readonly_connection(config)
            if connection is not None:
                with connection:
                    max_date_df = pd.read_sql_query(
                        "SELECT MAX(日期) AS max_date FROM daily_prices;", connection
                    )
                    if not max_date_df.empty and max_date_df["max_date"].iloc[0]:
                        max_date_str = str(max_date_df["max_date"].iloc[0])
                        latest_date = datetime.strptime(max_date_str, "%Y%m%d")
                        days_back_db = 45 if period == "day" else 90
                        start_date = latest_date - timedelta(days=days_back_db)
                        start_date_str = start_date.strftime("%Y%m%d")
                        sql = """
                            SELECT p.*, t.*
                            FROM daily_prices p
                            LEFT JOIN technical_indicators t
                                ON p.證券代號 = t.證券代號 AND p.日期 = t.日期
                            WHERE p.日期 >= ?
                            ORDER BY p.日期 ASC;
                        """
                        sql_df = pd.read_sql_query(
                            sql, connection, params=(start_date_str,)
                        )
                        if not sql_df.empty:
                            sql_df = sql_df.loc[:, ~sql_df.columns.duplicated()]
                            sql_df["日期"] = pd.to_datetime(
                                sql_df["日期"].astype(str),
                                format="%Y%m%d",
                                errors="coerce",
                            )
                            sql_df = sql_df[sql_df["日期"].notna()]
                            sql_df["證券代號"] = (
                                sql_df["證券代號"].astype(str).str.strip()
                            )
                            numeric_cols = [
                                "收盤價",
                                "開盤價",
                                "最高價",
                                "最低價",
                                "成交股數",
                                "成交金額",
                            ]
                            for column in numeric_cols:
                                if column in sql_df.columns:
                                    sql_df[column] = pd.to_numeric(
                                        sql_df[column], errors="coerce"
                                    )

                            grouped_frames = tuple(
                                (stock_code, group.sort_values("日期"))
                                for stock_code, group in sql_df.groupby("證券代號")
                                if len(stock_code) == 4 and stock_code.isdigit()
                            )
                            logger.info(
                                "成功從 SQLite 載入 %s 支股票數據進行%s勢股篩選",
                                len(grouped_frames),
                                "強" if direction == "strong" else "弱",
                            )
                            return StockFallbackFrames(
                                frames=grouped_frames,
                                start_date=start_date,
                                days_back=days_back,
                                source_count=len(grouped_frames),
                                source="sqlite",
                                quality=tuple(quality),
                            )
        except Exception as db_err:  # noqa: BLE001 - 保留 CSV 降級
            quality.append(f"sqlite_fallback_failed:{db_err}")
            logger.warning(
                "從 SQLite 載入篩選數據失敗: %s，將降級為 CSV 掃描", db_err
            )
            start_date = datetime.now() - timedelta(days=days_back)

    technical_dir = Path(getattr(config, "technical_dir", ""))
    if not technical_dir.exists():
        message = f"錯誤：技術指標目錄不存在: {technical_dir}"
        logger.warning(message)
        quality.append("technical_indicator_directory_missing")
        return StockFallbackFrames(
            frames=(),
            start_date=start_date,
            days_back=days_back,
            source_count=0,
            source="unavailable",
            quality=tuple(quality),
            missing_source=True,
        )

    indicator_files = list(technical_dir.glob("*_indicators.csv"))
    if not indicator_files:
        message = f"錯誤：在 {technical_dir} 中找不到任何指標文件"
        logger.warning(message)
        quality.append("technical_indicator_files_missing")
        return StockFallbackFrames(
            frames=(),
            start_date=start_date,
            days_back=days_back,
            source_count=0,
            source="unavailable",
            quality=tuple(quality),
            missing_source=True,
        )

    frames: list[tuple[str, pd.DataFrame]] = []
    for indicator_file in indicator_files:
        stock_code = indicator_file.stem.replace("_indicators", "")
        try:
            frames.append(
                (
                    stock_code,
                    pd.read_csv(indicator_file, encoding="utf-8-sig"),
                )
            )
        except Exception as read_err:  # noqa: BLE001 - 單檔失敗時略過該檔
            logger.debug("[StockScreener] 跳過 %s: %s", indicator_file, read_err)
            quality.append(f"indicator_csv_unreadable:{indicator_file.name}")

    logger.info(
        "[StockScreener] period=%s, days_back=%s, start_date=%s",
        period,
        days_back,
        start_date.strftime("%Y-%m-%d"),
    )
    logger.info("[StockScreener] 找到 %s 個指標文件", len(indicator_files))
    return StockFallbackFrames(
        frames=tuple(frames),
        start_date=start_date,
        days_back=days_back,
        source_count=len(indicator_files),
        source="csv",
        quality=tuple(quality),
    )


def load_industry_fallback_frame(
    config: Any,
    direction: Literal["strong", "weak"],
) -> IndustryFallbackFrame:
    """載入原有產業 SQLite 或 CSV fallback frame。"""
    quality: list[str] = []
    if getattr(config, "use_sqlite", False):
        try:
            connection = _readonly_connection(config)
            if connection is not None:
                with connection:
                    sql_df = pd.read_sql_query(
                        "SELECT * FROM industry_indices ORDER BY 日期 ASC;",
                        connection,
                    )
                if not sql_df.empty:
                    sql_df["日期"] = pd.to_datetime(
                        sql_df["日期"].astype(str),
                        format="%Y%m%d",
                        errors="coerce",
                    ).dt.strftime("%Y-%m-%d")
                    logger.info(
                        "成功從 SQLite 載入產業指數數據進行%s勢產業篩選",
                        "強" if direction == "strong" else "弱",
                    )
                    return IndustryFallbackFrame(
                        frame=sql_df,
                        source="sqlite",
                        quality=tuple(quality),
                    )
        except Exception as sql_err:  # noqa: BLE001 - 保留 CSV 降級
            quality.append(f"sqlite_fallback_failed:{sql_err}")
            logger.warning(
                "從 SQLite 載入產業指數數據失敗: %s，將降級讀取 CSV", sql_err
            )

    configured_path = Path(getattr(config, "industry_index_file", ""))
    technical_dir = Path(getattr(config, "technical_dir", ""))
    meta_data_dir = Path(getattr(config, "meta_data_dir", ""))
    candidates = (
        configured_path,
        technical_dir / "industry_index.csv",
        meta_data_dir / "industry_index.csv",
    )
    industry_file = next((path for path in candidates if path.exists()), None)
    if industry_file is None:
        quality.append("industry_index_csv_missing")
        if direction == "strong":
            logger.warning("錯誤：找不到 industry_index.csv")
            logger.warning("嘗試的路徑：")
            for index, path in enumerate(candidates, start=1):
                logger.warning("  %s. %s", index, path)
        return IndustryFallbackFrame(
            frame=None,
            source="unavailable",
            quality=tuple(quality),
        )

    try:
        frame = pd.read_csv(industry_file, encoding="utf-8-sig")
        return IndustryFallbackFrame(
            frame=frame,
            source="csv",
            quality=tuple(quality),
        )
    except Exception as read_err:  # noqa: BLE001 - 沿用既有空結果降級
        if direction == "strong":
            logger.error("讀取文件失敗: %s", industry_file)
            logger.error("錯誤: %s", read_err)
        quality.append(f"industry_index_csv_unreadable:{industry_file.name}")
        return IndustryFallbackFrame(
            frame=None,
            source="unavailable",
            quality=tuple(quality),
        )
