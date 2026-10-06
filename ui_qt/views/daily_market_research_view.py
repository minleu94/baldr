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
    QDialog,
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
from app_module.daily_research_source_selection import DailyResearchQuery
from ui_qt.widgets.daily_research_source_selector import DailyResearchSourceSelector
from app_module.daily_market_feature_snapshot import (
    DAILY_MARKET_FEATURE_CONTRACT_VERSION_BBANDS30_UPPER,
    feature_contract_for_version,
)
from app_module.original_stock_ranking import VerifiedOriginalStockRanking
from app_module.original_stock_ranking import research_context_for_original_stock_ranking
from app_module.daily_market_snapshot_repository import VerifiedDailyMarketSnapshot
from app_module.rule_research_sample_capture import build_rule_research_capture
from app_module.rule_research_sample_readiness import project_rule_sample_readiness
from app_module.multi_method_research_consensus import (
    MultiMethodResearchConsensus,
    adapt_daily_market_snapshot,
    build_multi_method_consensus,
)
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
from ui_qt.widgets.info_button import InfoButton
from ui_qt.workers.task_worker import TaskWorker


_TAIPEI = ZoneInfo("Asia/Taipei")
_CONDITION_LABELS = {
    "close_above_ma20": "收盤價高於 MA20",
    "close_above_ma60": "收盤價高於 MA60",
    "close_above_bbands30_upper": "收盤價高於布林上軌（30）",
}
_METHOD_HELP = (
    "固定 close／MA20／MA60 比較；MA20 需 20 根、MA60 需 60 根有效觀測。"
    "布林上軌（30）只讀已核驗 v3 保存值，需 30 根有效觀測；"
    "v2 未保存 BB、缺件或暖機不足維持未知，來源參數 lineage 未核驗仍為未知。"
    "僅供研究，不代表預測、勝率或投資結論。"
)
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
    researchQueryChanged = Signal(object)

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
        self._multi_method_consensus: MultiMethodResearchConsensus | None = None
        self._multi_method_consensus_error = ""
        self._multi_method_as_of = ""
        self._cohort_projection: object | None = None
        self._cohort_members_by_code: dict[str, object] = {}
        self._original_ranking: VerifiedOriginalStockRanking | None = None
        self._original_ranking_error = ""
        self._original_ranking_pending = False
        self._lifecycle_result: object | None = None
        self._lifecycle_query_key: tuple[str, tuple[str, ...], str] | None = None
        self._lifecycle_pending = False
        self._lifecycle_error = "歷史不足／尚未核對"
        self._history_dialog: QDialog | None = None
        self._parent_receipt_dialog: QDialog | None = None
        self._history_page: object | None = None
        self._history_cursors: list[str | None] = [None]
        self._history_position = 0
        self._history_base_position = 0
        self._history_page_query_key: tuple[object, ...] | None = None
        self._history_message = "尚未讀取歷史；瀏覽不會自動建立索引。"
        self._history_operation = ""
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
        self._return_query: tuple[str, DailyResearchQuery] | None = None
        self._last_emitted_query: DailyResearchQuery | None = None
        self.source_selector: DailyResearchSourceSelector | None = None
        self._build_ui()
        self._set_service_availability()

    def open_parent_receipt(self) -> None:
        if self._shutting_down:
            return
        from ui_qt.rule_research_parent_receipt_dialog import RuleResearchParentReceiptDialog
        if self._parent_receipt_dialog is None:
            self._parent_receipt_dialog = RuleResearchParentReceiptDialog(self)
        self._parent_receipt_dialog.show()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)
        config = getattr(self.service, "config", None)
        if config is not None:
            self.source_selector = DailyResearchSourceSelector(config,
                snapshot_root=getattr(self.service, "snapshot_root", None), parent=self)
            self.source_selector.sourceLoaded.connect(self._accept_selected_source)
            root.addWidget(self.source_selector)

        title_layout = QHBoxLayout()
        title = QLabel("每日研究條件")
        title.setObjectName("dailyMarketResearchTitle")
        title.setAccessibleName("每日研究條件")
        title.setStyleSheet(
            f"color: {MIDNIGHT_ANALYST.text_primary}; font-size: 15px; font-weight: 700;"
        )
        title_layout.addWidget(title)
        title_layout.addStretch()
        title_layout.addWidget(InfoButton("daily_market_research", self))
        root.addLayout(title_layout)

        self.disclaimer_label = QLabel(
            "研究快照：僅表示明示 cohort 的已保存 close／MA20／MA60／布林上軌條件，"
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
        self.local_stock_filter = QLineEdit()
        self.local_stock_filter.setObjectName("dailyMarketLocalStockFilter")
        self.local_stock_filter.setAccessibleName("只篩選目前已核驗名單股票")
        self.local_stock_filter.setPlaceholderText("在目前名單找股票代碼；不重讀、不更新來源")
        self.local_stock_filter.setMaxLength(16)
        self.local_stock_filter.textChanged.connect(self._render_rows)
        root.addWidget(self.local_stock_filter)
        self.local_filter_summary_label = QLabel("局部顯示：尚未載入核驗名單。")
        self.local_filter_summary_label.setWordWrap(True)
        root.addWidget(self.local_filter_summary_label)

        self.sample_readiness_label = QLabel("研究樣本：尚未核對完整單批控制組；成熟結果未知。")
        self.sample_readiness_label.setObjectName("dailyMarketRuleSampleReadiness")
        self.sample_readiness_label.setTextFormat(Qt.TextFormat.PlainText)
        self.sample_readiness_label.setWordWrap(True)
        root.addWidget(self.sample_readiness_label)
        self.parent_receipt_button = QPushButton("查看保存母體收據")
        self.parent_receipt_button.setObjectName("dailyMarketParentReceipt")
        self.parent_receipt_button.setToolTip("唯讀核對明示保存的多批母體；不更新快照或保存新樣本。")
        self.parent_receipt_button.clicked.connect(self.open_parent_receipt)
        root.addWidget(self.parent_receipt_button)

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
        self.bbands30_upper_checkbox = QCheckBox("收盤價高於布林上軌（30）")
        self.bbands30_upper_checkbox.setObjectName("dailyMarketResearchBbands30Upper")
        self.bbands30_upper_checkbox.setAccessibleName("使用收盤價高於布林上軌 30 條件")
        self.bbands30_upper_checkbox.setToolTip(
            "只篩選原保存 v3 證據；按更新研究快照才明示 opt-in，來源參數 lineage 未核驗。"
        )
        condition_row.addWidget(self.bbands30_upper_checkbox)
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

        self.preset_help_label = QLabel(_METHOD_HELP)
        self.preset_help_label.setObjectName("dailyMarketResearchPresetHelp")
        self.preset_help_label.setAccessibleName("每日研究方法與預設使用說明")
        self.preset_help_label.setWordWrap(True)
        self.preset_help_label.setToolTip(_METHOD_HELP)
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
            ("布林上軌（30）", "bbands30_upper"),
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

        self.results_table = QTableWidget(0, 13)
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
        self.results_table.setHorizontalHeaderItem(10, QTableWidgetItem("入選歷程"))
        self.results_table.setHorizontalHeaderItem(11, QTableWidgetItem("收盤／布林上軌（30）"))
        self.results_table.setHorizontalHeaderItem(12, QTableWidgetItem("布林上軌（30）保存值"))
        # 邏輯欄位不移位，讓歷程緊接目前符合狀態出現在可見區。
        self.results_table.horizontalHeader().moveSection(10, 5)
        self.results_table.horizontalHeader().moveSection(11, 4)
        self.results_table.setColumnWidth(10, 220)
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

        history_actions = QHBoxLayout()
        self.history_browse_button = QPushButton("查看選中股票歷史")
        self.history_rebuild_button = QPushButton("建立／重建歷史索引")
        self.history_browse_button.setObjectName("dailyMarketMembershipHistoryBrowse")
        self.history_rebuild_button.setObjectName("dailyMarketMembershipHistoryRebuild")
        self.history_browse_button.setToolTip("每頁最多 32 個原觀測，逐頁核對來源；不改當期名單或收藏。")
        self.history_rebuild_button.setToolTip("只重建派生索引；保留原快照、舊索引版本與收藏，不補跑歷史。")
        self.history_browse_button.clicked.connect(lambda: self._request_history_page(reset=True))
        self.history_rebuild_button.clicked.connect(self._request_history_rebuild)
        history_actions.addWidget(self.history_browse_button)
        history_actions.addWidget(self.history_rebuild_button)
        history_actions.addStretch()
        root.addLayout(history_actions)

        for widget in (
            self.stock_codes_input,
            self.cohort_id_input,
            self.decision_date_edit,
            self.decision_time_edit,
            self.ma20_checkbox,
            self.ma60_checkbox,
            self.bbands30_upper_checkbox,
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
                "預設 API 尚未載入；仍可使用 MA20／MA60／布林上軌手動條件。"
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
            key not in _CONDITION_LABELS
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
                self.bbands30_upper_checkbox,
                self.combine_mode_combo,
                self.filter_state_combo,
            )
        ]
        self.ma20_checkbox.setChecked("close_above_ma20" in condition_keys)
        self.ma60_checkbox.setChecked("close_above_ma60" in condition_keys)
        self.bbands30_upper_checkbox.setChecked("close_above_bbands30_upper" in condition_keys)
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

    def _ensure_history_dialog(self) -> None:
        if self._history_dialog is not None:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("已保存研究觀測歷史")
        dialog.resize(900, 470)
        layout = QVBoxLayout(dialog)
        self.history_status_label = QLabel(self._history_message)
        self.history_status_label.setWordWrap(True)
        layout.addWidget(self.history_status_label)
        notice = QLabel("固定當期來源與截至時點，每頁最多 32 個觀測；同日修訂各列。這是該日保存條件，不授予歷史 PIT 或自然樣本資格。")
        notice.setWordWrap(True)
        layout.addWidget(notice)
        self.history_table = QTableWidget(0, 5)
        self.history_table.setHorizontalHeaderLabels(("觀測日期", "股票", "保存條件", "理由／限制", "發布時刻"))
        self.history_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.history_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        apply_financial_table_style(self.history_table)
        self.history_table.setColumnWidth(3, 340)
        layout.addWidget(self.history_table, 1)
        actions = QHBoxLayout()
        self.history_previous_button = QPushButton("上一頁")
        self.history_next_button = QPushButton("較早一頁")
        self.history_previous_button.clicked.connect(lambda: self._request_history_page(step=-1))
        self.history_next_button.clicked.connect(lambda: self._request_history_page(step=1))
        actions.addWidget(self.history_previous_button)
        actions.addWidget(self.history_next_button)
        actions.addStretch()
        layout.addLayout(actions)
        self._history_dialog = dialog

    def _history_stock_code(self) -> str:
        selected = self.results_table.selectionModel().selectedRows()
        if len(selected) != 1:
            return ""
        item = self.results_table.item(selected[0].row(), 0)
        return item.text().strip() if item is not None else ""

    def _history_query_key(self) -> tuple[object, ...]:
        return (*self._membership_query_key(), self._history_stock_code())

    def _request_history_page(self, *, reset: bool = False, step: int = 0) -> None:
        if self._snapshot is None or self._shutting_down or self._worker is not None:
            return
        reader = getattr(self.service, "read_membership_history_page", None)
        if not callable(reader) or not self._history_stock_code():
            return
        self._ensure_history_dialog()
        assert self._history_dialog is not None
        self._history_dialog.show()
        if reset:
            self._history_cursors = [None]
            self._history_position = 0
            self._history_base_position = 0
            self._history_page = None
        target = self._history_position + step
        if target < 0:
            return
        if step == 1:
            cursor = getattr(self._history_page, "next_cursor", None)
            if not cursor:
                return
            # 有界導航窗口向前滑動，不限制整個長歷史可瀏覽的頁數。
            if target == len(self._history_cursors) and len(self._history_cursors) >= 64:
                self._history_cursors.pop(0)
                self._history_base_position += 1
                self._history_position -= 1
                target -= 1
            if target == len(self._history_cursors):
                self._history_cursors.append(str(cursor))
        if target >= len(self._history_cursors):
            return
        key, snapshot = self._history_query_key(), self._snapshot
        cursor = self._history_cursors[target]
        self._history_message = "正在背景核對本頁來源；當期名單仍保留。"
        self._history_operation = "membership_history_page"
        self._render_history_page()

        def operation(cancel_callback: Callable[[], bool]) -> object:
            page = reader(snapshot, cursor=cursor, page_size=32,
                          condition_keys=key[1], combine_mode=key[2], stock_code=key[3],
                          cancel_callback=cancel_callback)
            return {"query_key": key, "page": page, "position": target}

        self._start_operation("membership_history_page", operation)

    def _request_history_rebuild(self) -> None:
        if self._snapshot is None or self._shutting_down or self._worker is not None:
            return
        builder = getattr(self.service, "rebuild_membership_history_index", None)
        if not callable(builder):
            return
        key = self._membership_query_key()
        self._history_operation = "membership_history_rebuild"
        self._history_message = "正在背景重建派生索引；不修改原快照或收藏。"
        self.status_label.setText(self._history_message)

        def operation(cancel_callback: Callable[[], bool]) -> object:
            result = builder(cancel_callback=cancel_callback)
            return {"query_key": key, "build": result}

        self._start_operation("membership_history_rebuild", operation)

    def _accept_history_operation(self, kind: str, result: object) -> None:
        if not isinstance(result, Mapping):
            self._history_message = "歷史結果缺少來源身份；保持未知。"
        elif kind == "membership_history_rebuild":
            if result.get("query_key") != self._membership_query_key():
                self._history_message = "來源或條件已切換；舊建立回呼不覆蓋當期畫面。"
                self._render_history_page()
                return
            build = result.get("build")
            if getattr(build, "activated", False) is not True:
                self._history_message = "索引沒有完整啟用收據；原來源保留，請明示重試。"
                self._render_history_page()
                return
            self._history_message = "派生索引已完成；可重新核對歷程或明示查看歷史。"
            self._history_page = None
            self._lifecycle_query_key = None
            self._lifecycle_pending = True
        else:
            page = result.get("page")
            if result.get("query_key") != self._history_query_key():
                self._history_message = "股票或條件已切換；舊歷史頁不安裝，請從第一頁重讀。"
                self._render_history_page()
                return
            if (getattr(page, "current_manifest_sha256", "") != self._manifest_sha256
                    or getattr(page, "current_manifest_identity_sha256", "") != self._manifest_identity_sha256
                    or getattr(page, "cohort_id", "") != self._loaded_cohort_id
                    or tuple(getattr(page, "condition_keys", ())) != tuple(sorted(self._selected_condition_keys()))
                    or getattr(page, "combine_mode", "") != str(self.combine_mode_combo.currentData() or "AND")
                    or getattr(page, "stock_code", "") != self._history_stock_code()):
                self._history_page = None
                self._history_message = "歷史來源身份不符；可從第一頁重新核對。"
            else:
                self._history_page = page
                self._history_page_query_key = self._history_query_key()
                self._history_position = int(result.get("position", 0))
                self._history_message = (f"第 {self._history_base_position + self._history_position + 1} 頁；本頁 {len(tuple(getattr(page, 'rows', ())))} 個觀測；"
                                         + ("尚有較早觀測。" if getattr(page, "has_more", False) else "已到此來源截至時點的最早頁。"))
        self._render_history_page()

    def _render_history_page(self) -> None:
        if self._history_dialog is None:
            return
        if self._history_page is not None and self._history_page_query_key != self._history_query_key():
            self._history_page = None
            self._history_page_query_key = None
            self._history_cursors = [None]
            self._history_position = 0
            self._history_base_position = 0
            self._history_message = "股票或條件已切換；請明示從第一頁重新核對。"
        self.history_status_label.setText(self._history_message)
        rows = tuple(getattr(self._history_page, "rows", ()) or ())[:32]
        self.history_table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            values = (getattr(row, "decision_date", ""), getattr(row, "stock_code", ""),
                      _STATE_LABELS.get(str(getattr(row, "state", "unknown")), "未知"),
                      getattr(row, "reason", ""), getattr(row, "published_at", ""))
            audit = (f"manifest={getattr(row, 'manifest_sha256', '')}\n"
                     f"identity={getattr(row, 'manifest_identity_sha256', '')}\n"
                     f"artifact={getattr(row, 'artifact_sha256', '')}\n"
                     f"cutoff={getattr(row, 'cutoff_at', '')}")
            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setToolTip(audit)
                self.history_table.setItem(index, col, item)
        busy = self._worker is not None
        self.history_previous_button.setEnabled(not busy and self._history_position > 0)
        self.history_next_button.setEnabled(not busy and bool(getattr(self._history_page, "next_cursor", None)))

    def _membership_query_key(self) -> tuple[str, tuple[str, ...], str]:
        return (self._manifest_sha256, self._selected_condition_keys(),
                str(self.combine_mode_combo.currentData() or "AND"))

    def _request_membership_read(self) -> None:
        if self._snapshot is None or self._shutting_down:
            return
        reader = getattr(self.service, "read_membership_lifecycle", None)
        key = self._membership_query_key()
        if not key[1]:
            self._lifecycle_result = None
            self._lifecycle_pending = False
            self._lifecycle_error = "請選擇研究條件；入選歷程未知"
            return
        if key == self._lifecycle_query_key:
            return
        self._lifecycle_result = None
        self._lifecycle_error = "歷史不足／正在核對"
        if not callable(reader):
            self._lifecycle_pending = False
            self._lifecycle_error = "歷史不足／此服務未提供歷程 reader"
            return
        if self._worker is not None and self._worker.isRunning():
            self._lifecycle_pending = True
            return
        snapshot = self._snapshot
        self._lifecycle_pending = False
        self._lifecycle_query_key = key

        def operation(cancel_callback: Callable[[], bool]) -> object:
            result = reader(snapshot, key[1], key[2], cancel_callback=cancel_callback)
            return {"query_key": key, "lifecycle": result}

        self._start_operation("membership_lifecycle_read", operation)

    def _accept_membership_read(self, result: object) -> None:
        if not isinstance(result, Mapping):
            self._lifecycle_error = "歷程來源未提供可核驗結果"
            return
        if result.get("query_key") != self._membership_query_key():
            self._lifecycle_pending = True
            return
        model = result.get("lifecycle")
        if (getattr(model, "current_manifest_sha256", "") != self._manifest_sha256
                or getattr(model, "current_manifest_identity_sha256", "")
                != self._manifest_identity_sha256
                or tuple(getattr(model, "condition_keys", ()) or ())
                != tuple(sorted(self._selected_condition_keys()))
                or getattr(model, "combine_mode", "")
                != str(self.combine_mode_combo.currentData() or "AND")
                or str(getattr(model, "current_decision_date", "")) != self._loaded_decision_date
                or getattr(model, "cohort_id", "") != self._loaded_cohort_id):
            self._lifecycle_error = "歷程來源身份不符；保持未知"
            self._lifecycle_result = None
        else:
            self._lifecycle_result = model
            self._lifecycle_error = ""
        self._render_candidate_summary()
        self._render_rows()

    def _membership_row(self, stock_code: str) -> object | None:
        if self._lifecycle_query_key != self._membership_query_key():
            return None
        return next((row for row in tuple(getattr(self._lifecycle_result, "rows", ()) or ())
                     if str(getattr(row, "stock_code", "")) == stock_code), None)

    def _membership_text(self, stock_code: str) -> str:
        row = self._membership_row(stock_code)
        if row is None:
            return self._lifecycle_error or "歷史不足／尚未核對"
        raw = getattr(row, "status", "unknown")
        status = str(getattr(raw, "value", raw)).lower()
        labels = {"new": "本次新入選", "continued": "持續符合",
                  "reentered": "重新入選", "exited": "未再符合",
                  "still_no_match": "持續未符合", "first_observation": "首次觀測／歷史不足",
                  "history_insufficient": "歷史不足", "incomparable": "無法比較",
                  "unknown": "未知"}
        label = labels.get(status, "未知")
        previous = getattr(row, "previous_date", None)
        reason = str(getattr(row, "reason_display", "") or getattr(row, "reason", "") or "未提供比較理由")
        return f"{label} · 前次 {previous or '未提供'} · {reason}"

    def _membership_tooltip(self, stock_code: str) -> str:
        row = self._membership_row(stock_code)
        return (self._membership_text(stock_code) + "\n"
                + f"目前觀測={getattr(row, 'current_observation_id', '')}\n"
                + f"前次觀測={getattr(row, 'previous_observation_id', '')}\n"
                + f"manifest={self._manifest_sha256}\n"
                + f"首次觀測={getattr(row, 'first_seen', None)}；最後命中={getattr(row, 'last_hit', None)}；連續有效期={getattr(row, 'streak', 0)}\n"
                + f"history observations={getattr(row, 'history_observation_ids', ())}\n"
                + f"source identities={getattr(row, 'source_refs', getattr(row, 'source_identities', ()))}\n"
                + "僅比較相同研究條件查詢及具名母體的完整已發布觀測；刷新不寫入歷程事件。")

    def _membership_summary_text(self) -> str:
        rows = tuple(getattr(self._lifecycle_result, "rows", ()) or ())
        if not rows or self._lifecycle_query_key != self._membership_query_key():
            return "入選歷程：" + (self._lifecycle_error or "歷史不足／尚未核對")
        counts: dict[str, int] = {}
        for row in rows:
            text = self._membership_text(str(getattr(row, "stock_code", ""))).split(" · ")[0]
            counts[text] = counts.get(text, 0) + 1
        reason = str(getattr(self._lifecycle_result, "reason_display", "")
                     or getattr(self._lifecycle_result, "reason", ""))
        if reason == "history_complete":
            reason = "已核對可見快照範圍；不表示可比較歷史足夠"
        reasons = tuple(dict.fromkeys(
            str(getattr(row, "reason_display", "") or "") for row in rows
            if getattr(row, "reason_display", "")
        ))
        if all(getattr(row, "previous_date", None) is None for row in rows):
            reason += "；歷史不足／沒有有效前次比較"
        return ("入選歷程：" + "、".join(f"{label} {count}" for label, count in counts.items())
                + "；" + reason + ("；" + "；".join(reasons[:3]) if reasons else ""))

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
            or any(key not in _CONDITION_LABELS for key in condition_keys)
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
                self.bbands30_upper_checkbox,
                self.combine_mode_combo,
            )
        ]
        self.cohort_id_input.setText(cohort_id)
        self.ma20_checkbox.setChecked("close_above_ma20" in condition_keys)
        self.ma60_checkbox.setChecked("close_above_ma60" in condition_keys)
        self.bbands30_upper_checkbox.setChecked("close_above_bbands30_upper" in condition_keys)
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
                include_bbands30_upper="close_above_bbands30_upper" in condition_keys,
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
        include_bbands30_upper: bool = False,
    ) -> dict[str, object]:
        # 未勾選保留原 v2 呼叫契約；勾選才明示產生 v3，讀回仍走原 reader。
        options: dict[str, object] = {}
        if include_bbands30_upper:
            options["include_bbands30_upper"] = True
        result = producer(
            stock_codes,
            decision_cutoff,
            cohort_id,
            cancel_callback=cancel_callback,
            **options,
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
        main_busy = busy and not kind.startswith("membership_history_")
        if self.source_selector is not None:
            self.source_selector.set_external_busy(busy)
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
            self.preset_combo.setEnabled(not main_busy and self.preset_combo.count() > 0)
            self.apply_preset_button.setEnabled(
                available and self._snapshot is not None and not main_busy
            )
            self.cancel_button.setEnabled(busy)
            self.history_browse_button.setEnabled(not busy and self._has_selected_row() and callable(getattr(self.service, "read_membership_history_page", None)))
            self.history_rebuild_button.setEnabled(not busy and self._snapshot is not None and callable(getattr(self.service, "rebuild_membership_history_index", None)))
            self._render_history_page()
            self.open_selected_stock_button.setEnabled(not main_busy and self._has_selected_row())
            self.bookmark_selected_research_button.setEnabled(
                not main_busy
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
                self.bbands30_upper_checkbox,
                self.combine_mode_combo,
                self.filter_state_combo,
                self.preset_combo,
                self.sort_key_combo,
                self.sort_direction_combo,
                self.original_rank_period_combo,
                self.original_rank_direction_combo,
            ):
                widget.setEnabled(not main_busy)
            self.sort_key_combo.setEnabled(not main_busy and self._cohort_projection is not None)
            self.sort_direction_combo.setEnabled(
                not main_busy and self._cohort_projection is not None
            )
            can_read_original = callable(
                getattr(self.service, "read_original_ranking", None)
            )
            self.original_rank_period_combo.setEnabled(
                can_read_original and not main_busy
            )
            self.original_rank_direction_combo.setEnabled(
                can_read_original and not main_busy
            )
            self._sync_original_rank_sort_controls(busy=main_busy)

    def _on_operation_started(self, generation: int, kind: str) -> None:
        if generation == self._operation_generation and not self._shutting_down:
            self._set_busy(True, kind)

    def _on_operation_finished(self, generation: int, kind: str, result: object) -> None:
        if generation != self._operation_generation or self._shutting_down:
            return
        if isinstance(result, Mapping) and result.get("cancelled") is True:
            self._on_operation_cancelled(generation)
            return
        if kind in {"membership_history_page", "membership_history_rebuild"}:
            self._accept_history_operation(kind, result)
            return
        if kind == "membership_lifecycle_read":
            self._accept_membership_read(result)
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
        if operation_kind in {"membership_history_page", "membership_history_rebuild"}:
            self._history_page = None
            self._history_message = "歷史索引／本頁核對失敗；原來源保留，可明示重建或重試：" + str(message).splitlines()[0]
            self._render_history_page()
            self.status_label.setText(self._history_message)
            return
        if operation_kind == "membership_lifecycle_read":
            self._lifecycle_result = None
            self._lifecycle_error = "歷程讀取失敗／保持未知：" + str(message).splitlines()[0]
            self._render_candidate_summary()
            self._render_rows()
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
        if self._lifecycle_query_key is not None and self._lifecycle_result is None:
            self._lifecycle_error = "歷程讀取已取消／保持未知"
            self._render_candidate_summary()
            self._render_rows()
        if self._history_operation:
            self._history_message = "歷史工作已取消；未完成頁不可用，原索引／快照保留。"
            self._render_history_page()
        self.status_label.setText("快照工作已取消；未把未完成讀取呈現為有效結果。")

    def _on_worker_native_finished(self, worker: TaskWorker, generation: int) -> None:
        if self._worker is not worker:
            return
        self._worker = None
        completed_history = bool(self._history_operation)
        self._history_operation = ""
        if not self._shutting_down and generation == self._operation_generation:
            self._set_busy(False)
            self._sync_open_button()
            if self._original_ranking_pending and self._snapshot is not None:
                self._request_original_ranking_read()
            elif self._lifecycle_pending and self._snapshot is not None:
                self._request_membership_read()
            elif completed_history:
                self.status_label.setText(self._history_message)
                self._history_operation = ""
                self._render_history_page()
            elif self._snapshot is not None and self._lifecycle_query_key is not None:
                self.status_label.setText(
                    "已核驗目前快照；入選歷程核對完成，限制見候選摘要。"
                    if self._lifecycle_result is not None
                    else "已核驗目前快照；" + self._lifecycle_error
                )

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
        self._lifecycle_result = None
        self._lifecycle_query_key = None
        self._lifecycle_pending = False
        self._lifecycle_error = "歷史不足／尚未核對"
        self._history_page = None
        self._history_message = "目前來源不可用；原索引保留，歷史頁保持未知。"
        self._render_history_page()
        self._cohort_projection = None
        self._cohort_members_by_code = {}
        self._cohort_full_rows = ()
        self._original_ranking_pending = False
        self._manifest_sha256 = manifest_sha256
        self._manifest_identity_sha256 = manifest_identity
        self._loaded_cohort_id = cohort_id
        self._loaded_decision_date = decision_date
        self._project_multi_method_consensus(snapshot)
        self._render_rule_sample_readiness(snapshot)
        self._selected_stock_code = ""
        self._history_page = None
        self._history_cursors = [None]
        self._history_position = 0
        self._history_message = "當期來源已切換；請明示重新讀取歷史。"
        self._render_history_page()
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

    def _render_rule_sample_readiness(self, snapshot: object) -> None:
        """呈現當期完整控制組；純 DTO 投影不保存 capture 或補入成熟資格。"""
        import json
        try:
            observed = datetime.fromisoformat(self._multi_method_as_of)
            capture = build_rule_research_capture(cast(VerifiedDailyMarketSnapshot, snapshot),
                as_of=observed, observed_at=observed)
            readiness = project_rule_sample_readiness(capture)
            counts = readiness["method_counts"]
            summaries = []
            for item in counts:
                label = next((label for key, label in _CONDITION_LABELS.items()
                    if str(item["method_id"]).endswith(key)), str(item["method_id"]))
                summaries.append(f"{label} 符合 {item['matched']}／不符合 {item['notmatched']}／未知 {item['unknown']}／排除 {item['excluded']}")
            self.sample_readiness_label.setText(
                f"研究樣本：{readiness['decision_date']}，完整聲明單批 {readiness['represented_denominator']} 檔（含排除）；"
                + "；".join(summaries)
                + "。僅當期投影，尚未保存樣本；入選規則、來源當時可得、交易日曆與成熟結果未知。")
            self.sample_readiness_label.setToolTip(json.dumps(readiness, ensure_ascii=False, indent=2))
        except Exception as exc:
            self.sample_readiness_label.setText("研究樣本：完整單批控制組尚未核對；未保存樣本，成熟結果未知。")
            self.sample_readiness_label.setToolTip(f"{type(exc).__name__}: {exc}")

    def _project_multi_method_consensus(self, snapshot: object) -> None:
        """只投影剛接受的 pinned snapshot；不相容時不沿用前次交集。"""

        self._multi_method_consensus = None
        self._multi_method_consensus_error = ""
        observed_at = datetime.now(_TAIPEI)
        self._multi_method_as_of = observed_at.isoformat()
        try:
            sources = adapt_daily_market_snapshot(
                cast(VerifiedDailyMarketSnapshot, snapshot), as_of=observed_at
            )
            self._multi_method_consensus = build_multi_method_consensus(sources)
        except Exception as exc:
            code = str(getattr(exc, "code", "") or "").strip()
            detail = f"{code}: " if code else ""
            self._multi_method_consensus_error = (
                f"{detail}{type(exc).__name__}: {exc}"
            )

    @staticmethod
    def _multi_method_error_label(error: str) -> str:
        code = error.split(":", 1)[0].strip()
        descriptions = {
            "snapshot_type_invalid": "舊版來源不符合 verified pinned snapshot 契約",
            "captured_methods_missing_or_mixed": "快照未帶齊同版方法契約",
            "source_after_as_of": "快照發布時間晚於接受時的本機觀測時鐘",
            "method_version_or_contract_mismatch": "方法版本或方法契約不相容",
            "incomparable_source_scope_or_revision": "方法來源日期、cohort 或版本不能比較",
        }
        description = descriptions.get(code, "來源相容性或身份核驗失敗")
        return f"多方法交集未知／不適用：{description}（{code or error}）。每日研究結果仍可查看。"

    def _multi_method_source_tooltip(self) -> str:
        model = self._multi_method_consensus
        if model is None:
            return (
                f"接受時觀測時間={self._multi_method_as_of or '未提供'}\n"
                f"cohort={self._loaded_cohort_id}\n"
                f"decision_date={self._loaded_decision_date}\n"
                f"manifest_identity_sha256={self._manifest_identity_sha256}\n"
                f"manifest_sha256={self._manifest_sha256}\n"
                f"多方法錯誤={self._multi_method_consensus_error or '未提供'}"
            )
        lines = [
            f"接受時觀測時間={self._multi_method_as_of}",
            "資格=current-observed research only; historical_pit_eligible=false",
        ]
        for source in model.sources:
            lines.extend((
                f"方法={source.method_id}; method_key={source.method_key}; family={source.family}; version={source.version}",
                f"manifest_identity_sha256={source.snapshot_id}; manifest_sha256={source.snapshot_sha256}",
                f"cohort={source.cohort_id}; cohort_sha256={source.cohort_sha256}; decision_date={source.decision_date}",
                f"decision_cutoff={source.decision_cutoff}; published_at={source.published_at}",
                f"method_contracts_sha256={source.contracts_sha256}; parameters={source.parameters_json}",
            ))
        return "\n".join(lines)

    def _multi_method_candidate_text(self) -> str:
        model = self._multi_method_consensus
        if model is None:
            return (
                self._multi_method_error_label(self._multi_method_consensus_error)
                if self._multi_method_consensus_error
                else ""
            )
        family_count = len({source.family for source in model.sources})
        method_counts: list[str] = []
        counts = {method_id: (selected, not_selected, unknown)
                  for method_id, selected, not_selected, unknown in model.method_counts}
        for source in model.sources:
            selected, not_selected, unknown = counts.get(
                source.method_id, (0, 0, model.denominator)
            )
            method_label = _CONDITION_LABELS.get(source.method_key, source.method_key)
            method_counts.append(
                f"{method_label} 符合{selected}／不符合{not_selected}／"
                f"未知{unknown}／分母{model.denominator}"
            )
        counts_text = "；".join(method_counts)
        return (
            f"多方法交集（當期觀測）：{len(model.sources)} 方法／{family_count} 家族；"
            f"{counts_text}；跨家族共同入選未知。"
        )

    def _append_multi_method_candidate_summary(self, detail_lines: list[str]) -> None:
        text = self._multi_method_candidate_text()
        if not text:
            return
        self.candidate_summary_label.setText(
            self.candidate_summary_label.text() + "\n" + text
        )
        detail_lines.append(self._multi_method_source_tooltip())
        model = self._multi_method_consensus
        if model is not None:
            counts = {method_id: (selected, not_selected, unknown)
                      for method_id, selected, not_selected, unknown in model.method_counts}
            for source in model.sources:
                detail_lines.append(
                    f"method_id={source.method_id}; method_key={source.method_key}; "
                    f"family={source.family}; version={source.version}; "
                    f"counts={counts.get(source.method_id)}; denominator={model.denominator}"
                )
                for row in model.rows:
                    observation = dict(row.methods).get(source.method_id)
                    if observation is None:
                        continue
                    detail_lines.append(
                        f"stock={row.stock_code}; method_id={source.method_id}; "
                        f"state={observation.state}; reason={observation.reason}; "
                        f"unknown_reason={observation.unknown_reason}; "
                        f"data_date={observation.data_date or '未知'}; "
                        f"artifact_sha256={observation.artifact_sha256 or '未提供'}"
                    )
        self.candidate_summary_label.setToolTip("\n".join(detail_lines))

    def _multi_method_selected_summary(self, stock_code: str) -> tuple[str, str]:
        model = self._multi_method_consensus
        if model is None:
            text = (
                self._multi_method_error_label(self._multi_method_consensus_error)
                if self._multi_method_consensus_error
                else ""
            )
            return text, self._multi_method_source_tooltip() if text else ""
        row = next((item for item in model.rows if item.stock_code == stock_code), None)
        if row is None:
            return (
                f"多方法摘要未知：{stock_code} 不在此 pinned manifest 的宣告分母內。",
                self._multi_method_source_tooltip(),
            )
        state_labels = {"selected": "符合", "not_selected": "不符合", "unknown": "未知"}
        visible = (
            f"多方法：符合 {row.selected_method_count} 方法／"
            f"{row.selected_family_count} 家族；跨家族共同入選"
            f"{state_labels[row.multi_family_state]}。"
        )
        sources = {source.method_id: source for source in model.sources}
        details = [
            f"股票={stock_code}; selected_method_count={row.selected_method_count}; "
            f"selected_family_count={row.selected_family_count}; "
            f"multi_family_state={row.multi_family_state}; reason={row.multi_family_reason}"
        ]
        for method_id, observation in row.methods:
            source = sources.get(method_id)
            family_version = (
                f"family={source.family}; version={source.version}"
                if source is not None else "來源 metadata 未提供"
            )
            reason = observation.reason
            if observation.unknown_reason:
                reason += f"; unknown_reason={observation.unknown_reason}"
            details.append(
                f"method_id={method_id}; {family_version}; state={observation.state}; "
                f"reason={reason or '未提供'}; data_date={observation.data_date or '未知'}; "
                f"artifact_sha256={observation.artifact_sha256 or '未提供'}; "
                f"stock_snapshot_sha256={observation.stock_snapshot_sha256 or '未提供'}; "
                f"input_sha256={observation.input_sha256 or '未提供'}"
            )
        tooltip = self._multi_method_source_tooltip() + "\n" + "\n".join(details)
        return visible, tooltip

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
                    self._saved_condition_keys(snapshot),
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

    @staticmethod
    def _saved_condition_keys(snapshot: object) -> tuple[str, ...]:
        manifest = getattr(snapshot, "manifest", {})
        version = manifest.get("feature_contract_version") if isinstance(manifest, Mapping) else None
        if version == DAILY_MARKET_FEATURE_CONTRACT_VERSION_BBANDS30_UPPER:
            return feature_contract_for_version(str(version)).condition_keys
        return ("close_above_ma20", "close_above_ma60")

    def _bbands_condition_text(self, condition: object | None) -> str:
        if "close_above_bbands30_upper" not in self._saved_condition_keys(self._snapshot):
            return "未知｜此版本未保存 BB 證據"
        reason = str(getattr(condition, "unknown_reason", "") or "")
        reason_labels = {
            "insufficient_valid_ohlc_streak": "有效觀測不足 30 根",
            "technical_metric_missing": "缺少保存上軌值",
            "technical_source_identity_missing": "上軌來源身份未知",
            "technical_metric_not_observed": "上軌來源品質未知",
            "method_contract_invalid": "上軌方法／參數未核驗",
        }
        detail = "、".join(label for code, label in reason_labels.items() if code in reason)
        return (
            self._condition_text(condition)
            + (f"｜{detail}" if detail else "")
            + "｜來源參數 lineage 未核驗（未知）"
        )

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
                _METHOD_HELP
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
            _METHOD_HELP + "\n已發布方法契約：\n"
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
            self._lifecycle_result = None
            self._lifecycle_pending = False
            self._lifecycle_query_key = None
            self._lifecycle_error = "請選擇研究條件；入選歷程未知"
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
        self._request_membership_read()
        self._render_rows()
        self._render_candidate_summary()

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
            self._append_multi_method_candidate_summary([])
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
            self._append_multi_method_candidate_summary([detail])
            return
        if summary is None:
            self.candidate_summary_label.setText(
                "候選摘要未知：來源未提供完整分母或狀態計數。"
            )
            self.candidate_summary_label.setToolTip(error)
            self._append_multi_method_candidate_summary([error])
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
        self.candidate_summary_label.setText(self.candidate_summary_label.text() + "\n" + self._membership_summary_text())
        details.append(self._membership_summary_text())
        details.append(universe_detail)
        details.append(ranking_summary_text(self._original_ranking))
        details.append(original_rank_row_tooltip(self._original_ranking, None))
        self.candidate_summary_label.setToolTip("\n".join(details))
        self._append_multi_method_candidate_summary(details)

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
        self.local_filter_summary_label.setText(
            f"局部顯示 {len(rows)}／{len(self._all_rows)} 核驗列；完整來源分母與未知條件保留。"
        )
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
                " · ".join(self._membership_text(stock_code).split(" · ")[:2]),
                self._bbands_condition_text(condition_map.get("close_above_bbands30_upper")),
                self._market_value_text(member, "bbands30_upper"),
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
                if column == 10:
                    item.setToolTip(self._membership_tooltip(stock_code))
                if column in {11, 12}:
                    import json
                    payloads = getattr(self._snapshot, "stock_snapshots", {})
                    payload = payloads.get(stock_code, {}) if isinstance(payloads, Mapping) else {}
                    features = payload.get("features", {}) if isinstance(payload, Mapping) else {}
                    feature = features.get("BB_Upper") if isinstance(features, Mapping) else None
                    item.setToolTip(
                        f"manifest_sha256={self._manifest_sha256}\n"
                        + _METHOD_HELP + "\n保存 BB_Upper：\n"
                        + json.dumps(feature, ensure_ascii=False, sort_keys=True)
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
        query = self.current_research_query()
        if query != self._last_emitted_query:
            self._last_emitted_query = query
            self.researchQueryChanged.emit(query)

    def _accept_selected_source(self, value: object) -> None:
        if self._shutting_down or self._worker is not None:
            self.status_label.setText("原名單仍忙碌；未套用來源選擇。")
            return
        if not isinstance(value, tuple) or len(value) != 2 or not isinstance(value[1], VerifiedDailyMarketSnapshot):
            self.status_label.setText("來源選擇未回傳 verified 規則快照；原名單保留。")
            return
        service, snapshot = value
        self.service = service
        self.cohort_id_input.setText(snapshot.cohort_id)
        self._return_query = None
        self._accept_snapshot(snapshot, sync_cutoff=True)

    def current_research_query(self) -> DailyResearchQuery | None:
        if self._snapshot is None or not self._selected_condition_keys():
            return None
        return DailyResearchQuery(self._manifest_sha256, self._manifest_identity_sha256,
            self._selected_condition_keys(), str(self.combine_mode_combo.currentData() or "AND"),
            str(self.filter_state_combo.currentData() or "all"),
            str(self.sort_key_combo.currentData() or "stock_code"),
            str(self.sort_direction_combo.currentData() or "asc") == "desc",
            self.local_stock_filter.text().strip())

    def restore_research_query(self, query: DailyResearchQuery) -> bool:
        """同 pin 精確恢復條件與排序；來源切換時拒絕而非找 latest。"""
        if not isinstance(self._snapshot, VerifiedDailyMarketSnapshot):
            return False
        try:
            query.assert_snapshot(self._snapshot)
        except ValueError:
            return False
        widgets = (self.ma20_checkbox, self.ma60_checkbox, self.bbands30_upper_checkbox,
            self.combine_mode_combo, self.filter_state_combo, self.sort_key_combo,
            self.sort_direction_combo, self.local_stock_filter)
        blockers = [QSignalBlocker(widget) for widget in widgets]
        for widget, key in ((self.ma20_checkbox, "close_above_ma20"),
            (self.ma60_checkbox, "close_above_ma60"),
            (self.bbands30_upper_checkbox, "close_above_bbands30_upper")):
            widget.setChecked(key in query.condition_keys)
        for widget, value in ((self.combine_mode_combo, query.combine_mode),
            (self.filter_state_combo, query.filter_state), (self.sort_key_combo, query.sort_key),
            (self.sort_direction_combo, "desc" if query.descending else "asc")):
            index = widget.findData(value)
            if index < 0:
                return False
            widget.setCurrentIndex(index)
        self.local_stock_filter.setText(query.stock_filter)
        del blockers
        self._apply_filter_controls()
        return True

    def open_stock_from_shared_query(self, code: str, query: DailyResearchQuery) -> bool:
        """市場共用頁沿原 daily context 路由下鑽，不另建研究來源。"""
        if self._shutting_down or self._worker is not None:
            return False
        self._return_query = None
        if not self.restore_research_query(query) or not self.restore_research_snapshot_stock(code, query.manifest_sha256):
            return False
        return self.open_selected_stock()

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
        visible_methods = "、".join(_CONDITION_LABELS.get(key, key) for key in by_key)
        if "close_above_bbands30_upper" in by_key:
            limitations.append("BB 來源參數 lineage 未核驗（未知）；比較結果不授予模型或交易資格")
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
            + _METHOD_HELP
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

        self.selected_summary_label.setText(self.selected_summary_label.text() + "\n入選歷程：" + self._membership_text(code))
        self.selected_summary_label.setToolTip(self.selected_summary_label.toolTip() + "\n" + self._membership_tooltip(code))
        multi_method_text, multi_method_tooltip = self._multi_method_selected_summary(code)
        if multi_method_text:
            self.selected_summary_label.setText(
                self.selected_summary_label.text() + "\n" + multi_method_text
            )
            self.selected_summary_label.setToolTip(
                self.selected_summary_label.toolTip() + "\n" + multi_method_tooltip
            )

    def _current_filtered_rows(self) -> tuple[object, ...]:
        selected_filter = str(self.filter_state_combo.currentData() or "all")
        stock_filter = self.local_stock_filter.text().strip()
        return tuple(
            row
            for row in self._all_rows
            if (selected_filter == "all"
                or str(getattr(row, "combined_state", "unknown") or "unknown") == selected_filter)
            and (not stock_filter or stock_filter in str(getattr(row, "stock_code", "")))
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
        if self.bbands30_upper_checkbox.isChecked():
            keys.append("close_above_bbands30_upper")
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
        busy = self._worker is not None or self._shutting_down
        self.history_browse_button.setEnabled(not busy and self._has_selected_row() and callable(getattr(self.service, "read_membership_history_page", None)))
        self.history_rebuild_button.setEnabled(not busy and self._snapshot is not None and callable(getattr(self.service, "rebuild_membership_history_index", None)))
        self._render_history_page()
        main_available = self._worker is None or not self._worker.isRunning() or bool(self._history_operation)
        self.open_selected_stock_button.setEnabled(
            not self._shutting_down
            and main_available
            and self._has_selected_row()
        )
        if hasattr(self, "bookmark_selected_research_button"):
            is_original_rank = (
                str(self.sort_key_combo.currentData() or "")
                == "original_strength_rank"
            )
            bookmark_source_ready = (
                self._original_ranking is not None
                if is_original_rank
                else self._snapshot is not None
            )
            self.bookmark_selected_research_button.setEnabled(
                self.watchlist_service is not None
                and bookmark_source_ready
                and not self._shutting_down
                and main_available
                and self._has_selected_row()
            )
        if hasattr(self, "apply_preset_button"):
            self.apply_preset_button.setEnabled(
                self.service is not None
                and self._snapshot is not None
                and not self._shutting_down
                and main_available
            )

    def bookmark_selected_research(self) -> bool:
        """保存已核驗的選取列；只有使用者確認後才呼叫觀察清單服務。"""

        if str(self.sort_key_combo.currentData() or "") == "original_strength_rank":
            return self._bookmark_selected_original_ranking()
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

    def _bookmark_selected_original_ranking(self) -> bool:
        if (
            self.watchlist_service is None
            or self._snapshot is None
            or self._original_ranking is None
            or self._shutting_down
        ):
            reason = self._original_ranking_error or "尚未有可核驗原始排名。"
            self.status_label.setText(f"原始排名來源不可用；未收藏。原因：{reason}")
            return False
        selected = self.results_table.selectionModel().selectedRows()
        if len(selected) != 1:
            self.status_label.setText("請先選取一列已核驗的原始排名結果。")
            return False
        item = self.results_table.item(selected[0].row(), 0)
        row = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        stock_code = str(getattr(row, "stock_code", "") or "").strip()
        if not stock_code:
            self.status_label.setText("選取列缺少原始股票身份；未收藏。")
            return False
        try:
            from app_module.daily_market_research_bookmark import (
                create_original_stock_ranking_bookmark,
            )

            context_builder = getattr(self.service, "context_for_stock", None)
            if not callable(context_builder):
                raise ValueError("rank bookmark requires the verified parent context builder")
            inherited_context = context_builder(row, stock_name="")
            repository = getattr(self.service, "original_ranking_repository", None)
            ranking_root = getattr(repository, "ranking_root", "")
            filter_state = str(self.filter_state_combo.currentData() or "all")
            descending = (
                str(self.sort_direction_combo.currentData() or "asc").lower()
                in {"desc", "descending"}
            )
            bookmark = create_original_stock_ranking_bookmark(
                self._snapshot,
                self._original_ranking,
                ranking_root=ranking_root,
                stock_code=stock_code,
                source_context=research_context_for_original_stock_ranking(
                    self._snapshot,
                    self._original_ranking,
                    ranking_root=ranking_root,
                    stock_code=stock_code,
                    source_workspace="recommendation",
                    source_label="原始日／週排名研究",
                    inherited_context=inherited_context,
                    filter_state=filter_state,
                    sort_key="rank",
                    descending=descending,
                ),
                filter_state=filter_state,
                sort_key="rank",
                descending=descending,
            )
        except Exception as exc:
            self.status_label.setText(
                f"原始排名書籤無法核驗；未收藏：{type(exc).__name__}: {exc}"
            )
            return False
        if not self._confirm_original_ranking_bookmark(bookmark, stock_code):
            self.status_label.setText("已取消原排名收藏；觀察清單未變更。")
            return False
        add_bookmark = getattr(
            self.watchlist_service, "add_rank_research_bookmark", None
        )
        if not callable(add_bookmark):
            self.status_label.setText("觀察清單服務不支援版本化原排名收藏；未保存。")
            return False
        try:
            result = add_bookmark(bookmark)
        except Exception as exc:
            self.status_label.setText(
                f"原排名收藏保存失敗：{type(exc).__name__}: {exc}。"
            )
            return False
        status = str(getattr(result, "status", "") or "")
        if status == "conflict":
            message = str(getattr(result, "message", "") or "書籤身份衝突")
            self.status_label.setText(f"{message}；未覆寫既有收藏。")
            return False
        if status not in {"added", "already_present"}:
            self.status_label.setText(
                str(getattr(result, "message", "原排名收藏未能保存。"))
            )
            return False
        self.bookmarkSaved.emit(bookmark)
        self.status_label.setText(
            f"{'已收藏' if status == 'added' else '此原排名已收藏'} {stock_code}；保留此版本來源。"
        )
        return True

    def _confirm_original_ranking_bookmark(
        self, bookmark: object, stock_code: str
    ) -> bool:
        callback = self.bookmark_confirmation_callback
        if callback is not None:
            try:
                return bool(callback(bookmark))
            except Exception as exc:
                self.status_label.setText(
                    f"原排名收藏確認流程失敗：{type(exc).__name__}: {exc}；未保存。"
                )
                return False
        ranking = self._original_ranking
        if ranking is None:
            return False
        row = next(
            (item for item in ranking.rows if item.get("stock_code") == stock_code),
            None,
        )
        if row is None:
            return False
        rank_label = str(row.get("score_label") or "")
        query = getattr(bookmark, "query", {})
        query_text = str(query or "")
        details = (
            f"股票：{stock_code}｜原名次：{row.get('rank')}｜publisher 標籤：{rank_label}\n"
            f"模式：{'週' if ranking.period == 'week' else '日'}／"
            f"{'強勢 Top' if ranking.direction == 'strong' else '弱勢 Bottom'}\n"
            f"比較日：{row.get('comparison_date')} → 最新日：{row.get('latest_date')}\n"
            f"研究母體：{ranking.metadata.get('research_universe_sha256', '未知')}\n"
            f"方法：{ranking.metadata.get('engine_method', '未知')} "
            f"{ranking.metadata.get('engine_version', '')}\n"
            f"排名來源 manifest：{ranking.manifest_identity_sha256}\n"
            f"排名來源 SHA-256：{ranking.manifest_sha256}"
        )
        if query_text:
            details += f"\n保存查詢偏好：{query_text}"
        return (
            QMessageBox.question(
                self,
                "確認收藏此原排名研究",
                f"將此已驗證的原排名來源版本加入觀察清單？\n\n{details}",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            == QMessageBox.StandardButton.Yes
        )

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
            is_original_rank = (
                str(self.sort_key_combo.currentData() or "")
                == "original_strength_rank"
            )
            if is_original_rank:
                ranking = self._original_ranking
                repository = getattr(self.service, "original_ranking_repository", None)
                ranking_root = getattr(repository, "ranking_root", "")
                if ranking is None:
                    raise ValueError(
                        self._original_ranking_error or "原始排名尚未通過來源驗證。"
                    )
                context = research_context_for_original_stock_ranking(
                    self._snapshot,
                    ranking,
                    ranking_root=ranking_root,
                    stock_code=str(getattr(row, "stock_code", "") or "").strip(),
                    source_workspace="recommendation",
                    source_label="原始日／週排名研究",
                    inherited_context=context,
                    filter_state=str(self.filter_state_combo.currentData() or "all"),
                    sort_key="rank",
                    descending=(
                        str(self.sort_direction_combo.currentData() or "asc").lower()
                        in {"desc", "descending"}
                    ),
                )
        except Exception as exc:
            self.status_label.setText(
                f"無法建立釘選快照 context：{type(exc).__name__}: {exc}"
            )
            return False
        stock_code = str(getattr(row, "stock_code", "") or "").strip()
        if getattr(context, "rank_context", None) is not None:
            rank_context = context.rank_context
            expected_rank = {
                "source_kind": "original_stock_ranking",
                "source_workspace": "recommendation",
                "stock_code": stock_code,
                "decision_date": str(getattr(row, "decision_date", "") or ""),
            }
            for name, value in expected_rank.items():
                if str(getattr(context, name, "") or "").strip() != value:
                    self.status_label.setText(
                        f"下鑽 rank context 的 {name} 與選取列身份不一致；未開啟報告。"
                    )
                    return False
            if rank_context.selected_stock_code != stock_code:
                self.status_label.setText("rank context 選取股票不符；未開啟報告。")
                return False
            if rank_context.source_hash != self._original_ranking.manifest_sha256:
                self.status_label.setText("rank context manifest hash 與目前已驗證排名不同。")
                return False
            self._selected_stock_code = stock_code
            self.stockResearchRequested.emit(context)
            self.status_label.setText(
                f"已開啟 {stock_code} 的唯讀個股研究；原始排名列與 hash 已固定。"
            )
            return True
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
        query = self.current_research_query()
        if query is not None and isinstance(self._snapshot, VerifiedDailyMarketSnapshot):
            self._return_query = (stock_code, query)
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
            self._shutting_down
            or not requested
            or self._snapshot is None
            or not expected_hash
            or expected_hash != self._manifest_sha256
        ):
            self.status_label.setText(
                "原每日研究快照尚未載入或 manifest 已變；請返回每日研究條件重讀／更新快照。"
            )
            return False
        if self._return_query is not None and self._return_query[0] == requested:
            query = self._return_query[1]
            if query.manifest_sha256 != expected_hash or not self.restore_research_query(query):
                self.status_label.setText("原查詢來源已變更；未以最新名單替代原研究。")
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

        selector_done = self.source_selector is None or self.source_selector.begin_shutdown()
        if self._shutting_down:
            worker = self._worker
            return selector_done and (worker is None or not worker.isRunning())
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
            self.bbands30_upper_checkbox,
            self.combine_mode_combo,
            self.filter_state_combo,
            self.sort_key_combo,
            self.sort_direction_combo,
            self.results_table,
            self.local_stock_filter,
        ):
            widget.setEnabled(False)
        worker = self._worker
        if worker is not None and worker.isRunning():
            worker.cancel(cooperative=True, wait=False)
            return False
        return selector_done

    def _clear_current_snapshot(self) -> None:
        self._snapshot = None
        self.local_filter_summary_label.setText("局部顯示：來源已清除，尚無核驗名單。")
        self.sample_readiness_label.setText("研究樣本：來源已清除，完整單批控制組與成熟結果未知。")
        self.sample_readiness_label.setToolTip("")
        self._multi_method_consensus = None
        self._multi_method_consensus_error = ""
        self._multi_method_as_of = ""
        self._lifecycle_result = None
        self._lifecycle_query_key = None
        self._lifecycle_pending = False
        self._lifecycle_error = "歷史不足／尚未核對"
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
