"""正常UpdateView只讀接線、原精度與舊回呼／錯來源清除。"""
from dataclasses import replace
from hashlib import sha256
import threading
import time

from PySide6.QtWidgets import QApplication

from app_module.institutional_daily_snapshot import read_twse_institutional_daily_snapshot
from app_module.update_service import UpdateService
from test_institutional_daily_snapshot import _capture_twse, _seal, _CUTOFF
from test_ui_qt_update_view_workbench import FakeUpdateService, _TestableUpdateView


class _ReadOnlyService(FakeUpdateService):
    read_saved_institutional_daily_batch = UpdateService.read_saved_institutional_daily_batch


def _wait(app, condition):
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        app.processEvents()
        if condition():
            return
        time.sleep(0.005)
    assert condition(), "原8秒內UI讀取未收尾"


def _select(widget, pin, stock="2330"):
    widget.directory_edit.setText(str(pin.directory))
    widget.manifest_sha_edit.setText(pin.manifest_sha256)
    widget.receipt_sha_edit.setText(pin.receipt_sha256)
    widget.stock_code_edit.setText(stock)


def _fixture(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    run, capture = _capture_twse(tmp_path, monkeypatch)
    pin = _seal(run, capture["manifest_sha256"])
    service = _ReadOnlyService()
    view = _TestableUpdateView(service)
    return app, view, service, pin


def _close(app, view):
    view.begin_shutdown()
    _wait(app, lambda: view._institutional_daily_worker is None)
    view.close()
    app.processEvents()


def test_normal_update_view_reads_original_integers_and_rejects_wrong_pin(tmp_path, monkeypatch):
    app, view, service, pin = _fixture(tmp_path, monkeypatch)
    before = {str(path): sha256(path.read_bytes()).hexdigest() for path in pin.directory.parent.rglob("*") if path.is_file()}
    widget = view.institutional_daily_widget
    try:
        _select(widget, pin)
        widget.open_button.click()
        _wait(app, lambda: view._institutional_daily_worker is None)
        assert widget.rows_table.rowCount() == 1
        assert [widget.rows_table.item(0, col).text() for col in range(11)] == [
            "2026-09-08", "2330", "110", "55", "55", "30", "20", "10", "10", "5", "5",
        ]
        assert "2026-09-08T20:00:00+08:00" in widget.identity_label.text()
        assert pin.manifest_sha256 in widget.identity_label.text()
        assert "2026-09-08T17:30:00+08:00" in widget.rows_table.item(0, 0).toolTip()
        assert "不得用於連買" in widget.identity_label.text()
        widget.receipt_sha_edit.setText("0" * 64)
        assert widget.rows_table.rowCount() == 0
        widget.open_button.click()
        _wait(app, lambda: view._institutional_daily_worker is None)
        assert "SHA不符" in widget.status_label.text()
        assert widget.rows_table.rowCount() == 0 and widget.identity_label.text() == ""
        assert service.calls == []
        assert before == {str(path): sha256(path.read_bytes()).hexdigest() for path in pin.directory.parent.rglob("*") if path.is_file()}
    finally:
        _close(app, view)


def test_missing_stock_is_loaded_empty_and_display_keeps_large_integer(tmp_path, monkeypatch):
    app, view, _, pin = _fixture(tmp_path, monkeypatch)
    widget = view.institutional_daily_widget
    try:
        _select(widget, pin, "9999")
        widget.open_button.click()
        _wait(app, lambda: view._institutional_daily_worker is None)
        assert widget.rows_table.rowCount() == 0 and "0 命中" in widget.status_label.text()
        assert pin.receipt_sha256 in widget.identity_label.text()
        result = read_twse_institutional_daily_snapshot(pin, stock_code="2330", decision_cutoff=_CUTOFF)
        row = replace(result.rows[0], foreign_investor_buy=9007199254740993)
        widget.show_result(replace(result, rows=(row,)))
        assert widget.rows_table.item(0, 2).text() == "9007199254740993"
        widget.cancel_button.click()
        assert widget.rows_table.rowCount() == 0 and not widget.identity_label.text()
    finally:
        _close(app, view)


def test_input_change_and_shutdown_cancel_real_worker_and_ignore_old_payload(tmp_path, monkeypatch):
    app, view, service, pin = _fixture(tmp_path, monkeypatch)
    result = read_twse_institutional_daily_snapshot(pin, stock_code="2330", decision_cutoff=_CUTOFF)
    entered, release = threading.Event(), threading.Event()

    def controlled(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        return result

    monkeypatch.setattr(service, "read_saved_institutional_daily_batch", controlled)
    widget = view.institutional_daily_widget
    try:
        _select(widget, pin)
        widget.open_button.click()
        _wait(app, entered.is_set)
        worker = view._institutional_daily_worker
        assert worker is not None and not widget.open_button.isEnabled()
        widget.stock_code_edit.setText("2317")
        worker.finished.emit(result)
        app.processEvents()
        assert widget.rows_table.rowCount() == 0 and not widget.identity_label.text()
        assert worker.is_cancel_requested()
        view.begin_shutdown()
        assert worker.is_cancel_requested()
    finally:
        release.set()
        _close(app, view)


def test_relative_path_does_not_start_a_worker(tmp_path, monkeypatch):
    app, view, _, pin = _fixture(tmp_path, monkeypatch)
    try:
        widget = view.institutional_daily_widget
        _select(widget, pin)
        widget.directory_edit.setText("relative/daily_snapshot")
        widget.open_button.click()
        assert view._institutional_daily_worker is None
        assert "絕對批次目錄" in widget.status_label.text()
    finally:
        _close(app, view)
