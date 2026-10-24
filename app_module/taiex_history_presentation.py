"""供市場研究 UI 使用的唯讀 TAIEX 歷史 OHLCV 投影。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
import sqlite3
from typing import Final, Sequence


TAIEX_SOURCE_ID: Final[str] = "sqlite.market_indices:TAIEX"
_REQUIRED_COLUMNS: Final[frozenset[str]] = frozenset(
    {"日期", "指數名稱", "收盤指數"}
)
_BAR_COLUMNS: Final[tuple[str, ...]] = (
    "開盤價",
    "最高價",
    "最低價",
    "收盤指數",
    "成交量",
)
_DATE_KEY_SQL: Final[str] = (
    "CASE WHEN length(trim(\"日期\")) = 8 "
    "THEN trim(\"日期\") "
    "ELSE replace(trim(\"日期\"), '-', '') END"
)


@dataclass(frozen=True)
class TaiexHistoryBarDTO:
    """單一 TAIEX 觀測列；缺少的原始欄位保持 None。"""

    trade_date: date
    open: Decimal | None
    high: Decimal | None
    low: Decimal | None
    close: Decimal | None
    volume: int | None


@dataclass(frozen=True)
class TaiexHistoryDTO:
    """有界歷史資料與其可得性限制。"""

    requested_as_of: date
    effective_date: date | None
    bars: tuple[TaiexHistoryBarDTO, ...]
    quality: str
    warnings: tuple[str, ...]
    source_id: str = TAIEX_SOURCE_ID
    historical_pit_eligible: bool = False
    known_at: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "bars", tuple(self.bars))
        object.__setattr__(self, "warnings", tuple(str(item) for item in self.warnings))
        if self.source_id != TAIEX_SOURCE_ID:
            raise ValueError("source_id 必須使用固定 TAIEX SQLite 來源")
        if self.historical_pit_eligible is not False:
            raise ValueError("TAIEX 歷史 OHLCV 不具 historical PIT 資格")
        if self.known_at is not None:
            raise ValueError("market_indices 沒有可驗證的通用 known_at")


class TaiexHistoryReader:
    """以唯讀 SQLite 載入有界的 TAIEX 歷史列。"""

    def __init__(self, db_path: str | Path | None) -> None:
        self._db_path = Path(db_path) if db_path is not None else None

    def read(self, as_of_date: date, max_sessions: int = 60) -> TaiexHistoryDTO:
        """讀取截至指定觀測日的最近 N 個不同日期；不推定資料可得時間。

        ``max_sessions`` 僅接受 1 至 120 的整數。無效參數會明確拒絕。
        日期欄僅支援資料契約中的 YYYYMMDD 與 YYYY-MM-DD 表示。
        """

        if type(as_of_date) is not date:
            raise ValueError("as_of_date 必須是 datetime.date")
        if type(max_sessions) is not int or not 1 <= max_sessions <= 120:
            raise ValueError("max_sessions 必須介於 1 到 120")
        if self._db_path is None:
            return self._unavailable(as_of_date, "market_indices_db_path_unavailable")

        try:
            return self._read_sqlite(as_of_date, max_sessions)
        except (OSError, sqlite3.Error, ValueError, TypeError, InvalidOperation) as exc:
            return self._unavailable(
                as_of_date,
                f"taiex_history_read_failed:{type(exc).__name__}",
            )

    def _read_sqlite(self, as_of_date: date, max_sessions: int) -> TaiexHistoryDTO:
        db_path = self._db_path
        if db_path is None:
            return self._unavailable(as_of_date, "market_indices_db_path_unavailable")
        database_uri = db_path.resolve().as_uri() + "?mode=ro"
        connection = sqlite3.connect(database_uri, uri=True)
        try:
            connection.execute("PRAGMA query_only = ON")
            connection.execute("BEGIN")
            table_info = connection.execute('PRAGMA table_info("market_indices")').fetchall()
            if not table_info:
                return self._unavailable(as_of_date, "market_indices_table_missing")

            available = {str(row[1]) for row in table_info}
            if not _REQUIRED_COLUMNS <= available:
                return self._unavailable(as_of_date, "market_indices_required_schema_missing")

            selected_dates = self._select_dates(connection, as_of_date, max_sessions)
            if not selected_dates:
                return TaiexHistoryDTO(
                    requested_as_of=as_of_date,
                    effective_date=None,
                    bars=(),
                    quality="missing",
                    warnings=("taiex_history_no_rows_on_or_before_as_of",),
                )

            placeholders = ", ".join("?" for _ in selected_dates)
            columns = [column for column in _BAR_COLUMNS if column in available]
            if "收盤價" in available:
                columns.append("收盤價")
            selected_columns = ["日期", "指數名稱", *columns]
            quoted_columns = ", ".join(self._quoted_column(item) for item in selected_columns)
            rows = connection.execute(
                f'SELECT {quoted_columns} FROM "market_indices" '
                f'WHERE "指數名稱" = ? AND {_DATE_KEY_SQL} IN ({placeholders}) '
                'LIMIT ?',
                ("TAIEX", *selected_dates, len(selected_dates) + 1),
            ).fetchall()
            if len(rows) > len(selected_dates):
                return self._unavailable(
                    as_of_date,
                    "taiex_history_duplicate_date_fail_closed",
                )
        finally:
            connection.close()

        grouped: dict[date, list[tuple[object, ...]]] = {}
        warnings: list[str] = []
        for row in rows:
            try:
                trade_date = _parse_trade_date(row[0])
            except ValueError:
                warnings.append("taiex_history_invalid_trade_date_omitted")
                continue
            if trade_date > as_of_date:
                continue
            grouped.setdefault(trade_date, []).append(tuple(row))

        duplicate_dates = sorted(day for day, matching in grouped.items() if len(matching) != 1)
        if duplicate_dates:
            return self._unavailable(
                as_of_date,
                "taiex_history_duplicate_date_fail_closed",
            )

        index = {column: position for position, column in enumerate(selected_columns)}
        bars: list[TaiexHistoryBarDTO] = []
        partial = False
        for trade_date in sorted(grouped):
            row = grouped[trade_date][0]
            close_index = index["收盤指數"]
            close = _positive_decimal_or_none(row[close_index])
            if "收盤價" in available:
                companion = _positive_decimal_or_none(row[index["收盤價"]])
                if companion != close:
                    warnings.append(
                        f"taiex_history_conflicting_close_omitted:{trade_date.isoformat()}"
                    )
                    partial = True
                    continue

            opening = self._optional_price(row, index.get("開盤價"))
            high = self._optional_price(row, index.get("最高價"))
            low = self._optional_price(row, index.get("最低價"))
            volume = self._optional_volume(row, index.get("成交量"))
            if any(value is None for value in (opening, high, low, close, volume)):
                partial = True
                warnings.append(f"taiex_history_incomplete_ohlcv:{trade_date.isoformat()}")
            bars.append(
                TaiexHistoryBarDTO(
                    trade_date=trade_date,
                    open=opening,
                    high=high,
                    low=low,
                    close=close,
                    volume=volume,
                )
            )

        if not bars:
            return TaiexHistoryDTO(
                requested_as_of=as_of_date,
                effective_date=None,
                bars=(),
                quality="missing",
                warnings=tuple(dict.fromkeys(warnings or ["taiex_history_no_valid_rows"])),
            )
        if warnings and any("conflicting_close" in item for item in warnings):
            quality = "partial"
        elif partial or warnings:
            quality = "partial"
        else:
            quality = "complete"
        return TaiexHistoryDTO(
            requested_as_of=as_of_date,
            effective_date=bars[-1].trade_date,
            bars=tuple(bars),
            quality=quality,
            warnings=tuple(dict.fromkeys(warnings)),
        )

    @staticmethod
    def _select_dates(
        connection: sqlite3.Connection,
        as_of_date: date,
        max_sessions: int,
    ) -> tuple[str, ...]:
        compact = as_of_date.strftime("%Y%m%d")
        iso = as_of_date.isoformat()
        rows = connection.execute(
            f'SELECT {_DATE_KEY_SQL} AS canonical_date FROM "market_indices" '
            'WHERE "指數名稱" = ? AND '
            '((length(trim("日期")) = 8 AND trim("日期") <= ?) OR '
            '(length(trim("日期")) = 10 AND trim("日期") <= ?)) '
            'GROUP BY canonical_date ORDER BY canonical_date DESC LIMIT ?',
            ("TAIEX", compact, iso, max_sessions),
        ).fetchall()
        return tuple(str(row[0]) for row in rows if row[0] is not None)

    @staticmethod
    def _quoted_column(column: str) -> str:
        if column not in _REQUIRED_COLUMNS | frozenset(_BAR_COLUMNS) | {"收盤價"}:
            raise ValueError("market_indices 欄位不在白名單")
        return '"' + column.replace('"', '""') + '"'

    @staticmethod
    def _optional_price(row: Sequence[object], position: int | None) -> Decimal | None:
        if position is None:
            return None
        return _positive_decimal_or_none(row[position])

    @staticmethod
    def _optional_volume(row: Sequence[object], position: int | None) -> int | None:
        if position is None:
            return None
        value = _decimal_or_none(row[position])
        if value is None or value < 0 or value != value.to_integral_value():
            return None
        return int(value)

    @staticmethod
    def _unavailable(as_of_date: date, warning: str) -> TaiexHistoryDTO:
        return TaiexHistoryDTO(
            requested_as_of=as_of_date,
            effective_date=None,
            bars=(),
            quality="unavailable",
            warnings=(warning,),
        )


def _parse_trade_date(value: object) -> date:
    if value is None:
        raise ValueError("日期缺失")
    text = str(value).strip()
    formats = ("%Y%m%d", "%Y-%m-%d")
    for date_format in formats:
        try:
            return datetime.strptime(text, date_format).date()
        except ValueError:
            continue
    raise ValueError("日期格式無效")


def _decimal_or_none(value: object) -> Decimal | None:
    if value is None:
        return None
    try:
        number = Decimal(str(value).strip().replace(",", ""))
    except (InvalidOperation, ValueError):
        return None
    if not number.is_finite():
        return None
    return number


def _positive_decimal_or_none(value: object) -> Decimal | None:
    """只把正數 OHLC storage 值投影為可畫出的指數價位。"""

    number = _decimal_or_none(value)
    if number is None or number <= 0:
        return None
    return number
