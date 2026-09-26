"""Invocation-local, immutable candidate/feature preparation facts for R026.

This module intentionally stops before ``PreparedMLInput``: source snapshot
references, model binding and same-day availability are not inferred here.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import date
from decimal import Decimal
import hashlib
import json
import re
from collections.abc import Sequence
from typing import ClassVar, TypeAlias, TypeVar, cast

from data_module.contracts.market import SourceRef
from decision_module.recommendation.contracts import (
    FactorContribution,
    RecommendationItem,
    UniverseReference,
)
from ml_module.feature_registry import FeatureRegistry
from ml_module.historical_contracts import HistoricalFeatureRow
from ml_module.historical_feature_builder import (
    HistoricalFeatureBuilder,
    HistoricalFeatureBuilderLoadContract,
    HistoricalFeatureVector,
)


ML_PREPARATION_FACTS_V1 = "recommendation-ml-preparation-facts.v1"
_CANDIDATE_ID_PREFIX = "candidate.v1:"
_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_DIGEST_RE = re.compile(r"[0-9a-f]{64}\Z")
FeatureSchema: TypeAlias = tuple[tuple[str, str, str], ...]
_RecordT = TypeVar("_RecordT")

_EXPECTED_RECORD_FIELDS: dict[type[object], tuple[str, ...]] = {
    RecommendationItem: (
        "stock_code",
        "rule_score",
        "close_price",
        "price_change",
        "indicator_score",
        "pattern_score",
        "volume_score",
        "industry",
        "reason_text",
        "factor_contributions",
        "rank",
        "universe_ref",
        "reasons",
        "confidence",
        "stock_name",
        "score_percentile_bp",
        "eligible_universe_size",
        "eligible_universe_date",
        "ranking_method",
        "threshold_mode",
        "regime_match",
    ),
    FactorContribution: (
        "factor_id",
        "value",
        "unit",
        "version",
        "source_refs",
    ),
    UniverseReference: ("policy_id", "snapshot_id", "as_of_date", "members_hash"),
    SourceRef: ("source_id", "revision", "snapshot_id"),
}


@dataclass(frozen=True, slots=True)
class CandidateFeatureFactV1:
    """一個有序 selected item 與 feature row 的 invocation-bound opaque ID。

    ID 將 item、feature row、result 與 selection index 綁定；它不是跨 feature
    版本穩定的 candidate identity，也不取代獨立的 feature-row digest。
    """

    candidate_id: str
    symbol: str
    selection_index: int
    selected_item_sha256: str
    feature_values: tuple[int | None, ...]
    feature_row_sha256: str
    feature_as_of_date: date
    available_date: date

    def __post_init__(self) -> None:
        if type(self.candidate_id) is not str or not self.candidate_id.startswith(
            _CANDIDATE_ID_PREFIX
        ):
            raise ValueError("candidate_id 必須是本版本產生的不透明 ID")
        digest = self.candidate_id[len(_CANDIDATE_ID_PREFIX) :]
        if _DIGEST_RE.fullmatch(digest) is None:
            raise ValueError("candidate_id digest 格式錯誤")
        _require_text(self.symbol, "symbol")
        if type(self.selection_index) is not int or self.selection_index < 0:
            raise ValueError("selection_index 必須是非負 int")
        _require_sha256(self.selected_item_sha256, "selected_item_sha256")
        values = _freeze_feature_values(self.feature_values)
        if not values:
            raise ValueError("feature_values 不可為空")
        _require_sha256(self.feature_row_sha256, "feature_row_sha256")
        if type(self.feature_as_of_date) is not date:
            raise TypeError("feature_as_of_date 必須是 date")
        if type(self.available_date) is not date:
            raise TypeError("available_date 必須是 date")
        object.__setattr__(self, "feature_values", values)


@dataclass(frozen=True, slots=True)
class RecommendationMLPreparationFactsV1:
    """只含 selected candidate 與有序 features 的深不可變 v1 payload。"""

    result_id: str
    decision_date: date
    feature_cutoff_date: date
    feature_registry_id: str
    feature_registry_hash: str
    feature_schema: FeatureSchema
    feature_ids: tuple[str, ...]
    feature_schema_hash: str
    feature_load_contract_hash: str
    candidates: tuple[CandidateFeatureFactV1, ...]
    payload_sha256: str

    contract_version: ClassVar[str] = ML_PREPARATION_FACTS_V1

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
        schema = _freeze_feature_schema(self.feature_schema)
        ids = _freeze_text_tuple(self.feature_ids, "feature_ids")
        if not schema or tuple(item[0] for item in schema) != ids:
            raise ValueError("feature_ids 順序必須與 feature_schema 完全相同")
        if len(set(ids)) != len(ids):
            raise ValueError("feature_ids 不可重複")
        _require_sha256(self.feature_schema_hash, "feature_schema_hash")
        _require_sha256(
            self.feature_load_contract_hash, "feature_load_contract_hash"
        )
        candidates = _freeze_candidate_tuple(self.candidates)
        if not candidates:
            raise ValueError("candidates 不可為空")
        symbols = tuple(candidate.symbol for candidate in candidates)
        candidate_ids = tuple(candidate.candidate_id for candidate in candidates)
        if len(set(symbols)) != len(symbols):
            raise ValueError("candidate symbols 不可重複")
        if len(set(candidate_ids)) != len(candidate_ids):
            raise ValueError("candidate IDs 不可重複")
        for index, candidate in enumerate(candidates):
            if candidate.selection_index != index:
                raise ValueError("candidate selection order/index 不一致")
            if len(candidate.feature_values) != len(ids):
                raise ValueError("candidate feature width 與 feature schema 不一致")
            if candidate.feature_as_of_date != self.feature_cutoff_date:
                raise ValueError("candidate feature cutoff 不一致")
            if candidate.available_date > self.decision_date:
                raise ValueError("candidate feature availability 晚於 decision_date")
            expected_id = _candidate_id(
                result_id=self.result_id,
                decision_date=self.decision_date,
                feature_cutoff_date=self.feature_cutoff_date,
                selection_index=index,
                symbol=candidate.symbol,
                selected_item_sha256=candidate.selected_item_sha256,
                feature_registry_hash=self.feature_registry_hash,
                feature_schema_hash=self.feature_schema_hash,
                feature_row_sha256=candidate.feature_row_sha256,
            )
            if candidate.candidate_id != expected_id:
                raise ValueError("candidate_id 與本筆 selected/feature facts 不一致")
        _require_sha256(self.payload_sha256, "payload_sha256")

        object.__setattr__(self, "feature_schema", schema)
        object.__setattr__(self, "feature_ids", ids)
        object.__setattr__(self, "candidates", candidates)
        expected_payload_hash = _sha256_payload(_facts_payload(self))
        if self.payload_sha256 != expected_payload_hash:
            raise ValueError("payload_sha256 與 preparation facts 不一致")


def build_recommendation_ml_preparation_facts_v1(
    *,
    result_id: str,
    decision_date: date,
    feature_cutoff_date: date,
    selected_items: Sequence[RecommendationItem],
    feature_rows: Sequence[HistoricalFeatureRow],
    feature_builder: HistoricalFeatureBuilder,
) -> RecommendationMLPreparationFactsV1:
    """由同次 typed selection 與 builder canonical load 結果建 facts。

    本函式只整理已在記憶體中的選取列與 feature rows；不查詢 source、模型、
    pointer、receipt，也不推導 PreparedMLInput 的 snapshot/model references。
    """

    _require_text(result_id, "result_id")
    if type(decision_date) is not date:
        raise TypeError("decision_date 必須是 date")
    if type(feature_cutoff_date) is not date:
        raise TypeError("feature_cutoff_date 必須是 date")
    if feature_cutoff_date >= decision_date:
        raise ValueError("feature_cutoff_date 必須早於 decision_date")
    if type(feature_builder) is not HistoricalFeatureBuilder:
        raise TypeError("feature_builder 必須是 canonical HistoricalFeatureBuilder")

    registry = getattr(feature_builder, "_registry", None)
    load_contract = getattr(feature_builder, "load_contract", None)
    if type(registry) is not FeatureRegistry:
        raise TypeError("feature_builder registry 型別不支援")
    if type(load_contract) is not HistoricalFeatureBuilderLoadContract:
        raise TypeError("feature_builder load contract 型別不支援")
    expected_contract = HistoricalFeatureBuilderLoadContract.from_registry(registry)
    if load_contract != expected_contract:
        raise ValueError("feature_builder load contract 與 registry 不一致")

    items = _snapshot_sequence(selected_items, RecommendationItem, "selected_items")
    rows = _snapshot_sequence(feature_rows, HistoricalFeatureRow, "feature_rows")
    if not items:
        raise ValueError("selected_items 不可為空")
    if len(items) != len(rows):
        raise ValueError("selected_items 與 feature_rows 必須有相同數量")
    symbols = tuple(item.stock_code for item in items)
    if len(set(symbols)) != len(symbols):
        raise ValueError("selected_items stock_code 不可重複")

    # 使用官方 load 實作本體，避免 instance/subclass override 建立第二排序規則。
    vectors = tuple(HistoricalFeatureBuilder.load(feature_builder, row) for row in rows)
    candidate_facts: list[CandidateFeatureFactV1] = []
    for index, (item, row, vector) in enumerate(zip(items, rows, vectors)):
        if row.symbol != item.stock_code or vector.symbol != item.stock_code:
            raise ValueError("selected item 與 feature row candidate order/symbol 不一致")
        if type(vector) is not HistoricalFeatureVector:
            raise TypeError("feature builder load 必須回傳 HistoricalFeatureVector")
        if vector.decision_date != decision_date.isoformat():
            raise ValueError("feature row decision_date 不一致")
        if vector.feature_as_of_date != feature_cutoff_date.isoformat():
            raise ValueError("feature row cutoff 不一致")
        if vector.available_date != date.fromisoformat(vector.available_date).isoformat():
            raise ValueError("feature available_date 必須是 canonical ISO date")
        available_date = date.fromisoformat(vector.available_date)
        if available_date > decision_date:
            raise ValueError("feature available_date 晚於 decision_date")
        if vector.registry_hash != load_contract.registry_hash:
            raise ValueError("feature row registry hash 不一致")
        if vector.schema_hash != load_contract.schema_hash:
            raise ValueError("feature row schema hash 不一致")
        if vector.feature_ids != load_contract.canonical_ids:
            raise ValueError("feature row IDs/order 不符合 canonical schema")
        if vector.feature_dtypes != load_contract.canonical_dtypes:
            raise ValueError("feature row dtype/order 不符合 canonical schema")
        if vector.feature_units != load_contract.canonical_units:
            raise ValueError("feature row unit/order 不符合 canonical schema")
        if len(vector.values) != len(load_contract.canonical_ids):
            raise ValueError("feature row width 不符合 canonical schema")
        values = _freeze_feature_values(vector.values)
        _require_sha256(vector.snapshot_hash, "feature row snapshot_hash")
        item_hash = _selected_item_hash(item)
        candidate_facts.append(
            CandidateFeatureFactV1(
                candidate_id=_candidate_id(
                    result_id=result_id,
                    decision_date=decision_date,
                    feature_cutoff_date=feature_cutoff_date,
                    selection_index=index,
                    symbol=item.stock_code,
                    selected_item_sha256=item_hash,
                    feature_registry_hash=load_contract.registry_hash,
                    feature_schema_hash=load_contract.schema_hash,
                    feature_row_sha256=vector.snapshot_hash,
                ),
                symbol=item.stock_code,
                selection_index=index,
                selected_item_sha256=item_hash,
                feature_values=values,
                feature_row_sha256=vector.snapshot_hash,
                feature_as_of_date=date.fromisoformat(vector.feature_as_of_date),
                available_date=available_date,
            )
        )

    schema: FeatureSchema = load_contract.canonical_schema
    ids = load_contract.canonical_ids
    payload_without_hash = {
        "contract_version": ML_PREPARATION_FACTS_V1,
        "result_id": result_id,
        "decision_date": decision_date.isoformat(),
        "feature_cutoff_date": feature_cutoff_date.isoformat(),
        "feature_registry_id": registry.registry_id,
        "feature_registry_hash": load_contract.registry_hash,
        "feature_schema": [list(item) for item in schema],
        "feature_ids": list(ids),
        "feature_schema_hash": load_contract.schema_hash,
        "feature_load_contract_hash": load_contract.contract_hash,
        "candidates": [_candidate_payload(item) for item in candidate_facts],
    }
    return RecommendationMLPreparationFactsV1(
        result_id=result_id,
        decision_date=decision_date,
        feature_cutoff_date=feature_cutoff_date,
        feature_registry_id=registry.registry_id,
        feature_registry_hash=load_contract.registry_hash,
        feature_schema=schema,
        feature_ids=ids,
        feature_schema_hash=load_contract.schema_hash,
        feature_load_contract_hash=load_contract.contract_hash,
        candidates=tuple(candidate_facts),
        payload_sha256=_sha256_payload(payload_without_hash),
    )


def _candidate_id(
    *,
    result_id: str,
    decision_date: date,
    feature_cutoff_date: date,
    selection_index: int,
    symbol: str,
    selected_item_sha256: str,
    feature_registry_hash: str,
    feature_schema_hash: str,
    feature_row_sha256: str,
) -> str:
    payload = {
        "domain": "r026.recommendation-candidate.v1",
        "result_id": result_id,
        "decision_date": decision_date.isoformat(),
        "feature_cutoff_date": feature_cutoff_date.isoformat(),
        "selection_index": selection_index,
        "symbol": symbol,
        "selected_item_sha256": selected_item_sha256,
        "feature_registry_hash": feature_registry_hash,
        "feature_schema_hash": feature_schema_hash,
        "feature_row_sha256": feature_row_sha256,
    }
    return _CANDIDATE_ID_PREFIX + _sha256_payload(payload).removeprefix("sha256:")


def _selected_item_hash(item: RecommendationItem) -> str:
    payload = {
        "domain": "r026.selected-recommendation-item.v1",
        "item": _encode_record(item),
    }
    return _sha256_payload(payload)


def _encode_record(value: object) -> dict[str, object]:
    expected = _EXPECTED_RECORD_FIELDS.get(type(value))
    if expected is None:
        raise TypeError(f"unsupported selected item record: {type(value).__name__}")
    record_value = cast(
        RecommendationItem | FactorContribution | UniverseReference | SourceRef,
        value,
    )
    actual = tuple(item.name for item in fields(record_value))
    if actual != expected:
        raise ValueError(
            f"selected item v1 record fields changed: {type(value).__name__}"
        )
    return {
        "record_type": f"{type(value).__module__}.{type(value).__qualname__}",
        "fields": [
            [name, _encode_value(getattr(value, name))]
            for name in expected
        ],
    }


def _encode_value(value: object) -> object:
    if value is None:
        return ["none"]
    if type(value) is bool:
        return ["bool", value]
    if type(value) is int:
        return ["int", value]
    if type(value) is str:
        return ["str", value]
    if type(value) is date:
        return ["date", value.isoformat()]
    if type(value) is Decimal:
        if not value.is_finite():
            raise ValueError("selected item Decimal must be finite")
        decimal_tuple = value.as_tuple()
        return [
            "decimal",
            decimal_tuple.sign,
            list(decimal_tuple.digits),
            decimal_tuple.exponent,
        ]
    if type(value) is tuple:
        return ["tuple", [_encode_value(item) for item in value]]
    if type(value) in _EXPECTED_RECORD_FIELDS:
        return ["record", _encode_record(value)]
    raise TypeError(f"selected item value type is unsupported: {type(value).__name__}")


def _facts_payload(facts: RecommendationMLPreparationFactsV1) -> dict[str, object]:
    return {
        "contract_version": facts.contract_version,
        "result_id": facts.result_id,
        "decision_date": facts.decision_date.isoformat(),
        "feature_cutoff_date": facts.feature_cutoff_date.isoformat(),
        "feature_registry_id": facts.feature_registry_id,
        "feature_registry_hash": facts.feature_registry_hash,
        "feature_schema": [list(item) for item in facts.feature_schema],
        "feature_ids": list(facts.feature_ids),
        "feature_schema_hash": facts.feature_schema_hash,
        "feature_load_contract_hash": facts.feature_load_contract_hash,
        "candidates": [_candidate_payload(item) for item in facts.candidates],
    }


def _candidate_payload(candidate: CandidateFeatureFactV1) -> dict[str, object]:
    return {
        "candidate_id": candidate.candidate_id,
        "symbol": candidate.symbol,
        "selection_index": candidate.selection_index,
        "selected_item_sha256": candidate.selected_item_sha256,
        "feature_values": list(candidate.feature_values),
        "feature_row_sha256": candidate.feature_row_sha256,
        "feature_as_of_date": candidate.feature_as_of_date.isoformat(),
        "available_date": candidate.available_date.isoformat(),
    }


def _canonical_json_bytes(payload: object) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256_payload(payload: object) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()


def _require_text(value: object, field_name: str) -> None:
    if type(value) is not str or not value.strip():
        raise ValueError(f"{field_name} 必須是非空白 str")


def _require_sha256(value: object, field_name: str) -> None:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise ValueError(f"{field_name} 必須是 sha256:<64 lowercase hex>")


def _freeze_feature_values(value: object) -> tuple[int | None, ...]:
    if type(value) not in (tuple, list):
        raise TypeError("feature_values 必須是 tuple/list")
    values: tuple[object, ...] = tuple(cast(Sequence[object], value))
    if any(item is not None and type(item) is not int for item in values):
        raise TypeError("feature_values 僅接受 exact int 或 None；bool 不可代替 int")
    return cast(tuple[int | None, ...], values)


def _freeze_feature_schema(value: object) -> FeatureSchema:
    if type(value) not in (tuple, list):
        raise TypeError("feature_schema 必須是 tuple/list")
    rows: list[tuple[str, str, str]] = []
    source_rows = cast(Sequence[object], value)
    for index, row in enumerate(source_rows):
        if type(row) not in (tuple, list):
            raise TypeError(f"feature_schema[{index}] 必須是三欄 tuple/list")
        values = cast(Sequence[object], row)
        if len(values) != 3:
            raise TypeError(f"feature_schema[{index}] 必須是三欄 tuple/list")
        if any(type(item) is not str or not item.strip() for item in values):
            raise TypeError(f"feature_schema[{index}] 欄位必須是非空白 str")
        rows.append((cast(str, values[0]), cast(str, values[1]), cast(str, values[2])))
    schema = tuple(rows)
    ids = tuple(item[0] for item in schema)
    if len(set(ids)) != len(ids):
        raise ValueError("feature_schema feature_id 不可重複")
    return schema


def _freeze_text_tuple(value: object, field_name: str) -> tuple[str, ...]:
    if type(value) not in (tuple, list):
        raise TypeError(f"{field_name} 必須是 tuple/list")
    raw_values = tuple(cast(Sequence[object], value))
    if any(type(item) is not str or not item.strip() for item in raw_values):
        raise TypeError(f"{field_name} 含有非空白 str 以外的值")
    return cast(tuple[str, ...], raw_values)


def _freeze_candidate_tuple(
    value: object,
) -> tuple[CandidateFeatureFactV1, ...]:
    if type(value) not in (tuple, list):
        raise TypeError("candidates 必須是 tuple/list")
    raw_candidates = tuple(cast(Sequence[object], value))
    if any(type(item) is not CandidateFeatureFactV1 for item in raw_candidates):
        raise TypeError("candidates 只能含 CandidateFeatureFactV1")
    return cast(tuple[CandidateFeatureFactV1, ...], raw_candidates)


def _snapshot_sequence(
    value: object,
    expected_type: type[_RecordT],
    field_name: str,
) -> tuple[_RecordT, ...]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise TypeError(f"{field_name} 必須是有序 sequence")
    values = tuple(cast(Sequence[object], value))
    if any(type(item) is not expected_type for item in values):
        raise TypeError(f"{field_name} 含不支援的 record 型別")
    return cast(tuple[_RecordT, ...], values)


__all__ = (
    "CandidateFeatureFactV1",
    "ML_PREPARATION_FACTS_V1",
    "RecommendationMLPreparationFactsV1",
    "build_recommendation_ml_preparation_facts_v1",
)
