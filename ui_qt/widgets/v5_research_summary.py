"""V5 研究頁共用的日常摘要元件。

這個元件只負責把既有 read model／DTO 的文字整理成固定閱讀順序：
結論、最多兩項重點或缺件、下一步。它不執行資料查詢、評分或交易判斷。
"""

from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QGroupBox, QLabel, QSizePolicy, QVBoxLayout


class V5ResearchSummary(QGroupBox):
    """用固定欄位呈現非技術使用者先看的研究摘要。"""

    def __init__(self, title: str, parent=None) -> None:
        super().__init__(title, parent)
        self.setObjectName("v5ResearchSummary")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)

        self.conclusion_label = self._label("v5ResearchConclusion")
        self.evidence_label = self._label("v5ResearchEvidence")
        self.change_label = self._label("v5ResearchChange")
        self.risk_label = self._label("v5ResearchRisk")
        self.sufficiency_label = self._label("v5ResearchSufficiency")
        self.reasons_label = self._label("v5ResearchReasons")
        self.next_step_label = self._label("v5ResearchNextStep")
        layout.addWidget(self.conclusion_label)
        layout.addWidget(self.evidence_label)
        layout.addWidget(self.change_label)
        layout.addWidget(self.risk_label)
        layout.addWidget(self.sufficiency_label)
        layout.addWidget(self.reasons_label)
        layout.addWidget(self.next_step_label)

        self.set_summary(
            conclusion="尚未有可閱讀的摘要。",
            reasons=("資料尚未載入。",),
            next_step="先選取一筆資料或重新整理。",
        )

    @staticmethod
    def _label(object_name: str) -> QLabel:
        label = QLabel()
        label.setObjectName(object_name)
        label.setWordWrap(True)
        label.setTextInteractionFlags(
            Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard
        )
        label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        return label

    def minimumSizeHint(self) -> QSize:  # noqa: N802 - Qt override
        """讓摘要不把外層桌面頁面撐高；窄版仍可由 layout 依文字換行擴展。"""

        hint = super().minimumSizeHint()
        return QSize(hint.width(), min(hint.height(), 128))

    def set_summary(
        self,
        *,
        conclusion: str,
        reasons: Iterable[str] = (),
        next_step: str,
        evidence: str = "",
        change: str = "",
        risk: str = "",
        sufficiency: str = "",
        reasons_title: str = "判讀依據／未知",
    ) -> None:
        """更新摘要文字；重點固定最多呈現兩項，避免首屏過度擁擠。"""

        clean_reasons = [str(item).strip() for item in reasons if str(item).strip()]
        clean_reasons = clean_reasons[:2]
        if not clean_reasons:
            clean_reasons = ["目前沒有足夠資料判讀。"]
        self.conclusion_label.setText(f"結論：{str(conclusion).strip() or '未知'}")
        optional = (
            (self.evidence_label, "主要證據／資料日：", evidence),
            (self.change_label, "較前變化：", change),
            (self.risk_label, "主要風險／反證：", risk),
            (self.sufficiency_label, "資料是否足夠：", sufficiency),
        )
        for label, prefix, value in optional:
            clean_value = str(value).strip()
            label.setVisible(bool(clean_value))
            label.setText(f"{prefix}{clean_value}" if clean_value else "")
        self.reasons_label.setText(
            f"{reasons_title}：" + "；".join(clean_reasons)
        )
        self.next_step_label.setText(
            f"下一步：{str(next_step).strip() or '確認資料日期與缺件後再深入研究。'}"
        )
