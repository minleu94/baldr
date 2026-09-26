from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import date
from decimal import Decimal

import pytest

from app_module.recommendation.ml_preparation_facts import (
    CandidateFeatureFactV1,
    ML_PREPARATION_FACTS_V1,
    build_recommendation_ml_preparation_facts_v1,
)
from decision_module.recommendation.contracts import RecommendationItem
from ml_module.feature_registry import CORE_LONG_HISTORY_FEATURE_REGISTRY
from ml_module.historical_contracts import HistoricalFeatureRow
from ml_module.historical_feature_builder import HistoricalFeatureBuilder


DECISION_DATE = date(2026, 9, 25)
FEATURE_CUTOFF_DATE = date(2026, 9, 24)


def _feature_row(symbol: str, *, base: int, reverse: bool = False) -> HistoricalFeatureRow:
    values = tuple(
        (
            feature_id,
            None if index == 3 else base + index,
        )
        for index, (feature_id, _dtype, _unit) in enumerate(
            CORE_LONG_HISTORY_FEATURE_REGISTRY.canonical_schema
        )
    )
    if reverse:
        values = tuple(reversed(values))
    return HistoricalFeatureRow(
        symbol=symbol,
        decision_date=DECISION_DATE.isoformat(),
        feature_as_of_date=FEATURE_CUTOFF_DATE.isoformat(),
        available_date=DECISION_DATE.isoformat(),
        values=values,
    )


def _items() -> tuple[RecommendationItem, ...]:
    return (
        RecommendationItem(
            stock_code="2330",
            rule_score=Decimal("12.50"),
            rank=1,
            reasons=("rule-a", "rule-b"),
        ),
        RecommendationItem(
            stock_code="2317",
            rule_score=17,
            rank=2,
            reasons=("rule-c",),
        ),
    )


def _build(
    *,
    result_id: str = "result-r026-001",
    items: tuple[RecommendationItem, ...] | None = None,
    rows: tuple[HistoricalFeatureRow, ...] | None = None,
    feature_cutoff_date: date = FEATURE_CUTOFF_DATE,
):
    selected_items = _items() if items is None else items
    feature_rows = (
        (_feature_row("2330", base=100), _feature_row("2317", base=200))
        if rows is None
        else rows
    )
    return build_recommendation_ml_preparation_facts_v1(
        result_id=result_id,
        decision_date=DECISION_DATE,
        feature_cutoff_date=feature_cutoff_date,
        selected_items=selected_items,
        feature_rows=feature_rows,
        feature_builder=HistoricalFeatureBuilder(
            CORE_LONG_HISTORY_FEATURE_REGISTRY
        ),
    )


def test_preparation_facts_preserve_ordered_selected_items_and_canonical_features() -> None:
    facts = _build()

    assert facts.contract_version == ML_PREPARATION_FACTS_V1
    assert facts.result_id == "result-r026-001"
    assert facts.decision_date == DECISION_DATE
    assert facts.feature_cutoff_date == FEATURE_CUTOFF_DATE
    assert facts.feature_ids == CORE_LONG_HISTORY_FEATURE_REGISTRY.canonical_ids
    assert facts.feature_schema == CORE_LONG_HISTORY_FEATURE_REGISTRY.canonical_schema
    assert tuple(candidate.symbol for candidate in facts.candidates) == (
        "2330",
        "2317",
    )
    assert tuple(candidate.selection_index for candidate in facts.candidates) == (0, 1)
    assert facts.candidates[0].feature_values == tuple(
        None if index == 3 else 100 + index
        for index, _ in enumerate(facts.feature_ids)
    )
    assert facts.candidates[1].feature_values == tuple(
        None if index == 3 else 200 + index
        for index, _ in enumerate(facts.feature_ids)
    )
    assert all(candidate.candidate_id.startswith("candidate.v1:") for candidate in facts.candidates)
    assert all(candidate.candidate_id != candidate.symbol for candidate in facts.candidates)
    assert facts.candidates[0].candidate_id != facts.candidates[1].candidate_id
    assert facts.payload_sha256 == (
        "sha256:e8516ec9535dd14d7501aafc893bc67e93db374f38add3d679369e280a66347b"
    )
    assert tuple(candidate.candidate_id for candidate in facts.candidates) == (
        "candidate.v1:80fd427d7840ad758302c920a7cc5aca2558a79e838dc263255493ea957926df",
        "candidate.v1:51927b62b1acbe4fadb9d2f580466b2b365edb088390b41362a4cdb3939a9bf5",
    )

    with pytest.raises(FrozenInstanceError):
        facts.result_id = "mutated"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        facts.candidates[0].symbol = "2317"  # type: ignore[misc]


def test_preparation_facts_are_stable_and_candidate_identity_binds_item_and_features() -> None:
    first = _build()
    same = _build()
    changed_result = _build(result_id="result-r026-002")
    changed_item = _build(
        items=(
            RecommendationItem(
                stock_code="2330",
                rule_score=Decimal("12.51"),
                rank=1,
                reasons=("rule-a", "rule-b"),
            ),
            _items()[1],
        )
    )
    changed_feature = _build(
        rows=(_feature_row("2330", base=101), _feature_row("2317", base=200))
    )

    assert first.candidates[0].candidate_id == same.candidates[0].candidate_id
    assert first.payload_sha256 == same.payload_sha256
    assert first.candidates[0].candidate_id != changed_result.candidates[0].candidate_id
    assert first.candidates[0].candidate_id != changed_item.candidates[0].candidate_id
    assert first.candidates[0].symbol == changed_feature.candidates[0].symbol
    assert first.candidates[0].candidate_id != changed_feature.candidates[0].candidate_id
    assert (
        first.candidates[0].feature_row_sha256
        != changed_feature.candidates[0].feature_row_sha256
    )


def test_feature_builder_load_remains_the_only_feature_order_authority() -> None:
    rows = (
        _feature_row("2330", base=100, reverse=True),
        _feature_row("2317", base=200),
    )
    facts = _build(
        rows=rows
    )
    canonical_vector = HistoricalFeatureBuilder(
        CORE_LONG_HISTORY_FEATURE_REGISTRY
    ).load(rows[0])

    assert facts.feature_ids == CORE_LONG_HISTORY_FEATURE_REGISTRY.canonical_ids
    assert facts.candidates[0].feature_row_sha256 == canonical_vector.snapshot_hash
    assert facts.candidates[0].feature_values == tuple(
        None if index == 3 else 100 + index
        for index, _ in enumerate(facts.feature_ids)
    )
    assert facts.candidates[0].feature_values == canonical_vector.values


def test_preparation_facts_reject_item_feature_omission_or_order_mismatch() -> None:
    with pytest.raises(ValueError, match="candidate.*order|order.*candidate"):
        _build(
            rows=(_feature_row("2317", base=200), _feature_row("2330", base=100))
        )

    with pytest.raises(ValueError, match="same number|count|length|相同數量"):
        _build(rows=(_feature_row("2330", base=100),))

    with pytest.raises(ValueError, match="duplicate|unique|不可重複"):
        _build(
            items=(
                RecommendationItem(stock_code="2330", rank=1),
                RecommendationItem(stock_code="2330", rank=2),
            ),
            rows=(_feature_row("2330", base=100), _feature_row("2330", base=200)),
        )


def test_preparation_facts_reject_incomplete_schema_boolean_and_wrong_cutoff() -> None:
    incomplete = HistoricalFeatureRow(
        symbol="2330",
        decision_date=DECISION_DATE.isoformat(),
        feature_as_of_date=FEATURE_CUTOFF_DATE.isoformat(),
        available_date=DECISION_DATE.isoformat(),
        values=(
            (CORE_LONG_HISTORY_FEATURE_REGISTRY.canonical_ids[0], 1),
        ),
    )
    with pytest.raises(ValueError, match="feature id set mismatch"):
        _build(rows=(incomplete, _feature_row("2317", base=200)))

    with pytest.raises(TypeError, match="integer units"):
        HistoricalFeatureRow(
            symbol="2330",
            decision_date=DECISION_DATE.isoformat(),
            feature_as_of_date=FEATURE_CUTOFF_DATE.isoformat(),
            available_date=DECISION_DATE.isoformat(),
            values=(
                (CORE_LONG_HISTORY_FEATURE_REGISTRY.canonical_ids[0], True),
            ),
        )

    with pytest.raises(ValueError, match="cutoff"):
        _build(
            rows=(
                HistoricalFeatureRow(
                    symbol="2330",
                    decision_date=DECISION_DATE.isoformat(),
                    feature_as_of_date="2026-09-23",
                    available_date=DECISION_DATE.isoformat(),
                    values=_feature_row("2330", base=100).values,
                ),
                _feature_row("2317", base=200),
            )
        )


def test_candidate_fact_rejects_bool_as_integer_feature_value() -> None:
    with pytest.raises(TypeError, match="bool"):
        CandidateFeatureFactV1(
            candidate_id="candidate.v1:" + "0" * 64,
            symbol="2330",
            selection_index=0,
            selected_item_sha256="sha256:" + "1" * 64,
            feature_values=(True,),
            feature_row_sha256="sha256:" + "2" * 64,
            feature_as_of_date=FEATURE_CUTOFF_DATE,
            available_date=DECISION_DATE,
        )


def test_preparation_facts_reject_extra_feature_id() -> None:
    source_row = _feature_row("2330", base=100)
    with_extra = HistoricalFeatureRow(
        symbol=source_row.symbol,
        decision_date=source_row.decision_date,
        feature_as_of_date=source_row.feature_as_of_date,
        available_date=source_row.available_date,
        values=source_row.values + (("unregistered.extra", 7),),
    )
    with pytest.raises(ValueError, match="feature id set mismatch"):
        _build(rows=(with_extra, _feature_row("2317", base=200)))


def test_preparation_facts_reject_bad_result_or_date_identity() -> None:
    with pytest.raises(ValueError, match="result_id"):
        _build(result_id=" ")

    with pytest.raises(ValueError, match="decision_date|cutoff"):
        build_recommendation_ml_preparation_facts_v1(
            result_id="result-r026-001",
            decision_date=DECISION_DATE,
            feature_cutoff_date=date(2026, 9, 26),
            selected_items=_items(),
            feature_rows=(_feature_row("2330", base=100), _feature_row("2317", base=200)),
            feature_builder=HistoricalFeatureBuilder(
                CORE_LONG_HISTORY_FEATURE_REGISTRY
            ),
        )
