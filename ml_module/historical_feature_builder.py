"""Shared canonical feature loading boundary for training and inference."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal, ROUND_HALF_EVEN, localcontext
import hashlib
import json
from collections import defaultdict
from typing import Any, Mapping, Sequence

from data_module.ml_historical_snapshot_provider import (
    HistoricalIndexObservation,
    HistoricalPriceObservation,
    HistoricalRawSnapshot,
    HistoricalTechnicalObservation,
)
from data_module.ml_price_availability_contract import (
    build_price_unavailable_research_contract,
    validate_price_unavailable_research_contract,
)
from ml_module.feature_registry import (
    CORE_LONG_HISTORY_FEATURE_REGISTRY,
    FeatureRegistry,
)
from ml_module.historical_contracts import HistoricalFeatureRow


FeatureSchema = tuple[tuple[str, str, str], ...]

CURRENT_RESTATED_CORE19_FEATURE_IDS = tuple(
    feature_id
    for feature_id in CORE_LONG_HISTORY_FEATURE_REGISTRY.canonical_ids
    if feature_id != "industry_relative_return_20d_bp"
)


@dataclass(frozen=True, slots=True)
class CurrentRestatedCore19Projection:
    """不含 PIT availability 的 CORE19 純數值投影結果。"""

    symbol: str
    event_date: str
    feature_ids: tuple[str, ...]
    values: tuple[int | None, ...]
    missing_feature_ids: tuple[str, ...]
    quality_blocked_feature_ids: tuple[str, ...] = ()
    staleness_blocked_feature_ids: tuple[str, ...] = ()
    excluded_feature_ids: tuple[str, ...] = ("industry_relative_return_20d_bp",)
    excluded_reason: str = "verified_symbol_industry_membership_unavailable"

    def __post_init__(self) -> None:
        if not self.symbol or self.symbol != self.symbol.strip():
            raise ValueError("current-restated projection symbol is invalid")
        parsed = date.fromisoformat(self.event_date)
        if parsed.isoformat() != self.event_date:
            raise ValueError("current-restated projection event date must be ISO")
        if self.feature_ids != CURRENT_RESTATED_CORE19_FEATURE_IDS:
            raise ValueError("current-restated projection feature IDs differ from CORE19")
        if len(self.values) != len(self.feature_ids):
            raise ValueError("current-restated projection values differ from CORE19 width")
        if any(value is not None and (isinstance(value, bool) or not isinstance(value, int)) for value in self.values):
            raise TypeError("current-restated projection values must be integer units or missing")
        expected_missing = tuple(
            feature_id
            for feature_id, value in zip(self.feature_ids, self.values)
            if value is None
        )
        if self.missing_feature_ids != expected_missing:
            raise ValueError("current-restated projection missing mask differs from values")
        for label, feature_ids in (
            ("quality", self.quality_blocked_feature_ids),
            ("staleness", self.staleness_blocked_feature_ids),
        ):
            if len(feature_ids) != len(set(feature_ids)) or not set(feature_ids).issubset(
                self.feature_ids
            ):
                raise ValueError(f"current-restated {label} mask is outside CORE19")
        if self.excluded_feature_ids != ("industry_relative_return_20d_bp",):
            raise ValueError("CORE19 must explicitly exclude the unverified industry feature")
        if not self.excluded_reason:
            raise ValueError("excluded industry feature requires a reason")


@dataclass(frozen=True)
class HistoricalFeatureBuilderLoadContract:
    registry_id: str
    registry_hash: str
    canonical_schema: FeatureSchema
    schema_hash: str
    decision_timing: str
    missing_policy: str
    contract_hash: str
    shadow_only: bool = True
    production_action_allowed: bool = False

    @classmethod
    def from_registry(
        cls, registry: FeatureRegistry
    ) -> "HistoricalFeatureBuilderLoadContract":
        schema_hash = _hash_payload(
            {
                "registry_hash": registry.registry_hash,
                "canonical_schema": [list(item) for item in registry.canonical_schema],
            }
        )
        payload = {
            "registry_id": registry.registry_id,
            "registry_hash": registry.registry_hash,
            "canonical_schema": [list(item) for item in registry.canonical_schema],
            "schema_hash": schema_hash,
            "decision_timing": "decision_t_uses_previous_trading_day",
            "missing_policy": "missing_is_not_zero",
            "shadow_only": True,
            "production_action_allowed": False,
        }
        return cls(
            registry_id=registry.registry_id,
            registry_hash=registry.registry_hash,
            canonical_schema=registry.canonical_schema,
            schema_hash=schema_hash,
            decision_timing="decision_t_uses_previous_trading_day",
            missing_policy="missing_is_not_zero",
            contract_hash=_hash_payload(payload),
        )

    @property
    def canonical_ids(self) -> tuple[str, ...]:
        return tuple(item[0] for item in self.canonical_schema)

    @property
    def canonical_dtypes(self) -> tuple[str, ...]:
        return tuple(item[1] for item in self.canonical_schema)

    @property
    def canonical_units(self) -> tuple[str, ...]:
        return tuple(item[2] for item in self.canonical_schema)

    def validate(
        self,
        *,
        expected_registry_hash: str,
        expected_canonical_schema: FeatureSchema,
        expected_schema_hash: str,
    ) -> None:
        if not self.shadow_only or self.production_action_allowed:
            raise ValueError("feature builder contract must remain shadow-only")
        if expected_registry_hash != self.registry_hash:
            raise ValueError("feature registry hash mismatch")
        if expected_canonical_schema != self.canonical_schema:
            raise ValueError("feature schema mismatch")
        if expected_schema_hash != self.schema_hash:
            raise ValueError("feature schema hash mismatch")


@dataclass(frozen=True)
class HistoricalFeatureVector:
    symbol: str
    decision_date: str
    feature_as_of_date: str
    available_date: str
    registry_hash: str
    schema_hash: str
    feature_ids: tuple[str, ...]
    feature_dtypes: tuple[str, ...]
    feature_units: tuple[str, ...]
    values: tuple[int | None, ...]
    missing_feature_ids: tuple[str, ...]
    snapshot_hash: str
    shadow_only: bool = True


class HistoricalFeatureBuilder:
    """Canonicalizes causal feature rows without fitting or imputing values."""

    def __init__(
        self, registry: FeatureRegistry = CORE_LONG_HISTORY_FEATURE_REGISTRY
    ) -> None:
        self._registry = registry
        self.load_contract = HistoricalFeatureBuilderLoadContract.from_registry(registry)

    def load(self, row: HistoricalFeatureRow) -> HistoricalFeatureVector:
        by_id = dict(row.values)
        expected_ids = self.load_contract.canonical_ids
        if set(by_id) != set(expected_ids):
            missing = tuple(sorted(set(expected_ids) - set(by_id)))
            extra = tuple(sorted(set(by_id) - set(expected_ids)))
            raise ValueError(
                f"feature id set mismatch: missing={missing}, extra={extra}"
            )
        values = tuple(by_id[feature_id] for feature_id in expected_ids)
        missing_ids = tuple(
            feature_id
            for feature_id, value in zip(expected_ids, values)
            if value is None
        )
        payload = {
            "symbol": row.symbol,
            "decision_date": row.decision_date,
            "feature_as_of_date": row.feature_as_of_date,
            "available_date": row.available_date,
            "registry_hash": self.load_contract.registry_hash,
            "schema_hash": self.load_contract.schema_hash,
            "feature_ids": list(expected_ids),
            "values": list(values),
        }
        return HistoricalFeatureVector(
            symbol=row.symbol,
            decision_date=row.decision_date,
            feature_as_of_date=row.feature_as_of_date,
            available_date=row.available_date,
            registry_hash=self.load_contract.registry_hash,
            schema_hash=self.load_contract.schema_hash,
            feature_ids=expected_ids,
            feature_dtypes=self.load_contract.canonical_dtypes,
            feature_units=self.load_contract.canonical_units,
            values=values,
            missing_feature_ids=missing_ids,
            snapshot_hash=_hash_payload(payload),
        )

    def load_many(
        self, rows: tuple[HistoricalFeatureRow, ...]
    ) -> tuple[HistoricalFeatureVector, ...]:
        return tuple(self.load(row) for row in rows)

    def compute(
        self,
        snapshot: HistoricalRawSnapshot,
        *,
        industry_index_name_by_symbol: Mapping[str, str],
        price_unavailable_contracts: Sequence[Mapping[str, Any]] = (),
    ) -> tuple[HistoricalFeatureRow, ...]:
        """Compute prefix-invariant integer features using only snapshot T-1 rows."""
        cutoff = snapshot.feature_as_of_date
        explicit_gap_dates, feature_context_dates = (
            _validated_feature_contract_scope(price_unavailable_contracts)
        )
        price_by_symbol: dict[str, list[HistoricalPriceObservation]] = defaultdict(list)
        for price_observation in snapshot.prices:
            if price_observation.trading_date <= cutoff:
                price_by_symbol[price_observation.symbol].append(price_observation)
        technical_by_symbol: dict[str, list[HistoricalTechnicalObservation]] = defaultdict(list)
        for technical_observation in snapshot.technicals:
            if technical_observation.trading_date <= cutoff:
                technical_by_symbol[technical_observation.symbol].append(technical_observation)
        market_dates, market_by_date = _index_by_date(
            snapshot.market, cutoff=cutoff, index_name="market"
        )
        observed_price_dates = {
            observation.trading_date
            for symbol_rows in price_by_symbol.values()
            for observation in symbol_rows
        }
        # Keep the requested cutoff and every observed source date in the
        # assembly timeline.  A market row can be missing at the cutoff (or
        # in the middle) while a stock row is present.  Appending the cutoff
        # as an empty market slot prevents silently re-labelling the prior
        # market date as feature_as_of_date; unioning price dates prevents a
        # missing market session from being compressed out of index windows.
        timeline_dates = tuple(
            sorted(set(market_dates) | observed_price_dates | {cutoff})
        )
        market_values = [market_by_date.get(trading_date) for trading_date in timeline_dates]
        industry_names = {row.index_name for row in snapshot.industries}
        industries = {
            name: {
                trading_date: close
                for trading_date, close in _index_by_date(
                    snapshot.industries,
                    cutoff=cutoff,
                    index_name=name,
                )[1].items()
            }
            for name in industry_names
        }
        market_5 = _return_bp(market_values, 5)
        market_20 = _return_bp(market_values, 20)
        market_60 = _return_bp(market_values, 60)
        observed_dates_by_symbol = {
            symbol: {observation.trading_date for observation in observations}
            for symbol, observations in price_by_symbol.items()
        }
        for symbol, context_dates in feature_context_dates.items():
            required_dates = {
                date_iso for date_iso in context_dates if date_iso <= cutoff
            }
            missing_context_dates = sorted(
                required_dates - observed_dates_by_symbol.get(symbol, set())
            )
            if missing_context_dates:
                raise ValueError(
                    "price availability feature context is incomplete for "
                    f"{symbol}: {','.join(missing_context_dates)}"
                )

        rows: list[HistoricalFeatureRow] = []
        for symbol in sorted(price_by_symbol):
            observations = sorted(price_by_symbol[symbol], key=lambda row: row.trading_date)
            explicit_dates = {
                date_iso
                for date_iso in explicit_gap_dates.get(symbol, set())
                if date_iso <= cutoff
            }
            # Build the same research contract used by source-quality audit for
            # every incomplete OHLC row.  A missing middle row becomes an
            # explicit gap for all price windows; surrounding observations are
            # never silently bridged into a synthetic adjacent sequence.  The
            # explicit contract's feature_window_dates are context evidence,
            # not additional missing rows; only its source anchor is masked.
            price_unavailable_dates = set(explicit_dates)
            for observation in observations:
                if not any(
                    value is None
                    for value in (
                        observation.open_price,
                        observation.high_price,
                        observation.low_price,
                        observation.close_price,
                    )
                ):
                    continue
                contract = build_price_unavailable_research_contract(
                    symbol=symbol,
                    date_iso=observation.trading_date,
                    raw_row={
                        "symbol": observation.symbol,
                        "open": observation.open_price,
                        "high": observation.high_price,
                        "low": observation.low_price,
                        "close": observation.close_price,
                        "volume": observation.volume,
                    },
                )
                price_unavailable_dates.add(str(contract["date"]))
            effective_by_date = {
                observation.trading_date: (
                    replace(
                        observation,
                        open_price=None,
                        high_price=None,
                        low_price=None,
                        close_price=None,
                        volume=None,
                        turnover_amount_minor=None,
                    )
                    if observation.trading_date in price_unavailable_dates
                    else observation
                )
                for observation in observations
            }
            # Assemble every stock feature on the observed market-date path.
            # A missing stock row becomes an explicit empty slot; it is never
            # compressed away by the trailing-window helpers.  The source
            # calendar remains observational only, so this protects joins
            # without claiming an official complete session horizon.
            symbol_timeline_dates = tuple(
                sorted(
                    set(timeline_dates)
                    | {observation.trading_date for observation in observations}
                )
            )
            effective_observations = [
                effective_by_date.get(
                    trading_date,
                    _missing_price_observation(symbol, trading_date),
                )
                for trading_date in symbol_timeline_dates
            ]
            closes = [row.close_price for row in effective_observations]
            volumes = [row.volume for row in effective_observations]
            latest = (
                effective_observations[-1]
                if effective_observations
                else _missing_price_observation(symbol, cutoff)
            )
            latest_close = latest.close_price
            technical_by_date = {
                row.trading_date: row for row in technical_by_symbol[symbol]
            }
            technical = technical_by_date.get(cutoff)
            stock_20 = _return_bp(closes, 20)
            industry_name = industry_index_name_by_symbol.get(symbol)
            industry_by_date = (
                industries.get(industry_name, {})
                if industry_name is not None
                else {}
            )
            industry_values = [
                industry_by_date.get(trading_date)
                for trading_date in timeline_dates
            ]
            industry_20 = _return_bp(
                industry_values,
                20,
            )
            values = {
                "stock_return_1d_bp": _return_bp(closes, 1),
                "stock_return_5d_bp": _return_bp(closes, 5),
                "stock_return_20d_bp": stock_20,
                "stock_return_60d_bp": _return_bp(closes, 60),
                "trailing_volatility_20d_bp": _volatility_bp(closes, 20),
                "high_low_range_20d_bp": _range_bp(effective_observations, 20),
                "close_to_ma_5d_bp": _close_to_average_bp(closes, 5),
                "close_to_ma_20d_bp": _close_to_average_bp(closes, 20),
                "close_to_ma_60d_bp": _close_to_average_bp(closes, 60),
                "rsi_normalized_bp": _rsi_bp(technical.rsi if technical else None),
                "adx_normalized_bp": _scaled_bp(technical.adx if technical else None),
                "macd_normalized_bp": _ratio_bp(
                    technical.macd if technical else None, latest_close
                ),
                "volume_ratio_5d_bp": _recent_ratio_bp(volumes, 5),
                "volume_ratio_20d_bp": _recent_ratio_bp(volumes, 20),
                "turnover_amount_minor": latest.turnover_amount_minor,
                "market_return_5d_bp": market_5,
                "market_return_20d_bp": market_20,
                "market_return_60d_bp": market_60,
                "stock_minus_market_20d_bp": _difference(stock_20, market_20),
                "industry_relative_return_20d_bp": _difference(stock_20, industry_20),
            }
            rows.append(HistoricalFeatureRow(
                symbol=symbol,
                decision_date=snapshot.decision_date,
                feature_as_of_date=cutoff,
                available_date=snapshot.decision_date,
                values=tuple((feature_id, values[feature_id]) for feature_id in self.load_contract.canonical_ids),
            ))
        return tuple(rows)


def compute_current_restated_core19_projection(
    *,
    symbol: str,
    event_date: str,
    prices: Sequence[HistoricalPriceObservation],
    technicals: Sequence[HistoricalTechnicalObservation],
    market: Sequence[HistoricalIndexObservation],
    unavailable_price_dates: Sequence[str] = (),
    unavailable_technical_dates: Sequence[str] = (),
    unavailable_market_dates: Sequence[str] = (),
    quality_blocked_price_dates: Sequence[str] = (),
    stale_price_dates: Sequence[str] = (),
    quality_blocked_technical_dates: Sequence[str] = (),
    stale_technical_dates: Sequence[str] = (),
    quality_blocked_market_dates: Sequence[str] = (),
    stale_market_dates: Sequence[str] = (),
) -> CurrentRestatedCore19Projection:
    """以既有 Decimal 公式投影 CORE19，不建立任何歷史/PIT row。

    ``event_date`` 是 raw observation 的參考日，不代表決策日或 availability。
    呼叫端需從已驗證來源傳入觀測值與遮罩日期；此函式只回傳 scaled integer
    feature values，沒有 available_date、decision_date 或 provider evidence。
    """

    if not isinstance(symbol, str) or not symbol or symbol != symbol.strip():
        raise ValueError("current-restated projection symbol is invalid")
    cutoff = _strict_iso_date(event_date, "event_date")
    unavailable_prices = _strict_date_set(unavailable_price_dates, cutoff, "price")
    unavailable_technicals = _strict_date_set(
        unavailable_technical_dates, cutoff, "technical"
    )
    unavailable_market = _strict_date_set(unavailable_market_dates, cutoff, "market")
    quality_price = _strict_date_set(quality_blocked_price_dates, cutoff, "quality price")
    stale_price = _strict_date_set(stale_price_dates, cutoff, "stale price")
    quality_technical = _strict_date_set(
        quality_blocked_technical_dates, cutoff, "quality technical"
    )
    stale_technical = _strict_date_set(
        stale_technical_dates, cutoff, "stale technical"
    )
    quality_market = _strict_date_set(
        quality_blocked_market_dates, cutoff, "quality market"
    )
    stale_market = _strict_date_set(stale_market_dates, cutoff, "stale market")

    price_by_date: dict[str, HistoricalPriceObservation] = {}
    for price_observation in prices:
        if type(price_observation) is not HistoricalPriceObservation:
            raise TypeError("current-restated prices must be typed price observations")
        if price_observation.symbol != symbol:
            raise ValueError("current-restated price symbol differs from projection symbol")
        _strict_iso_date(price_observation.trading_date, "price.trading_date")
        if price_observation.trading_date > event_date:
            continue
        if price_observation.trading_date in price_by_date:
            raise ValueError("current-restated prices repeat a symbol/date")
        _validate_price_observation(price_observation)
        price_by_date[price_observation.trading_date] = price_observation

    technical_by_date: dict[str, HistoricalTechnicalObservation] = {}
    for technical_observation in technicals:
        if type(technical_observation) is not HistoricalTechnicalObservation:
            raise TypeError("current-restated technicals must be typed observations")
        if technical_observation.symbol != symbol:
            raise ValueError("current-restated technical symbol differs from projection symbol")
        _strict_iso_date(technical_observation.trading_date, "technical.trading_date")
        if technical_observation.trading_date > event_date:
            continue
        if technical_observation.trading_date in technical_by_date:
            raise ValueError("current-restated technicals repeat a symbol/date")
        _validate_optional_decimal_observation(
            (technical_observation.rsi, technical_observation.macd, technical_observation.adx),
            "technical value",
        )
        technical_by_date[technical_observation.trading_date] = technical_observation

    market_by_date: dict[str, Decimal | None] = {}
    for market_observation in market:
        if type(market_observation) is not HistoricalIndexObservation:
            raise TypeError("current-restated market must be typed index observations")
        if market_observation.index_name != "market":
            raise ValueError("current-restated market index name must be canonical 'market'")
        _strict_iso_date(market_observation.trading_date, "market.trading_date")
        if market_observation.trading_date > event_date:
            continue
        if market_observation.trading_date in market_by_date:
            raise ValueError("current-restated market repeats a date")
        _validate_optional_decimal_observation((market_observation.close_value,), "market value")
        market_by_date[market_observation.trading_date] = market_observation.close_value

    timeline_dates = tuple(
        sorted(set(market_by_date) | set(price_by_date) | {event_date})
    )
    effective_prices: list[HistoricalPriceObservation] = []
    for trading_date in timeline_dates:
        source_row = price_by_date.get(trading_date)
        if source_row is None:
            effective_prices.append(_missing_price_observation(symbol, trading_date))
            continue
        incomplete_ohlc = any(
            value is None
            for value in (
                source_row.open_price,
                source_row.high_price,
                source_row.low_price,
                source_row.close_price,
            )
        )
        if (
            incomplete_ohlc
            or trading_date in unavailable_prices
            or trading_date in quality_price
            or trading_date in stale_price
        ):
            effective_prices.append(
                replace(
                    source_row,
                    open_price=None,
                    high_price=None,
                    low_price=None,
                    close_price=None,
                    volume=None,
                    turnover_amount_minor=None,
                )
            )
        else:
            effective_prices.append(source_row)

    closes = [row.close_price for row in effective_prices]
    volumes = [row.volume for row in effective_prices]
    latest = effective_prices[-1]
    technical = technical_by_date.get(event_date)
    if (
        event_date in unavailable_technicals
        or event_date in quality_technical
        or event_date in stale_technical
    ):
        technical = None
    market_values = [
        None
        if trading_date in unavailable_market
        or trading_date in quality_market
        or trading_date in stale_market
        else market_by_date.get(trading_date)
        for trading_date in timeline_dates
    ]
    stock_20 = _return_bp(closes, 20)
    market_5 = _return_bp(market_values, 5)
    market_20 = _return_bp(market_values, 20)
    market_60 = _return_bp(market_values, 60)
    values_by_id = {
        "stock_return_1d_bp": _return_bp(closes, 1),
        "stock_return_5d_bp": _return_bp(closes, 5),
        "stock_return_20d_bp": stock_20,
        "stock_return_60d_bp": _return_bp(closes, 60),
        "trailing_volatility_20d_bp": _volatility_bp(closes, 20),
        "high_low_range_20d_bp": _range_bp(effective_prices, 20),
        "close_to_ma_5d_bp": _close_to_average_bp(closes, 5),
        "close_to_ma_20d_bp": _close_to_average_bp(closes, 20),
        "close_to_ma_60d_bp": _close_to_average_bp(closes, 60),
        "rsi_normalized_bp": _rsi_bp(technical.rsi if technical else None),
        "adx_normalized_bp": _scaled_bp(technical.adx if technical else None),
        "macd_normalized_bp": _ratio_bp(
            technical.macd if technical else None, latest.close_price
        ),
        "volume_ratio_5d_bp": _recent_ratio_bp(volumes, 5),
        "volume_ratio_20d_bp": _recent_ratio_bp(volumes, 20),
        "turnover_amount_minor": latest.turnover_amount_minor,
        "market_return_5d_bp": market_5,
        "market_return_20d_bp": market_20,
        "market_return_60d_bp": market_60,
        "stock_minus_market_20d_bp": _difference(stock_20, market_20),
    }
    if tuple(values_by_id) != CURRENT_RESTATED_CORE19_FEATURE_IDS:
        raise RuntimeError("current-restated CORE19 projection order differs from registry")
    values = tuple(values_by_id[feature_id] for feature_id in CURRENT_RESTATED_CORE19_FEATURE_IDS)
    missing = tuple(
        feature_id
        for feature_id, value in zip(CURRENT_RESTATED_CORE19_FEATURE_IDS, values)
        if value is None
    )
    close_dates = {
        feature_id: tuple(timeline_dates[-periods - 1 :])
        for feature_id, periods in (
            ("stock_return_1d_bp", 1),
            ("stock_return_5d_bp", 5),
            ("stock_return_20d_bp", 20),
            ("stock_return_60d_bp", 60),
            ("trailing_volatility_20d_bp", 20),
        )
    }
    close_dates.update(
        {
            feature_id: tuple(timeline_dates[-periods:])
            for feature_id, periods in (
                ("close_to_ma_5d_bp", 5),
                ("close_to_ma_20d_bp", 20),
                ("close_to_ma_60d_bp", 60),
                ("volume_ratio_5d_bp", 5),
                ("volume_ratio_20d_bp", 20),
                ("high_low_range_20d_bp", 20),
            )
        }
    )
    close_dates["turnover_amount_minor"] = (timeline_dates[-1],)
    close_dates["rsi_normalized_bp"] = (event_date,)
    close_dates["adx_normalized_bp"] = (event_date,)
    close_dates["macd_normalized_bp"] = (event_date, timeline_dates[-1])
    for period, feature_id in (
        (5, "market_return_5d_bp"),
        (20, "market_return_20d_bp"),
        (60, "market_return_60d_bp"),
    ):
        close_dates[feature_id] = tuple(timeline_dates[-period - 1 :])
    close_dates["stock_minus_market_20d_bp"] = tuple(timeline_dates[-21:])

    def _depends_on(dates: Sequence[str], blocked_dates: frozenset[str]) -> bool:
        return bool(set(dates).intersection(blocked_dates))

    quality_blocked_ids: list[str] = []
    staleness_blocked_ids: list[str] = []
    for feature_id, value in zip(CURRENT_RESTATED_CORE19_FEATURE_IDS, values):
        if value is not None:
            continue
        dates = close_dates[feature_id]
        price_dependent = feature_id not in {
            "market_return_5d_bp",
            "market_return_20d_bp",
            "market_return_60d_bp",
        }
        market_dependent = feature_id.startswith("market_return_") or feature_id == "stock_minus_market_20d_bp"
        technical_dependent = feature_id in {
            "rsi_normalized_bp",
            "adx_normalized_bp",
            "macd_normalized_bp",
        }
        if price_dependent and _depends_on(dates, quality_price):
            quality_blocked_ids.append(feature_id)
        if market_dependent and _depends_on(dates, quality_market):
            quality_blocked_ids.append(feature_id)
        if technical_dependent and event_date in quality_technical:
            quality_blocked_ids.append(feature_id)
        if price_dependent and _depends_on(dates, stale_price):
            staleness_blocked_ids.append(feature_id)
        if market_dependent and _depends_on(dates, stale_market):
            staleness_blocked_ids.append(feature_id)
        if technical_dependent and event_date in stale_technical:
            staleness_blocked_ids.append(feature_id)
    return CurrentRestatedCore19Projection(
        symbol=symbol,
        event_date=event_date,
        feature_ids=CURRENT_RESTATED_CORE19_FEATURE_IDS,
        values=values,
        missing_feature_ids=missing,
        quality_blocked_feature_ids=tuple(
            feature_id for feature_id in CURRENT_RESTATED_CORE19_FEATURE_IDS
            if feature_id in set(quality_blocked_ids)
        ),
        staleness_blocked_feature_ids=tuple(
            feature_id for feature_id in CURRENT_RESTATED_CORE19_FEATURE_IDS
            if feature_id in set(staleness_blocked_ids)
        ),
    )


def _strict_iso_date(value: str, field: str) -> date:
    if not isinstance(value, str):
        raise TypeError(f"{field} must be canonical ISO date text")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field} must be canonical ISO date text") from exc
    if parsed.isoformat() != value:
        raise ValueError(f"{field} must be canonical ISO date text")
    return parsed


def _strict_date_set(
    values: Sequence[str], cutoff: date, field: str
) -> frozenset[str]:
    result: set[str] = set()
    for value in values:
        parsed = _strict_iso_date(value, f"{field} unavailable date")
        if parsed <= cutoff:
            result.add(value)
    return frozenset(result)


def _validate_optional_decimal_observation(
    values: Sequence[Decimal | None], field: str
) -> None:
    for value in values:
        if value is not None and (not isinstance(value, Decimal) or not value.is_finite()):
            raise TypeError(f"{field} must be a finite Decimal or None")


def _validate_price_observation(observation: HistoricalPriceObservation) -> None:
    _validate_optional_decimal_observation(
        (
            observation.open_price,
            observation.high_price,
            observation.low_price,
            observation.close_price,
        ),
        "price value",
    )
    for name, value in (
        ("volume", observation.volume),
        ("turnover_amount_minor", observation.turnover_amount_minor),
    ):
        if value is not None and (isinstance(value, bool) or not isinstance(value, int)):
            raise TypeError(f"{name} must be an integer or None")


def _validated_feature_contract_scope(
    contracts: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """Validate feature context and return source anchors separately.

    Anchor-only contracts are intentionally rejected here.  A feature caller
    must provide the actual T-1 window dates so the builder can prove that the
    source context exists.  The context dates are never themselves treated as
    unavailable: only the contract's source row anchor is a price gap.  This
    lets a gap early in the context block long lookbacks while preserving
    shorter lookbacks whose windows do not include that anchor.
    """

    gap_dates: dict[str, set[str]] = {}
    context_dates_by_symbol: dict[str, set[str]] = {}
    for contract in contracts:
        symbol, anchor_date, _affected_dates = (
            validate_price_unavailable_research_contract(contract)
        )
        affected_window = contract.get("affected_window")
        if not isinstance(affected_window, Mapping):
            raise ValueError("price availability feature window is invalid")
        if affected_window.get("feature_window_complete") is not True:
            raise ValueError(
                "price availability contract feature window is incomplete"
            )
        feature_dates = affected_window.get("feature_window_dates")
        if not isinstance(feature_dates, list) or not feature_dates:
            raise ValueError(
                "price availability contract feature window is empty"
            )
        gap_dates.setdefault(symbol, set()).add(anchor_date)
        context_dates_by_symbol.setdefault(symbol, set()).update(
            str(value) for value in feature_dates
        )
    return gap_dates, context_dates_by_symbol


def _hash_payload(payload: object) -> str:
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return f"sha256:{digest}"


_BASIS_POINTS = Decimal(10_000)


def _quantized_integer(value: Decimal) -> int:
    return int(value.quantize(Decimal(1), rounding=ROUND_HALF_EVEN))


def _return_bp(values: list[Decimal | None], periods: int) -> int | None:
    if len(values) <= periods:
        return None
    window = values[-periods - 1:]
    if any(value is None for value in window):
        return None
    start, end = window[0], window[-1]
    if start is None or start == 0 or end is None:
        return None
    return _quantized_integer((end / start - 1) * _BASIS_POINTS)


def _ratio_bp(numerator: Decimal | None, denominator: Decimal | None) -> int | None:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return _quantized_integer(numerator / denominator * _BASIS_POINTS)


def _difference(left: int | None, right: int | None) -> int | None:
    return None if left is None or right is None else left - right


def _close_to_average_bp(values: list[Decimal | None], periods: int) -> int | None:
    if len(values) < periods:
        return None
    window = values[-periods:]
    if any(value is None for value in window):
        return None
    complete = [value for value in window if value is not None]
    average = sum(complete, Decimal(0)) / Decimal(periods)
    return _ratio_bp(complete[-1] - average, average)


def _recent_ratio_bp(values: list[int | None], periods: int) -> int | None:
    if len(values) < periods:
        return None
    window = values[-periods:]
    if any(value is None for value in window):
        return None
    complete = [value for value in window if value is not None]
    average = Decimal(sum(complete)) / Decimal(periods)
    return _ratio_bp(Decimal(complete[-1]), average)


def _range_bp(observations: list[HistoricalPriceObservation], periods: int) -> int | None:
    if len(observations) < periods:
        return None
    highs = [row.high_price for row in observations[-periods:] if row.high_price is not None]
    lows = [row.low_price for row in observations[-periods:] if row.low_price is not None]
    if len(highs) != periods or len(lows) != periods or min(lows) == 0:
        return None
    return _quantized_integer((max(highs) / min(lows) - 1) * _BASIS_POINTS)


def _volatility_bp(values: list[Decimal | None], periods: int) -> int | None:
    if len(values) <= periods:
        return None
    window = values[-periods - 1:]
    if any(value is None for value in window):
        return None
    complete = [value for value in window if value is not None]
    if any(previous == 0 for previous in complete[:-1]):
        return None
    returns = [current / previous - 1 for previous, current in zip(complete, complete[1:])]
    mean = sum(returns, Decimal(0)) / Decimal(len(returns))
    variance = sum(((value - mean) ** 2 for value in returns), Decimal(0)) / Decimal(len(returns))
    with localcontext() as context:
        context.prec = 34
        return _quantized_integer(variance.sqrt() * _BASIS_POINTS)


def _rsi_bp(value: Decimal | None) -> int | None:
    if value is None:
        return None
    return _quantized_integer((value - Decimal(50)) * Decimal(200))


def _scaled_bp(value: Decimal | None) -> int | None:
    return None if value is None else _quantized_integer(value * Decimal(100))


def _missing_price_observation(symbol: str, trading_date: str) -> HistoricalPriceObservation:
    return HistoricalPriceObservation(
        symbol=symbol,
        trading_date=trading_date,
        open_price=None,
        high_price=None,
        low_price=None,
        close_price=None,
        volume=None,
        turnover_amount_minor=None,
    )


def _index_by_date(
    rows: tuple[HistoricalIndexObservation, ...],
    *,
    cutoff: str,
    index_name: str,
) -> tuple[tuple[str, ...], dict[str, Decimal | None]]:
    selected = sorted(
        (
            row
            for row in rows
            if row.index_name == index_name and row.trading_date <= cutoff
        ),
        key=lambda row: row.trading_date,
    )
    by_date = {row.trading_date: row.close_value for row in selected}
    return tuple(sorted(by_date)), by_date


def _index_closes(
    rows: tuple[HistoricalIndexObservation, ...], *, cutoff: str, index_name: str
) -> list[Decimal | None]:
    selected = sorted(
        (row for row in rows if row.index_name == index_name and row.trading_date <= cutoff),
        key=lambda row: row.trading_date,
    )
    return [row.close_value for row in selected]
