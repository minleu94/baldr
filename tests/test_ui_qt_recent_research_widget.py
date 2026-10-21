from __future__ import annotations

import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication, QFrame, QLabel, QPushButton

from app_module.dtos.portfolio_dtos import JournalEntryDTO
from app_module.research_timeline_dtos import ResearchTimelineEntry, ResearchTimelineReadResult
from ui_qt.widgets.recent_research_widget import RecentResearchWidget

_APPLICATION: QApplication | None = None


def _app() -> QApplication:
    global _APPLICATION
    if _APPLICATION is not None:
        return _APPLICATION
    instance = QApplication.instance()
    _APPLICATION = instance if instance is not None else QApplication(sys.argv)
    return _APPLICATION


@pytest.fixture(autouse=True)
def _keep_qt_application_and_drain_deferred_deletes():
    application = _app()
    existing_windows = set(application.topLevelWidgets())
    yield
    for widget in application.topLevelWidgets():
        if widget not in existing_windows:
            widget.close()
            widget.deleteLater()
    application.processEvents()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    application.processEvents()


def _entry(record_id: str, recorded_at: str, *, kind: str = "manual", text: str = "原始判斷"):
    reference = JournalEntryDTO(
        journal_id=record_id,
        portfolio_id="default",
        body=text,
        stock_code="2330",
        created_at=recorded_at,
        revision_id=record_id,
    )
    return ResearchTimelineEntry(
        kind=kind,
        record_id=record_id,
        recorded_at=recorded_at,
        text=text,
        reference=reference,
        stock_code="2330",
        data_date="",
        source_identity=f"identity-{record_id}",
    )


def test_widget_projects_at_most_three_aware_entries_and_emits_original_entry() -> None:
    _app()
    entries = tuple(
        _entry(f"entry-{index}", f"2026-10-{20-index:02d}T10:00:00+00:00", text=f"判斷 {index}")
        for index in range(5)
    )
    widget = RecentResearchWidget()
    emitted: list[object] = []
    widget.entryRequested.connect(emitted.append)

    widget.set_result(ResearchTimelineReadResult(entries))

    cards = widget.findChildren(QFrame, "recentResearchEntry")
    assert len(cards) == 3
    assert widget.entries_layout.count() == 3
    assert "顯示 3 筆" in widget.status_label.text()
    metadata = widget.entries_layout.itemAt(0).widget().findChild(
        QLabel, "recentResearchEntryMetadata"
    )
    assert metadata is not None
    assert "資料日 原件未提供" in metadata.text()

    button = widget.findChild(QPushButton, "recentResearchOpenEntry")
    assert button is not None
    assert button.text() == "開啟研究紀錄與覆盤"
    button.click()
    assert emitted == [entries[0]]
    widget.close()


def test_unknown_or_naive_timestamps_are_not_presented_as_recent() -> None:
    _app()
    widget = RecentResearchWidget()
    widget.set_result(ResearchTimelineReadResult((
        _entry("naive", "2026-10-20T10:00:00"),
        _entry("invalid", "unknown"),
    )))

    assert widget.entries_layout.count() == 0
    assert "沒有保存時間明確的最近研究" in widget.status_label.text()
    assert widget.findChild(QPushButton, "recentResearchOpenEntry") is None
    widget.close()


def test_limited_and_warning_results_are_marked_incomplete() -> None:
    _app()
    widget = RecentResearchWidget()
    widget.set_result(ResearchTimelineReadResult(
        (_entry("latest", "2026-10-20T10:00:00+00:00", kind="report"),),
        warnings=("theme lane 讀取失敗",),
        limited=True,
    ))

    assert "不是完整歷史" in widget.status_label.text()
    assert "列表可能不完整" in widget.status_label.text()
    assert "theme lane 讀取失敗" in widget.status_label.text()
    widget.close()


def test_unavailable_read_clears_old_snapshot_and_missing_provenance_is_explicit() -> None:
    _app()
    widget = RecentResearchWidget()
    entry = _entry("missing", "2026-10-20T10:00:00+00:00")
    entry = ResearchTimelineEntry(
        kind=entry.kind,
        record_id=entry.record_id,
        recorded_at=entry.recorded_at,
        text=entry.text,
        reference=entry.reference,
    )
    widget.set_result(ResearchTimelineReadResult((entry,)))
    hint = widget.findChild(QLabel, "recentResearchEntryEvidenceHint")
    assert hint is not None
    assert "缺少資料日、來源身份；原件未提供這些欄位" in hint.text()

    widget.set_unavailable("時間軸讀取失敗。")
    assert widget.entries_layout.count() == 0
    assert widget.status_label.text() == "時間軸讀取失敗。"
    widget.close()
