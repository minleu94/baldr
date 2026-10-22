from __future__ import annotations

import sys
from datetime import datetime, timezone
from threading import Event
from types import SimpleNamespace

from PySide6.QtCore import QEventLoop, QTimer

from PySide6.QtWidgets import QApplication

from app_module.dtos.portfolio_dtos import JournalEntryDTO
from app_module.research_paper_producer import ResearchPaperProductionResult, ResearchPaperProducer
from app_module.research_timeline_dtos import ResearchTimelineEntry
from tests.test_research_paper_evidence_binding import _build_paper_fixture
from ui_qt.widgets.research_paper_simulation_dialog import ResearchPaperSimulationDialog


_APPLICATION: QApplication | None = None


def _app() -> QApplication:
    global _APPLICATION
    if _APPLICATION is None:
        instance = QApplication.instance()
        _APPLICATION = instance if instance is not None else QApplication(sys.argv)
    return _APPLICATION


def _entry() -> ResearchTimelineEntry:
    reference = JournalEntryDTO(
        journal_id="paper-ui-saved-research",
        portfolio_id="default",
        body="研究原文只讀。",
        stock_code="2330",
        created_at="2026-10-21T08:30:00+00:00",
        revision_id="paper-ui-saved-research-r1",
    )
    return ResearchTimelineEntry(
        kind="report",
        record_id="paper-ui-saved-research",
        recorded_at="2026-10-21T08:30:00+00:00",
        text="研究原文只讀。",
        reference=reference,
        stock_code="2330",
        data_date="2026-10-20",
        source_identity="來源身份由原件提供",
    )


def _wait_for(predicate, *, timeout: float = 8.0) -> None:
    _app()
    loop = QEventLoop()
    timer = QTimer()
    timer.setInterval(10)
    state = {"done": False}

    def check() -> None:
        if predicate():
            state["done"] = True
            loop.quit()

    timer.timeout.connect(check)
    timer.start()
    QTimer.singleShot(round(timeout * 1000), loop.quit)
    check()
    if not state["done"]:
        loop.exec()
    timer.stop()
    assert state["done"], "timed out waiting for Paper dialog worker"


class _GatedReader:
    def __init__(self, reader, gate: Event) -> None:
        self.reader = reader
        self.gate = gate

    def preview(self, entry: ResearchTimelineEntry):
        self.gate.wait(timeout=8)
        return self.reader.preview(entry)

    def verify(self, entry: ResearchTimelineEntry, intent: object):
        return self.reader.verify(entry, intent)


def test_missing_reader_and_producer_keep_simulation_flow_fail_closed():
    _app()
    entry = _entry()
    dialog = ResearchPaperSimulationDialog(entry, provider=None, producer_factory=None)

    assert dialog.objectName() == "researchPaperSimulationDialog"
    assert not dialog.preview_source_button.isEnabled()
    assert not dialog.preview_button.isEnabled()
    assert not dialog.confirm_button.isEnabled()
    assert dialog.quantity_edit.text() == ""
    assert dialog.account_combo.currentData() is None
    assert dialog.strategy_combo.currentData() is None
    assert dialog.side_combo.currentData() is None
    assert "未設定" in dialog.status_label.text()
    assert dialog._validated_inputs() is None

    returned: list[object] = []
    status_requests: list[None] = []
    dialog.returnToEntryRequested.connect(returned.append)
    dialog.paperStatusRequested.connect(lambda: status_requests.append(None))
    assert dialog.paper_status_button.text() == "查看既有 Paper"
    dialog.paper_status_button.click()
    assert status_requests == [None]
    dialog.return_button.click()
    assert returned == [entry]
    assert dialog.entry is entry
    dialog.deleteLater()


def test_missing_verified_context_never_builds_an_intent_or_invokes_producer():
    _app()
    entry = _entry()
    calls: list[str] = []

    def producer_factory(_intent: object):
        calls.append("factory")
        raise AssertionError("producer factory must remain untouched before confirmation")

    dialog = ResearchPaperSimulationDialog(entry, provider=None, producer_factory=producer_factory)
    dialog._start_simulation_preview()

    assert dialog._context is None
    assert dialog._intent is None
    assert dialog._preview_values is None
    assert not dialog.confirm_button.isEnabled()
    assert calls == []
    dialog.close()
    dialog.deleteLater()


def _dialog(fixture, producer_factory, *, provider=None, clock=None):
    return ResearchPaperSimulationDialog(
        fixture.entry,
        provider=provider or fixture.reader,
        producer_factory=producer_factory,
        clock=clock or (lambda: datetime(2026, 10, 21, 5, 0, tzinfo=timezone.utc)),
    )


def _load_source_and_preview(dialog: ResearchPaperSimulationDialog) -> None:
    dialog.preview_source_button.click()
    _wait_for(lambda: dialog._worker is None and dialog._context is not None)
    assert dialog.account_combo.currentData() is None
    assert dialog.strategy_combo.currentData() is None
    assert dialog.side_combo.currentData() is None
    dialog.account_combo.setCurrentIndex(1)
    dialog.strategy_combo.setCurrentIndex(1)
    dialog.side_combo.setCurrentIndex(1)
    dialog.quantity_edit.setText("1000")
    dialog.preview_button.click()
    _wait_for(lambda: dialog._worker is None and dialog._intent is not None)
    assert dialog._preview_values is not None
    assert dialog.confirm_button.isEnabled()


def test_positive_widget_confirmation_uses_real_preview_and_returns_saved_original(tmp_path):
    _app()
    factory_intents = []
    fixture = _build_paper_fixture(tmp_path)
    clock_values = iter((
        datetime(2026, 10, 21, 5, 0, tzinfo=timezone.utc),
        datetime(2026, 10, 21, 5, 10, tzinfo=timezone.utc),
        datetime(2026, 10, 21, 5, 15, tzinfo=timezone.utc),
    ))

    def factory(intent):
        factory_intents.append(intent)
        return ResearchPaperProducer(
            evidence_provider=fixture.reader,
            ledger=fixture.ledger,
            clock=lambda: datetime(2026, 10, 21, 5, 30, tzinfo=timezone.utc),
        )

    dialog = _dialog(fixture, factory, clock=lambda: next(clock_values))
    entry = fixture.entry
    results = []
    returned = []
    dialog.paperProduced.connect(results.append)
    dialog.returnToEntryRequested.connect(returned.append)
    _load_source_and_preview(dialog)

    preview_text = dialog.preview_summary.toPlainText()
    assert "行情日期：2026-10-21" in preview_text
    assert "佣金：" in preview_text
    assert "模擬後現金：" in preview_text
    obsolete_intent = dialog._intent
    dialog.quantity_edit.setText("3000")
    assert dialog._intent is None
    assert not dialog.confirm_button.isEnabled()
    dialog.quantity_edit.setText("1000")
    dialog.preview_button.click()
    _wait_for(lambda: dialog._worker is None and dialog._intent is not None)
    preview_intent = dialog._intent
    assert preview_intent is not obsolete_intent
    dialog.confirm_button.click()
    intent = dialog._intent
    assert intent is not preview_intent
    assert intent.operation_id == preview_intent.operation_id
    assert intent.confirmation_id == preview_intent.confirmation_id
    assert intent.confirmed_at == "2026-10-21T05:15:00+00:00"
    _wait_for(lambda: dialog._worker is None and bool(results))

    result = results[0]
    assert isinstance(result, ResearchPaperProductionResult)
    assert len(factory_intents) == 1 and factory_intents[0] is intent
    assert result.return_entry is entry
    assert result.fill.research_only is True
    assert result.fill.broker_order_allowed is False
    assert result.fill.auto_rebalance_allowed is False
    assert fixture.ledger.read_exact_daily_operation(
        intent.operation_id,
        portfolio_id=result.account_namespace,
        event_date=intent.event_date,
    ).ordered_fills == (result.fill,)
    assert returned == [entry]
    dialog.close()
    dialog.deleteLater()


def test_failed_save_retry_reuses_same_immutable_intent(tmp_path):
    _app()
    seen_factory_intents = []
    seen_producer_intents = []
    calls = {"count": 0}

    class _Producer:
        def produce(self, entry, intent):
            seen_producer_intents.append(intent)
            calls["count"] += 1
            if calls["count"] == 1:
                raise RuntimeError("fixture transient failure")
            return SimpleNamespace(return_entry=entry, operation_id=intent.operation_id)

    def factory(intent):
        seen_factory_intents.append(intent)
        return _Producer()

    fixture = _build_paper_fixture(tmp_path)
    dialog = _dialog(fixture, factory)
    entry = fixture.entry
    results = []
    dialog.paperProduced.connect(results.append)
    _load_source_and_preview(dialog)
    preview_intent = dialog._intent
    clock_values = iter((
        datetime(2026, 10, 21, 5, 6, tzinfo=timezone.utc),
    ))
    clock_calls = []
    dialog._clock = lambda: clock_calls.append(None) or next(clock_values)

    dialog.confirm_button.click()
    frozen_intent = dialog._intent
    assert frozen_intent is not preview_intent
    assert frozen_intent.confirmed_at == "2026-10-21T05:06:00+00:00"
    _wait_for(lambda: dialog._worker is None and dialog.retry_button.isEnabled())
    assert dialog._intent is frozen_intent
    assert frozen_intent.confirmed_at == "2026-10-21T05:06:00+00:00"
    assert not dialog.confirm_button.isEnabled()
    dialog.retry_button.click()
    _wait_for(lambda: dialog._worker is None and bool(results))
    assert len(seen_factory_intents) == 2
    assert len(seen_producer_intents) == 2
    assert all(intent is frozen_intent for intent in seen_factory_intents)
    assert all(intent is frozen_intent for intent in seen_producer_intents)
    assert len(clock_calls) == 1
    assert dialog._intent is frozen_intent
    assert results[0].return_entry is entry
    dialog.close()
    dialog.deleteLater()


def test_confirmation_crossing_taipei_date_clears_preview_without_factory(tmp_path):
    _app()
    factory_calls = []
    clock_values = iter((
        datetime(2026, 10, 21, 15, 59, tzinfo=timezone.utc),
        datetime(2026, 10, 21, 16, 1, tzinfo=timezone.utc),
    ))
    fixture = _build_paper_fixture(tmp_path)

    def factory(intent):
        factory_calls.append(intent)
        raise AssertionError("跨日確認不得建立 writer")

    dialog = _dialog(fixture, factory, clock=lambda: next(clock_values))
    _load_source_and_preview(dialog)
    assert dialog._intent.confirmed_at == "2026-10-21T15:59:00+00:00"

    dialog.confirm_button.click()

    assert factory_calls == []
    assert dialog._worker is None
    assert dialog._intent is None
    assert dialog._preview_values is None
    assert "跨行情事件日" in dialog.status_label.text()
    dialog.close()
    dialog.deleteLater()


def test_close_waits_for_late_preview_worker_and_return_preserves_exact_entry(tmp_path):
    _app()
    release = Event()
    fixture = _build_paper_fixture(tmp_path)
    entry = fixture.entry
    reader = _GatedReader(fixture.reader, release)
    dialog = _dialog(fixture, None, provider=reader)
    returned = []
    dialog.returnToEntryRequested.connect(returned.append)
    dialog.show()
    dialog.preview_source_button.click()
    assert dialog._worker is not None
    assert not dialog.paper_status_button.isEnabled()
    dialog.close()
    assert dialog.isVisible()
    assert dialog._worker is not None

    release.set()
    _wait_for(lambda: dialog._worker is None and dialog._context is not None)
    assert dialog.isVisible()
    dialog.return_button.click()
    assert returned == [entry]
    assert not dialog.isVisible()
    dialog.deleteLater()
