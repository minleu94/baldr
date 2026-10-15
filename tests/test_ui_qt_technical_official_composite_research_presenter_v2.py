"""驗證 V2 presenter 同時保留四群基線與 F07 價格 gate。"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app_module.daily_market_technical_official_disposition_composite_query_v1 import (
    DailyMarketTechnicalOfficialDispositionCompositeQueryV1,
)
from app_module.daily_market_technical_official_disposition_composite_query_v2 import (
    DailyMarketTechnicalOfficialDispositionCompositeQueryPageV2,
    DailyMarketTechnicalOfficialDispositionCompositeQueryV2,
    DailyMarketTechnicalOfficialDispositionCompositeResultRowV2,
    DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV2,
    execute_composite_query_v2,
)
from ui_qt.technical_official_composite_research_presenter_v2 import (
    format_composite_counts_v2,
    format_composite_page_v2,
    format_composite_row_v2,
    present_composite_counts_v2,
    present_composite_page_v2,
    present_composite_row_v2,
)

pytest_plugins = (
    "test_daily_market_technical_official_disposition_composite_query_v2",
)


@pytest.fixture(scope="module")
def verified_v2_result(
    exact_query,
    projection_group_session_v3,
) -> DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV2:
    session = projection_group_session_v3
    known_prices = tuple(
        fact.close_price
        for fact in session.price_facts
        if fact.status == "known" and fact.close_price is not None
    )
    assert known_prices
    base_query = DailyMarketTechnicalOfficialDispositionCompositeQueryV1.create(
        exact_query,
        projection_group_session_identity_sha256=session.identity_sha256,
    )
    query = DailyMarketTechnicalOfficialDispositionCompositeQueryV2.create(
        base_query,
        min_close_price=min(known_prices),
        max_close_price=max(known_prices),
        unknown_price_policy="include",
    )
    result = execute_composite_query_v2(query, session)
    assert result.visible_count > 0
    return result


@pytest.fixture(scope="module")
def first_v2_page(
    verified_v2_result: DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV2,
) -> DailyMarketTechnicalOfficialDispositionCompositeQueryPageV2:
    return verified_v2_result.read_page(0, 32)


def test_v2_presenter_uses_full_cohort_counts_and_separate_price_gate(
    verified_v2_result: DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV2,
    first_v2_page: DailyMarketTechnicalOfficialDispositionCompositeQueryPageV2,
) -> None:
    result = verified_v2_result
    view = present_composite_counts_v2(result)
    assert result.query.min_close_price is not None
    assert result.query.max_close_price is not None
    assert view.declared_count == result.counts.base_f17_counts.population.declared_count
    assert view.processed_count == result.counts.base_f17_counts.population.processed_count
    assert view.base_four_group_visible_count == result.counts.base_visible_count
    assert view.visible_count == result.counts.visible_count
    assert view.price_known_count == result.counts.price_known_count
    assert view.price_unknown_count == result.counts.price_unknown_count
    assert view.price_filter.active is True
    assert view.price_filter.min_close_price == result.query.min_close_price
    assert view.price_filter.min_close_price_text == format(result.query.min_close_price, "f")
    assert view.price_filter.min_inclusive is True
    assert view.price_filter.max_close_price == result.query.max_close_price
    assert view.price_filter.max_close_price_text == format(result.query.max_close_price, "f")
    assert view.price_filter.max_inclusive is True
    assert view.price_filter.unknown_price_policy == result.query.unknown_price_policy
    assert view.base_composite_truth_counts == result.counts.base_composite_counts.composite_truth_counts
    assert view.price_truth_counts == result.counts.price_truth_counts
    assert view.final_truth_counts == result.counts.final_truth_counts

    page_view = present_composite_page_v2(result, first_v2_page)
    assert page_view.global_counts == view
    assert page_view.page_row_count == len(first_v2_page.rows)
    assert page_view.global_counts.visible_count == result.visible_count
    assert "四群原可見：" in format_composite_counts_v2(result)
    assert "F07 查詢範圍：" in format_composite_counts_v2(result)
    assert "F07 gate 後可見：" in format_composite_counts_v2(result)
    assert "current-only" in format_composite_page_v2(result, first_v2_page)


def test_v2_row_presentation_keeps_four_base_truths_and_final_and_gate(
    first_v2_page: DailyMarketTechnicalOfficialDispositionCompositeQueryPageV2,
) -> None:
    assert first_v2_page.rows, "V2 fixture must contain a reader-visible row"
    row = first_v2_page.rows[0]
    view = present_composite_row_v2(row)

    assert tuple(name for name, _truth, _active in view.four_group_truths) == (
        "technical", "ma", "kdj", "volatility",
    )
    assert tuple(truth for _name, truth, _active in view.four_group_truths) == (
        row.evaluation.technical_truth,
        row.evaluation.ma_truth,
        row.evaluation.kdj_truth,
        row.evaluation.volatility_truth,
    )
    assert view.base_four_group.composite_truth == row.base_row.evaluation.composite_truth
    assert view.price_gate.truth == row.evaluation.price_truth == row.price_state
    assert view.price_gate.active is row.evaluation.active_groups[4]
    assert view.final_composite_truth == row.evaluation.composite_truth
    assert view.visible is row.evaluation.visible
    assert view.current_only is True
    assert view.official_available_at is None
    assert view.availability_status == "unknown"
    assert view.historical_pit_eligible is False
    if view.price_gate.close_price is not None:
        assert type(view.price_gate.close_price) is Decimal
        assert view.price_gate.close_price_text == format(view.price_gate.close_price, "f")
        assert view.price_gate.unit == "TWD/share"

    text = format_composite_row_v2(row)
    assert "四群原複合結果：" in text
    assert "F07 價格閘門：" in text
    assert "最終複合結果（四群結果 AND 價格閘門）：" in text


def test_v2_presenter_rejects_v1_row_and_unowned_page(
    verified_v2_result: DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV2,
    first_v2_page: DailyMarketTechnicalOfficialDispositionCompositeQueryPageV2,
) -> None:
    assert first_v2_page.rows, "V2 fixture must contain a reader-visible row"
    with pytest.raises(ValueError, match="composite_presenter_v2_row_type_invalid"):
        present_composite_row_v2(first_v2_page.rows[0].base_row)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="composite_presenter_v2_page_type_invalid"):
        present_composite_page_v2(verified_v2_result, object())  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="composite_presenter_v2_result_type_invalid"):
        present_composite_counts_v2(object())  # type: ignore[arg-type]
