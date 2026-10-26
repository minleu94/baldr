from __future__ import annotations

import os
import sqlite3
import sys
import threading
import time
from dataclasses import replace
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import shiboken6
from PySide6.QtCore import QCoreApplication, QDate, QEvent, QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDateEdit,
    QLabel,
    QScrollArea,
    QTabWidget,
    QWidget,
)
import pytest

from app_module.decision_quality_dashboard_dtos import (
    DecisionQualityDashboardCards,
    DecisionQualityDashboardRequest,
    DecisionQualityDashboardResult,
)
from app_module.decision_quality_dashboard_service import DecisionQualityDashboardService
from app_module.signal_decay_dashboard_dtos import (
    SignalDecayDashboardCards,
    SignalDecayDashboardRequest,
    SignalDecayDashboardResult,
)
from app_module.live_research_gap_dashboard_dtos import (
    LiveResearchGapDashboardCards,
    LiveResearchGapDashboardRequest,
    LiveResearchGapDashboardResult,
    LiveResearchGapDashboardRow,
)
from app_module.evidence_operations_history_dashboard_dtos import (
    EvidenceOperationsHistoryDashboardCards,
    EvidenceOperationsHistoryCursor,
    EvidenceOperationsHistoryDashboardRequest,
    EvidenceOperationsHistoryDashboardResult,
    EvidenceOperationsHistoryDashboardRow,
)
from ui_qt.models.evidence_operations_history_table_model import EvidenceOperationsHistoryTableModel
from ui_qt.models.decision_quality_table_model import DecisionQualityTableModel
from ui_qt.models.signal_decay_table_model import SignalDecayTableModel
from ui_qt.views.decision_quality_view import DecisionQualityView
from ui_qt.views.evidence_review_view import EvidenceReviewView
from ui_qt.views.evidence_operations_history_view import EvidenceOperationsHistoryView
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
                r"status_missing:F:\Min\Python\Project\FA_Data\output\scheduled\recommendation_snapshot\latest_status.json",
                r"manual_recommendation_result_observed:F:\Min\Python\Project\FA_Data\output\recommendation\runs\rec_20260707_113744.json",
            ),
            manual_recommendation_result_path=Path(
                r"F:\Min\Python\Project\FA_Data\output\recommendation\runs\rec_20260707_113744.json"
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
    db_path = r"F:\Min\Python\Project\FA_Data\output\evidence_ui_smoke\data_root\sqlite\twstock.db"
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

    assert view.freshness_label.text().startswith("資料新鮮度\n")
    assert view.recommendation_label.text().startswith("推薦快照\n")
    assert view.evidence_label.text().startswith("證據流程試跑\n")
    assert view.forward_outcome_label.text().startswith("前瞻結果追蹤\n")
    assert view.report_label.text().startswith("報告\n")
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


def test_scheduled_status_view_shows_readable_blockers_and_safe_next_steps() -> None:
    app()
    source = FakeScheduledStatus()
    source.result = replace(
        source.result,
        pipeline_blocking_gaps=("watchlist_trigger_not_ready", "risk_prompt_not_ready"),
        pipeline_warnings_count=20,
        source_coverage_warnings=("source_freshness_degraded:market.relative_strength",),
    )
    view = ScheduledEvidenceStatusView(source, auto_refresh=False, async_refresh=False)

    view.refresh_status()

    text = view.action_label.text()
    assert text.startswith("主要缺口與下一步\n2 項阻擋")
    assert "檢查 Watchlist pool 與其行情新鮮度／品質" in text
    assert "不要手動補候選" in text
    assert "breadth、relative strength/liquidity、sector rotation" in text
    assert "watchlist_trigger_not_ready" in view.detail_panel.toPlainText()


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


def test_scheduled_status_maturity_chart_shows_each_valid_horizon_separately() -> None:
    app()
    from app_module.scheduled_evidence_status_service import ScheduledEvidenceStatus

    status = ScheduledEvidenceStatus(
        load_state="current",
        forward_health_horizons={
            "5d": {"ready": 2, "pending": 5, "missing": 1},
            "20d": {"ready": 4, "pending": 0, "missing": 3},
        },
    )
    view = ScheduledEvidenceStatusView(FakeScheduledStatus(), auto_refresh=False, async_refresh=False)
    view._on_status_loaded(status)

    distribution = view.maturity_distribution
    assert "本次有界摘要（非完整歷史）" in distribution._title.text()
    assert "綠色就緒、黃色待成熟、灰色缺失" in distribution._legend.accessibleName()
    assert "不代表績效或交易訊號" in distribution._legend.accessibleName()
    count_labels = {
        row.findChild(QLabel, "maturityCounts_5d").text(): row
        for row in distribution._rows
        if row.findChild(QLabel, "maturityCounts_5d") is not None
    }
    assert "2 / 5 / 1" in count_labels
    assert "4 / 0 / 3" in [
        row.findChild(QLabel, "maturityCounts_20d").text()
        for row in distribution._rows
        if row.findChild(QLabel, "maturityCounts_20d") is not None
    ]
    bar = count_labels["2 / 5 / 1"].findChild(QWidget, "maturityBar_5d")
    assert bar is not None
    assert bar.counts == (2, 5, 1)
    assert bar.total == 8
    assert "horizon ready/pending/missing: 20d:R4/P0/M3; 5d:R2/P5/M1" in view.detail_panel.toPlainText()


def test_scheduled_status_horizon_order_is_numeric_then_deterministic_label_order() -> None:
    app()
    from app_module.scheduled_evidence_status_service import ScheduledEvidenceStatus

    status = ScheduledEvidenceStatus(
        load_state="current",
        forward_health_horizons={
            "60": {"ready": 1, "pending": 0, "missing": 0},
            "10": {"ready": 1, "pending": 0, "missing": 0},
            "5": {"ready": 1, "pending": 0, "missing": 0},
            "20": {"ready": 1, "pending": 0, "missing": 0},
            "H5": {"ready": 1, "pending": 0, "missing": 0},
        },
    )
    view = ScheduledEvidenceStatusView(FakeScheduledStatus(), auto_refresh=False, async_refresh=False)
    view._on_status_loaded(status)

    chart_order = [row.layout().itemAt(0).widget().text() for row in view.maturity_distribution._rows]
    assert chart_order == ["5", "10", "20", "60", "H5"]
    summary = view.detail_panel.toPlainText().split("horizon ready/pending/missing: ", 1)[1].splitlines()[0]
    assert summary == "5:R1/P0/M0; 10:R1/P0/M0; 20:R1/P0/M0; 60:R1/P0/M0; H5:R1/P0/M0"


@pytest.mark.parametrize(
    "counts, expected",
    [
        ({"ready": 2, "pending": 1}, "缺少 missing"),
        ({"ready": True, "pending": 1, "missing": 0}, "ready=True"),
        ({"ready": 2, "pending": -1, "missing": 0}, "pending=-1"),
        ({"ready": 2, "pending": 1.5, "missing": 0}, "pending=1.5"),
    ],
    ids=("missing-key", "boolean-is-not-count", "negative", "non-integer"),
)
def test_scheduled_status_maturity_chart_keeps_invalid_horizon_unknown(counts, expected) -> None:
    app()
    from app_module.scheduled_evidence_status_service import ScheduledEvidenceStatus

    status = ScheduledEvidenceStatus(load_state="current", forward_health_horizons={"10d": counts})
    view = ScheduledEvidenceStatusView(FakeScheduledStatus(), auto_refresh=False, async_refresh=False)
    view._on_status_loaded(status)

    texts = [row.text() for row in view.maturity_distribution._rows if isinstance(row, QLabel)]
    assert any("10d: 未知" in text and expected in text for text in texts)
    assert not any(row.findChild(QWidget, "maturityBar_10d") for row in view.maturity_distribution._rows)
    assert f"horizon ready/pending/missing: 10d:未知（{expected}）" in view.detail_panel.toPlainText()


def test_scheduled_status_maturity_chart_shows_true_zero_without_a_bar() -> None:
    app()
    from app_module.scheduled_evidence_status_service import ScheduledEvidenceStatus

    status = ScheduledEvidenceStatus(
        load_state="current",
        forward_health_horizons={"H20": {"ready": 0, "pending": 0, "missing": 0}},
    )
    view = ScheduledEvidenceStatusView(FakeScheduledStatus(), auto_refresh=False, async_refresh=False)
    view._on_status_loaded(status)

    row = next(
        row
        for row in view.maturity_distribution._rows
        if row.findChild(QLabel, "maturityCounts_H20") is not None
    )
    bar = row.findChild(QWidget, "maturityBar_H20")
    assert row.findChild(QLabel, "maturityCounts_H20").text() == "0 / 0 / 0"
    assert bar is not None and bar.total == 0


def test_scheduled_status_maturity_chart_marks_last_known_good_stale() -> None:
    app()
    from app_module.scheduled_evidence_status_service import ScheduledEvidenceStatus

    source = _FlakyScheduledStatus(
        ScheduledEvidenceStatus(
            load_state="current",
            forward_health_horizons={"H5": {"ready": 1, "pending": 2, "missing": 3}},
        )
    )
    view = ScheduledEvidenceStatusView(source, auto_refresh=False, async_refresh=False)
    view.refresh_status()
    view.refresh_status()

    assert "STALE" in view.maturity_distribution._title.text()
    assert any(
        row.findChild(QLabel, "maturityCounts_H5") is not None
        and row.findChild(QLabel, "maturityCounts_H5").text() == "1 / 2 / 3"
        for row in view.maturity_distribution._rows
    )


def test_scheduled_status_maturity_chart_clears_for_initial_error_and_unknown_payload() -> None:
    app()
    from app_module.scheduled_evidence_status_service import ScheduledEvidenceStatus

    failed_view = ScheduledEvidenceStatusView(
        _AlwaysFailScheduledStatus(), auto_refresh=False, async_refresh=False
    )
    failed_view.refresh_status()
    assert "未知" in failed_view.maturity_distribution._title.text()
    assert not any(row.findChild(QWidget, "maturityBar_H5") for row in failed_view.maturity_distribution._rows)

    unknown_status = ScheduledEvidenceStatus(
        load_state="unknown",
        load_checked_at="2026-10-23T12:00:00+00:00",
        diagnostics=("latest_status_missing",),
        forward_health_horizons={"H5": {"ready": 5, "pending": 0, "missing": 0}},
    )
    unknown_view = ScheduledEvidenceStatusView(
        FakeScheduledStatus(), auto_refresh=False, async_refresh=False
    )
    unknown_view._on_status_loaded(unknown_status)
    assert "latest_status_missing" in " ".join(
        row.text() for row in unknown_view.maturity_distribution._rows if isinstance(row, QLabel)
    )
    assert not any(row.findChild(QWidget, "maturityBar_H5") for row in unknown_view.maturity_distribution._rows)


def test_scheduled_status_maturity_chart_clears_old_values_during_refresh() -> None:
    application = app()
    from app_module.scheduled_evidence_status_service import ScheduledEvidenceStatus

    service = _GatedScheduledStatus(
        ScheduledEvidenceStatus(
            load_state="current",
            forward_health_horizons={"H10": {"ready": 4, "pending": 2, "missing": 1}},
        )
    )
    view = ScheduledEvidenceStatusView(service, auto_refresh=False, async_refresh=True)
    view.maturity_distribution.set_horizons({"H10": {"ready": 1, "pending": 0, "missing": 0}})
    view.refresh_status()

    assert "重新整理中" in " ".join(
        row.text() for row in view.maturity_distribution._rows if isinstance(row, QLabel)
    )
    assert not any(row.findChild(QWidget, "maturityBar_H10") for row in view.maturity_distribution._rows)
    worker = view._worker
    assert worker is not None and service.started.wait(timeout=2)
    service.release.set()
    assert worker.wait(5000)
    _wait_for_qt_callbacks(application)
    assert any(
        row.findChild(QLabel, "maturityCounts_H10") is not None
        and row.findChild(QLabel, "maturityCounts_H10").text() == "4 / 2 / 1"
        for row in view.maturity_distribution._rows
    )


def test_scheduled_status_four_horizon_chart_keeps_two_card_columns_balanced() -> None:
    application = app()
    from app_module.scheduled_evidence_status_service import ScheduledEvidenceStatus

    status = ScheduledEvidenceStatus(
        load_state="current",
        forward_health_horizons={
            "H5": {"ready": 2, "pending": 3, "missing": 1},
            "H10": {"ready": 1, "pending": 4, "missing": 2},
            "H20": {"ready": 0, "pending": 5, "missing": 2},
            "H60": {"ready": 0, "pending": 3, "missing": 4},
        },
    )
    view = ScheduledEvidenceStatusView(FakeScheduledStatus(), auto_refresh=False, async_refresh=False)
    view.resize(1280, 760)
    view.show()
    view._on_status_loaded(status)
    application.processEvents()

    left_width = view.freshness_label.width()
    right_width = view.recommendation_label.width()
    assert left_width > 0 and right_width > 0
    assert abs(left_width - right_width) / max(left_width, right_width) <= 0.15
    assert len(view.maturity_distribution._rows) == 4
    assert all(
        row.findChild(QWidget, f"maturityBar_{horizon}") is not None
        for row, horizon in zip(view.maturity_distribution._rows, ("H10", "H20", "H5", "H60"))
    )


def test_scheduled_status_unknown_detaches_and_hides_old_maturity_bars_immediately() -> None:
    application = app()
    from app_module.scheduled_evidence_status_service import ScheduledEvidenceStatus

    view = ScheduledEvidenceStatusView(FakeScheduledStatus(), auto_refresh=False, async_refresh=False)
    view.resize(1280, 760)
    view.show()
    view._on_status_loaded(
        ScheduledEvidenceStatus(
            load_state="current",
            forward_health_horizons={"H5": {"ready": 1, "pending": 2, "missing": 3}},
        )
    )
    application.processEvents()
    old_row = view.maturity_distribution._rows[0]
    old_bar = old_row.findChild(QWidget, "maturityBar_H5")
    assert old_bar is not None and old_bar.isVisible()

    view._on_status_loaded(
        ScheduledEvidenceStatus(
            load_state="unknown",
            load_checked_at="2026-10-23T12:00:00+00:00",
            diagnostics=("latest_status_missing",),
            forward_health_horizons={"H5": {"ready": 9, "pending": 0, "missing": 0}},
        )
    )
    application.processEvents()

    assert old_row.parentWidget() is None
    assert old_row.isHidden()
    assert not old_bar.isVisible()
    assert not view.maturity_distribution.findChildren(QWidget, "maturityBar_H5")


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


def test_evidence_operations_history_table_model_shows_saved_time_after_period() -> None:
    app()
    first = EvidenceOperationsHistoryDashboardRow(
        period_start="2026-07-06",
        period_end="2026-07-12",
        review_status="coverage_only",
        scheduler_readiness="ready_for_manual_confirm",
        production_scheduler_allowed=False,
        decision_quality_reviews_count=1,
        signal_decay_observations_count=2,
        manual_lifecycle_candidate_count=0,
        warnings_count=1,
        review_id="eor_with_time",
        created_at="2026-07-13T01:23:45Z",
    )
    second = EvidenceOperationsHistoryDashboardRow(
        period_start="2026-07-06",
        period_end="2026-07-12",
        review_status="coverage_only",
        scheduler_readiness="ready_for_manual_confirm",
        production_scheduler_allowed=False,
        decision_quality_reviews_count=1,
        signal_decay_observations_count=2,
        manual_lifecycle_candidate_count=0,
        warnings_count=1,
        review_id="eor_without_time",
    )
    model = EvidenceOperationsHistoryTableModel((first, second))

    start_col = model.column_index("period_start")
    end_col = model.column_index("period_end")
    saved_time_col = model.column_index("created_at")
    assert saved_time_col == end_col + 1
    assert model.headerData(saved_time_col, Qt.Horizontal) == "保存時間"
    assert model.data(model.index(0, saved_time_col)) == "2026-07-13T01:23:45Z"
    assert model.data(model.index(1, saved_time_col)) == "未提供"
    assert model.raw_value(0, "created_at") == "2026-07-13T01:23:45Z"
    assert model.raw_value(1, "created_at") == ""
    assert start_col < end_col < saved_time_col


def test_evidence_operations_history_details_follow_selected_saved_review() -> None:
    app()
    first = EvidenceOperationsHistoryDashboardRow(
        period_start="2026-07-06",
        period_end="2026-07-12",
        review_status="coverage_only",
        scheduler_readiness="ready_for_manual_confirm",
        production_scheduler_allowed=False,
        decision_quality_reviews_count=1,
        signal_decay_observations_count=2,
        manual_lifecycle_candidate_count=0,
        warnings_count=1,
        review_id="eor_first",
        created_at="2026-07-13T01:23:45Z",
    )
    second = EvidenceOperationsHistoryDashboardRow(
        period_start="2026-07-06",
        period_end="2026-07-12",
        review_status="ready_for_weekly_closeout",
        scheduler_readiness="operational_production",
        production_scheduler_allowed=True,
        decision_quality_reviews_count=3,
        signal_decay_observations_count=4,
        manual_lifecycle_candidate_count=1,
        warnings_count=0,
        review_id="eor_second",
        created_at="2026-07-13T09:08:07+08:00",
    )
    unknown = EvidenceOperationsHistoryDashboardRow(
        period_start="2026-07-06",
        period_end="2026-07-12",
        review_status="future_review_code",
        scheduler_readiness="future_readiness_code",
        production_scheduler_allowed=False,
        decision_quality_reviews_count=0,
        signal_decay_observations_count=0,
        manual_lifecycle_candidate_count=0,
        warnings_count=0,
        review_id="eor_unknown",
    )
    limitations = ("只顯示已保存的週報。", "仍需人工覆盤。")
    result = EvidenceOperationsHistoryDashboardResult(
        EvidenceOperationsHistoryDashboardRequest(),
        EvidenceOperationsHistoryDashboardCards(),
        rows=(first, second, unknown),
        limitations=limitations,
    )
    view = EvidenceOperationsHistoryView(
        FakeDashboard(result), auto_refresh=False, async_refresh=False
    )

    view._on_dashboard_loaded(result, request_id=view._active_request_id)
    first_details = view.detail_panel.toPlainText()
    assert "週期: 2026-07-06 至 2026-07-12" in first_details
    assert "保存時間: 2026-07-13T01:23:45Z" in first_details
    assert "Record ID: eor_first" in first_details
    assert "覆盤狀態: 僅有覆蓋資料（原始碼：coverage_only）" in first_details
    assert "正式排程條件: 待人工確認（原始碼：ready_for_manual_confirm）" in first_details
    assert "正式排程允許: 否" in first_details
    assert "限制: 只顯示已保存的週報。 仍需人工覆盤。" in first_details

    view._on_table_row_clicked(view.table_model.index(1, 0))
    second_details = view.detail_panel.toPlainText()
    assert "週期: 2026-07-06 至 2026-07-12" in second_details
    assert "保存時間: 2026-07-13T09:08:07+08:00" in second_details
    assert "Record ID: eor_second" in second_details
    assert "覆盤狀態: 可準備週報收尾（原始碼：ready_for_weekly_closeout）" in second_details
    assert "正式排程條件: 正式作業狀態（原始碼：operational_production）" in second_details
    assert "正式排程允許: 是" in second_details
    assert "Decision Quality reviews: 3" in second_details
    assert "限制: 只顯示已保存的週報。 仍需人工覆盤。" in second_details

    view._on_table_row_clicked(view.table_model.index(2, 0))
    unknown_details = view.detail_panel.toPlainText()
    assert "覆盤狀態: 未識別狀態（原始碼：future_review_code）" in unknown_details
    assert "正式排程條件: 未識別狀態（原始碼：future_readiness_code）" in unknown_details


def test_evidence_operations_history_cards_use_available_width_and_keep_table_rows() -> None:
    application = app()
    view = EvidenceOperationsHistoryView(
        FakeDashboard(EvidenceOperationsHistoryDashboardResult(
            EvidenceOperationsHistoryDashboardRequest(),
            EvidenceOperationsHistoryDashboardCards(),
        )),
        auto_refresh=False,
        async_refresh=False,
    )
    view.resize(1200, 760)
    view.show()
    application.processEvents()

    wide_positions = [view.cards_layout.getItemPosition(index)[:2] for index in range(6)]
    assert wide_positions == [(0, column) for column in range(6)]
    assert all(
        card.width() >= card.fontMetrics().horizontalAdvance("允許正式排程") + 20
        for card in view.cards.values()
    )

    view.resize(900, 760)
    application.processEvents()
    narrow_positions = [view.cards_layout.getItemPosition(index)[:2] for index in range(6)]
    assert narrow_positions == [(row, column) for row in range(2) for column in range(3)]
    assert view.summary_table.selectionBehavior() == QAbstractItemView.SelectionBehavior.SelectRows
    assert view.summary_table.minimumHeight() >= (
        5 * view.summary_table.verticalHeader().minimumSectionSize()
    )


def test_evidence_operations_history_details_show_missing_saved_time() -> None:
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
        review_id="eor_without_time",
    )
    result = EvidenceOperationsHistoryDashboardResult(
        EvidenceOperationsHistoryDashboardRequest(),
        EvidenceOperationsHistoryDashboardCards(),
        rows=(row,),
    )
    view = EvidenceOperationsHistoryView(
        FakeDashboard(result), auto_refresh=False, async_refresh=False
    )

    view._on_dashboard_loaded(result, request_id=view._active_request_id)

    details = view.detail_panel.toPlainText()
    assert "保存時間: 未提供" in details
    assert "Record ID: eor_without_time" in details
    assert "週期: 2026-07-06 至 2026-07-12" in details


def test_evidence_operations_history_cards_distinguish_unavailable_from_observed_zero() -> None:
    app()
    empty_result = EvidenceOperationsHistoryDashboardResult(
        EvidenceOperationsHistoryDashboardRequest(),
        EvidenceOperationsHistoryDashboardCards(),
        empty_state_message="尚無 weekly review history。",
    )
    view = EvidenceOperationsHistoryView(
        FakeDashboard(empty_result), auto_refresh=False, async_refresh=False
    )
    assert all(card.text().endswith("\n尚未載入") for card in view.cards.values())
    view._on_dashboard_loaded(empty_result, request_id=view._active_request_id)
    assert all(card.text().endswith("\n0") for card in view.cards.values())
    assert "第 1 頁；本頁索引 0" in view.scope_label.text()
    assert "卡片統計本頁 0 筆" in view.scope_label.text()

    unavailable_result = EvidenceOperationsHistoryDashboardResult(
        EvidenceOperationsHistoryDashboardRequest(),
        EvidenceOperationsHistoryDashboardCards(),
        empty_state_message="目前只讀資料源不可用。",
        source_available=False,
    )
    view._on_dashboard_loaded(unavailable_result, request_id=view._active_request_id)
    assert all(card.text().endswith("\n未知") for card in view.cards.values())
    assert "顯示範圍未知" in view.scope_label.text()


def test_evidence_operations_history_discloses_limited_display_and_card_scope() -> None:
    app()
    rows = tuple(
        EvidenceOperationsHistoryDashboardRow(
            period_start="2026-07-06",
            period_end="2026-07-12",
            review_status="coverage_only",
            scheduler_readiness="ready_for_manual_confirm",
            production_scheduler_allowed=False,
            decision_quality_reviews_count=0,
            signal_decay_observations_count=0,
            manual_lifecycle_candidate_count=0,
            warnings_count=0,
            review_id=f"eor-{index}",
        )
        for index in range(50)
    )
    result = EvidenceOperationsHistoryDashboardResult(
        EvidenceOperationsHistoryDashboardRequest(start_date="2026-07-01", end_date="2026-07-31"),
        EvidenceOperationsHistoryDashboardCards(reviews_count=50),
        rows=rows,
        has_more_rows=True,
    )
    view = EvidenceOperationsHistoryView(
        FakeDashboard(result), auto_refresh=False, async_refresh=False
    )

    view._on_dashboard_loaded(result, request_id=view._active_request_id)

    assert "第 1 頁；本頁索引 1–50" in view.scope_label.text()
    assert "後面還有較舊週報" in view.scope_label.text()
    assert "卡片僅統計本頁 50 筆" in view.scope_label.text()


def test_evidence_operations_history_pagination_buttons_keep_filter_cursor_stack() -> None:
    app()
    cursor = EvidenceOperationsHistoryCursor("2026-07-12", "2026-07-06", "eor-050")
    first_result = EvidenceOperationsHistoryDashboardResult(
        EvidenceOperationsHistoryDashboardRequest(start_date="2026-07-01", end_date="2026-07-31"),
        EvidenceOperationsHistoryDashboardCards(reviews_count=50),
        rows=tuple(
            EvidenceOperationsHistoryDashboardRow(
                period_start="2026-07-06",
                period_end="2026-07-12",
                review_status="coverage_only",
                scheduler_readiness="ready_for_manual_confirm",
                production_scheduler_allowed=False,
                decision_quality_reviews_count=0,
                signal_decay_observations_count=0,
                manual_lifecycle_candidate_count=0,
                warnings_count=0,
                review_id=f"eor-{index:03d}",
            )
            for index in range(50)
        ),
        has_more_rows=True,
        next_cursor=cursor,
    )

    class RecordingService:
        def __init__(self):
            self.requests = []

        def load_dashboard(self, request):
            self.requests.append(request)
            return first_result

    service = RecordingService()
    view = EvidenceOperationsHistoryView(service, auto_refresh=False, async_refresh=False)
    view.start_date_input.setDate(QDate(2026, 7, 1))
    view.end_date_input.setDate(QDate(2026, 7, 31))
    view.refresh_dashboard()
    assert view.previous_button.isEnabled() is False
    assert view.next_button.isEnabled() is True
    assert "第 1 頁；本頁索引 1–50" in view.scope_label.text()

    view.next_button.click()
    assert service.requests[-1].cursor == cursor
    assert view.previous_button.isEnabled() is True
    assert "第 2 頁；本頁索引 51–100" in view.scope_label.text()

    view.previous_button.click()
    assert service.requests[-1].cursor is None
    assert view.previous_button.isEnabled() is False
    view.end_date_input.setDate(QDate(2026, 8, 1))
    assert view.next_button.isEnabled() is False
    assert view.table_model.rowCount() == 0
    assert "日期篩選已變更" in view.empty_state_label.text()
    request_count = len(service.requests)
    view.next_button.click()
    assert len(service.requests) == request_count
    view.refresh_dashboard()
    assert view._page_index == 0
    assert view._cursor_stack == [None]
    assert service.requests[-1].cursor is None
    assert service.requests[-1].end_date == "2026-08-01"


def test_evidence_operations_history_load_error_clears_stale_cards_and_details() -> None:
    app()
    result = EvidenceOperationsHistoryDashboardResult(
        EvidenceOperationsHistoryDashboardRequest(),
        EvidenceOperationsHistoryDashboardCards(reviews_count=2, warnings_count=1),
    )
    view = EvidenceOperationsHistoryView(
        FakeDashboard(result), auto_refresh=False, async_refresh=False
    )
    view._on_dashboard_loaded(result, request_id=view._active_request_id)
    assert view.cards["reviews_count"].text() == "週報紀錄\n2"

    view._on_dashboard_error("database unavailable", request_id=view._active_request_id)

    assert all(card.text().endswith("\n未知") for card in view.cards.values())
    assert view.table_model.rowCount() == 0
    assert view._current_result is None
    assert view.detail_panel.toPlainText() == ""
    assert "允許正式排程" in view.cards["production_scheduler_allowed_count"].text()
    assert view.next_button.isEnabled() is False


def test_evidence_operations_history_ignores_expired_page_response_and_clears_on_loading() -> None:
    app()
    result = EvidenceOperationsHistoryDashboardResult(
        EvidenceOperationsHistoryDashboardRequest(),
        EvidenceOperationsHistoryDashboardCards(reviews_count=1),
    )
    view = EvidenceOperationsHistoryView(FakeDashboard(result), auto_refresh=False, async_refresh=False)
    view._on_dashboard_loaded(result, request_id=view._active_request_id)
    view._active_request_id += 1
    active_id = view._active_request_id
    view._loading = True
    view._current_result = None
    view._set_all_cards("載入中")
    view.table_model.set_rows(())

    view._on_dashboard_loaded(result, request_id=active_id - 1)

    assert view._loading is True
    assert all(card.text().endswith("\n載入中") for card in view.cards.values())
    assert view.table_model.rowCount() == 0


def test_evidence_operations_history_async_load_disables_paging_and_ignores_expired_error() -> None:
    app()
    started = threading.Event()
    release = threading.Event()
    result = EvidenceOperationsHistoryDashboardResult(
        EvidenceOperationsHistoryDashboardRequest(),
        EvidenceOperationsHistoryDashboardCards(reviews_count=1),
    )

    class BlockingHistoryService:
        def load_dashboard(self, _request):
            started.set()
            release.wait(timeout=3)
            return result

    view = EvidenceOperationsHistoryView(
        BlockingHistoryService(), auto_refresh=False, async_refresh=True
    )
    view._set_all_cards("舊資料")
    view.refresh_dashboard()
    active_id = view._active_request_id
    assert started.wait(timeout=1)
    assert view.refresh_button.isEnabled() is False
    assert view.previous_button.isEnabled() is False
    assert view.next_button.isEnabled() is False
    assert all(card.text().endswith("\n載入中") for card in view.cards.values())
    assert view.table_model.rowCount() == 0

    view._on_dashboard_error("expired request", request_id=active_id - 1)
    assert view._loading is True
    assert "載入失敗" not in view.empty_state_label.text()

    release.set()
    deadline = time.monotonic() + 3
    while view._loading and time.monotonic() < deadline:
        QTest.qWait(10)
    assert view._loading is False
    assert view.cards["reviews_count"].text() == "週報紀錄\n1"


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


def test_live_research_gap_quality_distribution_uses_only_service_counts() -> None:
    app()
    rows = (LiveResearchGapDashboardRow(),) * 5
    result = LiveResearchGapDashboardResult(
        LiveResearchGapDashboardRequest(),
        LiveResearchGapDashboardCards(positions_seen=5),
        rows=rows,
        quality_counts={"observed": 2, "degraded": 1, "missing": 1, "future_code": 1},
    )
    service = FakeDashboard(result)
    view = LiveResearchGapView(service, auto_refresh=False, async_refresh=False)
    view.resize(1280, 760)
    for index, quality in enumerate(("observed", "degraded", "missing", "__other__")):
        row, column, _, _ = view.quality_layout.getItemPosition(
            view.quality_layout.indexOf(view.quality_bars[quality])
        )
        count_row, count_column, _, _ = view.quality_layout.getItemPosition(
            view.quality_layout.indexOf(view.quality_counts_labels[quality])
        )
        assert (row, column) == (index // 2, (index % 2) * 3 + 1)
        assert (count_row, count_column) == (row, column + 1)
    view.refresh_dashboard()
    assert "已載入 5 筆" in view.quality_summary_label.text()
    assert "future_code 1" in view.quality_summary_label.text()
    assert view.quality_counts_labels["observed"].text() == "2"
    assert view.quality_counts_labels["degraded"].text() == "1"
    assert view.quality_counts_labels["missing"].text() == "1"
    assert view.quality_counts_labels["__other__"].text() == "1"
    assert view.quality_bars["observed"].maximum() == 5
    assert view.quality_bars["observed"].value() == 2

    # 服務明確提供真零時照原值顯示，不把零改成未知。
    zero_result = LiveResearchGapDashboardResult(
        LiveResearchGapDashboardRequest(),
        LiveResearchGapDashboardCards(positions_seen=1),
        rows=(LiveResearchGapDashboardRow(),),
        quality_counts={"observed": 0, "degraded": 1, "missing": 0},
    )
    view._on_dashboard_loaded(zero_result, request_id=view._active_request_id)
    assert view.quality_counts_labels["observed"].text() == "0"

    # 空集合是成功讀取的 0 筆；診斷則代表來源狀態未知。
    empty_result = LiveResearchGapDashboardResult(
        LiveResearchGapDashboardRequest(), LiveResearchGapDashboardCards(), quality_counts={}
    )
    view._on_dashboard_loaded(empty_result, request_id=view._active_request_id)
    assert "已載入 0 筆" in view.quality_summary_label.text()
    assert all(card.text().endswith("\n0") for card in view.cards.values())
    unavailable = LiveResearchGapDashboardResult(
        LiveResearchGapDashboardRequest(),
        LiveResearchGapDashboardCards(),
        empty_state_message="SQLite 證據來源不可用。",
        limitations=("來源不可用，計數未知。",),
        diagnostics=("sqlite_database_missing",),
    )
    view._on_dashboard_loaded(unavailable, request_id=view._active_request_id)
    assert "未知" in view.quality_summary_label.text()
    assert all(label.text() == "—" for label in view.quality_counts_labels.values())
    assert all(card.text().endswith("\n未知") for card in view.cards.values())
    assert "不可用" in view.empty_state_label.text()
    assert "計數未知" in view.detail_panel.toPlainText()

    for invalid_counts, expected in (
        ({}, "未提供完整品質計數"),
        ({"observed": 2}, "品質計數與已載入列數不一致"),
    ):
        invalid = LiveResearchGapDashboardResult(
            LiveResearchGapDashboardRequest(),
            LiveResearchGapDashboardCards(positions_seen=5),
            rows=rows,
            quality_counts=invalid_counts,
        )
        view._on_dashboard_loaded(invalid, request_id=view._active_request_id)
        assert expected in view.quality_summary_label.text()
        assert all(label.text() == "—" for label in view.quality_counts_labels.values())

    view._on_dashboard_loaded(result, request_id=view._active_request_id)
    started = threading.Event()
    release = threading.Event()

    class BlockingFailingDashboard:
        def load_dashboard(self, _request):
            started.set()
            release.wait(timeout=3)
            raise RuntimeError("synthetic failure")

    view.dashboard_service = BlockingFailingDashboard()
    view.async_refresh = True
    view.refresh_dashboard()
    assert started.wait(timeout=1)
    try:
        assert all(card.text().endswith("\n載入中") for card in view.cards.values())
        assert view.empty_state_label.text() == "研究落差證據載入中…"
        assert view.detail_panel.toPlainText() == "研究落差明細載入中…"
        assert view.table_model.rowCount() == 0
        assert "載入中" in view.quality_summary_label.text()
    finally:
        release.set()
    deadline = time.monotonic() + 3
    while not view.refresh_button.isEnabled() and time.monotonic() < deadline:
        QTest.qWait(10)
    assert "來源載入失敗" in view.quality_summary_label.text()
    assert all(label.text() == "—" for label in view.quality_counts_labels.values())
    assert all(card.text().endswith("\n未知") for card in view.cards.values())
    assert "載入失敗" in view.empty_state_label.text()
    assert view.detail_panel.toPlainText() == ""


def test_live_research_gap_warning_frequency_is_bounded_and_fails_closed() -> None:
    app()
    rows = (
        LiveResearchGapDashboardRow(warnings=("alpha", "beta", "gamma")),
        LiveResearchGapDashboardRow(warnings=("alpha", "beta", "delta")),
        LiveResearchGapDashboardRow(warnings=("epsilon", "zeta")),
    )
    result = LiveResearchGapDashboardResult(
        LiveResearchGapDashboardRequest(),
        LiveResearchGapDashboardCards(positions_seen=3, warnings_count=8),
        rows=rows,
        quality_counts={"missing": 3},
        warning_counts={
            "alpha": 2,
            "beta": 2,
            "gamma": 1,
            "delta": 1,
            "epsilon": 1,
            "zeta": 1,
        },
    )
    service = FakeDashboard(result)
    view = LiveResearchGapView(service, auto_refresh=False, async_refresh=False)
    assert not view.warning_distribution_group.isChecked()
    assert view.warning_summary_label.isHidden()
    assert view.warning_rows_widget.isHidden()
    view.refresh_dashboard()

    assert view.warning_distribution_group.title() == "警示文字頻次（8 次／6 種）"
    assert "同一列可包含多則警示" in view.warning_summary_label.text()
    assert "分母為本次警示出現總次數" in view.warning_summary_label.text()
    displayed_texts = [label.text() for label, _bar, _count in view.warning_bar_rows]
    assert displayed_texts[:5] == ["alpha", "beta", "delta", "epsilon", "gamma"]
    assert "zeta" not in displayed_texts
    assert any("其餘 1 種警示文字：1 次" in text for text in displayed_texts)
    assert all(
        label.textFormat() == Qt.TextFormat.PlainText
        for label, _bar, _count in view.warning_bar_rows[:5]
    )
    assert view.warning_bar_rows[0][1].maximum() == 8
    assert view.warning_bar_rows[0][1].value() == 2
    view.warning_distribution_group.setChecked(True)
    assert not view.warning_summary_label.isHidden()
    assert not view.warning_rows_widget.isHidden()
    view.warning_distribution_group.setChecked(False)
    assert view.warning_summary_label.isHidden()
    assert view.warning_rows_widget.isHidden()

    zero_result = LiveResearchGapDashboardResult(
        LiveResearchGapDashboardRequest(), LiveResearchGapDashboardCards(), warning_counts={}
    )
    view._on_dashboard_loaded(zero_result, request_id=view._active_request_id)
    assert "0 次" in view.warning_summary_label.text()
    assert not view.warning_bar_rows

    invalid_results = (
        LiveResearchGapDashboardResult(
            LiveResearchGapDashboardRequest(),
            LiveResearchGapDashboardCards(positions_seen=3, warnings_count=8),
            rows=rows,
            warning_counts={"alpha": True},
        ),
        LiveResearchGapDashboardResult(
            LiveResearchGapDashboardRequest(),
            LiveResearchGapDashboardCards(positions_seen=3, warnings_count=8),
            rows=rows,
            warning_counts={"   ": 8},
        ),
        LiveResearchGapDashboardResult(
            LiveResearchGapDashboardRequest(),
            LiveResearchGapDashboardCards(positions_seen=3, warnings_count=8),
            rows=rows,
            warning_counts={"alpha": 7},
        ),
        LiveResearchGapDashboardResult(
            LiveResearchGapDashboardRequest(),
            LiveResearchGapDashboardCards(positions_seen=3, warnings_count=8),
            rows=rows,
            warning_counts={
                "alpha": 1,
                "beta": 3,
                "gamma": 1,
                "delta": 1,
                "epsilon": 1,
                "zeta": 1,
            },
        ),
        LiveResearchGapDashboardResult(
            LiveResearchGapDashboardRequest(),
            LiveResearchGapDashboardCards(positions_seen=4, warnings_count=8),
            rows=rows,
            warning_counts={"alpha": 8},
        ),
        LiveResearchGapDashboardResult(
            LiveResearchGapDashboardRequest(),
            LiveResearchGapDashboardCards(positions_seen=3, warnings_count=8),
            rows=rows,
            warning_counts={"alpha": 8},
            diagnostics=("source_incomplete",),
        ),
    )
    for invalid in invalid_results:
        view._on_dashboard_loaded(invalid, request_id=view._active_request_id)
        assert "未知" in view.warning_summary_label.text()
        assert not view.warning_bar_rows

    view._on_dashboard_loaded(result, request_id=view._active_request_id)
    assert view.warning_bar_rows

    class FailingDashboard:
        def load_dashboard(self, _request):
            raise RuntimeError("synthetic failure")

    view.dashboard_service = FailingDashboard()
    view.refresh_dashboard()
    assert "載入失敗" in view.warning_summary_label.text()
    assert not view.warning_bar_rows
    assert view.warning_distribution_group.title() == "警示文字頻次（未知）"


def test_live_research_gap_details_show_trace_ids_from_selected_row() -> None:
    app()
    linked = LiveResearchGapDashboardRow(
        symbol="2330",
        portfolio_mode="simulated",
        source_type="research_run",
        source_id="source-1",
        strategy_version_id="strategy-v1",
        match_confidence="high",
        quality="observed",
        research_run_id="run-1",
        evidence_event_id="event-1",
        evidence_outcome_id="outcome-1",
    )
    missing = LiveResearchGapDashboardRow(
        symbol="2317",
        portfolio_mode="unknown",
        source_type="manual",
        source_id="source-2",
        strategy_version_id="strategy-v2",
        match_confidence="low",
        quality="degraded",
    )
    result = LiveResearchGapDashboardResult(
        LiveResearchGapDashboardRequest(),
        LiveResearchGapDashboardCards(positions_seen=2),
        rows=(linked, missing),
        quality_counts={"observed": 1, "degraded": 1},
    )
    view = LiveResearchGapView(
        FakeDashboard(result), auto_refresh=False, async_refresh=False
    )
    view._on_dashboard_loaded(result, request_id=view._active_request_id)

    details = view.detail_panel.toPlainText()
    assert "來源: research_run / source-1" in details
    assert "策略版本: strategy-v1" in details
    assert "連結信心: high" in details
    assert "Research Run ID: run-1" in details
    assert "Evidence Event ID: event-1" in details
    assert "Evidence Outcome ID: outcome-1" in details
    assert "不表示匹配或來源資格" in details
    assert "Research Run: run-1" in view.trace_summary_label.text()
    assert "Evidence Event: event-1" in view.trace_summary_label.text()
    assert "Evidence Outcome: outcome-1" in view.trace_summary_label.text()
    assert "不表示匹配或來源資格" in view.trace_summary_label.toolTip()

    view._on_table_row_clicked(view.table_model.index(1, 0))
    details = view.detail_panel.toPlainText()
    assert "來源: manual / source-2" in details
    assert "連結信心: low" in details
    assert "Research Run ID: 未提供" in details
    assert "Evidence Event ID: 未提供" in details
    assert "Evidence Outcome ID: 未提供" in details
    assert "run-1" not in details
    assert "event-1" not in details
    assert "outcome-1" not in details
    assert "Research Run: 未提供" in view.trace_summary_label.text()
    assert "run-1" not in view.trace_summary_label.text()


def test_live_research_gap_details_clear_trace_ids_on_empty_refresh_and_error() -> None:
    app()
    linked = LiveResearchGapDashboardRow(
        symbol="2330",
        source_type="research_run",
        source_id="source-1",
        research_run_id="run-1",
        evidence_event_id="event-1",
        evidence_outcome_id="outcome-1",
        match_confidence="high",
    )
    result = LiveResearchGapDashboardResult(
        LiveResearchGapDashboardRequest(),
        LiveResearchGapDashboardCards(positions_seen=1),
        rows=(linked,),
        quality_counts={"observed": 1},
    )
    view = LiveResearchGapView(
        FakeDashboard(result), auto_refresh=False, async_refresh=False
    )
    view._on_dashboard_loaded(result, request_id=view._active_request_id)
    assert "run-1" in view.detail_panel.toPlainText()

    empty_result = LiveResearchGapDashboardResult(
        LiveResearchGapDashboardRequest(), LiveResearchGapDashboardCards()
    )
    view.dashboard_service = FakeDashboard(empty_result)
    view.refresh_dashboard()
    assert view.detail_panel.toPlainText() == ""
    assert "目前沒有可選列" in view.trace_summary_label.text()
    assert all(
        trace_id not in view.detail_panel.toPlainText()
        for trace_id in ("run-1", "event-1", "outcome-1")
    )

    view._on_dashboard_loaded(result, request_id=view._active_request_id)

    class FailingDashboard:
        def load_dashboard(self, _request):
            raise RuntimeError("synthetic failure")

    view.dashboard_service = FailingDashboard()
    view.refresh_dashboard()
    assert view.detail_panel.toPlainText() == ""
    assert "載入失敗" in view.trace_summary_label.text()
    assert all(
        trace_id not in view.detail_panel.toPlainText()
        for trace_id in ("run-1", "event-1", "outcome-1")
    )


class FakeDecisionQualityBackend:
    def __init__(self, reviews=(), items=(), error=None):
        self.reviews = reviews
        self.items = items
        self.error = error

    def list_reviews(self, **_kwargs):
        if self.error is not None:
            raise self.error
        return self.reviews

    def list_items(self, **_kwargs):
        if self.error is not None:
            raise self.error
        return self.items


def _decision_quality_item(*, status="open"):
    return SimpleNamespace(
        review_id="review-1",
        item_type="journal_gap",
        symbol="2330",
        event_date="2026-10-20",
        decision_date="2026-10-20",
        source_type="manual",
        severity="medium",
        status=status,
        suggested_review_question="核對原始依據",
        reason_codes_json=(),
        related_gap_id="",
        related_decay_id="",
        evidence_json={},
        metadata_json={},
    )


def _decision_quality_review(score=0):
    return SimpleNamespace(
        review_period_end="2026-10-20",
        review_id="review-1",
        decision_quality_score_bp=score,
        process_adherence_score_bp=score,
        evidence_usage_score_bp=score,
        risk_discipline_score_bp=score,
        review_completeness_score_bp=score,
        warnings_json=(),
    )


def test_decision_quality_table_model_localizes_known_codes_and_preserves_raw_values() -> None:
    app()
    row = DecisionQualityDashboardService(
        FakeDecisionQualityBackend(
            reviews=(_decision_quality_review(),),
            items=(_decision_quality_item(),),
        )
    ).load_dashboard(DecisionQualityDashboardRequest()).rows[0]
    item_type_labels = {
        "ignored_portfolio_alert": "忽略投資組合警示",
        "manual_override_without_evidence": "缺少依據的手動覆寫",
        "trade_without_source_trace": "交易缺少來源追溯",
        "missed_high_quality_signal": "遺漏高品質訊號",
        "unreviewed_signal_decay": "訊號衰退未覆盤",
        "large_live_research_gap": "實際與研究落差偏大",
        "low_quality_data_used": "使用低品質資料",
        "regime_profile_mismatch": "市場狀態與設定不符",
    }
    model = DecisionQualityTableModel(
        tuple(
            SimpleNamespace(**{**row.__dict__, "item_type": raw, "severity": "high", "status": "reviewed"})
            for raw in item_type_labels
        )
    )

    for row_index, (raw, expected_label) in enumerate(item_type_labels.items()):
        index = model.index(row_index, model.column_index("item_type"))
        assert model.data(index, Qt.DisplayRole) == expected_label
        assert model.data(index, Qt.ToolTipRole) == raw
        assert model.raw_value(row_index, "item_type") == raw
        assert model.data(model.index(row_index, model.column_index("severity")), Qt.DisplayRole) == "高"
        assert model.data(model.index(row_index, model.column_index("status")), Qt.DisplayRole) == "已覆盤"
    assert model.data(model.index(0, model.column_index("severity")), Qt.ToolTipRole) == "high"
    assert model.data(model.index(0, model.column_index("status")), Qt.ToolTipRole) == "reviewed"
    assert model.raw_value(0, "severity") == "high"
    assert model.raw_value(0, "status") == "reviewed"


def test_decision_quality_table_model_keeps_unknown_and_missing_codes_readable() -> None:
    app()
    row = DecisionQualityDashboardService(
        FakeDecisionQualityBackend(
            reviews=(_decision_quality_review(),),
            items=(_decision_quality_item(),),
        )
    ).load_dashboard(DecisionQualityDashboardRequest()).rows[0]
    unknown = SimpleNamespace(
        **{**row.__dict__, "item_type": "future_item", "severity": "urgent", "status": "future_status"}
    )
    missing = SimpleNamespace(**{**row.__dict__, "item_type": "", "severity": "", "status": ""})
    model = DecisionQualityTableModel((unknown, missing))

    for field_name, raw in (("item_type", "future_item"), ("severity", "urgent"), ("status", "future_status")):
        index = model.index(0, model.column_index(field_name))
        assert model.data(index, Qt.DisplayRole) == raw
        assert model.data(index, Qt.ToolTipRole) == raw
        assert model.raw_value(0, field_name) == raw
    for field_name in ("item_type", "severity", "status"):
        index = model.index(1, model.column_index(field_name))
        assert model.data(index, Qt.DisplayRole) == "未知"
        assert model.data(index, Qt.ToolTipRole) == "未知"
        assert model.raw_value(1, field_name) == ""


def test_decision_quality_details_show_labels_and_raw_keys_with_unknown_fallback() -> None:
    app()
    result = DecisionQualityDashboardService(
        FakeDecisionQualityBackend(
            reviews=(_decision_quality_review(),),
            items=(_decision_quality_item(),),
        )
    ).load_dashboard(DecisionQualityDashboardRequest())
    view = DecisionQualityView(FakeDashboard(result), auto_refresh=False, async_refresh=False)
    view._on_dashboard_loaded(result, request_id=view._active_request_id)
    details = view.detail_panel.toPlainText()
    assert "項目類型: journal_gap（未知代碼）" in details
    assert "嚴重度 / 狀態: 中（原始值：medium） / 待處理（原始值：open）" in details

    known_row = SimpleNamespace(
        **{**result.rows[0].__dict__, "item_type": "ignored_portfolio_alert", "severity": "high", "status": "reviewed"}
    )
    view._render_details(known_row, result)
    details = view.detail_panel.toPlainText()
    assert "項目類型: 忽略投資組合警示（原始值：ignored_portfolio_alert）" in details
    assert "嚴重度 / 狀態: 高（原始值：high） / 已覆盤（原始值：reviewed）" in details


def test_decision_quality_dashboard_no_review_marks_scores_missing_and_excludes_orphan_items() -> None:
    app()
    service = DecisionQualityDashboardService(
        FakeDecisionQualityBackend(items=(_decision_quality_item(),))
    )
    result = service.load_dashboard(DecisionQualityDashboardRequest())
    view = DecisionQualityView(FakeDashboard(result), auto_refresh=False, async_refresh=False)
    assert all(card.text().endswith("\n尚未載入") for card in view.cards.values())
    view._on_dashboard_loaded(result, request_id=view._active_request_id)

    assert result.review_count == 0
    assert result.source_available is True
    assert view.cards["decision_quality_score"].text() == "決策品質 / 10000\n未提供"
    assert view.cards["open_items"].text() == "待處理\n0"
    assert view.cards["reviewed_items"].text() == "已覆盤\n0"
    assert view.table_model.rowCount() == 0


@pytest.mark.parametrize(
    ("error", "diagnostic"),
    [
        (FileNotFoundError("review.sqlite3"), "sqlite_database_missing"),
        (sqlite3.OperationalError("no such table: decision_quality_reviews"), "sqlite_evidence_table_missing"),
    ],
)
def test_decision_quality_dashboard_unavailable_source_marks_all_cards_unknown(error, diagnostic) -> None:
    app()
    result = DecisionQualityDashboardService(
        FakeDecisionQualityBackend(error=error)
    ).load_dashboard(DecisionQualityDashboardRequest())
    view = DecisionQualityView(FakeDashboard(result), auto_refresh=False, async_refresh=False)
    view._on_dashboard_loaded(result, request_id=view._active_request_id)

    assert result.source_available is False
    assert result.diagnostics == (diagnostic,)
    assert all(card.text().endswith("\n未知") for card in view.cards.values())
    assert diagnostic in view.empty_state_label.text()


def test_decision_quality_dashboard_observed_zero_scores_and_existing_rows_remain_zero() -> None:
    app()
    result = DecisionQualityDashboardService(
        FakeDecisionQualityBackend(
            reviews=(_decision_quality_review(0),),
            items=(_decision_quality_item(status="reviewed"),),
        )
    ).load_dashboard(DecisionQualityDashboardRequest())
    view = DecisionQualityView(FakeDashboard(result), auto_refresh=False, async_refresh=False)
    view._on_dashboard_loaded(result, request_id=view._active_request_id)

    assert result.review_count == 1
    assert view.cards["decision_quality_score"].text() == "決策品質 / 10000\n0"
    assert view.cards["reviewed_items"].text() == "已覆盤\n1"


def test_decision_quality_dashboard_error_clears_previous_cards_to_unknown() -> None:
    app()
    result = DecisionQualityDashboardResult(
        DecisionQualityDashboardRequest(),
        DecisionQualityDashboardCards(decision_quality_score=4200),
        review_count=1,
    )
    view = DecisionQualityView(FakeDashboard(result), auto_refresh=False, async_refresh=False)
    view._on_dashboard_loaded(result, request_id=view._active_request_id)
    view._on_dashboard_error("database unavailable", request_id=view._active_request_id)

    assert all(card.text().endswith("\n未知") for card in view.cards.values())


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ("abc", "最低分數需為 0–10000 的整數，或留空。"),
        ("-1", "最低分數需介於 0 至 10000，或留空。"),
        ("10001", "最低分數需介於 0 至 10000，或留空。"),
    ],
)
def test_decision_quality_invalid_min_score_clears_stale_dashboard_without_loading(value, message) -> None:
    app()
    result = DecisionQualityDashboardService(
        FakeDecisionQualityBackend(
            reviews=(_decision_quality_review(4200),),
            items=(_decision_quality_item(),),
        )
    ).load_dashboard(DecisionQualityDashboardRequest())
    service = FakeDashboard(result)
    view = DecisionQualityView(service, auto_refresh=False, async_refresh=False)
    view._on_dashboard_loaded(result, request_id=view._active_request_id)
    prior_request_id = view._active_request_id
    assert view.table_model.rowCount() == 1
    assert view.detail_panel.toPlainText()

    # 程式化 setText 仍可能送入 validator 不會接受的內容。
    view.min_score_input.setText(value)
    view.refresh_dashboard()

    assert service.calls == []
    assert view.refresh_button.isEnabled()
    assert view._current_result is None
    assert all(card.text().endswith("\n尚未載入") for card in view.cards.values())
    assert view.table_model.rowCount() == 0
    assert view.detail_panel.toPlainText() == ""
    assert view.empty_state_label.text() == message
    assert view.min_score_error_label.text() == message
    assert not view.min_score_error_label.isHidden()

    view._on_dashboard_loaded(result, request_id=prior_request_id)
    assert view._current_result is None
    assert view.table_model.rowCount() == 0


@pytest.mark.parametrize(("value", "expected"), [("", None), ("0", 0), ("10000", 10000)])
def test_decision_quality_min_score_accepts_blank_and_range_boundaries(value, expected) -> None:
    app()
    result = DecisionQualityDashboardResult(
        DecisionQualityDashboardRequest(),
        DecisionQualityDashboardCards(),
    )
    service = FakeDashboard(result)
    view = DecisionQualityView(service, auto_refresh=False, async_refresh=False)
    view.min_score_input.setText(value)

    view.refresh_dashboard()

    assert len(service.calls) == 1
    assert service.calls[0].min_score == expected
    assert view.min_score_error_label.text() == ""
    assert view.min_score_error_label.isHidden()


def test_decision_quality_scope_hints_and_scrollable_filter_keep_refresh_visible() -> None:
    """模擬 Main 外層長頁，確認內層篩選可捲且刷新按鈕仍在首屏。"""

    app_instance = app()
    result = DecisionQualityDashboardResult(
        DecisionQualityDashboardRequest(),
        DecisionQualityDashboardCards(decision_quality_score=4000),
    )
    service = FakeDashboard(result)
    outer_scroll = QScrollArea()
    outer_scroll.setWidgetResizable(False)
    outer_scroll.resize(1280, 760)
    outer_page = QWidget()
    outer_page.resize(1260, 1500)
    view = DecisionQualityView(
        service,
        auto_refresh=False,
        async_refresh=False,
        parent=outer_page,
    )
    view.setGeometry(0, 0, 1260, 1400)
    outer_scroll.setWidget(outer_page)
    outer_scroll.show()
    app_instance.processEvents()
    # Offscreen Qt may expose a much taller virtual screen than the native
    # 1280×760 window; constrain this fixture to the narrow visible pane.
    view.filter_panel.setMaximumHeight(360)
    app_instance.processEvents()

    assert "只篩下方項目列" in view.symbol_scope_hint.text()
    assert "不是單股分數" in view.symbol_scope_hint.text()
    assert "最新整體分數" in view.symbol_scope_hint.text()
    assert "篩選後最新覆盤的整體決策品質分數" in view.min_score_scope_hint.text()
    assert "不是逐項分數" in view.min_score_scope_hint.text()
    assert "只清空項目列" in view.min_score_scope_hint.text()
    assert "分數卡保留原分數" in view.min_score_scope_hint.text()
    assert isinstance(view.filter_scroll_area, QScrollArea)
    assert outer_scroll.verticalScrollBar().maximum() > 0
    assert outer_scroll.verticalScrollBar().value() == 0
    assert view.filter_panel is not None
    assert view.filter_panel.height() <= view.filter_panel.maximumHeight()
    assert view.filter_scroll_area.verticalScrollBar().maximum() > 0
    assert view.filter_scroll_area.horizontalScrollBar().maximum() == 0
    filter_viewport = view.filter_scroll_area.viewport()
    filter_controls = (
        view.review_type_input,
        view.start_date_input,
        view.end_date_input,
        view.symbol_input,
        view.portfolio_id_input,
        view.item_type_input,
        view.severity_combo,
        view.status_combo,
        view.min_score_input,
    )
    for control in filter_controls:
        control_top_left = control.mapTo(filter_viewport, QPoint(0, 0))
        assert control_top_left.x() >= 0
        assert control_top_left.x() + control.width() <= filter_viewport.width()
    assert view.refresh_button.parentWidget() is view.filter_scroll_area.parentWidget()
    assert view.refresh_button.y() >= (
        view.filter_scroll_area.y() + view.filter_scroll_area.height()
    )

    # The normal Main page has content above Decision Quality. Bring this
    # section into the outer viewport before checking its sticky action.
    outer_scroll.ensureWidgetVisible(view.refresh_button)
    app_instance.processEvents()
    assert outer_scroll.verticalScrollBar().value() > 0

    view.filter_scroll_area.ensureWidgetVisible(view.min_score_input)
    app_instance.processEvents()
    viewport = view.filter_scroll_area.viewport()
    min_score_top = view.min_score_input.mapTo(viewport, QPoint(0, 0))
    assert 0 <= min_score_top.y()
    assert min_score_top.y() + view.min_score_input.height() <= viewport.height()

    viewport = outer_scroll.viewport()
    refresh_top = view.refresh_button.mapTo(viewport, QPoint(0, 0))
    refresh_rect = view.refresh_button.rect().translated(refresh_top)
    assert viewport.rect().contains(refresh_rect)

    view.symbol_input.setText("2330")
    view.min_score_input.setText("6000")
    view.refresh_button.click()
    assert service.calls[-1].symbol == "2330"
    assert service.calls[-1].min_score == 6000
    outer_scroll.close()
