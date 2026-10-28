"""每日決策工作台 View."""

from datetime import date, datetime, timezone
from typing import Any, Callable

from PySide6.QtCore import QEvent, QObject, QPoint, QTimer, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QFrame,
    QGridLayout,
    QComboBox,
)

from app_module.decision_desk_dtos import (
    DecisionDeskQuality,
    DecisionDeskRiskPromptSummary,
    DecisionDeskSnapshot,
    RelativeStrengthLiquiditySummary,
)
from app_module.decision_desk_service import DecisionDeskSnapshotBuilder
from app_module.watchlist_trigger_presentation import format_watchlist_trigger_review
from app_module.decision_presentation import (
    DecisionPresentationService,
    format_decision_presentation,
)
from app_module.market_data_visibility_dtos import MarketDataVisibilitySummary
from app_module.research_session import ResearchStockContextDTO
from data_module.market_session_policy import resolve_project_market_session_boundary
from ui_qt.theme import MIDNIGHT_ANALYST
from ui_qt.status_vocabulary import status_detail, status_label
from ui_qt.research_date_presentation import source_data_date_text
from ui_qt.workers.task_worker import TaskWorker
from ui_qt.widgets.theme_widgets import (
    CollapsibleSectionPanel,
    CompactCodeList,
    MetricCard,
    SectionPanel,
    StatusBadge,
    WarningList,
)
from ui_qt.widgets.layout_helpers import set_scroll_content_constraints
from ui_qt.widgets.info_button import InfoButton


def _current_taipei_decision_date(clock: Callable[[], datetime] | None = None) -> date:
    """Return the project decision date in Taipei, independent of host timezone."""
    observed_at = clock() if clock is not None else datetime.now(timezone.utc)
    return resolve_project_market_session_boundary(observed_at).taipei_date


def _market_regime_source_data_date(section: Any) -> str:
    """Return only a canonical source date no later than the section cutoff."""
    meta = getattr(section, "meta", None)
    raw_value = meta.get("source_data_date") if isinstance(meta, dict) else None
    if not isinstance(raw_value, str):
        return "未知"
    section_as_of_date = getattr(section, "as_of_date", None)
    if type(section_as_of_date) is not date:
        return "未知"
    return source_data_date_text(raw_value, cutoff=section_as_of_date)


class DecisionDeskView(QWidget):
    """每日決策工作台：只透過 DecisionDeskSnapshotBuilder 取得快照。"""

    stockResearchRequested = Signal(object)
    savedRecommendationRequested = Signal(str)

    def __init__(
        self,
        decision_desk_builder: DecisionDeskSnapshotBuilder | None = None,
        as_of_date: date | None = None,
        auto_refresh: bool = True,
        async_refresh: bool = True,
        navigate_to_smart_money_callback: Callable[[str], None] | None = None,
        parent=None,
        presentation_service: DecisionPresentationService | None = None,
        clock: Callable[[], datetime] | None = None,
    ):
        super().__init__(parent)
        self.decision_desk_builder = decision_desk_builder or DecisionDeskSnapshotBuilder()
        self._clock = clock
        self._historical_date_pinned = as_of_date is not None
        self.as_of_date = (
            as_of_date
            if as_of_date is not None
            else (
                _current_taipei_decision_date()
                if self._clock is None
                else _current_taipei_decision_date(self._clock)
            )
        )
        self.async_refresh = async_refresh
        self.navigate_to_smart_money_callback = navigate_to_smart_money_callback
        self.presentation_service = presentation_service or DecisionPresentationService()
        self._auto_refresh_pending = auto_refresh
        self._last_snapshot: DecisionDeskSnapshot | None = None
        self._refresh_worker: TaskWorker | None = None
        self._refresh_generation = 0
        self._worker_generation = 0
        self._refresh_pending = False
        self._closing = False

        self._setup_ui()
        self._display_pending_snapshot()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        QTimer.singleShot(0, self._reflow_industry_strength_cards)
        if self._auto_refresh_pending:
            self._auto_refresh_pending = False
            self.refresh_snapshot()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802 - Qt override
        if (
            (
                watched is self._industry_strength_card_viewport
                or watched is self._main_scroll_viewport
            )
            and event.type() == QEvent.Type.Resize
            and not getattr(self, "_industry_strength_reflow_pending", False)
        ):
            self._industry_strength_reflow_pending = True
            QTimer.singleShot(0, self._reflow_industry_strength_cards)
        return super().eventFilter(watched, event)

    def _reflow_industry_strength_cards(self) -> None:
        self._industry_strength_reflow_pending = False
        if self._closing:
            return
        available_width = self._main_scroll_viewport.width()
        if available_width > 0:
            self.industry_strength_panel.setMaximumWidth(available_width)
        width = min(
            self.industry_strength_chart_scroll.viewport().width(),
            max(0, available_width - 28),
        )
        columns = self._industry_strength_columns_for_width(width)
        if columns == self._industry_strength_grid_columns:
            self._sync_industry_strength_chart_height()
            return
        cards = tuple(self._industry_strength_row_widgets.values())
        while self.industry_strength_card_grid.count():
            self.industry_strength_card_grid.takeAt(0)
        for column in range(3):
            self.industry_strength_card_grid.setColumnStretch(
                column, 1 if column < columns else 0
            )
        for index, card in enumerate(cards):
            self.industry_strength_card_grid.addWidget(
                card, index // columns, index % columns
            )
        self._industry_strength_grid_columns = columns
        self.industry_strength_card_grid.activate()
        self.industry_strength_chart_content.adjustSize()
        self._sync_industry_strength_chart_height()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(12, 12, 12, 12)

        scroll_area = QScrollArea()
        scroll_area.setObjectName("decisionDeskMainScrollArea")
        self.main_scroll_area = scroll_area
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setFrameShape(QScrollArea.NoFrame)
        scroll_content = QWidget()
        content_layout = QVBoxLayout(scroll_content)
        content_layout.setSpacing(10)
        content_layout.setContentsMargins(0, 0, 0, 0)

        title_layout = QHBoxLayout()
        title = QLabel("每日決策")
        title_font = QFont()
        title_font.setPointSize(17)
        title_font.setBold(True)
        title.setFont(title_font)
        title_layout.addWidget(title)
        title_layout.addWidget(InfoButton("market_overview", self))
        title_layout.addStretch()

        self.refresh_btn = QPushButton("更新決策摘要")
        self.refresh_btn.setProperty("variant", "primary")
        self.refresh_btn.clicked.connect(self.refresh_snapshot)
        title_layout.addWidget(self.refresh_btn)
        content_layout.addLayout(title_layout)

        self.overall_status_label = QLabel("")
        self.generated_at_label = QLabel("")
        self.overall_status_label.setWordWrap(True)
        status_font = QFont()
        status_font.setPointSize(13)
        status_font.setBold(True)
        self.overall_status_label.setFont(status_font)
        generated_font = QFont()
        generated_font.setPointSize(10)
        self.generated_at_label.setFont(generated_font)
        self.generated_at_label.setStyleSheet(f"color: {MIDNIGHT_ANALYST.text_muted};")
        self.overall_quality_badge = StatusBadge("", "observed")
        # Keep the quality badge and metric cards as compatibility attrs, while the
        # default view exposes one compact, neutral status row.
        self.overall_quality_badge.setVisible(False)
        self.warning_list = WarningList()
        self.overall_warn_label = self.warning_list
        self.warning_summary_label = QLabel(
            "資料品質：尚未載入；提示數：未知；首條：尚未載入"
        )
        self.warning_summary_label.setObjectName("decisionDeskWarningSummary")
        self.warning_summary_label.setWordWrap(True)
        self.warning_summary_label.setStyleSheet(
            f"color: {MIDNIGHT_ANALYST.text_secondary};"
        )
        self.warning_details_panel = CollapsibleSectionPanel(
            "完整警示",
            collapsed=True,
        )
        self.warning_details_panel.toggle_button.setAccessibleName("展開完整警示")
        self.warning_details_panel.content_layout.addWidget(self.warning_list)
        self.decision_date_card = MetricCard("決策日", self.as_of_date.isoformat())
        self.generated_at_card = MetricCard("生成時間", "N/A")
        self.decision_date_card.setVisible(False)
        self.generated_at_card.setVisible(False)

        info_group = SectionPanel("總覽")
        info_layout = info_group.layout
        status_layout = QHBoxLayout()
        status_layout.addWidget(self.overall_status_label, 1)
        status_layout.addWidget(self.overall_quality_badge, 0)
        info_layout.addLayout(status_layout)
        metric_layout = QHBoxLayout()
        metric_layout.addWidget(self.decision_date_card)
        metric_layout.addWidget(self.generated_at_card)
        info_layout.addLayout(metric_layout)
        info_layout.addWidget(self.generated_at_label)
        self.saved_recommendation_label = QLabel("保存推薦：尚未載入")
        self.saved_recommendation_label.setObjectName("decisionDeskSavedRecommendationSummary")
        self.saved_recommendation_label.setTextFormat(Qt.TextFormat.PlainText)
        self.saved_recommendation_label.setWordWrap(True)
        self.saved_recommendation_label.setStyleSheet(
            f"color: {MIDNIGHT_ANALYST.text_secondary};"
        )
        self.saved_recommendation_button = QPushButton("開啟原保存推薦")
        self.saved_recommendation_button.setProperty("variant", "secondary")
        self.saved_recommendation_button.setAccessibleName("開啟每日決策中的原保存推薦")
        self.saved_recommendation_button.setToolTip(
            "只讀取此處列出的原保存結果；不產生今日新推薦或交易指令。"
        )
        self.saved_recommendation_button.setEnabled(False)
        self.saved_recommendation_button.clicked.connect(
            self._open_saved_recommendation
        )
        saved_recommendation_row = QHBoxLayout()
        saved_recommendation_row.setSpacing(8)
        saved_recommendation_row.addWidget(self.saved_recommendation_label, 1)
        saved_recommendation_row.addWidget(
            self.saved_recommendation_button, 0, Qt.AlignmentFlag.AlignTop
        )
        info_layout.addLayout(saved_recommendation_row)
        self.saved_recommendation_open_status = QLabel("")
        self.saved_recommendation_open_status.setObjectName(
            "decisionDeskSavedRecommendationOpenStatus"
        )
        self.saved_recommendation_open_status.setTextFormat(Qt.TextFormat.PlainText)
        self.saved_recommendation_open_status.setWordWrap(True)
        self.saved_recommendation_open_status.setAccessibleName("原保存推薦開啟狀態")
        self.saved_recommendation_open_status.setStyleSheet(
            f"color: {MIDNIGHT_ANALYST.text_secondary};"
        )
        self.saved_recommendation_open_status.setVisible(False)
        info_layout.addWidget(self.saved_recommendation_open_status)
        info_layout.addWidget(self.warning_summary_label)
        info_layout.addWidget(self.warning_details_panel)

        self.action_headline_label = QLabel("今日主結論：尚未載入")
        self.action_headline_label.setWordWrap(True)
        action_font = QFont()
        action_font.setPointSize(14)
        action_font.setBold(True)
        self.action_headline_label.setFont(action_font)
        self.action_note_label = QLabel("研究模式：以下為市場與籌碼輔助判讀，不是交易建議。")
        self.action_note_label.setWordWrap(True)
        self.action_note_label.setStyleSheet(f"color: {MIDNIGHT_ANALYST.text_secondary};")
        conclusion_group = SectionPanel("今日主結論")
        conclusion_group.layout.addWidget(self.action_headline_label)
        conclusion_group.layout.addWidget(self.action_note_label)
        content_layout.addWidget(info_group)
        # 先顯示資料日期、品質與警示摘要，再呈現今日主結論。
        content_layout.addWidget(conclusion_group)

        self.priority_sector_label = QLabel("優先產業：尚未載入")
        self.risk_sector_label = QLabel("避開產業 / 風險區：尚未載入")
        self.priority_stock_label = QLabel("優先研究股票：尚未載入")
        self.risk_stock_label = QLabel("風險股票：尚未載入")
        self.market_data_impact_label = QLabel("資料影響：尚未確認")
        self.industry_focus_buttons: list[QPushButton] = []
        self.stock_focus_buttons: list[QPushButton] = []
        focus_group = SectionPanel("市場焦點")
        for label in (
            self.priority_sector_label,
            self.risk_sector_label,
            self.priority_stock_label,
            self.risk_stock_label,
        ):
            label.setWordWrap(True)
            label.setStyleSheet(f"color: {MIDNIGHT_ANALYST.text_primary}; font-size: 10pt;")
            focus_group.layout.addWidget(label)
        self.market_data_impact_label.setWordWrap(True)
        self.market_data_impact_label.setStyleSheet(
            f"color: {MIDNIGHT_ANALYST.text_secondary}; font-size: 10pt;"
        )
        focus_group.layout.addWidget(self.market_data_impact_label)

        self.focus_details_collapsible = CollapsibleSectionPanel(
            "查看理由與其他研究入口",
            collapsed=True,
        )
        self.focus_details_collapsible.toggle_button.setAccessibleName(
            "展開市場焦點理由與其他研究入口"
        )
        self.industry_focus_button_container = QWidget()
        self.industry_focus_button_layout = QHBoxLayout(self.industry_focus_button_container)
        self.industry_focus_button_layout.setContentsMargins(0, 4, 0, 0)
        self.industry_focus_button_layout.setSpacing(6)
        self.focus_details_collapsible.content_layout.addWidget(
            self.industry_focus_button_container
        )
        self.stock_focus_button_container = QWidget()
        self.stock_focus_button_layout = QHBoxLayout(self.stock_focus_button_container)
        self.stock_focus_button_layout.setContentsMargins(0, 4, 0, 0)
        self.stock_focus_button_layout.setSpacing(6)
        self.focus_details_collapsible.content_layout.addWidget(
            self.stock_focus_button_container
        )
        focus_group.layout.addWidget(self.focus_details_collapsible)
        self.stock_focus_research_button = QPushButton("開啟焦點研究報告")
        self.stock_focus_research_button.setProperty("variant", "secondary")
        self.stock_focus_research_button.setAccessibleName("開啟市場焦點個股研究報告")
        self.stock_focus_research_button.setToolTip(
            "以市場焦點的既有日期與來源開啟個股研究；沒有焦點時停用。"
        )
        self.stock_focus_research_button.setEnabled(False)
        self.stock_focus_research_button.clicked.connect(self._open_stock_focus_research)
        focus_group.layout.addWidget(self.stock_focus_research_button)
        content_layout.addWidget(focus_group)

        self.advanced_market_panel = CollapsibleSectionPanel(
            "完整市場資料",
            collapsed=True,
        )
        self.advanced_market_panel.setObjectName("v5AdvancedDecisionDesk")
        self.advanced_market_panel.toggle_button.setAccessibleName("展開完整市場資料")
        self.advanced_market_panel.toggle_button.setToolTip(
            "查看各模組完整數值、來源可見性與呈現契約；不會重新取得或重算資料。"
        )
        self.market_details_button = QPushButton("查看完整市場資料")
        self.market_details_button.setProperty("variant", "secondary")
        self.market_details_button.setAccessibleName("查看完整市場資料")
        self.market_details_button.clicked.connect(
            lambda: self.advanced_market_panel.set_collapsed(False)
        )
        focus_group.layout.addWidget(self.market_details_button)
        advanced_layout = self.advanced_market_panel.content_layout

        self.presentation_contract_label = QLabel("尚未載入共用呈現契約。")
        self.presentation_contract_label.setWordWrap(True)
        self.presentation_contract_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.presentation_contract_label.setStyleSheet(
            f"color: {MIDNIGHT_ANALYST.text_primary}; font-size: 10pt;"
        )
        presentation_group = SectionPanel("共用呈現契約")
        presentation_intro = QLabel(
            "市場焦點只沿用既有快照；沒有合格來源的分數、機率、樣本或權重維持未知。"
        )
        presentation_intro.setWordWrap(True)
        presentation_intro.setStyleSheet(f"color: {MIDNIGHT_ANALYST.text_secondary};")
        presentation_group.layout.addWidget(presentation_intro)
        presentation_group.layout.addWidget(self.presentation_contract_label)
        advanced_layout.addWidget(presentation_group)

        self.visibility_section = SectionPanel("資料可見性與擴充因子")
        visibility_header = QHBoxLayout()
        visibility_intro = QLabel("呈現決策日當下可取得的資料範圍與研究因子，不參與今日行動、焦點或 Score。")
        visibility_intro.setWordWrap(True)
        visibility_intro.setStyleSheet(f"color: {MIDNIGHT_ANALYST.text_secondary};")
        self.visibility_quality_badge = StatusBadge("尚未載入", "missing")
        visibility_header.addWidget(visibility_intro, 1)
        visibility_header.addWidget(self.visibility_quality_badge, 0)
        self.visibility_section.layout.addLayout(visibility_header)
        visibility_cards = QHBoxLayout()
        self.revenue_visibility_card = MetricCard("月營收廣度", "尚未載入")
        self.institutional_visibility_card = MetricCard("三大法人市場流向", "尚未載入")
        self.institutional_flow_bar = QWidget(self.institutional_visibility_card)
        self.institutional_flow_bar.setObjectName("decisionDeskInstitutionalFlowBar")
        self.institutional_flow_bar.setAccessibleName("三大法人買賣超相對分布")
        self.institutional_flow_bar.setToolTip("三類法人淨買賣超股數；共用零軸，長度僅表示三者內相對大小。")
        self.institutional_flow_bar_layout = QGridLayout(self.institutional_flow_bar)
        self.institutional_flow_bar_layout.setContentsMargins(0, 3, 0, 0)
        self.institutional_flow_bar_layout.setHorizontalSpacing(4)
        self.institutional_flow_bar_layout.setVerticalSpacing(3)
        self.institutional_flow_rows: dict[str, tuple[QLabel, QFrame, QLabel]] = {}
        self.institutional_flow_zero_axis = QFrame(self.institutional_flow_bar)
        self.institutional_flow_zero_axis.setObjectName("decisionDeskInstitutionalFlowZeroAxis")
        self.institutional_flow_zero_axis.setAccessibleName("共用零軸")
        self.institutional_flow_zero_axis.setFixedWidth(1)
        self.institutional_flow_zero_axis.setStyleSheet(f"background-color: {MIDNIGHT_ANALYST.text_muted};")
        self.institutional_flow_bar_layout.addWidget(self.institutional_flow_zero_axis, 0, 2, 3, 1)
        self.institutional_flow_bar.hide()
        self.institutional_visibility_card.layout().addWidget(self.institutional_flow_bar)
        visibility_cards.addWidget(self.revenue_visibility_card)
        visibility_cards.addWidget(self.institutional_visibility_card)
        self.visibility_section.layout.addLayout(visibility_cards)
        self.visibility_sources_label = QLabel("來源狀態：尚未載入")
        self.visibility_sources_label.setWordWrap(True)
        self.visibility_sources_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.visibility_sources_label.setStyleSheet(f"color: {MIDNIGHT_ANALYST.text_secondary};")
        self.visibility_action_hint = QLabel(
            "下一步：依來源核對缺漏、可得時間、授權與覆蓋；未核清前僅作研究觀察，不用於歷史回測或 ML。"
        )
        self.visibility_action_hint.setWordWrap(True)
        self.visibility_action_hint.setStyleSheet(f"color: {MIDNIGHT_ANALYST.warning};")
        self.visibility_section.layout.addWidget(self.visibility_sources_label)
        self.visibility_section.layout.addWidget(self.visibility_action_hint)
        advanced_layout.addWidget(self.visibility_section)

        self.market_regime_status = QLabel("")
        self.market_regime_value = QLabel("")
        self.market_breadth_status = QLabel("")
        self.market_breadth_value = QLabel("")
        self.sector_rotation_status = QLabel("")
        self.sector_rotation_value = QLabel("")
        self.relative_strength_liquidity_status = QLabel("")
        self.relative_strength_liquidity_value = QLabel("")
        self.watchlist_triggers_status = QLabel("")
        self.watchlist_triggers_value = QLabel("")
        self.portfolio_alerts_status = QLabel("")
        self.portfolio_alerts_value = QLabel("")
        self.risk_prompts_status = QLabel("")
        self.risk_prompts_value = QLabel("")
        self.risk_prompts_value.setObjectName("decisionDeskRiskPromptDetails")
        self.risk_prompts_value.setAccessibleName("每日決策風險提示詳情")
        self.risk_prompts_value.setTextFormat(Qt.PlainText)
        self.relative_strength_codes = CompactCodeList()
        self._section_badges: dict[str, StatusBadge] = {}
        self._status_badges: dict[QLabel, StatusBadge] = {}

        sections_group = SectionPanel("各模組狀態")
        sections_layout = sections_group.layout
        sections_layout.addWidget(self._make_section_row("市場情緒", self.market_regime_status, self.market_regime_value))
        breadth_row = self._make_section_row("市況廣度", self.market_breadth_status, self.market_breadth_value)
        self.market_breadth_row = breadth_row
        self.market_breadth_row.setAccessibleName("市況廣度摘要與家數分布")
        self.market_breadth_bar = QWidget()
        self.market_breadth_bar.setObjectName("decisionDeskMarketBreadthBar")
        self.market_breadth_bar_layout = QHBoxLayout(self.market_breadth_bar)
        self.market_breadth_bar_layout.setContentsMargins(0, 3, 0, 0)
        self.market_breadth_bar_layout.setSpacing(2)
        self.market_breadth_bar.setAccessibleName("市況廣度家數分布")
        self.market_breadth_bar.hide()
        self.market_breadth_legend = QLabel("")
        self.market_breadth_legend.setObjectName("decisionDeskMarketBreadthLegend")
        self.market_breadth_legend.setWordWrap(True)
        self.market_breadth_caption = QLabel("")
        self.market_breadth_caption.setObjectName("decisionDeskMarketBreadthCaption")
        self.market_breadth_caption.setWordWrap(True)
        self.market_breadth_caption.setStyleSheet(f"color: {MIDNIGHT_ANALYST.text_secondary}; font-size: 9pt;")
        breadth_layout = breadth_row.layout()
        assert isinstance(breadth_layout, QVBoxLayout)
        breadth_layout.addWidget(self.market_breadth_bar)
        breadth_layout.addWidget(self.market_breadth_legend)
        breadth_layout.addWidget(self.market_breadth_caption)
        self.market_breadth_legend.hide()
        self.market_breadth_caption.hide()
        content_layout.insertWidget(content_layout.indexOf(focus_group), breadth_row)
        sections_layout.addWidget(self._make_section_row("產業輪動", self.sector_rotation_status, self.sector_rotation_value))
        self.industry_strength_panel = SectionPanel("可比產業超額表現")
        self.industry_strength_panel.setObjectName("decisionDeskIndustryStrengthPanel")
        self.industry_strength_meta = QLabel("尚未載入可比產業資料")
        self.industry_strength_meta.setObjectName("decisionDeskIndustryStrengthMeta")
        self.industry_strength_meta.setWordWrap(True)
        self.industry_strength_meta.setStyleSheet(
            f"color: {MIDNIGHT_ANALYST.text_secondary}; font-size: 9pt;"
        )
        self.industry_strength_panel.layout.addWidget(self.industry_strength_meta)
        self.industry_strength_group_selector = QComboBox()
        self.industry_strength_group_selector.setObjectName("decisionDeskIndustryStrengthGroup")
        self.industry_strength_group_selector.setAccessibleName("可比產業層級與市場範圍")
        self.industry_strength_group_selector.currentIndexChanged.connect(
            self._on_industry_strength_group_changed
        )
        self.industry_strength_panel.layout.addWidget(self.industry_strength_group_selector)
        self.industry_strength_navigation = QWidget()
        self.industry_strength_navigation.setObjectName("decisionDeskIndustryStrengthNavigation")
        navigation_layout = QHBoxLayout(self.industry_strength_navigation)
        navigation_layout.setContentsMargins(0, 2, 0, 2)
        navigation_layout.setSpacing(6)
        self.industry_strength_leading_button = QPushButton("定位來源領先")
        self.industry_strength_leading_button.setObjectName("decisionDeskIndustryStrengthLeading")
        self.industry_strength_leading_button.clicked.connect(
            lambda: self._locate_industry_strength_headline("leading")
        )
        navigation_layout.addWidget(self.industry_strength_leading_button)
        self.industry_strength_trailing_button = QPushButton("定位來源落後")
        self.industry_strength_trailing_button.setObjectName("decisionDeskIndustryStrengthTrailing")
        self.industry_strength_trailing_button.clicked.connect(
            lambda: self._locate_industry_strength_headline("trailing")
        )
        navigation_layout.addWidget(self.industry_strength_trailing_button)
        self.industry_strength_navigation_status = QLabel("定位僅使用同一快照提供的 20 日領先／落後名稱。")
        self.industry_strength_navigation_status.setObjectName("decisionDeskIndustryStrengthNavigationStatus")
        self.industry_strength_navigation_status.setWordWrap(True)
        navigation_layout.addWidget(self.industry_strength_navigation_status, 1)
        self.industry_strength_panel.layout.addWidget(self.industry_strength_navigation)
        self.industry_strength_empty_state = QLabel("")
        self.industry_strength_empty_state.setObjectName("decisionDeskIndustryStrengthEmptyState")
        self.industry_strength_empty_state.setWordWrap(True)
        self.industry_strength_empty_state.setStyleSheet(
            f"color: {MIDNIGHT_ANALYST.text_secondary}; font-size: 9pt;"
        )
        self.industry_strength_panel.layout.addWidget(self.industry_strength_empty_state)
        self.industry_strength_chart_scroll = QScrollArea()
        self.industry_strength_chart_scroll.setObjectName("decisionDeskIndustryStrengthChartScroll")
        self.industry_strength_chart_scroll.setWidgetResizable(True)
        self.industry_strength_chart_scroll.setFrameShape(QScrollArea.NoFrame)
        self.industry_strength_chart_scroll.setMinimumHeight(230)
        self.industry_strength_chart_scroll.setMaximumHeight(235)
        self.industry_strength_chart_content = QWidget()
        self.industry_strength_chart_layout = QVBoxLayout(self.industry_strength_chart_content)
        self.industry_strength_chart_layout.setContentsMargins(0, 0, 0, 0)
        self.industry_strength_chart_layout.setSpacing(6)
        self.industry_strength_chart_header = QLabel("")
        self.industry_strength_chart_header.setObjectName("decisionDeskIndustryStrengthChartHeader")
        self.industry_strength_chart_header.setWordWrap(True)
        self.industry_strength_chart_header.setStyleSheet(
            f"color: {MIDNIGHT_ANALYST.text_secondary}; font-size: 9pt;"
        )
        self.industry_strength_chart_layout.addWidget(self.industry_strength_chart_header)
        self.industry_strength_card_grid_widget = QWidget()
        self.industry_strength_card_grid = QGridLayout(self.industry_strength_card_grid_widget)
        self.industry_strength_card_grid.setContentsMargins(2, 2, 2, 2)
        self.industry_strength_card_grid.setHorizontalSpacing(8)
        self.industry_strength_card_grid.setVerticalSpacing(8)
        self.industry_strength_card_grid.setHorizontalSizeConstraint(
            QGridLayout.SizeConstraint.SetNoConstraint
        )
        self.industry_strength_card_grid_widget.setMinimumWidth(0)
        self.industry_strength_card_grid_widget.setSizePolicy(
            QSizePolicy.Ignored, QSizePolicy.Preferred
        )
        self.industry_strength_chart_layout.addWidget(self.industry_strength_card_grid_widget)
        self.industry_strength_chart_content.setMinimumWidth(0)
        self.industry_strength_chart_content.setSizePolicy(
            QSizePolicy.Ignored, QSizePolicy.Preferred
        )
        self.industry_strength_chart_scroll.setWidget(self.industry_strength_chart_content)
        self._industry_strength_card_viewport = self.industry_strength_chart_scroll.viewport()
        self._industry_strength_card_viewport.installEventFilter(self)
        self.industry_strength_panel.layout.addWidget(self.industry_strength_chart_scroll)
        self.industry_strength_representatives = QWidget()
        self.industry_strength_representatives_layout = QHBoxLayout(
            self.industry_strength_representatives
        )
        self.industry_strength_representatives_layout.setContentsMargins(0, 4, 0, 0)
        self.industry_strength_representatives_layout.setSpacing(6)
        self.industry_strength_panel.layout.addWidget(self.industry_strength_representatives)
        self._industry_strength_rows: tuple[Any, ...] = ()
        self._industry_strength_as_of_date = self.as_of_date
        self._industry_strength_summary = None
        self._industry_strength_selected_name = ""
        self._industry_strength_expanded_name = ""
        self._industry_strength_row_buttons: list[QPushButton] = []
        self._industry_strength_row_widgets: dict[tuple[str, str, str], QWidget] = {}
        self._industry_strength_card_details: dict[str, QWidget] = {}
        self._industry_strength_card_frames: dict[str, QFrame] = {}
        self._industry_strength_grid_columns = 0
        self._industry_strength_reflow_pending = False
        self._industry_strength_headline_targets: dict[str, tuple[tuple[str, str], Any]] = {}
        self._industry_strength_navigation_request_id = 0
        self.industry_strength_empty_state.hide()
        self._clear_industry_strength_chart("尚未載入可比產業資料")
        content_layout.addWidget(self.industry_strength_panel)
        sections_layout.addWidget(self._make_section_row("強弱與流動性", self.relative_strength_liquidity_status, self.relative_strength_liquidity_value))
        sections_layout.addWidget(self.relative_strength_codes)
        sections_layout.addWidget(self._make_section_row("Watchlist 提示", self.watchlist_triggers_status, self.watchlist_triggers_value))
        sections_layout.addWidget(self._make_section_row("持倉警示", self.portfolio_alerts_status, self.portfolio_alerts_value))
        sections_layout.addWidget(self._make_section_row("風險提示", self.risk_prompts_status, self.risk_prompts_value))
        advanced_layout.addWidget(sections_group)
        advanced_layout.addStretch()
        content_layout.addWidget(self.advanced_market_panel)
        content_layout.addStretch()

        set_scroll_content_constraints(scroll_content)
        scroll_area.setWidget(scroll_content)
        self._main_scroll_viewport = scroll_area.viewport()
        self._main_scroll_viewport.installEventFilter(self)
        layout.addWidget(scroll_area)

    def _make_section_row(self, title: str, status_label: QLabel, value_label: QLabel) -> QWidget:
        row = QWidget()
        row.setObjectName("decisionDeskSectionRow")
        row_layout = QVBoxLayout(row)
        row_layout.setContentsMargins(8, 6, 8, 6)
        row_layout.setSpacing(3)
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(8)
        title_label = QLabel(title)
        title_font = QFont()
        title_font.setPointSize(11)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setStyleSheet(f"color: {MIDNIGHT_ANALYST.text_primary};")
        quality_badge = StatusBadge("", "observed")
        if title == "風險提示":
            row.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
            quality_badge.setMaximumHeight(32)
        self._section_badges[title] = quality_badge
        self._status_badges[status_label] = quality_badge
        status_label.setWordWrap(True)
        value_label.setWordWrap(True)
        status_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        value_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        if title == "風險提示":
            status_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
            value_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        status_label.setMinimumWidth(0)
        value_label.setMinimumWidth(0)
        status_label.setStyleSheet(f"color: {MIDNIGHT_ANALYST.text_secondary}; font-size: 10pt;")
        value_label.setStyleSheet(f"color: {MIDNIGHT_ANALYST.text_primary}; font-size: 10pt; line-height: 130%;")
        status_label.hide()
        row.setStyleSheet(
            f"#decisionDeskSectionRow {{ background: {MIDNIGHT_ANALYST.surface_1}; "
            f"border-bottom: 1px solid {MIDNIGHT_ANALYST.border}; }}"
        )

        header_layout.addWidget(title_label, 1)
        header_layout.addWidget(quality_badge, 0)
        row_layout.addLayout(header_layout)
        row_layout.addWidget(status_label)
        row_layout.addWidget(value_label)
        return row

    def _clear_market_breadth_bar(self) -> None:
        while self.market_breadth_bar_layout.count():
            item = self.market_breadth_bar_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self.market_breadth_bar.hide()
        self.market_breadth_legend.clear()
        self.market_breadth_legend.hide()
        self.market_breadth_caption.clear()
        self.market_breadth_caption.hide()

    def _render_market_breadth_bar(self, breadth: Any, snapshot_date: date) -> None:
        self._clear_market_breadth_bar()
        counts = (breadth.advancing, breadth.declining, breadth.unchanged)
        if any(type(count) is not int or count < 0 for count in counts):
            return
        if sum(counts) <= 0:
            return
        quality = getattr(breadth.quality, "value", breadth.quality)
        if str(quality).upper() not in {"OBSERVED", "ESTIMATED", "DEGRADED"}:
            return
        source_date = breadth.as_of_date
        if (
            type(source_date) is not date
            or type(snapshot_date) is not date
            or source_date > snapshot_date
        ):
            return

        labels = ("上漲", "下跌", "平盤")
        colors = (
            MIDNIGHT_ANALYST.market_up,
            MIDNIGHT_ANALYST.market_down,
            MIDNIGHT_ANALYST.market_flat,
        )
        for index, (label, count, color) in enumerate(zip(labels, counts, colors)):
            segment = QFrame(self.market_breadth_bar)
            segment.setObjectName(f"decisionDeskBreadthSegment{index}")
            segment.setProperty("breadthCount", count)
            segment.setProperty("breadthStretch", count)
            segment.setAccessibleName(f"{label} {count} 家")
            segment.setToolTip(f"{label}：{count} 家")
            segment.setStyleSheet(f"background-color: {color}; border-radius: 3px;")
            segment.setMinimumHeight(12)
            if count == 0:
                segment.setFixedWidth(0)
            self.market_breadth_bar_layout.addWidget(segment, count)

        self.market_breadth_bar.setAccessibleDescription(
            f"上漲 {counts[0]} 家、下跌 {counts[1]} 家、平盤 {counts[2]} 家"
        )
        self.market_breadth_legend.setText(
            f"上漲：{counts[0]} 家｜下跌：{counts[1]} 家｜平盤：{counts[2]} 家"
        )
        self.market_breadth_legend.show()
        coverage_details: list[str] = []
        meta = getattr(breadth, "meta", None)
        if isinstance(meta, dict):
            classified = meta.get("classified_stock_count")
            stock_count = meta.get("stock_count")
            if (
                type(classified) is int
                and classified >= 0
                and type(stock_count) is int
                and stock_count >= 0
            ):
                coverage_details.append(f"方向分類 {classified}/{stock_count}")
            detail_labels = (
                ("twse_zero_direction_evidence_count", "TWSE 空白符核驗平盤"),
                ("official_non_comparable_exclusions_count", "官方不比價排除"),
                ("corporate_action_exclusions_count", "除權息排除"),
                ("unknown_skipped_rows_count", "方向未知略過"),
            )
            for key, label in detail_labels:
                value = meta.get(key)
                if type(value) is int and value > 0:
                    coverage_details.append(f"{label} {value}")
        coverage_suffix = "｜" + "｜".join(coverage_details) if coverage_details else ""
        self.market_breadth_caption.setText(
            f"已載入家數分布；非指數報酬／交易訊號｜來源日：{source_date.isoformat()}｜品質：{self._display_quality_value(quality)}{coverage_suffix}"
        )
        self.market_breadth_caption.show()
        self.market_breadth_bar.show()

    def refresh_snapshot(self):
        if self._closing:
            return
        self._clear_market_breadth_bar()
        self._clear_institutional_flow_bar()
        if not self._historical_date_pinned:
            current_date = (
                _current_taipei_decision_date()
                if self._clock is None
                else _current_taipei_decision_date(self._clock)
            )
            if current_date != self.as_of_date:
                self.as_of_date = current_date
                self._last_snapshot = None
                self._display_pending_snapshot()
        self._refresh_generation += 1
        if self.async_refresh:
            self._start_refresh_worker()
        else:
            self._refresh_snapshot()

    def _display_pending_snapshot(self) -> None:
        self._render_saved_recommendation(None)
        self._clear_market_breadth_bar()
        self.overall_status_label.setText("摘要尚未載入")
        self.generated_at_label.setText(
            f"本次評估日（台北）：{self.as_of_date.isoformat()}｜"
            f"快照判讀日：{self.as_of_date.isoformat()}｜產生時間：N/A"
        )
        self.overall_quality_badge.setText("尚未載入")
        self.overall_quality_badge.set_quality("missing")
        self.decision_date_card.value_label.setText(self.as_of_date.isoformat())
        self.generated_at_card.value_label.setText("N/A")
        self.warning_list.set_warnings(())
        self.warning_summary_label.setText(
            "資料品質：尚未載入；提示數：未知；首條：尚未載入"
        )
        self.warning_details_panel.set_collapsed(True)
        self.relative_strength_codes.set_groups(())
        self.action_headline_label.setText("今日主結論：尚未載入")
        self.action_note_label.setText("研究模式：以下為市場與籌碼輔助判讀，不是交易建議。")
        self.priority_sector_label.setText("優先產業：尚未載入")
        self.risk_sector_label.setText("避開產業 / 風險區：尚未載入")
        self.priority_stock_label.setText("優先研究股票：尚未載入")
        self.risk_stock_label.setText("風險股票：尚未載入")
        self.market_data_impact_label.setText("資料影響：尚未確認；缺資料不等於安全。")
        self._set_industry_focus_buttons(None, self.as_of_date)
        self.presentation_contract_label.setText("尚未載入共用呈現契約。")
        self._set_stock_focus_buttons(())
        self._render_market_data_visibility(None)
        for status_label, badge in self._status_badges.items():
            status_label.setText("尚未載入")
            badge.setText("尚未載入")
            badge.set_quality("missing")
        for value_label in (
            self.market_regime_value,
            self.market_breadth_value,
            self.sector_rotation_value,
            self.relative_strength_liquidity_value,
            self.watchlist_triggers_value,
            self.portfolio_alerts_value,
            self.risk_prompts_value,
        ):
            value_label.setText("待背景載入")
        self.risk_prompts_value.setAccessibleDescription("風險提示尚未載入。")
        self.overall_status_label.setStyleSheet(
            f"background: {MIDNIGHT_ANALYST.surface_2}; color: {MIDNIGHT_ANALYST.text_secondary}; "
            f"border: 1px solid {MIDNIGHT_ANALYST.border}; "
            "border-radius: 6px; padding: 4px 8px; font-size: 12pt; font-weight: 700;"
        )

    def _display_loading_snapshot(self) -> None:
        self._render_saved_recommendation(None)
        self._clear_market_breadth_bar()
        self.market_breadth_row.hide()
        self._clear_institutional_flow_bar()
        self._clear_industry_strength_chart("載入中；可比產業圖卡已清除舊快照")
        self.risk_prompts_value.setText("載入中；舊風險提示已清除。")
        loading_detail = "正在讀取新快照；舊風險提示已清除。"
        self.risk_prompts_value.setAccessibleDescription(loading_detail)
        self.risk_prompts_status.setText("載入中")
        self.risk_prompts_status.setToolTip(loading_detail)
        self.risk_prompts_status.setAccessibleDescription(loading_detail)
        risk_prompts_badge = self._status_badges.get(self.risk_prompts_status)
        if risk_prompts_badge is not None:
            risk_prompts_badge.setText("載入中")
            risk_prompts_badge.set_quality("missing")
            risk_prompts_badge.setToolTip(loading_detail)
            risk_prompts_badge.setAccessibleDescription(loading_detail)
        self.overall_status_label.setText("摘要載入中")
        self.generated_at_label.setText(
            f"判讀日：{self.as_of_date.isoformat()}｜產生時間：背景載入中"
        )
        self.generated_at_card.value_label.setText("載入中")
        self.refresh_btn.setEnabled(False)

    def _start_refresh_worker(self) -> None:
        if self._closing:
            return
        if self._refresh_worker is not None and self._refresh_worker.isRunning():
            self._refresh_pending = True
            return
        self._refresh_pending = False
        self._display_loading_snapshot()
        request_date = self.as_of_date
        generation = self._refresh_generation
        self._worker_generation = generation
        worker = TaskWorker(self.decision_desk_builder.build_snapshot, request_date)
        self._refresh_worker = worker
        worker.finished.connect(lambda snapshot: self._on_refresh_worker_finished(snapshot, generation, request_date))
        worker.error.connect(lambda error: self._on_refresh_worker_error(error, generation, request_date))
        worker.cancelled.connect(lambda: self._on_refresh_worker_cancelled(generation))
        worker.native_thread_finished.connect(self._on_refresh_worker_native_thread_finished)
        worker.start()

    def _release_refresh_worker(self) -> None:
        self.refresh_btn.setEnabled(True)
        worker = self._refresh_worker
        self._refresh_worker = None
        if worker is not None:
            worker.deleteLater()
        if self._refresh_pending and not self._closing:
            self._start_refresh_worker()

    def begin_shutdown(self) -> None:
        """撤銷 pending refresh，避免取消舊 worker 後自動補起新一輪。"""

        self._closing = True
        self._refresh_generation += 1
        self._refresh_pending = False
        worker = self._refresh_worker
        if worker is not None:
            try:
                is_running = bool(worker.isRunning())
            except RuntimeError:
                is_running = False
            if is_running:
                worker.cancel(cooperative=True, wait=False)

    def _on_refresh_worker_finished(self, snapshot: DecisionDeskSnapshot, generation: int | None = None, request_date: date | None = None) -> None:
        if generation is not None and generation != self._worker_generation:
            return
        if (generation is None or generation == self._refresh_generation) and (request_date is None or request_date == self.as_of_date):
            self._last_snapshot = snapshot
            self._render_snapshot(snapshot)
        self._release_refresh_worker()

    def _on_refresh_worker_error(self, error_message: str, generation: int | None = None, request_date: date | None = None) -> None:
        if generation is not None and generation != self._worker_generation:
            return
        if (generation is None or generation == self._refresh_generation) and (request_date is None or request_date == self.as_of_date):
            self._display_exception_snapshot(error_message)
        self._release_refresh_worker()

    def _on_refresh_worker_cancelled(self, generation: int | None = None) -> None:
        if generation is not None and generation != self._worker_generation:
            return
        self._release_refresh_worker()

    def _on_refresh_worker_native_thread_finished(self) -> None:
        if self._closing:
            QTimer.singleShot(0, self.close)

    def closeEvent(self, event) -> None:
        self.begin_shutdown()
        if self._refresh_worker is not None and self._refresh_worker.isRunning():
            event.ignore()
            return
        super().closeEvent(event)

    def _set_section_quality(
        self,
        status_label: QLabel,
        quality: DecisionDeskQuality,
        as_of_date: date | None = None,
    ) -> None:
        label = self._quality_label(quality)
        detail = status_detail(quality, dimension="data")
        if as_of_date is not None:
            detail += f"；判讀日：{as_of_date.isoformat()}"
        status_label.setText(label)
        status_label.setToolTip(detail)
        status_label.setAccessibleDescription(detail)
        badge = self._status_badges.get(status_label)
        if badge is not None:
            badge.setText(label)
            badge.set_quality(self._quality_token(quality))
            badge.setToolTip(detail)
            badge.setAccessibleDescription(detail)

    def _refresh_snapshot(self) -> None:
        request_date = self.as_of_date
        try:
            snapshot = self.decision_desk_builder.build_snapshot(request_date)
        except Exception as exc:
            self._display_exception_snapshot(str(exc))
            return

        if self.as_of_date == request_date:
            self._last_snapshot = snapshot
            self._render_snapshot(snapshot)

    def _render_snapshot(self, snapshot: DecisionDeskSnapshot) -> None:
        self._render_saved_recommendation(snapshot.recommendations)
        self._render_answer_first_dashboard(snapshot)
        self._set_industry_focus_buttons(snapshot.sector_rotation, snapshot.as_of_date)
        self.market_breadth_row.show()
        self._render_industry_strength_chart(snapshot.sector_rotation, snapshot.as_of_date)
        self._render_market_data_visibility(snapshot.market_data_visibility)
        self.overall_status_label.setText("摘要已載入")
        self.generated_at_label.setText(
            f"本次評估日（台北）：{self.as_of_date.isoformat()}｜"
            f"快照判讀日：{snapshot.as_of_date.isoformat()}｜"
            f"來源市場資料日：{_market_regime_source_data_date(snapshot.market_regime)}｜"
            f"產生時間：{snapshot.generated_at.isoformat()}"
        )
        self.overall_quality_badge.setText(self._quality_label(snapshot.overall_quality))
        self.overall_quality_badge.set_quality(self._quality_token(snapshot.overall_quality))
        overall_quality_detail = status_detail(snapshot.overall_quality, dimension="data")
        self.overall_quality_badge.setToolTip(
            f"{overall_quality_detail}；判讀日：{snapshot.as_of_date.isoformat()}"
        )
        self.decision_date_card.value_label.setText(snapshot.as_of_date.isoformat())
        self.generated_at_card.value_label.setText(snapshot.generated_at.strftime("%H:%M:%S"))

        warning_lines = [self._humanize_warning_token(item) for item in snapshot.warnings]
        visibility_summary = snapshot.market_data_visibility
        visibility_quality = (
            "MISSING"
            if visibility_summary is None
            else str(getattr(visibility_summary, "overall_quality", "UNKNOWN")).upper()
        )
        if visibility_quality != "OBSERVED":
            visibility_warning = (
                "資料可見性：缺漏"
                if visibility_quality == "MISSING"
                else f"資料可見性：{self._visibility_quality_label(visibility_quality)}"
            )
            if visibility_warning not in warning_lines:
                warning_lines.append(visibility_warning)
        self._set_section_quality(
            self.market_regime_status,
            snapshot.market_regime.quality,
            getattr(snapshot.market_regime, "as_of_date", snapshot.as_of_date),
        )
        regime_value_label = (
            "匹配分數（bp）"
            if (getattr(snapshot.market_regime, "meta", None) or {}).get("regime_value_kind")
            == "match_score_bp"
            else "訊號強度"
        )
        self.market_regime_value.setText(
            f"市場狀態：{snapshot.market_regime.regime_label or '未定義'}；"
            f"得分：{snapshot.market_regime.regime_score if snapshot.market_regime.regime_score is not None else '未知'}；"
            f"{regime_value_label}：{snapshot.market_regime.regime_confidence if snapshot.market_regime.regime_confidence is not None else '未知'}；"
            f"行情日：{_market_regime_source_data_date(snapshot.market_regime)}；"
            f"判斷日：{snapshot.as_of_date.isoformat()}"
        )

        self._set_section_quality(
            self.market_breadth_status,
            snapshot.market_breadth.quality,
            getattr(snapshot.market_breadth, "as_of_date", snapshot.as_of_date),
        )
        breadth = snapshot.market_breadth
        advancing = breadth.advancing if breadth.advancing is not None else "未提供"
        declining = breadth.declining if breadth.declining is not None else "未提供"
        unchanged = breadth.unchanged if breadth.unchanged is not None else "未提供"
        breadth_ratio = (
            breadth.breadth_ratio_bp
            if breadth.breadth_ratio_bp is not None
            else "未知"
        )
        self.market_breadth_value.setText(
            f"多方：{advancing}；空方：{declining}；"
            f"持平：{unchanged}；廣度比率BP：{breadth_ratio}"
        )
        self._render_market_breadth_bar(breadth, snapshot.as_of_date)

        self._set_section_quality(
            self.sector_rotation_status,
            snapshot.sector_rotation.quality,
            getattr(snapshot.sector_rotation, "as_of_date", snapshot.as_of_date),
        )
        self.sector_rotation_value.setText(self._format_sector_rotation(snapshot.sector_rotation))

        self._set_section_quality(
            self.relative_strength_liquidity_status,
            snapshot.relative_strength_liquidity.quality,
            getattr(
                snapshot.relative_strength_liquidity,
                "as_of_date",
                snapshot.as_of_date,
            ),
        )
        self.relative_strength_liquidity_value.setText("")
        self.relative_strength_liquidity_value.hide()
        self.relative_strength_codes.set_groups(
            [
                ("強勢", snapshot.relative_strength_liquidity.top_strength_codes),
                ("弱勢", snapshot.relative_strength_liquidity.weak_strength_codes),
                ("低流動性", snapshot.relative_strength_liquidity.low_liquidity_codes),
            ]
        )

        self._set_section_quality(
            self.watchlist_triggers_status,
            snapshot.watchlist_triggers.quality,
            getattr(snapshot.watchlist_triggers, "as_of_date", snapshot.as_of_date),
        )
        self.watchlist_triggers_value.setText(
            format_watchlist_trigger_review(snapshot.watchlist_triggers)
        )

        self._set_section_quality(
            self.portfolio_alerts_status,
            snapshot.portfolio_alerts.quality,
            getattr(snapshot.portfolio_alerts, "as_of_date", snapshot.as_of_date),
        )
        portfolio_attribution_text = self._format_portfolio_attributions(getattr(snapshot.portfolio_alerts, "attributions", ()))
        self.portfolio_alerts_value.setText(
            f"警示數：{snapshot.portfolio_alerts.alert_count if snapshot.portfolio_alerts.alert_count is not None else '未知'}；"
            f"持倉代碼：{', '.join(snapshot.portfolio_alerts.alert_codes) if snapshot.portfolio_alerts.alert_codes else '無'}；"
            f"等級：{snapshot.portfolio_alerts.alert_level or '未知'}；"
            f"來源歸因：{portfolio_attribution_text}"
        )

        self._set_section_quality(
            self.risk_prompts_status,
            snapshot.risk_prompts.quality,
            getattr(snapshot.risk_prompts, "as_of_date", snapshot.as_of_date),
        )
        self.risk_prompts_value.setText(self._format_risk_prompts(snapshot.risk_prompts))
        self.risk_prompts_value.setAccessibleDescription(
            self._risk_prompts_accessible_description(snapshot.risk_prompts)
        )

        for section_text in self._collect_warnings(snapshot):
            humanized = self._humanize_warning_token(section_text)
            if humanized not in warning_lines:
                warning_lines.append(humanized)

        if warning_lines:
            warning_lines = [str(item) for item in warning_lines]
        else:
            warning_lines = []
        self.warning_list.set_warnings(warning_lines)
        quality_label = self._quality_label(snapshot.overall_quality)
        if warning_lines:
            first_warning = warning_lines[0].strip() or "未提供"
            if len(first_warning) > 72:
                first_warning = first_warning[:71].rstrip() + "…"
            warning_summary = (
                f"資料品質：{quality_label}；提示數：{len(warning_lines)}；"
                f"首條：{first_warning}"
            )
        else:
            if snapshot.overall_quality == DecisionDeskQuality.OBSERVED:
                warning_summary = (
                    f"資料品質：{quality_label}；提示數：0；目前無警示"
                )
            else:
                warning_summary = (
                    f"資料品質：{quality_label}；提示數：0（未收到額外警示）；"
                    f"狀態仍為「{quality_label}」"
                )
        self.warning_summary_label.setText(warning_summary)

        self.overall_status_label.setStyleSheet(
            f"background: {MIDNIGHT_ANALYST.surface_2}; color: {MIDNIGHT_ANALYST.text_secondary}; "
            f"border: 1px solid {MIDNIGHT_ANALYST.border}; "
            "border-radius: 6px; padding: 4px 8px; font-size: 12pt; font-weight: 700;"
        )

    def _render_saved_recommendation(self, recommendation: Any | None) -> None:
        """只呈現快照提供的原保存結果身分，不推定缺席代表沒有結果。"""

        self.clear_saved_recommendation_open_error()
        if recommendation is None:
            self.saved_recommendation_label.setText(
                "保存推薦：本次摘要未提供（狀態未知）；不是今日新推薦。"
            )
            self.saved_recommendation_button.setEnabled(False)
            self.saved_recommendation_button.setProperty("result_id", None)
            self.saved_recommendation_button.setVisible(False)
            return

        result_id = getattr(recommendation, "result_id", None)
        valid_result_id = (
            type(result_id) is str
            and bool(result_id.strip())
            and result_id == result_id.strip()
        )
        as_of_date = getattr(recommendation, "as_of_date", None)
        date_text = as_of_date.isoformat() if type(as_of_date) is date else "未知"
        quality = self._quality_label(getattr(recommendation, "quality", None))
        raw_codes = getattr(recommendation, "stock_codes", ())
        codes = tuple(str(code) for code in raw_codes if isinstance(code, str) and code)
        candidate_text = ", ".join(codes) if codes else "未提供"
        displayed_id = result_id if valid_result_id else "未知"
        self.saved_recommendation_label.setText(
            f"原保存推薦（非今日新推薦／非交易指令）：資料日 {date_text}；"
            f"品質 {quality}；來源 ID {displayed_id}；候選 {candidate_text}。"
        )
        self.saved_recommendation_button.setProperty(
            "result_id", result_id if valid_result_id else None
        )
        self.saved_recommendation_button.setEnabled(valid_result_id)
        self.saved_recommendation_button.setVisible(valid_result_id)

    def _open_saved_recommendation(self) -> None:
        self.clear_saved_recommendation_open_error()
        result_id = self.saved_recommendation_button.property("result_id")
        if (
            type(result_id) is str
            and bool(result_id.strip())
            and result_id == result_id.strip()
        ):
            self.savedRecommendationRequested.emit(result_id)

    def clear_saved_recommendation_open_error(self) -> None:
        self.saved_recommendation_open_status.clear()
        self.saved_recommendation_open_status.setVisible(False)

    def show_saved_recommendation_open_error(self, message: str) -> None:
        """在原摘要旁顯示 Main 導覽準備失敗的可讀原因。"""

        text = str(message).splitlines()[0][:300].strip()
        if not text:
            text = "原保存推薦尚未能讀取；未改選其他結果。"
        self.saved_recommendation_open_status.setText(text)
        self.saved_recommendation_open_status.setVisible(True)

    @staticmethod
    def _visibility_quality_label(value: str) -> str:
        raw = str(value or "unknown").strip()
        shared_label = status_label(raw, dimension="data")
        return {"estimated": "估算"}.get(raw.lower(), shared_label)

    @staticmethod
    def _visibility_pit_label(value: str) -> str:
        raw = str(value or "unknown").strip()
        return {
            "verified": "可得時間已核驗",
            "observation_date_only": "只有觀測日，沒有可得日",
            "historical_pit_unverified": "歷史可得時間未驗證",
            "missing": "可得時間缺件",
        }.get(raw.lower(), f"可得時間狀態未登錄（{raw}）")

    @staticmethod
    def _visibility_eligibility_label(value: str) -> str:
        raw = str(value or "unknown").strip()
        return {
            "research_only": "僅供研究",
            "none": "尚無可用資格",
        }.get(raw.lower(), f"資格狀態未登錄（{raw}）")

    @staticmethod
    def _format_ratio_bp(value: int | None) -> str:
        if value is None:
            return "N/A"
        sign = "-" if value < 0 else ""
        absolute = abs(value)
        return f"{sign}{absolute // 100}.{absolute % 100:02d}%"

    @staticmethod
    def _format_sector_rotation(rotation) -> str:
        strength = getattr(rotation, "industry_strength", None)
        if strength is None:
            return (
                f"領先產業：{rotation.leading_sector or '未定義'}；"
                f"落後產業：{rotation.trailing_sector or '未定義'}；"
                f"輪動強度BP：{rotation.rotation_intensity_bp if rotation.rotation_intensity_bp is not None else 'N/A'}"
            )
        rows = tuple(getattr(strength, "rows", ()) or ())
        by_name = {item.industry_name: item for item in rows}
        leading = by_name.get(getattr(rotation, "leading_sector", None))
        trailing = by_name.get(getattr(rotation, "trailing_sector", None))
        leading_text = getattr(rotation, "leading_sector", None) or "未定義"
        trailing_text = getattr(rotation, "trailing_sector", None) or "未定義"
        detail = (
            f"5日／20日超額BP：{leading.excess_5d_bp if leading else 'N/A'}／"
            f"{leading.excess_20d_bp if leading else 'N/A'}；"
            f"覆蓋：{leading.coverage_5d_bp if leading else 'N/A'}／"
            f"{leading.coverage_20d_bp if leading else 'N/A'} bp；"
            f"代表股：{', '.join(item.stock_code for item in leading.representative_stocks[:3]) if leading else '無'}"
        )
        return (
            f"可比產業（相對 TAIEX）｜領先：{leading_text}；落後：{trailing_text}；"
            f"輪動強度BP：{rotation.rotation_intensity_bp if rotation.rotation_intensity_bp is not None else 'N/A'}；"
            f"{detail}｜資料日 {getattr(strength, 'as_of_date', None) or '未知'}；"
            f"來源 {getattr(strength, 'source_id', '未知')}；"
            f"映射版本 {getattr(strength, 'mapping_version', '未知')}；"
            f"層級分開排名；映射為 current research only"
        )

    @staticmethod
    def _format_share_count(value: int | None) -> str:
        return f"{value:,}" if value is not None else "N/A"

    def _render_market_data_visibility(
        self, summary: MarketDataVisibilitySummary | None
    ) -> None:
        self._clear_institutional_flow_bar()
        if summary is None:
            self.visibility_quality_badge.setText(self._visibility_quality_label("MISSING"))
            self.visibility_quality_badge.set_quality("missing")
            self.visibility_quality_badge.setToolTip(status_detail("MISSING", dimension="data"))
            self.market_data_impact_label.setText(
                "資料影響：資料缺件，市場輔助資料尚未確認；不能把空白當成安全訊號。"
            )
            self.revenue_visibility_card.value_label.setText("尚未匯入（0 筆）")
            self.institutional_visibility_card.value_label.setText("尚未匯入（0 筆）")
            self.visibility_sources_label.setText(
                f"來源狀態：{self._visibility_quality_label('MISSING')}"
            )
            return

        quality = str(summary.overall_quality).upper()
        self.visibility_quality_badge.setText(self._visibility_quality_label(quality))
        self.visibility_quality_badge.set_quality(quality.lower())
        self.visibility_quality_badge.setToolTip(status_detail(quality, dimension="data"))
        impact_text = {
            "OBSERVED": "資料影響：市場輔助資料可檢視；仍以各項警示與日期為準。",
            "ESTIMATED": "資料影響：部分資料為估算；完整判讀請查看來源狀態。",
            "DEGRADED": "資料影響：資料降級；市場重點需保留不確定性。",
            "MISSING": "資料影響：資料缺件；無法完整確認市場重點。",
        }.get(
            quality,
            "資料影響：狀態未知；不能把未知畫成安全。",
        )
        self.market_data_impact_label.setText(impact_text)

        revenue = summary.monthly_revenue
        if revenue.latest_period is None:
            revenue_text = "尚未匯入（0 筆）"
        else:
            revenue_text = (
                f"{revenue.latest_period}｜{revenue.stock_count} 檔\n"
                f"月增正向 {self._format_ratio_bp(revenue.mom_positive_ratio_bp)}｜"
                f"年增正向 {self._format_ratio_bp(revenue.yoy_positive_ratio_bp)}"
            )
        self.revenue_visibility_card.value_label.setText(revenue_text)

        institutional = summary.institutional_flow
        if institutional.latest_date is None or str(institutional.quality).upper() == "MISSING":
            institutional_text = "、".join(institutional.warnings) or "尚未匯入（0 筆）"
        else:
            institutional_text = (
                f"{institutional.latest_date}｜{institutional.stock_count} 檔\n"
                f"外資 {self._format_share_count(institutional.foreign_net_shares)} 股｜"
                f"投信 {self._format_share_count(institutional.investment_trust_net_shares)} 股｜"
                f"自營商 {self._format_share_count(institutional.dealer_net_shares)} 股"
            )
        institutional_warnings = tuple(getattr(institutional, "warnings", ()) or ())
        if institutional_warnings and institutional.latest_date is not None and str(
            institutional.quality
        ).upper() != "MISSING":
            institutional_text += "\n提示：" + "、".join(
                str(item) for item in institutional_warnings
            )
        self.institutional_visibility_card.value_label.setText(institutional_text)
        self._render_institutional_flow_bar(institutional, summary.as_of_date)

        source_lines: list[str] = []
        for status in summary.source_statuses:
            source_lines.append(
                f"{status.display_name}｜{self._visibility_quality_label(status.quality)}｜"
                f"{status.row_count:,} 列／{status.stock_count:,} 檔"
            )
            source_lines.append(
                f"  觀測至 {status.latest_observation_date or '未確認'}；"
                f"可得日 {status.available_date or '未確認'}；"
                f"{self._visibility_pit_label(status.pit_status)}；"
                f"資格 {self._visibility_eligibility_label(status.eligibility)}"
            )
            warnings = tuple(str(item) for item in (status.warnings or ()))
            display_warnings = tuple(
                (
                    warning.replace("公告日缺漏 ", "公告日期缺漏 ", 1)
                    if warning.startswith("公告日缺漏 ")
                    else warning
                )
                for warning in warnings
                if warning != "historical_pit_unverified"
            )
            if display_warnings:
                source_lines.append("  缺口／提示：" + "；".join(display_warnings))
        current_observations = getattr(
            summary, "current_fundamental_observations", None
        )
        if current_observations is not None:
            source_lines.append("現況基本面觀測（僅研究，不代表來源驗收）")
            if current_observations.state == "unavailable":
                source_lines.append(
                    "  筆數未知；資料表或欄位無法唯讀彙總。"
                    + ("；".join(current_observations.warnings or ()) or "請檢查資料庫診斷。")
                )
            else:
                row_count = current_observations.row_count
                stock_count = current_observations.stock_count
                source_lines.append(
                    f"  {row_count:,} 列／{stock_count:,} 檔；資格僅供研究；"
                    f"PIT {self._visibility_pit_label(current_observations.pit_status)}"
                )
                source_lines.append(
                    "  樣本截至 "
                    f"{current_observations.latest_as_of_date or '未確認'}；"
                    "原始最新觀測／可得時間（語意未驗）："
                    f"{current_observations.latest_observed_at or '未提供'}／"
                    f"{current_observations.latest_source_available_at or '未提供'}"
                )
                for title, attribute in (
                    ("市場", "market_counts"),
                    ("資料種類", "kind_counts"),
                    ("來源", "source_counts"),
                    ("來源版本", "source_version_counts"),
                    ("期間基準", "period_basis_counts"),
                ):
                    categories = tuple(getattr(current_observations, attribute, ()) or ())
                    if categories:
                        values = "、".join(
                            f"{item.value if item.value is not None else '未提供'} {item.row_count:,} 列"
                            for item in categories
                        )
                        source_lines.append(f"  {title}：{values}")
                basis_verified = current_observations.basis_verified_count
                basis_unverified = current_observations.basis_unverified_count
                basis_unknown = current_observations.basis_unknown_count
                eligible = current_observations.aggregate_feature_eligible_count
                ineligible = current_observations.aggregate_feature_ineligible_count
                eligibility_unknown = (
                    current_observations.aggregate_feature_eligibility_unknown_count
                )
                available_known = current_observations.source_available_at_known_count
                available_missing = current_observations.source_available_at_missing_count
                available_after_cutoff = (
                    current_observations.source_available_at_after_as_of_date_count
                )
                source_lines.append(
                    "  基準已驗證／未驗證／未知："
                    f"{basis_verified if basis_verified is not None else '未知'}／"
                    f"{basis_unverified if basis_unverified is not None else '未知'}／"
                    f"{basis_unknown if basis_unknown is not None else '未知'}"
                )
                source_lines.append(
                    "  aggregate feature 標記 eligible／ineligible／未知："
                    f"{eligible if eligible is not None else '未知'}／"
                    f"{ineligible if ineligible is not None else '未知'}／"
                    f"{eligibility_unknown if eligibility_unknown is not None else '未知'}"
                )
                source_lines.append(
                    "  source available-at 已知／缺漏／晚於判斷日："
                    f"{available_known if available_known is not None else '未知'}／"
                    f"{available_missing if available_missing is not None else '未知'}／"
                    f"{available_after_cutoff if available_after_cutoff is not None else '未知'}"
                )
                if current_observations.warnings:
                    source_lines.append(
                        "  缺口／提示：" + "；".join(current_observations.warnings)
                    )
        self.visibility_sources_label.setText("\n".join(source_lines) or "來源狀態：缺漏")
        if source_lines:
            self.visibility_quality_badge.setToolTip(
                status_detail(quality, dimension="data") + "\n" + "\n".join(source_lines)
            )

    def _clear_institutional_flow_bar(self) -> None:
        for label, bar, amount in self.institutional_flow_rows.values():
            self.institutional_flow_bar_layout.removeWidget(label)
            self.institutional_flow_bar_layout.removeWidget(bar)
            self.institutional_flow_bar_layout.removeWidget(amount)
            label.setParent(None)
            bar.setParent(None)
            amount.setParent(None)
            label.deleteLater()
            bar.deleteLater()
            amount.deleteLater()
        self.institutional_flow_rows.clear()
        self.institutional_flow_bar.hide()

    def _render_institutional_flow_bar(
        self, institutional: Any, summary_as_of_date: Any
    ) -> None:
        self._clear_institutional_flow_bar()
        values = (
            ("外資", getattr(institutional, "foreign_net_shares", None)),
            ("投信", getattr(institutional, "investment_trust_net_shares", None)),
            ("自營商", getattr(institutional, "dealer_net_shares", None)),
        )
        raw_quality = getattr(institutional, "quality", "UNKNOWN")
        quality = str(getattr(raw_quality, "value", raw_quality)).upper()
        if quality not in {"OBSERVED", "ESTIMATED", "DEGRADED"}:
            return
        if any(type(value) is not int for _, value in values):
            return
        source_date = getattr(institutional, "latest_date", None)
        try:
            source_cutoff = date.fromisoformat(source_date)
            decision_date = (
                summary_as_of_date
                if type(summary_as_of_date) is date
                else date.fromisoformat(summary_as_of_date)
            )
        except (TypeError, ValueError):
            return
        if (
            source_cutoff.isoformat() != source_date
            or type(decision_date) is not date
            or source_cutoff > decision_date
        ):
            return

        scale = max(abs(value) for _, value in values)
        half_width = 52
        for row_index, (name, value) in enumerate(values):
            label = QLabel(name)
            label.setObjectName(f"decisionDeskInstitutionalFlowLabel{row_index}")
            label.setAccessibleName(name)
            label.setMinimumWidth(42)
            amount = QLabel(f"{value:+,} 股")
            amount.setObjectName(f"decisionDeskInstitutionalFlowAmount{row_index}")
            amount.setAccessibleName(f"{name}淨買賣超 {value:+,} 股")
            amount.setToolTip(f"{source_date}｜{name}：{value:+,} 股｜品質：{quality}")
            amount.setStyleSheet(f"color: {MIDNIGHT_ANALYST.text_secondary}; font-size: 9pt;")
            bar = QFrame(self.institutional_flow_bar)
            bar.setObjectName(f"decisionDeskInstitutionalFlowSegment{row_index}")
            bar.setProperty("netShares", value)
            bar.setProperty("relativeScaleMax", scale)
            bar.setProperty("sourceDate", source_date)
            bar.setProperty("quality", quality)
            bar.setAccessibleName(f"{name} {value:+,} 股")
            bar.setToolTip(f"{source_date}｜{name}：{value:+,} 股｜品質：{quality}")
            color = (
                MIDNIGHT_ANALYST.market_up
                if value > 0
                else MIDNIGHT_ANALYST.market_down
                if value < 0
                else MIDNIGHT_ANALYST.market_flat
            )
            bar.setStyleSheet(f"background-color: {color}; border-radius: 2px;")
            length = 0 if scale == 0 else max(1, abs(value) * half_width // scale)
            bar.setFixedHeight(10)
            bar.setFixedWidth(length if value else 3)
            self.institutional_flow_bar_layout.addWidget(label, row_index, 0)
            if value < 0:
                self.institutional_flow_bar_layout.addWidget(
                    bar, row_index, 1, alignment=Qt.AlignRight | Qt.AlignVCenter
                )
            else:
                self.institutional_flow_bar_layout.addWidget(
                    bar, row_index, 3, alignment=Qt.AlignLeft | Qt.AlignVCenter
                )
            self.institutional_flow_bar_layout.addWidget(amount, row_index, 4)
            self.institutional_flow_rows[name] = (label, bar, amount)

        self.institutional_flow_bar_layout.setColumnMinimumWidth(1, half_width)
        self.institutional_flow_bar_layout.setColumnMinimumWidth(2, 1)
        self.institutional_flow_bar_layout.setColumnMinimumWidth(3, half_width)
        self.institutional_flow_bar.setAccessibleDescription(
            f"資料日 {source_date}；品質 {quality}；單位股；三列共用零軸與相對尺度，最大絕對值 {scale:,} 股。"
        )
        self.institutional_flow_bar.show()

    def _render_answer_first_dashboard(self, snapshot: DecisionDeskSnapshot) -> None:
        action = getattr(snapshot, "action_summary", None)
        if action is None:
            self.action_headline_label.setText("今日主結論：尚未產生")
            self.action_note_label.setText("研究模式：以下為市場與籌碼輔助判讀，不是交易建議。")
        else:
            self.action_headline_label.setText(action.headline)
            self.action_note_label.setText(action.research_mode_note)

        sector_focus = getattr(snapshot, "sector_focus", None)
        if sector_focus is None:
            self.priority_sector_label.setText("優先產業：尚未產生")
            self.risk_sector_label.setText("避開產業 / 風險區：尚未產生")
        else:
            self.priority_sector_label.setText(
                "優先產業：" + self._format_sector_cards(sector_focus.priority_sectors)
            )
            self.risk_sector_label.setText(
                "避開產業 / 風險區：" + self._format_sector_cards(sector_focus.risk_sectors)
            )

        stock_focus = getattr(snapshot, "stock_focus", None)
        if stock_focus is None:
            self.priority_stock_label.setText("優先研究股票：尚未產生")
            self.risk_stock_label.setText("風險股票：尚未產生")
            self._set_stock_focus_buttons(())
        else:
            self.priority_stock_label.setText(
                "優先研究股票：" + self._format_stock_cards(stock_focus.priority_stocks)
            )
            self.risk_stock_label.setText("風險股票：" + self._format_stock_cards(stock_focus.risk_stocks))
            self._set_stock_focus_buttons(tuple(stock_focus.priority_stocks) + tuple(stock_focus.risk_stocks))
        self._render_presentation_contract(snapshot)

    def _render_presentation_contract(self, snapshot: DecisionDeskSnapshot) -> None:
        focus = getattr(snapshot, "stock_focus", None)
        cards = () if focus is None else (*focus.priority_stocks, *focus.risk_stocks)
        if not cards:
            self.presentation_contract_label.setText(
                "目前沒有可呈現的個股焦點；缺資料不等於看多或看空。"
            )
            return
        rows = []
        for card in cards[:6]:
            presentation = self.presentation_service.from_market_focus_card(
                card,
                as_of_date=self._focus_stock_data_date(card, snapshot),
            )
            rows.append(f"{presentation.stock_code} {presentation.stock_name}\n{format_decision_presentation(presentation)}")
        self.presentation_contract_label.setText("\n\n".join(rows))

    @staticmethod
    def _focus_stock_data_date(card: Any, snapshot: DecisionDeskSnapshot | None) -> date | None:
        """只傳遞相對強弱來源已證明的有效資料日。"""

        if snapshot is None:
            return None
        source = str(getattr(card, "source", "") or "")
        if source not in {"relative_strength", "relative_strength_liquidity"}:
            return None

        summary = getattr(snapshot, "relative_strength_liquidity", None)
        if not isinstance(summary, RelativeStrengthLiquiditySummary):
            return None
        if summary.quality == DecisionDeskQuality.MISSING:
            return None
        meta = summary.meta
        if not isinstance(meta, dict) or meta.get("source") != "relative_strength_liquidity_service":
            return None

        stock_code = str(getattr(card, "stock_code", "") or "").strip()
        if source == "relative_strength" and stock_code not in summary.top_strength_codes:
            return None
        if source == "relative_strength_liquidity" and stock_code not in (
            *summary.weak_strength_codes,
            *summary.low_liquidity_codes,
        ):
            return None

        effective_date = summary.as_of_date
        decision_date = snapshot.as_of_date
        if (
            not isinstance(effective_date, date)
            or isinstance(effective_date, datetime)
            or not isinstance(decision_date, date)
            or isinstance(decision_date, datetime)
            or effective_date > decision_date
        ):
            return None
        return effective_date

    @staticmethod
    def _format_sector_cards(cards) -> str:
        if not cards:
            return "無"
        return "；".join(f"{card.sector_name}（{card.reason}）" for card in cards[:5])

    @staticmethod
    def _format_stock_cards(cards) -> str:
        if not cards:
            return "無"
        return "；".join(f"{card.stock_code} {card.reason}" for card in cards[:5])

    def _set_stock_focus_buttons(self, cards) -> None:
        while self.stock_focus_button_layout.count():
            item = self.stock_focus_button_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.stock_focus_buttons = []
        self._stock_focus_research_card = None
        for card in cards[:6]:
            button = QPushButton(str(card.stock_code))
            button.setToolTip(f"開啟主力流向：{card.stock_code} {card.reason}")
            button.clicked.connect(lambda checked=False, code=str(card.stock_code): self._navigate_to_smart_money(code))
            self.stock_focus_button_layout.addWidget(button)
            self.stock_focus_buttons.append(button)
        self.stock_focus_button_layout.addStretch()
        first_card = next(iter(cards[:6]), None)
        self._stock_focus_research_card = first_card
        if first_card is None:
            self.stock_focus_research_button.setText("開啟焦點研究報告")
            self.stock_focus_research_button.setEnabled(False)
        else:
            self.stock_focus_research_button.setText(
                f"開啟 {first_card.stock_code} 研究報告"
            )
            self.stock_focus_research_button.setEnabled(True)

    def _set_industry_focus_buttons(self, rotation, as_of_date: date) -> None:
        while self.industry_focus_button_layout.count():
            item = self.industry_focus_button_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.industry_focus_buttons = []
        strength = getattr(rotation, "industry_strength", None)
        if strength is None:
            self.industry_focus_button_layout.addStretch()
            return
        rows = {item.industry_name: item for item in getattr(strength, "rows", ())}
        seen: set[str] = set()
        for sector_name in (
            getattr(rotation, "leading_sector", None),
            getattr(rotation, "trailing_sector", None),
        ):
            row = rows.get(sector_name)
            if row is None:
                continue
            for representative in row.representative_stocks[:3]:
                code = str(representative.stock_code)
                if not code or code in seen:
                    continue
                seen.add(code)
                button = QPushButton(f"{code} {representative.stock_name}")
                button.setAccessibleName(f"開啟{row.industry_name}代表股{code}研究報告")
                button.setToolTip(
                    f"由{row.industry_name}的可比產業排名開啟唯讀個股研究；不寫入觀察清單。"
                )
                button.clicked.connect(
                    lambda checked=False, item=representative, source_row=row: self._open_industry_stock_research(
                        item, source_row, as_of_date
                    )
                )
                self.industry_focus_button_layout.addWidget(button)
                self.industry_focus_buttons.append(button)
        self.industry_focus_button_layout.addStretch()

    def _clear_industry_strength_chart(self, message: str) -> None:
        self._industry_strength_navigation_request_id += 1
        self._industry_strength_rows = ()
        self._industry_strength_summary = None
        self._industry_strength_selected_name = ""
        self._industry_strength_expanded_name = ""
        self._industry_strength_row_buttons = []
        self._industry_strength_row_widgets = {}
        self._industry_strength_card_details = {}
        self._industry_strength_card_frames = {}
        self._industry_strength_headline_targets = {}
        self.industry_strength_meta.setText(message)
        self.industry_strength_meta.setAccessibleDescription(message)
        self.industry_strength_group_selector.blockSignals(True)
        self.industry_strength_group_selector.clear()
        self.industry_strength_group_selector.setEnabled(False)
        self.industry_strength_group_selector.blockSignals(False)
        self._clear_layout_widgets(self.industry_strength_card_grid)
        self.industry_strength_chart_header.clear()
        self._industry_strength_grid_columns = 0
        self._clear_layout_widgets(self.industry_strength_representatives_layout)
        self.industry_strength_leading_button.setText("定位來源領先")
        self.industry_strength_trailing_button.setText("定位來源落後")
        self.industry_strength_leading_button.setEnabled(False)
        self.industry_strength_trailing_button.setEnabled(False)
        self.industry_strength_navigation_status.setText(
            "領先／落後定位暫不可用：目前沒有可用快照列。"
        )
        self.industry_strength_empty_state.clear()
        self.industry_strength_empty_state.hide()
        self.industry_strength_chart_scroll.hide()
        self.industry_strength_representatives.hide()

    @staticmethod
    def _clear_layout_widgets(layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.setEnabled(False)
                widget.setParent(None)
                widget.deleteLater()

    @staticmethod
    def _industry_strength_group_label(level: str, scope: str) -> str:
        normalized_level = level.strip().lower()
        normalized_scope = scope.strip().lower()
        level_label = {
            "leaf": "細分產業",
            "aggregate": "整體層級",
        }.get(normalized_level, "未知層級")
        scope_label = {
            "twse": "上市（TWSE）",
            "tpex": "上櫃（TPEx）",
        }.get(normalized_scope, "未知市場範圍")
        return f"層級：{level_label}｜市場範圍：{scope_label}"

    def _update_industry_strength_group_description(self) -> None:
        selected_group = self.industry_strength_group_selector.currentData()
        if not selected_group:
            detail = "目前沒有可比產業群組；原始層級與市場範圍未知。"
        else:
            level, scope = tuple(selected_group)
            display = self._industry_strength_group_label(str(level), str(scope))
            detail = f"目前群組：{display}；原始代碼：industry_level={level}，market_scope={scope}。"
        self.industry_strength_group_selector.setToolTip(
            "選取要比較的產業層級與市場範圍。"
        )
        self.industry_strength_group_selector.setAccessibleDescription(detail)

    def _on_industry_strength_group_changed(self, *_args) -> None:
        self._industry_strength_navigation_request_id += 1
        self._update_industry_strength_group_description()
        self._render_selected_industry_strength_group()

    def _render_industry_strength_chart(self, rotation, as_of_date: date) -> None:
        self._industry_strength_navigation_request_id += 1
        strength = getattr(rotation, "industry_strength", None)
        rows = tuple(getattr(strength, "rows", ()) or ()) if strength is not None else ()
        if strength is None or not rows:
            self._clear_industry_strength_chart(
                "可比產業資料缺件（Unknown）；此狀態不代表超額表現為 0。"
            )
            return

        self._industry_strength_rows = rows
        self._industry_strength_summary = strength
        self._industry_strength_as_of_date = as_of_date
        headlines = {
            "leading": getattr(rotation, "leading_sector", None),
            "trailing": getattr(rotation, "trailing_sector", None),
        }
        self._industry_strength_headline_targets = {
            key: target
            for key, name in headlines.items()
            if (target := self._resolve_industry_strength_headline_target(name)) is not None
        }
        self._update_industry_strength_navigation(headlines)
        groups: dict[tuple[str, str], list[Any]] = {}
        for row in rows:
            groups.setdefault((str(row.industry_level or "Unknown"), str(row.market_scope or "Unknown")), []).append(row)

        previous_group = self.industry_strength_group_selector.currentData()
        self.industry_strength_group_selector.blockSignals(True)
        self.industry_strength_group_selector.clear()
        group_keys = tuple(groups)
        for level, scope in group_keys:
            self.industry_strength_group_selector.addItem(
                self._industry_strength_group_label(level, scope), (level, scope)
            )
            self.industry_strength_group_selector.setItemData(
                self.industry_strength_group_selector.count() - 1,
                "選取要比較的產業層級與市場範圍。",
                Qt.ToolTipRole,
            )
        if previous_group in group_keys:
            self.industry_strength_group_selector.setCurrentIndex(group_keys.index(previous_group))
        else:
            self.industry_strength_group_selector.setCurrentIndex(0)
        self.industry_strength_group_selector.setEnabled(len(group_keys) > 1)
        self.industry_strength_group_selector.blockSignals(False)
        self._update_industry_strength_group_description()

        coverage = getattr(strength, "coverage", {}) or {}
        coverage_items = [f"{key}={value}" for key, value in sorted(coverage.items())[:3]]
        coverage_text = ", ".join(coverage_items) if coverage_items else "Unknown"
        benchmark = getattr(strength, "benchmark_name", None) or "Unknown"
        data_date = getattr(strength, "as_of_date", None)
        source_id = getattr(strength, "source_id", None) or "Unknown"
        source_version = getattr(strength, "source_version", None) or "Unknown"
        mapping_version = getattr(strength, "mapping_version", None) or "Unknown"
        mapping_date = getattr(strength, "mapping_observed_date", None) or "Unknown"
        quality = self._quality_label(strength.quality)
        warning_text = "、".join(str(item) for item in getattr(strength, "warnings", ())[:3]) or "無"
        self.industry_strength_meta.setText(
            f"相對 {benchmark} 超額 bp｜資料日 {data_date or 'Unknown'}｜品質 {quality}｜"
            "僅供當期研究（非歷史 PIT）｜5／20 日共用 0 軸與尺度"
        )
        detail = (
            f"基準：{benchmark}（來源 {getattr(strength, 'benchmark_source_id', None) or 'Unknown'}；"
            f"觀測日 {getattr(strength, 'benchmark_observed_date', None) or 'Unknown'}）｜"
            f"資料日：{data_date or 'Unknown'}｜摘要覆蓋：{coverage_text}｜品質：{quality}｜警示：{warning_text}｜"
            f"來源：{source_id}（{source_version}）｜映射：{mapping_version}／觀測日 {mapping_date}｜"
            f"current research only（僅供當期研究）；歷史 PIT：{'可用' if strength.historical_pit_eligible else '不適用'}。"
            "正負表示相對基準超額，不代表股價漲跌；同一選定層級與市場範圍內，5 日與 20 日共用絕對值尺度。"
        )
        self.industry_strength_meta.setToolTip(
            f"超額＝產業指數報酬減去 {benchmark} 報酬；正值代表領先、負值代表落後。"
            "成分資料覆蓋率是具備期間行情、可計算報酬的成分股比例。"
            "點卡片標題可查看期間明細、品質與來源。此資料僅供當期研究，非歷史 PIT。"
        )
        self.industry_strength_meta.setAccessibleDescription(detail)
        self.industry_strength_panel.setToolTip("")
        self.industry_strength_panel.setAccessibleDescription(detail)
        self.industry_strength_chart_scroll.show()
        self.industry_strength_empty_state.hide()
        self._render_selected_industry_strength_group()

    def _resolve_industry_strength_headline_target(self, headline) -> tuple[tuple[str, str], Any] | None:
        name = str(headline or "").strip()
        if not name:
            return None
        matches = tuple(row for row in self._industry_strength_rows if row.industry_name == name)
        if len(matches) != 1 or matches[0].excess_20d_bp is None:
            return None
        row = matches[0]
        group = (str(row.industry_level or "Unknown"), str(row.market_scope or "Unknown"))
        return group, row

    def _update_industry_strength_navigation(self, headlines: dict[str, Any]) -> None:
        statuses = []
        for key, title, button in (
            ("leading", "領先", self.industry_strength_leading_button),
            ("trailing", "落後", self.industry_strength_trailing_button),
        ):
            name = str(headlines.get(key) or "").strip()
            target = self._industry_strength_headline_targets.get(key)
            if target is not None:
                button.setText(f"定位來源{title}")
                button.setEnabled(True)
                button.setToolTip(f"定位來源提供的 20 日{title}列：{name}")
                button.setAccessibleDescription(
                    f"使用來源提供的 20 日{title}名稱 {name}，切換到其原始層級與市場範圍並定位原始列。"
                )
                statuses.append(f"{title}：{name}（可定位）")
            else:
                reason = (
                    "來源未提供名稱"
                    if not name
                    else "來源名稱不唯一、未出現在產業列表，或缺少 20 日超額值"
                )
                button.setText(f"定位來源{title}：不可用")
                button.setEnabled(False)
                button.setToolTip(f"20 日{title}列無法定位：{reason}")
                button.setAccessibleDescription(f"{title}定位不可用：{reason}。不推算排名或跨市場範圍尋找。")
                statuses.append(f"{title}：{reason}")
        detail = "；".join(statuses) + "。定位依來源提供的領先／落後名稱與同一份產業資料，不重算排名。"
        self.industry_strength_navigation_status.setText(detail)
        self.industry_strength_navigation_status.setAccessibleDescription(detail)

    def _locate_industry_strength_headline(self, key: str) -> None:
        target = self._industry_strength_headline_targets.get(key)
        if target is None:
            return
        self._industry_strength_navigation_request_id += 1
        group, row = target
        group_index = next(
            (
                index
                for index in range(self.industry_strength_group_selector.count())
                if tuple(self.industry_strength_group_selector.itemData(index) or ()) == group
            ),
            -1,
        )
        if group_index < 0:
            return
        if self.industry_strength_group_selector.currentIndex() != group_index:
            self.industry_strength_group_selector.setCurrentIndex(group_index)
        row_widget = self._industry_strength_row_widgets.get(
            (group[0], group[1], row.industry_name)
        )
        if row_widget is None:
            return
        self._select_industry_strength_row(row.industry_name, preserve_navigation_request=True)
        request_id = self._industry_strength_navigation_request_id
        refresh_generation = self._refresh_generation
        summary = self._industry_strength_summary
        QTimer.singleShot(
            0,
            lambda: self._scroll_to_industry_strength_row(
                request_id,
                refresh_generation,
                summary,
                group,
                row.industry_name,
                row_widget,
            ),
        )

    def _scroll_to_industry_strength_row(
        self,
        request_id: int,
        refresh_generation: int,
        summary,
        group: tuple[str, str],
        industry_name: str,
        row_widget: QWidget,
    ) -> None:
        row_key = (group[0], group[1], industry_name)
        current_group = tuple(self.industry_strength_group_selector.currentData() or ())
        if (
            self._closing
            or request_id != self._industry_strength_navigation_request_id
            or refresh_generation != self._refresh_generation
            or summary is not self._industry_strength_summary
            or current_group != group
            or self._industry_strength_selected_name != industry_name
            or self._industry_strength_row_widgets.get(row_key) is not row_widget
            or not self.industry_strength_chart_scroll.isVisible()
            or row_widget.isHidden()
        ):
            return
        self.industry_strength_chart_layout.activate()
        self.industry_strength_chart_content.adjustSize()
        self.industry_strength_chart_layout.activate()
        self.industry_strength_chart_scroll.ensureWidgetVisible(row_widget, 0, 8)
        # An expanded card can be taller than the bounded inner viewport. In that
        # case ensureWidgetVisible aligns its bottom and clips the title; anchor
        # the card top so the user sees where to start before scrolling its detail.
        row_top = row_widget.mapTo(
            self.industry_strength_chart_content, QPoint(0, 0)
        ).y()
        if row_widget.height() > self.industry_strength_chart_scroll.viewport().height():
            self.industry_strength_chart_scroll.verticalScrollBar().setValue(row_top)
        main_content = self.main_scroll_area.widget()
        main_layout = main_content.layout() if main_content is not None else None
        if main_layout is not None:
            main_layout.activate()
        self.main_scroll_area.ensureWidgetVisible(row_widget, 0, 12)
        representative_buttons = self.industry_strength_representatives.findChildren(QPushButton)
        if representative_buttons and self.industry_strength_representatives.isVisible():
            self.main_scroll_area.ensureWidgetVisible(
                self.industry_strength_representatives, 0, 8
            )

    def _render_selected_industry_strength_group(self, *_args) -> None:
        self.industry_strength_chart_scroll.setMinimumHeight(230)
        self.industry_strength_chart_scroll.setMaximumHeight(235)
        self._clear_layout_widgets(self.industry_strength_card_grid)
        self.industry_strength_chart_header.clear()
        self._clear_layout_widgets(self.industry_strength_representatives_layout)
        self._industry_strength_row_buttons = []
        self._industry_strength_row_widgets = {}
        self._industry_strength_card_details = {}
        self._industry_strength_card_frames = {}
        self._industry_strength_expanded_name = ""
        selected_group = self.industry_strength_group_selector.currentData()
        if not selected_group or not self._industry_strength_rows:
            return
        rows = tuple(
            row for row in self._industry_strength_rows
            if (str(row.industry_level or "Unknown"), str(row.market_scope or "Unknown")) == tuple(selected_group)
        )
        if not rows:
            self.industry_strength_chart_header.clear()
            return
        selected_exists = any(row.industry_name == self._industry_strength_selected_name for row in rows)
        if not selected_exists:
            self._industry_strength_selected_name = rows[0].industry_name
        if all(row.excess_5d_bp is None and row.excess_20d_bp is None for row in rows):
            self.industry_strength_empty_state.setText(
                "此群組 5 日與 20 日超額值皆為 Unknown（無可比數值）；來源、資料日與品質資訊仍見上方摘要。"
            )
            self.industry_strength_empty_state.setAccessibleDescription(
                "此群組的 5 日與 20 日超額值皆缺失；缺值不代表 0。"
            )
            self.industry_strength_chart_scroll.hide()
            self.industry_strength_representatives.hide()
            self.industry_strength_empty_state.show()
            return
        self.industry_strength_empty_state.hide()
        self.industry_strength_chart_scroll.show()
        common_max_abs = max(
            (
                abs(value)
                for row in rows
                for value in (row.excess_5d_bp, row.excess_20d_bp)
                if value is not None
            ),
            default=0,
        )
        benchmark = getattr(self._industry_strength_summary, "benchmark_name", None) or "Unknown"
        self.industry_strength_chart_header.setText(
            f"相對 {benchmark}｜5 日與 20 日共用零軸及尺度。"
            "正值代表領先大盤，負值代表落後；成分資料覆蓋率另列。點卡片標題展開詳情。"
        )
        columns = self._industry_strength_columns_for_width(
            self.industry_strength_chart_scroll.viewport().width()
        )
        self._industry_strength_grid_columns = columns
        for column in range(3):
            self.industry_strength_card_grid.setColumnStretch(
                column, 1 if column < columns else 0
            )
        for index, row in enumerate(rows):
            row_widget, selector, details = self._build_industry_strength_card(
                row, benchmark, common_max_abs
            )
            self.industry_strength_card_grid.addWidget(
                row_widget, index // columns, index % columns
            )
            self._industry_strength_card_details[row.industry_name] = details
            self._industry_strength_card_frames[row.industry_name] = row_widget
            self._industry_strength_row_widgets[
                (
                    str(row.industry_level or "Unknown"),
                    str(row.market_scope or "Unknown"),
                    row.industry_name,
                )
            ] = row_widget
        self._reflow_industry_strength_cards()
        for name, card in self._industry_strength_card_frames.items():
            border_color = (
                MIDNIGHT_ANALYST.accent
                if name == self._industry_strength_selected_name
                else MIDNIGHT_ANALYST.border
            )
            card.setStyleSheet(
                f"QFrame#decisionDeskIndustryStrengthCard {{ background: {MIDNIGHT_ANALYST.surface_1}; "
                f"border: 1px solid {border_color}; border-radius: 8px; }}"
            )
        if self._industry_strength_selected_name:
            for button in self._industry_strength_row_buttons:
                if button.text() == self._industry_strength_selected_name:
                    button.setChecked(False)
        self._update_industry_strength_representatives(rows)

    def _sync_industry_strength_chart_height(self) -> None:
        if not self._industry_strength_expanded_name:
            self.industry_strength_chart_scroll.setMinimumHeight(230)
            self.industry_strength_chart_scroll.setMaximumHeight(235)
            return
        card = self._industry_strength_card_frames.get(
            self._industry_strength_expanded_name
        )
        if card is None:
            return
        card.adjustSize()
        needed = (
            card.sizeHint().height()
            + self.industry_strength_chart_header.sizeHint().height()
            + 40
        )
        height = min(500, max(235, needed))
        self.industry_strength_chart_scroll.setMinimumHeight(height)
        self.industry_strength_chart_scroll.setMaximumHeight(height)

    @staticmethod
    def _industry_strength_columns_for_width(width: int) -> int:
        return 3 if width >= 1020 else 2 if width >= 660 else 1

    @staticmethod
    def _industry_strength_bp_text(value: int | None) -> str:
        if value is None:
            return "Unknown"
        if value == 0:
            return "0 bp"
        sign = "+" if value > 0 else "−"
        return f"{sign}{abs(value):,} bp"

    @staticmethod
    def _industry_strength_percent_text(value: int | None) -> str:
        if value is None:
            return "Unknown"
        sign = "+" if value > 0 else "−" if value < 0 else ""
        absolute = abs(value)
        return f"{sign}{absolute // 100}.{absolute % 100:02d}%"

    @staticmethod
    def _industry_strength_coverage_text(value: int | None) -> str:
        if value is None or value < 0 or value > 10_000:
            return "Unknown"
        if value == 10_000:
            return "100%"
        return f"{value // 100}.{value % 100:02d}%"

    @staticmethod
    def _industry_strength_direction(value: int | None) -> tuple[str, str]:
        if value is None:
            return "資料不足", MIDNIGHT_ANALYST.text_secondary
        if value > 0:
            return "領先大盤", MIDNIGHT_ANALYST.market_up
        if value < 0:
            return "落後大盤", MIDNIGHT_ANALYST.market_down
        return "與大盤持平", MIDNIGHT_ANALYST.market_flat

    @classmethod
    def _industry_strength_direction_label(cls, value: int | None) -> str:
        direction, _ = cls._industry_strength_direction(value)
        if value is None:
            return direction
        if value == 0:
            return direction
        absolute = abs(value)
        return f"{direction} {absolute // 100}.{absolute % 100:02d} 個百分點"

    def _build_industry_strength_card(
        self, row, benchmark: str, common_max_abs: int
    ) -> tuple[QFrame, QPushButton, QWidget]:
        card = QFrame()
        card.setObjectName("decisionDeskIndustryStrengthCard")
        card.setProperty("industryName", row.industry_name)
        card.setStyleSheet(
            f"QFrame#decisionDeskIndustryStrengthCard {{ background: {MIDNIGHT_ANALYST.surface_1}; "
            f"border: 1px solid {MIDNIGHT_ANALYST.border}; border-radius: 8px; }}"
        )
        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)

        selector = QPushButton(row.industry_name)
        selector.setObjectName("decisionDeskIndustryStrengthCardTitle")
        selector.setCheckable(True)
        selector.setChecked(False)
        selector.setMinimumHeight(30)
        selector.setStyleSheet(
            f"QPushButton#decisionDeskIndustryStrengthCardTitle {{ text-align: left; "
            f"color: {MIDNIGHT_ANALYST.text_primary}; background: transparent; border: 0; "
            "font-size: 11pt; font-weight: 700; padding: 2px 0; }"
            f"QPushButton#decisionDeskIndustryStrengthCardTitle:hover {{ color: {MIDNIGHT_ANALYST.accent_hover}; }}"
            f"QPushButton#decisionDeskIndustryStrengthCardTitle:checked {{ color: {MIDNIGHT_ANALYST.accent}; }}"
        )
        selector.setAccessibleName(f"展開{row.industry_name}產業卡片詳情")
        selector.setAccessibleDescription(
            f"層級 {row.industry_level}；市場範圍 {row.market_scope}；"
            f"資料品質 {self._quality_label(row.quality)}。按下可展開各期間報酬、成分資料覆蓋與來源資訊。"
        )
        selector.setToolTip("點擊展開各期間報酬、成分資料覆蓋與來源資訊。")
        selector.clicked.connect(
            lambda checked=False, name=row.industry_name: self._toggle_industry_strength_row(
                name, checked
            )
        )
        layout.addWidget(selector)
        self._industry_strength_row_buttons.append(selector)

        layout.addWidget(
            self._industry_strength_metric_lane(
                horizon="5 日",
                value=row.excess_5d_bp,
                coverage=row.coverage_5d_bp,
                max_abs=common_max_abs,
                return_bp=row.return_5d_bp,
                market_return_bp=row.market_return_5d_bp,
                eligible_count=row.eligible_stock_count_5d,
                constituent_count=row.constituent_count,
                benchmark=benchmark,
                as_of_date=getattr(self._industry_strength_summary, "as_of_date", None),
            )
        )
        layout.addWidget(
            self._industry_strength_metric_lane(
                horizon="20 日",
                value=row.excess_20d_bp,
                coverage=row.coverage_20d_bp,
                max_abs=common_max_abs,
                return_bp=row.return_20d_bp,
                market_return_bp=row.market_return_20d_bp,
                eligible_count=row.eligible_stock_count_20d,
                constituent_count=row.constituent_count,
                benchmark=benchmark,
                as_of_date=getattr(self._industry_strength_summary, "as_of_date", None),
            )
        )

        details = self._industry_strength_card_detail(row, benchmark)
        layout.addWidget(details)
        details.hide()
        return card, selector, details

    def _industry_strength_metric_lane(
        self,
        *,
        horizon: str,
        value: int | None,
        coverage: int | None,
        max_abs: int,
        return_bp: int | None,
        market_return_bp: int | None,
        eligible_count: int,
        constituent_count: int,
        benchmark: str,
        as_of_date,
    ) -> QWidget:
        lane = QWidget()
        lane.setObjectName(
            "decisionDeskIndustryStrength5dLane"
            if horizon == "5 日"
            else "decisionDeskIndustryStrength20dLane"
        )
        layout = QVBoxLayout(lane)
        layout.setContentsMargins(0, 1, 0, 1)
        layout.setSpacing(1)
        summary = QHBoxLayout()
        summary.setContentsMargins(0, 0, 0, 0)
        summary.setSpacing(5)
        period_label = QLabel(horizon)
        period_label.setFixedWidth(38)
        summary.addWidget(period_label)

        value_text = self._industry_strength_bp_text(value)
        value_label = QLabel(value_text if value is not None else "資料不足")
        value_label.setStyleSheet(
            f"color: {self._industry_strength_direction(value)[1]}; font-size: 11pt; font-weight: 700;"
        )
        summary.addWidget(value_label)

        _, direction_color = self._industry_strength_direction(value)
        direction_label = QLabel(self._industry_strength_direction_label(value))
        direction_label.setWordWrap(True)
        direction_label.setStyleSheet(
            f"color: {direction_color}; font-size: 9pt; font-weight: 600;"
        )
        summary.addWidget(direction_label)
        summary.addStretch(1)

        coverage_text = self._industry_strength_coverage_text(coverage)
        coverage_label = QLabel(
            f"成分資料 {coverage_text}" if coverage_text != "Unknown" else "成分資料未知"
        )
        coverage_label.setWordWrap(True)
        coverage_label.setAlignment(Qt.AlignCenter)
        coverage_label.setStyleSheet(
            f"color: {MIDNIGHT_ANALYST.text_secondary}; background: {MIDNIGHT_ANALYST.surface_2}; "
            f"border: 1px solid {MIDNIGHT_ANALYST.border}; border-radius: 4px; padding: 2px 5px;"
        )
        summary.addWidget(coverage_label)
        layout.addLayout(summary)

        channel = QWidget()
        channel.setMinimumHeight(8)
        channel_layout = QHBoxLayout(channel)
        channel_layout.setContentsMargins(2, 1, 2, 1)
        channel_layout.setSpacing(0)
        left = QWidget()
        left_layout = QHBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        right = QWidget()
        right_layout = QHBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        center = QFrame()
        center.setFixedWidth(1)
        center.setFixedHeight(7)
        center.setStyleSheet(f"background: {MIDNIGHT_ANALYST.text_muted};")
        segment = QFrame()
        segment.setObjectName("decisionDeskIndustryStrengthBar")
        segment.setProperty("excessBp", value)
        segment.setProperty("scaleMaxAbsBp", max_abs)
        segment.setFixedHeight(6)
        segment.setStyleSheet(
            f"background: {self._industry_strength_direction(value)[1]}; border-radius: 3px;"
        )
        segment.setFixedWidth(
            max(1, abs(value) * 90 // max_abs) if value is not None and max_abs else 0
        )
        if value is not None and value < 0:
            left_layout.addStretch(1)
            left_layout.addWidget(segment)
        else:
            left_layout.addStretch(1)
        if value is not None and value > 0:
            right_layout.addWidget(segment)
            right_layout.addStretch(1)
        else:
            right_layout.addStretch(1)
        channel_layout.addWidget(left, 1)
        channel_layout.addWidget(center)
        channel_layout.addWidget(right, 1)
        layout.addWidget(channel)

        count_text = (
            f"{eligible_count}/{constituent_count} 檔"
            if constituent_count > 0
            else "成分數未提供"
        )
        if return_bp is None:
            industry_return_text = "Unknown（缺值；不代表 0）"
        else:
            industry_return_text = self._industry_strength_percent_text(return_bp)
        if market_return_bp is None:
            market_return_text = "Unknown（缺值；不代表 0）"
        else:
            market_return_text = self._industry_strength_percent_text(market_return_bp)
        if value is None:
            excess_description = "相對超額缺值（不代表 0）"
        elif value == 0:
            excess_description = "與大盤持平 0 bp"
        else:
            direction = "領先" if value > 0 else "落後"
            absolute = abs(value)
            excess_description = (
                f"{direction} {absolute // 100}.{absolute % 100:02d} 個百分點"
                f"（{self._industry_strength_bp_text(value)}）"
            )
        tooltip = (
            f"{horizon}相對 {benchmark} 比較\n"
            f"產業指數報酬：{industry_return_text}\n"
            f"{benchmark} 報酬：{market_return_text}\n"
            f"相對表現：{excess_description}\n"
            f"可計算成分股：{count_text}（覆蓋 {coverage_text}）\n"
            f"資料日：{as_of_date or 'Unknown'}\n"
            "點擊卡片標題可看來源與品質詳情。"
        )
        lane.setAccessibleDescription(tooltip.replace("\n", "；"))
        lane.setToolTip(tooltip)
        for child in (period_label, value_label, direction_label, coverage_label, channel, segment):
            child.setToolTip(tooltip)
            child.setAccessibleDescription(tooltip.replace("\n", "；"))
        return lane

    def _industry_strength_card_detail(self, row, benchmark: str) -> QWidget:
        detail = QFrame()
        detail.setObjectName("decisionDeskIndustryStrengthCardDetail")
        detail.setStyleSheet(
            f"QFrame#decisionDeskIndustryStrengthCardDetail {{ background: {MIDNIGHT_ANALYST.surface_2}; "
            f"border: 1px solid {MIDNIGHT_ANALYST.border}; border-radius: 6px; }}"
        )
        layout = QVBoxLayout(detail)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(3)
        for period, industry_return, market_return, excess, coverage, eligible in (
            (
                "5 日",
                row.return_5d_bp,
                row.market_return_5d_bp,
                row.excess_5d_bp,
                row.coverage_5d_bp,
                row.eligible_stock_count_5d,
            ),
            (
                "20 日",
                row.return_20d_bp,
                row.market_return_20d_bp,
                row.excess_20d_bp,
                row.coverage_20d_bp,
                row.eligible_stock_count_20d,
            ),
        ):
            comparison = QLabel(
                f"{period}報酬｜產業 {self._industry_strength_percent_text(industry_return)}"
                f"｜{benchmark} {self._industry_strength_percent_text(market_return)}"
            )
            comparison.setObjectName(
                f"decisionDeskIndustryStrengthDetail{period.replace(' ', '')}Returns"
            )
            comparison.setWordWrap(True)
            comparison.setStyleSheet(
                f"color: {MIDNIGHT_ANALYST.text_primary}; font-size: 9pt;"
            )
            layout.addWidget(comparison)
            coverage_text = self._industry_strength_coverage_text(coverage)
            count_detail = (
                f"{eligible}/{row.constituent_count} 檔"
                if row.constituent_count > 0
                else "成分數未提供"
            )
            direction, _ = self._industry_strength_direction(excess)
            excess_detail = (
                "超額缺值（不代表 0）"
                if excess is None
                else f"{direction} {self._industry_strength_bp_text(excess)}"
            )
            evidence = QLabel(
                f"{excess_detail}｜可計算成分 {coverage_text}（{count_detail}）"
            )
            evidence.setWordWrap(True)
            evidence.setStyleSheet(
                f"color: {MIDNIGHT_ANALYST.text_secondary}; font-size: 8.5pt;"
            )
            layout.addWidget(evidence)

        summary = self._industry_strength_summary
        data_date = getattr(summary, "as_of_date", None) or "Unknown"
        snapshot_quality = self._quality_label(summary.quality) if summary is not None else "Unknown"
        row_quality = self._quality_label(row.quality)
        quality_detail = (
            f"快照品質 {snapshot_quality}｜此列品質 {row_quality}"
            if snapshot_quality != row_quality
            else f"品質 {snapshot_quality}"
        )
        usage = QLabel(
            f"資料日 {data_date}｜{quality_detail}｜僅供當期研究，非歷史 PIT"
        )
        usage.setWordWrap(True)
        usage.setStyleSheet(
            f"color: {MIDNIGHT_ANALYST.text_secondary}; font-size: 8.5pt;"
        )
        layout.addWidget(usage)
        provenance = QLabel(
            f"來源 {getattr(summary, 'source_id', None) or 'Unknown'}／"
            f"{getattr(summary, 'source_version', None) or 'Unknown'}；映射 "
            f"{getattr(summary, 'mapping_source_id', None) or 'Unknown'}／"
            f"{getattr(summary, 'mapping_version', None) or 'Unknown'}，觀測日 "
            f"{getattr(summary, 'mapping_observed_date', None) or 'Unknown'}"
        )
        provenance.setWordWrap(True)
        provenance.setStyleSheet(
            f"color: {MIDNIGHT_ANALYST.text_muted}; font-size: 8pt;"
        )
        layout.addWidget(provenance)
        detail.setAccessibleName(f"{row.industry_name}報酬與來源詳情")
        detail.setAccessibleDescription(
            f"{row.industry_name}。資料日 {data_date}；{quality_detail}；"
            f"來源 {getattr(summary, 'source_id', None) or 'Unknown'}，"
            f"映射 {getattr(summary, 'mapping_source_id', None) or 'Unknown'}。"
            "僅供當期研究，非歷史 PIT。"
        )
        return detail

    def _toggle_industry_strength_row(self, industry_name: str, checked: bool) -> None:
        if checked:
            self._select_industry_strength_row(industry_name)
            return
        if self._industry_strength_expanded_name != industry_name:
            return
        self._industry_strength_expanded_name = ""
        detail = self._industry_strength_card_details.get(industry_name)
        if detail is not None:
            detail.hide()
        self._sync_industry_strength_chart_height()
        for button in self._industry_strength_row_buttons:
            if button.text() == industry_name:
                button.setToolTip("點擊展開各期間報酬、成分資料覆蓋與來源資訊。")
                button.setAccessibleDescription(
                    button.accessibleDescription().split("；目前狀態：")[0]
                    + "；目前狀態：已收合。"
                )
        card = self._industry_strength_card_frames.get(industry_name)
        if card is not None:
            border_color = (
                MIDNIGHT_ANALYST.accent
                if self._industry_strength_selected_name == industry_name
                else MIDNIGHT_ANALYST.border
            )
            card.setStyleSheet(
                f"QFrame#decisionDeskIndustryStrengthCard {{ background: {MIDNIGHT_ANALYST.surface_1}; "
                f"border: 1px solid {border_color}; border-radius: 8px; }}"
            )
        self.industry_strength_chart_content.adjustSize()
        self.industry_strength_card_grid.activate()

    def _select_industry_strength_row(
        self, industry_name: str, *, preserve_navigation_request: bool = False
    ) -> None:
        if not preserve_navigation_request:
            self._industry_strength_navigation_request_id += 1
        self._industry_strength_selected_name = industry_name
        self._industry_strength_expanded_name = industry_name
        for button in self._industry_strength_row_buttons:
            is_expanded = button.text() == industry_name
            button.setChecked(is_expanded)
            button.setToolTip(
                "點擊收合此卡片詳情。"
                if is_expanded
                else "點擊展開各期間報酬、成分資料覆蓋與來源資訊。"
            )
            base_description = button.accessibleDescription().split("；目前狀態：")[0]
            button.setAccessibleDescription(
                base_description + f"；目前狀態：{'已展開' if is_expanded else '已收合'}。"
            )
        for name, details in self._industry_strength_card_details.items():
            details.setVisible(name == industry_name)
            card = self._industry_strength_card_frames.get(name)
            if card is not None:
                border_color = (
                    MIDNIGHT_ANALYST.accent
                    if name == industry_name
                    else MIDNIGHT_ANALYST.border
                )
                card.setStyleSheet(
                    f"QFrame#decisionDeskIndustryStrengthCard {{ background: {MIDNIGHT_ANALYST.surface_1}; "
                    f"border: 1px solid {border_color}; border-radius: 8px; }}"
                )
        selected_group = self.industry_strength_group_selector.currentData()
        rows = tuple(
            row for row in self._industry_strength_rows
            if selected_group
            and (str(row.industry_level or "Unknown"), str(row.market_scope or "Unknown")) == tuple(selected_group)
        )
        self._update_industry_strength_representatives(rows)
        self.industry_strength_card_grid.activate()
        self.industry_strength_chart_content.adjustSize()
        self._sync_industry_strength_chart_height()

    def _update_industry_strength_representatives(self, rows) -> None:
        self._clear_layout_widgets(self.industry_strength_representatives_layout)
        selected = next((row for row in rows if row.industry_name == self._industry_strength_selected_name), None)
        if selected is None or not selected.representative_stocks:
            placeholder = QLabel("代表股：Unknown／目前沒有代表股資料")
            placeholder.setWordWrap(True)
            self.industry_strength_representatives_layout.addWidget(placeholder)
            self.industry_strength_representatives.show()
            return
        for representative in selected.representative_stocks[:3]:
            code = str(representative.stock_code)
            button = QPushButton(f"{code} {representative.stock_name}")
            button.setAccessibleName(f"開啟{selected.industry_name}代表股{code}研究報告")
            button.setToolTip(
                f"來源產業：{selected.industry_name}；資料日 {getattr(self._industry_strength_summary, 'as_of_date', None) or 'Unknown'}；"
                "由同一份可比產業快照開啟唯讀研究。"
            )
            button.clicked.connect(
                lambda checked=False, item=representative, source_row=selected: self._open_industry_stock_research(
                    item, source_row, self._industry_strength_as_of_date
                )
            )
            self.industry_strength_representatives_layout.addWidget(button)
        self.industry_strength_representatives_layout.addStretch(1)
        self.industry_strength_representatives.show()

    def _open_industry_stock_research(self, representative, source_row, as_of_date: date) -> None:
        strength = getattr(self._last_snapshot.sector_rotation, "industry_strength", None) if self._last_snapshot else None
        source_id = str(getattr(strength, "source_id", "industry_strength.sqlite_current_research"))
        self.stockResearchRequested.emit(
            ResearchStockContextDTO(
                stock_code=str(representative.stock_code),
                stock_name=str(representative.stock_name),
                decision_date=as_of_date.isoformat(),
                data_date=(
                    str(getattr(strength, "as_of_date", None) or as_of_date.isoformat())
                ),
                source_id=source_id,
                source_version=str(getattr(strength, "source_version", "") or ""),
                mapping_source_id=str(getattr(strength, "mapping_source_id", "") or ""),
                mapping_version=str(getattr(strength, "mapping_version", "") or ""),
                mapping_observed_date=(
                    str(getattr(strength, "mapping_observed_date", None) or "")
                ),
                source_kind="industry_strength",
                source_label=f"市場總覽／{source_row.industry_name}代表股",
                source_workspace="market_explore",
            )
        )

    def _open_stock_focus_research(self) -> None:
        card = getattr(self, "_stock_focus_research_card", None)
        if card is None:
            return
        source_data_date = self._focus_stock_data_date(card, self._last_snapshot)
        self.stockResearchRequested.emit(
            ResearchStockContextDTO(
                stock_code=str(card.stock_code),
                stock_name=str(getattr(card, "stock_name", "") or ""),
                decision_date=(
                    self._last_snapshot.as_of_date.isoformat()
                    if self._last_snapshot is not None
                    else self.as_of_date.isoformat()
                ),
                data_date=source_data_date.isoformat() if source_data_date is not None else "",
                source_id=str(getattr(card, "source", "") or "decision_desk"),
                source_kind="decision_desk",
                source_label="市場總覽／關鍵股焦點",
                source_workspace="market_explore",
            )
        )

    def _navigate_to_smart_money(self, stock_code: str) -> None:
        if self.navigate_to_smart_money_callback is not None:
            self.navigate_to_smart_money_callback(str(stock_code))

    @staticmethod
    def _format_risk_prompts(summary: DecisionDeskRiskPromptSummary) -> str:
        prompts = summary.prompts
        if not prompts:
            if summary.quality == DecisionDeskQuality.OBSERVED:
                return "這份來源未列風險提示；這不代表沒有風險。"
            if summary.quality == DecisionDeskQuality.MISSING:
                return "風險提示資料缺漏，無法判定；這不代表沒有風險。"
            if summary.quality == DecisionDeskQuality.DEGRADED:
                return "風險提示資料品質降級，目前無法確認是否有提示；這不代表沒有風險。"
            return "風險提示僅有估算狀態，目前無法確認是否有提示；這不代表沒有風險。"

        rows = []
        severity_labels = {
            "info": "資訊",
            "warning": "注意",
            "critical": "嚴重",
        }
        category_labels = {
            "market_context": "市場情勢",
            "liquidity": "流動性",
            "weakness": "相對弱勢",
            "watchlist_risk": "觀察清單風險",
            "portfolio_alert": "持倉警示",
            "fundamental_diagnostic": "基本面異常",
        }
        for prompt in prompts[:5]:
            severity = severity_labels.get(prompt.severity, str(prompt.severity))
            category = category_labels.get(prompt.category, prompt.category)
            source = DecisionDeskView._display_source_label(prompt.source)
            code_text = f"｜代碼：{prompt.code}" if prompt.code else ""
            rows.append(
                f"[{severity}] {prompt.title}{code_text}\n"
                f"分類：{category}｜來源：{source}\n"
                f"原因：{prompt.reason}\n"
                f"建議檢查：{prompt.action_hint}"
            )
        if len(prompts) > 5:
            rows.append(f"另有 {len(prompts) - 5} 筆風險提示未列出。")
        return "\n\n".join(rows)

    @staticmethod
    def _risk_prompts_accessible_description(
        summary: DecisionDeskRiskPromptSummary,
    ) -> str:
        if not summary.prompts:
            return DecisionDeskView._format_risk_prompts(summary)
        lines = [
            (
                f"風險提示 {index}：原 severity={prompt.severity}；"
                f"原 category={prompt.category}；原 source={prompt.source}"
            )
            for index, prompt in enumerate(summary.prompts[:5], start=1)
        ]
        if len(summary.prompts) > 5:
            lines.append(f"另有 {len(summary.prompts) - 5} 筆提示未列出。")
        return "\n".join(lines)

    @staticmethod
    def _format_portfolio_attributions(attributions) -> str:
        if not attributions:
            return "無"
        parts = []
        for item in attributions[:3]:
            source = DecisionDeskView._display_source_label(item.source_label)
            condition = DecisionDeskView._display_condition_label(item.condition_status)
            chip = DecisionDeskView._display_chip_label(item.chip_risk_level)
            parts.append(
                f"{item.stock_code} 來源：{source}；條件：{condition}；籌碼：{chip}"
            )
        return "；".join(parts)

    @staticmethod
    def _format_code_list(codes, limit: int = 8) -> str:
        items = [str(code) for code in codes or () if str(code)]
        if not items:
            return "無"
        shown = items[:limit]
        suffix = f"（另 {len(items) - limit} 檔）" if len(items) > limit else ""
        return ", ".join(shown) + suffix

    def _display_exception_snapshot(self, error_message: str):
        self._render_saved_recommendation(None)
        self._clear_market_breadth_bar()
        now = datetime.now()
        fallback_snapshot = DecisionDeskSnapshot(
            as_of_date=self.as_of_date,
            generated_at=now,
            schema_version=1,
            overall_quality=DecisionDeskQuality.DEGRADED,
            market_regime=_EmptySection(DecisionDeskQuality.DEGRADED, warnings=(f"市場情勢:{error_message}",)),
            market_breadth=_EmptySection(DecisionDeskQuality.DEGRADED, warnings=(f"市場廣度:{error_message}",)),
            sector_rotation=_EmptySection(DecisionDeskQuality.DEGRADED, warnings=(f"產業輪動:{error_message}",)),
            relative_strength_liquidity=_EmptySection(DecisionDeskQuality.DEGRADED, warnings=(f"強弱與流動性:{error_message}",)),
            watchlist_triggers=_EmptySection(DecisionDeskQuality.DEGRADED, warnings=(f"Watchlist:{error_message}",)),
            portfolio_alerts=_EmptySection(DecisionDeskQuality.DEGRADED, warnings=(f"持倉警示:{error_message}",)),
            risk_prompts=_EmptySection(DecisionDeskQuality.DEGRADED, warnings=(f"風險提示:{error_message}",)),
            warnings=(f"snapshot_error:{error_message}",),
        )
        self._render_snapshot(fallback_snapshot)
        self.overall_status_label.setText("摘要載入失敗；請查看警示")

    @staticmethod
    def _quality_label(quality: DecisionDeskQuality) -> str:
        raw = getattr(quality, "value", quality)
        shared_label = status_label(quality, dimension="data")
        return {"estimated": "估算"}.get(str(raw).strip().lower(), shared_label)

    @staticmethod
    def _quality_token(quality: DecisionDeskQuality) -> str:
        return quality.value if hasattr(quality, "value") else str(quality).lower()

    @staticmethod
    def _collect_warnings(snapshot: DecisionDeskSnapshot) -> list[str]:
        lines: list[str] = []
        section_statuses = [
            ("市場情勢", snapshot.market_regime.warnings),
            ("市場廣度", snapshot.market_breadth.warnings),
            ("產業輪動", snapshot.sector_rotation.warnings),
            ("強弱與流動性", snapshot.relative_strength_liquidity.warnings),
            ("Watchlist", snapshot.watchlist_triggers.warnings),
            ("持倉警示", snapshot.portfolio_alerts.warnings),
            ("風險提示", snapshot.risk_prompts.warnings),
        ]
        for section_name, section_warnings in section_statuses:
            for warning in section_warnings:
                lines.append(f"{section_name}:{warning}")
        return lines

    @staticmethod
    def _humanize_warning_token(warning: object) -> str:
        token = str(warning)
        if not token:
            return token

        section = ""
        raw_code = token
        english_sections = {
            "market_regime": "市場情勢",
            "market_breadth": "市場廣度",
            "sector_rotation": "產業輪動",
            "relative_strength_liquidity": "強弱與流動性",
            "watchlist_triggers": "Watchlist",
            "portfolio_alerts": "持倉警示",
            "risk_prompts": "風險提示",
        }
        for raw_section, display_section in english_sections.items():
            prefix = f"{raw_section}:"
            if token.startswith(prefix):
                section = display_section
                raw_code = token[len(prefix):]
                break
        known_sections = (
            "市場情勢",
            "市場廣度",
            "產業輪動",
            "強弱與流動性",
            "Watchlist",
            "持倉警示",
            "風險提示",
        )
        legacy_risk_prefix = "Why Not / 風險提示:"
        if token.startswith(legacy_risk_prefix):
            section = "風險提示"
            raw_code = token[len(legacy_risk_prefix):]
        if not section:
            for section_name in known_sections:
                prefix = f"{section_name}:"
                if token.startswith(prefix):
                    section = section_name
                    raw_code = token[len(prefix):]
                    break

        def with_section(message: str) -> str:
            if section and not message.startswith(section):
                return f"{section}：{message}"
            return message

        parts = raw_code.split(":")
        code = parts[0]
        value = parts[1] if len(parts) > 1 else ""
        extra = parts[2:] if len(parts) > 2 else []
        source_label = DecisionDeskView._display_source_label(value)

        if code == "relative_strength_liquidity_skipped_symbols" and value:
            return with_section(f"強弱與流動性：因流動性或資料條件不足跳過 {value} 檔股票")
        if code == "relative_strength_liquidity_missing":
            return with_section("強弱與流動性資料缺漏")
        if code == "relative_strength_liquidity_insufficient_history":
            return with_section("強弱與流動性歷史資料不足，無法完成排序")
        if code == "relative_strength_liquidity_missing_required_columns":
            return with_section("強弱與流動性缺少必要欄位")
        if code == "watchlist_trigger_data_insufficient" and value:
            return with_section(f"Watchlist 提示：{value} 資料不足，暫無法判斷觸發狀態")
        if code == "watchlist_stale":
            return with_section("Watchlist 資料可能不是最新狀態")
        if code == "sector_missing":
            return with_section("產業輪動資料缺漏")
        if raw_code == "market_regime_effective_date_unknown":
            return with_section("有效資料日未知，無法確認資料日期")
        if raw_code == "market_regime_detector_degraded":
            return with_section("偵測器回報錯誤，結果品質降級")
        if code == "market_regime_as_of_fallback" and len(parts) == 2 and value:
            return with_section(f"採用備援有效資料日：{value}")
        if code in {"market_regime_fetch_error", "market_breadth_fetch_error"}:
            reason = raw_code.partition(":")[2] or "未知原因"
            section_name = "市場情勢" if code.startswith("market_regime") else "市場廣度"
            return with_section(f"{section_name}資料取得失敗：{reason}")
        if code == "sector_rotation_fetch_error":
            reason = raw_code.partition(":")[2] or "未知原因"
            return with_section(f"產業輪動資料取得失敗：{reason}")
        if code in {
            "market_regime_date_unavailable_or_future",
            "market_breadth_date_unavailable_or_future",
            "sector_rotation_date_unavailable_or_future",
            "relative_strength_liquidity_date_unavailable_or_future",
            "watchlist_triggers_date_unavailable_or_future",
            "portfolio_alerts_date_unavailable_or_future",
        }:
            name = DecisionDeskView._display_source_label(
                code[: -len("_date_unavailable_or_future")]
            )
            return with_section(f"{name}的資料日不可用或晚於判斷日")
        if code == "risk_prompt_source_quality" and len(parts) >= 3:
            quality = DecisionDeskView._display_quality_value(extra[0])
            return with_section(f"風險提示來源「{source_label}」目前為{quality}資料")
        if code == "watchlist_trigger_risk_alert" and value:
            return with_section(f"Watchlist 觸發風險提示：{value}")
        if code == "portfolio_alert_top_source" and len(parts) >= 3:
            count = extra[0]
            return with_section(f"持倉警示主要來源為「{source_label}」，共 {count} 筆")
        if code == "portfolio_alerts_chip_estimated" and value:
            return with_section(f"{value} 籌碼張數使用估算資料")
        if code == "portfolio_alerts_chip_unavailable_events" and len(parts) >= 3:
            count = extra[0]
            return with_section(f"{value} 有 {count} 筆籌碼事件缺少可用張數")
        if code == "portfolio_alerts_chip_data_missing" and value:
            return with_section(f"{value} 籌碼資料缺漏")
        if code == "portfolio_alerts_chip_summary_invalid" and value:
            return with_section(f"{value} 籌碼摘要無法判讀")
        if code == "portfolio_alerts_no_active_position":
            return with_section("目前沒有可檢查的啟用持倉")
        if code == "portfolio_alerts_condition_monitor_error" and len(parts) >= 3:
            return with_section(f"{value} 持倉條件檢查失敗：{':'.join(extra)}")
        if code == "portfolio_alerts_portfolio_service_error" and value:
            return with_section(f"持倉資料服務發生錯誤：{value}")
        if code.endswith("_missing"):
            name = DecisionDeskView._display_source_label(code[:-8])
            return with_section(f"{name}資料缺漏")
        if code.endswith("_provider_error"):
            name = DecisionDeskView._display_source_label(code[:-15])
            return with_section(f"{name}資料提供者發生錯誤")
        if code.endswith("_as_of_fallback"):
            name = DecisionDeskView._display_source_label(code[:-15])
            return with_section(f"{name}使用備援決策日")

        return with_section(raw_code) if section else token

    @staticmethod
    def _display_source_label(source: object) -> str:
        text = str(source or "")
        labels = {
            "relative_strength_liquidity": "強弱與流動性",
            "relative_strength_liquidity_service": "強弱與流動性",
            "portfolio_alerts": "持倉警示",
            "portfolio_alert": "持倉警示",
            "watchlist_triggers": "觀察清單觸發",
            "watchlist": "觀察清單",
            "market_breadth": "市場廣度",
            "sector_rotation": "產業輪動",
            "market_regime": "市場情勢",
            "risk_prompts": "風險提示",
            "manual": "手動來源",
            "recommendation_result": "推薦結果",
            "fundamental": "基本面診斷",
        }
        if text.startswith("recommendation_result:"):
            return "推薦結果 " + text.split(":", 1)[1]
        return labels.get(text, text)

    @staticmethod
    def _display_quality_value(value: object) -> str:
        text = str(value or "").lower()
        labels = {
            "observed": "觀察到",
            "estimated": "估算",
            "degraded": "降級",
            "missing": "缺漏",
            "unavailable": "不可用",
        }
        return labels.get(text, str(value or "未知"))

    @staticmethod
    def _display_condition_label(value: object) -> str:
        text = str(value or "").lower()
        labels = {
            "valid": "正常",
            "warning": "警示",
            "invalid": "失效",
            "unknown": "未知",
        }
        return labels.get(text, str(value or "未知"))

    @staticmethod
    def _display_chip_label(value: object) -> str:
        text = str(value or "").lower()
        labels = {
            "bullish": "偏多",
            "bearish": "偏空",
            "neutral": "中性",
            "risk": "風險",
            "extreme": "極端風險",
            "unknown": "未知",
        }
        return labels.get(text, str(value or "未知"))


class _EmptySection:
    """Fallback section with minimal required fields for degraded rendering."""

    def __init__(self, quality: DecisionDeskQuality, warnings: tuple[str, ...] = ()):
        self.quality = quality
        self.warnings = warnings
        self.regime_label = None
        self.regime_score = None
        self.regime_confidence = None
        self.breadth_ratio_bp = None
        self.advancing = None
        self.declining = None
        self.unchanged = None
        self.leading_sector = None
        self.trailing_sector = None
        self.rotation_intensity_bp = None
        self.trigger_count = None
        self.triggered_codes: tuple[str, ...] = ()
        self.top_signal = None
        self.top_strength_codes: tuple[str, ...] = ()
        self.weak_strength_codes: tuple[str, ...] = ()
        self.low_liquidity_codes: tuple[str, ...] = ()
        self.alert_count = None
        self.alert_codes: tuple[str, ...] = ()
        self.alert_level = None
        self.prompts: tuple[object, ...] = ()
        self.attributions: tuple[object, ...] = ()
