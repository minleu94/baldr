from __future__ import annotations

import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication, QFrame, QLabel, QPushButton

from app_module.dtos.portfolio_dtos import JournalEntryDTO
from app_module.research_timeline_dtos import ResearchTimelineEntry, ResearchTimelineReadResult
from app_module.research_session.session_dtos import ResearchStockContextDTO
from app_module.stock_research_report_dtos import StockPricePointDTO, StockResearchReportDTO
from app_module.stock_research_report_notes import StockResearchReportNote
from app_module.stock_research_report_snapshot_codec import (
    create_stock_research_report_projection_snapshot,
)
from ui_qt.main import MainWindow
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


def _entry(
    record_id: str,
    recorded_at: str,
    *,
    kind: str = "manual",
    text: str = "原始判斷",
    data_date: str = "",
    source_identity: str | None = None,
):
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
        data_date=data_date,
        source_identity=source_identity if source_identity is not None else f"identity-{record_id}",
    )


def _report_entry(
    record_id: str,
    *,
    source_date: str = "2026-10-16",
    price_dates: tuple[str, ...] = ("2026-09-23",),
) -> ResearchTimelineEntry:
    recorded_at = "2026-10-20T10:00:00+00:00"
    report = StockResearchReportDTO(
        stock_code="2330",
        as_of="2026-10-16T13:30:00+08:00",
        price_points=tuple(StockPricePointDTO(data_date=value) for value in price_dates),
        read_only=True,
    )
    context = ResearchStockContextDTO(
        stock_code="2330",
        data_date=source_date,
        source_kind="scheduled_recommendation",
    )
    snapshot = create_stock_research_report_projection_snapshot(report, context)
    note = StockResearchReportNote(
        revision_id=record_id,
        snapshot=snapshot,
        text="保存時報告",
        recorded_at=recorded_at,
    )
    return ResearchTimelineEntry(
        kind="report",
        record_id=record_id,
        recorded_at=recorded_at,
        text=note.text,
        reference=note,
        stock_code="2330",
        data_date=source_date,
        source_identity=snapshot.identity_sha256,
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


def test_report_with_date_and_source_identity_emits_same_entry_for_original_and_keeps_timeline_action() -> None:
    _app()
    entry = _report_entry("dated-report")
    widget = RecentResearchWidget()
    timeline_emitted: list[object] = []
    original_emitted: list[object] = []
    widget.entryRequested.connect(timeline_emitted.append)
    widget.originalRequested.connect(original_emitted.append)
    widget.set_result(ResearchTimelineReadResult((entry,)))

    original_button = widget.findChild(QPushButton, "recentResearchOpenOriginalReport")
    timeline_button = widget.findChild(QPushButton, "recentResearchOpenEntry")
    assert original_button is not None
    assert original_button.text() == "回訪原報告"
    assert timeline_button is not None

    original_button.click()
    timeline_button.click()

    assert len(original_emitted) == 1
    assert original_emitted[0] is entry
    assert len(timeline_emitted) == 1
    assert timeline_emitted[0] is entry
    widget.close()


def test_report_card_separates_original_source_date_from_typed_saved_price_date() -> None:
    _app()
    widget = RecentResearchWidget()
    widget.set_result(ResearchTimelineReadResult((_report_entry("dated-report"),)))

    metadata = widget.findChild(QLabel, "recentResearchEntryMetadata")
    assert metadata is not None
    assert "保存時間 2026-10-20T10:00:00+00:00" in metadata.text()
    assert "原研究來源日 2026-10-16" in metadata.text()
    assert "行情日 2026-09-23" in metadata.text()
    widget.close()


def test_report_card_does_not_borrow_source_date_when_typed_saved_prices_are_missing() -> None:
    _app()
    widget = RecentResearchWidget()
    widget.set_result(ResearchTimelineReadResult((
        _report_entry("missing-prices", price_dates=()),
    )))

    metadata = widget.findChild(QLabel, "recentResearchEntryMetadata")
    assert metadata is not None
    assert "原研究來源日 2026-10-16" in metadata.text()
    assert "行情日 原件未提供" in metadata.text()
    widget.close()


def test_report_card_marks_blank_typed_last_price_date_as_missing() -> None:
    _app()
    widget = RecentResearchWidget()
    widget.set_result(ResearchTimelineReadResult((
        _report_entry("blank-price-date", price_dates=("",)),
    )))

    metadata = widget.findChild(QLabel, "recentResearchEntryMetadata")
    assert metadata is not None
    assert "原研究來源日 2026-10-16" in metadata.text()
    assert "行情日 原件未提供" in metadata.text()
    widget.close()


def test_report_card_requires_typed_saved_note_for_market_date() -> None:
    _app()
    entry = _entry(
        "untyped-report",
        "2026-10-20T10:00:00+00:00",
        kind="report",
        data_date="2026-10-16",
        source_identity="e" * 64,
    )
    widget = RecentResearchWidget()
    widget.set_result(ResearchTimelineReadResult((entry,)))

    metadata = widget.findChild(QLabel, "recentResearchEntryMetadata")
    assert metadata is not None
    assert "原研究來源日 2026-10-16" in metadata.text()
    assert "行情日 原件未提供" in metadata.text()
    widget.close()


@pytest.mark.parametrize(
    ("kind", "data_date", "source_identity"),
    (
        ("report", "", "a" * 64),
        ("report", "2026-10-19", ""),
        ("price", "2026-10-19", "a" * 64),
        ("theme", "2026-10-19", "a" * 64),
        ("manual", "2026-10-19", "a" * 64),
    ),
)
def test_original_report_action_requires_report_kind_and_complete_provenance(
    kind: str,
    data_date: str,
    source_identity: str,
) -> None:
    _app()
    widget = RecentResearchWidget()
    widget.set_result(ResearchTimelineReadResult((
        _entry(
            "not-eligible",
            "2026-10-20T10:00:00+00:00",
            kind=kind,
            data_date=data_date,
            source_identity=source_identity,
        ),
    )))

    assert widget.findChild(QPushButton, "recentResearchOpenOriginalReport") is None
    assert widget.findChild(QPushButton, "recentResearchOpenEntry") is not None
    widget.close()


class _RecentReportOriginalHost:
    def __init__(self, *, select_result: bool = True, shutting_down: bool = False) -> None:
        self._shutdown_close_requested = shutting_down
        self.select_result = select_result
        self.selected: list[object] = []
        self.routes: list[str] = []
        self.original_requests: list[tuple[object, str]] = []
        self.status_messages: list[str] = []
        self.research_timeline_view = self
        self.product_shell = self

    def select_entry(self, entry: object) -> bool:
        self.selected.append(entry)
        return self.select_result

    def activate_route(self, route: str) -> None:
        self.routes.append(route)

    def _open_timeline_original(self, entry: object, *, return_route: str) -> None:
        self.original_requests.append((entry, return_route))

    def statusBar(self):
        return self

    def showMessage(self, message: str) -> None:
        self.status_messages.append(message)


def test_main_handler_routes_the_same_eligible_entry_through_original_reader() -> None:
    entry = _report_entry("dated-main-report")
    host = _RecentReportOriginalHost()

    MainWindow._open_recent_report_original(host, entry)

    assert len(host.selected) == 1 and host.selected[0] is entry
    assert host.routes == ["journal"]
    assert len(host.original_requests) == 1
    assert host.original_requests[0][0] is entry
    assert host.original_requests[0][1] == "overview"


def test_main_handler_rejects_stale_selection_before_route_or_original_reader() -> None:
    selected_entry = _entry(
        "same-record",
        "2026-10-20T10:00:00+00:00",
        kind="report",
        data_date="2026-10-19",
        source_identity="c" * 64,
    )
    stale_entry = _entry(
        "same-record",
        "2026-10-20T10:00:00+00:00",
        kind="report",
        data_date="2026-10-19",
        source_identity="c" * 64,
    )
    assert stale_entry is not selected_entry
    host = _RecentReportOriginalHost(select_result=False)

    MainWindow._open_recent_report_original(host, stale_entry)

    assert len(host.selected) == 1 and host.selected[0] is stale_entry
    assert host.routes == []
    assert host.original_requests == []
    assert host.status_messages
    assert "重新讀取" in host.status_messages[0]


@pytest.mark.parametrize(
    ("kind", "data_date", "source_identity", "shutting_down"),
    (
        ("report", "2026-10-19", "d" * 64, True),
        ("price", "2026-10-19", "d" * 64, False),
        ("report", "", "d" * 64, False),
        ("report", "2026-10-19", "", False),
    ),
)
def test_main_handler_rejects_shutdown_wrong_kind_and_missing_report_provenance(
    kind: str,
    data_date: str,
    source_identity: str,
    shutting_down: bool,
) -> None:
    entry = _entry(
        "rejected-main-report",
        "2026-10-20T10:00:00+00:00",
        kind=kind,
        data_date=data_date,
        source_identity=source_identity,
    )
    host = _RecentReportOriginalHost(shutting_down=shutting_down)

    MainWindow._open_recent_report_original(host, entry)

    assert host.selected == []
    assert host.routes == []
    assert host.original_requests == []
