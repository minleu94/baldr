from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import os
from pathlib import Path
import threading
import time
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QDate, QEvent
from PySide6.QtWidgets import QApplication, QWidget
from PySide6.QtTest import QTest

from app_module.user_declared_holding_research import (
    ConditionObservation,
    MarketObservation,
    RESEARCH_ACTION_REDUCE,
    UserDeclaredHoldingDraft,
    UserDeclaredHoldingResearchReadModel,
    UserDeclaredHoldingResearchService,
    UserDeclaredHoldingResearchStore,
)
from ui_qt.widgets.user_declared_holding_research_widget import (
    UserDeclaredHoldingResearchWidget,
)


EARLY_NOW = datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc)
NOW = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)
EARLY_DATE = EARLY_NOW.date()
CURRENT_DATE = NOW.date()


def _app() -> QApplication:
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication(sys.argv)
    return instance


def _wait_until(predicate, timeout_seconds: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout_seconds
    instance = _app()
    while time.monotonic() < deadline:
        instance.processEvents()
        if predicate():
            return True
        QTest.qWait(5)
    instance.processEvents()
    return bool(predicate())


def _set_date(editor, value: date) -> None:
    editor.setDate(QDate(value.year, value.month, value.day))


def _service(tmp_path: Path, clock) -> UserDeclaredHoldingResearchService:
    return UserDeclaredHoldingResearchService(
        UserDeclaredHoldingResearchStore(
            tmp_path / "portfolio" / "user_declared_holdings.jsonl"
        ),
        now_provider=clock,
    )


def _market(
    stock_code: str,
    evaluation_date: date,
    *,
    price: Decimal = Decimal("123.45"),
) -> MarketObservation:
    historical = evaluation_date < CURRENT_DATE
    available_at = EARLY_NOW - timedelta(minutes=5) if historical else NOW - timedelta(hours=1)
    return MarketObservation(
        stock_code=stock_code,
        price=price,
        as_of_date=evaluation_date,
        source_id="ui-market-fixture",
        source_snapshot_hash="sha256:" + "a" * 64,
        available_at=available_at,
        quality="verified",
        availability_custody=historical,
    )


def _condition(record, evaluation_date: date) -> ConditionObservation:
    historical = evaluation_date < CURRENT_DATE
    available_at = EARLY_NOW - timedelta(minutes=5) if historical else NOW - timedelta(hours=1)
    return ConditionObservation(
        stock_code=record.stock_code,
        suggested_action=RESEARCH_ACTION_REDUCE,
        as_of_date=evaluation_date,
        source_id="ui-condition-fixture",
        source_snapshot_hash="sha256:" + "b" * 64,
        reasons=("UI 測試研究條件",),
        summary="研究條件需人工複核",
        available_at=available_at,
        quality="verified",
        availability_custody=historical,
    )


def _wait_for_refresh(widget: UserDeclaredHoldingResearchWidget) -> bool:
    # QThread.isRunning() 可能先變成 false，而 worker 的 queued finished
    # callback 尚未套用 read model；測試要等 widget 釋放 worker identity。
    return _wait_until(lambda: widget._refresh_worker is None)


def _close_widget(widget: UserDeclaredHoldingResearchWidget) -> None:
    if widget.is_refresh_running():
        widget.begin_shutdown()
        assert _wait_for_refresh(widget)
    widget.close()
    widget.deleteLater()
    _app().processEvents()


def test_user_declared_widget_crud_research_and_exact_revision_resync(tmp_path: Path) -> None:
    _app()
    clock = [EARLY_NOW]
    service = _service(tmp_path, lambda: clock[0])
    widget = UserDeclaredHoldingResearchWidget(
        service,
        market_source=_market,
        condition_source=_condition,
        now_provider=lambda: clock[0],
    )
    try:
        assert _wait_for_refresh(widget)
        assert widget.table_model.rowCount() == 0
        assert widget.form_group.isHidden()
        widget.form_toggle.click()
        assert widget.form_group.isHidden() is False

        widget.stock_code_input.setText("2330")
        widget.quantity_input.setValue(100)
        widget.declared_cost_input.setText("100.00")
        _set_date(widget.declared_date_input, EARLY_DATE)
        widget.thesis_input.setPlainText("趨勢與基本面仍需持續確認")
        widget.notes_input.setPlainText("首次聲明")
        widget.save_new()

        assert _wait_for_refresh(widget)
        assert widget.table_model.rowCount() == 1
        first_row = widget.table_model.row_at(0)
        assert first_row is not None
        holding_id = first_row.holding_id
        assert first_row.record.revision_number == 1
        assert first_row.research_status == "ready"
        assert widget.boundary_label.text().find("不是券商成交") >= 0
        assert widget.boundary_label.text().find("Paper Portfolio") >= 0

        # 跨日刷新後使用目前 worker 的 exact identity；此時仍是 revision 1。
        clock[0] = NOW
        _set_date(widget.evaluation_date_input, CURRENT_DATE)
        widget.refresh_research()
        assert _wait_for_refresh(widget)
        assert widget.table_model.row_at(0).record.revision_number == 1
        widget.holdings_table.selectRow(0)
        widget._on_row_selected(widget.table_model.index(0, 0))
        assert widget._editing_holding_id == holding_id
        assert widget._editing_revision_number == 1
        assert "聲明研究帳" in widget.detail_label.text()
        assert "成本口徑：使用者聲明單價 100.00" in widget.detail_label.text()
        assert "估值日期：" in widget.detail_label.text()
        assert "費稅／滑價／換手率／集中度影響：未提供，未知" in widget.detail_label.text()

        widget.quantity_input.setValue(120)
        widget.save_revision()
        assert _wait_for_refresh(widget)
        revised_row = widget.table_model.row_at(0)
        assert revised_row is not None
        assert revised_row.record.revision_number == 2
        assert revised_row.record.quantity == 120
        assert widget._editing_revision_number == 2

        widget.technical_toggle.click()
        assert widget.technical_detail.isHidden() is False
        assert "formal_credit=False" in widget.technical_detail.toPlainText()
        assert "revision=2" in widget.technical_detail.toPlainText()

        # 歷史讀取只能投影當時存在的 revision；不可把目前 revision 悄悄帶入 editor。
        _set_date(widget.evaluation_date_input, EARLY_DATE)
        widget.refresh_research()
        assert _wait_for_refresh(widget)
        historical_row = widget.table_model.row_at(0)
        assert historical_row is not None
        assert historical_row.record.revision_number == 1
        assert widget._editing_holding_id == ""
        assert widget._editing_revision_number is None
        assert widget.revise_button.isEnabled() is False

        _set_date(widget.evaluation_date_input, CURRENT_DATE)
        widget.refresh_research()
        assert _wait_for_refresh(widget)
        assert widget.table_model.row_at(0).record.revision_number == 2
        widget.holdings_table.selectRow(0)
        widget._on_row_selected(widget.table_model.index(0, 0))
        widget.archive_selected(confirm=False)
        assert _wait_for_refresh(widget)
        assert widget.table_model.rowCount() == 0
        assert widget.read_model is not None
        assert widget.read_model.status == "empty"
        assert len(service.history(holding_id)) == 3
    finally:
        _close_widget(widget)


class _SlowMarketSource:
    def __init__(self) -> None:
        self.delay_seconds = 0.2
        self.price = Decimal("101.00")
        self.calls = 0
        self.started = threading.Event()
        self.cancelled = threading.Event()

    def __call__(self, stock_code: str, evaluation_date: date, *, cancel_callback=None):
        self.calls += 1
        self.started.set()
        deadline = time.monotonic() + self.delay_seconds
        while time.monotonic() < deadline:
            if callable(cancel_callback) and cancel_callback():
                self.cancelled.set()
                raise RuntimeError("slow market source cancelled")
            time.sleep(0.005)
        return _market(stock_code, evaluation_date, price=self.price)


def test_user_declared_widget_cancels_slow_refresh_and_closes_naturally(tmp_path: Path) -> None:
    _app()
    clock = lambda: NOW
    service = _service(tmp_path, clock)
    service.create_holding(
        UserDeclaredHoldingDraft(
            stock_code="2330",
            quantity=100,
            declared_cost="100.00",
            declared_date=CURRENT_DATE,
            thesis="背景刷新取消測試",
        ),
        request_id="ui-cancel-create",
    )
    slow_market = _SlowMarketSource()
    widget = UserDeclaredHoldingResearchWidget(
        service,
        market_source=slow_market,
        condition_source=_condition,
        now_provider=clock,
    )
    try:
        assert slow_market.started.wait(timeout=2)
        started_at = time.monotonic()
        widget.refresh_research()
        elapsed = time.monotonic() - started_at
        assert elapsed < 0.12
        assert widget._refresh_pending is True
        slow_market.price = Decimal("202.00")

        assert _wait_until(
            lambda: slow_market.cancelled.is_set()
            and slow_market.calls >= 2
            and widget._refresh_worker is None,
            timeout_seconds=5.0,
        )
        row = widget.table_model.row_at(0)
        assert row is not None
        assert row.market_price == Decimal("202.00")

        # close() 第一次只發出合作式取消，不能在主執行緒 wait／terminate。
        slow_market.started.clear()
        slow_market.cancelled.clear()
        slow_market.price = Decimal("303.00")
        widget.refresh_research()
        assert slow_market.started.wait(timeout=2)
        close_started_at = time.monotonic()
        widget.close()
        assert time.monotonic() - close_started_at < 0.12
        assert widget._closing is True
        assert _wait_for_refresh(widget)
        assert slow_market.cancelled.is_set()
        widget.close()
    finally:
        _close_widget(widget)


def test_parent_destruction_drops_late_research_worker_callback(
    tmp_path: Path, monkeypatch
) -> None:
    _app()
    worker_started = threading.Event()
    release_worker = threading.Event()
    applied_models = []

    class BarrierService:
        def read_research(
            self,
            *,
            evaluation_date,
            evaluated_at,
            portfolio_id,
            market_source,
            condition_source,
            cancel_callback=None,
        ):
            worker_started.set()
            if not release_worker.wait(timeout=5):
                raise TimeoutError("測試 barrier 未釋放")
            return UserDeclaredHoldingResearchReadModel(
                evaluation_date=evaluation_date,
                evaluated_at=evaluated_at.isoformat(),
                status="empty",
                rows=(),
            )

    monkeypatch.setattr(
        UserDeclaredHoldingResearchWidget,
        "_apply_research_read_model",
        lambda self, model, selection: applied_models.append((model, selection)),
    )
    parent = QWidget()
    widget = UserDeclaredHoldingResearchWidget(
        BarrierService(),
        now_provider=lambda: NOW,
        parent=parent,
    )
    worker = widget._refresh_worker
    assert worker is not None

    try:
        assert worker_started.wait(timeout=2)
        parent.deleteLater()
        QCoreApplication.sendPostedEvents(parent, QEvent.DeferredDelete)
        release_worker.set()
        assert worker.wait(5000)
        _app().processEvents()

        assert applied_models == []
    finally:
        release_worker.set()
        worker.wait(5000)
        _app().processEvents()
