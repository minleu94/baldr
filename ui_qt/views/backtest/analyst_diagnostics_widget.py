"""Research Lab 的分析師診斷呈現元件。"""

from __future__ import annotations

from typing import Any, Mapping

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QGridLayout,
    QGroupBox,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app_module.backtest_analyst_diagnostics import AnalystDiagnosticsDTO
from ui_qt.theme import MIDNIGHT_ANALYST


def _display(value: object, suffix: str = "") -> str:
    if value is None or value == "":
        return "未知"
    return f"{value}{suffix}"


class AnalystDiagnosticsWidget(QWidget):
    """把已計算的診斷 DTO 以分析師可讀的表格呈現。"""

    _MONTH_LABELS = ("年", "1月", "2月", "3月", "4月", "5月", "6月", "7月", "8月", "9月", "10月", "11月", "12月")

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
        self.monthly_table = self._create_table(self._MONTH_LABELS, "每格直接顯示 bp；未知表示該月沒有足夠的已保存權益觀測。")
        self.monthly_table.setMinimumHeight(120)
        monthly_layout.addWidget(self.monthly_table)
        layout.addWidget(monthly_group)

        benchmark_group = QGroupBox("Frozen benchmark attribution")
        benchmark_layout = QVBoxLayout(benchmark_group)
        self.benchmark_table = self._create_table(("指標", "策略", "Benchmark", "差額／狀態"), "只使用報告內既有 baseline comparison，不回抓市場資料。")
        benchmark_layout.addWidget(self.benchmark_table)
        layout.addWidget(benchmark_group)

        definition_group = QGroupBox("定義與限制")
        definition_layout = QVBoxLayout(definition_group)
        self.definition_text = QTextEdit()
        self.definition_text.setReadOnly(True)
        self.definition_text.setAccessibleName("分析診斷定義與限制")
        self.definition_text.setMaximumHeight(110)
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
        for item in dto.monthly:
            year = item.get("year")
            month = item.get("month")
            if isinstance(year, int) and isinstance(month, int):
                by_year.setdefault(year, {})[month] = item.get("return_text", "未知")
        for year in sorted(by_year):
            row = self.monthly_table.rowCount()
            self.monthly_table.insertRow(row)
            self._set_item(self.monthly_table, row, 0, year)
            for month in range(1, 13):
                self._set_item(self.monthly_table, row, month, by_year[year].get(month, "—"))

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
            self._set_item(self.benchmark_table, row, 1, _display(strategy, suffix))
            self._set_item(self.benchmark_table, row, 2, _display(baseline, suffix))
            self._set_item(self.benchmark_table, row, 3, _display(delta, suffix) if delta is not None else benchmark.get("reason", "未知"))

        self.definition_text.setPlainText("\n".join(dto.definitions) if dto.definitions else (dto.reason or "未知"))


__all__ = ["AnalystDiagnosticsWidget"]
