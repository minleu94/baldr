"""從名單已驗證快照呈現具名研究母體盤勢。"""

from __future__ import annotations

import json

from ui_qt.research_universe_presentation import research_universe_text

from typing import Callable

from PySide6.QtWidgets import (
    QDialog, QGroupBox, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QTableWidget, QTabWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from app_module.daily_market_cohort_projection import project_daily_market_cohort
from app_module.daily_market_snapshot_repository import VerifiedDailyMarketSnapshot
from ui_qt.original_ranking_presentation import (
    original_rank_cell,
    original_rank_row_tooltip,
    ranking_audit_tooltip,
    ranking_matches_snapshot,
    ranking_rows_by_code,
    ranking_summary_text,
)
from ui_qt.views.daily_market_research_view import DailyMarketResearchView
from ui_qt.widgets.table_style import apply_financial_table_style
from ui_qt.widgets.info_button import InfoButton


class DailyMarketCohortView(QWidget):
    """盤勢與名單共享同一個讀取流程；本頁不讀資料庫或重算方法。"""

    def __init__(
        self,
        source_view: DailyMarketResearchView,
        open_list: Callable[[], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.source_view = source_view
        self.projection: object | None = None
        self._snapshot: object | None = None
        self.original_ranking: object | None = None
        self._capability_report: object | None = None
        self._capability_dialog: QDialog | None = None
        self._capability_text: QPlainTextEdit | None = None
        self._capability_table: QTableWidget | None = None
        layout = QVBoxLayout(self)
        title_layout = QHBoxLayout()
        title = QLabel("研究母體盤勢")
        title_layout.addWidget(title)
        title_layout.addStretch()
        title_layout.addWidget(InfoButton("daily_market_cohort", self))
        layout.addLayout(title_layout)
        self.scope_label = QLabel(
            "最多 16 檔具名研究母體；此頁不是全市場廣度或原強弱排名。"
        )
        self.scope_label.setWordWrap(True)
        layout.addWidget(self.scope_label)
        self.identity_label = QLabel("尚未讀取已發布研究快照。")
        self.identity_label.setWordWrap(True)
        layout.addWidget(self.identity_label)
        group = QGroupBox("同一快照的既有條件觀察")
        group_layout = QVBoxLayout(group)
        self.methods_table = QTableWidget(0, 4)
        self.methods_table.setHorizontalHeaderLabels(
            ["固定方法", "符合", "不符合", "未知"]
        )
        self.methods_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        apply_financial_table_style(self.methods_table)
        group_layout.addWidget(self.methods_table)
        layout.addWidget(group)
        self.members_table = QTableWidget(0, 6)
        self.members_table.setHorizontalHeaderLabels(
            ["母體股票", "行情資料日", "收盤價", "MA20", "MA60"]
        )
        self.members_table.setHorizontalHeaderItem(5, QTableWidgetItem("原始名次"))
        self.members_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        apply_financial_table_style(self.members_table)
        layout.addWidget(self.members_table)
        self.ranking_label = QLabel(
            "原排名未提供：發布快照未含原強弱排名。名單可依既有指標值排序；"
            "排序不是投資分數，不能推定強弱或勝率。"
        )
        self.ranking_label.setWordWrap(True)
        layout.addWidget(self.ranking_label)
        controls = QHBoxLayout()
        self.capability_button = QPushButton("查看已開能力與來源")
        self.capability_button.setEnabled(False)
        self.capability_button.clicked.connect(self._show_capability_audit)
        controls.addWidget(self.capability_button)
        self.reload_button = QPushButton("重讀同一研究來源")
        self.reload_button.clicked.connect(source_view.reload_published_snapshot)
        controls.addWidget(self.reload_button)
        self.open_list_button = QPushButton("開啟同來源研究名單／明確更新")
        self.open_list_button.clicked.connect(open_list)
        controls.addWidget(self.open_list_button)
        layout.addLayout(controls)
        self.status_label = QLabel("唯讀；更新必須在研究名單明確執行。")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        source_view.snapshotAccepted.connect(self.accept_snapshot)
        source_view.snapshotCleared.connect(self.clear_snapshot)
        source_view.originalRankingAccepted.connect(self.accept_original_ranking)
        source_view.originalRankingCleared.connect(self.clear_original_ranking)

    def on_first_open(self) -> None:
        self.source_view.on_first_open()

    def accept_snapshot(self, snapshot: object) -> None:
        if not isinstance(snapshot, VerifiedDailyMarketSnapshot):
            self.clear_snapshot()
            return
        self._snapshot = snapshot
        self.original_ranking = None
        service = self.source_view.service
        filter_rows = getattr(service, "filter_rows", None)
        if not callable(filter_rows):
            self.clear_snapshot()
            return
        try:
            rows = filter_rows(snapshot, ("close_above_ma20", "close_above_ma60"), "AND")
            projection = project_daily_market_cohort(
                snapshot, rows,
                expected_snapshot_root=getattr(service, "snapshot_root", None),
            )
            from app_module.daily_market_research_capabilities import (
                project_daily_market_research_capabilities,
            )
            capability_report = project_daily_market_research_capabilities(
                snapshot, rows,
                expected_snapshot_root=getattr(service, "snapshot_root", None),
            )
        except Exception as exc:
            self.clear_snapshot()
            self.status_label.setText(f"研究母體未知；共用投影拒絕：{type(exc).__name__}: {exc}")
            return
        self.projection = projection
        self._capability_report = capability_report
        self.capability_button.setEnabled(True)
        self._refresh_capability_audit()
        self.scope_label.setText(
            f"母體 {projection.cohort_id}：{len(projection.declared_stock_codes)} 檔"
            f"（{', '.join(projection.declared_stock_codes)}）；非全市場，篩選不改變此分母。"
            f"\n已發布 {projection.published_count} 檔；"
            f"缺件：{', '.join(projection.missing_stock_codes) or '無'}；{projection.completeness}。"
        )
        self.identity_label.setText(
            f"決策日 {projection.decision_date}｜來源 {projection.source_snapshot_id}\n"
            f"manifest {projection.source_snapshot_hash}\n"
            f"方法契約 {projection.method_contracts_sha256}"
        )
        universe_text, universe_detail = research_universe_text(
            projection.research_universe, published_count=projection.published_count,
            declared_count=len(projection.declared_stock_codes),
            original_rank_available=self.original_ranking is not None,
        )
        self.scope_label.setText(self.scope_label.text() + "\n" + universe_text)
        self.scope_label.setToolTip(universe_detail)
        self.methods_table.setRowCount(len(projection.method_counts))
        for index, counts in enumerate(projection.method_counts):
            label = {
                "close_above_ma20": "收盤價高於 MA20",
                "close_above_ma60": "收盤價高於 MA60",
            }.get(counts.key, counts.key)
            values = (
                f"{label}｜v{counts.version}", str(counts.match_count), str(counts.no_match_count),
                str(counts.unknown_count),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(
                    f"{counts.method_id}\n家族：{counts.family}\n"
                    f"固定參數：{dict(counts.parameters)}\n母體分母：{counts.denominator}"
                )
                self.methods_table.setItem(index, column, item)
        self.methods_table.resizeColumnsToContents()
        self.members_table.setRowCount(len(projection.members))
        for index, member in enumerate(projection.members):
            values = (
                member.stock_code, member.data_date or "未知",
                "未知" if member.close is None else str(member.close),
                "未知" if member.ma20 is None else str(member.ma20),
                "未知" if member.ma60 is None else str(member.ma60),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(
                    f"來源欄位：{dict(member.source_refs)}\n"
                    + "\n".join(
                        f"{condition.method_id}：{condition.state}；{condition.reason}"
                        for condition in member.conditions
                    )
                )
                self.members_table.setItem(index, column, item)
        self.members_table.resizeColumnsToContents()
        self.status_label.setText(
            "盤勢與名單共享已驗證快照；未知包含缺資料，不能當成不符合。"
        )

        self._render_members_table()
        self.ranking_label.setText(ranking_summary_text(self.original_ranking))
        self.ranking_label.setToolTip(ranking_audit_tooltip(self.original_ranking))

    def _render_members_table(self) -> None:
        projection = self.projection
        if projection is None:
            self.members_table.setRowCount(0)
            return
        rows_by_code = ranking_rows_by_code(self.original_ranking) or {}
        members = tuple(getattr(projection, "members", ()) or ())
        self.members_table.setRowCount(len(members))
        for index, member in enumerate(members):
            code = str(getattr(member, "stock_code", "") or "")
            ranking_row = rows_by_code.get(code)
            values = (
                code,
                str(getattr(member, "data_date", None) or "未知"),
                "未知" if getattr(member, "close", None) is None else str(member.close),
                "未知" if getattr(member, "ma20", None) is None else str(member.ma20),
                "未知" if getattr(member, "ma60", None) is None else str(member.ma60),
                original_rank_cell(self.original_ranking, code),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 5:
                    item.setToolTip(
                        original_rank_row_tooltip(self.original_ranking, ranking_row)
                    )
                self.members_table.setItem(index, column, item)
        self.members_table.resizeColumnsToContents()

    def accept_original_ranking(self, ranking: object) -> None:
        snapshot = self._snapshot
        if snapshot is None or not ranking_matches_snapshot(
            snapshot,
            ranking,
            period=str(self.source_view.original_rank_period_combo.currentData() or "day"),
            direction=str(self.source_view.original_rank_direction_combo.currentData() or "strong"),
        ):
            self.clear_original_ranking()
            return
        projection = self.source_view._cohort_projection
        if (
            projection is None
            or getattr(projection, "original_ranking", None) is not ranking
        ):
            self.clear_original_ranking()
            return
        self.original_ranking = ranking
        self.projection = projection
        self.ranking_label.setText(ranking_summary_text(ranking))
        self.ranking_label.setToolTip(ranking_audit_tooltip(ranking))
        self._render_members_table()

    def clear_original_ranking(self) -> None:
        self.original_ranking = None
        projection = self.source_view._cohort_projection
        if (
            projection is not None
            and getattr(projection, "original_ranking", None) is None
        ):
            self.projection = projection
        self.ranking_label.setText(self.source_view.original_ranking_label.text())
        self.ranking_label.setToolTip(self.source_view.original_ranking_label.toolTip())
        self._render_members_table()

    def clear_snapshot(self) -> None:
        self.projection = None
        self._snapshot = None
        self.original_ranking = None
        self._capability_report = None
        self.capability_button.setEnabled(False)
        self._refresh_capability_audit()
        self.methods_table.setRowCount(0)
        self.members_table.setRowCount(0)
        self.scope_label.setText(
            "研究母體未知；目前沒有可用的已驗證快照，不能沿舊母體判定完整。"
        )
        self.identity_label.setText("研究母體未知；目前沒有可用的已驗證快照。")
        self.status_label.setText(self.source_view.status_label.text())

    def _show_capability_audit(self) -> None:
        """明示查看同一 immutable 來源的已開能力；不重算或開新方法。"""

        if self._capability_report is None:
            return
        if self._capability_dialog is None:
            dialog = QDialog(self)
            dialog.setWindowTitle("已開能力與來源核對")
            dialog.resize(900, 650)
            layout = QVBoxLayout(dialog)
            label = QLabel(
                "僅 close／MA20／MA60 與兩條固定觀察；完整相對具名 declared cohort。\n"
                "可得性及未記錄成本維持未知；這是當次保存來源的核對，不授予全市場或歷史 PIT。"
            )
            label.setWordWrap(True)
            layout.addWidget(label)
            tabs = QTabWidget(dialog)
            self._capability_table = QTableWidget(0, 7, tabs)
            self._capability_table.setHorizontalHeaderLabels(
                ["已開項目", "字段／單位", "暖機", "缺值", "可得性", "版本", "成本／來源"]
            )
            self._capability_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
            apply_financial_table_style(self._capability_table)
            tabs.addTab(self._capability_table, "已開能力矩陣")
            self._capability_text = QPlainTextEdit(dialog)
            self._capability_text.setReadOnly(True)
            tabs.addTab(self._capability_text, "逐股與完整來源明細")
            layout.addWidget(tabs)
            self._capability_dialog = dialog
        self._refresh_capability_audit()
        self._capability_dialog.show()

    def _refresh_capability_audit(self) -> None:
        if self._capability_text is None:
            return
        report = self._capability_report
        to_dict = getattr(report, "to_dict", None)
        if not callable(to_dict):
            self._capability_text.setPlainText("來源已失效；請重新核對同一研究來源。")
            if self._capability_table is not None:
                self._capability_table.setRowCount(0)
            return
        payload = to_dict()
        self._capability_text.setPlainText(json.dumps(payload, ensure_ascii=False, indent=2))
        table = self._capability_table
        if table is None:
            return
        catalog = payload.get("catalog", {})
        entries = tuple(catalog.get("features", ())) + tuple(catalog.get("methods", ()))
        table.setRowCount(len(entries))
        for index, entry in enumerate(entries):
            field = entry.get("field", "未知")
            fields = ", ".join(field) if isinstance(field, list) else str(field)
            warmup = entry.get("warmup", {})
            count = warmup.get("required_observation_count")
            warmup_text = (
                "不需暖機" if warmup.get("state") == "not_required"
                else f"{count} 筆；依保存前綴" if count is not None
                else "沿輸入欄位暖機"
            )
            source = entry.get("source", {})
            source_text = str(source.get("source_table") or ", ".join(source.get("input_fields", ())) or "詳見來源明細")
            values = (
                str(entry.get("key", "未知")), f"{fields}\n{entry.get('unit', '未知')}",
                warmup_text, "未知；不補值", "官方時點未知", str(entry.get("version", "未知")),
                f"量測成本未知\n{source_text}",
            )
            detail = json.dumps(entry, ensure_ascii=False, indent=2)
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(detail)
                table.setItem(index, column, item)
        table.resizeColumnsToContents()
        table.resizeRowsToContents()
