from __future__ import annotations

import os
import sys
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from app_module.dtos.portfolio_dtos import JournalEntryDTO
from app_module.research_timeline_dtos import ResearchTimelineEntry
from ui_qt.main import MainWindow


_APPLICATION: QApplication | None = None


@pytest.fixture(scope="session", autouse=True)
def _keep_qt_application() -> QApplication:
    """整個測試工作階段共用 Qt application，不逐測試摧毀全域 instance。"""
    global _APPLICATION
    instance = QApplication.instance()
    _APPLICATION = instance if instance is not None else QApplication(sys.argv)
    return _APPLICATION


class _Signal:
    def __init__(self) -> None:
        self._slots = []

    def connect(self, callback) -> None:
        self._slots.append(callback)

    def emit(self, *args) -> None:
        for callback in tuple(self._slots):
            callback(*args)


class _DialogSpy:
    instances: list["_DialogSpy"] = []

    def __init__(self, entry, parent=None) -> None:
        self.entry = entry
        self.parent = parent
        self.paperStatusRequested = _Signal()
        self.finished = _Signal()
        self.open_count = 0
        self.close_count = 0
        type(self).instances.append(self)

    def setAttribute(self, *_args) -> None:
        return None

    def open(self) -> None:
        self.open_count += 1

    def close(self) -> None:
        self.close_count += 1


def _entry(record_id: str = "paper-prereq-main-1") -> ResearchTimelineEntry:
    note = JournalEntryDTO(
        journal_id=record_id,
        portfolio_id="default",
        body="保存的研究判斷。",
        stock_code="2330",
        created_at="2026-10-21T08:30:00+00:00",
        revision_id=record_id,
    )
    return ResearchTimelineEntry(
        kind="manual",
        record_id=record_id,
        recorded_at=note.created_at,
        text=note.body,
        reference=note,
        stock_code=note.stock_code,
        source_identity="source-identity-1",
    )


def _host(entry: ResearchTimelineEntry):
    page = object()
    timeline = SimpleNamespace(selected_entry=entry, evidence_comparison_revision=7)
    stack = SimpleNamespace(currentWidget=lambda: page)
    host = SimpleNamespace(
        _shutdown_close_requested=False,
        research_timeline_view=timeline,
        workspace_stack=stack,
        workspace_widgets={"research_timeline": page},
        product_shell=SimpleNamespace(routes=[]),
    )
    host.product_shell.activate_route = host.product_shell.routes.append
    pending = []
    verify_calls = []

    def verify(selected, completed, *, evidence_baseline=False):
        verify_calls.append((selected, evidence_baseline))
        pending.append(completed)

    host._verify_timeline_entry = verify
    return host, pending, verify_calls, page


def _install_dialog_spy(monkeypatch) -> None:
    from ui_qt.widgets import research_paper_prerequisite_dialog

    _DialogSpy.instances.clear()
    monkeypatch.setattr(
        research_paper_prerequisite_dialog,
        "ResearchPaperPrerequisiteDialog",
        _DialogSpy,
    )


def test_prerequisite_check_rejects_wrong_type_wrong_selection_and_non_timeline_page(monkeypatch):
    _install_dialog_spy(monkeypatch)
    selected = _entry("selected")
    other = _entry("other")

    host, pending, calls, _page = _host(selected)
    MainWindow._check_timeline_paper_prerequisites(host, object())
    assert calls == []

    host.research_timeline_view.selected_entry = other
    MainWindow._check_timeline_paper_prerequisites(host, selected)
    assert calls == []

    host.research_timeline_view.selected_entry = selected
    host.workspace_stack.currentWidget = lambda: object()
    MainWindow._check_timeline_paper_prerequisites(host, selected)
    assert calls == []
    assert pending == []
    assert _DialogSpy.instances == []
    assert host.product_shell.routes == []


@pytest.mark.parametrize("stale_event", ["selection", "revision", "page", "shutdown"])
def test_late_baseline_result_never_opens_dialog_or_routes(monkeypatch, stale_event: str):
    _install_dialog_spy(monkeypatch)
    selected = _entry("late-result")
    host, pending, calls, page = _host(selected)

    MainWindow._check_timeline_paper_prerequisites(host, selected)
    assert calls == [(selected, True)]  # 必須走原件與 evidence baseline 重核。
    assert len(pending) == 1
    completed = pending[0]

    if stale_event == "selection":
        host.research_timeline_view.selected_entry = _entry("new-selection")
    elif stale_event == "revision":
        # refresh / selection revision 改變，即使 entry identity 相同也拒絕晚到結果。
        host.research_timeline_view.evidence_comparison_revision += 1
    elif stale_event == "page":
        host.workspace_stack.currentWidget = lambda: object()
    else:
        host._shutdown_close_requested = True

    completed((selected.reference, None))
    assert _DialogSpy.instances == []
    assert host.product_shell.routes == []


def test_invalid_baseline_result_does_not_open_dialog(monkeypatch):
    _install_dialog_spy(monkeypatch)
    selected = _entry("invalid-baseline")
    host, pending, calls, _page = _host(selected)

    MainWindow._check_timeline_paper_prerequisites(host, selected)
    assert calls == [(selected, True)]
    pending[0]("baseline reader returned an invalid object")

    assert _DialogSpy.instances == []
    assert host.product_shell.routes == []


def test_current_verified_entry_opens_dialog_and_status_signal_routes_once(monkeypatch):
    _install_dialog_spy(monkeypatch)
    selected = _entry("verified-baseline")
    host, pending, calls, _page = _host(selected)

    MainWindow._check_timeline_paper_prerequisites(host, selected)
    assert calls == [(selected, True)]
    pending[0]((selected.reference, None))

    assert len(_DialogSpy.instances) == 1
    dialog = _DialogSpy.instances[0]
    assert dialog.entry is selected
    assert dialog.parent is host
    assert dialog.open_count == 1
    assert host.research_timeline_view.selected_entry is selected
    assert host.product_shell.routes == []

    dialog.paperStatusRequested.emit()
    assert dialog.close_count == 1
    assert host.product_shell.routes == ["paper"]
    assert host.research_timeline_view.selected_entry is selected

