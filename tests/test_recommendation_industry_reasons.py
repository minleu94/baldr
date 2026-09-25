from __future__ import annotations

import ast
from decimal import Decimal
from pathlib import Path

import pytest

from app_module.recommendation.source_fact_projection import (
    project_industry_context_fact,
    project_legacy_industry_reason,
)
from decision_module.recommendation.evaluate import (
    IndustryChangeSourceKind,
    IndustryContextFact,
)
from decision_module.recommendation.industry_reasons import (
    IndustryPerformanceReason,
    build_industry_performance_reason,
)


def test_decision_industry_reason_module_has_no_outer_layer_imports() -> None:
    source_path = (
        Path(__file__).resolve().parents[1]
        / "decision_module"
        / "recommendation"
        / "industry_reasons.py"
    )
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    imports = [
        node.module or ""
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    ]
    imports.extend(
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    )
    assert not any(
        name.startswith(("app_module", "data_module", "ui_qt", "scripts"))
        for name in imports
    )


@pytest.mark.parametrize(
    ("raw_value", "expected_evidence", "expected_contribution"),
    [
        ("1.50%", "半導體業類指數漲幅 1.50%", 0.75),
        (2.675, "半導體業類指數漲幅 2.67%", 1.3375),
        (21, "半導體業類指數漲幅 21.00%", 10.0),
    ],
)
def test_projected_float_and_text_reasons_keep_legacy_rounding_and_cap(
    raw_value: object,
    expected_evidence: str,
    expected_contribution: float,
) -> None:
    fact = project_industry_context_fact(
        ("半導體業",), {"漲跌百分比": raw_value}
    )

    reason = build_industry_performance_reason(fact)

    assert type(reason) is IndustryPerformanceReason
    assert reason.tag == "半導體業指數上漲"
    assert reason.evidence == expected_evidence
    assert float(reason.score_contrib) == expected_contribution
    legacy = project_legacy_industry_reason(reason)
    assert legacy == {
        "tag": "半導體業指數上漲",
        "evidence": expected_evidence,
        "score_contrib": float(expected_contribution),
    }


@pytest.mark.parametrize(
    ("raw_value", "source_kind"),
    [
        (Decimal("0"), IndustryChangeSourceKind.LEGACY_DECIMAL),
        (Decimal("-1.50"), IndustryChangeSourceKind.LEGACY_DECIMAL),
        (0.0, IndustryChangeSourceKind.LEGACY_FLOAT),
        (-1.5, IndustryChangeSourceKind.LEGACY_FLOAT),
        ("0.00%", IndustryChangeSourceKind.LEGACY_FLOAT),
        ("-1.50%", IndustryChangeSourceKind.LEGACY_FLOAT),
        ("不是百分比", IndustryChangeSourceKind.FALLBACK_ZERO),
    ],
)
def test_nonpositive_and_malformed_values_do_not_add_a_reason(
    raw_value: object,
    source_kind: IndustryChangeSourceKind,
) -> None:
    fact = project_industry_context_fact(
        ("半導體業",), {"漲跌百分比": raw_value}
    )

    assert fact.first_industry_change_source_kind is source_kind
    assert build_industry_performance_reason(fact) is None


def test_large_native_integer_preserves_legacy_float_conversion_boundary() -> None:
    positive = project_industry_context_fact(
        ("半導體業",), {"漲跌百分比": 10**400}
    )
    negative = project_industry_context_fact(
        ("半導體業",), {"漲跌百分比": -(10**400)}
    )

    assert (
        positive.first_industry_change_source_kind
        is IndustryChangeSourceKind.LEGACY_INTEGER_OVERFLOW
    )
    with pytest.raises(OverflowError, match="int too large to convert to float"):
        build_industry_performance_reason(positive)

    assert negative.first_industry_change_source_kind is IndustryChangeSourceKind.INTEGER
    assert build_industry_performance_reason(negative) is None


def test_native_positive_decimal_keeps_legacy_degraded_error() -> None:
    fact = project_industry_context_fact(
        ("半導體業",), {"漲跌百分比": Decimal("1.50")}
    )
    pre_source_kind_fact = IndustryContextFact(
        industries=("半導體業",),
        first_industry_change_percent=Decimal("1.50"),
    )

    with pytest.raises(
        TypeError,
        match=r"unsupported operand type\(s\) for \*: 'decimal.Decimal' and 'float'",
    ):
        build_industry_performance_reason(fact)
    assert (
        pre_source_kind_fact.first_industry_change_source_kind
        is IndustryChangeSourceKind.LEGACY_DECIMAL
    )
    with pytest.raises(TypeError, match="unsupported operand type"):
        build_industry_performance_reason(pre_source_kind_fact)


def test_nan_and_unavailable_industry_values_keep_legacy_empty_result() -> None:
    nan_fact = project_industry_context_fact(
        ("半導體業",), {"漲跌百分比": float("nan")}
    )
    missing_fact = project_industry_context_fact(("半導體業",), {})
    unavailable_fact = IndustryContextFact(industries=("半導體業",))

    assert build_industry_performance_reason(nan_fact) is None
    assert build_industry_performance_reason(missing_fact) is None
    assert build_industry_performance_reason(unavailable_fact) is None


def test_present_none_value_keeps_comparison_failure() -> None:
    fact = project_industry_context_fact(
        ("半導體業",), {"漲跌百分比": None}
    )

    assert fact.first_industry_change_source_kind is IndustryChangeSourceKind.UNSUPPORTED
    with pytest.raises(TypeError, match="does not support comparison"):
        build_industry_performance_reason(fact)
