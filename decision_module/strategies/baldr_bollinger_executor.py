"""布林基礎突破研究：既有因果指標邊界，Decimal 比較，原撮合器執行。"""
from decimal import Decimal, DecimalException
from typing import Any

import pandas as pd

from analysis_module.technical_analysis.technical_indicators import calculate_causal_indicators
from analysis_module.technical_analysis.technical_date_support import safe_convert_technical_dates
from decision_module.strategies.baldr_bollinger_contract import (
    STRATEGY_ID, STRATEGY_VERSION, DIAGNOSTICS_SCHEMA,
    confirmation_sessions, rule_definition, strategy_metadata,
)
from decision_module.strategies.contracts import StrategySpec


def _price(value: Any) -> Decimal | None:
    try:
        number = Decimal(str(value))
        return number if number.is_finite() and number > 0 else None
    except (DecimalException, TypeError, ValueError):
        return None


class BaldrBollingerExecutor:
    @staticmethod
    def get_meta() -> dict[str, Any]:
        return strategy_metadata()

    def __init__(self, spec: StrategySpec) -> None:
        if (spec.strategy_id, spec.strategy_version) != (STRATEGY_ID, STRATEGY_VERSION):
            raise ValueError("布林基礎策略版本不符")
        self.spec = spec
        self.rules = rule_definition(spec.config.get("params", {}))

    def generate_signals(self, df: pd.DataFrame, spec: StrategySpec,
                         execution_start_date: str | None = None) -> pd.DataFrame:
        if spec.to_dict() != self.spec.to_dict():
            raise ValueError("布林基礎執行規格已變動")
        source = df.copy()
        if "日期" in source.columns:
            source.index = pd.DatetimeIndex(safe_convert_technical_dates(source["日期"]))
            source = source.drop(columns=["日期"])
        if (not isinstance(source.index, pd.DatetimeIndex) or source.index.hasnans
                or source.index.tz is not None or not source.index.is_monotonic_increasing
                or source.index.has_duplicates or not source.index.equals(source.index.normalize())):
            raise ValueError("布林研究須為無時區、唯一且依日遞增的日期索引")
        if not any(key in source for key in ("成交股數", "Volume", "volume")):
            raise ValueError("布林研究缺少原成交股數，不可假定成交可行")
        # 指標浮點數留在既有分析邊界；不採用來源內預存的同名 bands。
        result = calculate_causal_indicators(source)
        close_column = next((key for key in ("收盤價", "Close", "close") if key in result), None)
        if close_column is None:
            raise ValueError("缺少收盤價")
        count = confirmation_sessions(spec.config.get("params", {}))
        start = pd.Timestamp(execution_start_date) if execution_start_date is not None else None
        signals, ready, entries, exits, tags = [], [], [], [], []
        previous_close = previous_upper = None
        confirmation = 0
        for when, row in result.iterrows():
            close, upper, middle = (_price(row[key]) for key in (close_column, "upperband", "middleband"))
            valid = all(value is not None for value in (close, upper, middle))
            signal, entry, exit_match = 0, False, False
            reason = "warming_or_missing_ohlc"
            if close is not None and upper is not None and middle is not None:
                exit_match = close < middle
                if start is not None and when < start:
                    confirmation = 0
                    reason = "context_only_no_order"
                else:
                    cross = (previous_close is not None and previous_upper is not None
                             and previous_close <= previous_upper and close > upper)
                    confirmation = (1 if cross else confirmation + 1 if confirmation and close > upper else 0)
                    entry = confirmation == count
                    if entry:
                        confirmation = 0
                    signal = -1 if exit_match else 1 if entry else 0
                    reason = "below_middle_exit_intent" if exit_match else (
                        "upper_cross_confirmed_entry_intent" if entry else "rule_hold")
            else:
                confirmation = 0
            signals.append(signal); ready.append(valid); entries.append(entry); exits.append(exit_match)
            tags.append(reason)
            previous_close, previous_upper = (close, upper) if valid else (None, None)
        result["signal"] = signals
        result["rule_observation_ready"] = ready
        result["entry_rule_match"] = entries
        result["exit_rule_match"] = exits
        result["reason_tags"] = tags
        result["regime_match"] = False  # 未做市場狀態判斷，不補為匹配。
        result.attrs["rule_diagnostics"] = {
            "schema": DIAGNOSTICS_SCHEMA, "strategy_id": STRATEGY_ID, "strategy_version": STRATEGY_VERSION,
            "total_sessions": len(result), "ready_sessions": sum(ready),
            "unavailable_sessions": len(result) - sum(ready), "entry_signal_sessions": sum(entries),
            "exit_condition_sessions": sum(exits), "confirmation_sessions": count,
            "entry_description": "前列未高於上軌→當列高於上軌，連續確認後發進場意圖",
            "exit_description": "收盤低於中軌發出場意圖；等於中軌保持",
        }
        return result
