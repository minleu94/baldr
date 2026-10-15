"""以原始回應保存候選 TWSE／TPEX 期間行事曆證據。"""

from __future__ import annotations

import base64
import binascii
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
import hashlib
import json
import math
import re
from typing import Literal, NoReturn, cast

from data_module.official_calendar_bundle import (
    MAX_CAPTURE_DAYS,
    MAX_FIXTURE_BYTES,
    TPEX_MARKET_CALENDAR_URL,
    TWSE_HOLIDAY_SCHEDULE_URL,
    CapturedCalendarResponse,
    OfficialCalendarBundleError,
    build_official_calendar_bundle,
    hash_response_bytes,
)


PORTFOLIO_PERIOD_CALENDAR_EVIDENCE_SCHEMA_V1 = "recommendation-portfolio-period-calendar-evidence.v1"
_MAX_RESPONSE_COUNT = 8
_MAX_EVIDENCE_BYTES = 128 * 1024 * 1024
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_RESPONSE_FIELDS = {
    "kind", "key", "source", "source_hash", "metadata", "payload", "raw_response_base64",
}
_EVIDENCE_FIELDS = {
    "schema_version", "start_date", "end_date", "captured_at", "capture_mode",
    "twse_responses", "tpex_responses", "expected_session_dates", "candidate_only",
    "historical_pit_eligible", "performance_eligible", "formal_clock_eligible", "evidence_sha256",
}


class PortfolioPeriodCalendarEvidenceV1Error(ValueError):
    """候選行事曆證據或其原始回應不符合有界 canonical 契約。"""


def _fail(reason: str) -> NoReturn:
    raise PortfolioPeriodCalendarEvidenceV1Error(reason)


def _canonical_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8", errors="strict")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise PortfolioPeriodCalendarEvidenceV1Error("value_is_not_canonical_json") from exc


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _reject_constant(value: str) -> NoReturn:
    raise PortfolioPeriodCalendarEvidenceV1Error(f"nonfinite_json_constant:{value}")


def _object_from_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            _fail("duplicate_json_key")
        result[key] = value
    return result


def _parse_json(raw: bytes, *, label: str) -> object:
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeError as exc:
        raise PortfolioPeriodCalendarEvidenceV1Error(f"{label}_invalid_utf8") from exc
    try:
        parsed = json.loads(
            text,
            object_pairs_hook=_object_from_pairs,
            parse_constant=_reject_constant,
        )
    except PortfolioPeriodCalendarEvidenceV1Error:
        raise
    except (json.JSONDecodeError, ValueError, RecursionError) as exc:
        raise PortfolioPeriodCalendarEvidenceV1Error(f"{label}_invalid_json") from exc
    try:
        _validate_json_value(parsed, label=label)
    except RecursionError as exc:
        raise PortfolioPeriodCalendarEvidenceV1Error(f"{label}_json_nesting_over_limit") from exc
    return parsed


def _validate_json_value(value: object, *, label: str) -> None:
    if value is None or type(value) in (str, bool, int):
        return
    if type(value) is float:
        if not math.isfinite(value):
            _fail(f"{label}_contains_nonfinite_number")
        return
    if isinstance(value, list):
        for item in value:
            _validate_json_value(item, label=label)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if type(key) is not str:
                _fail(f"{label}_object_key_invalid")
            _validate_json_value(item, label=label)
        return
    _fail(f"{label}_value_not_json_compatible")


def _plain_json_value(value: object, *, label: str) -> object:
    """複製 JSON 相容值，並拒絕會在序列化時遺失的 Python 型別。"""
    if value is None or type(value) in (str, bool, int):
        return value
    if type(value) is float:
        if not math.isfinite(value):
            _fail(f"{label}_contains_nonfinite_number")
        return value
    if isinstance(value, Mapping):
        copied: dict[str, object] = {}
        for key, item in value.items():
            if type(key) is not str or key in copied:
                _fail(f"{label}_object_key_invalid")
            copied[key] = _plain_json_value(item, label=label)
        return copied
    if isinstance(value, (list, tuple)):
        return [_plain_json_value(item, label=label) for item in value]
    _fail(f"{label}_value_not_json_compatible")


def _parse_date(value: object, *, label: str) -> date:
    if type(value) is not str:
        _fail(f"{label}_must_be_canonical_date_text")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise PortfolioPeriodCalendarEvidenceV1Error(f"{label}_invalid_date") from exc
    if parsed.isoformat() != value:
        _fail(f"{label}_must_be_canonical_date_text")
    return parsed


def _parse_captured_at(value: object) -> datetime:
    if type(value) is not str:
        _fail("captured_at_must_be_canonical_aware_datetime_text")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise PortfolioPeriodCalendarEvidenceV1Error("captured_at_invalid_datetime") from exc
    if parsed.isoformat() != value or parsed.tzinfo is None or parsed.utcoffset() is None:
        _fail("captured_at_must_be_canonical_aware_datetime_text")
    return parsed


def _expected_source(kind: str, key: str) -> str:
    if kind == "twse":
        if not re.fullmatch(r"[1-9][0-9]{3}", key):
            _fail("twse_key_invalid")
        year = int(key)
        roc_year = year - 1911
        if roc_year <= 0:
            _fail("twse_key_invalid")
        return f"{TWSE_HOLIDAY_SCHEDULE_URL}?queryYear={roc_year}"
    if kind == "tpex":
        if not re.fullmatch(r"[0-9]{6}", key):
            _fail("tpex_key_invalid")
        year, month = int(key[:4]), int(key[4:])
        if year < 1 or not 1 <= month <= 12:
            _fail("tpex_key_invalid")
        return f"{TPEX_MARKET_CALENDAR_URL}?ym={key}&lang=zh-tw"
    _fail("calendar_response_kind_invalid")


@dataclass(frozen=True, slots=True)
class _CalendarResponseEvidenceV1:
    kind: Literal["twse", "tpex"]
    key: str
    source: str
    source_hash: str
    raw_bytes: bytes
    payload_json: str
    metadata_json: str

    def __post_init__(self) -> None:
        if self.kind not in ("twse", "tpex"):
            _fail("calendar_response_kind_invalid")
        if type(self.key) is not str or not self.key:
            _fail("calendar_response_key_invalid")
        if self.source != _expected_source(self.kind, self.key):
            _fail("calendar_response_endpoint_or_period_mismatch")
        if type(self.source_hash) is not str or not re.fullmatch(r"sha256:[0-9a-f]{64}", self.source_hash):
            _fail("calendar_response_hash_invalid")
        if type(self.raw_bytes) is not bytes or not self.raw_bytes:
            _fail("calendar_response_raw_bytes_missing")
        if len(self.raw_bytes) > MAX_FIXTURE_BYTES:
            _fail("calendar_response_raw_bytes_over_limit")
        if hash_response_bytes(self.raw_bytes) != self.source_hash:
            _fail("calendar_response_raw_hash_mismatch")
        if type(self.payload_json) is not str or type(self.metadata_json) is not str:
            _fail("calendar_response_payload_or_metadata_encoding_invalid")
        payload_value = _parse_json(self.raw_bytes, label="calendar_response_raw")
        if _canonical_bytes(payload_value).decode("utf-8") != self.payload_json:
            _fail("calendar_response_payload_does_not_match_raw")
        metadata_value = _parse_json(self.metadata_json.encode("utf-8"), label="calendar_response_metadata")
        if metadata_value is not None and not isinstance(metadata_value, dict):
            _fail("calendar_response_metadata_must_be_object_or_null")
        if _canonical_bytes(metadata_value).decode("utf-8") != self.metadata_json:
            _fail("calendar_response_metadata_not_canonical")

    @classmethod
    def from_response(
        cls,
        response: CapturedCalendarResponse,
        *,
        expected_kind: Literal["twse", "tpex"],
        expected_key: str,
    ) -> _CalendarResponseEvidenceV1:
        if type(response) is not CapturedCalendarResponse:
            _fail("calendar_response_type_invalid")
        if response.kind != expected_kind or response.key != expected_key:
            _fail("calendar_response_identity_mismatch")
        source = _expected_source(expected_kind, expected_key)
        if response.source != source:
            _fail("calendar_response_endpoint_or_period_mismatch")
        raw = response.raw_bytes
        if type(raw) is not bytes or not raw:
            _fail("calendar_response_raw_bytes_missing")
        if len(raw) > MAX_FIXTURE_BYTES:
            _fail("calendar_response_raw_bytes_over_limit")
        parsed_raw = _parse_json(raw, label="calendar_response_raw")
        copied_payload = _plain_json_value(response.payload, label="calendar_response_payload")
        if _canonical_bytes(parsed_raw) != _canonical_bytes(copied_payload):
            _fail("calendar_response_payload_does_not_match_raw")
        metadata = _plain_json_value(response.metadata, label="calendar_response_metadata")
        if metadata is not None and not isinstance(metadata, dict):
            _fail("calendar_response_metadata_must_be_object_or_null")
        return cls(
            kind=expected_kind,
            key=expected_key,
            source=source,
            source_hash=response.source_hash,
            raw_bytes=raw,
            payload_json=_canonical_bytes(copied_payload).decode("utf-8"),
            metadata_json=_canonical_bytes(metadata).decode("utf-8"),
        )

    @classmethod
    def from_dict(cls, value: object, *, expected_kind: Literal["twse", "tpex"]) -> _CalendarResponseEvidenceV1:
        if not isinstance(value, dict) or set(value) != _RESPONSE_FIELDS:
            _fail("calendar_response_fields_invalid")
        kind = value.get("kind")
        key = value.get("key")
        source = value.get("source")
        source_hash = value.get("source_hash")
        encoded_raw = value.get("raw_response_base64")
        if type(kind) is not str or kind != expected_kind:
            _fail("calendar_response_kind_mismatch")
        if type(key) is not str or type(source) is not str or type(source_hash) is not str:
            _fail("calendar_response_identity_invalid")
        if type(encoded_raw) is not str:
            _fail("calendar_response_raw_base64_invalid")
        try:
            raw = base64.b64decode(encoded_raw, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise PortfolioPeriodCalendarEvidenceV1Error("calendar_response_raw_base64_invalid") from exc
        if base64.b64encode(raw).decode("ascii") != encoded_raw:
            _fail("calendar_response_raw_base64_noncanonical")
        payload = _plain_json_value(value.get("payload"), label="calendar_response_payload")
        metadata = _plain_json_value(value.get("metadata"), label="calendar_response_metadata")
        if metadata is not None and not isinstance(metadata, dict):
            _fail("calendar_response_metadata_must_be_object_or_null")
        parsed_raw = _parse_json(raw, label="calendar_response_raw")
        if _canonical_bytes(parsed_raw) != _canonical_bytes(payload):
            _fail("calendar_response_payload_does_not_match_raw")
        record = cls(
            kind=cast(Literal["twse", "tpex"], kind),
            key=key,
            source=source,
            source_hash=source_hash,
            raw_bytes=raw,
            payload_json=_canonical_bytes(payload).decode("utf-8"),
            metadata_json=_canonical_bytes(metadata).decode("utf-8"),
        )
        return record

    def to_dict(self) -> dict[str, object]:
        payload = _parse_json(self.payload_json.encode("utf-8"), label="calendar_response_payload")
        metadata = _parse_json(self.metadata_json.encode("utf-8"), label="calendar_response_metadata")
        return {
            "kind": self.kind,
            "key": self.key,
            "source": self.source,
            "source_hash": self.source_hash,
            "metadata": metadata,
            "payload": payload,
            "raw_response_base64": base64.b64encode(self.raw_bytes).decode("ascii"),
        }

    def to_response(self) -> CapturedCalendarResponse:
        payload = _parse_json(self.payload_json.encode("utf-8"), label="calendar_response_payload")
        metadata_value = _parse_json(self.metadata_json.encode("utf-8"), label="calendar_response_metadata")
        metadata = cast(Mapping[str, object] | None, metadata_value)
        return CapturedCalendarResponse(
            kind=self.kind,
            key=self.key,
            source=self.source,
            source_hash=self.source_hash,
            payload=payload,
            raw_bytes=self.raw_bytes,
            metadata=metadata,
        )


def _response_records_from_mappings(
    twse_responses: Mapping[int, CapturedCalendarResponse],
    tpex_responses: Mapping[str, CapturedCalendarResponse],
) -> tuple[tuple[_CalendarResponseEvidenceV1, ...], tuple[_CalendarResponseEvidenceV1, ...]]:
    if not isinstance(twse_responses, Mapping) or not twse_responses:
        _fail("twse_responses_must_be_nonempty_mapping")
    if not isinstance(tpex_responses, Mapping) or not tpex_responses:
        _fail("tpex_responses_must_be_nonempty_mapping")
    twse_items = list(twse_responses.items())
    tpex_items = list(tpex_responses.items())
    if len(twse_items) + len(tpex_items) > _MAX_RESPONSE_COUNT:
        _fail("calendar_response_count_over_limit")
    twse_records: list[_CalendarResponseEvidenceV1] = []
    tpex_records: list[_CalendarResponseEvidenceV1] = []
    for key, response in twse_items:
        if type(key) is not int:
            _fail("twse_response_mapping_key_invalid")
        twse_records.append(_CalendarResponseEvidenceV1.from_response(
            response, expected_kind="twse", expected_key=str(key)))
    for key, response in tpex_items:
        if type(key) is not str:
            _fail("tpex_response_mapping_key_invalid")
        tpex_records.append(_CalendarResponseEvidenceV1.from_response(
            response, expected_kind="tpex", expected_key=key))
    twse_records.sort(key=lambda item: int(item.key))
    tpex_records.sort(key=lambda item: item.key)
    identities = [(item.kind, item.key) for item in (*twse_records, *tpex_records)]
    if len(set(identities)) != len(identities):
        _fail("calendar_response_identity_duplicated")
    return tuple(twse_records), tuple(tpex_records)


def _derive_session_dates(
    *,
    start_date: date,
    end_date: date,
    captured_at: datetime,
    capture_mode: str,
    twse_records: tuple[_CalendarResponseEvidenceV1, ...],
    tpex_records: tuple[_CalendarResponseEvidenceV1, ...],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    twse = {int(item.key): item.to_response() for item in twse_records}
    tpex = {item.key: item.to_response() for item in tpex_records}
    try:
        bundle = build_official_calendar_bundle(
            start_date=start_date,
            end_date=end_date,
            twse_responses=twse,
            tpex_responses=tpex,
            capture_mode=capture_mode,
            network_enabled=capture_mode in {"bounded_network", "mixed"},
            captured_at=captured_at,
        )
    except OfficialCalendarBundleError as exc:
        raise PortfolioPeriodCalendarEvidenceV1Error(f"official_calendar_builder_rejected:{exc}") from exc
    if bundle.get("candidate_only") is not True or bundle.get("formal_clock_created") is not False:
        _fail("official_calendar_builder_candidate_contract_mismatch")
    days = bundle.get("days")
    if not isinstance(days, list):
        _fail("official_calendar_builder_days_invalid")
    twse_dates: list[str] = []
    tpex_dates: list[str] = []
    for item in days:
        if not isinstance(item, dict):
            _fail("official_calendar_builder_day_invalid")
        day_text = item.get("date")
        twse_value = item.get("twse")
        tpex_value = item.get("tpex")
        if type(day_text) is not str or not isinstance(twse_value, dict) or not isinstance(tpex_value, dict):
            _fail("official_calendar_builder_day_invalid")
        if twse_value.get("is_trading_day") is True:
            twse_dates.append(day_text)
        if tpex_value.get("is_trading_day") is True:
            tpex_dates.append(day_text)
    return tuple(twse_dates), tuple(tpex_dates)


def _body_dict(
    *,
    start_date: str,
    end_date: str,
    captured_at: str,
    capture_mode: str,
    twse_records: tuple[_CalendarResponseEvidenceV1, ...],
    tpex_records: tuple[_CalendarResponseEvidenceV1, ...],
    twse_session_dates: tuple[str, ...],
    tpex_session_dates: tuple[str, ...],
) -> dict[str, object]:
    return {
        "schema_version": PORTFOLIO_PERIOD_CALENDAR_EVIDENCE_SCHEMA_V1,
        "start_date": start_date,
        "end_date": end_date,
        "captured_at": captured_at,
        "capture_mode": capture_mode,
        "twse_responses": [item.to_dict() for item in twse_records],
        "tpex_responses": [item.to_dict() for item in tpex_records],
        "expected_session_dates": {
            "twse": list(twse_session_dates),
            "tpex": list(tpex_session_dates),
        },
        "candidate_only": True,
        "historical_pit_eligible": False,
        "performance_eligible": False,
        "formal_clock_eligible": False,
    }


@dataclass(frozen=True, slots=True)
class PortfolioPeriodCalendarEvidenceV1:
    """完整保存原始回應並重算的候選期間日曆，不授予時鐘或績效資格。"""

    schema_version: str
    start_date: str
    end_date: str
    captured_at: str
    capture_mode: str
    _twse_records: tuple[_CalendarResponseEvidenceV1, ...]
    _tpex_records: tuple[_CalendarResponseEvidenceV1, ...]
    _twse_session_dates: tuple[str, ...]
    _tpex_session_dates: tuple[str, ...]
    evidence_sha256: str
    candidate_only: Literal[True] = field(default=True, init=False)
    historical_pit_eligible: Literal[False] = field(default=False, init=False)
    performance_eligible: Literal[False] = field(default=False, init=False)
    formal_clock_eligible: Literal[False] = field(default=False, init=False)

    def __post_init__(self) -> None:
        self._validate()

    @classmethod
    def build(
        cls,
        *,
        start_date: date,
        end_date: date,
        twse_responses: Mapping[int, CapturedCalendarResponse],
        tpex_responses: Mapping[str, CapturedCalendarResponse],
        captured_at: datetime,
        capture_mode: str = "fixture_only",
    ) -> PortfolioPeriodCalendarEvidenceV1:
        if type(start_date) is not date or type(end_date) is not date:
            _fail("start_date_end_date_must_be_dates")
        if end_date < start_date:
            _fail("end_date_precedes_start_date")
        if (end_date - start_date).days + 1 > MAX_CAPTURE_DAYS:
            _fail("calendar_range_over_93_days")
        if not isinstance(captured_at, datetime) or captured_at.tzinfo is None or captured_at.utcoffset() is None:
            _fail("captured_at_must_be_timezone_aware")
        if type(capture_mode) is not str or capture_mode not in {"fixture_only", "bounded_network", "mixed"}:
            _fail("capture_mode_invalid")
        twse_records, tpex_records = _response_records_from_mappings(twse_responses, tpex_responses)
        twse_dates, tpex_dates = _derive_session_dates(
            start_date=start_date,
            end_date=end_date,
            captured_at=captured_at,
            capture_mode=capture_mode,
            twse_records=twse_records,
            tpex_records=tpex_records,
        )
        start_text, end_text, captured_text = start_date.isoformat(), end_date.isoformat(), captured_at.isoformat()
        body = _body_dict(
            start_date=start_text,
            end_date=end_text,
            captured_at=captured_text,
            capture_mode=capture_mode,
            twse_records=twse_records,
            tpex_records=tpex_records,
            twse_session_dates=twse_dates,
            tpex_session_dates=tpex_dates,
        )
        evidence = cls(
            schema_version=PORTFOLIO_PERIOD_CALENDAR_EVIDENCE_SCHEMA_V1,
            start_date=start_text,
            end_date=end_text,
            captured_at=captured_text,
            capture_mode=capture_mode,
            _twse_records=twse_records,
            _tpex_records=tpex_records,
            _twse_session_dates=twse_dates,
            _tpex_session_dates=tpex_dates,
            evidence_sha256=_sha256(_canonical_bytes(body)),
        )
        evidence.to_json()
        return evidence

    def _validate(self) -> None:
        if self.schema_version != PORTFOLIO_PERIOD_CALENDAR_EVIDENCE_SCHEMA_V1:
            _fail("calendar_evidence_schema_version_invalid")
        start = _parse_date(self.start_date, label="start_date")
        end = _parse_date(self.end_date, label="end_date")
        captured = _parse_captured_at(self.captured_at)
        if end < start or (end - start).days + 1 > MAX_CAPTURE_DAYS:
            _fail("calendar_range_invalid")
        if type(self.capture_mode) is not str or self.capture_mode not in {"fixture_only", "bounded_network", "mixed"}:
            _fail("capture_mode_invalid")
        if (type(self._twse_records) is not tuple or type(self._tpex_records) is not tuple
                or type(self._twse_session_dates) is not tuple or type(self._tpex_session_dates) is not tuple):
            _fail("calendar_evidence_collections_must_be_immutable_tuples")
        if len(self._twse_records) == 0 or len(self._tpex_records) == 0:
            _fail("calendar_responses_must_cover_both_markets")
        if len(self._twse_records) + len(self._tpex_records) > _MAX_RESPONSE_COUNT:
            _fail("calendar_response_count_over_limit")
        for record in self._twse_records:
            if type(record) is not _CalendarResponseEvidenceV1 or record.kind != "twse":
                _fail("twse_response_record_invalid")
        for record in self._tpex_records:
            if type(record) is not _CalendarResponseEvidenceV1 or record.kind != "tpex":
                _fail("tpex_response_record_invalid")
        identities = [(item.kind, item.key) for item in (*self._twse_records, *self._tpex_records)]
        if len(set(identities)) != len(identities):
            _fail("calendar_response_identity_duplicated")
        if (tuple(sorted(self._twse_records, key=lambda item: int(item.key))) != self._twse_records
                or tuple(sorted(self._tpex_records, key=lambda item: item.key)) != self._tpex_records):
            _fail("calendar_response_order_noncanonical")
        expected_twse, expected_tpex = _derive_session_dates(
            start_date=start,
            end_date=end,
            captured_at=captured,
            capture_mode=self.capture_mode,
            twse_records=self._twse_records,
            tpex_records=self._tpex_records,
        )
        if expected_twse != self._twse_session_dates or expected_tpex != self._tpex_session_dates:
            _fail("calendar_session_dates_do_not_match_original_responses")
        if (self.candidate_only is not True or self.historical_pit_eligible is not False
                or self.performance_eligible is not False or self.formal_clock_eligible is not False):
            _fail("calendar_evidence_qualification_flags_invalid")
        if type(self.evidence_sha256) is not str or _SHA256_PATTERN.fullmatch(self.evidence_sha256) is None:
            _fail("calendar_evidence_sha256_invalid")
        body = _body_dict(
            start_date=self.start_date,
            end_date=self.end_date,
            captured_at=self.captured_at,
            capture_mode=self.capture_mode,
            twse_records=self._twse_records,
            tpex_records=self._tpex_records,
            twse_session_dates=self._twse_session_dates,
            tpex_session_dates=self._tpex_session_dates,
        )
        if _sha256(_canonical_bytes(body)) != self.evidence_sha256:
            _fail("calendar_evidence_sha256_mismatch")

    def expected_session_dates(self, market: Literal["twse", "tpex"]) -> tuple[str, ...]:
        self._validate()
        if market == "twse":
            return self._twse_session_dates
        if market == "tpex":
            return self._tpex_session_dates
        _fail("calendar_market_invalid")

    def to_dict(self) -> dict[str, object]:
        self._validate()
        body = _body_dict(
            start_date=self.start_date,
            end_date=self.end_date,
            captured_at=self.captured_at,
            capture_mode=self.capture_mode,
            twse_records=self._twse_records,
            tpex_records=self._tpex_records,
            twse_session_dates=self._twse_session_dates,
            tpex_session_dates=self._tpex_session_dates,
        )
        body["evidence_sha256"] = self.evidence_sha256
        return body

    def to_json(self) -> str:
        self._validate()
        raw = _canonical_bytes(self.to_dict())
        if len(raw) > _MAX_EVIDENCE_BYTES:
            _fail("calendar_evidence_over_byte_limit")
        return raw.decode("utf-8")

    @classmethod
    def from_json(cls, raw: str | bytes) -> PortfolioPeriodCalendarEvidenceV1:
        if type(raw) is str:
            try:
                encoded = raw.encode("utf-8", errors="strict")
            except UnicodeError as exc:
                raise PortfolioPeriodCalendarEvidenceV1Error("calendar_evidence_invalid_utf8") from exc
        elif type(raw) is bytes:
            encoded = raw
        else:
            _fail("calendar_evidence_json_type_invalid")
        if not encoded or len(encoded) > _MAX_EVIDENCE_BYTES:
            _fail("calendar_evidence_size_invalid")
        value = _parse_json(encoded, label="calendar_evidence")
        if not isinstance(value, dict) or set(value) != _EVIDENCE_FIELDS:
            _fail("calendar_evidence_fields_invalid")
        if _canonical_bytes(value) != encoded:
            _fail("calendar_evidence_json_not_canonical")
        if value.get("schema_version") != PORTFOLIO_PERIOD_CALENDAR_EVIDENCE_SCHEMA_V1:
            _fail("calendar_evidence_schema_version_invalid")
        digest = value.get("evidence_sha256")
        if type(digest) is not str or _SHA256_PATTERN.fullmatch(digest) is None:
            _fail("calendar_evidence_sha256_invalid")
        body = dict(value)
        del body["evidence_sha256"]
        if _sha256(_canonical_bytes(body)) != digest:
            _fail("calendar_evidence_sha256_mismatch")
        start_value, end_value = value.get("start_date"), value.get("end_date")
        captured_value, mode_value = value.get("captured_at"), value.get("capture_mode")
        if type(start_value) is not str or type(end_value) is not str or type(captured_value) is not str or type(mode_value) is not str:
            _fail("calendar_evidence_header_invalid")
        _parse_date(start_value, label="start_date")
        _parse_date(end_value, label="end_date")
        _parse_captured_at(captured_value)
        twse_values, tpex_values = value.get("twse_responses"), value.get("tpex_responses")
        if not isinstance(twse_values, list) or not isinstance(tpex_values, list):
            _fail("calendar_response_arrays_invalid")
        if len(twse_values) == 0 or len(tpex_values) == 0 or len(twse_values) + len(tpex_values) > _MAX_RESPONSE_COUNT:
            _fail("calendar_response_count_invalid")
        twse_records = tuple(_CalendarResponseEvidenceV1.from_dict(item, expected_kind="twse") for item in twse_values)
        tpex_records = tuple(_CalendarResponseEvidenceV1.from_dict(item, expected_kind="tpex") for item in tpex_values)
        if tuple(sorted(twse_records, key=lambda item: int(item.key))) != twse_records:
            _fail("twse_response_order_noncanonical")
        if tuple(sorted(tpex_records, key=lambda item: item.key)) != tpex_records:
            _fail("tpex_response_order_noncanonical")
        dates_value = value.get("expected_session_dates")
        if not isinstance(dates_value, dict) or set(dates_value) != {"twse", "tpex"}:
            _fail("calendar_session_dates_shape_invalid")
        twse_dates_value, tpex_dates_value = dates_value.get("twse"), dates_value.get("tpex")
        if not isinstance(twse_dates_value, list) or not isinstance(tpex_dates_value, list):
            _fail("calendar_session_dates_shape_invalid")
        twse_dates = tuple(cast(str, item) for item in twse_dates_value)
        tpex_dates = tuple(cast(str, item) for item in tpex_dates_value)
        if any(type(item) is not str for item in (*twse_dates_value, *tpex_dates_value)):
            _fail("calendar_session_date_invalid")
        for item in (*twse_dates, *tpex_dates):
            _parse_date(item, label="session_date")
        if value.get("candidate_only") is not True or value.get("historical_pit_eligible") is not False or value.get("performance_eligible") is not False or value.get("formal_clock_eligible") is not False:
            _fail("calendar_evidence_qualification_flags_invalid")
        instance = cls(
            schema_version=cast(str, value.get("schema_version")),
            start_date=start_value,
            end_date=end_value,
            captured_at=captured_value,
            capture_mode=mode_value,
            _twse_records=twse_records,
            _tpex_records=tpex_records,
            _twse_session_dates=twse_dates,
            _tpex_session_dates=tpex_dates,
            evidence_sha256=digest,
        )
        return instance
