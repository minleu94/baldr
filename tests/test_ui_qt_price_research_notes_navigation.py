"""F07 個股判斷筆記沿正常價格研究頁導航與關閉整合。"""

from __future__ import annotations

import time
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from typing import Any, Callable, cast

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QMainWindow, QTabWidget, QWidget

pytest_plugins = ("tests.test_daily_market_technical_universe_price_query_v1",)

from app_module.daily_market_technical_universe_price_bookmark_v1 import (
    DailyMarketTechnicalUniversePriceBookmarkStateV1,
    DailyMarketTechnicalUniversePriceBookmarkV1,
)
from app_module.daily_market_technical_universe_price_comparison_v1 import (
    DailyMarketTechnicalUniversePriceSelectionV1,
)
from app_module.daily_market_technical_universe_price_query_v1 import (
    DailyMarketTechnicalUniversePriceReadSessionV1,
    open_daily_market_technical_universe_price_read_session_v1,
)
from app_module.journal_service import JournalService
from app_module.personal_journal_paths import resolve_personal_journal_paths
from app_module.pinned_stock_research_notes import (
    PinnedStockResearchNote,
    PinnedStockResearchNoteSaveReadback,
    PinnedStockResearchNoteService,
    PinnedStockResearchSource,
    verify_pinned_stock_research_source,
)
from ui_qt.main import MainWindow
from ui_qt.views.stock_research_workspace import StockResearchWorkspace


def _open_session(fixture: dict[str, Any]) -> DailyMarketTechnicalUniversePriceReadSessionV1:
    plan = fixture["plan"]
    receipt = fixture["receipt"]
    return open_daily_market_technical_universe_price_read_session_v1(
        store_output_root=fixture["store_root"],
        generation_identity_sha256=plan.generation_identity_sha256,
        plan_identity_sha256=plan.identity_sha256,
        plan_sha256=fixture["plan_sha256"],
        receipt_identity_sha256=receipt.identity_sha256,
        receipt_sha256=receipt.content_sha256,
    )


def _selections(
    fixture: dict[str, Any],
) -> tuple[
    tuple[object, object],
    tuple[
        DailyMarketTechnicalUniversePriceSelectionV1,
        DailyMarketTechnicalUniversePriceSelectionV1,
    ],
]:
    session = _open_session(fixture)
    query = session.create_query(unknown_price_policy="include")
    result = session.execute(query)
    request = result.create_page_request(0, page_size=4)
    page = result.read_page(request)
    stocks = tuple(result.read_stock_snapshot(request, code) for code in ("S0001", "S0002"))
    selections = tuple(
        DailyMarketTechnicalUniversePriceSelectionV1.from_page(query, page, code)
        for code in ("S0001", "S0002")
    )
    return cast(tuple[object, object], stocks), cast(
        tuple[
            DailyMarketTechnicalUniversePriceSelectionV1,
            DailyMarketTechnicalUniversePriceSelectionV1,
        ],
        selections,
    )


def _journal_note_service(tmp_path: Path) -> PinnedStockResearchNoteService:
    data_root = tmp_path / "FA_Data"
    paths = resolve_personal_journal_paths(
        data_root,
        personal_root=data_root / "personal",
    )
    journal = JournalService(
        SimpleNamespace(output_root=paths.personal_paths.legacy_output_root),
        journal_paths=paths,
    )
    return PinnedStockResearchNoteService(journal)


def _bookmark(
    selection: DailyMarketTechnicalUniversePriceSelectionV1,
) -> DailyMarketTechnicalUniversePriceBookmarkV1:
    return DailyMarketTechnicalUniversePriceBookmarkV1.create(
        selected=selection,
        scroll_position=0,
    )


def _wait(
    app: QApplication,
    predicate: Callable[[], bool],
    *,
    timeout_seconds: float = 30.0,
    diagnostic: Callable[[], str] | None = None,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    while not predicate():
        app.processEvents()
        if time.monotonic() >= deadline:
            detail = diagnostic() if diagnostic is not None else "無 notes 診斷來源"
            raise AssertionError(f"F07 個股筆記導航背景工作逾時；{detail}")
        QTest.qWait(10)
        time.sleep(0.001)
    app.processEvents()


def _notes_wait_diagnostic(notes: Any) -> str:
    status_label = getattr(notes, "status_label", None)
    status_text = status_label.text() if callable(getattr(status_label, "text", None)) else status_label
    return (
        f"active_job={getattr(notes, '_active_job', None)!r}; "
        f"outcome={getattr(notes, '_active_outcome', None)!r}; "
        f"native_finished={getattr(notes, '_active_native_finished', None)!r}; "
        f"status_label={status_text!r}; "
        f"source_error={getattr(notes, '_source_error', None)!r}"
    )


class _NoGeneralRead:
    def read_report(self, *_args: object, **_kwargs: object) -> object:
        raise AssertionError("F07 原價格研究不可改讀一般價庫")


class _PriceBookmarkRouteHost(QMainWindow):
    """只提供 MainWindow 原 bookmark route 所需的 Qt 導航容器。"""

    def __init__(self, daily: QWidget) -> None:
        super().__init__()
        self._shutdown_close_requested = False
        self.workspace_selections: list[str] = []
        tabs = QTabWidget(self)
        tabs.addTab(QLabel("其他工作區", tabs), "其他")
        tabs.addTab(daily, "每日研究")
        self.setCentralWidget(tabs)
        self.result_source_tabs = tabs
        self.recommendation_view = SimpleNamespace(
            daily_market_research_view=daily,
            result_source_tabs=tabs,
        )

    def _select_main_workspace(self, workspace: str) -> None:
        self.workspace_selections.append(workspace)


@pytest.fixture(scope="module")
def app() -> QApplication:
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication([])
    return cast(QApplication, instance)


def test_price_notes_tab_stays_persistent_and_drops_old_revision_parent(
    app: QApplication,
    exact_price_store: dict[str, Any],
    tmp_path: Path,
) -> None:
    service = _journal_note_service(tmp_path)
    (first_stock, second_stock), (first_selection, second_selection) = _selections(
        exact_price_store
    )
    first_bookmark = _bookmark(first_selection)
    first_source = verify_pinned_stock_research_source(first_bookmark)
    service.save(first_source, "S0001 的原版本筆記", revision_id="navigation-s0001-root")

    workspace = StockResearchWorkspace(
        cast(Any, _NoGeneralRead()),
        price_note_service=service,
    )
    workspace.resize(900, 720)
    workspace.show()
    try:
        workspace.show_price_research(first_stock, first_selection)
        first_view = workspace.price_research_view
        notes = workspace.price_notes_widget
        assert first_view is not None and notes is not None
        _wait(
            app,
            lambda: not notes.is_busy()
            and notes._verified_source is not None
            and notes._verified_source.stock_code == "S0001",
            diagnostic=lambda: _notes_wait_diagnostic(notes),
        )
        first_tab = first_view.detail_tabs.indexOf(workspace.price_notes_page)
        assert workspace.price_notes_page.widget() is notes
        assert workspace.price_notes_page.widgetResizable()
        assert first_tab >= 0
        assert first_view.detail_tabs.tabText(first_tab) == "我的判斷"
        assert notes._bookmark is not None
        assert notes._bookmark.to_json() == first_bookmark.to_json()
        assert notes._verified_source is not None
        assert notes._verified_source.identity_sha256 == first_bookmark.bookmark_identity_sha256

        revision_index = notes.revisions.findData(
            "navigation-s0001-root",
            Qt.ItemDataRole.UserRole,
        )
        assert revision_index >= 0
        notes.revisions.setCurrentIndex(revision_index)
        notes.read_button.click()
        _wait(
            app,
            lambda: not notes.is_busy()
            and notes._loaded_note is not None
            and notes._loaded_note.revision_id == "navigation-s0001-root"
            and notes._loaded_source_state is not None,
        )
        notes.revise_button.click()
        assert notes._draft_revision_of == "navigation-s0001-root"
        assert notes.editor.toPlainText() == "S0001 的原版本筆記"

        workspace.show_price_research(second_stock, second_selection)
        second_view = workspace.price_research_view
        assert second_view is not None and second_view is not first_view
        assert workspace.price_notes_widget is notes
        assert first_view.detail_tabs.indexOf(workspace.price_notes_page) == -1
        second_tab = second_view.detail_tabs.indexOf(workspace.price_notes_page)
        assert second_tab >= 0
        assert second_view.detail_tabs.tabText(second_tab) == "我的判斷"
        second_bookmark = _bookmark(second_selection)
        assert notes._bookmark is not None
        assert notes._bookmark.to_json() == second_bookmark.to_json()
        assert notes._draft_revision_of is None
        assert notes._selected_revision_id() is None

        _wait(
            app,
            lambda: not notes.is_busy()
            and notes._verified_source is not None
            and notes._verified_source.stock_code == "S0002",
        )
        assert notes._verified_source is not None
        assert notes._verified_source.identity_sha256 == second_bookmark.bookmark_identity_sha256
        assert "navigation-s0001-root" not in notes._notes_by_id
        assert notes._loaded_note is None
        assert notes._draft_source is not None
        assert notes._draft_source.identity_sha256 == first_bookmark.bookmark_identity_sha256
        assert not notes.save_button.isEnabled()
    finally:
        workspace.request_close()
        workspace.close()
        app.processEvents()


def test_open_source_signal_uses_existing_main_bookmark_route(
    app: QApplication,
    exact_price_store: dict[str, Any],
    tmp_path: Path,
) -> None:
    service = _journal_note_service(tmp_path)
    (stock, _), (selection, _) = _selections(exact_price_store)
    expected_bookmark = _bookmark(selection)
    source = verify_pinned_stock_research_source(expected_bookmark)
    service.save(source, "供原版本返回測試", revision_id="navigation-route-root")

    workspace = StockResearchWorkspace(
        cast(Any, _NoGeneralRead()),
        price_note_service=service,
    )
    daily = QWidget()
    route_calls: list[tuple[str, object | None]] = []

    def restore(value: object) -> bool:
        route_calls.append(("restore", value))
        return True

    def open_selected_stock() -> bool:
        route_calls.append(("open_selected_stock", None))
        return True

    daily._shutting_down = False  # type: ignore[attr-defined]
    daily.technical_price_view = SimpleNamespace(  # type: ignore[attr-defined]
        restore_bookmark_state=restore,
        open_selected_stock=open_selected_stock,
    )
    host = _PriceBookmarkRouteHost(daily)
    workspace.resize(900, 720)
    workspace.show()
    host.show()
    try:
        workspace.show_price_research(stock, selection)
        notes = workspace.price_notes_widget
        assert notes is not None
        _wait(
            app,
            lambda: not notes.is_busy()
            and notes._verified_source is not None
            and notes._verified_source.identity_sha256 == expected_bookmark.bookmark_identity_sha256,
            diagnostic=lambda: _notes_wait_diagnostic(notes),
        )
        revision_index = notes.revisions.findData(
            "navigation-route-root",
            Qt.ItemDataRole.UserRole,
        )
        assert revision_index >= 0
        notes.revisions.setCurrentIndex(revision_index)
        notes.read_button.click()
        _wait(
            app,
            lambda: not notes.is_busy()
            and notes._loaded_note is not None
            and notes._loaded_source_state is not None,
        )

        emitted: list[object] = []
        workspace.priceNoteSourceRequested.connect(
            lambda value: MainWindow._open_price_bookmark_state(
                cast(MainWindow, host), value
            )
        )
        workspace.priceNoteSourceRequested.connect(emitted.append)
        notes.open_source_button.click()
        _wait(app, lambda: not notes.is_busy() and len(emitted) == 1,
              diagnostic=lambda: _notes_wait_diagnostic(notes))

        assert len(emitted) == 1
        state = emitted[0]
        state = cast(DailyMarketTechnicalUniversePriceBookmarkStateV1, state)
        assert type(state) is DailyMarketTechnicalUniversePriceBookmarkStateV1
        assert state.bookmark.to_json() == expected_bookmark.to_json()
        assert route_calls == [("restore", state), ("open_selected_stock", None)]
        assert host.workspace_selections == ["recommendation"]
        assert host.result_source_tabs.currentWidget() is daily
    finally:
        workspace.request_close()
        workspace.close()
        host.close()
        app.processEvents()


def test_pending_note_write_keeps_workspace_close_not_ready(
    app: QApplication,
    exact_price_store: dict[str, Any],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _journal_note_service(tmp_path)
    (stock, _), (selection, _) = _selections(exact_price_store)
    workspace = StockResearchWorkspace(
        cast(Any, _NoGeneralRead()),
        price_note_service=service,
    )
    workspace.resize(900, 720)
    workspace.show()
    release_write = Event()
    write_started = Event()
    notes = workspace.price_notes_widget
    assert notes is not None
    try:
        workspace.show_price_research(stock, selection)
        _wait(
            app,
            lambda: not notes.is_busy()
            and notes._verified_source is not None
            and notes._verified_source.stock_code == "S0001",
            diagnostic=lambda: _notes_wait_diagnostic(notes),
        )
        notes.editor.setPlainText("關閉時需等待的筆記")
        assert notes.save_button.isEnabled()
        original_save = service.save_with_readback

        def blocked_save(
            source: PinnedStockResearchSource,
            text: str,
            *,
            revision_id: str,
            revision_of: str | None = None,
        ) -> PinnedStockResearchNoteSaveReadback:
            write_started.set()
            if not release_write.wait(timeout=30.0):
                raise TimeoutError("測試寫入等待未收到釋放訊號")
            return original_save(
                source,
                text,
                revision_id=revision_id,
                revision_of=revision_of,
            )

        monkeypatch.setattr(service, "save_with_readback", blocked_save)
        notes.save_button.click()
        _wait(app, write_started.is_set)
        assert notes.has_pending_write()
        assert workspace.request_close() is False
        assert notes.has_pending_write()
        assert notes.is_busy()
    finally:
        release_write.set()
        if notes.is_busy():
            _wait(app, lambda: not notes.is_busy())
        workspace.close()
        app.processEvents()


def test_workspace_without_note_service_keeps_exact_price_research_entry(
    app: QApplication,
    exact_price_store: dict[str, Any],
) -> None:
    (stock, _), (selection, _) = _selections(exact_price_store)
    workspace = StockResearchWorkspace(cast(Any, _NoGeneralRead()))
    workspace.resize(900, 720)
    workspace.show()
    try:
        assert workspace.price_notes_widget is None
        returned: list[object] = []
        workspace.priceResearchReturnRequested.connect(returned.append)

        workspace.show_price_research(stock, selection)
        app.processEvents()
        price_view = workspace.price_research_view
        assert price_view is not None and price_view.isVisible()
        assert price_view._origin_selection == selection
        assert "我的判斷" not in tuple(
            price_view.detail_tabs.tabText(index)
            for index in range(price_view.detail_tabs.count())
        )

        price_view.return_button.click()
        assert returned == [selection]
        assert workspace.request_close()
    finally:
        workspace.close()
        app.processEvents()
