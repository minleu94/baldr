"""以單層導覽區分純自選、舊候選來源、代碼清單及 typed 研究收藏。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from PySide6.QtCore import QObject, QModelIndex, Signal
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from app_module.watchlist_service import (
    _bookmark_payload_id,
    _bookmark_source,
    decode_daily_market_research_bookmark,
)


class WatchlistProductLayout(QObject):
    """不重建 WatchlistView/model 的頁面導覽與唯讀列篩選。"""

    comparisonRequested = Signal(object)

    _SECTIONS = (
        ("pure_self", "純自選"),
        ("candidates", "候選與其他來源"),
        ("saved_codes", "已保存股票代碼清單"),
        ("research_bookmarks", "保存研究與查詢"),
        ("comparison", "來源內比較／返回原研究"),
    )

    def __init__(self, watchlist_view: QWidget) -> None:
        super().__init__(watchlist_view)
        self.watchlist_view = watchlist_view
        self._installed = False
        self._active_section = "candidates"
        self._connected_model: Any | None = None
        self._connected_selection_model: Any | None = None
        self._transitioning = False

    def install(self) -> bool:
        """在既有頁面前插入單層導覽，不移動任何現有 widget。"""
        if self._installed:
            return True
        view = self.watchlist_view
        splitter = getattr(view, "main_splitter", None)
        scroll = getattr(view, "page_scroll", None)
        content = scroll.widget() if scroll is not None and hasattr(scroll, "widget") else None
        layout = content.layout() if isinstance(content, QWidget) else None
        if splitter is None or layout is None or splitter.count() < 2:
            return False

        self.content = content
        self.content_layout = layout
        self.main_splitter = splitter
        self.candidate_panel = splitter.widget(0)
        self.saved_codes_panel = splitter.widget(1)
        self.section_selector = QComboBox(content)
        self.section_selector.setObjectName("watchlistProductSectionSelector")
        self.section_selector.setAccessibleName("候選與保存資料區")
        self.section_selector.setToolTip("切換純自選、其他來源候選、股票代碼清單、保存研究或來源內比較。")
        for key, label in self._SECTIONS:
            self.section_selector.addItem(label, key)

        self.section_status = QLabel(content)
        self.section_status.setObjectName("watchlistProductSectionStatus")
        self.section_status.setProperty("role", "muted")
        self.section_status.setWordWrap(True)

        self.comparison_panel = QWidget(content)
        self.comparison_panel.setObjectName("watchlistOriginalComparisonPanel")
        comparison_layout = QVBoxLayout(self.comparison_panel)
        self.comparison_status = QLabel(
            "此處可開啟所選研究保存時的來源內比較；尚不支援另外建立或編輯獨立比較清單。"
            "請先在「保存研究與查詢」選取一筆研究。",
            self.comparison_panel,
        )
        self.comparison_status.setWordWrap(True)
        self.comparison_button = QPushButton("開啟來源內比較", self.comparison_panel)
        self.comparison_button.setObjectName("watchlistOpenOriginalComparison")
        self.comparison_button.setEnabled(False)
        self.comparison_button.setToolTip("返回所選研究保存時的來源內比較。")
        comparison_layout.addWidget(self.comparison_status)
        comparison_layout.addWidget(self.comparison_button)
        comparison_layout.addStretch(1)
        self.comparison_panel.hide()

        splitter_index = layout.indexOf(splitter)
        if splitter_index < 0:
            return False
        layout.insertWidget(splitter_index, self.section_selector)
        layout.insertWidget(splitter_index + 1, self.section_status)
        layout.insertWidget(splitter_index + 3, self.comparison_panel, 1)

        self.section_selector.currentIndexChanged.connect(self._on_selector_changed)
        self.comparison_button.clicked.connect(self._request_comparison)
        updated = getattr(view, "watchlistUpdated", None)
        if updated is not None and hasattr(updated, "connect"):
            updated.connect(self.sync_rows)
        loaded = getattr(view, "watchlistLoaded", None)
        if loaded is not None and hasattr(loaded, "connect"):
            loaded.connect(self.sync_rows)
        refresh_button = getattr(view, "refresh_btn", None)
        clicked = getattr(refresh_button, "clicked", None)
        if clicked is not None and hasattr(clicked, "connect"):
            # 既有同步讀取 callback 先執行；其後再對新 model 做純呈現同步。
            clicked.connect(self.sync_rows)

        self._installed = True
        return self.select_section("pure_self")

    def _on_selector_changed(self, index: int) -> None:
        if self._transitioning or index < 0:
            return
        key = self.section_selector.itemData(index)
        if isinstance(key, str):
            self.select_section(key)

    def select_section(self, section: str) -> bool:
        """切換顯示區；只改 widget visibility 與現有表格的 row-hidden 狀態。"""
        if not self._installed or section not in {key for key, _ in self._SECTIONS}:
            return False
        self._active_section = section
        self._transitioning = True
        index = self.section_selector.findData(section)
        self.section_selector.setCurrentIndex(index)
        self._transitioning = False

        if section == "comparison":
            self.main_splitter.hide()
            self.comparison_panel.show()
            self.section_status.setText(
                "此處可開啟所選研究保存時的來源內比較；尚不支援另外建立或編輯獨立比較清單。"
            )
            self.sync_rows()
            return True

        self.comparison_panel.hide()
        self.main_splitter.show()
        if section == "saved_codes":
            self.candidate_panel.hide()
            self.saved_codes_panel.show()
            self.section_status.setText(
                "這類清單只保存股票代碼，不包含當時的研究條件或資料版本。"
            )
            self.sync_rows()
            return True

        self.candidate_panel.show()
        self.saved_codes_panel.hide()
        if section == "pure_self":
            self.section_status.setText(
                "顯示手動加入的股票；可新增、移除或開啟個股研究。"
            )
        elif section == "candidates":
            self.section_status.setText(
                "保留其他來源的候選及未能核對的舊收藏，來源標記與原操作保持。"
            )
        else:
            self.section_status.setText(
                "已核對保存身份的研究與查詢；可回訪原來源。"
            )
        self.sync_rows()
        return True

    def sync_rows(self, *_args) -> bool:
        """重套既有 model 的純視覺列篩選，不讀服務、不寫入收藏。"""
        table = getattr(self.watchlist_view, "stocks_table", None)
        self._connect_selection_model(
            table.selectionModel() if table is not None else None
        )
        model = getattr(self.watchlist_view, "stocks_model", None)
        if table is None or model is None or table.model() is not model:
            self._update_comparison_action()
            return False
        dataframe_reader = getattr(model, "getDataFrame", None)
        if not callable(dataframe_reader):
            self._update_comparison_action()
            return False
        try:
            frame = dataframe_reader()
            row_count = len(frame)
        except (TypeError, ValueError):
            self._update_comparison_action()
            return False

        if self._connected_model is not model:
            self._disconnect_model_signals()
            model.layoutChanged.connect(self.sync_rows)
            model.modelReset.connect(self.sync_rows)
            self._connected_model = model

        section = self._active_section
        hidden_selected = False
        typed_rows: list[bool] = []
        for row_index in range(row_count):
            row = frame.iloc[row_index]
            typed = self._verified_research_bookmark(row)
            typed_rows.append(typed)
            if section == "research_bookmarks":
                hide = not typed
            elif section == "pure_self":
                hide = typed or str(row.get("source", "") or "").strip() != "manual"
            elif section == "candidates":
                hide = typed
            else:
                hide = False
            table.setRowHidden(row_index, hide)
            if hide and table.selectionModel() is not None:
                hidden_selected = hidden_selected or any(
                    selected.row() == row_index
                    for selected in table.selectionModel().selectedRows()
                )

        if hidden_selected and table.selectionModel() is not None:
            table.selectionModel().clearSelection()
            table.setCurrentIndex(QModelIndex())

        unknown_count = sum(
            1 for row_index, (_, row) in enumerate(frame.iterrows())
            if self._row_declares_bookmark(row) and not typed_rows[row_index]
        )
        typed_count = sum(typed_rows)
        if section == "research_bookmarks":
            message = f"已核對保存身份的研究與查詢：{typed_count} 筆；可回訪原來源。"
        elif section == "pure_self":
            pure_self_count = sum(
                1 for row_index, (_, row) in enumerate(frame.iterrows())
                if not typed_rows[row_index]
                and str(row.get("source", "") or "").strip() == "manual"
            )
            message = f"顯示手動加入的股票：{pure_self_count} 筆；可新增、移除或開啟個股研究。"
        elif section == "candidates":
            message = (
                "保留其他來源的候選及未能核對的舊收藏，來源標記與原操作保持。"
                + (
                    f"另有 {unknown_count} 筆未能核對的舊收藏，仍保留在候選區。"
                if unknown_count else "未能核對的舊收藏：0 筆。"
                )
            )
        else:
            message = self.section_status.text()
        self.section_status.setText(message)
        self._update_comparison_action()
        return True

    def _verified_research_bookmark(self, row: object) -> bool:
        if not isinstance(row, Mapping) and not callable(getattr(row, "get", None)):
            return False
        payload = row.get("research_bookmark")
        if not isinstance(payload, Mapping) or not isinstance(payload.get("schema_version"), str):
            return False
        try:
            bookmark = decode_daily_market_research_bookmark(payload)
        except (TypeError, ValueError):
            return False
        code = str(row.get("證券代號", row.get("stock_code", "")) or "").strip()
        source = str(row.get("source", "") or "").strip()
        source_id = str(row.get("source_id", "") or "").strip()
        payload_id = _bookmark_payload_id(dict(payload))
        typed_source = _bookmark_source(bookmark)
        return bool(
            type(payload_id) is str
            and payload_id
            and type(source_id) is str
            and source_id == payload_id
            and code
            and source
            and source == typed_source
            and getattr(bookmark, "stock_code", None) == code
        )

    def _disconnect_model_signals(self) -> None:
        """解除舊 model 的同步連線，避免換表後累積保留 model。"""
        model = self._connected_model
        if model is None:
            return
        for signal_name in ("layoutChanged", "modelReset"):
            signal = getattr(model, signal_name, None)
            disconnect = getattr(signal, "disconnect", None)
            if callable(disconnect):
                try:
                    disconnect(self.sync_rows)
                except (RuntimeError, TypeError):
                    pass
        self._connected_model = None

    def _connect_selection_model(self, selection_model: Any | None) -> None:
        """比較按鈕只訂閱目前表格的 selectionModel。"""
        if self._connected_selection_model is selection_model:
            return
        old_model = self._connected_selection_model
        old_signal = getattr(old_model, "selectionChanged", None)
        disconnect = getattr(old_signal, "disconnect", None)
        if callable(disconnect):
            try:
                disconnect(self._update_comparison_action)
            except (RuntimeError, TypeError):
                pass
        self._connected_selection_model = selection_model
        new_signal = getattr(selection_model, "selectionChanged", None)
        connect = getattr(new_signal, "connect", None)
        if callable(connect):
            connect(self._update_comparison_action)

    def _row_declares_bookmark(self, row: object) -> bool:
        checker = getattr(self.watchlist_view, "_row_declares_research_bookmark", None)
        if callable(checker):
            return bool(checker(row))
        getter = getattr(row, "get", None)
        return callable(getter) and bool(getter("research_bookmark"))

    def _selected_composite_envelope(self) -> Any | None:
        table = getattr(self.watchlist_view, "stocks_table", None)
        model = getattr(self.watchlist_view, "stocks_model", None)
        if table is None or model is None or table.model() is not model:
            return None
        selection = table.selectionModel()
        selected = selection.selectedRows() if selection is not None else []
        if len(selected) != 1:
            return None
        try:
            row = model.getDataFrame().iloc[selected[0].row()]
        except (AttributeError, IndexError, TypeError, ValueError):
            return None
        checker = getattr(self.watchlist_view, "_row_is_composite_bookmark", None)
        exact_reader = getattr(self.watchlist_view, "_exact_research_bookmark_id_for_row", None)
        if not callable(checker) or not checker(row) or not callable(exact_reader):
            return None
        try:
            exact_id = exact_reader(row)
        except (AttributeError, KeyError, TypeError, ValueError):
            return None
        if not exact_id or not self._verified_research_bookmark(row):
            return None
        try:
            from ui_qt.views.watchlist_view import _decode_composite_envelope

            return _decode_composite_envelope(row.get("research_bookmark"))
        except (TypeError, ValueError):
            return None

    def _update_comparison_action(self, *_args) -> None:
        if not hasattr(self, "comparison_button"):
            return
        envelope = self._selected_composite_envelope()
        self.comparison_button.setEnabled(envelope is not None)
        if envelope is None:
            self.comparison_status.setText(
                "此處可開啟所選研究保存時的來源內比較；尚不支援另外建立或編輯獨立比較清單。請先在「保存研究與查詢」選取一筆研究。"
            )
        else:
            self.comparison_status.setText(
                "已選取研究；可開啟保存時的來源內比較並返回原研究。"
            )

    def _request_comparison(self, *_args) -> None:
        envelope = self._selected_composite_envelope()
        if envelope is None:
            self._update_comparison_action()
            return
        self.comparisonRequested.emit(envelope)
