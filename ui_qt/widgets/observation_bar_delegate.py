"""原觀察值的表格長條；只將顯示幾何轉為浮點，不改寫數值。"""

from decimal import Decimal, InvalidOperation, localcontext

from PySide6.QtCore import QModelIndex, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPalette
from PySide6.QtWidgets import QStyledItemDelegate, QStyle, QStyleOptionViewItem

from ui_qt.theme import MIDNIGHT_ANALYST


OBSERVATION_VALUE_ROLE = int(Qt.ItemDataRole.UserRole) + 43
OBSERVATION_DIRECTIONAL_ROLE = int(Qt.ItemDataRole.UserRole) + 44


class ObservationBarDelegate(QStyledItemDelegate):
    """同欄當前列共用絕對值尺度；中線為零，精確文字及提示仍由原表提供。"""

    @staticmethod
    def numeric_value(index: QModelIndex) -> Decimal | None:
        raw = index.data(OBSERVATION_VALUE_ROLE)
        if not isinstance(raw, str):
            return None
        try:
            value = Decimal(raw)
        except InvalidOperation:
            return None
        return value if value.is_finite() else None

    @staticmethod
    def bar_color(value: Decimal, directional: bool) -> QColor:
        """通用指標保持中性；明確方向語意才套用台股方向色。"""
        if not directional:
            return QColor(MIDNIGHT_ANALYST.accent)
        token = (
            MIDNIGHT_ANALYST.market_up if value > 0 else
            MIDNIGHT_ANALYST.market_down if value < 0 else
            MIDNIGHT_ANALYST.market_flat
        )
        return QColor(token)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        styled = QStyleOptionViewItem(option)
        self.initStyleOption(styled, index)
        text = styled.text
        styled.text = ""
        widget = styled.widget
        if widget is None:
            super().paint(painter, option, index)
            return
        widget.style().drawControl(QStyle.ControlElement.CE_ItemViewItem, styled, painter, widget)
        painter.save()
        painter.setClipRect(option.rect)
        value = self.numeric_value(index)
        model = index.model()
        if value is not None and model is not None:
            values = tuple(self.numeric_value(model.index(row, index.column())) for row in range(model.rowCount()))
            scale = max((item.copy_abs() for item in values if item is not None), default=Decimal(0))
            signed = any(item is not None and item < 0 for item in values)
            area = QRectF(option.rect).adjusted(8, 5, -8, -5)
            middle = area.center().x() if signed else area.left()
            painter.setPen(QColor(MIDNIGHT_ANALYST.text_muted))
            painter.drawLine(int(middle), int(area.top()), int(middle), int(area.bottom()))
            if scale:
                with localcontext() as context:
                    context.prec = 28
                    width = float(value.copy_abs() / scale) * area.width() / (2 if signed else 1)
                directional = bool(index.data(OBSERVATION_DIRECTIONAL_ROLE))
                color = self.bar_color(value, directional)
                color.setAlpha(55)
                painter.fillRect(QRectF(middle if value >= 0 else middle - width, area.top(), width, area.height()), color)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        painter.setPen(option.palette.color(QPalette.ColorRole.HighlightedText if selected else QPalette.ColorRole.Text))
        painter.drawText(option.rect.adjusted(8, 0, -8, 0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, text)
        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        original = super().sizeHint(option, index)
        return QSize(max(220, original.width() + 16), max(32, original.height() + 8))
