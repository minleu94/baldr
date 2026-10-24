"""Research Lab 的分析師診斷呈現元件。"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
from typing import Any, Mapping

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QPainter
from PySide6.QtWidgets import (
    QGridLayout,
    QGroupBox,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QStyledItemDelegate,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from app_module.backtest_analyst_diagnostics import AnalystDiagnosticsDTO
from ui_qt.theme import MIDNIGHT_ANALYST


def _display(value: object, suffix: str = "") -> str:
    if value is None or value == "":
        return "未知"
    return f"{value}{suffix}"


def _format_sharpe(value: object) -> tuple[str, str]:
    """只在呈現層將 Sharpe 約至小數二位，並保留原始文字供核對。"""

    original = "未提供" if value is None else str(value)
    if value is None or isinstance(value, bool):
        return "未知", original
    try:
        number = value if isinstance(value, Decimal) else Decimal(original)
    except (InvalidOperation, TypeError, ValueError):
        return "未知", original
    if not number.is_finite():
        return "未知", original

    try:
        with localcontext() as context:
            context.prec = max(
                context.prec,
                len(number.as_tuple().digits) + max(number.adjusted(), 0) + 4,
            )
            rounded = number.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except InvalidOperation:
        return "未知", original

    if number == 0:
        return "0.00", original
    if abs(number) < Decimal("0.01"):
        scientific = format(number, ".2E")
        display = scientific if Decimal(scientific) == number else f"約{scientific}"
        return display, original
    display = format(rounded, ".2f")
    if rounded != number:
        display = f"約 {display}"
    return display, original


class _MonthlyHeatmapDelegate(QStyledItemDelegate):
    """在全站 QSS 下仍繪出月格原 BackgroundRole；選列保留標準高亮。"""

    def paint(self, painter: QPainter, option, index) -> None:
        super().paint(painter, option, index)
        if option.state & QStyle.StateFlag.State_Selected:
            return
        brush = index.data(Qt.ItemDataRole.BackgroundRole)
        if not isinstance(brush, QBrush) or brush.style() == Qt.BrushStyle.NoBrush:
            return
        painter.save()
        painter.setClipRect(option.rect)
        painter.fillRect(option.rect.adjusted(1, 1, -1, -1), brush)
        painter.setPen(QColor(MIDNIGHT_ANALYST.text_primary))
        painter.drawText(
            option.rect.adjusted(8, 0, -8, 0),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            str(index.data(Qt.ItemDataRole.DisplayRole) or ""),
        )
        painter.restore()


class AnalystDiagnosticsWidget(QWidget):
    """把已計算的診斷 DTO 以分析師可讀的表格呈現。"""

    _MONTH_LABELS = ("年", "1月", "2月", "3月", "4月", "5月", "6月", "7月", "8月", "9月", "10月", "11月", "12月")
    _MAX_MONTHLY_DISPLAY_MONTHS = 1200

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("analystDiagnosticsWidget")
        self.setAccessibleName("分析師診斷")
        self._setup_ui()
        self.clear()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(8)

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        self.status_label.setAccessibleName("分析診斷狀態")
        self.status_label.setToolTip("診斷只讀取目前回測或已保存 run 的欄位；未知不代表零")
        layout.addWidget(self.status_label)

        kpi_group = QGroupBox("分析師 KPI（數值定義）")
        kpi_group.setAccessibleName("分析師 KPI")
        kpi_layout = QGridLayout(kpi_group)
        self._kpi_labels: dict[str, QLabel] = {}
        kpis = (
            ("average_exposure_bp", "平均曝險", "position_value / equity，bp"),
            ("peak_exposure_bp", "峰值曝險", "position_value / equity，bp"),
            ("average_cash_utilization_bp", "平均現金使用率", "(equity - cash) / equity，bp"),
            ("turnover_bp", "Turnover", "成交金額總和 / 平均權益，bp"),
            ("fee_bp", "Fee／稅成本", "初始資金分母，bp"),
            ("slippage_bp", "滑價成本", "初始資金分母，bp"),
            ("total_bp", "交易成本合計", "Fee／稅 + 滑價，bp"),
        )
        for index, (key, title, tooltip) in enumerate(kpis):
            row, column = divmod(index, 3)
            label = QLabel("未知")
            label.setMinimumWidth(145)
            label.setAccessibleName(title)
            label.setToolTip(tooltip)
            label.setStyleSheet(
                f"padding: 6px; color: {MIDNIGHT_ANALYST.text_primary}; "
                f"background: {MIDNIGHT_ANALYST.surface_2}; "
                f"border: 1px solid {MIDNIGHT_ANALYST.border}; "
                f"border-radius: {MIDNIGHT_ANALYST.radius_badge}px;"
            )
            cell = QVBoxLayout()
            cell.addWidget(QLabel(title))
            cell.addWidget(label)
            kpi_layout.addLayout(cell, row, column)
            self._kpi_labels[key] = label
        layout.addWidget(kpi_group)

        rolling_group = QGroupBox("Trailing 報酬與年化波動")
        rolling_layout = QVBoxLayout(rolling_group)
        self.rolling_table = self._create_table(
            ("Window", "Return", "Annualized volatility", "Observations", "狀態／原因"),
            "Trailing 20／60 交易日只使用決策期內最後 window+1 筆 equity；不含未來資料。",
        )
        rolling_layout.addWidget(self.rolling_table)
        layout.addWidget(rolling_group)

        monthly_group = QGroupBox("月度報酬矩陣（年 × 月）")
        monthly_layout = QVBoxLayout(monthly_group)
        self.monthly_heatmap_legend = QLabel(
            "色階：正報酬紅、負報酬綠、真零中性；色深只相對本次 run 有效月份的最大絕對報酬，"
            "不可跨 run 比較，也不代表未來或 OOS。未知不著色，bp 原值保留。"
        )
        self.monthly_heatmap_legend.setObjectName("monthlyReturnHeatmapLegend")
        self.monthly_heatmap_legend.setAccessibleName("月度報酬色階與限制")
        self.monthly_heatmap_legend.setWordWrap(True)
        monthly_layout.addWidget(self.monthly_heatmap_legend)
        self.monthly_table = self._create_table(
            self._MONTH_LABELS,
            "每格直接顯示原始月報酬 bp。色深只相對本次 run 有效月份；"
            "未知表示該月沒有足夠的已保存權益觀測。",
        )
        self.monthly_table.setItemDelegate(_MonthlyHeatmapDelegate(self.monthly_table))
        self.monthly_table.setMinimumHeight(120)
        monthly_layout.addWidget(self.monthly_table)
        self.monthly_gap_note = QLabel()
        self.monthly_gap_note.setWordWrap(True)
        self.monthly_gap_note.setAccessibleName("月度矩陣省略年份說明")
        monthly_layout.addWidget(self.monthly_gap_note)
        layout.addWidget(monthly_group)

        benchmark_group = QGroupBox("原報告基準比較")
        benchmark_layout = QVBoxLayout(benchmark_group)
        self.benchmark_table = self._create_table(("指標", "策略", "比較基準", "差額／狀態"), "只使用報告中已保存的基準比較，不回抓市場資料。")
        benchmark_layout.addWidget(self.benchmark_table)
        layout.addWidget(benchmark_group)

        definition_group = QGroupBox("定義與限制")
        definition_layout = QVBoxLayout(definition_group)
        self.definition_text = QTextEdit()
        self.definition_text.setReadOnly(True)
        self.definition_text.setAccessibleName("分析診斷定義與限制")
        self.definition_text.setMinimumHeight(150)
        self.definition_text.setMaximumHeight(260)
        definition_layout.addWidget(self.definition_text)
        layout.addWidget(definition_group)
        layout.addStretch()

    @staticmethod
    def _create_table(headers: tuple[str, ...], tooltip: str) -> QTableWidget:
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(list(headers))
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setAlternatingRowColors(True)
        table.setAccessibleName("分析診斷資料表")
        table.setToolTip(tooltip)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setStretchLastSection(True)
        table.verticalHeader().setVisible(False)
        table.setStyleSheet(
            f"QTableWidget {{ color: {MIDNIGHT_ANALYST.text_primary}; background: {MIDNIGHT_ANALYST.surface_1}; "
            f"gridline-color: {MIDNIGHT_ANALYST.border}; }}"
        )
        return table

    @staticmethod
    def _set_item(table: QTableWidget, row: int, column: int, text: object) -> None:
        table.setItem(row, column, QTableWidgetItem(str(text)))

    @staticmethod
    def _set_sharpe_item(
        table: QTableWidget,
        row: int,
        column: int,
        value: object,
        *,
        missing_reason: object = None,
    ) -> None:
        display, original = _format_sharpe(value)
        source_description = f"原始值：{original}"
        if value is None and missing_reason is not None and str(missing_reason).strip():
            display = str(missing_reason)
            source_description += f"；原因：{display}"
        item = QTableWidgetItem(display)
        item.setToolTip(source_description)
        item.setData(
            Qt.ItemDataRole.AccessibleDescriptionRole,
            source_description,
        )
        table.setItem(row, column, item)

    def clear(self) -> None:
        self.set_diagnostics(AnalystDiagnosticsDTO.unknown("尚未完成回測；沒有可用診斷資料"))

    def set_diagnostics(self, dto: AnalystDiagnosticsDTO) -> None:
        if dto.status == "available":
            self.status_label.setText("分析診斷：可用。所有成本、rolling 與 benchmark 欄位都標示其資料來源與觀測數。")
            self.status_label.setStyleSheet(
                f"padding: 7px; color: {MIDNIGHT_ANALYST.text_primary}; background: {MIDNIGHT_ANALYST.surface_2}; "
                f"border-left: 4px solid {MIDNIGHT_ANALYST.success};"
            )
        else:
            self.status_label.setText(f"分析診斷：未知。{dto.reason or '缺少必要欄位，沒有估算。'}")
            self.status_label.setStyleSheet(
                f"padding: 7px; color: {MIDNIGHT_ANALYST.text_primary}; background: {MIDNIGHT_ANALYST.surface_2}; "
                f"border-left: 4px solid {MIDNIGHT_ANALYST.warning};"
            )

        kpis = dto.kpis
        for key, label in self._kpi_labels.items():
            value: object = kpis.get(key)
            if key.endswith("_bp") or key in {"fee_bp", "slippage_bp", "total_bp"}:
                label.setText(_display(value, " bp") if value is not None else "未知")
            else:
                label.setText(_display(value))

        costs = kpis.get("transaction_costs")
        if isinstance(costs, Mapping):
            for key, label_key in (("fee_bp", "fee_bp"), ("slippage_bp", "slippage_bp"), ("total_bp", "total_bp")):
                self._kpi_labels[label_key].setText(_display(costs.get(key), " bp"))

        self.rolling_table.setRowCount(0)
        for row_data in dto.rolling:
            row = self.rolling_table.rowCount()
            self.rolling_table.insertRow(row)
            self._set_item(self.rolling_table, row, 0, f"Trailing {row_data.get('window', '?')}")
            self._set_item(self.rolling_table, row, 1, _display(row_data.get("return_bp"), " bp"))
            self._set_item(self.rolling_table, row, 2, _display(row_data.get("annualized_vol_bp"), " bp"))
            self._set_item(self.rolling_table, row, 3, row_data.get("observation_count", "未知"))
            self._set_item(self.rolling_table, row, 4, row_data.get("reason") or row_data.get("status", "未知"))

        self.monthly_table.setRowCount(0)
        by_year: dict[int, dict[int, object]] = {}
        monthly_by_period: dict[tuple[int, int], Mapping[str, Any]] = {}
        for item in dto.monthly:
            year = item.get("year")
            month = item.get("month")
            if type(year) is int and type(month) is int and 1 <= month <= 12:
                by_year.setdefault(year, {})[month] = item.get("return_text", "未知")
                monthly_by_period[(year, month)] = item
        valid_monthly_bp = [
            item.get("return_bp")
            for item in monthly_by_period.values()
            if dto.status == "available"
            and item.get("status") == "available"
            and type(item.get("return_bp")) is int
        ]
        scale_max_abs_bp = max((abs(value) for value in valid_monthly_bp), default=0)
        observed_periods = {
            year * 12 + month - 1
            for year, months in by_year.items()
            for month in months
        }
        first_period = min(observed_periods) if observed_periods else None
        last_period = max(observed_periods) if observed_periods else None
        fill_period_gaps = (
            first_period is not None
            and last_period is not None
            and last_period - first_period + 1 <= self._MAX_MONTHLY_DISPLAY_MONTHS
        )
        self.monthly_gap_note.setText(
            "期間跨度超過 100 年，矩陣僅列有觀測資料的年份；中間省略年份的月份仍屬未知。"
            if first_period is not None and not fill_period_gaps else ""
        )
        if first_period is None or last_period is None:
            years = ()
        elif fill_period_gaps:
            # 只在有限期間內補齊跨年缺列，避免異常 DTO 展開成大量空白列。
            years = range(first_period // 12, last_period // 12 + 1)
        else:
            years = sorted(by_year)
        for year in years:
            row = self.monthly_table.rowCount()
            self.monthly_table.insertRow(row)
            self._set_item(self.monthly_table, row, 0, year)
            for month in range(1, 13):
                period = year * 12 + month - 1
                in_observed_span = (
                    first_period is not None
                    and last_period is not None
                    and first_period <= period <= last_period
                )
                missing_value = "未知" if in_observed_span else "—"
                self._set_item(
                    self.monthly_table, row, month,
                    by_year.get(year, {}).get(month, missing_value),
                )
                monthly_item = monthly_by_period.get((year, month))
                if dto.status != "available" or monthly_item is None:
                    continue
                return_bp = monthly_item.get("return_bp")
                if monthly_item.get("status") != "available" or type(return_bp) is not int:
                    continue
                if return_bp == 0 or scale_max_abs_bp == 0:
                    color = MIDNIGHT_ANALYST.surface_3
                else:
                    # 以整數 bp 將本次有效值分為四級；僅供同次矩陣辨識相對強度。
                    strength = min(3, ((abs(return_bp) * 4) - 1) // scale_max_abs_bp)
                    palette = (
                        ("#4a1b22", "#63232a", "#7b2831", "#932a31")
                        if return_bp > 0
                        else ("#173e2e", "#1a5138", "#1d6643", "#207a4e")
                    )
                    color = palette[strength]
                cell = self.monthly_table.item(row, month)
                if cell is not None:
                    cell.setBackground(QColor(color))
                    cell.setForeground(QColor(MIDNIGHT_ANALYST.text_primary))

        self.benchmark_table.setRowCount(0)
        benchmark = dto.benchmark
        rows = (
            ("報酬率", benchmark.get("strategy_return_bp"), benchmark.get("benchmark_return_bp"), benchmark.get("excess_return_bp")),
            ("Sharpe", benchmark.get("strategy_sharpe"), benchmark.get("benchmark_sharpe"), benchmark.get("sharpe_delta")),
            ("最大回撤", benchmark.get("strategy_mdd_bp"), benchmark.get("benchmark_mdd_bp"), benchmark.get("mdd_delta_bp")),
        )
        for title, strategy, baseline, delta in rows:
            row = self.benchmark_table.rowCount()
            self.benchmark_table.insertRow(row)
            self._set_item(self.benchmark_table, row, 0, title)
            suffix = " bp" if title != "Sharpe" else ""
            if title == "Sharpe":
                self._set_sharpe_item(self.benchmark_table, row, 1, strategy)
                self._set_sharpe_item(self.benchmark_table, row, 2, baseline)
                self._set_sharpe_item(
                    self.benchmark_table,
                    row,
                    3,
                    delta,
                    missing_reason=benchmark.get("reason"),
                )
            else:
                self._set_item(self.benchmark_table, row, 1, _display(strategy, suffix))
                self._set_item(self.benchmark_table, row, 2, _display(baseline, suffix))
                self._set_item(self.benchmark_table, row, 3, _display(delta, suffix) if delta is not None else benchmark.get("reason", "未知"))

        self.definition_text.setPlainText("\n".join(dto.definitions) if dto.definitions else (dto.reason or "未知"))


__all__ = ["AnalystDiagnosticsWidget"]
