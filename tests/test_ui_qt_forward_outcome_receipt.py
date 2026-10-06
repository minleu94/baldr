"""既有母體視窗的研究結果最小畫面，僅 offscreen。"""
from datetime import date, timedelta
import json
import os
import threading

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QFileDialog
from tests.test_ui_qt_parent_receipt_dialog import qt_driver, _wait
from tests.test_rule_research_forward_outcome_reader import forward_saved
from ui_qt.rule_research_parent_receipt_dialog import RuleResearchParentReceiptDialog, read_parent_receipt_selection


def _load(qt_driver, saved, monkeypatch):
    _, receipt, source, _ = saved
    dialog = RuleResearchParentReceiptDialog()
    qt_driver.addWidget(dialog)
    dialog.show()
    dialog.read_receipt(str(receipt))
    _wait(qt_driver, dialog)
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **kw: (str(source), ""))
    dialog.outcome_input_button.click()
    _wait(qt_driver, dialog)
    dialog.result_tabs.setCurrentIndex(1)
    return dialog


def test_actual_ui_horizons_cost_denominator_and_no_data(qt_driver, forward_saved, monkeypatch):
    dialog = _load(qt_driver, forward_saved, monkeypatch)
    assert "每方法完整分母 19" in dialog.outcome_summary.text()
    assert all(h in dialog.outcome_summary.text() for h in ("H5", "H10", "H20"))
    assert "15/30 bp" in dialog.outcome_summary.text() and "5/10 bp" in dialog.outcome_summary.text()
    assert dialog.outcome_table.rowCount() == 19
    assert dialog.outcome_table.item(0, 4).text() == "500"
    assert dialog.outcome_table.item(0, 5).text() != "500"
    assert dialog.outcome_table.item(0, 7).text() != "—"
    assert dialog.outcome_table.item(18, 1).text() == "明示排除"
    dialog.outcome_horizon.setCurrentIndex(2)
    assert dialog.outcome_table.item(0, 4).text() == "2000"
    dialog.outcome_method.setCurrentIndex(1)
    assert dialog.outcome_table.rowCount() == 19
    assert not dialog.audit.isVisible()
    assert "endpoint" not in dialog.outcome_summary.text()
    screenshot = os.environ.get("UX21_SCREENSHOT")
    if screenshot:
        assert dialog.grab().save(screenshot)
    dialog.outcome_clear_button.click()
    _wait(qt_driver, dialog)
    assert "資料不足" in dialog.outcome_summary.text() and dialog.outcome_table.rowCount() == 0


@pytest.mark.parametrize("mode", ["missing", "pending", "cost_unknown", "calendar_unknown", "wrong_parent"])
def test_plain_language_missing_pending_and_reject(qt_driver, forward_saved, monkeypatch, mode):
    _, _, source, value = forward_saved
    if mode == "missing":
        endpoint = value["calendar"]["trading_dates"][5]
        value["prices"] = [p for p in value["prices"] if not (p["instrument_id"] == "1000" and p["trade_date"] == endpoint)]
    elif mode == "pending":
        start = date.fromisoformat(value["decision_date"])
        dates = [(start + timedelta(days=15 * i)).isoformat() for i in range(21)]
        value["calendar"].update(trading_dates=dates, coverage_end=dates[-1])
    elif mode == "cost_unknown": value["cost_policy"] = None
    elif mode == "calendar_unknown":
        value["calendar"] = {"known": False, "complete": False, "trading_dates": [], "coverage_start": None,
                             "coverage_end": None, "source_identity": None, "available_date": None}
    else: value["parent_identity_sha256"] = "0" * 64
    source.write_text(json.dumps(value), encoding="utf-8")
    dialog = _load(qt_driver, forward_saved, monkeypatch)
    if mode == "wrong_parent":
        assert "核對失敗" in dialog.outcome_summary.text() and dialog.outcome_table.rowCount() == 0
        assert "完整保存" in dialog.summary.text() and dialog.batch_table.rowCount() == 2
        assert "parent_mismatch" in dialog.audit.toPlainText()
    elif mode == "missing": assert dialog.outcome_table.item(0, 2).text() == "缺價／停牌"
    elif mode == "pending": assert "未成熟 17" in dialog.outcome_summary.text()
    elif mode == "calendar_unknown": assert dialog.outcome_table.item(0, 2).text() == "資料不足"
    else:
        assert "成本未知" in dialog.outcome_summary.text()
        assert dialog.outcome_table.item(0, 4).text() == "500"
        assert dialog.outcome_table.item(0, 5).text() == dialog.outcome_table.item(0, 7).text() == "—"


def test_cancel_stale_and_retry_same_input(qt_driver, forward_saved):
    _, receipt, source, _ = forward_saved
    started, release = threading.Event(), threading.Event()
    def reader(path, **kw):
        started.set()
        assert release.wait(8)
        return read_parent_receipt_selection(path, **kw)
    dialog = RuleResearchParentReceiptDialog(reader=reader)
    qt_driver.addWidget(dialog)
    dialog._selected_path = str(receipt)
    dialog._outcome_input_path = str(source)
    dialog.reload_receipt()
    qt_driver.waitUntil(started.is_set)
    old_generation = dialog._generation
    worker = dialog._worker
    dialog.reload_receipt()
    assert dialog._worker is worker
    dialog.cancel_read()
    release.set()
    _wait(qt_driver, dialog)
    late = read_parent_receipt_selection(str(receipt), outcome_input_path=str(source))
    dialog._completed(old_generation, late)
    dialog._failed(old_generation, "late_error")
    assert "已取消" in dialog.outcome_summary.text() and dialog.outcome_table.rowCount() == 0
    dialog.reload_receipt()
    _wait(qt_driver, dialog)
    assert dialog.outcome_table.rowCount() == 19
    dialog.reject()
    dialog._completed(dialog._generation - 1, late)
    assert dialog._returned
