"""R030 fixture-only 擴充推演：檢查正式 codec、registry 與 builder 路徑。"""

from __future__ import annotations

from dataclasses import dataclass, field, fields, make_dataclass, replace
from datetime import date, timedelta
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
import numpy as np
import pandas as pd

import app_module.recommendation.codec as execution_codec
import app_module.recommendation.contracts as execution_contracts
import app_module.recommendation.persistence as execution_persistence
import decision_module.recommendation.contracts as decision_contracts
from app_module.recommendation.contracts import (
    RecommendationExecution,
)
from app_module.recommendation.persistence import RecommendationExecutionPersistence
from app_module.recommendation.queries import RecommendationExecutionQueries
from data_module.result_artifact_store import ResultArtifactStore
from data_module.ml_historical_snapshot_provider import (
    HistoricalIndexObservation,
    HistoricalPriceObservation,
    HistoricalRawSnapshot,
    HistoricalTechnicalObservation,
)
from decision_module.recommendation.contracts import DecisionBatch, RecommendationItem
import decision_module.strategies
from decision_module.strategies.baseline_score_executor import BaselineScoreExecutor
from decision_module.strategies.contracts import StrategyExecutor, StrategySpec
from decision_module.strategies.registry import StrategyRegistry
from ml_module.feature_registry import CORE_LONG_HISTORY_FEATURE_REGISTRY, FeatureRegistry
from ml_module.historical_contracts import HistoricalFeatureRow, HistoricalFeatureSpec
from ml_module.historical_feature_builder import HistoricalFeatureBuilder
from ml_module.probability_calibration import FittedShadowProbabilityCalibrator
from ml_module.recommendation_calibration_training import RunnableRecommendationCalibrationModel
from decision_module.strategy_configurator import StrategyConfigurator
from ui_qt.views.recommendation.presenter import recommendation_item_to_view_row


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / "fixtures" / "r030"


class _SyntheticPrefixExecutor(StrategyExecutor):
    """fixture 專用策略：只依目前與前一交易日收盤整數分值產生訊號。"""

    def __init__(self, spec: StrategySpec) -> None:
        self.spec = spec

    def generate_signals(
        self,
        df: pd.DataFrame,
        spec: StrategySpec,
        execution_start_date: str | None = None,
    ) -> pd.DataFrame:
        if not isinstance(df.index, pd.DatetimeIndex):
            raise ValueError("fixture executor 需要 DatetimeIndex")
        ordered = df.sort_index().copy()
        close_cents = ordered["close_cents"]
        previous_cents = close_cents.shift(1)
        rising = close_cents > previous_cents
        start = (
            pd.Timestamp(execution_start_date)
            if execution_start_date is not None
            else ordered.index.min()
        )
        active = ordered.index >= start
        signals = (rising & active).astype("int64")
        ordered["signal"] = signals
        ordered["score"] = signals * 10_000
        ordered["reason_tags"] = ["price_up" if signal else "no_rise" for signal in signals]
        ordered["regime_match"] = True
        return ordered


@dataclass(frozen=True, slots=True)
class _SyntheticConfidenceContractV1:
    confidence_score_bp: int | None
    confidence_method_version: str | None
    confidence_status: str

    def __post_init__(self) -> None:
        score = self.confidence_score_bp
        if score is None:
            if self.confidence_method_version is not None or self.confidence_status != "not_computed":
                raise ValueError("missing confidence requires not_computed status and no method")
            return
        if type(score) is not int or not 0 <= score <= 10_000:
            raise ValueError("confidence_score_bp must be an integer in 0..10000")
        if self.confidence_method_version != "r030.synthetic-confidence.v1":
            raise ValueError("confidence method version mismatch")
        if self.confidence_status != "computed":
            raise ValueError("computed confidence requires computed status")


def _synthetic_confidence(values: tuple[int, ...] | None) -> _SyntheticConfidenceContractV1:
    if values is None:
        return _SyntheticConfidenceContractV1(None, None, "not_computed")
    score = sum(values)
    return _SyntheticConfidenceContractV1(
        score,
        "r030.synthetic-confidence.v1",
        "computed",
    )


def _fixture_presenter(item: RecommendationItem) -> dict[str, Any]:
    """只格式化 fixture 新欄位；舊欄位全部由 production presenter 產生。"""

    row = recommendation_item_to_view_row(item, ml_status="not_requested")
    row.update(
        {
            "confidence_score_bp": getattr(item, "confidence_score_bp"),
            "confidence_method_version": getattr(item, "confidence_method_version"),
            "confidence_status": getattr(item, "confidence_status"),
        }
    )
    return row


def _register_fixture_contract(monkeypatch: pytest.MonkeyPatch) -> Any:
    """模擬新版 row contract alias、wire registration 與 schema revision。"""

    schema = json.loads(
        (FIXTURES / "confidence_extension_contract.json").read_text(encoding="utf-8")
    )
    assert schema["fixture_only"] is True
    annotation_types: dict[str, Any] = {
        "int | null": int | None,
        "str | null": str | None,
        "str": str,
    }
    extension_fields = tuple(
        (
            field_spec["name"],
            annotation_types[field_spec["annotation"]],
            field(default=field_spec["default"]),
        )
        for field_spec in schema["fields"]
    )

    def validate_confidence(self: object) -> None:
        RecommendationItem.__post_init__(self)  # type: ignore[arg-type]
        score = getattr(self, "confidence_score_bp")
        method = getattr(self, "confidence_method_version")
        status = getattr(self, "confidence_status")
        _SyntheticConfidenceContractV1(score, method, status)

    extended_item = make_dataclass(
        "RecommendationItemWithSyntheticConfidenceV1",
        extension_fields,
        bases=(RecommendationItem,),
        namespace={"__module__": __name__, "__post_init__": validate_confidence},
        frozen=True,
        slots=True,
    )
    extended_type = extended_item  # make_dataclass 回傳所建立的 contract class。
    wire_id = schema["wire_record_id"]
    schema_revision = schema["schema_revision"]
    supported_revisions = tuple(schema["supported_schema_revisions"])

    # 模擬 typed row class alias 與固定 wire allowlist 的新版 registration。
    monkeypatch.setattr(decision_contracts, "RecommendationItem", extended_type)
    monkeypatch.setattr(execution_contracts, "RecommendationItem", extended_type)
    monkeypatch.setattr(execution_codec, "RecommendationItem", extended_type)
    monkeypatch.setattr(
        decision_contracts,
        "_ALLOWED_FROZEN_RECORD_TYPES",
        tuple(
            extended_type if item is RecommendationItem else item
            for item in decision_contracts._ALLOWED_FROZEN_RECORD_TYPES
        ),
    )
    monkeypatch.setattr(
        execution_contracts,
        "_ALLOWED_FROZEN_RECORD_TYPES",
        tuple(
            extended_type if item is RecommendationItem else item
            for item in execution_contracts._ALLOWED_FROZEN_RECORD_TYPES
        ),
    )
    record_ids = {
        record_type: current_wire_id
        for record_type, current_wire_id in execution_codec._RECORD_IDS.items()
        if record_type is not RecommendationItem
    }
    record_ids[extended_type] = wire_id
    record_types = {
        current_wire_id: record_type
        for current_wire_id, record_type in execution_codec._RECORD_TYPES.items()
        if current_wire_id != wire_id
    }
    record_types[wire_id] = extended_type
    monkeypatch.setattr(execution_codec, "_RECORD_IDS", record_ids)
    monkeypatch.setattr(execution_codec, "_RECORD_TYPES", record_types)
    # 此 fixture 模擬新增 typed contract revision；序列化／解碼實作保持原封不動。
    monkeypatch.setattr(execution_contracts, "EXECUTION_SCHEMA_REVISION", schema_revision)
    monkeypatch.setattr(
        execution_contracts,
        "SUPPORTED_EXECUTION_SCHEMA_REVISIONS",
        supported_revisions,
    )
    monkeypatch.setattr(execution_codec, "EXECUTION_SCHEMA_REVISION", schema_revision)
    monkeypatch.setattr(
        execution_codec,
        "SUPPORTED_EXECUTION_SCHEMA_REVISIONS",
        supported_revisions,
    )
    monkeypatch.setattr(execution_persistence, "EXECUTION_SCHEMA_REVISION", schema_revision)
    return extended_type


def _replayed_execution(monkeypatch: pytest.MonkeyPatch) -> RecommendationExecution:
    from app_module.recommendation_dataframe_provider import RecommendationDataFrameProvider
    from app_module.recommendation_replay_service import RecommendationReplayService

    monkeypatch.setattr(StrategyConfigurator, "_filter_log_count", 0, raising=False)
    monkeypatch.setattr(StrategyConfigurator, "_price_filter_log_count", 0, raising=False)
    monkeypatch.setattr(StrategyConfigurator, "_volume_filter_log_count", 0, raising=False)
    provider = RecommendationDataFrameProvider()
    monkeypatch.setattr(
        provider.strategy_configurator,
        "configure_technical_indicators",
        lambda frame, technical_config, full_config=None: frame,
    )

    def fixed_score(frame: pd.DataFrame, config: dict[str, Any], regime: Any = None) -> pd.DataFrame:
        scored = frame.copy()
        count = len(scored)
        for name, values in (
            ("漲幅%", np.asarray([2.0] * count, dtype="float64")),
            ("成交量變化率%", np.asarray([20.0] * count, dtype="float64")),
            ("RSI", np.asarray([50] * count, dtype="int64")),
        ):
            scored[name] = pd.Series(values, index=scored.index)
        scored["TotalScore"] = 50
        scored["FinalScore"] = 50
        scored["IndicatorScore"] = 50
        scored["PatternScore"] = 0
        scored["VolumeScore"] = 0
        return scored

    monkeypatch.setattr(
        provider.strategy_configurator.scoring_engine,
        "calculate_total_score",
        fixed_score,
    )
    dates = pd.date_range("2026-09-01", periods=21, freq="D")
    history = pd.DataFrame(
        {
            "日期": [int(value.strftime("%Y%m%d")) for value in dates],
            "證券代號": ["2330"] * len(dates),
            "證券名稱": ["fixture"] * len(dates),
            "開盤價": [100] * len(dates),
            "最高價": [101] * len(dates),
            "最低價": [99] * len(dates),
            "收盤價": [100] * len(dates),
            "成交股數": [1000] * len(dates),
            "RSI": [50] * len(dates),
        },
    )
    history.loc[history.index[-1], "收盤價"] = 101
    history.loc[history.index[-1], "開盤價"] = 101
    history.loc[history.index[-1], "最高價"] = 102
    history.loc[history.index[-1], "最低價"] = 100
    snapshot = RecommendationReplayService(provider).run_snapshot(
        as_of_date="2026-09-21",
        profile_id="r030-synthetic-confidence",
        config={"filters": {"price_change_min": 1.0}},
        history=history,
        universe=None,
        top_n=10,
        parent_result_id="r030-synthetic-replay-parent",
    )
    assert snapshot.canonical_execution is not None
    return snapshot.canonical_execution


def _attach_confidence_to_replayed_rows(
    execution: RecommendationExecution,
    extended_item_type: Any,
    values: tuple[int, ...] | None,
    *,
    result_id: str,
) -> RecommendationExecution:
    """fixture calculator 將新 typed 欄位附加至真 replay 產出的 canonical rows。"""

    confidence = _synthetic_confidence(values)
    extended_items = tuple(
        extended_item_type(
            **{item.name: getattr(item_value, item.name) for item in fields(RecommendationItem)},
            confidence_score_bp=confidence.confidence_score_bp,
            confidence_method_version=confidence.confidence_method_version,
            confidence_status=confidence.confidence_status,
        )
        for item_value in execution.items
    )
    assert execution.decision is not None
    return replace(
        execution,
        result_id=result_id,
        decision=replace(execution.decision, items=extended_items),
    )


def _rehash(document: dict[str, object]) -> bytes:
    header = {
        "schema_version": document["schema_version"],
        "schema_revision": document["schema_revision"],
        "payload": document["payload"],
    }
    canonical = json.dumps(
        header,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    document["payload_hash"] = "sha256:" + hashlib.sha256(canonical).hexdigest()
    return json.dumps(
        document,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


@pytest.mark.parametrize("score_inputs", (None, (0,), (10_000,)))
def test_confidence_extension_uses_real_codec_store_readback_and_presenter(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    score_inputs: tuple[int, ...] | None,
) -> None:
    replayed = _replayed_execution(monkeypatch)
    extended_item_type = _register_fixture_contract(monkeypatch)
    confidence = _synthetic_confidence(score_inputs)
    execution = _attach_confidence_to_replayed_rows(
        replayed,
        extended_item_type,
        score_inputs,
        result_id=f"r030-confidence-{score_inputs}",
    )
    store = ResultArtifactStore(
        artifact_root=tmp_path / "output" / "runs" / "execution_artifacts",
        database_path=tmp_path / "output" / "runs" / "recommendation_runs.db",
    )
    persistence = RecommendationExecutionPersistence(store)
    saved = persistence.save(execution)
    loaded = RecommendationExecutionQueries(persistence).get(execution.result_id)

    assert loaded is not None
    assert loaded.execution == execution
    assert loaded.schema_revision == 3
    assert loaded.payload_hash == saved.payload_hash

    current_item = execution.items[0]
    history_item = loaded.execution.items[0]
    current_old_row = recommendation_item_to_view_row(current_item, ml_status="not_requested")
    history_old_row = recommendation_item_to_view_row(history_item, ml_status="not_requested")
    current_row = _fixture_presenter(current_item)
    history_row = _fixture_presenter(history_item)
    assert current_old_row == history_old_row
    assert current_row == history_row
    assert {key: current_row[key] for key in current_old_row} == current_old_row
    assert type(current_item) is extended_item_type
    assert type(history_item) is extended_item_type
    assert getattr(current_item, "confidence_score_bp") == confidence.confidence_score_bp
    assert getattr(current_item, "confidence_method_version") == confidence.confidence_method_version
    assert getattr(current_item, "confidence_status") == confidence.confidence_status
    assert getattr(history_item, "confidence_score_bp") == confidence.confidence_score_bp
    assert getattr(history_item, "confidence_method_version") == confidence.confidence_method_version
    assert getattr(history_item, "confidence_status") == confidence.confidence_status
    assert "confidence_score_bp" not in RecommendationItem.__dataclass_fields__
    with pytest.raises(ValueError, match="stock_code"):
        extended_item_type(stock_code=" ")


@pytest.mark.parametrize("score_inputs", ((-1,), (10_001,)))
def test_confidence_extension_rejects_out_of_range_values(
    score_inputs: tuple[int, ...],
) -> None:
    with pytest.raises(ValueError, match=r"0\.\.10000"):
        _synthetic_confidence(score_inputs)


def test_confidence_extension_preserves_old_revision_bytes_and_rejects_unknown_revision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    replayed = _replayed_execution(monkeypatch)
    extended_item_type = _register_fixture_contract(monkeypatch)
    old_path = ROOT / "tests" / "fixtures" / "recommendation_execution_rev1.json"
    old_bytes = old_path.read_bytes()
    old_hash = hashlib.sha256(old_bytes).hexdigest()

    old_envelope = execution_codec.decode_execution_envelope(old_bytes)

    assert old_envelope.schema_revision == 1
    assert hashlib.sha256(old_path.read_bytes()).hexdigest() == old_hash
    assert old_path.read_bytes() == old_bytes

    execution = _attach_confidence_to_replayed_rows(
        replayed,
        extended_item_type,
        (0,),
        result_id="r030-unsupported-revision",
    )
    encoded = execution_codec.encode_execution(execution)
    document = json.loads(encoded)
    document["schema_revision"] = 4
    unsupported = _rehash(document)
    with pytest.raises(execution_codec.ExecutionCodecError, match="schema_revision"):
        execution_codec.decode_execution(unsupported)


def test_codec_rejects_fixture_unlisted_record_type_without_dynamic_import() -> None:
    old_path = ROOT / "tests" / "fixtures" / "recommendation_execution_rev1.json"
    document = json.loads(old_path.read_bytes())
    unknown_record = json.loads((FIXTURES / "unknown_codec_record.json").read_text(encoding="utf-8"))
    document["payload"] = unknown_record
    raw = _rehash(document)

    with pytest.raises(execution_codec.ExecutionCodecError, match="contract type"):
        execution_codec.decode_execution(raw)


def _synthetic_feature_snapshot() -> HistoricalRawSnapshot:
    dates = tuple(date(2026, 1, 1) + timedelta(days=index) for index in range(61))
    iso_dates = tuple(value.isoformat() for value in dates)
    prices = tuple(
        HistoricalPriceObservation(
            symbol="2330",
            trading_date=trading_date,
            open_price=Decimal(99 + index),
            high_price=Decimal(101 + index),
            low_price=Decimal(98 + index),
            close_price=Decimal(100 + index),
            volume=1_000 + index,
            turnover_amount_minor=(100 + index) * (1_000 + index),
        )
        for index, trading_date in enumerate(iso_dates)
    )
    cutoff = iso_dates[-1]
    decision_date = (dates[-1] + timedelta(days=1)).isoformat()
    future_row = HistoricalPriceObservation(
        symbol="2330",
        trading_date=decision_date,
        open_price=Decimal("999998"),
        high_price=Decimal("1000000"),
        low_price=Decimal("999997"),
        close_price=Decimal("999999"),
        volume=999_999,
        turnover_amount_minor=999_999_000_000,
    )
    market = tuple(
        HistoricalIndexObservation("market", trading_date, Decimal(5_000 + index * 2))
        for index, trading_date in enumerate(iso_dates)
    )
    industry = tuple(
        HistoricalIndexObservation("synthetic-industry", trading_date, Decimal(2_000 + index))
        for index, trading_date in enumerate(iso_dates)
    )
    technicals = (
        HistoricalTechnicalObservation(
            "2330", cutoff, None, Decimal("1.25"), Decimal("23")
        ),
    )
    return HistoricalRawSnapshot(
        decision_date=decision_date,
        feature_as_of_date=cutoff,
        prices=(*prices, future_row),
        technicals=technicals,
        market=market,
        industries=industry,
        source_fingerprint="sha256:" + "1" * 64,
        query_count=5,
    )


def _feature_vector_bytes(vector: object) -> bytes:
    document = {
        "symbol": getattr(vector, "symbol"),
        "decision_date": getattr(vector, "decision_date"),
        "feature_as_of_date": getattr(vector, "feature_as_of_date"),
        "available_date": getattr(vector, "available_date"),
        "registry_hash": getattr(vector, "registry_hash"),
        "schema_hash": getattr(vector, "schema_hash"),
        "feature_ids": list(getattr(vector, "feature_ids")),
        "feature_dtypes": list(getattr(vector, "feature_dtypes")),
        "feature_units": list(getattr(vector, "feature_units")),
        "values": list(getattr(vector, "values")),
        "missing_feature_ids": list(getattr(vector, "missing_feature_ids")),
        "snapshot_hash": getattr(vector, "snapshot_hash"),
    }
    return json.dumps(
        document,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _new_registry(added: dict[str, Any]) -> FeatureRegistry:
    feature = added["added_feature"]
    return FeatureRegistry.create(
        registry_id=added["new_registry_id"],
        model_family="core_long_history",
        specs=(
            *CORE_LONG_HISTORY_FEATURE_REGISTRY.specs,
            HistoricalFeatureSpec(
                feature_id=feature["feature_id"],
                family=feature["family"],
                dtype=feature["dtype"],
                unit=feature["unit"],
                missing_policy=feature["missing_policy"],
                availability_policy=feature["availability_policy"],
            ),
        ),
        excluded_families=CORE_LONG_HISTORY_FEATURE_REGISTRY.excluded_families,
    )


def _feature_extension_vectors(
    snapshot: HistoricalRawSnapshot,
    *,
    feature_id: str,
) -> tuple[Any, Any, FeatureRegistry]:
    """用真 builder 計算舊 features，fixture calculator 只計算新增 leaf。"""

    old_builder = HistoricalFeatureBuilder(CORE_LONG_HISTORY_FEATURE_REGISTRY)
    old_row = old_builder.compute(
        snapshot,
        industry_index_name_by_symbol={"2330": "synthetic-industry"},
    )[0]
    cutoff_prices = tuple(
        sorted(
            (
                row
                for row in snapshot.prices
                if row.symbol == "2330" and row.trading_date <= snapshot.feature_as_of_date
            ),
            key=lambda row: row.trading_date,
        )
    )
    current, previous = cutoff_prices[-1], cutoff_prices[-2]
    added_value = (
        None
        if current.close_price is None
        or previous.close_price is None
        or previous.close_price == 0
        else int((current.close_price / previous.close_price - Decimal(1)) * Decimal(10_000))
    )
    new_row = replace(
        old_row,
        values=(*old_row.values, (feature_id, added_value)),
    )
    added = json.loads((FIXTURES / "new_technical_feature.json").read_text(encoding="utf-8"))
    registry = _new_registry(added)
    new_vector = HistoricalFeatureBuilder(registry).load(new_row)
    return old_builder.load(old_row), new_vector, registry


class _ControlledReturnEstimator:
    """只控制數值輸出；輸入轉換仍由 RunnableRecommendationCalibrationModel 執行。"""

    def __init__(self) -> None:
        self.inputs: list[Any] = []

    def predict(self, matrix: Any) -> Any:
        self.inputs.append(matrix.copy())
        return np.nansum(matrix, axis=1)


class _ControlledProbabilityEstimator:
    def __init__(self) -> None:
        self.inputs: list[Any] = []

    def predict_proba(self, matrix: Any) -> Any:
        self.inputs.append(matrix.copy())
        return np.asarray([[0.4, 0.6] for _ in range(len(matrix))], dtype=float)


class _IdentityProbabilityEstimator:
    def predict(self, values: Any) -> Any:
        return values


def _controlled_runnable_model(
    registry: FeatureRegistry,
) -> tuple[RunnableRecommendationCalibrationModel, _ControlledReturnEstimator, _ControlledProbabilityEstimator]:
    model_id = "r030-controlled-legacy-model"
    return_estimator = _ControlledReturnEstimator()
    probability_estimator = _ControlledProbabilityEstimator()
    calibrator = FittedShadowProbabilityCalibrator(
        calibration_id="r030-controlled-calibrator",
        model_id=model_id,
        estimator=_IdentityProbabilityEstimator(),
        sample_count=10,
        fold_count=2,
    )
    model = RunnableRecommendationCalibrationModel(
        model_id=model_id,
        dataset_id="r030-v1-dataset",
        model_family=registry.model_family,
        feature_names=registry.canonical_ids,
        feature_schema=registry.canonical_schema,
        training_as_of="2026-01-01",
        horizon_trading_days=20,
        training_row_count=10,
        return_model=return_estimator,
        upside_model=probability_estimator,
        after_cost_model=None,
        upside_calibrator=calibrator,
        after_cost_calibrator=None,
        calibration_sample_count=10,
        after_cost_calibration_sample_count=0,
        rule_baseline_id="r030-existing-rule",
    )
    return model, return_estimator, probability_estimator


def test_new_technical_feature_is_additive_and_old_v1_fingerprint_is_pinned() -> None:
    pinned = json.loads((FIXTURES / "historical_v1_fingerprint.json").read_text(encoding="utf-8"))
    baseline = CORE_LONG_HISTORY_FEATURE_REGISTRY
    old_builder = HistoricalFeatureBuilder(baseline)
    old_contract = old_builder.load_contract

    assert baseline.registry_id == pinned["registry_id"]
    assert baseline.registry_hash == pinned["registry_hash"]
    assert [list(item) for item in baseline.canonical_schema] == pinned["canonical_schema"]
    assert old_contract.schema_hash == pinned["schema_hash"]
    assert old_contract.contract_hash == pinned["contract_hash"]
    assert old_contract.decision_timing == pinned["decision_timing"]
    assert old_contract.missing_policy == pinned["missing_policy"]

    added = json.loads((FIXTURES / "new_technical_feature.json").read_text(encoding="utf-8"))
    feature = added["added_feature"]
    snapshot = _synthetic_feature_snapshot()
    old_vector_before, new_vector, new_registry = _feature_extension_vectors(
        snapshot,
        feature_id=feature["feature_id"],
    )
    old_vector_bytes = _feature_vector_bytes(old_vector_before)
    old_model_input = old_vector_before.values
    new_old_model_input = new_vector.values[: len(baseline.canonical_ids)]
    model, return_estimator, probability_estimator = _controlled_runnable_model(baseline)
    old_prediction = model.predict(old_model_input)
    new_prediction = model.predict(new_old_model_input)
    old_vector_after, _, _ = _feature_extension_vectors(
        snapshot,
        feature_id=feature["feature_id"],
    )

    assert len(new_vector.feature_ids) == len(baseline.canonical_ids) + 1
    assert new_vector.feature_ids[-1] == feature["feature_id"]
    assert new_vector.registry_hash == new_registry.registry_hash
    assert new_vector.feature_ids[: len(baseline.canonical_ids)] == old_vector_before.feature_ids
    assert new_vector.feature_dtypes[: len(baseline.canonical_dtypes)] == old_vector_before.feature_dtypes
    assert new_vector.feature_units[: len(baseline.canonical_units)] == old_vector_before.feature_units
    assert new_vector.values[: len(baseline.canonical_ids)] == old_vector_before.values
    assert tuple(
        feature_id for feature_id in new_vector.missing_feature_ids
        if feature_id in baseline.canonical_ids
    ) == old_vector_before.missing_feature_ids
    assert old_model_input == new_old_model_input
    assert old_prediction == new_prediction
    assert len(return_estimator.inputs) == len(probability_estimator.inputs) == 2
    np.testing.assert_array_equal(return_estimator.inputs[0], return_estimator.inputs[1])
    np.testing.assert_array_equal(probability_estimator.inputs[0], probability_estimator.inputs[1])
    missing_index = baseline.canonical_ids.index("rsi_normalized_bp")
    assert np.isnan(return_estimator.inputs[0][0][missing_index])
    assert _feature_vector_bytes(old_vector_after) == old_vector_bytes
    assert baseline.registry_id == pinned["registry_id"]
    assert baseline.registry_hash == pinned["registry_hash"]
    assert old_builder.load_contract.canonical_schema == tuple(
        tuple(item) for item in pinned["canonical_schema"]
    )
    with pytest.raises(ValueError, match="schema mismatch"):
        old_contract.validate(
            expected_registry_hash=old_contract.registry_hash,
            expected_canonical_schema=(*old_contract.canonical_schema, new_registry.canonical_schema[-1]),
            expected_schema_hash=old_contract.schema_hash,
        )


@pytest.mark.parametrize(("close_mode", "expected_value"), (("zero", 0), ("missing", None)))
def test_new_feature_preserves_zero_missing_and_excludes_after_cutoff(
    close_mode: str,
    expected_value: int | None,
) -> None:
    added = json.loads((FIXTURES / "new_technical_feature.json").read_text(encoding="utf-8"))
    feature_id = added["added_feature"]["feature_id"]
    snapshot = _synthetic_feature_snapshot()
    cutoff_index = next(
        index
        for index, row in enumerate(snapshot.prices)
        if row.trading_date == snapshot.feature_as_of_date
    )
    prices = list(snapshot.prices)
    cutoff_row = prices[cutoff_index]
    if close_mode == "zero":
        prices[cutoff_index] = replace(
            cutoff_row,
            close_price=prices[cutoff_index - 1].close_price,
        )
    else:
        prices[cutoff_index] = replace(cutoff_row, close_price=None)
    snapshot = replace(snapshot, prices=tuple(prices))
    _, vector, _ = _feature_extension_vectors(snapshot, feature_id=feature_id)

    future_variant_prices = list(snapshot.prices)
    future_row_index = next(
        index
        for index, row in enumerate(future_variant_prices)
        if row.trading_date > snapshot.feature_as_of_date
    )
    future_variant_prices[future_row_index] = replace(
        future_variant_prices[future_row_index],
        close_price=Decimal("123456789"),
    )
    _, future_variant_vector, _ = _feature_extension_vectors(
        replace(snapshot, prices=tuple(future_variant_prices)),
        feature_id=feature_id,
    )

    assert vector.feature_as_of_date == snapshot.feature_as_of_date
    assert vector.values[-1] == expected_value
    assert future_variant_vector == vector


def test_new_strategy_uses_registry_executor_and_preserves_prefix_pit() -> None:
    new_strategy_id = "r030.synthetic_strategy.v1"
    before = tuple(StrategyRegistry.list_strategies())
    existing_baseline = StrategyRegistry.get_executor(
        StrategySpec("baseline_score_threshold", "1.0.0")
    )
    if StrategyRegistry.is_registered(new_strategy_id):
        raise AssertionError("R030 fixture strategy id must be absent before registration")

    with pytest.raises(ValueError, match="未知的策略"):
        StrategyRegistry.get_executor(StrategySpec(new_strategy_id, "1.0.0"))

    try:
        StrategyRegistry.register(new_strategy_id, _SyntheticPrefixExecutor)
        spec = StrategySpec(new_strategy_id, "1.0.0")
        executor = StrategyRegistry.get_executor(spec)
        assert type(executor) is _SyntheticPrefixExecutor
        assert tuple(StrategyRegistry.list_strategies()) == (*before, new_strategy_id)

        dates = pd.date_range("2026-09-01", periods=4, freq="D")
        history = pd.DataFrame(
            {"close_cents": [10_000, 10_100, 9_900, 10_200]},
            index=dates,
        )
        cutoff = dates[2].date().isoformat()
        full = executor.generate_signals(history, spec, execution_start_date=cutoff)
        prefix = executor.generate_signals(
            history.iloc[:3], spec, execution_start_date=cutoff
        )
        changed_future = history.copy()
        changed_future.loc[dates[3], "close_cents"] = 999_999
        future_changed_result = executor.generate_signals(
            changed_future, spec, execution_start_date=cutoff
        )
        projected_columns = ["signal", "score", "reason_tags", "regime_match"]
        pd.testing.assert_frame_equal(
            full.loc[: dates[2], projected_columns], prefix[projected_columns]
        )
        pd.testing.assert_frame_equal(
            full.loc[: dates[2], projected_columns],
            future_changed_result.loc[: dates[2], projected_columns],
        )
        assert tuple(full.loc[: dates[1], "signal"]) == (0, 0)
        assert tuple(full.loc[dates[2] :, "signal"]) == (0, 1)
        assert type(existing_baseline) is BaselineScoreExecutor
    finally:
        StrategyRegistry._registry.pop(new_strategy_id, None)

    assert tuple(StrategyRegistry.list_strategies()) == before
    assert type(
        StrategyRegistry.get_executor(StrategySpec("baseline_score_threshold", "1.0.0"))
    ) is BaselineScoreExecutor
