"""Daily Decision Desk 單次 snapshot 共用的唯讀市場資料 frame。"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from threading import RLock
from typing import Callable

import pandas as pd
from app_module.exceptions import BacktestCancelledError
from app_module.price_change_direction import CHANGE_SIGN_COLUMNS


def _install_sqlite_cancel_handler(
    connection: sqlite3.Connection,
    cancel_callback: Callable[[], bool] | None,
    *,
    check_interval: int = 1000,
) -> Callable[[], bool]:
    """安裝只屬於此 SQLite 連線的合作式取消檢查。"""

    sql_cancelled = False

    def cancel_sql() -> int:
        nonlocal sql_cancelled
        if cancel_callback is not None and cancel_callback():
            sql_cancelled = True
            return 1
        return 0

    if cancel_callback is not None:
        connection.set_progress_handler(cancel_sql, max(1, int(check_interval)))
    return lambda: sql_cancelled


class DecisionMarketFrameLoader:
    """在單次 snapshot 內重用 daily_prices，下一次 snapshot 必須 reset。"""

    SQLITE_CANCEL_CHECK_INTERVAL = 1000
    MAX_RECENT_PRICE_CACHE_ENTRIES = 2

    COLUMNS = (
        "日期",
        "證券代號",
        "收盤價",
        "漲跌價差",
        "成交股數",
        *CHANGE_SIGN_COLUMNS,
    )
    SOURCE_TIMING_COLUMNS = ("available_at", "observed_at")

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self._as_of_date: date | None = None
        self._lookback_days = 0
        self._frame: pd.DataFrame | None = None
        self._frame_source_identity: tuple[object, ...] | None = None
        self._include_source_timing = False
        self._raise_sql_errors = False
        self._recent_price_cache: dict[
            tuple[tuple[object, ...], date, int],
            dict[str, list[tuple[date, Decimal]]],
        ] = {}
        self._lock = RLock()

    def reset(self, as_of_date: date) -> None:
        with self._lock:
            self._as_of_date = as_of_date
            self._lookback_days = 0
            self._frame = None
            self._frame_source_identity = None
            self._include_source_timing = False
            self._raise_sql_errors = False
            self._recent_price_cache.clear()

    def load(
        self,
        as_of_date: date,
        lookback_days: int,
        *,
        cancel_callback: Callable[[], bool] | None = None,
        include_source_timing: bool = False,
        raise_sql_errors: bool = False,
    ) -> pd.DataFrame:
        if lookback_days <= 0:
            return pd.DataFrame(columns=self._columns(include_source_timing))
        self._raise_if_cancelled(cancel_callback)
        with self._lock:
            source_identity = self._source_identity()
            if (
                self._frame is None
                or self._as_of_date != as_of_date
                or self._frame_source_identity != source_identity
                or lookback_days > self._lookback_days
                or self._include_source_timing != bool(include_source_timing)
                or self._raise_sql_errors != bool(raise_sql_errors)
            ):
                self._recent_price_cache.clear()
                if include_source_timing or raise_sql_errors:
                    frame = self._read_frame(
                        as_of_date,
                        lookback_days,
                        cancel_callback=cancel_callback,
                        include_source_timing=include_source_timing,
                        raise_sql_errors=raise_sql_errors,
                    )
                else:
                    frame = self._read_frame(
                        as_of_date,
                        lookback_days,
                        cancel_callback=cancel_callback,
                    )
                self._frame = frame
                self._as_of_date = as_of_date
                self._lookback_days = lookback_days
                self._frame_source_identity = source_identity
                self._include_source_timing = bool(include_source_timing)
                self._raise_sql_errors = bool(raise_sql_errors)
            self._raise_if_cancelled(cancel_callback)
            frame = self._slice_to_lookback(self._frame, lookback_days)
            self._raise_if_cancelled(cancel_callback)
            return frame.copy()

    def load_recent_prices(
        self,
        stock_code: str,
        decision_date: date,
        limit: int,
        *,
        cancel_callback: Callable[[], bool] | None = None,
    ) -> list[tuple[date, Decimal]]:
        if limit <= 0:
            return []
        code = str(stock_code).strip()
        return self.load_recent_prices_batch(
            (code,),
            decision_date,
            limit,
            cancel_callback=cancel_callback,
        ).get(code, [])

    def load_recent_prices_batch(
        self,
        stock_codes: tuple[str, ...],
        decision_date: date,
        limit: int,
        *,
        cancel_callback: Callable[[], bool] | None = None,
    ) -> dict[str, list[tuple[date, Decimal]]]:
        """依共用市場交易日窗口分組股票價格，供同一批次重複讀取。"""

        codes = tuple(
            dict.fromkeys(str(code).strip() for code in stock_codes if str(code).strip())
        )
        if not codes or limit <= 0:
            return {}

        self._raise_if_cancelled(cancel_callback)
        source_identity = self._source_identity()
        cache_key = (source_identity, decision_date, int(limit))
        with self._lock:
            prices_by_code = self._recent_price_cache.get(cache_key)
            if prices_by_code is None:
                frame = self.load(
                    decision_date,
                    limit,
                    cancel_callback=cancel_callback,
                )
                grouped: defaultdict[str, list[tuple[date, Decimal]]] = defaultdict(list)
                if not frame.empty:
                    columns = frame[["證券代號", "日期", "收盤價"]]
                    for index, (raw_code, raw_date, raw_price) in enumerate(
                        columns.itertuples(index=False, name=None)
                    ):
                        if index % 256 == 0:
                            self._raise_if_cancelled(cancel_callback)
                        code = str(raw_code).strip()
                        parsed_date = self._parse_date(raw_date)
                        if not code or parsed_date is None or parsed_date > decision_date:
                            continue
                        try:
                            price = Decimal(str(raw_price).replace(",", ""))
                        except (InvalidOperation, TypeError, ValueError):
                            continue
                        if price.is_finite() and price > 0:
                            grouped[code].append((parsed_date, price))

                prices_by_code = {}
                for code, prices in grouped.items():
                    prices.sort(key=lambda item: item[0], reverse=True)
                    prices_by_code[code] = prices[:limit]
                self._raise_if_cancelled(cancel_callback)
                self._recent_price_cache[cache_key] = prices_by_code
                while len(self._recent_price_cache) > self.MAX_RECENT_PRICE_CACHE_ENTRIES:
                    oldest_key = next(iter(self._recent_price_cache))
                    del self._recent_price_cache[oldest_key]

            self._raise_if_cancelled(cancel_callback)
            return {
                code: list(prices_by_code[code])
                for code in codes
                if code in prices_by_code
            }

    def _read_frame(
        self,
        as_of_date: date,
        lookback_days: int,
        *,
        cancel_callback: Callable[[], bool] | None = None,
        include_source_timing: bool = False,
        raise_sql_errors: bool = False,
    ) -> pd.DataFrame:
        if not self.db_path.exists():
            return pd.DataFrame(columns=self._columns(include_source_timing))

        target_key = as_of_date.strftime("%Y%m%d")
        db_uri = f"{self.db_path.resolve().as_uri()}?mode=ro"
        was_sql_cancelled = lambda: False

        try:
            with sqlite3.connect(db_uri, uri=True) as conn:
                conn.execute("PRAGMA query_only=ON")
                if cancel_callback is not None:
                    was_sql_cancelled = _install_sqlite_cancel_handler(
                        conn,
                        cancel_callback,
                        check_interval=self.SQLITE_CANCEL_CHECK_INTERVAL,
                    )
                table_columns = {
                    str(row[1])
                    for row in conn.execute('PRAGMA table_info("daily_prices")')
                }
                date_rows = pd.read_sql_query(
                    """
                    SELECT DISTINCT 日期
                    FROM daily_prices
                    WHERE REPLACE(REPLACE(日期, '-', ''), '/', '') <= ?
                    ORDER BY REPLACE(REPLACE(日期, '-', ''), '/', '') DESC
                    LIMIT ?
                    """,
                    conn,
                    params=(target_key, int(lookback_days)),
                )
                self._raise_if_cancelled(cancel_callback)
                if date_rows.empty:
                    return pd.DataFrame(columns=self._columns(include_source_timing))
                normalized_dates = [
                    str(value).strip().replace("-", "").replace("/", "")
                    for value in date_rows["日期"].tolist()
                ]
                placeholders = ",".join("?" for _ in normalized_dates)
                sign_projection = ", ".join(
                    f'"{name}"' if name in table_columns else f'NULL AS "{name}"'
                    for name in CHANGE_SIGN_COLUMNS
                )
                timing_projection = ""
                if include_source_timing:
                    timing_projection = ", " + ", ".join(
                        f'"{name}"' if name in table_columns else f'NULL AS "{name}"'
                        for name in self.SOURCE_TIMING_COLUMNS
                    )
                frame = pd.read_sql_query(
                    f"""
                    SELECT 日期, 證券代號, 收盤價, 漲跌價差, 成交股數, {sign_projection}{timing_projection}
                    FROM daily_prices
                    WHERE REPLACE(REPLACE(日期, '-', ''), '/', '') IN ({placeholders})
                    ORDER BY REPLACE(REPLACE(日期, '-', ''), '/', '') ASC, 證券代號 ASC
                    """,
                    conn,
                    params=tuple(normalized_dates),
                )
                self._raise_if_cancelled(cancel_callback)
                return frame
        except sqlite3.Error as exc:
            if was_sql_cancelled():
                raise BacktestCancelledError("決策台市場查詢已取消。") from exc
            if raise_sql_errors:
                raise
            return pd.DataFrame(columns=self._columns(include_source_timing))
        except pd.errors.DatabaseError as exc:
            if was_sql_cancelled():
                raise BacktestCancelledError("決策台市場查詢已取消。") from exc
            raise

    @classmethod
    def _columns(cls, include_source_timing: bool) -> tuple[str, ...]:
        if include_source_timing:
            return (*cls.COLUMNS, *cls.SOURCE_TIMING_COLUMNS)
        return cls.COLUMNS

    def _source_identity(self) -> tuple[object, ...]:
        path = self.db_path.resolve()
        try:
            stat = path.stat()
        except OSError:
            return (str(path), None, None, None, None)
        return (
            str(path),
            stat.st_dev,
            stat.st_ino,
            stat.st_size,
            stat.st_mtime_ns,
        )

    @staticmethod
    def _raise_if_cancelled(
        cancel_callback: Callable[[], bool] | None,
    ) -> None:
        if cancel_callback is not None and cancel_callback():
            raise BacktestCancelledError("決策台市場資料載入已取消。")

    @classmethod
    def _slice_to_lookback(cls, frame: pd.DataFrame, lookback_days: int) -> pd.DataFrame:
        if frame.empty or "日期" not in frame.columns:
            return frame.copy()
        date_keys = frame["日期"].map(cls._normalize_date_key)
        selected_keys = sorted(
            {key for key in date_keys if key is not None},
            reverse=True,
        )[:lookback_days]
        result = frame.loc[date_keys.isin(selected_keys)].copy()
        result["_date_key"] = result["日期"].map(cls._normalize_date_key)
        result = result.sort_values(["_date_key", "證券代號"]).drop(columns=["_date_key"])
        return result.reset_index(drop=True)

    @staticmethod
    def _normalize_date_key(value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip().replace("-", "").replace("/", "")
        return text if len(text) == 8 and text.isdigit() else None

    @classmethod
    def _parse_date(cls, value: object) -> date | None:
        key = cls._normalize_date_key(value)
        if key is None:
            return None
        try:
            return datetime.strptime(key, "%Y%m%d").date()
        except ValueError:
            return None
