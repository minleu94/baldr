"""損毀及未知月營收收藏維持來源隔離，拒絕一般股票路由。"""

import pytest

from app_module.daily_market_research_bookmark import DailyMarketResearchBookmarkError
from app_module.daily_market_technical_official_disposition_revenue_bookmark_v1 import (
    DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_BOOKMARK_SOURCE,
)
from app_module.watchlist_service import WatchlistItem, decode_daily_market_research_bookmark
from ui_qt.views.watchlist_view import WatchlistView


@pytest.mark.parametrize("version", ("v1", "v9"))
def test_invalid_revenue_bookmark_keeps_namespace_and_refuses_route(version: str) -> None:
    payload = {
        "schema_version": f"daily-market-technical-official-disposition-revenue-bookmark.{version}",
        "bookmark_identity_sha256": "a" * 64,
        "raw_evidence": "保留原收藏排錯",
    }
    item = WatchlistItem.from_mapping({
        "stock_code": "2382", "source": "manual", "research_bookmark": payload,
    })
    assert item.source == DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_BOOKMARK_SOURCE
    assert item.research_bookmark == payload
    row = {"stock_code": "2382", "source": item.source,
           "source_id": "a" * 64, "research_bookmark": payload}
    assert WatchlistView._row_is_technical_official_revenue_bookmark(row)
    assert WatchlistView._row_declares_research_bookmark(row)
    assert WatchlistView._exact_research_bookmark_id_for_row(row) == ""
    with pytest.raises(DailyMarketResearchBookmarkError):
        decode_daily_market_research_bookmark(payload)
