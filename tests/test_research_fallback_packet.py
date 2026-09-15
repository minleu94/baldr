from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from app_module.daily_investment_journey import (
    DailyInvestmentJourneyService,
    _CandidateRead,
    _EvidenceRead,
    _PendingHorizonAnchor,
    _fallback_horizon_days,
    _matched_source_snapshot_id,
    _matching_pending_horizon_anchors,
    _pending_horizon_anchors,
)
from app_module.recommendation_learning_evidence_projection_service import (
    LearningHorizonProjection,
    LearningLaneProjection,
    RecommendationLearningEvidenceProjection,
)
from app_module.workbench_dtos import ResearchFallbackPacket
from app_module.v4_evidence_identity import DEFAULT_RETURN_BASIS


class _WeekdayCalendar:
    def is_official_trading_day(self, target_date, *, allow_online_probe: bool = False):
        return target_date.weekday() < 5, "fixture_official_weekday"


class _UnknownCalendar:
    def is_official_trading_day(self, target_date, *, allow_online_probe: bool = False):
        return None, "lacks_official_evidence"


def _service(tmp_path: Path, calendar) -> DailyInvestmentJourneyService:
    config = SimpleNamespace(
        output_root=tmp_path / "output",
        db_file=tmp_path / "evidence.sqlite",
    )
    return DailyInvestmentJourneyService(config, trading_calendar=calendar)


def _projection(
    *,
    status: str = "pending",
    data_recorded_status: str = "recorded",
    data_recorded_reason: str = "scheduled live prediction capture is recorded",
    lane_status: str = "pending",
    lane_reason: str = "natural_forward_evidence_receipt_missing",
    horizon_days: object = 5,
    cost_lane: str = "banktaiwan_estimated_research",
    historical_count: int = 0,
    horizon_scope_lane_id: str = "candidate_natural",
) -> RecommendationLearningEvidenceProjection:
    horizon = LearningHorizonProjection(
        horizon_days=horizon_days,  # type: ignore[arg-type]
        status="pending",
        reason=lane_reason,
    )
    candidate_lane = LearningLaneProjection(
        lane_id="candidate_natural",
        label="候選 natural evidence",
        status=lane_status,
        reason=lane_reason,
        candidate_id="candidate-a",
        cost_scenario_id="cost-1",
        capture_status="recorded" if data_recorded_status == "recorded" else "not_recorded",
        horizons=(horizon,),
    )
    active_lane = LearningLaneProjection(
        lane_id="active_model_natural",
        label="active model natural evidence",
        status="not_applicable",
        reason="active_pointer_not_active",
    )
    return RecommendationLearningEvidenceProjection(
        schema_version="projection.v1",
        status=status,
        requested_date="2026-09-14",
        learning_decision_date="2026-09-14",
        checked_at=None,
        decision="retain_current",
        decision_reason=lane_reason,
        candidate_id="candidate-a",
        candidate_model_version="candidate-a",
        candidate_training_as_of=None,
        data_recorded_status=data_recorded_status,
        data_recorded_reason=data_recorded_reason,
        next_gap="等待同一 capture 的 natural maturity",
        adoption_reason=lane_reason,
        candidate_lane=candidate_lane,
        active_lane=active_lane,
        horizons=(horizon,),
        horizon_scope_lane_id=horizon_scope_lane_id,
        horizon_scope_label="候選 natural evidence",
        horizon_scope_cost_scenario_id="cost-1",
        historical_evaluation_status=(
            "research_only_historical_replay" if historical_count else "research_only_not_natural"
        ),
        historical_evaluation_sample_count=historical_count,
        historical_evaluation_note="evaluation 僅為 historical replay，不能與 natural evidence 混算。",
        cost_lane=cost_lane,
    )


def _candidate(*, snapshot_id: str | None = "snapshot-a") -> _CandidateRead:
    return _CandidateRead(
        status="candidate",
        result_id="result-a",
        source_id="source-a",
        source_snapshot_id=snapshot_id,
        symbols=("2330",),
        identity=(
            "strategy_version_id=strategy-1",
            "cost_model_id=cost-1",
            "cost_scenario_id=cost-1",
            "benchmark_id=TAIEX",
            "horizon_days=20",
            "learning_candidate_id=candidate-a",
        ),
        source_trace=("candidate.result_id=result-a",),
    )


def _evidence(
    *,
    pending: bool = True,
    matched_snapshot_id: str | None = "snapshot-a",
    anchors: tuple[_PendingHorizonAnchor, ...] = (
        _PendingHorizonAnchor(
            horizon_days=5,
            decision_date="2026-09-14",
            symbol="2330",
            source_id="source-a",
            source_snapshot_id="snapshot-a",
            identity=(
                ("result_id", "result-a"),
                ("strategy_version_id", "strategy-1"),
                ("cost_model_id", "cost-1"),
                ("cost_scenario_id", "cost-1"),
                ("benchmark_id", "TAIEX"),
                ("horizon_days", "20"),
                ("learning_candidate_id", "candidate-a"),
            ),
            window_type="trading_days",
            return_basis=DEFAULT_RETURN_BASIS,
        ),
    ),
) -> _EvidenceRead:
    return _EvidenceRead(
        status="waiting_for_time" if pending else "ready",
        event_count=1,
        outcome_total=1,
        outcome_pending=1 if pending else 0,
        outcome_ready=0 if pending else 1,
        source_snapshot_ids=(matched_snapshot_id,) if matched_snapshot_id else ("snapshot-b",),
        pending_horizon_anchors=anchors if pending else (),
        source_trace=("evidence_event[evt-a].source_snapshot_id=snapshot-a",),
    )


def _packet(service, *, decision_date: str, candidate=None, evidence=None, projection=None):
    return service._build_research_fallback_packet(
        decision_date=decision_date,
        candidate=candidate or _candidate(),
        evidence=evidence or _evidence(),
        recommendation_learning_projection=projection or _projection(),
    )


def test_pending_packet_uses_original_same_scope_event_anchor_and_stays_stable_next_day(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path, _WeekdayCalendar())
    projection = _projection(horizon_days=5)
    evidence = _evidence()

    first = _packet(service, decision_date="2026-09-14", evidence=evidence, projection=projection)
    next_day = _packet(service, decision_date="2026-09-15", evidence=evidence, projection=projection)

    assert first.status == "pending_natural_evidence"
    assert first.revisit_date == "2026-09-21"
    assert next_day.revisit_date == first.revisit_date
    assert first.revisit_basis == "OfficialTradingCalendar + horizon_trading_days"


def test_pending_and_blocked_identity_cost_are_distinct(tmp_path: Path) -> None:
    service = _service(tmp_path, _WeekdayCalendar())
    pending = _packet(service, decision_date="2026-09-14")
    blocked = _packet(
        service,
        decision_date="2026-09-14",
        evidence=_evidence(pending=False),
        projection=_projection(
            status="blocked_provenance",
            data_recorded_status="blocked_provenance",
            data_recorded_reason="candidate capture identity mismatch",
            lane_status="blocked_provenance",
            lane_reason="blocked_cost_scope:selected=banktaiwan_estimated_research:artifact=legacy",
        ),
    )

    assert pending.status == "pending_natural_evidence"
    assert blocked.status == "blocked_identity_or_cost"
    assert blocked.revisit_date is None
    assert "identity" in blocked.missing_reason


def test_capture_missing_is_not_reported_as_natural_pending(tmp_path: Path) -> None:
    service = _service(tmp_path, _WeekdayCalendar())
    packet = _packet(
        service,
        decision_date="2026-09-14",
        evidence=_evidence(pending=False),
        projection=_projection(
            status="pending",
            data_recorded_status="not_recorded",
            data_recorded_reason="candidate live capture not supplied",
            lane_status="pending",
        ),
    )

    assert packet.status == "pending_capture"
    assert packet.revisit_date is None
    assert "capture" in packet.missing_reason


def test_revisit_is_unknown_without_official_calendar_or_with_non_integer_horizon(
    tmp_path: Path,
) -> None:
    unknown_calendar = _service(tmp_path / "unknown", _UnknownCalendar())
    unknown_packet = _packet(unknown_calendar, decision_date="2026-09-14")
    assert unknown_packet.revisit_date is None
    assert unknown_packet.revisit_status == "unknown"
    assert "官方交易日曆未知" in unknown_packet.revisit_reason

    invalid_horizon = _projection(horizon_days=1.9)
    invalid_packet = _packet(
        _service(tmp_path / "invalid", _WeekdayCalendar()),
        decision_date="2026-09-14",
        projection=invalid_horizon,
    )
    assert _fallback_horizon_days(invalid_horizon) is None
    assert invalid_packet.revisit_date is None
    assert "正整數 horizon" in invalid_packet.revisit_reason


def test_candidate_and_active_horizons_do_not_mix(tmp_path: Path) -> None:
    projection = _projection(horizon_days=5)
    active_horizon = LearningHorizonProjection(horizon_days=20, status="pending")
    projection = RecommendationLearningEvidenceProjection(
        **{
            **projection.__dict__,
            "active_lane": LearningLaneProjection(
                lane_id="active_model_natural",
                label="active model natural evidence",
                status="pending",
                reason="active_model_natural_evidence_missing",
                horizons=(active_horizon,),
            ),
        }
    )

    assert _fallback_horizon_days(projection) == 5


def test_pending_anchor_reader_is_same_scope_and_excludes_future_event() -> None:
    event = SimpleNamespace(
        event_id="evt-a",
        decision_date="2026-09-14",
        symbol="2330",
        source_id="source-a",
        source_snapshot_id="snapshot-a",
        strategy_version_id="strategy-1",
        cost_model_id="cost-1",
        benchmark_id="TAIEX",
        metadata={
            "result_id": "result-a",
            "cost_scenario_id": "cost-1",
            "horizon_days": 20,
            "learning_candidate_id": "candidate-a",
        },
    )
    future_event = SimpleNamespace(
        event_id="evt-future",
        decision_date="2026-09-15",
        symbol="2330",
        source_id="source-a",
        source_snapshot_id="snapshot-a",
        strategy_version_id="strategy-1",
        cost_model_id="cost-1",
        benchmark_id="TAIEX",
        metadata={
            "result_id": "result-a",
            "cost_scenario_id": "cost-1",
            "horizon_days": 20,
            "learning_candidate_id": "candidate-a",
        },
    )
    pending = SimpleNamespace(
        event_id="evt-a",
        window_days=5,
        outcome_status="pending",
        window_type="trading_days",
        return_basis=DEFAULT_RETURN_BASIS,
    )
    future_pending = SimpleNamespace(
        event_id="evt-future",
        window_days=5,
        outcome_status="pending",
        window_type="trading_days",
        return_basis=DEFAULT_RETURN_BASIS,
    )

    anchors = _pending_horizon_anchors(
        (event, future_event),
        (pending, future_pending),
        (5,),
        requested_date="2026-09-14",
    )

    assert len(anchors) == 1
    assert anchors[0].decision_date == "2026-09-14"
    assert anchors[0].source_id == "source-a"
    assert anchors[0].source_snapshot_id == "snapshot-a"
    assert _matched_source_snapshot_id((event,), _candidate()) == "snapshot-a"
    assert _matched_source_snapshot_id((future_event,), _candidate()) == "snapshot-a"
    unrelated = SimpleNamespace(
        event_id="evt-b",
        source_id="source-b",
        source_snapshot_id="snapshot-b",
    )
    assert _matched_source_snapshot_id((unrelated,), _candidate()) is None


def test_pending_anchor_rejects_field_conflicts_and_cross_field_collisions() -> None:
    candidate = _candidate()
    evidence = _EvidenceRead(
        pending_horizon_anchors=(
            replace(_evidence().pending_horizon_anchors[0], source_snapshot_id="snapshot-b"),
            replace(_evidence().pending_horizon_anchors[0], source_id="source-b"),
            replace(
                _evidence().pending_horizon_anchors[0],
                source_id="source-b",
                source_snapshot_id="result-a",
            ),
        )
    )

    assert _matching_pending_horizon_anchors(candidate, evidence, 5) == ()


def test_revisit_stays_unknown_for_ambiguous_original_dates_or_unproven_scope(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path, _WeekdayCalendar())
    original = _evidence().pending_horizon_anchors[0]
    ambiguous = _evidence(
        anchors=(
            original,
            replace(original, decision_date="2026-09-15"),
        )
    )
    ambiguous_packet = _packet(
        service,
        decision_date="2026-09-15",
        evidence=ambiguous,
    )
    assert ambiguous_packet.revisit_date is None
    assert "唯一同 scope" in ambiguous_packet.revisit_reason

    incomplete_scope = replace(
        original,
        identity=tuple(
            (key, value)
            for key, value in original.identity
            if key not in {"learning_candidate_id", "cost_scenario_id"}
        ),
        return_basis=None,
    )
    incomplete_packet = _packet(
        service,
        decision_date="2026-09-14",
        evidence=_evidence(anchors=(incomplete_scope,)),
    )
    assert incomplete_packet.revisit_date is None
    assert "不以 Workbench 查看日倒填" in incomplete_packet.revisit_reason


def test_packet_does_not_borrow_unrelated_snapshot_and_marks_owner_unknown(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path, _WeekdayCalendar())
    candidate = _candidate(snapshot_id=None)
    unrelated_evidence = _evidence(
        pending=False,
        matched_snapshot_id=None,
        anchors=(),
    )
    packet = _packet(
        service,
        decision_date="2026-09-14",
        candidate=candidate,
        evidence=unrelated_evidence,
        projection=_projection(status="missing", data_recorded_status="not_recorded"),
    )

    assert packet.scope_result_id == "result-a"
    assert packet.source_snapshot_id is None
    assert packet.source_owner_known is False
    assert "未知" in packet.source_owner
    assert "owner-a" not in packet.source_owner


def test_packet_scope_key_separates_same_date_cost_and_source_lanes(tmp_path: Path) -> None:
    service = _service(tmp_path, _WeekdayCalendar())
    first = _packet(service, decision_date="2026-09-14")
    second = _packet(
        service,
        decision_date="2026-09-14",
        candidate=_CandidateRead(
            status="candidate",
            result_id="result-b",
            source_id="source-b",
            source_snapshot_id="snapshot-b",
            symbols=("2330",),
        ),
        projection=_projection(cost_lane="legacy_fixed_bp"),
    )

    assert first.scope_key != second.scope_key
    assert first.cost_lane != second.cost_lane
    assert first.source_id != second.source_id


def test_packet_is_readonly_and_historical_replay_remains_research_only(tmp_path: Path) -> None:
    packet = _packet(
        _service(tmp_path, _WeekdayCalendar()),
        decision_date="2026-09-14",
        projection=_projection(historical_count=4),
    )

    payload = packet.to_dict()
    assert packet.read_only is True
    assert packet.write_intent is False
    assert packet.positive_fallback_allowed is False
    assert packet.historical_research_allowed is True
    assert any("historical replay" in item for item in packet.limitations)
    assert "probability_bp" not in payload
    assert "score" in " ".join(packet.limitations)
    with pytest.raises(ValueError):
        ResearchFallbackPacket(status="blocked", read_only=False)
    with pytest.raises(ValueError):
        ResearchFallbackPacket(status="blocked", positive_fallback_allowed=True)
