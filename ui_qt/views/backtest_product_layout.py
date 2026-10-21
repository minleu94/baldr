"""將既有回測工作區攤平成單層結果導航；只讀取目前頁面與結果欄位。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import re
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QLabel,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QTabWidget,
)


def _text(value: Any) -> str:
    if value is None or value == "":
        return "未提供"
    return str(value)


def _details(report: Any) -> Mapping[str, Any]:
    value = report.get("details", {}) if isinstance(report, Mapping) else getattr(report, "details", {})
    return value if isinstance(value, Mapping) else {}


def _visible_tab(tabs: QTabWidget, index: int) -> bool:
    if not tabs.isTabEnabled(index):
        return False
    checker = getattr(tabs.tabBar(), "isTabVisible", None)
    return bool(checker(index)) if callable(checker) else True


def _slug(value: str) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    return text.replace("/", "／") or "未命名頁面"


@dataclass(frozen=True)
class _ResultRoute:
    key: str
    label: str
    kind: str
    outer_index: int | None = None
    tab_steps: tuple[tuple[QTabWidget, int], ...] = ()
    page: QWidget | None = None


class BacktestProductLayout:
    """保留既有回測元件，以單層路徑選單呈現結果與原始觀測。"""

    def __init__(self, backtest_view: QWidget) -> None:
        self.backtest_view = backtest_view
        self._installed = False
        self._transitioning = False
        self._routes: dict[str, _ResultRoute] = {}
        self._connected_nested_tabs: set[int] = set()
        self._last_report: Any = None
        self._last_params: Mapping[str, Any] = {}
        self._presented_snapshot_exists = False
        self._presented_source = ""
        self._snapshot_params_by_report: dict[int, tuple[Any, Mapping[str, Any]]] = {}

    def install(self) -> bool:
        """安裝單層 leaf selector，並保留原始 QTabWidget 與 callbacks。"""
        if self._installed:
            return True
        panel = getattr(self.backtest_view, "result_panel", None)
        tabs = getattr(panel, "result_tabs", None)
        layout = panel.layout() if panel is not None else None
        if not isinstance(panel, QWidget) or not isinstance(tabs, QTabWidget) or layout is None:
            return False

        self.result_panel = panel
        self.result_tabs = tabs
        self.navigator = QComboBox(panel)
        self.navigator.setObjectName("backtestProductLeafSelector")
        self.navigator.setAccessibleName("回測結果頁面")
        self.navigator.setToolTip("平面選取結果、診斷、圖表與比較內容；原始頁面和 callback 保留。")
        self.assumption_banner = QLabel(panel)
        self.assumption_banner.setObjectName("backtestRunAssumptionsBanner")
        self.assumption_banner.setAccessibleName("目前回測運算假設")
        self.assumption_banner.setWordWrap(True)
        self.assumption_banner.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.draft_status = QLabel(panel)
        self.draft_status.setObjectName("backtestDraftAssumptionStatus")
        self.draft_status.setWordWrap(True)
        self.draft_status.setVisible(False)

        self.stack = QStackedWidget(panel)
        self.stack.setObjectName("backtestProductResultStack")
        original_index = layout.indexOf(tabs)
        if original_index < 0:
            return False
        layout.removeWidget(tabs)
        self.stack.addWidget(tabs)
        layout.insertWidget(original_index, self.stack, 1)
        layout.insertWidget(1, self.assumption_banner)
        layout.insertWidget(2, self.draft_status)
        layout.insertWidget(3, self.navigator)

        self.open_positions_page, self.open_positions_table, self.open_positions_status = self._make_table_page(
            "backtestOpenPositionsPage", "期末未平倉：只顯示本次結果原始期末欄位。"
        )
        self.daily_signals_page, self.daily_signals_table, self.daily_signals_status = self._make_table_page(
            "backtestDailySignalsPage", "逐日訊號：只顯示結果已附的原始觀測，不推算缺失日。"
        )
        self.stack.addWidget(self.open_positions_page)
        self.stack.addWidget(self.daily_signals_page)
        self._custom_routes = (
            _ResultRoute("open_positions", "期末未平倉", "custom", page=self.open_positions_page),
            _ResultRoute("daily_signals", "逐日訊號", "custom", page=self.daily_signals_page),
        )

        self.navigator.currentIndexChanged.connect(self._on_route_selected)
        self.result_tabs.currentChanged.connect(self._on_outer_tab_changed)
        self._hide_tab_bars()
        self.refresh_routes()
        self.refresh_assumptions()
        self._connect_draft_controls()
        mode_combo = getattr(self.backtest_view, "research_lab_mode_combo", None)
        if mode_combo is not None and hasattr(mode_combo, "currentIndexChanged"):
            mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        self._installed = True
        return True

    def _make_table_page(self, object_name: str, description: str):
        page = QWidget(self.result_panel)
        page.setObjectName(object_name)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(6, 6, 6, 6)
        status = QLabel(description, page)
        status.setWordWrap(True)
        layout.addWidget(status)
        table = QTableWidget(page)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setAlternatingRowColors(True)
        table.setSortingEnabled(False)
        layout.addWidget(table, 1)
        return page, table, status

    def _hide_tab_bars(self) -> None:
        self.result_tabs.tabBar().hide()
        for tabs in self.result_panel.findChildren(QTabWidget):
            if tabs is not self.result_tabs:
                tabs.tabBar().hide()

    def _direct_nested_tabs(self, container: QWidget) -> list[QTabWidget]:
        found: list[QTabWidget] = []

        def visit(parent: QWidget) -> None:
            for child in parent.findChildren(QWidget, options=Qt.FindChildOption.FindDirectChildrenOnly):
                if isinstance(child, QTabWidget):
                    found.append(child)
                else:
                    visit(child)

        visit(container)
        return found

    def _unique_key(self, base: str, used: set[str]) -> str:
        if base not in used:
            used.add(base)
            return base
        suffix = 2
        while f"{base}~{suffix}" in used:
            suffix += 1
        key = f"{base}~{suffix}"
        used.add(key)
        return key

    def _walk_nested_routes(
        self,
        *,
        outer_key: str,
        outer_title: str,
        outer_index: int,
        tabs: QTabWidget,
        prefix_steps: tuple[tuple[QTabWidget, int], ...],
        crumbs: tuple[str, ...],
        used: set[str],
    ) -> list[_ResultRoute]:
        routes: list[_ResultRoute] = []
        tab_id = id(tabs)
        if tab_id not in self._connected_nested_tabs:
            tabs.currentChanged.connect(self._on_nested_tab_changed)
            self._connected_nested_tabs.add(tab_id)
        self._hide_one_tab_bar(tabs)
        for index in range(tabs.count()):
            if not _visible_tab(tabs, index):
                continue
            title = _slug(tabs.tabText(index))
            steps = prefix_steps + ((tabs, index),)
            path = crumbs + (title,)
            page = tabs.widget(index)
            nested = self._direct_nested_tabs(page) if page is not None else []
            if nested:
                for child_tabs in nested:
                    routes.extend(self._walk_nested_routes(
                        outer_key=outer_key,
                        outer_title=outer_title,
                        outer_index=outer_index,
                        tabs=child_tabs,
                        prefix_steps=steps,
                        crumbs=path,
                        used=used,
                    ))
                continue
            key = self._unique_key("/".join((outer_key, *path)), used)
            routes.append(_ResultRoute(key, " › ".join((outer_title, *path)), "tabs", outer_index, steps))
        return routes

    def _hide_one_tab_bar(self, tabs: QTabWidget) -> None:
        tabs.tabBar().hide()

    def refresh_routes(self, *_args) -> None:
        """重建目前模式可用的路徑；被模式隱藏的頁面不加入選單。"""
        self._rebuild_routes(prefer_current=False)

    def _rebuild_routes(self, *, prefer_current: bool) -> None:
        if not hasattr(self, "result_tabs"):
            return
        previous = self.navigator.currentData() if self.navigator.count() else None
        used: set[str] = set()
        routes: list[_ResultRoute] = []
        key_for_index = {
            self.result_tabs.indexOf(widget): key
            for key, widget in getattr(self.result_panel, "_result_tab_widgets", {}).items()
        }
        for outer_index in range(self.result_tabs.count()):
            if not _visible_tab(self.result_tabs, outer_index):
                continue
            outer_key = key_for_index.get(outer_index)
            if not isinstance(outer_key, str) or not outer_key:
                continue
            outer_title = _slug(self.result_tabs.tabText(outer_index))
            page = self.result_panel.result_tab_content_widget(outer_key)
            if page is None:
                page = self.result_tabs.widget(outer_index)
            nested = self._direct_nested_tabs(page) if page is not None else []
            if nested:
                for child_tabs in nested:
                    routes.extend(self._walk_nested_routes(
                        outer_key=outer_key,
                        outer_title=outer_title,
                        outer_index=outer_index,
                        tabs=child_tabs,
                        prefix_steps=(),
                        crumbs=(),
                        used=used,
                    ))
            else:
                key = self._unique_key(outer_key, used)
                routes.append(_ResultRoute(key, f"{outer_title} › {outer_key}", "tabs", outer_index))

        if self._active_mode() == "single_stock":
            routes.extend(self._custom_routes)
        self._routes = {route.key: route for route in routes}
        self._transitioning = True
        self.navigator.blockSignals(True)
        self.navigator.clear()
        for route in routes:
            self.navigator.addItem(route.label, route.key)
        self.navigator.blockSignals(False)
        current = self._current_route_key()
        if prefer_current:
            target = current if isinstance(current, str) and current in self._routes else None
        else:
            target = previous if isinstance(previous, str) and previous in self._routes else None
            if target is None and isinstance(current, str) and current in self._routes:
                target = current
        if target not in self._routes and routes:
            target = routes[0].key
        index = self.navigator.findData(target) if target is not None else -1
        self.navigator.setCurrentIndex(index)
        if index >= 0 and target in self._routes:
            self._apply_route(self._routes[target])
        self._transitioning = False

    def _current_route_key(self) -> str | None:
        if self.stack.currentWidget() is self.open_positions_page:
            return "open_positions"
        if self.stack.currentWidget() is self.daily_signals_page:
            return "daily_signals"
        outer_index = self.result_tabs.currentIndex()
        for route in self._routes.values():
            if route.kind != "tabs" or route.outer_index != outer_index:
                continue
            if all(tabs.currentIndex() == index for tabs, index in route.tab_steps):
                return route.key
        return None

    def select_result(self, path_key: str) -> bool:
        """切換到可見的結果 leaf；隱藏模式或未知路徑一律拒絕。"""
        if not self._installed and not hasattr(self, "_custom_routes"):
            return False
        self.refresh_routes()
        route = self._routes.get(path_key)
        if route is None:
            return False
        self._transitioning = True
        applied = self._apply_route(route)
        index = self.navigator.findData(path_key)
        self.navigator.blockSignals(True)
        self.navigator.setCurrentIndex(index)
        self.navigator.blockSignals(False)
        self._transitioning = False
        return applied and index >= 0

    def _apply_route(self, route: _ResultRoute) -> bool:
        if route.kind == "custom":
            if route.page is None:
                return False
            self.stack.setCurrentWidget(route.page)
        else:
            if route.outer_index is None or not _visible_tab(self.result_tabs, route.outer_index):
                return False
            self.stack.setCurrentWidget(self.result_tabs)
            self.result_tabs.setCurrentIndex(route.outer_index)
            for tabs, index in route.tab_steps:
                if index >= tabs.count() or not _visible_tab(tabs, index):
                    return False
                tabs.setCurrentIndex(index)
        return True

    def _on_route_selected(self, index: int) -> None:
        if self._transitioning or index < 0:
            return
        key = self.navigator.itemData(index)
        if isinstance(key, str):
            self.select_result(key)

    def _on_outer_tab_changed(self, _index: int) -> None:
        if not self._transitioning:
            self.stack.setCurrentWidget(self.result_tabs)
            self._rebuild_routes(prefer_current=True)

    def _on_nested_tab_changed(self, _index: int) -> None:
        if not self._transitioning:
            self.stack.setCurrentWidget(self.result_tabs)
            self._rebuild_routes(prefer_current=True)

    def _active_mode(self) -> str:
        combo = getattr(self.backtest_view, "research_lab_mode_combo", None)
        value = combo.currentData() if combo is not None and hasattr(combo, "currentData") else None
        return str(value or "single_stock")

    def _active_mode_label(self) -> str:
        combo = getattr(self.backtest_view, "research_lab_mode_combo", None)
        label = combo.currentText().strip() if combo is not None and hasattr(combo, "currentText") else ""
        return label or self._active_mode()

    def _on_mode_changed(self, *_args) -> None:
        """模式切換後清除上一模式快照，再同步可見頁面與狀態。"""
        self._presented_snapshot_exists = False
        self._last_report = None
        self._last_params = {}
        self._presented_source = ""
        self.refresh_routes()
        self.refresh_assumptions()

    def _connect_draft_controls(self) -> None:
        panel = getattr(self.backtest_view, "config_panel", None)
        controls = (
            "start_date", "end_date", "capital_input", "fee_bps_input",
            "slippage_bps_input", "execution_price_combo",
        )
        for name in controls:
            control = getattr(panel, name, None)
            if control is None:
                continue
            signal = getattr(control, "valueChanged", None)
            if signal is None:
                signal = getattr(control, "currentTextChanged", None)
            if signal is None:
                signal = getattr(control, "dateChanged", None)
            if signal is not None:
                signal.connect(self._on_draft_changed)

    def _on_draft_changed(self, *_args) -> None:
        if self._last_report is not None or getattr(self.backtest_view, "current_run_id", None):
            self.draft_status.setText(
                "設定欄已變更；上方仍顯示目前結果的來源假設，變更值只適用下一次執行。"
            )
            self.draft_status.setVisible(True)
        else:
            self.refresh_assumptions()

    def refresh_assumptions(self, report: Any = None) -> bool:
        """只呈現明確結果事件或歷史 payload；None 不會重新綁定可變的 live state。"""
        mode = self._active_mode()
        if mode != "single_stock":
            mode_label = self._active_mode_label()
            self._last_report = None
            self._last_params = {}
            message = (
                f"目前研究模式：{mode_label}。此投影未提供本模式的原結果假設、期末持倉或逐日訊號；"
                "請核對原結果頁。資格未提供。"
            )
            self.assumption_banner.setText(message)
            self.draft_status.setVisible(False)
            self._clear_projected_results(message)
            return True

        target = report if report is not None else self._last_report
        history_payload = isinstance(target, Mapping) and isinstance(target.get("details"), Mapping)
        if history_payload:
            details = _details(target)
            params = {
                key: details[key]
                for key in (
                    "start_date", "end_date", "capital", "fee_bps", "slippage_bps",
                    "execution_price", "execution_contract", "data_manifest",
                )
                if key in details
            }
            if "capital" not in params and "initial_capital" in details:
                params["capital"] = details["initial_capital"]
            self._last_report = target
            self._last_params = params
            self._presented_snapshot_exists = True
            self._presented_source = "已保存 run 原始資料"
            source_label = self._presented_source
        elif report is not None:
            details = _details(report)
            if report is getattr(self.backtest_view, "current_report", None):
                saved = self._snapshot_params_by_report.get(id(report))
                params = saved[1] if saved is not None and saved[0] is report else None
                if params is None:
                    live = getattr(self.backtest_view, "current_run_params", None)
                    params = dict(live) if isinstance(live, Mapping) else {}
                    self._snapshot_params_by_report[id(report)] = (report, params)
                self._last_report = report
                self._last_params = params
                self._presented_snapshot_exists = True
                self._presented_source = "當次結果原始參數"
                source_label = self._presented_source
            else:
                # 陌生 report 僅能使用其自身 details；不得借用目前可變的 run 參數。
                self._last_report = report
                self._last_params = {}
                self._presented_snapshot_exists = True
                self._presented_source = "結果原始欄位（參數未提供）"
                params = {}
                source_label = self._presented_source
        elif self._presented_snapshot_exists and self._last_report is not None:
            target = self._last_report
            details = _details(target)
            params = self._last_params
            source_label = self._presented_source or "已呈現結果快照"
        else:
            self._last_report = None
            details = {}
            live = getattr(self.backtest_view, "current_run_params", None)
            live = live if isinstance(live, Mapping) else {}
            if getattr(self.backtest_view, "worker", None) is not None and live:
                params = dict(live)
                source_label = "本次執行輸入（尚未完成）"
            else:
                params = self._draft_params()
                source_label = "設定草稿（適用下次執行）"
            self._last_params = params
        period_start = details.get("start_date") or params.get("start_date")
        period_end = details.get("end_date") or params.get("end_date")
        execution = details.get("execution_price") or params.get("execution_price")
        if execution is None:
            execution = params.get("execution_contract") or details.get("execution_contract")
        capital = params.get("capital")
        if capital is None:
            capital = details.get("capital", details.get("initial_capital"))
        fee = params.get("fee_bps")
        if fee is None:
            fee = details.get("fee_bps")
        slippage = params.get("slippage_bps")
        if slippage is None:
            slippage = details.get("slippage_bps")
        source_identity = details.get("source_identity")
        if source_identity is None:
            manifest = details.get("data_manifest")
            if isinstance(manifest, Mapping):
                source_identity = manifest.get("source_identity")
        qualification = details.get("source_qualification")
        if qualification is None:
            qualification = details.get("qualification")
        self.assumption_banner.setText(
            f"{source_label}｜期間 {_text(period_start)}～{_text(period_end)}｜"
            f"撮合 {_text(execution)}｜資金 {_text(capital)}｜"
            f"手續費 {_text(fee)} bps｜滑價 {_text(slippage)} bps｜"
            f"來源身份 {_text(source_identity)}｜來源資格 {_text(qualification)}"
        )
        self.draft_status.setVisible(False)
        self._refresh_open_positions(target)
        self._refresh_daily_signals(target)
        return True

    def _clear_projected_results(self, message: str) -> None:
        self._set_key_value_table(self.open_positions_table, [], ("欄位", "原始值", "來源"))
        self.open_positions_status.setText(message)
        self.daily_signals_table.clear()
        self.daily_signals_table.setRowCount(0)
        self.daily_signals_status.setText(message)

    def _draft_params(self) -> dict[str, Any]:
        panel = getattr(self.backtest_view, "config_panel", None)
        if panel is None:
            return {}

        def value(name: str) -> Any:
            control = getattr(panel, name, None)
            if control is None:
                return None
            if name in {"start_date", "end_date"} and hasattr(control, "date"):
                date_value = control.date()
                return date_value.toString("yyyy-MM-dd") if hasattr(date_value, "toString") else None
            if name == "execution_price_combo" and hasattr(control, "currentText"):
                return control.currentText()
            getter = getattr(control, "value", None)
            return getter() if callable(getter) else None

        return {
            "start_date": value("start_date"),
            "end_date": value("end_date"),
            "capital": value("capital_input"),
            "fee_bps": value("fee_bps_input"),
            "slippage_bps": value("slippage_bps_input"),
            "execution_price": value("execution_price_combo"),
        }

    def _refresh_open_positions(self, report: Any) -> None:
        if self._active_mode() != "single_stock":
            mode_label = self._active_mode_label()
            self._clear_projected_results(
                f"目前研究模式：{mode_label}。此投影未提供本模式期末持倉；請核對原結果頁。資格未提供。"
            )
            return
        details = _details(report) if report is not None else {}
        rows: list[tuple[str, Any, str]] = []
        terminal = details.get("terminal_position")
        if type(terminal) is int and terminal >= 0:
            rows.append(("期末持股", terminal, "report.details.terminal_position"))
        else:
            rows.append(("期末持股", None, "report.details.terminal_position"))
        curve = details.get("equity_curve")
        columns = getattr(curve, "columns", ())
        if (curve is not None and hasattr(curve, "iloc") and hasattr(curve, "index")
                and hasattr(curve, "__len__") and len(curve) > 0):
            try:
                last = curve.iloc[-1]
                rows.append(("期末觀測日期", curve.index[-1], "report.details.equity_curve.index[-1]"))
                for key in ("position", "position_value", "price", "cash", "equity"):
                    if key in columns:
                        rows.append((key, last[key], f"report.details.equity_curve.iloc[-1][{key!r}]"))
            except (IndexError, KeyError, TypeError):
                rows.append(("期末觀測", None, "原始 equity_curve 最後一列不可讀"))
        self._set_key_value_table(
            self.open_positions_table,
            rows,
            ("欄位", "原始值", "來源"),
        )
        if report is None:
            self.open_positions_status.setText("未提供：目前沒有可投影的單股回測結果。")
        elif len(rows) == 1 and rows[0][1] is None:
            self.open_positions_status.setText("未提供：結果未附期末持股或期末權益曲線原始列。")
        else:
            self.open_positions_status.setText("期末持倉只投影原始報告欄位；不補估值、不視為已實現配對。")

    def _refresh_daily_signals(self, report: Any) -> None:
        if self._active_mode() != "single_stock":
            mode_label = self._active_mode_label()
            self.daily_signals_table.clear()
            self.daily_signals_table.setRowCount(0)
            self.daily_signals_status.setText(
                f"目前研究模式：{mode_label}。此投影未提供本模式逐日訊號；請核對原結果頁。資格未提供。"
            )
            return
        details = _details(report) if report is not None else {}
        observations: list[tuple[str, Mapping[str, Any]]] = []
        for key, label in (
            ("rule_signal_observations", "規則逐日訊號原始觀測"),
            ("score_signal_observations", "分數逐日訊號原始觀測"),
        ):
            raw = details.get(key)
            if isinstance(raw, (list, tuple)):
                observations.extend(
                    (label, row) for row in raw if isinstance(row, Mapping)
                )
            elif isinstance(raw, Mapping):
                # 單筆觀測用欄位名識別；否則僅接受「鍵 -> 觀測 mapping」集合。
                if any(field in raw for field in ("date", "signal", "score", "symbol")):
                    observations.append((label, raw))
                elif raw and all(isinstance(row, Mapping) for row in raw.values()):
                    observations.extend(
                        (label, {"觀測鍵": observation_key, **row})
                        for observation_key, row in raw.items()
                    )
        keys: list[str] = []
        for _source, row in observations:
            for key in row:
                if isinstance(key, str) and key not in keys:
                    keys.append(key)
        headers = ["觀測來源", *keys]
        table = self.daily_signals_table
        table.clear()
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setRowCount(len(observations))
        for row_index, (source, observation) in enumerate(observations):
            self._set_cell(table, row_index, 0, source)
            for column_index, key in enumerate(keys, start=1):
                self._set_cell(table, row_index, column_index, observation.get(key))
        table.resizeColumnsToContents()
        if report is None:
            self.daily_signals_status.setText("未提供：目前沒有可投影的回測結果。")
        elif not observations:
            self.daily_signals_status.setText("未提供：此結果沒有保存逐日訊號觀測；不從圖表或交易表反推。")
        else:
            self.daily_signals_status.setText(
                f"共 {len(observations)} 筆原始逐日觀測；各來源分開保留，沒有合併或推算。"
            )

    @staticmethod
    def _set_cell(table: QTableWidget, row: int, column: int, value: Any) -> None:
        item = QTableWidgetItem(_text(value))
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        table.setItem(row, column, item)

    def _set_key_value_table(
        self,
        table: QTableWidget,
        rows: list[tuple[str, Any, str]],
        headers: tuple[str, ...],
    ) -> None:
        table.clear()
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(list(headers))
        table.setRowCount(len(rows))
        for row_index, values in enumerate(rows):
            for column_index, value in enumerate(values):
                self._set_cell(table, row_index, column_index, value)
        table.resizeColumnsToContents()
