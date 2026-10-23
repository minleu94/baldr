"""以原始Decimal值呈現單一單位的研究橫條。"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, localcontext
from datetime import date
import re
from typing import Sequence

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFontMetricsF, QPainter, QPen
from PySide6.QtWidgets import (
    QBoxLayout,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ui_qt.theme import MIDNIGHT_ANALYST
from ui_qt.widgets.theme_widgets import CollapsibleSectionPanel


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
        directional: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._value = value if value is not None and value.is_finite() else None
        self._scale = scale if scale.is_finite() and scale > 0 else Decimal(0)
        self._directional = directional
        self.setMinimumSize(40, 24)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setAccessibleName("原值比例長條")
        self.setAccessibleDescription(
            "缺值" if self._value is None else f"原始數值：{format(self._value, 'f')}"
        )

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        area = QRectF(self.rect()).adjusted(5, 7, -5, -7)
        painter.setPen(QPen(QColor(MIDNIGHT_ANALYST.border), 1))
        painter.drawLine(int(area.left()), int(area.center().y()), int(area.right()), int(area.center().y()))
        negative = self._value is not None and self._value < 0
        signed = negative or getattr(self, "_signed", False)
        middle = area.center().x() if signed else area.left()
        painter.setPen(QPen(QColor(MIDNIGHT_ANALYST.text_muted), 1))
        painter.drawLine(int(middle), int(area.top()), int(middle), int(area.bottom()))
        if self._value is not None and self._scale > 0:
            with localcontext() as context:
                context.prec = 28
                ratio = min(self._value.copy_abs() / self._scale, Decimal(1))
                width = float(ratio) * area.width() / (2 if signed else 1)
            # 通用值保持中性；只有明確方向語意才使用市場方向色。
            color = QColor(
                MIDNIGHT_ANALYST.market_up if self._value > 0 else
                MIDNIGHT_ANALYST.market_down if self._value < 0 else
                MIDNIGHT_ANALYST.market_flat
            ) if self._directional else QColor(MIDNIGHT_ANALYST.accent)
            color.setAlpha(150)
            left = middle if self._value >= 0 else middle - width
            painter.fillRect(QRectF(left, area.top(), width, area.height()), color)
        painter.end()


class _PeriodColumnChart(QWidget):
    """以原期間位置繪製柱；月份缺口按日曆距離保留。"""

    def __init__(
        self,
        points: Sequence[ResearchMetricBar],
        periods: Sequence[str],
        unit: str,
        paired: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._points = tuple(points)
        self._periods = tuple(periods)
        self._unit = unit
        self._paired = paired
        self.setMinimumHeight(150)
        self.setAccessibleName("原值期間柱圖")
        self._period_axis = paired or (
            len(self._periods) == len(self._points)
            and all(self._parse_period(p) is not None for p in self._periods)
        )
        self.setToolTip(
            "比較類別並列原始值。" if paired else
            "柱位依 YYYY-MM 月份間隔排列；缺少月份不補值。" if self._period_axis else
            "部分期間不符合 YYYY-MM；按原標籤作類別排列，不推定月份連續性。"
        )

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        area = QRectF(self.rect()).adjusted(8, 30, -8, -34)
        if not self._points or area.width() <= 0:
            painter.end()
            return
        values = [p.value for p in self._points if p.value is not None and p.value.is_finite()]
        if not values:
            painter.end()
            return
        signed = any(v < 0 for v in values)
        scale = max((abs(v) for v in values), default=Decimal(1)) or Decimal(1)
        labels = [self._periods[i] if i < len(self._periods) else point.label
                  for i, point in enumerate(self._points)]
        value_labels = [
            "缺值" if point.value is None or not point.value.is_finite()
            else f"{format(point.value, 'f')} {self._unit}".rstrip()
            for point in self._points
        ]
        edge_margin, plot_width = self._edge_label_layout(area.width(), (*labels, *value_labels))
        xs = [area.left() + edge_margin + value for value in self._x_positions(plot_width)]
        zero_y = area.center().y() if signed else area.bottom()
        painter.setPen(QPen(QColor(MIDNIGHT_ANALYST.text_muted), 1))
        painter.drawLine(int(area.left()), int(zero_y), int(area.right()), int(zero_y))
        step = plot_width / max(1, len(self._points))
        width = max(4, min(34, step * .58))
        max_bar_height = max(0.0, area.height() - 28) if not signed else max(0.0, area.height() / 2 - 28)
        for i, (point, x) in enumerate(zip(self._points, xs)):
            value = point.value
            value_text = value_labels[i]
            self.setAccessibleDescription(f"{point.label}：{value_text}")
            if value is not None and value.is_finite():
                with localcontext() as context:
                    context.prec = 28
                    height = float(abs(value) / scale) * max_bar_height
                color = QColor(MIDNIGHT_ANALYST.accent)
                painter.fillRect(QRectF(x - width / 2, zero_y - height if value >= 0 else zero_y,
                                        width, height), color)
                # 顯示精確原值，paired_column 不必展開明細就能比較兩根柱。
                painter.setPen(QColor(MIDNIGHT_ANALYST.text_primary))
                value_rect = self._centered_label_rect(value_text, x, zero_y - height - 22)
                if value < 0:
                    value_rect.moveTop(zero_y + height + 2)
                painter.drawText(
                    value_rect,
                    Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                    value_text,
                )
                self.setToolTip(f"{point.label}｜原值 {value_text}")
            label = labels[i]
            painter.setPen(QColor(MIDNIGHT_ANALYST.text_secondary))
            painter.drawText(self._centered_label_rect(label, x, area.bottom() + 4),
                             Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, label)
        painter.end()

    def _edge_label_layout(self, width: float, labels: Sequence[str]) -> tuple[float, float]:
        """保留完整首尾標籤寬度，期間位置仍映射到同一日曆比例。"""
        metrics = QFontMetricsF(self.font())
        half_label = max((metrics.horizontalAdvance(label) / 2 for label in labels), default=0.0)
        margin = min(half_label + 6.0, max(0.0, (width - 8.0) / 2))
        return margin, max(1.0, width - 2 * margin)

    def _centered_label_rect(self, text: str, x: float, y: float) -> QRectF:
        width = max(1.0, QFontMetricsF(self.font()).horizontalAdvance(text) + 2.0)
        return QRectF(x - width / 2, y, width, 22.0)

    def _x_positions(self, width: float) -> tuple[float, ...]:
        if self._paired:
            gap = min(100.0, max(60.0, width * .2))
            return tuple(
                width / 2 + (i - (len(self._points) - 1) / 2) * gap
                for i in range(len(self._points))
            )
        dates = tuple(self._parse_period(period) for period in self._periods)
        valid_dates = tuple(item for item in dates if item is not None)
        if self._period_axis and len(valid_dates) == len(self._points) and len(set(valid_dates)) > 1:
            first, last = min(valid_dates), max(valid_dates)
            span = (last - first).days or 1
            return tuple((item - first).days / span * width for item in valid_dates)
        step = width / max(1, len(self._points))
        return tuple(step * (i + .5) for i in range(len(self._points)))

    @staticmethod
    def _parse_period(period: str):
        try:
            if not re.fullmatch(r"\d{4}-\d{2}", period):
                return None
            year, month = period.split("-")
            return date(int(year), int(month), 1)
        except (ValueError, TypeError):
            return None


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
        *,
        orientation: str = "bar",
        directional: bool = False,
        periods: Sequence[str] | None = None,
        detail_note: str = "",
    ) -> None:
        super().__init__(parent)
        self._points = tuple(points)
        self.title = title
        self.unit = unit
        self.note = note
        self.detail_note = detail_note
        self.orientation = orientation if orientation in {"bar", "column", "paired_column"} else "bar"
        self.directional = directional
        self.periods = tuple(periods or (point.label for point in self._points))
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

        content = QWidget()
        content.setObjectName("researchMetricChartContent")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(2, 2, 2, 2)
        content_layout.setSpacing(5)
        root.addWidget(content)

        finite_values = tuple(
            point.value
            for point in self._points
            if point.value is not None and point.value.is_finite()
        )
        self._scale = max((value.copy_abs() for value in finite_values), default=Decimal(0))
        self._signed = any(value < 0 for value in finite_values)
        self._row_widgets: list[QWidget] = []
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
            if self.orientation in {"column", "paired_column"} and len(self._points) > 1:
                plot = _PeriodColumnChart(
                    self._points, self.periods, unit,
                    paired=self.orientation == "paired_column", parent=content,
                )
                plot.setObjectName("researchMetricChartPlot")
                content_layout.addWidget(plot)
                if self.orientation == "paired_column":
                    legend = QLabel(
                        "　｜　".join(
                            f"{point.label}：{self._format_value(point.value if point.value is not None and point.value.is_finite() else None)}"
                            for point in self._points
                        )
                    )
                    legend.setTextFormat(Qt.TextFormat.PlainText)
                    legend.setObjectName("researchMetricChartPairedValues")
                    legend.setWordWrap(True)
                    legend.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                    legend.setAccessibleName("比較柱原始值")
                    legend.setAccessibleDescription(legend.text())
                    legend.setStyleSheet(f"color: {MIDNIGHT_ANALYST.text_primary};")
                    content_layout.addWidget(legend)
            elif self.orientation in {"column", "paired_column"}:
                # 單一期間只呈現原值卡，不畫單柱趨勢圖，也不把原值藏在明細。
                point = self._points[0]
                period = self.periods[0] if self.periods else point.label
                value = point.value if point.value is not None and point.value.is_finite() else None
                card = QLabel(
                    f"{point.label or '未命名項目'}　{self._format_value(value)}\n"
                    f"期間：{period}　｜　單一觀測，不能判定趨勢"
                )
                card.setTextFormat(Qt.TextFormat.PlainText)
                card.setObjectName("researchMetricChartSingleColumnValue")
                card.setWordWrap(True)
                card.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                card.setAccessibleName(f"{point.label or '未命名項目'}單一期間原值")
                card.setAccessibleDescription(card.text())
                card.setStyleSheet(
                    f"color: {MIDNIGHT_ANALYST.text_primary}; font-weight: 600;"
                )
                content_layout.addWidget(card)
            if self.orientation == "bar":
                for point in self._points:
                    row = self._build_row(point)
                    self._row_widgets.append(row)
                    content_layout.addWidget(row)
            self.details_panel = self._build_details_panel()
            content_layout.addWidget(self.details_panel)
        content_layout.addStretch(1)

    @property
    def points(self) -> tuple[ResearchMetricBar, ...]:
        """傳回建立圖表時的唯讀點集合。"""

        return self._points

    def _build_row(self, point: ResearchMetricBar) -> QWidget:
        row = _ResponsiveResearchMetricRow()
        row.setObjectName("researchMetricChartRow")
        row.setAccessibleName(point.label or "未命名項目")
        row.setAccessibleDescription(point.label or "未命名項目")
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
        layout.addWidget(text_column, 1)

        value = point.value if point.value is not None and point.value.is_finite() else None
        value_bar = QWidget()
        value_bar.setObjectName("researchMetricChartValueBar")
        value_bar_layout = QHBoxLayout(value_bar)
        value_bar_layout.setContentsMargins(0, 0, 0, 0)
        value_bar_layout.setSpacing(8)
        if len(self._points) > 1:
            bar = _ZeroCenteredBar(value, self._scale, directional=self.directional)
            bar._signed = self._signed
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

    def _build_details_panel(self) -> CollapsibleSectionPanel:
        panel = CollapsibleSectionPanel("原值與來源明細（選取展開）", collapsed=True)
        panel.setObjectName("researchMetricChartDetails")
        panel.layout.setContentsMargins(4, 2, 4, 2)
        panel.layout.setSpacing(2)
        panel.title_label.setStyleSheet(
            f"color: {MIDNIGHT_ANALYST.text_secondary}; font-size: 12px; "
            "font-weight: 600; padding: 0; border: none; background: transparent;"
        )
        if self.detail_note:
            note = QLabel(self.detail_note)
            note.setTextFormat(Qt.TextFormat.PlainText)
            note.setObjectName("researchMetricChartSourceDetail")
            note.setWordWrap(True)
            note.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            note.setAccessibleName("來源與原始說明")
            note.setAccessibleDescription(self.detail_note)
            note.setStyleSheet(f"color: {MIDNIGHT_ANALYST.text_secondary};")
            panel.content_layout.addWidget(note)
        for point in self._points:
            value = point.value if point.value is not None and point.value.is_finite() else None
            label = QLabel(
                f"{point.label or '未命名項目'}｜原值 {self._format_value(value)}"
                + (f"｜{point.detail}" if point.detail else "｜來源明細未提供")
            )
            label.setTextFormat(Qt.TextFormat.PlainText)
            label.setObjectName("researchMetricChartExactDetail")
            label.setWordWrap(True)
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            label.setAccessibleName(f"{point.label or '未命名項目'}原值與來源明細")
            label.setAccessibleDescription(
                f"原值 {self._format_value(value)}；{point.detail or '來源明細未提供'}"
            )
            label.setStyleSheet(f"color: {MIDNIGHT_ANALYST.text_secondary};")
            panel.content_layout.addWidget(label)
        return panel

    def _format_value(self, value: Decimal | None) -> str:
        if value is None:
            return "缺值"
        rendered = format(value, "f")
        return f"{rendered} {self.unit}".rstrip()
