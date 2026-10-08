"""官方對照原收藏沿既有觀察清單保存與重開，不能轉一般研究。"""
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app_module.daily_market_research_bookmark import DailyMarketResearchBookmarkError
from app_module.daily_market_technical_official_disposition_bookmark_v1 import DailyMarketTechnicalOfficialDispositionBookmarkV1
from app_module.daily_market_technical_official_disposition_query_reader_v1 import DailyMarketTechnicalOfficialDispositionPageRequestV1, open_daily_market_technical_official_disposition_bundle_session_v1
from app_module.watchlist_service import WatchlistService
from test_daily_market_technical_official_disposition_bundle_v1 import bundle_fixture  # type: ignore[import-not-found]


def test_real_bookmark_persists_and_reopens_without_generic_context(bundle_fixture: Any, tmp_path: Path) -> None:
    fixture = bundle_fixture
    session = open_daily_market_technical_official_disposition_bundle_session_v1(
        bundle_output_root=fixture.bundle_root,
        bundle_identity_sha256=fixture.reference.bundle_identity_sha256,
        expected_manifest_sha256=fixture.reference.manifest_sha256,
        row_scope_filter=("included_processed", "included_pending", "excluded"),
    )
    result = session.execute()
    page = result.read_page(0, 50)
    request = DailyMarketTechnicalOfficialDispositionPageRequestV1.create(query=result.query, page_index=0, page_size=50)
    bookmark = DailyMarketTechnicalOfficialDispositionBookmarkV1.create(origin_page_request=request, selected_row=page.rows[0])
    output = tmp_path / "private_output"
    config = SimpleNamespace(output_root=output, resolve_output_path=lambda name: output / name)
    service = WatchlistService(config)
    assert service.add_research_bookmark(bookmark).status == "added"
    assert service.add_research_bookmark(bookmark).status == "already_present"
    reopened = WatchlistService(config)
    loaded = reopened.get_research_bookmark(bookmark.bookmark_id)
    assert type(loaded) is DailyMarketTechnicalOfficialDispositionBookmarkV1
    assert loaded.to_dict() == bookmark.to_dict()
    with pytest.raises(DailyMarketResearchBookmarkError) as error:
        reopened.get_research_bookmark_context(bookmark.bookmark_id)
    assert error.value.code == "technical_official_bookmark_typed_reopen_required"
    removed = reopened.remove_research_bookmark(bookmark.bookmark_id)
    assert removed.status == "removed"
    assert reopened.get_research_bookmark(bookmark.bookmark_id) is None
    assert removed.restore_token is not None
    assert reopened.restore_research_bookmark(removed.restore_token).status == "restored"
    restored = reopened.get_research_bookmark(bookmark.bookmark_id)
    assert restored is not None
    assert restored.to_dict() == bookmark.to_dict()
