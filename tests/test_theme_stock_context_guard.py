"""題材報告不得替任意搜尋代碼沿用舊成員來源。"""
from types import SimpleNamespace

import pytest

from app_module.research_session import ResearchStockContextDTO
from ui_qt.views.stock_research_report_view import StockResearchReportView


@pytest.mark.parametrize("requested", ["2317", "9999"])
def test_theme_stock_switch_requires_returning_to_verified_member_source(requested):
    original = ResearchStockContextDTO(
        stock_code="2330", stock_name="台積電", data_date="2026-10-16",
        source_kind="industry_theme_snapshot", source_workspace="market_explore",
        source_snapshot_id="a" * 64, source_snapshot_hash="a" * 64,
    )
    statuses = []
    edits = []
    host = SimpleNamespace(
        _saved_snapshot_only=False,
        context=original, _set_status=lambda *args: statuses.append(args),
        stock_search=SimpleNamespace(setText=edits.append),
    )
    StockResearchReportView._load_stock(host, requested)
    assert host.context is original
    assert edits == ["2330"]
    assert statuses == [("目前報告綁定原題材成員；請返回產業與題材選取其他成員，或另開一般個股研究。", "warning")]
