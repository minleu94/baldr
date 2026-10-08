"""真 MainWindow 的 H20 名單、下鑽、取消與精確返回整合測試。

所有來源均由隔離合成 fixture 建立，沿產品 public reader 與 typed sealed view；
不以 tuple/object 假造核驗結果，也不讀正式資料或啟動模型。
"""

from __future__ import annotations

import os
from pathlib import Path
import threading
from typing import Any

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget

from app_module.recommendation.personal_h20_research_cohort import (
    PersonalH20ResearchSelection,
)
from app_module.recommendation.personal_h20_verified_cohort_view import (
    PersonalH20VerifiedCohortView,
)
from tests.test_ui_qt_personal_h20_mainwindow_saved_journey import (
    _close_mainwindow,
    _double_click_selected_h20_row,
    _load_h20_list,
    _prepare_saved_h20_mainwindow,
    _wait_for,
)


def _selected_h20_selection(widget: Any) -> PersonalH20ResearchSelection:
    row_index = widget.table.currentRow()
    if row_index < 0:
        selected = widget.table.selectedItems()
        row_index = selected[0].row() if selected else 0
    item = widget.table.item(row_index, 0)
    assert item is not None
    selection = item.data(Qt.ItemDataRole.UserRole)
    assert type(selection) is PersonalH20ResearchSelection
    return selection


def _wait_for_cohort_worker(app: Any, window: Any) -> None:
    _wait_for(
        app,
        lambda: getattr(window, "_personal_h20_cohort_worker", None) is None,
        timeout_seconds=90.0,
    )


def test_main_mount_exact_drilldown_and_return_reuses_verified_view(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mode: dict[str, Any] = {}
    app, window, saved, network_attempts, _task_context = _prepare_saved_h20_mainwindow(
        tmp_path, monkeypatch, source_mode=mode
    )
    source_path = Path(saved["snapshot_database"])
    source_bytes = source_path.read_bytes()
    try:
        window.show()
        app.processEvents()
        widget = _load_h20_list(app, window)
        assert type(window._personal_h20_cohort_view) is PersonalH20VerifiedCohortView
        assert mode.get("_cohort_operation_count") == 1
        assert widget.summary_label.text().startswith("已保存 H20 研究母體：1 列")

        signals = _double_click_selected_h20_row(app, window, widget)
        workspace = window.stock_research_workspace
        assert workspace is not None
        report_view = workspace.report_view
        _wait_for(
            app,
            lambda: getattr(report_view.context, "source_kind", None)
            == "personal_h20_saved_cohort"
            and getattr(workspace.personal_h20_saved_evidence, "status", None)
            == "available"
            and getattr(window, "_personal_h20_worker", None) is None
            and not workspace.personal_h20_saved_busy,
        )
        evidence = workspace.personal_h20_saved_evidence
        assert evidence is not None
        assert signals["research_requested"]
        assert evidence.stock_code == "2382"
        assert evidence.gross_return_bp == 1234
        assert "+12.34%" in workspace.personal_h20_saved_summary.text()
        assert mode.get("_cohort_operation_count") == 1
        assert mode.get("_product_operation_count", 0) == 0

        selection = window._personal_h20_research_origin[1]
        report_view.return_button.click()
        _wait_for(
            app,
            lambda: getattr(window, "_personal_h20_return_worker", None) is None
            and window.recommendation_view.result_source_tabs.currentWidget()
            is window.personal_h20_research_panel
            and widget.isEnabled()
            and bool(widget.table.selectedItems()),
        )
        row_index = widget.table.currentRow()
        item = widget.table.item(row_index, 0)
        assert item is not None and item.text() == "2382"
        assert item.data(Qt.ItemDataRole.UserRole) == selection
        assert mode.get("_cohort_operation_count") == 1
        assert mode.get("_warm_projection_count") == 2
        assert network_attempts == []
    finally:
        _close_mainwindow(app, window)
    assert source_path.read_bytes() == source_bytes


def test_stale_configuration_and_missing_capture_never_publish_old_selection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entered = threading.Event()
    release = threading.Event()
    mode: dict[str, Any] = {"block_cohort_operation_before": 2}
    app, window, saved, network_attempts, _task_context = _prepare_saved_h20_mainwindow(
        tmp_path,
        monkeypatch,
        source_mode=mode,
        source_entered=entered,
        source_release=release,
    )
    snapshot_path = Path(saved["snapshot_database"])
    snapshot_before = snapshot_path.read_bytes()
    capture_path = Path(saved["saved_capture"]["path"])
    capture_bytes = capture_path.read_bytes()
    try:
        window.show()
        app.processEvents()
        widget = _load_h20_list(app, window)
        original_view = window._personal_h20_cohort_view
        original_cohort = widget._cohort
        assert type(original_view) is PersonalH20VerifiedCohortView

        window._personal_h20_refresh_button.click()
        _wait_for(app, entered.is_set)
        worker = window._personal_h20_cohort_worker
        assert worker is not None and worker.isRunning()
        monkeypatch.setenv(
            "PERSONAL_H20_ACTIVATION_CONFIG", str(tmp_path / "changed-activation.json")
        )
        release.set()
        _wait_for_cohort_worker(app, window)
        assert window._personal_h20_cohort_view is original_view
        assert widget._cohort is original_cohort
        assert "過期" in window._personal_h20_loading_label.text()
        assert mode.get("_cohort_operation_count") == 2

        # 恢復設定後先用當次已核 view 正常下鑽，再刪除合成 capture，明確要求
        # 完整重核並嘗試恢復原選取；reader 應保留未知列且拒絕研究選取。
        monkeypatch.setenv(
            "PERSONAL_H20_ACTIVATION_CONFIG", str(saved["activation"].config_path)
        )
        signals = _double_click_selected_h20_row(app, window, widget)
        assert signals["research_requested"]
        workspace = window.stock_research_workspace
        assert workspace is not None
        _wait_for(
            app,
            lambda: getattr(workspace.personal_h20_saved_evidence, "status", None)
            == "available"
            and getattr(window, "_personal_h20_worker", None) is None
            and not workspace.personal_h20_saved_busy,
        )
        selection = window._personal_h20_research_origin[1]
        capture_path.unlink()
        window._refresh_personal_h20_cohort(selection, open_research=True)
        _wait_for(
            app,
            lambda: getattr(window, "_personal_h20_cohort_worker", None) is None
            and getattr(workspace.personal_h20_saved_evidence, "status", None)
            == "unavailable"
            and not workspace.personal_h20_saved_busy,
        )
        evidence = workspace.personal_h20_saved_evidence
        assert evidence is not None and evidence.reason
        assert widget._cohort is not None and widget._cohort.rows[0].status == "unknown"
        assert "+12.34%" not in workspace.personal_h20_saved_summary.text()
        assert mode.get("_cohort_operation_count") == 3
        assert network_attempts == []
    finally:
        release.set()
        if capture_path.parent.is_dir() and not capture_path.exists():
            capture_path.write_bytes(capture_bytes)
        _close_mainwindow(app, window)
    assert snapshot_path.read_bytes() == snapshot_before


def test_cancel_waits_for_native_cohort_reader_and_allows_retry_after_finish(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entered = threading.Event()
    release = threading.Event()
    mode: dict[str, Any] = {"block_cohort_operation_before": 2}
    app, window, _saved, network_attempts, _task_context = _prepare_saved_h20_mainwindow(
        tmp_path,
        monkeypatch,
        source_mode=mode,
        source_entered=entered,
        source_release=release,
    )
    try:
        window.show()
        app.processEvents()
        widget = _load_h20_list(app, window)
        original_view = window._personal_h20_cohort_view
        selection = _selected_h20_selection(widget)

        window._personal_h20_refresh_button.click()
        _wait_for(app, entered.is_set)
        worker = window._personal_h20_cohort_worker
        assert worker is not None and worker.isRunning()
        assert widget.isEnabled() is False
        assert window._personal_h20_refresh_button.isEnabled() is False

        # busy期間的重複 refresh 和下鑽請求都不可建立第二個 operation。
        window._refresh_personal_h20_cohort()
        window._request_personal_h20_research(selection)
        assert window._personal_h20_cohort_worker is worker
        assert mode.get("_cohort_operation_count") == 2
        assert window._personal_h20_research_origin is None

        window._personal_h20_cancel_read_button.click()
        assert worker.is_cancel_requested()
        assert worker.isRunning()
        assert widget.isEnabled() is False
        assert window._personal_h20_refresh_button.isEnabled() is False
        assert "已送出取消" in window._personal_h20_loading_label.text()
        assert window._personal_h20_cohort_view is original_view

        release.set()
        _wait_for_cohort_worker(app, window)
        assert window._personal_h20_cohort_view is original_view
        assert widget._cohort is original_view.cohort
        assert "名單讀取已取消" in window._personal_h20_loading_label.text()
        assert widget.isEnabled() and window._personal_h20_refresh_button.isEnabled()

        window._personal_h20_refresh_button.click()
        _wait_for(
            app,
            lambda: getattr(window, "_personal_h20_cohort_worker", None) is None
            and window._personal_h20_cohort_view is not original_view,
        )
        assert type(window._personal_h20_cohort_view) is PersonalH20VerifiedCohortView
        assert mode.get("_cohort_operation_count") == 3
        assert network_attempts == []
    finally:
        release.set()
        _close_mainwindow(app, window)


def test_close_during_cohort_read_discards_result_until_worker_finishes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entered = threading.Event()
    release = threading.Event()
    mode: dict[str, Any] = {"block_cohort_operation_before": 2}
    app, window, _saved, network_attempts, _task_context = _prepare_saved_h20_mainwindow(
        tmp_path,
        monkeypatch,
        source_mode=mode,
        source_entered=entered,
        source_release=release,
    )
    try:
        window.show()
        app.processEvents()
        widget = _load_h20_list(app, window)
        original_view = window._personal_h20_cohort_view

        window._personal_h20_refresh_button.click()
        _wait_for(app, entered.is_set)
        worker = window._personal_h20_cohort_worker
        assert worker is not None and worker.isRunning()
        window.close()
        _wait_for(app, worker.is_cancel_requested)
        release.set()
        _wait_for(app, lambda: not window.isVisible())
        _wait_for(app, lambda: getattr(window, "_personal_h20_cohort_worker", None) is None)
        assert window._personal_h20_cohort_view is original_view
        assert widget._cohort is original_view.cohort
        assert mode.get("_cohort_operation_count") == 2
        assert network_attempts == []
    finally:
        release.set()
        _close_mainwindow(app, window)


def test_return_from_other_result_tab_restores_exact_h20_selection_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mode: dict[str, Any] = {}
    app, window, _saved, network_attempts, _task_context = _prepare_saved_h20_mainwindow(
        tmp_path, monkeypatch, source_mode=mode
    )
    try:
        window.show()
        app.processEvents()
        widget = _load_h20_list(app, window)
        _double_click_selected_h20_row(app, window, widget)
        workspace = window.stock_research_workspace
        assert workspace is not None
        report_view = workspace.report_view
        _wait_for(
            app,
            lambda: getattr(report_view.context, "source_kind", None)
            == "personal_h20_saved_cohort"
            and getattr(window, "_personal_h20_worker", None) is None
            and not workspace.personal_h20_saved_busy,
        )
        selection = window._personal_h20_research_origin[1]

        tabs = window.recommendation_view.result_source_tabs
        other_result = QWidget(window.recommendation_view)
        other_index = tabs.addTab(other_result, "其他研究結果")
        tabs.setCurrentIndex(other_index)
        app.processEvents()
        assert tabs.currentWidget() is other_result
        assert mode.get("_cohort_operation_count") == 1

        report_view.return_button.click()
        _wait_for(
            app,
            lambda: getattr(window, "_personal_h20_return_worker", None) is None
            and widget.isEnabled()
            and bool(widget.table.selectedItems()),
        )
        assert tabs.currentWidget() is window.personal_h20_research_panel
        item = widget.table.item(widget.table.currentRow(), 0)
        assert item is not None and item.text() == "2382"
        assert item.data(Qt.ItemDataRole.UserRole) == selection
        assert mode.get("_cohort_operation_count") == 1
        assert mode.get("_warm_projection_count") == 2
        assert network_attempts == []
    finally:
        _close_mainwindow(app, window)


def test_busy_unknown_missing_reference_and_shutdown_keep_research_disabled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mode: dict[str, Any] = {}
    app, window, saved, network_attempts, _task_context = _prepare_saved_h20_mainwindow(
        tmp_path, monkeypatch, source_mode=mode
    )
    capture_path = Path(saved["saved_capture"]["path"])
    capture_bytes = capture_path.read_bytes()
    try:
        window.show()
        app.processEvents()
        widget = _load_h20_list(app, window)
        valid_selection = _selected_h20_selection(widget)

        widget.setEnabled(False)
        window._request_personal_h20_research(valid_selection)
        assert window._personal_h20_research_origin is None
        widget.setEnabled(True)

        reference = window._personal_h20_cohort_reference
        window._personal_h20_cohort_reference = None
        window._request_personal_h20_research(valid_selection)
        assert window._personal_h20_research_origin is None
        window._personal_h20_cohort_reference = reference

        window._shutdown_close_requested = True
        window._request_personal_h20_research(valid_selection)
        assert window._personal_h20_research_origin is None
        window._shutdown_close_requested = False

        # 刪除隔離 fixture 的 exact capture 後重新走完整 public reader；未知列
        # 仍保留在分母與表格，但選取研究與 bookmark 操作均停用。
        capture_path.unlink()
        original_view = window._personal_h20_cohort_view
        window._personal_h20_refresh_button.click()
        _wait_for(
            app,
            lambda: getattr(window, "_personal_h20_cohort_worker", None) is None
            and getattr(window, "_personal_h20_cohort_view", None)
            is not None
            and window._personal_h20_cohort_view is not original_view,
        )
        cohort = widget._cohort
        assert cohort is not None and len(cohort.rows) == 1
        assert cohort.rows[0].status == "unknown"
        assert cohort.rows[0].reason
        assert "可研究 0 列" in widget.summary_label.text()
        assert "未知 1 列" in widget.summary_label.text()
        assert "可研究 0 列、未知 1 列" in window._personal_h20_loading_label.text()

        widget.table.selectRow(0)
        app.processEvents()
        unknown_selection = _selected_h20_selection(widget)
        assert widget.research_button.isEnabled() is False
        assert widget.bookmark_button.isEnabled() is False
        window._request_personal_h20_research(unknown_selection)
        assert window._personal_h20_research_origin is None
        assert mode.get("_cohort_operation_count") == 2
        assert network_attempts == []
    finally:
        if capture_path.parent.is_dir() and not capture_path.exists():
            capture_path.write_bytes(capture_bytes)
        _close_mainwindow(app, window)
