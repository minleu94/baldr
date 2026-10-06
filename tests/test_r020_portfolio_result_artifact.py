"""R020 portfolio-result sidecar codec 的 synthetic TEMP contract tests。"""

from __future__ import annotations

import hashlib
import json
import struct
from datetime import date
from decimal import Decimal
from typing import Any, Callable

import numpy as np
import pandas as pd
import pytest

from app_module.recommendation_portfolio_dtos import (
    PeriodHoldingDTO,
    RecommendationPortfolioBacktestResultDTO,
    RecommendationSnapshotDTO,
    StockContributionDTO,
)
from app_module.recommendation_portfolio_result_artifact import (
    PortfolioResultArtifactCodecError,
    RecommendationPortfolioResultArtifactV1,
    decode_portfolio_result_artifact,
    encode_portfolio_result_artifact,
)


_REGISTRY_RUN_ID = "registry-r020-synthetic-01"
_PARENT_ID = "portfolio-parent-r020-synthetic-01"
_EQUITY_BYTES = b"equity parquet synthetic bytes"
_TRADES_BYTES = b"trades parquet synthetic bytes"
_EQUITY_HASH = "sha256:" + hashlib.sha256(_EQUITY_BYTES).hexdigest()
_TRADES_HASH = "sha256:" + hashlib.sha256(_TRADES_BYTES).hexdigest()


def _snapshot(as_of_date: str, codes: tuple[str, ...]) -> RecommendationSnapshotDTO:
    snapshot = RecommendationSnapshotDTO(
        as_of_date=as_of_date,
        profile_id="synthetic-momentum",
        strategy_config={
            "signals": {"technical": Decimal("0.5000"), "pattern": np.float32(0.25)},
            "window": np.int64(20),
            "date_fact": date(2026, 9, 22),
            "none_fact": None,
            "pandas_na_fact": pd.NA,
            "pandas_nat_fact": pd.NaT,
        },
        regime="Trend",
        recommendations=[
            {
                "stock_code": code,
                "stock_name": f"TEMP {code}",
                "total_score": np.float64(91.25 - index),
                "selection_reason": "synthetic order preserved",
                "nullable": None if index == 0 else pd.NA,
            }
            for index, code in enumerate(codes)
        ],
        diagnostics=["synthetic-diagnostic", "second-diagnostic"],
    )
    snapshot.attach_replay_parent_id(_PARENT_ID)
    return snapshot


def _result(
    *,
    snapshots: list[RecommendationSnapshotDTO] | None = None,
) -> RecommendationPortfolioBacktestResultDTO:
    result = RecommendationPortfolioBacktestResultDTO(
        summary={
            "total_return": Decimal("0.123400"),
            "max_drawdown": -0.0,
            "large_integer": 2**80 + 3,
            "date_fact": date(2026, 9, 24),
            "none_fact": None,
            "nan_fact": float("nan"),
            "decimal_nan_fact": Decimal("-NaN123"),
            "numpy_int": np.int64(2**53 + 1),
        },
        equity_curve=pd.DataFrame(
            [{"date": "2026-09-22", "equity": Decimal("1000000.00")}]
        ),
        trades=pd.DataFrame(
            [{"date": "2026-09-22", "stock_code": "2330", "shares": np.int64(10)}]
        ),
        snapshots=(
            [_snapshot("2026-09-22", ("2330", "2317"))]
            if snapshots is None
            else snapshots
        ),
        period_holdings=[
            PeriodHoldingDTO(
                rebalance_date="2026-09-22",
                stock_code="2330",
                stock_name="TEMP 2330",
                rank=1,
                total_score=91.25,
                factor_scores={"technical": np.float32(0.8125)},
                allocation_amount=Decimal("250000.00"),
                allocation_weight=0.25,
                entry_date="2026-09-22",
                entry_price=101.5,
                planned_exit_date="2026-09-23",
                actual_exit_date="2026-09-23",
                actual_exit_price=102.0,
                exit_reason="holding_period",
                holding_days=1,
                return_pct=Decimal("0.004926108374384236453201970443"),
                shares=100,
                actual_allocation_weight=None,
                execution_contract="synthetic-contract.v1",
                position_status="closed",
                exit_signal_date="2026-09-22",
                pnl_cents=None,
            )
        ],
        stock_contribution=[
            StockContributionDTO(
                stock_code="2330",
                stock_name="TEMP 2330",
                selected_count=1,
                total_pnl=Decimal("1234.50"),
                avg_return_pct=0.0049,
                win_rate=1.0,
                worst_return_pct=0.0049,
            )
        ],
        selection_diagnostics=["selection-a", "selection-b"],
        improvement_hints=["TEMP hint one", "TEMP hint two"],
        details={
            "cash_ledger": [
                {
                    "date": date(2026, 9, 22),
                    "opening_cash": Decimal("1000000.00"),
                    "closing_cash": None,
                    "missing": pd.NA,
                }
            ],
            "weight_exposure": {
                "codes": ("2330", "2317"),
                "nan": np.float32(float("nan")),
                "infinity": np.float64(float("inf")),
            },
        },
    )
    result.attach_replay_parent_id(_PARENT_ID)
    return result


def _encode(
    result: RecommendationPortfolioBacktestResultDTO | None = None,
) -> RecommendationPortfolioResultArtifactV1:
    return encode_portfolio_result_artifact(
        _result() if result is None else result,
        registry_run_id=_REGISTRY_RUN_ID,
        portfolio_parent_id=_PARENT_ID,
        equity_parquet_sha256=_EQUITY_HASH,
        trades_parquet_sha256=_TRADES_HASH,
    )


def _materialize(
    artifact: RecommendationPortfolioResultArtifactV1,
    *,
    equity_curve: pd.DataFrame | None = None,
    trades: pd.DataFrame | None = None,
) -> RecommendationPortfolioBacktestResultDTO:
    return artifact.materialize_result(
        equity_curve=pd.DataFrame() if equity_curve is None else equity_curve,
        trades=pd.DataFrame() if trades is None else trades,
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
    rehash_header: bool,
) -> bytes:
    document = json.loads(raw_payload.decode("utf-8"))
    mutate(document)
    if rehash_header:
        header = {key: value for key, value in document.items() if key != "payload_hash"}
        document["payload_hash"] = "sha256:" + hashlib.sha256(
            _canonical_bytes(header)
        ).hexdigest()
    return _canonical_bytes(document)


def test_sidecar_roundtrip_preserves_full_non_parquet_fields_and_types() -> None:
    result = _result()
    artifact = _encode(result)
    decoded = decode_portfolio_result_artifact(artifact.raw_payload)
    equity = pd.DataFrame(
        [{"date": "2026-09-22", "equity": Decimal("1000000.00")}]
    )
    trades = pd.DataFrame(
        [{"date": "2026-09-22", "stock_code": "2330", "shares": np.int64(10)}]
    )
    restored = _materialize(decoded, equity_curve=equity, trades=trades)

    assert decoded.raw_payload == artifact.raw_payload
    assert decoded.payload_hash == artifact.payload_hash
    assert decoded.canonical_payload_hash == artifact.payload_hash
    assert decoded.raw_payload_sha256 == artifact.raw_payload_sha256
    assert decoded.schema_revision == 1
    assert restored.equity_curve is equity
    assert restored.trades is trades
    assert restored.replay_parent_id == _PARENT_ID
    assert restored.snapshots[0].replay_parent_id == _PARENT_ID
    assert [row["stock_code"] for row in restored.snapshots[0].recommendations] == [
        "2330",
        "2317",
    ]
    assert list(restored.snapshots[0].recommendations[0]) == list(
        result.snapshots[0].recommendations[0]
    )
    assert type(restored.snapshots[0].recommendations[0]["total_score"]) is np.float64
    assert restored.summary["total_return"].as_tuple() == Decimal("0.123400").as_tuple()
    assert type(restored.summary["numpy_int"]) is np.int64
    assert restored.summary["numpy_int"] == 2**53 + 1
    assert type(restored.summary["large_integer"]) is int
    assert restored.summary["large_integer"] == 2**80 + 3
    assert struct.pack(">d", restored.summary["max_drawdown"]) == struct.pack(">d", -0.0)
    assert np.isnan(restored.summary["nan_fact"])
    assert restored.summary["decimal_nan_fact"].as_tuple() == Decimal(
        "-NaN123"
    ).as_tuple()
    assert restored.snapshots[0].strategy_config["pandas_nat_fact"] is pd.NaT
    assert type(restored.details["weight_exposure"]["nan"]) is np.float32
    assert np.isnan(restored.details["weight_exposure"]["nan"])
    assert restored.details["cash_ledger"][0]["date"] == date(2026, 9, 22)
    assert type(restored.details["cash_ledger"][0]["date"]) is date
    assert restored.details["cash_ledger"][0]["missing"] is pd.NA
    assert restored.details["cash_ledger"][0]["closing_cash"] is None
    assert restored.details["weight_exposure"]["codes"] == ("2330", "2317")
    assert type(restored.period_holdings[0].return_pct) is Decimal
    assert restored.period_holdings[0].return_pct.as_tuple() == result.period_holdings[
        0
    ].return_pct.as_tuple()
    assert type(restored.period_holdings[0].factor_scores["technical"]) is np.float32
    assert restored.stock_contribution[0].total_pnl.as_tuple() == Decimal(
        "1234.50"
    ).as_tuple()
    assert restored.selection_diagnostics == result.selection_diagnostics
    assert restored.improvement_hints == result.improvement_hints


def test_encoding_is_deterministic_and_keeps_multi_snapshot_and_v1_row_order() -> None:
    snapshots = [
        _snapshot("2026-09-23", ("2317", "2330")),
        _snapshot("2026-09-22", ("2454", "2308")),
    ]
    result = _result(snapshots=snapshots)

    first = _encode(result)
    second = _encode(result)
    restored = _materialize(decode_portfolio_result_artifact(first.raw_payload))

    assert first.raw_payload == second.raw_payload
    assert first.payload_hash == second.payload_hash
    assert first.raw_payload_sha256 == second.raw_payload_sha256
    assert [item.as_of_date for item in restored.snapshots] == [
        "2026-09-23",
        "2026-09-22",
    ]
    assert [row["stock_code"] for row in restored.snapshots[0].recommendations] == [
        "2317",
        "2330",
    ]
    assert [row["stock_code"] for row in restored.snapshots[1].recommendations] == [
        "2454",
        "2308",
    ]


def test_empty_portfolio_roundtrip_keeps_empty_rows_and_external_frame_columns() -> None:
    result = _result(snapshots=[])
    result.period_holdings = []
    result.stock_contribution = []
    result.selection_diagnostics = []
    result.improvement_hints = []
    result.details = {"cash_ledger": []}
    artifact = _encode(result)
    equity = pd.DataFrame(columns=["date", "equity"])
    trades = pd.DataFrame(columns=["date", "stock_code", "shares"])

    restored = _materialize(
        decode_portfolio_result_artifact(artifact.raw_payload),
        equity_curve=equity,
        trades=trades,
    )

    assert restored.snapshots == []
    assert restored.period_holdings == []
    assert restored.stock_contribution == []
    assert restored.selection_diagnostics == []
    assert restored.improvement_hints == []
    assert restored.equity_curve.empty and list(restored.equity_curve.columns) == [
        "date",
        "equity",
    ]
    assert restored.trades.empty and list(restored.trades.columns) == [
        "date",
        "stock_code",
        "shares",
    ]
    assert restored.replay_parent_id == _PARENT_ID


def test_unknown_schema_missing_fields_and_duplicate_keys_fail_closed() -> None:
    raw = _encode().raw_payload

    def remove_details(document: dict[str, Any]) -> None:
        document["payload"].pop("details")

    unknown_schema = _rewrite_document(
        raw,
        lambda document: document.__setitem__("schema_version", "portfolio.v99"),
        rehash_header=True,
    )

    with pytest.raises(PortfolioResultArtifactCodecError, match="schema_version"):
        decode_portfolio_result_artifact(unknown_schema)

    missing_payload_field = _rewrite_document(
        raw,
        remove_details,
        rehash_header=True,
    )
    wrong_payload_type = _rewrite_document(
        raw,
        lambda document: document["payload"].__setitem__("summary", {"kind": "none"}),
        rehash_header=True,
    )
    with pytest.raises(PortfolioResultArtifactCodecError, match="payload"):
        decode_portfolio_result_artifact(missing_payload_field)

    with pytest.raises(PortfolioResultArtifactCodecError, match="summary"):
        decode_portfolio_result_artifact(wrong_payload_type)

    wrong_dto_type = _rewrite_document(
        raw,
        lambda document: document["payload"]["period_holdings"][0].__setitem__(
            "rank", {"kind": "str", "value": "first"}
        ),
        rehash_header=True,
    )
    with pytest.raises(PortfolioResultArtifactCodecError, match="rank"):
        decode_portfolio_result_artifact(wrong_dto_type)

    duplicate_key = raw[:-1] + b',"schema_version":"duplicate"}'
    with pytest.raises(PortfolioResultArtifactCodecError, match="重複 key"):
        decode_portfolio_result_artifact(duplicate_key)


def test_raw_payload_and_canonical_hash_tampering_are_rejected() -> None:
    raw = _encode().raw_payload
    tampered_payload = _rewrite_document(
        raw,
        lambda document: document["payload"].__setitem__("snapshots", []),
        rehash_header=False,
    )
    tampered_hash = _rewrite_document(
        raw,
        lambda document: document.__setitem__("payload_hash", "sha256:" + "0" * 64),
        rehash_header=False,
    )
    noncanonical_raw = raw + b" "

    for candidate in (tampered_payload, tampered_hash, noncanonical_raw):
        with pytest.raises(PortfolioResultArtifactCodecError):
            decode_portfolio_result_artifact(candidate)


def test_numpy_scalar_dtype_alias_is_rejected_after_payload_hash_recalculation() -> None:
    artifact = _encode()
    normal_roundtrip = decode_portfolio_result_artifact(artifact.raw_payload)
    assert normal_roundtrip.raw_payload == artifact.raw_payload

    def change_canonical_float32_dtype(document: dict[str, Any]) -> None:
        pending: list[object] = [document]
        while pending:
            value = pending.pop()
            if type(value) is dict:
                mapping = value
                if (
                    mapping.get("kind") == "numpy_scalar"
                    and mapping.get("dtype") == "<f4"
                ):
                    mapping["dtype"] = "f4"
                    return
                pending.extend(mapping.values())
            elif type(value) is list:
                pending.extend(value)
        raise AssertionError("encoded sidecar missing canonical <f4 scalar")

    aliased_dtype = _rewrite_document(
        artifact.raw_payload,
        change_canonical_float32_dtype,
        rehash_header=True,
    )
    with pytest.raises(PortfolioResultArtifactCodecError, match="dtype.*canonical"):
        decode_portfolio_result_artifact(aliased_dtype)


def test_materialization_checks_registry_parent_and_parquet_hash_bindings() -> None:
    artifact = _encode()
    equity = pd.DataFrame()
    trades = pd.DataFrame()

    bad_expectations = (
        {"expected_registry_run_id": "registry-other"},
        {"expected_portfolio_parent_id": "parent-other"},
        {"equity_parquet_sha256": "sha256:" + "0" * 64},
        {"trades_parquet_sha256": "sha256:" + "1" * 64},
    )
    for changes in bad_expectations:
        args: dict[str, object] = {
            "equity_curve": equity,
            "trades": trades,
            "expected_registry_run_id": _REGISTRY_RUN_ID,
            "expected_portfolio_parent_id": _PARENT_ID,
            "equity_parquet_sha256": _EQUITY_HASH,
            "trades_parquet_sha256": _TRADES_HASH,
        }
        args.update(changes)
        with pytest.raises(PortfolioResultArtifactCodecError):
            artifact.materialize_result(**args)  # type: ignore[arg-type]


def test_parent_identity_conflicts_and_unsupported_values_are_rejected() -> None:
    result = RecommendationPortfolioBacktestResultDTO(
        summary={},
        equity_curve=pd.DataFrame(),
        trades=pd.DataFrame(),
        snapshots=[],
        period_holdings=[],
        stock_contribution=[],
    )
    result.attach_replay_parent_id("parent-other")
    with pytest.raises(PortfolioResultArtifactCodecError, match="parent"):
        _encode(result)

    with pytest.raises(PortfolioResultArtifactCodecError, match="必須分離"):
        encode_portfolio_result_artifact(
            _result(),
            registry_run_id=_PARENT_ID,
            portfolio_parent_id=_PARENT_ID,
            equity_parquet_sha256=_EQUITY_HASH,
            trades_parquet_sha256=_TRADES_HASH,
        )

    unsupported = _result(snapshots=[])
    unsupported.details = {"unsupported": np.array((1,), dtype=[("x", "i4")])[()]}
    with pytest.raises(PortfolioResultArtifactCodecError, match="NumPy scalar dtype"):
        _encode(unsupported)


def test_envelope_constructor_rejects_claims_not_matching_verified_bytes() -> None:
    artifact = _encode()
    with pytest.raises(PortfolioResultArtifactCodecError, match="fields 與 raw payload"):
        RecommendationPortfolioResultArtifactV1(
            raw_payload=artifact.raw_payload,
            registry_run_id="registry-other",
            portfolio_parent_id=artifact.portfolio_parent_id,
            equity_parquet_sha256=artifact.equity_parquet_sha256,
            trades_parquet_sha256=artifact.trades_parquet_sha256,
            payload_hash=artifact.payload_hash,
            raw_payload_sha256=artifact.raw_payload_sha256,
        )
    with pytest.raises(PortfolioResultArtifactCodecError, match="raw_payload_sha256"):
        RecommendationPortfolioResultArtifactV1(
            raw_payload=artifact.raw_payload,
            registry_run_id=artifact.registry_run_id,
            portfolio_parent_id=artifact.portfolio_parent_id,
            equity_parquet_sha256=artifact.equity_parquet_sha256,
            trades_parquet_sha256=artifact.trades_parquet_sha256,
            payload_hash=artifact.payload_hash,
            raw_payload_sha256="sha256:" + "0" * 64,
        )
