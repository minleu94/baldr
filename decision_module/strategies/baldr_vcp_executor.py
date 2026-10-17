"""因果三段轉折收縮觀測器；確認日才知道轉折，金融比較只用Decimal／整數。"""
from collections import deque
from copy import deepcopy
from dataclasses import dataclass
from decimal import Decimal, DecimalException, localcontext
from numbers import Integral
import re
from typing import Any

import pandas as pd

from analysis_module.technical_analysis.technical_date_support import safe_convert_technical_dates
from decision_module.strategies.baldr_vcp_contract import (
    DIAGNOSTICS_SCHEMA, MAX_BASE_ROWS, MIN_BASE_ROWS, MIN_READY_ROWS, PIVOT_SPAN,
    STRATEGY_ID, STRATEGY_VERSION, rule_definition, strategy_metadata,
)
from decision_module.strategies.contracts import StrategySpec


@dataclass(frozen=True)
class _Bar:
    position: int
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int


@dataclass(frozen=True)
class _Pivot:
    kind: str
    position: int
    price: Decimal
    confirmed_position: int


def _number(value: Any) -> Decimal | None:
    if isinstance(value, bool):
        raise ValueError("價量不可使用布林值")
    if isinstance(value, str):
        value = value.strip()
        if value in ("", "--"):
            return None
        if "," in value:
            if not re.fullmatch(r"[+-]?\d{1,3}(?:,\d{3})+(?:\.\d+)?", value):
                raise ValueError("價量千分位格式不符")
            value = value.replace(",", "")
    try:
        number = Decimal(str(value))
    except (DecimalException, TypeError, ValueError) as exc:
        if pd.isna(value):
            return None
        raise ValueError("價量不是有限數值") from exc
    if number.is_nan():
        return None
    if not number.is_finite() or len(number.as_tuple().digits) > 28 or abs(number.adjusted()) > 24:
        raise ValueError("價量超出有限量化範圍")
    return number


def _push(pivots: deque[_Pivot], pivot: _Pivot) -> None:
    if pivots and pivots[-1].kind == pivot.kind:
        previous = pivots[-1]
        if ((pivot.kind == "high" and pivot.price > previous.price)
                or (pivot.kind == "low" and pivot.price < previous.price)):
            pivots[-1] = pivot
    else:
        pivots.append(pivot)


def _base(pivots: deque[_Pivot], bars: deque[_Bar], position: int, max_base_rows: int) -> tuple[bool, dict[str, Any]]:
    selected = tuple(pivots)[-6:]
    evidence: dict[str, Any] = {"pivots": [
        {"kind": p.kind, "position": p.position, "price": p.price, "confirmed_position": p.confirmed_position}
        for p in selected
    ]}
    if (tuple(p.kind for p in selected) != ("high", "low", "high", "low", "high", "low")
            or not MIN_BASE_ROWS <= selected[-1].position - selected[0].position + 1 <= max_base_rows
            or position - selected[0].position + 1 > max_base_rows):
        return False, evidence
    highs, lows = selected[::2], selected[1::2]
    if (not highs[0].price >= highs[1].price >= highs[2].price
            or not lows[0].price < lows[1].price < lows[2].price
            or any(low.position - high.position < 2 or low.price >= high.price for high, low in zip(highs, lows))):
        return False, evidence
    depths = tuple(high.price - low.price for high, low in zip(highs, lows))
    if (depths[0] * 10000 > highs[0].price * 3000
            or depths[2] * 10000 > highs[2].price * 800
            or not depths[0] * highs[1].price > depths[1] * highs[0].price
            or not depths[1] * highs[2].price > depths[2] * highs[1].price):
        return False, evidence
    first = [bar.volume for bar in bars if highs[0].position <= bar.position <= lows[0].position]
    last = [bar.volume for bar in bars if highs[2].position <= bar.position <= lows[2].position]
    if not first or not last:
        return False, evidence
    evidence.update(first_pullback_volume_sum=sum(first), first_pullback_rows=len(first),
                    last_pullback_volume_sum=sum(last), last_pullback_rows=len(last),
                    pivot_price=max(high.price for high in highs))
    return sum(first) > 0 and sum(last) > 0 and sum(last) * len(first) < sum(first) * len(last), evidence


def _observe_frame(df: pd.DataFrame, *, execution_start_date: str | None = None,
                   pivot_span: int = PIVOT_SPAN, max_base_rows: int = MAX_BASE_ROWS) -> pd.DataFrame:
    """敏感度變體另標身分；正式executor不開放參數變更。"""
    if type(pivot_span) is not int or pivot_span not in (1, 2, 3) or type(max_base_rows) is not int or max_base_rows not in (40, 60, 80):
        raise ValueError("未預宣告的敏感度變體")
    source = df.copy(deep=True)
    if "日期" in source:
        source.index = pd.DatetimeIndex(safe_convert_technical_dates(source["日期"]))
        source = source.drop(columns=["日期"])
    if (not isinstance(source.index, pd.DatetimeIndex) or source.index.hasnans or source.index.tz is not None
            or source.index.has_duplicates or not source.index.is_monotonic_increasing
            or not source.index.equals(source.index.normalize())):
        raise ValueError("收縮研究須為無時區、唯一且依日遞增的日期索引")
    aliases = (("開盤價", "Open", "open"), ("最高價", "High", "high"), ("最低價", "Low", "low"),
               ("收盤價", "Close", "close"), ("成交股數", "Volume", "volume"))
    keys = [next((key for key in group if key in source), None) for group in aliases]
    if any(key is None for key in keys):
        raise ValueError("收縮研究缺少原OHLCV")
    # 直接取各原欄位scalar，禁止iterrows把大整數成交股數轉成float。
    columns = [source[key].tolist() for key in keys if key is not None]
    start = pd.Timestamp(execution_start_date) if execution_start_date is not None else None
    if start is not None and (pd.isna(start) or start.tzinfo is not None or start != start.normalize()):
        raise ValueError("研究起點必須是無時區的日期")
    bars: deque[_Bar] = deque(maxlen=128)
    pivots: deque[_Pivot] = deque(maxlen=12)
    consumed: set[tuple[int, ...]] = set()
    valid_rows = 0
    previous_close: Decimal | None = None
    observations: list[dict[str, Any]] = []
    with localcontext() as context:
        context.prec = 120
        for position, (when, raw) in enumerate(zip(source.index, zip(*columns))):
            open_value, high, low, close, volume = (_number(value) for value in raw)
            if volume is not None and not isinstance(raw[4], (str, Decimal, Integral)):
                raise ValueError("原成交股數須保留整數／Decimal／字串，不接受已轉浮點的數量")
            if volume is not None and (volume < 0 or volume != volume.to_integral_value()):
                raise ValueError("原成交股數必須是非負整數股")
            prices = (open_value, high, low, close)
            if any(value is not None and value <= 0 for value in prices):
                raise ValueError("原OHLC必須為正值")
            if all(value is not None for value in prices):
                assert open_value is not None and high is not None and low is not None and close is not None
                if high < max(open_value, close) or low > min(open_value, close) or high < low:
                    raise ValueError("原OHLC互相矛盾")
            valid = all(value is not None for value in (*prices, volume))
            ready = entry = exit_match = False
            setup: bool | None = None
            ma20 = ma50 = volume_sum = None
            evidence: dict[str, Any] = {"pivots": []}
            already_consumed = False
            if valid:
                assert high is not None and low is not None and close is not None and volume is not None
                bars.append(_Bar(position, high, low, close, int(volume)))
                valid_rows += 1
                window = tuple(bars)[-(2 * pivot_span + 1):]
                if len(window) == 2 * pivot_span + 1:
                    center = window[pivot_span]
                    others = window[:pivot_span] + window[pivot_span + 1:]
                    peak = all(center.high > bar.high for bar in others)
                    trough = all(center.low < bar.low for bar in others)
                    if peak != trough:
                        _push(pivots, _Pivot("high" if peak else "low", center.position,
                                            center.high if peak else center.low, position))
                while pivots and position - pivots[0].position + 1 > max_base_rows:
                    pivots.popleft()
                consumed = {identity for identity in consumed if position - identity[0] + 1 <= max_base_rows}
                recent = tuple(bars)
                if len(recent) >= 20:
                    ma20 = sum((bar.close for bar in recent[-20:]), Decimal(0)) / Decimal(20)
                    volume_sum = sum(bar.volume for bar in recent[-20:])
                if len(recent) >= 50:
                    ma50 = sum((bar.close for bar in recent[-50:]), Decimal(0)) / Decimal(50)
                ready = valid_rows >= MIN_READY_ROWS and volume_sum is not None and volume_sum > 0
                if ready:
                    assert ma20 is not None and ma50 is not None and previous_close is not None and volume_sum is not None
                    setup, evidence = _base(pivots, bars, position, max_base_rows)
                    identity = tuple(p["position"] for p in evidence["pivots"])
                    already_consumed = identity in consumed
                    exit_match = close < ma20
                    pivot_price = evidence.get("pivot_price")
                    entry = (setup and not already_consumed and not exit_match and pivot_price is not None
                             and previous_close <= pivot_price < close and close > ma50
                             and int(volume) * 40 > volume_sum * 3)
                    if entry:
                        consumed.add(identity)
            else:
                bars.clear()
                pivots.clear()
                consumed.clear()
                valid_rows = 0
            context_only = start is not None and when < start
            if context_only:
                entry = exit_match = False
            reason = ("context_only_no_order" if context_only else "warming_or_missing_inputs" if not ready
                      else "below_sma20_exit_intent" if exit_match else "three_contraction_breakout_entry_intent"
                      if entry else "pattern_not_matched" if setup is False else "rule_hold")
            observations.append({
                "signal": -1 if exit_match else 1 if entry else 0, "rule_observation_ready": ready,
                "entry_rule_match": entry, "exit_rule_match": exit_match, "reason_tags": reason,
                "setup_match": setup, "pattern_already_consumed": already_consumed,
                "valid_observed_rows": valid_rows, "previous_close": previous_close,
                "observation_position": position, "observed_open": open_value,
                "observed_high": high, "observed_low": low,
                "observed_close": close, "observed_volume": None if volume is None else int(volume),
                "vcp_ma20": ma20, "vcp_ma50": ma50, "volume_sum20": volume_sum,
                "contraction_evidence": evidence,
            })
            previous_close = close if valid else None
    result = source.copy(deep=True)
    fields = (tuple(observations[0]) if observations else
              ("signal", "rule_observation_ready", "entry_rule_match", "exit_rule_match", "reason_tags"))
    for field in fields:
        scalar = field in {"signal", "rule_observation_ready", "entry_rule_match", "exit_rule_match",
                           "valid_observed_rows", "observation_position", "pattern_already_consumed"}
        result[field] = pd.Series([row[field] for row in observations], index=source.index, dtype=None if scalar else object)
    result["regime_match"] = False
    fixed = (pivot_span, max_base_rows) == (PIVOT_SPAN, MAX_BASE_ROWS)
    result.attrs["rule_diagnostics"] = {
        "schema": DIAGNOSTICS_SCHEMA if fixed else "baldr-vcp-three-contractions-sensitivity.v1",
        "strategy_id": STRATEGY_ID if fixed else "experimental_not_registered_strategy",
        "strategy_version": STRATEGY_VERSION if fixed else "unregistered",
        "fixed_version_compatible": fixed, "pivot_span": pivot_span, "max_base_rows": max_base_rows,
        "total_sessions": len(result), "ready_sessions": sum(row["rule_observation_ready"] for row in observations),
        "entry_signal_sessions": sum(row["entry_rule_match"] for row in observations),
        "exit_condition_sessions": sum(row["exit_rule_match"] for row in observations),
        "historical_pit_eligible": False, "performance_evaluable": False,
    }
    return result


class BaldrVCPExecutor:
    @staticmethod
    def get_meta() -> dict[str, Any]:
        return strategy_metadata()

    def __init__(self, spec: StrategySpec) -> None:
        if (spec.strategy_id, spec.strategy_version) != (STRATEGY_ID, STRATEGY_VERSION):
            raise ValueError("三段轉折收縮研究版本不符")
        self._spec_payload = deepcopy(spec.to_dict())
        self.rules = rule_definition(spec.config.get("params", {}))

    def generate_signals(self, df: pd.DataFrame, spec: StrategySpec,
                         execution_start_date: str | None = None) -> pd.DataFrame:
        if spec.to_dict() != self._spec_payload:
            raise ValueError("三段轉折收縮執行規格已變動")
        return _observe_frame(df, execution_start_date=execution_start_date)
