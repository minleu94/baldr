from __future__ import annotations

from datetime import date

import pytest

from app_module.recommendation.contracts import (
    Context,
    ExecutionEvent,
    ExecutionStatus,
    RecommendationExecution,
    ReferenceKind,
    Request,
    VersionReference,
)
from app_module.recommendation.negative_evidence_projection import (
    NegativeEvidenceProjectionError,
)
from decision_module.recommendation.contracts import (
    CandidateAssessment,
    DecisionBatch,
    FilterOutcome,
)
from scripts.scheduled.run_scheduled_recommendation_snapshot import (
    _execution_capture_summary,
)


def _typed_execution(*, include_typed_evidence: bool) -> RecommendationExecution:
    assessment = CandidateAssessment(
        stock_code="2330",
        eligible=True,
        filter_outcomes=(
            {
                "legacy:final_selection": FilterOutcome(
                    filter_id="legacy:final_selection",
                    passed=True,
                    reason="recommendation_selected",
                    evidence={
                        "stock_code": "2330",
                        "stock_name": "Synthetic",
                        "status": "pass",
                        "reason_codes": ["recommendation_selected"],
                        "quality": "observed",
                        "stage": "final_selection",
                        "threshold_name": "",
                        "observed_value": "",
                        "required_value": "",
                        "total_score": "0.00000000000000000001",
                        "score_bp": 0,
                        "score_percentile_bp": 0,
                        "eligible_universe_size": 0,
                        "threshold_mode": "fixed",
                        "warnings": [],
                        "industry": "Synthetic",
                        "as_of_date": "2026-09-08",
                        "data_fingerprint": "sha256:typed-scheduled-fixture",
                    },
                )
            }
            if include_typed_evidence
            else {}
        ),
    )
    return RecommendationExecution(
        result_id="r029-scheduled-projection",
        request=Request(
            as_of_date=date(2026, 9, 8),
            profile_ref=VersionReference(ReferenceKind.PROFILE, "synthetic", "1"),
        ),
        context=Context(as_of_date=date(2026, 9, 8)),
        status=ExecutionStatus.COMPLETED,
        decision=DecisionBatch(items=(), assessments=(assessment,)),
        events=(
            ExecutionEvent(
                event_type="legacy_negative_evidence_capture",
                message="consumer must read typed evidence",
                details={"screening_matrix": [{"stock_code": "wrong-event-value"}]},
            ),
        ),
    )


def test_scheduled_summary_reads_typed_rows_and_ignores_legacy_event_values() -> None:
    summary = _execution_capture_summary(_typed_execution(include_typed_evidence=True))

    assert summary["screening_matrix"][0]["stock_code"] == "2330"
    assert summary["screening_matrix"][0]["score_bp"] == 0
    assert summary["screening_matrix"][0]["score_percentile_bp"] == 0
    assert summary["screening_matrix"][0]["eligible_universe_size"] == 0
    assert summary["exclusion_quality"] == "observed"
    assert summary["exclusion_warnings"] == ("screening_matrix_persisted_v1",)


def test_scheduled_summary_fails_closed_when_typed_row_is_missing() -> None:
    with pytest.raises(NegativeEvidenceProjectionError, match="legacy:<stage>"):
        _execution_capture_summary(_typed_execution(include_typed_evidence=False))


def test_scheduled_empty_completed_decision_keeps_unknown_evidence_quality() -> None:
    execution = RecommendationExecution(
        result_id="r029-scheduled-empty",
        request=Request(
            as_of_date=date(2026, 9, 8),
            profile_ref=VersionReference(ReferenceKind.PROFILE, "synthetic", "1"),
        ),
        context=Context(as_of_date=date(2026, 9, 8)),
        status=ExecutionStatus.COMPLETED,
        decision=DecisionBatch(items=(), assessments=()),
    )

    summary = _execution_capture_summary(execution)

    assert summary["screening_matrix"] == ()
    assert summary["excluded_candidates"] == ()
    assert summary["why_not_payload"] == ()
    assert summary["liquidity_gate_payload"] == ()
    assert summary["exclusion_quality"] == "unknown"
    assert summary["exclusion_warnings"] == ()
