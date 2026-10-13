"""Portable UI state-machine checks for saved Position Health selection.

This module uses the product overlay through ordinary app_module/ui_qt imports.
It imports the public application and UI modules without task-specific path metadata.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace
import threading
import time

import pytest
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app_module.exceptions import BacktestCancelledError
from app_module.position_health_saved_archive import SavedHealthReceiptCandidate
from app_module.position_health_saved_selection import (
    SavedHealthSelection,
    SavedHealthSelectionStore,
)
from ui_qt.widgets.position_health_saved_panel import PositionHealthSavedPanel
from ui_qt.workers.task_worker import running_task_workers


@pytest.fixture
def application() -> QApplication:
    current = QApplication.instance()
    return current if current is not None else QApplication(["health-saved-panel-portable"])


def _wait(application: QApplication, predicate, *, timeout: float = 8.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        application.processEvents()
        if predicate():
            return
        QTest.qWait(10)
    application.processEvents()
    assert predicate(), "saved Health UI operation did not reach its expected state"


def _record(key: str) -> SavedHealthSelection:
    return SavedHealthSelection(
        account_kind="paper-main",
        namespace=None,
        portfolio_id="paper-main",
        snapshot_id=f"paper-main-20261008-{key}",
        snapshot_rows_sha256="sha256:" + key * 64,
        decision_date="2026-10-08",
        receipt_id="phsr-v1-" + key * 64,
        receipt_sha256="sha256:" + ("a" if key == "1" else "b") * 64,
        result_sha256="sha256:" + ("c" if key == "1" else "d") * 64,
        status="passed",
        selected_position_id=None,
        selected_at="2026-10-08T09:00:00+00:00",
        saved_receipt_available_at="2026-10-08T08:55:00+00:00",
        health_observed_at="2026-10-08T08:50:00+00:00",
        source_observed_at="2026-10-08T08:45:00+00:00",
        source_available_at=None,
        baseline_saved_available_at="2026-10-08T08:48:00+00:00",
        health_source_available_at=None,
        source_witness_status="structurally_valid",
    )


def _candidate(record: SavedHealthSelection) -> SavedHealthReceiptCandidate:
    return SavedHealthReceiptCandidate(
        receipt_id=record.receipt_id,
        receipt_sha256=record.receipt_sha256,
        result_sha256=record.result_sha256,
        portfolio_id=record.portfolio_id,
        snapshot_id=record.snapshot_id,
        decision_date=date.fromisoformat(record.decision_date),
        source_snapshot_rows_sha256=record.snapshot_rows_sha256,
        status=record.status,
        observed_at=record.health_observed_at,
        available_at=record.saved_receipt_available_at,
    )


def _opened(record: SavedHealthSelection):
    return SimpleNamespace(
        source=SimpleNamespace(
            receipt_id=record.receipt_id,
            receipt_sha256=record.receipt_sha256,
            result_sha256=record.result_sha256,
            observed_at=record.health_observed_at,
            available_at=record.saved_receipt_available_at,
            source_observed_at=record.source_observed_at,
            source_available_at=record.source_available_at,
        ),
        snapshot=SimpleNamespace(
            portfolio_id=record.portfolio_id,
            snapshot_id=record.snapshot_id,
            source_snapshot_rows_sha256=record.snapshot_rows_sha256,
            decision_date=date.fromisoformat(record.decision_date),
        ),
        read_model=SimpleNamespace(
            health=object(),
            status=record.status,
            positions=(),
            saved_receipt_available_at=record.saved_receipt_available_at,
            observed_at=record.health_observed_at,
            source_observed_at=record.source_observed_at,
            source_available_at=record.source_available_at,
            baseline_saved_available_at=record.baseline_saved_available_at,
            health_source_available_at=record.health_source_available_at,
            source_witness_status=record.source_witness_status,
        ),
        paper_snapshot_receipt_present=False,
    )


class CandidateReader:
    def __init__(self, records: tuple[SavedHealthSelection, ...]) -> None:
        self.candidates = tuple(_candidate(item) for item in records)

    def list_saved_receipts(self, cancel_callback=None):
        if cancel_callback is not None and cancel_callback():
            raise BacktestCancelledError("candidate listing cancelled")
        return self.candidates


class ImmediateExactFactory:
    def __init__(self, records: tuple[SavedHealthSelection, ...]) -> None:
        self.records = {item.receipt_id: item for item in records}
        self.opened_receipts: list[str] = []

    def open_saved_selection(self, selector, *, cancel_callback=None, **expected):
        if cancel_callback is not None and cancel_callback():
            raise BacktestCancelledError("exact open cancelled")
        record = self.records[selector.receipt_id]
        assert expected["expected_receipt_sha256"] == record.receipt_sha256
        assert expected["expected_result_sha256"] == record.result_sha256
        assert expected["expected_snapshot_rows_sha256"] == record.snapshot_rows_sha256
        assert expected["expected_snapshot_id"] == record.snapshot_id
        assert expected["expected_decision_date"] == record.decision_date
        self.opened_receipts.append(selector.receipt_id)
        return _opened(record)


class BlockingExactFactory(ImmediateExactFactory):
    def __init__(
        self,
        records: tuple[SavedHealthSelection, ...],
        *,
        block_receipt_id: str,
    ) -> None:
        super().__init__(records)
        self.block_receipt_id = block_receipt_id
        self.first_started = threading.Event()
        self.release_first = threading.Event()
        self.cancelled_receipts: list[str] = []

    def open_saved_selection(self, selector, *, cancel_callback=None, **expected):
        if selector.receipt_id == self.block_receipt_id:
            self.first_started.set()
            if not self.release_first.wait(8):
                raise TimeoutError("controlled exact open did not release")
            if cancel_callback is not None and cancel_callback():
                self.cancelled_receipts.append(selector.receipt_id)
                raise BacktestCancelledError("exact open cooperatively cancelled")
        return super().open_saved_selection(
            selector, cancel_callback=cancel_callback, **expected
        )


def test_saved_panel_requires_explicit_receipt_and_keeps_prior_selection_on_save_failure(
    tmp_path: Path, application: QApplication
) -> None:
    old_record, new_record = _record("1"), _record("2")
    output_root = tmp_path / "output"
    output_root.mkdir()
    backing = SavedHealthSelectionStore(
        output_root / "portfolio" / "saved_health_selection.json",
        allowed_root=output_root,
    )
    backing.save(old_record)

    class FailingStore:
        def read(self):
            return backing.read()

        def save(self, _record):
            raise OSError("controlled persistence failure")

    factory = ImmediateExactFactory((old_record, new_record))
    panel = PositionHealthSavedPanel(
        reader=CandidateReader((old_record, new_record)),
        scope_factory=factory,
        selection_store=FailingStore(),
    )
    try:
        panel.reload_persisted_selection()
        _wait(application, lambda: panel._current_record == old_record and panel._worker is None)
        assert factory.opened_receipts == [old_record.receipt_id]
        panel.load_candidates()
        _wait(
            application,
            lambda: panel.saved_receipt_selector.count() == 2
            and panel._worker is None,
        )
        assert panel.saved_receipt_selector.currentIndex() == -1
        panel.open_selected()
        assert factory.opened_receipts == [old_record.receipt_id]
        assert "請先載入並明確選取" in panel.saved_status_label.text()

        panel.saved_receipt_selector.setCurrentIndex(1)
        panel.open_selected()
        _wait(application, lambda: panel._worker is None)
        assert factory.opened_receipts == [old_record.receipt_id, new_record.receipt_id]
        assert panel._current_record == old_record
        assert backing.read() == old_record
        assert "無法安全保存回訪選擇" in panel.saved_status_label.text()
    finally:
        panel.begin_shutdown()
        panel.close()
        _wait(application, lambda: not running_task_workers())


def test_real_taskworker_cancels_stale_receipt_and_releases_only_matching_owner(
    tmp_path: Path, application: QApplication
) -> None:
    first, latest = _record("1"), _record("2")
    records = (first, latest)
    output_root = tmp_path / "output"
    output_root.mkdir()
    store = SavedHealthSelectionStore(
        output_root / "portfolio" / "saved_health_selection.json",
        allowed_root=output_root,
    )
    factory = BlockingExactFactory(records, block_receipt_id=first.receipt_id)
    panel = PositionHealthSavedPanel(
        reader=CandidateReader(records),
        scope_factory=factory,
        selection_store=store,
    )
    finished_generations: list[int] = []
    panel._worker_events.native_finished.connect(
        lambda generation, _worker: finished_generations.append(generation)
    )
    try:
        panel.load_candidates()
        _wait(
            application,
            lambda: panel.saved_receipt_selector.count() == 2
            and panel._worker is None,
        )
        panel.saved_receipt_selector.setCurrentIndex(0)
        panel.open_selected()
        _wait(application, lambda: factory.first_started.is_set())
        first_worker = panel._worker
        assert first_worker is not None

        panel.saved_receipt_selector.setCurrentIndex(1)
        panel.open_selected()
        assert panel._worker is first_worker
        assert panel._pending is not None
        assert panel._pending[2][0].receipt_id == latest.receipt_id
        assert store.read() is None
        panel._on_finished(2, "open_candidate", (_opened(first), first))
        panel._on_native_finished(1, first_worker)
        assert panel._worker is first_worker
        assert panel._pending is not None and panel._pending[2][0].receipt_id == latest.receipt_id
        assert store.read() is None

        factory.release_first.set()
        _wait(
            application,
            lambda: panel._worker is None
            and panel._current_record is not None
            and panel._current_record.receipt_id == latest.receipt_id,
        )
        assert factory.cancelled_receipts == [first.receipt_id]
        assert store.read() == panel._current_record
        assert finished_generations == [1, 2, 3]
    finally:
        factory.release_first.set()
        panel.begin_shutdown()
        panel.close()
        _wait(application, lambda: not running_task_workers())
def test_real_taskworker_close_keeps_owner_until_native_finish(
    tmp_path: Path, application: QApplication
) -> None:
    current, second = _record("1"), _record("2")
    records = (current, second)
    output_root = tmp_path / "output"
    output_root.mkdir()
    store = SavedHealthSelectionStore(
        output_root / "portfolio" / "saved_health_selection.json",
        allowed_root=output_root,
    )
    factory = BlockingExactFactory(records, block_receipt_id=second.receipt_id)
    panel = PositionHealthSavedPanel(
        reader=CandidateReader(records),
        scope_factory=factory,
        selection_store=store,
    )
    try:
        panel.load_candidates()
        _wait(
            application,
            lambda: panel.saved_receipt_selector.count() == 2
            and panel._worker is None,
        )
        panel.saved_receipt_selector.setCurrentIndex(1)
        panel.open_selected()
        _wait(application, lambda: factory.first_started.is_set())
        running = panel._worker
        assert running is not None
        panel.begin_shutdown()
        panel.close()
        assert panel.has_running_worker()
        assert store.read() is None
        factory.release_first.set()
        _wait(application, lambda: not panel.has_running_worker())
        assert panel._worker is None
        assert store.read() is None
        assert factory.cancelled_receipts == [second.receipt_id]
    finally:
        factory.release_first.set()
        panel.begin_shutdown()
        panel.close()
        _wait(application, lambda: not running_task_workers())