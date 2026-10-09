"""MA 收藏損毀／未知版本不轉成一般股票，拒絕保存時不寫入觀察清單。"""

from pathlib import Path
from types import SimpleNamespace

import pytest

from app_module.daily_market_research_bookmark import DailyMarketResearchBookmarkError
from app_module.daily_market_technical_official_disposition_ma_bookmark_v1 import (
    DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_RESEARCH_BOOKMARK_SOURCE,
    DailyMarketTechnicalOfficialDispositionMaBookmarkV1,
    read_daily_market_technical_official_disposition_ma_bookmark_v1,
)
from app_module.daily_market_technical_official_disposition_ma_comparison_v1 import (
    DailyMarketTechnicalOfficialDispositionMaSelectionV1,
)
from app_module.watchlist_service import WatchlistItem, WatchlistService
from test_daily_market_technical_official_disposition_ma_comparison_v1 import (  # type: ignore[import-not-found]
    _MaContext,
    ma_context,
)

pytest_plugins = ("test_daily_market_technical_official_disposition_bundle_v1",)


@pytest.mark.parametrize("version", ["v1", "v9"])
def test_corrupt_ma_payload_retains_namespace_and_raw_evidence(version: str) -> None:
    payload = {
        "schema_version": f"daily-market-technical-official-disposition-ma-bookmark.{version}",
        "bookmark_identity_sha256": "a" * 64,
        "unrecognised_evidence": "保留損毀來源供排錯",
    }
    item = WatchlistItem.from_mapping({
        "stock_code": "2382", "source": "manual", "research_bookmark": payload,
    })
    assert item.source == DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_RESEARCH_BOOKMARK_SOURCE
    assert item.research_bookmark == payload


def test_corrupt_ma_bookmark_rejected_before_primary_write(tmp_path: Path) -> None:
    output = tmp_path / "private_output"
    service = WatchlistService(SimpleNamespace(
        output_root=output, resolve_output_path=lambda name: output / name,
    ))
    before = {path.relative_to(output): path.read_bytes() for path in output.rglob("*") if path.is_file()}
    with pytest.raises(DailyMarketResearchBookmarkError):
        service.add_research_bookmark({
            "schema_version": "daily-market-technical-official-disposition-ma-bookmark.v1",
            "bookmark_identity_sha256": "a" * 64,
        })
    after = {path.relative_to(output): path.read_bytes() for path in output.rglob("*") if path.is_file()}
    assert after == before


def test_real_ma_bookmark_storage_reopen_remove_and_restore(
    ma_context: _MaContext, tmp_path: Path,
) -> None:
    comparisons = (
        DailyMarketTechnicalOfficialDispositionMaSelectionV1.from_page(ma_context.page_zero, "1000"),
        DailyMarketTechnicalOfficialDispositionMaSelectionV1.from_page(ma_context.page_one, "1004"),
    )
    bookmark = DailyMarketTechnicalOfficialDispositionMaBookmarkV1.create(
        query=ma_context.query, page=ma_context.page_one, stock_code="1004",
        scroll_position=321, comparison_selections=comparisons,
    )
    output = tmp_path / "private_output"
    config = SimpleNamespace(output_root=output, resolve_output_path=lambda name: output / name)
    service = WatchlistService(config)
    assert service.add_research_bookmark(bookmark).status == "added"
    primary = output / "watchlist" / "default.json"
    saved_bytes = primary.read_bytes()
    assert service.add_research_bookmark(bookmark).status == "already_present"
    assert primary.read_bytes() == saved_bytes
    reopened = WatchlistService(config)
    loaded = reopened.get_research_bookmark(bookmark.bookmark_id)
    assert type(loaded) is DailyMarketTechnicalOfficialDispositionMaBookmarkV1
    assert loaded.to_dict() == bookmark.to_dict()
    with pytest.raises(DailyMarketResearchBookmarkError) as error:
        reopened.get_research_bookmark_context(bookmark.bookmark_id)
    assert error.value.code == "technical_official_ma_bookmark_typed_reopen_required"
    removed = reopened.remove_research_bookmark(bookmark.bookmark_id)
    assert removed.status == "removed"
    assert reopened.get_research_bookmark(bookmark.bookmark_id) is None
    assert removed.restore_token is not None
    assert reopened.restore_research_bookmark(removed.restore_token).status == "restored"
    restored = WatchlistService(config).get_research_bookmark(bookmark.bookmark_id)
    assert isinstance(restored, DailyMarketTechnicalOfficialDispositionMaBookmarkV1)
    assert restored.to_dict() == bookmark.to_dict()
    verified = read_daily_market_technical_official_disposition_ma_bookmark_v1(restored.to_json())
    assert verified.selected.row.stock_code == "1004"
    assert tuple(item.selection.page_index for item in verified.comparison_selections) == (0, 1)
    assert verified.bookmark.scroll_position == 321
    assert verified.selected.row.ma_entry is not None
    assert verified.selected.row.ma_entry.ma_state == "unknown"
    assert verified.historical_pit_eligible is False
