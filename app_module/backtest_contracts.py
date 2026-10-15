"""回測服務使用的結構型輸入契約。"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from math import isfinite
from typing import Any, Dict, Mapping, Protocol

PROFIT_FACTOR_SEMANTICS = "closed-pair-net-pnl-ratio.v1"
_UNAVAILABLE_PF = {
    "no_closed_pairs", "unbounded_no_gross_loss", "undefined_zero_over_zero", "unavailable_nonfinite",
}


def profit_factor_projection(details: Mapping[str, Any]) -> dict[str, Any]:
    """只傳遞有語意版本的有限原值；不重算或改寫舊報告。"""
    version = details.get("profit_factor_semantics")
    status = details.get("profit_factor_status")
    result: dict[str, Any] = {
        "profit_factor": None, "profit_factor_status": "legacy_unversioned", "profit_factor_semantics": None,
    }
    if version != PROFIT_FACTOR_SEMANTICS:
        return result
    result["profit_factor_semantics"] = version
    value = details.get("profit_factor")
    if isinstance(status, str) and status in _UNAVAILABLE_PF and value is None:
        result["profit_factor_status"] = status
        return result
    result["profit_factor_status"] = "unavailable_nonfinite"
    if status != "observed" or isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        return result
    try:
        number = Decimal(str(value))
        if not number.is_finite() or number < 0:
            return result
        projected = float(number)  # numeric-boundary: dto
        if not isfinite(projected):
            return result
    except (InvalidOperation, ValueError, OverflowError):
        return result
    result.update(profit_factor=projected, profit_factor_status="observed")
    return result


class WalkForwardResultContract(Protocol):
    """BacktestService 計算過擬合風險所需的最小 Walk-forward 介面。"""

    train_metrics: Dict[str, Any]
    test_metrics: Dict[str, Any]
