"""真 MainWindow 保存→觀察清單原版本重開→摘要→返回旅程。"""

from dataclasses import replace
from pathlib import Path

import pytest
from PySide6.QtCore import Qt

from app_module.recommendation.personal_h20_activation import publish_personal_h20_activation
from tests.test_ui_qt_personal_h20_mainwindow_saved_journey import (
    _prepare_saved_h20_mainwindow, _load_h20_list, _wait_for, _close_mainwindow,
)


def _save_and_find(app, window):
    widget = _load_h20_list(app, window)
    service = window.watchlist_service
    assert service is not None
    assert service.upgrade_to_repository().is_repository
    widget.table.selectRow(0)
    widget.table.setCurrentCell(0, 0)
    widget.bookmark_button.click()
    _wait_for(app, lambda: not widget._bookmark_busy)
    rows = [row for row in service.get_stocks() if row.get("source") == "personal_h20_research_bookmark"]
    assert len(rows) == 1, widget.bookmark_status_label.text()
    bookmark_id = rows[0]["source_id"]
    window.left_navigation.button_for_key("watchlist").click()
    controls = window.watchlist_view.personal_h20_bookmark_controls
    assert controls is not None
    controls.refresh_bookmarks()
    _wait_for(app, lambda: controls._worker is None and controls.bookmarks.count() == 1)
    assert controls.restore_selection(bookmark_id) == "selected"
    return service, controls, bookmark_id


@pytest.mark.parametrize("disabled", [False, True])
def test_actual_mainwindow_reopens_original_h20_bookmark_and_returns_exactly(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, disabled: bool):
    app, window, saved, network, _ = _prepare_saved_h20_mainwindow(tmp_path, monkeypatch)
    before = Path(saved["snapshot_database"]).read_bytes()
    try:
        window.show()
        service, controls, bookmark_id = _save_and_find(app, window)
        if disabled:
            publish_personal_h20_activation(
                replace(saved["activation"], revision=2, enabled=False), expected_revision=1, execute=True,
            )
        controls.open_button.click()
        workspace = window.stock_research_workspace
        _wait_for(app, lambda: workspace.personal_h20_saved_evidence is not None
            and workspace.report_view.context is not None
            and workspace.report_view.context.source_kind == "personal_h20_research_bookmark")
        evidence = workspace.personal_h20_saved_evidence
        assert evidence is not None and evidence.status == "available"
        assert evidence.stock_code == "2382" and evidence.gross_return_bp == 1234
        assert workspace.report_view.context.source_id == bookmark_id
        assert "+12.34%" in workspace.personal_h20_saved_summary.text()
        if disabled:
            assert "目前個人模型停用" in workspace.personal_h20_saved_summary.text()

        # 再次收到同一個已核 bookmark state 時，已載入的精確報告也要更新摘要。
        report_view = workspace.report_view
        _wait_for(app, lambda: report_view._loaded_report is not None
            and report_view._loaded_request_context == report_view.context)
        report_view._personal_h20_evidence = None
        window._handle_personal_h20_bookmark_context(report_view.context)
        assert report_view._personal_h20_evidence is not None
        assert report_view._personal_h20_evidence.status == "available"
        assert report_view._personal_h20_evidence.gross_return_bp == 1234
        workspace.report_view.return_button.click()
        _wait_for(app, lambda: controls._worker is None)
        entry = controls.bookmarks.currentItem()
        assert entry is not None
        assert entry.data(Qt.ItemDataRole.UserRole).bookmark_id == bookmark_id
        assert len(service.get_stocks()) == 1
        assert Path(saved["snapshot_database"]).read_bytes() == before
        assert network == []
    finally:
        _close_mainwindow(app, window)


def test_deleted_bookmark_return_cannot_select_another_same_stock_source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    app, window, _saved, network, _ = _prepare_saved_h20_mainwindow(tmp_path, monkeypatch)
    try:
        window.show()
        service, controls, bookmark_id = _save_and_find(app, window)
        controls.open_button.click()
        workspace = window.stock_research_workspace
        _wait_for(app, lambda: workspace.personal_h20_saved_evidence is not None
            and workspace.report_view.context is not None
            and workspace.report_view.context.source_kind == "personal_h20_research_bookmark")
        assert service.remove_research_bookmark(bookmark_id).status == "removed"
        assert service.add_stocks([{"stock_code": "2382", "stock_name": "同股其他來源"}], source="manual") == 1
        workspace.report_view.return_button.click()
        _wait_for(app, lambda: controls._worker is None)
        assert controls.bookmarks.currentItem() is None
        assert controls.bookmarks.count() == 0
        assert "沒有改選其他列" in controls.status_label.text()
        assert network == []
    finally:
        _close_mainwindow(app, window)


def test_historical_recheck_rejects_source_drift_without_using_current_prediction(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    app, window, saved, network, _ = _prepare_saved_h20_mainwindow(tmp_path, monkeypatch)
    try:
        window.show()
        _service, controls, bookmark_id = _save_and_find(app, window)
        controls.open_button.click()
        workspace = window.stock_research_workspace
        _wait_for(app, lambda: workspace.personal_h20_saved_evidence is not None
            and workspace.report_view.context is not None
            and workspace.report_view.context.source_kind == "personal_h20_research_bookmark")
        _wait_for(app, lambda: controls._worker is None)
        assert workspace.personal_h20_saved_evidence.status == "available"
        source = Path(saved["snapshot_database"])
        source.write_bytes(source.read_bytes() + b"synthetic-history-source-drift")
        workspace.personal_h20_saved_recheck_button.click()
        _wait_for(app, lambda: getattr(window, "_personal_h20_worker", None) is None)
        evidence = workspace.personal_h20_saved_evidence
        assert evidence is not None and evidence.status == "unavailable"
        assert evidence.gross_return_bp is None
        assert "+12.34%" not in workspace.personal_h20_saved_summary.text()
        assert workspace.report_view.context.source_id == bookmark_id
        assert network == []
    finally:
        _close_mainwindow(app, window)
