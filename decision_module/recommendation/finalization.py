"""Pure late score and regime decisions for recommendation candidates."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal
from enum import Enum

from decision_module.recommendation.contracts import (
    RecommendationItem,
    UniverseReference,
)
from decision_module.recommendation.evaluate import StrategyEvaluationError
from decision_module.recommendation.evaluate import CandidateEvaluationOutcome


@dataclass(frozen=True, slots=True)
class LegacyDecimalConversionFact:
    """App-projected result of one legacy Decimal(str(value)) conversion."""

    value: Decimal | None = None
    error: StrategyEvaluationError | None = None

    def __post_init__(self) -> None:
        if self.value is not None and type(self.value) is not Decimal:
            raise TypeError("value 必須是 Decimal 或 None")
        if self.error is not None and type(self.error) is not StrategyEvaluationError:
            raise TypeError("error 必須是 StrategyEvaluationError 或 None")
        if self.value is not None and self.error is not None:
            raise ValueError("value 與 error 不可同時存在")


@dataclass(frozen=True, slots=True)
class FinalScoreFacts:
    invocation_id: str
    stock_code: str
    score: LegacyDecimalConversionFact

    def __post_init__(self) -> None:
        for name in ("invocation_id", "stock_code"):
            value = getattr(self, name)
            if type(value) is not str or not value.strip():
                raise ValueError(f"{name} 不可為空")
        if type(self.score) is not LegacyDecimalConversionFact:
            raise TypeError("score 必須是 LegacyDecimalConversionFact")


class FinalScoreDisposition(str, Enum):
    READY = "ready"
    MISSING = "missing"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class FinalScoreResult:
    invocation_id: str
    stock_code: str
    disposition: FinalScoreDisposition
    score: Decimal | None = None
    error: StrategyEvaluationError | None = None

    def __post_init__(self) -> None:
        for name in ("invocation_id", "stock_code"):
            value = getattr(self, name)
            if type(value) is not str or not value.strip():
                raise ValueError(f"{name} 不可為空")
        if type(self.disposition) is not FinalScoreDisposition:
            raise TypeError("disposition 必須是 FinalScoreDisposition")
        if self.score is not None and type(self.score) is not Decimal:
            raise TypeError("score 必須是 Decimal 或 None")
        if self.error is not None and type(self.error) is not StrategyEvaluationError:
            raise TypeError("error 必須是 StrategyEvaluationError 或 None")
        if self.disposition is FinalScoreDisposition.READY:
            if self.score is None or not self.score.is_finite() or self.error is not None:
                raise ValueError("ready final score 必須是有限 Decimal")
        elif self.disposition is FinalScoreDisposition.MISSING:
            if self.score is not None or self.error is not None:
                raise ValueError("missing final score 不可攜帶 score/error")
        elif self.score is not None or self.error is None:
            raise ValueError("error final score 必須只攜帶 error")


def classify_final_score(facts: FinalScoreFacts) -> FinalScoreResult:
    """Classify score conversion, missing, and non-finite outcomes."""

    if type(facts) is not FinalScoreFacts:
        raise TypeError("facts 必須是 FinalScoreFacts")
    if facts.score.error is not None:
        return FinalScoreResult(
            invocation_id=facts.invocation_id,
            stock_code=facts.stock_code,
            disposition=FinalScoreDisposition.ERROR,
            error=facts.score.error,
        )
    value = facts.score.value
    if value is None or not value.is_finite():
        return FinalScoreResult(
            invocation_id=facts.invocation_id,
            stock_code=facts.stock_code,
            disposition=FinalScoreDisposition.MISSING,
        )
    return FinalScoreResult(
        invocation_id=facts.invocation_id,
        stock_code=facts.stock_code,
        disposition=FinalScoreDisposition.READY,
        score=value,
    )


@dataclass(frozen=True, slots=True)
class RegimeMatchFacts:
    invocation_id: str
    stock_code: str
    final_score: Decimal
    enabled: bool
    total_score: LegacyDecimalConversionFact | None = None

    def __post_init__(self) -> None:
        for name in ("invocation_id", "stock_code"):
            value = getattr(self, name)
            if type(value) is not str or not value.strip():
                raise ValueError(f"{name} 不可為空")
        if type(self.final_score) is not Decimal or not self.final_score.is_finite():
            raise ValueError("final_score 必須是有限 Decimal")
        if type(self.enabled) is not bool:
            raise TypeError("enabled 必須是 bool")
        if self.enabled:
            if type(self.total_score) is not LegacyDecimalConversionFact:
                raise TypeError("enabled regime 必須有 total_score fact")
            if self.total_score.value is None and self.total_score.error is None:
                raise ValueError("enabled regime total_score 不可缺值")
        elif self.total_score is not None:
            raise ValueError("disabled regime 不得轉換 total_score")


@dataclass(frozen=True, slots=True)
class RegimeMatchResult:
    invocation_id: str
    stock_code: str
    regime_match: bool
    error: StrategyEvaluationError | None = None

    def __post_init__(self) -> None:
        for name in ("invocation_id", "stock_code"):
            value = getattr(self, name)
            if type(value) is not str or not value.strip():
                raise ValueError(f"{name} 不可為空")
        if type(self.regime_match) is not bool:
            raise TypeError("regime_match 必須是 bool")
        if self.error is not None and type(self.error) is not StrategyEvaluationError:
            raise TypeError("error 必須是 StrategyEvaluationError 或 None")
        if self.error is not None and self.regime_match:
            raise ValueError("regime error 不可同時宣告 match")


def evaluate_regime_match(facts: RegimeMatchFacts) -> RegimeMatchResult:
    """Apply the legacy strict FinalScore > TotalScore * 1.05 rule."""

    if type(facts) is not RegimeMatchFacts:
        raise TypeError("facts 必須是 RegimeMatchFacts")
    if not facts.enabled:
        return RegimeMatchResult(
            invocation_id=facts.invocation_id,
            stock_code=facts.stock_code,
            regime_match=False,
        )
    assert facts.total_score is not None
    if facts.total_score.error is not None:
        return RegimeMatchResult(
            invocation_id=facts.invocation_id,
            stock_code=facts.stock_code,
            regime_match=False,
            error=facts.total_score.error,
        )
    assert facts.total_score.value is not None
    try:
        matched = facts.final_score > facts.total_score.value * Decimal("1.05")
    except Exception as exc:
        return RegimeMatchResult(
            invocation_id=facts.invocation_id,
            stock_code=facts.stock_code,
            regime_match=False,
            error=StrategyEvaluationError(
                error_type=type(exc).__name__,
                message=str(exc),
            ),
        )
    return RegimeMatchResult(
        invocation_id=facts.invocation_id,
        stock_code=facts.stock_code,
        regime_match=matched,
    )


@dataclass(frozen=True, slots=True)
class RecommendationItemFacts:
    """Invocation-bound typed values needed to complete one canonical item."""

    invocation_id: str
    stock_code: str
    stock_name: str
    close_price: Decimal
    price_change: Decimal
    indicator_score: Decimal
    pattern_score: Decimal
    volume_score: Decimal
    industry: str
    reason_text: str
    reasons: tuple[str, ...]
    universe_policy_id: str
    universe_snapshot_id: str
    universe_as_of_date: date | None
    universe_members_hash: str
    regime_match: bool

    def __post_init__(self) -> None:
        for name in (
            "invocation_id",
            "stock_code",
            "stock_name",
            "industry",
            "reason_text",
            "universe_policy_id",
            "universe_snapshot_id",
            "universe_members_hash",
        ):
            if type(getattr(self, name)) is not str:
                raise TypeError(f"{name} 必須是 str")
        if not self.invocation_id.strip() or not self.stock_code.strip():
            raise ValueError("invocation_id 與 stock_code 不可為空")
        for name in (
            "close_price",
            "price_change",
            "indicator_score",
            "pattern_score",
            "volume_score",
        ):
            if type(getattr(self, name)) is not Decimal:
                raise TypeError(f"{name} 必須是 Decimal")
        if type(self.reasons) is not tuple or any(
            type(reason) is not str for reason in self.reasons
        ):
            raise TypeError("reasons 必須是 str tuple")
        if self.universe_as_of_date is not None and type(
            self.universe_as_of_date
        ) is not date:
            raise TypeError("universe_as_of_date 必須是 date 或 None")
        if type(self.regime_match) is not bool:
            raise TypeError("regime_match 必須是 bool")


def reason_tags_from_legacy_reasons(
    reasons: Sequence[object],
) -> tuple[str, ...]:
    """Project the legacy reason row sequence to its canonical tag tuple."""

    return tuple(
        str(reason.get("tag") or "")
        for reason in reasons
        if isinstance(reason, Mapping) and str(reason.get("tag") or "")
    )


def finalize_candidate_item(
    outcome: CandidateEvaluationOutcome,
    facts: RecommendationItemFacts,
) -> CandidateEvaluationOutcome:
    """Build the complete canonical RecommendationItem inside decision."""

    if type(outcome) is not CandidateEvaluationOutcome:
        raise TypeError("outcome 必須是 CandidateEvaluationOutcome")
    if type(facts) is not RecommendationItemFacts:
        raise TypeError("facts 必須是 RecommendationItemFacts")
    if (
        outcome.invocation_id != facts.invocation_id
        or outcome.stock_code != facts.stock_code
    ):
        raise ValueError("candidate outcome/item facts identity 不一致")
    if (
        outcome.status != "fail"
        or outcome.quality != "observed"
        or outcome.stage != "candidate_scored"
        or outcome.reason_codes != ("pending_final_selection",)
        or outcome.assessment is None
        or outcome.assessment.eligible is not True
        or outcome.item is None
        or outcome.score is None
    ):
        raise ValueError("只有 evaluator 成功評分的候選可建立完整 item")
    item = RecommendationItem(
        stock_code=facts.stock_code,
        stock_name=facts.stock_name,
        rule_score=outcome.item.rule_score,
        close_price=facts.close_price,
        price_change=facts.price_change,
        indicator_score=facts.indicator_score,
        pattern_score=facts.pattern_score,
        volume_score=facts.volume_score,
        industry=facts.industry,
        reason_text=facts.reason_text,
        reasons=facts.reasons,
        universe_ref=UniverseReference(
            policy_id=facts.universe_policy_id,
            snapshot_id=facts.universe_snapshot_id,
            as_of_date=facts.universe_as_of_date,
            members_hash=facts.universe_members_hash,
        ),
        regime_match=facts.regime_match,
    )
    return replace(outcome, item=item)


__all__ = (
    "FinalScoreDisposition",
    "FinalScoreFacts",
    "FinalScoreResult",
    "LegacyDecimalConversionFact",
    "RecommendationItemFacts",
    "RegimeMatchFacts",
    "RegimeMatchResult",
    "classify_final_score",
    "evaluate_regime_match",
    "finalize_candidate_item",
    "reason_tags_from_legacy_reasons",
)
