"""四均線研究沿既有因果分析邊界取值，再以Decimal比較原F02規則。"""
from copy import deepcopy
from decimal import Decimal, DecimalException
from typing import Any

import pandas as pd

from analysis_module.technical_analysis.technical_indicators import calculate_causal_indicators
from analysis_module.technical_analysis.technical_date_support import safe_convert_technical_dates
from decision_module.strategies.baldr_ma_alignment_contract import (
    STRATEGY_ID, STRATEGY_VERSION, DIAGNOSTICS_SCHEMA, PERIODS,
    rule_definition, strategy_metadata,
)
from decision_module.strategies.contracts import StrategySpec


def _positive(value: Any) -> Decimal | None:
    try:
        number = Decimal(str(value))
        return number if number.is_finite() and number > 0 else None
    except (DecimalException, TypeError, ValueError):
        return None


class BaldrMAAlignmentExecutor:
    @staticmethod
    def get_meta() -> dict[str, Any]:
        return strategy_metadata()

    def __init__(self, spec: StrategySpec) -> None:
        if (spec.strategy_id, spec.strategy_version) != (STRATEGY_ID, STRATEGY_VERSION):
            raise ValueError("四均線基礎策略版本不符")
        self.spec = deepcopy(spec)
        self.rules = rule_definition(spec.config.get("params", {}))

    def generate_signals(self, df: pd.DataFrame, spec: StrategySpec,
                         execution_start_date: str | None = None) -> pd.DataFrame:
        if spec.to_dict() != self.spec.to_dict():
            raise ValueError("四均線執行規格已變動")
        source = df.copy()
        if "日期" in source:
            source.index = pd.DatetimeIndex(safe_convert_technical_dates(source["日期"]))
            source = source.drop(columns=["日期"])
        if (not isinstance(source.index, pd.DatetimeIndex) or source.index.hasnans
                or source.index.tz is not None or not source.index.is_monotonic_increasing
                or source.index.has_duplicates or not source.index.equals(source.index.normalize())):
            raise ValueError("四均線研究須為無時區、唯一且依日遞增的日期索引")
        if not any(key in source for key in ("成交股數", "Volume", "volume")):
            raise ValueError("四均線研究缺少原成交股數，不可假定成交可行")
        # 同名預存均線不作權威；浮點只存在於既有分析及圖表邊界。
        result = calculate_causal_indicators(source)
        close_key = next((key for key in ("收盤價", "Close", "close") if key in result), None)
        if close_key is None:
            raise ValueError("缺少收盤價")
        start = pd.Timestamp(execution_start_date) if execution_start_date is not None else None
        signals: list[int] = []
        ready: list[bool] = []
        alignments: list[bool | None] = []
        previous_alignments: list[bool | None] = []
        entries: list[bool] = []
        exits: list[bool] = []
        reasons: list[str] = []
        previous: bool | None = None
        for when, row in result.iterrows():
            values = tuple(_positive(row[f"MA{period}"]) for period in PERIODS)
            valid = _positive(row[close_key]) is not None and all(value is not None for value in values)
            alignment: bool | None = None
            entry = exit_match = False
            reason = "warming_or_missing_ohlc"
            if valid:
                alignment = all(left > right for left, right in zip(values, values[1:])
                                if left is not None and right is not None)
                if start is not None and when < start:
                    reason = "context_only_no_order"
                else:
                    entry = previous is False and alignment
                    exit_match = not alignment
                    reason = ("alignment_transition_entry_intent" if entry else
                              "alignment_broken_exit_intent" if exit_match else
                              "aligned_without_new_transition")
            signals.append(-1 if exit_match else 1 if entry else 0)
            previous_alignments.append(previous)
            ready.append(valid)
            alignments.append(alignment)
            entries.append(entry)
            exits.append(exit_match)
            reasons.append(reason)
            previous = alignment
        result["signal"] = signals
        result["rule_observation_ready"] = ready
        result["ma_alignment"] = pd.Series(alignments, index=result.index, dtype=object)
        result["previous_ma_alignment"] = pd.Series(previous_alignments, index=result.index, dtype=object)
        result["entry_rule_match"] = entries
        result["exit_rule_match"] = exits
        result["reason_tags"] = reasons
        result["regime_match"] = False
        result.attrs["rule_diagnostics"] = {
            "schema": DIAGNOSTICS_SCHEMA, "strategy_id": STRATEGY_ID, "strategy_version": STRATEGY_VERSION,
            "total_sessions": len(result), "ready_sessions": sum(ready),
            "unavailable_sessions": len(result) - sum(ready), "entry_signal_sessions": sum(entries),
            "exit_condition_sessions": sum(exits),
            "entry_description": "四均線由已知非排列轉嚴格多頭排列；首個已知排列與持續排列不重複進場",
            "exit_description": "四均線皆已知而排列破壞或相等時發出場意圖；缺件不造出場",
        }
        return result
