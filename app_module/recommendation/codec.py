"""具型別與版本的推薦執行 codec，以及唯讀歷史資料解碼器。

本模組不寫入 artifact，也不連接持久化層。
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import MISSING, dataclass, fields, is_dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from enum import Enum
from hashlib import sha256
import json
import re
from types import UnionType
from typing import Any, Union, cast, get_args, get_origin, get_type_hints

from app_module.recommendation.contracts import (
    EXECUTION_SCHEMA_REVISION,
    SUPPORTED_EXECUTION_SCHEMA_REVISIONS,
    MLAvailability,
    MLAvailabilityReason,
    MLAvailabilityStatus,
    MLReceiptBinding,
    QualityReport,
    QualityStatus,
    RecommendationExecution,
    RecommendationConfigSnapshot,
    RecommendationResultConfigSnapshot,
    RecommendationRunEvidenceIdentity,
    RecommendationUniverseIdentity,
    ReferenceKind,
    Request,
    Context,
    ExecutionEvent,
    ExecutionStatus,
    SnapshotCohort,
    SnapshotCohortCoverage,
    SnapshotCohortCoverageStatus,
    StrategyConfigIdentity,
    UniversePolicyIdentity,
    UniverseSnapshotIdentity,
    VersionReference,
    schema_version,
)
from data_module.contracts.market import SourceRef
from decision_module.recommendation.contracts import (
    CandidateAssessment,
    DecisionBatch,
    FactorContribution,
    FilterOutcome,
    LiquidityAssessment,
    NegativeEvidence,
    RecommendationItem,
    RegimeStateTransition,
    UniverseReference,
)


class ExecutionCodecError(ValueError):
    """新格式執行 payload 無效或不受支援時拋出的錯誤。"""


@dataclass(frozen=True, slots=True)
class ExecutionReadEnvelope:
    """保留來源 artifact header、hash 與原始 bytes 的唯讀解碼結果。"""

    execution: RecommendationExecution
    schema_version: str
    schema_revision: int
    payload_hash: str
    raw_payload_sha256: str
    raw_payload: bytes


_HASH_PATTERN = re.compile(r"(?:sha256:)?[0-9a-f]{64}\Z")

# 這些識別碼是封閉的 wire allowlist，不是匯入路徑；欄位定義仍由各 record
# 自己的 dataclass 負責。
_RECORD_IDS: dict[type[object], str] = {
    RecommendationExecution: "recommendation.execution.v1",
    Request: "recommendation.request.v1",
    Context: "recommendation.context.v1",
    RecommendationConfigSnapshot: "recommendation.config-snapshot.v1",
    RecommendationResultConfigSnapshot: "recommendation.result-config-snapshot.v1",
    StrategyConfigIdentity: "recommendation.strategy-config-identity.v1",
    UniversePolicyIdentity: "recommendation.universe-policy-identity.v1",
    UniverseSnapshotIdentity: "recommendation.universe-snapshot-identity.v1",
    RecommendationUniverseIdentity: "recommendation.universe-identity.v1",
    SnapshotCohortCoverage: "recommendation.snapshot-cohort-coverage.v1",
    SnapshotCohort: "recommendation.snapshot-cohort.v1",
    RecommendationRunEvidenceIdentity: "recommendation.run-evidence-identity.v1",
    QualityReport: "recommendation.quality-report.v1",
    ExecutionEvent: "recommendation.execution-event.v1",
    MLAvailability: "recommendation.ml-availability.v1",
    MLReceiptBinding: "recommendation.ml-receipt-binding.v1",
    VersionReference: "recommendation.version-reference.v1",
    SourceRef: "data.source-reference.v1",
    DecisionBatch: "decision.recommendation-batch.v1",
    CandidateAssessment: "decision.candidate-assessment.v1",
    FactorContribution: "decision.factor-contribution.v1",
    FilterOutcome: "decision.filter-outcome.v1",
    LiquidityAssessment: "decision.liquidity-assessment.v1",
    NegativeEvidence: "decision.negative-evidence.v1",
    RecommendationItem: "decision.recommendation-item.v1",
    RegimeStateTransition: "decision.regime-state-transition.v1",
    UniverseReference: "decision.universe-reference.v1",
}
_RECORD_TYPES = {wire_id: record_type for record_type, wire_id in _RECORD_IDS.items()}

_ENUM_IDS: dict[type[Enum], str] = {
    ReferenceKind: "recommendation.reference-kind.v1",
    ExecutionStatus: "recommendation.execution-status.v1",
    QualityStatus: "recommendation.quality-status.v1",
    MLAvailabilityStatus: "recommendation.ml-availability-status.v1",
    MLAvailabilityReason: "recommendation.ml-availability-reason.v1",
    SnapshotCohortCoverageStatus: "recommendation.snapshot-cohort-coverage-status.v1",
}
_ENUM_TYPES = {wire_id: enum_type for enum_type, wire_id in _ENUM_IDS.items()}

_TAG_RECORD = "$record"
_TAG_ENUM = "$enum"
_TAG_DECIMAL = "$decimal"
_TAG_DATE = "$date"
_TAG_DATETIME = "$datetime"
_TAG_MAPPING = "$mapping"


def _canonical_json_bytes(value: object) -> bytes:
    try:
        text = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ExecutionCodecError("payload 無法轉為 canonical JSON") from exc
    return text.encode("utf-8")


def _type_name(record_type: type[object]) -> str:
    wire_id = _RECORD_IDS.get(record_type)
    if wire_id is None:
        raise ExecutionCodecError(f"未允許的 contract type: {record_type.__name__}")
    return wire_id


def _is_mapping_origin(origin: object) -> bool:
    return isinstance(origin, type) and issubclass(origin, Mapping)


def _encode_record(value: object) -> dict[str, object]:
    record_type = type(value)
    wire_id = _type_name(record_type)
    if not is_dataclass(value):
        raise ExecutionCodecError(f"{record_type.__name__} 不是 dataclass contract")
    params = getattr(record_type, "__dataclass_params__", None)
    if params is None or not params.frozen:
        raise ExecutionCodecError(f"{wire_id} 必須是 frozen contract")

    try:
        annotations = get_type_hints(record_type)
    except (NameError, TypeError) as exc:
        raise ExecutionCodecError(f"{wire_id} 的 annotations 無法解析") from exc

    encoded_fields: dict[str, object] = {}
    for item in fields(value):
        if item.name not in annotations:
            raise ExecutionCodecError(f"{wire_id}.{item.name} 缺少型別 annotation")
        field_value = getattr(value, item.name)
        encoded_fields[item.name] = _encode_value(
            field_value, annotations[item.name], f"{wire_id}.{item.name}"
        )
    return {_TAG_RECORD: wire_id, "fields": encoded_fields}


def _encode_value(value: object, annotation: object, path: str) -> object:
    if annotation is Any or annotation is object:
        return _encode_dynamic(value, path)

    origin = get_origin(annotation)
    if origin in (Union, UnionType):
        errors: list[ExecutionCodecError] = []
        for option in get_args(annotation):
            try:
                return _encode_value(value, option, path)
            except ExecutionCodecError as exc:
                errors.append(exc)
        raise ExecutionCodecError(f"{path} 不符合 union annotation") from (
            errors[-1] if errors else None
        )

    if annotation is type(None):
        if value is None:
            return None
        raise ExecutionCodecError(f"{path} 不允許非空值")
    if value is None:
        raise ExecutionCodecError(f"{path} 不允許 None")

    if origin is tuple:
        if type(value) is not tuple:
            raise ExecutionCodecError(f"{path} 必須是 tuple")
        arguments = get_args(annotation)
        if len(arguments) == 2 and arguments[1] is Ellipsis:
            item_annotation = arguments[0]
            return [
                _encode_value(item, item_annotation, f"{path}[{index}]")
                for index, item in enumerate(value)
            ]
        if len(value) != len(arguments):
            raise ExecutionCodecError(f"{path} tuple 長度不符")
        return [
            _encode_value(item, item_annotation, f"{path}[{index}]")
            for index, (item, item_annotation) in enumerate(zip(value, arguments))
        ]

    if _is_mapping_origin(origin):
        if not isinstance(value, Mapping):
            raise ExecutionCodecError(f"{path} 必須是 mapping")
        key_annotation, value_annotation = get_args(annotation) or (str, object)
        if key_annotation is not str:
            raise ExecutionCodecError(f"{path} 只支援 str mapping key")
        encoded_mapping: dict[str, object] = {}
        for key, item in value.items():
            if type(key) is not str:
                raise ExecutionCodecError(f"{path} mapping key 必須是內建 str")
            encoded_mapping[key] = _encode_value(
                item, value_annotation, f"{path}.{key}"
            )
        return encoded_mapping

    if isinstance(annotation, type) and issubclass(annotation, Enum):
        if type(value) is not annotation or annotation not in _ENUM_IDS:
            raise ExecutionCodecError(f"{path} enum 不在 wire allowlist")
        enum_value = value.value
        if type(enum_value) not in (str, int, bool):
            raise ExecutionCodecError(f"{path} enum value 型別不支援")
        return {_TAG_ENUM: _ENUM_IDS[annotation], "value": enum_value}

    if annotation is Decimal:
        if type(value) is not Decimal or not value.is_finite():
            raise ExecutionCodecError(f"{path} 必須是有限 Decimal")
        return {_TAG_DECIMAL: str(value)}

    if annotation is datetime:
        if type(value) is not datetime or value.utcoffset() is None:
            raise ExecutionCodecError(f"{path} 必須是含 offset 的內建 datetime")
        return {_TAG_DATETIME: value.isoformat()}

    if annotation is date:
        if type(value) is not date:
            raise ExecutionCodecError(f"{path} 必須是 date")
        return {_TAG_DATE: value.isoformat()}

    if annotation is bool:
        if type(value) is not bool:
            raise ExecutionCodecError(f"{path} 必須是 bool")
        return value
    if annotation is int:
        if type(value) is not int:
            raise ExecutionCodecError(f"{path} 必須是 JSON integer 對應的 int")
        return value
    if annotation is str:
        if type(value) is not str:
            raise ExecutionCodecError(f"{path} 必須是內建 str")
        return value

    if isinstance(annotation, type) and annotation in _RECORD_IDS:
        if type(value) is not annotation:
            raise ExecutionCodecError(f"{path} 必須是 {annotation.__name__}")
        return _encode_record(value)

    raise ExecutionCodecError(f"{path} annotation 不在 codec allowlist")


def _encode_dynamic(value: object, path: str) -> object:
    if value is None or type(value) in (str, int, bool):
        return value
    if type(value) is Decimal:
        if not value.is_finite():
            raise ExecutionCodecError(f"{path} 必須是有限 Decimal")
        return {_TAG_DECIMAL: str(value)}
    if type(value) is datetime:
        if value.utcoffset() is None:
            raise ExecutionCodecError(f"{path} datetime 必須含 offset")
        return {_TAG_DATETIME: value.isoformat()}
    if type(value) is date:
        return {_TAG_DATE: value.isoformat()}
    if isinstance(value, Enum):
        enum_type = type(value)
        wire_id = _ENUM_IDS.get(enum_type)
        if wire_id is None:
            raise ExecutionCodecError(f"{path} enum 不在 wire allowlist")
        enum_value = value.value
        if type(enum_value) not in (str, int, bool):
            raise ExecutionCodecError(f"{path} enum value 型別不支援")
        return {_TAG_ENUM: wire_id, "value": enum_value}
    if type(value) is tuple:
        return [_encode_dynamic(item, f"{path}[{index}]") for index, item in enumerate(value)]
    if isinstance(value, Mapping):
        encoded: dict[str, object] = {}
        for key, item in value.items():
            if type(key) is not str:
                raise ExecutionCodecError(f"{path} mapping key 必須是內建 str")
            encoded[key] = _encode_dynamic(item, f"{path}.{key}")
        # 以 wrapper 區分一般 mapping 與 typed record 標記。
        return {_TAG_MAPPING: encoded}
    if type(value) in _RECORD_IDS:
        return _encode_record(value)
    raise ExecutionCodecError(f"{path} runtime type 不在 codec allowlist")


def _decode_record(value: object, expected_type: type[object], path: str) -> object:
    if type(value) is not dict or set(value) != {_TAG_RECORD, "fields"}:
        raise ExecutionCodecError(f"{path} 必須是 typed record")
    wire_id = value[_TAG_RECORD]
    if type(wire_id) is not str:
        raise ExecutionCodecError(f"{path} record id 必須是 str")
    record_type = _RECORD_TYPES.get(wire_id)
    if record_type is None:
        raise ExecutionCodecError(f"{path} 不支援 contract type {wire_id!r}")
    if record_type is not expected_type:
        raise ExecutionCodecError(f"{path} record type 與欄位 annotation 不符")
    raw_fields = value["fields"]
    if type(raw_fields) is not dict:
        raise ExecutionCodecError(f"{path}.fields 必須是 object")

    try:
        annotations = get_type_hints(record_type)
    except (NameError, TypeError) as exc:
        raise ExecutionCodecError(f"{wire_id} 的 annotations 無法解析") from exc
    declared_fields = {item.name: item for item in fields(cast(Any, record_type))}
    unknown_fields = set(raw_fields) - set(declared_fields)
    if unknown_fields:
        raise ExecutionCodecError(
            f"{path} 含未知欄位: {', '.join(sorted(unknown_fields))}"
        )

    kwargs: dict[str, object] = {}
    for name, item in declared_fields.items():
        if name in raw_fields:
            kwargs[name] = _decode_value(
                raw_fields[name], annotations[name], f"{path}.{name}"
            )
        elif item.default is not MISSING:
            kwargs[name] = item.default
        elif item.default_factory is not MISSING:
            kwargs[name] = item.default_factory()
        else:
            raise ExecutionCodecError(f"{path} 缺少必要欄位 {name}")
    try:
        return record_type(**kwargs)
    except (TypeError, ValueError) as exc:
        raise ExecutionCodecError(f"{path} contract 驗證失敗: {exc}") from exc


def _decode_value(value: object, annotation: object, path: str) -> object:
    if annotation is Any or annotation is object:
        return _decode_dynamic(value, path)

    origin = get_origin(annotation)
    if origin in (Union, UnionType):
        options = get_args(annotation)
        if value is None and type(None) in options:
            return None
        last_error: ExecutionCodecError | None = None
        for option in options:
            if option is type(None):
                continue
            try:
                return _decode_value(value, option, path)
            except ExecutionCodecError as exc:
                last_error = exc
        raise ExecutionCodecError(f"{path} wire value 不符合 union annotation") from last_error

    if value is None:
        raise ExecutionCodecError(f"{path} 不允許 null")

    if origin is tuple:
        if type(value) is not list:
            raise ExecutionCodecError(f"{path} tuple wire value 必須是 array")
        arguments = get_args(annotation)
        if len(arguments) == 2 and arguments[1] is Ellipsis:
            return tuple(
                _decode_value(item, arguments[0], f"{path}[{index}]")
                for index, item in enumerate(value)
            )
        if len(value) != len(arguments):
            raise ExecutionCodecError(f"{path} tuple 長度不符")
        return tuple(
            _decode_value(item, item_annotation, f"{path}[{index}]")
            for index, (item, item_annotation) in enumerate(zip(value, arguments))
        )

    if _is_mapping_origin(origin):
        if type(value) is not dict:
            raise ExecutionCodecError(f"{path} mapping wire value 必須是 object")
        key_annotation, value_annotation = get_args(annotation) or (str, object)
        if key_annotation is not str:
            raise ExecutionCodecError(f"{path} 只支援 str mapping key")
        if any(type(key) is not str for key in value):
            raise ExecutionCodecError(f"{path} mapping key 必須是 str")
        return {
            key: _decode_value(item, value_annotation, f"{path}.{key}")
            for key, item in value.items()
        }

    if isinstance(annotation, type) and issubclass(annotation, Enum):
        if type(value) is not dict or set(value) != {_TAG_ENUM, "value"}:
            raise ExecutionCodecError(f"{path} 必須是 enum tag")
        wire_id = value[_TAG_ENUM]
        if type(wire_id) is not str or _ENUM_TYPES.get(wire_id) is not annotation:
            raise ExecutionCodecError(f"{path} enum type 不支援")
        try:
            return annotation(value["value"])
        except (TypeError, ValueError) as exc:
            raise ExecutionCodecError(f"{path} enum value 不支援") from exc

    if annotation is Decimal:
        return _decode_decimal(value, path)
    if annotation is datetime:
        return _decode_datetime(value, path)
    if annotation is date:
        return _decode_date(value, path)
    if annotation is bool:
        if type(value) is not bool:
            raise ExecutionCodecError(f"{path} 必須是 JSON boolean")
        return value
    if annotation is int:
        if type(value) is not int:
            raise ExecutionCodecError(f"{path} 必須是 JSON integer")
        return value
    if annotation is str:
        if type(value) is not str:
            raise ExecutionCodecError(f"{path} 必須是 JSON string")
        return value
    if isinstance(annotation, type) and annotation in _RECORD_IDS:
        return _decode_record(value, annotation, path)
    raise ExecutionCodecError(f"{path} annotation 不在 codec allowlist")


def _decode_dynamic(value: object, path: str) -> object:
    if value is None or type(value) in (str, int, bool):
        return value
    if type(value) is list:
        return tuple(_decode_dynamic(item, f"{path}[{index}]") for index, item in enumerate(value))
    if type(value) is not dict:
        raise ExecutionCodecError(f"{path} runtime wire type 不支援")
    if set(value) == {_TAG_DECIMAL}:
        return _decode_decimal(value, path)
    if set(value) == {_TAG_DATE}:
        return _decode_date(value, path)
    if set(value) == {_TAG_DATETIME}:
        return _decode_datetime(value, path)
    if set(value) == {_TAG_ENUM, "value"}:
        wire_id = value[_TAG_ENUM]
        enum_type = _ENUM_TYPES.get(wire_id) if type(wire_id) is str else None
        if enum_type is None:
            raise ExecutionCodecError(f"{path} enum type 不支援")
        try:
            return enum_type(value["value"])
        except (TypeError, ValueError) as exc:
            raise ExecutionCodecError(f"{path} enum value 不支援") from exc
    if set(value) == {_TAG_RECORD, "fields"}:
        wire_id = value.get(_TAG_RECORD)
        record_type = _RECORD_TYPES.get(wire_id) if type(wire_id) is str else None
        if record_type is None:
            raise ExecutionCodecError(f"{path} contract type 不支援")
        return _decode_record(value, record_type, path)
    if set(value) == {_TAG_MAPPING} and type(value[_TAG_MAPPING]) is dict:
        mapping = value[_TAG_MAPPING]
        if any(type(key) is not str for key in mapping):
            raise ExecutionCodecError(f"{path} mapping key 必須是 str")
        return {
            key: _decode_dynamic(item, f"{path}.{key}")
            for key, item in mapping.items()
        }
    raise ExecutionCodecError(f"{path} 含未知或不明確的 dynamic object")


def _decode_decimal(value: object, path: str) -> Decimal:
    if type(value) is not dict or set(value) != {_TAG_DECIMAL}:
        raise ExecutionCodecError(f"{path} 必須是 Decimal tag")
    raw = value[_TAG_DECIMAL]
    if type(raw) is not str:
        raise ExecutionCodecError(f"{path} Decimal wire value 必須是 str")
    try:
        result = Decimal(raw)
    except InvalidOperation as exc:
        raise ExecutionCodecError(f"{path} Decimal 字串無效") from exc
    if not result.is_finite() or str(result) != raw:
        raise ExecutionCodecError(f"{path} Decimal 必須是有限 canonical 字串")
    return result


def _decode_date(value: object, path: str) -> date:
    if type(value) is not dict or set(value) != {_TAG_DATE}:
        raise ExecutionCodecError(f"{path} 必須是 date tag")
    raw = value[_TAG_DATE]
    if type(raw) is not str:
        raise ExecutionCodecError(f"{path} date wire value 必須是 str")
    try:
        result = date.fromisoformat(raw)
    except ValueError as exc:
        raise ExecutionCodecError(f"{path} date 格式無效") from exc
    if type(result) is not date or result.isoformat() != raw:
        raise ExecutionCodecError(f"{path} date 必須是 canonical ISO date")
    return result


def _decode_datetime(value: object, path: str) -> datetime:
    if type(value) is not dict or set(value) != {_TAG_DATETIME}:
        raise ExecutionCodecError(f"{path} 必須是 datetime tag")
    raw = value[_TAG_DATETIME]
    if type(raw) is not str:
        raise ExecutionCodecError(f"{path} datetime wire value 必須是 str")
    try:
        result = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ExecutionCodecError(f"{path} datetime 格式無效") from exc
    if result.utcoffset() is None or result.isoformat() != raw:
        raise ExecutionCodecError(f"{path} 必須是含 offset 的 canonical ISO datetime")
    return result


def _verify_raw_hash(raw_payload: bytes, expected_hash: str) -> None:
    if type(raw_payload) is not bytes:
        raise TypeError("歷史 payload 必須以原始 bytes 傳入")
    if type(expected_hash) is not str or _HASH_PATTERN.fullmatch(expected_hash) is None:
        raise ExecutionCodecError("expected_sha256 必須是 sha256 hex")
    expected_hex = expected_hash.removeprefix("sha256:")
    actual_hex = sha256(raw_payload).hexdigest()
    if actual_hex != expected_hex:
        raise ExecutionCodecError("原始 artifact SHA-256 不符；尚未解析或建立 DTO")


def _strict_json_load(raw_payload: bytes) -> object:
    if type(raw_payload) is not bytes:
        raise TypeError("codec payload 必須是 bytes")

    def reject_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ExecutionCodecError(f"JSON object 含重複 key: {key}")
            result[key] = value
        return result

    def reject_constant(value: str) -> object:
        raise ExecutionCodecError(f"JSON 不允許非有限數值: {value}")

    try:
        return json.loads(
            raw_payload.decode("utf-8"),
            object_pairs_hook=reject_duplicates,
            parse_constant=reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ExecutionCodecError("payload 不是有效 UTF-8 JSON") from exc


def _hash_material(document: Mapping[str, object]) -> dict[str, object]:
    return {
        "schema_version": document.get("schema_version"),
        "schema_revision": document.get("schema_revision"),
        "payload": document.get("payload"),
    }


def encode_execution(
    execution: RecommendationExecution,
) -> bytes:
    """將一筆封存的執行結果編碼為確定性的 UTF-8 JSON bytes。

    雜湊材料包含固定 schema header 與具型別 payload。輸出的 canonical artifact
    不包含可變 metadata；label、notes、persisted_at 等由 index 獨立保存。本函式
    只負責 codec，持久化與 artifact 發布由後續遷移任務負責。
    """

    if type(execution) is not RecommendationExecution:
        raise ExecutionCodecError("encode_execution 僅接受 RecommendationExecution")
    encoded_payload = _encode_record(execution)
    header: dict[str, object] = {
        "schema_version": schema_version,
        "schema_revision": EXECUTION_SCHEMA_REVISION,
        "payload": encoded_payload,
    }
    payload_hash = "sha256:" + sha256(_canonical_json_bytes(header)).hexdigest()
    document = dict(header)
    document["payload_hash"] = payload_hash
    return _canonical_json_bytes(document)


def _decode_execution_document(
    document: object, *, raw_payload: bytes | None = None
) -> RecommendationExecution:
    if type(document) is not dict:
        raise ExecutionCodecError("new execution artifact 頂層必須是 object")
    required = {"schema_version", "schema_revision", "payload", "payload_hash"}
    if set(document) != required:
        raise ExecutionCodecError("new execution artifact header 欄位不完整或含未知欄位")
    schema = document["schema_version"]
    revision = document["schema_revision"]
    payload_hash = document["payload_hash"]
    if type(schema) is not str or type(revision) is not int:
        raise ExecutionCodecError("schema header 型別錯誤")
    if type(payload_hash) is not str or _HASH_PATTERN.fullmatch(payload_hash) is None:
        raise ExecutionCodecError("payload_hash 格式錯誤")
    actual_hash = "sha256:" + sha256(_canonical_json_bytes(_hash_material(document))).hexdigest()
    if actual_hash != payload_hash:
        raise ExecutionCodecError("canonical payload hash 不符；尚未 decode contract")
    if schema != schema_version:
        raise ExecutionCodecError(f"不支援 schema_version: {schema!r}")
    if revision not in SUPPORTED_EXECUTION_SCHEMA_REVISIONS:
        raise ExecutionCodecError(f"不支援 schema_revision: {revision!r}")
    if raw_payload is not None and raw_payload != _canonical_json_bytes(document):
        raise ExecutionCodecError("execution artifact bytes 不是 canonical UTF-8 JSON")
    result = _decode_record(
        document["payload"], RecommendationExecution, "payload"
    )
    return result  # type: ignore[return-value]  # contract decoder 保證此回傳型別


def decode_execution(raw_payload: bytes) -> RecommendationExecution:
    """驗證 canonical hash，並解碼受支援的新格式執行結果。"""

    return decode_execution_envelope(raw_payload).execution


def decode_execution_envelope(raw_payload: bytes) -> ExecutionReadEnvelope:
    """解碼新格式 execution，並公開保留的來源 revision 與原始 bytes。

    `decode_execution` 維持原本回傳 RecommendationExecution 的 ABI；讀取歷史
    revision 的 caller 可使用本 envelope 取得來源 header 與 hash，不需重新編碼。
    """

    document = _strict_json_load(raw_payload)
    execution = _decode_execution_document(document, raw_payload=raw_payload)
    assert type(document) is dict  # 上方 decoder 已驗證文件結構。
    assert type(raw_payload) is bytes  # strict loader 已驗證輸入型別。
    return ExecutionReadEnvelope(
        execution=execution,
        schema_version=cast(str, document["schema_version"]),
        schema_revision=cast(int, document["schema_revision"]),
        payload_hash=cast(str, document["payload_hash"]),
        raw_payload_sha256="sha256:" + sha256(raw_payload).hexdigest(),
        raw_payload=raw_payload,
    )


def encode_legacy_recommendation(value: object) -> dict[str, object]:
    """輸出保留中英文欄位名稱的歷史 DTO dictionary。

    這個明確的 legacy export 僅供舊呼叫端與 characterization 使用，並非新格式
    artifact writer。
    """

    from app_module.recommendation.legacy_dtos import RecommendationDTO

    if not isinstance(value, RecommendationDTO):
        raise TypeError("legacy export 僅接受 RecommendationDTO")
    dto = value
    result: dict[str, object] = {
        "證券代號": dto.stock_code,
        "證券名稱": dto.stock_name,
        "收盤價": dto.close_price,
        "漲幅%": dto.price_change,
        "總分": dto.total_score,
        "指標分": dto.indicator_score,
        "圖形分": dto.pattern_score,
        "成交量分": dto.volume_score,
        "推薦理由": dto.recommendation_reasons,
        "產業": dto.industry,
        "Regime匹配": "是" if dto.regime_match else "否",
        "score_percentile_bp": dto.score_percentile_bp,
        "eligible_universe_size": dto.eligible_universe_size,
        "eligible_universe_date": dto.eligible_universe_date,
        "ranking_method": dto.ranking_method,
        "threshold_mode": dto.threshold_mode,
    }
    result.update(
        {
            "ranking_score_bp": dto.ranking_score_bp,
            "calibrated_probability_bp": dto.calibrated_probability_bp,
            "calibrated_probability_status": dto.calibrated_probability_status,
            "after_cost_profit_probability_bp": dto.after_cost_profit_probability_bp,
            "after_cost_profit_probability_status": dto.after_cost_profit_probability_status,
            "evidence_confidence": dto.evidence_confidence,
            "sample_size": dto.sample_size,
            "cost_basis_bp": dto.cost_basis_bp,
            "calibration_model_version": dto.calibration_model_version,
            "calibration_dataset_version": dto.calibration_dataset_version,
            "calibration_horizon": dto.calibration_horizon,
            "calibration_status": dto.calibration_status,
            "calibration_source": dto.calibration_source,
            "calibration_warnings": list(dto.calibration_warnings),
            "calibration_source_trace": list(dto.calibration_source_trace),
            "calibration_probability_transform_id": dto.calibration_probability_transform_id,
            "calibration_probability_baseline_id": dto.calibration_probability_baseline_id,
            "calibration_probability_baseline_kind": dto.calibration_probability_baseline_kind,
            "calibration_probability_baseline_probability_bp": dto.calibration_probability_baseline_probability_bp,
            "calibration_raw_probability_bp": dto.calibration_raw_probability_bp,
            "calibration_raw_after_cost_probability_bp": dto.calibration_raw_after_cost_probability_bp,
            "calibration_provenance": deepcopy(dto.calibration_provenance),
        }
    )
    if dto.threshold_mode == "quantile":
        result["百分位"] = (
            f"{dto.score_percentile_bp / 100:.2f}%"
            if dto.score_percentile_bp is not None
            else "N/A"
        )
        result["母體數"] = (
            dto.eligible_universe_size
            if dto.eligible_universe_size is not None
            else "N/A"
        )
        result["排名日期"] = (
            dto.eligible_universe_date
            if dto.eligible_universe_date is not None
            else "N/A"
        )
        result["排名方法"] = (
            dto.ranking_method if dto.ranking_method is not None else "N/A"
        )
        result["門檻模式"] = "百分位"
    return result


def decode_legacy_recommendation(
    data: Mapping[str, Any], *, dto_type: type[Any] | None = None
) -> Any:
    """唯讀解碼已知的 RecommendationDTO 中英文歷史欄位格式。"""

    from app_module.recommendation.legacy_dtos import RecommendationDTO

    selected_type = RecommendationDTO if dto_type is None else dto_type
    if not isinstance(data, Mapping):
        raise TypeError("legacy recommendation 必須是 mapping")
    if not isinstance(selected_type, type) or not issubclass(selected_type, RecommendationDTO):
        raise TypeError("dto_type 必須是 RecommendationDTO")
    stock_code = data.get("stock_code", data.get("證券代號", ""))
    stock_name = data.get("stock_name", data.get("證券名稱", ""))
    close_price = data.get("close_price", data.get("收盤價", 0.0))
    price_change = data.get("price_change", data.get("漲幅%", 0.0))
    total_score = data.get("total_score", data.get("總分", 0.0))
    indicator_score = data.get("indicator_score", data.get("指標分", 0.0))
    pattern_score = data.get("pattern_score", data.get("圖形分", 0.0))
    volume_score = data.get("volume_score", data.get("成交量分", 0.0))
    recommendation_reasons = data.get("recommendation_reasons", data.get("推薦理由", ""))
    industry = data.get("industry", data.get("產業", ""))
    regime_match_value = data.get("regime_match", data.get("Regime匹配", False))
    regime_match = (
        regime_match_value == "是"
        if isinstance(regime_match_value, str)
        else bool(regime_match_value)
    )
    provenance = data.get("calibration_provenance")
    return selected_type(
        stock_code=str(stock_code),
        stock_name=str(stock_name),
        close_price=Decimal(str(close_price)),
        price_change=float(price_change),
        total_score=float(total_score),
        indicator_score=float(indicator_score),
        pattern_score=float(pattern_score),
        volume_score=float(volume_score),
        recommendation_reasons=str(recommendation_reasons),
        industry=str(industry),
        regime_match=regime_match,
        score_percentile_bp=data.get("score_percentile_bp"),
        eligible_universe_size=data.get("eligible_universe_size"),
        eligible_universe_date=data.get("eligible_universe_date"),
        ranking_method=data.get("ranking_method"),
        threshold_mode=data.get("threshold_mode", "fixed"),
        ranking_score_bp=data.get("ranking_score_bp"),
        calibrated_probability_bp=data.get("calibrated_probability_bp"),
        calibrated_probability_status=data.get(
            "calibrated_probability_status", "unavailable"
        ),
        after_cost_profit_probability_bp=data.get("after_cost_profit_probability_bp"),
        after_cost_profit_probability_status=data.get(
            "after_cost_profit_probability_status", "unavailable"
        ),
        evidence_confidence=str(data.get("evidence_confidence", "") or ""),
        sample_size=data.get("sample_size"),
        cost_basis_bp=data.get("cost_basis_bp"),
        calibration_model_version=str(data.get("calibration_model_version", "") or ""),
        calibration_dataset_version=str(data.get("calibration_dataset_version", "") or ""),
        calibration_horizon=str(data.get("calibration_horizon", "") or ""),
        calibration_status=str(data.get("calibration_status", "unavailable") or "unavailable"),
        calibration_source=str(data.get("calibration_source", "") or ""),
        calibration_warnings=[str(item) for item in (data.get("calibration_warnings") or [])],
        calibration_source_trace=[str(item) for item in (data.get("calibration_source_trace") or [])],
        calibration_probability_transform_id=str(
            data.get("calibration_probability_transform_id", "") or ""
        ),
        calibration_probability_baseline_id=str(
            data.get("calibration_probability_baseline_id", "") or ""
        ),
        calibration_probability_baseline_kind=str(
            data.get("calibration_probability_baseline_kind", "") or ""
        ),
        calibration_probability_baseline_probability_bp=data.get(
            "calibration_probability_baseline_probability_bp"
        ),
        calibration_raw_probability_bp=data.get("calibration_raw_probability_bp"),
        calibration_raw_after_cost_probability_bp=data.get(
            "calibration_raw_after_cost_probability_bp"
        ),
        calibration_provenance=(
            dict(provenance) if isinstance(provenance, Mapping) else {}
        ),
    )


def decode_legacy_result(
    raw_payload: bytes, *, expected_sha256: str
) -> object:
    """先驗證歷史 bytes，再解碼成唯讀 legacy artifact DTO view。"""

    _verify_raw_hash(raw_payload, expected_sha256)
    try:
        document = json.loads(raw_payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ExecutionCodecError("legacy artifact 不是有效 UTF-8 JSON") from exc
    if not isinstance(document, Mapping):
        raise ExecutionCodecError("legacy artifact 頂層必須是 object")
    if "schema_version" in document or "schema_revision" in document:
        raise ExecutionCodecError("含 schema header 的 artifact 必須走 decode_execution")
    from app_module.recommendation.legacy_dtos import RecommendationResultDTO

    return RecommendationResultDTO.from_dict(cast(dict[str, Any], document))


def decode_artifact(
    raw_payload: bytes, *, expected_sha256: str
) -> RecommendationExecution | object:
    """先驗證來源 bytes，再唯讀分派新格式 execution 或 legacy DTO。"""

    _verify_raw_hash(raw_payload, expected_sha256)
    document = _strict_json_load(raw_payload)
    if type(document) is dict and (
        "schema_version" in document or "schema_revision" in document
    ):
        return _decode_execution_document(document, raw_payload=raw_payload)
    if type(document) is not dict:
        raise ExecutionCodecError("legacy artifact 頂層必須是 object")
    from app_module.recommendation.legacy_dtos import RecommendationResultDTO

    return RecommendationResultDTO.from_dict(cast(dict[str, Any], document))


__all__ = (
    "ExecutionReadEnvelope",
    "ExecutionCodecError",
    "decode_artifact",
    "decode_execution",
    "decode_execution_envelope",
    "decode_legacy_recommendation",
    "decode_legacy_result",
    "encode_execution",
    "encode_legacy_recommendation",
)
