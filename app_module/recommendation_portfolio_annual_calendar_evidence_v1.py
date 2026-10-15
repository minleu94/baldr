"""候選年度 TPEx／TWSE 期間行事曆證據的純 codec。"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
import hashlib
import re
from typing import Literal, NoReturn, overload

from app_module.recommendation_portfolio_calendar_evidence_v1 import (
    PortfolioPeriodCalendarEvidenceV1Error,
    _canonical_bytes as _v1_canonical_bytes,
    _parse_captured_at as _v1_parse_captured_at,
    _parse_date as _v1_parse_date,
    _parse_json as _v1_parse_json,
)
from data_module.official_calendar_bundle import (
    OfficialCalendarBundleError,
    derive_annual_calendar_sessions_v1,
)
from data_module.official_calendar_transport_v1 import (
    OfficialCalendarJsonTransportV1,
    OfficialCalendarTransportError,
)
from data_module.tpex_annual_calendar_transport_v1 import (
    OfficialCalendarTpexAnnualJsonTransportV1,
)


PORTFOLIO_PERIOD_ANNUAL_CALENDAR_EVIDENCE_SCHEMA_V1 = (
    "recommendation-portfolio-period-annual-calendar-evidence.v1"
)
_MAX_EVIDENCE_BYTES = 32 * 1024**2
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_FIELDS = frozenset({
    "schema_version", "start_date", "end_date", "captured_at", "twse_transports",
    "tpex_transports", "expected_session_dates", "candidate_only",
    "historical_pit_eligible", "performance_eligible", "formal_clock_eligible",
    "evidence_sha256",
})


class PortfolioPeriodAnnualCalendarEvidenceV1Error(ValueError):
    """年度行事曆期間證據或其 canonical 原件不符合契約。"""


def _fail(reason: str) -> NoReturn:
    raise PortfolioPeriodAnnualCalendarEvidenceV1Error(reason)


def _canonical(value: object) -> bytes:
    try:
        return _v1_canonical_bytes(value)
    except PortfolioPeriodCalendarEvidenceV1Error as exc:
        raise PortfolioPeriodAnnualCalendarEvidenceV1Error(
            "annual_evidence_canonical_json_invalid:" + str(exc)
        ) from exc


def _parse(raw: bytes) -> object:
    try:
        return _v1_parse_json(raw, label="annual_calendar_evidence")
    except PortfolioPeriodCalendarEvidenceV1Error as exc:
        raise PortfolioPeriodAnnualCalendarEvidenceV1Error(
            "annual_evidence_json_invalid:" + str(exc)
        ) from exc


def _date(value: object, *, label: str) -> date:
    try:
        return _v1_parse_date(value, label=label)
    except PortfolioPeriodCalendarEvidenceV1Error as exc:
        raise PortfolioPeriodAnnualCalendarEvidenceV1Error(
            "annual_evidence_date_invalid:" + str(exc)
        ) from exc


def _captured_at(value: object) -> datetime:
    try:
        return _v1_parse_captured_at(value)
    except PortfolioPeriodCalendarEvidenceV1Error as exc:
        raise PortfolioPeriodAnnualCalendarEvidenceV1Error(
            "annual_evidence_clock_invalid:" + str(exc)
        ) from exc


def _hash(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


@overload
def _roundtrip_transports(
    values: tuple[OfficialCalendarJsonTransportV1, ...], *, market: Literal["twse"],
) -> tuple[OfficialCalendarJsonTransportV1, ...]: ...


@overload
def _roundtrip_transports(
    values: tuple[OfficialCalendarTpexAnnualJsonTransportV1, ...], *, market: Literal["tpex"],
) -> tuple[OfficialCalendarTpexAnnualJsonTransportV1, ...]: ...


@overload
def _roundtrip_transports(
    values: tuple[object, ...], *, market: Literal["twse", "tpex"],
) -> tuple[
    OfficialCalendarJsonTransportV1, ...
] | tuple[OfficialCalendarTpexAnnualJsonTransportV1, ...]: ...


def _roundtrip_transports(
    values: tuple[object, ...], *, market: Literal["twse", "tpex"],
) -> tuple[
    OfficialCalendarJsonTransportV1, ...
] | tuple[OfficialCalendarTpexAnnualJsonTransportV1, ...]:
    if type(values) is not tuple or not 1 <= len(values) <= 2:
        _fail(f"annual_{market}_transport_tuple_or_count_invalid")
    if market == "twse":
        rebuilt_twse: list[OfficialCalendarJsonTransportV1] = []
        for value in values:
            if type(value) is not OfficialCalendarJsonTransportV1:
                _fail("annual_twse_transport_type_invalid")
            try:
                rebuilt_twse.append(OfficialCalendarJsonTransportV1.from_dict(value.to_dict()))
            except (OfficialCalendarTransportError, TypeError, ValueError, KeyError) as exc:
                raise PortfolioPeriodAnnualCalendarEvidenceV1Error(
                    f"annual_twse_transport_revalidation_failed:{exc}"
                ) from exc
        try:
            return tuple(sorted(rebuilt_twse, key=lambda item: int(item.key)))
        except (AttributeError, TypeError, ValueError) as exc:
            raise PortfolioPeriodAnnualCalendarEvidenceV1Error(
                "annual_twse_transport_order_invalid"
            ) from exc
    rebuilt_tpex: list[OfficialCalendarTpexAnnualJsonTransportV1] = []
    for value in values:
        if type(value) is not OfficialCalendarTpexAnnualJsonTransportV1:
            _fail("annual_tpex_transport_type_invalid")
        try:
            rebuilt_tpex.append(OfficialCalendarTpexAnnualJsonTransportV1.from_dict(value.to_dict()))
        except (OfficialCalendarTransportError, TypeError, ValueError, KeyError) as exc:
            raise PortfolioPeriodAnnualCalendarEvidenceV1Error(
                f"annual_tpex_transport_revalidation_failed:{exc}"
            ) from exc
    try:
        return tuple(sorted(rebuilt_tpex, key=lambda item: item.year))
    except (AttributeError, TypeError, ValueError) as exc:
        raise PortfolioPeriodAnnualCalendarEvidenceV1Error(
            "annual_tpex_transport_order_invalid"
        ) from exc


def _sessions(
    start: date,
    end: date,
    twse: tuple[OfficialCalendarJsonTransportV1, ...],
    tpex: tuple[OfficialCalendarTpexAnnualJsonTransportV1, ...],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    try:
        result = derive_annual_calendar_sessions_v1(
            start_date=start, end_date=end, twse_transports=twse, tpex_transports=tpex,
        )
    except (OfficialCalendarBundleError, OfficialCalendarTransportError) as exc:
        raise PortfolioPeriodAnnualCalendarEvidenceV1Error(
            "annual_calendar_derivation_rejected:" + str(exc)
        ) from exc
    if type(result) is not tuple or len(result) != 2:
        _fail("annual_calendar_derivation_result_invalid")
    normalized: list[tuple[str, ...]] = []
    for market, values in zip(("twse", "tpex"), result):
        if type(values) is not tuple or any(type(item) is not str for item in values):
            _fail(f"annual_{market}_session_dates_invalid")
        parsed = tuple(_date(item, label=f"{market}_session_date") for item in values)
        if (parsed != tuple(sorted(set(parsed)))
                or any(item < start or item > end for item in parsed)):
            _fail(f"annual_{market}_session_dates_noncanonical")
        normalized.append(values)
    return normalized[0], normalized[1]


def _body(
    *,
    start: str,
    end: str,
    captured_at: str,
    twse: tuple[OfficialCalendarJsonTransportV1, ...],
    tpex: tuple[OfficialCalendarTpexAnnualJsonTransportV1, ...],
    twse_dates: tuple[str, ...],
    tpex_dates: tuple[str, ...],
) -> dict[str, object]:
    return {
        "schema_version": PORTFOLIO_PERIOD_ANNUAL_CALENDAR_EVIDENCE_SCHEMA_V1,
        "start_date": start,
        "end_date": end,
        "captured_at": captured_at,
        "twse_transports": [item.to_dict() for item in twse],
        "tpex_transports": [item.to_dict() for item in tpex],
        "expected_session_dates": {"twse": list(twse_dates), "tpex": list(tpex_dates)},
        "candidate_only": True,
        "historical_pit_eligible": False,
        "performance_eligible": False,
        "formal_clock_eligible": False,
    }


@dataclass(frozen=True, slots=True)
class PortfolioPeriodAnnualCalendarEvidenceV1:
    """保存具名年度原件並重驗候選 session dates，不授予用途或績效資格。"""

    start_date: str
    end_date: str
    twse_transports: tuple[OfficialCalendarJsonTransportV1, ...]
    tpex_transports: tuple[OfficialCalendarTpexAnnualJsonTransportV1, ...]
    captured_at: str = field(init=False)
    evidence_sha256: str = field(init=False)
    _twse_session_dates: tuple[str, ...] = field(init=False, repr=False)
    _tpex_session_dates: tuple[str, ...] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if type(self.start_date) is not str or type(self.end_date) is not str:
            _fail("annual_evidence_start_end_must_be_canonical_strings")
        start = _date(self.start_date, label="start_date")
        end = _date(self.end_date, label="end_date")
        if self.start_date != start.isoformat() or self.end_date != end.isoformat():
            _fail("annual_evidence_start_end_must_be_canonical_strings")
        if end < start:
            _fail("annual_evidence_end_precedes_start")
        if (type(self.twse_transports) is not tuple
                or type(self.tpex_transports) is not tuple
                or len(self.twse_transports) + len(self.tpex_transports) > 4):
            _fail("annual_evidence_transports_must_be_bounded_tuples")
        twse = _roundtrip_transports(self.twse_transports, market="twse")
        tpex = _roundtrip_transports(self.tpex_transports, market="tpex")
        object.__setattr__(self, "twse_transports", twse)
        object.__setattr__(self, "tpex_transports", tpex)
        twse_dates, tpex_dates = _sessions(start, end, twse, tpex)
        completed = (tuple(item.body_completed_at for item in twse)
                     + tuple(item.body_completed_at for item in tpex))
        captured = max(completed).isoformat()
        body = _body(
            start=self.start_date, end=self.end_date, captured_at=captured,
            twse=twse, tpex=tpex, twse_dates=twse_dates, tpex_dates=tpex_dates,
        )
        digest = _hash(_canonical(body))
        object.__setattr__(self, "captured_at", captured)
        object.__setattr__(self, "_twse_session_dates", twse_dates)
        object.__setattr__(self, "_tpex_session_dates", tpex_dates)
        object.__setattr__(self, "evidence_sha256", digest)

    @classmethod
    def build(
        cls,
        *,
        start_date: date,
        end_date: date,
        twse_transports: Sequence[OfficialCalendarJsonTransportV1],
        tpex_transports: Sequence[OfficialCalendarTpexAnnualJsonTransportV1],
    ) -> PortfolioPeriodAnnualCalendarEvidenceV1:
        if (not isinstance(twse_transports, Sequence)
                or isinstance(twse_transports, (str, bytes, bytearray))
                or not isinstance(tpex_transports, Sequence)
                or isinstance(tpex_transports, (str, bytes, bytearray))):
            _fail("annual_evidence_build_requires_transport_sequences")
        if type(start_date) is not date or type(end_date) is not date:
            _fail("annual_evidence_build_requires_exact_dates")
        return cls(
            start_date=start_date.isoformat(), end_date=end_date.isoformat(),
            twse_transports=tuple(twse_transports),
            tpex_transports=tuple(tpex_transports),
        )

    @property
    def candidate_only(self) -> Literal[True]:
        return True

    @property
    def historical_pit_eligible(self) -> Literal[False]:
        return False

    @property
    def performance_eligible(self) -> Literal[False]:
        return False

    @property
    def formal_clock_eligible(self) -> Literal[False]:
        return False

    def _validated_wire(self) -> dict[str, object]:
        if type(self.start_date) is not str or type(self.end_date) is not str:
            _fail("annual_evidence_date_state_changed")
        start = _date(self.start_date, label="start_date")
        end = _date(self.end_date, label="end_date")
        if (self.start_date != start.isoformat() or self.end_date != end.isoformat()
                or end < start):
            _fail("annual_evidence_date_state_changed")
        if (type(self.twse_transports) is not tuple or type(self.tpex_transports) is not tuple
                or not 1 <= len(self.twse_transports) <= 2
                or not 1 <= len(self.tpex_transports) <= 2
                or len(self.twse_transports) + len(self.tpex_transports) > 4):
            _fail("annual_evidence_transport_state_changed")
        twse = _roundtrip_transports(self.twse_transports, market="twse")
        tpex = _roundtrip_transports(self.tpex_transports, market="tpex")
        original_twse_wire = [item.to_dict() for item in self.twse_transports]
        original_tpex_wire = [item.to_dict() for item in self.tpex_transports]
        if (_canonical(original_twse_wire) != _canonical([item.to_dict() for item in twse])
                or _canonical(original_tpex_wire) != _canonical([item.to_dict() for item in tpex])
                or tuple(item.key for item in self.twse_transports)
                != tuple(sorted((item.key for item in self.twse_transports), key=int))
                or tuple(item.year for item in self.tpex_transports)
                != tuple(sorted(item.year for item in self.tpex_transports))):
            _fail("annual_evidence_transport_state_changed")
        twse_dates, tpex_dates = _sessions(start, end, twse, tpex)
        completed = (tuple(item.body_completed_at for item in twse)
                     + tuple(item.body_completed_at for item in tpex))
        captured = max(completed).isoformat()
        body = _body(
            start=self.start_date, end=self.end_date, captured_at=captured,
            twse=twse, tpex=tpex, twse_dates=twse_dates, tpex_dates=tpex_dates,
        )
        digest = _hash(_canonical(body))
        current_captured = self.captured_at
        if (type(current_captured) is not str
                or current_captured != captured
                or self._twse_session_dates != twse_dates
                or self._tpex_session_dates != tpex_dates
                or type(self.evidence_sha256) is not str or self.evidence_sha256 != digest):
            _fail("annual_evidence_derived_state_changed")
        body["evidence_sha256"] = digest
        return body

    def expected_session_dates(self, market: Literal["twse", "tpex"]) -> tuple[str, ...]:
        self._validated_wire()
        if type(market) is not str or market not in ("twse", "tpex"):
            _fail("annual_evidence_market_invalid")
        return self._twse_session_dates if market == "twse" else self._tpex_session_dates

    def to_dict(self) -> dict[str, object]:
        return self._validated_wire()

    def to_json(self) -> str:
        raw = _canonical(self.to_dict())
        if len(raw) > _MAX_EVIDENCE_BYTES:
            _fail("annual_evidence_over_byte_limit")
        return raw.decode("utf-8", errors="strict")

    @classmethod
    def from_dict(cls, value: object) -> PortfolioPeriodAnnualCalendarEvidenceV1:
        if type(value) is not dict or set(value) != _FIELDS:
            _fail("annual_evidence_fields_invalid")
        if (type(value["schema_version"]) is not str
                or value["schema_version"] != PORTFOLIO_PERIOD_ANNUAL_CALENDAR_EVIDENCE_SCHEMA_V1):
            _fail("annual_evidence_schema_version_invalid")
        start = _date(value["start_date"], label="start_date")
        end = _date(value["end_date"], label="end_date")
        _captured_at(value["captured_at"])
        twse_values, tpex_values = value["twse_transports"], value["tpex_transports"]
        if (type(twse_values) is not list or type(tpex_values) is not list
                or not 1 <= len(twse_values) <= 2 or not 1 <= len(tpex_values) <= 2
                or len(twse_values) + len(tpex_values) > 4):
            _fail("annual_evidence_transport_arrays_invalid")
        try:
            twse = tuple(OfficialCalendarJsonTransportV1.from_dict(item) for item in twse_values)
            tpex = tuple(OfficialCalendarTpexAnnualJsonTransportV1.from_dict(item) for item in tpex_values)
        except OfficialCalendarTransportError as exc:
            raise PortfolioPeriodAnnualCalendarEvidenceV1Error(
                "annual_evidence_transport_decode_failed:" + str(exc)
            ) from exc
        dates = value["expected_session_dates"]
        if (type(dates) is not dict or set(dates) != {"twse", "tpex"}
                or type(dates["twse"]) is not list or type(dates["tpex"]) is not list
                or any(type(item) is not str for item in (*dates["twse"], *dates["tpex"]))):
            _fail("annual_evidence_expected_dates_invalid")
        for item in (*dates["twse"], *dates["tpex"]):
            _date(item, label="expected_session_date")
        for name, expected in (
            ("candidate_only", True),
            ("historical_pit_eligible", False),
            ("performance_eligible", False),
            ("formal_clock_eligible", False),
        ):
            if type(value[name]) is not bool or value[name] is not expected:
                _fail("annual_evidence_qualification_flags_invalid")
        digest = value["evidence_sha256"]
        if type(digest) is not str or _SHA256.fullmatch(digest) is None:
            _fail("annual_evidence_sha256_invalid")
        instance = cls(
            start_date=start.isoformat(), end_date=end.isoformat(),
            twse_transports=twse, tpex_transports=tpex,
        )
        if _canonical(instance.to_dict()) != _canonical(value):
            _fail("annual_evidence_roundtrip_mismatch")
        return instance

    @classmethod
    def from_json(cls, raw: str | bytes) -> PortfolioPeriodAnnualCalendarEvidenceV1:
        if type(raw) is str:
            if len(raw) > _MAX_EVIDENCE_BYTES:
                _fail("annual_evidence_size_invalid")
            try:
                encoded = raw.encode("utf-8", errors="strict")
            except UnicodeError as exc:
                raise PortfolioPeriodAnnualCalendarEvidenceV1Error(
                    "annual_evidence_invalid_utf8"
                ) from exc
        elif type(raw) is bytes:
            encoded = raw
        else:
            _fail("annual_evidence_json_type_invalid")
        if not encoded or len(encoded) > _MAX_EVIDENCE_BYTES:
            _fail("annual_evidence_size_invalid")
        value = _parse(encoded)
        if _canonical(value) != encoded:
            _fail("annual_evidence_json_not_canonical")
        return cls.from_dict(value)
