"""個股研究報告畫面的真 service、競態、鍵盤與窄版驗收。"""

from __future__ import annotations

from datetime import datetime
from dataclasses import asdict, replace
from decimal import Decimal
import json
import os
import sqlite3
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QGroupBox, QLabel, QTableView
from PySide6.QtTest import QTest

from app_module.research_session import ResearchStockContextDTO
from app_module.watchlist_analysis_service import WatchlistAnalysisDTO
from app_module.stock_research_report_dtos import (
    StockAdviceSnapshotDTO,
    StockEvidenceEventDTO,
    StockMarketStatusEvidenceDTO,
    StockMarketStatusSnapshotDTO,
    StockMetricDTO,
    StockMLSnapshotDTO,
    StockOutcomeDTO,
    StockPositionSnapshotDTO,
    StockPricePointDTO,
    StockReportSourceDTO,
    StockResearchReportDTO,
    StockTradingRestrictionDTO,
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
    _report_pending_text,
    _ml_estimate_summary,
    _current_h20_observation_allows,
)
from ui_qt.views.stock_research_workspace import StockResearchWorkspace


def _app() -> QApplication:
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication(sys.argv)
    return instance


@pytest.mark.parametrize("state", ["not_mature", "not_mature_as_of_cutoff"])
def test_legal_h5_immaturity_preserves_forecast_and_qualification(state) -> None:
    ml = StockMLSnapshotDTO(status="degraded", h5_status=state,
        target_metric="benchmark_excess_after_standard_80bp_cost",
        predicted_benchmark_excess_return_bp={"H5": -100}, research_only=True,
        formal_qualified=False)
    report = StockResearchReportDTO(stock_code="2382", ml=ml)
    text = _report_pending_text(report)
    assert "未識別" not in text
    assert "結果尚未成熟" in text and "研究估計仍可查看" in text
    assert "H5：-100 bp" in _ml_estimate_summary(ml)
    assert ml.formal_qualified is False and ml.h5_gross_stock_return_bp is None


def _current_h20_case():
    from app_module.recommendation.personal_h20_product_evidence import PersonalH20ProductEvidence

    report = StockResearchReportDTO(stock_code="2382", as_of="2026-10-06",
        price_points=(StockPricePointDTO(data_date="2026-10-06", close_price=Decimal("330")),))
    context = ResearchStockContextDTO(stock_code="2382", ml_scope_mode="current_stock_research")
    evidence = PersonalH20ProductEvidence("2382", "available", "自然結果待核驗", 684,
        "2026-10-07", "2026-10-06", "2026-10-05", "2026-10-06T16:42:07+00:00",
        "model", "sample", "prediction")
    now = datetime.fromisoformat("2026-10-06T21:45:00+00:00")
    return report, context, evidence, now


def test_current_h20_uses_observation_clock_instead_of_price_cutoff() -> None:
    _app()
    report, context, evidence, now = _current_h20_case()
    assert _current_h20_observation_allows(evidence, report, context, now=now)
    view = StockResearchReportView(SimpleNamespace())
    try:
        view.context = context
        view._loaded_request_context = context
        view._loaded_report = report
        view.set_personal_h20_evidence(evidence)
        assert "+6.84%（684 bp）" in view.personal_h20_label.text()
        assert "自然結果待核驗" in view.personal_h20_label.text()
        before = view.personal_h20_label.text()
        view.context = replace(context, source_id="changed")
        view.set_personal_h20_evidence(replace(evidence, gross_return_bp=999))
        assert view.personal_h20_label.text() == before
        view.context = context
        unavailable = replace(evidence, status="unavailable", decision_date=None,
            reason="historical SQLite source changed during snapshot load")
        view.set_personal_h20_evidence(unavailable)
        assert "模型資料暫時無法驗證" in view.personal_h20_label.text()
        assert "+6.84%" not in view.personal_h20_label.text()
        assert unavailable.reason == view.personal_h20_label.toolTip()
    finally:
        view.close()


@pytest.mark.parametrize(
    ("source_kind", "evidence_status"),
    [
        ("personal_h20_saved_cohort", "available"),
        ("personal_h20_saved_cohort", "unavailable"),
        ("personal_h20_research_bookmark", "unavailable"),
    ],
)
def test_personal_h20_context_separates_report_ml_from_saved_prediction(
    source_kind: str, evidence_status: str,
) -> None:
    from app_module.recommendation.personal_h20_product_evidence import (
        PersonalH20ProductEvidence,
    )

    _app()
    context = ResearchStockContextDTO(
        stock_code="2382",
        decision_date="2026-10-07",
        data_date="2026-10-06",
        source_snapshot_id="h20-cycle-20261007",
        source_snapshot_hash="sha256:" + "a" * 64,
        source_id="h20-prediction-2382",
        source_kind=source_kind,
        source_workspace="recommendation",
    )
    generic_ml = StockMLSnapshotDTO(
        status="unavailable",
        limitations=("此研究模型只支援當下觀測；歷史日期不具使用資格。",),
    )
    report = replace(_report_for("2382", "330"), ml=generic_ml)
    if evidence_status == "available":
        evidence = PersonalH20ProductEvidence(
            stock_code="2382",
            status="available",
            reason="自然結果待核驗",
            gross_return_bp=684,
            decision_date="2026-10-07",
            source_date="2026-10-06",
            feature_date="2026-10-05",
            observed_at="2026-10-06T16:42:07+00:00",
            candidate_id="fixture-h20-candidate",
            sample_id="fixture-h20-sample",
            prediction_id="h20-prediction-2382",
        )
    else:
        evidence = PersonalH20ProductEvidence(
            stock_code="2382",
            status="unavailable",
            reason="fixture_h20_source_unavailable",
        )

    workspace = StockResearchWorkspace(SimpleNamespace())
    try:
        view = workspace.report_view
        view.context = context
        view._loaded_request_context = context
        view._loaded_report = report
        view._active_code = "2382"
        view._render_decision(report)
        workspace.set_personal_h20_saved_evidence(evidence, context=context)

        group = view.findChild(QGroupBox, "stockResearchMLGroup")
        assert group is not None
        assert group.title() == "另一份個股 ML 報告（與上方 H20 毛報酬分開）"
        separation = group.findChild(QLabel, "stockResearchMLH20Separation")
        assert separation is not None
        assert "只呈現個股報告 ML" in separation.text()
        assert "本區顯示「未提供」只代表" in separation.text()
        assert "H20 的來源狀態與數值請看上方保存 H20 區" in separation.text()
        report_ml_labels = [label.text() for label in group.findChildren(QLabel)]
        assert any(
            "另一份個股 ML 報告（與上方 H20 毛報酬分開）的估計" in text
            and "未提供合格估計值" in text
            for text in report_ml_labels
        )
        assert any(
            "另一份個股 ML 報告（與上方 H20 毛報酬分開）沒有合格輸出" in text
            and "請依上方保存 H20 區的來源狀態判讀" in text
            for text in report_ml_labels
        )

        identity_table = group.findChild(QTableView, "stockResearchMLIdentityTable")
        assert identity_table is not None and identity_table.model() is not None
        identity_rows = {
            identity_table.model().data(identity_table.model().index(row, 0), Qt.DisplayRole):
            identity_table.model().data(identity_table.model().index(row, 1), Qt.DisplayRole)
            for row in range(identity_table.model().rowCount())
        }
        assert identity_rows["範圍"] == "個股報告 ML 範圍未提供"
        assert "歷史日期不具使用資格" in " ".join(
            label.text() for label in group.findChildren(QLabel)
        )
        assert "未提供合格估計值" in _ml_estimate_summary(generic_ml)
        assert "估計所扣成本情境與數值未提供" in _ml_estimate_summary(generic_ml)
        assert "另一份個股 ML 報告" not in _ml_estimate_summary(generic_ml)
        assert report.ml.predicted_benchmark_excess_return_bp == {}

        saved_text = workspace.personal_h20_saved_summary.text()
        if evidence_status == "available":
            assert "（未扣成本）：+6.84%" in saved_text
            assert "目前尚無已核驗結果" in saved_text
        else:
            assert "保存來源讀取失敗" in saved_text
            assert "+6.84%" not in saved_text
    finally:
        workspace.close()


def test_personal_h20_and_report_ml_estimate_remain_separate() -> None:
    from app_module.recommendation.personal_h20_product_evidence import (
        PersonalH20ProductEvidence,
    )

    _app()
    context = ResearchStockContextDTO(
        stock_code="2382",
        decision_date="2026-10-07",
        data_date="2026-10-06",
        source_snapshot_id="h20-cycle-20261007",
        source_snapshot_hash="sha256:" + "c" * 64,
        source_id="h20-prediction-2382",
        source_kind="personal_h20_saved_cohort",
        source_workspace="recommendation",
    )
    report_ml = StockMLSnapshotDTO(
        status="available",
        target_metric="cost_adjusted_benchmark_excess_bp",
        predicted_benchmark_excess_return_bp={"other_report_horizon": 51},
        research_only=True,
    )
    report = replace(_report_for("2382", "330"), ml=report_ml)
    evidence = PersonalH20ProductEvidence(
        stock_code="2382",
        status="available",
        reason="自然結果待核驗",
        gross_return_bp=684,
        decision_date="2026-10-07",
        source_date="2026-10-06",
        feature_date="2026-10-05",
        observed_at="2026-10-06T16:42:07+00:00",
        candidate_id="fixture-h20-candidate",
        sample_id="fixture-h20-sample",
        prediction_id="h20-prediction-2382",
    )
    workspace = StockResearchWorkspace(SimpleNamespace())
    try:
        view = workspace.report_view
        view.context = context
        view._loaded_request_context = context
        view._loaded_report = report
        view._active_code = "2382"
        view._render_decision(report)
        workspace.set_personal_h20_saved_evidence(evidence, context=context)

        group = view.findChild(QGroupBox, "stockResearchMLGroup")
        assert group is not None
        assert group.title() == "另一份個股 ML 報告（與上方 H20 毛報酬分開）"
        labels = "\n".join(label.text() for label in group.findChildren(QLabel))
        assert "另一份個股 ML 報告（與上方 H20 毛報酬分開）的估計" in labels
        assert "other_report_horizon：+51 bp" in labels
        assert "+6.84%" not in labels
        assert "（未扣成本）：+6.84%" in workspace.personal_h20_saved_summary.text()
        assert "目前尚無已核驗結果" in workspace.personal_h20_saved_summary.text()
        assert report.ml.predicted_benchmark_excess_return_bp == {
            "other_report_horizon": 51
        }
    finally:
        workspace.close()


def test_non_h20_report_ml_presentation_remains_unchanged() -> None:
    _app()
    context = ResearchStockContextDTO(
        stock_code="2382",
        source_kind="recommendation",
        source_snapshot_id="saved-report-cycle",
        source_snapshot_hash="sha256:" + "b" * 64,
        ml_scope_mode="selected_saved_decision",
    )
    report = replace(
        _report_for("2382", "330"),
        ml=StockMLSnapshotDTO(
            status="unavailable",
            scope_mode="selected_saved_decision",
            limitations=("一般報告 ML 的既有資格限制。",),
        ),
    )
    view = StockResearchReportView(SimpleNamespace())
    try:
        view.context = context
        view._loaded_report = report
        view._active_code = "2382"
        view._render_decision(report)
        group = view.findChild(QGroupBox, "stockResearchMLGroup")
        assert group is not None
        assert group.title() == "所選保存決策ML研究（模型事件日：未提供）"
        assert group.findChild(QLabel, "stockResearchMLH20Separation") is None
        assert "一般報告 ML 的既有資格限制。" in " ".join(
            label.text() for label in group.findChildren(QLabel)
        )
    finally:
        view.close()


@pytest.mark.parametrize("change", ["future_clock", "wrong_stock", "wrong_source", "saved", "unknown_scope"])
def test_current_h20_clock_exception_rejects_invalid_scope_and_provenance(change) -> None:
    report, context, evidence, now = _current_h20_case()
    if change == "future_clock":
        evidence = replace(evidence, observed_at="2026-10-07T21:45:00+00:00")
    elif change == "wrong_stock":
        evidence = replace(evidence, stock_code="2330")
    elif change == "wrong_source":
        evidence = replace(evidence, source_date="2026-10-05")
    elif change == "saved":
        context = replace(context, ml_scope_mode="selected_saved_decision", decision_date="2026-10-06")
    else:
        context = replace(context, ml_scope_mode="")
    assert not _current_h20_observation_allows(evidence, report, context, now=now)


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
        clock=lambda: datetime(2026, 9, 8, 15, 0, 0, tzinfo=ZoneInfo("Asia/Taipei")),
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
    assert "完整來源範圍：2026-09-08 至 2026-09-08" in chart_range.text()
    assert "最新涵蓋日：2026-09-08" in chart_range.text()
    price_table = view.findChild(QTableView, "stockResearchPriceHistoryTable")
    assert price_table is not None
    assert price_table.model() is not None
    assert price_table.model().rowCount() == 1
    assert price_table.model().columnCount() == 8
    assert price_table.model().index(0, 0).data() == "2026-09-08"
    assert price_table.model().index(0, 4).data() == "100"
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


def test_h20_saved_report_keeps_current_sqlite_prices_out_of_saved_sections(
    tmp_path: Path,
) -> None:
    service = _real_service(tmp_path)
    with sqlite3.connect(Path(getattr(service.config, "db_file"))) as connection:
        connection.execute(
            "INSERT INTO daily_prices VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("2026-09-08", "2382", "廣達", "99", "102", "98", "100", 1000, "100000", "1"),
        )
    context = ResearchStockContextDTO(
        stock_code="2382",
        stock_name="廣達",
        decision_date="2026-09-08",
        data_date="2026-09-08",
        source_snapshot_id="saved-h20-cycle",
        source_snapshot_hash="saved-h20-manifest-pin",
        source_id="saved-h20-prediction",
        source_version="saved-h20-contract",
        source_kind="personal_h20_saved_cohort",
        source_workspace="recommendation",
    )

    report = service.read_report("2382", context=context)

    sections = {section.section_id: section for section in report.sections}
    assert report.price_points == ()
    assert report.technical is None
    assert sections["price"].status == "missing"
    assert sections["technical"].status == "missing"
    assert "H20" in sections["price"].summary
    assert "同版本價格／技術圖表" in sections["price"].summary
    assert "不以另一份行情來源補入" in sections["technical"].summary
    assert not any("價格：" in error or "技術指標：" in error for error in report.limitations)


def test_h20_current_market_action_stays_disabled_when_saved_estimate_is_unknown(
    tmp_path: Path,
) -> None:
    _app()
    context = ResearchStockContextDTO(
        stock_code="2382",
        source_kind="personal_h20_saved_cohort",
        source_workspace="recommendation",
    )
    report = StockResearchReportDTO(
        stock_code="2382",
        research_context={"source_kind": "personal_h20_saved_cohort"},
    )
    view = StockResearchReportView(_real_service(tmp_path))
    try:
        view.context = context
        view._loaded_request_context = context
        view._loaded_report = report
        view._sync_original_rank_actions()
        assert not view.open_latest_rank_research_button.isHidden()
        assert view.open_latest_rank_research_button.text() == "查看目前個股行情與資料（獨立研究）"
        assert not view.open_latest_rank_research_button.isEnabled()
        assert view.request_latest_research() is False
    finally:
        view.close()


def test_market_status_and_position_quote_dates_render_separately(tmp_path: Path) -> None:
    view = StockResearchReportView(_real_service(tmp_path))
    view._render_market_status(
        StockMarketStatusSnapshotDTO(
            status="partial",
            listing_status="listed",
            market="上市",
            name="台積電",
            trading_restrictions=(
                StockTradingRestrictionDTO(
                    restriction_type="注意股票",
                    restriction_state="active",
                    effective_from="2026-10-03",
                    effective_to="2026-10-04",
                    resumed_on="",
                    published_date="2026-10-02",
                    notice_reference="notice-2330",
                    source_id="mops-status-2330",
                    details="來源公告註記",
                ),
            ),
            status_evidence=(
                StockMarketStatusEvidenceDTO(
                    evidence_type="listing_status",
                    source_id="exchange-status-2330",
                    observed_at="2026-10-04T09:00:00+08:00",
                    published_date="2026-10-02",
                    effective_from="2026-10-02",
                    source_data_dates=("2026-10-02",),
                    notice_reference="listing-notice-2330",
                ),
            ),
            source_ids=("exchange-status-2330", "mops-status-2330"),
            source_data_dates=("2026-10-02",),
            observed_at="2026-10-04T09:00:00+08:00",
            source_warnings=("部分市場限制來源沒有回應。",),
            partial_failure=True,
            scope="current_only",
            pit_eligible=False,
            limitations=("現況證據不能回填歷史。",),
        )
    )
    status_text = view.market_status_label.text()
    evidence_text = view.market_status_evidence_label.text()
    assert "部分來源可用" in status_text
    assert "上市狀態：已上市" in status_text
    assert "範圍：current_only" in status_text
    assert "可用於歷史 PIT：否" in status_text
    assert "公告日：2026-10-02" in status_text
    assert "有效期間：2026-10-03 至 2026-10-04" in status_text
    assert "不代表交易建議" in status_text
    assert "公告日：2026-10-02" in evidence_text
    assert "資料日：2026-10-02" in evidence_text
    assert "來源警示：部分市場限制來源沒有回應。" in status_text
    assert "部分來源讀取失敗" in status_text

    view._render_position(
        StockPositionSnapshotDTO(
            is_holding=True,
            position_as_of="2026-10-04",
            quote_data_date="2026-10-02",
            quote_available_at="",
            quantity=Decimal("1000"),
            average_cost=Decimal("99.50"),
            current_price=Decimal("100.00"),
            unrealized_pnl=Decimal("500.00"),
            last_trade_date="2026-10-03",
        )
    )
    position_page = view.tabs.widget(4).widget()
    tables = position_page.findChildren(QTableView)
    assert tables
    model = tables[0].model()
    rows = {
        str(model.index(row, 0).data()): str(model.index(row, 1).data())
        for row in range(model.rowCount())
    }
    assert rows["持倉讀取日"] == "2026-10-04"
    assert rows["行情資料日"] == "2026-10-02"
    assert rows["行情可得時間"] == "來源未提供"
    assert rows["最後交易日"] == "2026-10-03"
    assert rows["持倉讀取日"] != rows["最後交易日"]
    view.close()


def test_position_rerender_hides_stale_placeholder_before_deferred_delete(
    tmp_path: Path,
) -> None:
    app = _app()
    view = StockResearchReportView(_real_service(tmp_path))
    view.resize(860, 620)
    view._render_position(None)
    position_page = view.tabs.widget(4).widget()
    assert position_page is not None
    stale_label = next(
        label
        for label in position_page.findChildren(QLabel)
        if "沒有此股票的持倉 row" in label.text()
    )

    view.tabs.setCurrentIndex(4)
    view.show()
    app.processEvents()
    assert stale_label.isVisible()

    view._render_position(
        StockPositionSnapshotDTO(
            is_holding=True,
            position_as_of="2026-10-05",
            quote_data_date="2026-10-02",
            quote_available_at="",
            quantity=Decimal("1000"),
            average_cost=Decimal("281"),
            current_price=Decimal("332"),
            unrealized_pnl=Decimal("51000"),
        )
    )

    # The clear-and-render slot must hide stale content before Qt processes deleteLater().
    assert stale_label.isHidden()
    assert stale_label.parentWidget() is not None
    assert "沒有此股票的持倉 row" in stale_label.text()
    view.close()


def test_mainwindow_injects_current_restated_ml_registry_read_provider(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = _app()
    monkeypatch.setenv("DATA_ROOT", str(tmp_path / "data"))
    monkeypatch.setenv("OUTPUT_ROOT", str(tmp_path / "output"))
    from app_module.stock_research_report_provider_adapters import (
        CurrentRestatedMLRunRegistry,
    )
    from ui_qt.main import MainWindow, _drain_qt_deferred_deletes

    window = MainWindow()
    try:
        assert isinstance(window.stock_research_ml_registry, CurrentRestatedMLRunRegistry)
        assert window.stock_research_report_service.ml_provider is (
            window.stock_research_ml_registry
        )
        assert callable(window.stock_research_report_service.ml_provider)
    finally:
        window.close()
        app.processEvents()
        _drain_qt_deferred_deletes(app, (window,))


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


def _chart_report(
    code: str,
    as_of: str,
    dates: tuple[str, ...],
    *,
    source_context: dict[str, str] | None = None,
) -> StockResearchReportDTO:
    points = tuple(
        StockPricePointDTO(
            data_date=data_date,
            open_price=Decimal("10")
            + Decimal(index)
            + Decimal("0.123456789123456789"),
            high_price=Decimal("10")
            + Decimal(index)
            + Decimal("0.987654321987654321"),
            low_price=Decimal("10")
            + Decimal(index)
            + Decimal("0.111111111111111111"),
            close_price=Decimal("10")
            + Decimal(index)
            + Decimal("0.456789123456789123"),
            change=Decimal("0.123456789123456789"),
            volume=9_876_543_210 + index,
            turnover=Decimal("123456789.123456789") + Decimal(index),
            source_id="sqlite.daily_prices",
        )
        for index, data_date in enumerate(dates)
    )
    return StockResearchReportDTO(
        stock_code=code,
        stock_name=code,
        as_of=as_of,
        sources=(
            StockReportSourceDTO(
                source_id="sqlite.daily_prices",
                source_label="每日價格",
            ),
        ),
        price_points=points,
        research_context=source_context or {},
    )


def _price_page_table(view: StockResearchReportView) -> QTableView | None:
    layout = view._page_layouts["price"]
    for index in range(layout.count()):
        widget = layout.itemAt(index).widget()
        if (
            isinstance(widget, QTableView)
            and widget.objectName() == "stockResearchPriceHistoryTable"
        ):
            return widget
    return None


def test_price_projection_drives_exact_table_and_native_chart_at_cutoff() -> None:
    _app()
    context = ResearchStockContextDTO(
        stock_code="2330",
        decision_date="2026-09-07",
    )
    report = _chart_report(
        "2330",
        "2026-09-07",
        ("2026-09-06", "2026-09-07", "2026-09-08"),
        source_context={"decision_date": "2026-09-07"},
    )
    view = StockResearchReportView(SimpleNamespace())
    view._active_code = "2330"
    view._loaded_request_context = context
    view._render_price(report)

    chart = next(
        widget
        for index in range(view._page_layouts["price"].count())
        if isinstance(
            (widget := view._page_layouts["price"].itemAt(index).widget()),
            StockPriceChartWidget,
        )
    )
    assert tuple(point.data_date for point in chart._points) == (
        "2026-09-06",
        "2026-09-07",
    )
    table = _price_page_table(view)
    assert table is not None and table.model() is not None
    model = table.model()
    assert model.rowCount() == 2
    assert model.columnCount() == 8
    assert model.index(0, 0).data() == "2026-09-07"
    assert model.index(0, 1).data() == "11.123456789123456789"
    assert model.index(0, 2).data() == "11.987654321987654321"
    assert model.index(0, 3).data() == "11.111111111111111111"
    assert model.index(0, 4).data() == "11.456789123456789123"
    assert model.index(0, 6).data() == "9,876,543,211"
    assert model.index(0, 7).data() == "123,456,790.123456789"
    assert model.index(1, 0).data() == "2026-09-06"

    tooltip = chart._point_tooltip(chart._points[-1])
    assert "11.123456789123456789" in tooltip
    assert "9,876,543,211" in tooltip
    assert "來源：" not in tooltip
    assert "可得時間：" not in tooltip
    assert "SHA-256" not in tooltip

    metadata = next(
        widget
        for index in range(view._page_layouts["price"].count())
        if isinstance(
            (widget := view._page_layouts["price"].itemAt(index).widget()),
            QLabel,
        )
        and widget.objectName() == "stockResearchPriceChartRange"
    )
    assert "截止日：2026-09-07" in metadata.text()
    assert "每日價格" in metadata.text()
    assert "可得時間：未知（來源未提供）" in metadata.text()
    assert "歷史可得性（PIT）尚未核證" in metadata.text()
    assert "價格列指紋核對：unknown" in metadata.toolTip()
    assert "歷史 PIT 核證：not eligible" in metadata.toolTip()
    view.close()


@pytest.mark.parametrize("failure_stage", ["constructor", "set_points"])
def test_native_chart_failure_keeps_projected_exact_price_table(
    failure_stage: str,
    monkeypatch,
) -> None:
    _app()
    report = _chart_report("2330", "2026-09-07", ("2026-09-07",))
    if failure_stage == "constructor":
        def _fail_constructor(*_args, **_kwargs):
            raise RuntimeError("native constructor failed")

        monkeypatch.setattr(
            "ui_qt.views.stock_research_report_view.StockPriceChartWidget",
            _fail_constructor,
        )
    else:
        def _fail_set_points(_self, _points) -> None:
            raise RuntimeError("native set_points failed")

        monkeypatch.setattr(StockPriceChartWidget, "set_points", _fail_set_points)

    view = StockResearchReportView(SimpleNamespace())
    view._active_code = "2330"
    view._render_price(report)

    fallback = next(
        widget
        for index in range(view._page_layouts["price"].count())
        if isinstance(
            (widget := view._page_layouts["price"].itemAt(index).widget()),
            QLabel,
        )
        and widget.objectName() == "stockResearchPriceChartFallback"
    )
    assert "仍保留同一投影的精確價格資料" in fallback.text()
    assert fallback.toolTip() == f"native {failure_stage} failed"
    table = _price_page_table(view)
    assert table is not None and table.model() is not None
    assert table.model().rowCount() == 1
    assert table.model().index(0, 4).data() == "10.456789123456789123"
    view.close()


def test_source_pin_rejection_hides_old_chart_and_table_values() -> None:
    _app()
    view = StockResearchReportView(SimpleNamespace())
    view._active_code = "2330"
    valid_report = _chart_report("2330", "2026-09-07", ("2026-09-07",))
    view._render_price(valid_report)
    assert _price_page_table(view) is not None

    context = ResearchStockContextDTO(
        stock_code="2330",
        decision_date="2026-09-07",
        result_id="expected-result",
    )
    mismatched_report = _chart_report(
        "2330",
        "2026-09-07",
        ("2026-09-07",),
        source_context={
            "decision_date": "2026-09-07",
            "result_id": "different-result",
        },
    )
    view._loaded_request_context = context
    view._render_price(mismatched_report)

    assert _price_page_table(view) is None
    labels = [
        view._page_layouts["price"].itemAt(index).widget()
        for index in range(view._page_layouts["price"].count())
    ]
    failure_panel = next(
        widget
        for widget in labels
        if widget is not None and widget.toolTip() == "source_context_pin_mismatch"
    )
    assert "股號、日期或來源核對失敗" in failure_panel.text()
    assert "different-result" not in failure_panel.text()
    view.close()


def test_report_load_rejects_wrong_stock_and_pinned_date_before_summary() -> None:
    _app()
    view = StockResearchReportView(SimpleNamespace())
    view._active_code = "2330"
    view._request_id = 4
    loaded: list[StockResearchReportDTO] = []
    failures: list[str] = []
    view.reportLoaded.connect(loaded.append)
    view.reportFailed.connect(failures.append)

    view._on_report_loaded(4, "2330", _report_for("2317", "100"))
    assert loaded == []
    assert failures and "報告股票代碼不符" in failures[-1]
    assert view._loaded_report is None

    context = ResearchStockContextDTO(
        stock_code="2330",
        decision_date="2026-09-07",
        source_kind="recommendation",
    )
    view.context = context
    view._request_id = 5
    view._on_report_loaded(
        5,
        "2330",
        _chart_report("2330", "2026-09-08", ("2026-09-08",)),
        context,
    )
    assert loaded == []
    assert failures and "報告資料日不符" in failures[-1]
    assert view._loaded_report is None
    view.close()


def test_saved_source_a_b_a_restores_cutoffs_and_current_scope_uses_report_date() -> None:
    _app()
    view = StockResearchReportView(SimpleNamespace())
    view._active_code = "2330"
    view.tabs.setCurrentIndex(1)

    scenarios = (
        (
            ResearchStockContextDTO(
                stock_code="2330",
                decision_date="2026-09-06",
                result_id="saved-A",
                source_id="saved-A",
                source_kind="recommendation",
                ml_scope_mode="selected_saved_decision",
            ),
            "2026-09-06",
            ("2026-09-05", "2026-09-06", "2026-09-07"),
            ("2026-09-05", "2026-09-06"),
        ),
        (
            ResearchStockContextDTO(
                stock_code="2330",
                decision_date="2026-09-05",
                result_id="saved-B",
                source_id="saved-B",
                source_kind="recommendation",
                ml_scope_mode="selected_saved_decision",
            ),
            "2026-09-05",
            ("2026-09-04", "2026-09-05", "2026-09-06"),
            ("2026-09-04", "2026-09-05"),
        ),
        (
            ResearchStockContextDTO(
                stock_code="2330",
                decision_date="2026-09-06",
                result_id="saved-A",
                source_id="saved-A",
                source_kind="recommendation",
                ml_scope_mode="selected_saved_decision",
            ),
            "2026-09-06",
            ("2026-09-05", "2026-09-06", "2026-09-07"),
            ("2026-09-05", "2026-09-06"),
        ),
        (
            ResearchStockContextDTO(
                stock_code="2330",
                decision_date="2026-09-05",
                ml_scope_mode="current_stock_research",
            ),
            "2026-09-07",
            ("2026-09-05", "2026-09-06", "2026-09-07"),
            ("2026-09-05", "2026-09-06", "2026-09-07"),
        ),
    )

    for request_id, (context, as_of, dates, expected_dates) in enumerate(
        scenarios,
        start=1,
    ):
        source_context = {
            key: value
            for key, value in (
                ("decision_date", context.decision_date),
                ("result_id", context.result_id),
                ("source_id", context.source_id),
                ("source_kind", context.source_kind),
                ("ml_scope_mode", context.ml_scope_mode),
            )
            if value
        }
        report = _chart_report(
            "2330",
            as_of,
            dates,
            source_context=source_context,
        )
        view.context = context
        view._active_code = "2330"
        view._request_id = request_id
        view._on_report_loaded(request_id, "2330", report, context)

        chart = next(
            widget
            for index in range(view._page_layouts["price"].count())
            if isinstance(
                (widget := view._page_layouts["price"].itemAt(index).widget()),
                StockPriceChartWidget,
            )
        )
        assert tuple(point.data_date for point in chart._points) == expected_dates
        table = _price_page_table(view)
        assert table is not None and table.model() is not None
        assert tuple(
            table.model().index(row, 0).data()
            for row in range(table.model().rowCount())
        ) == tuple(reversed(expected_dates))
    view.close()


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


def test_current_ml_scope_switch_keeps_exact_saved_advice_identity() -> None:
    app = _app()
    saved = ResearchStockContextDTO(
        stock_code="1477",
        stock_name="聚陽",
        decision_date="2026-09-23",
        data_date="2026-09-22",
        result_id="rec-1477-exact",
        identity_status="linked",
        source_snapshot_id="snapshot-1477",
        source_snapshot_hash="sha256:" + "a" * 64,
        source_id="rec-1477-exact",
        source_kind="recommendation",
        source_label="已保存篩選紀錄／未入選",
        source_workspace="recommendation",
        ml_scope_mode="selected_saved_decision",
    )
    view = StockResearchReportView(SimpleNamespace())
    view.context = saved
    view._saved_decision_context = saved
    view._active_code = "1477"
    view._loaded_report = _report_for("1477", "123")
    view._load_stock = lambda _code: None
    view._render_decision(view._loaded_report)
    view.tabs.setCurrentIndex(5)
    view.show()
    app.processEvents()
    assert view.current_ml_mode_button.isVisible()
    assert view.current_ml_mode_button.isEnabled()
    QTest.mouseClick(view.current_ml_mode_button, Qt.LeftButton)

    assert view.context is not None
    assert view.context.ml_scope_mode == "current_stock_research"
    assert view.context.result_id == saved.result_id
    assert view.context.decision_date == saved.decision_date
    assert view.context.source_snapshot_id == saved.source_snapshot_id
    assert view.context.source_snapshot_hash == saved.source_snapshot_hash
    assert "不合併保存 Advice" in view.context_path_label.text()
    current_context = view.context

    view._render_decision(view._loaded_report)
    app.processEvents()
    assert view.saved_ml_mode_button.isVisible()
    assert view.saved_ml_mode_button.isEnabled()
    QTest.mouseClick(view.saved_ml_mode_button, Qt.LeftButton)

    assert view.context == saved
    assert view.context.ml_scope_mode == "selected_saved_decision"
    assert current_context.ml_scope_mode == "current_stock_research"
    assert view.context.ml_scope_mode == "selected_saved_decision"

    view.context = replace(view.context, stock_code="1101")
    view._active_code = "1101"
    view._loaded_report = _report_for("1101", "77")
    view._render_decision(view._loaded_report)
    app.processEvents()
    assert view.saved_ml_mode_button.isHidden()
    QTest.mouseClick(view.current_ml_mode_button, Qt.LeftButton)
    assert view._saved_decision_context == saved
    view._use_selected_saved_decision_mode()
    assert view._saved_decision_context == saved
    assert view.context.stock_code == "1101"
    assert view.context.ml_scope_mode == "current_stock_research"
    view.close()
    app.processEvents()


def test_新建研究頁從現況範圍可返回精確保存決策() -> None:
    app = _app()
    saved_context = ResearchStockContextDTO(
        stock_code="1477",
        stock_name="聚陽",
        decision_date="2026-09-23",
        data_date="2026-09-22",
        result_id="rec-1477-exact",
        identity_status="linked",
        source_snapshot_id="snapshot-1477",
        source_snapshot_hash="sha256:" + "a" * 64,
        source_id="rec-1477-exact",
        source_kind="recommendation",
        source_label="已保存篩選紀錄／未入選",
        source_workspace="recommendation",
        ml_scope_mode="selected_saved_decision",
    )
    current_context = replace(saved_context, ml_scope_mode="current_stock_research")
    view = StockResearchReportView(SimpleNamespace())
    view._load_stock = lambda _code: None
    view._active_code = "1477"

    # 這是新建的 view，只收到當下模式 DTO；不得依賴原 view 的暫存欄位。
    view.set_context(current_context)
    report = _report_for("1477", "123")
    view._loaded_report = report
    view._render_decision(report)
    view.tabs.setCurrentIndex(5)
    view.show()
    app.processEvents()

    expected_saved_context = replace(
        current_context,
        ml_scope_mode="selected_saved_decision",
    )
    assert view._saved_decision_context == expected_saved_context
    assert view.saved_ml_mode_button.isVisible()
    assert view.saved_ml_mode_button.isEnabled()
    QTest.mouseClick(view.saved_ml_mode_button, Qt.LeftButton)

    assert view.context == expected_saved_context
    assert view.context.result_id == saved_context.result_id
    assert view.context.decision_date == saved_context.decision_date
    assert view.context.data_date == saved_context.data_date
    assert view.context.source_id == saved_context.source_id
    assert view.context.source_snapshot_id == saved_context.source_snapshot_id
    assert view.context.source_snapshot_hash == saved_context.source_snapshot_hash
    view.close()
    app.processEvents()


def test_新建研究頁的現況context沒有result_id不建立保存備份() -> None:
    app = _app()
    view = StockResearchReportView(SimpleNamespace())
    view._load_stock = lambda _code: None
    view._active_code = "1477"
    view.set_context(
        ResearchStockContextDTO(
            stock_code="1477",
            stock_name="聚陽",
            ml_scope_mode="current_stock_research",
        )
    )
    report = _report_for("1477", "123")
    view._loaded_report = report
    view._render_decision(report)
    view.tabs.setCurrentIndex(5)
    view.show()
    app.processEvents()

    assert view._saved_decision_context is None
    assert view.saved_ml_mode_button.isHidden()
    view.close()
    app.processEvents()


def test_same_stock_source_change_clears_old_report_while_new_run_loads(monkeypatch) -> None:
    from ui_qt.views import stock_research_report_view as view_module

    class _Signal:
        def connect(self, _callback):
            return None

    class _PendingWorker:
        def __init__(self, _task):
            self.started = _Signal()
            self.finished = _Signal()
            self.error = _Signal()
            self.cancelled = _Signal()
            self.native_thread_finished = _Signal()

        def start(self):
            return None

        def isRunning(self):
            return False

    monkeypatch.setattr(view_module, "TaskWorker", _PendingWorker)
    first = ResearchStockContextDTO(
        stock_code="1477",
        decision_date="2026-09-23",
        data_date="2026-09-22",
        result_id="rec-first",
        source_snapshot_id="snapshot-first",
        source_snapshot_hash="sha256:" + "a" * 64,
        source_workspace="recommendation",
    )
    second = ResearchStockContextDTO(
        stock_code="1477",
        decision_date="2026-09-24",
        data_date="2026-09-23",
        result_id="rec-second",
        source_snapshot_id="snapshot-second",
        source_snapshot_hash="sha256:" + "b" * 64,
        source_workspace="recommendation",
    )
    view = StockResearchReportView(SimpleNamespace(), first)
    view._loaded_report = _report_for("1477", "123")
    view._loaded_context_identity = view._context_identity(first, "1477")

    view.set_context(second)

    assert view.context == second
    assert view._loaded_report is None
    assert view._loaded_context_identity is None
    assert "載入中" in view.summary_focus.conclusion_label.text()
    view.close()


def test_market_status_clears_on_switch_and_keeps_same_stock_last_good() -> None:
    app = _app()
    view = StockResearchReportView(SimpleNamespace())
    old_report = _report_for("1477", "123")
    view._active_code = "1477"
    view._loaded_report = old_report
    view._loaded_context_identity = view._context_identity(None, "1477")
    view._render_market_status(
        StockMarketStatusSnapshotDTO(
            status="available",
            listing_status="listed",
            market="上市",
            name="聚陽",
            source_ids=("status-source-1477",),
            source_data_dates=("2026-10-02",),
            observed_at="2026-10-04T09:00:00+08:00",
            scope="current_only",
            pit_eligible=False,
        )
    )

    view._set_loading_state("1477")
    assert "status-source-1477" in view.market_status_evidence_label.text()
    assert "重新載入中；以下內容是同一檔股票的上次可用資料。" in (
        view.summary_focus.conclusion_label.text()
    )
    view._on_report_cancelled(view._request_id, "1477")
    assert "status-source-1477" in view.market_status_evidence_label.text()
    assert "讀取已取消；畫面仍保留同一檔股票的上次可用資料。" in (
        view.summary_focus.conclusion_label.text()
    )

    view._request_id += 1
    view._active_code = "2382"
    view._set_loading_state("2382")
    assert view.market_status_label.text() == "當下上市／交易狀態：尚未載入本股。"
    assert view.market_status_evidence_label.text() == "尚未載入本股的狀態來源證據。"
    assert "status-source-1477" not in view.market_status_evidence_label.text()
    view._on_report_cancelled(view._request_id, "2382")
    assert view.market_status_label.text() == "當下上市／交易狀態：尚未載入本股。"
    assert view.market_status_evidence_label.text() == "尚未載入本股的狀態來源證據。"
    assert "讀取已取消" in view.summary_focus.conclusion_label.text()
    view.close()
    app.processEvents()


def test_ml_panel_displays_integer_bp_h5_and_exact_current_scope() -> None:
    view = StockResearchReportView(SimpleNamespace())
    view.context = ResearchStockContextDTO(
        stock_code="1477",
        decision_date="2026-09-23",
        result_id="rec-1477-exact",
        source_snapshot_hash="sha256:" + "a" * 64,
        source_workspace="recommendation",
        ml_scope_mode="current_stock_research",
    )
    report = _report_for("1477", "123")
    report = replace(
        report,
        advice=StockAdviceSnapshotDTO(rule_reasons=("保存來源原理由",)),
        rule_reasons=("當下趨勢觀測", "保存來源原理由", "歷史事件風險"),
        events=(
            StockEvidenceEventDTO(
                event_id="event-1477-old",
                event_date="2026-10-01",
                decision_date="2026-10-01",
                event_type="historical_advice",
                reasons=("歷史事件風險",),
            ),
        ),
        ml=StockMLSnapshotDTO(
            status="degraded",
            model_version="current-restated-v1",
            dataset_version="dataset-current-v1",
            inference_at="2026-10-04T08:00:00+00:00",
            research_or_formal="research_only",
            run_id="run-1477-20261004",
            scope_mode="current_stock_research",
            event_date="2026-10-02",
            model_manifest_sha256="sha256:" + "b" * 64,
            model_bundle_sha256="sha256:" + "c" * 64,
            source_snapshot_hash="sha256:" + "d" * 64,
            target_metric="cost-adjusted benchmark excess bp",
            predicted_benchmark_excess_return_bp={"H5": 128},
            h5_status="mature",
            h5_horizon=5,
            h5_gross_stock_return_bp=420,
            h5_gross_benchmark_return_bp=180,
            h5_benchmark_excess_after_standard_80bp_cost=160,
            h5_after_lane_cost_stock_return_bp=340,
            h5_horizon_end_date="2026-10-02",
            scope_symbols=("1477",),
            qualification=("僅研究，不具歷史 PIT 或正式資格",),
        ),
    )
    view._active_code = "1477"
    view._render_report(report)
    view._render_decision(report)

    tables = {table.objectName(): table for table in view.findChildren(QTableView)}
    ml_identity = tables["stockResearchMLIdentityTable"].model()
    rendered_identity = [
        ml_identity.data(ml_identity.index(row, 1), Qt.DisplayRole)
        for row in range(ml_identity.rowCount())
    ]
    assert "當下個股獨立研究（不併入保存 Advice）" in rendered_identity
    assert "run-1477-20261004" in rendered_identity
    assert "2026-10-02" in rendered_identity
    assert "current-stock independent research" not in "\n".join(rendered_identity)

    prediction_model = tables["stockResearchMLBenchmarkExcessTable"].model()
    assert prediction_model.data(prediction_model.index(0, 0), Qt.DisplayRole) == "H5"
    assert prediction_model.data(prediction_model.index(0, 1), Qt.DisplayRole) == "+128 bp"
    h5_model = tables["stockResearchMLH5Table"].model()
    h5_rows = {
        h5_model.data(h5_model.index(row, 0), Qt.DisplayRole): h5_model.data(
            h5_model.index(row, 1), Qt.DisplayRole
        )
        for row in range(h5_model.rowCount())
    }
    assert h5_rows["H5 狀態"] == "mature"
    assert h5_rows["基準超額（扣標準 80bp）"] == "160 bp"
    assert view.query_as_of_label.text().startswith("本次當下觀測日（as_of）")
    assert "保存 Advice 決策日：2026-09-23" in view.query_as_of_label.text()
    assert "不併入保存 Advice" in view.query_as_of_label.text()
    rule_group_titles = {
        group.title()
        for group in view.findChildren(QGroupBox)
        if "Rule 證據" in group.title() or "已保存 Advice 原 Rule 理由" in group.title()
    }
    assert "當下技術／Rule 證據（本次資料日期：2026-09-08）" in rule_group_titles
    assert "已保存 Advice 原 Rule 理由（原決策日：2026-09-23）" in rule_group_titles
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


def _saved_analysis_report(
    *,
    status: str = "saved",
    stock_code: str = "1477",
    result_id: str = "rec-1477-run",
    decision_date: str = "2026-10-05",
    data_date: str = "2026-10-02",
    report_stock_code: str = "1477",
) -> StockResearchReportDTO:
    analysis = WatchlistAnalysisDTO(
        stock_code=stock_code,
        status=status,
        result_id=result_id,
        decision_date=decision_date,
        data_date=data_date,
    )
    return replace(
        _report_for(report_stock_code, "123"),
        as_of="2026-10-05",
        advice=StockAdviceSnapshotDTO(
            status="degraded" if status == "saved" else "unavailable",
            saved_analysis=analysis,
        ),
    )


def _blank_saved_source_context(
    *,
    stock_code: str = "1477",
    result_id: str = "rec-1477-run",
    decision_date: str = "2026-10-05",
) -> ResearchStockContextDTO:
    return ResearchStockContextDTO(
        stock_code=stock_code,
        decision_date=decision_date,
        data_date="",
        result_id=result_id,
        source_id=result_id,
        source_kind="recommendation",
        source_workspace="recommendation",
    )


@pytest.mark.parametrize("analysis_status", ["saved", "not_in_result"])
def test_report_loaded_backfills_same_saved_result_quote_date_everywhere(
    analysis_status: str,
) -> None:
    view = StockResearchReportView(SimpleNamespace())
    context = _blank_saved_source_context()
    saved_context = replace(context, ml_scope_mode="selected_saved_decision")
    report = _saved_analysis_report(status=analysis_status)
    view.context = context
    view._saved_decision_context = saved_context
    view._active_code = "1477"
    view._request_id = 7
    context_events: list[ResearchStockContextDTO] = []
    report_events: list[StockResearchReportDTO] = []
    view.activeContextChanged.connect(context_events.append)
    view.reportLoaded.connect(report_events.append)

    view._on_report_loaded(7, "1477", report, context)

    assert view.context == replace(context, data_date="2026-10-02")
    assert view._saved_decision_context == replace(saved_context, data_date="2026-10-02")
    assert "資料日：2026-10-02" in view.context_path_label.text()
    assert view._loaded_context_identity == view._context_identity(view.context, "1477")
    assert len(context_events) == 1
    assert asdict(context_events[0]) == asdict(view.context)
    assert asdict(context_events[0])["data_date"] == "2026-10-02"
    assert report_events == [report]
    assert report_events[0].to_dict()["advice"]["saved_analysis"]["data_date"] == "2026-10-02"
    view.close()


@pytest.mark.parametrize(
    "case",
    [
        "no_analysis",
        "unsupported_status",
        "wrong_saved_stock",
        "wrong_saved_result",
        "wrong_saved_decision",
        "future_quote_date",
        "noncanonical_quote_date",
        "wrong_report_stock",
        "wrong_context_stock",
        "wrong_context_result",
        "wrong_context_decision",
    ],
)
def test_report_loaded_does_not_backfill_unbound_or_invalid_quote_date(case: str) -> None:
    view = StockResearchReportView(SimpleNamespace())
    context = _blank_saved_source_context()
    report = _saved_analysis_report()

    if case == "no_analysis":
        report = replace(report, advice=StockAdviceSnapshotDTO(status="unavailable"))
    elif case == "unsupported_status":
        report = _saved_analysis_report(status="missing")
    elif case == "wrong_saved_stock":
        report = _saved_analysis_report(stock_code="2382")
    elif case == "wrong_saved_result":
        report = _saved_analysis_report(result_id="rec-other-run")
    elif case == "wrong_saved_decision":
        report = _saved_analysis_report(decision_date="2026-10-04")
    elif case == "future_quote_date":
        report = _saved_analysis_report(data_date="2026-10-06")
    elif case == "noncanonical_quote_date":
        report = _saved_analysis_report(data_date="2026-10-2")
    elif case == "wrong_report_stock":
        report = _saved_analysis_report(report_stock_code="2382")
    elif case == "wrong_context_stock":
        context = _blank_saved_source_context(stock_code="2382")
    elif case == "wrong_context_result":
        context = _blank_saved_source_context(result_id="rec-other-run")
    elif case == "wrong_context_decision":
        context = _blank_saved_source_context(decision_date="2026-10-04")

    view.context = context
    view._render_context_path()
    view._active_code = "1477"
    view._request_id = 9
    context_events: list[ResearchStockContextDTO] = []
    view.activeContextChanged.connect(context_events.append)

    view._on_report_loaded(9, "1477", report, context)

    assert view.context == context
    assert view.context.data_date == ""
    assert "資料日：未知" in view.context_path_label.text()
    assert context_events == []
    if case in {"wrong_report_stock", "wrong_context_decision"}:
        assert view._loaded_context_identity is None
        assert view._loaded_report is None
    else:
        assert view._loaded_context_identity == view._context_identity(context, "1477")
    view.close()


def test_report_loaded_never_overwrites_nonempty_context_date_even_if_conflicting() -> None:
    view = StockResearchReportView(SimpleNamespace())
    context = replace(_blank_saved_source_context(), data_date="2026-10-01")
    report = _saved_analysis_report(data_date="2026-10-02")
    view.context = context
    view._render_context_path()
    view._active_code = "1477"
    view._request_id = 11
    context_events: list[ResearchStockContextDTO] = []
    view.activeContextChanged.connect(context_events.append)

    view._on_report_loaded(11, "1477", report, context)

    assert view.context == context
    assert "資料日：2026-10-01" in view.context_path_label.text()
    assert context_events == []
    view.close()
