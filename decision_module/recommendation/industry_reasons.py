"""Pure recommendation decisions for industry-performance explanations."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, localcontext

from decision_module.recommendation.evaluate import (
    IndustryChangeSourceKind,
    IndustryContextFact,
)


@dataclass(frozen=True, slots=True)
class IndustryPerformanceReason:
    """Decision-owned reason values before legacy presentation projection."""

    tag: str
    evidence: str
    score_contrib: Decimal

    def __post_init__(self) -> None:
        if type(self.tag) is not str or not self.tag:
            raise ValueError("tag 不可為空")
        if type(self.evidence) is not str:
            raise TypeError("evidence 必須是 str")
        if type(self.score_contrib) is not Decimal or not self.score_contrib.is_finite():
            raise TypeError("score_contrib 必須是有限 Decimal")


def build_industry_performance_reason(
    fact: IndustryContextFact,
) -> IndustryPerformanceReason | None:
    """Apply the legacy positive-change rule using typed Decimal source facts.

    The native Decimal source case intentionally retains the old positive-value
    TypeError. The previous app rule multiplied that source by a bare float,
    which degraded that candidate; changing it would be a separate behavior
    change. Float and parsed-text inputs arrive as exact Decimal representations
    of their legacy binary value, so half-cent evidence remains byte-compatible.
    """

    if type(fact) is not IndustryContextFact:
        raise TypeError("fact 必須是 IndustryContextFact")
    if not fact.industries:
        return None

    source_kind = fact.first_industry_change_source_kind
    change = fact.first_industry_change_percent
    if source_kind is IndustryChangeSourceKind.UNAVAILABLE:
        return None
    if source_kind is IndustryChangeSourceKind.UNSUPPORTED:
        raise TypeError("industry percent source does not support comparison")
    if change is None:
        raise ValueError("industry change source is missing its Decimal value")

    if source_kind is IndustryChangeSourceKind.LEGACY_FLOAT and change.is_nan():
        # Python float NaN > 0 is False; Decimal NaN comparison would raise.
        return None
    if not change > 0:
        return None
    if source_kind is IndustryChangeSourceKind.LEGACY_INTEGER_OVERFLOW:
        raise OverflowError("int too large to convert to float")
    if source_kind is IndustryChangeSourceKind.LEGACY_DECIMAL:
        raise TypeError(
            "unsupported operand type(s) for *: 'decimal.Decimal' and 'float'"
        )

    industry = fact.industries[0]
    if change.is_infinite():
        legacy_display = "inf" if change > 0 else "-inf"
    else:
        legacy_display = format(change, ".2f")

    # Keep enough Decimal precision for the exact parsed IEEE value before the
    # app later projects this compatibility payload back to a Python float.
    precision = max(28, len(change.as_tuple().digits) + 2)
    with localcontext() as context:
        context.prec = precision
        score_contrib = min(change * Decimal("0.5"), Decimal("10"))

    return IndustryPerformanceReason(
        tag=f"{industry}指數上漲",
        evidence=f"{industry}類指數漲幅 {legacy_display}%",
        score_contrib=score_contrib,
    )


__all__ = (
    "IndustryPerformanceReason",
    "build_industry_performance_reason",
)
