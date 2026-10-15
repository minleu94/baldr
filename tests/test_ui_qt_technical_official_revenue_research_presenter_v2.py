from __future__ import annotations

from decimal import Decimal
from typing import Any, cast

import pytest

pytest_plugins = ("test_daily_market_technical_official_disposition_revenue_query_v2",)

from app_module.daily_market_technical_official_disposition_revenue_query_v1 import (
    DailyMarketTechnicalOfficialDispositionRevenueCountsV1,
    DailyMarketTechnicalOfficialDispositionRevenueResultRowV1,
)
from app_module.daily_market_technical_official_disposition_revenue_query_v2 import (
    DailyMarketTechnicalOfficialDispositionRevenueSortClauseV2,
)
from ui_qt.technical_official_revenue_research_presenter_v2 import (
    format_technical_official_revenue_counts_v2,
    format_technical_official_revenue_research_row_v2,
    revenue_row_cells_v2,
)


def _result_and_first_page(ma_context: Any, revenue_index_environment: Any) -> tuple[Any, Any]:
    bound = ma_context.session.with_monthly_revenue_yoy_index_v2(
        revenue_index_environment.session,
    )
    query = bound.create_revenue_query_v2(
        ma_states=("unknown",),
        minimum_yoy_percent=Decimal("0"),
        sort_clauses=(
            DailyMarketTechnicalOfficialDispositionRevenueSortClauseV2(
                "monthly_revenue_yoy_percent", "desc",
            ),
            DailyMarketTechnicalOfficialDispositionRevenueSortClauseV2(
                "stock_code", "asc",
            ),
        ),
    )
    result = bound.execute_revenue_query_v2(query)
    return result, result.read_page(0, 4)


def test_v2_row_preserves_decimal_separate_source_and_projection_and_all_clock_fields(
    ma_context: Any,
    revenue_index_environment: Any,
) -> None:
    result, page = _result_and_first_page(ma_context, revenue_index_environment)
    observed = next(row for row in page.rows if row.stock_code == "1000")
    unknown = next(
        row for row in page.rows
        if row.monthly_entry.projected_fact.state == "unknown"
    )

    rendered = format_technical_official_revenue_research_row_v2(observed)
    projected = observed.monthly_entry.projected_fact
    current = projected.current
    comparator = projected.comparator
    pin = projected.cohort_pin

    assert current is not None and comparator is not None
    assert f"當期月份：{current.period}" in rendered
    assert format(current.revenue, "f") in rendered
    assert f"比較基期：{comparator.period}" in rendered
    assert format(comparator.revenue, "f") in rendered
    assert projected.growth_percent == Decimal("22.006875")
    precise_growth_text = format(projected.growth_percent, "f") + "%"
    assert f"成長率：{precise_growth_text}" in rendered
    assert "原始來源事實狀態：已觀測" in rendered
    assert "YoY 投影狀態：observed" in rendered
    assert "來源時間保存值（source_available_at）" in rendered
    assert (
        current.source_available_at.isoformat() in rendered
        if current.source_available_at is not None
        else "來源時間保存值（source_available_at）：未提供" in rendered
    )
    assert "未保存未解析的來源時間文字" in rendered
    assert pin.available_hour.isoformat() in rendered
    assert pin.cohort_sha256 in rendered
    for market_pin in pin.market_pins:
        assert market_pin.batch_id in rendered
        assert market_pin.source_batch_started_at.isoformat() in rendered
        assert market_pin.first_persisted_at.isoformat() in rendered
        assert market_pin.successful_batch_completed_at.isoformat() in rendered

    cells = revenue_row_cells_v2(observed)
    assert len(cells) == 6
    assert cells[0] == observed.stock_code
    assert cells[3] == "來源 已觀測／YoY 已觀測"
    assert cells[4] == precise_growth_text

    unknown_rendered = format_technical_official_revenue_research_row_v2(unknown)
    unknown_cells = revenue_row_cells_v2(unknown)
    assert "YoY 投影狀態：unknown" in unknown_rendered
    assert "成長率：未知" in unknown_rendered
    assert "範圍：outer query current_only" in unknown_rendered
    assert "monthly_official_available_at 均未知" in unknown_rendered
    assert "historical/formal PIT 均不具資格" in unknown_rendered
    assert unknown_cells[3] == "來源 未知／YoY 未知"
    assert unknown_cells[4] == "未知"
    assert result.scope == "current_only"
    assert result.monthly_official_available_at is None
    assert result.historical_pit_eligible is False


def test_v2_counts_show_independent_full_f17_denominators_and_keep_outer_gate(
    ma_context: Any,
    revenue_index_environment: Any,
) -> None:
    result, _page = _result_and_first_page(ma_context, revenue_index_environment)
    rendered = format_technical_official_revenue_counts_v2(
        result.counts,
        result_status=result.result_status,
        official_coverage_status=result.official_source_coverage_status,
    )
    declared = result.counts.declared_count

    assert f"月營收來源事實（分母 {declared}）" in rendered
    assert f"月營收 YoY 投影（分母 {declared}）" in rendered
    assert "阻擋 0；已觀測 1；未知 257" in rendered
    assert "已觀測 1；未知 257" in rendered
    assert "官方來源覆蓋輸入：" in rendered
    assert "outer current_only" in rendered
    assert "official_available_at 與 monthly_official_available_at 未知" in rendered
    assert "historical/formal PIT 不具資格" in rendered


def test_v2_presenter_refuses_v1_and_untyped_objects_without_conversion() -> None:
    legacy_row = cast(Any, object.__new__(DailyMarketTechnicalOfficialDispositionRevenueResultRowV1))
    legacy_counts = cast(Any, object.__new__(DailyMarketTechnicalOfficialDispositionRevenueCountsV1))

    with pytest.raises(ValueError, match="presenter_v2_row_invalid"):
        format_technical_official_revenue_research_row_v2(legacy_row)
    with pytest.raises(ValueError, match="presenter_v2_row_invalid"):
        revenue_row_cells_v2(legacy_row)
    with pytest.raises(ValueError, match="presenter_v2_counts_invalid"):
        format_technical_official_revenue_counts_v2(
            legacy_counts,
            result_status="complete",
            official_coverage_status="complete",
        )

