from __future__ import annotations

from copy import copy, deepcopy
from dataclasses import FrozenInstanceError, replace
from datetime import date, datetime, timedelta, timezone, tzinfo
from decimal import Decimal
import hashlib
import json
import pickle
from pathlib import Path
from typing import Any, cast

import pytest

from app_module.recommendation.ml_preparation_facts import (
    RecommendationMLPreparationFactsV1,
    build_recommendation_ml_preparation_facts_v1,
    _selected_item_hash,
)
from app_module.recommendation.model_resolution_facts import (
    ArtifactPathVerificationV1,
    CandidateResolutionIdentityV1,
    ModelArtifactDeclarationV1,
    ModelResolutionLibraryVersionV1,
    ModelRuntimeProfileV1,
    ProbabilityLineageIdentityV1,
    RecommendationModelResolutionEvidenceV1,
    TrainingLineageResolutionV1,
    UnknownModelBindingFieldsV1,
)
from app_module.recommendation.prepared_runtime_input import (
    BoundRuleSnapshotsV1,
    LegacyShadowIdentityV1,
    LegacyUnboundRuleIdentityV1,
    LoadedModelRuntimeClassV1,
    MissingCandidateFeatureV1,
    MissingCandidateProjectionInputV1,
    PreparedCandidateProjectionInputV1,
    PreparedInferenceProvenanceV1,
    PreparedMLInvocationBindingV1,
    PreparedMLProjectionContextV1,
    PreparedMLRuntimeInputV1,
    RecommendationMLSparsePreparationFactsV1,
    StrictPreparedMLIdentityV1,
)
from decision_module.recommendation.contracts import RecommendationItem
from ml_module.feature_registry import CORE_LONG_HISTORY_FEATURE_REGISTRY
from ml_module.historical_contracts import HistoricalFeatureRow
from ml_module.historical_feature_builder import HistoricalFeatureBuilder
from ml_module.prepared_input_contract import (
    AvailabilityBinding,
    AvailabilityStatus,
    CandidateIdentity,
    DateRange,
    FeatureContract,
    FeatureSchemaItem,
    LibraryVersion,
    ModelBinding,
    PermissionStatus,
    PreparedMLInput,
    QuarantineStatus,
    SnapshotKind,
    SnapshotQualityStatus,
    SnapshotReference,
    SnapshotScopeStatus,
)
from ml_module.prepared_source_contract import (
    SourceContractFeatureRowV1,
    VerifiedSourceContractEvidenceV1,
    build_verified_source_contract_evidence_v1,
)
from ml_module.recommendation_inference_provenance import (
    _hash_payload,
    _source_contract_feature_rows_hash,
    verify_source_contract_binding,
)


DECISION_DAY = date(2026, 9, 25)
FEATURE_CUTOFF = date(2026, 9, 24)
HASH_A = "sha256:" + "a" * 64
HASH_B = "sha256:" + "b" * 64
HASH_C = "sha256:" + "c" * 64
HASH_D = "sha256:" + "d" * 64
HASH_E = "sha256:" + "e" * 64


def _item(symbol: str, index: int) -> RecommendationItem:
    return RecommendationItem(
        stock_code=symbol,
        rule_score=Decimal(f"{index + 1}.25"),
        rank=index + 1,
        reasons=(f"rule-{symbol}",),
    )


def _feature_row(symbol: str, seed: int) -> HistoricalFeatureRow:
    values = tuple(
        (feature_id, None if index == 3 else seed + index)
        for index, feature_id in enumerate(
            CORE_LONG_HISTORY_FEATURE_REGISTRY.canonical_ids
        )
    )
    return HistoricalFeatureRow(
        symbol=symbol,
        decision_date=DECISION_DAY.isoformat(),
        feature_as_of_date=FEATURE_CUTOFF.isoformat(),
        available_date=FEATURE_CUTOFF.isoformat(),
        values=values,
    )


def _facts(symbols: tuple[str, ...] = ("2330", "2317")) -> RecommendationMLPreparationFactsV1:
    return build_recommendation_ml_preparation_facts_v1(
        result_id="result:prepared-runtime-v1",
        decision_date=DECISION_DAY,
        feature_cutoff_date=FEATURE_CUTOFF,
        selected_items=tuple(_item(symbol, index) for index, symbol in enumerate(symbols)),
        feature_rows=tuple(_feature_row(symbol, 100 * (index + 1)) for index, symbol in enumerate(symbols)),
        feature_builder=HistoricalFeatureBuilder(CORE_LONG_HISTORY_FEATURE_REGISTRY),
    )


def _snapshot(
    facts: Any,
    snapshot_id: str,
    *,
    row_end: date | None = None,
    availability: AvailabilityBinding | None = None,
) -> SnapshotReference:
    cutoff = facts.feature_cutoff_date
    return SnapshotReference(
        snapshot_id=snapshot_id,
        source_id=f"source:{snapshot_id}",
        kind=SnapshotKind.BOUNDED,
        dataset_id=None,
        schema_version="prepared-runtime.test.v1",
        content_hash=HASH_A,
        row_identity_hash=HASH_B,
        row_count=1,
        row_range=DateRange(cutoff - timedelta(days=1), row_end or cutoff),
        source_revision=None,
        availability=availability or AvailabilityBinding(AvailabilityStatus.UNKNOWN),
        quality_status=SnapshotQualityStatus.COMPLETE,
        missing_inputs=(),
        scope_status=SnapshotScopeStatus.PIT,
    )


def _strict_input(
    facts: Any,
    decision_at: datetime,
) -> PreparedMLInput:
    schema = tuple(
        FeatureSchemaItem(feature_id, dtype, unit)
        for feature_id, dtype, unit in facts.feature_schema
    )
    contract = FeatureContract(
        feature_schema=schema,
        feature_registry_hash=facts.feature_registry_hash,
        transform_contract_id="test-transform",
        transform_contract_version="v1",
        transform_contract_hash=HASH_B,
        missing_value_policy="missing-is-not-zero",
        mask_policy="observed-zero;missing-one",
        normalization_policy="training-fitted",
    )
    binding = ModelBinding(
        model_id="model:strict-test",
        release_id="release:strict-test",
        model_family="recommendation-test",
        training_dataset_id="dataset:training-test",
        training_dataset_hash=HASH_C,
        feature_registry_hash=facts.feature_registry_hash,
        label_registry_hash=HASH_D,
        transform_contract_hash=HASH_B,
        artifact_hash=HASH_A,
        manifest_hash=HASH_E,
        qualified_class_path="test_models.StrictModel",
        serialization_format="joblib",
        library_versions=(LibraryVersion("python", "3.11.9"),),
        quarantine_status=QuarantineStatus.CLEAR,
        shadow_only=True,
        production_eligible=False,
        production_action_allowed=False,
        permission_status=PermissionStatus.GRANTED,
    )
    start = facts.feature_cutoff_date - timedelta(days=1)
    return PreparedMLInput(
        result_id=facts.result_id,
        decision_date=facts.decision_date,
        decision_at=decision_at,
        as_of_date=facts.decision_date,
        feature_cutoff_date=facts.feature_cutoff_date,
        mode="shadow-test",
        candidate_identities=tuple(
            CandidateIdentity(item.candidate_id, item.symbol)
            for item in facts.candidates
        ),
        rule_snapshot_refs=(_snapshot(facts, "rule:strict", row_end=facts.feature_cutoff_date),),
        ml_snapshot_refs=(_snapshot(facts, "ml:strict", row_end=facts.feature_cutoff_date),),
        feature_contract=contract,
        model_binding=binding,
    )


def _present_context(
    facts: RecommendationMLPreparationFactsV1,
) -> PreparedMLProjectionContextV1:
    candidates = tuple(
        PreparedCandidateProjectionInputV1(
            candidate_id=item.candidate_id,
            symbol=item.symbol,
            rule_probability_bp=10_123 - index,
            after_cost_rule_probability_bp=None if index else 8_850,
            after_cost_rule_baseline_id=None if index else "cost-baseline:original",
            ranking_percentile_bp=9_999 - index,
        )
        for index, item in enumerate(facts.candidates)
    )
    return PreparedMLProjectionContextV1(
        candidates=candidates,
        rule_baseline_id="rule-baseline:original",
        data_quality="observed",
        selection_authority="rule_top_n",
        selection_score_kind="rule_total_score",
        selection_percentile_kind="rule_percentile",
        top_n_changed_by_model=False,
    )


def _context_symbols(context: PreparedMLProjectionContextV1) -> tuple[str, ...]:
    symbols: list[str] = []
    for item in context.candidates:
        if type(item) is MissingCandidateProjectionInputV1:
            symbols.append(item.missing_feature.symbol)
        else:
            symbols.append(cast(PreparedCandidateProjectionInputV1, item).symbol)
    return tuple(symbols)


def _legacy_resolution(decision_day: date) -> RecommendationModelResolutionEvidenceV1:
    model_id = "model:legacy-test"
    manifest_hash = HASH_A
    artifact_hash = HASH_B
    freeze_hash = HASH_C
    dataset_hash = HASH_D
    missing = UnknownModelBindingFieldsV1(transform_status="legacy_unproven")
    candidate = CandidateResolutionIdentityV1(
        candidate_id=model_id,
        manifest_hash=manifest_hash,
        artifact_hash=artifact_hash,
        freeze_hash=freeze_hash,
        dataset_hash=dataset_hash,
        candidate_training_cutoff="2026-01-01",
        candidate_identity_claim_hash=HASH_E,
        pointer_schema_version="pointer.v1",
        pointer_bytes_check="equal_before_after_resolve",
        candidate_path_check="identity_rechecked_by_path_read_same_bytes_not_proven",
    )
    manifest = ModelArtifactDeclarationV1(
        manifest_schema_version="manifest.v1",
        model_id=model_id,
        dataset_id="dataset:legacy",
        created_run_id="run:legacy",
        created_at="2026-01-02T00:00:00+00:00",
        model_family="recommendation-test",
        feature_registry_hash=HASH_A,
        label_registry_hash=HASH_B,
        feature_schema=(("feature-a", "int32", "unit"),),
        training_as_of="2025-12-31",
        loaded_model_training_as_of=None,
        hyperparameters_hash=HASH_C,
        research_alpha_bp=0,
        production_alpha_bp=0,
        blend_selection_metric="balanced_accuracy",
        blend_selection_label_cutoff="2025-12-01",
        blend_selection_threshold_bp=0,
        serialization_format="joblib",
        artifact_filename="model.joblib",
        artifact_hash=artifact_hash,
        manifest_hash=manifest_hash,
        recorded_library_versions=(ModelResolutionLibraryVersionV1("numpy", "2.3.5"),),
        frozen=True,
        shadow_only=True,
        production_eligible=False,
        production_action_allowed=False,
    )
    training = TrainingLineageResolutionV1(
        status="legacy_unproven",
        reason="legacy manifest lacks training lineage",
        provenance_schema_version="legacy-training.v1",
        manifest_hash=None,
        training_source_hash=None,
        training_pit_hash=None,
        feature_registry_hash=None,
        feature_schema_hash=None,
        feature_transform_contract_hash=None,
        transform_status="legacy_unproven",
        dataset_id=None,
        dataset_hash=None,
        decision_date=None,
        training_as_of=None,
        training_semantics=None,
        decision_time_eligible=None,
        research_only=None,
        cost_scenario_hash=None,
    )
    lineage = ProbabilityLineageIdentityV1(
        position=0,
        kind="active_model",
        candidate_id=model_id,
        model_id=model_id,
        manifest_hash=manifest_hash,
        artifact_hash=artifact_hash,
        freeze_hash=freeze_hash,
        dataset_hash=dataset_hash,
        baseline_id="null-benchmark.v1",
        baseline_kind="null_benchmark",
        transform_id="probability-transform.v1",
        maximum_probability_change_bp=0,
        node_sha256=HASH_E,
    )
    return RecommendationModelResolutionEvidenceV1(
        decision_date=decision_day.isoformat(),
        candidate=candidate,
        manifest=manifest,
        artifact=ArtifactPathVerificationV1(
            declared_artifact_hash=artifact_hash,
            path_verified_artifact_hash=artifact_hash,
        ),
        training=training,
        probability_lineage=(lineage,),
        probability_lineage_sha256=HASH_A,
        runtime_profile=ModelRuntimeProfileV1(
            platform="test-platform",
            python_version=(3, 11, 9),
            library_versions=(ModelResolutionLibraryVersionV1("numpy", "2.3.5"),),
        ),
        missing_model_binding=missing,
    )


def _runtime(
    facts: Any,
    context: PreparedMLProjectionContextV1,
    *,
    identity: Any | None = None,
    decision_at: datetime | None = None,
    inference_provenance: PreparedInferenceProvenanceV1 | None = None,
    source_evidence: VerifiedSourceContractEvidenceV1 | None = None,
) -> PreparedMLRuntimeInputV1:
    clock = decision_at or datetime(2026, 9, 25, 9, 0, tzinfo=timezone.utc)
    if identity is None:
        if type(facts) is RecommendationMLPreparationFactsV1:
            identity = StrictPreparedMLIdentityV1(_strict_input(facts, clock))
        else:
            identity = _legacy_identity(facts, context)
    invocation = PreparedMLInvocationBindingV1(
        invocation_scope_id="scope:prepared-runtime-test",
        expected_identity_canonical_json_bytes=b'{"candidate_id":"model:active","symbols":["2330"]}',
    )
    return PreparedMLRuntimeInputV1(
        identity=identity,
        preparation_facts=facts,
        projection_context=context,
        invocation_binding=invocation,
        inference_provenance=inference_provenance,
        decision_clock=clock,
        invocation_capability=object(),
        source_contract_evidence=source_evidence,
    )


def test_present_runtime_keeps_ordered_context_and_blocks_copy_or_serialization() -> None:
    facts = _facts()
    caller_list = list(_present_context(facts).candidates)
    context = PreparedMLProjectionContextV1(
        candidates=caller_list,  # type: ignore[arg-type]
        rule_baseline_id="rule-baseline:original",
        data_quality="observed",
        selection_authority="rule_top_n",
        selection_score_kind="rule_total_score",
        selection_percentile_kind="rule_percentile",
        top_n_changed_by_model=True,
    )
    capability = object()
    clock = datetime(2026, 9, 25, 9, 0, tzinfo=timezone.utc)
    input_value = PreparedMLRuntimeInputV1(
        identity=StrictPreparedMLIdentityV1(
            _strict_input(facts, clock)
        ),
        preparation_facts=facts,
        projection_context=context,
        invocation_binding=PreparedMLInvocationBindingV1(
            "scope:present",
            b'{"candidate_id":"model-active","symbols":["2330","2317"]}',
        ),
        inference_provenance=None,
        decision_clock=clock,
        invocation_capability=capability,
    )
    caller_list.clear()

    assert _context_symbols(input_value.projection_context) == (
        "2330",
        "2317",
    )
    first_projection = cast(
        PreparedCandidateProjectionInputV1,
        input_value.projection_context.candidates[0],
    )
    second_projection = cast(
        PreparedCandidateProjectionInputV1,
        input_value.projection_context.candidates[1],
    )
    assert first_projection.rule_probability_bp == 10_123
    assert first_projection.after_cost_rule_probability_bp == 8_850
    assert second_projection.after_cost_rule_probability_bp is None
    assert input_value.projection_context.top_n_changed_by_model is True
    assert input_value.inference_provenance is None
    assert "invocation_capability" not in repr(input_value)
    assert "<object object" not in repr(input_value)
    with pytest.raises(TypeError, match="不可複製"):
        copy(input_value)
    with pytest.raises(TypeError, match="不可深複製"):
        deepcopy(input_value)
    with pytest.raises(TypeError, match="不可序列化"):
        pickle.dumps(input_value)
    with pytest.raises(FrozenInstanceError):
        input_value.decision_clock = clock  # type: ignore[misc]


def test_runtime_rejects_projection_identity_mismatch_and_noncanonical_bytes() -> None:
    facts = _facts()
    correct = _present_context(facts)
    changed = list(correct.candidates)
    first_candidate = cast(PreparedCandidateProjectionInputV1, changed[0])
    changed[0] = PreparedCandidateProjectionInputV1(
        candidate_id="candidate.v1:" + "0" * 64,
        symbol=first_candidate.symbol,
        rule_probability_bp=first_candidate.rule_probability_bp,
        after_cost_rule_probability_bp=first_candidate.after_cost_rule_probability_bp,
        after_cost_rule_baseline_id=first_candidate.after_cost_rule_baseline_id,
        ranking_percentile_bp=first_candidate.ranking_percentile_bp,
    )
    mismatched = PreparedMLProjectionContextV1(
        candidates=tuple(changed),
        rule_baseline_id=correct.rule_baseline_id,
        data_quality=correct.data_quality,
        selection_authority=correct.selection_authority,
        selection_score_kind=correct.selection_score_kind,
        selection_percentile_kind=correct.selection_percentile_kind,
        top_n_changed_by_model=correct.top_n_changed_by_model,
    )
    with pytest.raises(ValueError, match="candidate.*不一致"):
        _runtime(facts, mismatched)
    with pytest.raises(ValueError, match="canonical JSON"):
        PreparedMLInvocationBindingV1(
            "scope:bad",
            b'{ "candidate_id": "model-active" }',
        )
    with pytest.raises(ValueError, match="JSON object"):
        PreparedInferenceProvenanceV1(b"[]")


def test_strict_identity_rejects_same_symbol_with_different_opaque_candidate_id() -> None:
    facts = _facts(("2330",))
    context = _present_context(facts)
    clock = datetime(2026, 9, 25, 9, 0, tzinfo=timezone.utc)
    prepared = _strict_input(facts, clock)
    changed_identities = (
        CandidateIdentity("strict-other-id", facts.candidates[0].symbol),
    )
    mismatched = replace(prepared, candidate_identities=changed_identities)

    with pytest.raises(ValueError, match="candidate ID／symbol"):
        _runtime(
            facts,
            context,
            identity=StrictPreparedMLIdentityV1(mismatched),
            decision_at=clock,
        )


class _MutableTimezone(tzinfo):
    def __init__(self) -> None:
        self.offset = timedelta(hours=3)

    def utcoffset(self, _value: datetime | None) -> timedelta:
        return self.offset

    def dst(self, _value: datetime | None) -> timedelta:
        return timedelta(0)

    def tzname(self, _value: datetime | None) -> str:
        return "mutable-test-zone"


def test_runtime_freezes_mutable_timezone_offset_at_invocation_creation() -> None:
    facts = _facts()
    context = _present_context(facts)
    mutable_zone = _MutableTimezone()
    clock = datetime(2026, 9, 25, 12, 0, tzinfo=mutable_zone)
    input_value = _runtime(facts, context, decision_at=clock)
    captured_offset = input_value.decision_clock.utcoffset()
    assert captured_offset == timedelta(hours=3)

    mutable_zone.offset = timedelta(hours=9)

    assert input_value.decision_clock.utcoffset() == captured_offset
    assert input_value.decision_clock.isoformat() == "2026-09-25T12:00:00+03:00"


def _sparse_facts(
    present: RecommendationMLPreparationFactsV1 | None,
    metadata: RecommendationMLPreparationFactsV1,
    missing: tuple[MissingCandidateFeatureV1, ...],
) -> RecommendationMLSparsePreparationFactsV1:
    return RecommendationMLSparsePreparationFactsV1(
        result_id=metadata.result_id,
        decision_date=metadata.decision_date,
        feature_cutoff_date=metadata.feature_cutoff_date,
        feature_registry_id=metadata.feature_registry_id,
        feature_registry_hash=metadata.feature_registry_hash,
        feature_schema=metadata.feature_schema,
        feature_ids=metadata.feature_ids,
        feature_schema_hash=metadata.feature_schema_hash,
        feature_load_contract_hash=metadata.feature_load_contract_hash,
        present_facts=present,
        missing_candidates=missing,
    )


def _missing_context(
    present: RecommendationMLPreparationFactsV1 | None,
    missing: tuple[MissingCandidateFeatureV1, ...],
) -> PreparedMLProjectionContextV1:
    all_count = (0 if present is None else len(present.candidates)) + len(missing)
    missing_by_index = {item.selection_index: item for item in missing}
    present_iter = iter(() if present is None else present.candidates)
    candidates: list[PreparedCandidateProjectionInputV1 | MissingCandidateProjectionInputV1] = []
    for index in range(all_count):
        absent = missing_by_index.get(index)
        if absent is not None:
            candidates.append(
                MissingCandidateProjectionInputV1(
                    missing_feature=absent,
                    rule_probability_bp=7_800 + index,
                    after_cost_rule_probability_bp=None,
                    after_cost_rule_baseline_id=None,
                    ranking_percentile_bp=8_800 + index,
                )
            )
            continue
        present_candidate = next(present_iter)
        candidates.append(
            PreparedCandidateProjectionInputV1(
                candidate_id=present_candidate.candidate_id,
                symbol=present_candidate.symbol,
                rule_probability_bp=9_100 + index,
                after_cost_rule_probability_bp=8_800,
                after_cost_rule_baseline_id="cost-baseline:present",
                ranking_percentile_bp=9_500 - index,
            )
        )
    return PreparedMLProjectionContextV1(
        candidates=tuple(candidates),
        rule_baseline_id="rule-baseline:sparse",
        data_quality="observed_with_missing_feature_rows",
        selection_authority="rule_top_n",
        selection_score_kind="rule_total_score",
        selection_percentile_kind="rule_percentile",
        top_n_changed_by_model=False,
    )


def test_mixed_and_all_missing_candidates_keep_identity_without_fake_vectors() -> None:
    present = _facts(("2330",))
    selected_missing_item = _item("2317", 1)
    missing = MissingCandidateFeatureV1(
        symbol="2317",
        selection_index=1,
        selected_item_sha256=_selected_item_hash(selected_missing_item),
        reason="historical_price_row_missing",
    )
    mixed = _sparse_facts(present, present, (missing,))
    mixed_context = _missing_context(present, (missing,))
    mixed_input = _runtime(mixed, mixed_context)

    assert mixed.present_facts is present
    assert type(mixed_context.candidates[0]) is PreparedCandidateProjectionInputV1
    assert type(mixed_context.candidates[1]) is MissingCandidateProjectionInputV1
    assert mixed_context.candidates[1].missing_feature == missing
    assert mixed_context.candidates[1].rule_probability_bp == 7_801
    assert not hasattr(missing, "candidate_id")
    assert not hasattr(missing, "feature_values")
    assert type(mixed_input.preparation_facts) is RecommendationMLSparsePreparationFactsV1
    assert mixed_input.preparation_facts.missing_candidates == (missing,)

    missing_first_item = _item("1101", 0)
    missing_second_item = _item("2317", 1)
    all_missing = (
        MissingCandidateFeatureV1(
            symbol="1101",
            selection_index=0,
            selected_item_sha256=_selected_item_hash(missing_first_item),
            reason="historical_price_row_missing",
        ),
        MissingCandidateFeatureV1(
            symbol="2317",
            selection_index=1,
            selected_item_sha256=_selected_item_hash(missing_second_item),
            reason="historical_price_row_missing",
        ),
    )
    all_missing_facts = _sparse_facts(None, present, all_missing)
    all_missing_context = _missing_context(None, all_missing)
    all_missing_input = _runtime(all_missing_facts, all_missing_context)
    assert all_missing_facts.present_facts is None
    assert tuple(
        cast(MissingCandidateProjectionInputV1, item).missing_feature
        for item in all_missing_context.candidates
    ) == all_missing
    assert len(all_missing_input.projection_context.candidates) == 2


def test_strict_identity_explicitly_rejects_sparse_missing_candidate_ids() -> None:
    metadata = _facts(("2330",))
    missing = MissingCandidateFeatureV1(
        symbol="2317",
        selection_index=0,
        selected_item_sha256=_selected_item_hash(_item("2317", 0)),
        reason="historical_price_row_missing",
    )
    facts = _sparse_facts(None, metadata, (missing,))
    context = _missing_context(None, (missing,))
    clock = datetime(2026, 9, 25, 9, 0, tzinfo=timezone.utc)

    with pytest.raises(ValueError, match="strict identity 不支援 sparse"):
        _runtime(
            facts,
            context,
            identity=StrictPreparedMLIdentityV1(_strict_input(metadata, clock)),
            decision_at=clock,
        )


def test_sparse_missing_position_must_match_full_selection_order() -> None:
    present = _facts(("2330",))
    missing = MissingCandidateFeatureV1(
        symbol="2317",
        selection_index=1,
        selected_item_sha256=_selected_item_hash(_item("2317", 1)),
        reason="historical_price_row_missing",
    )
    facts = _sparse_facts(present, present, (missing,))
    context = _missing_context(present, (missing,))
    reversed_context = PreparedMLProjectionContextV1(
        candidates=tuple(reversed(context.candidates)),
        rule_baseline_id=context.rule_baseline_id,
        data_quality=context.data_quality,
        selection_authority=context.selection_authority,
        selection_score_kind=context.selection_score_kind,
        selection_percentile_kind=context.selection_percentile_kind,
        top_n_changed_by_model=context.top_n_changed_by_model,
    )
    with pytest.raises(ValueError, match="feature row 的位置|projection input"):
        _runtime(facts, reversed_context)


def _legacy_identity(
    facts: Any,
    context: PreparedMLProjectionContextV1,
    *,
    ml_refs: tuple[SnapshotReference, ...] | None = None,
) -> LegacyShadowIdentityV1:
    return LegacyShadowIdentityV1(
        model_resolution=_legacy_resolution(facts.decision_date),
        unknown_model_binding_fields=UnknownModelBindingFieldsV1(
            transform_status="legacy_unproven"
        ),
        loaded_model_runtime_class=LoadedModelRuntimeClassV1(
            "legacy.loaded.module", "ObservedModel"
        ),
        ml_snapshot_refs=ml_refs or (_snapshot(facts, "ml:legacy"),),
        rule_identity=LegacyUnboundRuleIdentityV1("legacy_source_identity_unbound"),
    )


def test_legacy_shadow_keeps_unknown_fields_and_rejects_known_future_sources() -> None:
    facts = _facts()
    context = _present_context(facts)
    unknown = _snapshot(facts, "ml:unknown")
    identity = _legacy_identity(facts, context, ml_refs=(unknown,))
    input_value = _runtime(facts, context, identity=identity)
    runtime_identity = cast(LegacyShadowIdentityV1, input_value.identity)
    assert runtime_identity.unknown_model_binding_fields.release_id is None
    assert runtime_identity.unknown_model_binding_fields.artifact_declared_qualified_class_path is None
    assert runtime_identity.unknown_model_binding_fields.quarantine_status == "unknown"
    assert runtime_identity.unknown_model_binding_fields.permission_status == "unknown"
    assert runtime_identity.loaded_model_runtime_class.qualified_name == "ObservedModel"
    assert runtime_identity.ml_snapshot_refs[0].availability.status is AvailabilityStatus.UNKNOWN

    future_at = datetime(2026, 9, 25, 10, 0, tzinfo=timezone.utc)
    future_ref = _snapshot(
        facts,
        "ml:future",
        availability=AvailabilityBinding(
            AvailabilityStatus.KNOWN,
            available_at=future_at,
        ),
    )
    future_identity = _legacy_identity(facts, context, ml_refs=(future_ref,))
    with pytest.raises(ValueError, match="晚於原始 decision_clock"):
        _runtime(facts, context, identity=future_identity)

    late_row_ref = _snapshot(
        facts,
        "ml:late-row",
        row_end=facts.feature_cutoff_date + timedelta(days=1),
    )
    late_identity = _legacy_identity(facts, context, ml_refs=(late_row_ref,))
    with pytest.raises(ValueError, match="超過共同 feature cutoff"):
        _runtime(facts, context, identity=late_identity)


def _source_contract_fixture(
    tmp_path: Path,
    *,
    snapshot_hash: str = "",
) -> dict[str, Any]:
    decision = DECISION_DAY.isoformat()
    cutoff = FEATURE_CUTOFF.isoformat()
    history = "2025-01-01"
    symbols = ["2330"]
    source_db_input = str(tmp_path / "nested" / ".." / "synthetic-source.db")
    source_db = str(Path(source_db_input).resolve())
    registry_hash = HASH_A
    schema_hash = HASH_B
    feature_ids = ["feature-a", "feature-b"]
    feature_rows = [
        {
            "row_id": "inference-row:2330",
            "symbol": "2330",
            "decision_date": decision,
            "feature_as_of_date": cutoff,
            "feature_available_date": cutoff,
            "feature_ids": feature_ids,
            "feature_values": [123, None],
            "snapshot_hash": snapshot_hash,
        }
    ]
    source_rows_hash = _source_contract_feature_rows_hash(
        source_db=source_db,
        decision_date=decision,
        history_start_date=history,
        feature_registry_hash=registry_hash,
        feature_schema_hash=schema_hash,
        symbols=symbols,
        rows=feature_rows,
    )
    snapshot_body = {
        "component": "prospective_recommendation_features",
        "source_db": source_db,
        "decision_date": decision,
        "history_start_date": history,
        "feature_registry_hash": registry_hash,
        "feature_schema_hash": schema_hash,
        "symbols": symbols,
        "rows": feature_rows,
        "rows_sha256": source_rows_hash,
    }
    snapshot = {
        **snapshot_body,
        "content_sha256": _hash_payload(snapshot_body),
    }
    contract_body = {
        "schema_version": "recommendation-source-contract.v1",
        "decision_date": decision,
        "symbols": symbols,
        "technical": {"prospective_feature_snapshot": snapshot},
    }
    contract_content_hash = _hash_payload(contract_body)
    contract_payload = {
        **contract_body,
        "contract_sha256": contract_content_hash,
        "checked_at": "2026-09-25T09:00:00+00:00",
    }
    contract_file_bytes = (
        json.dumps(contract_payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
    contract_path = (tmp_path / "configured-source-contract.json").resolve()
    contract_path.write_bytes(contract_file_bytes)
    binding: dict[str, Any] = {
        "schema_version": "recommendation-calibration-capture-source-binding.v1",
        "contract_path": str(contract_path),
        "contract_content_sha256": contract_content_hash,
        "contract_file_sha256": "sha256:" + hashlib.sha256(contract_file_bytes).hexdigest(),
        # 刻意不在 binding 內放 decision_date：既有 verifier 不要求此欄位，
        # 但會驗證 contract 自身的日期。
        "symbols": symbols,
        "price_up_prospective_status": "ready",
        "price_up_prospective_blockers": [],
        "technical_publication_receipt_file_sha256": HASH_C,
        "technical_publication_content_sha256": HASH_D,
        "technical_publication_available_at": "2026-09-25T08:00:00+00:00",
        "technical_source_available_ats": ["2026-09-25T08:00:00+00:00"],
        "feature_snapshot_content_sha256": snapshot["content_sha256"],
        "feature_snapshot_rows_sha256": source_rows_hash,
        "feature_snapshot_captured_at": "2026-09-25T08:00:00+00:00",
        "corporate_adjustment_manifest_hash": HASH_E,
        "corporate_adjustment_available_at": "2026-09-25T08:00:00+00:00",
        "official_event_available_at": "2026-09-25T08:00:00+00:00",
        "historical_pit_eligible": False,
        "source_semantics": "prospective_input_only;not_historical_backfill",
    }
    rows = [
        {
            "symbol": item["symbol"],
            "decision_date": item["decision_date"],
            "feature_as_of_date": item["feature_as_of_date"],
            "feature_available_date": item["feature_available_date"],
            "feature_ids": item["feature_ids"],
            "feature_values": item["feature_values"],
            "snapshot_hash": item["snapshot_hash"],
        }
        for item in feature_rows
    ]
    verify_source_contract_binding(
        binding,
        decision_date=decision,
        feature_rows=rows,
        feature_registry_hash=registry_hash,
        feature_schema_hash=schema_hash,
        source_database=source_db_input,
        history_start_date=history,
    )
    binding_payload_json = json.dumps(
        binding,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    typed_rows = tuple(
        SourceContractFeatureRowV1(
            symbol=cast(str, row["symbol"]),
            decision_date=cast(str, row["decision_date"]),
            feature_as_of_date=cast(str, row["feature_as_of_date"]),
            feature_available_date=cast(str, row["feature_available_date"]),
            feature_ids=tuple(cast(list[str], row["feature_ids"])),
            feature_values=tuple(cast(list[int | None], row["feature_values"])),
            snapshot_hash=cast(str, row["snapshot_hash"]),
        )
        for row in rows
    )
    return {
        "binding": binding,
        "binding_payload_json": binding_payload_json,
        "contract_file_bytes": contract_file_bytes,
        "contract_path": str(contract_path),
        "decision_date": decision,
        "symbols": tuple(symbols),
        "source_database": source_db,
        "source_database_original": source_db_input,
        "history_start_date": history,
        "feature_registry_hash": registry_hash,
        "feature_schema_hash": schema_hash,
        "feature_builder_schema_hash": None,
        "rows": typed_rows,
        "raw_rows": rows,
    }


def _build_source_evidence(fixture: dict[str, Any]) -> VerifiedSourceContractEvidenceV1:
    return build_verified_source_contract_evidence_v1(
        binding_payload_json=fixture["binding_payload_json"],
        contract_file_bytes=fixture["contract_file_bytes"],
        contract_path=fixture["contract_path"],
        decision_date=fixture["decision_date"],
        symbols=fixture["symbols"],
        source_database=fixture["source_database"],
        source_database_original=fixture["source_database_original"],
        history_start_date=fixture["history_start_date"],
        feature_registry_hash=fixture["feature_registry_hash"],
        feature_schema_hash=fixture["feature_schema_hash"],
        feature_builder_schema_hash=fixture["feature_builder_schema_hash"],
        consumed_feature_rows=fixture["rows"],
    )


def test_source_contract_leaf_matches_existing_verifier_and_preserves_opaque_row_hash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _source_contract_fixture(tmp_path, snapshot_hash="")
    evidence = _build_source_evidence(fixture)
    replay = _build_source_evidence(fixture)

    assert evidence.evidence_sha256.startswith("sha256:")
    assert evidence.evidence_sha256 == replay.evidence_sha256
    assert evidence.binding_payload_json == fixture["binding_payload_json"]
    assert evidence.contract_file_bytes == fixture["contract_file_bytes"]
    assert evidence.consumed_feature_rows[0].snapshot_hash == ""
    assert evidence.symbols == ("2330",)
    assert evidence.source_database == fixture["source_database"]
    assert evidence.source_database_original == fixture["source_database_original"]

    def no_io(*_args: Any, **_kwargs: Any) -> Any:
        pytest.fail("pure source-contract evidence builder attempted file I/O")

    monkeypatch.setattr(Path, "open", no_io)
    monkeypatch.setattr(Path, "read_bytes", no_io)
    monkeypatch.setattr(Path, "read_text", no_io)
    assert _build_source_evidence(fixture).evidence_sha256 == evidence.evidence_sha256


def test_source_contract_leaf_and_existing_verifier_reject_same_consumed_value_change(
    tmp_path: Path,
) -> None:
    fixture = _source_contract_fixture(tmp_path, snapshot_hash="opaque/source-hash-v0")
    changed_row = replace(fixture["rows"][0], feature_values=(999, None))
    changed_raw_rows = [dict(fixture["raw_rows"][0], feature_values=[999, None])]

    with pytest.raises(ValueError, match="feature rows hash|feature values"):
        verify_source_contract_binding(
            fixture["binding"],
            decision_date=fixture["decision_date"],
            feature_rows=changed_raw_rows,
            feature_registry_hash=fixture["feature_registry_hash"],
            feature_schema_hash=fixture["feature_schema_hash"],
            source_database=fixture["source_database_original"],
            history_start_date=fixture["history_start_date"],
        )
    with pytest.raises(ValueError, match="rows hash|values"):
        build_verified_source_contract_evidence_v1(
            binding_payload_json=fixture["binding_payload_json"],
            contract_file_bytes=fixture["contract_file_bytes"],
            contract_path=fixture["contract_path"],
            decision_date=fixture["decision_date"],
            symbols=fixture["symbols"],
            source_database=fixture["source_database"],
            source_database_original=fixture["source_database_original"],
            history_start_date=fixture["history_start_date"],
            feature_registry_hash=fixture["feature_registry_hash"],
            feature_schema_hash=fixture["feature_schema_hash"],
            feature_builder_schema_hash=None,
            consumed_feature_rows=(changed_row,),
        )


def test_source_contract_evidence_cannot_be_directly_forged_or_mismatched_to_provenance(
    tmp_path: Path,
) -> None:
    fixture = _source_contract_fixture(tmp_path)
    evidence = _build_source_evidence(fixture)
    with pytest.raises(TypeError, match="factory"):
        VerifiedSourceContractEvidenceV1()  # type: ignore[call-arg]

    provenance = {
        "schema_version": "recommendation-inference-provenance.v1",
        "status": "verified",
        "source_contract_binding": fixture["binding"],
    }
    provenance_bytes = json.dumps(
        provenance,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    context = _present_context(_facts(("2330",)))
    _runtime(
        _facts(("2330",)),
        context,
        inference_provenance=PreparedInferenceProvenanceV1(provenance_bytes),
        source_evidence=evidence,
    )

    changed = dict(provenance)
    changed_binding = dict(fixture["binding"])
    changed_binding["source_semantics"] = "changed"
    changed["source_contract_binding"] = changed_binding
    changed_bytes = json.dumps(
        changed,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    with pytest.raises(ValueError, match="source-contract evidence 不一致"):
        _runtime(
            _facts(("2330",)),
            _present_context(_facts(("2330",))),
            inference_provenance=PreparedInferenceProvenanceV1(changed_bytes),
            source_evidence=evidence,
        )
