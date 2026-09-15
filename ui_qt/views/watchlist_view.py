"""
觀察清單視圖
管理跨 Tab 共用的股票觀察清單
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QTableView, QMessageBox, QDialog,
    QDialogButtonBox, QLineEdit, QTextEdit, QListWidget,
    QListWidgetItem, QHeaderView, QMenu, QAbstractItemView,
    QGroupBox, QSplitter, QSizePolicy
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QAction
import pandas as pd
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)
from typing import List, Dict, Optional

from ui_qt.models.pandas_table_model import PandasTableModel
from app_module.watchlist_service import WatchlistService, WatchlistStorageStatus
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
from ui_qt.workers.task_worker import TaskWorker
from ui_qt.widgets.info_button import InfoButton
from ui_qt.widgets.table_style import apply_financial_table_style


class WatchlistView(QWidget):
    """觀察清單視圖"""
    
    # 信號：當觀察清單更新時發出
    watchlistUpdated = Signal()
    sendToBacktestRequested = Signal(dict)
    stockAnalysisRequested = Signal(str)
    stockResearchRequested = Signal(object)
    
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
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(8)
        main_layout.setContentsMargins(10, 10, 10, 10)
        
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
            "只在你明確按下後，將既有 JSON 複製核對至 canonical SQLite；原 JSON 不會被刪除。"
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

        # 操作區留在候選池內，讓使用者不必在三個區塊間來回尋找。
        watchlist_ops_group = QGroupBox("候選池操作")
        watchlist_ops_group.setObjectName("watchlistOpsGroup")
        watchlist_ops_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        watchlist_ops_group.setFixedHeight(64)
        self.watchlist_ops_group = watchlist_ops_group
        watchlist_ops_layout = QHBoxLayout(watchlist_ops_group)
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
        self.stocks_table.setMinimumHeight(180)
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

        # 右鍵選單
        self.stocks_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.stocks_table.customContextMenuRequested.connect(self._show_context_menu)

        candidate_layout.addWidget(self.stocks_table, stretch=1)
        self.stocks_table.doubleClicked.connect(self._open_stock_analysis)

        # 研究摘要明確標示，不再讓 QTextEdit 看起來像不明原因的第三個區塊。
        analysis_group = QGroupBox("個股研究摘要")
        analysis_group.setObjectName("watchlistResearchSummary")
        analysis_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        analysis_group.setFixedHeight(142)
        self.analysis_group = analysis_group
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
        self.stock_analysis_btn.setProperty("variant", "secondary")
        self.stock_analysis_btn.setAccessibleName("查看選中個股研究報告")
        self.stock_analysis_btn.setToolTip(
            "選取一檔股票後開啟同一份個股研究報告；也可雙擊或從右鍵選單開啟。"
        )
        # 舊的 stockAnalysisRequested signal 保留給獨立嵌入頁與既有測試；
        # MainWindow 以 stockResearchRequested 作為唯一正式報告入口。
        self.stock_research_btn = self.stock_analysis_btn
        self.stock_analysis_btn.clicked.connect(self._open_stock_analysis)
        analysis_header_layout.addWidget(self.stock_analysis_btn)
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
        self.analysis_text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.analysis_text.setFixedHeight(90)
        self.analysis_text.setPlaceholderText("選取一檔股票，查看共用呈現契約與已保存的推薦理由。")
        analysis_layout.addWidget(self.analysis_text)
        candidate_layout.addWidget(analysis_group)

        # 主要下一步與保存動作集中在候選池底部，並與資料區保持明確界線。
        next_actions_group = QGroupBox("下一步")
        next_actions_group.setObjectName("watchlistNextActions")
        next_actions_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        next_actions_group.setFixedHeight(64)
        self.next_actions_group = next_actions_group
        next_actions_layout = QHBoxLayout(next_actions_group)
        next_actions_layout.setSpacing(8)
        next_actions_layout.setContentsMargins(8, 8, 8, 8)
        self.next_actions_hint = QLabel("研究候選池，或保存成可重用的選股清單。")
        self.next_actions_hint.setProperty("role", "muted")
        next_actions_layout.addWidget(self.next_actions_hint)
        next_actions_layout.addStretch()

        self.send_to_research_lab_btn = QPushButton("送 Research Lab 批次回測")
        self.send_to_research_lab_btn.setProperty("variant", "primary")
        self.send_to_research_lab_btn.setEnabled(False)
        self.send_to_research_lab_btn.setToolTip("候選池目前沒有股票，加入股票後即可送 Research Lab 批次回測。")
        self.send_to_research_lab_btn.clicked.connect(self._send_to_research_lab)
        next_actions_layout.addWidget(self.send_to_research_lab_btn)

        self.save_to_universe_btn = QPushButton("保存為選股清單")
        self.save_to_universe_btn.setProperty("variant", "secondary")
        self.save_to_universe_btn.setToolTip("將目前候選池作為批次股票回測的輸入。")
        self.save_to_universe_btn.clicked.connect(self._save_watchlist_to_universe)
        next_actions_layout.addWidget(self.save_to_universe_btn)
        candidate_layout.addWidget(next_actions_group)

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
            self.watchlist_ops_group.setFixedHeight(64)
            self.stocks_table.setMinimumHeight(76)
            self.analysis_group.setFixedHeight(118)
            self.analysis_text.setFixedHeight(56)
            self.next_actions_group.setFixedHeight(56)
            self.universe_list.setMinimumHeight(50)
            self.universe_stock_list.setMinimumHeight(50)
            self.work_title.setVisible(False)
            self.candidate_hint.setVisible(False)
            self.universe_hint.setVisible(False)
            self.analysis_hint.setVisible(False)
            self._set_next_actions_hint_visible(False)
        else:
            self.main_splitter.setOrientation(Qt.Horizontal)
            width = max(self.width(), 1200)
            self.main_splitter.setSizes(
                [max(720, int(width * 0.68)), max(360, int(width * 0.32))]
            )
            self.watchlist_ops_group.setFixedHeight(64)
            self.stocks_table.setMinimumHeight(180)
            self.analysis_group.setFixedHeight(170)
            self.analysis_text.setFixedHeight(112)
            self.next_actions_group.setFixedHeight(64)
            self.universe_list.setMinimumHeight(100)
            self.universe_stock_list.setMinimumHeight(100)
            # 外層 QGroupBox 已提供唯一主標題，避免桌面版重複顯示「觀察候選池」。
            self.work_title.setVisible(False)
            self.candidate_hint.setVisible(True)
            self.universe_hint.setVisible(True)
            self.analysis_hint.setVisible(True)
            self._set_next_actions_hint_visible(True)

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

    def _set_next_actions_hint_visible(self, visible: bool) -> None:
        """窄版收起輔助文案，保留兩個主要動作的完整按鈕。"""

        hint = getattr(self, "next_actions_hint", None)
        if hint is not None:
            hint.setVisible(visible)

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().resizeEvent(event)
        self._apply_responsive_layout()

    @staticmethod
    def _empty_frame() -> pd.DataFrame:
        return pd.DataFrame(
            columns=["證券代號", "證券名稱", "加入時間", "來源", "備註"]
        )

    def _set_status_label(self, text: str, *, level: str) -> None:
        tone = level if level in {"info", "success", "warning", "error"} else "info"
        self.status_label.setProperty("statusTone", tone)
        style = self.status_label.style()
        if style is not None:
            style.unpolish(self.status_label)
            style.polish(self.status_label)
        self.status_label.setText(text)

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
        self.upgrade_storage_btn.setEnabled(
            status.upgrade_available and not status.is_repository
        )

    def _upgrade_watchlist_storage(self) -> None:
        """執行一次明確的 JSON→SQLite 升級，失敗時保留 JSON writer。"""

        upgrade = getattr(self.watchlist_service, "upgrade_to_repository", None)
        if not callable(upgrade):
            self._set_status_label("目前服務不支援儲存升級。", level="warning")
            return
        self.upgrade_storage_btn.setEnabled(False)
        try:
            status = upgrade()
        except Exception as exc:
            self._refresh_storage_status()
            self._set_status_label(
                f"儲存升級失敗，仍使用原 JSON：{str(exc).splitlines()[0]}",
                level="error",
            )
            return
        self._refresh_storage_status()
        if isinstance(status, WatchlistStorageStatus) and status.is_repository:
            self._set_status_label("儲存升級成功，已切換至唯一 canonical SQLite writer。", level="success")
            QMessageBox.information(self, "觀察清單儲存升級", status.message)
            self._load_watchlist()
            return
        message = (
            status.message
            if isinstance(status, WatchlistStorageStatus)
            else "升級未完成；目前仍使用原 JSON。"
        )
        self._set_status_label(message, level="warning")
        QMessageBox.warning(self, "觀察清單儲存升級未完成", message)

    def _load_watchlist(self):
        """載入觀察清單"""
        self._analysis_request_id += 1
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
                    'source': '來源',
                    'notes': '備註'
                })
                # 格式化時間
                if '加入時間' in df.columns:
                    df['加入時間'] = pd.to_datetime(df['加入時間'], errors='coerce').dt.strftime('%Y-%m-%d %H:%M')
                logger.info("[WatchlistView._load_watchlist] DataFrame 轉換完成")
            
            # 更新模型
            logger.info("[WatchlistView._load_watchlist] 創建 PandasTableModel...")
            logger.info(f"[WatchlistView._load_watchlist] DataFrame 形狀: {df.shape}")
            logger.info(f"[WatchlistView._load_watchlist] DataFrame 欄位: {list(df.columns)}")
            
            try:
                self.stocks_model = PandasTableModel(df)
                # 隱藏 tags 欄位（如果存在）
                if 'tags' in df.columns:
                    visible_cols = [col for col in df.columns if col != 'tags']
                    self.stocks_model.setVisibleColumns(visible_cols)
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
            self._update_research_lab_button_state(len(stocks))
            self._refresh_storage_status()
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
                self._update_research_lab_button_state(0)
                self._refresh_storage_status()
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
        
        # 確認對話框
        reply = QMessageBox.question(
            self, "確認", 
            f"確定要移除選中的 {len(selection)} 檔股票嗎？",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply != QMessageBox.Yes:
            return
        
        # 取得選中的股票代號
        df = self.stocks_model.getDataFrame()
        stock_codes = []
        for index in selection:
            row = index.row()
            if row < len(df):
                stock_code = df.iloc[row]['證券代號']
                stock_codes.append(stock_code)
        
        # 移除股票
        try:
            removed_count = self.watchlist_service.remove_stocks(stock_codes)
            if removed_count > 0:
                QMessageBox.information(self, "成功", f"已移除 {removed_count} 檔股票")
                self._load_watchlist()
                self.watchlistUpdated.emit()
        except Exception as e:
            QMessageBox.critical(self, "錯誤", f"移除股票失敗：\n{str(e)}")
    
    def _clear_watchlist(self):
        """清空觀察清單"""
        reply = QMessageBox.question(
            self, "確認", 
            "確定要清空整個候選池嗎？此操作無法復原。",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply != QMessageBox.Yes:
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
            self.analysis_context_label.setText(
                "狀態：尚未選取｜決策日：未知｜資料日：未知｜來源：未知"
            )
            self.analysis_text.setPlainText("請選取一檔股票查看分析摘要。")
            return
        row = self.stocks_model.getDataFrame().iloc[rows[0].row()]
        code = str(row["證券代號"]).strip()
        source = row.get("source_id", "")
        source_id = source.strip() if isinstance(source, str) else ""
        self._request_stock_summary(code, source_id, request_id)

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

    def closeEvent(self, event):
        self._analysis_request_id += 1
        super().closeEvent(event)

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
        if code:
            source_value = row.get("source_id", "")
            source_id = source_value.strip() if isinstance(source_value, str) else ""
            self.stockAnalysisRequested.emit(code)
            self.stockResearchRequested.emit(
                self._build_stock_research_context(
                    code,
                    str(row.get("證券名稱", "") or "").strip(),
                    source_id,
                )
            )

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
    ) -> ResearchStockContextDTO:
        """從觀察清單的保存來源建立唯讀上下文，不重新計算。"""

        code = str(stock_code).strip()
        source = str(source_id or "").strip()
        result = None
        if self.analysis_service is not None and source:
            try:
                cutoff = datetime.now(ZoneInfo("Asia/Taipei")).date()
                result = self.analysis_service.fetch(code, source, cutoff)
            except Exception as error:
                logger.warning("[WatchlistView] 讀取保存來源 metadata 失敗：%s", error)

        result_id = str(getattr(result, "result_id", "") or source)
        decision_date = str(
            getattr(result, "decision_date", "")
            or getattr(result, "analysis_date", "")
            or ""
        )
        data_date = str(getattr(result, "data_date", "") or "")
        profile_id = str(getattr(result, "profile_id", "") or "")
        profile_version = str(getattr(result, "profile_version", "") or "")
        lineage_id = str(getattr(result, "source_id", "") or "")
        return ResearchStockContextDTO(
            stock_code=code,
            stock_name=stock_name,
            decision_date=decision_date,
            data_date=data_date,
            result_id=result_id,
            profile_id=profile_id,
            profile_version=profile_version,
            source_id=source or lineage_id,
            source_kind=str(getattr(result, "source_kind", "") or "recommendation"),
            source_label=("已保存推薦結果" if result_id else "觀察清單"),
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
                    source = str(frame.iloc[row_number].get("source_id", "") or "").strip()
                    if source and source != str(result_id).strip():
                        return False
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
            
            if stock_code:
                stocks.append({
                    'stock_code': str(stock_code),
                    'stock_name': str(stock_name),
                    'notes': '',
                    'source_id': source_id
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

