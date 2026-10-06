"""R026 同次 ML 投影的不可變執行輸入契約。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from hashlib import sha256
import json
import re
from typing import Any, Final, Literal, SupportsIndex, TypeAlias, cast

from app_module.recommendation.ml_preparation_facts import (
    RecommendationMLPreparationFactsV1,
)
from app_module.recommendation.model_resolution_facts import (
    RecommendationModelResolutionEvidenceV1,
    UnknownModelBindingFieldsV1,
)
from ml_module.prepared_input_contract import (
    AvailabilityStatus,
    PreparedMLInput,
    SnapshotReference,
    _freeze_aware_datetime,
)
from ml_module.prepared_source_contract import (
    VerifiedSourceContractEvidenceV1,
)


_SHA256_RE: Final[re.Pattern[str]] = re.compile(r"sha256:[0-9a-f]{64}\Z")


def _require_text(value: object, field_name: str) -> str:
    if type(value) is not str:
        raise TypeError(f"{field_name} 必須是 str")
    return value


def _require_sha256(value: object, field_name: str) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise ValueError(f"{field_name} 必須是 sha256 格式")
    return value


def _freeze_text_tuple(value: object, field_name: str) -> tuple[str, ...]:
    if type(value) not in (tuple, list):
        raise TypeError(f"{field_name} 必須是 tuple 或 list")
    frozen = tuple(cast(tuple[object, ...] | list[object], value))
    if any(type(item) is not str for item in frozen):
        raise TypeError(f"{field_name} 項目必須是 str")
    return cast(tuple[str, ...], frozen)


def _freeze_schema(value: object) -> tuple[tuple[str, str, str], ...]:
    if type(value) not in (tuple, list):
        raise TypeError("feature_schema 必須是 tuple 或 list")
    frozen_items: list[tuple[str, str, str]] = []
    for item in cast(tuple[object, ...] | list[object], value):
        if type(item) not in (tuple, list):
            raise TypeError("feature_schema 每項必須是三欄 tuple")
        values = tuple(cast(tuple[object, ...] | list[object], item))
        if len(values) != 3:
            raise TypeError("feature_schema 每項必須是三欄 tuple")
        if any(type(part) is not str for part in values):
            raise TypeError("feature_schema 欄位必須是 str")
        frozen_items.append(cast(tuple[str, str, str], values))
    return tuple(frozen_items)


def _freeze_records(value: object, field_name: str, record_type: type[Any]) -> tuple[Any, ...]:
    if type(value) not in (tuple, list):
        raise TypeError(f"{field_name} 必須是 tuple 或 list")
    records = tuple(cast(tuple[object, ...] | list[object], value))
    if any(type(record) is not record_type for record in records):
        raise TypeError(f"{field_name} 含有不支援的 record")
    return records


def _canonical_json_object(payload: bytes, field_name: str) -> dict[str, Any]:
    if type(payload) is not bytes:
        raise TypeError(f"{field_name} 必須是不可變 bytes")
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{field_name} 不是 UTF-8 JSON") from exc
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} 必須是 JSON object")
    normalized = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    if normalized != payload:
        raise ValueError(f"{field_name} 必須使用 canonical JSON bytes")
    return dict(value)


@dataclass(frozen=True, slots=True)
class StrictPreparedMLIdentityV1:
    """保留原 strict `PreparedMLInput` V1 身分。"""

    prepared_input: PreparedMLInput

    def __post_init__(self) -> None:
        if type(self.prepared_input) is not PreparedMLInput:
            raise TypeError("prepared_input 必須是 PreparedMLInput")


@dataclass(frozen=True, slots=True)
class LoadedModelRuntimeClassV1:
    """記錄實際載入物件的 Python 類別，不代表 artifact 宣告類別。"""

    module: str
    qualified_name: str

    def __post_init__(self) -> None:
        _require_text(self.module, "module")
        _require_text(self.qualified_name, "qualified_name")


@dataclass(frozen=True, slots=True)
class BoundRuleSnapshotsV1:
    """同次呼叫已綁定的規則來源快照。"""

    snapshot_refs: tuple[SnapshotReference, ...]

    def __post_init__(self) -> None:
        refs = _freeze_records(self.snapshot_refs, "snapshot_refs", SnapshotReference)
        if not refs:
            raise ValueError("snapshot_refs 不可為空")
        object.__setattr__(self, "snapshot_refs", cast(tuple[SnapshotReference, ...], refs))


@dataclass(frozen=True, slots=True)
class LegacyUnboundRuleIdentityV1:
    """表達基線允許但無法綁定來源 identity 的舊規則輸入。"""

    reason: Literal["legacy_source_identity_unbound"]

    def __post_init__(self) -> None:
        if self.reason != "legacy_source_identity_unbound":
            raise ValueError("reason 必須是 legacy_source_identity_unbound")


RuleIdentityV1: TypeAlias = BoundRuleSnapshotsV1 | LegacyUnboundRuleIdentityV1


@dataclass(frozen=True, slots=True)
class LegacyShadowIdentityV1:
    """保留 legacy artifact 未提供的 binding 欄位為原始 UNKNOWN／None。"""

    model_resolution: RecommendationModelResolutionEvidenceV1
    unknown_model_binding_fields: UnknownModelBindingFieldsV1
    loaded_model_runtime_class: LoadedModelRuntimeClassV1
    ml_snapshot_refs: tuple[SnapshotReference, ...]
    rule_identity: RuleIdentityV1

    def __post_init__(self) -> None:
        if type(self.model_resolution) is not RecommendationModelResolutionEvidenceV1:
            raise TypeError("model_resolution 型別不支援")
        if type(self.unknown_model_binding_fields) is not UnknownModelBindingFieldsV1:
            raise TypeError("unknown_model_binding_fields 型別不支援")
        if self.model_resolution.missing_model_binding != self.unknown_model_binding_fields:
            raise ValueError("unknown binding 欄位必須來自同次 model-resolution facts")
        if type(self.loaded_model_runtime_class) is not LoadedModelRuntimeClassV1:
            raise TypeError("loaded_model_runtime_class 型別不支援")
        refs = _freeze_records(self.ml_snapshot_refs, "ml_snapshot_refs", SnapshotReference)
        if not refs:
            raise ValueError("ml_snapshot_refs 不可為空")
        if type(self.rule_identity) not in (BoundRuleSnapshotsV1, LegacyUnboundRuleIdentityV1):
            raise TypeError("rule_identity 型別不支援")
        object.__setattr__(self, "ml_snapshot_refs", cast(tuple[SnapshotReference, ...], refs))


@dataclass(frozen=True, slots=True)
class NoModelShadowIdentityV1:
    """封存 fresh baseline reload 的真實 rule-only/no-model 終止結果。"""

    decision_date: str
    reload_status: Literal["rule_only"]
    blocker: str
    pointer_status: str | None
    pointer_raw_bytes: bytes | None = field(repr=False)
    pointer_raw_bytes_sha256: str | None = field(init=False)

    def __post_init__(self) -> None:
        _require_text(self.decision_date, "decision_date")
        try:
            date.fromisoformat(self.decision_date)
        except ValueError as exc:
            raise ValueError("decision_date 必須是 ISO 日期") from exc
        if self.reload_status != "rule_only":
            raise ValueError("reload_status 必須是 rule_only")
        _require_text(self.blocker, "blocker")
        if self.pointer_status is not None and type(self.pointer_status) is not str:
            raise TypeError("pointer_status 必須保留原始字串值或 None")
        if self.pointer_raw_bytes is not None and type(self.pointer_raw_bytes) is not bytes:
            raise TypeError("pointer_raw_bytes 必須是 bytes 或 None")
        if self.pointer_raw_bytes is None:
            if self.pointer_status is not None or self.blocker != "active_pointer_missing":
                raise ValueError("缺少 pointer bytes 時只能保留 missing baseline 結果")
            pointer_hash = None
        else:
            pointer_hash = "sha256:" + sha256(self.pointer_raw_bytes).hexdigest()
        object.__setattr__(self, "pointer_raw_bytes_sha256", pointer_hash)


@dataclass(frozen=True, slots=True)
class MissingCandidateFeatureV1:
    """被選取但同次 canonical builder 缺少 price row 的真實 item 身分。"""

    symbol: str
    selection_index: int
    selected_item_sha256: str
    reason: Literal["historical_price_row_missing"]

    def __post_init__(self) -> None:
        _require_text(self.symbol, "symbol")
        if type(self.selection_index) is not int or self.selection_index < 0:
            raise ValueError("selection_index 必須是非負 int")
        _require_sha256(self.selected_item_sha256, "selected_item_sha256")
        if self.reason != "historical_price_row_missing":
            raise ValueError("reason 必須是 historical_price_row_missing")


@dataclass(frozen=True, slots=True)
class RecommendationMLSparsePreparationFactsV1:
    """保留有 feature row 與缺 row 的原候選順序，不補造向量或 row hash。"""

    result_id: str
    decision_date: date
    feature_cutoff_date: date
    feature_registry_id: str
    feature_registry_hash: str
    feature_schema: tuple[tuple[str, str, str], ...]
    feature_ids: tuple[str, ...]
    feature_schema_hash: str
    feature_load_contract_hash: str
    present_facts: RecommendationMLPreparationFactsV1 | None
    missing_candidates: tuple[MissingCandidateFeatureV1, ...]

    def __post_init__(self) -> None:
        _require_text(self.result_id, "result_id")
        if type(self.decision_date) is not date:
            raise TypeError("decision_date 必須是 date")
        if type(self.feature_cutoff_date) is not date:
            raise TypeError("feature_cutoff_date 必須是 date")
        if self.feature_cutoff_date >= self.decision_date:
            raise ValueError("feature_cutoff_date 必須早於 decision_date")
        _require_text(self.feature_registry_id, "feature_registry_id")
        _require_sha256(self.feature_registry_hash, "feature_registry_hash")
        schema = _freeze_schema(self.feature_schema)
        feature_ids = _freeze_text_tuple(self.feature_ids, "feature_ids")
        if not schema or tuple(item[0] for item in schema) != feature_ids:
            raise ValueError("feature_ids 順序必須與 feature_schema 一致")
        if len(set(feature_ids)) != len(feature_ids):
            raise ValueError("feature_ids 不可重複")
        _require_sha256(self.feature_schema_hash, "feature_schema_hash")
        _require_sha256(self.feature_load_contract_hash, "feature_load_contract_hash")
        if self.present_facts is not None:
            if type(self.present_facts) is not RecommendationMLPreparationFactsV1:
                raise TypeError("present_facts 型別不支援")
            present = self.present_facts
            shared_values = (
                (present.result_id, self.result_id),
                (present.decision_date, self.decision_date),
                (present.feature_cutoff_date, self.feature_cutoff_date),
                (present.feature_registry_id, self.feature_registry_id),
                (present.feature_registry_hash, self.feature_registry_hash),
                (present.feature_schema, schema),
                (present.feature_ids, feature_ids),
                (present.feature_schema_hash, self.feature_schema_hash),
                (present.feature_load_contract_hash, self.feature_load_contract_hash),
            )
            if any(left != right for left, right in shared_values):
                raise ValueError("present_facts 的共用 schema/date/hash 不一致")
        missing = _freeze_records(
            self.missing_candidates,
            "missing_candidates",
            MissingCandidateFeatureV1,
        )
        if not missing:
            raise ValueError("missing_candidates 不可為空")
        missing_candidates = cast(tuple[MissingCandidateFeatureV1, ...], missing)
        if tuple(item.selection_index for item in missing_candidates) != tuple(
            sorted(item.selection_index for item in missing_candidates)
        ):
            raise ValueError("missing_candidates 必須保留選取順序")
        present_candidates = () if self.present_facts is None else self.present_facts.candidates
        total_count = len(present_candidates) + len(missing_candidates)
        expected_indexes = tuple(item.selection_index for item in missing_candidates)
        if len(set(expected_indexes)) != len(expected_indexes) or any(
            index >= total_count for index in expected_indexes
        ):
            raise ValueError("missing candidate selection_index 不符合完整候選範圍")
        all_symbols = tuple(item.symbol for item in missing_candidates) + tuple(
            item.symbol for item in present_candidates
        )
        if len(set(all_symbols)) != len(all_symbols):
            raise ValueError("sparse preparation candidate symbols 不可重複")
        object.__setattr__(self, "feature_schema", schema)
        object.__setattr__(self, "feature_ids", feature_ids)
        object.__setattr__(self, "missing_candidates", missing_candidates)


PreparationFactsV1: TypeAlias = (
    RecommendationMLPreparationFactsV1 | RecommendationMLSparsePreparationFactsV1
)


@dataclass(frozen=True, slots=True)
class PreparedCandidateProjectionInputV1:
    """有 feature row 候選的同次 rule／after-cost／ranking baseline 值。"""

    candidate_id: str
    symbol: str
    rule_probability_bp: int | None
    after_cost_rule_probability_bp: int | None
    after_cost_rule_baseline_id: str | None
    ranking_percentile_bp: int | None

    def __post_init__(self) -> None:
        _require_text(self.candidate_id, "candidate_id")
        _require_text(self.symbol, "symbol")
        for name in (
            "rule_probability_bp",
            "after_cost_rule_probability_bp",
            "ranking_percentile_bp",
        ):
            value = getattr(self, name)
            if value is not None and type(value) is not int:
                raise TypeError(f"{name} 必須是 int 或 None")
        if (
            self.after_cost_rule_baseline_id is not None
            and type(self.after_cost_rule_baseline_id) is not str
        ):
            raise TypeError("after_cost_rule_baseline_id 必須是 str 或 None")


@dataclass(frozen=True, slots=True)
class MissingCandidateProjectionInputV1:
    """缺少 feature row 的候選保留同次 rule／ranking inputs。"""

    missing_feature: MissingCandidateFeatureV1
    rule_probability_bp: int | None
    after_cost_rule_probability_bp: int | None
    after_cost_rule_baseline_id: str | None
    ranking_percentile_bp: int | None

    def __post_init__(self) -> None:
        if type(self.missing_feature) is not MissingCandidateFeatureV1:
            raise TypeError("missing_feature 型別不支援")
        for name in (
            "rule_probability_bp",
            "after_cost_rule_probability_bp",
            "ranking_percentile_bp",
        ):
            value = getattr(self, name)
            if value is not None and type(value) is not int:
                raise TypeError(f"{name} 必須是 int 或 None")
        if (
            self.after_cost_rule_baseline_id is not None
            and type(self.after_cost_rule_baseline_id) is not str
        ):
            raise TypeError("after_cost_rule_baseline_id 必須是 str 或 None")


ProjectionCandidateInputV1: TypeAlias = (
    PreparedCandidateProjectionInputV1 | MissingCandidateProjectionInputV1
)


@dataclass(frozen=True, slots=True)
class PreparedMLProjectionContextV1:
    """`project_many()` 不能由 preparation facts 還原的既有輸入。"""

    candidates: tuple[ProjectionCandidateInputV1, ...]
    rule_baseline_id: str
    data_quality: str
    selection_authority: str
    selection_score_kind: str
    selection_percentile_kind: str
    top_n_changed_by_model: bool

    def __post_init__(self) -> None:
        if type(self.candidates) not in (tuple, list):
            raise TypeError("candidates 必須是 tuple 或 list")
        candidates = tuple(cast(tuple[object, ...] | list[object], self.candidates))
        if any(
            type(item)
            not in (PreparedCandidateProjectionInputV1, MissingCandidateProjectionInputV1)
            for item in candidates
        ):
            raise TypeError("candidates 含有不支援的 projection input")
        for name in (
            "rule_baseline_id",
            "data_quality",
            "selection_authority",
            "selection_score_kind",
            "selection_percentile_kind",
        ):
            _require_text(getattr(self, name), name)
        if type(self.top_n_changed_by_model) is not bool:
            raise TypeError("top_n_changed_by_model 必須是 bool")
        object.__setattr__(self, "candidates", cast(tuple[ProjectionCandidateInputV1, ...], candidates))


@dataclass(frozen=True, slots=True)
class PreparedInferenceProvenanceV1:
    """既有 inference provenance 的 canonical JSON bytes。"""

    canonical_json_bytes: bytes

    def __post_init__(self) -> None:
        _canonical_json_object(self.canonical_json_bytes, "canonical_json_bytes")


@dataclass(frozen=True, slots=True)
class PreparedMLInvocationBindingV1:
    """同次 capability scope 與 active identity 的 canonical bytes。"""

    invocation_scope_id: str
    expected_identity_canonical_json_bytes: bytes

    def __post_init__(self) -> None:
        _require_text(self.invocation_scope_id, "invocation_scope_id")
        _canonical_json_object(
            self.expected_identity_canonical_json_bytes,
            "expected_identity_canonical_json_bytes",
        )


def _validate_projection_alignment(
    facts: PreparationFactsV1,
    context: PreparedMLProjectionContextV1,
) -> None:
    if type(facts) is RecommendationMLPreparationFactsV1:
        expected = tuple((item.candidate_id, item.symbol) for item in facts.candidates)
        supplied: list[tuple[str, str]] = []
        for candidate in context.candidates:
            if type(candidate) is not PreparedCandidateProjectionInputV1:
                raise ValueError("完整 preparation facts 不接受 missing projection input")
            supplied.append((candidate.candidate_id, candidate.symbol))
        if tuple(supplied) != expected:
            raise ValueError("projection candidates 順序/identity 與 preparation facts 不一致")
        return

    if type(facts) is not RecommendationMLSparsePreparationFactsV1:
        raise TypeError("preparation_facts 型別不支援")
    total_count = (0 if facts.present_facts is None else len(facts.present_facts.candidates)) + len(
        facts.missing_candidates
    )
    if len(context.candidates) != total_count:
        raise ValueError("projection context 未涵蓋完整 sparse candidate 順序")
    present_facts = () if facts.present_facts is None else facts.present_facts.candidates
    missing_by_index = {item.selection_index: item for item in facts.missing_candidates}
    present_position = 0
    for index, projection in enumerate(context.candidates):
        missing = missing_by_index.get(index)
        if missing is not None:
            if type(projection) is not MissingCandidateProjectionInputV1:
                raise ValueError("缺少 feature row 的位置必須使用 missing projection input")
            if projection.missing_feature != missing:
                raise ValueError("missing projection identity 與 sparse facts 不一致")
            continue
        if type(projection) is not PreparedCandidateProjectionInputV1:
            raise ValueError("有 feature row 的位置必須使用 prepared projection input")
        if present_position >= len(present_facts):
            raise ValueError("projection context 多出 present candidate")
        prepared = present_facts[present_position]
        if (projection.candidate_id, projection.symbol) != (
            prepared.candidate_id,
            prepared.symbol,
        ):
            raise ValueError("present projection identity/order 與 facts 不一致")
        present_position += 1
    if present_position != len(present_facts):
        raise ValueError("projection context 遺漏 present candidate")


def _validate_identity_alignment(
    identity: StrictPreparedMLIdentityV1 | LegacyShadowIdentityV1 | NoModelShadowIdentityV1,
    facts: PreparationFactsV1,
    context: PreparedMLProjectionContextV1,
    decision_clock: datetime,
) -> None:
    decision_day = facts.decision_date.isoformat()
    if type(identity) is NoModelShadowIdentityV1:
        if identity.decision_date != decision_day:
            raise ValueError("no-model reload date 與 preparation facts 不一致")
        return
    if type(identity) is StrictPreparedMLIdentityV1:
        prepared = identity.prepared_input
        if prepared.result_id != facts.result_id:
            raise ValueError("strict identity result_id 與 preparation facts 不一致")
        if prepared.decision_date != facts.decision_date:
            raise ValueError("strict identity decision_date 與 preparation facts 不一致")
        if prepared.feature_cutoff_date != facts.feature_cutoff_date:
            raise ValueError("strict identity feature cutoff 與 preparation facts 不一致")
        if prepared.decision_at != decision_clock:
            raise ValueError("strict identity decision_at 與原始 decision_clock 不一致")
        if prepared.feature_contract.feature_registry_hash != facts.feature_registry_hash:
            raise ValueError("strict identity feature registry 與 preparation facts 不一致")
        schema = tuple(
            (item.feature_id, item.dtype, item.unit)
            for item in prepared.feature_contract.feature_schema
        )
        if schema != facts.feature_schema:
            raise ValueError("strict identity feature schema 與 preparation facts 不一致")
        if type(facts) is RecommendationMLPreparationFactsV1:
            expected = tuple(
                (item.candidate_id, item.symbol) for item in facts.candidates
            )
            actual = tuple(
                (item.candidate_id, item.symbol)
                for item in prepared.candidate_identities
            )
            if actual != expected:
                raise ValueError("strict identity candidate ID／symbol 順序不一致")
        else:
            raise ValueError(
                "strict identity 不支援 sparse facts：缺列候選沒有可驗證的 strict candidate ID 綁定"
            )
        return

    if type(identity) is not LegacyShadowIdentityV1:
        raise TypeError("identity 型別不支援")
    if identity.model_resolution.decision_date != decision_day:
        raise ValueError("legacy model-resolution decision date 與 preparation facts 不一致")
    references = identity.ml_snapshot_refs
    if type(identity.rule_identity) is BoundRuleSnapshotsV1:
        references = references + identity.rule_identity.snapshot_refs
    for reference in references:
        if (
            reference.row_range is not None
            and reference.row_range.end_date > facts.feature_cutoff_date
        ):
            raise ValueError("legacy snapshot 含超過共同 feature cutoff 的資料列")
        availability = reference.availability
        if (
            availability.status is AvailabilityStatus.KNOWN
            and availability.available_at is not None
            and availability.available_at > decision_clock
        ):
            raise ValueError("legacy snapshot 晚於原始 decision_clock 才可得")
        if (
            availability.status is AvailabilityStatus.KNOWN
            and availability.available_date is not None
            and availability.available_date > facts.decision_date
        ):
            raise ValueError("legacy snapshot 晚於 preparation decision_date 才可得")


@dataclass(frozen=True, slots=True)
class PreparedMLRuntimeInputV1:
    """單次投影所需的 typed facts 與不可重用 invocation capability。"""

    identity: StrictPreparedMLIdentityV1 | LegacyShadowIdentityV1 | NoModelShadowIdentityV1
    preparation_facts: PreparationFactsV1
    projection_context: PreparedMLProjectionContextV1
    invocation_binding: PreparedMLInvocationBindingV1
    inference_provenance: PreparedInferenceProvenanceV1 | None
    decision_clock: datetime
    invocation_capability: object = field(repr=False, compare=False)
    source_contract_evidence: VerifiedSourceContractEvidenceV1 | None = None

    def __post_init__(self) -> None:
        if type(self.identity) not in (
            StrictPreparedMLIdentityV1,
            LegacyShadowIdentityV1,
            NoModelShadowIdentityV1,
        ):
            raise TypeError("identity 型別不支援")
        if type(self.preparation_facts) not in (
            RecommendationMLPreparationFactsV1,
            RecommendationMLSparsePreparationFactsV1,
        ):
            raise TypeError("preparation_facts 型別不支援")
        if type(self.projection_context) is not PreparedMLProjectionContextV1:
            raise TypeError("projection_context 型別不支援")
        if type(self.invocation_binding) is not PreparedMLInvocationBindingV1:
            raise TypeError("invocation_binding 型別不支援")
        if self.inference_provenance is not None and type(self.inference_provenance) is not PreparedInferenceProvenanceV1:
            raise TypeError("inference_provenance 型別不支援")
        decision_clock = _freeze_aware_datetime(self.decision_clock, "decision_clock")
        object.__setattr__(self, "decision_clock", decision_clock)
        if self.invocation_capability is None:
            raise ValueError("invocation_capability 不可為 None")
        if self.source_contract_evidence is not None and type(
            self.source_contract_evidence
        ) is not VerifiedSourceContractEvidenceV1:
            raise TypeError("source_contract_evidence 型別不支援")
        if type(self.identity) is NoModelShadowIdentityV1 and _canonical_json_object(
            self.invocation_binding.expected_identity_canonical_json_bytes,
            "expected_identity_canonical_json_bytes",
        ):
            raise ValueError("no-model identity 的 expected identity 必須是空 object")

        _validate_projection_alignment(self.preparation_facts, self.projection_context)
        _validate_identity_alignment(
            self.identity,
            self.preparation_facts,
            self.projection_context,
            decision_clock,
        )

        provenance_binding: object | None = None
        if self.inference_provenance is not None:
            provenance = _canonical_json_object(
                self.inference_provenance.canonical_json_bytes,
                "inference_provenance.canonical_json_bytes",
            )
            provenance_binding = provenance.get("source_contract_binding")
        if (provenance_binding is None) != (self.source_contract_evidence is None):
            raise ValueError("source-contract binding 與 typed evidence 必須同次成對存在")
        if self.source_contract_evidence is not None:
            if type(provenance_binding) is not dict:
                raise ValueError("inference provenance source-contract binding 必須是 object")
            binding_bytes = json.dumps(
                provenance_binding,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            if binding_bytes != self.source_contract_evidence.binding_payload_json:
                raise ValueError("inference provenance 與 typed source-contract evidence 不一致")

    def __copy__(self) -> PreparedMLRuntimeInputV1:
        raise TypeError("invocation runtime input 不可複製")

    def __deepcopy__(self, memo: dict[int, Any]) -> PreparedMLRuntimeInputV1:
        del memo
        raise TypeError("invocation runtime input 不可深複製")

    def __reduce_ex__(self, protocol: SupportsIndex) -> str | tuple[Any, ...]:
        del protocol
        raise TypeError("invocation runtime input 不可序列化")


__all__ = [
    "BoundRuleSnapshotsV1",
    "LegacyShadowIdentityV1",
    "LegacyUnboundRuleIdentityV1",
    "LoadedModelRuntimeClassV1",
    "MissingCandidateFeatureV1",
    "MissingCandidateProjectionInputV1",
    "NoModelShadowIdentityV1",
    "PreparedCandidateProjectionInputV1",
    "PreparedInferenceProvenanceV1",
    "PreparedMLInvocationBindingV1",
    "PreparedMLProjectionContextV1",
    "PreparedMLRuntimeInputV1",
    "RecommendationMLSparsePreparationFactsV1",
    "StrictPreparedMLIdentityV1",
]
