"""推薦回放 parent/child lineage 的獨立版本化 sidecar 契約與 codec。"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from hashlib import sha256
from typing import ClassVar, cast

from app_module.recommendation.codec import (
    ExecutionCodecError,
    decode_execution_envelope,
    encode_execution,
)
from app_module.recommendation.contracts import (
    ExecutionStatus,
    RecommendationExecution,
    ReferenceKind,
    SaveReceipt,
    VersionReference,
)


REPLAY_LINEAGE_SCHEMA_VERSION = "recommendation-replay-lineage.v1"
REPLAY_LINEAGE_SCHEMA_REVISION = 1
_SHA256_PATTERN = re.compile(r"sha256:[0-9a-f]{64}\Z")
_REFERENCE_KINDS = {item.value: item for item in ReferenceKind}


class ReplayLineageCodecError(ValueError):
    """回放 lineage sidecar 格式、版本或內容雜湊無效。"""


class ReplayDataSnapshotStatusV1(str, Enum):
    """child 執行的資料快照參照是否可用。"""

    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


def _require_nonblank(value: object, field_name: str) -> str:
    if type(value) is not str:
        raise TypeError(f"{field_name} 必須是 str")
    if not value.strip():
        raise ValueError(f"{field_name} 不可為空白")
    return value


def _require_sha256(value: object, field_name: str) -> str:
    if type(value) is not str or _SHA256_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{field_name} 必須是小寫 sha256:<64 hex>")
    return value


def _freeze_references(
    value: object,
    *,
    field_name: str,
    expected_kind: ReferenceKind,
) -> tuple[VersionReference, ...]:
    if type(value) not in (tuple, list):
        raise TypeError(f"{field_name} 必須是 VersionReference tuple 或 list")
    references = cast(tuple[object, ...] | list[object], value)
    frozen = tuple(references)
    if any(type(item) is not VersionReference for item in frozen):
        raise TypeError(f"{field_name} 必須只包含 VersionReference")
    typed_references = cast(tuple[VersionReference, ...], frozen)
    if any(item.kind is not expected_kind for item in typed_references):
        raise ValueError(
            f"{field_name} 只接受 {expected_kind.value} references"
        )
    return typed_references


@dataclass(frozen=True, slots=True)
class ReplayLineageChildV1:
    """一個 replay 日期 child 的 canonical execution 身份。"""

    snapshot_date: date
    result_id: str
    canonical_payload_sha256: str
    replay_parent_ref: VersionReference
    data_snapshot_status: ReplayDataSnapshotStatusV1
    data_snapshot_refs: tuple[VersionReference, ...] = ()

    def __post_init__(self) -> None:
        if type(self.snapshot_date) is not date:
            raise TypeError("snapshot_date 必須是 date")
        _require_nonblank(self.result_id, "result_id")
        _require_sha256(self.canonical_payload_sha256, "canonical_payload_sha256")
        if type(self.replay_parent_ref) is not VersionReference:
            raise TypeError("replay_parent_ref 必須是 VersionReference")
        if self.replay_parent_ref.kind is not ReferenceKind.REPLAY_PARENT:
            raise ValueError("replay_parent_ref 必須是 replay_parent reference")
        if type(self.data_snapshot_status) is not ReplayDataSnapshotStatusV1:
            raise TypeError("data_snapshot_status 必須是 ReplayDataSnapshotStatusV1")
        references = _freeze_references(
            self.data_snapshot_refs,
            field_name="data_snapshot_refs",
            expected_kind=ReferenceKind.DATA_SNAPSHOT,
        )
        if self.data_snapshot_status is ReplayDataSnapshotStatusV1.AVAILABLE:
            if not references:
                raise ValueError("available data snapshot 必須有至少一個 reference")
        elif references:
            raise ValueError("unavailable data snapshot 不可包含 references")
        object.__setattr__(self, "data_snapshot_refs", references)

    @classmethod
    def from_execution(
        cls,
        execution: RecommendationExecution,
        *,
        snapshot_date: date,
        receipt: SaveReceipt | None = None,
    ) -> ReplayLineageChildV1:
        """由 canonical execution 及可選保存 receipt 建立 child facts。"""

        if type(execution) is not RecommendationExecution:
            raise TypeError("execution 必須是 RecommendationExecution")
        if execution.status is not ExecutionStatus.COMPLETED:
            raise ValueError("lineage child 只接受 completed execution")
        if type(snapshot_date) is not date:
            raise TypeError("snapshot_date 必須是 date")
        if execution.context.as_of_date != snapshot_date:
            raise ValueError("snapshot_date 必須符合 child execution context.as_of_date")

        parent_references = tuple(
            item
            for item in execution.related_references
            if item.kind is ReferenceKind.REPLAY_PARENT
        )
        if len(parent_references) != 1:
            raise ValueError("child execution 必須恰有一個 REPLAY_PARENT reference")

        encoded_execution = encode_execution(execution)
        envelope = decode_execution_envelope(encoded_execution)
        if envelope.execution != execution:
            raise ReplayLineageCodecError("canonical child execution readback 不一致")
        if receipt is not None:
            if type(receipt) is not SaveReceipt:
                raise TypeError("receipt 必須是 SaveReceipt 或 None")
            if receipt.result_id != execution.result_id:
                raise ValueError("SaveReceipt.result_id 與 child execution 不一致")
            if receipt.payload_hash != envelope.payload_hash:
                raise ValueError("SaveReceipt.payload_hash 與 canonical execution 不一致")
            if (
                receipt.schema_version != envelope.schema_version
                or receipt.schema_revision != envelope.schema_revision
            ):
                raise ValueError("SaveReceipt schema version/revision 與 execution 不一致")

        data_snapshot_refs = execution.context.data_snapshot_refs
        status = (
            ReplayDataSnapshotStatusV1.AVAILABLE
            if data_snapshot_refs
            else ReplayDataSnapshotStatusV1.UNAVAILABLE
        )
        return cls(
            snapshot_date=snapshot_date,
            result_id=execution.result_id,
            canonical_payload_sha256=envelope.payload_hash,
            replay_parent_ref=parent_references[0],
            data_snapshot_status=status,
            data_snapshot_refs=data_snapshot_refs,
        )

    def verify_execution_artifact(
        self,
        raw_payload: bytes,
        *,
        receipt: SaveReceipt | None = None,
    ) -> RecommendationExecution:
        """驗證實際讀回的 child artifact bytes、receipt 與 lineage facts。

        Sidecar 不內嵌 child payload；讀回端應載入 child artifact 的原始 bytes，
        再呼叫本方法確認其 canonical hash 與 parent/data references 一致。
        """

        if type(raw_payload) is not bytes:
            raise TypeError("raw_payload 必須是 bytes")
        try:
            envelope = decode_execution_envelope(raw_payload)
        except (ExecutionCodecError, TypeError, ValueError) as exc:
            raise ReplayLineageCodecError(
                "child execution artifact 無效或非 canonical"
            ) from exc

        execution = envelope.execution
        if envelope.payload_hash != self.canonical_payload_sha256:
            raise ReplayLineageCodecError(
                "child artifact payload hash 與 sidecar 不一致"
            )
        if execution.result_id != self.result_id:
            raise ReplayLineageCodecError(
                "child artifact result_id 與 sidecar 不一致"
            )
        if execution.status is not ExecutionStatus.COMPLETED:
            raise ReplayLineageCodecError(
                "sidecar child 必須對應 completed execution"
            )
        if execution.context.as_of_date != self.snapshot_date:
            raise ReplayLineageCodecError(
                "child artifact snapshot_date 與 sidecar 不一致"
            )
        parent_references = tuple(
            item
            for item in execution.related_references
            if item.kind is ReferenceKind.REPLAY_PARENT
        )
        if parent_references != (self.replay_parent_ref,):
            raise ReplayLineageCodecError(
                "child artifact REPLAY_PARENT reference 與 sidecar 不一致"
            )
        if execution.context.data_snapshot_refs != self.data_snapshot_refs:
            raise ReplayLineageCodecError(
                "child artifact data snapshot references 與 sidecar 不一致"
            )
        if receipt is not None:
            if type(receipt) is not SaveReceipt:
                raise TypeError("receipt 必須是 SaveReceipt 或 None")
            if receipt.result_id != execution.result_id:
                raise ReplayLineageCodecError(
                    "SaveReceipt.result_id 與 child artifact 不一致"
                )
            if receipt.payload_hash != envelope.payload_hash:
                raise ReplayLineageCodecError(
                    "SaveReceipt.payload_hash 與 child artifact 不一致"
                )
            if (
                receipt.schema_version != envelope.schema_version
                or receipt.schema_revision != envelope.schema_revision
            ):
                raise ReplayLineageCodecError(
                    "SaveReceipt schema version/revision 與 child artifact 不一致"
                )
        return execution


@dataclass(frozen=True, slots=True)
class ReplayLineageSidecarV1:
    """portfolio replay 的 parent identity 與日期排序 child lineage。"""

    parent_result_id: str
    children: tuple[ReplayLineageChildV1, ...] = ()
    schema_version: ClassVar[str] = REPLAY_LINEAGE_SCHEMA_VERSION
    schema_revision: ClassVar[int] = REPLAY_LINEAGE_SCHEMA_REVISION

    def __post_init__(self) -> None:
        _require_nonblank(self.parent_result_id, "parent_result_id")
        if type(self.children) not in (tuple, list):
            raise TypeError("children 必須是 ReplayLineageChildV1 tuple 或 list")
        raw_children = cast(tuple[object, ...] | list[object], self.children)
        if any(type(item) is not ReplayLineageChildV1 for item in raw_children):
            raise TypeError("children 必須只包含 ReplayLineageChildV1")
        children = cast(
            tuple[ReplayLineageChildV1, ...],
            tuple(
                sorted(
                    raw_children,
                    key=lambda item: (
                        cast(ReplayLineageChildV1, item).snapshot_date,
                        cast(ReplayLineageChildV1, item).result_id,
                    ),
                )
            ),
        )
        result_ids = tuple(item.result_id for item in children)
        if len(result_ids) != len(set(result_ids)):
            raise ValueError("child result_id 不可重複")
        snapshot_dates = tuple(item.snapshot_date for item in children)
        if len(snapshot_dates) != len(set(snapshot_dates)):
            raise ValueError("每個 snapshot_date 只可有一個 child")
        if self.parent_result_id in result_ids:
            raise ValueError("parent_result_id 不可與 child result_id 相同")
        if any(
            item.replay_parent_ref.reference_id != self.parent_result_id
            for item in children
        ):
            raise ValueError("child REPLAY_PARENT reference 必須符合 parent_result_id")
        object.__setattr__(self, "children", children)


@dataclass(frozen=True, slots=True)
class ReplayLineageReadEnvelope:
    """保留解碼後 sidecar、payload hash 與原始 canonical bytes。"""

    sidecar: ReplayLineageSidecarV1
    schema_version: str
    schema_revision: int
    payload_hash: str
    raw_payload_sha256: str
    raw_payload: bytes


def _canonical_json_bytes(value: object) -> bytes:
    try:
        text = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        return text.encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise ReplayLineageCodecError("sidecar 無法轉為 canonical JSON") from exc


def _reference_to_payload(reference: VersionReference) -> dict[str, object]:
    return {
        "kind": reference.kind.value,
        "reference_id": reference.reference_id,
        "version": reference.version,
    }


def _sidecar_payload(sidecar: ReplayLineageSidecarV1) -> dict[str, object]:
    return {
        "parent_result_id": sidecar.parent_result_id,
        "children": [
            {
                "snapshot_date": child.snapshot_date.isoformat(),
                "result_id": child.result_id,
                "canonical_payload_sha256": child.canonical_payload_sha256,
                "replay_parent_ref": _reference_to_payload(child.replay_parent_ref),
                "data_snapshot_status": child.data_snapshot_status.value,
                "data_snapshot_refs": [
                    _reference_to_payload(reference)
                    for reference in child.data_snapshot_refs
                ],
            }
            for child in sidecar.children
        ],
    }


def _header(sidecar: ReplayLineageSidecarV1) -> dict[str, object]:
    return {
        "schema_version": REPLAY_LINEAGE_SCHEMA_VERSION,
        "schema_revision": REPLAY_LINEAGE_SCHEMA_REVISION,
        "payload": _sidecar_payload(sidecar),
    }


def encode_replay_lineage(sidecar: ReplayLineageSidecarV1) -> bytes:
    """編碼 sidecar 為 deterministic UTF-8 JSON envelope。"""

    if type(sidecar) is not ReplayLineageSidecarV1:
        raise TypeError("sidecar 必須是 ReplayLineageSidecarV1")
    header = _header(sidecar)
    payload_hash = "sha256:" + sha256(_canonical_json_bytes(header)).hexdigest()
    document = dict(header)
    document["payload_hash"] = payload_hash
    return _canonical_json_bytes(document)


def _strict_json_load(raw_payload: bytes) -> object:
    if type(raw_payload) is not bytes:
        raise TypeError("sidecar payload 必須是 bytes")

    def reject_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ReplayLineageCodecError(f"JSON object 含重複 key: {key}")
            result[key] = value
        return result

    def reject_constant(value: str) -> object:
        raise ReplayLineageCodecError(f"JSON 不允許非有限數值: {value}")

    try:
        return json.loads(
            raw_payload.decode("utf-8"),
            object_pairs_hook=reject_duplicates,
            parse_constant=reject_constant,
        )
    except ReplayLineageCodecError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReplayLineageCodecError("sidecar 不是有效 UTF-8 JSON") from exc


def _require_object_keys(
    value: object,
    *,
    expected: set[str],
    field_name: str,
) -> dict[str, object]:
    if type(value) is not dict:
        raise ReplayLineageCodecError(f"{field_name} 必須是 JSON object")
    mapping = cast(dict[str, object], value)
    if set(mapping) != expected:
        raise ReplayLineageCodecError(f"{field_name} 欄位不完整或含未知欄位")
    return mapping


def _decode_reference(value: object, *, field_name: str) -> VersionReference:
    mapping = _require_object_keys(
        value,
        expected={"kind", "reference_id", "version"},
        field_name=field_name,
    )
    kind_value = mapping["kind"]
    if type(kind_value) is not str or kind_value not in _REFERENCE_KINDS:
        raise ReplayLineageCodecError(f"{field_name}.kind 不支援")
    reference_id = mapping["reference_id"]
    version = mapping["version"]
    if type(reference_id) is not str:
        raise ReplayLineageCodecError(f"{field_name}.reference_id 必須是 str")
    if version is not None and type(version) is not str:
        raise ReplayLineageCodecError(f"{field_name}.version 必須是 str 或 None")
    try:
        return VersionReference(
            kind=_REFERENCE_KINDS[kind_value],
            reference_id=reference_id,
            version=version,
        )
    except (TypeError, ValueError) as exc:
        raise ReplayLineageCodecError(f"{field_name} 無效") from exc


def _decode_payload(value: object) -> ReplayLineageSidecarV1:
    mapping = _require_object_keys(
        value,
        expected={"parent_result_id", "children"},
        field_name="payload",
    )
    parent_result_id = mapping["parent_result_id"]
    raw_children = mapping["children"]
    if type(parent_result_id) is not str:
        raise ReplayLineageCodecError("parent_result_id 必須是 str")
    if type(raw_children) is not list:
        raise ReplayLineageCodecError("children 必須是 JSON array")

    children: list[ReplayLineageChildV1] = []
    child_keys = {
        "snapshot_date",
        "result_id",
        "canonical_payload_sha256",
        "replay_parent_ref",
        "data_snapshot_status",
        "data_snapshot_refs",
    }
    for index, raw_child in enumerate(raw_children):
        field_name = f"children[{index}]"
        child = _require_object_keys(
            raw_child,
            expected=child_keys,
            field_name=field_name,
        )
        date_text = child["snapshot_date"]
        result_id = child["result_id"]
        payload_hash = child["canonical_payload_sha256"]
        status_text = child["data_snapshot_status"]
        raw_data_refs = child["data_snapshot_refs"]
        if type(date_text) is not str:
            raise ReplayLineageCodecError(f"{field_name}.snapshot_date 必須是 str")
        try:
            snapshot_date = date.fromisoformat(date_text)
        except ValueError as exc:
            raise ReplayLineageCodecError(f"{field_name}.snapshot_date 無效") from exc
        if snapshot_date.isoformat() != date_text:
            raise ReplayLineageCodecError(
                f"{field_name}.snapshot_date 必須使用 YYYY-MM-DD"
            )
        if type(result_id) is not str or type(payload_hash) is not str:
            raise ReplayLineageCodecError(f"{field_name} 的 ID/hash 型別錯誤")
        if type(status_text) is not str:
            raise ReplayLineageCodecError(
                f"{field_name}.data_snapshot_status 必須是 str"
            )
        try:
            status = ReplayDataSnapshotStatusV1(status_text)
        except ValueError as exc:
            raise ReplayLineageCodecError(
                f"{field_name}.data_snapshot_status 不支援"
            ) from exc
        if type(raw_data_refs) is not list:
            raise ReplayLineageCodecError(
                f"{field_name}.data_snapshot_refs 必須是 JSON array"
            )
        replay_parent_ref = _decode_reference(
            child["replay_parent_ref"],
            field_name=f"{field_name}.replay_parent_ref",
        )
        data_snapshot_refs = tuple(
            _decode_reference(item, field_name=f"{field_name}.data_snapshot_refs")
            for item in raw_data_refs
        )
        try:
            children.append(
                ReplayLineageChildV1(
                    snapshot_date=snapshot_date,
                    result_id=result_id,
                    canonical_payload_sha256=payload_hash,
                    replay_parent_ref=replay_parent_ref,
                    data_snapshot_status=status,
                    data_snapshot_refs=data_snapshot_refs,
                )
            )
        except (TypeError, ValueError) as exc:
            raise ReplayLineageCodecError(f"{field_name} contract 無效") from exc

    try:
        return ReplayLineageSidecarV1(
            parent_result_id=parent_result_id,
            children=tuple(children),
        )
    except (TypeError, ValueError) as exc:
        raise ReplayLineageCodecError(
            f"replay lineage payload contract 無效: {exc}"
        ) from exc


def decode_replay_lineage_envelope(raw_payload: bytes) -> ReplayLineageReadEnvelope:
    """嚴格驗證 sidecar schema、canonical bytes 與內容雜湊。"""

    document = _strict_json_load(raw_payload)
    mapping = _require_object_keys(
        document,
        expected={"schema_version", "schema_revision", "payload", "payload_hash"},
        field_name="sidecar envelope",
    )
    schema_version = mapping["schema_version"]
    schema_revision = mapping["schema_revision"]
    payload_hash = mapping["payload_hash"]
    if type(schema_version) is not str or type(schema_revision) is not int:
        raise ReplayLineageCodecError("schema header 型別錯誤")
    try:
        _require_sha256(payload_hash, "payload_hash")
    except ValueError as exc:
        raise ReplayLineageCodecError(str(exc)) from exc
    header = {
        "schema_version": schema_version,
        "schema_revision": schema_revision,
        "payload": mapping["payload"],
    }
    actual_hash = "sha256:" + sha256(_canonical_json_bytes(header)).hexdigest()
    if actual_hash != payload_hash:
        raise ReplayLineageCodecError("sidecar payload hash 不符")
    if schema_version != REPLAY_LINEAGE_SCHEMA_VERSION:
        raise ReplayLineageCodecError(f"不支援 schema_version: {schema_version!r}")
    if schema_revision != REPLAY_LINEAGE_SCHEMA_REVISION:
        raise ReplayLineageCodecError(f"不支援 schema_revision: {schema_revision!r}")

    sidecar = _decode_payload(mapping["payload"])
    if encode_replay_lineage(sidecar) != raw_payload:
        raise ReplayLineageCodecError("sidecar bytes 不是 canonical UTF-8 JSON")
    return ReplayLineageReadEnvelope(
        sidecar=sidecar,
        schema_version=schema_version,
        schema_revision=schema_revision,
        payload_hash=cast(str, payload_hash),
        raw_payload_sha256="sha256:" + sha256(raw_payload).hexdigest(),
        raw_payload=raw_payload,
    )


def decode_replay_lineage(raw_payload: bytes) -> ReplayLineageSidecarV1:
    """解碼 sidecar；需要原始 bytes/hash 時請使用 envelope API。"""

    return decode_replay_lineage_envelope(raw_payload).sidecar


__all__ = (
    "REPLAY_LINEAGE_SCHEMA_REVISION",
    "REPLAY_LINEAGE_SCHEMA_VERSION",
    "ReplayDataSnapshotStatusV1",
    "ReplayLineageChildV1",
    "ReplayLineageCodecError",
    "ReplayLineageReadEnvelope",
    "ReplayLineageSidecarV1",
    "decode_replay_lineage",
    "decode_replay_lineage_envelope",
    "encode_replay_lineage",
)
