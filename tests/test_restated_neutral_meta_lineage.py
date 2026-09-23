from __future__ import annotations

import pytest

from app_module.ml_allocation_inference_service import _validate_meta_fit_lineage
from ml_module.allocation_training_service import EXPERT_HEAD_IDS
from ml_module.allocation_v3_linear_release import (
    _ConstantProbabilityModel,
    _ConstantRegressionModel,
)


def _neutral_meta(*, fit_row_ids: list[str] | None = None) -> dict[str, object]:
    return {
        "numeric": {
            "target_weight_bp": _ConstantRegressionModel(0),
            "delta_weight_bp": _ConstantRegressionModel(0),
            "risk_contribution_bp": _ConstantRegressionModel(0),
            "risky_budget_bp": _ConstantRegressionModel(0),
            "cash_bp": _ConstantRegressionModel(10_000),
        },
        "rebalance": _ConstantProbabilityModel(0),
        "fit_row_ids": [] if fit_row_ids is None else fit_row_ids,
    }


def _audited_target_summary() -> dict[str, object]:
    return {
        "status": "verified_original_targets_constant_cash_only; neutral_meta_policy",
        "training_skipped": True,
        "model_learned_allocation": False,
        "neutral_meta_policy": (
            "fixed cash-only schema adapter; allocation heads remain research signals only"
        ),
        "target_values": {
            "target_weight_bp": 0,
            "delta_weight_bp": 0,
            "risk_contribution_bp": 0,
            "risky_budget_bp": 0,
            "cash_bp": 10_000,
            "rebalance": 0,
        },
    }


def test_meta_fit_lineage_keeps_normal_nonempty_contract() -> None:
    _validate_meta_fit_lineage(
        meta_models=_neutral_meta(fit_row_ids=["row:trained:1"]),
        target_summary=None,
        training_profile=None,
    )


def test_meta_fit_lineage_accepts_only_exact_audited_cash_only_constants() -> None:
    _validate_meta_fit_lineage(
        meta_models=_neutral_meta(),
        target_summary=_audited_target_summary(),
        training_profile="sealed_restated_linear_shadow_v1",
    )


def test_meta_fit_lineage_rejects_unmarked_empty_rows() -> None:
    with pytest.raises(ValueError, match="empty meta fit lineage"):
        _validate_meta_fit_lineage(
            meta_models=_neutral_meta(),
            target_summary=None,
            training_profile=None,
        )


@pytest.mark.parametrize(
    "invalid_policy", ["noncash", "rebalance", "wrong_profile", "lookalike"]
)
def test_meta_fit_lineage_rejects_marked_non_neutral_predictors(
    invalid_policy: str,
) -> None:
    meta = _neutral_meta()
    if invalid_policy == "noncash":
        meta["numeric"]["cash_bp"] = _ConstantRegressionModel(9_999)  # type: ignore[index]
    else:
        if invalid_policy == "rebalance":
            meta["rebalance"] = _ConstantProbabilityModel(1)
        elif invalid_policy == "lookalike":
            class CashLookalike:
                def __init__(self) -> None:
                    self.value = 10_000

            meta["numeric"]["cash_bp"] = CashLookalike()  # type: ignore[index]

    with pytest.raises(
        ValueError,
        match="empty meta fit lineage|exact audited cash-only|exact no-rebalance",
    ):
        _validate_meta_fit_lineage(
            meta_models=meta,
            target_summary=_audited_target_summary(),
            training_profile=(
                "other-profile"
                if invalid_policy == "wrong_profile"
                else "sealed_restated_linear_shadow_v1"
            ),
    )


def test_fit_row_commitment_parser_checks_all_frozen_heads() -> None:
    from app_module.ml_allocation_inference_service import (
        _parse_fit_row_lineage,
        _validate_fit_lineage_profile,
    )

    lineage = {
        "schema_version": "allocation-fit-row-commitments.v1",
        "mode": "sha256_row_id_commitments",
        "row_count": 2,
        "row_id_sha256": "sha256:" + "a" * 64,
        "heads": {
            head_id: {
                "row_count": 2,
                "row_id_sha256": "sha256:" + "b" * 64,
            }
            for head_id in EXPERT_HEAD_IDS
        },
    }
    assert _parse_fit_row_lineage(lineage, field_name="test") == lineage
    _validate_fit_lineage_profile(training_profile="sealed_restated_linear_shadow_v1")
    with pytest.raises(ValueError, match="requires the sealed restated research profile"):
        _validate_fit_lineage_profile(training_profile="legacy-profile")
    lineage["row_count"] = 1
    with pytest.raises(ValueError, match="row_count is invalid"):
        _parse_fit_row_lineage(lineage, field_name="test")
