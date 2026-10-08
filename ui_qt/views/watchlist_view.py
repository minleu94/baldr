"""
觀察清單視圖
管理跨 Tab 共用的股票觀察清單
"""

from collections.abc import Mapping
import json
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QBoxLayout, QLabel,
    QPushButton, QTableView, QMessageBox, QDialog,
    QDialogButtonBox, QLineEdit, QTextEdit, QListWidget,
    QListWidgetItem, QHeaderView, QMenu, QAbstractItemView,
    QGroupBox, QSplitter, QSizePolicy, QInputDialog
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QAction
import pandas as pd
import logging
from datetime import date, datetime
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)
from typing import List, Dict, Optional

from ui_qt.models.pandas_table_model import PandasTableModel
from app_module.watchlist_service import WatchlistService, WatchlistStorageStatus
from app_module.watchlist_review_state import WatchlistReviewSourceIdentity, WatchlistReviewState
from app_module.dtos.decision_continuity_dtos import (
    DecisionIdentity,
    IDENTITY_STATUS_CONFLICT,
    IDENTITY_STATUS_UNKNOWN,
)
from app_module.universe_service import UniverseService
from app_module.watchlist_analysis_service import WatchlistAnalysisService
from app_module.decision_presentation import (
    DecisionPresentationService,
    format_decision_presentation,
)
from app_module.research_session import (
    ResearchStockContextDTO,
    format_research_workflow_path,
)
from app_module.daily_market_research_bookmark import (
    DAILY_MARKET_RESEARCH_BOOKMARK_SOURCE,
    ORIGINAL_STOCK_RANKING_BOOKMARK_SCHEMA,
    decode_daily_market_research_bookmark,
)
from app_module.daily_market_technical_universe_v4_bookmark import (
    DAILY_MARKET_TECHNICAL_UNIVERSE_V4_BOOKMARK_SCHEMA,
    DAILY_MARKET_TECHNICAL_UNIVERSE_V4_BOOKMARK_SOURCE,
    DailyMarketTechnicalUniverseV4Bookmark,
)
from ui_qt.workers.task_worker import TaskWorker
from ui_qt.widgets.info_button import InfoButton
from ui_qt.widgets.layout_helpers import create_scroll_area, ensure_visible_rows
from ui_qt.widgets.table_style import apply_financial_table_style
from ui_qt.widgets.technical_universe_bookmark_controls import (
    DailyMarketTechnicalUniverseV4BookmarkControls,
)
from ui_qt.widgets.personal_h20_bookmark_controls import PersonalH20BookmarkControls
from ui_qt.widgets.v5_research_summary import V5ResearchSummary


class WatchlistView(QWidget):
    """觀察清單視圖"""
    
    # 信號：當觀察清單更新時發出
    watchlistUpdated = Signal()
    sendToBacktestRequested = Signal(dict)
    stockAnalysisRequested = Signal(str)
    stockResearchRequested = Signal(object)
    latestResearchRequested = Signal(object)
    technicalBookmarkStateReady = Signal(object)
    personalH20BookmarkStateReady = Signal(object)
    
    def __init__(
        self,
        watchlist_service: WatchlistService,
        config=None,
        parent=None,
        presentation_service: DecisionPresentationService | None = None,
    ):
        """初始化觀察清單視圖
        
        Args:
            watchlist_service: 觀察清單服務實例
            config: TWStockConfig 實例（用於初始化 UniverseService）
            parent: 父窗口
        """
        logger.info("[WatchlistView] 開始初始化...")
        super().__init__(parent)
        logger.info("[WatchlistView] 父類初始化完成")
        
        self.watchlist_service = watchlist_service
        self.config = config
        self.presentation_service = presentation_service or DecisionPresentationService()
        self.analysis_service = WatchlistAnalysisService(config) if config and hasattr(config, "output_root") else None
        self._analysis_request_id = 0
        self._analysis_worker: TaskWorker | None = None
        self._shutdown_started = False
        self.personal_h20_bookmark_controls: PersonalH20BookmarkControls | None = None
        self._research_bookmark_restore_tokens: list[object] = []
        self._observation_review: WatchlistReviewState | None = None
        logger.info("[WatchlistView] watchlist_service 設置完成")
        
        # 初始化選股清單服務（用於回測）
        if config:
            try:
                self.universe_service = UniverseService(config)
                logger.info("[WatchlistView] universe_service 初始化成功")
            except Exception as e:
                logger.warning(f"[WatchlistView] 警告：universe_service 初始化失敗: {e}")
                self.universe_service = None
        else:
            self.universe_service = None
        
        # 數據模型
        self.stocks_model: Optional[PandasTableModel] = None
        
        logger.info("[WatchlistView] 開始設置 UI...")
        self._setup_ui()
        logger.info("[WatchlistView] UI 設置完成")
        
        # 延遲載入觀察清單，避免初始化時出錯導致整個程式崩潰
        logger.info("[WatchlistView] 開始載入觀察清單...")
        try:
            self._load_watchlist()
            logger.info("[WatchlistView] 觀察清單載入成功")
        except Exception as e:
            import traceback
            logger.error(f"[WatchlistView] 錯誤：初始化時載入觀察清單失敗")
            logger.error(f"[WatchlistView] 錯誤類型: {type(e).__name__}")
            logger.error(f"[WatchlistView] 錯誤訊息: {str(e)}")
            logger.error(f"[WatchlistView] 詳細堆疊追蹤:\n{traceback.format_exc()}")
            # 顯示空表格，不阻止程式啟動
            try:
                self.stocks_model = PandasTableModel(self._empty_frame())
                self.stocks_table.setModel(self.stocks_model)
                self.stats_label.setText("共 0 檔股票（載入失敗）")
                self._set_status_label("載入失敗，請檢查數據文件", level="error")
                logger.error("[WatchlistView] 已顯示錯誤提示")
            except Exception as e2:
                logger.error(f"[WatchlistView] 顯示錯誤提示時也失敗: {e2}")
        
        logger.info("[WatchlistView] 初始化完成")
    
    def _setup_ui(self):
        """設置 UI"""
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        content = QWidget()
        content.setObjectName("watchlistPageContent")
        main_layout = QVBoxLayout(content)
        main_layout.setSpacing(8)
        main_layout.setContentsMargins(10, 10, 10, 10)
        self.page_scroll = create_scroll_area(content, object_name="watchlistPageScroll")
        outer_layout.addWidget(self.page_scroll)
        
        # 標題列（標題 + InfoButton）
        title_layout = QHBoxLayout()
        title = QLabel("候選池")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title.setFont(title_font)
        title_layout.addWidget(title)
        title_layout.addStretch()
        info_btn = InfoButton("watchlist", self)
        title_layout.addWidget(info_btn)
        main_layout.addLayout(title_layout)

        page_hint = QLabel(
            "研究路徑：" + format_research_workflow_path() +
            "\n左側整理候選股票；右側保存可重用的選股清單。"
        )
        page_hint.setProperty("role", "muted")
        page_hint.setObjectName("watchlistPageHint")
        page_hint.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        main_layout.addWidget(page_hint)

        storage_row = QHBoxLayout()
        self.storage_status_label = QLabel("觀察清單儲存狀態：讀取中…")
        self.storage_status_label.setObjectName("watchlistStorageStatus")
        self.storage_status_label.setProperty("role", "status")
        self.storage_status_label.setWordWrap(True)
        storage_row.addWidget(self.storage_status_label, 1)
        self.upgrade_storage_btn = QPushButton("升級觀察清單儲存")
        self.upgrade_storage_btn.setObjectName("watchlistUpgradeStorage")
        self.upgrade_storage_btn.setProperty("variant", "secondary")
        self.upgrade_storage_btn.setAccessibleName("升級觀察清單儲存")
        self.upgrade_storage_btn.setToolTip(
            "只在你明確按下後，將原 JSON 複製並核對到獨立 SQLite，成功後切換儲存；原 JSON 保留。"
        )
        self.upgrade_storage_btn.clicked.connect(self._upgrade_watchlist_storage)
        storage_row.addWidget(self.upgrade_storage_btn)
        main_layout.addLayout(storage_row)
        self._refresh_storage_status()

        # 桌面版只保留兩個有清楚責任的主面板：候選池與已保存清單；
        # 窄版才回到上下排列，維持同一套閱讀順序。
        main_splitter = QSplitter(Qt.Horizontal)
        main_splitter.setObjectName("watchlistMainSplitter")
        main_splitter.setChildrenCollapsible(False)
        main_splitter.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.main_splitter = main_splitter
        self._watchlist_layout_mode: bool | None = None

        # ========== 左側：候選池主工作區 ==========
        candidate_panel = QGroupBox("觀察候選池")
        candidate_panel.setObjectName("watchlistCandidatePanel")
        candidate_layout = QVBoxLayout(candidate_panel)
        candidate_layout.setSpacing(8)
        candidate_layout.setContentsMargins(12, 14, 12, 12)

        # 保留可被搜尋與輔助工具辨識的頁內標題；視覺上由外層面板標題統一呈現。
        work_title = QLabel("觀察候選池")
        work_title_font = QFont()
        work_title_font.setPointSize(11)
        work_title_font.setBold(True)
        work_title.setFont(work_title_font)
        self.work_title = work_title
        candidate_layout.addWidget(work_title)

        candidate_hint = QLabel("選取一檔股票查看摘要；雙擊或按鈕可開啟完整研究報告。")
        candidate_hint.setProperty("role", "muted")
        candidate_hint.setObjectName("watchlistCandidateHint")
        self.candidate_hint = candidate_hint
        candidate_layout.addWidget(candidate_hint)

        self.source_link_hint = QLabel(
            "「推薦來源」用來找回當時的推薦理由與後續結果，不是評分或買賣訊號。"
            "未連結時可選取股票後按「選擇原推薦來源」；來源不一致時請先核對原推薦。"
        )
        self.source_link_hint.setWordWrap(True)
        self.source_link_hint.setProperty("role", "muted")
        candidate_layout.addWidget(self.source_link_hint)

        self.watchlist_focus_summary = V5ResearchSummary("目前候選池重點")
        self.watchlist_focus_summary.setAccessibleName("候選池日常摘要")
        self.watchlist_focus_summary.setToolTip(
            "先看候選池狀態、來源可追溯性與下一步；完整研究內容由進階入口開啟。"
        )
        candidate_layout.addWidget(self.watchlist_focus_summary)

        # 操作區留在候選池內，讓使用者不必在三個區塊間來回尋找。
        watchlist_ops_group = QGroupBox("候選池操作")
        watchlist_ops_group.setObjectName("watchlistOpsGroup")
        watchlist_ops_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.watchlist_ops_group = watchlist_ops_group
        watchlist_ops_layout = QHBoxLayout(watchlist_ops_group)
        self.watchlist_ops_layout = watchlist_ops_layout
        watchlist_ops_layout.setSpacing(8)
        watchlist_ops_layout.setContentsMargins(8, 8, 8, 8)

        self.refresh_btn = QPushButton("刷新")
        self.refresh_btn.setProperty("variant", "secondary")
        self.refresh_btn.setMinimumHeight(30)
        self.refresh_btn.clicked.connect(self._load_watchlist)
        watchlist_ops_layout.addWidget(self.refresh_btn)

        self.add_btn = QPushButton("新增股票")
        self.add_btn.setProperty("variant", "secondary")
        self.add_btn.setMinimumHeight(30)
        self.add_btn.clicked.connect(self._show_add_dialog)
        watchlist_ops_layout.addWidget(self.add_btn)

        self.remove_btn = QPushButton("移除選中")
        self.remove_btn.setProperty("variant", "secondary")
        self.remove_btn.setMinimumHeight(30)
        self.remove_btn.clicked.connect(self._remove_selected)
        watchlist_ops_layout.addWidget(self.remove_btn)

        self.clear_btn = QPushButton("清空候選池")
        self.clear_btn.setProperty("variant", "danger")
        self.clear_btn.setMinimumHeight(30)
        self.clear_btn.clicked.connect(self._clear_watchlist)
        watchlist_ops_layout.addWidget(self.clear_btn)
        watchlist_ops_layout.addStretch()
        candidate_layout.addWidget(watchlist_ops_group)

        # 表格是候選池的主內容，讓它取得左側大部分可用高度。
        self.stocks_table = QTableView()
        apply_financial_table_style(self.stocks_table)
        self.stocks_table.setSelectionBehavior(QTableView.SelectRows)
        self.stocks_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.stocks_table.setSortingEnabled(True)
        self.stocks_table.setMinimumHeight(90)
        self.stocks_table.horizontalHeader().setStretchLastSection(True)
        self.stocks_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.stocks_table.setFocusPolicy(Qt.StrongFocus)
        self.stocks_table.setTabKeyNavigation(True)
        self.stocks_table.setAlternatingRowColors(True)
        self.stocks_table.setAccessibleName("觀察候選池股票表")
        self.stocks_table.setAccessibleDescription(
            "唯讀候選池；可用方向鍵選列，選取後查看研究／等待狀態與來源詳情。"
        )
        self.stocks_table.verticalHeader().setDefaultSectionSize(28)
        self.stocks_table.verticalHeader().setMinimumSectionSize(28)
        ensure_visible_rows(self.stocks_table, 5)

        # 右鍵選單
        self.stocks_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.stocks_table.customContextMenuRequested.connect(self._show_context_menu)

        candidate_layout.addWidget(self.stocks_table, stretch=1)
        self.stocks_table.doubleClicked.connect(self._open_stock_analysis)

        # 研究摘要明確標示，不再讓 QTextEdit 看起來像不明原因的第三個區塊。
        analysis_group = QGroupBox("個股研究摘要")
        analysis_group.setObjectName("watchlistResearchSummary")
        analysis_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.analysis_group = analysis_group
        self.analysis_group.setVisible(False)
        analysis_layout = QVBoxLayout(analysis_group)
        analysis_layout.setSpacing(6)
        analysis_layout.setContentsMargins(8, 10, 8, 8)
        analysis_header_layout = QHBoxLayout()
        analysis_hint = QLabel("只讀取已保存的推薦證據，不重新計算。")
        analysis_hint.setProperty("role", "muted")
        self.analysis_hint = analysis_hint
        analysis_header_layout.addWidget(analysis_hint)
        analysis_header_layout.addStretch()

        self.stock_analysis_btn = QPushButton("查看選中個股研究報告")
        self.stock_analysis_btn.setProperty("variant", "primary")
        self.stock_analysis_btn.setAccessibleName("查看選中個股研究報告")
        self.stock_analysis_btn.setToolTip(
            "選取一檔股票後開啟同一份個股研究報告；也可雙擊或從右鍵選單開啟。"
        )
        # 舊的 stockAnalysisRequested signal 保留給獨立嵌入頁與既有測試；
        # MainWindow 以 stockResearchRequested 作為唯一正式報告入口。
        self.stock_research_btn = self.stock_analysis_btn
        self.stock_analysis_btn.setEnabled(False)
        self.stock_analysis_btn.clicked.connect(self._open_stock_analysis)
        self.latest_research_btn = QPushButton("以最新來源另開研究")
        self.latest_research_btn.setProperty("variant", "secondary")
        self.latest_research_btn.setAccessibleName("以最新來源另開唯讀研究")
        self.latest_research_btn.setToolTip(
            "明確要求以目前最新來源另開唯讀研究；不更改已保存書籤的來源。"
        )
        self.latest_research_btn.setEnabled(False)
        self.latest_research_btn.clicked.connect(self._open_latest_source_research)
        self.choose_source_btn = QPushButton("選擇原推薦來源")
        self.choose_source_btn.setProperty("variant", "secondary")
        self.choose_source_btn.setAccessibleName("選擇原推薦來源")
        self.choose_source_btn.setToolTip(
            "legacy 候選沒有 exact result_id 時，明確選取保存結果；不會自動套用最新結果。"
        )
        self.choose_source_btn.setVisible(False)
        self.choose_source_btn.clicked.connect(self._choose_recommendation_source)
        self.restore_research_bookmark_btn = QPushButton("還原剛移除的研究書籤")
        self.restore_research_bookmark_btn.setProperty("variant", "ghost")
        self.restore_research_bookmark_btn.setEnabled(False)
        self.restore_research_bookmark_btn.setVisible(False)
        self.restore_research_bookmark_btn.clicked.connect(
            self._restore_last_research_bookmark
        )
        analysis_layout.addLayout(analysis_header_layout)

        self.analysis_context_label = QLabel(
            "狀態：尚未選取｜決策日：未知｜資料日：未知｜來源：未知"
        )
        self.analysis_context_label.setProperty("role", "status")
        self.analysis_context_label.setWordWrap(True)
        self.analysis_context_label.setAccessibleName("觀察清單研究狀態")
        analysis_layout.addWidget(self.analysis_context_label)

        self.analysis_text = QTextEdit()
        self.analysis_text.setObjectName("watchlistAnalysisText")
        self.analysis_text.setReadOnly(True)
        self.analysis_text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.analysis_text.setMinimumHeight(96)
        self.analysis_text.setPlaceholderText("選取一檔股票，查看共用呈現契約與已保存的推薦理由。")
        analysis_layout.addWidget(self.analysis_text)
        candidate_layout.addWidget(analysis_group)

        # 主要下一步與保存動作集中在候選池底部，並與資料區保持明確界線。
        next_actions_group = QGroupBox("下一步")
        next_actions_group.setObjectName("watchlistNextActions")
        next_actions_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.next_actions_group = next_actions_group
        next_actions_layout = QVBoxLayout(next_actions_group)
        next_actions_layout.setSpacing(4)
        next_actions_layout.setContentsMargins(8, 8, 8, 8)
        research_actions_layout = QHBoxLayout()
        self.research_actions_layout = research_actions_layout
        research_actions_layout.setSpacing(8)
        research_actions_layout.addWidget(self.stock_analysis_btn)
        research_actions_layout.addWidget(self.latest_research_btn)
        research_actions_layout.addWidget(self.choose_source_btn)
        research_actions_layout.addWidget(self.restore_research_bookmark_btn)
        research_actions_layout.addStretch()
        batch_actions_layout = QHBoxLayout()
        self.batch_actions_layout = batch_actions_layout
        batch_actions_layout.setSpacing(8)

        self.send_to_research_lab_btn = QPushButton("送 Research Lab 批次回測")
        self.send_to_research_lab_btn.setProperty("variant", "secondary")
        self.send_to_research_lab_btn.setEnabled(False)
        self.send_to_research_lab_btn.setToolTip("候選池目前沒有股票，加入股票後即可送 Research Lab 批次回測。")
        self.send_to_research_lab_btn.clicked.connect(self._send_to_research_lab)
        batch_actions_layout.addWidget(self.send_to_research_lab_btn)

        self.save_to_universe_btn = QPushButton("保存為選股清單")
        self.save_to_universe_btn.setProperty("variant", "secondary")
        self.save_to_universe_btn.setToolTip("將目前候選池作為批次股票回測的輸入。")
        self.save_to_universe_btn.clicked.connect(self._save_watchlist_to_universe)
        batch_actions_layout.addWidget(self.save_to_universe_btn)
        self.toggle_advanced_research_btn = QPushButton("顯示進階研究")
        self.toggle_advanced_research_btn.setProperty("variant", "ghost")
        self.toggle_advanced_research_btn.setAccessibleName("顯示候選池進階研究")
        self.toggle_advanced_research_btn.setToolTip(
            "展開已保存分析、完整共用證據與原推薦來源選擇；不會重新評分。"
        )
        self.toggle_advanced_research_btn.setCheckable(True)
        self.toggle_advanced_research_btn.toggled.connect(
            self._toggle_advanced_research
        )
        batch_actions_layout.addWidget(self.toggle_advanced_research_btn)
        batch_actions_layout.addStretch()
        next_actions_layout.addLayout(research_actions_layout)
        next_actions_layout.addLayout(batch_actions_layout)

        technical_bookmark_group = QGroupBox("完整母體技術研究收藏")
        technical_bookmark_group.setObjectName("watchlistTechnicalUniverseBookmarks")
        technical_bookmark_layout = QVBoxLayout(technical_bookmark_group)
        technical_bookmark_layout.setContentsMargins(8, 6, 8, 8)
        self.technical_bookmark_controls = DailyMarketTechnicalUniverseV4BookmarkControls(
            self.watchlist_service,
            parent=technical_bookmark_group,
        )
        self.technical_bookmark_controls.stateReady.connect(
            self.technicalBookmarkStateReady.emit
        )
        technical_bookmark_layout.addWidget(self.technical_bookmark_controls)
        next_actions_layout.addWidget(technical_bookmark_group)
        self.personal_h20_bookmark_group = QGroupBox("個人 H20 原保存研究收藏")
        self.personal_h20_bookmark_group.setObjectName("watchlistPersonalH20Bookmarks")
        self._personal_h20_bookmark_layout = QVBoxLayout(self.personal_h20_bookmark_group)
        self._personal_h20_bookmark_hint = QLabel("尚未指定個人研究設定。")
        self._personal_h20_bookmark_hint.setWordWrap(True)
        self._personal_h20_bookmark_layout.addWidget(self._personal_h20_bookmark_hint)
        next_actions_layout.addWidget(self.personal_h20_bookmark_group)
        candidate_layout.addWidget(next_actions_group)

        observation_group = QGroupBox("收藏理由與查看狀態")
        observation_layout = QVBoxLayout(observation_group)
        self.observation_reason_label = QLabel("收藏理由：尚未選取")
        self.observation_reason_label.setTextFormat(Qt.PlainText)
        self.observation_reason_label.setWordWrap(True)
        self.observation_change_label = QLabel("較前變化：未知；沒有同源比較資料。")
        self.observation_change_label.setTextFormat(Qt.PlainText)
        self.observation_change_label.setWordWrap(True)
        self.observation_state_label = QLabel("查看狀態：尚未選取；私人理由與狀態不改研究證據。")
        self.observation_state_label.setWordWrap(True)
        observation_layout.addWidget(self.observation_reason_label)
        observation_layout.addWidget(self.observation_change_label)
        observation_layout.addWidget(self.observation_state_label)
        observation_actions = QHBoxLayout()
        self.confirm_observation_button = QPushButton("已確認查看")
        self.later_observation_button = QPushButton("稍後查看")
        self.edit_observation_reason_button = QPushButton("編輯收藏理由")
        self.edit_observation_reason_button.clicked.connect(self._edit_observation_reason)
        self.confirm_observation_button.clicked.connect(lambda: self._set_observation_state("confirmed"))
        self.later_observation_button.clicked.connect(lambda: self._set_observation_state("deferred"))
        for button in (self.edit_observation_reason_button, self.confirm_observation_button, self.later_observation_button):
            button.setEnabled(False)
            observation_actions.addWidget(button)
        observation_layout.addLayout(observation_actions)
        candidate_layout.addWidget(observation_group)

        # 數量與狀態分開，讓「有幾檔」不會被「已更新」覆蓋。
        candidate_status_layout = QHBoxLayout()
        self.stats_label = QLabel("共 0 檔股票")
        self.stats_label.setObjectName("watchlistStats")
        self.stats_label.setProperty("role", "summary")
        candidate_status_layout.addWidget(self.stats_label)

        self.status_label = QLabel("尚未載入")
        self.status_label.setObjectName("watchlistStatus")
        self.status_label.setProperty("role", "status")
        self.status_label.setWordWrap(True)
        candidate_status_layout.addWidget(self.status_label, stretch=1)
        self._set_status_label("尚未載入", level="info")
        candidate_layout.addLayout(candidate_status_layout)

        main_splitter.addWidget(candidate_panel)

        # ========== 右側：已保存選股清單 ==========
        # 右側只處理保存後的清單，不再混入候選池的新增／移除操作。
        universe_group = QGroupBox("已保存選股清單")
        universe_group.setObjectName("watchlistUniversePanel")
        universe_layout = QVBoxLayout(universe_group)
        universe_layout.setSpacing(8)
        universe_layout.setContentsMargins(12, 14, 12, 12)

        universe_hint = QLabel("選取清單查看股票；可載入回候選池或管理清單內容。")
        universe_hint.setProperty("role", "muted")
        universe_hint.setObjectName("watchlistUniverseHint")
        self.universe_hint = universe_hint
        universe_layout.addWidget(universe_hint)

        list_header_layout = QHBoxLayout()
        list_header = QLabel("已保存清單")
        list_header.setFont(work_title_font)
        list_header_layout.addWidget(list_header)
        list_header_layout.addStretch()
        self.refresh_universe_btn = QPushButton("刷新")
        self.refresh_universe_btn.setProperty("variant", "ghost")
        self.refresh_universe_btn.setMinimumHeight(30)
        self.refresh_universe_btn.setMaximumWidth(72)
        self.refresh_universe_btn.clicked.connect(self._refresh_universe_list)
        list_header_layout.addWidget(self.refresh_universe_btn)
        universe_layout.addLayout(list_header_layout)

        # 右側內部只分割「清單」與「預覽」，而不是再切一個候選池操作欄。
        management_splitter = QSplitter(Qt.Vertical)
        management_splitter.setObjectName("watchlistManagementSplitter")
        management_splitter.setChildrenCollapsible(False)
        self.management_splitter = management_splitter
        self.universe_splitter = management_splitter

        universe_list_section = QWidget()
        universe_list_section.setObjectName("watchlistUniverseListSection")
        universe_list_section_layout = QVBoxLayout(universe_list_section)
        universe_list_section_layout.setSpacing(6)
        universe_list_section_layout.setContentsMargins(0, 0, 0, 0)
        self.universe_list = QListWidget()
        self.universe_list.setObjectName("watchlistUniverseList")
        self.universe_list.setUniformItemSizes(True)
        self.universe_list.setFocusPolicy(Qt.StrongFocus)
        self.universe_list.setAccessibleName("已保存選股清單")
        self.universe_list.setAccessibleDescription(
            "可用方向鍵選取保存清單；下方預覽只讀取既有清單內容。"
        )
        self.universe_list.setMinimumHeight(100)
        self.universe_list.setWordWrap(True)
        self.universe_list.setUniformItemSizes(False)
        ensure_visible_rows(self.universe_list, 5)
        universe_list_section_layout.addWidget(self.universe_list)
        management_splitter.addWidget(universe_list_section)

        universe_preview_section = QWidget()
        universe_preview_section.setObjectName("watchlistUniversePreviewSection")
        universe_preview_section_layout = QVBoxLayout(universe_preview_section)
        universe_preview_section_layout.setSpacing(6)
        universe_preview_section_layout.setContentsMargins(0, 0, 0, 0)
        preview_label = QLabel("清單個股預覽（單擊看摘要，雙擊開啟主力流向）")
        preview_label.setProperty("role", "muted")
        preview_label.setWordWrap(True)
        universe_preview_section_layout.addWidget(preview_label)
        self.universe_stock_list = QListWidget()
        self.universe_stock_list.setObjectName("watchlistUniverseStockList")
        self.universe_stock_list.setUniformItemSizes(True)
        self.universe_stock_list.setFocusPolicy(Qt.StrongFocus)
        self.universe_stock_list.setAccessibleName("已保存清單個股預覽")
        self.universe_stock_list.setAccessibleDescription(
            "可用方向鍵選取個股；雙擊開啟與候選池共用的研究報告。"
        )
        self.universe_stock_list.setMinimumHeight(100)
        self.universe_stock_list.setWordWrap(True)
        self.universe_stock_list.setUniformItemSizes(False)
        ensure_visible_rows(self.universe_stock_list, 5)
        universe_preview_section_layout.addWidget(self.universe_stock_list)
        management_splitter.addWidget(universe_preview_section)
        management_splitter.setStretchFactor(0, 2)
        management_splitter.setStretchFactor(1, 3)
        management_splitter.setSizes([220, 300])
        universe_layout.addWidget(management_splitter, stretch=1)

        self.universe_list.itemSelectionChanged.connect(self._preview_universe_stocks)
        self.universe_stock_list.currentItemChanged.connect(self._select_universe_stock)
        self.universe_stock_list.itemDoubleClicked.connect(self._open_universe_stock_analysis)

        # 右側底部是同一組清單動作，閱讀順序固定為載入，再新增／編輯／刪除。
        universe_action_layout = QHBoxLayout()
        universe_action_layout.setSpacing(6)
        self.load_to_watchlist_btn = QPushButton("載入到候選池")
        self.load_to_watchlist_btn.setProperty("variant", "secondary")
        self.load_to_watchlist_btn.clicked.connect(self._load_universe_to_watchlist)
        universe_action_layout.addWidget(self.load_to_watchlist_btn)
        universe_action_layout.addStretch()

        self.create_universe_btn = QPushButton("新增")
        self.create_universe_btn.setProperty("variant", "secondary")
        self.create_universe_btn.clicked.connect(self._create_universe)
        universe_action_layout.addWidget(self.create_universe_btn)

        self.edit_universe_btn = QPushButton("編輯")
        self.edit_universe_btn.setProperty("variant", "secondary")
        self.edit_universe_btn.clicked.connect(self._edit_universe)
        universe_action_layout.addWidget(self.edit_universe_btn)

        self.delete_universe_btn = QPushButton("刪除")
        self.delete_universe_btn.setProperty("variant", "danger")
        self.delete_universe_btn.clicked.connect(self._delete_universe)
        universe_action_layout.addWidget(self.delete_universe_btn)
        universe_layout.addLayout(universe_action_layout)

        if self.universe_service:
            self._refresh_universe_list()
        else:
            unavailable_hint = QLabel("選股清單服務未初始化。")
            unavailable_hint.setProperty("role", "hint")
            universe_layout.addWidget(unavailable_hint)
            for control in (
                self.refresh_universe_btn,
                self.universe_list,
                self.universe_stock_list,
                self.load_to_watchlist_btn,
                self.create_universe_btn,
                self.edit_universe_btn,
                self.delete_universe_btn,
            ):
                control.setEnabled(False)

        main_splitter.addWidget(universe_group)

        # 左側是主工作區，右側是次要但持續可見的清單面板。
        main_splitter.setStretchFactor(0, 7)
        main_splitter.setStretchFactor(1, 3)
        main_splitter.setSizes([860, 400])

        main_layout.addWidget(main_splitter)
        self._apply_responsive_layout()

    def _apply_responsive_layout(self) -> None:
        """依可用寬度切換兩個主面板，保持候選池優先且清單可讀。"""

        if not hasattr(self, "main_splitter"):
            return

        main_is_narrow = self.width() < 980
        layout_mode = main_is_narrow
        self._watchlist_layout_mode = layout_mode

        if main_is_narrow:
            self.main_splitter.setOrientation(Qt.Vertical)
            height = max(self.height(), 720)
            self.main_splitter.setSizes(
                [max(400, int(height * 0.60)), max(280, int(height * 0.40))]
            )
            self.work_title.setVisible(False)
            self.candidate_hint.setVisible(False)
            self.universe_hint.setVisible(False)
            self.analysis_hint.setVisible(False)
        else:
            self.main_splitter.setOrientation(Qt.Horizontal)
            width = max(self.width(), 1200)
            self.main_splitter.setSizes(
                [max(720, int(width * 0.68)), max(360, int(width * 0.32))]
            )
            # 外層 QGroupBox 已提供唯一主標題，避免桌面版重複顯示「觀察候選池」。
            self.work_title.setVisible(False)
            self.candidate_hint.setVisible(True)
            self.universe_hint.setVisible(True)
            self.analysis_hint.setVisible(True)

        action_direction = (
            QBoxLayout.Direction.TopToBottom
            if main_is_narrow
            else QBoxLayout.Direction.LeftToRight
        )
        self.watchlist_ops_layout.setDirection(action_direction)
        self.research_actions_layout.setDirection(action_direction)
        self.batch_actions_layout.setDirection(action_direction)

        # 子元件的窄版尺寸先完成，再重設主分割比例，避免 Qt 依舊的 sizeHint
        # 把兩個面板強制平均分配而造成內部內容重疊。
        if main_is_narrow:
            height = max(self.main_splitter.height(), 640)
            self.main_splitter.setSizes(
                [max(400, int(height * 0.60)), max(280, int(height * 0.40))]
            )
        else:
            width = max(self.main_splitter.width(), 1200)
            self.main_splitter.setSizes(
                [max(720, int(width * 0.68)), max(360, int(width * 0.32))]
            )

        if hasattr(self, "management_splitter"):
            # 右側固定採上下分割：上方選清單，下方看股票預覽。
            self.management_splitter.setOrientation(Qt.Vertical)
            height = max(self.height(), 520)
            self.management_splitter.setSizes(
                [max(160, int(height * 0.38)), max(180, int(height * 0.62))]
            )

    def _toggle_advanced_research(self, expanded: bool) -> None:
        """顯示／隱藏已保存研究明細，不改變目前選取與來源 binding。"""

        self.analysis_group.setVisible(expanded)
        self.toggle_advanced_research_btn.setText(
            "隱藏進階研究" if expanded else "顯示進階研究"
        )

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().resizeEvent(event)
        self._apply_responsive_layout()

    @staticmethod
    def _empty_frame() -> pd.DataFrame:
        return pd.DataFrame(
            columns=[
                "證券代號",
                "證券名稱",
                "加入時間",
                "來源",
                "推薦來源",
                "每日研究收藏",
                "備註",
                "source",
                "research_bookmark",
            ]
        )

    def _set_status_label(self, text: str, *, level: str) -> None:
        tone = level if level in {"info", "success", "warning", "error"} else "info"
        self.status_label.setProperty("statusTone", tone)
        style = self.status_label.style()
        if style is not None:
            style.unpolish(self.status_label)
            style.polish(self.status_label)
        self.status_label.setText(text)

    def _set_watchlist_focus_summary(
        self,
        *,
        count: int | None = None,
        row: object | None = None,
        status: str = "",
        message: str = "",
    ) -> None:
        """更新候選池日常摘要；完整分析仍留在進階研究區。"""

        if row is None or not hasattr(row, "get"):
            total_text = "未知" if count is None else str(count)
            reasons = [
                "候選池只保存股票與來源脈絡，不代表已完成推薦判定。",
                "沒有選取列時，沒有單股證據可引用。",
            ]
            if message:
                reasons[0] = message
            self.watchlist_focus_summary.set_summary(
                conclusion=(
                    f"候選池目前 {total_text} 檔；尚未選取個股。"
                    if count is not None
                    else "候選池狀態尚未完成讀取。"
                ),
                reasons=reasons,
                next_step="選取一檔股票查看重點；需要完整理由時開啟進階研究。",
            )
            return

        code = str(row.get("證券代號", "") or "").strip()
        name = str(row.get("證券名稱", "") or "").strip()
        identity = self._row_decision_identity(row, code)
        source_status = self._source_link_label(row)
        result_status = status or "尚未讀取保存分析"
        message_text = str(message or "").strip()
        clean_message = message_text.splitlines()[0].strip() if message_text else ""
        result_reason = f"保存分析：{result_status}"
        if clean_message:
            result_reason += f"；{clean_message}"
        reasons = [f"推薦來源：{source_status}", result_reason]
        failed = result_status in {"讀取失敗", "不可用", "資料缺漏"} or "失敗" in result_status
        self.watchlist_focus_summary.set_summary(
            conclusion=f"已選取 {code} {name}；目前只做研究整理。",
            reasons=reasons,
            next_step=(
                "先核對原推薦來源，再開啟完整個股研究報告。"
                if not identity.is_linked and not failed
                else (
                    "先再試一次；仍失敗時開啟進階研究查看詳細原因。"
                    if failed
                    else "開啟完整個股研究報告，確認資料日與主要風險。"
                )
            ),
        )

    def _refresh_storage_status(self) -> None:
        """呈現目前 writer；不在 UI 啟動時建立或遷移資料庫。"""

        getter = getattr(self.watchlist_service, "get_storage_status", None)
        if not callable(getter):
            self.storage_status_label.setText("觀察清單儲存狀態：沿用既有服務。")
            self.upgrade_storage_btn.setVisible(False)
            return
        try:
            status = getter()
        except Exception as exc:
            self.storage_status_label.setText(
                f"觀察清單儲存狀態讀取失敗：{str(exc).splitlines()[0]}"
            )
            self.upgrade_storage_btn.setVisible(False)
            return
        if not isinstance(status, WatchlistStorageStatus):
            # 與舊版測試替身／host 相容，不把未知物件誤判成已升級。
            self.storage_status_label.setText("觀察清單儲存狀態：沿用既有服務。")
            self.upgrade_storage_btn.setVisible(False)
            return
        self.storage_status_label.setText(
            f"觀察清單儲存狀態：{status.message}"
        )
        self.upgrade_storage_btn.setVisible(
            status.upgrade_available and not status.is_repository
        )
        if callable(getattr(self.watchlist_service, "personal_storage_preview", None)):
            self.upgrade_storage_btn.setText("建立並啟用個人副本")
        self.upgrade_storage_btn.setEnabled(
            status.upgrade_available and not status.is_repository
        )

    def _refresh_technical_bookmark_controls(self) -> None:
        """只在服務明確提供 typed reopen API 時刷新完整母體收藏。"""

        service_type = type(self.watchlist_service)
        supports_typed_reopen = callable(
            getattr(service_type, "get_technical_universe_research_bookmark_state", None)
        )
        if supports_typed_reopen:
            self.technical_bookmark_controls.refresh_bookmarks()
        h20_controls = self.personal_h20_bookmark_controls
        if h20_controls is not None:
            h20_controls.refresh_bookmarks()

    def configure_personal_h20_bookmarks(
        self, *, config_path: Path, market_root: Path, bookmark_state_reader,
    ) -> None:
        """以明示個人設定及原版本 session reader 掛入 H20 收藏。"""
        from ui_qt.widgets.personal_h20_bookmark_controls import PersonalH20BookmarkControls

        if self.personal_h20_bookmark_controls is not None:
            raise ValueError("personal_h20_bookmark_controls_already_configured")
        controls = PersonalH20BookmarkControls(
            self.watchlist_service, config_path=config_path, market_root=market_root,
            bookmark_state_reader=bookmark_state_reader, parent=self.personal_h20_bookmark_group,
        )
        controls.stateReady.connect(self.personalH20BookmarkStateReady.emit)
        self.personal_h20_bookmark_controls = controls
        self._personal_h20_bookmark_hint.hide()
        self._personal_h20_bookmark_layout.addWidget(controls)
        controls.refresh_bookmarks()

    def _upgrade_watchlist_storage(self) -> None:
        """明示升級；個人模式先預覽路徑且失敗時禁止來源寫入。"""

        upgrade = getattr(self.watchlist_service, "upgrade_to_repository", None)
        if not callable(upgrade):
            self._set_status_label("目前服務不支援儲存升級。", level="warning")
            return
        self.upgrade_storage_btn.setEnabled(False)
        try:
            preview = getattr(self.watchlist_service, "personal_storage_preview", None)
            if callable(preview):
                paths = preview()
                labels = (
                    ("source", "唯讀來源"), ("target", "個人資料庫"),
                    ("marker", "啟用標記"), ("receipt", "轉換收據"),
                    ("backup", "來源備份"), ("rollback_audit_root", "回滾紀錄"),
                )
                details = "\n".join(f"{label}：{paths.get(key, '未提供')}" for key, label in labels)
                answer = QMessageBox.question(
                    self, "啟用個人觀察清單", details +
                    "\n\n保留原來源，之後只寫入個人副本。回滾會停止寫入並保留個人歷史。",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if answer != QMessageBox.StandardButton.Yes:
                    self._refresh_storage_status()
                    return
            status = upgrade()
        except Exception as exc:
            self._refresh_storage_status()
            self._set_status_label(
                ("個人儲存啟用失敗，未切回原來源寫入："
                 if callable(getattr(self.watchlist_service, "personal_storage_preview", None))
                 else "儲存升級失敗，仍使用原 JSON：") + str(exc).splitlines()[0],
                level="error",
            )
            return
        self._refresh_storage_status()
        if isinstance(status, WatchlistStorageStatus) and status.is_repository:
            self._set_status_label(
                "個人儲存已啟用，後續保存使用個人 SQLite；原來源唯讀保留。"
                if callable(getattr(self.watchlist_service, "personal_storage_preview", None))
                else "儲存升級成功，後續保存使用 SQLite 觀察清單；原 JSON 保留。",
                level="success",
            )
            QMessageBox.information(self, "觀察清單儲存升級", status.message)
            self._load_watchlist()
            return
        message = (
            status.message
            if isinstance(status, WatchlistStorageStatus)
            else (
                "個人儲存未啟用；來源寫入已封鎖。"
                if callable(getattr(self.watchlist_service, "personal_storage_preview", None))
                else "升級未完成；目前仍使用原 JSON。"
            )
        )
        self._set_status_label(message, level="warning")
        QMessageBox.warning(self, "觀察清單儲存升級未完成", message)

    def _load_watchlist(self):
        self._render_observation(None)
        """載入觀察清單"""
        self._analysis_request_id += 1
        self.stock_analysis_btn.setEnabled(False)
        self._set_source_choice_state(None)
        self._set_watchlist_focus_summary(message="載入中")
        self.analysis_text.clear()
        self.analysis_context_label.setText(
            "狀態：載入中｜決策日：未知｜資料日：未知｜來源：讀取候選池"
        )
        logger.info("[WatchlistView._load_watchlist] 開始載入...")
        self._set_status_label("載入中…", level="info")
        try:
            logger.info("[WatchlistView._load_watchlist] 調用 watchlist_service.get_stocks()...")
            stocks = self.watchlist_service.get_stocks()
            logger.info(f"[WatchlistView._load_watchlist] 獲取到 {len(stocks) if stocks else 0} 檔股票")
            
            if not stocks:
                # 顯示空表格
                logger.info("[WatchlistView._load_watchlist] 候選池為空，顯示空表格")
                df = self._empty_frame()
            else:
                # 轉換為 DataFrame
                logger.info("[WatchlistView._load_watchlist] 轉換為 DataFrame...")
                df = pd.DataFrame(stocks)
                df = df.rename(columns={
                    'stock_code': '證券代號',
                    'stock_name': '證券名稱',
                    'added_at': '加入時間',
                    'notes': '備註'
                })
                if "source" not in df.columns:
                    df["source"] = ""
                df["來源"] = [
                    (
                        "完整母體技術研究收藏"
                        if str(value or "").strip()
                        == DAILY_MARKET_TECHNICAL_UNIVERSE_V4_BOOKMARK_SOURCE
                        else (
                            "每日研究收藏"
                            if str(value or "").strip()
                            == DAILY_MARKET_RESEARCH_BOOKMARK_SOURCE
                            else str(value or "未標示")
                        )
                    )
                    for value in df["source"]
                ]
                if "research_bookmark" not in df.columns:
                    df["research_bookmark"] = None
                df["每日研究收藏"] = [
                    self._research_bookmark_row_label(row)
                    for _, row in df.iterrows()
                ]
                # 格式化時間
                if '加入時間' in df.columns:
                    df['加入時間'] = pd.to_datetime(df['加入時間'], errors='coerce').dt.strftime('%Y-%m-%d %H:%M')
                df['推薦來源'] = [
                    self._source_link_label(row)
                    for _, row in df.iterrows()
                ]
                logger.info("[WatchlistView._load_watchlist] DataFrame 轉換完成")
            
            # 更新模型
            logger.info("[WatchlistView._load_watchlist] 創建 PandasTableModel...")
            logger.info(f"[WatchlistView._load_watchlist] DataFrame 形狀: {df.shape}")
            logger.info(f"[WatchlistView._load_watchlist] DataFrame 欄位: {list(df.columns)}")
            
            try:
                self.stocks_model = PandasTableModel(df)
                # 保留完整來源資料供下鑽；候選表只顯示可讀欄位，避免洩出原始識別字典。
                self.stocks_model.setVisibleColumns(
                    [
                        column
                        for column in self._empty_frame().columns
                        if column not in {"source", "research_bookmark"}
                    ]
                )
                logger.info("[WatchlistView._load_watchlist] PandasTableModel 創建成功")
            except Exception as e:
                logger.error(f"[WatchlistView._load_watchlist] 創建 PandasTableModel 失敗: {e}")
                import traceback
                logger.error(traceback.format_exc())
                raise
            
            logger.info("[WatchlistView._load_watchlist] 設置表格模型...")
            try:
                self.stocks_table.setModel(self.stocks_model)
                self._analysis_request_id += 1
                self.analysis_text.clear()
                self.stocks_table.selectionModel().selectionChanged.connect(self._load_selected_analysis)
                logger.info("[WatchlistView._load_watchlist] 表格模型設置成功")
            except Exception as e:
                logger.error(f"[WatchlistView._load_watchlist] 設置表格模型失敗: {e}")
                import traceback
                logger.error(traceback.format_exc())
                raise
            
            # 調整列寬
            logger.info("[WatchlistView._load_watchlist] 調整列寬...")
            try:
                self.stocks_table.resizeColumnsToContents()
                logger.info("[WatchlistView._load_watchlist] 列寬調整完成")
            except Exception as e:
                logger.error(f"[WatchlistView._load_watchlist] 調整列寬失敗: {e}")
                # 不拋出異常，繼續執行
            
            # 更新統計
            if stocks:
                self.stats_label.setText(f"共 {len(stocks)} 檔股票")
                self._set_status_label(f"已更新：{len(stocks)} 筆", level="success")
            else:
                self.stats_label.setText("共 0 檔股票（目前沒有候選）")
                self._set_status_label("已更新：0 筆；目前沒有候選", level="warning")
            self._set_watchlist_focus_summary(count=len(stocks) if stocks else 0)
            self._update_research_lab_button_state(len(stocks))
            self._refresh_storage_status()
            self._refresh_technical_bookmark_controls()
            logger.info("[WatchlistView._load_watchlist] 載入完成")
            
        except Exception as e:
            import traceback
            logger.error(f"[WatchlistView._load_watchlist] 錯誤：載入觀察清單失敗")
            logger.error(f"[WatchlistView._load_watchlist] 錯誤類型: {type(e).__name__}")
            logger.error(f"[WatchlistView._load_watchlist] 錯誤訊息: {str(e)}")
            logger.error(f"[WatchlistView._load_watchlist] 詳細堆疊追蹤:\n{traceback.format_exc()}")
            
            error_msg = f"載入觀察清單失敗：\n{str(e)}\n\n{traceback.format_exc()}"
            try:
                QMessageBox.critical(self, "錯誤", error_msg)
            except:
                logger.error("[WatchlistView._load_watchlist] 無法顯示錯誤對話框")
            
            # 顯示空表格，避免界面崩潰
            try:
                self.stocks_model = PandasTableModel(self._empty_frame())
                self.stocks_table.setModel(self.stocks_model)
                self.stats_label.setText("共 0 檔股票（載入失敗）")
                self._set_status_label(
                    f"載入失敗：{str(e).splitlines()[0] or type(e).__name__}",
                    level="error",
                )
                self._set_watchlist_focus_summary(
                    count=None,
                    message=f"載入失敗：{str(e).splitlines()[0] or type(e).__name__}",
                )
                self._update_research_lab_button_state(0)
                self._refresh_storage_status()
                self._refresh_technical_bookmark_controls()
                logger.error("[WatchlistView._load_watchlist] 已顯示錯誤提示")
            except Exception as e2:
                logger.error(f"[WatchlistView._load_watchlist] 顯示錯誤提示時也失敗: {e2}")

    def _update_research_lab_button_state(self, stock_count: int) -> None:
        """依候選池內容啟用或停用 Research Lab 批次回測入口。"""
        enabled = stock_count > 0
        self.send_to_research_lab_btn.setEnabled(enabled)
        if enabled:
            self.send_to_research_lab_btn.setToolTip("將目前候選池送到策略回測的批次模式。")
        else:
            self.send_to_research_lab_btn.setToolTip("候選池目前沒有股票，加入股票後即可送 Research Lab 批次回測。")

    def _send_to_research_lab(self) -> None:
        """將目前觀察清單送到策略回測的批次模式。"""
        stock_codes = [str(code).strip() for code in self.watchlist_service.get_stock_codes() if str(code).strip()]
        if not stock_codes:
            QMessageBox.warning(self, "提示", "候選池目前沒有股票，無法送 Research Lab 批次回測。")
            self._update_research_lab_button_state(0)
            return

        config = {
            "stock_list": stock_codes,
            "profile_id": "watchlist",
            "profile_name": "觀察清單",
            "strategy_config": {},
            "regime": None,
            "regime_snapshot": None,
            "source": "watchlist",
        }
        self.sendToBacktestRequested.emit(config)
        QMessageBox.information(
            self,
            "已送出",
            f"已將 {len(stock_codes)} 檔候選池股票送到 Research Lab 批次回測。\n\n"
            "請切換到「策略回測 / Research Lab」確認期間、策略與資金設定後執行。",
        )
    
    def _show_add_dialog(self):
        """顯示新增股票對話框"""
        dialog = QDialog(self)
        dialog.setWindowTitle("新增股票到候選池")
        dialog.setMinimumWidth(400)
        
        layout = QVBoxLayout(dialog)
        
        # 股票代號輸入
        code_layout = QHBoxLayout()
        code_layout.addWidget(QLabel("股票代號:"))
        code_input = QLineEdit()
        code_input.setPlaceholderText("例如：2330")
        code_layout.addWidget(code_input)
        layout.addLayout(code_layout)
        
        # 股票名稱輸入（可選）
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("股票名稱:"))
        name_input = QLineEdit()
        name_input.setPlaceholderText("可選，留空將自動查詢")
        name_layout.addWidget(name_input)
        layout.addLayout(name_layout)
        
        # 備註
        notes_layout = QVBoxLayout()
        notes_layout.addWidget(QLabel("備註:"))
        notes_input = QTextEdit()
        notes_input.setMaximumHeight(80)
        notes_layout.addWidget(notes_input)
        layout.addLayout(notes_layout)
        
        # 按鈕
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        
        if dialog.exec() == QDialog.Accepted:
            stock_code = code_input.text().strip()
            stock_name = name_input.text().strip()
            
            if not stock_code:
                QMessageBox.warning(self, "錯誤", "請輸入股票代號")
                return

            resolved = self._resolve_manual_stock(stock_code, stock_name)
            if resolved is None:
                QMessageBox.warning(
                    self,
                    "股票代號不存在",
                    f"找不到股票代號 {stock_code} 的正式資料，請確認代號是否正確。\n\n"
                    "目前手動新增只允許加入資料源中存在的股票，避免自訂代號混入正式候選池。",
                )
                return
            stock_code, stock_name = resolved
            
            # 新增股票
            try:
                added_count = self.watchlist_service.add_stocks(
                    stocks=[{
                        'stock_code': stock_code,
                        'stock_name': stock_name,
                        'notes': notes_input.toPlainText().strip()
                    }],
                    source='manual'
                )
                
                if added_count > 0:
                    QMessageBox.information(self, "成功", f"已新增 {added_count} 檔股票到候選池")
                    self._load_watchlist()
                    self.watchlistUpdated.emit()
                else:
                    QMessageBox.warning(self, "提示", "該股票已在候選池中")
            except Exception as e:
                QMessageBox.critical(self, "錯誤", f"新增股票失敗：\n{str(e)}")

    def _resolve_manual_stock(self, stock_code: str, stock_name: str) -> Optional[tuple[str, str]]:
        """驗證手動輸入股票代號，並在名稱空白時自動補正式名稱。"""
        code = str(stock_code).strip()
        name = str(stock_name).strip()
        if not code:
            return None

        name_map = self._query_stock_names([code])
        resolved_name = name_map.get(code)
        if not resolved_name:
            return None
        return code, name or resolved_name
    
    def _remove_selected(self):
        """移除選中的股票"""
        selection = self.stocks_table.selectionModel().selectedRows()
        if not selection or not self.stocks_model:
            QMessageBox.warning(self, "提示", "請先選擇要移除的股票")
            return

        frame = self.stocks_model.getDataFrame()
        bookmark_ids: list[str] = []
        legacy_rows: list[tuple[str, str, str]] = []
        bookmarked_codes = {
            str(row.get("證券代號", "") or "").strip()
            for _, row in frame.iterrows()
            if self._row_declares_research_bookmark(row)
        }
        for index in selection:
            if index.row() < 0 or index.row() >= len(frame):
                continue
            row = frame.iloc[index.row()]
            raw_bookmark = row.get("research_bookmark")
            if self._row_declares_research_bookmark(row):
                if not isinstance(raw_bookmark, Mapping):
                    self._set_status_label(
                        "選取列含無法解析的每日研究書籤；拒絕以股票代碼移除整列。",
                        level="error",
                    )
                    return
                bookmark_id = self._exact_research_bookmark_id_for_row(row)
                if not bookmark_id:
                    self._set_status_label(
                        "選取列的研究書籤身份或來源列不一致；拒絕以股票代碼移除整列。",
                        level="error",
                    )
                    return
                bookmark_ids.append(bookmark_id)
            else:
                stock_code = str(row.get("證券代號", "") or "").strip()
                if stock_code:
                    source_id_value = row.get("source_id", "")
                    source_id = (
                        source_id_value.strip()
                        if isinstance(source_id_value, str)
                        else ""
                    )
                    source_value = row.get("source", row.get("來源", ""))
                    expected_source = (
                        source_value.strip()
                        if isinstance(source_value, str)
                        else ""
                    )
                    legacy_rows.append((stock_code, source_id, expected_source))

        if bookmark_ids and not callable(
            getattr(self.watchlist_service, "remove_research_bookmark", None)
        ):
            self._set_status_label(
                "觀察清單服務不支援精確移除研究書籤；未移除任何列。",
                level="error",
            )
            return
        precise_item_remover = getattr(
            self.watchlist_service, "remove_watchlist_item", None
        )
        if any(code in bookmarked_codes for code, _, _ in legacy_rows) and not callable(
            precise_item_remover
        ):
            self._set_status_label(
                "同股另有每日研究書籤，且服務無法精確定位一般觀察列；未刪除任何項目。",
                level="error",
            )
            return

        reply = QMessageBox.question(
            self,
            "確認移除",
            f"確定要移除選取的 {len(bookmark_ids)} 個精確研究書籤與 "
            f"{len(legacy_rows)} 筆一般觀察列嗎？\n"
            "研究書籤會按 bookmark ID 精確移除，不會按股票代碼刪除同股其他來源。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            removed_items = 0
            remove_bookmark = getattr(
                self.watchlist_service, "remove_research_bookmark", None
            )
            for bookmark_id in bookmark_ids:
                result = remove_bookmark(bookmark_id)
                status = str(getattr(result, "status", "") or "")
                if status in {"removed", "deleted", "success", "ok"} or bool(
                    getattr(result, "removed", False)
                ):
                    removed_items += 1
                    restore_token = getattr(result, "restore_token", None)
                    if restore_token is not None:
                        self._research_bookmark_restore_tokens.append(restore_token)
            generic_codes: list[str] = []
            for stock_code, source_id, expected_source in legacy_rows:
                if stock_code not in bookmarked_codes:
                    generic_codes.append(stock_code)
                    continue
                result = precise_item_remover(
                    stock_code,
                    source_id,
                    expected_source,
                )
                if str(getattr(result, "status", "") or "") == "removed":
                    removed_items += 1
            if generic_codes:
                removed_items += int(self.watchlist_service.remove_stocks(generic_codes))
            self.restore_research_bookmark_btn.setEnabled(
                bool(self._research_bookmark_restore_tokens)
            )
            self.restore_research_bookmark_btn.setVisible(
                bool(self._research_bookmark_restore_tokens)
            )
            if removed_items > 0:
                QMessageBox.information(self, "成功", f"已精確移除 {removed_items} 個項目")
                self._load_watchlist()
                self.watchlistUpdated.emit()
            else:
                self._set_status_label("沒有項目符合精確移除條件。", level="warning")
        except Exception as e:
            QMessageBox.critical(self, "錯誤", f"移除股票失敗：\n{str(e)}")

    def _restore_last_research_bookmark(self) -> bool:
        if not self._research_bookmark_restore_tokens:
            return False
        restore = getattr(self.watchlist_service, "restore_research_bookmark", None)
        if not callable(restore):
            self._set_status_label("觀察清單服務不支援還原研究書籤。", level="error")
            return False
        token = self._research_bookmark_restore_tokens[-1]
        try:
            result = restore(token)
        except Exception as error:
            self._set_status_label(f"研究書籤還原失敗：{error}", level="error")
            return False
        status = str(getattr(result, "status", "") or "")
        if not (
            status in {"restored", "already_present", "added", "success", "ok"}
            or bool(getattr(result, "restored", False))
        ):
            self._set_status_label(
                str(getattr(result, "message", "研究書籤未能還原。")),
                level="warning",
            )
            return False
        self._research_bookmark_restore_tokens.pop()
        available = bool(self._research_bookmark_restore_tokens)
        self.restore_research_bookmark_btn.setEnabled(available)
        self.restore_research_bookmark_btn.setVisible(available)
        self._load_watchlist()
        self.watchlistUpdated.emit()
        self._set_status_label("已還原剛移除的精確研究書籤。", level="success")
        return True
    
    def _clear_watchlist(self):
        """清空觀察清單"""
        rows: list[Mapping[str, object]] | None = None
        get_stocks = getattr(self.watchlist_service, "get_stocks", None)
        if callable(get_stocks):
            try:
                raw_rows = list(get_stocks())
                if any(not isinstance(row, Mapping) for row in raw_rows):
                    raise TypeError("觀察清單列格式無效")
                rows = [row for row in raw_rows if isinstance(row, Mapping)]
            except Exception as error:
                QMessageBox.critical(self, "錯誤", f"清空清單前無法核對來源列：\n{error}")
                return

        has_full_n_bookmark = bool(
            rows is not None
            and any(self._row_is_technical_universe_bookmark(row) for row in rows)
        )
        bookmark_ids: list[str] = []
        ordinary_rows: list[tuple[str, str, str]] = []
        if has_full_n_bookmark and rows is not None:
            for row in rows:
                if self._row_declares_research_bookmark(row):
                    bookmark_id = self._exact_research_bookmark_id_for_row(row)
                    if not bookmark_id:
                        self._set_status_label(
                            "候選池含無法核對的研究書籤；拒絕清空，避免按股票代碼刪除完整母體收藏。",
                            level="error",
                        )
                        return
                    if bookmark_id not in bookmark_ids:
                        bookmark_ids.append(bookmark_id)
                    continue
                stock_code = str(
                    row.get("stock_code", row.get("證券代號", "")) or ""
                ).strip()
                if not stock_code:
                    self._set_status_label(
                        "候選池含缺少股票代碼的一般列；拒絕清空完整母體收藏。",
                        level="error",
                    )
                    return
                source_value = row.get("source", row.get("來源", ""))
                source = source_value.strip() if isinstance(source_value, str) else ""
                source_id_value = row.get("source_id", "")
                source_id = (
                    source_id_value.strip()
                    if isinstance(source_id_value, str)
                    else ""
                )
                ordinary_rows.append((stock_code, source_id, source))

            if bookmark_ids and not callable(
                getattr(self.watchlist_service, "remove_research_bookmark", None)
            ):
                self._set_status_label(
                    "觀察清單服務不支援依精確身份移除研究收藏；未清空候選池。",
                    level="error",
                )
                return
            if ordinary_rows and not callable(
                getattr(self.watchlist_service, "remove_watchlist_item", None)
            ):
                self._set_status_label(
                    "觀察清單服務無法精確定位一般列；未清空完整母體收藏。",
                    level="error",
                )
                return

        reply = QMessageBox.question(
            self, "確認", 
            (
                "確定要清空整個候選池嗎？完整母體收藏會按 payload identity 精確移除，"
                "一般列也會逐列核對，不會按股票代碼刪除完整母體收藏。"
                if has_full_n_bookmark
                else "確定要清空整個候選池嗎？每日研究書籤也會一併移除；此操作無法復原。"
            ),
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply != QMessageBox.Yes:
            return

        if has_full_n_bookmark:
            try:
                remove_bookmark = getattr(
                    self.watchlist_service, "remove_research_bookmark"
                )
                remove_item = getattr(self.watchlist_service, "remove_watchlist_item")
                removed_items = 0
                for bookmark_id in bookmark_ids:
                    result = remove_bookmark(bookmark_id)
                    status = str(getattr(result, "status", "") or "")
                    if status not in {"removed", "deleted", "success", "ok"} and not bool(
                        getattr(result, "removed", False)
                    ):
                        raise RuntimeError(
                            f"精確移除研究收藏失敗：{bookmark_id}（{status or 'unknown'}）"
                        )
                    removed_items += 1
                for stock_code, source_id, source in ordinary_rows:
                    result = remove_item(stock_code, source_id, source)
                    if str(getattr(result, "status", "") or "") != "removed":
                        raise RuntimeError(
                            f"一般列身份已變動或無法精確移除：{stock_code}"
                        )
                    removed_items += 1
                restore_available = bool(self._research_bookmark_restore_tokens)
                self.restore_research_bookmark_btn.setEnabled(restore_available)
                self.restore_research_bookmark_btn.setVisible(restore_available)
                QMessageBox.information(self, "成功", f"已清空候選池，共精確移除 {removed_items} 個項目")
                self._load_watchlist()
                self.watchlistUpdated.emit()
            except Exception as error:
                self._load_watchlist()
                QMessageBox.critical(self, "錯誤", f"清空清單未能完整完成：\n{error}")
            return
        
        try:
            # 取得所有股票代號
            stock_codes = self.watchlist_service.get_stock_codes()
            if stock_codes:
                self.watchlist_service.remove_stocks(stock_codes)
                QMessageBox.information(self, "成功", "已清空候選池")
                self._load_watchlist()
                self.watchlistUpdated.emit()
        except Exception as e:
            QMessageBox.critical(self, "錯誤", f"清空清單失敗：\n{str(e)}")
    
    def _load_selected_analysis(self, *_args):
        self._analysis_request_id += 1
        request_id = self._analysis_request_id
        selection = self.stocks_table.selectionModel()
        rows = selection.selectedRows() if selection else []
        if self.stocks_model is None or len(rows) != 1:
            self._render_observation(None)
            self.stock_analysis_btn.setEnabled(False)
            self.latest_research_btn.setEnabled(False)
            self._set_source_choice_state(None)
            self._set_watchlist_focus_summary(
                count=self.stocks_model.rowCount() if self.stocks_model is not None else 0,
            )
            self.analysis_context_label.setText(
                "狀態：尚未選取｜決策日：未知｜資料日：未知｜來源：未知"
            )
            self.analysis_text.setPlainText("請選取一檔股票查看分析摘要。")
            return
        row = self.stocks_model.getDataFrame().iloc[rows[0].row()]
        self._render_observation(row)
        code = str(row["證券代號"]).strip()
        if self._row_is_technical_universe_bookmark(row):
            self.stock_analysis_btn.setEnabled(False)
            self.latest_research_btn.setEnabled(False)
            self._set_source_choice_state(row)
            self.analysis_context_label.setText(
                "狀態：完整母體收藏｜決策日：未知｜資料日：未知｜來源：固定保存 pins"
            )
            self.analysis_text.setPlainText(
                "完整母體五規則結果由下方收藏控制項沿原 query 與 receipt typed reopen；"
                "不讀取 legacy 個股分析或最新來源。"
            )
            self._set_watchlist_focus_summary(
                row=row,
                status="完整母體收藏",
                message="請使用下方收藏控制項重開固定來源。",
            )
            return
        source = row.get("source_id", "")
        legacy_source_id = source.strip() if isinstance(source, str) else ""
        identity = self._row_decision_identity(row, code)
        # typed candidate 的 exact result_id 才是保存結果讀取鍵；source_id
        # 可能只是 provider lineage，不能讓同股不同 result 共用同一個摘要。
        source_id = identity.result_id if identity.is_linked else legacy_source_id
        self.stock_analysis_btn.setEnabled(True)
        self.latest_research_btn.setEnabled(True)
        self._set_source_choice_state(row)
        self._set_watchlist_focus_summary(row=row)
        research_bookmark = row.get("research_bookmark")
        if self._row_declares_research_bookmark(row):
            context = self._context_from_row_bookmark(row, code)
            self.analysis_context_label.setText(
                self._bookmark_context_summary(research_bookmark, context)
            )
            self.analysis_text.setPlainText(
                self._research_bookmark_detail(research_bookmark, context)
            )
            return
        self._request_stock_summary(code, source_id, request_id)

    @staticmethod
    def _observation_identity(row) -> str:
        """本次視窗狀態固定於完整來源列；同股不同版本不得共用。"""
        fields = (
            "證券代號", "加入時間", "source", "source_id", "result_id",
            "decision_date", "source_snapshot_id", "source_snapshot_hash",
            "decision_identity", "research_bookmark", "備註",
        )
        return json.dumps({key: row.get(key, None) for key in fields}, sort_keys=True, ensure_ascii=False, default=str)

    def _render_observation(self, row) -> None:
        self._observation_review = None
        for button in (self.edit_observation_reason_button, self.confirm_observation_button, self.later_observation_button):
            button.setEnabled(False)
        self.observation_change_label.setText("較前變化：未知；沒有同源比較資料，不借最新行情。")
        if row is None:
            self.observation_reason_label.setText("收藏理由：尚未選取")
            state = "尚未選取"
        else:
            notes = row.get("備註", "")
            reason = notes.strip() if isinstance(notes, str) else ""
            if not reason:
                reason = "未提供；可查看原保存推薦理由或研究條件，不代作個人收藏理由。"
            self.observation_reason_label.setText(f"收藏理由：{reason}")
            state = "待核對；目前不可保存"
            pins = row.get("review_source_identity")
            getter = getattr(self.watchlist_service, "get_review_state", None)
            if type(pins) is WatchlistReviewSourceIdentity and callable(getter):
                try:
                    review = getter(str(row.get("證券代號", "")), pins)
                    if type(review) is not WatchlistReviewState or review.source_identity != pins:
                        raise ValueError("私人查看狀態來源身份不一致")
                    self._observation_review = review
                    self.observation_reason_label.setText(f"收藏理由：{review.reason or '未提供'}")
                    state = {"pending": "待查看", "confirmed": "已確認查看", "deferred": "稍後查看"}[review.state]
                    state += "（已啟用私人保存）" if review.writable else "（唯讀；未啟用私人保存）"
                    for button in (self.edit_observation_reason_button, self.confirm_observation_button, self.later_observation_button):
                        button.setEnabled(review.writable and review.revision is not None)
                    comparer = getattr(self.watchlist_service, "get_same_source_change", None)
                    if review.revision is not None and review.revision > 1 and callable(comparer):
                        change = comparer(pins.stock_code, pins, before_revision=review.revision - 1,
                                          after_revision=review.revision)
                        self.observation_change_label.setText(f"較前保存變化：{change.message}")
                except Exception as exc:
                    self._observation_review = None
                    for button in (self.edit_observation_reason_button, self.confirm_observation_button, self.later_observation_button):
                        button.setEnabled(False)
                    state = f"來源／查看狀態不可核對：{str(exc).splitlines()[0]}"
        self.observation_state_label.setText(f"查看狀態：{state}；不排程提醒、不改研究證據。")

    def _edit_observation_reason(self) -> None:
        review = self._observation_review
        if review is None or not review.writable:
            return
        generation = self._analysis_request_id
        reason, accepted = QInputDialog.getText(self, "編輯收藏理由", "只保存私人收藏理由，不改原研究證據：", text=review.reason)
        if not accepted:
            self._set_status_label("已取消理由編輯；未保存。", level="info")
            return
        if generation != self._analysis_request_id or self._observation_review != review:
            self._set_status_label("選取來源已變動；未保存，請重新選取。", level="warning")
            return
        self._save_observation_review(reason, review.state, review)

    def _set_observation_state(self, state: str) -> None:
        if state not in {"confirmed", "deferred"}:
            return
        review = self._observation_review
        if review is None or not review.writable:
            return
        self._save_observation_review(review.reason, state, review)

    def _save_observation_review(self, reason, state, review: WatchlistReviewState) -> None:
        selected = self._selected_watchlist_row()
        if selected is None:
            return
        row, code = selected
        if row.get("review_source_identity") != review.source_identity or review.revision is None:
            self._set_status_label("來源身份已變動；未保存。", level="warning")
            return
        try:
            saved = self.watchlist_service.save_review_state(
                code, reason=reason, state=state, expected_revision=review.revision,
                sourcepins=review.source_identity,
            )
            if type(saved) is not WatchlistReviewState or saved.source_identity != review.source_identity:
                raise ValueError("保存回應身份不一致")
            # 原來源／bookmark 不變；同步重讀後精確定位本列，不選同股其他版本。
            self._load_watchlist()
            frame = self.stocks_model.getDataFrame() if self.stocks_model is not None else None
            if frame is not None:
                for index, candidate in frame.iterrows():
                    if candidate.get("review_source_identity") == review.source_identity:
                        self.stocks_table.selectRow(int(index))
                        break
            if self._observation_review != saved:
                raise ValueError("已保存，但目前讀回未能核對同一 revision／理由／狀態")
            self._set_status_label("已保存並重讀私人理由／查看狀態；原研究證據未變更。", level="success")
        except Exception as exc:
            self._set_status_label(f"私人查看狀態保存／核對失敗：{str(exc).splitlines()[0]}；請重讀來源。", level="warning")

    @staticmethod
    def _row_decision_identity(row: object, stock_code: str) -> DecisionIdentity:
        """從 model row 讀 typed identity；legacy row 明確維持 unknown。"""

        raw = row.get("decision_identity", {}) if hasattr(row, "get") else {}
        if isinstance(raw, DecisionIdentity):
            try:
                return DecisionIdentity.from_mapping(raw, default_stock_code=stock_code)
            except (TypeError, ValueError):
                return DecisionIdentity(
                    stock_code=stock_code,
                    identity_status=IDENTITY_STATUS_CONFLICT,
                )
        if isinstance(raw, Mapping):
            try:
                return DecisionIdentity.from_mapping(raw, default_stock_code=stock_code)
            except (TypeError, ValueError):
                return DecisionIdentity(
                    stock_code=stock_code,
                    identity_status=IDENTITY_STATUS_CONFLICT,
                )
        return DecisionIdentity(stock_code=stock_code, identity_status=IDENTITY_STATUS_UNKNOWN)

    def _source_link_label(self, row: object) -> str:
        """來源連結只代表可追溯，不表示該股已入選或結果已通過驗證。"""
        code = str(row.get("證券代號", "") or "") if hasattr(row, "get") else ""
        identity = self._row_decision_identity(row, code)
        if identity.identity_status == IDENTITY_STATUS_CONFLICT:
            return "來源不一致，需核對"
        if identity.is_linked:
            return "已連結原推薦"
        return "未連結原推薦"

    @staticmethod
    def _has_research_bookmark(value: object) -> bool:
        if value is None:
            return False
        if isinstance(value, str):
            return bool(value.strip())
        if isinstance(value, Mapping):
            return True
        if isinstance(value, float):
            return not pd.isna(value)
        return True

    @staticmethod
    def _is_technical_universe_bookmark_payload(value: object) -> bool:
        return (
            isinstance(value, Mapping)
            and value.get("schema_version")
            == DAILY_MARKET_TECHNICAL_UNIVERSE_V4_BOOKMARK_SCHEMA
        )

    @classmethod
    def _row_is_technical_universe_bookmark(cls, row: object) -> bool:
        if not hasattr(row, "get"):
            return False
        source = str(row.get("source", row.get("來源", "")) or "").strip()
        return (
            source == DAILY_MARKET_TECHNICAL_UNIVERSE_V4_BOOKMARK_SOURCE
            or cls._is_technical_universe_bookmark_payload(
                row.get("research_bookmark")
            )
        )

    @classmethod
    def _exact_research_bookmark_id_for_row(cls, row: object) -> str:
        """讀取列內既有的精確身份，不替 full-N payload 補舊欄位別名。"""

        if not hasattr(row, "get"):
            return ""
        payload = row.get("research_bookmark")
        if not isinstance(payload, Mapping):
            return ""
        if cls._is_technical_universe_bookmark_payload(payload):
            try:
                bookmark = DailyMarketTechnicalUniverseV4Bookmark.from_dict(payload)
            except Exception:
                return ""
            code = str(row.get("證券代號", row.get("stock_code", "")) or "").strip()
            source = str(row.get("source", row.get("來源", "")) or "").strip()
            source_id = str(row.get("source_id", "") or "").strip()
            if (
                bookmark.stock_code != code
                or source != DAILY_MARKET_TECHNICAL_UNIVERSE_V4_BOOKMARK_SOURCE
                or source_id != bookmark.bookmark_identity_sha256
            ):
                return ""
            return bookmark.bookmark_identity_sha256
        if (
            str(row.get("source", row.get("來源", "")) or "").strip()
            == DAILY_MARKET_TECHNICAL_UNIVERSE_V4_BOOKMARK_SOURCE
        ):
            return ""
        return str(payload.get("bookmark_id", "") or "").strip()

    @classmethod
    def _row_declares_research_bookmark(cls, row: object) -> bool:
        if not hasattr(row, "get"):
            return False
        if cls._has_research_bookmark(row.get("research_bookmark")):
            return True
        source = str(row.get("source", row.get("來源", "")) or "").strip()
        return source in {
            DAILY_MARKET_RESEARCH_BOOKMARK_SOURCE,
            DAILY_MARKET_TECHNICAL_UNIVERSE_V4_BOOKMARK_SOURCE,
        }

    @classmethod
    def _research_bookmark_row_label(cls, row: object) -> str:
        if not hasattr(row, "get"):
            return "書籤列格式錯誤；來源不可核驗"
        value = row.get("research_bookmark")
        if not cls._has_research_bookmark(value) and cls._row_declares_research_bookmark(row):
            if cls._row_is_technical_universe_bookmark(row):
                return "完整母體書籤內容缺失；來源不可核驗"
            return "書籤內容缺失；來源不可核驗"
        return cls._research_bookmark_label(value)

    @classmethod
    def _research_bookmark_label(cls, value: object) -> str:
        if not cls._has_research_bookmark(value):
            return "—"
        if not isinstance(value, Mapping):
            return "書籤格式錯誤；來源不可核驗"
        schema = str(value.get("schema_version", "") or "").strip()
        if schema == ORIGINAL_STOCK_RANKING_BOOKMARK_SCHEMA:
            try:
                decoded = decode_daily_market_research_bookmark(value)
                rank_context = decoded.rank_context
            except Exception as exc:
                code = str(getattr(exc, "code", "") or "").strip()
                return f"原排名書籤無效；來源不可核驗：{code or type(exc).__name__}"
            period = "週" if rank_context.period == "week" else "日"
            direction = "強勢 Top" if rank_context.direction == "strong" else "弱勢 Bottom"
            return (
                f"已收藏原排名｜{period}／{direction}｜第 {rank_context.selected_rank} 名｜"
                f"決策日 {rank_context.decision_date}"
            )
        if schema == DAILY_MARKET_TECHNICAL_UNIVERSE_V4_BOOKMARK_SCHEMA:
            try:
                bookmark = DailyMarketTechnicalUniverseV4Bookmark.from_dict(value)
                decision_date = bookmark.origin_query.decision_date.isoformat()
            except Exception as exc:
                code = str(getattr(exc, "code", "") or "").strip()
                return f"完整母體書籤無效；來源不可核驗：{code or type(exc).__name__}"
            return (
                f"已收藏完整母體技術研究｜決策日 {decision_date}｜"
                f"股票 {bookmark.stock_code}｜ID {bookmark.bookmark_identity_sha256[:12]}"
            )
        if schema != "daily-market-research-bookmark.v1":
            return f"書籤版本不支援：{schema or '未提供'}"
        required = (
            "bookmark_id",
            "payload_sha256",
            "query_sha256",
            "filter_state",
            "stock_code",
            "source_snapshot_id",
            "source_snapshot_hash",
            "decision_date",
            "snapshot_root",
            "cohort_id",
            "condition_keys",
            "combine_mode",
            "method_contracts_sha256",
            "context",
        )
        missing = [key for key in required if key not in value or value[key] in (None, "")]
        if missing:
            return "書籤資料不完整；來源不可核驗"
        decision_date = str(value.get("decision_date", "未知"))
        cohort_id = str(value.get("cohort_id", "未提供"))
        return f"已收藏｜日期 {decision_date}｜cohort {cohort_id}"

    def _context_from_row_bookmark(
        self,
        row: object,
        expected_stock_code: str,
        *,
        report_error: bool = True,
    ) -> ResearchStockContextDTO | None:
        def fail(message: str, *, level: str = "error") -> None:
            if report_error:
                self._set_status_label(message, level=level)

        bookmark = row.get("research_bookmark") if hasattr(row, "get") else None
        if self._row_is_technical_universe_bookmark(row):
            fail(
                "完整母體技術收藏需由下方收藏控制項 typed reopen；不會轉入舊每日研究或最新來源路徑。",
                level="warning",
            )
            return None
        if not isinstance(bookmark, Mapping):
            fail(
                "每日研究書籤內容缺失或格式錯誤；已拒絕下鑽，請勿改用手動來源。",
            )
            return None
        bookmark_id = str(bookmark.get("bookmark_id", "") or "").strip()
        if not bookmark_id:
            fail(
                "每日研究書籤缺少精確身份；已拒絕下鑽，請勿改用手動來源。",
            )
            return None
        if bookmark.get("schema_version") == ORIGINAL_STOCK_RANKING_BOOKMARK_SCHEMA:
            getter = getattr(
                self.watchlist_service,
                "get_rank_research_bookmark_context",
                None,
            )
            if not callable(getter):
                fail("觀察清單服務無法讀回原排名收藏；已拒絕下鑽。")
                return None
            db_path = self._rank_bookmark_db_path()
            if not db_path:
                fail("沒有可核驗原排名收藏來源的資料庫路徑；已拒絕下鑽。")
                return None
            try:
                read_result = getter(bookmark_id, db_path=db_path)
            except Exception as error:
                fail(f"原排名收藏讀回失敗；已拒絕下鑽：{error}")
                return None
            status = str(getattr(read_result, "status", "") or "")
            if status != "loaded":
                code = str(getattr(read_result, "code", "") or status or "source_refused")
                message = str(
                    getattr(read_result, "message", "")
                    or self._rank_bookmark_status_text(status, code)
                )
                fail(f"原排名收藏 {self._rank_bookmark_status_text(status, code)}；{message}")
                return None
            context = getattr(read_result, "context", None)
            exact_source_id = str(getattr(read_result, "source_id", "") or "")
            if (
                exact_source_id != bookmark_id
                or not self._bookmark_context_matches_record(
                    context, bookmark, expected_stock_code
                )
            ):
                fail("原排名收藏回傳的精確 source_id／股票／版本與此列不一致；已拒絕下鑽。")
                return None
            returned_bookmark = getattr(read_result, "bookmark", None)
            to_dict = getattr(returned_bookmark, "to_dict", None)
            if callable(to_dict):
                try:
                    if dict(to_dict()) != dict(bookmark):
                        fail("原排名收藏 payload 與服務讀回身份不一致；已拒絕下鑽。")
                        return None
                except Exception as error:
                    fail(f"原排名收藏 payload 無法精確比較；已拒絕下鑽：{error}")
                    return None
            return context
        getter = getattr(self.watchlist_service, "get_research_bookmark_context", None)
        if not callable(getter):
            fail("觀察清單服務無法讀回每日研究書籤；已拒絕下鑽。")
            return None
        try:
            context = getter(bookmark_id)
        except Exception as error:
            fail(f"每日研究書籤無效或不支援，已拒絕下鑽：{error}")
            return None
        if context is None:
            fail("每日研究書籤不存在或來源已撤回；已拒絕下鑽。")
            return None
        if not self._bookmark_context_matches_record(
            context, bookmark, expected_stock_code
        ):
            fail("讀回的每日研究書籤與此列來源身份不一致；已拒絕下鑽。")
            return None
        return context

    @staticmethod
    def _bookmark_context_matches_record(
        context: object,
        bookmark: Mapping[str, object],
        expected_stock_code: str,
    ) -> bool:
        if bookmark.get("schema_version") == DAILY_MARKET_TECHNICAL_UNIVERSE_V4_BOOKMARK_SCHEMA:
            return False
        if not isinstance(context, ResearchStockContextDTO):
            return False
        if bookmark.get("schema_version") == ORIGINAL_STOCK_RANKING_BOOKMARK_SCHEMA:
            try:
                decoded = decode_daily_market_research_bookmark(bookmark)
                decoded_payload = decoded.to_dict()
                expected_context = decoded.context
            except Exception:
                return False
            return (
                decoded_payload == dict(bookmark)
                and context == expected_context
                and context.stock_code == expected_stock_code
                and context.source_kind == "original_stock_ranking_bookmark"
                and context.source_workspace == "watchlist"
                and context.source_id == str(bookmark.get("bookmark_id", "") or "")
                and context.rank_context is not None
                and context.rank_context.selected_stock_code == expected_stock_code
                and context.result_id == ""
            )
        context_values = {
            "stock_code": context.stock_code,
            "source_kind": context.source_kind,
            "source_workspace": context.source_workspace,
            "source_id": context.source_id,
            "result_id": context.result_id,
            "decision_date": context.decision_date,
            "data_date": context.data_date,
            "source_snapshot_id": context.source_snapshot_id,
            "source_snapshot_hash": context.source_snapshot_hash,
            "daily_snapshot_root": context.daily_snapshot_root,
            "daily_snapshot_cohort_id": context.daily_snapshot_cohort_id,
            "daily_snapshot_condition_keys": context.daily_snapshot_condition_keys,
            "daily_snapshot_combine_mode": context.daily_snapshot_combine_mode,
        }
        condition_keys = bookmark.get("condition_keys", ())
        if isinstance(condition_keys, str):
            expected_conditions = ",".join(
                part.strip() for part in condition_keys.split(",") if part.strip()
            )
        else:
            expected_conditions = ",".join(
                str(part).strip() for part in (condition_keys or ()) if str(part).strip()
            )
        expected = {
            "stock_code": expected_stock_code,
            "source_kind": "daily_market_research_snapshot",
            "source_workspace": "watchlist",
            "source_id": str(bookmark.get("bookmark_id", "") or ""),
            "result_id": "",
            "decision_date": str(bookmark.get("decision_date", "") or ""),
            "data_date": str(bookmark.get("data_date", "") or ""),
            "source_snapshot_id": str(bookmark.get("source_snapshot_id", "") or ""),
            "source_snapshot_hash": str(bookmark.get("source_snapshot_hash", "") or ""),
            "daily_snapshot_root": str(bookmark.get("snapshot_root", "") or ""),
            "daily_snapshot_cohort_id": str(bookmark.get("cohort_id", "") or ""),
            "daily_snapshot_condition_keys": expected_conditions,
            "daily_snapshot_combine_mode": str(
                bookmark.get("combine_mode", "") or ""
            ).upper(),
        }
        for field_name, expected_value in expected.items():
            actual_value = str(context_values[field_name] or "").strip()
            expected_text = str(expected_value or "").strip()
            if field_name == "data_date" and not actual_value:
                # StockResearchReport may clear the first-read data date while
                # retaining its exact bookmark source identity.
                continue
            if actual_value != expected_text:
                return False
        return True

    @classmethod
    def _bookmark_context_summary(
        cls, bookmark: object, context: ResearchStockContextDTO | None
    ) -> str:
        if context is None:
            return "狀態：書籤無法核驗｜決策日：未知｜資料日：未知｜來源：拒絕比較"
        return (
            "狀態：每日研究收藏｜"
            f"決策日：{context.decision_date or '未知'}｜"
            f"資料日：{context.data_date or '未知'}｜"
            "來源：固定於原始快照"
        )

    @staticmethod
    def _research_bookmark_detail(
        bookmark: object, context: ResearchStockContextDTO | None
    ) -> str:
        if (
            isinstance(bookmark, Mapping)
            and bookmark.get("schema_version")
            == DAILY_MARKET_TECHNICAL_UNIVERSE_V4_BOOKMARK_SCHEMA
        ):
            return "完整母體技術收藏需由下方 typed reopen 控制項重開；不轉入舊每日研究 context。"
        if context is None or not isinstance(bookmark, Mapping):
            return "書籤格式無效、不支援或已無法讀回；不會改用手動或最新來源。"
        if bookmark.get("schema_version") == ORIGINAL_STOCK_RANKING_BOOKMARK_SCHEMA:
            rank = context.rank_context
            if rank is None:
                return "原排名收藏缺少 typed rank context；來源不可核驗，不會自動改用最新來源。"
            return "\n".join(
                (
                    f"{context.stock_code}｜原始排名唯讀收藏",
                    f"模式：{'週' if rank.period == 'week' else '日'}／"
                    f"{'強勢 Top' if rank.direction == 'strong' else '弱勢 Bottom'}｜"
                    f"原名次：{rank.selected_rank}",
                    f"決策日：{rank.decision_date}｜比較日：{rank.comparison_date} → {rank.latest_date}",
                    f"實際比較窗口：{'、'.join(rank.comparison_window_dates)}｜規則：{rank.comparison_window_rule}",
                    f"排名來源 ID：{rank.rank_snapshot_id}｜排名來源 SHA-256：{rank.source_hash}",
                    f"父快照 ID：{rank.parent_snapshot_id}｜父快照 SHA-256：{rank.parent_snapshot_hash}",
                    f"研究母體 SHA-256：{rank.research_universe_sha256}",
                    f"方法／版本：{rank.method_name} {rank.method_version}｜方法契約 SHA-256：{rank.method_contract_sha256}",
                    f"引擎 SHA-256：{rank.engine_file_sha256}｜來源 schema SHA-256：{rank.source_schema_sha256}",
                    f"收藏完整性 SHA-256：{bookmark.get('payload_sha256', '未提供')}｜查詢 SHA-256：{bookmark.get('query_sha256', '未提供')}",
                    "開啟時只重驗此收藏固定的 rank manifest；publisher numeric score 未公開。",
                )
            )
        methods = bookmark.get("method_contracts", {})
        try:
            methods_text = json.dumps(
                methods, ensure_ascii=False, sort_keys=True, default=str
            )
        except (TypeError, ValueError):
            methods_text = str(methods)
        return "\n".join(
            (
                f"{context.stock_code}｜每日研究唯讀書籤",
                f"決策日：{context.decision_date}｜資料日：{context.data_date or '未提供'}",
                f"來源 manifest：{context.source_snapshot_id}",
                f"來源 hash：{context.source_snapshot_hash}",
                f"書籤完整性 hash：{bookmark.get('payload_sha256', '未提供')}",
                f"快照身份 hash：{bookmark.get('snapshot_identity_sha256', '未提供')}",
                f"輸入指紋 hash：{bookmark.get('input_fingerprint_sha256', '未提供')}",
                f"cohort：{context.daily_snapshot_cohort_id}",
                f"條件：{context.daily_snapshot_condition_keys}｜組合：{context.daily_snapshot_combine_mode}",
                f"結果篩選：{bookmark.get('filter_state', '未提供')}",
                f"排序偏好：{bookmark.get('sort_key', '未提供')}｜"
                f"降冪：{'是' if bookmark.get('descending') is True else '否'}",
                f"方法契約：{methods_text}",
                f"方法契約 hash：{bookmark.get('method_contracts_sha256', '未提供')}",
                f"query hash：{bookmark.get('query_sha256', '未提供')}",
                "開啟時只使用此書籤固定來源。",
            )
        )

    def _set_source_choice_state(self, row: object | None) -> None:
        """顯示 legacy row 的 explicit source selection path。"""

        button = getattr(self, "choose_source_btn", None)
        if button is None:
            return
        if row is None or not hasattr(row, "get"):
            button.setVisible(False)
            button.setEnabled(False)
            return
        code = str(row.get("證券代號", "") or "").strip()
        if self._row_is_technical_universe_bookmark(row):
            button.setVisible(False)
            button.setEnabled(False)
            return
        identity = self._row_decision_identity(row, code)
        needs_choice = bool(code) and not identity.is_linked
        button.setVisible(needs_choice)
        button.setEnabled(needs_choice and bool(self._saved_source_options(code)))

    def _selected_watchlist_row(self) -> tuple[object, str] | None:
        model = self.stocks_model
        selection = self.stocks_table.selectionModel()
        rows = selection.selectedRows() if selection else []
        if model is None or len(rows) != 1:
            return None
        frame = model.getDataFrame()
        row_number = rows[0].row()
        if row_number < 0 or row_number >= len(frame):
            return None
        row = frame.iloc[row_number]
        return row, str(row.get("證券代號", "") or "").strip()

    def _saved_source_options(self, stock_code: str) -> list[dict[str, str]]:
        service = self.analysis_service
        list_sources = getattr(service, "list_saved_sources", None)
        code = str(stock_code or "").strip()
        if not callable(list_sources) or not code:
            return []
        try:
            cutoff = datetime.now(ZoneInfo("Asia/Taipei")).date()
            values = list_sources(code, as_of_date=cutoff)
        except Exception as error:
            logger.warning("[WatchlistView] 讀取保存結果選項失敗：%s", error)
            return []
        return [item for item in values if isinstance(item, dict) and item.get("result_id")]

    def _choose_recommendation_source(self) -> None:
        selected = self._selected_watchlist_row()
        if selected is None:
            self._set_status_label("請先選取一檔 legacy 候選。", level="info")
            return
        row, code = selected
        if not code:
            return
        options = self._saved_source_options(code)
        if not options:
            self._set_status_label(
                "目前沒有可選的保存推薦結果；請先到推薦分析保存原始結果。",
                level="warning",
            )
            return
        labels = []
        for item in options:
            membership = item.get("membership_status")
            pinned_dates = (
                f"決策日 {item.get('decision_date') or '未提供'}｜"
                f"資料日 {item.get('data_date') or '未提供'}"
            )
            if membership == "not_in_result":
                detail = (
                    f"同股明列未入選：{item.get('screening_reason') or '未提供原因'}｜"
                    f"{pinned_dates}"
                )
            elif membership == "saved":
                detail = f"此股已入選｜{pinned_dates}"
            else:
                detail = "來源待驗證"
            labels.append(
                f"{item['result_id']}｜{item.get('result_name') or '未命名結果'}｜{detail}"
            )
        selected_label, accepted = QInputDialog.getItem(
            self,
            "選擇同股保存來源",
            f"為 {code} 明確選取同股保存結果；未入選紀錄只作排除證據，不代表推薦：",
            labels,
            0,
            False,
        )
        if not accepted or selected_label not in labels:
            return
        source = options[labels.index(selected_label)]
        result_id = str(source["result_id"]).strip()
        if self.analysis_service is None:
            self._set_status_label("保存分析服務尚未配置；未寫入來源。", level="error")
            return
        cutoff = datetime.now(ZoneInfo("Asia/Taipei")).date()
        try:
            analysis = self.analysis_service.fetch(code, result_id, cutoff)
        except Exception as error:
            self._set_status_label(f"無法驗證來源內容；未寫入來源：{error}", level="error")
            return
        analysis_date = str(
            getattr(analysis, "decision_date", "")
            or getattr(analysis, "analysis_date", "")
        ).strip()
        try:
            parsed_date = date.fromisoformat(analysis_date)
        except ValueError:
            parsed_date = None
        status = str(getattr(analysis, "status", "") or "")
        current_identity = (
            status,
            analysis_date,
            str(getattr(analysis, "data_date", "") or "").strip(),
            str(getattr(analysis, "source_id", "") or "").strip(),
            str(getattr(analysis, "source_snapshot_id", "") or "").strip(),
            str(getattr(analysis, "source_snapshot_hash", "") or "").strip(),
        )
        selected_identity = tuple(
            str(source.get(field_name, "") or "").strip()
            for field_name in (
                "membership_status",
                "decision_date",
                "data_date",
                "source_id",
                "source_snapshot_id",
                "source_snapshot_hash",
            )
        )
        exact_membership = status == "saved" or (
            status == "not_in_result"
            and bool(str(getattr(analysis, "reasons", "") or "").strip())
        )
        if (
            str(getattr(analysis, "stock_code", "") or "").strip() != code
            or str(getattr(analysis, "result_id", "") or "").strip() != result_id
            or current_identity != selected_identity
            or not exact_membership
            or parsed_date is None
            or parsed_date.isoformat() != analysis_date
            or parsed_date > cutoff
        ):
            self._set_status_label(
                "來源與目前股票、決策日或保存內容不一致；未寫入來源，請重新載入清單。",
                level="warning",
            )
            return
        source_snapshot_id = str(getattr(analysis, "source_snapshot_id", "") or "").strip()
        source_snapshot_hash = str(getattr(analysis, "source_snapshot_hash", "") or "").strip()
        if source_snapshot_id == result_id:
            source_snapshot_id = ""
        if source_snapshot_hash == result_id:
            source_snapshot_hash = ""
        identity = DecisionIdentity(
            result_id=result_id,
            stock_code=code,
            source_snapshot_id=source_snapshot_id,
            source_snapshot_hash=source_snapshot_hash,
            decision_date=analysis_date,
        )
        source_value = row.get("source_id", "")
        expected_source_id = source_value.strip() if isinstance(source_value, str) else ""
        binder = getattr(self.watchlist_service, "bind_stock_decision_identity", None)
        if not callable(binder):
            self._set_status_label("目前候選池服務不支援來源綁定。", level="error")
            return
        try:
            bound = binder(
                code,
                identity,
                expected_source_id=expected_source_id,
            )
        except Exception as error:
            self._set_status_label(f"原推薦來源綁定失敗：{error}", level="error")
            return
        if not bound:
            self._set_status_label(
                "無法唯一定位此候選；未寫入來源，請先處理同股多列的既有 identity。",
                level="warning",
            )
            return
        self._load_watchlist()
        if status == "not_in_result":
            message = (
                f"已連結 {code} → {result_id} 的同股篩選紀錄；此股明列未入選，"
                "只保留排除證據，不會當成推薦。"
            )
        else:
            message = f"已驗證並連結 {code} → {result_id}；後續研究沿用此同股來源。"
        self._set_status_label(message, level="success")
        # 重載後依 exact result_id 定位該列，避免同股不同結果回到第一列。
        self.select_stock(code, result_id)

    def _request_stock_summary(self, code, source_id, request_id):
        if self.analysis_service is None:
            self.analysis_context_label.setText(
                f"狀態：研究中｜決策日：未知｜資料日：未知｜來源：未配置"
            )
            self.analysis_text.setPlainText(f"{code}｜分析來源尚未配置；可使用個股主力流向入口。")
            return
        self.analysis_context_label.setText(
            f"狀態：讀取中｜決策日：未知｜資料日：未知｜來源：{source_id or '未標示'}"
        )
        self.analysis_text.setPlainText(f"{code}｜正在讀取已保存分析…")
        service = self.analysis_service
        cutoff = datetime.now(ZoneInfo("Asia/Taipei")).date()
        worker = TaskWorker(lambda: service.fetch(code, source_id, cutoff))
        self._analysis_worker = worker
        worker.finished.connect(lambda result: self._show_selected_analysis(request_id, result))
        worker.error.connect(lambda error: self._show_analysis_error(request_id, error))
        worker.native_thread_finished.connect(worker.deleteLater)
        worker.start()

    def _preview_universe_stocks(self):
        self._analysis_request_id += 1
        self.analysis_text.clear()
        self.universe_stock_list.clear()
        selected = self.universe_list.currentItem()
        if selected is None or self.universe_service is None:
            return
        try:
            universe = self.universe_service.load_watchlist(selected.data(Qt.UserRole))
            if universe is None:
                return
            codes = [str(code).strip() for code in universe.codes]
            names = self._query_stock_names(codes)
            for code in codes:
                item = QListWidgetItem(f"{code} {names.get(code, '')}")
                item.setData(Qt.UserRole, code)
                item.setData(Qt.UserRole + 1, names.get(code, ""))
                self.universe_stock_list.addItem(item)
        except Exception as error:
            self.analysis_text.setPlainText(f"清單預覽讀取失敗：{error}")

    def _select_universe_stock(self, current, _previous):
        self._analysis_request_id += 1
        if current is not None:
            self._request_stock_summary(str(current.data(Qt.UserRole)), "", self._analysis_request_id)

    def _show_selected_analysis(self, request_id, result):
        if request_id != self._analysis_request_id:
            return
        status = str(getattr(result, "status", "unavailable") or "unavailable")
        status_label = {
            "saved": "研究／等待",
            "not_in_result": "研究／未入選",
            "missing": "資料缺漏",
            "unavailable": "不可用",
        }.get(status, "研究中")
        self.analysis_context_label.setText(
            f"狀態：{status_label}｜決策日：{getattr(result, 'decision_date', '') or getattr(result, 'analysis_date', '') or '未知'}"
            f"｜資料日：{getattr(result, 'data_date', '') or '未知'}"
            f"｜來源：{getattr(result, 'result_id', '') or getattr(result, 'source_id', '') or '未標示'}"
        )
        selected = self._selected_watchlist_row()
        if selected is not None and str(getattr(result, "stock_code", "")).strip() == selected[1]:
            self._set_watchlist_focus_summary(
                row=selected[0],
                status=status_label,
                message=str(getattr(result, "message", "") or "").strip(),
            )
        lines = [result.stock_code, result.message]
        if result.analysis_date:
            lines.append(f"分析日期：{result.analysis_date}｜來源：{result.result_id}")
        if getattr(result, "data_date", "") and result.data_date != result.analysis_date:
            lines.append(f"資料日期：{result.data_date}")
        if getattr(result, "profile_id", ""):
            profile = result.profile_id
            if getattr(result, "profile_version", ""):
                profile += f"（{result.profile_version}）"
            lines.append(f"Profile：{profile}")
        if result.status == "saved":
            lines.extend([f"當時收盤價：{result.close_price}｜推薦總分：{result.score}", f"推薦理由：{result.reasons}"])
        presentation = self.presentation_service.from_watchlist_analysis(result)
        lines.extend(["", "共用呈現契約（唯讀）：", format_decision_presentation(presentation)])
        self.analysis_text.setPlainText("\n".join(lines))

    def _show_analysis_error(self, request_id, error):
        if request_id == self._analysis_request_id:
            self.analysis_context_label.setText(
                "狀態：讀取失敗｜決策日：未知｜資料日：未知｜來源：未知"
            )
            self.analysis_text.setPlainText(f"分析讀取失敗：{str(error).splitlines()[0]}")
            selected = self._selected_watchlist_row()
            if selected is not None:
                self._set_watchlist_focus_summary(
                    row=selected[0],
                    status="讀取失敗",
                    message=str(error).splitlines()[0],
                )

    def closeEvent(self, event):
        self.begin_shutdown()
        super().closeEvent(event)

    def begin_shutdown(self) -> bool:
        """使舊分析結果失效並取消收藏控制項，不更動分析 worker 的既有流程。"""

        if not self._shutdown_started:
            self._shutdown_started = True
            self._analysis_request_id += 1
        technical_finished = self.technical_bookmark_controls.begin_shutdown()
        controls = self.personal_h20_bookmark_controls
        h20_finished = controls.begin_shutdown() if controls is not None else True
        return technical_finished and h20_finished

    def _open_stock_analysis(self, _checked=False):
        """以畫面排序後的選取列傳送股票代號與來源脈絡。"""
        selection = self.stocks_table.selectionModel()
        rows = selection.selectedRows() if selection else []
        if self.stocks_model is None or len(rows) != 1:
            self._set_status_label("請選取一檔股票查看個股研究報告", level="info")
            return
        frame = self.stocks_model.getDataFrame()
        row = frame.iloc[rows[0].row()]
        code = str(row["證券代號"]).strip()
        if self._row_is_technical_universe_bookmark(row):
            self._set_status_label(
                "完整母體技術收藏請使用下方收藏控制項重開；已拒絕舊個股研究路徑。",
                level="warning",
            )
            return
        if self._row_declares_research_bookmark(row):
            context = self._context_from_row_bookmark(row, code)
            if context is None:
                return
            self.stockAnalysisRequested.emit(code)
            self.stockResearchRequested.emit(context)
            self._set_status_label(
                f"已開啟 {code} 的唯讀每日研究書籤；來源固定於原 manifest。",
                level="success",
            )
            return
        if not code:
            return
        source_value = row.get("source_id", "")
        source_id = source_value.strip() if isinstance(source_value, str) else ""
        decision_identity = self._row_decision_identity(row, code)
        self.stockAnalysisRequested.emit(code)
        self.stockResearchRequested.emit(
            self._build_stock_research_context(
                code,
                str(row.get("證券名稱", "") or "").strip(),
                source_id,
                decision_identity=decision_identity,
            )
        )

    def _open_latest_source_research(self, _checked=False) -> bool:
        """由使用者明確要求另一個以最新來源為準的唯讀研究。"""

        selected = self._selected_watchlist_row()
        if selected is None:
            self._set_status_label("請先選取一檔股票，再明確要求以最新來源另開研究。", level="info")
            return False
        row, code = selected
        if not code:
            return False
        if self._row_is_technical_universe_bookmark(row):
            self._set_status_label(
                "完整母體技術收藏固定於原保存來源；不提供改用最新來源的路徑。",
                level="warning",
            )
            return False
        if self._row_declares_research_bookmark(row):
            context = self._context_from_row_bookmark(row, code)
            if context is None:
                # 明確的「另開最新」操作可以建立全新、無排名來源的 context；
                # 原收藏仍保留且不會因最新研究而變更。
                context = ResearchStockContextDTO(
                    stock_code=code,
                    stock_name=str(row.get("證券名稱", "") or "").strip(),
                    source_kind="explicit_latest_stock_research",
                    source_label="原收藏無法核驗；使用者明確另開最新個股研究",
                    source_workspace="stock_research",
                )
        else:
            context = ResearchStockContextDTO(
                stock_code=code,
                stock_name=str(row.get("證券名稱", "") or "").strip(),
                source_kind="watchlist_latest_request",
                source_label="使用者明確要求以最新來源另開唯讀研究",
                source_workspace="watchlist",
            )
        self.latestResearchRequested.emit(context)
        self._set_status_label(
            f"已送出 {code} 的最新來源唯讀研究請求；已保存研究書籤未變更。",
            level="info",
        )
        return True

    @staticmethod
    def _bookmark_group_matches_context(
        bookmark: Mapping[str, object], context: ResearchStockContextDTO
    ) -> bool:
        if bookmark.get("schema_version") == DAILY_MARKET_TECHNICAL_UNIVERSE_V4_BOOKMARK_SCHEMA:
            return False
        if bookmark.get("schema_version") == ORIGINAL_STOCK_RANKING_BOOKMARK_SCHEMA:
            try:
                decoded = decode_daily_market_research_bookmark(bookmark)
                bookmark_context = decoded.context
                other_rank = decoded.rank_context
                base_rank = context.rank_context
            except Exception:
                return False
            if base_rank is None:
                return False
            # 每筆收藏綁定不同選取列；群組比較只忽略選取股票／名次，仍精確比較
            # 同一 pinned manifest、模式、查詢偏好及外層 Daily 查詢身份。
            rank_fields = (
                "rank_kind",
                "period",
                "direction",
                "rank_snapshot_id",
                "source_hash",
                "ranking_root",
                "snapshot_root",
                "decision_date",
                "parent_snapshot_id",
                "parent_snapshot_hash",
                "parent_cohort_id",
                "comparison_date",
                "latest_date",
                "comparison_window_dates",
                "comparison_window_rule",
                "volume_reference_point_count",
                "declared_stock_codes",
                "eligible_stock_codes",
                "missing_rank_stock_codes",
                "research_universe_json",
                "research_universe_sha256",
                "method_name",
                "method_version",
                "method_contract_sha256",
                "engine_file_sha256",
                "engine_parameters_json",
                "engine_parameters_sha256",
                "source_schema_sha256",
                "filter_state",
                "sort_key",
                "descending",
            )
            return (
                all(getattr(other_rank, field) == getattr(base_rank, field) for field in rank_fields)
                and bookmark_context.source_workspace == "watchlist"
                and bookmark_context.daily_snapshot_root == context.daily_snapshot_root
                and bookmark_context.daily_snapshot_cohort_id == context.daily_snapshot_cohort_id
                and bookmark_context.daily_snapshot_condition_keys
                == context.daily_snapshot_condition_keys
                and bookmark_context.daily_snapshot_combine_mode
                == context.daily_snapshot_combine_mode
            )
        if WatchlistView._research_bookmark_label(bookmark).startswith(
            ("書籤版本不支援", "書籤資料不完整")
        ):
            return False
        keys = bookmark.get("condition_keys", ())
        if isinstance(keys, str):
            conditions = ",".join(
                part.strip() for part in keys.split(",") if part.strip()
            )
        elif isinstance(keys, (list, tuple)):
            conditions = ",".join(str(part).strip() for part in keys if str(part).strip())
        else:
            return False
        return (
            str(bookmark.get("source_snapshot_id", "") or "")
            == context.source_snapshot_id
            and str(bookmark.get("source_snapshot_hash", "") or "")
            == context.source_snapshot_hash
            and str(bookmark.get("decision_date", "") or "")
            == context.decision_date
            and str(bookmark.get("snapshot_root", "") or "")
            == context.daily_snapshot_root
            and str(bookmark.get("cohort_id", "") or "")
            == context.daily_snapshot_cohort_id
            and conditions == context.daily_snapshot_condition_keys
            and str(bookmark.get("combine_mode", "") or "").upper()
            == context.daily_snapshot_combine_mode
        )

    def _rank_bookmark_db_path(self) -> str | None:
        config = self.config or getattr(self.watchlist_service, "config", None)
        value = getattr(config, "db_file", None) or getattr(
            config, "sqlite_db_file", None
        )
        return str(value) if value else None

    @staticmethod
    def _rank_bookmark_status_text(status: str, code: str = "") -> str:
        labels = {
            "missing": "不存在或已被移除",
            "unsupported_version": "版本不支援",
            "wrong_hash": "完整性 hash 不符",
            "date_mismatch": "來源日期不符",
            "stock_mismatch": "股票身份不符",
            "source_refused": "原始排名來源已拒絕",
        }
        label = labels.get(status, "來源無法核驗")
        return f"{label}（{code}）" if code else label

    def _find_bookmark_record_for_context(
        self, context: ResearchStockContextDTO
    ) -> tuple[object, Mapping[str, object]] | None:
        if self.stocks_model is None or not context.source_id:
            return None
        frame = self.stocks_model.getDataFrame()
        matches: list[tuple[object, Mapping[str, object]]] = []
        for _, row in frame.iterrows():
            record = row.get("research_bookmark")
            if (
                isinstance(record, Mapping)
                and str(record.get("bookmark_id", "") or "") == context.source_id
                and self._bookmark_context_matches_record(
                    context,
                    record,
                    str(row.get("證券代號", "") or "").strip(),
                )
            ):
                matches.append((row, record))
        if len(matches) != 1:
            return None
        row, record = matches[0]
        code = str(row.get("證券代號", "") or "").strip()
        verified = self._context_from_row_bookmark(
            row, code, report_error=False
        )
        if verified is None or not self._bookmark_context_matches_record(
            verified, record, code
        ):
            return None
        return row, record

    def research_bookmark_stock_codes(
        self, context: ResearchStockContextDTO
    ) -> tuple[str, ...]:
        """列出相同 manifest、日期、篩選與 AND/OR 群組的有效書籤股票。"""

        if not isinstance(context, ResearchStockContextDTO):
            return ()
        base = self._find_bookmark_record_for_context(context)
        if base is None:
            return ()
        is_rank_bookmark = (
            base[1].get("schema_version") == ORIGINAL_STOCK_RANKING_BOOKMARK_SCHEMA
        )
        query_hash = str(base[1].get("query_sha256", "") or "")
        if not is_rank_bookmark and not query_hash:
            return ()
        frame = self.stocks_model.getDataFrame() if self.stocks_model is not None else None
        if frame is None:
            return ()
        codes: list[str] = []
        for _, row in frame.iterrows():
            record = row.get("research_bookmark")
            if not isinstance(record, Mapping):
                continue
            if not self._bookmark_group_matches_context(record, context):
                continue
            if not is_rank_bookmark and str(record.get("query_sha256", "") or "") != query_hash:
                continue
            if self._research_bookmark_label(record).startswith(
                ("書籤版本不支援", "書籤資料不完整")
            ):
                continue
            code = str(row.get("證券代號", "") or "").strip()
            resolved = self._context_from_row_bookmark(
                row, code, report_error=False
            )
            if resolved is None or not self._bookmark_context_matches_record(
                resolved, record, code
            ):
                continue
            if code and code not in codes:
                codes.append(code)
        return tuple(codes)

    def research_bookmark_context_for_stock(
        self, context: ResearchStockContextDTO, stock_code: str
    ) -> ResearchStockContextDTO | None:
        """在完全相同的來源與條件群組中讀回指定股票的書籤 context。"""

        requested = str(stock_code or "").strip()
        if not requested or not isinstance(context, ResearchStockContextDTO):
            return None
        base = self._find_bookmark_record_for_context(context)
        if base is None or self.stocks_model is None:
            return None
        base_record = base[1]
        is_rank_bookmark = (
            base_record.get("schema_version") == ORIGINAL_STOCK_RANKING_BOOKMARK_SCHEMA
        )
        query_hash = str(base_record.get("query_sha256", "") or "")
        if not is_rank_bookmark and not query_hash:
            return None
        frame = self.stocks_model.getDataFrame()
        candidates: list[tuple[object, Mapping[str, object], ResearchStockContextDTO]] = []
        for _, row in frame.iterrows():
            if str(row.get("證券代號", "") or "").strip() != requested:
                continue
            record = row.get("research_bookmark")
            if not isinstance(record, Mapping):
                continue
            if (
                self._bookmark_group_matches_context(record, context)
                and (
                    is_rank_bookmark
                    or str(record.get("query_sha256", "") or "") == query_hash
                )
                and self._research_bookmark_label(record).startswith("已收藏")
            ):
                resolved = self._context_from_row_bookmark(
                    row, requested, report_error=False
                )
                if resolved is None or not self._bookmark_context_matches_record(
                    resolved, record, requested
                ):
                    continue
                candidates.append((row, record, resolved))
        if len(candidates) != 1:
            if candidates:
                self._set_status_label(
                    "此股票在相同研究條件下有多個不同書籤；無法唯一還原，已拒絕切換。",
                    level="warning",
                )
            return None
        return candidates[0][2]

    def restore_research_bookmark_stock(
        self, context: ResearchStockContextDTO
    ) -> bool:
        """只選取與傳入 bookmark ID 及來源身份完全一致的列。"""

        if not isinstance(context, ResearchStockContextDTO) or self.stocks_model is None:
            self._set_status_label("每日研究書籤 context 無效；無法還原原列。", level="warning")
            return False
        frame = self.stocks_model.getDataFrame()
        matches: list[int] = []
        for row_number, (_, row) in enumerate(frame.iterrows()):
            record = row.get("research_bookmark")
            code = str(row.get("證券代號", "") or "").strip()
            if isinstance(record, Mapping) and self._bookmark_context_matches_record(
                context, record, code
            ):
                resolved = self._context_from_row_bookmark(
                    row, code, report_error=False
                )
                if resolved is not None and self._bookmark_context_matches_record(
                    resolved, record, code
                ):
                    matches.append(row_number)
        if len(matches) != 1:
            self._set_status_label(
                "找不到唯一且來源完全相同的研究書籤；未選取同股其他書籤。",
                level="warning",
            )
            return False
        self.stocks_table.selectRow(matches[0])
        return True

    def _open_universe_stock_analysis(self, item: QListWidgetItem) -> None:
        """由保存的選股清單下鑽；沒有 result id 時仍保留股票識別。"""

        code = str(item.data(Qt.UserRole) or "").strip()
        if not code:
            return
        name = str(item.data(Qt.UserRole + 1) or "").strip()
        self.stockAnalysisRequested.emit(code)
        self.stockResearchRequested.emit(
            self._build_stock_research_context(code, name, "")
        )

    def _build_stock_research_context(
        self,
        stock_code: str,
        stock_name: str = "",
        source_id: str = "",
        *,
        decision_identity: DecisionIdentity | Mapping[str, object] | None = None,
    ) -> ResearchStockContextDTO:
        """從觀察清單的保存來源建立唯讀上下文，不重新計算。"""

        code = str(stock_code).strip()
        source = str(source_id or "").strip()
        identity = self._row_decision_identity(
            {"decision_identity": decision_identity} if decision_identity is not None else {},
            code,
        )
        result = None
        explicit_result_id = identity.result_id if identity.is_linked else ""
        lookup_source = explicit_result_id or source
        if self.analysis_service is not None and lookup_source:
            try:
                cutoff = datetime.now(ZoneInfo("Asia/Taipei")).date()
                result = self.analysis_service.fetch(code, lookup_source, cutoff)
            except Exception as error:
                logger.warning("[WatchlistView] 讀取保存來源 metadata 失敗：%s", error)

        # result_id 只接受 row 的 typed identity，或已由 exact source lookup
        # 驗證成功的保存結果；不能把 legacy source_id 直接升格成結果身份。
        result_id = explicit_result_id
        if not result_id and result is not None and getattr(result, "status", "") in {
            "saved",
            "not_in_result",
        }:
            result_id = str(getattr(result, "result_id", "") or "").strip()
        decision_date = str(
            getattr(result, "decision_date", "")
            or getattr(result, "analysis_date", "")
            or identity.decision_date
            or ""
        )
        data_date = str(getattr(result, "data_date", "") or "")
        profile_id = str(getattr(result, "profile_id", "") or "")
        profile_version = str(getattr(result, "profile_version", "") or "")
        lineage_id = str(getattr(result, "source_id", "") or "")
        source_snapshot_id = str(
            getattr(result, "source_snapshot_id", "")
            or identity.source_snapshot_id
            or ""
        )
        source_snapshot_hash = str(
            getattr(result, "source_snapshot_hash", "")
            or identity.source_snapshot_hash
            or ""
        )
        identity_status = identity.identity_status
        for field_name in ("decision_date", "source_snapshot_id", "source_snapshot_hash"):
            context_value = getattr(identity, field_name)
            result_value = str(getattr(result, field_name, "") or "").strip()
            if context_value and result_value and context_value != result_value:
                identity_status = IDENTITY_STATUS_CONFLICT
        if result_id and not identity.is_linked:
            if identity_status != IDENTITY_STATUS_CONFLICT:
                identity_status = "linked"
        if result_id and getattr(result, "status", "") == "not_in_result":
            has_explicit_exclusion = bool(str(getattr(result, "reasons", "") or "").strip())
            source_label = (
                "保存篩選列（明列未入選；不代表看空）"
                if has_explicit_exclusion
                else "保存結果未包含此股"
            )
        else:
            source_label = "已保存推薦結果" if result_id else "觀察清單（尚未選定原始來源）"
        return ResearchStockContextDTO(
            stock_code=code,
            stock_name=stock_name,
            decision_date=decision_date,
            data_date=data_date,
            result_id=result_id,
            identity_status=identity_status,
            source_snapshot_id=source_snapshot_id,
            source_snapshot_hash=source_snapshot_hash,
            profile_id=profile_id,
            profile_version=profile_version,
            source_id=source or lineage_id,
            source_kind=str(getattr(result, "source_kind", "") or "recommendation"),
            source_label=source_label,
            source_workspace="watchlist",
        )

    def select_stock(self, stock_code: str, result_id: str | None = None) -> bool:
        """返回觀察清單時定位既有列，不載入或重算推薦。"""

        if self.stocks_model is None:
            return False
        code = str(stock_code).strip()
        frame = self.stocks_model.getDataFrame()
        for row_number, value in enumerate(frame.get("證券代號", ())):
            if str(value).strip() == code:
                if result_id:
                    row = frame.iloc[row_number]
                    row_identity = self._row_decision_identity(row, code)
                    source = str(row.get("source_id", "") or "").strip()
                    requested = str(result_id).strip()
                    exact_row_result = (
                        row_identity.result_id
                        if row_identity.is_linked
                        else ""
                    )
                    if exact_row_result and exact_row_result != requested:
                        continue
                    if not exact_row_result and source and source != requested:
                        continue
                    if not exact_row_result and not source:
                        continue
                self.stocks_table.selectRow(row_number)
                return True
        return False

    def _show_context_menu(self, position):
        """顯示右鍵選單"""
        if not self.stocks_model:
            return
        
        menu = QMenu(self)
        analysis_action = QAction("查看個股研究報告", self)
        analysis_action.triggered.connect(self._open_stock_analysis)
        menu.addAction(analysis_action)
        
        # 移除選項
        remove_action = QAction("移除選中", self)
        remove_action.triggered.connect(self._remove_selected)
        menu.addAction(remove_action)
        
        menu.exec(self.stocks_table.viewport().mapToGlobal(position))
    
    def add_stocks_from_dataframe(self, df: pd.DataFrame, source: str = "unknown"):
        """
        從 DataFrame 新增股票到觀察清單
        
        Args:
            df: 包含股票資料的 DataFrame（必須有 '證券代號' 或 'stock_code' 欄位）
            source: 來源標籤
        """
        if df is None or len(df) == 0:
            return
        
        # 轉換 DataFrame 為字典列表
        stocks = []
        for _, row in df.iterrows():
            stock_code = row.get('證券代號') or row.get('stock_code')
            stock_name = row.get('證券名稱') or row.get('stock_name', stock_code)
            source_id = row.get('source_id')
            if not isinstance(source_id, str) or not source_id.strip():
                source_id = row.get('result_id')
            source_id = source_id.strip() if isinstance(source_id, str) else ''

            raw_identity = row.get("decision_identity", {})
            if isinstance(raw_identity, Mapping):
                decision_identity = dict(raw_identity)
            else:
                def _clean(value: object) -> str:
                    if value is None:
                        return ""
                    try:
                        if bool(pd.isna(value)):
                            return ""
                    except (TypeError, ValueError):
                        pass
                    return str(value).strip()

                decision_identity = {
                    "result_id": _clean(row.get("result_id", "")),
                    "stock_code": _clean(stock_code),
                    "source_snapshot_id": _clean(row.get("source_snapshot_id", "")),
                    "source_snapshot_hash": _clean(row.get("source_snapshot_hash", "")),
                    "decision_date": _clean(row.get("decision_date", "")),
                }
            
            if stock_code:
                stocks.append({
                    'stock_code': str(stock_code),
                    'stock_name': str(stock_name),
                    'notes': '',
                    'source_id': source_id,
                    'decision_identity': decision_identity,
                })
        
        if stocks:
            try:
                added_count = self.watchlist_service.add_stocks(stocks, source=source)
                if added_count > 0:
                    self._load_watchlist()
                    self.watchlistUpdated.emit()
                    return added_count
            except Exception as e:
                QMessageBox.critical(self, "錯誤", f"新增股票到候選池失敗：\n{str(e)}")
        
        return 0
    
    def get_stock_codes(self) -> List[str]:
        """取得觀察清單中的股票代號列表"""
        return self.watchlist_service.get_stock_codes()
    
    # ========== 選股清單管理相關方法 ==========
    
    def _refresh_universe_list(self):
        """刷新選股清單列表"""
        if not self.universe_service or not hasattr(self, 'universe_list'):
            return
        
        self.universe_list.clear()
        try:
            watchlists = self.universe_service.list_watchlists()
            for watchlist in watchlists:
                name = watchlist.get('name', '')
                count = watchlist.get('count', 0)
                watchlist_id = watchlist.get('watchlist_id', '')
                display_text = f"{name} ({count}檔)"
                item = QListWidgetItem(display_text)
                item.setData(Qt.UserRole, watchlist_id)
                self.universe_list.addItem(item)
            
            # 顯示刷新成功提示（可選，避免過於頻繁）
            if hasattr(self, '_last_refresh_time'):
                from datetime import datetime
                now = datetime.now()
                if (now - self._last_refresh_time).total_seconds() > 1:  # 至少間隔1秒才顯示
                    pass  # 可以添加狀態提示
            else:
                from datetime import datetime
                self._last_refresh_time = datetime.now()
        except Exception as e:
            QMessageBox.warning(self, "錯誤", f"載入選股清單列表失敗：\n{str(e)}")
    
    def refresh_all(self):
        """刷新所有數據（觀察清單和選股清單）"""
        """當切換到觀察清單 Tab 時調用，確保數據同步"""
        self._load_watchlist()
        self._refresh_universe_list()
    
    def _save_watchlist_to_universe(self):
        """將當前觀察清單保存為選股清單"""
        if not self.universe_service:
            QMessageBox.warning(self, "錯誤", "選股清單服務未初始化")
            return
        
        # 獲取當前觀察清單的股票代號
        stock_codes = self.watchlist_service.get_stock_codes()
        if not stock_codes:
            QMessageBox.warning(self, "提示", "候選池為空，無法保存")
            return
        
        # 輸入清單名稱
        dialog = QDialog(self)
        dialog.setWindowTitle("保存為選股清單")
        dialog.setMinimumWidth(400)
        layout = QVBoxLayout(dialog)
        
        layout.addWidget(QLabel("清單名稱:"))
        name_input = QLineEdit()
        name_input.setPlaceholderText("例如：我的候選池")
        layout.addWidget(name_input)
        
        layout.addWidget(QLabel(f"將保存 {len(stock_codes)} 檔股票到選股清單"))
        
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        
        if dialog.exec() == QDialog.Accepted:
            name = name_input.text().strip()
            if not name:
                QMessageBox.warning(self, "錯誤", "請輸入清單名稱")
                return
            
            try:
                watchlist_id = self.universe_service.save_watchlist(
                    name=name,
                    codes=stock_codes,
                    source="watchlist"
                )
                QMessageBox.information(self, "成功", f"已保存為選股清單：{name}")
                self._refresh_universe_list()
            except Exception as e:
                QMessageBox.critical(self, "錯誤", f"保存失敗：\n{str(e)}")
    
    def _query_stock_names(self, stock_codes: List[str]) -> Dict[str, str]:
        """名稱解析只經候選池應用服務。"""
        return self.watchlist_service.query_stock_names(stock_codes)

    def _load_universe_to_watchlist(self):
        """從選股清單載入到候選池"""
        if not self.universe_service:
            QMessageBox.warning(self, "錯誤", "選股清單服務未初始化")
            return
        
        selected_items = self.universe_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "提示", "請選擇要載入的選股清單")
            return
        
        watchlist_id = selected_items[0].data(Qt.UserRole)
        watchlist = self.universe_service.load_watchlist(watchlist_id)
        
        if not watchlist:
            QMessageBox.warning(self, "錯誤", "載入選股清單失敗")
            return
        
        if not watchlist.codes:
            QMessageBox.warning(self, "提示", "選股清單為空")
            return
        
        # 確認對話框
        reply = QMessageBox.question(
            self, "確認",
            f"確定要將「{watchlist.name}」({len(watchlist.codes)}檔) 加入到候選池嗎？\n"
            f"（已存在的股票不會重複加入）",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply != QMessageBox.Yes:
            return
        
        # 轉換為觀察清單格式，並查詢股票名稱
        stocks = []
        stock_name_map = self._query_stock_names(watchlist.codes)
        
        for code in watchlist.codes:
            code_str = str(code).strip()
            stock_name = stock_name_map.get(code_str, code_str)
            stocks.append({
                'stock_code': code_str,
                'stock_name': stock_name,
                'notes': f'來自選股清單：{watchlist.name}'
            })
        
        try:
            added_count = self.watchlist_service.add_stocks(stocks, source='universe')
            if added_count > 0:
                QMessageBox.information(self, "成功", f"已加入 {added_count} 檔股票到候選池")
                self._load_watchlist()
                self.watchlistUpdated.emit()
            else:
                QMessageBox.information(self, "提示", "所有股票都已存在於候選池中")
        except Exception as e:
            QMessageBox.critical(self, "錯誤", f"載入失敗：\n{str(e)}")
    
    def _create_universe(self):
        """創建新選股清單"""
        if not self.universe_service:
            QMessageBox.warning(self, "錯誤", "選股清單服務未初始化")
            return
        
        dialog = QDialog(self)
        dialog.setWindowTitle("新增選股清單")
        dialog.setMinimumSize(500, 400)
        dialog_layout = QVBoxLayout(dialog)
        
        dialog_layout.addWidget(QLabel("清單名稱:"))
        name_input = QLineEdit()
        dialog_layout.addWidget(name_input)
        
        dialog_layout.addWidget(QLabel("股票代號（每行一個或逗號分隔）:"))
        codes_input = QTextEdit()
        codes_input.setMinimumHeight(200)
        dialog_layout.addWidget(codes_input)
        
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        dialog_layout.addWidget(buttons)
        
        if dialog.exec() == QDialog.Accepted:
            name = name_input.text().strip()
            if not name:
                QMessageBox.warning(self, "錯誤", "請輸入清單名稱")
                return
            
            # 解析股票代號
            codes_text = codes_input.toPlainText().strip()
            codes = self.universe_service.parse_codes_from_text(codes_text)
            
            if not codes:
                QMessageBox.warning(self, "錯誤", "請輸入至少一個股票代號")
                return
            
            try:
                self.universe_service.save_watchlist(name=name, codes=codes)
                QMessageBox.information(self, "成功", f"清單已創建: {name}")
                self._refresh_universe_list()
            except Exception as e:
                QMessageBox.critical(self, "錯誤", f"創建失敗: {str(e)}")
    
    def _edit_universe(self):
        """編輯選股清單"""
        if not self.universe_service:
            QMessageBox.warning(self, "錯誤", "選股清單服務未初始化")
            return
        
        selected_items = self.universe_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "錯誤", "請選擇要編輯的清單")
            return
        
        watchlist_id = selected_items[0].data(Qt.UserRole)
        watchlist = self.universe_service.load_watchlist(watchlist_id)
        if not watchlist:
            QMessageBox.warning(self, "錯誤", "載入清單失敗")
            return
        
        dialog = QDialog(self)
        dialog.setWindowTitle("編輯選股清單")
        dialog.setMinimumSize(500, 400)
        dialog_layout = QVBoxLayout(dialog)
        
        dialog_layout.addWidget(QLabel("清單名稱:"))
        name_input = QLineEdit(watchlist.name)
        dialog_layout.addWidget(name_input)
        
        dialog_layout.addWidget(QLabel("股票代號（每行一個或逗號分隔）:"))
        codes_input = QTextEdit('\n'.join(watchlist.codes))
        codes_input.setMinimumHeight(200)
        dialog_layout.addWidget(codes_input)
        
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        dialog_layout.addWidget(buttons)
        
        if dialog.exec() == QDialog.Accepted:
            name = name_input.text().strip()
            if not name:
                QMessageBox.warning(self, "錯誤", "請輸入清單名稱")
                return
            
            # 解析股票代號
            codes_text = codes_input.toPlainText().strip()
            codes = self.universe_service.parse_codes_from_text(codes_text)
            
            if not codes:
                QMessageBox.warning(self, "錯誤", "請輸入至少一個股票代號")
                return
            
            try:
                self.universe_service.save_watchlist(
                    name=name,
                    codes=codes,
                    watchlist_id=watchlist_id  # 更新現有清單
                )
                QMessageBox.information(self, "成功", f"清單已更新: {name}")
                self._refresh_universe_list()
            except Exception as e:
                QMessageBox.critical(self, "錯誤", f"更新失敗: {str(e)}")
    
    def _delete_universe(self):
        """刪除選股清單"""
        if not self.universe_service:
            QMessageBox.warning(self, "錯誤", "選股清單服務未初始化")
            return
        
        selected_items = self.universe_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "錯誤", "請選擇要刪除的清單")
            return
        
        watchlist_id = selected_items[0].data(Qt.UserRole)
        item_text = selected_items[0].text()
        
        reply = QMessageBox.question(
            self, "確認刪除",
            f"確定要刪除清單「{item_text}」嗎？",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            try:
                if self.universe_service.delete_watchlist(watchlist_id):
                    QMessageBox.information(self, "成功", "清單已刪除")
                    self._refresh_universe_list()
                else:
                    QMessageBox.warning(self, "錯誤", "刪除失敗")
            except Exception as e:
                QMessageBox.critical(self, "錯誤", f"刪除失敗: {str(e)}")

