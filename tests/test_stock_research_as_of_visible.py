from __future__ import annotations

import os
import sys
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication

from app_module.research_session import ResearchStockContextDTO
from app_module.stock_research_report_dtos import StockPricePointDTO, StockResearchReportDTO
from ui_qt.views.stock_research_report_view import StockResearchReportView


def _app() -> QApplication:
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication(sys.argv)
    return instance


def test_default_summary_shows_report_query_as_of_without_filling_entry_decision() -> None:
    app = _app()
    view = StockResearchReportView(SimpleNamespace())
    view.context = ResearchStockContextDTO(
        stock_code="2330",
        stock_name="台積電",
        decision_date="",
        data_date="2026-10-02",
        source_label="手動持倉",
        source_workspace="portfolio",
    )
    view._render_context_path()
    report = StockResearchReportDTO(
        stock_code="2330",
        stock_name="台積電",
        as_of="2026-10-03",
        generated_at=datetime(2026, 10, 3, 8, 30).isoformat(),
        price_points=(
            StockPricePointDTO(
                data_date="2026-10-02",
                close_price=Decimal("2500"),
                source_id="qa.daily_prices",
            ),
        ),
    )

    view._render_report(report)
    view.show()
    app.processEvents()

    assert view.query_as_of_label.isVisible()
    assert view.query_as_of_label.accessibleName() == "本次研究查詢日"
    assert view.query_as_of_label.text() == "本次研究查詢日（as_of）：2026-10-03"
    assert "決策日：未知" in view.context_path_label.text()
    assert "資料日：2026-10-02" in view.context_path_label.text()
    assert view.context.decision_date == ""

    view._clear_loaded_report()
    assert view.query_as_of_label.text() == "本次研究查詢日（as_of）：未知"
    assert view.context.decision_date == ""
    view.close()
