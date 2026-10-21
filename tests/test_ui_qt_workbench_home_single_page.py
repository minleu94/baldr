"""今日總覽共用 Workbench read model 的單頁導覽契約。"""

from __future__ import annotations

import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication, QPushButton

from ui_qt.views.research_console_view import ResearchConsoleView
from ui_qt.views.workbench_view import UnifiedDecisionWorkbenchView
from ui_qt.widgets.recent_research_widget import RecentResearchWidget

_APPLICATION: QApplication | None = None


def _app() -> QApplication:
    global _APPLICATION
    if _APPLICATION is not None:
        return _APPLICATION
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication(sys.argv)
    _APPLICATION = instance
    return _APPLICATION


@pytest.fixture(autouse=True)
def _keep_qt_application_and_drain_deferred_deletes():
    application = _app()
    existing_windows = set(application.topLevelWidgets())
    yield
    owned_windows = [
        widget for widget in application.topLevelWidgets()
        if widget not in existing_windows
    ]
    for widget in owned_windows:
        shutdown = getattr(widget, "begin_shutdown", None)
        if callable(shutdown):
            shutdown()
        worker = getattr(widget, "_refresh_worker", None)
        if worker is not None and worker.isRunning():
            worker.cancel(cooperative=True, wait=False)
            assert worker.wait(5000), "Workbench refresh worker 未能自然停止"
    application.processEvents()
    for widget in owned_windows:
        widget.close()
        widget.deleteLater()
    application.processEvents()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    application.processEvents()


def test_home_is_one_visible_page_with_existing_summary_widgets() -> None:
    _app()
    view = UnifiedDecisionWorkbenchView(auto_refresh=False)
    try:
        home = view.overview_scroll_area.widget()
        assert view.subtabs.tabBar().isHidden()
        assert view.subtabs.widget(0) is not None
        assert view.advanced_workbench_panel.is_collapsed()

        for widget in (
            view.guided_home_panel,
            view.position_health_panel,
            view.today_action_panel,
            view.daily_investment_journey_panel,
            view.advanced_workbench_panel,
        ):
            assert widget.parentWidget() is home

        assert view.home_theme_summary_label.text().startswith("尚未載入題材研究版本")
        assert view.home_research_evidence_button.isEnabled()
        assert view.home_advanced_button.isEnabled()
    finally:
        view.begin_shutdown()
        view.close()


def test_auxiliary_pages_have_explicit_entry_and_return_without_new_view() -> None:
    _app()
    view = UnifiedDecisionWorkbenchView(auto_refresh=False)
    try:
        original_console = view.research_console_view
        assert isinstance(original_console, ResearchConsoleView)

        view.home_research_evidence_button.click()
        assert view.subtabs.currentWidget() is original_console
        assert not view.auxiliary_navigation_row.isHidden()
        assert view.auxiliary_page_title.text() == "研究證據"
        assert view.return_home_button.text() == "返回今日總覽"

        view.return_home_button.click()
        assert view.subtabs.currentIndex() == 0
        assert view.auxiliary_navigation_row.isHidden()
        assert view.research_console_view is original_console

        for index, label in enumerate(("決策來源", "研究證據", "持倉追蹤", "操作節奏")):
            button = view.findChild(QPushButton, f"workbenchAuxiliaryAction{index}")
            assert button is not None
            button.click()
            assert view.subtabs.tabText(view.subtabs.currentIndex()) == label
            assert view.auxiliary_page_title.text() == label
            view.return_to_home()
            assert view.subtabs.currentIndex() == 0
    finally:
        view.begin_shutdown()
        view.close()


def test_advanced_action_expands_existing_details_in_place() -> None:
    _app()
    view = UnifiedDecisionWorkbenchView(auto_refresh=False)
    try:
        content = view.overview_scroll_area.widget()
        assert view.advanced_workbench_panel.parentWidget() is content
        assert view.advanced_workbench_panel.is_collapsed()
        view.home_advanced_button.click()
        assert not view.advanced_workbench_panel.is_collapsed()
        assert view.subtabs.currentIndex() == 0
        assert view.evidence_feed_table.model() is view.evidence_feed_model
        assert view.action_item_table.model() is view.action_item_model
    finally:
        view.begin_shutdown()
        view.close()


def test_recent_research_mount_uses_existing_home_and_entry_callback() -> None:
    _app()
    view = UnifiedDecisionWorkbenchView(auto_refresh=False)
    widget = RecentResearchWidget()
    received: list[object] = []
    entry = object()
    try:
        view.mount_recent_research_widget(widget, received.append)
        content = view.overview_scroll_area.widget()
        assert widget.parentWidget() is content
        assert content.layout().itemAt(6).widget() is widget
        widget.entryRequested.emit(entry)
        assert received == [entry]
        view.mount_recent_research_widget(widget, received.append)
        widget.entryRequested.emit(entry)
        assert received == [entry, entry]
    finally:
        view.begin_shutdown()
        view.close()
