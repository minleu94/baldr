"""MA 收藏損壞時仍維持專用路由，不轉成一般研究。"""

import pytest

from app_module.daily_market_technical_official_disposition_ma_bookmark_v1 import (
    DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_RESEARCH_BOOKMARK_SOURCE,
)
from ui_qt.views.watchlist_view import WatchlistView


@pytest.mark.parametrize("version", ["v1", "v9"])
def test_invalid_ma_payload_keeps_dedicated_route(version):
    payload = {
        "schema_version": f"daily-market-technical-official-disposition-ma-bookmark.{version}",
        "bookmark_id": "unverified",
    }
    row = {
        "證券代號": "2382",
        "source": DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_RESEARCH_BOOKMARK_SOURCE,
        "source_id": "unverified",
        "research_bookmark": payload,
    }
    assert WatchlistView._row_is_technical_official_ma_bookmark(row)
    assert WatchlistView._row_declares_research_bookmark(row)
    assert WatchlistView._exact_research_bookmark_id_for_row(row) == ""
    assert WatchlistView._research_bookmark_label(payload) == "四均線官方對照收藏無效；來源不可核驗"


def test_missing_ma_payload_cannot_become_generic_research():
    row = {
        "source": DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_RESEARCH_BOOKMARK_SOURCE,
        "research_bookmark": None,
    }
    assert WatchlistView._row_is_technical_official_ma_bookmark(row)
    assert WatchlistView._row_declares_research_bookmark(row)
    assert WatchlistView._exact_research_bookmark_id_for_row(row) == ""
