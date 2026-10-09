"""F17／四均線保存研究的繁體中文事實呈現。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import cast

from app_module.daily_market_technical_official_disposition_ma_query_v1 import (
    DailyMarketTechnicalOfficialDispositionMaCountsV1,
    DailyMarketTechnicalOfficialDispositionMaResultRowV1,
)


_STATE_LABELS = {
    "match": "符合",
    "no_match": "不符合",
    "unknown": "未知",
    "not_evaluated": "未評估",
    "not_applicable": "不適用",
}
_MA_STATE_LABELS = {"match": "符合", "no_match": "不符合", "unknown": "未知"}
_RULE_LABELS = {
    "ma5_20_golden_cross": "MA5／MA20 金叉",
    "kd_golden_cross": "K／D 金叉",
    "macd_golden_cross": "MACD 金叉",
    "volume_ratio_20_including_current": "量能比 20（含當日）",
    "volume_ratio_5_including_current": "量能比 5（含當日）",
}
_MARKET_LABELS = {
    "assigned_twse": "上市（TWSE）",
    "assigned_tpex": "上櫃（TPEx）",
    "unknown": "未知",
}
_DISPOSAL_LABELS = {
    "reported_upcoming": "已公告、尚未生效",
    "reported_active": "公告處置中",
    "reported_elapsed_only": "僅有已經過的處置紀錄",
    "unknown": "未知",
}
_SCOPE_LABELS = {
    "included_processed": "納入且已處理",
    "included_pending": "納入但待處理",
    "excluded": "明示排除",
}
_MA_REASON_LABELS = {
    "ma_alignment_current_session_missing": "目前保存版本沒有指定的均線觀測日。",
    "ma_alignment_current_session_future": "均線觀測日晚於決策日。",
    "ma_alignment_insufficient_sessions": "目前觀測日前的保存列不足 60 列。",
    "ma_alignment_non_contiguous_sessions": "目前觀測日前的保存列不連續。",
    "ma_alignment_invalid_close": "均線觀測窗口含無效收盤價。",
    "ma_alignment_source_row_invalid": "均線來源列未通過驗證。",
}


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _saved_dates(value: object) -> str:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return "未提供"
    values: list[str] = []
    for item in value:
        if isinstance(item, str):
            values.append(item)
        elif isinstance(item, Mapping):
            source = item.get("source_id", "來源")
            dates = item.get("dates")
            if isinstance(dates, Sequence) and not isinstance(dates, (str, bytes)):
                values.append(f"{source}：{'、'.join(str(part) for part in dates) or '未提供'}")
    return "；".join(values) or "未提供"


def _official_lines(row: DailyMarketTechnicalOfficialDispositionMaResultRowV1) -> list[str]:
    fact = row.fact_row.to_dict()
    market = _mapping(fact.get("market_assignment"))
    disposal = _mapping(fact.get("official_disposal"))
    lines = [
        f"市場狀態：{_MARKET_LABELS.get(str(market.get('state')), '未知')}",
        f"市場資料日期：{_saved_dates(market.get('source_data_dates'))}",
        f"市場觀察時間：{market.get('snapshot_observed_at') or '未提供'}",
        f"處置狀態：{_DISPOSAL_LABELS.get(str(disposal.get('state')), '未知')}",
        f"處置資料日期：{_saved_dates(disposal.get('source_data_dates'))}",
        f"處置觀察時間：{disposal.get('observed_at') or '未提供'}",
        f"處置觀察日期：{disposal.get('observed_date') or '未提供'}",
        f"處置來源解析狀態：{disposal.get('source_parse_status') or '未提供'}",
        f"處置來源原因：{disposal.get('reason_code') or '未提供'}",
        f"處置來源是否部分失敗：{'是' if disposal.get('partial_failure') is True else '否／未標示'}",
    ]
    warnings = disposal.get("source_warnings")
    if isinstance(warnings, Sequence) and not isinstance(warnings, (str, bytes)) and warnings:
        lines.extend(f"處置來源警告：{warning}" for warning in warnings)
    reason = fact.get("exclusion_reason")
    if isinstance(reason, str) and reason:
        lines.append(f"母體排除理由：{reason}")
    events = disposal.get("events")
    if isinstance(events, Sequence) and not isinstance(events, (str, bytes)) and events:
        for index, event in enumerate(events, start=1):
            if not isinstance(event, Mapping):
                continue
            parts = [f"處置事件 {index}：{event.get('name') or '名稱未提供'}"]
            for key, label in (
                ("announcement_date", "公告日"),
                ("effective_from", "生效日"),
                ("effective_to", "結束日"),
                ("reason", "原因"),
                ("measure", "措施"),
            ):
                value = event.get(key)
                if value not in (None, ""):
                    parts.append(f"{label}：{value}")
            lines.append("；".join(parts))
    else:
        lines.append("處置事件：沒有保存符合此股票的事件列。")
    return lines


def format_technical_official_ma_research_row_v1(
    row: DailyMarketTechnicalOfficialDispositionMaResultRowV1,
) -> str:
    """呈現 exact page row 的已保存事實；不重算指標或提供建議。"""

    if type(row) is not DailyMarketTechnicalOfficialDispositionMaResultRowV1:
        raise ValueError("technical_official_ma_presenter_row_invalid")
    fact = row.fact_row.to_dict()
    status = str(fact.get("technical_status", "unknown"))
    status_label = {
        "processed": "已處理",
        "pending": "待處理",
        "excluded": "明示排除",
    }.get(status, "未知")
    technical = row.technical_row
    lines = [
        f"股票代碼：{row.stock_code}",
        f"母體範圍：{_SCOPE_LABELS.get(row.filter_evaluation.row_scope, '未提供')}",
        f"處理狀態：{status_label}",
        f"條件群組結果：{_STATE_LABELS.get(row.composite_condition_truth, '未知')}",
        f"技術條件：{_STATE_LABELS.get(row.technical_condition_truth, '未知')}",
        f"四均線排列條件：{_STATE_LABELS.get(row.ma_condition_truth, '未知')}",
    ]
    if technical is None:
        lines.extend((
            "技術來源列：未提供；不以空值補成數值。",
            "技術觀測日期：未提供",
            "已保存來源列數：未提供",
        ))
    else:
        lines.extend((
            f"決策日期：{technical.decision_date.isoformat()}",
            f"最新技術觀測日：{technical.latest_feature_date.isoformat() if technical.latest_feature_date else '未提供'}",
            f"已保存來源列數：{technical.raw_row_count}",
            "五項技術規則：",
        ))
        for rule in technical.rules:
            label = _RULE_LABELS.get(rule.key, "方法契約未提供規則名稱")
            state = _STATE_LABELS.get(rule.state, "未知")
            lines.append(f"  {label}：{state}")
            if rule.ratio is not None:
                lines.append(f"    保存比率：{rule.ratio}")
            if rule.numerator is not None:
                lines.append(f"    保存分子：{rule.numerator}")
            if rule.denominator is not None:
                lines.append(f"    保存分母：{rule.denominator}")
            lines.extend(f"    支持事實：{item}" for item in rule.supports)
            lines.extend(f"    未符合事實：{item}" for item in rule.counterevidence)
            lines.extend(f"    未知原因：{item}" for item in rule.unknown_reasons)
    entry = row.ma_entry
    lines.append("四均線排列證據：")
    if entry is None:
        lines.extend((
            "  證據：未提供；此列可能待處理、排除或沒有已核對應來源。",
            f"  狀態：{_MA_STATE_LABELS.get(row.ma_condition_truth, '未評估')}",
        ))
    else:
        lines.extend((
            f"  狀態：{_MA_STATE_LABELS.get(entry.ma_state, '未知')}",
            f"  最新觀測日：{entry.feature_date.isoformat() if entry.feature_date else '未提供'}",
            f"  計算暖機觀測列數：{entry.warmup_observed_sessions}",
            f"  觀測前綴連續：{'是' if entry.observed_prefix_contiguous else '否／未核'}",
            f"  暖機連續：{'是' if entry.warmup_contiguous else '否／未核'}",
        ))
        if entry.ma_reason_codes:
            lines.extend(
                f"  未知／限制原因：{_MA_REASON_LABELS.get(reason, '方法契約記錄的限制：' + reason)}"
                for reason in entry.ma_reason_codes
            )
        for item in entry.base_rule_facts:
            label = f"規則 {item.key}"
            lines.append(f"  {label}：{_MA_STATE_LABELS.get(item.state, '未知')}")
            if item.numerator is not None:
                lines.append(f"    保存分子：{item.numerator}")
            if item.denominator is not None:
                lines.append(f"    保存分母：{item.denominator}")
            if item.ratio is not None:
                lines.append(f"    保存比率：{item.ratio}")
    lines.extend(_official_lines(row))
    lines.extend((
        "",
        "來源資格：沿所選保存版本完成 exact 核驗；來源不持續監測。",
        "分析範圍：current-only；官方可用時間未知，不具歷史 PIT 資格。",
    ))
    return "\n".join(lines)


def format_technical_official_ma_counts_v1(
    counts: DailyMarketTechnicalOfficialDispositionMaCountsV1,
    *,
    result_status: str,
    official_coverage_status: str,
) -> str:
    """分開呈現母體分母、來源覆蓋、truth 與未知政策後可見筆數。"""

    if type(counts) is not DailyMarketTechnicalOfficialDispositionMaCountsV1:
        raise ValueError("technical_official_ma_presenter_counts_invalid")
    population = counts.population
    count_values = cast(Mapping[str, int], population.to_dict())
    lines = [
        f"母體：宣告 {count_values['declared_count']}；納入 {count_values['included_count']}；排除 {count_values['excluded_count']}",
        f"處理：已處理 {count_values['processed_count']}；待處理 {count_values['pending_count']}；缺資料 {count_values['missing_data_count']}；待處理缺資料 {count_values['missing_data_pending_count']}",
        f"官方來源覆蓋：{_coverage_label(official_coverage_status)}；查詢狀態：{_coverage_label(result_status)}",
        f"硬條件適用列：{counts.hard_eligible_count}；政策後可見：{counts.visible_count}",
        f"可適用條件 truth：符合 {counts.predicate_match_count}；不符合 {dict(counts.eligible_truth_counts)['no_match']}；未知 {counts.predicate_unknown_count}；未評估 {counts.predicate_not_evaluated_count}",
        f"未知政策：納入 {counts.unknown_policy_included_count}；排除 {counts.unknown_policy_excluded_count}",
    ]
    lines.append("已處理列的四均線狀態：" + _pairs(counts.ma_state_counts))
    lines.append("技術條件 truth：" + _pairs(counts.technical_truth_counts))
    lines.append("四均線條件 truth：" + _pairs(counts.ma_truth_counts))
    lines.append("複合 truth：" + _pairs(counts.composite_truth_counts))
    lines.extend((
        "範圍：current-only；official available_at 未知；historical PIT 不適用。",
    ))
    return "\n".join(lines)


def _pairs(values: tuple[tuple[str, int], ...]) -> str:
    return "；".join(f"{_STATE_LABELS.get(key, key)} {value}" for key, value in values)


def _coverage_label(value: str) -> str:
    return "完整" if value == "complete" else "部分／未完整" if value == "partial" else "未提供"
