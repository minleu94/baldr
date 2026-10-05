from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import json
import sqlite3
from pathlib import Path

import pytest

from app_module import scheduled_forward_outcome_service as forward_runner
from app_module import scheduled_writer_reservation as writer_reservation
from app_module.evidence_event_dtos import EvidenceDataQuality, EvidenceEventType
from app_module.evidence_event_repository import EvidenceEventRepository
from app_module.evidence_event_service import EvidenceEventService
from app_module.official_maturity_calendar import OfficialMaturityCalendar
from app_module.scheduled_forward_outcome_service import run_scheduled_forward_outcomes
from data_module.config import TWStockConfig
from data_module.official_trading_calendar_cache import (
    build_twse_calendar_cache,
    build_twse_temporary_closure_cache,
    write_twse_calendar_cache,
    write_twse_temporary_closure_cache,
)


def _install_deterministic_writer_acquisition_clock(
    monkeypatch: pytest.MonkeyPatch,
    config: TWStockConfig,
) -> None:
    """Freeze service and reservation wall clocks, retaining the real waiter."""
    start = datetime(2026, 10, 4, 20, 0, tzinfo=timezone(timedelta(hours=8)))
    original_wait = forward_runner.wait_for_scheduled_writer_reservation
    clock_calls = 0
    utc_clock_calls = 0

    class DeterministicClock(datetime):
        @classmethod
        def now(cls, tz=None):
            nonlocal clock_calls
            current = start + timedelta(seconds=clock_calls * 10)
            clock_calls += 1
            return current.replace(tzinfo=None) if tz is None else current.astimezone(tz)

    def utc_now_for_test() -> datetime:
        nonlocal utc_clock_calls
        invocation_offset = max(0, clock_calls - 1) * 10
        current = start.astimezone(timezone.utc) + timedelta(
            seconds=invocation_offset + utc_clock_calls % 3
        )
        utc_clock_calls += 1
        return current

    def wait_with_clock(**kwargs):
        assert Path(kwargs["release_root"]).resolve() == (
            config.output_root.resolve() / "release_v4"
        )
        return original_wait(**kwargs)

    monkeypatch.setattr(forward_runner, "datetime", DeterministicClock)
    monkeypatch.setattr(writer_reservation, "_utc_now", utc_now_for_test)
    monkeypatch.setattr(
        forward_runner,
        "wait_for_scheduled_writer_reservation",
        wait_with_clock,
    )


def _write_calendar(
    root: Path,
    *,
    captured_at: datetime,
    year: int = 2026,
) -> Path:
    raw = json.dumps(
        [
            {
                "Name": "國曆新年開始交易日",
                "Date": f"{year - 1911:03d}0102",
                "Weekday": "五",
                "Description": "國曆新年開始交易。",
            },
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    path = root / f"twse_holiday_schedule_{year}_test.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    cache = build_twse_calendar_cache(
        calendar_year=year,
        raw_response=raw,
        requested_at=captured_at - timedelta(seconds=1),
        captured_at=captured_at,
        response_status=200,
        response_headers={"ETag": '"maturity-test"'},
    )
    write_twse_calendar_cache(path, cache, allowed_root=root)
    return path


def test_verified_calendar_returns_planned_date_and_custody_evidence(
    tmp_path: Path,
) -> None:
    captured = datetime(2026, 9, 9, tzinfo=timezone.utc)
    path = _write_calendar(tmp_path / "calendar", captured_at=captured)
    diagnostic = OfficialMaturityCalendar(
        path.parent,
        observed_at=datetime(2026, 9, 10, tzinfo=timezone.utc),
    ).evaluate(
        event_date="2026-09-07",
        window_days=5,
        as_of_date="2026-09-10",
    )

    assert diagnostic.status == "planned"
    assert diagnostic.planned_date == "2026-09-14"
    assert diagnostic.remaining_sessions == 2
    assert diagnostic.calendar["status"] == "annual_plan_only"
    source = diagnostic.calendar["sources"][0]
    assert source["schema_version"] == "official-trading-calendar-cache.v1"
    assert source["cache_file_sha256"].startswith("sha256:")
    assert source["cache_content_sha256"].startswith("sha256:")
    assert source["available_at"] == captured.isoformat()
    assert source["coverage"]["complete_year"] is True


def test_future_capture_and_expired_cache_fail_closed_without_weekday_fallback(
    tmp_path: Path,
) -> None:
    future_path = _write_calendar(
        tmp_path / "future",
        captured_at=datetime(2026, 9, 11, tzinfo=timezone.utc),
    )
    future = OfficialMaturityCalendar(
        future_path.parent,
        observed_at=datetime(2026, 9, 10, tzinfo=timezone.utc),
    ).evaluate(
        event_date="2026-09-07",
        window_days=5,
        as_of_date="2026-09-10",
    )
    assert future.status == "waiting_for_calendar"
    assert future.planned_date is None
    assert "capture is in the future" in future.calendar["reason"]

    expired_path = _write_calendar(
        tmp_path / "expired",
        captured_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
    )
    expired = OfficialMaturityCalendar(
        expired_path.parent,
        observed_at=datetime(2026, 9, 10, tzinfo=timezone.utc),
    ).evaluate(
        event_date="2026-09-07",
        window_days=5,
        as_of_date="2026-09-10",
    )
    assert expired.status == "waiting_for_calendar"
    assert expired.planned_date is None
    assert "freshness window expired" in expired.calendar["reason"]

    tampered_path = _write_calendar(
        tmp_path / "tampered",
        captured_at=datetime(2026, 9, 9, tzinfo=timezone.utc),
    )
    tampered_payload = json.loads(tampered_path.read_text(encoding="utf-8"))
    tampered_payload["raw_response_base64"] = "W10="
    tampered_path.write_text(
        json.dumps(tampered_payload, ensure_ascii=False),
        encoding="utf-8",
    )
    tampered = OfficialMaturityCalendar(
        tampered_path.parent,
        observed_at=datetime(2026, 9, 10, tzinfo=timezone.utc),
    ).evaluate(
        event_date="2026-09-07",
        window_days=5,
        as_of_date="2026-09-10",
    )
    assert tampered.status == "waiting_for_calendar"
    assert tampered.planned_date is None
    assert "content hash mismatch" in tampered.calendar["reason"]


def test_temporary_closure_scope_is_explicit_and_invalid_cache_blocks(
    tmp_path: Path,
) -> None:
    captured = datetime(2026, 9, 9, tzinfo=timezone.utc)
    annual_path = _write_calendar(tmp_path / "annual", captured_at=captured)
    annual_only = OfficialMaturityCalendar(
        annual_path.parent,
        observed_at=datetime(2026, 9, 10, tzinfo=timezone.utc),
    ).evaluate(
        event_date="2026-09-07",
        window_days=5,
        as_of_date="2026-09-10",
    )
    assert annual_only.status == "planned"
    assert annual_only.calendar["status"] == "annual_plan_only"
    assert annual_only.calendar["temporary_closure_status"] == (
        "unconfigured_future_events_unknown"
    )

    invalid_root = tmp_path / "invalid"
    invalid_root.mkdir()
    (invalid_root / "twse_temporary_closure_bad.json").write_text(
        "{not-json",
        encoding="utf-8",
    )
    invalid = OfficialMaturityCalendar(
        annual_path.parent,
        observed_at=datetime(2026, 9, 10, tzinfo=timezone.utc),
        temporary_closure_path=invalid_root,
    ).evaluate(
        event_date="2026-09-07",
        window_days=5,
        as_of_date="2026-09-10",
    )
    assert invalid.status == "waiting_for_calendar"
    assert invalid.planned_date is None
    assert invalid.calendar["temporary_closure_status"] == "invalid_or_missing"

    closure_root = tmp_path / "closure"
    closure_root.mkdir()
    closure_path = closure_root / "twse_temporary_closure_20260910.json"
    source_url = "https://www.twse.com.tw/zh/announcement/announcement/detail.html?id=test"
    closure_cache = build_twse_temporary_closure_cache(
        closure_date=date(2026, 9, 10),
        raw_response="臺灣證券交易所集中交易市場於115年9月10日全日休市一天，因颱風影響。".encode(
            "utf-8"
        ),
        source_url=source_url,
        requested_at=captured - timedelta(seconds=1),
        captured_at=captured,
        response_status=200,
        response_headers={"Content-Type": "text/html"},
        response_url=source_url,
    )
    write_twse_temporary_closure_cache(
        closure_path,
        closure_cache,
        allowed_root=closure_root,
    )
    closure = OfficialMaturityCalendar(
        annual_path.parent,
        observed_at=datetime(2026, 9, 10, tzinfo=timezone.utc),
        temporary_closure_path=closure_root,
    ).evaluate(
        event_date="2026-09-07",
        window_days=5,
        as_of_date="2026-09-10",
    )
    assert closure.status == "planned"
    assert closure.planned_date == "2026-09-15"
    assert closure.calendar["temporary_closure_evidence"][0]["closure_date"] == (
        "2026-09-10"
    )


@pytest.mark.parametrize(
    (
        "source_gap_now",
        "expected_legacy_maturity_date",
        "expected_price_read_cutoff_date",
        "expected_price_read_cutoff_basis",
    ),
    (
        pytest.param(
            datetime(2026, 9, 10, 6, 1, tzinfo=timezone(timedelta(hours=8))),
            None,
            "2026-09-09",
            "current_session_close_not_reached",
            id="before-official-close-excludes-same-day-price",
        ),
        pytest.param(
            datetime(2026, 9, 10, 14, 1, tzinfo=timezone(timedelta(hours=8))),
            "2026-09-10",
            "2026-09-10",
            "official_session_close_elapsed",
            id="after-official-close-includes-same-day-price",
        ),
    ),
)
def test_scheduled_health_uses_future_planned_date_without_changing_outcome_basis(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    source_gap_now: datetime,
    expected_legacy_maturity_date: str | None,
    expected_price_read_cutoff_date: str,
    expected_price_read_cutoff_basis: str,
) -> None:
    config = TWStockConfig(
        data_root=tmp_path / "data",
        output_root=tmp_path / "output",
    )
    _install_deterministic_writer_acquisition_clock(monkeypatch, config)
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
        # Official sessions after 9/1 are 9/2, 9/3, 9/4, 9/7, 9/8.
        # The source has a row but no close for the official 9/8 target;
        # five later non-null rows make the legacy row-offset end on 9/10.
        stock_days = (
            "20260901",
            "20260902",
            "20260903",
            "20260904",
            "20260908",
            "20260909",
            "20260910",
        )
        for index, day in enumerate(stock_days):
            stock_close = None if day == "20260908" else 100 + index
            conn.execute("INSERT INTO daily_prices VALUES (?, ?, ?)", (day, "2330", stock_close))
            conn.execute("INSERT INTO market_indices VALUES (?, ?, ?)", (day, "TAIEX", 10_000 + index))
            conn.execute(
                "INSERT INTO industry_indices VALUES (?, ?, ?)",
                (day, "半導體類指數", 2_000 + index),
            )
    event = EvidenceEventService(EvidenceEventRepository(config)).record_event(
        event_date="2026-09-01",
        decision_date="2026-09-01",
        symbol="2330",
        event_type=EvidenceEventType.RECOMMENDATION_INCLUDED,
        event_family="recommendation",
        source_type="recommendation_result",
        source_id="maturity-calendar-test",
        reason_codes=("rank_top",),
        score_bp=7000,
        data_quality=EvidenceDataQuality.OBSERVED,
        as_of_date="2026-09-01",
        available_date="2026-09-01",
        source_version="test",
        strategy_version_id="strategy-v1",
        cost_model_id="cost-v1",
        benchmark_id="TAIEX",
        industry_benchmark_id="半導體類指數",
        metadata={"universe_id": "universe-v1", "horizon_days": 60},
    )
    cache_path = _write_calendar(
        tmp_path / "calendar",
        captured_at=datetime(2026, 9, 9, tzinfo=timezone.utc),
    )

    result = run_scheduled_forward_outcomes(
        config=config,
        now=datetime(2026, 9, 10, 6, tzinfo=timezone(timedelta(hours=8))),
        confirm=True,
        allow_production_db_confirm=True,
        windows=(60,),
        start_date="2026-09-01",
        end_date="2026-09-10",
        data_as_of_date="2026-09-10",
        calendar_cache_path=cache_path.parent,
    )

    outcome = EvidenceEventRepository(config).list_outcomes()[0]
    assert outcome.outcome_status.value == "insufficient_future_data"
    assert outcome.return_basis == "close_to_close_event_date"
    assert outcome.metadata["planned_official_maturity_date"] > "2026-09-10"
    assert outcome.metadata["planned_official_calendar"]["status"] == (
        "annual_plan_only"
    )
    assert result["health"]["next_maturity_date"] == outcome.metadata[
        "planned_official_maturity_date"
    ]
    assert result["health"]["next_maturity_date_basis"] == (
        "official_annual_plan_only"
    )

    source_gap_result = run_scheduled_forward_outcomes(
        config=config,
        now=source_gap_now,
        confirm=True,
        allow_production_db_confirm=True,
        windows=(5,),
        start_date="2026-09-01",
        end_date="2026-09-10",
        data_as_of_date="2026-09-10",
        calendar_cache_path=cache_path.parent,
    )
    source_gap = EvidenceEventRepository(config).get_outcome(event.event_id, 5)
    assert source_gap is not None
    assert source_gap.outcome_status.value == "missing_price"
    assert source_gap.data_quality == EvidenceDataQuality.MISSING
    assert source_gap.event_price_date == "2026-09-01"
    assert source_gap.outcome_price_date is None
    assert source_gap.outcome_close is None
    assert source_gap.forward_return_bp is None
    assert source_gap.benchmark_return_bp is None
    assert source_gap.benchmark_excess_bp is None
    assert source_gap.industry_return_bp is None
    assert source_gap.industry_excess_bp is None
    assert source_gap.max_adverse_excursion_bp is None
    assert source_gap.max_favorable_excursion_bp is None
    assert source_gap.metadata["requested_data_as_of_date"] == "2026-09-10"
    assert source_gap.metadata["effective_data_as_of_date"] == "2026-09-10"
    assert source_gap.metadata["price_read_cutoff_date"] == (
        expected_price_read_cutoff_date
    )
    assert source_gap.metadata["price_read_cutoff_basis"] == (
        expected_price_read_cutoff_basis
    )
    if expected_legacy_maturity_date is None:
        # The database contains a valid 9/10 close, but it is not readable
        # before that session closes. With only four post-event closes through
        # 9/9, there is no legacy fifth-row maturity date to report.
        assert "expected_maturity_date" not in source_gap.metadata
        assert source_gap.metadata["maturity_calendar_comparison"] == (
            "legacy_expected_unavailable"
        )
    else:
        assert source_gap.metadata["expected_maturity_date"] == (
            expected_legacy_maturity_date
        )
        assert source_gap.metadata["maturity_calendar_comparison"] == (
            "legacy_price_row_offset_differs"
        )
    assert source_gap.metadata["return_basis"] == "close_to_close_event_date"
    assert source_gap.metadata["maturity_basis"] == "official_market_sessions"
    assert source_gap.metadata["planned_official_maturity_date"] == "2026-09-08"
    assert source_gap.metadata["target_price_state"] == (
        "missing_at_planned_official_session"
    )
    assert source_gap.metadata["source_price_gap_reason"] == (
        "no_close_on_planned_official_session"
    )
    assert source_gap.metadata["official_target_price_lookup_detail"] == (
        "daily_price_close_missing_or_invalid_on_planned_official_session"
    )
    assert source_gap.outcome_price_date is None
    assert "missing_outcome_price" in source_gap.warnings
    assert "official_target_session_price_missing" in source_gap.warnings
    assert "evidence_lineage" in source_gap.metadata
    assert source_gap_result["health"]["classification"] == "external_source_missing"
    assert source_gap_result["health"]["planned_official_maturity"][
        "comparison_blocked_count"
    ] == 0
    assert "outcome_price_missing" in source_gap_result["blockers"]
    assert source_gap_result["summary"]["blocked_time_contract_count"] == 0
