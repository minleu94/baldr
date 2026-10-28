import os
import sys
from decimal import Decimal
from datetime import date
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QItemSelectionModel, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QHeaderView
import pandas as pd

from decision_module.flow_contracts import (
    BranchFlowAggregation,
    BrokerFlowEvent,
    FlowSignalDTO,
    SmartMoneySummaryDTO,
    StockFlowAggregation,
)
from ui_qt.models.pandas_table_model import PandasTableModel
from ui_qt.views.smart_money.smart_money_flow_view import SmartMoneyFlowView
from ui_qt.views.smart_money.summary_strip import SummaryStrip
from ui_qt.views.smart_money.terminal_table_model import (
    BranchTrackerTableModel,
    TerminalTableModel,
)
from app_module.broker_flow_dashboard_dtos import BrokerFlowStockDetailSnapshot


def app():
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication(sys.argv)
    return instance


class FakeSmartMoneyService:
    def __init__(self, stock_details=None):
        self.stock_details = stock_details or []

    def get_stock_flow_signals(self, period="week"):
        return []

    def get_market_flow_summary(self, signals=None, period="week"):
        from decision_module.flow_contracts import SmartMoneySummaryDTO

        return SmartMoneySummaryDTO()

    def get_tracked_branches(self):
        return [
            {"display_name": "凱基-台北", "system_key": "kgi_taipei"},
            {"display_name": "富邦-仁愛", "system_key": "fubon_renai"},
        ]

    def get_branch_flow_details(self, period="week"):
        return []

    def get_stock_detail_by_branches(self, stock_code, period):
        return self.stock_details

    def load_stock_branch_detail(self, stock_code, period, as_of_date):
        return BrokerFlowStockDetailSnapshot(
            as_of_date=as_of_date,
            period=period,
            stock_code=stock_code,
            rows=tuple(self.stock_details),
            quality="observed",
        )


class FakeSemanticService:
    def build_stock_semantics(self, stock_code, decision_date):
        from app_module.dtos.smart_money_semantic_dtos import SmartMoneySemanticSummary, SmartMoneyWindowStats

        window = SmartMoneyWindowStats(
            window_days=5,
            net_qty=500,
            buy_qty=700,
            sell_qty=200,
            direction="buy",
            continuous_buy_days=2,
            continuous_sell_days=0,
            top_n=3,
            top_concentration_bp=7000,
            observed_count=3,
            estimated_count=0,
            unavailable_count=0,
            usable_coverage_bp=10000,
        )
        return SmartMoneySemanticSummary(
            stock_code=stock_code,
            stock_name=f"股票{stock_code}",
            decision_date=decision_date,
            primary_state="初轉買",
            semantic_flags=("分點集中異常",),
            confidence_bp=10000,
            quality="observed",
            warnings=(),
            evidence_lines=("5 日轉為買超",),
            window_5=window,
            window_20=window,
            window_60=window,
        )


def _signal(code: str, score: float, net_qty: int) -> FlowSignalDTO:
    aggregation = StockFlowAggregation(
        stock_code=code,
        stock_name=f"股票{code}",
        total_buy_qty=max(net_qty, 0),
        total_sell_qty=abs(min(net_qty, 0)),
        total_net_qty=net_qty,
        lots_coverage_ratio=Decimal("1"),
    )
    return FlowSignalDTO(
        stock_code=code,
        stock_name=f"股票{code}",
        aggregation=aggregation,
        smart_money_score=score,
        branch_concentration=0.5,
    )


def _branch_detail(name: str, buy_qty: int, sell_qty: int, net_qty: int) -> BranchFlowAggregation:
    return BranchFlowAggregation(
        branch_system_key=name,
        branch_display_name=name,
        stock_code="2330",
        stock_name="股票2330",
        total_buy_qty=buy_qty,
        total_sell_qty=sell_qty,
        total_net_qty=net_qty,
        usable_event_count=1,
    )


def test_smart_money_flow_defaults_to_top_and_bottom_50_scope():
    app()
    view = SmartMoneyFlowView(FakeSmartMoneyService())
    signals = [
        *[_signal(f"P{i:04d}", 100 - i, 1000 - i) for i in range(60)],
        *[_signal(f"N{i:04d}", i, -1000 - i) for i in range(60)],
    ]

    assert view.scope_combo.currentData() == "top_bottom_50"
    assert view.scanner_row_count_label.text() == "尚未載入"
    assert view.scanner_quality_label.text() == "品質：尚未載入"

    view._apply_scanner_signals(signals)
    filtered = view._filter_scanner_signals(signals)
    assert len(filtered) == 100
    assert view.scanner_row_count_label.text() == "顯示 100 檔"
    assert sum(1 for signal in filtered if signal.aggregation.total_net_qty > 0) == 50
    assert sum(1 for signal in filtered if signal.aggregation.total_net_qty < 0) == 50

    view.scope_combo.setCurrentIndex(view.scope_combo.findData("top50"))
    view._apply_scanner_signals(signals)
    assert view.scanner_row_count_label.text() == "顯示 50 檔"
    assert view.scanner_model.rowCount() == 50

    view.scope_combo.setCurrentIndex(view.scope_combo.findData("bottom50"))
    view._apply_scanner_signals(signals)
    assert view.scanner_row_count_label.text() == "顯示 50 檔"
    assert view.scanner_model.rowCount() == 50

    view.scope_combo.setCurrentIndex(view.scope_combo.findData("all"))
    view._apply_scanner_signals(signals)
    assert view.scanner_row_count_label.text() == "顯示 120 檔"
    assert view.scanner_model.rowCount() == 120

    view._apply_scanner_signals([])
    assert view.scanner_row_count_label.text() == "顯示 0 檔"
    assert view.scanner_quality_label.text() == "品質：估算 0／張數未知 0／未分類 0"
    assert view.scanner_model.rowCount() == 0


def test_smart_money_quality_coverage_follows_displayed_scope_only():
    app()
    view = SmartMoneyFlowView(FakeSmartMoneyService())
    positive = [_signal(f"P{i:04d}", 100 - i, 1000 - i) for i in range(60)]
    negative = [_signal(f"N{i:04d}", i, -1000 - i) for i in range(60)]
    signals = [*positive, *negative]
    for signal in signals:
        signal.observed_event_count = 1
    positive[0].estimated_event_count = 1
    positive[1].unavailable_event_count = 1
    positive[59].estimated_event_count = 1
    negative[59].estimated_event_count = 1
    negative[58].unavailable_event_count = 1
    negative[0].unavailable_event_count = 1

    summary = SmartMoneySummaryDTO(
        market_regime="Bullish Flow",
        bullish_stock_count=3,
        bearish_stock_count=1,
        abnormal_signal_count=2,
        market_heat_score=75.0,
    )
    view.summary_strip.update_summary(summary)
    summary_values = (
        view.summary_strip.lbl_regime["val_lbl"].text(),
        view.summary_strip.lbl_heat["val_lbl"].text(),
        view.summary_strip.lbl_bull_bear["val_lbl"].text(),
        view.summary_strip.lbl_abnormal["val_lbl"].text(),
    )
    view._dashboard_as_of_date = date(2026, 7, 3)

    view._apply_scanner_signals(signals)
    assert view.scanner_row_count_label.text() == "顯示 100 檔"
    assert view.scanner_quality_label.text() == "品質：估算 2／張數未知 2／未分類 0"

    view.scope_combo.setCurrentIndex(view.scope_combo.findData("top50"))
    view._apply_scanner_signals(signals)
    assert view.scanner_quality_label.text() == "品質：估算 1／張數未知 1／未分類 0"

    view.scope_combo.setCurrentIndex(view.scope_combo.findData("bottom50"))
    view._apply_scanner_signals(signals)
    assert view.scanner_quality_label.text() == "品質：估算 1／張數未知 1／未分類 0"

    view.scope_combo.setCurrentIndex(view.scope_combo.findData("all"))
    view._apply_scanner_signals(signals)
    assert view.scanner_quality_label.text() == "品質：估算 3／張數未知 3／未分類 0"
    assert summary_values == (
        view.summary_strip.lbl_regime["val_lbl"].text(),
        view.summary_strip.lbl_heat["val_lbl"].text(),
        view.summary_strip.lbl_bull_bear["val_lbl"].text(),
        view.summary_strip.lbl_abnormal["val_lbl"].text(),
    )
    assert view._dashboard_as_of_date == date(2026, 7, 3)


def test_smart_money_quality_coverage_labels_unclassified_rows():
    app()
    view = SmartMoneyFlowView(FakeSmartMoneyService())
    negative_count = _signal("2331", 87, 400)
    negative_count.observed_event_count = -1
    invalid_count = _signal("2332", 86, 300)
    invalid_count.estimated_event_count = "invalid"

    view._apply_scanner_signals(
        [_signal("2330", 88, 500), negative_count, invalid_count]
    )

    assert view.scanner_row_count_label.text() == "顯示 3 檔"
    assert view.scanner_quality_label.text() == "品質：估算 0／張數未知 0／未分類 3"
    assert "不代表市場完整母體" in view.scanner_quality_label.toolTip()


def test_smart_money_dashboard_refresh_updates_visible_row_count():
    app()
    view = SmartMoneyFlowView(FakeSmartMoneyService())
    view._apply_scanner_signals([_signal("OLD", 10, 100)])
    assert view.scanner_row_count_label.text() == "顯示 1 檔"

    view._apply_dashboard_snapshot(SimpleNamespace(
        as_of_date=date(2026, 7, 3),
        top_signals=(
            _signal("2330", 88, 500),
            _signal("2317", 84, 320),
        ),
        bottom_signals=(),
        summary=SmartMoneySummaryDTO(),
        semantics_by_code={},
        tracked_branches=(),
        quality="observed",
    ))

    assert view.scanner_row_count_label.text() == "顯示 2 檔"
    assert view.scanner_model.rowCount() == 2
    assert view.scanner_model.get_signal_at(0).stock_code == "2330"


def test_smart_money_flow_detail_double_click_switches_to_branch_tracker():
    app()
    view = SmartMoneyFlowView(FakeSmartMoneyService())
    branches = view.flow_service.get_tracked_branches()
    for branch in branches:
        view.branch_combo.addItem(branch["display_name"], branch["system_key"])

    view.detail_table.setModel(PandasTableModel(pd.DataFrame([{
        "分點名稱": "富邦-仁愛",
        "買進張數": "100",
        "賣出張數": "20",
        "淨買賣超": "+80",
    }])))

    index = view.detail_table.model().index(0, 0)
    view._drill_down_branch_from_detail(index)

    assert view.tab_widget.currentIndex() == 1
    assert view.branch_combo.currentText() == "富邦-仁愛"


def test_smart_money_table_model_renders_semantic_state_and_diagnostics():
    qt_app = app()
    signal = _signal("2330", 88, 500)
    view = SmartMoneyFlowView(
        FakeSmartMoneyService(),
        smart_money_semantic_service=FakeSemanticService(),
    )
    view.resize(1600, 800)
    view.show()

    semantic = FakeSemanticService().build_stock_semantics("2330", date.today())
    view._apply_scanner_signals([signal], semantics_by_code={"2330": semantic})
    qt_app.processEvents()

    model = view.scanner_table.model()
    headers = [model.headerData(i, Qt.Horizontal) for i in range(model.columnCount())]
    assert "語意狀態" in headers
    assert "5/20/60 日診斷" in headers
    semantic_col = headers.index("語意狀態")
    concentration_col = headers.index("集中度")
    score_col = headers.index("分數")
    diagnostic_col = headers.index("5/20/60 日診斷")
    assert "初轉買" in model.data(model.index(0, semantic_col), Qt.DisplayRole)
    assert "5D" in model.data(model.index(0, diagnostic_col), Qt.DisplayRole)
    assert model.headerData(score_col, Qt.Horizontal, Qt.ToolTipRole) == (
        "買方主力規則分數，範圍 0–100；賣方列不計買方分數，通常為 0。不是勝率或機率。"
    )
    assert "不是全市場或股權持有集中度" in model.headerData(
        concentration_col, Qt.Horizontal, Qt.ToolTipRole
    )
    assert "不是勝率或機率" in model.headerData(
        score_col, Qt.Horizontal, Qt.AccessibleTextRole
    )
    assert "僅計目前載入期間與資料" in model.data(
        model.index(0, concentration_col), Qt.AccessibleTextRole
    )
    assert view.scanner_table.columnWidth(concentration_col) <= 70
    assert view.scanner_table.columnWidth(semantic_col) <= 86
    header = view.scanner_table.horizontalHeader()
    trend_col = headers.index("近期趨勢 (Trend)")
    badges_col = headers.index("信號 (Badges)")
    assert header.sectionResizeMode(diagnostic_col) == QHeaderView.ResizeMode.Interactive
    assert header.sectionResizeMode(trend_col) == QHeaderView.ResizeMode.Interactive
    assert view.scanner_table.columnWidth(trend_col) == 190
    assert view.scanner_table.columnWidth(diagnostic_col) <= 420
    assert view.scanner_table.columnWidth(badges_col) <= 280
    total_column_width = sum(
        view.scanner_table.columnWidth(col)
        for col in range(model.columnCount())
    )
    assert total_column_width <= view.scanner_table.maximumWidth()
    assert view.scanner_table.horizontalScrollBar().maximum() == 0


def test_smart_money_scanner_width_measurements_are_reused_until_model_or_font_changes():
    qt_app = app()
    view = SmartMoneyFlowView(FakeSmartMoneyService())
    view.resize(1600, 800)
    view.show()
    counts = {"text": 0, "badges": 0}
    original_text_measure = view._fit_text_column_width
    original_badges_measure = view._fit_badges_column_width

    def count_text_measure(*args, **kwargs):
        counts["text"] += 1
        return original_text_measure(*args, **kwargs)

    def count_badges_measure(*args, **kwargs):
        counts["badges"] += 1
        return original_badges_measure(*args, **kwargs)

    view._fit_text_column_width = count_text_measure
    view._fit_badges_column_width = count_badges_measure
    signals = [
        _signal("2330", 88, 500),
        _signal("2317", 82, -300),
    ]

    view._apply_scanner_signals(signals)
    qt_app.processEvents()
    assert counts == {"text": 3, "badges": 1}

    for width in (1400, 1200, 1600, 1000):
        view.resize(width, 800)
        qt_app.processEvents()
        view._fit_scanner_diagnostic_column()
    assert counts == {"text": 3, "badges": 1}

    current_model = view.scanner_table.model()
    current_model.sort(0, Qt.DescendingOrder)
    view._fit_scanner_diagnostic_column()
    assert counts == {"text": 3, "badges": 1}

    view._apply_scanner_signals(signals)
    qt_app.processEvents()
    assert counts == {"text": 6, "badges": 2}

    updated_font = QFont(view.scanner_table.font())
    updated_font.setPointSizeF(updated_font.pointSizeF() + 1.0)
    view.scanner_table.setFont(updated_font)
    qt_app.processEvents()
    view._fit_scanner_diagnostic_column()
    assert counts == {"text": 9, "badges": 3}


def test_smart_money_search_filters_current_scope_and_preserves_market_summary():
    app()
    view = SmartMoneyFlowView(FakeSmartMoneyService())
    signals = [
        _signal("2330", 92, 1200),
        _signal("2317", 84, 800),
        _signal("2618", 76, -500),
    ]
    signals[0].stock_name = "台積電"
    signals[1].stock_name = "鴻海"
    signals[2].stock_name = "長榮航"
    for signal in signals:
        signal.observed_event_count = 1
    signals[0].estimated_event_count = 1
    signals[2].unavailable_event_count = 1

    summary = SmartMoneySummaryDTO(
        market_regime="Bullish Flow",
        bullish_stock_count=2,
        bearish_stock_count=1,
        abnormal_signal_count=1,
        market_heat_score=60.0,
    )
    view.summary_strip.update_summary(summary)
    summary_values = (
        view.summary_strip.lbl_regime["val_lbl"].text(),
        view.summary_strip.lbl_heat["val_lbl"].text(),
        view.summary_strip.lbl_bull_bear["val_lbl"].text(),
        view.summary_strip.lbl_abnormal["val_lbl"].text(),
    )
    view._all_scanner_signals = signals
    view._dashboard_as_of_date = date(2026, 7, 3)
    view._dashboard_period = "week"
    view._dashboard_scope = "top_bottom_50"
    snapshot = SimpleNamespace(as_of_date=date(2026, 7, 3))
    view._dashboard_snapshot = snapshot
    view._apply_scanner_signals(signals)
    request_ids = dict(view._request_ids)

    assert view.scanner_model.rowCount() == 3
    assert view.scanner_search_input.accessibleName() == "搜尋目前主表"
    assert "不擴大市場範圍" in view.scanner_search_input.accessibleDescription()

    view.scanner_search_input.setText("台積")
    assert view.scanner_model.rowCount() == 1
    assert view.scanner_model.get_signal_at(0).stock_code == "2330"
    assert view.scanner_row_count_label.text() == "符合 1／範圍 3 檔"
    assert view.scanner_quality_label.text() == "品質：估算 1／張數未知 0／未分類 0"

    view.scanner_search_input.setText("2317")
    assert view.scanner_model.rowCount() == 1
    assert view.scanner_model.get_signal_at(0).stock_code == "2317"

    view.scanner_search_input.setText("沒有這檔")
    assert view.scanner_model.rowCount() == 0
    assert view.scanner_row_count_label.text() == "此範圍無符合標的（0／3）"
    assert view.scanner_quality_label.text() == "品質：估算 0／張數未知 0／未分類 0"

    view.scanner_search_input.clear()
    assert view.scanner_model.rowCount() == 3
    assert view.scanner_row_count_label.text() == "顯示 3 檔"
    assert view._request_ids == request_ids
    assert view._all_scanner_signals == signals
    assert view._dashboard_snapshot is snapshot
    assert view._dashboard_as_of_date == date(2026, 7, 3)
    assert summary_values == (
        view.summary_strip.lbl_regime["val_lbl"].text(),
        view.summary_strip.lbl_heat["val_lbl"].text(),
        view.summary_strip.lbl_bull_bear["val_lbl"].text(),
        view.summary_strip.lbl_abnormal["val_lbl"].text(),
    )


def test_smart_money_search_empty_states_and_hidden_selection_are_distinct():
    app()
    view = SmartMoneyFlowView(FakeSmartMoneyService())
    assert view.scanner_row_count_label.text() == "尚未載入"
    view.scanner_search_input.setText("2330")
    assert view.scanner_row_count_label.text() == "尚未載入"

    view._apply_scanner_signals([])
    assert view.scanner_row_count_label.text() == "顯示 0 檔"
    view.scanner_search_input.clear()

    signal = _signal("2330", 90, 800)
    signal.stock_name = "台積電"
    view._apply_scanner_signals([signal])
    model = view.scanner_table.model()
    row = next(
        index
        for index in range(model.rowCount())
        if model.get_signal_at(index).stock_code == "2330"
    )
    view.scanner_table.selectionModel().select(
        model.index(row, 0),
        QItemSelectionModel.SelectionFlag.ClearAndSelect
        | QItemSelectionModel.SelectionFlag.Rows,
    )
    view._requested_stock_code = "2330"
    view.detail_status_label.setText("2330｜載入中")
    view.detail_table.setModel(PandasTableModel(pd.DataFrame([{"分點名稱": "測試"}])))

    view.scanner_search_input.setText("沒有這檔")

    assert view.scanner_model.rowCount() == 0
    assert view.scanner_row_count_label.text() == "此範圍無符合標的（0／1）"
    assert not view.scanner_table.selectionModel().selectedRows()
    assert view._requested_stock_code is None
    assert view.detail_table.model().rowCount() == 0
    assert "搜尋已隱藏 台積電（2330）" in view.detail_status_label.text()


def test_smart_money_quality_tooltip_keeps_unknown_counts_and_quality_caveats():
    signal = _signal("2330", 88, 500)
    branch = _branch_detail("元大證券", 100, 20, 80)
    scanner_model = TerminalTableModel([signal])
    branch_model = BranchTrackerTableModel([branch])

    scanner_tooltip = scanner_model.data(scanner_model.index(0, 0), Qt.ToolTipRole)
    branch_tooltip = branch_model.data(branch_model.index(0, 0), Qt.ToolTipRole)

    for tooltip in (scanner_tooltip, branch_tooltip):
        assert "資料品質：未知（未提供事件分類計數）" in tooltip
        assert "真實 100%" not in tooltip
        assert "不代表無交易，更非 0 交易" in tooltip

    signal.observed_event_count = 2
    signal.estimated_event_count = 1
    signal.unavailable_event_count = 1
    branch.observed_event_count = 2
    branch.estimated_event_count = 1
    branch.unavailable_event_count = 1

    scanner_tooltip = scanner_model.data(scanner_model.index(0, 0), Qt.ToolTipRole)
    branch_tooltip = branch_model.data(branch_model.index(0, 0), Qt.ToolTipRole)

    for tooltip in (scanner_tooltip, branch_tooltip):
        assert "資料品質：真實 50%｜估算 25%｜不可用 25%" in tooltip
        assert "不代表無交易，更非 0 交易" in tooltip


def test_smart_money_summary_distinguishes_unknown_from_neutral():
    strip = SummaryStrip()

    strip.update_summary(SmartMoneySummaryDTO())

    assert strip.lbl_regime["title_lbl"].text() == "主力訊號方向"
    assert strip.lbl_heat["title_lbl"].text() == "偏多訊號占比"
    assert strip.lbl_bull_bear["title_lbl"].text() == "多空訊號家數"
    assert strip.lbl_abnormal["title_lbl"].text() == "異常訊號數"
    assert strip.lbl_regime["val_lbl"].text() == "未知 (Unknown)"
    assert strip.lbl_heat["val_lbl"].text() == "—"
    assert "沒有可分類的多空主力訊號" in strip.lbl_heat["val_lbl"].toolTip()
    assert "風險提示" in strip.lbl_abnormal["val_lbl"].toolTip()

    strip.update_summary(
        SmartMoneySummaryDTO(
            market_regime="Neutral",
            bullish_stock_count=2,
            bearish_stock_count=2,
            market_heat_score=50.0,
        )
    )

    assert strip.lbl_regime["val_lbl"].text() == "中性整理 (Neutral)"
    assert strip.lbl_heat["val_lbl"].text() == "50.0%"
    assert "2 ÷ (2 + 2)" in strip.lbl_heat["val_lbl"].toolTip()
    assert "不是全市場漲跌家數" in strip.lbl_heat["val_lbl"].toolTip()


def test_smart_money_detail_table_fits_columns_without_horizontal_scroll():
    qt_app = app()
    service = FakeSmartMoneyService(stock_details=[
        _branch_detail("元大證券", 54622, 9742, 44880),
        _branch_detail("永豐金-板新", 10000, 37, 9963),
        _branch_detail("凱基", 681, 401, 280),
    ])
    view = SmartMoneyFlowView(
        service,
        smart_money_semantic_service=FakeSemanticService(),
    )
    view._dashboard_as_of_date = date(2026, 7, 3)
    view.resize(1440, 800)
    view.show()

    view._apply_scanner_signals([_signal("2330", 88, 500)])
    view.scanner_table.selectRow(0)
    view._workers["detail"].wait()
    qt_app.processEvents()

    model = view.detail_table.model()
    headers = [model.headerData(i, Qt.Horizontal) for i in range(model.columnCount())]
    net_col = headers.index("淨買賣超")
    sell_col = headers.index("賣出張數")
    total_column_width = sum(
        view.detail_table.columnWidth(col)
        for col in range(model.columnCount())
    )
    viewport_width = view.detail_table.viewport().width()

    assert total_column_width <= viewport_width
    assert viewport_width - total_column_width <= 24
    assert view.detail_table.columnWidth(net_col) >= 128
    assert view.detail_table.columnWidth(sell_col) < view.detail_table.columnWidth(net_col)
    assert view.detail_table.horizontalScrollBar().maximum() == 0
