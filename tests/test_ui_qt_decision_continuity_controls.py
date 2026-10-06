"""Increment B：研究動作控制項的隔離、重開讀回與失敗重試。"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import QDateTime
from PySide6.QtWidgets import QApplication
from PySide6.QtWidgets import QBoxLayout

from app_module.decision_continuity_controller import DecisionContinuityController
from app_module.dtos.decision_continuity_dtos import ACTION_NOTE
from app_module.journal_service import JournalService
from app_module.research_session import ResearchStockContextDTO
from ui_qt.widgets.decision_continuity_controls import (
    DecisionContinuityControlsWidget,
    PersonalRecommendationChoiceControlsWidget,
)


def _app() -> QApplication:
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication([])
    return instance


def _config(root: Path) -> SimpleNamespace:
    return SimpleNamespace(
        output_root=root / "output",
        resolve_output_path=lambda name: root / "output" / name,
    )


def _context(stock_code: str = "2330", result_id: str = "result-001") -> ResearchStockContextDTO:
    return ResearchStockContextDTO(
        stock_code=stock_code,
        stock_name="合成標的",
        result_id=result_id,
        decision_date="2026-09-14",
        data_date="2026-09-14",
        source_workspace="recommendation",
    )


@pytest.fixture(autouse=True)
def _qapp() -> QApplication:
    return _app()


def test_controls_save_accept_review_note_and_reopen_exact_state(tmp_path: Path) -> None:
    service = JournalService(_config(tmp_path))
    controller = DecisionContinuityController(service)
    widget = DecisionContinuityControlsWidget(controller)
    widget.set_context(_context())
    widget.show()

    assert widget.accept_button.isEnabled()
    widget.accept_button.click()
    assert "已納入研究" in widget.status_label.text()
    assert widget.history_list.count() == 1

    selected = QDateTime.fromString("2026-09-20 10:30:00", "yyyy-MM-dd HH:mm:ss")
    widget.review_datetime.setDateTime(selected)
    widget.review_button.click()
    assert "已納入研究" in widget.status_label.text()
    assert "2026-09-20T10:30:00+08:00" in widget.status_label.text()

    widget._submit(ACTION_NOTE, note="確認營收與風險")
    assert "Journal 紀錄：1 筆" in widget.status_label.text()
    assert widget.history_list.count() == 3
    widget.close()

    reopened = DecisionContinuityControlsWidget(
        DecisionContinuityController(JournalService(_config(tmp_path)))
    )
    reopened.set_context(_context())
    reopened.show()
    assert reopened.state is not None
    assert reopened.state.decision_status == "accepted"
    assert reopened.state.next_review_at == "2026-09-20T10:30:00+08:00"
    assert reopened.state.active_note_count == 1
    assert reopened.technical_details.isVisible() is False
    reopened.technical_toggle.click()
    assert reopened.technical_details.isVisible() is True
    assert "result_id=result-001" in reopened.identity_label.text()
    reopened.close()


def test_missing_result_disables_candidate_actions(tmp_path: Path) -> None:
    widget = DecisionContinuityControlsWidget(
        DecisionContinuityController(JournalService(_config(tmp_path)))
    )
    widget.set_context(_context(result_id=""))

    assert not widget.accept_button.isEnabled()
    assert not widget.skip_button.isEnabled()
    assert not widget.note_button.isEnabled()
    assert not widget.review_button.isEnabled()
    assert "exact result_id + stock_code" in widget.status_label.text()
    widget.close()


def test_failed_write_shows_retry_and_reuses_request_id_without_duplicate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = JournalService(_config(tmp_path))
    controller = DecisionContinuityController(service)
    original = service.record_research_action
    calls: list[str] = []

    def fail_once(*args, **kwargs):
        calls.append(str(kwargs["revision_id"]))
        raise RuntimeError("temporary journal failure")

    monkeypatch.setattr(service, "record_research_action", fail_once)
    widget = DecisionContinuityControlsWidget(controller)
    widget.set_context(_context())
    widget.accept_button.click()

    assert "儲存失敗" in widget.status_label.text()
    assert widget.retry_button.isEnabled()
    assert widget.history_list.count() == 1
    assert calls

    monkeypatch.setattr(service, "record_research_action", original)
    request_id = widget._pending_retry["request_id"] if widget._pending_retry else ""
    widget.retry_button.click()

    assert "已納入研究" in widget.status_label.text()
    assert calls == [request_id]
    assert len(service.list_decision_revisions()) == 1
    widget.close()


def test_personal_recommendation_choice_reflows_on_narrow_width() -> None:
    _app()
    widget = PersonalRecommendationChoiceControlsWidget()
    try:
        widget.resize(390, 700)
        widget.show()
        _app().processEvents()

        assert widget._choice_actions_layout.direction() == QBoxLayout.TopToBottom
        for button in (
            widget.adopt_button,
            widget.reject_button,
            widget.override_button,
        ):
            assert button.width() >= button.sizeHint().width()

        widget.resize(900, 700)
        _app().processEvents()
        assert widget._choice_actions_layout.direction() == QBoxLayout.LeftToRight
    finally:
        widget.close()
        widget.deleteLater()
        _app().processEvents()



def test_approved_context_source_reaches_original_writer_and_marker(tmp_path, monkeypatch):
    from tests.test_baldr_b05_chart_marker_reader import CONTEXT, POINTS, assert_visible
    from app_module.decision_outcome_journey import JsonlJournalReadAdapter
    from app_module.stock_research_chart_marker_reader import (
        StockChartMarkerReadRequest, StockChartMarkerRecordSource,
        StockResearchChartMarkerReader, stock_chart_saved_record_sha256,
    )
    service = JournalService(_config(tmp_path))
    original = service.record_research_action
    def save_at_original_clock(*args, **kwargs):
        return original(*args, recorded_at="2026-10-08T15:00:00+08:00", **kwargs)
    monkeypatch.setattr(service, "record_research_action", save_at_original_clock)
    widget = DecisionContinuityControlsWidget(DecisionContinuityController(service))
    widget.set_context(ResearchStockContextDTO(**CONTEXT, source_id="source-a"))
    widget.accept_button.click()
    assert widget.state is not None and widget.state.decision_status == "accepted"
    callback = JsonlJournalReadAdapter(service.store.journal_file)._records
    rows = callback()
    assert rows[0]["payload"]["source_id"] == "source-a"
    pins = tuple((row["revision_id"], stock_chart_saved_record_sha256(row)) for row in rows)
    request = StockChartMarkerReadRequest(
        StockChartMarkerRecordSource.RECOMMENDATION_CONFIRMATIONS, "2330", "2026-10-08",
        "default", "source-a", CONTEXT["result_id"], CONTEXT["decision_date"],
        CONTEXT["source_snapshot_id"], CONTEXT["source_snapshot_hash"],
        tuple(sorted(CONTEXT.items())), pins)
    reader = StockResearchChartMarkerReader(confirmation_records=callback)
    before = service.store.journal_file.read_bytes()
    result = reader.read(request, price_points=POINTS)
    assert len(result.candidates) == 1 and result.diagnostics == ()
    assert_visible(reader, request)
    assert reader.read(request, price_points=POINTS, cancelled=lambda: True).candidates == ()
    assert service.store.journal_file.read_bytes() == before
    from dataclasses import asdict
    import json
    import subprocess
    import sys
    replay = '''
import json, sys
from PySide6.QtWidgets import QApplication
from tests.test_baldr_b05_chart_marker_reader import *
data=json.loads(sys.argv[1]); path=data.pop('path')
data['record_source']=StockChartMarkerRecordSource(data['record_source'])
data['source_context']=tuple(map(tuple,data['source_context']))
data['expected_record_hashes']=tuple(map(tuple,data['expected_record_hashes']))
request=StockChartMarkerReadRequest(**data)
reader=StockResearchChartMarkerReader(confirmation_records=JsonlJournalReadAdapter(path)._records)
app=QApplication([])
assert_visible(reader,request)
print(reader.read(request,price_points=POINTS).candidates[0].content_sha256)
'''
    completed = subprocess.run(
        [sys.executable, '-c', replay, json.dumps({**asdict(request), 'path': str(service.store.journal_file)})],
        capture_output=True, text=True, timeout=40, check=True)
    assert completed.stdout.strip() == result.candidates[0].content_sha256
    assert service.store.journal_file.read_bytes() == before
    # A new unknown-source acceptance is saved as unknown, never borrowed from history.
    from dataclasses import replace
    widget.set_context(replace(ResearchStockContextDTO(**CONTEXT), source_id=''))
    widget.accept_button.click()
    rows = callback()
    unknown = rows[-1]
    assert unknown['source_id'] == '' and unknown['payload']['source_id'] == ''
    rejected = reader.read(replace(request, expected_record_hashes=(
        (unknown['revision_id'], stock_chart_saved_record_sha256(unknown)),)), price_points=POINTS)
    assert rejected.candidates == ()
    assert any('saved_source_mismatch' in reason for reason in rejected.diagnostics)
    widget.close()


def test_source_unknown_stays_empty_and_retry_requires_exact_source(tmp_path):
    from app_module.dtos.decision_continuity_dtos import ACTION_ACCEPTED
    service = JournalService(_config(tmp_path))
    controller = DecisionContinuityController(service)
    identity = controller.identity_from_context(_context())
    first = controller.apply(ACTION_ACCEPTED, identity, request_id="legacy-source")
    assert first.success and first.revision.payload["source_id"] == ""
    assert controller.apply(ACTION_ACCEPTED, identity, request_id="legacy-source").success
    conflict = controller.apply(ACTION_ACCEPTED, identity, request_id="legacy-source", source_id="new-source")
    assert not conflict.success and conflict.error_code == "journal_revision_event_conflict"
    assert len(service.list_decision_revisions()) == 1
    assert service.list_decision_revisions()[0].payload["source_id"] == ""


def test_context_change_cancels_old_retry_even_same_candidate(tmp_path, monkeypatch):
    from dataclasses import replace
    service = JournalService(_config(tmp_path))
    original = service.record_research_action
    widget = DecisionContinuityControlsWidget(DecisionContinuityController(service))
    context = replace(_context(), source_id="source-a")
    widget.set_context(context)
    def fail(*args, **kwargs):
        raise RuntimeError("cancelled synthetic write")
    monkeypatch.setattr(service, "record_research_action", fail)
    widget.accept_button.click()
    assert widget._pending_retry and widget._pending_retry["source_id"] == "source-a"
    widget.set_context(replace(context, source_id="source-b"))
    assert widget._pending_retry is None
    monkeypatch.setattr(service, "record_research_action", original)
    widget._retry()
    assert service.list_decision_revisions() == []
    widget.close()


def test_late_committed_result_does_not_replace_changed_context(tmp_path, monkeypatch):
    from dataclasses import replace
    service = JournalService(_config(tmp_path))
    original = service.record_research_action
    widget = DecisionContinuityControlsWidget(DecisionContinuityController(service))
    first = replace(_context(), source_id="source-a")
    widget.set_context(first)
    def save_then_switch(*args, **kwargs):
        revision = original(*args, **kwargs)
        widget.set_context(replace(first, stock_code="2317", source_id="source-b"))
        return revision
    monkeypatch.setattr(service, "record_research_action", save_then_switch)
    widget.accept_button.click()
    assert widget.identity.stock_code == "2317"
    assert widget.state.identity.stock_code == "2317"
    assert widget._pending_retry is None
    saved = service.list_decision_revisions()
    assert len(saved) == 1 and saved[0].payload["source_id"] == "source-a"
    widget.close()
