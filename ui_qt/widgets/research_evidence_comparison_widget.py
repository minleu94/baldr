"""唯讀呈現研究紀錄當時封存證據與目前可讀資料。"""

from __future__ import annotations

from math import ceil

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QTextOption
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app_module.research_evidence_comparison_dtos import ResearchEvidenceComparison


class _WrappedTextCell(QTextEdit):
    """可選取純文字儲存格，並在任何字元邊界換行長 hash/path。"""

    def __init__(self, text: str, parent: QWidget) -> None:
        super().__init__(parent)
        self.setPlainText(text)
        self.setReadOnly(True)
        self.setAcceptRichText(False)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.document().setDocumentMargin(0)
        self.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setMinimumWidth(0)
        self.setStyleSheet(
            "QTextEdit { background: transparent; border: 0; padding: 0; }"
        )
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        policy = self.sizePolicy()
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)

    def text(self) -> str:
        """保留 QLabel.text() 同名讀取介面，回傳未改寫原文。"""
        return self.toPlainText()

    def heightForWidth(self, width: int) -> int:
        text_width = max(1, width - 2 * self.frameWidth())
        self.document().setTextWidth(text_width)
        document_height = self.document().documentLayout().documentSize().height()
        return ceil(document_height) + 2 * self.frameWidth()

    def sizeHint(self) -> QSize:
        return QSize(0, self.fontMetrics().height())

    def minimumSizeHint(self) -> QSize:
        return QSize(0, self.fontMetrics().height())


class ResearchEvidenceComparisonWidget(QWidget):
    """將欄位聯集放入固定欄與目前欄，缺值不以另一側補造。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("researchEvidenceComparison")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self.status_label = QLabel("選取研究紀錄後可對照當時固定證據與目前可讀資料。", self)
        self.status_label.setObjectName("researchEvidenceComparisonStatus")
        self.status_label.setTextFormat(Qt.TextFormat.PlainText)
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)

        self.scroll = QScrollArea(self)
        self.scroll.setObjectName("researchEvidenceComparisonScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.content = QWidget(self.scroll)
        # 固定內容寬度跟隨 viewport；長欄位須換行增加列高，不能把 grid 撐出橫向捲動。
        self.content.setMinimumWidth(0)
        self.content.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Preferred,
        )
        self.grid = QGridLayout(self.content)
        self.grid.setContentsMargins(2, 2, 8, 2)
        self.grid.setHorizontalSpacing(12)
        self.grid.setVerticalSpacing(5)
        self.scroll.setWidget(self.content)
        root.addWidget(self.scroll, 1)
        self.clear("尚未讀取對照資料。")

    def clear(self, message: str = "") -> None:
        while self.grid.count():
            item = self.grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.status_label.setText(message)
        self.scroll.setVisible(False)

    def show_comparison(self, comparison: ResearchEvidenceComparison) -> None:
        self.clear()
        self.status_label.setText(
            f"對照時間：{comparison.compared_at}；欄位值依各自來源顯示，不推算差值或報酬。"
        )
        original = comparison.original
        current = comparison.current
        headers = ("欄位", "當時固定證據", "目前可讀資料")
        for column, title in enumerate(headers):
            label = QLabel(title, self.content)
            label.setStyleSheet("font-weight: bold")
            self._configure_label(label)
            self.grid.addWidget(label, 0, column, Qt.AlignmentFlag.AlignTop)

        fields = list(dict.fromkeys(key for key, _value in original.fields))
        original_keys = set(fields)
        fields.extend(
            key for key, _value in current.fields if key not in original_keys
        )
        self._add_cell(1, 0, "來源類型")
        self._add_cell(1, 1, original.title)
        self._add_cell(1, 2, current.title)
        row = 2
        original_fields = dict(original.fields)
        current_fields = dict(current.fields)
        for key in fields:
            self._add_cell(row, 0, key)
            self._add_cell(row, 1, original_fields.get(key) or "未封存")
            self._add_cell(row, 2, current_fields.get(key) or "無可讀值")
            row += 1
        if not fields:
            self._add_cell(row, 0, "欄位")
            self._add_cell(row, 1, "未封存")
            self._add_cell(row, 2, "無可讀值")
            row += 1

        self._add_cell(row, 0, "可讀狀態")
        status_labels = {
            "available": "可讀",
            "unavailable": "不可用",
            "limited": "有限",
        }
        self._add_cell(row, 1, status_labels[original.status])
        self._add_cell(row, 2, status_labels[current.status])
        row += 1
        max_limitations = max(len(original.limitations), len(current.limitations))
        for index in range(max_limitations):
            self._add_cell(row, 0, f"來源限制 {index + 1}")
            self._add_cell(
                row,
                1,
                original.limitations[index] if index < len(original.limitations) else "無其他說明",
            )
            self._add_cell(
                row,
                2,
                current.limitations[index] if index < len(current.limitations) else "無其他說明",
            )
            row += 1
        self.grid.setColumnStretch(0, 1)
        self.grid.setColumnStretch(1, 2)
        self.grid.setColumnStretch(2, 2)
        for column in range(3):
            self.grid.setColumnMinimumWidth(column, 0)
        self.scroll.setVisible(True)

    def _add_cell(self, row: int, column: int, text: str) -> None:
        cell = _WrappedTextCell(text or "無可讀值", self.content)
        self.grid.addWidget(cell, row, column, Qt.AlignmentFlag.AlignTop)

    @staticmethod
    def _configure_label(label: QLabel) -> None:
        label.setTextFormat(Qt.TextFormat.PlainText)
        label.setWordWrap(True)
        label.setMinimumWidth(0)
        label.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Preferred,
        )


__all__ = ["ResearchEvidenceComparisonWidget"]
