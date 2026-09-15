"""R1 acceptance tests for exact continuity reminders and Workbench routing."""

import os
import json
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app_module.continuity_review_projection import (
    CONTINUITY_DUE,
    CONTINUITY_DUE_INVALID,
    CONTINUITY_DUE_SCHEDULED,
    CONTINUITY_STREAM_INVALID,
    ContinuityReviewItem,
    ContinuityReviewProjectionResult,
    ContinuityReviewProjectionService,
)
from app_module.decision_outcome_journey import (
    DecisionOutcomeJourneyService,
    JourneyLinkStatus,
)
from app_module.dtos.decision_continuity_dtos import (
    ACTION_ACCEPTED,
    ACTION_CLEARED,
    ACTION_REVIEW_SCHEDULED,
    ACTION_SKIPPED,
    DecisionContinuityRevision,
    DecisionIdentity,
)
from app_module.portfolio_store import PortfolioJsonlStore
from app_module.pre_v2_readiness_service import PreV2ReadinessReport, STATUS_READY
from app_module.workbench_dtos import (
    WorkbenchAccessBoundary,
    WorkbenchDashboardDTO,
    WorkbenchReviewItem,
    WorkbenchStatusItem,
)
from app_module.workbench_read_only_composer import WorkbenchReadOnlyComposer
from ui_qt.views.portfolio_view import PortfolioView
from ui_qt.views.workbench_view import UnifiedDecisionWorkbenchView


def _journal_path(tmp_path: Path) -> Path:
    return tmp_path / "output" / "portfolio" / "journal_entries.jsonl"


def _append_revision(
    store: PortfolioJsonlStore,
    *,
    revision_id: str,
    action: str,
    created_at: str,
    revision_of: str = "",
    result_id: str = "R1",
    stock_code: str = "2330",
    next_review_at: str = "",
    identity_status: str = "linked",
    source_snapshot_id: str = "snap-1",
    source_snapshot_hash: str = "hash-1",
    decision_date: str = "2026-09-15",
) -> None:
    identity = DecisionIdentity(
        result_id=result_id,
        stock_code=stock_code,
        source_snapshot_id=source_snapshot_id,
        source_snapshot_hash=source_snapshot_hash,
        decision_date=decision_date,
        identity_status=identity_status,
    )
    entity_id = f"decision-candidate:{result_id}:{stock_code}"
    revision = DecisionContinuityRevision(
        revision_id=revision_id,
        continuity_event_id=revision_id,
        action=action,
        entity_type="decision",
        entity_id=entity_id,
        decision_identity=identity,
        revision_of=revision_of,
        next_review_at=next_review_at,
        created_at=created_at,
    )
    store.append_journal_revision(revision.to_dict())


def _ready_report() -> PreV2ReadinessReport:
    return PreV2ReadinessReport(
        generated_at="2026-09-15T12:00:00+08:00",
        overall_status=STATUS_READY,
        production_scheduler_allowed=False,
        items=(),
        limitations=(),
    )


class _JourneyRecommendationReader:
    def __init__(self, payload: Mapping[str, Any]) -> None:
        self.payload = dict(payload)

    def read_result(self, result_id: str) -> Mapping[str, Any] | None:
        return self.payload if self.payload.get("result_id") == result_id else None

    def result_path(self, result_id: str) -> str | None:
        return None if result_id == str(self.payload.get("result_id")) else None


class _JourneyEvidenceReader:
    def __init__(self, event: Mapping[str, Any]) -> None:
        self.event = dict(event)

    def list_events(self, *, decision_date: str | None = None) -> tuple[Mapping[str, Any], ...]:
        del decision_date
        return (self.event,)

    def list_outcomes(self, *, event_id: str) -> tuple[Mapping[str, Any], ...]:
        del event_id
        return ()


def _journey_root(*, include_snapshot: bool = True) -> dict[str, Any]:
    config: dict[str, Any] = {
        "decision_date": "2026-01-05",
        "source_snapshot_hash": "hash-R1",
    }
    if include_snapshot:
        config["source_snapshot_id"] = "snap-R1"
    return {
        "result_id": "R1",
        "created_at": "2026-01-05T09:00:00+08:00",
        "config": config,
        "recommendations": [{"stock_code": "2330", "stock_name": "台積電"}],
    }


def _journey_event(
    *,
    source_id: str | None,
    source_snapshot_id: str | None,
    metadata_result_id: str | None,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    if metadata_result_id is not None:
        metadata["source_result_id"] = metadata_result_id
    return {
        "event_id": "event-R1-2330",
        "event_hash": "sha256:event-R1-2330",
        "event_date": "2026-01-05",
        "decision_date": "2026-01-05",
        "symbol": "2330",
        "event_type": "recommendation_included",
        "event_family": "recommendation",
        "source_type": "recommendation_result",
        "source_id": source_id,
        "source_snapshot_id": source_snapshot_id,
        "available_date": "2026-01-05T09:01:00+08:00",
        "created_at": "2026-01-05T09:01:00+08:00",
        "metadata": metadata,
    }


def test_evidence_snapshot_is_consistency_check_not_a_standalone_join_key() -> None:
    cases = (
        # A valid result discriminator plus the same root snapshot is linked.
        (True, True, "R1", "snap-R1", "R1", JourneyLinkStatus.LINKED),
        # A matching snapshot cannot rescue a different result identity.
        (True, True, "R2", "snap-R1", "R2", JourneyLinkStatus.UNLINKED),
        # A matching snapshot cannot replace a missing result discriminator.
        (True, True, None, "snap-R1", None, JourneyLinkStatus.UNLINKED),
        # An exact result with a known, different snapshot fails closed.
        (True, True, "R1", "snap-other", "R1", JourneyLinkStatus.CONFLICT),
        # If the root has no snapshot, snapshot-only evidence is still unlinked.
        (False, False, None, "snap-R1", None, JourneyLinkStatus.UNLINKED),
        # A root without a snapshot can still use its explicit result key; the
        # missing snapshot is unknown, not a reason to invent a different join.
        (False, False, "R1", "snap-R1", "R1", JourneyLinkStatus.LINKED),
    )
    for include_snapshot, _unused, source_id, source_snapshot_id, metadata_result_id, expected in cases:
        service = DecisionOutcomeJourneyService(
            recommendation_reader=_JourneyRecommendationReader(
                _journey_root(include_snapshot=include_snapshot)
            ),
            evidence_reader=_JourneyEvidenceReader(
                _journey_event(
                    source_id=source_id,
                    source_snapshot_id=source_snapshot_id,
                    metadata_result_id=metadata_result_id,
                )
            ),
        )
        journey = service.build("R1")
        if expected is JourneyLinkStatus.UNLINKED:
            assert journey.evidence_events == ()
            assert journey.coverage.evidence_unlinked == 1
        else:
            assert len(journey.evidence_events) == 1
            assert journey.evidence_events[0].link_status is expected


def test_projection_keeps_historical_due_state_before_future_reschedule_and_intent_change(
    tmp_path: Path,
) -> None:
    journal_path = _journal_path(tmp_path)
    store = PortfolioJsonlStore(journal_path.parents[1])
    _append_revision(
        store,
        revision_id="r-accepted",
        action=ACTION_ACCEPTED,
        created_at="2026-09-10T01:00:00+00:00",
    )
    _append_revision(
        store,
        revision_id="r-review",
        action=ACTION_REVIEW_SCHEDULED,
        revision_of="r-accepted",
        created_at="2026-09-10T02:00:00+00:00",
        next_review_at="2026-09-15T09:00:00+08:00",
    )
    _append_revision(
        store,
        revision_id="r-skipped-later",
        action=ACTION_SKIPPED,
        revision_of="r-review",
        created_at="2026-09-16T02:00:00+00:00",
    )
    _append_revision(
        store,
        revision_id="r-review-later",
        action=ACTION_REVIEW_SCHEDULED,
        revision_of="r-skipped-later",
        created_at="2026-09-16T03:00:00+00:00",
        next_review_at="2026-09-30T09:00:00+08:00",
    )

    projection = ContinuityReviewProjectionService(journal_path)
    historical = projection.project(as_of="2026-09-15T12:00:00+08:00")
    current = projection.project(as_of="2026-09-17T12:00:00+08:00")

    assert len(historical.items) == 1
    assert historical.items[0].candidate_key == ("R1", "2330")
    assert historical.items[0].decision_status == "accepted"
    assert historical.items[0].due_status == CONTINUITY_DUE
    assert historical.items[0].reminder_revision_id == "r-review"
    assert historical.items[0].next_review_at == "2026-09-15T09:00:00+08:00"

    assert len(current.items) == 1
    assert current.items[0].decision_status == "skipped"
    assert current.items[0].due_status == CONTINUITY_DUE_SCHEDULED
    assert current.items[0].reminder_revision_id == "r-review-later"


def test_projection_normalizes_same_instant_timezones_and_future_clear_does_not_change_past(
    tmp_path: Path,
) -> None:
    journal_path = _journal_path(tmp_path)
    store = PortfolioJsonlStore(journal_path.parents[1])
    _append_revision(
        store,
        revision_id="r-accepted",
        action=ACTION_ACCEPTED,
        created_at="2026-09-10T01:00:00+00:00",
    )
    _append_revision(
        store,
        revision_id="r-review",
        action=ACTION_REVIEW_SCHEDULED,
        revision_of="r-accepted",
        created_at="2026-09-10T02:00:00+00:00",
        next_review_at="2026-09-15T01:00:00+00:00",
    )
    _append_revision(
        store,
        revision_id="r-cleared-later",
        action=ACTION_CLEARED,
        revision_of="r-review",
        created_at="2026-09-16T02:00:00+00:00",
    )

    projection = ContinuityReviewProjectionService(journal_path)
    same_instant = projection.project(as_of="2026-09-15T01:00:00+00:00")
    past_before_clear = projection.project(as_of="2026-09-15T12:00:00+08:00")
    current_after_clear = projection.project(as_of="2026-09-17T12:00:00+08:00")

    assert same_instant.items[0].due_status == CONTINUITY_DUE
    assert same_instant.items[0].next_review_at == "2026-09-15T09:00:00+08:00"
    assert past_before_clear.items[0].reminder_revision_id == "r-review"
    assert current_after_clear.items == ()


def test_projection_fail_closes_invalid_schedule_missing_stream_and_unknown_identity(
    tmp_path: Path,
) -> None:
    missing = ContinuityReviewProjectionService(_journal_path(tmp_path)).project(
        as_of="2026-09-15T12:00:00+08:00"
    )
    assert missing.items == ()
    assert missing.stream_status == "missing"

    journal_path = _journal_path(tmp_path)
    store = PortfolioJsonlStore(journal_path.parents[1])
    _append_revision(
        store,
        revision_id="r-invalid",
        action=ACTION_REVIEW_SCHEDULED,
        created_at="2026-09-10T02:00:00+00:00",
        next_review_at="2026-09-15T09:00:00",
    )
    invalid = ContinuityReviewProjectionService(journal_path).project(
        as_of="2026-09-15T12:00:00+08:00"
    )
    assert invalid.items[0].due_status == CONTINUITY_DUE_INVALID
    assert "next_review_at_requires_timezone" in invalid.items[0].diagnostics

    unknown_path = tmp_path / "unknown" / "portfolio" / "journal_entries.jsonl"
    unknown_store = PortfolioJsonlStore(unknown_path.parents[1])
    _append_revision(
        unknown_store,
        revision_id="r-unknown",
        action=ACTION_REVIEW_SCHEDULED,
        created_at="2026-09-10T02:00:00+00:00",
        result_id="",
        identity_status="unknown",
        next_review_at="2026-09-15T09:00:00+08:00",
    )
    unknown = ContinuityReviewProjectionService(unknown_path).project(
        as_of="2026-09-15T12:00:00+08:00"
    )
    assert unknown.items == ()
    assert any("identity_skipped" in item for item in unknown.diagnostics)


def test_projection_invalid_utf8_and_chain_conflict_return_diagnostics_not_exceptions(
    tmp_path: Path,
) -> None:
    invalid_path = _journal_path(tmp_path)
    invalid_path.parent.mkdir(parents=True)
    invalid_path.write_bytes(b"\xff\xfe\n")
    invalid = ContinuityReviewProjectionService(invalid_path).project(
        as_of="2026-09-15T12:00:00+08:00"
    )
    assert invalid.items == ()
    assert invalid.stream_status == CONTINUITY_STREAM_INVALID
    assert any("UnicodeDecodeError" in item for item in invalid.diagnostics)

    conflict_path = tmp_path / "conflict" / "portfolio" / "journal_entries.jsonl"
    conflict_path.parent.mkdir(parents=True)
    conflict_path.write_text(
        json.dumps(
            {
                "record_type": "decision_continuity_revision",
                "revision_id": "r-conflict",
                "continuity_event_id": "r-conflict",
                "action": ACTION_REVIEW_SCHEDULED,
                "entity_type": "decision",
                "entity_id": "decision-candidate:R1:2330",
                "result_id": "R2",
                "stock_code": "2330",
                "decision_identity": {
                    "result_id": "R1",
                    "stock_code": "2330",
                    "identity_status": "linked",
                },
                "next_review_at": "2026-09-15T09:00:00+08:00",
                "created_at": "2026-09-10T02:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    conflict = ContinuityReviewProjectionService(conflict_path).project(
        as_of="2026-09-15T12:00:00+08:00"
    )
    assert conflict.items == ()
    assert conflict.stream_status == CONTINUITY_STREAM_INVALID
    assert any("stream_invalid" in item for item in conflict.diagnostics)


def test_composer_exposes_exact_continuity_fields_as_read_only_review_item() -> None:
    continuity = ContinuityReviewItem(
        result_id="R1",
        stock_code="2330",
        decision_status="accepted",
        reminder_status="overdue",
        due_status="overdue",
        next_review_at="2026-09-10T09:00:00+08:00",
        revision_id="r-current",
        reminder_revision_id="r-review",
        revision_of="r-accepted",
        continuity_event_id="r-current",
        source_snapshot_id="snap-1",
        source_snapshot_hash="hash-1",
        decision_date="2026-09-01",
        source_trace="journal_entries.jsonl:r-review,r-current",
        history_count=2,
    )
    dashboard = WorkbenchReadOnlyComposer().compose(
        decision_snapshot=None,
        readiness_report=_ready_report(),
        continuity_reviews=ContinuityReviewProjectionResult(items=(continuity,)),
    )

    assert len(dashboard.review_items) == 1
    row = dashboard.review_items[0]
    assert row.source == "continuity_review"
    assert row.result_id == "R1"
    assert row.stock_code == "2330"
    assert row.candidate_key == "R1:2330"
    assert row.decision_status == "accepted"
    assert row.due_status == "overdue"
    assert row.revision_id == "r-current"
    assert row.source_snapshot_hash == "hash-1"
    assert row.read_only is True
    assert row.writes_allowed is False
    assert row.drilldown_target == "stock_research"


def test_portfolio_promotes_only_saved_recommendation_result_with_exact_stock(tmp_path: Path) -> None:
    view = PortfolioView.__new__(PortfolioView)
    view.portfolio_service = SimpleNamespace(config=SimpleNamespace(output_root=tmp_path))
    runs_dir = tmp_path / "recommendation" / "runs"
    runs_dir.mkdir(parents=True)
    (runs_dir / "R1.json").write_text(
        json.dumps(
            {
                "result_id": "R1",
                "recommendations": [{"stock_code": "2330"}],
            }
        ),
        encoding="utf-8",
    )

    valid = SimpleNamespace(
        source_type="recommendation_result",
        source_id="R1",
        source_summary={"result_id": "R1", "stock_code": "2330"},
    )
    assert view._validated_recommendation_result_id(valid, "2330") == "R1"

    for source_type in ("backtest_run", "strategy_version", "user_declared_research", ""):
        invalid = SimpleNamespace(source_type=source_type, source_id="R1", source_summary={})
        assert view._validated_recommendation_result_id(invalid, "2330") == ""
    mismatch = SimpleNamespace(
        source_type="recommendation_result",
        source_id="R1",
        source_summary={"result_id": "R1", "stock_code": "2317"},
    )
    assert view._validated_recommendation_result_id(mismatch, "2330") == ""


def test_workbench_continuity_rows_drill_down_with_the_selected_exact_candidate() -> None:
    application = QApplication.instance() or QApplication([])
    contexts: list[object] = []
    rows = (
        WorkbenchReviewItem(
            item_id="continuity_review:R1:2330",
            title="研究檢討提醒｜2330",
            severity="warning",
            source="continuity_review",
            summary="candidate=R1:2330；提醒=due",
            drilldown_target="stock_research",
            code="2330",
            result_id="R1",
            stock_code="2330",
            candidate_key="R1:2330",
            identity_status="linked",
            decision_status="accepted",
            due_status="due",
            next_review_at="2026-09-15T09:00:00+08:00",
            revision_id="rev-2330",
            source_snapshot_id="snap-2330",
            source_snapshot_hash="hash-2330",
            decision_date="2026-09-10",
        ),
        WorkbenchReviewItem(
            item_id="continuity_review:R2:2317",
            title="研究檢討提醒｜2317",
            severity="critical",
            source="continuity_review",
            summary="candidate=R2:2317；提醒=overdue",
            drilldown_target="stock_research",
            code="2317",
            result_id="R2",
            stock_code="2317",
            candidate_key="R2:2317",
            identity_status="linked",
            decision_status="skipped",
            due_status="overdue",
            next_review_at="2026-09-01T09:00:00+08:00",
            revision_id="rev-2317",
            source_snapshot_id="snap-2317",
            source_snapshot_hash="hash-2317",
            decision_date="2026-09-01",
        ),
    )
    dashboard = WorkbenchDashboardDTO(
        as_of_date=date(2026, 9, 15),
        generated_at=datetime(2026, 9, 15, 12, 0, 0),
        source_mode="read_only_sources",
        access_boundary=WorkbenchAccessBoundary(),
        status_strip=(
            WorkbenchStatusItem(
                item_id="scheduler",
                label="正式排程器",
                value="off",
                status="blocked",
            ),
        ),
        review_items=rows,
        evidence_summary=(),
        market_context={},
        portfolio_watchlist_summary={},
        daily_checklist=(),
    )
    view = UnifiedDecisionWorkbenchView(
        dashboard=dashboard,
        auto_refresh=False,
        navigate_to_stock_research_callback=contexts.append,
    )

    view._navigate_model_row(view.review_model, 1)

    assert len(contexts) == 1
    context = contexts[0]
    assert context.result_id == "R2"
    assert context.stock_code == "2317"
    assert context.source_snapshot_id == "snap-2317"
    assert context.source_id == "rev-2317"
    assert context.source_workspace == "workbench"
    assert context.identity_status == "linked"
    view.deleteLater()
    application.processEvents()
