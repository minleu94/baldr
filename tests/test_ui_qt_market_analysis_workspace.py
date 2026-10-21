from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication, QTabWidget, QWidget

from ui_qt.views.market_analysis_workspace import MarketAnalysisWorkspace


class _MarketPage(QWidget):
    def __init__(self, key: str) -> None:
        super().__init__()
        self.key = key
        self.load_count = 0

    def load_data_if_needed(self) -> None:
        self.load_count += 1


@pytest.fixture
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _make_workspace(
    *, include_cohort: bool = True, include_unmapped_theme: bool = False
) -> tuple[MarketAnalysisWorkspace, QTabWidget, dict[str, _MarketPage]]:
    tabs = QTabWidget()
    keys = [
        "summary",
        "index",
        "strong_stocks",
        "weak_stocks",
        "strong_industries",
        "weak_industries",
        "flow",
    ]
    if include_cohort:
        keys.append("cohort")
    pages = {key: _MarketPage(key) for key in keys}
    for key, page in pages.items():
        tabs.addTab(page, key)
    if include_unmapped_theme:
        tabs.addTab(_MarketPage("theme"), "產業與題材")
    workspace = MarketAnalysisWorkspace(tabs, pages)
    return workspace, tabs, pages


def test_all_existing_market_views_are_reused_and_change_once(app: QApplication) -> None:
    workspace, tabs, pages = _make_workspace()
    original_widgets = tuple(tabs.widget(index) for index in range(tabs.count()))
    original_count = tabs.count()
    tab_changes: list[int] = []

    def load_current_page(index: int) -> None:
        tab_changes.append(index)
        page = tabs.widget(index)
        if isinstance(page, _MarketPage):
            page.load_data_if_needed()

    tabs.currentChanged.connect(load_current_page)

    categories = {
        "summary": "overview",
        "index": "overview",
        "cohort": "overview",
        "strong_stocks": "stocks",
        "weak_stocks": "stocks",
        "strong_industries": "industries",
        "weak_industries": "industries",
        "flow": "flow",
    }
    for key, category in categories.items():
        changes_before = len(tab_changes)
        current_before = tabs.currentWidget()
        assert workspace.select_view(key)
        assert tabs.currentWidget() is pages[key]
        assert workspace.primary_view_selector.currentData() == category
        expected_change = int(current_before is not pages[key])
        assert len(tab_changes) == changes_before + expected_change
        assert pages[key].load_count == expected_change
        assert tabs.count() == original_count
        assert tuple(tabs.widget(index) for index in range(tabs.count())) == original_widgets

    changes_before = len(tab_changes)
    assert workspace.select_view("flow")
    assert len(tab_changes) == changes_before
    assert not workspace.select_view("unknown")
    assert not workspace.select_widget(QWidget())
    assert len(tab_changes) == changes_before


def test_external_legacy_tab_changes_sync_overview_and_direction(app: QApplication) -> None:
    workspace, tabs, pages = _make_workspace()

    tabs.setCurrentWidget(pages["weak_stocks"])
    assert workspace.primary_view_selector.currentData() == "stocks"
    assert workspace.direction_buttons["weak"].isChecked()
    assert not workspace.direction_buttons["strong"].isChecked()

    tabs.setCurrentWidget(pages["weak_industries"])
    assert workspace.primary_view_selector.currentData() == "industries"
    assert workspace.direction_buttons["weak"].isChecked()

    tabs.setCurrentWidget(pages["cohort"])
    assert workspace.primary_view_selector.currentData() == "overview"
    assert workspace.overview_selector.currentData() == "cohort"


def test_unmapped_theme_tab_hides_and_restores_market_controls(app: QApplication) -> None:
    workspace, tabs, pages = _make_workspace(include_unmapped_theme=True)
    theme = tabs.widget(tabs.count() - 1)

    tabs.setCurrentWidget(theme)
    assert tabs.currentWidget() is theme
    assert workspace.controls_bar.isHidden()
    assert tabs.count() == len(pages) + 1

    tabs.setCurrentWidget(pages["weak_industries"])
    assert not workspace.controls_bar.isHidden()
    assert workspace.primary_view_selector.currentData() == "industries"
    assert workspace.direction_buttons["weak"].isChecked()


def test_shared_direction_buttons_and_overview_selector_navigate_original_pages(
    app: QApplication,
) -> None:
    workspace, tabs, pages = _make_workspace()
    changes: list[int] = []
    tabs.currentChanged.connect(changes.append)

    workspace.primary_view_selector.setCurrentIndex(
        workspace.primary_view_selector.findData("stocks")
    )
    assert tabs.currentWidget() is pages["strong_stocks"]
    assert len(changes) == 1
    workspace.direction_buttons["weak"].click()
    assert tabs.currentWidget() is pages["weak_stocks"]
    assert len(changes) == 2

    workspace.primary_view_selector.setCurrentIndex(
        workspace.primary_view_selector.findData("industries")
    )
    assert tabs.currentWidget() is pages["strong_industries"]
    assert len(changes) == 3
    workspace.direction_buttons["weak"].click()
    assert tabs.currentWidget() is pages["weak_industries"]
    assert len(changes) == 4

    workspace.overview_selector.setCurrentIndex(
        workspace.overview_selector.findData("index")
    )
    assert tabs.currentWidget() is pages["index"]
    assert len(changes) == 5


def test_cohort_is_optional_and_unknown_mapping_keys_are_rejected(app: QApplication) -> None:
    workspace, _tabs, pages = _make_workspace(include_cohort=False)
    assert workspace.overview_selector.findData("cohort") == -1
    assert not workspace.select_view("cohort")
    assert workspace.select_view("summary")

    tabs = QTabWidget()
    widgets = {key: _MarketPage(key) for key in pages}
    for key, widget in widgets.items():
        tabs.addTab(widget, key)
    with pytest.raises(ValueError, match="不支援"):
        MarketAnalysisWorkspace(
            tabs,
            {**widgets, "legacy_extra": _MarketPage("extra")},
        )
