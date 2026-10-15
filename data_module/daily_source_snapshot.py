"""每日來源快照的不可變保存與小時可得性契約。"""

from __future__ import annotations

import base64
import codecs
from dataclasses import dataclass
from datetime import datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Callable, Mapping, Protocol, Sequence
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo


DAILY_SOURCE_SNAPSHOT_SCHEMA = "daily-source-snapshot.v1"
DAILY_SOURCE_SNAPSHOT_MANIFEST_SCHEMA_V1 = "daily-source-snapshot-manifest.v1"
DAILY_SOURCE_SNAPSHOT_MANIFEST_SCHEMA = "daily-source-snapshot-manifest.v2"
DAILY_SOURCE_SNAPSHOT_RECEIPT_SCHEMA = "daily-source-snapshot-receipt.v1"
DAILY_SOURCE_SNAPSHOT_QUARANTINE_SCHEMA = "daily-source-quarantine.v1"
DAILY_SOURCE_SNAPSHOT_QUARANTINE_TRANSPORT_SCHEMA = "daily-source-quarantine.v2"
DAILY_SOURCE_TIME_BASIS_POLICY = "daily-hour.v1"
DAILY_SOURCE_SNAPSHOT_DATASET_ID = "fundamental_current_observations.monthly_revenue"
DAILY_SOURCE_SNAPSHOT_SOURCE_ID = "mops.monthly_revenue_static_snapshot"
DAILY_SOURCE_SNAPSHOT_MANIFEST_NAME = "manifest.json"
DAILY_SOURCE_SNAPSHOT_RECEIPT_NAME = "receipt.json"
MAX_DAILY_SOURCE_RAW_BYTES = 16 * 1024 * 1024
MAX_DAILY_SOURCE_TRANSPORT_BYTES = 16 * 1024 * 1024
MAX_DAILY_SOURCE_MANIFEST_V1_BYTES = 24 * 1024 * 1024
MAX_DAILY_SOURCE_MANIFEST_BYTES = 48 * 1024 * 1024
# receipt 會逐列複寫來源識別與可用性；沿用 manifest 的有界上限供 writer/reader 共用。
MAX_DAILY_SOURCE_RECEIPT_BYTES = 24 * 1024 * 1024
MAX_DAILY_SOURCE_RECORDS = 100_000
_TAIPEI = ZoneInfo("Asia/Taipei")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_STOCK_CODE_RE = re.compile(r"^\d{4,6}$")
_BATCH_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_ROC_TIMESTAMP_RE = re.compile(r"^(\d{3})/(\d{2})/(\d{2}) (\d{2}):(\d{2}):(\d{2})$")
_ISO_ZONE_SUFFIX_RE = re.compile(r"(Z|[+-]\d{2}(?::?\d{2})?)$")
_CONTENT_TYPE_CHARSET_RE = re.compile(
    r"(?:^|;)\s*charset\s*=\s*(?:\"([^\"]+)\"|'([^']+)'|([^;\s]+))",
    re.IGNORECASE,
)
_CONTENT_TYPE_MEDIA_RE = re.compile(
    r"^[A-Za-z0-9!#$&^_.+-]+/[A-Za-z0-9!#$&^_.+-]+$"
)
_HTML_META_TAG_RE = re.compile(rb"<meta\b[^>]*>", re.IGNORECASE)
_HTML_COMMENT_RE = re.compile(rb"<!--.*?-->", re.DOTALL)
_HTML_META_ATTRIBUTE_RE = re.compile(
    rb"([^\s=/>]+)\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s>]+))",
    re.IGNORECASE,
)
_HTML_CONTENT_CHARSET_RE = re.compile(
    rb"(?:^|;)\s*charset\s*=\s*(?:\"([^\"]+)\"|'([^']+)'|([^;\s]+))",
    re.IGNORECASE,
)


class DailySourceSnapshotError(ValueError):
    """來源快照未通過不可變保存或可得性契約。"""


@dataclass(frozen=True, slots=True)
class DailySourceUseScope:
    """一次性用途接受所綁定的資料與使用範圍。"""

    dataset_id: str
    source_id: str
    market: str
    parser_version: str
    source_schema_version: str
    unit: str
    intended_use: str

    def __post_init__(self) -> None:
        for name in (
            "dataset_id",
            "source_id",
            "market",
            "parser_version",
            "source_schema_version",
            "unit",
            "intended_use",
        ):
            _require_text(getattr(self, name), name)

    def to_dict(self) -> dict[str, str]:
        return {
            "dataset_id": self.dataset_id,
            "source_id": self.source_id,
            "market": self.market,
            "parser_version": self.parser_version,
            "source_schema_version": self.source_schema_version,
            "unit": self.unit,
            "intended_use": self.intended_use,
        }


@dataclass(frozen=True, slots=True)
class DailySourceUseAcceptance:
    """保存一次性來源用途接受紀錄，不代表每日批次品質通過。"""

    scope: DailySourceUseScope
    acceptance_id: str
    accepted_at: datetime
    official_source_endpoint: str
    document_chain: tuple[str, ...]
    acceptance_evidence_ref: str
    authorization_scope: str
    time_basis_policy: str = DAILY_SOURCE_TIME_BASIS_POLICY

    def __post_init__(self) -> None:
        _require_text(self.acceptance_id, "acceptance_id")
        endpoint = _require_text(self.official_source_endpoint, "official_source_endpoint")
        if urlsplit(endpoint).scheme != "https" or not urlsplit(endpoint).netloc:
            raise DailySourceSnapshotError("official_source_endpoint 必須是 HTTPS endpoint")
        chain = _unique_texts_preserving_order(self.document_chain, "document_chain")
        if not chain:
            raise DailySourceSnapshotError("document_chain 不可為空")
        _require_text(self.acceptance_evidence_ref, "acceptance_evidence_ref")
        authorization_scope = _require_text(
            self.authorization_scope, "authorization_scope"
        )
        authorized_uses = set(re.findall(r"[A-Za-z0-9_.-]+", authorization_scope))
        if self.scope.intended_use not in authorized_uses:
            raise DailySourceSnapshotError("來源用途接受未授權此 intended_use")
        if self.time_basis_policy != DAILY_SOURCE_TIME_BASIS_POLICY:
            raise DailySourceSnapshotError("來源用途接受的時間政策版本不支援")
        object.__setattr__(self, "accepted_at", _to_taipei(self.accepted_at, "accepted_at"))
        object.__setattr__(self, "document_chain", chain)

    def to_dict(self) -> dict[str, object]:
        return {
            "scope": self.scope.to_dict(),
            "acceptance_id": self.acceptance_id,
            "accepted_at": _datetime_text(self.accepted_at),
            "official_source_endpoint": self.official_source_endpoint,
            "document_chain": list(self.document_chain),
            "acceptance_evidence_ref": self.acceptance_evidence_ref,
            "authorization_scope": self.authorization_scope,
            "time_basis_policy": self.time_basis_policy,
        }

    @classmethod
    def from_dict(cls, value: object) -> DailySourceUseAcceptance:
        """重用原接受decoder；canonical內容不能以正規化掩蓋來源漂移。"""
        result = _acceptance_from_dict(value)
        if result.to_dict() != value:
            raise DailySourceSnapshotError("一次性用途接受紀錄不是canonical內容")
        return result


@dataclass(frozen=True, slots=True)
class DailySourceSnapshotRecord:
    """一筆月營收列的來源識別；版本須沿用既有 MOPS v1/v2 hash 格式。"""

    stock_code: str
    market: str
    period: str
    source_version: str
    raw_source_sha256: str
    unit: str
    official_timestamp: datetime | None = None
    official_timestamp_original_text: str = ""
    official_timestamp_original_timezone: str = ""

    def __post_init__(self) -> None:
        if not _STOCK_CODE_RE.fullmatch(self.stock_code):
            raise DailySourceSnapshotError("stock_code 必須是四至六位數字")
        for name in ("market", "period", "source_version", "unit"):
            _require_text(getattr(self, name), name)
        if not _SHA256_RE.fullmatch(self.raw_source_sha256):
            raise DailySourceSnapshotError("raw_source_sha256 格式錯誤")
        _validate_mops_monthly_version_binding(self)
        if self.official_timestamp is not None:
            original_text = _require_text(
                self.official_timestamp_original_text,
                "official_timestamp_original_text",
            )
            try:
                original_timestamp, original_timezone = _parse_official_timestamp_text(
                    original_text
                )
            except ValueError as exc:
                raise DailySourceSnapshotError(
                    "official timestamp 原文格式或來源時區無法解析"
                ) from exc
            parsed_official = _to_taipei(
                self.official_timestamp, "official_timestamp"
            )
            if _to_taipei(original_timestamp, "official_timestamp_original_text") != parsed_official:
                raise DailySourceSnapshotError("official timestamp 原文與解析時間不符")
            if self.official_timestamp_original_timezone != original_timezone:
                raise DailySourceSnapshotError("official timestamp 原文時區標記不符")
            object.__setattr__(
                self,
                "official_timestamp",
                parsed_official,
            )
        elif self.official_timestamp_original_text:
            raise DailySourceSnapshotError("未提供 parsed official timestamp 卻含原文")
        elif self.official_timestamp_original_timezone:
            raise DailySourceSnapshotError("未提供 parsed official timestamp 卻含來源時區")

    def to_dict(self) -> dict[str, object]:
        return {
            "stock_code": self.stock_code,
            "market": self.market,
            "period": self.period,
            "source_version": self.source_version,
            "raw_source_sha256": self.raw_source_sha256,
            "unit": self.unit,
            "official_timestamp": (
                _datetime_text(self.official_timestamp)
                if self.official_timestamp is not None
                else None
            ),
            "official_timestamp_original_text": self.official_timestamp_original_text,
            "official_timestamp_original_timezone": self.official_timestamp_original_timezone,
        }


@dataclass(frozen=True, slots=True)
class DailySourceValidationCheck:
    """每日驗證的一個具名結果與可追溯原因碼。"""

    check_id: str
    status: str
    reason_code: str

    def __post_init__(self) -> None:
        _require_text(self.check_id, "check_id")
        _require_text(self.reason_code, "reason_code")
        if self.status not in {"pass", "fail", "not_required"}:
            raise DailySourceSnapshotError("每日驗證 check status 不支援")

    def to_dict(self) -> dict[str, str]:
        return {
            "check_id": self.check_id,
            "status": self.status,
            "reason_code": self.reason_code,
        }


@dataclass(frozen=True, slots=True)
class DailySourceBatchValidation:
    """單日批次的完整性與品質驗證收據資料。"""

    validation_id: str
    expected_partition_ids: tuple[str, ...]
    successful_partition_ids: tuple[str, ...]
    failed_partition_ids: tuple[str, ...]
    expected_record_count: int
    actual_record_count: int
    source_status_check: DailySourceValidationCheck
    raw_source_hash_check: DailySourceValidationCheck
    schema_check: DailySourceValidationCheck
    unit_check: DailySourceValidationCheck
    finite_values_check: DailySourceValidationCheck
    missing_values_check: DailySourceValidationCheck
    prior_period_required_check: DailySourceValidationCheck
    official_timestamp_parse_check: DailySourceValidationCheck

    def __post_init__(self) -> None:
        _require_text(self.validation_id, "validation_id")
        expected = _validated_unique_texts(
            self.expected_partition_ids, "expected_partition_ids"
        )
        successful = _validated_unique_texts(
            self.successful_partition_ids, "successful_partition_ids"
        )
        failed = _validated_unique_texts(self.failed_partition_ids, "failed_partition_ids")
        if not expected:
            raise DailySourceSnapshotError("expected_partition_ids 不可為空")
        if successful != expected or failed:
            raise DailySourceSnapshotError("批次分區未完整成功")
        if type(self.expected_record_count) is not int or self.expected_record_count <= 0:
            raise DailySourceSnapshotError("expected_record_count 必須是正整數")
        if type(self.actual_record_count) is not int or self.actual_record_count <= 0:
            raise DailySourceSnapshotError("actual_record_count 必須是正整數")
        if self.actual_record_count > MAX_DAILY_SOURCE_RECORDS:
            raise DailySourceSnapshotError("每日批次記錄數超過上限")
        checks = (
            ("source_status", self.source_status_check),
            ("raw_source_hash", self.raw_source_hash_check),
            ("schema", self.schema_check),
            ("unit", self.unit_check),
            ("finite_values", self.finite_values_check),
            ("missing_values", self.missing_values_check),
            ("prior_period_required", self.prior_period_required_check),
            ("official_timestamp_parse", self.official_timestamp_parse_check),
        )
        for expected_id, check in checks:
            if not isinstance(check, DailySourceValidationCheck):
                raise DailySourceSnapshotError(f"{expected_id} 驗證結果型別錯誤")
            if check.check_id != expected_id:
                raise DailySourceSnapshotError(f"{expected_id} 驗證結果名稱不符")
        if self.prior_period_required_check.status == "not_required":
            if self.prior_period_required_check.reason_code != "prior_period_not_required":
                raise DailySourceSnapshotError("前期 not_required 必須具名原因")
        elif self.prior_period_required_check.status != "pass":
            raise DailySourceSnapshotError("前期必填驗證未通過")
        if self.official_timestamp_parse_check.status == "not_required":
            if self.official_timestamp_parse_check.reason_code != "official_timestamp_not_provided":
                raise DailySourceSnapshotError("official timestamp not_required 必須具名原因")
        elif self.official_timestamp_parse_check.status != "pass":
            raise DailySourceSnapshotError("official timestamp 解析驗證未通過")
        object.__setattr__(self, "expected_partition_ids", expected)
        object.__setattr__(self, "successful_partition_ids", successful)
        object.__setattr__(self, "failed_partition_ids", failed)

    @property
    def quality_status(self) -> str:
        """依具名每日檢查計算品質狀態，不接受單一外部布林宣告。"""

        checks = (
            self.source_status_check,
            self.raw_source_hash_check,
            self.schema_check,
            self.unit_check,
            self.finite_values_check,
            self.missing_values_check,
            self.prior_period_required_check,
            self.official_timestamp_parse_check,
        )
        return (
            "pass"
            if all(check.status == "pass" for check in checks[:6])
            and checks[6].status in {"pass", "not_required"}
            and checks[7].status in {"pass", "not_required"}
            else "fail"
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "validation_id": self.validation_id,
            "expected_partition_ids": list(self.expected_partition_ids),
            "successful_partition_ids": list(self.successful_partition_ids),
            "failed_partition_ids": list(self.failed_partition_ids),
            "expected_record_count": self.expected_record_count,
            "actual_record_count": self.actual_record_count,
            "source_status_check": self.source_status_check.to_dict(),
            "raw_source_hash_check": self.raw_source_hash_check.to_dict(),
            "schema_check": self.schema_check.to_dict(),
            "unit_check": self.unit_check.to_dict(),
            "finite_values_check": self.finite_values_check.to_dict(),
            "missing_values_check": self.missing_values_check.to_dict(),
            "prior_period_required_check": self.prior_period_required_check.to_dict(),
            "official_timestamp_parse_check": self.official_timestamp_parse_check.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class DailySourceTransportCapture:
    """保存原始 HTTP response body 與其明示的嚴格文字解碼證據。"""

    raw_response_bytes: bytes
    official_source_url: str
    response_status: int
    content_type: str
    declared_decoding_encoding: str
    decoding_basis: str
    body_completed_at: datetime
    transport_sha256: str
    response_body_complete: bool
    received_body_bytes: int
    content_length_original_text: str | None
    body_completion_evidence_ref: str
    html_meta_charset_original_text: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.raw_response_bytes, bytes) or not self.raw_response_bytes:
            raise DailySourceSnapshotError("transport response bytes 不可為空")
        if len(self.raw_response_bytes) > MAX_DAILY_SOURCE_TRANSPORT_BYTES:
            raise DailySourceSnapshotError("transport response bytes 超過上限")
        if (
            type(self.response_body_complete) is not bool
            or not self.response_body_complete
        ):
            raise DailySourceSnapshotError("transport response body 必須明示完整")
        if type(self.received_body_bytes) is not int:
            raise DailySourceSnapshotError("received_body_bytes 必須是非 bool 整數")
        if self.received_body_bytes != len(self.raw_response_bytes):
            raise DailySourceSnapshotError("received_body_bytes 與原始 body 長度不符")
        # 先驗原件身分再解析 charset，篡改不能被誤分類成解析缺件。
        if not _SHA256_RE.fullmatch(self.transport_sha256):
            raise DailySourceSnapshotError("transport_sha256 格式錯誤")
        if hashlib.sha256(self.raw_response_bytes).hexdigest() != self.transport_sha256:
            raise DailySourceSnapshotError("transport response bytes 與 transport SHA-256 不符")
        completion_ref = _require_text(
            self.body_completion_evidence_ref,
            "body_completion_evidence_ref",
        )
        if self.content_length_original_text is None:
            if not completion_ref.startswith("eof:") or not completion_ref[4:].strip():
                raise DailySourceSnapshotError(
                    "缺少 Content-Length 時必須提供具名 EOF 完整性證據"
                )
        else:
            content_length = self.content_length_original_text
            if (
                not isinstance(content_length, str)
                or not content_length
                or not content_length.isascii()
                or not content_length.isdigit()
            ):
                raise DailySourceSnapshotError(
                    "content_length_original_text 必須是 ASCII 非負整數原文"
                )
            significant_length = content_length.lstrip("0") or "0"
            if (
                len(significant_length) > len(str(MAX_DAILY_SOURCE_TRANSPORT_BYTES))
                or int(significant_length) != len(self.raw_response_bytes)
            ):
                raise DailySourceSnapshotError(
                    "Content-Length 與原始 body 長度不符"
                )
        if type(self.response_status) is not int or self.response_status != 200:
            raise DailySourceSnapshotError("transport HTTP response status 必須是 200")
        _validate_https_url(self.official_source_url, "official_source_url")
        content_type = _require_text(self.content_type, "content_type")
        media_type = content_type.split(";", 1)[0].strip().lower()
        if not _CONTENT_TYPE_MEDIA_RE.fullmatch(media_type) or media_type not in {
            "text/html",
            "application/xhtml+xml",
        }:
            raise DailySourceSnapshotError("transport Content-Type 必須是 HTML media type")
        encoding = _require_text(
            self.declared_decoding_encoding, "declared_decoding_encoding"
        )
        header_charset = _content_type_charset_text(content_type)
        meta_charset = _html_meta_charset_text(self.raw_response_bytes)
        if (
            self.html_meta_charset_original_text is not None
            and self.html_meta_charset_original_text != meta_charset
        ):
            raise DailySourceSnapshotError("HTML meta charset 原文與 response bytes 不符")
        if header_charset is not None and meta_charset is not None:
            if _codec_name(header_charset) != _codec_name(meta_charset):
                raise DailySourceSnapshotError("HTTP Content-Type 與 HTML meta charset 衝突")
        if self.decoding_basis == "http_content_type_charset":
            selected_charset = header_charset
        elif self.decoding_basis == "html_meta_charset":
            selected_charset = meta_charset
        else:
            raise DailySourceSnapshotError("transport decoding_basis 不受支援")
        if selected_charset is None:
            raise DailySourceSnapshotError("transport decoding_basis 缺少原始 charset 宣告")
        if _codec_name(encoding) != _codec_name(selected_charset):
            raise DailySourceSnapshotError("declared decoding encoding 與原始 charset 不符")
        try:
            self.raw_response_bytes.decode(encoding, errors="strict")
        except (LookupError, UnicodeDecodeError) as exc:
            raise DailySourceSnapshotError("transport response bytes 無法依宣告編碼 strict decode") from exc
        object.__setattr__(
            self,
            "body_completed_at",
            _to_taipei(self.body_completed_at, "transport body_completed_at"),
        )
        object.__setattr__(self, "html_meta_charset_original_text", meta_charset)

    @property
    def decoded_html(self) -> str:
        """依已驗證的 encoding strict decode 原始 response body。"""

        return self.raw_response_bytes.decode(
            self.declared_decoding_encoding,
            errors="strict",
        )

    @property
    def canonical_source_bytes(self) -> bytes:
        """回傳既有 MOPS parser 使用的 UTF-8 canonical payload bytes。"""

        return self.decoded_html.encode("utf-8")

    def to_dict(self) -> dict[str, object]:
        return {
            "raw_response_bytes_base64": base64.b64encode(
                self.raw_response_bytes
            ).decode("ascii"),
            "official_source_url": self.official_source_url,
            "response_status": self.response_status,
            "content_type": self.content_type,
            "declared_decoding_encoding": self.declared_decoding_encoding,
            "decoding_basis": self.decoding_basis,
            "html_meta_charset_original_text": self.html_meta_charset_original_text,
            "body_completed_at": _datetime_text(self.body_completed_at),
            "transport_sha256": self.transport_sha256,
            "response_body_complete": self.response_body_complete,
            "received_body_bytes": self.received_body_bytes,
            "content_length_original_text": self.content_length_original_text,
            "body_completion_evidence_ref": self.body_completion_evidence_ref,
        }


@dataclass(frozen=True, slots=True)
class DailySourceRecordAvailability:
    """收據持久化的單列可用小時與具名時間依據。"""

    stock_code: str
    market: str
    period: str
    source_version: str
    raw_source_sha256: str
    available_hour: datetime
    basis: str

    def __post_init__(self) -> None:
        for name in (
            "stock_code",
            "market",
            "period",
            "source_version",
            "raw_source_sha256",
        ):
            _require_text(getattr(self, name), name)
        object.__setattr__(
            self, "available_hour", _to_taipei(self.available_hour, "available_hour")
        )
        if self.available_hour != self.available_hour.replace(
            minute=0, second=0, microsecond=0
        ):
            raise DailySourceSnapshotError("available_hour 必須是台北整點")
        if self.basis not in {
            "successful_batch_completion_fallback",
            "successful_batch_completion_exact_hour_publication_guard",
            "official_timestamp_and_successful_batch_completion",
            "official_timestamp_and_successful_batch_completion_exact_hour_publication_guard",
        }:
            raise DailySourceSnapshotError("available_hour basis 不受支援")

    def matches(self, record: DailySourceSnapshotRecord) -> bool:
        return (
            self.stock_code == record.stock_code
            and self.market == record.market
            and self.period == record.period
            and self.source_version == record.source_version
            and self.raw_source_sha256 == record.raw_source_sha256
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "stock_code": self.stock_code,
            "market": self.market,
            "period": self.period,
            "source_version": self.source_version,
            "raw_source_sha256": self.raw_source_sha256,
            "available_hour": _datetime_text(self.available_hour),
            "basis": self.basis,
        }


@dataclass(frozen=True, slots=True)
class DailySourceSnapshot:
    """經 manifest、原始 bytes 與批次收據驗證的可讀快照。"""

    batch_id: str
    scope: DailySourceUseScope
    use_acceptance: DailySourceUseAcceptance
    source_batch_started_at: datetime
    first_persisted_at: datetime
    successful_batch_completion_clock_sample_at: datetime
    successful_batch_completed_at: datetime
    successful_batch_completion_basis: str
    raw_source_bytes: bytes
    raw_source_sha256: str
    records: tuple[DailySourceSnapshotRecord, ...]
    record_availability: tuple[DailySourceRecordAvailability, ...]
    validation: DailySourceBatchValidation
    manifest_sha256: str
    receipt_sha256: str
    transport_capture: DailySourceTransportCapture | None = None

    def __post_init__(self) -> None:
        _validate_batch_id(self.batch_id)
        if self.use_acceptance.scope != self.scope:
            raise DailySourceSnapshotError("用途接受範圍與快照來源範圍不符")
        _validate_supported_scope(self.scope)
        for name in (
            "source_batch_started_at",
            "first_persisted_at",
            "successful_batch_completion_clock_sample_at",
            "successful_batch_completed_at",
        ):
            object.__setattr__(self, name, _to_taipei(getattr(self, name), name))
        if self.source_batch_started_at > self.first_persisted_at:
            raise DailySourceSnapshotError("批次開始時間晚於首次保存時間")
        if self.use_acceptance.accepted_at > self.first_persisted_at:
            raise DailySourceSnapshotError("來源用途接受時間晚於首次保存時間")
        if self.first_persisted_at > self.successful_batch_completed_at:
            raise DailySourceSnapshotError("首次保存時間晚於成功批次完成時間")
        expected_completed_at, expected_completion_basis = _completion_clock_sample(
            self.successful_batch_completion_clock_sample_at
        )
        if self.successful_batch_completed_at != expected_completed_at:
            raise DailySourceSnapshotError("成功批次完成時間與完成時鐘樣本不符")
        if self.successful_batch_completion_basis != expected_completion_basis:
            raise DailySourceSnapshotError("成功批次完成時間 basis 不符")
        if _hour_bucket(self.first_persisted_at) != _hour_bucket(
            self.successful_batch_completion_clock_sample_at
        ):
            raise DailySourceSnapshotError("保存至批次完成跨越整點，快照不可發布")
        if not isinstance(self.validation, DailySourceBatchValidation):
            raise DailySourceSnapshotError("每日驗證收據型別錯誤")
        if not isinstance(self.records, tuple) or not all(
            isinstance(record, DailySourceSnapshotRecord) for record in self.records
        ):
            raise DailySourceSnapshotError("快照列必須是不可變記錄 tuple")
        if not isinstance(self.record_availability, tuple) or not all(
            isinstance(item, DailySourceRecordAvailability)
            for item in self.record_availability
        ):
            raise DailySourceSnapshotError("列可用性必須是不可變收據 tuple")
        if not isinstance(self.raw_source_bytes, bytes) or not self.raw_source_bytes:
            raise DailySourceSnapshotError("raw source bytes 不可為空")
        if len(self.raw_source_bytes) > MAX_DAILY_SOURCE_RAW_BYTES:
            raise DailySourceSnapshotError("raw source bytes 超過上限")
        digest = hashlib.sha256(self.raw_source_bytes).hexdigest()
        if self.raw_source_sha256 != digest:
            raise DailySourceSnapshotError("raw source bytes 與 SHA-256 不符")
        if not self.records:
            raise DailySourceSnapshotError("快照至少需要一筆資料列")
        if len(self.record_availability) != len(self.records):
            raise DailySourceSnapshotError("持久化 available_hour 數量與列數不符")
        if len(self.records) != self.validation.actual_record_count:
            raise DailySourceSnapshotError("快照列數與每日驗證收據不符")
        if self.validation.quality_status != "pass":
            raise DailySourceSnapshotError("每日批次品質驗證未通過")
        contains_official_clock = any(
            record.official_timestamp is not None for record in self.records
        )
        if contains_official_clock and (
            self.validation.official_timestamp_parse_check.status != "pass"
        ):
            raise DailySourceSnapshotError("official timestamp 缺少具名解析通過證據")
        if not contains_official_clock and (
            self.validation.official_timestamp_parse_check.status != "not_required"
        ):
            raise DailySourceSnapshotError("缺少 official timestamp 卻宣告解析通過")
        identities: set[tuple[str, str, str, str, str]] = set()
        for record in self.records:
            if record.market != self.scope.market or record.unit != self.scope.unit:
                raise DailySourceSnapshotError("快照列市場或單位與用途接受範圍不符")
            if record.raw_source_sha256 != self.raw_source_sha256:
                raise DailySourceSnapshotError("快照列原始雜湊與保存 bytes 不符")
            identity = (
                record.stock_code,
                record.market,
                record.period,
                record.source_version,
                record.raw_source_sha256,
            )
            if identity in identities:
                raise DailySourceSnapshotError("每日快照含重複來源列")
            identities.add(identity)
        expected_availability = tuple(
            _availability_for_record(record, self.successful_batch_completed_at)
            for record in self.records
        )
        if self.record_availability != expected_availability:
            raise DailySourceSnapshotError("receipt available_hour/basis 與固定政策重算不符")
        if not _SHA256_RE.fullmatch(self.manifest_sha256):
            raise DailySourceSnapshotError("manifest SHA-256 格式錯誤")
        if not _SHA256_RE.fullmatch(self.receipt_sha256):
            raise DailySourceSnapshotError("receipt SHA-256 格式錯誤")
        _validate_snapshot_inputs(
            scope=self.scope,
            use_acceptance=self.use_acceptance,
            source_batch_started_at=self.source_batch_started_at,
            raw_source_sha256=self.raw_source_sha256,
            records=self.records,
            validation=self.validation,
        )
        _validate_transport_capture_for_snapshot(
            transport_capture=self.transport_capture,
            use_acceptance=self.use_acceptance,
            source_batch_started_at=self.source_batch_started_at,
            first_persisted_at=self.first_persisted_at,
            successful_batch_completed_at=self.successful_batch_completed_at,
            raw_source_bytes=self.raw_source_bytes,
            raw_source_sha256=self.raw_source_sha256,
            records=self.records,
        )

    @property
    def payload_provenance(self) -> str:
        """明示 canonical payload 是否有可驗證的 HTTP 原件來源。"""

        return (
            "verified_http_response_body"
            if self.transport_capture is not None
            else "canonical_utf8_payload_only"
        )

    def find_record(
        self,
        *,
        stock_code: str,
        market: str,
        period: str,
        source_version: str,
        raw_source_sha256: str,
        unit: str,
    ) -> DailySourceSnapshotRecord | None:
        """只在每個來源識別欄位完全相符時回傳快照列。"""

        for record in self.records:
            if (
                record.stock_code == stock_code
                and record.market == market
                and record.period == period
                and record.source_version == source_version
                and record.raw_source_sha256 == raw_source_sha256
                and record.unit == unit
            ):
                return record
        return None

    def availability_for(
        self, record: DailySourceSnapshotRecord
    ) -> tuple[datetime, str]:
        """回傳台北時區的小時可得時間與具名時間依據。"""

        if record not in self.records:
            raise DailySourceSnapshotError("來源列不屬於此快照")
        for persisted in self.record_availability:
            if persisted.matches(record):
                return persisted.available_hour, persisted.basis
        raise DailySourceSnapshotError("來源列缺少持久化 available_hour/basis")

    def is_available_by(self, record: DailySourceSnapshotRecord, cutoff: datetime) -> bool:
        """以原始精確決策時間檢查可得性，不向上取整決策 cutoff。"""

        cutoff_taipei = _to_taipei(cutoff, "decision_cutoff")
        if self.first_persisted_at > cutoff_taipei:
            return False
        available_hour, _ = self.availability_for(record)
        return available_hour <= cutoff_taipei


class DailySourceSnapshotReadPort(Protocol):
    """Recommendation reader 可選用的窄型來源快照讀取 port。"""

    def read_snapshot(
        self,
        batch_id: str,
        *,
        expected_scope: DailySourceUseScope,
    ) -> DailySourceSnapshot: ...


class DailySourceSnapshotFileReader:
    """只讀 caller 明確提供 root 下的不可變每日來源快照。"""

    def __init__(
        self,
        root: Path | str,
        *,
        trusted_acceptance: DailySourceUseAcceptance | None = None,
    ) -> None:
        self.root = _require_root(root)
        self.trusted_acceptance = trusted_acceptance

    def read_snapshot(
        self,
        batch_id: str,
        *,
        expected_scope: DailySourceUseScope,
    ) -> DailySourceSnapshot:
        return read_daily_source_snapshot(
            self.root,
            batch_id,
            expected_scope=expected_scope,
            trusted_acceptance=self.trusted_acceptance,
        )


def write_daily_source_snapshot(
    root: Path | str,
    *,
    batch_id: str,
    scope: DailySourceUseScope,
    use_acceptance: DailySourceUseAcceptance,
    source_batch_started_at: datetime,
    raw_source_bytes: bytes,
    records: Sequence[DailySourceSnapshotRecord],
    validation: DailySourceBatchValidation,
    transport_capture: DailySourceTransportCapture | None = None,
    clock: Callable[[], datetime] | None = None,
    quarantine_root: Path | str | None = None,
    check_cancel: Callable[[], None] | None = None,
) -> Path:
    """先 durable 保存暫存原件與收據，再受小時守衛後原子發布快照。

    合作式取消在保存前及最後 rename 前觀測；取消 callback 的例外由
    caller 保留與隔離。發布成功後不再觀測取消，以免錯報已發布的批次。
    """

    base = _require_root(root)
    _validate_batch_id(batch_id)
    if use_acceptance.scope != scope:
        raise DailySourceSnapshotError("用途接受範圍與快照來源範圍不符")
    started = _to_taipei(source_batch_started_at, "source_batch_started_at")
    raw_bytes = raw_source_bytes
    if not isinstance(raw_bytes, bytes) or not raw_bytes:
        raise DailySourceSnapshotError("raw source bytes 不可為空")
    if len(raw_bytes) > MAX_DAILY_SOURCE_RAW_BYTES:
        raise DailySourceSnapshotError("raw source bytes 超過上限")
    if not isinstance(validation, DailySourceBatchValidation):
        raise DailySourceSnapshotError("validation 必須是每日批次驗證收據")
    if any(not isinstance(record, DailySourceSnapshotRecord) for record in records):
        raise DailySourceSnapshotError("records 含非快照記錄型別")
    frozen_records = tuple(
        sorted(
            records,
            key=lambda item: (
                item.stock_code,
                item.market,
                item.period,
                item.source_version,
                item.raw_source_sha256,
            ),
        )
    )
    if len(frozen_records) != validation.actual_record_count:
        raise DailySourceSnapshotError("每日批次列數與驗證收據不符")
    if check_cancel is not None:
        check_cancel()
    raw_sha256 = hashlib.sha256(raw_bytes).hexdigest()
    try:
        _validate_snapshot_inputs(
            scope=scope,
            use_acceptance=use_acceptance,
            source_batch_started_at=started,
            raw_source_sha256=raw_sha256,
            records=frozen_records,
            validation=validation,
        )
        _validate_transport_capture_for_snapshot(
            transport_capture=transport_capture,
            use_acceptance=use_acceptance,
            source_batch_started_at=started,
            first_persisted_at=None,
            successful_batch_completed_at=None,
            raw_source_bytes=raw_bytes,
            raw_source_sha256=raw_sha256,
            records=frozen_records,
        )
    except DailySourceSnapshotError as exc:
        if quarantine_root is not None:
            _quarantine_publish_failure(
                base=base,
                quarantine_root=quarantine_root,
                batch_id=batch_id,
                raw_source_bytes=raw_bytes,
                failure_reason_code=f"snapshot_validation_rejected:{exc}",
                scope=scope,
                source_batch_started_at=started,
                validation=validation,
                primary_error=exc,
                transport_capture=(
                    transport_capture
                    if isinstance(transport_capture, DailySourceTransportCapture)
                    else None
                ),
            )
        raise
    get_clock = clock or (lambda: datetime.now(_TAIPEI))

    manifest_payload: dict[str, object] = {
        "schema_version": DAILY_SOURCE_SNAPSHOT_MANIFEST_SCHEMA,
        "contract_version": DAILY_SOURCE_SNAPSHOT_SCHEMA,
        "batch_id": batch_id,
        "scope": scope.to_dict(),
        "use_acceptance": use_acceptance.to_dict(),
        "source_batch_started_at": _datetime_text(started),
        "raw_source_sha256": raw_sha256,
        "raw_source_bytes_base64": base64.b64encode(raw_bytes).decode("ascii"),
        "records": [record.to_dict() for record in frozen_records],
        "transport_capture": (
            transport_capture.to_dict() if transport_capture is not None else None
        ),
    }
    manifest_bytes = _canonical_json_bytes(manifest_payload)
    if len(manifest_bytes) > MAX_DAILY_SOURCE_MANIFEST_BYTES:
        raise DailySourceSnapshotError("manifest 超過大小上限")
    manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()

    batch_root = _batch_root(base, batch_id)
    staging_parent = base / ".daily_source_snapshot_staging"
    if staging_parent.is_symlink():
        raise DailySourceSnapshotError("快照 staging root 不可是符號連結")
    staging_parent.mkdir(parents=True, exist_ok=True)
    if staging_parent.resolve(strict=True).parent != base:
        raise DailySourceSnapshotError("快照 staging root 超出 caller 提供的 root")
    staging_root = staging_parent / batch_id
    if batch_root.exists() or staging_root.exists():
        raise DailySourceSnapshotError("不可變快照 batch_id 已存在或仍在保存")
    try:
        staging_root.mkdir()
    except FileExistsError as exc:
        raise DailySourceSnapshotError("不可變快照 batch_id 已存在或仍在保存") from exc

    _write_create_only(
        staging_root / DAILY_SOURCE_SNAPSHOT_MANIFEST_NAME, manifest_bytes
    )
    first_persisted_at = _to_taipei(get_clock(), "first_persisted_at")
    if started > first_persisted_at:
        raise DailySourceSnapshotError("批次開始時間晚於首次保存時間")
    if use_acceptance.accepted_at > first_persisted_at:
        raise DailySourceSnapshotError("來源用途接受時間晚於首次保存時間")

    pending_payload: dict[str, object] = {
        "schema_version": DAILY_SOURCE_SNAPSHOT_RECEIPT_SCHEMA,
        "contract_version": DAILY_SOURCE_SNAPSHOT_SCHEMA,
        "batch_id": batch_id,
        "manifest_sha256": manifest_sha256,
        "stage_status": "prepared",
        "first_persisted_at": _datetime_text(first_persisted_at),
        "validation": validation.to_dict(),
    }
    _write_create_only(
        staging_root / ".receipt.pending.json",
        _canonical_json_bytes(pending_payload),
    )
    completion_clock_sample_at = _to_taipei(
        get_clock(), "successful_batch_completion_clock_sample_at"
    )
    if completion_clock_sample_at < first_persisted_at:
        raise DailySourceSnapshotError("批次完成時鐘早於首次持久化時鐘")
    if _hour_bucket(first_persisted_at) != _hour_bucket(completion_clock_sample_at):
        rejection = DailySourceSnapshotError("批次持久化跨越整點，已隔離且不發布成功收據")
        _quarantine_publish_failure(
            base=base,
            quarantine_root=quarantine_root,
            batch_id=batch_id,
            raw_source_bytes=raw_bytes,
            failure_reason_code="batch_persistence_crossed_hour_boundary",
            scope=scope,
            source_batch_started_at=started,
            validation=validation,
            primary_error=rejection,
            transport_capture=transport_capture,
        )
        raise rejection
    completed_at, completion_basis = _completion_clock_sample(
        completion_clock_sample_at
    )
    if completed_at < first_persisted_at:
        raise DailySourceSnapshotError("首次保存時間晚於成功批次完成時間")
    try:
        _validate_transport_capture_for_snapshot(
            transport_capture=transport_capture,
            use_acceptance=use_acceptance,
            source_batch_started_at=started,
            first_persisted_at=first_persisted_at,
            successful_batch_completed_at=completed_at,
            raw_source_bytes=raw_bytes,
            raw_source_sha256=raw_sha256,
            records=frozen_records,
        )
    except DailySourceSnapshotError as exc:
        _quarantine_publish_failure(
            base=base,
            quarantine_root=quarantine_root,
            batch_id=batch_id,
            raw_source_bytes=raw_bytes,
            failure_reason_code=f"transport_capture_rejected:{exc}",
            scope=scope,
            source_batch_started_at=started,
            validation=validation,
            primary_error=exc,
            transport_capture=transport_capture,
        )
        raise
    record_availability = tuple(
        _availability_for_record(record, completed_at) for record in frozen_records
    )
    receipt_payload: dict[str, object] = {
        "schema_version": DAILY_SOURCE_SNAPSHOT_RECEIPT_SCHEMA,
        "contract_version": DAILY_SOURCE_SNAPSHOT_SCHEMA,
        "batch_id": batch_id,
        "manifest_sha256": manifest_sha256,
        "batch_status": "success",
        "quality_status": validation.quality_status,
        "first_persisted_at": _datetime_text(first_persisted_at),
        "successful_batch_completion_clock_sample_at": _datetime_text(
            completion_clock_sample_at
        ),
        "successful_batch_completed_at": _datetime_text(completed_at),
        "successful_batch_completion_basis": completion_basis,
        "record_availability": [item.to_dict() for item in record_availability],
        "validation": validation.to_dict(),
    }
    receipt_payload["receipt_sha256"] = hashlib.sha256(
        _canonical_json_bytes(receipt_payload)
    ).hexdigest()
    receipt_bytes = _canonical_json_bytes(receipt_payload)
    if len(receipt_bytes) > MAX_DAILY_SOURCE_RECEIPT_BYTES:
        rejection = DailySourceSnapshotError("receipt 超過大小上限，已隔離且不發布")
        _quarantine_publish_failure(
            base=base,
            quarantine_root=quarantine_root,
            batch_id=batch_id,
            raw_source_bytes=raw_bytes,
            failure_reason_code="snapshot_receipt_exceeds_size_limit",
            scope=scope,
            source_batch_started_at=started,
            validation=validation,
            primary_error=rejection,
            transport_capture=transport_capture,
        )
        raise rejection
    _write_create_only(staging_root / DAILY_SOURCE_SNAPSHOT_RECEIPT_NAME, receipt_bytes)
    receipt_persisted_at = _to_taipei(
        get_clock(), "successful_receipt_persisted_at"
    )
    publish_hour = _batch_publish_guard_hour(completed_at)
    if receipt_persisted_at > publish_hour:
        rejection = DailySourceSnapshotError("成功收據晚於可用小時，已隔離且不發布")
        _quarantine_publish_failure(
            base=base,
            quarantine_root=quarantine_root,
            batch_id=batch_id,
            raw_source_bytes=raw_bytes,
            failure_reason_code="successful_receipt_persisted_after_available_hour",
            scope=scope,
            source_batch_started_at=started,
            validation=validation,
            primary_error=rejection,
            transport_capture=transport_capture,
        )
        raise rejection
    if check_cancel is not None:
        check_cancel()
    if batch_root.exists():
        raise DailySourceSnapshotError("不可變快照 batch_id 已存在，不可發布")
    try:
        os.rename(staging_root, batch_root)
    except FileExistsError as exc:
        raise DailySourceSnapshotError("不可變快照 batch_id 已存在，不可發布") from exc
    published_at = _to_taipei(get_clock(), "successful_batch_published_at")
    if published_at > publish_hour:
        rejection = DailySourceSnapshotError("快照發布跨越可用小時，已隔離且不授成功")
        _quarantine_publish_failure(
            base=base,
            quarantine_root=quarantine_root,
            batch_id=batch_id,
            raw_source_bytes=raw_bytes,
            failure_reason_code="snapshot_published_after_available_hour",
            scope=scope,
            source_batch_started_at=started,
            validation=validation,
            primary_error=rejection,
            transport_capture=transport_capture,
        )
        isolated_root = base / ".daily_source_snapshot_isolated"
        try:
            if isolated_root.is_symlink():
                raise DailySourceSnapshotError("發布失敗快照隔離 root 不可是符號連結")
            isolated_root.mkdir(exist_ok=True)
            if isolated_root.resolve(strict=True).parent != base:
                raise DailySourceSnapshotError("發布失敗快照隔離 root 超出 caller root")
            isolated_path = isolated_root / batch_id
            if isolated_path.exists() or isolated_path.is_symlink():
                raise DailySourceSnapshotError("發布失敗快照隔離路徑已存在")
            os.rename(batch_root, isolated_path)
        except (DailySourceSnapshotError, OSError) as isolation_error:
            rejection.add_note(f"snapshot_isolation_failed:{isolation_error}")
        # pending 收據仍在；即使搬移失敗，公開 reader 也不會授予成功。
        raise rejection
    # 僅在發布後時鐘及期限核驗通過後解除 pending barrier。若 clock/read/unlink
    # 失敗，留下 barrier，reader 拒絕已 rename 但尚未成功接受的 batch。
    (batch_root / ".receipt.pending.json").unlink()
    return batch_root


def write_daily_source_quarantine_candidate(
    root: Path | str,
    *,
    batch_id: str,
    raw_source_bytes: bytes,
    failure_reason_code: str,
    scope: DailySourceUseScope | None = None,
    source_batch_started_at: datetime | None = None,
    validation: DailySourceBatchValidation | None = None,
    failed_partition_ids: Sequence[str] = (),
    transport_capture: DailySourceTransportCapture | None = None,
) -> Path:
    """create-only 隔離失敗原件與理由；此格式沒有成功 reader 或可用小時。

    完整 HTTP capture 可一併保存；其完整 transport 不代表報表品質通過。
    canonical payload 與 HTTP 原件即使不相等也留下兩者及具名比對結果，
    不將隔離證據當作成功快照。截斷 response 不得偽造完整 capture DTO。
    """

    base = _require_root(root)
    _validate_batch_id(batch_id)
    reason = _require_text(failure_reason_code, "failure_reason_code")
    if not isinstance(raw_source_bytes, bytes) or not raw_source_bytes:
        raise DailySourceSnapshotError("quarantine raw source bytes 不可為空")
    if len(raw_source_bytes) > MAX_DAILY_SOURCE_RAW_BYTES:
        raise DailySourceSnapshotError("quarantine raw source bytes 超過上限")
    failed_partitions = _unique_texts_preserving_order(
        tuple(failed_partition_ids), "failed_partition_ids"
    )
    if validation is not None and not isinstance(validation, DailySourceBatchValidation):
        raise DailySourceSnapshotError("quarantine validation 型別錯誤")
    if transport_capture is not None:
        if not isinstance(transport_capture, DailySourceTransportCapture):
            raise DailySourceSnapshotError("quarantine transport capture 型別錯誤")
        # 重新解析與核對 bytes/hash/EOF/encoding；不信任手動改寫 frozen DTO。
        transport_capture = _transport_capture_from_dict(transport_capture.to_dict())
    started_text = (
        _datetime_text(_to_taipei(source_batch_started_at, "source_batch_started_at"))
        if source_batch_started_at is not None
        else None
    )
    payload: dict[str, object] = {
        "schema_version": (
            DAILY_SOURCE_SNAPSHOT_QUARANTINE_TRANSPORT_SCHEMA
            if transport_capture is not None
            else DAILY_SOURCE_SNAPSHOT_QUARANTINE_SCHEMA
        ),
        "contract_version": DAILY_SOURCE_SNAPSHOT_SCHEMA,
        "batch_id": batch_id,
        "failure_reason_code": reason,
        "source_batch_started_at": started_text,
        "scope": scope.to_dict() if scope is not None else None,
        "raw_source_sha256": hashlib.sha256(raw_source_bytes).hexdigest(),
        "raw_source_bytes_base64": base64.b64encode(raw_source_bytes).decode("ascii"),
        "failed_partition_ids": list(failed_partitions),
        "validation": validation.to_dict() if validation is not None else None,
    }
    if transport_capture is not None:
        payload["transport_capture"] = transport_capture.to_dict()
        payload["canonical_payload_matches_transport"] = (
            raw_source_bytes == transport_capture.canonical_source_bytes
        )
        payload["quarantine_sha256"] = hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()
    encoded = _canonical_json_bytes(payload)
    if len(encoded) > MAX_DAILY_SOURCE_MANIFEST_BYTES:
        raise DailySourceSnapshotError("quarantine candidate 超過大小上限")
    quarantine_dir = base / "quarantine"
    if quarantine_dir.is_symlink():
        raise DailySourceSnapshotError("quarantine root 不可是符號連結")
    quarantine_dir.mkdir(parents=True, exist_ok=True)
    if quarantine_dir.resolve(strict=True).parent != base:
        raise DailySourceSnapshotError("quarantine root 超出 caller 提供的 root")
    candidate_path = quarantine_dir / f"{batch_id}.json"
    _write_create_only(candidate_path, encoded)
    return candidate_path


def read_daily_source_snapshot(
    root: Path | str,
    batch_id: str,
    *,
    expected_scope: DailySourceUseScope,
    trusted_acceptance: DailySourceUseAcceptance | None = None,
) -> DailySourceSnapshot:
    """從公開 manifest/receipt 格式讀回並重新驗證每日快照。"""

    if trusted_acceptance is None:
        raise DailySourceSnapshotError("reader 必須提供可信來源用途接受錨點")
    if not isinstance(trusted_acceptance, DailySourceUseAcceptance):
        raise DailySourceSnapshotError("reader 可信來源用途接受錨點型別錯誤")
    base = _require_root(root)
    _validate_batch_id(batch_id)
    batch_root = _batch_root(base, batch_id)
    _require_publication_not_pending(batch_root)
    manifest_path = batch_root / DAILY_SOURCE_SNAPSHOT_MANIFEST_NAME
    receipt_path = batch_root / DAILY_SOURCE_SNAPSHOT_RECEIPT_NAME
    if manifest_path.is_symlink() or receipt_path.is_symlink():
        raise DailySourceSnapshotError("快照檔不可是符號連結")
    try:
        manifest_bytes = manifest_path.read_bytes()
        receipt_bytes = receipt_path.read_bytes()
    except OSError as exc:
        raise DailySourceSnapshotError("每日快照 manifest 或成功收據不存在") from exc
    if len(manifest_bytes) > MAX_DAILY_SOURCE_MANIFEST_BYTES:
        raise DailySourceSnapshotError("manifest 超過大小上限")
    if len(receipt_bytes) > MAX_DAILY_SOURCE_RECEIPT_BYTES:
        raise DailySourceSnapshotError("receipt 超過大小上限")

    manifest = _load_canonical_object(manifest_bytes, "manifest")
    receipt = _load_canonical_object(receipt_bytes, "receipt")
    manifest_schema = manifest.get("schema_version")
    manifest_v1_keys = {
        "schema_version",
        "contract_version",
        "batch_id",
        "scope",
        "use_acceptance",
        "source_batch_started_at",
        "raw_source_sha256",
        "raw_source_bytes_base64",
        "records",
    }
    if manifest_schema == DAILY_SOURCE_SNAPSHOT_MANIFEST_SCHEMA_V1:
        expected_manifest_keys = manifest_v1_keys
        if len(manifest_bytes) > MAX_DAILY_SOURCE_MANIFEST_V1_BYTES:
            raise DailySourceSnapshotError("manifest v1 超過既有大小上限")
    elif manifest_schema == DAILY_SOURCE_SNAPSHOT_MANIFEST_SCHEMA:
        expected_manifest_keys = manifest_v1_keys | {"transport_capture"}
    else:
        raise DailySourceSnapshotError("每日快照 manifest schema version 不支援")
    if set(manifest) != expected_manifest_keys:
        raise DailySourceSnapshotError("manifest 欄位與版本契約不符")
    if set(receipt) != {
        "schema_version",
        "contract_version",
        "batch_id",
        "manifest_sha256",
        "batch_status",
        "quality_status",
        "first_persisted_at",
        "successful_batch_completion_clock_sample_at",
        "successful_batch_completed_at",
        "successful_batch_completion_basis",
        "record_availability",
        "validation",
        "receipt_sha256",
    }:
        raise DailySourceSnapshotError("receipt 欄位與版本契約不符")
    if (
        manifest.get("contract_version") != DAILY_SOURCE_SNAPSHOT_SCHEMA
        or receipt.get("schema_version") != DAILY_SOURCE_SNAPSHOT_RECEIPT_SCHEMA
        or receipt.get("contract_version") != DAILY_SOURCE_SNAPSHOT_SCHEMA
    ):
        raise DailySourceSnapshotError("每日快照 schema version 不支援")
    if manifest.get("batch_id") != batch_id or receipt.get("batch_id") != batch_id:
        raise DailySourceSnapshotError("manifest 或 receipt batch_id 不符")
    manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    if receipt.get("manifest_sha256") != manifest_sha256:
        raise DailySourceSnapshotError("receipt 未綁定目前 manifest")
    if receipt.get("batch_status") != "success":
        raise DailySourceSnapshotError("每日批次未成功")
    if receipt.get("quality_status") != "pass":
        raise DailySourceSnapshotError("每日批次品質驗證未通過")
    receipt_without_hash = dict(receipt)
    supplied_receipt_sha256 = receipt_without_hash.pop("receipt_sha256")
    receipt_sha256 = hashlib.sha256(
        _canonical_json_bytes(receipt_without_hash)
    ).hexdigest()
    if supplied_receipt_sha256 != receipt_sha256:
        raise DailySourceSnapshotError("receipt SHA-256 不符")

    scope = _scope_from_dict(manifest.get("scope"))
    if scope != expected_scope:
        raise DailySourceSnapshotError("快照來源用途範圍與呼叫端預期不符")
    acceptance = _acceptance_from_dict(manifest.get("use_acceptance"))
    if acceptance.scope != scope:
        raise DailySourceSnapshotError("一次性用途接受紀錄與 manifest 範圍不符")
    if trusted_acceptance.scope != expected_scope or acceptance != trusted_acceptance:
        raise DailySourceSnapshotError("manifest 用途接受紀錄與 caller 可信錨點不符")
    started = _parse_datetime(manifest.get("source_batch_started_at"), "source_batch_started_at")
    first_persisted = _parse_datetime(
        receipt.get("first_persisted_at"), "first_persisted_at"
    )
    completion_clock_sample = _parse_datetime(
        receipt.get("successful_batch_completion_clock_sample_at"),
        "successful_batch_completion_clock_sample_at",
    )
    completed = _parse_datetime(
        receipt.get("successful_batch_completed_at"), "successful_batch_completed_at"
    )
    completion_basis = _require_text(
        receipt.get("successful_batch_completion_basis"),
        "successful_batch_completion_basis",
    )
    raw_sha256 = _require_hash(manifest.get("raw_source_sha256"), "raw_source_sha256")
    raw_bytes = _decode_raw_bytes(manifest.get("raw_source_bytes_base64"))
    records_value = manifest.get("records")
    if not isinstance(records_value, list) or not records_value:
        raise DailySourceSnapshotError("manifest records 不可為空")
    if len(records_value) > MAX_DAILY_SOURCE_RECORDS:
        raise DailySourceSnapshotError("manifest records 超過上限")
    records = tuple(_record_from_dict(value) for value in records_value)
    transport_capture_value = manifest.get("transport_capture")
    if transport_capture_value is None:
        transport_capture = None
    else:
        transport_capture = _transport_capture_from_dict(transport_capture_value)
    validation = _validation_from_dict(receipt.get("validation"))
    availability_value = receipt.get("record_availability")
    if not isinstance(availability_value, list):
        raise DailySourceSnapshotError("receipt record_availability 格式錯誤")
    record_availability = tuple(
        _availability_from_dict(value) for value in availability_value
    )
    snapshot = DailySourceSnapshot(
        batch_id=batch_id,
        scope=scope,
        use_acceptance=acceptance,
        source_batch_started_at=started,
        first_persisted_at=first_persisted,
        successful_batch_completion_clock_sample_at=completion_clock_sample,
        successful_batch_completed_at=completed,
        successful_batch_completion_basis=completion_basis,
        raw_source_bytes=raw_bytes,
        raw_source_sha256=raw_sha256,
        records=records,
        record_availability=record_availability,
        validation=validation,
        manifest_sha256=manifest_sha256,
        receipt_sha256=receipt_sha256,
        transport_capture=transport_capture,
    )
    _require_publication_not_pending(batch_root)
    return snapshot


def _require_publication_not_pending(batch_root: Path) -> None:
    try:
        (batch_root / ".receipt.pending.json").lstat()
    except FileNotFoundError:
        return
    except OSError as exc:
        raise DailySourceSnapshotError("snapshot publication 狀態無法核驗") from exc
    raise DailySourceSnapshotError("snapshot publication 尚未完成或已拒絕")


def _quarantine_publish_failure(
    *,
    base: Path,
    quarantine_root: Path | str | None,
    batch_id: str,
    raw_source_bytes: bytes,
    failure_reason_code: str,
    scope: DailySourceUseScope,
    source_batch_started_at: datetime,
    validation: DailySourceBatchValidation,
    primary_error: DailySourceSnapshotError,
    transport_capture: DailySourceTransportCapture | None = None,
) -> None:
    try:
        write_daily_source_quarantine_candidate(
            quarantine_root if quarantine_root is not None else base,
            batch_id=batch_id,
            raw_source_bytes=raw_source_bytes,
            failure_reason_code=failure_reason_code,
            scope=scope,
            source_batch_started_at=source_batch_started_at,
            validation=validation,
            transport_capture=transport_capture,
        )
    except (DailySourceSnapshotError, OSError) as secondary_error:
        # 封存失敗不能取代主拒絕，也不能阻止發布後的失敗快照搬到隔離區。
        primary_error.add_note(f"quarantine_preservation_failed:{secondary_error}")
        if transport_capture is not None:
            try:
                # 壞 transport DTO 不入封套，仍保留可用的 caller canonical 原件。
                write_daily_source_quarantine_candidate(
                    quarantine_root if quarantine_root is not None else base,
                    batch_id=batch_id, raw_source_bytes=raw_source_bytes,
                    failure_reason_code=f"{failure_reason_code};transport_capture_not_archived",
                    scope=scope, source_batch_started_at=source_batch_started_at,
                    validation=validation,
                )
            except (DailySourceSnapshotError, OSError) as fallback_error:
                primary_error.add_note(f"canonical_quarantine_preservation_failed:{fallback_error}")


def _hour_bucket(value: datetime) -> datetime:
    local = _to_taipei(value, "hour bucket timestamp")
    return local.replace(minute=0, second=0, microsecond=0)


def _completion_clock_sample(value: datetime) -> tuple[datetime, str]:
    sample = _to_taipei(value, "successful_batch_completion_clock_sample_at")
    return sample, "durable_temporary_receipt_closed"


def _batch_publish_guard_hour(successful_batch_completed_at: datetime) -> datetime:
    completed = _to_taipei(
        successful_batch_completed_at, "successful_batch_completed_at"
    )
    publish_hour = _ceil_hour(completed)
    if completed == _hour_bucket(completed):
        return publish_hour + timedelta(hours=1)
    return publish_hour


def _availability_for_record(
    record: DailySourceSnapshotRecord,
    successful_batch_completed_at: datetime,
) -> DailySourceRecordAvailability:
    completed = _to_taipei(
        successful_batch_completed_at, "successful_batch_completed_at"
    )
    batch_hour = _batch_publish_guard_hour(completed)
    exact_boundary_guard = completed == _hour_bucket(completed)
    if record.official_timestamp is None:
        return DailySourceRecordAvailability(
            stock_code=record.stock_code,
            market=record.market,
            period=record.period,
            source_version=record.source_version,
            raw_source_sha256=record.raw_source_sha256,
            available_hour=batch_hour,
            basis=(
                "successful_batch_completion_exact_hour_publication_guard"
                if exact_boundary_guard
                else "successful_batch_completion_fallback"
            ),
        )
    return DailySourceRecordAvailability(
        stock_code=record.stock_code,
        market=record.market,
        period=record.period,
        source_version=record.source_version,
        raw_source_sha256=record.raw_source_sha256,
        available_hour=max(_ceil_hour(record.official_timestamp), batch_hour),
        basis=(
            "official_timestamp_and_successful_batch_completion_exact_hour_publication_guard"
            if exact_boundary_guard
            else "official_timestamp_and_successful_batch_completion"
        ),
    )


def _availability_from_dict(value: object) -> DailySourceRecordAvailability:
    if not isinstance(value, dict) or set(value) != {
        "stock_code",
        "market",
        "period",
        "source_version",
        "raw_source_sha256",
        "available_hour",
        "basis",
    }:
        raise DailySourceSnapshotError("receipt 單列 available_hour 欄位錯誤")
    return DailySourceRecordAvailability(
        stock_code=_require_text(value.get("stock_code"), "stock_code"),
        market=_require_text(value.get("market"), "market"),
        period=_require_text(value.get("period"), "period"),
        source_version=_require_text(value.get("source_version"), "source_version"),
        raw_source_sha256=_require_hash(
            value.get("raw_source_sha256"), "raw_source_sha256"
        ),
        available_hour=_parse_datetime(value.get("available_hour"), "available_hour"),
        basis=_require_text(value.get("basis"), "availability_basis"),
    )


def _transport_capture_from_dict(value: object) -> DailySourceTransportCapture:
    if not isinstance(value, dict) or set(value) != {
        "raw_response_bytes_base64",
        "official_source_url",
        "response_status",
        "content_type",
        "declared_decoding_encoding",
        "decoding_basis",
        "html_meta_charset_original_text",
        "body_completed_at",
        "transport_sha256",
        "response_body_complete",
        "received_body_bytes",
        "content_length_original_text",
        "body_completion_evidence_ref",
    }:
        raise DailySourceSnapshotError("transport_capture 欄位與版本契約不符")
    meta_charset = value.get("html_meta_charset_original_text")
    if meta_charset is not None and not isinstance(meta_charset, str):
        raise DailySourceSnapshotError("HTML meta charset 原文型別錯誤")
    content_length_original_text = value.get("content_length_original_text")
    if content_length_original_text is not None and not isinstance(
        content_length_original_text, str
    ):
        raise DailySourceSnapshotError("Content-Length 原文型別錯誤")
    response_status = value.get("response_status")
    if type(response_status) is not int:
        raise DailySourceSnapshotError("transport HTTP response status 型別錯誤")
    response_body_complete = value.get("response_body_complete")
    if type(response_body_complete) is not bool:
        raise DailySourceSnapshotError("response_body_complete 型別錯誤")
    received_body_bytes = value.get("received_body_bytes")
    if type(received_body_bytes) is not int:
        raise DailySourceSnapshotError("received_body_bytes 必須是非 bool 整數")
    return DailySourceTransportCapture(
        raw_response_bytes=_decode_transport_bytes(
            value.get("raw_response_bytes_base64")
        ),
        official_source_url=_require_text(
            value.get("official_source_url"), "official_source_url"
        ),
        response_status=response_status,
        content_type=_require_text(value.get("content_type"), "content_type"),
        declared_decoding_encoding=_require_text(
            value.get("declared_decoding_encoding"),
            "declared_decoding_encoding",
        ),
        decoding_basis=_require_text(value.get("decoding_basis"), "decoding_basis"),
        body_completed_at=_parse_datetime(
            value.get("body_completed_at"), "transport body_completed_at"
        ),
        transport_sha256=_require_hash(
            value.get("transport_sha256"), "transport_sha256"
        ),
        response_body_complete=response_body_complete,
        received_body_bytes=received_body_bytes,
        content_length_original_text=content_length_original_text,
        body_completion_evidence_ref=_require_text(
            value.get("body_completion_evidence_ref"),
            "body_completion_evidence_ref",
        ),
        html_meta_charset_original_text=meta_charset,
    )


def _validate_transport_capture_for_snapshot(
    *,
    transport_capture: DailySourceTransportCapture | None,
    use_acceptance: DailySourceUseAcceptance,
    source_batch_started_at: datetime,
    first_persisted_at: datetime | None,
    successful_batch_completed_at: datetime | None,
    raw_source_bytes: bytes,
    raw_source_sha256: str,
    records: tuple[DailySourceSnapshotRecord, ...],
) -> None:
    if transport_capture is None:
        return
    if not isinstance(transport_capture, DailySourceTransportCapture):
        raise DailySourceSnapshotError("transport_capture 型別錯誤")
    _validate_transport_source_url(transport_capture, use_acceptance)
    if transport_capture.body_completed_at < _to_taipei(
        source_batch_started_at, "source_batch_started_at"
    ):
        raise DailySourceSnapshotError("transport body 完成時間早於批次開始")
    if first_persisted_at is not None and transport_capture.body_completed_at > _to_taipei(
        first_persisted_at, "first_persisted_at"
    ):
        raise DailySourceSnapshotError("transport body 完成時間晚於首次保存")
    if successful_batch_completed_at is not None and (
        transport_capture.body_completed_at
        > _to_taipei(successful_batch_completed_at, "successful_batch_completed_at")
    ):
        raise DailySourceSnapshotError("transport body 完成時間晚於成功批次完成")
    canonical_bytes = transport_capture.canonical_source_bytes
    if canonical_bytes != raw_source_bytes:
        raise DailySourceSnapshotError(
            "transport strict-decoded UTF-8 bytes 與 canonical source bytes 不符"
        )
    if hashlib.sha256(canonical_bytes).hexdigest() != raw_source_sha256:
        raise DailySourceSnapshotError("canonical source bytes 與既有 source SHA-256 不符")
    for record in records:
        source_body_clock = _mops_v2_body_completed_at(record)
        if source_body_clock != transport_capture.body_completed_at:
            raise DailySourceSnapshotError(
                "MOPS v2 body_completed_at 與 transport body 完成時間不符"
            )


def _validate_transport_source_url(
    transport_capture: DailySourceTransportCapture,
    use_acceptance: DailySourceUseAcceptance,
) -> None:
    captured_url = _validate_https_url(
        transport_capture.official_source_url,
        "official_source_url",
    )
    accepted_urls: set[str] = {
        _validate_https_url(
            use_acceptance.official_source_endpoint,
            "official_source_endpoint",
        )
    }
    for chain_item in use_acceptance.document_chain:
        if not chain_item.casefold().startswith("https://"):
            continue
        accepted_urls.add(_validate_https_url(chain_item, "document_chain HTTPS URL"))
    if captured_url not in accepted_urls:
        raise DailySourceSnapshotError(
            "transport URL 未精確列於可信用途接受 endpoint/document chain"
        )


def _mops_v2_body_completed_at(record: DailySourceSnapshotRecord) -> datetime:
    match = re.fullmatch(
        r"mops-static-snapshot\.v2:(twse|tpex):(\d{4}-\d{2}):"
        r"body_completed_at:(.+):sha256:([0-9a-f]{64})",
        record.source_version,
    )
    if match is None:
        raise DailySourceSnapshotError(
            "transport capture 需要含 body_completed_at 的 MOPS v2 source_version"
        )
    try:
        parsed = datetime.fromisoformat(match.group(3).replace("Z", "+00:00"))
    except ValueError as exc:
        raise DailySourceSnapshotError("MOPS v2 body_completed_at 格式錯誤") from exc
    return _to_taipei(parsed, "MOPS v2 body_completed_at")


def _validate_snapshot_inputs(
    *,
    scope: DailySourceUseScope,
    use_acceptance: DailySourceUseAcceptance,
    source_batch_started_at: datetime,
    raw_source_sha256: str,
    records: tuple[DailySourceSnapshotRecord, ...],
    validation: DailySourceBatchValidation,
) -> None:
    _validate_supported_scope(scope)
    if use_acceptance.scope != scope:
        raise DailySourceSnapshotError("用途接受範圍與快照來源範圍不符")
    if not _SHA256_RE.fullmatch(raw_source_sha256):
        raise DailySourceSnapshotError("raw source SHA-256 格式錯誤")
    if not records or len(records) != validation.actual_record_count:
        raise DailySourceSnapshotError("快照資料列與每日驗證收據不符")
    if validation.expected_record_count != len(records):
        raise DailySourceSnapshotError("每日批次不是完整資料列集合")
    if validation.quality_status != "pass":
        raise DailySourceSnapshotError("每日批次品質驗證未通過")
    contains_official_clock = any(record.official_timestamp is not None for record in records)
    if contains_official_clock and validation.official_timestamp_parse_check.status != "pass":
        raise DailySourceSnapshotError("official timestamp 缺少具名解析通過證據")
    if contains_official_clock and (
        validation.official_timestamp_parse_check.reason_code
        != f"official_timestamp_parsed_by:{scope.parser_version}"
    ):
        raise DailySourceSnapshotError("official timestamp 解析證據未綁定 scope parser version")
    if not contains_official_clock and (
        validation.official_timestamp_parse_check.status != "not_required"
    ):
        raise DailySourceSnapshotError("缺少 official timestamp 卻宣告解析通過")
    if not contains_official_clock and (
        validation.official_timestamp_parse_check.reason_code
        != "official_timestamp_not_provided"
    ):
        raise DailySourceSnapshotError("缺少 official timestamp 的解析原因碼不符")
    if not _validated_unique_texts(
        validation.expected_partition_ids, "expected_partition_ids"
    ) == _validated_unique_texts(
        validation.successful_partition_ids, "successful_partition_ids"
    ) or validation.failed_partition_ids:
        raise DailySourceSnapshotError("每日批次分區未完整成功")
    identities: set[tuple[str, str, str, str, str]] = set()
    for record in records:
        if record.market != scope.market or record.unit != scope.unit:
            raise DailySourceSnapshotError("快照列市場或單位與用途接受範圍不符")
        if record.raw_source_sha256 != raw_source_sha256:
            raise DailySourceSnapshotError("快照列原始雜湊與保存 bytes 不符")
        _validate_mops_monthly_version_binding(record)
        identity = (
            record.stock_code,
            record.market,
            record.period,
            record.source_version,
            record.raw_source_sha256,
        )
        if identity in identities:
            raise DailySourceSnapshotError("每日快照含重複來源列")
        identities.add(identity)
    if _to_taipei(use_acceptance.accepted_at, "accepted_at") > _to_taipei(
        source_batch_started_at, "source_batch_started_at"
    ):
        # 來源用途應在每日批次前接受；若政策流程的接受時間較晚，需建立新的可追溯批次。
        raise DailySourceSnapshotError("來源用途接受晚於每日批次開始")


def _validate_mops_monthly_version_binding(
    record: DailySourceSnapshotRecord,
) -> None:
    legacy = re.fullmatch(
        r"mops-static-(twse|tpex)-(\d{4}-\d{2})-sha256-([0-9a-f]{64})",
        record.source_version,
    )
    current = re.fullmatch(
        r"mops-static-snapshot\.v2:(twse|tpex):(\d{4}-\d{2}):"
        r"body_completed_at:(.+):sha256:([0-9a-f]{64})",
        record.source_version,
    )
    if legacy is not None:
        version = legacy
        version_hash = legacy.group(3)
    elif current is not None:
        version = current
        version_hash = current.group(4)
    else:
        raise DailySourceSnapshotError("MOPS 月營收 source_version 格式不受支援")
    if version.group(1) != record.market or version.group(2) != record.period:
        raise DailySourceSnapshotError("MOPS 月營收 source_version 市場或期間不符")
    if version_hash != record.raw_source_sha256:
        raise DailySourceSnapshotError("MOPS 月營收 source_version SHA 與原始 bytes 不符")
    if current is not None:
        try:
            source_clock = datetime.fromisoformat(
                current.group(3).replace("Z", "+00:00")
            )
        except ValueError as exc:
            raise DailySourceSnapshotError(
                "MOPS 月營收 source_version body clock 格式錯誤"
            ) from exc
        _to_taipei(source_clock, "MOPS source_version body_completed_at")


def _validate_supported_scope(scope: DailySourceUseScope) -> None:
    if (
        scope.dataset_id != DAILY_SOURCE_SNAPSHOT_DATASET_ID
        or scope.source_id != DAILY_SOURCE_SNAPSHOT_SOURCE_ID
    ):
        raise DailySourceSnapshotError("daily snapshot contract 目前只支援 MOPS 月營收來源")


def _scope_from_dict(value: object) -> DailySourceUseScope:
    if not isinstance(value, dict) or set(value) != {
        "dataset_id",
        "source_id",
        "market",
        "parser_version",
        "source_schema_version",
        "unit",
        "intended_use",
    }:
        raise DailySourceSnapshotError("source scope 欄位錯誤")
    return DailySourceUseScope(**value)


def _acceptance_from_dict(value: object) -> DailySourceUseAcceptance:
    if not isinstance(value, dict) or set(value) != {
        "scope",
        "acceptance_id",
        "accepted_at",
        "official_source_endpoint",
        "document_chain",
        "acceptance_evidence_ref",
        "authorization_scope",
        "time_basis_policy",
    }:
        raise DailySourceSnapshotError("一次性用途接受紀錄欄位錯誤")
    document_chain = value.get("document_chain")
    if not isinstance(document_chain, list):
        raise DailySourceSnapshotError("document_chain 格式錯誤")
    return DailySourceUseAcceptance(
        scope=_scope_from_dict(value.get("scope")),
        acceptance_id=_require_text(value.get("acceptance_id"), "acceptance_id"),
        accepted_at=_parse_datetime(value.get("accepted_at"), "accepted_at"),
        official_source_endpoint=_require_text(
            value.get("official_source_endpoint"), "official_source_endpoint"
        ),
        document_chain=tuple(
            _require_text(item, "document_chain_item") for item in document_chain
        ),
        acceptance_evidence_ref=_require_text(
            value.get("acceptance_evidence_ref"), "acceptance_evidence_ref"
        ),
        authorization_scope=_require_text(
            value.get("authorization_scope"), "authorization_scope"
        ),
        time_basis_policy=_require_text(
            value.get("time_basis_policy"), "time_basis_policy"
        ),
    )


def _record_from_dict(value: object) -> DailySourceSnapshotRecord:
    if not isinstance(value, dict) or set(value) != {
        "stock_code",
        "market",
        "period",
        "source_version",
        "raw_source_sha256",
        "unit",
        "official_timestamp",
        "official_timestamp_original_text",
        "official_timestamp_original_timezone",
    }:
        raise DailySourceSnapshotError("每日快照記錄欄位錯誤")
    official = value.get("official_timestamp")
    return DailySourceSnapshotRecord(
        stock_code=_require_text(value.get("stock_code"), "stock_code"),
        market=_require_text(value.get("market"), "market"),
        period=_require_text(value.get("period"), "period"),
        source_version=_require_text(value.get("source_version"), "source_version"),
        raw_source_sha256=_require_hash(
            value.get("raw_source_sha256"), "raw_source_sha256"
        ),
        unit=_require_text(value.get("unit"), "unit"),
        official_timestamp=(
            _parse_datetime(official, "official_timestamp") if official is not None else None
        ),
        official_timestamp_original_text=_require_text(
            value.get("official_timestamp_original_text"),
            "official_timestamp_original_text",
        )
        if official is not None
        else str(value.get("official_timestamp_original_text") or ""),
        official_timestamp_original_timezone=_require_text(
            value.get("official_timestamp_original_timezone"),
            "official_timestamp_original_timezone",
        )
        if official is not None
        else str(value.get("official_timestamp_original_timezone") or ""),
    )


def _validation_from_dict(value: object) -> DailySourceBatchValidation:
    if not isinstance(value, dict) or set(value) != {
        "validation_id",
        "expected_partition_ids",
        "successful_partition_ids",
        "failed_partition_ids",
        "expected_record_count",
        "actual_record_count",
        "source_status_check",
        "raw_source_hash_check",
        "schema_check",
        "unit_check",
        "finite_values_check",
        "missing_values_check",
        "prior_period_required_check",
        "official_timestamp_parse_check",
    }:
        raise DailySourceSnapshotError("每日驗證收據欄位錯誤")
    expected = value.get("expected_partition_ids")
    successful = value.get("successful_partition_ids")
    failed = value.get("failed_partition_ids")
    if (
        not isinstance(expected, list)
        or not isinstance(successful, list)
        or not isinstance(failed, list)
    ):
        raise DailySourceSnapshotError("每日驗證分區清單格式錯誤")
    expected_count = value.get("expected_record_count")
    actual_count = value.get("actual_record_count")
    if not isinstance(expected_count, int) or isinstance(expected_count, bool):
        raise DailySourceSnapshotError("expected_record_count 必須是正整數")
    if not isinstance(actual_count, int) or isinstance(actual_count, bool):
        raise DailySourceSnapshotError("actual_record_count 必須是正整數")
    return DailySourceBatchValidation(
        validation_id=_require_text(value.get("validation_id"), "validation_id"),
        expected_partition_ids=tuple(
            _require_text(item, "expected_partition_id") for item in expected
        ),
        successful_partition_ids=tuple(
            _require_text(item, "successful_partition_id") for item in successful
        ),
        failed_partition_ids=tuple(
            _require_text(item, "failed_partition_id") for item in failed
        ),
        expected_record_count=expected_count,
        actual_record_count=actual_count,
        source_status_check=_check_from_dict(value.get("source_status_check")),
        raw_source_hash_check=_check_from_dict(value.get("raw_source_hash_check")),
        schema_check=_check_from_dict(value.get("schema_check")),
        unit_check=_check_from_dict(value.get("unit_check")),
        finite_values_check=_check_from_dict(value.get("finite_values_check")),
        missing_values_check=_check_from_dict(value.get("missing_values_check")),
        prior_period_required_check=_check_from_dict(
            value.get("prior_period_required_check")
        ),
        official_timestamp_parse_check=_check_from_dict(
            value.get("official_timestamp_parse_check")
        ),
    )


def _check_from_dict(value: object) -> DailySourceValidationCheck:
    if not isinstance(value, dict) or set(value) != {"check_id", "status", "reason_code"}:
        raise DailySourceSnapshotError("每日具名檢查欄位錯誤")
    return DailySourceValidationCheck(
        check_id=_require_text(value.get("check_id"), "check_id"),
        status=_require_text(value.get("status"), "status"),
        reason_code=_require_text(value.get("reason_code"), "reason_code"),
    )


def _load_canonical_object(data: bytes, label: str) -> dict[str, object]:
    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=_unique_object_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise DailySourceSnapshotError(f"{label} JSON 格式錯誤") from exc
    if not isinstance(value, dict):
        raise DailySourceSnapshotError(f"{label} 必須是 JSON object")
    if _canonical_json_bytes(value) != data:
        raise DailySourceSnapshotError(f"{label} 必須使用 canonical JSON 編碼")
    return value


def _unique_object_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("JSON object 含重複欄位")
        result[key] = value
    return result


def _canonical_json_bytes(value: Mapping[str, object]) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _decode_raw_bytes(value: object) -> bytes:
    if not isinstance(value, str) or not value:
        raise DailySourceSnapshotError("raw source bytes 缺失")
    try:
        decoded = base64.b64decode(value.encode("ascii"), validate=True)
    except (UnicodeEncodeError, ValueError) as exc:
        raise DailySourceSnapshotError("raw source bytes base64 格式錯誤") from exc
    if not decoded or len(decoded) > MAX_DAILY_SOURCE_RAW_BYTES:
        raise DailySourceSnapshotError("raw source bytes 為空或超過上限")
    return decoded


def _decode_transport_bytes(value: object) -> bytes:
    if not isinstance(value, str) or not value:
        raise DailySourceSnapshotError("transport response bytes 缺失")
    try:
        decoded = base64.b64decode(value.encode("ascii"), validate=True)
    except (UnicodeEncodeError, ValueError) as exc:
        raise DailySourceSnapshotError("transport response bytes base64 格式錯誤") from exc
    if not decoded or len(decoded) > MAX_DAILY_SOURCE_TRANSPORT_BYTES:
        raise DailySourceSnapshotError("transport response bytes 為空或超過上限")
    return decoded


def _validate_https_url(value: object, label: str) -> str:
    url = _require_text(value, label)
    try:
        parsed = urlsplit(url)
        valid = (
            parsed.scheme.casefold() == "https"
            and bool(parsed.netloc)
            and bool(parsed.hostname)
            and parsed.username is None
            and parsed.password is None
            and not parsed.fragment
            and not any(ord(character) < 32 for character in url)
        )
        if parsed.port is not None and not 1 <= parsed.port <= 65535:
            valid = False
    except ValueError as exc:
        raise DailySourceSnapshotError(f"{label} URL 格式錯誤") from exc
    if not valid:
        raise DailySourceSnapshotError(f"{label} 必須是無憑證與 fragment 的 HTTPS URL")
    return url


def _codec_name(value: str) -> str:
    try:
        return codecs.lookup(_require_text(value, "charset")).name
    except LookupError as exc:
        raise DailySourceSnapshotError(f"charset 編碼名稱不受支援：{value}") from exc


def _match_ascii_charset(match: re.Match[bytes], label: str) -> str:
    raw_value = next((part for part in match.groups() if part is not None), None)
    if raw_value is None:
        raise DailySourceSnapshotError(f"{label} charset 原文缺失")
    try:
        return _require_text(raw_value.decode("ascii"), label)
    except UnicodeDecodeError as exc:
        raise DailySourceSnapshotError(f"{label} charset 必須是 ASCII 原文") from exc


def _match_text_charset(match: re.Match[str], label: str) -> str:
    raw_value = next((part for part in match.groups() if part is not None), None)
    if raw_value is None:
        raise DailySourceSnapshotError(f"{label} charset 原文缺失")
    return _require_text(raw_value, label)


def _content_type_charset_text(content_type: str) -> str | None:
    declarations = [
        _match_text_charset(match, "Content-Type")
        for match in _CONTENT_TYPE_CHARSET_RE.finditer(content_type)
    ]
    if not declarations:
        return None
    if len({_codec_name(value) for value in declarations}) != 1:
        raise DailySourceSnapshotError("HTTP Content-Type 含互相衝突的 charset")
    return declarations[0]


def _html_meta_charset_text(raw_response_bytes: bytes) -> str | None:
    ascii_prescan = _HTML_COMMENT_RE.sub(b"", raw_response_bytes[:1024])
    declarations: list[str] = []
    for tag in _HTML_META_TAG_RE.findall(ascii_prescan):
        attributes: dict[str, bytes] = {}
        for match in _HTML_META_ATTRIBUTE_RE.finditer(tag):
            try:
                key = match.group(1).decode("ascii", errors="strict").casefold()
            except UnicodeDecodeError as exc:
                raise DailySourceSnapshotError("HTML meta 屬性名稱必須是 ASCII") from exc
            raw_value = next(
                (part for part in match.groups()[1:] if part is not None), None
            )
            if raw_value is None:
                continue
            if key in attributes:
                raise DailySourceSnapshotError("HTML meta tag 含重複屬性")
            attributes[key] = raw_value
        direct_charset = attributes.get("charset")
        if direct_charset is not None:
            try:
                declarations.append(
                    _require_text(direct_charset.decode("ascii"), "HTML meta charset")
                )
            except UnicodeDecodeError as exc:
                raise DailySourceSnapshotError(
                    "HTML meta charset 必須是 ASCII 原文"
                ) from exc
        http_equiv = attributes.get("http-equiv")
        content = attributes.get("content")
        try:
            is_content_type = (
                http_equiv is not None
                and http_equiv.decode("ascii", errors="strict").strip().casefold()
                == "content-type"
            )
        except UnicodeDecodeError as exc:
            raise DailySourceSnapshotError("HTML meta http-equiv 必須是 ASCII") from exc
        if is_content_type and content is not None:
            try:
                content_text = content.decode("ascii")
            except UnicodeDecodeError as exc:
                raise DailySourceSnapshotError(
                    "HTML meta content-type 必須是 ASCII 原文"
                ) from exc
            declarations.extend(
                _match_text_charset(match, "HTML meta content-type")
                for match in _CONTENT_TYPE_CHARSET_RE.finditer(content_text)
            )
    if not declarations:
        return None
    if len({_codec_name(value) for value in declarations}) != 1:
        raise DailySourceSnapshotError("HTML meta 含互相衝突的 charset")
    if len(set(declarations)) != 1:
        raise DailySourceSnapshotError("HTML meta charset 原文不唯一")
    return declarations[0]


def _write_create_only(path: Path, data: bytes) -> None:
    try:
        with path.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as exc:
        raise DailySourceSnapshotError("不可變快照檔已存在，不可覆寫") from exc
    except OSError as exc:
        raise DailySourceSnapshotError("每日快照檔保存失敗") from exc


def _batch_root(root: Path, batch_id: str) -> Path:
    batch_root = root / batch_id
    try:
        resolved = batch_root.resolve(strict=False)
        resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise DailySourceSnapshotError("batch_id 路徑超出 caller 提供的 root") from exc
    return resolved


def _require_root(value: Path | str) -> Path:
    if not isinstance(value, (Path, str)) or not str(value).strip():
        raise DailySourceSnapshotError("snapshot root 必須由 caller 明確提供")
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise DailySourceSnapshotError("snapshot root 必須是絕對路徑")
    return path.resolve(strict=False)


def _validate_batch_id(value: str) -> None:
    if not isinstance(value, str) or not _BATCH_ID_RE.fullmatch(value):
        raise DailySourceSnapshotError("batch_id 格式錯誤")


def _validated_unique_texts(values: Sequence[str], label: str) -> tuple[str, ...]:
    if not isinstance(values, tuple):
        raise DailySourceSnapshotError(f"{label} 必須是 tuple")
    checked = tuple(_require_text(value, label) for value in values)
    if checked != tuple(sorted(set(checked))):
        raise DailySourceSnapshotError(f"{label} 必須排序且唯一")
    return checked


def _unique_texts_preserving_order(
    values: Sequence[str], label: str
) -> tuple[str, ...]:
    if not isinstance(values, tuple):
        raise DailySourceSnapshotError(f"{label} 必須是 tuple")
    checked = tuple(_require_text(value, label) for value in values)
    if len(checked) != len(set(checked)):
        raise DailySourceSnapshotError(f"{label} 不可重複")
    return checked


def _require_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise DailySourceSnapshotError(f"{label} 不可缺值")
    return value


def _require_hash(value: object, label: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise DailySourceSnapshotError(f"{label} 必須是小寫 SHA-256")
    return value


def _to_taipei(value: datetime, label: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise DailySourceSnapshotError(f"{label} 必須是 aware datetime")
    return value.astimezone(_TAIPEI)


def _datetime_text(value: datetime) -> str:
    return _to_taipei(value, "timestamp").isoformat(timespec="microseconds")


def _parse_datetime(value: object, label: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise DailySourceSnapshotError(f"{label} 缺少 aware ISO timestamp")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise DailySourceSnapshotError(f"{label} ISO timestamp 格式錯誤") from exc
    parsed_taipei = _to_taipei(parsed, label)
    if _datetime_text(parsed_taipei) != value:
        raise DailySourceSnapshotError(f"{label} 必須保存為台北時區 aware timestamp")
    return parsed_taipei


def _parse_official_timestamp_text(value: str) -> tuple[datetime, str]:
    """解析原樣保存的 ISO aware 時間或 MOPS 民國台北時間。"""

    roc_match = _ROC_TIMESTAMP_RE.fullmatch(value)
    if roc_match is not None:
        roc_year, month, day, hour, minute, second = (
            int(part) for part in roc_match.groups()
        )
        if roc_year <= 0:
            raise ValueError("民國年必須是正整數")
        return (
            datetime(
                roc_year + 1911,
                month,
                day,
                hour,
                minute,
                second,
                tzinfo=_TAIPEI,
            ),
            "Asia/Taipei",
        )

    zone_match = _ISO_ZONE_SUFFIX_RE.search(value)
    if zone_match is None:
        raise ValueError("ISO 時間必須明示時區")
    zone_text = zone_match.group(1)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("ISO 時間格式錯誤") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("ISO 時間必須是 aware")
    return parsed, "UTC" if zone_text == "Z" else zone_text


def _ceil_hour(value: datetime) -> datetime:
    local = _to_taipei(value, "availability timestamp")
    exact_hour = local.replace(minute=0, second=0, microsecond=0)
    if local == exact_hour:
        return exact_hour
    return exact_hour + timedelta(hours=1)


__all__ = (
    "DAILY_SOURCE_TIME_BASIS_POLICY",
    "DAILY_SOURCE_SNAPSHOT_DATASET_ID",
    "DAILY_SOURCE_SNAPSHOT_MANIFEST_SCHEMA",
    "DAILY_SOURCE_SNAPSHOT_MANIFEST_SCHEMA_V1",
    "DAILY_SOURCE_SNAPSHOT_SCHEMA",
    "DAILY_SOURCE_SNAPSHOT_SOURCE_ID",
    "MAX_DAILY_SOURCE_TRANSPORT_BYTES",
    "MAX_DAILY_SOURCE_RECEIPT_BYTES",
    "DailySourceBatchValidation",
    "DailySourceSnapshot",
    "DailySourceSnapshotError",
    "DailySourceSnapshotFileReader",
    "DailySourceSnapshotReadPort",
    "DailySourceSnapshotRecord",
    "DailySourceTransportCapture",
    "DailySourceUseAcceptance",
    "DailySourceUseScope",
    "DailySourceValidationCheck",
    "read_daily_source_snapshot",
    "write_daily_source_snapshot",
)
