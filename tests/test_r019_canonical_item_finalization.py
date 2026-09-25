from __future__ import annotations

import ast
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from decision_module.recommendation.contracts import (
    CandidateAssessment,
    RecommendationItem,
    UniverseReference,
)
from decision_module.recommendation.evaluate import (
    CandidateEvaluationOutcome,
    RecommendationScore,
)
from decision_module.recommendation.finalization import (
    RecommendationItemFacts,
    finalize_candidate_item,
    reason_tags_from_legacy_reasons,
)


def _outcome(
    *,
    invocation_id: str = "item-finalize-run-a",
    stock_code: str = "2330",
    item: RecommendationItem | None = None,
    score: RecommendationScore | None = None,
) -> CandidateEvaluationOutcome:
    canonical_item = item or RecommendationItem(
        stock_code=stock_code,
        stock_name="TSMC",
        rule_score=Decimal("84.0100"),
    )
    canonical_score = score or RecommendationScore(
        ordering_value=Decimal("84.01"),
        quantile_score_bp=8401,
    )
    return CandidateEvaluationOutcome(
        invocation_id=invocation_id,
        stock_code=stock_code,
        status="fail",
        quality="observed",
        stage="candidate_scored",
        reason_codes=("pending_final_selection",),
        item=canonical_item,
        assessment=CandidateAssessment(stock_code=stock_code, eligible=True),
        score=canonical_score,
    )


def _facts(
    *,
    invocation_id: str = "item-finalize-run-a",
    stock_code: str = "2330",
    reasons: tuple[str, ...] = ("PE 通過", "營收成長", "產業上漲", "量價確認"),
) -> RecommendationItemFacts:
    return RecommendationItemFacts(
        invocation_id=invocation_id,
        stock_code=stock_code,
        stock_name="TSMC",
        close_price=Decimal("100.00"),
        price_change=Decimal("1.2300"),
        indicator_score=Decimal("18.50"),
        pattern_score=Decimal("12.25"),
        volume_score=Decimal("3.75"),
        industry="半導體業",
        reason_text="PE 通過+、營收成長+、產業上漲+",
        reasons=reasons,
        universe_policy_id="policy-current",
        universe_snapshot_id="snapshot-current",
        universe_as_of_date=date(2026, 5, 20),
        universe_members_hash="a" * 64,
        regime_match=True,
    )


def test_finalizer_reuses_staged_rule_score_and_builds_complete_item() -> None:
    original = _outcome()

    finalized = finalize_candidate_item(original, _facts())

    assert finalized is not original
    assert finalized.assessment is original.assessment
    assert finalized.score is original.score
    assert finalized.item is not None
    assert finalized.item.rule_score is original.item.rule_score  # type: ignore[union-attr]
    assert finalized.item.rule_score == Decimal("84.0100")
    assert type(finalized.item.rule_score) is Decimal
    assert finalized.item.close_price == Decimal("100.00")
    assert type(finalized.item.close_price) is Decimal
    assert finalized.item.price_change == Decimal("1.2300")
    assert type(finalized.item.price_change) is Decimal
    assert finalized.item.indicator_score == Decimal("18.50")
    assert type(finalized.item.indicator_score) is Decimal
    assert finalized.item.pattern_score == Decimal("12.25")
    assert type(finalized.item.pattern_score) is Decimal
    assert finalized.item.volume_score == Decimal("3.75")
    assert type(finalized.item.volume_score) is Decimal
    assert finalized.item.stock_name == "TSMC"
    assert finalized.item.industry == "半導體業"
    assert finalized.item.reason_text == "PE 通過+、營收成長+、產業上漲+"
    assert finalized.item.reasons == ("PE 通過", "營收成長", "產業上漲", "量價確認")
    assert finalized.item.regime_match is True
    assert finalized.item.universe_ref == UniverseReference(
        policy_id="policy-current",
        snapshot_id="snapshot-current",
        as_of_date=date(2026, 5, 20),
        members_hash="a" * 64,
    )


def test_reason_tag_projection_keeps_all_ordered_tags_and_legacy_filtering() -> None:
    tags = reason_tags_from_legacy_reasons(
        (
            {"tag": "first"},
            {"tag": "second"},
            {"tag": ""},
            {"tag": 17},
            {"evidence": "no tag"},
            "not a reason mapping",
        )
    )

    assert tags == ("first", "second", "17")


@pytest.mark.parametrize(
    ("outcome_invocation", "outcome_code", "facts_invocation", "facts_code"),
    [
        ("run-a", "2330", "run-b", "2330"),
        ("run-a", "2330", "run-a", "2317"),
    ],
)
def test_finalizer_rejects_cross_candidate_facts(
    outcome_invocation: str,
    outcome_code: str,
    facts_invocation: str,
    facts_code: str,
) -> None:
    with pytest.raises(ValueError, match="identity"):
        finalize_candidate_item(
            _outcome(invocation_id=outcome_invocation, stock_code=outcome_code),
            _facts(invocation_id=facts_invocation, stock_code=facts_code),
        )


def test_finalizer_rejects_outcome_without_staged_item() -> None:
    outcome = CandidateEvaluationOutcome(
        invocation_id="item-finalize-run-a",
        stock_code="2330",
        status="missing",
        quality="missing",
        stage="strategy_evaluation",
        reason_codes=("total_score_missing_or_nonfinite",),
        assessment=CandidateAssessment(stock_code="2330", eligible=None),
    )

    with pytest.raises(ValueError, match="只有 evaluator 成功評分"):
        finalize_candidate_item(outcome, _facts())


def test_finalization_module_has_no_reverse_layer_imports() -> None:
    source = Path("decision_module/recommendation/finalization.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    forbidden_roots = {"app_module", "data_module", "ui_qt", "scripts"}

    imported_roots = {
        node.module.split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    imported_roots.update(
        alias.name.split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    )

    assert imported_roots.isdisjoint(forbidden_roots)
