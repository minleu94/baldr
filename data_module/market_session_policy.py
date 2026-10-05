"""Shared clock policy for the project's completed daily market session."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo


TAIPEI = ZoneInfo("Asia/Taipei")
PACIFIC = ZoneInfo("America/Los_Angeles")
_PUBLICATION_CUTOFF = time(4, 30)


@dataclass(frozen=True, slots=True)
class ProjectMarketSessionBoundary:
    """The project cutoff and latest calendar date eligible at one clock."""

    taipei_date: date
    publication_cutoff: datetime
    calendar_end_date: date


def project_market_publication_cutoff(taipei_date: date) -> datetime:
    """Return 04:30 America/Los_Angeles for a Taipei decision date.

    The date conversion deliberately uses a same-date 23:00 Taipei anchor so
    the Pacific calendar date is resolved with the zone's actual DST rules.
    """

    if type(taipei_date) is not date:
        raise TypeError("taipei_date must be a date")
    pacific_date = datetime.combine(taipei_date, time(23), TAIPEI).astimezone(
        PACIFIC
    ).date()
    return datetime.combine(pacific_date, _PUBLICATION_CUTOFF, PACIFIC)


def resolve_project_market_session_boundary(
    observed_at: datetime,
) -> ProjectMarketSessionBoundary:
    """Resolve the daily cutoff's calendar endpoint at an aware clock.

    This helper does not guess exchange holidays. Callers must still resolve
    the most recent official trading date on or before ``calendar_end_date``
    through their verified offline calendar source.
    """

    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ValueError("market-session clock must be timezone-aware")
    local_now = observed_at.astimezone(TAIPEI)
    cutoff = project_market_publication_cutoff(local_now.date())
    pacific_now = observed_at.astimezone(PACIFIC)
    end_date = (
        local_now.date()
        if pacific_now >= cutoff
        else local_now.date() - timedelta(days=1)
    )
    return ProjectMarketSessionBoundary(
        taipei_date=local_now.date(),
        publication_cutoff=cutoff,
        calendar_end_date=end_date,
    )
