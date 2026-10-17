"""沿原F02定義的四均線多頭排列研究規格；不授投資有效性。"""
from copy import deepcopy
from typing import Any

STRATEGY_ID = "baldr_ma_alignment_basic_v1"
STRATEGY_VERSION = "1.0.0"
PARAMETER_CONTRACT = "baldr-ma-alignment-basic.v1"
EXECUTION_SCHEMA = "single-backtest-ma-alignment-execution.v1"
DIAGNOSTICS_SCHEMA = "baldr-ma-alignment-basic-diagnostics.v1"
PERIODS = (5, 10, 20, 60)
MAX_PRIOR_ROWS = 61


def rule_definition(params: Any) -> dict[str, Any]:
    if not isinstance(params, dict) or params:
        raise ValueError("四均線基礎使用固定5／10／20／60期，不接受分數門檻或其他參數")
    return {
        "schema": PARAMETER_CONTRACT, "strategy_id": STRATEGY_ID,
        "strategy_version": STRATEGY_VERSION,
        "indicator": {"implementation": "calculate_causal_indicators", "kind": "SMA",
                      "periods": list(PERIODS), "warmup": "60_continuous_valid_ohlc_observations"},
        "entry": {"condition": "previous_alignment is false and current_alignment is true",
                  "alignment": "MA5 > MA10 > MA20 > MA60", "emit": "once_at_transition",
                  "unknown_previous": "no_entry", "equal": "not_aligned"},
        "exit": {"condition": "all_four_ma_known_and_not_strictly_aligned", "equal": "exit_intent"},
        "state": "order_intents_only_not_assumed_fills",
        "missing": "no_order_and_reset_previous_alignment_rewarm_indicators",
        "execution": "next-session-open.v2", "pyramid": False,
        "holding": "until_rule_or_submitted_broker_risk_exit_no_forced_terminal_sale",
        "calendar_completeness": "unknown_observed_rows_not_official_session_proof",
        "historical_pit_eligible": False, "performance_evaluable": False,
    }


def strategy_metadata() -> dict[str, Any]:
    return deepcopy({
        "strategy_id": STRATEGY_ID, "strategy_version": STRATEGY_VERSION,
        "name": "四均線多頭排列（研究）",
        "description": "MA5>MA10>MA20>MA60由不成立轉成立發進場意圖；排列破壞或相等發出場意圖，沿下一有效開盤撮合。固定觀測期、缺件重暖機的自有研究假說，不是均線斜率或金叉策略；未驗有效性及歷史PIT。",
        "regime": ["Trend"], "risk_level": "high", "target_type": "stock", "params": {},
    })
