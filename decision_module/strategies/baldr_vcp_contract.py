"""原P07的自有三段收縮研究假說；參數先固定，不宣稱標準VCP或有效績效。"""
from copy import deepcopy
from typing import Any

STRATEGY_ID = "baldr_vcp_three_contractions_v1"
STRATEGY_VERSION = "1.0.0"
PARAMETER_CONTRACT = "baldr-vcp-three-contractions.v1"
DIAGNOSTICS_SCHEMA = "baldr-vcp-three-contractions-diagnostics.v1"
PIVOT_SPAN = 2
MAX_BASE_ROWS = 60
MIN_BASE_ROWS = 15
MIN_READY_ROWS = 80


def rule_definition(params: Any) -> dict[str, Any]:
    if not isinstance(params, dict) or params:
        raise ValueError("三段收縮研究採固定規格，不接受額外參數")
    return {
        "schema": PARAMETER_CONTRACT, "strategy_id": STRATEGY_ID,
        "strategy_version": STRATEGY_VERSION,
        "parameter_origin": "root_predeclared_research_hypothesis_not_fitted_or_external_private_formula",
        "pivot": {"left_rows": PIVOT_SPAN, "right_confirmation_rows": PIVOT_SPAN,
                  "high": "strictly_above_all_other_highs_in_five_rows",
                  "low": "strictly_below_all_other_lows_in_five_rows",
                  "ambiguous_high_and_low": "ignore", "equal_extreme": "not_a_pivot",
                  "same_kind": "replace_only_with_more_extreme_confirmed_pivot"},
        "base": {"sequence": ["high", "low", "high", "low", "high", "low"],
                 "min_observed_rows": MIN_BASE_ROWS, "max_observed_rows": MAX_BASE_ROWS,
                 "minimum_high_to_low_distance": 2,
                 "highs": "nonincreasing", "lows": "strictly_increasing",
                 "depth": "(high-low)/high; strictly_decreasing_by_cross_multiplication",
                 "first_depth_max_bp": 3000, "last_depth_max_bp": 800,
                 "volume_dry": "last_pullback_mean < first_pullback_mean; endpoints_included",
                 "pivot_price": "maximum_of_three_confirmed_highs"},
        "entry": {"close": "previous_close <= pivot_price and close > pivot_price and close > SMA50",
                  "volume": "volume * 40 > sum_20_including_today * 3",
                  "emit": "once_per_six_pivot_identity_including_context_events"},
        "exit": {"condition": "close < SMA20", "equal": "hold", "priority": "exit_before_entry"},
        "moving_averages": "Decimal_SMA20_and_SMA50_on_contiguous_valid_observed_rows",
        "quantity_input": "original_integer_scalar_Decimal_or_string; finite_floating_quantity_rejected; NaN_is_missing",
        "warmup_rows": MIN_READY_ROWS,
        "missing": "official_empty_or_double_hyphen_or_NaN_resets_contiguous_windows_and_pivots_no_imputation",
        "numeric_text": "trim_whitespace_and_validate_thousands_groups_before_exact_Decimal_parse",
        "calendar_completeness": "unknown_observed_rows_are_not_verified_official_sessions",
        "execution": "next-session-open.v2", "pyramid": False,
        "holding": "rule_or_submitted_broker_risk_exit_no_forced_terminal_sale",
        "historical_pit_eligible": False, "performance_evaluable": False,
    }


def strategy_metadata() -> dict[str, Any]:
    return deepcopy({
        "strategy_id": STRATEGY_ID, "strategy_version": STRATEGY_VERSION,
        "name": "三段轉折收縮突破（研究）",
        "description": "左右各2列確認轉折；15至60列內三段跌幅遞減、低點抬高、末段均量低於首段；首次放量突破三峰且高於SMA50，跌破SMA20出場。自有固定假說，非通用VCP認證。",
        "regime": ["Breakout"], "risk_level": "high", "target_type": "stock", "params": {},
    })
