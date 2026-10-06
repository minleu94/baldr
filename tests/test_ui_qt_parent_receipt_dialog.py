"""實際隔離收據唯讀 UI 與背景取消／stale 防護；不操作 Native。"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QFileDialog, QApplication
from PySide6.QtGui import QFont, QFontDatabase

from app_module.rule_research_parent_capture import produce_parent_rule_samples
from tests.test_rule_research_parent_capture import _fixture
from ui_qt.rule_research_parent_receipt_dialog import (
    RuleResearchParentReceiptDialog, read_parent_receipt_selection,
)
from ui_qt.views.daily_market_research_view import DailyMarketResearchView


@pytest.fixture
def qt_driver():
    app = QApplication.instance() or QApplication([])
    font = Path("C:/Windows/Fonts/msjh.ttc")
    if font.exists():
        font_id = QFontDatabase.addApplicationFont(str(font))
        families = QFontDatabase.applicationFontFamilies(font_id)
        if families:
            app.setFont(QFont(families[0], 10))
    class Driver:
        def __init__(self):
            self.widgets = []
        def addWidget(self, widget):
            self.widgets.append(widget)
        def waitUntil(self, predicate, timeout=8000):
            end = time.monotonic() + timeout / 1000
            while not predicate():
                assert time.monotonic() < end, "有限背景工作未安全返回"
                app.processEvents()
                time.sleep(0.01)
            app.processEvents()
    driver = Driver()
    yield driver
    for widget in reversed(driver.widgets):
        widget.close()
    app.processEvents()


@pytest.fixture
def saved(tmp_path, monkeypatch):
    args, _ = _fixture(tmp_path, monkeypatch)
    result = produce_parent_rule_samples(**args)
    identity = result["parent_capture"]["receipt"]["capture_identity_sha256"]
    path = args["capture_root"] / "parents" / identity / "receipt.json"
    return args, path


def _wait(qt_driver, dialog):
    try:
        qt_driver.waitUntil(lambda: dialog._worker is None, timeout=8000)
    except AssertionError:
        print("worker_timeout", dialog._worker.isRunning() if dialog._worker else None, dialog.summary.text())
        raise


def test_actual_saved_readonly_ui_reread_and_diagnostics(qt_driver, saved, monkeypatch):
    args, path = saved
    before = {p: p.read_bytes() for p in args["capture_root"].rglob("*.json")}
    # 新consumer不准開市場DB或producer。
    import app_module.rule_research_parent_capture as parent
    monkeypatch.setattr(parent, "SQLiteDailyMarketSnapshotSource", lambda *a, **k: pytest.fail("opened DB"))
    dialog = RuleResearchParentReceiptDialog()
    qt_driver.addWidget(dialog)
    dialog.show()
    dialog.read_receipt(str(path))
    _wait(qt_driver, dialog)
    assert "完整保存" in dialog.summary.text() and "資料日" in dialog.summary.text()
    assert "聲明 19" in dialog.summary.text() and "未捕捉 0" in dialog.summary.text()
    assert "MA20" in dialog.methods.text() and "MA60" in dialog.methods.text()
    assert "正式入選" not in dialog.methods.text()
    assert dialog.batch_table.rowCount() == 2
    assert "已發布完整快照" in dialog.batch_table.item(0, 2).text()
    assert "樣本已保存" in dialog.batch_table.item(0, 3).text()
    assert not dialog.audit.isVisible()
    assert path.parent.name not in dialog.summary.text()
    dialog.audit_button.click()
    assert dialog.audit.isVisible() and path.parent.name in dialog.audit.toPlainText()
    dialog.reload_button.click()
    _wait(qt_driver, dialog)
    assert not dialog.audit.isVisible()
    assert before == {p: p.read_bytes() for p in args["capture_root"].rglob("*.json")}
    screenshot = os.environ.get("UX20_RECEIPT_SCREENSHOT")
    if screenshot:
        assert dialog.grab().save(screenshot)


def test_actual_receipt_new_process_readonly(saved):
    _, path = saved
    script = "from ui_qt.rule_research_parent_receipt_dialog import read_parent_receipt_selection; import sys,json; r=read_parent_receipt_selection(sys.argv[1]); print(json.dumps(r['readiness']['captured_member_count']))"
    result = subprocess.run([sys.executable, "-c", script, str(path)], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "19"


def test_incomplete_parent_shows_uncaptured_and_producer_capture_separately(qt_driver, tmp_path, monkeypatch):
    args, producer = _fixture(tmp_path, monkeypatch)
    original = producer.produce
    calls = []
    def fail_second(self, *a, **kw):
        calls.append(1)
        if len(calls) == 2:
            raise RuntimeError("controlled second batch failure")
        return original(self, *a, **kw)
    monkeypatch.setattr(producer, "produce", fail_second)
    result = produce_parent_rule_samples(**args)
    identity = result["parent_capture"]["receipt"]["capture_identity_sha256"]
    dialog = RuleResearchParentReceiptDialog()
    qt_driver.addWidget(dialog)
    dialog.read_receipt(str(args["capture_root"] / "parents" / identity / "receipt.json"))
    _wait(qt_driver, dialog)
    assert "保存未完整" in dialog.summary.text()
    assert "未捕捉 19" in dialog.summary.text()
    assert "已發布完整快照" in dialog.batch_table.item(0, 2).text()
    assert "未開始" in dialog.batch_table.item(0, 3).text()
    assert "重試" in dialog.next_step.text() and "負樣本" in dialog.next_step.text()


@pytest.mark.parametrize("damage", ["universe", "child"])
def test_verified_envelope_rejected_readiness_keeps_publication(qt_driver, saved, damage):
    args, path = saved
    if damage == "universe":
        args["universe_path"].write_text("{}", encoding="utf-8")
    else:
        child = next((args["capture_root"] / "samples").rglob("capture.json"))
        child.write_text("{}", encoding="utf-8")
    dialog = RuleResearchParentReceiptDialog()
    qt_driver.addWidget(dialog)
    dialog.read_receipt(str(path))
    _wait(qt_driver, dialog)
    assert "readiness 核對失敗" in dialog.summary.text()
    assert "完整資格未確認" in dialog.summary.text()
    assert "未核對" in dialog.methods.text()
    assert dialog.batch_table.rowCount() == 2
    assert "已發布完整快照" in dialog.batch_table.item(0, 2).text()
    assert "樣本已保存" in dialog.batch_table.item(0, 3).text()
    assert not dialog.audit_button.isChecked()


def test_invalid_receipt_error_retry_clear_previous(qt_driver, saved):
    _, path = saved
    dialog = RuleResearchParentReceiptDialog()
    qt_driver.addWidget(dialog)
    dialog.read_receipt(str(path))
    _wait(qt_driver, dialog)
    dialog.read_receipt(str(path.with_name("capture.json")))
    _wait(qt_driver, dialog)
    assert "核對失敗" in dialog.summary.text() and dialog.batch_table.rowCount() == 0
    assert dialog.reload_button.isEnabled()
    dialog.read_receipt(str(path))
    _wait(qt_driver, dialog)
    assert "完整保存" in dialog.summary.text()


@pytest.mark.parametrize("action", ["cancel", "return", "close"])
def test_background_duplicate_cancel_return_and_stale(qt_driver, saved, action):
    _, path = saved
    result = read_parent_receipt_selection(str(path))
    entered, release = threading.Event(), threading.Event()
    calls = []
    def reader(*a, cancel_callback=None):
        calls.append(a)
        entered.set()
        assert release.wait(5)
        # 故意回傳成功，必須由 UI generation 擋下晚到 callback。
        return result
    dialog = RuleResearchParentReceiptDialog(reader=reader)
    qt_driver.addWidget(dialog)
    dialog.show()
    dialog.read_receipt(str(path))
    qt_driver.waitUntil(entered.is_set)
    generation = dialog._generation
    worker = dialog._worker
    try:
        dialog.read_receipt(str(path))
        assert dialog._worker is worker and len(calls) == 1
        assert not dialog.reload_button.isEnabled()
        if action == "cancel":
            dialog.cancel_button.click()
        elif action == "return":
            dialog.return_button.click()
        else:
            dialog.close()
        text = dialog.summary.text()
        release.set()
        _wait(qt_driver, dialog)
        dialog._completed(generation, result)
        dialog._failed(generation, "late error")
        assert dialog.summary.text() == text
        assert "完整保存" not in text
        assert dialog.reload_button.isEnabled()
        dialog.show()
        dialog.read_receipt(str(path))
        _wait(qt_driver, dialog)
        assert "完整保存" in dialog.summary.text()
    finally:
        release.set()
        _wait(qt_driver, dialog)


def test_picker_cancel_and_daily_page_single_dialog(qt_driver, monkeypatch):
    view = DailyMarketResearchView()
    qt_driver.addWidget(view)
    view.parent_receipt_button.click()
    dialog = view._parent_receipt_dialog
    assert isinstance(dialog, RuleResearchParentReceiptDialog)
    assert dialog._worker is None
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: ("", ""))
    dialog.choose_button.click()
    assert dialog._worker is None and not dialog._selected_path
    view.parent_receipt_button.click()
    assert view._parent_receipt_dialog is dialog
    dialog.reject()


def test_reader_pre_cancel_does_not_open_any_file(tmp_path, monkeypatch):
    path = tmp_path / "parents" / ("a" * 64) / "receipt.json"
    assert read_parent_receipt_selection(str(path), cancel_callback=lambda: True) == {"cancelled": True}
