"""既有個股日價格與均線的唯讀研究快照投影。"""

from __future__ import annotations

import hashlib
import json
import math
import numbers
from collections import OrderedDict
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from threading import RLock
from typing import Any, Literal, Sequence

from app_module.stock_research_report_dtos import (
    StockMetricDTO,
    StockPricePointDTO,
    StockTechnicalSnapshotDTO,
)


DAILY_MARKET_FEATURE_CONTRACT_VERSION = "daily-market-feature-snapshot.v1"
DAILY_MARKET_FEATURE_MAX_CACHE_ENTRIES = 4
DAILY_MARKET_FEATURE_KEYS = ("close", "MA20", "MA60")
DAILY_MARKET_CONDITION_KEYS = ("close_above_ma20", "close_above_ma60")
PRICE_UNIT = "TWD/share"
WARMUP_BASIS = (
    "analysis_module.technical_analysis.technical_indicators.calculate_causal_indicators:"
    "TA-Lib SMA on the last contiguous valid OHLC segment"
)

FeatureState = Literal["observed", "unknown"]
WarmupState = Literal[
    "not_required", "sufficient_observed_prefix", "unknown"
]
ConditionState = Literal["match", "no_match", "unknown"]
PriceRelation = Literal["above", "below", "equal", "unknown"]


@dataclass(frozen=True, slots=True)
class DailyMarketFeature:
    """一項有明確來源、日期、單位與暖機證據的既有值。"""

    key: str
    value: Decimal | None
    unit: str
    state: FeatureState
    data_date: str | None
    source_id: str | None
    source_fingerprint_sha256: str
    reason: str | None = None
    warmup_required_count: int | None = None
    warmup_observed_count: int | None = None
    warmup_state: WarmupState = "not_required"
    warmup_basis: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "value": _decimal_text(self.value),
            "unit": self.unit,
            "state": self.state,
            "data_date": self.data_date,
            "source_id": self.source_id,
            "source_fingerprint_sha256": self.source_fingerprint_sha256,
            "reason": self.reason,
            "warmup_required_count": self.warmup_required_count,
            "warmup_observed_count": self.warmup_observed_count,
            "warmup_state": self.warmup_state,
            "warmup_basis": self.warmup_basis,
        }


@dataclass(frozen=True, slots=True)
class DailyMarketCondition:
    """把同日 close 與既有均線的相對位置表為觀察，不代表策略訊號。"""

    name: str
    state: ConditionState
    relation: PriceRelation
    close_value: Decimal | None
    reference_value: Decimal | None
    unit: str
    data_date: str | None
    reason: str | None = None
    semantics: str = "existing_observation"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "state": self.state,
            "relation": self.relation,
            "close_value": _decimal_text(self.close_value),
            "reference_value": _decimal_text(self.reference_value),
            "unit": self.unit,
            "data_date": self.data_date,
            "reason": self.reason,
            "semantics": self.semantics,
        }


@dataclass(frozen=True, slots=True)
class DailyMarketFeatureSnapshot:
    """單股、單決策日、綁定 scope 與完整輸入身份的研究投影。"""

    stock_code: str
    decision_date: date
    scope_identity: str
    market_date: str | None
    features: tuple[DailyMarketFeature, ...]
    conditions: tuple[DailyMarketCondition, ...]
    contract_version: str
    input_fingerprint_sha256: str
    snapshot_identity_sha256: str
    usage: str = "current_observed_research_only"
    official_availability_state: str = "unknown"
    market_calendar_completeness: str = "unknown"
    historical_pit_eligible: bool = False

    def feature(self, key: str) -> DailyMarketFeature:
        for item in self.features:
            if item.key == key:
                return item
        raise KeyError(key)

    def condition(self, name: str) -> DailyMarketCondition:
        for item in self.conditions:
            if item.name == name:
                return item
        raise KeyError(name)

    def to_dict(self) -> dict[str, Any]:
        """回傳 JSON-ready mapping；Decimal 僅在序列化邊界轉成字串。"""

        return {
            "contract_version": self.contract_version,
            "snapshot_identity_sha256": self.snapshot_identity_sha256,
            "input_fingerprint_sha256": self.input_fingerprint_sha256,
            "stock_code": self.stock_code,
            "decision_date": self.decision_date.isoformat(),
            "scope_identity": self.scope_identity,
            "market_date": self.market_date,
            "features": {item.key: item.to_dict() for item in self.features},
            "conditions": {item.name: item.to_dict() for item in self.conditions},
            "policy": {
                "usage": self.usage,
                "official_availability_state": self.official_availability_state,
                "market_calendar_completeness": self.market_calendar_completeness,
                "historical_pit_eligible": self.historical_pit_eligible,
                "warmup_is_formal_or_calendar_qualification": False,
            },
        }


@dataclass(frozen=True, slots=True)
class _PriceRow:
    point: StockPricePointDTO
    parsed_date: date


class DailyMarketFeatureSnapshotService:
    """將既有 StockReport DTO 投影成有界快取的唯讀每日特徵。"""

    def __init__(self, *, max_entries: int = DAILY_MARKET_FEATURE_MAX_CACHE_ENTRIES) -> None:
        if (
            isinstance(max_entries, bool)
            or not isinstance(max_entries, int)
            or not 1 <= max_entries <= DAILY_MARKET_FEATURE_MAX_CACHE_ENTRIES
        ):
            raise ValueError(
                "max_entries 必須介於 1 與 "
                f"{DAILY_MARKET_FEATURE_MAX_CACHE_ENTRIES} 之間"
            )
        self._max_entries = max_entries
        self._cache: OrderedDict[str, DailyMarketFeatureSnapshot] = OrderedDict()
        self._cache_version = DAILY_MARKET_FEATURE_CONTRACT_VERSION
        self._lock = RLock()

    def project(
        self,
        stock_code: str,
        decision_date: date,
        scope_identity: str,
        price_points: Sequence[StockPricePointDTO],
        technical: StockTechnicalSnapshotDTO | None,
    ) -> DailyMarketFeatureSnapshot:
        """投影既有 close／MA 值；不讀取資料庫，也不重算技術指標。"""

        code = str(stock_code).strip()
        scope = str(scope_identity).strip()
        if not code:
            raise ValueError("stock_code 不可為空")
        if not scope:
            raise ValueError("scope_identity 不可為空，請由 caller 明示研究母體身份")
        if isinstance(decision_date, datetime) or not isinstance(decision_date, date):
            raise ValueError("decision_date 必須是 date，不可含時間")
        if isinstance(price_points, (str, bytes)):
            raise TypeError("price_points 必須是 StockPricePointDTO 序列")
        points = tuple(price_points)
        if any(not isinstance(point, StockPricePointDTO) for point in points):
            raise TypeError("price_points 僅接受 StockPricePointDTO")
        if technical is not None and not isinstance(technical, StockTechnicalSnapshotDTO):
            raise TypeError("technical 僅接受 StockTechnicalSnapshotDTO 或 None")

        version = DAILY_MARKET_FEATURE_CONTRACT_VERSION
        input_fingerprint = _input_fingerprint(code, decision_date, scope, points, technical)
        snapshot_identity = _stable_hash(
            {
                "contract_version": version,
                "stock_code": code,
                "decision_date": decision_date.isoformat(),
                "scope_identity": scope,
                "input_fingerprint_sha256": input_fingerprint,
            }
        )
        with self._lock:
            if self._cache_version != version:
                self._cache.clear()
                self._cache_version = version
            cached = self._cache.get(snapshot_identity)
            if cached is not None:
                self._cache.move_to_end(snapshot_identity)
                return cached

            snapshot = _project_snapshot(
                code,
                decision_date,
                scope,
                points,
                technical,
                version,
                input_fingerprint,
                snapshot_identity,
            )
            self._cache[snapshot_identity] = snapshot
            self._cache.move_to_end(snapshot_identity)
            while len(self._cache) > self._max_entries:
                self._cache.popitem(last=False)
            return snapshot

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()


def daily_market_feature_input_fingerprint(
    stock_code: str,
    decision_date: date,
    scope_identity: str,
    price_points: Sequence[StockPricePointDTO],
    technical: StockTechnicalSnapshotDTO | None,
) -> str:
    """回傳 project 使用的完整輸入摘要，不執行特徵投影。"""

    code = str(stock_code).strip()
    scope = str(scope_identity).strip()
    if not code:
        raise ValueError("stock_code 不可為空")
    if not scope:
        raise ValueError("scope_identity 不可為空，請由 caller 明示研究母體身份")
    if isinstance(decision_date, datetime) or not isinstance(decision_date, date):
        raise ValueError("decision_date 必須是 date，不可含時間")
    if isinstance(price_points, (str, bytes)):
        raise TypeError("price_points 必須是 StockPricePointDTO 序列")
    points = tuple(price_points)
    if any(not isinstance(point, StockPricePointDTO) for point in points):
        raise TypeError("price_points 僅接受 StockPricePointDTO")
    if technical is not None and not isinstance(technical, StockTechnicalSnapshotDTO):
        raise TypeError("technical 僅接受 StockTechnicalSnapshotDTO 或 None")
    return _input_fingerprint(code, decision_date, scope, points, technical)


def _project_snapshot(
    stock_code: str,
    decision_date: date,
    scope_identity: str,
    points: tuple[StockPricePointDTO, ...],
    technical: StockTechnicalSnapshotDTO | None,
    version: str,
    input_fingerprint: str,
    snapshot_identity: str,
) -> DailyMarketFeatureSnapshot:
    rows: list[_PriceRow] = []
    invalid_market_date = False
    future_market_date = False
    for point in points:
        parsed = _parse_market_date(point.data_date)
        if parsed is None:
            invalid_market_date = True
            continue
        if parsed > decision_date:
            future_market_date = True
            continue
        rows.append(_PriceRow(point=point, parsed_date=parsed))

    rows.sort(key=lambda item: item.parsed_date)
    rows_by_date: dict[date, list[_PriceRow]] = {}
    for row in rows:
        rows_by_date.setdefault(row.parsed_date, []).append(row)
    duplicate_market_date = any(len(group) > 1 for group in rows_by_date.values())
    latest_row = rows[-1] if rows else None
    market_date = latest_row.parsed_date.isoformat() if latest_row is not None else None

    close_value: Decimal | None = None
    close_reason: str | None = None
    close_source_id: str | None = None
    if not points:
        close_reason = "no_price_rows"
    elif future_market_date:
        close_reason = "future_market_date"
    elif invalid_market_date:
        close_reason = "invalid_market_date"
    elif latest_row is None:
        close_reason = "no_price_rows"
    elif len(rows_by_date[latest_row.parsed_date]) > 1:
        close_reason = "duplicate_market_date"
    else:
        latest_point = latest_row.point
        close_value = _finite_positive_decimal(latest_point.close_price)
        if latest_point.close_price is None:
            close_reason = "latest_close_missing"
        elif close_value is None:
            close_reason = "latest_close_invalid"
        elif latest_point.quality != "observed":
            close_value = None
            close_reason = "price_quality_not_observed"
        elif not str(latest_point.source_id or "").strip():
            close_value = None
            close_reason = "price_source_identity_missing"
        else:
            close_source_id = str(latest_point.source_id).strip()

    source_hash_by_key: dict[str, str] = {}
    if latest_row is not None:
        source_hash_by_key["close"] = _feature_fingerprint(
            "close",
            latest_row.point.source_id,
            latest_row.parsed_date.isoformat(),
            latest_row.point.source_snapshot_hash,
            latest_row.point,
            close_value,
        )
    else:
        source_hash_by_key["close"] = _feature_fingerprint(
            "close", None, None, "", None, None
        )
    close_feature = DailyMarketFeature(
        key="close",
        value=close_value,
        unit=PRICE_UNIT,
        state="observed" if close_value is not None else "unknown",
        data_date=market_date,
        source_id=close_source_id,
        source_fingerprint_sha256=source_hash_by_key["close"],
        reason=close_reason,
    )

    warmup_counts: dict[int, int | None] = {20: None, 60: None}
    warmup_reasons: dict[int, str | None] = {20: None, 60: None}
    if invalid_market_date:
        warmup_reasons = {20: "invalid_market_date", 60: "invalid_market_date"}
    elif future_market_date:
        warmup_reasons = {20: "future_market_date", 60: "future_market_date"}
    elif duplicate_market_date:
        warmup_reasons = {20: "duplicate_market_date", 60: "duplicate_market_date"}
    elif latest_row is None:
        warmup_counts = {20: 0, 60: 0}
        warmup_reasons = {20: "no_price_rows", 60: "no_price_rows"}
    else:
        streak = 0
        invalid_ohlc_at_tail = False
        for row in reversed(rows):
            if _valid_ohlc(row.point):
                streak += 1
                if streak >= 60:
                    break
            else:
                invalid_ohlc_at_tail = True
                break
        warmup_counts = {20: streak, 60: streak}
        warmup_reasons = {
            window: (
                None
                if streak >= window
                else "invalid_ohlc_row"
                if invalid_ohlc_at_tail
                else "insufficient_valid_ohlc_streak"
            )
            for window in (20, 60)
        }

    technical_date = _parse_market_date(technical.data_date) if technical is not None else None
    metric_groups: dict[str, list[StockMetricDTO]] = {"MA20": [], "MA60": []}
    if technical is not None:
        for indicator in technical.indicators:
            if indicator.key in metric_groups:
                metric_groups[indicator.key].append(indicator)

    ma_features: list[DailyMarketFeature] = []
    for key, window in (("MA20", 20), ("MA60", 60)):
        metric_list = metric_groups[key]
        selected_metric = metric_list[0] if len(metric_list) == 1 else None
        raw_source_id = (
            (selected_metric.source_id or technical.source_id)
            if selected_metric is not None and technical is not None
            else None
        )
        source_id = str(raw_source_id).strip() if raw_source_id else ""
        metric_date = (
            _parse_market_date(selected_metric.data_as_of)
            if selected_metric is not None
            else None
        )
        value: Decimal | None = None
        reason: str | None = warmup_reasons[window]

        if reason is None and close_reason is not None:
            reason = close_reason
        if reason is None and technical is None:
            reason = "technical_missing"
        elif reason is None and technical is not None and technical.quality != "observed":
            reason = "technical_quality_not_observed"
        elif reason is None and technical_date is None:
            reason = "technical_date_mismatch"
        elif reason is None and market_date is not None and (
            latest_row is None or technical_date != latest_row.parsed_date
        ):
            reason = "technical_date_mismatch"
        elif reason is None and len(metric_list) == 0:
            reason = "technical_metric_missing"
        elif reason is None and len(metric_list) > 1:
            reason = "duplicate_technical_metric"
        elif reason is None and selected_metric is not None and selected_metric.data_as_of:
            if (
                metric_date is None
                or metric_date != technical_date
                or latest_row is None
                or metric_date != latest_row.parsed_date
            ):
                reason = "technical_metric_date_mismatch"
        elif reason is None and selected_metric is not None and not selected_metric.data_as_of:
            reason = "technical_metric_date_mismatch"
        if reason is None and selected_metric is not None and selected_metric.quality != "observed":
            reason = "technical_metric_not_observed"
        if reason is None and selected_metric is not None and not source_id:
            reason = "technical_source_identity_missing"
        if reason is None and selected_metric is not None:
            value = _finite_positive_decimal(selected_metric.value)
            if value is None:
                reason = "technical_metric_invalid"

        metric_source = source_id or None
        source_fingerprint = _feature_fingerprint(
            key,
            metric_source,
            metric_date.isoformat() if metric_date else None,
            "",
            selected_metric,
            value,
            warmup_rows=rows[-window:],
        )
        ma_features.append(
            DailyMarketFeature(
                key=key,
                value=value if reason is None else None,
                unit=PRICE_UNIT,
                state="observed" if reason is None and value is not None else "unknown",
                data_date=metric_date.isoformat() if metric_date is not None else market_date,
                source_id=metric_source,
                source_fingerprint_sha256=source_fingerprint,
                reason=reason,
                warmup_required_count=window,
                warmup_observed_count=warmup_counts[window],
                warmup_state=(
                    "sufficient_observed_prefix"
                    if warmup_reasons[window] is None
                    else "unknown"
                ),
                warmup_basis=WARMUP_BASIS,
            )
        )

    feature_map = {item.key: item for item in (close_feature, *ma_features)}
    conditions = tuple(
        _make_condition(
            name,
            close_feature,
            feature_map[ma_key],
            market_date,
        )
        for name, ma_key in (
            ("close_above_ma20", "MA20"),
            ("close_above_ma60", "MA60"),
        )
    )
    return DailyMarketFeatureSnapshot(
        stock_code=stock_code,
        decision_date=decision_date,
        scope_identity=scope_identity,
        market_date=market_date,
        features=(close_feature, *ma_features),
        conditions=conditions,
        contract_version=version,
        input_fingerprint_sha256=input_fingerprint,
        snapshot_identity_sha256=snapshot_identity,
    )


def _make_condition(
    name: str,
    close: DailyMarketFeature,
    moving_average: DailyMarketFeature,
    market_date: str | None,
) -> DailyMarketCondition:
    data_date = market_date
    if close.state != "observed" or moving_average.state != "observed":
        reasons = [
            item.reason
            for item in (close, moving_average)
            if item.reason is not None
        ]
        reason = reasons[0] if reasons else "condition_inputs_unknown"
        return DailyMarketCondition(
            name=name,
            state="unknown",
            relation="unknown",
            close_value=close.value,
            reference_value=moving_average.value,
            unit=PRICE_UNIT,
            data_date=data_date,
            reason=reason,
        )
    assert close.value is not None
    assert moving_average.value is not None
    if close.value > moving_average.value:
        relation: PriceRelation = "above"
        state: ConditionState = "match"
    elif close.value < moving_average.value:
        relation = "below"
        state = "no_match"
    else:
        relation = "equal"
        state = "no_match"
    return DailyMarketCondition(
        name=name,
        state=state,
        relation=relation,
        close_value=close.value,
        reference_value=moving_average.value,
        unit=PRICE_UNIT,
        data_date=data_date,
    )


def _valid_ohlc(point: StockPricePointDTO) -> bool:
    if point.quality != "observed":
        return False
    open_price = _finite_positive_decimal(point.open_price)
    high_price = _finite_positive_decimal(point.high_price)
    low_price = _finite_positive_decimal(point.low_price)
    close_price = _finite_positive_decimal(point.close_price)
    if None in (open_price, high_price, low_price, close_price):
        return False
    assert open_price is not None and high_price is not None
    assert low_price is not None and close_price is not None
    return low_price <= min(open_price, close_price) and high_price >= max(open_price, close_price)


def _finite_positive_decimal(value: Any) -> Decimal | None:
    if not isinstance(value, Decimal) or not value.is_finite() or value <= 0:
        return None
    return value


def _parse_market_date(value: Any) -> date | None:
    if not isinstance(value, (str, date)) or isinstance(value, datetime):
        return None
    if isinstance(value, date):
        return value
    text = value.strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        if len(text) == 8 and text.isdigit():
            try:
                return date(int(text[:4]), int(text[4:6]), int(text[6:8]))
            except ValueError:
                return None
        return None


def _input_fingerprint(
    stock_code: str,
    decision_date: date,
    scope_identity: str,
    points: tuple[StockPricePointDTO, ...],
    technical: StockTechnicalSnapshotDTO | None,
) -> str:
    payload = {
        "stock_code": stock_code,
        "decision_date": decision_date.isoformat(),
        "scope_identity": scope_identity,
        "contract_version": DAILY_MARKET_FEATURE_CONTRACT_VERSION,
        "price_points": [_canonical_value(point) for point in points],
        "technical": _canonical_value(technical),
    }
    return _stable_hash(payload)


def _feature_fingerprint(
    key: str,
    source_id: str | None,
    data_date: str | None,
    source_row_hash: str,
    source_value: Any,
    value: Decimal | None,
    *,
    warmup_rows: Sequence[_PriceRow] = (),
) -> str:
    return _stable_hash(
        {
            "feature_key": key,
            "source_id": source_id,
            "data_date": data_date,
            "source_row_hash": source_row_hash,
            "source_value": _canonical_value(source_value),
            "value": _decimal_text(value),
            "warmup_rows": [
                {
                    "date": row.parsed_date.isoformat(),
                    "source_row_hash": row.point.source_snapshot_hash,
                    "open": _decimal_text(row.point.open_price),
                    "high": _decimal_text(row.point.high_price),
                    "low": _decimal_text(row.point.low_price),
                    "close": _decimal_text(row.point.close_price),
                    "source_id": row.point.source_id,
                    "quality": row.point.quality,
                }
                for row in warmup_rows
            ],
        }
    )


def _canonical_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, Decimal):
        return {"decimal": str(value)}
    if isinstance(value, datetime):
        return {"datetime": value.isoformat()}
    if isinstance(value, date):
        return {"date": value.isoformat()}
    if isinstance(value, numbers.Integral):
        return {"integer": int(value)}
    if isinstance(value, numbers.Real):
        # 僅於輸入身份的序列化邊界固定非 Decimal 欄位；不是金融計算，
        # snapshot 的價格值仍只接受有限 Decimal。
        number = float(value)
        return {"float_hex": number.hex() if math.isfinite(number) else repr(number)}
    if isinstance(value, (tuple, list)):
        return [_canonical_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _canonical_value(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if hasattr(value, "__dataclass_fields__"):
        return {
            field_name: _canonical_value(getattr(value, field_name))
            for field_name in value.__dataclass_fields__
        }
    return {"type": type(value).__qualname__, "value": str(value)}


def _decimal_text(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


def _stable_hash(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
