"""使用者明選的本機產業鏈／題材研究版本檢視頁。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QSignalBlocker, Signal, Slot
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app_module.theme_daily_service import ThemeDailyRow
from app_module.theme_research_presentation import (
    ThemeResearchPresentation,
    build_theme_research_presentation,
)
from app_module.theme_research_snapshot import (
    ThemeResearchSnapshot,
    read_theme_research_snapshot,
)
from ui_qt.theme import MIDNIGHT_ANALYST
from ui_qt.workers.task_worker import TaskWorker


class IndustryThemeMapView(QWidget):
    """唯讀呈現使用者選取的本機題材快照，不建立或接受研究版本。"""

    stockSelected = Signal(str)
    snapshotChanged = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._generation = 0
        self._worker_generation: int | None = None
        self._worker: TaskWorker | None = None
        self._result: object = None
        self._error = ""
        self._cancelled = False
        self._busy = False
        self._closed = False
        self._snapshot: ThemeResearchSnapshot | None = None
        self._presentation: ThemeResearchPresentation | None = None
        self._theme_options: list[tuple[str, str] | None] = []
        self._rows_by_theme: dict[tuple[str, str], ThemeDailyRow] = {}
        self._mapping_by_theme_stock: dict[tuple[str, str, str], object] = {}

        self._build_ui()
        self._render_empty("請選取本機已保存的題材研究版本。")
        self._update_controls()

    @property
    def snapshot(self) -> ThemeResearchSnapshot | None:
        """目前載入的唯讀快照，供主視圖核對 identity 與映射。"""

        return self._snapshot

    def _build_ui(self) -> None:
        page_layout = QVBoxLayout(self)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(8)

        header = QHBoxLayout()
        self.title_label = QLabel("產業與題材")
        self.title_label.setAccessibleName("產業與題材頁標題")
        self.title_label.setStyleSheet(
            f"color: {MIDNIGHT_ANALYST.text_primary}; font-size: 18px; font-weight: 600;"
        )
        header.addWidget(self.title_label)
        header.addStretch(1)
        self.open_snapshot_button = QPushButton("選取本機研究版本…")
        self.open_snapshot_button.setObjectName("industryThemeOpenSnapshotButton")
        self.open_snapshot_button.setAccessibleName("選取本機已保存題材研究版本")
        self.open_snapshot_button.clicked.connect(self._choose_snapshot)
        header.addWidget(self.open_snapshot_button)
        page_layout.addLayout(header)

        self.status_label = QLabel("尚未載入題材研究版本。")
        self.status_label.setAccessibleName("題材研究版本讀取狀態")
        self.status_label.setWordWrap(True)
        self.status_label.setTextFormat(Qt.TextFormat.PlainText)
        self.status_label.setStyleSheet(f"color: {MIDNIGHT_ANALYST.text_secondary};")
        page_layout.addWidget(self.status_label)

        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll_area.setAccessibleName("產業與題材內容捲動區")
        self.content = QWidget()
        content_layout = QVBoxLayout(self.content)
        content_layout.setContentsMargins(10, 4, 10, 10)
        content_layout.setSpacing(8)

        self.overview_label = QLabel(
            "尚未載入題材研究版本；請先選取本機已保存版本。"
        )
        self.overview_label.setObjectName("industryThemeShortOverview")
        self.overview_label.setAccessibleName("題材研究短摘要")
        self.overview_label.setWordWrap(True)
        self.overview_label.setTextFormat(Qt.TextFormat.PlainText)
        content_layout.addWidget(self.overview_label)

        self.summary_group = QGroupBox("所選版本與限制")
        self.summary_group.setVisible(False)
        summary_layout = QVBoxLayout(self.summary_group)
        self.summary_label = QLabel("尚未載入。")
        self.summary_label.setObjectName("industryThemeSnapshotSummary")
        self.summary_label.setAccessibleName("所選題材研究版本摘要")
        self.summary_label.setWordWrap(True)
        self.summary_label.setTextFormat(Qt.TextFormat.PlainText)
        summary_layout.addWidget(self.summary_label)

        self.observations_group = QGroupBox("完整覆蓋觀察重點")
        observations_layout = QHBoxLayout(self.observations_group)
        observations_layout.setSpacing(8)
        self.leader_card_topics: dict[str, QLabel] = {}
        self.leader_card_values: dict[str, QLabel] = {}
        self.leader_card_coverages: dict[str, QLabel] = {}
        card_titles = (
            ("return", "較高日漲跌幅"),
            ("turnover", "較高成交金額"),
            ("institutional", "法人淨流向"),
            ("volume", "五日量能"),
        )
        for key, title in card_titles:
            card = QGroupBox(title)
            card_layout = QVBoxLayout(card)
            topic_label = QLabel("尚未載入")
            topic_label.setAccessibleName(f"{title}觀察題材")
            topic_label.setWordWrap(True)
            value_label = QLabel("資料不足")
            value_label.setAccessibleName(f"{title}觀察值")
            value_label.setWordWrap(True)
            value_label.setStyleSheet(
                f"color: {MIDNIGHT_ANALYST.text_primary}; font-size: 15px; font-weight: 600;"
            )
            coverage_label = QLabel("尚未載入")
            coverage_label.setAccessibleName(f"{title}欄位覆蓋")
            coverage_label.setWordWrap(True)
            card_layout.addWidget(topic_label)
            card_layout.addWidget(value_label)
            card_layout.addWidget(coverage_label)
            observations_layout.addWidget(card, 1)
            self.leader_card_topics[key] = topic_label
            self.leader_card_values[key] = value_label
            self.leader_card_coverages[key] = coverage_label
        content_layout.addWidget(self.observations_group)

        self.ranking_group = QGroupBox("完整覆蓋題材排行（最多前五名）")
        ranking_layout = QVBoxLayout(self.ranking_group)
        ranking_header = QHBoxLayout()
        ranking_header.addWidget(QLabel("排行類型"))
        self.ranking_type_combo = QComboBox()
        self.ranking_type_combo.setAccessibleName("題材排行類型")
        self.ranking_type_combo.addItem("平均日漲跌幅", "return")
        self.ranking_type_combo.addItem("成交金額", "turnover")
        self.ranking_type_combo.addItem("法人淨股數", "institutional")
        self.ranking_type_combo.addItem("五日成交量倍數", "volume")
        self.ranking_type_combo.currentIndexChanged.connect(self._render_leaderboard)
        ranking_header.addWidget(self.ranking_type_combo)
        ranking_header.addStretch(1)
        ranking_layout.addLayout(ranking_header)

        self.ranking_table = QTableWidget(0, 5)
        self.ranking_table.setObjectName("industryThemeResearchRankingTable")
        self.ranking_table.setAccessibleName("完整覆蓋題材排行表")
        self.ranking_table.setHorizontalHeaderLabels(
            ["名次", "產業鏈", "題材", "觀察值", "覆蓋數"]
        )
        self.ranking_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.ranking_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.ranking_table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.ranking_table.setAlternatingRowColors(True)
        self.ranking_table.setWordWrap(True)
        self.ranking_table.verticalHeader().setVisible(False)
        self.ranking_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        self.ranking_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents
        )
        self.ranking_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch
        )
        self.ranking_table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeMode.ResizeToContents
        )
        self.ranking_table.horizontalHeader().setSectionResizeMode(
            4, QHeaderView.ResizeMode.ResizeToContents
        )
        self.ranking_table.cellClicked.connect(self._on_leaderboard_row_clicked)
        ranking_layout.addWidget(self.ranking_table)
        self.ranking_empty_label = QLabel("尚未載入題材觀察排行。")
        self.ranking_empty_label.setAccessibleName("題材排行缺件說明")
        self.ranking_empty_label.setWordWrap(True)
        self.ranking_empty_label.setTextFormat(Qt.TextFormat.PlainText)
        ranking_layout.addWidget(self.ranking_empty_label)
        self.ranking_note = QLabel(
            "此表僅整理對應欄位覆蓋完整的觀察值，不形成策略結論；點選題材可定位原成員。"
        )
        self.ranking_note.setWordWrap(True)
        self.ranking_note.setTextFormat(Qt.TextFormat.PlainText)
        self.ranking_note.setStyleSheet(f"color: {MIDNIGHT_ANALYST.text_secondary};")
        ranking_layout.addWidget(self.ranking_note)
        content_layout.addWidget(self.ranking_group)

        self.source_details_button = QPushButton("顯示來源與限制")
        self.source_details_button.setObjectName("industryThemeSourceDetailsButton")
        self.source_details_button.setAccessibleName("顯示或收合題材來源與限制")
        self.source_details_button.setCheckable(True)
        self.source_details_button.toggled.connect(self._toggle_source_details)
        content_layout.addWidget(self.source_details_button)
        content_layout.addWidget(self.summary_group)

        self.filter_group = QGroupBox("選擇產業鏈與題材")
        filter_layout = QHBoxLayout(self.filter_group)
        self.chain_filter = QComboBox()
        self.chain_filter.setAccessibleName("產業鏈篩選")
        self.chain_filter.currentIndexChanged.connect(self._on_chain_changed)
        self.theme_filter = QComboBox()
        self.theme_filter.setAccessibleName("題材篩選")
        self.theme_filter.currentIndexChanged.connect(self._on_theme_changed)
        filter_layout.addWidget(QLabel("產業鏈"))
        filter_layout.addWidget(self.chain_filter, 1)
        filter_layout.addWidget(QLabel("題材"))
        filter_layout.addWidget(self.theme_filter, 2)
        content_layout.addWidget(self.filter_group)

        self.metrics_group = QGroupBox("題材指標與欄位覆蓋")
        metrics_layout = QVBoxLayout(self.metrics_group)
        self.metrics_table = QTableWidget(0, 3)
        self.metrics_table.setObjectName("industryThemeMetricsTable")
        self.metrics_table.setAccessibleName("題材指標與欄位覆蓋表")
        self.metrics_table.setHorizontalHeaderLabels(["指標", "觀察值", "覆蓋數"])
        self.metrics_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.metrics_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.metrics_table.setAlternatingRowColors(True)
        self.metrics_table.setWordWrap(True)
        self.metrics_table.verticalHeader().setVisible(False)
        self.metrics_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        self.metrics_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self.metrics_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.ResizeToContents
        )
        metrics_layout.addWidget(self.metrics_table)
        content_layout.addWidget(self.metrics_group)

        self.members_group = QGroupBox("題材成員（雙擊任一欄開啟）")
        members_layout = QVBoxLayout(self.members_group)
        self.member_table = QTableWidget(0, 4)
        self.member_table.setObjectName("industryThemeMemberTable")
        self.member_table.setAccessibleName("題材成員與分類依據清單")
        self.member_table.setHorizontalHeaderLabels(
            ["股票代號", "股票名稱", "鏈別位置", "分類依據"]
        )
        self.member_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.member_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.member_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.member_table.setAlternatingRowColors(True)
        self.member_table.setWordWrap(True)
        self.member_table.verticalHeader().setVisible(False)
        self.member_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        self.member_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self.member_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.ResizeToContents
        )
        self.member_table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeMode.Stretch
        )
        self.member_table.itemDoubleClicked.connect(self._emit_selected_stock)
        members_layout.addWidget(self.member_table)
        content_layout.addWidget(self.members_group)
        content_layout.addStretch(1)

        self.scroll_area.setWidget(self.content)
        page_layout.addWidget(self.scroll_area, 1)

    def _choose_snapshot(self) -> None:
        if self._closed or self._busy:
            return
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "選取題材研究版本",
            "",
            "題材版本 manifest (*.json);;所有檔案 (*.*)",
        )
        if selected:
            self.load_snapshot(Path(selected))

    def load_snapshot(
        self,
        path: Path,
        *,
        expected_identity_sha256: str | None = None,
    ) -> None:
        """背景讀取指定 manifest；新讀取開始即清除舊版本可操作狀態。"""

        if self._closed or self._busy:
            return
        if not isinstance(path, Path):
            raise TypeError("path 必須是 pathlib.Path")
        if expected_identity_sha256 is not None and not isinstance(
            expected_identity_sha256, str
        ):
            raise TypeError("expected_identity_sha256 必須是字串或 None")

        self._generation += 1
        generation = self._generation
        self._snapshot = None
        self._result = None
        self._error = ""
        self._cancelled = False
        self._clear_snapshot_view()
        self.snapshotChanged.emit(None)
        self._busy = True
        self.status_label.setText("正在讀取所選本機研究版本；舊版本已清除。")
        self._update_controls()

        if expected_identity_sha256 is None:
            worker = TaskWorker(read_theme_research_snapshot, path)
        else:
            worker = TaskWorker(
                read_theme_research_snapshot,
                path,
                expected_identity_sha256=expected_identity_sha256,
            )
        self._worker = worker
        self._worker_generation = generation
        worker.finished.connect(
            self._receive_snapshot, Qt.ConnectionType.QueuedConnection
        )
        worker.error.connect(
            self._receive_error, Qt.ConnectionType.QueuedConnection
        )
        worker.cancelled.connect(
            self._receive_cancelled, Qt.ConnectionType.QueuedConnection
        )
        worker.native_thread_finished.connect(
            self._finish_snapshot_load, Qt.ConnectionType.QueuedConnection
        )
        try:
            worker.start()
        except Exception as exc:
            self._worker = None
            self._worker_generation = None
            self._busy = False
            self._result = None
            self._error = ""
            self._cancelled = False
            self.status_label.setText(f"題材版本讀取無法啟動：{exc}")
            self.snapshotChanged.emit(None)
            worker.deleteLater()
            self._update_controls()

    def set_snapshot(self, snapshot: ThemeResearchSnapshot) -> None:
        """設定已讀取的 typed snapshot，並清除前一版本的篩選與選取。"""

        if self._closed:
            return
        if not isinstance(snapshot, ThemeResearchSnapshot):
            raise TypeError("snapshot 必須是 ThemeResearchSnapshot")
        self._generation += 1
        if self._worker is not None:
            self._worker.cancel(cooperative=True, wait=False)
        self._result = None
        self._error = ""
        self._cancelled = False
        self._snapshot = snapshot
        try:
            self._apply_snapshot(snapshot)
        except Exception as exc:
            self._snapshot = None
            self._clear_snapshot_view()
            self.status_label.setText(f"題材版本呈現失敗；沒有沿用舊版本：{exc}")
            self.snapshotChanged.emit(None)
            self._busy = self._worker is not None
            self._update_controls()
            return
        self.snapshotChanged.emit(snapshot)
        self._busy = self._worker is not None
        if self._busy:
            self.status_label.setText("已指定新版本；背景舊讀取正在合作式取消。")
        else:
            self.status_label.setText("已載入所選本機研究版本。")
        self._update_controls()

    def is_busy(self) -> bool:
        return self._busy

    def shutdown(self) -> None:
        """失效所有回呼並非阻塞地要求背景讀取取消。"""

        if self._closed:
            return
        self._closed = True
        self._generation += 1
        self._snapshot = None
        self.snapshotChanged.emit(None)
        if self._worker is not None:
            self._worker.cancel(cooperative=True, wait=False)
        self._clear_snapshot_view()
        self.status_label.setText("頁面已關閉；背景讀取正在合作式結束。")
        self._update_controls()

    @Slot(object)
    def _receive_snapshot(self, result: object) -> None:
        if (
            self.sender() is self._worker
            and self._worker_generation == self._generation
            and not self._closed
        ):
            self._result = result

    @Slot(str)
    def _receive_error(self, error: str) -> None:
        if (
            self.sender() is self._worker
            and self._worker_generation == self._generation
            and not self._closed
        ):
            self._error = error

    @Slot()
    def _receive_cancelled(self) -> None:
        if (
            self.sender() is self._worker
            and self._worker_generation == self._generation
            and not self._closed
        ):
            self._cancelled = True

    @Slot()
    def _finish_snapshot_load(self) -> None:
        worker = self.sender()
        if worker is not self._worker:
            return
        generation = self._worker_generation
        result = self._result
        error = self._error
        cancelled = self._cancelled
        self._worker = None
        self._worker_generation = None
        self._busy = False
        try:
            if self._closed:
                return
            if generation != self._generation:
                if self._snapshot is not None:
                    self.status_label.setText("已載入所選本機研究版本。")
                return
            if cancelled:
                self._snapshot = None
                self._clear_snapshot_view()
                self.status_label.setText("題材版本讀取已取消；沒有沿用舊版本。")
                self.snapshotChanged.emit(None)
                return
            if error:
                self._snapshot = None
                self._clear_snapshot_view()
                self.status_label.setText(
                    "題材版本讀取失敗；沒有沿用舊版本：" + error.splitlines()[0]
                )
                self.snapshotChanged.emit(None)
                return
            if not isinstance(result, ThemeResearchSnapshot):
                self._snapshot = None
                self._clear_snapshot_view()
                self.status_label.setText(
                    "題材版本讀取失敗；讀者未回傳 ThemeResearchSnapshot。"
                )
                self.snapshotChanged.emit(None)
                return
            self._snapshot = result
            self._apply_snapshot(result)
            self.snapshotChanged.emit(result)
            self.status_label.setText("已載入所選本機研究版本。")
        except Exception as exc:
            self._snapshot = None
            self._clear_snapshot_view()
            self.status_label.setText(f"題材版本呈現失敗；沒有沿用舊版本：{exc}")
            self.snapshotChanged.emit(None)
        finally:
            self._result = None
            self._error = ""
            self._cancelled = False
            self._update_controls()
            worker.deleteLater()

    def _apply_snapshot(self, snapshot: ThemeResearchSnapshot) -> None:
        self._clear_snapshot_view()
        self._presentation = build_theme_research_presentation(snapshot)
        report = snapshot.report
        rows = tuple(report.rows)
        self._rows_by_theme = {
            (row.chain_name, row.theme_name): row
            for row in rows
        }
        self._mapping_by_theme_stock = {}
        for mapping_row in snapshot.mapping:
            key = (
                mapping_row.chain_name,
                mapping_row.theme_name,
                mapping_row.stock_id,
            )
            self._mapping_by_theme_stock.setdefault(key, mapping_row)

        chain_names = [directory.chain_name for directory in self._presentation.chains]
        theme_keys = {(row.chain_name, row.theme_name) for row in rows}
        member_ids = {
            stock_id
            for directory in self._presentation.chains
            for stock_id in directory.stock_ids
        }
        if not member_ids:
            member_ids = {stock_id for row in rows for stock_id in row.stock_ids}

        self.summary_label.setText(
            "\n".join((
                f"資料日：{report.data_date.isoformat()}　｜　讀取時間：{report.known_at.isoformat()}",
                f"映射版本日期：{report.mapping_snapshot_date}　｜　映射可得日期：{report.mapping_available_date}",
                f"產業鏈：{len(chain_names)}　｜　題材：{len(theme_keys)}　｜　不重複成員：{len(member_ids)}",
                f"版本 identity SHA-256：{snapshot.identity_sha256}",
                "限制：這是使用者明選的本機目前研究版本；不代表官方來源接受或歷史 PIT。",
                "缺值與欄位覆蓋分開呈現；Decimal 只顯示保存值，不換算、不補零。",
                "本機版本讀取器不提供交易日曆；五日成交量倍數未提供時保留缺件。",
                "研究狀態：" + str(report.status),
                "來源提醒：" + ("；".join(report.warnings) if report.warnings else "沒有額外提醒。"),
            ))
        )
        missing_fields = []
        if any(row.coverage.returns < row.coverage.members for row in rows):
            missing_fields.append("價格漲跌")
        if any(row.coverage.turnover < row.coverage.members for row in rows):
            missing_fields.append("成交金額")
        if any(
            row.coverage.institutional_shares < row.coverage.members
            or row.coverage.institutional_amount < row.coverage.members
            for row in rows
        ):
            missing_fields.append("法人資料")
        if any(row.coverage.volume_history < row.coverage.members for row in rows):
            missing_fields.append("五日量能")

        warning_labels = {
            "mapping_clock_unavailable_or_future": "分類版本可得時間缺件",
            "mapping_not_date_aligned": "分類版本未與資料日對齊",
            "five_session_calendar_unavailable": "五日交易日曆未核",
            "price_clock_or_source_unavailable": "價格來源或可得時間缺件",
            "flow_clock_or_source_unavailable": "法人來源或可得時間缺件",
        }
        known_warnings = list(dict.fromkeys(
            warning_labels[warning]
            for warning in report.warnings
            if warning in warning_labels
        ))
        unknown_warning_count = sum(
            warning not in warning_labels for warning in report.warnings
        )
        overview_parts = [
            f"資料日：{report.data_date.isoformat()}　｜　"
            f"範圍：{len(chain_names)} 條產業鏈／{len(theme_keys)} 個題材",
            "使用者明選的本機目前研究；不代表官方來源接受或歷史 PIT。",
        ]
        if missing_fields:
            overview_parts.append("部分欄位缺件：" + "、".join(missing_fields))
        if known_warnings:
            overview_parts.append("來源限制：" + "、".join(known_warnings))
        if unknown_warning_count:
            overview_parts.append(
                f"另有 {unknown_warning_count} 項來源提醒，詳見來源與限制。"
            )
        self.overview_label.setText("　｜　".join(overview_parts))

        blocker = QSignalBlocker(self.chain_filter)
        self.chain_filter.clear()
        self.chain_filter.addItem("全部產業鏈", None)
        for chain_name in chain_names:
            self.chain_filter.addItem(chain_name, chain_name)
        del blocker
        self._populate_theme_filter()
        self._render_presentation()
        self.scroll_area.verticalScrollBar().setValue(0)
        self.scroll_area.horizontalScrollBar().setValue(0)

    def _clear_snapshot_view(self) -> None:
        self._presentation = None
        self._rows_by_theme = {}
        self._mapping_by_theme_stock = {}
        self._theme_options = [None]
        self.overview_label.setText(
            "尚未載入題材研究版本；請先選取本機已保存版本。"
        )
        self.summary_label.setText("尚未載入。")
        self.summary_group.setVisible(False)
        self.source_details_button.setChecked(False)
        self.source_details_button.setText("顯示來源與限制")
        self.metrics_table.setRowCount(0)
        self.member_table.setRowCount(0)
        for key in self.leader_card_topics:
            self.leader_card_topics[key].setText("尚未載入")
            self.leader_card_values[key].setText("資料不足")
            self.leader_card_values[key].setToolTip("")
            self.leader_card_coverages[key].setText("尚未載入題材觀察值。")
        self.ranking_table.setRowCount(0)
        self.ranking_empty_label.setText("尚未載入題材觀察排行。")
        self.ranking_empty_label.show()
        blockers = [QSignalBlocker(self.chain_filter), QSignalBlocker(self.theme_filter)]
        self.chain_filter.clear()
        self.chain_filter.addItem("全部產業鏈", None)
        self.theme_filter.clear()
        self.theme_filter.addItem("選擇題材", None)
        del blockers
        self.scroll_area.verticalScrollBar().setValue(0)
        self.scroll_area.horizontalScrollBar().setValue(0)

    def _populate_theme_filter(self) -> None:
        presentation = self._presentation
        chain_name = self.chain_filter.currentData()
        options = sorted({
            (directory.chain_name, theme)
            for directory in (presentation.chains if presentation is not None else ())
            if chain_name is None or directory.chain_name == chain_name
            for theme in directory.themes
        })
        self._theme_options = [None, *options]
        blocker = QSignalBlocker(self.theme_filter)
        self.theme_filter.clear()
        self.theme_filter.addItem("選擇題材", None)
        for chain, theme in options:
            label = theme if chain_name is not None else f"{chain}／{theme}"
            self.theme_filter.addItem(label)
        del blocker
        self._render_selected_theme()

    def _render_presentation(self) -> None:
        presentation = self._presentation
        if presentation is None:
            return
        leader_lists = {
            "return": presentation.return_leaders,
            "turnover": presentation.turnover_leaders,
            "institutional": presentation.institutional_leaders,
            "volume": presentation.volume_leaders,
        }
        for key, rows in leader_lists.items():
            if not rows:
                self.leader_card_topics[key].setText("完整覆蓋題材不足")
                self.leader_card_values[key].setText("資料不足")
                self.leader_card_values[key].setToolTip(
                    "沒有成員覆蓋完整且具可用觀察值的題材。"
                )
                self.leader_card_coverages[key].setText(
                    "沒有成員覆蓋完整且具可用觀察值的題材。"
                )
                continue
            row = rows[0]
            value, available, members = self._leader_value_and_coverage(key, row)
            self.leader_card_topics[key].setText(
                f"{row.chain_name}／{row.theme_name}"
            )
            self.leader_card_values[key].setText(value)
            self.leader_card_values[key].setToolTip(
                self._leader_original_value(key, row)
            )
            self.leader_card_coverages[key].setText(
                self._coverage(available, members)
            )
        self._render_leaderboard()

    def _render_leaderboard(self, _index: int = -1) -> None:
        presentation = self._presentation
        ranking_type = self.ranking_type_combo.currentData()
        row_sets = {
            "return": presentation.return_leaders if presentation is not None else (),
            "turnover": presentation.turnover_leaders if presentation is not None else (),
            "institutional": (
                presentation.institutional_leaders if presentation is not None else ()
            ),
            "volume": presentation.volume_leaders if presentation is not None else (),
        }
        leaders = row_sets.get(ranking_type, ())
        self.ranking_table.setRowCount(len(leaders))
        if not leaders:
            self.ranking_empty_label.setText(
                "此欄資料不足：沒有對應值與成員覆蓋完整的題材可列入排行。"
            )
            self.ranking_empty_label.show()
        else:
            self.ranking_empty_label.hide()
        for rank, row in enumerate(leaders, start=1):
            value, available, members = self._leader_value_and_coverage(
                str(ranking_type), row
            )
            values = (
                str(rank),
                row.chain_name,
                row.theme_name,
                value,
                self._coverage(available, members),
            )
            for column, text in enumerate(values):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if column == 3:
                    item.setToolTip(self._leader_original_value(str(ranking_type), row))
                self.ranking_table.setItem(rank - 1, column, item)

    def _leader_value_and_coverage(
        self, ranking_type: str, row: ThemeDailyRow
    ) -> tuple[str, int, int]:
        coverage = row.coverage
        if ranking_type == "return":
            return (
                self._display_decimal(row.mean_return_pct, suffix=" %"),
                coverage.returns,
                coverage.members,
            )
        if ranking_type == "turnover":
            return (
                self._display_decimal(row.turnover_twd, suffix=" TWD"),
                coverage.turnover,
                coverage.members,
            )
        if ranking_type == "institutional":
            value = self._display_optional_int(row.institutional_net_shares)
            if value != "未提供":
                value += " 股"
            return value, coverage.institutional_shares, coverage.members
        if ranking_type == "volume":
            return (
                self._display_decimal(row.volume_multiple_5d, suffix=" 倍"),
                coverage.volume_history,
                coverage.members,
            )
        return "資料不足", 0, coverage.members

    def _leader_original_value(self, ranking_type: str, row: ThemeDailyRow) -> str:
        if ranking_type == "return":
            return self._decimal_tooltip(row.mean_return_pct, suffix=" %")
        if ranking_type == "turnover":
            return self._decimal_tooltip(row.turnover_twd, suffix=" TWD")
        if ranking_type == "institutional":
            value = self._integer_tooltip(row.institutional_net_shares)
            return value if value == "未提供" else value + " 股"
        if ranking_type == "volume":
            return self._decimal_tooltip(row.volume_multiple_5d, suffix=" 倍")
        return "資料不足"

    @Slot(int, int)
    def _on_leaderboard_row_clicked(self, row_index: int, _column: int) -> None:
        chain_item = self.ranking_table.item(row_index, 1)
        theme_item = self.ranking_table.item(row_index, 2)
        if chain_item is None or theme_item is None:
            return
        chain_index = self.chain_filter.findData(chain_item.text())
        if chain_index < 0:
            return
        self.chain_filter.setCurrentIndex(chain_index)
        theme_index = self.theme_filter.findText(theme_item.text())
        if theme_index < 0:
            return
        self.theme_filter.setCurrentIndex(theme_index)
        self.scroll_area.ensureWidgetVisible(self.members_group)

    @Slot(int)
    def _on_chain_changed(self, _index: int) -> None:
        if self._snapshot is None:
            return
        self._populate_theme_filter()

    @Slot(int)
    def _on_theme_changed(self, _index: int) -> None:
        self._render_selected_theme()

    def _render_selected_theme(self) -> None:
        self.metrics_table.setRowCount(0)
        self.member_table.setRowCount(0)
        index = self.theme_filter.currentIndex()
        if index <= 0 or index >= len(self._theme_options):
            self.metrics_table.setToolTip("請選擇一個題材以查看指標與成員。")
            return
        key = self._theme_options[index]
        if key is None:
            return
        row = self._rows_by_theme.get(key)
        if row is None:
            return
        coverage = row.coverage
        metrics: tuple[tuple[str, str, str, str], ...] = (
            (
                "平均日漲跌幅",
                self._display_decimal(row.mean_return_pct, suffix=" %"),
                self._coverage(coverage.returns, coverage.members),
                self._decimal_tooltip(row.mean_return_pct, suffix=" %"),
            ),
            (
                "價格成交金額（TWD）",
                self._display_decimal(row.turnover_twd),
                self._coverage(coverage.turnover, coverage.members),
                self._decimal_tooltip(row.turnover_twd),
            ),
            (
                "成交量五日倍數",
                self._display_decimal(row.volume_multiple_5d),
                self._coverage(coverage.volume_history, coverage.members),
                self._decimal_tooltip(row.volume_multiple_5d),
            ),
            (
                "法人流向淨股數",
                self._display_optional_int(row.institutional_net_shares),
                self._coverage(coverage.institutional_shares, coverage.members),
                self._integer_tooltip(row.institutional_net_shares),
            ),
            (
                "法人流向淨金額（TWD）",
                self._display_decimal(row.institutional_net_turnover_twd),
                self._coverage(coverage.institutional_amount, coverage.members),
                self._decimal_tooltip(row.institutional_net_turnover_twd),
            ),
            ("上漲／下跌／平盤家數",
             f"{row.up_count}／{row.down_count}／{row.flat_count}",
             self._coverage(coverage.returns, coverage.members), ""),
            ("法人買超／賣超／持平家數",
             f"{row.institutional_buy_count}／{row.institutional_sell_count}／{row.institutional_flat_count}",
             self._coverage(coverage.institutional_shares, coverage.members), ""),
            (
                "上漲比例",
                self._display_decimal(row.advancing_ratio, percentage=True),
                self._coverage(coverage.returns, coverage.members),
                self._decimal_tooltip(row.advancing_ratio),
            ),
            (
                "法人買超比例",
                self._display_decimal(row.institutional_buy_ratio, percentage=True),
                self._coverage(coverage.institutional_shares, coverage.members),
                self._decimal_tooltip(row.institutional_buy_ratio),
            ),
        )
        self.metrics_table.setRowCount(len(metrics))
        for row_index, (label, displayed_value, available, tooltip) in enumerate(metrics):
            for column, value in enumerate((label, displayed_value, available)):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if column == 1 and tooltip:
                    item.setToolTip(tooltip)
                self.metrics_table.setItem(row_index, column, item)

        self.member_table.setRowCount(len(row.stock_ids))
        for member_index, stock_id in enumerate(row.stock_ids):
            mapping_row = self._mapping_by_theme_stock.get((*key, stock_id))
            name = self._mapping_text(mapping_row, "stock_name")
            chain_tier = self._mapping_text(mapping_row, "chain_tier")
            basis = self._mapping_basis(mapping_row)
            for column, value in enumerate((stock_id, name, chain_tier, basis)):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.member_table.setItem(member_index, column, item)
        self.member_table.resizeRowsToContents()

    @staticmethod
    def _display_decimal(
        value, *, suffix: str = "", percentage: bool = False
    ) -> str:
        if value is None:
            return "未提供"
        format_spec = ".2%" if percentage else ",.2f"
        return format(value, format_spec) + suffix

    @staticmethod
    def _decimal_tooltip(value, *, suffix: str = "") -> str:
        return "未提供" if value is None else str(value) + suffix

    @staticmethod
    def _display_optional_int(value: int | None) -> str:
        return "未提供" if value is None else str(value)

    @staticmethod
    def _integer_tooltip(value: int | None) -> str:
        return "未提供" if value is None else str(value)

    @staticmethod
    def _mapping_text(mapping_row: object | None, field_name: str) -> str:
        if mapping_row is None:
            return "未提供"
        value = getattr(mapping_row, field_name, None)
        if value is None or not str(value).strip():
            return "未提供"
        return str(value).strip()

    @classmethod
    def _mapping_basis(cls, mapping_row: object | None) -> str:
        if mapping_row is None:
            return "未提供"
        parts = [
            cls._mapping_text(mapping_row, "assignment_method"),
            cls._mapping_text(mapping_row, "source_name"),
            cls._mapping_text(mapping_row, "source_tier"),
            cls._mapping_text(mapping_row, "evidence_note"),
        ]
        available = [part for part in parts if part != "未提供"]
        return "；".join(available) if available else "未提供"

    @staticmethod
    def _coverage(available: int, members: int) -> str:
        return f"{available} / {members} 位成員"

    @Slot(QTableWidgetItem)
    def _emit_selected_stock(self, item: QTableWidgetItem) -> None:
        if self._busy or self._closed or self._snapshot is None:
            return
        identifier_item = self.member_table.item(item.row(), 0)
        if identifier_item is None:
            return
        stock_id = identifier_item.text().strip()
        if len(stock_id) == 4 and stock_id.isascii() and stock_id.isdigit():
            self.stockSelected.emit(stock_id)

    def _render_empty(self, message: str) -> None:
        self.summary_label.setText(message)
        self.metrics_table.setRowCount(0)
        self.member_table.setRowCount(0)

    @Slot(bool)
    def _toggle_source_details(self, expanded: bool) -> None:
        self.summary_group.setVisible(expanded)
        self.source_details_button.setText(
            "收合來源與限制" if expanded else "顯示來源與限制"
        )

    def _update_controls(self) -> None:
        available = self._snapshot is not None and not self._closed
        self.open_snapshot_button.setEnabled(not self._busy and not self._closed)
        self.ranking_type_combo.setEnabled(available and not self._busy)
        self.ranking_table.setEnabled(available and not self._busy)
        self.chain_filter.setEnabled(available and not self._busy)
        self.theme_filter.setEnabled(available and not self._busy)
        self.metrics_table.setEnabled(available and not self._busy)
        self.member_table.setEnabled(available and not self._busy)
