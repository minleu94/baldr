"""BacktestView 的純文字呈現規則。"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

import pandas as pd

from app_module.dtos import BacktestReportDTO, ValidationStatus
from ui_qt.status_vocabulary import status_detail


_PROFIT_FACTOR_SEMANTICS = "closed-pair-net-pnl-ratio.v1"
_PROFIT_FACTOR_STATUS_TEXT = {
    "no_closed_pairs": "未提供（無已完成配對）",
    "unbounded_no_gross_loss": "未提供（無虧損，沒有有限比率）",
    "undefined_zero_over_zero": "未提供（總獲利與虧損皆為零）",
    "unavailable_nonfinite": "未提供（非有限指標）",
}
_BOLLINGER_RULE_DIAGNOSTICS_SCHEMA = "baldr-bollinger-basic-diagnostics.v1"
_BOLLINGER_RULE_COUNT_LABELS = (
    ("total_sessions", "總觀測日數"),
    ("ready_sessions", "指標可用日數"),
    ("unavailable_sessions", "指標不可用日數"),
    ("entry_signal_sessions", "進場訊號日數"),
    ("exit_condition_sessions", "出場條件日數"),
    ("confirmation_sessions", "進場確認日數"),
)
_W_BOTTOM_RULE_DIAGNOSTICS_SCHEMA = "baldr-w-bottom-basic-diagnostics.v1"
_W_BOTTOM_RULE_DIAGNOSTICS_FIELDS = frozenset(
    {
        "schema",
        "strategy_id",
        "strategy_version",
        "total_sessions",
        "ready_sessions",
        "unavailable_sessions",
        "entry_signal_sessions",
        "exit_condition_sessions",
        "max_wait_sessions",
        "state_basis",
    }
)
_W_BOTTOM_RULE_COUNT_LABELS = (
    ("total_sessions", "總觀測列數"),
    ("ready_sessions", "規則可判讀列數"),
    ("unavailable_sessions", "不可判讀列數（含暖機、缺件與重啟）"),
    ("entry_signal_sessions", "進場意圖列數"),
    ("exit_condition_sessions", "出場意圖列數"),
)


def saved_backtest_number(value: object) -> Decimal | None:
    """舊保存欄位只在有有限數值時顯示；缺件不代入零。"""
    if type(value) not in (int, float, Decimal):
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return number if number.is_finite() else None


def saved_backtest_percent(value: object) -> Decimal | None:
    number = saved_backtest_number(value)
    return number * 100 if number is not None else None


def format_saved_backtest_summary(run_data: dict[str, Any]) -> str:
    """原 run 的缺欄、無法讀取明細及完成配對分別明示。"""
    def numeric_text(key: str, *, percent: bool = False) -> str:
        number = (
            saved_backtest_percent(run_data.get(key))
            if percent else saved_backtest_number(run_data.get(key))
        )
        return f"{number:.2f}{'%' if percent else ''}" if number is not None else "未提供"

    pair_count = run_data.get("total_trades")
    pair_count = pair_count if type(pair_count) is int and pair_count >= 0 else None
    trades = run_data.get("trade_list")
    detail_rows = len(trades) if isinstance(trades, pd.DataFrame) else None
    lines = [
        f"執行名稱: {run_data.get('run_name') or '未提供'}",
        f"股票代號: {run_data.get('stock_code') or '未提供'}",
        f"日期範圍: {run_data.get('start_date') or '未提供'} ~ {run_data.get('end_date') or '未提供'}",
        f"策略: {run_data.get('strategy_id') or '未提供'}",
        "",
        "=== 績效摘要 ===",
        f"總報酬率: {numeric_text('total_return', percent=True)}",
        f"年化報酬率: {numeric_text('annual_return', percent=True)}",
        f"夏普比率: {numeric_text('sharpe_ratio')}",
        f"最大回撤: {numeric_text('max_drawdown', percent=True)}",
        f"勝率: {numeric_text('win_rate', percent=True)}",
        f"總交易次數: {pair_count if pair_count is not None else '未提供'}（已完成進出場配對）",
        f"交易明細列數: {detail_rows if detail_rows is not None else '未提供（明細檔缺失或無法讀取）'}",
    ]
    if pair_count is not None and detail_rows is None and pair_count > 0:
        lines.append("⚠ 保存摘要有完成配對，但明細無法讀取；請核對原 run，勿把空表視為零交易。")
    elif pair_count is not None and detail_rows is not None and detail_rows != pair_count:
        lines.append("⚠ 保存摘要的完成配對數與明細列數不同；請核對原 run 與明細語意。")
    return "\n".join(lines)


def _bollinger_rule_diagnostics_lines(details: dict[str, Any]) -> list[str] | None:
    """只呈現已知版本的布林規則診斷；天數不代表成交或完成配對。"""
    diagnostics = details.get("rule_diagnostics")
    if (
        not isinstance(diagnostics, dict)
        or diagnostics.get("schema") != _BOLLINGER_RULE_DIAGNOSTICS_SCHEMA
    ):
        return None

    def count_text(key: str) -> str:
        value = diagnostics.get(key)
        return str(value) if type(value) is int and value >= 0 else "未提供"

    def description_text(key: str) -> str:
        value = diagnostics.get(key)
        return value if type(value) is str and value.strip() else "未提供"

    lines = ["", "--- 布林規則診斷 ---"]
    lines.extend(
        f"{label}: {count_text(key)} 天" for key, label in _BOLLINGER_RULE_COUNT_LABELS
    )
    lines.extend(
        [
            f"進場條件: {description_text('entry_description')}",
            f"出場條件: {description_text('exit_description')}",
            "以上日數表示條件或意圖，不代表成交或已完成進出場配對。",
        ]
    )
    return lines


def _w_bottom_rule_diagnostics_lines(details: dict[str, Any]) -> list[str] | None:
    """只呈現凍結版本的 W 底診斷；意圖狀態不代表成交或完成配對。"""
    diagnostics = details.get("rule_diagnostics")
    if (
        not isinstance(diagnostics, dict)
        or diagnostics.get("schema") != _W_BOTTOM_RULE_DIAGNOSTICS_SCHEMA
    ):
        return None

    identity_valid = (
        diagnostics.get("strategy_id") == "baldr_w_bottom_basic_v1"
        and diagnostics.get("strategy_version") == "1.0.0"
    )
    contract_shape_valid = set(diagnostics) == _W_BOTTOM_RULE_DIAGNOSTICS_FIELDS
    state_basis_valid = (
        diagnostics.get("state_basis") == "order_intent_episode_not_assumed_fills"
    )
    contract_valid = identity_valid and contract_shape_valid and state_basis_valid

    def count_text(key: str) -> str:
        value = diagnostics.get(key)
        if contract_valid and type(value) is int and value >= 0:
            return str(value)
        return "未提供"

    wait_value = diagnostics.get("max_wait_sessions")
    wait_text = (
        str(wait_value)
        if contract_valid and type(wait_value) is int and wait_value in (5, 10, 20)
        else "未提供"
    )

    lines = ["", "--- W 底規則診斷 ---"]
    if not contract_valid:
        lines.append("規則診斷不可用（欄位、身份或狀態基礎不符）。")
    lines.extend(
        f"{label}: {count_text(key)} 列"
        for key, label in _W_BOTTOM_RULE_COUNT_LABELS
    )
    lines.extend(
        [
            f"頸線突破等待上限: {wait_text} 列",
            "狀態基礎: 訊號意圖；不假設成交。"
            if contract_valid
            else "狀態基礎: 未提供。",
            "進出場意圖不代表成交，也不代表已完成配對。",
        ]
    )
    return lines


def _profit_factor_line(details: dict[str, Any]) -> str | None:
    """只呈現有版本的原始 PF 狀態，不從金額或交易明細回算。"""
    has_profit_factor_data = any(
        key in details
        for key in ("profit_factor", "profit_factor_semantics", "profit_factor_status")
    )
    if not has_profit_factor_data:
        return None

    status = details.get("profit_factor_status")
    if details.get("profit_factor_semantics") != _PROFIT_FACTOR_SEMANTICS:
        return "獲利因子：未驗證（舊保存值或語意版本未知）"
    if status == "observed":
        value = details.get("profit_factor")
        if type(value) is not float:
            return "獲利因子：未提供（觀測值無效）"
        try:
            numeric = Decimal(str(value))
        except (InvalidOperation, ValueError):
            return "獲利因子：未提供（觀測值無效）"
        if not numeric.is_finite() or numeric < 0:
            return "獲利因子：未提供（觀測值無效）"
        return f"獲利因子: {value:.2f}（無量綱）"

    status_text = _PROFIT_FACTOR_STATUS_TEXT.get(status) if type(status) is str else None
    if status_text is None:
        return "獲利因子：未驗證（舊保存值或狀態未知）"
    return f"獲利因子：{status_text}"


def build_portfolio_promotion_success_message(version_id: str, run_id: str) -> str:
    return (
        "推薦回放已升級為策略版本。\n\n"
        f"版本 ID: {version_id}\n"
        f"來源 run: {run_id}\n\n"
        "後續可到推薦分析的 Profile / 策略版本來源查看；"
        "若清單尚未更新，請重新整理或重新開啟推薦分析頁。"
    )


def choice_display_text(param_name: str, value: Any) -> str:
    value_text = str(value)
    display_map = {
        "threshold_mode": {
            "fixed": "固定門檻",
            "quantile": "百分位排名",
        },
        "quantile_method": {
            "nearest_rank": "最近名次法",
        },
    }
    return display_map.get(param_name, {}).get(value_text, value_text)


def format_backtest_summary(report: BacktestReportDTO) -> str:
    """格式化績效摘要，維持 Primary/SOP 指標優先順序。"""
    details = report.details
    actual_start = details.get("start_date", "未知")
    actual_end = details.get("end_date", "未知")
    requested_start = details.get("requested_start_date", actual_start)
    requested_end = details.get("requested_end_date", actual_end)
    lines = ["=== 績效摘要 ===", f"回測日期範圍: {actual_start} 至 {actual_end}"]
    if details.get("date_adjusted"):
        lines.append(
            f"注意: 請求範圍 {requested_start}~{requested_end} 已調整為實際數據範圍"
        )

    rule_diagnostics_lines = _bollinger_rule_diagnostics_lines(details)
    if rule_diagnostics_lines is None:
        rule_diagnostics_lines = _w_bottom_rule_diagnostics_lines(details)
    if rule_diagnostics_lines is not None:
        lines.extend(rule_diagnostics_lines)

    def score_text(value: Any) -> str:
        try:
            number = Decimal(str(value))
            return f"{number:.1f}" if number.is_finite() else "未提供"
        except (InvalidOperation, ValueError):
            return "未提供"

    score_diag = details.get("score_diagnostics")
    if rule_diagnostics_lines is None and isinstance(score_diag, dict) and score_diag:
        lines.extend(
            [
                "",
                "--- 策略分數診斷 (Scoring Diagnostics) ---",
                f"最高得分: {score_text(score_diag.get('max_score'))} | 最低得分: {score_text(score_diag.get('min_score'))} | 平均得分: {score_text(score_diag.get('avg_score'))}",
            ]
        )
        total_days = score_diag.get("total_days", 0)
        buy_hit_days = score_diag.get("buy_hit_days", 0)
        sell_hit_days = score_diag.get("sell_hit_days", 0)
        if score_diag.get("threshold_mode") == "quantile" and all(
            type(score_diag.get(key)) is int and score_diag[key] >= 0
            for key in ("warmup_ready_days", "total_days", "buy_hit_days", "sell_hit_days", "buy_quantile_bp", "sell_quantile_bp")
        ):
            ready_days = score_diag.get("warmup_ready_days", 0)
            buy_pct = buy_hit_days / ready_days * 100.0 if ready_days > 0 else 0.0
            sell_pct = sell_hit_days / ready_days * 100.0 if ready_days > 0 else 0.0
            buy_bp = score_diag.get("buy_quantile_bp", 8000)
            sell_bp = score_diag.get("sell_quantile_bp", 4000)
            lines.extend(
                [
                    f"門檻模式: 分位數 (暖機完成日數: {ready_days} 天 / 總日數: {total_days} 天)",
                    f"動態買進分位數 ({buy_bp/100:.1f}%) 命中天數: {buy_hit_days} 天 / 已暖機 {ready_days} 天 ({buy_pct:.1f}%)",
                    f"動態賣出分位數 ({sell_bp/100:.1f}%) 命中天數: {sell_hit_days} 天 / 已暖機 {ready_days} 天 ({sell_pct:.1f}%)",
                ]
            )
        elif score_diag.get("threshold_mode") == "fixed":
            buy_pct = buy_hit_days / total_days * 100.0 if total_days > 0 else 0.0
            sell_pct = sell_hit_days / total_days * 100.0 if total_days > 0 else 0.0
            lines.extend(
                [
                    f"買進門檻 ({score_text(score_diag.get('buy_score'))}) 命中天數: {buy_hit_days} 天 / {total_days} 天 ({buy_pct:.1f}%)",
                    f"賣出門檻 ({score_text(score_diag.get('sell_score'))}) 命中天數: {sell_hit_days} 天 / {total_days} 天 ({sell_pct:.1f}%)",
                ]
            )
        else:
            lines.append("門檻模式或觀測資料未提供，無法判讀命中情形。")

    lines.extend(
        [
            "",
            "╔════════════════════════════════════════╗",
            "║  Phase 3.5 SOP 驗證（必須優先查看）     ║",
            "╚════════════════════════════════════════╝",
        ]
    )
    status_text = {
        ValidationStatus.PASS: "[PASS]",
        ValidationStatus.WARNING: "[WARN]",
        ValidationStatus.FAIL: "[FAIL]",
    }.get(report.validation_status, "[UNKNOWN]")
    lines.append(f"驗證狀態: {status_text} {status_detail(report.validation_status, dimension='validation')}")
    if report.validation_messages:
        lines.append("")
        lines.extend(report.validation_messages)
    lines.extend(["", "--- Primary 指標（行為健康） ---", f"總交易次數: {report.total_trades}（已完成進出場配對）"])
    if report.total_trades == 0:
        lines.append("尚無已完成交易；配對數為 0 不代表沒有成交或期末沒有持股。")
    trade_list = details.get("trade_list")
    if isinstance(trade_list, pd.DataFrame) and len(trade_list) > 0 and "持有天數" in trade_list.columns:
        lines.append(f"平均持有天數: {trade_list['持有天數'].mean():.1f} 天")

    if report.baseline_comparison:
        lines.extend(["", "--- Baseline 對比 ---"])
        better_text = (
            "[PASS] 優於 Buy & Hold"
            if report.baseline_comparison.get("is_better", False)
            else "[FAIL] 不如 Buy & Hold"
        )
        lines.append(f"策略表現: {better_text}")
        if "excess_return" in report.baseline_comparison:
            lines.append(
                f"超額報酬率: {report.baseline_comparison['excess_return'] * 100:+.2f}%"
            )
    if report.overfitting_risk:
        lines.extend(["", "--- 穩健性（過擬合風險） ---"])
        risk_level = report.overfitting_risk.get("risk_level", "unknown")
        risk_token = {"low": "[LOW]", "medium": "[MEDIUM]", "high": "[HIGH]"}.get(
            risk_level, "[UNKNOWN]"
        )
        lines.append(f"過擬合風險等級: {risk_token} {risk_level.upper()}")
        degradation = report.overfitting_risk.get("degradation")
        if degradation is not None:
            lines.append(f"退化程度: {degradation * 100:.1f}%")

    lines.extend(
        [
            "",
            "╔════════════════════════════════════════╗",
            "║  Secondary 指標（輔助參考）            ║",
            "╚════════════════════════════════════════╝",
            "",
            f"總報酬率: {report.total_return * 100:.2f}%",
            f"年化報酬率 (CAGR): {report.annual_return * 100:.2f}%",
            f"夏普比率: {report.sharpe_ratio:.2f}",
            f"最大回撤: {report.max_drawdown * 100:.2f}%",
            f"勝率: {report.win_rate * 100:.2f}%",
            f"期望值: {report.expectancy * 100:.2f}%",
            "",
            "=== 詳細統計 ===",
        ]
    )
    detail_formats = (
        ("avg_win", "平均獲利: ${:.2f}"),
        ("avg_loss", "平均虧損: ${:.2f}"),
        ("largest_win", "最大獲利: ${:.2f}"),
        ("largest_loss", "最大虧損: ${:.2f}"),
        ("final_equity", "最終權益: ${:,.2f}"),
    )
    profit_factor_line = _profit_factor_line(details)
    if profit_factor_line is not None:
        lines.append(profit_factor_line)
    for key, template in detail_formats:
        if key in details:
            value = details[key]
            label = template.partition("{")[0].removesuffix("$")
            if value is None:
                lines.append(f"{label}未提供")
                continue
            try:
                lines.append(template.format(value))
            except (TypeError, ValueError):
                lines.append(f"{label}未提供")
    if "error" in details:
        lines.append(f"\n錯誤: {details['error']}")
    return "\n".join(lines)
