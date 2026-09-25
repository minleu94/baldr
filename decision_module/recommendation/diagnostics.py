"""Pure candidate diagnostic projections owned by recommendation decisions."""

from __future__ import annotations

from dataclasses import dataclass, replace
from collections.abc import Mapping

from decision_module.recommendation.contracts import (
    CandidateAssessment,
    DecisionBatch,
    FilterOutcome,
    LiquidityAssessment,
    NegativeEvidence,
)
from decision_module.recommendation.evaluate import (
    CandidateDecisionDisposition,
    RecommendationEvaluationPolicy,
    RecommendationEvaluationResult,
)


@dataclass(frozen=True, slots=True)
class CandidateDiagnosticFacts:
    """Typed, invocation-bound display and score details for one candidate."""

    stock_code: str
    stock_name: str
    industry: str = ""
    total_score_text: str = ""
    score_bp: int | None = None
    threshold_mode: str = "fixed"
    invocation_id: str = ""

    def __post_init__(self) -> None:
        for name in ("stock_code", "stock_name", "industry", "total_score_text"):
            if type(getattr(self, name)) is not str:
                raise TypeError(f"{name} 必須是 str")
        if not self.stock_code.strip():
            raise ValueError("stock_code 不可為空")
        if type(self.invocation_id) is not str or not self.invocation_id.strip():
            raise ValueError("invocation_id 不可為空")
        if self.score_bp is not None and type(self.score_bp) is not int:
            raise TypeError("score_bp 必須是 int 或 None")
        if self.threshold_mode not in {"fixed", "quantile"}:
            raise ValueError("threshold_mode 必須是 fixed 或 quantile")


@dataclass(frozen=True, slots=True)
class RecommendationDiagnosticContext:
    """Minimal run facts needed for exact diagnostics without app context types."""

    invocation_id: str
    as_of_date: str
    data_fingerprint: str

    def __post_init__(self) -> None:
        if type(self.invocation_id) is not str or not self.invocation_id.strip():
            raise ValueError("invocation_id 不可為空")
        if type(self.as_of_date) is not str:
            raise TypeError("as_of_date 必須是 str")
        if type(self.data_fingerprint) is not str:
            raise TypeError("data_fingerprint 必須是 str")


def build_candidate_diagnostic_payload(
    disposition: CandidateDecisionDisposition,
    facts: CandidateDiagnosticFacts,
    context: RecommendationDiagnosticContext,
    policy: RecommendationEvaluationPolicy,
) -> dict[str, object]:
    """Project typed decision details to the existing v1 screening-row shape."""

    if policy.invocation_id != context.invocation_id:
        raise ValueError("context/policy invocation_id 不一致")
    if disposition.invocation_id != policy.invocation_id:
        raise ValueError("disposition/policy invocation_id 不一致")
    if facts.invocation_id != policy.invocation_id:
        raise ValueError("CandidateRowFacts/policy invocation_id 不一致")
    if facts.threshold_mode != policy.threshold_mode:
        raise ValueError("CandidateRowFacts threshold_mode 必須符合 policy")
    if facts.stock_code != disposition.stock_code:
        raise ValueError("CandidateRowFacts/disposition stock_code 不一致")

    ranking = dict(disposition.assessment.filter_outcomes or {}).get(
        "recommendation_ranking"
    )
    ranking_evidence: Mapping[str, object] = (
        dict(ranking.evidence or {}) if ranking is not None else {}
    )
    percentile = ranking_evidence.get("score_percentile_bp")
    universe_size = ranking_evidence.get("eligible_universe_size")
    threshold_name = disposition.threshold_name
    observed_value = disposition.observed_value
    required_value = disposition.required_value
    score_percentile_bp: int | None = None
    eligible_universe_size: int | None = None
    if facts.threshold_mode == "quantile" and disposition.scored:
        if ranking is None:
            raise ValueError("quantile scored disposition 缺少 ranking evidence")
        ordered_rank = ranking_evidence.get("ordered_rank")
        ranking_mode = ranking_evidence.get("threshold_mode")
        if (
            type(percentile) is not int
            or not 0 <= percentile <= 10_000
            or type(universe_size) is not int
            or universe_size < 1
            or ranking_mode != "quantile"
        ):
            raise ValueError("quantile ranking evidence 不完整或不一致")
        if disposition.stage in {"final_selection", "top_n_gate"} and (
            type(ordered_rank) is not int or ordered_rank < 1
        ):
            raise ValueError("selected/top_n quantile disposition 缺少 ordered_rank")
        if disposition.stage == "threshold_gate" and ordered_rank is not None:
            raise ValueError("threshold_gate disposition 不應有 ordered_rank")
        score_percentile_bp = percentile
        eligible_universe_size = universe_size
        threshold_name = "recommendation_min_percentile_bp"
        observed_value = str(percentile)
        required_value = (
            str(policy.minimum_percentile_bp)
            if policy.minimum_percentile_bp is not None
            else ""
        )
        if disposition.stage == "top_n_gate":
            threshold_name = "top_n"
            observed_value = str(ordered_rank)
            required_value = str(policy.top_n)

    return {
        "stock_code": disposition.stock_code,
        "stock_name": facts.stock_name or facts.stock_code,
        "status": disposition.status,
        "reason_codes": list(disposition.reason_codes),
        "quality": disposition.quality,
        "stage": disposition.stage,
        "threshold_name": threshold_name,
        "observed_value": observed_value,
        "required_value": required_value,
        "total_score": facts.total_score_text,
        "score_bp": facts.score_bp,
        "score_percentile_bp": score_percentile_bp,
        "eligible_universe_size": eligible_universe_size,
        "threshold_mode": facts.threshold_mode,
        "warnings": list(disposition.warnings),
        "industry": facts.industry,
        "as_of_date": context.as_of_date,
        "data_fingerprint": context.data_fingerprint,
    }


def enrich_evaluation_result(
    result: RecommendationEvaluationResult,
    candidate_facts: tuple[CandidateDiagnosticFacts, ...],
    context: RecommendationDiagnosticContext,
    policy: RecommendationEvaluationPolicy,
) -> RecommendationEvaluationResult:
    """Add exact legacy assessment evidence from typed decision-side facts."""

    if context.invocation_id != policy.invocation_id:
        raise ValueError("context/policy invocation_id 不一致")
    disposition_codes_ordered = tuple(
        item.stock_code for item in result.dispositions
    )
    if tuple(item.stock_code for item in result.decision.assessments) != disposition_codes_ordered:
        raise ValueError("DecisionBatch assessments 必須與 dispositions 同序")
    if tuple(result.decision.assessments) != tuple(
        item.assessment for item in result.dispositions
    ):
        raise ValueError("DecisionBatch assessments 必須等於 disposition assessments")
    if any(item.invocation_id != policy.invocation_id for item in result.dispositions):
        raise ValueError("disposition/policy invocation_id 不一致")
    facts_by_code = {item.stock_code: item for item in candidate_facts}
    if len(facts_by_code) != len(candidate_facts):
        raise ValueError("candidate_facts 不可有重複 stock_code")
    if tuple(facts_by_code) != disposition_codes_ordered:
        raise ValueError("candidate_facts 必須與 evaluator dispositions 同序且一一對應")
    if any(item.invocation_id != policy.invocation_id for item in candidate_facts):
        raise ValueError("CandidateRowFacts/policy invocation_id 不一致")
    if any(item.threshold_mode != policy.threshold_mode for item in candidate_facts):
        raise ValueError("CandidateRowFacts threshold_mode 必須符合 policy")

    enriched_by_code: dict[str, CandidateAssessment] = {}
    enriched_dispositions: list[CandidateDecisionDisposition] = []
    for disposition in result.dispositions:
        facts = facts_by_code[disposition.stock_code]
        evidence = build_candidate_diagnostic_payload(
            disposition,
            facts,
            context,
            policy,
        )
        assessment = disposition.assessment
        status = disposition.status.lower()
        eligible = assessment.eligible
        legacy_filter_id = "legacy:" + disposition.stage
        filter_outcomes = dict(assessment.filter_outcomes or {})
        filter_outcomes[legacy_filter_id] = FilterOutcome(
            filter_id=legacy_filter_id,
            passed=eligible,
            reason=(
                disposition.reason_codes[0]
                if disposition.reason_codes
                else disposition.status
            ),
            evidence=evidence,
        )
        reasons = disposition.reason_codes
        negative = (
            tuple(
                NegativeEvidence(
                    evidence_id=f"legacy:{disposition.stock_code}:{index}:{reason}",
                    reason=reason,
                    details=evidence,
                )
                for index, reason in enumerate(reasons)
            )
            if status != "pass"
            else ()
        )
        threshold = str(evidence["threshold_name"] or "").lower()
        reason_text = " ".join(reasons).lower()
        has_liquidity = (
            "liquidity" in reason_text
            or (
                status in {"fail", "degraded", "skipped", "missing"}
                and "liquidity" in threshold
            )
        )
        liquidity = (
            LiquidityAssessment(
                acceptable=False if status != "pass" else None,
                reasons=reasons,
                observations=evidence,
            )
            if has_liquidity
            else None
        )
        missing = reasons if status in {"missing", "degraded"} else ()
        enriched = replace(
            assessment,
            eligible=eligible,
            filter_outcomes=filter_outcomes,
            negative_evidence=negative,
            reasons=reasons,
            liquidity=liquidity,
            missing_data=missing,
        )
        enriched_by_code[disposition.stock_code] = enriched
        enriched_dispositions.append(replace(disposition, assessment=enriched))

    decision = DecisionBatch(
        items=result.decision.items,
        assessments=tuple(
            enriched_by_code[item.stock_code]
            for item in result.decision.assessments
        ),
        regime=result.decision.regime,
        state_transition=result.decision.state_transition,
    )
    return RecommendationEvaluationResult(
        decision=decision,
        dispositions=tuple(enriched_dispositions),
    )


__all__ = (
    "CandidateDiagnosticFacts",
    "RecommendationDiagnosticContext",
    "build_candidate_diagnostic_payload",
    "enrich_evaluation_result",
)
