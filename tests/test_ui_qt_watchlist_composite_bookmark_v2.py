"""有效內層收藏不能遮蔽錯誤的外層Watchlist身份。"""
from __future__ import annotations

import pytest
from types import SimpleNamespace

from app_module.daily_market_technical_official_disposition_composite_bookmark_storage_v2 import (
    DailyMarketTechnicalOfficialDispositionCompositeViewBookmarkEnvelopeV2,
)
from ui_qt.views.watchlist_view import WatchlistView
from ui_qt.main import MainWindow

pytest_plugins = ("test_daily_market_technical_official_disposition_composite_bookmark_v2",)


@pytest.mark.parametrize("wrong_field", (None, "stock_code", "source", "source_id"))
def test_v2_label_requires_inner_and_outer_watchlist_identity(saved_v2_bookmark, wrong_field):
    envelope = DailyMarketTechnicalOfficialDispositionCompositeViewBookmarkEnvelopeV2.create(saved_v2_bookmark)
    row = {
        "stock_code": envelope.stock_code,
        "source": envelope.source,
        "source_id": envelope.view_bookmark_identity_sha256,
        "research_bookmark": envelope.to_dict(),
    }
    if wrong_field is not None:
        row[wrong_field] = "wrong"
        assert WatchlistView._exact_research_bookmark_id_for_row(row) == ""
        label = WatchlistView._research_bookmark_row_label(row)
        assert "不可核驗" in label and not label.startswith("已收藏")
    else:
        assert WatchlistView._exact_research_bookmark_id_for_row(row) == envelope.view_bookmark_identity_sha256
        assert WatchlistView._research_bookmark_row_label(row).startswith("已收藏官方條件與價格研究")


def test_v2_main_restore_refusal_preserves_current_workspace(saved_v2_bookmark):
    envelope = DailyMarketTechnicalOfficialDispositionCompositeViewBookmarkEnvelopeV2.create(saved_v2_bookmark)
    attempted = []
    navigated = []
    view = SimpleNamespace(restore_bookmark=lambda value: attempted.append(value) or False)
    caller = SimpleNamespace(
        technical_official_composite_price_research_view=view,
        workspace_widgets={"recommendation": SimpleNamespace(result_source_tabs=SimpleNamespace(
            setCurrentWidget=lambda value: navigated.append(value),
        ))},
        _select_main_workspace=lambda value: navigated.append(value),
    )
    MainWindow._open_composite_research_bookmark(caller, envelope)
    assert attempted == [envelope]
    assert navigated == []
