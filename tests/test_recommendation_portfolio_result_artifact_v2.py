"""Recommendation Portfolio V2 artifact 的 synthetic TEMP contract tests。"""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from decimal import Decimal
from typing import Any, Callable, Literal, cast

import pandas as pd
import pytest

from app_module.recommendation_portfolio_dtos import (
    RecommendationPortfolioBacktestResultDTO,
    RecommendationPortfolioPeriodPrecisionCaptureV2,
)
from app_module.recommendation_portfolio_period_precision_v2 import (
    RecommendationPortfolioPeriodObservationV2,
)
from app_module.recommendation_portfolio_result_artifact import (
    PortfolioResultArtifactCodecError,
    decode_portfolio_result_artifact,
    encode_portfolio_result_artifact,
)
from app_module.recommendation_portfolio_result_artifact_v2 import (
    PortfolioResultArtifactV2CodecError,
    RecommendationPortfolioResultArtifactV2,
    decode_portfolio_result_artifact_v2,
    encode_portfolio_result_artifact_v2,
)


_REGISTRY_RUN_ID = "registry-rp-v2-synthetic-01"
_PARENT_ID = "portfolio-parent-rp-v2-synthetic-01"
_STRATEGY_ID = "synthetic-strategy"
_STRATEGY_VERSION = "version-2026-10"
_EQUITY_BYTES = b"synthetic equity parquet"
_TRADES_BYTES = b"synthetic trades parquet"
_EQUITY_HASH = "sha256:" + hashlib.sha256(_EQUITY_BYTES).hexdigest()
_TRADES_HASH = "sha256:" + hashlib.sha256(_TRADES_BYTES).hexdigest()
_INITIAL = "9007199254740993.01"
_OBSERVATION_DATES = ("2026-10-01", "2026-10-02")


def _capture(
    *,
    cost_model_status: Literal["identified", "unknown"] = "identified",
) -> RecommendationPortfolioPeriodPrecisionCaptureV2:
    observations = (
        RecommendationPortfolioPeriodObservationV2(
            session_date=_OBSERVATION_DATES[0],
            stock_code="2330",
            cash_decimal=_INITIAL,
            position_value_decimal="0.00",
            equity_decimal=_INITIAL,
        ),
        RecommendationPortfolioPeriodObservationV2(
            session_date=_OBSERVATION_DATES[1],
            stock_code="2330",
            cash_decimal=_INITIAL,
            position_value_decimal="0.00",
            equity_decimal=_INITIAL,
        ),
    )
    if cost_model_status == "identified":
        cost_model_id = "synthetic-cost-policy"
        cost_model_version = "policy-v1"
    else:
        cost_model_id = None
        cost_model_version = None
    return RecommendationPortfolioPeriodPrecisionCaptureV2(
        stock_code="2330",
        stock_scope_status="exact_single_stock",
        capture_status="complete",
        initial_capital_decimal=_INITIAL,
        requested_start_date=_OBSERVATION_DATES[0],
        requested_end_date=_OBSERVATION_DATES[1],
        observed_session_dates=_OBSERVATION_DATES,
        completion_status="completed",
        execution_contract_id="next-session-open",
        execution_contract_version="v2",
        cost_model_status=cost_model_status,
        cost_model_id=cost_model_id,
        cost_model_version=cost_model_version,
        observations=observations,
    )


def _partial_capture() -> RecommendationPortfolioPeriodPrecisionCaptureV2:
    complete = _capture()
    observations = complete.observations[:1]
    return RecommendationPortfolioPeriodPrecisionCaptureV2(
        stock_code=complete.stock_code,
        stock_scope_status=complete.stock_scope_status,
        capture_status="partial",
        initial_capital_decimal=complete.initial_capital_decimal,
        requested_start_date=complete.requested_start_date,
        requested_end_date=complete.requested_end_date,
        observed_session_dates=tuple(row.session_date for row in observations),
        completion_status="cancelled",
        execution_contract_id=complete.execution_contract_id,
        execution_contract_version=complete.execution_contract_version,
        cost_model_status=complete.cost_model_status,
        cost_model_id=complete.cost_model_id,
        cost_model_version=complete.cost_model_version,
        observations=observations,
    )


def _result(
    *,
    capture: RecommendationPortfolioPeriodPrecisionCaptureV2 | None = None,
) -> RecommendationPortfolioBacktestResultDTO:
    typed_capture = _capture() if capture is None else capture
    is_complete = typed_capture.capture_status == "complete"
    result = RecommendationPortfolioBacktestResultDTO(
        summary={
            "status": "completed" if is_complete else "cancelled",
            "total_return": Decimal("0.00"),
        },
        equity_curve=pd.DataFrame(
            [{"date": _OBSERVATION_DATES[0], "equity": Decimal(_INITIAL)}]
        ),
        trades=pd.DataFrame(),
        snapshots=[],
        period_holdings=[],
        stock_contribution=[],
        details={"fixture_kind": "synthetic-contract-only"},
        period_precision_observations=typed_capture.observations,
        period_precision_capture_status=(
            "captured_unqualified" if is_complete else "partial"
        ),
        period_precision_capture_reason=(
            "decimal_observations_only; no source_currency_calendar_or_cost_qualification"
            if is_complete
            else "cancelled_before_all_sessions"
        ),
        period_precision_capture=typed_capture,
    )
    result.attach_replay_parent_id(_PARENT_ID)
    return result


def _encode(
    *,
    result: RecommendationPortfolioBacktestResultDTO | None = None,
    metadata_strategy_id: str | None = _STRATEGY_ID,
    metadata_strategy_version: str | None = _STRATEGY_VERSION,
) -> RecommendationPortfolioResultArtifactV2:
    return encode_portfolio_result_artifact_v2(
        _result() if result is None else result,
        registry_run_id=_REGISTRY_RUN_ID,
        portfolio_parent_id=_PARENT_ID,
        equity_parquet_sha256=_EQUITY_HASH,
        trades_parquet_sha256=_TRADES_HASH,
        metadata_strategy_id=metadata_strategy_id,
        metadata_strategy_version=metadata_strategy_version,
    )


def _materialize(
    artifact: RecommendationPortfolioResultArtifactV2,
) -> RecommendationPortfolioBacktestResultDTO:
    equity_curve = pd.DataFrame()
    trades = pd.DataFrame()
    return artifact.materialize_result(
        equity_curve=equity_curve,
        trades=trades,
        expected_registry_run_id=_REGISTRY_RUN_ID,
        expected_portfolio_parent_id=_PARENT_ID,
        equity_parquet_sha256=_EQUITY_HASH,
        trades_parquet_sha256=_TRADES_HASH,
    )


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _rewrite_document(
    raw_payload: bytes,
    mutate: Callable[[dict[str, Any]], None],
    *,
    rehash_header: bool = True,
) -> bytes:
    document = cast(dict[str, Any], json.loads(raw_payload.decode("utf-8")))
    mutate(document)
    if rehash_header:
        header = {key: value for key, value in document.items() if key != "payload_hash"}
        document["payload_hash"] = "sha256:" + hashlib.sha256(
            _canonical_bytes(header)
        ).hexdigest()
    return _canonical_bytes(document)


def test_v2_roundtrip_preserves_capture_v1_document_and_unqualified_precision() -> None:
    artifact = _encode()
    decoded = decode_portfolio_result_artifact_v2(artifact.raw_payload)

    assert decoded.raw_payload == artifact.raw_payload
    assert decoded.registry_run_id == _REGISTRY_RUN_ID
    assert decoded.portfolio_parent_id == _PARENT_ID
    assert decoded.equity_parquet_sha256 == _EQUITY_HASH
    assert decoded.trades_parquet_sha256 == _TRADES_HASH
    assert decoded.payload_hash == artifact.payload_hash
    assert decoded.canonical_payload_hash == artifact.payload_hash
    assert decoded.raw_payload_sha256 == artifact.raw_payload_sha256
    assert decoded.schema_version == "recommendation-portfolio-result.v2"
    assert decoded.schema_revision == 2
    assert decoded.period_precision_capture == _capture()
    assert decoded.period_precision_capture_status == "captured_unqualified"
    assert decoded.metadata_strategy_id == _STRATEGY_ID
    assert decoded.metadata_strategy_version == _STRATEGY_VERSION
    assert decoded.period_precision_capture_reason == (
        "decimal_observations_only; no source_currency_calendar_or_cost_qualification"
    )
    assert decoded.missing_precision_identity == ()

    precision = decoded.period_precision
    assert precision is not None
    assert precision.initial_capital_decimal == _INITIAL
    assert precision.actual_session_dates == _OBSERVATION_DATES
    assert precision.currency_code is None
    assert precision.minor_unit_exponent is None
    assert precision.currency_authority is None
    assert precision.source_fingerprint_sha256 is None
    assert precision.source_manifest_sha256 is None
    assert precision.source_raw_sha256 is None
    assert precision.equity_parquet_sha256 == _EQUITY_HASH
    assert precision.trades_parquet_sha256 == _TRADES_HASH
    assert precision.source_cutoff_at is None
    assert precision.source_available_at is None
    assert precision.source_availability_basis is None
    assert precision.source_quality_status == "unknown"
    assert precision.session_calendar_id is None
    assert precision.session_calendar_version is None
    assert precision.session_calendar_sha256 is None
    assert precision.expected_session_dates is None
    assert precision.coverage_status == "unknown"
    assert precision.execution_contract_sha256 is None
    assert precision.cost_model_sha256 is None
    assert precision.money_comparable is False
    assert precision.historical_pit_eligible is False
    assert precision.performance_eligible is False
    assert precision.broker_eligible is False

    restored = _materialize(decoded)
    assert restored.period_precision_capture == decoded.period_precision_capture
    assert restored.period_precision_observations == decoded.period_precision_capture.observations
    assert restored.period_precision_capture_status == "captured_unqualified"
    assert restored.period_precision_capture_reason == decoded.period_precision_capture_reason
    assert restored.replay_parent_id == _PARENT_ID
    assert not hasattr(restored, "period_precision_artifact")


def test_v1_codec_rejects_v2_envelope_without_changing_v1_dispatch() -> None:
    v2_artifact = _encode()
    v1_artifact = encode_portfolio_result_artifact(
        _result(),
        registry_run_id=_REGISTRY_RUN_ID,
        portfolio_parent_id=_PARENT_ID,
        equity_parquet_sha256=_EQUITY_HASH,
        trades_parquet_sha256=_TRADES_HASH,
    )

    with pytest.raises(PortfolioResultArtifactCodecError):
        decode_portfolio_result_artifact(v2_artifact.raw_payload)

    assert b"period_precision_capture" not in v1_artifact.raw_payload
    with pytest.raises(PortfolioResultArtifactV2CodecError):
        decode_portfolio_result_artifact_v2(v1_artifact.raw_payload)


def test_v2_encode_requires_typed_capture_descriptor() -> None:
    result = _result()
    result.period_precision_capture = None

    with pytest.raises(PortfolioResultArtifactV2CodecError):
        _encode(result=result)


def test_v2_materialize_preserves_original_partial_status_and_reason() -> None:
    capture = _partial_capture()
    artifact = _encode(result=_result(capture=capture))
    decoded = decode_portfolio_result_artifact_v2(artifact.raw_payload)
    restored = _materialize(decoded)

    assert decoded.period_precision_capture == capture
    assert decoded.period_precision_capture_status == "partial"
    assert decoded.period_precision_capture_reason == "cancelled_before_all_sessions"
    assert restored.period_precision_capture_status == "partial"
    assert restored.period_precision_capture_reason == "cancelled_before_all_sessions"
    assert restored.period_precision_observations == capture.observations
    assert decoded.period_precision is not None
    assert decoded.period_precision.completion_status == "cancelled"
    assert decoded.period_precision.expected_session_dates is None
    assert decoded.period_precision.money_comparable is False


def test_v2_encode_rejects_result_status_or_observations_not_matching_capture() -> None:
    wrong_status = _result()
    wrong_status.period_precision_capture_status = "partial"
    with pytest.raises(PortfolioResultArtifactV2CodecError):
        _encode(result=wrong_status)

    wrong_observations = _result()
    wrong_observations.period_precision_observations = ()
    with pytest.raises(PortfolioResultArtifactV2CodecError):
        _encode(result=wrong_observations)


@pytest.mark.parametrize(
    ("metadata_strategy_id", "metadata_strategy_version", "cost_known", "missing"),
    [
        (None, _STRATEGY_VERSION, True, ("metadata_strategy_id",)),
        (_STRATEGY_ID, None, True, ("metadata_strategy_version",)),
        (None, None, False, (
            "metadata_strategy_id",
            "metadata_strategy_version",
            "cost_model_id",
            "cost_model_version",
        )),
    ],
)
def test_missing_precision_identity_keeps_typed_capture_without_placeholder_ids(
    metadata_strategy_id: str | None,
    metadata_strategy_version: str | None,
    cost_known: bool,
    missing: tuple[str, ...],
) -> None:
    capture = _capture(
        cost_model_status="identified" if cost_known else "unknown"
    )
    artifact = _encode(
        result=_result(capture=capture),
        metadata_strategy_id=metadata_strategy_id,
        metadata_strategy_version=metadata_strategy_version,
    )
    decoded = decode_portfolio_result_artifact_v2(artifact.raw_payload)

    assert decoded.period_precision is None
    assert decoded.missing_precision_identity == missing
    assert decoded.period_precision_capture == capture
    assert _materialize(decoded).period_precision_capture == capture


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("registry_run_id", "different-registry-run"),
        (
            "equity_parquet_sha256",
            "sha256:" + "0" * 64,
        ),
        (
            "trades_parquet_sha256",
            "sha256:" + "1" * 64,
        ),
    ],
)
def test_v2_rejects_outer_identity_that_differs_from_nested_v1(
    field: str,
    replacement: str,
) -> None:
    artifact = _encode()
    raw = _rewrite_document(
        artifact.raw_payload,
        lambda document: document.__setitem__(field, replacement),
    )

    with pytest.raises(PortfolioResultArtifactV2CodecError):
        decode_portfolio_result_artifact_v2(raw)


@pytest.mark.parametrize("tamper", ["initial", "request_range", "row", "capture_status"])
def test_v2_rejects_capture_changes_inconsistent_with_typed_capture_or_precision(
    tamper: str,
) -> None:
    artifact = _encode()

    def mutate(document: dict[str, Any]) -> None:
        payload = cast(dict[str, Any], document["payload"])
        capture = cast(dict[str, Any], payload["period_precision_capture"])
        if tamper == "initial":
            capture["initial_capital_decimal"] = "9007199254740994.01"
        elif tamper == "request_range":
            capture["requested_end_date"] = "2026-10-01"
        elif tamper == "row":
            rows = cast(list[dict[str, Any]], capture["observations"])
            rows[0]["cash_decimal"] = "1.00"
        else:
            capture["capture_status"] = "partial"

    raw = _rewrite_document(artifact.raw_payload, mutate)
    with pytest.raises(PortfolioResultArtifactV2CodecError):
        decode_portfolio_result_artifact_v2(raw)


def test_v2_rejects_self_recomputed_precision_that_disagrees_with_capture() -> None:
    artifact = _encode()
    precision = artifact.period_precision
    assert precision is not None
    bad_precision = replace(
        precision,
        currency_code="TWD",
        minor_unit_exponent=2,
    )
    bad_precision_document = json.loads(bad_precision.to_json())

    def mutate(document: dict[str, Any]) -> None:
        payload = cast(dict[str, Any], document["payload"])
        payload["period_precision"] = bad_precision_document

    raw = _rewrite_document(artifact.raw_payload, mutate)
    with pytest.raises(PortfolioResultArtifactV2CodecError):
        decode_portfolio_result_artifact_v2(raw)


def test_v2_rejects_float_observation_and_unknown_envelope_or_payload_keys() -> None:
    artifact = _encode()

    def add_outer_key(document: dict[str, Any]) -> None:
        document["unrecognized"] = "extra"

    def add_payload_key(document: dict[str, Any]) -> None:
        payload = cast(dict[str, Any], document["payload"])
        payload["unrecognized"] = "extra"

    def replace_decimal_with_float(document: dict[str, Any]) -> None:
        payload = cast(dict[str, Any], document["payload"])
        capture = cast(dict[str, Any], payload["period_precision_capture"])
        rows = cast(list[dict[str, Any]], capture["observations"])
        rows[0]["cash_decimal"] = float(_INITIAL)

    for mutate in (add_outer_key, add_payload_key, replace_decimal_with_float):
        with pytest.raises(PortfolioResultArtifactV2CodecError):
            decode_portfolio_result_artifact_v2(
                _rewrite_document(artifact.raw_payload, mutate)
            )


def test_v2_rejects_duplicate_keys_noncanonical_bytes_and_raw_over_budget() -> None:
    artifact = _encode()
    duplicate = artifact.raw_payload.replace(
        b'"schema_version":"recommendation-portfolio-result.v2",',
        b'"schema_version":"recommendation-portfolio-result.v2",'
        b'"schema_version":"recommendation-portfolio-result.v2",',
        1,
    )
    with pytest.raises(PortfolioResultArtifactV2CodecError):
        decode_portfolio_result_artifact_v2(duplicate)

    noncanonical = artifact.raw_payload.replace(b",", b", ", 1)
    with pytest.raises(PortfolioResultArtifactV2CodecError):
        decode_portfolio_result_artifact_v2(noncanonical)

    over_budget = b" " * (16 * 1024 * 1024 + 1)
    with pytest.raises(PortfolioResultArtifactV2CodecError):
        decode_portfolio_result_artifact_v2(over_budget)


def test_v2_decoder_does_not_accept_empty_strategy_identity_strings() -> None:
    artifact = _encode()

    def empty_strategy_id(document: dict[str, Any]) -> None:
        payload = cast(dict[str, Any], document["payload"])
        payload["metadata_strategy_id"] = ""

    with pytest.raises(PortfolioResultArtifactV2CodecError):
        decode_portfolio_result_artifact_v2(
            _rewrite_document(artifact.raw_payload, empty_strategy_id)
        )
