"""推薦執行的不可變 application contracts。"""

from __future__ import annotations

import json
import re
import sys
from hashlib import sha256
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, fields, is_dataclass, replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from types import MappingProxyType
from typing import ClassVar, TypeVar, cast
from zoneinfo import ZoneInfo

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


schema_version = "recommendation-execution.v1"
EXECUTION_SCHEMA_REVISION = 2
SUPPORTED_EXECUTION_SCHEMA_REVISIONS: tuple[int, ...] = (1, 2)
_SHA256_TEXT_PATTERN = re.compile(r"(?:sha256:)?[0-9a-f]{64}\Z")
_JSON_DOUBLE_MAX = Decimal.from_float(sys.float_info.max)
_T = TypeVar("_T")


def _freeze_value(value: object, field_path: str, active: set[int] | None = None) -> object:
    """依封存白名單遞迴複製並凍結值。"""

    if active is None:
        active = set()

    if value is None or type(value) in (str, int, bool):
        return value
    if type(value) is Decimal:
        if not value.is_finite():
            raise ValueError(f"{field_path} 的 Decimal 必須為有限值")
        return value
    if isinstance(value, Enum):
        if type(value) not in _ALLOWED_ENUM_TYPES:
            raise TypeError(f"{field_path} 不是明示允許的 enum")
        enum_value = value.value
        if type(enum_value) not in (str, int, bool, Decimal) or (
            type(enum_value) is Decimal and not enum_value.is_finite()
        ):
            raise TypeError(f"{field_path} 的 enum value 不在封存白名單")
        return value
    if type(value) is datetime:
        return _freeze_aware_datetime(value, field_path)
    if type(value) is date:
        return value

    if type(value) in (tuple, list):
        identity = id(value)
        if identity in active:
            raise TypeError(f"{field_path} 不接受循環參照")
        active.add(identity)
        try:
            sequence = cast(Sequence[object], value)
            return tuple(
                _freeze_value(item, f"{field_path}[{index}]", active)
                for index, item in enumerate(sequence)
            )
        finally:
            active.remove(identity)

    if isinstance(value, Mapping):
        identity = id(value)
        if identity in active:
            raise TypeError(f"{field_path} 不接受循環參照")
        active.add(identity)
        try:
            copied: dict[str, object] = {}
            for key, item in value.items():
                if type(key) is not str:
                    raise TypeError(f"{field_path} 的 mapping key 必須是 str")
                copied[key] = _freeze_value(item, f"{field_path}.{key}", active)
            return MappingProxyType(copied)
        finally:
            active.remove(identity)

    if is_dataclass(value) and not isinstance(value, type):
        if type(value) not in _ALLOWED_FROZEN_RECORD_TYPES:
            raise TypeError(f"{field_path} 不是明示允許的 frozen contract")
        parameters = getattr(type(value), "__dataclass_params__", None)
        if parameters is None or not parameters.frozen:
            raise TypeError(f"{field_path} 只接受 frozen dataclass")
        identity = id(value)
        if identity in active:
            raise TypeError(f"{field_path} 不接受循環參照")
        active.add(identity)
        try:
            changes: dict[str, object] = {}
            for item in fields(value):
                original = getattr(value, item.name)
                frozen = _freeze_value(original, f"{field_path}.{item.name}", active)
                if frozen is not original:
                    changes[item.name] = frozen
            if not changes:
                return value
            try:
                return replace(value, **changes)
            except (TypeError, ValueError) as exc:
                raise TypeError(f"{field_path} 無法重建 frozen dataclass") from exc
        finally:
            active.remove(identity)

    raise TypeError(f"{field_path} 型別 {type(value).__name__} 不在封存白名單")


def _require_nonblank(value: str, field_name: str) -> None:
    if type(value) is not str:
        raise TypeError(f"{field_name} 必須是 str")
    if not value.strip():
        raise ValueError(f"{field_name} 不可為空白")


def _require_optional_text(value: str | None, field_name: str) -> None:
    if value is not None and type(value) is not str:
        raise TypeError(f"{field_name} 僅接受 str 或 None")


def _require_optional_hash(value: str | None, field_name: str) -> None:
    _require_optional_text(value, field_name)
    if value is not None and _SHA256_TEXT_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{field_name} 必須是 SHA-256 digest")


def _canonical_json_sha256(value: object, field_name: str) -> str:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise ValueError(f"{field_name} 無法形成有限 canonical JSON") from exc
    return "sha256:" + sha256(encoded).hexdigest()


def _validate_json_object_snapshot(value: str, field_name: str) -> None:
    """驗證具名原始 JSON snapshot，但絕不重序列化或量化其內容。"""

    if type(value) is not str:
        raise TypeError(f"{field_name} 必須是原始 JSON str")

    def reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, item in pairs:
            if key in result:
                raise ValueError(f"{field_name} 不可有重複 JSON key")
            result[key] = item
        return result

    def reject_nonfinite(value: str) -> object:
        raise ValueError(f"{field_name} 不接受非有限 JSON 數值 {value}")

    try:
        decoded = json.loads(
            value,
            object_pairs_hook=reject_duplicate_keys,
            parse_float=Decimal,
            parse_constant=reject_nonfinite,
        )
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"{field_name} 必須是有效 JSON object") from exc
    if type(decoded) is not dict:
        raise ValueError(f"{field_name} 的 JSON root 必須是 object")

    def validate_decoded(item: object, path: str) -> None:
        if item is None or type(item) in (int, bool):
            return
        if type(item) is str:
            try:
                item.encode("utf-8", errors="strict")
            except UnicodeEncodeError as exc:
                raise ValueError(f"{path} 必須是可逆 UTF-8 字串") from exc
            return
        if type(item) is Decimal:
            if not item.is_finite():
                raise ValueError(f"{path} 不可包含非有限 Decimal")
            if abs(item) > _JSON_DOUBLE_MAX:
                raise ValueError(f"{path} 不可超出既有 JSON numeric 範圍")
            if item != 0 and float(item) == 0.0:
                raise ValueError(f"{path} 的 JSON numeric 值不可 underflow 為零")
            return
        if type(item) is list:
            for index, child in enumerate(item):
                validate_decoded(child, f"{path}[{index}]")
            return
        if type(item) is dict:
            for key, child in item.items():
                if type(key) is not str:
                    raise TypeError(f"{path} 的 JSON key 必須是內建 str")
                validate_decoded(key, f"{path}.<key>")
                validate_decoded(child, f"{path}.{key}")
            return
        raise TypeError(f"{path} 含有不支援的 JSON 值 {type(item).__name__}")

    validate_decoded(decoded, field_name)


def _require_nonnegative_int(value: int, field_name: str) -> None:
    if type(value) is not int:
        raise TypeError(f"{field_name} 必須是 int")
    if value < 0:
        raise ValueError(f"{field_name} 不可為負數")


def _require_positive_optional_int(value: int | None, field_name: str) -> None:
    if value is None:
        return
    if type(value) is not int:
        raise TypeError(f"{field_name} 僅接受 int 或 None")
    if value <= 0:
        raise ValueError(f"{field_name} 必須大於 0")


def _require_optional_json_object(value: str | None, field_name: str) -> None:
    if value is not None:
        _validate_json_object_snapshot(value, field_name)


def _load_validated_json_object_snapshot(
    value: str, field_name: str
) -> dict[str, object]:
    _validate_json_object_snapshot(value, field_name)
    decoded = json.loads(value)
    if type(decoded) is not dict:
        raise TypeError(f"{field_name} 必須是 JSON object")
    return cast(dict[str, object], decoded)


def _same_json_value(left: object, right: object) -> bool:
    """比較 JSON 值時保留數字型別與 bool/int 差異。"""

    if type(left) is not type(right):
        return False
    if type(left) is dict:
        left_dict = cast(dict[str, object], left)
        right_dict = cast(dict[str, object], right)
        return left_dict.keys() == right_dict.keys() and all(
            _same_json_value(left_dict[key], right_dict[key]) for key in left_dict
        )
    if type(left) is list:
        left_list = cast(list[object], left)
        right_list = cast(list[object], right)
        return len(left_list) == len(right_list) and all(
            _same_json_value(left_value, right_value)
            for left_value, right_value in zip(left_list, right_list)
        )
    return left == right


def _assert_result_config_overlap(
    config: Mapping[str, object],
    key: str,
    expected: object,
    context_field: str,
    *,
    require_present: bool = False,
) -> None:
    expected_is_blank = expected is None or (
        type(expected) is str and not expected.strip()
    )
    if key not in config:
        if require_present and not expected_is_blank:
            raise ValueError(f"result_config.{key} 必須保存 Context.{context_field}")
        return
    if require_present and expected_is_blank:
        raise ValueError(
            f"result_config.{key} 須省略或由 Context.{context_field} 保存非空值"
        )
    if expected_is_blank:
        return
    if not _same_json_value(config[key], expected):
        raise ValueError(f"result_config.{key} 必須符合 Context.{context_field}")


def _require_date(value: date | None, field_name: str) -> None:
    if value is not None and type(value) is not date:
        raise TypeError(f"{field_name} 必須是 date 或 None，不可用 datetime 代替")


def _freeze_aware_datetime(
    value: datetime | None, field_name: str
) -> datetime | None:
    """封存時間值，避免自訂可變 tzinfo 留下外部別名。"""

    if value is None:
        return None
    if type(value) is not datetime:
        raise TypeError(f"{field_name} 必須是 datetime 或 None")
    tzinfo = value.tzinfo
    if tzinfo is None:
        raise ValueError(f"{field_name} 必須含時區")
    offset = value.utcoffset()
    if offset is None:
        raise ValueError(f"{field_name} 必須含時區")

    timezone_name = (
        tzinfo.tzname(value)
        if type(tzinfo) in (timezone, ZoneInfo)
        else None
    )
    # 標準時區只在 offset 與 name 都是精確內建型別時保留。
    if (
        type(tzinfo) in (timezone, ZoneInfo)
        and type(offset) is timedelta
        and type(timezone_name) is str
    ):
        return value

    if isinstance(timezone_name, str):
        timezone_name = str.__str__(timezone_name)
    else:
        timezone_name = None
    # 用內建 descriptor 讀底層整數，避免子類覆寫 days 等屬性改變 offset。
    # timedelta 子類可帶外部可變狀態；只複製其整數分量，不保留子類別名。
    fixed_offset = timedelta(
        days=cast(int, getattr(timedelta, "days").__get__(offset)),
        seconds=cast(int, getattr(timedelta, "seconds").__get__(offset)),
        microseconds=cast(
            int, getattr(timedelta, "microseconds").__get__(offset)
        ),
    )
    # 對其他 tzinfo 只保存封存當刻的內建 offset，避免保留可變物件。
    fixed_timezone = (
        timezone(fixed_offset)
        if timezone_name is None
        else timezone(fixed_offset, timezone_name)
    )
    return value.replace(tzinfo=fixed_timezone)


def _freeze_tuple(value: object, field_name: str, item_type: type[_T]) -> tuple[_T, ...]:
    frozen = _freeze_value(value, field_name)
    if not isinstance(frozen, tuple):
        raise TypeError(f"{field_name} 必須是 tuple 或 list")
    items = cast(tuple[object, ...], frozen)
    if any(type(item) is not item_type for item in items):
        raise TypeError(f"{field_name} 含有不支援的 record")
    return cast(tuple[_T, ...], frozen)


class ReferenceKind(str, Enum):
    CONFIG = "config"
    PROFILE = "profile"
    STRATEGY = "strategy"
    POLICY = "policy"
    UNIVERSE_POLICY = "universe_policy"
    UNIVERSE_SNAPSHOT = "universe_snapshot"
    DATA_SNAPSHOT = "data_snapshot"
    ALGORITHM = "algorithm"
    RUNTIME_RUN = "runtime_run"
    REPLAY_PARENT = "replay_parent"
    PORTFOLIO_RESULT = "portfolio_result"
    EVIDENCE = "evidence"
    ML_PROJECTION = "ml_projection"
    ML_RECEIPT = "ml_receipt"


@dataclass(frozen=True, slots=True)
class VersionReference:
    """保留命名空間的 typed reference，不混用不同領域 ID。"""

    kind: ReferenceKind
    reference_id: str
    version: str | None = None

    def __post_init__(self) -> None:
        if type(self.kind) is not ReferenceKind:
            raise TypeError("kind 必須是 ReferenceKind")
        _require_nonblank(self.reference_id, "reference_id")
        if self.version is not None:
            _require_nonblank(self.version, "version")


class ExecutionStatus(str, Enum):
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class QualityStatus(str, Enum):
    COMPLETE = "complete"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class QualityReport:
    """品質維度及警告；與 execution terminal status 分開保存。"""

    status: QualityStatus = QualityStatus.UNKNOWN
    warnings: tuple[str, ...] = ()
    metrics: Mapping[str, object] | None = None

    def __post_init__(self) -> None:
        if type(self.status) is not QualityStatus:
            raise TypeError("status 必須是 QualityStatus")
        warnings = _freeze_tuple(self.warnings, "warnings", str)
        metrics = _freeze_value({} if self.metrics is None else self.metrics, "metrics")
        if not isinstance(metrics, Mapping):
            raise TypeError("metrics 必須是 mapping")
        object.__setattr__(self, "warnings", warnings)
        object.__setattr__(self, "metrics", metrics)


@dataclass(frozen=True, slots=True)
class ExecutionEvent:
    """單次 invocation 的明示診斷事件。"""

    event_type: str
    message: str
    occurred_at: datetime | None = None
    details: Mapping[str, object] | None = None

    def __post_init__(self) -> None:
        _require_nonblank(self.event_type, "event_type")
        if type(self.message) is not str:
            raise TypeError("message 必須是 str")
        occurred_at = _freeze_aware_datetime(self.occurred_at, "occurred_at")
        details = _freeze_value({} if self.details is None else self.details, "details")
        if not isinstance(details, Mapping):
            raise TypeError("details 必須是 mapping")
        object.__setattr__(self, "occurred_at", occurred_at)
        object.__setattr__(self, "details", details)


@dataclass(frozen=True, slots=True)
class RecommendationConfigSnapshot:
    """原始 caller config 文件快照；不承載 execution 業務結果。"""

    raw_config_json: str
    raw_json_sha256: str
    schema_version: str = "recommendation-config-snapshot.v1"

    def __post_init__(self) -> None:
        _validate_json_object_snapshot(self.raw_config_json, "raw_config_json")
        if type(self.raw_json_sha256) is not str:
            raise TypeError("raw_json_sha256 必須是 str")
        if not self.raw_json_sha256.startswith("sha256:") or _SHA256_TEXT_PATTERN.fullmatch(
            self.raw_json_sha256
        ) is None:
            raise ValueError("raw_json_sha256 必須是帶 sha256: 前綴的 SHA-256 digest")
        try:
            actual_hash = "sha256:" + sha256(
                self.raw_config_json.encode("utf-8", errors="strict")
            ).hexdigest()
        except UnicodeEncodeError as exc:
            raise ValueError("raw_config_json 必須可用 UTF-8 精確編碼") from exc
        if self.raw_json_sha256 != actual_hash:
            raise ValueError("raw_json_sha256 必須符合原始 JSON UTF-8 bytes")
        if type(self.schema_version) is not str:
            raise TypeError("schema_version 必須是 str")
        if self.schema_version != "recommendation-config-snapshot.v1":
            raise ValueError("schema_version 僅接受 recommendation-config-snapshot.v1")


@dataclass(frozen=True, slots=True)
class RecommendationResultConfigSnapshot:
    """完整 post-run result config 的來源快照與 producer canonical hash。"""

    raw_result_config_json: str
    config_sha256: str
    schema_version: str = "recommendation-result-config-snapshot.v1"

    def __post_init__(self) -> None:
        config = _load_validated_json_object_snapshot(
            self.raw_result_config_json, "raw_result_config_json"
        )
        _validate_sha256_hash(self.config_sha256, "config_sha256")
        if self.config_sha256 != _canonical_json_sha256(
            config, "raw_result_config_json"
        ):
            raise ValueError(
                "config_sha256 必須符合完整 post-run result config canonical JSON"
            )
        if type(self.schema_version) is not str:
            raise TypeError("schema_version 必須是 str")
        if self.schema_version != "recommendation-result-config-snapshot.v1":
            raise ValueError(
                "schema_version 僅接受 recommendation-result-config-snapshot.v1"
            )


@dataclass(frozen=True, slots=True)
class StrategyConfigIdentity:
    """同次 run 的策略設定身份；spec 保留原始 typed identity payload。"""

    strategy_version_id: str | None = None
    strategy_config_id: str | None = None
    strategy_config_hash: str | None = None
    strategy_config_schema: str | None = None
    strategy_config_spec_json: str | None = None

    def __post_init__(self) -> None:
        for name in (
            "strategy_version_id",
            "strategy_config_id",
            "strategy_config_schema",
        ):
            _require_optional_text(getattr(self, name), name)
        _require_optional_hash(self.strategy_config_hash, "strategy_config_hash")
        _require_optional_json_object(
            self.strategy_config_spec_json, "strategy_config_spec_json"
        )
        if all(
            getattr(self, name) is None
            for name in (
                "strategy_version_id",
                "strategy_config_id",
                "strategy_config_hash",
                "strategy_config_schema",
                "strategy_config_spec_json",
            )
        ):
            raise ValueError("StrategyConfigIdentity 不可全為 None")
        required_identity_fields = (
            "strategy_config_id",
            "strategy_config_hash",
            "strategy_config_schema",
            "strategy_config_spec_json",
        )
        if any(getattr(self, name) is None for name in required_identity_fields):
            raise ValueError("StrategyConfigIdentity 必須保存完整 id/hash/schema/spec")
        if self.strategy_config_id is not None and self.strategy_config_hash is not None:
            digest = self.strategy_config_hash.removeprefix("sha256:")
            expected_id = f"recommendation-strategy-config-v1:{digest}"
            if self.strategy_config_id != expected_id:
                raise ValueError("strategy_config_id 必須與 strategy_config_hash 相符")
        spec = _load_validated_json_object_snapshot(
            cast(str, self.strategy_config_spec_json), "strategy_config_spec_json"
        )
        if set(spec) != {"schema", "max_stocks", "top_n", "config"}:
            raise ValueError("strategy_config_spec_json 必須符合 strategy-config v1 欄位")
        if spec["schema"] != self.strategy_config_schema:
            raise ValueError("strategy_config_spec schema 必須符合 strategy_config_schema")
        for name in ("max_stocks", "top_n"):
            if type(spec[name]) is not int:
                raise TypeError(f"strategy_config_spec.{name} 必須是 int")
            _require_positive_optional_int(cast(int, spec[name]), f"strategy_config_spec.{name}")
        if type(spec["config"]) is not dict:
            raise TypeError("strategy_config_spec.config 必須是 JSON object")
        if self.strategy_config_hash != _canonical_json_sha256(
            spec, "strategy_config_spec_json"
        ):
            raise ValueError("strategy_config_hash 必須符合已保存的完整 strategy spec")


@dataclass(frozen=True, slots=True)
class UniversePolicyIdentity:
    """跨日穩定 universe policy 的具名身份與完整 spec。"""

    universe_policy_id: str | None = None
    universe_policy_hash: str | None = None
    universe_policy_schema: str | None = None
    universe_policy_spec_json: str | None = None

    def __post_init__(self) -> None:
        _require_optional_text(self.universe_policy_id, "universe_policy_id")
        _require_optional_hash(self.universe_policy_hash, "universe_policy_hash")
        _require_optional_text(self.universe_policy_schema, "universe_policy_schema")
        _require_optional_json_object(
            self.universe_policy_spec_json, "universe_policy_spec_json"
        )
        if all(
            value is None
            for value in (
                self.universe_policy_id,
                self.universe_policy_hash,
                self.universe_policy_schema,
                self.universe_policy_spec_json,
            )
        ):
            raise ValueError("UniversePolicyIdentity 不可全為 None")
        required_identity_fields = (
            "universe_policy_id",
            "universe_policy_hash",
            "universe_policy_schema",
            "universe_policy_spec_json",
        )
        if any(getattr(self, name) is None for name in required_identity_fields):
            raise ValueError("UniversePolicyIdentity 必須保存完整 id/hash/schema/spec")
        if self.universe_policy_id is not None and self.universe_policy_hash is not None:
            digest = self.universe_policy_hash.removeprefix("sha256:")
            expected_id = f"recommendation-universe-policy-v1:{digest}"
            if self.universe_policy_id != expected_id:
                raise ValueError("universe_policy_id 必須與 universe_policy_hash 相符")
        spec = _load_validated_json_object_snapshot(
            cast(str, self.universe_policy_spec_json), "universe_policy_spec_json"
        )
        required_spec_fields = {
            "schema",
            "selection_algorithm",
            "selection_mode",
            "industry_filter",
            "max_stocks",
            "source_provider_id",
        }
        if set(spec) not in (required_spec_fields, required_spec_fields | {"requested_codes"}):
            raise ValueError("universe_policy_spec_json 必須符合 universe-policy v1 欄位")
        if spec["schema"] != self.universe_policy_schema:
            raise ValueError("universe_policy_spec schema 必須符合 universe_policy_schema")
        for name in ("selection_algorithm", "selection_mode", "industry_filter", "source_provider_id"):
            if type(spec[name]) is not str:
                raise TypeError(f"universe_policy_spec.{name} 必須是 str")
        if type(spec["max_stocks"]) is not int:
            raise TypeError("universe_policy_spec.max_stocks 必須是 int")
        _require_positive_optional_int(cast(int, spec["max_stocks"]), "universe_policy_spec.max_stocks")
        if "requested_codes" in spec and (
            type(spec["requested_codes"]) is not list
            or any(type(code) is not str for code in cast(list[object], spec["requested_codes"]))
        ):
            raise TypeError("universe_policy_spec.requested_codes 必須是 str list")
        if "requested_codes" in spec and spec["requested_codes"] != sorted(
            set(cast(list[str], spec["requested_codes"]))
        ):
            raise ValueError("universe_policy_spec.requested_codes 必須唯一且排序")
        if self.universe_policy_hash != _canonical_json_sha256(
            spec, "universe_policy_spec_json"
        ):
            raise ValueError("universe_policy_hash 必須符合已保存的完整 policy spec")


@dataclass(frozen=True, slots=True)
class UniverseSnapshotIdentity:
    """決策當下 universe 成分快照的具名身份與完整 spec。"""

    universe_snapshot_id: str | None = None
    universe_snapshot_hash: str | None = None
    universe_snapshot_schema: str | None = None
    universe_snapshot_source_provider_id: str | None = None
    universe_snapshot_selected_codes_hash: str | None = None
    universe_snapshot_spec_json: str | None = None

    def __post_init__(self) -> None:
        for name in (
            "universe_snapshot_id",
            "universe_snapshot_schema",
            "universe_snapshot_source_provider_id",
        ):
            _require_optional_text(getattr(self, name), name)
        _require_optional_hash(self.universe_snapshot_hash, "universe_snapshot_hash")
        _require_optional_hash(
            self.universe_snapshot_selected_codes_hash,
            "universe_snapshot_selected_codes_hash",
        )
        _require_optional_json_object(
            self.universe_snapshot_spec_json, "universe_snapshot_spec_json"
        )
        if all(
            getattr(self, name) is None
            for name in (
                "universe_snapshot_id",
                "universe_snapshot_hash",
                "universe_snapshot_schema",
                "universe_snapshot_source_provider_id",
                "universe_snapshot_selected_codes_hash",
                "universe_snapshot_spec_json",
            )
        ):
            raise ValueError("UniverseSnapshotIdentity 不可全為 None")
        required_identity_fields = (
            "universe_snapshot_id",
            "universe_snapshot_hash",
            "universe_snapshot_schema",
            "universe_snapshot_source_provider_id",
            "universe_snapshot_selected_codes_hash",
            "universe_snapshot_spec_json",
        )
        if any(getattr(self, name) is None for name in required_identity_fields):
            raise ValueError("UniverseSnapshotIdentity 必須保存完整 id/hash/schema/provider/selected hash/spec")
        if self.universe_snapshot_id is not None and self.universe_snapshot_hash is not None:
            digest = self.universe_snapshot_hash.removeprefix("sha256:")
            expected_id = f"recommendation-universe-snapshot-v1:{digest}"
            if self.universe_snapshot_id != expected_id:
                raise ValueError("universe_snapshot_id 必須與 universe_snapshot_hash 相符")
        spec = _load_validated_json_object_snapshot(
            cast(str, self.universe_snapshot_spec_json), "universe_snapshot_spec_json"
        )
        expected_spec_fields = {
            "schema",
            "universe_policy_id",
            "source_provider_id",
            "decision_date",
            "selection_mode",
            "selected_codes",
            "selected_count",
            "selected_codes_hash",
            "requested_codes",
        }
        if set(spec) != expected_spec_fields:
            raise ValueError("universe_snapshot_spec_json 必須符合 universe-snapshot v1 欄位")
        if spec["schema"] != self.universe_snapshot_schema:
            raise ValueError("universe_snapshot_spec schema 必須符合 universe_snapshot_schema")
        if spec["source_provider_id"] != self.universe_snapshot_source_provider_id:
            raise ValueError("universe_snapshot_spec provider 必須符合 identity 欄位")
        if spec["selected_codes_hash"] != self.universe_snapshot_selected_codes_hash:
            raise ValueError("universe_snapshot_spec selected hash 必須符合 identity 欄位")
        for name in ("universe_policy_id", "source_provider_id", "decision_date", "selection_mode"):
            if type(spec[name]) is not str:
                raise TypeError(f"universe_snapshot_spec.{name} 必須是 str")
        selected_codes = spec["selected_codes"]
        if type(selected_codes) is not list or any(type(code) is not str for code in selected_codes):
            raise TypeError("universe_snapshot_spec.selected_codes 必須是 str list")
        if selected_codes != sorted(set(selected_codes)):
            raise ValueError("universe_snapshot_spec.selected_codes 必須唯一且排序")
        if type(spec["selected_count"]) is not int or spec["selected_count"] != len(selected_codes):
            raise ValueError("universe_snapshot_spec.selected_count 必須符合 selected_codes")
        requested_codes = spec["requested_codes"]
        if requested_codes is not None and (
            type(requested_codes) is not list
            or any(type(code) is not str for code in cast(list[object], requested_codes))
            or requested_codes != sorted(set(cast(list[str], requested_codes)))
        ):
            raise ValueError("universe_snapshot_spec.requested_codes 必須是 None 或唯一排序 str list")
        if self.universe_snapshot_selected_codes_hash != _canonical_json_sha256(
            {"selected_codes": selected_codes}, "universe_snapshot_selected_codes_hash"
        ):
            raise ValueError("universe_snapshot_selected_codes_hash 必須符合 selected_codes")
        if self.universe_snapshot_hash != _canonical_json_sha256(
            spec, "universe_snapshot_spec_json"
        ):
            raise ValueError("universe_snapshot_hash 必須符合已保存的完整 snapshot spec")


@dataclass(frozen=True, slots=True)
class RecommendationUniverseIdentity:
    """舊 caller alias、穩定政策與當日快照的單次身份集合。"""

    universe_id: str | None = None
    universe_hash: str | None = None
    universe_identity_schema: str | None = None
    policy: UniversePolicyIdentity | None = None
    snapshot: UniverseSnapshotIdentity | None = None

    def __post_init__(self) -> None:
        for name in ("universe_id", "universe_identity_schema"):
            _require_optional_text(getattr(self, name), name)
        _require_optional_hash(self.universe_hash, "universe_hash")
        if self.policy is not None and type(self.policy) is not UniversePolicyIdentity:
            raise TypeError("policy 必須是 UniversePolicyIdentity 或 None")
        if self.snapshot is not None and type(self.snapshot) is not UniverseSnapshotIdentity:
            raise TypeError("snapshot 必須是 UniverseSnapshotIdentity 或 None")
        if all(
            value is None
            for value in (
                self.universe_id,
                self.universe_hash,
                self.universe_identity_schema,
                self.policy,
                self.snapshot,
            )
        ):
            raise ValueError("RecommendationUniverseIdentity 不可全為 None")
        if any(
            value is None
            for value in (
                self.universe_id,
                self.universe_hash,
                self.universe_identity_schema,
                self.policy,
                self.snapshot,
            )
        ):
            raise ValueError("RecommendationUniverseIdentity 必須保存 alias、policy 與 snapshot")
        if self.snapshot is not None:
            if (
                self.universe_hash is not None
                and self.snapshot.universe_snapshot_hash is not None
                and self.universe_hash != self.snapshot.universe_snapshot_hash
            ):
                raise ValueError("universe_hash 必須符合 universe_snapshot_hash")
            if (
                self.universe_identity_schema is not None
                and self.snapshot.universe_snapshot_schema is not None
                and self.universe_identity_schema
                != self.snapshot.universe_snapshot_schema
            ):
                raise ValueError("universe_identity_schema 必須符合 snapshot schema")
        if self.policy is not None and self.snapshot is not None:
            snapshot_spec = _load_validated_json_object_snapshot(
                cast(str, self.snapshot.universe_snapshot_spec_json),
                "universe_snapshot_spec_json",
            )
            if snapshot_spec["universe_policy_id"] != self.policy.universe_policy_id:
                raise ValueError("universe snapshot spec 必須參照已保存的 policy id")
        if self.universe_id is not None and self.universe_hash is not None:
            digest = self.universe_hash.removeprefix("sha256:")
            expected_id = f"recommendation-universe-v1:{digest}"
            if self.universe_id != expected_id:
                raise ValueError("universe_id 必須與 universe_hash 相符")


class SnapshotCohortCoverageStatus(str, Enum):
    PARTIAL = "partial"
    DEGRADED = "degraded"
    COMPLETE = "complete"


@dataclass(frozen=True, slots=True)
class SnapshotCohortCoverage:
    """單一代碼在 scheduled cohort 中保存的 coverage v1 列。"""

    status: str | None = None
    quality: str | None = None
    stage: str | None = None
    reason_codes: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("status", "quality", "stage"):
            _require_optional_text(getattr(self, name), name)
        reason_codes = _freeze_tuple(self.reason_codes, "reason_codes", str)
        warnings = _freeze_tuple(self.warnings, "warnings", str)
        object.__setattr__(self, "reason_codes", reason_codes)
        object.__setattr__(self, "warnings", warnings)


@dataclass(frozen=True, slots=True)
class SnapshotCohort:
    """scheduled-recommendation-snapshot-cohort.v1 的完整不可變 owner。"""

    cohort_hash: str
    requested_symbols: tuple[str, ...] = ()
    eligible_symbols: tuple[str, ...] = ()
    missing_symbols: tuple[str, ...] = ()
    degraded_symbols: tuple[str, ...] = ()
    excluded_symbols: tuple[str, ...] = ()
    requested_count: int = 0
    eligible_count: int = 0
    missing_count: int = 0
    degraded_count: int = 0
    excluded_count: int = 0
    coverage_status: SnapshotCohortCoverageStatus = SnapshotCohortCoverageStatus.COMPLETE
    coverage_by_symbol: Mapping[str, SnapshotCohortCoverage] = field(default_factory=dict)
    eligible_definition: str = "final scheduled recommendation DTO rows"
    missing_definition: str = "screening rows with quality=missing; same-day retry candidates"
    degraded_definition: str = "screening rows with quality=degraded; visible but not source-missing"
    excluded_definition: str = "requested rows not selected and not missing/degraded"
    schema_version: str = "scheduled-recommendation-snapshot-cohort.v1"

    def __post_init__(self) -> None:
        _require_optional_hash(self.cohort_hash, "cohort_hash")
        if not self.cohort_hash.startswith("sha256:"):
            raise ValueError("cohort_hash 必須使用 sha256: 前綴")
        if type(self.coverage_status) is not SnapshotCohortCoverageStatus:
            raise TypeError("coverage_status 必須是 SnapshotCohortCoverageStatus")
        if type(self.schema_version) is not str:
            raise TypeError("schema_version 必須是 str")
        if self.schema_version != "scheduled-recommendation-snapshot-cohort.v1":
            raise ValueError("schema_version 不支援此 SnapshotCohort 格式")

        symbol_fields = (
            "requested_symbols",
            "eligible_symbols",
            "missing_symbols",
            "degraded_symbols",
            "excluded_symbols",
        )
        frozen_symbols: dict[str, tuple[str, ...]] = {}
        for name in symbol_fields:
            values = _freeze_tuple(getattr(self, name), name, str)
            if any(not value.strip() for value in values):
                raise ValueError(f"{name} 不可有空白 symbol")
            if len(values) != len(set(values)):
                raise ValueError(f"{name} 不可有重複 symbol")
            if values != tuple(sorted(values)):
                raise ValueError(f"{name} 必須依 scheduled v1 字典序排序")
            frozen_symbols[name] = values

        count_fields = (
            "requested_count",
            "eligible_count",
            "missing_count",
            "degraded_count",
            "excluded_count",
        )
        for name in count_fields:
            _require_nonnegative_int(getattr(self, name), name)
        for name, values in (
            ("requested_count", frozen_symbols["requested_symbols"]),
            ("eligible_count", frozen_symbols["eligible_symbols"]),
            ("missing_count", frozen_symbols["missing_symbols"]),
            ("degraded_count", frozen_symbols["degraded_symbols"]),
            ("excluded_count", frozen_symbols["excluded_symbols"]),
        ):
            if getattr(self, name) != len(values):
                raise ValueError(f"{name} 必須符合對應 symbol 數量")

        requested = set(frozen_symbols["requested_symbols"])
        for name in symbol_fields[1:]:
            if not set(frozen_symbols[name]).issubset(requested):
                raise ValueError(f"{name} 必須包含於 requested_symbols")

        expected_status = (
            SnapshotCohortCoverageStatus.PARTIAL
            if frozen_symbols["missing_symbols"]
            else SnapshotCohortCoverageStatus.DEGRADED
            if frozen_symbols["degraded_symbols"]
            else SnapshotCohortCoverageStatus.COMPLETE
        )
        if self.coverage_status is not expected_status:
            raise ValueError("coverage_status 必須符合 missing/degraded symbols")

        coverage = _freeze_value(self.coverage_by_symbol, "coverage_by_symbol")
        if not isinstance(coverage, Mapping):
            raise TypeError("coverage_by_symbol 必須是 mapping")
        for symbol, item in coverage.items():
            if type(symbol) is not str or not symbol.strip():
                raise TypeError("coverage_by_symbol key 必須是非空白內建 str")
            if symbol not in requested:
                raise ValueError("coverage_by_symbol key 必須屬於 requested_symbols")
            if type(item) is not SnapshotCohortCoverage:
                raise TypeError("coverage_by_symbol 值必須是 SnapshotCohortCoverage")

        coverage_symbols = set(coverage)
        if set(frozen_symbols["requested_symbols"]) != (
            coverage_symbols | set(frozen_symbols["eligible_symbols"])
        ):
            raise ValueError(
                "requested_symbols 必須等於 coverage_by_symbol 與 eligible_symbols 聯集"
            )
        expected_missing = {
            symbol
            for symbol, row in coverage.items()
            if (row.quality or "").lower() == "missing"
        }
        expected_degraded = {
            symbol
            for symbol, row in coverage.items()
            if (row.quality or "").lower() == "degraded"
            and symbol not in expected_missing
        }
        if set(frozen_symbols["missing_symbols"]) != expected_missing:
            raise ValueError("missing_symbols 必須符合 coverage quality=missing")
        if set(frozen_symbols["degraded_symbols"]) != expected_degraded:
            raise ValueError("degraded_symbols 必須符合 coverage quality=degraded")
        expected_excluded = (
            set(frozen_symbols["requested_symbols"])
            - set(frozen_symbols["eligible_symbols"])
            - set(frozen_symbols["missing_symbols"])
            - set(frozen_symbols["degraded_symbols"])
        )
        if set(frozen_symbols["excluded_symbols"]) != expected_excluded:
            raise ValueError("excluded_symbols 必須符合 scheduled v1 集合公式")

        for name in (
            "eligible_definition",
            "missing_definition",
            "degraded_definition",
            "excluded_definition",
        ):
            if type(getattr(self, name)) is not str:
                raise TypeError(f"{name} 必須是 str")

        expected_definitions = {
            "eligible_definition": "final scheduled recommendation DTO rows",
            "missing_definition": "screening rows with quality=missing; same-day retry candidates",
            "degraded_definition": "screening rows with quality=degraded; visible but not source-missing",
            "excluded_definition": "requested rows not selected and not missing/degraded",
        }
        for name, expected in expected_definitions.items():
            if getattr(self, name) != expected:
                raise ValueError(f"{name} 必須符合 scheduled cohort v1 定義")

        body = {
            "schema_version": self.schema_version,
            "requested_symbols": list(frozen_symbols["requested_symbols"]),
            "eligible_symbols": list(frozen_symbols["eligible_symbols"]),
            "missing_symbols": list(frozen_symbols["missing_symbols"]),
            "degraded_symbols": list(frozen_symbols["degraded_symbols"]),
            "excluded_symbols": list(frozen_symbols["excluded_symbols"]),
            "requested_count": self.requested_count,
            "eligible_count": self.eligible_count,
            "missing_count": self.missing_count,
            "degraded_count": self.degraded_count,
            "excluded_count": self.excluded_count,
            "coverage_status": self.coverage_status.value,
            "coverage_by_symbol": {
                symbol: {
                    "status": row.status,
                    "quality": row.quality,
                    "stage": row.stage,
                    "reason_codes": list(row.reason_codes),
                    "warnings": list(row.warnings),
                }
                for symbol, row in coverage.items()
            },
            **expected_definitions,
        }
        expected_hash = "sha256:" + sha256(
            json.dumps(
                body,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        if self.cohort_hash != expected_hash:
            raise ValueError("cohort_hash 必須符合完整 scheduled cohort v1 body")

        for name, values in frozen_symbols.items():
            object.__setattr__(self, name, values)
        object.__setattr__(self, "coverage_by_symbol", coverage)


@dataclass(frozen=True, slots=True)
class RecommendationRunEvidenceIdentity:
    """scheduled recommendation 結果 config 會投影的證據身份欄位。"""

    cost_model_id: str | None = None
    benchmark_id: str | None = None
    industry_benchmark_id: str | None = None
    horizon_days: Decimal | int | str | None = None
    evidence_tier: str | None = None
    return_basis: str | None = None

    def __post_init__(self) -> None:
        for name in (
            "cost_model_id",
            "benchmark_id",
            "industry_benchmark_id",
            "evidence_tier",
            "return_basis",
        ):
            _require_optional_text(getattr(self, name), name)
        if self.horizon_days is not None:
            if type(self.horizon_days) not in (Decimal, int, str):
                raise TypeError("horizon_days 僅接受 Decimal、int、str 或 None")
            if type(self.horizon_days) is Decimal and not self.horizon_days.is_finite():
                raise ValueError("horizon_days Decimal 必須為有限值")
        if all(
            getattr(self, name) is None
            for name in (
                "cost_model_id",
                "benchmark_id",
                "industry_benchmark_id",
                "horizon_days",
                "evidence_tier",
                "return_basis",
            )
        ):
            raise ValueError("RecommendationRunEvidenceIdentity 不可全為 None")


def _snapshot_cohort_value(cohort: SnapshotCohort) -> dict[str, object]:
    """投影完整 scheduled cohort v1 body 與其已驗證 hash。"""

    definitions = {
        "eligible_definition": cohort.eligible_definition,
        "missing_definition": cohort.missing_definition,
        "degraded_definition": cohort.degraded_definition,
        "excluded_definition": cohort.excluded_definition,
    }
    return {
        "schema_version": cohort.schema_version,
        "requested_symbols": list(cohort.requested_symbols),
        "eligible_symbols": list(cohort.eligible_symbols),
        "missing_symbols": list(cohort.missing_symbols),
        "degraded_symbols": list(cohort.degraded_symbols),
        "excluded_symbols": list(cohort.excluded_symbols),
        "requested_count": cohort.requested_count,
        "eligible_count": cohort.eligible_count,
        "missing_count": cohort.missing_count,
        "degraded_count": cohort.degraded_count,
        "excluded_count": cohort.excluded_count,
        "coverage_status": cohort.coverage_status.value,
        "coverage_by_symbol": {
            symbol: {
                "status": row.status,
                "quality": row.quality,
                "stage": row.stage,
                "reason_codes": list(row.reason_codes),
                "warnings": list(row.warnings),
            }
            for symbol, row in cohort.coverage_by_symbol.items()
        },
        **definitions,
        "cohort_hash": cohort.cohort_hash,
    }


_SCHEDULED_RESULT_CONFIG_REQUIRED_KEYS = (
    "research_only",
    "decision_date",
    "max_stocks",
    "top_n",
    "profile_id",
    "profile_name",
    "look_ahead_check",
    "snapshot_cohort",
    "safety_boundary",
    "strategy_version_id",
    "strategy_config_id",
    "strategy_config_hash",
    "strategy_config_schema",
    "strategy_config_spec",
    "universe_id",
    "universe_hash",
    "universe_identity_schema",
    "universe_policy_id",
    "universe_policy_hash",
    "universe_policy_schema",
    "universe_policy_spec",
    "universe_snapshot_id",
    "universe_snapshot_hash",
    "universe_snapshot_schema",
    "universe_snapshot_source_provider_id",
    "universe_snapshot_selected_codes_hash",
    "universe_snapshot_spec",
    "cost_model_id",
    "benchmark_id",
    "horizon_days",
    "evidence_tier",
    "return_basis",
)


def _validate_scheduled_result_config(config: Mapping[str, object]) -> None:
    missing = [key for key in _SCHEDULED_RESULT_CONFIG_REQUIRED_KEYS if key not in config]
    if missing:
        raise ValueError(
            "scheduled result_config 缺少必要鍵: " + ", ".join(missing)
        )
    if config.get("scheduled_snapshot") is not True:
        raise ValueError("scheduled result_config.scheduled_snapshot 必須是 true")
    if config.get("research_only") is not True:
        raise ValueError("scheduled result_config.research_only 必須是 true")

    decision_date = config["decision_date"]
    if not isinstance(decision_date, str):
        raise TypeError("result_config.decision_date 必須是 str")
    _require_nonblank(decision_date, "result_config.decision_date")
    try:
        parsed_decision_date = date.fromisoformat(decision_date)
    except ValueError as exc:
        raise ValueError("result_config.decision_date 必須是 ISO 日期") from exc
    if parsed_decision_date.isoformat() != decision_date:
        raise ValueError("result_config.decision_date 必須是 YYYY-MM-DD")

    for key in ("max_stocks", "top_n"):
        if type(config[key]) is not int:
            raise TypeError(f"result_config.{key} 必須是 int")
        _require_positive_optional_int(cast(int, config[key]), f"result_config.{key}")
    for key in (
        "profile_id",
        "profile_name",
        "look_ahead_check",
        "strategy_version_id",
        "strategy_config_id",
        "strategy_config_hash",
        "strategy_config_schema",
        "universe_id",
        "universe_hash",
        "universe_identity_schema",
        "universe_policy_id",
        "universe_policy_hash",
        "universe_policy_schema",
        "universe_snapshot_id",
        "universe_snapshot_hash",
        "universe_snapshot_schema",
        "universe_snapshot_source_provider_id",
        "universe_snapshot_selected_codes_hash",
        "cost_model_id",
        "benchmark_id",
        "evidence_tier",
        "return_basis",
    ):
        _require_nonblank(cast(str, config[key]), f"result_config.{key}")

    horizon_days = config["horizon_days"]
    if type(horizon_days) not in (int, float, str):
        raise TypeError("result_config.horizon_days 必須是 numeric 或 numeric str")
    if type(horizon_days) is str:
        _require_nonblank(horizon_days, "result_config.horizon_days")
    try:
        parsed_horizon = Decimal(str(horizon_days))
    except (ArithmeticError, ValueError) as exc:
        raise ValueError("result_config.horizon_days 必須是有效 numeric 值") from exc
    if not parsed_horizon.is_finite() or parsed_horizon <= 0:
        raise ValueError("result_config.horizon_days 必須是有限正值")

    for key in (
        "snapshot_cohort",
        "strategy_config_spec",
        "universe_policy_spec",
        "universe_snapshot_spec",
    ):
        if type(config[key]) is not dict:
            raise TypeError(f"result_config.{key} 必須是 JSON object")

    expected_safety_boundary = {
        "confirm": False,
        "writes_evidence_db": False,
        "auto_trading": False,
        "lifecycle_action": False,
    }
    if not _same_json_value(config["safety_boundary"], expected_safety_boundary):
        raise ValueError(
            "result_config.safety_boundary 必須符合 scheduled wrapper contract"
        )


def _validate_result_config_context_overlap(
    config: Mapping[str, object], context: Context
) -> None:
    """比對同份 result config 與 Context 內已具名保存的重疊證據。"""

    require_present = config.get("scheduled_snapshot") is True
    if require_present:
        _validate_scheduled_result_config(config)
        for name in (
            "strategy_identity",
            "universe_identity",
            "evidence_identity",
            "snapshot_cohort",
        ):
            if getattr(context, name) is None:
                raise ValueError(f"scheduled Context.{name} 必須具名保存")

    def check(key: str, expected: object, context_field: str) -> None:
        _assert_result_config_overlap(
            config,
            key,
            expected,
            context_field,
            require_present=require_present,
        )

    if context.snapshot_cohort is not None:
        check(
            "snapshot_cohort",
            _snapshot_cohort_value(context.snapshot_cohort),
            "snapshot_cohort",
        )

    strategy = context.strategy_identity
    if strategy is not None:
        for key in (
            "strategy_version_id",
            "strategy_config_id",
            "strategy_config_hash",
            "strategy_config_schema",
        ):
            check(key, getattr(strategy, key), f"strategy_identity.{key}")
        if strategy.strategy_config_spec_json is not None:
            check(
                "strategy_config_spec",
                _load_validated_json_object_snapshot(
                    strategy.strategy_config_spec_json,
                    "strategy_config_spec_json",
                ),
                "strategy_identity.strategy_config_spec_json",
            )

    universe = context.universe_identity
    if universe is not None:
        for key in ("universe_id", "universe_hash", "universe_identity_schema"):
            check(key, getattr(universe, key), f"universe_identity.{key}")
        if universe.policy is not None:
            policy = universe.policy
            for key in (
                "universe_policy_id",
                "universe_policy_hash",
                "universe_policy_schema",
            ):
                check(
                    key,
                    getattr(policy, key),
                    f"universe_identity.policy.{key}",
                )
            if policy.universe_policy_spec_json is not None:
                check(
                    "universe_policy_spec",
                    _load_validated_json_object_snapshot(
                        policy.universe_policy_spec_json,
                        "universe_policy_spec_json",
                    ),
                    "universe_identity.policy.universe_policy_spec_json",
                )
        if universe.snapshot is not None:
            snapshot = universe.snapshot
            for key in (
                "universe_snapshot_id",
                "universe_snapshot_hash",
                "universe_snapshot_schema",
                "universe_snapshot_source_provider_id",
                "universe_snapshot_selected_codes_hash",
            ):
                check(
                    key,
                    getattr(snapshot, key),
                    f"universe_identity.snapshot.{key}",
                )
            if snapshot.universe_snapshot_spec_json is not None:
                check(
                    "universe_snapshot_spec",
                    _load_validated_json_object_snapshot(
                        snapshot.universe_snapshot_spec_json,
                        "universe_snapshot_spec_json",
                    ),
                    "universe_identity.snapshot.universe_snapshot_spec_json",
                )

    evidence = context.evidence_identity
    if evidence is not None:
        for key in (
            "cost_model_id",
            "benchmark_id",
            "industry_benchmark_id",
            "horizon_days",
            "evidence_tier",
            "return_basis",
        ):
            check(key, getattr(evidence, key), f"evidence_identity.{key}")
        if require_present:
            for key in (
                "cost_model_id",
                "benchmark_id",
                "horizon_days",
                "evidence_tier",
                "return_basis",
            ):
                value = getattr(evidence, key)
                if value is None or (type(value) is str and not value.strip()):
                    raise ValueError(
                        f"scheduled Context.evidence_identity.{key} 必須非空"
                    )


def _check_reference(reference: VersionReference | None, kind: ReferenceKind, field_name: str) -> None:
    if reference is not None:
        if type(reference) is not VersionReference:
            raise TypeError(f"{field_name} 必須是 VersionReference 或 None")
        if reference.kind is not kind:
            raise ValueError(f"{field_name} 的 reference kind 必須是 {kind.value}")


@dataclass(frozen=True, slots=True)
class Request:
    """呼叫者明示的推薦請求與版本選擇。"""

    as_of_date: date | None = None
    config_ref: VersionReference | None = None
    profile_ref: VersionReference | None = None
    strategy_ref: VersionReference | None = None
    policy_ref: VersionReference | None = None
    universe_policy_ref: VersionReference | None = None
    config_snapshot: RecommendationConfigSnapshot | None = None
    max_stocks: int | None = None
    top_n: int | None = None

    def __post_init__(self) -> None:
        _require_date(self.as_of_date, "as_of_date")
        _check_reference(self.config_ref, ReferenceKind.CONFIG, "config_ref")
        _check_reference(self.profile_ref, ReferenceKind.PROFILE, "profile_ref")
        _check_reference(self.strategy_ref, ReferenceKind.STRATEGY, "strategy_ref")
        _check_reference(self.policy_ref, ReferenceKind.POLICY, "policy_ref")
        _check_reference(
            self.universe_policy_ref,
            ReferenceKind.UNIVERSE_POLICY,
            "universe_policy_ref",
        )
        if self.config_snapshot is not None and type(self.config_snapshot) is not RecommendationConfigSnapshot:
            raise TypeError("config_snapshot 必須是 RecommendationConfigSnapshot 或 None")
        _require_positive_optional_int(self.max_stocks, "max_stocks")
        _require_positive_optional_int(self.top_n, "top_n")


@dataclass(frozen=True, slots=True)
class Context:
    """實際執行時取得的 cutoff、來源、版本與輸入品質。"""

    as_of_date: date | None = None
    decision_at: datetime | None = None
    source_refs: tuple[SourceRef, ...] = ()
    data_snapshot_refs: tuple[VersionReference, ...] = ()
    config_ref: VersionReference | None = None
    profile_ref: VersionReference | None = None
    strategy_ref: VersionReference | None = None
    policy_ref: VersionReference | None = None
    universe_policy_ref: VersionReference | None = None
    universe_snapshot_ref: VersionReference | None = None
    algorithm_ref: VersionReference | None = None
    input_quality: QualityReport = field(default_factory=QualityReport)
    warnings: tuple[str, ...] = ()
    created_at: datetime | None = None
    available_at: datetime | None = None
    strategy_identity: StrategyConfigIdentity | None = None
    universe_identity: RecommendationUniverseIdentity | None = None
    snapshot_cohort: SnapshotCohort | None = None
    evidence_identity: RecommendationRunEvidenceIdentity | None = None
    result_config_snapshot: RecommendationResultConfigSnapshot | None = None

    def __post_init__(self) -> None:
        _require_date(self.as_of_date, "as_of_date")
        decision_at = _freeze_aware_datetime(self.decision_at, "decision_at")
        created_at = _freeze_aware_datetime(self.created_at, "created_at")
        available_at = _freeze_aware_datetime(self.available_at, "available_at")
        if (
            available_at is not None
            and decision_at is not None
            and available_at > decision_at
        ):
            raise ValueError("available_at 不可晚於 decision_at")
        source_refs = _freeze_tuple(self.source_refs, "source_refs", SourceRef)
        data_refs = _freeze_tuple(
            self.data_snapshot_refs, "data_snapshot_refs", VersionReference
        )
        for index, reference in enumerate(data_refs):
            if reference.kind is not ReferenceKind.DATA_SNAPSHOT:
                raise ValueError(f"data_snapshot_refs[{index}] 必須是 data_snapshot reference")
        _check_reference(self.config_ref, ReferenceKind.CONFIG, "config_ref")
        _check_reference(self.profile_ref, ReferenceKind.PROFILE, "profile_ref")
        _check_reference(self.strategy_ref, ReferenceKind.STRATEGY, "strategy_ref")
        _check_reference(self.policy_ref, ReferenceKind.POLICY, "policy_ref")
        _check_reference(
            self.universe_policy_ref,
            ReferenceKind.UNIVERSE_POLICY,
            "universe_policy_ref",
        )
        _check_reference(
            self.universe_snapshot_ref,
            ReferenceKind.UNIVERSE_SNAPSHOT,
            "universe_snapshot_ref",
        )
        _check_reference(self.algorithm_ref, ReferenceKind.ALGORITHM, "algorithm_ref")
        if type(self.input_quality) is not QualityReport:
            raise TypeError("input_quality 必須是 QualityReport")
        if self.strategy_identity is not None and type(self.strategy_identity) is not StrategyConfigIdentity:
            raise TypeError("strategy_identity 必須是 StrategyConfigIdentity 或 None")
        if self.universe_identity is not None and type(self.universe_identity) is not RecommendationUniverseIdentity:
            raise TypeError("universe_identity 必須是 RecommendationUniverseIdentity 或 None")
        if self.snapshot_cohort is not None and type(self.snapshot_cohort) is not SnapshotCohort:
            raise TypeError("snapshot_cohort 必須是 SnapshotCohort 或 None")
        if self.evidence_identity is not None and type(self.evidence_identity) is not RecommendationRunEvidenceIdentity:
            raise TypeError("evidence_identity 必須是 RecommendationRunEvidenceIdentity 或 None")
        if self.result_config_snapshot is not None and type(
            self.result_config_snapshot
        ) is not RecommendationResultConfigSnapshot:
            raise TypeError(
                "result_config_snapshot 必須是 RecommendationResultConfigSnapshot 或 None"
            )
        if self.result_config_snapshot is not None:
            result_config = _load_validated_json_object_snapshot(
                self.result_config_snapshot.raw_result_config_json,
                "raw_result_config_json",
            )
            if (
                result_config.get("scheduled_snapshot") is True
                and self.snapshot_cohort is None
            ):
                raise ValueError(
                    "scheduled result config 必須保留 Context.snapshot_cohort"
                )
            _validate_result_config_context_overlap(result_config, self)
        warnings = _freeze_tuple(self.warnings, "warnings", str)
        object.__setattr__(self, "source_refs", source_refs)
        object.__setattr__(self, "data_snapshot_refs", data_refs)
        object.__setattr__(self, "decision_at", decision_at)
        object.__setattr__(self, "created_at", created_at)
        object.__setattr__(self, "available_at", available_at)
        object.__setattr__(self, "warnings", warnings)


class IndexStatus(str, Enum):
    INDEXED = "indexed"
    PENDING = "pending"
    FAILED = "failed"
    UNKNOWN = "unknown"


class MLAvailabilityStatus(str, Enum):
    """單次 execution 的 ML 可用性；不由 reference 或 terminal status 推算。"""

    NOT_REQUESTED = "not_requested"
    UNKNOWN = "unknown"
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    BLOCKED = "blocked"


class MLAvailabilityReason(str, Enum):
    """明示的 ML 缺值或拒絕原因。"""

    MISSING = "missing"
    SCHEMA_MISMATCH = "schema_mismatch"
    QUARANTINED = "quarantined"
    SOURCE_VERSION_UNAVAILABLE = "source_version_unavailable"
    CUTOFF_UNPROVEN = "cutoff_unproven"
    POLICY_BLOCKED = "policy_blocked"


@dataclass(frozen=True, slots=True)
class MLAvailability:
    """ML availability/outcome 與 Rule/quality/terminal outcome 分開保存。"""

    status: MLAvailabilityStatus = MLAvailabilityStatus.UNKNOWN
    reason: MLAvailabilityReason | None = None
    reason_detail: str | None = None

    def __post_init__(self) -> None:
        if type(self.status) is not MLAvailabilityStatus:
            raise TypeError("status 必須是 MLAvailabilityStatus")
        if self.reason is not None and type(self.reason) is not MLAvailabilityReason:
            raise TypeError("reason 必須是 MLAvailabilityReason 或 None")
        if self.reason_detail is not None:
            _require_nonblank(self.reason_detail, "reason_detail")

        if self.status in (
            MLAvailabilityStatus.NOT_REQUESTED,
            MLAvailabilityStatus.UNKNOWN,
            MLAvailabilityStatus.AVAILABLE,
        ):
            if self.reason is not None or self.reason_detail is not None:
                raise ValueError(f"{self.status.value} 不接受 absence reason")
        elif self.reason is None:
            raise ValueError(f"{self.status.value} 必須指定明確的 ML availability reason")


def _validate_result_id(result_id: str) -> None:
    """驗證已解析的結果識別碼，不改寫其原值。"""

    _require_nonblank(result_id, "result_id")


def _validate_sha256_hash(value: str, field_name: str) -> None:
    if type(value) is not str:
        raise TypeError(f"{field_name} 必須是 str")
    if re.fullmatch(r"sha256:[0-9a-f]{64}", value) is None:
        raise ValueError(f"{field_name} 必須是小寫 sha256:<64 hex>")


@dataclass(frozen=True, slots=True)
class MLReceiptBinding:
    """單一 ML receipt 與 execution 身分的不可變本地 binding 摘要。"""

    receipt_ref: VersionReference
    receipt_hash: str
    result_id: str
    decision_date: date
    model_candidate_id: str
    projected_stock_codes: tuple[str, ...]
    cost_scenario_hash: str | None = None

    def __post_init__(self) -> None:
        if type(self.receipt_ref) is not VersionReference:
            raise TypeError("receipt_ref 必須是 VersionReference")
        if self.receipt_ref.kind is not ReferenceKind.ML_RECEIPT:
            raise ValueError("receipt_ref 必須是 ML_RECEIPT reference")
        _validate_sha256_hash(self.receipt_hash, "receipt_hash")
        _validate_result_id(self.result_id)
        if type(self.decision_date) is not date:
            raise TypeError("decision_date 必須是 date")
        _require_nonblank(self.model_candidate_id, "model_candidate_id")
        stock_codes = _freeze_tuple(
            self.projected_stock_codes, "projected_stock_codes", str
        )
        if not stock_codes:
            raise ValueError("projected_stock_codes 不可為空；receipt builder 拒絕空 projection rows")
        for stock_code in stock_codes:
            _require_nonblank(stock_code, "projected_stock_codes stock_code")
        if len(set(stock_codes)) != len(stock_codes):
            raise ValueError("projected_stock_codes 不可重複")
        if self.cost_scenario_hash is not None:
            _validate_sha256_hash(self.cost_scenario_hash, "cost_scenario_hash")
        object.__setattr__(self, "projected_stock_codes", stock_codes)


@dataclass(frozen=True, slots=True)
class RecommendationExecution:
    """同一 invocation 的完整封存結果；items/assessments 只委派給 decision。"""

    result_id: str
    request: Request
    context: Context
    status: ExecutionStatus
    decision: DecisionBatch | None = None
    quality: QualityReport = field(default_factory=QualityReport)
    ml_availability: MLAvailability = field(default_factory=MLAvailability)
    events: tuple[ExecutionEvent, ...] = ()
    related_references: tuple[VersionReference, ...] = ()
    ml_projection_refs: tuple[VersionReference, ...] = ()
    ml_receipt_refs: tuple[MLReceiptBinding, ...] = ()
    failure_reason: str | None = None
    schema_version: ClassVar[str] = schema_version
    schema_revision: ClassVar[int] = EXECUTION_SCHEMA_REVISION

    def __post_init__(self) -> None:
        _validate_result_id(self.result_id)
        if type(self.request) is not Request:
            raise TypeError("request 必須是 Request")
        if type(self.context) is not Context:
            raise TypeError("context 必須是 Context")
        if type(self.status) is not ExecutionStatus:
            raise TypeError("status 必須是 ExecutionStatus")
        if self.context.result_config_snapshot is not None:
            result_config = _load_validated_json_object_snapshot(
                self.context.result_config_snapshot.raw_result_config_json,
                "raw_result_config_json",
            )
            scheduled_snapshot = result_config.get("scheduled_snapshot") is True
            if scheduled_snapshot:
                if self.request.config_snapshot is None:
                    raise ValueError(
                        "scheduled Request.config_snapshot 必須保存 pre-run caller config"
                    )
                caller_config = _load_validated_json_object_snapshot(
                    self.request.config_snapshot.raw_config_json,
                    "raw_config_json",
                )
                if not caller_config:
                    raise ValueError(
                        "scheduled Request.config_snapshot 不可是空 caller config"
                    )
            for limit_name in ("max_stocks", "top_n"):
                request_limit = getattr(self.request, limit_name)
                if scheduled_snapshot and request_limit is None:
                    raise ValueError(
                        f"Request.{limit_name} 必須明示保存 scheduled result config limit"
                    )
                _assert_result_config_overlap(
                    result_config,
                    limit_name,
                    request_limit,
                    f"request.{limit_name}",
                    require_present=scheduled_snapshot,
                )
        if self.status is ExecutionStatus.COMPLETED and self.decision is None:
            raise ValueError("completed execution 必須包含 DecisionBatch")
        if self.status is not ExecutionStatus.COMPLETED and self.decision is not None:
            raise ValueError("failed/cancelled execution 不得發布 DecisionBatch")
        if self.decision is not None and type(self.decision) is not DecisionBatch:
            raise TypeError("decision 必須是 DecisionBatch 或 None")
        if type(self.quality) is not QualityReport:
            raise TypeError("quality 必須是 QualityReport")
        if type(self.ml_availability) is not MLAvailability:
            raise TypeError("ml_availability 必須是 MLAvailability")
        if self.failure_reason is not None and type(self.failure_reason) is not str:
            raise TypeError("failure_reason 僅接受 str 或 None")
        if self.status is ExecutionStatus.COMPLETED:
            if self.failure_reason is not None:
                raise ValueError("completed execution 不得包含 failure_reason")
        elif self.failure_reason is None:
            raise ValueError("failed/cancelled execution 必須包含非空白 failure_reason")
        else:
            _require_nonblank(self.failure_reason, "failure_reason")

        events = _freeze_tuple(self.events, "events", ExecutionEvent)
        related = _freeze_tuple(
            self.related_references, "related_references", VersionReference
        )
        allowed_related_kinds = {
            ReferenceKind.RUNTIME_RUN,
            ReferenceKind.REPLAY_PARENT,
            ReferenceKind.PORTFOLIO_RESULT,
            ReferenceKind.EVIDENCE,
        }
        if any(item.kind not in allowed_related_kinds for item in related):
            raise ValueError(
                "related_references 僅接受 runtime/replay/portfolio/evidence references"
            )
        ml_projection = _freeze_tuple(
            self.ml_projection_refs, "ml_projection_refs", VersionReference
        )
        ml_receipts = _freeze_tuple(
            self.ml_receipt_refs, "ml_receipt_refs", MLReceiptBinding
        )
        if any(item.kind is not ReferenceKind.ML_PROJECTION for item in ml_projection):
            raise ValueError("ml_projection_refs 僅能包含 ML_PROJECTION references")
        receipt_ids = tuple(item.receipt_ref.reference_id for item in ml_receipts)
        if len(set(receipt_ids)) != len(receipt_ids):
            raise ValueError("ml_receipt_refs 不可重複 receipt reference")
        decision_stock_codes: set[str] | None = None
        if self.decision is not None:
            decision_stock_codes = {
                item.stock_code for item in self.decision.items
            } | {item.stock_code for item in self.decision.assessments}
        for index, binding in enumerate(ml_receipts):
            if binding.result_id != self.result_id:
                raise ValueError(
                    f"ml_receipt_refs[{index}] result_id 必須符合本次 execution"
                )
            if (
                self.context.as_of_date is not None
                and binding.decision_date != self.context.as_of_date
            ):
                raise ValueError(
                    f"ml_receipt_refs[{index}] decision_date 必須符合已知 Context.as_of_date"
                )
            if decision_stock_codes is not None and any(
                stock_code not in decision_stock_codes
                for stock_code in binding.projected_stock_codes
            ):
                raise ValueError(
                    f"ml_receipt_refs[{index}] stock_code 必須屬於 DecisionBatch"
                )
        if self.ml_availability.status is MLAvailabilityStatus.NOT_REQUESTED and (
            ml_projection or ml_receipts
        ):
            raise ValueError("not_requested 不可包含 ML projection/receipt references")
        if self.ml_availability.status is MLAvailabilityStatus.AVAILABLE and (
            not ml_projection or not ml_receipts
        ):
            raise ValueError("available 必須包含 projection 與已綁定 receipt references")

        object.__setattr__(self, "events", events)
        object.__setattr__(self, "related_references", related)
        object.__setattr__(self, "ml_projection_refs", ml_projection)
        object.__setattr__(self, "ml_receipt_refs", ml_receipts)

    @property
    def items(self) -> tuple[RecommendationItem, ...]:
        """唯讀委派，不保存第二份 items。"""

        return self.decision.items if self.decision is not None else ()

    @property
    def assessments(self) -> tuple[CandidateAssessment, ...]:
        """唯讀委派，不保存第二份 assessments。"""

        return self.decision.assessments if self.decision is not None else ()


@dataclass(frozen=True, slots=True)
class SaveReceipt:
    """保存結果摘要，不含另一份 recommendation 欄位清單。"""

    result_id: str
    payload_hash: str
    artifact_location: str | None
    persisted_at: datetime
    index_status: IndexStatus
    schema_version: str = schema_version
    schema_revision: int = EXECUTION_SCHEMA_REVISION

    def __post_init__(self) -> None:
        _validate_result_id(self.result_id)
        _require_nonblank(self.payload_hash, "payload_hash")
        if self.artifact_location is not None:
            _require_nonblank(self.artifact_location, "artifact_location")
        persisted_at = _freeze_aware_datetime(self.persisted_at, "persisted_at")
        if type(self.index_status) is not IndexStatus:
            raise TypeError("index_status 必須是 IndexStatus")
        if type(self.schema_version) is not str:
            raise TypeError("schema_version 必須是 str")
        if self.schema_version != schema_version:
            raise ValueError("schema_version 僅接受 recommendation-execution.v1")
        if (
            type(self.schema_revision) is not int
            or self.schema_revision not in SUPPORTED_EXECUTION_SCHEMA_REVISIONS
        ):
            raise ValueError(
                "schema_revision 僅接受明示支援的 revision 1 或 2；不得改寫歷史值"
            )
        object.__setattr__(self, "persisted_at", persisted_at)


_ALLOWED_FROZEN_RECORD_TYPES: tuple[type[object], ...] = (
    SourceRef,
    CandidateAssessment,
    DecisionBatch,
    FactorContribution,
    FilterOutcome,
    LiquidityAssessment,
    NegativeEvidence,
    RecommendationItem,
    RegimeStateTransition,
    UniverseReference,
    Context,
    ExecutionEvent,
    QualityReport,
    RecommendationExecution,
    Request,
    SaveReceipt,
    VersionReference,
    MLAvailability,
    MLReceiptBinding,
    RecommendationConfigSnapshot,
    RecommendationResultConfigSnapshot,
    StrategyConfigIdentity,
    UniversePolicyIdentity,
    UniverseSnapshotIdentity,
    RecommendationUniverseIdentity,
    SnapshotCohortCoverage,
    SnapshotCohort,
    RecommendationRunEvidenceIdentity,
)

_ALLOWED_ENUM_TYPES: tuple[type[Enum], ...] = (
    ReferenceKind,
    ExecutionStatus,
    QualityStatus,
    IndexStatus,
    MLAvailabilityStatus,
    MLAvailabilityReason,
    SnapshotCohortCoverageStatus,
)


__all__ = (
    "EXECUTION_SCHEMA_REVISION",
    "SUPPORTED_EXECUTION_SCHEMA_REVISIONS",
    "ExecutionEvent",
    "ExecutionStatus",
    "IndexStatus",
    "MLAvailability",
    "MLAvailabilityReason",
    "MLAvailabilityStatus",
    "MLReceiptBinding",
    "RecommendationConfigSnapshot",
    "RecommendationResultConfigSnapshot",
    "StrategyConfigIdentity",
    "UniversePolicyIdentity",
    "UniverseSnapshotIdentity",
    "RecommendationUniverseIdentity",
    "SnapshotCohortCoverage",
    "SnapshotCohortCoverageStatus",
    "SnapshotCohort",
    "RecommendationRunEvidenceIdentity",
    "QualityReport",
    "QualityStatus",
    "RecommendationExecution",
    "ReferenceKind",
    "Request",
    "SaveReceipt",
    "VersionReference",
    "Context",
    "schema_version",
)
