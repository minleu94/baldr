"""題材研究清除操作、筆記保護與背景讀取失效測試。"""

import os
import sys
import threading
import time
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from app_module.theme_daily_service import (
    ThemeDailyReport,
    ThemeDailyRow,
    ThemeMetricCoverage,
)
from app_module.theme_research_snapshot import ThemeResearchSnapshot
from ui_qt.views import industry_theme_map_view as view_module
from ui_qt.views.industry_theme_map_view import IndustryThemeMapView
from ui_qt.widgets.theme_research_notes_widget import ThemeResearchNotesWidget


def app() -> QApplication:
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication(sys.argv)
    return instance


def _wait_until(application: QApplication, predicate, *, timeout_ms: int) -> None:
    deadline = time.monotonic() + timeout_ms / 1000
    while True:
        application.processEvents()
        if predicate():
            application.processEvents()
            return
        if time.monotonic() >= deadline:
            raise AssertionError("Qt 狀態未在固定期限內完成")
        QTest.qWait(10)


def _show(view: IndustryThemeMapView, application: QApplication) -> None:
    view.resize(1280, 760)
    view.show()
    _wait_until(
        application,
        lambda: view.open_snapshot_button.isVisible(),
        timeout_ms=1000,
    )


def _snapshot(identity: str = "a" * 64) -> ThemeResearchSnapshot:
    row = ThemeDailyRow(
        chain_name="科技鏈",
        theme_name="AI",
        stock_ids=("2330", "2317"),
        mean_return_pct=Decimal("1.25"),
        turnover_twd=Decimal("250.00"),
        volume_multiple_5d=Decimal("1.10"),
        institutional_net_shares=10,
        institutional_net_turnover_twd=Decimal("150.00"),
        up_count=1,
        down_count=0,
        flat_count=1,
        institutional_buy_count=1,
        institutional_sell_count=0,
        institutional_flat_count=1,
        advancing_ratio=Decimal("0.5"),
        institutional_buy_ratio=Decimal("0.5"),
        coverage=ThemeMetricCoverage(2, 2, 2, 2, 2, 2),
        source_ids=("local-test-source",),
    )
    report = ThemeDailyReport(
        data_date=date(2026, 10, 16),
        known_at=datetime(2026, 10, 17, 2, 0, tzinfo=timezone.utc),
        mapping_snapshot_date="2026-10-15",
        mapping_available_date="2026-10-15",
        status="current_research",
        rows=(row,),
        warnings=(),
    )
    mapping = tuple(
        SimpleNamespace(
            stock_id=stock_id,
            stock_name=stock_name,
            chain_name="科技鏈",
            theme_name="AI",
            chain_tier="核心鏈",
            assignment_method="公司主業",
            source_name="本機分類來源",
            source_tier="來源一級",
            evidence_note="依保存映射列",
        )
        for stock_id, stock_name in (("2330", "台積電"), ("2317", "鴻海"))
    )
    return ThemeResearchSnapshot(identity, report, mapping)


def _attach_notes(view: IndustryThemeMapView) -> ThemeResearchNotesWidget:
    notes = ThemeResearchNotesWidget(
        SimpleNamespace(), parent=view, auto_refresh=False
    )
    view.content.layout().insertWidget(view.content.layout().count() - 1, notes)
    view.snapshotChanged.connect(notes.set_snapshot)
    return notes


def _select_ai(view: IndustryThemeMapView) -> None:
    view.chain_filter.setCurrentIndex(view.chain_filter.findData("科技鏈"))
    view.theme_filter.setCurrentIndex(view.theme_filter.findText("AI"))


def _answer_confirmation(monkeypatch, answer):
    seen = []

    def question(parent, title, text, buttons, default_button):
        seen.append((title, text, buttons, default_button))
        return answer

    monkeypatch.setattr(
        view_module,
        "QMessageBox",
        SimpleNamespace(StandardButton=QMessageBox.StandardButton, question=question),
    )
    return seen


def test_clear_research_resets_view_and_discards_confirmed_draft(monkeypatch):
    application = app()
    view = IndustryThemeMapView()
    notes = _attach_notes(view)
    snapshot = _snapshot()
    events = []
    selected_stocks = []
    view.snapshotChanged.connect(events.append)
    view.stockSelected.connect(selected_stocks.append)
    try:
        _show(view, application)
        view.set_snapshot(snapshot)
        _select_ai(view)
        view.ranking_type_combo.setCurrentIndex(
            view.ranking_type_combo.findData("turnover")
        )
        view.sorting_direction_combo.setCurrentIndex(
            view.sorting_direction_combo.findData(True)
        )
        view.stock_lookup_input.setText("2330")
        view.chain_directory_button.click()
        view.source_details_button.click()
        notes.saved_text.setPlainText("既有保存筆記原文")
        notes.editor.setPlainText("尚未保存的觀察草稿")
        _wait_until(application, lambda: notes._snapshot is snapshot, timeout_ms=1000)
        assert view.member_table.rowCount() == 2
        assert view.metrics_table.rowCount() > 0
        assert view.ranking_table.rowCount() > 0
        assert view.stock_lookup_results.count() > 1
        assert view.chain_directory_group.isVisible()
        assert view.summary_group.isVisible()

        seen = _answer_confirmation(
            monkeypatch, QMessageBox.StandardButton.Yes
        )
        view.clear_research_button.click()

        assert len(seen) == 1
        assert "尚未保存" in seen[0][1]
        assert "已保存筆記與來源檔案不會刪除" in seen[0][1]
        assert view.snapshot is None
        assert events == [snapshot, None]
        assert notes._snapshot is None
        assert notes.editor.toPlainText() == ""
        assert notes.saved_text.toPlainText() == "既有保存筆記原文"
        assert view.chain_filter.currentIndex() == 0
        assert view.theme_filter.currentIndex() == 0
        assert view.metrics_table.rowCount() == 0
        assert view.member_table.rowCount() == 0
        assert view.ranking_table.rowCount() == 0
        assert view.ranking_type_combo.currentData() == "return"
        assert view.sorting_direction_combo.currentData() is False
        assert view.stock_lookup_input.text() == ""
        assert view.stock_lookup_results.count() == 1
        assert view.stock_lookup_results.currentData(Qt.ItemDataRole.UserRole) is None
        assert not view.chain_directory_button.isChecked()
        assert view.chain_directory_group.isHidden()
        assert not view._chain_directory_buttons
        assert view.summary_group.isHidden()
        assert not view.source_details_button.isChecked()
        assert not view.source_details_button.isEnabled()
        assert "尚未載入" in view.overview_label.text()
        assert "已清除" in view.status_label.text()
        assert not view.clear_research_button.isEnabled()
        assert view.open_snapshot_button.isEnabled()
        assert selected_stocks == []
    finally:
        view.shutdown()
        view.close()
        application.processEvents()


def test_new_snapshot_during_confirmation_is_not_cleared(monkeypatch):
    application = app()
    view = IndustryThemeMapView()
    notes = _attach_notes(view)
    newer = _snapshot("b" * 64)
    try:
        _show(view, application)
        view.set_snapshot(_snapshot())
        notes.editor.setPlainText("確認前草稿")
        def changed(*_args, **_kwargs):
            view.set_snapshot(newer)
            return QMessageBox.StandardButton.Yes
        monkeypatch.setattr(QMessageBox, "question", changed)
        assert view.clear_research() is False
        assert view.snapshot is newer
        assert "研究或筆記工作已改變" in view.status_label.text()
    finally:
        view.shutdown()
        view.close()
        application.processEvents()


def test_notes_busy_rejects_clear_without_touching_snapshot_or_draft(monkeypatch):
    application = app()
    view = IndustryThemeMapView()
    notes = _attach_notes(view)
    snapshot = _snapshot()
    events = []
    view.snapshotChanged.connect(events.append)
    try:
        _show(view, application)
        view.set_snapshot(snapshot)
        _select_ai(view)
        notes.editor.setPlainText("保留中的草稿")
        monkeypatch.setattr(notes, "is_busy", lambda: True)
        seen = _answer_confirmation(
            monkeypatch, QMessageBox.StandardButton.Yes
        )

        view.clear_research_button.click()

        assert seen == []
        assert view.snapshot is snapshot
        assert notes._snapshot is snapshot
        assert notes.editor.toPlainText() == "保留中的草稿"
        assert view.chain_filter.currentData() == "科技鏈"
        assert view.theme_filter.currentText() == "AI"
        assert events == [snapshot]
        assert "筆記工作進行中" in view.status_label.text()
    finally:
        view.shutdown()
        view.close()
        application.processEvents()


def test_declining_draft_confirmation_leaves_selection_and_context_unchanged(monkeypatch):
    application = app()
    view = IndustryThemeMapView()
    notes = _attach_notes(view)
    snapshot = _snapshot()
    events = []
    view.snapshotChanged.connect(events.append)
    try:
        _show(view, application)
        view.set_snapshot(snapshot)
        _select_ai(view)
        notes.editor.setPlainText("稍後再保存")
        generation = view._generation
        seen = _answer_confirmation(
            monkeypatch, QMessageBox.StandardButton.No
        )

        view.clear_research_button.click()

        assert len(seen) == 1
        assert view.snapshot is snapshot
        assert view._generation == generation
        assert notes._snapshot is snapshot
        assert notes.editor.toPlainText() == "稍後再保存"
        assert view.chain_filter.currentData() == "科技鏈"
        assert view.theme_filter.currentText() == "AI"
        assert events == [snapshot]
        assert "已取消清除" in view.status_label.text()
    finally:
        view.shutdown()
        view.close()
        application.processEvents()


def test_file_picker_cancel_keeps_current_research(monkeypatch):
    application = app()
    view = IndustryThemeMapView()
    snapshot = _snapshot()
    try:
        _show(view, application)
        view.set_snapshot(snapshot)
        _select_ai(view)
        generation = view._generation
        monkeypatch.setattr(
            view_module,
            "QFileDialog",
            SimpleNamespace(getOpenFileName=lambda *args, **kwargs: ("", "")),
        )

        view.open_snapshot_button.click()

        assert view.snapshot is snapshot
        assert view._generation == generation
        assert view.chain_filter.currentData() == "科技鏈"
        assert view.theme_filter.currentText() == "AI"
        assert view.member_table.rowCount() == 2
        assert view.clear_research_button.isEnabled()
    finally:
        view.shutdown()
        view.close()
        application.processEvents()


def test_clear_cancels_current_load_and_allows_reload_after_native_finish(monkeypatch):
    application = app()
    view = IndustryThemeMapView()
    first_snapshot = _snapshot("b" * 64)
    second_snapshot = _snapshot("c" * 64)
    started = threading.Event()
    release = threading.Event()
    native_finished = []
    calls = []

    def delayed_reader(path: Path):
        calls.append(path)
        if len(calls) == 1:
            started.set()
            if not release.wait(3):
                raise TimeoutError("測試讀取未收到釋放")
            return first_snapshot
        return second_snapshot

    monkeypatch.setattr(view_module, "read_theme_research_snapshot", delayed_reader)
    events = []
    view.snapshotChanged.connect(events.append)
    try:
        _show(view, application)
        view.load_snapshot(Path("delayed-manifest.json"))
        _wait_until(application, started.is_set, timeout_ms=1000)
        worker = view._worker
        assert worker is not None
        worker.native_thread_finished.connect(lambda: native_finished.append(True))
        assert view.clear_research_button.isEnabled()

        view.clear_research_button.click()

        assert worker.is_cancel_requested()
        assert view.is_busy()
        assert view.snapshot is None
        assert not view.clear_research_button.isEnabled()
        assert not view.open_snapshot_button.isEnabled()
        release.set()
        _wait_until(
            application,
            lambda: not view.is_busy() and bool(native_finished),
            timeout_ms=3000,
        )
        assert view.snapshot is None
        assert events == [None, None]
        assert "背景讀取已停止" in view.status_label.text()

        view.load_snapshot(Path("replacement-manifest.json"))
        _wait_until(application, lambda: not view.is_busy(), timeout_ms=3000)
        assert view.snapshot is second_snapshot
        assert calls == [
            Path("delayed-manifest.json"),
            Path("replacement-manifest.json"),
        ]
    finally:
        release.set()
        if view.is_busy():
            _wait_until(application, lambda: not view.is_busy(), timeout_ms=3000)
        view.shutdown()
        view.close()
        application.processEvents()


def test_late_reader_result_cannot_restore_cleared_snapshot(monkeypatch):
    application = app()
    view = IndustryThemeMapView()
    late_snapshot = _snapshot("d" * 64)
    started = threading.Event()
    release = threading.Event()
    native_finished = []
    cancel_requests = []

    def delayed_reader(_path: Path):
        started.set()
        if not release.wait(3):
            raise TimeoutError("測試讀取未收到釋放")
        return late_snapshot

    monkeypatch.setattr(view_module, "read_theme_research_snapshot", delayed_reader)
    events = []
    view.snapshotChanged.connect(events.append)
    try:
        _show(view, application)
        view.load_snapshot(Path("late-manifest.json"))
        _wait_until(application, started.is_set, timeout_ms=1000)
        worker = view._worker
        assert worker is not None
        worker.native_thread_finished.connect(lambda: native_finished.append(True))

        def deferred_cancel(*, cooperative=True, wait=False):
            cancel_requests.append((cooperative, wait))

        monkeypatch.setattr(worker, "cancel", deferred_cancel)
        view.clear_research_button.click()
        assert cancel_requests == [(True, False)]
        release.set()
        _wait_until(
            application,
            lambda: not view.is_busy() and bool(native_finished),
            timeout_ms=3000,
        )

        assert view.snapshot is None
        assert view._result is None
        assert events == [None, None]
        assert "背景讀取已停止" in view.status_label.text()
    finally:
        release.set()
        if view.is_busy():
            _wait_until(application, lambda: not view.is_busy(), timeout_ms=3000)
        view.shutdown()
        view.close()
        application.processEvents()
