"""R026 typed runtime input 的純舊投影呼叫轉接器。

這個模組只把不可變 runtime envelope 展開成目前
``RecommendationCalibrationConsumer.project_many`` 相容入口所需的同次呼叫值。
它不讀檔、不查 consumer、不載入模型，也不改寫來源 provenance payload；
capability 持有 owner，並負責把此結果送入一次性舊投影邊界。
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Mapping

from app_module.recommendation.prepared_runtime_input import (
    MissingCandidateProjectionInputV1,
    PreparedInferenceProvenanceV1,
    PreparedCandidateProjectionInputV1,
    PreparedMLRuntimeInputV1,
    RecommendationMLPreparationFactsV1,
    RecommendationMLSparsePreparationFactsV1,
    PreparedMLProjectionContextV1,
)
from ml_module.prepared_source_contract import VerifiedSourceContractEvidenceV1


@dataclass(frozen=True, slots=True)
class PreparedMLProjectionArgumentsV1:
    """單次 call-local 的相容參數；不持久化也不成為第二份 runtime truth。"""

    invocation_scope_id: str
    expected_identity: Mapping[str, Any]
    feature_values_by_symbol: Mapping[str, tuple[int | None, ...]]
    rule_probability_by_symbol: Mapping[str, int]
    after_cost_rule_probability_by_symbol: Mapping[str, int]
    after_cost_rule_baseline_id_by_symbol: Mapping[str, str]
    decision_date: str
    rule_baseline_id: str
    ranking_percentile_by_symbol: Mapping[str, int]
    data_quality: str
    inference_provenance: Mapping[str, Any] | None
    selection_authority: str
    selection_score_kind: str
    selection_percentile_kind: str
    top_n_changed_by_model: bool
    source_contract_evidence: VerifiedSourceContractEvidenceV1 | None


def prepare_ml_projection_arguments_v1(
    runtime_input: PreparedMLRuntimeInputV1,
) -> PreparedMLProjectionArgumentsV1:
    """從唯一 typed runtime input 建立舊 ``project_many`` 的暫時參數。

    Mapping 僅在此相容邊界解碼；封存 input 仍使用 canonical immutable bytes 及
    有序 typed facts/context。所有候選欄位原樣帶入，不自行補值或排序。
    """

    if type(runtime_input) is not PreparedMLRuntimeInputV1:
        raise TypeError("runtime_input 必須是 exact PreparedMLRuntimeInputV1")

    facts = runtime_input.preparation_facts
    context = runtime_input.projection_context
    binding = runtime_input.invocation_binding
    fact_candidates, projection_candidates = _aligned_candidates(facts, context)

    expected_identity = _decode_canonical_object(
        binding.expected_identity_canonical_json_bytes,
        field_name="expected_identity_canonical_json_bytes",
    )
    inference_provenance: dict[str, Any] | None = None
    if runtime_input.inference_provenance is not None:
        inference_provenance = _decode_provenance_object(
            runtime_input.inference_provenance
        )

    feature_values = {
        fact.symbol: fact.feature_values for fact in fact_candidates
    }
    rule_probabilities = {
        _projection_symbol(item): item.rule_probability_bp
        for item in projection_candidates
        if item.rule_probability_bp is not None
    }
    after_cost_probabilities = {
        _projection_symbol(item): item.after_cost_rule_probability_bp
        for item in projection_candidates
        if item.after_cost_rule_probability_bp is not None
    }
    after_cost_baseline_ids = {
        _projection_symbol(item): item.after_cost_rule_baseline_id
        for item in projection_candidates
        if item.after_cost_rule_baseline_id is not None
    }
    ranking_percentiles = {
        _projection_symbol(item): item.ranking_percentile_bp
        for item in projection_candidates
        if item.ranking_percentile_bp is not None
    }

    return PreparedMLProjectionArgumentsV1(
        invocation_scope_id=binding.invocation_scope_id,
        expected_identity=expected_identity,
        feature_values_by_symbol=feature_values,
        rule_probability_by_symbol=rule_probabilities,
        after_cost_rule_probability_by_symbol=after_cost_probabilities,
        after_cost_rule_baseline_id_by_symbol=after_cost_baseline_ids,
        decision_date=facts.decision_date.isoformat(),
        rule_baseline_id=context.rule_baseline_id,
        ranking_percentile_by_symbol=ranking_percentiles,
        data_quality=context.data_quality,
        inference_provenance=inference_provenance,
        selection_authority=context.selection_authority,
        selection_score_kind=context.selection_score_kind,
        selection_percentile_kind=context.selection_percentile_kind,
        top_n_changed_by_model=context.top_n_changed_by_model,
        source_contract_evidence=runtime_input.source_contract_evidence,
    )


def project_prepared_ml_runtime_input_v1(
    runtime_input: PreparedMLRuntimeInputV1,
) -> Mapping[str, Any]:
    """以 runtime input 唯一參數呼叫其內含的一次性 capability。"""

    if type(runtime_input) is not PreparedMLRuntimeInputV1:
        raise TypeError("runtime_input 必須是 exact PreparedMLRuntimeInputV1")
    from app_module.recommendation_calibration_consumer import (
        _InvocationProjectionCapability,
        _NoModelProjectionCapability,
    )

    capability = runtime_input.invocation_capability
    if type(capability) not in (
        _InvocationProjectionCapability,
        _NoModelProjectionCapability,
    ):
        raise TypeError("runtime input 未攜帶受支援的 exact invocation capability")
    projector = getattr(capability, "project_prepared_runtime_input_v1", None)
    if not callable(projector):
        raise TypeError("invocation capability 不支援 prepared runtime input")
    return projector(runtime_input)


def _aligned_candidates(
    facts: RecommendationMLPreparationFactsV1
    | RecommendationMLSparsePreparationFactsV1,
    context: PreparedMLProjectionContextV1,
) -> tuple[tuple[Any, ...], tuple[Any, ...]]:
    """核對 sparse 中 present facts 與完整 projection 順序。"""

    projection_candidates = context.candidates
    if type(facts) is RecommendationMLPreparationFactsV1:
        fact_candidates = facts.candidates
        if len(fact_candidates) != len(projection_candidates):
            raise ValueError("projection candidates 與 preparation facts 數量不一致")
        for fact, projected in zip(fact_candidates, projection_candidates):
            if type(projected) is not PreparedCandidateProjectionInputV1 or (
                projected.candidate_id,
                projected.symbol,
            ) != (fact.candidate_id, fact.symbol):
                raise ValueError(
                    "projection candidate identity/order 與 preparation facts 不一致"
                )
        return fact_candidates, projection_candidates

    if type(facts) is not RecommendationMLSparsePreparationFactsV1:
        raise TypeError("preparation_facts 型別不支援")
    fact_candidates = (
        () if facts.present_facts is None else facts.present_facts.candidates
    )
    if len(fact_candidates) + len(facts.missing_candidates) != len(
        projection_candidates
    ):
        raise ValueError("sparse projection context 未涵蓋所有 candidates")
    missing_by_index = {
        item.selection_index: item for item in facts.missing_candidates
    }
    present_position = 0
    for index, projected in enumerate(projection_candidates):
        missing = missing_by_index.get(index)
        if missing is not None:
            if (
                type(projected) is not MissingCandidateProjectionInputV1
                or projected.missing_feature != missing
            ):
                raise ValueError("missing candidate context 與 sparse facts 不一致")
            continue
        if type(projected) is not PreparedCandidateProjectionInputV1:
            raise ValueError("present candidate 缺少 typed projection input")
        if present_position >= len(fact_candidates):
            raise ValueError("sparse projection context 多出 present candidate")
        fact = fact_candidates[present_position]
        if (projected.candidate_id, projected.symbol) != (
            fact.candidate_id,
            fact.symbol,
        ):
            raise ValueError("present candidate identity/order 與 sparse facts 不一致")
        present_position += 1
    if present_position != len(fact_candidates):
        raise ValueError("sparse projection context 遺漏 present candidate")
    return fact_candidates, projection_candidates


def _projection_symbol(candidate: Any) -> str:
    if type(candidate) is MissingCandidateProjectionInputV1:
        return candidate.missing_feature.symbol
    if type(candidate) is PreparedCandidateProjectionInputV1:
        return candidate.symbol
    raise TypeError("projection candidate 型別不支援")


def _decode_provenance_object(
    value: PreparedInferenceProvenanceV1,
) -> dict[str, Any]:
    if type(value) is not PreparedInferenceProvenanceV1:
        raise TypeError("inference_provenance 必須是 exact typed provenance 或 None")
    return _decode_canonical_object(
        value.canonical_json_bytes,
        field_name="inference_provenance.canonical_json_bytes",
    )


def _decode_canonical_object(raw_bytes: bytes, *, field_name: str) -> dict[str, Any]:
    if type(raw_bytes) is not bytes:
        raise TypeError(f"{field_name} 必須是 bytes")
    try:
        payload = json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{field_name} 不是有效 UTF-8 JSON") from exc
    if type(payload) is not dict:
        raise ValueError(f"{field_name} 必須編碼 JSON object")
    canonical_bytes = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    if canonical_bytes != raw_bytes:
        raise ValueError(f"{field_name} 必須是 canonical JSON bytes")
    return payload
