from __future__ import annotations

import pytest

from app_module.ml_allocation_inference_service import _validate_meta_fit_lineage
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


def test_meta_fit_lineage_rejects_unmarked_empty_rows() -> None:
    with pytest.raises(ValueError, match="empty meta fit lineage"):
        _validate_meta_fit_lineage(
            meta_models=_neutral_meta(),
            target_summary=None,
            training_profile=None,
        )


@pytest.mark.parametrize("invalid_policy", ["noncash", "rebalance"])
def test_meta_fit_lineage_rejects_marked_non_neutral_predictors(
    invalid_policy: str,
) -> None:
    meta = _neutral_meta()
    if invalid_policy == "noncash":
        meta["numeric"]["cash_bp"] = _ConstantRegressionModel(9_999)  # type: ignore[index]
    else:
        meta["rebalance"] = _ConstantProbabilityModel(1)

    with pytest.raises(ValueError, match="exact audited cash-only|exact no-rebalance"):
        _validate_meta_fit_lineage(
            meta_models=meta,
            target_summary=_audited_target_summary(),
            training_profile="sealed_restated_linear_shadow_v1",
        )
