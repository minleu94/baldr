"""使用者明選的本機產業鏈／題材研究版本檢視頁。"""

from __future__ import annotations

from decimal import Decimal
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QEvent, QObject, QRect, Qt, QSignalBlocker, Signal, Slot
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSplitter,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from app_module.theme_daily_service import ThemeDailyRow
from app_module.theme_research_presentation import (
    ThemeResearchPresentation,
    ThemeReturnVersionObservation,
    ThemeTurnoverTile,
    ThemeReturnTwoVersionPresentation,
    build_theme_return_two_version_presentation,
    build_theme_research_presentation,
)
from app_module.theme_classification_presentation import (
    ThemeClassificationMember,
    ThemeClassificationPresentation,
    build_theme_classification_presentation,
)
from app_module.theme_overlap_presentation import (
    build_theme_overlap_presentation,
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
from ui_qt.views.theme_member_navigation import ThemeMemberNavigation
from ui_qt.workers.task_worker import TaskWorker
from ui_qt.widgets.observation_bar_delegate import (
    ObservationBarDelegate,
    OBSERVATION_DIRECTIONAL_ROLE,
    OBSERVATION_VALUE_ROLE,
)


def _read_theme_comparison_pair(
    first_path: Path, second_path: Path,
) -> tuple[ThemeResearchSnapshot, ThemeResearchSnapshot]:
    """各自經既有 reader 驗讀使用者明選的兩個 manifest。"""
    first = read_theme_research_snapshot(first_path)
    second = read_theme_research_snapshot(second_path)
    return first, second


class IndustryThemeMapView(QWidget):
    """唯讀呈現使用者選取的本機題材快照，不建立或接受研究版本。"""

    _MAX_TURNOVER_AREA_TILES = 20
    _MEMBER_PAGE_SIZE = 50

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
        self._member_stock_ids: tuple[str, ...] = ()
        self._member_row_by_stock_id: dict[str, int] = {}
        self._member_l1_filter_stock_ids: tuple[str, ...] | None = None
        self._member_l1_filter_label: str | None = None
        self._classification_l1_filter_buttons: list[QPushButton] = []
        self._classification_l1_active_filter_button: QPushButton | None = None
        self._classification_l1_reset_button: QPushButton | None = None
        self._classification_members_base_status: str | None = None
        self._member_theme_key: tuple[str, str] | None = None
        self._member_snapshot_identity: str | None = None
        self._member_page_index = 0
        self._chain_directory_cards: list[QGroupBox] = []
        self._chain_directory_buttons: list[QPushButton] = []
        self._chain_directory_identity: str | None = None
        self._return_tile_buttons: dict[tuple[str, str], QPushButton] = {}
        self._return_tile_identity: str | None = None
        self._turnover_treemap_buttons: dict[tuple[str, str], QPushButton] = {}
        self._turnover_zero_buttons: dict[tuple[str, str], QPushButton] = {}
        self._turnover_tiles_by_key: dict[tuple[str, str], ThemeTurnoverTile] = {}
        self._turnover_treemap_identity: str | None = None
        self._comparison_generation = 0
        self._comparison_worker: TaskWorker | None = None
        self._comparison_worker_generation: int | None = None
        self._comparison_result: object = None
        self._comparison_error = ""
        self._comparison_paths: tuple[Path, Path] | None = None
        self._comparison_snapshots: tuple[ThemeResearchSnapshot, ThemeResearchSnapshot] | None = None
        self._comparison_presentation: ThemeReturnTwoVersionPresentation | None = None
        self._navigation_selection_revision = 0

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

    def capture_selected_member_navigation(
        self, expected_stock_code: str | None = None
    ) -> ThemeMemberNavigation | None:
        """只擷取目前已載快照、題材列及實際選取成員，不拼接搜尋結果。"""

        snapshot = self._snapshot
        if self._closed or self._busy or snapshot is None:
            return None
        theme_index = self.theme_filter.currentIndex()
        if theme_index <= 0 or theme_index >= len(self._theme_options):
            return None
        theme_key = self._theme_options[theme_index]
        if theme_key is None:
            return None
        row = self._rows_by_theme.get(theme_key)
        if row is None:
            return None
        selected_row = self.member_table.currentRow()
        visible_stock_ids = self._visible_member_stock_ids()
        global_row = self._member_page_index * self._MEMBER_PAGE_SIZE + selected_row
        if selected_row < 0 or global_row >= len(visible_stock_ids):
            return None
        if (
            self._member_theme_key != theme_key
            or self._member_snapshot_identity != snapshot.identity_sha256
        ):
            return None
        item = self.member_table.item(selected_row, 0)
        if item is None:
            return None
        selected_stock_code = item.text().strip()
        if (
            not selected_stock_code
            or selected_stock_code != visible_stock_ids[global_row]
            or selected_stock_code not in row.stock_ids
            or (expected_stock_code is not None
                and selected_stock_code != str(expected_stock_code).strip())
        ):
            return None
        original_row_index = row.stock_ids.index(selected_stock_code)
        member_names: list[tuple[str, str]] = []
        for stock_code in row.stock_ids:
            mapping_row = self._mapping_by_theme_stock.get(
                (*theme_key, stock_code)
            )
            stock_name = self._mapping_text(mapping_row, "stock_name")
            member_names.append(
                (stock_code, stock_name if stock_name != "未提供" else "")
            )
        return ThemeMemberNavigation(
            snapshot_ref=snapshot,
            snapshot_identity=snapshot.identity_sha256,
            theme_key=theme_key,
            member_stock_codes=tuple(row.stock_ids),
            member_names=tuple(member_names),
            origin_stock_code=selected_stock_code,
            origin_row_index=original_row_index,
            source_data_date=snapshot.report.data_date.isoformat(),
            mapping_version=snapshot.report.mapping_snapshot_date,
            selection_revision=self._navigation_selection_revision,
        )

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

        self.comparison_toggle = QPushButton("雙版本題材原值比較（展開）")
        self.comparison_toggle.setObjectName("industryThemeComparisonToggle")
        self.comparison_toggle.setCheckable(True)
        self.comparison_toggle.setAccessibleName("展開或收合雙版本題材原值比較")
        self.comparison_toggle.toggled.connect(self._toggle_comparison)
        content_layout.addWidget(self.comparison_toggle)
        self.comparison_group = QGroupBox("雙版本題材原值並列（非跨期績效）")
        self.comparison_group.setObjectName("industryThemeTwoVersionComparison")
        self.comparison_group.setVisible(False)
        comparison_layout = QVBoxLayout(self.comparison_group)
        comparison_note = QLabel(
            "請各自明選兩個本機 manifest；兩份檔案會分別經既有 reader 驗讀。"
            "讀取後再選鏈與題材，並列原值與各自身份／日期／映射／來源／覆蓋。"
            "缺列、部分覆蓋或缺值顯示「未知」；成員可能不同，不計算差額、排名或績效。"
        )
        comparison_note.setWordWrap(True)
        comparison_note.setTextFormat(Qt.TextFormat.PlainText)
        comparison_layout.addWidget(comparison_note)
        comparison_buttons = QHBoxLayout()
        self.comparison_choose_button = QPushButton("選擇兩個 manifest 並讀取…")
        self.comparison_choose_button.setObjectName("industryThemeChooseTwoVersions")
        self.comparison_choose_button.clicked.connect(self._choose_comparison_snapshots)
        comparison_buttons.addWidget(self.comparison_choose_button)
        self.comparison_load_button = QPushButton("重新讀取所選兩版")
        self.comparison_load_button.setObjectName("industryThemeLoadTwoVersions")
        self.comparison_load_button.clicked.connect(self._load_comparison_snapshots)
        comparison_buttons.addWidget(self.comparison_load_button)
        comparison_buttons.addStretch(1)
        comparison_layout.addLayout(comparison_buttons)
        self.comparison_status = QLabel("尚未明選雙版本。")
        self.comparison_status.setWordWrap(True)
        self.comparison_status.setTextFormat(Qt.TextFormat.PlainText)
        comparison_layout.addWidget(self.comparison_status)
        choice_row = QHBoxLayout()
        self.comparison_chain_filter = QComboBox()
        self.comparison_chain_filter.setAccessibleName("雙版本比較產業鏈")
        self.comparison_theme_filter = QComboBox()
        self.comparison_theme_filter.setAccessibleName("雙版本比較題材")
        self.comparison_chain_filter.currentIndexChanged.connect(self._populate_comparison_theme_filter)
        self.comparison_theme_filter.currentIndexChanged.connect(self._render_comparison)
        choice_row.addWidget(QLabel("鏈"))
        choice_row.addWidget(self.comparison_chain_filter, 1)
        choice_row.addWidget(QLabel("題材"))
        choice_row.addWidget(self.comparison_theme_filter, 1)
        comparison_layout.addLayout(choice_row)
        comparison_columns = QHBoxLayout()
        self.comparison_version_labels: list[QLabel] = []
        self.comparison_coverage_bars: list[QProgressBar] = []
        self.comparison_coverage_status_labels: list[QLabel] = []
        for index in range(2):
            column = QWidget(self.comparison_group)
            column_layout = QVBoxLayout(column)
            column_layout.setContentsMargins(0, 0, 0, 0)
            column_layout.setSpacing(4)
            coverage_bar = QProgressBar(column)
            coverage_bar.setObjectName(f"industryThemeComparisonCoverage{index + 1}")
            coverage_bar.setAccessibleName(f"雙版本第{index + 1}版報酬資料覆蓋")
            coverage_bar.setAccessibleDescription("尚未選擇題材")
            coverage_bar.setTextVisible(True)
            coverage_bar.setFixedHeight(18)
            coverage_bar.setVisible(False)
            coverage_bar.setStyleSheet(
                f"QProgressBar {{ border: 1px solid {MIDNIGHT_ANALYST.border}; "
                f"background-color: {MIDNIGHT_ANALYST.surface_2}; color: {MIDNIGHT_ANALYST.text_primary}; "
                "text-align: center; padding: 0px; } "
                f"QProgressBar::chunk {{ background-color: {MIDNIGHT_ANALYST.accent}; }}"
            )
            coverage_status = QLabel("")
            coverage_status.setObjectName(f"industryThemeComparisonCoverageStatus{index + 1}")
            coverage_status.setAccessibleName(f"雙版本第{index + 1}版報酬資料覆蓋狀態")
            coverage_status.setTextFormat(Qt.TextFormat.PlainText)
            coverage_status.setFixedHeight(18)
            coverage_status.setVisible(False)
            self.comparison_coverage_bars.append(coverage_bar)
            self.comparison_coverage_status_labels.append(coverage_status)
            column_layout.addWidget(coverage_bar)
            column_layout.addWidget(coverage_status)
            label = QLabel("尚未讀取版本。")
            label.setObjectName(f"industryThemeComparisonVersion{index + 1}")
            label.setAccessibleName(f"雙版本第{index + 1}版原值與來源脈絡")
            label.setWordWrap(True)
            label.setTextFormat(Qt.TextFormat.PlainText)
            label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            label.setMinimumHeight(238)
            label.setStyleSheet(
                f"background-color: {MIDNIGHT_ANALYST.surface_2}; "
                f"border: 1px solid {MIDNIGHT_ANALYST.border}; padding: 8px;"
            )
            self.comparison_version_labels.append(label)
            column_layout.addWidget(label, 1)
            comparison_columns.addWidget(column, 1)
        comparison_layout.addLayout(comparison_columns)
        content_layout.addWidget(self.comparison_group)

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
        observations_layout = QVBoxLayout(self.observations_group)
        self.observation_cards_layout = QGridLayout()
        observations_layout.addLayout(self.observation_cards_layout)
        self.observation_missing_label = QLabel("尚未載入題材觀察值。")
        self.observation_missing_label.setWordWrap(True)
        observations_layout.addWidget(self.observation_missing_label)
        self.observation_cards: dict[str, QGroupBox] = {}
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
            self.observation_cards[key] = card
            self.observation_cards_layout.addWidget(card, 0, len(self.observation_cards) - 1)
            card.hide()
            self.leader_card_topics[key] = topic_label
            self.leader_card_values[key] = value_label
            self.leader_card_coverages[key] = coverage_label
        content_layout.addWidget(self.observations_group)

        self.return_tiles_toggle = QPushButton("瀏覽完整覆蓋漲跌格（展開）")
        self.return_tiles_toggle.setObjectName("industryThemeReturnTilesToggle")
        self.return_tiles_toggle.setAccessibleName("展開或收合完整覆蓋題材漲跌格")
        self.return_tiles_toggle.setCheckable(True)
        self.return_tiles_toggle.toggled.connect(self._toggle_return_tiles)
        content_layout.addWidget(self.return_tiles_toggle)
        self.return_tiles_group = QGroupBox("完整覆蓋題材漲跌格")
        self.return_tiles_group.setObjectName("industryThemeReturnTilesGroup")
        self.return_tiles_group.setVisible(False)
        return_tiles_layout = QVBoxLayout(self.return_tiles_group)
        self.return_tiles_summary = QLabel("尚未載入題材漲跌格。")
        self.return_tiles_summary.setAccessibleName("題材漲跌格資料日與涵蓋摘要")
        self.return_tiles_summary.setWordWrap(True)
        self.return_tiles_summary.setTextFormat(Qt.TextFormat.PlainText)
        return_tiles_layout.addWidget(self.return_tiles_summary)
        self.return_tiles_note = QLabel(
            "每格等面積，不表示成交金額或題材規模。紅色為正、綠色為負、灰色為零；"
            "只顯示完整漲跌覆蓋的原值。按鈕可用滑鼠或鍵盤選取並定位原題材與成員明細。"
        )
        self.return_tiles_note.setWordWrap(True)
        self.return_tiles_note.setTextFormat(Qt.TextFormat.PlainText)
        self.return_tiles_note.setStyleSheet(f"color: {MIDNIGHT_ANALYST.text_secondary};")
        return_tiles_layout.addWidget(self.return_tiles_note)
        self.return_tiles_grid_widget = QWidget(self.return_tiles_group)
        self.return_tiles_grid = QGridLayout(self.return_tiles_grid_widget)
        self.return_tiles_grid.setContentsMargins(0, 0, 0, 0)
        self.return_tiles_grid.setHorizontalSpacing(6)
        self.return_tiles_grid.setVerticalSpacing(6)
        return_tiles_layout.addWidget(self.return_tiles_grid_widget)
        content_layout.addWidget(self.return_tiles_group)

        self.turnover_treemap_toggle = QPushButton("瀏覽完整覆蓋成交金額面積圖（展開）")
        self.turnover_treemap_toggle.setObjectName("industryThemeTurnoverTreemapToggle")
        self.turnover_treemap_toggle.setAccessibleName("展開或收合完整覆蓋成交金額面積圖")
        self.turnover_treemap_toggle.setCheckable(True)
        self.turnover_treemap_toggle.toggled.connect(self._toggle_turnover_treemap)
        content_layout.addWidget(self.turnover_treemap_toggle)
        self.turnover_treemap_group = QGroupBox("題材成交金額面積圖（TWD）")
        self.turnover_treemap_group.setObjectName("industryThemeTurnoverTreemapGroup")
        self.turnover_treemap_group.setVisible(False)
        turnover_layout = QVBoxLayout(self.turnover_treemap_group)
        self.turnover_treemap_summary = QLabel("尚未載入成交金額面積圖。")
        self.turnover_treemap_summary.setAccessibleName("成交金額面積圖資料日與完整覆蓋摘要")
        self.turnover_treemap_summary.setWordWrap(True)
        self.turnover_treemap_summary.setTextFormat(Qt.TextFormat.PlainText)
        turnover_layout.addWidget(self.turnover_treemap_summary)
        self.turnover_treemap_note = QLabel(
            "面積只比較圖中最多 20 個完整覆蓋正值題材；其他完整值可沿原產業鏈與題材篩選查閱。"
            "題材成員可能重疊，"
            "各格不可相加作市場占比。零成交金額另列且不占面積；缺值或覆蓋不全不畫格。"
            "這是當前研究版本的每日觀察，不代表歷史 PIT 資格。"
        )
        self.turnover_treemap_note.setWordWrap(True)
        self.turnover_treemap_note.setTextFormat(Qt.TextFormat.PlainText)
        self.turnover_treemap_note.setStyleSheet(f"color: {MIDNIGHT_ANALYST.text_secondary};")
        turnover_layout.addWidget(self.turnover_treemap_note)
        self.turnover_treemap_canvas = QWidget(self.turnover_treemap_group)
        self.turnover_treemap_canvas.setObjectName("industryThemeTurnoverTreemapCanvas")
        self.turnover_treemap_canvas.installEventFilter(self)
        self.turnover_treemap_canvas.setMinimumHeight(220)
        self.turnover_treemap_canvas.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        turnover_layout.addWidget(self.turnover_treemap_canvas)
        self.turnover_zero_summary = QLabel("零成交金額：無。")
        self.turnover_zero_summary.setAccessibleName("零成交金額題材列")
        self.turnover_zero_summary.setWordWrap(True)
        self.turnover_zero_summary.setTextFormat(Qt.TextFormat.PlainText)
        turnover_layout.addWidget(self.turnover_zero_summary)
        self.turnover_zero_buttons_widget = QWidget(self.turnover_treemap_group)
        self.turnover_zero_buttons_layout = QHBoxLayout(self.turnover_zero_buttons_widget)
        self.turnover_zero_buttons_layout.setContentsMargins(0, 0, 0, 0)
        self.turnover_zero_buttons_layout.setSpacing(6)
        turnover_layout.addWidget(self.turnover_zero_buttons_widget)
        content_layout.addWidget(self.turnover_treemap_group)

        self.ranking_group = QGroupBox("完整覆蓋題材觀察（兩端對照／前五名）")
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
        self.sorting_direction_combo.addItem("兩端對照（各前兩筆）", "both")
        self.sorting_direction_combo.setCurrentIndex(2)
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
            ["位置", "產業鏈", "題材", "觀察值｜中線 0", "覆蓋數"]
        )
        self.ranking_table.setItemDelegateForColumn(3, ObservationBarDelegate(self.ranking_table))
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
            "長條只對照目前列的共用尺度，中線為零；高低端重疊不重列，單一題材不構成兩端比較。"
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

        theme_search_layout = QHBoxLayout()
        theme_search_layout.addWidget(QLabel("題材名稱搜尋"))
        self.theme_search_input = QLineEdit()
        self.theme_search_input.setObjectName("industryThemeNameSearchInput")
        self.theme_search_input.setAccessibleName("題材名稱片段搜尋")
        self.theme_search_input.setPlaceholderText("輸入題材名稱片段；跨鏈同名會分列")
        self.theme_search_input.setClearButtonEnabled(True)
        self.theme_search_input.setMinimumWidth(0)
        self.theme_search_input.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed
        )
        self.theme_search_input.textChanged.connect(self._search_theme_names)
        theme_search_layout.addWidget(self.theme_search_input, 2)

        self.theme_search_results = QComboBox()
        self.theme_search_results.setObjectName("industryThemeNameSearchResults")
        self.theme_search_results.setAccessibleName("題材名稱搜尋結果，明選鏈與題材")
        self.theme_search_results.setMinimumWidth(0)
        self.theme_search_results.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed
        )
        self.theme_search_results.addItem("輸入片段以搜尋題材", None)
        self.theme_search_results.currentIndexChanged.connect(
            self._update_theme_search_controls
        )
        theme_search_layout.addWidget(self.theme_search_results, 3)

        self.theme_search_locate_button = QPushButton("定位題材")
        self.theme_search_locate_button.setObjectName("industryThemeNameSearchLocate")
        self.theme_search_locate_button.setAccessibleName("定位明選的題材搜尋結果")
        self.theme_search_locate_button.clicked.connect(
            self._locate_selected_theme_search_result
        )
        theme_search_layout.addWidget(self.theme_search_locate_button)

        self.theme_search_clear_button = QPushButton("清除")
        self.theme_search_clear_button.setObjectName("industryThemeNameSearchClear")
        self.theme_search_clear_button.setAccessibleName("清除題材名稱搜尋")
        self.theme_search_clear_button.clicked.connect(self.theme_search_input.clear)
        theme_search_layout.addWidget(self.theme_search_clear_button)
        filter_layout.addLayout(theme_search_layout)

        self.theme_search_status_label = QLabel("載入版本後可輸入題材名稱片段。")
        self.theme_search_status_label.setObjectName("industryThemeNameSearchStatus")
        self.theme_search_status_label.setAccessibleName("題材名稱搜尋狀態")
        self.theme_search_status_label.setWordWrap(True)
        self.theme_search_status_label.setTextFormat(Qt.TextFormat.PlainText)
        filter_layout.addWidget(self.theme_search_status_label)

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

        self.selected_theme_summary = QLabel("選擇題材以對照原指標與成員。")
        self.selected_theme_summary.setObjectName("industryThemeSelectedSummary")
        self.selected_theme_summary.setTextFormat(Qt.TextFormat.PlainText)
        self.selected_theme_summary.setWordWrap(True)
        self.selected_theme_summary.setStyleSheet(
            f"color: {MIDNIGHT_ANALYST.text_primary}; font-weight: 600;"
        )
        content_layout.addWidget(self.selected_theme_summary)
        self.theme_overlap_toggle = QPushButton("查看共用成員鄰域（展開）")
        self.theme_overlap_toggle.setObjectName("industryThemeOverlapToggle")
        self.theme_overlap_toggle.setAccessibleName("展開同版本共用成員鄰域")
        self.theme_overlap_toggle.setCheckable(True)
        self.theme_overlap_toggle.setChecked(False)
        self.theme_overlap_toggle.toggled.connect(self._toggle_theme_overlap)
        content_layout.addWidget(self.theme_overlap_toggle)
        self.theme_overlap_group = QGroupBox("共用成員鄰域")
        self.theme_overlap_group.setObjectName("industryThemeOverlapGroup")
        self.theme_overlap_group.setVisible(False)
        overlap_layout = QVBoxLayout(self.theme_overlap_group)
        self.theme_overlap_summary = QLabel("展開後顯示同版本題材的共用成員。")
        self.theme_overlap_summary.setObjectName("industryThemeOverlapSummary")
        self.theme_overlap_summary.setWordWrap(True)
        self.theme_overlap_summary.setTextFormat(Qt.TextFormat.PlainText)
        overlap_layout.addWidget(self.theme_overlap_summary)
        self.theme_overlap_cards_layout = QGridLayout()
        self.theme_overlap_cards_layout.setSpacing(6)
        overlap_layout.addLayout(self.theme_overlap_cards_layout)
        self.theme_overlap_context = QLabel("")
        self.theme_overlap_context.setObjectName("industryThemeOverlapContext")
        self.theme_overlap_context.setWordWrap(True)
        self.theme_overlap_context.setTextFormat(Qt.TextFormat.PlainText)
        overlap_layout.addWidget(self.theme_overlap_context)
        content_layout.addWidget(self.theme_overlap_group)
        self.classification_explorer_toggle = QPushButton(
            "查看所選題材分類成員（展開）"
        )
        self.classification_explorer_toggle.setObjectName(
            "industryThemeClassificationExplorerToggle"
        )
        self.classification_explorer_toggle.setAccessibleName(
            "展開所選產業鏈與題材的靜態分類成員"
        )
        self.classification_explorer_toggle.setCheckable(True)
        self.classification_explorer_toggle.setChecked(False)
        self.classification_explorer_toggle.toggled.connect(
            self._toggle_classification_explorer
        )
        content_layout.addWidget(self.classification_explorer_toggle)
        self.classification_explorer_group = QGroupBox(
            "產業鏈／題材／成員分類"
        )
        self.classification_explorer_group.setObjectName(
            "industryThemeClassificationExplorer"
        )
        self.classification_explorer_group.setAccessibleName(
            "所選題材靜態分類階層與來源"
        )
        self.classification_explorer_group.setVisible(False)
        classification_layout = QVBoxLayout(self.classification_explorer_group)
        self.classification_hierarchy_label = QLabel("尚未選擇題材。")
        self.classification_hierarchy_label.setObjectName(
            "industryThemeClassificationHierarchy"
        )
        self.classification_hierarchy_label.setAccessibleName(
            "產業鏈至題材的分類階層"
        )
        self.classification_hierarchy_label.setWordWrap(True)
        self.classification_hierarchy_label.setTextFormat(Qt.TextFormat.PlainText)
        classification_layout.addWidget(self.classification_hierarchy_label)
        self.classification_members_layout = QVBoxLayout()
        self.classification_members_layout.setSpacing(4)
        classification_layout.addLayout(self.classification_members_layout)
        self.classification_members_status = QLabel("展開後顯示分類成員。")
        self.classification_members_status.setObjectName(
            "industryThemeClassificationMembersStatus"
        )
        self.classification_members_status.setAccessibleName("分類成員顯示範圍")
        self.classification_members_status.setWordWrap(True)
        self.classification_members_status.setTextFormat(Qt.TextFormat.PlainText)
        classification_layout.addWidget(self.classification_members_status)
        content_layout.addWidget(self.classification_explorer_group)
        self._classification_explorer_identity: str | None = None
        self._classification_explorer_key: tuple[str, str] | None = None
        self._classification_explorer_member_limit = 30
        self._theme_overlap_identity: str | None = None
        self._theme_overlap_key: tuple[str, str] | None = None
        self._theme_overlap_buttons: list[QPushButton] = []
        self.theme_detail_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.theme_detail_splitter.setObjectName("industryThemeDetailSplitter")
        self.theme_detail_splitter.setChildrenCollapsible(False)
        content_layout.addWidget(self.theme_detail_splitter)
        self.metrics_group = QGroupBox("題材指標與欄位覆蓋")
        self.metrics_group.setMinimumWidth(0)
        metrics_layout = QVBoxLayout(self.metrics_group)
        self.metrics_cards_group = QGroupBox("九項指標概觀")
        self.metrics_cards_group.setObjectName("industryThemeMetricCards")
        self.metrics_cards_group.setVisible(False)
        self.metrics_cards_layout = QVBoxLayout(self.metrics_cards_group)
        self.metrics_card_rows: list[QHBoxLayout] = []
        self.metrics_card_labels: list[tuple[QLabel, QLabel, QLabel]] = []
        self._metric_card_widgets: list[QWidget] = []
        self._metric_card_columns = 0
        for _ in range(5):
            card_row = QHBoxLayout()
            card_row.setSpacing(6)
            self.metrics_cards_layout.addLayout(card_row)
            self.metrics_card_rows.append(card_row)
        self.metrics_group.installEventFilter(self)
        metrics_layout.addWidget(self.metrics_cards_group)
        self.metrics_table = QTableWidget(0, 3)
        self.metrics_table.setObjectName("industryThemeMetricsTable")
        self.metrics_table.setAccessibleName("題材指標與欄位覆蓋表")
        self.metrics_table.setMinimumHeight(200)
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
        self.theme_detail_splitter.addWidget(self.metrics_group)

        self.members_group = QGroupBox("題材成員（雙擊任一欄開啟）")
        self.members_group.setMinimumWidth(0)
        members_layout = QVBoxLayout(self.members_group)
        member_actions = QHBoxLayout()
        self.member_selection_label = QLabel("先選取一檔成員股票。")
        self.member_selection_label.setTextFormat(Qt.TextFormat.PlainText)
        self.member_selection_label.setWordWrap(True)
        member_actions.addWidget(self.member_selection_label, 1)
        self.open_member_button = QPushButton("研究選取股票")
        self.open_member_button.setObjectName("industryThemeOpenSelectedMember")
        self.open_member_button.setEnabled(False)
        self.open_member_button.clicked.connect(self._open_selected_member)
        member_actions.addWidget(self.open_member_button)
        members_layout.addLayout(member_actions)
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
        self.member_table.currentCellChanged.connect(self._on_member_cell_changed)
        member_pagination = QHBoxLayout()
        self.member_page_previous_button = QPushButton("上一頁")
        self.member_page_previous_button.setObjectName("industryThemeMemberPreviousPage")
        self.member_page_previous_button.setAccessibleName("題材成員上一頁")
        self.member_page_previous_button.clicked.connect(
            lambda: self._change_member_page(-1)
        )
        member_pagination.addWidget(self.member_page_previous_button)
        self.member_page_status_label = QLabel("顯示 0 / 0 位成員")
        self.member_page_status_label.setObjectName("industryThemeMemberPageStatus")
        self.member_page_status_label.setAccessibleName("題材成員目前顯示範圍")
        self.member_page_status_label.setTextFormat(Qt.TextFormat.PlainText)
        member_pagination.addWidget(self.member_page_status_label, 1)
        self.member_page_next_button = QPushButton("下一頁")
        self.member_page_next_button.setObjectName("industryThemeMemberNextPage")
        self.member_page_next_button.setAccessibleName("題材成員下一頁")
        self.member_page_next_button.clicked.connect(
            lambda: self._change_member_page(1)
        )
        member_pagination.addWidget(self.member_page_next_button)
        members_layout.addLayout(member_pagination)
        members_layout.addWidget(self.member_table)
        self.theme_detail_splitter.addWidget(self.members_group)
        self.theme_detail_splitter.setStretchFactor(0, 4)
        self.theme_detail_splitter.setStretchFactor(1, 6)
        content_layout.addStretch(1)

        self.scroll_area.setWidget(self.content)
        page_layout.addWidget(self.scroll_area, 1)

    @Slot(bool)
    def _toggle_comparison(self, expanded: bool) -> None:
        if self._closed or self._busy or self._snapshot is None:
            expanded = False
            blocker = QSignalBlocker(self.comparison_toggle)
            self.comparison_toggle.setChecked(False)
            del blocker
        self.comparison_group.setVisible(expanded)
        self.comparison_toggle.setText(
            "雙版本題材原值比較（收合）" if expanded else "雙版本題材原值比較（展開）"
        )

    def _invalidate_comparison(self, *, clear_paths: bool = True,
                               collapse: bool = True) -> None:
        """使舊雙版本回呼失效並清除原值；主版本變動時一律呼叫。"""
        self._comparison_generation += 1
        if self._comparison_worker is not None:
            self._comparison_worker.cancel(cooperative=True, wait=False)
        self._comparison_result = None
        self._comparison_error = ""
        self._comparison_snapshots = None
        self._comparison_presentation = None
        if clear_paths:
            self._comparison_paths = None
        self.comparison_status.setText("尚未明選雙版本。")
        self._clear_comparison_coverage()
        for label in self.comparison_version_labels:
            label.setText("尚未讀取版本。")
        blockers = [
            QSignalBlocker(self.comparison_chain_filter),
            QSignalBlocker(self.comparison_theme_filter),
        ]
        self.comparison_chain_filter.clear()
        self.comparison_theme_filter.clear()
        self.comparison_chain_filter.addItem("尚未選擇", None)
        self.comparison_theme_filter.addItem("尚未選擇", None)
        del blockers
        if collapse:
            blocker = QSignalBlocker(self.comparison_toggle)
            self.comparison_toggle.setChecked(False)
            del blocker
            self._toggle_comparison(False)
        self._update_comparison_controls()

    def _choose_comparison_snapshots(self) -> None:
        if (self._closed or self._busy or self._snapshot is None
                or self._comparison_worker is not None):
            return
        original_generation = self._generation
        original_snapshot = self._snapshot
        self._invalidate_comparison(collapse=False)
        self.comparison_status.setText("請依序明選兩份題材 manifest。")
        first_name, _ = QFileDialog.getOpenFileName(
            self, "選取雙版本比較的第一個 manifest", "",
            "題材版本 manifest (*.json);;所有檔案 (*.*)",
        )
        if not first_name:
            self.comparison_status.setText("已取消雙版本明選；比較已清除。")
            return
        second_name, _ = QFileDialog.getOpenFileName(
            self, "選取雙版本比較的第二個 manifest", "",
            "題材版本 manifest (*.json);;所有檔案 (*.*)",
        )
        if not second_name:
            self.comparison_status.setText("已取消雙版本明選；比較已清除。")
            return
        if (self._closed or self._busy or self._generation != original_generation
                or self._snapshot is not original_snapshot
                or self._comparison_worker is not None):
            self._invalidate_comparison()
            return
        self._comparison_paths = (Path(first_name), Path(second_name))
        self._load_comparison_snapshots()

    def _load_comparison_snapshots(self) -> None:
        paths = self._comparison_paths
        if (self._closed or self._busy or self._snapshot is None
                or self._comparison_worker is not None or paths is None):
            return
        self._comparison_generation += 1
        generation = self._comparison_generation
        self._comparison_snapshots = None
        self._comparison_presentation = None
        self._comparison_result = None
        self._comparison_error = ""
        self.comparison_status.setText("正在分別驗讀明選的兩個 manifest…")
        self._clear_comparison_coverage()
        for label in self.comparison_version_labels:
            label.setText("版本讀取中。")
        worker = TaskWorker(_read_theme_comparison_pair, *paths)
        self._comparison_worker = worker
        self._comparison_worker_generation = generation
        worker.finished.connect(self._receive_comparison_result, Qt.ConnectionType.QueuedConnection)
        worker.error.connect(self._receive_comparison_error, Qt.ConnectionType.QueuedConnection)
        worker.cancelled.connect(self._receive_comparison_cancelled, Qt.ConnectionType.QueuedConnection)
        worker.native_thread_finished.connect(self._finish_comparison_load, Qt.ConnectionType.QueuedConnection)
        self._update_comparison_controls()
        try:
            worker.start()
        except Exception as exc:
            self._comparison_worker = None
            self._comparison_worker_generation = None
            self._comparison_result = None
            self._comparison_error = ""
            self._invalidate_comparison(clear_paths=False, collapse=False)
            self.comparison_status.setText(f"雙版本讀取無法啟動：{exc}")
            worker.deleteLater()
            self._update_comparison_controls()

    @Slot(object)
    def _receive_comparison_result(self, result: object) -> None:
        if (self.sender() is self._comparison_worker
                and self._comparison_worker_generation == self._comparison_generation
                and not self._closed):
            self._comparison_result = result

    @Slot(str)
    def _receive_comparison_error(self, error: str) -> None:
        if (self.sender() is self._comparison_worker
                and self._comparison_worker_generation == self._comparison_generation
                and not self._closed):
            self._comparison_error = error

    @Slot()
    def _receive_comparison_cancelled(self) -> None:
        if (self.sender() is self._comparison_worker
                and self._comparison_worker_generation == self._comparison_generation
                and not self._closed):
            self._comparison_error = "雙版本讀取已取消。"

    @Slot()
    def _finish_comparison_load(self) -> None:
        worker = self.sender()
        if worker is not self._comparison_worker:
            return
        generation = self._comparison_worker_generation
        result = self._comparison_result
        error = self._comparison_error
        self._comparison_worker = None
        self._comparison_worker_generation = None
        self._comparison_result = None
        self._comparison_error = ""
        try:
            if self._closed or generation != self._comparison_generation:
                return
            if error:
                self._invalidate_comparison(clear_paths=False, collapse=False)
                self.comparison_status.setText(
                    "雙版本讀取失敗；比較已清除：" + error.splitlines()[0]
                )
                return
            if (type(result) is not tuple or len(result) != 2
                    or any(type(item) is not ThemeResearchSnapshot for item in result)):
                self._invalidate_comparison(clear_paths=False, collapse=False)
                self.comparison_status.setText("雙版本讀取失敗；reader 未回傳兩份有效快照。")
                return
            first, second = result
            if first.identity_sha256 == second.identity_sha256:
                self._invalidate_comparison(clear_paths=False, collapse=False)
                self.comparison_status.setText(
                    "雙版本讀取失敗；兩個 manifest 指向同一快照身份，已清除比較。"
                )
                return
            # 比較結果必須仍依附於目前明確載入的主版本生命週期。
            if self._snapshot is None:
                self._invalidate_comparison()
                return
            keys = {
                (item.chain_name, item.theme_name)
                for snapshot in (first, second)
                for item in (*snapshot.mapping, *snapshot.report.rows)
            }
            chains = sorted({chain for chain, _ in keys})
            blockers = [
                QSignalBlocker(self.comparison_chain_filter),
                QSignalBlocker(self.comparison_theme_filter),
            ]
            self.comparison_chain_filter.clear()
            self.comparison_chain_filter.addItem("選擇鏈", None)
            for chain in chains:
                self.comparison_chain_filter.addItem(chain, chain)
            self.comparison_theme_filter.clear()
            self.comparison_theme_filter.addItem("選擇題材", None)
            del blockers
            self._comparison_snapshots = (first, second)
            self.comparison_status.setText(
                "兩份明選 manifest 已分別驗讀。選擇鏈與題材以查看各自原值；"
                "讀取時間不是官方發布時間，亦不授歷史 PIT 或來源用途資格。"
            )
            self._populate_comparison_theme_filter()
        except Exception as exc:
            self._invalidate_comparison(clear_paths=False, collapse=False)
            self.comparison_status.setText(f"雙版本比較呈現失敗；比較已清除：{exc}")
        finally:
            self._update_comparison_controls()
            worker.deleteLater()

    @Slot(int)
    def _populate_comparison_theme_filter(self, _index: int = -1) -> None:
        snapshots = self._comparison_snapshots
        chain = self.comparison_chain_filter.currentData()
        blockers = [QSignalBlocker(self.comparison_theme_filter)]
        self.comparison_theme_filter.clear()
        self.comparison_theme_filter.addItem("選擇題材", None)
        if snapshots is not None and type(chain) is str:
            themes = sorted({
                theme for snapshot in snapshots
                for item in (*snapshot.mapping, *snapshot.report.rows)
                if item.chain_name == chain
                for theme in (item.theme_name,)
            })
            for theme in themes:
                self.comparison_theme_filter.addItem(theme, theme)
        del blockers
        self._render_comparison()

    @Slot(int)
    def _render_comparison(self, _index: int = -1) -> None:
        snapshots = self._comparison_snapshots
        chain = self.comparison_chain_filter.currentData()
        theme = self.comparison_theme_filter.currentData()
        if snapshots is None or type(chain) is not str or type(theme) is not str:
            self._clear_comparison_coverage()
            for label in self.comparison_version_labels:
                label.setText("讀取完成後請選擇鏈與題材。")
            return
        try:
            presentation = build_theme_return_two_version_presentation(
                snapshots[0], snapshots[1], chain_name=chain, theme_name=theme,
            )
        except Exception as exc:
            self._comparison_presentation = None
            self.comparison_status.setText(f"此題材無法呈現：{exc}")
            self._clear_comparison_coverage()
            for label in self.comparison_version_labels:
                label.setText("未知；此題材無法呈現。")
            return
        self._comparison_presentation = presentation
        for index, observation in enumerate(presentation.observations):
            self._render_comparison_coverage(index, observation)
            value = self._comparison_display_value(observation.mean_return_pct)
            coverage = (f"{observation.returns_coverage} / {observation.member_count} 位成員"
                        if observation.returns_coverage is not None else "未知")
            members = "、".join(observation.stock_ids) if observation.stock_ids else "未知"
            source_ids = "、".join(observation.source_ids) if observation.source_ids else "未知"
            label = self.comparison_version_labels[index]
            label.setText(
                f"明選版本 {index + 1}\n"
                f"鏈／題材：{observation.chain_name}／{observation.theme_name}\n"
                f"平均日漲跌幅（%）：{value}\n"
                f"報酬覆蓋：{coverage}\n"
                f"成員代碼：{members}\n"
                f"報表列：{'有' if observation.row_present else '無（覆蓋未知）'}\n"
                f"資料日：{observation.data_date}\n"
                f"映射版本／可得日：{observation.mapping_snapshot_date}／{observation.mapping_available_date}\n"
                f"讀取時間（known-at，非官方發布）：{observation.known_at}\n"
                f"題材列來源 ID：{source_ids}\n"
                f"manifest SHA-256：{observation.snapshot_identity}"
            )
            label.setToolTip(
                f"平均日漲跌幅完整原值（%）："
                f"{observation.mean_return_pct if observation.mean_return_pct is not None else '未知'}\n"
                f"題材列來源 ID：{source_ids}\n"
                f"manifest SHA-256：{observation.snapshot_identity}"
            )
        self.comparison_status.setText(
            "原值並列完成。兩版本成員集合可不同；未計算差額、變化率、排名或跨期績效。"
        )

    def _clear_comparison_coverage(self) -> None:
        """清除沒有有效題材選取時的覆蓋圖形與狀態。"""
        for bar, status in zip(
            self.comparison_coverage_bars, self.comparison_coverage_status_labels,
        ):
            bar.setVisible(False)
            bar.setRange(0, 1)
            bar.setValue(0)
            bar.setFormat("")
            bar.setAccessibleDescription("尚未選擇題材")
            status.clear()
            status.setAccessibleDescription("")
            status.setVisible(False)

    def _render_comparison_coverage(
        self, index: int, observation: ThemeReturnVersionObservation,
    ) -> None:
        """只用同版報酬覆蓋計數呈現中性比例，不推定缺值為零。"""
        bar = self.comparison_coverage_bars[index]
        status = self.comparison_coverage_status_labels[index]
        bar.setVisible(False)
        bar.setRange(0, 1)
        bar.setValue(0)
        bar.setFormat("")
        bar.setAccessibleDescription("報酬覆蓋未知")
        status.setVisible(False)
        row_present = observation.row_present
        available = observation.returns_coverage
        members = observation.member_count
        if row_present is True and type(available) is int and type(members) is int and members > 0:
            exact = f"報酬覆蓋 {available} / {members} 位成員"
            bar.setRange(0, members)
            bar.setValue(available)
            bar.setFormat(exact)
            bar.setAccessibleDescription(exact)
            bar.setVisible(True)
            return
        if row_present is True and type(members) is int and members == 0:
            message = "報酬覆蓋：不適用（0 位成員；比例未知）"
        else:
            message = "報酬覆蓋：未知（無報表列或覆蓋不可用）"
        status.setText(message)
        status.setAccessibleDescription(message)
        status.setVisible(True)

    @staticmethod
    def _comparison_display_value(value: Decimal | None) -> str:
        """長原值只縮短畫面字串；完整 Decimal 仍保留於 DTO 與提示。"""
        if value is None:
            return "未知"
        original = str(value)
        if value == 0 and ("E" in original or len(original) > 14):
            return "0（完整原值見提示）"
        if len(original) <= 14:
            return original
        shortened = format(value, ".4f")
        if Decimal(shortened) == 0:
            shortened = format(value, ".4E")
        return f"約{shortened}（完整原值見提示）"

    def _update_comparison_controls(self) -> None:
        available = (
            not self._closed and not self._busy and self._snapshot is not None
            and self._comparison_worker is None
        )
        self.comparison_choose_button.setEnabled(available)
        self.comparison_load_button.setEnabled(available and self._comparison_paths is not None)
        self.comparison_toggle.setEnabled(available)
        loaded = self._comparison_snapshots is not None and not self._closed
        self.comparison_chain_filter.setEnabled(loaded)
        self.comparison_theme_filter.setEnabled(loaded)

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

        self._invalidate_comparison()
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
        self._invalidate_comparison()
        self._generation += 1
        if self._worker is not None:
            self._worker.cancel(cooperative=True, wait=False)
        self._result = None
        self._error = ""
        self._cancelled = False
        self._clear_classification_explorer(collapse=True)
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
        self._invalidate_comparison()
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
        self._invalidate_comparison()
        self._snapshot = None
        self.snapshotChanged.emit(None)
        if self._worker is not None:
            self._worker.cancel(cooperative=True, wait=False)
        self._clear_snapshot_view()
        self.status_label.setText("頁面已關閉；背景讀取正在合作式結束。")
        self._update_controls()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        """頁面關閉時同步失效題材比較與其背景回呼。"""
        self.shutdown()
        super().closeEvent(event)

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
        self._clear_classification_explorer(collapse=True)
        self._clear_theme_overlap(collapse=True)
        self.selected_theme_summary.setText("選擇題材以對照原指標與成員。")
        self.selected_theme_summary.setToolTip("")
        self._presentation = None
        self._ascending_presentation = None
        self._rows_by_theme = {}
        self._mapping_by_theme_stock = {}
        self._member_stock_ids = ()
        self._member_row_by_stock_id = {}
        self._member_theme_key = None
        self._member_snapshot_identity = None
        self._member_page_index = 0
        self._clear_chain_directory()
        self._clear_return_tiles()
        self._clear_turnover_treemap()
        self._theme_options = [None]
        self.overview_label.setText(
            "尚未載入題材研究版本；請先選取本機已保存版本。"
        )
        self.summary_label.setText("尚未載入。")
        self.summary_group.setVisible(False)
        self.source_details_button.setChecked(False)
        self.source_details_button.setText("顯示來源與限制")
        self.metrics_table.setRowCount(0)
        self._clear_metric_cards()
        self.member_table.setRowCount(0)
        self.member_table.clearSelection()
        self.member_table.setCurrentCell(-1, -1)
        self.member_table.setToolTip("")
        self.member_page_status_label.setText("顯示 0 / 0 位成員")
        self.member_page_status_label.setAccessibleDescription(
            self.member_page_status_label.text()
        )
        self.member_page_previous_button.setEnabled(False)
        self.member_page_next_button.setEnabled(False)
        self._clear_stock_lookup()
        self._clear_theme_search()
        for key in self.leader_card_topics:
            self.observation_cards[key].hide()
            self.leader_card_topics[key].setText("尚未載入")
            self.leader_card_values[key].setText("資料不足")
            self.leader_card_values[key].setToolTip("")
            self.leader_card_coverages[key].setText("尚未載入題材觀察值。")
        self.observation_missing_label.setText("尚未載入題材觀察值；不能推定為零。")
        self.observation_missing_label.show()
        self._arrange_observation_cards()
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

        if (
            self._member_theme_key != (chain_name, theme_name)
            or self._member_snapshot_identity != snapshot.identity_sha256
        ):
            self.stock_lookup_status_label.setText(
                "所選股票不在該題材成員表；沒有定位。"
            )
            return
        row_index = self._member_row_by_stock_id.get(stock_id)
        if row_index is None or not self._select_member_global_row(row_index):
            self.stock_lookup_status_label.setText(
                "所選股票不在該題材成員表；沒有定位。"
            )
            return
        self.stock_lookup_status_label.setText(
            f"已定位 {stock_id}｜{chain_name}／{theme_name}；雙擊成員列可開啟個股。"
        )

    def _populate_theme_filter(self) -> None:
        chain_name = self.chain_filter.currentData()
        options = [
            key for key in self._all_theme_filter_keys()
            if chain_name is None or key[0] == chain_name
        ]
        self._theme_options = [None, *options]
        blocker = QSignalBlocker(self.theme_filter)
        self.theme_filter.clear()
        self.theme_filter.addItem("選擇題材", None)
        for chain, theme in options:
            label = theme if chain_name is not None else f"{chain}／{theme}"
            self.theme_filter.addItem(label)
        del blocker
        self._render_selected_theme()

    def _all_theme_filter_keys(self) -> tuple[tuple[str, str], ...]:
        presentation = self._presentation
        return tuple(sorted({
            (directory.chain_name, theme)
            for directory in (presentation.chains if presentation is not None else ())
            for theme in directory.themes
        }))

    @Slot(str)
    def _search_theme_names(self, query: str) -> None:
        """只搜尋目前快照的原題材名稱，結果仍保留各自鏈／題材鍵。"""
        normalized = query.strip().casefold()
        blocker = QSignalBlocker(self.theme_search_results)
        self.theme_search_results.clear()
        self.theme_search_results.addItem(
            "輸入片段以搜尋題材" if not normalized else "沒有符合的題材",
            None,
        )
        del blocker

        snapshot = self._snapshot
        if self._closed or self._busy or snapshot is None:
            self._update_theme_search_controls()
            return
        if not normalized:
            self._update_theme_search_controls()
            return

        matches = tuple(
            key for key in self._all_theme_filter_keys()
            if normalized in key[1].casefold()
        )
        blocker = QSignalBlocker(self.theme_search_results)
        self.theme_search_results.clear()
        self.theme_search_results.addItem(
            "請明選一筆題材搜尋結果" if matches else "沒有符合的題材",
            None,
        )
        for chain_name, theme_name in matches:
            self.theme_search_results.addItem(
                f"{chain_name}／{theme_name}",
                (snapshot.identity_sha256, chain_name, theme_name),
            )
        del blocker
        self._update_theme_search_controls()

    def _clear_theme_search(self) -> None:
        blocker = QSignalBlocker(self.theme_search_input)
        self.theme_search_input.clear()
        del blocker
        blocker = QSignalBlocker(self.theme_search_results)
        self.theme_search_results.clear()
        self.theme_search_results.addItem("輸入片段以搜尋題材", None)
        del blocker
        self._update_theme_search_controls()

    @Slot(int)
    def _update_theme_search_controls(self, _index: int = -1) -> None:
        snapshot = self._snapshot
        available = snapshot is not None and not self._closed
        lookup_available = available and not self._busy
        query = self.theme_search_input.text().strip()
        result_count = max(0, self.theme_search_results.count() - 1)
        selected = self.theme_search_results.currentData(Qt.ItemDataRole.UserRole)
        valid_selection = (
            isinstance(selected, (tuple, list))
            and len(selected) == 3
            and all(type(value) is str for value in selected)
            and snapshot is not None
            and selected[0] == snapshot.identity_sha256
            and (selected[1], selected[2]) in self._all_theme_filter_keys()
        )
        self.theme_search_input.setEnabled(lookup_available)
        self.theme_search_results.setEnabled(lookup_available and result_count > 0)
        self.theme_search_locate_button.setEnabled(
            lookup_available and valid_selection
        )
        self.theme_search_clear_button.setEnabled(bool(query) and not self._closed)

        if self._closed:
            message = "頁面已關閉；題材名稱搜尋已停用。"
        elif self._busy:
            message = "版本讀取中；題材搜尋已清除並暫停。"
        elif snapshot is None:
            message = "尚未載入版本；請先選取本機研究版本。"
        elif not query:
            message = "輸入題材名稱片段；結果按鏈／題材分列。"
        elif result_count == 0:
            message = f"沒有符合「{query}」的題材；目前選取與研究結果不變。"
        elif valid_selection:
            message = (
                f"已明選 {selected[1]}／{selected[2]}；按「定位題材」套用原篩選。"
            )
        else:
            message = (
                f"找到 {result_count} 個題材；同名題材分列，請明選結果後定位。"
            )
        self.theme_search_status_label.setText(message)

    @Slot()
    def _locate_selected_theme_search_result(self) -> None:
        snapshot = self._snapshot
        selected = self.theme_search_results.currentData(Qt.ItemDataRole.UserRole)
        if (
            self._closed or self._busy or snapshot is None
            or not isinstance(selected, (tuple, list)) or len(selected) != 3
            or any(type(value) is not str for value in selected)
            or selected[0] != snapshot.identity_sha256
        ):
            self._clear_theme_search()
            self.theme_search_status_label.setText(
                "搜尋結果已失效；請重新輸入題材名稱片段。"
            )
            return
        chain_name, theme_name = selected[1], selected[2]
        key = (chain_name, theme_name)
        if key not in self._all_theme_filter_keys():
            self.theme_search_status_label.setText(
                "所選題材已不在目前版本；沒有套用舊結果。"
            )
            return
        chain_index = self.chain_filter.findData(chain_name)
        if chain_index < 0:
            self.theme_search_status_label.setText(
                "所選產業鏈已不在目前版本；沒有套用舊結果。"
            )
            return
        self.chain_filter.setCurrentIndex(chain_index)
        try:
            theme_index = self._theme_options.index(key)
        except ValueError:
            self.theme_search_status_label.setText(
                "所選題材已不在目前篩選目錄；沒有套用舊結果。"
            )
            return
        self.theme_filter.setCurrentIndex(theme_index)
        self.theme_search_status_label.setText(
            f"已定位 {chain_name}／{theme_name}；原快照與題材身份保持不變。"
        )

    def _render_presentation(self) -> None:
        presentation = self._presentation
        if presentation is None:
            return
        self._render_return_tiles()
        self._render_turnover_treemap()
        leader_lists = {
            "return": presentation.return_leaders,
            "turnover": presentation.turnover_leaders,
            "institutional": presentation.institutional_leaders,
            "volume": presentation.volume_leaders,
        }
        missing: list[str] = []
        for key, rows in leader_lists.items():
            self.observation_cards[key].setVisible(bool(rows))
            if not rows:
                missing.append(self.observation_cards[key].title())
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
        self.observation_missing_label.setText(
            "資料不足：" + "、".join(missing) + "。沒有完整覆蓋觀察值，不能推定為零。"
            if missing else ""
        )
        self.observation_missing_label.setVisible(bool(missing))
        self._arrange_observation_cards()
        self._render_chain_directory()
        self._render_leaderboard()

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().resizeEvent(event)
        self._arrange_observation_cards()
        if hasattr(self, "return_tiles_grid") and self._return_tile_buttons:
            self._arrange_return_tile_buttons()
        if hasattr(self, "turnover_treemap_canvas") and self._turnover_treemap_buttons:
            self._arrange_turnover_treemap_buttons()
        if hasattr(self, "theme_detail_splitter"):
            orientation = Qt.Orientation.Horizontal if self.width() >= 1050 else Qt.Orientation.Vertical
            if self.theme_detail_splitter.orientation() != orientation:
                self.theme_detail_splitter.setOrientation(orientation)
                self.theme_detail_splitter.setSizes([400, 600])

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802 - Qt override
        if (
            hasattr(self, "turnover_treemap_canvas")
            and watched is self.turnover_treemap_canvas
            and event.type() == QEvent.Type.Resize
            and self._turnover_treemap_buttons
        ):
            self._arrange_turnover_treemap_buttons()
        if (
            hasattr(self, "metrics_group")
            and watched is self.metrics_group
            and event.type() == QEvent.Type.Resize
            and self._metric_card_widgets
        ):
            self._arrange_metric_cards()
        return super().eventFilter(watched, event)

    def _arrange_observation_cards(self) -> None:
        if not hasattr(self, "observation_cards"):
            return
        columns = 1 if self.width() < 650 else 2 if self.width() < 1100 else 4
        visible = [card for card in self.observation_cards.values() if not card.isHidden()]
        columns = min(columns, max(1, len(visible)))
        for card in self.observation_cards.values():
            self.observation_cards_layout.removeWidget(card)
        for index, card in enumerate(visible):
            self.observation_cards_layout.addWidget(card, index // columns, index % columns)
        for column in range(4):
            self.observation_cards_layout.setColumnStretch(column, int(column < columns))

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

    def _clear_return_tiles(self) -> None:
        self._return_tile_identity = None
        self._return_tile_buttons.clear()
        while self.return_tiles_grid.count():
            item = self.return_tiles_grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setEnabled(False)
                widget.hide()
                widget.deleteLater()
        self.return_tiles_summary.setText("尚未載入題材漲跌格。")
        self.return_tiles_group.setVisible(False)
        blocker = QSignalBlocker(self.return_tiles_toggle)
        self.return_tiles_toggle.setChecked(False)
        del blocker
        self.return_tiles_toggle.setText("瀏覽完整覆蓋漲跌格（展開）")
        self.return_tiles_toggle.setEnabled(False)

    def _render_return_tiles(self) -> None:
        presentation = self._presentation
        snapshot = self._snapshot
        self._clear_return_tiles()
        if presentation is None or snapshot is None or self._closed:
            return
        self._return_tile_identity = snapshot.identity_sha256
        eligible = len(presentation.return_tiles)
        self.return_tiles_summary.setText(
            f"資料日：{snapshot.report.data_date.isoformat()}　｜　"
            f"完整覆蓋：{eligible} / {presentation.return_tile_total} 個報表題材列"
        )
        if not presentation.return_tiles:
            self.return_tiles_summary.setText(
                self.return_tiles_summary.text()
                + "　｜　目前沒有完整覆蓋且具有限漲跌值的題材。"
            )
            return
        filter_keys = set(self._theme_options[1:])
        selectable_tiles = tuple(
            tile for tile in presentation.return_tiles
            if (tile.chain_name, tile.theme_name) in filter_keys
            and (tile.chain_name, tile.theme_name) in self._rows_by_theme
        )
        if len(selectable_tiles) != eligible:
            self.return_tiles_summary.setText(
                self.return_tiles_summary.text()
                + f"　｜　可由既有篩選定位：{len(selectable_tiles)} 格"
            )
        if not selectable_tiles:
            self.return_tiles_summary.setText(
                self.return_tiles_summary.text() + "　｜　沒有對應的既有題材篩選選項。"
            )
        chain_labels = self._duplicate_theme_chain_labels(selectable_tiles)
        for tile in selectable_tiles:
            chain_label = chain_labels.get((tile.chain_name, tile.theme_name))
            visible_name = (
                f"{chain_label}｜{tile.theme_name}" if chain_label else tile.theme_name
            )
            button = QPushButton(
                f"{visible_name}\n{self._display_decimal(tile.mean_return_pct, suffix=' %')}"
            )
            button.setObjectName("industryThemeReturnTile")
            button.setCheckable(True)
            button.setMinimumHeight(68)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            button.setAccessibleName(
                f"{tile.chain_name}／{tile.theme_name}，"
                f"平均日漲跌 {tile.mean_return_pct} 百分比，"
                f"完整覆蓋 {tile.returns_coverage} / {tile.members} 位成員"
            )
            button.setToolTip(
                f"{tile.chain_name}／{tile.theme_name}\n"
                f"原值：{tile.mean_return_pct} %\n"
                f"覆蓋：{tile.returns_coverage} / {tile.members} 位成員\n"
                f"資料日：{tile.data_date}\n"
                f"映射版本／可得：{tile.mapping_snapshot_date}／{tile.mapping_available_date}\n"
                f"讀取時間：{tile.known_at}\n"
                f"來源：{'、'.join(tile.source_ids) if tile.source_ids else '未提供'}\n"
                f"版本 SHA-256：{tile.snapshot_identity}"
            )
            button.setProperty("themeSnapshotIdentity", tile.snapshot_identity)
            button.setProperty("themeChainName", tile.chain_name)
            button.setProperty("themeName", tile.theme_name)
            if tile.mean_return_pct > 0:
                color = "#6F252B"
            elif tile.mean_return_pct < 0:
                color = "#25634A"
            else:
                color = "#555B63"
            button.setStyleSheet(
                f"QPushButton {{ background-color: {color}; color: #FFFFFF; "
                "border: 1px solid #8C949D; border-radius: 4px; padding: 6px; "
                "font-weight: 600; } QPushButton:focus { border: 2px solid #F2C94C; } "
                "QPushButton:checked { border: 3px solid #F2C94C; }"
            )
            button.clicked.connect(self._on_return_tile_clicked)
            self._return_tile_buttons[(tile.chain_name, tile.theme_name)] = button
        self._arrange_return_tile_buttons()
        self._sync_return_tile_selection()
        self._update_return_tile_controls()

    def _arrange_return_tile_buttons(self) -> None:
        while self.return_tiles_grid.count():
            self.return_tiles_grid.takeAt(0)
        columns = 2 if self.width() < 760 else 4
        for index, button in enumerate(self._return_tile_buttons.values()):
            row_index, column_index = divmod(index, columns)
            self.return_tiles_grid.addWidget(button, row_index, column_index)
        for column in range(columns):
            self.return_tiles_grid.setColumnStretch(column, 1)

    def _sync_return_tile_selection(self) -> None:
        chain_name = self.chain_filter.currentData()
        theme_index = self.theme_filter.currentIndex()
        selected_key = (
            self._theme_options[theme_index]
            if 0 < theme_index < len(self._theme_options) else None
        )
        if type(chain_name) is str and selected_key is not None:
            selected_key = (chain_name, selected_key[1])
        for key, button in self._return_tile_buttons.items():
            button.setChecked(key == selected_key)
        self._sync_turnover_treemap_selection()

    @Slot(bool)
    def _toggle_return_tiles(self, expanded: bool) -> None:
        if self._closed or self._busy or self._snapshot is None:
            expanded = False
            blocker = QSignalBlocker(self.return_tiles_toggle)
            self.return_tiles_toggle.setChecked(False)
            del blocker
        self.return_tiles_group.setVisible(expanded)
        self.return_tiles_toggle.setText(
            "瀏覽完整覆蓋漲跌格（收合）" if expanded else "瀏覽完整覆蓋漲跌格（展開）"
        )

    @Slot()
    def _on_return_tile_clicked(self) -> None:
        button = self.sender()
        snapshot = self._snapshot
        if not isinstance(button, QPushButton) or snapshot is None:
            return
        identity = button.property("themeSnapshotIdentity")
        chain_name = button.property("themeChainName")
        theme_name = button.property("themeName")
        key = (chain_name, theme_name)
        if (
            self._closed or self._busy
            or type(identity) is not str or type(chain_name) is not str
            or type(theme_name) is not str
            or identity != snapshot.identity_sha256
            or identity != self._return_tile_identity
            or key not in self._return_tile_buttons
            or key not in self._rows_by_theme
        ):
            return
        self._open_chain_directory_theme(identity, chain_name, theme_name)

    def _update_return_tile_controls(self) -> None:
        available = self._snapshot is not None and not self._closed and not self._busy
        self.return_tiles_toggle.setEnabled(available and bool(self._return_tile_buttons))
        self.return_tiles_group.setEnabled(available)
        for button in self._return_tile_buttons.values():
            button.setEnabled(available)
        if self._busy and self._snapshot is None:
            self.return_tiles_summary.setText("版本讀取中；題材漲跌格暫不顯示。")

    def _clear_turnover_treemap(self) -> None:
        self._turnover_treemap_identity = None
        self._turnover_treemap_buttons.clear()
        self._turnover_zero_buttons.clear()
        self._turnover_tiles_by_key.clear()
        for button in self.turnover_treemap_canvas.findChildren(QPushButton):
            button.setEnabled(False)
            button.hide()
            button.deleteLater()
        while self.turnover_zero_buttons_layout.count():
            item = self.turnover_zero_buttons_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setEnabled(False)
                widget.hide()
                widget.deleteLater()
        self.turnover_treemap_summary.setText("尚未載入成交金額面積圖。")
        self.turnover_zero_summary.setText("零成交金額：無。")
        self.turnover_treemap_group.setVisible(False)
        blocker = QSignalBlocker(self.turnover_treemap_toggle)
        self.turnover_treemap_toggle.setChecked(False)
        del blocker
        self.turnover_treemap_toggle.setText("瀏覽完整覆蓋成交金額面積圖（展開）")
        self.turnover_treemap_toggle.setEnabled(False)

    def _render_turnover_treemap(self) -> None:
        presentation = self._presentation
        snapshot = self._snapshot
        self._clear_turnover_treemap()
        if presentation is None or snapshot is None or self._closed:
            return
        self._turnover_treemap_identity = snapshot.identity_sha256
        eligible = presentation.turnover_tiles
        self._turnover_tiles_by_key = {
            (tile.chain_name, tile.theme_name): tile for tile in eligible
        }
        positive = tuple(tile for tile in eligible if tile.turnover_twd > 0)
        zero = tuple(tile for tile in eligible if tile.turnover_twd == 0)
        filter_keys = set(self._theme_options[1:])
        all_selectable_positive = tuple(
            tile for tile in positive
            if (tile.chain_name, tile.theme_name) in filter_keys
            and (tile.chain_name, tile.theme_name) in self._rows_by_theme
        )
        selectable_positive = tuple(sorted(
            all_selectable_positive,
            key=lambda tile: (-tile.turnover_twd, tile.chain_name, tile.theme_name),
        )[:self._MAX_TURNOVER_AREA_TILES])
        chain_labels = self._duplicate_theme_chain_labels(selectable_positive)
        selectable_zero = tuple(
            tile for tile in zero
            if (tile.chain_name, tile.theme_name) in filter_keys
            and (tile.chain_name, tile.theme_name) in self._rows_by_theme
        )
        self.turnover_treemap_summary.setText(
            f"資料日：{snapshot.report.data_date.isoformat()}　｜　"
            f"完整覆蓋有效值：{len(eligible)} / {presentation.turnover_tile_total} 個報表題材列　｜　"
            f"正值面積：{len(positive)} 格　｜　零值：{len(zero)} 筆"
        )
        if len(all_selectable_positive) > len(selectable_positive):
            self.turnover_treemap_summary.setText(
                self.turnover_treemap_summary.text()
                + f"　｜　面積圖顯示成交金額前 {len(selectable_positive)} / {len(all_selectable_positive)} 格"
            )
        if len(all_selectable_positive) != len(positive) or len(selectable_zero) != len(zero):
            self.turnover_treemap_summary.setText(
                self.turnover_treemap_summary.text()
                + f"　｜　可由既有篩選定位：{len(all_selectable_positive) + len(selectable_zero)} 筆"
            )
        excluded = presentation.turnover_tile_total - len(eligible)
        self.turnover_treemap_summary.setText(
            self.turnover_treemap_summary.text()
            + f"　｜　覆蓋不全、缺值或非有限值：{excluded} 筆未畫面積"
        )
        self.turnover_treemap_canvas.setMinimumHeight(420 if len(selectable_positive) > 10 else 220)
        for tile in selectable_positive:
            display = self._turnover_area_label(tile.turnover_twd)
            chain_label = chain_labels.get((tile.chain_name, tile.theme_name))
            visible_name = (
                f"{tile.theme_name}\n{chain_label} · {display}"
                if chain_label else f"{tile.theme_name}\n{display}"
            )
            button = QPushButton(
                visible_name,
                self.turnover_treemap_canvas,
            )
            button.setObjectName("industryThemeTurnoverTreemapTile")
            button.setCheckable(True)
            button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            button.setAccessibleName(
                f"{tile.chain_name}／{tile.theme_name}，成交金額 {tile.turnover_twd} TWD，"
                f"完整覆蓋 {tile.turnover_coverage} / {tile.members} 位成員"
            )
            button.setToolTip(self._turnover_tile_tooltip(tile))
            button.setProperty("themeSnapshotIdentity", tile.snapshot_identity)
            button.setProperty("themeChainName", tile.chain_name)
            button.setProperty("themeName", tile.theme_name)
            button.setStyleSheet(
                "QPushButton { background-color: #315C78; color: #FFFFFF; "
                "border: 1px solid #9AA8B4; border-radius: 3px; padding: 3px; font-weight: 600; } "
                "QPushButton:focus { border: 2px solid #F2C94C; } "
                "QPushButton:checked { border: 3px solid #F2C94C; }"
            )
            button.clicked.connect(self._on_turnover_tile_clicked)
            self._turnover_treemap_buttons[(tile.chain_name, tile.theme_name)] = button
        for tile in selectable_zero:
            button = QPushButton(f"{tile.chain_name}／{tile.theme_name}　0 TWD")
            button.setObjectName("industryThemeTurnoverZeroTile")
            button.setCheckable(True)
            button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            button.setAccessibleName(
                f"{tile.chain_name}／{tile.theme_name}，成交金額為零，沒有面積，"
                f"完整覆蓋 {tile.turnover_coverage} / {tile.members} 位成員"
            )
            button.setToolTip(self._turnover_tile_tooltip(tile) + "\n零值以文字列出，不占面積。")
            button.setProperty("themeSnapshotIdentity", tile.snapshot_identity)
            button.setProperty("themeChainName", tile.chain_name)
            button.setProperty("themeName", tile.theme_name)
            button.clicked.connect(self._on_turnover_tile_clicked)
            self._turnover_zero_buttons[(tile.chain_name, tile.theme_name)] = button
            self.turnover_zero_buttons_layout.addWidget(button)
        if zero:
            self.turnover_zero_summary.setText(
                "零成交金額（不占面積）：" + "、".join(
                    f"{tile.chain_name}／{tile.theme_name}（覆蓋 {tile.turnover_coverage} / {tile.members} 位）"
                    for tile in zero
                )
            )
        elif not eligible:
            self.turnover_zero_summary.setText("零成交金額：無；沒有完整覆蓋有效成交值。")
        self._arrange_turnover_treemap_buttons()
        self._sync_turnover_treemap_selection()
        self._update_turnover_treemap_controls()

    @staticmethod
    def _duplicate_theme_chain_labels(
        tiles: tuple[ThemeReturnTile, ...] | tuple[ThemeTurnoverTile, ...],
    ) -> dict[tuple[str, str], str]:
        """只為畫面中跨鏈同名題材產生最短可區分的鏈名標籤。"""
        chains_by_theme: dict[str, set[str]] = {}
        for tile in tiles:
            chains_by_theme.setdefault(tile.theme_name, set()).add(tile.chain_name)

        labels: dict[tuple[str, str], str] = {}
        for tile in tiles:
            chains = chains_by_theme[tile.theme_name]
            if len(chains) < 2:
                continue
            for length in range(1, len(tile.chain_name) + 1):
                candidate = tile.chain_name[:length]
                if all(
                    candidate != other[:min(length, len(other))]
                    for other in chains if other != tile.chain_name
                ):
                    labels[(tile.chain_name, tile.theme_name)] = candidate
                    break
            else:
                labels[(tile.chain_name, tile.theme_name)] = tile.chain_name
        return labels

    @staticmethod
    def _turnover_area_label(value: Decimal) -> str:
        """面積格的短字串；精確原值仍由提示與無障礙名稱保留。"""
        if value >= Decimal("100000000"):
            return f"約{value / Decimal('100000000'):,.1f}億"
        if value >= Decimal("10000"):
            return f"約{value / Decimal('10000'):,.0f}萬"
        return f"{value:,.2f} TWD"

    @staticmethod
    def _turnover_tile_tooltip(tile: ThemeTurnoverTile) -> str:
        return (
            f"{tile.chain_name}／{tile.theme_name}\n原成交金額：{tile.turnover_twd} TWD\n"
            f"覆蓋：{tile.turnover_coverage} / {tile.members} 位成員\n資料日：{tile.data_date}\n"
            f"映射版本／可得：{tile.mapping_snapshot_date}／{tile.mapping_available_date}\n"
            f"讀取時間：{tile.known_at}\n原題材列相關來源識別："
            f"{'、'.join(tile.source_ids) if tile.source_ids else '未提供'}\n"
            f"版本 SHA-256：{tile.snapshot_identity}"
        )

    def _arrange_turnover_treemap_buttons(self) -> None:
        buttons = self._turnover_treemap_buttons
        canvas = self.turnover_treemap_canvas
        if not buttons or canvas.width() <= 0 or canvas.height() <= 0:
            return
        values = tuple(sorted(
            ((key, self._turnover_tiles_by_key[key].turnover_twd)
             for key in buttons if key in self._turnover_tiles_by_key),
            key=lambda item: (-item[1], item[0]),
        ))
        rects = self._slice_turnover_rects(values, QRect(0, 0, canvas.width(), canvas.height()))
        for key, button in buttons.items():
            if key in rects:
                button.setGeometry(rects[key])

    @classmethod
    def _slice_turnover_rects(
        cls, values: tuple[tuple[tuple[str, str], Decimal], ...], rect: QRect,
    ) -> dict[tuple[str, str], QRect]:
        """依原成交額切分矩形；浮點比例只用於 Qt 像素幾何。"""
        if not values or rect.width() <= 0 or rect.height() <= 0:
            return {}
        if len(values) == 1:
            return {values[0][0]: rect}
        total = sum((value for _, value in values), Decimal(0))
        running = Decimal(0)
        split = 1
        best_gap: Decimal | None = None
        for index, (_, value) in enumerate(values[:-1], start=1):
            running += value
            gap = abs(total - running * 2)
            if best_gap is None or gap < best_gap:
                best_gap = gap
                split = index
        left_values, right_values = values[:split], values[split:]
        left_total = sum((value for _, value in left_values), Decimal(0))
        fraction = float(left_total / total) if total > 0 else len(left_values) / len(values)
        if rect.width() >= rect.height():
            first_size = min(rect.width() - 1, max(1, round(rect.width() * fraction)))
            first_rect = QRect(rect.x(), rect.y(), first_size, rect.height())
            second_rect = QRect(rect.x() + first_size, rect.y(), rect.width() - first_size, rect.height())
        else:
            first_size = min(rect.height() - 1, max(1, round(rect.height() * fraction)))
            first_rect = QRect(rect.x(), rect.y(), rect.width(), first_size)
            second_rect = QRect(rect.x(), rect.y() + first_size, rect.width(), rect.height() - first_size)
        result = cls._slice_turnover_rects(left_values, first_rect)
        result.update(cls._slice_turnover_rects(right_values, second_rect))
        return result

    def _sync_turnover_treemap_selection(self) -> None:
        chain_name = self.chain_filter.currentData()
        theme_index = self.theme_filter.currentIndex()
        selected_key = self._theme_options[theme_index] if 0 < theme_index < len(self._theme_options) else None
        if type(chain_name) is str and selected_key is not None:
            selected_key = (chain_name, selected_key[1])
        for key, button in (*self._turnover_treemap_buttons.items(), *self._turnover_zero_buttons.items()):
            button.setChecked(key == selected_key)

    @Slot(bool)
    def _toggle_turnover_treemap(self, expanded: bool) -> None:
        if self._closed or self._busy or self._snapshot is None:
            expanded = False
            blocker = QSignalBlocker(self.turnover_treemap_toggle)
            self.turnover_treemap_toggle.setChecked(False)
            del blocker
        self.turnover_treemap_group.setVisible(expanded)
        self.turnover_treemap_toggle.setText(
            "瀏覽完整覆蓋成交金額面積圖（收合）" if expanded
            else "瀏覽完整覆蓋成交金額面積圖（展開）"
        )

    @Slot()
    def _on_turnover_tile_clicked(self) -> None:
        button = self.sender()
        snapshot = self._snapshot
        if not isinstance(button, QPushButton) or snapshot is None:
            return
        identity = button.property("themeSnapshotIdentity")
        chain_name = button.property("themeChainName")
        theme_name = button.property("themeName")
        key = (chain_name, theme_name)
        if (
            self._closed or self._busy or type(identity) is not str
            or type(chain_name) is not str or type(theme_name) is not str
            or identity != snapshot.identity_sha256
            or identity != self._turnover_treemap_identity
            or (key not in self._turnover_treemap_buttons and key not in self._turnover_zero_buttons)
            or key not in self._rows_by_theme
        ):
            return
        self._open_chain_directory_theme(identity, chain_name, theme_name)

    def _update_turnover_treemap_controls(self) -> None:
        available = self._snapshot is not None and not self._closed and not self._busy
        has_items = bool(self._turnover_treemap_buttons or self._turnover_zero_buttons)
        self.turnover_treemap_toggle.setEnabled(available and has_items)
        self.turnover_treemap_group.setEnabled(available)
        for button in (*self._turnover_treemap_buttons.values(), *self._turnover_zero_buttons.values()):
            button.setEnabled(available)

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
        direction = self.sorting_direction_combo.currentData()
        if direction is True or direction == "both":
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
            if direction is True:
                presentation = ascending_presentation
        ranking_type = self.ranking_type_combo.currentData()
        row_sets = {
            "return": presentation.return_leaders,
            "turnover": presentation.turnover_leaders,
            "institutional": presentation.institutional_leaders,
            "volume": presentation.volume_leaders,
        }
        leaders = row_sets.get(ranking_type, ())
        positions = [str(rank) for rank in range(1, len(leaders) + 1)]
        if direction == "both" and self._ascending_presentation is not None:
            low_sets = {
                "return": self._ascending_presentation.return_leaders,
                "turnover": self._ascending_presentation.turnover_leaders,
                "institutional": self._ascending_presentation.institutional_leaders,
                "volume": self._ascending_presentation.volume_leaders,
            }
            high = leaders[:2]
            low = low_sets.get(ranking_type, ())[:2]
            high_keys = {(row.chain_name, row.theme_name) for row in high}
            low_keys = {(row.chain_name, row.theme_name) for row in low}
            leaders = high + tuple(row for row in low if (row.chain_name, row.theme_name) not in high_keys)
            positions = ["兩端重疊" if (row.chain_name, row.theme_name) in low_keys else f"高 {rank}" for rank, row in enumerate(high, 1)]
            positions += [f"低 {rank}" for rank, row in enumerate(low, 1) if (row.chain_name, row.theme_name) not in high_keys]
            if len(leaders) == 1:
                positions = ["單一觀察"]
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
                positions[rank - 1],
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
                    field = {"return": "mean_return_pct", "turnover": "turnover_twd", "institutional": "institutional_net_shares", "volume": "volume_multiple_5d"}.get(str(ranking_type))
                    raw = getattr(row, field, None) if field else None
                    item.setData(OBSERVATION_VALUE_ROLE, str(raw) if raw is not None else None)
                    item.setData(
                        OBSERVATION_DIRECTIONAL_ROLE,
                        str(ranking_type) in {"return", "institutional"},
                    )
                self.ranking_table.setItem(rank - 1, column, item)
        self.ranking_table.resizeRowsToContents()

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
            value = row.turnover_twd
            if value is not None and value.is_finite() and abs(value) >= Decimal("100000000"):
                display = f"{value / Decimal('100000000'):,.2f} 億元 TWD"
            elif value is not None and value.is_finite() and abs(value) >= Decimal("10000"):
                display = f"{value / Decimal('10000'):,.2f} 萬元 TWD"
            else:
                display = self._display_decimal(value, suffix=" TWD")
            return (
                display,
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
        self._navigation_selection_revision += 1
        self._clear_classification_explorer(collapse=True)
        if self._snapshot is None:
            return
        self._populate_theme_filter()
        self._sync_return_tile_selection()
        self._update_controls()

    @Slot(int)
    def _on_theme_changed(self, _index: int) -> None:
        self._navigation_selection_revision += 1
        self._render_selected_theme()
        self._sync_return_tile_selection()
        self._update_controls()

    def _clear_theme_overlap(self, *, collapse: bool) -> None:
        """清除舊版本／題材的鄰域卡，避免延遲點擊定位過期身份。"""
        if collapse:
            blocker = QSignalBlocker(self.theme_overlap_toggle)
            self.theme_overlap_toggle.setChecked(False)
            del blocker
            self.theme_overlap_toggle.setText("查看共用成員鄰域（展開）")
        self.theme_overlap_group.setVisible(False)
        self.theme_overlap_summary.setText("展開後顯示同版本題材的共用成員。")
        self.theme_overlap_context.clear()
        self._theme_overlap_identity = None
        self._theme_overlap_key = None
        for button in self._theme_overlap_buttons:
            button.setEnabled(False)
            button.hide()
        while self.theme_overlap_cards_layout.count():
            item = self.theme_overlap_cards_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._theme_overlap_buttons.clear()

    @Slot(bool)
    def _toggle_theme_overlap(self, expanded: bool) -> None:
        if (self._closed or self._busy or self._snapshot is None
                or self.theme_filter.currentIndex() <= 0):
            expanded = False
            blocker = QSignalBlocker(self.theme_overlap_toggle)
            self.theme_overlap_toggle.setChecked(False)
            del blocker
        if expanded:
            self._render_theme_overlap()
        else:
            self._clear_theme_overlap(collapse=False)
        self.theme_overlap_group.setVisible(expanded)
        self.theme_overlap_toggle.setText(
            "查看共用成員鄰域（收合）" if expanded
            else "查看共用成員鄰域（展開）"
        )

    def _render_theme_overlap(
        self, selected_key: tuple[str, str] | None = None
    ) -> None:
        self._clear_theme_overlap(collapse=False)
        snapshot = self._snapshot
        index = self.theme_filter.currentIndex()
        if snapshot is None or index <= 0 or index >= len(self._theme_options):
            return
        key = selected_key or self._theme_options[index]
        if key is None or self._theme_options[index] != key:
            return
        try:
            presentation = build_theme_overlap_presentation(snapshot, key[0], key[1])
        except (TypeError, ValueError) as exc:
            self.theme_overlap_summary.setText(
                f"此版本無法呈現共用成員鄰域：{str(exc).splitlines()[0]}"
            )
            return
        self._theme_overlap_identity = presentation.snapshot_identity_sha256
        self._theme_overlap_key = key
        self.theme_overlap_summary.setText(
            f"{presentation.chain_name}／{presentation.theme_name}："
            f"共用成員數／所選題材成員數；僅列前 {len(presentation.neighbors)} 個鄰居。"
        )
        self.theme_overlap_context.setText(
            f"鄰居共 {presentation.total_neighbors} 個，省略 {presentation.omitted_neighbors} 個　｜　"
            f"資料日 {presentation.data_date}　｜　映射快照日 {presentation.mapping_snapshot_date}　｜　"
            f"映射可得日 {presentation.mapping_available_date}　｜　"
            f"版本讀取時間 {presentation.known_at}　｜　"
            f"版本 SHA-256 {presentation.snapshot_identity_sha256}\n"
            "僅靜態分類重疊，非供應鏈、因果、歷史 PIT。"
        )
        for card_index, neighbor in enumerate(presentation.neighbors):
            ids = neighbor.shared_stock_ids
            names = neighbor.shared_stock_names
            shared_list = "、".join(
                f"{stock_id} {name or '名稱未提供'}"
                for stock_id, name in zip(ids, names)
            )
            visible = "、".join(
                f"{stock_id} {name or '名稱未提供'}"
                for stock_id, name in list(zip(ids, names))[:2]
            )
            if len(ids) > 2:
                visible += f"、另 {len(ids) - 2} 檔"
            card = QFrame(self.theme_overlap_group)
            card.setObjectName("industryThemeOverlapNeighborCard")
            card.setFrameShape(QFrame.Shape.StyledPanel)
            card_layout = QVBoxLayout(card)
            button = QPushButton(
                f"{neighbor.chain_name}／{neighbor.theme_name}\n{visible}"
            )
            button.setObjectName("industryThemeOverlapNeighborButton")
            button.setAccessibleName(
                f"定位共用成員題材 {neighbor.chain_name}／{neighbor.theme_name}"
            )
            button.setProperty("themeSnapshotIdentity", presentation.snapshot_identity_sha256)
            button.setProperty("themeSelectedKey", key)
            button.setProperty("themeChainName", neighbor.chain_name)
            button.setProperty("themeName", neighbor.theme_name)
            tooltip_lines = [
                f"完整共用股票：{shared_list}",
                f"所選題材成員：{presentation.selected_member_count} 檔",
            ]
            mapping_fields = (
                ("stock_name", "股票名稱"),
                ("source_name", "來源"),
                ("source_tier", "來源層級"),
                ("assignment_method", "分配方法"),
                ("pit_mode", "PIT 模式"),
                ("evidence_note", "證據註記"),
                ("snapshot_date", "快照日"),
                ("available_date", "可得日"),
            )
            for shared_index, (stock_id, selected_row, neighbor_row) in enumerate(zip(
                ids,
                neighbor.selected_mapping_rows,
                neighbor.neighbor_mapping_rows,
            )):
                if shared_index >= 2:
                    break
                tooltip_lines.append(f"\n共用股票 {stock_id}：")
                for side_label, row in (
                    (f"所選題材 {key[0]}／{key[1]}", selected_row),
                    (f"鄰居題材 {neighbor.chain_name}／{neighbor.theme_name}", neighbor_row),
                ):
                    tooltip_lines.append(f"{side_label} 原分類列：")
                    for field_name, field_label in mapping_fields:
                        value = getattr(row, field_name)
                        tooltip_lines.append(
                            f"  {field_label}：{value if value else '未提供'}"
                        )
            if len(ids) > 2:
                tooltip_lines.append(
                    f"其餘 {len(ids) - 2} 檔可至所選與鄰居題材各自的「產業鏈／題材／成員分類」查看原列。"
                )
            tooltip_lines.extend((
                f"資料日：{presentation.data_date}",
                f"映射快照日：{presentation.mapping_snapshot_date}",
                f"映射可得日：{presentation.mapping_available_date}",
                f"版本讀取時間：{presentation.known_at}",
                f"版本 SHA-256：{presentation.snapshot_identity_sha256}",
                "僅靜態分類重疊，非供應鏈、因果、歷史 PIT。",
            ))
            button.setToolTip("\n".join(tooltip_lines))
            button.setMinimumWidth(0)
            button.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            button.clicked.connect(self._open_theme_overlap_neighbor)
            card_layout.addWidget(button)
            overlap_bar = QProgressBar(card)
            overlap_bar.setObjectName("industryThemeOverlapProgressBar")
            overlap_bar.setAccessibleName(
                f"{neighbor.chain_name}／{neighbor.theme_name}共用成員比例"
            )
            overlap_bar.setRange(0, presentation.selected_member_count)
            overlap_bar.setValue(len(ids))
            overlap_bar.setFormat("共用 %v / %m 檔")
            overlap_bar.setTextVisible(True)
            overlap_bar.setToolTip(
                f"共用成員數 {len(ids)}，所選題材有效成員數 {presentation.selected_member_count}。"
            )
            card_layout.addWidget(overlap_bar)
            self.theme_overlap_cards_layout.addWidget(card, card_index // 2, card_index % 2)
            self._theme_overlap_buttons.append(button)
        if not presentation.neighbors:
            self.theme_overlap_summary.setText(
                f"{presentation.chain_name}／{presentation.theme_name} 沒有同版本共用成員題材。"
            )

    @Slot()
    def _open_theme_overlap_neighbor(self) -> None:
        button = self.sender()
        snapshot = self._snapshot
        if (not isinstance(button, QPushButton)
                or button not in self._theme_overlap_buttons
                or self._closed or self._busy or snapshot is None):
            return
        identity = button.property("themeSnapshotIdentity")
        selected_key = button.property("themeSelectedKey")
        if isinstance(selected_key, (tuple, list)) and len(selected_key) == 2:
            selected_key = tuple(selected_key)
        chain_name = button.property("themeChainName")
        theme_name = button.property("themeName")
        index = self.theme_filter.currentIndex()
        current_key = (
            self._theme_options[index]
            if 0 < index < len(self._theme_options) else None
        )
        if (type(identity) is not str or identity != snapshot.identity_sha256
                or identity != self._theme_overlap_identity
                or selected_key != self._theme_overlap_key
                or selected_key != current_key
                or not all(type(value) is str for value in (chain_name, theme_name))):
            return
        self._open_chain_directory_theme(identity, chain_name, theme_name)
        if self._member_theme_key == (chain_name, theme_name):
            self.scroll_area.ensureWidgetVisible(self.selected_theme_summary, 0, 0)

    def _clear_classification_explorer(self, *, collapse: bool) -> None:
        """清除舊分類投影，避免選取或版本替換後留下過期成員。"""
        self._clear_member_l1_filter(render_table=True)
        self._classification_l1_filter_buttons.clear()
        self._classification_l1_active_filter_button = None
        self._classification_l1_reset_button = None
        self._classification_members_base_status = None
        if collapse:
            blocker = QSignalBlocker(self.classification_explorer_toggle)
            self.classification_explorer_toggle.setChecked(False)
            del blocker
            self.classification_explorer_toggle.setText(
                "查看所選題材分類成員（展開）"
            )
        self.classification_explorer_group.setVisible(False)
        self.classification_hierarchy_label.setText("尚未選擇題材。")
        self.classification_members_status.setText("展開後顯示分類成員。")
        self._classification_explorer_identity = None
        self._classification_explorer_key = None
        while self.classification_members_layout.count():
            item = self.classification_members_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _visible_member_stock_ids(self) -> tuple[str, ...]:
        """回傳目前表格頁面使用的同一題材成員序列。"""
        if self._member_l1_filter_stock_ids is not None:
            return self._member_l1_filter_stock_ids
        return self._member_stock_ids

    def _clear_member_l1_filter(self, *, render_table: bool) -> None:
        had_filter = self._member_l1_filter_stock_ids is not None
        self._member_l1_filter_stock_ids = None
        self._member_l1_filter_label = None
        self._classification_l1_active_filter_button = None
        for button in self._classification_l1_filter_buttons:
            button.setChecked(False)
        if self._classification_l1_reset_button is not None:
            self._classification_l1_reset_button.setEnabled(False)
        if (had_filter and render_table and self._snapshot is not None
                and self._member_theme_key is not None):
            self._member_page_index = 0
            self._render_member_page()

    def _update_classification_l1_filter_buttons(self) -> None:
        snapshot = self._snapshot
        available = (
            snapshot is not None and not self._closed and not self._busy
            and self._classification_explorer_identity == snapshot.identity_sha256
            and self._classification_explorer_key == self._member_theme_key
        )
        for button in self._classification_l1_filter_buttons:
            button.setChecked(button is self._classification_l1_active_filter_button)
            button.setEnabled(available)
        if self._classification_l1_reset_button is not None:
            self._classification_l1_reset_button.setEnabled(
                available and self._member_l1_filter_stock_ids is not None
            )

    def _apply_classification_l1_filter(
        self,
        category_values: tuple[str, ...],
        include_missing: bool,
        label: str,
        snapshot_identity: str,
        theme_key: tuple[str, str],
        button: QPushButton,
        checked: bool,
    ) -> None:
        snapshot = self._snapshot
        if (
            self._closed or self._busy or snapshot is None
            or snapshot.identity_sha256 != snapshot_identity
            or self._classification_explorer_identity != snapshot_identity
            or self._classification_explorer_key != theme_key
            or self._member_snapshot_identity != snapshot_identity
            or self._member_theme_key != theme_key
        ):
            return
        if not checked:
            self._reset_classification_l1_filter(snapshot_identity, theme_key)
            return
        try:
            presentation = build_theme_classification_presentation(
                snapshot, theme_key[0], theme_key[1]
            )
        except (TypeError, ValueError):
            self._clear_member_l1_filter(render_table=True)
            self.classification_members_status.setText(
                "目前分類版本無法核對；已還原完整題材成員表。"
            )
            self._update_classification_l1_filter_buttons()
            return
        if presentation.snapshot_identity_sha256 != snapshot_identity:
            return

        selected_ids = tuple(
            member.stock_id
            for member in presentation.members
            if member.l1_industry_category in category_values
            and (not include_missing or not member.l1_industry_category.strip())
            and (include_missing or bool(member.l1_industry_category.strip()))
        )
        selected_id_set = set(selected_ids)
        visible_ids = tuple(
            stock_id for stock_id in self._member_stock_ids
            if stock_id in selected_id_set
        )
        if not selected_ids or len(visible_ids) != len(selected_ids):
            self._clear_member_l1_filter(render_table=True)
            self.classification_members_status.setText(
                "分類列與目前題材成員清單無法完整核對；已還原完整成員表。"
            )
            self._update_classification_l1_filter_buttons()
            return

        self._member_l1_filter_stock_ids = visible_ids
        self._member_l1_filter_label = label
        self._classification_l1_active_filter_button = button
        self._member_page_index = 0
        self._render_member_page()
        self.classification_members_status.setText(
            f"{self._classification_members_base_status or ''}\n"
            f"目前篩選：{label}；符合 {len(visible_ids)} / "
            f"本題材 {len(self._member_stock_ids)} 位。"
        )
        self._update_classification_l1_filter_buttons()
        content = self.scroll_area.widget()
        if content is not None:
            table_top = self.member_table.mapTo(
                content, self.member_table.rect().topLeft()
            ).y()
            self.scroll_area.verticalScrollBar().setValue(max(0, table_top - 8))

    def _reset_classification_l1_filter(
        self, snapshot_identity: str, theme_key: tuple[str, str],
    ) -> None:
        snapshot = self._snapshot
        if (
            self._closed or self._busy or snapshot is None
            or snapshot.identity_sha256 != snapshot_identity
            or self._classification_explorer_identity != snapshot_identity
            or self._classification_explorer_key != theme_key
            or self._member_snapshot_identity != snapshot_identity
            or self._member_theme_key != theme_key
        ):
            return
        self._clear_member_l1_filter(render_table=True)
        self.classification_members_status.setText(
            self._classification_members_base_status
            or "目前顯示完整題材分類成員。"
        )
        self._update_classification_l1_filter_buttons()

    @Slot(bool)
    def _toggle_classification_explorer(self, expanded: bool) -> None:
        if (self._closed or self._busy or self._snapshot is None
                or self.theme_filter.currentIndex() <= 0):
            expanded = False
            blocker = QSignalBlocker(self.classification_explorer_toggle)
            self.classification_explorer_toggle.setChecked(False)
            del blocker
        if expanded:
            self._render_classification_explorer()
        else:
            self._clear_classification_explorer(collapse=False)
        self.classification_explorer_group.setVisible(expanded)
        self.classification_explorer_toggle.setText(
            "查看所選題材分類成員（收合）" if expanded
            else "查看所選題材分類成員（展開）"
        )

    @staticmethod
    def _classification_value(value: str) -> str:
        return value.strip() if value.strip() else "未提供"

    def _add_classification_l1_summary(
        self, presentation: ThemeClassificationPresentation, total: int,
    ) -> None:
        """用目前題材的 typed members 顯示有界 L1 列數摘要。"""
        counts: dict[str, int] = {}
        missing_count = 0
        missing_values: dict[str, int] = {}
        for member in presentation.members:
            category = member.l1_industry_category
            if not category.strip():
                missing_count += 1
                missing_values[category] = missing_values.get(category, 0) + 1
                continue
            counts[category] = counts.get(category, 0) + 1

        ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        shown = ordered[:8]
        omitted = ordered[8:]
        card = QGroupBox("L1 產業組成（分類列數／本題材分類列總數）")
        card.setObjectName("industryThemeClassificationL1Summary")
        card.setAccessibleName("目前題材各 L1 產業的分類列數摘要")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(3)
        dates = QLabel(
            f"資料日 {presentation.data_date}；Mapping 日期 "
            f"{presentation.mapping_snapshot_date}／"
            f"{presentation.mapping_available_date}"
        )
        dates.setObjectName("industryThemeClassificationL1Dates")
        dates.setWordWrap(True)
        dates.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(dates)
        note = QLabel(
            "點選類別查看下方成員；依同一版本的分類列計數，"
            "不代表權重、供應關係或歷史 PIT。"
        )
        note.setObjectName("industryThemeClassificationL1Note")
        note.setWordWrap(True)
        note.setTextFormat(Qt.TextFormat.PlainText)
        note_row = QHBoxLayout()
        note_row.addWidget(note, 1)
        theme_key = (presentation.chain_name, presentation.theme_name)
        reset_button = QPushButton("全部成員")
        reset_button.setObjectName("industryThemeClassificationL1Reset")
        reset_button.setAccessibleName("還原完整題材成員清單")
        reset_button.setToolTip("清除 L1 類別篩選，還原此題材完整成員清單。")
        reset_button.clicked.connect(
            lambda _checked=False, identity=presentation.snapshot_identity_sha256,
            key=theme_key: self._reset_classification_l1_filter(identity, key)
        )
        note_row.addWidget(reset_button)
        layout.addLayout(note_row)
        self._classification_l1_reset_button = reset_button
        def add_bar(
            label_text: str,
            count: int,
            tooltip: str,
            category_values: tuple[str, ...],
            include_missing: bool = False,
        ) -> None:
            row = QHBoxLayout()
            category_label = QPushButton(label_text)
            category_label.setObjectName("industryThemeClassificationL1Category")
            category_label.setFixedWidth(190)
            category_label.setFixedHeight(23)
            display_label_text = QFontMetrics(category_label.font()).elidedText(
                label_text, Qt.TextElideMode.ElideRight, 190
            ).replace("&", "&&")
            category_label.setText(display_label_text)
            category_label.setAccessibleName(label_text)
            category_label.setAccessibleDescription(
                "按下以依此題材版本的原始 L1 分類篩選下方成員表。"
            )
            category_label.setToolTip(tooltip)
            category_label.setFlat(True)
            category_label.setCheckable(True)
            category_label.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            category_label.setCursor(Qt.CursorShape.PointingHandCursor)
            category_label.setStyleSheet(
                f"QPushButton {{ text-align: left; color: "
                f"{MIDNIGHT_ANALYST.text_primary}; border: 1px solid "
                f"{MIDNIGHT_ANALYST.border_subtle}; border-radius: 3px; "
                f"padding-left: 4px; }} "
                f"QPushButton:hover {{ border-color: {MIDNIGHT_ANALYST.border}; }} "
                f"QPushButton:checked {{ background-color: "
                f"{MIDNIGHT_ANALYST.surface_2}; "
                f"border-color: {MIDNIGHT_ANALYST.accent}; }}"
            )
            bar = QProgressBar()
            bar.setObjectName("industryThemeClassificationL1Bar")
            bar.setAccessibleName(f"{label_text}分類列數")
            bar.setRange(0, total)
            bar.setValue(count)
            bar.setFormat("%v / %m 列")
            bar.setTextVisible(True)
            bar.setToolTip(tooltip)
            bar.setStyleSheet(
                f"QProgressBar {{ border: 1px solid {MIDNIGHT_ANALYST.border}; "
                f"border-radius: 3px; text-align: center; color: "
                f"{MIDNIGHT_ANALYST.text_primary}; }} "
                f"QProgressBar::chunk {{ background-color: "
                f"{MIDNIGHT_ANALYST.accent}; }}"
            )
            row.addWidget(category_label)
            row.addWidget(bar, 1)
            layout.addLayout(row)
            category_label.clicked.connect(
                lambda checked=False, values=category_values,
                missing=include_missing, text=label_text,
                identity=presentation.snapshot_identity_sha256, key=theme_key,
                button=category_label:
                self._apply_classification_l1_filter(
                    values, missing, text, identity, key, button, checked
                )
            )
            self._classification_l1_filter_buttons.append(category_label)

        for category, count in shown:
            category_label = f"「{category}」"
            add_bar(
                category_label, count,
                f"來源原值：{category!r}；{count} / {total} 筆分類列；"
                "同一題材與版本。",
                (category,),
            )
        if omitted:
            tooltip_limit = 12
            omitted_rows = "；".join(
                f"{category!r} {count} 列"
                for category, count in omitted[:tooltip_limit]
            )
            omitted_remaining = len(omitted) - min(len(omitted), tooltip_limit)
            if omitted_remaining:
                omitted_rows += (
                    f"；另有 {omitted_remaining} 個 L1 類別，"
                    "請至下方完整成員表查看"
                )
            add_bar(
                f"其他（合併 {len(omitted)} 個 L1 類別）",
                sum(count for _, count in omitted),
                f"合併其餘 {len(omitted)} 個 L1 類別；逐類計數：{omitted_rows}。",
                tuple(category for category, _count in omitted),
            )
        if missing_count:
            missing_values_limit = 12
            missing_value_rows = "；".join(
                f"{category!r} {count} 列"
                for category, count in sorted(missing_values.items())[
                    :missing_values_limit
                ]
            )
            missing_values_remaining = max(
                0, len(missing_values) - missing_values_limit
            )
            if missing_values_remaining:
                missing_value_rows += (
                    f"；另有 {missing_values_remaining} 種空白原值，"
                    "請至下方完整成員表查看"
                )
            add_bar(
                "未提供（欄位空白）", missing_count,
                f"L1 產業欄位原值為空白：{missing_count} / {total} 筆分類列；"
                f"各空白原值計數：{missing_value_rows}。",
                tuple(missing_values),
                include_missing=True,
            )
        if total == 0:
            empty = QLabel("本題材沒有可計數的分類列。")
            empty.setObjectName("industryThemeClassificationL1Empty")
            layout.addWidget(empty)
        self._update_classification_l1_filter_buttons()
        self.classification_members_layout.addWidget(card)

    def _render_classification_explorer(self) -> None:
        """依目前 typed mapping 投影靜態階層，不推導方向或關係。"""
        self._clear_classification_explorer(collapse=False)
        snapshot = self._snapshot
        index = self.theme_filter.currentIndex()
        if snapshot is None or index <= 0 or index >= len(self._theme_options):
            return
        key = self._theme_options[index]
        if key is None:
            return
        try:
            presentation = build_theme_classification_presentation(
                snapshot, key[0], key[1]
            )
        except (TypeError, ValueError):
            self.classification_hierarchy_label.setText(
                f"{key[0]}　›　{key[1]}"
            )
            self.classification_members_status.setText(
                "此版本缺少可展開的原始分類列；下方既有成員表仍可使用。"
            )
            return

        # 僅保存 SHA 與所選鍵；子控制項不保留舊 snapshot 或 DTO。
        self._classification_explorer_identity = presentation.snapshot_identity_sha256
        self._classification_explorer_key = key
        self.classification_hierarchy_label.setText(
            f"產業鏈：{presentation.chain_name}　›　題材：{presentation.theme_name}\n"
            "靜態分類層級；不表示供應、客戶、資金或因果方向。"
        )
        total = len(presentation.members)
        self._add_classification_l1_summary(presentation, total)
        displayed_members = presentation.members[:self._classification_explorer_member_limit]
        members_by_tier: dict[str, list[ThemeClassificationMember]] = {}
        tier_totals: dict[str, int] = {}
        for member in presentation.members:
            tier = self._classification_value(member.chain_tier)
            tier_totals[tier] = tier_totals.get(tier, 0) + 1
        for member in displayed_members:
            tier = self._classification_value(member.chain_tier)
            members_by_tier.setdefault(tier, []).append(member)

        for tier, members in members_by_tier.items():
            tier_group = QGroupBox(
                f"成員分類位置：{tier}（圖中 {len(members)} / 共 {tier_totals[tier]} 位）"
            )
            tier_group.setObjectName("industryThemeClassificationTier")
            tier_group.setAccessibleName(
                f"成員分類位置 {tier}，圖中 {len(members)} 位，共 {tier_totals[tier]} 位"
            )
            tier_layout = QGridLayout(tier_group)
            tier_layout.setContentsMargins(6, 6, 6, 6)
            tier_layout.setHorizontalSpacing(6)
            tier_layout.setVerticalSpacing(4)
            for member_index, member in enumerate(members):
                stock_name = self._classification_value(member.stock_name)
                button = QPushButton(f"{member.stock_id}　{stock_name}")
                button.setObjectName("industryThemeClassificationMemberButton")
                button.setAccessibleName(
                    f"分類成員 {member.stock_id} {stock_name}，位置 {tier}；"
                    "按下後定位下方題材成員表"
                )
                button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
                button.setProperty(
                    "classificationSnapshotIdentity",
                    presentation.snapshot_identity_sha256,
                )
                button.setProperty("classificationChainName", key[0])
                button.setProperty("classificationThemeName", key[1])
                button.setProperty("classificationStockId", member.stock_id)
                button.setToolTip(
                    f"股票：{member.stock_id}　{stock_name}\n"
                    f"市場：{self._classification_value(member.market_type)}\n"
                    f"L1 產業：{self._classification_value(member.l1_industry_category)}\n"
                    f"分類位置：{tier}\n"
                    f"主要分類：{'是' if member.is_primary else '否'}\n"
                    f"分配方法：{self._classification_value(member.assignment_method)}\n"
                    f"來源：{self._classification_value(member.source_name)}\n"
                    f"來源層級：{self._classification_value(member.source_tier)}\n"
                    f"PIT 模式：{self._classification_value(member.pit_mode)}\n"
                    f"證據：{self._classification_value(member.evidence_note)}\n"
                    f"映射資料日：{self._classification_value(member.snapshot_date)}\n"
                    f"可得日期：{self._classification_value(member.available_date)}\n"
                    f"版本 SHA-256：{presentation.snapshot_identity_sha256}\n"
                    "按下只定位下方既有成員表，不會開啟個股研究。"
                )
                button.clicked.connect(self._focus_classification_member)
                tier_layout.addWidget(button, member_index // 3, member_index % 3)
            self.classification_members_layout.addWidget(tier_group)

        shown = len(displayed_members)
        remaining = total - shown
        self._classification_members_base_status = (
            f"顯示 {shown} / {total} 位分類成員；資料日 {presentation.data_date}；"
            f"讀取時間 {presentation.known_at}；"
            f"映射版本／可得日 {presentation.mapping_snapshot_date}／"
            f"{presentation.mapping_available_date}；歷史 PIT 資格旗標 "
            f"{'是' if presentation.historical_pit_eligible else '否'}；版本 SHA-256 "
            f"{presentation.snapshot_identity_sha256}。"
            + (f"其餘 {remaining} 位請在下方既有題材成員表查閱。" if remaining else "")
        )
        self.classification_members_status.setText(
            self._classification_members_base_status
        )

    @Slot()
    def _focus_classification_member(self) -> None:
        button = self.sender()
        snapshot = self._snapshot
        if not isinstance(button, QPushButton) or snapshot is None:
            return
        identity = button.property("classificationSnapshotIdentity")
        chain_name = button.property("classificationChainName")
        theme_name = button.property("classificationThemeName")
        stock_id = button.property("classificationStockId")
        current_index = self.theme_filter.currentIndex()
        current_key = (
            self._theme_options[current_index]
            if 0 < current_index < len(self._theme_options) else None
        )
        if (
            self._closed or self._busy or type(identity) is not str
            or type(chain_name) is not str or type(theme_name) is not str
            or type(stock_id) is not str
            or identity != snapshot.identity_sha256
            or identity != self._classification_explorer_identity
            or (chain_name, theme_name) != current_key
            or (chain_name, theme_name) != self._classification_explorer_key
        ):
            return
        row_index = self._member_row_by_stock_id.get(stock_id)
        if row_index is None or not self._select_member_global_row(row_index):
            return

    def _on_member_cell_changed(
        self, _current_row: int, _current_column: int,
        _previous_row: int, _previous_column: int,
    ) -> None:
        self._navigation_selection_revision += 1
        self._refresh_member_action()

    def _refresh_member_action(self) -> None:
        item = self.member_table.item(self.member_table.currentRow(), 0)
        navigation = self.capture_selected_member_navigation(item.text()) if item else None
        self.open_member_button.setEnabled(navigation is not None)
        self.member_selection_label.setText(
            f"已選 {item.text()}｜沿目前題材版本研究" if navigation is not None and item else
            "先選取一檔成員股票。"
        )

    def _open_selected_member(self) -> None:
        item = self.member_table.item(self.member_table.currentRow(), 0)
        if item is not None and self.capture_selected_member_navigation(item.text()) is not None:
            self._emit_selected_stock(item)

    def _render_selected_theme(self) -> None:
        self._clear_classification_explorer(collapse=True)
        self._clear_theme_overlap(collapse=True)
        self.metrics_table.setRowCount(0)
        self._clear_metric_cards()
        self._member_stock_ids = ()
        self._member_row_by_stock_id = {}
        self._member_theme_key = None
        self._member_snapshot_identity = None
        self._member_page_index = 0
        self._render_member_page()
        self.selected_theme_summary.setText("選擇題材以對照原指標與成員。")
        self.selected_theme_summary.setToolTip("")
        self._refresh_member_action()
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
        report = self._snapshot.report if self._snapshot else None
        self.selected_theme_summary.setText(
            f"{row.chain_name}／{row.theme_name}｜"
            f"平均日漲跌 {self._display_decimal(row.mean_return_pct, suffix=' %')}｜"
            f"覆蓋 {self._coverage(coverage.returns, coverage.members)}｜"
            f"資料日 {report.data_date.isoformat() if report else '未提供'}"
        )
        self.selected_theme_summary.setToolTip(self._decimal_tooltip(row.mean_return_pct, suffix=" %"))
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
        self._render_metric_cards(metrics)
        self.metrics_table.setRowCount(len(metrics))
        for row_index, (label, displayed_value, available, tooltip) in enumerate(metrics):
            for column, value in enumerate((label, displayed_value, available)):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if column == 1 and tooltip:
                    item.setToolTip(tooltip)
                self.metrics_table.setItem(row_index, column, item)

        self._member_stock_ids = tuple(row.stock_ids)
        self._member_row_by_stock_id = {}
        for member_index, stock_id in enumerate(self._member_stock_ids):
            self._member_row_by_stock_id.setdefault(stock_id, member_index)
        self._member_theme_key = key
        self._member_snapshot_identity = (
            self._snapshot.identity_sha256 if self._snapshot is not None else None
        )
        self._member_page_index = 0
        self._render_member_page()
        self._refresh_member_action()

    def _render_member_page(self) -> None:
        """只建立目前題材成員頁面需要的有限表格列。"""

        visible_stock_ids = self._visible_member_stock_ids()
        total = len(visible_stock_ids)
        page_count = (total + self._MEMBER_PAGE_SIZE - 1) // self._MEMBER_PAGE_SIZE
        if page_count == 0:
            self._member_page_index = 0
        else:
            self._member_page_index = min(self._member_page_index, page_count - 1)
        start = self._member_page_index * self._MEMBER_PAGE_SIZE
        end = min(total, start + self._MEMBER_PAGE_SIZE)
        page_stock_ids = visible_stock_ids[start:end]
        blocker = QSignalBlocker(self.member_table)
        self.member_table.clearSelection()
        self.member_table.setCurrentCell(-1, -1)
        self.member_table.setRowCount(len(page_stock_ids))
        for page_row, stock_id in enumerate(page_stock_ids):
            mapping_row = self._mapping_by_theme_stock.get(
                (*self._member_theme_key, stock_id)
            ) if self._member_theme_key is not None else None
            name = self._mapping_text(mapping_row, "stock_name")
            chain_tier = self._mapping_text(mapping_row, "chain_tier")
            basis = self._mapping_basis(mapping_row)
            for column, value in enumerate((stock_id, name, chain_tier, basis)):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                item.setToolTip(value)
                self.member_table.setItem(page_row, column, item)
        self.member_table.resizeRowsToContents()
        self.member_table.clearSelection()
        self.member_table.setCurrentCell(-1, -1)
        del blocker
        QToolTip.hideText()
        self.member_table.setToolTip("")
        self._navigation_selection_revision += 1
        if total:
            if self._member_l1_filter_stock_ids is None:
                self.member_page_status_label.setText(
                    f"顯示 {start + 1}–{end} / {total} 位成員；"
                    f"第 {self._member_page_index + 1} / {page_count} 頁"
                )
            else:
                self.member_page_status_label.setText(
                    f"L1 篩選：{self._member_l1_filter_label}；"
                    f"顯示 {start + 1}–{end} / {total} 位符合成員"
                    f"（本題材 {len(self._member_stock_ids)} 位）；"
                    f"第 {self._member_page_index + 1} / {page_count} 頁"
                )
        else:
            self.member_page_status_label.setText("顯示 0 / 0 位成員")
        self.member_page_status_label.setAccessibleDescription(
            self.member_page_status_label.text()
        )
        self.member_page_previous_button.setEnabled(
            total > 0 and self._member_page_index > 0 and not self._busy and not self._closed
        )
        self.member_page_next_button.setEnabled(
            total > 0 and self._member_page_index + 1 < page_count
            and not self._busy and not self._closed
        )
        self._refresh_member_action()

    def _change_member_page(self, offset: int) -> None:
        if self._closed or self._busy or self._snapshot is None:
            return
        visible_stock_ids = self._visible_member_stock_ids()
        page_count = (
            len(visible_stock_ids) + self._MEMBER_PAGE_SIZE - 1
        ) // self._MEMBER_PAGE_SIZE
        target_page = self._member_page_index + offset
        if target_page < 0 or target_page >= page_count:
            return
        self._member_page_index = target_page
        self._render_member_page()

    def _select_member_global_row(self, row_index: int) -> bool:
        if (
            self._closed or self._busy or self._snapshot is None
            or self._member_snapshot_identity != self._snapshot.identity_sha256
            or self._member_theme_key is None
            or not 0 <= row_index < len(self._member_stock_ids)
        ):
            return False
        stock_id = self._member_stock_ids[row_index]
        visible_stock_ids = self._visible_member_stock_ids()
        if stock_id not in visible_stock_ids:
            # 既有搜尋／分類成員下鑽仍定位原題材列；目標列不在篩選內時，
            # 先明確還原完整清單，再沿原始列索引完成定位。
            had_l1_filter = self._member_l1_filter_stock_ids is not None
            self._clear_member_l1_filter(render_table=True)
            if had_l1_filter and self._classification_members_base_status:
                self.classification_members_status.setText(
                    self._classification_members_base_status
                )
            self._update_classification_l1_filter_buttons()
            visible_stock_ids = self._member_stock_ids
        try:
            visible_row_index = visible_stock_ids.index(stock_id)
        except ValueError:
            return False
        target_page = visible_row_index // self._MEMBER_PAGE_SIZE
        if target_page != self._member_page_index:
            self._member_page_index = target_page
            self._render_member_page()
        else:
            self.member_table.clearSelection()
            self.member_table.setCurrentCell(-1, -1)
            QToolTip.hideText()
            self.member_table.setToolTip("")
            self._navigation_selection_revision += 1
            self._refresh_member_action()
        page_row = visible_row_index - self._member_page_index * self._MEMBER_PAGE_SIZE
        item = self.member_table.item(page_row, 0)
        if item is None or item.text() != visible_stock_ids[visible_row_index]:
            return False
        self.member_table.setCurrentItem(item)
        self.member_table.selectRow(page_row)
        self.member_table.scrollToItem(
            item, QAbstractItemView.ScrollHint.PositionAtCenter
        )
        self.scroll_area.ensureWidgetVisible(self.members_group, 0, 0)
        self.scroll_area.ensureWidgetVisible(self.member_table, 0, 0)
        return True

    def _clear_metric_cards(self) -> None:
        self.metrics_card_labels.clear()
        self.metrics_cards_group.setVisible(False)
        self.theme_detail_splitter.setMinimumHeight(0)
        self._metric_card_columns = 0
        for layout in self.metrics_card_rows:
            while layout.count():
                item = layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()
        self._metric_card_widgets.clear()

    def _arrange_metric_cards(self) -> None:
        # 主頁 1280 寬時此欄只約 40% 畫面；三欄會擠掉長名稱與數值。
        columns = 3 if self.metrics_group.width() >= 640 else 2
        if columns == self._metric_card_columns:
            return
        for layout in self.metrics_card_rows:
            while layout.count():
                layout.takeAt(0)
        for index, card in enumerate(self._metric_card_widgets):
            self.metrics_card_rows[index // columns].addWidget(card, 1)
        self._metric_card_columns = columns
        rows = (len(self._metric_card_widgets) + columns - 1) // columns
        cards_height = rows * 108 + max(0, rows - 1) * 6 + 36
        self.metrics_cards_group.setMinimumHeight(cards_height)
        self.theme_detail_splitter.setMinimumHeight(
            cards_height + self.metrics_table.minimumHeight() + 60
        )
        self.metrics_cards_group.updateGeometry()

    def _render_metric_cards(
        self, metrics: tuple[tuple[str, str, str, str], ...],
    ) -> None:
        self._clear_metric_cards()
        for label, displayed_value, coverage, tooltip in metrics:
            card = QWidget(self.metrics_cards_group)
            card.setObjectName("industryThemeMetricCard")
            card.setMinimumHeight(108)
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(8, 6, 8, 6)
            card_layout.setSpacing(2)
            title = QLabel(label, card)
            title.setAccessibleName(f"{label}指標名稱")
            title.setWordWrap(True)
            title.setTextFormat(Qt.TextFormat.PlainText)
            value = QLabel(displayed_value, card)
            value.setAccessibleName(f"{label}觀察值")
            value.setWordWrap(True)
            value.setTextFormat(Qt.TextFormat.PlainText)
            value.setStyleSheet("font-size: 16px; font-weight: 600;")
            denominator = QLabel(f"覆蓋：{coverage}", card)
            denominator.setAccessibleName(f"{label}覆蓋數")
            denominator.setWordWrap(True)
            denominator.setTextFormat(Qt.TextFormat.PlainText)
            for widget in (title, value, denominator):
                widget.setToolTip(tooltip)
                card_layout.addWidget(widget)
            card.setToolTip(tooltip)
            card.setStyleSheet(
                "QWidget#industryThemeMetricCard { "
                f"background-color: {MIDNIGHT_ANALYST.surface_2}; "
                f"border: 1px solid {MIDNIGHT_ANALYST.border}; "
                "border-radius: 4px; }"
            )
            self._metric_card_widgets.append(card)
            self.metrics_card_labels.append((title, value, denominator))
        self._arrange_metric_cards()
        self.metrics_cards_group.setVisible(bool(metrics))

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
        self._clear_metric_cards()
        self.member_table.setRowCount(0)
        self.member_table.clearSelection()
        self.member_table.setCurrentCell(-1, -1)
        self.member_page_status_label.setText("顯示 0 / 0 位成員")
        self.member_page_status_label.setAccessibleDescription(
            self.member_page_status_label.text()
        )
        self.member_page_previous_button.setEnabled(False)
        self.member_page_next_button.setEnabled(False)

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
        selected_theme = (
            0 < self.theme_filter.currentIndex() < len(self._theme_options)
            and self._theme_options[self.theme_filter.currentIndex()] is not None
        )
        self.classification_explorer_toggle.setEnabled(
            available and not self._busy and selected_theme
        )
        self.theme_overlap_toggle.setEnabled(
            available and not self._busy and selected_theme
        )
        member_page_count = (
            len(self._visible_member_stock_ids()) + self._MEMBER_PAGE_SIZE - 1
        ) // self._MEMBER_PAGE_SIZE
        self.member_page_previous_button.setEnabled(
            available and not self._busy and self._member_page_index > 0
        )
        self.member_page_next_button.setEnabled(
            available and not self._busy
            and self._member_page_index + 1 < member_page_count
        )
        self._update_classification_l1_filter_buttons()
        self._refresh_member_action()
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
        self._update_theme_search_controls()
        self._update_chain_directory_controls()
        self._update_return_tile_controls()
        self._update_turnover_treemap_controls()
        self._update_comparison_controls()
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
