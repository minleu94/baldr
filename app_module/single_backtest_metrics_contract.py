"""原單股引擎已保存指標的版本與有效性；只投影，不重算或授績效資格。"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from typing import Any, Mapping, TypedDict

import pandas as pd

from app_module.research_run_dtos import canonical_json
from app_module.research_run_dated_equity import research_run_dated_equity_copy, _validated_daily_date_keys
from backtest_module.performance_metrics import PerformanceMetrics

SINGLE_BACKTEST_METRICS_KEY = "single_backtest_metrics_contract"
SINGLE_BACKTEST_METRICS_SCHEMA = "single-backtest-performance.v1"
SINGLE_BACKTEST_METRIC_NAMES = (
    "total_return", "annual_return", "sharpe_ratio", "max_drawdown", "win_rate", "total_trades", "expectancy",
)
_PRODUCER = "backtest_module.performance_metrics.PerformanceAnalyzer.summarize"
_PRECISION = "original_analytics_numeric_boundary_not_decimal_core_or_performance_qualification"
_KEYS = {"schema_version", "producer", "precision_basis", "metrics_sha256", "metric_status", "stock_code", "contract_sha256",
         "equity_rows", "closed_pairs", "period_start", "period_end", "unit"}


class SingleBacktestMetricsProjection(TypedDict):
    stock_count: int | None
    signal_count: int | None
    completed_trades: int | None
    average_trade_return: Decimal | None
    total_return: Decimal | None
    annual_return: Decimal | None
    cagr: Decimal | None
    max_drawdown: Decimal | None
    win_rate: Decimal | None
    sharpe_ratio: Decimal | None
    expectancy: Decimal | None
    profit_factor: Decimal | None


def _decimal(value: object) -> Decimal:
    # 僅讀原 analytics/DTO 數值並轉展示文字，不回流策略或新增浮點運算。
    if isinstance(value, bool) or not isinstance(value, (Decimal, int, float, str)):
        raise ValueError("保存指標不是有限數值")
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("保存指標不是十進位數值") from exc
    if not result.is_finite():
        raise ValueError("保存指標含非有限數值")
    return result


def _metrics_hash(metrics: Mapping[str, Any]) -> str:
    if set(metrics) != set(SINGLE_BACKTEST_METRIC_NAMES):
        raise ValueError("原單股指標欄位不符")
    canonical_values: dict[str, Any] = {}
    for name, value in metrics.items():
        if name == "total_trades":
            if type(value) is not int or value < 0:
                raise ValueError("已完成交易配對必須是非負整數")
            canonical_values[name] = value
        else:
            # UI 的 JSON 數字以 Decimal 解碼；兩邊固定同一十進位值文字。
            canonical_values[name] = str(_decimal(value))
    return sha256(canonical_json(canonical_values).encode("utf-8")).hexdigest()


def capture_single_backtest_metrics_contract(
    metrics: PerformanceMetrics, *, equity: pd.DataFrame, trades: pd.DataFrame, stock_code: str,
) -> dict[str, Any]:
    """只由原引擎新結果發行；舊 run 不補版本或重算。"""
    if type(metrics) is not PerformanceMetrics or not isinstance(equity, pd.DataFrame) or not isinstance(trades, pd.DataFrame):
        raise ValueError("需要原引擎指標與同份權益／已配對交易表")
    raw = {key: getattr(metrics, key) for key in SINGLE_BACKTEST_METRIC_NAMES}
    digest = _metrics_hash(raw)
    if not stock_code or stock_code != stock_code.strip() or metrics.total_trades != len(trades):
        raise ValueError("單股身份／已完成配對筆數與原表不符")
    if not trades.empty and not {"進場日期", "出場日期", "報酬", "報酬率%", "股數"}.issubset(trades.columns):
        raise ValueError("單股已完成交易需使用原配對表，不接受成交事件筆數")
    status = dict(metrics.metric_status)
    if set(status) != set(SINGLE_BACKTEST_METRIC_NAMES) or any(value not in {"observed", "unavailable"} for value in status.values()):
        raise ValueError("原引擎缺逐指標有效性，不能升級舊零值")
    start = end = ""
    curve_valid = isinstance(equity.index, pd.DatetimeIndex) and not equity.empty and "equity" in equity
    if curve_valid:
        curve_valid = (not equity.index.hasnans and equity.index.is_monotonic_increasing and equity.index.is_unique)
        try:
            values = tuple(_decimal(value) for value in equity["equity"])
            curve_valid = curve_valid and all(value > 0 for value in values)
        except ValueError:
            curve_valid = False
    if curve_valid:
        start, end = equity.index[0].date().isoformat(), equity.index[-1].date().isoformat()
    else:
        for key in ("total_return", "annual_return", "sharpe_ratio", "max_drawdown"):
            status[key] = "unavailable"
    if not start or start == end:
        status["annual_return"] = "unavailable"
    if metrics.total_trades == 0:
        status["win_rate"] = status["expectancy"] = "unavailable"
    contract = {"schema_version": SINGLE_BACKTEST_METRICS_SCHEMA, "producer": _PRODUCER, "precision_basis": _PRECISION,
            "metrics_sha256": digest, "metric_status": status, "stock_code": stock_code,
            "equity_rows": len(equity), "closed_pairs": len(trades), "period_start": start, "period_end": end,
            "unit": "ratio_except_total_trades_count_and_sharpe_ratio"}
    contract["contract_sha256"] = sha256(canonical_json(contract).encode("utf-8")).hexdigest()
    return contract


def decode_single_backtest_metrics_contract(
    manifest: Mapping[str, Any], metrics: Mapping[str, Any], *, run_type: str, universe: object,
) -> SingleBacktestMetricsProjection | None:
    """None 表示原版缺 schema；已宣告但矛盾則拒絕，不降格洗掉錯誤。"""
    if SINGLE_BACKTEST_METRICS_KEY not in manifest:
        return None
    source = manifest[SINGLE_BACKTEST_METRICS_KEY]
    if (not isinstance(source, dict) or set(source) != _KEYS or run_type != "single_backtest"
            or source.get("schema_version") != SINGLE_BACKTEST_METRICS_SCHEMA or source.get("producer") != _PRODUCER
            or source.get("precision_basis") != _PRECISION or source.get("metrics_sha256") != _metrics_hash(metrics)
            or source.get("unit") != "ratio_except_total_trades_count_and_sharpe_ratio"
            or type(source.get("equity_rows")) is not int or source["equity_rows"] < 0
            or type(source.get("closed_pairs")) is not int or source["closed_pairs"] != metrics["total_trades"]
            or type(source.get("stock_code")) is not str or not 1 <= len(source["stock_code"]) <= 20
            or source["stock_code"] != source["stock_code"].strip() or universe != [source["stock_code"]]):
        raise ValueError("保存指標版本／原值／單股身份不符")
    signed_fields = {key: value for key, value in source.items() if key != "contract_sha256"}
    if source["contract_sha256"] != sha256(canonical_json(signed_fields).encode("utf-8")).hexdigest():
        raise ValueError("保存指標有效性／期間／來源契約SHA不符")
    status = source.get("metric_status")
    if (not isinstance(status, dict) or set(status) != set(SINGLE_BACKTEST_METRIC_NAMES)
            or any(value not in {"observed", "unavailable"} for value in status.values())):
        raise ValueError("保存指標逐項有效性不符")
    if status["total_trades"] != "observed":
        raise ValueError("保存配對筆數缺有效性")
    start, end = source["period_start"], source["period_end"]
    if type(start) is not str or type(end) is not str:
        raise ValueError("保存權益期間格式不符")
    if start or end:
        if (date.fromisoformat(start).isoformat() != start or date.fromisoformat(end).isoformat() != end
                or date.fromisoformat(start) > date.fromisoformat(end) or source["equity_rows"] < 1):
            raise ValueError("保存權益期間倒退或缺列")
    elif any(status[key] == "observed" for key in ("total_return", "annual_return", "sharpe_ratio", "max_drawdown")):
        raise ValueError("未提供權益期間不能宣告曲線指標")
    if start == end and status["annual_return"] == "observed":
        raise ValueError("沒有正期間不能宣告CAGR")
    values = {key: _decimal(value) if status[key] == "observed" else None for key, value in metrics.items() if key != "total_trades"}
    if metrics["total_trades"] == 0 and any(values[key] is not None for key in ("win_rate", "expectancy")):
        raise ValueError("零完成配對不能宣告勝率或平均配對報酬")
    if values["win_rate"] is not None and not Decimal("0") <= values["win_rate"] <= Decimal("1"):
        raise ValueError("勝率ratio範圍不符")
    return {"stock_count": 1, "signal_count": None, "completed_trades": metrics["total_trades"],
            "average_trade_return": values["expectancy"], "total_return": values["total_return"],
            "annual_return": values["annual_return"], "cagr": values["annual_return"],
            "max_drawdown": values["max_drawdown"], "win_rate": values["win_rate"],
            "sharpe_ratio": values["sharpe_ratio"], "expectancy": values["expectancy"], "profit_factor": None}


def validate_single_backtest_metrics_tables(manifest: Mapping[str, Any], *, equity: pd.DataFrame, trades: pd.DataFrame) -> None:
    """原 public reader 已核 Parquet SHA 後，再核所宣告的來源表與實際日期。"""
    source = manifest[SINGLE_BACKTEST_METRICS_KEY]
    if source["equity_rows"] != len(equity) or source["closed_pairs"] != len(trades):
        raise ValueError("保存指標與原表列數不符")
    if not trades.empty and not {"進場日期", "出場日期", "報酬", "報酬率%", "股數"}.issubset(trades.columns):
        raise ValueError("保存指標的交易來源不是原完成配對表")
    if source["period_start"]:
        copied = research_run_dated_equity_copy(equity)
        column = "date" if "date" in copied else "日期"
        keys = _validated_daily_date_keys(copied[column].tolist(), source="保存指標實際日期")
        if (date(*keys[0]).isoformat() != source["period_start"] or date(*keys[-1]).isoformat() != source["period_end"]
                or "equity" not in copied or any(_decimal(value) <= 0 for value in copied["equity"])):
            raise ValueError("保存指標的權益期間／原值與原表不符")
