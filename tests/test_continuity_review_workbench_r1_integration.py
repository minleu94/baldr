"""Producer-backed R1 integration evidence for the Workbench continuity loop."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from zoneinfo import ZoneInfo

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import QPoint, QDateTime
from PySide6.QtTest import QTest
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QScrollArea

from app_module.continuity_review_projection import (
    CONTINUITY_DUE,
    CONTINUITY_DUE_SCHEDULED,
)
from app_module.decision_continuity_controller import DecisionContinuityController
from app_module.decision_outcome_journey import DecisionOutcomeJourneyService
from app_module.dtos import RecommendationDTO, RecommendationResultDTO
from app_module.dtos.decision_continuity_dtos import (
    ACTION_ACCEPTED,
    DecisionIdentity,
)
from app_module.evidence_event_dtos import (
    EvidenceDataQuality,
    EvidenceEvent,
    EvidenceEventType,
    EvidenceOutcome,
    EvidenceOutcomeStatus,
)
from app_module.evidence_event_repository import EvidenceEventRepository
from app_module.journal_service import JournalService
from app_module.recommendation_repository import RecommendationRepository
from app_module.stock_research_report_service import StockResearchReportReadService
from app_module.workbench_source_service import WorkbenchSourceService
from app_module.research_session import ResearchStockContextDTO
from data_module.config import TWStockConfig
from ui_qt.theme import build_global_stylesheet
from ui_qt.theme.fonts import (
    preferred_qt_chinese_font_family,
    register_qt_chinese_fonts,
)
from ui_qt.views.stock_research_report_view import StockResearchReportDialog
from ui_qt.views.workbench_view import UnifiedDecisionWorkbenchView


ROOT = Path(__file__).resolve().parents[1]
TAIPEI = ZoneInfo("Asia/Taipei")
FIXTURE_DECISION_DATE = "2026-01-05"
FIXTURE_OUTCOME_DATE = "2026-01-12"
FIXTURE_OUTCOME_CALCULATED_AT = "2026-01-12T18:00:00+08:00"


def _app() -> QApplication:
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication([])
    instance.setStyle("Fusion")
    families = register_qt_chinese_fonts()
    preferred_family = preferred_qt_chinese_font_family(families)
    if preferred_family:
        instance.setFont(QFont(preferred_family, instance.font().pointSize()))
    instance.setStyleSheet(build_global_stylesheet())
    return instance


def _wait_for(predicate, timeout_ms: int = 8_000) -> None:
    app = QApplication.instance() or _app()
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        QTest.qWait(10)
    assert predicate()


def _config(tmp_path: Path) -> TWStockConfig:
    config = TWStockConfig(
        data_root=tmp_path / "data",
        output_root=tmp_path / "output",
    )
    config.db_file = tmp_path / "evidence.db"
    config.research_run_db_file = tmp_path / "research_runs.db"
    config.use_sqlite = True
    return config


def _recommendation(result_id: str, stocks: tuple[str, ...]) -> RecommendationResultDTO:
    names = {"2330": "台積電", "2317": "鴻海"}
    config = {
        "decision_date": FIXTURE_DECISION_DATE,
        "source_id": f"producer.{result_id}",
        "source_snapshot_id": f"snap-{result_id}",
        "source_snapshot_hash": f"hash-{result_id}",
        "strategy_version_id": "integration-strategy-v1",
        "strategy_config_id": "integration-config-v1",
    }
    return RecommendationResultDTO(
        result_id=result_id,
        result_name=f"producer-backed {result_id}",
        config=config,
        recommendations=[
            RecommendationDTO(
                stock_code=stock_code,
                stock_name=names.get(stock_code, stock_code),
                close_price=Decimal("1000") if stock_code == "2330" else Decimal("200"),
                price_change=Decimal("1.2"),
                total_score=Decimal("90"),
                indicator_score=Decimal("30"),
                pattern_score=Decimal("30"),
                volume_score=Decimal("30"),
                recommendation_reasons="producer-backed integration candidate",
                industry="半導體" if stock_code == "2330" else "電子",
                regime_match=True,
            )
            for stock_code in stocks
        ],
        regime="Trend",
        created_at="2026-09-10T09:00:00+08:00",
    )


def _seed_recommendations(config: TWStockConfig) -> dict[str, tuple[str, ...]]:
    repository = RecommendationRepository(config)
    results = {
        "R1": ("2330",),
        "R2": ("2330",),
        "R3": ("2330", "2317"),
    }
    for result_id, stocks in results.items():
        assert repository.save_result(_recommendation(result_id, stocks)) == result_id
    return results


def _seed_evidence(config: TWStockConfig, results: dict[str, tuple[str, ...]]) -> None:
    repository = EvidenceEventRepository(config, db_path=config.db_file)
    for result_id, stocks in results.items():
        for stock_code in stocks:
            event_id = f"evt-{result_id}-{stock_code}"
            event = repository.insert_event(
                EvidenceEvent(
                    event_id=event_id,
                    event_hash=f"sha256:{event_id}",
                    event_date=FIXTURE_DECISION_DATE,
                    decision_date=FIXTURE_DECISION_DATE,
                    symbol=stock_code,
                    event_type=EvidenceEventType.RECOMMENDATION_INCLUDED,
                    event_family="recommendation",
                    source_type="recommendation_result",
                    source_id=result_id,
                    source_snapshot_id=f"snap-{result_id}",
                    strategy_version_id="integration-strategy-v1",
                    profile_id="integration-profile-v1",
                    data_quality=EvidenceDataQuality.OBSERVED,
                    as_of_date=FIXTURE_DECISION_DATE,
                    available_date=f"{FIXTURE_DECISION_DATE}T09:01:00+08:00",
                    source_version="producer-backed-integration-v1",
                    metadata={
                        "source_result_id": result_id,
                        "is_execution_pnl": False,
                    },
                    created_at=f"{FIXTURE_DECISION_DATE}T09:01:00+08:00",
                )
            )
            repository.upsert_outcome(
                EvidenceOutcome(
                    outcome_id=f"out-{event_id}-5",
                    event_id=event.event_id,
                    window_days=5,
                    forward_return_bp=120,
                    outcome_status=EvidenceOutcomeStatus.READY,
                    data_quality=EvidenceDataQuality.OBSERVED,
                    event_price_date=FIXTURE_DECISION_DATE,
                    outcome_price_date=FIXTURE_OUTCOME_DATE,
                    data_as_of_date=FIXTURE_OUTCOME_DATE,
                    calculated_at=FIXTURE_OUTCOME_CALCULATED_AT,
                    metadata={"is_execution_pnl": False},
                )
            )
            repository.upsert_outcome(
                EvidenceOutcome(
                    outcome_id=f"out-{event_id}-10",
                    event_id=event.event_id,
                    window_days=10,
                    outcome_status=EvidenceOutcomeStatus.PENDING,
                    data_quality=EvidenceDataQuality.OBSERVED,
                    calculated_at=FIXTURE_OUTCOME_CALCULATED_AT,
                    metadata={"is_execution_pnl": False},
                )
            )


def _seed_continuity(
    config: TWStockConfig,
    results: dict[str, tuple[str, ...]],
) -> tuple[DecisionContinuityController, JournalService, datetime, str]:
    journal_service = JournalService(config)
    controller = DecisionContinuityController(journal_service)
    clock = datetime.now(TAIPEI)
    first_review = (clock + timedelta(hours=2)).isoformat(timespec="seconds")
    for result_id, stocks in results.items():
        for stock_code in stocks:
            identity = DecisionIdentity(
                result_id=result_id,
                stock_code=stock_code,
                source_snapshot_id=f"snap-{result_id}",
                source_snapshot_hash=f"hash-{result_id}",
                decision_date=FIXTURE_DECISION_DATE,
                identity_status="linked",
            )
            accepted = controller.accept(identity, request_id=f"accept-{result_id}-{stock_code}")
            assert accepted.success is True
            scheduled = controller.schedule_review(
                identity,
                next_review_at=first_review,
                request_id=f"review-{result_id}-{stock_code}",
            )
            assert scheduled.success is True
    return controller, journal_service, clock, first_review


def _continuity_rows(dashboard):
    return tuple(
        item for item in dashboard.review_items if item.source == "continuity_review"
    )


def _row_for(rows, result_id: str, stock_code: str):
    return next(
        item
        for item in rows
        if item.result_id == result_id and item.stock_code == stock_code
    )


def test_producer_backed_workbench_to_shared_report_journey_and_readback(
    tmp_path: Path,
) -> None:
    """Exercise the normal composition with real producer repositories and Qt."""

    config = _config(tmp_path)
    results = _seed_recommendations(config)
    _seed_evidence(config, results)
    controller, journal_service, clock, first_review = _seed_continuity(config, results)
    journal_path = Path(config.output_root) / "portfolio" / "journal_entries.jsonl"
    before_click = journal_path.read_bytes()

    source_service = WorkbenchSourceService(config)
    # decision_date is intentionally historical while continuity_as_of=None is
    # the live Workbench clock.  The explicit clock below is a controlled
    # replay boundary and is never inferred from dashboard.as_of_date.
    live_dashboard = source_service.inspect(decision_date=FIXTURE_DECISION_DATE)
    live_rows = _continuity_rows(live_dashboard)
    assert {
        item.candidate_key for item in live_rows
    } == {
        "R1:2330",
        "R2:2330",
        "R3:2330",
        "R3:2317",
    }
    live_r1 = _row_for(live_rows, "R1", "2330")
    assert live_dashboard.as_of_date == date.today()
    assert live_r1.due_status == CONTINUITY_DUE_SCHEDULED
    assert live_r1.next_review_at == first_review
    assert "股票 2330" in live_r1.summary
    assert "研究意向：已納入研究" in live_r1.summary
    assert f"檢討時間（台北）：{first_review}" in live_r1.summary
    assert "待檢討原因：尚未到檢討時間" in live_r1.summary
    assert "candidate=" not in live_r1.summary
    assert "hash-" not in live_r1.summary

    replay_as_of = datetime.fromisoformat(first_review) + timedelta(seconds=1)
    replay_dashboard = source_service.inspect(
        decision_date=FIXTURE_DECISION_DATE,
        continuity_as_of=replay_as_of,
    )
    replay_r1 = _row_for(_continuity_rows(replay_dashboard), "R1", "2330")
    assert replay_r1.due_status == CONTINUITY_DUE
    assert replay_r1.next_review_at == first_review
    # The dashboard date is a market/decision surface date; the reminder's
    # actual cutoff remains its own DTO field and is visible in the summary.
    assert replay_dashboard.as_of_date == live_dashboard.as_of_date

    journey_service = DecisionOutcomeJourneyService.from_config(
        config,
        journal_path=journal_path,
        portfolio_trades_path=Path(config.output_root) / "portfolio" / "trades.jsonl",
    )
    journey = journey_service.build("R1")
    maturity = {item.window_days: item for item in journey.outcome_maturity}
    assert journey.recommendation_result.result_id == "R1"
    assert maturity[5].candidate_key == ("R1", "2330")
    assert maturity[5].outcome_status == "ready"
    assert maturity[10].outcome_status == "pending"

    report_service = StockResearchReportReadService(config)
    contexts: list[ResearchStockContextDTO] = []
    dialogs: list[StockResearchReportDialog] = []

    def open_shared_report(value: object) -> None:
        assert isinstance(value, ResearchStockContextDTO)
        contexts.append(value)
        dialog = StockResearchReportDialog(
            report_service,
            value,
            journey_service=journey_service,
            continuity_controller=controller,
        )
        dialogs.append(dialog)
        dialog.show()

    app = _app()
    view = UnifiedDecisionWorkbenchView(
        # Render the explicit replay boundary so the acceptance artifact
        # visibly contains due reminders; the live clock was asserted above.
        dashboard=replay_dashboard,
        auto_refresh=False,
        navigate_to_stock_research_callback=open_shared_report,
    )
    view.resize(1366, 768)
    view.show()
    app.processEvents()
    visible_scroll_areas = [
        area for area in view.findChildren(QScrollArea) if area.isVisible()
    ]
    assert visible_scroll_areas
    scroll_area = visible_scroll_areas[0]
    index = next(
        index
        for index in range(view.review_model.rowCount())
        if view.review_model.row_at(index).candidate_key == "R1:2330"
    )
    selected_row = view.review_model.row_at(index)
    assert selected_row.due_status == CONTINUITY_DUE
    view._show_model_row_detail(view.review_model, index)
    assert "檢討時間（台北）" in view.detail_summary_box.text()
    assert "研究意向：已納入研究" in view.detail_summary_box.text()
    review_top = view.review_table.mapTo(scroll_area.widget(), QPoint(0, 0)).y()
    scroll_area.verticalScrollBar().setValue(review_top)
    app.processEvents()
    scroll_area.viewport().update()
    scroll_area.repaint()
    QTest.qWait(100)
    screenshot_path = Path(
        os.environ.get(
            "CONTINUITY_REVIEW_WORKBENCH_SCREENSHOT_PATH",
            str(tmp_path / "continuity_review_workbench_1366x768.png"),
        )
    ).expanduser().resolve()
    screenshot_path.parent.mkdir(parents=True, exist_ok=True)
    assert view.grab().size().width() == 1366
    assert view.grab().size().height() == 768
    assert view.grab().save(str(screenshot_path))

    view._navigate_model_row(view.review_model, index)
    _wait_for(lambda: len(contexts) == 1 and bool(dialogs))
    dialog = dialogs[0]
    _wait_for(
        lambda: dialog.journey_view is not None
        and dialog.journey_view.journey is not None
        and not dialog.is_busy(),
        # Functional completion bound, not a product latency SLA. The isolated
        # current/baseline no-follow read completed at 8.109/8.141 seconds.
        timeout_ms=15_000,
    )
    assert contexts[0].result_id == "R1"
    assert contexts[0].stock_code == "2330"
    assert contexts[0].source_snapshot_hash == "hash-R1"
    assert dialog.journey_view is not None
    assert dialog.journey_view.journey is not None
    assert dialog.journey_view.journey.recommendation_result.result_id == "R1"
    rendered_maturity = {
        dialog.journey_view.maturity_table.model().index(row, 0).data():
        dialog.journey_view.maturity_table.model().index(row, 2).data()
        for row in range(dialog.journey_view.maturity_table.model().rowCount())
    }
    assert rendered_maturity["5個交易日"] == "來源已標示 ready"
    assert rendered_maturity["10個交易日"] == "pending"
    assert dialog.journey_view.continuity_controls is not None
    controls = dialog.journey_view.continuity_controls
    assert controls.identity is not None
    assert controls.identity.candidate_key == ("R1", "2330")
    assert controls.state is not None
    assert controls.state.next_review_at == first_review
    assert journal_path.read_bytes() == before_click
    assert hashlib.sha256(journal_path.read_bytes()).hexdigest() == hashlib.sha256(
        before_click
    ).hexdigest()

    # This is the explicit user action after the read-only drilldown.  A new
    # process must be able to read the new head without relying on this Qt
    # object graph or a cached projection.
    journey_screenshot_path = Path(
        os.environ.get(
            "CONTINUITY_REVIEW_JOURNEY_SCREENSHOT_PATH",
            str(tmp_path / "continuity_review_journey_1366x768.png"),
        )
    ).expanduser().resolve()
    dialog.resize(1366, 768)
    dialog.dialog_tabs.setCurrentIndex(1)
    app.processEvents()
    assert dialog.grab().size().width() == 1366
    assert dialog.grab().size().height() == 768
    journey_screenshot_path.parent.mkdir(parents=True, exist_ok=True)
    assert dialog.grab().save(str(journey_screenshot_path))

    # Trigger the reschedule through the real shared controls, not by calling
    # the controller directly.  The controls must preserve the exact identity
    # and append a new Journal head only after this explicit user action.
    second_review = (clock + timedelta(hours=3)).isoformat(timespec="seconds")
    controls.review_datetime.setDateTime(
        QDateTime.fromString(second_review[:19].replace("T", " "), "yyyy-MM-dd HH:mm:ss")
    )
    controls.review_button.click()
    assert controls.state is not None
    assert controls.state.next_review_at == second_review
    assert journal_path.read_bytes() != before_click
    subprocess_code = (
        "import json, sys; "
        "from pathlib import Path; "
        "from app_module.continuity_review_projection import ContinuityReviewProjectionService; "
        "result = ContinuityReviewProjectionService(Path(sys.argv[1])).project(as_of=sys.argv[2]); "
        "print(json.dumps([item.to_dict() for item in result.items], ensure_ascii=False))"
    )
    readback = subprocess.run(
        [
            sys.executable,
            "-c",
            subprocess_code,
            str(journal_path),
            (datetime.now().astimezone() + timedelta(minutes=1)).isoformat(),
        ],
        cwd=ROOT,
        env=dict(os.environ, PYTHONIOENCODING="utf-8"),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        timeout=10,
    )
    assert readback.returncode == 0, readback.stderr
    readback_items = json.loads(readback.stdout)
    readback_r1 = next(
        item
        for item in readback_items
        if item["candidate_key"] == "R1:2330"
    )
    assert readback_r1["next_review_at"] == second_review
    assert readback_r1["candidate_key"] == "R1:2330"
    assert readback_r1["revision_id"] == controls.state.head_revision_id
    assert readback_r1["reminder_revision_id"] == controls.state.head_revision_id
    assert readback_r1["decision_status"] == "accepted"
    assert readback_r1["source_snapshot_hash"] == "hash-R1"

    receipt_path = Path(
        os.environ.get(
            "CONTINUITY_REVIEW_BUSY_CLOSE_RECEIPT_PATH",
            str(tmp_path / "continuity_review_busy_close_receipt.json"),
        )
    ).expanduser().resolve()
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    busy_close = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "qa_continuity_review_workbench_busy_close.py"),
            "--data-root",
            str(config.data_root),
            "--output-root",
            str(config.output_root),
            "--db-file",
            str(config.db_file),
            "--result-id",
            "R1",
            "--stock-code",
            "2330",
            "--receipt",
            str(receipt_path),
        ],
        cwd=ROOT,
        env=dict(os.environ, PYTHONIOENCODING="utf-8"),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        timeout=15,
    )
    assert busy_close.returncode == 0, busy_close.stderr or busy_close.stdout
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["pid"] > 0
    assert receipt["close_requested_while_busy"] is True
    assert receipt["dialog_finished"] is True
    assert receipt["app_exec_returncode"] == 0
    assert receipt["process_exit_code"] == 0

    dialog.close()
    view.close()
    app.processEvents()
