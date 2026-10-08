"""真 MainWindow 收藏按鈕、背景核驗與合成 COW 保存旅程。"""

from pathlib import Path
import threading

import pytest
from PySide6.QtCore import Qt

from app_module.recommendation.personal_h20_research_bookmark import PersonalH20ResearchBookmark
from tests.test_ui_qt_personal_h20_mainwindow_saved_journey import (
    _prepare_saved_h20_mainwindow, _load_h20_list, _wait_for, _close_mainwindow,
)


def test_actual_mainwindow_button_saves_exact_h20_bookmark_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app, window, saved, network, _ = _prepare_saved_h20_mainwindow(tmp_path, monkeypatch)
    source = Path(saved["snapshot_database"])
    before = source.read_bytes()
    try:
        window.show()
        widget = _load_h20_list(app, window)
        service = window.watchlist_service
        assert service is not None
        assert service.upgrade_to_repository().is_repository
        widget.table.selectRow(0)
        widget.table.setCurrentCell(0, 0)
        assert widget.bookmark_button.isEnabled()
        for _attempt in range(2):
            widget.bookmark_button.click()
            assert widget._bookmark_busy
            _wait_for(app, lambda: not widget._bookmark_busy)
            rows = [row for row in service.get_stocks() if row.get("source") == "personal_h20_research_bookmark"]
            assert len(rows) == 1, widget.bookmark_status_label.text()
            bookmark = service.get_research_bookmark(rows[0]["source_id"])
            assert isinstance(bookmark, PersonalH20ResearchBookmark)
            assert bookmark.stock_code == "2382"
            assert bookmark.manifest_sha256 == saved["manifest_sha256"]
            item = widget.table.item(0, 0)
            assert item is not None
            assert bookmark.selected_row == item.data(Qt.ItemDataRole.UserRole)
        assert source.read_bytes() == before
        assert network == []
    finally:
        _close_mainwindow(app, window)


def test_source_changed_before_save_keeps_watchlist_unchanged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app, window, saved, network, _ = _prepare_saved_h20_mainwindow(tmp_path, monkeypatch)
    try:
        window.show()
        widget = _load_h20_list(app, window)
        service = window.watchlist_service
        assert service is not None
        assert service.upgrade_to_repository().is_repository
        original_rows = service.get_stocks()
        source = Path(saved["snapshot_database"])
        source.write_bytes(source.read_bytes() + b"synthetic-source-drift")
        widget.table.selectRow(0)
        widget.table.setCurrentCell(0, 0)
        widget.bookmark_button.click()
        _wait_for(app, lambda: not widget._bookmark_busy)
        assert service.get_stocks() == original_rows
        assert "未保存收藏" in widget.bookmark_status_label.text()
        assert network == []
    finally:
        _close_mainwindow(app, window)


@pytest.mark.parametrize("change", ["selection", "config_unavailable"])
def test_selection_changed_during_prepare_never_writes_bookmark(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: str,
) -> None:
    import scripts.scheduled.personal_h20_bookmark_prepare as prepare_module
    app, window, _saved, network, _ = _prepare_saved_h20_mainwindow(tmp_path, monkeypatch)
    entered, release = threading.Event(), threading.Event()
    original = prepare_module.read_personal_h20_product_cohort

    def barrier(*args, **kwargs):
        entered.set()
        assert release.wait(30)
        return original(*args, **kwargs)

    monkeypatch.setattr(prepare_module, "read_personal_h20_product_cohort", barrier)
    try:
        window.show()
        widget = _load_h20_list(app, window)
        service = window.watchlist_service
        assert service is not None
        assert service.upgrade_to_repository().is_repository
        original_rows = service.get_stocks()
        widget.table.selectRow(0)
        widget.table.setCurrentCell(0, 0)
        widget.bookmark_button.click()
        _wait_for(app, entered.is_set)
        if change == "selection":
            widget.table.clearSelection()
        else:
            def unavailable_configuration():
                raise ValueError("synthetic_configuration_unavailable")
            monkeypatch.setattr(window, "_personal_h20_configuration", unavailable_configuration)
        release.set()
        _wait_for(app, lambda: not widget._bookmark_busy)
        assert service.get_stocks() == original_rows
        assert "未寫入收藏" in widget.bookmark_status_label.text()
        assert network == []
    finally:
        release.set()
        _close_mainwindow(app, window)


def test_close_during_prepare_cancels_before_private_write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import scripts.scheduled.personal_h20_bookmark_prepare as prepare_module
    app, window, _saved, network, _ = _prepare_saved_h20_mainwindow(tmp_path, monkeypatch)
    entered, release = threading.Event(), threading.Event()
    original = prepare_module.read_personal_h20_product_cohort

    def barrier(*args, **kwargs):
        entered.set()
        assert release.wait(30)
        return original(*args, **kwargs)

    monkeypatch.setattr(prepare_module, "read_personal_h20_product_cohort", barrier)
    try:
        window.show()
        widget = _load_h20_list(app, window)
        service = window.watchlist_service
        assert service is not None
        assert service.upgrade_to_repository().is_repository
        original_rows = service.get_stocks()
        widget.table.selectRow(0)
        widget.table.setCurrentCell(0, 0)
        widget.bookmark_button.click()
        _wait_for(app, entered.is_set)
        window.close()
        assert window._shutdown_close_requested
        status_before = widget.bookmark_status_label.text()
        release.set()
        _wait_for(app, lambda: not window.isVisible())
        assert service.get_stocks() == original_rows
        assert widget.bookmark_status_label.text() == status_before
        assert network == []
    finally:
        release.set()
        _close_mainwindow(app, window)
