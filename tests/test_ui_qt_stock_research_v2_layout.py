"""V2 個股研究工作區導覽不替換既有報告、來源或保存元件。"""

from __future__ import annotations

from decimal import Decimal
import threading
import time
from types import SimpleNamespace
from typing import Any

import pytest

from PySide6.QtWidgets import QApplication, QBoxLayout

from app_module.research_session import ResearchStockContextDTO
from app_module.stock_research_report_dtos import (
    StockPricePointDTO,
    StockMLSnapshotDTO,
    StockResearchReportDTO,
)
from app_module.stock_research_report_snapshot_codec import (
    create_stock_research_report_projection_snapshot,
)
from ui_qt.views.stock_research_workspace import StockResearchWorkspace

pytest_plugins = ("tests.test_daily_market_technical_universe_price_query_v1",)


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _wait(app: QApplication, predicate, timeout: float = 4.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        time.sleep(0.005)
    app.processEvents()
    assert predicate(), "個股研究背景工作未在期限內結束"


def _report(code: str = "2330") -> StockResearchReportDTO:
    return StockResearchReportDTO(
        stock_code=code,
        stock_name="測試名稱",
        as_of="2026-10-16",
        generated_at="2026-10-17T01:02:03+08:00",
        price_points=(
            StockPricePointDTO(
                data_date="2026-10-16", close_price=Decimal("100.0100")
            ),
        ),
        limitations=("保存來源缺件維持原樣",),
    )


class _ReadService:
    def read_report(self, stock_code: str, **_kwargs):
        return _report(stock_code)


class _NotesService:
    def __init__(self):
        self.writes = 0
        self.reads = 0

    def list_notes(self, *, stock_code: str):
        self.reads += 1
        return ()

    def get_note(self, *_args, **_kwargs):
        return None

    def save(self, *_args, **_kwargs):
        self.writes += 1
        raise AssertionError("只切換到保存判斷頁不得呼叫 writer")


def _price_selection(fixture: dict[str, Any]):
    from app_module.daily_market_technical_universe_price_comparison_v1 import (
        DailyMarketTechnicalUniversePriceSelectionV1,
    )
    from app_module.daily_market_technical_universe_price_query_v1 import (
        open_daily_market_technical_universe_price_read_session_v1,
    )

    plan = fixture["plan"]
    receipt = fixture["receipt"]
    session = open_daily_market_technical_universe_price_read_session_v1(
        store_output_root=fixture["store_root"],
        generation_identity_sha256=plan.generation_identity_sha256,
        plan_identity_sha256=plan.identity_sha256,
        plan_sha256=fixture["plan_sha256"],
        receipt_identity_sha256=receipt.identity_sha256,
        receipt_sha256=receipt.content_sha256,
    )
    query = session.create_query(unknown_price_policy="include")
    result = session.execute(query)
    request = result.create_page_request(0, page_size=4)
    page = result.read_page(request)
    stock = result.read_stock_snapshot(request, "S0001")
    selection = DailyMarketTechnicalUniversePriceSelectionV1.from_page(
        query, page, "S0001"
    )
    return stock, selection


def test_workspace_uses_action_row_and_all_six_report_sections_remain_reachable():
    app = _app()
    notes = _NotesService()
    workspace = StockResearchWorkspace(
        _ReadService(),
        journey_service=SimpleNamespace(build=lambda *_args, **_kwargs: None),
        report_note_service=notes,
    )
    try:
        report = workspace.report_view
        assert workspace.report_tabs.tabBar().isHidden()
        assert report.tabs.tabBar().isHidden()
        assert not workspace.product_action_row.isHidden()
        assert not workspace.save_judgment_action.isHidden()
        assert not workspace.outcome_tracking_action.isHidden()
        assert report.section_selector.count() == 6

        section_keys = (
            "summary", "price", "fundamental", "flows", "position", "decision",
        )
        for index, key in enumerate(section_keys):
            assert workspace.focus_section(key)
            app.processEvents()
            assert report.tabs.currentWidget() is report.tabs.widget(index)
            assert report.section_selector.currentData() == key

        workspace.report_tabs.setCurrentWidget(workspace.report_notes_page)
        assert workspace.save_judgment_action.isChecked()
        _wait(app, lambda: not workspace.report_notes_widget.is_busy())
        assert notes.reads == 1
        assert notes.writes == 0
        assert workspace.focus_section("fundamental")
        assert workspace.report_tabs.currentWidget() is report
        assert report.tabs.currentIndex() == 2

        workspace.report_tabs.setCurrentWidget(workspace.journey_view)
        assert workspace.outcome_tracking_action.isChecked()
        workspace.report_tabs.setCurrentWidget(report)
        assert workspace.research_content_action.isChecked()
    finally:
        workspace.request_close()
        _wait(app, lambda: not workspace.is_busy())
        workspace.close()


def test_overview_shows_same_source_chart_with_evidence_and_clears_on_stock_change(monkeypatch):
    app = _app()
    from ui_qt.views.stock_research_report_view import StockResearchReportView

    view = StockResearchReportView(_ReadService())
    view.enable_product_layout()
    view.resize(1200, 850)
    view.show()
    try:
        view.set_context(ResearchStockContextDTO(stock_code="2330"))
        _wait(app, lambda: view._loaded_report is not None and not view.is_busy())
        assert view.tabs.currentIndex() == 0
        assert view.overview_chart.isVisible()
        assert view.summary_focus.isVisible()
        assert view.overview_chart._points == _report().price_points
        assert "2026-10-16" in view.overview_chart_caption.text()
        assert "不是即時報價" in view.overview_chart_caption.text()
        assert "保存這次研究判斷" in view.summary_focus.next_step_label.text()
        assert "H20" not in view.summary_focus.next_step_label.text()
        assert view.overview_layout.direction() == QBoxLayout.LeftToRight
        assert view.overview_chart.mapTo(view, view.overview_chart.rect().topLeft()).x() < view.summary_focus.mapTo(view, view.summary_focus.rect().topLeft()).x()
        assert "完整缺件原因見資料稽核" in view.summary_focus.sufficiency_label.text()
        assert "保存來源缺件" in view.summary_limitations_detail_label.text()

        view.resize(740, 850)
        app.processEvents()
        assert view.overview_layout.direction() == QBoxLayout.TopToBottom
        assert view.overview_chart._points == _report().price_points
        loaded = view._loaded_report

        def fail_chart(_points):
            raise RuntimeError("fixture chart failure")

        with monkeypatch.context() as patch:
            patch.setattr(view.overview_chart, "set_points", fail_chart)
            view._render_overview_chart(_report())
            assert view.overview_chart.isHidden()
            assert "同來源精確價格表" in view.overview_chart_caption.text()
            assert view._loaded_report is loaded
            assert view.summary_focus.isVisible()
        view._clear_loaded_report()
        assert not view.overview_chart._points
        assert "本股" in view.overview_chart_caption.text()
    finally:
        view.request_close()
        _wait(app, lambda: not view.is_busy())
        view.close()


@pytest.mark.parametrize("inconsistent", [False, True])
def test_return_card_reuses_benchmark_cost_semantics_and_refuses_conflicting_fields(inconsistent):
    from dataclasses import replace
    from ui_qt.views.stock_research_report_view import StockResearchReportView

    app = _app()
    model = StockMLSnapshotDTO(
        status="degraded", research_only=True, formal_qualified=False,
        target_metric="benchmark_excess_after_standard_80bp_cost",
        predicted_benchmark_excess_return_bp={"H5": -100},
        h5_benchmark_excess_after_standard_80bp_cost=-120 if inconsistent else None,
        target_round_trip_cost_bp=80, target_buy_side_cost_bp=25, target_sell_side_cost_bp=55,
    )
    report = replace(_report(), ml=model)
    view = StockResearchReportView(SimpleNamespace(read_report=lambda *_args, **_kwargs: report))
    view.enable_product_layout()
    try:
        view.set_context(ResearchStockContextDTO(stock_code="2330"))
        _wait(app, lambda: view._loaded_report is not None and not view.is_busy())
        text = view.overview_return_label.text()
        if inconsistent:
            assert "原值欄位不一致" in text
            assert "-100" not in text and "-120" not in text
        else:
            assert "落後基準 1.00 個百分點" in text
            assert "總計 80 bp（買進 25 bp、賣出 55 bp）" in text
            assert "不換算為 H20 毛報酬" in text
        assert "不是獲利機率或已驗證收益" in text
        assert view._loaded_report.ml is model
        assert model.predicted_benchmark_excess_return_bp == {"H5": -100}
    finally:
        view.request_close()
        _wait(app, lambda: not view.is_busy())
        view.close()


def test_product_overview_constructor_failure_keeps_loaded_report(monkeypatch):
    app = _app()
    import ui_qt.views.stock_research_report_view as report_module

    def fail_chart(*_args, **_kwargs):
        raise RuntimeError("fixture chart constructor failure")

    monkeypatch.setattr(report_module, "StockPriceChartWidget", fail_chart)
    view = report_module.StockResearchReportView(_ReadService())
    view.enable_product_layout()
    try:
        view.set_context(ResearchStockContextDTO(stock_code="2330"))
        _wait(app, lambda: view._loaded_report is not None and not view.is_busy())
        assert view.overview_chart is None
        assert "同來源精確價格表" in view.overview_chart_caption.text()
        assert view._loaded_report.price_points == _report().price_points
        assert view.summary_focus.conclusion_label.text()
    finally:
        view.request_close()
        _wait(app, lambda: not view.is_busy())
        view.close()


def test_price_origin_and_saved_general_snapshot_keep_separate_dates_and_identity(
    exact_price_store: dict[str, Any],
):
    app = _app()
    stock, selection = _price_selection(exact_price_store)
    workspace = StockResearchWorkspace(_ReadService())
    try:
        workspace.show_price_research(stock, selection)
        app.processEvents()
        price_view = workspace.price_research_view
        assert price_view is not None
        assert workspace.content_stack.currentWidget() is workspace.price_research_page
        assert price_view.detail_tabs.tabBar().isHidden()
        assert workspace.price_section_selector.count() == 2
        assert "價格選股原來源（可得時間未知）" in workspace.price_source_header.text()
        assert "決策日 2026-10-06" in workspace.price_source_header.text()
        assert "資料日 2026-10-06" in workspace.price_source_header.text()

        workspace.focus_section("price_rules")
        assert price_view.detail_tabs.currentWidget() is price_view.evidence
        assert workspace.price_section_selector.currentText() == "原選股規則"
        workspace.focus_section("price_chart")
        assert price_view.detail_tabs.currentIndex() == 0

        historical_context = ResearchStockContextDTO(
            stock_code=stock.stock_code,
            decision_date="2026-10-06",
            data_date="2026-10-06",
            result_id="daily-result-20261006",
            identity_status="exact_saved_selection",
            source_id="daily-research-source",
            source_version="daily-research-version",
            source_kind="daily_market_research_snapshot",
            source_label="歷史釘定的母體價量研究",
            source_workspace="stock_research",
        )
        snapshot = create_stock_research_report_projection_snapshot(
            _report(stock.stock_code), historical_context
        )
        workspace.show_saved_report_snapshot(snapshot)
        saved_view = workspace.saved_report_view
        assert saved_view is not None
        assert saved_view.tabs.tabBar().isHidden()
        assert saved_view.context == historical_context
        assert saved_view.get_loaded_report_snapshot().identity_sha256 == snapshot.identity_sha256
        assert "2026-10-16" in saved_view.query_as_of_label.text()
        assert "2026-10-06" in saved_view.context_path_label.text()
        assert workspace.price_research_context.source_kind == "technical_price_saved_source"
        assert workspace.price_research_context.data_date == "2026-10-06"

        workspace.focus_section("fundamental")
        assert saved_view.tabs.currentIndex() == 2
        assert saved_view.get_loaded_report_snapshot().identity_sha256 == snapshot.identity_sha256
        assert workspace.report_tabs.tabBar().isHidden()
        workspace.research_content_action.click()
        assert workspace.report_tabs.currentWidget() is saved_view
        assert saved_view.get_loaded_report_snapshot().identity_sha256 == snapshot.identity_sha256
    finally:
        workspace.request_close()
        _wait(app, lambda: not workspace.is_busy())
        workspace.close()


def test_close_cancels_active_read_without_replacing_selected_saved_snapshot():
    app = _app()
    started = threading.Event()
    release = threading.Event()

    class DelayedRead:
        def read_report(self, stock_code: str, **_kwargs):
            started.set()
            assert release.wait(timeout=4)
            return _report(stock_code)

    report = _report("2330")
    context = ResearchStockContextDTO(
        stock_code="2330",
        decision_date="2026-10-16",
        data_date="2026-10-16",
        result_id="saved-result-2330",
        identity_status="exact_saved_selection",
        source_kind="daily_market_research_snapshot",
        source_label="歷史釘定研究",
    )
    snapshot = create_stock_research_report_projection_snapshot(report, context)
    workspace = StockResearchWorkspace(_ReadService())
    workspace.show_saved_report_snapshot(snapshot)
    saved_view = workspace.saved_report_view
    workspace.report_view.service = DelayedRead()
    try:
        workspace.set_context(
            ResearchStockContextDTO(
                stock_code="2317", source_kind="explicit_latest_stock_research"
            )
        )
        _wait(app, started.is_set)
        assert workspace.request_close() is False
        assert saved_view is not None
        assert saved_view.get_loaded_report_snapshot().identity_sha256 == snapshot.identity_sha256
        release.set()
        _wait(app, lambda: not workspace.report_view.is_busy())
        assert workspace.request_close() is True
        assert saved_view.get_loaded_report_snapshot().identity_sha256 == snapshot.identity_sha256
    finally:
        release.set()
        if workspace.is_busy():
            _wait(app, lambda: not workspace.is_busy())
        workspace.close()
