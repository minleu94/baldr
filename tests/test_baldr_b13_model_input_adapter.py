from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
import hashlib
import json
from typing import Sequence

import pytest

from app_module.rule_research_model_input_adapter import (
    ModelInputFairDenominatorRow,
    ModelInputEvidence,
    ModelInputPathBar,
    ModelInputPolicy,
    ModelInputRunnerResult,
    ModelInputSample,
    ModelInputSourcePin,
    ModelInputTimeSplit,
    PreparedModelInput,
    TrainingPreprocessingAudit,
    build_synthetic_offline_evidence,
    content_sha256,
    prepare_model_input,
    run_prepared_model_input,
    source_pins_sha256,
)
from ml_module.feature_registry import CORE_LONG_HISTORY_FEATURE_REGISTRY
from ml_module.historical_contracts import HistoricalFeatureRow
from ml_module.historical_feature_builder import HistoricalFeatureBuilder
from ml_module.historical_run_report import HistoricalMLShadowRunReport
from ml_module.model_artifact_loader import ShadowModelArtifactLoadResult
from ml_module.model_artifact_manifest import ModelArtifactManifest
from ml_module.shadow_inference_service import OneDateShadowInferenceService


def _digest(payload: bytes) -> str:
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _policy(*, primary_target: str | None = "endpoint_gross_return_bp") -> ModelInputPolicy:
    return ModelInputPolicy(
        primary_target=primary_target,
        horizon_sessions=1,
        split=ModelInputTimeSplit(
            train_start_date="2025-01-01",
            train_end_date="2025-01-01",
            evaluation_start_date="2025-01-04",
            evaluation_end_date="2025-01-04",
            training_as_of_date="2025-01-03",
            label_as_of_date="2025-01-06",
            purge_sessions=2,
            embargo_sessions=1,
        ),
        cost_policy_version="gross-no-cost:v1",
        benchmark_id="none:gross-no-excess",
        price_basis="raw_ohlc_no_corporate_action",
        price_basis_version="b13-endpoint-gross-v1",
        metric="gross_return_bp",
    )


def _path(day0: str, day1: str, close0: str, close1: str) -> tuple[ModelInputPathBar, ...]:
    prices = (Decimal(close0), Decimal(close1))
    return tuple(
        ModelInputPathBar(
            trading_date=day,
            open=price,
            high=price,
            low=price,
            close=price,
            available_date=day,
            state="available",
            corporate_action_status="none",
        )
        for day, price in zip((day0, day1), prices)
    )


def _schema() -> tuple[tuple[str, str, str], ...]:
    return CORE_LONG_HISTORY_FEATURE_REGISTRY.canonical_schema


def _schema_hash(registry_hash: str, schema: tuple[tuple[str, str, str], ...]) -> str:
    payload = {"registry_hash": registry_hash, "canonical_schema": [list(item) for item in schema]}
    return _digest(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode())


def _samples() -> tuple[ModelInputSample, ...]:
    schema = _schema()
    features = tuple((feature_id, index + 1) for index, (feature_id, _, _) in enumerate(schema))
    return (
        ModelInputSample(
            row_id="train-2330-20250101",
            symbol="2330",
            phase="training",
            decision_date="2025-01-01",
            feature_as_of_date="2024-12-31",
            feature_available_date="2024-12-31",
            features=features,
            actual_session_dates=("2025-01-01", "2025-01-02"),
            path=_path("2025-01-01", "2025-01-02", "100", "101"),
            target_value_bp=100,
            horizon_end_date="2025-01-02",
            label_available_date="2025-01-03",
        ),
        ModelInputSample(
            row_id="eval-2330-20250104",
            symbol="2330",
            phase="evaluation",
            decision_date="2025-01-04",
            feature_as_of_date="2025-01-03",
            feature_available_date="2025-01-03",
            features=features,
            actual_session_dates=("2025-01-04", "2025-01-05"),
            path=_path("2025-01-04", "2025-01-05", "100", "102"),
            target_value_bp=200,
            horizon_end_date="2025-01-05",
            label_available_date="2025-01-06",
        ),
    )


def _fair_denominator() -> tuple[ModelInputFairDenominatorRow, ...]:
    rows: list[ModelInputFairDenominatorRow] = []
    for method in ("method-a", "method-b"):
        rows.extend(
            (
                ModelInputFairDenominatorRow(
                    "2330", "2025-01-01", method, "represented", "train-2330-20250101", None
                ),
                ModelInputFairDenominatorRow(
                    "2330", "2025-01-04", method, "represented", "eval-2330-20250104", None
                ),
            )
        )
    rows.extend(
        (
            ModelInputFairDenominatorRow("2331", "2025-01-04", "method-a", "missing", None, "source row absent"),
            ModelInputFairDenominatorRow("2331", "2025-01-04", "method-b", "excluded", None, "quality gate"),
        )
    )
    return tuple(rows)


def _audit() -> TrainingPreprocessingAudit:
    return TrainingPreprocessingAudit(
        fitted_row_ids=("train-2330-20250101",),
        max_available_date="2024-12-31",
        fit_cutoff_date="2025-01-03",
    )


def _prepared(
    *,
    policy: ModelInputPolicy | None = None,
    samples: Sequence[ModelInputSample] | None = None,
    denominator: Sequence[ModelInputFairDenominatorRow] | None = None,
    audit: TrainingPreprocessingAudit | None = None,
) -> PreparedModelInput:
    selected_policy = policy if policy is not None else _policy()
    selected_samples = tuple(samples or _samples())
    selected_denominator = tuple(denominator or _fair_denominator())
    selected_audit = audit if audit is not None else _audit()
    evidence = _evidence(selected_policy, selected_samples, selected_denominator, selected_audit)
    return prepare_model_input(
        selected_policy,
        selected_samples,
        evidence,
        fair_denominator=selected_denominator,
        preprocessing_audit=selected_audit,
    )


def _evidence(
    policy: ModelInputPolicy,
    samples: Sequence[ModelInputSample],
    denominator: Sequence[ModelInputFairDenominatorRow],
    audit: TrainingPreprocessingAudit,
) -> ModelInputEvidence:
    selected_samples = tuple(samples)
    selected_denominator = tuple(denominator)
    schema = _schema()
    builder = HistoricalFeatureBuilder()
    return build_synthetic_offline_evidence(
        policy,
        selected_samples,
        fair_denominator=selected_denominator,
        preprocessing_audit=audit,
        dataset_id="dataset-synthetic-1",
        model_id="model-synthetic-1",
        run_id="run-synthetic-1",
        source_id="source-synthetic-1",
        feature_registry_sha256=builder.load_contract.registry_hash,
        feature_schema_sha256=builder.load_contract.schema_hash,
        feature_schema=schema,
        actual_session_calendar=(
            "2025-01-01", "2025-01-02", "2025-01-03", "2025-01-04", "2025-01-05"
        ),
        model_artifact_bytes=b"synthetic stub bytes; never deserialized",
    )


def _prepare_with_evidence(
    policy: ModelInputPolicy,
    samples: Sequence[ModelInputSample],
    denominator: Sequence[ModelInputFairDenominatorRow],
    audit: TrainingPreprocessingAudit | None,
    evidence: ModelInputEvidence,
) -> PreparedModelInput:
    return prepare_model_input(
        policy,
        samples,
        evidence,
        fair_denominator=denominator,
        preprocessing_audit=audit,
    )


def _assert_rejects_before_runner(prepared: PreparedModelInput) -> None:
    assert prepared.status == "reject_fit"
    runner = _NeverRunner()
    result = run_prepared_model_input(prepared, runner=runner)
    assert result.status == "reject_fit"
    assert runner.calls == 0


class _MemoryRegistry:
    def __init__(self) -> None:
        self.records: list[object] = []

    def append(self, record: object) -> None:
        self.records.append(record)


class _StubPredictor:
    def predict_shadow_bp(self, values: tuple[int, ...]) -> tuple[int, int, int, int]:
        assert len(values) == len(CORE_LONG_HISTORY_FEATURE_REGISTRY.specs)
        return 125, 6500, 1800, 300


class _ExistingRunnerBridge:
    """以合成 DTO 呼叫既有 one-date runner，絕不載入序列化 artifact。"""

    def __init__(self) -> None:
        self.builder = HistoricalFeatureBuilder()
        self.registry = _MemoryRegistry()
        self.service = OneDateShadowInferenceService(self.builder, self.registry)  # type: ignore[arg-type]
        schema = self.builder.load_contract.canonical_schema
        artifact_bytes = b"synthetic stub bytes; never deserialized"
        manifest = ModelArtifactManifest.create(
            model_id="model-synthetic-1",
            dataset_id="dataset-synthetic-1",
            created_run_id="run-synthetic-1",
            created_at="2025-01-03T00:00:00+00:00",
            model_family="core_long_history",
            feature_registry_hash=self.builder.load_contract.registry_hash,
            label_registry_hash=_digest(b"synthetic-label-contract"),
            feature_schema=schema,
            training_as_of="2025-01-03",
            hyperparameters_hash=_digest(b"synthetic-parameters"),
            library_versions={"python": "3.11.9"},
            serialization_format="joblib",
            artifact_filename="synthetic-only.joblib",
            artifact_hash=_digest(artifact_bytes),
        )
        self.artifact = ShadowModelArtifactLoadResult.ready(manifest, _StubPredictor())
        self.report = HistoricalMLShadowRunReport.create(
            run_id="run-synthetic-1",
            dataset_id="dataset-synthetic-1",
            model_id="model-synthetic-1",
            training_end_date="2025-01-03",
            oos_start_date="2025-01-04",
            oos_end_date="2025-01-04",
            accepted_rows=1,
            excluded_rows=0,
            fold_ids=("synthetic-fold",),
            metrics_bp={"mae_bp": 0},
            artifact_hashes={"model": _digest(artifact_bytes)},
            blockers=(),
            evidence_tier="historical_locked_oos",
            result_status="continue_shadow",
        )
        self.calls = 0

    def run(self, prepared: PreparedModelInput) -> ModelInputRunnerResult:
        self.calls += 1
        row = next(sample for sample in prepared.samples if sample.phase == "evaluation")
        feature_row = HistoricalFeatureRow(
            symbol=row.symbol,
            decision_date=row.decision_date,
            feature_as_of_date=row.feature_as_of_date,
            available_date=row.feature_available_date,
            values=row.features,
        )
        result = self.service.run_one_date(
            feature_row=feature_row,
            artifact=self.artifact,
            run_report=self.report,
            source_versions={"fixture": "synthetic-v1"},
            source_versions_hash=_digest(b"synthetic-sources"),
            expected_builder_contract_hash=self.builder.load_contract.contract_hash,
            expected_builder_schema_hash=self.builder.load_contract.schema_hash,
        )
        prediction = result.predictions[0] if result.predictions else None
        source_hash = source_pins_sha256(prepared.evidence.pins)
        blockers = tuple(result.blockers)
        status = "available" if result.status == "shadow_available" and prediction is not None else "unavailable"
        prediction_payload = None if prediction is None else {
            "prediction_id": prediction.prediction_id,
            "symbol": prediction.symbol,
            "return_prediction_bp": prediction.return_prediction_bp,
            "ranking_score_bp": prediction.ranking_score_bp,
            "downside_probability_bp": prediction.downside_probability_bp,
            "uncertainty_bp": prediction.uncertainty_bp,
        }
        payload = json.dumps(
            {
                "schema_version": "baldr-b13-runner-result.v1",
                "prepared_identity_sha256": prepared.identity_sha256,
                "dataset_id": prepared.evidence.dataset_id,
                "model_id": prepared.evidence.model_id,
                "run_id": prepared.evidence.run_id,
                "source_pins_sha256": source_hash,
                "sample_row_id": row.row_id,
                "symbol": row.symbol,
                "decision_date": row.decision_date,
                "status": status,
                "prediction": prediction_payload,
                "blockers": blockers,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return ModelInputRunnerResult(
            status=status,
            prepared_identity_sha256=prepared.identity_sha256,
            dataset_id=prepared.evidence.dataset_id,
            model_id=prepared.evidence.model_id,
            run_id=prepared.evidence.run_id,
            source_pins_sha256=source_hash,
            result_identity_sha256=content_sha256(payload),
            result_payload=payload,
            blockers=blockers,
        )


class _NeverRunner:
    def __init__(self) -> None:
        self.calls = 0

    def run(self, prepared: PreparedModelInput) -> ModelInputRunnerResult:
        self.calls += 1
        raise AssertionError("不合格輸入不可呼叫 runner")


def test_complete_synthetic_contract_reaches_existing_one_date_runner() -> None:
    prepared = _prepared()
    assert prepared.status == "ready"
    assert prepared.independent_sample_count == 2
    assert prepared.evidence.pins[0].namespace == "synthetic://offline"
    assert all(
        getattr(prepared, name) is False
        for name in (
            "formal_eligible", "training_eligible", "historical_pit_eligible",
            "natural_authority", "execution_eligible", "production_action_allowed",
        )
    )

    bridge = _ExistingRunnerBridge()
    result = run_prepared_model_input(prepared, runner=bridge)

    assert bridge.calls == 1
    assert result.status == "available"
    assert result.result_payload is not None
    assert content_sha256(result.result_payload) == result.result_identity_sha256
    assert len(bridge.registry.records) == 1
    payload = json.loads(result.result_payload)
    assert payload["prediction"]["return_prediction_bp"] == 125
    assert payload["prediction"]["downside_probability_bp"] == 1800


def test_unresolved_u2_policy_waits_without_runner_call() -> None:
    prepared = _prepared(policy=_policy(primary_target=None))
    assert prepared.status == "waiting"
    assert "u2_policy_missing:primary_target" in prepared.blockers
    runner = _NeverRunner()
    result = run_prepared_model_input(prepared, runner=runner)
    assert result.status == "waiting"
    assert runner.calls == 0


def test_every_method_must_cover_the_same_fair_denominator_universe() -> None:
    denominator = tuple(
        row for row in _fair_denominator()
        if not (row.symbol == "2331" and row.method_id == "method-b")
    )
    prepared = _prepared(denominator=denominator)
    assert prepared.status == "reject_fit"
    assert "fair_denominator_method_universe_incomplete" in prepared.blockers


def test_more_than_one_evaluation_row_is_rejected_before_runner() -> None:
    samples = _samples()
    second = replace(samples[1], row_id="eval-2332-extra", symbol="2332")
    denominator = (*_fair_denominator(),
        ModelInputFairDenominatorRow("2332", "2025-01-04", "method-a", "represented", second.row_id, None),
        ModelInputFairDenominatorRow("2332", "2025-01-04", "method-b", "represented", second.row_id, None),
    )
    prepared = _prepared(samples=(*samples, second), denominator=denominator)
    assert prepared.status == "reject_fit"
    assert "bounded_runner_requires_exactly_one_evaluation_sample" in prepared.blockers
    runner = _NeverRunner()
    run_prepared_model_input(prepared, runner=runner)
    assert runner.calls == 0


def test_prepared_independent_count_cannot_be_replaced_after_sealing() -> None:
    prepared = _prepared()
    forged = replace(prepared, independent_sample_count=999)
    runner = _NeverRunner()
    result = run_prepared_model_input(forged, runner=runner)
    assert result.status == "reject_fit"
    assert result.blockers == ("prepared_input_revalidation_failed",)
    assert runner.calls == 0


@pytest.mark.parametrize(
    ("downside", "uncertainty", "expected"),
    ((10001, 0, "bounded_runner_downside_probability_out_of_range"),
     (1000, -1, "bounded_runner_uncertainty_negative")),
)
def test_runner_receipt_rejects_invalid_uncertainty_and_probability(
    downside: int, uncertainty: int, expected: str
) -> None:
    prepared = _prepared()

    class BadOutputBridge(_ExistingRunnerBridge):
        def run(self, ready: PreparedModelInput) -> ModelInputRunnerResult:
            valid = super().run(ready)
            payload = json.loads(valid.result_payload)
            payload["prediction"]["downside_probability_bp"] = downside
            payload["prediction"]["uncertainty_bp"] = uncertainty
            encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
            return replace(valid, result_identity_sha256=content_sha256(encoded), result_payload=encoded)

    bridge = BadOutputBridge()
    result = run_prepared_model_input(prepared, runner=bridge)
    assert result.status == "reject_fit"
    assert result.blockers == (expected,)


def test_path_price_mismatch_rejects_even_with_rebuilt_content_pins() -> None:
    rows = _samples()
    invalid_path = (replace(rows[1].path[0], state="halted"), *rows[1].path[1:])
    altered = replace(rows[1], path=invalid_path)
    prepared = _prepared(samples=(rows[0], altered))
    assert prepared.status == "reject_fit"
    assert any(blocker.startswith("price_path_halted:") for blocker in prepared.blockers)


def test_empty_actual_sessions_rejects_without_index_error() -> None:
    rows = _samples()
    changed = replace(rows[1], actual_session_dates=(), path=())
    prepared = _prepared(samples=(rows[0], changed))
    _assert_rejects_before_runner(prepared)
    assert "actual_session_dates_invalid:eval-2330-20250104" in prepared.blockers


@pytest.mark.parametrize("payload", (b"[" * 1100 + b"0" + b"]" * 1100, b'{"value":' + b"1" * 10000 + b"}"))
def test_bounded_but_unparseable_runner_payload_rejects(payload: bytes) -> None:
    class BadJsonBridge(_ExistingRunnerBridge):
        def run(self, ready: PreparedModelInput) -> ModelInputRunnerResult:
            valid = super().run(ready)
            return replace(valid, result_identity_sha256=content_sha256(payload), result_payload=payload)

    result = run_prepared_model_input(_prepared(), runner=BadJsonBridge())
    assert result.status == "reject_fit"
    assert result.blockers == ("bounded_runner_payload_invalid",)


@pytest.mark.parametrize("bad_price", (Decimal("NaN"), Decimal("Infinity"), Decimal("1e999999")))
def test_nonfinite_or_unbounded_decimal_returns_reject_fit(bad_price: Decimal) -> None:
    rows = _samples()
    changed_bar = replace(rows[1].path[0], close=bad_price, high=bad_price)
    altered = replace(rows[1], path=(changed_bar, rows[1].path[1]))
    prepared = _prepared(samples=(rows[0], altered))
    assert prepared.status == "reject_fit"
    assert any(blocker.startswith("ohlc_decimal_missing_or_invalid:") for blocker in prepared.blockers)


@pytest.mark.parametrize("role", (
    "actual_sessions", "custody", "path_label", "source", "model_artifact", "training_audit"
))
def test_changed_role_content_hash_and_pin_are_rejected(role: str) -> None:
    base = _prepared()
    changed_pins: list[ModelInputSourcePin] = []
    for pin in base.evidence.pins:
        if pin.role == role:
            changed_content = pin.content + b"x"
            changed_pins.append(
                replace(pin, content=changed_content, content_sha256=content_sha256(changed_content))
            )
        else:
            changed_pins.append(pin)
    evidence = replace(base.evidence, pins=tuple(changed_pins))
    prepared = _prepare_with_evidence(
        base.policy, base.samples, base.fair_denominator, base.preprocessing_audit, evidence
    )
    _assert_rejects_before_runner(prepared)
    assert any(role in blocker for blocker in prepared.blockers)


def test_model_artifact_metadata_hash_mismatch_is_rejected_before_runner() -> None:
    base = _prepared()
    pins = tuple(
        replace(pin, metadata_sha256=content_sha256(b"different metadata"))
        if pin.role == "model_artifact" else pin
        for pin in base.evidence.pins
    )
    evidence = replace(base.evidence, pins=pins)
    prepared = _prepare_with_evidence(
        base.policy, base.samples, base.fair_denominator, base.preprocessing_audit, evidence
    )
    _assert_rejects_before_runner(prepared)
    assert "evidence_pin_metadata_hash_mismatch:model_artifact" in prepared.blockers


def test_non_synthetic_pin_namespace_waits_without_runner() -> None:
    base = _prepared()
    pins = tuple(
        replace(pin, namespace="external://unverified") if pin.role == "source" else pin
        for pin in base.evidence.pins
    )
    evidence = replace(base.evidence, pins=pins)
    prepared = _prepare_with_evidence(
        base.policy, base.samples, base.fair_denominator, base.preprocessing_audit, evidence
    )
    assert prepared.status == "waiting"
    assert "source_namespace_unqualified" in prepared.blockers
    runner = _NeverRunner()
    result = run_prepared_model_input(prepared, runner=runner)
    assert result.status == "waiting"
    assert runner.calls == 0


def test_feature_schema_hash_mismatch_rejects_before_runner() -> None:
    base = _prepared()
    evidence = replace(base.evidence, feature_schema_sha256=_digest(b"wrong schema"))
    prepared = _prepare_with_evidence(
        base.policy, base.samples, base.fair_denominator, base.preprocessing_audit, evidence
    )
    _assert_rejects_before_runner(prepared)
    assert "feature_schema_hash_mismatch" in prepared.blockers


@pytest.mark.parametrize(
    ("field", "value", "blocker"),
    (("purge_sessions", 3, "purge_gap_shorter_than_declared"),
     ("embargo_sessions", 2, "embargo_gap_shorter_than_declared")),
)
def test_purge_and_embargo_must_match_actual_calendar_spacing(
    field: str, value: int, blocker: str
) -> None:
    policy = _policy()
    assert policy.split is not None
    changed_split = replace(policy.split, **{field: value})
    prepared = _prepared(policy=replace(policy, split=changed_split))
    _assert_rejects_before_runner(prepared)
    assert blocker in prepared.blockers


def test_training_label_must_be_mature_by_training_as_of() -> None:
    samples = _samples()
    changed_train = replace(samples[0], label_available_date="2025-01-04")
    prepared = _prepared(samples=(changed_train, samples[1]))
    _assert_rejects_before_runner(prepared)
    assert any(blocker.startswith("training_label_not_mature_at_training_as_of:") for blocker in prepared.blockers)


def test_feature_availability_at_decision_date_is_not_t_minus_one() -> None:
    samples = _samples()
    changed_eval = replace(samples[1], feature_available_date=samples[1].decision_date)
    prepared = _prepared(samples=(samples[0], changed_eval))
    _assert_rejects_before_runner(prepared)
    assert any(blocker.startswith("feature_cutoff_or_availability_violation:") for blocker in prepared.blockers)


@pytest.mark.parametrize(
    ("audit", "blocker"),
    ((TrainingPreprocessingAudit(
        fitted_row_ids=("train-2330-20250101", "eval-2330-20250104"),
        max_available_date="2025-01-03",
        fit_cutoff_date="2025-01-03",
    ), "preprocessing_fit_rows_not_exact_training_rows"),
     (TrainingPreprocessingAudit(
        fitted_row_ids=("train-2330-20250101",),
        max_available_date="2024-12-31",
        fit_cutoff_date="2025-01-04",
    ), "preprocessing_cutoff_after_training_as_of")),
)
def test_preprocessing_audit_rejects_evaluation_rows_and_late_cutoff(
    audit: TrainingPreprocessingAudit, blocker: str
) -> None:
    prepared = _prepared(audit=audit)
    _assert_rejects_before_runner(prepared)
    assert blocker in prepared.blockers


def test_duplicate_instrument_and_decision_date_is_not_two_samples() -> None:
    samples = _samples()
    duplicate = replace(samples[1], row_id="eval-2330-duplicate")
    prepared = _prepared(samples=(*samples, duplicate))
    _assert_rejects_before_runner(prepared)
    assert "same_symbol_date_sample_not_deduplicated:2330:2025-01-04" in prepared.blockers


@pytest.mark.parametrize(
    ("field", "value", "blocker_prefix"),
    (("state", "missing", "price_path_missing:"),
     ("corporate_action_status", "unknown", "corporate_action_unknown:")),
)
def test_missing_path_or_unknown_corporate_action_rejects_before_runner(
    field: str, value: str, blocker_prefix: str
) -> None:
    samples = _samples()
    first_bar = replace(samples[1].path[1], **{field: value})
    changed = replace(samples[1], path=(samples[1].path[0], first_bar))
    prepared = _prepared(samples=(samples[0], changed))
    _assert_rejects_before_runner(prepared)
    assert any(blocker.startswith(blocker_prefix) for blocker in prepared.blockers)


@pytest.mark.parametrize("field", (
    "primary_target", "horizon_sessions", "split", "cost_policy_version",
    "benchmark_id", "price_basis", "price_basis_version", "metric",
))
def test_each_missing_u2_policy_declaration_waits_without_runner(field: str) -> None:
    policy = replace(_policy(), **{field: None})
    prepared = _prepared(policy=policy)
    assert prepared.status == "waiting"
    assert f"u2_policy_missing:{field}" in prepared.blockers
    runner = _NeverRunner()
    result = run_prepared_model_input(prepared, runner=runner)
    assert result.status == "waiting"
    assert runner.calls == 0
