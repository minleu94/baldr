"""F07 價格比較只重開明示的 exact 查詢與頁面。"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Callable

import pytest

from app_module.daily_market_technical_universe_price_comparison_v1 import (
    DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_COMPARISON_MAX_ITEMS,
    DailyMarketTechnicalUniversePriceComparisonV1Error,
    DailyMarketTechnicalUniversePriceSelectionV1,
    _canonical_decimal_text,
    _validate_decimal_text,
    read_daily_market_technical_universe_price_comparison_v1,
)
from app_module.daily_market_technical_universe_price_query_v1 import (
    DailyMarketTechnicalUniversePricePageRequestV1,
    DailyMarketTechnicalUniversePricePageV1,
    DailyMarketTechnicalUniversePriceQueryV1,
    DailyMarketTechnicalUniversePriceReadSessionV1,
    DailyMarketTechnicalUniversePriceResultV1,
)
from tests.test_daily_market_technical_universe_price_query_v1 import (
    _open_session,
    exact_price_store,
)
import app_module.daily_market_technical_universe_price_comparison_v1 as comparison_module


def _selection_for(
    session: DailyMarketTechnicalUniversePriceReadSessionV1,
    stock_code: str,
    *,
    minimum: Decimal | None = None,
) -> DailyMarketTechnicalUniversePriceSelectionV1:
    query = session.create_query(
        min_close_price=minimum,
        unknown_price_policy="include",
        descending=False,
    )
    result = session.execute(query)
    request = result.create_page_request(0, page_size=4)
    page = result.read_page(request)
    return DailyMarketTechnicalUniversePriceSelectionV1.from_page(query, page, stock_code)


def test_comparison_reopens_one_exact_source_and_reuses_same_query_page(
    exact_price_store: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _open_session(exact_price_store)
    known = _selection_for(session, "S0001")
    unknown = _selection_for(session, "S0003")
    calls = {"open": 0, "execute": 0, "page": 0}
    original_open = comparison_module.open_daily_market_technical_universe_price_session_for_query_v1
    original_execute = DailyMarketTechnicalUniversePriceReadSessionV1.execute
    original_read_page = DailyMarketTechnicalUniversePriceResultV1.read_page

    def counted_open(
        query: DailyMarketTechnicalUniversePriceQueryV1 | bytes | str,
        *,
        cancel_callback: Callable[[], object] | None = None,
    ) -> tuple[DailyMarketTechnicalUniversePriceReadSessionV1, DailyMarketTechnicalUniversePriceQueryV1]:
        calls["open"] += 1
        return original_open(query, cancel_callback=cancel_callback)

    def counted_execute(
        source_session: DailyMarketTechnicalUniversePriceReadSessionV1,
        query: DailyMarketTechnicalUniversePriceQueryV1,
        *,
        cancel_callback: Callable[[], object] | None = None,
    ) -> DailyMarketTechnicalUniversePriceResultV1:
        calls["execute"] += 1
        return original_execute(source_session, query, cancel_callback=cancel_callback)

    def counted_page(
        result: DailyMarketTechnicalUniversePriceResultV1,
        request: DailyMarketTechnicalUniversePricePageRequestV1,
        *,
        cancel_callback: Callable[[], object] | None = None,
    ) -> DailyMarketTechnicalUniversePricePageV1:
        calls["page"] += 1
        return original_read_page(result, request, cancel_callback=cancel_callback)

    monkeypatch.setattr(
        comparison_module,
        "open_daily_market_technical_universe_price_session_for_query_v1",
        counted_open,
    )
    monkeypatch.setattr(DailyMarketTechnicalUniversePriceReadSessionV1, "execute", counted_execute)
    monkeypatch.setattr(DailyMarketTechnicalUniversePriceResultV1, "read_page", counted_page)

    comparison = read_daily_market_technical_universe_price_comparison_v1((known, unknown))

    assert calls == {"open": 1, "execute": 1, "page": 1}
    assert tuple(column.selection.stock_code for column in comparison.columns) == ("S0001", "S0003")
    assert comparison.columns[0].row.price_fact.close_price == Decimal("100.0000000000000000000001")
    assert comparison.columns[1].row.price_state == "unknown"
    assert comparison.to_dict()["historical_pit_eligible"] is False
    assert comparison.to_dict()["source_available_at"] is None


def test_comparison_preserves_distinct_query_pins_and_rejects_duplicate_selection(
    exact_price_store: dict[str, Any],
) -> None:
    session = _open_session(exact_price_store)
    first = _selection_for(session, "S0001")
    distinct_query = _selection_for(session, "S0002", minimum=Decimal("150"))
    assert first.query.query_identity_sha256 != distinct_query.query.query_identity_sha256

    comparison = read_daily_market_technical_universe_price_comparison_v1((first, distinct_query))
    assert tuple(column.selection.query.query_identity_sha256 for column in comparison.columns) == (
        first.query.query_identity_sha256,
        distinct_query.query.query_identity_sha256,
    )
    assert tuple(column.to_dict()["decision_date"] for column in comparison.columns) == (
        first.query.source.decision_date.isoformat(),
        distinct_query.query.source.decision_date.isoformat(),
    )

    with pytest.raises(DailyMarketTechnicalUniversePriceComparisonV1Error) as duplicate:
        read_daily_market_technical_universe_price_comparison_v1((first, first))
    assert duplicate.value.code == "technical_universe_price_selection_duplicate"


def test_comparison_cancellation_propagates_and_never_publishes_partial_result(
    exact_price_store: dict[str, Any],
) -> None:
    session = _open_session(exact_price_store)
    selections = (_selection_for(session, "S0001"), _selection_for(session, "S0002"))
    with pytest.raises(InterruptedError):
        read_daily_market_technical_universe_price_comparison_v1(
            selections,
            cancel_callback=lambda: True,
        )


def test_decimal_expansion_and_deep_json_are_rejected_before_formatting() -> None:
    with pytest.raises(DailyMarketTechnicalUniversePriceComparisonV1Error) as exponent:
        _validate_decimal_text(
            "1E+999999999",
            nullable=False,
            code="comparison_price_invalid",
        )
    assert exponent.value.code == "comparison_price_invalid"

    with pytest.raises(DailyMarketTechnicalUniversePriceComparisonV1Error):
        _canonical_decimal_text(Decimal("1E+999999999"))

    deeply_nested = "[" * 33 + "0" + "]" * 33
    with pytest.raises(DailyMarketTechnicalUniversePriceComparisonV1Error) as depth:
        DailyMarketTechnicalUniversePriceSelectionV1.from_json(deeply_nested)
    assert depth.value.code == "technical_universe_price_comparison_json_depth_limit"


def test_comparison_count_is_bounded_before_any_source_reopen(
    exact_price_store: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _open_session(exact_price_store)
    selection = _selection_for(session, "S0001")
    open_calls = 0
    original_open = comparison_module.open_daily_market_technical_universe_price_session_for_query_v1

    def counted_open(
        query: DailyMarketTechnicalUniversePriceQueryV1 | bytes | str,
        *,
        cancel_callback: Callable[[], object] | None = None,
    ) -> tuple[DailyMarketTechnicalUniversePriceReadSessionV1, DailyMarketTechnicalUniversePriceQueryV1]:
        nonlocal open_calls
        open_calls += 1
        return original_open(query, cancel_callback=cancel_callback)

    monkeypatch.setattr(
        comparison_module,
        "open_daily_market_technical_universe_price_session_for_query_v1",
        counted_open,
    )
    with pytest.raises(DailyMarketTechnicalUniversePriceComparisonV1Error) as count_error:
        read_daily_market_technical_universe_price_comparison_v1(
            tuple(selection for _ in range(DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_COMPARISON_MAX_ITEMS + 1))
        )
    assert count_error.value.code == "technical_universe_price_comparison_count_invalid"
    assert open_calls == 0


def test_comparison_total_bytes_are_bounded_before_source_open(
    exact_price_store: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _open_session(exact_price_store)
    selection = _selection_for(session, "S0001")
    one_size = len(selection.to_json().encode("utf-8"))
    monkeypatch.setattr(
        comparison_module,
        "DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_COMPARISON_MAX_BYTES",
        one_size * 2 - 1,
    )
    with pytest.raises(DailyMarketTechnicalUniversePriceComparisonV1Error) as size_error:
        comparison_module.read_daily_market_technical_universe_price_selections_v1(
            (selection, selection)
        )
    assert size_error.value.code == "technical_universe_price_comparison_byte_limit"
