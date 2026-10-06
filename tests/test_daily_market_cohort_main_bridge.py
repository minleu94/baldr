"""盤勢入口與名單共享 verified 快照，不另走來源或日期。"""

from types import SimpleNamespace

import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication, QMainWindow, QTabWidget

from tests.test_daily_market_research_screener import _seed_database, _service, _produce
from ui_qt.main import MainWindow
from ui_qt.views.daily_market_research_view import DailyMarketResearchView


class RouteHarness(MainWindow):
    def __init__(self):
        QMainWindow.__init__(self)
        self.selected_workspace = ""

    def _select_main_workspace(self, workspace):
        self.selected_workspace = workspace


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
    window.close()
    result_tabs.close()
    app.processEvents()
