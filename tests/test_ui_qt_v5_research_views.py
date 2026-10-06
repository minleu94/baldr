"""V5 研究 UI 的摘要、圖表 fallback 與進階入口 focused tests。"""

from __future__ import annotations

from decimal import Decimal
import os
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QFont, QFontDatabase, QMouseEvent
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget

from app_module.stock_research_report_dtos import (
    ReportSectionStatus,
    StockPricePointDTO,
    StockResearchReportDTO,
    StockReportSectionDTO,
    StockTechnicalSnapshotDTO,
)
from ui_qt.views.stock_research_report_view import (
    StockPriceChartWidget,
    StockResearchReportView,
)
from ui_qt.views.watchlist_view import WatchlistView
from ui_qt.theme import build_global_stylesheet
from ui_qt.widgets.v5_research_summary import V5ResearchSummary


def _app() -> QApplication:
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication(sys.argv)
    return instance


def _send_chart_mouse_move(
    chart: StockPriceChartWidget,
    position: QPoint,
) -> None:
    """透過 Qt event dispatcher 將真實 mouse-move event 送至 chart widget。"""

    event = QMouseEvent(
        QEvent.Type.MouseMove,
        QPointF(position),
        QPointF(chart.mapToGlobal(position)),
        Qt.MouseButton.NoButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    assert QApplication.sendEvent(chart, event)


def _configure_visual_qa_theme(app: QApplication) -> None:
    """讓獨立 screenshot process 與正式 app 使用相同字體與 Midnight theme。"""

    app.setStyle("Fusion")
    font_id = QFontDatabase.addApplicationFont("C:/Windows/Fonts/msjh.ttc")
    families = (
        QFontDatabase.applicationFontFamilies(font_id)
        if font_id >= 0
        else []
    )
    family = str(families[0]) if families else "Microsoft JhengHei"
    app.setFont(QFont(family, 10))
    app.setStyleSheet(build_global_stylesheet())


def _mount_visual_qa_widget(
    widget: QWidget,
    app: QApplication,
    *,
    width: int = 1200,
    height: int = 800,
) -> QWidget:
    """在固定 viewport 中截圖，避免 top-level sizeHint 改寫 requested size。"""

    host = QWidget()
    host.setFixedSize(width, height)
    layout = QVBoxLayout(host)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(widget)
    host.show()
    app.processEvents()
    assert host.size().width() == width
    assert host.size().height() == height
    return host


def test_v5_summary_keeps_two_reasons_and_plain_next_step() -> None:
    _app()
    summary = V5ResearchSummary("摘要")
    summary.set_summary(
        conclusion="目前可讀",
        reasons=("依據一", "依據二", "不應出現在首屏"),
        next_step="核對資料日",
    )

    assert "依據一" in summary.reasons_label.text()
    assert "依據二" in summary.reasons_label.text()
    assert "不應出現在首屏" not in summary.reasons_label.text()
    assert summary.next_step_label.text() == "下一步：核對資料日"


def test_price_chart_requires_complete_ohlc_for_candles_and_volume() -> None:
    app = _app()
    chart = StockPriceChartWidget()
    chart.resize(720, 240)
    chart.show()
    complete = (
        StockPricePointDTO(
            data_date="2026-09-07",
            open_price=Decimal("99"),
            high_price=Decimal("103"),
            low_price=Decimal("98"),
            close_price=Decimal("102"),
            volume=1000,
        ),
        StockPricePointDTO(
            data_date="2026-09-08",
            open_price=Decimal("102"),
            high_price=Decimal("104"),
            low_price=Decimal("101"),
            close_price=Decimal("103"),
            volume=1500,
        ),
    )
    chart.set_points(complete)
    app.processEvents()
    assert chart.display_mode == "ohlc_volume"
    assert "K 線與成交量" in chart.toolTip()
    assert chart.grab().isNull() is False

    chart.set_points(
        (
            StockPricePointDTO(
                data_date="2026-09-08",
                open_price=Decimal("102"),
                high_price=None,
                low_price=Decimal("101"),
                close_price=Decimal("103"),
                volume=1500,
            ),
        )
    )
    app.processEvents()
    assert chart.display_mode == "close"
    assert "收盤價走勢" in chart.toolTip()
    chart.close()


def test_price_chart_hover_exposes_point_date_ohlc_volume_and_range() -> None:
    app = _app()
    chart = StockPriceChartWidget()
    screen = app.primaryScreen()
    available = screen.availableGeometry() if screen is not None else None
    if available is None:
        chart.resize(720, 240)
    else:
        chart.resize(
            max(140, min(720, available.width() - 40)),
            max(188, min(240, available.height() - 40)),
        )
        chart.move(available.topLeft())
    chart.show()
    try:
        points = (
            StockPricePointDTO(
                data_date="2026-09-07",
                open_price=Decimal("99"),
                high_price=Decimal("103"),
                low_price=Decimal("98"),
                close_price=Decimal("102"),
                volume=1000,
            ),
            StockPricePointDTO(
                data_date="2026-09-08",
                open_price=Decimal("102"),
                high_price=Decimal("104"),
                low_price=Decimal("101"),
                close_price=Decimal("103"),
                volume=1500,
            ),
            StockPricePointDTO(
                data_date="2026-09-09",
                open_price=Decimal("103"),
                high_price=Decimal("105"),
                low_price=Decimal("102"),
                close_price=Decimal("104"),
                volume=2000,
            ),
        )
        chart.set_points(points)
        app.processEvents()

        assert "圖表範圍：2026-09-07 至 2026-09-09" in chart.toolTip()
        assert "最新涵蓋日：2026-09-09" in chart.toolTip()

        # This widget-level regression should exercise the chart's real Qt handler
        # without relying on process-wide cursor/window hit-testing.
        plot_left, plot_right = chart._plot_x_bounds()
        middle_x = (plot_left + plot_right) // 2
        last_x = max(plot_left, plot_right - 2)
        _send_chart_mouse_move(chart, QPoint(10, chart.height() - 10))
        app.processEvents()
        _send_chart_mouse_move(chart, QPoint(plot_left, 80))
        app.processEvents()
        first_tooltip = chart.toolTip()
        assert "資料日：2026-09-07" in first_tooltip
        assert "開：99｜高：103｜低：98｜收：102" in first_tooltip
        assert "成交量：1,000" in first_tooltip

        _send_chart_mouse_move(chart, QPoint(middle_x, 80))
        app.processEvents()
        assert "資料日：2026-09-08" in chart.toolTip()
        assert "開：102｜高：104｜低：101｜收：103" in chart.toolTip()
        assert "成交量：1,500" in chart.toolTip()
        assert "圖表範圍：2026-09-07 至 2026-09-09" in chart.accessibleDescription()
        _send_chart_mouse_move(chart, QPoint(last_x, 80))
        app.processEvents()
        assert "資料日：2026-09-09" in chart.toolTip()
        assert "開：103｜高：105｜低：102｜收：104" in chart.toolTip()
        assert "成交量：2,000" in chart.toolTip()

        chart.set_points(
            (
                StockPricePointDTO(
                    data_date="2026-09-10",
                    close_price=Decimal("105"),
                ),
            )
        )
        _send_chart_mouse_move(chart, QPoint(plot_left, 80))
        app.processEvents()
        incomplete_tooltip = chart.toolTip()
        assert "資料日：2026-09-10" in incomplete_tooltip
        assert "開：—（未提供）｜高：—（未提供）｜低：—（未提供）｜收：105" in incomplete_tooltip
        assert "成交量：—（未提供）" in incomplete_tooltip
        assert "圖表範圍：2026-09-10 至 2026-09-10" in chart.accessibleDescription()

        chart.set_points(
            (
                StockPricePointDTO(
                    data_date="2026-09-11",
                    close_price=Decimal("106"),
                ),
                StockPricePointDTO(
                    data_date="2026-09-12",
                    open_price=Decimal("106"),
                    high_price=Decimal("108"),
                    low_price=Decimal("105"),
                    close_price=None,
                    volume=1800,
                ),
                StockPricePointDTO(
                    data_date="2026-09-15",
                    close_price=Decimal("107"),
                ),
            )
        )
        _send_chart_mouse_move(chart, QPoint(last_x, 80))
        app.processEvents()
        assert "資料日：2026-09-15" in chart.toolTip()
        assert "資料範圍：2026-09-11 至 2026-09-15" in chart.accessibleDescription()
        assert "圖上可繪製 2 點" in chart.accessibleDescription()

        chart.set_points(())
        _send_chart_mouse_move(chart, QPoint(middle_x, 80))
        app.processEvents()
        assert chart.toolTip() == "目前沒有可繪製的價格資料。"
    finally:
        chart.close()
        chart.deleteLater()
        app.processEvents()


@pytest.mark.parametrize("fundamental_available", [False, True], ids=["missing", "available"])
def test_report_summary_exposes_evidence_change_risk_sufficiency_and_next_step(
    fundamental_available: bool,
) -> None:
    _app()

    class Service:
        pass

    view = StockResearchReportView(Service())
    report = StockResearchReportDTO(
        stock_code="2330",
        stock_name="台積電",
        as_of="2026-09-08",
        attention_reasons=("已有保存研究理由",),
        key_risks=("保存研究理由仍需驗證",),
        sections=(
            StockReportSectionDTO(
                section_id="price",
                label="價格",
                status=ReportSectionStatus.AVAILABLE.value,
                data_as_of="2026-09-08",
            ),
            StockReportSectionDTO(
                section_id="fundamental",
                label="基本面",
                status=(ReportSectionStatus.AVAILABLE.value if fundamental_available
                        else ReportSectionStatus.MISSING.value),
                data_as_of="2026-09-08" if fundamental_available else "",
            ),
        ),
        price_points=(
            StockPricePointDTO(
                data_date="2026-09-08",
                close_price=Decimal("100"),
                change=Decimal("1"),
            ),
        ),
        technical=StockTechnicalSnapshotDTO(data_date="2026-09-08"),
    )

    view._render_report(report)

    # 關注理由不是當下規則證據；基本面足夠也不能升格為值得看。
    assert view.summary_focus.conclusion_label.text() == "結論：需核對資料：已有保存研究理由"
    assert "2026-09-08 收盤 100.00 TWD（漲跌 +1.00）" in view.summary_focus.evidence_label.text()
    assert "最新一日漲跌" in view.summary_focus.change_label.text()
    assert "主要風險／反證" in view.summary_focus.risk_label.text()
    if fundamental_available:
        assert "目前主要區塊都有可讀狀態" in view._summary_values["sufficiency"].text()
        assert "不足：基本面" not in view.summary_focus.sufficiency_label.text()
    else:
        assert "不足：基本面 缺資料或讀取失敗。" in view.summary_focus.sufficiency_label.text()
        assert "不足：基本面 缺資料或讀取失敗。" in view._summary_values["sufficiency"].text()
    assert "ML 狀態：" in view.summary_focus.sufficiency_label.text()
    assert "下一步：" in view.summary_focus.next_step_label.text()
    assert view.summary_source_group.isHidden()
    assert view.summary_detail_group.isHidden()
    view.close()


def test_watchlist_default_collapses_research_details_but_keeps_summary_and_entry() -> None:
    _app()
    service = MagicMock()
    service.get_stocks.return_value = [
        {"stock_code": "2330", "stock_name": "台積電", "source": "manual"}
    ]
    view = WatchlistView(service, config=None)
    view.show()
    _app().processEvents()

    assert "候選池目前 1 檔" in view.watchlist_focus_summary.conclusion_label.text()
    assert view.analysis_group.isHidden()
    view.toggle_advanced_research_btn.click()
    _app().processEvents()
    assert view.analysis_group.isVisible()
    assert view.toggle_advanced_research_btn.text() == "隱藏進階研究"
    view.close()


def test_watchlist_selected_research_cta_keeps_exact_context() -> None:
    _app()
    service = MagicMock()
    service.get_stocks.return_value = [
        {"stock_code": "2330", "stock_name": "台積電", "source": "manual"}
    ]
    view = WatchlistView(service, config=None)
    emitted: list[object] = []
    view.stockResearchRequested.connect(emitted.append)

    host = _mount_visual_qa_widget(view, _app())
    view.stocks_table.selectRow(0)
    _app().processEvents()

    assert view.stock_analysis_btn.isEnabled()
    assert not view.analysis_group.isVisible()
    assert not view.choose_source_btn.isHidden()
    first_row_bottom = max(
        view.stock_analysis_btn.geometry().bottom(),
        view.choose_source_btn.geometry().bottom(),
    )
    second_row_top = min(
        view.send_to_research_lab_btn.geometry().top(),
        view.save_to_universe_btn.geometry().top(),
        view.toggle_advanced_research_btn.geometry().top(),
    )
    assert first_row_bottom < second_row_top
    view.stock_analysis_btn.click()

    assert len(emitted) == 1
    assert emitted[0].stock_code == "2330"
    assert emitted[0].source_workspace == "watchlist"
    host.close()
    view.close()


def test_portfolio_summary_uses_plain_terms_and_marks_last_good_data(tmp_path: Path) -> None:
    _app()
    from tests.test_ui_qt_portfolio_view import make_portfolio_view

    view = make_portfolio_view(tmp_path)
    assert "目前持有 2 檔" in view.portfolio_focus_summary.conclusion_label.text()
    assert "目前持有" in view.portfolio_focus_summary.reasons_label.text()
    assert "模擬持倉" in view.portfolio_focus_summary.risk_label.text()
    assert "DTO" not in view.portfolio_focus_summary.evidence_label.text()
    assert "read model" not in view.portfolio_focus_summary.reasons_label.text()
    assert view.paper_health_group.isHidden()
    assert view.portfolio_detail_tabs.isHidden()
    view.toggle_advanced_portfolio_btn.click()
    _app().processEvents()
    assert not view.paper_health_group.isHidden()
    assert not view.portfolio_detail_tabs.isHidden()
    view.toggle_advanced_portfolio_btn.click()

    view._handle_portfolio_refresh_error("資料來源暫時不可用")
    assert "上次可用資料" in view.portfolio_focus_summary.conclusion_label.text()
    assert "資料來源暫時不可用" in view.portfolio_focus_summary.reasons_label.text()
    assert "最新資料不可用" in view.portfolio_focus_summary.sufficiency_label.text()

    view._set_portfolio_focus_state("loading")
    assert "上次可用資料" in view.portfolio_focus_summary.conclusion_label.text()
    view._set_portfolio_focus_state("cancelled")
    assert "更新已取消" in view.portfolio_focus_summary.conclusion_label.text()
    view.close()


def test_watchlist_summary_keeps_row_analysis_error_and_retry_entry() -> None:
    _app()
    service = MagicMock()
    service.get_stocks.return_value = []
    view = WatchlistView(service, config=None)
    row = {"證券代號": "2330", "證券名稱": "台積電", "source": "manual"}

    view._set_watchlist_focus_summary(
        row=row,
        status="讀取失敗",
        message="保存分析找不到對應資料",
    )

    assert "保存分析找不到對應資料" in view.watchlist_focus_summary.reasons_label.text()
    assert "再試一次" in view.watchlist_focus_summary.next_step_label.text()
    assert "進階研究" in view.watchlist_focus_summary.next_step_label.text()
    view.close()


def test_report_renders_deep_tabs_only_after_user_enters_them() -> None:
    _app()

    view = StockResearchReportView(object())
    report = StockResearchReportDTO(
        stock_code="2330",
        stock_name="台積電",
        as_of="2026-09-08",
        price_points=(
            StockPricePointDTO(
                data_date="2026-09-08",
                open_price=Decimal("99"),
                high_price=Decimal("103"),
                low_price=Decimal("98"),
                close_price=Decimal("102"),
                volume=1000,
            ),
        ),
    )

    view._render_report(report)
    assert "price" not in view._rendered_report_tabs
    view.tabs.setCurrentIndex(1)
    _app().processEvents()
    assert "price" in view._rendered_report_tabs
    assert view.findChild(StockPriceChartWidget) is not None
    view.close()


def test_v5_research_fixture_screenshots_if_paths_are_requested(tmp_path: Path) -> None:
    """Render candidate, report summary/price, and portfolio fixtures for visual QA."""

    requested = {
        key: os.environ.get(key, "").strip()
        for key in (
            "V5_WATCHLIST_SCREENSHOT_PATH",
            "V5_WATCHLIST_SELECTED_SCREENSHOT_PATH",
            "V5_REPORT_SUMMARY_SCREENSHOT_PATH",
            "V5_REPORT_PRICE_SCREENSHOT_PATH",
            "V5_PORTFOLIO_SCREENSHOT_PATH",
        )
    }
    if not any(requested.values()):
        return

    app = _app()
    _configure_visual_qa_theme(app)
    service = MagicMock()
    service.get_stocks.return_value = [
        {"stock_code": "2330", "stock_name": "台積電", "source": "manual"},
        {"stock_code": "2317", "stock_name": "鴻海", "source": "saved_recommendation"},
    ]
    watchlist = WatchlistView(service, config=None)
    watchlist_host = _mount_visual_qa_widget(watchlist, app)

    report = StockResearchReportView(object())
    fixture_report = StockResearchReportDTO(
        stock_code="2330",
        stock_name="台積電",
        as_of="2026-09-08",
        attention_reasons=("已有保存研究理由",),
        key_risks=("資料區塊仍有缺件",),
        sections=(
            StockReportSectionDTO(
                section_id="price",
                label="價格",
                status=ReportSectionStatus.AVAILABLE.value,
                data_as_of="2026-09-08",
            ),
            StockReportSectionDTO(
                section_id="fundamental",
                label="基本面",
                status=ReportSectionStatus.MISSING.value,
            ),
        ),
        price_points=(
            StockPricePointDTO(
                data_date="2026-09-07",
                open_price=Decimal("98"),
                high_price=Decimal("101"),
                low_price=Decimal("97"),
                close_price=Decimal("99"),
                volume=800,
            ),
            StockPricePointDTO(
                data_date="2026-09-08",
                open_price=Decimal("99"),
                high_price=Decimal("103"),
                low_price=Decimal("98"),
                close_price=Decimal("102"),
                volume=1200,
            ),
        ),
    )
    report._request_id = 1
    report._active_code = "2330"
    report._on_report_loaded(1, "2330", fixture_report)
    report_host = _mount_visual_qa_widget(report, app)

    from tests.test_ui_qt_portfolio_view import make_portfolio_view

    portfolio = make_portfolio_view(tmp_path)
    portfolio_host = _mount_visual_qa_widget(portfolio, app)

    for path_key, widget in (
        ("V5_WATCHLIST_SCREENSHOT_PATH", watchlist_host),
        ("V5_REPORT_SUMMARY_SCREENSHOT_PATH", report_host),
        ("V5_PORTFOLIO_SCREENSHOT_PATH", portfolio_host),
    ):
        path_text = requested[path_key]
        if path_text:
            path = Path(path_text)
            path.parent.mkdir(parents=True, exist_ok=True)
            assert widget.grab().save(str(path))

    selected_watchlist_path_text = requested["V5_WATCHLIST_SELECTED_SCREENSHOT_PATH"]
    if selected_watchlist_path_text:
        watchlist.stocks_table.selectRow(0)
        app.processEvents()
        selected_watchlist_path = Path(selected_watchlist_path_text)
        selected_watchlist_path.parent.mkdir(parents=True, exist_ok=True)
        assert watchlist_host.grab().save(str(selected_watchlist_path))

    price_path_text = requested["V5_REPORT_PRICE_SCREENSHOT_PATH"]
    if price_path_text:
        report.tabs.setCurrentIndex(1)
        app.processEvents()
        price_path = Path(price_path_text)
        price_path.parent.mkdir(parents=True, exist_ok=True)
        assert report_host.grab().save(str(price_path))

    watchlist_host.close()
    report_host.close()
    portfolio_host.close()
