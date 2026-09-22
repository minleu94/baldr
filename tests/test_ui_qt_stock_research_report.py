"""個股研究報告畫面的真 service、競態、鍵盤與窄版驗收。"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import os
import sqlite3
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest

from app_module.research_session import ResearchStockContextDTO
from app_module.stock_research_report_dtos import (
    StockPricePointDTO,
    StockResearchReportDTO,
)
from app_module.stock_research_report_service import StockResearchReportReadService
from ui_qt.views.stock_research_report_view import (
    StockPriceChartWidget,
    StockResearchReportDialog,
    StockResearchReportView,
)


def _app() -> QApplication:
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication(sys.argv)
    return instance


def _real_service(tmp_path: Path) -> StockResearchReportReadService:
    database = tmp_path / "twstock.db"
    with sqlite3.connect(database) as conn:
        conn.execute(
            "CREATE TABLE daily_prices (日期 TEXT, 證券代號 TEXT, 證券名稱 TEXT, 開盤價 TEXT, 最高價 TEXT, 最低價 TEXT, 收盤價 TEXT, 成交股數 INTEGER, 成交金額 TEXT, 漲跌價差 TEXT)"
        )
        conn.execute(
            "INSERT INTO daily_prices VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("2026-09-08", "2330", "台積電", "99", "102", "98", "100", 1000, "100000", "1"),
        )
    return StockResearchReportReadService(
        SimpleNamespace(db_file=database, output_root=tmp_path / "output"),
        clock=lambda: datetime(2026, 9, 8, 15, 0, 0),
    )


def _wait_for(view: StockResearchReportView, predicate, timeout_ms: int = 2500) -> None:
    app = _app()
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        QTest.qWait(10)
    assert predicate()


def test_report_view_reads_real_service_and_renders_missing_ml(tmp_path: Path) -> None:
    app = _app()
    view = StockResearchReportView(
        _real_service(tmp_path),
        ResearchStockContextDTO(stock_code="2330", stock_name="台積電", source_workspace="watchlist"),
    )
    loaded: list[StockResearchReportDTO] = []
    view.reportLoaded.connect(loaded.append)
    view.resize(860, 620)
    view.show()
    _wait_for(view, lambda: "100" in view._summary_values["latest_price"].text() and bool(loaded))

    assert "2330 台積電" in view.identity_label.text()
    report = loaded[-1]
    assert report.advice.status == "unavailable"
    assert report.advice.recommendation is None
    assert report.advice.limitations == (
        "尚未選定原始推薦來源；不會以同股或最新結果猜測。請回到推薦分析保存結果，或明確選擇原始推薦來源。",
    )
    assert view._summary_values["advice"].text() == report.advice.limitations[0]
    assert "ML" in view.tabs.tabText(5)
    assert view.sources_table.model() is not None
    headers = [
        view.sources_table.model().headerData(index, Qt.Horizontal)
        for index in range(view.sources_table.model().columnCount())
    ]
    assert "更新週期" in headers
    assert "預期資料期" in headers
    assert "資料可得時間" in headers
    assert view.stock_search.accessibleName() == "搜尋個股代碼"
    assert view.return_button.accessibleName() == "返回原持倉或觀察清單"
    assert view._summary_values["risk"].wordWrap() is True
    view.tabs.setCurrentIndex(1)
    app.processEvents()
    chart = view.findChild(StockPriceChartWidget)
    assert chart is not None
    assert chart.accessibleName() == "個股收盤價走勢圖"
    assert "2026-09-08" in chart.toolTip()
    assert chart.grab().isNull() is False
    view.tabs.setCurrentIndex(0)
    screenshot_path = os.environ.get("STOCK_RESEARCH_SCREENSHOT_PATH", "").strip()
    if screenshot_path:
        assert view.grab().save(screenshot_path)
    view.resize(375, 280)
    app.processEvents()
    assert view.minimumSizeHint().width() <= 375
    assert view.grab().isNull() is False
    narrow_screenshot_path = os.environ.get("STOCK_RESEARCH_NARROW_SCREENSHOT_PATH", "").strip()
    if narrow_screenshot_path:
        assert view.grab().save(narrow_screenshot_path)
    view.close()


def test_search_return_uses_keyboard_and_keeps_accessible_status(tmp_path: Path) -> None:
    view = StockResearchReportView(_real_service(tmp_path))
    view.show()
    view.stock_search.setText("2330")
    QTest.keyClick(view.stock_search, Qt.Key_Return)
    _wait_for(view, lambda: "100" in view._summary_values["latest_price"].text())
    assert view.status_badge.accessibleDescription().startswith("報告狀態：")
    assert view.load_button.isEnabled()
    view.close()


def _report_for(code: str, price: str) -> StockResearchReportDTO:
    return StockResearchReportDTO(
        stock_code=code,
        stock_name=code,
        as_of="2026-09-08",
        generated_at=datetime.now().isoformat(timespec="seconds"),
        price_points=(
            StockPricePointDTO(
                data_date="2026-09-08",
                close_price=Decimal(price),
                source_id="fixture.price",
            ),
        ),
    )


def test_old_worker_result_cannot_replace_new_stock() -> None:
    class RaceService:
        def read_report(self, stock_code, *, context=None, cancel_callback=None):
            del context, cancel_callback
            if stock_code == "A":
                time.sleep(0.12)
                return _report_for("A", "1")
            time.sleep(0.01)
            return _report_for("B", "2")

    view = StockResearchReportView(RaceService())
    view.show()
    view.stock_search.setText("A")
    view._load_from_search()
    QTest.qWait(15)
    view.stock_search.setText("B")
    view._load_from_search()
    _wait_for(view, lambda: "2" in view._summary_values["latest_price"].text())
    assert view.identity_label.text().startswith("B")
    assert "2" in view._summary_values["latest_price"].text()
    _wait_for(view, lambda: not view.is_busy())
    view.close()


def test_late_started_signal_cannot_replace_new_stock_status(tmp_path: Path) -> None:
    view = StockResearchReportView(_real_service(tmp_path))
    view._request_id = 2
    view._active_code = "B"
    view._set_status("B 已完成", "observed")

    view._on_report_started(1, "A")

    assert view.status_label.text() == "B 已完成"
    view.close()


def test_cross_stock_loading_clears_old_report_before_advanced_tab_is_opened() -> None:
    view = StockResearchReportView(SimpleNamespace())
    view.show()
    view._active_code = "A"
    view._request_id = 1
    view._render_report(_report_for("A", "1"))
    view.tabs.setCurrentIndex(1)
    _app().processEvents()

    view._active_code = "B"
    view._request_id = 2
    view._set_loading_state("B")
    assert view._loaded_report is None
    assert "A" not in view.identity_label.text()
    assert view._page_layouts["price"].count() == 2

    view.tabs.setCurrentIndex(1)
    _app().processEvents()
    view._on_report_error(2, "B", "B report unavailable")
    assert view._loaded_report is None
    assert "B" in view.identity_label.text()
    assert "B report unavailable" in view.summary_focus.reasons_label.text()
    assert "1" not in view._summary_values["latest_price"].text()
    view.close()


def test_same_stock_reload_marks_last_good_data_and_keeps_it_on_failure() -> None:
    view = StockResearchReportView(SimpleNamespace())
    view.show()
    report = _report_for("A", "1")
    view._active_code = "A"
    view._request_id = 1
    view._render_report(report)

    view._request_id = 2
    view._set_loading_state("A")
    assert view._loaded_report is report
    assert "上次可用資料 2026-09-08" in view.identity_label.text()
    assert "1" in view._summary_values["latest_price"].text()

    view._on_report_error(2, "A", "temporary source failure")
    assert view._loaded_report is report
    assert "上次可用資料" in view.summary_focus.reasons_label.text()
    assert "temporary source failure" in view.summary_focus.reasons_label.text()
    assert "1" in view._summary_values["latest_price"].text()
    view.close()


def test_report_dialog_title_tracks_internal_stock_switch() -> None:
    class Service:
        def read_report(self, stock_code, *, context=None, cancel_callback=None):
            del context, cancel_callback
            return _report_for(str(stock_code), "1")

    dialog = StockResearchReportDialog(
        Service(),
        ResearchStockContextDTO(stock_code="A", stock_name="A"),
    )
    dialog.report_view.activeStockChanged.emit("B")
    assert dialog.windowTitle() == "個股研究報告｜B"
    dialog.report_view.request_close()
    dialog.close()


def test_context_path_keeps_daily_summary_compact_and_full_trace_in_advanced_source() -> None:
    context = ResearchStockContextDTO(
        stock_code="2330",
        stock_name="台積電",
        decision_date="2026-09-14",
        data_date="2026-09-13",
        result_id="result-2330",
        source_snapshot_id="snapshot-2330",
        source_snapshot_hash="hash-2330",
        source_id="recommendation-run",
        source_version="recommendation-v5",
        mapping_source_id="twse-symbol-map",
        mapping_version="mapping-2026-09",
        mapping_observed_date="2026-09-15",
        profile_id="balanced",
        profile_version="balanced-v2",
        source_kind="recommendation",
        source_label="每日推薦",
        source_workspace="recommendation",
    )
    view = StockResearchReportView(SimpleNamespace(), context)
    view.show()
    _app().processEvents()

    daily_text = view.context_path_label.text()
    assert "來源：每日推薦" in daily_text
    assert "決策日：2026-09-14" in daily_text
    assert "資料日：2026-09-13" in daily_text
    assert "source_snapshot_id" not in daily_text
    assert "mapping_version" not in daily_text

    full_trace = view.context_path_label.toolTip()
    assert "市場總覽 →" in full_trace
    assert "source_snapshot_id：snapshot-2330" in full_trace
    assert "source_snapshot_hash：hash-2330" in full_trace
    assert "source_version：recommendation-v5" in full_trace
    assert "mapping_version：mapping-2026-09" in full_trace
    assert "stockResearchSourceTrace" in view.summary_source_trace_label.objectName()
    assert "mapping_version：mapping-2026-09" in view.summary_source_trace_label.text()
    view.close()
