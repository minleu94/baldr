"""封存月營收 V3 僅走精確 Watchlist typed 路由。"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

pytest_plugins = (
    "test_daily_market_technical_official_disposition_revenue_archived_bookmark_v3",
)

from app_module.daily_market_research_bookmark import DailyMarketResearchBookmarkError
from app_module.daily_market_technical_official_disposition_revenue_archived_bookmark_v3 import (
    DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_ARCHIVED_BOOKMARK_SCHEMA_V3,
    DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_ARCHIVED_BOOKMARK_SOURCE_V3,
    DailyMarketTechnicalOfficialDispositionRevenueArchivedBookmarkV3,
)
from app_module.watchlist_service import WatchlistService, decode_daily_market_research_bookmark
from tests.test_daily_market_technical_official_disposition_revenue_archived_bookmark_v3 import (
    _bookmark_v3,
)
from ui_qt.views.watchlist_view import WatchlistView


def _config(output_root: Path) -> SimpleNamespace:
    return SimpleNamespace(
        output_root=output_root,
        resolve_output_path=lambda name: output_root / name,
    )


def _row(bookmark: DailyMarketTechnicalOfficialDispositionRevenueArchivedBookmarkV3) -> dict[str, object]:
    # WatchlistView._load_watchlist 會把 service 的 stock_code 欄位改名為證券代號；投影列沒有雙別名。
    return {
        "證券代號": bookmark.stock_code,
        "stock_name": bookmark.stock_code,
        "source": bookmark.source,
        "source_id": bookmark.bookmark_id,
        "research_bookmark": bookmark.to_dict(),
    }


def test_archived_bookmark_v3_roundtrips_watchlist_and_keeps_typed_reopen_only(
    archive_bookmark_environment,
    tmp_path: Path,
) -> None:
    bookmark = _bookmark_v3(archive_bookmark_environment, "1000")
    assert type(bookmark) is DailyMarketTechnicalOfficialDispositionRevenueArchivedBookmarkV3
    assert bookmark.schema_version == DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_ARCHIVED_BOOKMARK_SCHEMA_V3
    assert bookmark.source == DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_ARCHIVED_BOOKMARK_SOURCE_V3
    assert bookmark.to_dict()["bookmark_is_reader_qualification"] is False
    assert bookmark.historical_pit_eligible is False

    service = WatchlistService(_config(tmp_path / "watchlist-output"))
    added = service.add_research_bookmark(bookmark)
    assert added.status == "added"
    assert added.bookmark_id == bookmark.bookmark_id
    assert "封存月營收" in added.message
    assert service.add_research_bookmark(bookmark).status == "already_present"

    listed = service.get_watchlist()
    assert listed is not None
    item = next(item for item in listed.items if item.source_id == bookmark.bookmark_id)
    assert item.source == DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_ARCHIVED_BOOKMARK_SOURCE_V3
    assert item.stock_code == bookmark.stock_code
    assert item.stock_name == bookmark.stock_code
    assert item.research_bookmark == bookmark.to_dict()

    output_config = _config(tmp_path / "watchlist-output")
    json_path = service.default_watchlist_file
    original_json = json_path.read_bytes()
    activated = service.upgrade_to_repository()
    assert activated.is_repository, activated.message
    assert json_path.read_bytes() == original_json

    reopened_service = WatchlistService(output_config)
    reopened = reopened_service.get_research_bookmark(bookmark.bookmark_id)
    assert type(reopened) is DailyMarketTechnicalOfficialDispositionRevenueArchivedBookmarkV3
    assert reopened is not None and reopened.to_dict() == bookmark.to_dict()
    with pytest.raises(DailyMarketResearchBookmarkError) as generic_context:
        reopened_service.get_research_bookmark_context(bookmark.bookmark_id)
    assert generic_context.value.code == "technical_official_revenue_bookmark_typed_reopen_required"

    row = _row(bookmark)
    assert WatchlistView._row_is_technical_official_revenue_bookmark(row)
    assert WatchlistView._exact_research_bookmark_id_for_row(row) == bookmark.bookmark_id
    assert WatchlistView._decode_revenue_bookmark_row(row) == bookmark
    label = WatchlistView._research_bookmark_row_label(row)
    assert label.startswith("已保存封存月營收收藏")
    assert "整體 unknown" in label and "歷史 PIT 否" in label

    emitted: list[object] = []
    frame = SimpleNamespace(iloc=[row])
    view = SimpleNamespace(
        stocks_table=SimpleNamespace(
            selectionModel=lambda: SimpleNamespace(selectedRows=lambda: [SimpleNamespace(row=lambda: 0)])
        ),
        stocks_model=SimpleNamespace(getDataFrame=lambda: frame),
        _row_is_composite_bookmark=lambda _row: False,
        _row_is_technical_official_revenue_bookmark=WatchlistView._row_is_technical_official_revenue_bookmark,
        _decode_revenue_bookmark_row=WatchlistView._decode_revenue_bookmark_row,
        technicalOfficialRevenueBookmarkReady=SimpleNamespace(emit=emitted.append),
        _set_status_label=lambda *_args, **_kwargs: None,
    )
    WatchlistView._open_stock_analysis(view)
    assert emitted == [bookmark]


@pytest.mark.parametrize("outer_field", ("證券代號", "source", "source_id"))
def test_archived_bookmark_v3_rejects_mismatched_watchlist_identity(
    archive_bookmark_environment,
    outer_field: str,
) -> None:
    bookmark = _bookmark_v3(archive_bookmark_environment, "1000")
    row = _row(bookmark)
    row[outer_field] = "wrong"

    assert WatchlistView._row_is_technical_official_revenue_bookmark(row)
    assert WatchlistView._exact_research_bookmark_id_for_row(row) == ""
    assert "不可核驗" in WatchlistView._research_bookmark_row_label(row)


def test_unknown_archived_bookmark_version_cannot_fall_through_to_legacy(
    archive_bookmark_environment,
    tmp_path: Path,
) -> None:
    bookmark = _bookmark_v3(archive_bookmark_environment, "1000")
    payload = bookmark.to_dict()
    payload["schema_version"] = "daily-market-technical-official-disposition-revenue-archived-bookmark.v999"

    with pytest.raises(DailyMarketResearchBookmarkError):
        decode_daily_market_research_bookmark(payload)

    row = _row(bookmark)
    row["research_bookmark"] = payload
    assert WatchlistView._row_is_technical_official_revenue_bookmark(row)
    assert WatchlistView._exact_research_bookmark_id_for_row(row) == ""
    assert "封存月營收研究收藏版本不支援" in WatchlistView._research_bookmark_label(payload)

    service = WatchlistService(_config(tmp_path / "watchlist-output"))
    with pytest.raises(DailyMarketResearchBookmarkError):
        service.add_research_bookmark(payload)
    unchanged = service.get_watchlist()
    assert unchanged is not None and unchanged.items == []
