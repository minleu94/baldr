"""供 shell 重用的純文字全域搜尋輸入列。"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QWidget,
)

from ui_qt.theme import MIDNIGHT_ANALYST


class GlobalSearchBar(QWidget):
    """提供文字輸入與明確提交，不負責來源判斷或自動完成。"""

    searchRequested = Signal(str)

    DEFAULT_CONTEXT_LABEL = "各資料域日期依頁面標示"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("GlobalSearchBar")
        self.setAccessibleName("全域搜尋")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.search_edit = QLineEdit(self)
        self.search_edit.setObjectName("GlobalSearchInput")
        self.search_edit.setAccessibleName("搜尋文字")
        self.search_edit.setPlaceholderText("輸入代號、名稱、題材或產業鏈")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.search_edit.returnPressed.connect(self._submit_search)
        layout.addWidget(self.search_edit, 1)

        self.search_button = QPushButton("搜尋", self)
        self.search_button.setObjectName("GlobalSearchButton")
        self.search_button.setAccessibleName("提交搜尋")
        self.search_button.setProperty("variant", "primary")
        self.search_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.search_button.clicked.connect(self._submit_search)
        layout.addWidget(self.search_button)

        self.context_label = QLabel(self.DEFAULT_CONTEXT_LABEL, self)
        self.context_label.setObjectName("GlobalSearchContextLabel")
        self.context_label.setAccessibleName("資料日期狀態")
        self.context_label.setProperty("role", "muted")
        self.context_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)
        self.context_label.setMinimumWidth(180)
        self.context_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        layout.addWidget(self.context_label)

        self.setMinimumHeight(34)
        self.setMaximumHeight(40)
        self.setStyleSheet(
            f"""
            QWidget#GlobalSearchBar QLineEdit#GlobalSearchInput {{
                min-height: 26px;
                padding: 2px 8px;
                background: {MIDNIGHT_ANALYST.surface_1};
                color: {MIDNIGHT_ANALYST.text_primary};
                border: 1px solid {MIDNIGHT_ANALYST.border};
                border-radius: {MIDNIGHT_ANALYST.radius_badge}px;
            }}
            QWidget#GlobalSearchBar QLineEdit#GlobalSearchInput:focus {{
                border-color: {MIDNIGHT_ANALYST.accent};
            }}
            QWidget#GlobalSearchBar QLabel#GlobalSearchContextLabel {{
                color: {MIDNIGHT_ANALYST.text_secondary};
                font-size: 9pt;
            }}
            """
        )

    def focus_search(self) -> None:
        """將鍵盤焦點移至文字輸入欄。"""

        self.search_edit.setFocus(Qt.FocusReason.ShortcutFocusReason)

    def set_context_label(self, text: str) -> None:
        """設定頂列可見的資料日期或狀態摘要。"""

        self.context_label.setText(text)
        self.context_label.setToolTip(text)

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt override
        return QSize(520, 36)

    def minimumSizeHint(self) -> QSize:  # noqa: N802 - Qt override
        return QSize(180, 34)

    def _submit_search(self) -> None:
        query = self.search_edit.text()
        if query.strip():
            # 保留使用者輸入的原始空白與字詞，不替它推斷搜尋來源。
            self.searchRequested.emit(query)
