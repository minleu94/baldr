"""價格收藏以獨立版本沿觀察清單保存，拒絕轉一般研究。"""

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app_module.daily_market_research_bookmark import DailyMarketResearchBookmarkError
from app_module.daily_market_technical_universe_price_bookmark_v1 import (
    DailyMarketTechnicalUniversePriceBookmarkV1,
    create_daily_market_technical_universe_price_bookmark_v1,
)
from app_module.watchlist_service import (
    TECHNICAL_UNIVERSE_PRICE_BOOKMARK_SOURCE,
    WatchlistService,
)
from tests.test_daily_market_technical_universe_price_query_v1 import (
    _open_session,
    exact_price_store,
)


def test_price_bookmark_persists_deduplicates_and_restores_exact_payload(
    exact_price_store: dict[str, Any], tmp_path: Path,
) -> None:
    session = _open_session(exact_price_store)
    query = session.create_query(unknown_price_policy="include")
    result = session.execute(query)
    page = result.read_page(result.create_page_request(0, page_size=4))
    bookmark = create_daily_market_technical_universe_price_bookmark_v1(
        query, page, "S0001", scroll_position=37,
    )
    output = tmp_path / "private_output"
    config = SimpleNamespace(output_root=output, resolve_output_path=lambda name: output / name)
    service = WatchlistService(config)
    assert service.add_research_bookmark(bookmark).status == "added"
    assert service.add_research_bookmark(bookmark).status == "already_present"
    reopened = WatchlistService(config)
    loaded = reopened.get_research_bookmark(bookmark.bookmark_id)
    assert type(loaded) is DailyMarketTechnicalUniversePriceBookmarkV1
    assert loaded.to_dict() == bookmark.to_dict()
    current = reopened.get_watchlist()
    assert current is not None
    saved = next(item for item in current.items if item.source_id == bookmark.bookmark_id)
    assert saved.source == TECHNICAL_UNIVERSE_PRICE_BOOKMARK_SOURCE
    with pytest.raises(DailyMarketResearchBookmarkError) as error:
        reopened.get_research_bookmark_context(bookmark.bookmark_id)
    assert error.value.code == "technical_price_bookmark_typed_reopen_required"
    removed = reopened.remove_research_bookmark(bookmark.bookmark_id)
    assert removed.status == "removed"
    assert removed.restore_token is not None
    assert reopened.restore_research_bookmark(removed.restore_token).status == "restored"
    restored = reopened.get_research_bookmark(bookmark.bookmark_id)
    assert restored is not None
    assert restored.to_dict() == bookmark.to_dict()
