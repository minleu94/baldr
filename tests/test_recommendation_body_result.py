"""R019 immutable body capture and v1 assessment projection tests."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import FrozenInstanceError, replace
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, cast

import pytest
import numpy as np

from app_module.dtos import RecommendationDTO
from app_module.recommendation.body_result import (
    CandidateRowFacts,
    FrozenPayload,
    InvocationLegacyContextOwner,
    LegacyRecommendationSnapshot,
    RecommendationBodyContextFacts,
    RecommendationBodyResult,
    build_candidate_row_payload,
    enrich_evaluation_result,
    freeze_payload,
)
from app_module.recommendation_run_support import build_negative_evidence_buffers
from app_module.recommendation.score_projection import project_legacy_recommendation_score
from decision_module.recommendation.contracts import (
    CandidateAssessment,
    DecisionBatch,
    FilterOutcome,
    LiquidityAssessment,
    NegativeEvidence,
    RecommendationItem,
)
from decision_module.recommendation.evaluate import (
    CandidateEvaluationOutcome,
    RecommendationEvaluationPolicy,
    RecommendationEvaluator,
    RecommendationScore,
)


DECISION_DATE = date(2026, 5, 20)


def _legacy_string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()
    return tuple(str(item) for item in value if item is not None)


def _legacy_safe_contract_value(
    value: object,
    active: set[int] | None = None,
    field_path: str = "value",
) -> Any:
    """Frozen test-only copy of execute's legacy evidence value allowlist."""

    if active is None:
        active = set()

    if value is None or type(value) in (str, int, bool, Decimal, date, datetime):
        if type(value) is Decimal and not value.is_finite():
            raise ValueError(f"{field_path} 的 Decimal 必須是有限值")
        if type(value) is datetime and (value.tzinfo is None or value.utcoffset() is None):
            return value.isoformat()
        return value

    if type(value) is float:
        try:
            converted = Decimal(str(value))
        except InvalidOperation as exc:
            raise ValueError(f"{field_path} 的 float 無法封存") from exc
        if not converted.is_finite():
            raise ValueError(f"{field_path} 的 float 必須是有限值")
        return converted

    if isinstance(value, np.bool_):
        return bool(value)

    if isinstance(value, np.integer):
        return int(value)

    if isinstance(value, np.floating):
        try:
            converted = Decimal(str(value))
        except InvalidOperation as exc:
            raise ValueError(f"{field_path} 的 NumPy 浮點值無法封存") from exc
        if not converted.is_finite():
            raise ValueError(f"{field_path} 的 NumPy 浮點值必須是有限值")
        return converted

    if isinstance(value, np.str_):
        return str(value)

    if isinstance(value, Mapping):
        identity = id(value)
        if identity in active:
            raise TypeError(f"{field_path} 不接受循環 mapping")
        active.add(identity)
        try:
            converted_mapping: dict[str, Any] = {}
            for key, item in value.items():
                if type(key) is not str:
                    raise TypeError(f"{field_path} 的 mapping key 必須是 str")
                converted_mapping[key] = _legacy_safe_contract_value(
                    item, active, f"{field_path}.{key}"
                )
            return converted_mapping
        finally:
            active.remove(identity)

    if type(value) in (list, tuple):
        identity = id(value)
        if identity in active:
            raise TypeError(f"{field_path} 不接受循環 sequence")
        active.add(identity)
        try:
            sequence = cast(Sequence[object], value)
            converted_items = tuple(
                _legacy_safe_contract_value(item, active, f"{field_path}[{index}]")
                for index, item in enumerate(sequence)
            )
        finally:
            active.remove(identity)
        return converted_items

    raise TypeError(
        f"{field_path} 型別 {type(value).__name__} 不在 execution evidence allowlist"
    )


def _legacy_assessments_oracle(
    legacy_state: Mapping[str, Any],
) -> tuple[CandidateAssessment, ...]:
    """Frozen test-only copy of the former execute._assessments behavior."""

    matrix = legacy_state.get("last_screening_matrix", ())
    excluded_codes = {
        str(row.get("stock_code") or "")
        for row in legacy_state.get("last_excluded_candidates_json", ())
        if isinstance(row, Mapping)
    }
    liquidity_codes = {
        str(row.get("stock_code") or "")
        for row in legacy_state.get("last_liquidity_gate_payload_json", ())
        if isinstance(row, Mapping)
    }
    assessments: list[CandidateAssessment] = []
    seen: set[str] = set()
    for raw_row in matrix:
        if not isinstance(raw_row, Mapping):
            continue
        code = str(raw_row.get("stock_code") or "").strip()
        if not code or code in seen:
            continue
        seen.add(code)
        status = str(raw_row.get("status") or "unknown").lower()
        eligible = True if status == "pass" else False if status in {
            "fail", "excluded", "skipped"
        } else None
        stage = str(raw_row.get("stage") or "legacy_screening")
        reasons = _legacy_string_tuple(raw_row.get("reason_codes"))
        evidence = _legacy_safe_contract_value(dict(raw_row))
        filter_outcomes = {
            "legacy:" + stage: FilterOutcome(
                filter_id="legacy:" + stage,
                passed=eligible,
                reason=(reasons[0] if reasons else status),
                evidence=evidence,
            )
        }
        negative_reasons = reasons if status != "pass" else ()
        negative = tuple(
            NegativeEvidence(
                evidence_id=f"legacy:{code}:{index}:{reason}",
                reason=reason,
                details=evidence,
            )
            for index, reason in enumerate(negative_reasons)
        )
        liquidity = None
        if code in liquidity_codes or any("liquidity" in item.lower() for item in reasons):
            liquidity = LiquidityAssessment(
                acceptable=False if status != "pass" else None,
                reasons=reasons,
                observations=evidence,
            )
        missing = reasons if status in {"missing", "degraded"} else ()
        assessments.append(
            CandidateAssessment(
                stock_code=code,
                eligible=eligible,
                filter_outcomes=filter_outcomes,
                negative_evidence=negative,
                reasons=reasons,
                liquidity=liquidity,
                missing_data=missing,
            )
        )
    return tuple(assessments)


def _policy(
    invocation_id: str,
    *,
    threshold_mode: str = "fixed",
    top_n: int = 50,
    minimum_bp: int | None = None,
    minimum_size: int | None = None,
) -> RecommendationEvaluationPolicy:
    return RecommendationEvaluationPolicy(
        invocation_id=invocation_id,
        decision_date=DECISION_DATE,
        decision_date_text=DECISION_DATE.isoformat(),
        threshold_mode=threshold_mode,
        top_n=top_n,
        minimum_percentile_bp=minimum_bp,
        minimum_universe_size=minimum_size,
        ranking_method="nearest_rank" if threshold_mode == "quantile" else "fixed",
        eligible_universe_date=DECISION_DATE,
    )


def _rankable(code: str, score: Decimal) -> CandidateEvaluationOutcome:
    projection = project_legacy_recommendation_score(score)
    return CandidateEvaluationOutcome(
        invocation_id="body-test",
        stock_code=code,
        status="fail",
        quality="observed",
        stage="candidate_scored",
        reason_codes=("pending_final_selection",),
        item=RecommendationItem(
            stock_code=code,
            stock_name=f"{code} name",
            rule_score=score,
            close_price=Decimal("10"),
            price_change=Decimal("1"),
            indicator_score=Decimal("1"),
            pattern_score=Decimal("1"),
            volume_score=Decimal("1"),
            industry="半導體",
            reason_text="selected",
            regime_match=False,
        ),
        assessment=CandidateAssessment(stock_code=code, eligible=True),
        score=projection.score,
    )


def _context(
    invocation_id: str = "body-test",
    *,
    eligible_universe_size: int = 2,
    result_id: str = "body-result-1",
) -> RecommendationBodyContextFacts:
    legacy_context = {
        "result_id": result_id,
        "as_of_date": "2026-05-20",
        "data_fingerprint": "data-hash-1",
        "market_data_fingerprint": "market-hash-1",
        "source_id": "market-provider-v1",
        "temporal_mode": "point_in_time",
        "decision_at": "2026-05-20T12:00:00+00:00",
        "eligible_universe_size": eligible_universe_size,
        "warnings": ["industry_membership_pit_verified"],
        "fundamental_inputs": [{"metric": "monthly_revenue", "value": "1"}],
    }
    owner = InvocationLegacyContextOwner(invocation_id)
    owner.mutable_context.update(legacy_context)
    return RecommendationBodyContextFacts.capture(
        result_id=result_id,
        invocation_id=invocation_id,
        as_of_date="2026-05-20",
        data_fingerprint="data-hash-1",
        market_data_fingerprint="market-hash-1",
        source_id="market-provider-v1",
        temporal_mode="point_in_time",
        decision_at="2026-05-20T12:00:00+00:00",
        eligible_universe_size=eligible_universe_size,
        warnings=("industry_membership_pit_verified",),
        legacy_context=owner.freeze_current_context(),
    )


def _dto_for_item(item: RecommendationItem) -> RecommendationDTO:
    assert item.rule_score is not None
    assert item.close_price is not None
    assert item.price_change is not None
    assert item.indicator_score is not None
    assert item.pattern_score is not None
    assert item.volume_score is not None
    return RecommendationDTO(
        stock_code=item.stock_code,
        stock_name=item.stock_name or "",
        close_price=item.close_price,
        price_change=item.price_change,
        total_score=item.rule_score,
        indicator_score=item.indicator_score,
        pattern_score=item.pattern_score,
        volume_score=item.volume_score,
        recommendation_reasons=item.reason_text or "",
        industry=item.industry or "",
        regime_match=item.regime_match is True,
        score_percentile_bp=item.score_percentile_bp,
        eligible_universe_size=item.eligible_universe_size,
        eligible_universe_date=(
            item.eligible_universe_date.isoformat()
            if item.eligible_universe_date is not None
            else None
        ),
        ranking_method=item.ranking_method,
        threshold_mode=item.threshold_mode or "fixed",
    )


def test_body_context_and_legacy_dto_sidecar_are_immutable_snapshots() -> None:
    legacy_context = {
        "result_id": "body-result-1",
        "as_of_date": "2026-05-20",
        "data_fingerprint": "hash",
        "market_data_fingerprint": "market-hash",
        "source_id": "provider",
        "temporal_mode": "point_in_time",
        "decision_at": "2026-05-20T12:00:00+00:00",
        "eligible_universe_size": 1,
        "warnings": ["captured"],
        "fundamental_inputs": [{"value": "original"}],
    }
    owner = InvocationLegacyContextOwner("body-test:call-1")
    owner.mutable_context.update(legacy_context)
    context = RecommendationBodyContextFacts.capture(
        result_id="body-result-1",
        invocation_id="body-test:call-1",
        as_of_date="2026-05-20",
        data_fingerprint="hash",
        market_data_fingerprint="market-hash",
        source_id="provider",
        temporal_mode="point_in_time",
        decision_at="2026-05-20T12:00:00+00:00",
        eligible_universe_size=1,
        warnings=("captured",),
        legacy_context=owner.freeze_current_context(),
    )
    legacy_context["warnings"].append("later mutation")
    legacy_context["fundamental_inputs"][0]["value"] = "changed"
    assert context.warnings == ("captured",)
    assert context.legacy_context.thaw()["fundamental_inputs"] == [
        {"value": "original"}
    ]

    dto = RecommendationDTO(
        stock_code="2330",
        stock_name="TSMC",
        close_price=Decimal("600.1000"),
        price_change=2.5,
        total_score=Decimal("91.2300"),  # type: ignore[arg-type]
        indicator_score=85.0,
        pattern_score=95.0,
        volume_score=90.0,
        recommendation_reasons="trend and volume confirmation",
        industry="半導體",
        regime_match=True,
        calibration_provenance={"nested": {"rows": ["original"]}},
    )
    snapshot = LegacyRecommendationSnapshot.capture(
        dto,
        invocation_id="body-test:call-1",
        result_id="body-result-1",
    )
    dto.calibration_provenance["nested"]["rows"][0] = "changed"
    restored = snapshot.materialize()
    assert type(restored.total_score) is Decimal
    assert restored.total_score == Decimal("91.2300")
    assert restored.calibration_provenance == {"nested": {"rows": ["original"]}}
    with pytest.raises(FrozenInstanceError):
        context.result_id = "changed"  # type: ignore[misc]
    with pytest.raises(ValueError, match="不可帶 scalar"):
        FrozenPayload(kind="list", scalar=[])
    structured = np.zeros(1, dtype=[("x", "i4")])
    structured_scalar = structured[0]
    with pytest.raises(TypeError, match="NumPy record"):
        freeze_payload({"nested": [structured_scalar]})
    assert structured["x"][0] == 0
    scalar_snapshot = freeze_payload({"score": np.float64(91.5)})
    frozen_score = scalar_snapshot.thaw()["score"]  # type: ignore[index]
    assert type(frozen_score) is np.float64


def test_body_context_normalizes_date_and_rejects_legacy_identity_from_another_run() -> None:
    baseline = _context()
    legacy_context = baseline.legacy_context.thaw()
    assert isinstance(legacy_context, dict)
    legacy_context["data_fingerprint"] = "fingerprint-from-run-b"
    wrong_hash_owner = InvocationLegacyContextOwner(baseline.invocation_id)
    wrong_hash_owner.mutable_context.update(legacy_context)

    with pytest.raises(ValueError, match="data_fingerprint 與 typed context 不一致"):
        RecommendationBodyContextFacts.capture(
            result_id=baseline.result_id,
            invocation_id=baseline.invocation_id,
            as_of_date=date(2026, 5, 20),
            data_fingerprint=baseline.data_fingerprint,
            market_data_fingerprint=baseline.market_data_fingerprint,
            source_id=baseline.source_id,
            temporal_mode=baseline.temporal_mode,
            decision_at=baseline.decision_at,
            eligible_universe_size=baseline.eligible_universe_size,
            warnings=baseline.warnings,
            legacy_context=wrong_hash_owner.freeze_current_context(),
        )

    date_from_other_run = baseline.legacy_context.thaw()
    assert isinstance(date_from_other_run, dict)
    date_from_other_run["as_of_date"] = "2026-05-21"
    wrong_date_owner = InvocationLegacyContextOwner(baseline.invocation_id)
    wrong_date_owner.mutable_context.update(date_from_other_run)
    with pytest.raises(ValueError, match="as_of_date 與 typed context 不一致"):
        RecommendationBodyContextFacts.capture(
            result_id=baseline.result_id,
            invocation_id=baseline.invocation_id,
            as_of_date="2026-05-20",
            data_fingerprint=baseline.data_fingerprint,
            market_data_fingerprint=baseline.market_data_fingerprint,
            source_id=baseline.source_id,
            temporal_mode=baseline.temporal_mode,
            decision_at=baseline.decision_at,
            eligible_universe_size=baseline.eligible_universe_size,
            warnings=baseline.warnings,
            legacy_context=wrong_date_owner.freeze_current_context(),
        )

    invocation_from_other_run = baseline.legacy_context.thaw()
    assert isinstance(invocation_from_other_run, dict)
    invocation_from_other_run["invocation_id"] = "run-b"
    explicit_wrong_id_owner = InvocationLegacyContextOwner(baseline.invocation_id)
    explicit_wrong_id_owner.mutable_context.update(invocation_from_other_run)
    with pytest.raises(ValueError, match="legacy_context.invocation_id"):
        RecommendationBodyContextFacts.capture(
            result_id=baseline.result_id,
            invocation_id=baseline.invocation_id,
            as_of_date=baseline.as_of_date,
            data_fingerprint=baseline.data_fingerprint,
            market_data_fingerprint=baseline.market_data_fingerprint,
            source_id=baseline.source_id,
            temporal_mode=baseline.temporal_mode,
            decision_at=baseline.decision_at,
            eligible_universe_size=baseline.eligible_universe_size,
            warnings=baseline.warnings,
            legacy_context=explicit_wrong_id_owner.freeze_current_context(),
        )

    owner_a = InvocationLegacyContextOwner("run-a")
    owner_b = InvocationLegacyContextOwner("run-b")
    owner_b.mutable_context.update(baseline.legacy_context.thaw())
    with pytest.raises(TypeError, match="positional argument"):
        owner_a.freeze_current_context(owner_b.mutable_context)  # type: ignore[call-arg]
    with pytest.raises(TypeError, match="invocation owner"):
        RecommendationBodyContextFacts.capture(
            result_id=baseline.result_id,
            invocation_id=baseline.invocation_id,
            as_of_date=baseline.as_of_date,
            data_fingerprint=baseline.data_fingerprint,
            market_data_fingerprint=baseline.market_data_fingerprint,
            source_id=baseline.source_id,
            temporal_mode=baseline.temporal_mode,
            decision_at=baseline.decision_at,
            eligible_universe_size=baseline.eligible_universe_size,
            warnings=baseline.warnings,
            legacy_context=baseline.legacy_context.thaw(),  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError, match="capture invocation token"):
        RecommendationBodyContextFacts.capture(
            result_id=baseline.result_id,
            invocation_id=baseline.invocation_id,
            as_of_date=baseline.as_of_date,
            data_fingerprint=baseline.data_fingerprint,
            market_data_fingerprint=baseline.market_data_fingerprint,
            source_id=baseline.source_id,
            temporal_mode=baseline.temporal_mode,
            decision_at=baseline.decision_at,
            eligible_universe_size=baseline.eligible_universe_size,
            warnings=baseline.warnings,
            legacy_context=owner_b.freeze_current_context(),
        )

    normalized = RecommendationBodyContextFacts.capture(
        result_id=baseline.result_id,
        invocation_id=baseline.invocation_id,
        as_of_date=date(2026, 5, 20),
        data_fingerprint=baseline.data_fingerprint,
        market_data_fingerprint=baseline.market_data_fingerprint,
        source_id=baseline.source_id,
        temporal_mode=baseline.temporal_mode,
        decision_at=baseline.decision_at,
        eligible_universe_size=baseline.eligible_universe_size,
        warnings=baseline.warnings,
        legacy_context=baseline.legacy_context,
    )
    assert normalized.as_of_date == "2026-05-20"


def test_c1_distinct_result_ids_keep_invocation_context_snapshots_separate() -> None:
    context_a = _context("c1-cross-boundary-A:invocation", result_id="c1-cross-boundary-A")
    context_b = _context("c1-cross-boundary-B:invocation", result_id="c1-cross-boundary-B")

    assert context_a.result_id == "c1-cross-boundary-A"
    assert context_b.result_id == "c1-cross-boundary-B"
    assert context_a.invocation_id != context_b.invocation_id
    assert "invocation_id" not in context_a.legacy_context.thaw()
    assert "invocation_id" not in context_b.legacy_context.thaw()


def test_typed_outcomes_project_exact_legacy_liquidity_assessment_evidence() -> None:
    assessment = CandidateAssessment(stock_code="LIQ", eligible=False)
    outcome = CandidateEvaluationOutcome(
        invocation_id="body-test",
        stock_code="LIQ",
        status="skipped",
        quality="degraded",
        stage="volume_gate",
        reason_codes=("liquidity_volume_ratio_below_min",),
        threshold_name="liquidity.volume_ratio_min",
        observed_value="0",
        required_value="1",
        assessment=assessment,
    )
    evaluator = RecommendationEvaluator()
    policy = _policy("body-test")
    evaluated = evaluator.evaluate_batch_result((outcome,), policy)
    context = _context()
    facts = (
        CandidateRowFacts(
            "LIQ",
            "Example Corp",
            threshold_mode="fixed",
            invocation_id="body-test",
        ),
    )

    enriched = enrich_evaluation_result(evaluated, facts, context, policy)

    candidate = enriched.decision.assessments[0]
    row = {
        "stock_code": "LIQ",
        "stock_name": "Example Corp",
        "status": "skipped",
        "reason_codes": ("liquidity_volume_ratio_below_min",),
        "quality": "degraded",
        "stage": "volume_gate",
        "threshold_name": "liquidity.volume_ratio_min",
        "observed_value": "0",
        "required_value": "1",
        "total_score": "",
        "score_bp": None,
        "score_percentile_bp": None,
        "eligible_universe_size": None,
        "threshold_mode": "fixed",
        "warnings": (),
        "industry": "",
        "as_of_date": "2026-05-20",
        "data_fingerprint": "data-hash-1",
    }
    legacy_filter = candidate.filter_outcomes["legacy:volume_gate"]
    assert legacy_filter.passed is False
    assert legacy_filter.reason == "liquidity_volume_ratio_below_min"
    assert dict(legacy_filter.evidence or {}) == row
    assert [item.evidence_id for item in candidate.negative_evidence] == [
        "legacy:LIQ:0:liquidity_volume_ratio_below_min"
    ]
    assert dict(candidate.negative_evidence[0].details or {}) == row
    assert candidate.liquidity is not None
    assert candidate.liquidity.acceptable is False
    assert candidate.liquidity.reasons == ("liquidity_volume_ratio_below_min",)
    assert dict(candidate.liquidity.observations or {}) == row
    assert candidate.missing_data == ()
    legacy_row = dict(row)
    legacy_row["reason_codes"] = ["liquidity_volume_ratio_below_min"]
    legacy_row["warnings"] = []
    baseline = _legacy_assessments_oracle({"last_screening_matrix": [legacy_row]})[0]
    assert candidate.filter_outcomes["legacy:volume_gate"] == baseline.filter_outcomes[
        "legacy:volume_gate"
    ]
    assert candidate.negative_evidence == baseline.negative_evidence
    assert candidate.liquidity == baseline.liquidity
    assert candidate.missing_data == baseline.missing_data


@pytest.mark.parametrize(
    ("code", "status", "quality", "stage", "reason", "threshold_name"),
    [
        ("EXCLUDED", "excluded", "observed", "universe_gate", "industry_filter_empty", ""),
        ("MISSING", "missing", "missing", "fundamental_gate", "valuation_pe_missing", "filters.pe_ratio_max"),
        ("DEGRADED", "degraded", "degraded", "strategy_evaluation", "screening_exception", "RuntimeError"),
        ("THRESHOLD_LIQ", "skipped", "observed", "volume_gate", "volume_ratio_below_min", "liquidity.volume_ratio_min"),
    ],
)
def test_typed_nonselected_status_and_threshold_liquidity_match_legacy_assessments(
    code: str,
    status: str,
    quality: str,
    stage: str,
    reason: str,
    threshold_name: str,
) -> None:
    outcome = CandidateEvaluationOutcome(
        invocation_id="body-test",
        stock_code=code,
        status=status,
        quality=quality,
        stage=stage,
        reason_codes=(reason,),
        threshold_name=threshold_name,
        observed_value="observed",
        required_value="required",
        assessment=CandidateAssessment(
            stock_code=code,
            eligible=False if status in {"excluded", "skipped"} else None,
        ),
    )
    policy = _policy("body-test")
    facts = (
        CandidateRowFacts(
            code,
            f"{code} name",
            threshold_mode="fixed",
            invocation_id="body-test",
        ),
    )
    enriched = enrich_evaluation_result(
        RecommendationEvaluator().evaluate_batch_result((outcome,), policy),
        facts,
        _context(),
        policy,
    )
    candidate = enriched.decision.assessments[0]
    legacy_filter_id = "legacy:" + stage
    row = dict(candidate.filter_outcomes[legacy_filter_id].evidence or {})
    buffers = build_negative_evidence_buffers((row,))
    baseline = _legacy_assessments_oracle(
        {
            "last_screening_matrix": (row,),
            "last_excluded_candidates_json": buffers.excluded_candidates,
            "last_liquidity_gate_payload_json": buffers.liquidity_gate_payload,
        }
    )[0]

    assert candidate.filter_outcomes[legacy_filter_id] == baseline.filter_outcomes[
        legacy_filter_id
    ]
    assert candidate.negative_evidence == baseline.negative_evidence
    assert candidate.liquidity == baseline.liquidity
    assert candidate.missing_data == baseline.missing_data


def test_selected_typed_assessment_matches_legacy_pass_projection() -> None:
    policy = _policy("body-test", top_n=1)
    outcome = _rankable("PASS", Decimal("80"))
    facts = (
        CandidateRowFacts(
            "PASS",
            "PASS name",
            industry="半導體",
            total_score_text="80",
            threshold_mode="fixed",
            invocation_id="body-test",
        ),
    )
    enriched = enrich_evaluation_result(
        RecommendationEvaluator().evaluate_batch_result((outcome,), policy),
        facts,
        _context(eligible_universe_size=1),
        policy,
    )
    candidate = enriched.decision.assessments[0]
    row = dict(candidate.filter_outcomes["legacy:final_selection"].evidence or {})
    buffers = build_negative_evidence_buffers((row,))
    baseline = _legacy_assessments_oracle(
        {
            "last_screening_matrix": (row,),
            "last_excluded_candidates_json": buffers.excluded_candidates,
            "last_liquidity_gate_payload_json": buffers.liquidity_gate_payload,
        }
    )[0]
    assert candidate.filter_outcomes["legacy:final_selection"] == baseline.filter_outcomes[
        "legacy:final_selection"
    ]
    assert candidate.negative_evidence == baseline.negative_evidence == ()
    assert candidate.liquidity == baseline.liquidity is None
    assert candidate.missing_data == baseline.missing_data == ()


def test_quantile_projection_preserves_selected_threshold_fields_and_top_n_ids() -> None:
    outcomes = (
        _rankable("TOP", Decimal("90.0000")),
        _rankable("OUT", Decimal("80.0000")),
    )
    policy = _policy(
        "body-test",
        threshold_mode="quantile",
        top_n=1,
        minimum_bp=4000,
        minimum_size=2,
    )
    evaluated = RecommendationEvaluator().evaluate_batch_result(outcomes, policy)
    facts = (
        CandidateRowFacts(
            "TOP",
            "TOP name",
            industry="半導體",
            total_score_text="90.0000",
            threshold_mode="quantile",
            invocation_id="body-test",
        ),
        CandidateRowFacts(
            "OUT",
            "OUT name",
            industry="半導體",
            total_score_text="80.0000",
            threshold_mode="quantile",
            invocation_id="body-test",
        ),
    )

    enriched = enrich_evaluation_result(evaluated, facts, _context(), policy)

    top = next(item for item in enriched.decision.assessments if item.stock_code == "TOP")
    top_evidence = top.filter_outcomes["legacy:final_selection"].evidence
    assert dict(top_evidence or {}) == {
        "stock_code": "TOP",
        "stock_name": "TOP name",
        "status": "pass",
        "reason_codes": ("recommendation_selected",),
        "quality": "observed",
        "stage": "final_selection",
        "threshold_name": "recommendation_min_percentile_bp",
        "observed_value": "10000",
        "required_value": "4000",
        "total_score": "90.0000",
        "score_bp": None,
        "score_percentile_bp": 10000,
        "eligible_universe_size": 2,
        "threshold_mode": "quantile",
        "warnings": (),
        "industry": "半導體",
        "as_of_date": "2026-05-20",
        "data_fingerprint": "data-hash-1",
    }
    out = next(item for item in enriched.decision.assessments if item.stock_code == "OUT")
    assert [item.evidence_id for item in out.negative_evidence] == [
        "legacy:OUT:0:recommendation_outside_top_n"
    ]
    out_evidence = dict(out.filter_outcomes["legacy:top_n_gate"].evidence or {})
    assert out_evidence["threshold_name"] == "top_n"
    assert out_evidence["observed_value"] == "2"
    assert out_evidence["required_value"] == "1"
    assert out_evidence["score_percentile_bp"] == 5000


def test_enrichment_requires_same_invocation_and_policy_mode() -> None:
    policy = _policy("body-test")
    evaluated = RecommendationEvaluator().evaluate_batch_result(
        (_rankable("SAME", Decimal("80")),), policy
    )
    good_facts = (
        CandidateRowFacts(
            "SAME",
            "SAME name",
            industry="半導體",
            total_score_text="80",
            threshold_mode="fixed",
            invocation_id="body-test",
        ),
    )
    with pytest.raises(ValueError, match="context/policy invocation_id"):
        enrich_evaluation_result(
            evaluated,
            good_facts,
            _context("run-b", eligible_universe_size=1),
            policy,
        )
    with pytest.raises(ValueError, match="CandidateRowFacts/policy invocation_id"):
        enrich_evaluation_result(
            evaluated,
            (replace(good_facts[0], invocation_id="run-b"),),
            _context(eligible_universe_size=1),
            policy,
        )
    with pytest.raises(ValueError, match="threshold_mode 必須符合 policy"):
        enrich_evaluation_result(
            evaluated,
            (replace(good_facts[0], threshold_mode="quantile"),),
            _context(eligible_universe_size=1),
            policy,
        )


def test_quantile_scored_row_rejects_missing_ranking_evidence() -> None:
    policy = _policy(
        "body-test",
        threshold_mode="quantile",
        top_n=2,
        minimum_bp=0,
        minimum_size=2,
    )
    result = RecommendationEvaluator().evaluate_batch_result(
        (
            _rankable("A", Decimal("90")),
            _rankable("B", Decimal("80")),
        ),
        policy,
    )
    disposition = result.dispositions[0]
    assessment = disposition.assessment
    filters = dict(assessment.filter_outcomes or {})
    filters.pop("recommendation_ranking")
    malformed = replace(
        disposition,
        assessment=replace(assessment, filter_outcomes=filters),
    )
    facts = CandidateRowFacts(
        malformed.stock_code,
        f"{malformed.stock_code} name",
        industry="半導體",
        total_score_text="90",
        threshold_mode="quantile",
        invocation_id="body-test",
    )
    with pytest.raises(ValueError, match="缺少 ranking evidence"):
        build_candidate_row_payload(malformed, facts, _context(), policy)


def test_body_result_validates_invocation_and_single_item_sidecar_identity() -> None:
    result_id = "body-result-1"
    invocation_id = "body-test:call-1"
    dto = RecommendationDTO(
        stock_code="2330",
        stock_name="TSMC",
        close_price=Decimal("600"),
        price_change=1.0,
        total_score=90.0,
        indicator_score=80.0,
        pattern_score=85.0,
        volume_score=88.0,
        recommendation_reasons="reason",
        industry="半導體",
        regime_match=False,
    )
    empty = RecommendationBodyResult(
        result_id=result_id,
        invocation_id=invocation_id,
        decision=RecommendationEvaluator().evaluate_batch((), _policy("body-test")),
        dispositions=(),
        candidate_facts=(),
        context=_context(invocation_id),
        legacy_recommendations=(),
    )
    assert empty.decision.items == ()

    with pytest.raises(ValueError, match="assessments 必須與 dispositions"):
        RecommendationBodyResult(
            result_id=result_id,
            invocation_id=invocation_id,
            decision=RecommendationEvaluator().evaluate_batch(
                (_rankable("2330", Decimal("90")),), _policy("body-test")
            ),
            dispositions=(),
            candidate_facts=(),
            context=_context(invocation_id),
            legacy_recommendations=(
                LegacyRecommendationSnapshot.capture(
                    dto,
                    invocation_id=invocation_id,
                    result_id=result_id,
                ),
            ),
        )


def test_body_result_requires_item_sidecar_order_and_uniqueness() -> None:
    outcomes = (
        _rankable("TOP", Decimal("90")),
        _rankable("NEXT", Decimal("80")),
    )
    policy = _policy("body-test", top_n=2)
    evaluated = RecommendationEvaluator().evaluate_batch_result(outcomes, policy)
    facts = (
        CandidateRowFacts(
            "TOP", "TOP name", industry="半導體", total_score_text="90",
            invocation_id="body-test",
        ),
        CandidateRowFacts(
            "NEXT", "NEXT name", industry="半導體", total_score_text="80",
            invocation_id="body-test",
        ),
    )
    context = _context("body-test")
    enriched = enrich_evaluation_result(evaluated, facts, context, policy)
    top_dto = _dto_for_item(enriched.decision.items[0])
    next_dto = _dto_for_item(enriched.decision.items[1])
    args = {
        "result_id": "body-result-1",
        "invocation_id": "body-test",
        "decision": enriched.decision,
        "dispositions": enriched.dispositions,
        "candidate_facts": facts,
        "context": context,
    }

    reordered_decision = DecisionBatch(
        items=enriched.decision.items,
        assessments=tuple(reversed(enriched.decision.assessments)),
    )
    with pytest.raises(ValueError, match="assessments 必須與 dispositions 同序"):
        RecommendationBodyResult(
            **{**args, "decision": reordered_decision},
            legacy_recommendations=(
                LegacyRecommendationSnapshot.capture(
                    top_dto, invocation_id="body-test", result_id="body-result-1"
                ),
                LegacyRecommendationSnapshot.capture(
                    next_dto, invocation_id="body-test", result_id="body-result-1"
                ),
            ),
        )

    with pytest.raises(ValueError, match="順序必須與 legacy"):
        RecommendationBodyResult(
            **args,
            legacy_recommendations=(
                LegacyRecommendationSnapshot.capture(
                    next_dto, invocation_id="body-test", result_id="body-result-1"
                ),
                LegacyRecommendationSnapshot.capture(
                    top_dto, invocation_id="body-test", result_id="body-result-1"
                ),
            ),
        )
    with pytest.raises(ValueError, match="不可有重複 stock_code"):
        RecommendationBodyResult(
            **args,
            legacy_recommendations=(
                LegacyRecommendationSnapshot.capture(
                    top_dto, invocation_id="body-test", result_id="body-result-1"
                ),
                LegacyRecommendationSnapshot.capture(
                    top_dto, invocation_id="body-test", result_id="body-result-1"
                ),
            ),
        )


def test_body_result_rejects_same_code_cross_invocation_and_payload_mismatch() -> None:
    outcomes = (_rankable("SAME", Decimal("90")),)
    policy = _policy("body-test", top_n=1)
    facts = (
        CandidateRowFacts(
            "SAME",
            "SAME name",
            industry="半導體",
            total_score_text="90",
            threshold_mode="fixed",
            invocation_id="body-test",
        ),
    )
    context = _context(eligible_universe_size=1)
    enriched = enrich_evaluation_result(
        RecommendationEvaluator().evaluate_batch_result(outcomes, policy),
        facts,
        context,
        policy,
    )
    dto = _dto_for_item(enriched.decision.items[0])
    snapshot = LegacyRecommendationSnapshot.capture(
        dto,
        invocation_id="body-test",
        result_id="body-result-1",
    )
    args = {
        "result_id": "body-result-1",
        "invocation_id": "body-test",
        "decision": enriched.decision,
        "dispositions": enriched.dispositions,
        "candidate_facts": facts,
        "context": context,
    }

    with pytest.raises(ValueError, match="candidate_facts invocation_id"):
        RecommendationBodyResult(
            **{**args, "candidate_facts": (replace(facts[0], invocation_id="run-b"),)},
            legacy_recommendations=(snapshot,),
        )

    with pytest.raises(ValueError, match="legacy recommendation invocation_id"):
        RecommendationBodyResult(
            **args,
            legacy_recommendations=(
                LegacyRecommendationSnapshot.capture(
                    dto, invocation_id="run-b", result_id="body-result-1"
                ),
            ),
        )

    with pytest.raises(ValueError, match="legacy recommendation result_id"):
        RecommendationBodyResult(
            **args,
            legacy_recommendations=(
                LegacyRecommendationSnapshot.capture(
                    dto, invocation_id="body-test", result_id="result-from-run-b"
                ),
            ),
        )

    changed_score_dto = replace(dto, total_score=Decimal("91"))
    with pytest.raises(ValueError, match="item/legacy DTO rule_score 不一致"):
        RecommendationBodyResult(
            **args,
            legacy_recommendations=(
                LegacyRecommendationSnapshot.capture(
                    changed_score_dto,
                    invocation_id="body-test",
                    result_id="body-result-1",
                ),
            ),
        )

    changed_assessment = replace(
        enriched.decision.assessments[0], missing_data=("run-b-only",)
    )
    changed_batch = DecisionBatch(
        items=enriched.decision.items,
        assessments=(changed_assessment,),
    )
    with pytest.raises(ValueError, match="必須等於 disposition assessments"):
        RecommendationBodyResult(
            **{**args, "decision": changed_batch},
            legacy_recommendations=(snapshot,),
        )
