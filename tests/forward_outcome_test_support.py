from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

from data_module.official_trading_calendar_cache import (
    build_twse_calendar_cache,
    write_twse_calendar_cache,
)


def write_verified_test_calendar_cache(
    root: Path,
    *,
    observed_at: datetime | None = None,
    year: int = 2026,
) -> Path:
    """Write a hash-bound annual calendar fixture under the test temp root."""

    calendar_observed_at = observed_at or datetime.now(timezone.utc)
    if (
        calendar_observed_at.tzinfo is None
        or calendar_observed_at.utcoffset() is None
    ):
        raise ValueError("observed_at must be aware")
    # Keep the verified fixture safely before the service's frozen invocation
    # clock; the runner intentionally truncates its clock to whole seconds.
    captured_at = calendar_observed_at - timedelta(seconds=2)
    root.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(
        [
            {
                "Name": "test closed day",
                "Date": f"{year - 1911:03d}0101",
                "Weekday": "Thursday",
                "Description": "test closed day",
            }
        ],
        separators=(",", ":"),
    ).encode("utf-8")
    path = root / f"twse_holiday_schedule_{year}_test.json"
    cache = build_twse_calendar_cache(
        calendar_year=year,
        raw_response=raw,
        requested_at=captured_at - timedelta(seconds=1),
        captured_at=captured_at,
        response_status=200,
        response_headers={"ETag": '"forward-outcome-fixture"'},
    )
    write_twse_calendar_cache(path, cache, allowed_root=root)
    return path
