"""TWSE 月營收 OpenAPI 的單股票研究候選 preparation 契約。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
from typing import Any, Mapping

from data_module.daily_source_snapshot import (
    DAILY_SOURCE_TIME_BASIS_POLICY,
    _ceil_hour,
)
from data_module.monthly_revenue_availability_history import (
    parse_announcement_date,
    parse_revenue_period,
)


TWSE_MONTHLY_REVENUE_OPENAPI_URL = (
    "https://openapi.twse.com.tw/v1/opendata/t187ap05_L"
)
TWSE_MONTHLY_REVENUE_OPENAPI_SOURCE_ID = "twse.openapi.t187ap05_L"
TWSE_MONTHLY_REVENUE_RAW_CAPTURE_SCHEMA = (
    "twse-monthly-revenue-openapi-raw-capture.v1"
)
TWSE_MONTHLY_REVENUE_PREPARATION_SCHEMA = (
    "twse-monthly-revenue-openapi-preparation.v1"
)
TWSE_MONTHLY_REVENUE_UNIT_PROOF_EXTENSION = (
    "twse-monthly-revenue-openapi-unit-proof.v1"
)
TWSE_MONTHLY_REVENUE_PARSER_VERSION = (
    "twse-monthly-revenue-openapi-parser.v1"
)
MAX_TWSE_MONTHLY_REVENUE_RAW_BYTES = 16 * 1024 * 1024
MAX_JSON_NESTING_DEPTH = 64
MAX_JSON_ROWS = 100_000
MAX_DECIMAL_TOKEN_CHARS = 128
MAX_DECIMAL_DIGITS = 64
MAX_DECIMAL_ABS_EXPONENT = 32

AMOUNT_FIELDS = (
    "營業收入-當月營收",
    "營業收入-上月營收",
    "營業收入-去年當月營收",
    "累計營業收入-當月累計營收",
    "累計營業收入-去年累計營收",
)
PERCENTAGE_FIELDS = (
    "營業收入-上月比較增減(%)",
    "營業收入-去年同月增減(%)",
    "累計營業收入-前期比較增減(%)",
)
REQUIRED_TARGET_FIELDS = (
    "資料年月",
    "公司代號",
    "公司名稱",
    *AMOUNT_FIELDS,
    *PERCENTAGE_FIELDS,
    "出表日期",
    "備註",
)


class TwseMonthlyRevenuePreparationError(ValueError):
    """具有穩定 reason code 的 TWSE OpenAPI preparation 失敗。"""

    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


@dataclass(frozen=True, slots=True)
class TwseMonthlyRevenueOpenApiRawCapture:
    """保留單次 HTTP response 的原始 bytes 與完整傳輸證據。"""

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
        if not isinstance(self.raw_response_bytes, bytes):
            raise TwseMonthlyRevenuePreparationError("raw_response_bytes_type_invalid")
        if not isinstance(self.requested_url, str) or not isinstance(self.response_url, str):
            raise TwseMonthlyRevenuePreparationError("response_url_type_invalid")
        for label, value in (
            ("content_type_original_text", self.content_type_original_text),
            ("content_encoding_original_text", self.content_encoding_original_text),
            ("content_length_original_text", self.content_length_original_text),
        ):
            if value is not None and not isinstance(value, str):
                raise TwseMonthlyRevenuePreparationError(f"{label}_type_invalid")
        if not isinstance(self.received_body_bytes, int) or isinstance(
            self.received_body_bytes, bool
        ):
            raise TwseMonthlyRevenuePreparationError("received_body_bytes_type_invalid")
        if self.received_body_bytes < 0:
            raise TwseMonthlyRevenuePreparationError("received_body_bytes_negative")
        if not isinstance(self.response_status, int) or isinstance(
            self.response_status, bool
        ):
            raise TwseMonthlyRevenuePreparationError("response_status_type_invalid")
        if not isinstance(self.response_body_complete, bool) or not isinstance(
            self.eof_observed, bool
        ):
            raise TwseMonthlyRevenuePreparationError("transport_completion_flag_invalid")
        _require_aware_datetime(
            self.body_observation_ended_at, "body_observation_ended_at"
        )
        if self.body_completed_at is not None:
            _require_aware_datetime(self.body_completed_at, "body_completed_at")
            try:
                if self.body_completed_at > self.body_observation_ended_at:
                    raise TwseMonthlyRevenuePreparationError(
                        "body_completion_clock_after_observation_end"
                    )
            except TypeError as exc:
                raise TwseMonthlyRevenuePreparationError(
                    "body_clock_comparison_invalid"
                ) from exc
        if self.response_body_complete and self.eof_observed and self.body_completed_at is None:
            raise TwseMonthlyRevenuePreparationError("body_completion_clock_missing")

    @property
    def raw_response_sha256(self) -> str:
        return hashlib.sha256(self.raw_response_bytes).hexdigest()

    def receipt_fields(self) -> dict[str, object]:
        """回傳不含 body 的 receipt metadata；原件由呼叫端另行保存。"""
        return {
            "schema_version": TWSE_MONTHLY_REVENUE_RAW_CAPTURE_SCHEMA,
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
            "body_observation_ended_at": _datetime_text(
                self.body_observation_ended_at
            ),
            "body_completed_at": (
                _datetime_text(self.body_completed_at)
                if self.body_completed_at is not None
                else None
            ),
        }


@dataclass(frozen=True, slots=True)
class TwseMonthlyRevenueUnitProofReference:
    """為後續新版本預留的官方單位證據索引，不會啟用 v1 換算。"""

    source_id: str
    endpoint_url: str
    official_document_url: str
    official_document_sha256: str
    trusted_evidence_scope_id: str
    source_unit_original_text: str
    conversion_to_twd: Decimal

    def __post_init__(self) -> None:
        if self.source_id != TWSE_MONTHLY_REVENUE_OPENAPI_SOURCE_ID:
            raise TwseMonthlyRevenuePreparationError("unit_proof_source_id_mismatch")
        if self.endpoint_url != TWSE_MONTHLY_REVENUE_OPENAPI_URL:
            raise TwseMonthlyRevenuePreparationError("unit_proof_endpoint_mismatch")
        if not isinstance(self.official_document_sha256, str) or not _SHA256_RE.fullmatch(
            self.official_document_sha256
        ):
            raise TwseMonthlyRevenuePreparationError("unit_proof_document_hash_invalid")
        if not isinstance(self.official_document_url, str) or not self.official_document_url.startswith(
            "https://"
        ):
            raise TwseMonthlyRevenuePreparationError("unit_proof_document_url_invalid")
        if not isinstance(self.trusted_evidence_scope_id, str) or not self.trusted_evidence_scope_id.strip():
            raise TwseMonthlyRevenuePreparationError("unit_proof_trusted_scope_missing")
        if not isinstance(self.source_unit_original_text, str) or not self.source_unit_original_text.strip():
            raise TwseMonthlyRevenuePreparationError("unit_proof_source_unit_missing")
        if (
            not isinstance(self.conversion_to_twd, Decimal)
            or not self.conversion_to_twd.is_finite()
            or self.conversion_to_twd <= 0
        ):
            raise TwseMonthlyRevenuePreparationError("unit_proof_conversion_invalid")


@dataclass(frozen=True, slots=True)
class PreparedTwseMonthlyRevenueOpenApi:
    """單一股票與期間的 shadow/diagnostics 結果，不代表完整市場。"""

    capture: TwseMonthlyRevenueOpenApiRawCapture
    stock_code: str
    period: str
    roc_period: str
    company_name: str
    report_date: date
    report_date_original_text: str
    source_values: tuple[tuple[str, str], ...]
    amount_values: tuple[tuple[str, Decimal], ...]
    percentage_values: tuple[tuple[str, Decimal | None], ...]
    percentage_missing_reasons: tuple[tuple[str, str], ...]
    response_row_count: int
    successful_batch_completed_at: datetime
    available_at: datetime
    source_version: str

    @property
    def raw_response_bytes(self) -> bytes:
        """提供原件 bytes 的唯讀參照；不以正規化 JSON 取代原件。"""
        return self.capture.raw_response_bytes

    def to_dict(self) -> dict[str, object]:
        """輸出可序列化的準備結果 metadata，不嵌入原始 response body。"""
        body_completed_at = self.capture.body_completed_at
        if body_completed_at is None:
            raise TwseMonthlyRevenuePreparationError(
                "prepared_capture_body_completion_clock_missing"
            )
        return {
            "schema_version": TWSE_MONTHLY_REVENUE_PREPARATION_SCHEMA,
            "parser_version": TWSE_MONTHLY_REVENUE_PARSER_VERSION,
            "source_id": TWSE_MONTHLY_REVENUE_OPENAPI_SOURCE_ID,
            "source_version": self.source_version,
            "capture_scope": "single_stock_period_target_row",
            "coverage_claim": "none",
            "response_row_count": self.response_row_count,
            "target_match_count": 1,
            "stock_code": self.stock_code,
            "period": self.period,
            "roc_period": self.roc_period,
            "company_name": self.company_name,
            "report_date": self.report_date.isoformat(),
            "report_date_original_text": self.report_date_original_text,
            "official_publication_at": None,
            "availability_clock_evidence": {
                "available_at": self.available_at.isoformat(),
                "time_basis": DAILY_SOURCE_TIME_BASIS_POLICY,
                "basis": "batch_completion_missing_official_hour",
                "report_date_is_date_only": True,
                "successful_batch_clock_available": True,
                "scope": "clock_evidence_only",
            },
            "response_body_completed_at": _datetime_text(body_completed_at),
            "successful_batch_completed_at": _datetime_text(
                self.successful_batch_completed_at
            ),
            "source_values": dict(self.source_values),
            "amount_values_decimal_source_units": {
                key: str(value) for key, value in self.amount_values
            },
            "percentage_values_decimal_source_units": {
                key: str(value) if value is not None else None
                for key, value in self.percentage_values
            },
            "percentage_missing_reasons": dict(self.percentage_missing_reasons),
            "unit_evidence": {
                "unit_status": "unverified",
                "unit_evidence_status": "missing_official_strong_anchor",
                "proof_extension_schema": TWSE_MONTHLY_REVENUE_UNIT_PROOF_EXTENSION,
                "proof_reference_present": False,
                "official_document_sha256": None,
                "trusted_evidence_scope_id": None,
                "source_unit_original_text": None,
                "conversion_to_twd": None,
                "formal_unit_contract_accepted": False,
            },
            "use_scope": {
                "allowed": ["shadow", "diagnostics"],
                "source_acceptance": False,
                "formal_apply_authorized": False,
                "production_ingestion_allowed": False,
                "scoring_allowed": False,
                "advice_allowed": False,
                "portfolio_allowed": False,
                "scheduler_allowed": False,
                "historical_pit_credit": False,
            },
            "raw_capture": self.capture.receipt_fields(),
        }

def prepare_twse_monthly_revenue_openapi_capture(
    *,
    capture: TwseMonthlyRevenueOpenApiRawCapture,
    stock_code: str,
    period: str,
    successful_batch_completed_at: datetime,
) -> PreparedTwseMonthlyRevenueOpenApi:
    """驗證已取得的 TWSE JSON 原件，只準備一個 exact target row。"""
    if not isinstance(capture, TwseMonthlyRevenueOpenApiRawCapture):
        raise TwseMonthlyRevenuePreparationError("capture_type_invalid")
    normalized_stock = _normalize_stock_code(stock_code)
    normalized_period, expected_roc_period = _normalize_requested_period(period)
    _validate_transport(capture)
    _require_aware_datetime(successful_batch_completed_at, "successful_batch_completed_at")
    body_completed_at = capture.body_completed_at
    if body_completed_at is None:
        raise TwseMonthlyRevenuePreparationError("body_completion_clock_missing")
    try:
        if successful_batch_completed_at < body_completed_at:
            raise TwseMonthlyRevenuePreparationError(
                "successful_batch_clock_precedes_body_completion"
            )
    except TypeError as exc:
        raise TwseMonthlyRevenuePreparationError("capture_clock_comparison_invalid") from exc

    available_at = _ceil_hour(successful_batch_completed_at)
    batch_taipei = successful_batch_completed_at.astimezone(available_at.tzinfo)
    batch_month = f"{batch_taipei.year:04d}-{batch_taipei.month:02d}"
    if normalized_period > batch_month:
        raise TwseMonthlyRevenuePreparationError(
            "requested_period_after_successful_batch_month"
        )

    rows = _decode_rows(capture.raw_response_bytes)
    keyed_rows = tuple(_row_identity(row) for row in rows)
    matching_rows = [
        row
        for row, (row_stock, row_period, _roc_period) in zip(rows, keyed_rows)
        if row_stock == normalized_stock and row_period == normalized_period
    ]
    if not matching_rows:
        raise TwseMonthlyRevenuePreparationError("target_row_missing")
    if len(matching_rows) != 1:
        raise TwseMonthlyRevenuePreparationError("target_row_duplicate")

    target_row = matching_rows[0]
    source_values = _required_target_values(target_row)
    if not source_values["公司名稱"].strip():
        raise TwseMonthlyRevenuePreparationError("target_company_name_missing")
    if not _is_date_only_text(source_values["出表日期"].strip()):
        raise TwseMonthlyRevenuePreparationError("target_report_date_not_date_only")
    try:
        report_date = parse_announcement_date(source_values["出表日期"].strip())
    except (TypeError, ValueError) as exc:
        raise TwseMonthlyRevenuePreparationError("target_report_date_invalid") from exc
    if report_date > batch_taipei.date():
        raise TwseMonthlyRevenuePreparationError(
            "target_report_date_after_successful_batch_date"
        )

    amount_values = tuple(
        (field, _parse_finite_decimal(source_values[field], field))
        for field in AMOUNT_FIELDS
    )
    percentages: list[tuple[str, Decimal | None]] = []
    missing_reasons: list[tuple[str, str]] = []
    for field in PERCENTAGE_FIELDS:
        original = source_values[field]
        if not original.strip():
            percentages.append((field, None))
            missing_reasons.append((field, "source_cell_blank"))
        else:
            percentages.append(
                (field, _parse_finite_decimal(original, field))
            )

    source_version = (
        f"{TWSE_MONTHLY_REVENUE_OPENAPI_SOURCE_ID}.v1:"
        f"{normalized_stock}:{expected_roc_period}:"
        f"sha256:{capture.raw_response_sha256}"
    )
    values = tuple((field, source_values[field]) for field in REQUIRED_TARGET_FIELDS)
    return PreparedTwseMonthlyRevenueOpenApi(
        capture=capture,
        stock_code=normalized_stock,
        period=normalized_period,
        roc_period=expected_roc_period,
        company_name=source_values["公司名稱"].strip(),
        report_date=report_date,
        report_date_original_text=source_values["出表日期"],
        source_values=values,
        amount_values=amount_values,
        percentage_values=tuple(percentages),
        percentage_missing_reasons=tuple(missing_reasons),
        response_row_count=len(rows),
        successful_batch_completed_at=successful_batch_completed_at,
        available_at=available_at,
        source_version=source_version,
    )


def _validate_transport(capture: TwseMonthlyRevenueOpenApiRawCapture) -> None:
    if capture.requested_url != TWSE_MONTHLY_REVENUE_OPENAPI_URL:
        raise TwseMonthlyRevenuePreparationError("requested_url_mismatch")
    if capture.response_url != TWSE_MONTHLY_REVENUE_OPENAPI_URL:
        raise TwseMonthlyRevenuePreparationError("response_url_redirect_or_mismatch")
    if capture.response_status != 200:
        raise TwseMonthlyRevenuePreparationError("http_status_not_200")
    content_type_parts = (capture.content_type_original_text or "").split(";")
    content_type = content_type_parts[0].strip().lower()
    if content_type != "application/json":
        raise TwseMonthlyRevenuePreparationError("content_type_not_json")
    charset_values: list[str] = []
    for parameter in content_type_parts[1:]:
        name, separator, raw_value = parameter.partition("=")
        if name.strip().lower() == "charset":
            if not separator:
                raise TwseMonthlyRevenuePreparationError(
                    "content_type_charset_invalid"
                )
            charset_values.append(raw_value.strip().strip("\"'").lower())
    if len(charset_values) > 1:
        raise TwseMonthlyRevenuePreparationError("content_type_charset_invalid")
    if charset_values and charset_values[0] not in {"utf-8", "utf8"}:
        raise TwseMonthlyRevenuePreparationError("content_type_charset_not_utf8")
    content_encoding = (capture.content_encoding_original_text or "identity").strip().lower()
    if content_encoding not in {"", "identity"}:
        raise TwseMonthlyRevenuePreparationError("content_encoding_not_identity")
    if not capture.response_body_complete or not capture.eof_observed:
        raise TwseMonthlyRevenuePreparationError("response_body_incomplete_or_eof_missing")
    if capture.body_completed_at is None:
        raise TwseMonthlyRevenuePreparationError("body_completion_clock_missing")
    if capture.received_body_bytes != len(capture.raw_response_bytes):
        raise TwseMonthlyRevenuePreparationError("received_body_byte_count_mismatch")
    if not capture.raw_response_bytes:
        raise TwseMonthlyRevenuePreparationError("response_body_empty")
    if len(capture.raw_response_bytes) > MAX_TWSE_MONTHLY_REVENUE_RAW_BYTES:
        raise TwseMonthlyRevenuePreparationError("response_body_exceeds_byte_limit")
    length_text = capture.content_length_original_text
    if length_text is not None:
        cleaned = length_text.strip()
        if not re.fullmatch(r"\d+", cleaned):
            raise TwseMonthlyRevenuePreparationError("content_length_invalid")
        if int(cleaned) != len(capture.raw_response_bytes):
            raise TwseMonthlyRevenuePreparationError("content_length_mismatch")


def _decode_rows(raw_bytes: bytes) -> tuple[dict[str, Any], ...]:
    try:
        decoded_text = raw_bytes.decode("utf-8-sig", errors="strict")
    except UnicodeDecodeError as exc:
        raise TwseMonthlyRevenuePreparationError("json_utf8_decode_failed") from exc
    _validate_json_structural_limits(decoded_text)
    try:
        payload = json.loads(
            decoded_text,
            object_pairs_hook=_unique_normalized_pairs,
            parse_constant=_reject_json_nonfinite_constant,
            parse_int=_parse_json_integer_token,
            parse_float=_parse_json_float_token,
        )
    except TwseMonthlyRevenuePreparationError:
        raise
    except (json.JSONDecodeError, RecursionError) as exc:
        raise TwseMonthlyRevenuePreparationError("json_payload_invalid") from exc
    if not isinstance(payload, list) or not payload:
        raise TwseMonthlyRevenuePreparationError("json_root_must_be_nonempty_array")
    if len(payload) > MAX_JSON_ROWS:
        raise TwseMonthlyRevenuePreparationError("json_row_count_exceeds_limit")
    rows: list[dict[str, Any]] = []
    for index, row in enumerate(payload):
        if not isinstance(row, dict):
            raise TwseMonthlyRevenuePreparationError("json_row_not_object")
        try:
            _row_identity(row)
        except TwseMonthlyRevenuePreparationError as exc:
            raise TwseMonthlyRevenuePreparationError(
                f"source_row_identity_invalid:{index}:{exc.reason_code}"
            ) from exc
        rows.append(row)
    return tuple(rows)


def _validate_json_structural_limits(decoded_text: str) -> None:
    """在 JSON parser 建立物件前限制巢狀深度與根陣列列數。"""
    depth = 0
    in_string = False
    escaped = False
    root_is_array = decoded_text.lstrip().startswith("[")
    root_array_commas = 0
    for character in decoded_text:
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue
        if character == '"':
            in_string = True
        elif character in "[{":
            depth += 1
            if depth > MAX_JSON_NESTING_DEPTH:
                raise TwseMonthlyRevenuePreparationError(
                    "json_nesting_depth_exceeds_limit"
                )
        elif character in "]}":
            depth -= 1
        elif character == "," and root_is_array and depth == 1:
            root_array_commas += 1
            if root_array_commas + 1 > MAX_JSON_ROWS:
                raise TwseMonthlyRevenuePreparationError(
                    "json_row_count_exceeds_limit"
                )


def _reject_json_nonfinite_constant(token: str) -> Any:
    raise TwseMonthlyRevenuePreparationError("json_non_finite_constant")


def _parse_json_integer_token(token: str) -> int:
    parsed = _parse_bounded_decimal_token(token, label="json_number")
    return int(parsed)


def _parse_json_float_token(token: str) -> Decimal:
    return _parse_bounded_decimal_token(token, label="json_number")


def _unique_normalized_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, value in pairs:
        if not isinstance(key, str):
            raise TwseMonthlyRevenuePreparationError("json_key_not_text")
        cleaned = key.lstrip("\ufeff").strip()
        if not cleaned:
            raise TwseMonthlyRevenuePreparationError("json_key_empty_after_normalization")
        if cleaned in normalized:
            raise TwseMonthlyRevenuePreparationError("json_key_duplicate_after_normalization")
        normalized[cleaned] = value
    return normalized


def _row_identity(row: Mapping[str, Any]) -> tuple[str, str, str]:
    code = row.get("公司代號")
    raw_period = row.get("資料年月")
    if not isinstance(code, str) or not isinstance(raw_period, str):
        raise TwseMonthlyRevenuePreparationError("identity_fields_missing_or_non_text")
    normalized_code = code.strip()
    normalized_roc_period = raw_period.strip()
    if not _STOCK_CODE_RE.fullmatch(normalized_code):
        raise TwseMonthlyRevenuePreparationError("stock_code_invalid")
    if not _ROC_PERIOD_RE.fullmatch(normalized_roc_period):
        raise TwseMonthlyRevenuePreparationError("roc_period_invalid")
    try:
        normalized_period = parse_revenue_period(normalized_roc_period)
    except (TypeError, ValueError) as exc:
        raise TwseMonthlyRevenuePreparationError("roc_period_invalid") from exc
    return normalized_code, normalized_period, normalized_roc_period


def _required_target_values(row: Mapping[str, Any]) -> dict[str, str]:
    missing = [field for field in REQUIRED_TARGET_FIELDS if field not in row]
    if missing:
        raise TwseMonthlyRevenuePreparationError(
            "target_required_fields_missing:" + ",".join(missing)
        )
    non_text = [field for field in REQUIRED_TARGET_FIELDS if not isinstance(row[field], str)]
    if non_text:
        raise TwseMonthlyRevenuePreparationError(
            "target_required_fields_non_text:" + ",".join(non_text)
        )
    return {field: row[field] for field in REQUIRED_TARGET_FIELDS}


def _normalize_requested_period(period: str) -> tuple[str, str]:
    if not isinstance(period, str) or not re.fullmatch(r"\d{4}-\d{2}", period):
        raise TwseMonthlyRevenuePreparationError("requested_period_invalid")
    try:
        year_text, month_text = period.split("-")
        year = int(year_text)
        month = int(month_text)
        date(year, month, 1)
    except (TypeError, ValueError) as exc:
        raise TwseMonthlyRevenuePreparationError("requested_period_invalid") from exc
    if year < 1912:
        raise TwseMonthlyRevenuePreparationError("requested_period_out_of_range")
    normalized = f"{year:04d}-{month:02d}"
    roc_year = year - 1911
    if roc_year < 1 or roc_year > 999:
        raise TwseMonthlyRevenuePreparationError("requested_period_out_of_range")
    return normalized, f"{roc_year:03d}{month:02d}"


def _normalize_stock_code(stock_code: str) -> str:
    if not isinstance(stock_code, str):
        raise TwseMonthlyRevenuePreparationError("requested_stock_code_invalid")
    normalized = stock_code.strip()
    if not _STOCK_CODE_RE.fullmatch(normalized):
        raise TwseMonthlyRevenuePreparationError("requested_stock_code_invalid")
    return normalized


def _parse_finite_decimal(value: str, field: str) -> Decimal:
    cleaned = value.strip()
    if not cleaned:
        raise TwseMonthlyRevenuePreparationError(f"value_missing:{field}")
    if cleaned.casefold() in {
        "nan", "+nan", "-nan", "inf", "+inf", "-inf",
        "infinity", "+infinity", "-infinity",
    }:
        raise TwseMonthlyRevenuePreparationError(f"value_not_finite:{field}")
    return _parse_bounded_decimal_token(cleaned, label="value", field=field)


def _parse_bounded_decimal_token(
    token: str,
    *,
    label: str,
    field: str | None = None,
) -> Decimal:
    def fail(reason: str) -> TwseMonthlyRevenuePreparationError:
        suffix = f":{field}" if field is not None else ""
        return TwseMonthlyRevenuePreparationError(f"{label}_{reason}{suffix}")

    if len(token) > MAX_DECIMAL_TOKEN_CHARS:
        raise fail("decimal_token_too_long")
    match = _DECIMAL_TOKEN_RE.fullmatch(token)
    if match is None:
        if label == "value":
            raise TwseMonthlyRevenuePreparationError(f"value_invalid_decimal:{field}")
        raise fail("invalid_decimal")
    coefficient_digits = sum(
        len(match.group(name) or "") for name in ("whole", "fraction", "leading_fraction")
    )
    if coefficient_digits > MAX_DECIMAL_DIGITS:
        raise fail("decimal_digits_exceeded")
    exponent_text = match.group("exponent")
    if exponent_text is not None and abs(int(exponent_text)) > MAX_DECIMAL_ABS_EXPONENT:
        raise fail("decimal_exponent_exceeded")
    try:
        parsed = Decimal(token)
    except (InvalidOperation, ValueError) as exc:
        if label == "value":
            raise TwseMonthlyRevenuePreparationError(
                f"value_invalid_decimal:{field}"
            ) from exc
        raise fail("invalid_decimal") from exc
    if not parsed.is_finite():
        if label == "value":
            raise TwseMonthlyRevenuePreparationError(f"value_not_finite:{field}")
        raise fail("non_finite")
    return parsed


def _is_date_only_text(value: str) -> bool:
    return bool(_ROC_DATE_RE.fullmatch(value) or _ISO_DATE_RE.fullmatch(value))


def _require_aware_datetime(value: datetime, label: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise TwseMonthlyRevenuePreparationError(f"{label}_timezone_missing")
    try:
        if value.utcoffset() is None:
            raise TwseMonthlyRevenuePreparationError(f"{label}_timezone_missing")
    except (OverflowError, ValueError) as exc:
        raise TwseMonthlyRevenuePreparationError(f"{label}_timezone_invalid") from exc


def _datetime_text(value: datetime) -> str:
    _require_aware_datetime(value, "datetime")
    return value.astimezone(timezone.utc).isoformat()


_STOCK_CODE_RE = re.compile(r"\d{4,6}")
_ROC_PERIOD_RE = re.compile(r"\d{5}")
_ROC_DATE_RE = re.compile(r"\d{7}")
_ISO_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_DECIMAL_TOKEN_RE = re.compile(
    r"[+-]?(?:(?P<whole>\d+)(?:\.(?P<fraction>\d*))?|"
    r"\.(?P<leading_fraction>\d+))(?:[eE](?P<exponent>[+-]?\d+))?"
)
