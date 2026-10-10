"""以真正發行的 257 股票 owner fixture 驗證 presenter 欄位。"""

from __future__ import annotations

from decimal import Decimal
from typing import cast

import pytest

from app_module.daily_market_technical_official_disposition_composite_query_v1 import (
    DailyMarketTechnicalOfficialDispositionCompositeQueryPageV1,
    DailyMarketTechnicalOfficialDispositionCompositeResultRowV1,
    DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV1,
)
from ui_qt.technical_official_composite_research_presenter import (
    _decimal_text,
    format_composite_counts_v1,
    format_composite_page_v1,
    format_composite_row_v1,
    present_composite_page_v1,
    present_composite_row_v1,
)
pytest_plugins = ("test_daily_market_technical_official_disposition_composite_reader_v1",)


@pytest.fixture(scope="module")
def full257_first_page(
    full257_or_result: DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV1,
) -> DailyMarketTechnicalOfficialDispositionCompositeQueryPageV1:
    return full257_or_result.read_page(0, 256)


def test_presenter_uses_global_result_counts_and_typed_page_rows(
    full257_or_result: DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV1,
    full257_first_page: DailyMarketTechnicalOfficialDispositionCompositeQueryPageV1,
) -> None:
    result = full257_or_result
    page = full257_first_page
    assert type(page) is DailyMarketTechnicalOfficialDispositionCompositeQueryPageV1

    view = present_composite_page_v1(result, page)
    assert view.global_counts.declared_count == 258
    assert view.global_counts.included_count == 257
    assert view.global_counts.excluded_count == 1
    assert view.global_counts.processed_count == 257
    assert view.global_counts.visible_count == 257
    assert view.page_row_count == 256
    assert view.page_count == 2
    assert len(view.rows) == 256

    counts_text = format_composite_counts_v1(result)
    page_text = format_composite_page_v1(result, page)
    assert "母體：宣告 258；納入 257；排除 1" in counts_text
    assert "政策後可見：257" in counts_text
    assert "本頁列數 256／每頁上限 256" in page_text
    assert "範圍：current-only；official available_at 未知；historical PIT 不適用。" in page_text


def test_row_presentation_keeps_all_four_group_truths_reasons_and_exact_decimals(
    full257_or_result: DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV1,
    full257_first_page: DailyMarketTechnicalOfficialDispositionCompositeQueryPageV1,
) -> None:
    result = full257_or_result
    page = full257_first_page
    row = page.rows[0]
    view = present_composite_row_v1(row)

    assert tuple(item.group for item in view.groups) == (
        "technical", "ma", "kdj", "volatility",
    )
    assert tuple(item.truth for item in view.groups) == (
        row.evaluation.technical_truth,
        row.evaluation.ma_truth,
        row.evaluation.kdj_truth,
        row.evaluation.volatility_truth,
    )
    assert view.groups[0].truth == "no_match"
    assert view.groups[2].truth == "match"
    assert view.groups[1].truth == "not_applicable"
    assert view.groups[3].truth == "not_applicable"
    assert view.visible is True
    assert view.current_only is True
    assert view.official_available_at is None
    assert view.availability_status == "unknown"
    assert view.historical_pit_eligible is False
    for item in view.numeric_facts:
        assert type(item.value) is Decimal
        assert item.value_text == format(item.value, "f")

    text = format_composite_row_v1(row)
    assert "技術條件：不符合（啟用）" in text
    assert "KDJ：符合（啟用）" in text
    assert "四均線排列：不適用（未啟用）" in text
    assert "波動條件：不適用（未啟用）" in text
    assert "保存數值" in text
    assert "historical PIT 不適用" in text


def test_decimal_text_preserves_exact_scale_and_rejects_float() -> None:
    assert _decimal_text(Decimal("1.2300")) == "1.2300"
    assert _decimal_text(None) is None
    with pytest.raises(ValueError, match="composite_presenter_decimal_invalid"):
        _decimal_text(1.23)  # type: ignore[arg-type]


def test_presenter_rejects_untyped_inputs(
    full257_or_result: DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV1,
    full257_first_page: DailyMarketTechnicalOfficialDispositionCompositeQueryPageV1,
) -> None:
    result = full257_or_result
    page = full257_first_page
    with pytest.raises(ValueError, match="composite_presenter_result_type_invalid"):
        format_composite_counts_v1(
            cast(DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV1, object())
        )
    with pytest.raises(ValueError, match="composite_presenter_row_type_invalid"):
        format_composite_row_v1(
            cast(DailyMarketTechnicalOfficialDispositionCompositeResultRowV1, object())
        )

    with pytest.raises(ValueError, match="composite_presenter_page_type_invalid"):
        present_composite_page_v1(
            result,
            cast(DailyMarketTechnicalOfficialDispositionCompositeQueryPageV1, object()),
        )
