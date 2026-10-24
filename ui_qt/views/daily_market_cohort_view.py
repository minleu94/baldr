"""從名單已驗證快照呈現具名研究母體盤勢。"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Callable, Sequence

from ui_qt.research_universe_presentation import research_universe_text

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QDialog, QGroupBox, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QTableWidget, QTabWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from app_module.daily_market_cohort_projection import (
    DailyMarketCohortMethodCount,
    DailyMarketCohortMember,
    DailyMarketCohortProjection,
    project_daily_market_cohort,
)
from app_module.daily_market_research_screener import DailyMarketResearchScreenRow
from app_module.daily_market_snapshot_repository import VerifiedDailyMarketSnapshot
from app_module.research_session import ResearchStockContextDTO
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


class _CohortStateDistributionTrack(QWidget):
    """以既有整數人數繪出具名母體的三態比例條。"""

    STATE_COLORS = (QColor("#3f7896"), QColor("#697781"), QColor("#9da8b0"))

    def __init__(
        self,
        match_count: int,
        no_match_count: int,
        unknown_count: int,
        denominator: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.counts = (match_count, no_match_count, unknown_count)
        self.denominator = denominator
        self.renderable = (
            type(denominator) is int
            and denominator > 0
            and all(type(count) is int and count >= 0 for count in self.counts)
            and sum(self.counts) == denominator
        )
        self.setObjectName("marketCohortStateDistributionTrack")
        self.setAccessibleName("研究母體條件符合、不符合與未知人數分布條")
        description = (
            "符合、不符合及未知的段長只依原快照整數人數與具名母體分母呈現。"
            if self.renderable else "分母或三態人數不可繪製；沒有比例條。"
        )
        self.setAccessibleDescription(description)
        self.setToolTip(description)
        self.setMinimumHeight(10)
        self.setMaximumHeight(10)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt event override
        painter = QPainter(self)
        painter.fillRect(self.rect(), self.palette().alternateBase())
        x = 0
        for next_x, color in zip(
            self.segment_endpoints(self.width()), self.STATE_COLORS,
        ):
            if next_x > x:
                painter.fillRect(x, 0, next_x - x, self.height(), color)
            x = next_x
        painter.end()

    def segment_endpoints(self, width: int) -> tuple[int, ...]:
        """回傳各三態區段的右界，使用整數分配像素寬度。"""

        if not self.renderable or width <= 0:
            return ()
        cumulative = 0
        endpoints: list[int] = []
        for count in self.counts:
            cumulative += count
            endpoints.append(width * cumulative // self.denominator)
        return tuple(endpoints)


class _CohortStateDistribution(QWidget):
    """在三態圖條旁保留 DTO 精確人數與固定母體分母。"""

    def __init__(
        self,
        match_count: int,
        no_match_count: int,
        unknown_count: int,
        denominator: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("marketCohortStateDistribution")
        self.setAccessibleName("研究母體三態人數分布")
        self.counts = (match_count, no_match_count, unknown_count)
        self.denominator = denominator
        self.track = _CohortStateDistributionTrack(
            match_count, no_match_count, unknown_count, denominator, self,
        )
        self.summary_text = (
            f"符合 {match_count}｜不符合 {no_match_count}｜未知 {unknown_count}"
            f"｜母體 {denominator}"
        )
        match_color, no_match_color, unknown_color = (
            color.name() for color in self.track.STATE_COLORS
        )
        self.counts_label = QLabel(self)
        self.counts_label.setTextFormat(Qt.TextFormat.RichText)
        self.counts_label.setText(
            f'<span style="color:{match_color}">■ 符合 {match_count}</span>｜'
            f'<span style="color:{no_match_color}">■ 不符合 {no_match_count}</span>｜'
            f'<span style="color:{unknown_color}">■ 未知 {unknown_count}</span>｜'
            f"母體 {denominator}"
        )
        self.counts_label.setObjectName("marketCohortStateDistributionCounts")
        self.counts_label.setAccessibleName("符合、不符合、未知及固定母體的精確人數")
        self.counts_label.setAccessibleDescription(self.summary_text)
        self.counts_label.setToolTip(self.summary_text)
        self.counts_label.setMinimumHeight(self.counts_label.fontMetrics().lineSpacing())
        self.counts_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(3, 2, 3, 2)
        layout.setSpacing(1)
        layout.addWidget(self.track)
        layout.addWidget(self.counts_label)
        self.setMinimumWidth(260)
        layout.activate()
        margins = layout.contentsMargins()
        track_height = max(
            self.track.minimumHeight(), self.track.sizeHint().height()
        )
        self.content_height = (
            margins.top()
            + track_height
            + layout.spacing()
            + self.counts_label.fontMetrics().lineSpacing()
            + margins.bottom()
        )
        self.setMinimumHeight(self.content_height)
        self.setToolTip(self.summary_text)


class DailyMarketCohortView(QWidget):
    """盤勢與名單共享同一個讀取流程；本頁不讀資料庫或重算方法。"""

    stockResearchRequested = Signal(object)

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
        self._screen_rows_by_code: dict[str, DailyMarketResearchScreenRow] = {}
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
        self.methods_table = QTableWidget(0, 5)
        self.methods_table.setHorizontalHeaderLabels(
            ["固定方法", "符合", "不符合", "未知", "三態分布（人數）"]
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
        self.members_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.members_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        apply_financial_table_style(self.members_table)
        member_workspace = QHBoxLayout()
        member_workspace.addWidget(self.members_table, 4)
        self.selected_member_detail_group = QGroupBox("所選成員固定條件觀察")
        detail_layout = QVBoxLayout(self.selected_member_detail_group)
        self.selected_member_detail_label = QLabel(
            "選取一列以查看同一快照中的固定條件原狀態、關係與原因；非投資建議。"
        )
        self.selected_member_detail_label.setObjectName("marketCohortSelectedMemberConditions")
        self.selected_member_detail_label.setAccessibleName("所選母體成員的固定條件觀察")
        self.selected_member_detail_label.setTextFormat(Qt.TextFormat.PlainText)
        self.selected_member_detail_label.setWordWrap(True)
        self.selected_member_detail_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        detail_layout.addWidget(self.selected_member_detail_label)
        detail_font = self.selected_member_detail_label.fontMetrics()
        self.selected_member_detail_group.setMinimumWidth(
            detail_font.horizontalAdvance(
                "收盤價高於 MA60：未知（unknown）｜關係：未知（unknown）"
            ) + detail_layout.contentsMargins().left()
            + detail_layout.contentsMargins().right()
        )
        member_workspace.addWidget(
            self.selected_member_detail_group, 2, Qt.AlignmentFlag.AlignTop,
        )
        layout.addLayout(member_workspace)
        self.members_table.itemSelectionChanged.connect(
            self._sync_research_selected_button
        )
        self.ranking_label = QLabel(
            "原排名未提供：發布快照未含原強弱排名。名單可依既有指標值排序；"
            "排序不是投資分數，不能推定強弱或勝率。"
        )
        self.ranking_label.setWordWrap(True)
        layout.addWidget(self.ranking_label)
        controls = QHBoxLayout()
        self.research_selected_button = QPushButton("研究所選成員")
        self.research_selected_button.setObjectName("marketCohortResearchSelectedMember")
        self.research_selected_button.setAccessibleName("開啟所選研究母體成員的個股研究")
        self.research_selected_button.setEnabled(False)
        self.research_selected_button.clicked.connect(self.open_selected_member_research)
        controls.addWidget(self.research_selected_button)
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
        self.members_table.clearSelection()
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
        self._screen_rows_by_code = {
            row.stock_code: row
            for row in rows
            if type(row) is DailyMarketResearchScreenRow
        }
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
        self._render_method_counts(projection.method_counts)
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
        self._sync_research_selected_button()
        self.status_label.setText(
            "盤勢與名單共享已驗證快照；未知包含缺資料，不能當成不符合。"
        )

        self._render_members_table()
        self.ranking_label.setText(ranking_summary_text(self.original_ranking))
        self.ranking_label.setToolTip(ranking_audit_tooltip(self.original_ranking))

    def _render_method_counts(
        self, method_counts: Sequence[DailyMarketCohortMethodCount],
    ) -> None:
        """保留原始三態數字，並以相同分母提供緊湊視覺掃讀。"""

        counts_rows = tuple(method_counts)
        self.methods_table.setRowCount(len(counts_rows))
        for index, counts in enumerate(counts_rows):
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
            distribution = _CohortStateDistribution(
                counts.match_count,
                counts.no_match_count,
                counts.unknown_count,
                counts.denominator,
                self.methods_table,
            )
            self.methods_table.setCellWidget(index, 4, distribution)
            # OS DPI 及字型會改變行距；列高以目前實際字型和版面邊距計算。
            cell_padding = max(2, self.methods_table.frameWidth() * 2)
            self.methods_table.setRowHeight(
                index,
                max(36, distribution.content_height + cell_padding),
            )
        self.methods_table.resizeColumnsToContents()

    def _render_members_table(self) -> None:
        projection = self.projection
        if projection is None:
            self.members_table.setRowCount(0)
            self._sync_research_selected_button()
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
        self._sync_research_selected_button()

    def _research_context_for_member(
        self, stock_code: str,
    ) -> ResearchStockContextDTO | None:
        """Build a source-pinned context only from the current verified cohort row."""

        snapshot = self._snapshot
        projection = self.projection
        source_view = self.source_view
        if (
            type(snapshot) is not VerifiedDailyMarketSnapshot
            or type(projection) is not DailyMarketCohortProjection
            or source_view._snapshot is not snapshot
            or source_view._shutting_down
            or projection.source_snapshot_hash != snapshot.manifest_sha256
            or projection.source_snapshot_id != snapshot.manifest_identity_sha256
            or projection.cohort_id != snapshot.cohort_id
            or projection.decision_date != snapshot.decision_date.isoformat()
            or source_view._manifest_sha256 != snapshot.manifest_sha256
            or source_view._manifest_identity_sha256 != snapshot.manifest_identity_sha256
            or source_view._loaded_decision_date != snapshot.decision_date.isoformat()
        ):
            return None
        code = str(stock_code or "").strip()
        row = self._screen_rows_by_code.get(code)
        if (
            not code
            or code not in snapshot.stock_snapshots
            or code not in projection.published_stock_codes
            or row is None
            or row.stock_code != code
            or row.cohort_id != projection.cohort_id
            or row.decision_date != projection.decision_date
            or row.source_snapshot_id != projection.source_snapshot_id
            or row.source_snapshot_hash != projection.source_snapshot_hash
            or row.condition_keys != ("close_above_ma20", "close_above_ma60")
            or row.combine_mode != "AND"
        ):
            return None
        member = next(
            (candidate for candidate in projection.members if candidate.stock_code == code),
            None,
        )
        if member is None or (member.data_date or "") != row.data_date:
            return None
        context_builder = getattr(source_view.service, "context_for_stock", None)
        if not callable(context_builder):
            return None
        try:
            context = context_builder(row, stock_name="")
        except Exception:
            return None
        if (
            type(context) is not ResearchStockContextDTO
            or context.stock_code != code
            or context.decision_date != row.decision_date
            or context.data_date != row.data_date
            or context.source_snapshot_id != projection.source_snapshot_id
            or context.source_snapshot_hash != projection.source_snapshot_hash
            or context.source_kind != "daily_market_research_snapshot"
            or context.daily_snapshot_cohort_id != projection.cohort_id
            or context.daily_snapshot_condition_keys != "close_above_ma20,close_above_ma60"
            or context.daily_snapshot_combine_mode != "AND"
            or not context.daily_snapshot_root
        ):
            return None
        try:
            expected_root = Path(source_view.service.snapshot_root).expanduser().resolve()
            if (
                Path(row.snapshot_root).expanduser().resolve() != expected_root
                or Path(context.daily_snapshot_root).expanduser().resolve() != expected_root
            ):
                return None
        except (AttributeError, OSError, TypeError, ValueError):
            return None
        return replace(
            context,
            source_label="市場探索／研究母體盤勢成員",
            source_workspace="market_explore",
        )

    def _selected_member_code(self) -> str:
        selected = self.members_table.selectionModel().selectedRows()
        if len(selected) != 1:
            return ""
        item = self.members_table.item(selected[0].row(), 0)
        return item.text().strip() if item is not None else ""

    def _sync_research_selected_button(self) -> None:
        button = getattr(self, "research_selected_button", None)
        if button is None:
            return
        button.setEnabled(
            self._research_context_for_member(self._selected_member_code()) is not None
        )
        self._render_selected_member_detail()

    def _render_selected_member_detail(self) -> None:
        """只顯示目前 typed cohort member 保存的兩項固定條件原值。"""

        projection = self.projection
        code = self._selected_member_code()
        if type(projection) is not DailyMarketCohortProjection or not code:
            self.selected_member_detail_label.setText(
                "選取一列以查看同一快照中的固定條件原狀態、關係與原因；非投資建議。"
            )
            return
        member = next(
            (
                candidate for candidate in projection.members
                if candidate.stock_code == code
            ),
            None,
        )
        if type(member) is not DailyMarketCohortMember:
            self.selected_member_detail_label.setText(
                "所選列不在目前已驗證的母體快照；固定條件觀察未知。"
            )
            return

        states = {
            "match": "符合",
            "no_match": "不符合",
            "unknown": "未知",
        }
        relations = {
            "above": "高於",
            "below": "低於",
            "equal": "相等",
            "unknown": "未知",
        }
        conditions = {condition.key: condition for condition in member.conditions}
        lines = [
            f"{member.stock_code}｜資料日 {member.data_date or '未知'}｜"
            "固定條件觀察，非投資建議。"
        ]
        for key, label in (
            ("close_above_ma20", "收盤價高於 MA20"),
            ("close_above_ma60", "收盤價高於 MA60"),
        ):
            condition = conditions.get(key)
            if condition is None:
                lines.append(f"{label}：未知（未提供）｜關係：未知｜原因：未提供")
                continue
            state = str(condition.state or "unknown")
            relation = str(condition.relation or "unknown")
            state_label = states.get(state, "未知")
            relation_label = relations.get(relation, "未知")
            reason = str(condition.reason or "未提供")
            lines.append(
                f"{label}：{state_label}（{state}）｜"
                f"關係：{relation_label}（{relation}）｜原因：{reason}"
            )
            unknown_reason = str(condition.unknown_reason or "").strip()
            if unknown_reason:
                lines.append(f"未知原因：{unknown_reason}")
        self.selected_member_detail_label.setText("\n".join(lines))

    def open_selected_member_research(self) -> bool:
        """Open the selected published member using its exact source row."""

        context = self._research_context_for_member(self._selected_member_code())
        if context is None:
            self.status_label.setText(
                "所選成員不屬於目前已驗證快照，或來源已變動；未開啟個股研究。"
            )
            self._sync_research_selected_button()
            return False
        self.stockResearchRequested.emit(context)
        self.status_label.setText(
            f"已開啟 {context.stock_code} 個股研究；來源固定於目前研究母體快照。"
        )
        return True

    def restore_member_selection(self, context: object) -> bool:
        """Restore a member only while its entire source context still matches."""

        if type(context) is not ResearchStockContextDTO:
            return False
        expected = self._research_context_for_member(context.stock_code)
        if expected != context:
            return False
        for row in range(self.members_table.rowCount()):
            item = self.members_table.item(row, 0)
            if item is not None and item.text().strip() == context.stock_code:
                self.members_table.selectRow(row)
                return True
        return False

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
        self._screen_rows_by_code = {}
        self.original_ranking = None
        self._capability_report = None
        self.capability_button.setEnabled(False)
        self._refresh_capability_audit()
        self._render_method_counts(())
        self.members_table.setRowCount(0)
        self.members_table.clearSelection()
        self._sync_research_selected_button()
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
