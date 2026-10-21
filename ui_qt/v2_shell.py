"""V2 導覽適配器；只組織既有畫面，不持有金融計算或保存契約。"""

from __future__ import annotations

from pathlib import Path
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QLabel, QMenu, QPushButton, QVBoxLayout, QWidget

from app_module.research_session import ResearchStockContextDTO
from ui_qt.main_window_coordinator import (
    LEGACY_DEFAULT_ROUTES, ROUTE_BY_ID, routes_for_group,
)
from ui_qt.widgets.global_search_bar import GlobalSearchBar
from ui_qt.widgets.workspace_subnav import WorkspaceSubnav
from app_module.stock_search_directory import StockSearchEntry, read_stock_search_directory
from ui_qt.workers.task_worker import TaskWorker


class ProductShell(QWidget):
    """統一主頁／子頁與詳情返回；保留原服務的來源驗證。"""

    def __init__(self, host, *, stock_directory: Path | None = None) -> None:
        super().__init__(host)
        self.host = host
        self.route_id = "overview"
        self._last_routes: dict[str, str] = {}
        self._activating = False
        self._detail_origin: str | None = None
        self._theme_auto_requested = False
        self._stock_directory_entries: tuple[StockSearchEntry, ...] = ()
        self._stock_directory_worker: TaskWorker | None = None
        self.setObjectName("baldrProductShell")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(2)
        self.search = GlobalSearchBar(self)
        self.search.searchRequested.connect(self.search_query)
        layout.addWidget(self.search)
        self.subnav = WorkspaceSubnav(self)
        self.subnav.set_tab_predecessor(self.search.search_button)
        self.subnav.routeSelected.connect(self.activate_route)
        layout.addWidget(self.subnav)
        self.return_button = QPushButton(self)
        self.return_button.setObjectName("productReturnToSource")
        self.return_button.setAccessibleName("返回原研究來源")
        self.return_button.clicked.connect(self.return_to_source)
        self.return_button.hide()
        layout.addWidget(self.return_button)
        self.route_hint = QLabel(self)
        self.route_hint.setObjectName("productRouteHint")
        self.route_hint.setWordWrap(True)
        self.route_hint.hide()
        layout.addWidget(self.route_hint)
        self.search_shortcut = QShortcut(QKeySequence("Ctrl+K"), host)
        self.search_shortcut.activated.connect(self.search.focus_search)
        self.return_shortcut = QShortcut(QKeySequence("Alt+Left"), host)
        self.return_shortcut.activated.connect(self.return_to_source)
        self._refresh_navigation()
        if stock_directory is not None:
            self._load_stock_directory(stock_directory)

    def _load_stock_directory(self, path: Path) -> None:
        worker = TaskWorker(read_stock_search_directory, path)
        self._stock_directory_worker = worker
        worker.finished.connect(self._receive_stock_directory)
        worker.error.connect(lambda _error: self.search.set_context_label("名錄不可讀；各域日期依頁面標示"))

        def cleanup() -> None:
            if self._stock_directory_worker is worker:
                self._stock_directory_worker = None
            worker.deleteLater()

        worker.native_thread_finished.connect(cleanup)
        worker.start()

    def _receive_stock_directory(self, value: object) -> None:
        if getattr(self.host, "_shutdown_close_requested", False):
            return
        if isinstance(value, tuple) and all(isinstance(entry, StockSearchEntry) for entry in value):
            self._stock_directory_entries = tuple(entry for entry in value if isinstance(entry, StockSearchEntry))

    def _maybe_load_theme_catalog(self) -> None:
        view = self.host.industry_theme_map_view
        load = getattr(view, "load_latest_snapshot", None)
        if not self._theme_auto_requested and view.snapshot is None and callable(load):
            if load() is True:
                self._theme_auto_requested = True

    def market_section_changed(self) -> None:
        """舊首頁捷徑與返回 callback 仍能同步目前真正可見的市場／題材路由。"""
        if self._activating or self._detail_origin is not None:
            return
        if self.host.workspace_stack.currentWidget() is not self.host.workspace_widgets.get("market_explore"):
            return
        self.route_id = "themes" if self.host.market_tabs.currentWidget() is self.host.industry_theme_map_view else "market"
        self._last_routes["explore"] = self.route_id
        self._refresh_navigation()
        if self.route_id == "themes":
            self._maybe_load_theme_catalog()

    def research_section_changed(self) -> None:
        if self._activating or self._detail_origin is not None:
            return
        if self.host.workspace_stack.currentWidget() is not self.host.workspace_widgets.get("recommendation"):
            return
        ml = getattr(self.host, "personal_h20_research_widget", None)
        current = self.host.recommendation_view.result_source_tabs.currentWidget()
        self.route_id = "ml" if ml is not None and current is ml else "screener"
        self._last_routes[ROUTE_BY_ID[self.route_id].group] = self.route_id
        self._refresh_navigation()

    def portfolio_section_changed(self, section: str) -> None:
        if self._activating or self._detail_origin is not None or section not in {"positions", "paper", "journal"}:
            return
        if self.host.workspace_stack.currentWidget() is not self.host.workspace_widgets.get("portfolio"):
            return
        self.route_id = section
        self._last_routes["investment"] = section
        self._refresh_navigation()

    def activate_group(self, group: str) -> None:
        routes = routes_for_group(group)
        if routes:
            self.activate_route(self._last_routes.get(group, routes[0].route_id))

    def activate_route(self, route_id: str, *, preserve_view_state: bool = False) -> None:
        route = ROUTE_BY_ID.get(route_id)
        if route is None:
            return
        self.host._timeline_pending_price_entry = None
        self.host._timeline_detail_entry = None
        self.host._historical_research_return = None
        self._activating = True
        try:
            self.route_id = route_id
            self._last_routes[route.group] = route_id
            self._detail_origin = None
            if preserve_view_state:
                self.host._select_main_workspace(route.workspace, preserve_view_state=True)
            else:
                self.host._select_main_workspace(route.workspace)
            if not preserve_view_state:
                self._select_existing_section(route_id)
            self._refresh_navigation()
        finally:
            self._activating = False

    def workspace_selected(self, key: str) -> None:
        """舊 callback 可沿原工作區 key 操作；詳情不改主頁高亮。"""
        if self._activating:
            return
        if key == "stock_research":
            if self._detail_origin is None:
                self._detail_origin = self.route_id
            self._refresh_navigation()
            return
        self.host._historical_research_return = None
        route_id = LEGACY_DEFAULT_ROUTES.get(key)
        if route_id is None:
            return
        # 原 view 保留 Query、排序、選列與捲動；不重建或序列化來源。
        current = ROUTE_BY_ID[self.route_id]
        if current.workspace != key or self._detail_origin is not None:
            origin = ROUTE_BY_ID.get(self._detail_origin or "")
            self.route_id = origin.route_id if origin and origin.workspace == key else route_id
        self._detail_origin = None
        self._last_routes[ROUTE_BY_ID[self.route_id].group] = self.route_id
        self._refresh_navigation()
        if key == "recommendation":
            self.research_section_changed()
        elif key == "market_explore":
            self.market_section_changed()

    def _refresh_navigation(self) -> None:
        route = ROUTE_BY_ID[self.route_id]
        self.host.left_navigation.set_current_key(route.group)
        self.subnav.set_routes(tuple((r.route_id, r.label) for r in routes_for_group(route.group)))
        self.subnav.set_current_route(self.route_id)
        self.subnav.setVisible(self._detail_origin is None and route.group != "workbench")
        self.return_button.setVisible(self._detail_origin is not None)
        if self._detail_origin is not None:
            self.return_button.setText("← 返回：" + ROUTE_BY_ID[self._detail_origin].label)
        hints = {
            "ml": "模型研究專區：未取得正式決策資格，預測不等於實際成果。",
        }
        hint = hints.get(self.route_id, "") if self._detail_origin is None else ""
        self.route_hint.setText(hint)
        self.route_hint.setVisible(bool(hint))

    def _select_existing_section(self, route_id: str) -> None:
        host = self.host
        if route_id in {"market", "themes"}:
            target = host.industry_theme_map_view if route_id == "themes" else host.decision_desk_view
            host.market_tabs.setCurrentWidget(target)
            if route_id == "themes":
                self._maybe_load_theme_catalog()
        elif route_id in {"positions", "paper"}:
            select = getattr(host.portfolio_view, "select_v2_section", None)
            if callable(select):
                select(route_id)
        elif route_id in {"backtests", "performance"}:
            panel = getattr(host.backtest_view, "result_panel", None)
            if route_id == "performance" and panel is not None:
                panel.focus_result_tab("registry")
        elif route_id == "storage":
            view = getattr(host, "storage_overview_view", None)
            if view is not None:
                view.refresh_if_needed()
        elif route_id in {"screener", "ml"}:
            adapter = getattr(host, "unified_screener_workspace", None)
            if adapter is not None:
                adapter.set_ml_mode(route_id == "ml")
                return
            view = host.recommendation_view
            tabs = view.result_source_tabs
            ml = getattr(host, "personal_h20_research_widget", None)
            for index in range(tabs.count()):
                tabs.setTabVisible(index, route_id == "ml" if tabs.widget(index) is ml else route_id != "ml")
            if route_id == "ml" and ml is not None:
                tabs.setCurrentWidget(ml)
            elif route_id == "screener":
                tabs.setCurrentIndex(0)
        elif route_id == "lookup":
            landing = getattr(host, "stock_lookup_landing", None)
            if landing is not None:
                landing.query_edit.setFocus()

    def return_to_source(self) -> None:
        if self._detail_origin is None:
            return
        historical_return = getattr(self.host, "_return_from_latest_historical_research", None)
        if callable(historical_return) and historical_return():
            return
        timeline_return = getattr(self.host, "_return_from_timeline_detail", None)
        if callable(timeline_return) and timeline_return():
            return
        workspace = self.host.stock_research_workspace
        price = getattr(workspace, "price_research_context", None)
        context = getattr(workspace.report_view, "context", None)
        if (context is not None and context.source_kind == "explicit_latest_stock_research"
                and context.source_workspace in {"stock_research", "stock_lookup"}):
            self.activate_route(self._detail_origin, preserve_view_state=True)
            return
        is_price = getattr(workspace, "_is_price_research_active", None)
        if price is not None and (
            is_price() if callable(is_price)
            else workspace.content_stack.currentWidget() is workspace.price_research_view
        ):
            # 經過詳情按鈕既有的來源配對驗證，再由它發出原 typed selection。
            workspace.price_research_view.return_button.click()
        else:
            self.host._return_from_stock_research_report()

    def set_detail_origin(self, route_id: str) -> None:
        """原件驗證完成後，由 Main 明確指定跨域回訪的原頁。"""
        if route_id not in ROUTE_BY_ID:
            raise ValueError("未知的返回來源")
        self.route_id = route_id
        self._detail_origin = route_id
        self._refresh_navigation()

    def search_query(self, query: str) -> None:
        """只搜尋已載入的題材映射；一般查股另由既有報告 reader 決定資格。"""
        query = query.strip()
        if not query:
            return
        previous_menu = getattr(self, "_search_menu", None)
        if previous_menu is not None:
            previous_menu.close()
            previous_menu.deleteLater()
        menu = QMenu(self.search)
        menu.setObjectName("globalSearchResults")
        if query.isascii() and query.isdigit() and 4 <= len(query) <= 6:
            action = menu.addAction(f"個股 {query}：另開一般可用資料")
            action.triggered.connect(lambda: self._open_general_stock(query))
        for entry in tuple(entry for entry in self._stock_directory_entries
                           if query.casefold() in entry.name.casefold() or query == entry.code)[:20]:
            action = menu.addAction(f"個股 {entry.code} {entry.name}（{entry.market_label}）：一般可用資料")
            action.triggered.connect(lambda _checked=False, code=entry.code: self._open_general_stock(code))
        view = self.host.industry_theme_map_view
        snapshot = view.snapshot
        matches: set[tuple[str, str]] = set()
        stocks: set[tuple[str, str]] = set()
        if snapshot is not None:
            identity = snapshot.identity_sha256
            for row in snapshot.mapping:
                if query.casefold() in (row.chain_name + " " + row.theme_name).casefold():
                    matches.add((row.chain_name, row.theme_name))
                if query == row.stock_id or query.casefold() in row.stock_name.casefold():
                    stocks.add((row.stock_id, row.stock_name))
            for code, name in sorted(stocks)[:15]:
                action = menu.addAction(f"{code} {name}：在原題材版本研究")
                action.triggered.connect(lambda _checked=False, code=code, identity=identity:
                                         self._open_theme_stock(code, identity))
            for chain, theme in sorted(matches)[:20]:
                action = menu.addAction(f"題材：{chain} / {theme}")
                action.triggered.connect(lambda _checked=False, chain=chain, theme=theme, identity=identity:
                                         self._open_theme(chain, theme, identity))
        if not menu.actions():
            action = menu.addAction("無可用結果；可輸入股票代號，或先在產業與題材載入合法版本。")
            action.setEnabled(False)
        # 由使用者明選才切換；保留 menu 物件直到 popup 關閉。
        self._search_menu = menu
        menu.popup(self.search.mapToGlobal(self.search.rect().bottomLeft()))

    def _open_general_stock(self, code: str) -> None:
        workspace = self.host.stock_research_workspace
        if workspace.is_busy():
            self.host.statusBar().showMessage("請等目前讀取或保存完成，再另開一般查詢。")
            return
        self.host._open_stock_research_context(ResearchStockContextDTO(
            stock_code=code, source_kind="explicit_latest_stock_research",
            source_label="使用者明選的一般個股查詢（獨立現況）",
            source_workspace="stock_lookup", ml_scope_mode="current_stock_research",
        ))

    def _theme_identity_is_current(self, identity: str) -> bool:
        view = self.host.industry_theme_map_view
        snapshot = view.snapshot
        if view.is_busy() or snapshot is None or snapshot.identity_sha256 != identity:
            self.host.statusBar().showMessage("搜尋來源版本已變動或尚忙，請重新搜尋後明選。")
            return False
        return True

    def _open_theme_stock(self, code: str, identity: str) -> None:
        if not self._theme_identity_is_current(identity):
            return
        self.activate_route("themes")
        self.host._open_theme_research_stock(code)

    def _open_theme(self, chain: str, theme: str, identity: str) -> None:
        if not self._theme_identity_is_current(identity):
            return
        view = self.host.industry_theme_map_view
        self.activate_route("themes")
        view.chain_filter.setCurrentText(chain)
        view.theme_filter.setCurrentText(theme)
