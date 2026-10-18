"""明選不可變SQLite版本的題材觀察讀者；不建立DB、不猜發布時間或交易日。"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from pathlib import Path
import sqlite3

from app_module.theme_daily_service import (
    ThemeFlowObservation, ThemeMarketInput, ThemePriceObservation, _aware,
)
from app_module.price_change_direction import change_sign_columns, resolve_signed_change

_MAX_ROWS = 100_000


def _decimal(raw: str | None) -> Decimal | None:
    if raw is None or not raw.strip() or raw.strip() in {"--", "---"}:
        return None
    try:
        value = Decimal(raw.replace(",", ""))
    except InvalidOperation:
        return None
    return value if value.is_finite() else None


def _integer(raw: str | None) -> int | None:
    value = _decimal(raw)
    if value is None or value != value.to_integral_value():
        return None
    return int(value)


def _date(raw: str) -> date:
    return date.fromisoformat(raw if "-" in raw else f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}")


class SQLiteThemeMarketReader:
    """只讀已封存且hash相符的DB；available_at由保存版本證據提供。

    該時間表示本機完整保存後的可用小時，不是官方發布時間。
    法人數量沿既有institutional_flows的股數欄位；缺金額不以價格推算。
    """

    def __init__(
        self, database: Path, *, expected_sha256: str, available_at: datetime,
        previous_sessions: tuple[date, ...] = (), session_source_id: str = "",
    ) -> None:
        _aware(available_at)
        if len(expected_sha256) != 64 or any(c not in "0123456789abcdef" for c in expected_sha256):
            raise ValueError("須明選SQLite版本SHA256")
        local_clock = available_at.astimezone(timezone(timedelta(hours=8)))
        if local_clock.minute or local_clock.second or local_clock.microsecond:
            raise ValueError("保存可用時間須依台北小時向上取整")
        self.database = database.resolve(strict=True)
        self.expected_sha256 = expected_sha256
        self.available_at = available_at
        self.previous_sessions = previous_sessions
        self.session_source_id = session_source_id

    def _verify(self) -> None:
        if any(Path(str(self.database) + suffix).exists() for suffix in ("-wal", "-shm", "-journal")):
            raise ValueError("須先明選無旁檔的封存SQLite版本，禁止讀取活動DB")
        digest = sha256()
        with self.database.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        if digest.hexdigest() != self.expected_sha256:
            raise ValueError("SQLite版本SHA256不符")

    @staticmethod
    def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
        # table只來自本模組固定常數。
        return {str(row[1]) for row in connection.execute(f'PRAGMA table_info("{table}")')}

    @staticmethod
    def _select(
        connection: sqlite3.Connection, table: str, stock_column: str, date_column: str,
        fields: tuple[str, ...], columns: set[str], ids: tuple[str, ...], dates: tuple[date, ...],
    ) -> list[tuple[str | None, ...]]:
        expressions = [f'CAST("{field}" AS TEXT)' if field in columns else "NULL" for field in fields]
        result: list[tuple[str | None, ...]] = []
        date_keys = tuple(key for day in dates for key in (day.isoformat(), day.strftime("%Y%m%d")))
        for offset in range(0, len(ids), 300):
            chunk = ids[offset:offset + 300]
            stock_marks = ",".join("?" for _ in chunk)
            date_marks = ",".join("?" for _ in date_keys)
            sql = (f'SELECT {",".join(expressions)} FROM "{table}" '
                   f'WHERE "{stock_column}" IN ({stock_marks}) '
                   f'AND "{date_column}" IN ({date_marks}) LIMIT ?')
            result.extend(connection.execute(sql, (*chunk, *date_keys, _MAX_ROWS + 1 - len(result))).fetchall())
            if len(result) > _MAX_ROWS:
                raise ValueError("題材來源超過限定讀取列數")
        return result

    def read(self, stock_ids: tuple[str, ...], data_date: date, known_at: datetime) -> ThemeMarketInput:
        _aware(known_at)
        if len(stock_ids) > 5000:
            raise ValueError("題材母體超過5000檔")
        self._verify()
        if not stock_ids or known_at < self.available_at:
            return ThemeMarketInput(warnings=("saved_version_not_yet_available",))
        prices: list[ThemePriceObservation] = []
        flows: list[ThemeFlowObservation] = []
        warnings: list[str] = []
        connection = sqlite3.connect(self.database.as_uri() + "?mode=ro", uri=True, timeout=5)
        try:
            connection.execute("PRAGMA query_only=ON")
            connection.execute("BEGIN")
            pc = self._columns(connection, "daily_prices")
            if {"證券代號", "日期"} <= pc:
                signs = change_sign_columns(tuple(sorted(pc)))
                fields = ("證券代號", "日期", "收盤價", "漲跌價差", "成交金額", "成交股數", *signs)
                selected = self._select(connection, "daily_prices", "證券代號", "日期", fields, pc,
                                        stock_ids, (data_date, *self.previous_sessions))
                for stock, day, close, change, turnover, volume, *direction in selected:
                    assert stock is not None and day is not None
                    signed_change, limitation = resolve_signed_change(change, direction)
                    if limitation:
                        warnings.append(limitation)
                    prices.append(ThemePriceObservation(stock, _date(day), self.available_at,
                        f"sqlite:{self.expected_sha256}:daily_prices", _decimal(close), signed_change,
                        _decimal(turnover), _integer(volume)))
            else:
                warnings.append("daily_prices_schema_unavailable")
            fc = self._columns(connection, "institutional_flows")
            if {"stock_code", "decision_date"} <= fc:
                fields = ("stock_code", "decision_date", "foreign_investor_net", "investment_trust_net", "dealer_net",
                          "observed_at", "available_date", "quality", "source_version")
                for stock, day, foreign, trust, dealer, observed, available_day, quality, version in self._select(
                    connection, "institutional_flows", "stock_code", "decision_date", fields, fc,
                    stock_ids, (data_date,),
                ):
                    assert stock is not None and day is not None
                    if quality not in {"verified", "degraded"}:
                        warnings.append("institutional_quality_unavailable")
                        continue
                    warnings.append(f"institutional_quality:{quality}")
                    clock = self.available_at
                    if observed:
                        try:
                            observed_clock = datetime.fromisoformat(observed)
                            _aware(observed_clock)
                            observed_clock = observed_clock.astimezone(timezone(timedelta(hours=8)))
                            rounded = observed_clock.replace(minute=0, second=0, microsecond=0)
                            if rounded < observed_clock:
                                rounded += timedelta(hours=1)
                            clock = max(clock, rounded)
                        except ValueError:
                            warnings.append("institutional_observed_clock_invalid")
                            continue
                    if available_day:
                        try:
                            day_clock = datetime.combine(_date(available_day), time.max,
                                tzinfo=timezone(timedelta(hours=8)))
                            if day_clock.date() > clock.astimezone(day_clock.tzinfo).date():
                                # 來源宣告尚不可用的日期，保守至該日結束，不能提前取用。
                                clock = day_clock + timedelta(microseconds=1)
                        except ValueError:
                            warnings.append("institutional_available_date_invalid")
                            continue
                    components = tuple(_integer(value) for value in (foreign, trust, dealer))
                    net = sum(value for value in components if value is not None) if all(
                        value is not None for value in components) else None
                    flows.append(ThemeFlowObservation(stock, _date(day), clock,
                        f"sqlite:{self.expected_sha256}:institutional_flows:{version or 'unprovided'}", net))
            else:
                warnings.append("institutional_flows_schema_unavailable")
        finally:
            connection.close()
        self._verify()
        return ThemeMarketInput(tuple(prices), tuple(flows), self.previous_sessions,
                                self.session_source_id, tuple(warnings))
