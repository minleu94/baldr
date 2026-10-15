from __future__ import annotations

from decimal import Decimal
import json
from typing import cast

import pytest

from app_module.recommendation_portfolio_execution_inputs_v1 import (
    EXECUTION_INPUTS_SCHEMA_V1,
    RecommendationPortfolioExecutionInputsV1,
    RecommendationPortfolioExecutionInputsV1Error,
)
from test_recommendation_portfolio_precision_capture import (
    _DATES,
    _history,
    _run_next_open,
)
from test_recommendation_portfolio_precision_registry_v2 import _producer


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _capture(
    *,
    fee_bps: object = None,
    slippage_bps: object = Decimal("0"),
    tax_bps: object = Decimal("0"),
    submitted_lot_size: int | None = 1,
    effective_lot_size: int = 1,
    cost_policy_metadata: dict[str, object] | None = None,
) -> RecommendationPortfolioExecutionInputsV1:
    return RecommendationPortfolioExecutionInputsV1.capture(
        execution_contract="next-session-open.v2",
        fee_bps=fee_bps,
        slippage_bps=slippage_bps,
        tax_bps=tax_bps,
        submitted_lot_size=submitted_lot_size,
        effective_lot_size=effective_lot_size,
        cost_policy_metadata=cost_policy_metadata,
    )


def test_none_and_explicit_zero_keep_submitted_values_but_share_effective_bps() -> None:
    unspecified = _capture(fee_bps=None)
    explicit_zero = _capture(fee_bps=Decimal("0"))

    assert unspecified.submitted_bps == (None, "0", "0")
    assert explicit_zero.submitted_bps == ("0", "0", "0")
    assert unspecified.effective_bps == explicit_zero.effective_bps == ("0", "0", "0")
    assert unspecified.input_identity_sha256 != explicit_zero.input_identity_sha256


def test_codec_roundtrips_canonical_input_identity_without_granting_authority() -> None:
    capture = _capture(fee_bps=None)
    encoded = capture.to_json()
    restored = RecommendationPortfolioExecutionInputsV1.from_json(encoded)

    assert json.loads(encoded)["schema_version"] == EXECUTION_INPUTS_SCHEMA_V1
    assert _canonical_json(json.loads(encoded)) == encoded
    assert restored == capture
    assert restored.to_json() == encoded
    assert restored.input_identity_sha256 == capture.input_identity_sha256
    # 此 hash 僅是輸入內容身份，不是撮合或成本模型 authority。
    assert not hasattr(capture, "execution_contract_sha256")
    assert not hasattr(capture, "cost_model_sha256")


def test_codec_rejects_unknown_fields_duplicate_keys_and_wrong_effective_values() -> None:
    capture = _capture(fee_bps=None)
    unknown = json.loads(capture.to_json())
    unknown["future_field"] = "not-supported"
    with pytest.raises(
        RecommendationPortfolioExecutionInputsV1Error,
        match="execution_inputs_fields_or_schema_invalid",
    ):
        RecommendationPortfolioExecutionInputsV1.from_json(_canonical_json(unknown))

    with pytest.raises(RecommendationPortfolioExecutionInputsV1Error):
        RecommendationPortfolioExecutionInputsV1.from_json(
            '{"schema_version":"first","schema_version":"second"}'
        )

    wrong_effective = json.loads(capture.to_json())
    wrong_effective["effective_bps"] = ["1", "0", "0"]
    with pytest.raises(
        RecommendationPortfolioExecutionInputsV1Error,
        match="execution_inputs_effective_bps_mismatch",
    ):
        RecommendationPortfolioExecutionInputsV1.from_json(_canonical_json(wrong_effective))

    wrong_lot = json.loads(capture.to_json())
    wrong_lot["effective_lot_size"] = 2
    with pytest.raises(
        RecommendationPortfolioExecutionInputsV1Error,
        match="execution_inputs_effective_lot_mismatch",
    ):
        RecommendationPortfolioExecutionInputsV1.from_json(_canonical_json(wrong_lot))


@pytest.mark.parametrize("raw", ['{"value":NaN}', '{"value":1.0}'])
def test_codec_rejects_nonfinite_constants_and_json_float_numbers(raw: str) -> None:
    with pytest.raises(RecommendationPortfolioExecutionInputsV1Error):
        RecommendationPortfolioExecutionInputsV1.from_json(raw)


def test_codec_rejects_over_budget_input_before_parsing() -> None:
    with pytest.raises(
        RecommendationPortfolioExecutionInputsV1Error,
        match="execution_inputs_byte_limit",
    ):
        RecommendationPortfolioExecutionInputsV1.from_json(" " * (32 * 1024 + 1))


@pytest.mark.parametrize("value", [Decimal("NaN"), Decimal("Infinity")])
def test_capture_rejects_nonfinite_submitted_bps(value: Decimal) -> None:
    with pytest.raises(RecommendationPortfolioExecutionInputsV1Error):
        _capture(fee_bps=value)


@pytest.mark.parametrize(
    ("submitted_lot_size", "effective_lot_size"),
    [(True, 1), (None, True)],
)
def test_capture_rejects_boolean_lot_sizes(
    submitted_lot_size: int | None,
    effective_lot_size: int,
) -> None:
    with pytest.raises(
        RecommendationPortfolioExecutionInputsV1Error,
        match="execution_inputs_lot_invalid",
    ):
        _capture(
            submitted_lot_size=submitted_lot_size,
            effective_lot_size=effective_lot_size,
        )


def test_policy_metadata_is_snapshotted_and_returned_as_a_deep_copy() -> None:
    metadata: dict[str, object] = {
        "policy_id": "policy-fixture",
        "policy_version": "fixture-v1",
        "lot_type": "full_lot",
        "instrument_type": "ordinary_stock",
        "full_lot_size_shares": 1000,
        "nested": {"labels": ["original"]},
    }
    capture = _capture(
        fee_bps=Decimal("0"),
        submitted_lot_size=1000,
        effective_lot_size=1000,
        cost_policy_metadata=metadata,
    )
    source_nested = cast(dict[str, object], metadata["nested"])
    cast(list[str], source_nested["labels"]).append("mutated-source")
    first_read = cast(dict[str, object], capture.to_dict()["cost_policy_metadata"])
    read_nested = cast(dict[str, object], first_read["nested"])
    cast(list[str], read_nested["labels"]).append("mutated-read")

    assert capture.cost_route == "banktaiwan_policy"
    assert capture.submitted_bps == ("0", "0", "0")
    assert capture.effective_bps is None
    remaining = cast(dict[str, object], capture.to_dict()["cost_policy_metadata"])
    assert remaining["nested"] == {"labels": ["original"]}


def test_policy_capture_rejects_effective_lot_conflicting_with_policy_metadata() -> None:
    metadata: dict[str, object] = {
        "policy_id": "policy-fixture",
        "policy_version": "fixture-v1",
        "lot_type": "full_lot",
        "instrument_type": "ordinary_stock",
        "full_lot_size_shares": 1000,
    }
    with pytest.raises(RecommendationPortfolioExecutionInputsV1Error):
        _capture(
            fee_bps=Decimal("0"),
            submitted_lot_size=999,
            effective_lot_size=999,
            cost_policy_metadata=metadata,
        )


def test_real_producer_capture_preserves_execution_inputs_without_changing_v1_wire() -> None:
    result = _run_next_open(_history(dates=_DATES[:2]))
    capture = result.execution_input_capture

    assert capture is not None
    assert capture.execution_contract == "next-session-open.v2"
    assert capture.cost_route == "configured_bps"
    assert capture.submitted_bps == ("0", "0", "0")
    assert capture.effective_bps == ("0", "0", "0")
    assert capture.submitted_lot_size == capture.effective_lot_size == 1

    legacy_wire = result.to_dict()
    assert "execution_input_capture" not in legacy_wire
    restored = type(result).from_dict(legacy_wire)
    assert restored.execution_input_capture is None


def test_real_policy_producer_capture_keeps_normalized_policy_inputs() -> None:
    result = _producer(named_cost=True)
    capture = result.execution_input_capture

    assert capture is not None
    assert capture.execution_contract == "next-session-open.v2"
    assert capture.cost_route == "banktaiwan_policy"
    assert capture.submitted_bps == ("0", "0", "0")
    assert capture.effective_bps is None
    metadata = cast(dict[str, object], capture.to_dict()["cost_policy_metadata"])
    assert metadata == result.details["execution_cost_policy"]
    assert metadata["lot_type"] == "full_lot"
    assert metadata["instrument_type"] == "ordinary_stock"
    assert metadata["full_lot_size_shares"] == capture.effective_lot_size == 1000
    assert capture.submitted_lot_size == capture.effective_lot_size
