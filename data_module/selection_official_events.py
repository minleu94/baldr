"""現行 TWSE／TPEx 官方處置來源的有界唯讀投影。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
from typing import Literal, Mapping, Sequence
from zoneinfo import ZoneInfo

from data_module.current_market_status_observation import (
    CurrentMarketStatusError,
    CurrentMarketStatusReader,
    parse_source_date,
)
from data_module.p0_official_source_parsers import RawFetchEnvelope, parse_twse_disposition


OFFICIAL_DISPOSAL_PIN_SCHEMA: Literal["selection-official-disposal-source-pin.v2"] = (
    "selection-official-disposal-source-pin.v2"
)
OFFICIAL_DISPOSAL_SCOPE: Literal["current_only"] = "current_only"
OFFICIAL_DISPOSAL_PIT_ELIGIBLE: Literal[False] = False
OFFICIAL_DISPOSAL_PARSER_VERSION: Literal["selection-official-disposal-parser.v2"] = (
    "selection-official-disposal-parser.v2"
)
TPEX_ROW_SCHEMA_VERSION: Literal["tpex-disposal-openapi-row-contract.v2"] = (
    "tpex-disposal-openapi-row-contract.v2"
)
TPEX_RESPONSE_ENVELOPE_VERSION: Literal["tpex-disposal-json-array-envelope.v1"] = (
    "tpex-disposal-json-array-envelope.v1"
)
TPEX_OPENAPI_SWAGGER_SHA256: Literal[
    "sha256:05af7755d0d528626c104f7a8ccd7b00c6a0cf228d30bcb4669020e514eb0c7e"
] = "sha256:05af7755d0d528626c104f7a8ccd7b00c6a0cf228d30bcb4669020e514eb0c7e"
TPEX_OPENAPI_SWAGGER_COMPLETED_AT: Literal["2026-09-30T22:38:52.420371+00:00"] = (
    "2026-09-30T22:38:52.420371+00:00"
)
TPEX_ENDPOINT_EVIDENCE_DATE: Literal["2026-10-04"] = "2026-10-04"
TPEX_ROW_FIELDS: tuple[str, ...] = (
    "CompanyName",
    "Date",
    "DisposalCondition",
    "DispositionPeriod",
    "DispositionReasons",
    "SecuritiesCompanyCode",
)
MAX_POINTER_BYTES = 128 * 1024
MAX_MANIFEST_BYTES = 4 * 1024 * 1024
MAX_SNAPSHOT_BYTES = 32 * 1024 * 1024
MAX_RAW_SOURCE_BYTES = 8 * 1024 * 1024
MAX_SOURCE_PIN_BYTES = 256 * 1024
MAX_DISPOSAL_ROWS = 25_000
READ_CHUNK_BYTES = 1024 * 1024
_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_SYMBOL_RE = re.compile(r"^[0-9]{4,6}$")
_RUN_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,96}$")
_WINDOWS_REPARSE_POINT = 0x400
_TAIPEI = ZoneInfo("Asia/Taipei")

_SOURCE_MARKETS: tuple[tuple[str, str, str], ...] = (
    (
        "twse.disposition_current",
        "twse",
        "https://openapi.twse.com.tw/v1/announcement/punish",
    ),
    (
        "tpex.disposition_current",
        "tpex",
        "https://www.tpex.org.tw/openapi/v1/tpex_disposal_information",
    ),
)
_SOURCE_BY_ID = {source_id: (market, url) for source_id, market, url in _SOURCE_MARKETS}
_TPEX_ROW_FIELD_SET = frozenset(TPEX_ROW_FIELDS)
_TPEx_DATE_RANGE_RE = re.compile(r"^\s*(.+?)\s*[~～]\s*(.+?)\s*$")


class SelectionOfficialEventError(ValueError):
    """固定代碼的處置來源身份或保存資料驗證錯誤。"""

    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)


@dataclass(frozen=True, slots=True)
class OfficialDisposalCaptureReferenceV1:
    """一個市場來源在單一保存 run 中的精確 capture pin。"""

    source_id: str
    market: Literal["twse", "tpex"]
    status: str
    parse_status: str | None
    requested_url: str | None
    final_url: str | None
    raw_relative_path: str | None
    raw_sha256: str | None
    raw_bytes: int | None
    captured_at: str | None
    source_data_dates: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "source_id": self.source_id,
            "market": self.market,
            "status": self.status,
            "parse_status": self.parse_status,
            "requested_url": self.requested_url,
            "final_url": self.final_url,
            "raw_relative_path": self.raw_relative_path,
            "raw_sha256": self.raw_sha256,
            "raw_bytes": self.raw_bytes,
            "captured_at": self.captured_at,
            "source_data_dates": list(self.source_data_dates),
        }


@dataclass(frozen=True, slots=True)
class CurrentOfficialDisposalSourcePinV1:
    """固定 pointer 當時所指的 immutable run；不會在重開時追到新 pointer。"""

    output_root: str
    pointer_sha256: str
    pointer_published_at: str
    run_id: str
    snapshot_relative_path: str
    snapshot_sha256: str
    manifest_relative_path: str
    manifest_sha256: str
    snapshot_observed_at: str
    snapshot_partial_failure: bool
    captures: tuple[OfficialDisposalCaptureReferenceV1, ...]
    reader_parser_version: Literal["selection-official-disposal-parser.v2"] = (
        OFFICIAL_DISPOSAL_PARSER_VERSION
    )
    tpex_source_schema_version: Literal["tpex-disposal-openapi-row-contract.v2"] = (
        TPEX_ROW_SCHEMA_VERSION
    )
    tpex_response_envelope_version: Literal["tpex-disposal-json-array-envelope.v1"] = (
        TPEX_RESPONSE_ENVELOPE_VERSION
    )
    tpex_openapi_swagger_sha256: Literal[
        "sha256:05af7755d0d528626c104f7a8ccd7b00c6a0cf228d30bcb4669020e514eb0c7e"
    ] = TPEX_OPENAPI_SWAGGER_SHA256
    tpex_openapi_swagger_completed_at: Literal["2026-09-30T22:38:52.420371+00:00"] = (
        TPEX_OPENAPI_SWAGGER_COMPLETED_AT
    )
    tpex_endpoint_evidence_date: Literal["2026-10-04"] = TPEX_ENDPOINT_EVIDENCE_DATE
    schema_version: Literal["selection-official-disposal-source-pin.v2"] = (
        OFFICIAL_DISPOSAL_PIN_SCHEMA
    )
    scope: Literal["current_only"] = OFFICIAL_DISPOSAL_SCOPE
    historical_pit_eligible: Literal[False] = OFFICIAL_DISPOSAL_PIT_ELIGIBLE

    def _identity_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "scope": self.scope,
            "historical_pit_eligible": self.historical_pit_eligible,
            "output_root": self.output_root,
            "pointer_sha256": self.pointer_sha256,
            "pointer_published_at": self.pointer_published_at,
            "run_id": self.run_id,
            "snapshot_relative_path": self.snapshot_relative_path,
            "snapshot_sha256": self.snapshot_sha256,
            "manifest_relative_path": self.manifest_relative_path,
            "manifest_sha256": self.manifest_sha256,
            "snapshot_observed_at": self.snapshot_observed_at,
            "snapshot_partial_failure": self.snapshot_partial_failure,
            "captures": [item.to_dict() for item in self.captures],
            "reader_parser_version": self.reader_parser_version,
            "tpex_source_schema_version": self.tpex_source_schema_version,
            "tpex_response_envelope_version": self.tpex_response_envelope_version,
            "tpex_openapi_swagger_sha256": self.tpex_openapi_swagger_sha256,
            "tpex_openapi_swagger_completed_at": self.tpex_openapi_swagger_completed_at,
            "tpex_endpoint_evidence_date": self.tpex_endpoint_evidence_date,
        }

    @property
    def identity_sha256(self) -> str:
        return _canonical_sha256(self._identity_payload())

    def to_dict(self) -> dict[str, object]:
        result = self._identity_payload()
        result["identity_sha256"] = self.identity_sha256
        return result

    def to_json(self) -> str:
        return _canonical_json(self.to_dict())

    @classmethod
    def from_json(cls, raw: str | bytes) -> "CurrentOfficialDisposalSourcePinV1":
        encoded = raw.encode("utf-8") if isinstance(raw, str) else raw
        if len(encoded) > MAX_SOURCE_PIN_BYTES:
            raise SelectionOfficialEventError("source_pin_exceeds_size_limit")
        try:
            payload = _strict_json_loads(encoded)
        except (UnicodeError, ValueError, json.JSONDecodeError) as error:
            raise SelectionOfficialEventError("source_pin_json_invalid") from error
        return cls.from_dict(payload)

    @classmethod
    def from_dict(cls, payload: object) -> "CurrentOfficialDisposalSourcePinV1":
        if not isinstance(payload, Mapping):
            raise SelectionOfficialEventError("source_pin_must_be_object")
        required = {
            "schema_version",
            "scope",
            "historical_pit_eligible",
            "output_root",
            "pointer_sha256",
            "pointer_published_at",
            "run_id",
            "snapshot_relative_path",
            "snapshot_sha256",
            "manifest_relative_path",
            "manifest_sha256",
            "snapshot_observed_at",
            "snapshot_partial_failure",
            "captures",
            "reader_parser_version",
            "tpex_source_schema_version",
            "tpex_response_envelope_version",
            "tpex_openapi_swagger_sha256",
            "tpex_openapi_swagger_completed_at",
            "tpex_endpoint_evidence_date",
            "identity_sha256",
        }
        if set(payload) != required:
            raise SelectionOfficialEventError("source_pin_keys_invalid")
        raw_captures = payload.get("captures")
        if not isinstance(raw_captures, list) or len(raw_captures) != len(_SOURCE_MARKETS):
            raise SelectionOfficialEventError("source_pin_captures_invalid")
        captures = tuple(_capture_reference_from_dict(item) for item in raw_captures)
        value = cls(
            output_root=_required_text(payload, "output_root"),
            pointer_sha256=_required_hash(payload, "pointer_sha256"),
            pointer_published_at=_required_aware_timestamp(payload, "pointer_published_at"),
            run_id=_required_text(payload, "run_id"),
            snapshot_relative_path=_required_text(payload, "snapshot_relative_path"),
            snapshot_sha256=_required_hash(payload, "snapshot_sha256"),
            manifest_relative_path=_required_text(payload, "manifest_relative_path"),
            manifest_sha256=_required_hash(payload, "manifest_sha256"),
            snapshot_observed_at=_required_aware_timestamp(payload, "snapshot_observed_at"),
            snapshot_partial_failure=_required_bool(payload, "snapshot_partial_failure"),
            captures=captures,
        )
        if (
            payload.get("schema_version") != OFFICIAL_DISPOSAL_PIN_SCHEMA
            or payload.get("scope") != OFFICIAL_DISPOSAL_SCOPE
            or payload.get("historical_pit_eligible") is not False
            or payload.get("reader_parser_version") != OFFICIAL_DISPOSAL_PARSER_VERSION
            or payload.get("tpex_source_schema_version") != TPEX_ROW_SCHEMA_VERSION
            or payload.get("tpex_response_envelope_version")
            != TPEX_RESPONSE_ENVELOPE_VERSION
            or payload.get("tpex_openapi_swagger_sha256")
            != TPEX_OPENAPI_SWAGGER_SHA256
            or payload.get("tpex_openapi_swagger_completed_at")
            != TPEX_OPENAPI_SWAGGER_COMPLETED_AT
            or payload.get("tpex_endpoint_evidence_date")
            != TPEX_ENDPOINT_EVIDENCE_DATE
            or payload.get("identity_sha256") != value.identity_sha256
        ):
            raise SelectionOfficialEventError("source_pin_identity_invalid")
        _validate_pin_shape(value)
        return value


@dataclass(frozen=True, slots=True)
class OfficialDisposalEventV1:
    symbol: str
    market: Literal["twse", "tpex"]
    source_id: str
    announcement_date: date
    effective_from: date
    effective_to: date
    observed_at: datetime
    observed_date: date
    state: Literal[
        "announced_not_yet_effective",
        "effective_in_reported_period",
        "reported_period_elapsed",
    ]
    name: str | None
    reason: str | None
    measure: str | None
    details: str | None
    source_data_dates: tuple[str, ...]
    raw_sha256: str
    raw_row_sha256: str
    official_available_at: None = None
    availability_basis: Literal["announcement_date_only_first_observed_not_official_time"] = (
        "announcement_date_only_first_observed_not_official_time"
    )
    scope: Literal["current_only"] = OFFICIAL_DISPOSAL_SCOPE
    historical_pit_eligible: Literal[False] = OFFICIAL_DISPOSAL_PIT_ELIGIBLE

    def to_dict(self) -> dict[str, object]:
        return {
            "symbol": self.symbol,
            "market": self.market,
            "source_id": self.source_id,
            "announcement_date": self.announcement_date.isoformat(),
            "effective_from": self.effective_from.isoformat(),
            "effective_to": self.effective_to.isoformat(),
            "observed_at": self.observed_at.isoformat(),
            "observed_date": self.observed_date.isoformat(),
            "state": self.state,
            "name": self.name,
            "reason": self.reason,
            "measure": self.measure,
            "details": self.details,
            "source_data_dates": list(self.source_data_dates),
            "raw_sha256": self.raw_sha256,
            "raw_row_sha256": self.raw_row_sha256,
            "official_available_at": None,
            "availability_basis": self.availability_basis,
            "scope": self.scope,
            "historical_pit_eligible": self.historical_pit_eligible,
        }


@dataclass(frozen=True, slots=True)
class CurrentOfficialDisposalObservationV1:
    symbol: str
    market: Literal["twse", "tpex"]
    state: Literal[
        "reported_upcoming",
        "reported_active",
        "reported_elapsed_only",
        "unknown",
    ]
    observed_at: datetime | None
    observed_date: date | None
    events: tuple[OfficialDisposalEventV1, ...]
    source_data_dates: tuple[str, ...]
    source_id: str | None
    source_status: str
    source_parse_status: str | None
    source_raw_sha256: str | None
    source_pin_sha256: str
    reason_code: str | None
    source_warnings: tuple[str, ...]
    partial_failure: bool
    scope: Literal["current_only"] = OFFICIAL_DISPOSAL_SCOPE
    historical_pit_eligible: Literal[False] = OFFICIAL_DISPOSAL_PIT_ELIGIBLE


@dataclass(frozen=True, slots=True)
class _ParsedFeed:
    events_by_symbol: Mapping[str, tuple[OfficialDisposalEventV1, ...]]
    global_issues: tuple[str, ...]
    symbol_issues: Mapping[str, tuple[str, ...]]
    parser_version: str


class CurrentOfficialDisposalReader:
    """讀固定 current capture 的正面處置證據；缺列不轉成安全狀態。"""

    def __init__(
        self,
        source_pin: CurrentOfficialDisposalSourcePinV1,
        feeds: Mapping[str, _ParsedFeed],
    ) -> None:
        self.source_pin = source_pin
        self._captures = {item.source_id: item for item in source_pin.captures}
        self._feeds = dict(feeds)

    @classmethod
    def from_pointer(
        cls,
        pointer_path: str | Path,
        *,
        cutoff_at: datetime | None = None,
    ) -> "CurrentOfficialDisposalReader":
        cutoff = _resolve_read_cutoff(cutoff_at, read_now=_read_now_utc())
        pointer = _absolute_path(pointer_path, "pointer_path_invalid")
        _require_pointer_location(pointer)
        pointer_raw = _read_bounded_regular_file(pointer, MAX_POINTER_BYTES, "pointer")
        pointer_payload = _load_object(pointer_raw, "pointer_json_invalid")
        output_root = pointer.parent
        _validate_pointer_payload(pointer_payload, output_root)
        snapshot_path = _path_from_relative(output_root, _required_text(pointer_payload, "snapshot_path"))
        manifest_path = _path_from_relative(output_root, _required_text(pointer_payload, "manifest_path"))
        snapshot_raw = _read_bounded_regular_file(snapshot_path, MAX_SNAPSHOT_BYTES, "snapshot")
        manifest_raw = _read_bounded_regular_file(manifest_path, MAX_MANIFEST_BYTES, "manifest")
        snapshot_payload = _load_object(snapshot_raw, "snapshot_json_invalid")
        manifest_payload = _load_object(manifest_raw, "manifest_json_invalid")
        pin = _build_pin(
            output_root=output_root,
            pointer_raw=pointer_raw,
            pointer_payload=pointer_payload,
            snapshot_raw=snapshot_raw,
            snapshot_payload=snapshot_payload,
            manifest_raw=manifest_raw,
            manifest_payload=manifest_payload,
        )
        return cls._from_verified_pin(
            pin,
            pointer_payload=pointer_payload,
            cutoff_at=cutoff,
        )

    @classmethod
    def from_exact(
        cls,
        source_pin: CurrentOfficialDisposalSourcePinV1 | Mapping[str, object],
        *,
        cutoff_at: datetime | None = None,
    ) -> "CurrentOfficialDisposalReader":
        cutoff = _resolve_read_cutoff(cutoff_at, read_now=_read_now_utc())
        pin = (
            source_pin
            if isinstance(source_pin, CurrentOfficialDisposalSourcePinV1)
            else CurrentOfficialDisposalSourcePinV1.from_dict(source_pin)
        )
        _validate_pin_shape(pin)
        return cls._from_verified_pin(
            pin,
            pointer_payload=None,
            cutoff_at=cutoff,
        )

    @classmethod
    def _from_verified_pin(
        cls,
        pin: CurrentOfficialDisposalSourcePinV1,
        *,
        pointer_payload: Mapping[str, object] | None,
        cutoff_at: datetime,
    ) -> "CurrentOfficialDisposalReader":
        _validate_pin_timestamps_before_cutoff(pin, cutoff_at)
        snapshot, captures = _verify_exact_references(pin, pointer_payload=pointer_payload)
        try:
            # 共用 reader 只核 current-only snapshot DTO；raw bytes、manifest 對應及路徑
            # 已由本 adapter 以有界讀取逐項核驗。
            CurrentMarketStatusReader(snapshot, verify_raw_files=False)
        except CurrentMarketStatusError as error:
            raise SelectionOfficialEventError("current_status_snapshot_contract_invalid") from error
        feeds: dict[str, _ParsedFeed] = {}
        for capture in pin.captures:
            if capture.status != "captured" or capture.raw_relative_path is None:
                feeds[capture.source_id] = _ParsedFeed({}, ("source_capture_unavailable",), {}, OFFICIAL_DISPOSAL_PARSER_VERSION)
                continue
            raw_path = _path_from_relative(Path(pin.output_root), capture.raw_relative_path)
            raw = _read_bounded_regular_file(raw_path, MAX_RAW_SOURCE_BYTES, "raw_source")
            if len(raw) != capture.raw_bytes or _sha256(raw) != capture.raw_sha256:
                raise SelectionOfficialEventError("raw_source_hash_or_size_mismatch")
            captured_at = _parse_aware(capture.captured_at, "source_capture_time_invalid")
            if captured_at > _parse_aware(pin.snapshot_observed_at, "snapshot_observed_time_invalid"):
                raise SelectionOfficialEventError("source_observed_after_snapshot")
            if captured_at > _parse_aware(pin.pointer_published_at, "pointer_published_before_capture"):
                raise SelectionOfficialEventError("source_observed_after_pointer_publication")
            _validate_source_dates(capture.source_data_dates, captured_at)
            if capture.status != "captured":
                feeds[capture.source_id] = _ParsedFeed({}, (f"source_status_{capture.status}",), {}, OFFICIAL_DISPOSAL_PARSER_VERSION)
                continue
            feeds[capture.source_id] = _parse_source_feed(capture, raw, captured_at)
        return cls(pin, feeds)

    def get(self, symbol: str, *, market: Literal["twse", "tpex"]) -> CurrentOfficialDisposalObservationV1:
        normalized = str(symbol).strip()
        if not _SYMBOL_RE.fullmatch(normalized):
            raise SelectionOfficialEventError("symbol_must_be_4_to_6_digits")
        if market not in {"twse", "tpex"}:
            raise SelectionOfficialEventError("market_not_supported")
        source_id = next((key for key, (source_market, _) in _SOURCE_BY_ID.items() if source_market == market), None)
        if source_id is None:
            raise SelectionOfficialEventError("market_source_not_configured")
        capture = self._captures.get(source_id)
        feed = self._feeds.get(source_id)
        if capture is None:
            return _unknown_observation(
                normalized,
                market,
                self.source_pin.identity_sha256,
                reason="market_source_not_captured",
                partial=self.source_pin.snapshot_partial_failure,
            )
        if capture.status == "missing":
            return _unknown_observation(
                normalized,
                market,
                self.source_pin.identity_sha256,
                source_id=source_id,
                source_status="missing",
                reason="market_source_not_captured",
                partial=self.source_pin.snapshot_partial_failure,
            )
        if capture.status != "captured" or feed is None:
            reason = feed.global_issues[0] if feed and feed.global_issues else "source_capture_unavailable"
            return _unknown_observation(
                normalized,
                market,
                self.source_pin.identity_sha256,
                source_id=source_id,
                source_status=capture.status,
                parse_status=capture.parse_status,
                source_data_dates=capture.source_data_dates,
                source_raw_sha256=capture.raw_sha256,
                reason=reason,
                warnings=feed.global_issues if feed else (),
                partial=True,
            )
        events = feed.events_by_symbol.get(normalized, ())
        symbol_issues = feed.symbol_issues.get(normalized, ())
        warnings = tuple(dict.fromkeys((*feed.global_issues, *symbol_issues)))
        if events:
            active = tuple(item for item in events if item.state == "effective_in_reported_period")
            upcoming = tuple(item for item in events if item.state == "announced_not_yet_effective")
            state: Literal[
                "reported_upcoming", "reported_active", "reported_elapsed_only", "unknown"
            ] = "reported_active" if active else "reported_upcoming" if upcoming else "reported_elapsed_only"
            return CurrentOfficialDisposalObservationV1(
                symbol=normalized,
                market=market,
                state=state,
                observed_at=events[0].observed_at,
                observed_date=events[0].observed_date,
                events=events,
                source_data_dates=capture.source_data_dates,
                source_id=source_id,
                source_status=capture.status,
                source_parse_status=capture.parse_status,
                source_raw_sha256=capture.raw_sha256,
                source_pin_sha256=self.source_pin.identity_sha256,
                reason_code=None,
                source_warnings=warnings,
                partial_failure=bool(warnings) or self.source_pin.snapshot_partial_failure,
            )
        reason = (
            symbol_issues[0]
            if symbol_issues
            else feed.global_issues[0]
            if feed.global_issues
            else "no_row_absence_not_certified"
        )
        return _unknown_observation(
            normalized,
            market,
            self.source_pin.identity_sha256,
            source_id=source_id,
            source_status=capture.status,
            parse_status=capture.parse_status,
            source_data_dates=capture.source_data_dates,
            source_raw_sha256=capture.raw_sha256,
            reason=reason,
            warnings=warnings,
            partial=bool(warnings) or self.source_pin.snapshot_partial_failure,
        )


def _build_pin(
    *,
    output_root: Path,
    pointer_raw: bytes,
    pointer_payload: Mapping[str, object],
    snapshot_raw: bytes,
    snapshot_payload: Mapping[str, object],
    manifest_raw: bytes,
    manifest_payload: Mapping[str, object],
) -> CurrentOfficialDisposalSourcePinV1:
    run_id = _required_text(pointer_payload, "run_id")
    snapshot_rel = _required_text(pointer_payload, "snapshot_path")
    manifest_rel = _required_text(pointer_payload, "manifest_path")
    captures = _capture_references(snapshot_payload, output_root, run_id)
    pin = CurrentOfficialDisposalSourcePinV1(
        output_root=str(output_root),
        pointer_sha256=_sha256(pointer_raw),
        pointer_published_at=_required_aware_timestamp(pointer_payload, "published_at"),
        run_id=run_id,
        snapshot_relative_path=snapshot_rel,
        snapshot_sha256=_required_hash(pointer_payload, "snapshot_sha256"),
        manifest_relative_path=manifest_rel,
        manifest_sha256=_required_hash(pointer_payload, "manifest_sha256"),
        snapshot_observed_at=_required_aware_timestamp(snapshot_payload, "observed_at"),
        snapshot_partial_failure=_required_bool(snapshot_payload, "partial_failure"),
        captures=captures,
    )
    _validate_pin_shape(pin)
    _verify_exact_references(pin, pointer_payload=pointer_payload, loaded=(snapshot_payload, manifest_payload, snapshot_raw, manifest_raw))
    return pin


def _verify_exact_references(
    pin: CurrentOfficialDisposalSourcePinV1,
    *,
    pointer_payload: Mapping[str, object] | None,
    loaded: tuple[Mapping[str, object], Mapping[str, object], bytes, bytes] | None = None,
) -> tuple[Mapping[str, object], dict[str, OfficialDisposalCaptureReferenceV1]]:
    _validate_pin_shape(pin)
    root = Path(pin.output_root)
    _reject_reparse_components(root, require_leaf_dir=True)
    if loaded is None:
        snapshot_path = _path_from_relative(root, pin.snapshot_relative_path)
        manifest_path = _path_from_relative(root, pin.manifest_relative_path)
        snapshot_raw = _read_bounded_regular_file(snapshot_path, MAX_SNAPSHOT_BYTES, "snapshot")
        manifest_raw = _read_bounded_regular_file(manifest_path, MAX_MANIFEST_BYTES, "manifest")
        snapshot = _load_object(snapshot_raw, "snapshot_json_invalid")
        manifest = _load_object(manifest_raw, "manifest_json_invalid")
    else:
        snapshot, manifest, snapshot_raw, manifest_raw = loaded
        snapshot_path = _path_from_relative(root, pin.snapshot_relative_path)
        manifest_path = _path_from_relative(root, pin.manifest_relative_path)
        if _sha256(snapshot_raw) != pin.snapshot_sha256 or _sha256(manifest_raw) != pin.manifest_sha256:
            raise SelectionOfficialEventError("run_manifest_or_snapshot_hash_mismatch")
        _same_open_file_bytes(snapshot_path, snapshot_raw, MAX_SNAPSHOT_BYTES, "snapshot")
        _same_open_file_bytes(manifest_path, manifest_raw, MAX_MANIFEST_BYTES, "manifest")
    if _sha256(snapshot_raw) != pin.snapshot_sha256:
        raise SelectionOfficialEventError("snapshot_hash_mismatch")
    if _sha256(manifest_raw) != pin.manifest_sha256:
        raise SelectionOfficialEventError("manifest_hash_mismatch")
    _validate_snapshot_and_manifest(pin, snapshot, manifest, root)
    actual_captures = _capture_references(snapshot, root, pin.run_id)
    if actual_captures != pin.captures:
        raise SelectionOfficialEventError("source_capture_pin_mismatch")
    capture_map = {item.source_id: item for item in actual_captures}
    for source_id, _, _ in _SOURCE_MARKETS:
        capture = capture_map[source_id]
        if capture.raw_relative_path is None:
            if capture.status == "captured":
                raise SelectionOfficialEventError("captured_source_raw_reference_missing")
            continue
        raw_path = _path_from_relative(root, capture.raw_relative_path)
        raw = _read_bounded_regular_file(raw_path, MAX_RAW_SOURCE_BYTES, "raw_source")
        if len(raw) != capture.raw_bytes or _sha256(raw) != capture.raw_sha256:
            raise SelectionOfficialEventError("raw_source_hash_or_size_mismatch")
    if pointer_payload is not None:
        _validate_pointer_payload(pointer_payload, root)
        if (
            pointer_payload.get("run_id") != pin.run_id
            or pointer_payload.get("snapshot_path") != pin.snapshot_relative_path
            or pointer_payload.get("manifest_path") != pin.manifest_relative_path
            or pointer_payload.get("snapshot_sha256") != pin.snapshot_sha256
            or pointer_payload.get("manifest_sha256") != pin.manifest_sha256
            or pointer_payload.get("partial_failure") is not pin.snapshot_partial_failure
        ):
            raise SelectionOfficialEventError("pointer_pin_mismatch")
        source_count = pointer_payload.get("source_count")
        successful_count = pointer_payload.get("successful_source_count")
        snapshot_captures = snapshot.get("source_captures")
        if (
            type(source_count) is not int
            or type(successful_count) is not int
            or not isinstance(snapshot_captures, list)
            or source_count != len(snapshot_captures)
            or successful_count != snapshot.get("successful_source_count")
        ):
            raise SelectionOfficialEventError("pointer_count_binding_mismatch")
    return snapshot, capture_map


def _validate_snapshot_and_manifest(
    pin: CurrentOfficialDisposalSourcePinV1,
    snapshot: Mapping[str, object],
    manifest: Mapping[str, object],
    root: Path,
) -> None:
    if (
        set(manifest)
        != {"schema_version", "run_id", "snapshot_path", "snapshot_sha256", "raw_sources"}
        or manifest.get("schema_version") != "current-market-status-capture-manifest.v1"
        or manifest.get("run_id") != pin.run_id
        or snapshot.get("schema_version") != "current-market-status-observation.v1"
        or snapshot.get("run_id") != pin.run_id
        or snapshot.get("scope") != "current_only"
        or snapshot.get("pit_eligible") is not False
        or snapshot.get("partial_failure") is not pin.snapshot_partial_failure
        or _required_aware_timestamp(snapshot, "observed_at") != pin.snapshot_observed_at
    ):
        raise SelectionOfficialEventError("run_snapshot_identity_mismatch")
    if _required_text(manifest, "snapshot_sha256") != pin.snapshot_sha256:
        raise SelectionOfficialEventError("manifest_snapshot_hash_mismatch")
    if _absolute_path(_required_text(manifest, "snapshot_path"), "manifest_snapshot_path_invalid") != _path_from_relative(root, pin.snapshot_relative_path):
        raise SelectionOfficialEventError("manifest_snapshot_path_mismatch")
    source_captures = snapshot.get("source_captures")
    manifest_sources = manifest.get("raw_sources")
    if not isinstance(source_captures, list) or not isinstance(manifest_sources, list) or len(source_captures) != len(manifest_sources):
        raise SelectionOfficialEventError("manifest_capture_count_mismatch")
    expected_sources: list[dict[str, object]] = []
    source_count = snapshot.get("source_count")
    success_count = snapshot.get("successful_source_count")
    if type(source_count) is not int or source_count != len(source_captures):
        raise SelectionOfficialEventError("snapshot_source_count_mismatch")
    calculated_success = 0
    for item in source_captures:
        if not isinstance(item, Mapping):
            raise SelectionOfficialEventError("snapshot_source_capture_invalid")
        expected_sources.append(
            {
                key: item.get(key)
                for key in ("source_id", "raw_path", "raw_sha256", "captured_at", "status", "parse_status")
            }
        )
        calculated_success += item.get("status") == "captured" and item.get("parse_status") == "parsed"
    if expected_sources != manifest_sources:
        raise SelectionOfficialEventError("manifest_capture_projection_mismatch")
    if type(success_count) is not int or success_count != calculated_success:
        raise SelectionOfficialEventError("snapshot_success_count_mismatch")
    if _absolute_path(pin.output_root, "output_root_invalid") != root:
        raise SelectionOfficialEventError("output_root_identity_mismatch")


def _capture_references(
    snapshot: Mapping[str, object], output_root: Path, run_id: str
) -> tuple[OfficialDisposalCaptureReferenceV1, ...]:
    raw_captures = snapshot.get("source_captures")
    if not isinstance(raw_captures, list):
        raise SelectionOfficialEventError("snapshot_source_captures_invalid")
    target_by_id: dict[str, Mapping[str, object]] = {}
    for item in raw_captures:
        if not isinstance(item, Mapping):
            raise SelectionOfficialEventError("snapshot_source_capture_invalid")
        source_id = item.get("source_id")
        if type(source_id) is not str:
            continue
        if source_id not in _SOURCE_BY_ID:
            continue
        if source_id in target_by_id:
            raise SelectionOfficialEventError("duplicate_disposal_source_capture")
        target_by_id[str(source_id)] = item
    references: list[OfficialDisposalCaptureReferenceV1] = []
    run_dir = f"cms_{run_id}"
    for source_id, market, expected_url in _SOURCE_MARKETS:
        item = target_by_id.get(source_id)
        if item is None:
            references.append(
                OfficialDisposalCaptureReferenceV1(
                    source_id=source_id,
                    market=market,  # type: ignore[arg-type]
                    status="missing",
                    parse_status=None,
                    requested_url=None,
                    final_url=None,
                    raw_relative_path=None,
                    raw_sha256=None,
                    raw_bytes=None,
                    captured_at=None,
                    source_data_dates=(),
                )
            )
            continue
        if item.get("market") != market or item.get("requested_url") != expected_url:
            raise SelectionOfficialEventError("disposal_source_market_or_endpoint_mismatch")
        status = _required_text(item, "status")
        parse_status = item.get("parse_status")
        if parse_status is not None and type(parse_status) is not str:
            raise SelectionOfficialEventError("source_parse_status_invalid")
        final_url = item.get("final_url")
        if final_url is not None and (type(final_url) is not str or final_url != expected_url):
            raise SelectionOfficialEventError("disposal_source_final_url_invalid")
        if status == "captured" and final_url is None:
            raise SelectionOfficialEventError("disposal_source_final_url_missing")
        raw_path_value = item.get("raw_path")
        raw_relative: str | None = None
        raw_hash: str | None = None
        raw_bytes: int | None = None
        if raw_path_value is not None:
            raw_path = _absolute_path(raw_path_value, "raw_source_path_invalid")
            run_root = output_root / run_dir
            _assert_direct_child_path(raw_path, run_root / "raw", "raw_source_path_invalid")
            if not re.fullmatch(r"s[0-9]{4}\.bin", raw_path.name):
                raise SelectionOfficialEventError("raw_source_filename_invalid")
            raw_relative = raw_path.relative_to(output_root).as_posix()
            raw_hash = _required_hash(item, "raw_sha256")
            raw_bytes = _required_nonnegative_int(item, "raw_bytes")
        elif status == "captured":
            raise SelectionOfficialEventError("captured_source_raw_reference_missing")
        captured_at_value = item.get("captured_at")
        captured_at = None
        if captured_at_value is not None:
            captured_at = _required_aware_timestamp(item, "captured_at")
        dates_value = item.get("source_data_dates", [])
        if not isinstance(dates_value, list) or not all(type(value) is str for value in dates_value):
            raise SelectionOfficialEventError("source_data_dates_invalid")
        source_dates = tuple(dates_value)
        for value in source_dates:
            try:
                parsed = date.fromisoformat(value)
            except ValueError as error:
                raise SelectionOfficialEventError("source_data_date_invalid") from error
            if parsed.isoformat() != value:
                raise SelectionOfficialEventError("source_data_date_invalid")
        if source_dates != tuple(sorted(set(source_dates))):
            raise SelectionOfficialEventError("source_data_dates_not_canonical")
        references.append(
            OfficialDisposalCaptureReferenceV1(
                source_id=source_id,
                market=market,  # type: ignore[arg-type]
                status=status,
                parse_status=parse_status,
                requested_url=expected_url,
                final_url=final_url,
                raw_relative_path=raw_relative,
                raw_sha256=raw_hash,
                raw_bytes=raw_bytes,
                captured_at=captured_at,
                source_data_dates=source_dates,
            )
        )
    return tuple(references)


def _parse_source_feed(
    capture: OfficialDisposalCaptureReferenceV1,
    raw: bytes,
    captured_at: datetime,
) -> _ParsedFeed:
    if capture.source_id == "twse.disposition_current":
        return _parse_twse_feed(capture, raw, captured_at)
    if capture.source_id == "tpex.disposition_current":
        return _parse_tpex_feed(capture, raw, captured_at)
    return _ParsedFeed({}, ("source_id_not_supported",), {}, OFFICIAL_DISPOSAL_PARSER_VERSION)


def _parse_twse_feed(
    capture: OfficialDisposalCaptureReferenceV1,
    raw: bytes,
    captured_at: datetime,
) -> _ParsedFeed:
    payload = _load_json(raw, "twse_disposal_json_invalid")
    if not isinstance(payload, Mapping):
        return _ParsedFeed({}, ("twse_disposal_schema_unconfirmed",), {}, OFFICIAL_DISPOSAL_PARSER_VERSION)
    fields = payload.get("fields")
    rows = payload.get("data")
    required_fields = {
        "公布日期",
        "證券代號",
        "累計",
        "處置條件",
        "處置起迄時間",
        "處置措施",
        "處置內容",
    }
    if (
        not isinstance(fields, list)
        or not all(type(field) is str for field in fields)
        or len(set(fields)) != len(fields)
        or not required_fields.issubset(fields)
        or not isinstance(rows, list)
        or len(rows) > MAX_DISPOSAL_ROWS
        or any(not isinstance(row, list) or len(row) != len(fields) for row in rows)
    ):
        return _ParsedFeed({}, ("twse_disposal_schema_unconfirmed",), {}, OFFICIAL_DISPOSAL_PARSER_VERSION)
    observed_date = captured_at.astimezone(_TAIPEI).date()
    announcement_index = fields.index("公布日期")
    for row in rows:
        announcement = parse_source_date(row[announcement_index])
        if announcement is not None and announcement > observed_date:
            raise SelectionOfficialEventError("future_announcement_after_observation")
    envelope = RawFetchEnvelope(
        source_id=capture.source_id,
        source_version="twse-disposition-openapi-current.v1",
        endpoint_id="twse.announcement.punish",
        request_parameters={},
        fetched_at=captured_at,
        http_status=200,
        http_headers={"content-type": "application/json"},
        payload=raw,
    )
    try:
        parsed = parse_twse_disposition(envelope)
    except (TypeError, ValueError):
        return _ParsedFeed({}, ("twse_disposition_schema_unconfirmed",), {}, OFFICIAL_DISPOSAL_PARSER_VERSION)
    events: dict[str, list[OfficialDisposalEventV1]] = {}
    symbol_issues: dict[str, list[str]] = {}
    for item in parsed.accepted:
        normalized = item.to_dict()
        metadata = normalized.get("metadata")
        if not isinstance(metadata, Mapping):
            continue
        announcement = _strict_iso_date(normalized.get("observation_date"), "twse_announcement_date_invalid")
        effective_from = _strict_iso_date(metadata.get("effective_from"), "twse_effective_from_invalid")
        effective_to = _strict_iso_date(metadata.get("effective_to"), "twse_effective_to_invalid")
        symbol = str(normalized.get("symbol", ""))
        if announcement > observed_date:
            raise SelectionOfficialEventError("future_announcement_after_observation")
        if effective_to < effective_from:
            symbol_issues.setdefault(symbol, []).append("effective_period_invalid")
            continue
        event = _make_event(
            symbol=symbol,
            market="twse",
            source_id=capture.source_id,
            announcement_date=announcement,
            effective_from=effective_from,
            effective_to=effective_to,
            observed_at=captured_at,
            name=_optional_text(normalized.get("metadata", {}).get("name")) if isinstance(normalized.get("metadata"), Mapping) else None,
            reason=_optional_text(metadata.get("condition")),
            measure=_optional_text(metadata.get("measure")),
            details=_optional_text(metadata.get("content")),
            source_data_dates=capture.source_data_dates,
            raw_sha256=capture.raw_sha256 or "",
            raw_row_sha256=_prefixed_raw_hash(normalized.get("raw_payload_sha256")),
        )
        events.setdefault(symbol, []).append(event)
    issues: list[str] = []
    if parsed.quarantine:
        issues.append("twse_disposition_rows_quarantined")
    return _freeze_feed(events, issues, symbol_issues, OFFICIAL_DISPOSAL_PARSER_VERSION)


def _parse_tpex_feed(
    capture: OfficialDisposalCaptureReferenceV1,
    raw: bytes,
    captured_at: datetime,
) -> _ParsedFeed:
    payload = _load_json(raw, "tpex_disposal_json_invalid")
    if (
        not isinstance(payload, list)
        or len(payload) > MAX_DISPOSAL_ROWS
        or any(not isinstance(item, Mapping) for item in payload)
    ):
        return _ParsedFeed({}, ("tpex_disposal_openapi_schema_unconfirmed",), {}, TPEX_ROW_SCHEMA_VERSION)
    observed_date = captured_at.astimezone(_TAIPEI).date()
    events: dict[str, list[OfficialDisposalEventV1]] = {}
    symbol_issues: dict[str, list[str]] = {}
    issues: list[str] = []
    seen: set[tuple[str, date, date, date]] = set()
    for raw_row in payload:
        row = dict(raw_row)
        if not all(type(key) is str for key in row):
            issues.append("tpex_disposal_row_keys_invalid")
            continue
        keys = set(row)
        if keys != _TPEX_ROW_FIELD_SET or any(
            type(row[field]) is not str for field in TPEX_ROW_FIELDS
        ):
            issues.append("tpex_disposal_openapi_schema_unconfirmed")
            continue
        symbol = _normalize_symbol(row.get("SecuritiesCompanyCode"))
        if symbol is None:
            issues.append("tpex_disposal_symbol_invalid")
            continue
        try:
            announcement = _parse_date(row.get("Date"), "tpex_announcement_date_invalid")
            if announcement > observed_date:
                raise SelectionOfficialEventError("future_announcement_after_observation")
            period = _optional_text(row.get("DispositionPeriod"))
            if period is None:
                raise SelectionOfficialEventError("tpex_effective_period_missing")
            match = _TPEx_DATE_RANGE_RE.fullmatch(period)
            if match is None:
                raise SelectionOfficialEventError("tpex_effective_period_unrecognized")
            effective_from = _parse_date(match.group(1), "tpex_effective_from_invalid")
            effective_to = _parse_date(match.group(2), "tpex_effective_to_invalid")
        except SelectionOfficialEventError as error:
            if error.reason_code == "future_announcement_after_observation":
                raise
            symbol_issues.setdefault(symbol, []).append(error.reason_code)
            continue
        if effective_to < effective_from:
            symbol_issues.setdefault(symbol, []).append("effective_period_invalid")
            continue
        identity = (symbol, announcement, effective_from, effective_to)
        if identity in seen:
            symbol_issues.setdefault(symbol, []).append("duplicate_disposal_event_row")
            issues.append("tpex_disposal_duplicate_rows_present")
            continue
        seen.add(identity)
        event = _make_event(
            symbol=symbol,
            market="tpex",
            source_id=capture.source_id,
            announcement_date=announcement,
            effective_from=effective_from,
            effective_to=effective_to,
            observed_at=captured_at,
            name=_optional_text(row.get("CompanyName")),
            reason=_optional_text(row.get("DispositionReasons")),
            measure=None,
            details=_optional_text(row.get("DisposalCondition")),
            source_data_dates=capture.source_data_dates,
            raw_sha256=capture.raw_sha256 or "",
            raw_row_sha256=_canonical_sha256(row),
        )
        events.setdefault(symbol, []).append(event)
    if not payload:
        issues.append("tpex_empty_feed_has_no_absence_certificate")
    return _freeze_feed(events, issues, symbol_issues, TPEX_ROW_SCHEMA_VERSION)


def _make_event(
    *,
    symbol: str,
    market: Literal["twse", "tpex"],
    source_id: str,
    announcement_date: date,
    effective_from: date,
    effective_to: date,
    observed_at: datetime,
    name: str | None,
    reason: str | None,
    measure: str | None,
    details: str | None,
    source_data_dates: tuple[str, ...],
    raw_sha256: str,
    raw_row_sha256: str,
) -> OfficialDisposalEventV1:
    if not _SYMBOL_RE.fullmatch(symbol):
        raise SelectionOfficialEventError("disposal_symbol_invalid")
    if not _SHA256_RE.fullmatch(raw_sha256) or not _SHA256_RE.fullmatch(raw_row_sha256):
        raise SelectionOfficialEventError("disposal_raw_hash_invalid")
    observed_date = observed_at.astimezone(_TAIPEI).date()
    state: Literal[
        "announced_not_yet_effective",
        "effective_in_reported_period",
        "reported_period_elapsed",
    ]
    if observed_date < effective_from:
        state = "announced_not_yet_effective"
    elif observed_date <= effective_to:
        state = "effective_in_reported_period"
    else:
        state = "reported_period_elapsed"
    return OfficialDisposalEventV1(
        symbol=symbol,
        market=market,
        source_id=source_id,
        announcement_date=announcement_date,
        effective_from=effective_from,
        effective_to=effective_to,
        observed_at=observed_at,
        observed_date=observed_date,
        state=state,
        name=name,
        reason=reason,
        measure=measure,
        details=details,
        source_data_dates=source_data_dates,
        raw_sha256=raw_sha256,
        raw_row_sha256=raw_row_sha256,
    )


def _freeze_feed(
    events: Mapping[str, Sequence[OfficialDisposalEventV1]],
    issues: Sequence[str],
    symbol_issues: Mapping[str, Sequence[str]],
    parser_version: str,
) -> _ParsedFeed:
    frozen_events = {
        key: tuple(sorted(value, key=lambda item: (item.announcement_date, item.effective_from, item.effective_to)))
        for key, value in events.items()
    }
    frozen_symbol_issues = {key: tuple(dict.fromkeys(value)) for key, value in symbol_issues.items()}
    return _ParsedFeed(frozen_events, tuple(dict.fromkeys(issues)), frozen_symbol_issues, parser_version)


def _unknown_observation(
    symbol: str,
    market: Literal["twse", "tpex"],
    pin_sha256: str,
    *,
    reason: str,
    source_id: str | None = None,
    source_status: str = "missing",
    parse_status: str | None = None,
    source_data_dates: tuple[str, ...] = (),
    source_raw_sha256: str | None = None,
    warnings: tuple[str, ...] = (),
    partial: bool,
) -> CurrentOfficialDisposalObservationV1:
    return CurrentOfficialDisposalObservationV1(
        symbol=symbol,
        market=market,
        state="unknown",
        observed_at=None,
        observed_date=None,
        events=(),
        source_data_dates=source_data_dates,
        source_id=source_id,
        source_status=source_status,
        source_parse_status=parse_status,
        source_raw_sha256=source_raw_sha256,
        source_pin_sha256=pin_sha256,
        reason_code=reason,
        source_warnings=warnings,
        partial_failure=partial,
    )


def _validate_pointer_payload(payload: Mapping[str, object], output_root: Path) -> None:
    required = {
        "schema_version",
        "scope",
        "pit_eligible",
        "run_id",
        "published_at",
        "snapshot_path",
        "snapshot_sha256",
        "manifest_path",
        "manifest_sha256",
        "source_count",
        "successful_source_count",
        "partial_failure",
    }
    if (
        set(payload) != required
        or payload.get("schema_version") != "current-market-status-pointer.v1"
        or payload.get("scope") != OFFICIAL_DISPOSAL_SCOPE
        or payload.get("pit_eligible") is not False
        or not _RUN_ID_RE.fullmatch(str(payload.get("run_id", "")))
    ):
        raise SelectionOfficialEventError("current_status_pointer_invalid")
    _parse_aware(_required_aware_timestamp(payload, "published_at"), "pointer_published_at_invalid")
    _required_hash(payload, "snapshot_sha256")
    _required_hash(payload, "manifest_sha256")
    _required_nonnegative_int(payload, "source_count")
    _required_nonnegative_int(payload, "successful_source_count")
    _required_bool(payload, "partial_failure")
    expected_dir = f"cms_{payload['run_id']}"
    if payload.get("snapshot_path") != f"{expected_dir}/snapshot.json" or payload.get("manifest_path") != f"{expected_dir}/manifest.json":
        raise SelectionOfficialEventError("current_status_pointer_path_invalid")
    _path_from_relative(output_root, str(payload["snapshot_path"]))
    _path_from_relative(output_root, str(payload["manifest_path"]))


def _validate_pin_shape(pin: CurrentOfficialDisposalSourcePinV1) -> None:
    if (
        pin.schema_version != OFFICIAL_DISPOSAL_PIN_SCHEMA
        or pin.scope != OFFICIAL_DISPOSAL_SCOPE
        or pin.historical_pit_eligible is not False
        or pin.reader_parser_version != OFFICIAL_DISPOSAL_PARSER_VERSION
        or pin.tpex_source_schema_version != TPEX_ROW_SCHEMA_VERSION
        or pin.tpex_response_envelope_version != TPEX_RESPONSE_ENVELOPE_VERSION
        or pin.tpex_openapi_swagger_sha256 != TPEX_OPENAPI_SWAGGER_SHA256
        or pin.tpex_openapi_swagger_completed_at
        != TPEX_OPENAPI_SWAGGER_COMPLETED_AT
        or pin.tpex_endpoint_evidence_date != TPEX_ENDPOINT_EVIDENCE_DATE
        or not _RUN_ID_RE.fullmatch(pin.run_id)
        or not _SHA256_RE.fullmatch(pin.pointer_sha256)
        or not _SHA256_RE.fullmatch(pin.snapshot_sha256)
        or not _SHA256_RE.fullmatch(pin.manifest_sha256)
        or type(pin.snapshot_partial_failure) is not bool
        or not Path(pin.output_root).is_absolute()
    ):
        raise SelectionOfficialEventError("source_pin_shape_invalid")
    expected_run = f"cms_{pin.run_id}"
    if (
        pin.snapshot_relative_path != f"{expected_run}/snapshot.json"
        or pin.manifest_relative_path != f"{expected_run}/manifest.json"
        or len(pin.captures) != len(_SOURCE_MARKETS)
    ):
        raise SelectionOfficialEventError("source_pin_paths_or_capture_count_invalid")
    if tuple(item.source_id for item in pin.captures) != tuple(source for source, _, _ in _SOURCE_MARKETS):
        raise SelectionOfficialEventError("source_pin_capture_order_invalid")
    for capture, (source_id, market, _) in zip(pin.captures, _SOURCE_MARKETS):
        if capture.source_id != source_id or capture.market != market:
            raise SelectionOfficialEventError("source_pin_capture_identity_invalid")
        if capture.status == "missing":
            if any(
                value is not None
                for value in (
                    capture.parse_status,
                    capture.requested_url,
                    capture.final_url,
                    capture.raw_relative_path,
                    capture.raw_sha256,
                    capture.raw_bytes,
                    capture.captured_at,
                )
            ) or capture.source_data_dates:
                raise SelectionOfficialEventError("missing_source_capture_has_evidence")
            continue
        if capture.requested_url != _SOURCE_BY_ID[source_id][1]:
            raise SelectionOfficialEventError("source_pin_endpoint_invalid")
        if capture.raw_relative_path is not None:
            _validate_relative_capture_path(capture.raw_relative_path, pin.run_id)
            if (
                capture.raw_sha256 is None
                or not _SHA256_RE.fullmatch(capture.raw_sha256)
                or type(capture.raw_bytes) is not int
                or capture.raw_bytes < 0
            ):
                raise SelectionOfficialEventError("source_pin_raw_reference_invalid")
        elif capture.status == "captured":
            raise SelectionOfficialEventError("source_pin_captured_raw_missing")
        if capture.captured_at is not None:
            _parse_aware(capture.captured_at, "source_capture_time_invalid")


def _validate_relative_capture_path(value: str, run_id: str) -> None:
    expected_prefix = f"cms_{run_id}/raw/"
    path = PurePosixPath(value)
    if (
        type(value) is not str
        or not value.startswith(expected_prefix)
        or "\\" in value
        or ":" in value
        or path.is_absolute()
        or str(path) != value
        or any(part in {"", ".", ".."} for part in path.parts)
        or not re.fullmatch(r"s[0-9]{4}\.bin", path.name)
    ):
        raise SelectionOfficialEventError("raw_source_relative_path_invalid")


def _capture_reference_from_dict(value: object) -> OfficialDisposalCaptureReferenceV1:
    if not isinstance(value, Mapping):
        raise SelectionOfficialEventError("source_pin_capture_invalid")
    required = {
        "source_id",
        "market",
        "status",
        "parse_status",
        "requested_url",
        "final_url",
        "raw_relative_path",
        "raw_sha256",
        "raw_bytes",
        "captured_at",
        "source_data_dates",
    }
    if set(value) != required:
        raise SelectionOfficialEventError("source_pin_capture_keys_invalid")
    strings_or_none: dict[str, str | None] = {}
    for name in ("parse_status", "requested_url", "final_url", "raw_relative_path", "raw_sha256", "captured_at"):
        item = value.get(name)
        if item is not None and type(item) is not str:
            raise SelectionOfficialEventError("source_pin_capture_value_invalid")
        strings_or_none[name] = item
    raw_bytes = value.get("raw_bytes")
    if raw_bytes is not None and (type(raw_bytes) is not int or raw_bytes < 0):
        raise SelectionOfficialEventError("source_pin_capture_size_invalid")
    dates = value.get("source_data_dates")
    if not isinstance(dates, list) or not all(type(item) is str for item in dates):
        raise SelectionOfficialEventError("source_pin_capture_dates_invalid")
    source_id = _required_text(value, "source_id")
    market = value.get("market")
    expected = _SOURCE_BY_ID.get(source_id)
    if expected is None or market != expected[0]:
        raise SelectionOfficialEventError("source_pin_capture_source_invalid")
    return OfficialDisposalCaptureReferenceV1(
        source_id=source_id,
        market=expected[0],  # type: ignore[arg-type]
        status=_required_text(value, "status"),
        parse_status=strings_or_none["parse_status"],
        requested_url=strings_or_none["requested_url"],
        final_url=strings_or_none["final_url"],
        raw_relative_path=strings_or_none["raw_relative_path"],
        raw_sha256=strings_or_none["raw_sha256"],
        raw_bytes=raw_bytes,
        captured_at=strings_or_none["captured_at"],
        source_data_dates=tuple(dates),
    )


def _require_pointer_location(path: Path) -> None:
    if path.name != "current_market_status_pointer.json":
        raise SelectionOfficialEventError("pointer_filename_invalid")
    _reject_reparse_components(path, require_leaf_dir=False)
    parent = path.parent
    _reject_reparse_components(parent, require_leaf_dir=True)


def _path_from_relative(root: Path, value: str) -> Path:
    if type(value) is not str or not value or "\\" in value or ":" in value:
        raise SelectionOfficialEventError("manifest_relative_path_invalid")
    relative = PurePosixPath(value)
    if (
        relative.is_absolute()
        or str(relative) != value
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise SelectionOfficialEventError("manifest_relative_path_invalid")
    result = root.joinpath(*relative.parts)
    try:
        if result.relative_to(root) == Path("."):
            raise SelectionOfficialEventError("manifest_relative_path_invalid")
    except ValueError as error:
        raise SelectionOfficialEventError("manifest_relative_path_invalid") from error
    return result


def _assert_direct_child_path(path: Path, expected_parent: Path, code: str) -> None:
    normalized_path = Path(os.path.abspath(str(path)))
    normalized_parent = Path(os.path.abspath(str(expected_parent)))
    if normalized_path.parent != normalized_parent:
        raise SelectionOfficialEventError(code)


def _absolute_path(value: object, code: str) -> Path:
    if not isinstance(value, (str, Path)):
        raise SelectionOfficialEventError(code)
    text = str(value)
    raw = Path(text).expanduser()
    if not raw.is_absolute() or any(part == ".." for part in raw.parts):
        raise SelectionOfficialEventError(code)
    return Path(os.path.abspath(str(raw)))


def _reject_reparse_components(path: Path, *, require_leaf_dir: bool) -> None:
    absolute = Path(os.path.abspath(str(path)))
    parts = absolute.parts
    if not parts:
        raise SelectionOfficialEventError("path_invalid")
    current = Path(absolute.anchor)
    for index, part in enumerate(parts[1:], start=1):
        current = current / part
        try:
            info = current.lstat()
        except OSError as error:
            raise SelectionOfficialEventError("path_component_missing") from error
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & _WINDOWS_REPARSE_POINT:
            raise SelectionOfficialEventError("path_reparse_component_rejected")
        is_leaf = index == len(parts) - 1
        if not is_leaf and not stat.S_ISDIR(info.st_mode):
            raise SelectionOfficialEventError("path_parent_not_directory")
        if is_leaf and require_leaf_dir and not stat.S_ISDIR(info.st_mode):
            raise SelectionOfficialEventError("path_root_not_directory")


def _read_bounded_regular_file(path: Path, max_bytes: int, role: str) -> bytes:
    _reject_reparse_components(path, require_leaf_dir=False)
    try:
        before = path.lstat()
    except OSError as error:
        raise SelectionOfficialEventError(f"{role}_file_unavailable") from error
    _require_single_link_regular(before, role)
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise SelectionOfficialEventError(f"{role}_file_open_failed") from error
    try:
        opened = os.fstat(descriptor)
        _require_single_link_regular(opened, role)
        if _stat_identity(before) != _stat_identity(opened):
            raise SelectionOfficialEventError(f"{role}_file_replaced_before_read")
        pieces: list[bytes] = []
        total = 0
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            while True:
                block = stream.read(min(READ_CHUNK_BYTES, max_bytes + 1 - total))
                if not block:
                    break
                total += len(block)
                if total > max_bytes:
                    raise SelectionOfficialEventError(f"{role}_file_exceeds_size_limit")
                pieces.append(block)
            after_fd = os.fstat(descriptor)
        after_path = path.lstat()
        _require_single_link_regular(after_path, role)
        if _stat_identity(opened) != _stat_identity(after_fd) or _stat_identity(after_fd) != _stat_identity(after_path):
            raise SelectionOfficialEventError(f"{role}_file_changed_during_read")
        return b"".join(pieces)
    finally:
        os.close(descriptor)


def _same_open_file_bytes(path: Path, expected_bytes: bytes, max_bytes: int, role: str) -> None:
    actual = _read_bounded_regular_file(path, max_bytes, role)
    if actual != expected_bytes:
        raise SelectionOfficialEventError(f"{role}_file_changed_during_read")


def _require_single_link_regular(info: os.stat_result, role: str) -> None:
    if (
        not stat.S_ISREG(info.st_mode)
        or stat.S_ISLNK(info.st_mode)
        or getattr(info, "st_file_attributes", 0) & _WINDOWS_REPARSE_POINT
    ):
        raise SelectionOfficialEventError(f"{role}_not_regular_file")
    if getattr(info, "st_nlink", 1) != 1:
        raise SelectionOfficialEventError(f"{role}_physical_link_count_invalid")


def _stat_identity(info: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        int(info.st_dev),
        int(info.st_ino),
        int(info.st_size),
        int(info.st_mtime_ns),
        int(info.st_mode),
        int(getattr(info, "st_nlink", 1)),
    )


def _load_object(raw: bytes, code: str) -> Mapping[str, object]:
    value = _load_json(raw, code)
    if not isinstance(value, Mapping):
        raise SelectionOfficialEventError(code)
    return value


def _load_json(raw: bytes, code: str) -> object:
    try:
        return _strict_json_loads(raw)
    except (UnicodeError, json.JSONDecodeError, ValueError) as error:
        raise SelectionOfficialEventError(code) from error


def _strict_json_loads(raw: bytes) -> object:
    def object_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    return json.loads(raw.decode("utf-8-sig", errors="strict"), object_pairs_hook=object_pairs)


def _validate_source_dates(values: tuple[str, ...], captured_at: datetime) -> None:
    observed_date = captured_at.astimezone(_TAIPEI).date()
    for value in values:
        try:
            parsed = date.fromisoformat(value)
        except ValueError as error:
            raise SelectionOfficialEventError("source_data_date_invalid") from error
        if parsed > observed_date:
            raise SelectionOfficialEventError("source_data_date_after_observation")


def _strict_iso_date(value: object, code: str) -> date:
    if type(value) is not str:
        raise SelectionOfficialEventError(code)
    try:
        result = date.fromisoformat(value)
    except ValueError as error:
        raise SelectionOfficialEventError(code) from error
    if result.isoformat() != value:
        raise SelectionOfficialEventError(code)
    return result


def _parse_date(value: object, code: str) -> date:
    if type(value) not in {str, int} or type(value) is bool:
        raise SelectionOfficialEventError(code)
    result = parse_source_date(value)
    if result is None:
        raise SelectionOfficialEventError(code)
    return result


def _normalize_symbol(value: object) -> str | None:
    if type(value) not in {str, int} or type(value) is bool:
        return None
    normalized = str(value).strip()
    return normalized if _SYMBOL_RE.fullmatch(normalized) else None


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    if type(value) is str:
        normalized = value.strip()
    elif type(value) is int and type(value) is not bool:
        normalized = str(value)
    else:
        raise SelectionOfficialEventError("source_text_field_invalid")
    if len(normalized) > 4096:
        raise SelectionOfficialEventError("source_text_field_exceeds_limit")
    return normalized or None


def _required_text(payload: Mapping[str, object], field: str) -> str:
    value = payload.get(field)
    if type(value) is not str or not value.strip():
        raise SelectionOfficialEventError(f"{field}_invalid")
    return value.strip()


def _required_hash(payload: Mapping[str, object], field: str) -> str:
    value = _required_text(payload, field)
    if not _SHA256_RE.fullmatch(value):
        raise SelectionOfficialEventError(f"{field}_invalid")
    return value


def _required_aware_timestamp(payload: Mapping[str, object], field: str) -> str:
    value = _required_text(payload, field)
    _parse_aware(value, f"{field}_invalid")
    return value


def _read_now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _resolve_read_cutoff(cutoff_at: datetime | None, *, read_now: datetime) -> datetime:
    if cutoff_at is None:
        return read_now
    if (
        not isinstance(cutoff_at, datetime)
        or cutoff_at.tzinfo is None
        or cutoff_at.utcoffset() is None
    ):
        raise SelectionOfficialEventError("read_cutoff_must_be_aware_datetime")
    cutoff = cutoff_at.astimezone(timezone.utc)
    if cutoff > read_now:
        raise SelectionOfficialEventError("read_cutoff_after_read_now")
    return cutoff


def _validate_pin_timestamps_before_cutoff(
    pin: CurrentOfficialDisposalSourcePinV1,
    cutoff_at: datetime,
) -> None:
    pointer_published_at = _parse_aware(
        pin.pointer_published_at,
        "pointer_published_at_invalid",
    )
    if pointer_published_at > cutoff_at:
        raise SelectionOfficialEventError("pointer_published_after_read_cutoff")
    snapshot_observed_at = _parse_aware(
        pin.snapshot_observed_at,
        "snapshot_observed_time_invalid",
    )
    if snapshot_observed_at > cutoff_at:
        raise SelectionOfficialEventError("snapshot_observed_after_read_cutoff")
    for capture in pin.captures:
        if capture.captured_at is None:
            continue
        captured_at = _parse_aware(capture.captured_at, "source_capture_time_invalid")
        if captured_at > cutoff_at:
            raise SelectionOfficialEventError("source_capture_after_read_cutoff")


def _parse_aware(value: str | None, code: str) -> datetime:
    if type(value) is not str:
        raise SelectionOfficialEventError(code)
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise SelectionOfficialEventError(code) from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SelectionOfficialEventError(code)
    return parsed


def _required_bool(payload: Mapping[str, object], field: str) -> bool:
    value = payload.get(field)
    if type(value) is not bool:
        raise SelectionOfficialEventError(f"{field}_invalid")
    return value


def _required_nonnegative_int(payload: Mapping[str, object], field: str) -> int:
    value = payload.get(field)
    if type(value) is not int or value < 0:
        raise SelectionOfficialEventError(f"{field}_invalid")
    return value


def _prefixed_raw_hash(value: object) -> str:
    if type(value) is not str or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise SelectionOfficialEventError("raw_row_hash_invalid")
    return f"sha256:{value}"


def _sha256(raw: bytes) -> str:
    return f"sha256:{sha256(raw).hexdigest()}"


def _canonical_json(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _canonical_json_bytes(payload: object) -> bytes:
    return _canonical_json(payload).encode("utf-8")


def _canonical_sha256(payload: object) -> str:
    return _sha256(_canonical_json_bytes(payload))
