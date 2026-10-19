from __future__ import annotations

import re
from pathlib import Path
from collections.abc import Callable
from datetime import date, datetime
from typing import cast

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QBoxLayout,
    QAbstractItemView,
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTabWidget,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from app_module.workbench_dtos import (
    WORKBENCH_LEGACY_DRILLDOWN_TARGETS,
    WorkbenchDashboardDTO,
    WorkbenchDailyEvidence,
    WorkbenchEvidenceSummary,
    ResearchFallbackPacket,
)
from app_module.machine_status_classification import (
    MACHINE_STATUS_HUMAN_REVIEW,
    MACHINE_STATUS_INVALID_EVIDENCE,
    MACHINE_STATUS_MACHINE_CANDIDATE,
    MACHINE_STATUS_MACHINE_DEGRADED,
    MACHINE_STATUS_SOURCE_MISSING,
    MACHINE_STATUS_STALE,
    MACHINE_STATUS_UNKNOWN,
    MACHINE_STATUS_WAITING_FOR_TIME,
)
from app_module.engineering_closure_dashboard_service import EvidenceRehearsalDashboard
from app_module.workbench_source_service import WorkbenchSourceService
from app_module.recommendation_learning_evidence_projection_service import (
    RecommendationLearningEvidenceProjectionService,
)
from app_module.research_console_source_service import ResearchConsoleSourceService
from app_module.advice_dtos import AdviceClassification
from app_module.decision_presentation import (
    DecisionPresentationService,
    PositionHealthReadModel,
    format_decision_lineage_detail,
    format_decision_presentation,
    format_position_health_presentation,
    format_position_health_read_model,
)
from app_module.research_session import ResearchStockContextDTO, format_research_workflow_path
from app_module.theme_research_presentation import build_theme_research_presentation
from app_module.theme_research_snapshot import ThemeResearchSnapshot
from ui_qt.models.workbench_table_models import (
    AdvicePortfolioTableModel,
    AdviceCandidateTableModel,
    AdviceRecommendationTableModel,
    GuidedWorkbenchRow,
    WorkbenchActionItemTableModel,
    WorkbenchChecklistTableModel,
    WorkbenchEvidenceFeedTableModel,
    WorkbenchEvidenceTableModel,
    WorkbenchGuidedSummaryTableModel,
    WorkbenchOperatingLoopTableModel,
    WorkbenchReviewQueueTableModel,
    WorkbenchStatusStripTableModel,
    PositionHealthTableModel,
    display_workbench_value,
)
from ui_qt.theme import MIDNIGHT_ANALYST
from ui_qt.widgets.layout_helpers import set_scroll_content_constraints
from ui_qt.widgets.info_button import InfoButton
from ui_qt.widgets.table_style import apply_financial_table_style
from ui_qt.widgets.theme_widgets import (
    CollapsibleSectionPanel,
    EmptyStatePanel,
    SectionPanel,
    StatusBadge,
    WarningList,
    TimelineCard,
    StatusCard,
    MetricCard,
)
from ui_qt.views.workbench_presenter import (
    action_item_state_text as _action_item_state_text,
    evidence_feed_state_text as _evidence_feed_state_text,
    operating_loop_state_text as _operating_loop_state_text,
    review_queue_state_text,
)
from ui_qt.views.research_console_view import ResearchConsoleView
from ui_qt.workers.task_worker import TaskWorker

WORKBENCH_TONES: dict[str, dict[str, str]] = {
    "ready": {"fg": "#22c55e", "bg": "#0d2116", "border": "#166534"},
    "observed": {"fg": "#22c55e", "bg": "#0d2116", "border": "#166534"},
    "passed": {"fg": "#22c55e", "bg": "#0d2116", "border": "#166534"},
    "done": {"fg": "#22c55e", "bg": "#0d2116", "border": "#166534"},
    "info": {"fg": "#38bdf8", "bg": "#0b1c27", "border": "#075985"},
    "manual_observed": {"fg": "#38bdf8", "bg": "#0b1c27", "border": "#075985"},
    "warning": {"fg": "#f59e0b", "bg": "#221a10", "border": "#92400e"},
    "degraded": {"fg": "#f59e0b", "bg": "#221a10", "border": "#92400e"},
    "waiting_for_time": {"fg": "#f59e0b", "bg": "#221a10", "border": "#92400e"},
    "manual_required": {"fg": "#f59e0b", "bg": "#221a10", "border": "#92400e"},
    "action_required": {"fg": "#f59e0b", "bg": "#221a10", "border": "#92400e"},
    "critical": {"fg": "#ef4444", "bg": "#2a1114", "border": "#991b1b"},
    "blocked": {"fg": "#ef4444", "bg": "#2a1114", "border": "#991b1b"},
    "missing": {"fg": "#ef4444", "bg": "#2a1114", "border": "#991b1b"},
    "source_missing": {"fg": "#ef4444", "bg": "#2a1114", "border": "#991b1b"},
    "invalid_evidence": {"fg": "#ef4444", "bg": "#2a1114", "border": "#991b1b"},
    "machine_candidate": {"fg": "#f59e0b", "bg": "#221a10", "border": "#92400e"},
    "machine_degraded": {"fg": "#f59e0b", "bg": "#221a10", "border": "#92400e"},
    "candidate": {"fg": "#f59e0b", "bg": "#221a10", "border": "#92400e"},
    "candidate_degraded": {"fg": "#f59e0b", "bg": "#221a10", "border": "#92400e"},
    "challenger_candidate": {"fg": "#f59e0b", "bg": "#221a10", "border": "#92400e"},
    "active_model": {"fg": "#22c55e", "bg": "#0d2116", "border": "#166534"},
    "future_blocked": {"fg": "#ef4444", "bg": "#2a1114", "border": "#991b1b"},
    "stale": {"fg": "#f59e0b", "bg": "#221a10", "border": "#92400e"},
    "unknown": {"fg": "#94a3b8", "bg": "#111827", "border": "#334155"},
    "off": {"fg": "#94a3b8", "bg": "#111827", "border": "#334155"},
    "neutral": {"fg": "#94a3b8", "bg": "#111827", "border": "#334155"},
}


def _inspect_workbench_dashboard(
    source_service: WorkbenchSourceService,
    decision_date: str | None,
    replay_summary_json: str | Path | None,
    *,
    cancel_callback: Callable[[], bool] | None = None,
) -> WorkbenchDashboardDTO:
    """在 TaskWorker 中讀取 Workbench 唯讀 DTO。"""

    return source_service.inspect(
        decision_date=decision_date,
        replay_summary_json=replay_summary_json,
        cancel_callback=cancel_callback,
    )


class UnifiedDecisionWorkbenchView(QWidget):
    """Read-only Unified Decision Workbench shell backed only by Workbench DTOs."""

    def __init__(
        self,
        *,
        source_service: WorkbenchSourceService | None = None,
        dashboard: WorkbenchDashboardDTO | None = None,
        decision_date: str | None = None,
        replay_summary_json: str | Path | None = None,
        evidence_rehearsal_dashboard: EvidenceRehearsalDashboard | None = None,
        research_console_source_service: ResearchConsoleSourceService | None = None,
        learning_projection_service: RecommendationLearningEvidenceProjectionService | None = None,
        legacy_learning_projection_service: RecommendationLearningEvidenceProjectionService | None = None,
        auto_refresh: bool = True,
        async_refresh: bool = False,
        decision_source_widget: QWidget | None = None,
        navigate_to_daily_decision_callback: Callable[[], None] | None = None,
        navigate_to_market_explore_callback: Callable[[], None] | None = None,
        navigate_to_evidence_review_callback: Callable[[], None] | None = None,
        navigate_to_portfolio_callback: Callable[[], None] | None = None,
        navigate_to_portfolio_position_callback: Callable[[PositionHealthReadModel, str], object] | None = None,
        navigate_to_watchlist_callback: Callable[[], None] | None = None,
        navigate_to_stock_research_callback: Callable[[object], None] | None = None,
        navigate_to_update_callback: Callable[[], None] | None = None,
        navigate_to_recommendation_callback: Callable[[], None] | None = None,
        navigate_to_industry_themes_callback: Callable[[], None] | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.source_service = source_service
        self.decision_date = decision_date
        self._async_refresh = bool(async_refresh)
        self._refresh_worker: TaskWorker | None = None
        self._refresh_generation = 0
        self._refresh_pending = False
        self._shutdown_requested = False
        self.replay_summary_json = replay_summary_json
        self.evidence_rehearsal_dashboard = evidence_rehearsal_dashboard
        self.research_console_source_service = (
            research_console_source_service or ResearchConsoleSourceService()
        )
        self.learning_projection_service = (
            learning_projection_service
            or getattr(self.source_service, "learning_evidence_projection_service", None)
        )
        self.legacy_learning_projection_service = legacy_learning_projection_service
        self.navigate_to_daily_decision_callback = navigate_to_daily_decision_callback
        self.navigate_to_market_explore_callback = navigate_to_market_explore_callback
        self.navigate_to_evidence_review_callback = navigate_to_evidence_review_callback
        self.navigate_to_portfolio_callback = navigate_to_portfolio_callback
        self.navigate_to_portfolio_position_callback = navigate_to_portfolio_position_callback
        self._position_health_navigation_source: PositionHealthReadModel | None = None
        self._position_health_navigation_id: str | None = None
        self.navigate_to_watchlist_callback = navigate_to_watchlist_callback
        self.navigate_to_stock_research_callback = navigate_to_stock_research_callback
        self.navigate_to_update_callback = navigate_to_update_callback
        self.navigate_to_recommendation_callback = navigate_to_recommendation_callback
        self.navigate_to_industry_themes_callback = (
            navigate_to_industry_themes_callback
        )
        self._theme_research_snapshot: ThemeResearchSnapshot | None = None
        self._dashboard: WorkbenchDashboardDTO | None = None
        self._last_good_dashboard: WorkbenchDashboardDTO | None = None
        self._last_good_dashboard_loaded_at: datetime | None = None
        self._dashboard_stale = False
        self._viewed_review_item_ids: set[str] = set()
        self._workbench_narrow = False
        self.presentation_service = DecisionPresentationService()
        self._selected_advice_presentation = None
        self._daily_candidate_selection_identity: tuple[object, ...] | None = None

        self.status_model = WorkbenchStatusStripTableModel()
        self.review_model = WorkbenchReviewQueueTableModel()
        self.evidence_feed_model = WorkbenchEvidenceFeedTableModel()
        self.action_item_model = WorkbenchActionItemTableModel()
        self.operating_loop_model = WorkbenchOperatingLoopTableModel()
        self.evidence_model = WorkbenchEvidenceTableModel()
        self.checklist_model = WorkbenchChecklistTableModel()
        self.advice_recommendation_model = AdviceRecommendationTableModel()
        self.advice_candidate_model = AdviceCandidateTableModel()
        self.advice_portfolio_model = AdvicePortfolioTableModel()
        self.position_health_model = PositionHealthTableModel()
        self.guided_summary_model = WorkbenchGuidedSummaryTableModel()

        self._setup_ui()
        self._render_evidence_rehearsal_dashboard(self.evidence_rehearsal_dashboard)
        if dashboard is not None:
            self.render_dashboard(dashboard)
        elif auto_refresh and self.source_service is not None:
            if self._async_refresh:
                QTimer.singleShot(0, self.refresh_dashboard)
            else:
                self.refresh_dashboard()
        else:
            self._display_pending_dashboard()

    def set_theme_research_snapshot(
        self, snapshot: ThemeResearchSnapshot | None
    ) -> None:
        """只呈現 Main 已持有的題材版本摘要，不重新讀取來源。"""

        if snapshot is not None and not isinstance(
            snapshot, ThemeResearchSnapshot
        ):
            raise TypeError("snapshot 必須是 ThemeResearchSnapshot 或 None")
        self._theme_research_snapshot = snapshot
        if snapshot is None:
            self.home_theme_summary_label.setText(
                "尚未載入題材研究版本；請先到「產業與題材」選取本機已保存版本。"
            )
            self.home_theme_summary_label.setToolTip("")
            return

        presentation = build_theme_research_presentation(snapshot)
        chain_count = len(presentation.chains)
        theme_count = sum(len(chain.themes) for chain in presentation.chains)
        self.home_theme_summary_label.setText(
            f"目前所選題材版本：資料日 {snapshot.report.data_date.isoformat()}；"
            f"涵蓋 {chain_count} 條產業鏈／{theme_count} 個題材。"
        )
        self.home_theme_summary_label.setToolTip(
            f"版本 identity SHA-256：{snapshot.identity_sha256}"
        )

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(12, 12, 12, 12)

        self.subtabs = QTabWidget()
        layout.addWidget(self.subtabs)

        overview_page = QWidget()
        overview_layout = QVBoxLayout(overview_page)
        overview_layout.setSpacing(10)
        overview_layout.setContentsMargins(12, 12, 12, 12)
        self.overview_layout = overview_layout

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.setFrameShape(QScrollArea.NoFrame)
        self.overview_scroll_area = scroll_area
        scroll_content = QWidget()
        scroll_content.setMinimumWidth(0)
        content_layout = QVBoxLayout(scroll_content)
        content_layout.setSpacing(10)
        content_layout.setContentsMargins(0, 0, 0, 0)
        root_content_layout = content_layout

        title_layout = QHBoxLayout()
        title = QLabel("決策工作台")
        title_font = QFont()
        title_font.setPointSize(17)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setStyleSheet(f"color: {MIDNIGHT_ANALYST.text_primary};")
        title_layout.addWidget(title)
        title_layout.addStretch()
        title_layout.addWidget(InfoButton("workbench", self))
        content_layout.addLayout(title_layout)

        self._build_guided_home(root_content_layout)
        self.advanced_workbench_panel = CollapsibleSectionPanel(
            "完整工作台／所有來源與進階詳情",
            collapsed=True,
        )
        self.advanced_workbench_panel.setObjectName("v5AdvancedWorkbench")
        self.advanced_workbench_panel.toggle_button.setAccessibleName("展開完整工作台")
        self.advanced_workbench_panel.toggle_button.setToolTip(
            "查看完整 workflow、原始表格、來源追蹤與技術詳情；不會重新取得或重算資料。"
        )
        self.advanced_overview_layout = self.advanced_workbench_panel.content_layout
        content_layout = self.advanced_overview_layout

        workflow_panel = CollapsibleSectionPanel(
            "單一路徑 / Research Workflow",
            collapsed=True,
        )
        self.workflow_collapsible = workflow_panel
        self.workflow_section_title = workflow_panel.title_label
        self.workflow_path_label = QLabel(
            "路徑：" + format_research_workflow_path()
        )
        self.workflow_path_label.setWordWrap(True)
        self.workflow_path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.workflow_path_label.setStyleSheet(
            f"color: {MIDNIGHT_ANALYST.text_secondary}; font-size: 11px;"
        )
        workflow_panel.content_layout.addWidget(self.workflow_path_label)
        workflow_path_layout = QHBoxLayout()
        workflow_path_layout.setContentsMargins(0, 0, 0, 0)
        workflow_path_layout.setSpacing(6)
        self.workflow_path_layout = workflow_path_layout
        self.workflow_path_buttons: dict[str, QPushButton] = {}
        for key, label, callback, tooltip in (
            (
                "market",
                "1 市場總覽",
                self.navigate_to_daily_decision_callback,
                "前往市場總覽，確認市場與風險焦點。",
            ),
            (
                "industry",
                "2 產業探索",
                self.navigate_to_market_explore_callback,
                "前往市場探索，人工比對產業與關鍵股。",
            ),
            (
                "watchlist",
                "4 觀察清單",
                self.navigate_to_watchlist_callback,
                "前往觀察清單，查看研究／等待／買進候選的來源理由。",
            ),
            (
                "portfolio",
                "5 持倉覆盤",
                self.navigate_to_portfolio_callback,
                "前往持倉管理，查看持有／減碼／退出候選與權重差距。",
            ),
        ):
            button = QPushButton(label)
            button.setProperty("variant", "secondary")
            button.setToolTip(tooltip)
            button.setAccessibleName(label)
            button.setEnabled(callback is not None)
            if callback is not None:
                button.clicked.connect(callback)
            workflow_path_layout.addWidget(button)
            self.workflow_path_buttons[key] = button
        workflow_path_layout.addStretch()
        workflow_panel.content_layout.addLayout(workflow_path_layout)
        self.workflow_path_note = self._make_state_label()
        self.workflow_path_note.setText(
            "第 3 段『個股研究』可由每日候選直接開啟，也可從市場焦點、觀察清單或持倉列選取；"
            "此處不自動新增候選，也不自動下單。"
        )
        workflow_panel.content_layout.addWidget(self.workflow_path_note)
        content_layout.addWidget(workflow_panel)

        self._build_daily_investment_journey(content_layout)
        self._build_today_action_center(content_layout)

        self.priority_banner = QLabel("")
        self.priority_banner.setWordWrap(True)
        self.priority_banner.setTextInteractionFlags(Qt.TextSelectableByMouse)
        content_layout.addWidget(self.priority_banner)

        self.summary_blocks: dict[str, QWidget] = {}
        self.summary_value_labels: dict[str, QLabel] = {}
        self.summary_detail_labels: dict[str, QLabel] = {}
        summary_row = QWidget()
        summary_layout = QHBoxLayout(summary_row)
        summary_layout.setContentsMargins(0, 0, 0, 0)
        summary_layout.setSpacing(8)
        self.summary_layout = summary_layout
        for key, label in (
            ("review", "今日待判讀"),
            ("action", "人工待處理"),
            ("waiting", "等待真實時間"),
            ("warning", "警告"),
        ):
            summary_layout.addWidget(self._make_summary_block(key, label), 1)
        content_layout.addWidget(summary_row)

        self.boundary_banner = QLabel("")
        self.boundary_banner.setWordWrap(True)
        self.boundary_banner.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.boundary_banner.setStyleSheet(
            f"background: {MIDNIGHT_ANALYST.surface_2}; color: {MIDNIGHT_ANALYST.text_secondary}; "
            f"border: 1px solid {MIDNIGHT_ANALYST.border}; "
            f"border-radius: {MIDNIGHT_ANALYST.radius_panel}px; padding: 8px;"
        )
        content_layout.addWidget(self.boundary_banner)

        advice_panel, self.advice_section_title = self._panel_with_title("今日 Advice 與研究候選")
        self.advice_summary = self._make_state_label()
        self.advice_recommendation_table = self._make_table(self.advice_recommendation_model)
        self.advice_candidate_table = self._make_table(self.advice_candidate_model)
        self.advice_portfolio_table = self._make_table(self.advice_portfolio_model)
        self.advice_recommendation_table.clicked.connect(
            lambda index: self._show_advice_row_presentation(
                self.advice_recommendation_model, index.row()
            )
        )
        self.advice_candidate_table.clicked.connect(
            lambda index: self._show_advice_row_presentation(
                self.advice_candidate_model, index.row()
            )
        )
        self.advice_portfolio_table.clicked.connect(
            lambda index: self._show_advice_row_presentation(
                self.advice_portfolio_model, index.row()
            )
        )
        advice_panel.layout.addWidget(self.advice_summary)
        advice_panel.layout.addWidget(self.advice_recommendation_table)
        self.advice_candidate_label = QLabel("Professional 研究候選（不屬於正式 Advice）")
        advice_panel.layout.addWidget(self.advice_candidate_label)
        advice_panel.layout.addWidget(self.advice_candidate_table)
        advice_panel.layout.addWidget(self.advice_portfolio_table)
        self.advice_presentation_detail = self._make_state_label()
        self.advice_presentation_detail.setObjectName("advicePresentationDetail")
        self.advice_presentation_detail.setText(
            "共用證據詳情：選取 Advice 或研究候選列後顯示；"
            "排名分數、校準機率與成本後獲利機率不互相代換。"
        )
        self.advice_lineage_button = QPushButton("查看機率依據")
        self.advice_lineage_button.setProperty("variant", "secondary")
        self.advice_lineage_button.setCheckable(True)
        self.advice_lineage_button.setEnabled(False)
        self.advice_lineage_button.setAccessibleName("查看機率依據")
        self.advice_lineage_button.setToolTip(
            "展開目前選取列的完整模型／資料集／來源追溯與 hash；唯讀，不會修改 Advice。"
        )
        self.advice_lineage_button.toggled.connect(self._toggle_advice_lineage)
        advice_panel.layout.addWidget(self.advice_lineage_button)
        advice_panel.layout.addWidget(self.advice_presentation_detail)

        # 建立三態空狀態 Widget 及其唯讀導引
        self.advice_empty_widget = QWidget()
        self.advice_empty_layout = QVBoxLayout(self.advice_empty_widget)
        self.advice_empty_layout.setContentsMargins(0, 0, 0, 0)
        self.advice_empty_label = QLabel("")
        self.advice_empty_label.setWordWrap(True)
        self.advice_empty_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.advice_empty_label.setStyleSheet("padding: 10px; background-color: #1e293b; color: #cbd5e1; border-radius: 6px; border: 1px solid #334155;")
        self.advice_empty_layout.addWidget(self.advice_empty_label)

        # 唯讀導引按鈕列
        nav_buttons_row = QHBoxLayout()
        self.nav_to_update_btn = QPushButton("前往數據更新工作台")
        self.nav_to_update_btn.setProperty("variant", "secondary")
        self.nav_to_update_btn.clicked.connect(lambda: self.navigate_to_drilldown_target("update"))

        self.nav_to_recommend_btn = QPushButton("前往推薦分析工作區")
        self.nav_to_recommend_btn.setProperty("variant", "secondary")
        self.nav_to_recommend_btn.clicked.connect(lambda: self.navigate_to_drilldown_target("recommendation"))

        nav_buttons_row.addWidget(self.nav_to_update_btn)
        nav_buttons_row.addWidget(self.nav_to_recommend_btn)
        nav_buttons_row.addStretch()
        self.advice_empty_layout.addLayout(nav_buttons_row)

        advice_panel.layout.addWidget(self.advice_empty_widget)
        self.advice_empty_widget.setVisible(False)

        content_layout.addWidget(advice_panel)

        position_health_panel, self.position_health_section_title = self._panel_with_title(
            "持倉健康／退出候選 / Paper Position Health"
        )
        self.position_health_panel = position_health_panel
        self.position_health_summary_label = self._make_state_label()
        self.position_health_table = self._make_table(self.position_health_model)
        self.position_health_table.clicked.connect(self._show_position_health_row)
        self.position_health_table.selectionModel().currentRowChanged.connect(
            lambda current, _previous: self._show_position_health_row(current)
        )
        self.position_health_open_portfolio_button = QPushButton("在持倉管理查看此 Paper 部位")
        self.position_health_open_portfolio_button.setEnabled(False)
        self.position_health_open_portfolio_button.setToolTip(
            "先明選部位；持倉頁重新讀取後，帳本、日期與來源版本相同才定位。"
        )
        self.position_health_open_portfolio_button.clicked.connect(
            self._open_selected_position_health
        )
        self.position_health_detail_button = QPushButton("查看 Position Health 技術詳情")
        self.position_health_detail_button.setProperty("variant", "secondary")
        self.position_health_detail_button.setCheckable(True)
        self.position_health_detail_button.setAccessibleName("查看 Position Health 技術詳情")
        self.position_health_detail_button.setToolTip(
            "展開來源 hash、available_at、identity、why／why-not 與安全邊界；唯讀。"
        )
        self.position_health_detail_button.toggled.connect(
            self._toggle_position_health_detail
        )
        self.position_health_detail_label = self._make_detail_box()
        self.position_health_detail_label.setVisible(False)
        position_health_panel.layout.addWidget(self.position_health_summary_label)
        position_health_panel.layout.addWidget(self.position_health_table)
        position_health_panel.layout.addWidget(self.position_health_open_portfolio_button)
        position_health_panel.layout.addWidget(self.position_health_detail_button)
        position_health_panel.layout.addWidget(self.position_health_detail_label)
        content_layout.addWidget(position_health_panel)

        drilldown_panel, self.drilldown_section_title = self._panel_with_title("操作下鑽 / Drill-down")
        drilldown_layout = QHBoxLayout()
        drilldown_layout.setContentsMargins(0, 0, 0, 0)
        drilldown_layout.setSpacing(8)
        self.drilldown_layout = drilldown_layout
        self.daily_decision_button = self._make_drilldown_button(
            "開啟市場總覽",
            self.navigate_to_daily_decision_callback,
            "切到市場探索的唯一市場總覽；Workbench 不持有第二份 Decision Desk。",
        )
        self.market_explore_button = self._make_drilldown_button(
            "開啟市場探索",
            self.navigate_to_market_explore_callback,
            "切到市場探索工作區，供人工研究與比對。",
        )
        self.evidence_review_button = self._make_drilldown_button(
            "開啟證據覆盤",
            self.navigate_to_evidence_review_callback,
            "切到策略回測內的證據覆盤，不啟用排程器。",
        )
        self.portfolio_button = self._make_drilldown_button(
            "開啟持倉管理",
            self.navigate_to_portfolio_callback,
            "切到持倉管理頁做人工覆盤，不產生買賣建議。",
        )
        drilldown_layout.addWidget(self.daily_decision_button)
        drilldown_layout.addWidget(self.market_explore_button)
        drilldown_layout.addWidget(self.evidence_review_button)
        drilldown_layout.addWidget(self.portfolio_button)
        drilldown_layout.addStretch()
        drilldown_panel.layout.addLayout(drilldown_layout)
        content_layout.addWidget(drilldown_panel)

        meta_panel, self.meta_section_title = self._panel_with_title("資料來源 / Workbench Source")
        self.meta_label = QLabel("")
        self.meta_label.setWordWrap(True)
        self.meta_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        meta_panel.layout.addWidget(self.meta_label)
        content_layout.addWidget(meta_panel)

        status_panel, self.status_section_title = self._panel_with_title("狀態列 / Status Strip")
        self.status_table = self._make_table(self.status_model)
        status_panel.layout.addWidget(self.status_table)
        content_layout.addWidget(status_panel)

        primary_area = QWidget()
        primary_layout = QHBoxLayout(primary_area)
        primary_layout.setContentsMargins(0, 0, 0, 0)
        primary_layout.setSpacing(10)
        self.primary_layout = primary_layout
        primary_area.setMinimumWidth(0)
        list_column = QWidget()
        list_layout = QVBoxLayout(list_column)
        list_layout.setContentsMargins(0, 0, 0, 0)
        list_layout.setSpacing(10)

        review_panel, self.review_section_title = self._panel_with_title("今日待判讀 / Today Review Queue")
        self.review_panel = review_panel
        self.review_state_label = self._make_state_label()
        self.review_empty_state = EmptyStatePanel(
            "目前沒有明確人工判讀項目",
            "今日待判讀佇列目前為空；請查看背景證據流與每日檢查清單。空佇列不代表風險已確認。",
        )
        self.review_table = self._make_table(self.review_model)
        self.review_table.clicked.connect(lambda index: self._show_model_row_detail(self.review_model, index.row()))
        self.review_table.doubleClicked.connect(
            lambda index: self._navigate_model_row(self.review_model, index.row())
        )
        review_panel.layout.addWidget(self.review_state_label)
        review_panel.layout.addWidget(self.review_empty_state)
        review_panel.layout.addWidget(self.review_table)
        list_layout.addWidget(review_panel)

        evidence_feed_panel, self.evidence_feed_section_title = self._panel_with_title(
            "背景證據流 / Background Evidence Feed"
        )
        self.evidence_feed_state_label = self._make_state_label()
        self.evidence_feed_table = self._make_table(self.evidence_feed_model)
        self.evidence_feed_table.clicked.connect(
            lambda index: self._show_model_row_detail(self.evidence_feed_model, index.row())
        )
        self.evidence_feed_table.doubleClicked.connect(
            lambda index: self._navigate_model_row(self.evidence_feed_model, index.row())
        )
        evidence_feed_panel.layout.addWidget(self.evidence_feed_state_label)
        evidence_feed_panel.layout.addWidget(self.evidence_feed_table)
        list_layout.addWidget(evidence_feed_panel)

        action_item_panel, self.action_item_section_title = self._panel_with_title(
            "只讀 Action Items / Machine + Manual Queue"
        )
        self.action_item_panel = action_item_panel
        self.action_item_state_label = self._make_state_label()
        self.action_item_table = self._make_table(self.action_item_model)
        self.action_item_table.clicked.connect(
            lambda index: self._show_model_row_detail(self.action_item_model, index.row())
        )
        self.action_item_table.doubleClicked.connect(
            lambda index: self._navigate_model_row(self.action_item_model, index.row())
        )
        action_item_panel.layout.addWidget(self.action_item_state_label)
        action_item_panel.layout.addWidget(self.action_item_table)
        list_layout.addWidget(action_item_panel)

        detail_panel, self.detail_section_title = self._panel_with_title("詳情檢視 / Inspector")
        detail_panel.setMinimumWidth(0)
        self.detail_panel = detail_panel
        self.detail_title_label = QLabel("尚未選取項目")
        detail_title_font = QFont()
        detail_title_font.setPointSize(13)
        detail_title_font.setBold(True)
        self.detail_title_label.setFont(detail_title_font)
        self.detail_title_label.setWordWrap(True)
        self.detail_title_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.detail_title_label.setStyleSheet(f"color: {MIDNIGHT_ANALYST.text_primary};")
        self.detail_status_label = QLabel("")
        self.detail_status_label.setWordWrap(True)
        self.detail_status_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.detail_status_label.setStyleSheet(
            f"color: {MIDNIGHT_ANALYST.text_secondary}; font-weight: 700;"
        )
        self.detail_body_label = QLabel("")
        self.detail_body_label.setWordWrap(True)
        self.detail_body_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.detail_body_label.setStyleSheet(
            f"background: {MIDNIGHT_ANALYST.surface_2}; color: {MIDNIGHT_ANALYST.text_secondary}; "
            f"border: 1px solid {MIDNIGHT_ANALYST.border}; "
            f"border-radius: {MIDNIGHT_ANALYST.radius_panel}px; padding: 10px; line-height: 135%;"
        )
        self.detail_drilldown_button = QPushButton("開啟下鑽")
        self.detail_drilldown_button.setProperty("variant", "secondary")
        self.detail_drilldown_button.clicked.connect(self._open_selected_detail_target)
        self._selected_detail_target = ""
        self._selected_detail_item = None
        detail_panel.layout.addWidget(self.detail_title_label)
        detail_header_row = QWidget()
        detail_header_layout = QHBoxLayout(detail_header_row)
        detail_header_layout.setContentsMargins(0, 0, 0, 0)
        detail_header_layout.setSpacing(8)
        self.detail_status_badge = QLabel("")
        self.detail_status_badge.setAlignment(Qt.AlignCenter)
        self.detail_status_badge.setMinimumHeight(26)
        detail_header_layout.addWidget(self.detail_status_badge, 0)
        detail_header_layout.addWidget(self.detail_status_label, 1)
        detail_panel.layout.addWidget(detail_header_row)

        self.detail_summary_box = self._make_detail_box()
        self.detail_source_box = self._make_detail_box()
        self.detail_diagnostics_box = self._make_detail_box()
        detail_panel.layout.addWidget(self.detail_summary_box)
        detail_panel.layout.addWidget(self.detail_source_box)
        detail_panel.layout.addWidget(self.detail_diagnostics_box)
        self.detail_body_label.setVisible(False)
        self.detail_technical_button = QPushButton("查看技術欄位（DTO raw）")
        self.detail_technical_button.setProperty("variant", "secondary")
        self.detail_technical_button.setCheckable(True)
        self.detail_technical_button.setAccessibleName("查看 Workbench 技術欄位")
        self.detail_technical_button.setAccessibleDescription(
            "展開既有 DTO 的來源追蹤、診斷、代碼與欄位可用性；不會執行查詢或計算。"
        )
        self.detail_technical_button.toggled.connect(self._toggle_detail_technical)
        detail_panel.layout.addWidget(self.detail_drilldown_button)
        detail_panel.layout.insertWidget(
            detail_panel.layout.indexOf(self.detail_drilldown_button),
            self.detail_body_label,
        )
        detail_panel.layout.insertWidget(
            detail_panel.layout.indexOf(self.detail_drilldown_button),
            self.detail_technical_button,
        )
        detail_panel.layout.addStretch()

        primary_layout.addWidget(list_column, 3)
        primary_layout.addWidget(detail_panel, 2)
        content_layout.addWidget(primary_area)

        operating_loop_panel = CollapsibleSectionPanel(
            "操作節奏 / Read-only Operating Loop",
            collapsed=True,
        )
        self.operating_loop_collapsible = operating_loop_panel
        self.operating_loop_section_title = operating_loop_panel.title_label
        self.operating_loop_state_label = self._make_state_label()
        self.operating_loop_list = QWidget()
        self.operating_loop_list_layout = QVBoxLayout(self.operating_loop_list)
        self.operating_loop_list_layout.setContentsMargins(0, 0, 0, 0)
        self.operating_loop_list_layout.setSpacing(6)
        operating_loop_panel.content_layout.addWidget(self.operating_loop_state_label)
        operating_loop_panel.content_layout.addWidget(self.operating_loop_list)
        content_layout.addWidget(operating_loop_panel)

        evidence_panel = CollapsibleSectionPanel("證據與品質 / Evidence Mode", collapsed=True)
        self.evidence_collapsible = evidence_panel
        self.evidence_section_title = evidence_panel.title_label

        self.evidence_summary_row = QWidget()
        evidence_summary_layout = QHBoxLayout(self.evidence_summary_row)
        evidence_summary_layout.setContentsMargins(0, 0, 0, 0)
        evidence_summary_layout.setSpacing(10)
        self.evidence_summary_layout = evidence_summary_layout
        self.evidence_boundary_card = MetricCard("邊界與 Gate 摘要", "")
        self.evidence_coverage_card = MetricCard("覆蓋率與缺口", "")
        self.evidence_boundary_card.value_label.setStyleSheet(
            f"color: {MIDNIGHT_ANALYST.text_secondary}; font-size: 12px; "
            "font-weight: normal; line-height: 145%;"
        )
        self.evidence_coverage_card.value_label.setStyleSheet(
            f"color: {MIDNIGHT_ANALYST.text_secondary}; font-size: 12px; "
            "font-weight: normal; line-height: 145%;"
        )
        self.evidence_boundary_card.value_label.setWordWrap(True)
        self.evidence_coverage_card.value_label.setWordWrap(True)
        evidence_summary_layout.addWidget(self.evidence_boundary_card, 1)
        evidence_summary_layout.addWidget(self.evidence_coverage_card, 1)

        self.evidence_table = self._make_table(self.evidence_model)
        self.evidence_table.clicked.connect(lambda index: self._show_model_row_detail(self.evidence_model, index.row()))
        evidence_panel.content_layout.addWidget(self.evidence_summary_row)
        evidence_panel.content_layout.addWidget(self.evidence_table)
        content_layout.addWidget(evidence_panel)

        rehearsal_panel, self.evidence_rehearsal_section_title = self._panel_with_title(
            "工程預演狀態 / Evidence Rehearsal"
        )
        self.evidence_rehearsal_summary_label = self._make_state_label()
        self.evidence_rehearsal_detail_label = self._make_state_label()
        rehearsal_panel.layout.addWidget(self.evidence_rehearsal_summary_label)
        rehearsal_panel.layout.addWidget(self.evidence_rehearsal_detail_label)
        content_layout.addWidget(rehearsal_panel)

        checklist_panel = CollapsibleSectionPanel("每日檢查清單 / Daily Checklist", collapsed=True)
        self.checklist_collapsible = checklist_panel
        self.checklist_section_title = checklist_panel.title_label
        self.checklist_list = QWidget()
        self.checklist_list_layout = QVBoxLayout(self.checklist_list)
        self.checklist_list_layout.setContentsMargins(0, 0, 0, 0)
        self.checklist_list_layout.setSpacing(6)
        checklist_panel.content_layout.addWidget(self.checklist_list)
        content_layout.addWidget(checklist_panel)

        warnings_panel = CollapsibleSectionPanel("警告與降級來源", collapsed=True)
        self.warnings_collapsible = warnings_panel
        self.warnings_section_title = warnings_panel.title_label
        self.warning_list = WarningList()
        self.warning_list.setMinimumHeight(90)
        warnings_panel.content_layout.addWidget(self.warning_list)
        content_layout.addWidget(warnings_panel)
        content_layout.addStretch()

        root_content_layout.addWidget(self.advanced_workbench_panel)
        root_content_layout.addStretch()

        set_scroll_content_constraints(scroll_content)
        scroll_area.setWidget(scroll_content)
        overview_layout.addWidget(scroll_area)
        self.subtabs.addTab(overview_page, "總覽")
        self.subtabs.addTab(self._build_decision_source_page(), "決策來源")
        self.research_console_view = ResearchConsoleView(
            source_service=self.research_console_source_service,
            learning_projection_service=self.learning_projection_service,
            legacy_learning_projection_service=self.legacy_learning_projection_service,
            decision_date=self.decision_date,
            auto_refresh=False,
            async_refresh=self._async_refresh,
            parent=self.subtabs,
        )
        self.subtabs.addTab(self.research_console_view, "研究證據")
        self.subtabs.setTabToolTip(2, "研究證據：查看完整的唯讀證據與成熟度資訊。")
        self.subtabs.currentChanged.connect(self._on_subtab_changed)
        self.subtabs.addTab(
            self._build_navigation_page(
                "持倉追蹤",
                "持倉與觀察清單摘要留在總覽；需實作檢查時切到持倉管理。",
                self.portfolio_button,
            ),
            "持倉追蹤",
        )
        self.subtabs.addTab(
            self._build_navigation_page(
                "操作節奏",
                "操作節奏只呈現 DTO 狀態；不標記完成、不寫 DB、不啟用排程器。",
                None,
            ),
            "操作節奏",
        )
        self._apply_responsive_layout(force=True)

    def _build_decision_source_page(self) -> QWidget:
        return self._build_navigation_page(
            "市場總覽",
            "Decision Desk 的唯一實例位於市場探索首頁；Workbench 僅提供導覽，不持有或嵌入第二份畫面。",
            self.daily_decision_button,
        )

    def _build_navigation_page(
        self,
        title: str,
        body: str,
        button: QPushButton | None,
    ) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        panel, _title = self._panel_with_title(title)
        label = QLabel(
            f"{body}\n\n"
            "此頁目前是摘要與下鑽入口，也是預留深挖區；完整資料與互動能力會等後續正式資料來源與功能切片補齊。"
        )
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        label.setStyleSheet(f"color: {MIDNIGHT_ANALYST.text_secondary};")
        panel.layout.addWidget(label)
        if button is not None:
            mirror_button = QPushButton(button.text())
            mirror_button.setProperty("variant", "secondary")
            mirror_button.setEnabled(button.isEnabled())
            mirror_button.setToolTip(button.toolTip())
            if button.isEnabled():
                mirror_button.clicked.connect(lambda _checked=False, source_button=button: source_button.click())
            panel.layout.addWidget(mirror_button)
        layout.addWidget(panel)
        layout.addStretch()
        return page

    def select_subtab(self, label: str) -> bool:
        lookup_label = "研究證據" if label == "Evidence" else label
        for index in range(self.subtabs.count()):
            if self.subtabs.tabText(index) == lookup_label:
                self.subtabs.setCurrentIndex(index)
                return True
        return False

    def viewed_review_item_ids(self) -> set[str]:
        return set(self._viewed_review_item_ids)

    def _panel_with_title(self, title: str) -> tuple[SectionPanel, QLabel]:
        panel = SectionPanel(title)
        title_widget = panel.layout.itemAt(0).widget()
        if isinstance(title_widget, QLabel):
            return panel, title_widget
        fallback_title = QLabel(title)
        panel.layout.insertWidget(0, fallback_title)
        return panel, fallback_title

    def _make_table(self, model) -> QTableView:
        table = QTableView()
        table.setModel(model)
        table.setMinimumHeight(110)
        table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setFocusPolicy(Qt.StrongFocus)
        table.setTabKeyNavigation(True)
        table.setAlternatingRowColors(True)
        table.setAccessibleDescription(
            "唯讀資料表；可用 Tab 與方向鍵移動，點選列後在詳情區查看完整來源。"
        )
        table.verticalHeader().setDefaultSectionSize(28)
        table.verticalHeader().setMinimumSectionSize(28)
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        table.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        apply_financial_table_style(table)
        if isinstance(model, PositionHealthTableModel):
            health_header = table.horizontalHeader()
            health_header.setStretchLastSection(False)
            health_header.setSectionResizeMode(
                model.column_index("why"), QHeaderView.Stretch
            )
            health_header.setSectionResizeMode(
                model.column_index("review_required"), QHeaderView.ResizeToContents
            )
        return table

    def _make_detail_box(self) -> QLabel:
        label = QLabel("")
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        label.setStyleSheet(
            f"background: {WORKBENCH_TONES['neutral']['bg']}; "
            f"color: {MIDNIGHT_ANALYST.text_secondary}; "
            f"border: 1px solid {WORKBENCH_TONES['neutral']['border']}; "
            f"border-left: 4px solid {WORKBENCH_TONES['neutral']['fg']}; "
            f"border-radius: {MIDNIGHT_ANALYST.radius_panel}px; padding: 10px; line-height: 140%;"
        )
        return label

    def _make_state_label(self) -> QLabel:
        label = QLabel("")
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        label.setStyleSheet(
            f"background: {MIDNIGHT_ANALYST.surface_2}; color: {MIDNIGHT_ANALYST.text_secondary}; "
            f"border: 1px solid {MIDNIGHT_ANALYST.border}; "
            f"border-radius: {MIDNIGHT_ANALYST.radius_panel}px; padding: 8px;"
        )
        return label

    def _build_guided_home(self, parent_layout: QVBoxLayout) -> None:
        """建立首屏的四列摘要；完整模型與技術欄位留在進階區。"""

        panel, self.guided_home_section_title = self._panel_with_title("今日優先查看")
        self.guided_home_panel = panel
        purpose_layout = QHBoxLayout()
        self.home_purpose_buttons: dict[str, QPushButton] = {}
        for key, label, target in (
            ("market", "看盤勢", "market_explore"),
            ("portfolio", "持倉健康", "portfolio"),
            ("selection", "選股研究", "recommendation"),
            ("stock", "個股研究", "stock_search"),
        ):
            button = QPushButton(label)
            button.setProperty("variant", "secondary")
            button.setAccessibleName(label)
            button.setEnabled(
                self.navigate_to_stock_research_callback is not None
                if target == "stock_search" else self._today_action_available(target)
            )
            button.clicked.connect(
                lambda checked=False, route=target: self._open_home_purpose(route)
            )
            purpose_layout.addWidget(button)
            self.home_purpose_buttons[key] = button
        panel.layout.addLayout(purpose_layout)
        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("股票代號"))
        self.home_stock_input = QLineEdit()
        self.home_stock_input.setAccessibleName("個股研究股票代號")
        self.home_stock_input.setPlaceholderText("輸入台股代號，開啟當下研究")
        self.home_stock_input.returnPressed.connect(self._open_home_stock_search)
        search_layout.addWidget(self.home_stock_input, 1)
        self.home_stock_search_button = QPushButton("開啟當下研究")
        self.home_stock_search_button.clicked.connect(self._open_home_stock_search)
        search_layout.addWidget(self.home_stock_search_button)
        search_available = self.navigate_to_stock_research_callback is not None
        self.home_stock_input.setEnabled(search_available)
        self.home_stock_search_button.setEnabled(search_available)
        panel.layout.addLayout(search_layout)
        self.home_stock_search_hint = QLabel(
            "自行搜尋使用當下研究來源；原候選與保存結果仍由原列下鑽。"
        )
        self.home_stock_search_hint.setWordWrap(True)
        panel.layout.addWidget(self.home_stock_search_hint)
        theme_entry_layout = QHBoxLayout()
        self.home_theme_button = QPushButton("繼續查看產業與題材")
        self.home_theme_button.setObjectName("homeThemeResearchButton")
        self.home_theme_button.setAccessibleName("繼續查看產業與題材研究")
        self.home_theme_button.setProperty("variant", "secondary")
        self.home_theme_button.setToolTip(
            "返回目前題材研究頁；不重新載入或清除所選版本。"
        )
        self.home_theme_button.setEnabled(
            self.navigate_to_industry_themes_callback is not None
        )
        self.home_theme_button.clicked.connect(self._open_home_industry_themes)
        theme_entry_layout.addWidget(self.home_theme_button)
        self.home_theme_summary_label = QLabel(
            "尚未載入題材研究版本；請先到「產業與題材」選取本機已保存版本。"
        )
        self.home_theme_summary_label.setObjectName("homeThemeResearchSummary")
        self.home_theme_summary_label.setAccessibleName("首頁題材研究版本摘要")
        self.home_theme_summary_label.setWordWrap(True)
        self.home_theme_summary_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        theme_entry_layout.addWidget(self.home_theme_summary_label, 1)
        panel.layout.addLayout(theme_entry_layout)
        intro = QLabel(
            "先看持倉、候選、市場與資料影響；需要完整理由時展開完整工作台。"
        )
        intro.setWordWrap(True)
        intro.setStyleSheet(f"color: {MIDNIGHT_ANALYST.text_secondary};")
        panel.layout.addWidget(intro)
        self.guided_date_label = QLabel("判讀日期：尚未確認｜資料日期：尚未確認")
        self.guided_date_label.setWordWrap(True)
        self.guided_date_label.setStyleSheet(
            f"color: {MIDNIGHT_ANALYST.text_muted}; font-size: 10px;"
        )
        panel.layout.addWidget(self.guided_date_label)
        self.guided_conclusion_label = QLabel("判讀結論：尚未確認。")
        conclusion_font = QFont()
        conclusion_font.setPointSize(14)
        conclusion_font.setBold(True)
        self.guided_conclusion_label.setFont(conclusion_font)
        self.guided_conclusion_label.setWordWrap(True)
        self.guided_conclusion_label.setStyleSheet(
            f"color: {MIDNIGHT_ANALYST.text_primary};"
        )
        panel.layout.addWidget(self.guided_conclusion_label)
        self.guided_next_action_label = QLabel("主要下一步：重新整理目前狀態。")
        self.guided_next_action_label.setWordWrap(True)
        self.guided_next_action_label.setStyleSheet(
            f"color: {MIDNIGHT_ANALYST.text_secondary}; font-weight: 700;"
        )
        panel.layout.addWidget(self.guided_next_action_label)

        self.guided_priority_rows: dict[str, QFrame] = {}
        self.guided_priority_status_badges: dict[str, StatusBadge] = {}
        self.guided_priority_conclusion_labels: dict[str, QLabel] = {}
        self.guided_priority_reason_labels: dict[str, QLabel] = {}
        self.guided_priority_action_buttons: dict[str, QPushButton] = {}
        self._guided_priority_row_indices: dict[str, int] = {}

        row_specs = (
            ("portfolio", "持倉"),
            ("candidates", "候選"),
            ("market", "市場"),
            ("data", "資料影響"),
            ("other", "其他待處理"),
        )
        for key, title in row_specs:
            row = QFrame()
            row.setObjectName("guidedPriorityRow")
            row.setStyleSheet(
                f"QFrame#guidedPriorityRow {{ background: {MIDNIGHT_ANALYST.surface_2}; "
                f"border: 1px solid {MIDNIGHT_ANALYST.border}; "
                f"border-radius: {MIDNIGHT_ANALYST.radius_panel}px; }}"
            )
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(9, 7, 9, 7)
            row_layout.setSpacing(10)

            title_label = QLabel(title)
            title_label.setMinimumWidth(68)
            title_label.setStyleSheet(
                f"color: {MIDNIGHT_ANALYST.text_primary}; font-weight: 800;"
            )
            row_layout.addWidget(title_label, 0)

            badge = StatusBadge("未知", "unknown")
            badge.setMinimumWidth(78)
            self.guided_priority_status_badges[key] = badge
            row_layout.addWidget(badge, 0)

            copy_layout = QVBoxLayout()
            copy_layout.setContentsMargins(0, 0, 0, 0)
            copy_layout.setSpacing(2)
            conclusion = QLabel("尚未確認。")
            conclusion.setWordWrap(True)
            conclusion.setStyleSheet(
                f"color: {MIDNIGHT_ANALYST.text_primary}; font-weight: 700;"
            )
            reason = QLabel("資料尚未載入，不推定沒有風險。")
            reason.setWordWrap(True)
            reason.setStyleSheet(
                f"color: {MIDNIGHT_ANALYST.text_secondary}; font-size: 12px;"
            )
            copy_layout.addWidget(conclusion)
            copy_layout.addWidget(reason)
            row_layout.addLayout(copy_layout, 1)

            action_button = QPushButton("查看")
            action_button.setProperty("variant", "secondary")
            action_button.setMinimumWidth(116)
            action_button.setAccessibleName(f"查看{title}重點")
            action_button.clicked.connect(
                lambda checked=False, row_key=key: self._open_guided_priority(row_key)
            )
            self.guided_priority_action_buttons[key] = action_button
            row_layout.addWidget(action_button, 0)

            self.guided_priority_rows[key] = row
            self.guided_priority_conclusion_labels[key] = conclusion
            self.guided_priority_reason_labels[key] = reason
            panel.layout.addWidget(row)
            if key == "other":
                row.setVisible(False)

        self.guided_warning_summary_label = QLabel("")
        self.guided_warning_summary_label.setWordWrap(True)
        self.guided_warning_summary_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.guided_warning_summary_label.setStyleSheet(
            f"color: {MIDNIGHT_ANALYST.warning}; font-weight: 700;"
        )
        panel.layout.addWidget(self.guided_warning_summary_label)
        parent_layout.addWidget(panel)

    def _render_guided_home(self, dashboard: WorkbenchDashboardDTO | None) -> None:
        """只整理已注入 DTO；不建立第二份來源或重新計算策略。"""

        if dashboard is None:
            rows = (
                GuidedWorkbenchRow(
                    "portfolio", "持倉", "unknown", "尚未確認持倉狀態。",
                    "資料尚未載入，不推定沒有風險。", "檢查持倉事項", "portfolio_review",
                ),
                GuidedWorkbenchRow(
                    "candidates", "候選", "unknown", "尚未確認研究候選。",
                    "資料尚未載入，不推定沒有候選。", "查看候選研究", "stock_research",
                ),
                GuidedWorkbenchRow(
                    "market", "市場", "unknown", "尚未確認市場狀態。",
                    "沒有可信工作台資料。", "查看市場重點", "daily_decision",
                ),
                GuidedWorkbenchRow(
                    "data", "資料影響", "missing", "資料狀態尚未確認。",
                    "先檢查資料狀態；缺件與等待會分開標示。", "查看資料狀態", "update",
                ),
            )
            warning_text = "警示尚未載入；請先查看資料狀態。"
            self.guided_date_label.setText(
                "保存快照日：尚未確認｜行情截至：尚未確認｜台北評估日：尚未確認"
            )
            self.guided_conclusion_label.setText("判讀結論：尚未確認。")
            self.guided_next_action_label.setText("主要下一步：重新整理目前狀態。")
        else:
            rows, warning_text = self._guided_rows_for_dashboard(dashboard)
            snapshot_date = _optional_date_text(dashboard.snapshot_date)
            market_date = _optional_date_text(dashboard.market_data_as_of_date)
            evaluation_date = _optional_date_text(dashboard.evaluation_date)
            freshness_note = "（請確認最新狀態）" if self._dashboard_stale else ""
            self.guided_date_label.setText(
                f"保存快照日：{snapshot_date}｜行情截至：{market_date}｜"
                f"台北評估日：{evaluation_date}｜"
                f"{_latest_capture_overview_text(dashboard)}{freshness_note}"
            )
            daily = dashboard.daily_evidence
            headline = _guided_compact(
                _home_public_text(getattr(daily, "headline", "")) if daily else "",
                "市場與資料重點請依下方四列確認。",
                132,
            )
            next_action = _guided_compact(
                _home_public_text(_home_next_action(getattr(daily, "next_action", "") if daily else "")),
                "先確認資料狀態，再查看主要重點。",
                132,
            )
            self.guided_conclusion_label.setText(f"判讀結論：{headline}")
            self.guided_next_action_label.setText(f"主要下一步：{next_action}")
            self.guided_conclusion_label.setToolTip(str(getattr(daily, "headline", "") or ""))
            self.guided_next_action_label.setToolTip(str(getattr(daily, "next_action", "") or ""))

        self.guided_summary_model.set_rows(rows)
        self._guided_priority_row_indices = {
            row.key: index for index, row in enumerate(rows)
        }
        for row in rows:
            self._set_guided_row_widgets(row)
        for key, row_widget in self.guided_priority_rows.items():
            row_widget.setVisible(key in self._guided_priority_row_indices)
        self.guided_warning_summary_label.setText(warning_text)

    def _guided_rows_for_dashboard(
        self, dashboard: WorkbenchDashboardDTO
    ) -> tuple[tuple[GuidedWorkbenchRow, ...], str]:
        daily = dashboard.daily_evidence
        market_context = dashboard.market_context if isinstance(dashboard.market_context, dict) else {}
        source_status = str(market_context.get("source_status") or "unknown").strip().lower()
        warning_lines = tuple(_guided_warning_text(item) for item in dashboard.warnings)
        if daily is not None:
            warning_lines += tuple(_guided_warning_text(item) for item in daily.warnings)

        human_actions = tuple(
            item
            for item in dashboard.action_items
            if str(getattr(item, "status_classification", "")) == MACHINE_STATUS_HUMAN_REVIEW
        )
        portfolio_actions = tuple(item for item in human_actions if _guided_is_portfolio_item(item))
        candidate_actions = tuple(item for item in human_actions if _guided_is_candidate_item(item))
        generic_actions = tuple(
            item for item in human_actions
            if item not in portfolio_actions and item not in candidate_actions
        )
        market_review_items = tuple(
            item for item in dashboard.review_items if _guided_is_market_item(item)
        )
        candidate_review_items = tuple(
            item for item in dashboard.review_items if _guided_is_candidate_item(item)
        )
        generic_review_items = tuple(
            item for item in dashboard.review_items
            if item not in market_review_items and item not in candidate_review_items
        )
        health = dashboard.position_health
        health_positions = tuple(getattr(health, "positions", ()) or ()) if health else ()
        risky_positions = tuple(
            item for item in health_positions
            if bool(getattr(item, "review_required", False))
            or str(getattr(item, "action_suitability", ""))
            in {"REDUCE_CANDIDATE", "EXIT_CANDIDATE"}
        )
        if portfolio_actions:
            portfolio_status = "warning"
            portfolio_conclusion = f"有 {len(portfolio_actions)} 項持倉或風險事項待檢查。"
            portfolio_reasons = _guided_join_reasons(
                *(getattr(item, "title", "") for item in portfolio_actions),
                *(getattr(item, "summary", "") for item in portfolio_actions),
                fallback="請依既有持倉與風險來源逐項確認。",
            )
        elif health is None or str(getattr(health, "status", "unknown")).lower() in {
            "unknown", "missing", "error"
        }:
            portfolio_status = "missing"
            portfolio_conclusion = "持倉資料尚未確認。"
            portfolio_reasons = "資料缺件與股票風險分開；目前不能推定沒有風險。"
        elif risky_positions:
            portfolio_status = "warning"
            portfolio_conclusion = f"有 {len(risky_positions)} 筆持倉狀態需要留意。"
            portfolio_reasons = _guided_join_reasons(
                *(getattr(item, "why", "") for item in risky_positions),
                *(getattr(item, "why_not", ()) for item in risky_positions),
                fallback="持倉來源已提供需要複核的狀態。",
            )
        elif health_positions:
            portfolio_status = "info"
            portfolio_conclusion = f"已載入 {len(health_positions)} 筆持倉狀態。"
            portfolio_reasons = "目前沒有明確人工待處理項目；仍可查看每筆來源理由。"
        else:
            portfolio_status = "info"
            portfolio_conclusion = "目前沒有可呈現的持倉列。"
            portfolio_reasons = "空結果不等於風險已排除；可查看持倉管理確認。"

        if candidate_actions or candidate_review_items:
            candidate_status = "warning"
            candidate_total = len(candidate_actions) + len(candidate_review_items)
            candidate_conclusion = f"有 {candidate_total} 項候選或研究事項待處理。"
            if daily is not None and daily.candidate_count:
                candidate_conclusion += f"另有 {daily.candidate_count} 檔候選可查看。"
            candidate_reasons = _guided_join_reasons(
                *(getattr(item, "title", "") for item in candidate_actions),
                *(getattr(item, "summary", "") for item in candidate_actions),
                *(getattr(item, "summary", "") for item in candidate_review_items),
                fallback="請查看完整清單中的候選股票、理由與日期。",
            )
            candidate_target = "advanced"
        elif daily is None:
            candidate_status = "missing"
            candidate_conclusion = "研究候選尚未確認。"
            candidate_reasons = "資料尚未載入；空白不等於沒有候選。"
            candidate_target = "advanced"
        else:
            candidate_state = str(daily.candidate_status or "unknown").strip().lower()
            if candidate_state in {"missing", "read_failure", "future_blocked", "stale"}:
                candidate_status = "critical" if candidate_state == "read_failure" else "missing"
                candidate_conclusion = "無法確認今天的研究候選。"
                candidate_reasons = _guided_join_reasons(
                    *daily.candidate_reasons,
                    "候選資料缺件時不推定沒有候選。",
                    fallback="請先查看資料狀態。",
                )
                candidate_target = "update"
            elif daily.candidate_count > 0:
                candidate_status = (
                    "warning" if candidate_state in {"candidate_degraded", "degraded"} else "info"
                )
                candidate_conclusion = f"有 {daily.candidate_count} 檔研究候選可查看。"
                candidate_reasons = _guided_join_reasons(
                    *daily.candidate_reasons,
                    daily.stock_summary,
                    "候選僅供研究，不代表可交易。",
                    fallback="請逐檔查看股票、理由與日期。",
                )
                candidate_target = (
                    "advanced"
                    if len(daily.candidate_symbols) > 1
                    else (
                        "stock_research"
                        if daily.candidate_symbols and self.navigate_to_stock_research_callback is not None
                        else "watchlist"
                    )
                )
            else:
                candidate_status = "info"
                candidate_conclusion = "目前沒有可安全呈現的候選列。"
                candidate_reasons = "空結果不代表條件已通過；請查看來源與限制。"
                candidate_target = "recommendation"

        if market_review_items:
            market_status = "warning"
            market_conclusion = f"有 {len(market_review_items)} 項市場判讀待處理。"
            market_reasons = _guided_join_reasons(
                *(getattr(item, "summary", "") for item in market_review_items),
                *(getattr(item, "title", "") for item in market_review_items),
                fallback="先查看市場重點與既有風險訊號。",
            )
        elif source_status in {"", "unknown", "missing", "blocked", "outage", "error"}:
            market_status = "missing"
            market_conclusion = "市場狀態尚未完全確認。"
            market_reasons = _guided_join_reasons(
                getattr(daily, "market_summary", "") if daily else "",
                getattr(daily, "industry_summary", "") if daily else "",
                fallback="市場資料缺件；不能把空白當成安全訊號。",
            )
        elif self._dashboard_stale:
            market_status = "stale"
            market_conclusion = "市場資料保留最後可信內容，尚未確認為最新。"
            market_reasons = "來源讀取失敗；請重新整理後再判讀。"
        else:
            market_status = "info"
            market_conclusion = _guided_compact(
                getattr(daily, "market_summary", "市場資料可檢視。") if daily else "市場資料可檢視。",
                "市場資料可檢視。",
            )
            market_reasons = _guided_join_reasons(
                getattr(daily, "industry_summary", "") if daily else "",
                getattr(daily, "stock_summary", "") if daily else "",
                fallback="請查看市場重點中的主要理由。",
            )
        market_reasons = _home_market_reason(market_reasons)

        waiting_items = tuple(
            item for item in dashboard.daily_checklist
            if str(getattr(item, "status", "")).strip().lower() == "waiting_for_time"
        )
        data_status = "info"
        data_conclusion = "資料狀態可檢視，但仍請留意日期與警示。"
        data_reasons = "沒有可信來源時不補值；自然等待會單獨標示。"
        data_action_label = "查看資料狀態"
        data_target = "update"
        if self._dashboard_stale:
            data_status = "stale"
            data_conclusion = "資料保留最後可信內容，尚未確認為最新。"
            data_reasons = "來源本次讀取失敗；請重新整理。"
        elif source_status in {"", "unknown", "missing", "blocked", "outage", "error"}:
            data_status = "missing"
            data_conclusion = "資料有缺件，市場與候選結論需要保留。"
            data_reasons = "資料缺件與股票風險分開；先查看資料狀態。"
        elif warning_lines:
            data_status = "warning"
            data_conclusion = f"有 {len(warning_lines)} 則資料或來源警示。"
            data_reasons = _guided_join_reasons(
                *warning_lines,
                fallback="請查看完整警示與來源狀態。",
            )
            data_action_label = "查看完整警示"
            data_target = "warnings"
            if waiting_items:
                data_reasons += f"；另有 {len(waiting_items)} 項自然等待。"
        elif waiting_items:
            data_status = "waiting_for_time"
            data_conclusion = f"有 {len(waiting_items)} 項需要等待真實時間累積。"
            data_reasons = _guided_join_reasons(
                *(getattr(item, "summary", "") for item in waiting_items),
                fallback="自然等待不等於資料讀取失敗。",
            )

        rows_list = [
            GuidedWorkbenchRow(
                "portfolio", "持倉", portfolio_status, portfolio_conclusion,
                portfolio_reasons, "查看持倉事項", "portfolio_review",
            ),
            GuidedWorkbenchRow(
                "candidates", "候選", candidate_status, candidate_conclusion,
                candidate_reasons, "查看候選研究", candidate_target,
            ),
            GuidedWorkbenchRow(
                "market", "市場", market_status, market_conclusion,
                market_reasons, "查看市場重點", "daily_decision",
            ),
            GuidedWorkbenchRow(
                "data", "資料影響", data_status, data_conclusion,
                data_reasons, data_action_label, data_target,
            ),
        ]
        generic_count = len(generic_actions) + len(generic_review_items)
        if generic_count:
            generic_reasons = _guided_join_reasons(
                *(getattr(item, "title", "") for item in generic_actions),
                *(getattr(item, "summary", "") for item in generic_actions),
                *(getattr(item, "summary", "") for item in generic_review_items),
                fallback="請展開完整工作台查看來源類別與下一步。",
            )
            rows_list.append(
                GuidedWorkbenchRow(
                    "other",
                    "其他待處理",
                    "warning",
                    f"有 {generic_count} 項待處理事項，來源尚未分組。",
                    generic_reasons,
                    "查看完整待處理",
                    "advanced",
                )
            )
        rows = tuple(rows_list)
        if warning_lines:
            warning_text = (
                f"警示：共 {len(warning_lines)} 則；按「查看完整警示」可查看全部內容。"
            )
        else:
            warning_text = "目前沒有可顯示的警示；資料不足仍會維持未知或缺件狀態。"
        return rows, warning_text

    def _set_guided_row_widgets(self, row: GuidedWorkbenchRow) -> None:
        badge = self.guided_priority_status_badges[row.key]
        badge.setText(_guided_status_text(row.status))
        badge.set_quality(_guided_status_tone(row.status))
        self.guided_priority_conclusion_labels[row.key].setText(_home_public_text(row.conclusion))
        self.guided_priority_reason_labels[row.key].setText(_home_public_text(row.reasons))
        self.guided_priority_conclusion_labels[row.key].setToolTip(row.conclusion)
        self.guided_priority_reason_labels[row.key].setToolTip(row.reasons)
        button = self.guided_priority_action_buttons[row.key]
        button.setText(row.action_label)
        button.setEnabled(self._guided_target_available(row.target))
        button.setToolTip("只導覽到既有工作區或顯示既有完整來源；不會重新取得資料。")

    def _guided_target_available(self, target: str) -> bool:
        if target in {"advanced", "warnings"}:
            return True
        return self._today_action_available(target)

    def _open_guided_priority(self, key: str) -> bool:
        index = self._guided_priority_row_indices.get(key)
        row = self.guided_summary_model.row_at(index) if index is not None else None
        if row is None:
            return False
        if key == "market" and self.navigate_to_market_explore_callback is not None:
            return self.navigate_to_drilldown_target("market_explore")
        if key == "portfolio" and self.navigate_to_portfolio_callback is not None:
            return self.navigate_to_drilldown_target(row.target)
        if key == "data":
            self.advanced_workbench_panel.set_collapsed(False)
            self.warnings_collapsible.set_collapsed(False)
            self.overview_scroll_area.ensureWidgetVisible(self.warnings_collapsible)
        elif key in {"portfolio", "market"} or row.target == "advanced":
            self.advanced_workbench_panel.set_collapsed(False)
            if key == "portfolio":
                if not self._select_guided_model_item(
                    self.action_item_model,
                    self.action_item_table,
                    _guided_is_portfolio_item,
                ):
                    self.overview_scroll_area.ensureWidgetVisible(self.position_health_panel)
            elif key == "market":
                self._select_guided_model_item(
                    self.review_model,
                    self.review_table,
                    _guided_is_market_item,
                )
            elif key == "candidates":
                if not self._select_guided_model_item(
                    self.review_model,
                    self.review_table,
                    _guided_is_candidate_item,
                ):
                    self._select_guided_model_item(
                        self.action_item_model,
                        self.action_item_table,
                        _guided_is_candidate_item,
                    )
            else:
                if not self._select_guided_model_item(
                    self.review_model,
                    self.review_table,
                    _guided_is_generic_item,
                ):
                    self._select_guided_model_item(
                        self.action_item_model,
                        self.action_item_table,
                        _guided_is_generic_item,
                    )
        if row.target in {"advanced", "warnings"}:
            return True
        return self.navigate_to_drilldown_target(row.target)

    def _open_home_purpose(self, target: str) -> bool:
        if target == "stock_search":
            self.home_stock_input.setFocus()
            return self._open_home_stock_search() if self.home_stock_input.text().strip() else True
        return self.navigate_to_drilldown_target(target)

    def _open_home_industry_themes(self) -> bool:
        callback = self.navigate_to_industry_themes_callback
        if callback is None:
            return False
        callback()
        return True

    def _open_home_stock_search(self) -> bool:
        callback = self.navigate_to_stock_research_callback
        stock_code = self.home_stock_input.text().strip()
        if callback is None or not re.fullmatch(r"[0-9]{4,6}", stock_code):
            self.home_stock_search_hint.setText("請輸入 4–6 位台股代號；股號與來源可用性由個股研究頁核對。")
            return False
        callback(ResearchStockContextDTO(
            stock_code=stock_code,
            source_kind="explicit_latest_stock_research",
            source_label="首頁明確搜尋的當下個股研究",
            source_workspace="workbench",
        ))
        self.home_stock_search_hint.setText(
            "已開啟當下研究；沒有沿用首頁候選的日期、結果或保存來源。"
        )
        return True

    def _select_guided_model_item(self, model, table: QTableView, predicate) -> bool:
        for index in range(model.rowCount()):
            item = model.row_at(index)
            if item is None or not predicate(item):
                continue
            self._show_model_row_detail(model, index)
            table.selectRow(index)
            panel = self.review_panel if table is self.review_table else self.action_item_panel
            self.overview_scroll_area.ensureWidgetVisible(panel)
            return True
        return False

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().resizeEvent(event)
        self._apply_responsive_layout()

    def _apply_responsive_layout(self, *, force: bool = False) -> None:
        """依可用寬度重排既有 Workbench 元件，不改變 DTO 或導覽契約。"""
        if not hasattr(self, "primary_layout"):
            return
        narrow = self.width() < 820
        if not force and narrow == self._workbench_narrow:
            return
        self._workbench_narrow = narrow

        direction = QBoxLayout.TopToBottom if narrow else QBoxLayout.LeftToRight
        self.summary_layout.setDirection(direction)
        self.workflow_path_layout.setDirection(direction)
        self.drilldown_layout.setDirection(direction)
        self.evidence_summary_layout.setDirection(direction)
        self.daily_metrics_layout.setDirection(direction)
        self.daily_action_layout.setDirection(direction)
        self.primary_layout.setDirection(direction)
        self.detail_panel.setMinimumWidth(0 if narrow else 360)

        cards_layout = self.today_cards_layout
        for index, key in enumerate(self.today_action_cards):
            card = self.today_action_cards[key]
            cards_layout.removeWidget(card)
            row = index if narrow else index // 2
            column = 0 if narrow else index % 2
            cards_layout.addWidget(card, row, column)
        cards_layout.setColumnStretch(0, 1)
        cards_layout.setColumnStretch(1, 0 if narrow else 1)
        self._resize_tables()

    def _format_workbench_source_meta(self, dashboard: WorkbenchDashboardDTO) -> str:
        """顯示來源契約可確認的日期與未知欄位，不由 UI 猜測 freshness。"""
        market_context = dashboard.market_context if isinstance(dashboard.market_context, dict) else {}
        source_status = display_workbench_value(str(market_context.get("source_status") or "unknown"))
        advice_data_date = ""
        advice = dashboard.advice_dashboard
        if advice is not None:
            advice_data_date = str(getattr(advice, "data_as_of_date", "") or "").strip()
        advice_date = advice_data_date or "未知"
        return "\n".join(
            (
                f"工作台 as_of：{dashboard.as_of_date.isoformat()}",
                f"保存快照日：{_optional_date_text(dashboard.snapshot_date)}",
                f"股票行情截至：{_optional_date_text(dashboard.market_data_as_of_date)}",
                f"大盤指數截至（TAIEX）：{_optional_date_text(dashboard.market_index_as_of_date)}",
                f"台北評估日：{_optional_date_text(dashboard.evaluation_date)}",
                f"Advice 資料日期：{advice_date}",
                f"最新保存快照擷取：{_latest_capture_status_text(dashboard)}",
                f"來源狀態：{source_status}；來源模式：{display_workbench_value(dashboard.source_mode)}",
                f"產生時間（既有 DTO）：{dashboard.generated_at.isoformat()}",
                (
                    "安全邊界：唯讀；不允許寫入、不啟用正式排程器。"
                    "日期與 freshness 不在 UI 補值，需到數據更新查看來源詳情。"
                ),
            )
        )

    def _build_daily_investment_journey(self, parent_layout: QVBoxLayout) -> None:
        """建立首頁首屏的每日結論與可追溯下鑽入口。"""

        panel, self.daily_journey_section_title = self._panel_with_title(
            "今日投資結論／每日決策旅程"
        )
        self.daily_journey_panel = panel
        self.daily_conclusion_label = QLabel("今日結論：等待 WorkbenchDashboardDTO。")
        conclusion_font = QFont()
        conclusion_font.setPointSize(14)
        conclusion_font.setBold(True)
        self.daily_conclusion_label.setFont(conclusion_font)
        self.daily_conclusion_label.setWordWrap(True)
        self.daily_conclusion_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.daily_conclusion_label.setStyleSheet(f"color: {MIDNIGHT_ANALYST.text_primary};")
        panel.layout.addWidget(self.daily_conclusion_label)

        self.daily_state_label = self._make_state_label()
        panel.layout.addWidget(self.daily_state_label)

        metrics_row = QWidget()
        self.daily_metrics_layout = QHBoxLayout(metrics_row)
        self.daily_metrics_layout.setContentsMargins(0, 0, 0, 0)
        self.daily_metrics_layout.setSpacing(8)
        self.daily_market_card = MetricCard("市場", "等待")
        self.daily_industry_card = MetricCard("產業", "等待")
        self.daily_candidate_card = MetricCard("今日候選", "等待")
        self.daily_portfolio_card = MetricCard("持倉", "等待")
        self.daily_evidence_card = MetricCard("證據成熟度", "等待")
        for card in (
            self.daily_market_card,
            self.daily_industry_card,
            self.daily_candidate_card,
            self.daily_portfolio_card,
            self.daily_evidence_card,
        ):
            card.value_label.setStyleSheet(
                f"color: {MIDNIGHT_ANALYST.text_primary}; font-size: 11pt; "
                "font-weight: 700; line-height: 135%;"
            )
            card.value_label.setWordWrap(True)
            self.daily_metrics_layout.addWidget(card, 1)
        panel.layout.addWidget(metrics_row)

        self.daily_journey_label = self._make_state_label()
        self.daily_journey_label.setObjectName("dailyJourneySummary")
        panel.layout.addWidget(self.daily_journey_label)

        self.daily_candidate_detail_label = QLabel("個股研究候選：等待來源。")
        self.daily_candidate_detail_label.setWordWrap(True)
        self.daily_candidate_detail_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.daily_candidate_detail_label.setMinimumHeight(48)
        self.daily_candidate_detail_label.setStyleSheet(
            f"background: {MIDNIGHT_ANALYST.surface_2}; color: {MIDNIGHT_ANALYST.text_secondary}; "
            f"border: 1px solid {MIDNIGHT_ANALYST.border}; "
            f"border-radius: {MIDNIGHT_ANALYST.radius_panel}px; padding: 8px;"
        )
        panel.layout.addWidget(self.daily_candidate_detail_label)

        candidate_selector_row = QWidget()
        candidate_selector_layout = QHBoxLayout(candidate_selector_row)
        candidate_selector_layout.setContentsMargins(0, 0, 0, 0)
        candidate_selector_layout.setSpacing(8)
        candidate_selector_label = QLabel("明選要開啟的研究股票")
        candidate_selector_label.setAccessibleName("每日候選研究股票選擇說明")
        self.daily_candidate_selector = QComboBox()
        self.daily_candidate_selector.setAccessibleName("每日候選研究股票明選")
        self.daily_candidate_selector.setMinimumContentsLength(18)
        self.daily_candidate_selector.addItem("請選擇研究股票", None)
        self.daily_candidate_selector.setEnabled(False)
        self.daily_candidate_selector.currentIndexChanged.connect(
            self._on_daily_candidate_selection_changed
        )
        candidate_selector_layout.addWidget(candidate_selector_label)
        candidate_selector_layout.addWidget(self.daily_candidate_selector, 1)
        panel.layout.addWidget(candidate_selector_row)

        actions_row = QWidget()
        self.daily_action_layout = QHBoxLayout(actions_row)
        self.daily_action_layout.setContentsMargins(0, 0, 0, 0)
        self.daily_action_layout.setSpacing(8)
        self.daily_candidate_button = QPushButton("開啟候選研究報告")
        self.daily_candidate_button.setProperty("variant", "primary")
        self.daily_candidate_button.setAccessibleName("開啟每日候選個股研究報告")
        self.daily_candidate_button.setToolTip(
            "以每日候選的股票代號、決策日與來源 identity 開啟既有個股研究報告；不新增觀察清單。"
        )
        self.daily_candidate_button.clicked.connect(self._open_daily_candidate_research)
        self.daily_watchlist_button = QPushButton("查看既有觀察清單")
        self.daily_watchlist_button.setProperty("variant", "secondary")
        self.daily_watchlist_button.setAccessibleName("查看既有觀察清單")
        self.daily_watchlist_button.setToolTip(
            "查看既有觀察清單；Workbench 不會因每日候選自動新增或修改清單。"
        )
        self.daily_watchlist_button.clicked.connect(
            lambda: self.navigate_to_drilldown_target("watchlist")
        )
        self.daily_evidence_button = QPushButton("查看證據成熟度")
        self.daily_evidence_button.setProperty("variant", "secondary")
        self.daily_evidence_button.setAccessibleName("查看每日證據成熟度")
        self.daily_evidence_button.setToolTip(
            "切到既有證據頁查看範圍、身份與各成熟度窗口；不執行重算。"
        )
        self.daily_evidence_button.clicked.connect(lambda: self.select_subtab("Evidence"))
        self.daily_detail_button = QPushButton("查看每日來源詳情")
        self.daily_detail_button.setProperty("variant", "secondary")
        self.daily_detail_button.setCheckable(True)
        self.daily_detail_button.setAccessibleName("查看每日來源詳情")
        self.daily_detail_button.setToolTip(
            "展開每日 snapshot、candidate、event identity、learning receipt 與診斷；唯讀。"
        )
        self.daily_detail_button.toggled.connect(self._toggle_daily_detail)
        for button in (
            self.daily_candidate_button,
            self.daily_watchlist_button,
            self.daily_evidence_button,
            self.daily_detail_button,
        ):
            self.daily_action_layout.addWidget(button)
        self.daily_action_layout.addStretch()
        panel.layout.addWidget(actions_row)

        self.daily_trace_label = self._make_detail_box()
        self.daily_trace_label.setObjectName("dailyJourneyTrace")
        self.daily_trace_label.setVisible(False)
        panel.layout.addWidget(self.daily_trace_label)
        parent_layout.addWidget(panel)

    def _render_daily_investment_journey(
        self,
        daily: WorkbenchDailyEvidence | None,
    ) -> None:
        self._daily_investment_evidence = daily
        self._populate_daily_candidate_selector(daily)
        self.daily_detail_button.blockSignals(True)
        self.daily_detail_button.setChecked(False)
        self.daily_detail_button.blockSignals(False)
        self.daily_trace_label.setVisible(False)
        if daily is None:
            self.daily_conclusion_label.setText("今日結論：等待 WorkbenchDashboardDTO。")
            self.daily_state_label.setText(
                "狀態：未知｜決策日：未知｜資料日：未知；沒有可信 DTO 時不推定沒有候選或風險。"
            )
            self._style_daily_state("unknown")
            for card in (
                self.daily_market_card,
                self.daily_industry_card,
                self.daily_candidate_card,
                self.daily_portfolio_card,
                self.daily_evidence_card,
            ):
                card.value_label.setText("等待")
            self.daily_journey_label.setText(
                "下一步：重新整理既有唯讀來源。UI 不讀 DB、不執行策略、不補值。"
            )
            self.daily_candidate_detail_label.setText(
                "個股研究候選：尚未載入；空白不等於沒有候選。"
            )
            self._sync_daily_candidate_open_controls()
            self.daily_watchlist_button.setEnabled(False)
            self.daily_evidence_button.setEnabled(False)
            self.daily_detail_button.setEnabled(False)
            self.daily_trace_label.setText("每日來源詳情：尚未有可信 DTO。")
            return

        tone_status = daily.status
        self.daily_conclusion_label.setText(f"{daily.decision_date} 今日結論：{daily.headline}")
        self.daily_state_label.setText(
            f"狀態：{display_workbench_value(daily.status)}｜"
            f"決策日：{daily.decision_date}｜資料日：{daily.data_as_of_date or '未知'}｜"
            f"研究候選 {daily.candidate_count} 檔；候選僅供人工研究，非交易指令。"
        )
        self._style_daily_state(tone_status)
        self.daily_market_card.value_label.setText(
            _compact_daily_text(_home_market_reason(daily.market_summary))
        )
        self.daily_industry_card.value_label.setText(_compact_daily_text(daily.industry_summary))
        self.daily_candidate_card.value_label.setText(
            f"{daily.candidate_count} 檔\n{_daily_candidate_surface_status(daily)}"
        )
        self.daily_portfolio_card.value_label.setText(_compact_daily_text(daily.portfolio_summary))
        self.daily_evidence_card.value_label.setText(_daily_evidence_card_text(daily))
        evidence_line = _daily_evidence_surface_line(daily)
        learning_line = _daily_learning_line(daily.learning, daily.learning_projection)
        next_action = _home_next_action(daily.next_action)
        journey_lines = [f"下一步：{next_action}", evidence_line, learning_line]
        fallback_line = _daily_research_fallback_line(daily.research_fallback)
        if fallback_line:
            journey_lines.append(fallback_line)
        self.daily_journey_label.setText("\n".join(journey_lines))
        reasons = tuple(daily.candidate_reasons)
        if reasons or daily.candidate_symbols:
            candidate_lines = []
            for index, symbol in enumerate(daily.candidate_symbols):
                reason = reasons[index] if index < len(reasons) else "來源未提供個別理由"
                candidate_lines.append(f"{symbol}：{reason}")
            if len(reasons) > len(daily.candidate_symbols):
                candidate_lines.extend(reasons[len(daily.candidate_symbols):])
            candidate_text = "\n".join(candidate_lines or reasons)
            suffix = (
                f"\n決策日：{daily.decision_date}｜"
                f"\n資料品質：{_daily_quality_text(daily.candidate_quality)}｜"
                f"資料日：{daily.candidate_data_date or '未知'}"
            )
            self.daily_candidate_detail_label.setText(
                "個股研究候選：\n"
                f"{candidate_text}{suffix}\n候選僅供研究；不代表已驗證、可成交或應下單。"
                f"\n下一步：{next_action}"
            )
        else:
            self.daily_candidate_detail_label.setText(
                "個股研究候選："
                "目前沒有可安全呈現的候選列；空結果不等於 Gate 已通過。"
            )
        self._sync_daily_candidate_open_controls()
        self.daily_watchlist_button.setEnabled(self.navigate_to_watchlist_callback is not None)
        self.daily_evidence_button.setEnabled(True)
        self.daily_detail_button.setEnabled(bool(daily.source_trace or daily.diagnostics))
        self.daily_trace_label.setText(self._format_daily_trace(daily))

    @staticmethod
    def _daily_candidate_source_identity(
        daily: WorkbenchDailyEvidence,
    ) -> tuple[object, ...]:
        """以每日 DTO 原有來源與列 identity 判斷是否可保留明選。"""

        return (
            daily.candidate_result_id,
            daily.candidate_source_id,
            daily.candidate_source_snapshot_id,
            daily.decision_date,
            daily.data_as_of_date,
            daily.candidate_data_date,
            tuple(daily.candidate_symbols),
            tuple(daily.candidate_identity),
        )

    @staticmethod
    def _daily_candidate_open_options(
        daily: WorkbenchDailyEvidence | None,
    ) -> tuple[str, ...]:
        if daily is None or str(daily.candidate_status).strip().lower() in {
            "read_failure",
            "stale",
            "future_blocked",
        }:
            return ()
        symbols = (str(symbol).strip() for symbol in daily.candidate_symbols)
        return tuple(dict.fromkeys(symbol for symbol in symbols if symbol))

    def _populate_daily_candidate_selector(
        self,
        daily: WorkbenchDailyEvidence | None,
    ) -> None:
        selector = self.daily_candidate_selector
        previous_identity = self._daily_candidate_selection_identity
        previous_code = selector.currentData()
        identity = self._daily_candidate_source_identity(daily) if daily is not None else None
        options = self._daily_candidate_open_options(daily)
        keep_previous = (
            identity is not None
            and identity == previous_identity
            and isinstance(previous_code, str)
            and previous_code in options
        )
        selected_code = (
            previous_code
            if keep_previous
            else options[0]
            if len(options) == 1
            else None
        )
        self._daily_candidate_selection_identity = identity

        was_blocked = selector.blockSignals(True)
        selector.clear()
        selector.addItem("請選擇研究股票", None)
        for stock_code in options:
            selector.addItem(stock_code, stock_code)
        selected_index = selector.findData(selected_code) if selected_code is not None else 0
        selector.setCurrentIndex(max(0, selected_index))
        selector.setEnabled(bool(options))
        selector.blockSignals(was_blocked)
        self._sync_daily_candidate_open_controls()

    def _daily_candidate_selection_is_openable(self) -> bool:
        daily = getattr(self, "_daily_investment_evidence", None)
        if daily is None or self.navigate_to_stock_research_callback is None:
            return False
        if self._daily_candidate_source_identity(daily) != self._daily_candidate_selection_identity:
            return False
        selected_code = self.daily_candidate_selector.currentData()
        return (
            isinstance(selected_code, str)
            and selected_code in self._daily_candidate_open_options(daily)
        )

    def _on_daily_candidate_selection_changed(self, _index: int) -> None:
        self._sync_daily_candidate_open_controls()

    def _sync_daily_candidate_open_controls(self) -> None:
        daily = getattr(self, "_daily_investment_evidence", None)
        options = self._daily_candidate_open_options(daily)
        selected_code = self.daily_candidate_selector.currentData()
        can_open = self._daily_candidate_selection_is_openable()
        if isinstance(selected_code, str) and selected_code in options:
            button_text = f"開啟 {selected_code} 個股研究報告"
        elif daily is not None and str(daily.candidate_status).strip().lower() == "read_failure":
            button_text = "候選來源讀取失敗"
        elif daily is not None and str(daily.candidate_status).strip().lower() in {
            "stale",
            "future_blocked",
        }:
            button_text = "候選資料日期不可用"
        elif options:
            button_text = "請先選擇研究股票"
        else:
            button_text = "開啟候選研究報告"
        self.daily_candidate_button.setText(button_text)
        self.daily_candidate_button.setEnabled(can_open)

        for key, target in getattr(self, "_today_action_targets", {}).items():
            if target == "stock_research":
                button = getattr(self, "today_action_buttons", {}).get(key)
                if button is not None:
                    button.setEnabled(can_open)
        if getattr(self, "_primary_action_target", "") == "stock_research":
            primary_button = getattr(self, "primary_action_button", None)
            if primary_button is not None:
                primary_button.setEnabled(can_open)

    def _style_daily_state(self, status: str) -> None:
        tone = _workbench_tone(status)
        self.daily_state_label.setStyleSheet(
            f"background: {tone['bg']}; color: {MIDNIGHT_ANALYST.text_secondary}; "
            f"border: 1px solid {tone['border']}; border-left: 4px solid {tone['fg']}; "
            f"border-radius: {MIDNIGHT_ANALYST.radius_panel}px; padding: 8px;"
        )

    def _format_daily_trace(self, daily: WorkbenchDailyEvidence) -> str:
        horizon_text = "；".join(
            f"{item.window_days}日 total={item.total}/ready={item.ready}/"
            f"waiting={item.pending}/missing={item.missing}"
            for item in daily.evidence_windows
        ) or "未知"
        lines = [
            "每日來源詳情（唯讀）",
            f"決策日={daily.decision_date}｜資料日={daily.data_as_of_date or '未知'}",
            f"候選 result_id={daily.candidate_result_id or '未知'}｜source_id={daily.candidate_source_id or '未知'}｜"
            f"source_snapshot_id={daily.candidate_source_snapshot_id or '未知'}",
            f"candidate identity：{'；'.join(daily.candidate_identity) or '未知'}",
            f"Evidence scope={daily.evidence_scope_start or '未知'}..{daily.evidence_scope_end or '未知'}｜"
            f"event_type={daily.evidence_event_type}｜require_cohort_identity={daily.evidence_require_cohort_identity}",
            f"events={daily.evidence_event_count}｜daily_events={daily.evidence_daily_event_count}｜"
            f"skipped_incomplete_identity={daily.evidence_skipped_incomplete_identity}",
            f"horizons：{horizon_text}",
            f"event_ids：{', '.join(daily.evidence_event_ids[:20]) or '無'}",
        ]
        if daily.learning is not None:
            learning = daily.learning
            lines.extend(
                (
                    f"learning schema={learning.schema_version}｜decision={learning.decision}｜"
                    f"decision_reason={learning.decision_reason or '未知'}",
                    f"candidate_id={learning.candidate_id or '無'}｜candidate_status={learning.candidate_status}｜"
                    f"active_pointer={learning.active_pointer_status}｜active_candidate_id={learning.active_candidate_id or '無'}",
                    f"receipt natural={learning.natural_matured_sample_count}｜"
                    f"candidate natural={learning.candidate_natural_matured_sample_count}｜"
                    f"active natural={learning.active_natural_matured_sample_count}｜"
                    f"cli_result_updated_at={learning.checked_at or '未知'}",
                )
            )
        if daily.learning_projection is not None:
            projection = daily.learning_projection
            lines.extend(
                (
                    f"learning projection lane={projection.cost_lane}｜status={projection.status}｜"
                    f"capture={projection.data_recorded_status}｜candidate={projection.candidate_id or '無'}",
                    f"learning next_gap={projection.next_gap}｜latest={projection.latest_evaluation_label}",
                )
            )
        if daily.research_fallback is not None:
            packet = daily.research_fallback
            lines.extend(
                (
                    "Research fallback packet（唯讀）",
                    f"status={packet.status}｜scope_key={packet.scope_key}｜"
                    f"decision_date={packet.decision_date or '未知'}｜cost_lane={packet.cost_lane}",
                    f"source_id={packet.source_id or '未知'}｜source_snapshot_id={packet.source_snapshot_id or '未知'}｜"
                    f"source_owner={packet.source_owner}｜owner_known={packet.source_owner_known}",
                    f"missing_reason={packet.missing_reason or '無'}",
                    f"research_question={packet.research_question or '未知'}",
                    f"next_step={packet.next_step or '未知'}",
                    f"revisit={packet.revisit_date or '未知'}｜status={packet.revisit_status}｜"
                    f"basis={packet.revisit_basis or '無'}｜reason={packet.revisit_reason or '未知'}",
                    f"natural_evidence_status={packet.natural_evidence_status}｜"
                    f"historical_research_allowed={packet.historical_research_allowed}",
                    "limitations：" + ("；".join(packet.limitations) or "無"),
                    "prohibited_actions：" + ("；".join(packet.prohibited_actions) or "無"),
                )
            )
        lines.append("source trace：" + ("\n".join(daily.source_trace) or "無"))
        lines.append("diagnostics：" + ("；".join(daily.diagnostics) or "無"))
        return "\n".join(lines)

    def _toggle_daily_detail(self, expanded: bool) -> None:
        self.daily_trace_label.setVisible(bool(expanded))
        self.daily_detail_button.setText(
            "收合每日來源詳情" if expanded else "查看每日來源詳情"
        )

    def _open_daily_candidate_research(self) -> bool:
        daily = getattr(self, "_daily_investment_evidence", None)
        callback = self.navigate_to_stock_research_callback
        if daily is None or callback is None or not self._daily_candidate_selection_is_openable():
            return False
        selected_code = self.daily_candidate_selector.currentData()
        stock_code = str(selected_code).strip() if isinstance(selected_code, str) else ""
        if not stock_code:
            return False
        callback(
            ResearchStockContextDTO(
                stock_code=stock_code,
                decision_date=daily.decision_date,
                data_date=daily.candidate_data_date or daily.data_as_of_date or daily.decision_date,
                result_id=daily.candidate_result_id or "",
                source_id=daily.candidate_source_id or daily.candidate_result_id or "",
                source_kind="scheduled_recommendation",
                source_label="每日推薦研究候選",
                source_workspace="recommendation",
            )
        )
        return True

    def _open_continuity_review_research(self, item: object) -> bool:
        """Open one due row through the existing exact stock research callback."""

        callback = self.navigate_to_stock_research_callback
        result_id = str(getattr(item, "result_id", "") or "").strip()
        stock_code = str(getattr(item, "stock_code", "") or "").strip()
        identity_status = str(getattr(item, "identity_status", "") or "").strip()
        if callback is None or not result_id or not stock_code or identity_status != "linked":
            return False
        decision_date = str(getattr(item, "decision_date", "") or "").strip()
        revision_id = str(
            getattr(item, "reminder_revision_id", "")
            or getattr(item, "revision_id", "")
            or ""
        ).strip()
        callback(
            ResearchStockContextDTO(
                stock_code=stock_code,
                decision_date=decision_date,
                # Continuity only records decision provenance; it must not
                # pretend that decision_date is a separately observed market
                # data date.  The shared report service owns its read cutoff.
                data_date="",
                result_id=result_id,
                identity_status=identity_status,
                source_snapshot_id=str(getattr(item, "source_snapshot_id", "") or "").strip(),
                source_snapshot_hash=str(getattr(item, "source_snapshot_hash", "") or "").strip(),
                source_id=revision_id,
                source_kind="decision_continuity_review",
                source_label="Workbench／到期研究檢討",
                source_workspace="workbench",
            )
        )
        return True

    def _build_today_action_center(self, parent_layout: QVBoxLayout) -> None:
        """建立首頁的任務導向入口；按鈕只切換既有工作區。"""

        panel = QFrame()
        panel.setObjectName("todayActionCenter")
        panel.setStyleSheet(
            f"#todayActionCenter {{ background: {MIDNIGHT_ANALYST.surface_1}; "
            f"border: 1px solid {MIDNIGHT_ANALYST.border}; "
            f"border-left: 4px solid {MIDNIGHT_ANALYST.accent}; "
            f"border-radius: {MIDNIGHT_ANALYST.radius_panel}px; }}"
        )
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 12, 14, 14)
        layout.setSpacing(10)

        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(10)
        copy_layout = QVBoxLayout()
        copy_layout.setContentsMargins(0, 0, 0, 0)
        copy_layout.setSpacing(2)
        self.today_action_title = QLabel("今日行動中心")
        title_font = QFont()
        title_font.setPointSize(15)
        title_font.setBold(True)
        self.today_action_title.setFont(title_font)
        self.today_action_title.setStyleSheet(f"color: {MIDNIGHT_ANALYST.text_primary};")
        self.today_action_hint_label = QLabel("")
        self.today_action_hint_label.setWordWrap(True)
        self.today_action_hint_label.setStyleSheet(
            f"color: {MIDNIGHT_ANALYST.text_secondary}; font-size: 11px;"
        )
        copy_layout.addWidget(self.today_action_title)
        copy_layout.addWidget(self.today_action_hint_label)
        header_layout.addLayout(copy_layout, 1)

        self.primary_action_button = QPushButton("開始今天的檢查")
        self.primary_action_button.setObjectName("todayPrimaryAction")
        self.primary_action_button.setProperty("variant", "primary")
        self.primary_action_button.setMinimumHeight(34)
        self.primary_action_button.setToolTip(
            "只會帶你前往既有工作區；不會更新資料、執行策略、寫入持倉或交易。"
        )
        self.primary_action_button.clicked.connect(self._open_primary_today_action)
        header_layout.addWidget(self.primary_action_button)

        self.refresh_button = QPushButton("重新整理狀態")
        self.refresh_button.setProperty("variant", "secondary")
        self.refresh_button.setMinimumHeight(34)
        self.refresh_button.setAccessibleName("重新整理工作台狀態")
        self.refresh_button.setAccessibleDescription(
            "重新讀取唯讀 Workbench 狀態；失敗時保留最後可信資料並標示 stale。"
        )
        self.refresh_button.setToolTip("重新讀取既有的唯讀工作台狀態。")
        self.refresh_button.clicked.connect(self.refresh_dashboard)
        header_layout.addWidget(self.refresh_button)
        layout.addWidget(header)

        cards_layout = QGridLayout()
        cards_layout.setContentsMargins(0, 0, 0, 0)
        cards_layout.setHorizontalSpacing(10)
        cards_layout.setVerticalSpacing(10)
        self.today_action_cards: dict[str, QFrame] = {}
        self.today_action_status_labels: dict[str, QLabel] = {}
        self.today_action_body_labels: dict[str, QLabel] = {}
        self.today_action_buttons: dict[str, QPushButton] = {}
        self._today_action_targets: dict[str, str] = {}
        self._primary_action_target = ""
        self.today_cards_layout = cards_layout

        specifications = (
            ("data", "資料狀態", "檢查今日資料是否可用", "查看數據更新", "update"),
            ("market", "市場判讀", "查看市場與今日待判讀事項", "開啟市場總覽", "daily_decision"),
            ("advice", "Advice 與候選", "確認今日是否已有可檢閱結果", "前往推薦分析", "recommendation"),
            ("portfolio", "持倉覆盤", "優先處理既有持倉的人工事項", "開啟持倉管理", "portfolio_review"),
        )
        for index, (key, title, description, button_text, target) in enumerate(specifications):
            card = self._make_today_action_card(
                key,
                title,
                description,
                button_text,
                target,
            )
            cards_layout.addWidget(card, index // 2, index % 2)
        layout.addLayout(cards_layout)
        parent_layout.addWidget(panel)

    def _make_today_action_card(
        self,
        key: str,
        title: str,
        description: str,
        button_text: str,
        target: str,
    ) -> QFrame:
        card = QFrame()
        card.setObjectName(f"todayActionCard_{key}")
        card.setMinimumHeight(128)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(5)
        title_label = QLabel(title)
        title_label.setStyleSheet(
            f"color: {MIDNIGHT_ANALYST.text_primary}; font-size: 12px; font-weight: 800;"
        )
        status_label = QLabel("等待狀態")
        status_label.setMinimumHeight(22)
        body_label = QLabel(description)
        body_label.setWordWrap(True)
        body_label.setStyleSheet(
            f"color: {MIDNIGHT_ANALYST.text_secondary}; font-size: 11px;"
        )
        button = QPushButton(button_text)
        button.setProperty("variant", "secondary")
        button.setMinimumHeight(28)
        button.clicked.connect(
            lambda _checked=False, action_key=key: self._open_today_action(action_key)
        )
        layout.addWidget(title_label)
        layout.addWidget(status_label)
        layout.addWidget(body_label, 1)
        layout.addWidget(button)
        self.today_action_cards[key] = card
        self.today_action_status_labels[key] = status_label
        self.today_action_body_labels[key] = body_label
        self.today_action_buttons[key] = button
        self._today_action_targets[key] = target
        self._set_today_action_card(
            key,
            status="等待狀態",
            body=description,
            tone="neutral",
            button_text=button_text,
            target=target,
        )
        return card

    def _set_today_action_card(
        self,
        key: str,
        *,
        status: str,
        body: str,
        tone: str,
        button_text: str,
        target: str,
    ) -> None:
        color = WORKBENCH_TONES.get(tone, WORKBENCH_TONES["neutral"])
        card = self.today_action_cards[key]
        card.setStyleSheet(
            f"QFrame#{card.objectName()} {{ background: {color['bg']}; "
            f"border: 1px solid {color['border']}; border-left: 4px solid {color['fg']}; "
            f"border-radius: {MIDNIGHT_ANALYST.radius_panel}px; }}"
        )
        status_label = self.today_action_status_labels[key]
        status_label.setText(status)
        status_label.setStyleSheet(
            f"color: {color['fg']}; font-size: 11px; font-weight: 800;"
        )
        self.today_action_body_labels[key].setText(body)
        button = self.today_action_buttons[key]
        button.setText(button_text)
        button.setEnabled(self._today_action_available(target))
        self._today_action_targets[key] = target

    def _render_today_action_center(self, dashboard: WorkbenchDashboardDTO | None) -> None:
        if dashboard is None:
            self.today_action_hint_label.setText(
                "正在等待工作台狀態；重新整理只會讀取既有資料，不會執行任何寫入。"
            )
            self.primary_action_button.setText("重新整理目前狀態")
            self.primary_action_button.setEnabled(self._today_action_available("refresh"))
            self._primary_action_target = "refresh"
            for key, status, body in (
                ("data", "等待狀態", "尚未取得資料狀態；可重新整理或前往數據更新確認。"),
                ("market", "等待狀態", "尚未取得市場判讀；資料載入後會顯示今日待判讀數。"),
                ("advice", "等待狀態", "尚未取得 Advice DTO；不把缺資料解讀為沒有風險。"),
                ("portfolio", "等待狀態", "尚未取得持倉覆盤項目；不會自行假定沒有持倉風險。"),
            ):
                self._set_today_action_card(
                    key,
                    status=status,
                    body=body,
                    tone="neutral",
                    button_text="重新整理狀態",
                    target="refresh",
                )
            return

        source_status = str(dashboard.market_context.get("source_status", "missing")).strip().lower()
        source_unavailable = source_status in {"", "missing", "blocked", "outage", "error"}
        if source_unavailable:
            self._set_today_action_card(
                "data",
                status="資料待確認",
                body="市場資料狀態尚未就緒；先確認更新與資料品質，再進行研究。",
                tone="warning",
                button_text="查看數據更新",
                target="update",
            )
        else:
            self._set_today_action_card(
                "data",
                status="資料可檢視",
                body=f"市場資料來源目前標示為 {display_workbench_value(source_status)}；仍請留意警告與日期。",
                tone="ready",
                button_text="查看數據更新",
                target="update",
            )

        review_count = len(dashboard.review_items)
        if review_count:
            self._set_today_action_card(
                "market",
                status=f"待判讀 {review_count} 項",
                body="先看市場總覽與既有風險訊號，再決定是否繼續研究候選。",
                tone="warning",
                button_text="開啟市場總覽",
                target="daily_decision",
            )
        else:
            self._set_today_action_card(
                "market",
                status="目前無待判讀",
                body="目前沒有明確人工項目；仍請查看背景機器提示、來源狀態與每日檢查清單。",
                tone="info",
                button_text="開啟市場總覽",
                target="daily_decision",
            )

        advice = dashboard.advice_dashboard
        advice_rows = tuple(getattr(advice, "recommendations", ())) if advice is not None else ()
        portfolio_rows = tuple(getattr(advice, "portfolio_rows", ())) if advice is not None else ()
        daily = dashboard.daily_evidence
        daily_candidate_count = daily.candidate_count if daily is not None else 0
        if advice is None:
            if daily_candidate_count:
                candidate_target = (
                    "stock_research"
                    if self.navigate_to_stock_research_callback is not None
                    else "watchlist"
                )
                self._set_today_action_card(
                    "advice",
                    status=f"已有 {daily_candidate_count} 檔研究候選",
                    body=(
                        "既有 scheduled snapshot 已提供研究候選，但尚未注入 AdviceDashboardDTO；"
                        "候選不是 current model、不是交易指令，請開啟個股研究報告。"
                    ),
                    tone=(
                        "machine_degraded"
                        if daily.candidate_status == "candidate_degraded"
                        else "machine_candidate"
                    ),
                    button_text=(
                        "開啟候選研究"
                        if candidate_target == "stock_research"
                        else "查看既有觀察清單"
                    ),
                    target=candidate_target,
                )
            else:
                self._set_today_action_card(
                    "advice",
                    status="尚未載入 Advice",
                    body="尚未有 Advice DTO；可到推薦分析建立並保存研究結果，不能以空白當成結論。",
                    tone="warning",
                    button_text="前往推薦分析",
                    target="recommendation",
                )
        elif not advice_rows and not portfolio_rows:
            self._set_today_action_card(
                "advice",
                status="目前無合格建議",
                body="這是正常的安全結果；請閱讀品質、限制與 Why Not，而非手動補值。",
                tone="info",
                button_text="檢視推薦分析",
                target="recommendation",
            )
        else:
            self._set_today_action_card(
                "advice",
                status=f"已載入 {len(advice_rows)} 筆結果",
                body="只讀呈現既有 Advice 與研究候選；請在原工作區檢閱完整理由與限制。",
                tone="ready",
                button_text="檢視推薦分析",
                target="recommendation",
            )

        action_count = _human_action_count(dashboard)
        machine_action_count = _machine_action_count(dashboard)
        if action_count:
            self._set_today_action_card(
                "portfolio",
                status=f"待覆盤 {action_count} 項",
                body=(
                    "已有持倉或風險相關的人工事項時，優先前往持倉管理檢查。"
                    f"另有機器證據狀態 {machine_action_count} 項，不需人工簽核。"
                ),
                tone="warning",
                button_text="開啟持倉管理",
                target="portfolio_review",
            )
        else:
            self._set_today_action_card(
                "portfolio",
                status=(
                    f"目前無人工待覆盤；機器狀態 {machine_action_count} 項"
                    if machine_action_count
                    else "目前無待覆盤項目"
                ),
                body=(
                    "目前沒有明確 human_review 項目；機器來源缺件或自然等待不會被標成人工。"
                    if machine_action_count
                    else "沒有 Action Item 不代表持倉風險為零；可在持倉管理進行人工確認。"
                ),
                tone="warning" if machine_action_count else "info",
                button_text="開啟持倉管理",
                target="portfolio_review",
            )

        if source_unavailable:
            primary_label, primary_target = "先確認資料狀態", "update"
        elif action_count:
            primary_label, primary_target = "先檢查持倉事項", "portfolio_review"
        elif advice is None and daily_candidate_count:
            primary_target = (
                "stock_research"
                if self.navigate_to_stock_research_callback is not None
                else "watchlist"
            )
            primary_label = "開啟今天的候選研究"
        elif review_count:
            primary_label, primary_target = f"查看 {review_count} 項今日待判讀", "daily_decision"
        elif advice is None:
            primary_label, primary_target = "建立今天的研究候選", "recommendation"
        else:
            primary_label, primary_target = "前往市場總覽", "daily_decision"
        self.today_action_hint_label.setText(
            f"建議下一步：{primary_label}。此入口只導覽，不會自動更新資料、執行策略或交易。"
        )
        self.primary_action_button.setText(primary_label)
        self.primary_action_button.setEnabled(self._today_action_available(primary_target))
        self._primary_action_target = primary_target

    def _today_action_available(self, target: str) -> bool:
        if target == "market_explore":
            return self.navigate_to_market_explore_callback is not None
        if target == "refresh":
            return self.source_service is not None
        if target == "update":
            return self.navigate_to_update_callback is not None
        if target == "recommendation":
            return self.navigate_to_recommendation_callback is not None
        if target == "stock_research":
            return self._daily_candidate_selection_is_openable()
        if target == "watchlist":
            return self.navigate_to_watchlist_callback is not None
        legacy_target = WORKBENCH_LEGACY_DRILLDOWN_TARGETS.get(target, target)
        callbacks: dict[str, Callable[[], None] | None] = {
            "daily_decision": self.navigate_to_daily_decision_callback,
            "evidence_review": self.navigate_to_evidence_review_callback,
            "portfolio": self.navigate_to_portfolio_callback,
        }
        return callbacks.get(legacy_target) is not None

    def _open_today_action(self, key: str) -> None:
        target = self._today_action_targets.get(key, "")
        if target == "refresh":
            self.refresh_dashboard()
            return
        self.navigate_to_drilldown_target(target)

    def _open_primary_today_action(self) -> None:
        target = self._primary_action_target
        if target == "refresh":
            self.refresh_dashboard()
            return
        self.navigate_to_drilldown_target(target)

    def _make_summary_block(self, key: str, title: str) -> QWidget:
        block = QWidget()
        block.setObjectName("workbenchSummaryBlock")
        block.setStyleSheet(
            f"#workbenchSummaryBlock {{ background: {MIDNIGHT_ANALYST.surface_2}; "
            f"border: 1px solid {MIDNIGHT_ANALYST.border}; "
            f"border-radius: {MIDNIGHT_ANALYST.radius_panel}px; }}"
        )
        layout = QVBoxLayout(block)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(3)

        title_label = QLabel(title)
        title_label.setStyleSheet(f"color: {MIDNIGHT_ANALYST.text_muted}; font-size: 10px; font-weight: 600;")
        value_label = QLabel("-")
        value_font = QFont()
        value_font.setPointSize(14)
        value_font.setBold(True)
        value_label.setFont(value_font)
        value_label.setStyleSheet(f"color: {MIDNIGHT_ANALYST.text_primary};")
        detail_label = QLabel("")
        detail_label.setWordWrap(True)
        detail_label.setStyleSheet(f"color: {MIDNIGHT_ANALYST.text_secondary}; font-size: 10px;")

        layout.addWidget(title_label)
        layout.addWidget(value_label)
        layout.addWidget(detail_label)
        if key == "waiting":
            block.setToolTip(
                "【等待真實時間】\n"
                "系統當前正處於 waiting_for_time 階段，Paper Portfolio 正處於第 1 週的累積與驗證中。"
            )
        self.summary_blocks[key] = block
        self.summary_value_labels[key] = value_label
        self.summary_detail_labels[key] = detail_label
        return block

    def _make_drilldown_button(
        self,
        text: str,
        callback: Callable[[], None] | None,
        tooltip: str,
    ) -> QPushButton:
        button = QPushButton(text)
        button.setProperty("variant", "secondary")
        button.setToolTip(tooltip)
        button.setEnabled(callback is not None)
        if callback is not None:
            button.clicked.connect(callback)
        return button

    def _on_subtab_changed(self, index: int) -> None:
        if self.subtabs.widget(index) is self.research_console_view:
            self.research_console_view.ensure_loaded()

    def begin_shutdown(self) -> None:
        """停止排隊中的唯讀 refresh，並合作式取消正在執行的讀取。"""

        if self._shutdown_requested:
            return
        self._shutdown_requested = True
        self._position_health_navigation_source = None
        self._position_health_navigation_id = None
        self.position_health_open_portfolio_button.setEnabled(False)
        self._refresh_generation += 1
        self._refresh_pending = False
        worker = self._refresh_worker
        if worker is not None:
            try:
                if worker.isRunning():
                    worker.cancel(cooperative=True, wait=False)
            except RuntimeError:
                self._refresh_worker = None
        self.research_console_view.begin_shutdown()

    def refresh_dashboard(self) -> None:
        self._position_health_navigation_source = None
        self._position_health_navigation_id = None
        self.position_health_open_portfolio_button.setEnabled(False)
        if self.source_service is None:
            self._display_exception_dashboard("WorkbenchSourceService 不可用")
            return
        if self._shutdown_requested:
            return
        if self._async_refresh:
            self._start_async_dashboard_refresh()
            return
        self.refresh_button.setEnabled(False)
        try:
            dashboard = self.source_service.inspect(
                decision_date=self.decision_date,
                replay_summary_json=self.replay_summary_json,
            )
        except Exception as exc:  # noqa: BLE001
            self._display_exception_dashboard(str(exc))
        else:
            self.render_dashboard(cast(WorkbenchDashboardDTO, dashboard))
        finally:
            self.refresh_button.setEnabled(True)

    def _start_async_dashboard_refresh(self) -> None:
        if self.source_service is None or self._shutdown_requested:
            return
        # 每次 refresh request 都先使舊結果失效，即使取消回呼尚在排隊。
        self._refresh_generation += 1
        generation = self._refresh_generation
        worker = self._refresh_worker
        if worker is not None:
            try:
                if worker.isRunning():
                    self._refresh_pending = True
                    worker.cancel(cooperative=True, wait=False)
                    self.meta_label.setText(
                        "正在取消較早的唯讀讀取，完成後會載入最新狀態。"
                    )
                    return
            except RuntimeError:
                self._refresh_worker = None

        requested_date = self.decision_date
        worker = TaskWorker(
            _inspect_workbench_dashboard,
            self.source_service,
            requested_date,
            self.replay_summary_json,
        )
        worker.native_thread_finished.connect(worker.deleteLater)
        worker.finished.connect(
            lambda dashboard, current_generation=generation, current_date=requested_date: self._on_async_dashboard_finished(
                current_generation, current_date, dashboard
            ),
            Qt.ConnectionType.QueuedConnection,
        )
        worker.error.connect(
            lambda error, current_generation=generation, current_date=requested_date: self._on_async_dashboard_error(
                current_generation, current_date, error
            ),
            Qt.ConnectionType.QueuedConnection,
        )
        worker.cancelled.connect(
            lambda current_generation=generation: self._on_async_dashboard_cancelled(
                current_generation
            ),
            Qt.ConnectionType.QueuedConnection,
        )
        worker.native_thread_finished.connect(
            lambda current_worker=worker: self._on_async_dashboard_thread_finished(
                current_worker
            ),
            Qt.ConnectionType.QueuedConnection,
        )
        self._refresh_worker = worker
        self.refresh_button.setEnabled(False)
        if self._last_good_dashboard is None:
            self._display_pending_dashboard()
            self.refresh_button.setEnabled(False)
        else:
            self.meta_label.setText(
                "正在背景重新讀取既有唯讀狀態；目前保留最後可信結果。"
            )
            self.priority_banner.setText(
                "資料狀態：更新中；目前仍顯示最後可信 Workbench DTO。"
            )
        worker.start()

    def _on_async_dashboard_finished(
        self,
        generation: int,
        requested_date: str | None,
        dashboard: object,
    ) -> None:
        if self._shutdown_requested or generation != self._refresh_generation:
            return
        if requested_date != self.decision_date:
            self._refresh_pending = True
            return
        if not isinstance(dashboard, WorkbenchDashboardDTO):
            self._on_async_dashboard_error(
                generation,
                requested_date,
                "WorkbenchSourceService 回傳非 WorkbenchDashboardDTO。",
            )
            return
        self.render_dashboard(dashboard)

    def _on_async_dashboard_error(
        self,
        generation: int,
        requested_date: str | None,
        error_message: str,
    ) -> None:
        if self._shutdown_requested or generation != self._refresh_generation:
            return
        if requested_date != self.decision_date:
            self._refresh_pending = True
            return
        self._display_exception_dashboard(error_message)

    def _on_async_dashboard_cancelled(self, generation: int) -> None:
        if generation != self._refresh_generation or self._shutdown_requested:
            return
        if not self._refresh_pending:
            self.meta_label.setText("唯讀讀取已取消；目前資料狀態維持原樣。")

    def _on_async_dashboard_thread_finished(self, worker: TaskWorker) -> None:
        if self._refresh_worker is not worker:
            try:
                worker.deleteLater()
            except RuntimeError:
                pass
            return
        self._refresh_worker = None
        should_refresh = self._refresh_pending and not self._shutdown_requested
        self._refresh_pending = False
        try:
            worker.deleteLater()
        except RuntimeError:
            pass
        if not self._shutdown_requested:
            self.refresh_button.setEnabled(self.source_service is not None)
        if should_refresh:
            QTimer.singleShot(0, self.refresh_dashboard)

    def navigate_to_drilldown_target(self, target: str) -> bool:
        if target == "market_explore":
            if self.navigate_to_market_explore_callback is None:
                return False
            self.navigate_to_market_explore_callback()
            return True
        if target == "update" and hasattr(self, "navigate_to_update_callback") and self.navigate_to_update_callback:
            self.navigate_to_update_callback()
            return True
        if target == "recommendation" and hasattr(self, "navigate_to_recommendation_callback") and self.navigate_to_recommendation_callback:
            self.navigate_to_recommendation_callback()
            return True
        if target == "stock_research":
            return self._open_daily_candidate_research()

        legacy_target = WORKBENCH_LEGACY_DRILLDOWN_TARGETS.get(str(target), str(target))
        callbacks: dict[str, Callable[[], None] | None] = {
            "daily_decision": self.navigate_to_daily_decision_callback,
            "evidence_review": self.navigate_to_evidence_review_callback,
            "portfolio": self.navigate_to_portfolio_callback,
            "watchlist": self.navigate_to_watchlist_callback,
        }
        callback = callbacks.get(str(legacy_target))
        if callback is None:
            return False
        callback()
        return True

    def _navigate_model_row(self, model, row: int) -> None:
        item = model.row_at(row)
        if item is None:
            return
        self._show_model_row_detail(model, row)
        if model is self.review_model and hasattr(item, "item_id"):
            self._viewed_review_item_ids.add(str(item.item_id))
            self.review_state_label.setText(self._review_queue_state_text(self._dashboard))
        if model is self.review_model and str(getattr(item, "source", "")) == "continuity_review":
            # 連續性覆盤列有自己的精確來源身份，不借用每日候選選擇。
            self._open_continuity_review_research(item)
            return
        target = getattr(item, "drilldown_target", "")
        self.navigate_to_drilldown_target(str(target))

    def _show_model_row_detail(self, model, row: int) -> None:
        item = model.row_at(row)
        if item is None:
            self._set_detail_placeholder("尚未選取項目", "請點選左側任一列查看完整來源追蹤與診斷訊號。")
            return
        title = _detail_title(item)
        status = _detail_status(item)
        target = str(getattr(item, "drilldown_target", "") or "")
        self._selected_detail_target = target
        self._selected_detail_item = item
        self.detail_title_label.setText(_detail_display_title(title))
        self.detail_status_label.setText(
            f"狀態：{display_workbench_value(status)}"
            + (f" | 下鑽：{display_workbench_value(target)}" if target else "")
        )
        self._apply_detail_tone(status)
        self._set_detail_sections(item)
        self.detail_body_label.setText(_format_detail_body(item))
        self.detail_drilldown_button.setEnabled(bool(target))

    def _toggle_detail_technical(self, expanded: bool) -> None:
        self.detail_body_label.setVisible(bool(expanded))
        self.detail_technical_button.setText(
            "收合技術欄位（DTO raw）" if expanded else "查看技術欄位（DTO raw）"
        )

    def _set_detail_placeholder(self, title: str, body: str) -> None:
        self._selected_detail_target = ""
        self._selected_detail_item = None
        self.detail_title_label.setText(_detail_display_title(title))
        self.detail_status_label.setText("狀態：等待選取")
        self.detail_status_badge.setText("WAIT")
        self._apply_detail_tone("info")
        self.detail_summary_box.setText(f"重點摘要\n{body}")
        self.detail_source_box.setText("來源與邊界\n等待 WorkbenchDashboardDTO。")
        self.detail_diagnostics_box.setText("診斷訊號\n尚無可檢視項目。")
        self.detail_body_label.setText(body)
        self.detail_technical_button.setChecked(False)
        self.detail_drilldown_button.setEnabled(False)

    def _open_selected_detail_target(self) -> None:
        item = getattr(self, "_selected_detail_item", None)
        if item is not None and str(getattr(item, "source", "")) == "continuity_review":
            self._open_continuity_review_research(item)
            return
        target = self._selected_detail_target
        if target:
            self.navigate_to_drilldown_target(target)

    def render_dashboard(self, dashboard: WorkbenchDashboardDTO) -> None:
        self._dashboard = dashboard
        self._last_good_dashboard = dashboard
        self._last_good_dashboard_loaded_at = datetime.now().astimezone()
        self._dashboard_stale = False
        self.refresh_button.setEnabled(self.source_service is not None)
        self.boundary_banner.setText(
            "安全與唯讀邊界：這裡只整理既有狀態與導覽；不是交易建議，不會寫 DB、執行策略或交易；"
            "Advice 僅呈現已注入 DTO、不執行 Policy；不重算 scoring / portfolio / backtest / lifecycle。"
        )
        self.boundary_banner.setToolTip(
            "資料只由 WorkbenchSourceService / WorkbenchDashboardDTO 供應；"
            "不寫 DB、不啟用正式排程器、不是交易建議；Advice 僅呈現已注入 DTO，"
            "不重算 scoring / portfolio / backtest / lifecycle。"
        )
        self._render_guided_home(dashboard)
        self._set_summary_blocks(dashboard)
        self._set_priority_banner(dashboard)
        self._render_daily_investment_journey(dashboard.daily_evidence)
        self._render_position_health(dashboard.position_health)
        self.research_console_view.set_decision_date(dashboard.as_of_date.isoformat())
        self._render_today_action_center(dashboard)
        self.meta_label.setText(
            f"工作台 as_of={dashboard.as_of_date.isoformat()} | "
            f"保存快照日={_optional_date_text(dashboard.snapshot_date)} | "
            f"行情截至={_optional_date_text(dashboard.market_data_as_of_date)} | "
            f"台北評估日={_optional_date_text(dashboard.evaluation_date)} | "
            f"最新快照擷取={_latest_capture_status_text(dashboard)} | "
            f"產生時間={dashboard.generated_at.isoformat()} | "
            f"來源模式={display_workbench_value(dashboard.source_mode)} | "
            f"允許寫入={_yes_no(dashboard.access_boundary.writes_allowed)} | "
            f"正式排程器={_yes_no(dashboard.access_boundary.production_scheduler_allowed)}"
        )
        self.meta_label.setToolTip(self._format_workbench_source_meta(dashboard))
        self.status_model.set_rows(dashboard.status_strip)
        self._render_advice(dashboard)
        self.review_model.set_rows(dashboard.review_items)
        self.review_state_label.setText(self._review_queue_state_text(dashboard))
        has_review_items = bool(dashboard.review_items)
        self.review_empty_state.setVisible(not has_review_items)
        if not has_review_items:
            self._set_review_empty_state(dashboard)
        self.review_table.setVisible(has_review_items)
        self.evidence_feed_model.set_rows(dashboard.background_evidence_feed)
        self.action_item_model.set_rows(dashboard.action_items)
        self.operating_loop_model.set_rows(dashboard.operating_loop_steps)
        self.evidence_feed_state_label.setText(_evidence_feed_state_text(dashboard))
        self.action_item_state_label.setText(_action_item_state_text(dashboard))
        self.operating_loop_state_label.setText(_operating_loop_state_text(dashboard))
        self.evidence_model.set_rows(dashboard.evidence_summary)
        self.checklist_model.set_rows(dashboard.daily_checklist)
        self._update_evidence_summary_cards(dashboard)
        self._render_operating_loop(dashboard.operating_loop_steps)
        self._render_checklist(dashboard.daily_checklist)
        self.warning_list.set_warnings(tuple(_humanize_warning(item) for item in dashboard.warnings))
        self._show_initial_detail(dashboard)
        self._resize_tables()

    def _render_position_health(
        self,
        health: PositionHealthReadModel | None,
    ) -> None:
        """只呈現 WorkbenchSourceService 已驗證的共用 health projection。"""

        self._position_health_navigation_source = health
        self._position_health_navigation_id = None
        self.position_health_open_portfolio_button.setEnabled(False)
        self.position_health_detail_button.blockSignals(True)
        self.position_health_detail_button.setChecked(False)
        self.position_health_detail_button.blockSignals(False)
        self.position_health_detail_label.setVisible(False)
        if health is None:
            self.position_health_model.set_rows(())
            self.position_health_table.setVisible(False)
            self.position_health_summary_label.setText(
                "Paper Position Health：未知；尚未有 source-backed read model。"
            )
            self.position_health_detail_button.setEnabled(False)
            self.position_health_detail_label.setText("尚未載入 Position Health receipt。")
            return

        self.position_health_model.set_rows(health.positions)
        self.position_health_table.setVisible(bool(health.positions))
        self.position_health_summary_label.setText(
            format_position_health_read_model(health)
        )
        self.position_health_detail_button.setEnabled(bool(health.positions))
        self.position_health_detail_label.setText(
            self._format_position_health_detail(health)
        )

    def _show_position_health_row(self, index) -> None:
        item = self.position_health_model.row_at(index.row())
        if item is None:
            self._position_health_navigation_id = None
            self.position_health_open_portfolio_button.setEnabled(False)
            return
        self._position_health_navigation_id = item.position_id
        self.position_health_open_portfolio_button.setEnabled(
            self._selected_position_health_navigation() is not None
        )
        self.position_health_detail_label.setText(
            format_position_health_presentation(item)
            + "\n\n來源 hash："
            + ("；".join(f"{key}={value}" for key, value in item.source_hashes) or "未提供")
            + "\n來源追溯："
            + ("；".join(item.source_trace) or "未提供")
        )
        self.position_health_detail_button.setChecked(True)

    def _selected_position_health_navigation(self) -> tuple[PositionHealthReadModel, str] | None:
        """只交接明選的同版本 Paper 評估，不能以同股票猜部位。"""

        source = self._position_health_navigation_source
        position_id = self._position_health_navigation_id
        if (
            self._shutdown_requested
            or self._dashboard_stale
            or not callable(self.navigate_to_portfolio_position_callback)
            or not isinstance(source, PositionHealthReadModel)
            or not source.is_readable
            or source.portfolio_id != "paper-main"
            or not source.research_only
            or source.apply_transition
            or source.auto_action_allowed
            or source.broker_execution
            or source.formal_credit
            or not source.decision_date
            or not source.source_snapshot_id
            or not position_id
        ):
            return None
        if any(
            not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None
            for value in (source.receipt_sha256, source.result_sha256, source.source_snapshot_rows_sha256)
        ):
            return None
        matches = tuple(row for row in source.positions if row.position_id == position_id)
        if (
            len(matches) != 1
            or not matches[0].is_identity_verified
            or not matches[0].stock_code.strip()
            or matches[0].decision_date != source.decision_date
            or matches[0].source_snapshot_id != source.source_snapshot_id
        ):
            return None
        return source, position_id

    def _open_selected_position_health(self) -> bool:
        selected = self._selected_position_health_navigation()
        if selected is None:
            self.position_health_open_portfolio_button.setEnabled(False)
            return False
        callback = self.navigate_to_portfolio_position_callback
        if callback is None:
            return False
        if callback(*selected) is False:
            self.position_health_detail_label.setText(
                "未能定位此份 Paper 評估；請核對原來源與持倉頁狀態，未改選手動帳的同股票。"
            )
            self.position_health_detail_button.setChecked(True)
            return False
        return True

    def _toggle_position_health_detail(self, expanded: bool) -> None:
        self.position_health_detail_label.setVisible(bool(expanded))
        self.position_health_detail_button.setText(
            "收合 Position Health 技術詳情"
            if expanded
            else "查看 Position Health 技術詳情"
        )

    def _format_position_health_detail(self, health) -> str:
        lines = [
            "Position Health receipt 詳情（唯讀）",
            f"receipt：{health.receipt_path or '未知'}",
            f"result：{health.result_path or '未知'}",
            f"result hash：{health.result_sha256 or '未知'}",
            f"receipt bytes hash：{health.receipt_sha256 or '未知'}",
            f"source snapshot：{health.source_snapshot_id or '未知'}",
            f"source rows hash：{health.source_snapshot_rows_sha256 or '未知'}",
            f"安全邊界：research_only={health.research_only}；"
            f"apply_transition={health.apply_transition}；"
            f"auto_action_allowed={health.auto_action_allowed}；"
            f"broker_execution={health.broker_execution}；"
            f"formal_credit={health.formal_credit}",
        ]
        if health.warnings:
            lines.append("警告：" + "；".join(health.warnings))
        if health.blockers:
            lines.append("阻擋：" + "；".join(health.blockers))
        return "\n".join(lines)

    def _set_advice_state(self, state: str, extra_msg: str = ""):
        self._clear_advice_presentation_selection()
        if state == "WAITING_FOR_ADVICE_DTO":
            self.advice_empty_label.setText(
                "<b>【狀態：WAITING_FOR_ADVICE_DTO】</b><br/>"
                "尚未載入 Advice DTO。請先完成資料更新，並至「推薦分析」頁執行策略篩選與保存，或使用下方導引按鈕。"
            )
            self.advice_empty_widget.setVisible(True)
            self.advice_recommendation_table.setVisible(False)
            self.advice_candidate_label.setVisible(False)
            self.advice_candidate_table.setVisible(False)
            self.advice_portfolio_table.setVisible(False)
            self.advice_summary.setText("等待 AdviceDashboardDTO；UI 不執行 Policy 或核心計算。")
            self.advice_presentation_detail.setText(
                "共用證據詳情：等待 AdviceDashboardDTO；沒有資料不等於沒有風險。"
            )

        elif state == "NO_ELIGIBLE_ADVICE":
            reasons_str = f" | 原因: {extra_msg}" if extra_msg else ""
            self.advice_empty_label.setText(
                "<b>【狀態：NO_ELIGIBLE_ADVICE】</b><br/>"
                f"目前無符合條件之 Advice 建議{reasons_str}。<br/>"
                "這可能是由於今日策略條件過於嚴格、資料品質未達 Gate 閥值、或可成交性不足所導致的正常空結果。"
            )
            self.advice_empty_widget.setVisible(True)
            self.advice_recommendation_table.setVisible(False)
            self.advice_candidate_label.setVisible(False)
            self.advice_candidate_table.setVisible(False)
            self.advice_portfolio_table.setVisible(False)
            self.advice_summary.setText("無可用建議；UI 不執行 Policy。")
            self.advice_presentation_detail.setText(
                "共用證據詳情：目前沒有合格 Advice；不補排名、機率或成本後結果。"
            )

        elif state == "ADVICE_DTO_ERROR":
            self.advice_empty_label.setText(
                "<b>【狀態：ADVICE_DTO_ERROR】</b><br/>"
                f"載入 Advice DTO 發生錯誤或安全診斷攔截（{extra_msg or 'DTO 載入降級'}）。<br/>"
                "請點擊下方『重新載入』或檢查底層服務日誌；不可保留可能過期的舊表格而不標示 stale。"
            )
            self.advice_empty_widget.setVisible(True)
            self.advice_recommendation_table.setVisible(False)
            self.advice_candidate_label.setVisible(False)
            self.advice_candidate_table.setVisible(False)
            self.advice_portfolio_table.setVisible(False)
            self.advice_summary.setText("Advice 載入錯誤或降級。")
            self.advice_presentation_detail.setText(
                "共用證據詳情：Advice DTO 狀態未知；請重新載入來源，不保留舊結論。"
            )

        elif state == "READY":
            self.advice_empty_widget.setVisible(False)
            self.advice_recommendation_table.setVisible(True)
            self.advice_candidate_label.setVisible(True)
            self.advice_candidate_table.setVisible(True)
            self.advice_portfolio_table.setVisible(True)

    def _render_advice(self, dashboard: WorkbenchDashboardDTO) -> None:
        advice = dashboard.advice_dashboard
        if advice is None:
            self._set_advice_state("WAITING_FOR_ADVICE_DTO")
            return

        formal_rows = tuple(
            row for row in advice.recommendations
            if row.classification is AdviceClassification.FORMAL_ADVICE
        )
        candidate_rows = tuple(
            row for row in advice.recommendations
            if row.classification is AdviceClassification.PROFESSIONAL_CANDIDATE
        )
        portfolio_rows = advice.portfolio_rows if hasattr(advice, "portfolio_rows") else ()

        total_rows = len(formal_rows) + len(candidate_rows) + len(portfolio_rows)
        if total_rows == 0:
            self._set_advice_state("NO_ELIGIBLE_ADVICE", ", ".join(advice.warnings) or "無合格標的")
            return

        self._set_advice_state("READY")
        self.advice_summary.setText(
            "Advice 唯讀邊界：僅呈現已注入 AdviceDashboardDTO；"
            f"mode={advice.mode.value} | decision_date={advice.decision_date} | "
            f"data_as_of_date={advice.data_as_of_date} | "
            f"warnings={', '.join(advice.warnings) or 'none'} | "
            f"正式 Advice {len(formal_rows)} 筆 | Professional 研究候選 {len(candidate_rows)} 筆 | "
            + "；".join(
                f"{row.stock_code or 'portfolio'} {row.advice_action.value} "
                f"{', '.join(row.why_not_reasons or row.refusal_reasons)} "
                f"quality={row.data_quality} feasibility={row.execution_feasibility}"
                for row in formal_rows
            )
        )
        self.advice_recommendation_model.set_rows(formal_rows)
        self.advice_candidate_model.set_rows(candidate_rows)
        self.advice_portfolio_model.set_rows(portfolio_rows)
        self.advice_presentation_detail.setText(
            "共用證據詳情：選取 Advice 或研究候選列後顯示；"
            "缺少校準／成本後機率時維持不可用，不從排名分數推導。"
        )

    def _clear_advice_presentation_selection(self) -> None:
        self._selected_advice_presentation = None
        if hasattr(self, "advice_lineage_button"):
            self.advice_lineage_button.blockSignals(True)
            self.advice_lineage_button.setChecked(False)
            self.advice_lineage_button.blockSignals(False)
            self.advice_lineage_button.setEnabled(False)

    def _render_advice_presentation_detail(self) -> None:
        presentation = self._selected_advice_presentation
        if presentation is None:
            return
        detail = "共用證據詳情（唯讀）\n" + format_decision_presentation(presentation)
        if self.advice_lineage_button.isChecked():
            detail += "\n\n" + format_decision_lineage_detail(presentation)
        self.advice_presentation_detail.setText(detail)

    def _toggle_advice_lineage(self, expanded: bool) -> None:
        del expanded
        self._render_advice_presentation_detail()

    def _show_advice_row_presentation(self, model, row: int) -> None:
        """在 Workbench 直接展示共用 DTO；無法適配時 fail closed。"""

        item = model.row_at(row)
        if item is None:
            self._clear_advice_presentation_selection()
            self.advice_presentation_detail.setText("共用證據詳情：尚未選取有效 Advice DTO。")
            return
        try:
            presentation = self.presentation_service.from_advice(item)
        except (TypeError, ValueError) as exc:
            self._clear_advice_presentation_selection()
            self.advice_presentation_detail.setText(
                f"共用證據詳情：Advice DTO 無法安全適配（{exc}）；請回到來源頁檢查。"
            )
            return
        self._selected_advice_presentation = presentation
        self.advice_lineage_button.setEnabled(True)
        self._render_advice_presentation_detail()

    def _show_initial_detail(self, dashboard: WorkbenchDashboardDTO) -> None:
        if self.evidence_feed_model.rowCount() > 0:
            self._show_model_row_detail(self.evidence_feed_model, 0)
            return
        if self.review_model.rowCount() > 0:
            self._show_model_row_detail(self.review_model, 0)
            return
        if self.action_item_model.rowCount() > 0:
            self._show_model_row_detail(self.action_item_model, 0)
            return
        if self.operating_loop_model.rowCount() > 0:
            self._show_model_row_detail(self.operating_loop_model, 0)
            return
        self._set_detail_placeholder(
            "目前沒有可檢視項目",
            (
                f"決策日期：{dashboard.as_of_date.isoformat()}\n"
                "Workbench 仍維持唯讀；沒有清單列不代表 Phase gate 完成。"
            ),
        )

    def _display_pending_dashboard(self) -> None:
        self.refresh_button.setEnabled(self.source_service is not None)
        self._render_guided_home(None)
        self._render_daily_investment_journey(None)
        self._render_position_health(None)
        self._render_today_action_center(None)
        self.boundary_banner.setText(
            "安全邊界：正在等待既有工作台狀態；不會將缺資料解讀為可交易結果。"
        )
        self._set_summary_placeholder("等待 DTO", "尚未載入 WorkbenchDashboardDTO")
        self.meta_label.setText("工作台尚未載入。")
        self.evidence_boundary_card.value_label.setText("等待 WorkbenchDashboardDTO。")
        self.evidence_coverage_card.value_label.setText("UI 不直接讀 DB、不啟用排程器，也不執行 replay。")
        self.evidence_feed_state_label.setText(
            "目前沒有背景證據列：等待 WorkbenchDashboardDTO；UI 不讀 DB、不執行 replay、不補資料。"
        )
        self.action_item_state_label.setText(
            "目前沒有人工待處理事項：等待 WorkbenchDashboardDTO；Workbench 不寫 DB、不標記完成，也不是買賣建議。"
        )
        self.operating_loop_state_label.setText(
            "尚未有操作節奏 payload：等待 WorkbenchDashboardDTO；只讀、不寫 DB、不標記完成。"
        )
        self.evidence_feed_model.set_rows(())
        self.advice_recommendation_model.set_rows(())
        self.advice_candidate_model.set_rows(())
        self.advice_portfolio_model.set_rows(())
        self._set_advice_state("WAITING_FOR_ADVICE_DTO")
        self.review_model.set_rows(())
        self.review_state_label.setText(
            "今日待判讀佇列尚未載入；等待 WorkbenchDashboardDTO。UI 不讀 DB、不執行 replay。"
        )
        self.review_empty_state.setVisible(True)
        self.review_table.setVisible(False)
        self._set_review_empty_state(None)
        self.action_item_model.set_rows(())
        self.operating_loop_model.set_rows(())
        self.warning_list.set_warnings(())
        self._set_detail_placeholder("等待 DTO", "請先重新載入 WorkbenchDashboardDTO。")

    def _set_review_empty_state(self, dashboard: WorkbenchDashboardDTO | None) -> None:
        """Keep a machine-only/unknown queue from looking like a green pass."""

        if dashboard is not None:
            machine_action_count = _machine_action_count(dashboard)
            machine_background_count = _machine_background_count(dashboard)
            machine_attention_count = machine_action_count + machine_background_count
            if machine_attention_count:
                self.review_empty_state.title_label.setText("目前無人工判讀；機器狀態待處理")
                self.review_empty_state.body_label.setText(
                    f"目前有 {machine_attention_count} 項機器來源缺件、自然等待、降級或市場批次提示。"
                    "這些狀態不需要具名人工簽核，也不能解讀為風險已確認；"
                    "請依背景證據、來源與時間條件重新整理。"
                )
                return
            self.review_empty_state.title_label.setText("目前沒有明確人工判讀項目")
            self.review_empty_state.body_label.setText(
                "今日待判讀佇列目前為空；請查看背景證據流與每日檢查清單。"
                "空佇列不代表風險已確認、Phase gate 已完成或可以交易。"
            )
            return

        self.review_empty_state.title_label.setText("狀態未知，不能判定風險")
        self.review_empty_state.body_label.setText(
            "尚無可信 Workbench DTO；請聚焦 Retry，不把空佇列解讀為風險已確認。"
        )

    def _display_exception_dashboard(self, error_message: str) -> None:
        if self._last_good_dashboard is not None:
            self._dashboard = self._last_good_dashboard
            self._dashboard_stale = True
            last_good_at = (
                self._last_good_dashboard_loaded_at.isoformat()
                if self._last_good_dashboard_loaded_at is not None
                else "未知"
            )
            dashboard = self._last_good_dashboard
            self._render_guided_home(dashboard)
            self._set_summary_blocks(dashboard)
            for key in self.summary_blocks:
                self._apply_summary_block_style(key, MACHINE_STATUS_STALE)
            self._render_daily_investment_journey(dashboard.daily_evidence)
            self._render_position_health(dashboard.position_health)
            self.daily_state_label.setText(
                self.daily_state_label.text()
                + "｜Workbench source 讀取失敗，本次內容為 stale；請 Retry。"
            )
            self._style_daily_state(MACHINE_STATUS_STALE)
            self._render_today_action_center(dashboard)
            if not dashboard.review_items:
                self._set_review_empty_state(dashboard)
            self.priority_banner.setText(
                "資料狀態：stale；目前保留最後可信 Workbench DTO。"
                f"最後成功載入：{last_good_at}。Retry 可重新讀取來源；不把舊資料當成 current。"
            )
            stale_tone = _workbench_tone(MACHINE_STATUS_STALE)
            self.priority_banner.setStyleSheet(
                f"background: {stale_tone['bg']}; color: {MIDNIGHT_ANALYST.text_primary}; "
                f"border: 1px solid {stale_tone['border']}; border-left: 6px solid {stale_tone['fg']}; "
                f"border-radius: {MIDNIGHT_ANALYST.radius_panel}px; padding: 10px 12px; "
                "font-size: 12px; font-weight: 700; line-height: 140%;"
            )
            self.boundary_banner.setText(
                "安全邊界：來源暫時不可用；畫面顯示最後可信 DTO 並明示 stale。"
                "不補值、不執行策略、不寫 DB；請聚焦 Retry 重新讀取。"
            )
            self.boundary_banner.setToolTip(
                "目前資料不是 current：最後可信載入時間已列在今日重點。"
                "Retry 只重新讀取 WorkbenchSourceService，不會寫 DB 或補 gate。"
            )
            self.meta_label.setText(
                f"Workbench DTO stale；最後成功載入={last_good_at}；"
                f"本次載入錯誤={error_message}"
            )
            self.evidence_feed_state_label.setText(
                "背景證據流保留最後可信 DTO；狀態為 stale，不宣稱目前來源有效。"
                "請聚焦 Retry；Workbench 不補值、不讀 DB。"
            )
            self.action_item_state_label.setText(
                "待處理清單保留最後可信 DTO；狀態為 stale，不把舊 Action Item 當成 current。"
                "只有 DTO 明示的 human_review 才需人工判讀。"
            )
            self.operating_loop_state_label.setText(
                "操作節奏保留最後可信 DTO；狀態為 stale。Retry 只重新讀取來源，"
                "不標記完成、不寫 DB。"
            )
            self.warning_list.set_warnings(
                (*dashboard.warnings, f"workbench_source_stale:{error_message}")
            )
            self.refresh_button.setEnabled(self.source_service is not None)
            self.refresh_button.setFocus(Qt.OtherFocusReason)
            return

        self._dashboard = None
        self._dashboard_stale = False
        self._render_guided_home(None)
        self._render_daily_investment_journey(None)
        self._render_position_health(None)
        self._render_today_action_center(None)
        self.boundary_banner.setText(
            "安全邊界：工作台狀態未知；尚無可信 DTO 可顯示。"
            "不會補值、執行策略或把資料問題當成交易結論；請聚焦 Retry。"
        )
        self._set_summary_placeholder("狀態未知", "尚無可信 Workbench DTO；請聚焦 Retry，Phase gate 不變")
        self.meta_label.setText(f"工作台載入失敗；狀態未知：{error_message}")
        self.evidence_boundary_card.value_label.setText("資料品質未知")
        self.evidence_coverage_card.value_label.setText("WorkbenchSourceService 未回傳 dashboard DTO。")
        self.evidence_feed_state_label.setText(
            "背景證據流未知：WorkbenchSourceService 未回傳可信 DTO；UI 不補值、不讀 DB、不執行 replay。"
        )
        self.action_item_state_label.setText(
            "待處理清單未知：沒有可信 DTO，不能推定需要人工；請聚焦 Retry，不寫 DB，也不是買賣建議。"
        )
        self.operating_loop_state_label.setText(
            "操作節奏未知：WorkbenchSourceService 未回傳 DTO；不能推定人工狀態，不寫 DB、不標記完成。"
        )
        self.evidence_feed_model.set_rows(())
        self.advice_recommendation_model.set_rows(())
        self.advice_candidate_model.set_rows(())
        self.advice_portfolio_model.set_rows(())
        self._set_advice_state("ADVICE_DTO_ERROR", error_message)
        self.review_model.set_rows(())
        self.review_state_label.setText(
            "今日待判讀佇列載入降級；請先確認 WorkbenchSourceService 問題。UI 不補 gate。"
        )
        self.review_empty_state.setVisible(True)
        self.review_table.setVisible(False)
        self._set_review_empty_state(None)
        self.action_item_model.set_rows(())
        self.operating_loop_model.set_rows(())
        self.warning_list.set_warnings((f"workbench_source_degraded:{error_message}",))
        self._set_detail_placeholder("狀態未知", f"WorkbenchSourceService 未回傳可信 DTO：{error_message}")
        self.refresh_button.setFocus(Qt.OtherFocusReason)

    def _resize_tables(self) -> None:
        for table in (
            self.status_table,
            self.review_table,
            self.evidence_feed_table,
            self.action_item_table,
            self.evidence_table,
            self.advice_recommendation_table,
            self.advice_candidate_table,
            self.advice_portfolio_table,
            self.position_health_table,
        ):
            table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            table.resizeColumnsToContents()
            table.resizeRowsToContents()
        self._fit_summary_table(self.evidence_feed_table, fixed_widths=(190, 92))
        self._fit_summary_table(self.action_item_table, fixed_widths=(104, 92, 130, 180))

    def _fit_summary_table(self, table: QTableView, *, fixed_widths: tuple[int, ...]) -> None:
        header = table.horizontalHeader()
        if table.model() is None or table.model().columnCount() <= len(fixed_widths):
            return
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        for index, width in enumerate(fixed_widths):
            header.setSectionResizeMode(index, QHeaderView.Fixed)
            table.setColumnWidth(index, width)
        header.setSectionResizeMode(len(fixed_widths), QHeaderView.Stretch)

    def _update_evidence_summary_cards(self, dashboard: WorkbenchDashboardDTO) -> None:
        boundary_lines = [
            f"資料品質來源模式：{display_workbench_value(dashboard.source_mode)}",
            "Workbench 維持唯讀：不重算評分、持倉、回測或生命週期",
        ]
        coverage_lines = []
        replay_summary = _find_replay_summary(dashboard.evidence_summary)
        if replay_summary is not None:
            boundary_lines.append("歷史 replay 摘要只作研究證據揭露")
            for item in replay_summary.diagnostics:
                text = _localize_workbench_text(_humanize_replay_diagnostic(item))
                if "覆蓋" in text or "缺口" in text or "缺" in text:
                    coverage_lines.append(text)
                else:
                    boundary_lines.append(text)
            boundary_lines.append(_format_phase0_gate_text(dashboard))
        else:
            boundary_lines.append(_format_phase0_gate_text(dashboard))
            coverage_lines.append("等待 replay 摘要診斷載入。")

        self.evidence_boundary_card.value_label.setText(_format_card_lines(boundary_lines))
        self.evidence_coverage_card.value_label.setText(
            _format_card_lines(coverage_lines) if coverage_lines else "• 目前沒有額外覆蓋率缺口。"
        )

    def _render_evidence_rehearsal_dashboard(
        self, rehearsal: EvidenceRehearsalDashboard | None
    ) -> None:
        if rehearsal is None:
            self.evidence_rehearsal_summary_label.setText(
                "尚未提供 rehearsal DTO；Workbench 不讀取資料庫、不執行 replay。"
            )
            self.evidence_rehearsal_detail_label.setText(
                "工程／Replay／Shadow 的預演狀態未載入；不是 forward evidence。"
            )
            return

        tier = {
            "engineering_fixture": "工程",
            "historical_replay_candidate": "Replay",
            "shadow_comparison": "Shadow",
            "forward_handoff_pending": "Forward handoff pending",
        }.get(rehearsal.tier, rehearsal.tier)
        status = "已阻擋" if rehearsal.status == "blocked" else "僅供預演"
        shadow_text = (
            "有"
            if rehearsal.shadow_comparison_present or rehearsal.tier == "shadow_comparison"
            else "未提供"
        )
        forward_text = "pending" if rehearsal.forward_handoff_pending else "未設定"
        coverage_text = "；".join(
            (
                f"{metric.source_id}：{metric.observed_count}/{metric.total_count} observed，"
                f"missing={metric.missing_count}，degraded={metric.degraded_count}，"
                f"future_blocked={metric.future_blocked_count}，"
                f"immature_label={metric.immature_label_count}"
            )
            for metric in rehearsal.coverage
        ) or "未提供 coverage"
        blockers_text = "；".join(rehearsal.blockers) or "無額外 blocker"
        self.evidence_rehearsal_summary_label.setText(
            f"{rehearsal.disclosure} | tier：{tier} | status：{status} | "
            f"Shadow comparison：{shadow_text} | Forward handoff：{forward_text}"
        )
        self.evidence_rehearsal_detail_label.setText(
            f"coverage：{coverage_text}\nblockers：{blockers_text}\n"
            "唯讀揭露：不寫入資料庫、不啟用排程器、不改變 Advice。"
        )

    def _render_operating_loop(self, steps) -> None:
        while self.operating_loop_list_layout.count():
            item = self.operating_loop_list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for i, step in enumerate(steps):
            chips = []
            linked = getattr(step, "linked_item_ids", ())
            if linked:
                for l in linked:
                    chips.append((_localize_chip_label(str(l)), "info"))
            if str(getattr(step, "step_id", "")) == "multi_day_dry_run":
                chips.append(("每週歷史", "info"))
                chips.append(("來源缺口", "warning"))
            details = _format_detail_body(step)
            card = TimelineCard(
                index=i,
                step_num=i + 1,
                title=_localize_workbench_text(str(getattr(step, "label", getattr(step, "step_id", "")))),
                summary=_localize_workbench_text(str(getattr(step, "summary", ""))),
                status_text=display_workbench_value(str(getattr(step, "status", ""))),
                status_tone=str(getattr(step, "status", "")),
                details_text=details,
                chips=chips
            )
            card.clicked.connect(lambda idx=i: self._show_model_row_detail(self.operating_loop_model, idx))
            card.doubleClicked.connect(lambda idx=i: self._navigate_model_row(self.operating_loop_model, idx))
            self.operating_loop_list_layout.addWidget(card)

    def _render_checklist(self, checklist) -> None:
        while self.checklist_list_layout.count():
            item = self.checklist_list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for i, item in enumerate(checklist):
            status = str(getattr(item, "status", ""))
            status_text = display_workbench_value(status)
            if status == "waiting_for_time":
                status_text = f"機器等待 / {status_text}"
            card = StatusCard(
                index=i,
                title=_localize_workbench_text(str(getattr(item, "label", ""))),
                summary=_localize_workbench_text(str(getattr(item, "summary", ""))),
                status_text=status_text,
                status_tone=status,
            )
            card.clicked.connect(lambda idx=i: self._show_model_row_detail(self.checklist_model, idx))
            self.checklist_list_layout.addWidget(card)

    def _set_summary_blocks(self, dashboard: WorkbenchDashboardDTO) -> None:
        review_count = len(dashboard.review_items)
        action_count = _human_action_count(dashboard)
        machine_action_count = _machine_action_count(dashboard)
        machine_background_count = _machine_background_count(dashboard)
        waiting_count = sum(
            1 for item in dashboard.daily_checklist if str(item.status) == "waiting_for_time"
        )
        warning_count = len(dashboard.warnings)
        self.summary_value_labels["review"].setText(f"{review_count} 筆")
        self.summary_detail_labels["review"].setText("今日需人工判讀；已查看只存在本次 UI session")
        self.summary_value_labels["action"].setText(f"{action_count} 筆")
        self.summary_detail_labels["action"].setText(
            f"只讀人工佇列；Action 機器證據 {machine_action_count} 筆、背景提示 {machine_background_count} 批；"
            "不需人工簽核、不寫 DB、不標記完成"
        )
        self.summary_value_labels["waiting"].setText(f"{waiting_count} 項")
        self.summary_detail_labels["waiting"].setText(_format_phase0_ratio_text(dashboard))
        self.summary_value_labels["warning"].setText(f"{warning_count} 則")
        self.summary_detail_labels["warning"].setText("降級、缺口與 replay 限制需人工檢查")

        self.summary_blocks["waiting"].setToolTip(_phase0_waiting_tooltip(dashboard))
        self._apply_summary_block_style("review", "info" if review_count else "ready")
        self._apply_summary_block_style("action", "warning" if action_count else "ready")
        self._apply_summary_block_style("waiting", "warning" if waiting_count else "ready")
        self._apply_summary_block_style("warning", "critical" if warning_count else "ready")

    def _apply_summary_block_style(self, key: str, status: str) -> None:
        tone = _workbench_tone(status)
        block = self.summary_blocks[key]
        block.setStyleSheet(
            f"#workbenchSummaryBlock {{ background: {tone['bg']}; "
            f"border: 1px solid {tone['border']}; border-left: 5px solid {tone['fg']}; "
            f"border-radius: {MIDNIGHT_ANALYST.radius_panel}px; }}"
        )
        self.summary_value_labels[key].setStyleSheet(
            f"color: {tone['fg']}; font-size: 17px; font-weight: 800;"
        )
        self.summary_detail_labels[key].setStyleSheet(
            f"color: {MIDNIGHT_ANALYST.text_secondary}; font-size: 11px; line-height: 135%;"
        )

    def _set_priority_banner(self, dashboard: WorkbenchDashboardDTO) -> None:
        review_count = len(dashboard.review_items)
        action_count = _human_action_count(dashboard)
        machine_action_count = _machine_action_count(dashboard)
        machine_background_count = _machine_background_count(dashboard)
        warning_count = len(dashboard.warnings)
        waiting_count = sum(
            1 for item in dashboard.daily_checklist if str(item.status) == "waiting_for_time"
        )
        tone_key = "warning" if warning_count or action_count or waiting_count or machine_background_count else "ready"
        tone = _workbench_tone(tone_key)
        self.priority_banner.setText(
            "今日重點："
            f"待判讀 {review_count} | 人工處理 {action_count} | "
            f"機器證據 {machine_action_count} | "
            f"背景提示 {machine_background_count} 批 | "
            f"等待真實時間 {waiting_count} | 警告 {warning_count}。"
            "右側 Inspector 只顯示既有 DTO 證據，不寫入、不補 gate。"
        )
        self.priority_banner.setStyleSheet(
            f"background: {tone['bg']}; color: {MIDNIGHT_ANALYST.text_primary}; "
            f"border: 1px solid {tone['border']}; border-left: 6px solid {tone['fg']}; "
            f"border-radius: {MIDNIGHT_ANALYST.radius_panel}px; padding: 10px 12px; "
            "font-size: 12px; font-weight: 700; line-height: 140%;"
        )

    def _set_summary_placeholder(self, value: str, detail: str) -> None:
        for key in self.summary_value_labels:
            self.summary_value_labels[key].setText(value)
            self.summary_detail_labels[key].setText(detail)
            self._apply_summary_block_style(key, "info")

    def _apply_detail_tone(self, status: str) -> None:
        tone = _workbench_tone(status)
        self.detail_status_badge.setText(display_workbench_value(status).upper())
        self.detail_status_badge.setStyleSheet(
            f"background: {tone['bg']}; color: {tone['fg']}; "
            f"border: 1px solid {tone['border']}; "
            f"border-radius: {MIDNIGHT_ANALYST.radius_badge}px; "
            "padding: 4px 10px; font-weight: 800;"
        )

    def _set_detail_sections(self, item) -> None:
        title = _detail_title(item)
        summary = _localize_workbench_text(str(getattr(item, "summary", "") or "無摘要。"))
        source_trace = _localize_workbench_text(
            str(getattr(item, "source_trace", getattr(item, "source", "")) or "未提供來源追蹤")
        )
        degraded_reason = _localize_workbench_text(str(getattr(item, "degraded_reason", "") or "無"))
        target = _localize_workbench_text(str(getattr(item, "drilldown_target", "") or "未提供"))
        diagnostics = getattr(item, "diagnostics", ())
        diagnostics_text = _format_detail_value(diagnostics) if diagnostics else "無額外診斷訊號。"
        self.detail_summary_box.setText(
            f"重點摘要\n{_localize_workbench_text(title)}\n{summary}"
        )
        self.detail_source_box.setText(
            "來源與邊界\n"
            f"來源追蹤：{source_trace}\n"
            f"降級原因：{degraded_reason}\n"
            f"下鑽目標：{target}\n"
            "唯讀邊界：不寫資料庫、不標記完成、不啟用排程器。"
        )
        self.detail_diagnostics_box.setText(
            f"診斷訊號\n{diagnostics_text}"
        )
        self._style_detail_box(self.detail_summary_box, "info")
        self._style_detail_box(self.detail_source_box, _detail_status(item) or "info")
        self._style_detail_box(self.detail_diagnostics_box, _detail_status(item) or "info")

    def _style_detail_box(self, label: QLabel, status: str) -> None:
        tone = _workbench_tone(status)
        label.setStyleSheet(
            f"background: {tone['bg']}; color: {MIDNIGHT_ANALYST.text_secondary}; "
            f"border: 1px solid {tone['border']}; border-left: 4px solid {tone['fg']}; "
            f"border-radius: {MIDNIGHT_ANALYST.radius_panel}px; padding: 10px; "
            "line-height: 140%; font-size: 11px;"
        )

    def _overview_summary_text(self, dashboard: WorkbenchDashboardDTO) -> str:
        return (
            f"今日待判讀 {len(dashboard.review_items)} 筆｜人工待處理 {_human_action_count(dashboard)} 筆｜"
            f"機器證據待驗證 {_machine_action_count(dashboard)} 筆｜"
            f"背景機器提示 {_machine_background_count(dashboard)} 批｜"
            f"等待真實時間 {sum(1 for item in dashboard.daily_checklist if str(item.status) == 'waiting_for_time')} 項｜"
            f"警告 {len(dashboard.warnings)} 則\n"
            f"{_format_phase0_gate_text(dashboard)}\n"
            "此總覽只彙整 WorkbenchDashboardDTO；不寫 DB、不補 gate、不產生買賣建議。"
        )

    def _review_queue_state_text(self, dashboard: WorkbenchDashboardDTO | None) -> str:
        return review_queue_state_text(dashboard, self._viewed_review_item_ids)


def _detail_title(item) -> str:
    return str(
        getattr(
            item,
            "label",
            getattr(item, "title", getattr(item, "item_id", getattr(item, "step_id", "Workbench item"))),
        )
    )


def _detail_display_title(title: str) -> str:
    if title == "Replay summary diagnostics":
        return "Replay 摘要診斷"
    return _localize_workbench_text(title)


def _workbench_tone(status: str) -> dict[str, str]:
    return WORKBENCH_TONES.get(str(status), WORKBENCH_TONES["neutral"])


def _guided_status_tone(status: str) -> str:
    token = str(status or "unknown").strip().lower()
    if token in {"critical", "missing", "source_missing", "read_failure", "invalid_evidence"}:
        return "critical" if token in {"critical", "read_failure", "invalid_evidence"} else "missing"
    if token in {"warning", "degraded", "stale", "waiting_for_time", "action_required"}:
        return "waiting_for_time" if token == "waiting_for_time" else "warning"
    if token in {"observed", "ready", "done", "passed"}:
        return "info"
    return "info" if token == "info" else "unknown"


def _guided_status_text(status: str) -> str:
    return {
        "critical": "需要立即確認",
        "missing": "資料缺件",
        "source_missing": "來源缺件",
        "read_failure": "讀取失敗",
        "invalid_evidence": "證據無效",
        "warning": "需要注意",
        "degraded": "資料降級",
        "stale": "資料過期",
        "waiting_for_time": "等待真實時間",
        "observed": "已觀測",
        "ready": "可檢視",
        "info": "請查看",
        "unknown": "尚未確認",
    }.get(str(status or "unknown").strip().lower(), "尚未確認")


def _guided_item_text(item: object) -> str:
    return " ".join(
        str(getattr(item, name, "") or "")
        for name in ("source_type", "source", "source_label", "drilldown_target", "code", "title")
    ).lower()


def _guided_is_portfolio_item(item: object) -> bool:
    text = _guided_item_text(item)
    return any(token in text for token in ("portfolio", "position", "持倉", "持有", "退出"))


def _guided_is_candidate_item(item: object) -> bool:
    text = _guided_item_text(item)
    return any(
        token in text
        for token in ("candidate", "watchlist", "continuity", "stock_research", "觀察清單", "候選")
    )


def _guided_is_market_item(item: object) -> bool:
    text = _guided_item_text(item)
    return any(
        token in text
        for token in ("market", "daily_decision", "breadth", "sector", "市場", "產業")
    )


def _guided_is_generic_item(item: object) -> bool:
    return not (
        _guided_is_portfolio_item(item)
        or _guided_is_candidate_item(item)
        or _guided_is_market_item(item)
    )


def _guided_warning_text(value: object) -> str:
    """首頁只顯示白話警示；完整代碼仍留在進階 WarningList。"""

    raw = str(value or "").strip()
    if not raw:
        return "來源警示：請查看詳情。"
    lowered = raw.lower()
    if lowered.startswith("source_missing:"):
        source = raw.split(":", 1)[1].strip().lower()
        source_labels = {
            "market_breadth": "市場漲跌廣度",
            "sector_rotation": "產業輪動",
            "watchlist": "觀察清單",
            "portfolio": "持倉資料",
        }
        return f"{source_labels.get(source, '來源資料')}缺件；請查看詳情。"
    if lowered.startswith("waiting_for_time:") or lowered.startswith("pending_future_data:"):
        return "自然等待：資料需要更多真實時間；請查看詳情。"
    if lowered.startswith("warning:"):
        return "來源有警示；請查看詳情。"
    if any(token in lowered for token in ("missing", "failed", "failure", "blocked", "invalid")):
        return "來源資料需要確認；請查看詳情。"
    if any(char in raw for char in ("_", ":")):
        return "來源有警示；請查看詳情。"
    return _guided_compact(_localize_workbench_text(raw), "來源有警示；請查看詳情。")


def _guided_compact(value: object, fallback: str, limit: int = 104) -> str:
    text = " ".join(str(value or "").split())
    if not text:
        return fallback
    return text if len(text) <= limit else text[: max(1, limit - 1)] + "…"


def _home_public_text(value: object) -> str:
    """首層翻譯技術詞；原文仍在完整來源與提示，限制不刪除。"""
    text = _localize_workbench_text(str(value or ""))
    for token, label in (
        ("DecisionDeskSnapshot", "市場分析來源"),
        ("EvidenceEvent table", "研究證據紀錄"),
        ("Evidence table", "研究證據紀錄"),
        ("scope receipt", "研究範圍收據"),
        ("source_status", "來源狀態"),
        ("current-observed", "目前觀測來源"),
        ("PIT=false", "歷史時點資格未具備"),
    ):
        text = text.replace(token, label)
    return re.sub(r"sha256:[0-9a-fA-F]{64}", "來源指紋（詳見完整來源）", text)


def _home_next_action(value: object) -> str:
    """首頁把工程欄位轉成可直接執行的下一步；詳細 trace 仍保留原 DTO。"""

    text = " ".join(str(value or "").split())
    for source, target in (
        (
            "確認資料日期、scope receipt 與正式 EvidenceEvent table",
            "確認資料日期與推薦來源紀錄",
        ),
        (
            "確認資料日期、scope receipt 與正式 Evidence table",
            "確認資料日期與推薦來源紀錄",
        ),
    ):
        text = text.replace(source, target)
    return text


def _home_market_reason(value: object) -> str:
    """首頁以白話說明市場資料缺口，不把 machine token 當成結論。"""

    text = " ".join(str(value or "").split())
    for source, target in (
        (
            "市場：缺少 DecisionDeskSnapshot；不能判定今日市場狀態。",
            "市場：尚未取得市場分析資料，暫無法判斷市場狀態。",
        ),
        (
            "產業：缺少 DecisionDeskSnapshot；不能判定領先／落後。",
            "產業：尚未取得市場分析資料，暫無法判斷產業輪動。",
        ),
        (
            "缺少 DecisionDeskSnapshot；不能判讀市場或產業。",
            "尚未取得市場分析資料，暫無法判斷市場與產業。",
        ),
    ):
        text = text.replace(source, target)
    # 若來源帶有額外句子，仍只翻譯 machine token，保留其餘理由。
    text = text.replace("缺少 DecisionDeskSnapshot", "尚未取得市場分析資料")
    return text


def _guided_join_reasons(*values: object, fallback: str) -> str:
    reasons: list[str] = []
    for value in values:
        if isinstance(value, (tuple, list)):
            reasons.extend(str(item) for item in value)
        else:
            reasons.append(str(value or ""))
    cleaned: list[str] = []
    seen: set[str] = set()
    for value in reasons:
        text = _guided_compact(_localize_workbench_text(value), "").strip()
        if not text or text in seen:
            continue
        cleaned.append(text)
        seen.add(text)
        if len(cleaned) >= 2:
            break
    return "；".join(cleaned) if cleaned else fallback


def _compact_daily_text(value: str, limit: int = 70) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: max(1, limit - 1)] + "…"


def _daily_quality_text(value: object) -> str:
    raw = str(value or "unknown").strip().lower()
    return {
        "observed": "可讀",
        "ready": "已就緒",
        "complete": "完整",
        "degraded": "降級",
        "missing": "缺漏",
        "stale": "過期",
        "future_blocked": "日期不可用",
        "unknown": "未知",
    }.get(raw, raw)


def _daily_candidate_surface_status(daily: WorkbenchDailyEvidence) -> str:
    status = str(daily.candidate_status or "unknown").strip().lower()
    if status == "candidate":
        return "待研究"
    if status == "candidate_degraded":
        return "資料需複核"
    if status in {"stale", "future_blocked"}:
        return "日期不可用"
    if status in {"missing", "read_failure"}:
        return "來源待檢查"
    return _daily_quality_text(status)


def _daily_evidence_state_parts(daily: WorkbenchDailyEvidence) -> list[str]:
    parts: list[str] = []
    if daily.outcome_ready > 0:
        parts.append(f"已成熟 {daily.outcome_ready}")
    if daily.outcome_pending > 0:
        parts.append(f"尚待成熟 {daily.outcome_pending}")
    if daily.outcome_missing > 0:
        parts.append(f"缺件 {daily.outcome_missing}")
    return parts or ["尚未形成"]


def _daily_evidence_card_text(daily: WorkbenchDailyEvidence) -> str:
    if daily.evidence_event_count == 0:
        return "合格事件 0 件\n尚無可核對結果"
    return (
        f"合格事件 {daily.evidence_event_count} 件\n"
        f"結果 {daily.outcome_total} 筆｜{'、'.join(_daily_evidence_state_parts(daily))}"
    )


def _daily_evidence_surface_line(daily: WorkbenchDailyEvidence) -> str:
    if daily.evidence_event_count == 0:
        return "證據：尚無可核對的合格事件；零事件不等於零風險。"
    return (
        f"證據：合格事件 {daily.evidence_event_count} 件；結果 {daily.outcome_total} 筆；"
        f"{'、'.join(_daily_evidence_state_parts(daily))}。"
    )


def _daily_research_fallback_line(packet: ResearchFallbackPacket | None) -> str:
    if packet is None:
        return ""
    if packet.status == "not_needed":
        return ""
    user_reason = _fallback_user_reason(packet)
    revisit = packet.revisit_date or "尚無法判定"
    if packet.status == "pending_natural_evidence" and packet.revisit_date:
        revisit = f"{packet.revisit_date}（官方交易日估算）"
    if packet.status == "blocked_identity_or_cost":
        next_step = "查看來源詳情定位衝突，再重新整理"
    elif packet.status == "pending_natural_evidence":
        next_step = "等待自然交易日資料，再查看證據成熟度"
    elif packet.status == "pending_capture":
        next_step = "重新整理每日資料，再查看證據成熟度"
    elif packet.status == "read_failure":
        next_step = "重新整理唯讀來源，再查看證據成熟度"
    else:
        next_step = "重新整理每日資料，再查看證據成熟度"
    return "\n".join(
        (
            f"研究 fallback：{user_reason}",
            f"下一步：{next_step}。再看時間：{revisit}。",
            "目前不能下有效機率、權重或買賣結論。",
        )
    )


def _fallback_user_reason(packet: ResearchFallbackPacket) -> str:
    if packet.status == "missing_data":
        return "缺少這次推薦的後續證據。"
    if packet.status == "missing_source":
        return "缺少每日證據來源。"
    if packet.status == "pending_capture":
        return "缺少這次推薦的後續價格紀錄。"
    if packet.status == "pending_natural_evidence":
        return "這次推薦的後續價格觀測尚未成熟。"
    if packet.status == "blocked_identity_or_cost":
        return "推薦、來源或成本版本不一致。"
    if packet.status == "blocked_provenance":
        return "證據來源尚未完成核對。"
    if packet.status == "blocked_scope":
        return "決策日與資料日不一致。"
    if packet.status == "read_failure":
        return "每日證據來源目前讀取失敗。"
    return "目前無法確認缺口。"


def _daily_learning_line(learning, projection=None) -> str:
    if projection is not None:
        if projection.verified_lane is not None:
            lane = projection.verified_lane
            horizon_text = "、".join(
                f"{item.horizon_days}日成熟{item.matured_sample_count}筆／{item.matured_decision_date_count}日"
                for item in projection.horizons
            ) or "horizon未知"
            return (
                f"學習：{lane.label} 已驗證 {lane.matured_sample_count} 筆／"
                f"{lane.matured_decision_date_count} 個決策日；scope={projection.horizon_scope_label or lane.label}；"
                f"{horizon_text}；"
                f"80% reliability 只看已成熟實際比例，最新 {projection.latest_evaluation_label}。"
            )
        if projection.data_recorded_status == "recorded":
            return (
                f"學習：{projection.cost_lane} 的 prediction capture 已記錄，"
                f"尚待自然成熟；80% 機率可靠度未知。"
            )
        if projection.status == "blocked_provenance":
            return "學習：provenance 受阻；不顯示可靠度，也不把歷史 replay 當 natural evidence。"
        return f"學習：{projection.next_gap}"
    if learning is None:
        return "學習：來源缺失，不能判定模型狀態。"
    active_pointer = str(learning.active_pointer_status or "unknown").strip().lower()
    active_sample = learning.active_natural_matured_sample_count
    if active_pointer == "active" and active_sample is not None and active_sample > 0:
        return "學習：已有自然成熟樣本；模型狀態可進一步複核。"
    if active_pointer == "rule_only":
        return "學習：尚待自然成熟樣本；今日候選僅供研究。"
    if active_sample == 0:
        return "學習：目前沒有自然成熟樣本；今日候選僅供研究。"
    return "學習：模型狀態待複核；今日候選僅供研究。"


def _detail_status(item) -> str:
    return str(getattr(item, "status", getattr(item, "severity", "")) or "")


def _human_action_count(dashboard: WorkbenchDashboardDTO) -> int:
    return sum(
        1
        for item in dashboard.action_items
        if str(getattr(item, "status_classification", "human_review"))
        == MACHINE_STATUS_HUMAN_REVIEW
    )


def _machine_action_count(dashboard: WorkbenchDashboardDTO) -> int:
    return len(dashboard.action_items) - _human_action_count(dashboard)


def _machine_background_count(dashboard: WorkbenchDashboardDTO) -> int:
    attention = {
        MACHINE_STATUS_INVALID_EVIDENCE,
        MACHINE_STATUS_MACHINE_CANDIDATE,
        MACHINE_STATUS_MACHINE_DEGRADED,
        MACHINE_STATUS_SOURCE_MISSING,
        MACHINE_STATUS_STALE,
        MACHINE_STATUS_UNKNOWN,
        MACHINE_STATUS_WAITING_FOR_TIME,
    }
    return sum(
        1
        for item in dashboard.background_evidence_feed
        if str(getattr(item, "status_classification", "")).strip() in attention
    )


def _format_card_lines(lines: list[str]) -> str:
    return "\n".join(f"• {_localize_workbench_text(line)}" for line in lines if str(line).strip())


def _localize_chip_label(text: str) -> str:
    token_map = {
        "readiness_weekly_history": "每週歷史",
        "readiness_multi_day_dry_run": "多日 dry-run",
        "readiness_source_gaps": "來源缺口",
        "replay_summary_manual_review": "replay 覆盤",
        "weekly_history": "每週歷史",
        "multi_day_dry_run": "多日 dry-run",
        "manual_review_note": "人工註記",
        "scheduler_off": "排程關閉",
        "readiness_weekly_history": "每週歷史",
        "readiness_multi_day_dry_run": "多日 dry-run",
        "readiness_source_gaps": "來源缺口",
        "replay_summary_manual_review": "replay 覆盤",
        "manual_review_note": "人工註記",
        "watchlist_trigger": "觀察清單觸發",
        "portfolio_review": "持倉覆盤",
        "evidence_review": "證據覆盤",
    }
    return token_map.get(text, display_workbench_value(text))


def _localize_workbench_text(text: str) -> str:
    replacements = {
        "manual_required": "需要人工覆盤",
        "waiting_for_time": "等待真實時間累積",
        "action_required": "需要處理",
        "blocked": "封鎖",
        "manual_observed": "人工已觀測",
        "passed": "通過",
        "missing": "缺漏",
        "source_missing": "來源缺件",
        "invalid_evidence": "證據無效",
        "machine_candidate": "機器候選",
        "machine_verified": "機器已驗證",
        "machine_degraded": "機器觀測降級",
        "stale": "資料過期（stale）",
        "unknown": "未知",
        "degraded": "降級",
        "records observed": "筆已觀測",
        "record observed": "筆已觀測",
        "Weekly review history": "每週覆盤歷史",
        "Multi-day dry-run": "多日 dry-run",
        "Multi-day dry-run record": "多日 dry-run 紀錄",
        "Scheduler write-mode": "排程器寫入模式",
        "Production scheduler remains off": "正式排程器維持關閉",
        "must accumulate in real time": "必須靠真實時間累積",
        "replay cannot replace this gate": "replay 不可取代這個 gate",
        "review item": "待判讀項目",
        "Scheduler gate": "排程 Gate",
        "Replay summary gap": "Replay 摘要缺口",
        "Replay summary diagnostics": "Replay 摘要診斷",
        "Replay summary": "Replay 摘要",
        "diagnostics": "診斷訊號",
        "Decision snapshot freshness": "決策快照新鮮度",
        "Evidence gate status": "證據門檻狀態",
        "Manual review note": "人工覆盤註記",
        "source trace": "來源追蹤",
        "degraded reason": "降級原因",
        "read-only": "唯讀",
        "Read-only": "唯讀",
        "scheduler": "排程器",
        "production scheduler": "正式排程器",
        "simulated scheduler": "模擬排程器",
        "scoring": "評分",
        "portfolio": "持倉",
        "backtest": "回測",
        "lifecycle": "生命週期",
        "Historical replay JSON summary": "歷史 replay 摘要",
        "research evidence only": "僅供研究證據使用",
        "does not replace real weekly or multi-day scheduler gates": "不可取代真實每週或多日排程 gate",
        "Recommendations source uses only persisted results": "推薦來源只使用已保存結果",
        "Forward outcomes are capped by replay_data_as_of_date": "forward outcome 受 replay_data_as_of_date 限制",
        "Production scheduler remains separate and is not enabled by this replay": "正式排程器與 replay 分離，且不會被 replay 啟用",
        "Phase 0 weekly history": "Phase 0 每週歷史",
        "weekly history": "每週歷史",
        "multi-day dry-run": "多日 dry-run",
        "source gaps": "來源缺口",
        "source gap": "來源缺口",
        "readiness_weekly_history": "每週歷史",
        "readiness_multi_day_dry_run": "多日 dry-run",
        "readiness_source_gaps": "來源缺口",
        "replay_summary_manual_review": "replay 覆盤",
        "manual_review_note": "人工註記",
        "watchlist_trigger": "觀察清單觸發",
        "portfolio_review": "持倉覆盤",
        "evidence_review": "證據覆盤",
        "after_manual_review": "人工覆盤後",
        "daily_until_3": "每日直到 3 筆",
        "weekly_until_3": "每週直到 3 筆",
        "pending_future_data": "等待未來資料",
        "source_missing_screening_matrix": "缺 screening matrix 來源",
        "recommendation": "推薦",
        "evidence": "證據",
    }
    localized = str(text)
    for source, target in sorted(replacements.items(), key=lambda item: len(item[0]), reverse=True):
        localized = localized.replace(source, target)
    return localized


def _format_detail_body(item) -> str:
    lines = [
        "唯讀邊界：此處只展示 WorkbenchDashboardDTO 既有欄位；不寫資料庫、不標記完成、不啟用排程器。",
        "",
    ]
    for label, field_name in (
        ("項目代號", "item_id"),
        ("步驟代號", "step_id"),
        ("摘要", "summary"),
        ("代碼", "code"),
        ("來源", "source"),
        ("來源類型", "source_type"),
        ("來源名稱", "source_label"),
        ("機器處理分類", "status_classification"),
        ("來源追蹤", "source_trace"),
        ("推薦結果 ID", "result_id"),
        ("股票代號", "stock_code"),
        ("Candidate key", "candidate_key"),
        ("身份狀態", "identity_status"),
        ("研究意向", "decision_status"),
        ("提醒狀態", "reminder_status"),
        ("到期狀態", "due_status"),
        ("下次檢視時間", "next_review_at"),
        ("Journal 原始檢視時間", "recorded_next_review_at"),
        ("Revision ID", "revision_id"),
        ("提醒 Revision ID", "reminder_revision_id"),
        ("Revision of", "revision_of"),
        ("Continuity event ID", "continuity_event_id"),
        ("來源 snapshot ID", "source_snapshot_id"),
        ("來源 snapshot hash", "source_snapshot_hash"),
        ("決策日期", "decision_date"),
        ("歷史筆數", "history_count"),
        ("研究筆記", "note"),
        ("降級原因", "degraded_reason"),
        ("節奏", "cadence"),
        ("關聯項目", "linked_item_ids"),
        ("人工提示", "guidance"),
        ("下鑽目標", "drilldown_target"),
        ("寫入意圖", "write_intent"),
        ("診斷訊號", "diagnostics"),
    ):
        if not hasattr(item, field_name):
            continue
        value = getattr(item, field_name)
        if value is None or value == "" or value == ():
            continue
        lines.append(f"- {label}: {_format_detail_value(value)}")
    lines.extend(
        (
            "",
            "欄位可用性",
            "- snapshot hash：未知（目前 DTO 未提供；UI 不自行重建）",
            "- schema 版本：未知（目前 DTO 未提供）",
            "- Gate 細項：未知（請以下鑽頁面的既有 evidence／readiness 結果為準）",
        )
    )
    return "\n".join(lines)


def _format_detail_value(value: object) -> str:
    if isinstance(value, tuple):
        return "；".join(_format_detail_token(item) for item in value) or "無"
    if isinstance(value, list):
        return "；".join(_format_detail_token(item) for item in value) or "無"
    if isinstance(value, bool):
        return "是" if value else "否"
    return _format_detail_token(value)


def _format_detail_token(value: object) -> str:
    raw = str(value)
    display = display_workbench_value(raw)
    if raw == display:
        return _localize_workbench_text(raw)
    return _localize_workbench_text(display.replace(f"（{raw}）", ""))


def _find_replay_summary(items: tuple[WorkbenchEvidenceSummary, ...]) -> WorkbenchEvidenceSummary | None:
    for item in items:
        if item.item_id == "historical_replay":
            return item
    return None












def _humanize_replay_diagnostic(token: str) -> str:
    text = str(token)
    if text == "simulated_scheduler":
        return "模擬排程器：replay 來自模擬排程器，不是正式排程器。"
    if text.startswith("source_gap:"):
        return f"來源缺口：{display_workbench_value(text.split(':', 1)[1])}"
    if text.startswith("source_gap_coverage:"):
        return display_workbench_value(text)
    if text.startswith("payload_gap:"):
        return f"payload 缺口：{display_workbench_value(text.split(':', 1)[1])}"
    if text.startswith("outcome_maturity:"):
        return display_workbench_value(text)
    if text.startswith("benchmark_coverage:"):
        return display_workbench_value(text)
    if text.startswith("industry_benchmark_coverage:"):
        return display_workbench_value(text)
    if text.startswith("missing_industry_benchmark:"):
        return display_workbench_value(text)
    if text.startswith("pending_future_data:"):
        return display_workbench_value(text)
    if text.startswith("phase0_gate_not_satisfied:"):
        return display_workbench_value(text)
    if text.startswith("replay_direction_assessment:"):
        return display_workbench_value(text)
    return display_workbench_value(text)


def _format_phase0_gate_text(dashboard: WorkbenchDashboardDTO) -> str:
    weekly = _ratio_for_item(dashboard, "weekly_history") or "尚未就緒"
    dry_run = _ratio_for_item(dashboard, "multi_day_dry_run") or "尚未就緒"
    evidence_gate = next(
        (item for item in dashboard.status_strip if item.item_id == "evidence_gate"),
        None,
    )
    credit_text = (
        "formal evidence credit 已授權"
        if evidence_gate is not None and "formal_credit_authorized=true" in (evidence_gate.summary or "")
        else "formal evidence credit 尚未授權"
    )
    return (
        f"Phase 0 每週歷史 {weekly} 與多日 dry-run {dry_run} 仍是真實時間 gate；"
        f"replay 不可取代；{credit_text}。"
    )


def _format_phase0_ratio_text(dashboard: WorkbenchDashboardDTO) -> str:
    weekly = _ratio_for_item(dashboard, "weekly_history") or "尚未就緒"
    dry_run = _ratio_for_item(dashboard, "multi_day_dry_run") or "尚未就緒"
    return f"weekly history {weekly}｜multi-day dry-run {dry_run}"


def _phase0_waiting_tooltip(dashboard: WorkbenchDashboardDTO) -> str:
    waiting_count = sum(
        1 for item in dashboard.daily_checklist if str(item.status) == "waiting_for_time"
    )
    ratio_text = _format_phase0_ratio_text(dashboard)
    if waiting_count:
        return (
            "【等待真實時間】\n"
            f"目前有 {waiting_count} 項仍在等待真實市場時間與資料累積。\n"
            f"{ratio_text}\n"
            "不可用 fixture、手動改表或 replay 補齊；請依實際交易日讓排程／人工覆盤自然累積。"
        )
    return (
        "【時間 gate 已有觀測】\n"
        f"{ratio_text}\n"
        "這只表示目前的 readiness／具名核准觀測已達門檻；仍須查看 evidence gate 摘要，"
        "formal credit 與 production scheduler 不會因 3/3 自動開啟。"
    )


def _ratio_for_item(dashboard: WorkbenchDashboardDTO, item_id: str) -> str | None:
    for item in dashboard.daily_checklist:
        if item.item_id != item_id:
            continue
        match = re.search(r"\b\d+/\d+\b", f"{item.label} {item.summary}")
        return match.group(0) if match else None
    for item in dashboard.evidence_summary:
        if item.item_id != item_id:
            continue
        match = re.search(r"\b\d+/\d+\b", f"{item.label} {item.summary}")
        return match.group(0) if match else None
    return None


def _optional_date_text(value: date | None) -> str:
    return value.isoformat() if type(value) is date else "未知"


def _latest_capture_status_text(dashboard: WorkbenchDashboardDTO) -> str:
    capture = dashboard.latest_capture_status
    labels = {
        "unknown": "未知",
        "saved": "已有快照",
        "failed": "擷取失敗",
        "timeout": "擷取逾時",
    }
    parts = [labels.get(capture.status, "未知")]
    if capture.decision_date is not None:
        parts.append(f"決策日 {capture.decision_date.isoformat()}")
    if capture.run_id:
        parts.append(f"run {capture.run_id}")
    if capture.failure_reason:
        reason = capture.failure_reason
        detail = {
            "snapshot_cli_timeout": "快照產生逾時",
            "snapshot_capture_failed": "快照未保存",
        }.get(reason, reason)
        parts.append(f"原因 {detail}（{reason}）")
    if capture.status == "timeout" and capture.snapshot_saved is None:
        parts.append("保存結果未知")
    return "；".join(parts)


def _latest_capture_overview_text(dashboard: WorkbenchDashboardDTO) -> str:
    capture = dashboard.latest_capture_status
    labels = {
        "unknown": "未知",
        "saved": "已保存",
        "failed": "失敗",
        "timeout": "逾時",
    }
    text = f"最近保存：{labels.get(capture.status, '未知')}"
    if capture.decision_date is not None:
        text += f"（{capture.decision_date.isoformat()}）"
    if capture.status == "timeout" and capture.snapshot_saved is None:
        text += "；保存結果未知"
    return text


def _yes_no(value: bool) -> str:
    return "是" if value else "否"


def _humanize_warning(token: object) -> str:
    text = str(token)
    if text.startswith("workbench_source_degraded:"):
        return "工作台來源降級：" + text.split(":", 1)[1]
    if text.startswith("degraded_source:"):
        return "降級來源：" + display_workbench_value(text.split(":", 1)[1])
    if "historical_replay" in text or text in {
        "simulated_scheduler",
        "not_production_readiness",
        "missing_industry_benchmark",
        "pending_insufficient_future_data",
    }:
        return _localize_workbench_text(display_workbench_value(text))
    return _localize_workbench_text(display_workbench_value(text))
