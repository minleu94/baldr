from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QApplication, QComboBox, QDoubleSpinBox, QLabel, QTabWidget, QVBoxLayout, QWidget

from ui_qt.views.backtest_product_layout import BacktestProductLayout


class _LastRow:
    def __init__(self, values):
        self.values = values

    def __getitem__(self, key):
        return self.values[key]


class _ILoc:
    def __init__(self, row):
        self.row = row

    def __getitem__(self, index):
        assert index == -1
        return _LastRow(self.row)


class _Frame:
    def __init__(self, row, columns, index):
        self.columns = columns
        self.empty = False
        self.index = [index]
        self.iloc = _ILoc(row)

    def __len__(self):
        return 1


class _ResultPanel(QWidget):
    def __init__(self):
        super().__init__()
        self.layout_root = QVBoxLayout(self)
        self.layout_root.addWidget(QLabel("結果上下文"))
        self.result_tabs = QTabWidget(self)
        self._result_tab_widgets = {}
        self._result_tab_content_widgets = {}

        summary = QWidget()
        summary.setObjectName("summaryPage")
        self._add_outer("summary", summary, "摘要")

        charts = QWidget()
        charts_layout = QVBoxLayout(charts)
        self.chart_tabs = QTabWidget(charts)
        self.chart_pages = []
        for title in ("權益曲線", "回撤曲線"):
            page = QWidget(self.chart_tabs)
            self.chart_pages.append(page)
            self.chart_tabs.addTab(page, title)
        charts_layout.addWidget(self.chart_tabs)
        self._add_outer("charts", charts, "圖表")

        hidden = QWidget()
        self._add_outer("batch", hidden, "批次結果")
        self.layout_root.addWidget(self.result_tabs)

    def _add_outer(self, key, page, title):
        index = self.result_tabs.addTab(page, title)
        wrapper = QWidget(self.result_tabs)
        wrapper_layout = QVBoxLayout(wrapper)
        wrapper_layout.addWidget(page)
        self.result_tabs.removeTab(index)
        scroll_page = QWidget(self.result_tabs)
        scroll_layout = QVBoxLayout(scroll_page)
        scroll_layout.addWidget(wrapper)
        index = self.result_tabs.addTab(scroll_page, title)
        self._result_tab_widgets[key] = self.result_tabs.widget(index)
        self._result_tab_content_widgets[key] = page

    def result_tab_content_widget(self, key):
        return self._result_tab_content_widgets.get(key)

    def result_tab_key(self, index):
        for key, widget in self._result_tab_widgets.items():
            if self.result_tabs.indexOf(widget) == index:
                return key
        return None


class _Host(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        self.result_panel = _ResultPanel()
        layout.addWidget(self.result_panel)
        self.config_panel = QWidget(self)
        self.fee_bps_input = QDoubleSpinBox(self.config_panel)
        self.slippage_bps_input = QDoubleSpinBox(self.config_panel)
        self.execution_price_combo = QComboBox(self.config_panel)
        self.execution_price_combo.addItem("下一根K開盤價 (next_open)")
        self.config_panel.fee_bps_input = self.fee_bps_input
        self.config_panel.slippage_bps_input = self.slippage_bps_input
        self.config_panel.execution_price_combo = self.execution_price_combo
        self.current_report = None
        self.current_run_params = {}
        self.current_run_id = None
        self.worker = None
        self.research_lab_mode_combo = QComboBox(self)
        self.research_lab_mode_combo.addItem("單股", "single_stock")
        self.research_lab_mode_combo.addItem("策略研究", "strategy_research")


def _app():
    app = QApplication.instance()
    return app if app is not None else QApplication(sys.argv)


@pytest.fixture
def qt_driver():
    app = _app()

    class Driver:
        def __init__(self):
            self.widgets = []

        def addWidget(self, widget):
            self.widgets.append(widget)

    driver = Driver()
    yield driver
    for widget in reversed(driver.widgets):
        widget.close()
        widget.deleteLater()
    app.processEvents()


def _layout(qt_driver):
    _app()
    host = _Host()
    qt_driver.addWidget(host)
    adapter = BacktestProductLayout(host)
    assert adapter.install()
    return host, adapter


def test_install_flattens_nested_tabs_and_preserves_original_widgets(qt_driver):
    host, adapter = _layout(qt_driver)
    original_tabs = host.result_panel.result_tabs
    original_chart_tabs = host.result_panel.chart_tabs
    original_page = host.result_panel.chart_pages[0]

    assert adapter.result_tabs is original_tabs
    assert host.result_panel.chart_tabs is original_chart_tabs
    assert original_tabs.tabBar().isHidden()
    assert original_chart_tabs.tabBar().isHidden()
    assert adapter.navigator.findData("charts/權益曲線") >= 0
    assert adapter.select_result("charts/權益曲線")
    assert original_tabs.currentWidget() is host.result_panel._result_tab_widgets["charts"]
    assert original_chart_tabs.currentWidget() is original_page
    assert adapter.stack.currentWidget() is original_tabs


def test_external_page_change_syncs_selector_and_hidden_mode_cannot_be_selected(qt_driver):
    host, adapter = _layout(qt_driver)
    tabs = host.result_panel.result_tabs
    batch_index = tabs.indexOf(host.result_panel._result_tab_widgets["batch"])
    tabs.setCurrentIndex(batch_index)

    assert adapter.navigator.currentData() == "batch"
    tabs.setTabVisible(batch_index, False)
    adapter.refresh_routes()

    assert adapter.navigator.findData("batch") == -1
    assert not adapter.select_result("batch")


def test_assumption_banner_uses_report_and_matching_run_params_not_live_draft(qt_driver):
    host, adapter = _layout(qt_driver)
    report = SimpleNamespace(details={
        "start_date": "2025-01-02",
        "end_date": "2025-06-30",
        "execution_price": "next_open",
        "source_identity": "sha256:original-source",
        "source_qualification": "research_only",
    })
    host.current_report = report
    host.current_run_params = {
        "start_date": "2025-01-01",
        "end_date": "2025-07-01",
        "capital": "1000000",
        "fee_bps": "14.25",
        "slippage_bps": "5.00",
        "execution_price": "next_open",
    }
    adapter.refresh_assumptions(report)
    host.fee_bps_input.setValue(99)
    adapter._on_draft_changed()

    text = adapter.assumption_banner.text()
    assert "當次結果原始參數" in text
    assert "2025-01-02～2025-06-30" in text
    assert "14.25 bps" in text
    assert "5.00 bps" in text
    assert "99" not in text
    assert "sha256:original-source" in text
    assert "research_only" in text
    assert not adapter.draft_status.isHidden()


def test_result_parameter_snapshot_is_not_rebound_by_refresh_none(qt_driver):
    host, adapter = _layout(qt_driver)
    report = SimpleNamespace(details={"start_date": "2025-01-01", "end_date": "2025-02-01"})
    host.current_report = report
    host.current_run_params = {"capital": "100000", "fee_bps": "10"}

    adapter.refresh_assumptions(report)
    host.current_run_params = {"capital": "900000", "fee_bps": "99"}
    adapter.refresh_assumptions()

    assert "100000" in adapter.assumption_banner.text()
    assert "10 bps" in adapter.assumption_banner.text()
    assert "900000" not in adapter.assumption_banner.text()


def test_history_payload_uses_only_saved_details_values(qt_driver):
    host, adapter = _layout(qt_driver)
    host.current_run_params = {"capital": "999999", "fee_bps": "99", "slippage_bps": "99"}
    payload = {"details": {
        "start_date": "2024-01-01", "end_date": "2024-12-31", "capital": "250000",
        "fee_bps": "12.5", "slippage_bps": "3.25", "execution_contract": "next-session-open.v2",
        "data_manifest": {"source_identity": "sha256:saved"},
    }}

    adapter.refresh_assumptions(payload)

    text = adapter.assumption_banner.text()
    assert "已保存 run 原始資料" in text
    assert "250000" in text
    assert "12.5 bps" in text
    assert "3.25 bps" in text
    assert "next-session-open.v2" in text
    assert "999999" not in text
    assert "sha256:saved" in text


def test_noncurrent_report_keeps_details_without_borrowing_live_params(qt_driver):
    host, adapter = _layout(qt_driver)
    host.current_run_params = {"capital": "888888", "fee_bps": "77"}
    report = SimpleNamespace(details={"start_date": "2023-01-01", "initial_capital": "120000"})

    adapter.refresh_assumptions(report)
    host.current_run_params = {"capital": "999999", "fee_bps": "99"}
    adapter.refresh_assumptions()

    text = adapter.assumption_banner.text()
    assert "120000" in text
    assert "參數未提供" in text
    assert "999999" not in text
    assert "77 bps" not in text


def test_mode_change_clears_single_stock_projection_and_hidden_custom_routes(qt_driver):
    host, adapter = _layout(qt_driver)
    report = SimpleNamespace(details={
        "terminal_position": 123,
        "rule_signal_observations": [{"date": "2025-01-01", "signal": 1}],
    })
    host.current_report = report
    host.current_run_params = {"capital": "100000"}
    adapter.refresh_assumptions(report)
    assert adapter.open_positions_table.rowCount() > 0
    assert adapter.daily_signals_table.rowCount() == 1

    host.research_lab_mode_combo.setCurrentIndex(1)

    assert "策略研究" in adapter.assumption_banner.text()
    assert "資格未提供" in adapter.assumption_banner.text()
    assert adapter.open_positions_table.rowCount() == 0
    assert adapter.daily_signals_table.rowCount() == 0
    assert adapter.navigator.findData("open_positions") == -1
    assert adapter.navigator.findData("daily_signals") == -1
    assert adapter.stack.currentWidget() is adapter.result_tabs


def test_mapping_form_signal_observations_are_projected_without_inference(qt_driver):
    _host, adapter = _layout(qt_driver)
    report = SimpleNamespace(details={
        "rule_signal_observations": {
            "2025-01-02": {"signal": 1, "rule_id": "r1"},
            "2025-01-03": {"signal": 0, "rule_id": "r1"},
        },
    })

    adapter.refresh_assumptions(report)

    assert adapter.daily_signals_table.rowCount() == 2
    assert "2025-01-02" in [
        adapter.daily_signals_table.item(row, 1).text()
        for row in range(adapter.daily_signals_table.rowCount())
    ]


def test_open_positions_and_daily_signals_project_only_raw_report_observations(qt_driver):
    host, adapter = _layout(qt_driver)
    curve = _Frame(
        {"position": 1000, "position_value": "250000.00", "price": "250.00", "equity": "900000.00"},
        ["position", "position_value", "price", "equity"],
        "2025-06-30",
    )
    report = SimpleNamespace(details={
        "terminal_position": 1000,
        "equity_curve": curve,
        "rule_signal_observations": [{"date": "2025-06-30", "signal": 1, "ready": True}],
        "score_signal_observations": [{"date": "2025-06-30", "score": "72.5", "signal": 1}],
    })

    adapter.refresh_assumptions(report)

    assert adapter.open_positions_table.rowCount() >= 5
    assert adapter.open_positions_table.item(0, 1).text() == "1000"
    assert adapter.open_positions_table.item(1, 1).text() == "2025-06-30"
    assert adapter.open_positions_table.item(2, 1).text() == "1000"
    assert adapter.daily_signals_table.rowCount() == 2
    assert adapter.daily_signals_table.item(0, 0).text() == "規則逐日訊號原始觀測"
    assert adapter.daily_signals_table.item(1, 0).text() == "分數逐日訊號原始觀測"
    assert adapter.select_result("open_positions")
    assert adapter.select_result("daily_signals")


def test_missing_observation_data_is_explicitly_unavailable(qt_driver):
    _host, adapter = _layout(qt_driver)
    adapter.refresh_assumptions(SimpleNamespace(details={"trade_list": []}))

    assert "未提供" in adapter.open_positions_status.text()
    assert "未提供" in adapter.daily_signals_status.text()
    assert adapter.daily_signals_table.rowCount() == 0
