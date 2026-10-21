"""從既有研究時間軸結果投影首頁最近紀錄。"""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from app_module.research_timeline_dtos import ResearchTimelineEntry, ResearchTimelineReadResult
from app_module.stock_research_report_notes import StockResearchReportNote


_KIND_LABELS = {
    "manual": "手動筆記",
    "price": "價格研究",
    "report": "一般報告",
    "theme": "題材研究",
}
_MAX_VISIBLE_ENTRIES = 3
_MAX_PREVIEW_CHARS = 120


class RecentResearchWidget(QWidget):
    """以不可變時間軸結果顯示最多三筆有明確保存時間的研究。"""

    entryRequested = Signal(object)
    originalRequested = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("recentResearchWidget")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        title = QLabel("最近研究", self)
        title.setObjectName("recentResearchTitle")
        title.setProperty("role", "section-title")
        root.addWidget(title)

        self.status_label = QLabel("尚未讀取研究時間軸。", self)
        self.status_label.setObjectName("recentResearchStatus")
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)

        self.entries_layout = QVBoxLayout()
        self.entries_layout.setContentsMargins(0, 0, 0, 0)
        self.entries_layout.setSpacing(6)
        root.addLayout(self.entries_layout)

    def set_result(self, result: ResearchTimelineReadResult) -> None:
        """只呈現傳入結果；不自行讀取、排序或補算時間軸資料。"""

        self._clear_entries()
        if not isinstance(result, ResearchTimelineReadResult):
            self.set_unavailable("研究時間軸結果無效；請重新讀取後再查看。")
            return

        # Service 已依保存時間排序；此處只排除無法證明時間先後的紀錄。
        recent = tuple(
            entry for entry in result.entries
            if type(entry) is ResearchTimelineEntry and _has_aware_recorded_at(entry.recorded_at)
        )[:_MAX_VISIBLE_ENTRIES]
        for entry in recent:
            self.entries_layout.addWidget(self._entry_card(entry))

        status_parts: list[str] = []
        if recent:
            status_parts.append(f"顯示 {len(recent)} 筆；最多 3 筆。")
        else:
            status_parts.append("目前沒有保存時間明確的最近研究。")
        if result.limited:
            status_parts.append("時間軸已達 500 筆上限，列表不是完整歷史。")
        if result.warnings:
            status_parts.append("時間軸讀取有警告，列表可能不完整：" + "；".join(result.warnings))
        self.status_label.setText(" ".join(status_parts))

    def set_unavailable(
        self,
        message: str = "研究時間軸目前無法讀取；請重新整理後再查看。",
    ) -> None:
        """讀取失敗或取消時清除舊卡片，避免舊快照看似仍是最新。"""

        self._clear_entries()
        detail = " ".join(str(message).split())
        self.status_label.setText(detail or "研究時間軸目前無法讀取；請重新整理後再查看。")

    def _entry_card(self, entry: ResearchTimelineEntry) -> QFrame:
        card = QFrame(self)
        card.setObjectName("recentResearchEntry")
        card.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(3)

        top = QHBoxLayout()
        kind = _KIND_LABELS.get(entry.kind, entry.kind)
        stock = entry.stock_code or "未提供代號"
        heading = QLabel(f"{kind}｜{stock}", card)
        heading.setObjectName("recentResearchEntryHeading")
        heading.setWordWrap(True)
        top.addWidget(heading, 1)

        open_button = QPushButton("開啟研究紀錄與覆盤", card)
        open_button.setObjectName("recentResearchOpenEntry")
        open_button.setProperty("variant", "secondary")
        open_button.clicked.connect(lambda _checked=False, selected=entry: self.entryRequested.emit(selected))
        top.addWidget(open_button)
        if _has_report_source_identity(entry):
            original_button = QPushButton("回訪原報告", card)
            original_button.setObjectName("recentResearchOpenOriginalReport")
            original_button.setProperty("variant", "secondary")
            original_button.setAccessibleName("回訪此筆保存報告原版本")
            original_button.clicked.connect(
                lambda _checked=False, selected=entry: self.originalRequested.emit(selected)
            )
            top.addWidget(original_button)
        layout.addLayout(top)

        if entry.kind == "report":
            market_date = _saved_report_market_date(entry)
            metadata_text = (
                f"保存時間 {entry.recorded_at}｜原研究來源日 {entry.data_date or '原件未提供'}｜"
                f"行情日 {market_date or '原件未提供'}"
            )
        else:
            metadata_text = f"保存時間 {entry.recorded_at}｜資料日 {entry.data_date or '原件未提供'}"
        metadata = QLabel(metadata_text, card)
        metadata.setObjectName("recentResearchEntryMetadata")
        metadata.setWordWrap(True)
        layout.addWidget(metadata)

        original_label = QLabel(_preview(entry.text), card)
        original_label.setTextFormat(Qt.TextFormat.PlainText)
        original_label.setObjectName("recentResearchEntryOriginal")
        original_label.setWordWrap(True)
        original_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(original_label)

        missing: list[str] = []
        if not entry.data_date:
            missing.append("資料日")
        if not entry.source_identity:
            missing.append("來源身份")
        qualification_text = (
            "缺少" + "、".join(missing) + "；原件未提供這些欄位，請在研究紀錄中核對。"
            if missing else "來源資格與缺件請在研究紀錄中核對。"
        )
        qualification = QLabel(qualification_text, card)
        qualification.setObjectName("recentResearchEntryEvidenceHint")
        qualification.setWordWrap(True)
        qualification.setProperty("role", "muted")
        layout.addWidget(qualification)

        identity = entry.source_identity or "原件未提供來源身份"
        card.setToolTip(
            f"紀錄 ID：{entry.record_id or '未提供'}\n"
            f"來源身份：{identity}\n"
            f"前版：{entry.revision_of or '無明確前版'}"
        )
        return card

    def _clear_entries(self) -> None:
        while self.entries_layout.count():
            item = self.entries_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.deleteLater()


def _has_aware_recorded_at(value: str) -> bool:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError):
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def _has_report_source_identity(entry: ResearchTimelineEntry) -> bool:
    return (
        entry.kind == "report"
        and bool(str(entry.data_date or "").strip())
        and bool(str(entry.source_identity or "").strip())
    )


def _saved_report_market_date(entry: ResearchTimelineEntry) -> str:
    if type(entry.reference) is not StockResearchReportNote:
        return ""
    points = entry.reference.snapshot.report.price_points
    if not points:
        return ""
    return str(points[-1].data_date or "").strip()


def _preview(value: str) -> str:
    text = " ".join(str(value).split())
    if len(text) <= _MAX_PREVIEW_CHARS:
        return text or "原件未提供文字。"
    return text[: _MAX_PREVIEW_CHARS - 1].rstrip() + "…"


__all__ = ["RecentResearchWidget"]
