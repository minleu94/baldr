from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta, timezone, tzinfo
from decimal import Decimal
from enum import Enum
from typing import cast
from zoneinfo import ZoneInfo

import pytest

from data_module.contracts.market import AvailabilityStatus
from decision_module.recommendation.contracts import (
    FilterOutcome,
    LiquidityAssessment,
    NegativeEvidence,
    RecommendationItem,
)


class MutableHoursTimezone(tzinfo):
    def __init__(self, hours: int) -> None:
        self.hours = hours

    def utcoffset(self, dt: datetime | None) -> timedelta:
        return timedelta(hours=self.hours)

    def dst(self, dt: datetime | None) -> timedelta:
        return timedelta(0)

    def tzname(self, dt: datetime | None) -> str:
        return f"mutable-{self.hours}"


class MutableDelta(timedelta):
    reported_seconds: int

    def __new__(cls, hours: int, reported_seconds: int) -> MutableDelta:
        value = super().__new__(cls, hours=hours)
        value.reported_seconds = reported_seconds
        return value

    @property
    def seconds(self) -> int:
        return self.reported_seconds


class MutableDeltaTimezone(tzinfo):
    def __init__(self, offset: MutableDelta) -> None:
        self.offset = offset

    def utcoffset(self, dt: datetime | None) -> timedelta:
        return self.offset

    def dst(self, dt: datetime | None) -> timedelta:
        return timedelta(0)

    def tzname(self, dt: datetime | None) -> str:
        return "mutable-delta"


class MutableLabelString(str):
    label: str

    def __new__(cls, value: str, label: str) -> MutableLabelString:
        name = super().__new__(cls, value)
        name.label = label
        return name

    def __repr__(self) -> str:
        return f"MutableLabelString({super().__repr__()}, label={self.label!r})"


@pytest.mark.parametrize(
    ("score_percentile_bp", "eligible_universe_size"),
    (
        (0, 0),
        (10_000, 0),
        (None, None),
        (5_000, None),
        (None, 1),
    ),
)
def test_accepts_percentile_and_universe_domain_boundaries(
    score_percentile_bp: int | None,
    eligible_universe_size: int | None,
) -> None:
    item = RecommendationItem(
        "2330",
        score_percentile_bp=score_percentile_bp,
        eligible_universe_size=eligible_universe_size,
    )

    assert item.score_percentile_bp == score_percentile_bp
    assert item.eligible_universe_size == eligible_universe_size


@pytest.mark.parametrize("score_percentile_bp", (-1, 10_001))
def test_rejects_percentile_outside_basis_point_range(score_percentile_bp: int) -> None:
    with pytest.raises(ValueError, match="score_percentile_bp"):
        RecommendationItem("2330", score_percentile_bp=score_percentile_bp)


def test_rejects_negative_eligible_universe_size() -> None:
    with pytest.raises(ValueError, match="eligible_universe_size"):
        RecommendationItem("2330", eligible_universe_size=-1)


@pytest.mark.parametrize("invalid_value", (True, 1.5, Decimal("1"), "1"))
def test_percentile_requires_exact_int_or_none(invalid_value: object) -> None:
    with pytest.raises(TypeError, match="score_percentile_bp"):
        RecommendationItem(
            "2330",
            score_percentile_bp=cast(int | None, invalid_value),
        )


@pytest.mark.parametrize("invalid_value", (False, 1.5, Decimal("1"), "1"))
def test_universe_size_requires_exact_int_or_none(invalid_value: object) -> None:
    with pytest.raises(TypeError, match="eligible_universe_size"):
        RecommendationItem(
            "2330",
            eligible_universe_size=cast(int | None, invalid_value),
        )


def test_percentile_validation_preserves_original_score_precision() -> None:
    score = Decimal("1.230000000000000000")

    item = RecommendationItem(
        "2330",
        rule_score=score,
        score_percentile_bp=9_999,
        eligible_universe_size=3,
    )

    assert item.rule_score is score
    assert isinstance(item.rule_score, Decimal)
    assert item.rule_score.as_tuple() == score.as_tuple()


def test_explicitly_allowed_market_enum_remains_supported_in_evidence() -> None:
    outcome = FilterOutcome(
        "availability",
        None,
        evidence={"status": AvailabilityStatus.UNKNOWN},
    )

    assert outcome.evidence is not None
    assert outcome.evidence["status"] is AvailabilityStatus.UNKNOWN


def test_rejects_mutable_enum_payload_alias_in_filter_evidence() -> None:
    class MutablePayloadEnum(Enum):
        VALUE = "value"

        def __init__(self, _: str) -> None:
            self.payload: list[str] = []

    member = MutablePayloadEnum.VALUE
    payload_alias = member.payload

    with pytest.raises(TypeError, match="明示允許的 enum"):
        FilterOutcome("enum-evidence", True, evidence={"nested": [member]})

    payload_alias.append("後續修改")
    assert member.payload == ["後續修改"]


def test_aware_datetime_freeze_snapshots_mutable_timezone_in_direct_and_nested_values() -> None:
    mutable_timezone = MutableHoursTimezone(hours=0)
    source = datetime(
        2026,
        9,
        22,
        12,
        34,
        56,
        789012,
        tzinfo=mutable_timezone,
        fold=1,
    )
    expected_iso = source.isoformat()
    expected_timestamp = source.timestamp()
    expected_offset = source.utcoffset()

    negative_evidence = NegativeEvidence(
        "negative",
        "not available",
        observed_at=source,
        details={"nested": [source]},
    )
    liquidity = LiquidityAssessment(
        acceptable=None,
        observations={"nested": {"clock": [source]}},
    )
    outcome = FilterOutcome(
        "availability",
        None,
        evidence={
            "clock": source,
            "negative": negative_evidence,
            "liquidity": liquidity,
        },
    )

    mutable_timezone.hours = 9

    assert negative_evidence.details is not None
    assert liquidity.observations is not None
    assert outcome.evidence is not None
    nested_negative = cast(NegativeEvidence, outcome.evidence["negative"])
    nested_liquidity = cast(LiquidityAssessment, outcome.evidence["liquidity"])
    assert nested_negative.details is not None
    assert nested_liquidity.observations is not None
    direct_negative_detail_values = cast(
        list[object], negative_evidence.details["nested"]
    )
    direct_liquidity_observations = cast(Mapping[str, object], liquidity.observations["nested"])
    nested_liquidity_observations = cast(
        Mapping[str, object], nested_liquidity.observations["nested"]
    )
    outcome_liquidity_values = cast(
        list[object], nested_liquidity_observations["clock"]
    )
    nested_outcome_negative_details = cast(
        list[object], nested_negative.details["nested"]
    )
    direct_observations_values = cast(
        list[object], direct_liquidity_observations["clock"]
    )
    frozen_values = (
        negative_evidence.observed_at,
        direct_negative_detail_values[0],
        direct_observations_values[0],
        outcome.evidence["clock"],
        nested_negative.observed_at,
        nested_outcome_negative_details[0],
        outcome_liquidity_values[0],
    )

    for frozen in frozen_values:
        assert type(frozen) is datetime
        assert frozen is not source
        assert frozen.tzinfo is not mutable_timezone
        assert frozen.utcoffset() == expected_offset
        assert frozen.fold == 1
        assert frozen.isoformat() == expected_iso
        assert frozen.timestamp() == expected_timestamp


@pytest.mark.parametrize(
    ("source_timezone", "expected_offset"),
    (
        (timezone.utc, timedelta(0)),
        (timezone(timedelta(hours=8)), timedelta(hours=8)),
    ),
)
def test_datetime_freeze_preserves_utc_and_fixed_offset_timezones(
    source_timezone: tzinfo,
    expected_offset: timedelta,
) -> None:
    source = datetime(2026, 9, 22, 12, 34, 56, 789012, tzinfo=source_timezone)
    expected_iso = source.isoformat()
    expected_timestamp = source.timestamp()

    evidence = NegativeEvidence("clock", "snapshot", observed_at=source)

    assert evidence.observed_at is not source
    assert evidence.observed_at is not None
    assert evidence.observed_at.tzinfo is source_timezone
    assert evidence.observed_at.utcoffset() == expected_offset
    assert evidence.observed_at.isoformat() == expected_iso
    assert evidence.observed_at.timestamp() == expected_timestamp


def test_datetime_freeze_preserves_immutable_zoneinfo_and_daylight_saving_semantics() -> None:
    source_timezone = ZoneInfo("America/New_York")
    source = datetime(
        2026,
        11,
        1,
        1,
        30,
        tzinfo=source_timezone,
        fold=1,
    )
    expected = (source.isoformat(), source.timestamp(), source.tzname())

    evidence = NegativeEvidence("clock", "snapshot", observed_at=source)

    assert evidence.observed_at is not source
    assert evidence.observed_at is not None
    assert evidence.observed_at.tzinfo is source_timezone
    assert evidence.observed_at.fold == 1
    assert (
        evidence.observed_at.isoformat(),
        evidence.observed_at.timestamp(),
        evidence.observed_at.tzname(),
    ) == expected


def test_datetime_freeze_copies_mutable_timedelta_subclass_from_custom_timezone() -> None:
    mutable_offset = MutableDelta(hours=1, reported_seconds=2 * 60 * 60)
    source = datetime(
        2026,
        9,
        22,
        12,
        34,
        56,
        789012,
        tzinfo=MutableDeltaTimezone(mutable_offset),
        fold=1,
    )
    expected = (source.isoformat(), source.timestamp())

    evidence = NegativeEvidence("clock", "snapshot", observed_at=source)

    assert evidence.observed_at is not None
    assert type(evidence.observed_at.tzinfo) is timezone
    assert type(evidence.observed_at.utcoffset()) is timedelta
    assert evidence.observed_at.utcoffset() == timedelta(hours=1)
    assert evidence.observed_at.fold == 1
    assert (evidence.observed_at.isoformat(), evidence.observed_at.timestamp()) == expected

    mutable_offset.reported_seconds = 3 * 60 * 60
    assert evidence.observed_at.utcoffset() == timedelta(hours=1)
    assert (evidence.observed_at.isoformat(), evidence.observed_at.timestamp()) == expected


def test_datetime_freeze_copies_timezone_with_mutable_timedelta_subclass_offset() -> None:
    mutable_offset = MutableDelta(hours=1, reported_seconds=2 * 60 * 60)
    source_timezone = timezone(mutable_offset, "explicit-zone-name")
    assert type(source_timezone) is timezone
    assert type(source_timezone.utcoffset(None)) is MutableDelta
    source = datetime(2026, 9, 22, 12, 34, 56, 789012, tzinfo=source_timezone, fold=1)
    expected = (source.isoformat(), source.timestamp(), source.tzname())

    evidence = NegativeEvidence("clock", "snapshot", observed_at=source)

    assert evidence.observed_at is not None
    assert evidence.observed_at.tzinfo is not source_timezone
    assert type(evidence.observed_at.tzinfo) is timezone
    assert type(evidence.observed_at.utcoffset()) is timedelta
    assert evidence.observed_at.utcoffset() == timedelta(hours=1)
    assert evidence.observed_at.fold == 1
    assert (
        evidence.observed_at.isoformat(),
        evidence.observed_at.timestamp(),
        evidence.observed_at.tzname(),
    ) == expected

    mutable_offset.reported_seconds = 3 * 60 * 60
    assert evidence.observed_at.utcoffset() == timedelta(hours=1)
    assert (
        evidence.observed_at.isoformat(),
        evidence.observed_at.timestamp(),
        evidence.observed_at.tzname(),
    ) == expected


def test_datetime_freeze_copies_mutable_timezone_name_for_direct_and_nested_evidence() -> None:
    mutable_name = MutableLabelString("CUSTOM", "before")
    source_timezone = timezone(timedelta(hours=5), mutable_name)
    source = datetime(
        2026,
        9,
        22,
        12,
        34,
        56,
        789012,
        tzinfo=source_timezone,
        fold=1,
    )
    expected_name = str.__str__(mutable_name)
    expected_iso = source.isoformat()
    expected_timestamp = source.timestamp()
    expected_offset = source.utcoffset()

    negative = NegativeEvidence(
        "named-clock",
        "snapshot",
        observed_at=source,
        details={"nested": [source]},
    )
    outcome = FilterOutcome(
        "named-clock",
        None,
        evidence={"clock": source, "negative": negative},
    )
    assert outcome.evidence is not None
    assert negative.details is not None
    nested_negative = cast(NegativeEvidence, outcome.evidence["negative"])
    assert nested_negative.details is not None
    nested_details = cast(list[object], nested_negative.details["nested"])
    direct_details = cast(list[object], negative.details["nested"])
    snapshots = (
        negative.observed_at,
        direct_details[0],
        outcome.evidence["clock"],
        nested_negative.observed_at,
        nested_details[0],
    )
    expected_reprs = tuple(repr(snapshot) for snapshot in snapshots)

    mutable_name.label = "after"

    for snapshot, expected_repr in zip(snapshots, expected_reprs):
        assert type(snapshot) is datetime
        assert snapshot.tzinfo is not source_timezone
        assert type(snapshot.tzname()) is str
        assert snapshot.tzname() == expected_name
        assert snapshot.utcoffset() == expected_offset
        assert snapshot.fold == 1
        assert snapshot.isoformat() == expected_iso
        assert snapshot.timestamp() == expected_timestamp
        assert repr(snapshot) == expected_repr
