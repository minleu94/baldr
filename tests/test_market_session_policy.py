from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from data_module.market_session_policy import (
    resolve_project_market_session_boundary,
)


TAIPEI = ZoneInfo("Asia/Taipei")


@pytest.mark.parametrize(
    ("observed_at", "expected_calendar_end", "expected_cutoff"),
    [
        (
            datetime(2026, 10, 5, 13, 30, tzinfo=TAIPEI),
            "2026-10-04",
            "2026-10-05T04:30:00-07:00",
        ),
        (
            datetime(2026, 10, 5, 19, 29, 59, tzinfo=TAIPEI),
            "2026-10-04",
            "2026-10-05T04:30:00-07:00",
        ),
        (
            datetime(2026, 10, 5, 19, 30, tzinfo=TAIPEI),
            "2026-10-05",
            "2026-10-05T04:30:00-07:00",
        ),
        (
            datetime(2026, 1, 5, 20, 29, 59, tzinfo=TAIPEI),
            "2026-01-04",
            "2026-01-05T04:30:00-08:00",
        ),
        (
            datetime(2026, 1, 5, 20, 30, tzinfo=TAIPEI),
            "2026-01-05",
            "2026-01-05T04:30:00-08:00",
        ),
        (
            datetime(2026, 10, 4, 20, 0, tzinfo=TAIPEI),
            "2026-10-04",
            "2026-10-04T04:30:00-07:00",
        ),
    ],
)
def test_project_session_policy_uses_dst_aware_shared_cutoff(
    observed_at: datetime,
    expected_calendar_end: str,
    expected_cutoff: str,
) -> None:
    boundary = resolve_project_market_session_boundary(observed_at)

    assert boundary.calendar_end_date.isoformat() == expected_calendar_end
    assert boundary.publication_cutoff.isoformat() == expected_cutoff


def test_project_session_policy_rejects_naive_clock() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        resolve_project_market_session_boundary(datetime(2026, 10, 5, 12))
