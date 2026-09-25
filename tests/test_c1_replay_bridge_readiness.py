"""C1 R017 option-2 readiness tests; these do not implement a replay bridge."""

from __future__ import annotations

from dataclasses import asdict, fields, replace
from datetime import date, datetime
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from app_module.recommendation.contracts import (
    Context,
    ExecutionStatus,
    RecommendationExecution,
    ReferenceKind,
    Request,
    VersionReference,
)
from app_module.recommendation_portfolio_dtos import (
    RecommendationPortfolioBacktestResultDTO,
)
from app_module.recommendation_replay_service import RecommendationReplayService
from data_module.contracts.market import SourceRef
from decision_module.recommendation.contracts import DecisionBatch, RecommendationItem


_FIXTURE_PATH = (
    Path(__file__).parent
    / "fixtures"
    / "c1_replay_bridge"
    / "r017_stored_annotation_snapshot.json"
)
_FIXTURE_MANIFEST_PATH = _FIXTURE_PATH.with_name("fixture_manifest.json")
_FIXTURE_ID = "c1-r017-option-2-stored-annotation"


def _load_fixture() -> tuple[dict[str, Any], bytes, dict[str, Any]]:
    manifest = json.loads(_FIXTURE_MANIFEST_PATH.read_bytes().decode("utf-8"))
    assert manifest["manifest_version"] == "c1-replay-bridge-fixtures.v1"
    matches = [
        entry
        for entry in manifest["fixtures"]
        if entry["fixture_id"] == _FIXTURE_ID
    ]
    assert len(matches) == 1
    pinned = matches[0]

    fixture_bytes = _FIXTURE_PATH.read_bytes()
    assert pinned["path"] == _FIXTURE_PATH.name
    assert pinned["hash_basis"] == "raw UTF-8 fixture bytes"
    assert len(fixture_bytes) == pinned["byte_length"]
    assert "sha256:" + hashlib.sha256(fixture_bytes).hexdigest() == pinned["sha256"]

    fixture = json.loads(fixture_bytes.decode("utf-8"))
    assert fixture["fixture_id"] == pinned["fixture_id"]
    assert fixture["fixture_scope"] == "synthetic-only"
    assert pinned["format"] == {
        "encoding": "UTF-8",
        "kind": "legacy-replay-snapshot-json",
        "has_canonical_execution_envelope": False,
        "schema_version": None,
        "schema_revision": None,
    }

    child = fixture["typed_child"]
    first_provider_row = fixture["provider_recommendations"][0]
    first_source_ref = first_provider_row["source_refs"][0]
    opaque_ids = pinned["opaque_ids"]
    assert opaque_ids == {
        "profile_id": fixture["snapshot"]["profile_id"],
        "typed_child_result_id": child["result_id"],
        "policy_id": child["policy_ref"]["reference_id"],
        "data_snapshot_id": child["data_snapshot_ref"]["reference_id"],
        "source_id": child["source_ref"]["source_id"],
        "source_snapshot_id": child["source_ref"]["snapshot_id"],
    }
    assert pinned["clocks"] == {
        "as_of_date": fixture["snapshot"]["as_of_date"],
        "decision_at": child["decision_at"],
        "created_at": child["created_at"],
        "available_at": child["available_at"],
    }
    assert first_provider_row["available_at"] == pinned["clocks"]["available_at"]
    assert pinned["unknown_source_flags"] == {
        "fixture_scope": "synthetic-only",
        "stored_annotation_value_origin": "test-fixture-injection-only",
        "stored_annotation_source_value": first_provider_row["stored_annotation"][
            "source"
        ],
        "production_annotation_source": "unknown",
        "parent_result_id": "unknown",
        "parent_source": "unknown",
        "canonical_ml_artifact": False,
    }
    assert "parent_result_id" not in child
    assert first_source_ref["source_id"] == opaque_ids["source_id"]
    assert first_source_ref["snapshot_id"] == opaque_ids["source_snapshot_id"]
    return fixture, fixture_bytes, pinned


def _assert_fixture_bytes_unchanged(
    fixture_bytes_before: bytes, pinned: dict[str, Any]
) -> None:
    fixture_bytes_after = _FIXTURE_PATH.read_bytes()
    assert fixture_bytes_after == fixture_bytes_before
    assert len(fixture_bytes_after) == pinned["byte_length"]
    assert "sha256:" + hashlib.sha256(fixture_bytes_after).hexdigest() == pinned[
        "sha256"
    ]


def _build_legacy_snapshot(fixture: dict[str, Any]):
    provider_calls: list[dict[str, Any]] = []

    def stored_result_provider(
        data: pd.DataFrame, config: dict[str, Any], top_n: int
    ) -> list[dict[str, Any]]:
        provider_calls.append(
            {
                "codes": data["證券代號"].astype(str).tolist(),
                "config": config,
                "top_n": top_n,
            }
        )
        return fixture["provider_recommendations"][:top_n]

    history = pd.DataFrame(
        {
            "日期": ["2026-09-01", "2026-09-01"],
            "證券代號": ["2330", "2317"],
            "available_date": ["2026-09-01", "2026-09-01"],
        }
    )
    snapshot_spec = fixture["snapshot"]
    snapshot = RecommendationReplayService(stored_result_provider).run_snapshot(
        as_of_date=snapshot_spec["as_of_date"],
        profile_id=snapshot_spec["profile_id"],
        config=dict(snapshot_spec["strategy_config"]),
        history=history,
        universe=None,
        top_n=snapshot_spec["strategy_config"]["top_n"],
    )
    return snapshot, provider_calls


def _build_synthetic_child(fixture: dict[str, Any]) -> RecommendationExecution:
    """Build only the explicit synthetic typed sample used by this readiness test."""

    child_spec = fixture["typed_child"]
    policy_spec = child_spec["policy_ref"]
    data_ref_spec = child_spec["data_snapshot_ref"]
    source_ref_spec = child_spec["source_ref"]
    policy_ref = VersionReference(
        kind=ReferenceKind(policy_spec["kind"]),
        reference_id=policy_spec["reference_id"],
        version=policy_spec["version"],
    )
    data_snapshot_ref = VersionReference(
        kind=ReferenceKind(data_ref_spec["kind"]),
        reference_id=data_ref_spec["reference_id"],
        version=data_ref_spec["version"],
    )
    source_ref = SourceRef(
        source_id=source_ref_spec["source_id"],
        revision=source_ref_spec["revision"],
        snapshot_id=source_ref_spec["snapshot_id"],
    )
    items = tuple(
        RecommendationItem(
            stock_code=item_spec["stock_code"],
            stock_name=item_spec["stock_name"],
            rule_score=Decimal(item_spec["rule_score"]),
            indicator_score=Decimal(item_spec["indicator_score"]),
            reason_text=item_spec["reason_text"],
        )
        for item_spec in child_spec["items"]
    )
    request = Request(
        as_of_date=date.fromisoformat(child_spec["as_of_date"]),
        policy_ref=policy_ref,
        top_n=len(items),
    )
    context = Context(
        as_of_date=date.fromisoformat(child_spec["as_of_date"]),
        decision_at=datetime.fromisoformat(child_spec["decision_at"]),
        created_at=datetime.fromisoformat(child_spec["created_at"]),
        available_at=datetime.fromisoformat(child_spec["available_at"]),
        source_refs=(source_ref,),
        data_snapshot_refs=(data_snapshot_ref,),
        policy_ref=policy_ref,
    )
    return RecommendationExecution(
        result_id=child_spec["result_id"],
        request=request,
        context=context,
        status=ExecutionStatus.COMPLETED,
        decision=DecisionBatch(items=items, regime=fixture["snapshot"]["regime"]),
    )


def _assert_child_matches_pinned_fixture_oracle(
    child: RecommendationExecution, fixture: dict[str, Any]
) -> None:
    """Assert exact typed-child fields against the pinned synthetic fixture."""

    spec = fixture["typed_child"]
    assert child.result_id == spec["result_id"], (
        "typed child result_id differs from pinned fixture"
    )
    assert child.status is ExecutionStatus.COMPLETED, (
        "typed child status differs from pinned fixture"
    )
    assert child.request.as_of_date == date.fromisoformat(spec["as_of_date"]), (
        "typed child Request.as_of_date differs from pinned fixture"
    )
    assert child.request.top_n == len(spec["items"]), (
        "typed child Request.top_n differs from pinned fixture"
    )
    expected_policy = VersionReference(
        ReferenceKind(spec["policy_ref"]["kind"]),
        spec["policy_ref"]["reference_id"],
        spec["policy_ref"]["version"],
    )
    assert child.request.policy_ref == expected_policy, (
        "typed child Request.policy_ref differs from pinned fixture"
    )

    assert child.context.as_of_date == date.fromisoformat(spec["as_of_date"]), (
        "typed child Context.as_of_date differs from pinned fixture"
    )
    for clock_name in ("decision_at", "created_at", "available_at"):
        assert getattr(child.context, clock_name) == datetime.fromisoformat(
            spec[clock_name]
        ), f"typed child Context.{clock_name} differs from pinned fixture"
    assert child.context.available_at <= child.context.decision_at
    assert child.context.policy_ref == expected_policy, (
        "typed child Context.policy_ref differs from pinned fixture"
    )

    data_ref_spec = spec["data_snapshot_ref"]
    expected_data_ref = VersionReference(
        ReferenceKind(data_ref_spec["kind"]),
        data_ref_spec["reference_id"],
        data_ref_spec["version"],
    )
    assert child.context.data_snapshot_refs == (expected_data_ref,), (
        "typed child data_snapshot_refs differ from pinned fixture"
    )
    source_ref_spec = spec["source_ref"]
    expected_source_ref = SourceRef(
        source_id=source_ref_spec["source_id"],
        revision=source_ref_spec["revision"],
        snapshot_id=source_ref_spec["snapshot_id"],
    )
    assert child.context.source_refs == (expected_source_ref,), (
        "typed child source_refs differ from pinned fixture"
    )

    assert child.decision is not None, (
        "typed child decision missing from pinned fixture"
    )
    assert child.decision.regime == fixture["snapshot"]["regime"], (
        "typed child regime differs from pinned fixture"
    )
    assert len(child.decision.items) == len(spec["items"]), (
        "typed child item count differs from pinned fixture"
    )
    for index, (actual, expected) in enumerate(
        zip(child.decision.items, spec["items"])
    ):
        assert actual.stock_code == expected["stock_code"], (
            f"typed child row[{index}].stock_code differs from pinned fixture"
        )
        assert actual.stock_name == expected["stock_name"], (
            f"typed child row[{index}].stock_name differs from pinned fixture"
        )
        assert type(actual.rule_score) is Decimal, (
            f"typed child row[{index}].rule_score is not Decimal"
        )
        assert actual.rule_score == Decimal(expected["rule_score"]), (
            f"typed child row[{index}].rule_score differs from pinned fixture"
        )
        assert type(actual.indicator_score) is Decimal, (
            f"typed child row[{index}].indicator_score is not Decimal"
        )
        assert actual.indicator_score == Decimal(expected["indicator_score"]), (
            f"typed child row[{index}].indicator_score differs from pinned fixture"
        )
        assert actual.reason_text == expected["reason_text"], (
            f"typed child row[{index}].reason_text differs from pinned fixture"
        )

    assert child.related_references == (), (
        "typed child has unpinned related references"
    )
    assert child.ml_projection_refs == (), "typed child has unpinned ML projections"
    assert child.ml_receipt_refs == (), "typed child has unpinned ML receipts"
    assert "parent_result_id" not in {field.name for field in fields(child)}, (
        "typed child exposes an unpinned parent reference"
    )


def test_option_2_outer_legacy_annotation_and_provenance_roundtrip_exactly():
    fixture, fixture_bytes_before, pinned = _load_fixture()
    snapshot, provider_calls = _build_legacy_snapshot(fixture)
    result = RecommendationPortfolioBacktestResultDTO(
        summary={},
        equity_curve=pd.DataFrame(),
        trades=pd.DataFrame(),
        snapshots=[snapshot],
        period_holdings=[],
        stock_contribution=[],
    )

    encoded = result.to_dict()
    serialized = json.dumps(
        encoded, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    decoded = json.loads(serialized.decode("utf-8"))
    restored = RecommendationPortfolioBacktestResultDTO.from_dict(decoded)
    restored_encoded = restored.to_dict()

    expected_rows = fixture["provider_recommendations"]
    restored_snapshot = restored.snapshots[0]
    assert provider_calls == [
        {
            "codes": ["2330", "2317"],
            "config": fixture["snapshot"]["strategy_config"],
            "top_n": 2,
        }
    ]
    assert restored_encoded == encoded
    assert restored_snapshot.as_of_date == "2026-09-01"
    assert restored_snapshot.profile_id == "stored-profile-v1"
    assert restored_snapshot.recommendations == expected_rows
    assert [row["stock_code"] for row in restored_snapshot.recommendations] == [
        "2330",
        "2317",
    ]
    assert [row["total_score"] for row in restored_snapshot.recommendations] == [
        82.35,
        71.25,
    ]
    assert all(type(row["total_score"]) is float for row in restored_snapshot.recommendations)
    assert restored_snapshot.recommendations[0]["stored_annotation"] == {
        "probability_bp": 8123,
        "model_version": "historical-model-v1",
        "source": "stored-result",
    }
    assert type(
        restored_snapshot.recommendations[0]["stored_annotation"]["probability_bp"]
    ) is int
    for expected_row, observed_row in zip(
        expected_rows, restored_snapshot.recommendations
    ):
        assert observed_row["available_date"] == expected_row["available_date"]
        assert observed_row["available_at"] == expected_row["available_at"]
        assert observed_row["source_refs"] == expected_row["source_refs"]
    _assert_fixture_bytes_unchanged(fixture_bytes_before, pinned)


def test_option_2_typed_child_keeps_known_values_and_has_no_annotation_or_parent(
    tmp_path: Path,
):
    fixture, fixture_bytes_before, pinned = _load_fixture()
    snapshot, _ = _build_legacy_snapshot(fixture)
    child = _build_synthetic_child(fixture)
    _assert_child_matches_pinned_fixture_oracle(child, fixture)

    assert snapshot.recommendations == fixture["provider_recommendations"]
    assert child.request.as_of_date == date(2026, 9, 1)
    assert child.request.top_n == 2
    assert child.request.policy_ref == VersionReference(
        ReferenceKind.POLICY, "legacy-replay-policy-v1", "v1"
    )
    assert child.context.as_of_date == date(2026, 9, 1)
    assert child.context.decision_at == datetime.fromisoformat(
        "2026-09-01T13:30:00+08:00"
    )
    assert child.context.created_at == datetime.fromisoformat(
        "2026-09-01T13:29:00+08:00"
    )
    assert child.context.available_at == datetime.fromisoformat(
        "2026-09-01T13:25:00+08:00"
    )
    assert child.context.available_at <= child.context.decision_at
    assert child.context.data_snapshot_refs == (
        VersionReference(
            ReferenceKind.DATA_SNAPSHOT,
            "c1-replay-history-v1",
            "r005-fixture-v1",
        ),
    )
    assert child.context.source_refs == (
        SourceRef(
            "synthetic-replay-provider",
            "r005-fixture-v1",
            "c1-replay-history-v1",
        ),
    )
    assert child.context.policy_ref == child.request.policy_ref
    assert child.decision is not None
    assert [item.stock_code for item in child.decision.items] == ["2330", "2317"]
    assert [item.rule_score for item in child.decision.items] == [
        Decimal("82.35"),
        Decimal("71.25"),
    ]
    assert [item.indicator_score for item in child.decision.items] == [
        Decimal("70.0"),
        Decimal("62.5"),
    ]
    assert [item.reason_text for item in child.decision.items] == [
        "fixture_reason",
        "fixture_second_reason",
    ]
    assert all(
        "stored_annotation" not in asdict(item)
        for item in child.decision.items
    )
    assert child.related_references == ()
    assert child.ml_projection_refs == ()
    assert child.ml_receipt_refs == ()
    assert "stored_annotation" not in {item.name for item in fields(RecommendationItem)}
    assert "parent_result_id" not in {
        item.name for item in fields(RecommendationExecution)
    }
    assert "extended_attributes" not in {
        item.name for item in fields(RecommendationExecution)
    }
    assert list(tmp_path.iterdir()) == []
    _assert_fixture_bytes_unchanged(fixture_bytes_before, pinned)


@pytest.mark.parametrize(
    "mutation",
    ["stock_code", "order", "stock_name", "rule_score", "indicator_score", "reason_text"],
)
def test_option_2_negative_examples_fail_exact_pinned_fixture_oracle(
    mutation: str,
):
    fixture, _, _ = _load_fixture()
    child = _build_synthetic_child(fixture)
    _assert_child_matches_pinned_fixture_oracle(child, fixture)
    assert child.decision is not None
    items = list(child.decision.items)
    if mutation == "stock_code":
        items[0] = replace(items[0], stock_code="9999")
    elif mutation == "order":
        items.reverse()
    elif mutation == "stock_name":
        items[0] = replace(items[0], stock_name="changed-name")
    elif mutation == "rule_score":
        items[0] = replace(items[0], rule_score=Decimal("82.36"))
    elif mutation == "indicator_score":
        items[0] = replace(items[0], indicator_score=Decimal("70.01"))
    else:
        items[0] = replace(items[0], reason_text="changed-reason")
    changed = replace(
        child,
        decision=DecisionBatch(items=tuple(items), regime=child.decision.regime),
    )

    with pytest.raises(AssertionError, match="differs from pinned fixture"):
        _assert_child_matches_pinned_fixture_oracle(changed, fixture)


def test_option_2_contract_rejects_annotation_and_fabricated_parent_fields():
    fixture, fixture_bytes_before, pinned = _load_fixture()
    assert fixture["fixture_scope"] == "synthetic-only"
    with pytest.raises(TypeError, match="unexpected keyword argument 'stored_annotation'"):
        RecommendationItem(
            stock_code="2330",
            rule_score=Decimal("82.35"),
            stored_annotation={"probability_bp": 8123},  # type: ignore[call-arg]
        )

    with pytest.raises(TypeError, match="unexpected keyword argument 'parent_result_id'"):
        RecommendationExecution(
            result_id="c1-r017-synthetic-child-001",
            request=Request(),
            context=Context(),
            status=ExecutionStatus.COMPLETED,
            decision=DecisionBatch(),
            parent_result_id="inferred-parent",  # type: ignore[call-arg]
        )
    _assert_fixture_bytes_unchanged(fixture_bytes_before, pinned)
