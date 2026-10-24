"""單股回測原結果圖卡；只投影既有結果，不計算績效或補齊缺值。"""

from collections.abc import Mapping
from decimal import Decimal, InvalidOperation, localcontext
from typing import Any

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QGridLayout, QGroupBox, QLabel, QVBoxLayout, QWidget, QSizePolicy, QToolTip

from ui_qt.theme import MIDNIGHT_ANALYST
from app_module.single_backtest_metrics_contract import (
    SINGLE_BACKTEST_METRICS_KEY, SINGLE_BACKTEST_METRIC_NAMES,
    decode_single_backtest_metrics_contract,
)


def _number(value: object) -> Decimal | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = Decimal(str(value))
    except (ValueError, InvalidOperation):
        return None
    return number if number.is_finite() else None


def _percent(value: object) -> str:
    number = _number(value)
    if number is None:
        return "未提供"
    with localcontext() as context:
        context.prec = max(28, len(number.as_tuple().digits) + 4)
        return f"{number * 100:,.2f} %"


class OriginalEquityPreview(QWidget):
    """只畫原權益列的最近120筆；不建立報酬、基準或回撤序列。"""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.points: tuple[tuple[str, Decimal | None], ...] = ()
        self.setFixedHeight(122)
        self.setMouseTracking(True)
        self.setAccessibleName("同筆原結果的權益曲線預覽")

    def set_points(self, points: tuple[tuple[str, Decimal | None], ...]) -> None:
        self.points = points
        self.update()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self.points:
            index = min(len(self.points) - 1, max(0, round((event.position().x() - 70) / max(1, self.width() - 82) * (len(self.points) - 1))))
            day, value = self.points[index]
            QToolTip.showText(event.globalPosition().toPoint(), f"原索引／日期 {day}\n原權益：{value if value is not None else '未提供'}", self)
        super().mouseMoveEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        area = QRectF(70, 8, max(1, self.width() - 82), 76)
        values = [value for _, value in self.points if value is not None]
        if not values:
            return
        low, high = min(values), max(values)
        painter.setPen(QColor(MIDNIGHT_ANALYST.text_muted))
        painter.drawText(0, 18, f"{high:,.0f}")
        painter.drawText(0, 84, f"{low:,.0f}")
        date_rect = self.rect().adjusted(70, 92, -12, -6)
        painter.drawText(date_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.points[0][0])
        painter.drawText(date_rect, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, self.points[-1][0])
        painter.setPen(QPen(QColor(MIDNIGHT_ANALYST.border), 1))
        painter.drawLine(area.bottomLeft(), area.bottomRight())
        path = QPainterPath()
        connected = False
        with localcontext() as context:
            context.prec = max(28, max(len(value.as_tuple().digits) for value in values) + 8)
            spread = high - low
            for index, (_, value) in enumerate(self.points):
                if value is None:
                    connected = False
                    continue
                fraction = float((value - low) / spread) if spread else 0.5
                point = QPointF(area.left() + area.width() * index / max(1, len(self.points) - 1), area.bottom() - fraction * area.height())
                if connected:
                    path.lineTo(point)
                else:
                    path.moveTo(point)
                connected = True
        painter.setPen(QPen(QColor(MIDNIGHT_ANALYST.accent), 2))
        painter.drawPath(path)


class BacktestOutcomeSummary(QWidget):
    """保留原比率單位與精確提示；費率只顯示原假設，不推算成本或淨報酬。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("backtestOutcomeSummary")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.context = QLabel()
        self.context.setWordWrap(True)
        self.context.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.context)
        self.grid = QGridLayout()
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(6)
        layout.addLayout(self.grid)
        self.cards: list[QGroupBox] = []
        self.values: dict[str, QLabel] = {}
        for key, title in (("return", "原總報酬"), ("drawdown", "原最大回撤"), ("trades", "完成進出場配對"), ("cost", "原成本假設")):
            card = QGroupBox(title, self)
            card.setMinimumWidth(0)
            card.setMinimumHeight(78)
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(8, 10, 8, 6)
            value = QLabel("未提供")
            value.setObjectName(f"backtestOutcome_{key}")
            value.setTextFormat(Qt.TextFormat.PlainText)
            value.setWordWrap(True)
            # 原績效與配對數突出；成本只是保存假設，維持次要層級。
            value_size, value_weight = (15, 600) if key == "cost" else (20, 700)
            value.setStyleSheet(
                f"color: {MIDNIGHT_ANALYST.text_primary}; "
                f"font-size: {value_size}px; font-weight: {value_weight};"
            )
            card_layout.addWidget(value)
            self.cards.append(card)
            self.grid.addWidget(card, 0, len(self.cards) - 1)
            self.values[key] = value
        self.curve_caption = QLabel()
        self.curve_caption.setWordWrap(True)
        self.curve_caption.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.curve_caption)
        self.curve = OriginalEquityPreview(self)
        layout.addWidget(self.curve)
        self.clear()

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().resizeEvent(event)
        columns = 4 if self.width() >= 850 else 2 if self.width() >= 440 else 1
        for card in self.cards:
            self.grid.removeWidget(card)
        for index, card in enumerate(self.cards):
            self.grid.addWidget(card, index // columns, index % columns)
        for column in range(4):
            self.grid.setColumnStretch(column, int(column < columns))

    def clear(self) -> None:
        self.context.clear()
        self.curve_caption.clear()
        self.curve.set_points(())
        self.curve.hide()
        for value in self.values.values():
            value.setText("未提供")
            value.setToolTip("")
        self.hide()

    def present(self, report: Any, params: Mapping[str, Any], source_label: str) -> None:
        details = report.get("details", {}) if isinstance(report, Mapping) else getattr(report, "details", {})
        details = details if isinstance(details, Mapping) else {}
        if report is None or details.get("error"):
            self.clear()
            return
        # 歷史事件只讀自己的保存欄位；不取目前可變的current_report或UI預設值。
        metrics = details if isinstance(report, Mapping) else report
        def original(field: str) -> Any:
            return metrics.get(field) if isinstance(metrics, Mapping) else getattr(metrics, field, None)
        stock = details.get("stock_code") or params.get("stock_code") or "未提供"
        manifest = details.get("data_manifest")
        decoded = None
        contract_declared = isinstance(manifest, Mapping) and SINGLE_BACKTEST_METRICS_KEY in manifest
        contract_status = "原摘要觀察，未核指標契約；僅研究用"
        if contract_declared:
            try:
                decoded = decode_single_backtest_metrics_contract(
                    manifest, {field: original(field) for field in SINGLE_BACKTEST_METRIC_NAMES},
                    run_type="single_backtest", universe=[stock],
                )
                contract_status = "原指標契約已核對；仍僅研究用"
            except (ValueError, TypeError, OverflowError):
                contract_status = "原指標契約不可核對；績效維持未知"
        for key, field in (("return", "total_return"), ("drawdown", "max_drawdown")):
            raw = decoded.get(field) if decoded is not None else None if contract_declared else original(field)
            self.values[key].setText(_percent(raw))
            self.values[key].setToolTip(f"原比率：{raw}" if _number(raw) is not None else "原結果未提供有效數值；不補零。")
        trades = decoded.get("completed_trades") if decoded is not None else None if contract_declared else original("total_trades")
        self.values["trades"].setText(str(trades) if type(trades) is int and trades >= 0 else "未提供")
        self.values["trades"].setToolTip("原完成進出場配對數；不等於成交筆數或期末持股。")
        cost = []
        for field, title in (("fee_bps", "手續費"), ("slippage_bps", "滑價")):
            raw = params.get(field, details.get(field))
            cost.append(f"{title} {raw if _number(raw) is not None else '未提供'} bps")
        self.values["cost"].setText("\n".join(cost))
        self.values["cost"].setToolTip("原保存的費率假設；不代表實際扣款合計，不另算成本或淨報酬。")
        start = details.get("start_date") or params.get("start_date") or "未提供"
        end = details.get("end_date") or params.get("end_date") or "未提供"
        run_id = details.get("run_id")
        self.context.setText(f"{source_label}｜股票 {stock}｜期間 {start}～{end}｜{contract_status}" + (f"｜run {run_id}" if run_id is not None else ""))
        self._present_curve(details.get("equity_curve"))
        self.show()

    def _present_curve(self, frame: Any) -> None:
        import pandas as pd
        self.curve.set_points(())
        self.curve.hide()
        self.curve_caption.setText("原件未附可繪製權益資料；不補零。")
        if not isinstance(frame, pd.DataFrame) or frame.empty or "equity" not in frame.columns:
            return
        tail = frame["equity"].tail(120)
        date_field = next((field for field in ("date", "日期") if field in frame.columns), None)
        dates = frame[date_field].tail(120) if date_field else tail.index
        points = tuple((str(day)[:10], _number(value)) for day, value in zip(dates, tail))
        if not any(value is not None for _, value in points):
            return
        self.curve.set_points(points)
        self.curve_caption.setText(f"同筆原權益預覽｜最近 {len(points)}／共 {len(frame)} 筆，依原列順序；缺值留斷點，游標可查原值。")
        self.curve.show()
