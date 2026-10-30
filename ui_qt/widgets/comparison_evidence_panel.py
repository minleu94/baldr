"""將所選比較欄的原證據分區呈現，不讀取來源或產生金融判斷。"""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextOption
from PySide6.QtWidgets import QDialog, QGroupBox, QHBoxLayout, QLabel, QTextBrowser, QVBoxLayout, QWidget
from ui_qt.theme import MIDNIGHT_ANALYST
from ui_qt.widgets.theme_widgets import CollapsibleSectionPanel


def style_comparison_dialog(dialog: QDialog) -> None:
    """隔離來源捲動區的透明背景規則，讓原生比較對話框可獨立閱讀。"""
    dialog.setObjectName("comparisonResearchDialog")
    selector = "QDialog#comparisonResearchDialog"
    dialog.setStyleSheet(
        f"{selector}, {selector} QWidget {{ background: {MIDNIGHT_ANALYST.app_bg}; }}"
        f"{selector} QLabel {{ background: transparent; }}"
        f"{selector} QGroupBox {{ background: {MIDNIGHT_ANALYST.surface_2}; }}"
        f"{selector} QTableView, {selector} QTextBrowser, {selector} QTextBrowser QWidget "
        f"{{ background: {MIDNIGHT_ANALYST.surface_1}; }}"
        f"{selector} QTableView::item {{ background: {MIDNIGHT_ANALYST.surface_1}; }}"
        f"{selector} QTableView::item:selected {{ background: {MIDNIGHT_ANALYST.table_selected}; }}"
    )


def compact_comparison_audit(panel: CollapsibleSectionPanel) -> None:
    """沿產品既有緊湊展開列，讓第一層高度留給表格與原證據。"""
    panel.layout.setContentsMargins(6, 2, 6, 2)
    panel.layout.setSpacing(2)
    panel.title_label.setStyleSheet(
        f"color: {MIDNIGHT_ANALYST.text_secondary}; font-size: 12px; "
        "font-weight: 700; padding: 0; border: none; background: transparent;"
    )
    panel.toggle_button.setStyleSheet("min-height: 0px; padding: 2px 6px;")
    panel.toggle_button.setFixedHeight(28)


class ComparisonEvidencePanel(QWidget):
    """支持、反證與未知原因只接受呼叫端提供的純文字。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setObjectName("comparisonEvidencePanel")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(4)
        self.heading = QLabel("點選股票欄或規則格，對照原證據。")
        self.heading.setTextFormat(Qt.TextFormat.PlainText)
        self.heading.setWordWrap(True)
        self.heading.setAccessibleName("目前比較的股票與規則")
        root.addWidget(self.heading)
        self.context = QLabel("")
        self.context.setTextFormat(Qt.TextFormat.PlainText)
        self.context.setWordWrap(True)
        self.context.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        root.addWidget(self.context)
        self.conditions = QLabel("")
        self.conditions.setTextFormat(Qt.TextFormat.PlainText)
        self.conditions.setWordWrap(True)
        self.conditions.setAccessibleName("所選欄的原查詢條件與範圍")
        self.conditions.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        root.addWidget(self.conditions)
        self.conditions.hide()
        columns = QHBoxLayout()
        self.values: dict[str, QTextBrowser] = {}
        for key, title in (("support", "支持依據"), ("counter", "反證與限制"), ("unknown", "未知原因")):
            value = QTextBrowser()
            value.setObjectName(f"comparisonEvidence_{key}")
            value.setAccessibleName(title + "原文")
            value.setOpenExternalLinks(False)
            value.setMinimumWidth(0)
            value.setMinimumHeight(72)
            value.setMaximumHeight(120)
            value.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
            self.values[key] = value
            if key == "unknown":
                self.unknown_details = CollapsibleSectionPanel(title, collapsed=True)
                self.unknown_details.setObjectName("comparisonUnknownDetails")
                self.unknown_details.layout.setContentsMargins(6, 2, 6, 2)
                self.unknown_details.layout.setSpacing(2)
                self.unknown_details.title_label.setStyleSheet(
                    f"color: {MIDNIGHT_ANALYST.text_muted}; font-size: 12px; "
                    "font-weight: 700; padding: 0; border: none; background: transparent;"
                )
                self.unknown_details.toggle_button.setStyleSheet(
                    f"color: {MIDNIGHT_ANALYST.text_muted}; min-height: 0px; padding: 2px 6px;"
                )
                self.unknown_details.content_layout.addWidget(value)
                value.setStyleSheet(
                    f"color: {MIDNIGHT_ANALYST.text_secondary}; background: {MIDNIGHT_ANALYST.surface_1};"
                )
                columns.addWidget(self.unknown_details, 1)
                continue
            group = QGroupBox(title)
            inner = QVBoxLayout(group)
            inner.setContentsMargins(6, 6, 6, 6)
            inner.addWidget(value)
            columns.addWidget(group, 1)
        root.addLayout(columns)

    def set_evidence(
        self, *, heading: str, context: str, supports: Sequence[str],
        counterevidence: Sequence[str], unknown_reasons: Sequence[str], conditions: str = "",
    ) -> None:
        self.heading.setText(heading)
        self.context.setText(context)
        self.conditions.setText(conditions)
        self.conditions.setVisible(bool(conditions))
        for key, lines, missing in (
            ("support", supports, "原件未提供支持理由。"),
            ("counter", counterevidence, "原件未提供反證；不代表沒有風險。"),
            ("unknown", unknown_reasons, "原件未提供未知原因；請核對狀態與資料日。"),
        ):
            self.values[key].setPlainText("\n".join(lines) if lines else missing)
            self.values[key].verticalScrollBar().setValue(0)
        count = len(unknown_reasons)
        self.unknown_details.title_label.setText(
            f"未知原因（{count} 項；選取查看）" if count else "未知原因（未提供；選取查看）"
        )
