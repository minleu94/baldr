"""每日市場研究快照的唯讀瀏覽與明示更新入口。"""

from __future__ import annotations

from ui_qt.research_universe_presentation import research_universe_text

from datetime import date, datetime, time
from typing import Callable, Mapping, Sequence, cast
from zoneinfo import ZoneInfo

from PySide6.QtCore import QDate, QSignalBlocker, Qt, QTime, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from app_module.research_session import ResearchStockContextDTO
from app_module.daily_market_cohort_projection import (
    DailyMarketCohortSortKey,
    project_daily_market_cohort,
    sort_daily_market_cohort_members,
)
from app_module.daily_market_research_screener import DailyMarketResearchScreenRow
from app_module.original_stock_ranking import VerifiedOriginalStockRanking
from app_module.daily_market_snapshot_repository import VerifiedDailyMarketSnapshot
from app_module.daily_market_research_bookmark import (
    create_daily_market_research_bookmark,
)
from app_module.daily_market_research_presets import (
    DAILY_MARKET_RESEARCH_PRESETS,
    ResearchFilterPreset,
    get_research_filter_preset,
    match_research_filter_preset,
    summarize_research_candidates,
)
from ui_qt.theme import MIDNIGHT_ANALYST
from ui_qt.original_ranking_presentation import (
    original_rank_cell,
    original_rank_row_tooltip,
    ranking_audit_tooltip,
    ranking_matches_snapshot,
    ranking_rows_by_code,
    ranking_summary_text,
    ranking_window_text,
    sort_by_original_rank,
)
from ui_qt.widgets.table_style import apply_financial_table_style
from ui_qt.workers.task_worker import TaskWorker


_TAIPEI = ZoneInfo("Asia/Taipei")
_CONDITION_LABELS = {
    "close_above_ma20": "收盤價高於 MA20",
    "close_above_ma60": "收盤價高於 MA60",
}
_STATE_LABELS = {
    "match": "符合",
    "no_match": "不符合",
    "unknown": "未知",
}
_RELATION_LABELS = {
    "above": "高於",
    "below": "低於",
    "equal": "相等",
    "unknown": "關係未知",
}
_FILTER_VALUES = ("all", "match", "no_match", "unknown")


class DailyMarketResearchView(QWidget):
    """只讀呈現已發布快照，並由使用者明示啟動有界更新。"""

    stockResearchRequested = Signal(object)
    snapshotAccepted = Signal(object)
    snapshotCleared = Signal()
    originalRankingAccepted = Signal(object)
    originalRankingCleared = Signal()
    bookmarkSaved = Signal(object)

    def __init__(
        self,
        service: object | None = None,
        parent: QWidget | None = None,
        watchlist_service: object | None = None,
        *,
        bookmark_confirmation_callback: Callable[[object], bool] | None = None,
    ) -> None:
        super().__init__(parent)
        self.service = service
        self.watchlist_service = watchlist_service
        self.bookmark_confirmation_callback = bookmark_confirmation_callback
        self._snapshot: object | None = None
        self._cohort_projection: object | None = None
        self._cohort_members_by_code: dict[str, object] = {}
        self._original_ranking: VerifiedOriginalStockRanking | None = None
        self._original_ranking_error = ""
        self._original_ranking_pending = False
        self._cohort_full_rows: tuple[object, ...] = ()
        self._all_rows: tuple[object, ...] = ()
        self._visible_rows: tuple[object, ...] = ()
        self._manifest_sha256 = ""
        self._manifest_identity_sha256 = ""
        self._loaded_cohort_id = ""
        self._loaded_decision_date = ""
        self._worker: TaskWorker | None = None
        self._operation_generation = 0
        self._initial_read_started = False
        self._shutting_down = False
        self._selected_stock_code = ""
        self._build_ui()
        self._set_service_availability()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        title = QLabel("每日研究條件")
        title.setObjectName("dailyMarketResearchTitle")
        title.setAccessibleName("每日研究條件")
        title.setStyleSheet(
            f"color: {MIDNIGHT_ANALYST.text_primary}; font-size: 15px; font-weight: 700;"
        )
        root.addWidget(title)

        self.disclaimer_label = QLabel(
            "研究快照：僅表示明示 cohort 的既有 close／MA20／MA60 條件，"
            "不是全市場、正式推薦、獲利機率或交易資格。未知條件會保留為未知。"
        )
        self.disclaimer_label.setObjectName("dailyMarketResearchDisclaimer")
        self.disclaimer_label.setAccessibleName("每日研究條件安全說明")
        self.disclaimer_label.setWordWrap(True)
        self.disclaimer_label.setStyleSheet(
            f"color: {MIDNIGHT_ANALYST.text_secondary}; "
            f"background: {MIDNIGHT_ANALYST.surface_2}; "
            f"border-left: 4px solid {MIDNIGHT_ANALYST.accent}; padding: 7px;"
        )
        root.addWidget(self.disclaimer_label)

        inputs = QGroupBox("研究範圍與條件")
        inputs.setObjectName("dailyMarketResearchInputs")
        form = QFormLayout(inputs)
        form.setContentsMargins(10, 8, 10, 8)
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(7)

        self.stock_codes_input = QLineEdit("2382,1477")
        self.stock_codes_input.setObjectName("dailyMarketResearchStockCodes")
        self.stock_codes_input.setAccessibleName("每日研究股票代碼")
        self.stock_codes_input.setPlaceholderText("以逗號分隔，最多 16 檔，例如 2382,1477")
        self.stock_codes_input.setMaxLength(256)
        form.addRow("股票代碼（最多 16 檔）", self.stock_codes_input)

        self.cohort_id_input = QLineEdit("daily-market-research")
        self.cohort_id_input.setObjectName("dailyMarketResearchCohortId")
        self.cohort_id_input.setAccessibleName("每日研究 cohort 識別")
        self.cohort_id_input.setMaxLength(160)
        form.addRow("研究 cohort", self.cohort_id_input)

        cutoff_row = QHBoxLayout()
        taipei_now = datetime.now(_TAIPEI)
        self.decision_date_edit = QDateEdit(
            QDate.fromString(taipei_now.date().isoformat(), Qt.DateFormat.ISODate)
        )
        self.decision_date_edit.setObjectName("dailyMarketResearchDecisionDate")
        self.decision_date_edit.setAccessibleName("每日研究基準日期")
        self.decision_date_edit.setCalendarPopup(True)
        self.decision_date_edit.setDisplayFormat("yyyy-MM-dd")
        self.decision_date_edit.setMaximumDate(
            QDate.fromString(taipei_now.date().isoformat(), Qt.DateFormat.ISODate)
        )
        self.decision_date_edit.setMinimumDate(QDate(1990, 1, 1))
        cutoff_row.addWidget(self.decision_date_edit)

        self.decision_time_edit = QTimeEdit(
            QTime.fromString(taipei_now.strftime("%H:%M:%S"), "HH:mm:ss")
        )
        self.decision_time_edit.setObjectName("dailyMarketResearchDecisionTime")
        self.decision_time_edit.setAccessibleName("每日研究台北時間截止時刻")
        self.decision_time_edit.setDisplayFormat("HH:mm:ss")
        cutoff_row.addWidget(QLabel("Asia/Taipei"))
        cutoff_row.addWidget(self.decision_time_edit)
        cutoff_row.addStretch(1)
        form.addRow("決策基準／截止時間", cutoff_row)

        condition_row = QHBoxLayout()
        self.ma20_checkbox = QCheckBox("收盤價高於 MA20")
        self.ma20_checkbox.setObjectName("dailyMarketResearchMa20")
        self.ma20_checkbox.setAccessibleName("使用收盤價高於 MA20 條件")
        self.ma20_checkbox.setChecked(True)
        condition_row.addWidget(self.ma20_checkbox)
        self.ma60_checkbox = QCheckBox("收盤價高於 MA60")
        self.ma60_checkbox.setObjectName("dailyMarketResearchMa60")
        self.ma60_checkbox.setAccessibleName("使用收盤價高於 MA60 條件")
        self.ma60_checkbox.setChecked(True)
        condition_row.addWidget(self.ma60_checkbox)
        self.combine_mode_combo = QComboBox()
        self.combine_mode_combo.setObjectName("dailyMarketResearchCombineMode")
        self.combine_mode_combo.setAccessibleName("每日研究條件組合方式")
        self.combine_mode_combo.addItem("全部符合（AND）", "AND")
        self.combine_mode_combo.addItem("任一符合（OR）", "OR")
        condition_row.addWidget(self.combine_mode_combo)
        condition_row.addStretch(1)
        form.addRow("條件規則", condition_row)

        preset_row = QHBoxLayout()
        self.preset_combo = QComboBox()
        self.preset_combo.setObjectName("dailyMarketResearchPreset")
        self.preset_combo.setAccessibleName("每日研究條件預設選擇")
        self._populate_research_presets()
        preset_row.addWidget(self.preset_combo)
        self.apply_preset_button = QPushButton("套用預設")
        self.apply_preset_button.setObjectName("dailyMarketResearchApplyPreset")
        self.apply_preset_button.setAccessibleName("明確套用每日研究條件預設")
        self.apply_preset_button.setEnabled(False)
        self.apply_preset_button.setToolTip(
            "只有按此按鈕才把選取預設套用到目前已核驗快照的篩選；不會重讀或產生資料。"
        )
        self.apply_preset_button.clicked.connect(self.apply_selected_preset)
        preset_row.addWidget(self.apply_preset_button)
        preset_row.addStretch(1)
        form.addRow("條件預設", preset_row)
        root.addWidget(inputs)

        self.preset_help_label = QLabel(
            "固定收盤價與 MA20／MA60 比較；MA20 需 20 個有效觀測、MA60 需 60 個，"
            "暖機不足保留為未知。僅供研究，沒有強弱排名或勝率含義；選取預設後須按「套用預設」。"
        )
        self.preset_help_label.setObjectName("dailyMarketResearchPresetHelp")
        self.preset_help_label.setAccessibleName("每日研究方法與預設使用說明")
        self.preset_help_label.setWordWrap(True)
        self.preset_help_label.setToolTip(
            "方法只比較已核驗快照提供的 close、MA20 與 MA60。需要的觀測暖機不足時維持未知；"
            "不推定交易日完整性、可得時間、historical PIT、預測能力或投資結論。"
        )
        root.addWidget(self.preset_help_label)

        self.market_cohort_group = QGroupBox("研究母體盤勢")
        self.market_cohort_group.setObjectName("dailyMarketResearchCohortSummary")
        cohort_layout = QVBoxLayout(self.market_cohort_group)
        cohort_layout.setContentsMargins(10, 7, 10, 7)
        cohort_layout.setSpacing(4)
        self.cohort_identity_label = QLabel(
            "尚未載入具名研究 cohort；此區不代表全市場。"
        )
        self.cohort_identity_label.setObjectName("dailyMarketResearchCohortIdentity")
        self.cohort_identity_label.setAccessibleName("研究母體來源、日期與方法雜湊")
        self.cohort_identity_label.setWordWrap(True)
        self.cohort_identity_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        cohort_layout.addWidget(self.cohort_identity_label)
        self.cohort_summary_label = QLabel(
            "固定方法的符合／不符合／未知分母尚未載入。"
        )
        self.cohort_summary_label.setObjectName("dailyMarketResearchCohortCounts")
        self.cohort_summary_label.setAccessibleName("研究母體固定方法三態計數")
        self.cohort_summary_label.setWordWrap(True)
        self.cohort_summary_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        cohort_layout.addWidget(self.cohort_summary_label)
        root.addWidget(self.market_cohort_group)

        action_row = QHBoxLayout()
        self.refresh_button = QPushButton("更新研究快照")
        self.refresh_button.setObjectName("dailyMarketResearchUpdateSnapshot")
        self.refresh_button.setAccessibleName("明示更新有界每日研究快照")
        self.refresh_button.setProperty("variant", "primary")
        self.refresh_button.setToolTip(
            "只有按此按鈕才執行有界快照產生；開啟頁面、排序與篩選不會產生資料。"
        )
        self.refresh_button.clicked.connect(self.start_snapshot_update)
        action_row.addWidget(self.refresh_button)

        self.reload_button = QPushButton("重讀已發布快照")
        self.reload_button.setObjectName("dailyMarketResearchReloadSnapshot")
        self.reload_button.setAccessibleName("唯讀重新核對每日研究快照")
        self.reload_button.setToolTip(
            "唯讀核對已發布的快照與目前來源；不會執行 producer。"
        )
        self.reload_button.clicked.connect(self.reload_published_snapshot)
        action_row.addWidget(self.reload_button)

        self.cancel_button = QPushButton("取消更新")
        self.cancel_button.setObjectName("dailyMarketResearchCancel")
        self.cancel_button.setAccessibleName("取消每日研究快照工作")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel_active_operation)
        action_row.addWidget(self.cancel_button)

        self.filter_state_combo = QComboBox()
        self.filter_state_combo.setObjectName("dailyMarketResearchFilterState")
        self.filter_state_combo.setAccessibleName("每日研究狀態篩選")
        for label, value in (
            ("全部", "all"),
            ("符合", "match"),
            ("不符合", "no_match"),
            ("未知", "unknown"),
        ):
            self.filter_state_combo.addItem(label, value)
        action_row.addStretch(1)
        action_row.addWidget(QLabel("顯示"))
        action_row.addWidget(self.filter_state_combo)
        root.addLayout(action_row)

        sort_row = QHBoxLayout()
        sort_row.addWidget(QLabel("名單排序"))
        self.sort_key_combo = QComboBox()
        self.sort_key_combo.setObjectName("sort_key_combo")
        self.sort_key_combo.setAccessibleName("研究母體名單排序欄位")
        for label, key in (
            ("股票代碼", "stock_code"),
            ("資料日", "data_date"),
            ("收盤價", "close"),
            ("MA20", "ma20"),
            ("MA60", "ma60"),
        ):
            self.sort_key_combo.addItem(label, key)
        self.sort_key_combo.addItem("原始強弱排名（未提供）", "original_strength_rank")
        rank_item = self.sort_key_combo.model().item(self.sort_key_combo.count() - 1)
        self.sort_key_combo.setItemText(
            self.sort_key_combo.count() - 1, "原始名次（原引擎）"
        )
        if rank_item is not None:
            rank_item.setEnabled(False)
            rank_item.setToolTip("此快照未提供原始強弱排名；不提供排名排序或篩選。")
        self.sort_key_combo.setEnabled(False)
        sort_row.addWidget(self.sort_key_combo)
        self.sort_direction_combo = QComboBox()
        self.sort_direction_combo.setObjectName("sort_direction_combo")
        self.sort_direction_combo.setAccessibleName("研究母體名單排序方向")
        self.sort_direction_combo.addItem("遞增", "asc")
        self.sort_direction_combo.addItem("遞減", "desc")
        self.sort_direction_combo.setEnabled(False)
        sort_row.addWidget(self.sort_direction_combo)
        sort_row.addStretch(1)
        root.addLayout(sort_row)

        original_rank_row = QHBoxLayout()
        original_rank_row.addWidget(QLabel("原排名期間"))
        self.original_rank_period_combo = QComboBox()
        self.original_rank_period_combo.setObjectName("original_rank_period_combo")
        self.original_rank_period_combo.setAccessibleName("原始排名期間")
        self.original_rank_period_combo.addItem("日比較", "day")
        self.original_rank_period_combo.addItem("週比較", "week")
        original_rank_row.addWidget(self.original_rank_period_combo)
        original_rank_row.addWidget(QLabel("原排名方向"))
        self.original_rank_direction_combo = QComboBox()
        self.original_rank_direction_combo.setObjectName("original_rank_direction_combo")
        self.original_rank_direction_combo.setAccessibleName("原始排名強弱方向")
        self.original_rank_direction_combo.addItem("強勢", "strong")
        self.original_rank_direction_combo.addItem("弱勢", "weak")
        original_rank_row.addWidget(self.original_rank_direction_combo)
        original_rank_row.addStretch(1)
        root.addLayout(original_rank_row)

        self.original_ranking_label = QLabel("原始排名：未知；尚未讀取不可變來源")
        self.original_ranking_label.setObjectName("dailyMarketOriginalRanking")
        self.original_ranking_label.setAccessibleName("原始排名來源狀態")
        self.original_ranking_label.setWordWrap(True)
        self.original_ranking_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        root.addWidget(self.original_ranking_label)

        self.summary_label = QLabel("尚未載入已發布研究快照。")
        self.summary_label.setObjectName("dailyMarketResearchSummary")
        self.summary_label.setAccessibleName("每日研究快照與狀態計數")
        self.summary_label.setWordWrap(True)
        self.summary_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        root.addWidget(self.summary_label)

        self.candidate_summary_label = QLabel(
            "候選母體分母與三態摘要尚未載入；不推估缺列或未知數。"
        )
        self.candidate_summary_label.setObjectName("dailyMarketResearchCandidateSummary")
        self.candidate_summary_label.setAccessibleName("每日研究候選母體摘要")
        self.candidate_summary_label.setWordWrap(True)
        self.candidate_summary_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        root.addWidget(self.candidate_summary_label)

        self.selected_summary_label = QLabel(
            "選取一列以查看支持、反證與資料限制；僅供研究，不是投資結論。"
        )
        self.selected_summary_label.setObjectName("dailyMarketResearchSelectedSummary")
        self.selected_summary_label.setAccessibleName("選取候選的證據與資料限制摘要")
        self.selected_summary_label.setWordWrap(True)
        self.selected_summary_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        root.addWidget(self.selected_summary_label)

        self.status_label = QLabel("首次開啟時只會唯讀核對已發布快照；不會自動更新。")
        self.status_label.setObjectName("dailyMarketResearchStatus")
        self.status_label.setAccessibleName("每日研究快照讀取狀態")
        self.status_label.setWordWrap(True)
        self.status_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        root.addWidget(self.status_label)

        self.results_table = QTableWidget(0, 10)
        self.results_table.setObjectName("dailyMarketResearchResults")
        self.results_table.setAccessibleName("每日研究條件結果")
        self.results_table.setHorizontalHeaderLabels(
            (
                "股票代碼",
                "資料日",
                "收盤／MA20",
                "收盤／MA60",
                "整體狀態",
                "理由／未知原因",
                "收盤價",
                "MA20",
                "MA60",
            )
        )
        self.results_table.setHorizontalHeaderItem(
            9, QTableWidgetItem("原始名次")
        )
        self.results_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.results_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.results_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.results_table.setAlternatingRowColors(True)
        self.results_table.setSortingEnabled(False)
        self.results_table.horizontalHeader().setStretchLastSection(True)
        self.results_table.horizontalHeader().setSectionResizeMode(
            0, self.results_table.horizontalHeader().ResizeMode.ResizeToContents
        )
        self.results_table.horizontalHeader().setSectionResizeMode(
            1, self.results_table.horizontalHeader().ResizeMode.ResizeToContents
        )
        apply_financial_table_style(self.results_table)
        self.results_table.itemSelectionChanged.connect(self._sync_open_button)
        self.results_table.itemSelectionChanged.connect(self._render_selected_summary)
        self.results_table.itemDoubleClicked.connect(lambda _item: self.open_selected_stock())
        root.addWidget(self.results_table, 1)

        self.open_selected_stock_button = QPushButton("開啟選中個股研究報告")
        self.open_selected_stock_button.setObjectName("dailyMarketResearchOpenStock")
        self.open_selected_stock_button.setAccessibleName("由研究快照開啟選中個股報告")
        self.open_selected_stock_button.setEnabled(False)
        self.open_selected_stock_button.clicked.connect(self.open_selected_stock)

        self.bookmark_selected_research_button = QPushButton("收藏此研究")
        self.bookmark_selected_research_button.setObjectName(
            "dailyMarketResearchBookmark"
        )
        self.bookmark_selected_research_button.setAccessibleName("收藏此研究")
        self.bookmark_selected_research_button.setToolTip(
            "確認後，將目前選取列與完整快照來源、日期、方法及查詢條件保存到既有觀察清單。"
        )
        self.bookmark_selected_research_button.setEnabled(False)
        self.bookmark_selected_research_button.clicked.connect(
            self.bookmark_selected_research
        )
        self.open_selected_stock_button.setMinimumHeight(34)
        self.bookmark_selected_research_button.setMinimumHeight(34)
        research_actions = QHBoxLayout()
        research_actions.addWidget(self.open_selected_stock_button, 1)
        research_actions.addWidget(self.bookmark_selected_research_button, 1)
        root.addLayout(research_actions)

        for widget in (
            self.stock_codes_input,
            self.cohort_id_input,
            self.decision_date_edit,
            self.decision_time_edit,
            self.ma20_checkbox,
            self.ma60_checkbox,
            self.combine_mode_combo,
            self.filter_state_combo,
            self.sort_key_combo,
            self.sort_direction_combo,
            self.original_rank_period_combo,
            self.original_rank_direction_combo,
        ):
            if isinstance(widget, QCheckBox):
                widget.toggled.connect(self._apply_filter_controls)
            elif isinstance(widget, QComboBox):
                if widget is self.sort_key_combo:
                    widget.currentIndexChanged.connect(self._on_sort_key_changed)
                elif widget is self.sort_direction_combo:
                    widget.currentIndexChanged.connect(self._render_rows)
                elif widget in (
                    self.original_rank_period_combo,
                    self.original_rank_direction_combo,
                ):
                    widget.currentIndexChanged.connect(
                        self._request_original_ranking_read
                    )
                else:
                    widget.currentIndexChanged.connect(self._apply_filter_controls)

    def _populate_research_presets(self) -> None:
        for preset in DAILY_MARKET_RESEARCH_PRESETS:
            preset_id = preset.preset_id.strip()
            label = preset.label.strip() or preset_id
            if not preset_id:
                continue
            self.preset_combo.addItem(label, preset_id)
            index = self.preset_combo.count() - 1
            description = preset.description
            if description:
                self.preset_combo.setItemData(
                    index, description, Qt.ItemDataRole.ToolTipRole
                )
        if self.preset_combo.count() == 0:
            self.preset_combo.addItem("預設尚未提供", "")
            self.preset_combo.setEnabled(False)
            self.preset_combo.setToolTip(
                "預設 API 尚未載入；仍可使用 MA20／MA60 手動條件。"
            )
            return
        default_index = self.preset_combo.findData("all_observations")
        if default_index >= 0:
            self.preset_combo.setCurrentIndex(default_index)
        self.preset_combo.currentIndexChanged.connect(self._show_pending_preset_help)

    def _show_pending_preset_help(self, *_args: object) -> None:
        preset = self._get_research_preset(str(self.preset_combo.currentData() or ""))
        if preset is None:
            return
        description = preset.description.strip()
        if description:
            self.preset_combo.setToolTip(
                f"待套用：{description}\n目前查詢不會因選取此項而改變；按「套用預設」才更新篩選。"
            )

    @staticmethod
    def _get_research_preset(preset_id: str) -> ResearchFilterPreset | None:
        try:
            return get_research_filter_preset(preset_id)
        except ValueError:
            return None

    def get_active_preset_id(self) -> str | None:
        """回傳目前手動條件精確符合的 preset ID；自訂組合回傳 None。"""

        try:
            value = match_research_filter_preset(
                self._selected_condition_keys(),
                str(self.combine_mode_combo.currentData() or "AND"),
                str(self.filter_state_combo.currentData() or "all"),
            )
        except (TypeError, ValueError):
            return None
        return str(value) if value else None

    def apply_selected_preset(self) -> bool:
        """明確套用選取預設到目前已載入 snapshot 的本機篩選。"""

        worker_busy = self._worker is not None and self._worker.isRunning()
        if (
            self._snapshot is None
            or self.service is None
            or self._shutting_down
            or worker_busy
        ):
            self.status_label.setText(
                "目前無法套用預設：需要已核驗且閒置的研究快照；未讀取或產生資料。"
            )
            return False
        preset_id = str(self.preset_combo.currentData() or "").strip()
        preset = self._get_research_preset(preset_id)
        if preset is None:
            self.status_label.setText("選取的研究預設不可用；目前快照與篩選未變。")
            return False
        condition_keys = tuple(
            str(key)
            for key in tuple(getattr(preset, "condition_keys", ()) or ())
        )
        if not condition_keys or any(
            key not in {"close_above_ma20", "close_above_ma60"}
            for key in condition_keys
        ):
            self.status_label.setText("研究預設條件不受支援；目前快照與篩選未變。")
            return False
        combine_mode = str(getattr(preset, "combine_mode", "") or "").upper()
        filter_state = str(getattr(preset, "filter_state", "") or "")
        if combine_mode not in {"AND", "OR"} or filter_state not in _FILTER_VALUES:
            self.status_label.setText("研究預設的組合方式或狀態篩選無效；目前快照未變。")
            return False
        blockers = [
            QSignalBlocker(widget)
            for widget in (
                self.ma20_checkbox,
                self.ma60_checkbox,
                self.combine_mode_combo,
                self.filter_state_combo,
            )
        ]
        self.ma20_checkbox.setChecked("close_above_ma20" in condition_keys)
        self.ma60_checkbox.setChecked("close_above_ma60" in condition_keys)
        self.combine_mode_combo.setCurrentIndex(
            max(0, self.combine_mode_combo.findData(combine_mode))
        )
        self.filter_state_combo.setCurrentIndex(
            max(0, self.filter_state_combo.findData(filter_state))
        )
        del blockers
        self._apply_filter_controls()
        label = preset.label or preset_id
        self.status_label.setText(
            f"已套用「{label}」到目前已核驗快照；來源、日期與 hash 保持固定，未呼叫 producer。"
        )
        return True

    def _set_service_availability(self) -> None:
        available = self.service is not None
        self.refresh_button.setEnabled(available)
        self.reload_button.setEnabled(available)
        can_read_original = callable(
            getattr(self.service, "read_original_ranking", None)
        )
        self.original_rank_period_combo.setEnabled(can_read_original)
        self.original_rank_direction_combo.setEnabled(can_read_original)
        self.apply_preset_button.setEnabled(
            available and self._snapshot is not None and not self._shutting_down
        )
        self._sync_original_rank_sort_controls()
        if not available:
            self.status_label.setText("每日研究快照服務尚未接線；目前不會執行讀取或更新。")

    def _sync_original_rank_sort_controls(self, *, busy: bool = False) -> None:
        verified = (
            self._snapshot is not None
            and self._cohort_projection is not None
            and self._original_ranking is not None
        )
        rank_index = self.sort_key_combo.findData("original_strength_rank")
        rank_item = self.sort_key_combo.model().item(rank_index) if rank_index >= 0 else None
        if rank_item is not None:
            rank_item.setText("原始名次（原引擎）" if verified else "原始名次（未提供相容來源）")
            rank_item.setEnabled(verified and not busy)
            rank_item.setToolTip(
                "只使用已核驗的原生名次；缺名次列保持未知並置於末端。"
                if verified
                else "原始排名來源尚未核驗；目前不可排序。"
            )
        projection_ready = self._cohort_projection is not None
        self.sort_key_combo.setEnabled(projection_ready and not busy)
        selected_key = str(self.sort_key_combo.currentData() or "stock_code")
        if selected_key == "original_strength_rank" and not verified:
            blocker = QSignalBlocker(self.sort_key_combo)
            self.sort_key_combo.setCurrentIndex(
                max(0, self.sort_key_combo.findData("stock_code"))
            )
            del blocker
            selected_key = "stock_code"
            self._set_sort_direction_ascending()
        self.sort_direction_combo.setEnabled(
            projection_ready and not busy and selected_key != "original_strength_rank"
        )

    def _set_sort_direction_ascending(self) -> None:
        blocker = QSignalBlocker(self.sort_direction_combo)
        index = self.sort_direction_combo.findData("asc")
        if index >= 0:
            self.sort_direction_combo.setCurrentIndex(index)
        del blocker

    def _on_sort_key_changed(self, *_args: object) -> None:
        if str(self.sort_key_combo.currentData() or "") == "original_strength_rank":
            self._set_sort_direction_ascending()
        busy = self._worker is not None and self._worker.isRunning()
        self._sync_original_rank_sort_controls(busy=busy)
        self._render_rows()

    def _request_original_ranking_read(self, *_args: object) -> None:
        if self._shutting_down:
            return
        reader = getattr(self.service, "read_original_ranking", None)
        if not callable(reader):
            self._original_ranking_pending = False
            self._fail_original_ranking("reader unavailable")
            self.original_rank_period_combo.setEnabled(False)
            self.original_rank_direction_combo.setEnabled(False)
            return
        snapshot = self._snapshot
        if snapshot is None:
            self._original_ranking_pending = False
            self._original_ranking = None
            self.original_ranking_label.setText(
                "原始排名：未知；讀取已核驗 snapshot 後才會查詢來源。"
            )
            self.original_ranking_label.setToolTip("")
            self._sync_original_rank_sort_controls()
            return
        period = str(self.original_rank_period_combo.currentData() or "day")
        direction = str(self.original_rank_direction_combo.currentData() or "strong")
        if self._original_ranking is not None and ranking_matches_snapshot(
            snapshot,
            self._original_ranking,
            period=period,
            direction=direction,
        ):
            self._original_ranking_pending = False
            return
        self._clear_original_ranking(
            "原始排名讀取中；名次暫為未知。",
            clear_projection=True,
        )
        worker = self._worker
        if worker is not None and worker.isRunning():
            self._original_ranking_pending = True
            return
        self._original_ranking_pending = False

        def operation(_cancel_callback: Callable[[], bool]) -> object:
            return reader(snapshot, period=period, direction=direction)

        self._start_operation("original_ranking_read", operation)

    def _accept_original_ranking(self, generation: int, ranking: object) -> None:
        if generation != self._operation_generation or self._shutting_down:
            return
        if self._original_ranking_pending:
            self._clear_original_ranking(
                "舊 mode 的 readback 已捨棄；接著讀取目前選取 mode。",
                clear_projection=True,
            )
            return
        snapshot = self._snapshot
        period = str(self.original_rank_period_combo.currentData() or "day")
        direction = str(self.original_rank_direction_combo.currentData() or "strong")
        if snapshot is None or not ranking_matches_snapshot(
            snapshot,
            ranking,
            period=period,
            direction=direction,
        ):
            self._fail_original_ranking("讀回來源身份或模式與已接受的 snapshot 不符")
            return
        if ranking_rows_by_code(ranking) is None:
            self._fail_original_ranking("原生排名列未通過消費端格式核對")
            return
        self._original_ranking = ranking
        self._original_ranking_error = ""
        self._original_ranking_pending = False
        self.original_ranking_label.setText(ranking_summary_text(ranking))
        self.original_ranking_label.setToolTip(original_rank_row_tooltip(ranking, None))
        self._project_market_cohort(snapshot)
        self._render_candidate_summary()
        self._render_rows()
        self._sync_original_rank_sort_controls()
        self.originalRankingAccepted.emit(ranking)

    def _clear_original_ranking(
        self,
        message: str,
        *,
        clear_projection: bool = False,
    ) -> None:
        self._original_ranking = None
        self._original_ranking_error = message
        if clear_projection and self._snapshot is not None:
            self._project_market_cohort(self._snapshot)
        self.original_ranking_label.setText(f"原始排名：未知；{message}")
        self.original_ranking_label.setToolTip(message)
        self._sync_original_rank_sort_controls(
            busy=self._worker is not None and self._worker.isRunning()
        )
        self.originalRankingCleared.emit()

    def _fail_original_ranking(self, message: str) -> None:
        self._original_ranking_pending = False
        short_message = str(message).splitlines()[0].strip() or "原始來源不可用"
        self._clear_original_ranking(
            f"來源不可用或身份不符（{short_message}）；名次保持未知。",
            clear_projection=True,
        )
        self.status_label.setText(
            f"原始排名未核驗；{short_message}；snapshot 研究結果仍可檢視。"
        )
        self.original_ranking_label.setToolTip(str(message))

    def on_first_open(self) -> None:
        """第一次切入此來源時唯讀核對 latest，不啟動 producer。"""

        if self._initial_read_started or self._shutting_down or self.service is None:
            return
        self._initial_read_started = True
        reader = getattr(self.service, "read_latest", None)
        if not callable(reader):
            self.status_label.setText("讀取服務尚未提供 latest 核對入口；可按「重讀已發布快照」。")
            return
        cohort_id = self.cohort_id_input.text().strip()
        if not cohort_id:
            self.status_label.setText("請先輸入研究 cohort，再唯讀核對已發布快照。")
            return

        def operation(cancel_callback: Callable[[], bool]) -> object:
            return reader(cohort_id, cancel_callback=cancel_callback)

        self._start_operation("initial_read", operation)

    def open_latest_research(self, context: object) -> bool:
        """依書籤的 cohort／條件明確唯讀載入最新已發布快照，不觸發 producer。"""

        if self.service is None or self._shutting_down:
            self.status_label.setText("每日研究服務不可用；未切換研究來源。")
            return False
        if self._worker is not None and self._worker.isRunning():
            self.status_label.setText("每日研究讀取仍在執行；目前無法切換來源。")
            return False
        if str(getattr(context, "source_kind", "") or "") != (
            "daily_market_research_snapshot"
        ):
            self.status_label.setText("此 context 不是每日研究書籤；未讀取其他來源。")
            return False
        cohort_id = str(
            getattr(context, "daily_snapshot_cohort_id", "") or ""
        ).strip()
        condition_keys = tuple(
            part.strip()
            for part in str(
                getattr(context, "daily_snapshot_condition_keys", "") or ""
            ).split(",")
            if part.strip()
        )
        combine_mode = str(
            getattr(context, "daily_snapshot_combine_mode", "") or ""
        ).upper()
        if (
            not cohort_id
            or not condition_keys
            or any(key not in {"close_above_ma20", "close_above_ma60"} for key in condition_keys)
            or combine_mode not in {"AND", "OR"}
        ):
            self.status_label.setText(
                "書籤缺少有效 cohort、條件或 AND／OR；拒絕改用其他來源。"
            )
            return False
        reader = getattr(self.service, "read_latest_published_snapshot", None)
        if not callable(reader):
            reader = getattr(self.service, "read_latest", None)
        if not callable(reader):
            self.status_label.setText("研究服務未提供唯讀 latest 入口；未更新快照。")
            return False

        blockers = [
            QSignalBlocker(widget)
            for widget in (
                self.cohort_id_input,
                self.ma20_checkbox,
                self.ma60_checkbox,
                self.combine_mode_combo,
            )
        ]
        self.cohort_id_input.setText(cohort_id)
        self.ma20_checkbox.setChecked("close_above_ma20" in condition_keys)
        self.ma60_checkbox.setChecked("close_above_ma60" in condition_keys)
        self.combine_mode_combo.setCurrentIndex(
            max(0, self.combine_mode_combo.findData(combine_mode))
        )
        del blockers

        def operation(cancel_callback: Callable[[], bool]) -> object:
            return reader(cohort_id, cancel_callback=cancel_callback)

        self._initial_read_started = True
        self.status_label.setText(
            f"明確要求唯讀讀取 cohort {cohort_id} 的最新已發布快照；未呼叫 producer。"
        )
        self._start_operation("latest_research_read", operation)
        return True

    def reload_published_snapshot(self) -> None:
        """唯讀重讀指定 cohort／日期的已發布快照。"""

        if self.service is None or self._shutting_down:
            return
        cohort_id = self.cohort_id_input.text().strip()
        if not cohort_id:
            self._show_input_error("請輸入研究 cohort。")
            return
        reader = getattr(self.service, "read_snapshot", None)
        if not callable(reader):
            self._show_input_error("快照讀取服務尚未提供。")
            return
        try:
            selected_date = self._selected_decision_date()
        except ValueError as exc:
            self._show_input_error(str(exc))
            return

        def operation(cancel_callback: Callable[[], bool]) -> object:
            return reader(
                cohort_id,
                selected_date,
                cancel_callback=cancel_callback,
            )

        self._start_operation("read", operation)

    def start_snapshot_update(self) -> None:
        """只有明示按下更新按鈕才執行 bounded producer。"""

        if self.service is None or self._shutting_down:
            return
        if self._snapshot is not None and "research_universe" in self._snapshot.manifest:
            self._show_input_error(
                "此快照已綁定母體設定；請用隔離 CLI 的 --universe-config 明示原設定或新版本，"
                "不能由手動股票欄位改寫來源。"
            )
            return
        producer = getattr(self.service, "produce_snapshot", None)
        if not callable(producer):
            self._show_input_error("快照更新服務尚未提供。")
            return
        try:
            stock_codes = self._selected_stock_codes()
            cohort_id = self.cohort_id_input.text().strip()
            if not cohort_id:
                raise ValueError("請輸入研究 cohort。")
            condition_keys = self._selected_condition_keys()
            if not condition_keys:
                raise ValueError("至少選擇一條研究條件。")
            decision_cutoff = self._selected_decision_cutoff()
        except ValueError as exc:
            self._show_input_error(str(exc))
            return

        self._start_operation(
            "produce",
            lambda cancel_callback: self._produce_then_read(
                producer,
                cohort_id=cohort_id,
                stock_codes=stock_codes,
                decision_cutoff=decision_cutoff,
                cancel_callback=cancel_callback,
            ),
        )

    def _produce_then_read(
        self,
        producer: Callable[..., object],
        *,
        cohort_id: str,
        stock_codes: tuple[str, ...],
        decision_cutoff: datetime,
        cancel_callback: Callable[[], bool],
    ) -> dict[str, object]:
        result = producer(
            stock_codes,
            decision_cutoff,
            cohort_id,
            cancel_callback=cancel_callback,
        )
        status = str(getattr(result, "status", ""))
        if status not in {"published_complete", "unchanged"}:
            code = str(getattr(result, "error_code", "") or status or "update_not_published")
            message = str(getattr(result, "error_message", "") or "快照未發布。")
            raise RuntimeError(f"{code}: {message}")
        manifest_sha256 = str(getattr(result, "manifest_sha256", "") or "")
        if len(manifest_sha256) != 64:
            raise RuntimeError("producer_missing_manifest_sha256: 更新結果缺少已發布 manifest 身份。")
        reader = getattr(self.service, "read_snapshot", None)
        if not callable(reader):
            raise RuntimeError("snapshot_reader_missing: 快照讀取服務尚未提供。")
        snapshot = reader(
            cohort_id,
            decision_cutoff.date(),
            manifest_sha256=manifest_sha256,
            cancel_callback=cancel_callback,
        )
        return {"kind": "produce", "production": result, "snapshot": snapshot}

    def _start_operation(
        self,
        kind: str,
        operation: Callable[[Callable[[], bool]], object],
    ) -> None:
        if self._worker is not None and self._worker.isRunning():
            self.status_label.setText("已有快照讀取／更新工作進行中；請等待或先取消。")
            return
        self._operation_generation += 1
        generation = self._operation_generation
        self._initial_read_started = self._initial_read_started or kind == "initial_read"
        self._set_busy(True, kind)

        def task(cancel_callback: Callable[[], bool] | None = None) -> object:
            callback = cancel_callback or (lambda: False)
            try:
                return operation(callback)
            except Exception as exc:
                if type(exc).__name__ == "DailyMarketResearchCancelled" and callback():
                    return {"cancelled": True, "kind": kind}
                raise

        worker = TaskWorker(task)
        self._worker = worker
        worker.started.connect(lambda g=generation, op=kind: self._on_operation_started(g, op))
        worker.finished.connect(
            lambda result, g=generation, op=kind: self._on_operation_finished(g, op, result)
        )
        worker.error.connect(
            lambda message, g=generation, op=kind: self._on_operation_error(
                g, message, operation_kind=op
            )
        )
        worker.cancelled.connect(lambda g=generation: self._on_operation_cancelled(g))
        worker.native_thread_finished.connect(
            lambda current=worker, g=generation: self._on_worker_native_finished(current, g)
        )
        worker.start()

    def _set_busy(self, busy: bool, kind: str = "") -> None:
        if busy:
            self.status_label.setText(
                "正在明示更新有界研究快照；來源仍是研究用途。"
                if kind == "produce"
                else "正在唯讀核對已發布快照及當前來源身份…"
            )
        if not self._shutting_down:
            available = self.service is not None
            self.refresh_button.setEnabled(available and not busy)
            self.reload_button.setEnabled(available and not busy)
            self.preset_combo.setEnabled(not busy and self.preset_combo.count() > 0)
            self.apply_preset_button.setEnabled(
                available and self._snapshot is not None and not busy
            )
            self.cancel_button.setEnabled(busy)
            self.open_selected_stock_button.setEnabled(not busy and self._has_selected_row())
            self.bookmark_selected_research_button.setEnabled(
                not busy
                and self.watchlist_service is not None
                and self._snapshot is not None
                and self._has_selected_row()
            )
            for widget in (
                self.stock_codes_input,
                self.cohort_id_input,
                self.decision_date_edit,
                self.decision_time_edit,
                self.ma20_checkbox,
                self.ma60_checkbox,
                self.combine_mode_combo,
                self.filter_state_combo,
                self.preset_combo,
                self.sort_key_combo,
                self.sort_direction_combo,
                self.original_rank_period_combo,
                self.original_rank_direction_combo,
            ):
                widget.setEnabled(not busy)
            self.sort_key_combo.setEnabled(not busy and self._cohort_projection is not None)
            self.sort_direction_combo.setEnabled(
                not busy and self._cohort_projection is not None
            )
            can_read_original = callable(
                getattr(self.service, "read_original_ranking", None)
            )
            self.original_rank_period_combo.setEnabled(
                can_read_original and not busy
            )
            self.original_rank_direction_combo.setEnabled(
                can_read_original and not busy
            )
            self._sync_original_rank_sort_controls(busy=busy)

    def _on_operation_started(self, generation: int, kind: str) -> None:
        if generation == self._operation_generation and not self._shutting_down:
            self._set_busy(True, kind)

    def _on_operation_finished(self, generation: int, kind: str, result: object) -> None:
        if generation != self._operation_generation or self._shutting_down:
            return
        if isinstance(result, Mapping) and result.get("cancelled") is True:
            self._on_operation_cancelled(generation)
            return
        if kind == "original_ranking_read":
            self._accept_original_ranking(generation, result)
            return
        if kind == "produce" and isinstance(result, Mapping):
            production = result.get("production")
            snapshot = result.get("snapshot")
            if production is None or snapshot is None:
                self._on_operation_error(generation, "快照更新後未取得可核驗讀回。")
                return
            self._render_production_result(production)
            self._accept_snapshot(snapshot, sync_cutoff=True)
            if self._snapshot is snapshot:
                self.status_label.setText(
                    f"{self.status_label.text()}；讀回 manifest 與來源核驗完成。"
                )
            return
        self._accept_snapshot(
            result,
            sync_cutoff=kind in {"initial_read", "latest_research_read"},
        )

    def _on_operation_error(
        self,
        generation: int,
        message: str,
        *,
        operation_kind: str = "",
    ) -> None:
        if generation != self._operation_generation or self._shutting_down:
            return
        if operation_kind == "original_ranking_read":
            if self._original_ranking_pending:
                return
            self._fail_original_ranking(str(message))
            return
        short_message = str(message).splitlines()[0].strip() or "未知快照讀取錯誤"
        self.status_label.setText(
            f"已發布快照無法核驗，條件視為未知；{short_message}。"
            "返回每日研究條件更新快照，按「重讀已發布快照」核對，或明示更新。"
        )
        self.status_label.setToolTip(str(message))
        self._clear_current_snapshot()

    def _on_operation_cancelled(self, generation: int) -> None:
        if generation != self._operation_generation or self._shutting_down:
            return
        self.status_label.setText("快照工作已取消；未把未完成讀取呈現為有效結果。")

    def _on_worker_native_finished(self, worker: TaskWorker, generation: int) -> None:
        if self._worker is not worker:
            return
        self._worker = None
        if not self._shutting_down and generation == self._operation_generation:
            self._set_busy(False)
            self._sync_open_button()
            if self._original_ranking_pending and self._snapshot is not None:
                self._request_original_ranking_read()

    def cancel_active_operation(self) -> None:
        worker = self._worker
        if worker is None or not worker.isRunning():
            return
        self.status_label.setText("已送出合作式取消；等待目前有限來源讀取安全返回…")
        self.cancel_button.setEnabled(False)
        worker.cancel(cooperative=True, wait=False)

    def _accept_snapshot(self, snapshot: object, *, sync_cutoff: bool) -> None:
        manifest = getattr(snapshot, "manifest", None)
        if not isinstance(manifest, Mapping):
            self._on_operation_error(self._operation_generation, "快照讀回未提供已核驗 manifest。")
            return
        cohort_id = str(manifest.get("cohort_id") or "").strip()
        decision_date = str(manifest.get("decision_date") or "").strip()
        manifest_sha256 = str(getattr(snapshot, "manifest_sha256", "") or "")
        manifest_identity = str(getattr(snapshot, "manifest_identity_sha256", "") or "")
        if not cohort_id or not decision_date or len(manifest_sha256) != 64 or len(manifest_identity) != 64:
            self._on_operation_error(self._operation_generation, "快照 manifest 缺少 cohort／日期／hash 身份。")
            return
        try:
            parsed_date = date.fromisoformat(decision_date)
        except ValueError:
            self._on_operation_error(self._operation_generation, "快照決策日期不是 YYYY-MM-DD。")
            return
        if parsed_date.isoformat() != decision_date:
            self._on_operation_error(self._operation_generation, "快照決策日期不是 YYYY-MM-DD。")
            return
        self.results_table.clearSelection()
        self._snapshot = snapshot
        self._cohort_projection = None
        self._cohort_members_by_code = {}
        self._cohort_full_rows = ()
        self._original_ranking_pending = False
        self._manifest_sha256 = manifest_sha256
        self._manifest_identity_sha256 = manifest_identity
        self._loaded_cohort_id = cohort_id
        self._loaded_decision_date = decision_date
        self._selected_stock_code = ""
        self._clear_original_ranking(
            "snapshot 已接受；正在讀取綁定此 manifest 的原始來源。"
        )
        if sync_cutoff:
            blocker_date = QSignalBlocker(self.decision_date_edit)
            blocker_time = QSignalBlocker(self.decision_time_edit)
            self.decision_date_edit.setDate(
                QDate.fromString(decision_date, Qt.DateFormat.ISODate)
            )
            cutoff_text = str(manifest.get("decision_cutoff") or "")
            try:
                cutoff = datetime.fromisoformat(cutoff_text)
            except ValueError:
                cutoff = None
            if cutoff is not None:
                self.decision_time_edit.setTime(
                    QTime.fromString(cutoff.astimezone(_TAIPEI).strftime("%H:%M:%S"), "HH:mm:ss")
                )
            del blocker_date, blocker_time
        self._project_market_cohort(snapshot)
        self._render_snapshot()
        self.status_label.setText(
            f"已唯讀核驗 cohort {cohort_id}、決策日 {decision_date} 與當前來源身份；"
            "只呈現研究快照，不代表正式推薦或 historical PIT。"
        )
        self.snapshotAccepted.emit(snapshot)
        self._original_ranking_pending = callable(
            getattr(self.service, "read_original_ranking", None)
        )
        if not self._original_ranking_pending:
            self.original_ranking_label.setText(
                "原始排名：未知；此 service 未提供不可變來源 reader。"
            )

    def _project_market_cohort(self, snapshot: object) -> None:
        self._cohort_projection = None
        self._cohort_members_by_code = {}
        self._render_market_cohort_projection()
        if self.service is None:
            return
        filter_rows = getattr(self.service, "filter_rows", None)
        if not callable(filter_rows):
            self.cohort_identity_label.setText(
                "研究母體盤勢不可用：完整固定方法 rows 服務尚未提供。"
            )
            return
        try:
            full_rows = tuple(
                filter_rows(
                    snapshot,
                    ("close_above_ma20", "close_above_ma60"),
                    "AND",
                )
            )
            self._cohort_full_rows = cast(tuple[object, ...], full_rows)
            snapshot_root = getattr(self.service, "snapshot_root", None)
            expected_snapshot_root = (
                str(snapshot_root) if snapshot_root is not None else None
            )
            self._cohort_projection = project_daily_market_cohort(
                cast(VerifiedDailyMarketSnapshot, snapshot),
                cast(Sequence[DailyMarketResearchScreenRow], full_rows),
                expected_snapshot_root=expected_snapshot_root,
                original_ranking=self._original_ranking,
            )
            self._cohort_members_by_code = {
                str(getattr(member, "stock_code", "") or "").strip(): member
                for member in tuple(
                    getattr(self._cohort_projection, "members", ()) or ()
                )
                if str(getattr(member, "stock_code", "") or "").strip()
            }
        except Exception as exc:
            self._cohort_projection = None
            self._cohort_members_by_code = {}
            self.cohort_identity_label.setText(
                "研究母體盤勢無法核驗；名單與分母維持未知。"
            )
            self.cohort_identity_label.setToolTip(
                f"{type(exc).__name__}: {exc}"
            )
            self.cohort_summary_label.setText(
                "固定方法計數未提供；不以缺少資料推定不符合。"
            )
            return
        self._render_market_cohort_projection()

    def _render_market_cohort_projection(self) -> None:
        projection = self._cohort_projection
        available = projection is not None
        self.sort_key_combo.setEnabled(available and not self._shutting_down)
        self.sort_direction_combo.setEnabled(available and not self._shutting_down)
        self._sync_original_rank_sort_controls(
            busy=self._worker is not None and self._worker.isRunning()
        )
        if projection is None:
            self.preset_help_label.setToolTip(
                "固定 close／MA20／MA60 收盤比較；MA20 需 20 個有效觀測、"
                "MA60 需 60 個有效觀測，暖機不足為未知。僅供研究，不代表預測或投資結論。"
            )
            if self._snapshot is None:
                self.cohort_identity_label.setText(
                    "尚未載入具名研究 cohort；此區不代表全市場。"
                )
                self.cohort_summary_label.setText(
                    "固定方法的符合／不符合／未知分母尚未載入。"
                )
            else:
                self.cohort_identity_label.setText(
                    f"快照 {self._loaded_cohort_id}／{self._loaded_decision_date} "
                    "已接受；同一 snapshot 的盤勢投影尚未核驗。"
                )
                self.cohort_summary_label.setText(
                    "原排名未提供；指標排序非投資分數。固定方法計數維持未知。"
                )
            return

        cohort_id = str(getattr(projection, "cohort_id", "") or "")
        decision_date = str(getattr(projection, "decision_date", "") or "")
        source_ref = str(getattr(projection, "source_ref", "") or "")
        if not source_ref:
            source_refs = {
                f"{key}={value}"
                for member in tuple(getattr(projection, "members", ()) or ())
                for key, value in tuple(getattr(member, "source_refs", ()) or ())
                if str(key).strip() and str(value).strip()
            }
            source_ref = "、".join(sorted(source_refs)) or "未提供"
        source_id = str(getattr(projection, "source_snapshot_id", "") or "")
        source_hash = str(getattr(projection, "source_snapshot_hash", "") or "")
        method_hash = str(
            getattr(projection, "method_contracts_sha256", "") or "未提供"
        )
        declared_codes = tuple(
            getattr(projection, "declared_stock_codes", ()) or ()
        )
        published_codes = tuple(
            getattr(projection, "published_stock_codes", ()) or ()
        )
        missing_codes = tuple(
            getattr(projection, "missing_stock_codes", ()) or ()
        )
        declared_count = len(declared_codes)
        published_count = int(
            getattr(projection, "published_count", len(published_codes))
        )
        completeness = str(getattr(projection, "completeness", "") or "未提供")
        identity_text = (
            "具名研究 cohort；非全市場／非正式推薦｜"
            f"資料來源 {source_ref}｜決策日 {decision_date}｜cohort {cohort_id}\n"
            f"已發布列 {published_count}/{declared_count}｜完整性 {completeness}｜"
            f"source snapshot ID {source_id}｜source hash {source_hash}\n"
            f"method_contracts_sha256 {method_hash}"
        )
        if missing_codes:
            identity_text += f"｜缺少已發布列：{', '.join(str(code) for code in missing_codes)}"
        visible_identity = (
            "具名研究 cohort；非全市場／非正式推薦｜"
            f"決策日 {decision_date}｜cohort {cohort_id}\n"
            f"已發布列 {published_count}/{declared_count}；來源／方法身分見提示。"
        )
        if missing_codes:
            visible_identity += f"｜缺少已發布列：{', '.join(str(code) for code in missing_codes)}"
        universe_text, universe_detail = research_universe_text(
            getattr(projection, "research_universe", None),
            published_count=published_count, declared_count=declared_count,
            original_rank_available=self._original_ranking is not None,
        )
        visible_identity += "\n" + universe_text + "\n" + ranking_summary_text(
            self._original_ranking
        )
        identity_text += (
            "\n"
            + universe_detail
            + "\n"
            + ranking_audit_tooltip(self._original_ranking)
        )
        self.cohort_identity_label.setText(visible_identity)
        self.cohort_identity_label.setToolTip(identity_text)

        count_lines: list[str] = []
        method_audit_lines: list[str] = []
        for item in tuple(getattr(projection, "method_counts", ()) or ()):
            key = str(getattr(item, "key", "") or "")
            label = _CONDITION_LABELS.get(key, key or "固定方法")
            method_id = str(getattr(item, "method_id", "") or "方法 ID 未提供")
            family = str(getattr(item, "family", "") or "")
            version = str(getattr(item, "version", "") or "")
            parameters = getattr(item, "parameters", {}) or {}
            if isinstance(parameters, Mapping):
                parameters_text = ", ".join(
                    f"{name}={value}" for name, value in parameters.items()
                )
            elif isinstance(parameters, Sequence) and not isinstance(
                parameters, (str, bytes)
            ):
                parameters_text = ", ".join(
                    f"{pair[0]}={pair[1]}"
                    for pair in parameters
                    if isinstance(pair, Sequence)
                    and not isinstance(pair, (str, bytes))
                    and len(pair) == 2
                )
            else:
                parameters_text = str(parameters)
            method_details = "／".join(
                part for part in (method_id, family, version, parameters_text) if part
            )
            method_audit_lines.append(f"{label} [{method_details}]")
            count_lines.append(
                f"{label}（v{version}）：符合 "
                f"{getattr(item, 'match_count', 0)}、不符合 "
                f"{getattr(item, 'no_match_count', 0)}、未知 "
                f"{getattr(item, 'unknown_count', 0)}；分母 "
                f"{getattr(item, 'denominator', declared_count)}。"
            )
        if not count_lines:
            count_lines.append("固定方法計數未提供；不以缺少資料推定不符合。")
        rank_state = str(getattr(projection, "original_rank_state", "unknown") or "unknown")
        if rank_state != "verified":
            count_lines.append("原排名未提供；指標排序非投資分數。")
        if missing_codes:
            count_lines.append(
                "缺少已發布個股列仍計入分母並列為未知；未建立可開啟的替代名單列。"
            )
        self.cohort_summary_label.setText("\n".join(count_lines))
        self.cohort_summary_label.setToolTip(
            "計數只涵蓋此具名研究 cohort。條件方法與版本來自已發布 snapshot；"
            "不宣稱全市場排名、alpha 或投資分數。\n"
            + "\n".join(method_audit_lines)
        )
        self.preset_help_label.setToolTip(
            "固定 close／MA20／MA60 收盤比較；MA20 需 20 個有效觀測、"
            "MA60 需 60 個有效觀測，暖機不足為未知。僅供研究，不代表預測或投資結論。\n"
            "已發布方法契約：\n"
            + "\n".join(method_audit_lines)
            + f"\nmethod_contracts_sha256={method_hash}"
        )

    def _render_production_result(self, result: object) -> None:
        status = str(getattr(result, "status", "unknown") or "unknown")
        reused = tuple(getattr(result, "reused_stock_codes", ()) or ())
        recomputed = tuple(getattr(result, "recomputed_stock_codes", ()) or ())
        self.status_label.setText(
            f"快照更新回報：{status}；重用 {len(reused)} 檔、重新投影 {len(recomputed)} 檔；"
            "以下為同一 manifest 的驗證讀回。"
        )

    def _render_snapshot(self) -> None:
        self._apply_filter_controls()

    def _apply_filter_controls(self, *_args: object) -> None:
        if self._snapshot is None or self.service is None:
            return
        condition_keys = self._selected_condition_keys()
        if not condition_keys:
            self._all_rows = ()
            self._visible_rows = ()
            self._render_rows()
            self.summary_label.setText(
                f"{self._loaded_decision_date}｜{self._loaded_cohort_id}｜"
                "請至少選擇一條研究條件；既有快照未變更。"
            )
            self._render_candidate_summary()
            return
        filter_rows = getattr(self.service, "filter_rows", None)
        if not callable(filter_rows):
            self.status_label.setText("研究條件篩選服務尚未提供；快照保持已核驗但不展示推論。")
            self._render_candidate_summary("研究條件篩選服務尚未提供。")
            return
        try:
            self._all_rows = tuple(
                filter_rows(
                    self._snapshot,
                    condition_keys,
                    str(self.combine_mode_combo.currentData() or "AND"),
                )
            )
        except Exception as exc:
            self._all_rows = ()
            self._visible_rows = ()
            self._render_rows()
            self._render_candidate_summary(
                f"研究條件篩選未能核驗：{type(exc).__name__}: {exc}"
            )
            self.status_label.setText(
                f"研究條件篩選失敗；條件保持未知：{type(exc).__name__}: {exc}"
            )
            return
        self._render_summary()
        self._render_candidate_summary()
        self._render_rows()

    def _render_summary(self) -> None:
        counts = {state: 0 for state in _STATE_LABELS}
        for row in self._all_rows:
            state = str(getattr(row, "combined_state", "unknown") or "unknown")
            counts[state if state in counts else "unknown"] += 1
        manifest = getattr(self._snapshot, "manifest", {})
        completeness = str(manifest.get("completeness") or "未提供")
        scope_label = "明示研究 cohort；非全市場／非正式推薦"
        if self._all_rows:
            scope_label = str(getattr(self._all_rows[0], "research_scope_label", scope_label) or scope_label)
        condition_names = "、".join(
            _CONDITION_LABELS.get(key, key) for key in self._selected_condition_keys()
        )
        combine_mode = str(self.combine_mode_combo.currentData() or "AND")
        active_preset_id = self.get_active_preset_id()
        active_preset = (
            self._get_research_preset(active_preset_id)
            if active_preset_id is not None
            else None
        )
        active_query_label = (
            active_preset.label or active_preset_id
            if active_preset is not None
            else "自訂查詢"
        )
        filter_state = str(self.filter_state_combo.currentData() or "all")
        filter_label = next(
            (
                label
                for label, value in (
                    ("全部", "all"),
                    ("符合", "match"),
                    ("不符合", "no_match"),
                    ("未知", "unknown"),
                )
                if value == filter_state
            ),
            "全部",
        )
        self.summary_label.setText(
            f"目前查詢：{active_query_label}｜條件 {condition_names}（{combine_mode}）｜"
            f"狀態篩選 {filter_label}｜核驗列 {len(self._all_rows)}："
            f"符合 {counts['match']}、不符合 {counts['no_match']}、未知 {counts['unknown']}。"
        )
        self.summary_label.setToolTip(
            f"決策日: {self._loaded_decision_date}\n"
            f"cohort: {self._loaded_cohort_id}\n"
            f"scope: {scope_label}\n"
            f"active preset: {active_preset_id or 'custom'}\n"
            f"completeness: {completeness}\n"
            f"manifest_identity_sha256: {self._manifest_identity_sha256}\n"
            f"manifest_sha256: {self._manifest_sha256}\n"
            "研究快照不代表完整市場母體、正式推薦或 historical PIT 資格。"
        )

    def _render_candidate_summary(self, error: str = "") -> None:
        if self._snapshot is None:
            self.candidate_summary_label.setText(
                "候選母體分母與三態摘要尚未載入；不推估缺列或未知數。"
            )
            self.candidate_summary_label.setToolTip("")
            return
        try:
            summary = summarize_research_candidates(
                self._snapshot,
                self._all_rows,
                str(self.filter_state_combo.currentData() or "all"),
            )
        except Exception as exc:
            detail = error or f"{type(exc).__name__}: {exc}"
            self.candidate_summary_label.setText(
                "候選摘要未知：無法核驗完整 cohort 分母、發布列、缺列與三態數量。"
            )
            self.candidate_summary_label.setToolTip(detail)
            return
        if summary is None:
            self.candidate_summary_label.setText(
                "候選摘要未知：來源未提供完整分母或狀態計數。"
            )
            self.candidate_summary_label.setToolTip(error)
            return

        self.candidate_summary_label.setText(
            f"研究母體：宣告 {summary.declared_count} 檔｜已發布 {summary.published_count}｜"
            f"缺件 {summary.missing_count}｜符合 {summary.match_count}｜"
            f"未符合 {summary.no_match_count}｜未知 {summary.unknown_count}\n"
            f"目前顯示 {summary.visible_count}｜因篩選隱藏 {summary.excluded_count}"
        )
        missing_codes = list(summary.missing_stock_codes)
        unknown_details: list[str] = []
        for row in self._all_rows:
            if str(getattr(row, "combined_state", "unknown") or "unknown") != "unknown":
                continue
            reasons = [
                f"{_CONDITION_LABELS.get(str(getattr(condition, 'key', '') or ''), '研究條件')}："
                f"{str(getattr(condition, 'reason', '') or '未知原因未提供')}"
                for condition in tuple(getattr(row, "conditions", ()) or ())
                if str(getattr(condition, "state", "unknown") or "unknown") == "unknown"
            ]
            reason_text = "；".join(reasons) or "未知原因未提供"
            unknown_details.append(
                f"{str(getattr(row, 'stock_code', '') or '未提供')}: {reason_text}"
            )
        reason_lines = list(summary.excluded_reasons)
        missing_top = "、".join(missing_codes[:2]) or "無"
        unknown_top = "；".join(unknown_details[:2]) or "無"
        excluded_top = "；".join(reason_lines[:2]) or "無"
        self.candidate_summary_label.setText(
            self.candidate_summary_label.text()
            + f"\n缺件：{missing_top}｜未知原因：{unknown_top}｜排除原因：{excluded_top}"
        )
        details = [
            f"宣告={summary.declared_count}; 已發布={summary.published_count}; "
            f"缺件={summary.missing_count}; 符合={summary.match_count}; "
            f"未符合={summary.no_match_count}; 未知={summary.unknown_count}; "
            f"顯示={summary.visible_count}; 因篩選隱藏={summary.excluded_count}"
        ]
        details.append(
            "缺少已發布 artifact 股票："
            + (", ".join(missing_codes) if missing_codes else "未提供／無")
        )
        details.append(
            "具名未知列原因："
            + ("；".join(unknown_details) if unknown_details else "未提供／無")
        )
        details.append(
            "排除原因："
            + ("；".join(reason_lines) if reason_lines else "未提供／無")
        )
        details.append(
            "unknown 保留為未知；缺少 artifact 不建立可開啟的替代列。"
        )
        universe_text, universe_detail = research_universe_text(
            getattr(self._cohort_projection, "research_universe", None),
            published_count=summary.published_count, declared_count=summary.declared_count,
            original_rank_available=self._original_ranking is not None,
        )
        self.candidate_summary_label.setText(
            self.candidate_summary_label.text()
            + "\n"
            + universe_text
            + "\n"
            + ranking_summary_text(self._original_ranking)
        )
        details.append(universe_detail)
        details.append(ranking_summary_text(self._original_ranking))
        details.append(original_rank_row_tooltip(self._original_ranking, None))
        self.candidate_summary_label.setToolTip("\n".join(details))

    def _render_rows(self, *_args: object) -> None:
        selected_identity: tuple[str, str, str] | None = None
        selected = self.results_table.selectionModel().selectedRows()
        if len(selected) == 1:
            selected_item = self.results_table.item(selected[0].row(), 0)
            selected_row = (
                selected_item.data(Qt.ItemDataRole.UserRole)
                if selected_item is not None
                else None
            )
            if selected_row is not None:
                selected_identity = (
                    str(getattr(selected_row, "stock_code", "") or "").strip(),
                    str(getattr(selected_row, "source_snapshot_id", "") or "").strip(),
                    str(getattr(selected_row, "source_snapshot_hash", "") or "").strip(),
                )
        rows = self._current_filtered_rows()
        rows = self._sort_filtered_rows(rows)
        self._visible_rows = rows
        self.results_table.setSortingEnabled(False)
        self.results_table.clearContents()
        self.results_table.setRowCount(len(rows))
        ranking_rows = ranking_rows_by_code(self._original_ranking) or {}
        for row_number, row in enumerate(rows):
            stock_code = str(getattr(row, "stock_code", "") or "")
            condition_map = {
                str(getattr(condition, "key", "")): condition
                for condition in (getattr(row, "conditions", ()) or ())
            }
            member = self._cohort_members_by_code.get(stock_code)
            values = (
                stock_code,
                str(getattr(member, "data_date", None) or getattr(row, "data_date", "") or "未知"),
                self._condition_text(condition_map.get("close_above_ma20")),
                self._condition_text(condition_map.get("close_above_ma60")),
                self._state_text(getattr(row, "combined_state", "unknown")),
                self._reason_text(row),
                self._market_value_text(member, "close"),
                self._market_value_text(member, "ma20"),
                self._market_value_text(member, "ma60"),
                original_rank_cell(self._original_ranking, stock_code),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, row)
                if column == 0:
                    item.setData(
                        Qt.ItemDataRole.AccessibleTextRole,
                        f"股票代碼 {stock_code}，來源 manifest {self._manifest_sha256}",
                    )
                if column == 9:
                    item.setToolTip(
                        original_rank_row_tooltip(
                            self._original_ranking,
                            ranking_rows.get(stock_code),
                        )
                    )
                self.results_table.setItem(row_number, column, item)
        if selected_identity is not None:
            for row_number, row in enumerate(rows):
                identity = (
                    str(getattr(row, "stock_code", "") or "").strip(),
                    str(getattr(row, "source_snapshot_id", "") or "").strip(),
                    str(getattr(row, "source_snapshot_hash", "") or "").strip(),
                )
                if identity == selected_identity:
                    self.results_table.selectRow(row_number)
                    break
        self._sync_open_button()
        self._render_selected_summary()

    def _render_selected_summary(self) -> None:
        selected = self.results_table.selectionModel().selectedRows()
        if len(selected) != 1:
            self.selected_summary_label.setText(
                "選取一列以查看支持、反證與資料限制；僅供研究，不是投資結論。"
            )
            self.selected_summary_label.setToolTip("")
            return
        item = self.results_table.item(selected[0].row(), 0)
        row = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        if row is None:
            self.selected_summary_label.setText(
                "選取列缺少已核驗的快照條件；證據摘要未知。"
            )
            self.selected_summary_label.setToolTip("")
            return
        conditions = tuple(getattr(row, "conditions", ()) or ())
        by_key = {
            str(getattr(condition, "key", "") or ""): condition
            for condition in conditions
        }
        supporting: list[str] = []
        refuting: list[str] = []
        limitations: list[str] = []
        for key, condition in by_key.items():
            label = _CONDITION_LABELS.get(key, key or "研究條件")
            state = str(getattr(condition, "state", "unknown") or "unknown")
            relation = _RELATION_LABELS.get(
                str(getattr(condition, "relation", "unknown") or "unknown"),
                "關係未知",
            )
            reason = str(getattr(condition, "reason", "") or "").strip()
            if state == "match":
                supporting.append(f"{label}（{relation}）")
            elif state == "no_match":
                refuting.append(f"{label}（{relation}；條件不符合）")
            elif state == "unknown":
                limitations.append(
                    f"{label}：{reason or '未知原因未提供'}"
                )
        if not supporting and str(getattr(row, "combined_state", "unknown")) == "match":
            supporting.append("符合的條件證據未提供")
        if not refuting and str(getattr(row, "combined_state", "unknown")) == "no_match":
            refuting.append("不符合條件的細節未提供")
        if not limitations and str(getattr(row, "combined_state", "unknown")) == "unknown":
            limitations.append("未知原因未提供")

        code = str(getattr(row, "stock_code", "") or "未提供")
        state = str(getattr(row, "combined_state", "unknown") or "unknown")
        member = self._cohort_members_by_code.get(code)
        data_date = str(
            getattr(member, "data_date", None)
            or getattr(row, "data_date", "")
            or "未知"
        )
        decision_date = str(
            getattr(row, "decision_date", "") or self._loaded_decision_date or "未知"
        )
        method_details: list[str] = []
        for key, condition in by_key.items():
            method_id = str(getattr(condition, "method_id", "") or "").strip()
            family = str(getattr(condition, "family", "") or "").strip()
            version = str(getattr(condition, "version", "") or "").strip()
            parameters = getattr(condition, "parameters", None)
            method_text = "／".join(
                part for part in (method_id, family, version) if part
            )
            if isinstance(parameters, Mapping) and parameters:
                method_text += "（" + ", ".join(
                    f"{name}={value}" for name, value in parameters.items()
                ) + "）"
            if method_text:
                method_details.append(
                    f"{_CONDITION_LABELS.get(key, key)}：{method_text}"
                )
        visible_methods = "固定 MA20（20 個有效觀測）／MA60（60 個有效觀測）比較"
        methods = "；".join(method_details) if method_details else visible_methods
        visible_limitations = [
            f"{reason[:80]}{'…' if len(reason) > 80 else ''}"
            for reason in limitations[:2]
        ]
        self.selected_summary_label.setText(
            f"{code}｜{self._state_text(state)}｜支持："
            f"{'；'.join(dict.fromkeys(supporting[:2])) or '無'}｜反證："
            f"{'；'.join(dict.fromkeys(refuting[:2])) or '無'}｜資料限制："
            f"{'；'.join(dict.fromkeys(visible_limitations)) or '無'}\n"
            f"方法：{visible_methods}｜決策日 {decision_date}｜資料日 {data_date}｜"
            "研究條件描述，非強弱、勝率或投資結論。"
        )
        self.selected_summary_label.setToolTip(
            f"決策日={decision_date}; 資料日={data_date}\n"
            f"方法={methods}\n"
            f"manifest_sha256={self._manifest_sha256}\n"
            f"manifest_identity_sha256={self._manifest_identity_sha256}\n"
            f"支持理由來源={self._as_texts(getattr(row, 'why', ()))}\n"
            f"不符合條件來源={self._as_texts(getattr(row, 'why_not', ()))}\n"
            f"支持={supporting}\n反證={refuting}\n資料限制={limitations}\n"
            "close/MA 條件不構成預測、勝率或投資建議。"
        )

        selected_ranking_rows = ranking_rows_by_code(self._original_ranking) or {}
        selected_rank = selected_ranking_rows.get(code)
        rank_line = f"原始名次：{original_rank_cell(self._original_ranking, code)}"
        if selected_rank is not None:
            rank_line += f" · 比較窗 {ranking_window_text(selected_rank)}"
        self.selected_summary_label.setText(
            self.selected_summary_label.text() + "\n" + rank_line
        )
        self.selected_summary_label.setToolTip(
            self.selected_summary_label.toolTip()
            + "\n"
            + original_rank_row_tooltip(self._original_ranking, selected_rank)
        )

    def _current_filtered_rows(self) -> tuple[object, ...]:
        selected_filter = str(self.filter_state_combo.currentData() or "all")
        return tuple(
            row
            for row in self._all_rows
            if selected_filter == "all"
            or str(getattr(row, "combined_state", "unknown") or "unknown") == selected_filter
        )

    def _sort_filtered_rows(self, rows: tuple[object, ...]) -> tuple[object, ...]:
        projection = self._cohort_projection
        if projection is None:
            return rows
        rows_by_code: dict[str, object] = {}
        for row in rows:
            code = str(getattr(row, "stock_code", "") or "").strip()
            if not code or code in rows_by_code:
                self.status_label.setText(
                    "研究名單股票身份重複或缺漏；停止顯示可下鑽名單。"
                )
                return ()
            rows_by_code[code] = row
        key = str(self.sort_key_combo.currentData() or "stock_code")
        direction = str(self.sort_direction_combo.currentData() or "asc")
        if key == "original_strength_rank":
            ordered_rows = sort_by_original_rank(
                rows,
                self._original_ranking,
                stock_code=lambda item: str(getattr(item, "stock_code", "") or ""),
            )
            if ordered_rows is None:
                self._fail_original_ranking(
                    "原生名次列無法在維持來源身份時使用"
                )
                return rows
            return ordered_rows
        try:
            members = sort_daily_market_cohort_members(
                tuple(getattr(projection, "members", ()) or ()),
                cast(DailyMarketCohortSortKey, key),
                descending=direction == "desc",
            )
        except Exception as exc:
            self.status_label.setText(
                f"研究名單排序身份無法核驗：{type(exc).__name__}: {exc}"
            )
            return ()
        ordered_codes = tuple(
            str(getattr(member, "stock_code", "") or "").strip()
            for member in members
        )
        if not set(rows_by_code).issubset(set(ordered_codes)):
            self.status_label.setText(
                "名單列不在目前研究母體投影中；停止顯示可下鑽名單。"
            )
            return ()
        return tuple(rows_by_code[code] for code in ordered_codes if code in rows_by_code)

    @staticmethod
    def _market_value_text(member: object | None, key: str) -> str:
        value = getattr(member, key, None) if member is not None else None
        if value is None:
            return "未知"
        return str(value)

    def visible_research_row_identities(self) -> tuple[tuple[str, str, str], ...]:
        """回傳依目前排序顯示的股票碼及其已發布快照身份。"""

        return tuple(
            (
                str(getattr(row, "stock_code", "") or "").strip(),
                str(getattr(row, "source_snapshot_id", "") or "").strip(),
                str(getattr(row, "source_snapshot_hash", "") or "").strip(),
            )
            for row in self._visible_rows
        )

    @staticmethod
    def _condition_text(condition: object | None) -> str:
        if condition is None:
            return "未知（條件缺件）"
        state = str(getattr(condition, "state", "unknown") or "unknown")
        label = _STATE_LABELS.get(state, "未知")
        relation = _RELATION_LABELS.get(
            str(getattr(condition, "relation", "unknown") or "unknown"),
            "",
        )
        reason = str(getattr(condition, "reason", "") or "").strip()
        text = f"{label}｜{relation}" if relation else label
        if state == "unknown" and reason:
            text += f"（{reason}）"
        return text

    @classmethod
    def _reason_text(cls, row: object) -> str:
        state = str(getattr(row, "combined_state", "unknown") or "unknown")
        reasons: list[str] = []
        if state == "match":
            reasons.extend(cls._as_texts(getattr(row, "why", ())))
        else:
            reasons.extend(cls._as_texts(getattr(row, "why_not", ())))
        if state == "unknown":
            for condition in (getattr(row, "conditions", ()) or ()):
                if str(getattr(condition, "state", "")) == "unknown":
                    reason = str(getattr(condition, "reason", "") or "").strip()
                    if reason:
                        reasons.append(reason)
        if not reasons:
            reasons.append(_STATE_LABELS.get(state, "未知"))
        return "；".join(dict.fromkeys(reasons))

    @staticmethod
    def _as_texts(value: object) -> list[str]:
        if isinstance(value, str):
            text = value.strip()
            return [text] if text else []
        if isinstance(value, Sequence):
            return [str(item).strip() for item in value if str(item).strip()]
        text = str(value or "").strip()
        return [text] if text else []

    @staticmethod
    def _state_text(value: object) -> str:
        state = str(value or "unknown")
        label = _STATE_LABELS.get(state, "未知")
        return f"{label}（{state}）" if state not in _STATE_LABELS else label

    def _selected_stock_codes(self) -> tuple[str, ...]:
        raw_codes = self.stock_codes_input.text().replace("\n", ",").split(",")
        codes = tuple(code.strip() for code in raw_codes if code.strip())
        if not codes:
            raise ValueError("請至少輸入一個股票代碼。")
        if len(codes) > 16:
            raise ValueError("每日研究快照每次最多接受 16 檔股票。")
        if len(set(codes)) != len(codes):
            raise ValueError("股票代碼不可重複。")
        return codes

    def _selected_condition_keys(self) -> tuple[str, ...]:
        keys: list[str] = []
        if self.ma20_checkbox.isChecked():
            keys.append("close_above_ma20")
        if self.ma60_checkbox.isChecked():
            keys.append("close_above_ma60")
        return tuple(keys)

    def _selected_decision_date(self) -> date:
        value = self.decision_date_edit.date().toString(Qt.DateFormat.ISODate)
        return date.fromisoformat(value)

    def _selected_decision_cutoff(self) -> datetime:
        selected_date = self._selected_decision_date()
        selected_time = time.fromisoformat(
            self.decision_time_edit.time().toString("HH:mm:ss")
        )
        cutoff = datetime.combine(selected_date, selected_time, tzinfo=_TAIPEI)
        if cutoff > datetime.now(_TAIPEI):
            raise ValueError("研究截止時間不可晚於目前 Asia/Taipei 時間。")
        return cutoff

    def _show_input_error(self, message: str) -> None:
        self.status_label.setText(f"無法開始每日研究工作：{message}")
        self.status_label.setToolTip(message)

    def _has_selected_row(self) -> bool:
        return bool(self.results_table.selectionModel().selectedRows())

    def _sync_open_button(self) -> None:
        self.open_selected_stock_button.setEnabled(
            not self._shutting_down
            and (self._worker is None or not self._worker.isRunning())
            and self._has_selected_row()
        )
        if hasattr(self, "bookmark_selected_research_button"):
            self.bookmark_selected_research_button.setEnabled(
                self.watchlist_service is not None
                and self._snapshot is not None
                and not self._shutting_down
                and (self._worker is None or not self._worker.isRunning())
                and self._has_selected_row()
            )
        if hasattr(self, "apply_preset_button"):
            self.apply_preset_button.setEnabled(
                self.service is not None
                and self._snapshot is not None
                and not self._shutting_down
                and (self._worker is None or not self._worker.isRunning())
            )

    def bookmark_selected_research(self) -> bool:
        """保存已核驗的選取列；只有使用者確認後才呼叫觀察清單服務。"""

        if str(self.sort_key_combo.currentData() or "") == "original_strength_rank":
            self.status_label.setText(
                "無法用原始排名排序儲存書籤；目前書籤格式不保存排名期間、方向與來源身份。"
            )
            self.status_label.setToolTip(
                "切回股票代號、日期或 MA 排序後即可使用現有研究書籤。"
            )
            return False
        if (
            self.watchlist_service is None
            or self._snapshot is None
            or self._shutting_down
        ):
            self.status_label.setText("觀察清單服務或已核驗快照尚未提供；未保存研究書籤。")
            return False
        selected = self.results_table.selectionModel().selectedRows()
        if len(selected) != 1:
            self.status_label.setText("請先選取一列已核驗的每日研究結果。")
            return False
        item = self.results_table.item(selected[0].row(), 0)
        row = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        if row is None:
            self.status_label.setText("選取列缺少快照來源資料；未保存研究書籤。")
            return False

        stock_code = str(getattr(row, "stock_code", "") or "").strip()
        try:
            bookmark = create_daily_market_research_bookmark(
                self._snapshot,
                row,
                sort_key=str(self.sort_key_combo.currentData() or "stock_code"),
                descending=str(self.sort_direction_combo.currentData() or "asc").lower()
                in {"desc", "descending"},
                filter_state=str(self.filter_state_combo.currentData() or "all"),
                stock_name="",
            )
        except Exception as exc:
            self.status_label.setText(
                f"無法建立完整研究書籤：{type(exc).__name__}: {exc}；未保存。"
            )
            return False

        if not self._confirm_research_bookmark(bookmark, row):
            self.status_label.setText("已取消收藏；觀察清單未變更。")
            return False

        add_bookmark = getattr(self.watchlist_service, "add_research_bookmark", None)
        if not callable(add_bookmark):
            self.status_label.setText("觀察清單服務不支援每日研究書籤；未保存。")
            return False
        try:
            result = add_bookmark(bookmark)
        except Exception as exc:
            self.status_label.setText(
                f"研究書籤保存失敗：{type(exc).__name__}: {exc}。"
            )
            return False

        status = str(getattr(result, "status", "") or "")
        if status == "conflict":
            message = str(getattr(result, "message", "") or "書籤身份衝突")
            self.status_label.setText(f"{message}；未覆寫既有書籤。")
            return False
        if status not in {"added", "already_present"}:
            self.status_label.setText(
                str(getattr(result, "message", "研究書籤未能保存。"))
            )
            return False
        self.bookmarkSaved.emit(bookmark)
        self.status_label.setText(
            f"{'已收藏' if status == 'added' else '此研究已收藏'} {stock_code}；來源仍固定於原 manifest。"
        )
        return True

    def _confirm_research_bookmark(self, bookmark: object, row: object) -> bool:
        callback = self.bookmark_confirmation_callback
        if callback is not None:
            try:
                return bool(callback(bookmark))
            except Exception as exc:
                self.status_label.setText(
                    f"研究書籤確認流程失敗：{type(exc).__name__}: {exc}；未保存。"
                )
                return False

        manifest = getattr(self._snapshot, "manifest", {})
        if not isinstance(manifest, Mapping):
            manifest = {}
        stock_code = str(getattr(row, "stock_code", "") or "").strip()
        decision_date = str(getattr(row, "decision_date", "") or "未知")
        data_date = str(getattr(row, "data_date", "") or "未知")
        conditions = ", ".join(self._selected_condition_keys()) or "未提供"
        combine_mode = str(self.combine_mode_combo.currentData() or "AND")
        filter_state = str(self.filter_state_combo.currentData() or "all")
        source_id = str(
            getattr(row, "source_snapshot_id", "")
            or manifest.get("source_snapshot_id", "")
            or "未提供"
        )
        source_hash = str(
            getattr(row, "source_snapshot_hash", "")
            or self._manifest_sha256
            or "未提供"
        )
        method_hash = str(manifest.get("method_contracts_sha256", "未提供"))
        query = getattr(bookmark, "query", None)
        if query is None:
            query = getattr(bookmark, "query_json", "")
        query_text = str(query or "").strip()
        detail = (
            f"股票：{stock_code}\n決策日：{decision_date}｜資料日：{data_date}\n"
            f"方法／條件：{conditions}｜組合：{combine_mode}\n"
            f"列狀態篩選：{filter_state}\n"
            f"方法契約雜湊：{method_hash}\n來源 manifest：{source_id}\n來源 hash：{source_hash}"
        )
        if query_text:
            detail += f"\n查詢：{query_text}"
        return (
            QMessageBox.question(
                self,
                "確認收藏此研究",
                f"將已驗證的原研究來源加入觀察清單？\n\n{detail}",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            == QMessageBox.StandardButton.Yes
        )

    def open_selected_stock(self) -> bool:
        if self.service is None or self._snapshot is None or self._shutting_down:
            return False
        selected = self.results_table.selectionModel().selectedRows()
        if len(selected) != 1:
            self.status_label.setText("請先選取一檔每日研究條件結果。")
            return False
        item = self.results_table.item(selected[0].row(), 0)
        row = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        if row is None:
            self.status_label.setText("選取列缺少已核驗的快照身份；請重讀已發布快照。")
            return False
        context_builder = getattr(self.service, "context_for_stock", None)
        if not callable(context_builder):
            self.status_label.setText("個股下鑽 context builder 尚未接線。")
            return False
        try:
            context = context_builder(row, stock_name="")
        except Exception as exc:
            self.status_label.setText(
                f"無法建立釘選快照 context：{type(exc).__name__}: {exc}"
            )
            return False
        stock_code = str(getattr(row, "stock_code", "") or "").strip()
        expected = {
            "stock_code": stock_code,
            "source_kind": "daily_market_research_snapshot",
            "source_workspace": "recommendation",
            "decision_date": str(getattr(row, "decision_date", "") or ""),
            "source_snapshot_id": str(getattr(row, "source_snapshot_id", "") or ""),
            "source_snapshot_hash": str(getattr(row, "source_snapshot_hash", "") or ""),
        }
        for name, value in expected.items():
            if str(getattr(context, name, "") or "").strip() != value:
                self.status_label.setText(
                    f"下鑽 context 的 {name} 與選取列身份不一致；未開啟報告。"
                )
                return False
        if expected["source_snapshot_hash"] != self._manifest_sha256:
            self.status_label.setText("選取列不屬於目前驗證的 manifest；未開啟報告。")
            return False
        condition_keys = ",".join(self._selected_condition_keys())
        if str(getattr(context, "daily_snapshot_condition_keys", "") or "") != condition_keys:
            self.status_label.setText("下鑽 context 的條件範圍不一致；未開啟報告。")
            return False
        if str(getattr(context, "daily_snapshot_combine_mode", "") or "") != str(
            self.combine_mode_combo.currentData() or "AND"
        ):
            self.status_label.setText("下鑽 context 的 AND／OR 組合方式不一致；未開啟報告。")
            return False
        self._selected_stock_code = stock_code
        self.stockResearchRequested.emit(context)
        self.status_label.setText(
            f"已開啟 {stock_code} 的唯讀個股研究；來源仍釘選於目前 cohort／manifest。"
        )
        return True

    def research_snapshot_stock_codes(self) -> tuple[str, ...]:
        """返回目前已核驗 snapshot 的完整 cohort 股票清單。"""

        return tuple(
            str(getattr(row, "stock_code", "") or "").strip()
            for row in self._all_rows
            if str(getattr(row, "stock_code", "") or "").strip()
        )

    def restore_research_snapshot_stock(
        self,
        code: str,
        manifest_sha256: str | None = None,
    ) -> bool:
        """只在同一份已核驗 manifest 與目前篩選下還原原選取列。"""

        requested = str(code or "").strip()
        expected_hash = str(manifest_sha256 or self._manifest_sha256).strip()
        if (
            not requested
            or self._snapshot is None
            or not expected_hash
            or expected_hash != self._manifest_sha256
        ):
            self.status_label.setText(
                "原每日研究快照尚未載入或 manifest 已變；請返回每日研究條件重讀／更新快照。"
            )
            return False
        if requested not in self.research_snapshot_stock_codes():
            self.status_label.setText(
                f"{requested} 不在原 cohort 清單；請返回每日研究條件確認來源。"
            )
            return False
        for row_number in range(self.results_table.rowCount()):
            item = self.results_table.item(row_number, 0)
            if item is not None and item.text().strip() == requested:
                self.results_table.selectRow(row_number)
                self._selected_stock_code = requested
                return True
        self.status_label.setText(
            f"{requested} 仍屬原 cohort，但目前條件篩選未顯示該列；已保留現有篩選。"
        )
        return False

    def begin_shutdown(self) -> bool:
        """凍結本頁回呼並合作取消自己的來源讀取／更新工作。"""

        if self._shutting_down:
            worker = self._worker
            return worker is None or not worker.isRunning()
        self._shutting_down = True
        self._operation_generation += 1
        for widget in (
            self.refresh_button,
            self.reload_button,
            self.cancel_button,
            self.open_selected_stock_button,
            self.bookmark_selected_research_button,
            self.stock_codes_input,
            self.cohort_id_input,
            self.decision_date_edit,
            self.decision_time_edit,
            self.ma20_checkbox,
            self.ma60_checkbox,
            self.combine_mode_combo,
            self.filter_state_combo,
            self.sort_key_combo,
            self.sort_direction_combo,
            self.results_table,
        ):
            widget.setEnabled(False)
        worker = self._worker
        if worker is not None and worker.isRunning():
            worker.cancel(cooperative=True, wait=False)
            return False
        return True

    def _clear_current_snapshot(self) -> None:
        self._snapshot = None
        self._cohort_projection = None
        self._cohort_members_by_code = {}
        self._cohort_full_rows = ()
        self._original_ranking_pending = False
        self._original_ranking = None
        self._original_ranking_error = ""
        self._all_rows = ()
        self._visible_rows = ()
        self._manifest_sha256 = ""
        self._manifest_identity_sha256 = ""
        self._loaded_cohort_id = ""
        self._loaded_decision_date = ""
        self.original_ranking_label.setText(
            "原始排名：未知；尚無已接受 snapshot。"
        )
        self.original_ranking_label.setToolTip("")
        self.originalRankingCleared.emit()
        self._selected_stock_code = ""
        self.results_table.clearSelection()
        self.results_table.setRowCount(0)
        self.summary_label.setText("目前沒有可核驗快照；未知條件不會視為不符合。")
        self._render_candidate_summary()
        self._render_selected_summary()
        self.cohort_identity_label.setText(
            "尚未載入具名研究 cohort；此區不代表全市場。"
        )
        self.cohort_identity_label.setToolTip("")
        self.cohort_summary_label.setText(
            "固定方法的符合／不符合／未知分母尚未載入。"
        )
        self.cohort_summary_label.setToolTip("")
        self.sort_key_combo.setEnabled(False)
        self.sort_direction_combo.setEnabled(False)
        self.open_selected_stock_button.setEnabled(False)
        self.apply_preset_button.setEnabled(False)
        self.snapshotCleared.emit()
