"""以唯讀 V3 複合查詢 DTO 呈現四群與 F07 價格閘門。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal, cast

from app_module.daily_market_technical_universe_price_query_v1 import (
    DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_UNIT,
)
import app_module.daily_market_technical_official_disposition_composite_query_v2 as composite_v2
from ui_qt.technical_official_composite_research_presenter import (
    CompositeGlobalCountsPresentationV1,
    CompositeNumericFactV1,
    CompositeRowPresentationV1,
    present_composite_row_v1,
)


TruthV2 = Literal[
    "match", "no_match", "unknown", "not_evaluated", "not_applicable",
]

_TRUTH_LABELS = {
    "match": "符合",
    "no_match": "不符合",
    "unknown": "未知",
    "not_evaluated": "未評估",
    "not_applicable": "不適用",
}
_GROUP_LABELS = {
    "technical": "技術條件",
    "ma": "四均線排列",
    "kdj": "KDJ",
    "volatility": "波動條件",
}


def _require_result(
    value: object,
) -> composite_v2.DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV2:
    expected = composite_v2.DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV2
    if type(value) is not expected:
        raise ValueError("composite_presenter_v2_result_type_invalid")
    result = cast(
        composite_v2.DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV2,
        value,
    )
    result.__post_init__()
    result.to_json()
    return result


def _require_row(
    value: object,
) -> composite_v2.DailyMarketTechnicalOfficialDispositionCompositeResultRowV2:
    expected = composite_v2.DailyMarketTechnicalOfficialDispositionCompositeResultRowV2
    if type(value) is not expected:
        raise ValueError("composite_presenter_v2_row_type_invalid")
    row = cast(
        composite_v2.DailyMarketTechnicalOfficialDispositionCompositeResultRowV2,
        value,
    )
    row.to_dict()
    if row.price_state != row.evaluation.price_truth:
        raise ValueError("composite_presenter_v2_price_truth_mismatch")
    return row


def _decimal_text(value: Decimal | None) -> str | None:
    if value is None:
        return None
    if type(value) is not Decimal or not value.is_finite():
        raise ValueError("composite_presenter_v2_decimal_invalid")
    return format(value, "f")


def _truth_counts(value: tuple[tuple[str, int], ...]) -> tuple[tuple[TruthV2, int], ...]:
    expected = ("match", "no_match", "unknown", "not_evaluated", "not_applicable")
    if (
        type(value) is not tuple
        or tuple(key for key, _count in value) != expected
        or any(type(count) is not int or count < 0 for _key, count in value)
    ):
        raise ValueError("composite_presenter_v2_truth_counts_invalid")
    return cast(tuple[tuple[TruthV2, int], ...], value)


@dataclass(frozen=True, slots=True)
class CompositePriceGatePresentationV2:
    truth: TruthV2
    active: bool
    status: Literal["known", "unknown", "not_provided"]
    close_price: Decimal | None
    close_price_text: str | None
    observation_date: date | None
    unit: str
    reason_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CompositePriceFilterPresentationV2:
    active: bool
    min_close_price: Decimal | None
    min_close_price_text: str | None
    min_inclusive: bool
    max_close_price: Decimal | None
    max_close_price_text: str | None
    max_inclusive: bool
    unknown_price_policy: Literal["include", "exclude", "only"]
    unit: str


@dataclass(frozen=True, slots=True)
class CompositeRowPresentationV2:
    base_four_group: CompositeRowPresentationV1
    price_gate: CompositePriceGatePresentationV2
    final_composite_truth: TruthV2
    hard_eligible: bool
    audit_visible: bool
    included_by_unknown_policy: bool
    predicate_match: bool
    visible: bool
    row_identity_sha256: str

    @property
    def stock_code(self) -> str:
        return self.base_four_group.stock_code

    @property
    def four_group_truths(self) -> tuple[tuple[str, TruthV2, bool], ...]:
        return tuple(
            (group.group, cast(TruthV2, group.truth), group.active)
            for group in self.base_four_group.groups
        )

    @property
    def numeric_facts(self) -> tuple[CompositeNumericFactV1, ...]:
        return self.base_four_group.numeric_facts

    @property
    def current_only(self) -> Literal[True]:
        return True

    @property
    def official_available_at(self) -> None:
        return None

    @property
    def availability_status(self) -> Literal["unknown"]:
        return "unknown"

    @property
    def historical_pit_eligible(self) -> Literal[False]:
        return False


@dataclass(frozen=True, slots=True)
class CompositeGlobalCountsPresentationV2:
    base_four_group_counts: CompositeGlobalCountsPresentationV1
    price_filter: CompositePriceFilterPresentationV2
    declared_count: int
    included_count: int
    processed_count: int
    excluded_count: int
    pending_count: int
    base_f17_matching_count: int
    base_four_group_visible_count: int
    visible_count: int
    price_known_count: int
    price_unknown_count: int
    technical_truth_counts: tuple[tuple[TruthV2, int], ...]
    ma_truth_counts: tuple[tuple[TruthV2, int], ...]
    kdj_truth_counts: tuple[tuple[TruthV2, int], ...]
    volatility_truth_counts: tuple[tuple[TruthV2, int], ...]
    base_composite_truth_counts: tuple[tuple[TruthV2, int], ...]
    price_truth_counts: tuple[tuple[TruthV2, int], ...]
    final_truth_counts: tuple[tuple[TruthV2, int], ...]
    result_status: Literal["complete", "partial"]
    official_source_coverage_status: Literal["complete", "partial"]
    current_only: Literal[True]
    official_available_at: None
    availability_status: Literal["unknown"]
    historical_pit_eligible: Literal[False]


@dataclass(frozen=True, slots=True)
class CompositePagePresentationV2:
    global_counts: CompositeGlobalCountsPresentationV2
    page_index: int
    page_size: int
    page_count: int
    page_row_count: int
    rows: tuple[CompositeRowPresentationV2, ...]
    operation_identity_sha256: str
    page_identity_sha256: str


def present_composite_row_v2(
    value: composite_v2.DailyMarketTechnicalOfficialDispositionCompositeResultRowV2,
) -> CompositeRowPresentationV2:
    """沿用已核四群列呈現，另明示 F07 gate 與最終 AND 結果。"""
    row = _require_row(value)
    base = present_composite_row_v1(row.base_row)
    fact = row.price_fact
    if fact is None:
        price_status: Literal["known", "unknown", "not_provided"] = "not_provided"
        close_price = None
        observation_date = None
        reasons: tuple[str, ...] = ()
    else:
        fact.__post_init__()
        price_status = cast(Literal["known", "unknown"], fact.status)
        close_price = fact.close_price
        observation_date = fact.observation_date
        reasons = fact.reason_codes
    gate_active = row.evaluation.active_groups[4]
    return CompositeRowPresentationV2(
        base_four_group=base,
        price_gate=CompositePriceGatePresentationV2(
            truth=cast(TruthV2, row.evaluation.price_truth),
            active=gate_active,
            status=price_status,
            close_price=close_price,
            close_price_text=_decimal_text(close_price),
            observation_date=observation_date,
            unit=DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_UNIT,
            reason_codes=reasons,
        ),
        final_composite_truth=cast(TruthV2, row.evaluation.composite_truth),
        hard_eligible=row.evaluation.hard_eligible,
        audit_visible=row.evaluation.audit_visible,
        included_by_unknown_policy=row.evaluation.included_by_unknown_policy,
        predicate_match=row.evaluation.predicate_match,
        visible=row.evaluation.visible,
        row_identity_sha256=row.row_identity_sha256,
    )


def present_composite_counts_v2(
    value: composite_v2.DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV2,
) -> CompositeGlobalCountsPresentationV2:
    """使用 reader-issued 全域分母，不以目前頁面的列數代替母體。"""
    result = _require_result(value)
    counts = result.counts
    query = result.query
    population = counts.base_f17_counts.population
    base = counts.base_composite_counts
    base_four_group = CompositeGlobalCountsPresentationV1(
        declared_count=population.declared_count,
        included_count=population.included_count,
        processed_count=population.processed_count,
        excluded_count=population.excluded_count,
        pending_count=population.pending_count,
        base_f17_matching_count=counts.base_f17_counts.matching_count,
        hard_eligible_count=base.hard_eligible_count,
        active_evaluable_count=base.active_evaluable_count,
        audit_visible_count=base.audit_visible_count,
        visible_count=counts.base_visible_count,
        unknown_policy_included_count=base.unknown_policy_included_count,
        unknown_policy_excluded_count=base.unknown_policy_excluded_count,
        technical_truth_counts=_truth_counts(base.technical_truth_counts),
        ma_truth_counts=_truth_counts(base.ma_truth_counts),
        kdj_truth_counts=_truth_counts(base.kdj_truth_counts),
        volatility_truth_counts=_truth_counts(base.volatility_truth_counts),
        composite_truth_counts=_truth_counts(base.composite_truth_counts),
        ma_state_counts=base.ma_state_counts,
        kdj_state_counts=base.kdj_state_counts,
        bandwidth_state_counts=base.bandwidth_state_counts,
        atr14_state_counts=base.atr14_state_counts,
        result_status=result.result_status,
        official_source_coverage_status=result.official_source_coverage_status,
        current_only=True,
        official_available_at=None,
        availability_status="unknown",
        historical_pit_eligible=False,
    )
    return CompositeGlobalCountsPresentationV2(
        base_four_group_counts=base_four_group,
        price_filter=CompositePriceFilterPresentationV2(
            active=query.active_price_filter,
            min_close_price=query.min_close_price,
            min_close_price_text=_decimal_text(query.min_close_price),
            min_inclusive=query.min_inclusive,
            max_close_price=query.max_close_price,
            max_close_price_text=_decimal_text(query.max_close_price),
            max_inclusive=query.max_inclusive,
            unknown_price_policy=cast(
                Literal["include", "exclude", "only"],
                query.unknown_price_policy,
            ),
            unit=DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_UNIT,
        ),
        declared_count=population.declared_count,
        included_count=population.included_count,
        processed_count=population.processed_count,
        excluded_count=population.excluded_count,
        pending_count=population.pending_count,
        base_f17_matching_count=counts.base_f17_counts.matching_count,
        base_four_group_visible_count=counts.base_visible_count,
        visible_count=counts.visible_count,
        price_known_count=counts.price_known_count,
        price_unknown_count=counts.price_unknown_count,
        technical_truth_counts=_truth_counts(base.technical_truth_counts),
        ma_truth_counts=_truth_counts(base.ma_truth_counts),
        kdj_truth_counts=_truth_counts(base.kdj_truth_counts),
        volatility_truth_counts=_truth_counts(base.volatility_truth_counts),
        base_composite_truth_counts=_truth_counts(base.composite_truth_counts),
        price_truth_counts=_truth_counts(counts.price_truth_counts),
        final_truth_counts=_truth_counts(counts.final_truth_counts),
        result_status=result.result_status,
        official_source_coverage_status=result.official_source_coverage_status,
        current_only=True,
        official_available_at=None,
        availability_status="unknown",
        historical_pit_eligible=False,
    )


def present_composite_page_v2(
    result: composite_v2.DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV2,
    page: composite_v2.DailyMarketTechnicalOfficialDispositionCompositeQueryPageV2,
) -> CompositePagePresentationV2:
    """檢查頁面仍屬同一 reader-issued result，再投影 typed rows。"""
    typed_result = _require_result(result)
    expected_page = composite_v2.DailyMarketTechnicalOfficialDispositionCompositeQueryPageV2
    if type(page) is not expected_page:
        raise ValueError("composite_presenter_v2_page_type_invalid")
    typed_page = cast(
        composite_v2.DailyMarketTechnicalOfficialDispositionCompositeQueryPageV2,
        page,
    )
    typed_page.__post_init__()
    typed_page.to_json()
    if (
        typed_page._result is not typed_result
        or typed_page.query is not typed_result.query
        or typed_page.operation_identity_sha256 != typed_result.operation_identity_sha256
        or typed_page.source_pins != typed_result.source_pins
        or typed_page.counts != typed_result.counts
    ):
        raise ValueError("composite_presenter_v2_page_owner_mismatch")
    return CompositePagePresentationV2(
        global_counts=present_composite_counts_v2(typed_result),
        page_index=typed_page.page_index,
        page_size=typed_page.page_size,
        page_count=typed_page.page_count,
        page_row_count=len(typed_page.rows),
        rows=tuple(present_composite_row_v2(row) for row in typed_page.rows),
        operation_identity_sha256=typed_page.operation_identity_sha256,
        page_identity_sha256=typed_page.page_identity_sha256,
    )


def _format_truth_counts(value: tuple[tuple[TruthV2, int], ...]) -> str:
    return "；".join(f"{_TRUTH_LABELS[truth]} {count}" for truth, count in value)


def format_composite_counts_v2(
    result: composite_v2.DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV2,
) -> str:
    """分開列出原四群計數、價格 gate 計數與最終可見數。"""
    view = present_composite_counts_v2(result)
    lines = [
        f"母體：宣告 {view.declared_count}；納入 {view.included_count}；排除 {view.excluded_count}",
        f"處理：已處理 {view.processed_count}；待處理 {view.pending_count}",
        f"F17 原始符合：{view.base_f17_matching_count}",
        "F07 查詢範圍："
        f"下限 {view.price_filter.min_close_price_text if view.price_filter.min_close_price_text is not None else '未設定'}"
        f"（{'含' if view.price_filter.min_inclusive else '不含'}）；"
        f"上限 {view.price_filter.max_close_price_text if view.price_filter.max_close_price_text is not None else '未設定'}"
        f"（{'含' if view.price_filter.max_inclusive else '不含'}）；"
        f"未知價格政策 {view.price_filter.unknown_price_policy}；單位 {view.price_filter.unit}",
        "四群資格："
        f"hard eligible {view.base_four_group_counts.hard_eligible_count}；"
        f"active evaluable {view.base_four_group_counts.active_evaluable_count}；"
        f"audit 可見 {view.base_four_group_counts.audit_visible_count}",
        "四群未知政策："
        f"納入 {view.base_four_group_counts.unknown_policy_included_count}；"
        f"排除 {view.base_four_group_counts.unknown_policy_excluded_count}",
        f"四群原可見：{view.base_four_group_visible_count}；F07 gate 後可見：{view.visible_count}",
        f"F07 價格列：已知 {view.price_known_count}；未知 {view.price_unknown_count}",
    ]
    for label, values in (
        ("技術條件", view.technical_truth_counts),
        ("四均線排列", view.ma_truth_counts),
        ("KDJ", view.kdj_truth_counts),
        ("波動條件", view.volatility_truth_counts),
        ("四群原複合結果", view.base_composite_truth_counts),
        ("F07 價格 gate", view.price_truth_counts),
        ("最終複合結果", view.final_truth_counts),
    ):
        lines.append(f"{label}：{_format_truth_counts(values)}")
    lines.extend((
        f"查詢狀態：{view.result_status}；官方來源覆蓋：{view.official_source_coverage_status}",
        "範圍：current-only；official available_at 未知；historical PIT 不適用。",
    ))
    return "\n".join(lines)


def format_composite_row_v2(
    row: composite_v2.DailyMarketTechnicalOfficialDispositionCompositeResultRowV2,
) -> str:
    """呈現四群原結果、F07 價格閘門與最後 AND 判定。"""
    view = present_composite_row_v2(row)
    gate = view.price_gate
    value_text = gate.close_price_text if gate.close_price_text is not None else "未提供"
    observation_text = (
        gate.observation_date.isoformat() if gate.observation_date is not None else "未提供"
    )
    lines = [
        f"股票代碼：{view.stock_code}",
        "四群條件：" + "；".join(
            f"{_GROUP_LABELS[name]} {_TRUTH_LABELS[truth]}（{'啟用' if active else '未啟用'}）"
            for name, truth, active in view.four_group_truths
        ),
        f"四群原複合結果：{_TRUTH_LABELS[view.base_four_group.composite_truth]}",
        f"F07 價格閘門：{_TRUTH_LABELS[gate.truth]}（{'啟用' if gate.active else '未啟用'}）",
        f"收盤價：{value_text} {gate.unit}；觀測日：{observation_text}；狀態：{gate.status}",
        "價格原因：" + ("、".join(gate.reason_codes) if gate.reason_codes else "無"),
        f"最終複合結果（四群結果 AND 價格閘門）：{_TRUTH_LABELS[view.final_composite_truth]}",
        f"可見：{'是' if view.visible else '否'}；未知政策納入：{'是' if view.included_by_unknown_policy else '否'}；predicate match：{'是' if view.predicate_match else '否'}",
        "範圍：current-only；official available_at 未知；historical PIT 不適用。",
    ]
    return "\n".join(lines)


def format_composite_page_v2(
    result: composite_v2.DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV2,
    page: composite_v2.DailyMarketTechnicalOfficialDispositionCompositeQueryPageV2,
) -> str:
    """同時呈現完整母體統計和目前頁面列數。"""
    view = present_composite_page_v2(result, page)
    typed_page = cast(
        composite_v2.DailyMarketTechnicalOfficialDispositionCompositeQueryPageV2,
        page,
    )
    lines = [
        format_composite_counts_v2(result),
        f"目前頁面：{view.page_index + 1}/{view.page_count}；本頁列數 {view.page_row_count}／每頁上限 {view.page_size}",
    ]
    lines.extend(format_composite_row_v2(row) for row in typed_page.rows)
    return "\n\n".join(lines)


__all__ = (
    "CompositeGlobalCountsPresentationV2",
    "CompositePagePresentationV2",
    "CompositePriceFilterPresentationV2",
    "CompositePriceGatePresentationV2",
    "CompositeRowPresentationV2",
    "format_composite_counts_v2",
    "format_composite_page_v2",
    "format_composite_row_v2",
    "present_composite_counts_v2",
    "present_composite_page_v2",
    "present_composite_row_v2",
)
