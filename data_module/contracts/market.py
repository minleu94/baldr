"""Immutable, I/O-free market source facts shared across module boundaries.

These records carry source facts and custody only. They deliberately do not
interpret factor eligibility, choose a current source, or perform I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone, tzinfo
from decimal import Decimal
from enum import Enum
from typing import TypeAlias, cast
from zoneinfo import ZoneInfo


MarketFactValue: TypeAlias = Decimal | int | bool | str | None
SourceRevision: TypeAlias = str | int


def _require_nonblank(value: str, field_name: str) -> None:
    if type(value) is not str:
        raise TypeError(f"{field_name} must be a string")
    if not value.strip():
        raise ValueError(f"{field_name} must not be blank")


def _require_date(value: date, field_name: str) -> None:
    # datetime subclasses date, but this contract keeps the two concepts apart.
    if type(value) is not date:
        raise TypeError(f"{field_name} must be a date, not a datetime")


def _freeze_aware_datetime(value: datetime | None, field_name: str) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    stored_tzinfo = cast(
        tzinfo | None, getattr(datetime, "tzinfo").__get__(value, datetime)
    )
    if stored_tzinfo is None:
        raise ValueError(f"{field_name} must include a timezone")
    offset = value.utcoffset()
    if offset is None:
        raise ValueError(f"{field_name} must include a timezone")
    if not isinstance(offset, timedelta):
        raise TypeError(f"{field_name} timezone offset must be a timedelta")

    # 標準時區的 tzname 也必須是不可變的 builtin str，避免 timezone
    # 留住呼叫者傳入的 str subclass 及其可變 payload。
    frozen_timezone_name: str | None = None
    if type(stored_tzinfo) in (timezone, ZoneInfo):
        timezone_name = stored_tzinfo.tzname(value)
        if (
            type(value) is datetime
            and type(offset) is timedelta
            and type(timezone_name) is str
        ):
            return value
        if not isinstance(timezone_name, str):
            raise TypeError(f"{field_name} timezone name must be a string")
        frozen_timezone_name = str.__str__(timezone_name)
        if type(frozen_timezone_name) is not str:
            raise TypeError(f"{field_name} timezone name cannot be snapshotted")

    # 使用 datetime 本體的欄位描述器，避免 subclass 屬性覆寫污染時鐘快照。
    def component(name: str) -> int:
        descriptor = getattr(datetime, name)
        return cast(int, descriptor.__get__(value, datetime))

    if type(offset) is timedelta:
        frozen_offset = offset
    else:
        frozen_offset = timedelta(
            days=cast(int, getattr(timedelta, "days").__get__(offset, timedelta)),
            seconds=cast(
                int, getattr(timedelta, "seconds").__get__(offset, timedelta)
            ),
            microseconds=cast(
                int,
                getattr(timedelta, "microseconds").__get__(offset, timedelta),
            ),
        )

    frozen_timezone = (
        timezone(frozen_offset)
        if frozen_timezone_name is None
        else timezone(frozen_offset, frozen_timezone_name)
    )
    return datetime(
        component("year"),
        component("month"),
        component("day"),
        component("hour"),
        component("minute"),
        component("second"),
        component("microsecond"),
        tzinfo=frozen_timezone,
        fold=component("fold"),
    )


@dataclass(frozen=True, slots=True)
class MeasureUnit:
    """The source-declared unit for one market fact; no conversion is implied."""

    code: str

    def __post_init__(self) -> None:
        _require_nonblank(self.code, "code")


@dataclass(frozen=True, slots=True)
class SourceRef:
    """A stable source and revision reference, optionally tied to a snapshot."""

    source_id: str
    revision: SourceRevision
    snapshot_id: str | None = None

    def __post_init__(self) -> None:
        _require_nonblank(self.source_id, "source_id")
        if type(self.revision) not in (str, int):
            raise TypeError("revision must be a string or integer")
        if isinstance(self.revision, str) and not self.revision.strip():
            raise ValueError("revision must not be blank")
        if self.snapshot_id is not None:
            _require_nonblank(self.snapshot_id, "snapshot_id")


class AvailabilityStatus(str, Enum):
    KNOWN = "known"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class Availability:
    """Source availability claims, retaining date-only precision when supplied."""

    status: AvailabilityStatus
    available_date: date | None = None
    available_at: datetime | None = None

    def __post_init__(self) -> None:
        if type(self.status) is not AvailabilityStatus:
            raise TypeError("status must be an AvailabilityStatus")
        if self.available_date is not None:
            _require_date(self.available_date, "available_date")
        available_at = _freeze_aware_datetime(self.available_at, "available_at")
        object.__setattr__(self, "available_at", available_at)

        has_availability_value = (
            self.available_date is not None or self.available_at is not None
        )
        if self.status is AvailabilityStatus.KNOWN and not has_availability_value:
            raise ValueError("known availability requires a date or timestamp")
        if self.status is AvailabilityStatus.UNKNOWN and has_availability_value:
            raise ValueError("unknown availability cannot carry a date or timestamp")


@dataclass(frozen=True, slots=True)
class SourceObservation:
    """One standardized source fact with its original date, unit and custody."""

    subject_id: str
    fact_id: str
    observation_date: date
    value: MarketFactValue
    unit: MeasureUnit
    availability: Availability
    source_ref: SourceRef

    def __post_init__(self) -> None:
        _require_nonblank(self.subject_id, "subject_id")
        _require_nonblank(self.fact_id, "fact_id")
        _require_date(self.observation_date, "observation_date")
        if self.value is not None and type(self.value) not in (Decimal, int, bool, str):
            raise TypeError("value must be Decimal, int, bool, str, or None")
        if isinstance(self.value, Decimal) and not self.value.is_finite():
            raise ValueError("Decimal market facts must be finite")
        if type(self.unit) is not MeasureUnit:
            raise TypeError("unit must be a MeasureUnit")
        if type(self.availability) is not Availability:
            raise TypeError("availability must be an Availability")
        if type(self.source_ref) is not SourceRef:
            raise TypeError("source_ref must be a SourceRef")

    @property
    def identity(self) -> tuple[str, str, date, SourceRef]:
        """Identity used to reject duplicate facts within one MarketSlice."""

        return (
            self.subject_id,
            self.fact_id,
            self.observation_date,
            self.source_ref,
        )


@dataclass(frozen=True, slots=True)
class MarketSlice:
    """A bounded immutable set of source facts for one as-of date and cutoff."""

    as_of_date: date
    observations: tuple[SourceObservation, ...] = ()
    source_refs: tuple[SourceRef, ...] = ()
    cutoff_at: datetime | None = None

    def __post_init__(self) -> None:
        _require_date(self.as_of_date, "as_of_date")
        cutoff_at = _freeze_aware_datetime(self.cutoff_at, "cutoff_at")
        object.__setattr__(self, "cutoff_at", cutoff_at)

        observations = tuple(self.observations)
        source_refs = tuple(self.source_refs)
        if any(type(item) is not SourceObservation for item in observations):
            raise TypeError("observations must contain only SourceObservation values")
        if any(type(item) is not SourceRef for item in source_refs):
            raise TypeError("source_refs must contain only SourceRef values")

        identities = tuple(item.identity for item in observations)
        if len(set(identities)) != len(identities):
            raise ValueError("MarketSlice contains duplicate observation identity")
        if len(set(source_refs)) != len(source_refs):
            raise ValueError("MarketSlice contains duplicate source references")

        declared_refs = set(source_refs)
        missing_refs = {
            item.source_ref for item in observations if item.source_ref not in declared_refs
        }
        if missing_refs:
            raise ValueError("source_refs must include every observation source_ref")
        if any(item.observation_date > self.as_of_date for item in observations):
            raise ValueError("MarketSlice cannot contain observations after as_of_date")

        # Copy any caller-owned iterable into tuples before sealing the record.
        object.__setattr__(self, "observations", observations)
        object.__setattr__(self, "source_refs", source_refs)


__all__ = (
    "Availability",
    "AvailabilityStatus",
    "MarketFactValue",
    "MarketSlice",
    "MeasureUnit",
    "SourceObservation",
    "SourceRef",
    "SourceRevision",
)
