"""R026 同次推薦來源與 typed ML runtime input 的準備 adapter。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime
import json
from pathlib import Path
from typing import Any

from app_module.recommendation.legacy_dtos import RecommendationDTO
from app_module.recommendation.historical_snapshot_custody import (
    HistoricalRawSnapshotQueryScopeV1,
    build_historical_raw_snapshot_custody_facts_v1,
)
from app_module.recommendation.ml_preparation_facts import (
    RecommendationMLPreparationFactsV1,
    _selected_item_hash,
    build_recommendation_ml_preparation_facts_v1,
)
from app_module.recommendation.model_resolution_facts import (
    RecommendationModelResolutionEvidenceV1,
)
from app_module.recommendation.prepared_runtime_input import (
    LegacyShadowIdentityV1,
    LegacyUnboundRuleIdentityV1,
    LoadedModelRuntimeClassV1,
    MissingCandidateFeatureV1,
    MissingCandidateProjectionInputV1,
    NoModelShadowIdentityV1,
    PreparedCandidateProjectionInputV1,
    PreparedInferenceProvenanceV1,
    PreparedMLInvocationBindingV1,
    PreparedMLProjectionContextV1,
    PreparedMLRuntimeInputV1,
    RecommendationMLSparsePreparationFactsV1,
)
from app_module.recommendation_calibration_consumer import (
    _InvocationProjectionCapability,
    _NoModelProjectionCapability,
)
from data_module.ml_historical_snapshot_provider import (
    HISTORICAL_SNAPSHOT_PROVIDER_CONTRACT_ID_V1,
    HistoricalRawSnapshot,
)
from decision_module.recommendation.contracts import RecommendationItem
from ml_module.historical_contracts import HistoricalFeatureRow
from ml_module.historical_feature_builder import HistoricalFeatureBuilder
from ml_module.prepared_source_contract import VerifiedSourceContractEvidenceV1
from ml_module.recommendation_inference_provenance import RecommendationProvenanceError
from ml_module.recommendation_probability_transform import NULL_BENCHMARK_BASELINE_ID


def read_source_contract_bytes_for_preparation(
    binding: Mapping[str, Any] | None,
) -> bytes | None:
    """只在準備階段讀取一次設定中的 source-contract bytes。"""

    if binding is None:
        return None
    path_text = str(binding.get("contract_path") or "")
    contract_path = Path(path_text).expanduser().resolve()
    if contract_path.is_symlink() or not contract_path.is_file():
        raise RecommendationProvenanceError("source contract receipt is missing")
    return contract_path.read_bytes()


def build_prepared_runtime_input_v1(
    *,
    selected_items: Sequence[RecommendationItem],
    recommendations: Sequence[RecommendationDTO],
    feature_rows: Sequence[HistoricalFeatureRow],
    feature_builder: HistoricalFeatureBuilder,
    snapshot: HistoricalRawSnapshot,
    capability: _InvocationProjectionCapability | _NoModelProjectionCapability,
    active_identity: Mapping[str, Any] | None,
    result_id: str,
    history_start_date: str,
    invocation_scope_id: str,
    decision_clock: datetime,
    inference_provenance: Mapping[str, Any] | None,
    source_contract_evidence: VerifiedSourceContractEvidenceV1 | None,
    rule_probability_by_symbol: Mapping[str, int],
    after_cost_rule_probability_by_symbol: Mapping[str, int],
    after_cost_rule_baseline_id_by_symbol: Mapping[str, str],
    selection_authority: str,
    selection_score_kind: str,
    selection_percentile_kind: str,
    top_n_changed_by_model: bool,
) -> PreparedMLRuntimeInputV1:
    """把同次 selected items 與 canonical rows 封存為 runtime input。"""

    if len(selected_items) != len(recommendations) or not selected_items:
        raise ValueError("selected items 與 recommendation DTO 必須同序同數")
    if not result_id:
        raise ValueError("runtime preparation requires the application result_id")
    no_model_identity: NoModelShadowIdentityV1 | None = None
    if type(capability) is _NoModelProjectionCapability:
        if active_identity not in (None, {}):
            raise ValueError("no-model preparation cannot carry an active identity")
        no_model_identity = capability.no_model_identity
        if type(no_model_identity) is not NoModelShadowIdentityV1:
            raise TypeError("no-model capability has no exact terminal identity")
    elif type(capability) is _InvocationProjectionCapability:
        if type(capability.model_resolution_evidence) is not RecommendationModelResolutionEvidenceV1:
            raise TypeError("invocation capability has no exact model-resolution evidence")
        if not isinstance(active_identity, Mapping) or not active_identity:
            raise ValueError("active-model preparation requires the captured identity")
    else:
        raise TypeError("runtime preparation requires an exact invocation capability")

    items = tuple(selected_items)
    dtos = tuple(recommendations)
    item_symbols = tuple(item.stock_code for item in items)
    dto_symbols = tuple(str(item.stock_code) for item in dtos)
    if item_symbols != dto_symbols or len(set(item_symbols)) != len(item_symbols):
        raise ValueError("selected items 與 recommendation DTO 順序/identity 不一致")
    rows_by_symbol = {row.symbol: row for row in feature_rows}
    if len(rows_by_symbol) != len(feature_rows):
        raise ValueError("canonical feature rows 含重複 symbol")
    present_indexes = tuple(
        index for index, symbol in enumerate(item_symbols) if symbol in rows_by_symbol
    )
    missing_indexes = tuple(
        index for index, symbol in enumerate(item_symbols) if symbol not in rows_by_symbol
    )
    present_items = tuple(items[index] for index in present_indexes)
    present_rows = tuple(rows_by_symbol[items[index].stock_code] for index in present_indexes)
    decision_day = date.fromisoformat(snapshot.decision_date)
    cutoff_day = date.fromisoformat(snapshot.feature_as_of_date)
    present_facts = (
        build_recommendation_ml_preparation_facts_v1(
            result_id=result_id,
            decision_date=decision_day,
            feature_cutoff_date=cutoff_day,
            selected_items=present_items,
            feature_rows=present_rows,
            feature_builder=feature_builder,
        )
        if present_items
        else None
    )
    if not missing_indexes:
        if present_facts is None:
            raise ValueError("complete preparation facts are missing")
        preparation_facts: (
            RecommendationMLPreparationFactsV1 | RecommendationMLSparsePreparationFactsV1
        ) = present_facts
        missing_by_index: dict[int, MissingCandidateFeatureV1] = {}
    else:
        registry = feature_builder._registry
        load_contract = feature_builder.load_contract
        missing_by_index = {
            index: MissingCandidateFeatureV1(
                symbol=items[index].stock_code,
                selection_index=index,
                selected_item_sha256=_selected_item_hash(items[index]),
                reason="historical_price_row_missing",
            )
            for index in missing_indexes
        }
        preparation_facts = RecommendationMLSparsePreparationFactsV1(
            result_id=result_id,
            decision_date=decision_day,
            feature_cutoff_date=cutoff_day,
            feature_registry_id=registry.registry_id,
            feature_registry_hash=load_contract.registry_hash,
            feature_schema=load_contract.canonical_schema,
            feature_ids=load_contract.canonical_ids,
            feature_schema_hash=load_contract.schema_hash,
            feature_load_contract_hash=load_contract.contract_hash,
            present_facts=present_facts,
            missing_candidates=tuple(missing_by_index[index] for index in missing_indexes),
        )

    candidates: list[
        PreparedCandidateProjectionInputV1 | MissingCandidateProjectionInputV1
    ] = []
    present_candidate_by_symbol = (
        {} if present_facts is None else {item.symbol: item for item in present_facts.candidates}
    )
    for index, item in enumerate(items):
        symbol = item.stock_code
        dto = dtos[index]
        ranking_percentile = (
            int(dto.score_percentile_bp)
            if dto.score_percentile_bp is not None
            else None
        )
        if index in missing_by_index:
            candidates.append(
                MissingCandidateProjectionInputV1(
                    missing_feature=missing_by_index[index],
                    rule_probability_bp=rule_probability_by_symbol.get(symbol),
                    after_cost_rule_probability_bp=(
                        after_cost_rule_probability_by_symbol.get(symbol)
                    ),
                    after_cost_rule_baseline_id=(
                        after_cost_rule_baseline_id_by_symbol.get(symbol)
                    ),
                    ranking_percentile_bp=ranking_percentile,
                )
            )
            continue
        fact = present_candidate_by_symbol.get(symbol)
        if fact is None:
            raise ValueError("present selected item has no matching candidate fact")
        candidates.append(
            PreparedCandidateProjectionInputV1(
                candidate_id=fact.candidate_id,
                symbol=symbol,
                rule_probability_bp=rule_probability_by_symbol.get(symbol),
                after_cost_rule_probability_bp=(
                    after_cost_rule_probability_by_symbol.get(symbol)
                ),
                after_cost_rule_baseline_id=(
                    after_cost_rule_baseline_id_by_symbol.get(symbol)
                ),
                ranking_percentile_bp=ranking_percentile,
            )
        )

    projection_context = PreparedMLProjectionContextV1(
        candidates=tuple(candidates),
        rule_baseline_id=NULL_BENCHMARK_BASELINE_ID,
        data_quality="observed",
        selection_authority=selection_authority,
        selection_score_kind=selection_score_kind,
        selection_percentile_kind=selection_percentile_kind,
        top_n_changed_by_model=top_n_changed_by_model,
    )
    provider_contract_id = snapshot.provider_contract_id
    if provider_contract_id != HISTORICAL_SNAPSHOT_PROVIDER_CONTRACT_ID_V1:
        raise ValueError("provider snapshot has no approved source contract ID")
    query_scope = HistoricalRawSnapshotQueryScopeV1(
        source_id=provider_contract_id,
        decision_date=decision_day,
        history_start_date=date.fromisoformat(history_start_date),
        symbols=tuple(sorted(item_symbols)),
        industry_index_names=(),
    )
    custody_facts = build_historical_raw_snapshot_custody_facts_v1(
        snapshot=snapshot,
        query_scope=query_scope,
    )
    if type(capability) is _NoModelProjectionCapability:
        assert no_model_identity is not None
        if no_model_identity.decision_date != decision_day.isoformat():
            raise ValueError("no-model identity 與 historical snapshot decision date 不一致")
        identity: LegacyShadowIdentityV1 | NoModelShadowIdentityV1 = no_model_identity
        expected_identity_bytes = _canonical_json_bytes({})
    elif type(capability) is _InvocationProjectionCapability:
        runtime_class = capability.loaded_model_runtime_class
        model_resolution = capability.model_resolution_evidence
        identity = LegacyShadowIdentityV1(
            model_resolution=model_resolution,
            unknown_model_binding_fields=model_resolution.missing_model_binding,
            loaded_model_runtime_class=LoadedModelRuntimeClassV1(
                module=runtime_class[0], qualified_name=runtime_class[1]
            ),
            ml_snapshot_refs=(custody_facts.to_snapshot_reference(),),
            rule_identity=LegacyUnboundRuleIdentityV1(
                reason="legacy_source_identity_unbound"
            ),
        )
        expected_identity_bytes = _canonical_json_bytes(dict(active_identity or {}))
    else:
        raise TypeError("runtime preparation requires an exact invocation capability")
    typed_provenance = (
        PreparedInferenceProvenanceV1(
            canonical_json_bytes=_canonical_json_bytes(dict(inference_provenance))
        )
        if inference_provenance is not None
        else None
    )
    return PreparedMLRuntimeInputV1(
        identity=identity,
        preparation_facts=preparation_facts,
        projection_context=projection_context,
        invocation_binding=PreparedMLInvocationBindingV1(
            invocation_scope_id=invocation_scope_id,
            expected_identity_canonical_json_bytes=expected_identity_bytes,
        ),
        inference_provenance=typed_provenance,
        decision_clock=decision_clock,
        invocation_capability=capability,
        source_contract_evidence=source_contract_evidence,
    )


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
