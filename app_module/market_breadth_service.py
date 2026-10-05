from __future__ import annotations

import numbers
import json
import sqlite3
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Protocol

import pandas as pd

from app_module.official_quote_exclusion_diagnostics import OfficialQuoteExclusionDiagnostics
from app_module.market_session_cadence import MarketSessionCadence
from app_module.decision_desk_dtos import DecisionDeskQuality, MarketBreadthSummary
from app_module.decision_market_frame import DecisionMarketFrameLoader
from app_module.dtos.market_loop_dtos import MarketBreadthDTO
from app_module.price_change_direction import (
    CHANGE_SIGN_COLUMNS,
    resolve_signed_change,
)


class MarketBreadthProvider(Protocol):
    def fetch(self, as_of_date: date) -> pd.DataFrame: ...


class MarketBreadthService:
    """Compute market breadth summary from injected DataFrame/provider."""

    def __init__(self, provider: MarketBreadthProvider | None = None, *, data: pd.DataFrame | None = None, cadence: MarketSessionCadence | None = None):
        if provider is None and data is None:
            raise ValueError("must provide provider or data")
        if provider is not None and data is not None:
            raise ValueError("provider and data cannot both be provided")

        self.provider = provider
        self.data = data
        self.cadence = cadence

    def build_snapshot(self, as_of_date: date) -> MarketBreadthSummary:
        try:
            if self.provider is not None:
                data = self.provider.fetch(as_of_date)
            else:
                data = self.data
        except Exception as exc:  # noqa: BLE001
            return MarketBreadthSummary(
                as_of_date=as_of_date,
                quality=DecisionDeskQuality.DEGRADED,
                warnings=(f"market_breadth_provider_error:{exc}",),
            )

        if data is None or data.empty:
            return MarketBreadthSummary(
                as_of_date=as_of_date,
                quality=DecisionDeskQuality.MISSING,
                warnings=("market_breadth_missing",),
            )

        row = self._find_row(data, as_of_date)
        if row is None:
            return MarketBreadthSummary(
                as_of_date=as_of_date,
                quality=DecisionDeskQuality.MISSING,
                warnings=("market_breadth_missing",),
            )

        row_dict = dict(zip(row.index, row.values))
        snapshot_date = self._parse_snapshot_date(row_dict, as_of_date)
        quality = self._parse_quality(row_dict)
        warnings = list(self._parse_warnings(row_dict))
        assessment = self.cadence.assess(as_of_date, snapshot_date) if self.cadence else None
        if assessment is not None and assessment.status == "future_rejected":
            return MarketBreadthSummary(snapshot_date, DecisionDeskQuality.MISSING, ("market_breadth_future_source_rejected",), meta={"cadence": assessment.metadata})
        if snapshot_date != as_of_date and not (assessment and assessment.current):
            fallback_warning = f"market_breadth_as_of_fallback:{snapshot_date.isoformat()}"
            if fallback_warning not in warnings:
                warnings.append(fallback_warning)
            if quality is DecisionDeskQuality.OBSERVED:
                quality = DecisionDeskQuality.DEGRADED
        if assessment is not None and not assessment.current:
            quality = DecisionDeskQuality.DEGRADED
            warnings.append(f"market_breadth_cadence:{assessment.status}")
        meta = self._parse_meta(row_dict)
        if assessment is not None:
            meta["cadence"] = assessment.metadata
        parsed = self._parse_counts(row_dict)
        if parsed is None:
            return MarketBreadthSummary(
                as_of_date=snapshot_date,
                quality=DecisionDeskQuality.DEGRADED,
                warnings=tuple(warnings) + ("market_breadth_invalid_counts",),
                advancing=None,
                declining=None,
                unchanged=None,
            )

        advancing, declining, unchanged = parsed
        breadth_ratio_bp = self._calc_breadth_ratio_bp(advancing, declining)
        return MarketBreadthSummary(
            as_of_date=snapshot_date,
            quality=quality,
            warnings=tuple(warnings),
            breadth_ratio_bp=breadth_ratio_bp,
            advancing=advancing,
            declining=declining,
            unchanged=unchanged,
            meta=meta,
        )

    def _find_row(self, data: pd.DataFrame, target_date: date) -> pd.Series | None:
        candidate_columns = ("as_of_date", "date", "trade_date", "timestamp", "time")
        for column in candidate_columns:
            if column not in data.columns:
                continue
            parsed_column = self._parse_date_series(data[column])
            if parsed_column is None:
                continue
            matched = parsed_column == target_date
            if not bool(matched.any()):
                continue
            return data.loc[matched].iloc[0]
        if len(data) == 1:
            row = data.iloc[0]
            row_dict = dict(zip(row.index, row.values))
            for column in candidate_columns:
                if column not in row_dict:
                    continue
                row_date = self._parse_date_value(row_dict[column])
                if row_date is not None and row_date <= target_date:
                    return row
        return None

    def build_snapshot_dto(self, as_of_date: date) -> MarketBreadthDTO:
        """建立含決策日與有效日的跨頁 DTO。"""

        summary = self.build_snapshot(as_of_date)
        return MarketBreadthDTO.from_summary(summary, decision_date=as_of_date)

    def _parse_date_series(self, values: pd.Series) -> pd.Series | None:
        parsed: list[date | None] = []
        for item in values:
            parsed.append(self._parse_date_value(item))
        if all(item is None for item in parsed):
            return None
        return pd.Series(parsed, index=values.index)

    def _parse_date_value(self, value: object) -> date | None:
        if isinstance(value, date) and not isinstance(value, datetime):
            return value
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, (int, float)):
            raw = str(int(value))
            if len(raw) == 8 and raw.isdigit():
                return self._parse_date_str(raw, "%Y%m%d")
            return None
        if isinstance(value, str):
            return (
                self._parse_date_str(value, "%Y-%m-%d")
                or self._parse_date_str(value, "%Y%m%d")
            )
        return None

    @staticmethod
    def _parse_date_str(raw: str, fmt: str) -> date | None:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            return None

    def _parse_counts(self, row: dict[str, object]) -> tuple[int, int, int | None] | None:
        advancing = self._read_int(row, ("advancing", "advancing_count", "adv"))
        declining = self._read_int(row, ("declining", "declining_count", "dec"))
        if advancing is None or declining is None:
            return None
        unchanged = self._read_int(row, ("unchanged", "unchanged_count"))
        return advancing, declining, unchanged

    def _read_int(self, row: dict[str, object], names: tuple[str, ...]) -> int | None:
        for name in names:
            if name not in row:
                continue
            raw = row[name]
            if raw is None:
                continue
            if isinstance(raw, bool):
                continue
            if isinstance(raw, numbers.Integral):
                return int(raw)
            if isinstance(raw, numbers.Real):
                try:
                    real_value = float(raw)
                except (TypeError, ValueError):
                    continue
                if not real_value.is_integer():
                    continue
                try:
                    return int(real_value)
                except (TypeError, ValueError, OverflowError):
                    continue
            if isinstance(raw, str) and raw.strip().isdigit():
                try:
                    return int(raw.strip())
                except ValueError:
                    continue
        return None

    def _calc_breadth_ratio_bp(self, advancing: int, declining: int) -> int:
        total = advancing + declining
        if total <= 0:
            return 0
        return (advancing * 10000) // total

    def _parse_snapshot_date(self, row: dict[str, object], default: date) -> date:
        for name in ("as_of_date", "date", "trade_date", "日期"):
            if name not in row:
                continue
            parsed = self._parse_date_value(row[name])
            if parsed is not None:
                return parsed
        return default

    @staticmethod
    def _parse_quality(row: dict[str, object]) -> DecisionDeskQuality:
        raw = row.get("quality")
        if raw is None:
            return DecisionDeskQuality.OBSERVED
        try:
            return DecisionDeskQuality(str(raw))
        except ValueError:
            return DecisionDeskQuality.DEGRADED

    @staticmethod
    def _parse_warnings(row: dict[str, object]) -> tuple[str, ...]:
        raw = row.get("warnings")
        if raw is None:
            return ()
        if isinstance(raw, str):
            if not raw.strip():
                return ()
            return tuple(item for item in raw.split("|") if item)
        if isinstance(raw, (tuple, list, set)):
            return tuple(str(item) for item in raw)
        return (str(raw),)

    @staticmethod
    def _parse_meta(row: dict[str, object]) -> dict[str, object]:
        excluded = {
            "as_of_date",
            "date",
            "trade_date",
            "timestamp",
            "time",
            "日期",
            "quality",
            "warnings",
            "advancing",
            "advancing_count",
            "adv",
            "declining",
            "declining_count",
            "dec",
            "unchanged",
            "unchanged_count",
        }
        meta: dict[str, object] = {}
        for key, value in row.items():
            if key == "exclusions_json":
                meta["exclusions"] = json.loads(str(value))
                continue
            if key in excluded or pd.isna(value):
                continue
            if isinstance(value, numbers.Integral):
                meta[key] = int(value)
            elif isinstance(value, numbers.Real):
                real_value = float(value)
                meta[key] = int(real_value) if real_value.is_integer() else real_value
            else:
                meta[key] = value
        return meta


class SQLiteDailyPriceMarketBreadthProvider:
    """Read-only provider that derives market breadth from SQLite daily_prices."""

    def __init__(
        self,
        db_path: str | Path,
        *,
        lookback_days: int = 60,
        market_frame_loader: DecisionMarketFrameLoader | None = None,
        quote_diagnostics: OfficialQuoteExclusionDiagnostics | None = None,
    ):
        self.db_path = Path(db_path)
        self.lookback_days = lookback_days
        self.market_frame_loader = market_frame_loader
        self.quote_diagnostics = quote_diagnostics

    def fetch(self, as_of_date: date) -> pd.DataFrame:
        if not self.db_path.exists():
            return pd.DataFrame()

        target_key = as_of_date.strftime("%Y%m%d")
        if self.market_frame_loader is not None:
            prices = self.market_frame_loader.load(as_of_date, self.lookback_days + 1)
            if prices.empty:
                return pd.DataFrame()
            normalized_keys = [
                self._normalize_date_key(value)
                for value in prices["日期"].tolist()
            ]
            available_keys: list[str] = [
                str(key)
                for key in normalized_keys
                if key is not None and key <= target_key
            ]
            if not available_keys:
                return pd.DataFrame()
            return self._build_breadth_frame(prices, max(available_keys), target_key)

        db_uri = f"{self.db_path.resolve().as_uri()}?mode=ro"
        with sqlite3.connect(db_uri, uri=True) as conn:
            conn.execute("PRAGMA query_only=ON")
            date_rows = pd.read_sql_query(
                """
                SELECT DISTINCT 日期
                FROM daily_prices
                WHERE REPLACE(REPLACE(日期, '-', ''), '/', '') <= ?
                ORDER BY REPLACE(REPLACE(日期, '-', ''), '/', '') DESC
                LIMIT ?
                """,
                conn,
                params=(target_key, self.lookback_days + 1),
            )
            if date_rows.empty:
                return pd.DataFrame()

            normalized_dates = [
                str(item).replace("-", "").replace("/", "")
                for item in date_rows["日期"].tolist()
            ]
            actual_key = normalized_dates[0]
            placeholders = ",".join("?" for _ in normalized_dates)
            table_columns = {
                str(row[1])
                for row in conn.execute('PRAGMA table_info("daily_prices")')
            }
            sign_projection = ", ".join(
                f'"{name}"' if name in table_columns else f'NULL AS "{name}"'
                for name in CHANGE_SIGN_COLUMNS
            )
            prices = pd.read_sql_query(
                f"""
                SELECT 日期, 證券代號, 收盤價, 漲跌價差, 成交股數, {sign_projection}
                FROM daily_prices
                WHERE REPLACE(REPLACE(日期, '-', ''), '/', '') IN ({placeholders})
                """,
                conn,
                params=tuple(normalized_dates),
            )

        if prices.empty:
            return pd.DataFrame()

        return self._build_breadth_frame(prices, actual_key, target_key)

    def _build_breadth_frame(self, prices: pd.DataFrame, actual_key: str, target_key: str) -> pd.DataFrame:
        data = prices.copy()
        data["_date_key"] = data["日期"].map(self._normalize_date_key)
        data["_close"] = data["收盤價"].map(self._to_decimal)
        data["_volume"] = data["成交股數"].map(self._to_decimal)

        current = data.loc[data["_date_key"] == actual_key].copy()
        current = current.dropna(subset=["證券代號", "_close"])
        if current.empty:
            return pd.DataFrame()

        previous_key = self._previous_date_key(data, actual_key)
        previous = data.loc[data["_date_key"] == previous_key].copy() if previous_key else pd.DataFrame()

        advancing = 0
        declining = 0
        unchanged = 0
        limit_up = 0
        limit_down = 0
        skipped = 0
        exclusions: list[dict[str, object]] = []
        corporate_action_exclusions = 0

        for _, row in current.iterrows():
            close_value = row["_close"]
            change, _ = resolve_signed_change(
                row.get("漲跌價差"),
                tuple(row.get(name) for name in CHANGE_SIGN_COLUMNS),
            )
            if change is None:
                # 價差與方向都未知時，不得以收盤價差猜測當日方向。
                skipped += 1
                official = self.quote_diagnostics.corporate_action(str(row.get("證券代號")), actual_key,
                    datetime.strptime(target_key, "%Y%m%d").date(), close_value, row.get("_volume")) if self.quote_diagnostics else None
                if official:
                    corporate_action_exclusions += 1
                exclusions.append({"stock_code": str(row.get("證券代號")), "date": actual_key,
                    "reason": "change_direction_unavailable", "raw_change": str(row.get("漲跌價差")),
                    "raw_signs": {name: str(row.get(name)) for name in CHANGE_SIGN_COLUMNS}, "source": "sqlite_daily_prices", **(official or {})})
                continue
            previous_close = close_value - change

            if change > 0:
                advancing += 1
            elif change < 0:
                declining += 1
            else:
                unchanged += 1

            if previous_close and previous_close > 0:
                change_ratio = change / previous_close
                if change_ratio >= Decimal("0.095"):
                    limit_up += 1
                elif change_ratio <= Decimal("-0.095"):
                    limit_down += 1

        warnings: list[str] = []
        quality = DecisionDeskQuality.OBSERVED
        actual_date = self._parse_date_key(actual_key)
        unknown_skipped = skipped - corporate_action_exclusions
        if unknown_skipped:
            quality = DecisionDeskQuality.DEGRADED
            warnings.append(f"market_breadth_skipped_rows:{unknown_skipped}")
        if corporate_action_exclusions:
            warnings.append(f"market_breadth_source_declared_corporate_action_exclusions:{corporate_action_exclusions}")

        row = {
            "as_of_date": actual_date.isoformat() if actual_date is not None else actual_key,
            "quality": quality.value,
            "warnings": "|".join(warnings),
            "advancing": advancing,
            "declining": declining,
            "unchanged": unchanged,
            "source": "sqlite_daily_prices",
            "stock_count": int(len(current)),
            "classified_stock_count": advancing + declining + unchanged,
            "corporate_action_exclusions_count": corporate_action_exclusions,
            "unknown_skipped_rows_count": unknown_skipped,
            "exclusions_json": json.dumps(exclusions, ensure_ascii=False),
            "limit_up_count": limit_up,
            "limit_down_count": limit_down,
            "volume_expansion_bp": self._volume_expansion_bp(current, previous),
            "new_high_20_count": self._new_extreme_count(data, current, actual_key, 20, "high"),
            "new_low_20_count": self._new_extreme_count(data, current, actual_key, 20, "low"),
            "new_high_60_count": self._new_extreme_count(data, current, actual_key, 60, "high"),
            "new_low_60_count": self._new_extreme_count(data, current, actual_key, 60, "low"),
        }
        return pd.DataFrame([row])

    @staticmethod
    def _normalize_date_key(value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip().replace("-", "").replace("/", "")
        return text if len(text) == 8 and text.isdigit() else None

    @staticmethod
    def _parse_date_key(value: str) -> date | None:
        try:
            return datetime.strptime(value, "%Y%m%d").date()
        except ValueError:
            return None

    @staticmethod
    def _to_decimal(value: object) -> Decimal | None:
        if value is None or isinstance(value, bool) or pd.isna(value):
            return None
        try:
            return Decimal(str(value).replace(",", ""))
        except (InvalidOperation, ValueError, TypeError):
            return None

    @staticmethod
    def _previous_date_key(data: pd.DataFrame, actual_key: str) -> str | None:
        keys = sorted(key for key in data["_date_key"].dropna().unique() if key < actual_key)
        return keys[-1] if keys else None

    @staticmethod
    def _volume_expansion_bp(current: pd.DataFrame, previous: pd.DataFrame) -> int | None:
        if current.empty or previous.empty or "_volume" not in current.columns or "_volume" not in previous.columns:
            return None
        current_volume = sum((item for item in current["_volume"] if item is not None), Decimal("0"))
        previous_volume = sum((item for item in previous["_volume"] if item is not None), Decimal("0"))
        if previous_volume <= 0:
            return None
        return int(((current_volume / previous_volume) * Decimal("10000")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    @staticmethod
    def _new_extreme_count(
        data: pd.DataFrame,
        current: pd.DataFrame,
        actual_key: str,
        window: int,
        direction: str,
    ) -> int | None:
        keys = sorted(key for key in data["_date_key"].dropna().unique() if key <= actual_key)
        window_keys = keys[-window:]
        if len(window_keys) < window:
            return None
        history = data.loc[data["_date_key"].isin(window_keys)].dropna(subset=["證券代號", "_close"])
        if history.empty:
            return None

        # Aggregate once by security instead of rescanning every history row
        # for every current security.  Keep Decimal comparisons and equality so
        # the existing tie-inclusive high/low definition is unchanged.
        extreme_by_stock: dict[object, Decimal] = {}
        is_high = direction == "high"
        for stock_code, close_value in history[["證券代號", "_close"]].itertuples(
            index=False, name=None
        ):
            existing = extreme_by_stock.get(stock_code)
            if existing is None or (
                close_value > existing if is_high else close_value < existing
            ):
                extreme_by_stock[stock_code] = close_value

        count = 0
        for stock_code, current_close in current[["證券代號", "_close"]].itertuples(
            index=False, name=None
        ):
            if current_close is None:
                continue
            extreme = extreme_by_stock.get(stock_code)
            if extreme is not None and current_close == extreme:
                count += 1
        return count
