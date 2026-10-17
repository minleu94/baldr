"""原P07布林進階的固定研究假說；不授有效績效或歷史PIT資格。"""
from copy import deepcopy
from typing import Any

STRATEGY_ID = "baldr_bollinger_squeeze_v1"
STRATEGY_VERSION = "1.0.0"
PARAMETER_CONTRACT = "baldr-bollinger-squeeze.v1"
EXECUTION_SCHEMA = "single-backtest-bollinger-squeeze-execution.v1"
DIAGNOSTICS_SCHEMA = "baldr-bollinger-squeeze-diagnostics.v1"


def rule_definition(params: Any) -> dict[str, Any]:
    if not isinstance(params, dict) or params:
        raise ValueError("布林帶寬低點突破採固定研究規格，不接受額外參數")
    return {
        "schema": PARAMETER_CONTRACT,
        "strategy_id": STRATEGY_ID, "strategy_version": STRATEGY_VERSION,
        "indicator": {"implementation": "calculate_causal_indicators", "period": 30,
                      "standard_deviations": "2", "middle": "SMA",
                      "warmup": "continuous_valid_ohlc"},
        "contraction": {"width": "(upper - lower) / middle", "window": 20,
                        "condition": "width <= minimum_20_including_observed_session",
                        "zero_width": "known", "entry_uses": "previous_session_only"},
        "entry": {"cross": "previous_close <= previous_upper and close > upper",
                  "setup": "previous_squeeze_is_true",
                  "volume": "volume * 20 * 2 > sum_20_including_today * 3",
                  "volume_window": 20, "volume_multiple": "1.5", "emit": "once_at_cross"},
        "exit": {"condition": "close < middle", "equal_middle": "hold"},
        "state": "order_intents_only_not_assumed_fills",
        "missing": "no_signal_rewarm_affected_contiguous_windows_no_imputation",
        "execution": "next-session-open.v2", "pyramid": False,
        "holding": "until_rule_or_submitted_broker_risk_exit_no_forced_terminal_sale",
        "historical_pit_eligible": False, "performance_evaluable": False,
    }


def strategy_metadata() -> dict[str, Any]:
    return deepcopy({
        "strategy_id": STRATEGY_ID, "strategy_version": STRATEGY_VERSION,
        "name": "布林帶寬低點突破（研究）",
        "description": "前一交易列BBANDS30帶寬位於含自身20列最低，當列首次突破上軌且20日含當日均量比嚴格大於1.5；跌破中軌出場。固定自有研究假說，非VCP，未驗有效性或歷史PIT。",
        "regime": ["Breakout"], "risk_level": "high", "target_type": "stock", "params": {},
    })
