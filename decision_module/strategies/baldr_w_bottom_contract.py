"""W底基礎研究假說的固定規格；不授權來源、績效或正式晉升。"""
from copy import deepcopy
from typing import Any

STRATEGY_ID = "baldr_w_bottom_basic_v1"
STRATEGY_VERSION = "1.0.0"
PARAMETER_CONTRACT = "baldr-w-bottom-basic.v1"
DIAGNOSTICS_SCHEMA = "baldr-w-bottom-basic-diagnostics.v1"


def wait_sessions(params: Any) -> int:
    if not isinstance(params, dict) or set(params) - {"max_wait_sessions"}:
        raise ValueError("W底基礎只接受 max_wait_sessions")
    value = params.get("max_wait_sessions", 20)
    if type(value) is int and value in (5, 10, 20):
        return value
    if type(value) is str and value in ("5", "10", "20"):
        return int(value)
    raise ValueError("W底突破等待須為 5、10 或 20 個觀測列")


def rule_definition(params: Any) -> dict[str, Any]:
    return {
        "schema": PARAMETER_CONTRACT, "strategy_id": STRATEGY_ID,
        "strategy_version": STRATEGY_VERSION,
        "trough": {"method": "strict_three_close_local_minimum", "right_confirmation_rows": 1,
                   "separation_rows": [3, 20], "consecutive_confirmed_troughs_only": True,
                   "predecline": "first_trough_prior_3_sum * 2 > next_2_sum * 3",
                   "predecline_required_rows": 5},
        "geometry": {"tolerance": "abs(first - second) * 10000 <= first * 500",
                     "neckline": "max_close_strictly_between_troughs_earliest_tie",
                     "height": "neckline * 10000 > each_trough * 10100"},
        "entry": {"condition": "previous_close <= frozen_neckline and close > frozen_neckline",
                  "earliest": "second_trough_confirmation_close", "emit": "once_per_intent_episode",
                  "max_wait_sessions": wait_sessions(params), "equal_deadline": "allowed"},
        "invalidation": {"condition": "close < min_trough or rows_since_confirmation > max_wait_sessions",
                         "priority": "before_new_geometry_and_entry", "on_invalidated_row": "restart_geometry_only"},
        "exit": {"condition": "close < entry_episode_frozen_neckline", "equal_neckline": "hold",
                 "reentry": "after_exit_intent_and_new_complete_geometry"},
        "missing": "clear_geometry_and_unentered_candidate_keep_existing_intent_episode_no_signal",
        "test_start": "reset_all_geometry_candidate_and_intent_episode",
        "state": "order_intent_episode_not_assumed_fills",
        "execution": "next-session-open.v2", "pyramid": False,
        "holding": "until_neckline_failure_or_submitted_broker_risk_no_forced_terminal_sale",
        "historical_pit_eligible": False, "performance_evaluable": False,
    }


def strategy_metadata() -> dict[str, Any]:
    return deepcopy({
        "strategy_id": STRATEGY_ID, "strategy_version": STRATEGY_VERSION,
        "name": "W底頸線突破（研究）",
        "description": "收盤價三點谷於右一列確認；相鄰雙谷合格後突破凍結頸線，跌回頸線出場。自有研究假說，非舊全段形態辨識；不授有效性或歷史PIT。",
        "regime": ["Breakout"], "risk_level": "high", "target_type": "stock",
        "params": {"max_wait_sessions": {"type": "choice", "default": 20, "choices": [5, 10, 20],
                                        "description": "第二谷確認後最多等待觀測列（5／10／20）"}},
    })
