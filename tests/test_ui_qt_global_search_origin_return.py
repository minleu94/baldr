"""ProductShell 一般全域查股應沿目前 route 返回。"""

from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication, QWidget

from app_module.research_session import ResearchStockContextDTO
from ui_qt.main_window_coordinator import ROUTE_BY_ID
from ui_qt.main import MainWindow
from ui_qt.v2_shell import ProductShell


class _Navigation:
    def __init__(self) -> None:
        self.current_key: str | None = None

    def set_current_key(self, key: str) -> None:
        self.current_key = key


class _Portfolio:
    def __init__(self) -> None:
        self.selected_section: str | None = None

    def select_v2_section(self, section: str) -> bool:
        self.selected_section = section
        return True


class _Host(QWidget):
    def __init__(self, origin: str) -> None:
        super().__init__()
        self.left_navigation = _Navigation()
        self.workspace_widgets = {route.workspace: QWidget(self) for route in ROUTE_BY_ID.values()}
        self.workspace_widgets["stock_research"] = QWidget(self)
        self.workspace_stack = SimpleNamespace(currentWidget=lambda: self.current_workspace)
        self.current_workspace = self.workspace_widgets[ROUTE_BY_ID[origin].workspace]
        self.portfolio_view = _Portfolio()
        self.stock_research_workspace = SimpleNamespace(
            is_busy=lambda: False,
            report_view=SimpleNamespace(context=None),
        )
        self.statusBar = lambda: SimpleNamespace(showMessage=lambda *_args, **_kwargs: None)
        self.shell: ProductShell | None = None
        self.workspace_selection_flags: list[tuple[str, bool]] = []

    def _select_main_workspace(self, key: str, *, preserve_view_state: bool = False) -> None:
        self.workspace_selection_flags.append((key, preserve_view_state))
        self.current_workspace = self.workspace_widgets[key]
        if self.shell is not None:
            self.shell.workspace_selected(key)

    def _open_stock_research_context(self, context: ResearchStockContextDTO) -> None:
        self.stock_research_workspace.report_view.context = context
        self._select_main_workspace("stock_research")

    def _return_from_timeline_detail(self) -> bool:
        return False

    def _return_from_stock_research_report(self) -> None:
        raise AssertionError("一般明選個股應由 ProductShell 回到來源 route")


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication(sys.argv)


@pytest.mark.parametrize("origin", ("overview", "paper", "strategies"))
def test_general_global_search_returns_to_exact_origin_route(app: QApplication, origin: str) -> None:
    host = _Host(origin)
    shell = ProductShell(host)
    host.shell = shell
    shell.activate_route(origin)
    original_workspace = host.current_workspace
    original_nav_key = host.left_navigation.current_key

    # 模擬使用者明選搜尋結果所呼叫的既有 ProductShell menu callback。
    shell._open_general_stock("2330")

    context = host.stock_research_workspace.report_view.context
    assert context is not None
    assert context.stock_code == "2330"
    assert context.source_kind == "explicit_latest_stock_research"
    assert context.source_workspace == "stock_lookup"
    assert shell.route_id == origin
    assert shell._detail_origin == origin
    assert host.left_navigation.current_key == original_nav_key
    assert not shell.return_button.isHidden()

    shell.return_to_source()

    assert shell.route_id == origin
    assert shell._detail_origin is None
    assert host.current_workspace is original_workspace
    assert host.workspace_selection_flags[-1] == (ROUTE_BY_ID[origin].workspace, True)
    assert host.left_navigation.current_key == original_nav_key
    assert shell.return_button.isHidden()
    if origin == "paper":
        assert host.portfolio_view.selected_section == "paper"

    shell.close()
    host.close()
    shell.deleteLater()
    host.deleteLater()
    app.processEvents()


def test_main_workspace_refresh_is_skipped_only_for_preserved_return() -> None:
    calls: list[str] = []
    host = SimpleNamespace(
        watchlist_view=SimpleNamespace(refresh_all=lambda: calls.append("watchlist.refresh")),
        watchlist_product_layout=SimpleNamespace(sync_rows=lambda: calls.append("watchlist.sync")),
        portfolio_view=SimpleNamespace(refresh_all=lambda: calls.append("portfolio.refresh")),
    )

    MainWindow._on_workspace_selected(host, "portfolio", preserve_view_state=True)
    MainWindow._on_workspace_selected(host, "watchlist", preserve_view_state=True)
    assert calls == []

    MainWindow._on_workspace_selected(host, "portfolio")
    MainWindow._on_workspace_selected(host, "watchlist")
    assert calls == ["portfolio.refresh", "watchlist.refresh", "watchlist.sync"]
