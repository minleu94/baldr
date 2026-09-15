"""Immutable security-lifecycle evidence derived from official MOPS raw JSON.

This module is intentionally a small source contract, not a universe producer.
It parses an explicit MOPS share-conversion announcement into typed security
identity and lifecycle evidence, then keeps the predecessor/successor market
state separate from score readiness.  It never moves historical prices or
scores and never grants formal or retroactive natural credit.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from enum import Enum
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo


SCHEMA_VERSION = "security-lifecycle-contract.v1"
SOURCE_ID = "mops.t05st01.security_lifecycle"
MOPS_LIST_ENDPOINT = "https://mops.twse.com.tw/mops/api/t05st01"
MOPS_DETAIL_ENDPOINT = "https://mops.twse.com.tw/mops/api/t05st01_detail"
SHA256_PREFIX = "sha256:"
_SHA256_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_ROC_DATE_PATTERN = re.compile(
    r"(?P<year>\d{3,4})\s*(?:年|/|-)\s*"
    r"(?P<month>\d{1,2})\s*(?:月|/|-)\s*"
    r"(?P<day>\d{1,2})\s*日?"
)
_TAIPEI = ZoneInfo("Asia/Taipei")
_RAW_KINDS = frozenset(
    {"mops_list", "mops_conversion_detail", "mops_listing_detail"}
)


class SecurityLifecycleContractError(ValueError):
    """Official security-lifecycle evidence cannot be safely contracted."""


class SecurityLifecycleScope(str, Enum):
    HISTORICAL_RESEARCH_REPLAY = "historical_research_replay"
    PROSPECTIVE_CAPTURE = "prospective_capture"


class SecurityLifecyclePhase(str, Enum):
    UNKNOWN = "unknown"
    NOT_EFFECTIVE = "not_effective"
    TRADING_SUSPENDED = "trading_suspended"
    SUCCESSOR_ACTIVE_WARMUP = "successor_active_warmup"


class SecurityMarketStatus(str, Enum):
    UNKNOWN = "unknown"
    PREDECESSOR_TRADABLE = "predecessor_tradable"
    TRADING_SUSPENDED = "trading_suspended"
    PREDECESSOR_TERMINATED_SUCCESSOR_TRADABLE = (
        "predecessor_terminated_successor_tradable"
    )


class SecurityIdentityStatus(str, Enum):
    NOT_VISIBLE = "not_visible"
    PREDECESSOR = "predecessor"
    SUCCESSOR = "successor"


class ScoreEligibility(str, Enum):
    NOT_VISIBLE = "not_visible"
    NOT_EFFECTIVE = "not_effective"
    MARKET_BLOCKED = "market_blocked"
    WARMUP_REQUIRED = "warmup_required"
    HISTORY_WARMUP_COMPLETE_REQUIRES_SCORER = (
        "history_warmup_complete_requires_scorer"
    )


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash_bytes(value: bytes) -> str:
    return SHA256_PREFIX + hashlib.sha256(value).hexdigest()


def _hash_json(value: object) -> str:
    return _hash_bytes(_canonical_json(value).encode("utf-8"))


def _aware_utc(value: datetime, *, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise SecurityLifecycleContractError(f"{field_name}_must_be_timezone_aware")
    return value.astimezone(timezone.utc)


def _iso_datetime(value: datetime) -> str:
    return _aware_utc(value, field_name="datetime").isoformat()


def _require_sha256(value: object, *, field_name: str) -> str:
    text = str(value or "")
    if not _SHA256_PATTERN.fullmatch(text):
        raise SecurityLifecycleContractError(f"{field_name}_must_be_sha256")
    return text


def _safe_text(value: object, *, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise SecurityLifecycleContractError(f"{field_name}_missing")
    return text


def _normalize_space(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _parse_roc_date(value: object, *, field_name: str) -> date:
    text = str(value or "").strip()
    match = _ROC_DATE_PATTERN.search(text)
    if match is None:
        raise SecurityLifecycleContractError(f"{field_name}_invalid_date")
    year = int(match.group("year"))
    if year < 1912:
        year += 1911
    try:
        return date(year, int(match.group("month")), int(match.group("day")))
    except ValueError as error:
        raise SecurityLifecycleContractError(f"{field_name}_invalid_date") from error


def _parse_roc_datetime(
    date_value: object,
    time_value: object,
    *,
    field_name: str,
) -> datetime:
    parsed_date = _parse_roc_date(date_value, field_name=field_name)
    time_text = str(time_value or "").strip()
    try:
        parsed_time = time.fromisoformat(time_text)
    except ValueError as error:
        raise SecurityLifecycleContractError(f"{field_name}_invalid_time") from error
    return datetime.combine(parsed_date, parsed_time, tzinfo=_TAIPEI).astimezone(
        timezone.utc
    )


def _parse_source_response_datetime(
    payload: Mapping[str, object], *, field_name: str
) -> datetime:
    value = _safe_text(payload.get("datetime"), field_name=f"{field_name}.datetime")
    parts = value.rsplit(" ", 1)
    if len(parts) != 2:
        raise SecurityLifecycleContractError(f"{field_name}_invalid_response_datetime")
    return _parse_roc_datetime(parts[0], parts[1], field_name=field_name)


def _date_after_label(text: str, label: str, *, field_name: str) -> date:
    pattern = re.compile(
        re.escape(label) + r"\s*[:：]?\s*" + _ROC_DATE_PATTERN.pattern
    )
    match = pattern.search(text)
    if match is None:
        raise SecurityLifecycleContractError(f"{field_name}_missing")
    return _parse_roc_date(match.group(0), field_name=field_name)


def _date_before_phrase(text: str, phrase: str, *, field_name: str) -> date:
    pattern = re.compile(
        _ROC_DATE_PATTERN.pattern + r"[\s\)）]*" + re.escape(phrase)
    )
    match = pattern.search(text)
    if match is None:
        raise SecurityLifecycleContractError(f"{field_name}_missing")
    return _parse_roc_date(match.group(0), field_name=field_name)


def _labeled_value(text: str, label: str, *, field_name: str) -> str:
    match = re.search(
        re.escape(label) + r"\s*[:：]\s*([^\r\n]+)",
        text,
    )
    if match is None:
        raise SecurityLifecycleContractError(f"{field_name}_missing")
    value = match.group(1).strip().strip("。；;")
    return _safe_text(value, field_name=field_name)


def _mapping(value: object, *, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise SecurityLifecycleContractError(f"{field_name}_must_be_object")
    return value


def _row(value: object, *, field_name: str) -> list[object]:
    if not isinstance(value, list):
        raise SecurityLifecycleContractError(f"{field_name}_must_be_row")
    if len(value) < 10:
        raise SecurityLifecycleContractError(f"{field_name}_too_short")
    return value


def _result(payload: Mapping[str, object], *, field_name: str) -> Mapping[str, object]:
    if payload.get("code") != 200:
        raise SecurityLifecycleContractError(f"{field_name}_not_success")
    return _mapping(payload.get("result"), field_name=f"{field_name}.result")


def _detail_row(payload: Mapping[str, object], *, field_name: str) -> tuple[str, list[object]]:
    result = _result(payload, field_name=field_name)
    company_id = _safe_text(result.get("companyId"), field_name=f"{field_name}.company_id")
    data = result.get("data")
    if not isinstance(data, list) or len(data) != 1:
        raise SecurityLifecycleContractError(f"{field_name}_must_have_one_detail_row")
    return company_id, _row(data[0], field_name=f"{field_name}.data[0]")


def _list_row(
    payload: Mapping[str, object],
    *,
    company_id: str,
    detail_row: Sequence[object],
) -> list[object]:
    result = _result(payload, field_name="mops_list")
    if _safe_text(result.get("companyId"), field_name="mops_list.company_id") != company_id:
        raise SecurityLifecycleContractError("mops_list_company_id_conflict")
    data = result.get("data")
    if not isinstance(data, list):
        raise SecurityLifecycleContractError("mops_list_data_invalid")
    detail_date = _safe_text(detail_row[1], field_name="detail.announcement_date")
    detail_time = _safe_text(detail_row[2], field_name="detail.announcement_time")
    detail_serial = _safe_text(detail_row[0], field_name="detail.serial_number")
    for candidate in data:
        if not isinstance(candidate, list) or len(candidate) < 6:
            continue
        if (
            str(candidate[0]).strip() != company_id
            or str(candidate[2]).strip() != detail_date
            or str(candidate[3]).strip() != detail_time
        ):
            continue
        metadata = _mapping(candidate[5], field_name="mops_list.row.metadata")
        params = _mapping(
            metadata.get("parameters"),
            field_name="mops_list.row.parameters",
        )
        if str(params.get("serialNumber") or "").strip() == detail_serial:
            return candidate
    raise SecurityLifecycleContractError("mops_list_detail_row_missing")


def _section_after(text: str, marker: str, *, field_name: str) -> str:
    start = text.find(marker)
    if start < 0:
        raise SecurityLifecycleContractError(f"{field_name}_section_missing")
    return text[start:]


def _security_identity(section: str, *, field_prefix: str) -> "SecurityIdentity":
    symbol = _labeled_value(section, "股票代號", field_name=f"{field_prefix}.symbol")
    if not re.fullmatch(r"\d{4,6}", symbol):
        raise SecurityLifecycleContractError(f"{field_prefix}.symbol_invalid")
    legal_name = _labeled_value(
        section,
        "公司中文名稱",
        field_name=f"{field_prefix}.legal_name",
    )
    abbreviation = _labeled_value(
        section,
        "公司中文簡稱",
        field_name=f"{field_prefix}.abbreviation",
    )
    return SecurityIdentity(
        symbol=symbol,
        legal_name=legal_name,
        abbreviation=abbreviation,
    )


def _extract_ratio(text: str) -> "ShareRatio":
    match = re.search(
        r"持股\s*(?P<numerator>[\d,]+)\s*股換發"
        r"[^\r\n。；;]*?股份\s*(?P<denominator>[\d,]+)\s*股",
        text,
    )
    if match is None:
        raise SecurityLifecycleContractError("share_conversion_ratio_missing")
    return ShareRatio(
        predecessor_shares=int(match.group("numerator").replace(",", "")),
        successor_shares=int(match.group("denominator").replace(",", "")),
    )


def _extract_converted_share_count(text: str) -> int:
    match = re.search(r"普通股\s*([\d,]+)\s*股全數轉換", text)
    if match is None:
        raise SecurityLifecycleContractError("converted_share_count_missing")
    value = int(match.group(1).replace(",", ""))
    if value <= 0:
        raise SecurityLifecycleContractError("converted_share_count_invalid")
    return value


def _extract_source_code(text: str, *, field_name: str) -> str:
    match = re.search(r"證券代號\s*為\s*[「『\"']?(\d{4,6})", text)
    if match is None:
        raise SecurityLifecycleContractError(f"{field_name}_missing")
    return match.group(1)


def _request_payload(ref: "RawResponseRef") -> dict[str, str]:
    return dict(ref.request_payload)


def _verify_source_refs(
    raw_refs: Sequence["RawResponseRef"],
    *,
    list_payload: Mapping[str, object],
    conversion_payload: Mapping[str, object],
    listing_payload: Mapping[str, object],
) -> tuple[dict[str, "RawResponseRef"], dict[str, Mapping[str, object]]]:
    refs_by_kind = {ref.kind: ref for ref in raw_refs}
    if set(refs_by_kind) != _RAW_KINDS:
        raise SecurityLifecycleContractError("raw_response_kinds_incomplete")
    payloads = {
        "mops_list": list_payload,
        "mops_conversion_detail": conversion_payload,
        "mops_listing_detail": listing_payload,
    }
    for kind, ref in refs_by_kind.items():
        if ref.method != "POST":
            raise SecurityLifecycleContractError(f"{kind}_method_invalid")
        expected_url = (
            MOPS_LIST_ENDPOINT if kind == "mops_list" else MOPS_DETAIL_ENDPOINT
        )
        if ref.source_url != expected_url:
            raise SecurityLifecycleContractError(f"{kind}_source_url_invalid")
        loaded = _read_verified_json(ref)
        if loaded != dict(payloads[kind]):
            raise SecurityLifecycleContractError(f"{kind}_raw_payload_mismatch")
    return refs_by_kind, payloads


def _read_verified_json(ref: "RawResponseRef") -> Mapping[str, object]:
    if ref.path.is_symlink() or not ref.path.is_file():
        raise SecurityLifecycleContractError(f"raw_response_missing:{ref.kind}")
    try:
        raw = ref.path.read_bytes()
    except OSError as error:
        raise SecurityLifecycleContractError(f"raw_response_unreadable:{ref.kind}") from error
    if _hash_bytes(raw) != ref.sha256:
        raise SecurityLifecycleContractError(f"raw_response_hash_mismatch:{ref.kind}")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SecurityLifecycleContractError(f"raw_response_json_invalid:{ref.kind}") from error
    return _mapping(value, field_name=f"raw_response.{ref.kind}")


@dataclass(frozen=True)
class RawResponseRef:
    """Exact request and immutable local custody reference for one MOPS response."""

    kind: str
    path: Path
    sha256: str
    source_url: str
    method: str
    request_payload: tuple[tuple[str, str], ...]
    captured_at: datetime

    def __post_init__(self) -> None:
        kind = _safe_text(self.kind, field_name="raw_response.kind")
        path = Path(self.path).expanduser().resolve()
        source_url = _safe_text(self.source_url, field_name="raw_response.source_url")
        method = _safe_text(self.method, field_name="raw_response.method").upper()
        request_payload = tuple(
            sorted((str(key), str(value)) for key, value in self.request_payload)
        )
        if not source_url.startswith("https://"):
            raise SecurityLifecycleContractError("raw_response_source_url_must_be_https")
        if method != "POST":
            raise SecurityLifecycleContractError("raw_response_method_must_be_post")
        _require_sha256(self.sha256, field_name="raw_response.sha256")
        captured_at = _aware_utc(self.captured_at, field_name="raw_response.captured_at")
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "path", path)
        object.__setattr__(self, "source_url", source_url)
        object.__setattr__(self, "method", method)
        object.__setattr__(self, "request_payload", request_payload)
        object.__setattr__(self, "captured_at", captured_at)

    @classmethod
    def from_file(
        cls,
        *,
        kind: str,
        path: Path,
        source_url: str,
        request_payload: Mapping[str, object],
        captured_at: datetime,
    ) -> "RawResponseRef":
        resolved = Path(path).expanduser().resolve()
        if resolved.is_symlink() or not resolved.is_file():
            raise SecurityLifecycleContractError(f"raw_response_missing:{kind}")
        return cls(
            kind=kind,
            path=resolved,
            sha256=_hash_bytes(resolved.read_bytes()),
            source_url=source_url,
            method="POST",
            request_payload=tuple((str(key), str(value)) for key, value in request_payload.items()),
            captured_at=captured_at,
        )

    def to_payload(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "path": str(self.path),
            "sha256": self.sha256,
            "source_url": self.source_url,
            "method": self.method,
            "request_payload": {key: value for key, value in self.request_payload},
            "captured_at": _iso_datetime(self.captured_at),
        }


@dataclass(frozen=True)
class SecurityIdentity:
    symbol: str
    legal_name: str
    abbreviation: str

    def __post_init__(self) -> None:
        symbol = _safe_text(self.symbol, field_name="security.symbol")
        if not re.fullmatch(r"\d{4,6}", symbol):
            raise SecurityLifecycleContractError("security.symbol_invalid")
        object.__setattr__(self, "symbol", symbol)
        object.__setattr__(
            self,
            "legal_name",
            _safe_text(self.legal_name, field_name="security.legal_name"),
        )
        object.__setattr__(
            self,
            "abbreviation",
            _safe_text(self.abbreviation, field_name="security.abbreviation"),
        )

    def to_payload(self) -> dict[str, str]:
        return {
            "symbol": self.symbol,
            "legal_name": self.legal_name,
            "abbreviation": self.abbreviation,
        }


@dataclass(frozen=True)
class ShareRatio:
    predecessor_shares: int
    successor_shares: int

    def __post_init__(self) -> None:
        if isinstance(self.predecessor_shares, bool) or not isinstance(
            self.predecessor_shares, int
        ):
            raise SecurityLifecycleContractError("predecessor_shares_must_be_int")
        if isinstance(self.successor_shares, bool) or not isinstance(
            self.successor_shares, int
        ):
            raise SecurityLifecycleContractError("successor_shares_must_be_int")
        if self.predecessor_shares <= 0 or self.successor_shares <= 0:
            raise SecurityLifecycleContractError("share_ratio_must_be_positive")

    def to_payload(self) -> dict[str, int | str]:
        return {
            "predecessor_shares": self.predecessor_shares,
            "successor_shares": self.successor_shares,
            "predecessor_to_successor": (
                f"{self.predecessor_shares}:{self.successor_shares}"
            ),
        }


@dataclass(frozen=True)
class SuccessorSessionEvidence:
    """Caller-verified successor session and its own price lineage."""

    session_date: date
    symbol: str
    official_trading_day_verified: bool
    price_source_id: str
    price_lineage_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.session_date, date) or isinstance(self.session_date, datetime):
            raise SecurityLifecycleContractError("session_date_invalid")
        symbol = _safe_text(self.symbol, field_name="session.symbol")
        if not re.fullmatch(r"\d{4,6}", symbol):
            raise SecurityLifecycleContractError("session.symbol_invalid")
        if self.official_trading_day_verified is not True:
            raise SecurityLifecycleContractError("official_trading_day_verification_missing")
        source_id = _safe_text(self.price_source_id, field_name="session.price_source_id")
        lineage_hash = _require_sha256(
            self.price_lineage_sha256,
            field_name="session.price_lineage_sha256",
        )
        object.__setattr__(self, "symbol", symbol)
        object.__setattr__(self, "price_source_id", source_id)
        object.__setattr__(self, "price_lineage_sha256", lineage_hash)


@dataclass(frozen=True)
class SecurityLifecycleEvent:
    event_id: str
    source_id: str
    source_scope: SecurityLifecycleScope
    original: SecurityIdentity
    predecessor: SecurityIdentity
    successor: SecurityIdentity
    ratio: ShareRatio
    converted_share_count: int
    announcement_at: datetime
    last_trade_date: date
    halt_from: date
    conversion_base_date: date
    termination_date: date
    successor_listed_date: date
    source_available_at: datetime
    available_at: datetime
    captured_at: datetime
    raw_response_refs: tuple[RawResponseRef, ...]
    research_only: bool = True
    formal_credit_allowed: bool = False
    natural_credit_allowed: bool = False
    historical_price_score_carry_forward_allowed: bool = False

    def __post_init__(self) -> None:
        _require_sha256(self.event_id, field_name="event_id")
        source_id = _safe_text(self.source_id, field_name="source_id")
        source_scope = (
            self.source_scope
            if isinstance(self.source_scope, SecurityLifecycleScope)
            else SecurityLifecycleScope(str(self.source_scope))
        )
        if self.original.symbol != self.predecessor.symbol:
            raise SecurityLifecycleContractError("original_predecessor_symbol_conflict")
        if self.original.legal_name != self.predecessor.legal_name:
            raise SecurityLifecycleContractError("original_predecessor_name_conflict")
        if (
            isinstance(self.converted_share_count, bool)
            or not isinstance(self.converted_share_count, int)
            or self.converted_share_count <= 0
        ):
            raise SecurityLifecycleContractError("converted_share_count_invalid")
        announcement_at = _aware_utc(self.announcement_at, field_name="announcement_at")
        source_available_at = _aware_utc(
            self.source_available_at,
            field_name="source_available_at",
        )
        available_at = _aware_utc(self.available_at, field_name="available_at")
        captured_at = _aware_utc(self.captured_at, field_name="captured_at")
        if announcement_at > available_at:
            raise SecurityLifecycleContractError("available_before_announcement")
        if source_available_at > available_at:
            raise SecurityLifecycleContractError("available_before_source_response")
        if available_at > captured_at:
            raise SecurityLifecycleContractError("captured_before_available")
        if announcement_at.astimezone(_TAIPEI).date() > self.last_trade_date:
            raise SecurityLifecycleContractError("announcement_after_last_trade")
        if not (
            self.last_trade_date < self.halt_from <= self.conversion_base_date
            and self.conversion_base_date == self.termination_date
            and self.termination_date == self.successor_listed_date
        ):
            raise SecurityLifecycleContractError("unsupported_lifecycle_date_shape")
        refs = tuple(self.raw_response_refs)
        if {ref.kind for ref in refs} != _RAW_KINDS:
            raise SecurityLifecycleContractError("raw_response_kinds_incomplete")
        if any(ref.captured_at > captured_at for ref in refs):
            raise SecurityLifecycleContractError("raw_capture_after_event_capture")
        if any(ref.captured_at > available_at for ref in refs):
            raise SecurityLifecycleContractError("available_before_raw_capture")
        if type(self.research_only) is not bool or self.research_only is not True:
            raise SecurityLifecycleContractError("research_only_guard_invalid")
        for field_name in (
            "formal_credit_allowed",
            "natural_credit_allowed",
            "historical_price_score_carry_forward_allowed",
        ):
            if getattr(self, field_name) is not False:
                raise SecurityLifecycleContractError(f"{field_name}_must_be_false")
        object.__setattr__(self, "source_id", source_id)
        object.__setattr__(self, "source_scope", source_scope)
        object.__setattr__(self, "announcement_at", announcement_at)
        object.__setattr__(self, "source_available_at", source_available_at)
        object.__setattr__(self, "available_at", available_at)
        object.__setattr__(self, "captured_at", captured_at)
        object.__setattr__(self, "raw_response_refs", refs)

    @property
    def raw_response_hashes(self) -> tuple[str, ...]:
        return tuple(ref.sha256 for ref in sorted(self.raw_response_refs, key=lambda item: item.kind))

    def _identity_payload(self) -> dict[str, object]:
        return {
            "source_id": self.source_id,
            "original": self.original.to_payload(),
            "predecessor": self.predecessor.to_payload(),
            "successor": self.successor.to_payload(),
            "ratio": self.ratio.to_payload(),
            "converted_share_count": self.converted_share_count,
            "announcement_at": _iso_datetime(self.announcement_at),
            "last_trade_date": self.last_trade_date.isoformat(),
            "halt_from": self.halt_from.isoformat(),
            "conversion_base_date": self.conversion_base_date.isoformat(),
            "termination_date": self.termination_date.isoformat(),
            "successor_listed_date": self.successor_listed_date.isoformat(),
        }

    def _body_payload(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "event_id": self.event_id,
            "source_id": self.source_id,
            "source_scope": self.source_scope.value,
            "original": self.original.to_payload(),
            "predecessor": self.predecessor.to_payload(),
            "successor": self.successor.to_payload(),
            "ratio": self.ratio.to_payload(),
            "converted_share_count": self.converted_share_count,
            "announcement_at": _iso_datetime(self.announcement_at),
            "last_trade_date": self.last_trade_date.isoformat(),
            "halt_from": self.halt_from.isoformat(),
            "conversion_base_date": self.conversion_base_date.isoformat(),
            "termination_date": self.termination_date.isoformat(),
            "successor_listed_date": self.successor_listed_date.isoformat(),
            "source_available_at": _iso_datetime(self.source_available_at),
            "available_at": _iso_datetime(self.available_at),
            "captured_at": _iso_datetime(self.captured_at),
            "raw_response_refs": [
                ref.to_payload()
                for ref in sorted(self.raw_response_refs, key=lambda item: item.kind)
            ],
            "quality": {
                "research_only": self.research_only,
                "formal_credit_allowed": self.formal_credit_allowed,
                "natural_credit_allowed": self.natural_credit_allowed,
                "historical_price_score_carry_forward_allowed": (
                    self.historical_price_score_carry_forward_allowed
                ),
            },
        }

    @property
    def event_hash(self) -> str:
        return _hash_json(self._body_payload())

    def to_payload(self) -> dict[str, object]:
        return {**self._body_payload(), "event_hash": self.event_hash}


@dataclass(frozen=True)
class SecurityLifecycleState:
    decision_at: datetime
    decision_date: date
    visible: bool
    phase: SecurityLifecyclePhase
    identity_status: SecurityIdentityStatus
    market_status: SecurityMarketStatus
    current_symbol: str | None
    predecessor_symbol: str
    successor_symbol: str
    market_tradable: bool | None
    history_warmup_complete: bool | None
    score_eligibility: ScoreEligibility
    reason_codes: tuple[str, ...]
    formal_credit_allowed: bool = False
    natural_credit_allowed: bool = False
    historical_price_score_carry_forward_allowed: bool = False

    def __post_init__(self) -> None:
        if any(
            flag is not False
            for flag in (
                self.formal_credit_allowed,
                self.natural_credit_allowed,
                self.historical_price_score_carry_forward_allowed,
            )
        ):
            raise SecurityLifecycleContractError("state_credit_guard_invalid")


def _validate_event_identity(event: SecurityLifecycleEvent) -> None:
    expected_event_id = _hash_json(event._identity_payload())
    if event.event_id != expected_event_id:
        raise SecurityLifecycleContractError("event_id_mismatch")


def _validate_request_identity(
    refs_by_kind: Mapping[str, RawResponseRef],
    *,
    company_id: str,
    announcement_date: str,
    conversion_serial: str,
    listing_serial: str,
) -> None:
    list_request = _request_payload(refs_by_kind["mops_list"])
    if list_request.get("companyId") != company_id:
        raise SecurityLifecycleContractError("mops_list_request_company_conflict")
    roc_year = announcement_date.split("/", 1)[0]
    if list_request.get("year") != roc_year:
        raise SecurityLifecycleContractError("mops_list_request_year_conflict")
    if list_request.get("month") not in {"all", ""}:
        raise SecurityLifecycleContractError("mops_list_request_month_not_full_year")
    for kind, serial in (
        ("mops_conversion_detail", conversion_serial),
        ("mops_listing_detail", listing_serial),
    ):
        request = _request_payload(refs_by_kind[kind])
        if (
            request.get("marketKind") != "pub"
            or request.get("companyId") != company_id
            or request.get("serialNumber") != serial
            or request.get("enterDate") != announcement_date.replace("/", "")
        ):
            raise SecurityLifecycleContractError(f"{kind}_request_identity_conflict")


def parse_mops_security_lifecycle(
    list_payload: Mapping[str, object],
    conversion_detail_payload: Mapping[str, object],
    listing_detail_payload: Mapping[str, object],
    *,
    raw_refs: Sequence[RawResponseRef],
    captured_at: datetime,
    source_scope: SecurityLifecycleScope = SecurityLifecycleScope.PROSPECTIVE_CAPTURE,
    declared_predecessor_symbol: str | None = None,
    declared_successor_symbol: str | None = None,
    declared_ratio: ShareRatio | tuple[int, int] | None = None,
) -> SecurityLifecycleEvent:
    """Parse one supported MOPS share-conversion event from its raw responses.

    The parser deliberately derives symbols, names, ratios, and dates from the
    supplied official detail bodies.  Declarations are optional cross-checks;
    they are never used to fill missing source fields.
    """

    captured_utc = _aware_utc(captured_at, field_name="captured_at")
    refs_by_kind, payloads = _verify_source_refs(
        raw_refs,
        list_payload=list_payload,
        conversion_payload=conversion_detail_payload,
        listing_payload=listing_detail_payload,
    )
    conversion_company_id, conversion_row = _detail_row(
        conversion_detail_payload,
        field_name="mops_conversion_detail",
    )
    listing_company_id, listing_row = _detail_row(
        listing_detail_payload,
        field_name="mops_listing_detail",
    )
    if conversion_company_id != listing_company_id:
        raise SecurityLifecycleContractError("detail_company_id_conflict")
    company_id = conversion_company_id
    list_row = _list_row(
        list_payload,
        company_id=company_id,
        detail_row=conversion_row,
    )
    list_title = _normalize_space(list_row[4])
    conversion_title = _normalize_space(conversion_row[6])
    listing_title = _normalize_space(listing_row[6])
    if list_title != conversion_title:
        raise SecurityLifecycleContractError("list_detail_title_conflict")
    if "股份轉換" not in conversion_title or "股份轉換基準日" not in conversion_title:
        raise SecurityLifecycleContractError("unsupported_conversion_announcement_shape")
    if "上櫃" not in listing_title or "終止上櫃" not in listing_title:
        raise SecurityLifecycleContractError("unsupported_listing_announcement_shape")

    conversion_text = _safe_text(
        conversion_row[9],
        field_name="mops_conversion_detail.explanation",
    )
    listing_text = _safe_text(
        listing_row[9],
        field_name="mops_listing_detail.explanation",
    )
    successor_section = _section_after(
        conversion_text,
        "上櫃股票代號、公司簡稱及產業類別",
        field_name="successor",
    )
    predecessor_section = _section_after(
        conversion_text,
        "終止上櫃股票代號及簡稱及產業類別",
        field_name="predecessor",
    )
    successor = _security_identity(successor_section, field_prefix="successor")
    predecessor = _security_identity(predecessor_section, field_prefix="predecessor")
    original_name = _labeled_value(
        conversion_text,
        "公司名稱",
        field_name="original.legal_name",
    )
    original = SecurityIdentity(
        symbol=company_id,
        legal_name=original_name,
        abbreviation=predecessor.abbreviation,
    )
    if predecessor.symbol != company_id:
        raise SecurityLifecycleContractError("declared_predecessor_symbol_conflict")
    if predecessor.legal_name != original_name:
        raise SecurityLifecycleContractError("predecessor_name_conflict")
    detail_listing_symbol = _extract_source_code(
        listing_text,
        field_name="listing.successor_symbol",
    )
    if detail_listing_symbol != successor.symbol:
        raise SecurityLifecycleContractError("successor_symbol_conflict")

    ratio = _extract_ratio(conversion_text)
    if declared_ratio is not None:
        expected_ratio = (
            declared_ratio
            if isinstance(declared_ratio, ShareRatio)
            else ShareRatio(*declared_ratio)
        )
        if ratio != expected_ratio:
            raise SecurityLifecycleContractError("declared_ratio_conflict")
    if declared_predecessor_symbol is not None and declared_predecessor_symbol != predecessor.symbol:
        raise SecurityLifecycleContractError("declared_predecessor_symbol_conflict")
    if declared_successor_symbol is not None and declared_successor_symbol != successor.symbol:
        raise SecurityLifecycleContractError("declared_successor_symbol_conflict")

    converted_share_count = _extract_converted_share_count(conversion_text)
    announcement_at = _parse_roc_datetime(
        conversion_row[1],
        conversion_row[2],
        field_name="announcement_at",
    )
    listing_announcement_at = _parse_roc_datetime(
        listing_row[1],
        listing_row[2],
        field_name="listing_announcement_at",
    )
    if announcement_at.astimezone(_TAIPEI).date() != listing_announcement_at.astimezone(
        _TAIPEI
    ).date():
        raise SecurityLifecycleContractError("announcement_date_conflict")
    last_trade_date = _date_after_label(
        conversion_text,
        "股票最後交易日",
        field_name="last_trade_date",
    )
    halt_from = _date_after_label(
        conversion_text,
        "股票停止買賣日",
        field_name="halt_from",
    )
    conversion_base_date = _date_after_label(
        conversion_text,
        "終止上櫃日期暨股份轉換基準日",
        field_name="conversion_base_date",
    )
    successor_listed_date = _date_after_label(
        conversion_text,
        "股票開始上櫃買賣日期",
        field_name="successor_listed_date",
    )
    termination_date = conversion_base_date
    if not re.search(r"終止上櫃", listing_text):
        raise SecurityLifecycleContractError("listing_termination_statement_missing")
    listing_termination_date = _date_before_phrase(
        listing_text,
        "終止上櫃",
        field_name="listing.termination_date",
    )
    listing_start_date = _date_before_phrase(
        listing_text,
        "起上櫃",
        field_name="listing.start_date",
    )
    if listing_termination_date != conversion_base_date:
        raise SecurityLifecycleContractError("listing_termination_date_conflict")
    if listing_start_date != successor_listed_date:
        raise SecurityLifecycleContractError("listing_start_date_conflict")

    source_available_at = max(
        _parse_source_response_datetime(payload, field_name=kind)
        for kind, payload in payloads.items()
    )
    if announcement_at > captured_utc:
        raise SecurityLifecycleContractError("future_announcement_at_capture")
    if source_available_at > captured_utc:
        raise SecurityLifecycleContractError("capture_before_source_available")
    _validate_request_identity(
        refs_by_kind,
        company_id=company_id,
        announcement_date=_safe_text(
            conversion_row[1],
            field_name="announcement_date",
        ),
        conversion_serial=_safe_text(conversion_row[0], field_name="conversion_serial"),
        listing_serial=_safe_text(listing_row[0], field_name="listing_serial"),
    )
    event_identity = {
        "source_id": SOURCE_ID,
        "original": original.to_payload(),
        "predecessor": predecessor.to_payload(),
        "successor": successor.to_payload(),
        "ratio": ratio.to_payload(),
        "converted_share_count": converted_share_count,
        "announcement_at": _iso_datetime(announcement_at),
        "last_trade_date": last_trade_date.isoformat(),
        "halt_from": halt_from.isoformat(),
        "conversion_base_date": conversion_base_date.isoformat(),
        "termination_date": termination_date.isoformat(),
        "successor_listed_date": successor_listed_date.isoformat(),
    }
    event = SecurityLifecycleEvent(
        event_id=_hash_json(event_identity),
        source_id=SOURCE_ID,
        source_scope=source_scope,
        original=original,
        predecessor=predecessor,
        successor=successor,
        ratio=ratio,
        converted_share_count=converted_share_count,
        announcement_at=announcement_at,
        last_trade_date=last_trade_date,
        halt_from=halt_from,
        conversion_base_date=conversion_base_date,
        termination_date=termination_date,
        successor_listed_date=successor_listed_date,
        source_available_at=source_available_at,
        available_at=max(
            captured_utc,
            source_available_at,
            *(ref.captured_at for ref in refs_by_kind.values()),
        ),
        captured_at=captured_utc,
        raw_response_refs=tuple(refs_by_kind.values()),
    )
    _validate_event_identity(event)
    return event


def _normalize_sessions(
    observed_sessions: Sequence[SuccessorSessionEvidence | date | str] | None,
    *,
    successor_symbol: str,
    successor_listed_date: date,
    decision_date: date,
) -> tuple[tuple[SuccessorSessionEvidence, ...] | None, bool, str]:
    if observed_sessions is None:
        return None, True, "not_provided"
    evidence: list[SuccessorSessionEvidence] = []
    for value in observed_sessions:
        if isinstance(value, SuccessorSessionEvidence):
            evidence.append(value)
        elif isinstance(value, date) and not isinstance(value, datetime):
            return tuple(), False, "date_window_not_caller_verified"
        elif isinstance(value, str):
            return tuple(), False, "date_window_not_caller_verified"
        else:
            return tuple(), False, "session_evidence_type_invalid"
    dates = [item.session_date for item in evidence]
    if len(dates) != len(set(dates)):
        return tuple(sorted(evidence, key=lambda item: item.session_date)), False, "duplicate_session_date"
    if any(item.symbol != successor_symbol for item in evidence):
        return tuple(sorted(evidence, key=lambda item: item.session_date)), False, "session_symbol_not_successor"
    ordered = tuple(sorted(evidence, key=lambda item: item.session_date))
    if not all(
        item.session_date >= successor_listed_date and item.session_date < decision_date
        for item in ordered
    ):
        return ordered, False, "session_outside_successor_window"
    return ordered, True, "verified_successor_session_window"


def security_lifecycle_state_as_of(
    event: SecurityLifecycleEvent,
    decision_at: datetime,
    *,
    observed_sessions: Sequence[SuccessorSessionEvidence | date | str] | None = None,
    required_warmup_sessions: int = 20,
) -> SecurityLifecycleState:
    """Project lifecycle state without granting final scorer readiness.

    ``observed_sessions`` must be caller-verified successor evidence.  A
    sequence of bare dates/strings is accepted only to return an unknown
    warm-up result; this helper does not implement an exchange calendar or
    verify T-1 features.
    """

    if type(required_warmup_sessions) is not int or required_warmup_sessions <= 0:
        raise SecurityLifecycleContractError("required_warmup_sessions_invalid")
    decision_utc = _aware_utc(decision_at, field_name="decision_at")
    decision_date = decision_utc.astimezone(_TAIPEI).date()
    base: dict[str, Any] = {
        "decision_at": decision_utc,
        "decision_date": decision_date,
        "predecessor_symbol": event.predecessor.symbol,
        "successor_symbol": event.successor.symbol,
        "formal_credit_allowed": False,
        "natural_credit_allowed": False,
        "historical_price_score_carry_forward_allowed": False,
    }
    if event.announcement_at > decision_utc or event.available_at > decision_utc:
        return SecurityLifecycleState(
            **base,
            visible=False,
            phase=SecurityLifecyclePhase.UNKNOWN,
            identity_status=SecurityIdentityStatus.NOT_VISIBLE,
            market_status=SecurityMarketStatus.UNKNOWN,
            current_symbol=None,
            market_tradable=None,
            history_warmup_complete=None,
            score_eligibility=ScoreEligibility.NOT_VISIBLE,
            reason_codes=("event_not_visible_at_decision_cutoff",),
        )

    if decision_date < event.successor_listed_date:
        if decision_date >= event.halt_from:
            return SecurityLifecycleState(
                **base,
                visible=True,
                phase=SecurityLifecyclePhase.NOT_EFFECTIVE,
                identity_status=SecurityIdentityStatus.PREDECESSOR,
                market_status=SecurityMarketStatus.TRADING_SUSPENDED,
                current_symbol=event.predecessor.symbol,
                market_tradable=False,
                history_warmup_complete=None,
                score_eligibility=ScoreEligibility.MARKET_BLOCKED,
                reason_codes=(
                    "successor_effective_date_not_reached",
                    "predecessor_trading_suspended",
                ),
            )
        return SecurityLifecycleState(
            **base,
            visible=True,
            phase=SecurityLifecyclePhase.NOT_EFFECTIVE,
            identity_status=SecurityIdentityStatus.PREDECESSOR,
            market_status=SecurityMarketStatus.PREDECESSOR_TRADABLE,
            current_symbol=event.predecessor.symbol,
            market_tradable=True,
            history_warmup_complete=None,
            score_eligibility=ScoreEligibility.NOT_EFFECTIVE,
            reason_codes=("successor_effective_date_not_reached",),
        )

    normalized_sessions, sessions_in_window, session_reason = _normalize_sessions(
        observed_sessions,
        successor_symbol=event.successor.symbol,
        successor_listed_date=event.successor_listed_date,
        decision_date=decision_date,
    )
    history_warmup_complete: bool | None
    reasons = ["predecessor_security_terminated", "successor_security_active"]
    if normalized_sessions is None:
        history_warmup_complete = None
        score_eligibility = ScoreEligibility.WARMUP_REQUIRED
        reasons.append("successor_history_evidence_not_provided")
    elif not sessions_in_window:
        history_warmup_complete = (
            None
            if session_reason == "date_window_not_caller_verified"
            else False
        )
        score_eligibility = ScoreEligibility.WARMUP_REQUIRED
        reasons.append(session_reason)
    else:
        history_warmup_complete = len(normalized_sessions) >= required_warmup_sessions
        score_eligibility = (
            ScoreEligibility.HISTORY_WARMUP_COMPLETE_REQUIRES_SCORER
            if history_warmup_complete
            else ScoreEligibility.WARMUP_REQUIRED
        )
        reasons.append(
            "successor_history_window_complete"
            if history_warmup_complete
            else "successor_history_warmup_incomplete"
        )
        if history_warmup_complete:
            reasons.append("final_score_readiness_not_evaluated_by_lifecycle_helper")
    return SecurityLifecycleState(
        **base,
        visible=True,
        phase=SecurityLifecyclePhase.SUCCESSOR_ACTIVE_WARMUP,
        identity_status=SecurityIdentityStatus.SUCCESSOR,
        market_status=SecurityMarketStatus.PREDECESSOR_TERMINATED_SUCCESSOR_TRADABLE,
        current_symbol=event.successor.symbol,
        market_tradable=True,
        history_warmup_complete=history_warmup_complete,
        score_eligibility=score_eligibility,
        reason_codes=tuple(reasons),
    )


def write_security_lifecycle_contract(
    path: Path,
    event: SecurityLifecycleEvent,
) -> str:
    """Write one canonical create-only contract and return its contract hash."""

    _validate_event_identity(event)
    for ref in event.raw_response_refs:
        _read_verified_json(ref)
    body = event.to_payload()
    contract = {**body, "contract_hash": _hash_json(body)}
    encoded = (_canonical_json(contract) + "\n").encode("utf-8")
    output = Path(path).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        if output.is_symlink() or output.read_bytes() != encoded:
            raise SecurityLifecycleContractError("immutable_contract_conflict")
        return str(contract["contract_hash"])
    temporary = output.with_name(f".{output.name}.{os.getpid()}.{uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, output)
        except FileExistsError:
            if output.read_bytes() != encoded:
                raise SecurityLifecycleContractError("immutable_contract_race_conflict")
    finally:
        temporary.unlink(missing_ok=True)
    return str(contract["contract_hash"])


def _identity_from_payload(value: object, *, field_name: str) -> SecurityIdentity:
    payload = _mapping(value, field_name=field_name)
    return SecurityIdentity(
        symbol=_safe_text(payload.get("symbol"), field_name=f"{field_name}.symbol"),
        legal_name=_safe_text(payload.get("legal_name"), field_name=f"{field_name}.legal_name"),
        abbreviation=_safe_text(
            payload.get("abbreviation"),
            field_name=f"{field_name}.abbreviation",
        ),
    )


def _ref_from_payload(value: object, *, field_name: str) -> RawResponseRef:
    payload = _mapping(value, field_name=field_name)
    request_payload = _mapping(
        payload.get("request_payload"),
        field_name=f"{field_name}.request_payload",
    )
    return RawResponseRef(
        kind=_safe_text(payload.get("kind"), field_name=f"{field_name}.kind"),
        path=Path(_safe_text(payload.get("path"), field_name=f"{field_name}.path")),
        sha256=_safe_text(payload.get("sha256"), field_name=f"{field_name}.sha256"),
        source_url=_safe_text(
            payload.get("source_url"),
            field_name=f"{field_name}.source_url",
        ),
        method=_safe_text(payload.get("method"), field_name=f"{field_name}.method"),
        request_payload=tuple((str(key), str(value)) for key, value in request_payload.items()),
        captured_at=datetime.fromisoformat(
            _safe_text(payload.get("captured_at"), field_name=f"{field_name}.captured_at")
        ),
    )


def _event_from_payload(payload: Mapping[str, object]) -> SecurityLifecycleEvent:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise SecurityLifecycleContractError("contract_schema_version_invalid")
    ratio_payload = _mapping(payload.get("ratio"), field_name="contract.ratio")
    predecessor_shares = ratio_payload.get("predecessor_shares")
    successor_shares = ratio_payload.get("successor_shares")
    if (
        isinstance(predecessor_shares, bool)
        or not isinstance(predecessor_shares, int)
        or isinstance(successor_shares, bool)
        or not isinstance(successor_shares, int)
    ):
        raise SecurityLifecycleContractError("contract.ratio_must_be_integer")
    converted_share_count = payload.get("converted_share_count")
    if (
        isinstance(converted_share_count, bool)
        or not isinstance(converted_share_count, int)
    ):
        raise SecurityLifecycleContractError("contract.converted_share_count_must_be_integer")
    quality = _mapping(payload.get("quality"), field_name="contract.quality")
    raw_refs_payload = payload.get("raw_response_refs")
    if not isinstance(raw_refs_payload, list):
        raise SecurityLifecycleContractError("contract.raw_response_refs_invalid")
    event = SecurityLifecycleEvent(
        event_id=_safe_text(payload.get("event_id"), field_name="contract.event_id"),
        source_id=_safe_text(payload.get("source_id"), field_name="contract.source_id"),
        source_scope=SecurityLifecycleScope(
            _safe_text(payload.get("source_scope"), field_name="contract.source_scope")
        ),
        original=_identity_from_payload(payload.get("original"), field_name="contract.original"),
        predecessor=_identity_from_payload(
            payload.get("predecessor"),
            field_name="contract.predecessor",
        ),
        successor=_identity_from_payload(payload.get("successor"), field_name="contract.successor"),
        ratio=ShareRatio(
            predecessor_shares=predecessor_shares,
            successor_shares=successor_shares,
        ),
        converted_share_count=converted_share_count,
        announcement_at=datetime.fromisoformat(
            _safe_text(payload.get("announcement_at"), field_name="contract.announcement_at")
        ),
        last_trade_date=date.fromisoformat(
            _safe_text(payload.get("last_trade_date"), field_name="contract.last_trade_date")
        ),
        halt_from=date.fromisoformat(
            _safe_text(payload.get("halt_from"), field_name="contract.halt_from")
        ),
        conversion_base_date=date.fromisoformat(
            _safe_text(
                payload.get("conversion_base_date"),
                field_name="contract.conversion_base_date",
            )
        ),
        termination_date=date.fromisoformat(
            _safe_text(payload.get("termination_date"), field_name="contract.termination_date")
        ),
        successor_listed_date=date.fromisoformat(
            _safe_text(
                payload.get("successor_listed_date"),
                field_name="contract.successor_listed_date",
            )
        ),
        available_at=datetime.fromisoformat(
            _safe_text(payload.get("available_at"), field_name="contract.available_at")
        ),
        source_available_at=datetime.fromisoformat(
            _safe_text(
                payload.get("source_available_at"),
                field_name="contract.source_available_at",
            )
        ),
        captured_at=datetime.fromisoformat(
            _safe_text(payload.get("captured_at"), field_name="contract.captured_at")
        ),
        raw_response_refs=tuple(
            _ref_from_payload(item, field_name=f"contract.raw_response_refs[{index}]")
            for index, item in enumerate(raw_refs_payload)
        ),
        research_only=quality.get("research_only") is True,
        formal_credit_allowed=quality.get("formal_credit_allowed") is True,
        natural_credit_allowed=quality.get("natural_credit_allowed") is True,
        historical_price_score_carry_forward_allowed=(
            quality.get("historical_price_score_carry_forward_allowed") is True
        ),
    )
    if payload.get("event_hash") != event.event_hash:
        raise SecurityLifecycleContractError("contract_event_hash_mismatch")
    _validate_event_identity(event)
    return event


def read_security_lifecycle_contract(path: Path) -> SecurityLifecycleEvent:
    """Read, hash-check, raw-check, and reparse an immutable contract."""

    contract_path = Path(path).expanduser().resolve()
    if contract_path.is_symlink() or not contract_path.is_file():
        raise SecurityLifecycleContractError("contract_missing")
    raw = contract_path.read_bytes()
    try:
        decoded = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SecurityLifecycleContractError("contract_json_invalid") from error
    payload = _mapping(decoded, field_name="contract")
    if raw != (_canonical_json(payload) + "\n").encode("utf-8"):
        raise SecurityLifecycleContractError("contract_not_canonical")
    contract_hash = _require_sha256(
        payload.get("contract_hash"),
        field_name="contract_hash",
    )
    body = dict(payload)
    body.pop("contract_hash", None)
    if _hash_json(body) != contract_hash:
        raise SecurityLifecycleContractError("contract_hash_mismatch")
    event = _event_from_payload(body)
    raw_payloads = {
        ref.kind: _read_verified_json(ref) for ref in event.raw_response_refs
    }
    reparsed = parse_mops_security_lifecycle(
        raw_payloads["mops_list"],
        raw_payloads["mops_conversion_detail"],
        raw_payloads["mops_listing_detail"],
        raw_refs=event.raw_response_refs,
        captured_at=event.captured_at,
        source_scope=event.source_scope,
        declared_predecessor_symbol=event.predecessor.symbol,
        declared_successor_symbol=event.successor.symbol,
        declared_ratio=event.ratio,
    )
    if reparsed.to_payload() != event.to_payload():
        raise SecurityLifecycleContractError("contract_reparse_mismatch")
    return event


__all__ = [
    "MOPS_DETAIL_ENDPOINT",
    "MOPS_LIST_ENDPOINT",
    "SCHEMA_VERSION",
    "ScoreEligibility",
    "SecurityIdentity",
    "SecurityIdentityStatus",
    "SecurityLifecycleContractError",
    "SecurityLifecycleEvent",
    "SecurityLifecyclePhase",
    "SecurityLifecycleScope",
    "SecurityLifecycleState",
    "SecurityMarketStatus",
    "RawResponseRef",
    "ShareRatio",
    "SuccessorSessionEvidence",
    "parse_mops_security_lifecycle",
    "read_security_lifecycle_contract",
    "security_lifecycle_state_as_of",
    "write_security_lifecycle_contract",
]
