"""TWSE／TPEx 月營收 OpenData 雙市場候選擷取與確定性正規化。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
import base64
import hashlib
import json
import os
import re
from pathlib import Path
import stat
from typing import Literal, Mapping
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from data_module.daily_source_snapshot import (
    DAILY_SOURCE_TIME_BASIS_POLICY,
    DAILY_SOURCE_SNAPSHOT_DATASET_ID,
    DailySourceTransportCapture,
    DailySourceBatchValidation,
    DailySourceSnapshotRecord,
    DailySourceUseAcceptance,
    DailySourceValidationCheck,
    _ceil_hour,
    write_daily_source_snapshot,
)
from data_module.monthly_revenue_availability_history import parse_announcement_date
from data_module.monthly_revenue_openapi_preparation import (
    AMOUNT_FIELDS,
    PERCENTAGE_FIELDS,
    REQUIRED_TARGET_FIELDS,
    TwseMonthlyRevenuePreparationError,
    _decode_rows,
    _is_date_only_text,
    _parse_finite_decimal,
    _required_target_values,
    _row_identity,
)


OpenApiMarket = Literal["twse", "tpex"]
TWSE_MONTHLY_REVENUE_OPENAPI_URL = (
    "https://openapi.twse.com.tw/v1/opendata/t187ap05_L"
)
TPEX_MONTHLY_REVENUE_OPENAPI_URL = (
    "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap05_O"
)
OPENAPI_MONTHLY_REVENUE_ENDPOINTS: dict[OpenApiMarket, str] = {
    "twse": TWSE_MONTHLY_REVENUE_OPENAPI_URL,
    "tpex": TPEX_MONTHLY_REVENUE_OPENAPI_URL,
}
OPENAPI_MONTHLY_REVENUE_SOURCE_IDS: dict[OpenApiMarket, str] = {
    "twse": "twse.openapi.t187ap05_L",
    "tpex": "tpex.openapi.mopsfin_t187ap05_O",
}
OPENAPI_MONTHLY_REVENUE_DATASET_IDS: dict[OpenApiMarket, str] = {
    "twse": "18420",
    "tpex": "56510",
}
OPENAPI_MONTHLY_REVENUE_PARSER_VERSION = "twse-tpex-openapi-monthly-revenue-parser.v1"
OPENAPI_MONTHLY_REVENUE_SOURCE_SCHEMA_VERSION = (
    "twse-tpex-openapi-monthly-revenue-14-fields.v1"
)
OPENAPI_MONTHLY_REVENUE_CANDIDATE_SCHEMA = (
    "twse-tpex-openapi-monthly-revenue-candidate.v1"
)
OPENAPI_MONTHLY_REVENUE_APPROVAL_REQUEST_SCHEMA = (
    "twse-tpex-openapi-monthly-revenue-approval-request.v1"
)
MAX_OPENAPI_MONTHLY_REVENUE_BYTES = 2 * 1024 * 1024
MAX_OPENAPI_MONTHLY_REVENUE_ROWS = 100_000
MAX_OPENAPI_UNIT_DOCUMENT_BYTES = 8 * 1024 * 1024
MAX_OPENAPI_UNIT_PROOF_ARTIFACT_BYTES = 9 * 1024 * 1024
MAX_OPENAPI_UNIT_FIELD_MAP_BYTES = 64 * 1024
_EXPECTED_FIELDS = frozenset(
    (
        "備註",
        "公司代號",
        "公司名稱",
        "出表日期",
        "營業收入-上月比較增減(%)",
        "營業收入-上月營收",
        "營業收入-去年同月增減(%)",
        "營業收入-去年當月營收",
        "營業收入-當月營收",
        "產業別",
        "累計營業收入-前期比較增減(%)",
        "累計營業收入-去年累計營收",
        "累計營業收入-當月累計營收",
        "資料年月",
    )
)
_TAIPEI = ZoneInfo("Asia/Taipei")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class OpenApiMonthlyRevenueError(ValueError):
    """OpenData 月營收候選未通過有界擷取或正規化契約。"""


@dataclass(frozen=True, slots=True)
class OpenApiMonthlyRevenueCapture:
    """單一官方 endpoint 的完整 HTTP response body 與 transport metadata。"""

    market: OpenApiMarket
    requested_url: str
    response_url: str
    response_status: int
    content_type_original_text: str | None
    content_encoding_original_text: str | None
    content_length_original_text: str | None
    response_body_complete: bool
    eof_observed: bool
    received_body_bytes: int
    body_observation_ended_at: datetime
    body_completed_at: datetime | None
    raw_response_bytes: bytes

    def __post_init__(self) -> None:
        if self.market not in OPENAPI_MONTHLY_REVENUE_ENDPOINTS:
            raise OpenApiMonthlyRevenueError("capture_market_unsupported")
        expected_url = OPENAPI_MONTHLY_REVENUE_ENDPOINTS[self.market]
        if self.requested_url != expected_url or self.response_url != expected_url:
            raise OpenApiMonthlyRevenueError("capture_endpoint_identity_mismatch")
        if type(self.response_status) is not int:
            raise OpenApiMonthlyRevenueError("capture_http_status_type_invalid")
        if type(self.response_body_complete) is not bool or type(self.eof_observed) is not bool:
            raise OpenApiMonthlyRevenueError("capture_completion_flag_invalid")
        if not isinstance(self.raw_response_bytes, bytes) or not self.raw_response_bytes:
            raise OpenApiMonthlyRevenueError("capture_body_empty_or_invalid")
        if len(self.raw_response_bytes) > MAX_OPENAPI_MONTHLY_REVENUE_BYTES:
            raise OpenApiMonthlyRevenueError("capture_body_exceeds_limit")
        if type(self.received_body_bytes) is not int or self.received_body_bytes != len(
            self.raw_response_bytes
        ):
            raise OpenApiMonthlyRevenueError("capture_body_byte_count_mismatch")
        _require_aware(self.body_observation_ended_at, "body_observation_ended_at")
        if self.body_completed_at is not None:
            _require_aware(self.body_completed_at, "body_completed_at")
            if self.body_completed_at > self.body_observation_ended_at:
                raise OpenApiMonthlyRevenueError("capture_completion_after_observation")

    @property
    def source_id(self) -> str:
        return OPENAPI_MONTHLY_REVENUE_SOURCE_IDS[self.market]

    @property
    def raw_response_sha256(self) -> str:
        return hashlib.sha256(self.raw_response_bytes).hexdigest()

    def verify_transport(self) -> None:
        if self.response_status != 200:
            raise OpenApiMonthlyRevenueError("capture_http_status_not_200")
        content_type = (self.content_type_original_text or "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            raise OpenApiMonthlyRevenueError("capture_content_type_not_json")
        encoding = (self.content_encoding_original_text or "identity").strip().lower()
        if encoding not in {"", "identity"}:
            raise OpenApiMonthlyRevenueError("capture_content_encoding_not_identity")
        if not self.response_body_complete or not self.eof_observed:
            raise OpenApiMonthlyRevenueError("capture_response_incomplete_or_eof_missing")
        if self.body_completed_at is None:
            raise OpenApiMonthlyRevenueError("capture_body_completion_clock_missing")
        if self.content_length_original_text is not None:
            value = self.content_length_original_text.strip()
            if not re.fullmatch(r"\d+", value):
                raise OpenApiMonthlyRevenueError("capture_content_length_invalid")
            if int(value) != len(self.raw_response_bytes):
                raise OpenApiMonthlyRevenueError("capture_content_length_mismatch")

    def provenance_dict(self) -> dict[str, object]:
        return {
            "market": self.market,
            "source_id": self.source_id,
            "requested_url": self.requested_url,
            "response_url": self.response_url,
            "response_status": self.response_status,
            "content_type_original_text": self.content_type_original_text,
            "content_encoding_original_text": self.content_encoding_original_text,
            "content_length_original_text": self.content_length_original_text,
            "response_body_complete": self.response_body_complete,
            "eof_observed": self.eof_observed,
            "received_body_bytes": self.received_body_bytes,
            "raw_response_sha256": self.raw_response_sha256,
            "body_observation_ended_at": _datetime_text(self.body_observation_ended_at),
            "body_completed_at": (
                _datetime_text(self.body_completed_at)
                if self.body_completed_at is not None
                else None
            ),
        }

    def to_daily_source_transport_capture(self) -> DailySourceTransportCapture:
        self.verify_transport()
        if self.body_completed_at is None or self.content_type_original_text is None:
            raise OpenApiMonthlyRevenueError("capture_transport_metadata_missing")
        return DailySourceTransportCapture(
            raw_response_bytes=self.raw_response_bytes,
            official_source_url=self.requested_url,
            response_status=self.response_status,
            content_type=str(self.content_type_original_text),
            declared_decoding_encoding="utf-8",
            decoding_basis="rfc8259_utf8",
            body_completed_at=self.body_completed_at,
            transport_sha256=self.raw_response_sha256,
            response_body_complete=self.response_body_complete,
            received_body_bytes=self.received_body_bytes,
            content_length_original_text=self.content_length_original_text,
            body_completion_evidence_ref="eof:bounded-openapi-read-until-empty",
            response_url=self.response_url,
            content_encoding_original_text=self.content_encoding_original_text,
            eof_observed=self.eof_observed,
            body_observation_ended_at=self.body_observation_ended_at,
        )


@dataclass(frozen=True, slots=True)
class OpenApiMonthlyRevenueRow:
    """由既有 TWSE parser helper 驗證的一筆 OpenData 月營收來源列。"""

    stock_code: str
    company_name: str
    industry: str
    period: str
    roc_period: str
    report_date: date
    report_date_original_text: str
    source_values: tuple[tuple[str, str], ...]
    amount_values_source_unit: tuple[tuple[str, Decimal], ...]
    percentage_values: tuple[tuple[str, Decimal | None], ...]
    percentage_missing_reasons: tuple[tuple[str, str], ...]
    source_version: str


@dataclass(frozen=True, slots=True)
class OpenApiMonthlyRevenueBatch:
    """同一市場、同一資料年月的一次 current-only 候選批次。"""

    capture: OpenApiMonthlyRevenueCapture
    period: str
    roc_period: str
    successful_batch_completed_at: datetime
    available_hour: datetime
    rows: tuple[OpenApiMonthlyRevenueRow, ...]
    unit_proof_sha256: str | None
    conversion_to_twd: Decimal | None

    def __post_init__(self) -> None:
        if self.unit_proof_sha256 is None:
            if self.conversion_to_twd is not None:
                raise OpenApiMonthlyRevenueError("unproven_batch_cannot_claim_unit_conversion")
        elif (
            not isinstance(self.unit_proof_sha256, str)
            or not _SHA256_RE.fullmatch(self.unit_proof_sha256)
            or type(self.conversion_to_twd) is not Decimal
            or self.conversion_to_twd != Decimal("1000")
        ):
            raise OpenApiMonthlyRevenueError("batch_unit_conversion_profile_invalid")

    @property
    def source_qualification(self) -> str:
        return "candidate_only"

    @property
    def historical_pit_eligible(self) -> bool:
        return False

    def to_dict(self) -> dict[str, object]:
        """提供確定性 normalization metadata，不嵌入官方 response bytes。"""
        body_completed_at = self.capture.body_completed_at
        if body_completed_at is None:
            raise OpenApiMonthlyRevenueError(
                "candidate_capture_completion_clock_missing"
            )
        return {
            "schema_version": OPENAPI_MONTHLY_REVENUE_CANDIDATE_SCHEMA,
            "source_id": self.capture.source_id,
            "market": self.capture.market,
            "parser_version": OPENAPI_MONTHLY_REVENUE_PARSER_VERSION,
            "source_schema_version": OPENAPI_MONTHLY_REVENUE_SOURCE_SCHEMA_VERSION,
            "source_authority": "金融監督管理委員會證券期貨局",
            "open_data_license": "政府資料開放授權條款第1版",
            "attribution_required": True,
            "dataset_page": (
                "https://data.gov.tw/dataset/"
                f"{OPENAPI_MONTHLY_REVENUE_DATASET_IDS[self.capture.market]}"
            ),
            "period": self.period,
            "roc_period": self.roc_period,
            "row_count": len(self.rows),
            "coverage_claim": "all_response_rows_only",
            "successful_batch_completed_at": _datetime_text(
                self.successful_batch_completed_at
            ),
            "available_hour": _datetime_text(self.available_hour),
            "availability_policy": DAILY_SOURCE_TIME_BASIS_POLICY,
            "official_publication_at": None,
            "unit_evidence": {
                "status": "trusted_anchor_supplied" if self.unit_proof_sha256 else "unverified",
                "source_unit_original_text": "仟元" if self.unit_proof_sha256 else None,
                "proof_sha256": self.unit_proof_sha256,
                "conversion_to_twd": (
                    str(self.conversion_to_twd)
                    if self.conversion_to_twd is not None
                    else None
                ),
            },
            "raw_capture": self.capture.provenance_dict(),
            "rows": [
                {
                    "stock_code": row.stock_code,
                    "company_name": row.company_name,
                    "industry": row.industry,
                    "period": row.period,
                    "report_date": row.report_date.isoformat(),
                    "report_date_original_text": row.report_date_original_text,
                    "source_version": row.source_version,
                    "source_values": dict(row.source_values),
                    "amount_values_source_unit": {
                        key: str(value) for key, value in row.amount_values_source_unit
                    },
                    "amount_values_twd": (
                        {
                            key: str(_decimal_times_1000_exact(value))
                            for key, value in row.amount_values_source_unit
                        }
                        if self.conversion_to_twd is not None
                        else None
                    ),
                    "percentage_values": {
                        key: str(value) if value is not None else None
                        for key, value in row.percentage_values
                    },
                    "percentage_missing_reasons": dict(row.percentage_missing_reasons),
                }
                for row in self.rows
            ],
            "use_scope": {
                "intended_use": "recommendation_current_fundamental",
                "source_acceptance": False,
                "formal_ingestion_allowed": False,
                "historical_pit_eligible": False,
            },
        }

    def canonical_bytes(self) -> bytes:
        return _canonical_json_bytes(self.to_dict())


@dataclass(frozen=True, slots=True)
class OpenApiMonthlyRevenueUnitProof:
    """外部可信錨點綁定的 OpenData 金額單位文件與欄位映射。"""

    market: OpenApiMarket
    source_id: str
    endpoint_url: str
    official_document_url: str
    official_document_bytes: bytes
    official_document_sha256: str
    field_map_bytes: bytes
    field_map_sha256: str
    trusted_evidence_scope_id: str
    source_unit_original_text: str
    conversion_to_twd: Decimal

    def __post_init__(self) -> None:
        if self.market not in OPENAPI_MONTHLY_REVENUE_ENDPOINTS:
            raise OpenApiMonthlyRevenueError("unit_proof_market_unsupported")
        if self.source_id != OPENAPI_MONTHLY_REVENUE_SOURCE_IDS[self.market]:
            raise OpenApiMonthlyRevenueError("unit_proof_source_identity_mismatch")
        if self.endpoint_url != OPENAPI_MONTHLY_REVENUE_ENDPOINTS[self.market]:
            raise OpenApiMonthlyRevenueError("unit_proof_endpoint_mismatch")
        document = urlsplit(self.official_document_url)
        allowed_hosts = {
            "twse": {"openapi.twse.com.tw", "data.gov.tw"},
            "tpex": {"www.tpex.org.tw", "data.gov.tw"},
        }[self.market]
        if document.scheme != "https" or document.hostname not in allowed_hosts:
            raise OpenApiMonthlyRevenueError("unit_proof_document_url_invalid")
        for label, value in (
            ("official_document_sha256", self.official_document_sha256),
            ("field_map_sha256", self.field_map_sha256),
        ):
            if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
                raise OpenApiMonthlyRevenueError(f"unit_proof_{label}_invalid")
        if (
            not isinstance(self.official_document_bytes, bytes)
            or not self.official_document_bytes
            or len(self.official_document_bytes) > MAX_OPENAPI_UNIT_DOCUMENT_BYTES
            or hashlib.sha256(self.official_document_bytes).hexdigest()
            != self.official_document_sha256
        ):
            raise OpenApiMonthlyRevenueError("unit_proof_official_document_bytes_hash_mismatch")
        if (
            not isinstance(self.field_map_bytes, bytes)
            or not self.field_map_bytes
            or len(self.field_map_bytes) > MAX_OPENAPI_UNIT_FIELD_MAP_BYTES
            or hashlib.sha256(self.field_map_bytes).hexdigest() != self.field_map_sha256
        ):
            raise OpenApiMonthlyRevenueError("unit_proof_field_map_bytes_hash_mismatch")
        expected_field_map = build_openapi_unit_field_map_bytes(
            market=self.market,
            official_document_url=self.official_document_url,
            official_document_sha256=self.official_document_sha256,
        )
        if self.field_map_bytes != expected_field_map:
            raise OpenApiMonthlyRevenueError("unit_proof_field_map_content_mismatch")
        if not self.trusted_evidence_scope_id.strip():
            raise OpenApiMonthlyRevenueError("unit_proof_trusted_scope_missing")
        if self.source_unit_original_text != "仟元":
            raise OpenApiMonthlyRevenueError("unit_proof_source_unit_not_exact")
        if self.conversion_to_twd != Decimal("1000"):
            raise OpenApiMonthlyRevenueError("unit_proof_conversion_not_exact")

    @property
    def proof_sha256(self) -> str:
        return hashlib.sha256(_canonical_json_bytes(self.to_dict())).hexdigest()

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": "opendata-monthly-revenue-unit-proof.v1",
            "market": self.market,
            "source_id": self.source_id,
            "endpoint_url": self.endpoint_url,
            "official_document_url": self.official_document_url,
            "official_document_sha256": self.official_document_sha256,
            "field_map_sha256": self.field_map_sha256,
            "trusted_evidence_scope_id": self.trusted_evidence_scope_id,
            "source_unit_original_text": self.source_unit_original_text,
            "conversion_to_twd": str(self.conversion_to_twd),
        }

    def to_artifact_bytes(self) -> bytes:
        return _canonical_json_bytes(
            {
                "schema_version": "opendata-monthly-revenue-unit-proof-artifact.v1",
                "proof": self.to_dict(),
                "official_document_bytes_base64": base64.b64encode(
                    self.official_document_bytes
                ).decode("ascii"),
                "field_map_bytes_base64": base64.b64encode(self.field_map_bytes).decode("ascii"),
            }
        )

    @classmethod
    def from_artifact_bytes(cls, raw: bytes) -> OpenApiMonthlyRevenueUnitProof:
        if not isinstance(raw, bytes) or not raw or len(raw) > MAX_OPENAPI_UNIT_PROOF_ARTIFACT_BYTES:
            raise OpenApiMonthlyRevenueError("unit_proof_artifact_size_invalid")
        try:
            value = json.loads(
                raw.decode("utf-8", errors="strict"),
                object_pairs_hook=_reject_duplicate_json_keys,
            )
            if _canonical_json_bytes(value) != raw:
                raise OpenApiMonthlyRevenueError("unit_proof_artifact_not_canonical")
            if not isinstance(value, dict) or set(value) != {
                "schema_version",
                "proof",
                "official_document_bytes_base64",
                "field_map_bytes_base64",
            } or value.get("schema_version") != "opendata-monthly-revenue-unit-proof-artifact.v1":
                raise OpenApiMonthlyRevenueError("unit_proof_artifact_schema_invalid")
            proof = value["proof"]
            if not isinstance(proof, dict) or set(proof) != {
                "schema_version",
                "market",
                "source_id",
                "endpoint_url",
                "official_document_url",
                "official_document_sha256",
                "field_map_sha256",
                "trusted_evidence_scope_id",
                "source_unit_original_text",
                "conversion_to_twd",
            } or proof.get("schema_version") != "opendata-monthly-revenue-unit-proof.v1":
                raise OpenApiMonthlyRevenueError("unit_proof_artifact_proof_invalid")
            doc_bytes = base64.b64decode(value["official_document_bytes_base64"], validate=True)
            field_map_bytes = base64.b64decode(value["field_map_bytes_base64"], validate=True)
            return cls(
                market=proof["market"],
                source_id=proof["source_id"],
                endpoint_url=proof["endpoint_url"],
                official_document_url=proof["official_document_url"],
                official_document_bytes=doc_bytes,
                official_document_sha256=proof["official_document_sha256"],
                field_map_bytes=field_map_bytes,
                field_map_sha256=proof["field_map_sha256"],
                trusted_evidence_scope_id=proof["trusted_evidence_scope_id"],
                source_unit_original_text=proof["source_unit_original_text"],
                conversion_to_twd=Decimal(proof["conversion_to_twd"]),
            )
        except OpenApiMonthlyRevenueError:
            raise
        except (UnicodeDecodeError, ValueError, TypeError, KeyError) as exc:
            raise OpenApiMonthlyRevenueError("unit_proof_artifact_invalid") from exc


def build_openapi_unit_field_map_bytes(
    *,
    market: OpenApiMarket,
    official_document_url: str,
    official_document_sha256: str,
) -> bytes:
    if market not in OPENAPI_MONTHLY_REVENUE_ENDPOINTS:
        raise OpenApiMonthlyRevenueError("unit_field_map_market_invalid")
    if not _SHA256_RE.fullmatch(official_document_sha256):
        raise OpenApiMonthlyRevenueError("unit_field_map_document_sha256_invalid")
    return _canonical_json_bytes(
        {
            "schema_version": "opendata-monthly-revenue-unit-field-map.v1",
            "market": market,
            "source_id": OPENAPI_MONTHLY_REVENUE_SOURCE_IDS[market],
            "endpoint_url": OPENAPI_MONTHLY_REVENUE_ENDPOINTS[market],
            "official_document_url": official_document_url,
            "official_document_sha256": official_document_sha256,
            "source_unit": "仟元",
            "conversion_to_twd": "1000",
            "field_unit_map": {field: "仟元" for field in AMOUNT_FIELDS},
        }
    )


def write_openapi_unit_proof_artifact_create_only(
    path: Path | str,
    proof: OpenApiMonthlyRevenueUnitProof,
) -> Path:
    if type(proof) is not OpenApiMonthlyRevenueUnitProof:
        raise OpenApiMonthlyRevenueError("unit_proof_artifact_type_invalid")
    target = Path(path).expanduser()
    if not target.is_absolute():
        raise OpenApiMonthlyRevenueError("unit_proof_artifact_path_must_be_absolute")
    parent = target.parent.resolve(strict=True)
    if target.parent != parent or target.is_symlink():
        raise OpenApiMonthlyRevenueError("unit_proof_artifact_path_invalid")
    payload = proof.to_artifact_bytes()
    if len(payload) > MAX_OPENAPI_UNIT_PROOF_ARTIFACT_BYTES:
        raise OpenApiMonthlyRevenueError("unit_proof_artifact_size_invalid")
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    try:
        descriptor = os.open(target, flags, 0o600)
    except FileExistsError as exc:
        raise OpenApiMonthlyRevenueError("unit_proof_artifact_create_only_conflict") from exc
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    return target


def read_openapi_unit_proof_artifact(
    path: Path | str,
    *,
    expected_proof_sha256: str,
) -> OpenApiMonthlyRevenueUnitProof:
    if not _SHA256_RE.fullmatch(expected_proof_sha256):
        raise OpenApiMonthlyRevenueError("trusted_unit_proof_sha256_invalid")
    target = Path(path).expanduser()
    if (
        not target.is_absolute()
        or target.is_symlink()
        or target.parent.resolve(strict=True) != target.parent
    ):
        raise OpenApiMonthlyRevenueError("unit_proof_artifact_path_invalid")
    try:
        info = target.lstat()
    except OSError as exc:
        raise OpenApiMonthlyRevenueError("unit_proof_artifact_missing") from exc
    if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_OPENAPI_UNIT_PROOF_ARTIFACT_BYTES:
        raise OpenApiMonthlyRevenueError("unit_proof_artifact_file_invalid")
    try:
        raw = target.read_bytes()
    except OSError as exc:
        raise OpenApiMonthlyRevenueError("unit_proof_artifact_unreadable") from exc
    proof = OpenApiMonthlyRevenueUnitProof.from_artifact_bytes(raw)
    if proof.proof_sha256 != expected_proof_sha256:
        raise OpenApiMonthlyRevenueError("unit_proof_artifact_external_hash_mismatch")
    return proof


def prepare_openapi_monthly_revenue_batch(
    *,
    capture: OpenApiMonthlyRevenueCapture,
    successful_batch_completed_at: datetime,
    unit_proof: OpenApiMonthlyRevenueUnitProof | None = None,
    trusted_unit_proof_sha256: str | None = None,
) -> OpenApiMonthlyRevenueBatch:
    """正規化一個官方完整回應；未核單位時只保留原 Decimal 數值。"""
    if type(capture) is not OpenApiMonthlyRevenueCapture:
        raise OpenApiMonthlyRevenueError("capture_type_invalid")
    capture.verify_transport()
    _require_aware(successful_batch_completed_at, "successful_batch_completed_at")
    if capture.body_completed_at is None:
        raise OpenApiMonthlyRevenueError("capture_body_completion_clock_missing")
    if successful_batch_completed_at < capture.body_completed_at:
        raise OpenApiMonthlyRevenueError("successful_batch_precedes_body_completion")
    if unit_proof is not None and (
        type(unit_proof) is not OpenApiMonthlyRevenueUnitProof
        or unit_proof.market != capture.market
        or unit_proof.source_id != capture.source_id
        or unit_proof.endpoint_url != capture.requested_url
    ):
        raise OpenApiMonthlyRevenueError("unit_proof_does_not_match_capture")
    if trusted_unit_proof_sha256 is not None and not _SHA256_RE.fullmatch(
        trusted_unit_proof_sha256
    ):
        raise OpenApiMonthlyRevenueError("trusted_unit_proof_sha256_invalid")
    trusted_proof = (
        unit_proof
        if unit_proof is not None
        and trusted_unit_proof_sha256 == unit_proof.proof_sha256
        else None
    )

    try:
        source_rows = _decode_rows(capture.raw_response_bytes)
    except TwseMonthlyRevenuePreparationError as exc:
        raise OpenApiMonthlyRevenueError(f"source_json_rejected:{exc.reason_code}") from exc
    if not source_rows or len(source_rows) > MAX_OPENAPI_MONTHLY_REVENUE_ROWS:
        raise OpenApiMonthlyRevenueError("source_row_count_invalid")

    normalized: list[OpenApiMonthlyRevenueRow] = []
    seen_codes: set[str] = set()
    period_set: set[str] = set()
    completion_taipei = successful_batch_completed_at.astimezone(_TAIPEI)
    completion_month = f"{completion_taipei.year:04d}-{completion_taipei.month:02d}"
    for index, source_row in enumerate(source_rows):
        if frozenset(source_row) != _EXPECTED_FIELDS:
            raise OpenApiMonthlyRevenueError(f"source_schema_fields_mismatch:{index}")
        if any(not isinstance(value, str) for value in source_row.values()):
            raise OpenApiMonthlyRevenueError(f"source_row_non_text_value:{index}")
        try:
            stock_code, period, roc_period = _row_identity(source_row)
            source_values = _required_target_values(source_row)
            if not source_values["公司名稱"].strip():
                raise OpenApiMonthlyRevenueError(f"company_name_missing:{index}")
            industry = source_row["產業別"].strip()
            if not industry:
                raise OpenApiMonthlyRevenueError(f"industry_missing:{index}")
            report_text = source_values["出表日期"].strip()
            if not _is_date_only_text(report_text):
                raise OpenApiMonthlyRevenueError(f"report_date_not_date_only:{index}")
            report_date = parse_announcement_date(report_text)
            if report_date > completion_taipei.date():
                raise OpenApiMonthlyRevenueError(f"report_date_after_batch:{index}")
            amounts = tuple(
                (field, _parse_finite_decimal(source_values[field], field))
                for field in AMOUNT_FIELDS
            )
            percentages: list[tuple[str, Decimal | None]] = []
            missing_reasons: list[tuple[str, str]] = []
            for field in PERCENTAGE_FIELDS:
                raw_value = source_values[field]
                if not raw_value.strip():
                    percentages.append((field, None))
                    missing_reasons.append((field, "source_cell_blank"))
                else:
                    percentages.append((field, _parse_finite_decimal(raw_value, field)))
        except (TwseMonthlyRevenuePreparationError, TypeError, ValueError) as exc:
            if isinstance(exc, OpenApiMonthlyRevenueError):
                raise
            reason = getattr(exc, "reason_code", "row_validation_failed")
            raise OpenApiMonthlyRevenueError(f"source_row_rejected:{index}:{reason}") from exc
        if stock_code in seen_codes:
            raise OpenApiMonthlyRevenueError(f"duplicate_stock_code:{stock_code}")
        seen_codes.add(stock_code)
        period_set.add(period)
        source_version = (
            f"{capture.source_id}.v1:{capture.market}:{period}:body_completed_at:"
            f"{_datetime_text(capture.body_completed_at)}:sha256:{capture.raw_response_sha256}"
        )
        normalized.append(
            OpenApiMonthlyRevenueRow(
                stock_code=stock_code,
                company_name=source_values["公司名稱"].strip(),
                industry=industry,
                period=period,
                roc_period=roc_period,
                report_date=report_date,
                report_date_original_text=source_values["出表日期"],
                source_values=tuple((field, source_values[field]) for field in REQUIRED_TARGET_FIELDS)
                + (("產業別", source_row["產業別"]),),
                amount_values_source_unit=amounts,
                percentage_values=tuple(percentages),
                percentage_missing_reasons=tuple(missing_reasons),
                source_version=source_version,
            )
        )
    if len(period_set) != 1:
        raise OpenApiMonthlyRevenueError("source_batch_contains_multiple_periods")
    period = next(iter(period_set))
    if period > completion_month:
        raise OpenApiMonthlyRevenueError("source_period_after_successful_batch_month")
    normalized.sort(key=lambda row: row.stock_code)
    return OpenApiMonthlyRevenueBatch(
        capture=capture,
        period=period,
        roc_period=normalized[0].roc_period,
        successful_batch_completed_at=successful_batch_completed_at,
        available_hour=_ceil_hour(successful_batch_completed_at),
        rows=tuple(normalized),
        unit_proof_sha256=trusted_proof.proof_sha256 if trusted_proof else None,
        conversion_to_twd=trusted_proof.conversion_to_twd if trusted_proof else None,
    )


def openapi_batch_to_current_observations(
    batch: OpenApiMonthlyRevenueBatch,
    *,
    observed_at: datetime,
) -> list[dict[str, str]]:
    """建立隔離正規化列；正式使用仍需可信用途接受。"""
    if not isinstance(batch, OpenApiMonthlyRevenueBatch):
        raise OpenApiMonthlyRevenueError("batch_type_invalid")
    if batch.unit_proof_sha256 is None or batch.conversion_to_twd != Decimal("1000"):
        raise OpenApiMonthlyRevenueError("trusted_unit_proof_required_for_twd_normalization")
    _require_aware(observed_at, "observed_at")
    capture_body_completed_at = batch.capture.body_completed_at
    if capture_body_completed_at is None:
        raise OpenApiMonthlyRevenueError("capture_body_completion_clock_missing")
    records: list[dict[str, str]] = []
    for row in batch.rows:
        amounts = dict(row.amount_values_source_unit)
        records.append(
            {
                "stock_code": row.stock_code,
                "kind": "monthly_revenue",
                "period": row.period,
                "as_of_date": _month_end_text(row.period),
                "item_code": "revenue",
                "item_name": "月營收:單月",
                "value": str(
                    _decimal_times_1000_exact(amounts["營業收入-當月營收"])
                ),
                "unit": "TWD",
                "observed_at": _datetime_text(observed_at),
                "source": batch.capture.source_id,
                "source_version": _derived_opendata_current_version(
                    batch.rows[0].source_version,
                    stock_code=row.stock_code,
                    period=row.period,
                    value=str(
                        _decimal_times_1000_exact(amounts["營業收入-當月營收"])
                    ),
                    source_available_at=_datetime_text(capture_body_completed_at),
                ),
                "market": batch.capture.market,
                "period_basis": "monthly_flow",
                "basis_verified": "1",
                "aggregate_feature_eligible": "0",
                "source_available_at": _datetime_text(capture_body_completed_at),
            }
        )
    return records


def publish_openapi_monthly_revenue_snapshot(
    *,
    capture: OpenApiMonthlyRevenueCapture,
    acceptance: DailySourceUseAcceptance,
    proof_artifact_path: Path | str,
    trusted_unit_proof_sha256: str,
    snapshot_root: Path | str,
    batch_id: str,
) -> Path:
    """以外部已批准的用途接受與磁碟proof原件發布一個市場的current快照。"""
    if type(acceptance) is not DailySourceUseAcceptance:
        raise OpenApiMonthlyRevenueError("trusted_source_acceptance_required")
    proof = read_openapi_unit_proof_artifact(
        proof_artifact_path, expected_proof_sha256=trusted_unit_proof_sha256
    )
    if (
        proof.market != capture.market
        or proof.source_id != capture.source_id
        or proof.endpoint_url != capture.requested_url
        or _unit_proof_from_acceptance(acceptance) != proof
    ):
        raise OpenApiMonthlyRevenueError("trusted_acceptance_or_unit_proof_mismatch")
    scope = acceptance.scope
    if (
        scope.dataset_id != DAILY_SOURCE_SNAPSHOT_DATASET_ID
        or scope.source_id != capture.source_id
        or scope.market != capture.market
        or scope.parser_version != OPENAPI_MONTHLY_REVENUE_PARSER_VERSION
        or scope.source_schema_version != OPENAPI_MONTHLY_REVENUE_SOURCE_SCHEMA_VERSION
        or scope.unit != "TWD"
        or scope.intended_use != "recommendation_current_fundamental"
        or acceptance.official_source_endpoint != capture.requested_url
    ):
        raise OpenApiMonthlyRevenueError("trusted_acceptance_profile_mismatch")
    if capture.body_completed_at is None:
        raise OpenApiMonthlyRevenueError("capture_body_completion_clock_missing")
    batch = prepare_openapi_monthly_revenue_batch(
        capture=capture,
        successful_batch_completed_at=capture.body_completed_at,
        unit_proof=proof,
        trusted_unit_proof_sha256=trusted_unit_proof_sha256,
    )
    digest = capture.raw_response_sha256
    records = tuple(
        DailySourceSnapshotRecord(
            stock_code=row.stock_code,
            market=capture.market,
            period=batch.period,
            source_version=row.source_version,
            raw_source_sha256=digest,
            unit="TWD",
        )
        for row in batch.rows
    )
    def passed(check_id: str) -> DailySourceValidationCheck:
        return DailySourceValidationCheck(check_id, "pass", f"{check_id}_opendata_batch_verified")

    validation = DailySourceBatchValidation(
        validation_id=f"{batch_id}-opendata-validation",
        expected_partition_ids=(f"{capture.market}-openapi-monthly-revenue",),
        successful_partition_ids=(f"{capture.market}-openapi-monthly-revenue",),
        failed_partition_ids=(),
        expected_record_count=len(records),
        actual_record_count=len(records),
        source_status_check=passed("source_status"),
        raw_source_hash_check=passed("raw_source_hash"),
        schema_check=passed("schema"),
        unit_check=passed("unit"),
        finite_values_check=passed("finite_values"),
        missing_values_check=passed("missing_values"),
        prior_period_required_check=DailySourceValidationCheck(
            "prior_period_required", "not_required", "prior_period_not_required"
        ),
        official_timestamp_parse_check=DailySourceValidationCheck(
            "official_timestamp_parse", "not_required", "official_timestamp_not_provided"
        ),
    )
    return write_daily_source_snapshot(
        snapshot_root,
        batch_id=batch_id,
        scope=scope,
        use_acceptance=acceptance,
        source_batch_started_at=capture.body_completed_at,
        raw_source_bytes=capture.raw_response_bytes,
        records=records,
        validation=validation,
        transport_capture=capture.to_daily_source_transport_capture(),
    )


def verify_openapi_snapshot_raw_batch(snapshot: object) -> dict[str, Decimal]:
    """重解析固定的完整 response，並要求精確外部單位 proof 錨點。"""
    from data_module.daily_source_snapshot import DailySourceSnapshot

    if type(snapshot) is not DailySourceSnapshot:
        raise OpenApiMonthlyRevenueError("snapshot_type_invalid")
    market = snapshot.scope.market
    if market not in OPENAPI_MONTHLY_REVENUE_ENDPOINTS:
        raise OpenApiMonthlyRevenueError("snapshot_market_invalid")
    expected_source_id = OPENAPI_MONTHLY_REVENUE_SOURCE_IDS[market]
    if snapshot.scope.source_id != expected_source_id or snapshot.scope.unit != "TWD":
        raise OpenApiMonthlyRevenueError("snapshot_profile_or_unit_mismatch")
    transport = snapshot.transport_capture
    if transport is None:
        raise OpenApiMonthlyRevenueError("snapshot_actual_transport_capture_required")
    if transport.canonical_source_bytes != snapshot.raw_source_bytes:
        raise OpenApiMonthlyRevenueError("snapshot_transport_raw_body_mismatch")
    body_observation_ended_at = transport.body_observation_ended_at
    if body_observation_ended_at is None:
        raise OpenApiMonthlyRevenueError("snapshot_transport_observation_end_missing")
    proof = _unit_proof_from_acceptance(snapshot.use_acceptance)
    if (
        proof.market != market
        or proof.source_id != expected_source_id
        or proof.endpoint_url != OPENAPI_MONTHLY_REVENUE_ENDPOINTS[market]
    ):
        raise OpenApiMonthlyRevenueError("trusted_unit_proof_profile_mismatch")
    if snapshot.use_acceptance.official_source_endpoint != OPENAPI_MONTHLY_REVENUE_ENDPOINTS[market]:
        raise OpenApiMonthlyRevenueError("acceptance_endpoint_mismatch")
    if not snapshot.records or any(
        item.market != market or item.unit != "TWD" or item.period != snapshot.records[0].period
        for item in snapshot.records
    ):
        raise OpenApiMonthlyRevenueError("snapshot_record_scope_mismatch")
    version = snapshot.records[0].source_version
    match = re.fullmatch(
        re.escape(expected_source_id) + r"\.v1:(twse|tpex):(\d{4}-\d{2}):"
        r"body_completed_at:(.+):sha256:([0-9a-f]{64})",
        version,
    )
    if match is None or match.group(1) != market or match.group(2) != snapshot.records[0].period:
        raise OpenApiMonthlyRevenueError("snapshot_source_version_profile_invalid")
    body_completed_at = transport.body_completed_at
    if _parse_aware_iso(match.group(3)) != body_completed_at:
        raise OpenApiMonthlyRevenueError("snapshot_transport_completion_clock_mismatch")
    digest = hashlib.sha256(snapshot.raw_source_bytes).hexdigest()
    if match.group(4) != digest or snapshot.raw_source_sha256 != digest:
        raise OpenApiMonthlyRevenueError("snapshot_raw_body_sha_mismatch")
    capture = OpenApiMonthlyRevenueCapture(
        market=market,
        requested_url=transport.official_source_url,
        response_url=transport.response_url or "",
        response_status=transport.response_status,
        content_type_original_text=transport.content_type,
        content_encoding_original_text=transport.content_encoding_original_text,
        content_length_original_text=transport.content_length_original_text,
        response_body_complete=transport.response_body_complete,
        eof_observed=transport.eof_observed,
        received_body_bytes=transport.received_body_bytes,
        body_observation_ended_at=body_observation_ended_at,
        body_completed_at=body_completed_at,
        raw_response_bytes=transport.raw_response_bytes,
    )
    batch = prepare_openapi_monthly_revenue_batch(
        capture=capture,
        successful_batch_completed_at=body_completed_at,
    )
    record_codes = tuple(item.stock_code for item in snapshot.records)
    parsed_by_code = {item.stock_code: item for item in batch.rows}
    if set(record_codes) != set(parsed_by_code) or len(set(record_codes)) != len(record_codes):
        raise OpenApiMonthlyRevenueError("snapshot_recordset_differs_from_raw_response")
    for record in snapshot.records:
        parsed = parsed_by_code[record.stock_code]
        if (
            record.source_version != parsed.source_version
            or record.raw_source_sha256 != digest
            or record.period != batch.period
        ):
            raise OpenApiMonthlyRevenueError("snapshot_record_differs_from_raw_response")
    return {
        row.stock_code: (
            _decimal_times_1000_exact(
                dict(row.amount_values_source_unit)["營業收入-當月營收"]
            )
        )
        for row in batch.rows
    }


def _unit_proof_from_acceptance(acceptance: object) -> OpenApiMonthlyRevenueUnitProof:
    document_chain = getattr(acceptance, "document_chain", None)
    if not isinstance(document_chain, tuple):
        raise OpenApiMonthlyRevenueError("trusted_exact_unit_proof_pin_missing")
    proof_hashes = [
        item.removeprefix("unit-proof-sha256:")
        for item in document_chain
        if isinstance(item, str) and item.startswith("unit-proof-sha256:")
    ]
    proof_refs = [
        item.removeprefix("unit-proof-artifact:")
        for item in document_chain
        if isinstance(item, str) and item.startswith("unit-proof-artifact:")
    ]
    if (
        len(proof_hashes) != 1
        or len(proof_refs) != 1
        or not _SHA256_RE.fullmatch(proof_hashes[0])
        or not proof_refs[0]
    ):
        raise OpenApiMonthlyRevenueError("trusted_exact_unit_proof_pin_missing")
    proof = read_openapi_unit_proof_artifact(
        proof_refs[0], expected_proof_sha256=proof_hashes[0]
    )
    if proof.official_document_url not in document_chain:
        raise OpenApiMonthlyRevenueError("trusted_unit_proof_document_ref_not_accepted")
    scope = getattr(acceptance, "scope", None)
    if (
        scope is None
        or getattr(scope, "market", None) != proof.market
        or getattr(scope, "source_id", None) != proof.source_id
        or getattr(scope, "unit", None) != "TWD"
    ):
        raise OpenApiMonthlyRevenueError("trusted_unit_proof_acceptance_scope_mismatch")
    return proof


def _derived_opendata_current_version(
    raw_source_version: str,
    *,
    stock_code: str,
    period: str,
    value: str,
    source_available_at: str,
) -> str:
    payload = "\0".join(
        (
            OPENAPI_MONTHLY_REVENUE_PARSER_VERSION,
            raw_source_version,
            stock_code,
            period,
            "revenue",
            value,
            "TWD",
            source_available_at,
            "monthly_flow",
            "basis_verified=1",
            "aggregate_feature_eligible=0",
        )
    ).encode("utf-8")
    return (
        f"{OPENAPI_MONTHLY_REVENUE_PARSER_VERSION}:{batch_market(raw_source_version)}:{period}"
        f":raw:{raw_source_version}:derived:sha256:{hashlib.sha256(payload).hexdigest()}"
    )


def batch_market(raw_source_version: str) -> str:
    if raw_source_version.startswith("twse.openapi.t187ap05_L."):
        return "twse"
    if raw_source_version.startswith("tpex.openapi.mopsfin_t187ap05_O."):
        return "tpex"
    raise OpenApiMonthlyRevenueError("raw_source_version_profile_invalid")


def _month_end_text(period: str) -> str:
    year, month = (int(part) for part in period.split("-"))
    from calendar import monthrange

    return date(year, month, monthrange(year, month)[1]).isoformat()


def _parse_aware_iso(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise OpenApiMonthlyRevenueError("source_version_clock_invalid") from exc
    _require_aware(parsed, "source_version_clock")
    return parsed


def build_openapi_monthly_revenue_pair_approval_request(
    *,
    unit_proofs: Mapping[OpenApiMarket, OpenApiMonthlyRevenueUnitProof] | None = None,
) -> bytes:
    """產生等待 Owner 決策的具名雙來源接受提案；不建立 acceptance/accepted_at。"""
    proofs = unit_proofs or {}
    if set(proofs) - set(OPENAPI_MONTHLY_REVENUE_ENDPOINTS):
        raise OpenApiMonthlyRevenueError("approval_request_unit_proof_market_invalid")
    sources: list[dict[str, object]] = []
    for market in ("twse", "tpex"):
        proof = proofs.get(market)
        if proof is not None and (
            type(proof) is not OpenApiMonthlyRevenueUnitProof or proof.market != market
        ):
            raise OpenApiMonthlyRevenueError("approval_request_unit_proof_mismatch")
        sources.append(
            {
                "market": market,
                "dataset_id": "fundamental_current_observations.monthly_revenue",
                "source_id": OPENAPI_MONTHLY_REVENUE_SOURCE_IDS[market],
                "official_source_endpoint": OPENAPI_MONTHLY_REVENUE_ENDPOINTS[market],
                "official_dataset_page": (
                    "https://data.gov.tw/dataset/"
                    f"{OPENAPI_MONTHLY_REVENUE_DATASET_IDS[market]}"
                ),
                "source_authority": "金融監督管理委員會證券期貨局",
                "open_data_license": "政府資料開放授權條款第1版",
                "attribution_required": True,
                "parser_version": OPENAPI_MONTHLY_REVENUE_PARSER_VERSION,
                "source_schema_version": OPENAPI_MONTHLY_REVENUE_SOURCE_SCHEMA_VERSION,
                "unit": "unverified_source_unit",
                "requested_normalized_unit": "TWD" if proof is not None else None,
                "proof_status": "candidate_untrusted" if proof is not None else "missing",
                "intended_use": "recommendation_current_fundamental",
                "unit_proof": proof.to_dict() if proof is not None else None,
            }
        )
    return _canonical_json_bytes(
        {
            "schema_version": OPENAPI_MONTHLY_REVENUE_APPROVAL_REQUEST_SCHEMA,
            "approval_status": "pending_owner_decision",
            "requested_qualification": "current_only_recommendation_fundamental",
            "historical_pit_eligible": False,
            "source_acceptance_created": False,
            "accepted_at": None,
            "sources": sources,
        }
    )


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _reject_duplicate_json_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """拒絕 proof artifact 中重複的 JSON 欄位，避免解析時靜默覆蓋。"""
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise OpenApiMonthlyRevenueError("unit_proof_artifact_duplicate_json_key")
        result[key] = value
    return result


def _decimal_times_1000_exact(value: Decimal) -> Decimal:
    """以調整 Decimal 係數精確乘千，避免 ambient context 捨入。"""
    if type(value) is not Decimal or not value.is_finite():
        raise OpenApiMonthlyRevenueError("source_amount_must_be_finite_decimal")
    sign, digits, exponent = value.as_tuple()
    if not isinstance(exponent, int):
        raise OpenApiMonthlyRevenueError("source_amount_decimal_exponent_invalid")
    return Decimal((sign, digits + (0, 0, 0), exponent))


def _require_aware(value: datetime, label: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise OpenApiMonthlyRevenueError(f"{label}_timezone_missing_or_invalid")


def _datetime_text(value: datetime) -> str:
    _require_aware(value, "datetime")
    return value.astimezone(timezone.utc).isoformat()


__all__ = [
    "MAX_OPENAPI_MONTHLY_REVENUE_BYTES",
    "OPENAPI_MONTHLY_REVENUE_APPROVAL_REQUEST_SCHEMA",
    "OPENAPI_MONTHLY_REVENUE_CANDIDATE_SCHEMA",
    "OPENAPI_MONTHLY_REVENUE_ENDPOINTS",
    "OPENAPI_MONTHLY_REVENUE_DATASET_IDS",
    "OPENAPI_MONTHLY_REVENUE_PARSER_VERSION",
    "OPENAPI_MONTHLY_REVENUE_SOURCE_IDS",
    "OPENAPI_MONTHLY_REVENUE_SOURCE_SCHEMA_VERSION",
    "OpenApiMonthlyRevenueBatch",
    "OpenApiMonthlyRevenueCapture",
    "OpenApiMonthlyRevenueError",
    "OpenApiMonthlyRevenueRow",
    "OpenApiMonthlyRevenueUnitProof",
    "build_openapi_monthly_revenue_pair_approval_request",
    "openapi_batch_to_current_observations",
    "publish_openapi_monthly_revenue_snapshot",
    "verify_openapi_snapshot_raw_batch",
    "prepare_openapi_monthly_revenue_batch",
]
