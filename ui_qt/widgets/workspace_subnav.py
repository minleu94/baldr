"""輕量工作區子頁導覽列。"""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import QAbstractButton, QButtonGroup, QHBoxLayout, QToolButton, QSizePolicy, QWidget

from ui_qt.theme import MIDNIGHT_ANALYST


class WorkspaceSubnav(QWidget):
    """以單列按鈕呈現目前工作區的一層子頁導覽。"""

    routeSelected = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("WorkspaceSubnav")
        self.setAccessibleName("工作區子頁導覽")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(6)
        self._button_group = QButtonGroup(self)
        self._button_group.setExclusive(True)
        self._button_group.buttonClicked.connect(self._on_button_clicked)
        self._buttons: dict[str, QToolButton] = {}
        self._current_route: str | None = None
        self._routes: tuple[tuple[str, str], ...] = ()

    @property
    def current_route(self) -> str | None:
        """目前選取的 route id；尚未設定時為 ``None``。"""

        return self._current_route

    def set_routes(self, routes: Sequence[tuple[str, str]]) -> None:
        """設定最多四個子頁，tuple 依序為 ``(route_id, label)``。"""

        normalized = tuple(routes)
        if len(normalized) > 4:
            raise ValueError("工作區子頁最多只能設定四項")
        route_ids = [route_id for route_id, _label in normalized]
        if any(not isinstance(route_id, str) or not route_id.strip() for route_id in route_ids):
            raise ValueError("route_id 必須是非空字串")
        if len(set(route_ids)) != len(route_ids):
            raise ValueError("route_id 不可重複")
        if any(not isinstance(label, str) or not label.strip() for _route_id, label in normalized):
            raise ValueError("子頁標籤必須是非空字串")
        if normalized == self._routes:
            return

        previous_route = self._current_route
        self._clear_buttons()
        self._routes = normalized
        for index, (route_id, label) in enumerate(normalized):
            button = QToolButton(self)
            button.setObjectName(f"WorkspaceSubnavRoute_{route_id}")
            button.setText(label)
            button.setAccessibleName(label)
            button.setCheckable(True)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            button.setProperty("routeId", route_id)
            self._button_group.addButton(button, index)
            self._layout.addWidget(button)
            self._buttons[route_id] = button

        self._layout.addStretch(1)
        self.setStyleSheet(
            f"""
            QWidget#WorkspaceSubnav QToolButton {{
                min-height: 28px;
                padding: 3px 10px;
                color: {MIDNIGHT_ANALYST.text_secondary};
                background: {MIDNIGHT_ANALYST.surface_2};
                border: 1px solid {MIDNIGHT_ANALYST.border};
                border-radius: {MIDNIGHT_ANALYST.radius_badge}px;
            }}
            QWidget#WorkspaceSubnav QToolButton:hover {{
                color: {MIDNIGHT_ANALYST.text_primary};
                border-color: {MIDNIGHT_ANALYST.accent};
            }}
            QWidget#WorkspaceSubnav QToolButton:checked {{
                color: {MIDNIGHT_ANALYST.text_primary};
                background: {MIDNIGHT_ANALYST.surface_3};
                border-color: {MIDNIGHT_ANALYST.accent};
            }}
            """
        )
        self._current_route = None
        if previous_route in self._buttons:
            self.set_current_route(previous_route)
        elif self._buttons:
            self.set_current_route(next(iter(self._buttons)))

    def set_current_route(self, route_id: str) -> None:
        """選取已設定的子頁，不會因程式設定而發出導覽訊號。"""

        button = self._buttons.get(route_id)
        if button is None:
            raise ValueError(f"未設定的 route_id：{route_id}")
        self._current_route = route_id
        button.setChecked(True)

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt override
        return QSize(280, 34)

    def minimumSizeHint(self) -> QSize:  # noqa: N802 - Qt override
        return QSize(0, 30)

    def _clear_buttons(self) -> None:
        for button in self._buttons.values():
            self._button_group.removeButton(button)
            self._layout.removeWidget(button)
            button.hide()
            button.deleteLater()
        self._buttons.clear()
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget() is not None:
                self._layout.removeWidget(item.widget())

    def _on_button_clicked(self, button: QAbstractButton) -> None:
        route_id = button.property("routeId")
        if not isinstance(route_id, str) or route_id == self._current_route:
            return
        self._current_route = route_id
        self.routeSelected.emit(route_id)
