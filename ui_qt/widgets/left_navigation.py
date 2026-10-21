from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Sequence

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap, QPen
from PySide6.QtWidgets import (
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ui_qt.theme import MIDNIGHT_ANALYST


_NAV_ICON_SVGS: dict[str, str] = {
    "command": """
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
            <path d="M12 4v4m0 8v4M4 12h4m8 0h4" />
            <circle cx="12" cy="12" r="3.2" />
            <circle cx="5" cy="5" r="2.2" />
            <circle cx="19" cy="5" r="2.2" />
            <circle cx="5" cy="19" r="2.2" />
            <circle cx="19" cy="19" r="2.2" />
            <path d="M6.7 6.7 9.8 9.8M17.3 6.7l-3.1 3.1M6.7 17.3l3.1-3.1M17.3 17.3l-3.1-3.1" />
        </svg>
    """,
    "radar": """
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
            <circle cx="12" cy="12" r="8.5" />
            <circle cx="12" cy="12" r="3" />
            <path d="M12 12 18 6" />
            <path d="M12 3.5v2M20.5 12h-2M12 20.5v-2M3.5 12h2" />
        </svg>
    """,
    "spark-list": """
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
            <path d="M8 7h11M8 12h11M8 17h7" />
            <path d="M4.5 5.5 5.2 7l1.6.7-1.6.7-.7 1.6-.7-1.6-1.6-.7 1.6-.7.7-1.5Z" />
        </svg>
    """,
    "replay": """
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
            <path d="M6 8a7 7 0 1 1 1 9.5" />
            <path d="M6 8V4H2" />
            <path d="M8 15l3-3 3 2 3-5" />
        </svg>
    """,
    "bookmark": """
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
            <path d="M7 4.5h10a1.5 1.5 0 0 1 1.5 1.5v14L12 16.2 5.5 20V6A1.5 1.5 0 0 1 7 4.5Z" />
        </svg>
    """,
    "briefcase": """
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
            <path d="M8.5 8V6.5A1.5 1.5 0 0 1 10 5h4a1.5 1.5 0 0 1 1.5 1.5V8" />
            <rect x="4" y="8" width="16" height="11" rx="2" />
            <path d="M4 12.5h16M10 12.5v1h4v-1" />
        </svg>
    """,
    "database-sync": """
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
            <ellipse cx="11" cy="6" rx="6.5" ry="2.5" />
            <path d="M4.5 6v5c0 1.4 2.9 2.5 6.5 2.5 1.3 0 2.6-.2 3.6-.5" />
            <path d="M4.5 11v5c0 1.4 2.9 2.5 6.5 2.5 1 0 1.9-.1 2.8-.3" />
            <path d="M17 13.5h3v-3M20 13.5a4.5 4.5 0 0 0-7.5-2" />
            <path d="M15 18.5h-3v3M12 18.5a4.5 4.5 0 0 0 7.5 2" />
        </svg>
    """,
    "pulse": """
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
            <path d="M3 12h4l2-6 4 12 2-6h6" />
            <path d="M5 5.5a9 9 0 0 1 14 0M5 18.5a9 9 0 0 0 14 0" />
        </svg>
    """,
}


_NAV_GROUPS: tuple[tuple[str, str], ...] = (
    ("daily", "日常使用"),
    ("research", "進階研究"),
    ("maintenance", "系統維護"),
)

_NAV_GROUP_BY_KEY: dict[str, str] = {
    "workbench": "daily",
    "market_explore": "daily",
    "recommendation": "daily",
    "watchlist": "daily",
    "stock_research": "daily",
    "portfolio": "daily",
    "backtest": "research",
    "update": "maintenance",
    "runtime": "maintenance",
}


@dataclass(frozen=True)
class NavigationItem:
    key: str
    label: str
    icon: str = ""
    badge: str = ""
    tooltip: str = ""


class _NavigationGroupButton(QToolButton):
    """以固定左側內容起點繪製分組按鈕。

    QToolButton 的 Fusion style 會把純文字工具按鈕置中，且 stylesheet 的
    ``text-align`` 不會改變該 style 的文字繪製位置。分組標題若被置中，會
    看起來比下方 workspace 更深一層；這裡保留 QToolButton 的 checkable／
    keyboard 行為，但直接繪製背景、focus ring 與左靠文字，讓父層與子項
    的縮排由 layout 與明確內容起點決定。
    """

    _CONTENT_LEFT = 6
    _CONTENT_RIGHT = 4

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setCursor(Qt.PointingHandCursor)
        self.setMouseTracking(True)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        draw_rect = self.rect().adjusted(0, 0, -1, -1)

        if self.underMouse():
            painter.setBrush(QColor(MIDNIGHT_ANALYST.surface_2))
        else:
            painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor(MIDNIGHT_ANALYST.border), 1))
        if self.underMouse():
            painter.drawRoundedRect(draw_rect, MIDNIGHT_ANALYST.radius_panel, MIDNIGHT_ANALYST.radius_panel)

        if self.hasFocus():
            painter.setPen(QPen(QColor(MIDNIGHT_ANALYST.accent), 1))
            painter.drawRoundedRect(draw_rect, MIDNIGHT_ANALYST.radius_panel, MIDNIGHT_ANALYST.radius_panel)

        if self.text():
            painter.setPen(QColor(MIDNIGHT_ANALYST.text_muted))
            painter.setFont(self.font())
            text_rect = self.rect().adjusted(
                self._CONTENT_LEFT,
                0,
                -self._CONTENT_RIGHT,
                0,
            )
            painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter, self.text())


class LeftNavigationWidget(QWidget):
    """Left-side main workspace navigation."""

    workspaceSelected = Signal(str)

    def __init__(
        self,
        items: Sequence[NavigationItem],
        parent=None,
        *,
        primary_mode: bool = False,
    ) -> None:
        super().__init__(parent)
        self._items = tuple(items)
        self._primary_mode = primary_mode
        self._buttons: dict[str, QPushButton] = {}
        self._group_buttons: dict[str, QToolButton] = {}
        self._group_items: dict[str, tuple[str, ...]] = {}
        self._group_expanded: dict[str, bool] = {}
        self._current_key: str | None = None
        self._collapsed = False

        self.setObjectName("leftWorkspaceNavigation")
        self.setFixedWidth(184)
        self.setMaximumWidth(184)
        self.setStyleSheet(
            f"#leftWorkspaceNavigation {{ background: {MIDNIGHT_ANALYST.surface_1}; "
            f"border-right: 1px solid {MIDNIGHT_ANALYST.border}; }}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 12, 10, 12)
        layout.setSpacing(6)

        self.collapse_button = QPushButton("‹")
        self.collapse_button.setObjectName("leftNavCollapseButton")
        self.collapse_button.setToolTip("收合左側導覽")
        self.collapse_button.setAccessibleName("收合左側導覽")
        self.collapse_button.setMinimumHeight(30)
        self.collapse_button.clicked.connect(lambda _checked=False: self.set_collapsed(not self._collapsed))
        layout.addWidget(self.collapse_button)

        if self._primary_mode:
            system_items = tuple(item for item in self._items if self._is_system_item(item))
            primary_items = tuple(item for item in self._items if not self._is_system_item(item))
            for item in primary_items:
                self._add_workspace_button(layout, item)
            layout.addStretch()
            for item in system_items:
                self._add_workspace_button(layout, item)
        else:
            grouped_items: dict[str, list[NavigationItem]] = {
                group_id: [] for group_id, _label in _NAV_GROUPS
            }
            for item in self._items:
                group_id = _NAV_GROUP_BY_KEY.get(item.key, "research")
                grouped_items.setdefault(group_id, []).append(item)

            for group_id, group_label in _NAV_GROUPS:
                group_items = grouped_items.get(group_id, [])
                if not group_items:
                    continue
                self._group_expanded[group_id] = True
                group_button = _NavigationGroupButton()
                group_button.setObjectName(f"leftNavGroup_{group_id}")
                group_button.setCheckable(True)
                group_button.setChecked(True)
                group_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                group_button.setMinimumHeight(26)
                group_button.setAccessibleName(f"導覽分組：{group_label}")
                group_button.setToolTip(f"展開或收合{group_label}")
                group_button.clicked.connect(
                    lambda checked, key=group_id: self._toggle_group(key, checked)
                )
                self._group_buttons[group_id] = group_button
                self._group_items[group_id] = tuple(item.key for item in group_items)
                layout.addWidget(group_button)

                for item in group_items:
                    self._add_workspace_button(layout, item)

            layout.addStretch()
        self._refresh_group_button_text()
        self._apply_styles()

    def item_keys(self) -> list[str]:
        return [item.key for item in self._items]

    def button_for_key(self, key: str) -> QPushButton | None:
        return self._buttons.get(key)

    def group_button_for_id(self, group_id: str) -> QToolButton | None:
        """提供測試與無障礙導覽使用的分組控制項。"""

        return self._group_buttons.get(group_id)

    def current_key(self) -> str | None:
        return self._current_key

    def label_for_key(self, key: str) -> str | None:
        for item in self._items:
            if item.key == key:
                if self._primary_mode and self._is_system_item(item):
                    return self._display_label(item)
                # 舊呼叫端仍以 Runtime 作為穩定識別文字；畫面按鈕使用新的白話標籤。
                if item.key == "runtime" and item.label == "系統狀態":
                    return "Runtime"
                return item.label
        return None

    def is_collapsed(self) -> bool:
        return self._collapsed

    def set_collapsed(self, collapsed: bool) -> None:
        self._collapsed = bool(collapsed)
        width = 58 if self._collapsed else 184
        self.setFixedWidth(width)
        self.setMaximumWidth(width)
        self.collapse_button.setText("›" if self._collapsed else "‹")
        self.collapse_button.setToolTip("展開左側導覽" if self._collapsed else "收合左側導覽")
        self.collapse_button.setAccessibleName(
            "展開左側導覽" if self._collapsed else "收合左側導覽"
        )
        self._refresh_group_button_text()
        for item in self._items:
            button = self._buttons[item.key]
            button.setText(self._button_text(item))
            button.setIconSize(QSize(22, 22) if self._collapsed else QSize(20, 20))
            button.setToolTip(item.tooltip or self._display_label(item))

    def set_current_key(self, key: str) -> None:
        if key not in self._buttons:
            return
        self._current_key = key
        group_id = self._group_for_key(key)
        if group_id and not self._group_expanded.get(group_id, True):
            self._set_group_expanded(group_id, True)
        for item_key, button in self._buttons.items():
            is_active = item_key == key
            button.setChecked(is_active)
            button.setProperty("active", is_active)
            button.style().unpolish(button)
            button.style().polish(button)

    def _select_from_click(self, key: str) -> None:
        if key == self._current_key:
            if not self._primary_mode:
                self.set_collapsed(not self._collapsed)
            return
        self.set_current_key(key)
        self.workspaceSelected.emit(key)

    def _add_workspace_button(self, layout: QVBoxLayout, item: NavigationItem) -> None:
        button = QPushButton(self._button_text(item))
        button.setObjectName(f"leftNavButton_{item.key}")
        button.setCheckable(True)
        button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        button.setMinimumHeight(34)
        button.setIcon(self._icon_for_item(item))
        button.setIconSize(QSize(20, 20))
        display_label = self._display_label(item)
        button.setToolTip(item.tooltip or display_label)
        button.setAccessibleName(display_label)
        button.clicked.connect(lambda _checked=False, key=item.key: self._select_from_click(key))
        self._buttons[item.key] = button
        layout.addWidget(button)

    @staticmethod
    def _is_system_item(item: NavigationItem) -> bool:
        normalized_label = item.label.strip()
        return item.key in {"systems", "system_management"} or normalized_label in {
            "⚙ 系統管理",
            "系統管理",
        }

    def _button_text(self, item: NavigationItem) -> str:
        display_label = self._display_label(item)
        if self._collapsed:
            return "" if item.icon in _NAV_ICON_SVGS else display_label[:1]
        display_label = (
            "系統狀態"
            if item.key == "runtime" and item.label == "系統狀態"
            else display_label
        )
        pieces = []
        pieces.append(display_label)
        if item.badge:
            pieces.append(item.badge)
        return "  ".join(pieces)

    def _display_label(self, item: NavigationItem) -> str:
        if self._primary_mode and self._is_system_item(item):
            return "⚙ 系統管理"
        return item.label

    def _group_for_key(self, key: str) -> str | None:
        for group_id, keys in self._group_items.items():
            if key in keys:
                return group_id
        return None

    def _toggle_group(self, group_id: str, expanded: bool) -> None:
        self._set_group_expanded(group_id, bool(expanded))

    def _set_group_expanded(self, group_id: str, expanded: bool) -> None:
        if group_id not in self._group_buttons:
            return
        self._group_expanded[group_id] = bool(expanded)
        group_button = self._group_buttons[group_id]
        group_button.blockSignals(True)
        group_button.setChecked(bool(expanded))
        group_button.blockSignals(False)
        self._refresh_group_button_text(group_id)
        for key in self._group_items.get(group_id, ()):
            button = self._buttons.get(key)
            if button is not None:
                # 讓目前 active workspace 在手動收合時仍可被看見。
                button.setVisible(bool(expanded) or key == self._current_key)

    def _refresh_group_button_text(self, group_id: str | None = None) -> None:
        group_ids = (group_id,) if group_id else tuple(self._group_buttons)
        labels = dict(_NAV_GROUPS)
        for current_id in group_ids:
            button = self._group_buttons.get(current_id)
            if button is None:
                continue
            label = labels.get(current_id, current_id)
            if self._collapsed:
                button.setText("")
            else:
                # 使用 ASCII marker，避免部分 msjh 字型在自繪 QPainter 中
                # 缺少幾何符號時顯示成方框；鍵盤與 tooltip 仍保留完整語意。
                marker = "v" if self._group_expanded.get(current_id, True) else ">"
                button.setText(f"{marker} {label}")

    def _icon_for_item(self, item: NavigationItem) -> QIcon:
        svg = _NAV_ICON_SVGS.get(item.icon, "")
        if not svg:
            return QIcon()
        return _icon_from_svg(svg, MIDNIGHT_ANALYST.text_secondary)

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            f"""
            #leftWorkspaceNavigation {{
                background: {MIDNIGHT_ANALYST.surface_1};
                border-right: 1px solid {MIDNIGHT_ANALYST.border};
            }}
            QPushButton {{
                background: transparent;
                color: {MIDNIGHT_ANALYST.text_secondary};
                border: 1px solid transparent;
                border-radius: {MIDNIGHT_ANALYST.radius_panel}px;
                padding: 7px 10px;
                text-align: left;
                font-weight: 600;
            }}
            QToolButton#leftNavGroup_daily,
            QToolButton#leftNavGroup_research,
            QToolButton#leftNavGroup_maintenance {{
                background: transparent;
                color: {MIDNIGHT_ANALYST.text_muted};
                border: 1px solid transparent;
                border-radius: {MIDNIGHT_ANALYST.radius_panel}px;
                padding: 4px 6px;
                text-align: left;
                font-size: 11px;
                font-weight: 700;
            }}
            #leftNavCollapseButton {{
                color: {MIDNIGHT_ANALYST.text_muted};
                text-align: center;
                font-weight: 700;
            }}
            QPushButton:hover {{
                background: {MIDNIGHT_ANALYST.surface_2};
                color: {MIDNIGHT_ANALYST.text_primary};
            }}
            QToolButton#leftNavGroup_daily:hover,
            QToolButton#leftNavGroup_research:hover,
            QToolButton#leftNavGroup_maintenance:hover {{
                background: {MIDNIGHT_ANALYST.surface_2};
                color: {MIDNIGHT_ANALYST.text_primary};
            }}
            QPushButton[active="true"] {{
                background: {MIDNIGHT_ANALYST.surface_3};
                color: {MIDNIGHT_ANALYST.text_primary};
                border: 1px solid {MIDNIGHT_ANALYST.accent};
            }}
            """
        )


def _icon_from_svg(svg_body: str, stroke_color: str) -> QIcon:
    svg = (
        svg_body.replace("<svg ", f'<svg fill="none" stroke="{stroke_color}" stroke-width="1.8" ')
        .replace("<path ", '<path stroke-linecap="round" stroke-linejoin="round" ')
        .replace("<circle ", '<circle stroke-linecap="round" stroke-linejoin="round" ')
        .replace("<rect ", '<rect stroke-linecap="round" stroke-linejoin="round" ')
        .replace("<ellipse ", '<ellipse stroke-linecap="round" stroke-linejoin="round" ')
    )
    pixmap = QPixmap()
    pixmap.loadFromData(svg.encode("utf-8"), "SVG")
    return QIcon(pixmap)
