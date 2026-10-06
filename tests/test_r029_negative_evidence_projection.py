from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from app_module.recommendation.negative_evidence_projection import (
    NegativeEvidenceProjectionError,
    count_legacy_assessment_outcomes,
    project_canonical_negative_evidence,
)
from decision_module.recommendation.contracts import (
    CandidateAssessment,
    DecisionBatch,
    FilterOutcome,
)


def _row(
    stock_code: str,
    *,
    status: str,
    stage: str,
    reason_codes: tuple[str, ...] = (),
    quality: str = "observed",
    score_bp: int | None = None,
    score_percentile_bp: int | None = None,
    eligible_universe_size: int | None = None,
    warnings: tuple[str, ...] = (),
) -> dict[str, object]:
    return {
        "stock_code": stock_code,
        "stock_name": f"name-{stock_code}",
        "status": status,
        "reason_codes": reason_codes,
        "quality": quality,
        "stage": stage,
        "threshold_name": "liquidity_minimum" if reason_codes else "",
        "observed_value": "0.0000000000000000000000000001",
        "required_value": "0.0000000000000000000000000002",
        "total_score": "78.50000000000000000000000001",
        "score_bp": score_bp,
        "score_percentile_bp": score_percentile_bp,
        "eligible_universe_size": eligible_universe_size,
        "threshold_mode": "fixed",
        "warnings": warnings,
        "industry": "synthetic-industry",
        "as_of_date": "2026-09-08",
        "data_fingerprint": "sha256:synthetic-r029",
    }


def _assessment(row: Mapping[str, object], *, eligible: bool | None) -> CandidateAssessment:
    stage = str(row["stage"])
    stock_code = str(row["stock_code"])
    return CandidateAssessment(
        stock_code=stock_code,
        eligible=eligible,
        filter_outcomes={
            f"legacy:{stage}": FilterOutcome(
                filter_id=f"legacy:{stage}",
                passed=eligible,
                reason=(str(row["reason_codes"][0]) if row["reason_codes"] else status_for(eligible)),
                evidence=dict(row),
            )
        },
    )


def status_for(eligible: bool | None) -> str:
    return "missing" if eligible is None else ("pass" if eligible else "fail")


def _assert_invocation_buffer_parity(
    state: Mapping[str, object],
    event_details: Mapping[str, object],
) -> None:
    """只在測試中比較舊 facade buffers 與 typed projection 的同次輸出。"""

    for projected, legacy in (
        ("screening_matrix", "last_screening_matrix"),
        ("excluded_candidates", "last_excluded_candidates_json"),
        ("why_not_payload", "last_why_not_payload_json"),
        ("liquidity_gate_payload", "last_liquidity_gate_payload_json"),
        ("exclusion_quality", "last_exclusion_quality"),
        ("exclusion_warnings", "last_exclusion_warnings_json"),
    ):
        assert _plain(event_details[projected]) == _plain(state[legacy])


def _plain(value: object) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if type(value) in (tuple, list):
        return [_plain(item) for item in value]
    return value


def test_typed_projection_preserves_order_precision_optional_values_and_warnings() -> None:
    selected = _row(
        "2330",
        status="pass",
        stage="final_selection",
        score_bp=0,
        score_percentile_bp=0,
        eligible_universe_size=0,
    )
    excluded = _row(
        "1101",
        status="fail",
        stage="threshold_gate",
        reason_codes=("liquidity_below_minimum",),
        quality="missing",
        warnings=("source_missing",),
    )
    decision = DecisionBatch(
        items=(),
        assessments=(
            _assessment(selected, eligible=True),
            _assessment(excluded, eligible=False),
        ),
    )

    projection = project_canonical_negative_evidence(decision)
    matrix = projection.as_event_details()["screening_matrix"]
    assert [row["stock_code"] for row in matrix] == ["2330", "1101"]
    assert matrix[0]["total_score"] == "78.50000000000000000000000001"
    assert matrix[0]["score_bp"] == 0
    assert matrix[0]["score_percentile_bp"] == 0
    assert matrix[0]["eligible_universe_size"] == 0
    assert matrix[1]["score_bp"] is None
    assert matrix[1]["score_percentile_bp"] is None
    assert matrix[1]["eligible_universe_size"] is None
    assert projection.exclusion_quality == "degraded"
    assert projection.exclusion_warnings == (
        "screening_matrix_persisted_v1",
        "screening_contains_unknown_evidence",
    )
    assert [row["stock_code"] for row in projection.why_not_payload] == ["1101"]
    assert [row["stock_code"] for row in projection.liquidity_gate_payload] == ["1101"]
    assert projection.why_not_payload[0]["observed_value"] == (
        "0.0000000000000000000000000001"
    )

    legacy_state = {
        "last_screening_matrix": matrix,
        "last_excluded_candidates_json": list(projection.excluded_candidates),
        "last_why_not_payload_json": list(projection.why_not_payload),
        "last_liquidity_gate_payload_json": list(projection.liquidity_gate_payload),
        "last_exclusion_quality": projection.exclusion_quality,
        "last_exclusion_warnings_json": list(projection.exclusion_warnings),
    }
    _assert_invocation_buffer_parity(legacy_state, projection.as_event_details())


def test_typed_projection_rejects_partial_or_malformed_assessment_evidence() -> None:
    valid = _row(
        "2330",
        status="pass",
        stage="final_selection",
    )
    partial = CandidateAssessment(stock_code="1101", eligible=False)
    mixed = DecisionBatch(
        items=(),
        assessments=(_assessment(valid, eligible=True), partial),
    )

    with pytest.raises(NegativeEvidenceProjectionError, match="只覆蓋部分"):
        count_legacy_assessment_outcomes(mixed)
    with pytest.raises(NegativeEvidenceProjectionError, match="legacy:<stage>"):
        project_canonical_negative_evidence(mixed)

    extra_field = {**valid, "unversioned_extra": "unknown"}
    malformed = DecisionBatch(
        items=(),
        assessments=(_assessment(extra_field, eligible=True),),
    )
    with pytest.raises(NegativeEvidenceProjectionError, match="v1 欄位集合"):
        project_canonical_negative_evidence(malformed)


def test_typed_projection_checks_reason_parity_and_accepts_status_reason() -> None:
    excluded = _row(
        "1101",
        status="fail",
        stage="threshold_gate",
        reason_codes=("liquidity_below_minimum",),
    )
    valid_assessment = _assessment(excluded, eligible=False)
    assert valid_assessment.filter_outcomes is not None
    valid_outcome = valid_assessment.filter_outcomes["legacy:threshold_gate"]
    mismatched = CandidateAssessment(
        stock_code="1101",
        eligible=False,
        filter_outcomes={
            "legacy:threshold_gate": FilterOutcome(
                filter_id="legacy:threshold_gate",
                passed=False,
                reason="different_reason",
                evidence=valid_outcome.evidence,
            )
        },
    )
    with pytest.raises(NegativeEvidenceProjectionError, match="reason 不一致"):
        project_canonical_negative_evidence(
            DecisionBatch(items=(), assessments=(mismatched,))
        )

    unknown = _row(
        "9999",
        status="missing",
        stage="source_gate",
    )
    projection = project_canonical_negative_evidence(
        DecisionBatch(
            items=(),
            assessments=(_assessment(unknown, eligible=None),),
        )
    )
    row = projection.screening_matrix[0]
    assert row["reason_codes"] == ()
    assert row["status"] == "missing"


def test_typed_projection_allows_a_proven_empty_live_batch_only() -> None:
    decision = DecisionBatch(items=(), assessments=())

    with pytest.raises(NegativeEvidenceProjectionError, match="沒有 typed screening"):
        project_canonical_negative_evidence(decision)

    projection = project_canonical_negative_evidence(decision, allow_empty=True)
    assert projection.screening_matrix == ()
    assert projection.why_not_payload == ()
    assert projection.exclusion_quality == "unknown"
    assert projection.exclusion_warnings == ()
