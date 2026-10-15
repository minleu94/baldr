"""月營收／官方來源研究頁的 V2 typed fact 呈現。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal

from app_module.daily_market_technical_official_disposition_revenue_query_v2 import (
    DailyMarketTechnicalOfficialDispositionRevenueCountsV2,
    DailyMarketTechnicalOfficialDispositionRevenueResultRowV2,
)
from decision_module.factors.selection_monthly_revenue_yoy_v2 import (
    MonthlyRevenueSourceEvidenceV2,
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
_MONTHLY_STATE_LABELS = {
    "blocked": "阻擋",
    "observed": "已觀測",
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


def _state_counts_label(values: object, labels: Mapping[str, str]) -> str:
    parts: list[str] = []
    for pair in _sequence(values):
        if not isinstance(pair, (tuple, list)) or len(pair) != 2:
            continue
        state, count = pair
        parts.append(f"{labels.get(str(state), str(state))} {count}")
    return "；".join(parts) or "未提供"


def _count_value(values: Mapping[str, object], key: str) -> str:
    value = values.get(key)
    return str(value) if type(value) is int and value >= 0 else "未提供"


def _source_evidence_lines(
    label: str,
    evidence: MonthlyRevenueSourceEvidenceV2 | None,
) -> list[str]:
    if evidence is None:
        return [f"  {label}來源證據：未提供；不以空值補成零。"]
    source_clock = (
        evidence.source_available_at.isoformat()
        if evidence.source_available_at is not None
        else "未提供"
    )
    return [
        f"  {label}證據：期間 {evidence.period}；原始值 {_raw_revenue_label(evidence.revenue)} {evidence.unit}",
        f"  {label}來源：{evidence.source}；市場 {evidence.market}；版本 {evidence.source_version}；原始版本 {evidence.raw_source_version}",
        f"  {label}來源原件 SHA-256：{evidence.raw_source_sha256}",
        f"  {label}觀測時間：{evidence.observed_at.isoformat()}",
        f"  {label}來源時間保存值（source_available_at）：{source_clock}；這不是 official_available_at。",
        f"  {label}有效使用時間：{evidence.available_at.isoformat()}；依據：{evidence.availability_basis}",
        f"  {label}來源批次：{evidence.availability_snapshot_batch_id}",
        f"  {label}首次保存時間：{evidence.availability_first_persisted_at.isoformat()}",
        f"  {label}輸入角色：{evidence.input_role}；母報表期間：{evidence.parent_report_period or '未提供'}",
    ]


def format_technical_official_revenue_research_row_v2(
    row: DailyMarketTechnicalOfficialDispositionRevenueResultRowV2,
) -> str:
    """呈現 V2 exact page 的保存事實，不重算條件或授予來源資格。"""

    if type(row) is not DailyMarketTechnicalOfficialDispositionRevenueResultRowV2:
        raise ValueError("technical_official_revenue_presenter_v2_row_invalid")
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

    source_fact = row.monthly_entry.source_fact
    projected = row.monthly_entry.projected_fact
    pin = projected.cohort_pin
    lines.extend((
        "月營收來源事實與 YoY 投影（分開呈現）：",
        f"  原始來源事實狀態：{_MONTHLY_STATE_LABELS.get(source_fact.state, source_fact.state)}；provider 狀態：{source_fact.status}",
        f"  原始來源事實期間：{source_fact.result.latest_period or '未提供'}；原因：{'、'.join(source_fact.reason_codes) or '無'}",
        f"  來源讀取診斷：{'、'.join(source_fact.result.diagnostics) or '無'}；阻擋期間：{'、'.join(source_fact.result.blocked_periods) or '無'}",
        f"  比較來源快照 SHA-256：{source_fact.result.comparison_snapshot_sha256 or '未提供'}",
        f"  YoY 投影狀態：{projected.state}；可用性：{projected.availability}；成長率：{_decimal_label(projected.growth_percent) + '%' if projected.growth_percent is not None else '未知'}",
        f"  YoY 公式：{projected.formula}；方法：{projected.method_id}／{projected.method_version}",
        f"  YoY 未知／限制原因：{'、'.join(projected.reason_codes) or '無'}；投影診斷：{'、'.join(projected.source_diagnostics) or '無'}",
        f"  cohort 期間：{pin.period}；市場：{'、'.join(pin.required_markets)}；批次 available hour：{pin.available_hour.isoformat()}",
        f"  cohort time-basis：{pin.time_basis_policy}；cohort SHA-256：{pin.cohort_sha256}",
        f"  投影當期月份：{projected.current.period if projected.current else '未提供'}；原始值：{_raw_revenue_label(projected.current.revenue if projected.current else None)}；單位：{projected.current.unit if projected.current else '未提供'}",
        f"  投影比較基期：{projected.comparator.period if projected.comparator else '未提供'}；原始值：{_raw_revenue_label(projected.comparator.revenue if projected.comparator else None)}；單位：{projected.comparator.unit if projected.comparator else '未提供'}",
        "  時間欄位界線：此 V2 evidence 保存解析後的 datetime；未保存未解析的來源時間文字。source_available_at 原值另行逐字顯示，cohort hour、來源批次與 first-persist 不互相替代。",
    ))
    lines.extend(_source_evidence_lines("當期", projected.current))
    lines.extend(_source_evidence_lines("比較基期", projected.comparator))
    lines.append("  cohort 各市場批次時間（hour、批次起始、首次保存、完成分列）：")
    for market_pin in pin.market_pins:
        lines.append(
            f"    {market_pin.market}／{market_pin.period}／{market_pin.batch_id}："
            f"available_hour={market_pin.available_hour.isoformat()}；"
            f"batch_started={market_pin.source_batch_started_at.isoformat()}；"
            f"first_persisted={market_pin.first_persisted_at.isoformat()}；"
            f"batch_completed={market_pin.successful_batch_completed_at.isoformat()}"
        )
    lines.extend((
        f"  cohort declared markets：{'、'.join(pin.required_markets)}；完整 pin 只說明本批次邊界，不是官方時間證明。",
        "來源資格：沿 exact V2 monthly index 保存的 source fact 與 cohort pin 呈現；本列不增加來源核准。",
        "範圍：outer query current_only；official_available_at 與 monthly_official_available_at 均未知；historical/formal PIT 均不具資格。",
    ))
    return "\n".join(lines)


def format_technical_official_revenue_counts_v2(
    counts: DailyMarketTechnicalOfficialDispositionRevenueCountsV2,
    *,
    result_status: str,
    official_coverage_status: str,
) -> str:
    """分開呈現原始來源事實、YoY 投影與完整 F17 母體分母。"""

    if type(counts) is not DailyMarketTechnicalOfficialDispositionRevenueCountsV2:
        raise ValueError("technical_official_revenue_presenter_v2_counts_invalid")
    base_to_dict = getattr(counts.base_f17_counts, "to_dict", None)
    if not callable(base_to_dict):
        raise ValueError("technical_official_revenue_presenter_v2_base_counts_invalid")
    base = _mapping(base_to_dict())
    population = _mapping(base.get("population"))
    source_counts = dict(counts.monthly_source_state_counts)
    projected_counts = dict(counts.monthly_projected_state_counts)
    declared = counts.declared_count
    lines = [
        f"F17 母體：宣告 {_count_value(population, 'declared_count')}；納入 {_count_value(population, 'included_count')}；排除 {_count_value(population, 'excluded_count')}",
        f"處理：已處理 {_count_value(population, 'processed_count')}；待處理 {_count_value(population, 'pending_count')}；缺資料 {_count_value(population, 'missing_data_count')}",
        f"月營收來源事實（分母 {declared}）：阻擋 {source_counts['blocked']}；已觀測 {source_counts['observed']}；未知 {source_counts['unknown']}",
        f"月營收 YoY 投影（分母 {declared}）：已觀測 {projected_counts['observed']}；未知 {projected_counts['unknown']}",
        f"官方來源覆蓋輸入：{'完整' if official_coverage_status == 'complete' else '部分／未完整' if official_coverage_status == 'partial' else '未提供'}；查詢狀態：{result_status}",
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
        lines.append(label + "：" + _state_counts_label(values, _TRUTH_LABELS))
    lines.append(
        "來源資格：outer current_only；official_available_at 與 monthly_official_available_at 未知；historical/formal PIT 不具資格。"
    )
    return "\n".join(lines)


def revenue_row_cells_v2(
    row: DailyMarketTechnicalOfficialDispositionRevenueResultRowV2,
) -> tuple[str, ...]:
    """固定沿用六欄順序；月營收來源狀態與投影狀態分開顯示。"""

    if type(row) is not DailyMarketTechnicalOfficialDispositionRevenueResultRowV2:
        raise ValueError("technical_official_revenue_presenter_v2_row_invalid")
    projected = row.monthly_entry.projected_fact
    source_state = _MONTHLY_STATE_LABELS.get(
        row.monthly_entry.source_fact.state,
        row.monthly_entry.source_fact.state,
    )
    projection_state = _MONTHLY_STATE_LABELS.get(projected.state, projected.state)
    growth = "未知" if projected.growth_percent is None else f"{format(projected.growth_percent, 'f')}%"
    return (
        row.stock_code,
        _TRUTH_LABELS.get(row.technical_condition_truth, "未知"),
        _TRUTH_LABELS.get(row.ma_condition_truth, "未知"),
        f"來源 {source_state}／YoY {projection_state}",
        growth,
        _TRUTH_LABELS.get(row.composite_condition_truth, "未知"),
    )
