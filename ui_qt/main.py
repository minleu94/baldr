"""
PySide6 主應用程式
"""

import os
import sys
import time
from pathlib import Path

# 添加項目根目錄到系統路徑
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
# 直接 script 與 -m 入口在任何服務／Qt 匯入前轉入共同 launcher。
if __name__ == "__main__":
    from baldr_launcher import main as launch_application
    raise SystemExit(launch_application())

from app_module.application_bootstrap import ApplicationSettings, resolve_application_settings
from app_module.build_identity import BuildIdentity, detect_build_identity
from data_module.phase3c_backfill_runner import configured_candidate_db_path

from ui_qt.crash_diagnostics import (
    install_crash_diagnostics,
    record_diagnostic,
    record_exception,
)


def _configure_console_streams() -> None:
    """讓 Windows 非 UTF-8 console 不會因為啟動訊息而中止 App。"""

    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if not callable(reconfigure):
            continue
        try:
            reconfigure(encoding="utf-8", errors="backslashreplace")
        except (OSError, ValueError):
            # Console／test capture stream 可能不允許重新設定；啟動流程
            # 仍應繼續，真正的 exception 會由 crash diagnostics 記錄。
            continue


# 直接啟動桌面 App 時，在載入 Qt 與各服務前先裝上 crash hooks；單元測試匯入
# ui_qt.main 時不會碰觸正式 DATA_ROOT。
_crash_diagnostics_log_path: Path | None = None
if __name__ == "__main__":
    _configure_console_streams()
    try:
        _crash_diagnostics_log_path = install_crash_diagnostics()
    except Exception as diagnostics_error:
        print(f"[Main] 無法啟用 crash diagnostics: {diagnostics_error}")

from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QMainWindow,
    QStatusBar,
    QTabWidget,
    QMessageBox,
    QLabel,
    QWidget,
    QPushButton,
    QVBoxLayout,
)
from typing import Dict, Any
from collections.abc import Mapping
from PySide6.QtCore import QCoreApplication, QEvent, QStandardPaths, Qt
from PySide6.QtGui import QFont, QIcon

from data_module.config import TWStockConfig
from app_module.market_breadth_service import (
    MarketBreadthService,
    SQLiteDailyPriceMarketBreadthProvider,
)
from app_module.sector_rotation_service import (
    SectorRotationService,
    SQLiteIndustryIndexSectorRotationProvider,
)
from app_module.industry_strength_service import IndustryStrengthService
from app_module.watchlist_trigger_service import (
    WatchlistTriggerService,
    WatchlistServiceWatchlistProvider,
    SQLiteRankingProvider,
)
from app_module.relative_strength_liquidity_service import (
    RelativeStrengthLiquidityService,
    SQLiteDailyPriceRelativeStrengthLiquidityProvider,
)
from app_module.portfolio_alert_service import PortfolioAlertService
from app_module.portfolio_condition_monitor import PortfolioConditionMonitor
from app_module.portfolio_chip_service import PortfolioChipService
from app_module.update_service import UpdateService
from app_module.backtest_service import BacktestService
from app_module.batch_backtest_service import BatchBacktestService
from app_module.watchlist_service import WatchlistService
from app_module.universe_service import UniverseService
from app_module.research_session import (
    ResearchSessionStore,
    ResearchSessionSnapshotDTO,
    ResearchStockContextDTO,
)
from app_module.decision_continuity_controller import DecisionContinuityController
from app_module.decision_outcome_journey import DecisionOutcomeJourneyService
from app_module.stock_research_report_service import StockResearchReportReadService
from app_module.daily_market_research_screener import DailyMarketResearchScreenerService
from ui_qt.views.daily_market_cohort_view import DailyMarketCohortView
from app_module.stock_research_report_provider_adapters import CurrentRestatedMLRunRegistry

# 導入策略模組以觸發註冊
import decision_module.strategies
from ui_qt.views.strong_stocks_view import StrongStocksView
from ui_qt.views.weak_stocks_view import WeakStocksView
from ui_qt.views.market_regime_view import MarketRegimeView
from ui_qt.views.strong_industries_view import StrongIndustriesView
from ui_qt.views.weak_industries_view import WeakIndustriesView
from ui_qt.views.recommendation_view import RecommendationView
from ui_qt.views.update_view import UpdateView
from ui_qt.views.backtest_view import BacktestView
from ui_qt.views.watchlist_view import WatchlistView
from ui_qt.views.stock_research_workspace import StockResearchWorkspace
from ui_qt.widgets.session_context_strip import SessionContextStrip
from ui_qt.views.smart_money.smart_money_flow_view import SmartMoneyFlowView
from app_module.broker_flow_service import BrokerFlowService
from app_module.smart_money_semantic_service import (
    SmartMoneySemanticService,
    SQLiteSmartMoneyPriceProvider,
)
from app_module.decision_market_frame import DecisionMarketFrameLoader
from app_module.decision_desk_service import (
    DecisionDeskSnapshotBuilder,
    SavedRecommendationDeskProvider,
)
from app_module.market_data_visibility_service import MarketDataVisibilityService
from ui_qt.views.decision_desk_view import DecisionDeskView
from app_module.workbench_source_service import WorkbenchSourceService
from app_module.recommendation_learning_evidence_projection_service import (
    RecommendationLearningEvidenceProjectionService,
)
from app_module.research_console_source_service import ResearchConsoleSourceService
from app_module.engineering_closure_dashboard_service import (
    EngineeringClosureDashboardService,
    EvidenceRehearsalDashboard,
)
from ui_qt.views.workbench_view import UnifiedDecisionWorkbenchView
from ui_qt.theme import build_global_stylesheet
from ui_qt.theme.fonts import (
    preferred_qt_chinese_font_family,
    register_qt_chinese_fonts,
)
from ui_qt.widgets.left_navigation import LeftNavigationWidget, NavigationItem
from ui_qt.widgets.adaptive_workspace_stack import AdaptiveWorkspaceStack
from ui_qt.widgets.layout_helpers import bounded_initial_window_geometry
from ui_qt.widgets.text_sanitizer import sanitize_button_texts
from ui_qt.main_window_coordinator import WORKSPACE_DEFINITIONS, resolve_workspace_key
from ui_qt.runtime_composition import build_runtime_ui_composition
from ui_qt.workers.task_worker import (
    request_cooperative_task_worker_shutdown,
    running_task_workers,
)
from app_module.decision_desk_composition import (
    DecisionDeskMarketRegimeProvider,
    build_decision_desk_composition,
    build_smart_money_composition,
)
from app_module.decision_service_composition import build_decision_service_composition

# Runtime Observatory Imports
from app_module.runtime_services.runtime_controller import RuntimeController
from app_module.runtime_services.environment_readiness_service import (
    EnvironmentReadinessService,
)
from ui_qt.bridges.runtime_event_bridge import QtRuntimeBridge
from ui_qt.views.runtime_view import RuntimeView
from PySide6.QtCore import QTimer


def apply_app_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    loaded_families = register_qt_chinese_fonts()
    preferred_family = preferred_qt_chinese_font_family(loaded_families)
    if preferred_family:
        font = QFont(preferred_family, app.font().pointSize())
        app.setFont(font)
    app.setStyleSheet(build_global_stylesheet())


def _drain_qt_deferred_deletes(
    app: QApplication,
    windows: tuple[Any, ...],
) -> None:
    """在 QApplication 有效期間釋放已關閉的 GUI QObject。"""

    record_diagnostic("qt_deferred_delete_drain_started")

    for window in windows:
        try:
            delete_later = getattr(window, "deleteLater", None)
        except RuntimeError:
            continue
        if not callable(delete_later):
            continue
        try:
            delete_later()
        except RuntimeError:
            # 其他關閉路徑可能已先釋放 wrapper；不要再次觸碰失效 C++ object。
            continue
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    app.processEvents()
    # processEvents 可能才配送 QThread.finished 的 queued cleanup；若該回呼
    # 在視窗釋放後呼叫 worker.deleteLater，第二次有限 flush 會在 Qt 尚有效時
    # 一併排空新建立的 DeferredDelete。
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    record_diagnostic("qt_deferred_delete_drain_finished")


def _resolve_personal_policy_config_path(
    explicit_path: str | Path | None,
    *,
    configured_path: str | Path | None = None,
) -> Path | None:
    """明示 caller 優先，其次共用 config，最後本機 AppConfigLocation。"""

    if explicit_path is None:
        explicit_path = configured_path
    if explicit_path is not None:
        requested_path = Path(explicit_path).expanduser()
        if not requested_path.is_absolute():
            raise ValueError("policy_config_path 必須是明示的絕對路徑")
        return requested_path.resolve()
    if QCoreApplication.instance() is None:
        return None
    location = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.AppConfigLocation
    )
    if not location:
        return None
    return (Path(location) / "personal_use_policy.json").resolve()


class MainWindow(QMainWindow):
    """主窗口"""

    # Keep a usable compact viewport while allowing the responsive navigation
    # and workspace pages to shrink below their desktop size hints.  The
    # previous implicit QMainWindow minimum could be inherited from whichever
    # page was active (Runtime was about 480--800 px wide), so a narrow-window
    # smoke probe was constrained before the navigation-collapse logic ran.
    RESPONSIVE_MIN_WIDTH = 320

    _DecisionDeskMarketRegimeProvider = DecisionDeskMarketRegimeProvider

    def _create_decision_desk_builder(self) -> DecisionDeskSnapshotBuilder:
        composition = build_decision_desk_composition(
            config=self.config,
            regime_service=self.regime_service,
            portfolio_service=self.portfolio_service,
            watchlist_service=self.watchlist_service,
            broker_flow_service=getattr(self, "broker_flow_service", None),
            smart_money_service=getattr(self, "smart_money_semantic_service", None),
            market_frame_loader=getattr(self, "decision_market_frame_loader", None),
            industry_strength_service=getattr(self, "industry_strength_service", None),
            dependencies={
                "DecisionMarketFrameLoader": DecisionMarketFrameLoader,
                "MarketBreadthService": MarketBreadthService,
                "SQLiteDailyPriceMarketBreadthProvider": SQLiteDailyPriceMarketBreadthProvider,
                "SectorRotationService": SectorRotationService,
                "SQLiteIndustryIndexSectorRotationProvider": SQLiteIndustryIndexSectorRotationProvider,
                "IndustryStrengthService": IndustryStrengthService,
                "PortfolioConditionMonitor": PortfolioConditionMonitor,
                "PortfolioChipService": PortfolioChipService,
                "PortfolioAlertService": PortfolioAlertService,
                "WatchlistServiceWatchlistProvider": WatchlistServiceWatchlistProvider,
                "SQLiteRankingProvider": SQLiteRankingProvider,
                "WatchlistTriggerService": WatchlistTriggerService,
                "SQLiteDailyPriceRelativeStrengthLiquidityProvider": SQLiteDailyPriceRelativeStrengthLiquidityProvider,
                "RelativeStrengthLiquidityService": RelativeStrengthLiquidityService,
                "DecisionDeskSnapshotBuilder": DecisionDeskSnapshotBuilder,
                "MarketDataVisibilityService": MarketDataVisibilityService,
            },
        )
        self.decision_market_frame_loader = composition.market_frame_loader
        if getattr(self.config, "output_root", None) is not None:
            composition.builder.recommendation_provider = (
                SavedRecommendationDeskProvider(self.config)
            )
        return composition.builder

    def _bind_selected_journey_readers(self) -> None:
        from app_module.stock_research_chart_marker_composition import (
            ChartMarkerSource, SelectedPortfolioTradeReadAdapter, SelectedJournalReadAdapter,
        )
        from app_module.stock_research_chart_marker_reader import StockChartMarkerRecordSource
        store = self.portfolio_service.store
        route = getattr(store, "route", None)
        if route is not None:
            self.decision_outcome_journey_service.portfolio_trade_reader = SelectedPortfolioTradeReadAdapter(
                ChartMarkerSource(store.trades_file, StockChartMarkerRecordSource.ACTUAL_TRADES,
                                  store._io_custody.guard), account_id=route.identity.key)
        paths = self.journal_storage_selection.paths
        if paths is not None:
            legacy = self.journal_storage_selection.legacy_read_only
            def guard(path: Path) -> Path:
                paths.assert_selected(path, legacy_read_only=legacy)
                return path
            self.decision_outcome_journey_service.journal_reader = SelectedJournalReadAdapter(
                ChartMarkerSource(self.journal_service.store.journal_file,
                                  StockChartMarkerRecordSource.RECOMMENDATION_CONFIRMATIONS, guard),
                journal_paths=paths, legacy_read_only=legacy)

    def _clear_stock_chart_markers(self, _context: object = None) -> None:
        self._chart_marker_generation = getattr(self, "_chart_marker_generation", 0) + 1
        worker = getattr(self, "_chart_marker_worker", None)
        if worker is not None:
            try:
                if worker.isRunning():
                    worker.cancel(wait=False)
            except RuntimeError:
                pass
        workspace = getattr(self, "stock_research_workspace", None)
        if workspace is not None:
            workspace.report_view.set_chart_marker_reader(None, None)

    def _load_stock_chart_markers(self, report: object) -> None:
        from app_module.stock_research_chart_marker_composition import ChartMarkerSource, compose_saved_chart_markers
        from app_module.stock_research_chart_marker_reader import StockChartMarkerRecordSource, StockChartMarkerReadResult
        from app_module.stock_research_report_dtos import StockResearchReportDTO
        from ui_qt.views.stock_research_report_view import _stock_chart_cutoff_date
        from ui_qt.workers.task_worker import TaskWorker

        self._clear_stock_chart_markers()
        workspace = self.stock_research_workspace
        if workspace is None or not isinstance(report, StockResearchReportDTO):
            return
        view = workspace.report_view
        context = view._loaded_request_context
        if context is None or view._loaded_report is not report or not context.source_id:
            return
        cutoff = _stock_chart_cutoff_date(report, context)
        if not cutoff or context.stock_code != report.stock_code:
            return
        generation = self._chart_marker_generation
        store = self.portfolio_service.store
        route = getattr(store, "route", None)
        account_id = route.identity.key if route is not None else "default"
        journal_paths = self.journal_storage_selection.paths
        legacy_journal = self.journal_storage_selection.legacy_read_only
        def journal_guard(path: Path) -> Path:
            if journal_paths is not None:
                journal_paths.assert_selected(path, legacy_read_only=legacy_journal)
            return path
        sources = (
            ChartMarkerSource(store.trades_file, StockChartMarkerRecordSource.ACTUAL_TRADES,
                              store._io_custody.guard),
            ChartMarkerSource(self.journal_service.store.journal_file,
                              StockChartMarkerRecordSource.RECOMMENDATION_CONFIRMATIONS, journal_guard),
        )
        worker = TaskWorker(compose_saved_chart_markers, report, cutoff_date=cutoff,
                            account_id=account_id, expected_source_id=context.source_id, sources=sources)
        self._chart_marker_worker = worker
        def apply(result: object) -> None:
            if (generation != self._chart_marker_generation or view._closing
                    or getattr(self, "_shutdown_close_requested", False)
                    or view._loaded_report is not report or view._loaded_request_context != context):
                return
            if isinstance(result, StockChartMarkerReadResult):
                view._chart_marker_diagnostics = result.diagnostics
                view.set_chart_marker_evidence(result.candidates, result.identities)
        worker.finished.connect(apply)
        worker.native_thread_finished.connect(
            lambda: setattr(self, "_chart_marker_worker", None)
            if getattr(self, "_chart_marker_worker", None) is worker else None
        )
        worker.native_thread_finished.connect(worker.deleteLater)
        worker.start()

    def _clear_personal_h20_product(self, _context: object = None) -> None:
        self._personal_h20_generation = getattr(self, "_personal_h20_generation", 0) + 1
        worker = getattr(self, "_personal_h20_worker", None)
        if worker is not None:
            try:
                if worker.isRunning():
                    worker.cancel(wait=False)
            except RuntimeError:
                pass
        workspace = getattr(self, "stock_research_workspace", None)
        if workspace is not None:
            workspace.report_view.personal_h20_label.setText("個人 H20 模型：等待此股受驗預測")

    def _load_personal_h20_product(self, report: object) -> None:
        from app_module.stock_research_report_dtos import StockResearchReportDTO
        from app_module.recommendation.personal_h20_product_evidence import (
            PersonalH20ProductEvidence, read_personal_h20_product_for_stock,
        )
        from ui_qt.workers.task_worker import TaskWorker
        from scripts.scheduled.personal_h20_daily_hook import read_personal_h20_daily_receipt, read_personal_h20_prediction

        self._clear_personal_h20_product()
        workspace = getattr(self, "stock_research_workspace", None)
        if workspace is None or not isinstance(report, StockResearchReportDTO):
            return
        view = workspace.report_view
        context = view._loaded_request_context
        if context is None or view._loaded_report is not report or context.stock_code != report.stock_code:
            return
        generation = self._personal_h20_generation
        market_root = Path(self.config.data_root)
        configured = os.environ.get("PERSONAL_H20_ACTIVATION_CONFIG")
        config_path = Path(configured) if configured else market_root / "personal" / "recommendation_h20" / "activation.json"
        expected_reference = None
        if context.source_kind == "personal_h20_saved_cohort":
            origin = getattr(self, "_personal_h20_research_origin", None)
            if origin is None or origin[0] != context:
                return
            expected_reference = origin[2]
        worker = TaskWorker(read_personal_h20_product_for_stock, config_path,
            stock_code=report.stock_code, market_root=market_root,
            daily_reader=read_personal_h20_daily_receipt, prediction_reader=read_personal_h20_prediction,
            expected_reference=expected_reference)
        self._personal_h20_worker = worker

        def apply(result: object) -> None:
            if (generation != self._personal_h20_generation or view._closing
                    or getattr(self, "_shutdown_close_requested", False)
                    or view._loaded_report is not report or view._loaded_request_context != context):
                return
            if isinstance(result, PersonalH20ProductEvidence):
                view.set_personal_h20_evidence(result)

        worker.finished.connect(apply)
        worker.native_thread_finished.connect(
            lambda: setattr(self, "_personal_h20_worker", None)
            if getattr(self, "_personal_h20_worker", None) is worker else None)
        worker.native_thread_finished.connect(worker.deleteLater)
        worker.start()

    def _personal_h20_configuration(self) -> tuple[Path, Path]:
        market_root = Path(self.config.data_root)
        configured = os.environ.get("PERSONAL_H20_ACTIVATION_CONFIG")
        return market_root, (Path(configured) if configured else
            market_root / "personal" / "recommendation_h20" / "activation.json")

    def _mount_personal_h20_research(self, recommendation: Any) -> None:
        """既有推薦工作區掛入保存母體；選頁才唯讀載入。"""
        from ui_qt.widgets.personal_h20_research_widget import PersonalH20ResearchWidget

        panel = QWidget(recommendation)
        layout = QVBoxLayout(panel)
        refresh = QPushButton("讀取每日已保存模型名單", panel)
        widget = PersonalH20ResearchWidget(panel)
        layout.addWidget(refresh)
        layout.addWidget(widget)
        self.personal_h20_research_widget = widget
        self.personal_h20_research_panel = panel
        self._personal_h20_cohort_generation = 0
        self._personal_h20_cohort_reference = None
        self._personal_h20_research_origin = None
        refresh.clicked.connect(lambda: self._refresh_personal_h20_cohort())
        widget.researchRequested.connect(self._request_personal_h20_research)
        tabs = recommendation.result_source_tabs
        tabs.addTab(panel, "個人模型選股研究（H20毛報酬）")
        tabs.currentChanged.connect(lambda _index:
            self._refresh_personal_h20_cohort() if tabs.currentWidget() is panel else None)

    def _request_personal_h20_research(self, selection: object) -> None:
        from app_module.recommendation.personal_h20_research_cohort import PersonalH20ResearchSelection
        widget = getattr(self, "personal_h20_research_widget", None)
        if (isinstance(selection, PersonalH20ResearchSelection) and widget is not None
                and widget.isEnabled() and widget.restore_selection(selection)):
            self._refresh_personal_h20_cohort(selection, open_research=True)

    def _refresh_personal_h20_cohort(self, selection: object = None, *, open_research: bool = False) -> None:
        from app_module.recommendation.personal_h20_research_cohort import (
            PersonalH20ResearchCohort, PersonalH20ResearchSelection,
        )
        from scripts.scheduled.personal_h20_daily_hook import read_personal_h20_product_cohort
        from ui_qt.workers.task_worker import TaskWorker

        widget = getattr(self, "personal_h20_research_widget", None)
        if widget is None or widget._closing or getattr(self, "_shutdown_close_requested", False):
            return
        self._personal_h20_cohort_generation += 1
        generation = self._personal_h20_cohort_generation
        previous = getattr(self, "_personal_h20_cohort_worker", None)
        if previous is not None and previous.isRunning():
            previous.cancel(wait=False)
        market_root, config_path = self._personal_h20_configuration()
        widget.setEnabled(False)
        widget._cohort = None
        widget.table.setRowCount(0)
        widget.summary_label.setText("正在唯讀核驗原完整模型名單、預測與來源 pins…")
        worker = TaskWorker(read_personal_h20_product_cohort, config_path, market_root=market_root)
        self._personal_h20_cohort_worker = worker
        def current() -> bool:
            return (generation == self._personal_h20_cohort_generation and not widget._closing
                and not getattr(self, "_shutdown_close_requested", False)
                and self._personal_h20_configuration() == (market_root, config_path))
        def apply(result: object) -> None:
            if not current() or not isinstance(result, tuple) or len(result) != 2:
                return
            reference, cohort = result
            if not isinstance(cohort, PersonalH20ResearchCohort):
                return
            self._personal_h20_cohort_reference = reference
            widget.set_cohort(cohort)
            widget.setEnabled(True)
            if selection is None:
                return
            if not isinstance(selection, PersonalH20ResearchSelection) or not widget.restore_selection(selection):
                self.statusBar().showMessage("原模型／母體／日期／預測 pins 已變動或缺件；無法精確返回或下鑽。")
                return
            if not open_research:
                return
            row = next(row for row in cohort.rows if row.symbol == selection.symbol)
            context = ResearchStockContextDTO(stock_code=row.symbol, decision_date=row.decision_date,
                data_date=row.source_date or "", result_id="", identity_status="personal_research_only",
                source_snapshot_id=cohort.cycle_id, source_snapshot_hash=cohort.manifest_sha256,
                profile_id=cohort.candidate_id, source_id=row.prediction_id,
                source_version=cohort.contract_hash, source_kind="personal_h20_saved_cohort",
                source_label="已保存個人 H20 毛報酬模型研究；效果未成熟",
                source_workspace="recommendation")
            self._personal_h20_research_origin = (context, selection, reference)
            self._open_stock_research_context(context)
        def failed(message: str) -> None:
            if current():
                self._personal_h20_cohort_reference = None
                widget.summary_label.setText("模型名單待核驗／目前不可用：" + str(message)[:300])
                self.statusBar().showMessage("原保存模型名單無法核驗；不以其他日期或QA樣本代替。")
        worker.finished.connect(apply)
        worker.error.connect(failed)
        worker.native_thread_finished.connect(lambda:
            setattr(self, "_personal_h20_cohort_worker", None)
            if getattr(self, "_personal_h20_cohort_worker", None) is worker else None)
        worker.native_thread_finished.connect(worker.deleteLater)
        worker.start()

    def _configure_personal_portfolio_services(self) -> None:
        """Bind existing account contracts once; no ledger creation or identity guesses."""
        from app_module.portfolio_service import PortfolioService
        from app_module.personal_store_selection import resolve_personal_store_selection
        from app_module.personal_store_routes import PersonalStoreDomain, PersonalStoreMode, StoreIdentity
        from app_module.user_declared_holding_research import UserDeclaredHoldingResearchStore
        from app_module.paper_portfolio_readiness_service import (
            PaperPortfolioReadinessService, DEFAULT_PORTFOLIO_ID, DEFAULT_BENCHMARK_ID,
        )
        from app_module.paper_portfolio_weekly_evidence_service import PaperPortfolioWeeklyEvidenceService

        selection = resolve_personal_store_selection(self.config)
        self.personal_store_selection = selection
        self._personal_portfolio_view_kwargs: dict[str, Any] = {}
        if selection.mode is PersonalStoreMode.LEGACY_COMPAT:
            self.portfolio_service = PortfolioService(self.config)
            return
        # These are the existing single-account UI and Paper service contracts.
        actual = selection.route(PersonalStoreDomain.TRADES, StoreIdentity("default"))
        declared = selection.route(PersonalStoreDomain.DECLARED_HOLDINGS, StoreIdentity("default"))
        paper = selection.route(PersonalStoreDomain.PAPER, StoreIdentity(DEFAULT_PORTFOLIO_ID))
        self.portfolio_service = PortfolioService(self.config, route=actual, personal_paths=selection.paths)
        shared = dict(output_root=self.config.output_root, route=paper, personal_paths=selection.paths,
                      config=self.config, portfolio_id=paper.identity.key, benchmark_id=DEFAULT_BENCHMARK_ID)
        self._personal_portfolio_view_kwargs = {
            "user_declared_store": UserDeclaredHoldingResearchStore.from_route(declared, personal_paths=selection.paths),
            "user_declared_portfolio_id": declared.identity.key,
            "paper_readiness_service": PaperPortfolioReadinessService(**shared),
            "paper_weekly_evidence_service": PaperPortfolioWeeklyEvidenceService(**shared),
        }

    def __init__(
        self,
        *,
        policy_config_path: str | Path | None = None,
        daily_market_snapshot_root: str | Path | None = None,
        daily_market_snapshot_cohort_id: str | None = None,
        original_stock_ranking_root: str | Path | None = None,
        application_settings: ApplicationSettings | None = None,
        build_identity: BuildIdentity | None = None,
    ):
        if (daily_market_snapshot_root is None) != (
            daily_market_snapshot_cohort_id is None
        ):
            raise ValueError(
                "daily_market_snapshot_root 與 daily_market_snapshot_cohort_id 必須一起明示"
            )
        for name, value in (
            ("daily_market_snapshot_root", daily_market_snapshot_root),
            ("daily_market_snapshot_cohort_id", daily_market_snapshot_cohort_id),
            ("original_stock_ranking_root", original_stock_ranking_root),
        ):
            if value is not None and not str(value).strip():
                raise ValueError(f"{name} 不可為空")
        if original_stock_ranking_root is not None and daily_market_snapshot_root is None:
            raise ValueError(
                "original_stock_ranking_root 必須搭配明示每日研究快照 root／cohort"
            )
        super().__init__()
        self.application_settings = application_settings or resolve_application_settings()
        self.build_identity = build_identity or detect_build_identity(repository_root=project_root)
        self.setWindowTitle(f"baldr · {self.build_identity.display_text}")
        self.build_identity_label = QLabel(self.build_identity.display_text)
        self.build_identity_label.setObjectName("baldrBuildIdentity")
        self.build_identity_label.setToolTip(
            f"來源 commit：{self.build_identity.source_commit}\n"
            f"設定：{self.application_settings.config_path}\n"
            f"行情：{self.application_settings.environment['DATA_ROOT']}\n"
            f"輸出：{self.application_settings.environment['OUTPUT_ROOT']}\n"
            f"執行狀態：{self.application_settings.runtime_state_root}\n"
            f"研究紀錄：{self.application_settings.ml_registry_repository_root}\n"
            f"程式資源：{self.application_settings.resource_root}"
        )
        self.statusBar().addPermanentWidget(self.build_identity_label)
        primary_screen = QApplication.primaryScreen()
        available_geometry = (
            primary_screen.availableGeometry() if primary_screen is not None else None
        )
        self._initial_window_geometry = bounded_initial_window_geometry(
            available_geometry
        )
        self.setGeometry(self._initial_window_geometry)
        self._navigation_collapsed_by_window = False
        self._shutdown_close_requested = False
        self._shutdown_close_finalizing = False
        self._shutdown_close_started_monotonic: float | None = None
        self._shutdown_close_last_blockers: tuple[str, ...] = ()
        self._shutdown_close_last_diagnostic_monotonic: float | None = None
        self._shutdown_close_timer = QTimer(self)
        self._shutdown_close_timer.setInterval(100)
        self._shutdown_close_timer.timeout.connect(self._poll_shutdown_close)
        self.personal_policy_config_path = _resolve_personal_policy_config_path(
            policy_config_path
        )

        # 設置窗口 icon
        icon_path = Path(__file__).parent / "app_icon.png"
        if icon_path.exists():
            icon_path_abs = icon_path.resolve()  # 使用絕對路徑
            self.setWindowIcon(QIcon(str(icon_path_abs)))

        import logging

        logger = logging.getLogger(__name__)

        try:
            # 初始化配置和服務
            if _startup_controller is not None:
                _startup_controller.window = self
                self.setEnabled(False)
            _startup_step("正在讀取資料設定")
            self.config = TWStockConfig()
            self.personal_policy_config_path = _resolve_personal_policy_config_path(
                policy_config_path,
                configured_path=getattr(self.config, "personal_model_policy_path", None),
            )

            _startup_step("正在建立分析服務")
            decision_services = build_decision_service_composition(config=self.config)
            self.screening_service = decision_services.screening_service
            self.industry_strength_service = decision_services.industry_strength_service
            self.regime_service = decision_services.regime_service
            self.recommendation_service = decision_services.recommendation_service
            self.update_service = UpdateService(
                self.config,
                monthly_revenue_availability_candidate_path=(
                    self._monthly_revenue_availability_candidate_path()
                ),
            )
            self.backtest_service = BacktestService(self.config)
            self.broker_flow_service = BrokerFlowService(self.config)
            self.research_session_store = ResearchSessionStore()

            # 初始化持倉與日記服務
            from app_module.portfolio_service import PortfolioService
            from app_module.journal_service import JournalService
            from app_module.personal_journal_paths import resolve_journal_storage_selection

            self._configure_personal_portfolio_services()
            self.journal_storage_selection = resolve_journal_storage_selection(self.config)
            self.journal_service = JournalService(
                self.config, journal_paths=self.journal_storage_selection.paths,
                legacy_read_only=self.journal_storage_selection.legacy_read_only,
            )
            self.decision_continuity_controller = DecisionContinuityController(
                self.journal_service
            )

            # 觀察清單服務初始化（可能失敗，需要特別處理）
            try:
                from app_module.personal_watchlist_service import build_watchlist_service
                self.watchlist_service = build_watchlist_service(self.config)
                self.watchlist_storage_status = self.watchlist_service.get_storage_status()
            except Exception as e:
                logger.error(f"初始化觀察清單服務失敗: {e}")
                # 創建一個空的服務實例，避免後續錯誤
                self.watchlist_service = None
                print(f"警告：觀察清單服務初始化失敗，將使用空服務: {e}")

            # 選股清單服務初始化（用於推薦結果自動創建選股清單）
            try:
                self.universe_service = UniverseService(self.config)
            except Exception as e:
                logger.error(f"初始化選股清單服務失敗: {e}")
                self.universe_service = None
                print(f"警告：選股清單服務初始化失敗: {e}")

            # 個股研究報告只組合既有 read contract；MainWindow 注入已驗證的
            # current-restated ML registry，不重算推薦，也不把 owner 邏輯搬入 UI。
            _startup_step("正在連接研究資料")
            self.stock_research_ml_registry = CurrentRestatedMLRunRegistry(
                repository_root=self.application_settings.ml_registry_repository_root,
            )
            self.daily_market_snapshot_root = (
                Path(daily_market_snapshot_root).expanduser().resolve()
                if daily_market_snapshot_root is not None
                else None
            )
            self.daily_market_snapshot_cohort_id = (
                str(daily_market_snapshot_cohort_id).strip()
                if daily_market_snapshot_cohort_id is not None
                else None
            )
            self.original_stock_ranking_root = (
                Path(original_stock_ranking_root).expanduser().resolve()
                if original_stock_ranking_root is not None
                else None
            )
            self.daily_market_research_screener_service = DailyMarketResearchScreenerService(
                self.config,
                snapshot_root=self.daily_market_snapshot_root,
                original_ranking_root=self.original_stock_ranking_root,
            )
            self.stock_research_report_service = StockResearchReportReadService(
                self.config,
                portfolio_service=self.portfolio_service,
                condition_monitor=PortfolioConditionMonitor(),
                ml_provider=self.stock_research_ml_registry,
                freshness_status_path=self._data_freshness_status_path(),
                candidate_db_file=configured_candidate_db_path() if self.config.profile != 'test' else None,
                daily_market_snapshot_root=self.daily_market_snapshot_root,
                daily_market_snapshot_cohort_id=self.daily_market_snapshot_cohort_id,
            )
            self.decision_outcome_journey_service = (
                DecisionOutcomeJourneyService.from_config(
                    self.config,
                    journal_path=(self.journal_service.store.journal_file
                                  if self.journal_storage_selection.paths is None else None),
                    journal_paths=self.journal_storage_selection.paths,
                    legacy_journal_read_only=self.journal_storage_selection.legacy_read_only,
                    portfolio_trades_path=self.portfolio_service.store.trades_file,
                )
            )
            self._bind_selected_journey_readers()
            self.stock_research_workspace: StockResearchWorkspace | None = None

            # 設置 UI
            self._setup_ui()
            if self.daily_market_snapshot_cohort_id is not None:
                # Keep the reader field aligned with the explicitly configured
                # source while leaving snapshot loading as a user action.
                self.recommendation_view.daily_market_research_view.cohort_id_input.setText(
                    self.daily_market_snapshot_cohort_id
                )
            self.setMinimumWidth(
                min(self.RESPONSIVE_MIN_WIDTH, self._initial_window_geometry.width())
            )
        except Exception as e:
            logger.error(f"初始化主窗口失敗: {e}")
            import traceback

            print(
                f"錯誤：初始化主窗口失敗\n{str(e)}\n\n詳細信息：\n{traceback.format_exc()}"
            )
            raise

    def _default_workbench_replay_summary_path(self) -> Path | None:
        output_root = getattr(self.config, "output_root", None)
        if output_root is None:
            return None
        candidate = (
            Path(output_root)
            / "evidence_pipeline"
            / "historical_replay_reference_fix_20260706"
            / "historical_replay_2026-01-06_2026-07-06_reference_fix.json"
        )
        return candidate if candidate.exists() else None

    def _research_console_projection_path(self) -> Path | None:
        """只接受顯式 sanitized projection；不掃描 development 或正式資料目錄。"""
        configured_path = os.environ.get("RESEARCH_CONSOLE_PROJECTION")
        return Path(configured_path).expanduser().resolve() if configured_path else None

    def _p0_source_audit_path(self) -> Path | None:
        """只接受顯式 P0 audit artifact；不掃描正式資料或 QA 目錄。"""
        configured_path = os.environ.get("P0_SOURCE_CONTROL_CENTER_AUDIT")
        return Path(configured_path).expanduser().resolve() if configured_path else None

    def _p0_source_decision_path(self) -> Path | None:
        """只接受顯式 P0 owner decision artifact；不掃描正式資料或 QA 目錄。"""
        configured_path = os.environ.get("P0_SOURCE_CONTROL_CENTER_DECISIONS")
        return Path(configured_path).expanduser().resolve() if configured_path else None

    def _p0_license_evidence_path(self) -> Path | None:
        """只接受顯式 P0 license candidate artifact；不掃描正式資料或 QA 目錄。"""
        configured_path = os.environ.get("P0_SOURCE_CONTROL_CENTER_LICENSE_EVIDENCE")
        return Path(configured_path).expanduser().resolve() if configured_path else None

    def _program_readiness_path(self) -> Path | None:
        """只接受顯式整體 readiness artifact；不掃描正式資料或暫存目錄。"""
        configured_path = os.environ.get("PROGRAM_READINESS_ARTIFACT")
        return Path(configured_path).expanduser().resolve() if configured_path else None

    def _monthly_revenue_availability_candidate_path(self) -> Path | None:
        """只接受顯式月營收 availability candidate；不掃描正式資料或暫存目錄。"""
        configured_path = os.environ.get("MONTHLY_REVENUE_AVAILABILITY_CANDIDATE")
        return Path(configured_path).expanduser().resolve() if configured_path else None

    def _data_update_status_path(self) -> Path | None:
        """資料更新時間軸只讀取明確 artifact；未設定時使用固定排程出口。"""
        configured_path = os.environ.get("DATA_UPDATE_STATUS_ARTIFACT")
        if configured_path:
            return Path(configured_path).expanduser().resolve()
        output_root = getattr(self.config, "output_root", None)
        if output_root is None:
            return None
        return (
            Path(output_root) / "scheduled" / "data_update_quick" / "latest_status.json"
        ).resolve()

    def _data_freshness_status_path(self) -> Path | None:
        """資料 freshness 時間軸出口；不搜尋其他 latest_status。"""
        configured_path = os.environ.get("DATA_FRESHNESS_STATUS_ARTIFACT")
        if configured_path:
            return Path(configured_path).expanduser().resolve()
        output_root = getattr(self.config, "output_root", None)
        if output_root is None:
            return None
        return (
            Path(output_root) / "scheduled" / "data_freshness" / "latest_status.json"
        ).resolve()

    def _data_update_history_path(self) -> Path | None:
        """資料更新 append-only history；只接受明確設定或固定排程出口。"""
        configured_path = os.environ.get("DATA_UPDATE_HISTORY_ARTIFACT")
        if configured_path:
            return Path(configured_path).expanduser().resolve()
        output_root = getattr(self.config, "output_root", None)
        if output_root is None:
            return None
        return (
            Path(output_root) / "scheduled" / "data_update_quick" / "history.jsonl"
        ).resolve()

    def _tpex_status_path(self) -> Path | None:
        """TPEX 背景流程狀態出口；只使用固定 meta_data 檔案。"""
        configured_path = os.environ.get("TPEX_REFRESH_STATUS_ARTIFACT")
        if configured_path:
            return Path(configured_path).expanduser().resolve()
        meta_data_dir = getattr(self.config, "meta_data_dir", None)
        if meta_data_dir is None:
            data_root = getattr(self.config, "data_root", None)
            if data_root is None:
                return None
            meta_data_dir = Path(data_root) / "meta_data"
        return (Path(meta_data_dir) / "tpex_full_refresh_status.json").resolve()

    def _controlled_rehearsal_dashboard(self) -> EvidenceRehearsalDashboard | None:
        """Read an explicitly configured controlled report without opening any database."""
        configured_path = os.environ.get("EVIDENCE_REHEARSAL_REPORT")
        if not configured_path:
            return None
        try:
            return EngineeringClosureDashboardService().load_rehearsal_report(
                Path(configured_path)
            )
        except ValueError as error:
            return EvidenceRehearsalDashboard(
                tier="engineering_fixture",
                status="blocked",
                coverage=(),
                blockers=(f"controlled_rehearsal_report_unavailable:{error}",),
            )

    def _select_main_workspace(self, key_or_label: str) -> None:
        workspace_stack = getattr(self, "workspace_stack", None)
        workspace_widgets = getattr(self, "workspace_widgets", {})
        if workspace_stack is None:
            return
        key = resolve_workspace_key(key_or_label)
        widget = workspace_widgets.get(key)
        if widget is None:
            return
        workspace_stack.setCurrentWidget(widget)
        left_navigation = getattr(self, "left_navigation", None)
        if left_navigation is not None:
            left_navigation.set_current_key(key)
        self._on_workspace_selected(key)

    def _select_main_tab(self, tab_name: str) -> None:
        self._select_main_workspace(tab_name)

    def _open_workbench_daily_decision(self) -> None:
        self._open_workbench_market_explore()

    def _open_workbench_market_explore(self) -> None:
        self._select_main_workspace("market_explore")
        market_tabs = getattr(self, "market_tabs", None)
        decision_desk_view = getattr(self, "decision_desk_view", None)
        if market_tabs is not None and decision_desk_view is not None:
            market_tabs.setCurrentWidget(decision_desk_view)

    def _open_workbench_evidence_review(self) -> None:
        self._select_main_workspace("backtest")
        backtest_view = getattr(self, "backtest_view", None)
        result_tabs = getattr(backtest_view, "result_tabs", None)
        if result_tabs is None:
            return
        for index in range(result_tabs.count()):
            if result_tabs.tabText(index) == "證據覆盤":
                result_tabs.setCurrentIndex(index)
                return

    def _open_workbench_portfolio(self) -> None:
        self._select_main_workspace("portfolio")

    def _on_workspace_selected(self, key: str) -> None:
        if key == "market_explore":
            market_tabs = getattr(self, "market_tabs", None)
            on_market_tab_changed = getattr(self, "_on_market_tab_changed", None)
            if market_tabs is not None and on_market_tab_changed is not None:
                on_market_tab_changed(market_tabs.currentIndex())
        elif key == "watchlist":
            watchlist = getattr(self, "watchlist_view", None)
            if hasattr(watchlist, "refresh_all"):
                watchlist.refresh_all()
        elif key == "portfolio":
            portfolio_view = getattr(self, "portfolio_view", None)
            if hasattr(portfolio_view, "refresh_all"):
                portfolio_view.refresh_all()

    def _setup_ui(self):
        """設置 UI"""
        print("[MainWindow] 開始設置 UI...")

        try:
            shell = QWidget()
            shell_layout = QHBoxLayout(shell)
            shell_layout.setContentsMargins(0, 0, 0, 0)
            shell_layout.setSpacing(0)
            workspace_stack = AdaptiveWorkspaceStack()
            workspace_widgets: dict[str, QWidget] = {}

            def add_workspace(key: str, widget: QWidget) -> int:
                workspace_widgets[key] = widget
                return workspace_stack.addWidget(widget)

            # 數據更新標籤
            print("[MainWindow] 創建數據更新視圖...")
            _startup_step("正在建立更新工作區")
            update_view = UpdateView(
                update_service=self.update_service,
                parent=self,
                p0_source_audit_path=self._p0_source_audit_path(),
                p0_license_evidence_path=self._p0_license_evidence_path(),
                p0_source_decision_path=self._p0_source_decision_path(),
                data_update_status_path=self._data_update_status_path(),
                data_update_history_path=self._data_update_history_path(),
                data_freshness_status_path=self._data_freshness_status_path(),
                tpex_status_path=self._tpex_status_path(),
                program_readiness_path=self._program_readiness_path(),
            )
            self.update_view = update_view
            print("[MainWindow] 數據更新視圖創建成功")

            # 市場探索標籤頁（包含多個子標籤）
            print("[MainWindow] 創建市場探索視圖...")
            _startup_step("正在建立市場工作區")
            market_tabs = QTabWidget()

            # 大盤指數標籤（放在最前面）
            print("[MainWindow] 創建大盤指數視圖...")
            market_regime = MarketRegimeView(
                regime_service=self.regime_service, parent=self
            )
            market_tabs.addTab(market_regime, "大盤指數")
            print("[MainWindow] 大盤指數視圖創建成功")

            # 強勢個股標籤
            print("[MainWindow] 創建強勢個股視圖...")
            strong_stocks = StrongStocksView(
                screening_service=self.screening_service,
                watchlist_service=self.watchlist_service,
                parent=self,
            )
            market_tabs.addTab(strong_stocks, "強勢個股")
            print("[MainWindow] 強勢個股視圖創建成功")

            # 弱勢個股標籤
            print("[MainWindow] 創建弱勢個股視圖...")
            weak_stocks = WeakStocksView(
                screening_service=self.screening_service,
                watchlist_service=self.watchlist_service,
                parent=self,
            )
            market_tabs.addTab(weak_stocks, "弱勢個股")
            print("[MainWindow] 弱勢個股視圖創建成功")

            # 強勢產業標籤
            print("[MainWindow] 創建強勢產業視圖...")
            strong_industries = StrongIndustriesView(
                screening_service=self.screening_service, parent=self
            )
            if hasattr(strong_industries, "stockResearchRequested"):
                strong_industries.stockResearchRequested.connect(
                    self._open_stock_research_context
                )
            market_tabs.addTab(strong_industries, "強勢產業")
            print("[MainWindow] 強勢產業視圖創建成功")

            # 弱勢產業標籤
            print("[MainWindow] 創建弱勢產業視圖...")
            weak_industries = WeakIndustriesView(
                screening_service=self.screening_service, parent=self
            )
            if hasattr(weak_industries, "stockResearchRequested"):
                weak_industries.stockResearchRequested.connect(
                    self._open_stock_research_context
                )
            market_tabs.addTab(weak_industries, "弱勢產業")
            print("[MainWindow] 弱勢產業視圖創建成功")

            # 主力流向標籤 (Smart Money Flow)
            print("[MainWindow] 創建主力流向視圖...")
            smart_money_composition = build_smart_money_composition(
                config=self.config,
                broker_flow_service=self.broker_flow_service,
                market_frame_loader=getattr(self, "decision_market_frame_loader", None),
                dependencies={
                    "DecisionMarketFrameLoader": DecisionMarketFrameLoader,
                    "SQLiteSmartMoneyPriceProvider": SQLiteSmartMoneyPriceProvider,
                    "SmartMoneySemanticService": SmartMoneySemanticService,
                },
            )
            self.decision_market_frame_loader = (
                smart_money_composition.market_frame_loader
            )
            self.smart_money_semantic_service = smart_money_composition.service
            smart_money_flow = SmartMoneyFlowView(
                broker_flow_service=self.broker_flow_service,
                watchlist_service=self.watchlist_service,
                smart_money_semantic_service=self.smart_money_semantic_service,
                parent=self,
            )
            market_tabs.addTab(smart_money_flow, "主力流向")
            print("[MainWindow] 主力流向視圖創建成功")

            # 監聽市場觀察 tab 切換事件
            def on_market_tab_changed(index):
                """當市場觀察 tab 被點擊時，檢查是否需要載入數據"""
                current_widget = market_tabs.widget(index)
                if current_widget is market_regime:
                    market_regime.load_data_if_needed()
                elif current_widget is strong_stocks:
                    strong_stocks.load_data_if_needed()
                elif current_widget is weak_stocks:
                    weak_stocks.load_data_if_needed()
                elif current_widget is strong_industries:
                    strong_industries.load_data_if_needed()
                elif current_widget is weak_industries:
                    weak_industries.load_data_if_needed()
                elif current_widget is smart_money_flow:
                    smart_money_flow.load_data_if_needed()

            market_tabs.currentChanged.connect(on_market_tab_changed)
            self._on_market_tab_changed = on_market_tab_changed
            print("[MainWindow] 市場探索標籤頁創建成功")

            # 市場總覽是 Decision Desk 的唯一實例，固定置於市場探索首頁。
            print("[MainWindow] 開始建立每日決策來源...")
            _startup_step("正在建立每日決策")
            try:
                self.decision_desk_builder = self._create_decision_desk_builder()
                decision_desk_view = DecisionDeskView(
                    decision_desk_builder=self.decision_desk_builder,
                    navigate_to_smart_money_callback=self.show_smart_money_flow_for_stock,
                    parent=self,
                )
                self.decision_desk_view = decision_desk_view
                if hasattr(decision_desk_view, "stockResearchRequested"):
                    decision_desk_view.stockResearchRequested.connect(
                        self._open_stock_research_context
                    )
                print("[MainWindow] 每日決策來源建立成功")
            except Exception as e:
                print(f"[MainWindow] 警告：每日決策來源初始化失敗：{e}")
                decision_desk_view = QLabel(f"每日決策初始化失敗，已降級顯示：{e}")
                decision_desk_view.setWordWrap(True)
                self.decision_desk_view = decision_desk_view

            market_tabs.insertTab(0, decision_desk_view, "市場總覽")
            market_tabs.setCurrentIndex(0)

            # Phase 2 Unified Decision Workbench shell（唯讀 DTO/service 邊界）
            print("[MainWindow] 開始建立決策工作台...")
            _startup_step("正在建立決策工作台")
            try:
                self.learning_projection_service = (
                    RecommendationLearningEvidenceProjectionService(
                        self.config,
                        cost_lane="banktaiwan_estimated_research",
                    )
                )
                self.legacy_learning_projection_service = (
                    RecommendationLearningEvidenceProjectionService(
                        self.config,
                        cost_lane="legacy_fixed_bp",
                    )
                )
                self.workbench_source_service = WorkbenchSourceService(
                    self.config,
                    learning_evidence_projection_service=self.learning_projection_service,
                    journal_paths=self.journal_storage_selection.paths,
                    legacy_journal_read_only=self.journal_storage_selection.legacy_read_only,
                )
                self.research_console_source_service = ResearchConsoleSourceService(
                    projection_path=self._research_console_projection_path(),
                    p0_audit_path=self._p0_source_audit_path(),
                    p0_license_evidence_path=self._p0_license_evidence_path(),
                    p0_decision_path=self._p0_source_decision_path(),
                )
                workbench_view = UnifiedDecisionWorkbenchView(
                    source_service=self.workbench_source_service,
                    research_console_source_service=self.research_console_source_service,
                    learning_projection_service=self.learning_projection_service,
                    legacy_learning_projection_service=self.legacy_learning_projection_service,
                    replay_summary_json=self._default_workbench_replay_summary_path(),
                    evidence_rehearsal_dashboard=self._controlled_rehearsal_dashboard(),
                    navigate_to_daily_decision_callback=self._open_workbench_daily_decision,
                    navigate_to_market_explore_callback=self._open_workbench_market_explore,
                    navigate_to_evidence_review_callback=self._open_workbench_evidence_review,
                    navigate_to_portfolio_callback=self._open_workbench_portfolio,
                    navigate_to_watchlist_callback=lambda: self._select_main_workspace(
                        "watchlist"
                    ),
                    navigate_to_stock_research_callback=self._open_stock_research_context,
                    navigate_to_update_callback=lambda: self._select_main_workspace(
                        "update"
                    ),
                    navigate_to_recommendation_callback=lambda: self._select_main_workspace(
                        "recommendation"
                    ),
                    auto_refresh=True,
                    async_refresh=True,
                    parent=self,
                )
                self.workbench_view = workbench_view
                print("[MainWindow] 決策工作台建立成功")
            except Exception as e:
                print(f"[MainWindow] 警告：決策工作台初始化失敗：{e}")
                workbench_view = QLabel(f"決策工作台初始化失敗，已降級顯示：{e}")
                workbench_view.setWordWrap(True)
                self.workbench_view = workbench_view

            # 策略回測標籤（先創建，因為推薦分析需要引用它）
            print("[MainWindow] 創建策略回測視圖...")
            _startup_step("正在建立回測工作區")
            backtest = BacktestView(
                backtest_service=self.backtest_service,
                config=self.config,
                watchlist_service=self.watchlist_service,
                parent=self,
            )
            self.backtest_view = backtest
            print("[MainWindow] 策略回測視圖創建成功")

            # 推薦分析標籤
            print("[MainWindow] 創建推薦分析視圖...")
            _startup_step("正在建立推薦工作區")
            recommendation = RecommendationView(
                recommendation_service=self.recommendation_service,
                daily_market_research_service=self.daily_market_research_screener_service,
                regime_service=self.regime_service,
                watchlist_service=self.watchlist_service,
                config=self.config,
                universe_service=self.universe_service,
                journal_service=self.journal_service,
                personal_policy_path=self.personal_policy_config_path,
                parent=self,
            )
            # 連接一鍵送回測信號（Phase 3.3）
            recommendation.sendToBacktestRequested.connect(
                lambda config: self._handle_send_to_backtest(backtest, config)
            )
            if hasattr(recommendation, "stockResearchRequested"):
                recommendation.stockResearchRequested.connect(
                    self._open_stock_research_context
                )
            self.recommendation_view = recommendation
            self._mount_personal_h20_research(recommendation)
            self._connect_daily_market_cohort_view(recommendation, market_tabs)
            print("[MainWindow] 推薦分析視圖創建成功")

            # 觀察清單標籤（作為獨立 Tab，方便管理）
            # 只有在 watchlist_service 可用時才創建
            _startup_step("正在建立觀察清單")
            watchlist_widget: QWidget
            if self.watchlist_service is not None:
                try:
                    print("[MainWindow] 創建觀察清單視圖...")
                    watchlist = WatchlistView(
                        watchlist_service=self.watchlist_service,
                        config=self.config,
                        parent=self,
                    )
                    if hasattr(watchlist, "sendToBacktestRequested"):
                        watchlist.sendToBacktestRequested.connect(
                            lambda config: self._handle_send_to_backtest(
                                backtest, config
                            )
                        )
                    self.watchlist_view = watchlist
                    self._connect_research_bookmark_routes(recommendation, watchlist)
                    if hasattr(watchlist, "stockResearchRequested"):
                        watchlist.stockResearchRequested.connect(
                            self._open_stock_research_context
                        )
                    elif hasattr(watchlist, "stockAnalysisRequested"):
                        watchlist.stockAnalysisRequested.connect(
                            self.show_smart_money_flow_for_stock
                        )
                    watchlist_widget = watchlist
                    print("[MainWindow] 觀察清單視圖創建成功")
                except Exception as e:
                    print(f"[MainWindow] 警告：無法創建觀察清單標籤: {e}")
                    import traceback

                    print(f"[MainWindow] 詳細堆疊追蹤:\n{traceback.format_exc()}")
                    watchlist_widget = QLabel(f"觀察清單初始化失敗，已降級顯示：{e}")
                    watchlist_widget.setWordWrap(True)
                    self.watchlist_view = watchlist_widget
            else:
                print("[MainWindow] 觀察清單服務不可用，跳過觀察清單標籤")
                watchlist_widget = QLabel("觀察清單服務不可用。")
                watchlist_widget.setWordWrap(True)
                self.watchlist_view = watchlist_widget

            # 持倉管理標籤 (Portfolio MVP)
            _startup_step("正在建立持倉工作區")
            portfolio_widget: QWidget
            try:
                print("[MainWindow] 創建持倉管理視圖...")
                from ui_qt.views.portfolio_view import PortfolioView

                portfolio_view = PortfolioView(
                    portfolio_service=self.portfolio_service,
                    journal_service=self.journal_service,
                    recommendation_service=self.recommendation_service,
                    broker_flow_service=self.broker_flow_service,
                    async_refresh=True,
                    parent=self,
                    **self._personal_portfolio_view_kwargs,
                )
                self.portfolio_view = portfolio_view
                if hasattr(portfolio_view, "stockResearchRequested"):
                    portfolio_view.stockResearchRequested.connect(
                        self._open_stock_research_context
                    )
                portfolio_widget = portfolio_view
                print("[MainWindow] 持倉管理視圖創建成功")
            except Exception as pe:
                print(f"[MainWindow] 警告：無法創建持倉管理標籤: {pe}")
                import traceback

                print(f"[MainWindow] 詳細堆疊追蹤:\n{traceback.format_exc()}")
                portfolio_widget = QLabel(f"持倉管理初始化失敗，已降級顯示：{pe}")
                portfolio_widget.setWordWrap(True)
                self.portfolio_view = portfolio_widget

            self.smart_money_flow = smart_money_flow
            self.market_tabs = market_tabs

            # --- Runtime Observatory MVP Integration ---
            _startup_step("正在建立執行監控")
            runtime_widget: QWidget
            try:
                print("[MainWindow] 初始化 Runtime Observatory...")
                runtime_composition = build_runtime_ui_composition(
                    project_root=self.application_settings.runtime_state_root,
                    parent=self,
                    scheduled_output_root=Path(self.config.output_root) / "scheduled",
                    dependencies={
                        "RuntimeController": RuntimeController,
                        "QtRuntimeBridge": QtRuntimeBridge,
                        "RuntimeView": RuntimeView,
                        "EnvironmentReadinessService": EnvironmentReadinessService,
                        "QTimer": QTimer,
                    },
                    environment_roots=(
                        Path(self.config.data_root),
                        Path(self.config.output_root),
                    ),
                )
                self.runtime_controller = runtime_composition.controller
                self.runtime_bridge = runtime_composition.bridge
                self.runtime_view = runtime_composition.view
                self.runtime_timer = runtime_composition.timer
                runtime_widget = runtime_composition.view
                print("[MainWindow] Runtime Observatory 整合完成")
            except Exception as re:
                print(f"[MainWindow] 警告: Runtime Observatory 初始化失敗: {re}")
                runtime_widget = QLabel(f"Runtime 初始化失敗，已降級顯示：{re}")
                runtime_widget.setWordWrap(True)
            # --------------------------------------------

            _startup_step("正在建立個股研究")
            self.stock_research_workspace = StockResearchWorkspace(
                self.stock_research_report_service,
                journey_service=self.decision_outcome_journey_service,
                continuity_controller=self.decision_continuity_controller,
                parent=self,
            )
            self.stock_research_workspace.returnRequested.connect(
                self._return_from_stock_research_report
            )
            self.stock_research_workspace.report_view.createAnalysisRequested.connect(self._prepare_stock_research_analysis)
            self.stock_research_workspace.report_view.research_bookmark_context_resolver = (
                self._resolve_research_bookmark_stock
            )
            self.stock_research_workspace.report_view.rankBookmarkRequested.connect(
                self._save_original_ranking_bookmark
            )
            self.stock_research_workspace.report_view.latestResearchRequested.connect(
                self._open_latest_bookmark_research
            )
            self.stock_research_workspace.report_view.activeContextChanged.connect(
                lambda context: self.research_session_store.set_stock_context(
                    context, source="stock_research"
                )
            )
            self.stock_research_workspace.report_view.activeContextChanged.connect(
                self._clear_stock_chart_markers
            )
            self.stock_research_workspace.report_view.reportLoaded.connect(
                self._load_stock_chart_markers
            )
            self.stock_research_workspace.report_view.activeContextChanged.connect(
                self._clear_personal_h20_product
            )
            self.stock_research_workspace.report_view.reportLoaded.connect(
                self._load_personal_h20_product
            )
            _startup_step("正在完成介面配置")
            workspace_instances = {
                "workbench": workbench_view,
                "market_explore": market_tabs,
                "recommendation": recommendation,
                "backtest": backtest,
                "watchlist": watchlist_widget,
                "stock_research": self.stock_research_workspace,
                "portfolio": portfolio_widget,
                "update": update_view,
                "runtime": runtime_widget,
            }
            for definition in WORKSPACE_DEFINITIONS:
                add_workspace(definition.key, workspace_instances[definition.key])

            workspace_items = tuple(
                NavigationItem(definition.key, definition.label, icon=definition.icon)
                for definition in WORKSPACE_DEFINITIONS
            )
            self.left_navigation = LeftNavigationWidget(workspace_items, parent=self)
            self.left_navigation.workspaceSelected.connect(self._select_main_workspace)
            shell_layout.addWidget(self.left_navigation)
            shell_layout.addWidget(workspace_stack, 1)

            self.workspace_stack = workspace_stack
            self.workspace_widgets = workspace_widgets
            self.tabs = workspace_stack
            self.left_navigation.set_current_key("workbench")
            self.workspace_stack.setCurrentWidget(workspace_widgets["workbench"])

            self.setCentralWidget(shell)
            print("[MainWindow] UI 設置完成")

            sanitize_button_texts(self)

            # 狀態欄
            self.statusBar().showMessage("就緒")
            self.session_context_strip = SessionContextStrip(
                self.research_session_store, self
            )
            if hasattr(self.session_context_strip, "returnToSourceRequested"):
                self.session_context_strip.returnToSourceRequested.connect(
                    self._return_to_research_source
                )
            self.statusBar().addPermanentWidget(self.session_context_strip, 1)
        except Exception as e:
            print(f"[MainWindow] 錯誤：設置 UI 失敗")
            print(f"[MainWindow] 錯誤類型: {type(e).__name__}")
            print(f"[MainWindow] 錯誤訊息: {str(e)}")
            import traceback

            print(f"[MainWindow] 詳細堆疊追蹤:\n{traceback.format_exc()}")
            raise

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt override
        """在窄桌面視窗自動釋放導覽列空間，不覆寫使用者手動收合。"""

        super().resizeEvent(event)
        navigation = getattr(self, "left_navigation", None)
        if navigation is None:
            return

        if self.width() <= 1120:
            if not navigation.is_collapsed():
                navigation.set_collapsed(True)
                self._navigation_collapsed_by_window = True
            return

        if self.width() >= 1240 and self._navigation_collapsed_by_window:
            navigation.set_collapsed(False)
            self._navigation_collapsed_by_window = False

    def _handle_send_to_backtest(
        self, backtest_view: BacktestView, config: Dict[str, Any]
    ):
        """處理一鍵送回測請求（Phase 3.3）

        Args:
            backtest_view: 回測視圖實例
            config: 回測配置（包含股票清單、策略配置等）
        """
        try:
            # 切換到回測標籤
            self._select_main_workspace("backtest")

            # 調用回測視圖的方法來載入配置
            if hasattr(backtest_view, "load_from_recommendation"):
                backtest_view.load_from_recommendation(config)
            else:
                # 如果方法不存在，顯示提示
                QMessageBox.information(
                    self,
                    "提示",
                    f"已切換到策略回測標籤\n\n"
                    f"股票清單：{len(config.get('stock_list', []))} 檔\n"
                    f"請手動配置回測參數。",
                )
        except Exception as e:
            import traceback

            QMessageBox.critical(
                self, "錯誤", f"一鍵送回測失敗：\n{str(e)}\n\n{traceback.format_exc()}"
            )
        except Exception as e:
            print(f"[MainWindow] 錯誤：設置 UI 失敗")
            print(f"[MainWindow] 錯誤類型: {type(e).__name__}")
            print(f"[MainWindow] 錯誤訊息: {str(e)}")
            import traceback

            print(f"[MainWindow] 詳細堆疊追蹤:\n{traceback.format_exc()}")
            raise

    def show_smart_money_flow_for_stock(self, stock_code: str):
        """切換至市場探索 -> 主力流向，並定位至該個股"""
        try:
            self._select_main_workspace("market_explore")
            if hasattr(self, "market_tabs") and hasattr(self, "smart_money_flow"):
                for j in range(self.market_tabs.count()):
                    if self.market_tabs.widget(j) == self.smart_money_flow:
                        self.market_tabs.setCurrentIndex(j)
                        break
                self.smart_money_flow.select_stock(stock_code)
        except Exception as e:
            import traceback

            QMessageBox.critical(
                self,
                "下鑽錯誤",
                f"無法下鑽主力流向：\n{str(e)}\n\n{traceback.format_exc()}",
            )

    def _coerce_stock_research_context(
        self, value: object
    ) -> ResearchStockContextDTO | None:
        """將頁面 signal 正規化成可放入 session store 的唯讀 DTO。"""

        if isinstance(value, ResearchStockContextDTO):
            return value
        if isinstance(value, Mapping):
            fields = {
                "stock_code",
                "stock_name",
                "decision_date",
                "data_date",
                "result_id",
                "identity_status",
                "source_snapshot_id",
                "source_snapshot_hash",
                "profile_id",
                "profile_version",
                "source_id",
                "source_version",
                "mapping_source_id",
                "mapping_version",
                "mapping_observed_date",
                "source_kind",
                "source_label",
                "source_workspace",
                "ml_scope_mode",
                "daily_snapshot_root",
                "daily_snapshot_cohort_id",
                "daily_snapshot_condition_keys",
                "daily_snapshot_combine_mode",
                "rank_context",
            }
            payload = {key: value.get(key, "") for key in fields}
            # 舊頁面未提供排名來源時，保留 optional DTO 的 None；明示錯誤仍由 DTO 拒絕。
            payload["rank_context"] = value.get("rank_context")
            if not str(payload.get("stock_code") or "").strip():
                return None
            return ResearchStockContextDTO(**payload)
        return None

    def _prepare_stock_research_analysis(self, code: str) -> None:
        view = self.workspace_widgets.get("recommendation")
        scope = getattr(view, "research_scope_input", None)
        if scope is None:
            self.statusBar().showMessage("推薦分析入口未就緒，請檢查模組狀態。")
            return
        scope.setText(code)
        self._select_main_workspace("recommendation")
        self.statusBar().showMessage(f"已指定研究股票 {code}；檢查策略後執行並保存，再返回個股研究明確選取來源。")

    def _open_stock_research_context(self, value: object) -> None:
        """接收保存結果／觀察清單的下鑽 context 並開啟單股研究頁。"""

        context = self._coerce_stock_research_context(value)
        if context is None or not context.stock_code:
            return
        store = getattr(self, "research_session_store", None)
        if store is not None:
            setter = getattr(store, "set_stock_context", None)
            if callable(setter):
                setter(context, source="stock_drilldown")
            else:
                # 與測試替身／舊 host 相容；正式 store 會走 set_stock_context。
                from app_module.research_session import StockResearchContextChanged

                dispatch = getattr(store, "dispatch", None)
                if callable(dispatch):
                    dispatch(
                        StockResearchContextChanged(
                            context=context,
                            stock_code=context.stock_code,
                            stock_name=context.stock_name,
                            decision_date=context.decision_date,
                            data_date=context.data_date,
                            result_id=context.result_id,
                            identity_status=context.identity_status,
                            source_snapshot_id=context.source_snapshot_id,
                            source_snapshot_hash=context.source_snapshot_hash,
                            profile_id=context.profile_id,
                            profile_version=context.profile_version,
                            source_id=context.source_id,
                            source_version=context.source_version,
                            mapping_source_id=context.mapping_source_id,
                            mapping_version=context.mapping_version,
                            mapping_observed_date=context.mapping_observed_date,
                            source_kind=context.source_kind,
                            source_label=context.source_label,
                            source_workspace=context.source_workspace,
                            ml_scope_mode=context.ml_scope_mode,
                            rank_context=context.rank_context,
                            source="stock_drilldown",
                        )
                    )
        report_service = getattr(self, "stock_research_report_service", None)
        if report_service is None:
            # 與舊 host／最小測試替身相容；正式 MainWindow 會走共用報告入口。
            legacy_route = getattr(self, "show_smart_money_flow_for_stock", None)
            if callable(legacy_route):
                legacy_route(context.stock_code)
            return

        workspace = getattr(self, "stock_research_workspace", None)
        if workspace is None:
            return
        workspace.set_context(
            context,
            stock_codes=self._stock_codes_for_research_context(context),
        )
        self._select_main_workspace("stock_research")

    def _connect_daily_market_cohort_view(self, recommendation, market_tabs) -> None:
        """盤勢讀名單的同一 verified snapshot，不另啟日期不同的計算。"""

        daily = recommendation.daily_market_research_view

        def open_list() -> None:
            self._select_main_workspace("recommendation")
            recommendation.result_source_tabs.setCurrentWidget(daily)

        # 原大盤／強弱頁保留自己的全市場來源；研究模式只接同一個
        # verified source view，不在切頁時呼叫 producer 或另建母體。
        shared_consumers = []
        for index in range(market_tabs.count()):
            consumer = market_tabs.widget(index)
            bind_source = getattr(consumer, "set_shared_research_source", None)
            if callable(bind_source):
                bind_source(daily)
                shared_consumers.append(consumer)
        self.shared_market_consumers = tuple(shared_consumers)

        cohort_view = DailyMarketCohortView(daily, open_list, parent=self)
        self.daily_market_cohort_view = cohort_view
        market_tabs.addTab(cohort_view, "研究母體盤勢")
        market_tabs.currentChanged.connect(
            lambda index: cohort_view.on_first_open()
            if market_tabs.widget(index) is cohort_view else None
        )

    def _connect_research_bookmark_routes(self, recommendation, watchlist) -> None:
        """收藏通知只刷新觀察清單；最新研究必須由使用者另行要求。"""

        daily = recommendation.daily_market_research_view
        daily.bookmarkSaved.connect(lambda *_args: watchlist._load_watchlist())
        watchlist.latestResearchRequested.connect(self._open_latest_bookmark_research)

    def _save_original_ranking_bookmark(self, value: object) -> None:
        """經使用者確認後，收藏報告目前 context 指向的原排名版本。"""

        context = self._coerce_stock_research_context(value)
        if context is None or context.rank_context is None:
            self.statusBar().showMessage("原排名收藏 context 不完整；未保存。")
            return
        rank = context.rank_context
        if rank.selected_stock_code != context.stock_code:
            self.statusBar().showMessage("原排名收藏股票身份不一致；已拒絕保存。")
            return
        service = getattr(self, "watchlist_service", None)
        add_bookmark = getattr(service, "add_rank_research_bookmark", None)
        if not callable(add_bookmark):
            self.statusBar().showMessage("觀察清單服務不支援版本化原排名收藏；未保存。")
            return
        config = getattr(self, "config", None)
        db_path = getattr(config, "db_file", None) or getattr(
            config, "sqlite_db_file", None
        )
        if not db_path:
            self.statusBar().showMessage("未配置原排名核驗資料庫；未保存。")
            return
        try:
            from app_module.daily_market_research_bookmark import (
                create_original_stock_ranking_bookmark_from_context,
            )

            bookmark = create_original_stock_ranking_bookmark_from_context(
                context,
                db_path=db_path,
                sort_key=rank.sort_key,
                descending=rank.descending,
                filter_state=rank.filter_state,
            )
        except Exception as exc:
            code = str(getattr(exc, "code", "") or "").strip()
            reason = f"{code}: {exc}" if code else f"{type(exc).__name__}: {exc}"
            self.statusBar().showMessage(
                f"原排名來源已拒絕或版本不符；未收藏。原因：{reason}"
            )
            return
        detail = self._original_ranking_bookmark_confirmation_text(context)
        if (
            QMessageBox.question(
                self,
                "確認收藏此原排名研究",
                f"將目前報告所指向的原始排名版本加入觀察清單？\n\n{detail}",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            != QMessageBox.StandardButton.Yes
        ):
            self.statusBar().showMessage("已取消原排名收藏；觀察清單未變更。")
            return
        try:
            result = add_bookmark(bookmark)
        except Exception as exc:
            self.statusBar().showMessage(
                f"原排名收藏保存失敗：{type(exc).__name__}: {exc}。"
            )
            return
        status = str(getattr(result, "status", "") or "")
        if status == "conflict":
            message = str(getattr(result, "message", "") or "收藏身份衝突")
            self.statusBar().showMessage(f"{message}；未覆寫既有收藏。")
            return
        if status not in {"added", "already_present"}:
            self.statusBar().showMessage(
                str(getattr(result, "message", "原排名收藏未能保存。"))
            )
            return
        watchlist_view = getattr(self, "watchlist_view", None)
        refresh = getattr(watchlist_view, "_load_watchlist", None)
        if callable(refresh):
            refresh()
        bookmark_id = str(
            getattr(result, "source_id", "")
            or getattr(result, "bookmark_id", "")
            or getattr(bookmark, "bookmark_id", "")
        )
        self.statusBar().showMessage(
            f"{'已收藏' if status == 'added' else '此原排名已收藏'} {context.stock_code}；"
            f"來源 ID：{bookmark_id or '已核驗'}。"
        )

    def _original_ranking_bookmark_confirmation_text(
        self, context: ResearchStockContextDTO
    ) -> str:
        rank = context.rank_context
        report_view = getattr(
            getattr(self, "stock_research_workspace", None), "report_view", None
        )
        report = getattr(report_view, "_loaded_report", None)
        ranking = getattr(report, "original_ranking", None)
        label = str(getattr(ranking, "native_score_label", "") or "")
        rank_number = getattr(ranking, "rank", None)
        window = "、".join(rank.comparison_window_dates)
        return (
            f"股票：{context.stock_code}｜模式：{'週' if rank.period == 'week' else '日'}／"
            f"{'強勢 Top' if rank.direction == 'strong' else '弱勢 Bottom'}｜"
            f"原名次：{rank_number if rank_number is not None else rank.selected_rank}｜"
            f"publisher 標籤：{label or '原標籤待報告核對'}\n"
            f"決策日：{rank.decision_date}｜實際比較日：{rank.comparison_date} → {rank.latest_date}\n"
            f"比較窗口：{window}｜規則：{rank.comparison_window_rule}\n"
            f"研究母體 SHA-256：{rank.research_universe_sha256}\n"
            f"方法／版本：{rank.method_name} {rank.method_version}｜"
            f"契約 SHA-256：{rank.method_contract_sha256}\n"
            f"排名 manifest identity／SHA-256：{rank.rank_snapshot_id}／{rank.source_hash}\n"
            f"父快照 identity／SHA-256：{rank.parent_snapshot_id}／{rank.parent_snapshot_hash}"
        )

    def _open_latest_bookmark_research(self, value: object) -> None:
        context = self._coerce_stock_research_context(value)
        if context is not None and (
            context.rank_context is not None
            or context.source_kind == "explicit_latest_stock_research"
        ):
            latest_context = ResearchStockContextDTO(
                stock_code=context.stock_code,
                stock_name=context.stock_name,
                source_kind="explicit_latest_stock_research",
                source_label="使用者明確要求另開最新個股研究",
                source_workspace="stock_research",
            )
            self._open_stock_research_context(latest_context)
            self._select_main_workspace("stock_research")
            return
        recommendation = getattr(self, "recommendation_view", None)
        daily = getattr(recommendation, "daily_market_research_view", None)
        opener = getattr(daily, "open_latest_research", None)
        if context is None or not callable(opener):
            return
        opener(context)
        self._select_main_workspace("recommendation")
        recommendation.result_source_tabs.setCurrentWidget(daily)

    def _resolve_research_bookmark_stock(
        self, context: ResearchStockContextDTO, stock_code: str,
    ) -> ResearchStockContextDTO | None:
        view = getattr(self, "watchlist_view", None)
        resolver = getattr(view, "research_bookmark_context_for_stock", None)
        return resolver(context, stock_code) if callable(resolver) else None

    def _stock_codes_for_research_context(
        self,
        context: ResearchStockContextDTO,
    ) -> tuple[str, ...]:
        """只從來源頁現有 model 取代碼，供研究頁上一檔／下一檔。"""

        if (
            context.source_workspace == "recommendation"
            and context.source_kind == "original_stock_ranking"
            and context.rank_context is not None
        ):
            return context.rank_context.eligible_stock_codes
        if (
            context.source_workspace == "recommendation"
            and context.source_kind == "daily_market_research_snapshot"
        ):
            view = getattr(self, "recommendation_view", None)
            getter = getattr(view, "research_snapshot_stock_codes", None)
            return tuple(getter()) if callable(getter) else ()
        if (
            context.source_workspace == "watchlist"
            and context.source_kind
            in {
                "daily_market_research_snapshot",
                "original_stock_ranking_bookmark",
            }
        ):
            view = getattr(self, "watchlist_view", None)
            getter = getattr(view, "research_bookmark_stock_codes", None)
            return tuple(getter(context)) if callable(getter) else ()
        if context.source_workspace == "watchlist":
            view = getattr(self, "watchlist_view", None)
            model = getattr(view, "stocks_model", None)
        elif context.source_workspace == "portfolio":
            view = getattr(self, "portfolio_view", None)
            model = getattr(view, "positions_model", None)
        else:
            model = None
        getter = getattr(model, "getDataFrame", None)
        if not callable(getter):
            return ()
        try:
            frame = getter()
            values = frame.get("證券代號", ())
            return tuple(
                dict.fromkeys(
                    str(value).strip()
                    for value in values
                    if str(value).strip() and str(value).strip() != "-"
                )
            )
        except Exception:
            return ()

    def _return_from_stock_research_report(self) -> None:
        workspace = getattr(self, "stock_research_workspace", None)
        context = getattr(getattr(workspace, "report_view", None), "context", None)
        if context is not None:
            self._return_to_research_source(context)
            return
        store = getattr(self, "research_session_store", None)
        snapshot = getattr(store, "get_snapshot", lambda: None)()
        if snapshot is not None:
            self._return_to_research_source(snapshot)

    def _return_to_research_source(self, value: object) -> None:
        """由 status strip 返回建立目前上下文的頁面並定位原股票。"""

        context: ResearchStockContextDTO | None = None
        if isinstance(value, ResearchSessionSnapshotDTO):
            context = value.stock_context
        else:
            context = self._coerce_stock_research_context(value)
        if context is None or not context.source_workspace:
            return
        if context.source_kind == "personal_h20_saved_cohort":
            origin = getattr(self, "_personal_h20_research_origin", None)
            if origin is None or origin[0] != context:
                self.statusBar().showMessage("原模型選取身份不可用；不以股票字串返回其他名單。")
                return
            self._select_main_workspace("recommendation")
            self.recommendation_view.result_source_tabs.setCurrentWidget(self.personal_h20_research_panel)
            self._refresh_personal_h20_cohort(origin[1])
            return
        self._select_main_workspace(context.source_workspace)
        if context.source_workspace == "recommendation":
            view = getattr(self, "recommendation_view", None)
        elif context.source_workspace == "watchlist":
            view = getattr(self, "watchlist_view", None)
        elif context.source_workspace == "portfolio":
            view = getattr(self, "portfolio_view", None)
        elif context.source_workspace == "market_explore":
            self._open_workbench_market_explore()
            view = None
        else:
            view = None
        if (
            context.rank_context is not None
            and context.source_workspace == "watchlist"
        ):
            restore = getattr(view, "restore_research_bookmark_stock", None)
            selected = bool(restore(context)) if callable(restore) else False
            if not selected:
                self.statusBar().showMessage(
                    "原排名收藏來源 ID 或 hash 無法精確返回；未用同股其他收藏替代。"
                )
            return
        if (
            context.rank_context is not None
            and context.source_workspace == "recommendation"
        ):
            restore = getattr(view, "restore_research_snapshot_stock", None)
            selected = (
                bool(
                    restore(
                        context.stock_code,
                        manifest_sha256=context.rank_context.parent_snapshot_hash,
                    )
                )
                if callable(restore)
                else False
            )
            if not selected:
                self.statusBar().showMessage(
                    "原排名父快照已變動或目前來源無法定位；未切換到其他模式或最新結果。"
                )
            return
        if context.source_kind == "daily_market_research_snapshot":
            if context.source_workspace == "watchlist":
                restore = getattr(view, "restore_research_bookmark_stock", None)
                selected = bool(restore(context)) if callable(restore) else False
            else:
                restore = getattr(view, "restore_research_snapshot_stock", None)
                selected = (
                    bool(restore(context.stock_code, manifest_sha256=context.source_snapshot_hash))
                    if callable(restore) else False
                )
            if not selected:
                self.statusBar().showMessage(
                    "原每日研究快照已變動或股票不在目前清單；請核對來源，不能用同股替代原結果。"
                )
            return
        selector = getattr(view, "select_stock", None)
        if callable(selector):
            selected = bool(selector(context.stock_code, context.result_id or None))
            if (
                not selected
                and context.source_workspace == "portfolio"
                and context.result_id
            ):
                self._show_research_return_failure(context)

    def _show_research_return_failure(self, context: ResearchStockContextDTO) -> None:
        """呈現 Portfolio exact identity 失配，避免使用者誤以為已返回。"""

        message = (
            f"持倉研究返回未精確定位：{context.stock_code} 的目前持倉來源不是 "
            f"{context.result_id}。為避免同股替代選取，這次未變更持倉列；"
            "請回推薦分析重新開啟正確結果。"
        )
        try:
            self.statusBar().showMessage(message)
        except (AttributeError, RuntimeError):
            # 關閉流程或最小測試 host 可能沒有可用 status bar；不讓提示
            # 失敗反過來破壞原本的 fail-closed return guard。
            return

    def _request_shutdown_dependencies(
        self,
        *,
        send_cancel: bool,
    ) -> tuple[tuple[Any, ...], bool]:
        """送出冪等取消並回報仍未完成的背景依賴。"""

        update_view = getattr(self, "update_view", None)
        if send_cancel:
            update_shutdown = getattr(update_view, "begin_shutdown", None)
            if not callable(update_shutdown):
                update_shutdown = getattr(
                    update_view, "request_cooperative_shutdown", None
                )
            if callable(update_shutdown):
                try:
                    # UpdateView 會建立本次 TPEX cancel marker，並阻止 queued
                    # callback 在收尾期間重新啟動 worker。
                    update_shutdown()
                except Exception as exc:  # pragma: no cover - defensive UI path
                    self._record_shutdown_message(f"UpdateView 關閉協調失敗：{exc}")

        if send_cancel:
            try:
                remaining_workers = request_cooperative_task_worker_shutdown()
            except Exception as exc:  # pragma: no cover - defensive UI path
                self._record_shutdown_message(f"背景 worker 關閉協調失敗：{exc}")
                remaining_workers = (exc,)
        else:
            try:
                remaining_workers = running_task_workers()
            except Exception as exc:  # pragma: no cover - defensive UI path
                self._record_shutdown_message(f"背景 worker 狀態查詢失敗：{exc}")
                remaining_workers = (exc,)

        try:
            background_process_running = bool(
                update_view is not None
                and getattr(
                    update_view,
                    "has_running_background_process",
                    lambda: False,
                )()
            )
        except Exception as exc:  # pragma: no cover - defensive UI path
            self._record_shutdown_message(f"TPEX 背景程序狀態未知：{exc}")
            background_process_running = True
        return tuple(remaining_workers), background_process_running

    def _record_shutdown_message(self, message: str) -> None:
        """把關閉生命週期寫入既有 logger，避免只靠使用者重按 X。"""

        import logging

        logging.getLogger(__name__).info(message)

    def _record_shutdown_diagnostic(
        self,
        event: str,
        *,
        elapsed_seconds: float | None = None,
        worker_count: int | None = None,
        background_process_running: bool | None = None,
    ) -> None:
        """保存不含路徑或工作參數的關閉階段摘要。"""

        record_diagnostic(
            f"ui_shutdown_{event}",
            elapsed_seconds=elapsed_seconds,
            worker_count=worker_count,
            background_process_running=background_process_running,
        )

    def _freeze_child_refresh_sources(self) -> None:
        """凍結有 pending generation 的子頁，避免取消後又補起新 worker。"""

        for attribute in ("workbench_view", "decision_desk_view", "portfolio_view", "recommendation_view"):
            view = getattr(self, attribute, None)
            begin_shutdown = getattr(view, "begin_shutdown", None)
            if not callable(begin_shutdown):
                continue
            try:
                begin_shutdown()
            except Exception as exc:  # pragma: no cover - defensive UI path
                self._record_shutdown_message(f"{attribute} 關閉 gate 設定失敗：{exc}")

        for view in getattr(self, "shared_market_consumers", ()):
            begin_shutdown = getattr(view, "begin_shutdown", None)
            if callable(begin_shutdown):
                try:
                    begin_shutdown()
                except Exception as exc:  # pragma: no cover - defensive UI path
                    self._record_shutdown_message(f"研究盤勢 consumer 關閉 gate 設定失敗：{exc}")

    def _set_shutdown_ui(self) -> None:
        """鎖住內容操作但保留事件迴圈與狀態列可更新。"""

        central_widget = getattr(self, "centralWidget", None)
        central = central_widget() if callable(central_widget) else None
        if central is not None:
            central.setEnabled(False)

    def _poll_shutdown_close(self) -> None:
        """在 worker／外部 process 安全完成後自動完成原本的 close。"""

        if not self._shutdown_close_requested or self._shutdown_close_finalizing:
            return
        remaining_workers, background_process_running = (
            MainWindow._request_shutdown_dependencies(self, send_cancel=False)
        )
        blockers: list[str] = []
        if remaining_workers:
            blockers.append(f"{len(remaining_workers)} 個合作式取消中的背景工作")
        if background_process_running:
            blockers.append("TPEX 背景更新程序（等待 cancel-completed）")
        blocker_tuple = tuple(blockers)
        if blocker_tuple:
            now = time.monotonic()
            if blocker_tuple != self._shutdown_close_last_blockers:
                self._shutdown_close_last_blockers = blocker_tuple
                self._shutdown_close_last_diagnostic_monotonic = now
                started = self._shutdown_close_started_monotonic
                elapsed = now - started if started is not None else 0.0
                MainWindow._record_shutdown_diagnostic(
                    self,
                    "waiting",
                    elapsed_seconds=elapsed,
                    worker_count=len(remaining_workers),
                    background_process_running=background_process_running,
                )
                MainWindow._record_shutdown_message(
                    self, "主視窗關閉仍在等待：" + "、".join(blocker_tuple)
                )
                self.statusBar().showMessage(
                    "已暫停關閉：" + "、".join(blocker_tuple)
                    + "；目前仍在安全收尾，完成後會自動關閉。"
                )
            elif (
                self._shutdown_close_last_diagnostic_monotonic is None
                or now - self._shutdown_close_last_diagnostic_monotonic >= 5.0
            ):
                self._shutdown_close_last_diagnostic_monotonic = now
                started = self._shutdown_close_started_monotonic
                elapsed = now - started if started is not None else 0.0
                MainWindow._record_shutdown_diagnostic(
                    self,
                    "still_waiting",
                    elapsed_seconds=elapsed,
                    worker_count=len(remaining_workers),
                    background_process_running=background_process_running,
                )
                MainWindow._record_shutdown_message(
                    self,
                    "主視窗關閉仍在等待（UI event loop 持續運作）："
                    f"elapsed={elapsed:.1f}s，原因=" + "、".join(blocker_tuple),
                )
                self.statusBar().showMessage(
                    f"已暫停關閉 {elapsed:.0f} 秒：" + "、".join(blocker_tuple)
                    + "；介面仍在等待安全收尾，完成後會自動關閉。"
                )
            return

        timer = getattr(self, "_shutdown_close_timer", None)
        if timer is not None:
            timer.stop()
        self._shutdown_close_finalizing = True
        started = self._shutdown_close_started_monotonic
        elapsed = time.monotonic() - started if started is not None else 0.0
        MainWindow._record_shutdown_message(
            self,
            f"主視窗背景工作已安全收尾，關閉耗時 {elapsed:.3f} 秒；自動完成 close。",
        )
        MainWindow._record_shutdown_diagnostic(
            self,
            "workers_finished",
            elapsed_seconds=elapsed,
            worker_count=0,
            background_process_running=False,
        )
        self.statusBar().showMessage("背景工作已安全收尾，正在關閉…", 3_000)
        QTimer.singleShot(0, self.close)

    def closeEvent(self, event):
        """一次 X 請求合作式取消，完成後自動關閉，不要求再次按 X。"""

        if getattr(self, "_shutdown_close_finalizing", False):
            timer = getattr(self, "_shutdown_close_timer", None)
            if timer is not None:
                timer.stop()
            event.accept()
            return

        first_request = not getattr(self, "_shutdown_close_requested", False)
        if first_request:
            self._shutdown_close_requested = True
            self._shutdown_close_started_monotonic = time.monotonic()
            self._shutdown_close_last_blockers = ()
            self._shutdown_close_last_diagnostic_monotonic = None
            MainWindow._record_shutdown_diagnostic(self, "requested")
            MainWindow._freeze_child_refresh_sources(self)

            research_workspace = getattr(self, "stock_research_workspace", None)
            request_report_close = getattr(research_workspace, "request_close", None)
            if callable(request_report_close):
                request_report_close()
            # MainWindow 的 closeEvent 不會可靠地逐一傳遞到子 QWidget；
            # _freeze_child_refresh_sources 已撤銷 Portfolio／每日決策頁的
            # pending generation，避免全域取消目前一輪後又補起下一輪。

        remaining_workers, background_process_running = (
            MainWindow._request_shutdown_dependencies(self, send_cancel=first_request)
        )
        if first_request:
            MainWindow._record_shutdown_diagnostic(
                self,
                "cancel_requested",
                elapsed_seconds=0.0,
                worker_count=len(remaining_workers),
                background_process_running=background_process_running,
            )
        if remaining_workers or background_process_running:
            MainWindow._set_shutdown_ui(self)
            parts: list[str] = []
            if remaining_workers:
                parts.append(f"{len(remaining_workers)} 個合作式取消中的背景工作")
            if background_process_running:
                parts.append("TPEX 背景更新程序（等待安全收尾）")
            blocker_tuple = tuple(parts)
            self._shutdown_close_last_blockers = blocker_tuple
            self.statusBar().showMessage(
                "已暫停關閉：" + "、".join(parts) + "；完成後將自動關閉。",
                10_000,
            )
            MainWindow._record_shutdown_message(
                self, "主視窗收到 close request，已進入合作式收尾：" + "、".join(parts)
            )
            timer = getattr(self, "_shutdown_close_timer", None)
            if timer is not None:
                timer.start()
            event.ignore()
            return

        self._shutdown_close_finalizing = True
        timer = getattr(self, "_shutdown_close_timer", None)
        if timer is not None:
            timer.stop()
        started = self._shutdown_close_started_monotonic
        elapsed = time.monotonic() - started if started is not None else 0.0
        MainWindow._record_shutdown_message(
            self, f"主視窗閒置關閉耗時 {elapsed:.3f} 秒；沒有背景依賴。"
        )
        MainWindow._record_shutdown_diagnostic(
            self,
            "accepted_idle_close",
            elapsed_seconds=elapsed,
            worker_count=0,
            background_process_running=False,
        )
        event.accept()


_startup_controller = None


def _startup_step(label: str) -> None:
    if _startup_controller is not None:
        _startup_controller.step(label)


def _cleanup_startup(app, controller) -> None:
    """不顯示半成品視窗，沿既有合作式關閉流程等待 worker 結束。"""
    window = controller.window
    controller.dismiss()
    if window is None:
        return
    window.hide()
    window.close()
    if not getattr(window, "_shutdown_close_finalizing", True):
        timer = QTimer()
        timer.setInterval(50)
        timer.timeout.connect(lambda: app.quit() if window._shutdown_close_finalizing else None)
        timer.start()
        app.exec()
        timer.stop()
    _drain_qt_deferred_deletes(app, (window,))


def main(*, application_settings: ApplicationSettings | None = None,
         build_identity: BuildIdentity | None = None, startup_controller=None):
    """由共同 launcher 注入設定、來源身分與啟動進度。"""
    import traceback
    global _startup_controller, _crash_diagnostics_log_path
    if application_settings is None:
        from baldr_launcher import initialize_application
        application_settings = initialize_application()
    if build_identity is None:
        build_identity = detect_build_identity(repository_root=application_settings.resource_root)
    previous_startup = _startup_controller
    _startup_controller = startup_controller
    _crash_diagnostics_log_path = install_crash_diagnostics()

    _configure_console_streams()
    print("[Main] 開始啟動應用程序...")
    if _crash_diagnostics_log_path is not None:
        print(f"[Main] Crash diagnostics: {_crash_diagnostics_log_path}")

    try:
        print("[Main] 正在創建 QApplication...")
        app = QApplication.instance() or QApplication(sys.argv)
        app.setOrganizationName("TechnicalAnalysis")
        app.setApplicationName("TechnicalAnalysis")
        print("[Main] QApplication 創建成功")

        # 設置應用程序 icon（必須在創建窗口之前設置）
        icon_path = application_settings.resource_root / "ui_qt" / "app_icon.png"
        if icon_path.exists():
            icon_path_abs = icon_path.resolve()  # 使用絕對路徑
            app.setWindowIcon(QIcon(str(icon_path_abs)))
            print(f"[Main] 應用程序 icon 設置完成: {icon_path_abs}")
        else:
            print(f"[Main] 警告: Icon 檔案不存在: {icon_path}")

        # 設置應用程序樣式（可選）
        apply_app_theme(app)
        print("[Main] Midnight Analyst 樣式設置完成")

        # 創建主窗口
        try:
            print("[Main] 正在創建主窗口...")
            window = MainWindow(application_settings=application_settings, build_identity=build_identity)
            if not application_settings.configured:
                from PySide6.QtCore import QTimer
                def show_first_setup() -> None:
                    box = QMessageBox(window)
                    box.setWindowTitle("baldr 首次資料設定")
                    box.setText(
                        f"目前使用空資料根：{application_settings.environment['DATA_ROOT']}\n"
                        f"請在 {application_settings.config_path} 明示 DATA_ROOT 與 OUTPUT_ROOT 後重開。\n"
                        "私人資料與模型請沿原設定成對選定；未設定不會自動啟用。"
                    )
                    box.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
                    box.show()
                QTimer.singleShot(250, show_first_setup)
            print("[Main] 主窗口創建成功")

            print("[Main] 正在顯示主窗口...")
            if _startup_controller is not None:
                _startup_controller.ready(window)
            else:
                window.show()
            print("[Main] 主窗口顯示成功")

            print("[Main] 應用程序準備就緒，進入事件循環...")
        except Exception as e:
            from ui_qt.startup_view import StartupCancelled
            if _startup_controller is not None:
                _cleanup_startup(app, _startup_controller)
            if isinstance(e, StartupCancelled):
                return 0
            record_exception("main_window_initialization", e)
            print(f"[Main] 錯誤：創建主窗口失敗")
            print(f"[Main] 錯誤類型: {type(e).__name__}")
            print(f"[Main] 錯誤訊息: {str(e)}")
            print(f"[Main] 詳細堆疊追蹤:\n{traceback.format_exc()}")
            return 1

        # 運行應用程序
        record_diagnostic("qapplication_exec_started")
        print("[Main] 開始運行應用程序事件循環...")
        exit_code = app.exec()
        record_diagnostic("qapplication_exec_returned", exit_code=exit_code)
        print(f"[Main] 應用程序退出，退出碼: {exit_code}")
        # closeEvent 只會隱藏／接受主視窗；若把 QObject 留到 Python
        # interpreter shutdown，PySide6／Qt6 可能在 native teardown 卡住。
        _drain_qt_deferred_deletes(app, (window,))
        return int(exit_code)
    except Exception as e:
        record_exception("application_startup", e)
        if _startup_controller is not None:
            _cleanup_startup(app, _startup_controller)
        print(f"[Main] 錯誤：應用程序啟動失敗")
        print(f"[Main] 錯誤類型: {type(e).__name__}")
        print(f"[Main] 錯誤訊息: {str(e)}")
        print(f"[Main] 詳細堆疊追蹤:\n{traceback.format_exc()}")
        return 1
    finally:
        _startup_controller = previous_startup


if __name__ == "__main__":
    raise SystemExit(main())
