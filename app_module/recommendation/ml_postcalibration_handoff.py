"""推薦 ML post-calibration facts 的 invocation-local typed handoff。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from enum import Enum
import json
from threading import Lock
from typing import Any, Mapping

from app_module.recommendation.contracts import (
    MLAvailability,
    MLAvailabilityReason,
    MLAvailabilityStatus,
    MLReceiptBinding,
    ReferenceKind,
    VersionReference,
)


class CalibrationProjectionStatusV1(str, Enum):
    """本次校準投影已發布的既有狀態。"""

    ACTIVE_CANDIDATE = "active_candidate"
    RULE_ONLY = "rule_only"
    UNAVAILABLE = "unavailable"


class CalibrationReceiptStatusV1(str, Enum):
    """receipt 發布的既有狀態。"""

    PERSISTED = "persisted"
    UNAVAILABLE = "unavailable"


def encode_candidate_identity_event_json_v1(
    candidate_identity: Mapping[str, Any],
) -> bytes:
    """將 receipt event 使用的 candidate identity 凍結為 canonical JSON bytes。"""

    if not isinstance(candidate_identity, Mapping):
        raise TypeError("candidate_identity 必須是 mapping")
    try:
        encoded = json.dumps(
            dict(candidate_identity),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("candidate_identity 必須可表示為有限 JSON object") from exc
    decoded = json.loads(encoded)
    if not isinstance(decoded, dict):
        raise ValueError("candidate_identity 必須編碼為 JSON object")
    return encoded


@dataclass(frozen=True, slots=True)
class CalibrationReceiptEventFactsV1:
    """同次 receipt event 所需的不可變語意欄位摘要。"""

    payload_present: bool = False
    attempted: bool = False
    persisted: bool = False
    readback_verified: bool = False
    identity_verified: bool = False
    path: str = ""
    receipt_hash: str = ""
    receipt_created_at: str = ""
    error: str = ""
    result_id: str = ""
    decision_date: str = ""
    candidate_id: str = ""
    candidate_identity_json: bytes | None = None
    cost_scenario_hash: str = ""
    cost_scenario_id: str = ""
    projected_stock_codes: tuple[str, ...] = ()
    projection_rows_sha256: str = ""
    inference_source_hash: str = ""
    inference_pit_hash: str = ""
    feature_rows_sha256: str = ""

    def __post_init__(self) -> None:
        for name in (
            "payload_present",
            "attempted",
            "persisted",
            "readback_verified",
            "identity_verified",
        ):
            if type(getattr(self, name)) is not bool:
                raise TypeError(f"{name} 必須是 bool")
        for name in (
            "path",
            "receipt_hash",
            "receipt_created_at",
            "error",
            "result_id",
            "decision_date",
            "candidate_id",
            "cost_scenario_hash",
            "cost_scenario_id",
            "projection_rows_sha256",
            "inference_source_hash",
            "inference_pit_hash",
            "feature_rows_sha256",
        ):
            if type(getattr(self, name)) is not str:
                raise TypeError(f"{name} 必須是 str")
        if self.candidate_identity_json is not None:
            if type(self.candidate_identity_json) is not bytes:
                raise TypeError("candidate_identity_json 必須是 bytes 或 None")
            try:
                decoded = json.loads(self.candidate_identity_json)
            except (UnicodeError, json.JSONDecodeError) as exc:
                raise ValueError("candidate_identity_json 不是有效 UTF-8 JSON") from exc
            if not isinstance(decoded, dict):
                raise ValueError("candidate_identity_json 必須是 JSON object")
            canonical = json.dumps(
                decoded,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
            if canonical != self.candidate_identity_json:
                raise ValueError("candidate_identity_json 必須是 canonical JSON bytes")
            if str(decoded.get("candidate_id") or "") != self.candidate_id:
                raise ValueError("candidate_identity_json 與 candidate_id 不一致")
        if type(self.projected_stock_codes) is not tuple or any(
            type(code) is not str for code in self.projected_stock_codes
        ):
            raise TypeError("projected_stock_codes 必須是 str tuple")

    def event_details(self) -> dict[str, object]:
        """投影成既有 execution event 的 details，不保留 mutable alias。"""

        details: dict[str, object] = {
            "attempted": self.attempted,
            "persisted": self.persisted,
            "readback_verified": self.readback_verified,
            "identity_verified": self.identity_verified,
            "path": self.path,
            "receipt_hash": self.receipt_hash,
            "receipt_created_at": self.receipt_created_at,
            "error": self.error,
        }
        if self.payload_present:
            candidate_identity: dict[str, object] = {}
            if self.candidate_identity_json is not None:
                decoded = json.loads(
                    self.candidate_identity_json,
                    parse_float=Decimal,
                )
                if isinstance(decoded, dict):
                    normalized = _normalize_event_value_v1(decoded)
                    if isinstance(normalized, dict):
                        candidate_identity = normalized
            details.update(
                {
                    "result_id": self.result_id,
                    "decision_date": self.decision_date,
                    "candidate_id": self.candidate_id,
                    "candidate_identity": candidate_identity,
                    "cost_scenario_hash": self.cost_scenario_hash,
                    "cost_scenario_id": self.cost_scenario_id,
                    "projected_stock_codes": self.projected_stock_codes,
                    "projection_rows_sha256": self.projection_rows_sha256,
                    "inference_source_hash": self.inference_source_hash,
                    "inference_pit_hash": self.inference_pit_hash,
                    "feature_rows_sha256": self.feature_rows_sha256,
                    "receipt_body_hash_verified": self.readback_verified,
                }
            )
        return details


@dataclass(frozen=True, slots=True)
class RecommendationPostCalibrationHandoffV1:
    """同一次 recommendation invocation 的 post-calibration 結果。"""

    consumer_configured: bool
    attempted: bool
    projection_status: CalibrationProjectionStatusV1 | None = None
    receipt_status: CalibrationReceiptStatusV1 | None = None
    receipt_error_detail: str | None = None
    receipt_event: CalibrationReceiptEventFactsV1 | None = None

    def __post_init__(self) -> None:
        if type(self.consumer_configured) is not bool:
            raise TypeError("consumer_configured 必須是 bool")
        if type(self.attempted) is not bool:
            raise TypeError("attempted 必須是 bool")
        if self.projection_status is not None and type(
            self.projection_status
        ) is not CalibrationProjectionStatusV1:
            raise TypeError("projection_status 型別不符")
        if self.receipt_status is not None and type(
            self.receipt_status
        ) is not CalibrationReceiptStatusV1:
            raise TypeError("receipt_status 型別不符")
        if self.receipt_error_detail is not None and type(
            self.receipt_error_detail
        ) is not str:
            raise TypeError("receipt_error_detail 必須是 str 或 None")
        if self.receipt_event is not None and type(
            self.receipt_event
        ) is not CalibrationReceiptEventFactsV1:
            raise TypeError("receipt_event 型別不符")


class RecommendationPostCalibrationHandoffSinkV1:
    """單次 execution 專用、只接受一次 immutable handoff 的 sink。"""

    __slots__ = ("__lock", "__published", "__snapshot")

    def __init__(self, *, consumer_configured: bool = False) -> None:
        if type(consumer_configured) is not bool:
            raise TypeError("consumer_configured 必須是 bool")
        self.__lock = Lock()
        self.__published = False
        self.__snapshot = RecommendationPostCalibrationHandoffV1(
            consumer_configured=consumer_configured,
            attempted=False,
        )

    def publish(self, facts: RecommendationPostCalibrationHandoffV1) -> None:
        """封存此 invocation 的最終 post-calibration facts。"""

        if type(facts) is not RecommendationPostCalibrationHandoffV1:
            raise TypeError("facts 必須是 RecommendationPostCalibrationHandoffV1")
        with self.__lock:
            if self.__published:
                raise RuntimeError("post-calibration handoff 已發布")
            self.__snapshot = facts
            self.__published = True

    def snapshot(self) -> RecommendationPostCalibrationHandoffV1:
        """讀取此 invocation 已發布的 immutable snapshot。"""

        with self.__lock:
            return self.__snapshot


def verified_receipt_references_v1(
    *,
    handoff: RecommendationPostCalibrationHandoffV1 | None,
    result_id: str,
    context_date: date | None,
) -> tuple[tuple[MLReceiptBinding, ...], tuple[VersionReference, ...]]:
    """依既有 readback 與 receipt identity 條件建立本地 references。"""

    receipt = handoff.receipt_event if handoff is not None else None
    if receipt is None or not receipt.readback_verified or not receipt.payload_present:
        return (), ()
    candidate_id = receipt.candidate_id.strip()
    receipt_path = receipt.path.strip()
    receipt_hash = receipt.receipt_hash.strip()
    receipt_result_id = receipt.result_id.strip()
    receipt_date = _date_value_v1(receipt.decision_date)
    stock_codes = receipt.projected_stock_codes
    if (
        not receipt_path
        or not receipt_hash
        or not candidate_id
        or receipt_date is None
        or receipt_result_id != result_id
        or (context_date is not None and context_date != receipt_date)
        or not stock_codes
    ):
        return (), ()
    try:
        binding = MLReceiptBinding(
            receipt_ref=VersionReference(ReferenceKind.ML_RECEIPT, receipt_path),
            receipt_hash=receipt_hash,
            result_id=receipt_result_id,
            decision_date=receipt_date,
            model_candidate_id=candidate_id,
            projected_stock_codes=stock_codes,
            cost_scenario_hash=(receipt.cost_scenario_hash or None),
        )
        projection_hash = receipt.projection_rows_sha256.strip()
        projection_ref = (
            VersionReference(ReferenceKind.ML_PROJECTION, projection_hash)
            if projection_hash
            else None
        )
    except (TypeError, ValueError):
        return (), ()
    return (binding,), ((projection_ref,) if projection_ref is not None else ())


def ml_availability_from_handoff_v1(
    *,
    handoff: RecommendationPostCalibrationHandoffV1 | None,
    bindings: tuple[MLReceiptBinding, ...],
    recommendation_count: int,
) -> MLAvailability:
    """依舊有 terminal 規則，由同次 typed facts 建立 ML availability。"""

    if type(recommendation_count) is not int or recommendation_count < 0:
        raise ValueError("recommendation_count 必須是非負 int")
    configured = handoff.consumer_configured if handoff is not None else False
    attempted = handoff.attempted if handoff is not None else False
    receipt = handoff.receipt_event if handoff is not None else None
    if receipt is not None and receipt.identity_verified and bindings:
        return MLAvailability(status=MLAvailabilityStatus.AVAILABLE)
    if not configured or (recommendation_count == 0 and not attempted):
        return MLAvailability(status=MLAvailabilityStatus.NOT_REQUESTED)
    if receipt is not None and (receipt.persisted or receipt.readback_verified):
        detail = receipt.error or "active_candidate_identity_not_verified"
        return MLAvailability(
            status=MLAvailabilityStatus.UNAVAILABLE,
            reason=MLAvailabilityReason.SOURCE_VERSION_UNAVAILABLE,
            reason_detail=detail,
        )
    projection_status = (
        handoff.projection_status if handoff is not None else None
    )
    receipt_status = handoff.receipt_status if handoff is not None else None
    if (
        receipt_status is CalibrationReceiptStatusV1.UNAVAILABLE
        or projection_status is CalibrationProjectionStatusV1.UNAVAILABLE
    ):
        receipt_error_detail = (
            handoff.receipt_error_detail if handoff is not None else None
        )
        detail = (
            receipt_error_detail
            or (
                projection_status.value
                if projection_status is not None
                else "legacy_calibration_unavailable"
            )
        )
        return MLAvailability(
            status=MLAvailabilityStatus.UNAVAILABLE,
            reason=MLAvailabilityReason.MISSING,
            reason_detail=detail,
        )
    return MLAvailability(status=MLAvailabilityStatus.UNKNOWN)


def _date_value_v1(value: object) -> date | None:
    if type(value) is date:
        return value
    if isinstance(value, datetime):
        return value.date()
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10].replace("/", "-"))
    except ValueError:
        if len(text) == 8 and text.isdigit():
            try:
                return datetime.strptime(text, "%Y%m%d").date()
            except ValueError:
                return None
        return None


def _normalize_event_value_v1(value: object) -> object:
    """模擬 execution evidence scalar 投影，不依賴 execute 模組。"""

    if value is None or type(value) in (str, int, bool, Decimal, date, datetime):
        return value
    if type(value) is float:
        try:
            converted = Decimal(str(value))
        except InvalidOperation as exc:
            raise ValueError("candidate identity float 無法封存") from exc
        if not converted.is_finite():
            raise ValueError("candidate identity float 必須是有限值")
        return converted
    if isinstance(value, Mapping):
        normalized: dict[str, object] = {}
        for key, item in value.items():
            if type(key) is not str:
                raise TypeError("candidate identity mapping key 必須是 str")
            normalized[key] = _normalize_event_value_v1(item)
        return normalized
    if isinstance(value, list):
        return tuple(_normalize_event_value_v1(item) for item in value)
    raise TypeError(f"candidate identity 值型別 {type(value).__name__} 不支援")


__all__ = (
    "CalibrationProjectionStatusV1",
    "CalibrationReceiptEventFactsV1",
    "CalibrationReceiptStatusV1",
    "RecommendationPostCalibrationHandoffSinkV1",
    "RecommendationPostCalibrationHandoffV1",
    "encode_candidate_identity_event_json_v1",
    "ml_availability_from_handoff_v1",
    "verified_receipt_references_v1",
)
