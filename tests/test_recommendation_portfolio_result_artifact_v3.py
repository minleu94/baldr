"""V3 在保留原 V1/V2 文件的同時封存 producer execution inputs。"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from typing import Any, Callable

import pytest

from app_module.recommendation_portfolio_dtos import RecommendationPortfolioBacktestResultDTO
from app_module.recommendation_portfolio_execution_inputs_v1 import (
    RecommendationPortfolioExecutionInputsV1Error,
)
from app_module.recommendation_portfolio_result_artifact import (
    PortfolioResultArtifactCodecError,
    RecommendationPortfolioResultArtifactV1,
    encode_portfolio_result_artifact,
)
from app_module.recommendation_portfolio_result_artifact_v2 import (
    RecommendationPortfolioResultArtifactV2,
    encode_portfolio_result_artifact_v2,
)
from app_module.recommendation_portfolio_result_artifact_v3 import (
    PortfolioResultArtifactV3CodecError,
    RecommendationPortfolioResultArtifactV3,
    decode_portfolio_result_artifact_v3,
    encode_portfolio_result_artifact_v3,
)
from test_recommendation_portfolio_precision_registry_v2 import _metadata, _producer
from test_recommendation_portfolio_precision_capture import _history, _run_next_open


_EQUITY_HASH = "sha256:" + "1" * 64
_TRADES_HASH = "sha256:" + "2" * 64


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _sha256(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _serialize_v3(document: dict[str, Any], *, rehash: bool = True) -> bytes:
    if rehash:
        header = {key: value for key, value in document.items() if key != "payload_hash"}
        document["payload_hash"] = _sha256(_canonical_bytes(header))
    return _canonical_bytes(document)


def _encode(
    result: RecommendationPortfolioBacktestResultDTO,
) -> RecommendationPortfolioResultArtifactV3:
    execution_inputs = result.execution_input_capture
    assert execution_inputs is not None
    metadata = _metadata()
    parent_id = result.replay_parent_id
    assert parent_id is not None
    return encode_portfolio_result_artifact_v3(
        result,
        registry_run_id=metadata.run_id,
        portfolio_parent_id=parent_id,
        equity_parquet_sha256=_EQUITY_HASH,
        trades_parquet_sha256=_TRADES_HASH,
        metadata_strategy_id=metadata.strategy_id,
        metadata_strategy_version=metadata.strategy_version,
        execution_inputs=execution_inputs,
    )


def _result_with_parent(
    result: RecommendationPortfolioBacktestResultDTO, parent_id: str
) -> RecommendationPortfolioBacktestResultDTO:
    if result.replay_parent_id == parent_id:
        return result
    rebound = replace(result, snapshots=[replace(item) for item in result.snapshots])
    for snapshot in rebound.snapshots:
        snapshot.attach_replay_parent_id(parent_id)
    rebound.attach_replay_parent_id(parent_id)
    return rebound


def _encode_v2_variant(
    result,
    *,
    registry_run_id: str | None = None,
    portfolio_parent_id: str | None = None,
    equity_parquet_sha256: str | None = None,
    trades_parquet_sha256: str | None = None,
    metadata_strategy_id: str | None = None,
    metadata_strategy_version: str | None = None,
) -> RecommendationPortfolioResultArtifactV2:
    metadata = _metadata()
    parent_id = portfolio_parent_id or result.replay_parent_id
    assert parent_id is not None
    return encode_portfolio_result_artifact_v2(
        _result_with_parent(result, parent_id),
        registry_run_id=registry_run_id or metadata.run_id,
        portfolio_parent_id=parent_id,
        equity_parquet_sha256=equity_parquet_sha256 or _EQUITY_HASH,
        trades_parquet_sha256=trades_parquet_sha256 or _TRADES_HASH,
        metadata_strategy_id=(metadata.strategy_id if metadata_strategy_id is None else metadata_strategy_id),
        metadata_strategy_version=(metadata.strategy_version if metadata_strategy_version is None else metadata_strategy_version),
    )


def _wrap_v2_base(
    result: RecommendationPortfolioBacktestResultDTO,
    base: RecommendationPortfolioResultArtifactV2,
) -> bytes:
    document = json.loads(_encode(result).raw_payload.decode("utf-8"))
    document["payload"]["base_schema_version"] = base.schema_version
    document["payload"]["base_schema_revision"] = base.schema_revision
    document["payload"]["base_document"] = json.loads(base.raw_payload.decode("utf-8"))
    return _serialize_v3(document)


def _rewrite_inputs(
    raw_payload: bytes,
    mutate: Callable[[dict[str, Any]], None],
) -> bytes:
    document = json.loads(raw_payload.decode("utf-8"))
    inputs = document["payload"]["execution_inputs"]
    mutate(inputs)
    document["payload"]["execution_inputs_identity_sha256"] = _sha256(
        _canonical_bytes(inputs)
    )
    return _serialize_v3(document)


@pytest.mark.parametrize("named_cost", [False, True])
def test_v3_roundtrip_preserves_producer_inputs_and_exact_v2_base(named_cost: bool) -> None:
    result = _producer(named_cost=named_cost)
    artifact = _encode(result)
    decoded = decode_portfolio_result_artifact_v3(artifact.raw_payload)
    metadata = _metadata()
    parent_id = result.replay_parent_id
    assert parent_id is not None
    original_v2 = encode_portfolio_result_artifact_v2(
        result,
        registry_run_id=metadata.run_id,
        portfolio_parent_id=parent_id,
        equity_parquet_sha256=_EQUITY_HASH,
        trades_parquet_sha256=_TRADES_HASH,
        metadata_strategy_id=metadata.strategy_id,
        metadata_strategy_version=metadata.strategy_version,
    )

    assert decoded.raw_payload == artifact.raw_payload
    assert decoded.schema_version == "recommendation-portfolio-result.v3"
    assert decoded.schema_revision == 3
    assert type(decoded.base_artifact) is RecommendationPortfolioResultArtifactV2
    assert decoded.base_artifact.raw_payload == original_v2.raw_payload
    assert decoded.execution_inputs == result.execution_input_capture
    restored = decoded.materialize_result(
        equity_curve=result.equity_curve,
        trades=result.trades,
        expected_registry_run_id=metadata.run_id,
        expected_portfolio_parent_id=parent_id,
        equity_parquet_sha256=_EQUITY_HASH,
        trades_parquet_sha256=_TRADES_HASH,
    )
    assert restored.execution_input_capture == result.execution_input_capture
    assert restored.period_precision_capture == result.period_precision_capture
    if named_cost:
        precision = decoded.base_artifact.period_precision
        assert precision is not None
        assert precision.source_quality_status == "unknown"
        assert precision.currency_code is None and precision.currency_authority is None
        assert precision.expected_session_dates is None
        assert not precision.money_comparable
        assert not precision.performance_eligible
        assert not precision.historical_pit_eligible
        assert not precision.broker_eligible


def test_v3_roundtrip_preserves_multi_stock_producer_inputs_and_exact_v1_base() -> None:
    result = _run_next_open(_history(stock_codes=("2330", "2317")))
    assert result.execution_input_capture is not None
    assert result.period_precision_capture_status == "not_single_stock"
    assert result.period_precision_capture_reason == "history_contains_multiple_stock_codes"
    assert result.period_precision_observations == ()
    assert result.period_precision_capture is None

    artifact = _encode(result)
    decoded = decode_portfolio_result_artifact_v3(artifact.raw_payload)
    metadata = _metadata()
    parent_id = result.replay_parent_id
    assert parent_id is not None
    original_v1 = encode_portfolio_result_artifact(
        result,
        registry_run_id=metadata.run_id,
        portfolio_parent_id=parent_id,
        equity_parquet_sha256=_EQUITY_HASH,
        trades_parquet_sha256=_TRADES_HASH,
    )

    assert type(decoded.base_artifact) is RecommendationPortfolioResultArtifactV1
    assert decoded.base_artifact.raw_payload == original_v1.raw_payload
    restored = decoded.materialize_result(
        equity_curve=result.equity_curve,
        trades=result.trades,
        expected_registry_run_id=metadata.run_id,
        expected_portfolio_parent_id=parent_id,
        equity_parquet_sha256=_EQUITY_HASH,
        trades_parquet_sha256=_TRADES_HASH,
    )
    assert restored.execution_input_capture == result.execution_input_capture
    assert restored.period_precision_capture is None


def test_v3_keeps_missing_bps_distinct_from_explicit_zero() -> None:
    zero_result = _producer()
    missing_result = deepcopy(zero_result)
    original = missing_result.execution_input_capture
    assert original is not None and original.effective_bps == ("0", "0", "0")
    missing_result.execution_input_capture = replace(
        original, submitted_bps=(None, original.submitted_bps[1], original.submitted_bps[2])
    )
    credibility = missing_result.details["portfolio_credibility"]
    warnings = list(credibility["warnings"])
    if "unspecified_cost_assumptions" not in warnings:
        warnings.append("unspecified_cost_assumptions")
    credibility["warnings"] = warnings
    missing_result.summary["credibility_warning_count"] = len(warnings)

    zero_artifact = _encode(zero_result)
    missing_artifact = _encode(missing_result)
    assert zero_artifact.execution_inputs.submitted_bps == ("0", "0", "0")
    assert missing_artifact.execution_inputs.submitted_bps == (None, "0", "0")
    assert zero_artifact.execution_inputs.effective_bps == missing_artifact.execution_inputs.effective_bps
    assert (
        zero_artifact.execution_inputs.input_identity_sha256
        != missing_artifact.execution_inputs.input_identity_sha256
    )
    assert zero_artifact.raw_payload != missing_artifact.raw_payload


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("registry_run_id", "different-run"),
        ("portfolio_parent_id", "different-parent"),
        ("equity_parquet_sha256", "sha256:" + "3" * 64),
        ("trades_parquet_sha256", "sha256:" + "4" * 64),
    ],
)
def test_v3_rejects_outer_identity_separated_from_embedded_base(field: str, value: str) -> None:
    document = json.loads(_encode(_producer()).raw_payload.decode("utf-8"))
    document[field] = value
    with pytest.raises(PortfolioResultArtifactV3CodecError):
        decode_portfolio_result_artifact_v3(_serialize_v3(document))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("registry_run_id", "different-inner-run"),
        ("portfolio_parent_id", "different-inner-parent"),
        ("equity_parquet_sha256", "sha256:" + "5" * 64),
        ("trades_parquet_sha256", "sha256:" + "6" * 64),
    ],
)
def test_v3_rejects_tampered_inner_base_identity(field: str, value: str) -> None:
    result = _producer()
    if field == "registry_run_id":
        base = _encode_v2_variant(result, registry_run_id=value)
    elif field == "portfolio_parent_id":
        base = _encode_v2_variant(result, portfolio_parent_id=value)
    elif field == "equity_parquet_sha256":
        base = _encode_v2_variant(result, equity_parquet_sha256=value)
    else:
        assert field == "trades_parquet_sha256"
        base = _encode_v2_variant(result, trades_parquet_sha256=value)
    # 內嵌 V2 本身仍是有效文件；V3 必須拒絕它與外層不同的 identity。
    with pytest.raises(PortfolioResultArtifactV3CodecError):
        decode_portfolio_result_artifact_v3(_wrap_v2_base(result, base))


def test_v3_rejects_inner_strategy_identity_separated_from_v3_header() -> None:
    result = _producer()
    base = _encode_v2_variant(result, metadata_strategy_id="different-inner-strategy")
    with pytest.raises(PortfolioResultArtifactV3CodecError):
        decode_portfolio_result_artifact_v3(_wrap_v2_base(result, base))


def test_v3_rejects_strategy_and_input_contract_crossbind_mismatch() -> None:
    artifact = _encode(_producer())
    document = json.loads(artifact.raw_payload.decode("utf-8"))
    document["payload"]["metadata_strategy_id"] = "other-strategy"
    with pytest.raises(PortfolioResultArtifactV3CodecError):
        decode_portfolio_result_artifact_v3(_serialize_v3(document))

    bad_contract = _rewrite_inputs(
        artifact.raw_payload,
        lambda inputs: inputs.update(execution_contract="different-contract.v1"),
    )
    with pytest.raises(PortfolioResultArtifactV3CodecError):
        decode_portfolio_result_artifact_v3(bad_contract)


def test_v3_rejects_lot_policy_and_input_hash_mismatches() -> None:
    generic = _encode(_producer())
    bad_lot = _rewrite_inputs(
        generic.raw_payload,
        lambda inputs: inputs.update(submitted_lot_size=2, effective_lot_size=2),
    )
    with pytest.raises(PortfolioResultArtifactV3CodecError):
        decode_portfolio_result_artifact_v3(bad_lot)

    named = _encode(_producer(named_cost=True))

    def change_policy(inputs: dict[str, Any]) -> None:
        inputs["cost_policy_metadata"]["policy_id"] = "different-policy"

    bad_policy = _rewrite_inputs(named.raw_payload, change_policy)
    with pytest.raises(PortfolioResultArtifactV3CodecError):
        decode_portfolio_result_artifact_v3(bad_policy)

    document = json.loads(generic.raw_payload.decode("utf-8"))
    document["payload"]["execution_inputs_identity_sha256"] = "sha256:" + "0" * 64
    with pytest.raises(PortfolioResultArtifactV3CodecError):
        decode_portfolio_result_artifact_v3(_serialize_v3(document))


def test_v3_rejects_unknown_duplicate_noncanonical_and_oversized_documents() -> None:
    raw_payload = _encode(_producer()).raw_payload
    unknown = json.loads(raw_payload.decode("utf-8"))
    unknown["unrecognized"] = True
    with pytest.raises(PortfolioResultArtifactCodecError):
        decode_portfolio_result_artifact_v3(_serialize_v3(unknown))

    unknown_input = json.loads(raw_payload.decode("utf-8"))
    unknown_input["payload"]["execution_inputs"]["unrecognized"] = True
    unknown_input["payload"]["execution_inputs_identity_sha256"] = _sha256(
        _canonical_bytes(unknown_input["payload"]["execution_inputs"])
    )
    with pytest.raises(RecommendationPortfolioExecutionInputsV1Error):
        decode_portfolio_result_artifact_v3(_serialize_v3(unknown_input))

    duplicate = raw_payload.replace(
        b'"schema_revision":3',
        b'"schema_revision":3,"schema_revision":3',
        1,
    )
    with pytest.raises(PortfolioResultArtifactCodecError):
        decode_portfolio_result_artifact_v3(duplicate)
    with pytest.raises(PortfolioResultArtifactV3CodecError):
        decode_portfolio_result_artifact_v3(raw_payload + b" ")
    with pytest.raises(PortfolioResultArtifactV3CodecError):
        decode_portfolio_result_artifact_v3(b"x" * (16 * 1024**2 + 1))


def test_v3_does_not_downgrade_when_period_capture_is_removed() -> None:
    result = _producer()
    inputs = result.execution_input_capture
    assert inputs is not None and result.period_precision_observations
    result.period_precision_capture = None
    metadata = _metadata()
    parent_id = result.replay_parent_id
    assert parent_id is not None
    with pytest.raises(PortfolioResultArtifactV3CodecError):
        encode_portfolio_result_artifact_v3(
            result,
            registry_run_id=metadata.run_id,
            portfolio_parent_id=parent_id,
            equity_parquet_sha256=_EQUITY_HASH,
            trades_parquet_sha256=_TRADES_HASH,
            metadata_strategy_id=metadata.strategy_id,
            metadata_strategy_version=metadata.strategy_version,
            execution_inputs=inputs,
        )
