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

from app_module.decision_continuity_controller import DecisionContinuityController
from app_module.dtos.decision_continuity_dtos import ACTION_NOTE
from app_module.journal_service import JournalService
from app_module.research_session import ResearchStockContextDTO
from ui_qt.widgets.decision_continuity_controls import (
    DecisionContinuityControlsWidget,
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
