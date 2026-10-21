from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QComboBox, QHBoxLayout, QLineEdit, QPushButton, QWidget

from ui_qt.main_window_coordinator import (
    LEGACY_DEFAULT_ROUTES,
    PRIMARY_NAVIGATION,
    ROUTE_BY_ID,
    WORKSPACE_DEFINITIONS,
)
from ui_qt.views.stock_lookup_landing import StockLookupLanding
from ui_qt.views.stock_research_report_view import StockResearchReportView
from ui_qt.v2_shell import ProductShell
from ui_qt.widgets.left_navigation import LeftNavigationWidget, NavigationItem


@pytest.fixture
def app() -> QApplication:
    instance = QApplication.instance()
    return instance if instance is not None else QApplication(sys.argv)


@dataclass(frozen=True)
class _MappingRow:
    stock_id: str
    stock_name: str
    chain_name: str
    theme_name: str


@dataclass(frozen=True)
class _ThemeSnapshot:
    identity_sha256: str
    mapping: tuple[_MappingRow, ...]


class _WorkspaceStack:
    def __init__(self, widgets: dict[str, QWidget]) -> None:
        self.widgets = widgets
        self.current_key = "workbench"

    def setCurrentWidget(self, widget: QWidget) -> None:  # noqa: N802 - Qt-like stub
        self.current_key = next(key for key, value in self.widgets.items() if value is widget)

    def currentWidget(self) -> QWidget:  # noqa: N802 - Qt-like stub
        return self.widgets[self.current_key]


class _MarketTabs:
    def __init__(self) -> None:
        self.current_widget = None

    def setCurrentWidget(self, widget) -> None:  # noqa: N802 - Qt-like stub
        self.current_widget = widget

    def currentWidget(self):  # noqa: N802 - Qt-like stub
        return self.current_widget


class _RecommendationTabs:
    def __init__(self) -> None:
        self.widgets: list[object] = []
        self.current_widget = None

    def count(self) -> int:
        return len(self.widgets)

    def setTabVisible(self, _index: int, _visible: bool) -> None:  # noqa: N802 - Qt-like stub
        return None

    def setCurrentIndex(self, index: int) -> None:  # noqa: N802 - Qt-like stub
        self.current_widget = self.widgets[index]

    def setCurrentWidget(self, widget) -> None:  # noqa: N802 - Qt-like stub
        self.current_widget = widget

    def currentWidget(self):  # noqa: N802 - Qt-like stub
        return self.current_widget

    def widget(self, index: int):
        return self.widgets[index]


class _ThemeView:
    def __init__(self) -> None:
        self.snapshot: _ThemeSnapshot | None = None
        self.chain_filter = QComboBox()
        self.theme_filter = QComboBox()
        self._busy = False

    def is_busy(self) -> bool:
        return self._busy


class _StatusBar:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def showMessage(self, message: str) -> None:  # noqa: N802 - Qt-like stub
        self.messages.append(message)


class _StockStepper:
    def __init__(self) -> None:
        self.stock_codes = ("2330", "2317", "2454")
        self._active_code = "2330"
        self.stock_search = QLineEdit()
        self.loaded_codes: list[str] = []
        self.previous_button = QPushButton("上一檔")
        self.next_button = QPushButton("下一檔")
        self.previous_button.clicked.connect(
            lambda _checked=False: StockResearchReportView._step_stock(self, -1)
        )
        self.next_button.clicked.connect(
            lambda _checked=False: StockResearchReportView._step_stock(self, 1)
        )

    def _load_stock(self, stock_code: str) -> None:
        self._active_code = stock_code
        self.loaded_codes.append(stock_code)


class _MinimalHost(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.workspace_widgets = {
            definition.key: QWidget(self) for definition in WORKSPACE_DEFINITIONS
        }
        self.stock_lookup_landing = StockLookupLanding(self)
        self.workspace_widgets["stock_lookup"] = self.stock_lookup_landing
        for route in ROUTE_BY_ID.values():
            self.workspace_widgets.setdefault(route.workspace, QWidget(self))
        self.workspace_stack = _WorkspaceStack(self.workspace_widgets)
        self.selected_workspace = "workbench"
        self.left_navigation = LeftNavigationWidget(
            tuple(
                NavigationItem(item.key, item.label, icon=item.icon)
                for item in PRIMARY_NAVIGATION
            ),
            parent=self,
            primary_mode=True,
        )
        self.industry_theme_map_view = _ThemeView()
        self.decision_desk_view = QWidget(self)
        self.market_tabs = _MarketTabs()
        self.portfolio_view = SimpleNamespace(selected_sections=[])
        self.portfolio_view.select_v2_section = self.portfolio_view.selected_sections.append
        self.backtest_view = SimpleNamespace(result_panel=None)
        self.recommendation_view = SimpleNamespace(result_source_tabs=_RecommendationTabs())
        self.stock_research_workspace = SimpleNamespace(
            report_view=SimpleNamespace(stock_search=QLineEdit(), context=None),
            is_busy=lambda: False,
            content_stack=SimpleNamespace(currentWidget=lambda: None),
            price_research_view=SimpleNamespace(returnRequested=SimpleNamespace(emit=lambda: None)),
        )
        self.opened_contexts: list[object] = []
        self.report_return_count = 0
        self.status_bar = _StatusBar()
        self.shell: ProductShell | None = None
        layout = QHBoxLayout(self)
        layout.addWidget(self.left_navigation)

    def attach_shell(self) -> ProductShell:
        self.shell = ProductShell(self)
        self.stock_lookup_landing.searchRequested.connect(self.shell.search_query)
        self.layout().addWidget(self.shell, 1)
        return self.shell

    def _select_main_workspace(self, key: str, *, preserve_view_state: bool = False) -> None:
        widget = self.workspace_widgets.get(key)
        if widget is None:
            return
        self.workspace_stack.setCurrentWidget(widget)
        self.selected_workspace = key
        self.left_navigation.set_current_key(key)
        if self.shell is not None:
            self.shell.workspace_selected(key)

    def _open_stock_research_context(self, context: object) -> None:
        self.opened_contexts.append(context)
        self.stock_research_workspace.report_view.context = context
        self._select_main_workspace("stock_research")

    def _open_theme_research_stock(self, stock_code: str) -> None:
        self.opened_contexts.append(stock_code)
        self._select_main_workspace("stock_research")

    def _return_from_stock_research_report(self) -> None:
        self.report_return_count += 1

    def statusBar(self) -> _StatusBar:  # noqa: N802 - Qt-like host API
        return self.status_bar


def _make_host(app: QApplication) -> tuple[_MinimalHost, ProductShell]:
    host = _MinimalHost()
    shell = host.attach_shell()
    return host, shell


def test_price_detail_return_recognizes_product_container(app: QApplication) -> None:
    host, shell = _make_host(app)
    host.recommendation_view.result_source_tabs.widgets.append(QWidget(host))
    shell.activate_route("screener")
    host._select_main_workspace("stock_research")
    returned: list[str] = []
    workspace = host.stock_research_workspace
    workspace.price_research_context = object()
    workspace._is_price_research_active = lambda: True
    workspace.price_research_view.returnRequested.emit = lambda: returned.append("original-price")
    shell.return_to_source()
    assert returned == ["original-price"]
    assert host.report_return_count == 0


def test_primary_routes_and_legacy_workspace_callbacks_reach_the_existing_views(app: QApplication) -> None:
    host, shell = _make_host(app)

    primary_route_ids = ("overview", "market", "lists", "strategies")
    for route_id in primary_route_ids:
        route = ROUTE_BY_ID[route_id]
        shell.activate_route(route_id)
        assert host.selected_workspace == route.workspace
        assert host.workspace_stack.current_key == route.workspace
        assert host.left_navigation.current_key() == route.group
        assert shell.route_id == route_id

    for legacy_key, route_id in LEGACY_DEFAULT_ROUTES.items():
        if legacy_key == "stock_research":
            continue
        host._select_main_workspace(legacy_key)
        route = ROUTE_BY_ID[route_id]
        assert host.selected_workspace == legacy_key
        assert shell.route_id == route_id
        assert host.left_navigation.current_key() == route.group

    shell.activate_route("themes")
    host._select_main_workspace("stock_research")
    assert shell.route_id == "themes"
    assert shell._detail_origin == "themes"
    assert host.left_navigation.current_key() == "explore"


def test_detail_keeps_primary_highlight_and_return_uses_source_guard(app: QApplication) -> None:
    host, shell = _make_host(app)
    shell.activate_route("themes")
    host._select_main_workspace("stock_research")
    host.show()
    app.processEvents()
    host.stock_research_workspace.report_view.context = SimpleNamespace(
        source_kind="explicit_latest_stock_research",
        source_workspace="stock_research",
    )

    assert shell.return_button.isVisible()
    assert shell.subnav.isVisible() is False
    assert host.left_navigation.current_key() == "explore"
    assert shell._detail_origin == "themes"

    shell.return_to_source()

    assert shell.route_id == "themes"
    assert host.selected_workspace == "market_explore"
    assert host.left_navigation.current_key() == "explore"
    assert shell.return_button.isVisible() is False
    assert host.report_return_count == 0

    host._select_main_workspace("stock_research")
    host.stock_research_workspace.report_view.context = SimpleNamespace(
        source_kind="industry_theme_snapshot",
        source_workspace="market_explore",
        source_version="changed-source",
    )
    shell.return_to_source()

    assert host.report_return_count == 1
    assert shell.route_id == "themes"


def test_stock_context_changes_keep_one_original_route_origin(app: QApplication) -> None:
    host, shell = _make_host(app)
    shell.activate_route("themes")
    host._select_main_workspace("stock_research")
    stepper = _StockStepper()
    stepper.next_button.click()
    stepper.next_button.click()
    stepper.previous_button.click()

    assert stepper.loaded_codes == ["2317", "2454", "2317"]
    assert shell.route_id == "themes"
    assert shell._detail_origin == "themes"
    assert host.left_navigation.current_key() == "explore"


def test_global_search_waits_for_explicit_selection_and_shows_disabled_empty_state(app: QApplication) -> None:
    host, shell = _make_host(app)
    host.industry_theme_map_view.snapshot = _ThemeSnapshot(
        "theme-v1", (_MappingRow("2330", "台積電", "半導體", "晶圓代工"),)
    )
    shell.search.search_edit.setText("2330")
    shell.search.search_button.click()

    menu = shell._search_menu
    general_action = next(action for action in menu.actions() if action.text().startswith("個股 2330"))
    assert host.opened_contexts == []
    general_action.trigger()
    assert len(host.opened_contexts) == 1
    assert getattr(host.opened_contexts[0], "stock_code", None) == "2330"
    assert getattr(host.opened_contexts[0], "source_kind", None) == "explicit_latest_stock_research"
    assert shell._detail_origin == "overview"
    shell.return_to_source()
    assert shell.route_id == "overview"
    assert host.report_return_count == 0

    shell.activate_route("overview")
    host.industry_theme_map_view.snapshot = None
    shell.search.search_edit.setText("無此題材")
    shell.search.search_button.click()
    empty_menu = shell._search_menu
    assert len(empty_menu.actions()) == 1
    assert empty_menu.actions()[0].isEnabled() is False
    assert shell.route_id == "overview"


def test_lookup_landing_hides_old_pinned_report_and_returns_after_new_search(
    app: QApplication,
) -> None:
    host, shell = _make_host(app)
    assert shell._stock_directory_worker is None
    stale_context = SimpleNamespace(
        source_kind="pinned_stock_research",
        source_workspace="stock_research",
        stock_code="2317",
    )
    host.stock_research_workspace.report_view.context = stale_context
    host.show()
    app.processEvents()

    shell.activate_route("lookup")
    app.processEvents()
    assert host.selected_workspace == "stock_lookup"
    assert host.workspace_stack.current_key == "stock_lookup"
    assert host.workspace_stack.widgets["stock_lookup"] is host.stock_lookup_landing
    assert host.workspace_stack.widgets["stock_research"] is not host.stock_lookup_landing
    assert host.stock_research_workspace.report_view.context is stale_context

    host.stock_lookup_landing.query_edit.setText("2330")
    host.stock_lookup_landing.submit_button.click()
    menu = shell._search_menu
    general_action = next(
        action for action in menu.actions()
        if action.text().startswith("個股 2330")
    )
    general_action.trigger()

    context = host.stock_research_workspace.report_view.context
    assert getattr(context, "stock_code", None) == "2330"
    assert getattr(context, "source_workspace", None) == "stock_lookup"
    assert host.selected_workspace == "stock_research"
    assert shell._detail_origin == "lookup"

    shell.return_to_source()

    assert shell.route_id == "lookup"
    assert host.selected_workspace == "stock_lookup"
    assert host.workspace_stack.current_key == "stock_lookup"
    assert host.report_return_count == 0


@pytest.mark.parametrize("query, action_prefix", [("晶圓代工", "題材："), ("2330", "2330 台積電")])
def test_search_action_is_rejected_after_theme_snapshot_identity_changes(
    app: QApplication, query: str, action_prefix: str
) -> None:
    host, shell = _make_host(app)
    host.industry_theme_map_view.snapshot = _ThemeSnapshot(
        "theme-v1", (_MappingRow("2330", "台積電", "半導體", "晶圓代工"),)
    )
    shell.search.search_edit.setText(query)
    shell.search.search_button.click()
    menu = shell._search_menu
    stale_action = next(action for action in menu.actions() if action.text().startswith(action_prefix))

    host.industry_theme_map_view.snapshot = _ThemeSnapshot(
        "theme-v2", (_MappingRow("2330", "台積電", "半導體", "晶圓代工"),)
    )
    stale_action.trigger()

    assert shell.route_id == "overview"
    assert host.opened_contexts == []
    assert host.status_bar.messages


def test_compact_shell_keeps_search_and_context_navigation_available(app: QApplication) -> None:
    host, shell = _make_host(app)
    host.resize(1280, 760)
    host.left_navigation.set_collapsed(True)
    shell.activate_route("market")
    host.show()
    app.processEvents()

    assert host.left_navigation.is_collapsed()
    assert shell.search.isVisible()
    assert shell.search.search_edit.isVisible()
    assert shell.search.search_button.isVisible()
    assert shell.search.context_label.isVisible()
    assert shell.search.context_label.width() >= 180
    assert shell.subnav.isVisible()
    assert shell.subnav.current_route == "market"


def test_external_market_tab_selection_syncs_theme_route_only_in_foreground(app: QApplication) -> None:
    host, shell = _make_host(app)
    shell.activate_route("market")

    host.market_tabs.setCurrentWidget(host.industry_theme_map_view)
    host._select_main_workspace("market_explore")

    assert shell.route_id == "themes"
    assert shell.subnav.current_route == "themes"

    shell.activate_route("overview")
    host.market_tabs.setCurrentWidget(host.industry_theme_map_view)
    shell.market_section_changed()

    assert shell.route_id == "overview"


def test_external_h20_tab_selection_syncs_ml_route_only_in_foreground(app: QApplication) -> None:
    host, shell = _make_host(app)
    tabs = host.recommendation_view.result_source_tabs
    screener = QWidget(host)
    ml = QWidget(host)
    tabs.widgets = [screener, ml]
    host.personal_h20_research_widget = ml
    tabs.setCurrentWidget(ml)

    host._select_main_workspace("recommendation")

    assert shell.route_id == "ml"
    assert shell.subnav.current_route == "ml"

    shell.activate_route("overview")
    shell.research_section_changed()

    assert shell.route_id == "overview"


def test_portfolio_section_sync_is_guarded_by_foreground_workspace(app: QApplication) -> None:
    host, shell = _make_host(app)
    host._select_main_workspace("portfolio")

    shell.portfolio_section_changed("paper")

    assert shell.route_id == "paper"
    assert shell.subnav.current_route == "paper"

    shell.activate_route("overview")
    shell.portfolio_section_changed("journal")

    assert shell.route_id == "overview"
