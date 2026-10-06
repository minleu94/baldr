"""R019 C3C2 contract tests for the invocation legacy-state snapshot."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app_module.recommendation.legacy_compatibility import (
    LegacyCompatibilitySnapshot,
)
from app_module.recommendation_calibration_consumer import (
    RecommendationCalibrationProjection,
)


_LEGACY_FIELDS = (
    "last_calibration_projections",
    "last_screening_matrix",
    "last_excluded_candidates_json",
    "last_why_not_payload_json",
    "last_liquidity_gate_payload_json",
    "last_exclusion_quality",
    "last_exclusion_warnings_json",
    "last_run_context",
)


def _projection() -> RecommendationCalibrationProjection:
    return RecommendationCalibrationProjection(
        stock_code="2330",
        ranking_score_bp=8_500,
        ranking_percentile_bp=9_000,
        ranking_method="fixed",
        calibrated_probability_bp=6_800,
        calibrated_probability_status="available",
        after_cost_profit_probability_bp=6_400,
        after_cost_profit_probability_status="available",
        confidence_tier="medium",
        evidence_confidence="observed",
        sample_size=128,
        horizon="20 trading days",
        cost_basis="round_trip",
        cost_basis_bp=50,
        model_version="model-v1",
        dataset_version="dataset-v1",
        source_trace=("source-v1",),
        status="available",
        training_provenance={
            "dataset": {"rows": [{"symbol": "2330", "fold": 1}]}
        },
        inference_provenance={
            "features": {"ordered": ["momentum", "volume"]}
        },
        provenance_compatibility={"compatible": True, "checks": ["schema"]},
    )


def _invocation() -> tuple[SimpleNamespace, dict[str, Any], RecommendationCalibrationProjection]:
    aliased_row: dict[str, Any] = {
        "stock_code": "2330",
        "reason_codes": ["volume_ok"],
        "nested": {"evidence": ["observed"]},
    }
    projection = _projection()
    invocation = SimpleNamespace(
        last_calibration_projections={"2330": projection},
        last_screening_matrix=[aliased_row],
        last_excluded_candidates_json=[{"stock_code": "2317", "reason": "filtered"}],
        last_why_not_payload_json=[aliased_row],
        last_liquidity_gate_payload_json=[aliased_row],
        last_exclusion_quality="degraded",
        last_exclusion_warnings_json=["screening_contains_unknown_evidence"],
        last_run_context={
            "as_of_date": "2026-05-20",
            "warnings": ["captured"],
        },
    )
    return invocation, aliased_row, projection


def _capture(
    invocation: object,
    *,
    body_invocation_id: str | None = "r019-body-a",
) -> LegacyCompatibilitySnapshot:
    return LegacyCompatibilitySnapshot.capture_from_invocation(
        invocation,
        capture_id="r019-capture-a",
        result_id="r019-result-a",
        body_invocation_id=body_invocation_id,
    )


def test_snapshot_detaches_one_eight_field_graph_and_preserves_cross_field_aliases() -> None:
    invocation, source_row, source_projection = _invocation()
    snapshot = _capture(invocation)

    assert snapshot.capture_id == "r019-capture-a"
    assert snapshot.result_id == "r019-result-a"
    assert snapshot.body_invocation_id == "r019-body-a"

    # The input graph can keep changing after capture; the snapshot owns its copy.
    source_row["reason_codes"].append("mutated-after-capture")
    source_row["nested"]["evidence"].append("later")
    source_projection.training_provenance["dataset"]["rows"][0]["symbol"] = "9999"
    invocation.last_exclusion_warnings_json.append("later-warning")
    invocation.last_run_context["warnings"].append("later-context-warning")

    first = snapshot.materialize()
    assert type(first) is dict
    assert tuple(first) == _LEGACY_FIELDS

    matrix_row = first["last_screening_matrix"][0]
    assert matrix_row is first["last_why_not_payload_json"][0]
    assert matrix_row is first["last_liquidity_gate_payload_json"][0]
    assert matrix_row is not source_row
    assert matrix_row["reason_codes"] == ["volume_ok"]
    assert matrix_row["nested"]["evidence"] == ["observed"]
    assert first["last_exclusion_warnings_json"] == [
        "screening_contains_unknown_evidence"
    ]
    assert first["last_run_context"]["warnings"] == ["captured"]

    captured_projection = first["last_calibration_projections"]["2330"]
    assert type(captured_projection) is RecommendationCalibrationProjection
    assert type(captured_projection.training_provenance) is dict
    assert type(captured_projection.inference_provenance) is dict
    assert type(captured_projection.provenance_compatibility) is dict
    assert captured_projection.training_provenance == {
        "dataset": {"rows": [{"symbol": "2330", "fold": 1}]}
    }

    # The alias is retained within a materialized graph, but that graph is
    # private to this call; another materialization cannot observe its mutation.
    matrix_row["reason_codes"].append("first-materialization-only")
    captured_projection.training_provenance["dataset"]["rows"][0]["symbol"] = "1111"
    second = snapshot.materialize()
    assert second is not first
    assert second["last_screening_matrix"] is not first["last_screening_matrix"]
    second_row = second["last_screening_matrix"][0]
    assert second_row is second["last_why_not_payload_json"][0]
    assert second_row is second["last_liquidity_gate_payload_json"][0]
    assert second_row is not matrix_row
    assert second_row["reason_codes"] == ["volume_ok"]
    assert second["last_calibration_projections"]["2330"].training_provenance == {
        "dataset": {"rows": [{"symbol": "2330", "fold": 1}]}
    }


def test_snapshot_identity_properties_are_read_only_and_body_identity_can_be_unknown() -> None:
    invocation, _, _ = _invocation()
    snapshot = _capture(invocation, body_invocation_id=None)

    assert snapshot.body_invocation_id is None
    with pytest.raises(AttributeError):
        setattr(snapshot, "capture_id", "replacement")
    with pytest.raises(AttributeError):
        setattr(snapshot, "result_id", "replacement")


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    (
        ("last_calibration_projections", []),
        ("last_calibration_projections", {2330: _projection()}),
        ("last_screening_matrix", ({"stock_code": "2330"},)),
        ("last_exclusion_warnings_json", ["valid", 7]),
        ("last_run_context", []),
    ),
)
def test_snapshot_rejects_invalid_legacy_field_shapes(
    field_name: str,
    invalid_value: object,
) -> None:
    invocation, _, _ = _invocation()
    setattr(invocation, field_name, invalid_value)

    with pytest.raises((TypeError, ValueError)):
        _capture(invocation)
