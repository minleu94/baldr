from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import json

import pytest

from app_module.dtos import RecommendationDTO, RecommendationResultDTO
from app_module.portfolio_source_adapter import (
    build_backtest_trade_source,
    build_recommendation_execution_trade_source,
    build_recommendation_trade_source,
    stable_snapshot_hash,
)
from app_module.portfolio_store import PortfolioJsonlStore
from app_module.recommendation.contracts import (
    Context,
    DecisionBatch,
    ExecutionStatus,
    IndexStatus,
    RecommendationConfigSnapshot,
    RecommendationExecution,
    RecommendationUniverseIdentity,
    Request,
    SaveReceipt,
    UniversePolicyIdentity,
    UniverseSnapshotIdentity,
)
from app_module.recommendation.queries import RecommendationExecutionReadModel
from app_module.recommendation.contracts import ReferenceKind, VersionReference
from decision_module.recommendation.contracts import RecommendationItem


def make_recommendation() -> RecommendationDTO:
    return RecommendationDTO(
        stock_code="2330",
        stock_name="台積電",
        close_price=888.0,
        price_change=1.25,
        total_score=82.5,
        indicator_score=80.0,
        pattern_score=75.0,
        volume_score=92.0,
        recommendation_reasons="量能放大；趨勢偏多",
        industry="半導體",
        regime_match=True,
    )


def test_build_recommendation_trade_source_contains_traceable_context():
    result = RecommendationResultDTO(
        result_id="rec_20260604_001",
        result_name="短線暴衝候選",
        created_at="2026-06-04T09:00:00",
        config={
            "profile_id": "aggressive_short",
            "profile_version": "1.0",
            "regime_snapshot": {"regime": "trend", "confidence": 0.81},
        },
        recommendations=[make_recommendation()],
        regime="trend",
        notes="日常推薦",
    )

    source = build_recommendation_trade_source(result, make_recommendation())

    assert source.source_type == "recommendation_result"
    assert source.source_id == "rec_20260604_001"
    assert source.source_snapshot_hash
    assert source.source_summary["result_id"] == "rec_20260604_001"
    assert source.source_summary["result_name"] == "短線暴衝候選"
    assert source.source_summary["created_at"] == "2026-06-04T09:00:00"
    assert source.source_summary["stock_code"] == "2330"
    assert source.source_summary["stock_name"] == "台積電"
    assert source.source_summary["close_price"] == 888.0
    assert source.source_summary["price_change"] == 1.25
    assert source.source_summary["profile_id"] == "aggressive_short"
    assert source.source_summary["profile_version"] == "1.0"
    assert source.source_summary["regime"] == "trend"
    assert source.source_summary["total_score"] == 82.5
    assert source.source_summary["indicator_score"] == 80.0
    assert source.source_summary["pattern_score"] == 75.0
    assert source.source_summary["volume_score"] == 92.0
    assert source.source_summary["recommendation_reasons"] == "量能放大；趨勢偏多"
    assert source.source_summary["reasons"] == ["量能放大", "趨勢偏多"]
    assert source.source_summary["industry"] == "半導體"
    assert source.source_summary["regime_match"] is True


def test_build_backtest_trade_source_contains_run_and_strategy_context():
    row = {
        "股票代號": "2330",
        "股票名稱": "台積電",
        "買賣": "買入",
        "交易日期": "2026-06-04",
        "價格": 888.0,
        "數量": 1000,
    }
    source = build_backtest_trade_source(
        run_id="run_001",
        run_name="2330 momentum smoke",
        strategy_id="momentum_aggressive_v1",
        validation_status="PASS",
        trade_row=row,
    )

    assert source.source_type == "backtest_run"
    assert source.source_id == "run_001"
    assert source.source_snapshot_hash
    assert source.source_summary["strategy_id"] == "momentum_aggressive_v1"
    assert source.source_summary["validation_status"] == "PASS"
    assert source.source_summary["stock_code"] == "2330"


def test_build_backtest_trade_source_keeps_amount_separate_from_quantity():
    row = {
        "股票代號": "2330",
        "股票名稱": "台積電",
        "買賣": "買入",
        "交易日期": "2026-06-04",
        "價格": 888.0,
        "amount": 100000,
    }
    source = build_backtest_trade_source(
        run_id="run_002",
        run_name="2330 momentum smoke",
        strategy_id="momentum_aggressive_v1",
        validation_status="PASS",
        trade_row=row,
    )

    assert source.source_summary["quantity"] == ""
    assert source.source_summary["amount"] == 100000


def test_build_backtest_trade_source_supports_realistic_ui_row_aliases():
    row = {
        "證券代號": "2330",
        "證券名稱": "台積電",
        "買賣": "買入",
        "日期": "2026-06-04",
        "單價": 888.0,
        "交易股數": 1000,
    }
    source = build_backtest_trade_source(
        run_id="run_003",
        run_name="2330 momentum smoke",
        strategy_id="momentum_aggressive_v1",
        validation_status="PASS",
        trade_row=row,
    )

    assert source.source_summary["stock_code"] == "2330"
    assert source.source_summary["stock_name"] == "台積電"
    assert source.source_summary["trade_date"] == "2026-06-04"
    assert source.source_summary["price"] == 888.0
    assert source.source_summary["quantity"] == 1000


def test_build_backtest_trade_source_supports_standard_backtest_trade_columns():
    row = {
        "證券代號": "2330",
        "證券名稱": "台積電",
        "買賣": "買入",
        "進場日期": "2026-06-04",
        "進場價格": 888.0,
        "股數": 1000,
        "報酬率%": 3.2,
    }
    source = build_backtest_trade_source(
        run_id="run_004",
        run_name="2330 momentum smoke",
        strategy_id="momentum_aggressive_v1",
        validation_status="PASS",
        trade_row=row,
    )

    assert source.source_summary["stock_code"] == "2330"
    assert source.source_summary["stock_name"] == "台積電"
    assert source.source_summary["trade_date"] == "2026-06-04"
    assert source.source_summary["price"] == 888.0
    assert source.source_summary["quantity"] == 1000


def test_stable_snapshot_hash_is_deterministic_for_same_payload_and_changes_with_payload():
    same_left = stable_snapshot_hash({"a": 1, "b": [2]})
    same_right = stable_snapshot_hash({"b": [2], "a": 1})
    different = stable_snapshot_hash({"a": 2, "b": [2]})

    assert same_left == same_right
    assert same_left != different
    assert len(stable_snapshot_hash({"a": 1})) == 64


def _universe_identity() -> RecommendationUniverseIdentity:
    policy_spec = {
        "schema": "recommendation-universe-policy.v1",
        "selection_algorithm": "ordered_input_v1",
        "selection_mode": "all",
        "industry_filter": "",
        "max_stocks": 200,
        "source_provider_id": "provider-1",
    }
    policy_spec_json = json.dumps(
        policy_spec,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    policy_hash = hashlib.sha256(policy_spec_json.encode("utf-8")).hexdigest()
    policy = UniversePolicyIdentity(
        universe_policy_id=f"recommendation-universe-policy-v1:{policy_hash}",
        universe_policy_hash=f"sha256:{policy_hash}",
        universe_policy_schema=policy_spec["schema"],
        universe_policy_spec_json=policy_spec_json,
    )
    selected_codes_hash = hashlib.sha256(
        json.dumps(
            {"selected_codes": ["2330"]},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    spec = {
        "schema": "recommendation-universe-snapshot.v1",
        "universe_policy_id": policy.universe_policy_id,
        "source_provider_id": "provider-1",
        "decision_date": "2026-09-23",
        "selection_mode": "all",
        "selected_codes": ["2330"],
        "selected_count": 1,
        "selected_codes_hash": f"sha256:{selected_codes_hash}",
        "requested_codes": None,
    }
    spec_json = json.dumps(
        spec,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    spec_hash = hashlib.sha256(spec_json.encode("utf-8")).hexdigest()
    snapshot = UniverseSnapshotIdentity(
        universe_snapshot_id=f"recommendation-universe-snapshot-v1:{spec_hash}",
        universe_snapshot_hash=f"sha256:{spec_hash}",
        universe_snapshot_schema=spec["schema"],
        universe_snapshot_source_provider_id="provider-1",
        universe_snapshot_selected_codes_hash=f"sha256:{selected_codes_hash}",
        universe_snapshot_spec_json=spec_json,
    )
    return RecommendationUniverseIdentity(
        universe_id=f"recommendation-universe-v1:{spec_hash}",
        universe_hash=f"sha256:{spec_hash}",
        universe_identity_schema=spec["schema"],
        policy=policy,
        snapshot=snapshot,
    )


def _canonical_execution_and_readback(
    *,
    ml_rows=(),
    ml_read_status="not_requested",
    snapshot_identity=True,
):
    config_json = json.dumps(
        {"manual_qt_snapshot": True, "profile_id": "momentum"},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    config_snapshot = RecommendationConfigSnapshot(
        raw_config_json=config_json,
        raw_json_sha256="sha256:" + hashlib.sha256(config_json.encode()).hexdigest(),
    )
    item = RecommendationItem(
        stock_code="2330",
        stock_name="台積電",
        close_price=Decimal("1E+2"),
        price_change=Decimal("1.25"),
        rule_score=Decimal("88.50"),
        indicator_score=Decimal("80"),
        pattern_score=Decimal("75"),
        volume_score=Decimal("92"),
        reason_text="量能放大；趨勢偏多",
        industry="半導體",
        rank=1,
    )
    request = Request(
        config_snapshot=config_snapshot,
        profile_ref=VersionReference(ReferenceKind.PROFILE, "momentum", "2.1"),
        max_stocks=200,
        top_n=50,
    )
    context = Context(
        as_of_date=date(2026, 9, 23),
        created_at=datetime(2026, 9, 23, tzinfo=timezone.utc),
        universe_identity=(
            _universe_identity()
            if snapshot_identity
            else None
        ),
        universe_snapshot_ref=(
            None
            if snapshot_identity
            else VersionReference(ReferenceKind.UNIVERSE_SNAPSHOT, "typed-snapshot-ref")
        ),
    )
    execution = RecommendationExecution(
        result_id="rec_qt_20260923_001",
        request=request,
        context=context,
        status=ExecutionStatus.COMPLETED,
        decision=DecisionBatch(items=(item,), regime="Trend"),
    )
    persisted_at = datetime(2026, 9, 23, 1, tzinfo=timezone.utc)
    payload_hash = "sha256:" + "a" * 64
    artifact_location = "C:/tmp/canonical-artifact.json"
    read_model = RecommendationExecutionReadModel(
        execution=execution,
        label="Qt recommendation",
        notes="Profile: momentum, Regime: Trend",
        persisted_at=persisted_at,
        payload_hash=payload_hash,
        artifact_location=artifact_location,
        integrity_basis="canonical_payload_and_index_verified",
        ml_read_status=ml_read_status,
        ml_projection_rows=tuple(ml_rows),
    )
    receipt = SaveReceipt(
        result_id=execution.result_id,
        payload_hash=payload_hash,
        artifact_location=artifact_location,
        persisted_at=persisted_at,
        index_status=IndexStatus.INDEXED,
    )
    return execution, item, read_model, receipt


def test_execution_trade_source_uses_verified_item_and_explicit_snapshot_identity():
    execution, item, read_model, receipt = _canonical_execution_and_readback()

    source = build_recommendation_execution_trade_source(
        execution, read_model, receipt, item
    )

    assert source.source_id == execution.result_id
    assert source.source_summary["result_id"] == execution.result_id
    assert source.source_summary["stock_code"] == item.stock_code
    assert source.source_summary["candidate_identity"] == {"stock_code": "2330", "rank": 1}
    assert source.source_summary["source_snapshot_id"].startswith(
        "recommendation-universe-snapshot-v1:"
    )
    assert source.source_summary["source_snapshot_hash"] == execution.context.universe_identity.snapshot.universe_snapshot_hash
    assert source.source_summary["artifact_location"] == receipt.artifact_location
    assert source.source_summary["payload_hash"] == receipt.payload_hash
    assert source.source_summary["source_snapshot_id"] != receipt.artifact_location
    assert source.source_snapshot_hash == stable_snapshot_hash(source.source_summary)
    assert source.source_summary["calibrated_probability_status"] == "unavailable"
    assert source.source_summary["calibrated_probability_bp"] is None


def test_execution_trade_source_maps_verified_ml_aliases_and_named_provenance():
    training = {"status": "verified", "training_source_hash": "sha256:" + "b" * 64}
    inference = {"status": "verified", "inference_source_hash": "sha256:" + "c" * 64}
    compatibility = {"status": "compatible", "schema_version": "v1"}
    rows = (
        {
            "stock_code": "2330",
            "model_version": "model-3",
            "dataset_version": "dataset-9",
            "horizon": "20 trading days",
            "status": "active_candidate",
            "source_trace": ["candidate:model-3"],
            "warnings": ["shadow only"],
            "probability_transform_id": "transform-v2",
            "raw_calibrated_probability_bp": 7250,
            "training_provenance": training,
            "inference_provenance": inference,
            "provenance_compatibility": compatibility,
            "provenance_status": "verified",
        },
    )
    execution, item, read_model, receipt = _canonical_execution_and_readback(
        ml_rows=rows,
        ml_read_status="verified",
    )

    source = build_recommendation_execution_trade_source(
        execution, read_model, receipt, item
    )
    summary = source.source_summary

    assert summary["calibration_model_version"] == "model-3"
    assert summary["calibration_dataset_version"] == "dataset-9"
    assert summary["calibration_horizon"] == "20 trading days"
    assert summary["calibration_status"] == "active_candidate"
    assert summary["calibration_source_trace"] == ["candidate:model-3"]
    assert summary["calibration_warnings"] == ["shadow only"]
    assert summary["calibration_probability_transform_id"] == "transform-v2"
    assert summary["calibration_raw_probability_bp"] == 7250
    assert summary["calibration_provenance"] == {
        "training_provenance": training,
        "inference_provenance": inference,
        "provenance_compatibility": compatibility,
        "provenance_status": "verified",
    }


def test_execution_trade_source_normalizes_summary_before_jsonl_hash_roundtrip(tmp_path):
    execution, item, read_model, receipt = _canonical_execution_and_readback(
        snapshot_identity=False
    )
    source = build_recommendation_execution_trade_source(
        execution, read_model, receipt, item
    )

    assert source.source_summary["source_snapshot_id"] == "typed-snapshot-ref"
    assert source.source_summary["source_snapshot_hash"] == ""
    assert source.source_summary["close_price"] == "100"
    assert source.source_summary["price_change"] == "1.25"

    store = PortfolioJsonlStore(tmp_path)
    store.append_trade(
        {
            "trade_id": "trade-1",
            "source_type": source.source_type,
            "source_id": source.source_id,
            "source_snapshot_hash": source.source_snapshot_hash,
            "source_summary": source.source_summary,
        }
    )
    stored = store.load_trades()[0]
    summary = stored["source_summary"]
    assert stable_snapshot_hash(summary) == stored["source_snapshot_hash"]

    def contains_float(value):
        if type(value) is float:
            return True
        if isinstance(value, dict):
            return any(contains_float(item) for item in value.values())
        if isinstance(value, list):
            return any(contains_float(item) for item in value)
        return False

    assert not contains_float(summary)


def test_execution_trade_source_rejects_mismatched_selected_item_or_readback():
    execution, item, read_model, receipt = _canonical_execution_and_readback()
    wrong_item = RecommendationItem(stock_code="2317", rank=1)
    with pytest.raises(ValueError, match="選定股票"):
        build_recommendation_execution_trade_source(
            execution, read_model, receipt, wrong_item
        )

    mismatched = RecommendationExecutionReadModel(
        execution=None,
        label=read_model.label,
        notes=read_model.notes,
        persisted_at=read_model.persisted_at,
        payload_hash=read_model.payload_hash,
        artifact_location=read_model.artifact_location,
        integrity_basis="canonical_payload_and_index_verified",
    )
    with pytest.raises(ValueError, match="同一份 sealed execution"):
        build_recommendation_execution_trade_source(
            execution, mismatched, receipt, item
        )
