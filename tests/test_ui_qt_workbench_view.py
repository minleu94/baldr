import os
import sys
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path
from threading import Event, current_thread
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent, QThread, Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QAbstractItemView, QBoxLayout, QWidget
import shiboken6

from app_module.workbench_dtos import (
    ManualSavedResearchLaneDTO,
    WorkbenchAccessBoundary,
    WorkbenchActionItem,
    WorkbenchChecklistItem,
    WorkbenchDashboardDTO,
    WorkbenchEvidenceFeedItem,
    WorkbenchEvidenceSummary,
    WorkbenchOperatingLoopStep,
    WorkbenchReviewItem,
    WorkbenchStatusItem,
    WorkbenchDailyEvidence,
)
from app_module.engineering_closure_dashboard_service import (
    EngineeringClosureDashboardService,
    EvidenceRehearsalDashboard,
)
from app_module.evidence_rehearsal_dtos import (
    CoverageMetric,
    EvidenceRehearsalReport,
    EvidenceRehearsalScenario,
    RehearsalArtifact,
)
from app_module.advice_dtos import (
    AdviceAction,
    AdviceClassification,
    AdviceDashboardDTO,
    AdviceMode,
    AdvicePolicyConfig,
    RecommendationAdviceDTO,
)
from ui_qt.models.workbench_table_models import (
    AdviceRecommendationTableModel,
    WorkbenchActionItemTableModel,
    WorkbenchEvidenceFeedTableModel,
    WorkbenchEvidenceTableModel,
    WorkbenchOperatingLoopTableModel,
    _is_attention_status,
    _status_tone,
)
import ui_qt.models.workbench_table_models as workbench_table_models
from ui_qt.views.workbench_view import (
    UnifiedDecisionWorkbenchView,
    WORKBENCH_TONES,
    _advice_contract_completeness,
    _localize_workbench_text,
    _workbench_tone,
)
from ui_qt.views.research_console_view import ResearchConsoleView
from ui_qt.theme.tokens import MIDNIGHT_ANALYST


def app():
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication(sys.argv)
    return instance


def test_evidence_subtab_hosts_read_only_research_console() -> None:
    app()
    view = UnifiedDecisionWorkbenchView(auto_refresh=False)

    evidence_page = view.subtabs.widget(2)
    assert isinstance(evidence_page, ResearchConsoleView)
    assert evidence_page.visible_text().count("formal_oos_allowed = False") == 1


def test_workbench_localizes_verified_advice_payload_hash_label() -> None:
    localized = _localize_workbench_text("canonical_payload_sha256:" + "a" * 64)

    assert localized == "已核驗保存結果 payload SHA-256：" + "a" * 64


def test_manual_saved_research_lane_is_separate_and_survives_dashboard_refresh() -> None:
    app()
    advice = AdviceDashboardDTO(
        decision_date="2026-09-08",
        data_as_of_date="2026-09-07",
        mode=AdviceMode.PROFESSIONAL,
        policy=AdvicePolicyConfig(mode=AdviceMode.PROFESSIONAL),
        recommendations=(
            RecommendationAdviceDTO(
                stock_code="2330",
                advice_action=AdviceAction.RESEARCH,
                decision_date="2026-09-08",
                data_as_of_date="2026-09-07",
                why_reasons=("saved reason",),
                why_not_reasons=("not promoted",),
                risk_reasons=("source limits",),
                source_trace=("manual-result-1",),
            ),
        ),
        warnings=("saved historical result",),
    )
    lane = ManualSavedResearchLaneDTO(
        result_id="manual-result-1",
        payload_sha256="sha256:" + "a" * 64,
        decision_date="2026-09-08",
        data_as_of_date="2026-09-07",
        strategy_version="strategy-v1",
        advice_dashboard=advice,
    )
    view = UnifiedDecisionWorkbenchView(auto_refresh=False)

    view.set_manual_saved_research_lane(lane)
    assert not view.manual_research_panel.isHidden()
    assert "原決策日：2026-09-08" in view.manual_research_text.toPlainText()
    assert "不代表今日排程建議" in view.manual_research_text.toPlainText()
    assert "saved reason" in view.manual_research_text.toPlainText()
    assert "所選保存結果 Advice" in view.manual_research_section_title.text()

    dashboard = _dashboard_with_replay()
    scheduled_advice = dashboard.advice_dashboard
    view.render_dashboard(dashboard)
    assert dashboard.advice_dashboard is scheduled_advice
    assert not view.manual_research_panel.isHidden()
    assert "manual-result-1" in view.manual_research_text.toPlainText()

    view.set_manual_saved_research_lane(None)
    assert view.manual_research_panel.isHidden()


def test_advice_detail_marks_author_fields_optional_and_does_not_fill_them() -> None:
    summary = _advice_contract_completeness(
        RecommendationAdviceDTO(stock_code="2330", advice_action=AdviceAction.RESEARCH)
    )

    assert "Advice 證據欄位待核對：成立理由、信心層級" in summary
    assert "資料日" in summary
    assert "來源追溯" in summary
    assert "不阻擋 Advice" in summary
    assert "未知或缺少來源的證據不會由排名分數、其他股票或空白欄位代填" in summary


def test_advice_contract_completeness_distinguishes_explicit_unknown_from_missing() -> None:
    summary = _advice_contract_completeness(
        RecommendationAdviceDTO(
            stock_code="2330",
            advice_action=AdviceAction.RESEARCH,
            liquidity_state="UNKNOWN",
            execution_feasibility="UNAVAILABLE",
            source_trace=(),
        )
    )

    assert "流動性狀態" not in summary.splitlines()[0]
    assert "可成交性" not in summary.splitlines()[0]
    assert "來源追溯" in summary
    assert "策略版本選填說明未提供" in summary
    assert "這些欄位不阻擋 Advice" in summary
    assert "明確未知／未提供欄位仍是限制：流動性狀態、可成交性" in summary


def test_advice_contract_completeness_rejects_source_kind_without_identity() -> None:
    summary = _advice_contract_completeness(
        RecommendationAdviceDTO(
            stock_code="2330",
            advice_action=AdviceAction.RESEARCH,
            source_trace=("RecommendationResultDTO",),
        )
    )

    assert "來源追溯" in summary


def test_advice_contract_completeness_accepts_known_negative_states_with_trace() -> None:
    summary = _advice_contract_completeness(
        RecommendationAdviceDTO(
            stock_code="2330",
            advice_action=AdviceAction.AVOID,
            why_reasons=("observed_gate_failure",),
            confidence_tier="low",
            evidence_tier="insufficient",
            data_quality="MISSING",
            strategy_version="v2.1",
            decision_date="2026-10-26",
            data_as_of_date="2026-10-25",
            holding_horizon="5 sessions",
            entry_thesis="觀察候選條件",
            invalidation_conditions=("close_below_support",),
            review_cadence="daily",
            market_regime="neutral",
            liquidity_state="GATE_FAIL",
            execution_feasibility="NOT_FEASIBLE",
            source_trace=("RecommendationResultDTO", "result-123"),
        )
    )

    assert "Advice 核心欄位與來源追溯可判讀" in summary


def test_advice_contract_completeness_accepts_explicit_unavailable_confidence() -> None:
    summary = _advice_contract_completeness(
        RecommendationAdviceDTO(
            stock_code="2330",
            advice_action=AdviceAction.RESEARCH,
            why_not_reasons=("source_not_accepted",),
            confidence_tier="unavailable",
            evidence_tier="insufficient",
            data_quality="ESTIMATED",
            strategy_version="candidate-v1",
            decision_date="2026-10-28",
            data_as_of_date="2026-10-28",
            market_regime="neutral",
            liquidity_state="GATE_FAIL",
            execution_feasibility="NOT_FEASIBLE",
            source_trace=("RecommendationResultDTO", "result-123"),
            source_result_id="result-123",
        )
    )

    assert "Advice 核心欄位與來源追溯可判讀" in summary
    assert "Advice 證據欄位待核對" not in summary
    assert "策略版本選填說明未提供" in summary
    assert "決策信心不可用" in summary
    assert "不可解讀為勝率" in summary


def test_advice_does_not_require_account_connection_or_offer_account_source_gate() -> None:
    app()
    navigations: list[str] = []
    view = UnifiedDecisionWorkbenchView(
        auto_refresh=False,
        navigate_to_portfolio_callback=lambda: navigations.append("portfolio"),
    )
    view._set_advice_state(
        "NO_ELIGIBLE_ADVICE",
        "strategy_candidate_research_only",
        warnings=(
            "策略建議不需要連接真實帳戶；持倉與交易由使用者手動記錄。",
        ),
    )
    view.show()
    app().processEvents()

    assert "不需要連接真實帳戶" in view.advice_warning_status.text()
    assert not hasattr(view, "advice_account_source_button")
    assert navigations == []
    view.close()


def test_workbench_advice_loading_empty_and_error_states_keep_plain_language_and_diagnostics() -> None:
    app()
    view = UnifiedDecisionWorkbenchView(auto_refresh=False)

    view._set_advice_state("WAITING_FOR_ADVICE_DTO")
    waiting_text = view.advice_empty_label.text()
    assert "尚未載入今日策略建議" in waiting_text
    assert "WAITING_FOR_ADVICE_DTO" not in waiting_text
    assert "AdviceDashboardDTO" not in view.advice_summary.text()
    assert "重新整理狀態" in waiting_text
    assert not view.advice_technical_diagnostics_button.isHidden()
    assert view.advice_technical_diagnostics_text.isHidden()

    view.advice_technical_diagnostics_button.click()
    assert not view.advice_technical_diagnostics_text.isHidden()
    assert "狀態代碼：WAITING_FOR_ADVICE_DTO" in view.advice_technical_diagnostics_text.toPlainText()
    assert view.advice_technical_diagnostics_button.text() == "隱藏技術診斷"

    source_warning = "策略候選需回查來源保存狀態"
    raw_diagnostic = "candidate_query_empty:source_id=example-1"
    view._set_advice_state(
        "NO_ELIGIBLE_ADVICE",
        raw_diagnostic,
        warnings=(source_warning,),
    )
    empty_text = view.advice_empty_label.text()
    assert "本次沒有可顯示的建議" in empty_text
    assert "NO_ELIGIBLE_ADVICE" not in empty_text
    assert "DTO" not in empty_text
    assert source_warning in empty_text
    assert raw_diagnostic not in empty_text
    assert source_warning in view.advice_warning_status.text()
    assert view.advice_technical_diagnostics_button.isChecked() is False
    assert view.advice_technical_diagnostics_text.isHidden()

    view.advice_technical_diagnostics_button.click()
    empty_diagnostics = view.advice_technical_diagnostics_text.toPlainText()
    assert "狀態代碼：NO_ELIGIBLE_ADVICE" in empty_diagnostics
    assert raw_diagnostic in empty_diagnostics
    assert view.advice_recommendation_model.rowCount() == 0
    assert view.advice_candidate_model.rowCount() == 0
    assert view.advice_portfolio_model.rowCount() == 0

    raw_error = "OSError: permission denied while reading saved recommendation"
    view._set_advice_state("ADVICE_DTO_ERROR", raw_error)
    error_text = view.advice_empty_label.text()
    assert "無法載入策略建議" in error_text
    assert "ADVICE_DTO_ERROR" not in error_text
    assert raw_error not in error_text
    assert "重新整理狀態" in error_text
    assert "技術診斷" in error_text
    assert "讀取失敗；舊建議已清除" in view.advice_summary.text()
    assert not view.advice_technical_diagnostics_button.isChecked()
    assert view.advice_technical_diagnostics_text.isHidden()
    assert view.advice_warning_status.text() == "警告狀態：載入失敗，舊警告已清除。"

    view.advice_technical_diagnostics_button.click()
    error_diagnostics = view.advice_technical_diagnostics_text.toPlainText()
    assert "狀態代碼：ADVICE_DTO_ERROR" in error_diagnostics
    assert raw_error in error_diagnostics
    assert "收合本次 Advice 狀態" in view.advice_technical_diagnostics_button.accessibleDescription()
    view.close()


def _dashboard_with_replay() -> WorkbenchDashboardDTO:
    return WorkbenchDashboardDTO(
        as_of_date=date(2026, 7, 6),
        generated_at=datetime(2026, 7, 6, 12, 0, 0),
        source_mode="read_only_sources_plus_historical_replay",
        access_boundary=WorkbenchAccessBoundary(),
        status_strip=(
            WorkbenchStatusItem(
                item_id="decision_snapshot",
                label="Daily Decision snapshot",
                value="2026-07-06",
                status="observed",
                summary="Read from WorkbenchSourceService.",
            ),
            WorkbenchStatusItem(
                item_id="evidence_gate",
                label="Evidence gate",
                value="waiting_for_time",
                status="info",
            ),
            WorkbenchStatusItem(
                item_id="scheduler",
                label="Production Scheduler",
                value="off",
                status="blocked",
                summary="production_scheduler_allowed=false",
            ),
        ),
        review_items=(
            WorkbenchReviewItem(
                item_id="watchlist_trigger",
                title="Watchlist trigger review",
                severity="warning",
                source="watchlist_trigger",
                summary="Human review required; no buy/sell recommendation is generated.",
                drilldown_target="evidence_mode",
                code="2603",
            ),
        ),
        evidence_summary=(
            WorkbenchEvidenceSummary(
                item_id="weekly_history",
                label="Weekly evidence operations history",
                status="waiting_for_time",
                summary="0/3 records observed.",
                diagnostics=("insufficient_weekly_history_records",),
            ),
            WorkbenchEvidenceSummary(
                item_id="historical_replay",
                label="Historical replay simulated evidence",
                status="degraded",
                summary=(
                    "118 days / 118056 events / 472224 outcomes; "
                    "source gap disclosed; payload gap disclosed; benchmark coverage disclosed."
                ),
                diagnostics=(
                    "simulated_scheduler",
                    "source_gap:source_missing_screening_matrix",
                    "source_gap_coverage:source_missing_screening_matrix=118/118",
                    "payload_gap:missing_industry_benchmark",
                    "outcome_maturity:ready=380736,pending_future_data=91488",
                    "benchmark_coverage:covered=380736,total=380736,missing=0",
                    "industry_benchmark_coverage:covered=2245,total=380736,missing=378491",
                    "missing_industry_benchmark:378491",
                    "pending_future_data:91488",
                    "replay_direction_assessment:market_benchmark_ready_but_industry_and_source_gaps_block_production_readiness",
                    "phase0_gate_not_satisfied:weekly_history_and_multi_day_dry_run_require_real_time_accumulation",
                ),
            ),
        ),
        market_context={"source_status": "ready", "overall_quality": "observed"},
        portfolio_watchlist_summary={"source_status": "ready"},
        daily_checklist=(
            WorkbenchChecklistItem(
                item_id="weekly_history",
                label="Phase 0 weekly history",
                status="waiting_for_time",
                summary="0/3; must accumulate in real time.",
            ),
            WorkbenchChecklistItem(
                item_id="multi_day_dry_run",
                label="Multi-day dry-run",
                status="waiting_for_time",
                summary="1/3; replay cannot replace this gate.",
            ),
            WorkbenchChecklistItem(
                item_id="scheduler_off",
                label="Scheduler write-mode",
                status="blocked",
                summary="Production scheduler remains off.",
            ),
        ),
        warnings=(
            "historical_replay / simulated_scheduler only supports design review.",
            "replay does not satisfy Phase 0 weekly or multi-day gates.",
            "degraded_source:decision_desk_snapshot_db_missing",
        ),
        background_evidence_feed=(
            WorkbenchEvidenceFeedItem(
                item_id="daily_decision_snapshot",
                label="Daily Decision snapshot",
                status="observed",
                summary="Snapshot payload already supplied by WorkbenchDashboardDTO.",
                source_trace="DecisionDeskSnapshot",
                degraded_reason="none",
                drilldown_target="daily_decision",
            ),
            WorkbenchEvidenceFeedItem(
                item_id="replay_summary_diagnostics",
                label="Replay summary diagnostics",
                status="degraded",
                summary="Replay summary exposes simulated scheduler and payload gaps.",
                source_trace="HistoricalReplaySummary",
                degraded_reason="missing_industry_benchmark",
                drilldown_target="evidence_review",
                diagnostics=("simulated_scheduler", "missing_industry_benchmark"),
            ),
        ),
        action_items=(
            WorkbenchActionItem(
                item_id="portfolio_alert_2330",
                title="Portfolio alert manual review",
                source_type="portfolio_alert",
                severity="warning",
                summary="Human review required; no action is applied.",
                source_trace="DecisionDeskSnapshot.portfolio_alerts",
                degraded_reason="portfolio_alert_requires_manual_review",
                drilldown_target="portfolio_review",
                code="2330",
            ),
        ),
        operating_loop_steps=(
            WorkbenchOperatingLoopStep(
                step_id="daily_start",
                label="每日先看",
                cadence="daily",
                status="manual_required",
                summary="今天先看 1 筆 review item；只讀，不寫 DB。",
                source_trace="WorkbenchDashboardDTO.review_items",
                linked_item_ids=("watchlist_trigger",),
                drilldown_target="daily_decision",
                guidance="先判讀今日待判讀與背景證據流。",
            ),
            WorkbenchOperatingLoopStep(
                step_id="manual_queue",
                label="人工處理佇列",
                cadence="daily",
                status="manual_required",
                summary="目前有 1 筆 Action Item 需要人工覆盤；不標記完成。",
                source_trace="WorkbenchDashboardDTO.action_items",
                linked_item_ids=("portfolio_alert_2330",),
                drilldown_target="portfolio_review",
                guidance="只檢查 source trace 與 degraded reason。",
            ),
            WorkbenchOperatingLoopStep(
                step_id="multi_day_dry_run",
                label="多日 dry-run",
                cadence="daily_until_3",
                status="waiting_for_time",
                summary="1/3；等待真實時間累積，replay 不可補齊。",
                source_trace="PreV2ReadinessReport.items.multi_day_dry_run",
                linked_item_ids=("multi_day_dry_run",),
                drilldown_target="evidence_review",
                guidance="只確認紀錄節奏，不執行 replay。",
            ),
            WorkbenchOperatingLoopStep(
                step_id="manual_review_note",
                label="人工覆盤註記",
                cadence="after_manual_review",
                status="manual_required",
                summary="手動在既有流程留下 note；Workbench 不寫 DB、不標記完成。",
                source_trace="WorkbenchDashboardDTO.daily_checklist.manual_review_note",
                linked_item_ids=("manual_review_note",),
                drilldown_target="evidence_review",
                guidance="需要 note 時下鑽到既有頁面處理。",
            ),
        ),
    )


def _empty_dashboard() -> WorkbenchDashboardDTO:
    return WorkbenchDashboardDTO(
        as_of_date=date(2026, 7, 6),
        generated_at=datetime(2026, 7, 6, 12, 0, 0),
        source_mode="read_only_sources",
        access_boundary=WorkbenchAccessBoundary(),
        status_strip=(
            WorkbenchStatusItem(
                item_id="scheduler",
                label="Production Scheduler",
                value="off",
                status="blocked",
                summary="production_scheduler_allowed=false",
            ),
        ),
        review_items=(),
        evidence_summary=(),
        market_context={"source_status": "missing"},
        portfolio_watchlist_summary={"source_status": "missing"},
        daily_checklist=(
            WorkbenchChecklistItem(
                item_id="scheduler_off",
                label="Scheduler write-mode",
                status="blocked",
                summary="Production scheduler remains off.",
            ),
        ),
        warnings=(),
        background_evidence_feed=(),
        action_items=(),
    )


class _FakeWorkbenchSourceService:
    def __init__(self, dashboard: WorkbenchDashboardDTO) -> None:
        self.dashboard = dashboard
        self.calls: list[dict[str, object]] = []
        self.thread_names: list[str] = []

    def inspect(self, **kwargs):
        self.calls.append(kwargs)
        self.thread_names.append(current_thread().name)
        return self.dashboard


class _FlakyWorkbenchSourceService:
    def __init__(self, dashboard: WorkbenchDashboardDTO) -> None:
        self.dashboard = dashboard
        self.calls = 0

    def inspect(self, **kwargs):
        self.calls += 1
        if self.calls > 1:
            raise RuntimeError()
        return self.dashboard


class _AlwaysFailWorkbenchSourceService:
    def inspect(self, **kwargs):
        raise RuntimeError()


class _RetryableWorkbenchSourceService:
    def __init__(self, dashboard: WorkbenchDashboardDTO) -> None:
        self.dashboard = dashboard
        self.calls = 0

    def inspect(self, **kwargs):
        self.calls += 1
        if self.calls == 2:
            raise RuntimeError("temporary fixture failure")
        return self.dashboard


class _LatestDateWorkbenchSourceService:
    def __init__(self, dashboard: WorkbenchDashboardDTO) -> None:
        self.dashboard = dashboard
        self.requested_dates: list[str | None] = []
        self.first_call_started = Event()
        self.release_first_call = Event()

    def inspect(self, **kwargs):
        requested_date = kwargs.get("decision_date")
        self.requested_dates.append(requested_date)
        if len(self.requested_dates) == 1:
            self.first_call_started.set()
            if not self.release_first_call.wait(timeout=2.0):
                raise TimeoutError("first Workbench date fixture was not released")
        if requested_date is None:
            return self.dashboard
        return replace(self.dashboard, as_of_date=date.fromisoformat(requested_date))


class _BlockingWorkbenchSourceService:
    def __init__(self, dashboard: WorkbenchDashboardDTO) -> None:
        self.dashboard = dashboard
        self.calls = 0
        self.started = Event()
        self.release = Event()

    def inspect(self, **kwargs):
        self.calls += 1
        self.started.set()
        if not self.release.wait(timeout=2.0):
            raise TimeoutError("blocked Workbench inspect fixture was not released")
        return self.dashboard


def _wait_until(
    predicate,
    timeout_ms: int = 2_000,
    message: str = "condition timed out",
) -> None:
    deadline = time.monotonic() + timeout_ms / 1_000
    while time.monotonic() < deadline:
        app().processEvents()
        if predicate():
            app().processEvents()
            return
        QTest.qWait(10)
    pytest.fail(message)


def _wait_for_workbench_calls(
    view: UnifiedDecisionWorkbenchView,
    service: object,
    expected_calls: int,
    timeout_ms: int = 2_000,
) -> None:
    def call_count() -> int:
        value = getattr(service, "requested_dates", None)
        if value is None:
            value = getattr(service, "calls", [])
        return len(value) if hasattr(value, "__len__") else int(value)

    _wait_until(
        lambda: view._refresh_worker is None
        and not view._refresh_pending
        and call_count() >= expected_calls,
        timeout_ms=timeout_ms,
        message="Workbench refresh/call queue did not settle",
    )


def _observe_view_callbacks_on_gui_thread(
    view,
    names: tuple[str, ...],
    observations: dict[str, list[bool]],
) -> None:
    for name in names:
        original = getattr(view, name)

        def record(*args, _original=original, _name=name, **kwargs):
            observations[_name].append(QThread.currentThread() == view.thread())
            return _original(*args, **kwargs)

        setattr(view, name, record)


def _drain_deferred_deletes() -> None:
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app().processEvents()


def _dispose_workbench_view(view: UnifiedDecisionWorkbenchView) -> None:
    view.begin_shutdown()
    deadline = time.monotonic() + 3.0
    while view._refresh_worker is not None and time.monotonic() < deadline:
        app().processEvents()
        QTest.qWait(10)
    view.close()
    view.deleteLater()
    _drain_deferred_deletes()


def test_workbench_evidence_table_model_has_no_diagnostics_column() -> None:
    app()
    replay = _dashboard_with_replay().evidence_summary[1]
    model = WorkbenchEvidenceTableModel((replay,))

    assert model.rowCount() == 1
    visible_fields = tuple(field for field, _label in model.COLUMNS)
    assert visible_fields == ("label", "status", "summary")


def test_market_card_keeps_missing_kpis_unknown_without_filling_zeros() -> None:
    app()
    dashboard = replace(
        _dashboard_with_replay(),
        market_context={"source_status": "partial", "market_breadth": {"quality": "missing"}},
    )
    view = UnifiedDecisionWorkbenchView(dashboard=dashboard, auto_refresh=False)
    try:
        assert view.daily_market_card.value_label.text() == "市場資料部分可用"
        assert all(label.text() == "—" for label in view.daily_market_kpi_labels.values())
        assert view.daily_market_footer_label.text() == "資料日 未提供｜品質 資料缺件｜來源 部分可用（資料缺件）"
    finally:
        _dispose_workbench_view(view)


def test_workbench_refresh_preserves_last_good_dashboard_as_stale_and_focuses_retry() -> None:
    app()
    dashboard = _dashboard_with_replay()
    view = UnifiedDecisionWorkbenchView(
        source_service=_FlakyWorkbenchSourceService(dashboard),
        dashboard=dashboard,
        auto_refresh=False,
    )

    view.refresh_dashboard()
    view.refresh_dashboard()

    assert view._dashboard is dashboard
    assert view.review_model.rowCount() == 1
    assert "stale" in view.priority_banner.text()
    assert "最後成功載入" in view.priority_banner.text()
    assert "不把舊資料當成 current" in view.priority_banner.text()
    assert "workbench_source_stale" in view.warning_list.toPlainText()
    assert view.refresh_button.focusPolicy().value != 0


def test_home_cards_reflow_without_reading_sources_or_losing_unknown_state() -> None:
    application = app()
    dashboard = _empty_dashboard()
    service = _FakeWorkbenchSourceService(dashboard)
    contexts = []
    view = UnifiedDecisionWorkbenchView(
        source_service=service, dashboard=dashboard, auto_refresh=False,
        navigate_to_stock_research_callback=contexts.append,
    )
    view.resize(1200, 900)
    view.show()
    try:
        application.processEvents()
        portfolio = view.guided_priority_rows["portfolio"]
        market = view.guided_priority_rows["market"]
        candidates = view.guided_priority_rows["candidates"]
        assert portfolio.geometry().x() < market.geometry().x()
        assert portfolio.geometry().y() == market.geometry().y()
        assert candidates.geometry().y() > portfolio.geometry().y()
        original_text = view.guided_priority_reason_labels["data"].text()
        assert original_text
        view.resize(740, 900)
        application.processEvents()
        assert portfolio.geometry().x() == market.geometry().x()
        assert portfolio.geometry().y() < market.geometry().y()
        assert view.guided_priority_reason_labels["data"].text() == original_text
        view.home_stock_input.setText("2330")
        view.home_stock_search_button.click()
        assert contexts[0].stock_code == "2330"
        assert contexts[0].source_kind == "explicit_latest_stock_research"
        assert service.calls == []
        assert view._dashboard is dashboard
    finally:
        _dispose_workbench_view(view)


def test_workbench_initial_refresh_failure_is_unknown_and_does_not_claim_human_review() -> None:
    app()
    view = UnifiedDecisionWorkbenchView(
        source_service=_AlwaysFailWorkbenchSourceService(),
        auto_refresh=False,
    )

    view.refresh_dashboard()

    assert "狀態未知" in view.boundary_banner.text()
    assert "不能推定需要人工" in view.action_item_state_label.text()
    assert view.review_model.rowCount() == 0


def test_async_workbench_reads_off_gui_thread_and_renders_on_gui_thread() -> None:
    app()
    dashboard = _dashboard_with_replay()
    service = _FakeWorkbenchSourceService(dashboard)
    view = UnifiedDecisionWorkbenchView(
        source_service=service,
        decision_date="2026-07-06",
        auto_refresh=False,
        async_refresh=True,
    )
    worker = None
    callback_threads: dict[str, list[bool]] = {
        "_on_async_dashboard_finished": [],
        "_on_async_dashboard_thread_finished": [],
    }
    _observe_view_callbacks_on_gui_thread(
        view,
        tuple(callback_threads),
        callback_threads,
    )
    rendered_on_gui_thread: list[bool] = []
    original_render = view.render_dashboard

    def record_render(rendered_dashboard: WorkbenchDashboardDTO) -> None:
        rendered_on_gui_thread.append(QThread.currentThread() == view.thread())
        original_render(rendered_dashboard)

    view.render_dashboard = record_render
    try:
        view.refresh_dashboard()
        worker = view._refresh_worker
        _wait_for_workbench_calls(view, service, expected_calls=1)
        _drain_deferred_deletes()

        assert service.thread_names and all(
            name != "MainThread" for name in service.thread_names
        )
        assert callback_threads["_on_async_dashboard_finished"] == [True]
        assert callback_threads["_on_async_dashboard_thread_finished"] == [True]
        assert rendered_on_gui_thread == [True]
        assert view._dashboard is dashboard
        assert worker is not None and not shiboken6.isValid(worker)
    finally:
        _dispose_workbench_view(view)


def test_async_workbench_keeps_last_good_data_stale_on_error_and_can_retry() -> None:
    app()
    dashboard = _dashboard_with_replay()
    service = _RetryableWorkbenchSourceService(dashboard)
    view = UnifiedDecisionWorkbenchView(
        source_service=service,
        dashboard=dashboard,
        auto_refresh=False,
        async_refresh=True,
    )
    callback_threads: dict[str, list[bool]] = {
        "_on_async_dashboard_error": [],
        "_on_async_dashboard_thread_finished": [],
    }
    _observe_view_callbacks_on_gui_thread(
        view,
        tuple(callback_threads),
        callback_threads,
    )

    try:
        view.refresh_dashboard()
        _wait_for_workbench_calls(view, service, expected_calls=1)
        view.refresh_dashboard()
        _wait_for_workbench_calls(view, service, expected_calls=2)

        assert view._dashboard is dashboard
        assert "stale" in view.priority_banner.text()
        assert "最後成功載入" in view.priority_banner.text()
        assert callback_threads["_on_async_dashboard_error"] == [True]
        assert all(callback_threads["_on_async_dashboard_thread_finished"])

        view.refresh_dashboard()
        _wait_for_workbench_calls(view, service, expected_calls=3)

        assert view._dashboard is dashboard
        assert view._dashboard_stale is False
        assert "workbench_source_stale" not in view.warning_list.toPlainText()
        assert all(callback_threads["_on_async_dashboard_thread_finished"])
    finally:
        _dispose_workbench_view(view)


def test_async_workbench_date_switch_coalesces_to_latest_request() -> None:
    app()
    service = _LatestDateWorkbenchSourceService(_dashboard_with_replay())
    view = UnifiedDecisionWorkbenchView(
        source_service=service,
        decision_date="2026-07-06",
        auto_refresh=False,
        async_refresh=True,
    )
    callback_threads: dict[str, list[bool]] = {
        "_on_async_dashboard_cancelled": [],
        "_on_async_dashboard_finished": [],
        "_on_async_dashboard_thread_finished": [],
    }
    _observe_view_callbacks_on_gui_thread(
        view,
        tuple(callback_threads),
        callback_threads,
    )
    rendered_dates: list[date] = []
    original_render = view.render_dashboard

    def record_render(rendered_dashboard: WorkbenchDashboardDTO) -> None:
        rendered_dates.append(rendered_dashboard.as_of_date)
        original_render(rendered_dashboard)

    view.render_dashboard = record_render
    worker = None
    try:
        view.refresh_dashboard()
        worker = view._refresh_worker
        assert service.first_call_started.wait(timeout=1.0)
        view.decision_date = "2026-07-07"
        view.refresh_dashboard()
        service.release_first_call.set()
        _wait_for_workbench_calls(view, service, expected_calls=2)
        _drain_deferred_deletes()

        assert service.requested_dates == ["2026-07-06", "2026-07-07"]
        assert rendered_dates == [date(2026, 7, 7)]
        assert view._dashboard is not None
        assert view._dashboard.as_of_date == date(2026, 7, 7)
        assert callback_threads["_on_async_dashboard_cancelled"] == [True]
        assert callback_threads["_on_async_dashboard_finished"] == [True]
        assert all(callback_threads["_on_async_dashboard_thread_finished"])
        assert worker is not None and not shiboken6.isValid(worker)
    finally:
        service.release_first_call.set()
        _dispose_workbench_view(view)


def test_async_workbench_shutdown_drops_pending_refresh_without_restart() -> None:
    app()
    dashboard = _dashboard_with_replay()
    service = _BlockingWorkbenchSourceService(dashboard)
    view = UnifiedDecisionWorkbenchView(
        source_service=service,
        auto_refresh=False,
        async_refresh=True,
    )
    cancelled_on_gui_thread: list[bool] = []
    original_cancelled = view._on_async_dashboard_cancelled

    def record_cancelled(generation: int) -> None:
        cancelled_on_gui_thread.append(QThread.currentThread() == view.thread())
        original_cancelled(generation)

    view._on_async_dashboard_cancelled = record_cancelled
    try:
        view.refresh_dashboard()
        assert service.started.wait(timeout=1.0)
        view.refresh_dashboard()
        assert view._refresh_pending is True
        view.begin_shutdown()
        service.release.set()
        _wait_for_workbench_calls(view, service, expected_calls=1)
        _drain_deferred_deletes()

        assert service.calls == 1
        assert view._refresh_pending is False
        assert view._refresh_worker is None
        assert cancelled_on_gui_thread == [True]
        assert view._dashboard is None
    finally:
        service.release.set()
        _dispose_workbench_view(view)


def test_async_workbench_ignores_result_queued_before_shutdown() -> None:
    app()
    dashboard = _dashboard_with_replay()
    service = _BlockingWorkbenchSourceService(dashboard)
    view = UnifiedDecisionWorkbenchView(
        source_service=service,
        auto_refresh=False,
        async_refresh=True,
    )
    worker = None
    rendered: list[WorkbenchDashboardDTO] = []
    original_render = view.render_dashboard

    def record_render(rendered_dashboard: WorkbenchDashboardDTO) -> None:
        rendered.append(rendered_dashboard)
        original_render(rendered_dashboard)

    view.render_dashboard = record_render
    callback_threads: dict[str, list[bool]] = {
        "_on_async_dashboard_finished": [],
        "_on_async_dashboard_thread_finished": [],
    }
    _observe_view_callbacks_on_gui_thread(
        view,
        tuple(callback_threads),
        callback_threads,
    )
    try:
        view.refresh_dashboard()
        worker = view._refresh_worker
        assert service.started.wait(timeout=1.0)
        service.release.set()
        deadline = time.monotonic() + 1.0
        while worker is not None and worker.isRunning() and time.monotonic() < deadline:
            time.sleep(0.001)
        assert worker is not None and not worker.isRunning()
        view.begin_shutdown()
        _wait_for_workbench_calls(view, service, expected_calls=1)
        _drain_deferred_deletes()

        assert callback_threads["_on_async_dashboard_finished"] == [True]
        assert callback_threads["_on_async_dashboard_thread_finished"] == [True]
        assert rendered == []
        assert view._dashboard is None
        assert worker is not None and not shiboken6.isValid(worker)
    finally:
        service.release.set()
        _dispose_workbench_view(view)



def test_workbench_action_item_table_model_is_compact_but_keeps_raw_detail() -> None:
    app()
    action = _dashboard_with_replay().action_items[0]
    model = WorkbenchActionItemTableModel((action,))
    visible_fields = tuple(field for field, _label in model.COLUMNS)

    assert visible_fields == ("queue_group", "severity", "source_label", "title", "summary")
    assert model.rowCount() == 1
    assert model.data(model.index(0, model.column_index("severity"))) == "警告"
    assert model.data(model.index(0, model.column_index("title"))) == "Portfolio alert manual review"
    assert model.raw_value(0, "source_trace") == "DecisionDeskSnapshot.portfolio_alerts"
    assert model.raw_value(0, "degraded_reason") == "portfolio_alert_requires_manual_review"
    assert model.raw_value(0, "drilldown_target") == "portfolio_review"


def test_workbench_portfolio_alert_home_text_is_localized_without_changing_source() -> None:
    app()
    dashboard = _dashboard_with_replay()
    action = dashboard.action_items[0]
    view = UnifiedDecisionWorkbenchView(dashboard=dashboard, auto_refresh=False)
    try:
        reason_label = view.guided_priority_reason_labels["portfolio"]
        reason_tooltip = reason_label.toolTip()
        action_model = view.action_item_model

        assert reason_label.text() == (
            "持倉警示待覆盤；需人工確認；不會套用任何動作。"
        )
        assert reason_tooltip == f"{action.title}；{action.summary}"
        assert action_model.raw_value(0, "title") == action.title
        assert action_model.raw_value(0, "summary") == action.summary
        assert dashboard.action_items[0] is action
        assert action.title == "Portfolio alert manual review"
        assert action.summary == "Human review required; no action is applied."
        candidate_reason = view.guided_priority_reason_labels["candidates"]
        assert "需人工判讀；未產生買賣建議。" in candidate_reason.text()
        assert "Human review required; no buy/sell recommendation is generated." in (
            candidate_reason.toolTip()
        )
    finally:
        _dispose_workbench_view(view)


def test_workbench_portfolio_alert_unknown_home_text_stays_raw() -> None:
    app()
    dashboard = _dashboard_with_replay()
    action = replace(
        dashboard.action_items[0],
        title="Provider alert needs review",
        summary="Provider-specific wording is pending confirmation.",
    )
    dashboard = replace(dashboard, action_items=(action,))
    view = UnifiedDecisionWorkbenchView(dashboard=dashboard, auto_refresh=False)
    try:
        reason_label = view.guided_priority_reason_labels["portfolio"]

        assert reason_label.text() == (
            "Provider alert needs review；Provider-specific wording is pending confirmation."
        )
        assert reason_label.toolTip() == reason_label.text()
        assert view.action_item_model.raw_value(0, "title") == action.title
        assert view.action_item_model.raw_value(0, "summary") == action.summary
    finally:
        _dispose_workbench_view(view)


def test_workbench_evidence_feed_table_model_is_compact_but_keeps_raw_detail() -> None:
    app()
    feed_item = _dashboard_with_replay().background_evidence_feed[1]
    model = WorkbenchEvidenceFeedTableModel((feed_item,))
    visible_fields = tuple(field for field, _label in model.COLUMNS)

    assert visible_fields == ("label", "status", "summary")
    assert model.rowCount() == 1
    assert model.data(model.index(0, model.column_index("status"))) == "降級"
    assert model.row_at(0).source_trace == "HistoricalReplaySummary"
    assert model.row_at(0).degraded_reason == "missing_industry_benchmark"
    assert model.row_at(0).diagnostics == ("simulated_scheduler", "missing_industry_benchmark")


def test_workbench_table_models_apply_semantic_status_colors() -> None:
    app()
    feed_item = _dashboard_with_replay().background_evidence_feed[1]
    model = WorkbenchEvidenceFeedTableModel((feed_item,))
    status_index = model.index(0, model.column_index("status"))
    summary_index = model.index(0, model.column_index("summary"))

    status_brush = model.data(status_index, Qt.ForegroundRole)
    row_background = model.data(summary_index, Qt.BackgroundRole)

    assert isinstance(status_brush, QBrush)
    assert status_brush.color() == QColor(MIDNIGHT_ANALYST.status_warning)
    assert isinstance(row_background, QBrush)
    assert row_background.color() == QColor("#221a10")
    assert model.data(status_index, Qt.FontRole).bold() is True


def test_workbench_status_tones_use_quality_tokens_without_changing_attention() -> None:
    success = _status_tone("ready")
    observed = _status_tone("observed")
    candidate = _status_tone("machine_candidate")
    active_model = _status_tone("active_model")
    degraded = _status_tone("candidate_degraded")
    blocked = _status_tone("future_blocked")
    unknown = _status_tone("unknown")

    assert success["fg"] == MIDNIGHT_ANALYST.status_success
    assert observed["fg"] == MIDNIGHT_ANALYST.status_info
    assert candidate["fg"] == MIDNIGHT_ANALYST.status_info
    assert active_model["fg"] == MIDNIGHT_ANALYST.status_info
    assert degraded["fg"] == MIDNIGHT_ANALYST.status_warning
    assert blocked["fg"] == MIDNIGHT_ANALYST.status_error
    assert unknown["fg"] == "#94a3b8"
    assert observed["fg"] != MIDNIGHT_ANALYST.market_down
    assert blocked["fg"] != MIDNIGHT_ANALYST.market_up
    assert _is_attention_status("machine_candidate") is True
    assert _is_attention_status("observed") is False

    app()
    feed_item = replace(_dashboard_with_replay().background_evidence_feed[1], status="observed")
    model = WorkbenchEvidenceFeedTableModel((feed_item,))
    status_index = model.index(0, model.column_index("status"))
    summary_index = model.index(0, model.column_index("summary"))
    status_brush = model.data(status_index, Qt.ForegroundRole)
    assert status_brush.color() == QColor(MIDNIGHT_ANALYST.status_info)
    assert model.data(summary_index, Qt.BackgroundRole) is None


def test_workbench_view_tones_match_semantic_status_tokens_and_muted_fallback() -> None:
    assert WORKBENCH_TONES["observed"]["fg"] == MIDNIGHT_ANALYST.status_info
    assert WORKBENCH_TONES["manual_observed"]["fg"] == MIDNIGHT_ANALYST.status_info
    assert WORKBENCH_TONES["candidate"]["fg"] == MIDNIGHT_ANALYST.status_info
    assert WORKBENCH_TONES["challenger_candidate"]["fg"] == MIDNIGHT_ANALYST.status_info
    assert WORKBENCH_TONES["active_model"]["fg"] == MIDNIGHT_ANALYST.status_info
    assert WORKBENCH_TONES["ready"]["fg"] == MIDNIGHT_ANALYST.status_success
    assert WORKBENCH_TONES["stale"]["fg"] == MIDNIGHT_ANALYST.status_warning
    assert WORKBENCH_TONES["future_blocked"]["fg"] == MIDNIGHT_ANALYST.status_error
    assert _workbench_tone("unknown")["fg"] == WORKBENCH_TONES["neutral"]["fg"]


def test_workbench_operating_loop_table_model_exposes_read_only_rhythm() -> None:
    app()
    step = _dashboard_with_replay().operating_loop_steps[1]
    model = WorkbenchOperatingLoopTableModel((step,))

    assert model.rowCount() == 1
    assert model.headerData(model.column_index("cadence"), Qt.Horizontal, Qt.DisplayRole) == "節奏"
    assert model.data(model.index(0, model.column_index("status"))) == "需要人工覆盤"
    assert "portfolio_alert_2330" in model.data(model.index(0, model.column_index("linked_item_ids")))
    assert model.data(model.index(0, model.column_index("drilldown_target"))) == "持倉覆盤"
    assert model.raw_value(0, "write_intent") is False


def test_unified_workbench_view_renders_read_only_mvp_shell_and_replay_limits() -> None:
    app()
    clicked: list[str] = []
    view = UnifiedDecisionWorkbenchView(
        dashboard=_dashboard_with_replay(),
        auto_refresh=False,
        navigate_to_daily_decision_callback=lambda: clicked.append("daily"),
        navigate_to_evidence_review_callback=lambda: clicked.append("evidence"),
        navigate_to_portfolio_callback=lambda: clicked.append("portfolio"),
    )

    assert view.status_model.rowCount() == 3
    assert view.review_model.rowCount() == 1
    assert view.evidence_feed_model.rowCount() == 2
    assert view.action_item_model.rowCount() == 1
    assert view.operating_loop_model.rowCount() == 4
    assert view.evidence_model.rowCount() == 2
    assert view.checklist_model.rowCount() == 3
    assert "唯讀邊界" in view.boundary_banner.text()
    assert "不是交易建議" in view.boundary_banner.text()
    assert "不重算 scoring" in view.boundary_banner.text()
    assert view.summary_value_labels["review"].text() == "1 筆"
    assert view.summary_value_labels["action"].text() == "1 筆"
    assert view.summary_value_labels["waiting"].text() == "2 項"
    assert view.summary_value_labels["warning"].text() == "3 則"
    assert "weekly history 0/3" in view.summary_detail_labels["waiting"].text()
    assert "multi-day dry-run 1/3" in view.summary_detail_labels["waiting"].text()
    overview_margins = view.overview_layout.contentsMargins()
    assert overview_margins.left() >= 12
    assert overview_margins.top() >= 12
    assert "狀態列" in view.status_section_title.text()
    assert "今日待判讀" in view.review_section_title.text()
    assert "背景證據流" in view.evidence_feed_section_title.text()
    assert "只讀 Action Items" in view.action_item_section_title.text()
    assert "操作節奏" in view.operating_loop_section_title.text()
    assert "證據與品質" in view.evidence_section_title.text()
    assert "每日檢查清單" in view.checklist_section_title.text()
    assert [view.subtabs.tabText(i) for i in range(view.subtabs.count())] == [
        "總覽",
        "決策來源",
        "研究證據",
        "持倉追蹤",
        "操作節奏",
    ]
    assert view.select_subtab("決策來源") is True
    assert view.subtabs.tabText(view.subtabs.currentIndex()) == "決策來源"
    assert view.daily_decision_button.text() == "開啟市場總覽"
    assert view.evidence_review_button.text() == "開啟證據覆盤"
    assert view.portfolio_button.text() == "開啟持倉管理"
    evidence_page_text = " ".join(
        label.text() for label in view.subtabs.widget(2).findChildren(type(view.boundary_banner))
    )
    assert "Research Console" in evidence_page_text
    assert "formal_oos_allowed = False" in evidence_page_text
    assert "projection_missing" in evidence_page_text

    view.daily_decision_button.click()
    view.evidence_review_button.click()
    view.portfolio_button.click()
    assert clicked == ["daily", "evidence", "portfolio"]

    waiting_tooltip = view.summary_blocks["waiting"].toolTip()
    assert "目前有 2 項仍在等待" in waiting_tooltip
    assert "第 1 週" not in waiting_tooltip
    assert "不可用 fixture" in waiting_tooltip

    boundary_text = view.evidence_boundary_card.value_label.text()
    coverage_text = view.evidence_coverage_card.value_label.text()
    data_quality_text = boundary_text + "\n" + coverage_text

    assert "模擬排程器" in data_quality_text
    assert "來源缺口" in data_quality_text
    assert "payload 缺口" in data_quality_text
    assert "結果成熟度" in data_quality_text
    assert "市場基準覆蓋" in data_quality_text
    assert "產業基準覆蓋" in data_quality_text
    assert "缺產業基準" in data_quality_text
    assert "等待未來資料" in data_quality_text
    assert "方向判讀" in data_quality_text
    assert "Phase 0 每週歷史 0/3" in data_quality_text
    assert "多日 dry-run 1/3" in data_quality_text
    assert "replay 不可取代" in data_quality_text
    assert "降級來源" in view.warning_list.toPlainText()
    loop_text = view.operating_loop_state_label.text()
    assert "今天要看" in loop_text
    assert "人工處理" in loop_text
    assert "等待真實時間累積" in loop_text
    assert "只讀" in loop_text
    assert "不標記完成" in loop_text
    operating_loop_text = " ".join(
        label.text() for label in view.operating_loop_list.findChildren(type(view.boundary_banner))
    )
    assert "需要人工覆盤" in operating_loop_text
    assert "等待真實時間累積" in operating_loop_text
    assert "manual_required" not in operating_loop_text
    assert "waiting_for_time" not in operating_loop_text
    assert "觀察清單觸發" in operating_loop_text
    assert "唯讀邊界" in operating_loop_text
    assert "read-only boundary" not in operating_loop_text

    checklist_text = " ".join(
        label.text() for label in view.checklist_list.findChildren(type(view.boundary_banner))
    )
    assert "封鎖" in checklist_text
    assert "等待真實時間累積" in checklist_text
    assert "blocked" not in checklist_text
    assert "action_required" not in checklist_text
    assert "waiting_for_time" not in checklist_text

    view.warning_list.set_warnings(("source gap warning", "manual waiting"))
    warning_text = " ".join(label.text() for label in view.warning_list.findChildren(type(view.boundary_banner)))
    assert "缺漏來源" in warning_text
    assert "需要人工覆盤" in warning_text
    assert "Missing Source" not in warning_text
    assert "Manual Review Required" not in warning_text


def test_workbench_decision_source_page_is_navigation_only_and_does_not_own_dashboard() -> None:
    app()
    duplicate_dashboard = QWidget()
    duplicate_dashboard.setObjectName("duplicateDecisionDesk")
    clicked: list[str] = []

    view = UnifiedDecisionWorkbenchView(
        dashboard=_dashboard_with_replay(),
        auto_refresh=False,
        decision_source_widget=duplicate_dashboard,
        navigate_to_daily_decision_callback=lambda: clicked.append("market-overview"),
    )

    decision_page = view.subtabs.widget(1)
    page_text = " ".join(
        label.text() for label in decision_page.findChildren(type(view.boundary_banner))
    )
    assert "市場總覽" in page_text
    assert "唯一" in page_text
    assert not hasattr(view, "decision_source_widget")
    assert duplicate_dashboard.parent() is None
    assert view.findChild(QWidget, "duplicateDecisionDesk") is None

    navigation_button = next(
        button
        for button in decision_page.findChildren(type(view.daily_decision_button))
        if button.text() == "開啟市場總覽"
    )
    navigation_button.click()
    assert clicked == ["market-overview"]


def test_unified_workbench_view_renders_blocked_rehearsal_without_ready_claim() -> None:
    app()
    rehearsal_dashboard = EvidenceRehearsalDashboard(
        tier="shadow_comparison",
        status="blocked",
        coverage=(
            CoverageMetric(
                source_id="p0_source",
                total_count=4,
                observed_count=0,
                degraded_count=0,
                missing_count=2,
                future_blocked_count=0,
                immature_label_count=2,
                coverage_bp=0,
            ),
        ),
        blockers=(
            "source_outage:p0_source",
            "insufficient_sample",
            "coverage_missing:p0_source=2",
        ),
    )

    view = UnifiedDecisionWorkbenchView(
        dashboard=_dashboard_with_replay(),
        evidence_rehearsal_dashboard=rehearsal_dashboard,
        auto_refresh=False,
    )

    rehearsal_text = (
        view.evidence_rehearsal_summary_label.text()
        + "\n"
        + view.evidence_rehearsal_detail_label.text()
    )
    assert "工程／Replay／Shadow；不是 forward evidence" in rehearsal_text
    assert "Shadow comparison：有" in rehearsal_text
    assert "Forward handoff：pending" in rehearsal_text
    assert "source_outage:p0_source" in rehearsal_text
    assert "insufficient_sample" in rehearsal_text
    assert "clean" not in rehearsal_text.lower()
    assert "ready" not in rehearsal_text.lower()
    assert "apply" not in rehearsal_text.lower()
    assert "promote" not in rehearsal_text.lower()


@pytest.mark.parametrize(
    "current_status",
    ("outage", "insufficient", "missing", "degraded", "blocked", "insufficient_sample"),
)
def test_unified_workbench_view_renders_status_only_rehearsal_as_blocked(
    current_status: str,
) -> None:
    app()
    rehearsal_report = EvidenceRehearsalReport(
        scenario=EvidenceRehearsalScenario(
            scenario_id=f"{current_status}-rehearsal",
            decision_date="2026-07-13",
            source_db_path="C:/fixture/source.sqlite",
            working_copy_db_path="C:/fixture/working-copy.sqlite",
            tier="engineering_fixture",
        ),
        artifacts=(
            RehearsalArtifact(
                artifact_id=f"artifact-{current_status}",
                decision_date="2026-07-13",
                available_date="2026-07-13",
                tier="engineering_fixture",
                current_status=current_status,
            ),
        ),
    )
    rehearsal_dashboard = EngineeringClosureDashboardService().compose(rehearsal_report)

    view = UnifiedDecisionWorkbenchView(
        dashboard=_dashboard_with_replay(),
        evidence_rehearsal_dashboard=rehearsal_dashboard,
        auto_refresh=False,
    )
    rehearsal_text = (
        view.evidence_rehearsal_summary_label.text()
        + "\n"
        + view.evidence_rehearsal_detail_label.text()
    )

    assert rehearsal_dashboard.status == "blocked"
    assert f"artifact_status:{current_status}" in rehearsal_text
    assert "status：已阻擋" in rehearsal_text
    assert "ready" not in rehearsal_text.lower()


def test_unified_workbench_view_renders_injected_advice_without_source_refresh() -> None:
    app()
    advice = AdviceDashboardDTO(
        decision_date="2026-07-06",
        data_as_of_date="2026-07-06",
        mode=AdviceMode.GUIDED,
        policy=AdvicePolicyConfig(),
        recommendations=(
            RecommendationAdviceDTO(
                stock_code="2330",
                advice_action=AdviceAction.NO_NEW_POSITION,
                confidence_tier="unavailable",
                evidence_tier="insufficient",
                why_not_reasons=("evidence_quality_missing",),
                data_quality="MISSING",
                liquidity_state="UNKNOWN",
                execution_feasibility="NOT_FEASIBLE",
            ),
        ),
    )
    view = UnifiedDecisionWorkbenchView(
        dashboard=replace(_dashboard_with_replay(), advice_dashboard=advice),
        auto_refresh=False,
    )

    assert view.advice_section_title.text() == "今日策略建議"
    assert view.advanced_overview_layout.indexOf(view.advice_panel) == -1
    assert not view.advanced_workbench_panel.isAncestorOf(view.advice_panel)
    assert view.paper_account_context_label.isHidden()
    assert not view.advice_summary_hint.isHidden()
    assert view.advice_recommendation_model.columnCount() == 8
    assert view.advice_recommendation_table.isColumnHidden(
        view.advice_recommendation_model.column_index("data_quality")
    )
    assert view.advice_recommendation_table.isColumnHidden(
        view.advice_recommendation_model.column_index("execution_feasibility")
    )
    view.resize(864, 900)
    view._apply_responsive_layout(force=True)
    assert view.advice_recommendation_table.isColumnHidden(
        view.advice_recommendation_model.column_index("primary_risk")
    )
    assert view.advice_recommendation_table.isColumnHidden(
        view.advice_recommendation_model.column_index("evidence_status")
    )
    view.resize(1280, 900)
    view._apply_responsive_layout(force=True)
    assert not view.advice_recommendation_table.isColumnHidden(
        view.advice_recommendation_model.column_index("primary_risk")
    )
    assert not view.advice_recommendation_table.isColumnHidden(
        view.advice_recommendation_model.column_index("evidence_status")
    )
    assert view.advice_metric_cards["formal"].value_label.text() == "1"
    assert "未回報警告；不能因此推定沒有風險" in view.advice_warning_status.text()
    action_index = view.advice_recommendation_model.index(
        0, view.advice_recommendation_model.column_index("advice_action")
    )
    assert view.advice_recommendation_model.data(action_index) == "暫不新增部位"
    assert view.advice_recommendation_model.data(action_index, Qt.ToolTipRole) == "原始值：NO_NEW_POSITION"
    confidence_index = view.advice_recommendation_model.index(
        0, view.advice_recommendation_model.column_index("confidence_tier")
    )
    assert view.advice_recommendation_model.data(confidence_index) == "不可用"
    assert view.advice_recommendation_model.data(confidence_index, Qt.ToolTipRole) == "原始值：unavailable"
    assert view.advice_recommendation_model.headerData(
        confidence_index.column(), Qt.Horizontal
    ) == "決策信心"
    stock_index = view.advice_recommendation_model.index(
        0, view.advice_recommendation_model.column_index("stock_code")
    )
    assert view.advice_recommendation_model.data(stock_index) == "2330"
    reason_index = view.advice_recommendation_model.index(
        0, view.advice_recommendation_model.column_index("quick_reasons")
    )
    assert view.advice_recommendation_model.data(reason_index) == (
        "支持：未提供｜政策／資格限制：缺少合格證據"
    )
    assert "政策／資格限制：缺少合格證據" in view.advice_recommendation_model.data(
        reason_index, Qt.ToolTipRole
    )
    assert "同股保存來源證據：未提供；不能據此推定沒有反證或風險" in view.advice_recommendation_model.data(
        reason_index, Qt.ToolTipRole
    )
    risk_index = view.advice_recommendation_model.index(
        0, view.advice_recommendation_model.column_index("primary_risk")
    )
    assert view.advice_recommendation_model.data(risk_index) == "未提供額外逐股風險資料"
    assert "不能據此推定沒有風險" in view.advice_recommendation_model.data(
        risk_index, Qt.ToolTipRole
    )
    status_index = view.advice_recommendation_model.index(
        0, view.advice_recommendation_model.column_index("evidence_status")
    )
    assert view.advice_recommendation_model.data(status_index) == (
        "缺漏｜證據成熟度：證據不足｜流動性 Gate：未知｜成交：不可成交｜資料日：未知"
    )
    assert "決策日：未知" in view.advice_recommendation_model.data(
        status_index, Qt.ToolTipRole
    )
    view.advice_recommendation_table.setCurrentIndex(
        view.advice_recommendation_model.index(0, 0)
    )
    assert "策略 Advice（人工判斷與採納）" in view.advice_selection_card.text()
    assert "evidence_quality_missing" in view.advice_selection_card.text()
    assert "證據成熟度：證據不足（原始值：insufficient）" in view.advice_selection_card.text()
    assert "決策信心不可用" in view.advice_selection_card.text()
    assert "證據層級" not in view.advice_selection_card.text()
    assert "失效條件：未提供" in view.advice_selection_card.text()
    assert "流動性 Gate：未知（原始值：UNKNOWN）" in view.advice_selection_card.text()
    assert "共用證據詳情（唯讀）" in view.advice_presentation_detail.toPlainText()
    assert view.advice_recommendation_model.rowCount() == 1


def test_advice_contract_backtest_navigation_carries_exact_current_candidate_identity() -> None:
    app()
    advice = AdviceDashboardDTO(
        decision_date="2026-07-06",
        data_as_of_date="2026-07-03",
        mode=AdviceMode.PROFESSIONAL,
        policy=AdvicePolicyConfig(mode=AdviceMode.PROFESSIONAL),
        recommendations=(
            RecommendationAdviceDTO(
                stock_code="2330",
                advice_action=AdviceAction.RESEARCH,
                classification=AdviceClassification.PROFESSIONAL_CANDIDATE,
                strategy_version="strategy-v7",
                decision_date="2026-07-06",
                data_as_of_date="2026-07-03",
                source_result_id="daily-result-001",
                source_trace=("daily-result-001",),
                data_quality="OBSERVED",
            ),
        ),
    )
    daily = WorkbenchDailyEvidence(
        status="ready",
        decision_date="2026-07-06",
        data_as_of_date="2026-07-03",
        headline="daily candidate",
        next_action="research",
        market_summary="",
        industry_summary="",
        stock_summary="",
        watchlist_summary="",
        portfolio_summary="",
        candidate_symbols=("2330",),
        candidate_status="candidate",
        candidate_result_id="daily-result-001",
        candidate_source_snapshot_id="snapshot-001",
        candidate_data_date="2026-07-03",
    )
    navigated: list[object] = []
    view = UnifiedDecisionWorkbenchView(
        dashboard=replace(
            _dashboard_with_replay(),
            advice_dashboard=advice,
            daily_evidence=daily,
        ),
        navigate_to_backtest_callback=lambda context: navigated.append(context) or True,
        auto_refresh=False,
    )

    view._show_advice_row_presentation(view.advice_candidate_model, 0)

    assert not view.advice_contract_backtest_button.isHidden()
    assert view._open_backtest_for_advice_contract() is True
    assert len(navigated) == 1
    context = navigated[0]
    assert context.candidate_result_id == "daily-result-001"
    assert context.source_snapshot_id == "snapshot-001"
    assert context.stock_code == "2330"
    assert context.strategy_version == "strategy-v7"
    assert context.missing_author_fields == (
        "進場論點",
        "失效條件",
        "策略持有期間",
        "策略檢視頻率",
    )
    view._dashboard_stale = True
    assert view._open_backtest_for_advice_contract() is False
    assert len(navigated) == 1


def test_workbench_advice_quick_read_separates_policy_restrictions_from_source_evidence() -> None:
    app()
    advice = AdviceDashboardDTO(
        decision_date="2026-07-06",
        data_as_of_date="2026-07-03",
        mode=AdviceMode.GUIDED,
        policy=AdvicePolicyConfig(),
        recommendations=(
            RecommendationAdviceDTO(
                stock_code="2330",
                advice_action=AdviceAction.RESEARCH,
                confidence_tier="medium",
                why_reasons=("research_gate_passed", "volume_confirmation"),
                why_not_reasons=("price_current_session_missing", "source_not_fresh"),
                source_evidence=("Why Not：結果=未通過；來源理由碼=price_current_session_missing",),
                risk_reasons=("position_limit_review", "low_liquidity_review"),
                data_quality="PARTIAL",
                liquidity_state="UNKNOWN",
                decision_date="2026-07-06",
                data_as_of_date="2026-07-03",
                execution_feasibility="UNKNOWN",
            ),
        ),
    )
    view = UnifiedDecisionWorkbenchView(
        dashboard=replace(_dashboard_with_replay(), advice_dashboard=advice),
        auto_refresh=False,
    )
    model = view.advice_recommendation_model
    quick_index = model.index(0, model.column_index("quick_reasons"))
    risk_index = model.index(0, model.column_index("primary_risk"))
    status_index = model.index(0, model.column_index("evidence_status"))
    confidence_index = model.index(0, model.column_index("confidence_tier"))

    assert model.headerData(
        model.column_index("quick_reasons"), Qt.Orientation.Horizontal
    ) == "支持理由／資格限制"
    assert model.data(quick_index).startswith("支持：符合研究條件（另 1 項）｜政策／資格限制：")
    assert "缺少當日價格" in model.data(quick_index, Qt.ToolTipRole)
    assert "同股保存來源證據：Why Not：結果=未通過" in model.data(
        quick_index, Qt.ToolTipRole
    )
    assert "不能據此推定沒有反證或風險" not in model.data(quick_index, Qt.ToolTipRole)
    view.advice_recommendation_table.setCurrentIndex(model.index(0, 0))
    assert "Advice 原始理由（含資格限制）" in view.advice_selection_card.text()
    assert "保存來源逐股證據：Why Not：結果=未通過" in view.advice_selection_card.text()
    assert model.data(risk_index) == "持倉限制待覆核（另 1 項）"
    assert model.data(status_index) == (
        "部分資料｜證據成熟度：未知／未對齊｜流動性 Gate：未知｜成交：未知｜資料日：2026-07-03"
    )
    assert "流動性 Gate：未知（原始值：UNKNOWN）" in model.data(
        status_index, Qt.ToolTipRole
    )
    assert "決策日：2026-07-06" in model.data(status_index, Qt.ToolTipRole)
    assert model.data(confidence_index) == "中"
    assert model.data(confidence_index, Qt.ToolTipRole) == "原始值：medium"

    reviewed = AdviceDashboardDTO(
        decision_date="2026-07-06",
        data_as_of_date="2026-07-03",
        mode=AdviceMode.GUIDED,
        policy=AdvicePolicyConfig(),
        recommendations=(
            RecommendationAdviceDTO(
                stock_code="2317",
                advice_action=AdviceAction.RESEARCH,
                evidence_tier="forward-reviewed",
            ),
            RecommendationAdviceDTO(
                stock_code="2308",
                advice_action=AdviceAction.RESEARCH,
                evidence_tier="forward",
            ),
        ),
    )
    reviewed_view = UnifiedDecisionWorkbenchView(
        dashboard=replace(_dashboard_with_replay(), advice_dashboard=reviewed),
        auto_refresh=False,
    )
    reviewed_status = reviewed_view.advice_recommendation_model.index(
        0, reviewed_view.advice_recommendation_model.column_index("evidence_status")
    )
    raw_forward_status = reviewed_view.advice_recommendation_model.index(
        1, reviewed_view.advice_recommendation_model.column_index("evidence_status")
    )
    assert "證據成熟度：前瞻證據已覆核" in reviewed_view.advice_recommendation_model.data(reviewed_status)
    assert "證據成熟度：未知／未對齊" in reviewed_view.advice_recommendation_model.data(raw_forward_status)
    assert "forward／paper／live" in reviewed_view.advice_recommendation_model.data(
        raw_forward_status, Qt.ToolTipRole
    )


def test_workbench_advice_quick_read_is_cached_until_rows_change(monkeypatch) -> None:
    app()
    calls: list[str] = []
    format_quick_read = workbench_table_models._advice_quick_read

    def count_formatting(row, field_name: str) -> tuple[str, str]:
        calls.append(field_name)
        return format_quick_read(row, field_name)

    monkeypatch.setattr(workbench_table_models, "_advice_quick_read", count_formatting)
    first = RecommendationAdviceDTO(
        stock_code="2330",
        advice_action=AdviceAction.RESEARCH,
        why_reasons=("research_gate_passed",),
        risk_reasons=("position_limit_review",),
        data_quality="OBSERVED",
        liquidity_state="UNKNOWN",
        execution_feasibility="UNKNOWN",
    )
    model = AdviceRecommendationTableModel((first,))

    assert calls == list(model.QUICK_READ_FIELDS)
    quick_index = model.index(0, model.column_index("quick_reasons"))
    for role in (Qt.DisplayRole, Qt.ToolTipRole, Qt.AccessibleTextRole):
        assert model.data(quick_index, role)
    assert calls == list(model.QUICK_READ_FIELDS)

    updated = replace(first, why_reasons=("source_not_fresh",))
    model.set_rows((updated,))

    assert calls == list(model.QUICK_READ_FIELDS) * 2
    updated_quick_index = model.index(0, model.column_index("quick_reasons"))
    assert model.data(updated_quick_index).startswith("支持：")
    assert "來源資料非最新" in model.data(updated_quick_index, Qt.ToolTipRole)
    assert model.data(updated_quick_index, Qt.AccessibleTextRole) == model.data(
        updated_quick_index, Qt.ToolTipRole
    )


def test_workbench_shows_stock_name_only_when_saved_result_identity_is_bound() -> None:
    app()
    advice = AdviceDashboardDTO(
        decision_date="2026-07-06",
        data_as_of_date="2026-07-03",
        mode=AdviceMode.GUIDED,
        policy=AdvicePolicyConfig(),
        recommendations=(
            RecommendationAdviceDTO(
                stock_code="2330",
                stock_name="台積電",
                advice_action=AdviceAction.RESEARCH,
                source_result_id="current-result",
            ),
            RecommendationAdviceDTO(
                stock_code="2317",
                stock_name="鴻海",
                advice_action=AdviceAction.RESEARCH,
            ),
        ),
    )
    view = UnifiedDecisionWorkbenchView(
        dashboard=replace(_dashboard_with_replay(), advice_dashboard=advice),
        auto_refresh=False,
    )
    model = view.advice_recommendation_model
    stock_column = model.column_index("stock_code")

    assert model.data(model.index(0, stock_column)) == "2330 台積電"
    assert "保存結果已對齊：current-result" in model.data(
        model.index(0, stock_column), Qt.ToolTipRole
    )
    assert model.data(model.index(1, stock_column)) == "2317"
    assert "未與目前保存結果核對" in model.data(
        model.index(1, stock_column), Qt.ToolTipRole
    )


def test_workbench_renders_missing_evidence_refusal_as_explicit_no_new_position() -> None:
    app()
    refusal = RecommendationAdviceDTO(
        stock_code="",
        advice_action=AdviceAction.NO_NEW_POSITION,
        why_not_reasons=("evidence_quality_missing",),
        refusal_reasons=("evidence_quality_missing",),
        risk_reasons=("evidence_quality_missing",),
        data_quality="MISSING",
        warnings=("candidate_data_date_missing",),
        source_trace=("AdviceComposer.refusal",),
    )
    advice = AdviceDashboardDTO(
        decision_date="2026-07-06",
        data_as_of_date="",
        mode=AdviceMode.PROFESSIONAL,
        policy=AdvicePolicyConfig(mode=AdviceMode.PROFESSIONAL),
        recommendations=(refusal,),
        warnings=refusal.warnings,
    )

    view = UnifiedDecisionWorkbenchView(
        dashboard=replace(_dashboard_with_replay(), advice_dashboard=advice),
        auto_refresh=False,
    )

    assert not view.advice_empty_widget.isHidden()
    assert "本次結論：暫不新增部位" in view.advice_empty_label.text()
    assert "缺少合格證據" in view.advice_empty_label.text()
    assert "候選資料日期缺失" in view.advice_empty_label.text()
    assert "不是賣出或清倉指令" in view.advice_empty_label.text()
    assert view.advice_technical_diagnostics_button.isHidden()
    assert view.advice_recommendation_table.isHidden()
    assert view.advice_recommendation_model.rowCount() == 0


def test_unified_workbench_advice_detail_keeps_probability_and_confidence_unknown() -> None:
    app()
    advice = AdviceDashboardDTO(
        decision_date="2026-07-06",
        data_as_of_date="2026-07-06",
        mode=AdviceMode.GUIDED,
        policy=AdvicePolicyConfig(),
        recommendations=(
            RecommendationAdviceDTO(
                stock_code="2330",
                advice_action=AdviceAction.ADD_CANDIDATE,
                why_reasons=("research_gate_passed",),
                risk_reasons=("position_limit_review",),
                confidence_tier="medium",
                evidence_tier="partial",
                data_quality="PARTIAL",
                holding_horizon="swing",
                entry_thesis="先確認產業與個股證據",
                invalidation_conditions=("證據失效",),
                decision_date="2026-07-06",
                data_as_of_date="2026-07-06",
                execution_feasibility="FEASIBLE",
                source_evidence=("篩選：階段=legacy:technical_gate；結果=通過；資料品質=已觀測",),
                source_trace=("fixture:advice",),
            ),
        ),
    )
    view = UnifiedDecisionWorkbenchView(
        dashboard=replace(_dashboard_with_replay(), advice_dashboard=advice),
        auto_refresh=False,
    )

    view._show_advice_row_presentation(view.advice_recommendation_model, 0)
    detail_text = view.advice_presentation_detail.toPlainText()

    assert "排名分數：未知（僅作排序，不等於機率）" in detail_text
    assert "校準機率：不可用（研究中）" in detail_text
    assert "成本後獲利機率：不可用（研究中）" in detail_text
    assert "證據信心：未提供" in detail_text
    assert view.advice_lineage_button.isEnabled() is True
    assert "機率依據詳情（唯讀）" not in detail_text

    view.advice_lineage_button.click()
    expanded_text = view.advice_presentation_detail.toPlainText()
    assert "機率依據詳情（唯讀）" in expanded_text
    assert "模型版本：未提供" in expanded_text
    assert "自然 evidence status：unknown" in expanded_text
    assert "自然 authority receipt：未提供" in expanded_text

    view.advice_lineage_button.click()
    assert "機率依據詳情（唯讀）" not in view.advice_presentation_detail.toPlainText()
    assert "策略持有期間：swing" in detail_text
    assert "資料日：2026-07-06" in detail_text
    assert "來源追溯：fixture:advice" in detail_text
    assert "保存來源逐股證據：篩選：階段=legacy:technical_gate" in view.advice_selection_card.text()
    assert "保存來源逐股證據：篩選：階段=legacy:technical_gate" in view.advice_selection_card.toolTip()


def test_unified_workbench_exposes_single_research_workflow_and_keyboard_tables() -> None:
    app()
    clicked: list[str] = []
    view = UnifiedDecisionWorkbenchView(
        dashboard=_dashboard_with_replay(),
        auto_refresh=False,
        navigate_to_daily_decision_callback=lambda: clicked.append("market"),
        navigate_to_market_explore_callback=lambda: clicked.append("industry"),
        navigate_to_watchlist_callback=lambda: clicked.append("watchlist"),
        navigate_to_portfolio_callback=lambda: clicked.append("portfolio"),
    )

    assert "市場總覽 → 產業／市場探索 → 關鍵股研究 → 觀察清單 → 持倉覆盤" in view.workflow_path_label.text()
    assert set(view.workflow_path_buttons) == {"market", "industry", "watchlist", "portfolio"}
    assert view.advice_recommendation_table.editTriggers() == QAbstractItemView.EditTrigger.NoEditTriggers
    assert view.advice_recommendation_table.focusPolicy() == Qt.FocusPolicy.StrongFocus

    for key in ("market", "industry", "watchlist", "portfolio"):
        view.workflow_path_buttons[key].click()
    assert clicked == ["market", "industry", "watchlist", "portfolio"]


def test_unified_workbench_overview_uses_detail_inspector_and_collapsible_sections() -> None:
    app()
    clicked: list[str] = []
    view = UnifiedDecisionWorkbenchView(
        dashboard=_dashboard_with_replay(),
        auto_refresh=False,
        navigate_to_evidence_review_callback=lambda: clicked.append("evidence"),
    )

    assert "詳情檢視" in view.detail_section_title.text()
    assert "Daily Decision snapshot" in view.detail_title_label.text()
    assert "DecisionDeskSnapshot" in view.detail_body_label.text()

    view._show_model_row_detail(view.evidence_feed_model, 1)

    detail_text = view.detail_body_label.text()
    assert "Replay 摘要診斷" in view.detail_title_label.text()
    assert "降級" in view.detail_status_badge.text()
    assert MIDNIGHT_ANALYST.status_warning in view.detail_status_badge.styleSheet()
    assert "重點摘要" in view.detail_summary_box.text()
    assert "來源與邊界" in view.detail_source_box.text()
    assert "診斷訊號" in view.detail_diagnostics_box.text()
    assert "HistoricalReplaySummary" in detail_text
    assert "缺產業基準" in detail_text
    assert "模擬 排程器" in detail_text or "模擬排程器" in detail_text
    assert "唯讀邊界" in detail_text
    assert "simulated_scheduler" not in detail_text
    assert "missing_industry_benchmark" not in detail_text
    assert "read-only" not in detail_text
    assert view.detail_drilldown_button.isEnabled() is True

    view.detail_drilldown_button.click()
    assert clicked == ["evidence"]

    assert view.evidence_collapsible.is_collapsed() is True
    view.evidence_collapsible.toggle_button.click()
    assert view.evidence_collapsible.is_collapsed() is False
    view.evidence_collapsible.toggle_button.click()
    assert view.evidence_collapsible.is_collapsed() is True


def test_unified_workbench_reflows_narrow_layout_and_expands_dto_fields() -> None:
    app()
    view = UnifiedDecisionWorkbenchView(
        dashboard=_dashboard_with_replay(),
        auto_refresh=False,
    )
    view.show()
    app().processEvents()

    view.resize(1366, 768)
    assert view.primary_layout.direction() == QBoxLayout.LeftToRight
    assert view.detail_panel.minimumWidth() == 360

    view.resize(390, 844)
    assert view.primary_layout.direction() == QBoxLayout.TopToBottom
    assert view.detail_panel.minimumWidth() == 0
    assert view.review_table.horizontalScrollBarPolicy() == Qt.ScrollBarAsNeeded
    assert view.detail_body_label.isHidden() is True

    view.detail_technical_button.click()
    assert view.detail_body_label.isHidden() is False
    assert "snapshot hash：未知" in view.detail_body_label.text()
    assert "schema 版本：未知" in view.detail_body_label.text()

    view.detail_technical_button.click()
    assert view.detail_body_label.isHidden() is True


def test_unified_workbench_overview_uses_high_contrast_priority_treatments() -> None:
    app()
    view = UnifiedDecisionWorkbenchView(
        dashboard=_dashboard_with_replay(),
        auto_refresh=False,
    )

    assert "今日重點" in view.priority_banner.text()
    assert "人工處理 1" in view.priority_banner.text()
    assert "警告 3" in view.priority_banner.text()
    assert MIDNIGHT_ANALYST.status_warning in view.priority_banner.styleSheet()
    assert MIDNIGHT_ANALYST.status_error in view.summary_blocks["warning"].styleSheet()
    assert MIDNIGHT_ANALYST.status_info in view.summary_blocks["review"].styleSheet()
    assert "font-size: 17px" in view.summary_value_labels["warning"].styleSheet()


def test_unified_workbench_view_displays_empty_and_degraded_queue_state_copy() -> None:
    app()
    empty_view = UnifiedDecisionWorkbenchView(
        dashboard=_empty_dashboard(),
        auto_refresh=False,
    )

    assert "沒有背景證據列" in empty_view.evidence_feed_state_label.text()
    assert "不讀 DB" in empty_view.evidence_feed_state_label.text()
    assert "沒有人工待處理事項" in empty_view.action_item_state_label.text()
    assert "不是買賣建議" in empty_view.action_item_state_label.text()
    assert "不寫 DB" in empty_view.action_item_state_label.text()
    assert "目前沒有明確人工判讀項目" in empty_view.review_empty_state.title_label.text()
    assert "空佇列不代表風險已確認" in empty_view.review_empty_state.body_label.text()
    assert empty_view.review_empty_state.isHidden() is False
    assert empty_view.review_table.isHidden() is True

    degraded_view = UnifiedDecisionWorkbenchView(
        dashboard=_dashboard_with_replay(),
        auto_refresh=False,
    )

    assert "降級" in degraded_view.evidence_feed_state_label.text()
    assert "不補值" in degraded_view.evidence_feed_state_label.text()
    assert "降級" in degraded_view.action_item_state_label.text()
    assert "只供人工覆盤排序" in degraded_view.action_item_state_label.text()
    assert "不是買賣建議" in degraded_view.action_item_state_label.text()


def test_unified_workbench_view_keeps_market_batch_outside_human_queue() -> None:
    app()
    machine_only = replace(
        _empty_dashboard(),
        background_evidence_feed=(
            WorkbenchEvidenceFeedItem(
                item_id="risk_prompt_liquidity_batch",
                label="低流動性市場提示",
                status="warning",
                summary="Decision Desk 已標記 1121 筆低流動性市場提示。",
                source_trace="DecisionDeskSnapshot.risk_prompts.category=liquidity",
                degraded_reason="market_screening_batch:liquidity",
                drilldown_target="daily_decision",
                diagnostics=("prompt_count:1121",),
                status_classification="machine_degraded",
            ),
        ),
    )

    view = UnifiedDecisionWorkbenchView(dashboard=machine_only, auto_refresh=False)

    assert view.review_model.rowCount() == 0
    assert "機器狀態待處理" in view.review_empty_state.title_label.text()
    assert "市場批次提示" in view.review_empty_state.body_label.text()
    assert "背景提示 1 批" in view.priority_banner.text()
    assert MIDNIGHT_ANALYST.status_warning in view.priority_banner.styleSheet()
    assert "空佇列不代表風險已確認" not in view.review_empty_state.body_label.text()


def test_unified_workbench_view_does_not_call_machine_only_gaps_confirmed() -> None:
    app()
    machine_only = replace(
        _empty_dashboard(),
        action_items=(
            WorkbenchActionItem(
                item_id="missing_source",
                title="官方來源缺件",
                source_type="pre_v2_readiness",
                severity="action_required",
                summary="來源尚未提供。",
                source_trace="PreV2ReadinessReport",
                degraded_reason="source_missing_screening_matrix",
                drilldown_target="evidence_review",
                queue_group="evidence_gate",
            ),
        ),
    )

    view = UnifiedDecisionWorkbenchView(dashboard=machine_only, auto_refresh=False)

    assert view.review_model.rowCount() == 0
    assert "機器狀態待處理" in view.review_empty_state.title_label.text()
    assert "不能解讀為風險已確認" in view.review_empty_state.body_label.text()
    assert "人工處理 0" in view.priority_banner.text()


def test_unified_workbench_view_routes_action_item_targets_to_legacy_pages() -> None:
    app()
    clicked: list[str] = []
    view = UnifiedDecisionWorkbenchView(
        dashboard=_dashboard_with_replay(),
        auto_refresh=False,
        navigate_to_daily_decision_callback=lambda: clicked.append("daily"),
        navigate_to_evidence_review_callback=lambda: clicked.append("evidence"),
        navigate_to_portfolio_callback=lambda: clicked.append("portfolio"),
    )

    assert view.navigate_to_drilldown_target("portfolio_review") is True
    assert view.navigate_to_drilldown_target("daily_decision") is True
    assert view.navigate_to_drilldown_target("evidence_review") is True
    assert view.navigate_to_drilldown_target("evidence_mode") is True
    assert view.navigate_to_drilldown_target("unknown_target") is False
    assert clicked == ["portfolio", "daily", "evidence", "evidence"]


def test_workbench_review_queue_marks_viewed_in_memory_only() -> None:
    app()
    clicked: list[str] = []
    view = UnifiedDecisionWorkbenchView(
        dashboard=_dashboard_with_replay(),
        auto_refresh=False,
        navigate_to_evidence_review_callback=lambda: clicked.append("evidence"),
    )

    view._navigate_model_row(view.review_model, 0)

    assert clicked == ["evidence"]
    assert view.viewed_review_item_ids() == {"watchlist_trigger"}
    assert "已查看 1/1" in view.review_state_label.text()


def test_unified_workbench_view_refreshes_only_through_source_service() -> None:
    app()
    service = _FakeWorkbenchSourceService(_dashboard_with_replay())
    view = UnifiedDecisionWorkbenchView(
        source_service=service,
        decision_date="2026-07-06",
        replay_summary_json=Path("replay_summary.json"),
        auto_refresh=False,
    )

    view.refresh_dashboard()

    assert service.calls == [
        {
            "decision_date": "2026-07-06",
            "replay_summary_json": Path("replay_summary.json"),
        }
    ]
    assert view.evidence_model.rowCount() == 2


def test_workbench_today_action_center_prioritizes_data_and_uses_navigation_only() -> None:
    app()
    clicked: list[str] = []
    view = UnifiedDecisionWorkbenchView(
        dashboard=_empty_dashboard(),
        auto_refresh=False,
        navigate_to_daily_decision_callback=lambda: clicked.append("market"),
        navigate_to_portfolio_callback=lambda: clicked.append("portfolio"),
        navigate_to_update_callback=lambda: clicked.append("update"),
        navigate_to_recommendation_callback=lambda: clicked.append("recommendation"),
    )

    assert view.today_action_title.text() == "今日行動中心"
    assert "資料待確認" in view.today_action_status_labels["data"].text()
    assert view.primary_action_button.text() == "先確認資料狀態"
    assert "不會自動更新資料" in view.today_action_hint_label.text()

    view.primary_action_button.click()
    view.today_action_buttons["advice"].click()

    assert clicked == ["update", "recommendation"]


def test_workbench_today_action_center_prioritizes_existing_portfolio_review() -> None:
    app()
    clicked: list[str] = []
    view = UnifiedDecisionWorkbenchView(
        dashboard=_dashboard_with_replay(),
        auto_refresh=False,
        navigate_to_daily_decision_callback=lambda: clicked.append("market"),
        navigate_to_portfolio_callback=lambda: clicked.append("portfolio"),
        navigate_to_update_callback=lambda: clicked.append("update"),
        navigate_to_recommendation_callback=lambda: clicked.append("recommendation"),
    )

    assert "待覆盤 1 項" in view.today_action_status_labels["portfolio"].text()
    assert view.primary_action_button.text() == "先檢查持倉事項"
    assert "只導覽" in view.today_action_hint_label.text()

    view.primary_action_button.click()
    view.today_action_buttons["market"].click()

    assert clicked == ["portfolio", "market"]


def test_workbench_view_does_not_import_db_scheduler_or_domain_calculation_modules() -> None:
    view_source = Path("ui_qt/views/workbench_view.py").read_text(encoding="utf-8")
    model_source = Path("ui_qt/models/workbench_table_models.py").read_text(encoding="utf-8")
    combined = view_source + "\n" + model_source
    blocked_patterns = [
        "sqlite3",
        "data_module.db_manager",
        "app_module.recommendation_service",
        "app_module.backtest_service",
        "app_module.portfolio_service",
        "decision_module.scoring_engine",
        "decision_module.stock_screener",
        "portfolio_module",
        "backtest_module",
        "runtime_scheduler",
    ]

    assert "app_module.workbench_dtos" in view_source
    assert "app_module.workbench_source_service" in view_source
    for pattern in blocked_patterns:
        assert pattern not in combined


def test_candidate_trigger_detail_opens_watchlist_and_keeps_reason_visible() -> None:
    from app_module.decision_desk_dtos import DecisionDeskQuality, WatchlistTriggerSummary
    from app_module.watchlist_trigger_presentation import format_watchlist_trigger_review

    app()
    summary = format_watchlist_trigger_review(WatchlistTriggerSummary(
        date(2026, 9, 21), DecisionDeskQuality.OBSERVED, (),
        trigger_count=2, triggered_codes=("2330", "2603"),
        top_signal="up=2330;down=2603",
    ))
    item = WorkbenchReviewItem(
        item_id="watchlist_trigger", title="候選股指標變化", severity="info",
        source="watchlist_trigger", summary=summary, drilldown_target="watchlist",
    )
    clicked: list[str] = []
    view = UnifiedDecisionWorkbenchView(
        dashboard=replace(_dashboard_with_replay(), review_items=(item,)),
        auto_refresh=False,
        navigate_to_watchlist_callback=lambda: clicked.append("watchlist"),
    )
    view.review_table.clicked.emit(view.review_model.index(0, 0))
    assert "2330：分數較前次上升" in view.detail_summary_box.text()
    assert "2603：分數較前次下降" in view.detail_summary_box.text()
    assert "查看選中個股研究報告" in view.detail_summary_box.text()
    view.detail_drilldown_button.click()
    assert clicked == ["watchlist"]
    view.close()
