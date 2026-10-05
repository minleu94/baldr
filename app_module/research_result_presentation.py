"""Research Lab 結果呈現與可靠度提示 helper。

本模組只整理已產生的結果 DTO / dict 成為 UI 可讀文案，不重跑回測、
不重新抓取資料，也不改變任何交易或績效計算。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
import json
from typing import Any


@dataclass(frozen=True)
class ReliabilityNotice:
    """Train-Test / Walk-forward 結果可靠度提示。"""

    level: str
    message: str
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ResearchTablePresentation:
    """研究頁面小表格的可讀文字與對應 tooltip。"""

    rows: tuple[tuple[str, ...], ...] = ()
    tooltips: tuple[tuple[str, ...], ...] = ()
    details: tuple[str, ...] = ()
    note: str = ""


_SHAREHOLDING_TIER_LABELS = {
    1: "1–999 股",
    2: "1,000–5,000 股",
    3: "5,001–10,000 股",
    4: "10,001–15,000 股",
    5: "15,001–20,000 股",
    6: "20,001–30,000 股",
    7: "30,001–40,000 股",
    8: "40,001–50,000 股",
    9: "50,001–100,000 股",
    10: "100,001–200,000 股",
    11: "200,001–400,000 股",
    12: "400,001–600,000 股",
    13: "600,001–800,000 股",
    14: "800,001–1,000,000 股",
    15: "1,000,001 股以上",
    16: "差異數調整",
    17: "合計",
}

_EVENT_TYPE_LABELS = {
    "watchlist_trigger": "觀察清單觸發",
    "watchlist_trigger_added": "觀察清單新增提醒",
    "watchlist_trigger_removed": "觀察清單移除提醒",
    "watchlist_trigger_strength_up": "觀察清單轉強提醒",
    "watchlist_trigger_strength_down": "觀察清單轉弱提醒",
    "watchlist_trigger_risk_alert": "觀察清單風險提醒",
    "recommendation_included": "推薦結果納入",
    "screening_matrix_pass": "篩選通過",
    "screening_matrix_fail": "篩選未通過",
    "screening_matrix_degraded": "篩選資料降級",
    "screening_matrix_skipped": "篩選略過",
    "screening_matrix_missing": "篩選資料缺漏",
    "why_not_excluded": "未採用原因",
    "liquidity_gate_excluded": "流動性門檻排除",
    "portfolio_alert": "持倉警示",
    "portfolio_alert_condition_warning": "持倉條件提醒",
    "portfolio_alert_condition_invalid": "持倉條件無效",
    "portfolio_alert_chip_risk": "持倉籌碼風險",
    "portfolio_alert_data_quality": "持倉資料品質提醒",
    "portfolio_alert:condition_warning": "持倉條件提醒",
    "portfolio_alert:condition_invalid": "持倉條件已失效",
    "portfolio_alert:chip_risk": "持倉籌碼風險",
    "risk_prompt_low_liquidity": "流動性風險提示",
    "risk_prompt_relative_weakness": "相對弱勢提示",
    "risk_prompt_fundamental_diagnostic": "基本面診斷提示",
    "risk_prompt_data_quality": "資料品質提示",
    "strategy_lifecycle": "策略生命週期事件",
}

_SOURCE_LABELS = {
    "daily_decision_desk_portfolio_alert": "每日決策台",
    "daily_decision_desk.portfolio_alert": "每日決策台",
    "daily_decision_desk.risk_prompt": "每日決策台風險提示",
    "portfolio_alert": "持倉警示服務",
    "portfolio-alert": "持倉警示服務",
    "watchlist": "觀察清單",
    "recommendation": "推薦結果",
    "recommendation_result": "推薦結果",
    "screening_matrix": "篩選矩陣",
    "risk_prompt": "風險提示",
}

_REASON_LABELS = {
    "condition:warning": "持倉條件出現提醒，需複核",
    "condition:invalid": "持倉條件已失效",
    "condition:valid": "持倉條件目前有效",
    "portfolio_alert_condition_warning": "持倉條件出現提醒",
    "portfolio_alert_condition_invalid": "持倉條件已失效",
    "portfolio_alert:condition_warning": "持倉條件出現提醒",
    "portfolio_alert:condition_invalid": "持倉條件已失效",
    "chip:risk_level:bearish": "籌碼風險偏弱",
    "chip:risk_level:extreme": "籌碼風險偏高",
    "chip:risk_level:risk": "籌碼有風險訊號",
    "chip:risk_level:error": "籌碼風險資料讀取失敗",
    "chip:estimated": "籌碼資料為估算",
    "portfolio_alert_unreviewed": "持倉警示尚未完成人工複核",
    "market_data_missing": "缺少市場資料",
    "condition_data_missing": "缺少條件／Advice 資料",
}

_QUALITY_LABELS = {
    "observed": "已觀測",
    "estimated": "估算",
    "degraded": "品質降級",
    "missing": "缺資料",
    "stale": "過期",
    "unavailable": "不可用",
    "unknown": "未知",
}


def build_shareholding_tier_table(value_text: object) -> ResearchTablePresentation:
    """把 TDCC 級距 JSON 轉成可閱讀表格，缺欄位時保留未知而不補零。"""

    raw_text = str(value_text or "").strip()
    if not raw_text:
        return ResearchTablePresentation(note="來源沒有提供持股級距明細。")
    try:
        payload = json.loads(raw_text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return ResearchTablePresentation(
            note="持股級距來源格式無法解析；完整原始內容保留在欄位 tooltip。"
        )
    if not isinstance(payload, list):
        return ResearchTablePresentation(
            note="持股級距來源不是明細列清單；完整原始內容保留在欄位 tooltip。"
        )

    rows: list[tuple[str, ...]] = []
    tooltips: list[tuple[str, ...]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        tier = _integer_value(item.get("tier"))
        if tier is None:
            tier_label = "來源未提供級距"
        else:
            tier_label = _SHAREHOLDING_TIER_LABELS.get(
                tier, f"第 {tier} 級（來源未提供區間）"
            )
        raw_row = json.dumps(item, ensure_ascii=False, sort_keys=True, indent=2)
        detail = f"原始級距欄位：\n{raw_row}"
        row = (
            tier_label,
            _integer_text(item.get("holder_count")),
            _integer_text(item.get("shares")),
            _ratio_text(item.get("holding_ratio_bp")),
        )
        rows.append(row)
        tooltips.append(tuple(detail for _ in row))

    if not rows:
        return ResearchTablePresentation(
            note="持股級距沒有可辨識的明細列；完整原始內容保留在欄位 tooltip。"
        )
    return ResearchTablePresentation(
        rows=tuple(rows),
        tooltips=tuple(tooltips),
        note="第 15 級是 1,000,001 股以上，第 16 級是來源的差異數調整，第 17 級是合計；各列只呈現來源已提供的值。",
    )


def build_stock_research_event_table(events: Any) -> ResearchTablePresentation:
    """把 Evidence event 的機器欄位轉成研究報告可讀列，原值放 tooltip。"""

    rows: list[tuple[str, ...]] = []
    tooltips: list[tuple[str, ...]] = []
    details: list[str] = []
    for event in tuple(events or ()):
        event_type = _token_text(getattr(event, "event_type", ""))
        event_family = _token_text(getattr(event, "event_family", ""))
        source_type = _token_text(getattr(event, "source_type", ""))
        data_quality = _token_text(getattr(event, "data_quality", ""))
        reasons = tuple(getattr(event, "reasons", ()) or ())
        why_not = tuple(getattr(event, "why_not_reasons", ()) or ())
        risk = tuple(getattr(event, "risk_reasons", ()) or ())
        warnings = tuple(getattr(event, "warnings", ()) or ())
        outcomes = tuple(getattr(event, "outcomes", ()) or ())

        date_text = str(
            getattr(event, "decision_date", "")
            or getattr(event, "event_date", "")
            or "—"
        )
        category = _event_family_label(event_family)
        event_label = _event_type_label(event_type)
        source_label = _SOURCE_LABELS.get(source_type.lower(), "其他來源")
        quality_label = _QUALITY_LABELS.get(data_quality.lower(), "未知")
        reason_text = _reason_text((*reasons, *why_not, *risk, *warnings))
        outcome_text = _outcome_text(outcomes)
        row = (date_text, event_label, quality_label, reason_text)
        rows.append(row)
        reason_detail = _reason_text(reasons, max_items=None, empty_text="未提供")
        why_not_detail = _reason_text(why_not, max_items=None, empty_text="未提供")
        risk_detail = _reason_text(risk, max_items=None, empty_text="未提供")
        warning_detail = _reason_text(warnings, max_items=None, empty_text="未提供")
        details.append(
            f"分類：{category}\n"
            f"來源：{source_label}\n"
            f"原因：{reason_detail}\n"
            f"反對理由：{why_not_detail}\n"
            f"風險：{risk_detail}\n"
            f"警告：{warning_detail}\n"
            f"後續結果：{outcome_text}"
        )
        raw_details = (
            f"原始 event_type：{event_type or '未提供'}\n"
            f"原始 event_family：{event_family or '未提供'}\n"
            f"原始 source_type：{source_type or '未提供'}\n"
            f"原始 source_id：{getattr(event, 'source_id', '') or '未提供'}\n"
            f"原始 source_version：{getattr(event, 'source_version', '') or '未提供'}\n"
            f"原始 data_quality：{data_quality or '未提供'}\n"
            f"原始 reasons：{json.dumps(list(reasons), ensure_ascii=False)}\n"
            f"原始 why_not_reasons：{json.dumps(list(why_not), ensure_ascii=False)}\n"
            f"原始 risk_reasons：{json.dumps(list(risk), ensure_ascii=False)}\n"
            f"原始 warnings：{json.dumps(list(warnings), ensure_ascii=False)}"
        )
        outcome_detail = "\n".join(
            f"{getattr(item, 'window_days', '—')}日："
            f"{getattr(item, 'outcome_status', '') or '未提供'}；"
            f"報酬bp：{getattr(item, 'forward_return_bp', None) if getattr(item, 'forward_return_bp', None) is not None else '未提供'}；"
            f"超額bp：{getattr(item, 'benchmark_excess_bp', None) if getattr(item, 'benchmark_excess_bp', None) is not None else '未提供'}"
            for item in outcomes
        ) or "尚無後續結果"
        tooltips.append(
            (
                f"決策日：{getattr(event, 'decision_date', '') or '未提供'}\n事件日：{getattr(event, 'event_date', '') or '未提供'}",
                raw_details,
                raw_details,
                f"{outcome_detail}\n\n{raw_details}",
            )
        )
    return ResearchTablePresentation(
        rows=tuple(rows), tooltips=tuple(tooltips), details=tuple(details)
    )


def _event_family_label(value: str) -> str:
    token = value.strip()
    if not token:
        return "事件"
    if token.lower() in {"portfolio", "portfolio_alert", "portfolio_alerts"}:
        return "持倉警示"
    if token.lower() in {"recommendation", "recommendation_result"}:
        return "推薦結果"
    if token.lower() in {"watchlist", "watchlist_trigger"}:
        return "觀察清單"
    if token.lower() in {"risk_prompt", "risk_prompts"}:
        return "風險提示"
    return f"產業／事件：{token}" if _looks_human(token) else "其他產業／事件"


def _event_type_label(value: str) -> str:
    token = value.strip()
    exact = _EVENT_TYPE_LABELS.get(token)
    if exact is not None:
        return exact
    lowered = token.lower()
    if lowered.startswith("portfolio_alert:"):
        suffix = lowered.split(":", 1)[1].replace("_", " ").strip()
        if suffix in {"condition warning", "warning"}:
            return "持倉條件提醒"
        if suffix in {"condition invalid", "invalid"}:
            return "持倉條件已失效"
        if suffix in {"chip risk", "chip"}:
            return "持倉籌碼風險"
        return "持倉警示事件"
    if lowered.startswith("risk_prompt:"):
        return "風險提示事件"
    return "其他事件"


def _reason_text(
    values: tuple[object, ...],
    *,
    max_items: int | None = 3,
    empty_text: str = "未提供原因",
) -> str:
    cleaned = [_token_text(value) for value in values if _token_text(value)]
    if not cleaned:
        return empty_text
    rendered = []
    selected = cleaned if max_items is None else cleaned[:max_items]
    for token in selected:
        rendered.append(_REASON_LABELS.get(token, token if _looks_human(token) else "其他原因（請看 tooltip）"))
    if max_items is not None and len(cleaned) > max_items:
        rendered.append(f"另有 {len(cleaned) - max_items} 項原因（請看 tooltip）")
    return "；".join(rendered)


def _outcome_text(outcomes: tuple[object, ...]) -> str:
    if not outcomes:
        return "尚無後續結果"
    rendered = []
    for outcome in outcomes[:3]:
        status = _token_text(getattr(outcome, "outcome_status", ""))
        status_label = {
            "ready": "已有結果",
            "observed": "已觀測",
            "pending": "尚待觀測",
            "missing_price": "缺後續價格",
            "insufficient_future_data": "後續資料不足",
        }.get(status.lower(), "結果狀態未對應")
        window = getattr(outcome, "window_days", None)
        window_text = f"{window}日" if window is not None else "期間未知"
        forward = getattr(outcome, "forward_return_bp", None)
        excess = getattr(outcome, "benchmark_excess_bp", None)
        value_text = []
        if forward is not None:
            value_text.append(f"報酬 {int(forward):+,} bp")
        if excess is not None:
            value_text.append(f"超額 {int(excess):+,} bp")
        rendered.append(f"{window_text}：{status_label}" + (f"（{'；'.join(value_text)}）" if value_text else ""))
    if len(outcomes) > 3:
        rendered.append(f"另有 {len(outcomes) - 3} 筆")
    return "；".join(rendered)


def _integer_value(value: object) -> int | None:
    try:
        if value is None:
            return None
        text = str(value).replace(",", "").strip()
        if not text or any(char not in "-0123456789" for char in text):
            return None
        return int(text)
    except (TypeError, ValueError):
        return None


def _integer_text(value: object) -> str:
    parsed = _integer_value(value)
    return "—" if parsed is None else f"{parsed:,}"


def _ratio_text(value: object) -> str:
    parsed = _integer_value(value)
    if parsed is None:
        return "—"
    return f"{(Decimal(parsed) / Decimal('100')).quantize(Decimal('0.01'))}%"


def _looks_human(value: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in value)


def _token_text(value: object) -> str:
    raw = getattr(value, "value", value)
    return "" if raw is None else str(raw).strip()


def build_recommendation_replay_sections(result: Any) -> list[str]:
    """建立推薦回放結果摘要區塊。"""

    summary = dict(getattr(result, "summary", {}) or {})
    sections = [
        "【概況】",
        f"總報酬率: {_format_ratio(summary.get('total_return'))}",
        f"最大回撤: {_format_ratio(summary.get('max_drawdown'))}",
        f"交易檔數: {_to_int(summary.get('total_trades'))}",
        f"平均持有天數: {_format_decimal(summary.get('avg_holding_days'), places=1)}",
        f"資金使用: {_format_int(summary.get('capital_used'))}",
        "資金使用代表期間投入金額，不等同最終淨值；請搭配現金帳、未成交與權重曝險判讀。",
        "",
        "【交易假設與可信度】",
        "交易假設提醒: 推薦回放仍以同日收盤成交為主要研究假設，不等同實盤可成交價格。",
        "若結果含 gap_risk、liquidity_limited、cash_limited 或 lot_size_limited，需先看對應限制再判讀績效。",
        f"出場統計: 停損 {_to_int(summary.get('stop_loss_exits'))} / "
        f"停利 {_to_int(summary.get('take_profit_exits'))} / "
        f"持有到期 {_to_int(summary.get('holding_period_exits'))}",
        f"虧損交易占比: {_format_ratio(summary.get('loss_trade_ratio'))}",
        f"最拖累股票: {summary.get('worst_stock_code', '')} "
        f"{summary.get('worst_stock_name', '')} "
        f"({_format_int(summary.get('worst_stock_pnl'))})",
        "",
        "【風險與情境指標】",
        f"Sharpe Ratio: {_format_decimal(summary.get('sharpe_ratio'), places=2)}",
        f"Sortino Ratio: {_format_decimal(summary.get('sortino_ratio'), places=2)}",
        "",
        "【Monte Carlo 情境】",
        "P05 / P50 / P95 分別代表模擬分布中的偏弱、中位與偏強情境報酬，不是保證績效。",
        f"P05 / P50 / P95: "
        f"{_format_ratio(summary.get('monte_carlo_p05_return'))} / "
        f"{_format_ratio(summary.get('monte_carlo_p50_return'))} / "
        f"{_format_ratio(summary.get('monte_carlo_p95_return'))}",
    ]

    hints = list(getattr(result, "improvement_hints", []) or [])
    if hints:
        sections.extend(["", "【策略改善建議】"])
        sections.extend(str(hint) for hint in hints)

    return sections


def build_train_test_reliability_notice(
    train_report: Any,
    test_report: Any,
) -> ReliabilityNotice:
    """依 Train-Test Split 的既有結果產生樣本可靠度提示。"""

    train_trades = _to_int(getattr(train_report, "total_trades", 0))
    test_trades = _to_int(getattr(test_report, "total_trades", 0))
    test_win_rate_bp = _ratio_to_bp(getattr(test_report, "win_rate", 0))
    test_max_drawdown_bp = _ratio_to_bp(getattr(test_report, "max_drawdown", 0))

    warnings: list[str] = []
    if test_trades < 20:
        warnings.append("測試集 OOS 交易數低於 20，樣本不足，不宜作正式策略判斷。")
    if test_win_rate_bp == 10000 and abs(test_max_drawdown_bp) >= 5000:
        warnings.append("測試集勝率 100% 但最大回撤偏大，請檢查是否由少量交易或單筆劇烈波動造成。")

    if not warnings:
        warnings.append("樣本可靠度未觸發重大警示；仍需搭配資料版本、成本模型與 Registry 可比性判讀。")

    message = "\n".join(
        [
            "【樣本可靠度】",
            f"訓練集交易數: {train_trades}",
            f"OOS 交易數: {test_trades}",
            *warnings,
        ]
    )
    level = "warning" if any("不足" in item or "偏大" in item for item in warnings) else "info"
    return ReliabilityNotice(
        level=level,
        message=message,
        evidence={
            "train_trades": train_trades,
            "test_trades": test_trades,
            "test_win_rate_bp": test_win_rate_bp,
            "test_max_drawdown_bp": test_max_drawdown_bp,
        },
    )


def build_walkforward_reliability_notice(
    results: list[Any],
    summary: dict[str, Any],
) -> ReliabilityNotice:
    """依 Walk-forward fold 結果產生可靠度提示。"""

    total_folds = _to_int(summary.get("total_folds", len(results)))
    if total_folds == 0:
        total_folds = len(results)
    oos_trades = sum(
        _to_int(getattr(result, "test_metrics", {}).get("total_trades", 0))
        for result in results
    )
    consistency_bp = _ratio_to_bp(summary.get("consistency", 0))

    warnings: list[str] = []
    if total_folds < 3:
        warnings.append("Fold 數低於 3，樣本不足，不宜作正式策略判斷。")
    if oos_trades < 20:
        warnings.append("OOS 交易數低於 20，結果容易受單一交易影響。")
    if consistency_bp == 10000 and total_folds < 3:
        warnings.append("一致性 100% 來自很少 fold，不能解讀為穩定獲利證據。")

    if not warnings:
        warnings.append("Walk-forward 樣本未觸發重大可靠度警示；仍需搭配 Registry 可比性與資料品質判讀。")

    message = "\n".join(
        [
            "【Walk-forward 樣本可靠度】",
            f"Fold 數: {total_folds}",
            f"OOS 交易數: {oos_trades}",
            f"測試期正向 Sharpe 覆蓋率: {_format_bp(consistency_bp)}",
            *warnings,
        ]
    )
    level = "warning" if any("不足" in item or "低於" in item for item in warnings) else "info"
    return ReliabilityNotice(
        level=level,
        message=message,
        evidence={
            "total_folds": total_folds,
            "oos_trades": oos_trades,
            "consistency_bp": consistency_bp,
        },
    )


def _to_decimal(value: Any, default: str = "0") -> Decimal:
    if value is None or value == "":
        return Decimal(default)
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal(default)


def _to_int(value: Any) -> int:
    return int(_to_decimal(value).to_integral_value(rounding=ROUND_HALF_UP))


def _ratio_to_bp(value: Any) -> int:
    return int(
        (_to_decimal(value) * Decimal("10000")).to_integral_value(
            rounding=ROUND_HALF_UP
        )
    )


def _format_bp(value: int) -> str:
    return f"{(Decimal(value) / Decimal('100')).quantize(Decimal('0.01'))}%"


def _format_ratio(value: Any) -> str:
    percent = (_to_decimal(value) * Decimal("100")).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )
    return f"{percent}%"


def _format_decimal(value: Any, *, places: int) -> str:
    quant = Decimal("1") if places == 0 else Decimal("0." + ("0" * (places - 1)) + "1")
    return str(_to_decimal(value).quantize(quant, rounding=ROUND_HALF_UP))


def _format_int(value: Any) -> str:
    return f"{_to_int(value):,}"


def is_research_data_limitation(reason: str) -> bool:
    """Identify missing source/contract diagnostics, without changing risk policy."""
    token = reason.strip().casefold()
    return token.endswith(("_missing", "_unavailable", "_unverified", "_unknown")) or token in {
        "基本面資料不足", "籌碼／分點資料不足", "缺少最新可用價格",
        "最新價格 row 沒有收盤價", "部分來源過期或讀取失敗",
        "feedback_failed", "feedback_degraded",
    }


def research_limitation_text(reason: str) -> str:
    """Keep raw diagnostics in audit details; explain known missingness in Chinese."""
    labels = {
        "condition_result_missing": "持倉健康缺少條件結果；WATCH 是待核對，未確認股票風險。",
        "source_trace_missing": "持倉健康缺少可追溯來源，暫不能判讀。",
        "feedback_failed": "持倉回饋驗證失敗，請核對原始診斷。",
        "feedback_degraded": "持倉回饋資料降級，請核對適用範圍。",
    }
    if reason in labels:
        return labels[reason]
    if is_research_data_limitation(reason) and "_" in reason:
        return "來源或條件資料缺件；原始代碼保留於資料稽核。"
    # Long identifiers and pipeline details are still retained verbatim in audit.
    if any(marker in reason.casefold() for marker in ("sha256", "run_id", "pipeline")):
        return "來源驗證有診斷限制；請展開資料稽核核對原始原因。"
    return reason if _looks_human(reason) else "來源限制尚未對應中文說明；原始診斷保留於資料稽核。"


def research_risk_text(reason: str) -> str:
    text = _reason_text((reason,), max_items=None)
    return text.replace("其他原因（請看 tooltip）", "來源有風險註記，原始原因詳見資料稽核")
