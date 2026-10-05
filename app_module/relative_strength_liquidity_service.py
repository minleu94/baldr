from __future__ import annotations

import inspect
import sqlite3
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol

import pandas as pd

from app_module.market_session_cadence import MarketSessionCadence
from app_module.decision_desk_dtos import DecisionDeskQuality, RelativeStrengthLiquiditySummary
from app_module.decision_market_frame import (
    DecisionMarketFrameLoader,
    _install_sqlite_cancel_handler,
)
from app_module.exceptions import BacktestCancelledError
from app_module.dtos.market_loop_dtos import RelativeStrengthLiquidityDTO


class RelativeStrengthLiquidityProvider(Protocol):
    def fetch(self, as_of_date: date) -> pd.DataFrame: ...


def _raise_if_cancelled(cancel_callback: Callable[[], bool] | None) -> None:
    if cancel_callback is not None and cancel_callback():
        raise BacktestCancelledError("相對強弱與流動性載入已取消。")


def _call_with_optional_cancel_callback(
    method: Callable[..., Any],
    *args: Any,
    cancel_callback: Callable[[], bool] | None,
) -> Any:
    if cancel_callback is None:
        return method(*args)

    supports_callback = False
    try:
        parameters = inspect.signature(method).parameters.values()
        supports_callback = any(
            parameter.name == "cancel_callback"
            and parameter.kind is not inspect.Parameter.POSITIONAL_ONLY
            for parameter in parameters
        ) or any(parameter.kind is inspect.Parameter.VAR_KEYWORD for parameter in parameters)
    except (TypeError, ValueError):
        pass

    _raise_if_cancelled(cancel_callback)
    if supports_callback:
        return method(*args, cancel_callback=cancel_callback)
    result = method(*args)
    _raise_if_cancelled(cancel_callback)
    return result


def _map_series_with_cancellation(
    values: pd.Series,
    mapper: Callable[[Any], Any],
    cancel_callback: Callable[[], bool] | None,
) -> pd.Series:
    if cancel_callback is None:
        return values.map(mapper)

    _raise_if_cancelled(cancel_callback)
    mapped_count = 0

    def map_with_check(value: Any) -> Any:
        nonlocal mapped_count
        if mapped_count % 256 == 0:
            _raise_if_cancelled(cancel_callback)
        mapped_count += 1
        return mapper(value)

    mapped = values.map(map_with_check)
    _raise_if_cancelled(cancel_callback)
    return mapped


class RelativeStrengthLiquidityService:
    """Build stock relative strength and liquidity ranking for Daily Decision Desk."""

    def __init__(
        self,
        provider: RelativeStrengthLiquidityProvider,
        *,
        cadence: MarketSessionCadence | None = None,
        top_n: int = 10,
        min_avg_turnover: int = 20_000_000,
        max_skipped_symbol_ratio_bp: int = 500,
    ) -> None:
        self.provider = provider
        self.cadence = cadence
        self.top_n = top_n
        self.min_avg_turnover = Decimal(int(min_avg_turnover))
        self.max_skipped_symbol_ratio_bp = min(10_000, max(0, int(max_skipped_symbol_ratio_bp)))

    def build_snapshot(
        self,
        as_of_date: date,
        *,
        cancel_callback: Callable[[], bool] | None = None,
    ) -> RelativeStrengthLiquiditySummary:
        _raise_if_cancelled(cancel_callback)
        try:
            frame = _call_with_optional_cancel_callback(
                self.provider.fetch,
                as_of_date,
                cancel_callback=cancel_callback,
            )
        except BacktestCancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            return RelativeStrengthLiquiditySummary(
                as_of_date=as_of_date,
                quality=DecisionDeskQuality.DEGRADED,
                warnings=(f"relative_strength_liquidity_provider_error:{exc}",),
            )

        _raise_if_cancelled(cancel_callback)
        if frame is None or frame.empty:
            return RelativeStrengthLiquiditySummary(
                as_of_date=as_of_date,
                quality=DecisionDeskQuality.MISSING,
                warnings=("relative_strength_liquidity_missing",),
            )

        result = self._build_from_frame(
            frame,
            as_of_date,
            cancel_callback=cancel_callback,
        )
        _raise_if_cancelled(cancel_callback)
        return result

    def build_snapshot_dto(
        self,
        as_of_date: date,
        *,
        cancel_callback: Callable[[], bool] | None = None,
    ) -> RelativeStrengthLiquidityDTO:
        """建立含決策日與有效日的相對強弱 DTO。"""

        summary = self.build_snapshot(as_of_date, cancel_callback=cancel_callback)
        return RelativeStrengthLiquidityDTO.from_summary(summary, decision_date=as_of_date)

    def _build_from_frame(
        self,
        frame: pd.DataFrame,
        as_of_date: date,
        *,
        cancel_callback: Callable[[], bool] | None = None,
    ) -> RelativeStrengthLiquiditySummary:
        _raise_if_cancelled(cancel_callback)
        required = {"日期", "證券代號", "收盤價", "成交股數"}
        if not required.issubset(set(frame.columns)):
            return RelativeStrengthLiquiditySummary(
                as_of_date=as_of_date,
                quality=DecisionDeskQuality.DEGRADED,
                warnings=("relative_strength_liquidity_missing_required_columns",),
            )

        data = frame.copy()
        data["_date"] = _map_series_with_cancellation(
            data["日期"], self._parse_date, cancel_callback
        )
        data["_close"] = _map_series_with_cancellation(
            data["收盤價"], self._to_decimal, cancel_callback
        )
        data["_volume"] = _map_series_with_cancellation(
            data["成交股數"], self._to_decimal, cancel_callback
        )
        data["_code"] = _map_series_with_cancellation(
            data["證券代號"], lambda value: str(value).strip(), cancel_callback
        )
        data = data.dropna(subset=["_date", "_close", "_volume", "_code"])

        if data.empty:
            return RelativeStrengthLiquiditySummary(
                as_of_date=as_of_date,
                quality=DecisionDeskQuality.MISSING,
                warnings=("relative_strength_liquidity_missing",),
            )

        eligible_dates = [item for item in data["_date"].unique() if item <= as_of_date]
        if not eligible_dates:
            return RelativeStrengthLiquiditySummary(
                as_of_date=as_of_date,
                quality=DecisionDeskQuality.MISSING,
                warnings=("relative_strength_liquidity_missing",),
            )
        effective_date = max(eligible_dates)
        warnings: list[str] = []
        assessment = self.cadence.assess(as_of_date, effective_date) if self.cadence else None
        if assessment is not None and assessment.status == "future_rejected":
            return RelativeStrengthLiquiditySummary(effective_date, DecisionDeskQuality.MISSING, ("relative_strength_liquidity_future_source_rejected",), meta={"cadence": assessment.metadata})
        stale = not assessment.current if assessment else effective_date != as_of_date
        if stale:
            warnings.append(f"relative_strength_liquidity_as_of_fallback:{effective_date.isoformat()}")

        ranking: list[dict[str, Any]] = []
        skipped = 0
        exclusions: list[dict[str, Any]] = []
        for stock_index, (stock_code, stock_frame) in enumerate(
            data.groupby("_code", sort=False)
        ):
            if stock_index % 64 == 0:
                _raise_if_cancelled(cancel_callback)
            item = self._rank_stock(str(stock_code), stock_frame, effective_date)
            if item is None:
                skipped += 1
                history = stock_frame.loc[stock_frame["_date"] <= effective_date].drop_duplicates("_date")
                current = history.loc[history["_date"] == effective_date]
                reason = ("insufficient_valid_history" if len(history) < 21 else
                    "missing_effective_session_quote" if current.empty else
                    "non_positive_close_or_lookback" if any(item <= 0 for item in history["_close"].tail(21)) else "turnover_unavailable")
                exclusions.append({"stock_code": str(stock_code), "reason": reason, "valid_observations": len(history),
                    "required_observations": 21, "latest_valid_date": max(history["_date"]).isoformat() if len(history) else None,
                    "effective_date": effective_date.isoformat(), "source": "sqlite_daily_prices"})
                continue
            ranking.append(item)

        _raise_if_cancelled(cancel_callback)

        if not ranking:
            return RelativeStrengthLiquiditySummary(
                as_of_date=effective_date,
                quality=DecisionDeskQuality.DEGRADED,
                warnings=tuple(warnings + ["relative_strength_liquidity_insufficient_history"]),
            )

        ranking = sorted(ranking, key=lambda item: (-int(item["strength_20d_bp"]), -int(item["strength_5d_bp"]), item["stock_code"]))
        weak = sorted(ranking, key=lambda item: (int(item["strength_20d_bp"]), int(item["strength_5d_bp"]), item["stock_code"]))
        low_liquidity = tuple(
            item["stock_code"]
            for item in ranking
            if Decimal(str(item["avg_turnover"])) < self.min_avg_turnover
        )

        if skipped:
            warnings.append(f"relative_strength_liquidity_skipped_symbols:{skipped}")

        ranked_symbol_count = len(ranking)
        total_symbol_count = ranked_symbol_count + skipped
        skipped_symbol_ratio_bp = self._ratio_bp(skipped, total_symbol_count)
        quality = (
            DecisionDeskQuality.DEGRADED
            if stale or skipped_symbol_ratio_bp > self.max_skipped_symbol_ratio_bp
            else DecisionDeskQuality.OBSERVED
        )
        return RelativeStrengthLiquiditySummary(
            as_of_date=effective_date,
            quality=quality,
            warnings=tuple(warnings),
            top_strength_codes=tuple(item["stock_code"] for item in ranking[: self.top_n]),
            weak_strength_codes=tuple(item["stock_code"] for item in weak[: self.top_n] if int(item["strength_20d_bp"]) < 0),
            low_liquidity_codes=low_liquidity,
            meta={
                "source": "relative_strength_liquidity_service",
                "min_avg_turnover": int(self.min_avg_turnover),
                "ranked_symbol_count": ranked_symbol_count,
                "skipped_symbol_count": skipped,
                "skipped_symbol_ratio_bp": skipped_symbol_ratio_bp,
                "max_skipped_symbol_ratio_bp": self.max_skipped_symbol_ratio_bp,
                "ranking": ranking[: self.top_n],
                "exclusions": exclusions,
                "cadence": assessment.metadata if assessment else None,
            },
        )

    def _rank_stock(self, stock_code: str, frame: pd.DataFrame, effective_date: date) -> dict[str, Any] | None:
        history = frame.sort_values("_date").drop_duplicates(subset=["_date"], keep="last")
        history = history.loc[history["_date"] <= effective_date]
        
        # 限制：20日相對強度必須至少有 21 個有效交易觀測值 (即當日 + 前 20 日)
        if len(history) < 21:
            return None
            
        current_rows = history.loc[history["_date"] == effective_date]
        if current_rows.empty:
            return None
        current = current_rows.iloc[-1]
        close_now = current["_close"]
        if close_now is None or close_now <= 0:
            return None

        close_5 = self._lookback_close(history, effective_date, 5)
        close_20 = self._lookback_close(history, effective_date, 20)
        if close_5 is None or close_20 is None or close_5 <= 0 or close_20 <= 0:
            return None

        strength_5d_bp = self._return_bp(close_now, close_5)
        strength_20d_bp = self._return_bp(close_now, close_20)
        avg_turnover = self._avg_turnover(history)
        if avg_turnover is None:
            return None

        return {
            "stock_code": stock_code,
            "strength_5d_bp": strength_5d_bp,
            "strength_20d_bp": strength_20d_bp,
            "avg_turnover": int(avg_turnover),
        }

    @staticmethod
    def _lookback_close(history: pd.DataFrame, effective_date: date, target_days: int) -> Decimal | None:
        prior = history.loc[history["_date"] < effective_date]
        if prior.empty:
            return None
        if len(prior) < target_days:
            return None
        value = prior.iloc[len(prior) - target_days]["_close"]
        return value if isinstance(value, Decimal) else None

    @staticmethod
    def _avg_turnover(history: pd.DataFrame) -> Decimal | None:
        turnovers: list[Decimal] = []
        for _, row in history.tail(20).iterrows():
            close_value = row["_close"]
            volume_value = row["_volume"]
            if isinstance(close_value, Decimal) and isinstance(volume_value, Decimal):
                turnovers.append(close_value * volume_value)
        if not turnovers:
            return None
        return sum(turnovers, Decimal("0")) / Decimal(len(turnovers))

    @staticmethod
    def _return_bp(current: Decimal, base: Decimal) -> int:
        value = ((current - base) / base) * Decimal("10000")
        return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    @staticmethod
    def _ratio_bp(numerator: int, denominator: int) -> int:
        if denominator <= 0:
            return 0
        value = Decimal(int(numerator)) * Decimal("10000") / Decimal(int(denominator))
        return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    @staticmethod
    def _to_decimal(value: object) -> Decimal | None:
        if value is None or isinstance(value, bool) or pd.isna(value):
            return None
        try:
            parsed = Decimal(str(value).replace(",", ""))
        except (InvalidOperation, ValueError, TypeError):
            return None
        return parsed if parsed.is_finite() else None

    @staticmethod
    def _parse_date(value: object) -> date | None:
        if isinstance(value, date) and not isinstance(value, datetime):
            return value
        text = str(value).strip().replace("-", "").replace("/", "")
        if len(text) != 8 or not text.isdigit():
            return None
        try:
            return datetime.strptime(text, "%Y%m%d").date()
        except ValueError:
            return None


class SQLiteDailyPriceRelativeStrengthLiquidityProvider:
    """Read-only provider that supplies price and volume history from SQLite daily_prices."""

    SQLITE_CANCEL_CHECK_INTERVAL = 1000

    def __init__(
        self,
        db_path: str | Path,
        *,
        lookback_days: int = 40,
        market_frame_loader: DecisionMarketFrameLoader | None = None,
    ) -> None:
        self.db_path = Path(db_path)
        self.lookback_days = lookback_days
        self.market_frame_loader = market_frame_loader

    def fetch(
        self,
        as_of_date: date,
        *,
        cancel_callback: Callable[[], bool] | None = None,
    ) -> pd.DataFrame:
        _raise_if_cancelled(cancel_callback)
        if not self.db_path.exists():
            return pd.DataFrame()
        if self.market_frame_loader is not None:
            return _call_with_optional_cancel_callback(
                self.market_frame_loader.load,
                as_of_date,
                self.lookback_days,
                cancel_callback=cancel_callback,
            )
        target_key = as_of_date.strftime("%Y%m%d")
        was_sql_cancelled = lambda: False
        try:
            db_uri = f"{self.db_path.resolve().as_uri()}?mode=ro"
            with sqlite3.connect(db_uri, uri=True) as conn:
                conn.execute("PRAGMA query_only=ON")
                if cancel_callback is not None:
                    was_sql_cancelled = _install_sqlite_cancel_handler(
                        conn,
                        cancel_callback,
                        check_interval=self.SQLITE_CANCEL_CHECK_INTERVAL,
                    )
                date_rows = pd.read_sql_query(
                    """
                    SELECT DISTINCT 日期
                    FROM daily_prices
                    WHERE REPLACE(REPLACE(日期, '-', ''), '/', '') <= ?
                    ORDER BY REPLACE(REPLACE(日期, '-', ''), '/', '') DESC
                    LIMIT ?
                    """,
                    conn,
                    params=(target_key, self.lookback_days),
                )
                if date_rows.empty:
                    _raise_if_cancelled(cancel_callback)
                    return pd.DataFrame()
                normalized_dates = [
                    str(item).replace("-", "").replace("/", "")
                    for item in date_rows["日期"].tolist()
                ]
                placeholders = ",".join("?" for _ in normalized_dates)
                frame = pd.read_sql_query(
                    f"""
                    SELECT 日期, 證券代號, 收盤價, 成交股數
                    FROM daily_prices
                    WHERE REPLACE(REPLACE(日期, '-', ''), '/', '') IN ({placeholders})
                    ORDER BY REPLACE(REPLACE(日期, '-', ''), '/', '') ASC, 證券代號 ASC
                    """,
                    conn,
                    params=tuple(normalized_dates),
                )
                _raise_if_cancelled(cancel_callback)
                return frame
        except sqlite3.OperationalError as exc:
            if was_sql_cancelled():
                raise BacktestCancelledError("相對強弱與流動性 SQL 查詢已取消。") from exc
            return pd.DataFrame()
        except (sqlite3.Error, pd.errors.DatabaseError) as exc:
            if was_sql_cancelled():
                raise BacktestCancelledError("相對強弱與流動性 SQL 查詢已取消。") from exc
            raise
