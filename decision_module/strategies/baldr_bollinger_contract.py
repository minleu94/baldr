"""布林基礎研究策略的版本化規格；不計算指標或授予研究資格。"""
from copy import deepcopy
from typing import Any

STRATEGY_ID = "baldr_bollinger_basic_v1"
STRATEGY_VERSION = "1.0.0"
PARAMETER_CONTRACT = "baldr-bollinger-basic.v1"
EXECUTION_SCHEMA = "single-backtest-bollinger-execution.v1"
DIAGNOSTICS_SCHEMA = "baldr-bollinger-basic-diagnostics.v1"


def confirmation_sessions(params: Any) -> int:
    if not isinstance(params, dict) or set(params) - {"entry_confirm_sessions"}:
        raise ValueError("布林基礎只接受 entry_confirm_sessions，不能套用分數門檻或其他參數")
    value = params.get("entry_confirm_sessions", 1)
    if type(value) is int and value in (1, 2, 3):
        return value
    if type(value) is str and value in ("1", "2", "3"):
        return int(value)
    raise ValueError("布林突破確認須為 1、2 或 3 個交易列")


def rule_definition(params: Any) -> dict[str, Any]:
    return {
        "schema": PARAMETER_CONTRACT,
        "strategy_id": STRATEGY_ID, "strategy_version": STRATEGY_VERSION,
        "indicator": {"implementation": "calculate_causal_indicators", "period": 30,
                      "standard_deviations": "2", "middle": "SMA", "warmup": "continuous_valid_ohlc"},
        "entry": {"cross": "previous_close <= previous_upper and close > upper",
                  "confirmation_sessions": confirmation_sessions(params),
                  "continuation": "close > each_session_upper", "emit": "once_at_confirmation"},
        "exit": {"condition": "close < middle", "equal_middle": "hold"},
        "state": "order_intents_only_not_assumed_fills",
        "missing": "no_signal_and_reset_entry_confirmation_rewarm_indicators",
        "execution": "next-session-open.v2", "pyramid": False,
        "holding": "until_rule_or_submitted_broker_risk_exit_no_forced_terminal_sale",
        "historical_pit_eligible": False, "performance_evaluable": False,
    }


def strategy_metadata() -> dict[str, Any]:
    return deepcopy({
        "strategy_id": STRATEGY_ID, "strategy_version": STRATEGY_VERSION,
        "name": "布林基礎突破（研究）",
        "description": "BBANDS30／2倍SMA首次向上突破；連續確認後下一有效開盤進場，收盤跌破中軌後下一有效開盤出場。自有研究假說，非壓縮策略；暖機／缺件不補值，未驗有效性或歷史PIT。",
        "regime": ["Trend", "Breakout"], "risk_level": "high", "target_type": "stock",
        "params": {"entry_confirm_sessions": {
            "type": "choice", "default": 1, "choices": [1, 2, 3],
            "description": "突破連續確認交易列（1／2／3）"}},
    })
