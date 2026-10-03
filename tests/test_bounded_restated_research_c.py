from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from dataclasses import replace
from decimal import Decimal
import hashlib
import json
import gzip
from pathlib import Path
from types import SimpleNamespace
import subprocess
import sys
import os

import numpy as np
import pytest
from sklearn.pipeline import Pipeline

from ml_module.allocation_training_service import (
    AllocationTrainingService,
    FeaturePackDefinition,
    _restated_outcome_matrix,
)
from ml_module.current_restated_research_bridge import (
    CurrentRestatedInputFilePin,
    CurrentRestatedFeature,
    CurrentRestatedOutcomeLabel,
    CurrentRestatedResearchRow,
    CurrentRestatedResearchSample,
    VerifiedCurrentRestatedBVectorBridge,
    capture_current_restated_training_code_pins,
    save_verified_current_restated_context_file,
    load_verified_current_restated_context_file,
    save_current_restated_outcome_model,
    load_current_restated_outcome_model,
    predict_current_restated_outcomes,
    convert_current_restated_turnover_twd_to_minor,
    _quantize_model_bp,
    _build_current_restated_market_observations,
    _load_verified_current_restated_market_history,
    CurrentRestatedResearchInvocation,
    CurrentRestatedSavedModel,
    verify_current_restated_legacy_terminal_receipt,
    _normalize_direct_feature_carrier,
)
from ml_module.purged_walk_forward import MLTimeWindowRow, PurgedWalkForwardFold
from data_module.ml_historical_snapshot_provider import (
    HistoricalIndexObservation,
    HistoricalPriceObservation,
    HistoricalRawSnapshot,
    HistoricalTechnicalObservation,
)
from ml_module.feature_registry import CORE_LONG_HISTORY_FEATURE_REGISTRY
from ml_module.historical_feature_builder import (
    CURRENT_RESTATED_CORE19_FEATURE_IDS,
    HistoricalFeatureBuilder,
    compute_current_restated_core19_projection,
)
from data_module.ml_research_output_boundary import resolve_ml_research_output_path
from data_module.portfolio_ml_current_restated_outcome_store import (
    CurrentRestatedOutcomeCostContractV1,
    CurrentRestatedOutcomeFeatureV1,
    VerifiedCurrentRestatedOutcomeArtifact,
)
from data_module.ml_daily_price_revision_gate import load_verified_current_restated_source_context
import data_module.ml_research_output_boundary as research_boundary
import ml_module.current_restated_research_bridge as research_bridge
from tests.ml_research_test_support import install_test_revision_gate, write_snapshot_context_receipt


_SOURCE_OBSERVED = "2026-10-03T00:23:25.887429+00:00"
_TRAINING_FREEZE = "2026-10-03T01:30:00+00:00"
_FEATURE_ID = "daily_prices.close"
_PACK = FeaturePackDefinition("core_close", (_FEATURE_ID,))
_SOURCE_HASH = "sha256:" + hashlib.sha256(b"representative source value").hexdigest()


def _sample(
    index: int,
    *,
    label_observed: bool = True,
    feature_missing: bool = False,
) -> CurrentRestatedResearchSample:
    event_date = date(2023, 1, 1) + timedelta(days=index)
    feature = CurrentRestatedFeature(
        feature_id=_FEATURE_ID,
        value_int=None if feature_missing else 250000 + index * 13,
        scale=2,
        observed=not feature_missing,
        event_at=event_date.isoformat(),
        source_available_at=None,
        source_observed_at=_SOURCE_OBSERVED,
        current_value_available_at=_SOURCE_OBSERVED,
        source_value_hash=_SOURCE_HASH,
        source_value_hash_semantics="verified_direct_store_value_bytes",
    )
    label = CurrentRestatedOutcomeLabel(
        horizon_trading_days=5,
        horizon_end_date=(event_date + timedelta(days=5)).isoformat(),
        available_at=_SOURCE_OBSERVED if label_observed else None,
        benchmark_excess_return_bp=((index % 31) - 15) * 7 if label_observed else None,
        observed=label_observed,
        source_available_at=None,
        source_observed_at=_SOURCE_OBSERVED,
        label_value_hash=_SOURCE_HASH,
    )
    row = CurrentRestatedResearchRow(
        row_id=f"row-{index:04d}",
        symbol="2330",
        event_date=event_date.isoformat(),
        event_at=event_date.isoformat(),
        features=(feature,),
        missing_mask=(_FEATURE_ID,) if feature_missing else (),
        quality_blocked_mask=(),
        source_observed_at=_SOURCE_OBSERVED,
    )
    return CurrentRestatedResearchSample(row=row, horizon_labels=(label,))


def _folds(samples: tuple[CurrentRestatedResearchSample, ...]) -> tuple[PurgedWalkForwardFold, ...]:
    folds: list[PurgedWalkForwardFold] = []
    for fold_index, test_start_index in enumerate((185, 253, 321, 389), 1):
        train = tuple(
            MLTimeWindowRow(
                row_id=sample.row.row_id,
                decision_date=sample.row.event_date,
                label_end_date=sample.horizon_labels[0].horizon_end_date,
            )
            for sample in samples[: test_start_index - 60]
        )
        test_samples = samples[test_start_index : test_start_index + 63]
        test = tuple(
            MLTimeWindowRow(
                row_id=sample.row.row_id,
                decision_date=sample.row.event_date,
                label_end_date=sample.horizon_labels[0].horizon_end_date,
            )
            for sample in test_samples
        )
        folds.append(
            PurgedWalkForwardFold(
                fold_id=f"fold-{fold_index:03d}",
                train_rows=train,
                test_rows=test,
                test_start=test[0].decision_date,
                test_end=test[-1].decision_date,
                purge_days=60,
                embargo_days=5,
            )
        )
    return tuple(folds)


def _event_calendar(samples: tuple[CurrentRestatedResearchSample, ...]) -> tuple[str, ...]:
    return tuple(sorted({sample.row.event_date for sample in samples}))


def test_current_restated_outcome_fit_reuses_pure_regressor_without_teacher() -> None:
    samples = tuple(
        _sample(
            index,
            label_observed=index != 200,
            feature_missing=index == 0,
        )
        for index in range(905)
    )
    result = AllocationTrainingService(random_state=7).fit_current_restated_outcome_only(
        samples=samples,
        feature_packs=(_PACK,),
        folds=_folds(samples),
        training_as_of=_TRAINING_FREEZE,
        dataset_manifest_file_hash=_SOURCE_HASH,
        event_date_calendar=_event_calendar(samples),
    )
    assert result.audit["status"] == "verified_base_outcome_only"
    assert result.audit["historical_pit"] is False
    assert result.audit["formal_oos_allowed"] is False
    assert result.audit["full_allocation_status"] == "blocked_full_allocation_teacher_unavailable"
    assert result.audit["production_alpha_bp"] == 0
    assert result.audit["production_action_allowed"] is False
    assert result.audit["target_heads"] == ["benchmark_excess_return_bp"]
    assert "AllocationTargets" not in result.audit["target_heads"]
    assert len(result.audit["folds"]) == 4
    assert len(result.audit["oof_predictions"]) == 4 * 63
    missing_test_label = next(
        row for row in result.audit["oof_predictions"] if row["row_id"] == "row-0200"
    )
    assert missing_test_label["observed_label"] is False
    assert missing_test_label["actual_excess_return_bp"] is None
    assert set(result.models) == {"final|core_close|h5|ridge_logistic"}
    assert isinstance(result.models["final|core_close|h5|ridge_logistic"], Pipeline)
    assert result.audit["dataset_manifest_file_hash"] == _SOURCE_HASH.removeprefix("sha256:")


def test_core19_fit_bridge_prefixes_direct_receipt_sha_through_fit_and_save_spy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = tmp_path / "synthetic-repository"
    research_root = repository / "output" / "ml_research"
    research_root.mkdir(parents=True)

    def test_resolver(path: Path) -> Path:
        return resolve_ml_research_output_path(path, repository_root=repository)

    monkeypatch.setattr(research_bridge, "resolve_ml_research_output_path", test_resolver)
    install_test_revision_gate(monkeypatch)
    snapshot_path = research_root / "snapshot" / "source.sqlite"
    snapshot_path.parent.mkdir()
    snapshot_path.write_bytes(b"synthetic fit-bridge snapshot")
    source_receipt_path, source_receipt_sha = write_snapshot_context_receipt(
        snapshot_path,
        tmp_path,
        completed_at="2026-10-03T00:23:25.887429+00:00",
    )
    context_now = datetime.now(timezone.utc)
    source_context = load_verified_current_restated_source_context(
        snapshot_path,
        source_receipt_path,
        expected_snapshot_database_sha256=hashlib.sha256(snapshot_path.read_bytes()).hexdigest(),
        expected_snapshot_receipt_sha256=source_receipt_sha,
        original_database_path=tmp_path / "source_context" / "original_source.sqlite",
        decision_at=context_now - timedelta(seconds=2),
        training_as_of=context_now - timedelta(seconds=1),
    )
    context_path, context_sha = save_verified_current_restated_context_file(
        source_context,
        output_path=research_root / "shared-source-context.json",
        fit_cutoff=(datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat(),
    )
    context_file = load_verified_current_restated_context_file(
        context_path,
        expected_context_sha256=context_sha,
    )

    direct_root = research_root / "direct"
    direct_root.mkdir()
    direct_manifest_path = direct_root / "manifest.json"
    direct_context_payload = research_bridge._source_context_plain_payload(source_context)
    direct_context_payload["source_revision_evidence"] = {
        "digest_sha256": source_context.source_revision_evidence_sha256,
        "cutoff_date": source_context.source_revision_evidence_cutoff_date,
        "schema_version": source_context.source_revision_evidence_schema_version,
        "scope_id": source_context.source_revision_evidence_scope_id,
    }
    context_bundle_sha = hashlib.sha256(
        research_bridge._canonical_json_bytes(direct_context_payload)
    ).hexdigest()
    direct_manifest_payload = {
        "schema_version": "portfolio-ml-current-restated-outcome-store.v1",
        "status": "current_restated_outcome_numeric_ready",
        "revision_dependency_bundle_sha256": source_context.revision_dependency_bundle_sha256,
        "source_context_revalidation": direct_context_payload,
        "source_pins": {"revalidated_context_bundle_sha256": context_bundle_sha},
    }
    direct_manifest_bytes = research_bridge._canonical_json_bytes(direct_manifest_payload) + b"\n"
    direct_manifest_path.write_bytes(direct_manifest_bytes)
    direct_manifest_sha = hashlib.sha256(direct_manifest_bytes).hexdigest()
    from data_module.portfolio_ml_current_restated_outcome_store import (
        CurrentRestatedOutcomeCostContractV1,
    )

    direct_artifact = VerifiedCurrentRestatedOutcomeArtifact(
        status="current_restated_outcome_numeric_ready",
        observations=(),
        feature_registry=(),
        feature_registry_sha256="a" * 64,
        labels_registry=("benchmark_excess_return_bp",),
        outcome_cost_contract=CurrentRestatedOutcomeCostContractV1(
            **research_bridge._expected_outcome_cost_contract_payload()
        ),
        raw_publication_manifest_path=str(direct_manifest_path),
        raw_publication_manifest_bytes_sha256=direct_manifest_sha,
        raw_dataset_manifest_path=str(direct_manifest_path),
        raw_dataset_manifest_bytes_sha256=direct_manifest_sha,
        artifact_receipt_path=str(direct_manifest_path),
        artifact_receipt_bytes_sha256=direct_manifest_sha,
        run_id="synthetic-fit-bridge-run",
        array_pins=(),
        raw_shard_pins=(),
        source_database_path=source_context.source_database_path,
        source_database_sha256=source_context.source_database_sha256,
        snapshot_database_path=source_context.snapshot_database_path,
        snapshot_database_sha256=source_context.snapshot_database_sha256,
        snapshot_receipt_path=source_context.snapshot_receipt_path,
        snapshot_receipt_sha256=source_context.snapshot_receipt_sha256,
        source_observed_at=source_context.source_observed_at,
        revision_dependencies_verified_at=source_context.revision_dependencies_verified_at,
        raw_revision_dependencies_verified_at=source_context.revision_dependencies_verified_at,
        revision_dependency_bundle_sha256=source_context.revision_dependency_bundle_sha256,
        raw_generated_at=source_context.source_observed_at,
        current_observation_freeze=source_context.source_observed_at,
        artifact_available_at=datetime.now(timezone.utc) - timedelta(milliseconds=1),
        target_symbols=("2317", "2330"),
        benchmark_entity_id="benchmark/market_indices.收盤指數",
        horizons=(5, 10, 20, 60),
        event_date_calendar=(),
        event_date_calendar_sha256="b" * 64,
        folds=(),
    )

    samples = tuple(_sample(index) for index in range(905))
    event_calendar = _event_calendar(samples)
    folds = _folds(samples)
    from ml_module.historical_feature_builder import CURRENT_RESTATED_CORE19_FEATURE_IDS

    prepared = SimpleNamespace(
        samples=samples,
        rows_by_symbol_date={},
        feature_registry=tuple(
            {"feature_id": feature_id, "unit": "bp", "scale": 0}
            for feature_id in CURRENT_RESTATED_CORE19_FEATURE_IDS
        ),
        feature_packs=(_PACK,),
        folds=folds,
        event_date_calendar=event_calendar,
        excluded_unusable_row_count=0,
        derived_at=datetime.now(timezone.utc).isoformat(),
        outcome_cost_contract=research_bridge._expected_outcome_cost_contract_payload(),
    )
    monkeypatch.setattr(
        research_bridge,
        "prepare_verified_current_restated_core19_dataset",
        lambda _artifact: prepared,
    )
    b_receipt_path = research_root / "inputs" / "b-consumption.json"
    b_receipt_path.parent.mkdir()
    b_receipt_bytes = b'{"schema_version":"synthetic-b-receipt.v1"}'
    b_receipt_path.write_bytes(b_receipt_bytes)
    b_receipt_sha = hashlib.sha256(b_receipt_bytes).hexdigest()
    b_bridge = VerifiedCurrentRestatedBVectorBridge(
        event_date="2026-10-02",
        vectors_by_symbol={},
        b_consumption_receipt_sha256=b_receipt_sha,
        b_candidate_manifest_sha256="c" * 64,
        b_adapted_manifest_sha256="d" * 64,
        b_feature_registry_sha256="e" * 64,
        payload={},
        payload_sha256="f" * 64,
    )
    monkeypatch.setattr(research_bridge, "verify_b_current_vector_against_core19", lambda **_kwargs: b_bridge)
    monkeypatch.setattr(research_bridge, "_verified_direct_artifact_input_pins", lambda _artifact: ())

    with pytest.raises(ValueError, match="dataset_manifest_file_hash must be a sha256: digest"):
        AllocationTrainingService(random_state=42).fit_current_restated_outcome_only(
            samples=(),
            feature_packs=(),
            folds=(),
            training_as_of=datetime.now(timezone.utc).isoformat(),
            dataset_manifest_file_hash=direct_manifest_sha,
            event_date_calendar=(),
        )

    service_calls: list[dict[str, object]] = []
    estimator_calls: list[str] = []
    original_fit = AllocationTrainingService.fit_current_restated_outcome_only

    def capture_fit(self: AllocationTrainingService, **kwargs: object) -> object:
        service_calls.append(dict(kwargs))
        return original_fit(self, **kwargs)  # type: ignore[arg-type]

    class ZeroPredictionEstimator:
        def predict(self, matrix: object) -> np.ndarray:
            return np.zeros(len(matrix), dtype=np.float64)  # type: ignore[arg-type]

    def mock_estimator_fit(
        _self: AllocationTrainingService,
        *,
        algorithm: str,
        x: object,
        target: object,
    ) -> ZeroPredictionEstimator:
        del x, target
        estimator_calls.append(algorithm)
        return ZeroPredictionEstimator()

    monkeypatch.setattr(
        AllocationTrainingService,
        "fit_current_restated_outcome_only",
        capture_fit,
    )
    monkeypatch.setattr(AllocationTrainingService, "_fit_regression_model", mock_estimator_fit)
    save_calls: list[dict[str, object]] = []
    saved_model = CurrentRestatedSavedModel(
        manifest_path=research_root / "models" / "mock-fit" / "manifest.json",
        manifest_sha256="1" * 64,
        model_bundle_sha256="2" * 64,
        model_keys=("final|core_close|h5|ridge_logistic",),
        target_contract={},
    )

    def save_spy(**kwargs: object) -> CurrentRestatedSavedModel:
        save_calls.append(dict(kwargs))
        return saved_model

    monkeypatch.setattr(research_bridge, "save_current_restated_outcome_model", save_spy)
    progress: dict[str, bool] = {}
    cutoff_before = datetime.now(timezone.utc)
    run = research_bridge.fit_and_save_verified_current_restated_core19_model(
        direct_artifact=direct_artifact,
        source_context_file=context_file,
        b_artifact=SimpleNamespace(),
        b_consumption_receipt_path=b_receipt_path,
        expected_b_consumption_receipt_sha256=b_receipt_sha,
        expected_b_candidate_manifest_sha256="c" * 64,
        expected_b_adapted_manifest_sha256="d" * 64,
        expected_b_feature_registry_sha256="e" * 64,
        current_symbols=("2317", "2330"),
        current_event_date="2026-10-02",
        output_directory=research_root / "models" / "mock-fit",
        actual_invocation=("synthetic-mock-fit-bridge",),
        fit_progress=progress,
    )
    cutoff_after = datetime.now(timezone.utc)

    assert len(service_calls) == 1
    fit_kwargs = service_calls[0]
    assert fit_kwargs["dataset_manifest_file_hash"] == "sha256:" + direct_manifest_sha
    assert fit_kwargs["horizons"] == (5,)
    assert fit_kwargs["algorithms"] == ("ridge_logistic",)
    assert fit_kwargs["minimum_train_dates"] == 125
    assert fit_kwargs["minimum_test_dates"] == 63
    assert fit_kwargs["minimum_purge_days"] == 60
    assert fit_kwargs["minimum_embargo_days"] == 5
    assert len(fit_kwargs["event_date_calendar"]) == 905  # type: ignore[arg-type]
    fit_cutoff = datetime.fromisoformat(str(fit_kwargs["training_as_of"]))
    assert cutoff_before <= fit_cutoff <= cutoff_after
    assert len(estimator_calls) == 5  # 四個 fold 加一個 final head；皆由 mock 取代
    assert progress == {"started": True, "completed": True}
    assert len(save_calls) == 1
    assert save_calls[0]["expected_direct_manifest_sha256"] == direct_manifest_sha
    assert run.saved_model is saved_model
    assert run.fit_result.audit["dataset_manifest_file_hash"] == direct_manifest_sha
    assert run.fit_result.audit["status"] == "verified_base_outcome_only"
    assert run.fit_result.audit["target_heads"] == ["benchmark_excess_return_bp"]
    assert run.fit_result.audit["formal_oos_allowed"] is False
    assert run.fit_result.audit["production_action_allowed"] is False
    assert run.fit_result.audit["full_allocation_status"] == "blocked_full_allocation_teacher_unavailable"
    qualification = run.fit_result.audit["current_restated_verified_fold_qualification"]
    assert qualification["direct_manifest_sha256"] == direct_manifest_sha
    assert qualification["event_date_calendar_count"] == 905
    assert qualification["minimum_qualified_fold_count"] == 4
    assert len(qualification["folds"]) == 4
    assert run.fit_result.audit["fit_selection"]["horizons"] == [5]
    assert run.fit_result.audit["fit_selection"]["algorithms"] == ["ridge_logistic"]


def test_current_restated_fit_preflights_actual_purge_and_embargo_before_any_fit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    samples = tuple(_sample(index) for index in range(500))
    baseline = _folds(samples)
    service = AllocationTrainingService(random_state=7)

    def must_not_fit(*_args: object, **_kwargs: object) -> object:
        pytest.fail("fold validation must finish before the first estimator fit")

    monkeypatch.setattr(AllocationTrainingService, "_fit_regression_model", must_not_fit)
    first = baseline[0]
    short_purge_train = tuple(
        sorted(
            first.train_rows + (MLTimeWindowRow(
                row_id=samples[179].row.row_id,
                decision_date=samples[179].row.event_date,
                label_end_date=samples[179].horizon_labels[0].horizon_end_date,
            ),),
            key=lambda row: (row.decision_date, row.row_id),
        )
    )
    short_purge_fold = replace(first, train_rows=short_purge_train, purge_days=60)
    with pytest.raises(ValueError, match="actual observed-date purge"):
        service.fit_current_restated_outcome_only(
            samples=samples,
            feature_packs=(_PACK,),
            folds=(short_purge_fold, *baseline[1:]),
            training_as_of=_TRAINING_FREEZE,
            dataset_manifest_file_hash=_SOURCE_HASH,
            event_date_calendar=_event_calendar(samples),
        )

    second = baseline[1]
    short_embargo_test_rows = tuple(
        MLTimeWindowRow(
            row_id=samples[index].row.row_id,
            decision_date=samples[index].row.event_date,
            label_end_date=samples[index].horizon_labels[0].horizon_end_date,
        )
        for index in range(252, 315)
    )
    short_embargo_fold = replace(
        second,
        train_rows=second.train_rows[:-1],
        test_rows=short_embargo_test_rows,
        test_start=samples[252].row.event_date,
        test_end=samples[314].row.event_date,
        purge_days=60,
        embargo_days=5,
    )
    with pytest.raises(ValueError, match="actual observed-date embargo"):
        service.fit_current_restated_outcome_only(
            samples=samples,
            feature_packs=(_PACK,),
            folds=(baseline[0], short_embargo_fold, *baseline[2:]),
            training_as_of=_TRAINING_FREEZE,
            dataset_manifest_file_hash=_SOURCE_HASH,
            event_date_calendar=_event_calendar(samples),
        )


def test_restated_model_boundary_uses_decimal_exponent_and_keeps_original_clock_unknown() -> None:
    sample = _sample(0)
    matrix = _restated_outcome_matrix((sample,), pack=_PACK, algorithm="ridge_logistic")
    assert matrix[0, 0] == 2500.0
    feature = sample.row.features[0]
    assert feature.source_available_at is None
    assert feature.source_observed_at == _SOURCE_OBSERVED
    assert feature.current_value_available_at == _SOURCE_OBSERVED
    assert sample.row.event_date == "2023-01-01"
    assert sample.historical_pit is False


def test_restated_feature_scale_contract_matches_verified_numeric_loader_range() -> None:
    base = _sample(0).row.features[0]
    scale_18 = CurrentRestatedFeature(
        feature_id=_FEATURE_ID,
        value_int=1,
        scale=18,
        observed=True,
        event_at=base.event_at,
        source_available_at=None,
        source_observed_at=_SOURCE_OBSERVED,
        current_value_available_at=_SOURCE_OBSERVED,
        source_value_hash=_SOURCE_HASH,
        source_value_hash_semantics="verified_direct_store_value_bytes",
    )
    assert scale_18.scale == 18
    with pytest.raises(ValueError, match="0..18"):
        CurrentRestatedFeature(
            feature_id=_FEATURE_ID,
            value_int=1,
            scale=19,
            observed=True,
            event_at=base.event_at,
            source_available_at=None,
            source_observed_at=_SOURCE_OBSERVED,
            current_value_available_at=_SOURCE_OBSERVED,
            source_value_hash=_SOURCE_HASH,
            source_value_hash_semantics="verified_direct_store_value_bytes",
        )


def test_quality_blocked_observation_is_masked_at_model_boundary() -> None:
    sample = _sample(0)
    blocked_row = replace(sample.row, quality_blocked_mask=(_FEATURE_ID,))
    blocked_sample = replace(sample, row=blocked_row)

    ridge_matrix = _restated_outcome_matrix(
        (blocked_sample,), pack=_PACK, algorithm="ridge_logistic"
    )
    hgb_matrix = _restated_outcome_matrix(
        (blocked_sample,), pack=_PACK, algorithm="hist_gradient_boosting"
    )

    assert np.isnan(ridge_matrix[0, 0])
    assert np.isnan(hgb_matrix[0, 0])
    assert hgb_matrix[0, 1] == 1.0


def test_stale_observation_is_masked_at_model_boundary() -> None:
    sample = _sample(0)
    stale_feature = replace(sample.row.features[0], stale=True)
    stale_row = replace(
        sample.row,
        features=(stale_feature,),
        staleness_mask=(_FEATURE_ID,),
    )
    stale_sample = replace(sample, row=stale_row)

    ridge_matrix = _restated_outcome_matrix(
        (stale_sample,), pack=_PACK, algorithm="ridge_logistic"
    )
    hgb_matrix = _restated_outcome_matrix(
        (stale_sample,), pack=_PACK, algorithm="hist_gradient_boosting"
    )

    assert np.isnan(ridge_matrix[0, 0])
    assert np.isnan(hgb_matrix[0, 0])
    assert hgb_matrix[0, 1] == 1.0


def test_current_restated_turnover_unit_crosswalk_is_explicit_and_integral() -> None:
    assert convert_current_restated_turnover_twd_to_minor(
        7_654_181_137,
        decimal_exponent=0,
        source_unit="TWD",
    ) == 765_418_113_700
    assert convert_current_restated_turnover_twd_to_minor(
        1,
        decimal_exponent=2,
        source_unit="TWD",
    ) == 1
    with pytest.raises(ValueError, match="corrected TWD"):
        convert_current_restated_turnover_twd_to_minor(
            7_654_181_137,
            decimal_exponent=0,
            source_unit="currency_minor",
        )
    with pytest.raises(ValueError, match="integer minor unit"):
        convert_current_restated_turnover_twd_to_minor(
            1,
            decimal_exponent=3,
            source_unit="TWD",
        )
    actual_raw_rows = (
        ("2317", "2026-01-02", 13_613_204_429, 1_361_320_442_900),
        ("2317", "2026-10-02", 7_654_181_137, 765_418_113_700),
        ("2330", "2026-01-02", 62_469_965_712, 6_246_996_571_200),
        ("2330", "2026-10-02", 39_508_159_297, 3_950_815_929_700),
    )
    for _symbol, _event_date, amount_twd, expected_minor in actual_raw_rows:
        assert convert_current_restated_turnover_twd_to_minor(
            amount_twd,
            decimal_exponent=0,
            source_unit="TWD",
        ) == expected_minor


def test_direct_missing_carrier_normalizes_only_verified_canonical_zero() -> None:
    assert _normalize_direct_feature_carrier(
        0,
        missing=True,
        quality_blocked=False,
        stale=False,
        feature_id="stock/daily_prices.收盤價",
    ) == (None, False, False, True)
    assert _normalize_direct_feature_carrier(
        0,
        missing=False,
        quality_blocked=False,
        stale=False,
        feature_id="stock/daily_prices.成交股數",
    ) == (0, False, False, False)
    assert _normalize_direct_feature_carrier(
        17,
        missing=False,
        quality_blocked=True,
        stale=True,
        feature_id="stock/daily_prices.成交金額",
    ) == (17, True, True, False)
    assert _normalize_direct_feature_carrier(
        0,
        missing=True,
        quality_blocked=True,
        stale=True,
        feature_id="stock/technical_indicators.RSI",
    ) == (None, True, True, True)

    invalid_carriers = (
        (1, True),
        (-1, True),
        (True, False),
        (None, True),
        (1.0, False),
        (2**63, False),
        (-(2**63) - 1, True),
    )
    for carrier, missing in invalid_carriers:
        with pytest.raises(ValueError):
            _normalize_direct_feature_carrier(
                carrier,
                missing=missing,
                quality_blocked=False,
                stale=False,
                feature_id="stock/daily_prices.收盤價",
            )
    for flag_kwargs in (
        {"missing": 1, "quality_blocked": False, "stale": False},
        {"missing": False, "quality_blocked": 0, "stale": False},
        {"missing": False, "quality_blocked": False, "stale": 1},
    ):
        with pytest.raises(ValueError, match="strict booleans"):
            _normalize_direct_feature_carrier(
                0,
                **flag_kwargs,
                feature_id="stock/daily_prices.收盤價",
            )


def test_published_raw_turnover_registry_uses_strict_scale_abi(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = tmp_path / "research-repository"
    raw_root = repository / "output" / "ml_research" / "fixture"
    raw_root.mkdir(parents=True)

    def test_resolver(path: Path) -> Path:
        return resolve_ml_research_output_path(path, repository_root=repository)

    monkeypatch.setattr(research_bridge, "resolve_ml_research_output_path", test_resolver)
    actual_published_descriptor = {
        "column_name": "成交金額",
        "eligibility_status": "formal_backfill",
        "family": "price_liquidity_technical",
        "feature_id": "daily_prices.成交金額",
        "formal_training_eligible": False,
        "record_hash": "sha256:" + hashlib.sha256(b"published registry descriptor").hexdigest(),
        "scale": 0,
        "source_id": "sqlite.daily_prices",
        "source_scale_denominator": 1,
        "staleness_days": 7,
        "table_name": "daily_prices",
        "unit": "TWD",
        "unit_contract": "tw-daily-price-transaction-amount-twd.v1",
    }

    def write_manifest(name: str, descriptor: dict[str, object]) -> SimpleNamespace:
        path = raw_root / name
        raw = json.dumps(
            {"schema_version": "ml-current-restated-year-shard-dataset.v1", "features": [descriptor]},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        path.write_bytes(raw)
        return SimpleNamespace(
            raw_dataset_manifest_path=str(path),
            raw_dataset_manifest_bytes_sha256=hashlib.sha256(raw).hexdigest(),
        )

    accepted = write_manifest("published-shape.json", actual_published_descriptor)
    research_bridge._verify_current_restated_twd_turnover_contract(accepted)

    invalid_descriptors: tuple[tuple[str, str, object], ...] = (
        ("boolean-scale.json", "scale", True),
        ("wrong-scale.json", "scale", 1),
        ("boolean-denominator.json", "source_scale_denominator", True),
        ("wrong-denominator.json", "source_scale_denominator", 100),
        ("wrong-source-id.json", "source_id", "derived:daily_prices"),
        ("wrong-table.json", "table_name", "derived_daily_prices"),
        ("wrong-column.json", "column_name", "成交股數"),
        ("wrong-unit.json", "unit", "currency_minor"),
        ("wrong-contract.json", "unit_contract", "legacy.currency_minor.v1"),
    )
    for filename, field, invalid_value in invalid_descriptors:
        descriptor = dict(actual_published_descriptor)
        descriptor[field] = invalid_value
        artifact = write_manifest(filename, descriptor)
        with pytest.raises(ValueError, match="verified TWD unit contract"):
            research_bridge._verify_current_restated_twd_turnover_contract(artifact)

    duplicate = write_manifest(
        "duplicate.json",
        actual_published_descriptor,
    )
    duplicate_payload = {
        "schema_version": "ml-current-restated-year-shard-dataset.v1",
        "features": [actual_published_descriptor, actual_published_descriptor],
    }
    duplicate_bytes = json.dumps(
        duplicate_payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    duplicate_path = Path(duplicate.raw_dataset_manifest_path)
    duplicate_path.write_bytes(duplicate_bytes)
    duplicate = SimpleNamespace(
        raw_dataset_manifest_path=str(duplicate_path),
        raw_dataset_manifest_bytes_sha256=hashlib.sha256(duplicate_bytes).hexdigest(),
    )
    with pytest.raises(ValueError, match="verified TWD unit contract"):
        research_bridge._verify_current_restated_twd_turnover_contract(duplicate)


def test_current_restated_core19_projection_reuses_decimal_formulas_without_pit_row() -> None:
    prices = tuple(
        HistoricalPriceObservation(
            symbol="2330",
            trading_date=f"2024-01-{day:02d}",
            open_price=Decimal(day),
            high_price=Decimal(day + 1),
            low_price=Decimal(day - 1),
            close_price=Decimal(day),
            volume=day * 100,
            turnover_amount_minor=day * 1000,
        )
        for day in range(1, 22)
    )
    market = tuple(
        HistoricalIndexObservation("market", f"2024-01-{day:02d}", Decimal(day * 2))
        for day in range(1, 22)
    )
    technicals = (
        HistoricalTechnicalObservation(
            "2330", "2024-01-21", Decimal("55"), Decimal("0.5"), Decimal("25")
        ),
    )
    projection = compute_current_restated_core19_projection(
        symbol="2330",
        event_date="2024-01-21",
        prices=prices,
        technicals=technicals,
        market=market,
    )
    snapshot = HistoricalRawSnapshot(
        decision_date="2024-01-22",
        feature_as_of_date="2024-01-21",
        prices=prices,
        technicals=technicals,
        market=market,
        industries=(),
        source_fingerprint=_SOURCE_HASH,
        query_count=3,
    )
    historical = HistoricalFeatureBuilder().compute(
        snapshot, industry_index_name_by_symbol={}
    )[0]
    expected = dict(historical.values)
    assert projection.feature_ids == tuple(
        feature_id
        for feature_id in CORE_LONG_HISTORY_FEATURE_REGISTRY.canonical_ids
        if feature_id != "industry_relative_return_20d_bp"
    )
    assert projection.feature_ids == CURRENT_RESTATED_CORE19_FEATURE_IDS
    assert dict(zip(projection.feature_ids, projection.values)) == {
        feature_id: expected[feature_id] for feature_id in projection.feature_ids
    }
    assert projection.excluded_feature_ids == ("industry_relative_return_20d_bp",)
    assert projection.excluded_reason == "verified_symbol_industry_membership_unavailable"
    assert not hasattr(projection, "available_date")
    assert not hasattr(projection, "decision_date")


def test_current_restated_market_bridge_keeps_full_verified_calendar_and_label_alias_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = tmp_path / "fixture-repository"
    research_root = repository / "output" / "ml_research"
    run_root = research_root / "market-calendar-fixture"
    raw_root = run_root / "core_long_history"
    raw_root.mkdir(parents=True)

    def test_resolver(path: Path) -> Path:
        return resolve_ml_research_output_path(path, repository_root=repository)

    monkeypatch.setattr(research_bridge, "resolve_ml_research_output_path", test_resolver)
    context_sha = "sha256:" + hashlib.sha256(b"fixture context bundle").hexdigest()
    source_observed = datetime.fromisoformat(_SOURCE_OBSERVED)
    current_available = datetime(2026, 10, 3, 3, 0, tzinfo=timezone.utc)
    calendar = tuple(date(2026, 1, 5) + timedelta(days=index) for index in range(4))
    source_ids = ("market_indices.收盤指數", "market_indices.收盤價")
    market_close_ids = tuple(f"benchmark/{source_id}" for source_id in source_ids)
    direct_registry = {
        stable_id: CurrentRestatedOutcomeFeatureV1(
            feature_id=stable_id,
            source_feature_id=source_id,
            source_table="market_indices",
            role="benchmark",
            unit="index_1e4",
            decimal_exponent=4,
            eligibility_status="formal_backfill",
        )
        for stable_id, source_id in zip(market_close_ids, source_ids, strict=True)
    }
    raw_feature_registry = [
        {
            "feature_id": source_id,
            "source_id": "sqlite.market_indices",
            "table_name": "market_indices",
            "unit": "index_1e4",
            "scale": 4,
        }
        for source_id in source_ids
    ]
    rows: list[dict[str, object]] = []
    for index, event_date in enumerate(calendar):
        preferred = None if index == 2 else 100_000 + index * 1_000
        alias = 102_000 if index == 2 else preferred
        row_sha = "sha256:" + hashlib.sha256(f"market-row-{index}".encode()).hexdigest()
        values = [
            {
                "feature_id": source_id,
                "value_int": value_int,
                "scale": 4,
                "unit": "index_1e4",
                "missing_mask": value_int is None,
                "quality_blocked_mask": False,
                "staleness_mask": False,
            }
            for source_id, value_int in zip(source_ids, (preferred, alias), strict=True)
        ]
        rows.append(
            {
                "source_table": "market_indices",
                "source_id": "sqlite.market_indices",
                "entity_id": "TAIEX",
                "event_date": event_date.isoformat(),
                "source_row_hash": row_sha,
                "source_context_bundle_sha256": context_sha,
                "source_observed_at": source_observed.isoformat(),
                "current_value_available_at": current_available.isoformat(),
                "current_restated": True,
                "event_reference_only": True,
                "source_available_at": None,
                "historical_pit_eligible": False,
                "formal_training_eligible": False,
                "values": values,
            }
        )
    raw_content = b"".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        + b"\n"
        for row in rows
    )
    compressed = gzip.compress(raw_content, mtime=0)
    shard_path = raw_root / "year=2026.jsonl.gz"
    shard_path.write_bytes(compressed)
    shard_stat = shard_path.stat()
    shard_sha = hashlib.sha256(compressed).hexdigest()
    content_sha = hashlib.sha256(raw_content).hexdigest()
    dataset_identity = "sha256:" + hashlib.sha256(b"fixture dataset identity").hexdigest()
    dataset_manifest = {
        "schema_version": "ml-current-restated-year-shard-dataset.v1",
        "current_restated": True,
        "historical_pit_eligible": False,
        "formal_training_eligible": False,
        "manifest_hash": dataset_identity,
        "source_context_bundle_sha256": context_sha,
        "features": raw_feature_registry,
        "shards": [
            {
                "year": 2026,
                "path": "core_long_history/year=2026.jsonl.gz",
                "compressed_bytes": len(compressed),
                "compressed_sha256": "sha256:" + shard_sha,
                "content_sha256": "sha256:" + content_sha,
                "row_count": len(rows),
            }
        ],
    }
    dataset_path = raw_root / "manifest.json"
    dataset_bytes = json.dumps(dataset_manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
    dataset_path.write_bytes(dataset_bytes)
    publication_manifest = {
        "schema_version": "ml-current-restated-year-shards.v1",
        "current_restated": True,
        "historical_pit_eligible": False,
        "formal_training_eligible": False,
        "source_context_bundle_sha256": context_sha,
        "datasets": {
            "core_long_history": {
                "manifest_path": "core_long_history/manifest.json",
                "manifest_hash": dataset_identity,
            }
        },
    }
    publication_path = run_root / "manifest.json"
    publication_bytes = json.dumps(publication_manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
    publication_path.write_bytes(publication_bytes)
    artifact = SimpleNamespace(
        raw_publication_manifest_path=str(publication_path.resolve()),
        raw_publication_manifest_bytes_sha256=hashlib.sha256(publication_bytes).hexdigest(),
        raw_dataset_manifest_path=str(dataset_path.resolve()),
        raw_dataset_manifest_bytes_sha256=hashlib.sha256(dataset_bytes).hexdigest(),
        raw_shard_pins=(SimpleNamespace(
            role_id="raw_shard_year_2026",
            path=str(shard_path.resolve()),
            bytes=len(compressed),
            mtime_ns=shard_stat.st_mtime_ns,
            sha256=shard_sha,
            content_sha256="sha256:" + content_sha,
            row_count=len(rows),
        ),),
        benchmark_entity_id="TAIEX",
        source_observed_at=source_observed,
        current_observation_freeze=datetime(2026, 10, 3, 3, 20, tzinfo=timezone.utc),
    )

    states, hashes = _load_verified_current_restated_market_history(
        artifact=artifact,
        calendar_dates=calendar,
        registry_by_source=direct_registry,
        market_close_ids=market_close_ids,
    )
    market_rows, _quality, _stale, unavailable = _build_current_restated_market_observations(
        calendar_dates=calendar,
        state_by_date=states,
        market_close_ids=market_close_ids,
        registry_by_source=direct_registry,
    )
    assert len(states) == 4
    assert tuple(date.fromisoformat(row.trading_date) for row in market_rows) == calendar
    assert len(hashes) == 4
    assert market_rows[2].close_value is None
    assert calendar[2].isoformat() in unavailable
    assert states[calendar[2]]["benchmark/market_indices.收盤指數"] == (None, False, False, True)
    assert states[calendar[2]]["benchmark/market_indices.收盤價"][0] == 102_000
    with pytest.raises(ValueError, match="complete pinned benchmark calendar"):
        _load_verified_current_restated_market_history(
            artifact=artifact,
            calendar_dates=calendar[:-1],
            registry_by_source=direct_registry,
            market_close_ids=market_close_ids,
        )
    blocked_state = dict(states)
    blocked_aliases = dict(blocked_state[calendar[0]])
    blocked_aliases["benchmark/market_indices.收盤指數"] = (100_000, True, False, False)
    blocked_state[calendar[0]] = blocked_aliases
    with pytest.raises(ValueError, match="label-preferred TAIEX close"):
        _build_current_restated_market_observations(
            calendar_dates=calendar,
            state_by_date=blocked_state,
            market_close_ids=market_close_ids,
            registry_by_source=direct_registry,
        )


def test_current_restated_core19_projection_keeps_future_and_gap_masks() -> None:
    prices = tuple(
        HistoricalPriceObservation(
            symbol="2330",
            trading_date=f"2024-01-{day:02d}",
            open_price=Decimal(day),
            high_price=Decimal(day + 1),
            low_price=Decimal(day - 1),
            close_price=Decimal(day),
            volume=day * 100,
            turnover_amount_minor=day * 1000,
        )
        for day in range(1, 22)
    ) + (
        HistoricalPriceObservation(
            "2330", "2024-01-22", Decimal(1000), Decimal(1001), Decimal(999),
            Decimal(1000), 100000, 1000000
        ),
    )
    market = tuple(
        HistoricalIndexObservation("market", f"2024-01-{day:02d}", Decimal(day * 2))
        for day in range(1, 22)
    )
    future_ignored = compute_current_restated_core19_projection(
        symbol="2330", event_date="2024-01-21", prices=prices,
        technicals=(), market=market
    )
    gap_masked = compute_current_restated_core19_projection(
        symbol="2330", event_date="2024-01-21", prices=prices,
        technicals=(), market=market,
        unavailable_price_dates=("2024-01-20",),
    )
    future_ignored_without_row = compute_current_restated_core19_projection(
        symbol="2330", event_date="2024-01-21", prices=prices[:-1],
        technicals=(), market=market
    )
    assert future_ignored == future_ignored_without_row
    future_ids = dict(zip(future_ignored.feature_ids, future_ignored.values))
    gap_ids = dict(zip(gap_masked.feature_ids, gap_masked.values))
    assert future_ids["turnover_amount_minor"] == 21000
    assert gap_ids["stock_return_1d_bp"] is None
    assert gap_ids["close_to_ma_5d_bp"] is None
    assert gap_ids["volume_ratio_5d_bp"] is None


def test_current_restated_core19_projection_preserves_quality_and_staleness_masks() -> None:
    prices = tuple(
        HistoricalPriceObservation(
            symbol="2330",
            trading_date=f"2024-01-{day:02d}",
            open_price=Decimal(day),
            high_price=Decimal(day + 1),
            low_price=Decimal(day - 1),
            close_price=Decimal(day),
            volume=day * 100,
            turnover_amount_minor=day * 1000,
        )
        for day in range(1, 22)
    )
    market = tuple(
        HistoricalIndexObservation("market", f"2024-01-{day:02d}", Decimal(day * 2))
        for day in range(1, 22)
    )
    projection = compute_current_restated_core19_projection(
        symbol="2330",
        event_date="2024-01-21",
        prices=prices,
        technicals=(HistoricalTechnicalObservation(
            "2330", "2024-01-21", Decimal("55"), Decimal("0.5"), Decimal("25")
        ),),
        market=market,
        quality_blocked_technical_dates=("2024-01-21",),
        stale_price_dates=("2024-01-21",),
    )
    values = dict(zip(projection.feature_ids, projection.values))
    assert values["rsi_normalized_bp"] is None
    assert values["adx_normalized_bp"] is None
    assert values["macd_normalized_bp"] is None
    assert set(projection.quality_blocked_feature_ids) == {
        "rsi_normalized_bp", "adx_normalized_bp", "macd_normalized_bp"
    }
    assert "stock_return_1d_bp" in projection.staleness_blocked_feature_ids
    assert "turnover_amount_minor" in projection.staleness_blocked_feature_ids
    assert "market_return_5d_bp" not in projection.staleness_blocked_feature_ids


def test_current_restated_fit_saves_and_new_process_reloads_exact_model_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = tmp_path / "synthetic-repository"
    research_root = repository / "output" / "ml_research"
    research_root.mkdir(parents=True)

    def test_resolver(path: Path) -> Path:
        return resolve_ml_research_output_path(path, repository_root=repository)

    monkeypatch.setattr(research_bridge, "resolve_ml_research_output_path", test_resolver)

    snapshot_dir = research_root / "snapshot"
    snapshot_dir.mkdir()
    snapshot_path = snapshot_dir / "source.sqlite"
    snapshot_path.write_bytes(b"synthetic consistent sqlite snapshot bytes")
    install_test_revision_gate(monkeypatch)
    source_receipt_path, source_receipt_sha = write_snapshot_context_receipt(
        snapshot_path,
        tmp_path,
        completed_at="2026-10-03T00:23:25.887429+00:00",
    )
    context_training_cutoff = datetime.now(timezone.utc)
    decision_at = context_training_cutoff - timedelta(seconds=2)
    source_context = load_verified_current_restated_source_context(
        snapshot_path,
        source_receipt_path,
        expected_snapshot_database_sha256=hashlib.sha256(snapshot_path.read_bytes()).hexdigest(),
        expected_snapshot_receipt_sha256=source_receipt_sha,
        original_database_path=tmp_path / "source_context" / "original_source.sqlite",
        decision_at=decision_at,
        training_as_of=context_training_cutoff,
    )
    context_file, context_sha = save_verified_current_restated_context_file(
        source_context,
        output_path=research_root / "shared-source-context.json",
        fit_cutoff=datetime.now(timezone.utc).isoformat(),
    )
    loaded_context_file = load_verified_current_restated_context_file(
        context_file,
        expected_context_sha256=context_sha,
    )
    assert loaded_context_file.sha256 == context_sha
    assert loaded_context_file.saved_payload["source_database_sha256"] == source_context.source_database_sha256
    assert (
        loaded_context_file.context.revision_dependencies_verified_at
        == source_context.revision_dependencies_verified_at
    )
    assert (
        loaded_context_file.context.revision_dependency_bundle_sha256
        == source_context.revision_dependency_bundle_sha256
    )
    assert (
        loaded_context_file.revalidated_dependency_bundle_sha256
        != loaded_context_file.context.revision_dependency_bundle_sha256
    )
    research_bridge._verify_direct_context_payload_binding(
        dict(loaded_context_file.saved_payload), loaded_context_file
    )
    with pytest.raises(ValueError, match="dependency inventory changed"):
        research_bridge._verify_direct_context_payload_binding(
            dict(loaded_context_file.saved_payload),
            replace(loaded_context_file, revalidated_dependency_inventory_sha256="0" * 64),
        )
    with pytest.raises(ValueError, match="actual-byte SHA-256 mismatch"):
        load_verified_current_restated_context_file(
            context_file,
            expected_context_sha256="0" * 64,
        )

    direct_root = research_root / "direct-input"
    direct_root.mkdir()
    direct_manifest = direct_root / "manifest.json"
    refreshed_context = load_verified_current_restated_source_context(
        snapshot_path,
        source_receipt_path,
        expected_snapshot_database_sha256=hashlib.sha256(snapshot_path.read_bytes()).hexdigest(),
        expected_snapshot_receipt_sha256=source_receipt_sha,
        original_database_path=Path(str(source_context.source_database_path)),
        decision_at=max(
            source_context.decision_at + timedelta(milliseconds=5),
            datetime.now(timezone.utc) - timedelta(milliseconds=500),
        ),
        training_as_of=max(
            source_context.training_as_of + timedelta(milliseconds=10),
            datetime.now(timezone.utc) - timedelta(milliseconds=100),
        ),
    )
    assert refreshed_context.decision_at != source_context.decision_at
    assert refreshed_context.training_as_of != source_context.training_as_of
    refreshed_envelope_path, refreshed_envelope_sha = save_verified_current_restated_context_file(
        refreshed_context,
        output_path=research_root / "fresh-source-context.json",
        fit_cutoff=datetime.now(timezone.utc).isoformat(),
    )
    fresh_context_file = load_verified_current_restated_context_file(
        refreshed_envelope_path,
        expected_context_sha256=refreshed_envelope_sha,
    )
    assert (
        fresh_context_file.context.revision_dependency_bundle_sha256
        != source_context.revision_dependency_bundle_sha256
    )
    original_direct_context = research_bridge._source_context_plain_payload(source_context)
    original_direct_context["source_revision_evidence"] = {
        "digest_sha256": source_context.source_revision_evidence_sha256,
        "cutoff_date": source_context.source_revision_evidence_cutoff_date,
        "schema_version": source_context.source_revision_evidence_schema_version,
        "scope_id": source_context.source_revision_evidence_scope_id,
    }
    original_context_bundle_sha = hashlib.sha256(
        json.dumps(
            original_direct_context,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    direct_manifest_payload = {
        "schema_version": "portfolio-ml-current-restated-outcome-store.v1",
        "status": "current_restated_outcome_numeric_ready",
        "revision_dependency_bundle_sha256": source_context.revision_dependency_bundle_sha256,
        "source_context_revalidation": original_direct_context,
        "source_pins": {
            "revalidated_context_bundle_sha256": original_context_bundle_sha
        },
    }
    direct_manifest_bytes = (
        json.dumps(
            direct_manifest_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )
    direct_manifest.write_bytes(direct_manifest_bytes)
    direct_context = SimpleNamespace(
        artifact_receipt_path=str(direct_manifest),
        artifact_receipt_bytes_sha256=hashlib.sha256(direct_manifest_bytes).hexdigest(),
        source_database_sha256=source_context.source_database_sha256,
        snapshot_database_sha256=source_context.snapshot_database_sha256,
        snapshot_receipt_sha256=source_context.snapshot_receipt_sha256,
        revision_dependency_bundle_sha256=source_context.revision_dependency_bundle_sha256,
        source_observed_at=source_context.source_observed_at,
        source_database_path=source_context.source_database_path,
        snapshot_database_path=source_context.snapshot_database_path,
        snapshot_receipt_path=source_context.snapshot_receipt_path,
    )
    research_bridge._verify_direct_context_binding(direct_context, fresh_context_file)
    with pytest.raises(ValueError, match="physical dependency closures differ"):
        research_bridge._verify_direct_context_binding(
            direct_context,
            replace(fresh_context_file, revalidated_dependency_inventory_sha256="0" * 64),
        )
    original_read_bytes = Path.read_bytes
    expected_status = b'"status":"current_restated_outcome_numeric_ready"'
    substituted_status = b'"status":"current_restated_outcome_numeric_stale"'
    assert len(expected_status) == len(substituted_status)
    substituted_manifest_bytes = direct_manifest_bytes.replace(expected_status, substituted_status, 1)
    assert len(substituted_manifest_bytes) == len(direct_manifest_bytes)

    def same_size_replacement(path: Path) -> bytes:
        if path == direct_manifest:
            return substituted_manifest_bytes
        return original_read_bytes(path)

    with monkeypatch.context() as private_read_patch:
        private_read_patch.setattr(research_bridge, "_verified_research_file", lambda *args, **kwargs: None)
        private_read_patch.setattr(Path, "read_bytes", same_size_replacement)
        with pytest.raises(ValueError, match="private-read bytes differ"):
            research_bridge._verify_direct_context_binding(direct_context, fresh_context_file)
    direct_receipt = direct_root / "receipt.json"
    direct_receipt.write_text('{"schema_version":"test-direct-receipt.v1"}', encoding="utf-8")
    value_file = direct_root / "values.i64"
    value_file.write_bytes(b"test-owned-i64-observations")
    mask_file = direct_root / "missing.u8"
    mask_file.write_bytes(b"test-owned-u8-mask")
    file_pins = tuple(
        CurrentRestatedInputFilePin(
            role=role,
            path=str(path),
            bytes=path.stat().st_size,
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        )
        for role, path in (("value_array", value_file), ("missing_mask", mask_file))
    )

    samples = tuple(
        _sample(index, label_observed=index != 200, feature_missing=index == 0)
        for index in range(905)
    )
    fit_freeze = datetime.now(timezone.utc)
    fit_code_pins = capture_current_restated_training_code_pins()
    result = AllocationTrainingService(random_state=7).fit_current_restated_outcome_only(
        samples=samples,
        feature_packs=(_PACK,),
        folds=_folds(samples),
        training_as_of=fit_freeze.isoformat(),
        dataset_manifest_file_hash="sha256:" + hashlib.sha256(direct_manifest.read_bytes()).hexdigest(),
        event_date_calendar=_event_calendar(samples),
    )
    test_cost_contract = research_bridge._expected_outcome_cost_contract_payload()
    result = replace(
        result,
        audit={
            **research_bridge._bind_verified_current_restated_fold_qualification(
                result.audit,
                folds=_folds(samples),
                event_date_calendar=_event_calendar(samples),
                direct_manifest_sha256=hashlib.sha256(direct_manifest.read_bytes()).hexdigest(),
            ),
            "outcome_cost_contract": test_cost_contract,
            "target_contract": research_bridge._outcome_target_contract(test_cost_contract),
        },
    )
    wrong_provenance = replace(
        result,
        audit={**result.audit, "dataset_manifest_file_hash": "0" * 64},
    )
    with pytest.raises(ValueError, match="fit dataset manifest differs"):
        save_current_restated_outcome_model(
            fit_result=wrong_provenance,
            feature_registry=({"feature_id": _FEATURE_ID, "scale": 2, "unit": "TWD per share"},),
            feature_packs=(_PACK,),
            source_context=source_context,
            direct_manifest_path=direct_manifest,
            expected_direct_manifest_sha256=hashlib.sha256(direct_manifest.read_bytes()).hexdigest(),
            direct_receipt_path=direct_receipt,
            expected_direct_receipt_sha256=hashlib.sha256(direct_receipt.read_bytes()).hexdigest(),
            input_file_pins=file_pins,
            fit_code_pins_before=fit_code_pins,
            training_as_of=fit_freeze.isoformat(),
            output_directory=research_root / "models" / "provenance-mismatch",
            actual_invocation=("synthetic-test-fit",),
        )
    saved = save_current_restated_outcome_model(
        fit_result=result,
        feature_registry=({"feature_id": _FEATURE_ID, "scale": 2, "unit": "TWD per share"},),
        feature_packs=(_PACK,),
        source_context=source_context,
        direct_manifest_path=direct_manifest,
        expected_direct_manifest_sha256=hashlib.sha256(direct_manifest.read_bytes()).hexdigest(),
        direct_receipt_path=direct_receipt,
        expected_direct_receipt_sha256=hashlib.sha256(direct_receipt.read_bytes()).hexdigest(),
        input_file_pins=file_pins,
        fit_code_pins_before=fit_code_pins,
        training_as_of=fit_freeze.isoformat(),
        output_directory=research_root / "models" / "outcome-only-test",
        actual_invocation=("synthetic-test-fit",),
    )

    loaded = load_current_restated_outcome_model(
        saved.manifest_path,
        expected_manifest_sha256=saved.manifest_sha256,
        expected_model_bundle_sha256=saved.model_bundle_sha256,
    )
    inference_at = datetime.now(timezone.utc).isoformat()
    sample = samples[-1]
    parent_prediction = predict_current_restated_outcomes(
        loaded,
        row=sample.row,
        inference_at=inference_at,
    )
    model_key = "final|core_close|h5|ridge_logistic"
    pre_save_prediction = _quantize_model_bp(
        result.models[model_key].predict(
            _restated_outcome_matrix((sample,), pack=_PACK, algorithm="ridge_logistic")
        )[0]
    )
    assert parent_prediction["predicted_benchmark_excess_return_bp"][model_key] == pre_save_prediction
    assert parent_prediction["decision_time_eligible"] is False
    assert parent_prediction["production_action_allowed"] is False
    shape = json.loads(saved.manifest_path.read_text(encoding="utf-8"))["model_bundle"]["shapes"][model_key]
    assert shape["feature_width"] == 1
    assert shape["missing_indicator_indices"] == [0]
    assert shape["transformed_width"] == 2
    assert shape["matrix_width"] == 2
    fully_blocked = replace(
        sample.row,
        features=(replace(sample.row.features[0], value_int=None, observed=False),),
        missing_mask=(_FEATURE_ID,),
    )
    with pytest.raises(ValueError, match="no usable observed feature"):
        predict_current_restated_outcomes(
            loaded,
            row=fully_blocked,
            inference_at=inference_at,
        )

    vector_path = research_root / "inputs" / "current_vector.json"
    vector_path.parent.mkdir()
    vector_payload = {
        "row_id": sample.row.row_id,
        "symbol": sample.row.symbol,
        "event_date": sample.row.event_date,
        "event_at": sample.row.event_at,
        "features": [
            {
                "feature_id": feature.feature_id,
                "value_int": feature.value_int,
                "scale": feature.scale,
                "observed": feature.observed,
                "event_at": feature.event_at,
                "source_available_at": feature.source_available_at,
                "source_observed_at": feature.source_observed_at,
                "current_value_available_at": feature.current_value_available_at,
                "source_value_hash": feature.source_value_hash,
                "source_value_hash_semantics": feature.source_value_hash_semantics,
            }
            for feature in sample.row.features
        ],
        "missing_mask": list(sample.row.missing_mask),
        "quality_blocked_mask": list(sample.row.quality_blocked_mask),
        "source_observed_at": sample.row.source_observed_at,
        "historical_pit_eligible": False,
    }
    vector_bytes = json.dumps(vector_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    vector_path.write_bytes(vector_bytes)

    cli_path = Path(__file__).resolve().parents[1] / "scripts" / "train_bounded_restated_research.py"
    future_cli_code = """
import runpy, sys
from pathlib import Path
import data_module.ml_research_output_boundary as boundary
original = boundary.resolve_ml_research_output_path
root = Path(sys.argv[1])
boundary.resolve_ml_research_output_path = lambda path, **kwargs: original(path, repository_root=root, **kwargs)
script = sys.argv[2]
sys.argv = [script, *sys.argv[3:]]
runpy.run_path(script, run_name='__main__')
"""
    future_cli = subprocess.run(
        [
            sys.executable,
            "-c",
            future_cli_code,
            str(repository),
            str(cli_path),
            "--verify-current-restated-model",
            str(saved.manifest_path),
            "--expected-model-manifest-sha256",
            saved.manifest_sha256,
            "--expected-model-bundle-sha256",
            saved.model_bundle_sha256,
            "--inference-vector-json",
            str(vector_path),
            "--expected-vector-sha256",
            hashlib.sha256(vector_bytes).hexdigest(),
            "--inference-at",
            (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )
    assert future_cli.returncode == 2
    assert "actual current clock" in future_cli.stderr

    child_code = """\
import json, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
repo, manifest, manifest_sha, model_sha, vector_path, vector_sha = sys.argv[1:]
import data_module.ml_research_output_boundary as boundary
import ml_module.current_restated_research_bridge as bridge
from ml_module.current_restated_research_bridge import CurrentRestatedFeature, CurrentRestatedResearchRow
boundary_root = Path(repo)
bridge.resolve_ml_research_output_path = lambda path: boundary.resolve_ml_research_output_path(path, repository_root=boundary_root)
model = bridge.load_current_restated_outcome_model(
    Path(manifest), expected_manifest_sha256=manifest_sha,
    expected_model_bundle_sha256=model_sha,
)
raw = Path(vector_path).read_bytes()
import hashlib
assert hashlib.sha256(raw).hexdigest() == vector_sha
payload = json.loads(raw.decode('utf-8'))
row = CurrentRestatedResearchRow(
    row_id=payload['row_id'], symbol=payload['symbol'], event_date=payload['event_date'], event_at=payload['event_at'],
    features=tuple(CurrentRestatedFeature(**item) for item in payload['features']),
    missing_mask=tuple(payload['missing_mask']), quality_blocked_mask=tuple(payload['quality_blocked_mask']),
    source_observed_at=payload['source_observed_at'], historical_pit_eligible=payload['historical_pit_eligible'],
)
result = bridge.predict_current_restated_outcomes(model, row=row, inference_at=datetime.now(timezone.utc).isoformat())
print(json.dumps(bridge._plain_json(result, 'prediction'), sort_keys=True))
"""
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            child_code,
            str(repository),
            str(saved.manifest_path),
            saved.manifest_sha256,
            saved.model_bundle_sha256,
            str(vector_path),
            hashlib.sha256(vector_bytes).hexdigest(),
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    child_prediction = json.loads(completed.stdout)
    assert child_prediction["model_manifest_sha256"] == saved.manifest_sha256
    assert child_prediction["predicted_benchmark_excess_return_bp"] == dict(
        parent_prediction["predicted_benchmark_excess_return_bp"]
    )

    import ml_module.model_artifact_loader as artifact_loader

    deserialize_calls = 0
    actual_deserializer = artifact_loader._deserialize_verified_joblib_buffer

    def count_deserializer(buffer: object) -> object:
        nonlocal deserialize_calls
        deserialize_calls += 1
        return actual_deserializer(buffer)  # type: ignore[arg-type]

    monkeypatch.setattr(artifact_loader, "_deserialize_verified_joblib_buffer", count_deserializer)
    manifest_path = saved.manifest_path
    original_manifest = manifest_path.read_bytes()
    for field, value in (
        ("target_contract", {"schema_version": "bad", "target_metric": "gross_stock_return_bp"}),
        ("outcome_cost_contract", {**research_bridge._expected_outcome_cost_contract_payload(), "buy_side_cost_bp": 50}),
    ):
        mutated = json.loads(original_manifest.decode("utf-8"))
        mutated[field] = value
        manifest_path.write_text(
            json.dumps(mutated, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        mutated_sha = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        with pytest.raises(ValueError, match="target/cost contract"):
            load_current_restated_outcome_model(
                manifest_path,
                expected_manifest_sha256=mutated_sha,
                expected_model_bundle_sha256=saved.model_bundle_sha256,
            )
        assert deserialize_calls == 0
    manifest_path.write_bytes(original_manifest)
    manifest_value = json.loads(original_manifest.decode("utf-8"))
    key = manifest_value["model_bundle"]["model_keys"][0]
    manifest_value["model_bundle"]["estimator_classes"][key] = "builtins.eval"
    manifest_path.write_text(
        json.dumps(manifest_value, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    mutated_manifest_sha = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="declared estimator classes"):
        load_current_restated_outcome_model(
            manifest_path,
            expected_manifest_sha256=mutated_manifest_sha,
            expected_model_bundle_sha256=saved.model_bundle_sha256,
        )
    assert deserialize_calls == 0

    manifest_value = json.loads(original_manifest.decode("utf-8"))
    manifest_value["source_context"]["source_observed_at"] = "2099-01-01T00:00:00+00:00"
    manifest_path.write_text(
        json.dumps(manifest_value, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    mutated_manifest_sha = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="exceeds the fit cutoff"):
        load_current_restated_outcome_model(
            manifest_path,
            expected_manifest_sha256=mutated_manifest_sha,
            expected_model_bundle_sha256=saved.model_bundle_sha256,
        )
    assert deserialize_calls == 0

    manifest_path.write_bytes(original_manifest)
    failed_receipt = manifest_path.parent / "failed_receipt.json"
    failed_receipt.write_text('{"status":"failed"}', encoding="utf-8")
    with pytest.raises(ValueError, match="failed receipt"):
        load_current_restated_outcome_model(
            manifest_path,
            expected_manifest_sha256=saved.manifest_sha256,
            expected_model_bundle_sha256=saved.model_bundle_sha256,
        )
    assert deserialize_calls == 0
    failed_receipt.unlink()

    with pytest.raises(ValueError, match="actual current clock"):
        predict_current_restated_outcomes(
            loaded,
            row=sample.row,
            inference_at=(datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        )

    with pytest.raises(ValueError, match="actual-byte SHA-256 mismatch"):
        load_current_restated_outcome_model(
            saved.manifest_path,
            expected_manifest_sha256="0" * 64,
            expected_model_bundle_sha256=saved.model_bundle_sha256,
        )
    with pytest.raises(ValueError, match="out-of-band trusted SHA-256"):
        load_current_restated_outcome_model(
            saved.manifest_path,
            expected_manifest_sha256=saved.manifest_sha256,
            expected_model_bundle_sha256="0" * 64,
        )
    (saved.manifest_path.parent / "models.joblib").write_bytes(b"truncated model bytes")
    with pytest.raises(ValueError, match="artifact hash or size mismatch"):
        load_current_restated_outcome_model(
            saved.manifest_path,
            expected_manifest_sha256=saved.manifest_sha256,
            expected_model_bundle_sha256=saved.model_bundle_sha256,
        )


def test_current_restated_fit_cli_requires_complete_pinned_inputs() -> None:
    repository = Path(__file__).resolve().parents[1]
    completed = subprocess.run(
        [
            sys.executable,
            str(repository / "scripts" / "train_bounded_restated_research.py"),
            "--fit-current-restated-outcome-artifact",
            str(repository / "output" / "ml_research" / "missing-manifest.json"),
        ],
        cwd=repository,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 2
    assert "requires all Direct, context, B-current-vector, and output pins" in completed.stderr


def test_current_restated_invocation_and_legacy_terminal_receipt_contract(
    tmp_path: Path,
) -> None:
    research_root = tmp_path / "output" / "ml_research"
    terminal_dir = research_root / "source_row_research" / "legacy" / "test-run"
    terminal_dir.mkdir(parents=True)
    receipt_path = terminal_dir / "receipt.json"
    binding = {
        "schema_version": "current-restated-source-row-research-binding.v1",
        "mode": "source_row_outcome_research",
        "source_context_sha256": "1" * 64,
        "outcome_receipt_sha256": "2" * 64,
        "raw_publication_manifest_sha256": "3" * 64,
        "raw_dataset_manifest_sha256": "4" * 64,
        "outcome_feature_registry_sha256": "5" * 64,
        "b_consumption_receipt_sha256": "6" * 64,
        "b_candidate_manifest_sha256": "7" * 64,
        "b_adapted_manifest_sha256": "8" * 64,
        "b_feature_registry_sha256": "9" * 64,
        "model_manifest_sha256": "a" * 64,
        "model_bundle_sha256": "b" * 64,
        "current_symbols": ["2317", "2330"],
        "current_event_date": "2026-10-02",
        "b_current_observation_freeze": "2026-10-03T01:15:57.935204+00:00",
        "historical_pit_eligible": False,
        "formal_calibration_performed": False,
        "model_training_performed": False,
        "verified_model_reused": True,
    }
    binding_sha = hashlib.sha256(
        json.dumps(binding, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    cohort = {
        "schema_version": "current-restated-source-row-sample-cohort.v1",
        "symbols": ["2317", "2330"],
        "event_date": "2026-10-02",
        "samples": [
            {"symbol": symbol, "sample_id": f"sample-{symbol}"}
            for symbol in ("2317", "2330")
        ],
        "cohort_kind": "verified_direct_source_rows_not_daily_recommendations",
        "historical_pit_eligible": False,
    }
    vectors = {symbol: hashlib.sha256(symbol.encode("ascii")).hexdigest() for symbol in cohort["symbols"]}
    payload = {
        "schema_version": "current-restated-source-row-learning-terminal.v1",
        "status": "verified_research_sidecar",
        "terminal": True,
        "mode": "source_row_outcome_research",
        "lane": "legacy",
        "binding_sha256": binding_sha,
        "input_binding": binding,
        "sample_cohort": cohort,
        "sample_cohort_sha256": hashlib.sha256(
            json.dumps(cohort, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        "core19_numeric_vector_sha256_by_symbol": vectors,
        "model_training_performed": False,
        "verified_model_reused": True,
        "formal_calibration_performed": False,
        "historical_pit_eligible": False,
        "decision_time_eligible": False,
    }
    receipt_bytes = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    receipt_path.write_bytes(receipt_bytes)
    receipt_sha = hashlib.sha256(receipt_bytes).hexdigest()
    verified = verify_current_restated_legacy_terminal_receipt(
        receipt_path,
        expected_receipt_sha256=receipt_sha,
        expected_binding_sha256=binding_sha,
        repository_root=tmp_path,
    )
    assert verified["status"] == "verified_research_sidecar"
    with pytest.raises(ValueError, match="contract or binding is invalid"):
        verify_current_restated_legacy_terminal_receipt(
            receipt_path,
            expected_receipt_sha256=receipt_sha,
            expected_binding_sha256="c" * 64,
            repository_root=tmp_path,
        )
    (terminal_dir / "failed_receipt.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="failed receipt"):
        verify_current_restated_legacy_terminal_receipt(
            receipt_path,
            expected_receipt_sha256=receipt_sha,
            expected_binding_sha256=binding_sha,
            repository_root=tmp_path,
        )

    invocation = CurrentRestatedResearchInvocation(
        source_context_path=research_root / "context.json",
        source_context_sha256="1" * 64,
        outcome_receipt_path=research_root / "direct" / "receipt.json",
        outcome_receipt_sha256="2" * 64,
        raw_publication_manifest_sha256="3" * 64,
        raw_dataset_manifest_sha256="4" * 64,
        outcome_feature_registry_sha256="5" * 64,
        b_consumption_receipt_path=research_root / "b" / "receipt.json",
        b_consumption_receipt_sha256="6" * 64,
        b_candidate_manifest_sha256="7" * 64,
        b_adapted_manifest_sha256="8" * 64,
        b_feature_registry_sha256="9" * 64,
        model_manifest_path=research_root / "model" / "manifest.json",
        model_manifest_sha256="a" * 64,
        model_bundle_sha256="b" * 64,
        current_symbols=("2317", "2330"),
        current_event_date="2026-10-02",
        b_current_observation_freeze="2026-10-03T01:15:57.935204+00:00",
        inference_at=None,
        output_root=research_root,
    )
    arguments = invocation.child_arguments()
    assert arguments[0] == "--current-restated-research-only"
    assert "--research-current-symbols" in arguments
    assert arguments[arguments.index("--research-current-symbols") + 1] == "2317,2330"
    assert "--research-outcome-receipt-sha256" in arguments
    assert "--research-inference-at" not in arguments
    assert hashlib.sha256(
        json.dumps(
            invocation.stable_binding_payload(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest() == research_bridge.current_restated_research_input_binding_sha256(invocation)


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("current_symbols", ["2317", "9999"]),
        ("model_manifest_sha256", "c" * 64),
        ("outcome_receipt_sha256", "d" * 64),
    ],
)
def test_banktaiwan_terminal_binding_freeze_normalizes_json_containers_and_rejects_foreign_inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    replacement: object,
) -> None:
    from ml_module.recommendation_cost_scenario import build_banktaiwan_cost_scenario

    research_root = tmp_path / "output" / "ml_research"
    terminal_dir = research_root / "source_row_research" / "legacy" / "terminal"
    terminal_dir.mkdir(parents=True)
    receipt_path = terminal_dir / "receipt.json"
    invocation = CurrentRestatedResearchInvocation(
        source_context_path=research_root / "context" / "source_context.json",
        source_context_sha256="1" * 64,
        outcome_receipt_path=research_root / "direct" / "manifest.json",
        outcome_receipt_sha256="2" * 64,
        raw_publication_manifest_sha256="3" * 64,
        raw_dataset_manifest_sha256="4" * 64,
        outcome_feature_registry_sha256="5" * 64,
        b_consumption_receipt_path=research_root / "b" / "receipt.json",
        b_consumption_receipt_sha256="6" * 64,
        b_candidate_manifest_sha256="7" * 64,
        b_adapted_manifest_sha256="8" * 64,
        b_feature_registry_sha256="9" * 64,
        model_manifest_path=research_root / "model" / "manifest.json",
        model_manifest_sha256="a" * 64,
        model_bundle_sha256="b" * 64,
        current_symbols=("2317", "2330"),
        current_event_date="2026-10-02",
        b_current_observation_freeze="2026-10-03T01:15:57.935204+00:00",
        inference_at=None,
        output_root=research_root,
    )
    binding = invocation.stable_binding_payload()
    binding_sha = research_bridge.current_restated_research_input_binding_sha256(
        invocation
    )
    cohort = {
        "schema_version": "current-restated-source-row-sample-cohort.v1",
        "symbols": ["2317", "2330"],
        "event_date": "2026-10-02",
        "samples": [
            {"symbol": symbol, "sample_id": f"sample-{symbol}"}
            for symbol in ("2317", "2330")
        ],
        "cohort_kind": "verified_direct_source_rows_not_daily_recommendations",
        "historical_pit_eligible": False,
    }
    vector_map = {
        symbol: hashlib.sha256(symbol.encode("ascii")).hexdigest()
        for symbol in ("2317", "2330")
    }
    payload = {
        "schema_version": "current-restated-source-row-learning-terminal.v1",
        "status": "verified_research_sidecar",
        "terminal": True,
        "mode": "source_row_outcome_research",
        "lane": "legacy",
        "binding_sha256": binding_sha,
        "input_binding": binding,
        "sample_cohort": cohort,
        "sample_cohort_sha256": hashlib.sha256(
            research_bridge._canonical_json_bytes(cohort)
        ).hexdigest(),
        "core19_numeric_vector_sha256_by_symbol": vector_map,
        "model_training_performed": False,
        "verified_model_reused": True,
        "formal_calibration_performed": False,
        "historical_pit_eligible": False,
        "decision_time_eligible": False,
    }
    receipt_bytes = research_bridge._canonical_json_bytes(payload)
    receipt_path.write_bytes(receipt_bytes)
    receipt_sha = hashlib.sha256(receipt_bytes).hexdigest()

    context_load_calls: list[bool] = []

    class _ReachedContextLoad(RuntimeError):
        pass

    def context_load_sentinel(*args: object, **kwargs: object) -> object:
        context_load_calls.append(True)
        raise _ReachedContextLoad

    monkeypatch.setattr(
        research_bridge,
        "load_verified_current_restated_context_file",
        context_load_sentinel,
    )

    def run_sidecar(
        *,
        expected_binding_sha: str,
        expected_receipt_sha: str,
    ) -> None:
        research_bridge.run_current_restated_research_sidecar(
            invocation,
            lane="banktaiwan",
            cost_scenario=build_banktaiwan_cost_scenario(
                policy_estimate_date="2026-01-01",
                research_order_quantity_shares=1_000,
                lot_type="full_lot",
                instrument_type="ordinary_stock",
            ),
            actual_invocation=(),
            upstream_terminal_receipt_path=receipt_path,
            expected_upstream_terminal_receipt_sha256=expected_receipt_sha,
            expected_upstream_binding_sha256=expected_binding_sha,
            repository_root=tmp_path,
        )

    if field == "current_symbols":
        verified = verify_current_restated_legacy_terminal_receipt(
            receipt_path,
            expected_receipt_sha256=receipt_sha,
            expected_binding_sha256=binding_sha,
            repository_root=tmp_path,
        )
        assert verified["input_binding"]["current_symbols"] == ("2317", "2330")
        with pytest.raises(_ReachedContextLoad):
            run_sidecar(
                expected_binding_sha=binding_sha,
                expected_receipt_sha=receipt_sha,
            )
        assert context_load_calls == [True]
        context_load_calls.clear()

    mutated_binding = dict(binding)
    mutated_binding[field] = replacement
    payload["input_binding"] = mutated_binding
    mutated_binding_sha = hashlib.sha256(
        research_bridge._canonical_json_bytes(mutated_binding)
    ).hexdigest()
    payload["binding_sha256"] = mutated_binding_sha
    mutated_receipt_bytes = research_bridge._canonical_json_bytes(payload)
    receipt_path.write_bytes(mutated_receipt_bytes)
    mutated_receipt_sha = hashlib.sha256(mutated_receipt_bytes).hexdigest()

    with pytest.raises(ValueError, match="Bank binding differs from the current source/model pins"):
        run_sidecar(
            expected_binding_sha=mutated_binding_sha,
            expected_receipt_sha=mutated_receipt_sha,
        )
    assert context_load_calls == []


def test_bounded_research_cli_help_is_utf8_under_cp1252_environment() -> None:
    repository = Path(__file__).resolve().parents[1]
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "cp1252"
    completed = subprocess.run(
        [sys.executable, str(repository / "scripts" / "train_bounded_restated_research.py"), "--help"],
        cwd=repository,
        env=env,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0
    help_text = completed.stdout.decode("utf-8")
    assert "只訓練標示" in help_text


def test_restated_outcome_fit_rejects_future_current_value_and_weakened_purge() -> None:
    samples = list(_sample(index) for index in range(500))
    original = samples[0]
    future_feature = CurrentRestatedFeature(
        feature_id=_FEATURE_ID,
        value_int=250000,
        scale=2,
        observed=True,
        event_at=original.row.event_at,
        source_available_at=None,
        source_observed_at="2026-10-03T01:31:00+00:00",
        current_value_available_at="2026-10-03T01:31:00+00:00",
        source_value_hash=_SOURCE_HASH,
        source_value_hash_semantics="verified_direct_store_value_bytes",
    )
    samples[0] = CurrentRestatedResearchSample(
        row=CurrentRestatedResearchRow(
            row_id=original.row.row_id,
            symbol=original.row.symbol,
            event_date=original.row.event_date,
            event_at=original.row.event_at,
            features=(future_feature,),
            missing_mask=(),
            quality_blocked_mask=(),
            source_observed_at=future_feature.source_observed_at,
        ),
        horizon_labels=original.horizon_labels,
    )
    service = AllocationTrainingService(random_state=7)
    with pytest.raises(ValueError, match="after actual fit freeze"):
        service.fit_current_restated_outcome_only(
            samples=tuple(samples),
            feature_packs=(_PACK,),
            folds=_folds(tuple(samples)),
            training_as_of=_TRAINING_FREEZE,
            dataset_manifest_file_hash=_SOURCE_HASH,
            event_date_calendar=_event_calendar(tuple(samples)),
        )

    baseline = tuple(_sample(index) for index in range(500))
    weak_folds = list(_folds(baseline))
    weak_folds[0] = PurgedWalkForwardFold(
        fold_id="fold-001",
        train_rows=weak_folds[0].train_rows,
        test_rows=weak_folds[0].test_rows,
        test_start=weak_folds[0].test_start,
        test_end=weak_folds[0].test_end,
        purge_days=59,
        embargo_days=5,
    )
    with pytest.raises(ValueError, match="weakens required purge/embargo"):
        service.fit_current_restated_outcome_only(
            samples=baseline,
            feature_packs=(_PACK,),
            folds=tuple(weak_folds),
            training_as_of=_TRAINING_FREEZE,
            dataset_manifest_file_hash=_SOURCE_HASH,
            event_date_calendar=_event_calendar(baseline),
        )


def test_restated_label_integer_and_mask_contract_is_strict() -> None:
    with pytest.raises(TypeError, match="integer bp"):
        CurrentRestatedOutcomeLabel(
            horizon_trading_days=5,
            horizon_end_date="2023-01-06",
            available_at=_SOURCE_OBSERVED,
            benchmark_excess_return_bp=True,
            observed=True,
            source_available_at=None,
            source_observed_at=_SOURCE_OBSERVED,
            label_value_hash=_SOURCE_HASH,
        )
    with pytest.raises(ValueError, match="missing mask disagrees"):
        CurrentRestatedResearchRow(
            row_id="bad-mask",
            symbol="2330",
            event_date="2023-01-01",
            event_at="2023-01-01",
            features=(_sample(0).row.features[0],),
            missing_mask=(_FEATURE_ID,),
            quality_blocked_mask=(),
            source_observed_at=_SOURCE_OBSERVED,
        )


def test_sidecar_revalidation_ignores_generation_clocks_but_binds_values_and_sources() -> None:
    def digest(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    def make_payload(
        derived_at: str,
        *,
        numeric_hash: str | None = None,
        source_hash: str | None = None,
    ) -> dict[str, object]:
        row = {
            "symbol": "2330",
            "event_date": "2026-10-02",
            "b_row_identity_sha256": digest("verified B row identity"),
            "b_available_at": "2026-10-03T01:15:57.935204+00:00",
            "comparisons": [
                {
                    "feature_id": "daily_prices.close",
                    "b_value_int": 123400,
                    "b_decimal_exponent": 2,
                    "b_unit": "TWD/share",
                    "direct_value_int": 123400,
                    "direct_decimal_exponent": 2,
                    "direct_unit": "price_1e4",
                    "exact_decimal_match": True,
                    "b_source_value_hash": source_hash or digest("verified B source value"),
                }
            ],
            "direct_sample_id": "sample-2330-20261002",
            "direct_source_row_identity_sha256": digest("verified Direct row identity"),
            "core19_vector_sha256": digest("full vector bytes with " + derived_at),
            "core19_numeric_vector_sha256": numeric_hash or digest("same CORE19 ints and masks"),
            "core19_missing_mask": [False] * 19,
            "core19_quality_blocked_mask": [False] * 19,
            "core19_staleness_mask": [False] * 19,
        }
        return {
            "schema_version": "current-restated-b7-to-core19-bridge.v1",
            "status": "verified_exact_b7_source_match_core19_derived",
            "mode": "source_row_outcome_research",
            "event_date": "2026-10-02",
            "symbols": ["2330"],
            "b_consumption_receipt_sha256": digest("B consumption receipt"),
            "b_consumption_receipt_path": "output/ml_research/b/consumption_receipt.json",
            "b_consumption_receipt_bytes": 1024,
            "b_candidate_manifest_sha256": digest("B candidate manifest"),
            "b_adapted_manifest_sha256": digest("B adapted manifest"),
            "b_feature_registry_sha256": digest("B feature registry"),
            "b_current_observation_freeze": "2026-10-03T01:15:57.935204+00:00",
            "b_revision_status": "source_revision_unverified",
            "direct_outcome_manifest_sha256": digest("Direct outcome manifest"),
            "direct_raw_publication_manifest_sha256": digest("raw publication"),
            "direct_raw_dataset_manifest_sha256": digest("raw dataset"),
            "direct_feature_registry_sha256": digest("Direct feature registry"),
            "event_date_calendar_sha256": digest("event date calendar"),
            "source_observed_at": "2026-10-03T00:23:25.887429+00:00",
            "direct_artifact_available_at": "2026-10-03T03:23:16.680702+00:00",
            "core19_derived_at": derived_at,
            "industry_membership_status": "blocked_missing_verified_symbol_membership",
            "rows": [row],
            "historical_pit_eligible": False,
            "formal_training_eligible": False,
            "model_training_performed": False,
            "production_action_allowed": False,
        }

    def verified_bridge(payload: dict[str, object]) -> VerifiedCurrentRestatedBVectorBridge:
        payload_sha = hashlib.sha256(research_bridge._canonical_json_bytes(payload)).hexdigest()
        return VerifiedCurrentRestatedBVectorBridge(
            event_date="2026-10-02",
            vectors_by_symbol={},
            b_consumption_receipt_sha256=str(payload["b_consumption_receipt_sha256"]),
            b_candidate_manifest_sha256=str(payload["b_candidate_manifest_sha256"]),
            b_adapted_manifest_sha256=str(payload["b_adapted_manifest_sha256"]),
            b_feature_registry_sha256=str(payload["b_feature_registry_sha256"]),
            payload=payload,
            payload_sha256=payload_sha,
        )

    training_payload = make_payload("2026-10-03T03:30:00+00:00")
    refreshed_payload = make_payload("2026-10-03T04:00:00+00:00")
    training_bridge = verified_bridge(training_payload)
    refreshed_bridge = verified_bridge(refreshed_payload)
    saved_descriptor = {
        "schema_version": "current-restated-b7-to-core19-bridge.v1",
        "sha256": training_bridge.payload_sha256,
        "payload": training_payload,
    }
    assert training_bridge.payload_sha256 != refreshed_bridge.payload_sha256
    assert research_bridge._verify_current_vector_bridge_revalidation(
        saved_descriptor,
        refreshed_bridge,
    ) == training_bridge.payload_sha256

    changed_numeric = make_payload(
        "2026-10-03T04:00:00+00:00",
        numeric_hash=digest("changed CORE19 integer vector"),
    )
    with pytest.raises(ValueError, match="numeric vectors differ"):
        research_bridge._verify_current_vector_bridge_revalidation(
            saved_descriptor,
            verified_bridge(changed_numeric),
        )

    changed_source = make_payload(
        "2026-10-03T04:00:00+00:00",
        source_hash=digest("different B source row"),
    )
    with pytest.raises(ValueError, match="numeric vectors differ"):
        research_bridge._verify_current_vector_bridge_revalidation(
            saved_descriptor,
            verified_bridge(changed_source),
        )
