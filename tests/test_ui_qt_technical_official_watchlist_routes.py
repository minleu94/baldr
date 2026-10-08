"""官方對照收藏損毀仍保持具名來源，不回退一般個股研究。"""
import pytest

from app_module.daily_market_technical_official_disposition_bookmark_v1 import DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_RESEARCH_BOOKMARK_SOURCE as SOURCE
from ui_qt.views.watchlist_view import WatchlistView


@pytest.mark.parametrize("payload", [None, {}, {"schema_version": "daily-market-technical-official-disposition-bookmark.v1"}])
def test_corrupt_declared_bookmark_preserves_source_and_has_no_mutation_id(payload: object) -> None:
    row = {"source": SOURCE, "source_id": "invalid", "證券代號": "2382", "research_bookmark": payload}
    assert WatchlistView._row_is_technical_official_bookmark(row)
    assert WatchlistView._row_declares_research_bookmark(row)
    assert WatchlistView._exact_research_bookmark_id_for_row(row) == ""


def test_unknown_declared_official_payload_has_readable_failure() -> None:
    assert "無效" in WatchlistView._research_bookmark_label({"schema_version": "daily-market-technical-official-disposition-bookmark.v1"})
