"""帶寬低點＋真突破＋既有量能口徑；只輸出意圖，成交沿原Broker。"""
from collections import deque
from copy import deepcopy
from decimal import Decimal, DecimalException, localcontext
from typing import Any

import pandas as pd

from analysis_module.technical_analysis.technical_date_support import safe_convert_technical_dates
from analysis_module.technical_analysis.technical_indicators import calculate_causal_indicators
from decision_module.strategies.baldr_bollinger_squeeze_contract import (
    DIAGNOSTICS_SCHEMA, STRATEGY_ID, STRATEGY_VERSION, rule_definition, strategy_metadata,
)
from decision_module.strategies.contracts import StrategySpec


def _number(value: Any, *, positive: bool = False) -> Decimal | None:
    if isinstance(value, bool):
        return None
    try:
        result = Decimal(str(value))
    except (DecimalException, TypeError, ValueError):
        return None
    if (not result.is_finite() or (positive and result <= 0)
            or len(result.as_tuple().digits) > 28 or abs(result.adjusted()) > 24):
        return None
    return result


class BaldrBollingerSqueezeExecutor:
    @staticmethod
    def get_meta() -> dict[str, Any]:
        return strategy_metadata()

    def __init__(self, spec: StrategySpec) -> None:
        if (spec.strategy_id, spec.strategy_version) != (STRATEGY_ID, STRATEGY_VERSION):
            raise ValueError("布林帶寬低點突破策略版本不符")
        self.spec = spec
        self._spec_payload = deepcopy(spec.to_dict())
        self.rules = rule_definition(spec.config.get("params", {}))

    def generate_signals(self, df: pd.DataFrame, spec: StrategySpec,
                         execution_start_date: str | None = None) -> pd.DataFrame:
        if spec.to_dict() != self._spec_payload:
            raise ValueError("布林帶寬低點突破執行規格已變動")
        source = df.copy(deep=True)
        if "日期" in source:
            source.index = pd.DatetimeIndex(safe_convert_technical_dates(source["日期"]))
            source = source.drop(columns=["日期"])
        if (not isinstance(source.index, pd.DatetimeIndex) or source.index.hasnans
                or source.index.tz is not None or source.index.has_duplicates
                or not source.index.is_monotonic_increasing
                or not source.index.equals(source.index.normalize())):
            raise ValueError("布林帶寬研究須為無時區、唯一且依日遞增的日期索引")
        volume_key = next((key for key in ("成交股數", "Volume", "volume") if key in source), None)
        close_key = next((key for key in ("收盤價", "Close", "close") if key in source), None)
        if volume_key is None or close_key is None:
            raise ValueError("布林帶寬研究缺少原收盤價／成交股數")
        # 預存同名bands不具本次方法身分；沿原因果分析邊界重新計算。
        result = calculate_causal_indicators(source)
        if not result.index.equals(source.index):
            raise ValueError("因果分析不得改變原成交股數的逐列身分")
        raw_volumes = source[volume_key].tolist()
        start = pd.Timestamp(execution_start_date) if execution_start_date is not None else None
        if start is not None and (pd.isna(start) or start.tzinfo is not None or start != start.normalize()):
            raise ValueError("研究起點必須是無時區的日期")
        widths: deque[tuple[Decimal, Decimal]] = deque(maxlen=20)
        volumes: deque[Decimal] = deque(maxlen=20)
        previous_close: Decimal | None = None
        previous_upper: Decimal | None = None
        previous_squeeze: bool | None = None
        observations: list[dict[str, object]] = []
        # 跨乘避免把帶寬比例或量能門檻量化成浮點數／四捨五入後決策。
        with localcontext() as context:
            context.prec = 120
            for position, (when, row) in enumerate(result.iterrows()):
                close, upper, middle = (_number(row[key], positive=True)
                                        for key in (close_key, "upperband", "middleband"))
                lower = _number(row["lowerband"])
                # iterrows可能把整數量轉float；量能決策必須取原欄位的逐列scalar。
                raw_volume = raw_volumes[position]
                volume = _number(raw_volume)
                if volume is None and not pd.isna(raw_volume):
                    raise ValueError("成交股數不是可用的有限量化數值")
                if volume is not None and volume < 0:
                    raise ValueError("成交股數不可為負數")
                valid_band = (close is not None and upper is not None and middle is not None
                              and lower is not None and upper >= middle >= lower)
                squeeze: bool | None = None
                floor_width = floor_middle = width = None
                if valid_band and upper is not None and lower is not None and middle is not None:
                    width = upper - lower
                    widths.append((width, middle))
                    if len(widths) == 20:
                        floor_width, floor_middle = widths[0]
                        for observed_width, observed_middle in widths:
                            if observed_width * floor_middle < floor_width * observed_middle:
                                floor_width, floor_middle = observed_width, observed_middle
                        squeeze = width * floor_middle <= floor_width * middle
                else:
                    widths.clear()
                if valid_band and volume is not None:
                    volumes.append(volume)
                else:
                    volumes.clear()
                volume_sum = sum(volumes, Decimal(0)) if len(volumes) == 20 else None
                volume_match = (volume is not None and volume_sum is not None and volume_sum > 0
                                and volume * 40 > volume_sum * 3)
                ready = (valid_band and squeeze is not None and volume_sum is not None
                         and volume_sum > 0 and previous_close is not None
                         and previous_upper is not None and previous_squeeze is not None)
                cross = (close is not None and upper is not None and previous_close is not None
                         and previous_upper is not None and previous_close <= previous_upper and close > upper)
                entry = ready and previous_squeeze is True and cross and volume_match
                exit_match = ready and close is not None and middle is not None and close < middle
                context_only = start is not None and when < start
                signal = 0 if context_only else -1 if exit_match else 1 if entry else 0
                if context_only:
                    entry = exit_match = False
                reason = ("context_only_no_order" if context_only else "warming_or_missing_inputs" if not ready
                          else "below_middle_exit_intent" if exit_match else "squeeze_cross_volume_entry_intent"
                          if entry else "rule_hold")
                observations.append({
                    "signal": signal, "rule_observation_ready": ready,
                    "entry_rule_match": entry, "exit_rule_match": exit_match, "reason_tags": reason,
                    "squeeze": squeeze, "previous_squeeze": previous_squeeze,
                    "previous_close": previous_close, "previous_upper": previous_upper,
                    "band_width": width, "floor_width20": floor_width, "floor_middle20": floor_middle,
                    "observed_volume": volume, "volume_sum20": volume_sum,
                })
                previous_close, previous_upper = (close, upper) if valid_band else (None, None)
                previous_squeeze = squeeze
        for key in observations[0] if observations else ():
            result[key] = pd.Series([item[key] for item in observations], index=result.index,
                                    dtype=object if key not in {"signal", "rule_observation_ready",
                                        "entry_rule_match", "exit_rule_match"} else None)
        # 空輸入保留相同欄位，讓producer按原空結果契約處理。
        if not observations:
            for key in ("signal", "rule_observation_ready", "entry_rule_match", "exit_rule_match", "reason_tags"):
                result[key] = pd.Series(index=result.index, dtype=object)
        result["regime_match"] = False
        ready_count = sum(bool(item["rule_observation_ready"]) for item in observations)
        result.attrs["rule_diagnostics"] = {
            "schema": DIAGNOSTICS_SCHEMA, "strategy_id": STRATEGY_ID, "strategy_version": STRATEGY_VERSION,
            "total_sessions": len(result), "ready_sessions": ready_count,
            "unavailable_sessions": len(result) - ready_count,
            "entry_signal_sessions": sum(bool(item["entry_rule_match"]) for item in observations),
            "exit_condition_sessions": sum(bool(item["exit_rule_match"]) for item in observations),
            "squeeze_window": 20, "volume_window": 20, "volume_multiple": "1.5",
            "entry_description": "前列20列帶寬低點；當列首次突破上軌且含當日20日均量比>1.5",
            "exit_description": "已可判讀且收盤低於中軌發出場意圖；等於保持",
        }
        return result
