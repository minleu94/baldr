"""今日總覽共用 Workbench read model 的單頁導覽契約。"""

from __future__ import annotations

import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication, QLabel, QPushButton

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
    application = _app()
    view = UnifiedDecisionWorkbenchView(auto_refresh=False)
    try:
        view.resize(1280, 900)
        view.show()
        application.processEvents()
        home = view.overview_scroll_area.widget()
        assert view.subtabs.tabBar().isHidden()
        assert view.subtabs.widget(0) is not None
        assert view.advanced_workbench_panel.is_collapsed()
        assert view.home_secondary_panel.is_collapsed()

        home_layout = home.layout()
        visible_widgets = [
            home_layout.itemAt(index).widget()
            for index in range(home_layout.count())
            if home_layout.itemAt(index).widget() is not None
        ]
        assert visible_widgets.index(view.daily_investment_journey_panel) < visible_widgets.index(
            view.advice_panel
        )
        assert visible_widgets.index(view.advice_panel) < visible_widgets.index(
            view.home_secondary_panel
        )

        for widget in (
            view.guided_home_panel,
            view.position_health_panel,
            view.today_action_panel,
        ):
            assert widget.parentWidget() is view.home_secondary_panel.content_widget
        assert view.daily_investment_journey_panel.parentWidget() is home
        assert view.advanced_workbench_panel.parentWidget() is home

        assert view.home_theme_summary_label.text().startswith("尚未載入題材研究版本")
        assert "候選資料尚未載入" in " ".join(
            label.text() for label in view.home_candidate_preview.findChildren(QLabel)
        )
        assert "不是按鈕" in view.guided_priority_status_badges["candidates"].accessibleDescription()
        assert view.home_research_evidence_button.isEnabled()
        assert view.home_advanced_button.isEnabled()
        assert view.daily_detail_button.text() == "查看每日來源詳情"
        assert view.daily_detail_button.accessibleName() == "查看每日來源、篩選與排除詳情"
        assert view.daily_detail_button.parentWidget() is view.daily_source_details_row
        assert view.daily_action_layout.indexOf(view.daily_detail_button) == -1
        journey_layout = view.daily_investment_journey_panel.layout
        assert journey_layout.indexOf(view.daily_candidate_detail_label) < journey_layout.indexOf(
            view.daily_source_details_row
        )
        assert journey_layout.indexOf(view.daily_source_details_row) < journey_layout.indexOf(
            view.home_candidate_selector_row
        ) < journey_layout.indexOf(view.daily_saved_result_row) < journey_layout.indexOf(
            view.daily_action_row
        )
        market_row = view.guided_priority_rows["market"]
        assert view.daily_market_kpi_row.parentWidget() is market_row
        assert view.daily_market_footer_label.parentWidget() is market_row
        assert not market_row.isVisible()
        view.home_secondary_panel.set_collapsed(False)
        assert market_row.isVisible()
    finally:
        view.begin_shutdown()
        view.close()


def test_auxiliary_pages_have_explicit_entry_and_return_without_new_view() -> None:
    _app()
    view = UnifiedDecisionWorkbenchView(auto_refresh=False)
    try:
        original_console = view.research_console_view
        assert isinstance(original_console, ResearchConsoleView)

        view.home_secondary_panel.set_collapsed(False)
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


def test_today_action_cards_use_four_columns_on_desktop_and_reflow_narrow() -> None:
    application = _app()
    view = UnifiedDecisionWorkbenchView(auto_refresh=False)
    try:
        view.show()
        application.processEvents()
        for width, expected_rows, expected_columns in (
            (1280, 1, 4),
            (900, 2, 2),
            (700, 4, 1),
        ):
            view.resize(width, 900)
            application.processEvents()
            positions = [
                view.today_cards_layout.getItemPosition(
                    view.today_cards_layout.indexOf(card)
                )
                for card in view.today_action_cards.values()
            ]
            assert max(row for row, _column, _row_span, _column_span in positions) + 1 == expected_rows
            assert max(column for _row, column, _row_span, _column_span in positions) + 1 == expected_columns
    finally:
        view.begin_shutdown()
        view.close()


def test_waiting_action_center_has_one_refresh_and_compact_destination_actions() -> None:
    _app()
    view = UnifiedDecisionWorkbenchView(auto_refresh=False)
    try:
        assert view.primary_action_button.isHidden()
        assert not view.refresh_button.isHidden()
        assert {
            key: (button.text(), view._today_action_targets[key])
            for key, button in view.today_action_buttons.items()
        } == {
            "data": ("查看數據更新", "update"),
            "market": ("開啟市場總覽", "daily_decision"),
            "advice": ("前往推薦分析", "recommendation"),
            "portfolio": ("開啟持倉管理", "portfolio_review"),
        }
        for button in view.today_action_buttons.values():
            assert button.maximumWidth() == 148
            assert button.minimumHeight() == 28
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
        view.home_secondary_panel.set_collapsed(False)
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
        assert widget.parentWidget() is view.home_recent_panel
        assert view.home_recent_layout.itemAt(0).widget() is widget
        widget.entryRequested.emit(entry)
        assert received == [entry]
        view.mount_recent_research_widget(widget, received.append)
        widget.entryRequested.emit(entry)
        assert received == [entry, entry]
    finally:
        view.begin_shutdown()
        view.close()


def test_theme_and_recent_research_stay_in_the_followup_row() -> None:
    _app()
    view = UnifiedDecisionWorkbenchView(auto_refresh=False)
    try:
        assert view.home_theme_panel.parentWidget() is view.guided_home_panel
        assert view.home_recent_panel.parentWidget() is view.guided_home_panel
        assert view.home_followup_layout.indexOf(view.home_theme_panel) == 0
        assert view.home_followup_layout.indexOf(view.home_recent_panel) == 1
        assert view.daily_candidate_button.styleSheet().find("QPushButton:disabled") >= 0
        assert view.daily_saved_result_button.styleSheet().find("QPushButton:disabled") >= 0
    finally:
        view.begin_shutdown()
        view.close()
