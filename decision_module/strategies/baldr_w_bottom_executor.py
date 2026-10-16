"""W底頸線研究執行器；只產生原Broker可消費的意圖，不假設成交。"""
from copy import deepcopy
from datetime import date
from typing import Any

import pandas as pd

from analysis_module.pattern_analysis.causal_w_bottom import observe_w_bottom, price_decimal
from analysis_module.technical_analysis.technical_date_support import safe_convert_technical_dates
from decision_module.strategies.baldr_w_bottom_contract import (
    STRATEGY_ID, STRATEGY_VERSION, DIAGNOSTICS_SCHEMA, rule_definition, strategy_metadata, wait_sessions,
)
from decision_module.strategies.contracts import StrategySpec


class BaldrWBottomExecutor:
    @staticmethod
    def get_meta() -> dict[str, Any]:
        return strategy_metadata()

    def __init__(self, spec: StrategySpec) -> None:
        if (spec.strategy_id, spec.strategy_version) != (STRATEGY_ID, STRATEGY_VERSION):
            raise ValueError("W底基礎策略版本不符")
        self._spec = deepcopy(spec.to_dict())
        self.rules = rule_definition(spec.config.get("params", {}))

    def generate_signals(self, df: pd.DataFrame, spec: StrategySpec,
                         execution_start_date: str | None = None) -> pd.DataFrame:
        if spec.to_dict() != self._spec:
            raise ValueError("W底基礎執行規格已變動")
        source = df.copy(deep=True)
        if "日期" in source:
            source.index = pd.DatetimeIndex(safe_convert_technical_dates(source["日期"]))
            source = source.drop(columns=["日期"])
        if (not isinstance(source.index, pd.DatetimeIndex) or source.index.hasnans
                or source.index.tz is not None or source.index.has_duplicates
                or not source.index.is_monotonic_increasing or not source.index.equals(source.index.normalize())):
            raise ValueError("W底研究須為無時區、唯一且依日遞增的日期索引")
        aliases = (("開盤價", "Open", "open"), ("最高價", "High", "high"),
                   ("最低價", "Low", "low"), ("收盤價", "Close", "close"))
        columns = [next((key for key in keys if key in source), None) for keys in aliases]
        if any(key is None for key in columns) or not any(key in source for key in ("成交股數", "Volume", "volume")):
            raise ValueError("W底研究缺少原OHLCV，不可假定行情或成交可行")
        prices = []
        for when, row in source.iterrows():
            values = [price_decimal(row[key]) for key in columns]
            opening, high, low, close = values
            if all(value is not None for value in values):
                assert opening is not None and high is not None and low is not None and close is not None
                if low > min(opening, close, high) or high < max(opening, close, low):
                    raise ValueError("W底研究OHLC高低矛盾")
            else:
                close = None
            prices.append((when.date(), close))
        start = date.fromisoformat(execution_start_date) if execution_start_date is not None else None
        observations = observe_w_bottom(prices, max_wait_sessions=wait_sessions(spec.config.get("params", {})), start=start)
        source["signal"] = [item.signal for item in observations]
        source["rule_observation_ready"] = [item.ready for item in observations]
        source["entry_rule_match"] = [item.signal == 1 for item in observations]
        source["exit_rule_match"] = [item.signal == -1 for item in observations]
        source["reason_tags"] = [item.reason for item in observations]
        source["pattern_state"] = [item.state for item in observations]
        for key in ("first_trough_at", "second_trough_at", "neckline_at", "confirmed_at", "first_trough", "second_trough", "neckline", "floor"):
            source["pattern_" + key] = [getattr(item.evidence, key) if item.evidence is not None else None for item in observations]
        source["regime_match"] = False
        source.attrs["rule_diagnostics"] = {
            "schema": DIAGNOSTICS_SCHEMA, "strategy_id": STRATEGY_ID, "strategy_version": STRATEGY_VERSION,
            "total_sessions": len(observations), "ready_sessions": sum(item.ready for item in observations),
            "unavailable_sessions": sum(not item.ready for item in observations),
            "entry_signal_sessions": sum(item.signal == 1 for item in observations),
            "exit_condition_sessions": sum(item.signal == -1 for item in observations),
            "max_wait_sessions": wait_sessions(spec.config.get("params", {})),
            "state_basis": "order_intent_episode_not_assumed_fills",
        }
        return source
