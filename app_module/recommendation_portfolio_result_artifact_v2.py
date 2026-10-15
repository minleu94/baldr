"""Recommendation Portfolio result artifact v2 codec.

V2 wraps the unchanged V1 document with the producer's typed Decimal capture and
an optional unqualified period-precision contract. It does not publish Registry
artifacts or infer missing source, currency, calendar, or strategy authority.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from typing import ClassVar, Literal, cast

import pandas as pd

from app_module.recommendation_portfolio_dtos import (
    RecommendationPortfolioBacktestResultDTO,
    RecommendationPortfolioPeriodPrecisionCaptureV2,
)
from app_module.recommendation_portfolio_period_precision_v2 import (
    RecommendationPortfolioPeriodObservationV2,
    RecommendationPortfolioPeriodPrecisionV2,
    RecommendationPortfolioPeriodPrecisionV2Error,
)
from app_module.recommendation_portfolio_result_artifact import (
    PortfolioResultArtifactCodecError,
    RecommendationPortfolioResultArtifactV1,
    decode_portfolio_result_artifact,
    encode_portfolio_result_artifact,
)


RECOMMENDATION_PORTFOLIO_RESULT_SCHEMA_VERSION_V2 = (
    "recommendation-portfolio-result.v2"
)
RECOMMENDATION_PORTFOLIO_RESULT_SCHEMA_REVISION_V2 = 2
_MAX_JSON_BYTES = 16 * 1024 * 1024
_MAX_CAPTURE_OBSERVATIONS = 20_000
_SHA256_PATTERN = re.compile(r"sha256:[0-9a-f]{64}\Z")
_ENVELOPE_KEYS = {
    "schema_version",
    "schema_revision",
    "registry_run_id",
    "portfolio_parent_id",
    "equity_parquet_sha256",
    "trades_parquet_sha256",
    "payload",
    "payload_hash",
}
_PAYLOAD_KEYS = {
    "base_v1_document",
    "period_precision_capture",
    "period_precision_capture_status",
    "period_precision_capture_reason",
    "metadata_strategy_id",
    "metadata_strategy_version",
    "period_precision",
}
_CAPTURE_KEYS = {
    "stock_code",
    "stock_scope_status",
    "capture_status",
    "initial_capital_decimal",
    "requested_start_date",
    "requested_end_date",
    "observed_session_dates",
    "completion_status",
    "execution_contract_id",
    "execution_contract_version",
    "cost_model_status",
    "cost_model_id",
    "cost_model_version",
    "observations",
}

CaptureResultStatusV2 = Literal["captured_unqualified", "partial"]


class PortfolioResultArtifactV2CodecError(PortfolioResultArtifactCodecError):
    """Portfolio result v2 envelope、capture 或 period contract 無效。"""


def _fail(message: str) -> PortfolioResultArtifactV2CodecError:
    return PortfolioResultArtifactV2CodecError(message)


def _canonical_json_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise _fail("portfolio result v2 無法編成 canonical UTF-8 JSON") from exc


def _require_object(
    value: object,
    *,
    keys: set[str],
    field_name: str,
) -> dict[str, object]:
    if type(value) is not dict:
        raise _fail(f"{field_name} 必須是 JSON object")
    mapping = cast(dict[str, object], value)
    if set(mapping) != keys:
        raise _fail(f"{field_name} 欄位不完整或含未知欄位")
    return mapping


def _require_identity(value: object, field_name: str) -> str:
    if (
        type(value) is not str
        or not value
        or len(value) > 256
        or value != value.strip()
        or any(ord(character) < 32 for character in value)
    ):
        raise _fail(f"{field_name} 必須是有界、無空白邊界的非空字串")
    return cast(str, value)


def _optional_metadata_identity(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _require_identity(value, field_name)


def _require_sha256(value: object, field_name: str) -> str:
    if type(value) is not str or _SHA256_PATTERN.fullmatch(value) is None:
        raise _fail(f"{field_name} 必須是 sha256:<64 小寫 hex>")
    return cast(str, value)


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _fail(f"JSON object 含重複 key: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> object:
    raise _fail(f"JSON 不允許非有限數值常數: {value}")


def _strict_json_load(raw_payload: bytes) -> object:
    if type(raw_payload) is not bytes:
        raise TypeError("raw_payload 必須是 bytes")
    if len(raw_payload) > _MAX_JSON_BYTES:
        raise _fail("portfolio result v2 JSON 超過 16 MiB byte budget")
    try:
        return json.loads(
            raw_payload.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_json_constant,
        )
    except PortfolioResultArtifactV2CodecError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise _fail("portfolio result v2 不是有效 UTF-8 JSON") from exc


@dataclass(frozen=True, slots=True)
class _DecodedPayloadV2:
    base_v1_artifact: RecommendationPortfolioResultArtifactV1
    period_precision_capture: RecommendationPortfolioPeriodPrecisionCaptureV2
    period_precision_capture_status: CaptureResultStatusV2
    period_precision_capture_reason: str | None
    metadata_strategy_id: str | None
    metadata_strategy_version: str | None
    period_precision: RecommendationPortfolioPeriodPrecisionV2 | None
    missing_precision_identity: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _DecodedDocumentV2:
    document: dict[str, object]
    payload: _DecodedPayloadV2


def _capture_from_dict(value: object) -> RecommendationPortfolioPeriodPrecisionCaptureV2:
    mapping = _require_object(
        value,
        keys=_CAPTURE_KEYS,
        field_name="period_precision_capture",
    )
    observation_values = mapping["observations"]
    if type(observation_values) is not list or not observation_values:
        raise _fail("period_precision_capture.observations 必須是非空 JSON array")
    if len(observation_values) > _MAX_CAPTURE_OBSERVATIONS:
        raise _fail("period_precision_capture.observations 超過列數 budget")
    try:
        observations = tuple(
            RecommendationPortfolioPeriodObservationV2.from_dict(item)
            for item in observation_values
        )
        observed_dates_value = mapping["observed_session_dates"]
        if type(observed_dates_value) is not list:
            raise _fail("observed_session_dates 必須是 JSON array")
        capture = RecommendationPortfolioPeriodPrecisionCaptureV2(
            stock_code=cast(str, mapping["stock_code"]),
            stock_scope_status=cast(Literal["exact_single_stock"], mapping["stock_scope_status"]),
            capture_status=cast(Literal["complete", "partial"], mapping["capture_status"]),
            initial_capital_decimal=cast(str, mapping["initial_capital_decimal"]),
            requested_start_date=cast(str, mapping["requested_start_date"]),
            requested_end_date=cast(str, mapping["requested_end_date"]),
            observed_session_dates=tuple(cast(list[str], observed_dates_value)),
            completion_status=cast(Literal["completed", "cancelled"], mapping["completion_status"]),
            execution_contract_id=cast(str, mapping["execution_contract_id"]),
            execution_contract_version=cast(str, mapping["execution_contract_version"]),
            cost_model_status=cast(Literal["identified", "unknown"], mapping["cost_model_status"]),
            cost_model_id=cast(str | None, mapping["cost_model_id"]),
            cost_model_version=cast(str | None, mapping["cost_model_version"]),
            observations=observations,
        )
    except PortfolioResultArtifactV2CodecError:
        raise
    except (TypeError, ValueError, RecommendationPortfolioPeriodPrecisionV2Error) as exc:
        raise _fail("period_precision_capture 欄位不符合 typed producer contract") from exc
    if _canonical_json_bytes(asdict(capture)) != _canonical_json_bytes(mapping):
        raise _fail("period_precision_capture 不是 canonical typed capture")
    return capture


def _missing_precision_identity(
    *,
    capture: RecommendationPortfolioPeriodPrecisionCaptureV2,
    metadata_strategy_id: str | None,
    metadata_strategy_version: str | None,
) -> tuple[str, ...]:
    missing: list[str] = []
    if metadata_strategy_id is None:
        missing.append("metadata_strategy_id")
    if metadata_strategy_version is None:
        missing.append("metadata_strategy_version")
    if capture.cost_model_status != "identified":
        missing.extend(("cost_model_id", "cost_model_version"))
    return tuple(missing)


def _build_period_precision(
    *,
    capture: RecommendationPortfolioPeriodPrecisionCaptureV2,
    metadata_strategy_id: str | None,
    metadata_strategy_version: str | None,
    registry_run_id: str,
    portfolio_parent_id: str,
    equity_parquet_sha256: str,
    trades_parquet_sha256: str,
) -> tuple[
    RecommendationPortfolioPeriodPrecisionV2 | None,
    tuple[str, ...],
]:
    missing = _missing_precision_identity(
        capture=capture,
        metadata_strategy_id=metadata_strategy_id,
        metadata_strategy_version=metadata_strategy_version,
    )
    if missing:
        return None, missing
    if capture.cost_model_id is None or capture.cost_model_version is None:
        raise _fail("identified cost model 缺少原始 ID 或版本")
    if metadata_strategy_id is None or metadata_strategy_version is None:
        raise _fail("策略身份缺件分類與 period precision 建立條件不一致")
    try:
        precision = RecommendationPortfolioPeriodPrecisionV2.create(
            registry_run_id=registry_run_id,
            portfolio_parent_id=portfolio_parent_id,
            strategy_id=metadata_strategy_id,
            strategy_version=metadata_strategy_version,
            stock_code=capture.stock_code,
            initial_capital_decimal=capture.initial_capital_decimal,
            currency_code=None,
            minor_unit_exponent=None,
            currency_authority=None,
            source_fingerprint_sha256=None,
            source_manifest_sha256=None,
            source_raw_sha256=None,
            equity_parquet_sha256=equity_parquet_sha256,
            trades_parquet_sha256=trades_parquet_sha256,
            source_cutoff_at=None,
            source_available_at=None,
            source_availability_basis=None,
            source_quality_status="unknown",
            session_calendar_id=None,
            session_calendar_version=None,
            session_calendar_sha256=None,
            expected_session_dates=None,
            completion_status=capture.completion_status,
            execution_contract_id=capture.execution_contract_id,
            execution_contract_version=capture.execution_contract_version,
            execution_contract_sha256=None,
            cost_model_id=capture.cost_model_id,
            cost_model_version=capture.cost_model_version,
            cost_model_sha256=None,
            observations=capture.observations,
        )
    except RecommendationPortfolioPeriodPrecisionV2Error as exc:
        raise _fail("period_precision 無法由 capture 與明示 metadata 建立") from exc
    precision_bytes = precision.to_json().encode("utf-8")
    if len(precision_bytes) > _MAX_JSON_BYTES:
        raise _fail("period_precision JSON 超過 16 MiB byte budget")
    return precision, ()


def _decode_payload(
    value: object,
    *,
    registry_run_id: str,
    portfolio_parent_id: str,
    equity_parquet_sha256: str,
    trades_parquet_sha256: str,
) -> _DecodedPayloadV2:
    mapping = _require_object(value, keys=_PAYLOAD_KEYS, field_name="portfolio result v2 payload")
    base_v1_document = mapping["base_v1_document"]
    if type(base_v1_document) is not dict:
        raise _fail("base_v1_document 必須是完整 JSON object")
    base_v1_raw = _canonical_json_bytes(base_v1_document)
    if len(base_v1_raw) > _MAX_JSON_BYTES:
        raise _fail("base_v1_document 超過 16 MiB byte budget")
    try:
        base_v1_artifact = decode_portfolio_result_artifact(base_v1_raw)
    except PortfolioResultArtifactCodecError as exc:
        raise _fail("V2 內嵌 V1 document 無法通過既有公開 codec") from exc
    if (
        base_v1_artifact.registry_run_id != registry_run_id
        or base_v1_artifact.portfolio_parent_id != portfolio_parent_id
        or base_v1_artifact.equity_parquet_sha256 != equity_parquet_sha256
        or base_v1_artifact.trades_parquet_sha256 != trades_parquet_sha256
    ):
        raise _fail("V2 envelope 與內嵌 V1 artifact identity/Parquet SHA 不一致")

    capture = _capture_from_dict(mapping["period_precision_capture"])
    raw_capture_status = mapping["period_precision_capture_status"]
    expected_capture_status = (
        "captured_unqualified"
        if capture.capture_status == "complete"
        else "partial"
    )
    if raw_capture_status != expected_capture_status or type(raw_capture_status) is not str:
        raise _fail("原 capture status 與 typed capture completion 不一致")
    capture_status = cast(CaptureResultStatusV2, raw_capture_status)
    capture_reason_value = mapping["period_precision_capture_reason"]
    if capture_reason_value is not None and type(capture_reason_value) is not str:
        raise _fail("原 capture reason 必須保留為字串或 None")
    capture_reason = cast(str | None, capture_reason_value)

    metadata_strategy_id = _optional_metadata_identity(
        mapping["metadata_strategy_id"], "metadata_strategy_id"
    )
    metadata_strategy_version = _optional_metadata_identity(
        mapping["metadata_strategy_version"], "metadata_strategy_version"
    )
    expected_summary_status = (
        "cancelled" if capture.completion_status == "cancelled" else "completed"
    )
    try:
        base_result = base_v1_artifact.materialize_result(
            equity_curve=pd.DataFrame(),
            trades=pd.DataFrame(),
            expected_registry_run_id=registry_run_id,
            expected_portfolio_parent_id=portfolio_parent_id,
            equity_parquet_sha256=equity_parquet_sha256,
            trades_parquet_sha256=trades_parquet_sha256,
        )
    except PortfolioResultArtifactCodecError as exc:
        raise _fail("內嵌 V1 payload 無法 materialize 以驗證 completion") from exc
    if base_result.summary.get("status") != expected_summary_status:
        raise _fail("capture completion 與原始 V1 result summary status 不一致")

    expected_precision, missing = _build_period_precision(
        capture=capture,
        metadata_strategy_id=metadata_strategy_id,
        metadata_strategy_version=metadata_strategy_version,
        registry_run_id=registry_run_id,
        portfolio_parent_id=portfolio_parent_id,
        equity_parquet_sha256=equity_parquet_sha256,
        trades_parquet_sha256=trades_parquet_sha256,
    )
    precision_value = mapping["period_precision"]
    if expected_precision is None:
        if precision_value is not None:
            raise _fail("precision identity 缺件時不得保存 period_precision")
        precision = None
    else:
        if type(precision_value) is not dict:
            raise _fail("完整 precision identity 必須保存 period_precision object")
        precision_bytes = _canonical_json_bytes(precision_value)
        if len(precision_bytes) > _MAX_JSON_BYTES:
            raise _fail("period_precision JSON 超過 16 MiB byte budget")
        try:
            precision = RecommendationPortfolioPeriodPrecisionV2.from_json(
                precision_bytes
            )
        except RecommendationPortfolioPeriodPrecisionV2Error as exc:
            raise _fail("period_precision 不符合 typed V2 contract") from exc
        if precision.to_json() != expected_precision.to_json():
            raise _fail("period_precision 與 capture/metadata/outer identity 不一致")

    return _DecodedPayloadV2(
        base_v1_artifact=base_v1_artifact,
        period_precision_capture=capture,
        period_precision_capture_status=capture_status,
        period_precision_capture_reason=capture_reason,
        metadata_strategy_id=metadata_strategy_id,
        metadata_strategy_version=metadata_strategy_version,
        period_precision=precision,
        missing_precision_identity=missing,
    )


def _parse_document(raw_payload: bytes) -> _DecodedDocumentV2:
    document = _require_object(
        _strict_json_load(raw_payload),
        keys=_ENVELOPE_KEYS,
        field_name="portfolio result v2 envelope",
    )
    schema_version = document["schema_version"]
    if (
        type(schema_version) is not str
        or schema_version != RECOMMENDATION_PORTFOLIO_RESULT_SCHEMA_VERSION_V2
    ):
        raise _fail(f"不支援 schema_version: {schema_version!r}")
    schema_revision = document["schema_revision"]
    if (
        type(schema_revision) is not int
        or schema_revision != RECOMMENDATION_PORTFOLIO_RESULT_SCHEMA_REVISION_V2
    ):
        raise _fail(f"不支援 schema_revision: {schema_revision!r}")
    registry_run_id = _require_identity(document["registry_run_id"], "registry_run_id")
    portfolio_parent_id = _require_identity(
        document["portfolio_parent_id"], "portfolio_parent_id"
    )
    if registry_run_id == portfolio_parent_id:
        raise _fail("registry_run_id 與 portfolio_parent_id 必須分離")
    equity_hash = _require_sha256(
        document["equity_parquet_sha256"], "equity_parquet_sha256"
    )
    trades_hash = _require_sha256(
        document["trades_parquet_sha256"], "trades_parquet_sha256"
    )
    payload_hash = _require_sha256(document["payload_hash"], "payload_hash")
    header = {key: document[key] for key in _ENVELOPE_KEYS if key != "payload_hash"}
    actual_payload_hash = "sha256:" + hashlib.sha256(
        _canonical_json_bytes(header)
    ).hexdigest()
    if actual_payload_hash != payload_hash:
        raise _fail("canonical payload_hash 不符")
    payload = _decode_payload(
        document["payload"],
        registry_run_id=registry_run_id,
        portfolio_parent_id=portfolio_parent_id,
        equity_parquet_sha256=equity_hash,
        trades_parquet_sha256=trades_hash,
    )
    if _canonical_json_bytes(document) != raw_payload:
        raise _fail("V2 sidecar bytes 不是 canonical UTF-8 JSON")
    return _DecodedDocumentV2(document=document, payload=payload)


@dataclass(frozen=True, slots=True)
class RecommendationPortfolioResultArtifactV2:
    """含完整 V1 document 與 typed capture 的不可變 V2 envelope。"""

    raw_payload: bytes
    registry_run_id: str
    portfolio_parent_id: str
    equity_parquet_sha256: str
    trades_parquet_sha256: str
    payload_hash: str
    raw_payload_sha256: str

    schema_version: ClassVar[str] = RECOMMENDATION_PORTFOLIO_RESULT_SCHEMA_VERSION_V2
    schema_revision: ClassVar[int] = RECOMMENDATION_PORTFOLIO_RESULT_SCHEMA_REVISION_V2

    @property
    def canonical_payload_hash(self) -> str:
        return self.payload_hash

    def __post_init__(self) -> None:
        parsed = _parse_document(self.raw_payload)
        document = parsed.document
        expected = {
            "registry_run_id": self.registry_run_id,
            "portfolio_parent_id": self.portfolio_parent_id,
            "equity_parquet_sha256": self.equity_parquet_sha256,
            "trades_parquet_sha256": self.trades_parquet_sha256,
            "payload_hash": self.payload_hash,
        }
        if any(document[key] != value for key, value in expected.items()):
            raise _fail("V2 descriptor fields 與 raw payload 不一致")
        actual_raw_hash = "sha256:" + hashlib.sha256(self.raw_payload).hexdigest()
        if self.raw_payload_sha256 != actual_raw_hash:
            raise _fail("raw_payload_sha256 不符")

    @property
    def period_precision_capture(self) -> RecommendationPortfolioPeriodPrecisionCaptureV2:
        return _parse_document(self.raw_payload).payload.period_precision_capture

    @property
    def period_precision_capture_status(self) -> CaptureResultStatusV2:
        return _parse_document(self.raw_payload).payload.period_precision_capture_status

    @property
    def period_precision_capture_reason(self) -> str | None:
        return _parse_document(self.raw_payload).payload.period_precision_capture_reason

    @property
    def period_precision(self) -> RecommendationPortfolioPeriodPrecisionV2 | None:
        return _parse_document(self.raw_payload).payload.period_precision

    @property
    def missing_precision_identity(self) -> tuple[str, ...]:
        return _parse_document(self.raw_payload).payload.missing_precision_identity

    @property
    def metadata_strategy_id(self) -> str | None:
        return _parse_document(self.raw_payload).payload.metadata_strategy_id

    @property
    def metadata_strategy_version(self) -> str | None:
        return _parse_document(self.raw_payload).payload.metadata_strategy_version

    def materialize_result(
        self,
        *,
        equity_curve: pd.DataFrame,
        trades: pd.DataFrame,
        expected_registry_run_id: str,
        expected_portfolio_parent_id: str,
        equity_parquet_sha256: str,
        trades_parquet_sha256: str,
    ) -> RecommendationPortfolioBacktestResultDTO:
        parsed = _parse_document(self.raw_payload)
        result = parsed.payload.base_v1_artifact.materialize_result(
            equity_curve=equity_curve,
            trades=trades,
            expected_registry_run_id=expected_registry_run_id,
            expected_portfolio_parent_id=expected_portfolio_parent_id,
            equity_parquet_sha256=equity_parquet_sha256,
            trades_parquet_sha256=trades_parquet_sha256,
        )
        result.period_precision_capture = parsed.payload.period_precision_capture
        result.period_precision_observations = (
            parsed.payload.period_precision_capture.observations
        )
        result.period_precision_capture_status = (
            parsed.payload.period_precision_capture_status
        )
        result.period_precision_capture_reason = (
            parsed.payload.period_precision_capture_reason
        )
        return result


def encode_portfolio_result_artifact_v2(
    result: RecommendationPortfolioBacktestResultDTO,
    *,
    registry_run_id: str,
    portfolio_parent_id: str,
    equity_parquet_sha256: str,
    trades_parquet_sha256: str,
    metadata_strategy_id: str | None,
    metadata_strategy_version: str | None,
) -> RecommendationPortfolioResultArtifactV2:
    """編碼 V2 sidecar；策略身份必須由 caller 的 metadata 明示。"""

    if type(result) is not RecommendationPortfolioBacktestResultDTO:
        raise TypeError("result 必須是 RecommendationPortfolioBacktestResultDTO")
    capture = result.period_precision_capture
    if type(capture) is not RecommendationPortfolioPeriodPrecisionCaptureV2:
        raise _fail("V2 encode 必須有 typed period_precision_capture")
    if len(capture.observations) > _MAX_CAPTURE_OBSERVATIONS:
        raise _fail("period_precision_capture.observations 超過列數 budget")
    if result.period_precision_observations != capture.observations:
        raise _fail("result observation tuple 與 capture 不完全一致")
    expected_capture_status = (
        "captured_unqualified" if capture.capture_status == "complete" else "partial"
    )
    if result.period_precision_capture_status != expected_capture_status:
        raise _fail("result capture status 與 typed capture completion 不一致")
    if result.period_precision_capture_reason is not None and type(
        result.period_precision_capture_reason
    ) is not str:
        raise _fail("原 capture reason 必須是字串或 None")
    expected_summary_status = (
        "cancelled" if capture.completion_status == "cancelled" else "completed"
    )
    if result.summary.get("status") != expected_summary_status:
        raise _fail("typed capture completion 與 result summary status 不一致")

    run_id = _require_identity(registry_run_id, "registry_run_id")
    parent_id = _require_identity(portfolio_parent_id, "portfolio_parent_id")
    if run_id == parent_id:
        raise _fail("registry_run_id 與 portfolio_parent_id 必須分離")
    equity_hash = _require_sha256(equity_parquet_sha256, "equity_parquet_sha256")
    trades_hash = _require_sha256(trades_parquet_sha256, "trades_parquet_sha256")
    strategy_id = _optional_metadata_identity(
        metadata_strategy_id, "metadata_strategy_id"
    )
    strategy_version = _optional_metadata_identity(
        metadata_strategy_version, "metadata_strategy_version"
    )

    try:
        base_v1_artifact = encode_portfolio_result_artifact(
            result,
            registry_run_id=run_id,
            portfolio_parent_id=parent_id,
            equity_parquet_sha256=equity_hash,
            trades_parquet_sha256=trades_hash,
        )
    except PortfolioResultArtifactCodecError as exc:
        raise _fail("原 V1 document 無法通過既有公開 codec") from exc
    base_v1_document = _strict_json_load(base_v1_artifact.raw_payload)
    precision, _missing = _build_period_precision(
        capture=capture,
        metadata_strategy_id=strategy_id,
        metadata_strategy_version=strategy_version,
        registry_run_id=run_id,
        portfolio_parent_id=parent_id,
        equity_parquet_sha256=equity_hash,
        trades_parquet_sha256=trades_hash,
    )
    precision_document: object | None = (
        json.loads(precision.to_json()) if precision is not None else None
    )
    payload: dict[str, object] = {
        "base_v1_document": base_v1_document,
        "period_precision_capture": asdict(capture),
        "period_precision_capture_status": result.period_precision_capture_status,
        "period_precision_capture_reason": result.period_precision_capture_reason,
        "metadata_strategy_id": strategy_id,
        "metadata_strategy_version": strategy_version,
        "period_precision": precision_document,
    }
    header: dict[str, object] = {
        "schema_version": RECOMMENDATION_PORTFOLIO_RESULT_SCHEMA_VERSION_V2,
        "schema_revision": RECOMMENDATION_PORTFOLIO_RESULT_SCHEMA_REVISION_V2,
        "registry_run_id": run_id,
        "portfolio_parent_id": parent_id,
        "equity_parquet_sha256": equity_hash,
        "trades_parquet_sha256": trades_hash,
        "payload": payload,
    }
    payload_hash = "sha256:" + hashlib.sha256(
        _canonical_json_bytes(header)
    ).hexdigest()
    document = dict(header)
    document["payload_hash"] = payload_hash
    raw_payload = _canonical_json_bytes(document)
    if len(raw_payload) > _MAX_JSON_BYTES:
        raise _fail("portfolio result v2 JSON 超過 16 MiB byte budget")
    raw_payload_sha256 = "sha256:" + hashlib.sha256(raw_payload).hexdigest()
    return RecommendationPortfolioResultArtifactV2(
        raw_payload=raw_payload,
        registry_run_id=run_id,
        portfolio_parent_id=parent_id,
        equity_parquet_sha256=equity_hash,
        trades_parquet_sha256=trades_hash,
        payload_hash=payload_hash,
        raw_payload_sha256=raw_payload_sha256,
    )


def decode_portfolio_result_artifact_v2(
    raw_payload: bytes,
) -> RecommendationPortfolioResultArtifactV2:
    """嚴格解碼 V2；V1 仍由其原 codec 單獨 dispatch。"""

    parsed = _parse_document(raw_payload)
    document = parsed.document
    return RecommendationPortfolioResultArtifactV2(
        raw_payload=raw_payload,
        registry_run_id=cast(str, document["registry_run_id"]),
        portfolio_parent_id=cast(str, document["portfolio_parent_id"]),
        equity_parquet_sha256=cast(str, document["equity_parquet_sha256"]),
        trades_parquet_sha256=cast(str, document["trades_parquet_sha256"]),
        payload_hash=cast(str, document["payload_hash"]),
        raw_payload_sha256="sha256:" + hashlib.sha256(raw_payload).hexdigest(),
    )


__all__ = (
    "CaptureResultStatusV2",
    "PortfolioResultArtifactV2CodecError",
    "RECOMMENDATION_PORTFOLIO_RESULT_SCHEMA_REVISION_V2",
    "RECOMMENDATION_PORTFOLIO_RESULT_SCHEMA_VERSION_V2",
    "RecommendationPortfolioResultArtifactV2",
    "decode_portfolio_result_artifact_v2",
    "encode_portfolio_result_artifact_v2",
)
