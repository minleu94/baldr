"""月營收／官方來源研究頁的可讀事實呈現。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import cast

from app_module.daily_market_technical_official_disposition_revenue_query_v1 import (
    DailyMarketTechnicalOfficialDispositionRevenueCountsV1,
    DailyMarketTechnicalOfficialDispositionRevenueResultRowV1,
)


_TRUTH_LABELS = {
    "match": "符合",
    "no_match": "不符合",
    "unknown": "未知",
    "not_evaluated": "未評估",
    "not_applicable": "未啟用",
}
_SCOPE_LABELS = {
    "included_processed": "納入且已處理",
    "included_pending": "納入但待處理",
    "excluded": "明示排除",
}
_TECHNICAL_RULE_LABELS = {
    "ma5_20_golden_cross": "MA5／MA20 金叉",
    "kd_golden_cross": "K／D 金叉",
    "macd_golden_cross": "MACD 金叉",
    "volume_ratio_20_including_current": "量能比 20（含當日）",
    "volume_ratio_5_including_current": "量能比 5（含當日）",
}
_OFFICIAL_MARKET_LABELS = {
    "assigned_twse": "上市（TWSE）",
    "assigned_tpex": "上櫃（TPEx）",
    "unknown": "未知",
}
_OFFICIAL_DISPOSAL_LABELS = {
    "reported_upcoming": "已公告、尚未生效",
    "reported_active": "公告處置中",
    "reported_elapsed_only": "僅有已經過的處置紀錄",
    "unknown": "未知",
}


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: object) -> Sequence[object]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return value
    return ()


def _saved_dates(value: object) -> str:
    values: list[str] = []
    for item in _sequence(value):
        if isinstance(item, Mapping):
            source = item.get("source_id") or "來源"
            dates = _sequence(item.get("dates"))
            values.append(f"{source}：{'、'.join(str(part) for part in dates) or '未提供'}")
        elif isinstance(item, str):
            values.append(item)
    return "；".join(values) or "未提供"


def _decimal_label(value: object) -> str:
    if type(value) is Decimal:
        return format(value, "f")
    if value is None:
        return "未知"
    return str(value)


def _raw_revenue_label(value: object) -> str:
    """保留 Decimal 零值；只有真正缺值才顯示未提供。"""

    if value is None:
        return "未提供"
    if type(value) is Decimal:
        return format(value, "f")
    return str(value)


def format_technical_official_revenue_research_row_v1(
    row: DailyMarketTechnicalOfficialDispositionRevenueResultRowV1,
) -> str:
    """呈現 exact page 的保存事實，不重算條件或提供投資建議。"""

    if type(row) is not DailyMarketTechnicalOfficialDispositionRevenueResultRowV1:
        raise ValueError("technical_official_revenue_presenter_row_invalid")
    fact = row.fact_row.to_dict()
    market = _mapping(fact.get("market_assignment"))
    disposal = _mapping(fact.get("official_disposal"))
    status = str(fact.get("technical_status", "unknown"))
    lines = [
        f"股票代碼：{row.stock_code}",
        f"母體範圍：{_SCOPE_LABELS.get(row.filter_evaluation.row_scope, '未提供')}",
        f"處理狀態：{'已處理' if status == 'processed' else '待處理' if status == 'pending' else '明示排除' if status == 'excluded' else '未知'}",
        f"官方市場狀態：{_OFFICIAL_MARKET_LABELS.get(str(market.get('state')), '未知')}",
        f"官方處置狀態：{_OFFICIAL_DISPOSAL_LABELS.get(str(disposal.get('state')), '未知')}",
        f"技術條件：{_TRUTH_LABELS.get(row.technical_condition_truth, '未知')}",
        f"四均線條件：{_TRUTH_LABELS.get(row.ma_condition_truth, '未知')}",
        f"月營收 YoY 條件：{_TRUTH_LABELS.get(row.revenue_condition_truth, '未知')}",
        f"複合條件：{_TRUTH_LABELS.get(row.composite_condition_truth, '未知')}",
        f"硬性母體條件：{'符合' if row.hard_filter_match else '不符合'}；未知政策後可見：{'是' if row.included_by_unknown_policy else '否'}",
        f"市場資料日期：{_saved_dates(market.get('source_data_dates'))}",
        f"市場觀察時間：{market.get('snapshot_observed_at') or '未提供'}",
        f"處置資料日期：{_saved_dates(disposal.get('source_data_dates'))}",
        f"處置觀察時間：{disposal.get('observed_at') or '未提供'}",
        f"處置觀察日期：{disposal.get('observed_date') or '未提供'}",
        f"處置來源解析狀態：{disposal.get('source_parse_status') or '未提供'}",
        f"處置來源原因：{disposal.get('reason_code') or '未提供'}",
        f"處置來源部分失敗：{'是' if disposal.get('partial_failure') is True else '否／未標示'}",
    ]
    warnings = _sequence(disposal.get("source_warnings"))
    lines.extend(f"處置來源警告：{warning}" for warning in warnings)
    reason = fact.get("exclusion_reason")
    if isinstance(reason, str) and reason:
        lines.append(f"母體排除理由：{reason}")

    technical = row.technical_row
    lines.append("五項技術規則事實：")
    if technical is None:
        lines.append("  技術列未提供；不以空值補成數字。")
    else:
        lines.extend((
            f"  決策日期：{technical.decision_date.isoformat()}",
            f"  最新技術觀測日：{technical.latest_feature_date.isoformat() if technical.latest_feature_date else '未提供'}",
            f"  已保存原始列數：{technical.raw_row_count}",
        ))
        for rule in technical.rules:
            lines.append(
                f"  {_TECHNICAL_RULE_LABELS.get(rule.key, '方法契約未提供規則名稱')}：{_TRUTH_LABELS.get(rule.state, '未知')}"
            )
            if rule.ratio is not None:
                lines.append(f"    保存比率：{rule.ratio}")
            if rule.numerator is not None:
                lines.append(f"    保存分子：{rule.numerator}")
            if rule.denominator is not None:
                lines.append(f"    保存分母：{rule.denominator}")
            lines.extend(f"    支持事實：{item}" for item in rule.supports)
            lines.extend(f"    反證事實：{item}" for item in rule.counterevidence)
            lines.extend(f"    未知原因：{item}" for item in rule.unknown_reasons)

    ma = row.ma_entry
    lines.append("四均線排列證據：")
    if ma is None:
        lines.append("  未提供已核證據；不以缺件補成符合。")
    else:
        lines.extend((
            f"  狀態：{_TRUTH_LABELS.get(ma.ma_state, '未知')}",
            f"  均線觀測日：{ma.feature_date.isoformat() if ma.feature_date else '未提供'}",
            f"  暖機觀測列數：{ma.warmup_observed_sessions}",
            f"  來源前綴連續：{'是' if ma.observed_prefix_contiguous else '否／未核'}",
            f"  暖機連續：{'是' if ma.warmup_contiguous else '否／未核'}",
        ))
        if ma.ma_reason_codes:
            lines.extend(f"  未知原因：{reason_code}" for reason_code in ma.ma_reason_codes)

    monthly = row.monthly_entry.source_fact.to_dict()
    projected = row.monthly_entry.projected_fact.to_dict()
    current = _mapping(monthly.get("current"))
    comparator = _mapping(monthly.get("comparator"))
    lines.extend((
        "月營收來源事實：",
        f"  來源狀態：{monthly.get('state') or '未知'}；原因：{'、'.join(str(item) for item in _sequence(monthly.get('reason_codes'))) or '未提供'}",
        f"  當期月份：{current.get('period') or '未提供'}；原始值：{_raw_revenue_label(current.get('revenue'))}；單位：{current.get('unit') or '未提供'}",
        f"  比較基期：{comparator.get('period') or '未提供'}；原始值：{_raw_revenue_label(comparator.get('revenue'))}；單位：{comparator.get('unit') or '未提供'}",
        f"  YoY 狀態：{projected.get('state') or '未知'}；成長率：{_decimal_label(projected.get('growth_percent'))}%",
        f"  YoY 未知／限制原因：{'、'.join(str(item) for item in _sequence(projected.get('reason_codes'))) or '無'}",
        f"  原始比較欄診斷：{row.monthly_entry.source_fact.raw_comparator_evidence.classification if row.monthly_entry.source_fact.raw_comparator_evidence else '未提供'}；不會自動替代合格基期。",
        "來源資格：沿所選保存 F17 與月營收封存版本完成 exact 核驗；來源不持續監測。",
        "範圍：current-only；官方可用時間未知，不具歷史 PIT 資格。",
    ))
    return "\n".join(lines)


def format_technical_official_revenue_counts_v1(
    counts: DailyMarketTechnicalOfficialDispositionRevenueCountsV1,
    *,
    result_status: str,
    official_coverage_status: str,
) -> str:
    """分開呈現完整母體、來源覆蓋、truth 與未知政策後可見筆數。"""

    if type(counts) is not DailyMarketTechnicalOfficialDispositionRevenueCountsV1:
        raise ValueError("technical_official_revenue_presenter_counts_invalid")
    population = cast(Mapping[str, int], counts.base_f17_counts.population.to_dict())
    monthly_states = dict(counts.monthly_source_state_counts)
    lines = [
        f"母體：宣告 {population['declared_count']}；納入 {population['included_count']}；排除 {population['excluded_count']}",
        f"處理：已處理 {population['processed_count']}；待處理 {population['pending_count']}；缺資料 {population['missing_data_count']}",
        f"月營收來源：觀測 {monthly_states['observed']}；未知 {monthly_states['unknown']}；阻擋 {monthly_states['blocked']}",
        f"官方來源覆蓋：{'完整' if official_coverage_status == 'complete' else '部分／未完整' if official_coverage_status == 'partial' else '未提供'}；查詢狀態：{result_status}",
        f"硬性母體符合：{counts.hard_eligible_count}；政策後可見：{counts.visible_count}",
        f"可適用 truth：符合 {counts.predicate_match_count}；不符合 {dict(counts.eligible_truth_counts)['no_match']}；未知 {counts.predicate_unknown_count}；未評估 {counts.predicate_not_evaluated_count}",
        f"未知政策納入：{counts.unknown_policy_included_count}；排除：{counts.unknown_policy_excluded_count}",
    ]
    for label, values in (
        ("技術條件 truth", counts.technical_truth_counts),
        ("四均線 truth", counts.ma_truth_counts),
        ("月營收 YoY truth", counts.revenue_truth_counts),
        ("複合 truth", counts.composite_truth_counts),
        ("硬性符合列 truth", counts.eligible_truth_counts),
    ):
        lines.append(label + "：" + "；".join(
            f"{_TRUTH_LABELS.get(state, state)} {value}" for state, value in values
        ))
    lines.append("來源資格：current-only；官方及月營收 available_at 未知；historical PIT 不適用。")
    return "\n".join(lines)


def revenue_row_cells_v1(
    row: DailyMarketTechnicalOfficialDispositionRevenueResultRowV1,
) -> tuple[str, ...]:
    """提供表格一頁內固定欄位；排序由全域 reader 先完成。"""

    if type(row) is not DailyMarketTechnicalOfficialDispositionRevenueResultRowV1:
        raise ValueError("technical_official_revenue_presenter_row_invalid")
    monthly = row.monthly_entry.projected_fact
    growth = "未知" if monthly.growth_percent is None else f"{monthly.growth_percent}%"
    return (
        row.stock_code,
        _TRUTH_LABELS.get(row.technical_condition_truth, "未知"),
        _TRUTH_LABELS.get(row.ma_condition_truth, "未知"),
        monthly.state,
        growth,
        _TRUTH_LABELS.get(row.composite_condition_truth, "未知"),
    )
