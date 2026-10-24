"""盤勢入口與名單共享 verified 快照，不另走來源或日期。"""

import time
from dataclasses import replace
from types import SimpleNamespace

import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication, QMainWindow, QTabWidget

from tests.test_daily_market_research_screener import _seed_database, _service, _produce
from ui_qt.main import MainWindow
from ui_qt.views.daily_market_research_view import DailyMarketResearchView
from ui_qt.workers.task_worker import running_task_workers


class RouteHarness(MainWindow):
    def __init__(self):
        QMainWindow.__init__(self)
        self.selected_workspace = ""
        self.opened_context = None

    def _select_main_workspace(self, workspace):
        self.selected_workspace = workspace

    def _open_stock_research_context(self, context):
        self.opened_context = context
        self._daily_market_cohort_origin = context


def _close_route_harness(app, daily, window, result_tabs):
    """讓本測試啟動的讀取自然完成，關閉前核對 TaskWorker 終態。"""

    daily.begin_shutdown()
    deadline = time.monotonic() + 10
    while running_task_workers() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert not running_task_workers()
    window.close()
    result_tabs.close()
    app.processEvents()


def test_market_list_bridge_uses_exact_snapshot_and_clear_on_rejection(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    database, _, decision_date = _seed_database(tmp_path)
    service = _service(database, tmp_path / "published")
    _produce(monkeypatch, service, decision_date)
    snapshot = service.read_snapshot("controlled-daily-market", decision_date)
    daily = DailyMarketResearchView(service)
    window = RouteHarness()
    result_tabs = QTabWidget()
    result_tabs.addTab(daily, "研究名單")
    recommendation = SimpleNamespace(
        daily_market_research_view=daily, result_source_tabs=result_tabs,
    )
    market_tabs = QTabWidget(window)
    window.market_tabs = market_tabs
    window._connect_daily_market_cohort_view(recommendation, market_tabs)
    market = window.daily_market_cohort_view
    daily._accept_snapshot(snapshot, sync_cutoff=True)
    assert market.projection.source_snapshot_hash == daily._manifest_sha256
    assert market.projection.source_snapshot_id == daily._manifest_identity_sha256
    assert market.projection.decision_date == daily._loaded_decision_date
    assert market.projection.declared_stock_codes == tuple(sorted(daily.research_snapshot_stock_codes()))
    assert all(count.denominator == 2 for count in market.projection.method_counts)
    daily.filter_state_combo.setCurrentIndex(daily.filter_state_combo.findData("match"))
    assert all(count.denominator == 2 for count in market.projection.method_counts)
    market.open_list_button.click()
    assert window.selected_workspace == "recommendation"
    assert result_tabs.currentWidget() is daily
    daily._on_operation_error(daily._operation_generation, "snapshot_manifest_legacy_v1")
    assert market.projection is None
    assert market.methods_table.rowCount() == 0
    assert daily.results_table.rowCount() == 0
    daily._accept_snapshot(snapshot, sync_cutoff=True)
    assert market.projection.source_snapshot_hash == snapshot.manifest_sha256
    _close_route_harness(app, daily, window, result_tabs)


def test_market_cohort_member_opens_and_returns_to_same_source_row(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    database, _, decision_date = _seed_database(tmp_path)
    service = _service(database, tmp_path / "published")
    _produce(monkeypatch, service, decision_date)
    snapshot = service.read_snapshot("controlled-daily-market", decision_date)
    daily = DailyMarketResearchView(service)
    window = RouteHarness()
    result_tabs = QTabWidget()
    result_tabs.addTab(daily, "研究名單")
    recommendation = SimpleNamespace(
        daily_market_research_view=daily, result_source_tabs=result_tabs,
    )
    market_tabs = QTabWidget(window)
    window.market_tabs = market_tabs
    window._connect_daily_market_cohort_view(recommendation, market_tabs)
    market = window.daily_market_cohort_view
    daily._accept_snapshot(snapshot, sync_cutoff=True)

    market.members_table.selectRow(0)
    assert market.research_selected_button.isEnabled()
    stock_code = market.members_table.item(0, 0).text()
    market.research_selected_button.click()

    context = window.opened_context
    assert context is not None
    assert context.stock_code == stock_code
    assert context.source_workspace == "market_explore"
    assert context.source_kind == "daily_market_research_snapshot"
    assert context.source_snapshot_id == snapshot.manifest_identity_sha256
    assert context.source_snapshot_hash == snapshot.manifest_sha256
    assert context.decision_date == snapshot.decision_date.isoformat()
    assert context.daily_snapshot_root == str(service.snapshot_root)
    assert context.daily_snapshot_cohort_id == snapshot.cohort_id
    assert context.daily_snapshot_condition_keys == "close_above_ma20,close_above_ma60"
    assert context.daily_snapshot_combine_mode == "AND"

    window.selected_workspace = "stock_research"
    # 實際個股報告會在重新核 pinned artifact 前暫清資料日。
    window._return_to_research_source(replace(context, data_date=""))
    assert window.selected_workspace == "market_explore"
    assert market_tabs.currentWidget() is market
    assert market.members_table.currentRow() == 0

    _close_route_harness(app, daily, window, result_tabs)


def test_market_cohort_return_rejects_changed_snapshot_without_navigation(
    tmp_path, monkeypatch,
):
    app = QApplication.instance() or QApplication([])
    database, _, decision_date = _seed_database(tmp_path)
    service = _service(database, tmp_path / "published")
    _produce(monkeypatch, service, decision_date)
    snapshot = service.read_snapshot("controlled-daily-market", decision_date)
    daily = DailyMarketResearchView(service)
    window = RouteHarness()
    result_tabs = QTabWidget()
    result_tabs.addTab(daily, "研究名單")
    recommendation = SimpleNamespace(
        daily_market_research_view=daily, result_source_tabs=result_tabs,
    )
    market_tabs = QTabWidget(window)
    window.market_tabs = market_tabs
    window._connect_daily_market_cohort_view(recommendation, market_tabs)
    market = window.daily_market_cohort_view
    daily._accept_snapshot(snapshot, sync_cutoff=True)
    market.members_table.selectRow(0)
    market.research_selected_button.click()
    context = window.opened_context
    assert context is not None

    daily._on_operation_error(daily._operation_generation, "snapshot_manifest_legacy_v1")
    assert market.projection is None
    assert not market.research_selected_button.isEnabled()
    window.selected_workspace = "watchlist"
    window._return_to_research_source(context)
    assert window.selected_workspace == "watchlist"
    assert market_tabs.currentWidget() is market
    assert "未切換" in window.statusBar().currentMessage()

    _close_route_harness(app, daily, window, result_tabs)
