"""重用既有市場分析頁的單頁工作區。"""

from __future__ import annotations

from collections.abc import Mapping

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QHBoxLayout,
    QLayout,
    QSizePolicy,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


_REQUIRED_WIDGET_KEYS = frozenset(
    {
        "summary",
        "index",
        "strong_stocks",
        "weak_stocks",
        "strong_industries",
        "weak_industries",
        "flow",
    }
)
_ALLOWED_WIDGET_KEYS = _REQUIRED_WIDGET_KEYS | {"cohort"}
_CATEGORY_BY_KEY = {
    "summary": "overview",
    "index": "overview",
    "cohort": "overview",
    "strong_stocks": "stocks",
    "weak_stocks": "stocks",
    "strong_industries": "industries",
    "weak_industries": "industries",
    "flow": "flow",
}


class MarketAnalysisWorkspace(QWidget):
    """以單一選擇列呈現原有市場分析 widgets，不複製資料或頁面。"""

    _PRIMARY_VIEWS = (
        ("overview", "市場概況"),
        ("stocks", "股票排行"),
        ("industries", "產業排行"),
        ("flow", "部分樣本流向"),
    )
    _OVERVIEW_KEYS = ("summary", "index", "cohort")

    def minimumSizeHint(self) -> QSize:  # noqa: N802 - Qt 覆寫
        """原頁面由其表格／捲動區承接高度，不讓隱藏分頁撐大桌面視窗。"""
        return QSize(0, 0)

    def __init__(
        self,
        legacy_tabs: QTabWidget,
        widgets: Mapping[str, QWidget],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        if not isinstance(legacy_tabs, QTabWidget):
            raise TypeError("legacy_tabs 必須是既有 QTabWidget")
        if not isinstance(widgets, Mapping):
            raise TypeError("widgets 必須是 key 到 QWidget 的 mapping")

        unknown_keys = set(widgets) - _ALLOWED_WIDGET_KEYS
        missing_keys = _REQUIRED_WIDGET_KEYS - set(widgets)
        if unknown_keys:
            raise ValueError(f"不支援的市場分析 widget key：{sorted(unknown_keys)}")
        if missing_keys:
            raise ValueError(f"缺少必要的市場分析 widget：{sorted(missing_keys)}")

        self.legacy_tabs = legacy_tabs
        self._widgets = dict(widgets)
        self._key_by_widget: dict[QWidget, str] = {}
        for key, widget in self._widgets.items():
            if not isinstance(widget, QWidget):
                raise TypeError(f"市場分析 widget {key!r} 必須是 QWidget")
            if legacy_tabs.indexOf(widget) < 0:
                raise ValueError(f"市場分析 widget {key!r} 不在 legacy_tabs 中")
            if widget in self._key_by_widget:
                raise ValueError("每個市場分析 widget 只能對應一個 key")
            self._key_by_widget[widget] = key

        self.setObjectName("MarketAnalysisWorkspace")
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )

        self.primary_view_selector = QComboBox(self)
        self.primary_view_selector.setObjectName("MarketAnalysisPrimaryView")
        self.primary_view_selector.setAccessibleName("市場分析主視角")
        for view_key, label in self._PRIMARY_VIEWS:
            self.primary_view_selector.addItem(label, view_key)

        self.overview_selector = QComboBox(self)
        self.overview_selector.setObjectName("MarketAnalysisOverviewView")
        self.overview_selector.setAccessibleName("市場概況內容")
        for key in self._OVERVIEW_KEYS:
            if key in self._widgets:
                self.overview_selector.addItem(self._label_for_key(key), key)

        self._direction_group = QButtonGroup(self)
        self._direction_group.setExclusive(True)
        self.direction_buttons: dict[str, QToolButton] = {}
        for direction, label in (("strong", "強勢"), ("weak", "弱勢")):
            button = QToolButton(self)
            button.setObjectName(f"MarketAnalysisDirection_{direction}")
            button.setText(label)
            button.setAccessibleName(label)
            button.setCheckable(True)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            button.clicked.connect(
                lambda _checked=False, selected=direction: self._select_direction(
                    selected
                )
            )
            self._direction_group.addButton(button)
            self.direction_buttons[direction] = button

        self.controls_bar = QWidget(self)
        self.controls_bar.setObjectName("MarketAnalysisControls")
        controls = QHBoxLayout(self.controls_bar)
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(8)
        controls.addWidget(self.primary_view_selector)
        controls.addWidget(self.overview_selector)
        controls.addWidget(self.direction_buttons["strong"])
        controls.addWidget(self.direction_buttons["weak"])
        controls.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self.controls_bar)
        # QTabWidget 仍是唯一內容 stack；原表格高度與水平捲軸不受外層捲動區影響。
        layout.addWidget(self.legacy_tabs, 1)
        self.legacy_tabs.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Ignored)
        self.legacy_tabs.tabBar().hide()

        self.primary_view_selector.currentIndexChanged.connect(
            self._on_primary_view_changed
        )
        self.overview_selector.currentIndexChanged.connect(
            self._on_overview_view_changed
        )
        self.legacy_tabs.currentChanged.connect(self._sync_controls_from_tabs)

        self._last_overview_key = "summary"
        self._last_stock_key = "strong_stocks"
        self._last_industry_key = "strong_industries"
        current_key = self._key_by_widget.get(self.legacy_tabs.currentWidget())
        if current_key is None:
            self.controls_bar.hide()
        else:
            self._sync_controls_for_key(current_key)

    @staticmethod
    def _label_for_key(key: str) -> str:
        return {
            "summary": "市場總覽",
            "index": "市場指數",
            "cohort": "母體盤勢",
        }[key]

    def _available_overview_key(self) -> str:
        if self._last_overview_key in self._widgets:
            return self._last_overview_key
        return next(key for key in self._OVERVIEW_KEYS if key in self._widgets)

    def _select_direction(self, direction: str) -> bool:
        category_index = self.primary_view_selector.currentData()
        if category_index == "industries":
            key = f"{direction}_industries"
        else:
            key = f"{direction}_stocks"
        return self.select_view(key)

    def _on_primary_view_changed(self, _index: int) -> None:
        view_key = self.primary_view_selector.currentData()
        if view_key == "overview":
            self.select_view(self._available_overview_key())
        elif view_key == "stocks":
            key = self._last_stock_key
            self.select_view(key if key in self._widgets else "strong_stocks")
        elif view_key == "industries":
            key = self._last_industry_key
            self.select_view(key if key in self._widgets else "strong_industries")
        elif view_key == "flow":
            self.select_view("flow")

    def _on_overview_view_changed(self, _index: int) -> None:
        key = self.overview_selector.currentData()
        if isinstance(key, str):
            self.select_view(key)

    def _sync_controls_from_tabs(self, _index: int) -> None:
        key = self._key_by_widget.get(self.legacy_tabs.currentWidget())
        if key is None:
            # 題材頁由獨立 route 負責；舊 tab 仍留在 stack 並由外部導航使用。
            self.controls_bar.hide()
            return
        self.controls_bar.show()
        self._sync_controls_for_key(key)

    def _sync_controls_for_key(self, key: str) -> None:
        category = _CATEGORY_BY_KEY[key]
        if category == "overview":
            self._last_overview_key = key
        elif category == "stocks":
            self._last_stock_key = key
        elif category == "industries":
            self._last_industry_key = key

        self._set_combo_data(self.primary_view_selector, category)
        self._set_combo_data(
            self.overview_selector,
            key if category == "overview" else None,
        )
        self.overview_selector.setVisible(category == "overview")
        show_direction = category in {"stocks", "industries"}
        self.direction_buttons["strong"].setVisible(show_direction)
        self.direction_buttons["weak"].setVisible(show_direction)
        if show_direction:
            direction = "strong" if key.startswith("strong_") else "weak"
            self.direction_buttons[direction].setChecked(True)

    @staticmethod
    def _set_combo_data(combo: QComboBox, value: str | None) -> None:
        old_block = combo.blockSignals(True)
        try:
            index = combo.findData(value) if value is not None else -1
            if index >= 0:
                combo.setCurrentIndex(index)
        finally:
            combo.blockSignals(old_block)

    def select_widget(self, widget: QWidget) -> bool:
        """依 widget 身分切換，未知或未映射的元件回傳 False。"""

        key = self._key_by_widget.get(widget)
        return self.select_view(key) if key is not None else False

    def select_view(self, key: str) -> bool:
        """切換至既有 view；未映射的 key 不改變目前頁面。"""

        widget = self._widgets.get(key)
        if widget is None:
            return False
        self.legacy_tabs.setCurrentWidget(widget)
        return self.legacy_tabs.currentWidget() is widget
