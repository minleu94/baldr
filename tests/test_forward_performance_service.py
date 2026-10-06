from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from data_module.config import TWStockConfig
from app_module.evidence_event_dtos import (
    EvidenceDataQuality,
    EvidenceEventType,
    EvidenceOutcomeStatus,
)
from app_module.evidence_event_repository import EvidenceEventRepository
from app_module.evidence_event_service import EvidenceEventService
from app_module.official_maturity_calendar import OfficialMaturityCalendar
from app_module.forward_performance_service import ForwardPerformanceService
from data_module.official_trading_calendar_cache import (
    build_twse_calendar_cache,
    write_twse_calendar_cache,
)


def _config(tmp_path: Path) -> TWStockConfig:
    config = TWStockConfig(data_root=tmp_path / "data", output_root=tmp_path / "output")
    config.db_file.parent.mkdir(parents=True, exist_ok=True)
    return config


def _verified_calendar(root: Path) -> OfficialMaturityCalendar:
    observed_at = datetime.now(timezone.utc)
    cache_root = root / "test_official_calendar"
    cache_root.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(
        [
            {
                "Name": "test closed day",
                "Date": "1150101",
                "Weekday": "Thursday",
                "Description": "test closed day",
            }
        ],
        separators=(",", ":"),
    ).encode("utf-8")
    cache = build_twse_calendar_cache(
        calendar_year=2026,
        raw_response=raw,
        requested_at=observed_at - timedelta(seconds=1),
        captured_at=observed_at,
        response_status=200,
        response_headers={"ETag": '"forward-service-test"'},
    )
    write_twse_calendar_cache(
        cache_root / "twse_holiday_schedule_2026_test.json",
        cache,
        allowed_root=cache_root,
    )
    return OfficialMaturityCalendar(cache_root, observed_at=observed_at)


def _seed_prices(db_path: Path) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE daily_prices (
                日期 TEXT,
                證券代號 TEXT,
                收盤價 REAL,
                PRIMARY KEY (證券代號, 日期)
            );
            CREATE TABLE market_indices (
                日期 TEXT,
                指數名稱 TEXT,
                收盤指數 REAL,
                PRIMARY KEY (指數名稱, 日期)
            );
            CREATE TABLE industry_indices (
                日期 TEXT,
                指數名稱 TEXT,
                收盤指數 REAL,
                PRIMARY KEY (指數名稱, 日期)
            );
            """
        )
        for index in range(0, 8):
            day = f"202606{index + 1:02d}"
            conn.execute(
                "INSERT INTO daily_prices VALUES (?, ?, ?)",
                (day, "2330", 100 + index * 2),
            )
            conn.execute(
                "INSERT INTO market_indices VALUES (?, ?, ?)",
                (day, "TAIEX", 10000 + index * 10),
            )
            conn.execute(
                "INSERT INTO industry_indices VALUES (?, ?, ?)",
                (day, "半導體類指數", 500 + index * 5),
            )


def _record_event(
    config: TWStockConfig,
    *,
    benchmark_id: str | None = "TAIEX",
    industry_id: str | None = "半導體類指數",
    sector: str | None = None,
    event_date: str = "2026-06-01",
):
    service = EvidenceEventService(EvidenceEventRepository(config))
    return service.record_event(
        event_date=event_date,
        decision_date=event_date,
        symbol="2330",
        event_type=EvidenceEventType.WATCHLIST_TRIGGER,
        event_family="watchlist",
        source_type="decision_desk",
        source_id="desk-001",
        reason_codes=("rank_top",),
        data_quality=EvidenceDataQuality.OBSERVED,
        warnings=(),
        as_of_date=event_date,
        available_date=event_date,
        source_version="test",
        sector=sector,
        benchmark_id=benchmark_id,
        industry_benchmark_id=industry_id,
    )


def _seed_unnamed_market_index_with_close_price(db_path: Path) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE daily_prices (
                日期 TEXT,
                證券代號 TEXT,
                收盤價 REAL,
                PRIMARY KEY (證券代號, 日期)
            );
            CREATE TABLE market_indices (
                日期 TEXT,
                指數名稱 TEXT,
                收盤指數 REAL,
                收盤價 REAL
            );
            CREATE TABLE industry_indices (
                日期 TEXT,
                指數名稱 TEXT,
                收盤指數 REAL,
                PRIMARY KEY (指數名稱, 日期)
            );
            """
        )
        for index in range(0, 8):
            day = f"202606{index + 1:02d}"
            conn.execute(
                "INSERT INTO daily_prices VALUES (?, ?, ?)",
                (day, "2330", 100 + index * 2),
            )
            conn.execute(
                "INSERT INTO market_indices VALUES (?, ?, ?, ?)",
                (day, None, None, 10000 + index * 10),
            )
            conn.execute(
                "INSERT INTO industry_indices VALUES (?, ?, ?)",
                (day, "半導體類指數", 500 + index * 5),
            )


def test_forward_outcome_uses_trading_day_window_not_calendar_days(tmp_path):
    config = _config(tmp_path)
    _seed_prices(config.db_file)
    event = _record_event(config)
    forward = ForwardPerformanceService(
        config,
        EvidenceEventRepository(config),
        maturity_calendar=_verified_calendar(config.output_root),
    )

    summary = forward.calculate(windows=(5,), dry_run=False)
    outcome = forward.repository.list_outcomes(event_id=event.event_id)[0]

    assert summary.events_scanned == 1
    assert summary.outcomes_created == 1
    assert outcome.outcome_status == EvidenceOutcomeStatus.READY
    assert outcome.event_price_date == "2026-06-01"
    assert outcome.outcome_price_date == "2026-06-08"
    assert outcome.forward_return_bp == 1400
    assert outcome.return_basis == "close_to_close_event_date"
    assert outcome.window_type == "trading_days"
    assert outcome.metadata["maturity_basis"] == "official_market_sessions"
    assert outcome.metadata["planned_official_maturity_date"] == "2026-06-08"


def test_verified_calendar_keeps_matured_exact_session_ready(tmp_path):
    config = _config(tmp_path)
    _seed_prices(config.db_file)
    event = _record_event(config)
    forward = ForwardPerformanceService(
        config,
        EvidenceEventRepository(config),
        maturity_calendar=_verified_calendar(config.output_root),
    )
    summary = forward.calculate(windows=(5,), dry_run=False)
    outcome = forward.repository.list_outcomes(event_id=event.event_id)[0]

    assert summary.blocked_time_contract_count == 0
    assert outcome.outcome_status == EvidenceOutcomeStatus.READY
    assert outcome.outcome_price_date == "2026-06-08"
    assert outcome.forward_return_bp is not None
    assert outcome.metadata["planned_official_calendar"]["status"] == "annual_plan_only"
    assert outcome.metadata["maturity_calendar_comparison"] == (
        "legacy_price_row_offset_differs"
    )


def test_summary_counts_missing_event_price_separately(tmp_path: Path) -> None:
    config = _config(tmp_path)
    _seed_prices(config.db_file)
    event = _record_event(config, event_date="2026-05-31")
    forward = ForwardPerformanceService(
        config,
        EvidenceEventRepository(config),
        maturity_calendar=_verified_calendar(config.output_root),
    )

    summary = forward.calculate(windows=(5,), dry_run=False)
    outcome = forward.repository.get_outcome(event.event_id, 5)

    assert outcome is not None
    assert outcome.outcome_status == EvidenceOutcomeStatus.MISSING_PRICE
    assert "missing_event_price" in outcome.warnings
    assert summary.missing_event_price == 1
    assert summary.missing_outcome_price == 0


def test_summary_counts_missing_official_target_price_without_missing_event(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    _seed_prices(config.db_file)
    with sqlite3.connect(config.db_file) as conn:
        conn.execute("DELETE FROM daily_prices WHERE 日期 = ?", ("20260608",))
    event = _record_event(config)
    forward = ForwardPerformanceService(
        config,
        EvidenceEventRepository(config),
        maturity_calendar=_verified_calendar(config.output_root),
    )

    summary = forward.calculate(windows=(5,), dry_run=False)
    outcome = forward.repository.get_outcome(event.event_id, 5)

    assert outcome is not None
    assert outcome.outcome_status == EvidenceOutcomeStatus.MISSING_PRICE
    assert "missing_outcome_price" in outcome.warnings
    assert "missing_event_price" not in outcome.warnings
    assert summary.missing_event_price == 0
    assert summary.missing_outcome_price == 1


def test_missing_calendar_blocks_outcome_without_row_offset_price(tmp_path):
    config = _config(tmp_path)
    _seed_prices(config.db_file)
    event = _record_event(config)
    forward = ForwardPerformanceService(config, EvidenceEventRepository(config))

    summary = forward.calculate(windows=(5,), dry_run=False)
    outcome = forward.repository.list_outcomes(event_id=event.event_id)[0]

    assert summary.blocked_time_contract_count == 1
    assert summary.events_ready == 1
    assert summary.outcomes_created == 1
    assert outcome.outcome_status == EvidenceOutcomeStatus.PENDING
    assert outcome.data_quality == EvidenceDataQuality.DEGRADED
    assert outcome.outcome_price_date is None
    assert outcome.outcome_close is None
    assert outcome.forward_return_bp is None
    assert "expected_maturity_date" not in outcome.metadata
    assert outcome.metadata["time_contract_state"] == "blocked_time_contract"
    assert outcome.metadata["expected_maturity_date_basis"] == (
        "verified_official_market_sessions_required"
    )
    assert outcome.metadata["maturity_status_basis"] == (
        "verified_official_market_sessions_required"
    )
    assert outcome.metadata["maturity_calendar_comparison"] == (
        "official_calendar_not_configured"
    )
    assert "official_maturity_calendar_unavailable" in outcome.warnings


def test_default_cutoff_ignores_future_database_rows_after_taipei_today(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config = _config(tmp_path)
    _seed_prices(config.db_file)
    with sqlite3.connect(config.db_file) as conn:
        future_rows = (
            ("20260928", 300),
            ("20260929", 302),
            ("20260930", 304),
            ("20261001", 306),
            ("20261002", 308),
            ("20261005", 310),
        )
        for day, close in future_rows:
            conn.execute(
                "INSERT INTO daily_prices VALUES (?, ?, ?)",
                (day, "2330", close),
            )
            conn.execute(
                "INSERT INTO market_indices VALUES (?, ?, ?)",
                (day, "TAIEX", 10000 + close),
            )
            conn.execute(
                "INSERT INTO industry_indices VALUES (?, ?, ?)",
                (day, "半導體類指數", 500 + close),
            )
    event = _record_event(config, event_date="2026-09-28")

    class _FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            fixed = datetime(2026, 10, 4, 12, 0, tzinfo=timezone.utc)
            return fixed.astimezone(tz) if tz is not None else fixed.replace(tzinfo=None)

    import app_module.forward_performance_service as service_module

    monkeypatch.setattr(service_module, "datetime", _FrozenDateTime)
    forward = ForwardPerformanceService(
        config,
        EvidenceEventRepository(config),
        maturity_calendar=_verified_calendar(config.output_root),
    )

    summary = forward.calculate(windows=(5,), dry_run=False)
    outcome = forward.repository.list_outcomes(event_id=event.event_id)[0]

    assert summary.pending_insufficient_future_data == 1
    assert outcome.outcome_status == EvidenceOutcomeStatus.INSUFFICIENT_FUTURE_DATA
    assert outcome.outcome_price_date is None
    assert outcome.metadata["planned_official_maturity_date"] == "2026-10-05"


def test_official_target_session_overrides_legacy_non_null_row_offset(tmp_path):
    config = _config(tmp_path)
    _seed_prices(config.db_file)
    event = _record_event(config)

    class _OfficialTarget:
        def evaluate(self, **_kwargs):
            return SimpleNamespace(
                planned_date="2026-06-05",
                status="planned_reached",
                remaining_sessions=0,
                calendar={"status": "annual_plan_only"},
            )

    forward = ForwardPerformanceService(
        config,
        EvidenceEventRepository(config),
        maturity_calendar=_OfficialTarget(),
    )
    summary = forward.calculate(windows=(5,), dry_run=False)
    outcome = forward.repository.list_outcomes(event_id=event.event_id)[0]

    assert summary.blocked_time_contract_count == 0
    assert outcome.outcome_status == EvidenceOutcomeStatus.READY
    assert outcome.outcome_price_date == "2026-06-05"
    assert outcome.forward_return_bp == 800
    assert outcome.metadata["planned_official_maturity_date"] == "2026-06-05"
    assert outcome.metadata["expected_maturity_date"] == "2026-06-06"
    assert outcome.metadata["maturity_basis"] == "official_market_sessions"
    assert outcome.metadata["expected_maturity_date_basis"] == (
        "legacy_price_row_offset"
    )
    assert outcome.metadata["maturity_status_basis"] == "legacy_price_row_offset"
    assert outcome.metadata["maturity_calendar_comparison"] == (
        "legacy_price_row_offset_differs"
    )
    assert outcome.metadata["target_price_state"] == (
        "observed_on_planned_official_session"
    )


def test_official_session_horizons_5_10_20_60_use_exact_target_close(tmp_path):
    config = _config(tmp_path)
    sessions = []
    current = date(2026, 6, 1)
    while len(sessions) < 61:
        if current.weekday() < 5:
            sessions.append(current)
        current += timedelta(days=1)
    with sqlite3.connect(config.db_file) as conn:
        conn.executescript(
            """
            CREATE TABLE daily_prices (
                日期 TEXT,
                證券代號 TEXT,
                收盤價 REAL,
                PRIMARY KEY (證券代號, 日期)
            );
            CREATE TABLE market_indices (
                日期 TEXT,
                index_name TEXT,
                close REAL,
                PRIMARY KEY (index_name, 日期)
            );
            CREATE TABLE industry_indices (
                日期 TEXT,
                index_name TEXT,
                close REAL,
                PRIMARY KEY (index_name, 日期)
            );
            """
        )
        for index, day in enumerate(sessions):
            day_key = day.strftime("%Y%m%d")
            conn.execute(
                "INSERT INTO daily_prices VALUES (?, ?, ?)",
                (day_key, "2330", 100 + index),
            )
            conn.execute(
                "INSERT INTO market_indices VALUES (?, ?, ?)",
                (day_key, "TAIEX", 10_000 + index * 10),
            )
            conn.execute(
                "INSERT INTO industry_indices VALUES (?, ?, ?)",
                (day_key, "半導體業", 2_000 + index * 5),
            )
    event = _record_event(config)

    class _OfficialSessions:
        def evaluate(self, *, window_days, **_kwargs):
            return SimpleNamespace(
                planned_date=sessions[int(window_days)].isoformat(),
                status="planned_reached",
                remaining_sessions=0,
                calendar={"status": "annual_plan_only"},
            )

    forward = ForwardPerformanceService(
        config,
        EvidenceEventRepository(config),
        maturity_calendar=_OfficialSessions(),
    )
    summary = forward.calculate(windows=(5, 10, 20, 60), dry_run=False)
    outcomes = {
        item.window_days: item
        for item in forward.repository.list_outcomes(event_id=event.event_id)
    }

    assert summary.blocked_time_contract_count == 0
    assert set(outcomes) == {5, 10, 20, 60}
    for window in (5, 10, 20, 60):
        outcome = outcomes[window]
        assert outcome.outcome_status == EvidenceOutcomeStatus.READY
        assert outcome.outcome_price_date == sessions[window].isoformat()
        assert outcome.forward_return_bp == window * 100
        assert outcome.metadata["maturity_basis"] == "official_market_sessions"
        assert outcome.metadata["maturity_calendar_comparison"] == "match"
        assert outcome.metadata["official_target_price_lookup_detail"] == (
            "verified_unique_close"
        )


def test_unavailable_official_calendar_does_not_fall_back_to_row_offset(tmp_path):
    config = _config(tmp_path)
    _seed_prices(config.db_file)
    event = _record_event(config)

    class _UnavailableCalendar:
        def evaluate(self, **_kwargs):
            return SimpleNamespace(
                planned_date=None,
                status="waiting_for_calendar",
                remaining_sessions=None,
                calendar={"status": "waiting_for_calendar", "reason": "fixture"},
            )

    forward = ForwardPerformanceService(
        config,
        EvidenceEventRepository(config),
        maturity_calendar=_UnavailableCalendar(),
    )
    outcome = forward._build_outcome(
        event,
        5,
        data_as_of_date="2026-06-08",
    )

    assert outcome.outcome_status == EvidenceOutcomeStatus.PENDING
    assert outcome.outcome_price_date is None
    assert outcome.forward_return_bp is None
    assert outcome.metadata["time_contract_state"] == "blocked_time_contract"
    assert outcome.metadata["readiness_blocker"] == (
        "official_maturity_calendar_unavailable"
    )
    assert outcome.metadata["target_price_state"] == (
        "waiting_for_verified_official_session"
    )


def test_official_target_after_cutoff_does_not_read_future_close(tmp_path, monkeypatch):
    config = _config(tmp_path)
    _seed_prices(config.db_file)
    event = _record_event(config)

    class _FutureOfficialTarget:
        def evaluate(self, **_kwargs):
            return SimpleNamespace(
                planned_date="2026-06-07",
                status="planned",
                remaining_sessions=1,
                calendar={"status": "annual_plan_only"},
            )

    forward = ForwardPerformanceService(
        config,
        EvidenceEventRepository(config),
        maturity_calendar=_FutureOfficialTarget(),
    )

    def _unexpected_exact_lookup(*_args, **_kwargs):
        raise AssertionError("future official close must not be queried before cutoff")

    monkeypatch.setattr(
        forward,
        "_find_exact_official_outcome_price",
        _unexpected_exact_lookup,
    )
    monkeypatch.setattr(forward, "_find_outcome_price", _unexpected_exact_lookup)
    outcome = forward._build_outcome(
        event,
        5,
        data_as_of_date="2026-06-06",
    )

    assert outcome.outcome_status == EvidenceOutcomeStatus.INSUFFICIENT_FUTURE_DATA
    assert outcome.outcome_price_date is None
    assert outcome.forward_return_bp is None
    assert outcome.metadata["official_maturity_date"] == "2026-06-07"
    assert outcome.metadata["target_price_state"] == (
        "waiting_for_planned_official_session"
    )
    assert outcome.metadata["source_price_gap_reason"] is None
    assert "insufficient_future_data" in outcome.warnings


def test_forward_outcome_uses_unnamed_market_index_when_event_benchmark_missing(tmp_path):
    config = _config(tmp_path)
    _seed_unnamed_market_index_with_close_price(config.db_file)
    event = _record_event(config, benchmark_id=None)
    forward = ForwardPerformanceService(
        config,
        EvidenceEventRepository(config),
        maturity_calendar=_verified_calendar(config.output_root),
    )

    summary = forward.calculate(windows=(5,), dry_run=False)
    outcome = forward.repository.list_outcomes(event_id=event.event_id)[0]

    assert summary.missing_benchmark == 0
    assert outcome.benchmark_return_bp == 70
    assert outcome.benchmark_excess_bp == 1330
    assert "missing_benchmark" not in outcome.warnings


def test_forward_outcome_maps_event_sector_to_industry_index_name(tmp_path):
    config = _config(tmp_path)
    _seed_prices(config.db_file)
    event = _record_event(
        config,
        industry_id=None,
        sector="電子零組件業",
    )
    with sqlite3.connect(config.db_file) as conn:
        for index in range(0, 8):
            day = f"202606{index + 1:02d}"
            conn.execute(
                "INSERT INTO industry_indices VALUES (?, ?, ?)",
                (day, "電子零組件類指數", 1000 + index * 10),
            )
    forward = ForwardPerformanceService(
        config,
        EvidenceEventRepository(config),
        maturity_calendar=_verified_calendar(config.output_root),
    )

    summary = forward.calculate(windows=(5,), dry_run=False)
    outcome = forward.repository.list_outcomes(event_id=event.event_id)[0]

    assert summary.missing_industry_benchmark == 0
    assert outcome.industry_return_bp == 700
    assert outcome.industry_excess_bp == 700
    assert "missing_industry_benchmark" not in outcome.warnings


def test_forward_outcome_marks_insufficient_future_data_without_failing_batch(tmp_path):
    config = _config(tmp_path)
    _seed_prices(config.db_file)
    event = _record_event(config)
    forward = ForwardPerformanceService(
        config,
        EvidenceEventRepository(config),
        maturity_calendar=_verified_calendar(config.output_root),
    )

    summary = forward.calculate(
        windows=(60,),
        dry_run=False,
        data_as_of_date="2026-06-08",
    )
    outcome = forward.repository.list_outcomes(event_id=event.event_id)[0]

    assert summary.pending_insufficient_future_data == 1
    assert outcome.outcome_status == EvidenceOutcomeStatus.INSUFFICIENT_FUTURE_DATA
    assert "insufficient_future_data" in outcome.warnings


def test_weekend_event_uses_previous_trading_day_without_look_ahead(tmp_path):
    config = _config(tmp_path)
    with sqlite3.connect(config.db_file) as conn:
        conn.execute("CREATE TABLE daily_prices (日期 TEXT, 證券代號 TEXT, 收盤價 REAL)")
        conn.executemany(
            "INSERT INTO daily_prices VALUES (?, ?, ?)",
            (("20260710", "2330", 1000), ("20260713", "2330", 1010)),
        )
    event = EvidenceEventService(EvidenceEventRepository(config)).record_event(
        event_date="2026-07-12",
        decision_date="2026-07-12",
        symbol="2330",
        event_type=EvidenceEventType.RECOMMENDATION_INCLUDED,
        event_family="recommendation",
        source_type="persisted_recommendation",
        data_quality=EvidenceDataQuality.OBSERVED,
        warnings=(),
        as_of_date="2026-07-12",
        available_date="2026-07-12",
    )
    forward = ForwardPerformanceService(
        config,
        EvidenceEventRepository(config),
        maturity_calendar=_verified_calendar(config.output_root),
    )

    forward.calculate(windows=(1,), dry_run=False, data_as_of_date="2026-07-12")
    outcome = forward.repository.list_outcomes(event_id=event.event_id)[0]

    assert outcome.event_price_date == "2026-07-10"
    assert outcome.event_close == "1000.0"
    assert outcome.outcome_status == EvidenceOutcomeStatus.INSUFFICIENT_FUTURE_DATA
    assert outcome.metadata["event_price_fallback_reason"] == "previous_trading_day"


def test_missing_benchmark_and_industry_create_warnings_not_batch_failure(tmp_path):
    config = _config(tmp_path)
    _seed_prices(config.db_file)
    event = _record_event(config, benchmark_id="MISSING_INDEX", industry_id="MISSING_INDUSTRY")
    forward = ForwardPerformanceService(
        config,
        EvidenceEventRepository(config),
        maturity_calendar=_verified_calendar(config.output_root),
    )

    summary = forward.calculate(windows=(5,), dry_run=False)
    outcome = forward.repository.list_outcomes(event_id=event.event_id)[0]

    assert summary.events_ready == 1
    assert summary.missing_benchmark == 1
    assert summary.missing_industry_benchmark == 1
    assert outcome.outcome_status == EvidenceOutcomeStatus.READY
    assert outcome.benchmark_return_bp is None
    assert outcome.industry_return_bp is None
    assert "missing_benchmark" in outcome.warnings
    assert "missing_industry_benchmark" in outcome.warnings


def test_dry_run_does_not_write_outcomes(tmp_path):
    config = _config(tmp_path)
    _seed_prices(config.db_file)
    event = _record_event(config)
    repo = EvidenceEventRepository(config)
    forward = ForwardPerformanceService(
        config,
        repo,
        maturity_calendar=_verified_calendar(config.output_root),
    )

    summary = forward.calculate(windows=(5,), dry_run=True)

    assert summary.dry_run is True
    assert summary.outcomes_created == 1
    assert repo.list_outcomes(event_id=event.event_id) == []


def test_calculator_filters_symbol_event_type_and_decision_date(tmp_path):
    config = _config(tmp_path)
    _seed_prices(config.db_file)
    event = _record_event(config)
    forward = ForwardPerformanceService(
        config,
        EvidenceEventRepository(config),
        maturity_calendar=_verified_calendar(config.output_root),
    )

    skipped = forward.calculate(windows=(5,), symbol="2317", dry_run=True)
    selected = forward.calculate(
        windows=(5,),
        symbol="2330",
        event_type=EvidenceEventType.WATCHLIST_TRIGGER,
        decision_date="2026-06-01",
        dry_run=True,
    )

    assert skipped.events_scanned == 0
    assert selected.events_scanned == 1
    assert selected.events_ready == 1
    assert event.symbol == "2330"


def test_forward_outcome_degrades_when_corporate_action_gap_detected(tmp_path):
    config = _config(tmp_path)
    _seed_prices(config.db_file)
    import contextlib
    with contextlib.closing(sqlite3.connect(config.db_file)) as conn:
        conn.execute("CREATE TABLE corporate_action_events (stock_code TEXT, event_type TEXT, event_date TEXT)")
        conn.execute("INSERT INTO corporate_action_events VALUES ('2330', 'ex_dividend', '2026-06-03')")
        conn.commit()

    event = _record_event(config)
    forward = ForwardPerformanceService(
        config,
        EvidenceEventRepository(config),
        maturity_calendar=_verified_calendar(config.output_root),
    )

    summary = forward.calculate(windows=(5,), dry_run=False)
    outcome = forward.repository.list_outcomes(event_id=event.event_id)[0]

    assert "corporate_action_gap_detected" in outcome.warnings
    assert outcome.data_quality == EvidenceDataQuality.DEGRADED


def test_forward_outcome_degrades_when_trading_restriction_gap_detected(tmp_path):
    config = _config(tmp_path)
    _seed_prices(config.db_file)
    import contextlib
    with contextlib.closing(sqlite3.connect(config.db_file)) as conn:
        conn.execute("CREATE TABLE microstructure_restriction_events (stock_code TEXT, restriction_type TEXT, effective_date TEXT)")
        conn.execute("INSERT INTO microstructure_restriction_events VALUES ('2330', 'disposition', '2026-06-03')")
        conn.commit()

    event = _record_event(config)
    forward = ForwardPerformanceService(
        config,
        EvidenceEventRepository(config),
        maturity_calendar=_verified_calendar(config.output_root),
    )
    summary = forward.calculate(windows=(5,), dry_run=False)
    outcome = forward.repository.list_outcomes(event_id=event.event_id)[0]

    assert "trading_restriction_gap_detected" in outcome.warnings
    assert outcome.data_quality == EvidenceDataQuality.DEGRADED


def _seed_clock_boundary_prices(db_path: Path, *, include_today: bool) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            '''
            CREATE TABLE daily_prices (
                "日期" TEXT,
                "證券代號" TEXT,
                "收盤價" REAL,
                PRIMARY KEY ("證券代號", "日期")
            );
            CREATE TABLE market_indices (
                date TEXT,
                name TEXT,
                close REAL,
                PRIMARY KEY (name, date)
            );
            CREATE TABLE industry_indices (
                date TEXT,
                name TEXT,
                close REAL,
                PRIMARY KEY (name, date)
            );
            '''
        )
        stock_rows = [("20261002", "2330", 100)]
        index_rows = [("20261002", "TAIEX", 10000)]
        industry_rows = [("20261002", "半導體", 500)]
        if include_today:
            stock_rows.append(("20261005", "2330", 105))
            index_rows.append(("20261005", "TAIEX", 10100))
            industry_rows.append(("20261005", "半導體", 505))
        conn.executemany("INSERT INTO daily_prices VALUES (?, ?, ?)", stock_rows)
        conn.executemany("INSERT INTO market_indices VALUES (?, ?, ?)", index_rows)
        conn.executemany("INSERT INTO industry_indices VALUES (?, ?, ?)", industry_rows)


class _FixedOfficialTarget:
    def __init__(self, planned_date: str, seen_as_of: list[str]) -> None:
        self.planned_date = planned_date
        self.seen_as_of = seen_as_of

    def evaluate(self, *, as_of_date: str, **_kwargs):
        self.seen_as_of.append(as_of_date)
        return SimpleNamespace(
            planned_date=self.planned_date,
            status="planned_reached" if self.planned_date <= as_of_date else "pending",
            remaining_sessions=0 if self.planned_date <= as_of_date else 1,
            calendar={"status": "verified_test_calendar"},
        )


def _clocked_forward(
    config: TWStockConfig,
    *,
    now: datetime,
    planned_date: str,
    seen_calendar_dates: list[str],
) -> ForwardPerformanceService:
    return ForwardPerformanceService(
        config,
        EvidenceEventRepository(config),
        maturity_calendar=_FixedOfficialTarget(planned_date, seen_calendar_dates),
        clock=lambda: now + timedelta(seconds=1),
    )


def test_same_day_official_target_stays_pending_until_close_without_reading_today_rows(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from zoneinfo import ZoneInfo

    before_close = datetime(2026, 10, 5, 13, 29, tzinfo=ZoneInfo("Asia/Taipei"))
    for include_today in (False, True):
        config = _config(tmp_path / ("with_today" if include_today else "without_today"))
        _seed_clock_boundary_prices(config.db_file, include_today=include_today)
        event = _record_event(config, event_date="2026-10-02")
        calendar_dates: list[str] = []
        forward = _clocked_forward(
            config,
            now=before_close,
            planned_date="2026-10-05",
            seen_calendar_dates=calendar_dates,
        )
        observed_rows: list[tuple[str | None, tuple[str, ...]]] = []
        exact_lookups: list[str] = []
        original_series = forward._daily_price_series
        original_exact = forward._find_exact_official_outcome_price

        def traced_series(symbol: str, *, as_of_date: str | None = None):
            keys, values = original_series(symbol, as_of_date=as_of_date)
            observed_rows.append((as_of_date, keys))
            return keys, values

        def traced_exact(symbol: str, planned_date: str, *, data_as_of_date: str):
            exact_lookups.append(planned_date)
            return original_exact(
                symbol, planned_date, data_as_of_date=data_as_of_date
            )

        monkeypatch.setattr(forward, "_daily_price_series", traced_series)
        monkeypatch.setattr(forward, "_find_exact_official_outcome_price", traced_exact)

        summary = forward.calculate(
            windows=(1,),
            dry_run=False,
            data_as_of_date="2026-10-05",
            invocation_at=before_close,
        )
        outcome = forward.repository.get_outcome(event.event_id, 1)

        assert outcome is not None
        assert outcome.outcome_status == EvidenceOutcomeStatus.INSUFFICIENT_FUTURE_DATA
        assert "missing_outcome_price" not in outcome.warnings
        assert summary.pending_insufficient_future_data == 1
        assert summary.missing_outcome_price == 0
        assert summary.requested_data_as_of_date == "2026-10-05"
        assert summary.invocation_date_taipei == "2026-10-05"
        assert summary.price_read_cutoff_date == "2026-10-04"
        assert summary.price_read_cutoff_basis == "current_session_close_not_reached"
        assert outcome.metadata["price_read_cutoff_date"] == "2026-10-04"
        assert calendar_dates == ["2026-10-04"]
        assert observed_rows
        assert all(as_of == "2026-10-04" for as_of, _keys in observed_rows)
        assert all("20261005" not in keys for _as_of, keys in observed_rows)
        assert exact_lookups == []


def test_after_close_missing_exact_quote_is_reported_and_historical_cutoff_stays_eod(
    tmp_path: Path,
) -> None:
    from zoneinfo import ZoneInfo

    after_close = datetime(2026, 10, 5, 13, 31, tzinfo=ZoneInfo("Asia/Taipei"))
    config = _config(tmp_path / "after_close")
    _seed_clock_boundary_prices(config.db_file, include_today=False)
    event = _record_event(config, event_date="2026-10-02")
    calendar_dates: list[str] = []
    forward = _clocked_forward(
        config,
        now=after_close,
        planned_date="2026-10-05",
        seen_calendar_dates=calendar_dates,
    )

    summary = forward.calculate(
        windows=(1,),
        dry_run=False,
        data_as_of_date="2026-10-05",
        invocation_at=after_close,
    )
    outcome = forward.repository.get_outcome(event.event_id, 1)

    assert outcome is not None
    assert outcome.outcome_status == EvidenceOutcomeStatus.MISSING_PRICE
    assert "missing_outcome_price" in outcome.warnings
    assert summary.pending_insufficient_future_data == 0
    assert summary.missing_outcome_price == 1
    assert summary.price_read_cutoff_date == "2026-10-05"
    assert summary.price_read_cutoff_basis == "official_session_close_elapsed"
    assert calendar_dates == ["2026-10-05"]

    historical_config = _config(tmp_path / "historical")
    _seed_clock_boundary_prices(historical_config.db_file, include_today=True)
    historical_event = _record_event(historical_config, event_date="2026-10-01")
    with sqlite3.connect(historical_config.db_file) as conn:
        conn.execute(
            'INSERT INTO daily_prices VALUES (?, ?, ?)',
            ("20261001", "2330", 98),
        )
        conn.execute(
            'INSERT INTO market_indices VALUES (?, ?, ?)',
            ("20261001", "TAIEX", 9900),
        )
        conn.execute(
            'INSERT INTO industry_indices VALUES (?, ?, ?)',
            ("20261001", "半導體", 495),
        )
    historical_calendar_dates: list[str] = []
    historical_forward = _clocked_forward(
        historical_config,
        now=datetime(2026, 10, 5, 12, 0, tzinfo=ZoneInfo("Asia/Taipei")),
        planned_date="2026-10-02",
        seen_calendar_dates=historical_calendar_dates,
    )
    historical_summary = historical_forward.calculate(
        windows=(1,),
        dry_run=False,
        data_as_of_date="2026-10-02",
        invocation_at=datetime(2026, 10, 5, 12, 0, tzinfo=ZoneInfo("Asia/Taipei")),
    )
    historical_outcome = historical_forward.repository.get_outcome(historical_event.event_id, 1)

    assert historical_outcome is not None
    assert historical_outcome.outcome_status == EvidenceOutcomeStatus.READY
    assert historical_outcome.outcome_price_date == "2026-10-02"
    assert historical_outcome.data_as_of_date == "2026-10-02"
    assert historical_summary.invocation_date_taipei == "2026-10-05"
    assert historical_summary.requested_data_as_of_date == "2026-10-02"
    assert historical_summary.price_read_cutoff_date == "2026-10-02"
    assert historical_summary.price_read_cutoff_basis == "explicit_historical_data_as_of_date"
    assert historical_calendar_dates == ["2026-10-02"]


def test_forward_rejects_naive_or_future_clock_and_future_data_cutoff_before_event_reads(
    tmp_path: Path,
) -> None:
    from zoneinfo import ZoneInfo

    now = datetime(2026, 10, 5, 12, 0, tzinfo=ZoneInfo("Asia/Taipei"))
    config = _config(tmp_path)
    _seed_clock_boundary_prices(config.db_file, include_today=True)
    _record_event(config, event_date="2026-10-02")
    forward = ForwardPerformanceService(
        config,
        EvidenceEventRepository(config),
        clock=lambda: now,
    )

    def unexpected_event_read(**_kwargs):
        pytest.fail("invalid clock/cutoff must be rejected before event/source reads")

    forward.repository.list_events = unexpected_event_read
    with pytest.raises(ValueError, match="invocation_at must be an aware datetime"):
        forward.calculate(invocation_at=datetime(2026, 10, 5, 12, 0))
    with pytest.raises(ValueError, match="invocation_at cannot be in the future"):
        forward.calculate(invocation_at=now + timedelta(seconds=1))
    with pytest.raises(ValueError, match="data_as_of_date cannot be later than invocation date"):
        forward.calculate(data_as_of_date="2026-10-06", invocation_at=now)

    naive_clock_forward = ForwardPerformanceService(
        config,
        EvidenceEventRepository(config),
        clock=lambda: datetime(2026, 10, 5, 12, 0),
    )
    naive_clock_forward.repository.list_events = unexpected_event_read
    with pytest.raises(ValueError, match="clock must be an aware datetime"):
        naive_clock_forward.calculate()
