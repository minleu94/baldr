"""呈現已保存研究原件的 Paper 前置條件與明確缺件。"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from app_module.research_timeline_dtos import ResearchTimelineEntry


_KIND_LABELS = {
    "manual": "手動筆記",
    "price": "價格研究",
    "report": "報告判斷",
    "theme": "題材研究",
}


class ResearchPaperPrerequisiteDialog(QDialog):
    """只檢視既有研究與 Paper 資格缺件，不建立帳戶或改寫原件。"""

    paperStatusRequested = Signal()

    def __init__(self, entry: ResearchTimelineEntry, parent=None) -> None:
        super().__init__(parent)
        self.entry = entry
        self.setObjectName("researchPaperPrerequisiteDialog")
        self.setWindowTitle("檢查 Paper 條件")
        self.resize(720, 680)

        root = QVBoxLayout(self)
        intro = QLabel(
            "此檢查以已保存研究原件為起點。Paper 是模擬用途，不會下單；"
            "本頁只說明現有條件與缺件，不建立 Paper 帳戶。",
            self,
        )
        intro.setObjectName("researchPaperPrerequisiteIntro")
        intro.setTextFormat(Qt.TextFormat.PlainText)
        intro.setWordWrap(True)
        root.addWidget(intro)

        metadata = QFormLayout()
        self.metadata_text = QLabel(self)
        self.metadata_text.setObjectName("researchPaperPrerequisiteMetadata")
        self.metadata_text.setTextFormat(Qt.TextFormat.PlainText)
        self.metadata_text.setWordWrap(True)
        self.metadata_text.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        details = (
            f"原文種類：{_KIND_LABELS.get(entry.kind, entry.kind or '未提供')}\n"
            f"原件 ID：{entry.record_id or '未提供'}\n"
            f"股票：{entry.stock_code or '未提供'}\n"
            f"保存時間：{entry.recorded_at or '未提供'}\n"
            f"資料日：{entry.data_date or '未提供'}"
        )
        self.metadata_text.setText(details)
        metadata.addRow("研究原件", self.metadata_text)
        root.addLayout(metadata)

        source_label = QLabel("完整來源身份", self)
        source_label.setTextFormat(Qt.TextFormat.PlainText)
        root.addWidget(source_label)
        self.source_identity_text = QTextEdit(self)
        self.source_identity_text.setObjectName("researchPaperPrerequisiteSourceIdentity")
        self.source_identity_text.setReadOnly(True)
        self.source_identity_text.setAcceptRichText(False)
        self.source_identity_text.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.source_identity_text.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.source_identity_text.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.source_identity_text.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self.source_identity_text.setPlainText(entry.source_identity or "未提供來源身份")
        self.source_identity_text.setFixedHeight(74)
        root.addWidget(self.source_identity_text)

        original_label = QLabel("保存原文", self)
        original_label.setTextFormat(Qt.TextFormat.PlainText)
        root.addWidget(original_label)
        self.original_text = QTextEdit(self)
        self.original_text.setObjectName("researchPaperPrerequisiteOriginalText")
        self.original_text.setReadOnly(True)
        self.original_text.setAcceptRichText(False)
        self.original_text.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.original_text.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.original_text.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.original_text.setAccessibleName("已保存研究原件全文")
        self.original_text.setPlainText(entry.text)
        self.original_text.setMinimumHeight(120)
        root.addWidget(self.original_text, 1)

        self.blockers_label = QLabel(
            "尚未取得這筆研究對應的 Paper 帳戶身分、同日合格行情與可核現金，"
            "現行建帳流程尚未支援直接納入此研究。\n"
            "既有 Paper 帳本與等權重比較基準不能代替這些條件。",
            self,
        )
        self.blockers_label.setObjectName("researchPaperPrerequisiteBlockers")
        self.blockers_label.setTextFormat(Qt.TextFormat.PlainText)
        self.blockers_label.setWordWrap(True)
        root.addWidget(self.blockers_label)

        actions = QHBoxLayout()
        self.create_account_button = QPushButton("建立 Paper 帳戶", self)
        self.create_account_button.setObjectName("researchPaperPrerequisiteCreateAccount")
        self.create_account_button.setEnabled(False)
        self.create_account_button.setToolTip(self.blockers_label.text())
        actions.addWidget(self.create_account_button)
        self.paper_status_button = QPushButton("查看既有 Paper 狀態", self)
        self.paper_status_button.setObjectName("researchPaperPrerequisitePaperStatus")
        self.paper_status_button.clicked.connect(self.paperStatusRequested.emit)
        actions.addWidget(self.paper_status_button)
        self.close_button = QPushButton("返回原研究", self)
        self.close_button.setObjectName("researchPaperPrerequisiteReturn")
        self.close_button.clicked.connect(self.reject)
        actions.addWidget(self.close_button)
        root.addLayout(actions)


__all__ = ["ResearchPaperPrerequisiteDialog"]
