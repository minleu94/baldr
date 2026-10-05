"""UX09 名單生命週期純函式狀態轉移測試。"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import hashlib

import pytest

from app_module.research_membership_lifecycle import (
    ExpectedSession,
    HistoryCoverage,
    LifecycleResult,
    LifecycleStatus,
    MembershipObservation,
    MembershipState,
    MethodIdentity,
    UniverseIdentity,
    classify_membership_lifecycle,
)


UTC = timezone.utc
_METHOD_PARAMETERS = {"direction": "above", "window": 20}


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _observation(
    day: date,
    state: MembershipState,
    *,
    previous: date | None,
    revision: str = "r1",
    method_version: str = "1.0.0",
    method_parameters: dict[str, object] | None = None,
    predicate: str = "AND(close_above_ma20)",
    universe_version: str = "v1",
    universe_semantic_key: str = "fixed-cohort:TW-research-v1",
    calendar_version: str = "official-v1",
    verified: bool = True,
    cutoff_delta: timedelta = timedelta(0),
    published_delta: timedelta = timedelta(minutes=1),
    available_delta: timedelta | None = timedelta(0),
) -> MembershipObservation:
    cutoff = datetime.combine(day, datetime.min.time(), UTC) + timedelta(hours=15) + cutoff_delta
    method = MethodIdentity.from_parameters(
        method_id="daily_market.close_above_ma20",
        version=method_version,
        parameters=method_parameters or _METHOD_PARAMETERS,
        predicate_semantic_key=predicate,
        window_policy_key="ma20:last-20-valid-closes",
    )
    return MembershipObservation(
        stock_id="2330",
        state=state,
        method=method,
        universe=UniverseIdentity(
            universe_id="tw-research-cohort",
            version=universe_version,
            semantic_key=universe_semantic_key,
        ),
        decision_date=day,
        cutoff_at=cutoff,
        published_at=cutoff + published_delta,
        source_available_at=(
            cutoff + available_delta if available_delta is not None else None
        ),
        schedule=ExpectedSession(
            calendar_key="TWSE-official",
            calendar_version=calendar_version,
            expected_previous_date=previous,
            verified=verified,
            calendar_manifest_id="calendar:2026",
            calendar_manifest_sha256=_sha(f"calendar:{calendar_version}"),
        ),
        source_manifest_id=f"snapshot:{day.isoformat()}:{revision}",
        source_manifest_sha256=_sha(f"manifest:{day.isoformat()}:{revision}"),
        source_artifact_sha256=_sha(f"artifact:{day.isoformat()}:{revision}"),
    )


def _classify(
    current: MembershipObservation,
    history: tuple[MembershipObservation, ...] | list[MembershipObservation],
    *,
    coverage: HistoryCoverage = HistoryCoverage.COMPLETE,
    as_of: datetime | None = None,
) -> LifecycleResult:
    return classify_membership_lifecycle(
        current,
        history,
        as_of=as_of or current.published_at,
        history_coverage=coverage,
    )


def test_weekend_session_links_and_lifecycle_transitions_are_replayable() -> None:
    thursday = date(2026, 10, 1)
    friday = date(2026, 10, 2)
    monday = date(2026, 10, 5)
    tuesday = date(2026, 10, 6)
    wednesday = date(2026, 10, 7)
    first_hit = _observation(thursday, MembershipState.MATCH, previous=None)
    no_match = _observation(friday, MembershipState.NO_MATCH, previous=thursday)
    reentered = _observation(monday, MembershipState.MATCH, previous=friday)
    continuing = _observation(tuesday, MembershipState.MATCH, previous=monday)
    exited = _observation(wednesday, MembershipState.NO_MATCH, previous=tuesday)

    reentry_result = _classify(reentered, [no_match, first_hit])
    assert reentry_result.status is LifecycleStatus.RESELECTED
    assert reentry_result.reason == "prior_hit_then_consecutive_no_match_to_match"
    assert reentry_result.first_seen == thursday
    assert reentry_result.last_hit == monday
    assert reentry_result.previous_date == friday
    assert reentry_result.previous_state is MembershipState.NO_MATCH
    assert reentry_result.streak == 1

    continued_result = _classify(continuing, [reentered, no_match, first_hit])
    assert continued_result.status is LifecycleStatus.CONTINUING
    assert continued_result.streak == 2

    exit_result = _classify(exited, [continuing, reentered, no_match, first_hit])
    assert exit_result.status is LifecycleStatus.NO_LONGER_SELECTED
    assert exit_result.last_hit == tuesday

    round_trip = LifecycleResult.from_dict(exit_result.to_dict())
    assert round_trip == exit_result
    assert round_trip.result_id == exit_result.result_id
    assert round_trip.reason_display == "連續預期交易日由符合轉為未符合。"


def test_new_selection_and_still_not_selected_need_consecutive_observations() -> None:
    friday = date(2026, 10, 2)
    monday = date(2026, 10, 5)
    tuesday = date(2026, 10, 6)
    prior_no_match = _observation(friday, MembershipState.NO_MATCH, previous=None)
    new_hit = _observation(monday, MembershipState.MATCH, previous=friday)
    assert _classify(new_hit, [prior_no_match]).status is LifecycleStatus.NEWLY_SELECTED

    remains = _observation(tuesday, MembershipState.NO_MATCH, previous=monday)
    result = _classify(remains, [new_hit, prior_no_match])
    assert result.status is LifecycleStatus.NO_LONGER_SELECTED
    second_no_match = _observation(date(2026, 10, 7), MembershipState.NO_MATCH, previous=tuesday)
    assert _classify(second_no_match, [remains, new_hit, prior_no_match]).status is LifecycleStatus.REMAINS_NOT_SELECTED


def test_gaps_and_unknown_membership_never_create_exit_or_reentry() -> None:
    thursday = date(2026, 10, 1)
    monday = date(2026, 10, 5)
    old_hit = _observation(thursday, MembershipState.MATCH, previous=None)
    current_hit = _observation(monday, MembershipState.MATCH, previous=date(2026, 10, 2))
    gap = _classify(current_hit, [old_hit])
    assert gap.status is LifecycleStatus.HISTORY_INSUFFICIENT
    assert gap.reason == "expected_session_gap_or_missing_observation"

    friday_unknown = _observation(date(2026, 10, 2), MembershipState.UNKNOWN, previous=thursday)
    monday_reentry = _observation(monday, MembershipState.MATCH, previous=date(2026, 10, 2))
    unknown_prior = _classify(monday_reentry, [friday_unknown, old_hit])
    assert unknown_prior.status is LifecycleStatus.UNKNOWN
    assert unknown_prior.reason == "previous_membership_unknown"

    current_unknown = _observation(monday, MembershipState.UNKNOWN, previous=date(2026, 10, 2))
    assert _classify(current_unknown, [friday_unknown, old_hit]).status is LifecycleStatus.UNKNOWN


def test_exact_duplicate_is_idempotent_but_older_date_revisions_are_boundary() -> None:
    friday = date(2026, 10, 2)
    monday = date(2026, 10, 5)
    prior = _observation(friday, MembershipState.MATCH, previous=None)
    current = _observation(monday, MembershipState.NO_MATCH, previous=friday)

    once = _classify(current, [prior])
    repeated = _classify(current, [prior, prior, current])
    assert once.status is LifecycleStatus.NO_LONGER_SELECTED
    assert repeated.result_id == once.result_id
    assert len(repeated.source_observations) == 2

    revision = _observation(
        friday,
        MembershipState.NO_MATCH,
        previous=None,
        revision="r2",
    )
    revised_history = _classify(current, [prior, revision])
    assert revised_history.status is LifecycleStatus.INCOMPARABLE
    assert revised_history.reason == "same_session_multiple_observations_or_revisions"
    assert revised_history.previous_date is None


def test_same_day_cutoff_revision_does_not_become_an_extra_session() -> None:
    friday = date(2026, 10, 2)
    monday = date(2026, 10, 5)
    current = _observation(monday, MembershipState.MATCH, previous=friday)
    alternate_cutoff = _observation(
        monday,
        MembershipState.NO_MATCH,
        previous=friday,
        revision="r2",
    )
    current_later_cutoff = _observation(
        monday,
        MembershipState.MATCH,
        previous=friday,
        revision="r3",
        cutoff_delta=timedelta(minutes=20),
    )
    prior = _observation(friday, MembershipState.NO_MATCH, previous=None)
    result = _classify(current_later_cutoff, [prior, alternate_cutoff])
    assert result.status is LifecycleStatus.INCOMPARABLE
    assert result.reason == "same_session_multiple_observations_or_revisions"


@pytest.mark.parametrize(
    ("changed", "reason"),
    [
        ({"method_version": "2.0.0"}, "method_identity_changed"),
        ({"method_parameters": {"direction": "above", "window": 60}}, "method_identity_changed"),
        ({"predicate": "OR(close_above_ma20,close_above_ma60)"}, "method_identity_changed"),
        ({"universe_version": "v2"}, "universe_identity_changed"),
        ({"universe_semantic_key": "different-cohort"}, "universe_identity_changed"),
    ],
)
def test_method_and_universe_identity_changes_are_incomparable(
    changed: dict[str, object], reason: str
) -> None:
    friday = date(2026, 10, 2)
    monday = date(2026, 10, 5)
    prior = _observation(friday, MembershipState.NO_MATCH, previous=None)
    current = _observation(monday, MembershipState.MATCH, previous=friday, **changed)
    result = _classify(current, [prior])
    assert result.status is LifecycleStatus.INCOMPARABLE
    assert result.reason == reason


def test_as_of_future_publication_and_retrospective_backfill_are_not_used() -> None:
    friday = date(2026, 10, 2)
    monday = date(2026, 10, 5)
    prior = _observation(friday, MembershipState.MATCH, previous=None)
    future = _observation(monday, MembershipState.NO_MATCH, previous=friday)
    earlier_as_of = future.cutoff_at + timedelta(seconds=30)
    future_result = _classify(future, [prior], as_of=earlier_as_of)
    assert future_result.status is LifecycleStatus.UNKNOWN
    assert future_result.reason == "current_publication_after_as_of"
    assert future_result.first_seen == friday
    assert future_result.last_hit == friday

    backfill = _observation(
        monday,
        MembershipState.MATCH,
        previous=friday,
        available_delta=timedelta(minutes=10),
        published_delta=timedelta(minutes=15),
    )
    backfill_result = _classify(backfill, [prior])
    assert backfill_result.status is LifecycleStatus.INCOMPARABLE
    assert backfill_result.reason == "current_retrospective_backfill_after_cutoff"
    assert backfill_result.last_hit == friday

    late_prior = _observation(
        friday,
        MembershipState.MATCH,
        previous=None,
        available_delta=timedelta(minutes=10),
        published_delta=timedelta(minutes=15),
    )
    no_match = _observation(
        monday,
        MembershipState.NO_MATCH,
        previous=friday,
        published_delta=timedelta(minutes=20),
    )
    late_history_result = _classify(no_match, [late_prior])
    assert late_history_result.status is LifecycleStatus.INCOMPARABLE
    assert late_history_result.reason == "previous_retrospective_backfill_after_cutoff"
    assert late_history_result.last_hit is None


def test_unknown_schedule_and_future_cutoff_fail_closed() -> None:
    friday = date(2026, 10, 2)
    monday = date(2026, 10, 5)
    unverified = _observation(friday, MembershipState.NO_MATCH, previous=None, verified=False)
    current = _observation(monday, MembershipState.MATCH, previous=friday)
    assert _classify(unverified, []).status is LifecycleStatus.INCOMPARABLE
    result = _classify(current, [unverified])
    assert result.status is LifecycleStatus.INCOMPARABLE
    assert result.reason == "previous_expected_session_unverified"

    future_cutoff = _observation(
        monday,
        MembershipState.MATCH,
        previous=friday,
        cutoff_delta=timedelta(days=1),
        published_delta=timedelta(days=1, minutes=2),
    )
    cutoff_result = _classify(
        future_cutoff,
        [unverified],
        as_of=future_cutoff.cutoff_at - timedelta(minutes=1),
    )
    assert cutoff_result.status is LifecycleStatus.INCOMPARABLE
    assert cutoff_result.reason == "current_cutoff_after_as_of"


def test_incomplete_history_reports_insufficient_and_float_parameters_reject() -> None:
    current = _observation(date(2026, 10, 5), MembershipState.MATCH, previous=None)
    result = _classify(current, [], coverage=HistoryCoverage.TRUNCATED)
    assert result.status is LifecycleStatus.HISTORY_INSUFFICIENT
    assert result.reason == "history_boundary_not_complete"
    with pytest.raises(ValueError, match="floats"):
        MethodIdentity.from_parameters(
            method_id="daily_market.close_above_ma20",
            version="1.0.0",
            parameters={"threshold": 1.25},
            predicate_semantic_key="AND(close_above_ma20)",
            window_policy_key="ma20:last-20-valid-closes",
        )


def test_new_is_scoped_to_complete_observed_archive_with_real_calendar_predecessor() -> None:
    first_day = date(2026, 10, 2)
    first = _observation(first_day, MembershipState.NO_MATCH, previous=date(2026, 10, 1))
    current = _observation(date(2026, 10, 5), MembershipState.MATCH, previous=first_day)
    result = _classify(current, [first])
    assert result.status is LifecycleStatus.NEWLY_SELECTED
    assert result.first_seen == first_day
    assert "歷史範圍" in result.reason_display
    assert _classify(current, [first], coverage=HistoryCoverage.UNKNOWN).status is LifecycleStatus.HISTORY_INSUFFICIENT
    older = _observation(date(2026, 9, 30), MembershipState.MATCH, previous=None)
    assert _classify(current, [first, older]).status is LifecycleStatus.HISTORY_INSUFFICIENT
