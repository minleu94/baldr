import os
import sys
from datetime import date
from decimal import Decimal

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app_module.broker_flow_dashboard_dtos import (
    BrokerFlowBranchTrackerSnapshot,
    BrokerFlowDashboardSnapshot,
    BrokerFlowStockDetailSnapshot,
)
from decision_module.flow_contracts import (
    BranchFlowAggregation,
    FlowSignalDTO,
    SmartMoneySummaryDTO,
    StockFlowAggregation,
)
import ui_qt.views.smart_money.smart_money_flow_view as smart_money_view_module
from ui_qt.views.smart_money.smart_money_flow_view import SmartMoneyFlowView


class _Signal:
    def __init__(self):
        self.callbacks = []

    def connect(self, callback):
        self.callbacks.append(callback)

    def emit(self, *args):
        for callback in self.callbacks:
            callback(*args)


class ManualWorker:
    def __init__(self, task):
        self.task = task
        self.finished = _Signal()
        self.error = _Signal()
        self.cancelled = _Signal()
        self.cancel_calls = []
        self.started = False

    def start(self):
        self.started = True

    def cancel(self, *, cooperative, wait):
        self.cancel_calls.append((cooperative, wait))


class WorkerFactory:
    def __init__(self):
        self.workers = []

    def __call__(self, task):
        worker = ManualWorker(task)
        self.workers.append(worker)
        return worker


class AsyncService:
    def load_dashboard_snapshot(self, query):
        raise AssertionError("manual worker should not run in GUI thread")

    def load_stock_branch_detail(
        self, stock_code, period, as_of_date, *, dashboard_snapshot=None
    ):
        raise AssertionError("manual worker should not run in GUI thread")

    def load_branch_tracker(self, branch_system_key, period, as_of_date):
        raise AssertionError("manual worker should not run in GUI thread")


class CapturingDashboardService(AsyncService):
    def __init__(self):
        self.queries = []

    def load_dashboard_snapshot(self, query):
        self.queries.append(query)
        return _snapshot("2330")


def _app():
    return QApplication.instance() or QApplication(sys.argv)


def _signal(code):
    aggregation = StockFlowAggregation(
        stock_code=code,
        stock_name=code,
        total_buy_qty=10,
        total_net_qty=10,
        lots_coverage_ratio=Decimal("1"),
    )
    return FlowSignalDTO(stock_code=code, stock_name=code, aggregation=aggregation)


def _snapshot(
    code,
    as_of_date=date(2026, 7, 10),
    period="week",
    tracked_branches=(("branch-a", "Branch A"),),
):
    return BrokerFlowDashboardSnapshot(
        as_of_date=as_of_date,
        period=period,
        top_signals=(_signal(code),),
        bottom_signals=(),
        summary=SmartMoneySummaryDTO(),
        semantics_by_code={},
        tracked_branches=tracked_branches,
        quality="observed",
    )


def _branch_row(stock_code, branch_name="Branch A"):
    return BranchFlowAggregation(
        branch_system_key=branch_name.lower().replace(" ", "-"),
        branch_display_name=branch_name,
        stock_code=stock_code,
        stock_name=stock_code,
        total_buy_qty=12,
        total_sell_qty=3,
        total_net_qty=9,
        usable_event_count=1,
    )


def test_dashboard_refresh_cancels_cooperatively_and_discards_stale_result():
    _app()
    factory = WorkerFactory()
    view = SmartMoneyFlowView(AsyncService(), task_worker_factory=factory)

    view._refresh_data()
    first = factory.workers[-1]
    view._refresh_data()
    second = factory.workers[-1]

    assert first.cancel_calls == [(True, False)]
    first.finished.emit(_snapshot("OLD"))
    assert not hasattr(view, "scanner_model")

    second.finished.emit(_snapshot("NEW"))
    assert view.scanner_model.get_signal_at(0).stock_code == "NEW"
    assert view.refresh_btn.isEnabled()


def test_dashboard_refresh_failure_keeps_previous_rows_and_identifies_their_date():
    _app()
    factory = WorkerFactory()
    view = SmartMoneyFlowView(AsyncService(), task_worker_factory=factory)
    view._apply_dashboard_snapshot(_snapshot("2330"))
    previous_row_count = view.scanner_model.rowCount()

    view.period_combo.setCurrentIndex(2)
    refresh_worker = factory.workers[-1]
    assert "主力資料更新中" in view.load_status_label.text()
    assert (
        "目前選擇「月線 (MONTH)／Top / Bottom 50」"
        in view.load_status_label.text()
    )
    assert (
        "前次成功結果「週線 (WEEK)／Top / Bottom 50」（資料日：2026-07-10）"
        in view.load_status_label.text()
    )
    assert view.scanner_model.rowCount() == previous_row_count

    refresh_worker.error.emit("database unavailable\ntraceback detail")

    assert view.scanner_model.rowCount() == previous_row_count
    assert view.scanner_model.get_signal_at(0).stock_code == "2330"
    assert "主力資料更新失敗：database unavailable" in view.load_status_label.text()
    assert (
        "前次成功結果「週線 (WEEK)／Top / Bottom 50」（資料日：2026-07-10）"
        in view.load_status_label.text()
    )


def test_scope_change_failure_identifies_previous_dashboard_scope():
    _app()
    factory = WorkerFactory()
    view = SmartMoneyFlowView(AsyncService(), task_worker_factory=factory)
    view._apply_dashboard_snapshot(_snapshot("2330"))

    view.scope_combo.setCurrentIndex(view.scope_combo.findData("all"))
    refresh_worker = factory.workers[-1]
    assert "目前選擇「週線 (WEEK)／全部」" in view.load_status_label.text()
    assert (
        "前次成功結果「週線 (WEEK)／Top / Bottom 50」"
        in view.load_status_label.text()
    )

    refresh_worker.error.emit("scope refresh failed")

    assert "主力資料更新失敗：scope refresh failed" in view.load_status_label.text()
    assert (
        "前次成功結果「週線 (WEEK)／Top / Bottom 50」"
        in view.load_status_label.text()
    )


def test_initial_dashboard_failure_does_not_claim_that_old_data_is_visible():
    _app()
    factory = WorkerFactory()
    view = SmartMoneyFlowView(AsyncService(), task_worker_factory=factory)

    view._refresh_data()
    factory.workers[-1].error.emit("database unavailable")

    assert "主力資料載入失敗：database unavailable" == view.load_status_label.text()
    assert "前次成功結果" not in view.load_status_label.text()
    assert view.scanner_row_count_label.text() == "尚未載入"


def test_successful_refresh_replaces_retained_snapshot_date_with_new_date():
    _app()
    factory = WorkerFactory()
    view = SmartMoneyFlowView(AsyncService(), task_worker_factory=factory)
    view._apply_dashboard_snapshot(_snapshot("OLD"))

    view._refresh_data()
    refresh_worker = factory.workers[-1]
    refresh_worker.finished.emit(
        _snapshot("NEW", as_of_date=date(2026, 7, 13))
    )

    assert view.scanner_model.get_signal_at(0).stock_code == "NEW"
    assert (
        "主力資料完成｜週線 (WEEK)／Top / Bottom 50｜資料日 2026-07-13｜observed"
        == view.load_status_label.text()
    )
    assert "前次成功結果" not in view.load_status_label.text()
    assert "分點追蹤載入中" in view.branch_status_label.text()


def test_branch_tracker_status_does_not_replace_dashboard_status():
    _app()
    factory = WorkerFactory()
    view = SmartMoneyFlowView(AsyncService(), task_worker_factory=factory)

    view._apply_dashboard_snapshot(_snapshot("2330"))
    dashboard_status = view.load_status_label.text()
    branch_worker = factory.workers[-1]
    branch_worker.finished.emit(BrokerFlowBranchTrackerSnapshot(
        as_of_date=date(2026, 7, 10),
        period="week",
        branch_system_key="branch-a",
        rows=(_branch_row("2330"),),
        quality="observed",
    ))

    assert view.load_status_label.text() == dashboard_status
    assert "Branch A｜週線 (WEEK)｜資料日 2026-07-10｜observed｜1 檔" == view.branch_status_label.text()


def test_branch_change_clears_old_rows_and_reports_failure_locally():
    _app()
    factory = WorkerFactory()
    view = SmartMoneyFlowView(AsyncService(), task_worker_factory=factory)
    view._apply_dashboard_snapshot(_snapshot(
        "2330",
        tracked_branches=(("branch-a", "Branch A"), ("branch-b", "Branch B")),
    ))
    first_branch_worker = factory.workers[-1]
    first_branch_worker.finished.emit(BrokerFlowBranchTrackerSnapshot(
        as_of_date=date(2026, 7, 10), period="week", branch_system_key="branch-a",
        rows=(_branch_row("2330"),), quality="observed",
    ))
    assert view.branch_table.model().rowCount() == 1
    dashboard_status = view.load_status_label.text()

    view.branch_combo.setCurrentIndex(1)
    branch_worker = factory.workers[-1]
    assert view.branch_table.model().rowCount() == 0
    assert "Branch B｜週線 (WEEK)｜資料日 2026-07-10｜分點追蹤載入中" in view.branch_status_label.text()

    branch_worker.error.emit("branch read failed")

    assert "Branch B｜週線 (WEEK)｜資料日 2026-07-10｜分點追蹤載入失敗：branch read failed" == view.branch_status_label.text()
    assert view.load_status_label.text() == dashboard_status


def test_dashboard_request_uses_taiwan_market_date(monkeypatch):
    _app()
    factory = WorkerFactory()
    service = CapturingDashboardService()
    monkeypatch.setattr(
        smart_money_view_module,
        "taiwan_market_today",
        lambda: date(2026, 10, 5),
    )
    view = SmartMoneyFlowView(service, task_worker_factory=factory)

    view._refresh_data()
    factory.workers[-1].task()

    assert service.queries[0].requested_as_of_date == date(2026, 10, 5)


def test_unknown_taiwan_market_date_starts_no_dashboard_or_detail_request(monkeypatch):
    _app()
    factory = WorkerFactory()

    def unavailable_date():
        raise OSError("Taiwan clock unavailable")

    monkeypatch.setattr(
        smart_money_view_module, "taiwan_market_today", unavailable_date
    )
    view = SmartMoneyFlowView(AsyncService(), task_worker_factory=factory)

    view._refresh_data()
    view.select_stock("2330")

    assert factory.workers == []
    assert "日期無法取得" in view.load_status_label.text()
    assert view.refresh_btn.isEnabled()
    assert view.period_combo.isEnabled()
    assert view.scope_combo.isEnabled()


def test_unknown_taiwan_market_date_keeps_previous_snapshot_date_visible(monkeypatch):
    _app()
    factory = WorkerFactory()
    view = SmartMoneyFlowView(AsyncService(), task_worker_factory=factory)
    view._apply_dashboard_snapshot(_snapshot("2330"))
    previous_worker_count = len(factory.workers)

    def unavailable_date():
        raise OSError("Taiwan clock unavailable")

    monkeypatch.setattr(
        smart_money_view_module, "taiwan_market_today", unavailable_date
    )
    view._refresh_data()

    assert len(factory.workers) == previous_worker_count
    assert view.scanner_model.get_signal_at(0).stock_code == "2330"
    assert "主力資料日期無法取得：Taiwan clock unavailable" in view.load_status_label.text()
    assert (
        "前次成功結果「週線 (WEEK)／Top / Bottom 50」（資料日：2026-07-10）"
        in view.load_status_label.text()
    )


def test_stock_detail_uses_worker_and_discards_previous_selection_result():
    _app()
    factory = WorkerFactory()
    view = SmartMoneyFlowView(AsyncService(), task_worker_factory=factory)
    view._dashboard_as_of_date = date(2026, 7, 10)
    view._apply_scanner_signals([_signal("2330")], semantics_by_code={})
    view.scanner_table.selectRow(0)
    view._on_scanner_selection_changed()

    worker = factory.workers[-1]
    assert worker.started
    assert view.detail_label.text().endswith("載入中…")
    assert "2330｜資料日 2026-07-10｜分點明細載入中" in view.detail_status_label.text()
    worker.finished.emit(BrokerFlowStockDetailSnapshot(
        as_of_date=date(2026, 7, 10), period="week", stock_code="2330",
        rows=(_branch_row("2330"),), quality="observed",
    ))
    assert view.detail_table.model().rowCount() == 1
    assert "2330｜資料日 2026-07-10｜品質 observed｜1 個分點" == view.detail_status_label.text()


def test_stock_change_clears_previous_rows_and_stale_result_cannot_replace_selection():
    _app()
    factory = WorkerFactory()
    view = SmartMoneyFlowView(AsyncService(), task_worker_factory=factory)
    view._dashboard_as_of_date = date(2026, 7, 10)
    view._apply_scanner_signals([_signal("2330"), _signal("2317")], semantics_by_code={})

    view.scanner_table.selectRow(0)
    worker_a = factory.workers[-1]
    worker_a.finished.emit(BrokerFlowStockDetailSnapshot(
        as_of_date=date(2026, 7, 10), period="week", stock_code="2330",
        rows=(_branch_row("2330", "A branch"),), quality="observed",
    ))
    assert view.detail_table.model().rowCount() == 1

    view.scanner_table.selectRow(1)
    worker_b = factory.workers[-1]
    assert view.detail_table.model().rowCount() == 0
    assert "2317｜資料日 2026-07-10｜分點明細載入中" in view.detail_status_label.text()

    worker_a.finished.emit(BrokerFlowStockDetailSnapshot(
        as_of_date=date(2026, 7, 10), period="week", stock_code="2330",
        rows=(_branch_row("2330", "Stale branch"),), quality="observed",
    ))
    assert view.detail_table.model().rowCount() == 0
    assert "2317" in view.detail_status_label.text()

    worker_b.finished.emit(BrokerFlowStockDetailSnapshot(
        as_of_date=date(2026, 7, 10), period="week", stock_code="2317",
        rows=(_branch_row("2317", "B branch"),), quality="observed",
    ))
    assert view.detail_table.model().rowCount() == 1
    assert "2317｜資料日 2026-07-10｜品質 observed｜1 個分點" == view.detail_status_label.text()


def test_stock_detail_worker_receives_the_dashboard_snapshot_for_reuse():
    _app()
    factory = WorkerFactory()

    class CapturingService(AsyncService):
        def __init__(self):
            self.detail_calls = []

        def load_stock_branch_detail(
            self, stock_code, period, as_of_date, *, dashboard_snapshot=None
        ):
            self.detail_calls.append(
                (stock_code, period, as_of_date, dashboard_snapshot)
            )
            return BrokerFlowStockDetailSnapshot(
                as_of_date=as_of_date,
                period=period,
                stock_code=stock_code,
                rows=(),
                quality="observed",
            )

    service = CapturingService()
    view = SmartMoneyFlowView(service, task_worker_factory=factory)
    snapshot = _snapshot("2330")
    view._apply_dashboard_snapshot(snapshot)

    view.scanner_table.selectRow(0)
    view._on_scanner_selection_changed()
    worker = factory.workers[-1]
    worker.task()

    assert service.detail_calls == [
        ("2330", "week", snapshot.as_of_date, snapshot)
    ]


def test_empty_degraded_and_failed_detail_states_are_explicit():
    _app()
    factory = WorkerFactory()
    view = SmartMoneyFlowView(AsyncService(), task_worker_factory=factory)
    view._dashboard_as_of_date = date(2026, 7, 10)
    view._apply_scanner_signals([_signal("2330")], semantics_by_code={})
    view.scanner_table.selectRow(0)
    worker = factory.workers[-1]

    worker.finished.emit(BrokerFlowStockDetailSnapshot(
        as_of_date=date(2026, 7, 10), period="week", stock_code="2330",
        rows=(), quality="observed",
    ))
    assert view.detail_table.model().rowCount() == 0
    assert "本次沒有可呈現的分點資料" in view.detail_status_label.text()

    view._on_scanner_selection_changed()
    worker = factory.workers[-1]
    worker.finished.emit(BrokerFlowStockDetailSnapshot(
        as_of_date=date(2026, 7, 10), period="week", stock_code="2330",
        rows=(), quality="degraded", warnings=("branch source incomplete",),
    ))
    assert "品質 degraded" in view.detail_status_label.text()
    assert "來源警示" in view.detail_status_label.text()
    assert "branch source incomplete" in view.detail_status_label.toolTip()

    view._on_scanner_selection_changed()
    worker = factory.workers[-1]
    worker.finished.emit(BrokerFlowStockDetailSnapshot(
        as_of_date=date(2026, 7, 10), period="week", stock_code="2330",
        rows=(), quality="missing", warnings=("branch dates unavailable",),
    ))
    assert "來源資料不可用" in view.detail_status_label.text()

    view._on_scanner_selection_changed()
    worker = factory.workers[-1]
    view._apply_stock_detail(BrokerFlowStockDetailSnapshot(
        as_of_date=date(2026, 7, 10), period="week", stock_code="2330",
        rows=(_branch_row("2330"),), quality="observed",
    ))
    assert view.detail_table.model().rowCount() == 1
    worker.error.emit("sqlite read failed\ntraceback detail")
    assert view.detail_table.model().rowCount() == 0
    assert "2330｜資料日 2026-07-10｜分點明細載入失敗" in view.detail_status_label.text()
    assert view.detail_label.text() == "分點買賣明細 (BRANCH DRILL-DOWN)"
    assert "sqlite read failed" in view.detail_status_label.toolTip()


def test_external_stock_selection_uses_the_same_context_and_clears_old_detail():
    _app()
    factory = WorkerFactory()
    view = SmartMoneyFlowView(AsyncService(), task_worker_factory=factory)
    view._dashboard_as_of_date = date(2026, 7, 10)
    view._data_loaded = True
    view._apply_scanner_signals([_signal("2330")], semantics_by_code={})
    view._apply_stock_detail(BrokerFlowStockDetailSnapshot(
        as_of_date=date(2026, 7, 10), period="week", stock_code="2330",
        rows=(_branch_row("2330"),), quality="observed",
    ))
    assert view.detail_table.model().rowCount() == 1

    view.select_stock("9999")

    worker = factory.workers[-1]
    assert view.detail_table.model().rowCount() == 0
    assert "9999｜資料日 2026-07-10｜分點明細載入中" in view.detail_status_label.text()
    worker.finished.emit(BrokerFlowStockDetailSnapshot(
        as_of_date=date(2026, 7, 10), period="week", stock_code="9999",
        rows=(), quality="missing", warnings=("branch dates unavailable",),
    ))
    assert "來源資料不可用" in view.detail_status_label.text()


def test_close_event_only_requests_cooperative_cancellation():
    _app()
    factory = WorkerFactory()
    view = SmartMoneyFlowView(AsyncService(), task_worker_factory=factory)
    view._refresh_data()
    worker = factory.workers[-1]

    view.close()

    assert worker.cancel_calls == [(True, False)]
