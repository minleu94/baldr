"""F17 複合研究結果的唯讀 typed presenter 候選。"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal, cast

from app_module.daily_market_technical_official_disposition_composite_query_v1 import (
    DailyMarketTechnicalOfficialDispositionCompositeQueryPageV1,
    DailyMarketTechnicalOfficialDispositionCompositeResultRowV1,
    DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV1,
)


GroupName = Literal["technical", "ma", "kdj", "volatility"]
Truth = Literal["match", "no_match", "unknown", "not_evaluated", "not_applicable"]

_GROUP_LABELS = {
    "technical": "技術條件",
    "ma": "四均線排列",
    "kdj": "KDJ",
    "volatility": "波動條件",
}
_TRUTH_LABELS = {
    "match": "符合",
    "no_match": "不符合",
    "unknown": "未知",
    "not_evaluated": "未評估",
    "not_applicable": "不適用",
}
_ROW_SCOPE_LABELS = {
    "included_processed": "納入且已處理",
    "included_pending": "納入但待處理",
    "excluded": "明示排除",
}


def _require_result(
    result: object,
) -> DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV1:
    if type(result) is not DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV1:
        raise ValueError("composite_presenter_result_type_invalid")
    typed = cast(DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV1, result)
    typed.__post_init__()
    return typed


def _require_row(
    row: object,
) -> DailyMarketTechnicalOfficialDispositionCompositeResultRowV1:
    if type(row) is not DailyMarketTechnicalOfficialDispositionCompositeResultRowV1:
        raise ValueError("composite_presenter_row_type_invalid")
    typed = cast(DailyMarketTechnicalOfficialDispositionCompositeResultRowV1, row)
    typed.to_dict()
    return typed


def _decimal_text(value: Decimal | None) -> str | None:
    if value is None:
        return None
    if type(value) is not Decimal or not value.is_finite():
        raise ValueError("composite_presenter_decimal_invalid")
    return format(value, "f")


@dataclass(frozen=True, slots=True)
class CompositeNumericFactV1:
    group: GroupName
    label: str
    value: Decimal
    value_text: str
    unit: str
    state: str
    reason_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CompositeGroupPresentationV1:
    group: GroupName
    truth: Truth
    active: bool
    reason_codes: tuple[str, ...]
    evidence_lines: tuple[str, ...]

    @property
    def label(self) -> str:
        return _GROUP_LABELS[self.group]

    @property
    def truth_label(self) -> str:
        return _TRUTH_LABELS[self.truth]


@dataclass(frozen=True, slots=True)
class CompositeRowPresentationV1:
    stock_code: str
    technical_status: str
    row_scope: str
    groups: tuple[CompositeGroupPresentationV1, ...]
    composite_truth: Truth
    hard_eligible: bool
    audit_visible: bool
    included_by_unknown_policy: bool
    predicate_match: bool
    visible: bool
    numeric_facts: tuple[CompositeNumericFactV1, ...]
    current_only: Literal[True]
    official_available_at: None
    availability_status: Literal["unknown"]
    historical_pit_eligible: Literal[False]
    row_identity_sha256: str


@dataclass(frozen=True, slots=True)
class CompositeGlobalCountsPresentationV1:
    declared_count: int
    included_count: int
    processed_count: int
    excluded_count: int
    pending_count: int
    base_f17_matching_count: int
    hard_eligible_count: int
    active_evaluable_count: int
    audit_visible_count: int
    visible_count: int
    unknown_policy_included_count: int
    unknown_policy_excluded_count: int
    technical_truth_counts: tuple[tuple[str, int], ...]
    ma_truth_counts: tuple[tuple[str, int], ...]
    kdj_truth_counts: tuple[tuple[str, int], ...]
    volatility_truth_counts: tuple[tuple[str, int], ...]
    composite_truth_counts: tuple[tuple[str, int], ...]
    ma_state_counts: tuple[tuple[str, int], ...]
    kdj_state_counts: tuple[tuple[str, int], ...]
    bandwidth_state_counts: tuple[tuple[str, int], ...]
    atr14_state_counts: tuple[tuple[str, int], ...]
    result_status: Literal["complete", "partial"]
    official_source_coverage_status: Literal["complete", "partial"]
    current_only: Literal[True]
    official_available_at: None
    availability_status: Literal["unknown"]
    historical_pit_eligible: Literal[False]


@dataclass(frozen=True, slots=True)
class CompositePagePresentationV1:
    global_counts: CompositeGlobalCountsPresentationV1
    page_index: int
    page_size: int
    page_count: int
    page_row_count: int
    rows: tuple[CompositeRowPresentationV1, ...]
    operation_identity_sha256: str
    page_identity_sha256: str


def _numeric_fact(
    group: GroupName,
    label: str,
    value: Decimal | None,
    *,
    unit: str,
    state: str,
    reason_codes: tuple[str, ...] = (),
) -> CompositeNumericFactV1 | None:
    text = _decimal_text(value)
    if value is None or text is None:
        return None
    return CompositeNumericFactV1(
        group=group,
        label=label,
        value=value,
        value_text=text,
        unit=unit,
        state=state,
        reason_codes=reason_codes,
    )


def _group_reasons_and_evidence(
    row: DailyMarketTechnicalOfficialDispositionCompositeResultRowV1,
    group: GroupName,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    reasons: list[str] = []
    evidence: list[str] = []
    if group == "technical":
        technical = row.technical_row
        if technical is None:
            evidence.append("沒有已處理的技術投影列。")
        else:
            for rule in technical.rules:
                reasons.extend(rule.unknown_reasons)
                details = [f"規則 {rule.key}：{_TRUTH_LABELS.get(rule.state, '未知')}"]
                if rule.supports:
                    details.append("支持事實：" + "、".join(rule.supports))
                if rule.counterevidence:
                    details.append("未符合事實：" + "、".join(rule.counterevidence))
                if rule.unknown_reasons:
                    details.append("未知原因：" + "、".join(rule.unknown_reasons))
                evidence.append("；".join(details))
    elif group == "ma":
        entry = row.ma_entry
        if entry is None:
            evidence.append("沒有已處理的四均線投影列。")
        else:
            reasons.extend(entry.ma_reason_codes)
            evidence.append(
                "均線狀態："
                + _TRUTH_LABELS.get(entry.ma_state, "未知")
                + f"；觀測日：{entry.feature_date.isoformat() if entry.feature_date else '未提供'}"
                + f"；暖機觀測列：{entry.warmup_observed_sessions}"
                + f"；暖機連續：{'是' if entry.warmup_contiguous else '否'}"
            )
            for fact in entry.base_rule_facts:
                evidence.append(
                    f"基礎規則 {fact.key}：{_TRUTH_LABELS.get(fact.state, '未知')}"
                    f"；分子 {fact.numerator if fact.numerator is not None else '未提供'}"
                    f"；分母 {fact.denominator if fact.denominator is not None else '未提供'}"
                    f"；比率 {fact.ratio if fact.ratio is not None else '未提供'}"
                )
    elif group == "kdj":
        entry = row.kdj_entry
        if entry is None:
            evidence.append("沒有已處理的 KDJ 投影列。")
        else:
            reasons.extend(entry.reason_codes)
            evidence.append(
                f"KDJ 證據狀態：{_TRUTH_LABELS.get(entry.state, '未知')}"
                f"；觀測日：{entry.current.feature_date.isoformat() if entry.current else '未提供'}"
                f"；暖機觀測列：{entry.warmup_observed_sessions}"
                f"；暖機連續：{'是' if entry.warmup_contiguous else '否'}"
            )
    else:
        entry = row.volatility_entry
        if entry is None:
            evidence.append("沒有已處理的波動率投影列。")
        else:
            for measure_name, measure in (
                ("Bandwidth", entry.evidence.bandwidth),
                ("ATR14 SMA", entry.evidence.atr14_sma),
            ):
                reasons.extend(measure.reason_codes)
                value_text = _decimal_text(measure.value) or "未提供"
                normalized_text = _decimal_text(measure.normalized_value)
                evidence.append(
                    f"{measure_name}：{measure.state} {value_text} {measure.unit}"
                    + (
                        "；正規化值 " + normalized_text + " percent"
                        if normalized_text is not None
                        else ""
                    )
                    + (
                        "；原因 " + "、".join(measure.reason_codes)
                        if measure.reason_codes
                        else ""
                    )
                )
    return tuple(dict.fromkeys(reasons)), tuple(evidence)


def present_composite_row_v1(
    row: DailyMarketTechnicalOfficialDispositionCompositeResultRowV1,
) -> CompositeRowPresentationV1:
    """只投影已保存 row facts；不重算金融條件或從未知補值。"""
    typed = _require_row(row)
    fact_payload = typed.fact_row.to_dict()
    status = fact_payload.get("technical_status")
    if type(status) is not str:
        raise ValueError("composite_presenter_row_status_invalid")
    group_specs: tuple[tuple[GroupName, Truth], ...] = (
        ("technical", typed.evaluation.technical_truth),
        ("ma", typed.evaluation.ma_truth),
        ("kdj", typed.evaluation.kdj_truth),
        ("volatility", typed.evaluation.volatility_truth),
    )
    groups: list[CompositeGroupPresentationV1] = []
    for index, (group, truth) in enumerate(group_specs):
        reasons, evidence = _group_reasons_and_evidence(typed, group)
        groups.append(CompositeGroupPresentationV1(
            group=group,
            truth=truth,
            active=typed.evaluation.active_groups[index],
            reason_codes=reasons,
            evidence_lines=evidence,
        ))

    numeric_facts: list[CompositeNumericFactV1] = []
    technical = typed.technical_row
    if technical is not None:
        for rule in technical.rules:
            for label, value in (
                (f"{rule.key} 分子", rule.numerator),
                (f"{rule.key} 分母", rule.denominator),
                (f"{rule.key} 比率", rule.ratio),
            ):
                item = _numeric_fact(
                    "technical", label, value, unit="來源值", state=rule.state,
                    reason_codes=rule.unknown_reasons,
                )
                if item is not None:
                    numeric_facts.append(item)
    kdj = typed.kdj_entry
    if kdj is not None:
        for day_name, day in (("前次", kdj.previous), ("當次", kdj.current)):
            if day is None:
                continue
            for field_name, value in (
                ("RSV", day.rsv),
                ("K", day.k),
                ("D", day.d),
                ("J", day.j),
            ):
                item = _numeric_fact(
                    "kdj", f"{day_name} {field_name}", value,
                    unit="保存值", state=kdj.state, reason_codes=kdj.reason_codes,
                )
                if item is not None:
                    numeric_facts.append(item)
    volatility = typed.volatility_entry
    if volatility is not None:
        for label, measure in (
            ("Bandwidth", volatility.evidence.bandwidth),
            ("ATR14 SMA", volatility.evidence.atr14_sma),
        ):
            for value_label, value, unit in (
                (label, measure.value, measure.unit),
                (
                    label + " 正規化",
                    measure.normalized_value,
                    measure.normalized_unit or measure.unit,
                ),
            ):
                item = _numeric_fact(
                    "volatility", value_label, value, unit=unit,
                    state=measure.state, reason_codes=measure.reason_codes,
                )
                if item is not None:
                    numeric_facts.append(item)

    return CompositeRowPresentationV1(
        stock_code=typed.stock_code,
        technical_status=status,
        row_scope=typed.filter_evaluation.row_scope,
        groups=tuple(groups),
        composite_truth=typed.evaluation.composite_truth,
        hard_eligible=typed.evaluation.hard_eligible,
        audit_visible=typed.evaluation.audit_visible,
        included_by_unknown_policy=typed.evaluation.included_by_unknown_policy,
        predicate_match=typed.evaluation.predicate_match,
        visible=typed.evaluation.visible,
        numeric_facts=tuple(numeric_facts),
        current_only=True,
        official_available_at=None,
        availability_status="unknown",
        historical_pit_eligible=False,
        row_identity_sha256=typed.row_identity_sha256,
    )


def present_composite_counts_v1(
    result: DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV1,
) -> CompositeGlobalCountsPresentationV1:
    """從完整 reader-issued result counts 建立母體分母，不讀 page counts。"""
    typed = _require_result(result)
    counts = typed.counts
    population = counts.base_f17_counts.population
    return CompositeGlobalCountsPresentationV1(
        declared_count=population.declared_count,
        included_count=population.included_count,
        processed_count=population.processed_count,
        excluded_count=population.excluded_count,
        pending_count=population.pending_count,
        base_f17_matching_count=counts.base_f17_counts.matching_count,
        hard_eligible_count=counts.hard_eligible_count,
        active_evaluable_count=counts.active_evaluable_count,
        audit_visible_count=counts.audit_visible_count,
        visible_count=counts.visible_count,
        unknown_policy_included_count=counts.unknown_policy_included_count,
        unknown_policy_excluded_count=counts.unknown_policy_excluded_count,
        technical_truth_counts=counts.technical_truth_counts,
        ma_truth_counts=counts.ma_truth_counts,
        kdj_truth_counts=counts.kdj_truth_counts,
        volatility_truth_counts=counts.volatility_truth_counts,
        composite_truth_counts=counts.composite_truth_counts,
        ma_state_counts=counts.ma_state_counts,
        kdj_state_counts=counts.kdj_state_counts,
        bandwidth_state_counts=counts.bandwidth_state_counts,
        atr14_state_counts=counts.atr14_state_counts,
        result_status=typed.result_status,
        official_source_coverage_status=typed.official_source_coverage_status,
        current_only=True,
        official_available_at=None,
        availability_status="unknown",
        historical_pit_eligible=False,
    )


def present_composite_page_v1(
    result: DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV1,
    page: DailyMarketTechnicalOfficialDispositionCompositeQueryPageV1,
) -> CompositePagePresentationV1:
    """頁面只提供列與頁碼；母體統計一律取自同次完整 result。"""
    typed_result = _require_result(result)
    if type(page) is not DailyMarketTechnicalOfficialDispositionCompositeQueryPageV1:
        raise ValueError("composite_presenter_page_type_invalid")
    typed_page = cast(DailyMarketTechnicalOfficialDispositionCompositeQueryPageV1, page)
    typed_page.__post_init__()
    if (
        typed_page._result is not typed_result
        or typed_page.query is not typed_result.query
        or typed_page.operation_identity_sha256 != typed_result.operation_identity_sha256
        or typed_page.source_pins != typed_result.source_pins
        or typed_page.counts is not typed_result.counts
    ):
        raise ValueError("composite_presenter_page_owner_mismatch")
    global_counts = present_composite_counts_v1(typed_result)
    return CompositePagePresentationV1(
        global_counts=global_counts,
        page_index=typed_page.page_index,
        page_size=typed_page.page_size,
        page_count=typed_page.page_count,
        page_row_count=len(typed_page.rows),
        rows=tuple(present_composite_row_v1(row) for row in typed_page.rows),
        operation_identity_sha256=typed_page.operation_identity_sha256,
        page_identity_sha256=typed_page.page_identity_sha256,
    )


def format_composite_counts_v1(
    result: DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV1,
) -> str:
    """用完整 result 的全域 counts 呈現母體與政策後可見數。"""
    view = present_composite_counts_v1(result)
    lines = [
        f"母體：宣告 {view.declared_count}；納入 {view.included_count}；排除 {view.excluded_count}",
        f"處理：已處理 {view.processed_count}；待處理 {view.pending_count}",
        f"F17 原始符合：{view.base_f17_matching_count}；hard eligible：{view.hard_eligible_count}；active evaluable：{view.active_evaluable_count}",
        f"audit 可見：{view.audit_visible_count}；政策後可見：{view.visible_count}",
        f"未知政策：納入 {view.unknown_policy_included_count}；排除 {view.unknown_policy_excluded_count}",
    ]
    for group, counts in (
        ("技術條件", view.technical_truth_counts),
        ("四均線排列", view.ma_truth_counts),
        ("KDJ", view.kdj_truth_counts),
        ("波動條件", view.volatility_truth_counts),
        ("複合結果", view.composite_truth_counts),
    ):
        lines.append(group + "：" + "；".join(
            f"{_TRUTH_LABELS.get(state, state)} {count}" for state, count in counts
        ))
    lines.extend((
        f"查詢狀態：{view.result_status}；官方來源覆蓋：{view.official_source_coverage_status}",
        "範圍：current-only；official available_at 未知；historical PIT 不適用。",
    ))
    return "\n".join(lines)


def format_composite_row_v1(
    row: DailyMarketTechnicalOfficialDispositionCompositeResultRowV1,
) -> str:
    """呈現一列保存事實、四群 truth 與明確原因，不建立交易訊號。"""
    view = present_composite_row_v1(row)
    lines = [
        f"股票代碼：{view.stock_code}",
        f"母體範圍：{_ROW_SCOPE_LABELS.get(view.row_scope, view.row_scope)}；處理狀態：{view.technical_status}",
    ]
    for group in view.groups:
        state = "啟用" if group.active else "未啟用"
        lines.append(f"{group.label}：{group.truth_label}（{state}）")
        lines.extend(f"  原因：{reason}" for reason in group.reason_codes)
        lines.extend(f"  保存事實：{detail}" for detail in group.evidence_lines)
    lines.extend((
        f"複合結果：{_TRUTH_LABELS[view.composite_truth]}；hard eligible：{'是' if view.hard_eligible else '否'}；audit 可見：{'是' if view.audit_visible else '否'}",
        f"未知政策納入：{'是' if view.included_by_unknown_policy else '否'}；predicate match：{'是' if view.predicate_match else '否'}；可見：{'是' if view.visible else '否'}",
    ))
    for item in view.numeric_facts:
        lines.append(f"保存數值 {item.group}/{item.label}：{item.value_text} {item.unit}（{item.state}）")
        lines.extend(f"  原因：{reason}" for reason in item.reason_codes)
    lines.append("範圍：current-only；official available_at 未知；historical PIT 不適用。")
    return "\n".join(lines)


def format_composite_page_v1(
    result: DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV1,
    page: DailyMarketTechnicalOfficialDispositionCompositeQueryPageV1,
) -> str:
    """同時呈現全域 counts 與本頁筆數，避免把 page 當成母體。"""
    view = present_composite_page_v1(result, page)
    typed_page = cast(DailyMarketTechnicalOfficialDispositionCompositeQueryPageV1, page)
    lines = [
        format_composite_counts_v1(result),
        f"目前頁面：{view.page_index + 1}/{view.page_count}；本頁列數 {view.page_row_count}／每頁上限 {view.page_size}",
    ]
    lines.extend(format_composite_row_v1(row) for row in typed_page.rows)
    return "\n\n".join(lines)
