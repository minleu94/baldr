"""不可變且純資料的推薦 ML 準備契約。

本模組只描述已解析的執行、來源、特徵與模型身分；不讀取來源、不載入模型，
也不推導缺失的版本、可得時間或權限狀態。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from enum import Enum
import re
from typing import ClassVar, TypeVar, cast
from zoneinfo import ZoneInfo


_T = TypeVar("_T")
_SHA256_PATTERN = re.compile(r"sha256:[0-9a-f]{64}\Z")


class SnapshotKind(str, Enum):
    """資料集版本或可驗證的有界快照。"""

    DATASET = "dataset"
    BOUNDED = "bounded"


class AvailabilityStatus(str, Enum):
    """來源可得時間的明示狀態；未知不得用缺值補成已知。"""

    KNOWN = "known"
    UNKNOWN = "unknown"


class SnapshotQualityStatus(str, Enum):
    """消費來源的品質／缺件狀態；未知不可推定為完整。"""

    COMPLETE = "complete"
    DEGRADED = "degraded"
    MISSING = "missing"
    UNKNOWN = "unknown"


class SnapshotScopeStatus(str, Enum):
    """來源時間語意；明示 PIT、current 或 research，不互相推定。"""

    PIT = "pit"
    CURRENT = "current"
    RESEARCH = "research"
    UNKNOWN = "unknown"


class QuarantineStatus(str, Enum):
    CLEAR = "clear"
    QUARANTINED = "quarantined"
    UNKNOWN = "unknown"


class PermissionStatus(str, Enum):
    GRANTED = "granted"
    DENIED = "denied"
    UNKNOWN = "unknown"


def _require_text(value: object, field_name: str) -> str:
    if type(value) is not str:
        raise TypeError(f"{field_name} 必須是 str")
    if not value.strip():
        raise ValueError(f"{field_name} 不可為空白")
    return cast(str, value)


def _require_sha256(value: object, field_name: str) -> str:
    text = _require_text(value, field_name)
    if _SHA256_PATTERN.fullmatch(text) is None:
        raise ValueError(f"{field_name} 必須是小寫 sha256:<64 hex>")
    return text


def _require_exact_date(value: object, field_name: str) -> date:
    if type(value) is not date:
        raise TypeError(f"{field_name} 必須是 date")
    return cast(date, value)


def _require_nonnegative_int(value: object, field_name: str) -> int:
    if type(value) is not int:
        raise TypeError(f"{field_name} 必須是 int")
    if value < 0:
        raise ValueError(f"{field_name} 不可為負數")
    return cast(int, value)


def _freeze_aware_datetime(value: object, field_name: str) -> datetime:
    """複製時區狀態，不保留呼叫者提供的可變 tzinfo/timedelta 子類別名。"""

    if type(value) is not datetime:
        raise TypeError(f"{field_name} 必須是 datetime")
    value = cast(datetime, value)
    tzinfo = value.tzinfo
    if tzinfo is None:
        raise ValueError(f"{field_name} 必須含時區")
    offset = value.utcoffset()
    if offset is None or not isinstance(offset, timedelta):
        raise ValueError(f"{field_name} 必須含有效時區")

    timezone_name = (
        tzinfo.tzname(value) if type(tzinfo) in (timezone, ZoneInfo) else None
    )
    if (
        type(tzinfo) in (timezone, ZoneInfo)
        and type(offset) is timedelta
        and type(timezone_name) is str
    ):
        return value

    if type(timezone_name) is str:
        frozen_name = str.__str__(timezone_name)
    else:
        frozen_name = None
    # 內建 descriptor 讀取 timedelta 的底層值，避免子類覆寫 days/seconds。
    fixed_offset = timedelta(
        days=cast(int, timedelta.days.__get__(offset)),
        seconds=cast(int, timedelta.seconds.__get__(offset)),
        microseconds=cast(int, timedelta.microseconds.__get__(offset)),
    )
    fixed_timezone = (
        timezone(fixed_offset)
        if frozen_name is None
        else timezone(fixed_offset, frozen_name)
    )
    return value.replace(tzinfo=fixed_timezone)


def _freeze_records(
    value: object, field_name: str, record_type: type[_T]
) -> tuple[_T, ...]:
    if type(value) not in (tuple, list):
        raise TypeError(f"{field_name} 必須是 tuple 或 list")
    records = tuple(cast(tuple[object, ...] | list[object], value))
    if any(type(record) is not record_type for record in records):
        raise TypeError(f"{field_name} 含有不支援的 record")
    return cast(tuple[_T, ...], records)


@dataclass(frozen=True, slots=True)
class CandidateIdentity:
    """單一候選的不透明識別與顯示／交易代碼，兩者不可互代。"""

    candidate_id: str
    symbol: str

    def __post_init__(self) -> None:
        _require_text(self.candidate_id, "candidate_id")
        _require_text(self.symbol, "symbol")


@dataclass(frozen=True, slots=True)
class DateRange:
    start_date: date
    end_date: date

    def __post_init__(self) -> None:
        start = _require_exact_date(self.start_date, "start_date")
        end = _require_exact_date(self.end_date, "end_date")
        if start > end:
            raise ValueError("row range start_date 不可晚於 end_date")


@dataclass(frozen=True, slots=True)
class MissingInput:
    """一項品質或缺件問題的明確識別與原因碼。"""

    item_id: str
    reason_code: str

    def __post_init__(self) -> None:
        _require_text(self.item_id, "item_id")
        _require_text(self.reason_code, "reason_code")


@dataclass(frozen=True, slots=True)
class AvailabilityBinding:
    """保留來源日期或 timestamp 精度；混合可得時間應拆成不同 snapshot。"""

    status: AvailabilityStatus
    available_at: datetime | None = None
    available_date: date | None = None

    def __post_init__(self) -> None:
        if type(self.status) is not AvailabilityStatus:
            raise TypeError("status 必須是 AvailabilityStatus")
        available_date = (
            None
            if self.available_date is None
            else _require_exact_date(self.available_date, "available_date")
        )
        if self.status is AvailabilityStatus.UNKNOWN:
            if self.available_at is not None or available_date is not None:
                raise ValueError(
                    "unknown availability 不得附帶 available_date 或 available_at"
                )
            return
        if self.available_at is None and available_date is None:
            raise ValueError("known availability 必須提供 available_date 或 available_at")
        frozen = (
            None
            if self.available_at is None
            else _freeze_aware_datetime(self.available_at, "available_at")
        )
        object.__setattr__(self, "available_at", frozen)
        object.__setattr__(self, "available_date", available_date)


@dataclass(frozen=True, slots=True)
class SnapshotReference:
    """不含資料矩陣的已消費來源／資料集快照識別。"""

    snapshot_id: str
    source_id: str
    kind: SnapshotKind
    dataset_id: str | None
    schema_version: str
    content_hash: str
    row_identity_hash: str
    row_count: int
    row_range: DateRange | None
    source_revision: str | None
    availability: AvailabilityBinding
    quality_status: SnapshotQualityStatus
    missing_inputs: tuple[MissingInput, ...]
    scope_status: SnapshotScopeStatus

    def __post_init__(self) -> None:
        _require_text(self.snapshot_id, "snapshot_id")
        _require_text(self.source_id, "source_id")
        if type(self.kind) is not SnapshotKind:
            raise TypeError("kind 必須是 SnapshotKind")
        if self.dataset_id is not None:
            _require_text(self.dataset_id, "dataset_id")
        if self.kind is SnapshotKind.DATASET and self.dataset_id is None:
            raise ValueError("dataset snapshot 必須提供實際 dataset_id")
        if self.kind is SnapshotKind.BOUNDED and self.dataset_id is not None:
            raise ValueError("bounded snapshot 不得編造 dataset_id")
        _require_text(self.schema_version, "schema_version")
        _require_sha256(self.content_hash, "content_hash")
        _require_sha256(self.row_identity_hash, "row_identity_hash")
        row_count = _require_nonnegative_int(self.row_count, "row_count")
        if self.row_range is not None and type(self.row_range) is not DateRange:
            raise TypeError("row_range 必須是 DateRange 或 None")
        if row_count == 0 and self.row_range is not None:
            raise ValueError("空 snapshot 不得宣稱 row_range")
        if row_count > 0 and self.row_range is None:
            raise ValueError("非空 snapshot 必須綁定 row_range")
        if self.source_revision is not None:
            _require_text(self.source_revision, "source_revision")
        if type(self.availability) is not AvailabilityBinding:
            raise TypeError("availability 必須是 AvailabilityBinding")
        if type(self.quality_status) is not SnapshotQualityStatus:
            raise TypeError("quality_status 必須是 SnapshotQualityStatus")
        missing_inputs = _freeze_records(
            self.missing_inputs, "missing_inputs", MissingInput
        )
        missing_ids = tuple(item.item_id for item in missing_inputs)
        if len(set(missing_ids)) != len(missing_ids):
            raise ValueError("missing_inputs 的 item_id 不可重複")
        if self.quality_status is SnapshotQualityStatus.COMPLETE and missing_inputs:
            raise ValueError("complete quality 不得列出 missing_inputs")
        if (
            self.quality_status
            in (SnapshotQualityStatus.DEGRADED, SnapshotQualityStatus.MISSING)
            and not missing_inputs
        ):
            raise ValueError("degraded/missing quality 必須列出 missing_inputs")
        if type(self.scope_status) is not SnapshotScopeStatus:
            raise TypeError("scope_status 必須是 SnapshotScopeStatus")
        object.__setattr__(self, "missing_inputs", missing_inputs)


@dataclass(frozen=True, slots=True)
class FeatureSchemaItem:
    feature_id: str
    dtype: str
    unit: str

    def __post_init__(self) -> None:
        _require_text(self.feature_id, "feature_id")
        _require_text(self.dtype, "dtype")
        _require_text(self.unit, "unit")


@dataclass(frozen=True, slots=True)
class FeatureContract:
    """既有有序 feature ABI 與已擬合 transform／missing policy 的識別。"""

    feature_schema: tuple[FeatureSchemaItem, ...]
    feature_registry_hash: str
    transform_contract_id: str
    transform_contract_version: str
    transform_contract_hash: str
    missing_value_policy: str
    mask_policy: str
    normalization_policy: str

    def __post_init__(self) -> None:
        schema = _freeze_records(
            self.feature_schema, "feature_schema", FeatureSchemaItem
        )
        if not schema:
            raise ValueError("feature_schema 不可為空")
        feature_ids = tuple(item.feature_id for item in schema)
        if len(set(feature_ids)) != len(feature_ids):
            raise ValueError("feature_schema 的 feature_id 不可重複")
        _require_sha256(self.feature_registry_hash, "feature_registry_hash")
        _require_text(self.transform_contract_id, "transform_contract_id")
        _require_text(self.transform_contract_version, "transform_contract_version")
        _require_sha256(self.transform_contract_hash, "transform_contract_hash")
        _require_text(self.missing_value_policy, "missing_value_policy")
        _require_text(self.mask_policy, "mask_policy")
        _require_text(self.normalization_policy, "normalization_policy")
        object.__setattr__(self, "feature_schema", schema)


@dataclass(frozen=True, slots=True)
class LibraryVersion:
    library: str
    version: str

    def __post_init__(self) -> None:
        _require_text(self.library, "library")
        _require_text(self.version, "version")


@dataclass(frozen=True, slots=True)
class ModelBinding:
    """固定模型、訓練資料、artifact ABI 與安全狀態；不含路徑或 active pointer。"""

    model_id: str
    release_id: str
    model_family: str
    training_dataset_id: str
    training_dataset_hash: str
    feature_registry_hash: str
    label_registry_hash: str
    transform_contract_hash: str
    artifact_hash: str
    manifest_hash: str
    qualified_class_path: str
    serialization_format: str
    library_versions: tuple[LibraryVersion, ...]
    quarantine_status: QuarantineStatus
    shadow_only: bool
    production_eligible: bool
    production_action_allowed: bool
    permission_status: PermissionStatus

    def __post_init__(self) -> None:
        for name in (
            "model_id",
            "release_id",
            "model_family",
            "training_dataset_id",
            "qualified_class_path",
            "serialization_format",
        ):
            _require_text(getattr(self, name), name)
        for name in (
            "training_dataset_hash",
            "feature_registry_hash",
            "label_registry_hash",
            "transform_contract_hash",
            "artifact_hash",
            "manifest_hash",
        ):
            _require_sha256(getattr(self, name), name)
        versions = _freeze_records(
            self.library_versions, "library_versions", LibraryVersion
        )
        if not versions:
            raise ValueError("library_versions 不可為空")
        library_names = tuple(item.library for item in versions)
        if len(set(library_names)) != len(library_names):
            raise ValueError("library_versions 的 library 不可重複")
        for name in ("shadow_only", "production_eligible", "production_action_allowed"):
            if type(getattr(self, name)) is not bool:
                raise TypeError(f"{name} 必須是 bool")
        if type(self.quarantine_status) is not QuarantineStatus:
            raise TypeError("quarantine_status 必須是 QuarantineStatus")
        if type(self.permission_status) is not PermissionStatus:
            raise TypeError("permission_status 必須是 PermissionStatus")
        if self.production_action_allowed and (
            self.quarantine_status is not QuarantineStatus.CLEAR
            or self.permission_status is not PermissionStatus.GRANTED
            or self.shadow_only
            or not self.production_eligible
        ):
            raise ValueError("production_action_allowed 與模型安全狀態衝突")
        object.__setattr__(self, "library_versions", versions)


@dataclass(frozen=True, slots=True)
class CostReceiptBinding:
    """可選的成本合約及其輸入 receipt 身分，不含成本估算或交易計算。"""

    scenario_id: str
    scenario_version: str
    scenario_hash: str
    receipt_id: str | None
    receipt_hash: str | None

    def __post_init__(self) -> None:
        _require_text(self.scenario_id, "scenario_id")
        _require_text(self.scenario_version, "scenario_version")
        _require_sha256(self.scenario_hash, "scenario_hash")
        if self.receipt_id is not None:
            _require_text(self.receipt_id, "receipt_id")
        if self.receipt_hash is not None:
            _require_sha256(self.receipt_hash, "receipt_hash")
        if (self.receipt_id is None) != (self.receipt_hash is None):
            raise ValueError("receipt_id 與 receipt_hash 必須同時提供或同時缺省")


@dataclass(frozen=True, slots=True)
class PreparedMLInput:
    """單次 projection 的精確輸入身分；不承載特徵矩陣或可變來源。"""

    result_id: str
    decision_date: date
    decision_at: datetime
    as_of_date: date
    feature_cutoff_date: date
    mode: str
    candidate_identities: tuple[CandidateIdentity, ...]
    rule_snapshot_refs: tuple[SnapshotReference, ...]
    ml_snapshot_refs: tuple[SnapshotReference, ...]
    feature_contract: FeatureContract
    model_binding: ModelBinding
    cost_receipt_binding: CostReceiptBinding | None = None

    contract_version: ClassVar[str] = "prepared-ml-input.v1"

    def __post_init__(self) -> None:
        # result_id 與 mode 保留呼叫端的 opaque 原值，不做正規化。
        _require_text(self.result_id, "result_id")
        decision_date_value = _require_exact_date(self.decision_date, "decision_date")
        as_of = _require_exact_date(self.as_of_date, "as_of_date")
        feature_cutoff = _require_exact_date(
            self.feature_cutoff_date, "feature_cutoff_date"
        )
        if as_of > decision_date_value:
            raise ValueError("as_of_date 不可晚於 decision_date")
        if feature_cutoff > as_of:
            raise ValueError("feature_cutoff_date 不可晚於 as_of_date")
        decision_at = _freeze_aware_datetime(self.decision_at, "decision_at")
        _require_text(self.mode, "mode")

        candidates = _freeze_records(
            self.candidate_identities, "candidate_identities", CandidateIdentity
        )
        if not candidates:
            raise ValueError("candidate_identities 不可為空")
        candidate_ids = tuple(item.candidate_id for item in candidates)
        symbols = tuple(item.symbol for item in candidates)
        if len(set(candidate_ids)) != len(candidate_ids):
            raise ValueError("candidate_identities 的 candidate_id 不可重複")
        if len(set(symbols)) != len(symbols):
            raise ValueError("candidate_identities 的 symbol 不可重複")

        rule_refs = _freeze_records(
            self.rule_snapshot_refs, "rule_snapshot_refs", SnapshotReference
        )
        ml_refs = _freeze_records(
            self.ml_snapshot_refs, "ml_snapshot_refs", SnapshotReference
        )
        if not rule_refs:
            raise ValueError("rule_snapshot_refs 不可為空")
        if not ml_refs:
            raise ValueError("ml_snapshot_refs 不可為空")
        for field_name, refs in (
            ("rule_snapshot_refs", rule_refs),
            ("ml_snapshot_refs", ml_refs),
        ):
            snapshot_ids = tuple(item.snapshot_id for item in refs)
            if len(set(snapshot_ids)) != len(snapshot_ids):
                raise ValueError(f"{field_name} 的 snapshot_id 不可重複")
            for reference in refs:
                if (
                    reference.row_range is not None
                    and reference.row_range.end_date > feature_cutoff
                ):
                    raise ValueError(
                        f"{field_name} 含超過共同 feature cutoff 的資料列"
                    )
                availability = reference.availability
                if (
                    availability.status is AvailabilityStatus.KNOWN
                    and availability.available_at is not None
                    and availability.available_at > decision_at
                ):
                    raise ValueError(
                        f"{field_name} 含晚於 decision_at 才可得的來源"
                    )
                if (
                    availability.status is AvailabilityStatus.KNOWN
                    and availability.available_date is not None
                    and availability.available_date > decision_date_value
                ):
                    raise ValueError(
                        f"{field_name} 含晚於 decision_date 才可得的來源"
                    )

        if type(self.feature_contract) is not FeatureContract:
            raise TypeError("feature_contract 必須是 FeatureContract")
        if type(self.model_binding) is not ModelBinding:
            raise TypeError("model_binding 必須是 ModelBinding")
        if (
            self.feature_contract.feature_registry_hash
            != self.model_binding.feature_registry_hash
        ):
            raise ValueError("model 與 input feature_registry_hash 不一致")
        if (
            self.feature_contract.transform_contract_hash
            != self.model_binding.transform_contract_hash
        ):
            raise ValueError("model 與 input transform_contract_hash 不一致")
        if self.cost_receipt_binding is not None and type(
            self.cost_receipt_binding
        ) is not CostReceiptBinding:
            raise TypeError("cost_receipt_binding 必須是 CostReceiptBinding 或 None")

        object.__setattr__(self, "decision_at", decision_at)
        object.__setattr__(self, "candidate_identities", candidates)
        object.__setattr__(self, "rule_snapshot_refs", rule_refs)
        object.__setattr__(self, "ml_snapshot_refs", ml_refs)


__all__ = (
    "AvailabilityBinding",
    "AvailabilityStatus",
    "CandidateIdentity",
    "CostReceiptBinding",
    "DateRange",
    "FeatureContract",
    "FeatureSchemaItem",
    "LibraryVersion",
    "MissingInput",
    "ModelBinding",
    "PermissionStatus",
    "PreparedMLInput",
    "QuarantineStatus",
    "SnapshotKind",
    "SnapshotQualityStatus",
    "SnapshotReference",
    "SnapshotScopeStatus",
)
