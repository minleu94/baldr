from datetime import date, datetime, timedelta, timezone
import sqlite3
from unittest.mock import MagicMock, patch

import pytest

from data_module.official_trading_calendar import (
    CalendarObservationClock,
    CalendarObservationClockError,
    OfficialTradingCalendar,
    OfficialTradingCalendarError,
)


def test_official_trading_calendar_uses_market_indices_evidence(tmp_path):
    db_path = tmp_path / "market.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE market_indices (trade_date TEXT, index_name TEXT)")
        conn.execute("INSERT INTO market_indices VALUES ('20240722', 'TAIEX')")

    is_td, reason = OfficialTradingCalendar(db_path).is_official_trading_day(
        date(2024, 7, 22), allow_online_probe=False
    )

    assert is_td is True
    assert reason == "twstock_db_market_indices_evidence"


def test_official_trading_calendar_missing_evidence_is_unknown(tmp_path):
    is_td, reason = OfficialTradingCalendar(tmp_path / "missing.db").is_official_trading_day(
        date(2024, 7, 22), allow_online_probe=False
    )

    assert is_td is None
    assert reason == "lacks_official_evidence"


def test_historical_calendar_clock_is_aware_finite_and_cannot_probe_or_use_db(
    tmp_path,
):
    with pytest.raises(
        CalendarObservationClockError,
        match="requires_aware_datetime",
    ):
        CalendarObservationClock.historical_as_of(datetime(2026, 9, 8)).capture()

    future = datetime.now(timezone.utc) + timedelta(minutes=1)
    with pytest.raises(
        CalendarObservationClockError,
        match="future_rejected",
    ):
        CalendarObservationClock.historical_as_of(future).capture()

    db_path = tmp_path / "market.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE market_indices (trade_date TEXT, index_name TEXT)")
        conn.execute("INSERT INTO market_indices VALUES ('20240722', 'TAIEX')")
    historical = CalendarObservationClock.historical_as_of(
        datetime(2024, 7, 22, tzinfo=timezone.utc)
    )
    calendar = OfficialTradingCalendar(db_path)
    observation = historical.capture()
    with pytest.raises(AttributeError, match="calendar_observation_is_immutable"):
        observation.mode = "live_now"
    with pytest.raises(AttributeError, match="calendar_observation_is_immutable"):
        observation.effective_at = datetime.now(timezone.utc)
    assert observation.to_dict() == {
        "mode": "historical_as_of",
        "effective_at": "2024-07-22T00:00:00+00:00",
    }
    with patch(
        "data_module.official_trading_calendar.safe_request",
        side_effect=AssertionError("historical mode must stay offline"),
    ) as request:
        with pytest.raises(
            CalendarObservationClockError,
            match="cannot_probe_online",
        ):
            calendar.read_operation(
                observation_clock=observation,
                allow_online_probe=True,
            )
        result = calendar.is_official_trading_day(
            date(2024, 7, 22),
            allow_online_probe=False,
            observation_clock=observation,
        )
    assert result == (None, "lacks_official_evidence")
    request.assert_not_called()


def test_captured_calendar_observation_is_single_use(tmp_path):
    observation = CalendarObservationClock.historical_as_of(
        datetime(2026, 9, 8, 13, 0, tzinfo=timezone.utc)
    ).capture()
    calendar = OfficialTradingCalendar(tmp_path / "missing.db")

    assert calendar.is_official_trading_day(
        date(2026, 9, 8),
        allow_online_probe=False,
        observation_clock=observation,
    ) == (None, "lacks_official_evidence")
    with pytest.raises(
        CalendarObservationClockError,
        match="already_consumed",
    ):
        calendar.is_official_trading_day(
            date(2026, 9, 8),
            allow_online_probe=False,
            observation_clock=observation,
        )


@pytest.mark.parametrize("mode", ["live_now", "historical_as_of"])
def test_calendar_observation_clock_fields_are_read_only_and_one_use(
    tmp_path,
    mode,
):
    if mode == "live_now":
        clock = CalendarObservationClock.live_now()
    else:
        clock = CalendarObservationClock.historical_as_of(
            datetime(2026, 9, 8, 13, 0, tzinfo=timezone.utc)
        )
    observation = clock.capture()
    original = observation.to_dict()
    calendar = OfficialTradingCalendar(tmp_path / "missing.db")

    with pytest.raises(AttributeError):
        clock.mode = mode
    with pytest.raises(AttributeError):
        clock.as_of = datetime(2026, 9, 8, 13, 0, tzinfo=timezone.utc)
    with pytest.raises(AttributeError, match="calendar_observation_is_immutable"):
        observation.mode = "historical_as_of"
    with pytest.raises(AttributeError, match="calendar_observation_is_immutable"):
        observation.effective_at = datetime(2026, 9, 9, 13, 0, tzinfo=timezone.utc)

    with calendar.read_operation(
        observation_clock=observation,
        allow_online_probe=False,
    ) as operation:
        assert operation.observation.to_dict() == original
    with pytest.raises(
        CalendarObservationClockError,
        match="already_consumed",
    ):
        calendar.read_operation(
            observation_clock=observation,
            allow_online_probe=False,
        )


@pytest.mark.parametrize(
    ("field", "replacement", "reason"),
    [
        ("_mode", "live_now", "calendar_observation_mutated"),
        (
            "_effective_at",
            "future",
            "calendar_observation_clock_future_rejected",
        ),
    ],
)
def test_calendar_observation_revalidates_private_clock_on_claim(
    tmp_path,
    field,
    replacement,
    reason,
):
    observation = CalendarObservationClock.historical_as_of(
        datetime(2026, 9, 8, 13, 0, tzinfo=timezone.utc)
    ).capture()
    if replacement == "future":
        replacement = datetime.now(timezone.utc) + timedelta(minutes=1)
    object.__setattr__(observation, field, replacement)

    with pytest.raises(CalendarObservationClockError, match=reason):
        OfficialTradingCalendar(tmp_path / "missing.db").read_operation(
            observation_clock=observation,
            allow_online_probe=False,
        )


def test_calendar_read_operation_rechecks_observation_before_each_public_read(
    tmp_path,
):
    observation = CalendarObservationClock.historical_as_of(
        datetime(2026, 9, 8, 13, 0, tzinfo=timezone.utc)
    ).capture()
    calendar = OfficialTradingCalendar(tmp_path / "missing.db")

    with calendar.read_operation(
        observation_clock=observation,
        allow_online_probe=False,
    ) as operation:
        object.__setattr__(
            observation,
            "_effective_at",
            datetime(2026, 9, 7, 13, 0, tzinfo=timezone.utc),
        )
        with pytest.raises(
            CalendarObservationClockError,
            match="calendar_observation_mutated",
        ):
            operation.evidence_for(date(2026, 9, 8))


def test_calendar_read_operation_rejects_future_clock_before_public_read(
    tmp_path,
):
    observation = CalendarObservationClock.historical_as_of(
        datetime(2026, 9, 8, 13, 0, tzinfo=timezone.utc)
    ).capture()
    calendar = OfficialTradingCalendar(tmp_path / "missing.db")

    with calendar.read_operation(
        observation_clock=observation,
        allow_online_probe=False,
    ) as operation:
        object.__setattr__(
            observation,
            "_effective_at",
            datetime.now(timezone.utc) + timedelta(minutes=1),
        )
        with pytest.raises(
            CalendarObservationClockError,
            match="calendar_observation_clock_future_rejected",
        ):
            operation.evidence_for(date(2026, 9, 8))


def _official_response(rows: list[dict[str, str]]) -> MagicMock:
    response = MagicMock()
    response.json.return_value = rows
    return response


def test_official_trading_calendar_weekend_is_closed_without_online_request(
    tmp_path,
):
    with patch("data_module.official_trading_calendar.safe_request") as mock_req:
        is_td, reason = OfficialTradingCalendar(tmp_path / "missing.db").is_official_trading_day(
            date(2026, 8, 1), allow_online_probe=True
        )

    assert is_td is False
    assert reason == "weekend_closed"
    mock_req.assert_not_called()


def test_weekday_absent_from_valid_official_schedule_is_open(tmp_path):
    with patch(
        "data_module.official_trading_calendar.safe_request",
        return_value=_official_response(
            [
                {
                    "Name": "中華民國開國紀念日",
                    "Date": "1150101",
                    "Description": "依規定放假一日。",
                }
            ]
        ),
    ) as request:
        is_td, reason = OfficialTradingCalendar(
            tmp_path / "missing.db"
        ).is_official_trading_day(date(2026, 7, 29))

    assert is_td is True
    assert reason == "twse_holiday_schedule_open"
    assert request.call_args.kwargs["params"] == {"queryYear": "115"}


def test_weekday_listed_as_holiday_is_closed(tmp_path):
    with patch(
        "data_module.official_trading_calendar.safe_request",
        return_value=_official_response(
            [
                {
                    "Name": "和平紀念日補假",
                    "Date": "1150302",
                    "Description": "停止交易。",
                }
            ]
        ),
    ):
        is_td, reason = OfficialTradingCalendar(
            tmp_path / "missing.db"
        ).is_official_trading_day(date(2026, 3, 2))

    assert is_td is False
    assert reason == "twse_holiday_schedule_closed"


def test_explicit_start_last_resume_or_normal_trading_row_is_open(tmp_path):
    calendar = OfficialTradingCalendar(tmp_path / "missing.db")
    with patch(
        "data_module.official_trading_calendar.safe_request",
        return_value=_official_response(
            [
                {
                    "Name": "農曆春節前最後交易日",
                    "Date": "1150211",
                    "Description": "農曆春節前最後交易。",
                },
                {
                    "Name": "農曆春節後開始交易日",
                    "Date": "1150223",
                    "Description": "恢復交易。",
                },
            ]
        ),
    ):
        before, before_reason = calendar.is_official_trading_day(
            date(2026, 2, 11)
        )
        after, after_reason = calendar.is_official_trading_day(
            date(2026, 2, 23)
        )

    assert before is True
    assert after is True
    assert before_reason == "twse_holiday_schedule_explicit_open"
    assert after_reason == "twse_holiday_schedule_explicit_open"


def test_official_trading_calendar_request_failure_is_unknown_and_cached(
    tmp_path,
):
    with patch(
        "data_module.official_trading_calendar.safe_request",
        side_effect=RuntimeError("service temporarily unavailable"),
    ) as request:
        calendar = OfficialTradingCalendar(tmp_path / "missing.db")
        first = calendar.is_official_trading_day(date(2026, 7, 29))
        second = calendar.is_official_trading_day(date(2026, 7, 30))

    assert first == (None, "twse_holiday_schedule_unavailable")
    assert second == (None, "twse_holiday_schedule_unavailable")
    assert request.call_count == 1


def test_malformed_official_schedule_fails_closed(tmp_path):
    with patch(
        "data_module.official_trading_calendar.safe_request",
        return_value=_official_response([{"unexpected": "payload"}]),
    ):
        result = OfficialTradingCalendar(
            tmp_path / "missing.db"
        ).is_official_trading_day(date(2026, 7, 29))

    assert result == (None, "twse_holiday_schedule_unavailable")


def test_require_trading_days_fails_closed_on_unresolved_calendar(tmp_path):
    with patch(
        "data_module.official_trading_calendar.safe_request",
        side_effect=RuntimeError("service unavailable"),
    ):
        calendar = OfficialTradingCalendar(tmp_path / "missing.db")
        with pytest.raises(OfficialTradingCalendarError):
            calendar.require_trading_days_in_range(
                date(2026, 7, 29),
                date(2026, 7, 30),
            )


def test_recent_official_sessions_skip_holiday_and_weekend(tmp_path):
    with patch(
        "data_module.official_trading_calendar.safe_request",
        return_value=_official_response(
            [
                {
                    "Name": "和平紀念日補假",
                    "Date": "1150302",
                    "Description": "停止交易。",
                }
            ]
        ),
    ):
        calendar = OfficialTradingCalendar(tmp_path / "missing.db")
        records = calendar.get_recent_official_trading_days(
            date(2026, 3, 2),
            1,
        )

    assert [record["date_str"] for record in records] == ["2026-02-27"]
    assert records[0]["evidence"]["reason_code"] == "twse_holiday_schedule_open"
