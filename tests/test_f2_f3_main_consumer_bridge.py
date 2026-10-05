"""F2/F3 主視窗共享來源與能力核對入口的隔離接線驗證。"""
from types import SimpleNamespace
import json
import sqlite3
import time

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QApplication, QMainWindow, QTabWidget, QWidget
from PySide6.QtTest import QTest
from tests.test_daily_market_research_screener import _seed_database, _service, _produce
from ui_qt.main import MainWindow
from ui_qt.views.daily_market_research_view import DailyMarketResearchView
from ui_qt.views.market_regime_view import MarketRegimeView
from ui_qt.views.strong_stocks_view import StrongStocksView
from ui_qt.views.weak_stocks_view import WeakStocksView


class _Window(MainWindow):
    def __init__(self):
        QMainWindow.__init__(self)
        self.messages = []

    def _record_shutdown_message(self, value):
        self.messages.append(value)

    def _select_main_workspace(self, value):
        self.selected_workspace = value


class _Consumer(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.bound = None
        self.stopped = False

    def set_shared_research_source(self, source):
        self.bound = source

    def begin_shutdown(self):
        self.stopped = True


def _drain(app, daily):
    deadline = time.monotonic() + 8
    while daily._worker is not None and time.monotonic() < deadline:
        app.processEvents()
        QTest.qWait(5)
    assert daily._worker is None


def test_main_shared_source_binding_capability_audit_and_shutdown(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    database, _, decision_date = _seed_database(tmp_path)
    service = _service(database, tmp_path / "published")
    _produce(monkeypatch, service, decision_date)
    snapshot = service.read_snapshot("controlled-daily-market", decision_date)
    daily = DailyMarketResearchView(service)
    window = _Window()
    result_tabs = QTabWidget()
    result_tabs.addTab(daily, "研究名單")
    recommendation = SimpleNamespace(daily_market_research_view=daily, result_source_tabs=result_tabs)
    market_tabs = QTabWidget(window)
    consumers = [_Consumer(window) for _ in range(3)]
    for index, consumer in enumerate(consumers):
        market_tabs.addTab(consumer, str(index))
    window._connect_daily_market_cohort_view(recommendation, market_tabs)
    assert window.shared_market_consumers == tuple(consumers)
    assert all(consumer.bound is daily for consumer in consumers)
    market = window.daily_market_cohort_view
    daily._accept_snapshot(snapshot, sync_cutoff=True)
    _drain(app, daily)
    assert market.capability_button.isEnabled(), market.status_label.text()
    market.capability_button.click()
    assert market._capability_dialog is not None
    assert market._capability_table.rowCount() == 5
    audit = json.loads(market._capability_text.toPlainText())
    assert snapshot.manifest_sha256 in json.dumps(audit)
    assert market.projection.source_snapshot_hash == snapshot.manifest_sha256
    daily.snapshotCleared.emit()
    assert not market.capability_button.isEnabled()
    assert "不能沿舊母體判定完整" in market.scope_label.text()
    assert "來源已失效" in market._capability_text.toPlainText()
    window._freeze_child_refresh_sources()
    assert all(consumer.stopped for consumer in consumers)
    assert not window.messages
    daily.begin_shutdown()
    _drain(app, daily)
    window.close()
    result_tabs.close()
    app.processEvents()


def test_actual_three_consumers_share_main_source_and_clear_together(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    database, price_date, decision_date = _seed_database(tmp_path)
    service = _service(database, tmp_path / "published")
    _produce(monkeypatch, service, decision_date)
    snapshot = service.read_snapshot("controlled-daily-market", decision_date)
    daily = DailyMarketResearchView(service)
    window = _Window()
    tabs = QTabWidget(window)
    consumers = [MarketRegimeView(SimpleNamespace()), StrongStocksView(SimpleNamespace()), WeakStocksView(SimpleNamespace())]
    for view in consumers:
        tabs.addTab(view, type(view).__name__)
    result_tabs = QTabWidget()
    result_tabs.addTab(daily, "research")
    window._connect_daily_market_cohort_view(
        SimpleNamespace(daily_market_research_view=daily, result_source_tabs=result_tabs), tabs
    )
    assert window.shared_market_consumers == tuple(consumers)
    for view in consumers[1:]:
        view.shared_research_mode_selector.setCurrentIndex(1)
    daily._accept_snapshot(snapshot, sync_cutoff=True)
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        app.processEvents()
        if daily._worker is None and all(view.shared_research_consumer._worker is None for view in consumers):
            break
        QTest.qWait(5)
    assert daily._worker is None
    assert all(view.shared_research_consumer._worker is None for view in consumers)
    assert all(view.shared_research_consumer.snapshot is snapshot for view in consumers)
    for view in consumers[1:]:
        frame = view.stocks_model.getDataFrame()
        assert tuple(frame["證券代號"]) == tuple(snapshot.manifest["declared_stock_codes"])
        assert set(frame["原始名次"]) == {"未知"}
        assert snapshot.manifest_sha256 in view.source_scope_label.text()
    assert snapshot.manifest_sha256 in consumers[0].shared_research_summary_label.text()
    # 當原 SQLite 的內容修訂後，返回三頁須拒絕舊 pin，不切換其他來源。
    with sqlite3.connect(database) as connection:
        changed = connection.execute(
            'UPDATE daily_prices SET "收盤價" = ? WHERE "證券代號" = ? AND "日期" = ?',
            ("999999", snapshot.manifest["declared_stock_codes"][0], price_date.isoformat()),
        )
        assert changed.rowcount == 1
    for view in consumers:
        view.load_data_if_needed()
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        app.processEvents()
        if all(view.shared_research_consumer._worker is None for view in consumers):
            break
        QTest.qWait(5)
    assert all(view.shared_research_consumer._worker is None for view in consumers)
    assert all(view.stocks_model.rowCount() == 0 for view in consumers[1:])
    assert all("不可用" in view.source_scope_label.text() for view in consumers[1:])
    assert "無法核驗" in consumers[0].shared_research_summary_label.text()
    daily.snapshotCleared.emit()
    assert all(view.shared_research_consumer.snapshot is None for view in consumers)
    assert all(view.stocks_model.rowCount() == 0 for view in consumers[1:])
    assert "不可用" in consumers[0].shared_research_summary_label.text()
    window._freeze_child_refresh_sources()
    daily.begin_shutdown()
    _drain(app, daily)
    assert all(view.shared_research_consumer.begin_shutdown() for view in consumers)
    window.close()
    result_tabs.close()
    app.processEvents()
