"""以原始Decimal值呈現單一單位的研究橫條。"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, localcontext
from typing import Sequence

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame,
    QBoxLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ui_qt.theme import MIDNIGHT_ANALYST


@dataclass(frozen=True)
class ResearchMetricBar:
    """一列原始研究觀察值；None代表缺值，不代表零。"""

    label: str
    value: Decimal | None
    detail: str = ""


class _ZeroCenteredBar(QWidget):
    def __init__(
        self,
        value: Decimal | None,
        scale: Decimal,
        *,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._value = value if value is not None and value.is_finite() else None
        self._scale = scale if scale.is_finite() and scale > 0 else Decimal(0)
        self.setMinimumSize(40, 24)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setAccessibleName("以零為中心的數值長條")
        self.setAccessibleDescription(
            "缺值" if self._value is None else f"原始數值：{format(self._value, 'f')}"
        )

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        area = QRectF(self.rect()).adjusted(5, 7, -5, -7)
        middle = area.center().x()
        painter.setPen(QPen(QColor(MIDNIGHT_ANALYST.border), 1))
        painter.drawLine(int(area.left()), int(area.center().y()), int(area.right()), int(area.center().y()))
        painter.setPen(QPen(QColor(MIDNIGHT_ANALYST.text_muted), 1))
        painter.drawLine(int(middle), int(area.top()), int(middle), int(area.bottom()))
        if self._value is not None and self._scale > 0:
            with localcontext() as context:
                context.prec = 28
                ratio = min(self._value.copy_abs() / self._scale, Decimal(1))
                width = float(ratio) * area.width() / 2
            # 原觀測的正負不是利多利空；用中性色避免把賣出量或餘額誤當訊號。
            color = QColor(MIDNIGHT_ANALYST.accent)
            color.setAlpha(150)
            left = middle if self._value >= 0 else middle - width
            painter.fillRect(QRectF(left, area.top(), width, area.height()), color)
        painter.end()


class _ResponsiveResearchMetricRow(QWidget):
    """依可用寬度切換橫排與直排，讓窄欄位仍看得到數值。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._layout = QBoxLayout(QBoxLayout.Direction.LeftToRight, self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(6)

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().resizeEvent(event)
        direction = (
            QBoxLayout.Direction.LeftToRight
            if event.size().width() >= 650
            else QBoxLayout.Direction.TopToBottom
        )
        if self._layout.direction() != direction:
            self._layout.setDirection(direction)


class ResearchMetricChart(QWidget):
    """響應式、單位一致橫條圖，保留原值及逐列可讀資訊。"""

    def __init__(
        self,
        title: str,
        unit: str,
        points: Sequence[ResearchMetricBar],
        note: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._points = tuple(points)
        self.title = title
        self.unit = unit
        self.note = note
        self.setObjectName("researchMetricChart")
        self.setAccessibleName(title)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        heading = QLabel(title)
        heading.setTextFormat(Qt.TextFormat.PlainText)
        heading.setObjectName("researchMetricChartTitle")
        heading.setAccessibleName(title)
        heading.setStyleSheet(
            f"color: {MIDNIGHT_ANALYST.text_primary}; font-weight: 700;"
        )
        root.addWidget(heading)

        if note:
            note_label = QLabel(note)
            note_label.setTextFormat(Qt.TextFormat.PlainText)
            note_label.setObjectName("researchMetricChartNote")
            note_label.setWordWrap(True)
            note_label.setAccessibleName("圖表說明")
            note_label.setAccessibleDescription(note)
            note_label.setStyleSheet(f"color: {MIDNIGHT_ANALYST.text_secondary};")
            root.addWidget(note_label)

        self._scroll = QScrollArea()
        self._scroll.setObjectName("researchMetricChartScrollArea")
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        root.addWidget(self._scroll)

        content = QWidget()
        content.setObjectName("researchMetricChartContent")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(2, 2, 8, 2)
        content_layout.setSpacing(5)
        self._scroll.setWidget(content)

        finite_values = tuple(
            point.value
            for point in self._points
            if point.value is not None and point.value.is_finite()
        )
        self._scale = max((value.copy_abs() for value in finite_values), default=Decimal(0))
        self._row_widgets: list[QWidget] = []
        visible_rows = min(6, max(1, len(self._points)))
        chart_height = visible_rows * 48 + 12
        self._scroll.setMinimumHeight(chart_height)
        self._scroll.setMaximumHeight(chart_height)

        if not finite_values:
            missing = QLabel("目前沒有可繪製的數值；缺值不視為零。")
            missing.setObjectName("researchMetricChartMissing")
            missing.setWordWrap(True)
            missing.setAccessibleName("圖表資料缺件")
            missing.setAccessibleDescription(missing.text())
            missing.setStyleSheet(f"color: {MIDNIGHT_ANALYST.text_muted};")
            content_layout.addWidget(missing)
            self._missing_label = missing
        else:
            self._missing_label = None
            for point in self._points:
                row = self._build_row(point)
                self._row_widgets.append(row)
                content_layout.addWidget(row)
        content_layout.addStretch(1)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if hasattr(self, "_scroll"):
            row_height = 48 if event.size().width() >= 650 else 84
            height = min(6, max(1, len(self._points))) * row_height + 12
            self._scroll.setFixedHeight(height)

    @property
    def points(self) -> tuple[ResearchMetricBar, ...]:
        """傳回建立圖表時的唯讀點集合。"""

        return self._points

    def _build_row(self, point: ResearchMetricBar) -> QWidget:
        row = _ResponsiveResearchMetricRow()
        row.setObjectName("researchMetricChartRow")
        row.setAccessibleName(point.label or "未命名項目")
        row.setAccessibleDescription(point.detail or point.label or "未提供列說明")
        row.setToolTip(point.detail)
        layout = row._layout

        text_column = QWidget()
        text_column.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        text_layout = QVBoxLayout(text_column)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(1)
        label = QLabel(point.label or "未命名項目")
        label.setTextFormat(Qt.TextFormat.PlainText)
        label.setObjectName("researchMetricChartRowLabel")
        label.setWordWrap(True)
        label.setAccessibleName(point.label or "未命名項目")
        label.setStyleSheet(f"color: {MIDNIGHT_ANALYST.text_primary};")
        text_layout.addWidget(label)
        if point.detail:
            detail = QLabel(point.detail)
            detail.setTextFormat(Qt.TextFormat.PlainText)
            detail.setObjectName("researchMetricChartRowDetail")
            detail.setWordWrap(True)
            detail.setAccessibleName("資料日期與來源明細")
            detail.setAccessibleDescription(point.detail)
            detail.setStyleSheet(f"color: {MIDNIGHT_ANALYST.text_secondary}; font-size: 12px;")
            text_layout.addWidget(detail)
        layout.addWidget(text_column, 1)

        value = point.value if point.value is not None and point.value.is_finite() else None
        value_bar = QWidget()
        value_bar.setObjectName("researchMetricChartValueBar")
        value_bar_layout = QHBoxLayout(value_bar)
        value_bar_layout.setContentsMargins(0, 0, 0, 0)
        value_bar_layout.setSpacing(8)
        if len(self._points) > 1:
            bar = _ZeroCenteredBar(value, self._scale)
            bar.setObjectName("researchMetricChartBar")
            value_bar_layout.addWidget(bar, 1)
        else:
            single_note = QLabel("單筆原觀測；不能判定趨勢")
            single_note.setWordWrap(True)
            value_bar_layout.addWidget(single_note, 1)

        value_text = self._format_value(value)
        value_label = QLabel(value_text)
        value_label.setTextFormat(Qt.TextFormat.PlainText)
        value_label.setObjectName("researchMetricChartValue")
        value_label.setMinimumWidth(90)
        value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        value_label.setAccessibleName(f"{point.label or '未命名項目'}數值")
        value_label.setAccessibleDescription(value_text)
        tone = MIDNIGHT_ANALYST.text_muted if value is None else MIDNIGHT_ANALYST.text_primary
        value_label.setStyleSheet(f"color: {tone}; font-weight: 600;")
        value_bar_layout.addWidget(value_label)
        layout.addWidget(value_bar, 2)
        return row

    def _format_value(self, value: Decimal | None) -> str:
        if value is None:
            return "缺值"
        rendered = format(value, "f")
        return f"{rendered} {self.unit}".rstrip()
