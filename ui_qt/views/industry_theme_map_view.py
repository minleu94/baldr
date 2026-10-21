"""使用者明選的本機產業鏈／題材研究版本檢視頁。"""

from __future__ import annotations

from decimal import Decimal
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from PySide6.QtCore import Qt, QSignalBlocker, Signal, Slot
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
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
from app_module.theme_snapshot_catalog import (
    ThemeSnapshotCatalogResult,
    resolve_latest_theme_research_snapshot,
)
from ui_qt.theme import MIDNIGHT_ANALYST
from ui_qt.workers.task_worker import TaskWorker


class IndustryThemeMapView(QWidget):
    """唯讀呈現使用者選取的本機題材快照，不建立或接受研究版本。"""

    stockSelected = Signal(str)
    snapshotChanged = Signal(object)
    catalogRootSelected = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._generation = 0
        self._worker_generation: int | None = None
        self._worker: TaskWorker | None = None
        self._load_kind = "manifest"
        self._result: object = None
        self._error = ""
        self._cancelled = False
        self._busy = False
        self._closed = False
        self._snapshot: ThemeResearchSnapshot | None = None
        self._catalog_root: Path | None = None
        self._presentation: ThemeResearchPresentation | None = None
        self._ascending_presentation: ThemeResearchPresentation | None = None
        self._theme_options: list[tuple[str, str] | None] = []
        self._rows_by_theme: dict[tuple[str, str], ThemeDailyRow] = {}
        self._mapping_by_theme_stock: dict[tuple[str, str, str], object] = {}
        self._chain_directory_cards: list[QGroupBox] = []
        self._chain_directory_buttons: list[QPushButton] = []
        self._chain_directory_identity: str | None = None

        self._build_ui()
        self._render_empty("請設定題材版本目錄，或明選歷史版本。")
        self.status_label.setText(
            "尚未設定本機題材版本目錄；請選擇目錄或明選歷史版本。"
        )
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
        self.latest_snapshot_button = QPushButton("最新可讀版本")
        self.latest_snapshot_button.setObjectName("industryThemeLoadLatestButton")
        self.latest_snapshot_button.setAccessibleName("載入最新可讀價量題材版本")
        self.latest_snapshot_button.setToolTip(
            "只搜尋已設定的本機版本目錄，預設使用已完成且可讀的 price-v1 版本。"
        )
        self.latest_snapshot_button.clicked.connect(self.load_latest_snapshot)
        header.addWidget(self.latest_snapshot_button)
        self.choose_catalog_root_button = QPushButton("選擇版本目錄…")
        self.choose_catalog_root_button.setObjectName("industryThemeChooseCatalogRootButton")
        self.choose_catalog_root_button.setAccessibleName("選擇本機題材版本目錄")
        self.choose_catalog_root_button.clicked.connect(self._choose_catalog_root)
        header.addWidget(self.choose_catalog_root_button)
        self.open_snapshot_button = QPushButton("明選歷史版本…")
        self.open_snapshot_button.setObjectName("industryThemeOpenSnapshotButton")
        self.open_snapshot_button.setAccessibleName("明選題材歷史版本manifest")
        self.open_snapshot_button.setToolTip(
            "保留原 manifest 選取器，可明選 price-v1 或 flow-v2 歷史版本。"
        )
        self.open_snapshot_button.clicked.connect(self._choose_snapshot)
        header.addWidget(self.open_snapshot_button)
        self.clear_research_button = QPushButton("清除研究")
        self.clear_research_button.setObjectName("industryThemeClearResearchButton")
        self.clear_research_button.setAccessibleName("清除目前題材研究")
        self.clear_research_button.setToolTip(
            "只清除此頁目前顯示版本並停止讀取；未保存草稿會在確認後清除，"
            "已保存筆記與來源檔案不會刪除。"
        )
        self.clear_research_button.clicked.connect(self.clear_research)
        header.addWidget(self.clear_research_button)
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
        ranking_header.addWidget(QLabel("排序方向"))
        self.sorting_direction_combo = QComboBox()
        self.sorting_direction_combo.setAccessibleName("題材排行排序方向")
        self.sorting_direction_combo.addItem("由高到低", False)
        self.sorting_direction_combo.addItem("由低到高", True)
        self.sorting_direction_combo.currentIndexChanged.connect(
            self._render_leaderboard
        )
        ranking_header.addWidget(self.sorting_direction_combo)
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
            "此表只整理欄位覆蓋完整的觀察值，不形成策略結論；低值不自動代表下跌或法人賣超。"
            "點選題材可定位原成員。"
        )
        self.ranking_note.setWordWrap(True)
        self.ranking_note.setTextFormat(Qt.TextFormat.PlainText)
        self.ranking_note.setStyleSheet(f"color: {MIDNIGHT_ANALYST.text_secondary};")
        ranking_layout.addWidget(self.ranking_note)
        content_layout.addWidget(self.ranking_group)

        self.chain_directory_button = QPushButton("瀏覽產業鏈目錄（展開）")
        self.chain_directory_button.setObjectName("industryThemeChainDirectoryButton")
        self.chain_directory_button.setAccessibleName("展開或收合產業鏈卡片目錄")
        self.chain_directory_button.setCheckable(True)
        self.chain_directory_button.setChecked(False)
        self.chain_directory_button.toggled.connect(self._toggle_chain_directory)
        content_layout.addWidget(self.chain_directory_button)

        self.chain_directory_group = QGroupBox("產業鏈卡片目錄")
        self.chain_directory_group.setObjectName("industryThemeChainDirectoryGroup")
        self.chain_directory_group.setVisible(False)
        directory_layout = QVBoxLayout(self.chain_directory_group)
        self.chain_directory_note = QLabel(
            "每條鏈列題材名稱序前三個捷徑；名稱序不是表現排行。"
            "完整題材仍可使用下方產業鏈與題材篩選。"
        )
        self.chain_directory_note.setAccessibleName("產業鏈目錄排序說明")
        self.chain_directory_note.setWordWrap(True)
        self.chain_directory_note.setTextFormat(Qt.TextFormat.PlainText)
        directory_layout.addWidget(self.chain_directory_note)
        self.chain_directory_cards_widget = QWidget(self.chain_directory_group)
        self.chain_directory_cards_layout = QGridLayout(self.chain_directory_cards_widget)
        self.chain_directory_cards_layout.setContentsMargins(0, 0, 0, 0)
        self.chain_directory_cards_layout.setHorizontalSpacing(8)
        self.chain_directory_cards_layout.setVerticalSpacing(8)
        directory_layout.addWidget(self.chain_directory_cards_widget)
        content_layout.addWidget(self.chain_directory_group)

        self.source_details_button = QPushButton("顯示來源與限制")
        self.source_details_button.setObjectName("industryThemeSourceDetailsButton")
        self.source_details_button.setAccessibleName("顯示或收合題材來源與限制")
        self.source_details_button.setCheckable(True)
        self.source_details_button.toggled.connect(self._toggle_source_details)
        content_layout.addWidget(self.source_details_button)
        content_layout.addWidget(self.summary_group)

        self.filter_group = QGroupBox("選擇產業鏈、題材與股票")
        filter_layout = QVBoxLayout(self.filter_group)
        selector_layout = QHBoxLayout()
        self.chain_filter = QComboBox()
        self.chain_filter.setAccessibleName("產業鏈篩選")
        self.chain_filter.currentIndexChanged.connect(self._on_chain_changed)
        self.theme_filter = QComboBox()
        self.theme_filter.setAccessibleName("題材篩選")
        self.theme_filter.currentIndexChanged.connect(self._on_theme_changed)
        self.chain_filter.setMinimumWidth(0)
        self.theme_filter.setMinimumWidth(0)
        selector_layout.addWidget(QLabel("產業鏈"))
        selector_layout.addWidget(self.chain_filter, 1)
        selector_layout.addWidget(QLabel("題材"))
        selector_layout.addWidget(self.theme_filter, 2)
        filter_layout.addLayout(selector_layout)

        lookup_layout = QHBoxLayout()
        lookup_layout.addWidget(QLabel("股票反查"))
        self.stock_lookup_input = QLineEdit()
        self.stock_lookup_input.setObjectName("industryThemeStockLookupInput")
        self.stock_lookup_input.setAccessibleName("股票代號或名稱搜尋")
        self.stock_lookup_input.setPlaceholderText("完整四碼代號或公司名稱片段")
        self.stock_lookup_input.setMinimumWidth(0)
        self.stock_lookup_input.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed
        )
        self.stock_lookup_input.textChanged.connect(self._search_stock_lookup)
        lookup_layout.addWidget(self.stock_lookup_input, 2)

        self.stock_lookup_results = QComboBox()
        self.stock_lookup_results.setObjectName("industryThemeStockLookupResults")
        self.stock_lookup_results.setAccessibleName("明選股票反查結果與題材")
        self.stock_lookup_results.setMinimumWidth(0)
        self.stock_lookup_results.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed
        )
        self.stock_lookup_results.addItem("請輸入代號或名稱", None)
        self.stock_lookup_results.currentIndexChanged.connect(
            self._on_stock_lookup_result_changed
        )
        lookup_layout.addWidget(self.stock_lookup_results, 3)

        self.stock_lookup_locate_button = QPushButton("定位所選股票")
        self.stock_lookup_locate_button.setObjectName(
            "industryThemeStockLookupLocateButton"
        )
        self.stock_lookup_locate_button.setAccessibleName("定位明選股票題材與成員")
        self.stock_lookup_locate_button.clicked.connect(
            self._locate_selected_stock_lookup_result
        )
        lookup_layout.addWidget(self.stock_lookup_locate_button)
        filter_layout.addLayout(lookup_layout)

        self.stock_lookup_status_label = QLabel(
            "尚未載入版本；請先選取本機研究版本。"
        )
        self.stock_lookup_status_label.setObjectName(
            "industryThemeStockLookupStatus"
        )
        self.stock_lookup_status_label.setAccessibleName("股票反查狀態")
        self.stock_lookup_status_label.setWordWrap(True)
        self.stock_lookup_status_label.setTextFormat(Qt.TextFormat.PlainText)
        filter_layout.addWidget(self.stock_lookup_status_label)
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

    def _choose_catalog_root(self) -> None:
        if self._closed or self._busy:
            return
        selected = QFileDialog.getExistingDirectory(
            self,
            "選擇本機題材版本目錄",
            str(self._catalog_root) if self._catalog_root is not None else "",
        )
        if not selected:
            return
        previous_root = self._catalog_root
        selected_root = Path(selected).resolve()
        self.configure_catalog_root(selected_root)
        if self.load_latest_snapshot():
            self.catalogRootSelected.emit(selected_root)
        else:
            self.configure_catalog_root(previous_root)

    def configure_catalog_root(self, root: Path | None) -> None:
        """設定由主視窗提供的本機版本根目錄；此處不列舉或讀取檔案。"""

        if root is not None and not isinstance(root, Path):
            raise TypeError("root 必須是 pathlib.Path 或 None")
        self._catalog_root = root
        if root is None and self._snapshot is None and not self._busy:
            self.status_label.setText(
                "尚未設定本機題材版本目錄；請選擇目錄或明選歷史版本。"
            )
        self._update_controls()

    def load_latest_snapshot(self) -> bool:
        """在明示的本機目錄尋找最新可讀價量版本；不建立或改寫版本。"""

        if self._closed or self._busy:
            return False
        if self._catalog_root is None:
            self.status_label.setText(
                "尚未設定本機題材版本目錄；請選擇目錄，或明選歷史版本。"
            )
            return False
        return self._start_snapshot_load(
            resolve_latest_theme_research_snapshot,
            self._catalog_root,
            kwargs={
                "known_at": datetime.now(timezone.utc),
                "schema": "price-v1",
            },
            load_kind="catalog",
            status="正在已設定的本機目錄尋找最新可讀 price-v1；舊版本已清除。",
        )

    def load_snapshot(
        self,
        path: Path,
        *,
        expected_identity_sha256: str | None = None,
    ) -> None:
        """背景讀取指定 manifest；新讀取開始即清除舊版本可操作狀態。"""

        if not isinstance(path, Path):
            raise TypeError("path 必須是 pathlib.Path")
        if expected_identity_sha256 is not None and not isinstance(
            expected_identity_sha256, str
        ):
            raise TypeError("expected_identity_sha256 必須是字串或 None")

        kwargs = (
            {"expected_identity_sha256": expected_identity_sha256}
            if expected_identity_sha256 is not None
            else {}
        )
        self._start_snapshot_load(
            read_theme_research_snapshot,
            path,
            kwargs=kwargs,
            load_kind="manifest",
            status="正在讀取明選的本機研究版本；舊版本已清除。",
        )

    def _confirm_load_replacement(self) -> tuple[QPlainTextEdit | None, str] | None:
        """確認版本切換不會靜默丟棄忙碌中的筆記或未保存草稿。"""

        notes_widget, notes_editor = self._notes_editor_context()
        notes_is_busy = (
            getattr(notes_widget, "is_busy", None) if notes_widget is not None else None
        )
        if callable(notes_is_busy) and notes_is_busy():
            self.status_label.setText("題材筆記工作進行中；完成後再切換研究版本。")
            return None
        draft = notes_editor.toPlainText() if notes_editor is not None else ""
        original_generation = self._generation
        original_snapshot = self._snapshot
        original_worker = self._worker
        if draft:
            answer = QMessageBox.question(
                self,
                "切換題材版本",
                "切換版本會清除此頁未保存的題材研究草稿；已保存筆記與來源檔案不會更動。要繼續嗎？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                self.status_label.setText("已取消版本切換；目前版本與未保存草稿仍保留。")
                return None
        if (
            self._closed
            or self._busy
            or self._generation != original_generation
            or self._snapshot is not original_snapshot
            or self._worker is not original_worker
            or (notes_editor is not None and notes_editor.toPlainText() != draft)
            or (callable(notes_is_busy) and notes_is_busy())
        ):
            self.status_label.setText("研究或筆記工作已改變；未執行先前的版本切換。")
            return None
        return notes_editor, draft

    def _start_snapshot_load(
        self,
        task_function: Callable[..., object],
        *args: object,
        kwargs: dict[str, object],
        load_kind: str,
        status: str,
    ) -> bool:
        if self._closed or self._busy:
            return False
        confirmed = self._confirm_load_replacement()
        if confirmed is None:
            return False
        notes_editor, draft = confirmed

        self._generation += 1
        generation = self._generation
        self._snapshot = None
        self._result = None
        self._error = ""
        self._cancelled = False
        self._clear_snapshot_view()
        self.snapshotChanged.emit(None)
        self._busy = True
        self.status_label.setText(status)
        self._update_controls()
        worker = TaskWorker(task_function, *args, **kwargs)
        self._worker = worker
        self._worker_generation = generation
        self._load_kind = load_kind
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
        self._update_controls()
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
            return False
        if notes_editor is not None and draft and notes_editor.toPlainText() == draft:
            notes_editor.clear()
        return True

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

    def _notes_editor_context(self) -> tuple[QWidget | None, QPlainTextEdit | None]:
        editor = self.findChild(QPlainTextEdit, "themeResearchNoteEditor")
        if editor is None:
            return None, None
        candidate: QWidget | None = editor
        while candidate is not None and candidate is not self:
            if callable(getattr(candidate, "is_busy", None)):
                return candidate, editor
            candidate = candidate.parentWidget()
        return None, editor

    def clear_research(self) -> bool:
        """清除目前呈現與未保存草稿；不刪除來源或已保存筆記。"""

        if self._closed:
            return False
        has_current_load = (
            self._worker is not None
            and self._worker_generation == self._generation
        )
        if self._snapshot is None and not has_current_load:
            return False

        notes_widget, notes_editor = self._notes_editor_context()
        notes_is_busy = (
            getattr(notes_widget, "is_busy", None) if notes_widget is not None else None
        )
        if callable(notes_is_busy) and notes_is_busy():
            self.status_label.setText(
                "題材筆記工作進行中；請等待完成後再清除研究。"
            )
            return False

        has_unsaved_draft = (
            notes_editor is not None and bool(notes_editor.toPlainText())
        )
        original_generation = self._generation
        original_snapshot = self._snapshot
        original_worker = self._worker
        if has_unsaved_draft:
            answer = QMessageBox.question(
                self,
                "清除研究",
                "只清除此頁目前顯示的題材研究。尚未保存的研究草稿會一併清除；"
                "已保存筆記與來源檔案不會刪除。要繼續嗎？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                self.status_label.setText(
                    "已取消清除；目前研究版本與未保存草稿仍保留。"
                )
                return False

        if (self._closed or self._generation != original_generation
            or self._snapshot is not original_snapshot or self._worker is not original_worker
            or callable(notes_is_busy) and notes_is_busy()):
            self.status_label.setText("研究或筆記工作已改變；未執行先前的清除確認。")
            return False

        worker = self._worker
        self._generation += 1
        self._snapshot = None
        self._result = None
        self._error = ""
        self._cancelled = False
        self._clear_snapshot_view()
        ranking_blockers = [
            QSignalBlocker(self.ranking_type_combo),
            QSignalBlocker(self.sorting_direction_combo),
        ]
        self.ranking_type_combo.setCurrentIndex(0)
        self.sorting_direction_combo.setCurrentIndex(
            self.sorting_direction_combo.findData(False)
        )
        del ranking_blockers
        self.snapshotChanged.emit(None)
        if notes_editor is not None and notes_editor.toPlainText():
            notes_editor.clear()

        if worker is not None:
            worker.cancel(cooperative=True, wait=False)
            self._busy = True
            self.status_label.setText(
                "研究已清除；正在合作式停止背景讀取，完成前不能載入其他版本。"
            )
        else:
            self._busy = False
            self.status_label.setText("研究版本已清除。")
        self._update_controls()
        return True

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
        load_kind = self._load_kind
        self._worker = None
        self._worker_generation = None
        self._busy = False
        try:
            if self._closed:
                return
            if generation != self._generation:
                if self._snapshot is not None:
                    self.status_label.setText("已載入所選本機研究版本。")
                elif not self._closed:
                    self.status_label.setText("研究版本已清除；背景讀取已停止。")
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
                if load_kind == "catalog" and isinstance(
                    result, ThemeSnapshotCatalogResult
                ):
                    entry = result.selected
                    if entry is None:
                        self._snapshot = None
                        self._clear_snapshot_view()
                        if result.limited:
                            reason = result.limit_reason or "搜尋範圍未能完整核實"
                            message = (
                                "未宣稱最新版本：有界搜尋已停止（"
                                + reason
                                + "）。可縮小已選目錄或明選歷史版本。"
                            )
                        elif result.rejections:
                            rejection = result.rejections[0]
                            message = (
                                "目前目錄沒有可讀的 price-v1 版本；首項拒絕："
                                f"{rejection.path.name}（{rejection.reason}）。"
                                "可檢查來源完整性，或明選其他歷史版本。"
                            )
                        else:
                            message = (
                                "目前目錄沒有可讀的 price-v1 版本；"
                                "可檢查合法版本，或明選歷史版本。"
                            )
                        self.status_label.setText(message)
                        self.snapshotChanged.emit(None)
                        return
                    snapshot = entry.snapshot
                    if not isinstance(snapshot, ThemeResearchSnapshot):
                        raise TypeError("catalog entry 未回傳 ThemeResearchSnapshot")
                    self._snapshot = snapshot
                    self._apply_snapshot(snapshot)
                    self.snapshotChanged.emit(snapshot)
                    skipped = len(result.rejections)
                    suffix = f"；拒絕候選 {skipped} 項" if skipped else ""
                    self.status_label.setText(
                        f"已載入最新可讀 price-v1（資料日 {entry.data_date.isoformat()}）{suffix}。"
                    )
                else:
                    self._snapshot = None
                    self._clear_snapshot_view()
                    self.status_label.setText(
                        "題材版本讀取失敗；讀者未回傳 ThemeResearchSnapshot。"
                    )
                    self.snapshotChanged.emit(None)
                    return
            else:
                self._snapshot = result
                self._apply_snapshot(result)
                self.snapshotChanged.emit(result)
                self.status_label.setText("已載入明選的本機研究版本。")
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
            "institutional_tpex_diagnostics_only": "僅上櫃三大法人股數診斷",
            "non_tpex_members_excluded": "上市、興櫃與未知市場未納入法人數值",
            "institutional_selected_member_not_found": "部分上櫃成員缺此日法人原列",
            "institutional_date_mismatch": "法人原列日期不符，未借用其他日",
            "no_selected_members": "沒有符合此次來源的上櫃成員",
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
            f"映射版本：{report.mapping_snapshot_date}　｜　"
            "用途：本機目前研究／題材價量觀察，不代表官方來源接受或歷史 PIT",
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
        self._ascending_presentation = None
        self._rows_by_theme = {}
        self._mapping_by_theme_stock = {}
        self._clear_chain_directory()
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
        self._clear_stock_lookup()
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

    def _clear_stock_lookup(self) -> None:
        input_blocker = QSignalBlocker(self.stock_lookup_input)
        self.stock_lookup_input.clear()
        del input_blocker
        result_blocker = QSignalBlocker(self.stock_lookup_results)
        self.stock_lookup_results.clear()
        self.stock_lookup_results.addItem("請輸入代號或名稱", None)
        del result_blocker
        if self._closed:
            message = "頁面已關閉；股票反查已停用。"
        elif self._busy:
            message = "版本讀取中；舊搜尋結果已清除。"
        elif self._snapshot is None:
            message = "尚未載入版本；請先選取本機研究版本。"
        else:
            message = "已載入本機版本；代號需完整四碼，名稱可輸入片段。"
        self.stock_lookup_status_label.setText(message)

    @staticmethod
    def _stock_lookup_selection(value: object) -> tuple[str, str, str, str] | None:
        if not isinstance(value, (tuple, list)) or len(value) != 4:
            return None
        if any(type(item) is not str for item in value):
            return None
        return (value[0], value[1], value[2], value[3])

    @Slot(str)
    def _search_stock_lookup(self, query: str) -> None:
        blocker = QSignalBlocker(self.stock_lookup_results)
        self.stock_lookup_results.clear()
        self.stock_lookup_results.addItem("請明選一筆搜尋結果", None)
        del blocker

        if self._closed:
            self.stock_lookup_status_label.setText("頁面已關閉；股票反查已停用。")
            self._update_controls()
            return
        if self._busy:
            self.stock_lookup_status_label.setText("版本讀取中；股票反查暫停。")
            self._update_controls()
            return
        snapshot = self._snapshot
        if snapshot is None:
            self.stock_lookup_status_label.setText("請先選取本機研究版本。")
            self._update_controls()
            return

        normalized = query.strip()
        if not normalized:
            self.stock_lookup_status_label.setText(
                "請輸入完整四碼代號，或輸入公司名稱片段。"
            )
            self._update_controls()
            return

        mapping_items = sorted(
            self._mapping_by_theme_stock.items(),
            key=lambda item: (
                item[0][2],
                item[0][0].casefold(),
                item[0][1].casefold(),
            ),
        )
        if normalized.isnumeric():
            if not normalized.isascii() or not normalized.isdigit() or len(normalized) != 4:
                self.stock_lookup_status_label.setText(
                    "股票代號請輸入完整四碼半形數字；不做代號模糊比對。"
                )
                self._update_controls()
                return
            matches = [
                (key, mapping_row)
                for key, mapping_row in mapping_items
                if key[2] == normalized
            ]
        else:
            needle = normalized.casefold()
            matches = []
            for key, mapping_row in mapping_items:
                name = getattr(mapping_row, "stock_name", None)
                if type(name) is str and name.strip() and needle in name.casefold():
                    matches.append((key, mapping_row))

        if not matches:
            self.stock_lookup_status_label.setText(
                "沒有符合的本機映射；請確認代號完整或改用名稱片段。"
            )
            self._update_controls()
            return

        for key, mapping_row in matches:
            chain_name, theme_name, stock_id = key
            stock_name = self._mapping_text(mapping_row, "stock_name")
            chain_tier = self._mapping_text(mapping_row, "chain_tier")
            label = (
                f"{stock_id}｜{stock_name}｜{chain_name}／{theme_name}｜{chain_tier}"
            )
            self.stock_lookup_results.addItem(
                label,
                (snapshot.identity_sha256, stock_id, chain_name, theme_name),
            )
        self.stock_lookup_status_label.setText(
            f"找到 {len(matches)} 筆本機映射；請明選股票及其產業鏈／題材。"
        )
        self._update_controls()

    @Slot(int)
    def _on_stock_lookup_result_changed(self, _index: int) -> None:
        selected = self._stock_lookup_selection(
            self.stock_lookup_results.currentData(Qt.ItemDataRole.UserRole)
        )
        snapshot = self._snapshot
        if selected is not None and snapshot is not None:
            if selected[0] != snapshot.identity_sha256:
                self.stock_lookup_status_label.setText(
                    "所選搜尋結果屬於其他版本；請重新搜尋。"
                )
            else:
                self.stock_lookup_status_label.setText(
                    "已明選一筆股票／題材；按「定位所選股票」查看成員。"
                )
        self._update_controls()

    @Slot()
    def _locate_selected_stock_lookup_result(self) -> None:
        snapshot = self._snapshot
        if self._closed or self._busy or snapshot is None:
            return
        selected = self._stock_lookup_selection(
            self.stock_lookup_results.currentData(Qt.ItemDataRole.UserRole)
        )
        if selected is None:
            self.stock_lookup_status_label.setText("請先明確選擇一筆股票反查結果。")
            self._update_controls()
            return
        identity, stock_id, chain_name, theme_name = selected
        if identity != snapshot.identity_sha256:
            self.stock_lookup_status_label.setText(
                "所選搜尋結果屬於其他版本；沒有定位，請重新搜尋。"
            )
            return
        if (chain_name, theme_name, stock_id) not in self._mapping_by_theme_stock:
            self.stock_lookup_status_label.setText(
                "所選結果不在目前版本映射中；沒有定位，請重新搜尋。"
            )
            return

        chain_index = self.chain_filter.findData(chain_name)
        if chain_index < 0:
            self.stock_lookup_status_label.setText(
                "目前版本找不到所選產業鏈；沒有定位。"
            )
            return
        self.chain_filter.setCurrentIndex(chain_index)
        theme_index = self.theme_filter.findText(theme_name)
        if theme_index < 0:
            self.stock_lookup_status_label.setText(
                "目前版本找不到所選題材；沒有定位。"
            )
            return
        self.theme_filter.setCurrentIndex(theme_index)

        identifier_item = next(
            (
                self.member_table.item(row, 0)
                for row in range(self.member_table.rowCount())
                if self.member_table.item(row, 0) is not None
                and self.member_table.item(row, 0).text() == stock_id
            ),
            None,
        )
        if identifier_item is None:
            self.stock_lookup_status_label.setText(
                "所選股票不在該題材成員表；沒有定位。"
            )
            return
        self.scroll_area.ensureWidgetVisible(self.members_group, 0, 0)
        self.member_table.setCurrentItem(identifier_item)
        self.member_table.selectRow(identifier_item.row())
        self.member_table.scrollToItem(
            identifier_item, QAbstractItemView.ScrollHint.PositionAtCenter
        )
        self.scroll_area.ensureWidgetVisible(self.member_table, 0, 0)
        self.stock_lookup_status_label.setText(
            f"已定位 {stock_id}｜{chain_name}／{theme_name}；雙擊成員列可開啟個股。"
        )

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
        self._render_chain_directory()
        self._render_leaderboard()

    def _clear_chain_directory(self) -> None:
        self._chain_directory_identity = None
        for button in self._chain_directory_buttons:
            button.setEnabled(False)
            button.hide()
        self._chain_directory_buttons.clear()
        self._chain_directory_cards.clear()
        while self.chain_directory_cards_layout.count():
            item = self.chain_directory_cards_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setEnabled(False)
                widget.hide()
                widget.deleteLater()
        self.chain_directory_group.setVisible(False)
        blocker = QSignalBlocker(self.chain_directory_button)
        self.chain_directory_button.setChecked(False)
        del blocker
        self.chain_directory_button.setText("瀏覽產業鏈目錄（展開）")

    def _render_chain_directory(self) -> None:
        presentation = self._presentation
        snapshot = self._snapshot
        if presentation is None or snapshot is None or self._closed:
            self._clear_chain_directory()
            return

        self._clear_chain_directory()
        self._chain_directory_identity = snapshot.identity_sha256
        for chain_index, directory in enumerate(presentation.chains):
            themes = tuple(sorted(set(directory.themes)))
            card = QGroupBox(directory.chain_name, self.chain_directory_cards_widget)
            card.setObjectName("industryThemeChainDirectoryCard")
            card.setMinimumWidth(0)
            card.setSizePolicy(
                QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
            )
            card_layout = QVBoxLayout(card)
            metadata = QLabel(
                f"{len(themes)} 個題材　｜　"
                f"{len(set(directory.stock_ids))} 檔不重複成員"
            )
            metadata.setAccessibleName(f"{directory.chain_name}題材與成員數")
            metadata.setWordWrap(True)
            card_layout.addWidget(metadata)

            for theme_name in themes[:3]:
                key = (directory.chain_name, theme_name)
                row = self._rows_by_theme.get(key)
                button = QPushButton(theme_name)
                button.setObjectName("industryThemeChainDirectoryShortcut")
                button.setAccessibleName(
                    f"{directory.chain_name}／{theme_name}題材捷徑"
                )
                button.setMinimumWidth(0)
                button.setSizePolicy(
                    QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
                )
                if row is not None:
                    button.setToolTip(self._chain_directory_shortcut_tooltip(row))
                value_label = QLabel(self._chain_directory_shortcut_text(row))
                value_label.setAccessibleName(
                    f"{directory.chain_name}／{theme_name}漲跌觀察與覆蓋"
                )
                value_label.setWordWrap(True)
                value_label.setTextFormat(Qt.TextFormat.PlainText)
                if row is not None:
                    value_label.setToolTip(self._chain_directory_shortcut_tooltip(row))
                button.setProperty("themeSnapshotIdentity", snapshot.identity_sha256)
                button.setProperty("themeChainName", directory.chain_name)
                button.setProperty("themeName", theme_name)
                button.clicked.connect(self._on_chain_directory_shortcut_clicked)
                card_layout.addWidget(button)
                card_layout.addWidget(value_label)
                self._chain_directory_buttons.append(button)

            row_index, column_index = divmod(chain_index, 2)
            self.chain_directory_cards_layout.addWidget(
                card, row_index, column_index
            )
            self._chain_directory_cards.append(card)

        self._update_chain_directory_controls()

    def _chain_directory_shortcut_text(self, row: ThemeDailyRow | None) -> str:
        if row is None:
            return "平均日漲跌幅：未提供｜題材報表列未提供"
        coverage = row.coverage
        value = row.mean_return_pct
        if (
            coverage.members > 0
            and coverage.returns == coverage.members
            and type(value) is Decimal
            and value.is_finite()
        ):
            displayed = self._display_decimal(value, suffix=" %")
        else:
            displayed = "漲跌未提供"
        return (
            f"平均日漲跌幅：{displayed}｜"
            f"{self._coverage(coverage.returns, coverage.members)}"
        )

    @staticmethod
    def _chain_directory_shortcut_tooltip(row: ThemeDailyRow) -> str:
        coverage = row.coverage
        value = row.mean_return_pct
        if (
            coverage.members > 0
            and coverage.returns == coverage.members
            and type(value) is Decimal
            and value.is_finite()
        ):
            return IndustryThemeMapView._decimal_tooltip(value, suffix=" %")
        return (
            "漲跌未提供；沒有用其他來源或日期補值。\n"
            f"原始覆蓋：{IndustryThemeMapView._coverage(coverage.returns, coverage.members)}"
        )

    @Slot(bool)
    def _toggle_chain_directory(self, expanded: bool) -> None:
        if self._closed or self._busy or self._snapshot is None:
            expanded = False
            blocker = QSignalBlocker(self.chain_directory_button)
            self.chain_directory_button.setChecked(False)
            del blocker
        self.chain_directory_group.setVisible(expanded)
        self.chain_directory_button.setText(
            "瀏覽產業鏈目錄（收合）" if expanded else "瀏覽產業鏈目錄（展開）"
        )

    def _update_chain_directory_controls(self) -> None:
        available = self._snapshot is not None and not self._closed and not self._busy
        self.chain_directory_button.setEnabled(available)
        for button in self._chain_directory_buttons:
            button.setEnabled(available)
        self.chain_directory_group.setEnabled(available)

    @Slot()
    def _on_chain_directory_shortcut_clicked(self) -> None:
        button = self.sender()
        if not isinstance(button, QPushButton):
            return
        identity = button.property("themeSnapshotIdentity")
        chain_name = button.property("themeChainName")
        theme_name = button.property("themeName")
        if not all(type(value) is str for value in (identity, chain_name, theme_name)):
            return
        self._open_chain_directory_theme(identity, chain_name, theme_name)

    def _open_chain_directory_theme(
        self, identity: str, chain_name: str, theme_name: str
    ) -> None:
        snapshot = self._snapshot
        presentation = self._presentation
        if (
            self._closed
            or self._busy
            or snapshot is None
            or presentation is None
            or identity != snapshot.identity_sha256
            or self._chain_directory_identity != snapshot.identity_sha256
        ):
            return
        directory = next(
            (item for item in presentation.chains if item.chain_name == chain_name),
            None,
        )
        if (
            directory is None
            or theme_name not in directory.themes
            or (chain_name, theme_name) not in self._rows_by_theme
        ):
            return
        chain_index = self.chain_filter.findData(chain_name)
        if chain_index < 0:
            return
        self.chain_filter.setCurrentIndex(chain_index)
        theme_index = self.theme_filter.findText(theme_name)
        if theme_index < 0:
            return
        self.theme_filter.setCurrentIndex(theme_index)
        self.chain_directory_button.setChecked(False)
        self.scroll_area.ensureWidgetVisible(self.metrics_group, 0, 0)
        self.scroll_area.ensureWidgetVisible(self.members_group, 0, 0)

    def _render_leaderboard(self, _index: int = -1) -> None:
        presentation = self._presentation
        if presentation is None or self._snapshot is None:
            self.ranking_table.setRowCount(0)
            self.ranking_empty_label.setText("尚未載入題材觀察排行。")
            self.ranking_empty_label.show()
            return
        if self.sorting_direction_combo.currentData() is True:
            ascending_presentation = self._ascending_presentation
            if ascending_presentation is None:
                try:
                    ascending_presentation = build_theme_research_presentation(
                        self._snapshot,
                        ascending=True,
                    )
                except Exception as exc:
                    self.ranking_table.setRowCount(0)
                    self.ranking_empty_label.setText(
                        "低值觀察排序無法產生；沒有沿用舊排行。"
                    )
                    self.ranking_empty_label.show()
                    first_line = str(exc).splitlines()[0] if str(exc).splitlines() else ""
                    self.status_label.setText(
                        f"低值觀察排序失敗；沒有沿用舊排行：{first_line}"
                    )
                    return
                self._ascending_presentation = ascending_presentation
            presentation = ascending_presentation
        ranking_type = self.ranking_type_combo.currentData()
        row_sets = {
            "return": presentation.return_leaders,
            "turnover": presentation.turnover_leaders,
            "institutional": presentation.institutional_leaders,
            "volume": presentation.volume_leaders,
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
                ("法人淨股數（已覆蓋成員合計）" if 0 < coverage.institutional_shares < coverage.members else "法人流向淨股數"),
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
             (f"{row.up_count}／{row.down_count}／{row.flat_count}" if coverage.returns else "未提供"),
             self._coverage(coverage.returns, coverage.members), ""),
            (("法人買超／賣超／持平家數（已覆蓋成員）" if 0 < coverage.institutional_shares < coverage.members else "法人買超／賣超／持平家數"),
             (f"{row.institutional_buy_count}／{row.institutional_sell_count}／{row.institutional_flat_count}" if coverage.institutional_shares else "未提供"),
             self._coverage(coverage.institutional_shares, coverage.members), ""),
            (
                "上漲比例",
                self._display_decimal(row.advancing_ratio, percentage=True),
                self._coverage(coverage.returns, coverage.members),
                self._decimal_tooltip(row.advancing_ratio),
            ),
            (
                ("法人買超比例（已覆蓋成員）" if 0 < coverage.institutional_shares < coverage.members else "法人買超比例"),
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
        lookup_available = available and not self._busy
        self.latest_snapshot_button.setEnabled(
            self._catalog_root is not None and not self._busy and not self._closed
        )
        self.choose_catalog_root_button.setEnabled(not self._busy and not self._closed)
        self.open_snapshot_button.setEnabled(not self._busy and not self._closed)
        has_current_load = (
            self._worker is not None
            and self._worker_generation == self._generation
        )
        self.clear_research_button.setEnabled(
            not self._closed and (self._snapshot is not None or has_current_load)
        )
        self.source_details_button.setEnabled(available and not self._busy)
        self.ranking_type_combo.setEnabled(available and not self._busy)
        self.sorting_direction_combo.setEnabled(available and not self._busy)
        self.ranking_table.setEnabled(available and not self._busy)
        self.chain_filter.setEnabled(available and not self._busy)
        self.theme_filter.setEnabled(available and not self._busy)
        self.metrics_table.setEnabled(available and not self._busy)
        self.member_table.setEnabled(available and not self._busy)
        self.stock_lookup_input.setEnabled(lookup_available)
        self.stock_lookup_results.setEnabled(
            lookup_available and self.stock_lookup_results.count() > 1
        )
        self.stock_lookup_locate_button.setEnabled(
            lookup_available
            and self._stock_lookup_selection(
                self.stock_lookup_results.currentData(Qt.ItemDataRole.UserRole)
            )
            is not None
        )
        self._update_chain_directory_controls()
        if self._closed:
            self.stock_lookup_status_label.setText(
                "頁面已關閉；股票反查已停用。"
            )
        elif self._busy:
            self.stock_lookup_status_label.setText(
                "版本讀取中；舊搜尋結果已清除，反查暫停。"
            )
        elif self._snapshot is None:
            self.stock_lookup_status_label.setText(
                "尚未載入版本；請先選取本機研究版本。"
            )
        elif (
            not self.stock_lookup_input.text().strip()
            and self.stock_lookup_results.count() == 1
            and "讀取中" in self.stock_lookup_status_label.text()
        ):
            self.stock_lookup_status_label.setText(
                "已載入本機版本；代號需完整四碼，名稱可輸入片段。"
            )
