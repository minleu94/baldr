"""回測分析師診斷的 application/presentation boundary。

本模組只讀取已完成的回測報告或 legacy run payload，不重新抓取市場資料、
不改寫策略訊號，也不把缺少的欄位估算成零。所有金融數值先以 Decimal／整數
基點整理；只有 UI 自己需要格式化時才轉成文字。rolling 統計只取 trailing
equity history，故不會把決策日之後的資料帶回較早期間。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Mapping, Sequence, cast

import pandas as pd


ZERO = Decimal("0")
BP_SCALE = Decimal("10000")
TRADING_DAYS_PER_YEAR = Decimal("252")


def _decimal(value: object) -> Decimal | None:
    """在 analytics boundary 將既有 DTO 數值安全轉成 Decimal。"""

    if value is None or isinstance(value, bool):
        return None
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    if not result.is_finite():
        return None
    return result


def _bp(value: Decimal | None) -> int | None:
    if value is None:
        return None
    return int((value * BP_SCALE).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _ratio_bp(numerator: Decimal | None, denominator: Decimal | None) -> int | None:
    if numerator is None or denominator is None or denominator <= ZERO:
        return None
    return _bp(numerator / denominator)


def _text_bp(value: int | None) -> str:
    if value is None:
        return "未知"
    sign = "+" if value > 0 else ""
    return f"{sign}{value} bp"


@dataclass(frozen=True)
class AnalystDiagnosticsDTO:
    """供 Qt 呈現的不可變診斷快照。"""

    status: str
    reason: str | None
    kpis: Mapping[str, Any] = field(default_factory=dict)
    rolling: tuple[Mapping[str, Any], ...] = ()
    monthly: tuple[Mapping[str, Any], ...] = ()
    benchmark: Mapping[str, Any] = field(default_factory=dict)
    definitions: tuple[str, ...] = ()

    @classmethod
    def unknown(cls, reason: str) -> "AnalystDiagnosticsDTO":
        return cls(status="unknown", reason=reason)


def _empty_or_unknown(value: object, reason: str) -> tuple[pd.DataFrame | None, str | None]:
    if not isinstance(value, pd.DataFrame) or value.empty:
        return None, reason
    return value.copy(), None


def _normalise_equity_curve(value: object) -> pd.DataFrame | None:
    if not isinstance(value, pd.DataFrame) or value.empty:
        return None
    frame = value.copy()
    if "equity" not in frame.columns:
        return None
    try:
        index = pd.to_datetime(frame.index)
    except (TypeError, ValueError):
        return None
    frame.index = index
    frame = frame[~frame.index.duplicated(keep="last")].sort_index()
    return frame


def _series_decimal(frame: pd.DataFrame, column: str) -> list[Decimal]:
    values: list[Decimal] = []
    if column not in frame.columns:
        return values
    for value in frame[column].tolist():
        numeric = _decimal(value)
        if numeric is not None:
            values.append(numeric)
    return values


def _daily_returns(equity: Sequence[Decimal]) -> list[Decimal]:
    returns: list[Decimal] = []
    for previous, current in zip(equity, equity[1:]):
        if previous <= ZERO:
            continue
        returns.append((current / previous) - Decimal("1"))
    return returns


def _rolling_snapshot(equity: Sequence[Decimal], window: int) -> dict[str, Any]:
    # 僅使用最後 window+1 個觀測點；不使用任何 future slice。
    if len(equity) < window + 1:
        return {
            "window": window,
            "status": "unknown",
            "reason": f"需要至少 {window + 1} 筆權益觀測，實際 {len(equity)} 筆",
            "observation_count": max(len(equity) - 1, 0),
            "return_bp": None,
            "annualized_vol_bp": None,
        }
    trailing = list(equity[-(window + 1):])
    returns = _daily_returns(trailing)
    if not returns or trailing[0] <= ZERO:
        return {
            "window": window,
            "status": "unknown",
            "reason": "權益資料無法形成正數 trailing return",
            "observation_count": len(returns),
            "return_bp": None,
            "annualized_vol_bp": None,
        }
    mean = sum(returns, ZERO) / Decimal(len(returns))
    if len(returns) > 1:
        variance = sum(((item - mean) ** 2 for item in returns), ZERO) / Decimal(len(returns) - 1)
        volatility = variance.sqrt() * TRADING_DAYS_PER_YEAR.sqrt()
    else:
        volatility = None
    return {
        "window": window,
        "status": "available",
        "reason": None,
        "observation_count": len(returns),
        "return_bp": _bp((trailing[-1] / trailing[0]) - Decimal("1")),
        "annualized_vol_bp": _bp(volatility),
    }


def _monthly_rows(
    frame: pd.DataFrame,
    initial_capital: Decimal | None = None,
) -> tuple[Mapping[str, Any], ...]:
    if frame.empty or "equity" not in frame.columns:
        return ()
    rows: list[Mapping[str, Any]] = []
    month_end_values: list[tuple[Any, Decimal | None]] = []
    for period, group in frame.groupby(frame.index.to_period("M")):
        values = [_decimal(value) for value in group["equity"].tolist()]
        values = [value for value in values if value is not None and value > ZERO]
        month_end_values.append((period, values[-1] if values else None))

    previous_end = initial_capital if initial_capital is not None and initial_capital > ZERO else None
    last_valid_period_key: int | None = None
    for index, (period, current_end) in enumerate(month_end_values):
        period_key = int(period.year) * 12 + int(period.month)
        has_missing_period = (
            last_valid_period_key is not None
            and period_key != last_valid_period_key + 1
        )
        if has_missing_period:
            # 中間整月沒有有效觀測時，不能把跨缺口的累積報酬掛到目前月份。
            reason = "前一個有觀測月份與本月之間存在缺觀測月份；不合併為單月報酬"
            return_bp = None
            status = "unknown"
        elif current_end is None or previous_end is None or previous_end <= ZERO:
            reason = (
                "第一個月缺少明確 initial_capital／起始權益 anchor"
                if index == 0
                else "前一月末或本月末缺少正數權益觀測"
            )
            return_bp = None
            status = "unknown"
        else:
            return_bp = _bp((current_end / previous_end) - Decimal("1"))
            reason = None
            status = "available"
        rows.append({
            "year": int(period.year),
            "month": int(period.month),
            "status": status,
            "reason": reason,
            "return_bp": return_bp,
            "return_text": _text_bp(return_bp),
        })
        if current_end is not None and current_end > ZERO:
            previous_end = current_end
            last_valid_period_key = period_key
    return tuple(rows)


def _cost_snapshot(details: Mapping[str, Any], initial_capital: Decimal | None) -> dict[str, Any]:
    costs = details.get("transaction_costs")
    if not isinstance(costs, Mapping):
        return {
            "status": "unknown",
            "reason": "此 run 未保存 transaction_costs metadata",
            "fee_cents": None,
            "slippage_cents": None,
            "total_cents": None,
            "fee_bp": None,
            "slippage_bp": None,
            "total_bp": None,
        }
    fee_cents = costs.get("fee_cents")
    slippage_cents = costs.get("slippage_cents")
    total_cents = costs.get("total_cents")
    if not all(isinstance(item, int) for item in (fee_cents, slippage_cents, total_cents)):
        return {
            "status": "unknown",
            "reason": "transaction_costs metadata 欄位不完整",
            "fee_cents": None,
            "slippage_cents": None,
            "total_cents": None,
            "fee_bp": None,
            "slippage_bp": None,
            "total_bp": None,
        }
    fee_cents = cast(int, fee_cents)
    slippage_cents = cast(int, slippage_cents)
    total_cents = cast(int, total_cents)
    # 以整數分／初始資金的整數分計算 bp，避免把 UI 浮點帶回核心。
    capital_cents_value = None if initial_capital is None else int((initial_capital * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return {
        "status": "available",
        "reason": None,
        "fee_cents": fee_cents,
        "slippage_cents": slippage_cents,
        "total_cents": total_cents,
        "fee_bp": None if not capital_cents_value else int((Decimal(fee_cents) / Decimal(capital_cents_value) * BP_SCALE).quantize(Decimal("1"), rounding=ROUND_HALF_UP)),
        "slippage_bp": None if not capital_cents_value else int((Decimal(slippage_cents) / Decimal(capital_cents_value) * BP_SCALE).quantize(Decimal("1"), rounding=ROUND_HALF_UP)),
        "total_bp": None if not capital_cents_value else int((Decimal(total_cents) / Decimal(capital_cents_value) * BP_SCALE).quantize(Decimal("1"), rounding=ROUND_HALF_UP)),
        "capital_denominator": "初始資金（分）",
    }


def _benchmark_snapshot(
    report: Any,
    details: Mapping[str, Any],
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    comparison = getattr(report, "baseline_comparison", None)
    if not isinstance(comparison, Mapping):
        comparison = details.get("baseline_comparison")
    if not isinstance(comparison, Mapping):
        comparison = payload.get("baseline_comparison")
    if not isinstance(comparison, Mapping):
        nested = details.get("benchmark_results")
        comparison = nested.get("comparison") if isinstance(nested, Mapping) else None
    if not isinstance(comparison, Mapping):
        return {"status": "unknown", "reason": "既有 baseline_comparison 不存在；不重新抓取 benchmark"}
    strategy_return = getattr(report, "total_return", None) if report is not None else payload.get("total_return")
    strategy_sharpe = getattr(report, "sharpe_ratio", None) if report is not None else payload.get("sharpe_ratio")
    strategy_mdd = getattr(report, "max_drawdown", None) if report is not None else payload.get("max_drawdown")
    strategy_return = _decimal(strategy_return)
    strategy_sharpe = _decimal(strategy_sharpe)
    strategy_mdd = _decimal(strategy_mdd)
    comparison_strategy_return = _decimal(comparison.get("strategy_returns"))
    comparison_strategy_sharpe = _decimal(comparison.get("strategy_sharpe"))
    comparison_strategy_mdd = _decimal(comparison.get("strategy_max_drawdown"))
    if strategy_return is None:
        strategy_return = comparison_strategy_return
    if strategy_sharpe is None:
        strategy_sharpe = comparison_strategy_sharpe
    if strategy_mdd is None:
        strategy_mdd = comparison_strategy_mdd
    baseline_return = _decimal(comparison.get("baseline_returns"))
    baseline_sharpe = _decimal(comparison.get("baseline_sharpe"))
    baseline_mdd = _decimal(comparison.get("baseline_max_drawdown"))
    if all(value is None for value in (strategy_return, strategy_sharpe, strategy_mdd, baseline_return, baseline_sharpe, baseline_mdd)):
        return {"status": "unknown", "reason": "baseline_comparison 缺少可呈現的策略／benchmark 指標"}
    fields = {
        "strategy_return_bp": _bp(strategy_return),
        "benchmark_return_bp": _bp(baseline_return),
        "excess_return_bp": _bp(_decimal(comparison.get("excess_returns"))),
        "strategy_sharpe": strategy_sharpe,
        "benchmark_sharpe": baseline_sharpe,
        "sharpe_delta": _decimal(comparison.get("relative_sharpe")),
        "strategy_mdd_bp": _bp(strategy_mdd),
        "benchmark_mdd_bp": _bp(baseline_mdd),
        "mdd_delta_bp": _bp(_decimal(comparison.get("relative_drawdown"))),
    }
    return {"status": "available", "reason": None, **fields}


def build_backtest_analyst_diagnostics(
    report: Any | None = None,
    *,
    run_data: Mapping[str, Any] | None = None,
) -> AnalystDiagnosticsDTO:
    """從新報告或 legacy saved run 建立分析師診斷。

    `run_data` 只接受已保存 payload；缺少 equity／cost／benchmark 時，
    builder 會保留 unknown 與原因，不會回抓目前市場資料或臆測歷史欄位。
    """

    payload: Mapping[str, Any] = run_data or {}
    if report is not None:
        details = getattr(report, "details", {}) or {}
    else:
        details = payload.get("details", {})
    if not isinstance(details, Mapping):
        details = {}
    equity = _normalise_equity_curve(details.get("equity_curve", payload.get("equity_curve")))
    if equity is None:
        return AnalystDiagnosticsDTO.unknown("此 run 缺少可用 equity_curve；不補抓或重算歷史資料")

    initial_capital = _decimal(
        details.get(
            "initial_capital",
            payload.get(
                "initial_capital",
                payload.get("capital", details.get("start_equity", details.get("starting_equity"))),
            ),
        )
    )
    equity_values = _series_decimal(equity, "equity")
    kpis: dict[str, Any] = {}
    exposure = _series_decimal(equity, "position_value")
    equity_for_exposure = _series_decimal(equity, "equity")
    if exposure and len(exposure) == len(equity_for_exposure):
        exposure_bp = [ratio for value, total in zip(exposure, equity_for_exposure) if (ratio := _ratio_bp(value, total)) is not None]
        if exposure_bp:
            kpis["average_exposure_bp"] = int(sum(exposure_bp) / len(exposure_bp))
            kpis["peak_exposure_bp"] = max(exposure_bp)
            kpis["exposure_status"] = "available"
        else:
            kpis["average_exposure_bp"] = None
            kpis["peak_exposure_bp"] = None
            kpis["exposure_status"] = "unknown"
    else:
        kpis["average_exposure_bp"] = None
        kpis["peak_exposure_bp"] = None
        kpis["exposure_status"] = "unknown"
        kpis["exposure_reason"] = "equity_curve 缺少 position_value"

    cash = _series_decimal(equity, "cash")
    if cash and len(cash) == len(equity_for_exposure):
        usage_bp = [
            ratio
            for total, cash_value in zip(equity_for_exposure, cash)
            if (ratio := _ratio_bp(total - cash_value, total)) is not None
        ]
        kpis["average_cash_utilization_bp"] = int(sum(usage_bp) / len(usage_bp)) if usage_bp else None
        kpis["cash_utilization_status"] = "available" if usage_bp else "unknown"
    else:
        kpis["average_cash_utilization_bp"] = None
        kpis["cash_utilization_status"] = "unknown"
        kpis["cash_utilization_reason"] = "equity_curve 缺少 cash"

    costs = _cost_snapshot(details, initial_capital)
    execution = details.get("execution_summary")
    avg_equity = (sum(equity_values, ZERO) / Decimal(len(equity_values))) if equity_values else None
    traded_notional_cents = execution.get("gross_notional_cents") if isinstance(execution, Mapping) else None
    if isinstance(traded_notional_cents, int) and avg_equity is not None:
        avg_equity_cents = int((avg_equity * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        kpis["turnover_bp"] = None if avg_equity_cents <= 0 else int((Decimal(traded_notional_cents) / Decimal(avg_equity_cents) * BP_SCALE).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        kpis["turnover_status"] = "available"
        kpis["turnover_definition"] = "買賣成交金額總和 / 權益曲線平均權益"
    else:
        kpis["turnover_bp"] = None
        kpis["turnover_status"] = "unknown"
        kpis["turnover_reason"] = "缺少 execution_summary gross_notional_cents"
        kpis["turnover_definition"] = "買賣成交金額總和 / 權益曲線平均權益"
    kpis["transaction_costs"] = costs

    rolling = tuple(_rolling_snapshot(equity_values, window) for window in (20, 60))
    monthly = _monthly_rows(equity, initial_capital)
    benchmark = _benchmark_snapshot(report, details, payload)
    definitions = (
        "曝險＝position_value / equity；現金使用率＝(equity - cash) / equity，均以 bp 顯示。",
        "Turnover＝買賣成交金額總和 / 權益曲線平均權益；不是交易次數。",
        "成本 bp 以初始資金為分母；既有 Trade.fee 已包含賣出證交稅，UI 會標示為 fee／稅合計。",
        "Rolling 只使用截至目前資料的 trailing 20／60 個交易日；不是 OOS 或信賴區間。",
        "月度報酬採相鄰月末權益變化；第一個月只有在有明確 initial_capital／起始權益 anchor 時才計算，不以顏色代替數值。",
    )
    return AnalystDiagnosticsDTO(
        status="available",
        reason=None,
        kpis=kpis,
        rolling=rolling,
        monthly=monthly,
        benchmark=benchmark,
        definitions=definitions,
    )


__all__ = ["AnalystDiagnosticsDTO", "build_backtest_analyst_diagnostics"]
