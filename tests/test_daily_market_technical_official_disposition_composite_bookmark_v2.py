"""驗證 V2 bookmark 對 result、page、row、來源 pins 與 basket 的完整綁定。"""

from __future__ import annotations

import json

import pytest

import app_module.daily_market_technical_official_disposition_composite_bookmark_v2 as bookmark_v2
from app_module.daily_market_technical_official_disposition_composite_query_v1 import (
    DailyMarketTechnicalOfficialDispositionCompositeQueryV1,
)
from app_module.daily_market_technical_official_disposition_composite_query_v2 import (
    DailyMarketTechnicalOfficialDispositionCompositeQueryV2,
    DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV2,
    execute_composite_query_v2,
)

pytest_plugins = (
    "test_daily_market_technical_official_disposition_composite_query_v2",
)


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


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
    assert len(known_prices) >= 2
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
    assert result.visible_count >= 2
    return result


@pytest.fixture(scope="module")
def two_visible_pages(verified_v2_result):
    result = verified_v2_result
    assert result.visible_count >= 2, "V2 fixture must cover two visible pages"
    first = result.read_page(0, 1)
    second = result.read_page(1, 1)
    assert len(first.rows) == len(second.rows) == 1
    return first, second


@pytest.fixture(scope="module")
def saved_v2_bookmark(verified_v2_result, two_visible_pages):
    first, second = two_visible_pages
    return bookmark_v2.DailyMarketTechnicalOfficialDispositionCompositeBookmarkV2.create_from_real_row_context(
        verified_v2_result,
        first,
        first.rows[0].stock_code,
        scroll_position=37,
        comparison_contexts=((second, second.rows[0].stock_code),),
        basket_stock_codes=(
            first.rows[0].stock_code,
            second.rows[0].stock_code,
        ),
    )


def test_v2_bookmark_reopens_exact_rows_and_preserves_basket_on_same_v3_session(
    saved_v2_bookmark,
    projection_group_session_v3,
) -> None:
    bookmark = saved_v2_bookmark
    raw = bookmark.to_json()
    restored = bookmark_v2.DailyMarketTechnicalOfficialDispositionCompositeBookmarkV2.from_json(raw)
    saved_row = json.loads(restored.selected.row_json)
    assert "visible" not in saved_row
    assert saved_row["evaluation"]["visible"] is True
    assert restored.to_json() == raw
    assert restored.query.to_json() == bookmark.query_json
    assert restored.source_pins == bookmark.source_pins
    assert restored.basket_stock_codes == bookmark.basket_stock_codes
    assert restored.scroll_position == 37

    context = bookmark_v2.read_daily_market_technical_official_disposition_composite_bookmark_context_v2(
        raw,
        projection_group_session=projection_group_session_v3,
    )
    assert context.result.operation_identity_sha256 == bookmark.result_identity_sha256
    assert context.result.query.to_json() == bookmark.query_json
    assert context.selected.row.stock_code == bookmark.selected.stock_code
    assert context.selected.row.to_dict() == json.loads(bookmark.selected.row_json)
    assert len(context.comparison_selections) == 1
    comparison = context.comparison_selections[0]
    assert comparison.row.stock_code == bookmark.comparison_selections[0].stock_code
    assert comparison.page.page_index == bookmark.comparison_selections[0].page_index
    assert context.basket_stock_codes == bookmark.basket_stock_codes
    assert context.scroll_position == bookmark.scroll_position
    assert context.scope == "current_only"
    assert context.official_available_at is None
    assert context.availability_status == "unknown"
    assert context.historical_pit_eligible is False
    assert context.bookmark_is_reader_certification is False

    reopened = context.read_page(1, 1)
    assert reopened.page_identity_sha256 == comparison.selection.page_identity_sha256


@pytest.mark.parametrize(
    "tamper",
    (
        "bookmark_scroll",
        "bookmark_basket_member",
        "bookmark_source_pin",
        "selection_page_identity",
        "selection_page_json",
        "selection_row_bytes",
        "result_source_pin",
    ),
)
def test_v2_bookmark_rejects_tampered_saved_identities(
    saved_v2_bookmark,
    tamper: str,
) -> None:
    payload = json.loads(saved_v2_bookmark.to_json())
    if tamper == "bookmark_scroll":
        payload["scroll_position"] += 1
    elif tamper == "bookmark_basket_member":
        payload["basket_stock_codes"][0] = "ZZZZ"
    elif tamper == "bookmark_source_pin":
        payload["source_pins"][0][1] += ":tampered"
    elif tamper == "selection_page_identity":
        payload["selected"]["page_identity_sha256"] = "0" * 64
    elif tamper == "selection_page_json":
        page = json.loads(payload["selected"]["page_json"])
        page["page_identity_sha256"] = "0" * 64
        payload["selected"]["page_json"] = _canonical(page).decode("utf-8")
    elif tamper == "selection_row_bytes":
        row = json.loads(payload["selected"]["row_json"])
        evaluation = row["evaluation"]
        assert isinstance(evaluation, dict)
        evaluation["visible"] = False
        payload["selected"]["row_json"] = _canonical(row).decode("utf-8")
    else:
        result_payload = json.loads(payload["result_json"])
        result_payload["source_pins"][0][1] += ":tampered"
        payload["result_json"] = _canonical(result_payload).decode("utf-8")

    with pytest.raises(bookmark_v2.DailyMarketTechnicalOfficialDispositionCompositeBookmarkV2Error):
        bookmark_v2.DailyMarketTechnicalOfficialDispositionCompositeBookmarkV2.from_json(
            _canonical(payload)
        )


def test_v2_bookmark_restore_requires_the_callers_matching_v3_group(
    saved_v2_bookmark,
) -> None:
    with pytest.raises(
        bookmark_v2.DailyMarketTechnicalOfficialDispositionCompositeBookmarkV2Error,
        match="projection_group_session_invalid",
    ):
        bookmark_v2.read_daily_market_technical_official_disposition_composite_bookmark_context_v2(
            saved_v2_bookmark,
            projection_group_session=object(),  # type: ignore[arg-type]
        )


def test_v2_bookmark_does_not_dispatch_v1_or_accept_duplicate_json_keys(
    saved_v2_bookmark,
) -> None:
    v1_payload = {
        "schema_version": "daily-market-technical-official-disposition-composite-bookmark.v1",
    }
    with pytest.raises(bookmark_v2.DailyMarketTechnicalOfficialDispositionCompositeBookmarkV2Error):
        bookmark_v2.DailyMarketTechnicalOfficialDispositionCompositeBookmarkV2.from_json(
            _canonical(v1_payload)
        )
    with pytest.raises(
        bookmark_v2.DailyMarketTechnicalOfficialDispositionCompositeBookmarkV2Error,
        match="duplicate_json_key",
    ):
        bookmark_v2.DailyMarketTechnicalOfficialDispositionCompositeBookmarkV2.from_json(
            b'{"schema_version":"x","schema_version":"y"}'
        )

