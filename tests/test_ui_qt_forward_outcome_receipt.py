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
from ui_qt.rule_research_parent_receipt_dialog import (
    RuleResearchParentReceiptDialog, _benchmark_summary, read_parent_receipt_selection,
)


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


def test_saved_source_missing_is_visible_outside_diagnostics(qt_driver, forward_saved):
    _, parent, source, value = forward_saved
    value["prices"] = [p for p in value["prices"] if not (p["instrument_id"] == "1000" and p["trade_date"] == value["decision_date"])]
    source.write_text(json.dumps(value), encoding="utf-8")
    def reader(path, **kwargs):
        result = read_parent_receipt_selection(path, **kwargs)
        result["outcome"]["source_contract"] = {"issues": [{"stock_code": "1000", "reason": "exact_endpoint_missing"}]}
        return result
    dialog = RuleResearchParentReceiptDialog(reader=reader)
    qt_driver.addWidget(dialog)
    dialog._selected_path = str(parent)
    dialog._outcome_input_path = str(source)
    dialog.reload_receipt()
    _wait(qt_driver, dialog)
    assert "來源缺件" in dialog.outcome_summary.text() and "1 筆價格資料不足" in dialog.outcome_summary.text()
    assert "非含息總報酬" in dialog.outcome_summary.text()
    assert dialog.outcome_table.item(0, 4).text() in {"-", "—"} and not dialog.audit.isVisible()


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


def test_saved_benchmark_request_status_and_cost_version_survive_same_receipt_reload(
    qt_driver, forward_saved,
):
    _, receipt, source, value = forward_saved
    request = {
        "version": "benchmark-settings-v1",
        "benchmark_name": "TAIEX",
        "currency": "TWD",
        "unit": "index_point",
        "price_basis": "unadjusted_close",
        "corporate_action_basis": "not_applicable",
    }
    contract = {
        "benchmark_request": request,
        "benchmark_result": {
            "status": "unknown",
            "reason_codes": ["benchmark_row_missing", "target_basis_incompatible", "benchmark_available_date_unknown"],
            "benchmark": None,
            "prices": [],
            "observed_rowset_sha256": "a" * 64,
            "observed_decision_row_sha256": "b" * 64,
            "source_contract_json": "{\"historical_pit_eligible\":false}",
            "source_contract_sha256": "c" * 64,
            "historical_pit_eligible": False,
            "formal_eligible": False,
            "training_eligible": False,
            "execution_eligible": False,
        },
        "benchmark_status": "unknown",
        "target_basis_status": "unknown",
        "historical_pit_eligible": False,
    }

    def reader(path, **kwargs):
        result = read_parent_receipt_selection(path, **kwargs)
        if result.get("outcome") is not None:
            result["outcome"]["source_contract"] = contract
        return result

    dialog = RuleResearchParentReceiptDialog(reader=reader)
    qt_driver.addWidget(dialog)
    dialog.show()
    dialog._selected_path = str(receipt)
    dialog._outcome_input_path = str(source)
    dialog.reload_receipt()
    _wait(qt_driver, dialog)

    expected_cost_version = value["cost_policy"]["version"]
    assert "基準設定：TAIEX · 設定版本 benchmark-settings-v1" in dialog.benchmark_summary.text()
    assert "設定版本 benchmark-settings-v1" in dialog.benchmark_summary.text()
    assert "基準狀態：未知（" in dialog.benchmark_summary.text()
    assert "比較基礎缺件或不相容" in dialog.benchmark_summary.text()
    assert "來源可得時間未知或晚於評估日" in dialog.benchmark_summary.text()
    assert "超額未知，保留空值" in dialog.benchmark_summary.text()
    assert "歷史 PIT／正式／訓練／交易資格未核定" in dialog.benchmark_summary.text()
    assert "index_point" not in dialog.benchmark_summary.text()
    assert "unadjusted_close" not in dialog.benchmark_summary.text()
    assert f"成本版本 {expected_cost_version}" in dialog.outcome_summary.text()
    assert not dialog.audit.isVisible()

    displayed_benchmark = dialog.benchmark_summary.text()
    dialog.reload_button.click()
    _wait(qt_driver, dialog)
    assert dialog.benchmark_summary.text() == displayed_benchmark
    assert dialog.outcome_table.rowCount() == 19

    dialog.audit_button.click()
    assert dialog.audit.isVisible()
    assert "observed_rowset_sha256" in dialog.audit.toPlainText()
    assert "source_contract_sha256" in dialog.audit.toPlainText()
    assert "benchmark_request" in dialog.audit.toPlainText()
    assert "basis_comparable" in dialog.audit.toPlainText()
    assert "index_point" in dialog.audit.toPlainText()


def test_legacy_unconfigured_benchmark_stays_unknown():
    projection = {"benchmark": None, "members": []}
    summary = _benchmark_summary(projection, {"benchmark_status": "unconfigured_unknown"})
    assert "基準設定：未設定" in summary
    assert "超額未知，保留空值" in summary


def test_benchmark_spec_without_any_comparable_rows_stays_unknown():
    projection = {
        "benchmark": {"instrument_id": "market_indices.TAIEX"},
        "members": [{"horizons": [{"comparison": {
            "basis_comparable": None,
            "gross_excess_return": {"integer_bp_half_even": None},
        }}]}],
    }
    source_contract = {
        "benchmark_request": {"version": "settings-v2", "benchmark_name": "TAIEX"},
        "benchmark_result": {"status": "qualified_research", "reason_codes": [],
                             "benchmark": projection["benchmark"]},
        "benchmark_status": "qualified_research",
        "target_basis_status": "caller_declared_research_only",
    }

    summary = _benchmark_summary(projection, source_contract)
    assert "基準狀態：未知" in summary
    assert "目前沒有基礎相容且端點完整的同期間結果" in summary
    assert "已有同期間可比研究結果" not in summary
    assert "market_indices.TAIEX" not in summary
