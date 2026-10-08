"""F07 價格收藏只保留 exact query/page/code 的重開錨點。"""

from __future__ import annotations

from typing import Any, Callable

import pytest

from app_module.daily_market_technical_universe_price_bookmark_v1 import (
    DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_BOOKMARK_V1_SCHEMA,
    DailyMarketTechnicalUniversePriceBookmarkV1,
    DailyMarketTechnicalUniversePriceBookmarkV1Error,
    create_daily_market_technical_universe_price_bookmark_v1,
    read_daily_market_technical_universe_price_bookmark_v1,
)
from app_module.daily_market_technical_universe_price_comparison_v1 import (
    DailyMarketTechnicalUniversePriceSelectionV1,
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
) -> tuple[
    DailyMarketTechnicalUniversePriceQueryV1,
    DailyMarketTechnicalUniversePricePageV1,
    DailyMarketTechnicalUniversePriceSelectionV1,
]:
    query = session.create_query(unknown_price_policy="include")
    result = session.execute(query)
    request = result.create_page_request(0, page_size=4)
    page = result.read_page(request)
    return query, page, DailyMarketTechnicalUniversePriceSelectionV1.from_page(query, page, stock_code)


def test_price_bookmark_roundtrips_and_fresh_reopens_grouped_source(
    exact_price_store: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _open_session(exact_price_store)
    query, page, selected = _selection_for(session, "S0001")
    _comparison_query, _comparison_page, comparison_one = _selection_for(session, "S0002")
    _unknown_query, _unknown_page, comparison_two = _selection_for(session, "S0003")
    bookmark = create_daily_market_technical_universe_price_bookmark_v1(
        query,
        page,
        "S0001",
        scroll_position=37,
        comparison_selections=(comparison_one, comparison_two),
    )

    encoded = bookmark.to_json()
    decoded = DailyMarketTechnicalUniversePriceBookmarkV1.from_json(encoded)
    assert decoded == bookmark
    assert bookmark.stock_code == "S0001"
    assert bookmark.source_id == bookmark.bookmark_identity_sha256
    assert bookmark.bookmark_id == bookmark.bookmark_identity_sha256
    assert bookmark.to_dict()["schema_version"] == DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_BOOKMARK_V1_SCHEMA
    assert bookmark.to_dict()["bookmark_is_reader_certification"] is False

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
    state = read_daily_market_technical_universe_price_bookmark_v1(decoded)

    assert calls == {"open": 1, "execute": 1, "page": 1}
    assert state.selected.selection.to_dict() == selected.to_dict()
    assert state.selected.row.technical_row.stock_code == "S0001"
    assert state.comparison is not None
    assert tuple(column.selection.stock_code for column in state.comparison.columns) == ("S0002", "S0003")
    assert state.comparison.columns[-1].row.price_state == "unknown"
    assert state.bookmark.scroll_position == 37


def test_price_bookmark_rejects_single_comparison_duplicate_and_identity_tamper(
    exact_price_store: dict[str, Any],
) -> None:
    session = _open_session(exact_price_store)
    query, page, selected = _selection_for(session, "S0001")
    _query_two, _page_two, second = _selection_for(session, "S0002")

    with pytest.raises(DailyMarketTechnicalUniversePriceBookmarkV1Error) as one_item:
        DailyMarketTechnicalUniversePriceBookmarkV1.create(
            selected=selected,
            scroll_position=0,
            comparison_selections=(second,),
        )
    assert one_item.value.code == "technical_universe_price_bookmark_comparison_count_invalid"

    with pytest.raises(DailyMarketTechnicalUniversePriceBookmarkV1Error) as duplicate:
        create_daily_market_technical_universe_price_bookmark_v1(
            query,
            page,
            "S0001",
            scroll_position=0,
            comparison_selections=(second, second),
        )
    assert duplicate.value.code == "technical_universe_price_bookmark_duplicate_selection"

    valid = DailyMarketTechnicalUniversePriceBookmarkV1.create(
        selected=selected,
        scroll_position=0,
    )
    payload = valid.to_dict()
    payload["bookmark_identity_sha256"] = "0" * 64
    with pytest.raises(DailyMarketTechnicalUniversePriceBookmarkV1Error) as tampered:
        DailyMarketTechnicalUniversePriceBookmarkV1.from_dict(payload)
    assert tampered.value.code == "technical_universe_price_bookmark_identity_mismatch"


def test_price_bookmark_rejects_deep_payload_and_propagates_cancel(
    exact_price_store: dict[str, Any],
) -> None:
    deeply_nested = "[" * 33 + "0" + "]" * 33
    with pytest.raises(DailyMarketTechnicalUniversePriceBookmarkV1Error) as depth:
        DailyMarketTechnicalUniversePriceBookmarkV1.from_json(deeply_nested)
    assert depth.value.code == "technical_universe_price_bookmark_json_depth_limit"

    session = _open_session(exact_price_store)
    query, page, selected = _selection_for(session, "S0001")
    bookmark = create_daily_market_technical_universe_price_bookmark_v1(
        query,
        page,
        "S0001",
        scroll_position=0,
    )
    assert bookmark.selected.to_dict() == selected.to_dict()
    with pytest.raises(InterruptedError):
        read_daily_market_technical_universe_price_bookmark_v1(
            bookmark,
            cancel_callback=lambda: True,
        )
