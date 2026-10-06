"""原保存→cohort→Qt列表→exact研究返回；offscreen 合成證據。"""
from dataclasses import asdict, replace
import json
import os
import subprocess
import sys

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QTableWidgetItem

from app_module.recommendation.personal_h20_research_cohort import PersonalH20ResearchSelection
from tests.test_personal_h20_research_cohort import saved_cohort, read_saved
from ui_qt.widgets.personal_h20_research_widget import PersonalH20ResearchWidget


def app():
    return QApplication.instance() or QApplication([])


def selection(cohort, row):
    return PersonalH20ResearchSelection(cohort.manifest_sha256, cohort.candidate_id,
        cohort.contract_hash, cohort.cycle_id, row.symbol, row.sample_id, row.prediction_id, row.capture_sha256)


def test_complete_table_integer_sort_exact_request_and_two_refreshes(tmp_path):
    qt = app()
    cohort = read_saved(saved_cohort(tmp_path))
    widget = PersonalH20ResearchWidget()
    emitted = []
    widget.researchRequested.connect(emitted.append)
    widget.set_cohort(cohort)
    assert widget.table.rowCount() == 3
    assert [widget.table.item(i, 0).text() for i in range(3)] == ["1101", "2330", "2454"]
    assert widget.table.item(0, 1).text() == "120"
    assert "不是勝率或機率" in widget.limit_label.text()
    assert "不代表全市場" in widget.summary_label.text()
    exact = selection(cohort, cohort.rows[1])
    for _ in range(2):
        widget.set_cohort(cohort)
        assert not widget.research_button.isEnabled()
        assert widget.restore_selection(exact)
        widget.research_button.click()
    assert emitted == [exact, exact]
    widget.sort_combo.setCurrentIndex(1)
    assert [widget.table.item(i, 0).text() for i in range(3)] == ["2454", "1101", "2330"]
    assert widget.restore_selection(exact)
    assert widget.table.currentItem().data(Qt.ItemDataRole.UserRole) == exact
    widget.close()
    qt.processEvents()


@pytest.mark.parametrize("field", ["manifest_sha256", "candidate_id", "contract_hash", "cycle_id", "symbol",
    "sample_id", "prediction_id", "capture_sha256"])
def test_exact_restore_refuses_other_scope_or_stale_identity(tmp_path, field):
    qt = app()
    cohort = read_saved(saved_cohort(tmp_path))
    widget = PersonalH20ResearchWidget()
    widget.set_cohort(cohort)
    exact = selection(cohort, cohort.rows[0])
    assert widget.restore_selection(exact)
    assert not widget.restore_selection(replace(exact, **{field: "other"}))
    assert not widget.research_button.isEnabled()
    widget.close()
    qt.processEvents()


def test_unknown_row_kept_not_actionable_and_all_unknown(tmp_path):
    qt = app()
    saved = saved_cohort(tmp_path)
    def reader(*a, **k): raise ValueError("synthetic_missing")
    cohort = read_saved(saved, reader)
    widget = PersonalH20ResearchWidget()
    widget.set_cohort(cohort)
    emitted = []
    widget.researchRequested.connect(emitted.append)
    assert widget.table.rowCount() == 3
    assert all(widget.table.item(i, 1).text() == "—" for i in range(3))
    assert not widget.restore_selection(selection(cohort, cohort.rows[0]))
    widget.table.selectRow(0)
    widget._request_item(widget.table.item(0, 0))
    assert not emitted
    widget.close()
    qt.processEvents()


def test_previous_cohort_callback_wrong_decision_and_closed_callback_refused(tmp_path):
    qt = app()
    cohort = read_saved(saved_cohort(tmp_path))
    widget = PersonalH20ResearchWidget()
    widget.set_cohort(cohort)
    exact = selection(cohort, cohort.rows[0])
    stale_item = QTableWidgetItem("1101")
    stale_item.setData(Qt.ItemDataRole.UserRole, exact)
    emitted = []
    widget.researchRequested.connect(emitted.append)
    newer = replace(cohort, manifest_sha256="sha256:" + "b" * 64, cycle_id="next",
        decision_date="2026-10-07", rows=tuple(replace(r, decision_date="2026-10-07") for r in cohort.rows))
    widget.set_cohort(newer)
    widget._request_item(stale_item)
    assert not widget.restore_selection(exact)
    assert not emitted
    widget.close()
    widget.set_cohort(cohort)
    widget._request_item(stale_item)
    assert not widget.restore_selection(exact) and not emitted
    qt.processEvents()


def test_new_process_original_saved_read_and_exact_return_restore(tmp_path):
    saved = saved_cohort(tmp_path)
    cohort = read_saved(saved)
    exact = selection(cohort, cohort.rows[1])
    code = """
import json,sys
from PySide6.QtWidgets import QApplication
from tests.test_personal_h20_research_cohort import public_reader
from app_module.recommendation.personal_h20_research_cohort import read_personal_h20_research_cohort,PersonalH20ResearchSelection
from ui_qt.widgets.personal_h20_research_widget import PersonalH20ResearchWidget
a=QApplication([])
c=read_personal_h20_research_cohort(sys.argv[1],root=sys.argv[2],expected_sha256=sys.argv[3],prediction_reader=public_reader)
s=PersonalH20ResearchSelection(**json.loads(sys.argv[4]))
w=PersonalH20ResearchWidget();w.set_cohort(c)
assert w.restore_selection(s)
got=[];w.researchRequested.connect(got.append);w.research_button.click();assert got==[s]
w.close();a.processEvents();print('exact_restored')
"""
    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"
    result = subprocess.run([sys.executable, "-c", code, str(saved[1]), str(saved[0]), saved[2], json.dumps(asdict(exact))],
        env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert "exact_restored" in result.stdout
