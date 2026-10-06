from __future__ import annotations

import os
import sys
import threading
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import shiboken6
from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDateEdit, QTabWidget
import pytest

from app_module.decision_quality_dashboard_dtos import (
    DecisionQualityDashboardCards,
    DecisionQualityDashboardRequest,
    DecisionQualityDashboardResult,
)
from app_module.signal_decay_dashboard_dtos import (
    SignalDecayDashboardCards,
    SignalDecayDashboardRequest,
    SignalDecayDashboardResult,
)
from app_module.live_research_gap_dashboard_dtos import (
    LiveResearchGapDashboardCards,
    LiveResearchGapDashboardRequest,
    LiveResearchGapDashboardResult,
)
from app_module.evidence_operations_history_dashboard_dtos import (
    EvidenceOperationsHistoryDashboardCards,
    EvidenceOperationsHistoryDashboardRequest,
    EvidenceOperationsHistoryDashboardResult,
    EvidenceOperationsHistoryDashboardRow,
)
from ui_qt.models.evidence_operations_history_table_model import EvidenceOperationsHistoryTableModel
from ui_qt.models.signal_decay_table_model import SignalDecayTableModel
from ui_qt.views.decision_quality_view import DecisionQualityView
from ui_qt.views.evidence_review_view import EvidenceReviewView
from ui_qt.views.live_research_gap_view import LiveResearchGapView
from ui_qt.views.scheduled_evidence_status_view import ScheduledEvidenceStatusView
from ui_qt.views.signal_decay_view import SignalDecayView


def app():
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication(sys.argv)
    return instance


class FakeDashboard:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def load_dashboard(self, request):
        self.calls.append(request)
        return self.result


class FakeScheduledStatus:
    def __init__(self):
        from app_module.scheduled_evidence_status_service import ScheduledEvidenceStatus

        self.result = ScheduledEvidenceStatus(
            freshness_status="passed",
            evidence_status="degraded",
            pipeline_overall_status="degraded",
            recommendation_status="passed",
            forward_outcome_status="passed_with_warnings",
            latest_data_date="20260707",
            decision_date="2026-07-07",
            recommendation_result_id="scheduled_rec_20260707_051001",
            forward_outcome_run_id="20260707T214000000000Z",
            recommendations_count=12,
            forward_outcome_events_scanned=12,
            forward_outcome_outcomes_written=7,
            forward_outcome_pending=5,
            forward_outcome_warnings_count=1,
            evidence_progress_status="passed_with_warnings",
            evidence_progress_daily={
                "captures": {"decision_day_count": 2, "new_event_count": 1},
                "maturity": {"ready": 0, "pending": 12, "missing": 0},
            },
            evidence_progress_weekly={"capture_decision_day_count": 2},
            evidence_progress_no_new_data_alert={
                "alert": False,
                "consecutive_no_new_data_days": 0,
            },
            screening_matrix_rows=200,
            dry_run=True,
            writes_evidence_db=False,
            forward_outcome_writes_evidence_db=False,
            writes_recommendation_result=True,
            auto_trading=False,
            lifecycle_action=False,
            source_coverage_warnings=("screening_matrix_missing",),
            pipeline_warnings_count=7,
            pipeline_warning_unique_count=2,
            pipeline_warning_top_counts=(
                ("risk_prompt_source_quality:portfolio_alerts:estimated", 4),
                ("relative_strength_liquidity_skipped_symbols:1", 3),
            ),
            pipeline_advisories_count=3,
            pipeline_advisory_unique_count=2,
            pipeline_advisory_top_counts=(("portfolio_alerts_chip_estimated:2330", 1),),
            report_preview="## Run Metadata\n- decision_date: 2026-07-07",
        )

    def load_latest(self):
        return self.result


class FakeManualObservedScheduledStatus:
    def __init__(self):
        from pathlib import Path

        from app_module.scheduled_evidence_status_service import ScheduledEvidenceStatus

        self.result = ScheduledEvidenceStatus(
            freshness_status="passed",
            evidence_status="passed",
            recommendation_status="manual_observed",
            recommendation_source="manual_result",
            latest_data_date="20260707",
            decision_date="2026-07-07",
            recommendation_result_id="rec_20260707_113744",
            recommendations_count=4,
            screening_matrix_rows=200,
            why_not_payload_rows=196,
            liquidity_gate_payload_rows=169,
            dry_run=True,
            confirm=False,
            writes_evidence_db=False,
            writes_recommendation_result=True,
            auto_trading=False,
            lifecycle_action=False,
            scheduler_readiness_after="ready_for_manual_confirm",
            source_coverage_warnings=("screening_matrix_missing",),
            pipeline_diagnostic_codes=("source_missing_screening_matrix",),
            pipeline_blocking_gaps=(),
            diagnostics=(
                r"status_missing:D:\Min\Python\Project\FA_Data\output\scheduled\recommendation_snapshot\latest_status.json",
                r"manual_recommendation_result_observed:D:\Min\Python\Project\FA_Data\output\recommendation\runs\rec_20260707_113744.json",
            ),
            manual_recommendation_result_path=Path(
                r"D:\Min\Python\Project\FA_Data\output\recommendation\runs\rec_20260707_113744.json"
            ),
            report_preview=(
                "# Evidence Pipeline Dry-run Report\n\n"
                "## Run Metadata\n"
                "- decision_date: 2026-07-07\n\n"
                "## Source Coverage\n"
                "```json\n"
                '{"source_capabilities": {"very": "long"}}\n'
                "```"
            ),
        )

    def load_latest(self):
        return self.result


class _FlakyScheduledStatus:
    def __init__(self, result) -> None:
        self.result = result
        self.calls = 0

    def load_latest(self):
        self.calls += 1
        if self.calls > 1:
            raise RuntimeError()
        return self.result


class _AlwaysFailScheduledStatus:
    def load_latest(self):
        raise RuntimeError()


class _GatedScheduledStatus:
    def __init__(self, result, *, error: str | None = None) -> None:
        self.result = result
        self.error = error
        self.started = threading.Event()
        self.release = threading.Event()

    def load_latest(self):
        self.started.set()
        if not self.release.wait(timeout=5):
            raise TimeoutError("test did not release scheduled status worker")
        if self.error is not None:
            raise RuntimeError(self.error)
        return self.result


def _wait_for_qt_callbacks(application: QApplication) -> None:
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline:
        application.processEvents()
        QTest.qWait(5)


def test_signal_decay_table_model_formats_bp_without_changing_raw_value() -> None:
    app()
    from app_module.signal_decay_dashboard_dtos import SignalDecayDashboardRow

    row = SignalDecayDashboardRow(
        signal_scope_type="event_type",
        signal_scope_id="recommendation_included",
        sample_size_short=12,
        sample_size_long=40,
        forward_excess_short_bp=-700,
        forward_excess_long_bp=300,
        decay_score_bp=6500,
        decay_status="decaying",
        suggested_lifecycle_action="demote_candidate",
        confidence="medium",
        quality="degraded",
        warnings=("missing_industry_evidence",),
    )
    model = SignalDecayTableModel((row,))

    col = model.column_index("forward_excess_short_bp")
    assert model.data(model.index(0, col)) == "-7.00%"
    assert model.raw_value(0, "forward_excess_short_bp") == -700


def test_evidence_review_view_contains_read_only_tabs_including_scheduled_status() -> None:
    app()
    view = EvidenceReviewView(
        forward_performance_widget=QTabWidget(),
        live_gap_service=FakeDashboard(LiveResearchGapDashboardResult(LiveResearchGapDashboardRequest(), LiveResearchGapDashboardCards())),
        signal_decay_service=FakeDashboard(SignalDecayDashboardResult(SignalDecayDashboardRequest(), SignalDecayDashboardCards())),
        decision_quality_service=FakeDashboard(DecisionQualityDashboardResult(DecisionQualityDashboardRequest(), DecisionQualityDashboardCards())),
        evidence_history_service=FakeDashboard(EvidenceOperationsHistoryDashboardResult(EvidenceOperationsHistoryDashboardRequest(), EvidenceOperationsHistoryDashboardCards())),
        scheduled_status_service=FakeScheduledStatus(),
    )

    labels = [view.tabs.tabText(index) for index in range(view.tabs.count())]
    assert labels == ["今日決策", "歷史驗證", "資料缺口"]

    # 驗證嵌套的子 Tab 項目是否齊全
    # 今日決策
    today_widget = view.tabs.widget(0)
    today_tabs = today_widget.findChild(QTabWidget)
    assert today_tabs is not None
    today_labels = [today_tabs.tabText(i) for i in range(today_tabs.count())]
    assert "決策品質" in today_labels
    assert "排程狀態" in today_labels

    # 歷史驗證
    hist_widget = view.tabs.widget(1)
    hist_tabs = hist_widget.findChild(QTabWidget)
    assert hist_tabs is not None
    hist_labels = [hist_tabs.tabText(i) for i in range(hist_tabs.count())]
    assert "前瞻證據" in hist_labels
    assert "訊號衰退" in hist_labels
    assert "覆盤歷史" in hist_labels

    assert "任何 demote / retire" in view.boundary_banner.text()


def test_evidence_review_view_shows_current_evidence_database_path() -> None:
    app()
    db_path = r"D:\Min\Python\Project\FA_Data\output\evidence_ui_smoke\data_root\sqlite\twstock.db"
    view = EvidenceReviewView(
        forward_performance_widget=QTabWidget(),
        live_gap_service=FakeDashboard(LiveResearchGapDashboardResult(LiveResearchGapDashboardRequest(), LiveResearchGapDashboardCards())),
        signal_decay_service=FakeDashboard(SignalDecayDashboardResult(SignalDecayDashboardRequest(), SignalDecayDashboardCards())),
        decision_quality_service=FakeDashboard(DecisionQualityDashboardResult(DecisionQualityDashboardRequest(), DecisionQualityDashboardCards())),
        evidence_history_service=FakeDashboard(EvidenceOperationsHistoryDashboardResult(EvidenceOperationsHistoryDashboardRequest(), EvidenceOperationsHistoryDashboardCards())),
        evidence_db_path=db_path,
    )

    assert "目前資料庫" in view.evidence_db_path_label.text()
    assert db_path in view.evidence_db_path_label.text()


def test_scheduled_evidence_status_view_shows_latest_scheduled_run() -> None:
    app()
    view = ScheduledEvidenceStatusView(FakeScheduledStatus(), auto_refresh=False, async_refresh=False)

    view.refresh_status()

    assert "20260707" in view.freshness_label.text()
    assert "scheduled_rec_20260707_051001" in view.recommendation_label.text()
    assert "degraded / 決策日 2026-07-07" in view.evidence_label.text()
    assert "passed_with_warnings / 掃描 12 / 寫入 7" in view.forward_outcome_label.text()
    assert "進度：passed_with_warnings / 無新增 0 天 / 正常" in view.forward_outcome_label.text()
    assert "writes_recommendation_result: true" in view.detail_panel.toPlainText()
    assert "writes_evidence_db=false" in view.safety_label.text()
    assert "screening_matrix_missing" in view.detail_panel.toPlainText()
    assert "pipeline warnings: 7 warning occurrences / 2 warning types" in view.detail_panel.toPlainText()
    assert "pipeline advisories: 3 advisory occurrences / 2 advisory types" in view.detail_panel.toPlainText()
    assert "pipeline_overall_status: degraded" in view.detail_panel.toPlainText()
    assert "forward outcomes: passed_with_warnings" in view.detail_panel.toPlainText()
    assert "evidence progress: status=passed_with_warnings" in view.detail_panel.toPlainText()
    assert "weekly decision days=2" in view.detail_panel.toPlainText()
    assert "recommendation result write: true / research-only output" in view.detail_panel.toPlainText()
    assert "production evidence/trading write risk: false" in view.detail_panel.toPlainText()
    assert "risk_prompt_source_quality:portfolio_alerts:estimated=4" in view.detail_panel.toPlainText()
    assert "Run Metadata" in view.detail_panel.toPlainText()


def test_scheduled_status_view_separates_engineering_run_from_research_cohort_quality() -> None:
    app()
    from app_module.scheduled_evidence_status_service import ScheduledEvidenceStatus

    class FixedStatus:
        def __init__(self, result):
            self.result = result

        def load_latest(self):
            return self.result

    verified = ScheduledEvidenceStatus(
        recommendation_status="passed",
        recommendation_source="scheduled_latest_status",
        recommendation_result_id="rec_20261002_verified",
        decision_date="2026-10-02",
        recommendations_count=15,
        recommendation_cohort_integrity_basis="canonical_payload_and_index_verified",
        recommendation_canonical_payload_hash="sha256:" + "b" * 64,
        recommendation_cohort_hash="sha256:" + "a" * 64,
        recommendation_cohort_requested_count=200,
        recommendation_cohort_quality_missing_count=0,
        recommendation_cohort_quality_degraded_count=185,
        recommendation_cohort_classifications=(
            ("可用候選", 15),
            ("策略排除", 185),
            ("缺資料", 0),
            ("來源品質問題", 0),
            ("其他未判定", 0),
        ),
    )
    view = ScheduledEvidenceStatusView(
        FixedStatus(verified), auto_refresh=False, async_refresh=False
    )
    view.refresh_status()

    card = view.recommendation_label.text()
    details = view.detail_panel.toPlainText()
    assert view.recommendation_label.wordWrap()
    assert view.recommendation_label.minimumHeight() >= 112
    assert "passed / scheduled_latest_status" in card
    assert "可用候選 15 / 策略排除 185 / 缺資料 0 / 來源品質問題 0 / 其他未判定 0" in card
    assert "推薦工程執行結果：passed" in details
    assert "canonical_payload_and_index_verified" in details
    assert "payload_hash=sha256:" in details
    assert "保存的 cohort quality 原始統計（未改寫）：degraded=185 / missing=0" in details
    assert "研究用途" in details
    assert "不代表勝率或策略績效" in details

    unverified = ScheduledEvidenceStatus(
        recommendation_status="passed",
        recommendation_source="scheduled_latest_status",
        recommendation_result_id="rec_20261002_unverified",
    )
    unverified_view = ScheduledEvidenceStatusView(
        FixedStatus(unverified), auto_refresh=False, async_refresh=False
    )
    unverified_view.refresh_status()
    assert "未確認" in unverified_view.recommendation_label.text()
    assert "來源品質問題 0" not in unverified_view.recommendation_label.text()


@pytest.mark.parametrize(
    "error",
    (None, "controlled scheduled status error"),
    ids=("success", "error"),
)
def test_scheduled_status_worker_release_while_view_is_alive(monkeypatch, error) -> None:
    application = app()
    qt_exceptions = []
    monkeypatch.setattr(
        sys,
        "excepthook",
        lambda exception_type, exception, traceback: qt_exceptions.append(
            (exception_type, exception, traceback)
        ),
    )

    service = _GatedScheduledStatus(FakeScheduledStatus().result, error=error)
    view = ScheduledEvidenceStatusView(
        service,
        auto_refresh=False,
        async_refresh=True,
    )
    view.refresh_status()
    worker = view._worker
    assert worker is not None
    assert service.started.wait(timeout=2)
    service.release.set()
    assert worker.wait(5000)
    _wait_for_qt_callbacks(application)

    assert view._worker is None
    assert view.refresh_button.isEnabled()
    if error is None:
        assert "20260707" in view.freshness_label.text()
    else:
        assert "狀態未知" in view.boundary_label.text()
    assert qt_exceptions == []

    worker.deleteLater()
    view.setAttribute(Qt.WA_DeleteOnClose, True)
    assert view.close()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


@pytest.mark.parametrize(
    "error",
    (None, "controlled scheduled status error"),
    ids=("success", "error"),
)
@pytest.mark.parametrize(
    "delete_before_result",
    (True, False),
    ids=("view-deleted-first", "result-queued-first"),
)
def test_scheduled_status_worker_callbacks_disconnect_when_view_is_deleted(
    monkeypatch,
    error,
    delete_before_result,
) -> None:
    application = app()
    qt_exceptions = []
    monkeypatch.setattr(
        sys,
        "excepthook",
        lambda exception_type, exception, traceback: qt_exceptions.append(
            (exception_type, exception, traceback)
        ),
    )

    service = _GatedScheduledStatus(FakeScheduledStatus().result, error=error)
    view = ScheduledEvidenceStatusView(
        service,
        auto_refresh=False,
        async_refresh=True,
    )
    view.refresh_status()
    worker = view._worker
    assert worker is not None
    assert service.started.wait(timeout=2)

    if not delete_before_result:
        service.release.set()
        assert worker.wait(5000)
        assert view._worker is worker
        assert not view.refresh_button.isEnabled()

    view.setAttribute(Qt.WA_DeleteOnClose, True)
    assert view.close()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    assert not shiboken6.isValid(view)

    if delete_before_result:
        service.release.set()
    assert worker.wait(5000)
    _wait_for_qt_callbacks(application)

    assert qt_exceptions == []
    worker.deleteLater()
    QCoreApplication.sendPostedEvents(worker, QEvent.DeferredDelete)


def test_scheduled_evidence_status_view_prioritizes_manual_observed_summary_over_raw_report() -> None:
    app()
    view = ScheduledEvidenceStatusView(FakeManualObservedScheduledStatus(), auto_refresh=False, async_refresh=False)

    view.refresh_status()

    details = view.detail_panel.toPlainText()

    assert "判讀摘要" in details
    assert "manual_observed / manual_result / rec_20260707_113744 / 4 筆" in details
    assert "scheduled latest_status missing；manual result observed" in details
    assert "production evidence/trading write risk: false" in details
    assert "Report preview（trimmed）" in details
    assert "source_capabilities" not in details


def test_scheduled_status_view_marks_each_card_stale_and_focuses_retry() -> None:
    app()
    source = _FlakyScheduledStatus(FakeScheduledStatus().result)
    view = ScheduledEvidenceStatusView(source, auto_refresh=False, async_refresh=False)

    view.refresh_status()
    first_id = view.recommendation_label.text()
    view.refresh_status()

    assert "scheduled_rec_20260707_051001" in first_id
    assert "scheduled_rec_20260707_051001" in view.recommendation_label.text()
    assert all("資料狀態：stale" in label.text() for label in (
        view.freshness_label,
        view.recommendation_label,
        view.evidence_label,
        view.forward_outcome_label,
        view.safety_label,
        view.report_label,
    ))
    assert "last-known-good" in view.detail_panel.toPlainText()
    assert view.refresh_button.accessibleName() == "重新整理排程證據狀態"
    assert view.refresh_button.focusPolicy().value != 0


def test_scheduled_status_view_keeps_initial_empty_error_unknown_without_index_error() -> None:
    app()
    view = ScheduledEvidenceStatusView(
        _AlwaysFailScheduledStatus(), auto_refresh=False, async_refresh=False
    )

    view.refresh_status()

    assert "狀態未知" in view.boundary_label.text()
    assert "尚無 last-known-good" in view.detail_panel.toPlainText()
    assert "狀態未知" in view.safety_label.text()


def test_evidence_operations_history_table_model_formats_scheduler_boundary() -> None:
    app()
    row = EvidenceOperationsHistoryDashboardRow(
        period_start="2026-07-06",
        period_end="2026-07-12",
        review_status="coverage_only",
        scheduler_readiness="ready_for_manual_confirm",
        production_scheduler_allowed=False,
        decision_quality_reviews_count=1,
        signal_decay_observations_count=2,
        manual_lifecycle_candidate_count=0,
        warnings_count=1,
        review_id="eor_123",
    )
    model = EvidenceOperationsHistoryTableModel((row,))

    col = model.column_index("production_scheduler_allowed")
    assert model.data(model.index(0, col)) == "否"
    assert model.raw_value(0, "production_scheduler_allowed") is False


def test_evidence_review_dashboard_date_filters_use_calendar_inputs() -> None:
    app()
    gap_view = LiveResearchGapView(
        FakeDashboard(LiveResearchGapDashboardResult(LiveResearchGapDashboardRequest(), LiveResearchGapDashboardCards())),
        auto_refresh=False,
        async_refresh=False,
    )
    decay_view = SignalDecayView(
        FakeDashboard(SignalDecayDashboardResult(SignalDecayDashboardRequest(), SignalDecayDashboardCards())),
        auto_refresh=False,
        async_refresh=False,
    )
    quality_view = DecisionQualityView(
        FakeDashboard(DecisionQualityDashboardResult(DecisionQualityDashboardRequest(), DecisionQualityDashboardCards())),
        auto_refresh=False,
        async_refresh=False,
    )

    for widget in (
        gap_view.observation_date_input,
        decay_view.observation_date_input,
        quality_view.start_date_input,
        quality_view.end_date_input,
    ):
        assert isinstance(widget, QDateEdit)
        assert widget.calendarPopup()


def test_dashboard_views_render_empty_states_and_ignore_stale_results() -> None:
    app()
    dq_service = FakeDashboard(
        DecisionQualityDashboardResult(
            DecisionQualityDashboardRequest(),
            DecisionQualityDashboardCards(),
            empty_state_message="尚無 decision quality review evidence。",
        )
    )
    dq_view = DecisionQualityView(dq_service, auto_refresh=False, async_refresh=False)
    dq_view.refresh_dashboard()
    assert "尚無 decision quality review evidence" in dq_view.empty_state_label.text()

    decay_service = FakeDashboard(
        SignalDecayDashboardResult(
            SignalDecayDashboardRequest(),
            SignalDecayDashboardCards(),
            empty_state_message="尚無 signal decay evidence。",
        )
    )
    decay_view = SignalDecayView(decay_service, auto_refresh=False, async_refresh=False)
    decay_view._active_request_id = 2
    decay_view._on_dashboard_loaded(decay_service.result, request_id=1)
    assert decay_view.table_model.rowCount() == 0
    decay_view._on_dashboard_loaded(decay_service.result, request_id=2)
    assert "尚無 signal decay evidence" in decay_view.empty_state_label.text()

    gap_service = FakeDashboard(
        LiveResearchGapDashboardResult(
            LiveResearchGapDashboardRequest(),
            LiveResearchGapDashboardCards(),
            empty_state_message="尚無 live research gap evidence。",
        )
    )
    gap_view = LiveResearchGapView(gap_service, auto_refresh=False, async_refresh=False)
    gap_view.refresh_dashboard()
    assert "尚無 live research gap evidence" in gap_view.empty_state_label.text()
