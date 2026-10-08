"""真 public H20 reader 與 Main 方法的同次檢視旅程。"""
from pathlib import Path
from types import MethodType
import threading

import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from ui_qt.main import MainWindow
from tests.test_personal_h20_verified_cohort_view import _saved_store
from tests.test_ui_qt_h20_saved_source_journey import (
    _MainWindowJourneyHarness, _app, _close_harness, _real_report_service, _wait_until,
)


def test_main_initial_double_click_return_and_explicit_recheck_use_exact_view(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """一般下鑽/返回只一份副本，明確重驗才啟動第二次完整讀取。"""
    from scripts.scheduled.personal_h20_sqlite_read_operation import PersonalH20SQLiteReadOperation

    app = _app()
    saved, private_root = _saved_store(tmp_path, monkeypatch)
    operations = []
    original_finish = PersonalH20SQLiteReadOperation.finish
    def finish(self):
        bindings = original_finish(self)
        operations.append(bindings)
        return bindings
    monkeypatch.setattr(PersonalH20SQLiteReadOperation, "finish", finish)
    service = _real_report_service(saved["snapshot_database"], tmp_path / "report-output", fail_clock=True)
    window = _MainWindowJourneyHarness(saved["market_root"], service)
    window.config.personal_h20_sqlite_read_root = private_root
    for name in ("_personal_h20_sqlite_read_root", "_return_to_verified_personal_h20_view", "_return_to_research_source"):
        setattr(window, name, MethodType(getattr(MainWindow, name), window))
    window.show()
    app.processEvents()
    try:
        tabs = window.recommendation_view.result_source_tabs
        tabs.setCurrentWidget(window.personal_h20_research_panel)
        widget = window.personal_h20_research_widget
        _wait_until(lambda: getattr(window, "_personal_h20_cohort_worker", None) is None and widget._cohort is not None)
        first_view = window._personal_h20_cohort_view
        assert len(operations) == 1
        assert "核驗完成時間" in window._personal_h20_loading_label.text()
        widget.table.selectRow(0)
        app.processEvents()
        rect = widget.table.visualItemRect(widget.table.item(0, 0))
        assert rect.isValid()
        QTest.mouseClick(widget.table.viewport(), Qt.LeftButton, pos=rect.center())
        app.processEvents()
        QTest.mouseDClick(widget.table.viewport(), Qt.LeftButton, pos=rect.center(), delay=50)
        app.processEvents()
        assert window._personal_h20_research_origin is not None, widget.summary_label.text()
        _wait_until(lambda: getattr(window, "_personal_h20_saved_evidence", None) is not None
            and getattr(window, "_personal_h20_worker", None) is None)
        evidence = window._personal_h20_saved_evidence
        assert evidence.status == "available" and evidence.gross_return_bp == 1234
        assert len(operations) == 1
        context = window._personal_h20_research_origin[0]
        selection = window._personal_h20_research_origin[1]
        original_cohort = widget._cohort
        window._return_to_research_source(context)
        _wait_until(lambda: getattr(window, "_personal_h20_return_worker", None) is None)
        assert window._personal_h20_cohort_view is first_view
        assert widget._cohort is original_cohort
        assert widget.restore_selection(selection)
        assert len(operations) == 1
        window._recheck_personal_h20_saved_evidence()
        _wait_until(lambda: getattr(window, "_personal_h20_cohort_worker", None) is None
            and getattr(window, "_personal_h20_worker", None) is None
            and getattr(window, "_personal_h20_saved_evidence", None) is not None)
        assert len(operations) == 2
        assert window._personal_h20_cohort_view.view_id != first_view.view_id
        assert window._personal_h20_saved_evidence.gross_return_bp == 1234
        assert not list(private_root.iterdir())
    finally:
        _close_harness(window)


def test_main_return_late_result_does_not_restore_selection_after_context_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """小型 reference worker 晚到不能更新已離開的研究頁。"""
    from scripts.scheduled import personal_h20_daily_hook as hook
    app = _app()
    saved, private_root = _saved_store(tmp_path, monkeypatch)
    window = _MainWindowJourneyHarness(saved["market_root"],
        _real_report_service(saved["snapshot_database"], tmp_path / "report-output", fail_clock=True))
    window.config.personal_h20_sqlite_read_root = private_root
    for name in ("_personal_h20_sqlite_read_root", "_return_to_verified_personal_h20_view", "_return_to_research_source"):
        setattr(window, name, MethodType(getattr(MainWindow, name), window))
    entered, release = threading.Event(), threading.Event()
    window.show()
    app.processEvents()
    try:
        window.recommendation_view.result_source_tabs.setCurrentWidget(window.personal_h20_research_panel)
        widget = window.personal_h20_research_widget
        _wait_until(lambda: getattr(window, "_personal_h20_cohort_worker", None) is None and widget._cohort is not None)
        widget.table.selectRow(0)
        widget.research_button.click()
        _wait_until(lambda: getattr(window, "_personal_h20_saved_evidence", None) is not None
            and getattr(window, "_personal_h20_worker", None) is None)
        original_projection = hook.project_personal_h20_verified_cohort_selection_with_reference
        def blocked(*args, **kwargs):
            result = original_projection(*args, **kwargs)
            entered.set()
            assert release.wait(10)
            return result
        monkeypatch.setattr(hook, "project_personal_h20_verified_cohort_selection_with_reference", blocked)
        window._return_to_research_source(window._personal_h20_research_origin[0])
        _wait_until(entered.is_set)
        restored = []
        monkeypatch.setattr(widget, "restore_selection", lambda selection: restored.append(selection) or True)
        window._clear_personal_h20_product()
        release.set()
        _wait_until(lambda: getattr(window, "_personal_h20_return_worker", None) is None)
        assert restored == []
        assert "已返回原保存名單" not in window.statusBar().currentMessage()
        assert widget.isEnabled()
    finally:
        release.set()
        _wait_until(lambda: getattr(window, "_personal_h20_return_worker", None) is None)
        _close_harness(window)


@pytest.mark.parametrize("change", ["read_root_changed", "missing_root", "force_navigation_changed"])
def test_main_stale_full_read_preserves_view_and_releases_busy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: str,
) -> None:
    """完整 reader 完成後的受控 barrier 重現設定/導航變動。"""
    from scripts.scheduled import personal_h20_daily_hook as hook
    app = _app()
    saved, private_root = _saved_store(tmp_path, monkeypatch)
    service = _real_report_service(saved["snapshot_database"], tmp_path / "report-output", fail_clock=True)
    window = _MainWindowJourneyHarness(saved["market_root"], service)
    window.config.personal_h20_sqlite_read_root = private_root
    window._personal_h20_sqlite_read_root = MethodType(MainWindow._personal_h20_sqlite_read_root, window)
    entered, release = threading.Event(), threading.Event()
    window.show()
    app.processEvents()
    try:
        window.recommendation_view.result_source_tabs.setCurrentWidget(window.personal_h20_research_panel)
        widget = window.personal_h20_research_widget
        _wait_until(lambda: getattr(window, "_personal_h20_cohort_worker", None) is None and widget._cohort is not None)
        original_view, original_cohort = window._personal_h20_cohort_view, widget._cohort
        if change == "force_navigation_changed":
            widget.table.selectRow(0)
            widget.research_button.click()
            _wait_until(lambda: getattr(window, "_personal_h20_saved_evidence", None) is not None
                and getattr(window, "_personal_h20_worker", None) is None)
        original_reader = hook.read_personal_h20_verified_cohort_view
        def blocked_reader(*args, **kwargs):
            result = original_reader(*args, **kwargs)
            entered.set()
            assert release.wait(10), "測試 barrier 必須釋放"
            return result
        monkeypatch.setattr(hook, "read_personal_h20_verified_cohort_view", blocked_reader)
        if change == "force_navigation_changed":
            window._recheck_personal_h20_saved_evidence()
        else:
            window._refresh_personal_h20_cohort()
        _wait_until(entered.is_set)
        assert not widget.isEnabled()
        if change == "missing_root":
            window.config.personal_h20_sqlite_read_root = None
            window._refresh_personal_h20_cohort()
        elif change == "read_root_changed":
            new_root = tmp_path / "another-private-root"
            new_root.mkdir()
            window.config.personal_h20_sqlite_read_root = new_root
        else:
            window._clear_personal_h20_product()
            window._select_workspace("recommendation")
        release.set()
        _wait_until(lambda: getattr(window, "_personal_h20_cohort_worker", None) is None)
        assert window._personal_h20_cohort_view is original_view
        assert widget._cohort is original_cohort
        assert widget.isEnabled()
        assert not window._personal_h20_loading_timer.isActive()
        assert not window._personal_h20_cancel_read_button.isEnabled()
        if change == "force_navigation_changed":
            assert window._selected_workspace == "recommendation"
    finally:
        release.set()
        _wait_until(lambda: getattr(window, "_personal_h20_cohort_worker", None) is None)
        _close_harness(window)


@pytest.mark.parametrize("failure_kind", ["reader", "selection_restore"])
def test_main_explicit_recheck_failure_is_terminal_and_retryable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure_kind: str,
) -> None:
    """重驗失敗不得永久顯示 loading 或讓上次預測冒充新結果。"""
    from scripts.scheduled import personal_h20_daily_hook as hook
    app = _app()
    saved, private_root = _saved_store(tmp_path, monkeypatch)
    window = _MainWindowJourneyHarness(saved["market_root"],
        _real_report_service(saved["snapshot_database"], tmp_path / "report-output", fail_clock=True))
    window.config.personal_h20_sqlite_read_root = private_root
    window._personal_h20_sqlite_read_root = MethodType(MainWindow._personal_h20_sqlite_read_root, window)
    window.show()
    app.processEvents()
    try:
        window.recommendation_view.result_source_tabs.setCurrentWidget(window.personal_h20_research_panel)
        widget = window.personal_h20_research_widget
        _wait_until(lambda: getattr(window, "_personal_h20_cohort_worker", None) is None and widget._cohort is not None)
        original_view = window._personal_h20_cohort_view
        widget.table.selectRow(0)
        widget.research_button.click()
        _wait_until(lambda: getattr(window, "_personal_h20_saved_evidence", None) is not None
            and getattr(window, "_personal_h20_worker", None) is None)
        def fail(*_args, **_kwargs):
            raise ValueError("synthetic_original_source_recheck_failed")
        if failure_kind == "reader":
            monkeypatch.setattr(hook, "read_personal_h20_verified_cohort_view", fail)
        else:
            monkeypatch.setattr(widget, "restore_selection", lambda _selection: False)
        window._recheck_personal_h20_saved_evidence()
        _wait_until(lambda: getattr(window, "_personal_h20_cohort_worker", None) is None)
        workspace = window.stock_research_workspace
        if failure_kind == "reader":
            assert window._personal_h20_cohort_view is original_view
        else:
            assert window._personal_h20_cohort_view.reference == original_view.reference
        assert window._personal_h20_saved_evidence.status == "unavailable"
        expected_reason = ("synthetic_original_source_recheck_failed" if failure_kind == "reader"
            else "saved_h20_full_recheck_selection_restore_failed")
        assert expected_reason in window._personal_h20_saved_evidence.reason
        assert not workspace.personal_h20_saved_busy
        assert workspace.personal_h20_saved_recheck_button.isEnabled()
        assert widget.isEnabled()
        assert not window._personal_h20_loading_timer.isActive()
    finally:
        _close_harness(window)
