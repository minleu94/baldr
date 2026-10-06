from __future__ import annotations

from decimal import Decimal

import pytest

from decision_module.recommendation.evaluate import StrategyEvaluationError
from decision_module.recommendation.finalization import (
    FinalScoreDisposition,
    FinalScoreFacts,
    LegacyDecimalConversionFact,
    RegimeMatchFacts,
    classify_final_score,
    evaluate_regime_match,
)


@pytest.mark.parametrize(
    "score",
    [
        LegacyDecimalConversionFact(),
        LegacyDecimalConversionFact(value=Decimal("NaN")),
        LegacyDecimalConversionFact(value=Decimal("Infinity")),
    ],
)
def test_final_score_missing_or_nonfinite_is_a_typed_missing_result(
    score: LegacyDecimalConversionFact,
) -> None:
    result = classify_final_score(
        FinalScoreFacts(
            invocation_id="finalization-test",
            stock_code="2330",
            score=score,
        )
    )

    assert result.disposition is FinalScoreDisposition.MISSING
    assert result.score is None
    assert result.error is None


def test_final_score_conversion_failure_keeps_its_legacy_error() -> None:
    error = StrategyEvaluationError(
        error_type="InvalidOperation",
        message="[<class 'decimal.ConversionSyntax'>]",
    )

    result = classify_final_score(
        FinalScoreFacts(
            invocation_id="finalization-test",
            stock_code="2330",
            score=LegacyDecimalConversionFact(error=error),
        )
    )

    assert result.disposition is FinalScoreDisposition.ERROR
    assert result.score is None
    assert result.error == error


@pytest.mark.parametrize(
    ("score", "expected"),
    [
        (Decimal("83.99"), False),
        (Decimal("84.00"), False),
        (Decimal("84.01"), True),
    ],
)
def test_regime_match_keeps_strict_five_percent_boundary(
    score: Decimal,
    expected: bool,
) -> None:
    result = evaluate_regime_match(
        RegimeMatchFacts(
            invocation_id="finalization-test",
            stock_code="2330",
            final_score=score,
            enabled=True,
            total_score=LegacyDecimalConversionFact(value=Decimal("80")),
        )
    )

    assert result.regime_match is expected
    assert result.error is None


def test_disabled_regime_does_not_require_or_convert_total_score() -> None:
    result = evaluate_regime_match(
        RegimeMatchFacts(
            invocation_id="finalization-test",
            stock_code="2330",
            final_score=Decimal("84.01"),
            enabled=False,
        )
    )

    assert result.regime_match is False
    assert result.error is None


def test_regime_conversion_and_decimal_comparison_errors_remain_typed() -> None:
    conversion_error = StrategyEvaluationError(
        error_type="InvalidOperation",
        message="[<class 'decimal.ConversionSyntax'>]",
    )
    conversion_result = evaluate_regime_match(
        RegimeMatchFacts(
            invocation_id="finalization-test",
            stock_code="2330",
            final_score=Decimal("84.01"),
            enabled=True,
            total_score=LegacyDecimalConversionFact(error=conversion_error),
        )
    )
    assert conversion_result.error == conversion_error

    nan_result = evaluate_regime_match(
        RegimeMatchFacts(
            invocation_id="finalization-test",
            stock_code="2330",
            final_score=Decimal("84.01"),
            enabled=True,
            total_score=LegacyDecimalConversionFact(value=Decimal("NaN")),
        )
    )
    assert nan_result.regime_match is False
    assert nan_result.error is not None
    assert nan_result.error.error_type == "InvalidOperation"
