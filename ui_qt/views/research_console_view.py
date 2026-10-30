"""Workbench Evidence 子頁的唯讀 Research Console。"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from pathlib import Path
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QProgressBar,
    QSizePolicy,
    QToolButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from typing import Any

from app_module.research_console_dtos import ResearchConsoleDTO
from app_module.research_console_source_service import (
    FORMAL_MONTHLY_REVENUE_QUALITY_DETAIL_SCHEMA,
    ResearchConsoleSourceService,
)
from app_module.recommendation_learning_evidence_projection_service import (
    RecommendationLearningEvidenceProjection,
    RecommendationLearningEvidenceProjectionService,
)
from app_module.p0_source_control_center import P0SourceControlCenterDTO
from ui_qt.theme import MIDNIGHT_ANALYST
from ui_qt.status_vocabulary import status_detail, status_label
from ui_qt.widgets.layout_helpers import ensure_visible_rows, set_scroll_content_constraints
from ui_qt.widgets.theme_widgets import SectionPanel
from ui_qt.views.update.update_formatters import (
    format_p0_license_capture_status,
    format_p0_owner_decision_details,
)
from ui_qt.workers.task_worker import TaskWorker
_STATUS_COLORS = {
    "observed": MIDNIGHT_ANALYST.status_info,
    "research_baseline": MIDNIGHT_ANALYST.status_info,
    "development_challenger": MIDNIGHT_ANALYST.status_info,
    "development_only": MIDNIGHT_ANALYST.status_info,
    "candidate": "#a78bfa",
    "provisional": "#a78bfa",
    "fixture": "#94a3b8",
    "replay": "#94a3b8",
    "degraded": MIDNIGHT_ANALYST.status_warning,
    "research_only_degraded": MIDNIGHT_ANALYST.status_warning,
    "missing": MIDNIGHT_ANALYST.status_error,
    "unknown": MIDNIGHT_ANALYST.text_muted,
    "contract_only": "#a78bfa",
    "blocked_provenance": MIDNIGHT_ANALYST.status_error,
    "blocked": MIDNIGHT_ANALYST.status_error,
    "deferred": MIDNIGHT_ANALYST.status_warning,
    "disabled": MIDNIGHT_ANALYST.text_muted,
    "limited": MIDNIGHT_ANALYST.status_warning,
    "accepted": MIDNIGHT_ANALYST.status_success,
    "completed": MIDNIGHT_ANALYST.status_success,
    "not_supplied": "#94a3b8",
    "not_observed": "#94a3b8",
    "verified": MIDNIGHT_ANALYST.status_info,
    "pending": MIDNIGHT_ANALYST.status_warning,
    "not_applicable": "#94a3b8",
    "future_blocked": MIDNIGHT_ANALYST.status_error,
    "stale": MIDNIGHT_ANALYST.status_warning,
    "recorded": MIDNIGHT_ANALYST.status_info,
    "research_shadow": "#a78bfa",
    "research_only_estimated_cost": "#a78bfa",
}

_STATUS_LABELS = {
    "observed": "已觀測",
    "research_baseline": "研究基準",
    "development_challenger": "開發挑戰者",
    "development_only": "僅開發",
    "candidate": "候選",
    "provisional": "暫定",
    "fixture": "測試資料",
    "replay": "回放",
    "degraded": status_label("degraded", dimension="data"),
    "research_only_degraded": status_label("research_only_degraded", dimension="data"),
    "missing": status_label("missing", dimension="data"),
    "unknown": "未知",
    "contract_only": "僅契約",
    "blocked_provenance": "來源追溯受阻",
    "blocked": "受阻",
    "deferred": "延後",
    "disabled": "停用",
    "limited": "受限",
    "accepted": "已接受",
    "not_supplied": "未提供",
    "not_observed": "未觀測",
    "verified": "已驗證",
    "pending": status_label("pending", dimension="research"),
    "not_applicable": "不適用",
    "future_blocked": "未來日期已阻擋",
    "stale": "過期",
    "recorded": "已記錄",
    "research_only_estimated_cost": "研究限定／估計成本",
    "candidate_file_parsed": "候選檔可解析",
    "candidate_empty_response": "候選回應無資料列",
    "candidate_file_missing": "候選檔缺失",
    "candidate_file_invalid": "候選檔驗證失敗",
    "research_shadow": "研究影子",
    "waiting_for_formal_inputs": "等待正式輸入",
    "formal_input_missing": "缺正式輸入",
    "formal_inputs_missing": "缺正式輸入",
    "not_ready": "尚未就緒",
    "unavailable": "不可用",
    "failed": status_label("failed", dimension="load"),
    "read_only": "唯讀",
    "source_acceptance_pending": "等待來源接受",
}

_BLOCKER_LABELS = {
    "projection_stale": "研究投影已過期",
    "projection_missing": "缺少研究投影",
    "projection_read_failed": "研究投影讀取失敗",
    "projection_schema_invalid": "研究投影格式無效",
    "projection_boundary_violation": "研究投影安全邊界違反",
    "projection_generated_at_missing": "缺少投影產生時間",
    "projection_generated_at_invalid": "投影產生時間無效",
    "formal_oos_input_missing": "缺少正式 OOS 輸入",
    "pit_sector_evidence_missing": "缺少 PIT 產業證據",
    "causal_non_cash_features_missing": "缺少因果非現金特徵",
    "rule_champion_artifact_missing": "缺少 Rule champion artifact",
}


def _inspect_research_console_bundle(
    source_service: ResearchConsoleSourceService,
    learning_service: RecommendationLearningEvidenceProjectionService | None,
    decision_date: str | None,
    *,
    cancel_callback: Callable[[], bool] | None = None,
) -> tuple[
    ResearchConsoleDTO,
    RecommendationLearningEvidenceProjection | None,
    str | None,
]:
    """在 worker thread 取得兩個唯讀 projection，保留同一日期快照。"""

    console = source_service.inspect(cancel_callback=cancel_callback)
    if cancel_callback is not None and cancel_callback():
        return console, None, None
    if learning_service is None:
        return console, None, None
    try:
        projection = learning_service.inspect(
            requested_date=decision_date,
            cancel_callback=cancel_callback,
        )
    except (OSError, TypeError, ValueError, KeyError) as exc:
        return console, None, f"{type(exc).__name__}: {exc}"
    return console, projection, None


class ResearchConsoleView(QWidget):
    """只複製 ResearchConsoleDTO；不計算或寫入 domain state。"""

    def __init__(
        self,
        *,
        source_service: ResearchConsoleSourceService | None = None,
        console: ResearchConsoleDTO | None = None,
        learning_projection_service: RecommendationLearningEvidenceProjectionService | None = None,
        legacy_learning_projection_service: RecommendationLearningEvidenceProjectionService | None = None,
        decision_date: str | None = None,
        auto_refresh: bool = True,
        async_refresh: bool = False,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.source_service = source_service or ResearchConsoleSourceService()
        self.learning_projection_service = learning_projection_service
        self.legacy_learning_projection_service = legacy_learning_projection_service
        self.decision_date = decision_date
        self._async_refresh = bool(async_refresh)
        self._learning_projection: RecommendationLearningEvidenceProjection | None = None
        self._console: ResearchConsoleDTO | None = None
        self._console_loaded = console is not None
        self._load_requested = False
        self._shutdown_requested = False
        self._refresh_worker: TaskWorker | None = None
        self._refresh_generation = 0
        self._refresh_pending = False
        self._monthly_quality_detail_worker: TaskWorker | None = None
        self._monthly_quality_detail_generation = 0
        self._monthly_quality_detail_period: str | None = None
        self._monthly_quality_detail_offset = 0
        self._monthly_quality_detail_total: int | None = None
        self._setup_ui()
        if console is not None:
            self.render_console(console)
            if self._async_refresh and self._selected_learning_service() is not None:
                self._refresh_learning_projection()
        elif auto_refresh and self._async_refresh:
            self.render_console(self.source_service.missing_projection())
            QTimer.singleShot(0, self.ensure_loaded)
        elif auto_refresh:
            self.refresh_console()
        else:
            # auto_refresh=False 代表建構時不讀取來源；placeholder 不觸碰設定路徑。
            self.render_console(self.source_service.missing_projection())

    def _setup_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(8)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        title = QLabel("研究控制台（Research Console）／開發證據")
        title.setStyleSheet(
            f"color: {MIDNIGHT_ANALYST.text_primary}; font-size: 18px; font-weight: 700;"
        )
        subtitle = QLabel(
            "唯讀呈現已清理的 frozen projection；開發、候選與回放資料不等於正式證據。"
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(f"color: {MIDNIGHT_ANALYST.text_secondary};")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        self.refresh_action_row = QWidget(content)
        refresh_row_layout = QHBoxLayout(self.refresh_action_row)
        refresh_row_layout.setContentsMargins(0, 0, 0, 0)
        refresh_row_layout.setSpacing(8)
        self.refresh_status_label = QLabel("尚未載入；切換到此分頁時才會讀取唯讀投影。")
        self.refresh_status_label.setWordWrap(True)
        self.refresh_status_label.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        self.refresh_status_label.setStyleSheet(
            f"color: {MIDNIGHT_ANALYST.text_secondary};"
        )
        self.refresh_button = QPushButton("重新載入唯讀 projection")
        self.refresh_button.setProperty("variant", "secondary")
        self.refresh_button.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed,
        )
        self.refresh_button.setAccessibleName("重新載入 Research Console 唯讀 projection")
        self.refresh_button.setToolTip("只重新讀取既有唯讀投影；不執行資料更新或保存。")
        self.refresh_button.clicked.connect(self.refresh_console)
        refresh_row_layout.addWidget(self.refresh_status_label, 1)
        refresh_row_layout.addWidget(self.refresh_button)
        layout.addWidget(self.refresh_action_row)

        self.conclusion_banner = QLabel()
        self.conclusion_banner.setObjectName("ResearchConsoleConclusion")
        self.conclusion_banner.setAccessibleName("Research Console 中文結論")
        self.conclusion_banner.setWordWrap(True)
        self.conclusion_banner.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.conclusion_banner.setStyleSheet(
            f"background: {MIDNIGHT_ANALYST.surface_2}; color: {MIDNIGHT_ANALYST.text_primary}; "
            f"border: 1px solid {MIDNIGHT_ANALYST.border}; border-radius: 6px; padding: 10px;"
        )
        layout.addWidget(self.conclusion_banner)

        # 技術識別碼與原始狀態預設收合，讓一般使用者先看到可採取的結論。
        self.diagnostics_toggle = QToolButton()
        self.diagnostics_toggle.setText("顯示技術診斷")
        self.diagnostics_toggle.setAccessibleName("展開或收合 Research Console 技術診斷")
        self.diagnostics_toggle.setCheckable(True)
        self.diagnostics_toggle.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.diagnostics_toggle.toggled.connect(self._toggle_diagnostics)
        layout.addWidget(self.diagnostics_toggle)
        self.diagnostics_panel = QLabel()
        self.diagnostics_panel.setObjectName("ResearchConsoleDiagnostics")
        self.diagnostics_panel.setAccessibleName("Research Console 技術診斷內容")
        self.diagnostics_panel.setWordWrap(True)
        self.diagnostics_panel.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.diagnostics_panel.setStyleSheet(
            f"background: {MIDNIGHT_ANALYST.surface_1}; color: {MIDNIGHT_ANALYST.text_secondary}; "
            f"border: 1px solid {MIDNIGHT_ANALYST.border}; border-radius: 6px; padding: 8px;"
        )
        self.diagnostics_panel.setVisible(False)
        layout.addWidget(self.diagnostics_panel)

        boundary_panel = SectionPanel("1. Safety Boundary")
        boundary_grid = QGridLayout()
        boundary_grid.setSpacing(8)
        self.boundary_labels: dict[str, QLabel] = {}
        for index, (key, label) in enumerate(
            (
                ("formal_oos", "正式 OOS"),
                ("alpha", "正式混合權重"),
                ("ml", "正式 ML"),
                ("formal_path", "正式推薦／投組"),
                ("actions", "升級／重訓／排程／交易"),
            )
        ):
            card = QLabel()
            card.setWordWrap(True)
            card.setTextInteractionFlags(Qt.TextSelectableByMouse)
            card.setStyleSheet(
                f"background: {MIDNIGHT_ANALYST.surface_2}; color: {MIDNIGHT_ANALYST.text_primary}; "
                f"border: 1px solid {MIDNIGHT_ANALYST.border}; border-radius: 6px; padding: 8px;"
            )
            boundary_grid.addWidget(QLabel(label), index // 2 * 2, index % 2)
            boundary_grid.addWidget(card, index // 2 * 2 + 1, index % 2)
            self.boundary_labels[key] = card
        boundary_panel.layout.addLayout(boundary_grid)
        layout.addWidget(boundary_panel)

        learning_panel = SectionPanel("每日學習／機率校準（唯讀）")
        learning_header = QGridLayout()
        learning_header.setSpacing(8)
        learning_header.addWidget(QLabel("研究成本情境"), 0, 0)
        self.learning_lane_selector = QComboBox()
        self.learning_lane_selector.addItem("臺銀公開成本研究（預設）", "banktaiwan_estimated_research")
        self.learning_lane_selector.addItem("Legacy 固定 50bp（獨立 lane）", "legacy_fixed_bp")
        self.learning_lane_selector.currentIndexChanged.connect(self._on_learning_lane_changed)
        learning_header.addWidget(self.learning_lane_selector, 0, 1)
        self.learning_summary_label = QLabel()
        self.learning_summary_label.setObjectName("ResearchLearningSummary")
        self.learning_summary_label.setWordWrap(True)
        self.learning_summary_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.learning_summary_label.setStyleSheet(
            f"background: {MIDNIGHT_ANALYST.surface_2}; color: {MIDNIGHT_ANALYST.text_primary}; "
            f"border: 1px solid {MIDNIGHT_ANALYST.border}; border-radius: 6px; padding: 10px;"
        )
        learning_header.addWidget(self.learning_summary_label, 1, 0, 1, 2)
        learning_panel.layout.addLayout(learning_header)
        self.learning_table = _table(
            (
                "驗證範圍",
                "預測機率區間",
                "實際事件發生比例",
                "樣本數",
                "決策日數",
                "期間",
                "狀態",
            )
        )
        learning_panel.layout.addWidget(self.learning_table)
        self.learning_detail_toggle = QToolButton()
        self.learning_detail_toggle.setText("顯示驗證詳情")
        self.learning_detail_toggle.setAccessibleName("展開或收合每日學習驗證詳情")
        self.learning_detail_toggle.setCheckable(True)
        self.learning_detail_toggle.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.learning_detail_toggle.toggled.connect(self._toggle_learning_details)
        learning_panel.layout.addWidget(self.learning_detail_toggle)
        self.learning_detail_label = QLabel()
        self.learning_detail_label.setObjectName("ResearchLearningDetails")
        self.learning_detail_label.setWordWrap(True)
        self.learning_detail_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.learning_detail_label.setStyleSheet(
            f"background: {MIDNIGHT_ANALYST.surface_1}; color: {MIDNIGHT_ANALYST.text_secondary}; "
            f"border: 1px solid {MIDNIGHT_ANALYST.border}; border-radius: 6px; padding: 8px;"
        )
        self.learning_detail_label.setVisible(False)
        learning_panel.layout.addWidget(self.learning_detail_label)
        layout.addWidget(learning_panel)

        pipeline_panel = SectionPanel("2. 開發流程（Development Pipeline）")
        self.pipeline_state_label = QLabel()
        self.pipeline_state_label.setWordWrap(True)
        self.pipeline_state_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.pipeline_table = _table(
            ("元件", "Identity", "狀態", "Cutoff / Maturity", "Rows / Eligible / Features", "Artifact / Blockers")
        )
        pipeline_panel.layout.addWidget(self.pipeline_state_label)
        pipeline_panel.layout.addWidget(self.pipeline_table)
        layout.addWidget(pipeline_panel)

        gates_panel = SectionPanel("3. 證據／來源閘門（Evidence / Source Gates）")
        self.gate_table = _table(("Gate", "狀態", "說明", "Artifact"))
        self.source_table = _table(("來源", "Lane", "狀態", "Allowed use", "Rows", "缺口 / Revision"))
        self.artifact_table = _table(("Artifact", "Identity", "狀態", "Citation"))
        self.broker_lane_label = QLabel("Broker Dataset（獨立 lane）")
        self.broker_lane_label.setStyleSheet("color: #a78bfa; font-weight: 700;")
        gates_panel.layout.addWidget(self.gate_table)
        gates_panel.layout.addWidget(self.broker_lane_label)
        gates_panel.layout.addWidget(self.source_table)
        control_panel = SectionPanel("P0 Data Source Control Center")
        self.control_center_summary_label = QLabel()
        self.control_center_summary_label.setWordWrap(True)
        self.control_center_summary_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.control_center_summary_label.setStyleSheet(f"color: {MIDNIGHT_ANALYST.text_secondary};")
        self.control_center_table = _table(
            (
                "來源",
                "Family",
                "治理狀態",
                "Machine / Audit",
                "Actual route / Fallback",
                "PIT / 解析通過率",
                "License",
                "Decision / Eligibility",
                "Blockers",
            )
        )
        self.control_center_detail_label = QLabel(
            "選取來源查看 Owner 決議、資料／授權／PIT 缺口及下一步。"
        )
        self.control_center_detail_label.setWordWrap(True)
        self.control_center_detail_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.control_center_table.itemSelectionChanged.connect(
            self._render_selected_control_center_details
        )
        control_panel.layout.addWidget(self.control_center_summary_label)
        control_panel.layout.addWidget(self.control_center_table)
        control_panel.layout.addWidget(self.control_center_detail_label)
        gates_panel.layout.addWidget(control_panel)
        quarterly_panel = SectionPanel("季度財報 CSV 欄位缺漏（研究候選）")
        self.quarterly_candidate_root_label = QLabel()
        self.quarterly_candidate_root_label.setWordWrap(True)
        self.quarterly_candidate_root_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        quarterly_controls = QHBoxLayout()
        self.choose_quarterly_candidate_root_button = QPushButton(
            "選擇 CSV 候選目錄…"
        )
        self.choose_quarterly_candidate_root_button.setToolTip(
            "只讀取已封存的候選 manifest 與 CSV；不連網、不匯入或修改檔案，也不接受來源。"
        )
        self.choose_quarterly_candidate_root_button.clicked.connect(
            self._choose_quarterly_candidate_root
        )
        self.reset_quarterly_candidate_root_button = QPushButton("還原啟動設定")
        self.reset_quarterly_candidate_root_button.clicked.connect(
            self._reset_quarterly_candidate_root
        )
        has_candidate_selector = callable(
            getattr(self.source_service, "set_p0_quarterly_candidate_root", None)
        )
        self.choose_quarterly_candidate_root_button.setEnabled(has_candidate_selector)
        self.reset_quarterly_candidate_root_button.setEnabled(has_candidate_selector)
        quarterly_controls.addWidget(self.quarterly_candidate_root_label, stretch=1)
        quarterly_controls.addWidget(self.choose_quarterly_candidate_root_button)
        quarterly_controls.addWidget(self.reset_quarterly_candidate_root_button)
        directory_controls = QHBoxLayout()
        self.issuer_directory_candidate_root_label = QLabel()
        self.issuer_directory_candidate_root_label.setWordWrap(True)
        self.issuer_directory_candidate_root_label.setTextInteractionFlags(
            Qt.TextSelectableByMouse
        )
        self.choose_issuer_directory_candidate_root_button = QPushButton(
            "選擇公司名錄候選目錄…"
        )
        self.choose_issuer_directory_candidate_root_button.setToolTip(
            "只讀取已封存的 TWSE／TPEx 名錄 manifest 與 CSV；不連網、不匯入、不改檔或授予資格。"
        )
        self.choose_issuer_directory_candidate_root_button.clicked.connect(
            self._choose_issuer_directory_candidate_root
        )
        self.reset_issuer_directory_candidate_root_button = QPushButton("還原啟動設定")
        self.reset_issuer_directory_candidate_root_button.clicked.connect(
            self._reset_issuer_directory_candidate_root
        )
        has_directory_selector = callable(
            getattr(self.source_service, "set_p0_issuer_directory_candidate_root", None)
        )
        self.choose_issuer_directory_candidate_root_button.setEnabled(
            has_directory_selector
        )
        self.reset_issuer_directory_candidate_root_button.setEnabled(
            has_directory_selector
        )
        directory_controls.addWidget(self.issuer_directory_candidate_root_label, stretch=1)
        directory_controls.addWidget(self.choose_issuer_directory_candidate_root_button)
        directory_controls.addWidget(self.reset_issuer_directory_candidate_root_button)
        self.quarterly_candidate_summary_label = QLabel(
            "未選擇候選目錄；來源資格維持 none。"
        )
        self.quarterly_candidate_summary_label.setWordWrap(True)
        self.quarterly_resource_table = _table(
            ("市場", "報表", "產業", "Dataset／Artifact", "候選檔狀態", "列數", "逐檔唯一公司", "空白／非空（含 placeholder）／其中 placeholder", "SHA-256")
        )
        self.quarterly_resource_table.itemSelectionChanged.connect(
            self._render_quarterly_candidate_fields
        )
        self.quarterly_resource_table.itemSelectionChanged.connect(
            self._render_quarterly_candidate_next_step
        )
        self.quarterly_resource_table.itemSelectionChanged.connect(
            self._render_quarterly_candidate_row_profiles
        )
        self.quarterly_resource_table.itemSelectionChanged.connect(
            self._render_quarterly_announcement_crosswalk_resource
        )
        self.quarterly_field_table = _table(
            ("原始財務欄位", "空白", "非空", "CSV 空白率", "placeholder")
        )
        self.quarterly_row_profile_filter = QLineEdit()
        self.quarterly_row_profile_filter.setPlaceholderText(
            "篩選公司代碼、名稱或財報期別…"
        )
        self.quarterly_row_profile_filter.setClearButtonEnabled(True)
        self.quarterly_row_profile_filter.textChanged.connect(
            self._filter_quarterly_row_profiles
        )
        self.quarterly_row_profile_summary_label = QLabel(
            "選取一項候選資源查看公司／期別的儲存格計數。"
        )
        self.quarterly_row_profile_summary_label.setWordWrap(True)
        self.quarterly_row_profile_table = _table(
            (
                "公司代碼",
                "公司名稱",
                "財報期別",
                "出表日期（原值）",
                "來源列數",
                "空白儲存格",
                "非空（含 placeholder）",
                "placeholder 數",
                "空白欄位數",
            )
        )
        self.quarterly_row_profile_table.itemSelectionChanged.connect(
            self._render_selected_quarterly_row_profile
        )
        self.quarterly_row_profile_detail_label = QLabel(
            "空白只表示 CSV 儲存格為空；不推定缺報、不適用或來源完整性。"
        )
        self.quarterly_row_profile_detail_label.setWordWrap(True)
        self.quarterly_row_profile_detail_label.setTextInteractionFlags(
            Qt.TextSelectableByMouse
        )
        self._quarterly_candidate_resources: list[dict[str, Any]] = []
        self._quarterly_coverage_rows: list[dict[str, Any]] = []
        self._update_quarterly_candidate_root_label()
        self._update_issuer_directory_candidate_root_label()
        quarterly_panel.layout.addLayout(quarterly_controls)
        quarterly_panel.layout.addLayout(directory_controls)
        quarterly_panel.layout.addWidget(self.quarterly_candidate_summary_label)
        quarterly_panel.layout.addWidget(self.quarterly_resource_table)
        self.quarterly_resource_next_step_label = QLabel(
            "選取資源查看目前候選狀態與下一個核查步驟。"
        )
        self.quarterly_resource_next_step_label.setWordWrap(True)
        self.quarterly_resource_next_step_label.setTextFormat(Qt.PlainText)
        self.quarterly_resource_next_step_label.setTextInteractionFlags(
            Qt.TextSelectableByMouse
        )
        quarterly_panel.layout.addWidget(self.quarterly_resource_next_step_label)
        quarterly_panel.layout.addWidget(self.quarterly_field_table)
        quarterly_panel.layout.addWidget(QLabel("逐公司／期別空白分布"))
        quarterly_panel.layout.addWidget(self.quarterly_row_profile_filter)
        quarterly_panel.layout.addWidget(self.quarterly_row_profile_summary_label)
        quarterly_panel.layout.addWidget(self.quarterly_row_profile_table)
        quarterly_panel.layout.addWidget(self.quarterly_row_profile_detail_label)
        quarterly_panel.layout.addWidget(QLabel("目前候選與名錄的逐代號差異（僅近時點檔案對照）"))
        self.quarterly_coverage_summary_label = QLabel(
            "選取季度候選與公司名錄候選後，才會顯示逐代號對照。"
        )
        self.quarterly_coverage_summary_label.setWordWrap(True)
        quarterly_panel.layout.addWidget(self.quarterly_coverage_summary_label)
        self.quarterly_coverage_filter = QLineEdit()
        self.quarterly_coverage_filter.setPlaceholderText("篩選代號、公司名稱或產業代碼…")
        self.quarterly_coverage_filter.setClearButtonEnabled(True)
        self.quarterly_coverage_filter.textChanged.connect(
            self._filter_quarterly_coverage_rows
        )
        coverage_filters = QHBoxLayout()
        self.quarterly_coverage_filter_mode = QComboBox()
        self.quarterly_coverage_filter_mode.addItems(("只看差異", "顯示全部代號"))
        self.quarterly_coverage_filter_mode.currentIndexChanged.connect(
            lambda _index: self._filter_quarterly_coverage_rows(
                self.quarterly_coverage_filter.text()
            )
        )
        coverage_filters.addWidget(self.quarterly_coverage_filter, stretch=1)
        coverage_filters.addWidget(self.quarterly_coverage_filter_mode)
        quarterly_panel.layout.addLayout(coverage_filters)
        self.quarterly_coverage_table = _table(
            ("市場", "公司代號", "名錄公司名稱", "目錄產業碼", "檔案對照")
        )
        quarterly_panel.layout.addWidget(self.quarterly_coverage_table)
        self.quarterly_coverage_detail_label = QLabel(
            "名錄有而目前季報候選未見，不代表未申報或漏抓。"
        )
        self.quarterly_coverage_detail_label.setWordWrap(True)
        self.quarterly_coverage_detail_label.setTextInteractionFlags(
            Qt.TextSelectableByMouse
        )
        quarterly_panel.layout.addWidget(self.quarterly_coverage_detail_label)
        gates_panel.layout.addWidget(quarterly_panel)
        announcement_panel = SectionPanel(
            "季報與 MOPS 公告候選對照（availability-only）"
        )
        self.mops_announcement_candidate_roots_label = QLabel()
        self.mops_announcement_candidate_roots_label.setWordWrap(True)
        self.mops_announcement_candidate_roots_label.setTextInteractionFlags(
            Qt.TextSelectableByMouse
        )
        self._update_mops_announcement_candidate_roots_label()
        announcement_controls = QHBoxLayout()
        self.choose_mops_announcement_candidate_roots_button = QPushButton(
            "選擇 MOPS 公告候選 JSON…"
        )
        self.choose_mops_announcement_candidate_roots_button.setToolTip(
            "可多選已封存的 mops-statement-availability.json；只核對同目錄候選 CSV、來源雜湊與查詢窗口，不連網、不匯入或授予資格。"
        )
        self.choose_mops_announcement_candidate_roots_button.clicked.connect(
            self._choose_mops_announcement_candidate_roots
        )
        self.reset_mops_announcement_candidate_roots_button = QPushButton(
            "還原啟動設定"
        )
        self.reset_mops_announcement_candidate_roots_button.clicked.connect(
            self._reset_mops_announcement_candidate_roots
        )
        has_announcement_selector = callable(
            getattr(self.source_service, "set_p0_mops_announcement_candidate_roots", None)
        )
        self.choose_mops_announcement_candidate_roots_button.setEnabled(
            has_announcement_selector
        )
        self.reset_mops_announcement_candidate_roots_button.setEnabled(
            has_announcement_selector
        )
        announcement_controls.addWidget(
            self.mops_announcement_candidate_roots_label, stretch=1
        )
        announcement_controls.addWidget(
            self.choose_mops_announcement_candidate_roots_button
        )
        announcement_controls.addWidget(
            self.reset_mops_announcement_candidate_roots_button
        )
        self.quarterly_announcement_crosswalk_summary_label = QLabel(
            "需同時選取季報 CSV 與公告候選；目前不推定公告缺漏或資料可得。"
        )
        self.quarterly_announcement_crosswalk_summary_label.setWordWrap(True)
        self.quarterly_formal_impact_state_label = QLabel(
            "正式資料影響：尚未讀取；各計數未知。"
        )
        self.quarterly_formal_impact_state_label.setObjectName(
            "QuarterlyFormalImpactState"
        )
        self.quarterly_formal_impact_state_label.setWordWrap(True)
        self.quarterly_formal_impact_table = _table(
            ("正式資料影響指標", "Reader 回讀值")
        )
        self.quarterly_formal_impact_table.setAccessibleName(
            "季報公告候選對照的正式資料影響摘要"
        )
        self.quarterly_formal_impact_blockers_label = QLabel(
            "正式資料 blockers：未知。"
        )
        self.quarterly_formal_impact_blockers_label.setWordWrap(True)
        self.quarterly_formal_impact_blockers_label.setTextInteractionFlags(
            Qt.TextSelectableByMouse
        )
        self.quarterly_formal_impact_boundary_label = QLabel(
            "同公司／報表／期間只表示 identity overlap，不代表同版本連結；"
            "沒有精確版本連結時不可解除。此彙總唯讀、不回填正式資料；"
            "候選數不推導正式解除筆數。"
        )
        self.quarterly_formal_impact_boundary_label.setWordWrap(True)
        self.quarterly_formal_impact_boundary_label.setTextInteractionFlags(
            Qt.TextSelectableByMouse
        )
        self.quarterly_announcement_crosswalk_table = _table(
            ("市場", "報表", "CSV profile 數", "單一公告候選", "多筆／歧義", "選取窗口未觀測", "查詢窗口不完整", "身份缺漏")
        )
        self.quarterly_announcement_crosswalk_detail_label = QLabel(
            "選取上方季度 CSV 資源，查看該資源的同公司／報表／期別公告候選。"
        )
        self.quarterly_announcement_crosswalk_detail_label.setWordWrap(True)
        self.quarterly_announcement_crosswalk_detail_label.setTextInteractionFlags(
            Qt.TextSelectableByMouse
        )
        self.quarterly_announcement_period_summary_table = _table(
            (
                "財報期別",
                "Profile 列數",
                "單一候選",
                "多筆歧義",
                "窗口內未觀測",
                "查詢窗口不完整",
                "身份缺漏",
            )
        )
        self.quarterly_announcement_period_summary_table.setAccessibleName(
            "所選季報資源依財報期別的公告對照摘要"
        )
        self.quarterly_announcement_crosswalk_resource_table = _table(
            ("公司代碼", "財報期別", "公告對照狀態", "MOPS 公告日時間（台北）", "候選數", "公告 response SHA-256")
        )
        self._quarterly_announcement_crosswalk: dict[str, Any] | None = None
        self._update_mops_announcement_candidate_roots_label()
        announcement_panel.layout.addLayout(announcement_controls)
        announcement_panel.layout.addWidget(
            self.quarterly_announcement_crosswalk_summary_label
        )
        announcement_panel.layout.addWidget(
            QLabel("正式資料影響（僅顯示 reader 回讀值）")
        )
        announcement_panel.layout.addWidget(
            self.quarterly_formal_impact_state_label
        )
        announcement_panel.layout.addWidget(self.quarterly_formal_impact_table)
        announcement_panel.layout.addWidget(
            self.quarterly_formal_impact_blockers_label
        )
        announcement_panel.layout.addWidget(
            self.quarterly_formal_impact_boundary_label
        )
        announcement_panel.layout.addWidget(self.quarterly_announcement_crosswalk_table)
        announcement_note = QLabel(
            "同鍵表示市場、公司、報表種類與期別一致；依 Owner 授權，明確匹配的 MOPS 顯示日期與時間可作公告時間戳。"
            "若有多筆公告，保留版本歧義。此候選對照不會回寫正式財報資料，也不證明 CSV 數值版本、首次可得時間或來源資格。"
            "選取窗口未觀測不等於未申報；本區不授歷史 PIT／Gate credit。"
        )
        announcement_note.setWordWrap(True)
        announcement_panel.layout.addWidget(announcement_note)
        announcement_panel.layout.addWidget(
            self.quarterly_announcement_crosswalk_detail_label
        )
        announcement_panel.layout.addWidget(
            QLabel(
                "以下按財報所屬期別統計所選 CSV 資源的 profile 列；"
                "窗口內未觀測只表示所選公告查詢窗口沒有找到候選，不代表未申報。"
            )
        )
        announcement_panel.layout.addWidget(
            self.quarterly_announcement_period_summary_table
        )
        announcement_panel.layout.addWidget(
            self.quarterly_announcement_crosswalk_resource_table
        )
        gates_panel.layout.addWidget(announcement_panel)
        monthly_quality_panel = SectionPanel(
            "正式月營收公告日品質（按資料期別唯讀彙總）"
        )
        self.formal_monthly_revenue_quality_state_label = QLabel(
            "尚未讀取正式月營收摘要；各月份數字未知。"
        )
        self.formal_monthly_revenue_quality_state_label.setWordWrap(True)
        self.formal_monthly_revenue_quality_table = _table(
            (
                "營收資料月份",
                "正式列數",
                "缺公告日列數",
                "報表日期來源待核實列數",
                "公司代碼數",
                "來源版本數",
            )
        )
        self.formal_monthly_revenue_quality_table.setAccessibleName(
            "正式月營收按月份公告日期品質摘要"
        )
        self.formal_monthly_revenue_quality_table.itemSelectionChanged.connect(
            self._update_monthly_quality_detail_controls
        )
        monthly_quality_panel.layout.addWidget(
            self.formal_monthly_revenue_quality_state_label
        )
        monthly_quality_panel.layout.addWidget(
            self.formal_monthly_revenue_quality_table
        )
        monthly_quality_detail_controls = QHBoxLayout()
        self.formal_monthly_revenue_quality_detail_button = QPushButton(
            "查看選取月份公告日缺漏／報表日期核對"
        )
        self.formal_monthly_revenue_quality_detail_button.clicked.connect(
            self._load_selected_monthly_quality_detail
        )
        self.formal_monthly_revenue_quality_previous_button = QPushButton("上一頁")
        self.formal_monthly_revenue_quality_previous_button.clicked.connect(
            lambda: self._load_monthly_quality_detail_page(
                max(0, self._monthly_quality_detail_offset - 100)
            )
        )
        self.formal_monthly_revenue_quality_next_button = QPushButton("下一頁")
        self.formal_monthly_revenue_quality_next_button.clicked.connect(
            lambda: self._load_monthly_quality_detail_page(
                self._monthly_quality_detail_offset + 100
            )
        )
        self.formal_monthly_revenue_quality_previous_button.setEnabled(False)
        self.formal_monthly_revenue_quality_next_button.setEnabled(False)
        monthly_quality_detail_controls.addWidget(
            self.formal_monthly_revenue_quality_detail_button
        )
        monthly_quality_detail_controls.addWidget(
            self.formal_monthly_revenue_quality_previous_button
        )
        monthly_quality_detail_controls.addWidget(
            self.formal_monthly_revenue_quality_next_button
        )
        monthly_quality_panel.layout.addLayout(monthly_quality_detail_controls)
        self.formal_monthly_revenue_quality_detail_state_label = QLabel(
            "選取有公告日缺漏或報表日期待核實的月份後載入明細；並排顯示正式列日期與精確版本 MOPS mapping 日期。"
        )
        self.formal_monthly_revenue_quality_detail_state_label.setWordWrap(True)
        monthly_quality_panel.layout.addWidget(
            self.formal_monthly_revenue_quality_detail_state_label
        )
        self.formal_monthly_revenue_quality_detail_table = _table(
            ("公司代碼", "來源", "來源版本", "正式列日期", "MOPS 公告日期", "核對狀態")
        )
        self.formal_monthly_revenue_quality_detail_table.setAccessibleName(
            "正式月營收公告日缺漏與報表日期待核實公司、來源版本及 MOPS mapping 明細"
        )
        monthly_quality_panel.layout.addWidget(
            self.formal_monthly_revenue_quality_detail_table
        )
        monthly_quality_note = QLabel(
            "公告日期非空只代表欄位有值；靜態報表來源日期只有與精確 MOPS 公告日期一致才從待核實計數扣除，"
            "不等同公司別公告事件。只計正式月營收列與識別資訊，不讀取營收值，"
            "明選月份後每頁最多 100 列。精確 mapping 依公司、月份與 target source version 對照；"
            "mapping 缺失、無法讀取或含診斷時顯示未知。此對照不回填日期，也不判定 Gate／PIT 資格。"
        )
        monthly_quality_note.setWordWrap(True)
        monthly_quality_panel.layout.addWidget(monthly_quality_note)
        gates_panel.layout.addWidget(monthly_quality_panel)
        gates_panel.layout.addWidget(QLabel("Artifact Inspector"))
        gates_panel.layout.addWidget(self.artifact_table)
        layout.addWidget(gates_panel)
        layout.addStretch()

        set_scroll_content_constraints(content)
        scroll.setWidget(content)
        root_layout.addWidget(scroll)

    def refresh_console(self) -> None:
        if self._shutdown_requested:
            return
        if self._async_refresh:
            self._start_async_refresh()
            return
        self.refresh_button.setEnabled(False)
        self.refresh_status_label.setText("正在讀取唯讀 projection…")
        try:
            self.render_console(self.source_service.inspect())
            self._refresh_learning_projection()
            self._console_loaded = True
            self._load_requested = False
            self.refresh_status_label.setText("唯讀 projection 已載入。")
        finally:
            self.refresh_button.setEnabled(True)

    def ensure_loaded(self) -> None:
        """只在研究證據分頁首次顯示時載入；重複切頁不重讀。"""

        if self._shutdown_requested or self._console_loaded or self._load_requested:
            return
        self._load_requested = True
        self.refresh_console()

    def begin_shutdown(self) -> None:
        if self._shutdown_requested:
            return
        self._shutdown_requested = True
        self._refresh_generation += 1
        self._monthly_quality_detail_generation += 1
        self._refresh_pending = False
        worker = self._refresh_worker
        if worker is not None:
            try:
                if worker.isRunning():
                    worker.cancel(cooperative=True, wait=False)
            except RuntimeError:
                self._refresh_worker = None
        detail_worker = self._monthly_quality_detail_worker
        if detail_worker is not None:
            try:
                if detail_worker.isRunning():
                    detail_worker.cancel(cooperative=True, wait=False)
            except RuntimeError:
                self._monthly_quality_detail_worker = None

    def _start_async_refresh(self) -> None:
        if self._shutdown_requested:
            return
        # 任何新日期／成本 lane 請求都立刻使先前已排隊的結果失效。
        self._refresh_generation += 1
        generation = self._refresh_generation
        # Keep the in-flight state explicit for initial loads and retries as
        # well as refreshes of an already rendered console. A lane/date change
        # during any of these reads must request the latest snapshot.
        self._load_requested = True
        worker = self._refresh_worker
        if worker is not None:
            try:
                if worker.isRunning():
                    self._refresh_pending = True
                    worker.cancel(cooperative=True, wait=False)
                    self.refresh_status_label.setText(
                        "正在取消較早的唯讀讀取，完成後載入最新日期與成本情境。"
                    )
                    return
            except RuntimeError:
                self._refresh_worker = None

        requested_date = self.decision_date
        learning_service = self._selected_learning_service()
        worker = TaskWorker(
            _inspect_research_console_bundle,
            self.source_service,
            learning_service,
            requested_date,
        )
        worker.native_thread_finished.connect(worker.deleteLater)
        worker.finished.connect(
            lambda bundle, current_generation=generation, current_date=requested_date: self._on_async_refresh_finished(
                current_generation, current_date, bundle
            ),
            Qt.ConnectionType.QueuedConnection,
        )
        worker.error.connect(
            lambda error, current_generation=generation, current_date=requested_date: self._on_async_refresh_error(
                current_generation, current_date, error
            ),
            Qt.ConnectionType.QueuedConnection,
        )
        worker.cancelled.connect(
            lambda current_generation=generation: self._on_async_refresh_cancelled(
                current_generation
            ),
            Qt.ConnectionType.QueuedConnection,
        )
        worker.native_thread_finished.connect(
            lambda current_worker=worker: self._on_async_refresh_thread_finished(
                current_worker
            ),
            Qt.ConnectionType.QueuedConnection,
        )
        self._refresh_worker = worker
        self.refresh_button.setEnabled(False)
        self.refresh_status_label.setText(
            "正在背景讀取唯讀資料來源；關閉程式時會合作式取消。"
        )
        worker.start()

    def _on_async_refresh_finished(
        self,
        generation: int,
        requested_date: str | None,
        bundle: object,
    ) -> None:
        if self._shutdown_requested or generation != self._refresh_generation:
            return
        if requested_date != self.decision_date:
            self._refresh_pending = True
            return
        if (
            not isinstance(bundle, tuple)
            or len(bundle) != 3
            or not isinstance(bundle[0], ResearchConsoleDTO)
        ):
            self._on_async_refresh_error(
                generation,
                requested_date,
                "Research Console source 回傳格式無效。",
            )
            return
        console, projection, projection_error = bundle
        self.render_console(console)
        self.render_learning_projection(projection, error=projection_error)
        self._console_loaded = True
        self._load_requested = False
        self.refresh_status_label.setText("唯讀 projection 已載入。")

    def _on_async_refresh_error(
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
        self._load_requested = False
        self.refresh_status_label.setText(
            f"唯讀 projection 讀取失敗：{error_message}；可重新載入。"
        )

    def _on_async_refresh_cancelled(self, generation: int) -> None:
        if generation != self._refresh_generation or self._shutdown_requested:
            return
        if not self._refresh_pending:
            self._load_requested = False
            self.refresh_status_label.setText(
                "唯讀讀取已取消；目前畫面保留最後一次結果。"
            )

    def _on_async_refresh_thread_finished(self, worker: TaskWorker) -> None:
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
            self.refresh_button.setEnabled(True)
        if should_refresh:
            QTimer.singleShot(0, self.refresh_console)

    def set_decision_date(self, decision_date: str | None) -> None:
        """Bind learning freshness to the selected Workbench decision date."""

        if decision_date == self.decision_date:
            return
        self.decision_date = decision_date
        if self._async_refresh:
            if self._console_loaded or self._load_requested:
                self.refresh_console()
        else:
            self._refresh_learning_projection()

    def _on_learning_lane_changed(self, _index: int) -> None:
        self._refresh_learning_projection()

    def _refresh_learning_projection(self) -> None:
        if self._async_refresh:
            # A lane change during the first lazy load must invalidate that
            # in-flight result too; otherwise its older projection can be
            # rendered under the newly selected lane.
            if self._console_loaded or self._load_requested:
                self.refresh_console()
            return
        service = self._selected_learning_service()
        if service is None:
            self.render_learning_projection(None)
            return
        try:
            projection = service.inspect(requested_date=self.decision_date)
        except (OSError, TypeError, ValueError, KeyError) as exc:
            self.render_learning_projection(None, error=f"{type(exc).__name__}: {exc}")
            return
        self.render_learning_projection(projection)

    def _selected_learning_service(self) -> RecommendationLearningEvidenceProjectionService | None:
        lane = self.learning_lane_selector.currentData()
        if lane == "legacy_fixed_bp":
            return self.legacy_learning_projection_service or (
                self.learning_projection_service
                if self.learning_projection_service is not None
                and getattr(self.learning_projection_service, "cost_lane", "") == "legacy_fixed_bp"
                else None
            )
        return self.learning_projection_service

    def render_learning_projection(
        self,
        projection: RecommendationLearningEvidenceProjection | None,
        *,
        error: str | None = None,
    ) -> None:
        self._learning_projection = projection
        if error:
            self.learning_summary_label.setText(f"學習 projection 讀取失敗：{error}")
            self.learning_detail_label.setText("失敗不是零樣本；請檢查隔離 learning root 與 receipt。")
            self.learning_table.setRowCount(0)
            return
        if projection is None:
            self.learning_summary_label.setText(
                "尚未接入 recommendation learning projection；不能由 UI 推定模型可靠度。"
            )
            self.learning_detail_label.setText("")
            self.learning_table.setRowCount(0)
            return
        candidate = projection.candidate_lane
        active = projection.active_lane
        horizon_text = "；".join(
            f"{item.horizon_days}日：{_status_display(item.status)}／已成熟 {item.matured_sample_count} 筆／"
            f"{item.matured_decision_date_count} 個決策日"
            for item in projection.horizons
        ) or "未知"
        horizon_scope = (
            f"{projection.horizon_scope_label or '未知'}／"
            f"模型={projection.horizon_scope_model_version or '未知'}／"
            f"成本情境={projection.horizon_scope_cost_scenario_id or '未知'}"
        )
        lane_label = _learning_lane_label(projection.cost_lane)
        cost_summary = _learning_cost_summary(candidate, active, projection.cost_lane)
        record_summary = _learning_record_summary(projection)
        candidate_maturity = _maturity_summary(candidate)
        active_maturity = _maturity_summary(active)
        verified_summary = _verified_maturity_summary(candidate, active)
        self.learning_summary_label.setText(
            f"研究範圍：{lane_label}｜整體狀態：{_status_display(projection.status)}\n"
            f"目標決策日：{projection.requested_date or '未知'}｜"
            f"學習資料決策日：{projection.learning_decision_date or '未知'}\n"
            f"成本：{cost_summary}\n"
            f"該日預測：{record_summary}\n"
            f"已成熟樣本：候選 {candidate_maturity}；目前路徑 {active_maturity}\n"
            f"已驗證自然樣本：{verified_summary}\n"
            f"判定：{_learning_decision_summary(projection)}\n"
            f"下一步：{_learning_next_step(projection)}"
        )
        rows = []
        for item in projection.reliability_bins:
            target = "上漲機率" if item.target == "upside_probability" else "成本後獲利機率"
            rows.append(
                (
                    target,
                    f"{item.lower_probability_bp / 100:.0f}%–{item.upper_probability_bp / 100:.0f}%",
                    f"{item.matured_actual_up_ratio_bp / 100:.2f}%",
                    item.sample_count,
                    item.decision_date_count,
                    f"{item.period_start or '未知'}..{item.period_end or '未知'}",
                    "研究限定／估計成本" if item.research_only else item.status,
                )
            )
        if not rows:
            rows.append(
                (
                    "尚無已驗證自然樣本",
                    "未知",
                    "未知",
                    0,
                    0,
                    "未知",
                    "pending",
                )
            )
        _set_rows(
            self.learning_table, rows, status_column=6, status_dimension="research"
        )
        self.learning_detail_label.setText(
            f"candidate identity：{candidate.candidate_id or '未知'}\n"
            f"candidate 狀態／原始原因：{candidate.status}／{candidate.reason or '未知'}\n"
            f"candidate model／dataset／training-as-of：{candidate.model_version or '未知'}／"
            f"{candidate.dataset_version or '未知'}／{candidate.training_as_of or '未知'}\n"
            f"active model／狀態／原始原因：{active.model_version or '未知'}／"
            f"{active.status}／{active.reason or '未知'}\n"
            f"horizon scope：{horizon_scope}\n"
            f"horizon 明細：{horizon_text}\n"
            f"成本 basis／scenario／version／hash：{candidate.cost_basis or active.cost_basis or '未知'}／"
            f"{candidate.cost_scenario_id or active.cost_scenario_id or '未知'}／"
            f"{candidate.cost_scenario_version or active.cost_scenario_version or '未知'}／"
            f"{candidate.cost_scenario_hash or active.cost_scenario_hash or '未知'}\n"
            f"capture：{candidate.capture_status}／{candidate.capture_count} 筆 capture／"
            f"{candidate.recorded_row_count} 筆 rows\n"
            f"receipt／evidence：{candidate.receipt_path or active.receipt_path or '未知'}／"
            f"{candidate.receipt_hash or active.receipt_hash or '未知'}／"
            f"{candidate.evidence_id or active.evidence_id or '未知'}\n"
            f"decision reason：{projection.decision_reason or '未知'}\n"
            f"data recorded raw reason：{projection.data_recorded_reason or '未知'}\n"
            f"next gap raw：{projection.next_gap}\n"
            f"adoption raw：{projection.adoption_reason}\n"
            f"Historical evaluation：{projection.historical_evaluation_sample_count} 筆；"
            f"{projection.historical_evaluation_note}\n"
            f"diagnostics：{'；'.join(projection.diagnostics) or '無'}\n"
            f"source trace：{'；'.join(projection.source_trace) or '未知'}"
        )

    def _toggle_learning_details(self, checked: bool) -> None:
        self.learning_detail_label.setVisible(bool(checked))
        self.learning_detail_toggle.setText(
            "收合驗證詳情" if checked else "顯示驗證詳情"
        )

    def _toggle_diagnostics(self, checked: bool) -> None:
        self.diagnostics_panel.setVisible(bool(checked))
        self.diagnostics_toggle.setText(
            "收合技術診斷" if checked else "顯示技術診斷"
        )

    def render_console(self, console: ResearchConsoleDTO) -> None:
        self._console = console
        boundary = console.boundary
        self.boundary_labels["formal_oos"].setText(
            "正式 OOS：停用\n不可用於正式決策"
        )
        self.boundary_labels["alpha"].setText(
            "正式混合權重：0 bp\n停用"
        )
        self.boundary_labels["ml"].setText("正式 ML：未參與\n僅開發／影子研究")
        self.boundary_labels["formal_path"].setText(
            "正式路徑：Rule（規則）\n推薦／投組沿用既有規則"
        )
        self.boundary_labels["actions"].setText(
            "升級：停用｜重訓：停用｜排程：停用｜交易：停用"
        )
        self.conclusion_banner.setText(_build_conclusion(console))
        self.pipeline_state_label.setText(
            f"整體狀態：{_status_display(console.overall_status, dimension='research')}｜"
            f"待處理：{_join_blockers(console.blockers)}"
        )
        self.diagnostics_panel.setText(_build_diagnostics(console))
        _set_rows(
            self.pipeline_table,
            (
                (
                    row.label,
                    row.identity,
                    row.status,
                    _join_optional(row.cutoff, row.feature_interval, row.label_maturity),
                    _counts(row.row_count, row.eligible_count, row.feature_count),
                    _join_optional(row.artifact_path, row.artifact_hash, _join_blockers(row.blockers)),
                )
                for row in console.pipeline
            ),
            status_column=2,
            status_dimension="load",
        )
        _set_rows(
            self.gate_table,
            ((row.gate_id, row.status, row.detail, row.artifact_citation or "Not Available") for row in console.gates),
            status_column=1,
            status_dimension="qualification",
        )
        _set_rows(
            self.source_table,
            (
                (
                    row.label,
                    row.lane.upper(),
                    row.status,
                    row.allowed_use,
                    _optional_number(row.observed_rows),
                    _join_optional(row.degraded_reason, row.revision, row.owner),
                )
                for row in console.sources
            ),
            status_column=2,
            status_dimension="data",
        )
        control_center = console.source_control_center
        if control_center is None:
            self._control_center_rows: list[dict[str, Any]] = []
            self._formal_monthly_revenue_quality = None
            self.control_center_detail_label.setText(
                "沒有可選取的來源治理資料；未知不代表沒有缺口。"
            )
            self.control_center_summary_label.setText(
                    "P0 來源控制中心：未提供 13 項來源治理投影。"
            )
            self.control_center_table.setRowCount(0)
        else:
            self._control_center_rows = [row.to_dict() for row in control_center.rows]
            self._formal_monthly_revenue_quality = control_center.to_dict().get(
                "formal_monthly_revenue_quality"
            )
            self.control_center_detail_label.setText(
                "選取來源查看 Owner 決議、資料／授權／PIT 缺口及下一步。"
            )
            self.control_center_summary_label.setText(
                "狀態：{status}｜P0：{count}｜Research shadow：{shadow}｜"
                "Blocked provenance：{blocked}｜Accepted / Limited：{accepted} / {limited}｜"
                "Downstream eligible：{eligible}\n"
                "唯讀邊界：writes=false、formal_oos=false、scheduler=false、auto_accept=false\n"
                "Global blockers：{blockers}".format(
                        status=_status_display(
                        _control_center_status(control_center),
                        dimension="qualification",
                    ),
                    count=control_center.p0_source_count,
                    shadow=control_center.research_shadow_count,
                    blocked=control_center.blocked_count,
                    accepted=control_center.accepted_count,
                    limited=control_center.limited_count,
                    eligible=control_center.downstream_eligible_count,
                    blockers=_join_blockers(control_center.global_blockers),
                )
            )
            _set_rows(
                self.control_center_table,
                (
                (
                    row.source_id,
                    row.family,
                    row.governance_status,
                    f"{row.machine_status} / {row.audit_status}",
                    _control_route(row),
                    _control_pit_coverage(row),
                    _control_license(row),
                    f"{row.decision_status} / {row.downstream_eligibility}",
                    _join_blockers(row.blockers),
                )
                    for row in control_center.rows
                ),
                status_column=2,
                status_dimension="qualification",
            )
        self._render_quarterly_candidate_audit()
        self._render_quarterly_announcement_crosswalk()
        self._render_formal_monthly_revenue_quality()
        _set_rows(
            self.artifact_table,
            ((row.artifact_type, row.artifact_id, row.status, row.citation) for row in console.artifacts),
            status_column=2,
            status_dimension="research",
        )
        if self.learning_projection_service is not None and not self._async_refresh:
            self._refresh_learning_projection()

    def _update_quarterly_candidate_root_label(self) -> None:
        root = getattr(self.source_service, "p0_quarterly_candidate_root", None)
        self.quarterly_candidate_root_label.setText(
            f"目前候選目錄：{root}" if root is not None else "目前候選目錄：未設定"
        )

    def _update_issuer_directory_candidate_root_label(self) -> None:
        root = getattr(self.source_service, "p0_issuer_directory_candidate_root", None)
        self.issuer_directory_candidate_root_label.setText(
            f"目前名錄候選：{root}" if root is not None else "目前名錄候選：未設定"
        )

    def _update_mops_announcement_candidate_roots_label(self) -> None:
        roots = getattr(
            self.source_service, "p0_mops_announcement_candidate_roots", ()
        )
        self.mops_announcement_candidate_roots_label.setText(
            "目前公告候選：\n" + "\n".join(str(root) for root in roots)
            if roots
            else "目前公告候選：未設定"
        )

    def _choose_mops_announcement_candidate_roots(self) -> None:
        current = getattr(
            self.source_service, "p0_mops_announcement_candidate_roots", ()
        )
        start_directory = str(Path(current[0]).parent) if current else str(Path.home())
        selected, _filter = QFileDialog.getOpenFileNames(
            self,
            "選取一個或多個已封存的 MOPS 公告候選 JSON",
            start_directory,
            "MOPS 公告候選 (mops-statement-availability.json)",
        )
        if not selected:
            return
        setter = getattr(
            self.source_service, "set_p0_mops_announcement_candidate_roots", None
        )
        if not callable(setter):
            return
        roots = tuple(dict.fromkeys(str(Path(path).parent) for path in selected))
        setter(roots)
        self._update_mops_announcement_candidate_roots_label()
        self.refresh_console()

    def _reset_mops_announcement_candidate_roots(self) -> None:
        setter = getattr(
            self.source_service, "set_p0_mops_announcement_candidate_roots", None
        )
        if not callable(setter):
            return
        setter(None)
        self._update_mops_announcement_candidate_roots_label()
        self.refresh_console()

    def _choose_issuer_directory_candidate_root(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self,
            "選擇已封存的 TWSE／TPEx 公司名錄候選目錄",
            str(
                getattr(self.source_service, "p0_issuer_directory_candidate_root", None)
                or Path.home()
            ),
        )
        if not selected:
            return
        setter = getattr(
            self.source_service, "set_p0_issuer_directory_candidate_root", None
        )
        if not callable(setter):
            return
        setter(selected)
        self._update_issuer_directory_candidate_root_label()
        self.refresh_console()

    def _reset_issuer_directory_candidate_root(self) -> None:
        setter = getattr(
            self.source_service, "set_p0_issuer_directory_candidate_root", None
        )
        if not callable(setter):
            return
        setter(None)
        self._update_issuer_directory_candidate_root_label()
        self.refresh_console()

    def _choose_quarterly_candidate_root(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self,
            "選擇已封存的季度財報 CSV 候選目錄",
            str(getattr(self.source_service, "p0_quarterly_candidate_root", None) or Path.home()),
        )
        if not selected:
            return
        set_candidate_root = getattr(
            self.source_service, "set_p0_quarterly_candidate_root", None
        )
        if not callable(set_candidate_root):
            return
        set_candidate_root(selected)
        self._update_quarterly_candidate_root_label()
        self.refresh_console()

    def _reset_quarterly_candidate_root(self) -> None:
        set_candidate_root = getattr(
            self.source_service, "set_p0_quarterly_candidate_root", None
        )
        if not callable(set_candidate_root):
            return
        set_candidate_root(None)
        self._update_quarterly_candidate_root_label()
        self.refresh_console()

    def _render_quarterly_announcement_crosswalk(self) -> None:
        rows = getattr(self, "_control_center_rows", [])
        source_row = next(
            (
                row
                for row in rows
                if row.get("source_id") == "pit.quarterly_financials"
            ),
            None,
        )
        crosswalk = (
            source_row.get("quarterly_announcement_crosswalk")
            if source_row
            else None
        )
        self._quarterly_announcement_crosswalk = (
            crosswalk if isinstance(crosswalk, dict) else None
        )
        self.quarterly_announcement_crosswalk_table.setRowCount(0)
        self.quarterly_announcement_crosswalk_resource_table.setRowCount(0)
        if self._quarterly_announcement_crosswalk is None:
            self.quarterly_announcement_crosswalk_summary_label.setText(
                "公告候選尚未與季報 CSV 同時讀取；本區不推定未公告、available-at 或來源資格。"
            )
            self.quarterly_announcement_crosswalk_detail_label.setText(
                "選取季報資源並明選一個或多個公告候選後，才會顯示有限窗口對照。"
            )
            self._render_quarterly_formal_impact(None)
            return

        crosswalk = self._quarterly_announcement_crosswalk
        self._render_quarterly_formal_impact(crosswalk.get("formal_impact"))
        state = str(crosswalk.get("status", "unknown"))
        start = crosswalk.get("query_window_start") or "未知"
        end = crosswalk.get("query_window_end") or "未知"
        bundle_rows = crosswalk.get("announcement_candidate_bundles", [])
        bundle_text = "、".join(
            str(item.get("candidate_name", "候選"))
            for item in bundle_rows
            if isinstance(item, dict)
        ) or "未驗證"
        summary = (
            f"狀態：{_announcement_crosswalk_state(state)}｜候選 bundle：{crosswalk.get('announcement_candidate_bundle_count', 0)}"
            f"｜查詢窗口：{start} 至 {end}\n"
            f"唯一公告時間候選：{crosswalk.get('unique_announcement_timestamp_match_count', 0)} 筆；"
            f"多版本歧義：{crosswalk.get('ambiguous_announcement_version_match_count', 0)} 筆。\n"
            f"候選：{bundle_text}\n"
            "依 Owner 授權，明確匹配的 MOPS 顯示日期與時間作為公告時間戳。這是候選對照，尚未回寫正式資料；"
            "不證明 CSV 數值版本、全市場 coverage、歷史 PIT 或來源授權；source acceptance=false、Gate credit=false。"
        )
        errors = crosswalk.get("errors", [])
        if isinstance(errors, list) and errors:
            summary += "\n讀取問題：" + "、".join(str(item) for item in errors)
        self.quarterly_announcement_crosswalk_summary_label.setText(summary)

        summary_rows = crosswalk.get("summary_by_market_statement", [])
        if not isinstance(summary_rows, list):
            summary_rows = []
        _set_rows(
            self.quarterly_announcement_crosswalk_table,
            (
                (
                    item.get("market", "未知"),
                    item.get("statement_type", "未知"),
                    item.get("profile_count", 0),
                    item.get("one_announcement_candidate", 0),
                    item.get("multiple_announcement_candidates", 0),
                    item.get("not_observed_in_selected_windows", 0),
                    item.get("query_window_incomplete", 0),
                    item.get("identity_incomplete", 0),
                )
                for item in summary_rows
                if isinstance(item, dict)
            ),
            status_column=-1,
        )
        self._render_quarterly_announcement_crosswalk_resource()

    def _render_quarterly_formal_impact(self, value: object) -> None:
        """只呈現 reader 提供的正式資料影響，不由候選數推算解除量。"""

        impact = value if isinstance(value, dict) else {}
        status = str(impact.get("status", "unavailable") or "unavailable")
        status_labels = {
            "observed": "已讀回",
            "unavailable": "不可用",
            "not_evaluated": "尚未評估",
        }
        status_text = status_labels.get(status, f"未知（{status}）")
        self.quarterly_formal_impact_state_label.setText(
            f"正式資料影響狀態：{status_text}。"
        )

        metric_specs = (
            ("候選唯一鍵", "candidate_unique_keys"),
            ("正式同公司／報表／期間 identity overlap", "formal_identity_overlap"),
            ("identity overlap 的正式版本數", "formal_version_count"),
            ("identity overlap 的正式財報項目列", "formal_item_rows"),
            ("identity overlap 上正式缺公告日項目列", "missing_announcement_date_rows"),
            ("精確版本連結數", "exact_version_links"),
            ("本次公告對照解除列數（reader 回報）", "rows_cleared"),
        )
        observed = status == "observed"
        rows = []
        for label, key in metric_specs:
            count = impact.get(key) if observed else None
            display_count = (
                f"{count:,}"
                if type(count) is int and count >= 0
                else "未知"
            )
            rows.append((label, display_count))
        table = self.quarterly_formal_impact_table
        table.setRowCount(len(rows))
        for row_index, values in enumerate(rows):
            for column_index, value_text in enumerate(values):
                cell = QTableWidgetItem(value_text)
                cell.setToolTip(value_text)
                table.setItem(row_index, column_index, cell)
        ensure_visible_rows(table, len(metric_specs))

        blockers = impact.get("blockers")
        if isinstance(blockers, (list, tuple)) and all(
            isinstance(item, str) for item in blockers
        ):
            blocker_items = tuple(item.strip() for item in blockers if item.strip())
            if blocker_items:
                blocker_text = "；".join(blocker_items)
                self.quarterly_formal_impact_blockers_label.setText(
                    "Reader blockers：" + blocker_text
                )
            elif observed:
                self.quarterly_formal_impact_blockers_label.setText(
                    "Reader blockers：未回報（不代表來源接受或 Gate 通過）。"
                )
            else:
                self.quarterly_formal_impact_blockers_label.setText(
                    "Reader blockers：未知；目前狀態不足以判定沒有阻擋。"
                )
        else:
            self.quarterly_formal_impact_blockers_label.setText(
                "Reader blockers：未知。"
            )

    def _render_formal_monthly_revenue_quality(self) -> None:
        self._reset_monthly_quality_detail(
            "選取有缺公告日的月份後載入明細；公告候選匹配狀態為未知。"
        )
        table = self.formal_monthly_revenue_quality_table
        table.setRowCount(0)
        value = getattr(self, "_formal_monthly_revenue_quality", None)
        if not isinstance(value, dict):
            self.formal_monthly_revenue_quality_state_label.setText(
                "正式月營收摘要：未知；沒有可讀回的唯讀聚合結果。"
            )
            return
        status = value.get("status")
        blockers = value.get("blockers", [])
        blocker_text = (
            "；原因：" + "、".join(item for item in blockers if isinstance(item, str))
            if isinstance(blockers, list) and blockers
            else ""
        )
        if status != "observed" or value.get("financial_values_returned") is not False:
            self.formal_monthly_revenue_quality_state_label.setText(
                f"正式月營收摘要：不可用／未知{blocker_text}。"
            )
            table.setRowCount(1)
            for column in range(table.columnCount()):
                table.setItem(
                    0,
                    column,
                    QTableWidgetItem("—" if column == 0 else "未知"),
                )
            return
        periods = value.get("periods")
        if not isinstance(periods, list):
            self.formal_monthly_revenue_quality_state_label.setText(
                "正式月營收摘要：未知；期別摘要格式無效。"
            )
            return
        self.formal_monthly_revenue_quality_state_label.setText(
            f"正式月營收摘要：已讀回 {len(periods)} 個資料月份。"
            "讀回成功不代表公告時間已逐公司核實；靜態報表日期另行標示待核實。"
        )
        table.setRowCount(len(periods))
        for row_index, item in enumerate(periods):
            if not isinstance(item, dict):
                continue
            values = (
                str(item.get("period") or "未知"),
                str(item.get("formal_row_count", "未知")),
                str(item.get("missing_announcement_date_row_count", "未知")),
                str(item.get("report_level_date_unverified_row_count", "未知")),
                str(item.get("distinct_stock_code_count", "未知")),
                str(item.get("distinct_source_version_count", "未知")),
            )
            for column, cell_value in enumerate(values):
                table.setItem(row_index, column, QTableWidgetItem(cell_value))
            period_item = table.item(row_index, 0)
            missing_item = table.item(row_index, 2)
            report_level_item = table.item(row_index, 3)
            if period_item is not None:
                period_item.setData(
                    Qt.ItemDataRole.UserRole,
                    str(item.get("period") or ""),
                )
            if missing_item is not None:
                missing_item.setData(
                    Qt.ItemDataRole.UserRole,
                    item.get("missing_announcement_date_row_count"),
                )
            if report_level_item is not None:
                report_level_item.setData(
                    Qt.ItemDataRole.UserRole,
                    item.get("report_level_date_unverified_row_count"),
                )
        self._update_monthly_quality_detail_controls()

    def _selected_monthly_quality_period(self) -> str | None:
        selected = self.formal_monthly_revenue_quality_table.selectedItems()
        if not selected:
            return None
        row = selected[0].row()
        period_item = self.formal_monthly_revenue_quality_table.item(row, 0)
        missing_item = self.formal_monthly_revenue_quality_table.item(row, 2)
        report_level_item = self.formal_monthly_revenue_quality_table.item(row, 3)
        if period_item is None or missing_item is None or report_level_item is None:
            return None
        period = period_item.data(Qt.ItemDataRole.UserRole)
        missing_count = missing_item.data(Qt.ItemDataRole.UserRole)
        report_level_count = report_level_item.data(Qt.ItemDataRole.UserRole)
        if (
            not isinstance(period, str)
            or not period
            or isinstance(missing_count, bool)
            or not isinstance(missing_count, int)
            or missing_count < 0
            or isinstance(report_level_count, bool)
            or not isinstance(report_level_count, int)
            or report_level_count < 0
            or (missing_count == 0 and report_level_count == 0)
        ):
            return None
        return period

    def _update_monthly_quality_detail_controls(self) -> None:
        if self._monthly_quality_detail_worker is not None:
            return
        self.formal_monthly_revenue_quality_detail_button.setEnabled(
            self._selected_monthly_quality_period() is not None
        )

    def _load_selected_monthly_quality_detail(self) -> None:
        period = self._selected_monthly_quality_period()
        if period is None:
            self.formal_monthly_revenue_quality_detail_state_label.setText(
                "請選取公告日缺漏或報表日期待核實列數大於 0 的月份。"
            )
            return
        self._monthly_quality_detail_period = period
        self._load_monthly_quality_detail_page(0)

    def _load_monthly_quality_detail_page(self, offset: int) -> None:
        if self._shutdown_requested or self._monthly_quality_detail_worker is not None:
            return
        period = self._monthly_quality_detail_period
        if period is None:
            period = self._selected_monthly_quality_period()
        if period is None or offset < 0:
            return
        self._monthly_quality_detail_generation += 1
        generation = self._monthly_quality_detail_generation
        worker = TaskWorker(
            self.source_service.read_formal_monthly_revenue_quality_missing_rows,
            period,
            offset,
            100,
        )
        worker.native_thread_finished.connect(worker.deleteLater)
        worker.finished.connect(
            lambda result, current_generation=generation, current_period=period, current_offset=offset: self._on_monthly_quality_detail_finished(
                current_generation, current_period, current_offset, result
            ),
            Qt.ConnectionType.QueuedConnection,
        )
        worker.error.connect(
            lambda error, current_generation=generation: self._on_monthly_quality_detail_error(
                current_generation, error
            ),
            Qt.ConnectionType.QueuedConnection,
        )
        worker.cancelled.connect(
            lambda current_generation=generation: self._on_monthly_quality_detail_cancelled(
                current_generation
            ),
            Qt.ConnectionType.QueuedConnection,
        )
        worker.native_thread_finished.connect(
            lambda current_worker=worker: self._on_monthly_quality_detail_thread_finished(
                current_worker
            ),
            Qt.ConnectionType.QueuedConnection,
        )
        self._monthly_quality_detail_worker = worker
        self.formal_monthly_revenue_quality_detail_button.setEnabled(False)
        self.formal_monthly_revenue_quality_previous_button.setEnabled(False)
        self.formal_monthly_revenue_quality_next_button.setEnabled(False)
        self.formal_monthly_revenue_quality_detail_state_label.setText(
            f"正在背景唯讀載入 {period} 公告日品質明細…"
        )
        worker.start()

    def _on_monthly_quality_detail_finished(
        self,
        generation: int,
        period: str,
        offset: int,
        result: object,
    ) -> None:
        if self._shutdown_requested or generation != self._monthly_quality_detail_generation:
            return
        table = self.formal_monthly_revenue_quality_detail_table
        table.setRowCount(0)
        if (
            not isinstance(result, dict)
            or result.get("schema_version") != FORMAL_MONTHLY_REVENUE_QUALITY_DETAIL_SCHEMA
            or result.get("status") not in {"observed", "unavailable"}
            or result.get("formal_db_write") is not False
            or result.get("financial_values_returned") is not False
            or result.get("period") != period
            or result.get("offset") != offset
            or result.get("limit") != 100
        ):
            self.formal_monthly_revenue_quality_detail_state_label.setText(
                "公告日品質明細：不可用／未知；回傳格式或唯讀邊界不符。"
            )
            return
        if result.get("status") == "unavailable":
            blockers = result.get("blockers")
            if (
                result.get("rows") is not None
                or result.get("mapping_status") != "unknown"
                or result.get("total_count") is not None
                or result.get("has_more") is not None
                or result.get("scope") != "unknown"
                or not isinstance(blockers, list)
                or not blockers
                or any(not isinstance(blocker, str) or not blocker for blocker in blockers)
            ):
                self.formal_monthly_revenue_quality_detail_state_label.setText(
                    "公告日品質明細：不可用／未知；回傳格式或唯讀邊界不符。"
                )
                return
            blocker_text = ", ".join(blockers[:3]).replace("_", " ")
            self.formal_monthly_revenue_quality_detail_state_label.setText(
                f"公告日品質明細目前不可用（{blocker_text}）；mapping 狀態未知，正式資料未修改。"
            )
            return
        rows_value = result.get("rows")
        total_count_value = result.get("total_count")
        if (
            result.get("status") != "observed"
            or not isinstance(rows_value, list)
            or len(rows_value) > 100
            or isinstance(total_count_value, bool)
            or not isinstance(total_count_value, int)
            or total_count_value < 0
            or offset > total_count_value
            or offset + len(rows_value) > total_count_value
            or not isinstance(result.get("has_more"), bool)
            or result.get("has_more") is not (offset + len(rows_value) < total_count_value)
            or result.get("mapping_status")
            not in {"verified", "not_configured", "unavailable", "invalid"}
            or result.get("blockers") != []
            or result.get("scope")
            != "formal_monthly_revenue_announcement_quality_identity_page"
        ):
            self.formal_monthly_revenue_quality_detail_state_label.setText(
                "公告日品質明細：不可用／未知；回傳格式或唯讀邊界不符。"
            )
            return
        rows = result["rows"]
        allowed_match_states = {
            "exact_version_mapping_present",
            "exact_mapping_date_matches",
            "exact_mapping_date_differs",
            "no_exact_version_mapping",
            "unknown",
        }
        if any(
            not isinstance(row, dict)
            or set(row)
            != {
                "stock_code",
                "source",
                "source_version",
                "stored_announced_date",
                "mapping_match_state",
                "mapping_announced_date",
            }
            or row.get("mapping_match_state") not in allowed_match_states
            or not isinstance(row.get("stock_code"), str)
            or not row.get("stock_code", "").strip()
            or not isinstance(row.get("source"), str)
            or not row.get("source", "").strip()
            or not isinstance(row.get("source_version"), str)
            or not row.get("source_version", "").strip()
            or not _monthly_mapping_date_is_valid(
                row, str(result["mapping_status"])
            )
            for row in rows
        ):
            self.formal_monthly_revenue_quality_detail_state_label.setText(
                "公告日品質明細：未知；列身份或候選狀態無法核對。"
            )
            return
        table.setRowCount(len(rows))
        exact_count = 0
        date_match_count = 0
        date_differs_count = 0
        no_exact_count = 0
        for row_index, row in enumerate(rows):
            match_state = row["mapping_match_state"]
            if match_state == "exact_version_mapping_present":
                exact_count += 1
                match_label = "缺公告日列有精確 mapping 候選"
            elif match_state == "exact_mapping_date_matches":
                date_match_count += 1
                match_label = "正式日期與精確 MOPS 公告日期一致"
            elif match_state == "exact_mapping_date_differs":
                date_differs_count += 1
                match_label = "日期不一致（仍待核實）"
            elif match_state == "no_exact_version_mapping":
                no_exact_count += 1
                match_label = "目前 mapping 無精確版本（不代表未公告）"
            else:
                match_label = "未知（mapping 未配置或無法核驗）"
            values = (
                row["stock_code"],
                row["source"],
                row["source_version"],
                row["stored_announced_date"] or "（空白）",
                row["mapping_announced_date"] or "（無精確 mapping）",
                match_label,
            )
            for column, cell_value in enumerate(values):
                table.setItem(row_index, column, QTableWidgetItem(cell_value))
        total_count = result["total_count"]
        displayed_start = offset + 1 if rows else 0
        displayed_end = offset + len(rows)
        if total_count == 0:
            detail_text = f"{period}：正式資料目前沒有公告日缺漏或報表日期待核實列。"
        elif result["mapping_status"] == "verified":
            detail_text = (
                f"{period}：顯示 {displayed_start}–{displayed_end} / {total_count} 列；"
                f"本頁正式日期與 MOPS 日期一致 {date_match_count} 列、日期不一致 {date_differs_count} 列、"
                f"缺公告日但有精確 mapping {exact_count} 列、無精確 mapping {no_exact_count} 列。"
                "日期不一致仍列待核實；無精確 mapping 不代表公司未公告。"
            )
        else:
            mapping_reason = {
                "not_configured": "未配置",
                "unavailable": "不存在或無法讀取",
                "invalid": "含有驗證診斷",
            }.get(str(result["mapping_status"]), "無法核驗")
            detail_text = (
                f"{period}：顯示 {displayed_start}–{displayed_end} / {total_count} 列；"
                f"正式 mapping {mapping_reason}，本頁匹配狀態未知。"
            )
        self.formal_monthly_revenue_quality_detail_state_label.setText(
            detail_text + " 正式資料唯讀；日期仍未重算或回填，也不代表 Gate／PIT 通過。"
        )
        self._monthly_quality_detail_period = period
        self._monthly_quality_detail_offset = offset
        self._monthly_quality_detail_total = total_count
        self.formal_monthly_revenue_quality_previous_button.setEnabled(offset > 0)
        self.formal_monthly_revenue_quality_next_button.setEnabled(
            result.get("has_more") is True
        )

    def _on_monthly_quality_detail_error(self, generation: int, error: str) -> None:
        if self._shutdown_requested or generation != self._monthly_quality_detail_generation:
            return
        self.formal_monthly_revenue_quality_detail_table.setRowCount(0)
        self.formal_monthly_revenue_quality_detail_state_label.setText(
            f"公告日品質明細：不可用／未知（{error}）。正式資料未修改。"
        )

    def _on_monthly_quality_detail_cancelled(self, generation: int) -> None:
        if self._shutdown_requested or generation != self._monthly_quality_detail_generation:
            return
        self.formal_monthly_revenue_quality_detail_state_label.setText(
            "公告日品質明細讀取已取消；狀態未知，正式資料未修改。"
        )

    def _on_monthly_quality_detail_thread_finished(self, worker: TaskWorker) -> None:
        if self._monthly_quality_detail_worker is not worker:
            try:
                worker.deleteLater()
            except RuntimeError:
                pass
            return
        self._monthly_quality_detail_worker = None
        try:
            worker.deleteLater()
        except RuntimeError:
            pass
        if not self._shutdown_requested:
            self.formal_monthly_revenue_quality_previous_button.setEnabled(
                self._monthly_quality_detail_offset > 0
            )
            self.formal_monthly_revenue_quality_next_button.setEnabled(
                self._monthly_quality_detail_total is not None
                and self._monthly_quality_detail_offset + 100
                < self._monthly_quality_detail_total
            )
            self._update_monthly_quality_detail_controls()

    def _reset_monthly_quality_detail(self, status: str) -> None:
        self._monthly_quality_detail_generation += 1
        worker = self._monthly_quality_detail_worker
        if worker is not None:
            try:
                if worker.isRunning():
                    worker.cancel(cooperative=True, wait=False)
            except RuntimeError:
                self._monthly_quality_detail_worker = None
        self._monthly_quality_detail_period = None
        self._monthly_quality_detail_offset = 0
        self._monthly_quality_detail_total = None
        self.formal_monthly_revenue_quality_detail_table.setRowCount(0)
        self.formal_monthly_revenue_quality_detail_state_label.setText(status)
        self.formal_monthly_revenue_quality_previous_button.setEnabled(False)
        self.formal_monthly_revenue_quality_next_button.setEnabled(False)
        self.formal_monthly_revenue_quality_detail_button.setEnabled(False)

    def _render_quarterly_announcement_crosswalk_resource(self) -> None:
        table = self.quarterly_announcement_crosswalk_resource_table
        table.setRowCount(0)
        period_table = self.quarterly_announcement_period_summary_table
        period_table.setRowCount(0)
        crosswalk = self._quarterly_announcement_crosswalk
        selected = self._selected_quarterly_candidate_resource()
        if crosswalk is None or selected is None:
            self.quarterly_announcement_crosswalk_detail_label.setText(
                "選取上方季度 CSV 資源，查看該資源的同公司／報表／期別公告候選。"
            )
            return
        resources = crosswalk.get("resources", [])
        if not isinstance(resources, list):
            resources = []
        match = next(
            (
                item
                for item in resources
                if isinstance(item, dict)
                and item.get("dataset_id") == selected.get("dataset_id")
                and item.get("market") == selected.get("market")
                and item.get("statement") == selected.get("statement")
                and item.get("industry") == selected.get("industry")
            ),
            None,
        )
        if match is None:
            self.quarterly_announcement_crosswalk_detail_label.setText(
                "此資源沒有可核對的完整公司／期別 profile；不從部分列推論公告對照。"
            )
            return
        period_summary = match.get("period_summary", [])
        if isinstance(period_summary, list):
            period_table.setRowCount(len(period_summary))
            for row_index, item in enumerate(period_summary):
                if not isinstance(item, dict):
                    continue
                status_counts = item.get("status_counts", {})
                if not isinstance(status_counts, dict):
                    status_counts = {}
                values = (
                    str(item.get("fiscal_period") or "未知"),
                    str(item.get("profile_row_count", "未知")),
                    str(status_counts.get("one_announcement_candidate", "未知")),
                    str(status_counts.get("multiple_announcement_candidates", "未知")),
                    str(status_counts.get("not_observed_in_selected_windows", "未知")),
                    str(status_counts.get("query_window_incomplete", "未知")),
                    str(status_counts.get("identity_incomplete", "未知")),
                )
                for column, value in enumerate(values):
                    period_table.setItem(row_index, column, QTableWidgetItem(value))
        profile_rows = match.get("rows", [])
        if not isinstance(profile_rows, list):
            profile_rows = []
        summary = match.get("summary", {})
        if not isinstance(summary, dict):
            summary = {}
        profiles_complete = match.get("row_profiles_complete") is True
        completeness_note = (
            "Profile 掃描完整。"
            if profiles_complete
            else "Profile 掃描不完整或未知；期別計數僅涵蓋目前解析列。"
        )
        self.quarterly_announcement_crosswalk_detail_label.setText(
            f"目前資源：{match.get('market')}／{match.get('statement')}／{match.get('industry')}；"
            f"單一公告候選 {summary.get('one_announcement_candidate', 0)}，"
            f"多筆歧義 {summary.get('multiple_announcement_candidates', 0)}，"
            f"窗口內未觀測 {summary.get('not_observed_in_selected_windows', 0)}，"
            f"查詢窗口不完整 {summary.get('query_window_incomplete', 0)}。 {completeness_note}"
        )
        table.setRowCount(len(profile_rows))
        for row_index, item in enumerate(profile_rows):
            if not isinstance(item, dict):
                continue
            candidates = item.get("announcement_candidates", [])
            if not isinstance(candidates, list):
                candidates = []
            dates = sorted(
                {
                    str(candidate.get("announced_date"))
                    for candidate in candidates
                    if isinstance(candidate, dict)
                }
            )
            hashes = sorted(
                {
                    str(candidate.get("source_sha256"))
                    for candidate in candidates
                    if isinstance(candidate, dict)
                }
            )
            values = (
                str(item.get("issuer_code") or "未知"),
                str(item.get("fiscal_period") or "未知"),
                _announcement_crosswalk_state(str(item.get("status", "unknown"))),
                "、".join(
                    sorted(
                        str(candidate.get("announcement_at") or "")
                        for candidate in candidates
                        if isinstance(candidate, dict)
                    )
                ) or ("、".join(dates) if dates else "未觀測"),
                str(item.get("announcement_count", 0)),
                "、".join(value[:12] + "…" for value in hashes) if hashes else "未提供",
            )
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                if column == 5 and hashes:
                    cell.setToolTip("\n".join(hashes))
                elif column == 3 and candidates:
                    cell.setToolTip(
                        "\n".join(
                            f"公告事件 SHA-256: {candidate.get('event_sha256', '未提供')}"
                            f"\n官方公告明細：{candidate.get('detail_url', '未提供')}"
                            for candidate in candidates
                            if isinstance(candidate, dict)
                        )
                    )
                table.setItem(row_index, column, cell)

    def _render_quarterly_candidate_audit(self) -> None:
        rows = getattr(self, "_control_center_rows", [])
        source_row = next(
            (
                row
                for row in rows
                if row.get("source_id") == "pit.quarterly_financials"
            ),
            None,
        )
        audit = source_row.get("quarterly_candidate_audit") if source_row else None
        if not isinstance(audit, dict):
            self._quarterly_candidate_resources = []
            self._quarterly_display_row_profiles = []
            self.quarterly_candidate_summary_label.setText(
                "未載入候選資料。此處只顯示研究候選；來源資格與下游 eligibility 維持 none。"
            )
            self.quarterly_resource_table.setRowCount(0)
            self.quarterly_field_table.setRowCount(0)
            self.quarterly_row_profile_table.setRowCount(0)
            self._quarterly_display_row_profiles = []
            self.quarterly_row_profile_summary_label.setText(
                "尚未載入公司／期別計數。"
            )
            self.quarterly_row_profile_detail_label.setText(
                "空白只表示 CSV 儲存格為空；不推定缺報、不適用或來源完整性。"
            )
            self._render_quarterly_coverage_comparison(None)
            return

        summary = audit.get("summary")
        summary = summary if isinstance(summary, dict) else {}
        resources = audit.get("resources")
        self._quarterly_candidate_resources = [
            item for item in resources if isinstance(item, dict)
        ] if isinstance(resources, list) else []
        blank_total = 0
        nonblank_total = 0
        placeholder_total = 0
        for resource in self._quarterly_candidate_resources:
            field_counts = resource.get("field_counts")
            if not isinstance(field_counts, list):
                continue
            for field in field_counts:
                if not isinstance(field, dict):
                    continue
                blank = field.get("blank_count")
                nonblank = field.get("nonblank_count")
                placeholders = field.get("known_placeholder_counts")
                if isinstance(blank, int):
                    blank_total += blank
                if isinstance(nonblank, int):
                    nonblank_total += nonblank
                if isinstance(placeholders, dict):
                    placeholder_total += sum(
                        value for value in placeholders.values()
                        if isinstance(value, int)
                    )
        errors = audit.get("errors")
        error_text = f"｜驗證錯誤：{_join_blockers(errors)}" if isinstance(errors, list) and errors else ""
        self.quarterly_candidate_summary_label.setText(
            "稽核狀態：{state}｜資源：{resources}（CSV 可解析 {available}、空回應 {empty}、缺檔 {missing}、無效 {invalid}）｜"
            "資料列：{rows}｜重複業務鍵：{duplicates}｜空白／非空（含 placeholder）／其中已知 placeholder：{blank}／{nonblank}／{placeholder}\n"
            "邊界：candidate-only、僅結構與儲存格計數；不推定空白語意、coverage、PIT、授權或來源接受；不寫正式 DB、無 Gate credit、下游資格 none{errors}".format(
                state=_quarterly_audit_state(audit.get("overall_state")),
                resources=summary.get("resource_count", "未知"),
                available=summary.get("available_resource_count", "未知"),
                empty=summary.get("empty_response_resource_count", "未知"),
                missing=summary.get("missing_resource_count", "未知"),
                invalid=summary.get("invalid_resource_count", "未知"),
                rows=summary.get("row_count", "未知"),
                duplicates=summary.get("duplicate_business_key_count", "未知"),
                blank=blank_total,
                nonblank=nonblank_total,
                placeholder=placeholder_total,
                errors=error_text,
            )
        )
        _set_rows(
            self.quarterly_resource_table,
            (
                (
                    resource.get("market", "unknown"),
                    resource.get("statement", "unknown"),
                    resource.get("industry", "unknown"),
                    f"{resource.get('dataset_id', 'unknown')}／{resource.get('artifact') or 'artifact missing'}",
                    _quarterly_candidate_state(resource.get("state")),
                    _display(resource.get("row_count")),
                    _display(resource.get("unique_issuer_count")),
                    _quarterly_resource_cell_summary(resource),
                    _short_hash(resource.get("sha256")),
                )
                for resource in self._quarterly_candidate_resources
            ),
            status_column=4,
            status_dimension="data",
        )
        for row_index, resource in enumerate(self._quarterly_candidate_resources):
            artifact_item = self.quarterly_resource_table.item(row_index, 3)
            if artifact_item is not None:
                artifact_item.setToolTip(str(resource.get("artifact") or "未提供 artifact"))
            hash_item = self.quarterly_resource_table.item(row_index, 8)
            if hash_item is not None:
                hash_item.setToolTip(str(resource.get("sha256") or "沒有已驗證的實檔 SHA-256"))
        if self._quarterly_candidate_resources:
            self.quarterly_resource_table.selectRow(0)
        else:
            self.quarterly_field_table.setRowCount(0)
            self._quarterly_display_row_profiles = []
            self.quarterly_row_profile_table.setRowCount(0)
            self.quarterly_row_profile_summary_label.setText(
                "目前候選目錄沒有可顯示的公司／期別 profile。"
            )
            self.quarterly_row_profile_detail_label.setText(
                "空白只表示 CSV 儲存格為空；不推定缺報、不適用或來源完整性。"
            )
        self._render_quarterly_coverage_comparison(audit.get("coverage_comparison"))

    def _render_quarterly_coverage_comparison(self, value: object) -> None:
        if not isinstance(value, dict):
            self._quarterly_coverage_rows = []
            self.quarterly_coverage_summary_label.setText(
                "選取季度候選與公司名錄候選後，才會顯示逐代號對照。"
            )
            self.quarterly_coverage_table.setRowCount(0)
            self.quarterly_coverage_detail_label.setText(
                "此對照只描述明選的候選檔，不會推定缺報、漏抓、歷史母體或來源完整。"
            )
            return
        rows = value.get("rows")
        summaries = value.get("summary_by_market")
        self._quarterly_coverage_rows = (
            [item for item in rows if isinstance(item, dict)]
            if isinstance(rows, list)
            else []
        )
        if not isinstance(summaries, dict) or not summaries:
            errors = value.get("errors")
            error_text = _join_blockers(errors) if isinstance(errors, list) else ""
            self.quarterly_coverage_summary_label.setText(
                "逐代號對照未完成；目前不顯示部分差異。請確認已選取季度候選與名錄候選，並核對完整性。"
                + (f" 原因：{error_text}" if error_text else "")
            )
        else:
            summary_parts = []
            directory_dates = value.get("directory_dates_by_market")
            quarterly_periods = value.get("quarterly_periods_by_market")
            quarterly_dates = value.get("quarterly_output_dates_by_market")
            for market in ("TWSE", "TPEx"):
                summary = summaries.get(market)
                if not isinstance(summary, dict):
                    continue
                directory_date_values = (
                    directory_dates.get(market, [])
                    if isinstance(directory_dates, dict)
                    else []
                )
                period_values = (
                    quarterly_periods.get(market, [])
                    if isinstance(quarterly_periods, dict)
                    else []
                )
                quarterly_date_values = (
                    quarterly_dates.get(market, [])
                    if isinstance(quarterly_dates, dict)
                    else []
                )
                summary_parts.append(
                    "{market}：目錄觀測代號 {directory}｜目前候選觀測代號 {candidate}｜兩邊都有 {both}｜"
                    "名錄有、目前候選未見 {directory_only}｜候選有、名錄未見 {candidate_only}".format(
                        market=market,
                        directory=summary.get("directory_issuer_count", "未知"),
                        candidate=summary.get("quarterly_candidate_issuer_count", "未知"),
                        both=summary.get("in_both_count", "未知"),
                        directory_only=summary.get(
                            "directory_only_in_current_comparison_count", "未知"
                        ),
                        candidate_only=summary.get(
                            "quarterly_candidate_without_directory_match_count", "未知"
                        ),
                    )
                )
                summary_parts.append(
                    "  名錄出表日：{directory_dates}｜目前候選期別：{periods}｜季報出表日：{quarterly_dates}".format(
                        directory_dates="、".join(str(item) for item in directory_date_values)
                        if isinstance(directory_date_values, list) and directory_date_values
                        else "未提供",
                        periods="、".join(str(item) for item in period_values)
                        if isinstance(period_values, list) and period_values
                        else "未提供",
                        quarterly_dates="、".join(str(item) for item in quarterly_date_values)
                        if isinstance(quarterly_date_values, list) and quarterly_date_values
                        else "未提供",
                    )
                )
            self.quarterly_coverage_summary_label.setText(
                "\n".join(summary_parts)
                + "\n口徑：只比較目前明選的季度候選目錄；名錄與季度 CSV 出表日不同，不是歷史母體。"
                + (
                    "\n目前季度候選含空回應、缺檔、無效或未完整 profile；差異只對照已完整解析的候選列。"
                    if value.get("complete") is not True
                    else ""
                )
            )
        _set_rows(
            self.quarterly_coverage_table,
            (
                (
                    row.get("market", "未知"),
                    row.get("code", "未知"),
                    row.get("name") or "名錄未提供",
                    row.get("industry_code") or "未提供",
                    _quarterly_coverage_state(row.get("comparison_state")),
                )
                for row in self._quarterly_coverage_rows
            ),
            status_column=4,
            status_dimension="data",
        )
        self._filter_quarterly_coverage_rows(self.quarterly_coverage_filter.text())
        self.quarterly_coverage_detail_label.setText(
            "名錄有而目前候選未見，只是這兩份不同日期快照的差異；不代表未申報、漏抓或應申報。"
            "候選有而目前名錄未見，也可能是日期或 issuer 身分差異。來源接受、Gate 3 與 ML 資格均不變。"
        )

    def _filter_quarterly_coverage_rows(self, query: str) -> None:
        normalized = query.strip().casefold()
        visible_rows = []
        for row in getattr(self, "_quarterly_coverage_rows", []):
            if (
                row.get("comparison_state") == "in_both"
                and self.quarterly_coverage_filter_mode.currentIndex() == 0
            ):
                continue
            haystack = " ".join(
                str(row.get(key) or "")
                for key in ("market", "code", "name", "industry_code", "comparison_state")
            ).casefold()
            if not normalized or normalized in haystack:
                visible_rows.append(
                    (
                        row.get("market", "未知"),
                        row.get("code", "未知"),
                        row.get("name") or "名錄未提供",
                        row.get("industry_code") or "未提供",
                        _quarterly_coverage_state(row.get("comparison_state")),
                    )
                )
        _set_rows(
            self.quarterly_coverage_table,
            visible_rows,
            status_column=4,
            status_dimension="data",
        )

    def _render_quarterly_candidate_fields(self) -> None:
        row_index = self.quarterly_resource_table.currentRow()
        resources = getattr(self, "_quarterly_candidate_resources", [])
        if row_index < 0 or row_index >= len(resources):
            self.quarterly_field_table.setRowCount(0)
            return
        resource = resources[row_index]
        counts = resource.get("field_counts")
        if not isinstance(counts, list):
            self.quarterly_field_table.setRowCount(0)
            return
        _set_rows(
            self.quarterly_field_table,
            (
                (
                    field.get("field_name", "unknown"),
                    _display(field.get("blank_count")),
                    _display(field.get("nonblank_count")),
                    _quarterly_blank_rate_text(
                        field.get("blank_count"), field.get("nonblank_count")
                    ),
                    _placeholder_counts(field.get("known_placeholder_counts")),
                )
                for field in counts if isinstance(field, dict)
            ),
            status_column=-1,
        )
        for field_row, field in enumerate(
            item for item in counts if isinstance(item, dict)
        ):
            blank_count = field.get("blank_count")
            nonblank_count = field.get("nonblank_count")
            bar = QProgressBar()
            bar.setRange(0, 1000)
            rate_tenths = _quarterly_blank_rate_tenths(blank_count, nonblank_count)
            if rate_tenths is None:
                bar.setValue(0)
                bar.setFormat("N/A")
            else:
                bar.setValue(rate_tenths)
                bar.setFormat(f"{rate_tenths // 10}.{rate_tenths % 10}%")
            field_name = field.get("field_name", "unknown")
            denominator = (
                blank_count + nonblank_count
                if isinstance(blank_count, int)
                and not isinstance(blank_count, bool)
                and isinstance(nonblank_count, int)
                and not isinstance(nonblank_count, bool)
                else None
            )
            bar.setToolTip(
                f"{field_name}：空白儲存格 {blank_count}／有效 CSV 列 {denominator if denominator is not None else '未知'}。"
                "此比例只描述候選 CSV 的空白儲存格；空白語意未定，不判為缺報或不適用。"
            )
            self.quarterly_field_table.setCellWidget(field_row, 3, bar)

    def _render_quarterly_candidate_next_step(self) -> None:
        resource = self._selected_quarterly_candidate_resource()
        if resource is None:
            self.quarterly_resource_next_step_label.setText(
                "選取資源查看目前候選狀態與下一個核查步驟。"
            )
            return
        self.quarterly_resource_next_step_label.setText(
            _quarterly_resource_next_step(resource)
        )

    def _selected_quarterly_candidate_resource(self) -> dict[str, Any] | None:
        row_index = self.quarterly_resource_table.currentRow()
        resources = getattr(self, "_quarterly_candidate_resources", [])
        if row_index < 0 or row_index >= len(resources):
            return None
        return resources[row_index]

    def _render_quarterly_candidate_row_profiles(self) -> None:
        resource = self._selected_quarterly_candidate_resource()
        profiles = resource.get("row_profiles") if resource is not None else None
        if not isinstance(profiles, list):
            self._quarterly_display_row_profiles = []
            self.quarterly_row_profile_table.setRowCount(0)
            self.quarterly_row_profile_summary_label.setText(
                "此資源沒有逐公司／期別計數；檔案缺失、無效或尚未產生 row profile。"
            )
            self.quarterly_row_profile_detail_label.setText(
                "空白只表示 CSV 儲存格為空；不推定缺報、不適用或來源完整性。"
            )
            return
        rows = [item for item in profiles if isinstance(item, dict)]
        rows.sort(
            key=lambda item: (
                -int(item.get("blank_cell_count", 0))
                if isinstance(item.get("blank_cell_count"), int)
                else 0,
                str(item.get("issuer_code", "")),
                str(item.get("fiscal_period", "")),
            )
        )
        self._quarterly_display_row_profiles = rows
        _set_rows(
            self.quarterly_row_profile_table,
            (
                (
                    profile.get("issuer_code", "未知"),
                    _quarterly_profile_name(profile),
                    profile.get("fiscal_period", "未知"),
                    "、".join(str(value) for value in profile.get("output_dates", []))
                    if isinstance(profile.get("output_dates"), list)
                    else "未提供",
                    _display(profile.get("source_row_count")),
                    _display(profile.get("blank_cell_count")),
                    _display(profile.get("nonblank_cell_count")),
                    _placeholder_total(profile.get("known_placeholder_counts")),
                    len(profile.get("blank_fields", []))
                    if isinstance(profile.get("blank_fields"), list)
                    else "未知",
                )
                for profile in rows
            ),
            status_column=-1,
        )
        for row_index, profile in enumerate(rows):
            blank_fields = profile.get("blank_fields")
            blank_item = self.quarterly_row_profile_table.item(row_index, 8)
            if blank_item is not None:
                blank_item.setToolTip(
                    "空白欄位（原始欄名）："
                    + (
                        "、".join(str(value) for value in blank_fields)
                        if isinstance(blank_fields, list) and blank_fields
                        else "無"
                    )
                )
            placeholder_item = self.quarterly_row_profile_table.item(row_index, 7)
            if placeholder_item is not None:
                placeholder_item.setToolTip(
                    _placeholder_counts(profile.get("known_placeholder_counts"))
                )
        profile_count = resource.get("row_profile_count", len(rows)) if resource else len(rows)
        scanned_count = (
            resource.get("row_profile_scanned_key_count", profile_count)
            if resource
            else profile_count
        )
        truncated = bool(resource.get("row_profiles_truncated")) if resource else False
        complete = resource.get("row_profiles_complete") is True if resource else False
        truncation_text = (
            f"；超過輸出上限，僅保留依公司代碼／期別排序的前 {profile_count} 筆"
            if truncated
            else ""
        )
        completeness_text = "完整列出已解析 key" if complete and not truncated else "不宣稱完整"
        self.quarterly_row_profile_summary_label.setText(
            f"目前顯示 {len(rows)}／輸出 {profile_count}／掃描 {scanned_count} 個公司—期別 key；"
            f"表格依空白儲存格數由高到低；{completeness_text}{truncation_text}。"
            "列數是 CSV 中有完整 issuer／年度／季別鍵的觀察，不是市場分母。"
        )
        self._filter_quarterly_row_profiles(self.quarterly_row_profile_filter.text())

    def _filter_quarterly_row_profiles(self, query: str) -> None:
        needle = query.strip().casefold()
        visible = 0
        table = self.quarterly_row_profile_table
        for row_index in range(table.rowCount()):
            searchable = " ".join(
                table.item(row_index, column).text()
                for column in range(min(3, table.columnCount()))
                if table.item(row_index, column) is not None
            ).casefold()
            hidden = bool(needle and needle not in searchable)
            table.setRowHidden(row_index, hidden)
            if not hidden:
                visible += 1
        crosswalk_table = self.quarterly_announcement_crosswalk_resource_table
        for row_index in range(crosswalk_table.rowCount()):
            searchable = " ".join(
                crosswalk_table.item(row_index, column).text()
                for column in (0, 1)
                if crosswalk_table.item(row_index, column) is not None
            ).casefold()
            crosswalk_table.setRowHidden(
                row_index,
                bool(needle and needle not in searchable),
            )
        resource = self._selected_quarterly_candidate_resource()
        profiles = resource.get("row_profiles") if resource is not None else None
        total_profiles = (
            resource.get("row_profile_count", len(profiles))
            if resource is not None and isinstance(profiles, list)
            else 0
        )
        scanned_count = (
            resource.get("row_profile_scanned_key_count", total_profiles)
            if resource is not None
            else total_profiles
        )
        truncation = (
            "；超過輸出上限，profile 顯示不完整"
            if resource is not None and resource.get("row_profiles_truncated") is True
            else ""
        )
        if needle:
            summary = (
                f"篩選後顯示 {visible}／表格 {table.rowCount()} 個 key；"
                f"輸出 {total_profiles}／掃描 {scanned_count} 個 key{truncation}。"
                "公司／期別列不等於市場 coverage。"
            )
        else:
            complete = (
                resource is not None
                and resource.get("row_profiles_complete") is True
                and resource.get("row_profiles_truncated") is not True
            )
            completeness = "完整列出已解析 key" if complete else "不宣稱完整"
            summary = (
                f"目前顯示 {visible}／輸出 {total_profiles}／掃描 {scanned_count} 個公司—期別 key；"
                f"表格依空白儲存格數由高到低；{completeness}{truncation}。"
                "列數是 CSV 中有完整 issuer／年度／季別鍵的觀察，不是市場分母。"
            )
        self.quarterly_row_profile_summary_label.setText(summary)

    def _render_selected_quarterly_row_profile(self) -> None:
        row_index = self.quarterly_row_profile_table.currentRow()
        resource = self._selected_quarterly_candidate_resource()
        profiles = resource.get("row_profiles") if resource is not None else None
        if not isinstance(profiles, list) or row_index < 0:
            self.quarterly_row_profile_detail_label.setText(
                "空白只表示 CSV 儲存格為空；不推定缺報、不適用或來源完整性。"
            )
            return
        candidates = getattr(self, "_quarterly_display_row_profiles", [])
        if row_index >= len(candidates):
            return
        profile = candidates[row_index]
        blank_fields = profile.get("blank_fields")
        blank_names = (
            "、".join(str(value) for value in blank_fields)
            if isinstance(blank_fields, list) and blank_fields
            else "無空白欄位"
        )
        placeholders = _placeholder_counts(profile.get("known_placeholder_counts"))
        self.quarterly_row_profile_detail_label.setText(
            "選取列：{code} {name}｜期別原值 {period}｜出表日期原值 {dates}｜來源列數 {source_rows}\n"
            "名稱欄位：{name_status}\n空白欄位：{blank_fields}\n已知 placeholder（非空值子集）：{placeholders}\n"
            "以上只描述候選 CSV 儲存格；空白語意、申報義務與 PIT 均未判定。".format(
                code=profile.get("issuer_code", "未知"),
                name=_quarterly_profile_name(profile),
                name_status=(
                    "此 issuer-period 在來源列出現多個公司名稱，未自行選一個。"
                    if profile.get("issuer_name_conflict") is True
                    else "單一觀測值或未提供。"
                ),
                period=profile.get("fiscal_period", "未知"),
                dates="、".join(str(value) for value in profile.get("output_dates", []))
                if isinstance(profile.get("output_dates"), list)
                else "未提供",
                source_rows=profile.get("source_row_count", "未知"),
                blank_fields=blank_names,
                placeholders=placeholders,
            )
        )

    def _render_selected_control_center_details(self) -> None:
        row_index = self.control_center_table.currentRow()
        rows = getattr(self, "_control_center_rows", [])
        if row_index < 0 or row_index >= len(rows):
            self.control_center_detail_label.setText(
                "選取來源查看 Owner 決議、資料／授權／PIT 缺口及下一步。"
            )
            return
        self.control_center_detail_label.setText(
            format_p0_owner_decision_details(rows[row_index])
        )

    def visible_text(self) -> str:
        values = [label.text() for label in self.findChildren(QLabel)]
        for table in (
            self.pipeline_table,
            self.gate_table,
            self.source_table,
            self.control_center_table,
            self.quarterly_resource_table,
            self.quarterly_field_table,
            self.quarterly_row_profile_table,
            self.quarterly_coverage_table,
            self.artifact_table,
            self.learning_table,
        ):
            for row in range(table.rowCount()):
                for column in range(table.columnCount()):
                    item = table.item(row, column)
                    if item is not None:
                        values.append(item.text())
        return "\n".join(values)


def _table(headers: tuple[str, ...]) -> QTableWidget:
    table = QTableWidget(0, len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectRows)
    table.setAlternatingRowColors(True)
    table.verticalHeader().setVisible(False)
    header = table.horizontalHeader()
    header.setSectionResizeMode(QHeaderView.Interactive)
    header.setMinimumSectionSize(72)
    column_count = table.columnCount()
    initial_width = (
        220 if column_count == 1
        else 180 if column_count == 2
        else 150 if column_count <= 4
        else 128 if column_count <= 6
        else 112 if column_count <= 8
        else 104
    )
    for column in range(column_count):
        table.setColumnWidth(column, initial_width)
    table.horizontalHeader().setStretchLastSection(True)
    for column in range(table.columnCount()):
        header_item = table.horizontalHeaderItem(column)
        if header_item is not None:
            header_item.setToolTip(header_item.text())
    ensure_visible_rows(table, 5)
    return table


def _short_hash(value: object) -> str:
    if not isinstance(value, str) or not value:
        return "未驗證"
    return value[:12] + "…"


def _quarterly_candidate_state(value: object) -> str:
    return {
        "available": "candidate_file_parsed",
        "empty_response": "candidate_empty_response",
        "missing": "candidate_file_missing",
        "invalid": "candidate_file_invalid",
    }.get(str(value), "unknown")


def _announcement_crosswalk_state(value: str) -> str:
    return {
        "available": "候選對照完成",
        "partial": "部分窗口／profile 不完整",
        "invalid": "候選驗證失敗",
        "one_announcement_candidate": "有一筆公告候選",
        "multiple_announcement_candidates": "多筆公告候選／歧義",
        "not_observed_in_selected_windows": "選取窗口內未觀測",
        "query_window_incomplete": "查詢窗口不完整",
        "identity_incomplete": "季報身份欄缺漏",
        "unknown": "未知",
    }.get(value, value.replace("_", " "))


def _monthly_mapping_date_is_valid(row: dict[str, Any], mapping_status: str) -> bool:
    state = row.get("mapping_match_state")
    announced_date = row.get("mapping_announced_date")
    stored_date = row.get("stored_announced_date")
    if stored_date is not None and not isinstance(stored_date, str):
        return False
    if state in {
        "exact_version_mapping_present",
        "exact_mapping_date_matches",
        "exact_mapping_date_differs",
    }:
        if mapping_status != "verified" or not isinstance(announced_date, str):
            return False
        try:
            canonical_mapping_date = date.fromisoformat(announced_date).isoformat()
        except ValueError:
            return False
        if state == "exact_version_mapping_present":
            return stored_date is None or stored_date == ""
        if not isinstance(stored_date, str) or not stored_date.strip():
            return False
        dates_match = canonical_mapping_date == stored_date
        return dates_match if state == "exact_mapping_date_matches" else not dates_match
    if state == "no_exact_version_mapping":
        return mapping_status == "verified" and announced_date is None
    if state == "unknown":
        return mapping_status != "verified" and announced_date is None
    return False


def _quarterly_audit_state(value: object) -> str:
    return {
        "available": "結構盤點完成（可能含空回應）",
        "partial": "候選資源不完整",
        "empty_response": "全部資源均無資料列",
        "invalid": "稽核無效或讀取失敗",
        "not_selected": "尚未選取季度候選",
    }.get(str(value), "未知")


def _quarterly_coverage_state(value: object) -> str:
    return {
        "in_both": "名錄與目前候選皆有",
        "directory_only_in_current_comparison": "名錄有／目前候選未見",
        "quarterly_candidate_without_directory_match": "目前候選有／名錄未見",
    }.get(str(value), "未知")


def _quarterly_profile_name(profile: dict[str, Any]) -> str:
    if profile.get("issuer_name_conflict") is True:
        return "名稱有多版本"
    value = profile.get("issuer_name")
    return str(value) if isinstance(value, str) and value else "未提供"


def _quarterly_resource_next_step(resource: dict[str, Any]) -> str:
    identity = "／".join(
        str(resource.get(key) or fallback)
        for key, fallback in (
            ("market", "市場未知"),
            ("dataset_id", "dataset 未知"),
            ("artifact", "artifact 未提供"),
        )
    )
    state = resource.get("state")
    if state == "available":
        guidance = (
            "候選 CSV 結構與檔案雜湊可解析；可查看欄位空白率及公司／期別剖面。"
            "下一步須分別核對可得時間／PIT、授權、單位與報表基準、以及時間相符的 issuer coverage。"
        )
    elif state == "empty_response":
        guidance = (
            "本次候選回應沒有可解析的財報資料列。下一步核對 capture manifest 的原始回應、dataset、"
            "市場、HTTP 與 readback 收據；這不表示市場沒有申報或該欄位不適用。若需重採，另建新候選並保留原件。"
        )
    elif state == "missing":
        guidance = (
            "manifest 列出的候選檔案目前缺失。下一步核對隔離候選目錄與 readback 原件；若無法恢復，"
            "重新擷取時另建新候選，不改寫既存 manifest 或原件。"
        )
    elif state == "invalid":
        guidance = (
            "此候選未通過檔案／收據／CSV 結構驗證。下一步依下方稽核註記檢查原始 manifest 與檔案；"
            "修復後另建新候選並保留原件。"
        )
    else:
        guidance = (
            "候選狀態未知。下一步先確認 manifest 與隔離檔案收據；狀態釐清前不使用該資源。"
        )
    warnings = resource.get("warnings")
    warning_items = (
        [item for item in warnings if isinstance(item, str) and item]
        if isinstance(warnings, list)
        else []
    )
    warning_text = (
        "\n稽核註記：" + "；".join(warning_items[:3])
        if warning_items
        else ""
    )
    return (
        f"選取資源：{identity}\n{guidance}{warning_text}\n"
        "資格邊界：仍為 candidate-only；來源接受為 false、無 Gate credit、下游 eligibility 為 none。"
    )


def _quarterly_resource_cell_summary(resource: dict[str, Any]) -> str:
    counts = resource.get("field_counts")
    if not isinstance(counts, list):
        return "—"
    blank = nonblank = placeholder = 0
    for item in counts:
        if not isinstance(item, dict):
            continue
        blank_value = item.get("blank_count")
        nonblank_value = item.get("nonblank_count")
        if isinstance(blank_value, int):
            blank += blank_value
        if isinstance(nonblank_value, int):
            nonblank += nonblank_value
        placeholder_values = item.get("known_placeholder_counts")
        if isinstance(placeholder_values, dict):
            placeholder += sum(
                value for value in placeholder_values.values()
                if isinstance(value, int)
            )
    return f"{blank}／{nonblank}／{placeholder}"


def _placeholder_counts(value: object) -> str:
    if not isinstance(value, dict) or not value:
        return "0"
    return "、".join(
        f"{token}: {count}"
        for token, count in sorted(value.items())
        if isinstance(token, str) and isinstance(count, int)
    ) or "0"


def _placeholder_total(value: object) -> int | str:
    if not isinstance(value, dict):
        return "未知"
    return sum(count for count in value.values() if isinstance(count, int))


def _quarterly_blank_rate_tenths(blank_count: object, nonblank_count: object) -> int | None:
    if (
        not isinstance(blank_count, int)
        or isinstance(blank_count, bool)
        or blank_count < 0
        or not isinstance(nonblank_count, int)
        or isinstance(nonblank_count, bool)
        or nonblank_count < 0
    ):
        return None
    denominator = blank_count + nonblank_count
    if denominator == 0:
        return None
    return (blank_count * 1000 + denominator // 2) // denominator


def _quarterly_blank_rate_text(blank_count: object, nonblank_count: object) -> str:
    tenths = _quarterly_blank_rate_tenths(blank_count, nonblank_count)
    return "N/A" if tenths is None else f"{tenths // 10}.{tenths % 10}%"


def _set_rows(
    table: QTableWidget,
    rows,
    *,
    status_column: int,
    status_dimension: str = "data",
) -> None:
    materialized = tuple(rows)
    table.setRowCount(len(materialized))
    for row_index, values in enumerate(materialized):
        for column_index, value in enumerate(values):
            item = QTableWidgetItem(
                _status_display(value, dimension=status_dimension)
                if column_index == status_column
                else _display(value)
            )
            item.setToolTip(
                _status_detail_display(value, dimension=status_dimension)
                if column_index == status_column
                else item.text()
            )
            if column_index == status_column:
                item.setForeground(QColor(_STATUS_COLORS.get(str(value).lower(), "#94a3b8")))
            table.setItem(row_index, column_index, item)
    ensure_visible_rows(table, 5)


def _display(value: object) -> str:
    text = str(value) if value not in (None, "") else "Missing / Unknown"
    return text.replace("missing", "Missing").replace("unknown", "Unknown")


def _status_display(value: object, *, dimension: str = "data") -> str:
    raw_value = getattr(value, "value", value)
    raw = str(raw_value if raw_value is not None else "unknown").strip() or "unknown"
    key = raw.lower()
    shared_dimension = dimension
    if key in {
        "waiting_for_time",
        "not_due",
        "market_closed",
        "skipped_market_closed",
        "skipped_non_trading_day",
    }:
        shared_dimension = "event"
    shared_label = status_label(value, dimension=shared_dimension)
    if shared_label.lower() != raw.lower():
        return shared_label
    return _STATUS_LABELS.get(key, raw)


def _status_detail_display(value: object, *, dimension: str = "data") -> str:
    display = _status_display(value, dimension=dimension)
    if display == status_label(value, dimension=dimension):
        return status_detail(value, dimension=dimension)
    raw_value = getattr(value, "value", value)
    raw = str(raw_value if raw_value is not None else "unknown").strip() or "unknown"
    return f"{display}（原始狀態：{raw}）"


def _learning_lane_label(cost_lane: object) -> str:
    if str(cost_lane) == "legacy_fixed_bp":
        return "Legacy 固定 50bp（獨立 lane）"
    return "臺銀公開成本研究"


def _learning_cost_summary(candidate: Any, active: Any, cost_lane: object) -> str:
    if str(cost_lane) == "banktaiwan_estimated_research":
        return "臺銀費稅估算（研究限定，非實際成交）"
    return "Legacy 固定 50bp（獨立研究 lane）"


def _maturity_summary(lane: Any) -> str:
    return (
        f"{getattr(lane, 'matured_sample_count', 0)} 筆／"
        f"{getattr(lane, 'matured_decision_date_count', 0)} 個決策日"
    )


def _verified_maturity_summary(candidate: Any, active: Any) -> str:
    lane = active if getattr(active, "status", "") == "verified" else candidate
    if getattr(lane, "status", "") != "verified":
        return "0 筆／0 個決策日（可靠度未知）"
    return _maturity_summary(lane)


def _learning_record_summary(projection: RecommendationLearningEvidenceProjection) -> str:
    status = str(projection.data_recorded_status or "unknown").lower()
    projection_status = str(projection.status or "unknown").lower()
    if status == "recorded":
        record_summary = "已建立該日預測紀錄"
    elif status == "not_recorded":
        record_summary = "尚未建立該日預測紀錄"
    elif status == "stale":
        record_summary = "資料已過期，未採用"
    elif status == "future_blocked":
        record_summary = "資料日期在未來，已阻擋"
    elif status == "blocked_provenance":
        record_summary = "預測紀錄無法確認"
    else:
        record_summary = "預測紀錄未知，未採用"

    if projection_status == "verified":
        evidence_summary = "自然證據已完成驗證"
    elif projection_status == "blocked_provenance":
        evidence_summary = "自然證據來源追溯受阻，未採用"
    elif projection_status in {"stale", "future_blocked"}:
        evidence_summary = "自然證據日期不在有效範圍，未採用"
    elif projection_status == "pending" and status == "recorded":
        evidence_summary = "自然證據等待成熟"
    else:
        evidence_summary = "自然證據尚未完成驗證"
    return f"{record_summary}；{evidence_summary}"


def _learning_decision_summary(projection: RecommendationLearningEvidenceProjection) -> str:
    decision = str(projection.decision or "unknown").lower()
    if decision == "retain_current":
        reason = _learning_reason_summary(
            projection.decision_reason or projection.adoption_reason
        )
        return f"保留目前模型／規則路徑：{reason}"
    if decision in {"adopt_candidate", "adopt_challenger", "promote"}:
        return "候選變更仍受既有 shadow policy 限制"
    if decision in {"rollback", "rollback_active"}:
        return "依既有 policy 回退目前 active"
    return _status_display(projection.status)


def _learning_next_step(projection: RecommendationLearningEvidenceProjection) -> str:
    status = str(projection.data_recorded_status or "unknown").lower()
    projection_status = str(projection.status or "unknown").lower()
    if projection_status == "blocked_provenance" or status == "blocked_provenance":
        return "先修復來源追溯；修復前不顯示可靠度。"
    if status in {"stale", "future_blocked", "unknown"}:
        return "先確認目標決策日、來源日期與隔離 learning artifact。"
    if projection_status == "verified":
        return projection.next_gap or "已完成自然驗證；依既有 learning gate 進行後續覆核。"
    if projection_status == "pending" and status == "recorded":
        return "等待自然成熟與 typed receipt（自然 forward）；目前不解讀為準確率。"
    if status == "not_recorded":
        return "先建立同一決策日的 scheduled live prediction capture。"
    if status == "recorded":
        return "先確認自然證據驗證狀態；目前不解讀為準確率。"
    return "依驗證詳情與既有 learning gate 進行下一次唯讀覆核。"


def _learning_reason_summary(value: object) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return "原因見驗證詳情"
    if "natural_forward_evidence_receipt_missing" in raw:
        return "自然 forward 證據尚未提供"
    if "cross-capture" in raw or "provenance" in raw:
        return "來源追溯受阻"
    if "blocked_cost_scope" in raw or "cost" in raw and "scope" in raw:
        return "成本情境不一致"
    if "calibration" in raw and ("improv" in raw or "gap" in raw):
        return "校準未改善"
    if "insufficient" in raw and "evidence" in raw:
        return "自然證據不足"
    if "active_pointer_not_available" in raw:
        return "目前沒有可用 active 路徑"
    if "capture" in raw and ("missing" in raw or "not" in raw):
        return "該日預測紀錄不足"
    return "原因見驗證詳情"


def _join(values: tuple[str, ...]) -> str:
    return "；".join(values) if values else "None"


def _join_blockers(values) -> str:
    return "；".join(_blocker_display(value) for value in values) if values else "無"


def _blocker_display(value: object) -> str:
    raw = str(value)
    if raw in _BLOCKER_LABELS:
        return _BLOCKER_LABELS[raw]
    lowered = raw.lower()
    if "stale" in lowered:
        return "研究投影已過期"
    if "formal" in lowered and any(
        token in lowered for token in ("missing", "not_ready", "blocked", "absent")
    ):
        return "缺正式輸入"
    if "missing" in lowered:
        return "資料缺漏"
    return raw


def _join_optional(*values: str | None) -> str:
    present = tuple(value for value in values if value)
    return "｜".join(present) if present else "Missing / Unknown"


def _counts(rows: int | None, eligible: int | None, features: int | None) -> str:
    return (
        f"Rows: {_optional_number(rows)}｜Eligible: {_optional_number(eligible)}｜"
        f"Features: {_optional_number(features)}"
    )


def _optional_number(value: int | None) -> str:
    return f"{value:,}" if value is not None else "Missing / Unknown"


def _control_center_status(control_center: P0SourceControlCenterDTO) -> str:
    if control_center.blocked_count:
        return "blocked"
    if control_center.contract_only_count:
        return "contract_only"
    if control_center.research_shadow_count:
        return "research_shadow"
    if control_center.limited_count:
        return "limited"
    if control_center.accepted_count:
        return "accepted"
    return "unknown"


def _build_conclusion(console: ResearchConsoleDTO) -> str:
    """把投影狀態翻成使用者可先讀懂的決策結論。"""

    blockers = tuple(str(item) for item in console.blockers)
    blockers += tuple(
        str(item)
        for row in console.pipeline
        for item in row.blockers
    )
    if console.source_control_center is not None:
        blockers += tuple(str(item) for item in console.source_control_center.global_blockers)
    unique_blockers = tuple(dict.fromkeys(blockers))
    if "projection_stale" in unique_blockers:
        return (
            "結論：Rule 使用中（規則路徑）；ML 未參與正式決策。\n"
            "研究投影已過期（stale projection），請先重新產生並檢查來源後再解讀開發證據。"
        )
    missing_input = any(
        item in unique_blockers
        for item in (
            "formal_oos_input_missing",
            "formal_inputs_missing",
            "pit_sector_evidence_missing",
            "causal_non_cash_features_missing",
            "rule_champion_artifact_missing",
        )
    )
    missing_input = missing_input or any(
        "formal" in item and ("missing" in item or "not_ready" in item or "blocked" in item)
        for item in unique_blockers
    )
    if missing_input:
        return (
            "結論：Rule 使用中（規則路徑）；ML 未參與正式決策。\n"
            "缺正式輸入：正式 ML 輸入仍缺漏，開發結果只能作為研究參考。"
        )
    if any(item.startswith("projection_") for item in unique_blockers):
        return (
            "結論：Rule 使用中（規則路徑）；ML 未參與正式決策。\n"
            "研究投影尚未具備完整輸入，正式決策維持封閉。"
        )
    return (
        "結論：Rule 使用中（規則路徑）；ML 未參與正式決策。\n"
        "下方開發資料僅供研究與驗證，不能直接改變正式路徑。"
    )


def _build_diagnostics(console: ResearchConsoleDTO) -> str:
    """收合區提供工程排查所需的原始 token 與來源識別。"""

    boundary = console.boundary
    pipeline_status = "；".join(
        f"{row.component_id}={row.status}" for row in console.pipeline
    ) or "None"
    pipeline_blockers = "；".join(
        f"{row.component_id}:{_join(row.blockers)}"
        for row in console.pipeline
        if row.blockers
    ) or "None"
    return (
        f"原始投影狀態：{console.overall_status}\n"
        f"來源識別：{console.source_reference}\n"
        f"Pipeline raw status：{pipeline_status}\n"
        f"Blockers raw：{_join(console.blockers)}\n"
        f"Pipeline blockers raw：{pipeline_blockers}\n"
        f"formal_oos_allowed = {boundary.formal_oos_allowed}\n"
        f"production_blend_alpha_bp = {boundary.production_blend_alpha_bp}\n"
        "Production ML: Disabled\n"
        "Formal path: Rule-only\n"
        "Promotion: Disabled｜Retrain: Disabled｜Scheduler: Disabled｜Trading: Disabled"
    )


def _control_route(row: Any) -> str:
    route = str(getattr(row, "acquisition_route_id", None) or "Missing / Unknown")
    if getattr(row, "fallback_used", None) is True:
        source_route = str(getattr(row, "fallback_from_route_id", None) or "Unknown")
        return f"{route} ← fallback from {source_route}"
    if getattr(row, "fallback_used", None) is False:
        return f"{route} (primary)"
    return route


def _control_pit_coverage(row: Any) -> str:
    pit = str(getattr(row, "pit_status", None) or "Missing / Unknown")
    timestamp_kind = str(getattr(row, "timestamp_kind", None) or "Unknown class")
    coverage_bp = getattr(row, "coverage_bp", None)
    if isinstance(coverage_bp, int) and 0 <= coverage_bp <= 10_000:
        coverage = f"{coverage_bp // 100}.{coverage_bp % 100:02d}%"
    else:
        coverage = "Missing / Unknown"
    observed = getattr(row, "observed_rows", None)
    accepted = getattr(row, "accepted_rows", None)
    blocked = getattr(row, "blocked_rows", None)
    row_counts = ""
    if all(isinstance(value, int) and value >= 0 for value in (accepted, observed)):
        row_counts = f" / accepted {accepted:,} / observed {observed:,}"
        if isinstance(blocked, int) and blocked >= 0:
            row_counts += f" / blocked {blocked:,}"
    # This ratio only measures parser acceptance among observed rows. It is
    # deliberately not labelled as market/universe coverage without an
    # independent denominator supplied by the source owner.
    return f"{pit} / {timestamp_kind} / parser {coverage}{row_counts}"


def _control_license(row: Any) -> str:
    status = str(getattr(row, "license_status", None) or "Missing / Unknown")
    urls = getattr(row, "license_evidence_urls", ()) or ()
    result = f"{status} / URLs: {len(urls)}" if urls else status
    capture_status = str(
        getattr(row, "license_evidence_capture_status", None) or "not_supplied"
    )
    if capture_status != "not_supplied":
        result += f" / candidate: {format_p0_license_capture_status(capture_status)}"
    return result
