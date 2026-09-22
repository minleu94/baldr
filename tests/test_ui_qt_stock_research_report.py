"""個股研究報告畫面的真 service、競態、鍵盤與窄版驗收。"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import json
import os
import sqlite3
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel, QTableView
from PySide6.QtTest import QTest

from app_module.research_session import ResearchStockContextDTO
from app_module.stock_research_report_dtos import (
    StockEvidenceEventDTO,
    StockMetricDTO,
    StockOutcomeDTO,
    StockPricePointDTO,
    StockResearchReportDTO,
)
from app_module.stock_research_report_service import StockResearchReportReadService
from app_module.research_result_presentation import (
    build_shareholding_tier_table,
    build_stock_research_event_table,
)
from ui_qt.views.stock_research_report_view import (
    StockPriceChartWidget,
    StockResearchReportDialog,
    StockResearchReportView,
    _price_change_text,
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
    chart_range = view.findChild(QLabel, "stockResearchPriceChartRange")
    assert chart_range is not None
    assert "圖表範圍：2026-09-08 至 2026-09-08" in chart_range.text()
    assert "最新涵蓋日：2026-09-08" in chart_range.text()
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


def test_missing_change_direction_is_not_presented_as_a_rise() -> None:
    point = StockPricePointDTO(
        data_date="2026-09-21",
        close_price=Decimal("170"),
        change=None,
    )

    assert _price_change_text((point,)) == "漲跌資料或方向不足，無法確認。"


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


def test_shareholding_tier_table_translates_json_to_semantic_rows() -> None:
    raw = json.dumps(
        [
            {"tier": 1, "holder_count": 12, "shares": 999, "holding_ratio_bp": 10},
            {"tier": 15, "holder_count": 1, "shares": 2000001, "holding_ratio_bp": 6200},
            {"tier": 16, "holder_count": 0, "shares": -1, "holding_ratio_bp": -1},
            {"tier": 17, "holder_count": 20, "shares": 10000, "holding_ratio_bp": 10000},
        ],
        ensure_ascii=False,
    )

    presentation = build_shareholding_tier_table(raw)

    assert presentation.rows == (
        ("1–999 股", "12", "999", "0.10%"),
        ("1,000,001 股以上", "1", "2,000,001", "62.00%"),
        ("差異數調整", "0", "-1", "-0.01%"),
        ("合計", "20", "10,000", "100.00%"),
    )
    assert "原始級距欄位" in presentation.tooltips[0][0]
    assert '"tier": 1' in presentation.tooltips[0][0]


def test_shareholding_tier_table_keeps_real_zero_and_missing_distinct() -> None:
    presentation = build_shareholding_tier_table(
        json.dumps(
            [
                {"tier": 2, "holder_count": 0, "shares": 0},
                {"tier": 3, "holder_count": None, "shares": None, "holding_ratio_bp": None},
            ]
        )
    )

    assert presentation.rows[0] == ("1,000–5,000 股", "0", "0", "—")
    assert presentation.rows[1] == ("5,001–10,000 股", "—", "—", "—")


def test_event_table_humanizes_portfolio_tokens_and_keeps_raw_tooltip() -> None:
    event = StockEvidenceEventDTO(
        event_id="event-1",
        event_date="2026-09-21",
        decision_date="2026-09-21",
        event_type="portfolio_alert_condition_warning",
        event_family="portfolio",
        source_type="daily_decision_desk.portfolio_alert",
        source_id="portfolio-alert:2026-09-21",
        source_version="portfolio_alert_importer_v1",
        data_quality="degraded",
        reasons=("condition:warning", "chip:risk_level:bearish"),
        risk_reasons=("portfolio_alert_condition_warning",),
        outcomes=(StockOutcomeDTO(window_days=5, outcome_status="pending"),),
    )

    presentation = build_stock_research_event_table((event,))
    row = presentation.rows[0]

    assert row[1:3] == ("持倉條件提醒", "品質降級")
    assert "持倉條件出現提醒" in row[3]
    assert "籌碼風險偏弱" in row[3]
    assert "portfolio_alert_condition_warning" not in row
    assert "分類：持倉警示" in presentation.details[0]
    assert "來源：每日決策台" in presentation.details[0]
    assert "反對理由：未提供" in presentation.details[0]
    assert "風險：持倉條件出現提醒" in presentation.details[0]
    assert "警告：未提供" in presentation.details[0]
    assert "尚待觀測" in presentation.details[0]
    assert "原始 event_type：portfolio_alert_condition_warning" in presentation.tooltips[0][1]
    assert "condition:warning" in presentation.tooltips[0][3]


def test_flows_tab_separates_ownership_groups_and_event_table() -> None:
    view = StockResearchReportView(SimpleNamespace())
    report = StockResearchReportDTO(
        stock_code="2330",
        shareholding=(
            StockMetricDTO(
                key="large_holder_ratio_bp",
                label="大戶持股比例",
                value=Decimal("6200"),
                unit="bp",
                data_as_of="2026-09-04",
                quality="degraded",
            ),
            StockMetricDTO(
                key="shareholding_tiers",
                label="持股級距",
                value_text=json.dumps(
                    [{"tier": 1, "holder_count": 2, "shares": 999, "holding_ratio_bp": 10}]
                ),
                data_as_of="2026-09-04",
                quality="degraded",
            ),
        ),
        events=(
            StockEvidenceEventDTO(
                event_id="event-1",
                event_date="2026-09-21",
                decision_date="2026-09-21",
                event_type="portfolio_alert_condition_warning",
                event_family="portfolio",
                source_type="daily_decision_desk_portfolio_alert",
                data_quality="degraded",
                reasons=("condition:warning",),
            ),
        ),
    )

    view._render_flows(report)
    tables = {table.objectName(): table for table in view.findChildren(QTableView)}

    tier_table = tables["stockResearchShareholdingTiers"]
    assert tier_table.model().data(tier_table.model().index(0, 0), Qt.DisplayRole) == "1–999 股"
    assert tables["stockResearchEvidenceEvents"].model().data(
        tables["stockResearchEvidenceEvents"].model().index(0, 1), Qt.DisplayRole
    ) == "持倉條件提醒"
    view.close()


def test_shareholding_tier_table_shows_all_tdcc_rows_without_inner_scroll() -> None:
    view = StockResearchReportView(SimpleNamespace())
    tier_rows = [
        {
            "tier": tier,
            "holder_count": tier,
            "shares": tier * 1000,
            "holding_ratio_bp": tier * 10,
        }
        for tier in range(1, 18)
    ]
    report = StockResearchReportDTO(
        stock_code="2330",
        shareholding=(
            StockMetricDTO(
                key="shareholding_tiers",
                label="持股級距",
                value_text=json.dumps(tier_rows),
            ),
        ),
    )

    view._render_flows(report)
    view.resize(760, 640)
    view.show()
    view.tabs.setCurrentIndex(3)
    _app().processEvents()

    table = view.findChild(QTableView, "stockResearchShareholdingTiers")
    assert table is not None
    assert table.model() is not None
    assert table.model().rowCount() == 17
    assert table.verticalScrollBar().maximum() == 0
    assert table.height() >= 500
    view.close()


def test_event_table_humanizes_risk_prompt_and_portfolio_alert_variants() -> None:
    event = StockEvidenceEventDTO(
        event_id="event-variant",
        event_date="2026-09-21",
        decision_date="2026-09-21",
        event_type="portfolio_alert:condition_invalid",
        event_family="risk_prompt",
        source_type="daily_decision_desk.risk_prompt",
        data_quality="degraded",
        reasons=("chip:estimated", "condition:invalid"),
    )

    presentation = build_stock_research_event_table((event,))

    assert presentation.rows[0][1] == "持倉條件已失效"
    assert presentation.rows[0][2] == "品質降級"
    assert "籌碼資料為估算" in presentation.rows[0][3]
    assert "持倉條件已失效" in presentation.rows[0][3]
    assert "portfolio_alert:condition_invalid" not in presentation.rows[0]
    assert "每日決策台風險提示" in presentation.details[0]
