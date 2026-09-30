"""Workbench Evidence 子頁的唯讀 Research Console。"""

from __future__ import annotations

from collections.abc import Callable
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QGridLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QToolButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from typing import Any

from app_module.research_console_dtos import ResearchConsoleDTO
from app_module.research_console_source_service import ResearchConsoleSourceService
from app_module.recommendation_learning_evidence_projection_service import (
    RecommendationLearningEvidenceProjection,
    RecommendationLearningEvidenceProjectionService,
)
from app_module.p0_source_control_center import P0SourceControlCenterDTO
from ui_qt.theme import MIDNIGHT_ANALYST
from ui_qt.widgets.layout_helpers import ensure_visible_rows, set_scroll_content_constraints
from ui_qt.widgets.theme_widgets import SectionPanel
from ui_qt.views.update.update_formatters import format_p0_license_capture_status
from ui_qt.workers.task_worker import TaskWorker


_STATUS_COLORS = {
    "observed": "#22c55e",
    "research_baseline": "#38bdf8",
    "development_challenger": "#38bdf8",
    "development_only": "#38bdf8",
    "candidate": "#a78bfa",
    "provisional": "#a78bfa",
    "fixture": "#94a3b8",
    "replay": "#94a3b8",
    "degraded": "#f59e0b",
    "research_only_degraded": "#f59e0b",
    "missing": "#ef4444",
    "unknown": "#ef4444",
    "contract_only": "#a78bfa",
    "blocked_provenance": "#ef4444",
    "blocked": "#ef4444",
    "deferred": "#f59e0b",
    "disabled": "#ef4444",
    "limited": "#f59e0b",
    "accepted": "#22c55e",
    "not_supplied": "#94a3b8",
    "not_observed": "#94a3b8",
    "verified": "#22c55e",
    "pending": "#f59e0b",
    "not_applicable": "#94a3b8",
    "future_blocked": "#ef4444",
    "stale": "#f59e0b",
    "recorded": "#38bdf8",
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
    "degraded": "降級",
    "research_only_degraded": "研究限定／降級",
    "missing": "缺漏",
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
    "pending": "等待自然成熟",
    "not_applicable": "不適用",
    "future_blocked": "未來日期已阻擋",
    "stale": "過期",
    "recorded": "已記錄",
    "research_only_estimated_cost": "研究限定／估計成本",
    "research_shadow": "研究影子",
    "waiting_for_formal_inputs": "等待正式輸入",
    "formal_input_missing": "缺正式輸入",
    "formal_inputs_missing": "缺正式輸入",
    "not_ready": "尚未就緒",
    "unavailable": "不可用",
    "failed": "失敗",
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

        self.refresh_button = QPushButton("重新載入唯讀 projection")
        self.refresh_button.setProperty("variant", "secondary")
        self.refresh_button.clicked.connect(self.refresh_console)
        layout.addWidget(self.refresh_button)
        self.refresh_status_label = QLabel("尚未載入；切換到此分頁時才會讀取唯讀投影。")
        self.refresh_status_label.setWordWrap(True)
        self.refresh_status_label.setStyleSheet(
            f"color: {MIDNIGHT_ANALYST.text_secondary};"
        )
        layout.addWidget(self.refresh_status_label)

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
        control_panel.layout.addWidget(self.control_center_summary_label)
        control_panel.layout.addWidget(self.control_center_table)
        gates_panel.layout.addWidget(control_panel)
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
        self._refresh_pending = False
        worker = self._refresh_worker
        if worker is not None:
            try:
                if worker.isRunning():
                    worker.cancel(cooperative=True, wait=False)
            except RuntimeError:
                self._refresh_worker = None

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
        _set_rows(self.learning_table, rows, status_column=6)
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
            f"整體狀態：{_status_display(console.overall_status)}｜"
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
        )
        _set_rows(
            self.gate_table,
            ((row.gate_id, row.status, row.detail, row.artifact_citation or "Not Available") for row in console.gates),
            status_column=1,
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
        )
        control_center = console.source_control_center
        if control_center is None:
            self.control_center_summary_label.setText(
                    "P0 來源控制中心：未提供 13 項來源治理投影。"
            )
            self.control_center_table.setRowCount(0)
        else:
            self.control_center_summary_label.setText(
                "狀態：{status}｜P0：{count}｜Research shadow：{shadow}｜"
                "Blocked provenance：{blocked}｜Accepted / Limited：{accepted} / {limited}｜"
                "Downstream eligible：{eligible}\n"
                "唯讀邊界：writes=false、formal_oos=false、scheduler=false、auto_accept=false\n"
                "Global blockers：{blockers}".format(
                        status=_status_display(
                        _control_center_status(control_center)
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
            )
        _set_rows(
            self.artifact_table,
            ((row.artifact_type, row.artifact_id, row.status, row.citation) for row in console.artifacts),
            status_column=2,
        )
        if self.learning_projection_service is not None and not self._async_refresh:
            self._refresh_learning_projection()

    def visible_text(self) -> str:
        values = [label.text() for label in self.findChildren(QLabel)]
        for table in (
            self.pipeline_table,
            self.gate_table,
            self.source_table,
            self.control_center_table,
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
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
    table.horizontalHeader().setStretchLastSection(True)
    for column in range(table.columnCount()):
        header_item = table.horizontalHeaderItem(column)
        if header_item is not None:
            header_item.setToolTip(header_item.text())
    ensure_visible_rows(table, 5)
    return table


def _set_rows(table: QTableWidget, rows, *, status_column: int) -> None:
    materialized = tuple(rows)
    table.setRowCount(len(materialized))
    for row_index, values in enumerate(materialized):
        for column_index, value in enumerate(values):
            item = QTableWidgetItem(
                _status_display(value) if column_index == status_column else _display(value)
            )
            item.setToolTip(item.text())
            if column_index == status_column:
                item.setForeground(QColor(_STATUS_COLORS.get(str(value).lower(), "#94a3b8")))
            table.setItem(row_index, column_index, item)
    ensure_visible_rows(table, 5)


def _display(value: object) -> str:
    text = str(value) if value not in (None, "") else "Missing / Unknown"
    return text.replace("missing", "Missing").replace("unknown", "Unknown")


def _status_display(value: object) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return "缺漏／未知"
    return _STATUS_LABELS.get(raw, _display(value))


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
