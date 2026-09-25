from __future__ import annotations

import subprocess
import sys
from dataclasses import FrozenInstanceError
from datetime import date, datetime, timedelta, timezone, tzinfo
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from data_module.contracts import (
    Availability,
    AvailabilityStatus,
    MarketSlice,
    MeasureUnit,
    SourceObservation,
    SourceRef,
)


def _observation(
    *,
    value: Decimal | int | bool | str | None = Decimal("12.50"),
    source_ref: SourceRef | None = None,
    available: Availability | None = None,
    observation_date: date = date(2026, 9, 21),
    unit: MeasureUnit | None = None,
) -> SourceObservation:
    return SourceObservation(
        subject_id="2330",
        fact_id="close_price",
        observation_date=observation_date,
        value=value,
        unit=unit or MeasureUnit("TWD/share"),
        availability=available
        or Availability(
            AvailabilityStatus.KNOWN,
            available_date=date(2026, 9, 21),
        ),
        source_ref=source_ref or SourceRef("twse.daily", "rev-7", "snapshot-20260921"),
    )


class MutableHoursTZ(tzinfo):
    def __init__(self, hours: int) -> None:
        self.hours = hours

    def utcoffset(self, dt: datetime | None) -> timedelta:
        return timedelta(hours=self.hours)

    def dst(self, dt: datetime | None) -> timedelta:
        return timedelta(0)

    def tzname(self, dt: datetime | None) -> str:
        return f"MutableUTC{self.hours:+03d}"


class MutablePayloadTimedelta(timedelta):
    pass


class MutableOffsetDatetime(datetime):
    __slots__ = ("shift", "last_offset")

    @property
    def year(self) -> int:
        return 1999

    @property
    def fold(self) -> int:
        return 0

    def utcoffset(self) -> timedelta:
        offset = MutablePayloadTimedelta(hours=self.shift)
        offset.payload = []
        self.last_offset = offset
        return offset


class MutablePayloadMeasureUnit(MeasureUnit):
    __slots__ = ("payload",)


class MutablePayloadAvailability(Availability):
    __slots__ = ("payload",)


class MutablePayloadSourceRef(SourceRef):
    __slots__ = ("payload",)


class MutablePayloadSourceObservation(SourceObservation):
    __slots__ = ("payload",)


class MutablePayloadString(str):
    pass


class SpoofedAvailabilityStatus:
    payload: list[str]

    @property
    def __class__(self) -> type[AvailabilityStatus]:
        return AvailabilityStatus


def test_records_are_frozen_and_market_slice_copies_input_collections() -> None:
    observation = _observation()
    ref = observation.source_ref
    refs = [ref]
    observations = [observation]
    market_slice = MarketSlice(
        as_of_date=date(2026, 9, 21),
        observations=observations,  # type: ignore[arg-type]
        source_refs=refs,  # type: ignore[arg-type]
        cutoff_at=datetime(2026, 9, 22, 1, 0, tzinfo=timezone.utc),
    )

    observations.clear()
    refs.clear()
    assert market_slice.observations == (observation,)
    assert market_slice.source_refs == (ref,)
    with pytest.raises(FrozenInstanceError):
        observation.value = Decimal("1")  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        market_slice.as_of_date = date(2026, 9, 20)  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        ref.revision = "rev-8"  # type: ignore[misc]


def test_dates_timestamps_and_date_only_availability_keep_their_precision() -> None:
    date_only = Availability(
        AvailabilityStatus.KNOWN,
        available_date=date(2026, 9, 21),
    )
    assert date_only.available_date == date(2026, 9, 21)
    assert date_only.available_at is None

    timestamp = datetime(2026, 9, 21, 9, 30, tzinfo=timezone.utc)
    precise = Availability(AvailabilityStatus.KNOWN, available_at=timestamp)
    assert precise.available_at is timestamp
    assert MarketSlice(as_of_date=date(2026, 9, 21), cutoff_at=timestamp).cutoff_at is timestamp

    with pytest.raises(ValueError, match="timezone"):
        Availability(
            AvailabilityStatus.KNOWN,
            available_at=datetime(2026, 9, 21, 9, 30),
        )
    with pytest.raises(TypeError, match="date, not a datetime"):
        MarketSlice(as_of_date=datetime(2026, 9, 21, tzinfo=timezone.utc))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="timezone"):
        MarketSlice(
            as_of_date=date(2026, 9, 21),
            cutoff_at=datetime(2026, 9, 21, 9, 30),
        )


def test_mutable_tzinfo_is_snapshotted_in_direct_and_nested_market_records() -> None:
    source_timezone = MutableHoursTZ(2)
    available_at = datetime(
        2026, 9, 21, 14, 30, 5, 654321, tzinfo=source_timezone, fold=1
    )
    cutoff_at = datetime(
        2026, 9, 21, 14, 31, 6, 123456, tzinfo=source_timezone, fold=1
    )
    expected_available = (
        available_at.utcoffset(),
        available_at.isoformat(),
        available_at.timestamp(),
        (available_at.year, available_at.month, available_at.day,
         available_at.hour, available_at.minute, available_at.second,
         available_at.microsecond),
        available_at.fold,
    )
    expected_cutoff = (
        cutoff_at.utcoffset(),
        cutoff_at.isoformat(),
        cutoff_at.timestamp(),
        (cutoff_at.year, cutoff_at.month, cutoff_at.day,
         cutoff_at.hour, cutoff_at.minute, cutoff_at.second,
         cutoff_at.microsecond),
        cutoff_at.fold,
    )
    availability = Availability(AvailabilityStatus.KNOWN, available_at=available_at)
    observation = _observation(available=availability)
    market_slice = MarketSlice(
        as_of_date=date(2026, 9, 21),
        observations=(observation,),
        source_refs=(observation.source_ref,),
        cutoff_at=cutoff_at,
    )

    assert availability.available_at is not available_at
    assert availability.available_at is not None
    assert availability.available_at.tzinfo is not source_timezone
    assert market_slice.cutoff_at is not cutoff_at
    assert market_slice.cutoff_at is not None
    assert market_slice.cutoff_at.tzinfo is not source_timezone

    source_timezone.hours = 9

    sealed_available_at = market_slice.observations[0].availability.available_at
    sealed_cutoff_at = market_slice.cutoff_at
    assert sealed_available_at is not None
    assert sealed_cutoff_at is not None
    assert (
        sealed_available_at.utcoffset(),
        sealed_available_at.isoformat(),
        sealed_available_at.timestamp(),
        (sealed_available_at.year, sealed_available_at.month,
         sealed_available_at.day, sealed_available_at.hour,
         sealed_available_at.minute, sealed_available_at.second,
         sealed_available_at.microsecond),
        sealed_available_at.fold,
    ) == expected_available
    assert (
        sealed_cutoff_at.utcoffset(),
        sealed_cutoff_at.isoformat(),
        sealed_cutoff_at.timestamp(),
        (sealed_cutoff_at.year, sealed_cutoff_at.month,
         sealed_cutoff_at.day, sealed_cutoff_at.hour,
         sealed_cutoff_at.minute, sealed_cutoff_at.second,
         sealed_cutoff_at.microsecond),
        sealed_cutoff_at.fold,
    ) == expected_cutoff


def test_immutable_zoneinfo_datetime_keeps_its_timezone_and_dst_semantics() -> None:
    source_timezone = ZoneInfo("America/New_York")
    timestamp = datetime(
        2026, 11, 1, 1, 30, 0, 987654, tzinfo=source_timezone, fold=1
    )
    expected = (
        timestamp.utcoffset(),
        timestamp.isoformat(),
        timestamp.timestamp(),
        timestamp.tzname(),
        timestamp.fold,
    )

    availability = Availability(AvailabilityStatus.KNOWN, available_at=timestamp)

    assert availability.available_at is timestamp
    assert availability.available_at is not None
    assert availability.available_at.tzinfo is source_timezone
    assert (
        availability.available_at.utcoffset(),
        availability.available_at.isoformat(),
        availability.available_at.timestamp(),
        availability.available_at.tzname(),
        availability.available_at.fold,
    ) == expected


def test_datetime_subclass_is_copied_to_builtin_using_sealed_offset_and_fields() -> None:
    source = MutableOffsetDatetime(
        2026, 9, 22, 12, 34, 56, 789012, tzinfo=timezone.utc, fold=1
    )
    source.shift = 0
    expected = (
        source.utcoffset(),
        datetime.isoformat(source),
        datetime.timestamp(source),
        (
            datetime.year.__get__(source, datetime),
            datetime.month.__get__(source, datetime),
            datetime.day.__get__(source, datetime),
            datetime.hour.__get__(source, datetime),
            datetime.minute.__get__(source, datetime),
            datetime.second.__get__(source, datetime),
            datetime.microsecond.__get__(source, datetime),
        ),
        datetime.fold.__get__(source, datetime),
    )

    availability = Availability(AvailabilityStatus.KNOWN, available_at=source)
    sealed = availability.available_at

    assert sealed is not None
    assert type(sealed) is datetime
    assert sealed is not source
    assert type(sealed.utcoffset()) is timedelta
    assert sealed.year == 2026
    assert sealed.fold == 1

    source.last_offset.payload.append("external mutation")
    source.shift = 9

    assert source.utcoffset() == timedelta(hours=9)
    assert (
        sealed.utcoffset(),
        sealed.isoformat(),
        sealed.timestamp(),
        (
            sealed.year,
            sealed.month,
            sealed.day,
            sealed.hour,
            sealed.minute,
            sealed.second,
            sealed.microsecond,
        ),
        sealed.fold,
    ) == expected


def test_trusted_timezone_with_mutable_timedelta_offset_is_snapshotted() -> None:
    source_offset = MutablePayloadTimedelta(hours=2)
    source_offset.payload = []
    source_timezone = timezone(source_offset)
    timestamp = datetime(
        2026, 9, 22, 12, 34, 56, 789012, tzinfo=source_timezone, fold=1
    )
    expected = (
        timestamp.utcoffset(),
        timestamp.isoformat(),
        timestamp.timestamp(),
        timestamp.fold,
    )

    availability = Availability(AvailabilityStatus.KNOWN, available_at=timestamp)
    sealed = availability.available_at

    assert sealed is not None
    assert type(sealed) is datetime
    assert sealed is not timestamp
    assert sealed.tzinfo is not source_timezone
    assert type(sealed.utcoffset()) is timedelta

    source_offset.payload.append("external mutation")

    assert (
        sealed.utcoffset(),
        sealed.isoformat(),
        sealed.timestamp(),
        sealed.fold,
    ) == expected


def test_timezone_name_subclass_is_snapshotted_across_market_contracts() -> None:
    source_name = MutablePayloadString("caller-owned-zone")
    source_name.payload = []
    source_timezone = timezone(timedelta(hours=5), source_name)
    source_timestamp = datetime(
        2026, 9, 22, 12, 34, 56, 789012, tzinfo=source_timezone, fold=1
    )
    expected = (
        source_timestamp.utcoffset(),
        source_timestamp.isoformat(),
        source_timestamp.timestamp(),
        source_timestamp.fold,
    )
    assert source_timestamp.tzname() is source_name

    availability = Availability(
        AvailabilityStatus.KNOWN,
        available_at=source_timestamp,
    )
    observation = _observation(available=availability)
    market_slice = MarketSlice(
        as_of_date=date(2026, 9, 22),
        observations=(observation,),
        source_refs=(observation.source_ref,),
        cutoff_at=source_timestamp,
    )

    sealed_values = (
        availability.available_at,
        market_slice.observations[0].availability.available_at,
        market_slice.cutoff_at,
    )
    for sealed in sealed_values:
        assert sealed is not None
        assert sealed is not source_timestamp
        assert sealed.tzinfo is not source_timezone
        assert type(sealed.tzname()) is str
        assert sealed.tzname() == "caller-owned-zone"
        assert sealed.tzname() is not source_name
        assert (
            sealed.utcoffset(),
            sealed.isoformat(),
            sealed.timestamp(),
            sealed.fold,
        ) == expected

    source_name.payload.append("external mutation")

    for sealed in sealed_values:
        assert sealed is not None
        assert sealed.tzname() == "caller-owned-zone"
        assert (
            sealed.utcoffset(),
            sealed.isoformat(),
            sealed.timestamp(),
            sealed.fold,
        ) == expected


def test_nested_contracts_reject_subclasses_with_mutable_payload_slots() -> None:
    observation = _observation()

    mutable_unit = MutablePayloadMeasureUnit("TWD/share")
    object.__setattr__(mutable_unit, "payload", [])
    mutable_unit.payload.append("mutable")
    with pytest.raises(TypeError, match="unit must be a MeasureUnit"):
        _observation(unit=mutable_unit)

    mutable_availability = MutablePayloadAvailability(AvailabilityStatus.UNKNOWN)
    object.__setattr__(mutable_availability, "payload", [])
    mutable_availability.payload.append("mutable")
    with pytest.raises(TypeError, match="availability must be an Availability"):
        _observation(available=mutable_availability)

    mutable_source_ref = MutablePayloadSourceRef("twse.daily", "rev-7")
    object.__setattr__(mutable_source_ref, "payload", [])
    mutable_source_ref.payload.append("mutable")
    with pytest.raises(TypeError, match="source_ref must be a SourceRef"):
        _observation(source_ref=mutable_source_ref)
    with pytest.raises(TypeError, match="source_refs must contain only SourceRef"):
        MarketSlice(
            as_of_date=date(2026, 9, 21),
            source_refs=(mutable_source_ref,),
        )

    mutable_observation = MutablePayloadSourceObservation(
        observation.subject_id,
        observation.fact_id,
        observation.observation_date,
        observation.value,
        observation.unit,
        observation.availability,
        observation.source_ref,
    )
    object.__setattr__(mutable_observation, "payload", [])
    mutable_observation.payload.append("mutable")
    with pytest.raises(TypeError, match="observations must contain only SourceObservation"):
        MarketSlice(
            as_of_date=date(2026, 9, 21),
            observations=(mutable_observation,),
            source_refs=(observation.source_ref,),
        )


def test_nonblank_fields_reject_mutable_string_subclasses_before_sealing() -> None:
    observation = _observation()
    mutable_text = MutablePayloadString("2330")
    mutable_text.payload = []
    mutable_text.payload.append("external mutation")

    with pytest.raises(TypeError, match="code must be a string"):
        MeasureUnit(mutable_text)
    with pytest.raises(TypeError, match="source_id must be a string"):
        SourceRef(mutable_text, "rev-7")
    with pytest.raises(TypeError, match="snapshot_id must be a string"):
        SourceRef("twse.daily", "rev-7", mutable_text)
    with pytest.raises(TypeError, match="subject_id must be a string"):
        SourceObservation(
            mutable_text,
            observation.fact_id,
            observation.observation_date,
            observation.value,
            observation.unit,
            observation.availability,
            observation.source_ref,
        )
    with pytest.raises(TypeError, match="fact_id must be a string"):
        SourceObservation(
            observation.subject_id,
            mutable_text,
            observation.observation_date,
            observation.value,
            observation.unit,
            observation.availability,
            observation.source_ref,
        )


def test_availability_rejects_a_status_object_that_spoofs_its_class() -> None:
    fake_status = SpoofedAvailabilityStatus()
    fake_status.payload = ["caller-owned"]
    assert isinstance(fake_status, AvailabilityStatus)
    assert type(fake_status) is not AvailabilityStatus

    with pytest.raises(TypeError, match="status must be an AvailabilityStatus"):
        Availability(fake_status)  # type: ignore[arg-type]


def test_unit_source_revision_and_unknown_none_zero_are_preserved() -> None:
    ref = SourceRef("exchange-x", 4, "snapshot-x-4")
    assert ref.source_id == "exchange-x"
    assert ref.revision == 4
    assert ref.snapshot_id == "snapshot-x-4"

    unit = MeasureUnit("shares")
    unknown_availability = Availability(AvailabilityStatus.UNKNOWN)
    missing_slice = MarketSlice(as_of_date=date(2026, 9, 21), source_refs=(ref,))
    unknown_value_observation = _observation(
        value=None,
        source_ref=ref,
        available=Availability(
            AvailabilityStatus.KNOWN,
            available_date=date(2026, 9, 21),
        ),
        unit=unit,
    )
    unknown_availability_observation = _observation(
        value=Decimal("12"),
        source_ref=ref,
        available=unknown_availability,
        unit=unit,
    )
    zero_observation = _observation(
        value=Decimal("0"),
        source_ref=ref,
        available=unknown_availability,
        unit=unit,
    )
    unknown_value_slice = MarketSlice(
        as_of_date=date(2026, 9, 21),
        observations=(unknown_value_observation,),
        source_refs=(ref,),
    )
    unknown_availability_slice = MarketSlice(
        as_of_date=date(2026, 9, 21),
        observations=(unknown_availability_observation,),
        source_refs=(ref,),
    )
    zero_slice = MarketSlice(
        as_of_date=date(2026, 9, 21),
        observations=(zero_observation,),
        source_refs=(ref,),
    )

    assert unit.code == "shares"
    assert unknown_value_slice.observations[0].unit == unit
    assert missing_slice.observations == ()  # Missing row.
    assert unknown_value_slice.observations[0].value is None  # Present row, missing/unknown value.
    assert (
        unknown_availability_slice.observations[0].availability.status
        is AvailabilityStatus.UNKNOWN
    )
    assert zero_slice.observations[0].value == Decimal("0")  # Present numeric zero.


def test_market_slice_rejects_duplicate_identity_even_if_values_differ() -> None:
    first = _observation(value=Decimal("12.50"))
    conflicting = _observation(value=Decimal("12.51"))
    with pytest.raises(ValueError, match="duplicate observation identity"):
        MarketSlice(
            as_of_date=date(2026, 9, 21),
            observations=(first, conflicting),
            source_refs=(first.source_ref,),
        )


def test_market_fact_value_rejects_untyped_payloads_and_non_decimal_float() -> None:
    with pytest.raises(TypeError, match="Decimal, int, bool, str, or None"):
        _observation(value=12.5)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="Decimal, int, bool, str, or None"):
        _observation(value=object())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="must be finite"):
        _observation(value=Decimal("NaN"))


def test_contract_import_is_io_free_and_does_not_load_app_or_domain_modules() -> None:
    script = r'''
import sys

def audit(event, args):
    if event == "sqlite3.connect":
        raise AssertionError("contract import attempted a SQLite connection")
    if event == "open" and args:
        path = str(args[0]).lower()
        # Python must read module code to import it; all other file opens are forbidden.
        if not path.endswith((".py", ".pyc", ".pyd", ".dll")):
            raise AssertionError(f"contract import opened a non-code file: {path}")

sys.addaudithook(audit)
from data_module.contracts import market
import data_module

for module_name in (
    "data_module.data_loader",
    "data_module.data_processor",
    "app_module",
    "analysis_module",
    "backtest_module",
    "decision_module",
    "ml_module",
    "portfolio_module",
    "ui_qt",
    "yfinance",
):
    assert module_name not in sys.modules, module_name
assert not any(name.startswith((
    "app_module.", "analysis_module.", "backtest_module.",
    "decision_module.", "ml_module.", "portfolio_module.", "ui_qt."
)) for name in sys.modules)
assert "data_module.data_loader" not in sys.modules
assert "data_module.data_processor" not in sys.modules
assert "yfinance" not in sys.modules
assert market.MarketSlice
'''
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path.cwd(),
        capture_output=True,
        check=False,
        text=True,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_legacy_top_level_exports_resolve_to_the_original_classes() -> None:
    import data_module
    from data_module import DataLoader, MarketDateRange, TWMarketDataProcessor, TWStockConfig
    from data_module.config import TWStockConfig as ConfigTWStockConfig
    from data_module.data_loader import DataLoader as LoaderDataLoader
    from data_module.data_loader import MarketDateRange as LoaderMarketDateRange
    from data_module.data_processor import TWMarketDataProcessor as Processor

    assert data_module.__all__ == [
        "TWStockConfig",
        "MarketDateRange",
        "TWMarketDataProcessor",
        "DataLoader",
    ]
    assert TWStockConfig is ConfigTWStockConfig
    assert MarketDateRange is LoaderMarketDateRange
    assert DataLoader is LoaderDataLoader
    assert TWMarketDataProcessor is Processor

    star_imports: dict[str, object] = {}
    exec("from data_module import *", star_imports)
    assert star_imports["TWStockConfig"] is ConfigTWStockConfig
    assert star_imports["MarketDateRange"] is LoaderMarketDateRange
    assert star_imports["TWMarketDataProcessor"] is Processor
    assert star_imports["DataLoader"] is LoaderDataLoader


def test_from_data_module_import_of_an_ordinary_submodule_still_works() -> None:
    script = r'''
import sys
from data_module import config

assert config.__name__ == "data_module.config"
assert "data_module.data_loader" not in sys.modules
'''
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path.cwd(),
        capture_output=True,
        check=False,
        text=True,
    )
    assert result.returncode == 0, result.stderr or result.stdout
