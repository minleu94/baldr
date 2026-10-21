from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QTextEdit

from app_module.dtos.portfolio_dtos import JournalEntryDTO
from app_module.research_timeline_dtos import ResearchTimelineEntry, ResearchTimelineReadResult
from ui_qt.views.research_timeline_view import ResearchTimelineView
from ui_qt.widgets.research_paper_prerequisite_dialog import (
    ResearchPaperPrerequisiteDialog,
)


_APPLICATION: QApplication | None = None


def _app() -> QApplication:
    global _APPLICATION
    if _APPLICATION is not None:
        return _APPLICATION
    instance = QApplication.instance()
    _APPLICATION = instance if instance is not None else QApplication(sys.argv)
    return _APPLICATION


def _entry(
    *,
    kind: str = "report",
    record_id: str = "saved-note-42",
    stock_code: str = "2330",
    data_date: str = "2026-10-20",
    source_identity: str = "a" * 64,
    text: str = "保存當時的研究判斷\n第二行仍保留。",
) -> ResearchTimelineEntry:
    reference = JournalEntryDTO(
        journal_id=record_id,
        portfolio_id="default",
        body=text,
        stock_code=stock_code,
        created_at="2026-10-21T08:30:00+00:00",
        revision_id=record_id,
    )
    return ResearchTimelineEntry(
        kind=kind, record_id=record_id, recorded_at="2026-10-21T08:30:00+00:00",
        text=text, reference=reference, stock_code=stock_code, data_date=data_date,
        source_identity=source_identity,
    )


class _Reader:
    def __init__(self, result: ResearchTimelineReadResult) -> None:
        self.result = result
        self.calls = 0

    def read(self, cancel_callback=None) -> ResearchTimelineReadResult:
        self.calls += 1
        return self.result


def test_dialog_shows_saved_identity_and_readonly_original_without_enabling_account_creation():
    _app()
    source_identity = "0123456789abcdef" * 4
    original = "保存原文 <b>純文字</b>\n不可在 Paper 條件視窗改寫。"
    entry = _entry(source_identity=source_identity, text=original)
    dialog = ResearchPaperPrerequisiteDialog(entry)

    assert dialog.objectName() == "researchPaperPrerequisiteDialog"
    assert "報告判斷" in dialog.metadata_text.text()
    assert entry.record_id in dialog.metadata_text.text()
    assert "2330" in dialog.metadata_text.text()
    assert "2026-10-21T08:30:00+00:00" in dialog.metadata_text.text()
    assert "2026-10-20" in dialog.metadata_text.text()
    assert dialog.source_identity_text.toPlainText() == source_identity
    assert dialog.source_identity_text.isReadOnly()
    assert dialog.source_identity_text.lineWrapMode() == QTextEdit.LineWrapMode.WidgetWidth
    assert dialog.source_identity_text.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    assert dialog.original_text.toPlainText() == original
    assert dialog.original_text.isReadOnly()
    assert not dialog.create_account_button.isEnabled()
    assert "現行建帳流程尚未支援直接納入此研究" in dialog.blockers_label.text()
    assert "既有 Paper 帳本與等權重比較基準不能代替" in dialog.blockers_label.text()

    requested: list[bool] = []
    dialog.paperStatusRequested.connect(lambda: requested.append(True))
    dialog.show()
    assert dialog.isVisible()
    dialog.paper_status_button.click()
    assert requested == [True]
    assert dialog.isVisible()

    dialog.close_button.click()
    assert not dialog.isVisible()
    dialog.deleteLater()


def test_dialog_marks_missing_optional_metadata_instead_of_inventing_values():
    _app()
    entry = _entry(
        kind="manual", stock_code="", data_date="", source_identity="", text="只有原文。"
    )
    dialog = ResearchPaperPrerequisiteDialog(entry)

    assert "手動筆記" in dialog.metadata_text.text()
    assert "股票：未提供" in dialog.metadata_text.text()
    assert "資料日：未提供" in dialog.metadata_text.text()
    assert dialog.source_identity_text.toPlainText() == "未提供來源身份"
    assert dialog.original_text.toPlainText() == "只有原文。"
    assert not dialog.create_account_button.isEnabled()
    dialog.close()
    dialog.deleteLater()


def test_timeline_emits_only_selected_entry_and_does_not_read_or_write_paper_state():
    _app()
    first = _entry(record_id="paper-first")
    second = _entry(kind="manual", record_id="paper-second", text="另一筆保存研究。")
    result = ResearchTimelineReadResult((first, second))
    reader = _Reader(result)
    view = ResearchTimelineView(reader, auto_refresh=False)
    assert not view.paper_prerequisites_button.isEnabled()
    assert reader.calls == 0

    view._receive(view._generation, result)
    assert view.selected_entry is first
    assert view.paper_prerequisites_button.isEnabled()
    emitted: list[object] = []
    view.paperPrerequisitesRequested.connect(emitted.append)
    view.paper_prerequisites_button.click()

    assert emitted == [first]
    assert emitted[0] is first
    assert view.last_result is result
    assert reader.calls == 0
    assert view.selected_entry is first

    assert view.select_entry(second)
    view.paper_prerequisites_button.click()
    assert emitted == [first, second]
    assert emitted[-1] is second
    assert reader.calls == 0

    view.request_close()
    assert not view.paper_prerequisites_button.isEnabled()
    view.close()
    view.deleteLater()
